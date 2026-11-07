"""Pantau Server - Core Application Entrypoint.

Enterprise-Grade, Domain-Driven NOC Server Monitoring & Remote Orchestration.
FastAPI Application Factory, Router Mounting, Background Loops & Lifespan Management.
"""

from contextlib import asynccontextmanager
import json
import logging
import os
from pathlib import Path
import threading
from typing import Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from config import settings
    from core.database import engine, SessionLocal, Base
    from core.security import _prune_expired_sessions, get_current_user, SESSION_COOKIE, _csrf_token
    from core.templates import render_template
    from prober import ProbeScheduler
    from services.migration_service import run_all_migrations
    from services.problem_service import _problem_bg_loop, _retention_loop, BG_PROBLEM_EVAL_SECS
    from routers import (
        api_agent,
        audit,
        auth,
        dashboard,
        files,
        maintenance,
        probes,
        servers,
        services,
        settings as settings_router,
        system_ops,
        terminal,
        users,
    )
except ImportError:
    from server.config import settings
    from server.core.database import engine, SessionLocal, Base
    from server.core.security import _prune_expired_sessions, get_current_user, SESSION_COOKIE, _csrf_token
    from server.core.templates import render_template
    from server.prober import ProbeScheduler
    from server.services.migration_service import run_all_migrations
    from server.services.problem_service import _problem_bg_loop, _retention_loop, BG_PROBLEM_EVAL_SECS
    from server.routers import (
        api_agent,
        audit,
        auth,
        dashboard,
        files,
        maintenance,
        probes,
        servers,
        services,
        settings as settings_router,
        system_ops,
        terminal,
        users,
    )

# Konfigurasi Logging Standar
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pantau")

_probe_scheduler: Optional[ProbeScheduler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Siklus hidup aplikasi: inisialisasi basis data, migrasi, dan pekerja latar belakang."""
    global _probe_scheduler
    logger.info("[startup] Menginisialisasi basis data dan menjalankan migrasi skema...")
    Base.metadata.create_all(bind=engine)
    run_all_migrations()

    try:
        with SessionLocal() as sess:
            _prune_expired_sessions(sess)
            sess.commit()
    except Exception as exc:
        logger.warning("[startup] Pemangkasan sesi kadaluarsa gagal: %s", exc)

    if not os.environ.get("PANTAU_BG_DISABLED"):
        threading.Thread(target=_problem_bg_loop, name="bg-problems", daemon=True).start()
        threading.Thread(target=_retention_loop, name="retention", daemon=True).start()
        logger.info("[bg-problems] Evaluator latar belakang aktif (tiap %ds)", BG_PROBLEM_EVAL_SECS)

        _probe_scheduler = ProbeScheduler(SessionLocal)
        _probe_scheduler.start()

    logger.info("[startup] Pantau Server siap melayani permintaan")
    yield
    if _probe_scheduler:
        _probe_scheduler.stop()
    logger.info("[shutdown] Pantau Server dihentikan")


app = FastAPI(
    title="Pantau Server",
    description="Sistem Pemantauan NOC Mandiri & Kendali Server Jarak Jauh",
    version=getattr(settings, "APP_VERSION", "4.8.120"),
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)

# Mounting Berkas Statis
static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/favicon.ico", include_in_schema=False)
def favicon_route():
    return Response(status_code=204)


# Middleware Header Keamanan
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
if getattr(settings, "SESSION_COOKIE_SECURE", False):
    _SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        if k not in resp.headers:
            resp.headers[k] = v
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"

    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        expected_csrf = _csrf_token(sid)
        if expected_csrf and request.cookies.get("pantau_csrf_token") != expected_csrf:
            resp.set_cookie(
                "pantau_csrf_token",
                expected_csrf,
                httponly=False,
                samesite="lax",
                secure=getattr(settings, "SESSION_COOKIE_SECURE", False),
                path="/",
            )
    return resp


# Penanganan Kendala (Exception Handlers)
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        db = SessionLocal()
        user = None
        try:
            user = get_current_user(request, db)
        except Exception:
            pass
        finally:
            db.close()

        status_code = exc.status_code
        if status_code == 404:
            title = "Halaman Tidak Ditemukan"
            msg = "Halaman atau tautan yang Anda tuju tidak ditemukan atau sudah dipindahkan."
        elif status_code == 403:
            title = "Akses Dibatasi"
            msg = str(exc.detail) if exc.detail else "Anda tidak memiliki wewenang untuk mengakses halaman ini."
        else:
            title = f"Kendala Permintaan ({status_code})"
            msg = str(exc.detail) if exc.detail else "Permintaan tidak dapat diproses."

        return render_template(
            request,
            "error.html",
            {
                "status_code": status_code,
                "title": title,
                "message": msg,
                "user": user,
            },
            status_code=status_code,
        )

    return Response(
        content=json.dumps({"detail": exc.detail}),
        status_code=exc.status_code,
        media_type="application/json",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("[unhandled_exception] Kendala pada %s %s: %s", request.method, request.url.path, exc)
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        db = SessionLocal()
        user = None
        try:
            user = get_current_user(request, db)
        except Exception:
            pass
        finally:
            db.close()

        title = "Terjadi Kendala Sesaat (500)"
        msg = (
            "Aplikasi Pantau Server mendeteksi kendala internal saat memproses halaman ini. "
            "Data server Anda tetap aman. Silakan muat ulang halaman atau kembali ke Dashboard."
        )
        detail_info = str(exc) if (user and (getattr(user, "is_master_admin", lambda: False)() or getattr(user, "is_operator", lambda: False)())) else None

        return render_template(
            request,
            "error.html",
            {
                "status_code": 500,
                "title": title,
                "message": msg,
                "detail_info": detail_info,
                "user": user,
            },
            status_code=500,
        )

    return Response(
        content=json.dumps({"detail": "Internal Server Error"}),
        status_code=500,
        media_type="application/json",
    )


# Registrasi Router Berdasarkan Domain
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(servers.router)
app.include_router(services.router)
app.include_router(terminal.router)
app.include_router(files.router)
app.include_router(probes.router)
app.include_router(maintenance.router)
app.include_router(audit.router)
app.include_router(system_ops.router)
app.include_router(users.router)
app.include_router(settings_router.router)
app.include_router(api_agent.router)
