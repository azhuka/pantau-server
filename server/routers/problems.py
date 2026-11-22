import json
from datetime import datetime
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
    query = db.query(ServerProblem, Server.hostname).join(Server, Server.id == ServerProblem.server_id)
    if active_only:
        query = query.filter(ServerProblem.resolved_at == None)
    
    problems = query.order_by(ServerProblem.id.desc()).limit(100).all()
    result = []
    
    for prob, hostname in problems:
        if not user.can_access_server(prob.server_id):
            continue

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
            "key": prob.key,
            "severity": prob.severity,
            "message": prob.message,
            "tip": prob.tip,
            "started_at": prob.started_at.isoformat() if prob.started_at else None,
            "resolved_at": prob.resolved_at.isoformat() if prob.resolved_at else None,
            "resolved_note": prob.resolved_note,
            "is_active": prob.is_active,
            "action": action,
            "context": context_obj
        })

    return {"ok": True, "problems": result}

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
        raise HTTPException(status_code=400, detail="Bukan tiket insiden sesi SSH aktif")

    parts = prob.key.split(":")
    if len(parts) < 3:
        raise HTTPException(status_code=400, detail="Format key insiden tidak valid")
    
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
