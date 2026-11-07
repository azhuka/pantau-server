"""Audit logs and application dashboard logs router."""

import os
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

try:
    from config import settings
    from models import Server, User
    from core.database import get_db
    from core.security import get_current_user, require_user
    from core.templates import tpl
    from services.audit_service import (
        AUDIT_ACTION_LABELS,
        AUDIT_CATEGORIES,
        _audit_rows,
        tail_lines,
    )
except ImportError:
    from server.config import settings
    from server.models import Server, User
    from server.core.database import get_db
    from server.core.security import get_current_user, require_user
    from server.core.templates import tpl
    from server.services.audit_service import (
        AUDIT_ACTION_LABELS,
        AUDIT_CATEGORIES,
        _audit_rows,
        tail_lines,
    )

router = APIRouter(tags=["Audit & Logs"])


@router.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return tpl(request, "logs.html", {"user": user, "log_file": settings.LOG_FILE})


@router.get("/api/logs/dashboard")
def api_logs_dashboard(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    lines: int = 300,
):
    lines = max(10, min(lines, 2000))
    path = settings.LOG_FILE
    last_lines = tail_lines(path, lines)
    return {
        "path": path,
        "exists": os.path.exists(path),
        "count": min(lines, len(last_lines)),
        "lines": last_lines,
    }


@router.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    action: str = "",
    user: str = "",
    period: str = "",
    server: str = "",
    status: str = "",
    start_date: str = "",
    end_date: str = "",
):
    user_actor = get_current_user(request, db)
    if not user_actor:
        return RedirectResponse("/login", status_code=303)
    if not (user_actor.is_master_admin() or user_actor.has_perm("can_audit")):
        return RedirectResponse("/", status_code=303)

    user_clean = user.strip()
    period_clean = period.strip().lower()
    server_id = int(server.strip()) if server.strip().isdigit() else None
    status_clean = status.strip().upper()
    start_date_clean = start_date.strip()
    end_date_clean = end_date.strip()

    rows = _audit_rows(
        db,
        limit=500,
        q=q,
        action=action,
        user_filter=user_clean,
        period=period_clean,
        server_id=server_id,
        status_filter=status_clean,
        start_date=start_date_clean,
        end_date=end_date_clean,
    )
    if not user_actor.is_master_admin():
        master_admin_names = {u.username for u in db.query(User).filter(User.role == "master_admin").all()}
        for r in rows:
            if r.get("user") in master_admin_names:
                r["user"] = "Sistem"
            target_str = str(r.get("target") or "")
            for m in master_admin_names:
                if m in target_str:
                    target_str = target_str.replace(m, "Sistem")
            if "master_admin" in target_str:
                target_str = target_str.replace("master_admin", "sistem")
            r["target"] = target_str

        if user_clean in master_admin_names:
            rows = []

        available_users = [
            u.username
            for u in db.query(User).filter(~User.role.in_(["master_admin", "admin"])).order_by(User.username).all()
        ]
    else:
        available_users = [u.username for u in db.query(User).order_by(User.username).all()]

    if user_clean and user_clean not in available_users and (
        user_actor.is_master_admin() or user_clean not in master_admin_names
    ):
        available_users.append(user_clean)
        available_users.sort()

    all_servers = db.query(Server).order_by(Server.hostname).all()

    st_cls = {
        "SUCCESS": "up",
        "FAILED": "danger",
        "PENDING": "muted",
        "EXECUTING": "warn",
    }
    st_label = {
        "SUCCESS": "BERHASIL",
        "FAILED": "GAGAL",
        "PENDING": "MENUNGGU",
        "EXECUTING": "PROSES",
    }

    return tpl(
        request,
        "audit.html",
        {
            "user": user_actor,
            "rows": rows,
            "q": q,
            "action": action,
            "period": period_clean,
            "selected_user": user_clean,
            "selected_server": server_id,
            "selected_status": status_clean,
            "start_date": start_date_clean,
            "end_date": end_date_clean,
            "all_servers": all_servers,
            "available_users": available_users,
            "categories": AUDIT_CATEGORIES,
            "actions": sorted(AUDIT_ACTION_LABELS.items()),
            "st_cls": st_cls,
            "st_label": st_label,
        },
    )
