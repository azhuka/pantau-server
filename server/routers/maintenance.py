"""Scheduled Maintenance Windows API router."""

from datetime import datetime
import json
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy import desc
from sqlalchemy.orm import Session

from core.database import get_db
from models.misc import AuditLog, MaintenanceWindow
from models.server import Server
from models.user import User
from routers.auth import get_current_user
from services.maintenance_service import evaluate_maintenance_windows

router = APIRouter(tags=["Maintenance Windows"])


def _require_maint_perm(user: User) -> None:
    if not (user.is_master_admin or user.has_perm("can_manage_servers") or user.has_perm("can_server_control")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Server management permission is required",
        )


def _window_server_ids(win: MaintenanceWindow) -> list[int]:
    if win.server_ids:
        try:
            return [int(x) for x in json.loads(win.server_ids)]
        except Exception:
            return []
    if win.server_id:
        return [win.server_id]
    return []


def _user_can_access_window(user: User, win: MaintenanceWindow) -> bool:
    if user.allowed_server_ids is None:
        return True
    if win.scope_type in ("all", "group"):
        return False
    sids = _window_server_ids(win)
    return bool(sids) and all(user.can_access_server(sid) for sid in sids)


def _assert_window_access(user: User, win: MaintenanceWindow) -> None:
    if not _user_can_access_window(user, win):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied for this maintenance window",
        )


def _win_to_dict(w: MaintenanceWindow, servers_map: dict[int, str]) -> dict:
    sids: list[int] = []
    if w.server_ids:
        try:
            sids = [int(x) for x in json.loads(w.server_ids)]
        except Exception:
            sids = []
    elif w.server_id:
        sids = [w.server_id]

    target_label = "All Assets"
    if w.scope_type == "single" and w.server_id:
        target_label = servers_map.get(w.server_id, f"Host #{w.server_id}")
    elif w.scope_type == "group" and w.server_group:
        target_label = f"Group: {w.server_group}"
    elif w.scope_type == "multi" and sids:
        names = [servers_map.get(sid, f"#{sid}") for sid in sids[:3]]
        target_label = ", ".join(names) + (f" (+{len(sids) - 3})" if len(sids) > 3 else "")

    return {
        "id": w.id,
        "title": w.title,
        "description": w.description,
        "scope_type": w.scope_type,
        "server_id": w.server_id,
        "server_ids": sids,
        "server_group": w.server_group,
        "target_label": target_label,
        "schedule_type": w.schedule_type,
        "start_time": w.start_time.isoformat() if w.start_time else None,
        "end_time": w.end_time.isoformat() if w.end_time else None,
        "repeat_days": w.repeat_days,
        "repeat_time_start": w.repeat_time_start,
        "repeat_time_end": w.repeat_time_end,
        "status": w.status,
        "is_active": bool(w.is_active),
        "created_by": w.created_by,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


@router.get("/api/maintenance-windows")
def list_maintenance_windows(
    status_filter: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    evaluate_maintenance_windows(db)
    q = db.query(MaintenanceWindow).filter(MaintenanceWindow.is_active == 1).order_by(desc(MaintenanceWindow.start_time))
    if status_filter and status_filter != "all":
        q = q.filter(MaintenanceWindow.status == status_filter)
    windows = [w for w in q.all() if _user_can_access_window(user, w)]
    servers_map = {s.id: s.hostname for s in db.query(Server.id, Server.hostname).filter(Server.is_active == 1).all()}
    return {
        "windows": [_win_to_dict(w, servers_map) for w in windows],
        "summary": {
            "active": sum(1 for w in windows if w.status == "active"),
            "scheduled": sum(1 for w in windows if w.status == "scheduled"),
            "completed": sum(1 for w in windows if w.status == "completed"),
        },
    }


@router.post("/api/maintenance-windows")
def create_maintenance_window(
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_maint_perm(user)
    title = str(body.get("title") or "").strip()[:150]
    if not title:
        raise HTTPException(status_code=400, detail="Maintenance window title is required")

    try:
        start_dt = datetime.fromisoformat(str(body.get("start_time") or "").replace("Z", "+00:00")).replace(tzinfo=None)
        end_dt = datetime.fromisoformat(str(body.get("end_time") or "").replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        raise HTTPException(status_code=400, detail="Valid start_time and end_time (ISO-8601) are required")

    if end_dt <= start_dt:
        raise HTTPException(status_code=400, detail="End time must be after start time")

    scope_type = str(body.get("scope_type") or "single").lower()
    if scope_type not in ("single", "multi", "group", "all"):
        raise HTTPException(status_code=400, detail="Invalid scope_type")

    schedule_type = str(body.get("schedule_type") or "once").lower()
    if schedule_type not in ("once", "daily", "weekly"):
        raise HTTPException(status_code=400, detail="Invalid schedule_type")

    sid = int(body["server_id"]) if scope_type == "single" and body.get("server_id") else None
    sids_list = [int(x) for x in (body.get("server_ids") or [])] if scope_type == "multi" else []
    sids_json = json.dumps(sids_list) if scope_type == "multi" else None
    sgroup = str(body.get("server_group") or "").strip()[:64] if scope_type == "group" else None

    if user.allowed_server_ids is not None:
        if scope_type in ("all", "group"):
            raise HTTPException(status_code=403, detail="Scoped operators cannot create global or group maintenance windows")
        if scope_type == "single" and (not sid or not user.can_access_server(sid)):
            raise HTTPException(status_code=403, detail="Access denied for selected asset")
        if scope_type == "multi" and (not sids_list or not all(user.can_access_server(x) for x in sids_list)):
            raise HTTPException(status_code=403, detail="Access denied for one or more selected assets")

    now = datetime.utcnow()
    initial_status = "active" if (schedule_type == "once" and start_dt <= now < end_dt) else "scheduled"

    win = MaintenanceWindow(
        title=title,
        description=str(body.get("description") or "").strip() or None,
        scope_type=scope_type,
        server_id=sid,
        server_ids=sids_json,
        server_group=sgroup,
        schedule_type=schedule_type,
        start_time=start_dt,
        end_time=end_dt,
        repeat_days=str(body.get("repeat_days") or "").strip()[:50] or None,
        repeat_time_start=str(body.get("repeat_time_start") or "").strip()[:10] or None,
        repeat_time_end=str(body.get("repeat_time_end") or "").strip()[:10] or None,
        is_active=1,
        status=initial_status,
        created_by=user.username,
    )
    db.add(win)
    db.add(AuditLog(
        server_id=sid,
        username=user.username,
        action="maintenance_create",
        target=title,
        result="success",
        created_at=now,
    ))
    db.commit()
    evaluate_maintenance_windows(db, now)
    db.refresh(win)
    servers_map = {s.id: s.hostname for s in db.query(Server.id, Server.hostname).filter(Server.is_active == 1).all()}
    return {"ok": True, "window": _win_to_dict(win, servers_map), "message": f"Maintenance window '{title}' created"}


@router.post("/api/maintenance-windows/{wid}/complete")
def complete_maintenance_window(
    wid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_maint_perm(user)
    win = db.query(MaintenanceWindow).filter(MaintenanceWindow.id == wid).first()
    if not win:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    _assert_window_access(user, win)
    win.status = "completed"
    db.add(AuditLog(
        server_id=win.server_id,
        username=user.username,
        action="maintenance_complete",
        target=win.title,
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"Maintenance window '{win.title}' completed"}


@router.post("/api/maintenance-windows/{wid}/cancel")
def cancel_maintenance_window(
    wid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_maint_perm(user)
    win = db.query(MaintenanceWindow).filter(MaintenanceWindow.id == wid).first()
    if not win:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    _assert_window_access(user, win)
    win.status = "cancelled"
    win.is_active = 0
    db.add(AuditLog(
        server_id=win.server_id,
        username=user.username,
        action="maintenance_cancel",
        target=win.title,
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"Maintenance window '{win.title}' cancelled"}


@router.delete("/api/maintenance-windows/{wid}")
def delete_maintenance_window(
    wid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_maint_perm(user)
    win = db.query(MaintenanceWindow).filter(MaintenanceWindow.id == wid).first()
    if not win:
        raise HTTPException(status_code=404, detail="Maintenance window not found")
    _assert_window_access(user, win)
    title = win.title
    db.delete(win)
    db.add(AuditLog(
        server_id=win.server_id,
        username=user.username,
        action="maintenance_delete",
        target=title,
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"Maintenance window '{title}' deleted"}
