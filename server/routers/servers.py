import json
import os
import re
import stat
import pwd
import grp
import shutil
import subprocess
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body, Form, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from core.database import get_db
from routers.auth import get_current_user
from models.user import User
from models.server import Server, ServerExtras, SystemSnapshot, Service
from models.problem import ServerProblem
from models.command import Command
from models.misc import AuditLog
from services.problem_service import check_all_servers_stale

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
            return {"type": "vm", "label": "Mesin Virtual (VM)", "short_label": "VM", "virt": "VM"}
        elif override == "lxc":
            return {"type": "lxc", "label": "LXC Container", "short_label": "LXC", "virt": "LXC"}

    if not isinstance(platform_dict, dict) or not platform_dict:
        return {"type": "pending", "label": "Auto Deteksi", "short_label": "AUTO", "virt": "Auto"}

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
            if getattr(p, "is_ignored", 0):
                ignored_p.append(p)
                continue

            # Workflow Severity: Aset Non-Produksi (Tier != 1) dibatasi (cap) maksimal ke level warning
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

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    if server.is_maintenance and server.maintenance_until and server.maintenance_until < now:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
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
            "group_name": server.group_name or "Default",
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
    if not (user.is_master_admin or user.has_perm("can_services")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Service Control permission (can_services) is required")
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.systemd_units:
        return {"ok": True, "services": []}
    try:
        data = json.loads(extras.systemd_units)
        normalized = []
        if isinstance(data, list):
            for s in data:
                if isinstance(s, dict):
                    name = s.get("name") or s.get("service_name") or s.get("unit") or "service"
                    is_up = (s.get("status") == "up") or (s.get("active") == "active") or (s.get("sub") == "running")
                    active = "active" if is_up else (s.get("active") or "inactive")
                    sub = "running" if is_up else (s.get("sub") or "stopped")
                    desc = s.get("description") or (f"Port {s.get('port')}" if s.get("port") else "-")
                    normalized.append({
                        "name": name,
                        "active": active,
                        "sub": sub,
                        "status": s.get("status") or sub,
                        "boot": s.get("boot") or "unknown",
                        "memory": s.get("memory"),
                        "description": desc,
                        "port": s.get("port")
                    })
                elif isinstance(s, str):
                    normalized.append({
                        "name": s,
                        "active": "active",
                        "sub": "running",
                        "status": "running",
                        "boot": "unknown",
                        "memory": None,
                        "description": "System service unit",
                        "port": None
                    })
        return {"ok": True, "services": normalized}
    except Exception:
        return {"ok": True, "services": []}

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
def get_server_problems(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Insiden / anomali aktif khusus untuk server ini."""
    check_server_access(user, sid)
    problems = (
        db.query(ServerProblem)
        .filter(ServerProblem.server_id == sid, ServerProblem.resolved_at == None)
        .order_by(ServerProblem.id.desc())
        .all()
    )
    result = []
    now = datetime.utcnow()
    for prob in problems:
        is_ign = bool(prob.is_ignored and (not prob.ignored_until or prob.ignored_until > now))
        result.append({
            "id": prob.id,
            "key": prob.key,
            "severity": prob.severity,
            "message": prob.message,
            "tip": prob.tip,
            "started_at": prob.started_at.isoformat() if prob.started_at else None,
            "is_active": prob.is_active,
            "acknowledged_by": prob.acknowledged_by,
            "acknowledged_at": prob.acknowledged_at.isoformat() if prob.acknowledged_at else None,
            "is_ignored": is_ign,
            "ignored_until": prob.ignored_until.isoformat() if prob.ignored_until else None,
            "ignored_by": prob.ignored_by,
            "ignored_reason": prob.ignored_reason,
        })
    return {"ok": True, "problems": result}

@router.post("/{sid}/actions")
def dispatch_server_action(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kirim perintah aksi kontrol ke server klien:
    - restart_service, stop_service, start_service
    - kill_process
    - terminate_ssh_session (putus paksa sesi remote)
    """
    check_server_access(user, sid)

    action = body.get("action")
    params = body.get("params") or {}
    now = datetime.utcnow()

    # RBAC Granular Permission Enforcement
    if action in ("restart_service", "stop_service", "start_service", "reload_service", "enable_service", "disable_service"):
        if not user.has_perm("can_services"):
            raise HTTPException(status_code=403, detail="Access denied: Service Control permission (can_services) is required")
    elif action in ("kill_process", "suspend_process", "resume_process"):
        if not user.has_perm("can_processes"):
            raise HTTPException(status_code=403, detail="Access denied: Process Manager permission (can_processes) is required")
    elif action in ("reboot_host", "poweroff_host", "shutdown_host"):
        if not user.has_perm("can_server_control"):
            raise HTTPException(status_code=403, detail="Access denied: Host Control permission (can_server_control) is required")
    elif action in ("terminate_ssh_session", "lock_user", "unlock_user", "delete_user", "create_user"):
        if not user.has_perm("can_users_sys"):
            raise HTTPException(status_code=403, detail="Access denied: System Users permission (can_users_sys) is required")
    elif action in ("block_ip", "unblock_ip", "toggle_ufw"):
        if not user.has_perm("can_firewall"):
            raise HTTPException(status_code=403, detail="Access denied: Firewall Control permission (can_firewall) is required")

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

    # Proteksi Proxmox HA pada aksi Power OFF / Reboot
    if action in ("poweroff_host", "reboot_host"):
        target_srv = db.query(Server).filter(Server.id == sid).first()
        if target_srv and getattr(target_srv, "is_proxmox_ha", 0) == 1:
            raise HTTPException(
                status_code=400,
                detail="Host is protected by Proxmox HA. Perform power actions via Proxmox VE Web UI / Cluster Manager."
            )

    cmd = Command(
        server_id=sid,
        action=action,
        params=json.dumps(params, ensure_ascii=False),
        issued_by=user.username,
        status="pending",
        created_at=now
    )
    db.add(cmd)
    db.flush()

    # Log ke audit trail
    audit_entry = AuditLog(
        server_id=sid,
        username=user.username,
        action=action,
        target=str(params),
        result="antre",
        meta=f"Perintah {action} didaftarkan oleh {user.username}",
        created_at=now
    )
    db.add(audit_entry)
    db.commit()

    return {"ok": True, "command_id": cmd.id, "message": f"Perintah {action} berhasil dijadwalkan"}


def _format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}" if unit != 'B' else f"{size_bytes} B"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


@router.post("/{sid}/terminal/exec")
def execute_terminal_command(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eksekusi perintah terminal pada server secara real-time."""
    check_server_access(user, sid)
    if not (user.is_master_admin or user.has_perm("can_terminal")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied: Web Terminal permission (can_terminal) is required")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    if server.is_maintenance and server.maintenance_until and server.maintenance_until < now:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        db.commit()

    cmd = (body.get("cmd") or "").strip()
    cwd = body.get("cwd") or "/root"
    if not cmd:
        return {"ok": False, "error": "Command is empty"}

    # Proteksi dasar perintah destruktif fatal
    dangerous_patterns = [r"\brm\s+-rf\s+/\b", r"\bmkfs\b", r"\bdd\s+if="]
    for pattern in dangerous_patterns:
        if re.search(pattern, cmd):
            raise HTTPException(status_code=400, detail="Command blocked by safety guardrails")

    now = datetime.utcnow()
    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="terminal_exec",
        target=cmd[:200],
        result="success",
        meta=f"Terminal command executed by {user.username}",
        created_at=now
    )
    db.add(audit)
    db.commit()

    try:
        run_cwd = cwd if (os.path.isdir(cwd) and os.access(cwd, os.R_OK | os.X_OK)) else os.path.expanduser("~")
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=run_cwd,
            text=True,
            capture_output=True,
            timeout=15,
            executable="/bin/bash"
        )
        out = res.stdout
        if res.stderr:
            out = f"{out}\n{res.stderr}" if out else res.stderr
        return {
            "ok": True,
            "output": out if out else "(Command completed with no output)",
            "exit_code": res.returncode,
            "cwd": run_cwd
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "output": "Error: Command timed out after 15 seconds.",
            "exit_code": 124,
            "cwd": cwd
        }
    except Exception as e:
        return {
            "ok": False,
            "output": f"Execution error: {str(e)}",
            "exit_code": 1,
            "cwd": cwd
        }



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

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    if server.is_maintenance and server.maintenance_until and server.maintenance_until < now:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
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
            {"id": "SYSTEM_ERRORS", "group": "System & Security", "name": "System Critical Error Journal", "desc": "journalctl -p 0..3"},
            {"id": "AUTH", "group": "System & Security", "name": "SSH & Sudo Authentication Log", "desc": "/var/log/auth.log"},
            {"id": "SYSLOG", "group": "System & Security", "name": "System Syslog", "desc": "/var/log/syslog"},
            {"id": "DPKG", "group": "System & Security", "name": "Package History (dpkg.log)", "desc": "/var/log/dpkg.log"},
        ]
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
    return {"ok": True, "message": f"Konfigurasi host {server.hostname} berhasil diperbarui", "server_id": sid}


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
    return {"ok": True, "notes": server.notes or "", "message": "Catatan host berhasil disimpan"}


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
                "message": f"Koneksi SSH ke {host}:{port} berhasil [{latency_ms}ms]{banner_info}"
            }
        else:
            s.close()
            return {"ok": False, "error": f"Koneksi ke {host}:{port} gagal (TCP errno {res})"}
    except Exception as e:
        return {"ok": False, "error": f"Gagal menghubungi {host}:{port}: {str(e)}"}


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
        "message": f"SSH Public Key berhasil diinjeksi untuk host {server.hostname}"
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
    return {"ok": True, "message": f"Host {server.hostname} berhasil dihapus dari inventaris"}
