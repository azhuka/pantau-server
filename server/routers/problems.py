import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from core.database import get_db
from routers.auth import get_current_user
from models.user import User
from models.problem import ServerProblem
from models.server import Server
from models.command import Command
from models.misc import AuditLog
from services.problem_service import check_all_servers_stale

router = APIRouter(prefix="/api/problems", tags=["Problems & Alerts"])

@router.get("")
def list_problems(
    active_only: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengambil daftar insiden / masalah operasional & keamanan NOC."""
    check_all_servers_stale(db)
    query = db.query(ServerProblem, Server.hostname, Server.group_name).join(Server, Server.id == ServerProblem.server_id)
    if active_only:
        query = query.filter(ServerProblem.resolved_at == None)
    
    problems = query.order_by(ServerProblem.id.desc()).limit(100).all()
    result = []
    now = datetime.utcnow()
    
    for prob, hostname, group_name in problems:
        if not user.can_access_server(prob.server_id):
            continue

        # Cek kedaluwarsa pengabaian berbatas waktu
        is_ign = bool(prob.is_ignored)
        if is_ign and prob.ignored_until and prob.ignored_until < now:
            prob.is_ignored = 0
            prob.ignored_until = None
            prob.ignored_reason = None
            prob.ignore_mode = None
            is_ign = False
            try:
                db.commit()
            except Exception:
                db.rollback()

        context_obj = None
        if prob.context:
            try:
                context_obj = json.loads(prob.context)
            except Exception:
                context_obj = prob.context

        # Deteksi aksi yang tersedia
        action = None
        if prob.key.startswith("ssh_active_session:"):
            action = "terminate_session"
        elif prob.key.startswith("service_down:"):
            action = "restart_service"

        result.append({
            "id": prob.id,
            "server_id": prob.server_id,
            "hostname": hostname,
            "group_name": group_name or "Default",
            "key": prob.key,
            "severity": prob.severity,
            "message": prob.message,
            "tip": prob.tip,
            "started_at": prob.started_at.isoformat() if prob.started_at else None,
            "resolved_at": prob.resolved_at.isoformat() if prob.resolved_at else None,
            "resolved_note": prob.resolved_note,
            "is_active": prob.is_active,
            "is_ignored": is_ign,
            "ignored_until": prob.ignored_until.isoformat() if prob.ignored_until else None,
            "ignored_by": prob.ignored_by,
            "ignored_reason": prob.ignored_reason,
            "ignore_mode": prob.ignore_mode,
            "action": action,
            "context": context_obj
        })

    return {"ok": True, "problems": result}


@router.post("/{pid}/ignore")
def ignore_problem_action(
    pid: int,
    body: dict = Body(default={}),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Abaikan insiden (tunda alarm dan sembunyikan dari daftar aktif)."""
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewer accounts cannot ignore incidents")

    prob = db.query(ServerProblem).filter(ServerProblem.id == pid, ServerProblem.resolved_at == None).first()
    if not prob:
        raise HTTPException(status_code=404, detail="Active incident not found")

    if prob.server_id and not user.can_access_server(prob.server_id):
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission for this server")

    duration = str(body.get("duration", "24h")).lower().strip()
    reason = str(body.get("reason", "")).strip()[:255] or None

    now = datetime.utcnow()
    until = None
    ignore_mode = "duration"

    if duration == "2h":
        until = now + timedelta(hours=2)
    elif duration == "24h":
        until = now + timedelta(hours=24)
    elif duration == "7d":
        until = now + timedelta(days=7)
    elif duration == "30d":
        until = now + timedelta(days=30)
    elif duration in ("0", "perm", "permanent", "forever"):
        until = None
        ignore_mode = "permanent"
    elif duration == "incident":
        until = None
        ignore_mode = "incident"
    else:
        until = now + timedelta(hours=24)

    prob.is_ignored = 1
    prob.ignored_until = until
    prob.ignored_by = user.username
    prob.ignored_reason = reason
    prob.ignore_mode = ignore_mode
    prob.updated_at = now

    audit = AuditLog(
        server_id=prob.server_id,
        username=user.username,
        action="problem_ignore",
        target=prob.message[:100],
        result="berhasil",
        meta=f"Diabaikan ({duration}) oleh {user.username}: {reason or 'tanpa alasan'}",
        created_at=now
    )
    db.add(audit)
    db.commit()

    return {
        "ok": True,
        "id": pid,
        "is_ignored": True,
        "ignored_until": until.isoformat() if until else None,
        "ignore_mode": ignore_mode,
        "ignored_by": user.username,
        "ignored_reason": reason,
        "message": f"Insiden berhasil diabaikan ({duration})"
    }


@router.post("/{pid}/unignore")
def unignore_problem_action(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Batalkan pengabaian / aktifkan kembali pemantauan insiden."""
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewer accounts cannot unignore incidents")

    prob = db.query(ServerProblem).filter(ServerProblem.id == pid, ServerProblem.resolved_at == None).first()
    if not prob:
        raise HTTPException(status_code=404, detail="Incident not found")

    if prob.server_id and not user.can_access_server(prob.server_id):
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission for this server")

    now = datetime.utcnow()
    # Bersihkan seluruh riwayat pengabaian pada masalah ini dan key terkait di server ini
    db.query(ServerProblem).filter(
        ServerProblem.server_id == prob.server_id,
        ServerProblem.key == prob.key,
    ).update(
        {
            ServerProblem.is_ignored: 0,
            ServerProblem.ignored_until: None,
            ServerProblem.ignored_reason: None,
            ServerProblem.ignore_mode: None,
            ServerProblem.updated_at: now
        },
        synchronize_session=False,
    )

    audit = AuditLog(
        server_id=prob.server_id,
        username=user.username,
        action="problem_unignore",
        target=prob.message[:100],
        result="berhasil",
        meta=f"Pemantauan diaktifkan kembali oleh {user.username}",
        created_at=now
    )
    db.add(audit)
    db.commit()

    return {"ok": True, "id": pid, "is_ignored": False, "message": "Pemantauan insiden berhasil diaktifkan kembali"}

@router.post("/{pid}/terminate-ssh")
def terminate_ssh_session_action(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Putus paksa sesi SSH aktif yang terdeteksi pada tiket insiden."""
    prob = db.query(ServerProblem).filter(ServerProblem.id == pid).first()
    if not prob or not prob.is_active:
        raise HTTPException(status_code=404, detail="Active problem not found")
    
    if not prob.key.startswith("ssh_active_session:"):
        raise HTTPException(status_code=400, detail="Target incident is not an active SSH session")

    parts = prob.key.split(":")
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Invalid incident key format")
    
    user_name = parts[1]
    tty_name = parts[2].replace("_", "/")

    now = datetime.utcnow()
    # Daftarkan perintah kill sesi SSH ke agen
    cmd = Command(
        server_id=prob.server_id,
        action="terminate_session",
        params=json.dumps({"user": user_name, "tty": tty_name}),
        issued_by=user.username,
        status="pending",
        created_at=now
    )
    db.add(cmd)

    audit = AuditLog(
        server_id=prob.server_id,
        username=user.username,
        action="putus_sesi_ssh",
        target=f"{user_name}@{tty_name}",
        result="antre",
        meta=f"Operator {user.username} memutuskan paksa sesi SSH {user_name} pada {tty_name}",
        created_at=now
    )
    db.add(audit)
    db.commit()

    return {"ok": True, "message": f"Perintah pemutusan sesi SSH {user_name} ({tty_name}) berhasil dijadwalkan"}
