import json
from datetime import datetime, timedelta
from sqlalchemy import desc
from sqlalchemy.orm import Session
from models.command import Command
from models.misc import AuditLog
from models.server import Server, ServerExtras, Service, SystemSnapshot, Metric
from models.fim import FIMPath, FIMEvent
from services.problem_service import evaluate_server_problems

from core.utils import hash_api_key

def process_telemetry_report(db: Session, api_key: str, report_dict: dict) -> dict:
    hashed_key = hash_api_key(api_key)
    srv = db.query(Server).filter(
        Server.is_active == 1,
        (Server.api_key == hashed_key) | (Server.api_key == api_key),
    ).first()
    if not srv:
        return {"ok": False, "error": "Invalid API Key"}

    now = datetime.utcnow()
    srv.last_seen = now
    client_ip = report_dict.get("ip_address")
    if client_ip and client_ip != "127.0.0.1":
        srv.ip_address = client_ip

    # 1. Snapshot metrik sistem (Mendukung payload mandiri pantau-agent)
    sysd = report_dict.get("system") if isinstance(report_dict.get("system"), dict) else report_dict
    
    cpu_val = float(sysd.get("cpu") if sysd.get("cpu") is not None else (report_dict.get("cpu") or 0.0))

    load = report_dict.get("load")
    if isinstance(load, list) and len(load) >= 3:
        l1, l5, l15 = float(load[0] or 0.0), float(load[1] or 0.0), float(load[2] or 0.0)
    else:
        l1 = float(sysd.get("load1") or 0.0)
        l5 = float(sysd.get("load5") or 0.0)
        l15 = float(sysd.get("load15") or 0.0)

    mem = report_dict.get("mem") if isinstance(report_dict.get("mem"), dict) else {}
    mem_total = int(sysd.get("mem_total") or mem.get("total") or 0)
    mem_used = int(sysd.get("mem_used") or mem.get("used") or 0)
    mem_avail = int(sysd.get("mem_avail") or mem.get("available") or mem.get("free") or 0)

    swap = report_dict.get("swap") if isinstance(report_dict.get("swap"), dict) else {}
    swap_total = int(sysd.get("swap_total") or swap.get("total") or 0)
    swap_used = int(sysd.get("swap_used") or swap.get("used") or 0)

    procs = int(sysd.get("procs") or report_dict.get("procs") or 0)
    uptime_secs = int(sysd.get("uptime") or report_dict.get("uptime") or 0)
    disks_val = sysd.get("disks") if sysd.get("disks") is not None else report_dict.get("disk")
    net_val = sysd.get("net") if sysd.get("net") is not None else report_dict.get("net")

    def _to_json(val):
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    snap = SystemSnapshot(
        server_id=srv.id,
        timestamp=now,
        cpu=cpu_val,
        load1=l1,
        load5=l5,
        load15=l15,
        mem_total=mem_total,
        mem_used=mem_used,
        mem_avail=mem_avail,
        swap_total=swap_total,
        swap_used=swap_used,
        procs=procs,
        uptime_secs=uptime_secs,
        disks=_to_json(disks_val),
        net=_to_json(net_val),
    )
    db.add(snap)

    # 2. Update ServerExtras
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == srv.id).first()
    if not extras:
        extras = ServerExtras(server_id=srv.id)
        db.add(extras)

    extras.updated_at = now
    if "kernel" in report_dict:
        extras.kernel = str(report_dict.get("kernel") or "")[:100]
    if "os_label" in report_dict or "os" in report_dict:
        extras.os_label = str(report_dict.get("os_label") or report_dict.get("os") or "")[:120]
    if "arch" in report_dict:
        extras.arch = str(report_dict.get("arch") or "")[:24]
    if "agent_version" in report_dict:
        new_ver = str(report_dict.get("agent_version") or "")[:16]
        extras.agent_version = new_ver
        from models.command import Command
        exec_otas = db.query(Command).filter(
            Command.server_id == srv.id,
            Command.action == "update_agent",
            Command.status.in_(["pending", "executing"]),
        ).all()
        for ota_cmd in exec_otas:
            try:
                p_ver = json.loads(ota_cmd.params or "{}").get("version")
            except Exception:
                p_ver = None
            if p_ver and new_ver == p_ver:
                ota_cmd.status = "success"
                ota_cmd.result = f"Agent update to v{new_ver} verified via telemetry."
                ota_cmd.executed_at = now

    if "accounts" in report_dict:
        extras.accounts = _to_json(report_dict["accounts"])
    if "groups" in report_dict or "system_groups" in report_dict:
        extras.system_groups = _to_json(report_dict.get("groups") if "groups" in report_dict else report_dict.get("system_groups"))
    if "security" in report_dict:
        extras.security = _to_json(report_dict["security"])

    top_procs = sysd.get("top_procs") if sysd.get("top_procs") is not None else report_dict.get("top_procs")
    if top_procs is not None:
        extras.top_procs = _to_json(top_procs)

    units_raw = report_dict.get("systemd_units") or report_dict.get("units")
    if units_raw is not None:
        extras.systemd_units = _to_json(units_raw)
    if "units" in report_dict:
        extras.units = _to_json(report_dict["units"])

    # Ingest monitored services & metric samples
    raw_services = report_dict.get("services")
    if isinstance(raw_services, list):
        existing_svcs = {
            s.service_name: s
            for s in db.query(Service).filter(Service.server_id == srv.id).all()
        }
        for svc_item in raw_services[:100]:
            if not isinstance(svc_item, dict):
                continue
            sname = str(svc_item.get("service_name") or svc_item.get("name") or "").strip()[:100]
            if not sname:
                continue
            sport = svc_item.get("port")
            try:
                sport = int(sport) if sport is not None else None
            except (TypeError, ValueError):
                sport = None
            sproc = str(svc_item.get("process_name") or svc_item.get("process") or "")[:100] or None
            svc_obj = existing_svcs.get(sname)
            if not svc_obj:
                svc_obj = Service(
                    server_id=srv.id,
                    service_name=sname,
                    port=sport,
                    process_name=sproc,
                )
                db.add(svc_obj)
                db.flush()
                existing_svcs[sname] = svc_obj
            else:
                if sport is not None:
                    svc_obj.port = sport
                if sproc:
                    svc_obj.process_name = sproc

            s_status = str(svc_item.get("status") or "unknown").lower()[:20]
            s_conns = int(svc_item.get("active_connections") or svc_item.get("connections") or 0)
            s_rt = int(svc_item.get("response_time_ms") or 0)
            s_msg = str(svc_item.get("health_message") or "")[:255] or None
            db.add(Metric(
                service_id=svc_obj.id,
                timestamp=now,
                status=s_status,
                active_connections=s_conns,
                response_time_ms=s_rt,
                health_message=s_msg,
            ))

    if "cron_jobs" in report_dict:
        extras.cron_jobs = _to_json(report_dict["cron_jobs"])
    if "firewall" in report_dict:
        extras.firewall = _to_json(report_dict["firewall"])
    if "listening_ports" in report_dict:
        extras.listening_ports = _to_json(report_dict["listening_ports"])
    if "ssl_certs" in report_dict:
        extras.ssl_certs = _to_json(report_dict["ssl_certs"])

    # Ingest File Integrity Monitoring (FIM) paths & events
    fim_payload = report_dict.get("fim")
    if isinstance(fim_payload, dict):
        raw_paths = fim_payload.get("paths") or []
        if isinstance(raw_paths, list) and raw_paths:
            existing_paths = {
                fp.path: fp
                for fp in db.query(FIMPath).filter(FIMPath.server_id == srv.id).all()
            }
            seen_p = set()
            for item in raw_paths[:200]:
                if not isinstance(item, dict):
                    continue
                p_str = str(item.get("path") or "").strip()[:500]
                if not p_str:
                    continue
                seen_p.add(p_str)
                fp = existing_paths.get(p_str)
                if not fp:
                    fp = FIMPath(server_id=srv.id, path=p_str)
                    db.add(fp)
                fp.category = str(item.get("category") or "system")[:20]
                fp.status = str(item.get("status") or "VALID")[:20]
                fp.size_bytes = int(item.get("size_bytes") or item.get("size") or 0)
                fp.size_human = str(item.get("size_human") or "")[:50] or None
                fp.size_detail = str(item.get("size_detail") or "")[:100] or None
                fp.sha256_hash = str(item.get("sha256") or item.get("sha256_hash") or "")[:64] or None
                fp.permissions = str(item.get("permissions") or "")[:30] or None
                fp.owner_group = str(item.get("owner_group") or "")[:60] or None
                fp.last_checked_at = now
                fp.is_active = 1
            for old_p, old_fp in existing_paths.items():
                if old_p not in seen_p:
                    old_fp.is_active = 0

        raw_events = fim_payload.get("events") or []
        if isinstance(raw_events, list):
            for ev in raw_events[:100]:
                if not isinstance(ev, dict):
                    continue
                epath = str(ev.get("path") or "").strip()[:500]
                etype = str(ev.get("event_type") or "MODIFIED").strip()[:50]
                if not epath:
                    continue
                db.add(FIMEvent(
                    server_id=srv.id,
                    path=epath,
                    event_type=etype,
                    severity=str(ev.get("severity") or "warning")[:20],
                    details=str(ev.get("details") or "")[:1000] or None,
                    detected_at=now,
                    acknowledged=0,
                ))

    hw_specs = report_dict.get("hardware_specs") or report_dict.get("hardware")
    if hw_specs is not None:
        extras.hardware_specs = _to_json(hw_specs)

    if "kernel_events" in report_dict:
        extras.kernel_events = _to_json(report_dict["kernel_events"])
    if "system_logs" in report_dict:
        extras.system_logs = _to_json(report_dict["system_logs"])
    if "available_logs" in report_dict:
        extras.available_logs = _to_json(report_dict["available_logs"])

    if "apt" in report_dict and isinstance(report_dict["apt"], dict):
        apt_data = report_dict["apt"]
        extras.apt_upgradable = int(apt_data.get("upgradable") or 0)
        if "packages" in apt_data:
            extras.apt_packages = _to_json(apt_data["packages"])
        extras.apt_last_update = now

    # 3. Proxmox HA Auto-Revive Heuristic (if host revives <5m after poweroff_host with uptime <180s)
    uptime_raw = report_dict.get("uptime")
    try:
        uptime_val = int(uptime_raw) if uptime_raw is not None else None
    except (TypeError, ValueError):
        uptime_val = None
    if uptime_val is not None and uptime_val < 180 and getattr(srv, "is_proxmox_ha", 0) == 0:
        recent_cutoff = now - timedelta(seconds=300)
        recent_poweroff = (
            db.query(Command)
            .filter(
                Command.server_id == srv.id,
                Command.action == "poweroff_host",
                Command.created_at >= recent_cutoff,
            )
            .order_by(desc(Command.created_at))
            .first()
        )
        if recent_poweroff:
            srv.is_proxmox_ha = 1
            db.add(AuditLog(
                server_id=srv.id,
                username="System",
                action="proxmox_ha_detected",
                target=f"{srv.hostname} ({srv.ip_address})",
                result="success",
                meta=f"Auto-revive detected after poweroff (uptime={uptime_val}s); enabled Proxmox HA protection",
                created_at=now,
            ))

    # 4. Evaluasi insiden (termasuk Sesi Remote SSH Aktif)
    evaluate_server_problems(db, srv, report_dict, extras)

    db.commit()
    return {"ok": True, "server_id": srv.id, "status": "processed"}
