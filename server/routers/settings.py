"""
Router Pengaturan Sistem & Master Control Center Pantau Server.
Menyediakan portal manajemen Master Control untuk Master Administrator:
inspeksi dan optimasi basis data MySQL (reclaim fragmented storage, ukuran tabel),
telemetri sumber daya host pusat, ambang batas insiden global (thresholds),
serta tata kelola sistem berkepadatan tinggi.
"""

from datetime import datetime
import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from core.database import get_db
from core.security import (
    get_current_user,
    require_user,
    require_master_admin,
    _verify_csrf_header,
)
from core.templates import tpl
from models import (
    AppSession,
    Server,
    SystemSetting,
    User,
)
from services.audit_service import _audit
from services.problem_service import (
    DEFAULT_THRESHOLDS,
    get_global_thresholds,
    _RETENTION_LIMITS,
)
from services.system_service import (
    _proc_uptime,
    _proc_cpu,
    _proc_memory,
    _proc_disks,
    get_database_status,
)

logger = logging.getLogger("pantau.settings")

router = APIRouter(tags=["Settings & Master Control"])


# ---------------------------------------------------------------------------
# GLOBAL THRESHOLDS API
# ---------------------------------------------------------------------------
@router.post("/api/settings/thresholds")
def api_update_thresholds(
    request: Request,
    body: dict = Body(default={}),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Perbarui ambang batas masalah global."""
    _verify_csrf_header(request)
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    new_th = {}
    float_keys = [
        "cpu_warn",
        "cpu_danger",
        "ram_warn",
        "ram_danger",
        "disk_warn",
        "disk_danger",
        "swap_warn",
        "swap_danger",
    ]
    int_keys = ["ssh_fail_warn", "ssh_fail_danger"]

    for k in float_keys:
        if k in body and body[k] is not None:
            try:
                val = float(body[k])
                if 1.0 <= val <= 100.0:
                    new_th[k] = val
            except (ValueError, TypeError):
                pass

    for k in int_keys:
        if k in body and body[k] is not None:
            try:
                val = int(body[k])
                if val >= 1:
                    new_th[k] = val
            except (ValueError, TypeError):
                pass

    pairs = [
        ("cpu_warn", "cpu_danger"),
        ("ram_warn", "ram_danger"),
        ("disk_warn", "disk_danger"),
        ("swap_warn", "swap_danger"),
        ("ssh_fail_warn", "ssh_fail_danger"),
    ]
    for w_k, d_k in pairs:
        w_val = new_th.get(w_k, DEFAULT_THRESHOLDS[w_k])
        d_val = new_th.get(d_k, DEFAULT_THRESHOLDS[d_k])
        if w_val > d_val:
            raise HTTPException(
                status_code=400,
                detail=f"Nilai Warning ({w_k}) tidak boleh lebih besar dari Danger ({d_k})",
            )

    current_th = get_global_thresholds(db)
    current_th.update(new_th)

    row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
    if not row:
        row = SystemSetting(key="thresholds", value=json.dumps(current_th), updated_at=datetime.utcnow())
        db.add(row)
    else:
        row.value = json.dumps(current_th)
        row.updated_at = datetime.utcnow()

    _audit(
        db,
        user.username,
        "settings_update",
        target="Ambang Batas Insiden Global",
        result="disimpan",
    )
    db.commit()
    return {"ok": True, "thresholds": current_th}


@router.post("/api/settings/thresholds/reset")
def api_reset_thresholds(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Reset ambang batas masalah global ke bawaan pabrik."""
    _verify_csrf_header(request)
    if not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
    if row:
        db.delete(row)
        _audit(
            db,
            user.username,
            "settings_reset",
            target="Ambang Batas Insiden Global",
            result="direset ke bawaan pabrik",
        )
        db.commit()

    return {"ok": True, "thresholds": dict(DEFAULT_THRESHOLDS)}


# ---------------------------------------------------------------------------
# MASTER CONTROL CENTER (PORTAL MASTER ADMIN)
# ---------------------------------------------------------------------------
@router.get("/master-control", response_class=HTMLResponse)
def master_control_page(request: Request, db: Session = Depends(get_db)):
    """Pusat Kendali Master (Master Control Center) untuk Master Administrator."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not user.is_master_admin():
        return RedirectResponse("/", status_code=303)

    db_status = get_database_status(db)
    servers_count = db.query(Server).count()
    users_count = db.query(User).count()
    active_sessions = db.query(AppSession).filter(AppSession.expires_at > datetime.utcnow()).count()

    host_mem = _proc_memory()
    host_disks = _proc_disks()
    global_th = get_global_thresholds(db)

    return tpl(
        request,
        "master_control.html",
        {
            "user": user,
            "db_status": db_status,
            "servers_count": servers_count,
            "users_count": users_count,
            "active_sessions": active_sessions,
            "host_mem": host_mem,
            "host_disks": host_disks,
            "global_thresholds": global_th,
            "default_thresholds": DEFAULT_THRESHOLDS,
            "retention_limits": _RETENTION_LIMITS,
            "app_version": settings.APP_VERSION,
        },
    )


@router.get("/api/master-control/status")
@router.get("/api/master-control/metrics")
def api_master_control_status(
    user: User = Depends(require_master_admin),
    db: Session = Depends(get_db),
):
    """Telemetri real-time status basis data dan server pusat untuk Master Control."""
    db_status = get_database_status(db)
    servers_count = db.query(Server).count()
    users_count = db.query(User).count()
    active_sessions = db.query(AppSession).filter(AppSession.expires_at > datetime.utcnow()).count()

    mem_data = _proc_memory()
    return {
        "ok": True,
        "database": db_status,
        "db_stats": db_status,
        "servers_count": servers_count,
        "users_count": users_count,
        "active_sessions": active_sessions,
        "cpu": _proc_cpu(),
        "memory": mem_data,
        "mem": mem_data,
        "disks": _proc_disks(),
        "uptime": _proc_uptime(),
    }


@router.post("/api/master-control/optimize-db")
def api_master_control_optimize_db(
    request: Request,
    user: User = Depends(require_master_admin),
    db: Session = Depends(get_db),
):
    """Jalankan perintah SQL OPTIMIZE TABLE untuk defragmentasi dan reklamasi ruang disk."""
    _verify_csrf_header(request)
    tables_to_optimize = [
        "metrics",
        "system_snapshots",
        "sys_snapshots_hourly",
        "audit_logs",
        "commands",
        "server_problems",
        "probe_checks",
    ]
    results = []
    try:
        for tbl_name in tables_to_optimize:
            try:
                res = db.execute(text(f"OPTIMIZE TABLE `{tbl_name}`")).fetchall()
                results.append({"table": tbl_name, "status": "optimized"})
            except Exception as e:
                results.append({"table": tbl_name, "status": f"error: {e}"})

        _audit(
            db,
            user.username,
            "db_optimize",
            target="Basis Data MySQL",
            result=f"Optimasi {len(tables_to_optimize)} tabel selesai",
        )
        db.commit()
        return {"ok": True, "message": "Optimasi tabel basis data berhasil dijalankan", "details": results}
    except Exception as exc:
        logger.error("[Master Control] Optimasi basis data gagal: %s", exc)
        raise HTTPException(status_code=500, detail=f"Gagal mengoptimasi basis data: {exc}")
