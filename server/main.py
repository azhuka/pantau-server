"""
Server Monitoring Central - FastAPI Backend
============================================
Full-featured web app for server monitoring.
"""

import asyncio
import base64
import hashlib
import hmac as _hmac
import ipaddress
import json
import logging
import os
import re
import secrets
import socket
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import (
    Body, Depends, FastAPI, File, Form, Header, HTTPException, Request, Response,
    UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import create_engine, desc, func, text
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
from models import (
    AppSession, AuditLog, Base, Command, LogRequest, LoginAttempt, Metric,
    Server, ServerExtras, ServerProblem, Service, SysSnapshotHour,
    SystemSnapshot, User,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("pantau")

# Secret key (resolusi saat startup)
_SECRET_KEY: str = ""  # diisi saat startup

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
engine = create_engine(
    settings.database_url,
    pool_size=settings.POOL_SIZE, max_overflow=settings.POOL_MAX_OVERFLOW,
    pool_recycle=settings.POOL_RECYCLE, pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Auth helpers (sesi persisten di DB — tahan restart server)
# ---------------------------------------------------------------------------
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_COOKIE = "session_id"
SESSION_TTL = timedelta(hours=12)

_last_metrics_prune = datetime.utcnow() - timedelta(days=1)
_prune_lock = threading.Lock()


def _prune_expired_sessions(db: Session) -> None:
    """Hapus sesi kedaluwarsa (dipanggil ringan saat login/startup/maintanen)."""
    db.query(AppSession).filter(AppSession.expires_at < datetime.utcnow()).delete(
        synchronize_session=False)


def create_session(db: Session, user_id: int, ip: str, user_agent: str | None = None) -> str:
    sid = secrets.token_hex(32)
    db.add(AppSession(
        sid=sid, user_id=user_id, ip_address=_clean_str(ip, None, 45),
        user_agent=_clean_str(user_agent, None, 255),
        expires_at=datetime.utcnow() + SESSION_TTL,
    ))
    return sid


def get_current_user(request: Request, db: Session) -> User | None:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    row = db.query(AppSession).filter(AppSession.sid == sid).first()
    if not row:
        return None
    if datetime.utcnow() > row.expires_at:
        # Jangan commit di jalur baca berulang; buang sekali lalu abaikan.
        db.delete(row)
        db.commit()
        return None
    return db.query(User).filter(User.id == row.user_id).first()


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency API JSON: wajib sesi login aktif."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency FastAPI: wajib login sebagai admin. Raise 401/403 jika tidak berhak."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya admin")
    return user


def _audit(db, username: str, action: str, target=None, result=None, meta=None):
    """Catat jejak aksi admin pada tabel audit_logs (dicommit oleh pemanggil)."""
    db.add(AuditLog(
        username=_clean_str(username, "-", 100),
        action=_clean_str(action, "", 50),
        target=_clean_str(target, None, 255),
        result=_clean_str(result, None, 500),
        meta=json.dumps(meta) if meta else None,
    ))




# ---------------------------------------------------------------------------
# Sanitasi input
# ---------------------------------------------------------------------------
def _clean_str(value, default="", length: int = 100) -> str:
    """Normalisasi string: wajib str, whitespace dirapikan, potong panjang."""
    if value is None:
        return default
    if not isinstance(value, str):
        value = str(value)
    value = " ".join(value.split())
    if len(value) > length:
        value = value[:length]
    return value


def _parse_iso_dt(value, default=None):
    """Parse ISO-8601 (opsional akhiran Z/offset) ke datetime naive UTC; fallback default."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return default
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return default


_CLEAN_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f]")
# Kode warna SGR (ESC[...m) & sekuens clear screen — dipertahankan untuk render terminal
_TERM_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")
_TERM_KEEP_RE = re.compile(r"\x1b\[(?:[0-9;]*m|2J|3J|H|1;1H|[0-2]?K|[0-9]*P|[0-9]*[A-D])")
_ANSI_ANY_RE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|.)")


def _clean_result(value, maxchars: int = 40000, maxlines: int = 2000) -> str:
    """Sanitasi hasil log: KETAHAN pemisah baris (LF), buang kontrol lain.

    Versi regex — jauh lebih cepat dari iterasi per-karakter untuk output
    besar (apt streaming hingga beberapa MB per chunk).
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = _CLEAN_CTRL_RE.sub(" ", value)
    clean_lines = value.splitlines()
    if len(clean_lines) > maxlines:
        clean_lines = clean_lines[-maxlines:]
    clean = "\n".join(clean_lines)
    return clean[-maxchars:]


def _clean_terminal(value, maxchars: int = 200000, maxlines: int = 4000) -> str:
    """Sanitasi stream terminal (apt & shell) TANPA merusak tampilan.

    Berbeda dengan `_clean_result`, carriage return, backspace, form feed (\x0c),
    sekuens clear screen (\x1b[2J dll), dan kode warna SGR HARUS dipertahankan:
    kotak terminal di dashboard merender ulang kodenya supaya hasilnya sama
    seperti menjalankan shell/apt lewat SSH.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    def _keep_only(m: re.Match) -> str:
        return m.group(0) if _TERM_KEEP_RE.fullmatch(m.group(0)) else ""

    value = _ANSI_ANY_RE.sub(_keep_only, value)
    kept: list[str] = []

    def _stash(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"\ue000{len(kept) - 1}\ue001"

    value = _TERM_KEEP_RE.sub(_stash, value)
    value = "".join(c for c in value if c >= " " or c in "\n\r\b\t\x0c\ue000\ue001")
    for idx, code in enumerate(kept):
        value = value.replace(f"\ue000{idx}\ue001", code)
    lines = value.split("\n")
    if len(lines) > maxlines:
        lines = lines[-maxlines:]
    return "\n".join(lines)[-maxchars:]


def _clamp_int(value, default=None, lo: int = 0, hi: int = 2 ** 31 - 1):
    """Koersi ke int dalam rentang aman; fallback default bila tak valid."""
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _flash_qs(ok: bool, text: str) -> str:
    """Query string notifikasi utk redirect (?msg=… / ?err=…), URL-encoded."""
    return f"?{('msg' if ok else 'err')}={quote(text)}"


def _validate_ip(value: str) -> bool:
    """Cek apakah string adalah IPv4 atau IPv6 yang valid."""
    try:
        ipaddress.ip_address(value.strip())
        return True
    except ValueError:
        return False


def _clamp_float(value, default=None, lo: float = 0.0, hi: float = 2 ** 31 - 1):
    """Koersi ke float dalam rentang aman; fallback default bila tak valid."""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return max(lo, min(hi, v))


def _is_agent_outdated(agent_ver: str | None, current_ver: str) -> bool:
    """Cek apakah versi agen lebih lama dari versi dashboard saat ini."""
    if not agent_ver:
        return False
    try:
        v_agent = tuple(int(x) for x in re.findall(r"\d+", str(agent_ver)))
        v_curr = tuple(int(x) for x in re.findall(r"\d+", str(current_ver)))
        return v_agent < v_curr
    except Exception:
        return False


# ---------------------------------------------------------------------------
# API key: simpan sha256 (berprefix) di DB, bukan plaintext
# ---------------------------------------------------------------------------
KEY_PREFIX = "sha256:"


def hash_api_key(raw: str) -> str:
    return KEY_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def api_key_fingerprint(api_key: str) -> str:
    h = api_key
    if h.startswith(KEY_PREFIX):
        h = h[len(KEY_PREFIX):]
    return h[:8] + "…" + h[-8:] if len(h) > 16 else h


# ---------------------------------------------------------------------------
# CSRF protection (HMAC berbasis session ID)
# ---------------------------------------------------------------------------
def _csrf_token(sid: str) -> str:
    """Generate CSRF token dari session ID menggunakan HMAC-SHA256."""
    if not sid or not _SECRET_KEY:
        return ""
    return _hmac.new(
        _SECRET_KEY.encode("utf-8"),
        sid.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verify_csrf_form(request: Request, form_token: str) -> None:
    """Validasi CSRF token dari form field. Raise 403 jika tidak valid."""
    sid = request.cookies.get(SESSION_COOKIE, "")
    if not sid:
        return  # belum login, auth lain yang akan menolak
    expected = _csrf_token(sid)
    if not expected or not form_token or not _hmac.compare_digest(expected, form_token):
        raise HTTPException(status_code=403, detail="CSRF token tidak valid. Muat ulang halaman dan coba lagi.")


def _verify_csrf_header(request: Request) -> None:
    """Validasi CSRF token dari header X-CSRF-Token (untuk fetch/AJAX). Raise 403 jika tidak valid."""
    sid = request.cookies.get(SESSION_COOKIE, "")
    if not sid:
        return
    expected = _csrf_token(sid)
    header_token = request.headers.get("X-CSRF-Token", "")
    if not expected or not header_token or not _hmac.compare_digest(expected, header_token):
        raise HTTPException(status_code=403, detail="CSRF token tidak valid.")


def migrate_api_keys():
    """Sekali pakai: hash API key plaintext lama yang tersisa di DB."""
    db = SessionLocal()
    try:
        migrated = 0
        for srv in db.query(Server).filter(~Server.api_key.like(KEY_PREFIX + "%")).all():
            srv.api_key = hash_api_key(srv.api_key)
            migrated += 1
        if migrated:
            db.commit()
            logger.info("[startup] API key lama di-hash: %d server", migrated)
    finally:
        db.close()


def migrate_log_request_input():
    """Sekali pakai: tambah kolom input admin ke log_requests (mode interaktif)."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "log_requests" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("log_requests")}
    wanted = {
        "input_data": "VARCHAR(500) NULL",
        "input_at": "DATETIME NULL",
        "input_queue": "TEXT NULL",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    if not missing:
        return
    db = SessionLocal()
    try:
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE log_requests ADD COLUMN {col} {ddl}"))
        db.commit()
        logger.info("[startup] Kolom baru log_requests: %s", ", ".join(missing))
    except Exception as exc:  # noqa: BLE001 -- startup tak boleh gagal karena migrasi
        db.rollback()
        logger.warning("[startup] Migrasi kolom input gagal: %s", exc)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _SECRET_KEY
    _SECRET_KEY = settings.resolve_secret_key()
    Base.metadata.create_all(bind=engine)
    migrate_api_keys()
    migrate_log_request_input()
    try:
        with SessionLocal() as sess:
            _prune_expired_sessions(sess)
            sess.commit()
    except Exception as exc:
        logger.warning("[startup] prune sesi gagal: %s", exc)

    if not os.environ.get("PANTAU_BG_DISABLED"):
        threading.Thread(target=_problem_bg_loop, name="bg-problems", daemon=True).start()
        threading.Thread(target=_retention_loop, name="retention", daemon=True).start()
        logger.info("[bg-problems] evaluator aktif (tiap %ds)", BG_PROBLEM_EVAL_SECS)

    logger.info("[startup] Pantau Server siap")
    yield
    logger.info("[shutdown] Pantau Server berhenti")


# ---------------------------------------------------------------------------
# App & templates
# ---------------------------------------------------------------------------
app = FastAPI(title="Pantau Server", docs_url=None, redoc_url=None, lifespan=lifespan)
templates = Jinja2Templates(directory=settings.templates_dir)

static_dir = Path(__file__).resolve().parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self'; connect-src 'self' ws: wss:; form-action 'self'; "
        "base-uri 'self'; frame-ancestors 'none'; object-src 'none'"
    ),
}
# Tambahkan HSTS hanya jika HTTPS aktif
if settings.SESSION_COOKIE_SECURE:
    _SECURITY_HEADERS["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"


@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    for k, v in _SECURITY_HEADERS.items():
        if k not in resp.headers:
            resp.headers[k] = v
    return resp


def tpl(request: Request, name: str, context: dict, status_code: int = 200) -> HTMLResponse:
    ctx = dict(context) if context else {}
    # Injeksi CSRF token otomatis dan app_version ke semua template
    sid = request.cookies.get(SESSION_COOKIE, "")
    ctx.setdefault("csrf_token", _csrf_token(sid) if sid else "")
    ctx.setdefault("app_version", settings.APP_VERSION)
    return templates.TemplateResponse(request, name, ctx, status_code=status_code)


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
            msg = str(exc.detail) if exc.detail else "Anda tidak memiliki izin untuk mengakses halaman ini."
        else:
            title = f"Kendala Permintaan ({status_code})"
            msg = str(exc.detail) if exc.detail else "Permintaan tidak dapat diproses."

        return tpl(request, "error.html", {
            "status_code": status_code,
            "title": title,
            "message": msg,
            "user": user,
        }, status_code=status_code)

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
        detail_info = str(exc) if (user and getattr(user, "role", "") == "admin") else None

        return tpl(request, "error.html", {
            "status_code": 500,
            "title": title,
            "message": msg,
            "detail_info": detail_info,
            "user": user,
        }, status_code=500)

    return Response(
        content=json.dumps({"detail": "Internal Server Error"}),
        status_code=500,
        media_type="application/json",
    )




# ---------------------------------------------------------------------------
# PUBLIC: Agent report endpoint
# ---------------------------------------------------------------------------
# Pemetaan paket OS → nama service yang tampil di aplikasi (untuk tahu service
# mana yang akan terdampak upgrade). Selain tabel ini, dicocokkan langsung
# dengan service_name / process_name yang sedang berjalan di server.
PKG_SERVICE_MAP = {
    "openssh-server": "sshd",
    "openssh-client": "sshd",
    "nginx": "nginx",
    "nginx-core": "nginx",
    "mysql-server": "mysql",
    "mysql-client": "mysql",
    "mariadb-server": "mysql",
    "mariadb-client": "mysql",
    "mongodb-org-server": "mongod",
    "mongodb-org": "mongod",
    "postgresql": "postgresql",
    "redis-server": "redis",
    "docker.io": "docker",
    "docker-ce": "docker",
    "cockpit": "cockpit",
    "cockpit-ws": "cockpit-tls",
    "uvicorn": "uvicorn",
    "python3-uvicorn": "uvicorn",
    "zabbix-agent2": "zabbix_agent2",
    "google-chrome-stable": "chrome",
    "postfix": "postfix",
    "systemd": "systemd-resolve",
    "systemd-resolved": "systemd-resolve",
    "bind9": "named",
    "inetutils-syslogd": "syslog",
    "rsyslog": "syslog",
    "curl": "curl",
    "nodejs": "node",
    "nftables": "nft",
    "ufw": "ufw",
}


def _apt_pkg_services(pkg_name: str, services: list[str]) -> list[str]:
    """Service aktif (dari service_name) yang terdampak upgrade paket."""
    low = (pkg_name or "").lower()
    hits = set()
    mapped = PKG_SERVICE_MAP.get(low)
    if mapped:
        hits.add(mapped)
    for s in services:
        if not s:
            continue
        ls = s.lower()
        if ls == low:
            hits.add(s)
        elif len(ls) >= 3 and (low.startswith(ls) or ls in low.split("-")):
            hits.add(s)
    return sorted(hits)


def _sanitize_disk_list(raw) -> str | None:
    """Sanitasi list disk dari agen — validasi field dan tipe data."""
    if not isinstance(raw, list):
        return None
    cleaned = []
    for d in raw[:100]:
        if not isinstance(d, dict):
            continue
        cleaned.append({
            "mount": _clean_str(d.get("mount"), "", 255),
            "type": _clean_str(d.get("type"), "", 32),
            "total": _clamp_int(d.get("total"), 0, 0, 2 ** 63 - 1),
            "used": _clamp_int(d.get("used"), 0, 0, 2 ** 63 - 1),
            "pct": _clamp_float(d.get("pct"), 0.0, 0.0, 100.0),
        })
    return json.dumps(cleaned) if cleaned else None


def _sanitize_net_list(raw) -> str | None:
    """Sanitasi list interface jaringan dari agen — validasi field dan tipe data."""
    if not isinstance(raw, list):
        return None
    cleaned = []
    for n in raw[:50]:
        if not isinstance(n, dict):
            continue
        raw_ips = n.get("ip_addrs") or []
        ip_addrs = [str(ip)[:50] for ip in raw_ips[:8] if isinstance(ip, str)]
        cleaned.append({
            "iface": _clean_str(n.get("iface"), "", 32),
            "rx": _clamp_int(n.get("rx"), 0, 0, 2 ** 63 - 1),
            "tx": _clamp_int(n.get("tx"), 0, 0, 2 ** 63 - 1),
            "rx_rate": _clamp_float(n.get("rx_rate"), 0.0, 0.0, 1e12),
            "tx_rate": _clamp_float(n.get("tx_rate"), 0.0, 0.0, 1e12),
            "is_up": bool(n.get("is_up")),
            "ip_addrs": ip_addrs,
        })
    return json.dumps(cleaned) if cleaned else None



@app.post("/api/report")
def agent_report(
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        logger.warning("[AUTH] /api/report 401: fp=%s", api_key_fingerprint(x_api_key))
        raise HTTPException(status_code=401, detail="Invalid API key")

    server.hostname = _clean_str(body.get("hostname", server.hostname), server.hostname, 255)
    server.ip_address = _clean_str(body.get("ip_address", server.ip_address), server.ip_address, 45)[:45]
    server.last_seen = datetime.utcnow()
    db.flush()

    reported_service_ids = set()

    services = body.get("services")
    if not isinstance(services, list):
        services = []

    for svc in services:
        if not isinstance(svc, dict):
            continue
        service_name = _clean_str(svc.get("service_name"), "", 100)
        port = _clamp_int(svc.get("port"), 0, 1, 65535)
        if not service_name or not (1 <= port <= 65535):
            continue
        process_name = _clean_str(svc.get("process_name"), "", 100)
        status = svc.get("status", "down")
        if status not in ("up", "down"):
            status = "down"
        active_connections = _clamp_int(svc.get("active_connections"), 0, 0, 10 ** 9)
        response_time_ms = _clamp_int(svc.get("response_time_ms"), None, 0, 10 ** 6)
        health_message = _clean_str(svc.get("health_message"), "", 255)

        service = (
            db.query(Service)
            .filter(Service.server_id == server.id, Service.service_name == service_name)
            .first()
        )
        if not service and port > 0:
            # Bila port sudah ada di server ini (mis. smtpd vs master), pakai service yang ada agar tidak duplikat
            service = (
                db.query(Service)
                .filter(Service.server_id == server.id, Service.port == port)
                .first()
            )
        if not service:
            service = Service(
                server_id=server.id, service_name=service_name,
                port=port, process_name=process_name,
            )
            db.add(service)
            db.flush()
        else:
            service.port = port
            service.process_name = process_name

        reported_service_ids.add(service.id)
        db.add(Metric(
            service_id=service.id,
            status=status,
            active_connections=active_connections,
            response_time_ms=response_time_ms,
            health_message=health_message or None,
        ))

    # Service yang sudah terdaftar tapi tidak dilaporkan lagi -> tandai down
    existing = (
        db.query(Service).filter(Service.server_id == server.id).all()
    )
    for svc in existing:
        if svc.id in reported_service_ids:
            continue
        # Cek status terakhir, jangan insert duplikat kalau sudah down
        last = (
            db.query(Metric).filter(Metric.service_id == svc.id)
            .order_by(desc(Metric.timestamp)).first()
        )
        if not last or last.status == "up":
            db.add(Metric(
                service_id=svc.id, status="down", active_connections=0,
            ))

    db.commit()

    # ------------------------------------------------------------------
    # Data kinerja hardware/jaringan + akun + unit layanan (opsional)
    # ------------------------------------------------------------------
    sysd = body.get("system")
    if isinstance(sysd, dict):
        snap = SystemSnapshot(
            server_id=server.id,
            cpu=_clamp_float(sysd.get("cpu"), 0, 0, 100),
            load1=_clamp_float(sysd.get("load1"), 0, 0, 10 ** 9),
            load5=_clamp_float(sysd.get("load5"), 0, 0, 10 ** 9),
            load15=_clamp_float(sysd.get("load15"), 0, 0, 10 ** 9),
            mem_total=_clamp_int(sysd.get("mem_total"), 0, 0, 2 ** 63 - 1),
            mem_used=_clamp_int(sysd.get("mem_used"), 0, 0, 2 ** 63 - 1),
            mem_avail=_clamp_int(sysd.get("mem_avail"), 0, 0, 2 ** 63 - 1),
            swap_total=_clamp_int(sysd.get("swap_total"), 0, 0, 2 ** 63 - 1),
            swap_used=_clamp_int(sysd.get("swap_used"), 0, 0, 2 ** 63 - 1),
            procs=_clamp_int(sysd.get("procs"), None, 0, 2 ** 31 - 1),
            uptime_secs=_clamp_int(sysd.get("uptime"), None, 0, 2 ** 63 - 1),
            disks=_sanitize_disk_list(sysd.get("disks")),
            net=_sanitize_net_list(sysd.get("net")),
        )
        db.add(snap)
        # Prune snapshot > 24 jam (hemat disk)
        cutoff = datetime.utcnow() - timedelta(hours=24)
        db.query(SystemSnapshot).filter(
            SystemSnapshot.server_id == server.id,
            SystemSnapshot.timestamp < cutoff,
        ).delete(synchronize_session=False)
        # Materialisasikan rollup per jam (idempotent, hanya jam yang sudah lewat)
        _rollup_sys_hours(db, server.id)

    # Data berubah-sedikit: kernel, unit aktif, daftar akun
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
    if extras is None:
        extras = ServerExtras(server_id=server.id)
        db.add(extras)
    extras.kernel = _clean_str(body.get("kernel"), None, 100) or None
    extras.os_label = _clean_str(body.get("os_label"), None, 120) or None
    extras.arch = _clean_str(body.get("arch"), None, 24) or None
    extras.agent_version = _clean_str(body.get("agent_version"), None, 16) or None

    if isinstance(sysd, dict) and isinstance(sysd.get("top_procs"), dict):
        top_p = sysd["top_procs"]
        clean_top = {"cpu": [], "mem": []}
        for item in (top_p.get("cpu") or [])[:20]:
            if isinstance(item, dict):
                clean_top["cpu"].append({
                    "pid": _clamp_int(item.get("pid"), 0, 0, 2 ** 31 - 1),
                    "user": _clean_str(item.get("user"), "", 32),
                    "comm": _clean_str(item.get("comm"), "", 64),
                    "cpu": _clamp_float(item.get("cpu"), 0.0, 0.0, 1000.0),
                    "mem": _clamp_float(item.get("mem"), 0.0, 0.0, 100.0),
                })
        for item in (top_p.get("mem") or [])[:20]:
            if isinstance(item, dict):
                clean_top["mem"].append({
                    "pid": _clamp_int(item.get("pid"), 0, 0, 2 ** 31 - 1),
                    "user": _clean_str(item.get("user"), "", 32),
                    "comm": _clean_str(item.get("comm"), "", 64),
                    "cpu": _clamp_float(item.get("cpu"), 0.0, 0.0, 1000.0),
                    "mem": _clamp_float(item.get("mem"), 0.0, 0.0, 100.0),
                })
        extras.top_procs = json.dumps(clean_top)

    _VALID_UNIT_RE = re.compile(r'^[A-Za-z0-9@_.\-:]{1,100}$')
    if isinstance(body.get("units"), list):
        clean_units = [
            str(u)[:100] for u in body["units"][:200]
            if isinstance(u, str) and _VALID_UNIT_RE.match(str(u))
        ]
        extras.units = json.dumps(clean_units)
    if isinstance(body.get("accounts"), list):
        clean_accounts = []
        for acc in body["accounts"][:100]:
            if isinstance(acc, dict):
                clean_accounts.append({
                    "user": _clean_str(acc.get("user"), "", 64),
                    "uid": _clamp_int(acc.get("uid"), None, 0, 2 ** 31),
                    "shell": _clean_str(acc.get("shell"), "", 50),
                    "last_login": _clean_str(acc.get("last_login"), None, 32),
                    "sessions": _clamp_int(acc.get("sessions"), 0, 0, 9999),
                })
        extras.accounts = json.dumps(clean_accounts)
    # Info paket OS yang bisa di-upgrade (dari agen)
    if isinstance(body.get("apt"), dict):
        apt = body["apt"]
        if isinstance(apt.get("upgradable"), int):
            extras.apt_upgradable = max(0, apt["upgradable"])
        if isinstance(apt.get("last_update"), str):
            last_upd = _parse_iso_dt(apt["last_update"], None)
            if last_upd is not None:
                extras.apt_last_update = last_upd
        if isinstance(apt.get("packages"), list):
            running = [
                s.service_name
                for s in db.query(Service).filter(Service.server_id == server.id).all()
                if s.service_name
            ]
            pkgs = []
            for p in apt["packages"]:
                if isinstance(p, str) and p.strip():
                    cfg = {"name": p.strip(), "version": "", "services": []}
                elif isinstance(p, dict) and p.get("name"):
                    cfg = {
                        "name": str(p["name"]).strip(),
                        "version": str(p.get("version") or "").strip(),
                        "services": [],
                    }
                else:
                    continue
                cfg["services"] = _apt_pkg_services(cfg["name"], running)
                if cfg["name"]:
                    pkgs.append(cfg)
            extras.apt_packages = json.dumps(pkgs) if pkgs else None
    if isinstance(body.get("security"), dict):
        sec = body["security"]
        _ls_raw = _clean_str(sec.get("last_seen"), None, 32)
        last_seen = None
        if _ls_raw:
            try:
                datetime.fromisoformat(_ls_raw)
                last_seen = _ls_raw
            except ValueError:
                last_seen = None
        clean = {
            "failed": _clamp_int(sec.get("failed"), 0, 0, 10 ** 9),
            "invalid_users": _clamp_int(sec.get("invalid_users"), 0, 0, 10 ** 9),
            "source_ips": {str(k)[:45]: _clamp_int(v, 0, 0, 10 ** 9)
                           for k, v in (sec.get("source_ips") or {}).items()
                           if isinstance(v, (int, float)) and _validate_ip(str(k))},
            "last_seen": last_seen,
        }
        extras.security = json.dumps(clean)
    extras.updated_at = datetime.utcnow()

    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# JSON API (read-only)
# ---------------------------------------------------------------------------
@app.get("/api/servers")
def api_servers(user: User = Depends(require_user), db: Session = Depends(get_db)):
    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    extras_map = {ex.server_id: ex for ex in db.query(ServerExtras).all()}
    result = []
    for srv in servers:
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_list = []
        for svc in services:
            latest = latest_map.get(svc.id)
            svc_list.append({
                "id": svc.id, "name": svc.service_name, "port": svc.port,
                "process": svc.process_name,
                "status": latest.status if latest else "unknown",
                "connections": latest.active_connections if latest else 0,
                "response_time_ms": latest.response_time_ms if latest else None,
                "health_message": latest.health_message if latest else None,
                "last_check": latest.timestamp.isoformat() if latest else None,
            })
        stale = _server_stale(srv)
        overall = "down" if not any(s["status"] == "up" for s in svc_list) else "up"
        if stale:
            overall = "offline"
            for s in svc_list:
                s["status"] = "offline"
        ex = extras_map.get(srv.id)
        # Snapshot HW terbaru untuk CPU/RAM/uptime di dashboard
        latest_sys = (
            db.query(SystemSnapshot)
            .filter(SystemSnapshot.server_id == srv.id)
            .order_by(desc(SystemSnapshot.timestamp))
            .first()
        )
        cpu_pct = round(latest_sys.cpu, 1) if latest_sys else None
        mem_pct = (
            round(latest_sys.mem_used / latest_sys.mem_total * 100, 1)
            if latest_sys and latest_sys.mem_total else None
        )
        uptime_secs = latest_sys.uptime_secs if latest_sys else None
        down_svc_count = sum(1 for s in svc_list if s["status"] in ("down", "offline"))
        result.append({
            "id": srv.id, "hostname": srv.hostname, "ip_address": srv.ip_address,
            "is_active": srv.is_active,
            "online": overall != "offline",
            "last_seen": srv.last_seen.isoformat() if srv.last_seen else None,
            "overall_status": overall, "services": svc_list,
            "apt_upgradable": ex.apt_upgradable if ex else None,
            "apt_last_update": ex.apt_last_update.isoformat() if ex and ex.apt_last_update else None,
            "kernel": ex.kernel if ex else None,
            "os_label": ex.os_label if ex else None,
            "arch": ex.arch if ex else None,
            "cpu": cpu_pct,
            "mem_pct": mem_pct,
            "uptime_secs": uptime_secs,
            "down_svc_count": down_svc_count,
        })
    return result



@app.get("/api/servers/{sid}/overview")
def api_server_overview(sid: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Ringkasan live (services + perintah terbaru) untuk polling UI halaman Services."""
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    services = db.query(Service).filter(Service.server_id == sid).order_by(Service.port).all()
    pending_ids = {
        c.service_id
        for c in db.query(Command).filter(
            Command.server_id == sid, Command.status == "pending"
        ).all()
    }
    latest_map = _latest_metrics(db, (s.id for s in services))
    svc_list = []
    for svc in services:
        latest = latest_map.get(svc.id)
        svc_list.append({
            "id": svc.id, "name": svc.service_name, "port": svc.port,
            "status": latest.status if latest else "unknown",
            "connections": latest.active_connections if latest else 0,
            "response_time_ms": latest.response_time_ms if latest else None,
            "health_message": latest.health_message if latest else None,
            "pending": svc.id in pending_ids,
        })

    if _server_stale(server):
        for s in svc_list:
            s["status"] = "offline"

    commands = (
        db.query(Command).filter(Command.server_id == sid)
        .order_by(desc(Command.created_at)).limit(10).all()
    )
    cmd_list = [{
        "id": c.id, "service_id": c.service_id, "action": c.action,
        "status": c.status, "result": c.result,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    } for c in commands]
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    apt_run = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.unit.in_(APT_UNITS),
            LogRequest.status.in_(["pending", "executing"]),
        )
        .order_by(LogRequest.created_at)
        .first()
    )
    # Sesi Terminal Bawaan yang masih hidup, supaya halaman yang di-reload
    # menyambung lagi ke shell yang sama (tidak membuka shell kedua).
    shell_run = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.unit == SHELL_UNIT,
            LogRequest.status.in_(["pending", "executing"]),
        )
        .order_by(LogRequest.created_at.desc())
        .first()
    )
    if shell_run:
        stale_limit = datetime.utcnow() - timedelta(seconds=25)
        if (shell_run.updated_at and shell_run.updated_at < stale_limit) or (shell_run.created_at < stale_limit and shell_run.status == "pending"):
            shell_run.status = "failed"
            shell_run.result = (shell_run.result or "").strip() + "\n[sesi shell kedaluwarsa]"
            db.commit()
            shell_run = None
    return {
        "services": svc_list, "commands": cmd_list,
        "online": not _server_stale(server),
        "last_seen": server.last_seen.isoformat() if server.last_seen else None,
        # Kesegaran akurat (ms sejak laporan terakhir) — dipakai banner konfirmasi
        # Reboot/Power Off dengan jendela pendek (~30 dtk), bukan ambang offline 60 dtk.
        "last_seen_ago_ms": (
            int((datetime.now(timezone.utc)
                 - (server.last_seen.replace(tzinfo=timezone.utc)
                    if server.last_seen.tzinfo is None else server.last_seen)
                 ).total_seconds() * 1000)
            if server.last_seen else None
        ),
        "apt_upgradable": extras.apt_upgradable if extras else None,
        "apt_last_update": extras.apt_last_update.isoformat() if extras and extras.apt_last_update else None,
        "agent_version": extras.agent_version if extras else None,
        "agent_outdated": _is_agent_outdated(extras.agent_version if extras else None, settings.APP_VERSION),
        # Proses apt yang sedang berjalan (memenuhi polling resume bila halaman reload).
        "apt_exec": {
            "id": apt_run.id,
            "kind": apt_run.unit,
            "started_ms": int(apt_run.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if apt_run.created_at else None,
        } if apt_run else None,
        "is_maintenance": bool(server.is_maintenance),
        "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
        "maintenance_reason": server.maintenance_reason,
        # Sesi Terminal Bawaan yang masih hidup (resume setelah reload).
        "shell_exec": {
            "id": shell_run.id,
            "started_ms": int(shell_run.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if shell_run.created_at else None,
        } if shell_run else None,
    }


@app.get("/api/servers/{sid}/top-procs")
def api_server_top_procs(sid: int, request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Unauthorized")
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    procs = {"cpu": [], "mem": []}
    if extra and extra.top_procs:
        try:
            procs = json.loads(extra.top_procs)
        except Exception:
            pass
    return {
        "ok": True,
        "updated_at": extra.updated_at.isoformat() if extra and extra.updated_at else None,
        "top_procs": procs,
    }


@app.post("/api/servers/{sid}/maintenance")
async def api_server_maintenance(
    sid: int,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengatur mode pemeliharaan")
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    try:
        body = await request.json()
    except Exception:
        body = {}

    action = body.get("action", "enable")
    try:
        duration = int(body.get("duration_minutes", 60) or 0)
    except (ValueError, TypeError):
        duration = 60
    reason = str(body.get("reason", "") or "").strip()[:255]

    if action == "enable":
        server.is_maintenance = 1
        server.maintenance_reason = reason or "Pemeliharaan terencana"
        if duration > 0:
            server.maintenance_until = datetime.utcnow() + timedelta(minutes=duration)
        else:
            server.maintenance_until = None
        detail_msg = f"Mode pemeliharaan diaktifkan ({duration}m, alasan: {server.maintenance_reason})"
    else:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        detail_msg = "Mode pemeliharaan dinonaktifkan"

    db.add(AuditLog(
        username=user.username,
        action="maintenance_mode",
        target=f"Server {server.hostname} (ID {server.id})",
        result=detail_msg,
    ))
    db.commit()
    return {
        "ok": True,
        "is_maintenance": bool(server.is_maintenance),
        "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
        "maintenance_reason": server.maintenance_reason,
        "message": detail_msg,
    }


# ---------------------------------------------------------------------------
# Command queue (agent polling + result)
# ---------------------------------------------------------------------------
def _normalize_unit_for_systemctl(name: str | None) -> str | None:
    if not name:
        return name
    mapping = {
        "zabbix_agent2": "zabbix-agent2",
        "zabbix_agent": "zabbix-agent",
        "sshd": "ssh",
        "mysqld": "mariadb",
        "mariadbd": "mariadb",
    }
    return mapping.get(name, name.replace("_", "-") if name.startswith("zabbix_") else name)


@app.get("/api/commands")
def api_commands_pending(
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent mem-poll command pending untuk servernya."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    pending = (
        db.query(Command)
        .filter(Command.server_id == server.id, Command.status == "pending")
        .order_by(Command.created_at)
        .all()
    )
    return {
        "commands": [
            {
                "id": c.id,
                "action": c.action,
                "service_name": c.service.service_name if c.service else None,
                "process_name": _normalize_unit_for_systemctl(c.service.process_name if c.service else (c.service.service_name if c.service else None)),
                "port": c.service.port if c.service else None,
                "params": json.loads(c.params) if c.params else None,
            }
            for c in pending
        ]
    }



@app.post("/api/commands/{cid}/status")
def api_command_status(
    cid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent menandai command sedang dieksekusi."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if body.get("status") != "executing":
        raise HTTPException(status_code=400, detail="Status must be 'executing'")
    cmd = db.query(Command).filter(
        Command.id == cid, Command.server_id == server.id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd.status = "executing"
    db.commit()
    return {"ok": True}


@app.post("/api/commands/{cid}/result")
def api_command_result(
    cid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent melaporkan hasil eksekusi command."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    status = body.get("status")
    if status not in ("success", "failed"):
        raise HTTPException(status_code=400, detail="Status must be 'success' or 'failed'")
    cmd = db.query(Command).filter(
        Command.id == cid, Command.server_id == server.id
    ).first()
    if not cmd:
        raise HTTPException(status_code=404, detail="Command not found")

    cmd.status = status
    cmd.result = _clean_str(body.get("result"), "", 4000)
    cmd.executed_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Uptime helper
# ---------------------------------------------------------------------------
def compute_uptime(metrics: list[Metric]) -> dict:
    """
    Hitung uptime dari list metrics yang sudah sorted by timestamp.
    Menggunakan durasi antar sampel utk estimasi uptime yang akurat.
    """
    if not metrics:
        return {"uptime_pct": None, "downtime_seconds": 0, "samples": 0}

    total_sec = 0.0
    up_sec = 0.0
    down_sec = 0.0

    for i in range(len(metrics) - 1):
        cur, nxt = metrics[i], metrics[i + 1]
        dur = (nxt.timestamp - cur.timestamp).total_seconds()
        if dur < 0 or dur > 3600:  # clamp gap > 1 jam
            continue
        total_sec += dur
        if cur.status == "up":
            up_sec += dur
        else:
            down_sec += dur

    if total_sec == 0:
        return {"uptime_pct": None, "downtime_seconds": 0, "samples": len(metrics)}

    # Sampel terakhir sampai sekarang
    last = metrics[-1]
    dur = (datetime.utcnow() - last.timestamp).total_seconds()
    if 0 < dur <= 3600:
        total_sec += dur
        if last.status == "up":
            up_sec += dur
        else:
            down_sec += dur

    return {
        "uptime_pct": round((up_sec / total_sec) * 100, 2),
        "downtime_seconds": int(down_sec),
        "samples": len(metrics),
    }


def get_uptime_stats(db: Session, service_id: int, hours: int = 24) -> dict:
    """Uptime stats untuk service dalam rentang waktu."""
    since = datetime.utcnow() - timedelta(hours=hours)
    metrics = (
        db.query(Metric)
        .filter(Metric.service_id == service_id, Metric.timestamp >= since)
        .order_by(Metric.timestamp)
        .all()
    )
    return compute_uptime(metrics)


def _latest_metrics(db: Session, service_ids) -> dict[int, Metric]:
    """Satu query SQL utk metric terbaru per service (hindari N+1)."""
    if not service_ids:
        return {}
    sub = (
        db.query(Metric.service_id.label("service_id"), func.max(Metric.timestamp).label("max_ts"))
        .filter(Metric.service_id.in_(list(service_ids)))
        .group_by(Metric.service_id)
        .subquery()
    )
    rows = db.query(Metric).join(
        sub, (Metric.service_id == sub.c.service_id) & (Metric.timestamp == sub.c.max_ts)
    ).all()
    return {m.service_id: m for m in rows}


# ---------------------------------------------------------------------------
# LOGIN / LOGOUT
# ---------------------------------------------------------------------------
@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return tpl(request, "login.html", {"error": None})


LOGIN_MAX_FAILS = 5
LOGIN_LOCK_DURATIONS = [60, 300, 1800, 7200]  # 1 menit, 5 menit, 30 menit, 2 jam


def _client_ip(request: Request) -> str:
    """Dapatkan IP klien. Hanya percaya X-Forwarded-For dari proxy terpercaya."""
    real_ip = request.client.host if request.client else "unknown"
    if real_ip in settings.trusted_proxy_set:
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            candidate = xff.split(",")[0].strip()[:45]
            return candidate
    return real_ip


def _login_trial(db: Session, ip: str) -> LoginAttempt:
    row = db.query(LoginAttempt).filter(LoginAttempt.ip_address == ip).first()
    if row is None:
        row = LoginAttempt(ip_address=ip)
        db.add(row)
        db.flush()
    return row


@dataclass
class _Trial:
    fails: int
    lock_until: datetime | None


def _lock_remaining(row: LoginAttempt) -> int:
    if row.lock_until is None:
        return 0
    return max(0, int((row.lock_until - datetime.utcnow()).total_seconds()))


@app.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = _client_ip(request)
    row = _login_trial(db, ip)
    if _lock_remaining(row) > 0:
        wait = int((row.lock_until - datetime.utcnow()).total_seconds())
        db.rollback()  # buang baris baru bila belum pernah ada
        return tpl(request, "login.html", {"error": f"Terlalu banyak percobaan. Coba lagi dalam {wait} detik."})

    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_ctx.verify(password, user.password_hash):
        # Gunakan fails negatif untuk menyimpan lock_count jika belum di-reset
        lock_count = -row.fails if row.fails < 0 else 0
        if row.fails < 0:
            row.fails = 1
        else:
            row.fails += 1
            
        row.updated_at = datetime.utcnow()
        if row.fails >= LOGIN_MAX_FAILS:
            lock_secs = LOGIN_LOCK_DURATIONS[min(lock_count, len(LOGIN_LOCK_DURATIONS) - 1)]
            row.lock_until = datetime.utcnow() + timedelta(seconds=lock_secs)
            row.fails = -(lock_count + 1)
            logger.warning("[AUTH] Login gagal terlalu banyak dari IP %s — kunci %d detik", request.client.host if request.client else "unknown", lock_secs)
        db.commit()
        return tpl(request, "login.html", {"error": "Username atau password salah"})

    row.fails = 0
    row.lock_until = None
    row.updated_at = datetime.utcnow()
    _prune_expired_sessions(db)
    sid = create_session(db, user.id, ip, request.headers.get("user-agent"))
    _audit(db, user.username, "login", f"masuk dari {ip}", "berhasil")
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE, sid, httponly=True, samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()), path="/",
    )
    return resp


@app.get("/logout")
@app.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        db.query(AppSession).filter(AppSession.sid == sid).delete(synchronize_session=False)
        db.commit()
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    total = len(servers)
    up_count = 0
    down_services = 0
    extras_map = {ex.server_id: ex for ex in db.query(ServerExtras).all()}

    for srv in servers:
        ex = extras_map.get(srv.id)
        srv._apt_upgradable = ex.apt_upgradable if ex else None
        srv._apt_last_update = ex.apt_last_update if ex else None
        srv._os_label = ex.os_label if ex else None
        srv._arch = ex.arch if ex else None
        srv._kernel = ex.kernel if ex else None
        srv._agent_version = ex.agent_version if ex else None
        srv._agent_outdated = _is_agent_outdated(srv._agent_version, settings.APP_VERSION)
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        srv._svc_data = []
        for svc in services:
            latest = latest_map.get(svc.id)
            d = {
                "name": svc.service_name, "port": svc.port, "process": svc.process_name,
                "status": latest.status if latest else "unknown",
                "connections": latest.active_connections if latest else 0,
                "response_time": latest.response_time_ms if latest else None,
                "health_msg": latest.health_message if latest else None,
                "last_check": latest.timestamp.isoformat() if latest else None,
            }
            srv._svc_data.append(d)
            if latest and latest.status != "up":
                down_services += 1
        stale = _server_stale(srv)
        if stale:
            for d in srv._svc_data:
                d["status"] = "offline"
        if srv.is_maintenance:
            srv._status_label, srv._status_cls = "Pemeliharaan", "badge-warn"
        else:
            srv._status_label, srv._status_cls = _server_status(
                srv, stale, bool(srv._svc_data), any(d["status"] == "up" for d in srv._svc_data))
        if srv._status_cls == "badge-up":
            up_count += 1
        srv._problem_level, srv._problems, _ph = sync_server_problems(
            db, srv, _problem_instances(srv, ex, srv._svc_data, db))

    last_metric = db.query(Metric.timestamp).order_by(desc(Metric.timestamp)).first()
    if last_metric:
        ts = last_metric[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        last_update_secs = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    else:
        last_update_secs = -1

    return tpl(request, "dashboard.html", {
        "user": user, "servers": servers, "total": total,
        "up_count": up_count, "down_count": total - up_count,
        "down_services": down_services, "last_update_secs": last_update_secs,
    })


# ---------------------------------------------------------------------------
# SERVERS
# ---------------------------------------------------------------------------
@app.get("/servers", response_class=HTMLResponse)
def servers_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    extras_map = {ex.server_id: ex for ex in db.query(ServerExtras).all()}
    server_ids = [s.id for s in servers]
    svc_counts = dict(
        db.query(Service.server_id, func.count(Service.id))
        .filter(Service.server_id.in_(server_ids))
        .group_by(Service.server_id)
        .all()
    ) if server_ids else {}

    for srv in servers:
        srv._service_count = svc_counts.get(srv.id, 0)
        srv._key_fp = api_key_fingerprint(srv.api_key)
        ex = extras_map.get(srv.id)
        srv._apt_upgradable = ex.apt_upgradable if ex else None
        srv._apt_last_update = ex.apt_last_update if ex and ex.apt_last_update else None
        srv._os_label = ex.os_label if ex else None
        srv._arch = ex.arch if ex else None
        srv._agent_version = ex.agent_version if ex else None
        srv._agent_outdated = _is_agent_outdated(srv._agent_version, settings.APP_VERSION)
        srv._online = not _server_stale(srv)
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_data = []
        for svc in services:
            latest = latest_map.get(svc.id)
            svc_data.append({
                "name": svc.service_name,
                "status": latest.status if latest else "unknown",
            })
        if srv.is_maintenance:
            srv._status_label, srv._status_cls = "Pemeliharaan", "badge-warn"
        else:
            srv._status_label, srv._status_cls = _server_status(
                srv, not srv._online, bool(svc_data), any(d["status"] == "up" for d in svc_data))
        srv._problem_level, srv._problems, _ph = sync_server_problems(
            db, srv, _problem_instances(srv, ex, svc_data, db))
    return tpl(request, "servers.html", {"user": user, "servers": servers})


@app.get("/servers/add", response_class=HTMLResponse)
def server_add_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    return tpl(request, "server_form.html", {"user": user, "server": None, "mode": "add"})


@app.post("/servers/add")
def server_add_submit(
    request: Request,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    hostname = _clean_str(hostname, "", 255)
    ip_address = _clean_str(ip_address, "", 45)[:45]
    if ip_address and not _validate_ip(ip_address):
        return tpl(request, "server_form.html", {
            "user": user, "server": None, "mode": "add",
            "error": "Format IP address tidak valid. Gunakan IPv4 (contoh: 192.168.1.1) atau IPv6."
        })
    raw = secrets.token_hex(32)
    srv = Server(hostname=hostname, ip_address=ip_address, api_key=hash_api_key(raw))
    db.add(srv)
    _audit(db, user.username, "server_add", f"{hostname} ({ip_address})", "berhasil")
    db.commit()
    resp = tpl(request, "key_reveal.html", {"user": user, "server": srv, "api_key": raw})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/servers/{sid}/edit", response_class=HTMLResponse)
def server_edit_page(request: Request, sid: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    server._key_fp = api_key_fingerprint(server.api_key)
    return tpl(request, "server_form.html", {"user": user, "server": server, "mode": "edit"})


@app.post("/servers/{sid}/edit")
def server_edit_submit(
    request: Request, sid: int,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    is_active: int = Form(1),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if server:
        hostname = _clean_str(hostname, server.hostname, 255)
        ip_address = _clean_str(ip_address, server.ip_address, 45)[:45]
        if ip_address and not _validate_ip(ip_address):
            server._key_fp = api_key_fingerprint(server.api_key)
            return tpl(request, "server_form.html", {
                "user": user, "server": server, "mode": "edit",
                "error": "Format IP address tidak valid. Gunakan IPv4 (contoh: 192.168.1.1) atau IPv6."
            })
        server.hostname = hostname
        server.ip_address = ip_address
        server.is_active = 1 if is_active else 0
        _audit(db, user.username, "server_edit",
               f"id={server.id} {server.hostname} ({server.ip_address})", "berhasil")
        db.commit()
        return RedirectResponse("/servers" + _flash_qs(True, "Server diperbarui"), status_code=303)
    return RedirectResponse("/servers" + _flash_qs(False, "Server tidak ditemukan"), status_code=303)


@app.post("/servers/{sid}/regenerate-key")
def server_regenerate_key(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if server:
        raw = secrets.token_hex(32)
        server.api_key = hash_api_key(raw)
        _audit(db, user.username, "key_regenerate", f"{server.hostname} (id={server.id})", "berhasil")
        db.commit()
        resp = tpl(request, "key_reveal.html", {"user": user, "server": server, "api_key": raw})
        resp.headers["Cache-Control"] = "no-store"
        return resp
    return RedirectResponse("/servers", status_code=303)


@app.post("/servers/{sid}/delete")
def server_delete(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if server:
        _audit(db, user.username, "server_delete",
               f"{server.hostname} ({server.ip_address}) id={server.id}", "berhasil")
        db.delete(server)
        db.commit()
        return RedirectResponse("/servers" + _flash_qs(True, "Server dihapus"), status_code=303)
    return RedirectResponse("/servers" + _flash_qs(False, "Server tidak ditemukan"), status_code=303)


# ---------------------------------------------------------------------------
# SERVICES
# ---------------------------------------------------------------------------
@app.get("/servers/{sid}/services", response_class=HTMLResponse)
def services_page(request: Request, sid: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    services = db.query(Service).filter(Service.server_id == sid).all()
    latest_map = _latest_metrics(db, (s.id for s in services))
    for svc in services:
        latest = latest_map.get(svc.id)
        svc._status = latest.status if latest else "unknown"
        svc._conns = latest.active_connections if latest else 0
        svc._response_time = latest.response_time_ms if latest else None
        svc._health_msg = latest.health_message if latest else None
        svc._last_check = latest.timestamp if latest else None
        svc._uptime = get_uptime_stats(db, svc.id, hours=24)

        # Cek apakah ada command pending/sedang berjalan
        svc._pending_cmd = (
            db.query(Command)
            .filter(
                Command.service_id == svc.id,
                Command.status.in_(["pending", "executing"]),
            )
            .first()
        )

    commands = (
        db.query(Command)
        .filter(Command.server_id == sid)
        .order_by(desc(Command.created_at))
        .limit(10)
        .all()
    )
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    svc_data = [{"name": s.service_name, "status": getattr(s, "_status", "unknown")}
                for s in services]
    problem_level, open_problems, problem_history = sync_server_problems(
        db, server, _problem_instances(server, extra, svc_data, db))
    svc_map = {s.service_name: s for s in services}
    log_units = {"SYSLOG", "AUTH", "SYSTEM"}
    try:
        log_units |= set(json.loads(extra.units) or []) if extra and extra.units else set()
    except (TypeError, ValueError):
        pass
    sec = _parse_extras_security(extra)
    for r in open_problems:
        if r["key"].startswith("service_down:"):
            svc = svc_map.get(r["key"].split(":", 1)[1])
            r["action"] = "restart" if svc else None
            r["svc_id"] = svc.id if svc else None
            r["log_unit"] = r["key"].split(":", 1)[1] if r["key"].split(":", 1)[1] in log_units else None
        elif r["key"].startswith("svc_no_data:"):
            r["action"] = "log"
            r["log_unit"] = r["key"].split(":", 1)[1] if r["key"].split(":", 1)[1] in log_units else None
        elif r["key"] in ("security_danger", "failed_logins"):
            r["action"] = "mitigate"
            r["log_unit"] = "AUTH"
            r["ip_count"] = len(sec.get("source_ips") or {})
        elif r["key"] == "agent_stale":
            r["action"] = "agent_restart"
        elif r["key"] == "apt_updates":
            r["action"] = "apt_update" if user.role == "admin" else None
        else:
            r["action"] = None
    top_p = {"cpu": [], "mem": []}
    if extra and extra.top_procs:
        try:
            top_p = json.loads(extra.top_procs)
        except Exception:
            pass
    return tpl(request, "services.html", {
        "user": user, "server": server, "services": services, "commands": commands,
        "agent_version": extra.agent_version if extra else None,
        "is_agent_outdated": _is_agent_outdated(extra.agent_version if extra else None, settings.APP_VERSION),
        "os_label": extra.os_label if extra else None,
        "kernel": extra.kernel if extra else None,
        "is_online": not _server_stale(server),
        "problem_level": problem_level, "open_problems": open_problems,
        "problem_history": problem_history,
        "top_procs": top_p,
    })


@app.get("/servers/{sid}/user/{username}", response_class=HTMLResponse)
def user_activity_page(request: Request, sid: int, username: str, db: Session = Depends(get_db)):
    """Detail aktivitas seorang user: info akun, aktivitas login, riwayat perintah."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    if not VALID_UNIT_RE.match(username) or len(username) > 64:
        return RedirectResponse(f"/servers/{sid}/services", status_code=303)
    account = None
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if extra and extra.accounts:
        try:
            accounts = json.loads(extra.accounts)
        except (TypeError, ValueError):
            accounts = []
        for a in (accounts if isinstance(accounts, list) else []):
            if a.get("user") == username:
                account = a
                break
    return tpl(request, "user_activity.html", {
        "user": user, "server": server, "username": username, "account": account,
    })


@app.post("/servers/{sid}/services/add")
def service_add_submit(
    request: Request, sid: int,
    service_name: str = Form(...),
    port: int = Form(...),
    process_name: str = Form(...),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    svc = Service(
        server_id=sid,
        service_name=_clean_str(service_name, "", 100),
        port=_clamp_int(port, 0, 1, 65535),
        process_name=_clean_str(process_name, "", 100),
    )
    if not svc.service_name or not (1 <= svc.port <= 65535):
        return RedirectResponse(f"/servers/{sid}/services" + _flash_qs(False, "Service tidak lengkap: nama wajib & port 1-65535"), status_code=303)
    existing = (
        db.query(Service).filter(
            Service.server_id == sid, Service.service_name == svc.service_name
        ).first()
    )
    if existing:
        return RedirectResponse(f"/servers/{sid}/services" + _flash_qs(False, "Nama service sudah ada"), status_code=303)
    db.add(svc)
    db.commit()
    return RedirectResponse(f"/servers/{sid}/services" + _flash_qs(True, "Service ditambahkan"), status_code=303)


@app.post("/servers/{sid}/services/{svc_id}/restart")
def service_restart(
    request: Request, sid: int, svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or user.role != "admin":
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Akses ditolak (hanya admin)"}), status_code=403, media_type="application/json")
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Service tidak ditemukan"}), status_code=404, media_type="application/json")
        return RedirectResponse(f"/servers/{sid}/services", status_code=303)

    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.service_id == svc_id,
            Command.status == "pending",
        )
        .first()
    )
    if not existing:
        db.add(Command(
            server_id=sid, service_id=svc_id, action="restart", status="pending",
            issued_by=user.username,
        ))
        db.commit()
    if is_json:
        return Response(json.dumps({"ok": True, "detail": f"Perintah restart {svc.service_name} telah dikirim ke Agen Pantau."}), media_type="application/json")
    return RedirectResponse(f"/servers/{sid}/services?restarted=1", status_code=303)


def _service_action(request: Request, sid: int, svc_id: int, action: str, db, csrf_token: str = ""):
    """Helper bersama untuk start/stop layanan."""
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or user.role != "admin":
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Akses ditolak (hanya admin)"}), status_code=403, media_type="application/json")
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Service tidak ditemukan"}), status_code=404, media_type="application/json")
        return RedirectResponse(f"/servers/{sid}/services", status_code=303)
    existing = (
        db.query(Command)
        .filter(Command.server_id == sid, Command.service_id == svc_id, Command.status == "pending")
        .first()
    )
    if not existing:
        db.add(Command(
            server_id=sid, service_id=svc_id, action=action, status="pending",
            issued_by=user.username,
        ))
        server = db.query(Server).filter(Server.id == sid).first()
        _audit(db, user.username, f"service_{action}",
               f"{server.hostname if server else sid}:{svc.service_name}", "dikirim ke agen")
        db.commit()
    label_id = {"start": "mulai", "stop": "hentikan"}.get(action, action)
    if is_json:
        return Response(json.dumps({"ok": True, "detail": f"Perintah {label_id} {svc.service_name} telah dikirim ke Agen Pantau."}), media_type="application/json")
    return RedirectResponse(f"/servers/{sid}/services?restarted=1", status_code=303)


@app.post("/servers/{sid}/services/{svc_id}/start")
def service_start(
    request: Request, sid: int, svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Mulai layanan yang sedang stop (admin)."""
    return _service_action(request, sid, svc_id, "start", db, csrf_token)


@app.post("/servers/{sid}/services/{svc_id}/stop")
def service_stop(
    request: Request, sid: int, svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Hentikan layanan yang sedang berjalan (admin)."""
    return _service_action(request, sid, svc_id, "stop", db, csrf_token)

def _enqueue_mitigation(db, sid: int, action: str, params: dict | None = None, issued_by=None) -> None:
    """Antrekan command mitigasi (block_ip/restart_agent) tanpa service terkait."""
    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == action,
            Command.status == "pending",
        )
        .first()
    )
    if not existing:
        db.add(Command(
            server_id=sid, service_id=None, action=action,
            params=json.dumps(params) if params else None, status="pending",
            issued_by=issued_by,
        ))
        db.commit()


@app.post("/servers/{sid}/problems/block")
def problem_block_ip(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Mitigasi: blokir IP sumber serangan SSH (iptables) via agen."""
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    sec = _parse_extras_security(extra)

    def _safe_block_ip(s: str) -> bool:
        try:
            a = ipaddress.ip_address(s)
        except ValueError:
            return False
        if a.is_loopback or a.is_link_local or a.is_multicast \
                or a.is_unspecified or a.is_reserved:
            return False
        return s != server.ip_address

    all_ips = list((sec.get("source_ips") or {}).keys())
    ips = [s for s in all_ips[:40] if _safe_block_ip(s)][:10]
    if not ips:
        return RedirectResponse(f"/servers/{sid}/services?action=noips", status_code=303)
    _enqueue_mitigation(db, sid, "block_ip", {"ips": ips}, issued_by=user.username)
    return RedirectResponse(f"/servers/{sid}/services?action=block", status_code=303)


@app.post("/servers/{sid}/problems/restart-agent")
def problem_restart_agent(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Mitigasi: restart agen (agent_pantau) jika tidak lagi melapor."""
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    _enqueue_mitigation(db, sid, "restart_agent", issued_by=user.username)
    return RedirectResponse(f"/servers/{sid}/services?action=agent", status_code=303)


def _host_control(request: Request, sid: int, db: Session, action: str, csrf_token: str = "") -> RedirectResponse:
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    _enqueue_mitigation(db, sid, action, issued_by=user.username)
    _audit(db, user.username, action,
           f"{server.hostname} ({server.ip_address})", "dikirim ke agen")
    db.commit()
    flag = "reboot" if action == "reboot_host" else "poweroff"
    at_epoch = int(datetime.now(timezone.utc).timestamp())
    return RedirectResponse(f"/servers/{sid}/services?action={flag}&at={at_epoch}", status_code=303)


@app.post("/servers/{sid}/host/reboot")
def host_reboot(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Reboot OS server klien (admin). Tegas: mesin restart seketika ±4 detik."""
    return _host_control(request, sid, db, "reboot_host", csrf_token)


@app.post("/servers/{sid}/host/poweroff")
def host_poweroff(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Poweroff OS server klien (admin). Tegas: mesin mati sampai dinyalakan manual."""
    return _host_control(request, sid, db, "poweroff_host", csrf_token)


@app.post("/servers/{sid}/services/{svc_id}/delete")
def service_delete(
    request: Request, sid: int, svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or user.role != "admin":
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Akses ditolak (hanya admin)"}), status_code=403, media_type="application/json")
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if svc:
        server = db.query(Server).filter(Server.id == sid).first()
        _audit(db, user.username, "service_delete",
               f"{server.hostname if server else sid}:{svc.service_name}", "berhasil")
        db.delete(svc)
        db.commit()
        if is_json:
            return Response(json.dumps({"ok": True, "detail": f"Service {svc.service_name} dihapus"}), media_type="application/json")
    elif is_json:
        return Response(json.dumps({"ok": False, "detail": "Service tidak ditemukan"}), status_code=404, media_type="application/json")
    return RedirectResponse(f"/servers/{sid}/services", status_code=303)


# ---------------------------------------------------------------------------
# PROBLEMS (agregat semua server)
# ---------------------------------------------------------------------------
@app.get("/problems", response_class=HTMLResponse)
def problems_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    filter_sid_str = request.query_params.get("server", "")
    filter_sid = int(filter_sid_str) if filter_sid_str.isdigit() else None
    open_problems, recent_resolved = problems_aggregate(db)
    if filter_sid:
        open_problems = [p for p in open_problems if p["server_id"] == filter_sid]
        recent_resolved = [p for p in recent_resolved if p["server_id"] == filter_sid]
    servers_total = db.query(Server).count()
    open_servers = {p["server_id"] for p in open_problems}
    all_servers = db.query(Server).order_by(Server.hostname).all()
    return tpl(request, "problems.html", {
        "user": user,
        "open_problems": open_problems,
        "recent_resolved": recent_resolved,
        "danger_open": sum(1 for p in open_problems if p["severity"] == "danger"),
        "warning_open": sum(1 for p in open_problems if p["severity"] == "warning"),
        "info_open": sum(1 for p in open_problems if p["severity"] == "info"),
        "ok_count": servers_total - len(open_servers),
        "all_servers": all_servers,
        "filter_sid": filter_sid,
    })



# ---------------------------------------------------------------------------
# METRICS
# ---------------------------------------------------------------------------
# Halaman Metrik tidak lagi terpisah: seluruh data metrik per-layanan sudah
# ada di tab "Layanan" halaman Rincian (grafik + daftar + uptime), dengan
# versi yang lebih baik. Tautan lama dialihkan ke sana supaya tidak hilang.
@app.get("/servers/{sid}/metrics", response_class=HTMLResponse)
def metrics_page(request: Request, sid: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    return RedirectResponse(f"/servers/{sid}/services?tab=layanan", status_code=303)


# ---------------------------------------------------------------------------
# DASHBOARD LOGS (log aplikasi pusat, dibaca lokal)
# ---------------------------------------------------------------------------
def tail_lines(path: str, n: int = 300) -> list[str]:
    """Ambil N baris terakhir dari file log dengan aman (satu kali buka file)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            n = max(1, n)
            block = 4096
            data = b""
            offset = size
            while offset > 0 and len(data) < n * 1024:
                read_bytes = min(block, offset)
                offset -= read_bytes
                f.seek(offset)
                data = f.read(read_bytes) + data
            lines = data.decode("utf-8", errors="replace").splitlines()
            return lines[-n:]
    except OSError:
        return []


@app.get("/logs", response_class=HTMLResponse)
def logs_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return tpl(request, "logs.html", {"user": user, "log_file": settings.LOG_FILE})


@app.get("/api/logs/dashboard")
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


# ---------------------------------------------------------------------------
# SYSTEM STATUS (performa host dashboard, dibaca dari /proc)
# ---------------------------------------------------------------------------
PROC_CACHE: dict = {"t": 0.0, "pt": 0.0, "cput": 0, "cpub": 0, "procs": {}}


def _proc_uptime() -> float:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except OSError:
        return 0.0


def _proc_loadavg() -> list:
    try:
        with open("/proc/loadavg") as f:
            return [float(x) for x in f.read().split()[:3]]
    except OSError:
        return []


def _proc_cpu() -> dict:
    now = time.time()
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
    except OSError:
        return {"cpu_percent": None, "cores": 0}
    if not parts or parts[0] != "cpu":
        return {"cpu_percent": None, "cores": 0}
    vals = [int(x) for x in parts[1:8]]
    total = sum(vals)
    busy = total - (vals[3] + vals[4])  # idle + iowait
    pct = None
    prev_t = PROC_CACHE["t"]
    if prev_t:
        dt = now - prev_t
        nt = total - PROC_CACHE["cput"]
        if dt > 0 and nt > 0:
            pct = round((busy - PROC_CACHE["cpub"]) / nt * 100, 1)
    PROC_CACHE["pt"], PROC_CACHE["t"] = prev_t, now
    PROC_CACHE["cput"], PROC_CACHE["cpub"] = total, busy
    return {"cpu_percent": pct, "cores": os.cpu_count() or 1}


def _proc_memory() -> dict:
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2:
                    info[p[0].rstrip(":")] = int(p[1])
    except OSError:
        return {}
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    kb = 1024
    return {
        "total": total * kb,
        "available": avail * kb,
        "used": max(0, total - avail) * kb,
        "swap_total": swap_total * kb,
        "swap_used": max(0, swap_total - swap_free) * kb,
    }


def _proc_disks() -> list:
    mounts = []
    seen = set()
    try:
        with open("/proc/mounts") as f:
            rows = [l.split() for l in f]
    except OSError:
        return mounts
    for r in rows:
        if len(r) < 3:
            continue
        fstype = r[2]
        if not (
            fstype.startswith(("ext", "xfs", "btrfs", "vfat", "ntfs", "zfs"))
            or fstype == "overlay"
        ):
            continue
        mp = r[1]
        if mp in seen:
            continue
        seen.add(mp)
        try:
            st = os.statvfs(mp)
        except OSError:
            continue
        if mp == "/": 
            row = {"mount": mp, "fstype": fstype if fstype != "overlay" else "rootfs"}
        else:
            row = {"mount": mp, "fstype": fstype}
        total = st.f_blocks * st.f_frsize
        used = (st.f_blocks - st.f_bavail) * st.f_frsize
        row["total"] = total
        row["used"] = used
        row["percent"] = round(used / total * 100, 1) if total else 0.0
        mounts.append(row)
    return mounts[:8]


def _proc_top(n: int = 8) -> list:
    clk = os.sysconf("SC_CLK_TCK") or 100
    pagesize = os.sysconf("SC_PAGE_SIZE") or 4096
    now = time.time()
    prev = PROC_CACHE["procs"]
    cur = {}
    rows = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return rows
    ncpu = os.cpu_count() or 1
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as f:
                fields = f.read().rstrip(")").rsplit(")", 1)[1].split()
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()[:30]
            if len(fields) < 13:
                continue
            state = fields[0]
            utime = int(fields[11])
            stime = int(fields[12])
            with open(f"/proc/{pid}/statm") as f:
                rss = int(f.read().split()[1]) * pagesize
        except (OSError, ValueError, IndexError):
            continue
        cur[pid] = (utime, stime)
        dt = PROC_CACHE["t"] - PROC_CACHE["pt"]  # rentang sampel sebelumnya -> sekarang
        if pid in prev and dt > 0:
            pu, ps = prev[pid]
            ticks = (utime - pu) + (stime - ps)
            if ticks >= 0:
                pct = min(round(ticks / (dt * clk) * 100, 1), ncpu * 100)
                rows.append({"pid": int(pid), "comm": comm, "state": state, "cpu": pct, "rss": rss})
    PROC_CACHE["procs"] = cur
    rows.sort(key=lambda x: x["cpu"], reverse=True)
    return rows[:n]


@app.get("/api/system/status")
def api_system_status(user: User = Depends(require_user), db: Session = Depends(get_db)):
    return {
        "hostname": socket.gethostname(),
        "uptime": _proc_uptime(),
        "loadavg": _proc_loadavg(),
        "cpu": _proc_cpu(),
        "memory": _proc_memory(),
        "disks": _proc_disks(),
        "processes": _proc_top(),  # deltas butuh sampel pertama dari poll sebelumnya
    }


VALID_UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:+-]{1,100}$")
# Unit log khusus OS: bisa butuh jawaban admin saat berjalan (mode interaktif),
# jadi tidak boleh dianggap "stale" seperti permintaan log biasa.
APT_UNITS = ("APT_UPDATE", "APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX")
# Terminal Bawaan: shell root interaktif di pty. Bukan "unit log" - lives
# sampai admin menutupnya, dan input dialirkan terus-menerus.
SHELL_UNIT = "SHELL"
# Semua unit yang butuh admin + boleh menerima input stdin sambil berjalan.
INTERACTIVE_UNITS = APT_UNITS + (SHELL_UNIT,)
# Batas antrean ketikan shell yang ditahan sebelum byte terlama dibuang.
SHELL_INPUT_MAX = 64 * 1024


def _req_is_shell(db: Session, rid: int, server_id: int) -> bool:
    """True bila rid adalah sesi shell milik server ini dan masih hidup."""
    row = db.query(LogRequest.unit, LogRequest.status).filter(
        LogRequest.id == rid, LogRequest.server_id == server_id
    ).first()
    return bool(row) and row[0] == SHELL_UNIT and row[1] == "executing"
SYSLOG_FILE = "/var/log/syslog"
AUTH_FILE = "/var/log/auth.log"
STALE_LOG_SECONDS = 600
# Server dianggap offline bila tidak ada laporan dalam rentang ini (interval agent 10s)
OFFLINE_AFTER_SECONDS = 60
# Batas output apt update/upgrade yang disimpan/streaming (praktis tak terpotong;
# MEDIUMTEXT di DB kuota 16MB, ini masih jauh di bawahnya).
APT_STREAM_MAXCHARS = 4_000_000
APT_STREAM_MAXLINES = 120_000

# Ambang indikator keamanan (dari ringkasan auth.log window agen)
SECURITY_DANGER_FAILED = 12      # >= -> kemungkinan brute force
SECURITY_DANGER_INVALID = 4      # >= upaya user invalid -> recon/serangan
SECURITY_WARNING_FAILED = 5      # >= -> warning
PROBLEM_RANK = {"ok": 0, "info": 1, "warning": 2, "danger": 3}

# Ambang sumber daya (data real-time dari agen). Data dianggap segar bila
# snapshot terakhir < FRESH_SNAP_SECS (interval agen 10-15 detik).
FRESH_SNAP_SECS = 90
RAM_DANGER_PCT = 95.0        # persentase RAM terpakai -> danger
RAM_WARNING_PCT = 85.0
SWAP_DANGER_PCT = 92.0
SWAP_WARNING_PCT = 80.0
CPU_DANGER_PCT = 95.0        # rata-rata CPU % -> danger
CPU_WARNING_PCT = 85.0
DISK_DANGER_PCT = 95.0       # persentase disk terpakai -> danger
DISK_WARNING_PCT = 90.0

RAM_TIP = ("Cek proses pemakan memori: sudo ps aux --sort=-%mem | head | Hentikan/mulai ulang ambisius: "
           "sudo systemctl restart <unit> | Beri sumber daya RVMM. Server bisa crash/OOM bila dibiarkan.")
CPU_TIP = ("Cek proses pemakan CPU: sudo ps aux --sort=-%cpu | head -20 | restart unit bermasalah; "
           "pertimbangkan menaikkan kuota CPU bila rutin melonjak.")
DISK_TIP = ("Bersihkan: sudo du -xh --max-depth=2 / | sort -rh | head -20 | hapus log lama: "
            "sudo journalctl --vacuum-size=200M. Disk penuh bisa mematikan database & aplikasi.")
SWAP_TIP = ("RAM menipis sedang dibuang ke swap — dampak kinerja besar. Cek RAM & proses (lihat tips RAM).")

# Jendela tenang: masalah danger ditutup otomatis bila tidak ada deteksi/kejadian
# baru selama rentang ini (mencegah banner macet karena sisa data auth.log).
SECURITY_QUIET_SECS = 600      # keamanan: 10 menit tanpa percobaan baru
RESOURCE_QUIET_SECS = 60       # resource: 1 menit dalam kondisi normal
BG_PROBLEM_EVAL_SECS = 15      # interval evaluator background


def _quiet_secs_for(key: str) -> int:
    if key in ("security_danger", "failed_logins"):
        return SECURITY_QUIET_SECS
    if key.startswith(("ram_", "swap_", "cpu_", "disk_")):
        return RESOURCE_QUIET_SECS
    return 0


def _parse_extras_security(extras) -> dict:
    if not extras or not extras.security:
        return {}
    try:
        d = json.loads(extras.security)
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def _rollup_sys_hours(db, server_id):
    """Materialisasikan rollup per jam dari sys_snapshots (idempotent).

    Dipanggil tiap laporan agent; hanya memperbaiki "jam yang sudah lewat"
    (di bawah jam berjalan) yang belum ada di sys_snapshots_hourly, lalu
    memangkas metric service > 7 hari (prune mahal -> dibatasi tiap 24 jam).
    """
    global _last_metrics_prune
    now = datetime.utcnow()
    this_hour = now.replace(minute=0, second=0, microsecond=0)

    with _prune_lock:
        if now - _last_metrics_prune > timedelta(hours=24):
            mcut = now - timedelta(days=7)
            db.query(Metric).filter(Metric.timestamp < mcut).delete(synchronize_session=False)
            _last_metrics_prune = now

    latest = (
        db.query(func.max(SysSnapshotHour.bucket))
        .filter(SysSnapshotHour.server_id == server_id)
        .scalar()
    )
    bucket = latest + timedelta(hours=1) if latest else this_hour - timedelta(hours=24)
    while bucket < this_hour:
        nxt = bucket + timedelta(hours=1)
        agg = db.query(
            func.count(SystemSnapshot.id),
            func.avg(SystemSnapshot.cpu),
            func.max(SystemSnapshot.cpu),
            func.avg(SystemSnapshot.load1),
            func.avg(SystemSnapshot.load5),
            func.avg(SystemSnapshot.load15),
            func.max(SystemSnapshot.mem_total),
            func.avg(SystemSnapshot.mem_used),
            func.avg(SystemSnapshot.mem_avail),
            func.max(SystemSnapshot.swap_total),
            func.avg(SystemSnapshot.swap_used),
            func.avg(SystemSnapshot.procs),
        ).filter(
            SystemSnapshot.server_id == server_id,
            SystemSnapshot.timestamp >= bucket,
            SystemSnapshot.timestamp < nxt,
        ).one()
        if agg[0]:
            last_snap = (
                db.query(SystemSnapshot.disks)
                .filter(
                    SystemSnapshot.server_id == server_id,
                    SystemSnapshot.timestamp >= bucket,
                    SystemSnapshot.timestamp < nxt,
                )
                .order_by(desc(SystemSnapshot.timestamp))
                .first()
            )
            disk_max_pct = None
            if last_snap and last_snap.disks:
                try:
                    disks = json.loads(last_snap.disks)
                    disk_max_pct = max(
                        (d.get("pct") or 0) for d in disks if isinstance(d, dict)
                    ) or None
                except (TypeError, ValueError):
                    disk_max_pct = None
            db.add(SysSnapshotHour(
                server_id=server_id, bucket=bucket, samples=agg[0],
                cpu_avg=agg[1] or 0.0, cpu_max=agg[2] or 0.0,
                load1_avg=agg[3], load5_avg=agg[4], load15_avg=agg[5],
                mem_total=agg[6] or 0, mem_used_avg=agg[7] or 0,
                mem_avail_avg=agg[8] or 0, swap_total=agg[9] or 0,
                swap_used_avg=agg[10] or 0,
                procs_avg=int(agg[11]) if agg[11] is not None else None,
                disk_max_pct=disk_max_pct,
            ))
        bucket = nxt

    prune_h = now - timedelta(days=90)
    db.query(SysSnapshotHour).filter(
        SysSnapshotHour.server_id == server_id,
        SysSnapshotHour.bucket < prune_h,
    ).delete(synchronize_session=False)


SECURITY_TIPS = {
    "danger": ("Kemungkinan serangan SSH — blokir IP sumber "
               "(sudo iptables -A INPUT -s <ip> -j DROP), pasang fail2ban "
               "(sudo apt install fail2ban), ganti password akun, perketat sshd "
               "(PasswordAuthentication no + PubkeyAuthentication yes)."),
    "warning": "Login SSH gagal dalam jumlah mencurigakan — cek IP sumber & akun; blokir bila repetitif; pasang fail2ban.",
    "info": "Ada login SSH gagal — bisa typo password; tetap pantau aktivitas di halaman Aktivitas User.",
}
APT_TIP = ("Buka Rincian server lalu pilih Update OS atau Upgrade. "
           "Di server bisa juga manual: sudo apt update && sudo apt upgrade")
SVC_DOWN_TIP = ("Cek status: sudo systemctl status {name} | Balik hidupkan: "
                "sudo systemctl restart {name} | Log: journalctl -u {name} -n 50")
SVC_NODATA_TIP = "Pastikan service benar-benar ada & port terbuka (ss -tlnp); agen memindai ulang tiap siklus."
AGENT_STALE_TIP = ("Agen tidak melapor — mulai ulang: sudo systemctl restart agent_pantau | "
                   "Log: journalctl -u agent_pantau -n 30")


def _fmt_size(n: int | float | None) -> str:
    n = n or 0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _resource_problem_instances(db, srv) -> list:
    """Masalah hardware/performa: RAM/swap penuh, CPU jenuh, disk penuh.

    Data diambil dari snapshot real-time terbaru agen; diabaikan bila basi
    (agen sudah dianggap offline oleh indikator agent_stale).
    """
    inst: list = []
    now = datetime.utcnow()
    snaps = (
        db.query(SystemSnapshot)
        .filter(
            SystemSnapshot.server_id == srv.id,
            SystemSnapshot.timestamp >= now - timedelta(minutes=10),
        )
        .order_by(desc(SystemSnapshot.timestamp))
        .limit(12)
        .all()
    )
    if not snaps:
        return inst
    latest = snaps[0]
    if latest.timestamp < now - timedelta(seconds=FRESH_SNAP_SECS):
        return inst

    mem_total, mem_used = latest.mem_total or 0, latest.mem_used or 0
    if mem_total > 0:
        pct = mem_used / mem_total * 100
        if pct >= RAM_DANGER_PCT:
            inst.append({
                "key": "ram_critical", "severity": "danger",
                "message": (f"RAM HAMPIR PENUH: {pct:.0f}% "
                            f"({_fmt_size(mem_used)} / {_fmt_size(mem_total)})"),
                "tip": RAM_TIP,
            })
        elif pct >= RAM_WARNING_PCT:
            inst.append({
                "key": "ram_high", "severity": "warning",
                "message": (f"RAM tinggi: {pct:.0f}% "
                            f"({_fmt_size(mem_used)} / {_fmt_size(mem_total)})"),
                "tip": RAM_TIP,
            })

    swap_total, swap_used = latest.swap_total or 0, latest.swap_used or 0
    if swap_total > 0:
        spct = swap_used / swap_total * 100
        if spct >= SWAP_DANGER_PCT:
            inst.append({
                "key": "swap_critical", "severity": "danger",
                "message": f"Swap hampir penuh: {spct:.0f}% — RAM menipis",
                "tip": SWAP_TIP,
            })
        elif spct >= SWAP_WARNING_PCT:
            inst.append({
                "key": "swap_high", "severity": "warning",
                "message": f"Swap terpakai tinggi: {spct:.0f}%",
                "tip": SWAP_TIP,
            })

    cpu_vals = [s.cpu for s in snaps if s.cpu is not None]
    if cpu_vals:
        cpu_avg = sum(cpu_vals) / len(cpu_vals)
        cpu_max = max(cpu_vals)
        if cpu_avg >= CPU_DANGER_PCT:
            inst.append({
                "key": "cpu_saturated", "severity": "danger",
                "message": (f"CPU jenuh/saturasi: rata-rata {cpu_avg:.0f}% "
                            f"(puncak {cpu_max:.0f}%)"),
                "tip": CPU_TIP,
            })
        elif cpu_avg >= CPU_WARNING_PCT:
            inst.append({
                "key": "cpu_high", "severity": "warning",
                "message": f"CPU tinggi: rata-rata {cpu_avg:.0f}% (puncak {cpu_max:.0f}%)",
                "tip": CPU_TIP,
            })

    disks = None
    if latest.disks:
        try:
            disks = json.loads(latest.disks)
        except (TypeError, ValueError):
            disks = None
    for d in disks or []:
        mount = d.get("mount", "?")
        total, used = d.get("total") or 0, d.get("used") or 0
        if total <= 0:
            continue
        dpct = used / total * 100 if total else 0
        if dpct >= DISK_DANGER_PCT:
            inst.append({
                "key": f"disk_critical:{mount}", "severity": "danger",
                "message": f"Disk {mount} HAMPIR PENUH: {dpct:.0f}% ({_fmt_size(used)} / {_fmt_size(total)})",
                "tip": DISK_TIP,
            })
        elif dpct >= DISK_WARNING_PCT:
            inst.append({
                "key": f"disk_high:{mount}", "severity": "warning",
                "message": f"Disk {mount} terisi tinggi: {dpct:.0f}%",
                "tip": DISK_TIP,
            })
    return inst


def _problem_instances(srv, extras, svc_data, db=None) -> list:
    """Masalah yang sedang terjadi -> [{key,severity,message,tip}] (Zabbix-like)."""
    inst: list = []
    if db is not None:
        inst += _resource_problem_instances(db, srv)
    if srv.last_seen is None:
        return inst
    if _server_stale(srv):
        inst.append({"key": "agent_stale", "severity": "warning",
                     "message": "Agen tidak melapor (data kedaluwarsa)",
                     "tip": AGENT_STALE_TIP})
    if extras is not None:
        if (extras.apt_upgradable or 0) > 0:
            inst.append({"key": "apt_updates", "severity": "info",
                         "message": f"{extras.apt_upgradable} paket menunggu upgrade",
                         "tip": APT_TIP})
        sec = _parse_extras_security(extras)
        if sec:
            failed = int(sec.get("failed") or 0)
            invalid = int(sec.get("invalid_users") or 0)
            nips = len(sec.get("source_ips") or {})
            event_at = None
            if sec.get("last_seen"):
                try:
                    _dt = datetime.fromisoformat(str(sec["last_seen"]))
                    if _dt.tzinfo is not None:
                        _dt = _dt.astimezone(timezone.utc).replace(tzinfo=None)
                    event_at = _dt
                except (TypeError, ValueError):
                    event_at = None
            if event_at is None and extras is not None and extras.updated_at is not None:
                event_at = extras.updated_at  # fallback bila agen tak mengirim last_seen
            if invalid >= SECURITY_DANGER_INVALID or failed >= SECURITY_DANGER_FAILED:
                inst.append({"key": "security_danger", "severity": "danger",
                             "message": f"Kemungkinan serangan SSH: {failed} login gagal, "
                                        f"{invalid} user invalid, dari {nips} IP"
                                        + (f" · terakhir {_rel_dt(event_at)}" if event_at else ""),
                             "tip": SECURITY_TIPS["danger"], "event_at": event_at})
            elif failed >= SECURITY_WARNING_FAILED:
                inst.append({"key": "failed_logins", "severity": "warning",
                             "message": f"{failed} login SSH gagal dari {nips} IP"
                                        + (f" · terakhir {_rel_dt(event_at)}" if event_at else "")
                                        + " — waspada brute force",
                             "tip": SECURITY_TIPS["warning"], "event_at": event_at})
            elif failed >= 1:
                inst.append({"key": "failed_logins", "severity": "info",
                             "message": f"{failed} login SSH gagal (ringan)"
                                        + (f" · terakhir {_rel_dt(event_at)}" if event_at else ""),
                             "tip": SECURITY_TIPS["info"], "event_at": event_at})
    for d in svc_data or []:
        name = d.get("name", "?")
        st = d.get("status")
        if st == "down":
            inst.append({"key": f"service_down:{name}", "severity": "warning",
                         "message": f"Layanan {name} down",
                         "tip": SVC_DOWN_TIP.format(name=name)})
        elif st == "unknown":
            inst.append({"key": f"svc_no_data:{name}", "severity": "info",
                         "message": f"Layanan {name} belum ada data",
                         "tip": SVC_NODATA_TIP})
    return inst




def _fmt_duration(start: datetime, end: datetime) -> str:
    s = max(0, int((end - start).total_seconds()))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h} j {m} mnt"
    if m:
        return f"{m} mnt {sec} dtk"
    return f"{sec} dtk"


def _rel_dt(dt: datetime, now: datetime | None = None) -> str:
    """Waktu relatif (bebas zona waktu) untuk menampilkan aktivitas terakhir."""
    now = now or datetime.utcnow()
    s = int((now - dt).total_seconds())
    if s < 10:
        return "baru saja"
    if s < 60:
        return f"{s} dtk lalu"
    if s < 3600:
        return f"{s // 60} mnt lalu"
    if s < 86400:
        h, m = divmod(s // 60, 60)
        return f"{h} j {m} mnt lalu"
    return f"{s // 86400} h lalu"


def _problem_row2dict(row) -> dict:
    end = row.resolved_at
    return {
        "id": row.id,
        "key": row.key, "severity": row.severity, "message": row.message,
        "tip": row.tip, "started_at": row.started_at, "resolved_at": end,
        "is_open": end is None,
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": row.acknowledged_at,
        "resolved_note": row.resolved_note,
        "durasi": _fmt_duration(row.started_at, end if end else datetime.utcnow()),
    }


def sync_server_problems(db, srv, instances, keep_history=40, now=None):
    """Rekonsiliasi masalah dengan tabel server_problems (mirip evaluasi Zabbix).

    - Instance baru  -> insert terbuka (started_at=now, last_active_at).
    - Masih ada      -> perbarui severity/message/tip; majukan last_active_at.
    - Tidak ada lagi -> tandai resolved_at=now; untuk tipe berjendela-tenang,
      hanya bila sudah tenang >= jendela (resolved_note='auto').
    - Kejadian berbasis (keamanan): instans tertutup otomatis bila kejadian
      terakhir lebih tua dari jendela tenang (sisa data auth.log tidak macetkan banner).
    Arsip teratasi > 30 hari dihapus. Kembalikan (level, open, history).
    """
    now = now or datetime.utcnow()
    if getattr(srv, "is_maintenance", 0):
        m_until = getattr(srv, "maintenance_until", None)
        if m_until and m_until < now:
            srv.is_maintenance = 0
            srv.maintenance_until = None
            srv.maintenance_reason = None
            db.commit()
        else:
            instances = []
    current_keys = {p["key"] for p in instances}

    for p in instances:
        quiet = _quiet_secs_for(p["key"])
        ev = p.get("event_at")
        row = (
            db.query(ServerProblem).filter(
                ServerProblem.server_id == srv.id,
                ServerProblem.key == p["key"],
                ServerProblem.resolved_at.is_(None),
            ).first()
        )
        if quiet > 0 and ev is not None and (now - ev).total_seconds() >= quiet:
            # Sudah tenang melebihi jendela -> tutup otomatis (jangan buka baru).
            if row is not None:
                row.resolved_at = now
                row.updated_at = now
                row.resolved_note = "auto"
            continue
        active = max(ev, now) if ev else now
        if row is None:
            db.add(ServerProblem(
                server_id=srv.id, key=p["key"], severity=p["severity"],
                message=p["message"], tip=p["tip"], started_at=now,
                last_active_at=active,
            ))
        else:
            if active > (row.last_active_at or row.started_at):
                row.last_active_at = active
            if (row.severity != p["severity"] or row.message != p["message"]
                    or row.tip != p["tip"]):
                row.severity, row.message, row.tip = p["severity"], p["message"], p["tip"]
            row.updated_at = now

    for row in (
        db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).all()
    ):
        if row.key in current_keys:
            continue
        quiet = _quiet_secs_for(row.key)
        last = row.last_active_at or row.started_at
        if quiet <= 0 or (now - last).total_seconds() >= quiet:
            row.resolved_at = now
            row.updated_at = now
            row.resolved_note = "auto" if quiet > 0 else None

    stale = now - timedelta(days=30)
    db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.resolved_at.isnot(None),
        ServerProblem.resolved_at < stale,
    ).delete(synchronize_session=False)
    db.commit()  # Simpan pembaruan status problem ke database agar ID valid saat di-ack/resolve

    open_rows = (
        db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).order_by(desc(ServerProblem.started_at)).all()
    )
    history = (
        db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.isnot(None),
        ).order_by(desc(ServerProblem.resolved_at)).limit(keep_history).all()
    )
    level = "ok"
    if open_rows:
        level = max((r.severity for r in open_rows),
                    key=lambda x: PROBLEM_RANK.get(x, 0))
    cutoff_24 = now - timedelta(hours=24)
    counts: dict = {}
    for r in db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.started_at >= cutoff_24,
    ).all():
        counts[r.key] = counts.get(r.key, 0) + 1
    open_list = [_problem_row2dict(r) for r in open_rows]
    hist_list = [_problem_row2dict(r) for r in history]
    for d in open_list + hist_list:
        d["count_24h"] = counts.get(d["key"], 0)
    return level, open_list, hist_list


def _agg_row(srv, row, counts=None) -> dict:
    d = _problem_row2dict(row)
    d.update({"server_id": srv.id, "hostname": srv.hostname})
    if counts:
        d["count_24h"] = counts.get(row.key, 0)
    return d


def problems_aggregate(db):
    """Daftar masalah semua server untuk halaman /problems.

    Kembalikan (open_list, recent_resolved), urut severity lalu waktu.
    """
    extras_map = {e.server_id: e for e in db.query(ServerExtras).all()}
    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    cutoff_24 = datetime.utcnow() - timedelta(hours=24)
    open_list: list = []
    resolved_list: list = []
    for srv in servers:
        ex = extras_map.get(srv.id)
        services = db.query(Service).filter(Service.server_id == srv.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_data = []
        for svc in services:
            latest = latest_map.get(svc.id)
            svc_data.append({"name": svc.service_name,
                             "status": latest.status if latest else "unknown"})
        if _server_stale(srv):
            for d in svc_data:
                d["status"] = "offline"
        sync_server_problems(db, srv, _problem_instances(srv, ex, svc_data, db))
        counts = {}
        for r in db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.started_at >= cutoff_24,
        ).all():
            counts[r.key] = counts.get(r.key, 0) + 1
        for r in db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).all():
            open_list.append(_agg_row(srv, r, counts))
        for r in db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.isnot(None),
            ServerProblem.resolved_at >= cutoff_24,
        ).all():
            resolved_list.append(_agg_row(srv, r, counts))
    rank = {"danger": 3, "warning": 2, "info": 1}
    open_list.sort(key=lambda r: (rank.get(r["severity"], 0), r["started_at"]),
                   reverse=True)
    resolved_list.sort(key=lambda r: r["resolved_at"], reverse=True)
    return open_list, resolved_list


def _server_stale(srv) -> bool:
    """True bila server belum melapor terlalu lama / tidak pernah melapor."""
    ls = srv.last_seen
    if ls is None:
        return True
    if ls.tzinfo is None:
        ls = ls.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ls).total_seconds() > OFFLINE_AFTER_SECONDS


def _server_status(srv, stale: bool, has_services: bool, any_up: bool):
    """Status server dalam satu kosakata untuk semua halaman.

    Kembalikan (label, kelas_badge) supaya Dashboard, Servers, dan Rincian
    tidak lagi berbeda-beda menampilkan server yang sama.
    """
    if not srv.is_active:
        return "nonaktif", "badge-muted"
    if stale:
        return ("offline", "badge-down") if srv.last_seen else ("belum ada data", "badge-muted")
    if not has_services:
        # agen melapor normal, hanya belum ada service yang terdeteksi
        return "online", "badge-up"
    return ("online", "badge-up") if any_up else ("service down", "badge-down")


# ---------------------------------------------------------------------------
# AUDIT LOG
# ---------------------------------------------------------------------------
AUDIT_ACTION_LABELS = {
    "login": "Login",
    "server_add": "Tambah server",
    "server_edit": "Ubah server",
    "server_delete": "Hapus server",
    "key_regenerate": "Regenerasi API key",
    "service_add": "Tambah service",
    "service_delete": "Hapus service",
    "user_add": "Tambah user",
    "user_delete": "Hapus user",
    "apt_update": "Apt update",
    "apt_upgrade": "Apt upgrade",
    "apt_upgrade_interact": "Apt upgrade (interaktif)",
    "alert_ack": "Akui peringatan (alert)",
    "cmd:restart": "Restart service",
    "cmd:block_ip": "Blokir IP",
    "cmd:restart_agent": "Restart agen",
    "cmd:reboot_host": "Reboot server",
    "cmd:poweroff_host": "Power off server",
    "cmd:start": "Start service",
    "cmd:stop": "Stop service",
}
AUDIT_ACTION_SET = dict(AUDIT_ACTION_LABELS)


def _audit_rows(db, limit: int = 250, q: str = "", action: str = ""):
    """Gabungkan jejak audit_logs + tabel commands (aksi remote), urut turun waktu."""
    q = (q or "").strip().lower()
    rows: list[dict] = []

    items = (
        db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit).all()
    )
    for a in items:
        rows.append({
            "t": a.created_at, "user": a.username, "kind": "log",
            "label": AUDIT_ACTION_LABELS.get(a.action, a.action),
            "key": a.action,
            "target": a.target or "-", "status": None, "result": a.result or "",
        })

    server_map = {s.id: s.hostname for s in db.query(Server).all()}
    svc_map = {s.id: s.service_name for s in db.query(Service).all()}
    cmds = (
        db.query(Command).order_by(desc(Command.created_at)).limit(limit).all()
    )
    label_map = {
        "restart": "cmd:restart", "start": "cmd:start", "stop": "cmd:stop",
        "block_ip": "cmd:block_ip", "restart_agent": "cmd:restart_agent",
        "reboot_host": "cmd:reboot_host", "poweroff_host": "cmd:poweroff_host",
    }
    for c in cmds:
        key = label_map.get(c.action, f"cmd:{c.action}")
        target = server_map.get(c.server_id, f"server#{c.server_id}")
        if c.service_id and c.service_id in svc_map:
            target += f" · {svc_map[c.service_id]}"
        if c.action == "block_ip" and c.params:
            try:
                ps = json.loads(c.params)
                ips = ps.get("ips") or []
                if ips:
                    target += f" ({', '.join(str(i) for i in ips[:3])}{'…' if len(ips) > 3 else ''})"
            except (TypeError, ValueError):
                pass
        status = (c.status or "").upper()
        short = (c.result or "").strip()
        if len(short) > 90:
            short = short[:90] + "…"
        rows.append({
            "t": c.created_at, "user": c.issued_by or "-", "kind": "cmd",
            "key": key,
            "label": AUDIT_ACTION_LABELS.get(key, c.action),
            "target": target, "status": status, "result": short,
        })

    if q:
        rows = [r for r in rows if q in " ".join(
            [r["user"], r["label"], r["target"], r["result"]]).lower()]
    if action and AUDIT_ACTION_SET.get(action):
        rows = [r for r in rows if r["key"] == action]
    rows.sort(key=lambda r: r["t"], reverse=True)
    return rows[:limit]


@app.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request, db: Session = Depends(get_db),
    q: str = "", action: str = "",
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role != "admin":
        return RedirectResponse("/", status_code=303)
    rows = _audit_rows(db, limit=250, q=q, action=action)
    return tpl(request, "audit.html", {
        "user": user, "rows": rows,
        "q": q, "action": action,
        "actions": sorted(AUDIT_ACTION_LABELS.items()),
    })


# ---------------------------------------------------------------------------
# ALERT DANGER (popup yang tidak bisa diabaikan)
# ---------------------------------------------------------------------------
def _alert_dict(row, hostname: str, now: datetime) -> dict:
    return {
        "id": row.id,
        "server_id": row.server_id,
        "hostname": hostname,
        "key": row.key,
        "severity": row.severity,
        "message": row.message,
        "tip": row.tip,
        "started_at": row.started_at.isoformat(),
        "durasi": _fmt_duration(row.started_at, now),
        "acknowledged": row.acknowledged_at is not None,
        "acknowledged_by": row.acknowledged_by,
    }


@app.get("/api/alerts")
def api_alerts(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Danger terbuka. `alerts` = belum diakui (harus dimunculkan), sisanya rangkuman."""
    now = datetime.utcnow()
    host = {s.id: s.hostname for s in db.query(Server).all()}
    open_danger = (
        db.query(ServerProblem)
        .filter(
            ServerProblem.severity == "danger",
            ServerProblem.resolved_at.is_(None),
        )
        .order_by(desc(ServerProblem.started_at)).all()
    )
    alerts = [_alert_dict(r, host.get(r.server_id, "?"), now)
              for r in open_danger if r.acknowledged_at is None]
    return {
        "alerts": alerts,
        "unack_count": len(alerts),
        "open_danger_count": len(open_danger),
        "acked_count": len(open_danger) - len(alerts),
    }


@app.post("/api/alerts/{pid}/ack")
def api_alert_ack(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Acknowledge peringatan (semua level) agar tidak mengganggu terus-menerus."""
    _verify_csrf_header(request)
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Peringatan tidak ditemukan")
    row.acknowledged_at = datetime.utcnow()
    row.acknowledged_by = user.username
    db.add(AuditLog(
        username=user.username, action="alert_ack",
        target=f"{row.key} ({row.message[:60]})", result="diakui",
    ))
    db.commit()
    return {"ok": True, "id": pid, "acknowledged_by": user.username}


@app.post("/api/alerts/{pid}/resolve")
def api_alert_resolve(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Tandai masalah selesai/teratasi secara manual oleh admin/user."""
    _verify_csrf_header(request)
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Masalah tidak ditemukan")
    now = datetime.utcnow()
    row.resolved_at = now
    row.resolved_note = f"manual ({user.username})"
    row.acknowledged_at = row.acknowledged_at or now
    row.acknowledged_by = row.acknowledged_by or user.username
    db.add(AuditLog(
        username=user.username, action="problem_resolve",
        target=f"{row.key} ({row.message[:60]})", result="diselesaikan manual",
    ))
    db.commit()
    return {"ok": True, "id": pid, "resolved_by": user.username}




def _journal_tail(unit: str, lines: int) -> list:
    try:
        p = subprocess.run(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return [f"[gagal membaca journal: {e}]"]
    out = p.stdout.rstrip().splitlines()
    if not out:
        msg = p.stderr.strip() or f"tidak ada entri untuk unit {unit}"
        return [f"[{msg}]"]
    return out[-lines:]


def _journal_boot_tail(lines: int) -> list:
    try:
        p = subprocess.run(
            ["journalctl", "-b", "-n", str(lines), "--no-pager", "-o", "short-iso"],
            capture_output=True, text=True, errors="replace", timeout=20,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        return [f"[gagal membaca journal: {e}]"]
    return p.stdout.rstrip().splitlines()[-lines:] or ["[journal boot kosong]"]


@app.get("/api/logs/services")
def api_logs_services(user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Daftar unit service aktif + mode file untuk dropdown log."""
    units = []
    try:
        p = subprocess.run(
            ["systemctl", "list-units", "--type=service", "--state=running",
             "--no-pager", "--no-legend"],
            capture_output=True, text=True, timeout=15,
        )
        for line in p.stdout.splitlines():
            s = line.split()
            if s and s[0].endswith(".service") and VALID_UNIT_RE.match(s[0][:-8]):
                units.append(s[0][:-8])
    except (subprocess.TimeoutExpired, OSError):
        pass
    return {"units": sorted(set(units)), "extras": ["SYSLOG", "AUTH", "SYSTEM"]}


@app.get("/api/logs/service")
def api_logs_service(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    unit: str = "mariadb",
    lines: int = 300,
):
    lines = max(10, min(lines, 2000))
    if unit == "SYSLOG":
        return {"unit": unit, "lines": tail_lines(SYSLOG_FILE, lines) or [f"[file {SYSLOG_FILE} tak dapat dibaca]"]}
    if unit == "AUTH":
        return {"unit": unit, "lines": tail_lines(AUTH_FILE, lines) or [f"[file {AUTH_FILE} tak dapat dibaca]"]}
    if unit == "SYSTEM":
        return {"unit": unit, "lines": _journal_boot_tail(lines)}
    if not VALID_UNIT_RE.match(unit):
        raise HTTPException(status_code=400, detail="Invalid unit name")
    return {"unit": unit, "lines": _journal_tail(unit, lines)}


# ---------------------------------------------------------------------------
# PUBLIC (agent): ambil permintaan log layanan & kirim hasil
# ---------------------------------------------------------------------------
@app.get("/api/logs/pending")
def api_logs_pending(
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent mem-poll permintaan log yang masih pending untuk servernya."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    _expire_stale_logs(db, server.id)

    pending = (
        db.query(LogRequest)
        .filter(LogRequest.server_id == server.id, LogRequest.status == "pending")
        .order_by(LogRequest.created_at)
        .limit(10)
        .all()
    )
    return {
        "requests": [
            {"id": r.id, "unit": r.unit, "lines": r.lines, "detail": r.detail} for r in pending
        ]
    }


def _expire_stale_logs(db: Session, server_id: int):
    """Expire permintaan log yang menggantung terlalu lama (agent offline)."""
    cutoff = datetime.utcnow() - timedelta(seconds=STALE_LOG_SECONDS)
    stale = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == server_id,
            LogRequest.status.in_(["pending", "executing"]),
            LogRequest.unit.notin_(INTERACTIVE_UNITS),
            LogRequest.created_at < cutoff,
        )
        .all()
    )
    for r in stale:
        r.status = "failed"
        r.result = "timeout: agen tidak merespons"
        r.updated_at = datetime.utcnow()

    # Expire sesi SHELL yang sudah mati / agen tidak lagi polling input
    shell_cutoff = datetime.utcnow() - timedelta(seconds=25)
    stale_shells = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == server_id,
            LogRequest.unit == SHELL_UNIT,
            LogRequest.status.in_(["pending", "executing"]),
            (LogRequest.updated_at < shell_cutoff) | (LogRequest.created_at < shell_cutoff),
        )
        .all()
    )
    for r in stale_shells:
        r.status = "failed"
        r.result = (r.result or "").strip() + "\n[sesi shell terputus: tidak ada respons dari agen]"
        r.updated_at = datetime.utcnow()

    if stale or stale_shells:
        db.commit()


@app.post("/api/logs/{rid}/status")
def api_logs_status(
    rid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent menandai permintaan log sedang diproses."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if body.get("status") != "executing":
        raise HTTPException(status_code=400, detail="Status must be 'executing'")
    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")
    req.status = "executing"
    req.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@app.post("/api/logs/{rid}/progress")
def api_logs_progress(
    rid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent mengirim chunk output saat proses panjang (apt update/upgrade).

    Chunk diakumulasi ke kolom `result` supaya UI bisa menampilkan progres
    live sambil polling; status tetap 'executing' sampai hasil final datang.
    """
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    chunk = body.get("chunk")
    if chunk is None:
        raise HTTPException(status_code=400, detail="chunk required")
    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")
    if req.status != "executing":
        return {"ok": True, "ignored": True}  # proses sudah selesai/kedaluwarsa

    new_result = str(chunk) if body.get("replace") else (req.result or "") + str(chunk)
    # stream terminal: CR + warna SGR harus utuh (dirender ulang di UI)
    req.result = _clean_terminal(new_result, APT_STREAM_MAXCHARS, APT_STREAM_MAXLINES)
    req.updated_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@app.post("/api/logs/{rid}/input")
def api_logs_input(
    rid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    """Admin mengirim jawaban untuk proses apt yang sedang berjalan (mode interaktif).

    Jawaban disimpan di `input_data`; agent mengambilnya lewat GET
    /api/logs/{rid}/input (khusus agen, pakai X-Api-Key) lalu menulis ke stdin
    proses. Jawaban selalu diakhiri baris baru; pty menerjemahkannya jadi
    tombol Enter. Jawaban kosong = Enter saja (pakai pilihan bawaan dpkg).
    """
    req = db.query(LogRequest).filter(LogRequest.id == rid).first()
    if not req:
        raise HTTPException(status_code=404, detail="Permintaan tidak ditemukan")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Hanya admin")
    if req.status != "executing" or req.unit not in INTERACTIVE_UNITS:
        raise HTTPException(status_code=409, detail="Proses tidak sedang berjalan")

    raw = body.get("data")
    if not isinstance(raw, str):
        raise HTTPException(status_code=400, detail="data harus string")

    if req.unit == SHELL_UNIT:
        # Sesi shell: ini byte mentah untuk pty, bukan "jawaban". Jadi apa
        # adanya diteruskan - Enter, Tab, panah (ESC [ A), Ctrl+C (0x03),
        # Ctrl+D (0x04) semuanya berarti. Tidak ada baris baru yang disisipkan
        # (Ctrl+C tidak boleh mengirim perintah) dan tidak ada karakter yang
        # "dibersihkan", karena cleaning justru merusak terminal sungguhan.
        # Yang dibuang hanya NUL dan byte C1 yang bisa merusak kolom TEXT.
        # (Nama variabel 'raw', bukan 'text': text = sqlalchemy.text.)
        raw = "".join(ch for ch in raw if ch != "\x00" and not "\x80" <= ch <= "\x9f")
        if len(raw) > SHELL_INPUT_MAX:
            raw = raw[-SHELL_INPUT_MAX:]
        if not raw:
            return {"ok": True}
        # Ditumpuk, bukan ditimpa: admin mengetik cepat, agent mengambil
        # setiap ~350ms, jadi dua POST bisa jatuh di sela yang sama.
        # Penumpukan dilakukan dalam SATU pernyataan SQL (CONCAT) supaya dua
        # POST yang benar-benar bersamaan tidak saling menimpa - kalau
        # read-modify-write di sisi Python, ketikan bisa hilang.
        # Syarat panjang menjaga antrean tidak tumbuh tanpa batas saat shell
        # macet (paste raksasa saat shell tidak lagi membaca).
        db.execute(
            text(
                "UPDATE log_requests SET input_queue = CONCAT("
                "COALESCE(input_queue, ''), :chunk) "
                "WHERE id = :rid AND CHAR_LENGTH(COALESCE(input_queue, '')) "
                "+ CHAR_LENGTH(:chunk) <= :cap"
            ),
            {"chunk": raw, "rid": rid, "cap": SHELL_INPUT_MAX},
        )
    else:
        # Buang karakter kontrol (kecuali baris baru/tab) agar admin tidak
        # bisa menyuntik perintah lain ke terminal yang sedang berjalan.
        cleaned = _CLEAN_CTRL_RE.sub("", raw.replace("\r", ""))
        cleaned = cleaned.replace("\n", "").replace("\t", " ")[:200].strip()
        # Jawaban kosong = tekan Enter saja -> pakai pilihan bawaan dpkg.
        req.input_data = (cleaned + "\n") if cleaned else "\n"
    req.input_at = datetime.utcnow()
    req.updated_at = req.input_at
    db.commit()
    return {"ok": True}


@app.get("/api/logs/{rid}/input")
def api_logs_input_take(
    rid: int,
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Ambil input admin (sekali ambil lalu dikosongkan). Dipanggil agent."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if _req_is_shell(db, rid, server.id):
        # Ambil seluruh antrean raw sekaligus. SELECT ... FOR UPDATE mengunci
        # baris supaya ketikan yang masuk bersamaan tidak hilang di antara
        # "baca" dan "kosongkan".
        row = db.execute(
            text("SELECT input_queue FROM log_requests WHERE id=:rid FOR UPDATE"),
            {"rid": rid},
        ).first()
        data = row[0] if row and row[0] else None
        if data:
            db.execute(text("UPDATE log_requests SET input_queue=NULL, input_at=NULL WHERE id=:rid"),
                      {"rid": rid})
            db.commit()
        return {"data": data}

    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req or not req.input_data or req.status != "executing":
        return {"data": None}
    data = req.input_data
    req.input_data = None      # sekali ambil: mencegah pengiriman berulang
    req.input_at = None
    db.commit()
    return {"data": data}


@app.post("/api/logs/{rid}/result")
def api_logs_result(
    rid: int,
    request: Request,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agent melaporkan hasil pembacaan log untuk satu permintaan."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    status = body.get("status")
    if status not in ("success", "failed"):
        raise HTTPException(status_code=400, detail="Status must be 'success' or 'failed'")
    req = db.query(LogRequest).filter(
        LogRequest.id == rid, LogRequest.server_id == server.id
    ).first()
    if not req:
        raise HTTPException(status_code=404, detail="Log request not found")

    req.status = status
    clean = _clean_terminal if req.unit in INTERACTIVE_UNITS else _clean_result
    req.result = clean(body.get("result"), APT_STREAM_MAXCHARS, APT_STREAM_MAXLINES)
    req.updated_at = datetime.utcnow()

    # Sesi shell ditutup: jangan simpan sisa input tak terpakai.
    if req.unit == SHELL_UNIT and (req.input_data or req.input_queue):
        req.input_data = None
        req.input_queue = None
        req.input_at = None

    # Segera sinkronkan status apt ke ServerExtras agar dashboard & tombol upgrade langsung aktif tanpa jeda
    if req.unit in ("APT_UPDATE", "APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE", "APT_FIX") and status == "success":
        try:
            raw_res = body.get("result", "")
            parsed = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            if isinstance(parsed, dict) and "apt" in parsed:
                apt_info = parsed.get("apt")
                if isinstance(apt_info, dict):
                    extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
                    if not extras:
                        extras = ServerExtras(server_id=server.id)
                        db.add(extras)
                    if "upgradable" in apt_info:
                        extras.apt_upgradable = _clamp_int(apt_info.get("upgradable"), 0)
                    if "packages" in apt_info and isinstance(apt_info["packages"], list):
                        extras.apt_packages_json = json.dumps(apt_info["packages"][:200])
                    extras.apt_last_update = datetime.utcnow()
        except Exception as exc:
            logger.warning("[apt_result_sync] Gagal sinkronkan ServerExtras: %s", exc)

    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# USER API: akses data kinerja + akun + permintaan log
# ---------------------------------------------------------------------------
@app.get("/api/servers/{sid}/perf")
def api_server_perf(
    sid: int,
    range: str = "24h",  # pylint: disable=redefined-builtin
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Riwayat kinerja sistem utk grafik: gabungan rollup per jam + snapshot mentalah.

    Rentang > 24 jam memakai sys_snapshots_hourly (histori), sisanya memakai
    sys_snapshots yang di-downsample lewat SQL. Mengembalikan poin ascending.
    """
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    span = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
        "30d": timedelta(days=30),
    }.get(range)
    if not span:
        raise HTTPException(status_code=400, detail="Rentang tidak dikenal")

    now = datetime.utcnow()
    start = now - span
    # Jam terakhir yang sudah selesai dipandu (anchor pemisah historis vs mentah)
    anchor = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    points: list[dict] = []

    if start < anchor:
        hour_rows = (
            db.query(SysSnapshotHour)
            .filter(
                SysSnapshotHour.server_id == sid,
                SysSnapshotHour.bucket >= start,
                SysSnapshotHour.bucket < anchor,
            )
            .order_by(SysSnapshotHour.bucket)
            .all()
        )
        points = [
            {
                "t": int(h.bucket.timestamp()),
                "cpu": round(h.cpu_avg, 1),
                "load": round(h.load1_avg, 2) if h.load1_avg is not None else None,
                "mem_used": h.mem_used_avg,
                "mem_total": h.mem_total,
                "swap_used": h.swap_used_avg,
                "swap_total": h.swap_total,
                "disk": round(h.disk_max_pct, 1) if h.disk_max_pct is not None else None,
            }
            for h in hour_rows
        ]
        raw_from = anchor
    else:
        raw_from = start

    # Snapshot mentalah terbaru, di-downsample per bucket waktu (SQL).
    step_secs = max(int(span.total_seconds() / 120), 30)
    raw = (
        db.query(
            (func.floor(func.unix_timestamp(SystemSnapshot.timestamp) / step_secs)
             * step_secs).label("tb"),
            func.avg(SystemSnapshot.cpu),
            func.avg(SystemSnapshot.load1),
            func.max(SystemSnapshot.mem_total),
            func.avg(SystemSnapshot.mem_used),
            func.max(SystemSnapshot.swap_total),
            func.avg(SystemSnapshot.swap_used),
            func.max(SystemSnapshot.disks),
        )
        .filter(
            SystemSnapshot.server_id == sid,
            SystemSnapshot.timestamp >= raw_from,
            SystemSnapshot.timestamp <= now,
        )
        .group_by("tb")
        .order_by("tb")
        .all()
    )

    def _parse_disks(raw_json):
        if not raw_json:
            return []
        try:
            val = json.loads(raw_json)
            return val if isinstance(val, list) else []
        except Exception:
            return []

    points.extend([
        {
            "t": int(tb_stamp),
            "cpu": round(cpu_avg, 1) if cpu_avg is not None else None,
            "load": round(load_avg, 2) if load_avg is not None else None,
            "mem_used": mem_used,
            "mem_total": mem_total,
            "swap_used": swap_used,
            "swap_total": swap_total,
            "disks": _parse_disks(disks_raw),
        }
        for tb_stamp, cpu_avg, load_avg, mem_total, mem_used, swap_total, swap_used, disks_raw in raw
    ])

    return {
        "server_id": sid,
        "range": range,
        "from": start.isoformat(),
        "to": now.isoformat(),
        "points": points,
    }


@app.get("/api/servers/{sid}/services/{svc_id}/history")
def api_service_history(
    sid: int, svc_id: int,
    range: str = "24h",  # pylint: disable=redefined-builtin
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Riwayat metric service (status, koneksi, waktu respon) utk grafik layanan."""
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")

    span = {
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }.get(range)
    if not span:
        raise HTTPException(status_code=400, detail="Rentang tidak dikenal")

    now = datetime.utcnow()
    step_secs = max(int(span.total_seconds() / 120), 30)
    rows = (
        db.query(
            (func.floor(func.unix_timestamp(Metric.timestamp) / step_secs)
             * step_secs).label("tb"),
            func.count(Metric.id),
            getattr(func, "if")(Metric.status == "up", 1, 0),
            func.avg(Metric.active_connections),
            func.avg(Metric.response_time_ms),
        )
        .filter(
            Metric.service_id == svc_id,
            Metric.timestamp >= now - span,
            Metric.timestamp <= now,
        )
        .group_by("tb")
        .order_by("tb")
        .all()
    )
    points = []
    for tb, n, ups, conns, rt in rows:
        up_ratio = (ups / n) if n else None
        points.append({
            "t": int(tb),
            "up_ratio": round(up_ratio, 3) if up_ratio is not None else None,
            "samples": int(n),
            "conns": round(conns, 1) if conns is not None else 0,
            "rt": round(rt, 1) if rt is not None else None,
        })

    latest = (
        db.query(Metric).filter(Metric.service_id == svc_id)
        .order_by(desc(Metric.timestamp)).first()
    )
    return {
        "server_id": sid,
        "service": {"id": svc.id, "name": svc.service_name, "port": svc.port},
        "range": range,
        "now": {
            "status": latest.status if latest else "unknown",
            "connections": latest.active_connections if latest else 0,
            "response_time_ms": latest.response_time_ms if latest else None,
        },
        "points": points,
    }


@app.get("/api/servers/{sid}/system")
def api_server_system(
    sid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Snapshot HW/jaringan terbaru + riwayat singkat + akun + unit layanan."""
    server = (
        db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    )
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    latest = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(desc(SystemSnapshot.timestamp))
        .first()
    )
    series = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(desc(SystemSnapshot.timestamp))
        .limit(60)
        .all()
    )
    series = list(reversed(series))

    def parse_list(raw):
        try:
            obj = json.loads(raw) if raw else None
        except (TypeError, ValueError):
            obj = None
        return obj if isinstance(obj, list) else []

    return {
        "server_id": sid,
        "ts": latest.timestamp.isoformat() if latest else None,
        "system": {
            "cpu": round(latest.cpu, 1) if latest else None,
            "load1": round(latest.load1, 2) if latest else None,
            "load5": round(latest.load5, 2) if latest else None,
            "load15": round(latest.load15, 2) if latest else None,
            "mem_total": latest.mem_total if latest else None,
            "mem_used": latest.mem_used if latest else None,
            "mem_avail": latest.mem_avail if latest else None,
            "swap_total": latest.swap_total if latest else None,
            "swap_used": latest.swap_used if latest else None,
            "procs": latest.procs if latest else None,
            "uptime": latest.uptime_secs if latest else None,
            "disks": parse_list(latest.disks) if latest else [],
            "net": parse_list(latest.net) if latest else [],
        },
        "series": [
            {
                "ts": s.timestamp.isoformat(),
                "cpu": round(s.cpu, 1),
                "mem_used": s.mem_used,
                "mem_total": s.mem_total,
                "load1": round(s.load1, 2) if s.load1 is not None else None,
            }
            for s in series
        ],
        "kernel": (extra.kernel if extra else None),
        "os_label": (extra.os_label if extra else None),
        "units": parse_list(extra.units if extra else None),
        "accounts": parse_list(extra.accounts if extra else None),
        "apt_upgradable": (extra.apt_upgradable if extra else None),
        "apt_last_update": (extra.apt_last_update.isoformat()
                            if extra and extra.apt_last_update else None),
        "apt_packages": parse_list(extra.apt_packages if extra else None),
        "extras": ["SYSLOG", "AUTH"],
    }


@app.post("/api/logs/request")
def api_logs_request(
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Buat permintaan log layanan (dieksekusi agent klien)."""
    _verify_csrf_header(request)
    sid = _clamp_int(body.get("server_id"), None, 0, 2 ** 31 - 1)
    unit = _clean_str(body.get("unit"), "", 100)
    lines = _clamp_int(body.get("lines"), 200, 10, 2000)
    detail = _clean_str(body.get("detail"), "", 128)
    if detail and not VALID_UNIT_RE.match(detail):
        raise HTTPException(status_code=400, detail="Invalid detail")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    if not VALID_UNIT_RE.match(unit):
        raise HTTPException(status_code=400, detail="Invalid unit name")

    is_apt = unit in APT_UNITS
    is_shell = unit == SHELL_UNIT
    if (is_apt or is_shell) and user.role != "admin":
        raise HTTPException(
            status_code=403,
            detail="Terminal Bawaan & Update/Upgrade hanya untuk admin",
        )
    if is_apt:
        busy = (
            db.query(LogRequest)
            .filter(
                LogRequest.server_id == sid,
                LogRequest.unit.in_(APT_UNITS),
                LogRequest.status.in_(["pending", "executing"]),
            )
            .first()
        )
        if busy:
            raise HTTPException(status_code=409, detail="Proses apt lain masih berjalan")
    if is_shell:
        busy = (
            db.query(LogRequest)
            .filter(
                LogRequest.server_id == sid,
                LogRequest.unit == SHELL_UNIT,
                LogRequest.status.in_(["pending", "executing"]),
            )
            .first()
        )
        if busy:
            stale_limit = datetime.utcnow() - timedelta(seconds=20)
            is_stale = (busy.updated_at and busy.updated_at < stale_limit) or (busy.created_at < stale_limit and busy.status == "pending")
            if is_stale or body.get("force"):
                busy.status = "failed"
                busy.result = (busy.result or "").strip() + "\n[sesi shell lama ditutup untuk membuka sesi baru]"
                busy.updated_at = datetime.utcnow()
                db.commit()
            else:
                raise HTTPException(status_code=409, detail="Sesi shell sudah terbuka di server ini")

    _expire_stale_logs(db, sid)

    logreq = LogRequest(server_id=sid, unit=unit, lines=lines, detail=detail or None)
    db.add(logreq)
    if is_apt:
        _audit(db, user.username, f"apt_{unit.removeprefix('APT_').lower()}",
               server.hostname, "dikirim ke agen")
    elif is_shell:
        # Terminal Bawaan = root shell. Catat SIAPA membuka sesi di server mana.
        _audit(db, user.username, "terminal_shell_open", server.hostname,
               "membuka Terminal Bawaan (shell root)")
    db.commit()
    db.refresh(logreq)

    # Bersihkan permintaan lama yang sudah selesai (maks 100/server)
    done = (
        db.query(LogRequest)
        .filter(
            LogRequest.server_id == sid,
            LogRequest.status.in_(["success", "failed"]),
        )
        .order_by(desc(LogRequest.created_at))
        .offset(100)
        .all()
    )
    for d in done:
        db.delete(d)
    db.commit()
    return {"id": logreq.id}


@app.get("/api/logs/request/{rid}")
def api_logs_request_status(
    rid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Status & hasil permintaan log untuk polling UI."""
    logreq = db.query(LogRequest).filter(LogRequest.id == rid).first()
    if not logreq:
        raise HTTPException(status_code=404, detail="Log request tidak ditemukan")
    server = db.query(Server.id).filter(Server.id == logreq.server_id).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    return {
        "id": logreq.id,
        "status": logreq.status,
        "result": logreq.result,
    }


# ---------------------------------------------------------------------------
# FILE MANAGER (Berkas) - Live RPC ke Agen via HTTP Long-Poll
# ---------------------------------------------------------------------------
class FileManagerDispatcher:
    def __init__(self):
        self._pending: dict[int, list[dict]] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._waiters: dict[str, asyncio.Future] = {}
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_or_create_event(self, server_id: int) -> asyncio.Event:
        lock = self._get_lock()
        async with lock:
            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            return self._events[server_id]

    async def dispatch(self, server_id: int, action: str, params: dict, timeout: float = 25.0) -> dict:
        req_id = secrets.token_hex(16)
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._waiters[req_id] = fut

        req_item = {
            "id": req_id,
            "action": action,
            "params": params,
            "created_at": time.time(),
        }

        lock = self._get_lock()
        async with lock:
            if server_id not in self._pending:
                self._pending[server_id] = []
            self._pending[server_id].append(req_item)
            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            self._events[server_id].set()

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Agen server tidak merespons permintaan berkas (timeout). Pastikan service agent_pantau aktif."
            )
        finally:
            self._waiters.pop(req_id, None)

    async def pop_pending(self, server_id: int) -> list[dict]:
        lock = self._get_lock()
        async with lock:
            reqs = self._pending.pop(server_id, [])
            if server_id in self._events:
                self._events[server_id].clear()
            return reqs

    def resolve(self, req_id: str, result: dict) -> bool:
        fut = self._waiters.get(req_id)
        if fut and not fut.done():
            fut.set_result(result)
            return True
        return False

file_dispatcher = FileManagerDispatcher()


@app.get("/api/agent/file-requests")
async def api_agent_file_requests(
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen mem-poll permintaan berkas secara cepat/long-poll (tahan hingga 15 dtk)."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    reqs = await file_dispatcher.pop_pending(server.id)
    if reqs:
        return {"requests": reqs}

    event = await file_dispatcher.get_or_create_event(server.id)
    try:
        await asyncio.wait_for(event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        pass

    reqs = await file_dispatcher.pop_pending(server.id)
    return {"requests": reqs}


@app.post("/api/agent/file-requests/{req_id}/result")
async def api_agent_file_result(
    req_id: str,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen melaporkan hasil eksekusi operasi berkas."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    ok = file_dispatcher.resolve(req_id, body)
    return {"ok": ok}


# ---------------------------------------------------------------------------
# Terminal Realtime WebSocket Bridge (Memory-only, Zero DB Polling)
# ---------------------------------------------------------------------------
class TerminalSessionBridge:
    def __init__(self, session_id: str, server_id: int):
        self.session_id = session_id
        self.server_id = server_id
        self.browser_ws: WebSocket | None = None
        self.stdin_queue: asyncio.Queue = asyncio.Queue()
        self.created_at = time.time()
        self.last_active = time.time()
        self.closed = False


class TerminalBridgeDispatcher:
    def __init__(self):
        self._sessions: dict[str, TerminalSessionBridge] = {}
        self._server_to_session: dict[int, str] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._pending_opens: dict[int, str] = {}
        self._lock = None

    def _get_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_or_create_event(self, server_id: int) -> asyncio.Event:
        if server_id not in self._events:
            self._events[server_id] = asyncio.Event()
        return self._events[server_id]

    async def open_session(self, server_id: int, ws: WebSocket) -> TerminalSessionBridge:
        lock = self._get_lock()
        async with lock:
            old_sid = self._server_to_session.get(server_id)
            if old_sid and old_sid in self._sessions:
                old_session = self._sessions.pop(old_sid, None)
                if old_session:
                    old_session.closed = True

            sess_id = secrets.token_hex(16)
            bridge = TerminalSessionBridge(sess_id, server_id)
            bridge.browser_ws = ws
            self._sessions[sess_id] = bridge
            self._server_to_session[server_id] = sess_id
            self._pending_opens[server_id] = sess_id

            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            self._events[server_id].set()
            return bridge

    async def pop_pending_open(self, server_id: int) -> str | None:
        lock = self._get_lock()
        async with lock:
            sess_id = self._pending_opens.pop(server_id, None)
            if server_id in self._events:
                self._events[server_id].clear()
            return sess_id

    def get_session(self, sess_id: str) -> TerminalSessionBridge | None:
        return self._sessions.get(sess_id)

    async def close_session(self, sess_id: str):
        lock = self._get_lock()
        async with lock:
            bridge = self._sessions.pop(sess_id, None)
            if bridge:
                bridge.closed = True
                if self._server_to_session.get(bridge.server_id) == sess_id:
                    self._server_to_session.pop(bridge.server_id, None)

term_dispatcher = TerminalBridgeDispatcher()


@app.websocket("/ws/servers/{sid}/terminal")
async def ws_server_terminal(websocket: WebSocket, sid: int):
    """Koneksi terminal realtime browser WebSocket (xterm.js)."""
    cookie_sid = websocket.cookies.get(SESSION_COOKIE)
    if not cookie_sid:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        row = db.query(AppSession).filter(AppSession.sid == cookie_sid).first()
        if not row or (row.expires_at and row.expires_at < datetime.utcnow()):
            await websocket.close(code=4401)
            return
        user = db.query(User).filter(User.id == row.user_id).first()
        if not user or user.role != "admin":
            await websocket.close(code=4403)
            return
        server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
        if not server:
            await websocket.close(code=4404)
            return
        hostname = server.hostname
        username = user.username
    finally:
        db.close()

    await websocket.accept()

    bridge = await term_dispatcher.open_session(sid, websocket)

    db = SessionLocal()
    try:
        _audit(db, username, "terminal_open", f"{hostname}:{bridge.session_id}", "berhasil")
        db.commit()
    finally:
        db.close()

    try:
        while not bridge.closed:
            raw = await websocket.receive_text()
            bridge.last_active = time.time()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"type": "input", "data": raw}

            await bridge.stdin_queue.put(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS TERM] Sesi {bridge.session_id} error: {e}")
    finally:
        await term_dispatcher.close_session(bridge.session_id)
        db = SessionLocal()
        try:
            _audit(db, username, "terminal_close", f"{hostname}:{bridge.session_id}", "selesai")
            db.commit()
        finally:
            db.close()


@app.get("/api/agent/terminal-requests")
async def api_agent_terminal_requests(
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen mem-poll permintaan pembukaan terminal session realtime (long-poll 15 dtk)."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    sess_id = await term_dispatcher.pop_pending_open(server.id)
    if sess_id:
        return {"session_id": sess_id}

    event = await term_dispatcher.get_or_create_event(server.id)
    try:
        await asyncio.wait_for(event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        pass

    sess_id = await term_dispatcher.pop_pending_open(server.id)
    return {"session_id": sess_id}


@app.get("/api/agent/terminal/{session_id}/stdin")
async def api_agent_terminal_stdin(
    session_id: str,
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen mengambil ketikan admin (stdin) atau sinyal resize dari dashboard."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if not bridge or bridge.closed:
        raise HTTPException(status_code=410, detail="Sesi terminal sudah ditutup")

    try:
        msg = await asyncio.wait_for(bridge.stdin_queue.get(), timeout=15.0)
        return msg
    except asyncio.TimeoutError:
        return {"type": "ping"}


@app.post("/api/agent/terminal/{session_id}/stdout")
async def api_agent_terminal_stdout(
    session_id: str,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen mengirimkan potongan teks output terminal ke browser WebSocket."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if not bridge or bridge.closed:
        raise HTTPException(status_code=410, detail="Sesi terminal sudah ditutup")

    chunk = body.get("chunk", "")
    if chunk and bridge.browser_ws:
        try:
            await bridge.browser_ws.send_text(json.dumps({"type": "stdout", "data": chunk}))
        except Exception:
            bridge.closed = True
            await term_dispatcher.close_session(session_id)
            return {"ok": False}

    return {"ok": True}


@app.post("/api/agent/terminal/{session_id}/close")
async def api_agent_terminal_close(
    session_id: str,
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen melaporkan bahwa proses shell lokal telah selesai/ditutup."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if bridge:
        if bridge.browser_ws:
            try:
                await bridge.browser_ws.close()
            except Exception:
                pass
        await term_dispatcher.close_session(session_id)
    return {"ok": True}


@app.get("/servers/{sid}/files", response_class=HTMLResponse)
def page_server_files(request: Request, sid: int, db: Session = Depends(get_db)):
    """Halaman antarmuka dedicated File Manager untuk server klien."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Akses ditolak: File Manager hanya untuk admin")
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    return tpl(request, "file_manager.html", {
        "server": server,
        "user": user,
    })


@app.get("/api/servers/{sid}/files/ls")
async def api_server_files_ls(
    sid: int,
    path: str = "/",
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    res = await file_dispatcher.dispatch(sid, "ls", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membaca direktori"))
    return res


@app.get("/api/servers/{sid}/files/cat")
async def api_server_files_cat(
    sid: int,
    path: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    res = await file_dispatcher.dispatch(sid, "cat", {"path": path})
    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=res.get("error", "Gagal membaca file"),
            headers={"X-Is-Binary": "1" if res.get("is_binary") else "0"}
        )
    return res


@app.post("/api/servers/{sid}/files/write")
async def api_server_files_write(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    path = str(body.get("path", "")).strip()
    content = str(body.get("content", ""))
    make_backup = bool(body.get("make_backup", True))

    if not path:
        raise HTTPException(status_code=400, detail="Path file tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "write", {"path": path, "content": content, "make_backup": make_backup})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menyimpan file"))

    _audit(db, user.username, "file_save", f"{server.hostname}:{path}", "berhasil",
           {"size": len(content), "backup": res.get("backup_created")})
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/mkdir")
async def api_server_files_mkdir(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    path = str(body.get("path", "")).strip()
    mode = str(body.get("mode", "0755")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "mkdir", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membuat direktori"))

    _audit(db, user.username, "file_mkdir", f"{server.hostname}:{path}", "berhasil")
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/touch")
async def api_server_files_touch(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    path = str(body.get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "touch", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membuat file"))

    _audit(db, user.username, "file_touch", f"{server.hostname}:{path}", "berhasil")
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/rm")
async def api_server_files_rm(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    path = str(body.get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "rm", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menghapus"))

    _audit(db, user.username, "file_rm", f"{server.hostname}:{path}", "berhasil")
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/rename")
async def api_server_files_rename(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    old_path = str(body.get("old_path", "")).strip()
    new_path = str(body.get("new_path", "")).strip()
    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="Path asal dan tujuan tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "rename", {"old_path": old_path, "new_path": new_path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengganti nama file/folder"))

    _audit(db, user.username, "file_rename", f"{server.hostname}:{old_path} -> {new_path}", "berhasil")
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/chmod")
async def api_server_files_chmod(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    path = str(body.get("path", "")).strip()
    mode = str(body.get("mode", "")).strip()
    res = await file_dispatcher.dispatch(sid, "chmod", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah izin"))

    _audit(db, user.username, "file_chmod", f"{server.hostname}:{path}", f"mode={mode}")
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/chown")
async def api_server_files_chown(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    path = str(body.get("path", "")).strip()
    owner = str(body.get("owner", "")).strip()
    group = str(body.get("group", "")).strip() or None
    res = await file_dispatcher.dispatch(sid, "chown", {"path": path, "owner": owner, "group": group})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah kepemilikan"))

    _audit(db, user.username, "file_chown", f"{server.hostname}:{path}", f"owner={owner}:{group}")
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/upload")
async def api_server_files_upload(
    sid: int,
    request: Request,
    destination: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran file terlalu besar (maksimal 50 MB)")

    filename = os.path.basename(file.filename or "uploaded_file")
    target_path = os.path.join(destination.rstrip("/"), filename)
    b64_data = base64.b64encode(raw).decode("ascii")

    res = await file_dispatcher.dispatch(sid, "write_binary", {"path": target_path, "data_b64": b64_data}, timeout=35.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengunggah file"))

    _audit(db, user.username, "file_upload", f"{server.hostname}:{target_path}", f"{len(raw)} bytes")
    db.commit()
    return {"ok": True, "path": target_path, "size": len(raw)}


@app.get("/api/servers/{sid}/files/download")
async def api_server_files_download(
    sid: int,
    path: str,
    user: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    res = await file_dispatcher.dispatch(sid, "read_binary", {"path": path}, timeout=35.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membaca file"))

    b64_data = res.get("data_b64", "")
    try:
        raw_bytes = base64.b64decode(b64_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal membaca data file dari agen")

    filename = os.path.basename(path)
    safe_name = quote(filename)
    return Response(
        content=raw_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{safe_name}',
            "Content-Length": str(len(raw_bytes)),
        }
    )


# ---------------------------------------------------------------------------
# USERS
# ---------------------------------------------------------------------------
@app.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role != "admin":
        return RedirectResponse("/", status_code=303)
    users = db.query(User).all()
    return tpl(request, "users.html", {"user": user, "users": users})


@app.post("/users/add")
def user_add_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("viewer"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    username = username.strip()
    role = role if role in ("admin", "viewer") else "viewer"
    if len(password) < 8:
        return RedirectResponse("/users" + _flash_qs(False, "Password minimal 8 karakter"), status_code=303)
    if username and password and not db.query(User).filter(User.username == username).first():
        db.add(User(username=username[:100], password_hash=pwd_ctx.hash(password), role=role))
        _audit(db, user.username, "user_add", f"{username[:100]} (role {role})", "berhasil")
        db.commit()
        return RedirectResponse("/users" + _flash_qs(True, "User ditambahkan"), status_code=303)
    return RedirectResponse("/users" + _flash_qs(False, "Username sudah dipakai atau data tidak lengkap"), status_code=303)


@app.post("/users/{uid}/delete")
def user_delete(
    request: Request, uid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.role != "admin":
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    if uid == user.id:
        return RedirectResponse("/users" + _flash_qs(False, "Tidak bisa menghapus akun sendiri"), status_code=303)
    u = db.query(User).filter(User.id == uid).first()
    if u:
        _audit(db, user.username, "user_delete", f"{u.username}", "berhasil")
        db.delete(u)
        db.commit()
        return RedirectResponse("/users" + _flash_qs(True, "User dihapus"), status_code=303)
    return RedirectResponse("/users" + _flash_qs(False, "User tidak ditemukan"), status_code=303)


# ---------------------------------------------------------------------------
# Evaluator background: menyelaraskan masalah secara berkala (jendela tenang,
# auto-close) walau tak ada halaman terbuka, agar banner alert akurat.
# ---------------------------------------------------------------------------
def _problem_bg_loop() -> None:
    while True:
        time.sleep(BG_PROBLEM_EVAL_SECS)
        try:
            with SessionLocal() as sess:
                problems_aggregate(sess)
        except Exception as exc:  # noqa: BLE001 -- jangan matikan thread
            print(f"[bg-problems] error: {exc}", flush=True)


# Retensi data: bersihkan sesi/login-attempt/riwayat yang sudah terlalu tua
# setiap jam supaya tabel tidak bertumbuh tanpa batas (disk + query lambat).
_RETENTION_LIMITS = {
    "login_attempts_days": 1,
    "audit_logs_days": 365,
    "commands_days": 180,      # hanya status sukses/gagal (bukan yang berjalan)
    "log_requests_days": 30,   # hanya yang sudah selesai
    "resolved_problems_days": 90, # masalah yang sudah terselesaikan lampau
}


def _retention_prune(db: Session) -> None:
    now = datetime.utcnow()
    _prune_expired_sessions(db)
    db.query(LoginAttempt).filter(
        LoginAttempt.updated_at < now - timedelta(days=_RETENTION_LIMITS["login_attempts_days"])
    ).delete(synchronize_session=False)
    db.query(AuditLog).filter(
        AuditLog.created_at < now - timedelta(days=_RETENTION_LIMITS["audit_logs_days"])
    ).delete(synchronize_session=False)
    db.query(Command).filter(
        Command.status.in_(["success", "failed"]),
        Command.created_at < now - timedelta(days=_RETENTION_LIMITS["commands_days"]),
    ).delete(synchronize_session=False)
    db.query(LogRequest).filter(
        LogRequest.status.in_(["success", "failed"]),
        LogRequest.updated_at < now - timedelta(days=_RETENTION_LIMITS["log_requests_days"]),
    ).delete(synchronize_session=False)
    db.query(Problem).filter(
        Problem.status == "resolved",
        Problem.resolved_at < now - timedelta(days=_RETENTION_LIMITS["resolved_problems_days"]),
    ).delete(synchronize_session=False)
    db.commit()


def _retention_loop() -> None:
    while True:
        time.sleep(3600)  # tiap jam
        try:
            with SessionLocal() as sess:
                _retention_prune(sess)
        except Exception as exc:  # noqa: BLE001 -- jangan matikan thread
            logger.error("[retention] error: %s", exc)
