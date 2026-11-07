"""Scheduled maintenance windows router."""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

try:
    from models import MaintenanceWindow, Server
    from core.database import get_db
    from core.security import (
        get_current_user,
        _verify_csrf_header,
    )
    from core.templates import tpl
    from core.utils import _parse_iso_datetime
    from services.audit_service import _audit
    from services.maintenance_service import _evaluate_maintenance_windows
    from services.server_service import get_existing_groups_and_tags
except ImportError:
    from server.models import MaintenanceWindow, Server
    from server.core.database import get_db
    from server.core.security import (
        get_current_user,
        _verify_csrf_header,
    )
    from server.core.templates import tpl
    from server.core.utils import _parse_iso_datetime
    from server.services.audit_service import _audit
    from server.services.maintenance_service import _evaluate_maintenance_windows
    from server.services.server_service import get_existing_groups_and_tags

router = APIRouter(tags=["Maintenance"])


@router.get("/maintenance", response_class=HTMLResponse)
def maintenance_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    servers_list = db.query(Server).order_by(Server.hostname).all()
    servers_data = [
        {"id": s.id, "hostname": s.hostname, "ip_address": s.ip_address, "group_name": s.group_name}
        for s in servers_list
    ]
    groups, _ = get_existing_groups_and_tags(db)
    can_manage = user.is_master_admin() or user.has_perm("can_manage_servers")

    return tpl(
        request,
        "maintenance.html",
        {
            "user": user,
            "servers": servers_data,
            "groups": sorted(groups),
            "server_groups": sorted(groups),
            "can_manage": can_manage,
        },
    )


@router.get("/api/maintenance-windows")
def api_maintenance_windows_list(
    request: Request,
    status: Optional[str] = None,
    scope_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Harap login terlebih dahulu")

    _evaluate_maintenance_windows(db)

    query = db.query(MaintenanceWindow).order_by(MaintenanceWindow.id.desc())

    if status and status != "all":
        query = query.filter(MaintenanceWindow.status == status)

    if scope_type and scope_type != "all":
        query = query.filter(MaintenanceWindow.scope_type == scope_type)

    all_windows = db.query(MaintenanceWindow).all()
    active_count = sum(1 for w in all_windows if w.status == "active")
    upcoming_count = sum(1 for w in all_windows if w.status == "scheduled")
    completed_count = sum(1 for w in all_windows if w.status in ("completed", "cancelled"))

    windows = query.all()
    all_servers_map = {s.id: s.hostname for s in db.query(Server).all()}
    result = []
    for w in windows:
        server_hostnames = []
        if w.scope_type in ("servers", "custom") and w.server_ids:
            try:
                sids = [int(x.strip()) for x in w.server_ids.split(",") if x.strip().isdigit()]
                server_hostnames = [all_servers_map[sid] for sid in sids if sid in all_servers_map]
            except Exception:
                pass
        result.append(
            {
                "id": w.id,
                "title": w.title,
                "description": w.description,
                "scope_type": w.scope_type,
                "server_id": w.server_id,
                "server_ids": w.server_ids,
                "server_hostname": w.server.hostname if w.server else None,
                "server_hostnames": server_hostnames,
                "server_group": w.server_group,
                "schedule_type": w.schedule_type,
                "start_time": w.start_time.isoformat() if w.start_time else None,
                "end_time": w.end_time.isoformat() if w.end_time else None,
                "repeat_days": w.repeat_days,
                "repeat_time_start": w.repeat_time_start,
                "repeat_time_end": w.repeat_time_end,
                "is_active": w.is_active,
                "status": w.status,
                "created_by": w.created_by,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
        )

    return {
        "ok": True,
        "windows": result,
        "active_count": active_count,
        "upcoming_count": upcoming_count,
        "completed_count": completed_count,
    }


@router.post("/api/maintenance-windows")
async def api_maintenance_windows_create(
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Harap login terlebih dahulu")
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kelola server diperlukan")

    _verify_csrf_header(request)

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Format JSON tidak valid")

    title = str(body.get("title", "") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Judul jadwal pemeliharaan wajib diisi")
    if len(title) > 150:
        raise HTTPException(status_code=400, detail="Judul jadwal maksimal 150 karakter")

    description = str(body.get("description", "") or "").strip() or None
    scope_type = str(body.get("scope_type", "server") or "").strip()
    if scope_type not in ("all", "group", "server", "servers", "custom"):
        raise HTTPException(status_code=400, detail="Tipe cakupan tidak valid")

    server_id = None
    server_ids = None
    server_group = None
    if scope_type == "server":
        try:
            server_id = int(body.get("server_id"))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="Server target wajib dipilih")
        srv = db.query(Server).filter(Server.id == server_id).first()
        if not srv:
            raise HTTPException(status_code=404, detail="Server target tidak ditemukan")
    elif scope_type in ("servers", "custom"):
        raw_ids = body.get("server_ids") or []
        if isinstance(raw_ids, str):
            parsed_ids = [x.strip() for x in raw_ids.split(",") if x.strip().isdigit()]
        elif isinstance(raw_ids, list):
            parsed_ids = [str(int(x)) for x in raw_ids if str(x).isdigit()]
        else:
            parsed_ids = []
        if not parsed_ids:
            raise HTTPException(status_code=400, detail="Pilih minimal satu server target")
        server_ids = ",".join(parsed_ids)
    elif scope_type == "group":
        server_group = str(body.get("server_group", "") or "").strip()
        if not server_group:
            raise HTTPException(status_code=400, detail="Grup target wajib dipilih")

    schedule_type = str(body.get("schedule_type", "once") or "").strip()
    if schedule_type not in ("once", "daily", "weekly"):
        raise HTTPException(status_code=400, detail="Tipe jadwal tidak valid")

    start_time = _parse_iso_datetime(body.get("start_time"))
    end_time = _parse_iso_datetime(body.get("end_time"))

    repeat_days = None
    repeat_time_start = None
    repeat_time_end = None

    if schedule_type == "once":
        if not start_time or not end_time:
            raise HTTPException(status_code=400, detail="Waktu mulai dan selesai wajib diisi")
        if end_time <= start_time:
            raise HTTPException(status_code=400, detail="Waktu selesai harus lebih besar dari waktu mulai")
    else:
        repeat_time_start = str(body.get("repeat_time_start", "") or "").strip() or None
        repeat_time_end = str(body.get("repeat_time_end", "") or "").strip() or None
        if not repeat_time_start or not repeat_time_end:
            raise HTTPException(status_code=400, detail="Jam mulai dan jam selesai pengulangan wajib diisi (HH:MM)")
        if schedule_type == "weekly":
            repeat_days = str(body.get("repeat_days", "") or "").strip() or None
            if not repeat_days:
                raise HTTPException(status_code=400, detail="Hari pengulangan mingguan wajib dipilih")
        if not start_time:
            start_time = datetime.utcnow()
        if not end_time:
            end_time = datetime.utcnow() + timedelta(days=3650)

    now = datetime.utcnow()
    initial_status = "scheduled"
    if schedule_type == "once" and start_time <= now < end_time:
        initial_status = "active"

    mw = MaintenanceWindow(
        title=title,
        description=description,
        scope_type=scope_type,
        server_id=server_id,
        server_ids=server_ids,
        server_group=server_group,
        schedule_type=schedule_type,
        start_time=start_time,
        end_time=end_time,
        repeat_days=repeat_days,
        repeat_time_start=repeat_time_start,
        repeat_time_end=repeat_time_end,
        is_active=1,
        status=initial_status,
        created_by=user.username,
    )
    db.add(mw)
    db.commit()
    db.refresh(mw)

    _audit(
        db,
        user.username,
        "maintenance_create",
        target=mw.title,
        result=f"Jendela pemeliharaan dibuat (ID #{mw.id}, scope: {scope_type})",
        server_id=server_id,
    )

    _evaluate_maintenance_windows(db)

    return {
        "ok": True,
        "id": mw.id,
        "message": "Jendela pemeliharaan berhasil dijadwalkan",
    }


@router.post("/api/maintenance-windows/{wid}/cancel")
async def api_maintenance_windows_cancel(
    wid: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Harap login terlebih dahulu")
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kelola server diperlukan")

    _verify_csrf_header(request)

    mw = db.query(MaintenanceWindow).filter(MaintenanceWindow.id == wid).first()
    if not mw:
        raise HTTPException(status_code=404, detail="Jadwal pemeliharaan tidak ditemukan")

    mw.status = "cancelled"
    mw.is_active = 0
    _audit(
        db,
        user.username,
        "maintenance_cancel",
        target=mw.title,
        result=f"Jadwal pemeliharaan #{wid} dibatalkan",
        server_id=mw.server_id,
    )
    db.commit()

    _evaluate_maintenance_windows(db)

    return {
        "ok": True,
        "message": "Jadwal pemeliharaan berhasil dibatalkan",
    }


@router.post("/api/maintenance-windows/{wid}/complete")
async def api_maintenance_windows_complete(
    wid: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Harap login terlebih dahulu")
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kelola server diperlukan")

    _verify_csrf_header(request)

    mw = db.query(MaintenanceWindow).filter(MaintenanceWindow.id == wid).first()
    if not mw:
        raise HTTPException(status_code=404, detail="Jadwal pemeliharaan tidak ditemukan")

    mw.status = "completed"
    mw.is_active = 0
    mw.end_time = datetime.utcnow()
    _audit(
        db,
        user.username,
        "maintenance_complete",
        target=mw.title,
        result=f"Jadwal pemeliharaan #{wid} ditandai selesai lebih awal",
        server_id=mw.server_id,
    )
    db.commit()

    _evaluate_maintenance_windows(db)

    return {
        "ok": True,
        "message": "Jendela pemeliharaan selesai lebih awal, server dipulihkan",
    }


@router.delete("/api/maintenance-windows/{wid}")
async def api_maintenance_windows_delete(
    wid: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Harap login terlebih dahulu")
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kelola server diperlukan")

    _verify_csrf_header(request)

    mw = db.query(MaintenanceWindow).filter(MaintenanceWindow.id == wid).first()
    if not mw:
        raise HTTPException(status_code=404, detail="Jadwal pemeliharaan tidak ditemukan")

    title = mw.title
    server_id = mw.server_id
    db.delete(mw)
    _audit(
        db,
        user.username,
        "maintenance_delete",
        target=title,
        result=f"Jadwal pemeliharaan #{wid} dihapus permanen",
        server_id=server_id,
    )
    db.commit()

    _evaluate_maintenance_windows(db)

    return {
        "ok": True,
        "message": "Jadwal pemeliharaan berhasil dihapus",
    }
