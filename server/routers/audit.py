"""Router Audit Log & Jejak Aktivitas Operasional Pantau Server."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.database import get_db
from models.user import User
from routers.auth import get_current_user
from services.audit_service import get_audit_metadata, query_audit_entries

router = APIRouter(tags=["Audit & Logs"])


@router.get("/api/audit/meta")
def api_get_audit_meta(
    user_actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Metadata dropdown filter Audit Trail (Users, Assets, Action Categories)."""
    if not (user_actor.is_master_admin or user_actor.has_perm("can_audit")):
        raise HTTPException(status_code=403, detail="Access denied: can_audit permission required.")
    return get_audit_metadata(db, user_actor)


@router.get("/api/audit")
def api_get_audit_logs(
    q: str = Query("", description="Search keyword"),
    action: str = Query("", description="Action key or cat:* category filter"),
    user: str = Query("", description="Operator username filter"),
    period: str = Query("24h", description="Timeframe preset: 24h, today, 7d, 30d, all, custom"),
    start_date: str = Query("", description="Custom start date YYYY-MM-DD"),
    end_date: str = Query("", description="Custom end date YYYY-MM-DD"),
    server_id: Optional[int] = Query(None, description="Target Server ID"),
    status: str = Query("", description="Execution status: SUCCESS, FAILED, PENDING"),
    limit: int = Query(200, ge=1, le=500, description="Max rows returned"),
    user_actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Fetch chronological audit trail with multi-criteria filtering."""
    if not (user_actor.is_master_admin or user_actor.has_perm("can_audit")):
        raise HTTPException(status_code=403, detail="Access denied: can_audit permission required.")

    return query_audit_entries(
        db=db,
        user_actor=user_actor,
        q=q,
        action=action,
        user_filter=user,
        period=period,
        start_date=start_date,
        end_date=end_date,
        server_id=server_id,
        status_filter=status,
        limit=limit,
    )
