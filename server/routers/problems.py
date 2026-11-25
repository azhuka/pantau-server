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


def _classify_resolution_type(prob: ServerProblem) -> str:
    """Map resolved problem metadata into canonical blueprint resolution mode."""
    note = (prob.resolved_note or "").strip().lower()
    if prob.acknowledged_by or note == "manual" or "operator" in note:
        return "manual"
    if "server_online" in note:
        return "online"
    if "service_up" in note:
        return "service_up"
    if "server_offline" in note or "stale" in note:
        return "stale_closed"
    if "session_closed" in note or "ssh_closed" in note:
        return "session_closed"
    if "duplicate" in note or "dedup" in note:
        return "dedup"
    return "auto"


def _classify_component(key: str) -> str:
    """Derive human-readable subsystem component label from incident key."""
    k = (key or "").lower()
    if k.startswith("cpu") or "load" in k:
        return "CPU"
    if k.startswith(("mem", "ram", "swap")):
        return "Memory"
    if k.startswith("disk") or "inode" in k:
        return "Storage"
    if k.startswith("service_down"):
        return "Services"
    if k.startswith("ssh_") or "firewall" in k or "fim" in k:
        return "Security"
    if "offline" in k or "host_down" in k:
        return "Connectivity"
    if k.startswith("apt") or "pkg" in k:
        return "Packages"
    return "System"


@router.get("")
def list_problems(
    active_only: bool = True,
    server_id: int | None = None,
    group_name: str | None = None,
    severity: str | None = None,
    res_type: str | None = None,
    period: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 150,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengambil daftar insiden / masalah operasional & keamanan NOC."""
    check_all_servers_stale(db)
    query = db.query(ServerProblem, Server.hostname, Server.group_name).join(Server, Server.id == ServerProblem.server_id)
    
    now = datetime.utcnow()
    if active_only:
        query = query.filter(ServerProblem.resolved_at == None)
    else:
        # Jika melihat arsip riwayat teratasi
        query = query.filter(ServerProblem.resolved_at != None)
        if period == "today":
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            query = query.filter(ServerProblem.resolved_at >= start_of_day)
        elif period == "24h":
            query = query.filter(ServerProblem.resolved_at >= now - timedelta(hours=24))
        elif period == "7d":
            query = query.filter(ServerProblem.resolved_at >= now - timedelta(days=7))
        elif period == "30d":
            query = query.filter(ServerProblem.resolved_at >= now - timedelta(days=30))
        elif (period == "custom" or (start_date or end_date)):
            try:
                if start_date:
                    s_dt = datetime.fromisoformat(start_date[:10])
                    query = query.filter(ServerProblem.resolved_at >= s_dt)
                if end_date:
                    e_dt = datetime.fromisoformat(end_date[:10]).replace(hour=23, minute=59, second=59)
                    query = query.filter(ServerProblem.resolved_at <= e_dt)
            except Exception:
                pass

    if server_id:
        query = query.filter(ServerProblem.server_id == server_id)
    if group_name:
        if group_name == "__none__":
            query = query.filter((Server.group_name == None) | (Server.group_name == ""))
        else:
            query = query.filter(Server.group_name == group_name)
    if severity and severity != "all":
        query = query.filter(ServerProblem.severity == severity)
    
    problems = query.order_by(ServerProblem.id.desc()).limit(limit).all()
    result = []
    
    for prob, hostname, s_group_name in problems:
        if not user.can_access_server(prob.server_id):
            continue

        derived_res_type = _classify_resolution_type(prob) if prob.resolved_at else None
        if res_type and res_type != "all" and derived_res_type != res_type:
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

        # Hitung durasi terukur
        duration_sec = None
        if prob.started_at:
            end_t = prob.resolved_at or now
            duration_sec = max(0, int((end_t - prob.started_at).total_seconds()))

        result.append({
            "id": prob.id,
            "server_id": prob.server_id,
            "hostname": hostname,
            "group_name": s_group_name or "",
            "component": _classify_component(prob.key),
            "key": prob.key,
            "severity": prob.severity,
            "message": prob.message,
            "tip": prob.tip,
            "started_at": prob.started_at.isoformat() if prob.started_at else None,
            "resolved_at": prob.resolved_at.isoformat() if prob.resolved_at else None,
            "resolved_note": prob.resolved_note,
            "res_type": derived_res_type,
            "duration_sec": duration_sec,
            "is_active": prob.is_active,
            "acknowledged_by": prob.acknowledged_by,
            "acknowledged_at": prob.acknowledged_at.isoformat() if prob.acknowledged_at else None,
            "is_ignored": is_ign,
            "ignored_until": prob.ignored_until.isoformat() if prob.ignored_until else None,
            "ignored_by": prob.ignored_by,
            "ignored_reason": prob.ignored_reason,
            "ignore_mode": prob.ignore_mode,
            "action": action,
            "context": context_obj
        })

    return {"ok": True, "problems": result}


@router.get("/stats")
def get_incident_stats(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengambil ringkasan statistik insiden aktif & metrik kinerja pemulihan (MTTR)."""
    # 1. Hitung ringkasan insiden aktif
    active_probs = db.query(ServerProblem).filter(ServerProblem.resolved_at == None).all()
    counts = {"danger": 0, "critical": 0, "warning": 0, "info": 0, "ignored": 0, "active_total": 0}
    for p in active_probs:
        if not user.can_access_server(p.server_id):
            continue
        if p.is_ignored:
            counts["ignored"] += 1
        else:
            counts["active_total"] += 1
            sev = (p.severity or "").lower()
            if sev in counts:
                counts[sev] += 1

    # 2. Hitung statistik riwayat pemulihan (30 hari terakhir) untuk kalkulasi MTTR
    since_30d = datetime.utcnow() - timedelta(days=30)
    resolved_probs = db.query(ServerProblem).filter(
        ServerProblem.resolved_at != None,
        ServerProblem.resolved_at >= since_30d
    ).all()

    total_resolved = 0
    auto_count = 0
    manual_count = 0
    total_duration_sec = 0.0

    for p in resolved_probs:
        if not user.can_access_server(p.server_id):
            continue
        total_resolved += 1
        if p.started_at and p.resolved_at:
            dur = (p.resolved_at - p.started_at).total_seconds()
            if dur > 0:
                total_duration_sec += dur
        if p.acknowledged_by or p.resolved_note == "manual":
            manual_count += 1
        else:
            auto_count += 1

    avg_mttr_sec = (total_duration_sec / total_resolved) if total_resolved > 0 else 0
    if avg_mttr_sec < 60:
        mttr_str = f"{int(avg_mttr_sec)}s"
    elif avg_mttr_sec < 3600:
        mttr_str = f"{int(avg_mttr_sec // 60)}m {int(avg_mttr_sec % 60)}s"
    else:
        h = int(avg_mttr_sec // 3600)
        m = int((avg_mttr_sec % 3600) // 60)
        mttr_str = f"{h}h {m}m"

    return {
        "ok": True,
        "active": counts,
        "resolved": {
            "total": total_resolved,
            "auto_count": auto_count,
            "manual_count": manual_count,
            "avg_mttr_seconds": avg_mttr_sec,
            "avg_mttr_formatted": mttr_str if total_resolved > 0 else "-"
        }
    }


@router.get("/thresholds")
def get_thresholds_endpoint(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengambil konfigurasi ambang batas global insiden."""
    from services.problem_service import get_global_thresholds, DEFAULT_THRESHOLDS
    current = get_global_thresholds(db)
    return {"ok": True, "thresholds": current, "defaults": DEFAULT_THRESHOLDS}


@router.post("/thresholds")
def update_thresholds_endpoint(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update global incident thresholds via canonical validator."""
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewer accounts cannot edit thresholds")
    if not (user.is_master_admin or (user.allowed_server_ids is None and user.has_perm("can_manage_servers"))):
        raise HTTPException(status_code=403, detail="Access denied: Global server management permission is required")

    from routers.settings import validate_and_save_thresholds
    merged = validate_and_save_thresholds(db, body, user.username)
    return {"ok": True, "thresholds": merged, "message": "Global incident thresholds updated successfully"}


@router.post("/{pid}/ack")
def acknowledge_problem_action(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Tandai insiden sedang ditangani oleh operator (Acknowledge). Insiden tetap aktif secara fisik."""
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewer accounts cannot acknowledge incidents")

    prob = db.query(ServerProblem).filter(ServerProblem.id == pid, ServerProblem.resolved_at == None).first()
    if not prob:
        raise HTTPException(status_code=404, detail="Active incident not found")

    if prob.server_id and not user.can_access_server(prob.server_id):
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission for this server")

    now = datetime.utcnow()
    prob.acknowledged_by = user.username
    prob.acknowledged_at = now
    prob.updated_at = now

    audit = AuditLog(
        server_id=prob.server_id,
        username=user.username,
        action="problem_ack",
        target=prob.message[:100],
        result="berhasil",
        meta=f"Insiden ditandai sedang ditangani oleh {user.username}",
        created_at=now
    )
    db.add(audit)
    db.commit()

    return {
        "ok": True,
        "id": pid,
        "acknowledged_by": user.username,
        "acknowledged_at": now.isoformat(),
        "message": f"Insiden berhasil ditandai sedang ditangani oleh {user.username}"
    }


@router.post("/{pid}/unack")
def unacknowledge_problem_action(
    pid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Membatalkan status penanganan insiden (Unacknowledge)."""
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewer accounts cannot unacknowledge incidents")

    prob = db.query(ServerProblem).filter(ServerProblem.id == pid, ServerProblem.resolved_at == None).first()
    if not prob:
        raise HTTPException(status_code=404, detail="Active incident not found")

    if prob.server_id and not user.can_access_server(prob.server_id):
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission for this server")

    now = datetime.utcnow()
    old_ack = prob.acknowledged_by
    prob.acknowledged_by = None
    prob.acknowledged_at = None
    prob.updated_at = now

    audit = AuditLog(
        server_id=prob.server_id,
        username=user.username,
        action="problem_unack",
        target=prob.message[:100],
        result="berhasil",
        meta=f"Tanda penanganan insiden dibatalkan oleh {user.username} (sebelumnya: {old_ack})",
        created_at=now
    )
    db.add(audit)
    db.commit()

    return {
        "ok": True,
        "id": pid,
        "acknowledged_by": None,
        "acknowledged_at": None,
        "message": f"Tanda penanganan insiden berhasil dibatalkan oleh {user.username}"
    }


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
    if user.is_viewer:
        raise HTTPException(status_code=403, detail="Access denied: Viewer accounts cannot terminate sessions")

    prob = db.query(ServerProblem).filter(ServerProblem.id == pid).first()
    if not prob or not prob.is_active:
        raise HTTPException(status_code=404, detail="Active problem not found")

    if prob.server_id and not user.can_access_server(prob.server_id):
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission for this server")

    if not user.is_master_admin and not user.has_perm("can_users_sys"):
        raise HTTPException(status_code=403, detail="Access denied: System Users permission (can_users_sys) is required to terminate SSH sessions")
    
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
