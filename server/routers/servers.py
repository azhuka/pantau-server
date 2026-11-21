import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from core.database import get_db
from routers.auth import get_current_user
from models.user import User
from models.server import Server, ServerExtras, SystemSnapshot
from models.problem import ServerProblem
from models.command import Command
from models.misc import AuditLog

router = APIRouter(prefix="/api/servers", tags=["Servers"])

@router.get("")
def list_servers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Daftar seluruh server armada NOC beserta ringkasan status real-time."""
    servers = db.query(Server).filter(Server.is_active == 1).order_by(Server.id.asc()).all()
    now = datetime.utcnow()
    result = []

    for s in servers:
        if not user.can_access_server(s.id):
            continue

        is_online = False
        if s.last_seen:
            diff_secs = (now - s.last_seen).total_seconds()
            is_online = diff_secs <= 60

        # Snapshot metrik terbaru
        latest_snap = (
            db.query(SystemSnapshot)
            .filter(SystemSnapshot.server_id == s.id)
            .order_by(SystemSnapshot.id.desc())
            .first()
        )

        cpu = latest_snap.cpu if latest_snap else 0.0
        mem_pct = 0.0
        if latest_snap and latest_snap.mem_total and latest_snap.mem_total > 0:
            mem_pct = round((latest_snap.mem_used / latest_snap.mem_total) * 100, 1)

        # Hitung masalah aktif
        active_problems_count = (
            db.query(ServerProblem)
            .filter(ServerProblem.server_id == s.id, ServerProblem.resolved_at == None)
            .count()
        )

        result.append({
            "id": s.id,
            "hostname": s.hostname,
            "ip_address": s.ip_address,
            "group_name": s.group_name or "Default",
            "tier": s.tier,
            "is_online": is_online,
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
            "cpu": cpu,
            "mem_pct": mem_pct,
            "uptime_secs": latest_snap.uptime_secs if latest_snap else 0,
            "active_problems_count": active_problems_count,
            "is_maintenance": bool(s.is_maintenance),
        })

    return {"ok": True, "servers": result}

@router.get("/{sid}")
def get_server_detail(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rincian profil server, spesifikasi perangkat keras, dan snapshot."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

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

    return {
        "ok": True,
        "server": {
            "id": server.id,
            "hostname": server.hostname,
            "ip_address": server.ip_address,
            "group_name": server.group_name,
            "tier": server.tier,
            "last_seen": server.last_seen.isoformat() if server.last_seen else None,
            "kernel": extras.kernel if extras else None,
            "os_label": extras.os_label if extras else None,
            "arch": extras.arch if extras else None,
            "agent_version": extras.agent_version if extras else None,
            "hardware": _parse(extras.hardware_specs) if extras else None,
            "metrics": {
                "cpu": latest_snap.cpu if latest_snap else 0.0,
                "load": [latest_snap.load1, latest_snap.load5, latest_snap.load15] if latest_snap else [0, 0, 0],
                "mem_total": latest_snap.mem_total if latest_snap else 0,
                "mem_used": latest_snap.mem_used if latest_snap else 0,
                "mem_avail": latest_snap.mem_avail if latest_snap else 0,
                "swap_total": latest_snap.swap_total if latest_snap else 0,
                "swap_used": latest_snap.swap_used if latest_snap else 0,
                "uptime_secs": latest_snap.uptime_secs if latest_snap else 0,
                "disks": _parse(latest_snap.disks) if latest_snap else [],
                "net": _parse(latest_snap.net) if latest_snap else {},
            }
        }
    }

@router.get("/{sid}/services")
def get_server_services(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.systemd_units:
        return {"ok": True, "services": []}
    try:
        data = json.loads(extras.systemd_units)
        return {"ok": True, "services": data}
    except Exception:
        return {"ok": True, "services": []}

@router.get("/{sid}/processes")
def get_server_processes(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.top_procs:
        return {"ok": True, "processes": []}
    try:
        data = json.loads(extras.top_procs)
        return {"ok": True, "processes": data}
    except Exception:
        return {"ok": True, "processes": []}

@router.get("/{sid}/ports")
def get_server_ports(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.listening_ports:
        return {"ok": True, "ports": []}
    try:
        data = json.loads(extras.listening_ports)
        return {"ok": True, "ports": data}
    except Exception:
        return {"ok": True, "ports": []}

@router.get("/{sid}/accounts")
def get_server_accounts(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mengembalikan akun pengguna lokal serta sesi SSH remote aktif."""
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
    problems = (
        db.query(ServerProblem)
        .filter(ServerProblem.server_id == sid, ServerProblem.resolved_at == None)
        .order_by(ServerProblem.id.desc())
        .all()
    )
    result = []
    for prob in problems:
        result.append({
            "id": prob.id,
            "key": prob.key,
            "severity": prob.severity,
            "message": prob.message,
            "tip": prob.tip,
            "started_at": prob.started_at.isoformat() if prob.started_at else None,
            "is_active": prob.is_active,
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
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    action = body.get("action")
    params = body.get("params") or {}
    now = datetime.utcnow()

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
