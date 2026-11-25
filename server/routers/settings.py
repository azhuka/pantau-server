"""Router Pengaturan Sistem & Master Control Center Pantau Server.
Menyediakan portal manajemen Master Control untuk Master Administrator:
inspeksi dan optimasi database MySQL (reclaim fragmented storage, ukuran tabel),
telemetri resource host pusat, threshold insiden global (thresholds),
serta manajemen sistem berdensitas tinggi.
"""

from datetime import datetime
import json
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from core.database import get_db
from routers.auth import get_current_user
from models.user import User
from models.server import Server
from models.misc import SystemSetting, AuditLog
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


def record_audit(
    db: Session,
    username: str,
    action: str,
    target: str = None,
    result: str = None,
    server_id: int = None,
) -> None:
    try:
        log = AuditLog(
            username=username,
            action=action,
            target=target,
            result=result,
            server_id=server_id,
        )
        db.add(log)
    except Exception as e:
        logger.warning("Failed to record audit log: %s", e)


# ---------------------------------------------------------------------------
# GLOBAL THRESHOLDS API
# ---------------------------------------------------------------------------
@router.get("/api/settings/thresholds")
def api_get_thresholds(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ambil threshold insiden global saat ini."""
    return {
        "ok": True,
        "thresholds": get_global_thresholds(db),
        "defaults": DEFAULT_THRESHOLDS,
    }


def validate_and_save_thresholds(db: Session, body: dict, actor_username: str) -> dict:
    """Validate threshold ordering/bounds and persist atomically to SystemSetting."""
    new_th = {}
    float_keys = [
        "cpu_warn", "cpu_average", "cpu_danger",
        "ram_warn", "ram_average", "ram_danger",
        "disk_warn", "disk_average", "disk_danger",
        "swap_warn", "swap_average", "swap_danger",
    ]
    int_keys = ["ssh_fail_warn", "ssh_fail_danger"]

    for k in float_keys:
        if k in body and body[k] is not None:
            try:
                val = float(body[k])
                if not (1.0 <= val <= 100.0):
                    raise HTTPException(status_code=400, detail=f"Threshold {k} must be between 1 and 100.")
                new_th[k] = val
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail=f"Invalid numeric value for threshold {k}.")

    for k in int_keys:
        if k in body and body[k] is not None:
            try:
                val = int(body[k])
                if val < 1:
                    raise HTTPException(status_code=400, detail=f"Threshold {k} must be at least 1.")
                new_th[k] = val
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail=f"Invalid integer value for threshold {k}.")

    current_th = get_global_thresholds(db)
    merged = dict(current_th)
    merged.update(new_th)

    trios = [
        ("cpu_warn", "cpu_average", "cpu_danger", "CPU Load"),
        ("ram_warn", "ram_average", "ram_danger", "Memory / RAM Usage"),
        ("disk_warn", "disk_average", "disk_danger", "Disk Usage"),
        ("swap_warn", "swap_average", "swap_danger", "Swap Usage"),
    ]
    for w_k, a_k, d_k, lbl in trios:
        w_val, a_val, d_val = merged[w_k], merged[a_k], merged[d_k]
        if not (w_val <= a_val <= d_val):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid threshold ordering for {lbl}: Warning ({w_val:.0f}%) <= Critical ({a_val:.0f}%) <= Danger ({d_val:.0f}%).",
            )
    if merged["ssh_fail_warn"] > merged["ssh_fail_danger"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid SSH failure threshold ordering: Warning ({merged['ssh_fail_warn']}) <= Danger ({merged['ssh_fail_danger']}).",
        )

    row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
    if not row:
        row = SystemSetting(key="thresholds", value=json.dumps(merged), updated_at=datetime.utcnow())
        db.add(row)
    else:
        row.value = json.dumps(merged)
        row.updated_at = datetime.utcnow()

    record_audit(
        db,
        actor_username,
        "settings_update",
        target="Global Incident Thresholds",
        result="success",
    )
    db.commit()
    return merged


@router.post("/api/settings/thresholds")
def api_update_thresholds(
    request: Request,
    body: dict = Body(default={}),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update global incident alert thresholds."""
    if not (user.is_master_admin or (user.allowed_server_ids is None and user.has_perm("can_manage_servers"))):
        raise HTTPException(
            status_code=403,
            detail="Access denied: Master Admin or Global Operator permission is required to modify global thresholds.",
        )
    merged = validate_and_save_thresholds(db, body, user.username)
    return {"ok": True, "thresholds": merged}


@router.post("/api/settings/thresholds/reset")
def api_reset_thresholds(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset global incident thresholds to factory defaults."""
    if not (user.is_master_admin or (user.allowed_server_ids is None and user.has_perm("can_manage_servers"))):
        raise HTTPException(
            status_code=403,
            detail="Access denied: Master Admin or Global Operator permission is required to reset global thresholds.",
        )

    row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
    if row:
        db.delete(row)
        record_audit(
            db,
            user.username,
            "settings_reset",
            target="Global Incident Thresholds",
            result="success",
        )
        db.commit()

    return {"ok": True, "thresholds": dict(DEFAULT_THRESHOLDS)}


# ---------------------------------------------------------------------------
# MASTER CONTROL CENTER API
# ---------------------------------------------------------------------------
@router.get("/api/master-control/status")
def api_master_control_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Real-time database and control host telemetry for Master Control."""
    if not user.is_master_admin:
        raise HTTPException(status_code=403, detail="Access denied: Master Admin only.")
    db_status = get_database_status(db)
    servers_count = db.query(Server).count()
    users_count = db.query(User).count()

    mem_data = _proc_memory()
    return {
        "ok": True,
        "database": db_status,
        "servers_count": servers_count,
        "users_count": users_count,
        "cpu": _proc_cpu(),
        "memory": mem_data,
        "disks": _proc_disks(),
        "uptime": _proc_uptime(),
        "retention_limits": _RETENTION_LIMITS,
    }


@router.post("/api/master-control/optimize-db")
def api_master_control_optimize_db(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Jalankan perintah SQL OPTIMIZE TABLE untuk defragmentasi dan reklamasi ruang disk."""
    if not user.is_master_admin:
        raise HTTPException(status_code=403, detail="Access denied: Master Admin only.")
    tables_to_optimize = [
        "metrics",
        "system_snapshots",
        "sys_snapshots_hourly",
        "audit_logs",
        "commands",
        "server_problems",
        "servers",
        "users",
    ]
    results = []
    try:
        for tbl_name in tables_to_optimize:
            try:
                db.execute(text(f"OPTIMIZE TABLE `{tbl_name}`"))
                results.append({"table": tbl_name, "status": "optimized"})
            except Exception as e:
                results.append({"table": tbl_name, "status": f"skipped: {e}"})

        record_audit(
            db,
            user.username,
            "db_optimize",
            target="MySQL Database (pantau_db)",
            result="success",
        )
        db.commit()
        return {"ok": True, "message": "Database table optimization completed successfully", "details": results}
    except Exception as exc:
        db.rollback()
        logger.error("[Master Control] Database optimization failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Database optimization failed: {exc}")
