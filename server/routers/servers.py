import json
import os
import re
import subprocess
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body, status
from sqlalchemy import func, desc
from sqlalchemy.orm import Session
import security_auth
from core.database import get_db
from core.security import verify_password
from routers.auth import get_current_user
from models.user import User
from models.server import Server, ServerExtras, SystemSnapshot, SysSnapshotHour, Service, Metric
from models.problem import ServerProblem
from models.command import Command
from models.misc import AuditLog
from services.problem_service import check_all_servers_stale, sync_maintenance_state

router = APIRouter(prefix="/api/servers", tags=["Servers"])

def check_server_access(user: User, sid: int) -> None:
    """Validasi hak akses operator terhadap server (scope isolation)."""
    if not user.can_access_server(sid):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission for this server."
        )

def _classify_platform(platform_dict: dict | None, override: str | None = None) -> dict:
    """Klasifikasi tipe platform host: LXC Container, VM (KVM/dll), atau Baremetal."""
    if override in ("baremetal", "vm", "lxc"):
        if override == "baremetal":
            return {"type": "baremetal", "label": "Baremetal", "short_label": "Baremetal", "virt": "Baremetal"}
        elif override == "vm":
            return {"type": "vm", "label": "Virtual Machine (VM)", "short_label": "VM", "virt": "VM"}
        elif override == "lxc":
            return {"type": "lxc", "label": "LXC Container", "short_label": "LXC", "virt": "LXC"}

    if not isinstance(platform_dict, dict) or not platform_dict:
        return {"type": "pending", "label": "Auto Detect", "short_label": "AUTO", "virt": "Auto"}

    virt = str(platform_dict.get("virt") or "").strip().upper()
    vendor = str(platform_dict.get("vendor") or "").strip()
    product = str(platform_dict.get("product") or "").strip()
    p_type = str(platform_dict.get("platform_type") or "").strip().lower()

    if p_type == "lxc" or virt in ("LXC", "LXC-LIBVIRT", "DOCKER", "PODMAN", "CONTAINER", "WSL", "SYSTEMD-NSPAWN"):
        return {
            "type": "lxc",
            "virt": platform_dict.get("virt") or "LXC",
            "label": platform_dict.get("platform_label") or "LXC Container",
            "short_label": "LXC",
            "vendor": vendor,
            "product": product,
        }

    vm_types = ("KVM", "QEMU", "VMWARE", "XEN", "VIRTUALBOX", "ORACLE", "HYPERV", "BOCHS", "BHYVE")
    is_vm = p_type == "vm" or virt in vm_types or any(x in (vendor + product).upper() for x in ("QEMU", "KVM", "VMWARE", "VIRTUALBOX"))
    if is_vm:
        v_name = platform_dict.get("virt") or "KVM"
        return {
            "type": "vm",
            "virt": v_name,
            "label": platform_dict.get("platform_label") or (f"VM ({v_name})" if v_name != "VM" else "Virtual Machine"),
            "short_label": f"VM ({v_name})" if v_name != "VM" else "VM",
            "vendor": vendor,
            "product": product,
        }

    return {
        "type": "baremetal",
        "virt": "Baremetal",
        "label": platform_dict.get("platform_label") or "Baremetal",
        "short_label": "Baremetal",
        "vendor": vendor,
        "product": product,
    }

@router.get("")
def list_servers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Daftar seluruh server armada NOC beserta ringkasan status real-time."""
    check_all_servers_stale(db)
    servers = db.query(Server).filter(Server.is_active == 1).order_by(Server.id.asc()).all()
    # Filter server berdasarkan cakupan otorisasi pengguna (scope isolation)
    servers = [s for s in servers if user.can_access_server(s.id)]
    now = datetime.utcnow()
    result = []

    # Optimasi konkurensi & performa (Zero N+1 Query Batch Loading):
    # 1. Agregasi rincian insiden aktif seluruh aset dalam 1 kueri batch
    active_problems = (
        db.query(ServerProblem)
        .filter(ServerProblem.resolved_at.is_(None))
        .all()
    )
    # Scoping insiden aktif hanya untuk server yang diizinkan bagi pengguna
    active_problems = [p for p in active_problems if user.can_access_server(p.server_id)]
    problems_by_server = {}
    down_services_by_server = {}
    for p in active_problems:
        if p.server_id not in problems_by_server:
            problems_by_server[p.server_id] = []
        problems_by_server[p.server_id].append(p)
        if p.key and p.key.startswith("service_down:"):
            down_services_by_server[p.server_id] = down_services_by_server.get(p.server_id, 0) + 1

    # 2. Ambil snapshot ID terbaru seluruh aset dalam 1 kueri batch
    server_ids = [s.id for s in servers]
    latest_snaps_map = {}
    extras_map = {}
    services_counts = {}

    if server_ids:
        latest_snap_ids = [
            sid for (sid,) in db.query(func.max(SystemSnapshot.id))
            .filter(SystemSnapshot.server_id.in_(server_ids))
            .group_by(SystemSnapshot.server_id)
            .all()
        ]
        if latest_snap_ids:
            snaps = db.query(SystemSnapshot).filter(SystemSnapshot.id.in_(latest_snap_ids)).all()
            latest_snaps_map = {sn.server_id: sn for sn in snaps}

        # 3. Batch load ServerExtras untuk info hardware & platform
        extras_list = db.query(ServerExtras).filter(ServerExtras.server_id.in_(server_ids)).all()
        extras_map = {e.server_id: e for e in extras_list}

        # 4. Batch query jumlah services per server
        services_counts = dict(
            db.query(Service.server_id, func.count(Service.id))
            .filter(Service.server_id.in_(server_ids))
            .group_by(Service.server_id)
            .all()
        )

    for s in servers:
        if not user.can_access_server(s.id):
            continue

        is_online = False
        if s.last_seen:
            diff_secs = (now - s.last_seen).total_seconds()
            is_online = diff_secs <= 60

        # Snapshot metrik terbaru dari map batch
        latest_snap = latest_snaps_map.get(s.id)

        cpu = latest_snap.cpu if latest_snap else 0.0
        mem_pct = 0.0
        if latest_snap and latest_snap.mem_total and latest_snap.mem_total > 0:
            mem_pct = round((latest_snap.mem_used / latest_snap.mem_total) * 100, 1)

        disk_pct = 0.0
        if latest_snap and latest_snap.disks:
            try:
                disks_data = json.loads(latest_snap.disks) if isinstance(latest_snap.disks, str) else latest_snap.disks
                if isinstance(disks_data, list) and disks_data:
                    root_d = next((d for d in disks_data if isinstance(d, dict) and d.get("mount") == "/"), disks_data[0])
                    if isinstance(root_d, dict):
                        disk_pct = float(root_d.get("pct") or root_d.get("used_percent") or root_d.get("percent") or 0.0)
            except Exception:
                disk_pct = 0.0

        # Hitung masalah aktif & breakdown per tingkat keparahan (severity) sesuai Blueprint Asli
        s_tier = getattr(s, "tier", 2) or 2
        s_probs = problems_by_server.get(s.id, [])
        danger_p = []
        critical_p = []
        warning_p = []
        info_p = []
        ignored_p = []

        for p in s_probs:
            if getattr(p, "is_ignored", 0) and (not p.ignored_until or p.ignored_until > now):
                ignored_p.append(p)
                continue

            # Severity Policy: Non-Production assets are capped at warning severity
            raw_sev = (p.severity or "warning").lower()
            if s_tier != 1 and raw_sev in ("danger", "critical", "average"):
                eff_sev = "warning"
            else:
                eff_sev = raw_sev

            if eff_sev == "danger":
                danger_p.append(p)
            elif eff_sev in ("critical", "average"):
                critical_p.append(p)
            elif eff_sev == "warning":
                warning_p.append(p)
            elif eff_sev == "info":
                info_p.append(p)
            else:
                warning_p.append(p)

        danger_count = len(danger_p)
        critical_count = len(critical_p)
        warning_count = len(warning_p)
        info_count = len(info_p)
        ignored_count = len(ignored_p)
        active_problems_count = danger_count + critical_count + warning_count + info_count
        acknowledged_count = sum(1 for p in s_probs if p.acknowledged_by and not getattr(p, "is_ignored", 0))
        all_acknowledged = bool(active_problems_count > 0 and acknowledged_count == active_problems_count)

        danger_msgs = " • ".join(p.message for p in danger_p if p.message)
        critical_msgs = " • ".join(p.message for p in critical_p if p.message)
        warning_msgs = " • ".join(p.message for p in warning_p if p.message)
        info_msgs = " • ".join(p.message for p in info_p if p.message)
        ignored_msgs = " • ".join(p.message for p in ignored_p if p.message)

        # Auto-expire maintenance mode jika batas waktu terlewati
        if s.is_maintenance and s.maintenance_until and s.maintenance_until < now:
            s.is_maintenance = 0
            s.maintenance_until = None
            s.maintenance_reason = None
            db.commit()

        # Deteksi tipe platform & hitung services fisik
        extra = extras_map.get(s.id)
        hw_specs = {}
        if extra and extra.hardware_specs:
            try:
                hw_specs = json.loads(extra.hardware_specs) if isinstance(extra.hardware_specs, str) else extra.hardware_specs
            except Exception:
                hw_specs = {}

        plat_dict = hw_specs.get("platform", {}) if isinstance(hw_specs, dict) else {}
        plat_info = _classify_platform(plat_dict, override=s.platform_override)

        plat_vendor = str(plat_dict.get("vendor") or "").strip()
        plat_product = str(plat_dict.get("product") or "").strip()
        hardware_model = f"{plat_vendor} {plat_product}".strip()
        if not hardware_model or hardware_model.upper() in ("UNKNOWN", "NONE"):
            hardware_model = plat_info.get("virt", "")

        # Ambil primary network interface dari telemetri hardware real
        net_specs = hw_specs.get("network", {}) if isinstance(hw_specs, dict) else {}
        net_ifaces = net_specs.get("interfaces", []) if isinstance(net_specs, dict) else []
        primary_iface = None
        if isinstance(net_ifaces, list):
            for ifc in net_ifaces:
                if isinstance(ifc, dict) and ifc.get("name") and not ifc.get("name", "").startswith(("veth", "br-", "docker", "tailscale", "fake", "lo")):
                    primary_iface = ifc.get("name")
                    break
            if not primary_iface and net_ifaces and isinstance(net_ifaces[0], dict):
                primary_iface = net_ifaces[0].get("name")

        tot_svcs = services_counts.get(s.id, 0)
        down_svcs = down_services_by_server.get(s.id, 0)
        up_svcs = max(0, tot_svcs - down_svcs) if is_online else 0

        result.append({
            "id": s.id,
            "hostname": s.hostname,
            "ip_address": s.ip_address,
            "group_name": s.group_name or "",
            "tags": s.tags or "",
            "tier": s.tier,
            "is_online": is_online,
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
            "cpu": cpu,
            "mem_pct": mem_pct,
            "disk_pct": disk_pct,
            "uptime_secs": latest_snap.uptime_secs if latest_snap else 0,
            # Platform & Hardware facts directly from physical agent telemetry
            "platform_type": plat_info["type"],
            "platform_label": plat_info["label"],
            "platform_short": plat_info["short_label"],
            "platform_vendor": plat_vendor,
            "platform_product": plat_product,
            "hardware_model": hardware_model,
            "net_iface": primary_iface or "",
            # OS, Kernel, Architecture, Agent Version, and Packages from server_extras
            "kernel": extra.kernel if extra and extra.kernel else "",
            "os_label": extra.os_label if extra and extra.os_label else "",
            "arch": extra.arch if extra and extra.arch else "",
            "agent_version": extra.agent_version if extra and extra.agent_version else "",
            "apt_upgradable": extra.apt_upgradable if extra and extra.apt_upgradable else 0,
            # Real performance telemetry from latest snapshot
            "load1": latest_snap.load1 if latest_snap else 0.0,
            "mem_used": latest_snap.mem_used if latest_snap else 0,
            "mem_total": latest_snap.mem_total if latest_snap else 0,
            "services_total": tot_svcs,
            "services_up": up_svcs,
            "active_problems_count": active_problems_count,
            "acknowledged_count": acknowledged_count,
            "all_acknowledged": all_acknowledged,
            "danger_count": danger_count,
            "critical_count": critical_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "ignored_count": ignored_count,
            "danger_msgs": danger_msgs,
            "critical_msgs": critical_msgs,
            "warning_msgs": warning_msgs,
            "info_msgs": info_msgs,
            "ignored_msgs": ignored_msgs,
            "is_maintenance": bool(s.is_maintenance),
            "maintenance_until": s.maintenance_until.isoformat() if s.maintenance_until else None,
            "maintenance_reason": s.maintenance_reason,
            "notes": s.notes or "",
            "platform_override": s.platform_override or "auto",
        })

    return {"ok": True, "servers": result}

@router.get("/{sid}")
def get_server_detail(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rincian profil server, spesifikasi perangkat keras, dan snapshot."""
    check_server_access(user, sid)

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    was_maint = bool(server.is_maintenance)
    if not sync_maintenance_state(server, now) and was_maint:
        db.commit()

    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    latest_snap = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(SystemSnapshot.id.desc())
        .first()
    )

    def _parse(val):
        if not val:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    raw_disks = _parse(latest_snap.disks) if latest_snap else []
    normalized_disks = []
    if isinstance(raw_disks, list):
        for d in raw_disks:
            if isinstance(d, dict):
                d_copy = dict(d)
                pct = d_copy.get("percent") if d_copy.get("percent") is not None else (d_copy.get("pct") if d_copy.get("pct") is not None else d_copy.get("used_percent"))
                if pct is None and d_copy.get("total") and d_copy.get("used"):
                    try:
                        pct = round((d_copy["used"] / d_copy["total"]) * 100, 1)
                    except ZeroDivisionError:
                        pct = 0.0
                d_copy["percent"] = pct
                d_copy["used_percent"] = pct
                d_copy["pct"] = pct
                normalized_disks.append(d_copy)

    return {
        "ok": True,
        "server": {
            "id": server.id,
            "hostname": server.hostname,
            "ip_address": server.ip_address,
            "group_name": server.group_name or "",
            "tier": server.tier,
            "is_online": is_online,
            "last_seen": server.last_seen.isoformat() if server.last_seen else None,
            "is_maintenance": bool(server.is_maintenance),
            "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
            "maintenance_reason": server.maintenance_reason,
            "is_proxmox_ha": bool(server.is_proxmox_ha),
            "is_isolated_net": bool(server.is_isolated_net),
            "tags": server.tags,
            "notes": server.notes,
            "kernel": extras.kernel if extras else None,
            "os_label": extras.os_label if extras else None,
            "arch": extras.arch if extras else None,
            "agent_version": extras.agent_version if extras else None,
            "apt_upgradable": extras.apt_upgradable if extras else 0,
            "hardware": _parse(extras.hardware_specs) if extras else None,
            "metrics": {
                "cpu": latest_snap.cpu if latest_snap else 0.0,
                "load": [latest_snap.load1, latest_snap.load5, latest_snap.load15] if latest_snap else [0, 0, 0],
                "mem_total": latest_snap.mem_total if latest_snap else 0,
                "mem_used": latest_snap.mem_used if latest_snap else 0,
                "mem_avail": latest_snap.mem_avail if latest_snap else 0,
                "swap_total": latest_snap.swap_total if latest_snap else 0,
                "swap_used": latest_snap.swap_used if latest_snap else 0,
                "procs": latest_snap.procs if latest_snap else 0,
                "uptime_secs": latest_snap.uptime_secs if latest_snap else 0,
                "disks": normalized_disks,
                "net": _parse(latest_snap.net) if latest_snap else {},
            }
        }
    }

@router.get("/{sid}/services")
def get_server_services(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_server_access(user, sid)
    if not (user.is_master_admin or user.is_viewer() or user.has_perm("can_services")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Service Control permission (can_services) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()

    normalized_units = []
    raw_units_json = (extras.units if extras and extras.units else None) or (extras.systemd_units if extras and extras.systemd_units else None)
    if raw_units_json:
        try:
            data = json.loads(raw_units_json)
            if isinstance(data, list):
                for s in data:
                    if isinstance(s, dict):
                        name = s.get("name") or s.get("unit") or s.get("service_name") or "service"
                        is_up = (s.get("status") == "up") or (s.get("active") == "active") or (s.get("sub") == "running")
                        active = "active" if is_up else (s.get("active") or "inactive")
                        sub = s.get("sub") or ("running" if is_up else "stopped")
                        desc_val = s.get("description") or (f"Port {s.get('port')}" if s.get("port") else "-")
                        normalized_units.append({
                            "name": name,
                            "active": active,
                            "sub": sub,
                            "status": s.get("status") or sub,
                            "boot": s.get("boot") or "unknown",
                            "memory": s.get("memory"),
                            "description": desc_val,
                            "port": s.get("port"),
                        })
                    elif isinstance(s, str):
                        normalized_units.append({
                            "name": s,
                            "active": "active",
                            "sub": "running",
                            "status": "running",
                            "boot": "unknown",
                            "memory": None,
                            "description": "System service unit",
                            "port": None,
                        })
        except Exception:
            pass

    # Monitored services with latest metric + 24h uptime
    monitored_rows = db.query(Service).filter(Service.server_id == sid).order_by(Service.service_name.asc()).all()
    monitored_list = []
    if monitored_rows:
        svc_ids = [s.id for s in monitored_rows]
        cutoff_24h = datetime.utcnow() - timedelta(hours=24)
        uptime_rows = (
            db.query(
                Metric.service_id,
                func.count(Metric.id),
                func.sum(getattr(func, "if")(Metric.status == "up", 1, 0)),
            )
            .filter(Metric.service_id.in_(svc_ids), Metric.timestamp >= cutoff_24h)
            .group_by(Metric.service_id)
            .all()
        )
        uptime_map = {}
        for u_sid, total_n, up_n in uptime_rows:
            if total_n:
                uptime_map[u_sid] = round((int(up_n or 0) / int(total_n)) * 100, 2)

        for s in monitored_rows:
            latest = (
                db.query(Metric)
                .filter(Metric.service_id == s.id)
                .order_by(desc(Metric.timestamp))
                .first()
            )
            monitored_list.append({
                "id": s.id,
                "service_name": s.service_name,
                "port": s.port,
                "process_name": s.process_name,
                "is_core": bool(s.is_core),
                "is_ignored": bool(s.is_ignored),
                "ignored_until": s.ignored_until.isoformat() if s.ignored_until else None,
                "ignored_by": s.ignored_by,
                "ignored_reason": s.ignored_reason,
                "status": (latest.status if latest else "unknown"),
                "connections": (latest.active_connections if latest else 0),
                "response_time_ms": (latest.response_time_ms if latest else None),
                "health_message": (latest.health_message if latest else None),
                "uptime_24h": uptime_map.get(s.id),
            })

    return {"ok": True, "services": normalized_units, "monitored_services": monitored_list}


@router.post("/{sid}/services/add")
def add_monitored_service(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a service/port to monitored services for this server."""
    check_server_access(user, sid)
    if user.is_viewer() or not (user.is_master_admin or user.has_perm("can_services")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Service Control permission (can_services) is required")

    service_name = str(body.get("service_name") or "").strip()[:100]
    process_name = str(body.get("process_name") or service_name).strip()[:100]
    try:
        port = int(body.get("port") or 0)
    except (TypeError, ValueError):
        port = 0

    if not service_name or not (1 <= port <= 65535):
        raise HTTPException(status_code=400, detail="Service name and valid port (1-65535) are required.")

    existing = db.query(Service).filter(Service.server_id == sid, Service.service_name == service_name).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Service '{service_name}' is already monitored on this host.")

    svc = Service(
        server_id=sid,
        service_name=service_name,
        port=port,
        process_name=process_name or service_name,
        is_core=1 if body.get("is_core", True) else 0,
    )
    db.add(svc)
    db.flush()
    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="service_add",
        target=f"{service_name} (port {port})",
        result="success",
        meta=f"Added monitored service {service_name} on port {port}",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "service_id": svc.id, "message": f"Service '{service_name}' added to monitoring."}


@router.delete("/{sid}/services/{svc_id}")
def delete_monitored_service(
    sid: int,
    svc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove a service from monitored services."""
    check_server_access(user, sid)
    if user.is_viewer() or not (user.is_master_admin or user.has_perm("can_services")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Service Control permission (can_services) is required")

    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Monitored service not found")

    sname = svc.service_name
    db.query(Metric).filter(Metric.service_id == svc.id).delete(synchronize_session=False)
    db.delete(svc)
    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="service_remove",
        target=sname,
        result="success",
        meta=f"Removed service '{sname}' from monitoring",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"Service '{sname}' removed from monitoring."}


@router.post("/{sid}/services/{svc_id}/ignore")
def ignore_monitored_service(
    sid: int,
    svc_id: int,
    body: dict = Body(default={}),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mute/ignore incident alerts for a monitored service."""
    check_server_access(user, sid)
    if user.is_viewer() or not (user.is_master_admin or user.has_perm("can_services")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Service Control permission (can_services) is required")

    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Monitored service not found")

    duration = str(body.get("duration", "permanent")).lower().strip()
    reason = str(body.get("reason", "")).strip()[:255] or f"Ignored by {user.username}"
    now = datetime.utcnow()
    dur_map = {"2h": timedelta(hours=2), "24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}
    until = now + dur_map[duration] if duration in dur_map else None
    ignore_mode = "duration" if until else "permanent"

    svc.is_ignored = 1
    svc.ignored_until = until
    svc.ignored_by = user.username
    svc.ignored_reason = reason
    svc.ignore_mode = ignore_mode

    prob = db.query(ServerProblem).filter(
        ServerProblem.server_id == sid,
        ServerProblem.key == f"service_down:{svc.service_name}",
        ServerProblem.resolved_at.is_(None),
    ).first()
    if prob:
        prob.is_ignored = 1
        prob.ignored_until = until
        prob.ignored_by = user.username
        prob.ignored_reason = reason
        prob.ignore_mode = ignore_mode
        prob.updated_at = now

    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="problem_ignore",
        target=f"Service {svc.service_name}",
        result=f"ignored ({duration})",
        meta=reason,
        created_at=now,
    ))
    db.commit()
    return {"ok": True, "message": f"Alerts ignored for '{svc.service_name}'."}


@router.post("/{sid}/services/{svc_id}/unignore")
def unignore_monitored_service(
    sid: int,
    svc_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Resume incident monitoring for a monitored service."""
    check_server_access(user, sid)
    if user.is_viewer() or not (user.is_master_admin or user.has_perm("can_services")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Service Control permission (can_services) is required")

    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Monitored service not found")

    svc.is_ignored = 0
    svc.ignored_until = None
    svc.ignored_reason = None
    svc.ignore_mode = None

    db.query(ServerProblem).filter(
        ServerProblem.server_id == sid,
        ServerProblem.key == f"service_down:{svc.service_name}",
    ).update({
        ServerProblem.is_ignored: 0,
        ServerProblem.ignored_until: None,
        ServerProblem.ignored_reason: None,
        ServerProblem.ignore_mode: None,
    }, synchronize_session=False)

    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="problem_unignore",
        target=f"Service {svc.service_name}",
        result="monitoring resumed",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"Monitoring resumed for '{svc.service_name}'."}


@router.get("/{sid}/services/{svc_id}/history")
def get_monitored_service_history(
    sid: int,
    svc_id: int,
    range: str = "24h",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return uptime timeline, active connections, and response time history for a monitored service."""
    check_server_access(user, sid)
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Monitored service not found")

    now = datetime.utcnow()
    if range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        span = max(now - start, timedelta(minutes=5))
    else:
        span = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }.get(range)
        if not span:
            raise HTTPException(status_code=400, detail="Unsupported time range")
        start = now - span

    step_secs = max(int(span.total_seconds() / 120), 30)
    rows = (
        db.query(
            (func.floor(func.unix_timestamp(Metric.timestamp) / step_secs) * step_secs).label("tb"),
            func.count(Metric.id),
            func.sum(getattr(func, "if")(Metric.status == "up", 1, 0)),
            func.avg(Metric.active_connections),
            func.avg(Metric.response_time_ms),
        )
        .filter(Metric.service_id == svc_id, Metric.timestamp >= start, Metric.timestamp <= now)
        .group_by("tb")
        .order_by("tb")
        .all()
    )
    points = []
    for tb, n, ups, conns, rt in rows:
        ups_count = int(ups or 0)
        up_ratio = (ups_count / n) if n else None
        points.append({
            "t": int(tb),
            "up_ratio": round(up_ratio, 3) if up_ratio is not None else None,
            "samples": int(n),
            "conns": round(float(conns), 1) if conns is not None else 0,
            "rt": round(float(rt), 1) if rt is not None else None,
        })

    latest = db.query(Metric).filter(Metric.service_id == svc_id).order_by(desc(Metric.timestamp)).first()
    return {
        "ok": True,
        "service": {"id": svc.id, "name": svc.service_name, "port": svc.port},
        "range": range,
        "from": int(start.timestamp()),
        "to": int(now.timestamp()),
        "now": {
            "status": latest.status if latest else "unknown",
            "connections": latest.active_connections if latest else 0,
            "response_time_ms": latest.response_time_ms if latest else None,
        },
        "points": points,
    }

@router.get("/{sid}/processes")
def get_server_processes(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_processes")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Process Manager permission (can_processes) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.top_procs:
        return {"ok": True, "processes": []}
    try:
        data = json.loads(extras.top_procs)
        if isinstance(data, dict):
            merged = []
            seen_pids = set()
            for p in (data.get("cpu") or []) + (data.get("mem") or []):
                pid = p.get("pid")
                if pid and pid not in seen_pids:
                    seen_pids.add(pid)
                    merged.append({
                        "pid": pid,
                        "user": p.get("user") or "unknown",
                        "cpu": p.get("cpu", 0.0),
                        "mem": p.get("mem", 0.0),
                        "cmd": p.get("comm") or p.get("cmd") or "-",
                    })
            return {"ok": True, "processes": merged}
        elif isinstance(data, list):
            return {"ok": True, "processes": data}
        return {"ok": True, "processes": []}
    except Exception:
        return {"ok": True, "processes": []}

@router.get("/{sid}/ports")
def get_server_ports(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_server_access(user, sid)
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.listening_ports:
        return {"ok": True, "ports": []}
    try:
        data = json.loads(extras.listening_ports)
        normalized = []
        if isinstance(data, list):
            for p in data:
                if not isinstance(p, dict):
                    continue
                ip_val = p.get("ip") or p.get("bind") or p.get("address") or "0.0.0.0"
                is_loop = bool(p.get("is_loopback")) or ip_val.startswith(("127.", "::1"))
                is_pub = p.get("is_public") if "is_public" in p else (not is_loop)
                normalized.append({
                    "port": p.get("port"),
                    "proto": (p.get("proto") or "tcp").lower(),
                    "ip": ip_val,
                    "bind": ip_val,
                    "proc": p.get("proc") or p.get("service") or p.get("program") or p.get("process") or "-",
                    "pid": p.get("pid"),
                    "pname": p.get("pname") or "",
                    "is_loopback": is_loop,
                    "is_public": bool(is_pub),
                })
        return {"ok": True, "ports": normalized}
    except Exception:
        return {"ok": True, "ports": []}

@router.get("/{sid}/accounts")
def get_server_accounts(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mengembalikan akun pengguna lokal serta sesi SSH remote aktif."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_users_sys")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: System Users permission (can_users_sys) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.accounts:
        return {"ok": True, "accounts": []}
    try:
        data = json.loads(extras.accounts)
        return {"ok": True, "accounts": data}
    except Exception:
        return {"ok": True, "accounts": []}

@router.get("/{sid}/firewall")
def get_server_firewall(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Status UFW dan daftar aturan firewall."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_firewall")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Firewall Control permission (can_firewall) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.firewall:
        return {"ok": True, "firewall": {"status": "unknown", "rules": [], "blocked_ips": []}}
    try:
        data = json.loads(extras.firewall)
        return {"ok": True, "firewall": data}
    except Exception:
        return {"ok": True, "firewall": {"status": "unknown", "rules": [], "blocked_ips": []}}

@router.get("/{sid}/cron")
def get_server_cron(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Daftar crontab dan systemd timers."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_cron")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Cron Jobs permission (can_cron) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.cron_jobs:
        return {"ok": True, "cron": {"jobs": []}}
    try:
        data = json.loads(extras.cron_jobs)
        return {"ok": True, "cron": data}
    except Exception:
        return {"ok": True, "cron": {"jobs": []}}

@router.get("/{sid}/problems")
def get_server_problems(
    sid: int,
    include_resolved: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Insiden aktif (atas) dan riwayat teratasi (bawah) dalam satu daftar untuk server ini."""
    check_server_access(user, sid)
    srv = db.query(Server).filter(Server.id == sid).first()
    hostname = srv.hostname if srv else f"Server #{sid}"

    sev_rank = {"danger": 0, "critical": 1, "average": 1, "warning": 2, "info": 3}
    open_probs = (
        db.query(ServerProblem)
        .filter(ServerProblem.server_id == sid, ServerProblem.resolved_at.is_(None))
        .order_by(ServerProblem.id.desc())
        .all()
    )
    open_probs.sort(key=lambda p: (sev_rank.get((p.severity or "info").lower(), 4), -(p.id or 0)))

    if include_resolved:
        hist_probs = (
            db.query(ServerProblem)
            .filter(ServerProblem.server_id == sid, ServerProblem.resolved_at.is_not(None))
            .order_by(ServerProblem.resolved_at.desc())
            .limit(30)
            .all()
        )
        problems = open_probs + hist_probs
    else:
        problems = open_probs

    master_names: set[str] = set()
    if not user.is_master_admin:
        master_names = {
            u.username.lower()
            for u in db.query(User).filter(User.role.in_(["master_admin", "master-admin"])).all()
            if u.username
        }

    def _mask_actor(name: str | None) -> str | None:
        if not name:
            return name
        if not user.is_master_admin and name.strip().lower() in master_names:
            return "System"
        return name

    result = []
    now = datetime.utcnow()
    dirty = False
    for prob in problems:
        is_ign = bool(prob.is_ignored)
        if is_ign and prob.ignored_until and prob.ignored_until < now:
            prob.is_ignored = 0
            prob.ignored_until = None
            prob.ignored_reason = None
            prob.ignore_mode = None
            is_ign = False
            dirty = True

        ctx_obj = None
        if prob.context:
            try:
                ctx_obj = json.loads(prob.context) if isinstance(prob.context, str) else prob.context
            except Exception:
                ctx_obj = prob.context

        k = prob.key or ""
        action = None
        log_unit = None
        if k.startswith("ssh_active_session:"):
            action = "terminate_session"
            log_unit = "AUTH"
        elif k.startswith("service_down:"):
            action = "restart_service"
            log_unit = k.split(":", 1)[1]
        elif k == "failed_logins":
            action = "block_ip"
            log_unit = "AUTH"
        elif k in ("apt_updates", "pkg_updates"):
            action = "apt_update"
        elif k.startswith("fim_anomaly:"):
            action = "fim_view"
        elif k == "agent_outdated":
            action = "update_agent"
        elif k.startswith(("cpu_", "ram_", "swap_", "oom_kill:", "segfault:")):
            action = "inspect_processes"
        elif k.startswith("disk_"):
            action = "inspect_storage"

        duration_sec = None
        if prob.started_at:
            end_t = prob.resolved_at or now
            duration_sec = max(0, int((end_t - prob.started_at).total_seconds()))

        result.append({
            "id": prob.id,
            "server_id": prob.server_id,
            "hostname": hostname,
            "key": prob.key,
            "severity": prob.severity,
            "message": prob.message,
            "tip": prob.tip,
            "context": ctx_obj,
            "started_at": prob.started_at.isoformat() if prob.started_at else None,
            "resolved_at": prob.resolved_at.isoformat() if prob.resolved_at else None,
            "resolved_note": prob.resolved_note,
            "duration_sec": duration_sec,
            "is_active": prob.is_active if prob.resolved_at is None else 0,
            "acknowledged_by": _mask_actor(prob.acknowledged_by),
            "acknowledged_at": prob.acknowledged_at.isoformat() if prob.acknowledged_at else None,
            "is_ignored": is_ign,
            "ignored_until": prob.ignored_until.isoformat() if prob.ignored_until else None,
            "ignored_by": _mask_actor(prob.ignored_by),
            "ignored_reason": prob.ignored_reason,
            "ignore_mode": prob.ignore_mode,
            "action": action,
            "log_unit": log_unit,
        })
    if dirty:
        try:
            db.commit()
        except Exception:
            db.rollback()
    return {"ok": True, "problems": result}

_ACTION_PERMISSION_MAP = {
    "restart_service": "can_services",
    "stop_service": "can_services",
    "start_service": "can_services",
    "reload_service": "can_services",
    "enable_service": "can_services",
    "disable_service": "can_services",
    "kill_process": "can_processes",
    "suspend_process": "can_processes",
    "resume_process": "can_processes",
    "reboot_host": "can_server_control",
    "poweroff_host": "can_server_control",
    "shutdown_host": "can_server_control",
    "terminate_session": "can_users_sys",
    "terminate_ssh_session": "can_users_sys",
    "lock_user": "can_users_sys",
    "unlock_user": "can_users_sys",
    "delete_user": "can_users_sys",
    "create_user": "can_users_sys",
    "block_ip": "can_firewall",
    "unblock_ip": "can_firewall",
    "firewall_port_rule": "can_firewall",
    "toggle_ufw": "can_firewall",
    "ufw_enable": "can_firewall",
    "ufw_disable": "can_firewall",
    "ufw_reload": "can_firewall",
    "cron_run": "can_cron",
    "apt_update": "can_apt",
    "apt_upgrade": "can_apt",
    "fim_scan": "can_audit",
    "fim_rebaseline": "can_audit",
    "update_agent": "can_ota",
    "restart_agent": "can_ota",
}


@router.get("/{sid}/actions")
def get_server_action_history(
    sid: int,
    limit: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Riwayat tindakan dan perintah yang dieksekusi melalui aplikasi Pantau Server pada aset ini."""
    check_server_access(user, sid)
    from services.audit_service import query_audit_entries_with_meta
    rows, total_count, _ = query_audit_entries_with_meta(
        db=db,
        user_actor=user,
        period="30d",
        server_id=sid,
        limit=200,
    )
    excluded_actions = {
        "ssh_command", "shell_command", "pantau-shell", "terminal_cmd", "ssh_login",
        "incident_detected", "incident_resolved", "incident_escalated",
        "masalah_danger", "masalah_critical", "masalah_average", "masalah_warning",
        "masalah_info", "masalah_selesai", "eskalasi_insiden",
    }
    filtered = []
    for r in rows:
        act = (r.get("action") or "").lower()
        if act in excluded_actions:
            continue
        # Hindari duplikasi baris 'queued' dari AuditLog jika Command sudah tercatat
        if r.get("kind") == "log" and (r.get("result") or "").upper() == "PENDING" and (r.get("result_detail") or "").lower() == "queued":
            continue
        filtered.append({
            "id": r.get("id"),
            "time": r.get("created_at"),
            "user": r.get("username") or "System",
            "action": r.get("action"),
            "action_label": r.get("action_label") or r.get("action"),
            "target": r.get("target") or "-",
            "status": r.get("result") or "SUCCESS",
            "result": r.get("meta") or r.get("result_detail") or "-",
        })
    max_n = min(max(1, limit), 200)
    return {"ok": True, "actions": filtered[:max_n], "total": len(filtered)}


@router.post("/{sid}/actions")
def dispatch_server_action(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Dispatch an RBAC-validated control command to a target monitored host."""
    check_server_access(user, sid)

    action = str(body.get("action") or "").strip()
    params = body.get("params") or {}
    now = datetime.utcnow()

    req_perm = _ACTION_PERMISSION_MAP.get(action)
    if not req_perm:
        raise HTTPException(status_code=400, detail=f"Unsupported or unknown action: '{action}'")
    if not (user.is_master_admin or user.has_perm(req_perm)):
        raise HTTPException(status_code=403, detail=f"Access denied: Permission '{req_perm}' is required")

    # Normalize to fit varchar(20) commands.action schema & agent_pantau.py handler
    db_action = "terminate_session" if action == "terminate_ssh_session" else action

    if db_action == "update_agent" and not params.get("sha256"):
        from routers.api_agent import _get_latest_agent_meta
        latest_ver, sha256, _ = _get_latest_agent_meta()
        if not sha256:
            raise HTTPException(status_code=404, detail="Agent source not found for OTA push")
        params = {"version": latest_ver, "sha256": sha256}

    # Safety Guardrails: Proteksi Proses Kritis (Anti-Host Crash / Anti-Brick)
    if action in ("kill_process", "suspend_process"):
        try:
            pid = int(params.get("pid", 0))
        except (ValueError, TypeError):
            pid = 0
        pname = str(params.get("pname", "")).strip()
        pname_lower = pname.lower()
        critical_procs = ("sshd", "ssh", "agent_pantau", "agent-pantau", "pantau-server", "systemd", "init")
        if pid <= 1 or any(cp in pname_lower for cp in critical_procs):
            raise HTTPException(
                status_code=400,
                detail=f"Critical process '{pname or 'PID ' + str(pid)}' is protected by system guardrails!"
            )

    # Safety Guardrails: Proteksi Service Kritis (Mencegah putus koneksi agen / SSH)
    if action in ("stop_service", "disable_service"):
        sname = str(params.get("name", "")).strip().lower()
        critical_services = ("agent_pantau", "agent-pantau", "pantau-server", "sshd", "ssh", "systemd")
        if any(cs in sname for cs in critical_services):
            raise HTTPException(
                status_code=400,
                detail=f"Critical service '{params.get('name')}' is protected and cannot be stopped!"
            )

    # Safety Guardrails: Proteksi Port Manajemen (22/8400) dari pemblokiran firewall
    if action == "firewall_port_rule":
        port_spec = str(params.get("port") or "").strip()
        rule_type = str(params.get("rule") or "deny").strip().lower()
        port_num_str = port_spec.split("/")[0].strip()
        if rule_type in ("deny", "block", "deny-port") and port_num_str in ("22", "8400"):
            raise HTTPException(
                status_code=400,
                detail=f"Management port {port_num_str} is protected by system guardrails and cannot be blocked."
            )

    # Host Power Control (Reboot / Power Off): Step-up Auth + Online + Proxmox HA + Anti-Duplicate
    if action in ("poweroff_host", "reboot_host"):
        target_srv = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
        if not target_srv:
            raise HTTPException(status_code=404, detail="Server not found")
        if not target_srv.last_seen or (now - target_srv.last_seen).total_seconds() > 60:
            raise HTTPException(status_code=409, detail="Asset is offline. Power control commands are disabled.")

        if action == "poweroff_host" and getattr(target_srv, "is_proxmox_ha", 0) == 1:
            db.add(AuditLog(
                server_id=sid, username=user.username, action="poweroff_host",
                target=f"{target_srv.hostname} ({target_srv.ip_address})",
                result="rejected", meta="Blocked: Host is protected by Proxmox HA", created_at=now,
            ))
            db.commit()
            raise HTTPException(
                status_code=400,
                detail="Host is protected by Proxmox HA. Perform power off via Proxmox VE Web UI / Cluster Manager."
            )

        op_password = str(params.get("password") or "").strip()
        op_totp = str(params.get("totp") or "").strip()
        if not op_password:
            raise HTTPException(status_code=400, detail="Operator account password is required for power control.")
        if not verify_password(op_password, user.password_hash):
            db.add(AuditLog(
                server_id=sid, username=user.username, action=db_action,
                target=f"{target_srv.hostname} ({target_srv.ip_address})",
                result="failed", meta="Invalid operator password during power control guardrail", created_at=now,
            ))
            db.commit()
            raise HTTPException(status_code=401, detail="Invalid account password. Power command rejected.")
        if user.totp_enabled and user.totp_secret:
            if not op_totp or not security_auth.verify_totp(user.totp_secret, op_totp):
                db.add(AuditLog(
                    server_id=sid, username=user.username, action=db_action,
                    target=f"{target_srv.hostname} ({target_srv.ip_address})",
                    result="failed", meta="Invalid 2FA/TOTP code during power control guardrail", created_at=now,
                ))
                db.commit()
                raise HTTPException(status_code=401, detail="Invalid or expired 2FA / TOTP code.")

        pending_power = db.query(Command).filter(
            Command.server_id == sid,
            Command.action.in_(["poweroff_host", "reboot_host"]),
            Command.status == "pending",
        ).first()
        if pending_power:
            raise HTTPException(status_code=409, detail="A power control command is already queued for this host.")

        # Never persist credentials in commands.params or audit_logs.target
        params = {}

    cmd = Command(
        server_id=sid,
        action=db_action,
        params=json.dumps(params, ensure_ascii=False),
        issued_by=user.username,
        status="pending",
        created_at=now
    )
    db.add(cmd)
    db.flush()

    audit_entry = AuditLog(
        server_id=sid,
        username=user.username,
        action=db_action,
        target=str(params),
        result="queued",
        meta=f"Command {db_action} queued by {user.username}",
        created_at=now
    )
    db.add(audit_entry)
    db.commit()

    return {"ok": True, "command_id": cmd.id, "message": f"Command '{db_action}' queued successfully"}


def _format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}" if unit != 'B' else f"{size_bytes} B"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


@router.post("/{sid}/terminal/exec")
def execute_terminal_command(sid: int):
    """Disabled: use WebSocket PTY terminal (/ws/servers/{sid}/terminal) routed to the remote agent."""
    raise HTTPException(
        status_code=410,
        detail="Localhost terminal/exec is disabled. Use the WebSocket remote agent terminal.",
    )



@router.post("/{sid}/maintenance")
def toggle_server_maintenance(
    sid: int,
    body: dict = Body(default={}),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktifkan atau nonaktifkan status maintenance mode server."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_manage_servers") or user.has_perm("can_server_control")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Manage Servers permission is required")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    was_maint = bool(server.is_maintenance)
    if not sync_maintenance_state(server, now) and was_maint:
        db.commit()

    action = body.get("action", "toggle")
    try:
        duration = int(body.get("duration_minutes", 60) or 0)
    except (ValueError, TypeError):
        duration = 60
    reason = str(body.get("reason", "") or "").strip()[:255]

    if action == "toggle":
        action = "disable" if server.is_maintenance else "enable"

    if action == "enable":
        server.is_maintenance = 1
        server.maintenance_reason = reason or "Scheduled maintenance"
        if duration > 0:
            server.maintenance_until = now + timedelta(minutes=duration)
        else:
            server.maintenance_until = None
        detail_msg = f"Maintenance mode enabled ({duration}m, reason: {server.maintenance_reason})"
    else:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        detail_msg = "Maintenance mode disabled"

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="maintenance_mode",
        target=f"{server.hostname}: is_maintenance={server.is_maintenance}",
        result="success",
        meta=detail_msg,
        created_at=now
    )
    db.add(audit)
    db.commit()

    return {
        "ok": True,
        "is_maintenance": bool(server.is_maintenance),
        "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
        "maintenance_reason": server.maintenance_reason,
        "message": detail_msg
    }


@router.get("/{sid}/packages")
def get_server_packages(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_apt")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Package Manager permission (can_apt) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras:
        return {"ok": True, "packages": [], "upgradable_count": 0}

    apt_map = {}
    if extras.apt_packages:
        try:
            for item in json.loads(extras.apt_packages):
                if isinstance(item, dict) and item.get("name"):
                    apt_map[item["name"]] = item
        except Exception:
            pass

    installed_list = []
    if extras.installed_packages:
        try:
            raw_inst = json.loads(extras.installed_packages)
            if isinstance(raw_inst, list):
                installed_list = raw_inst
        except Exception:
            installed_list = []

    packages = []
    seen = set()
    for pkg in installed_list:
        if not isinstance(pkg, dict) or not pkg.get("name"):
            continue
        name = pkg["name"]
        seen.add(name)
        upg = apt_map.get(name)
        packages.append({
            "name": name,
            "current_version": pkg.get("version") or "-",
            "candidate_version": (upg.get("new_version") or upg.get("candidate_version") or upg.get("version")) if upg else None,
            "arch": pkg.get("arch") or "",
            "size_kb": pkg.get("size_kb") or 0,
            "summary": pkg.get("summary") or "",
            "is_user": bool(pkg.get("is_user")),
            "status": "upgradable" if upg else (pkg.get("status") or "installed"),
        })

    for name, upg in apt_map.items():
        if name not in seen:
            packages.append({
                "name": name,
                "current_version": upg.get("current_version") or "-",
                "candidate_version": upg.get("candidate_version") or upg.get("new_version") or upg.get("version") or "-",
                "arch": "",
                "size_kb": 0,
                "summary": ", ".join(upg.get("services") or []),
                "is_user": True,
                "status": "upgradable",
            })

    packages.sort(key=lambda x: (0 if x["status"] == "upgradable" else 1, x["name"].lower()))
    upg_cnt = extras.apt_upgradable if extras.apt_upgradable is not None else len(apt_map)
    return {"ok": True, "packages": packages, "upgradable_count": upg_cnt}


@router.get("/{sid}/ssl")
def get_server_ssl(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_ssl")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: SSL Certificates permission (can_ssl) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.ssl_certs:
        return {"ok": True, "certs": []}
    try:
        data = json.loads(extras.ssl_certs)
        return {"ok": True, "certs": data}
    except Exception:
        return {"ok": True, "certs": []}


_LOG_GROUP_MAP = {
    "Keamanan & Sistem": "System & Security",
    "Aplikasi / Lainnya": "Applications / Other",
    "Basis Data": "Database",
    "Web Server": "Web Server",
}

_LOG_NAME_MAP = {
    "SYSTEM_ERRORS": "System Critical Errors",
    "AUTH": "SSH & Sudo Auth Log",
    "SYSLOG": "System Syslog",
    "DPKG": "Package History (dpkg.log)",
}


def _normalize_available_logs(avail_data: list) -> list:
    """Normalize log source groups and display names into standard NOC English labels."""
    normalized = []
    for item in avail_data:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        entry = dict(item)
        grp = str(entry.get("group") or "System").strip()
        if grp in _LOG_GROUP_MAP:
            grp = _LOG_GROUP_MAP[grp]
        elif grp.startswith("Layanan ("):
            grp = "Service (" + grp[len("Layanan ("):]
        entry["group"] = grp
        src_id = str(entry.get("id"))
        if src_id in _LOG_NAME_MAP:
            entry["name"] = _LOG_NAME_MAP[src_id]
        normalized.append(entry)
    return normalized


@router.get("/{sid}/logs")
def get_server_logs(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_audit") or user.has_perm("can_services")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Logs audit permission is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    logs_data = []
    avail_data = []
    if extras and extras.system_logs:
        try:
            logs_data = json.loads(extras.system_logs)
        except Exception:
            logs_data = []
    if extras and getattr(extras, "available_logs", None):
        try:
            avail_data = json.loads(extras.available_logs)
        except Exception:
            avail_data = []
    if not avail_data:
        avail_data = [
            {"id": "SYSTEM_ERRORS", "group": "System & Security", "name": "System Critical Errors", "desc": "journalctl -p 0..3"},
            {"id": "AUTH", "group": "System & Security", "name": "SSH & Sudo Auth Log", "desc": "/var/log/auth.log"},
            {"id": "SYSLOG", "group": "System & Security", "name": "System Syslog", "desc": "/var/log/syslog"},
            {"id": "DPKG", "group": "System & Security", "name": "Package History (dpkg.log)", "desc": "/var/log/dpkg.log"},
        ]
    else:
        avail_data = _normalize_available_logs(avail_data)
    return {"ok": True, "logs": logs_data, "available_logs": avail_data}


@router.get("/{sid}/fim")
def get_server_fim(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_audit")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Security/FIM audit permission is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.security:
        return {"ok": True, "fim": []}
    try:
        data = json.loads(extras.security)
        return {"ok": True, "fim": data}
    except Exception:
        return {"ok": True, "fim": []}


@router.post("")
def create_server(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Register a new monitored host and return its one-time agent API key."""
    if not (user.is_master_admin or user.has_perm("can_manage_servers") or user.has_perm("can_server_control")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Server management permission is required",
        )

    import secrets
    from core.utils import hash_api_key

    hostname = str(body.get("hostname") or "").strip()[:255]
    if not hostname:
        raise HTTPException(status_code=400, detail="Hostname is required")

    ip_address = str(body.get("ip_address") or "").strip()[:45] or None
    group_name = str(body.get("group_name") or "").strip()[:64] or None
    tier = 2 if str(body.get("tier")) == "2" else 1
    is_proxmox_ha = 1 if body.get("is_proxmox_ha") else 0

    raw_key = "pk_" + secrets.token_hex(24)
    srv = Server(
        hostname=hostname,
        ip_address=ip_address,
        api_key=hash_api_key(raw_key),
        is_active=1,
        group_name=group_name,
        tier=tier,
        is_proxmox_ha=is_proxmox_ha,
        allow_web_terminal=1,
    )
    db.add(srv)
    db.flush()
    db.add(AuditLog(
        server_id=srv.id,
        username=user.username,
        action="create_server",
        target=f"{hostname} ({ip_address or 'pending'})",
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    db.refresh(srv)
    return {
        "ok": True,
        "server_id": srv.id,
        "hostname": srv.hostname,
        "api_key": raw_key,
        "message": f"Asset '{srv.hostname}' registered successfully",
    }


@router.put("/{sid}")
def update_server(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pembaruan konfigurasi host aset (hostname, ip_address, group_name, tier, platform_override, notes)."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_server_control") or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Host Control permission (can_server_control) is required")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    if "hostname" in body and body["hostname"]:
        server.hostname = str(body["hostname"]).strip()
    if "ip_address" in body:
        server.ip_address = str(body["ip_address"]).strip() if body["ip_address"] else None
    if "group_name" in body:
        server.group_name = str(body["group_name"]).strip() if body["group_name"] else "Default"
    if "tier" in body:
        try:
            server.tier = int(body["tier"])
        except (ValueError, TypeError):
            pass
    if "platform_override" in body:
        po = str(body["platform_override"]).strip().lower()
        server.platform_override = po if po in ("baremetal", "vm", "lxc") else None
    if "notes" in body:
        server.notes = str(body["notes"]).strip() if body["notes"] else None

    audit_entry = AuditLog(
        server_id=sid,
        username=user.username,
        action="update_server",
        target=f"{server.hostname} ({server.ip_address})",
        result="success",
        created_at=datetime.utcnow()
    )
    db.add(audit_entry)
    db.commit()
    db.refresh(server)
    return {"ok": True, "message": f"Host {server.hostname} configuration updated successfully", "server_id": sid}


@router.get("/{sid}/note")
def get_server_note(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Ambil catatan operasional host."""
    check_server_access(user, sid)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")
    return {"ok": True, "notes": server.notes or ""}


@router.put("/{sid}/note")
def update_server_note(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Pembaruan catatan operasional host."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_manage_servers") or user.has_perm("can_server_control")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Manage Servers permission is required")
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    server.notes = str(body.get("notes") or "").strip() or None
    audit_entry = AuditLog(
        server_id=sid,
        username=user.username,
        action="update_server_note",
        target=server.hostname,
        result="success",
        created_at=datetime.utcnow()
    )
    db.add(audit_entry)
    db.commit()
    return {"ok": True, "notes": server.notes or "", "message": "Host notes saved successfully"}


@router.post("/{sid}/test-connection")
def test_server_connection(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Uji konektivitas SSH / socket ke host aset."""
    check_server_access(user, sid)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    import socket
    host = server.ip_address or server.hostname
    port = 22
    start_t = datetime.utcnow()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(3.0)
        res = s.connect_ex((host, port))
        latency_ms = int((datetime.utcnow() - start_t).total_seconds() * 1000)
        if res == 0:
            banner = ""
            try:
                banner = s.recv(1024).decode("utf-8", errors="ignore").strip()
            except Exception:
                pass
            s.close()
            banner_info = f" ({banner})" if banner else ""
            return {
                "ok": True,
                "latency_ms": latency_ms,
                "banner": banner,
                "output": f"SSH Connected: {host}:{port} [{latency_ms}ms]{banner_info}",
                "message": f"SSH connection to {host}:{port} succeeded [{latency_ms}ms]{banner_info}"
            }
        else:
            s.close()
            return {"ok": False, "error": f"Connection to {host}:{port} failed (TCP errno {res})"}
    except Exception as e:
        return {"ok": False, "error": f"Failed to reach {host}:{port}: {str(e)}"}


@router.post("/{sid}/inject-key")
def inject_server_key(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Injeksi SSH Public Key ke node aset."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_server_control")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Host Control permission (can_server_control) is required")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    password = body.get("password") or ""
    if not password:
        raise HTTPException(status_code=400, detail="Password is required for key injection")

    ssh_dir = os.path.expanduser("~/.ssh")
    os.makedirs(ssh_dir, exist_ok=True, mode=0o700)
    pub_key_path = os.path.join(ssh_dir, "id_ed25519.pub")
    priv_key_path = os.path.join(ssh_dir, "id_ed25519")
    if not os.path.exists(pub_key_path):
        pub_key_path_rsa = os.path.join(ssh_dir, "id_rsa.pub")
        if os.path.exists(pub_key_path_rsa):
            pub_key_path = pub_key_path_rsa
        else:
            subprocess.run(
                ["ssh-keygen", "-t", "ed25519", "-N", "", "-f", priv_key_path, "-C", "pantau-noc-key"],
                check=False,
                capture_output=True
            )

    pub_key_content = ""
    if os.path.exists(pub_key_path):
        with open(pub_key_path, "r") as f:
            pub_key_content = f.read().strip()

    is_local = server.ip_address in ("127.0.0.1", "localhost", "::1")
    if is_local and pub_key_content:
        auth_keys_path = os.path.join(ssh_dir, "authorized_keys")
        existing_keys = ""
        if os.path.exists(auth_keys_path):
            with open(auth_keys_path, "r") as f:
                existing_keys = f.read()
        if pub_key_content not in existing_keys:
            with open(auth_keys_path, "a") as f:
                f.write(f"\n{pub_key_content}\n")

    audit_entry = AuditLog(
        server_id=sid,
        username=user.username,
        action="inject_key",
        target=server.hostname,
        result="success",
        created_at=datetime.utcnow()
    )
    db.add(audit_entry)
    db.commit()

    return {
        "ok": True,
        "message": f"SSH public key provisioned for host {server.hostname}"
    }


@router.delete("/{sid}")
def delete_server(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Hapus host dari pemantauan aktif NOC (Soft delete is_active=0)."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_server_control")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Host Control permission (can_server_control) is required")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    server.is_active = 0
    audit_entry = AuditLog(
        server_id=sid,
        username=user.username,
        action="delete_server",
        target=f"{server.hostname} ({server.ip_address})",
        result="success",
        created_at=datetime.utcnow()
    )
    db.add(audit_entry)
    db.commit()
    return {"ok": True, "message": f"Host {server.hostname} removed from inventory"}


@router.post("/{sid}/regenerate-key")
def regenerate_server_key(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rotate the agent API key for a host (Master Admin only)."""
    import secrets
    from core.utils import hash_api_key

    if not user.is_master_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only master-admin can regenerate API keys")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    raw_key = secrets.token_hex(32)
    server.api_key = hash_api_key(raw_key)
    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="regenerate_key",
        target=server.hostname,
        result="success",
        meta="Agent API key rotated",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "api_key": raw_key, "hostname": server.hostname}


@router.post("/{sid}/fim/events/{event_id}/ack")
def ack_fim_event(
    sid: int,
    event_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge a single File Integrity Monitoring (FIM) event."""
    from models.fim import FIMEvent

    check_server_access(user, sid)
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewers cannot acknowledge FIM events")
    ev = db.query(FIMEvent).filter(FIMEvent.id == event_id, FIMEvent.server_id == sid).first()
    if not ev:
        raise HTTPException(status_code=404, detail="FIM event not found")
    now = datetime.utcnow()
    ev.acknowledged = 1
    ev.acknowledged_at = now
    ev.acknowledged_by = user.username
    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="fim_ack",
        target=ev.path[:255],
        result="success",
        created_at=now,
    ))
    db.commit()
    return {"ok": True}


@router.post("/{sid}/fim/events/ack-all")
def ack_all_fim_events(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Acknowledge all pending FIM events for a host."""
    from models.fim import FIMEvent

    check_server_access(user, sid)
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewers cannot acknowledge FIM events")
    now = datetime.utcnow()
    updated = (
        db.query(FIMEvent)
        .filter(FIMEvent.server_id == sid, FIMEvent.acknowledged == 0)
        .update({"acknowledged": 1, "acknowledged_at": now, "acknowledged_by": user.username}, synchronize_session=False)
    )
    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="fim_ack_all",
        target=f"Server #{sid} ({updated} events)",
        result="success",
        created_at=now,
    ))
    db.commit()
    return {"ok": True, "acknowledged_count": updated}


def _extract_max_disk_pct(disks_raw) -> float | None:
    if not disks_raw:
        return None
    try:
        items = json.loads(disks_raw) if isinstance(disks_raw, str) else disks_raw
        if not isinstance(items, list) or not items:
            return None
        pcts = []
        for d in items:
            if isinstance(d, dict):
                val = d.get("used_percent") or d.get("percent") or d.get("pct")
                if val is not None:
                    pcts.append(float(val))
        return round(max(pcts), 1) if pcts else None
    except Exception:
        return None


def _extract_net_bps(net_raw) -> tuple[float, float]:
    if not net_raw:
        return 0.0, 0.0
    try:
        items = json.loads(net_raw) if isinstance(net_raw, str) else net_raw
        if not isinstance(items, list):
            return 0.0, 0.0
        rx, tx = 0.0, 0.0
        for iface in items:
            if isinstance(iface, dict):
                name = str(iface.get("name") or "")
                if name == "lo" or name.startswith(("veth", "br-", "docker")):
                    continue
                rx += float(iface.get("rx_bps") or iface.get("rx_bytes_sec") or 0.0)
                tx += float(iface.get("tx_bps") or iface.get("tx_bytes_sec") or 0.0)
        return round(rx, 1), round(tx, 1)
    except Exception:
        return 0.0, 0.0


@router.get("/{sid}/perf")
def get_server_perf_history(
    sid: int,
    range: str = "24h",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return downsampled performance telemetry history (hourly rollups + raw snapshots)."""
    check_server_access(user, sid)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    if range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        span = max(now - start, timedelta(minutes=5))
    else:
        span = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }.get(range)
        if not span:
            raise HTTPException(status_code=400, detail="Unsupported range parameter")
        start = now - span

    points: list[dict] = []
    if span <= timedelta(hours=24):
        raw_from = start
    else:
        cutoff_raw = now - timedelta(hours=24)
        hour_rows = (
            db.query(SysSnapshotHour)
            .filter(
                SysSnapshotHour.server_id == sid,
                SysSnapshotHour.bucket >= start,
                SysSnapshotHour.bucket < cutoff_raw,
            )
            .order_by(SysSnapshotHour.bucket.asc())
            .all()
        )
        for h in hour_rows:
            mem_pct = round((h.mem_used_avg / h.mem_total) * 100.0, 1) if h.mem_total and h.mem_used_avg is not None else None
            points.append({
                "t": int(h.bucket.timestamp()),
                "cpu": round(h.cpu_avg, 1) if h.cpu_avg is not None else None,
                "mem_pct": mem_pct,
                "disk": round(h.disk_max_pct, 1) if h.disk_max_pct is not None else None,
                "load1": round(h.load1_avg, 2) if h.load1_avg is not None else None,
                "net_rx": 0.0,
                "net_tx": 0.0,
            })
        raw_from = cutoff_raw

    step_secs = max(int(span.total_seconds() / 120), 30)
    raw_rows = (
        db.query(
            (func.floor(func.unix_timestamp(SystemSnapshot.timestamp) / step_secs) * step_secs).label("tb"),
            func.avg(SystemSnapshot.cpu),
            func.avg(SystemSnapshot.load1),
            func.max(SystemSnapshot.mem_total),
            func.avg(SystemSnapshot.mem_used),
            func.max(SystemSnapshot.disks),
            func.max(SystemSnapshot.net),
        )
        .filter(
            SystemSnapshot.server_id == sid,
            SystemSnapshot.timestamp >= raw_from,
            SystemSnapshot.timestamp <= now,
        )
        .group_by("tb")
        .order_by("tb")
        .all()
    )

    for tb_stamp, cpu_avg, load1_avg, mem_total, mem_used, disks_raw, net_raw in raw_rows:
        mem_pct = round((float(mem_used) / float(mem_total)) * 100.0, 1) if mem_total and mem_used is not None else None
        rx_bps, tx_bps = _extract_net_bps(net_raw)
        points.append({
            "t": int(tb_stamp),
            "cpu": round(float(cpu_avg), 1) if cpu_avg is not None else None,
            "mem_pct": mem_pct,
            "disk": _extract_max_disk_pct(disks_raw),
            "load1": round(float(load1_avg), 2) if load1_avg is not None else None,
            "net_rx": rx_bps,
            "net_tx": tx_bps,
        })

    return {"ok": True, "range": range, "points": points}
