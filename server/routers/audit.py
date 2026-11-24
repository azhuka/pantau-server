"""Router Audit Log & Jejak Aktivitas Operasional Pantau Server."""

from datetime import datetime, timedelta
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from core.database import get_db
from routers.auth import get_current_user
from models.user import User
from models.server import Server
from models.misc import AuditLog

logger = logging.getLogger("pantau.audit")

router = APIRouter(tags=["Audit & Logs"])


@router.get("/api/audit")
def api_get_audit_logs(
    q: str = Query("", description="Kata kunci pencarian"),
    action: str = Query("", description="Filter aksi"),
    user: str = Query("", description="Filter username"),
    period: str = Query("all", description="Filter periode: 24h, today, 7d, 30d, all"),
    server_id: Optional[int] = Query(None, description="Filter ID Server"),
    status: str = Query("", description="Filter status: success, failed"),
    limit: int = Query(50, ge=1, le=500, description="Jumlah baris data"),
    user_actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mengambil jejak audit operasional NOC."""
    if not (user_actor.is_master_admin or user_actor.has_perm("can_audit")):
        raise HTTPException(status_code=403, detail="Akses ditolak: Izin audit trail diperlukan.")

    now_utc = datetime.utcnow()
    cutoff = None
    if period == "24h":
        cutoff = now_utc - timedelta(hours=24)
    elif period == "today":
        cutoff = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "7d":
        cutoff = now_utc - timedelta(days=7)
    elif period == "30d":
        cutoff = now_utc - timedelta(days=30)

    query = db.query(AuditLog)
    if cutoff:
        query = query.filter(AuditLog.created_at >= cutoff)

    # Scoping server untuk operator terbatas
    allowed_sids = user_actor.get_allowed_server_ids()
    if allowed_sids is not None:
        if server_id is not None:
            if server_id not in allowed_sids:
                return []
            query = query.filter(AuditLog.server_id == server_id)
        else:
            query = query.filter(AuditLog.server_id.in_(allowed_sids))
    elif server_id is not None:
        query = query.filter(AuditLog.server_id == server_id)

    if user.strip():
        query = query.filter(AuditLog.username == user.strip())

    if action.strip():
        query = query.filter(AuditLog.action == action.strip())

    if status.strip().upper() == "SUCCESS":
        query = query.filter(~AuditLog.result.ilike("%gagal%"), ~AuditLog.result.ilike("%fail%"), ~AuditLog.result.ilike("%error%"))
    elif status.strip().upper() == "FAILED":
        query = query.filter(
            (AuditLog.result.ilike("%gagal%")) | (AuditLog.result.ilike("%fail%")) | (AuditLog.result.ilike("%error%"))
        )

    if q.strip():
        search_kw = f"%{q.strip()}%"
        query = query.filter(
            (AuditLog.username.ilike(search_kw))
            | (AuditLog.action.ilike(search_kw))
            | (AuditLog.target.ilike(search_kw))
            | (AuditLog.result.ilike(search_kw))
        )

    records = query.order_by(desc(AuditLog.created_at)).limit(limit).all()

    # Map server hostnames
    server_map = {s.id: s.hostname for s in db.query(Server).all()}

    results = []
    for r in records:
        srv_name = server_map.get(r.server_id) or ("Host Pusat" if not r.server_id else f"#{r.server_id}")
        results.append({
            "id": r.id,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "-",
            "username": r.username,
            "server_id": r.server_id,
            "server_name": srv_name,
            "action": r.action,
            "target": r.target or "-",
            "result": r.result or "SUCCESS",
            "meta": r.meta,
        })

    return results
