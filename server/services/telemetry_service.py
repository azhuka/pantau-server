import json
from datetime import datetime
from sqlalchemy.orm import Session
from models.server import Server, ServerExtras, SystemSnapshot
from services.problem_service import evaluate_server_problems

from core.utils import hash_api_key

def process_telemetry_report(db: Session, api_key: str, report_dict: dict) -> dict:
    hashed_key = hash_api_key(api_key)
    srv = db.query(Server).filter((Server.api_key == hashed_key) | (Server.api_key == api_key)).first()
    if not srv:
        return {"ok": False, "error": "Invalid API Key"}

    now = datetime.utcnow()
    srv.last_seen = now
    client_ip = report_dict.get("ip_address")
    if client_ip and client_ip != "127.0.0.1":
        srv.ip_address = client_ip

    # 1. Snapshot metrik sistem
    load = report_dict.get("load") or [0.0, 0.0, 0.0]
    mem = report_dict.get("mem") or {}
    swap = report_dict.get("swap") or {}
    
    def _to_json(val):
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    snap = SystemSnapshot(
        server_id=srv.id,
        timestamp=now,
        cpu=float(report_dict.get("cpu") or 0.0),
        load1=float(load[0]) if len(load) > 0 else 0.0,
        load5=float(load[1]) if len(load) > 1 else 0.0,
        load15=float(load[2]) if len(load) > 2 else 0.0,
        mem_total=int(mem.get("total") or 0),
        mem_used=int(mem.get("used") or 0),
        mem_avail=int(mem.get("available") or mem.get("free") or 0),
        swap_total=int(swap.get("total") or 0),
        swap_used=int(swap.get("used") or 0),
        procs=int(report_dict.get("procs") or 0),
        uptime_secs=int(report_dict.get("uptime") or 0),
        disks=_to_json(report_dict.get("disk")),
        net=_to_json(report_dict.get("net")),
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
    if "os" in report_dict:
        extras.os_label = str(report_dict.get("os") or "")[:120]
    if "arch" in report_dict:
        extras.arch = str(report_dict.get("arch") or "")[:24]
    if "agent_version" in report_dict:
        extras.agent_version = str(report_dict.get("agent_version") or "")[:16]

    if "accounts" in report_dict:
        extras.accounts = _to_json(report_dict["accounts"])
    if "security" in report_dict:
        extras.security = _to_json(report_dict["security"])
    if "top_procs" in report_dict:
        extras.top_procs = _to_json(report_dict["top_procs"])
    if "systemd_units" in report_dict:
        extras.systemd_units = _to_json(report_dict["systemd_units"])
    if "cron_jobs" in report_dict:
        extras.cron_jobs = _to_json(report_dict["cron_jobs"])
    if "firewall" in report_dict:
        extras.firewall = _to_json(report_dict["firewall"])
    if "listening_ports" in report_dict:
        extras.listening_ports = _to_json(report_dict["listening_ports"])
    if "ssl_certs" in report_dict:
        extras.ssl_certs = _to_json(report_dict["ssl_certs"])
    if "hardware" in report_dict:
        extras.hardware_specs = _to_json(report_dict["hardware"])
    if "kernel_events" in report_dict:
        extras.kernel_events = _to_json(report_dict["kernel_events"])

    # 3. Evaluasi insiden (termasuk Sesi Remote SSH Aktif)
    evaluate_server_problems(db, srv, report_dict, extras)

    db.commit()
    return {"ok": True, "server_id": srv.id, "status": "processed"}
