import json
from datetime import datetime
from sqlalchemy.orm import Session
from models.server import Server, ServerExtras, SystemSnapshot
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
        extras.agent_version = str(report_dict.get("agent_version") or "")[:16]

    if "accounts" in report_dict:
        extras.accounts = _to_json(report_dict["accounts"])
    if "security" in report_dict:
        extras.security = _to_json(report_dict["security"])

    top_procs = sysd.get("top_procs") if sysd.get("top_procs") is not None else report_dict.get("top_procs")
    if top_procs is not None:
        extras.top_procs = _to_json(top_procs)

    units_raw = report_dict.get("systemd_units") or report_dict.get("services") or report_dict.get("units")
    if units_raw is not None:
        extras.systemd_units = _to_json(units_raw)
    if "units" in report_dict:
        extras.units = _to_json(report_dict["units"])

    if "cron_jobs" in report_dict:
        extras.cron_jobs = _to_json(report_dict["cron_jobs"])
    if "firewall" in report_dict:
        extras.firewall = _to_json(report_dict["firewall"])
    if "listening_ports" in report_dict:
        extras.listening_ports = _to_json(report_dict["listening_ports"])
    if "ssl_certs" in report_dict:
        extras.ssl_certs = _to_json(report_dict["ssl_certs"])

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

    # 3. Evaluasi insiden (termasuk Sesi Remote SSH Aktif)
    evaluate_server_problems(db, srv, report_dict, extras)

    db.commit()
    return {"ok": True, "server_id": srv.id, "status": "processed"}
