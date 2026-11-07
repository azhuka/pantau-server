"""Jinja2 Templates engine, globals, branding injection, and HTML response helper."""

import json
from pathlib import Path
import time
from typing import Optional
from fastapi import Request
from fastapi.responses import HTMLResponse, FileResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

try:
    from config import settings
    from models import SystemSetting
    from core.database import SessionLocal
    from core.security import _csrf_token, SESSION_COOKIE
    from core.utils import _fmt_dt, _fmt_short_dt, _rel_dt
    from services.maintenance_service import get_active_maintenance_info
except ImportError:
    from server.config import settings
    from server.models import SystemSetting
    from server.core.database import SessionLocal
    from server.core.security import _csrf_token, SESSION_COOKIE
    from server.core.utils import _fmt_dt, _fmt_short_dt, _rel_dt
    from server.services.maintenance_service import get_active_maintenance_info

templates = Jinja2Templates(directory=settings.templates_dir)

# Template Globals
templates.env.globals["_fmt_dt"] = _fmt_dt
templates.env.globals["_fmt_short_dt"] = _fmt_short_dt
templates.env.globals["_rel_dt"] = _rel_dt
templates.env.globals["getattr"] = getattr
templates.env.globals["bool"] = bool

# ---------------------------------------------------------------------------
# Pengaturan Identitas & Pengumuman Organisasi (Branding & MOTD)
# ---------------------------------------------------------------------------
_BRANDING_CACHE = {
    "data": None,
    "expires_at": 0.0,
}


def get_branding_settings(db: Optional[Session] = None) -> dict:
    """Ambil pengaturan identitas organisasi dan pesan operasional (branding & MOTD)."""
    now = time.time()
    if _BRANDING_CACHE["data"] is not None and now < _BRANDING_CACHE["expires_at"] and db is None:
        return dict(_BRANDING_CACHE["data"])

    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    defaults = {
        "org_name": "",
        "org_unit": "",
        "dash_motd": "",
        "show_motd": True,
        "logo_url": "",
    }
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == "branding").first()
        if row and row.value:
            data = json.loads(row.value)
            defaults["org_name"] = str(data.get("org_name", "") or "").strip()
            defaults["org_unit"] = str(data.get("org_unit", "") or "").strip()
            defaults["dash_motd"] = str(data.get("dash_motd", "") or "").strip()
            defaults["show_motd"] = bool(data.get("show_motd", True))
            defaults["logo_url"] = str(data.get("logo_url", "") or "").strip()
        _BRANDING_CACHE["data"] = dict(defaults)
        _BRANDING_CACHE["expires_at"] = now + 15.0  # cache 15 detik
        return defaults
    except Exception:
        if not close_db:
            try:
                db.rollback()
            except Exception:
                pass
        return defaults
    finally:
        if close_db:
            db.close()


def invalidate_branding_cache() -> None:
    _BRANDING_CACHE["data"] = None
    _BRANDING_CACHE["expires_at"] = 0.0


def tpl(request: Request, name: str, context: Optional[dict] = None, status_code: int = 200) -> HTMLResponse:
    """Render template dengan CSRF token, versi aplikasi, dan branding otomatis."""
    ctx = dict(context) if context else {}
    sid = request.cookies.get(SESSION_COOKIE, "")
    ctx.setdefault("csrf_token", _csrf_token(sid) if sid else "")
    ctx.setdefault("app_version", settings.APP_VERSION)
    ctx.setdefault("brand", get_branding_settings())
    active_m_count, active_m_titles = get_active_maintenance_info()
    ctx.setdefault("active_maintenance_count", active_m_count)
    ctx.setdefault("active_maintenance_titles", active_m_titles)
    resp = templates.TemplateResponse(request, name, ctx, status_code=status_code)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


render_template = tpl


_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "SAMEORIGIN",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; img-src 'self' data:; "
        "font-src 'self' https://fonts.gstatic.com data:; connect-src 'self' ws: wss:; form-action 'self'; "
        "base-uri 'self'; frame-ancestors 'self'; object-src 'none'"
    ),
}
if settings.SESSION_COOKIE_SECURE:
    _SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
