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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import create_engine, desc, func, text, or_
from sqlalchemy.orm import Session, sessionmaker
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import settings
import security_auth
from models import (
    AppSession, AuditLog, Base, Command, LogRequest, LoginAttempt, Metric,
    Server, ServerExtras, ServerProblem, Service, SysSnapshotHour,
    SystemSetting, SystemSnapshot, User,
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

# Pelacak IP pelapor untuk mendeteksi konflik API key ganda / kloning VM
_agent_ip_tracker: dict[int, dict[str, float]] = {}  # server_id -> {ip_str: timestamp_epoch}
_agent_tracker_lock = threading.Lock()

# Sesi unlock terminal berbasis step-up password / TOTP (ephemeral lease per operator per server)
_terminal_unlocks: dict[tuple[int, int], datetime] = {}
_terminal_unlocks_lock = threading.Lock()


def is_terminal_unlocked(user_id: int, server_id: int) -> bool:
    with _terminal_unlocks_lock:
        exp = _terminal_unlocks.get((user_id, server_id))
        if not exp:
            return False
        if datetime.utcnow() > exp:
            _terminal_unlocks.pop((user_id, server_id), None)
            return False
        return True


def get_terminal_lease_remaining(user_id: int, server_id: int) -> int:
    with _terminal_unlocks_lock:
        exp = _terminal_unlocks.get((user_id, server_id))
        if not exp:
            return 0
        rem = int((exp - datetime.utcnow()).total_seconds())
        if rem <= 0:
            _terminal_unlocks.pop((user_id, server_id), None)
            return 0
        return rem


def set_terminal_unlock(user_id: int, server_id: int, duration_minutes: int):
    with _terminal_unlocks_lock:
        _terminal_unlocks[(user_id, server_id)] = datetime.utcnow() + timedelta(minutes=duration_minutes)


def revoke_terminal_unlock(user_id: int, server_id: int):
    with _terminal_unlocks_lock:
        _terminal_unlocks.pop((user_id, server_id), None)



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
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        return None
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency API JSON: wajib sesi login aktif."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency FastAPI: wajib login sebagai Master Admin atau Operator."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu")
    if not (user.is_master_admin() or user.is_operator()):
        raise HTTPException(status_code=403, detail="Akses ditolak: wewenang tidak mencukupi")
    return user


def require_master_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency FastAPI: khusus Master Admin."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu")
    if not user.is_master_admin():
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya Master Admin")
    return user


def require_file_manager(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency FastAPI: khusus pengguna dengan izin File Manager."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu")
    if not user.has_perm("can_file_manager"):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin File Manager diperlukan")
    return user


def _audit(db, username: str, action: str, target=None, result=None, meta=None, server_id=None):
    """Catat jejak aksi admin pada tabel audit_logs (dicommit oleh pemanggil)."""
    db.add(AuditLog(
        server_id=server_id,
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


def _flash_profile_users(ok: bool, text: str) -> str:
    """Redirect URL ke tab users dengan parameter pesan/error."""
    return f"/profile{_flash_qs(ok, text)}&tab=users"


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
        a_parts = [int(x) for x in re.findall(r"\d+", str(agent_ver))]
        c_parts = [int(x) for x in re.findall(r"\d+", str(current_ver))]
        max_len = max(len(a_parts), len(c_parts), 3)
        v_agent = tuple(a_parts + [0] * (max_len - len(a_parts)))
        v_curr = tuple(c_parts + [0] * (max_len - len(c_parts)))
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


def migrate_server_problem_ignored():
    """Migrasi penambahan kolom pembungkaman/abaikan masalah pada tabel server_problems."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "server_problems" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("server_problems")}
    wanted = {
        "is_ignored": "TINYINT(1) DEFAULT 0",
        "ignored_until": "DATETIME NULL",
        "ignored_by": "VARCHAR(100) NULL",
        "ignored_reason": "VARCHAR(255) NULL",
        "ignore_mode": "VARCHAR(20) DEFAULT 'permanent'",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    if not missing:
        return
    db = SessionLocal()
    try:
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE server_problems ADD COLUMN {col} {ddl}"))
        db.commit()
        logger.info("[startup] Kolom baru server_problems (abaikan masalah): %s", ", ".join(missing))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[startup] Migrasi kolom ignored gagal: %s", exc)
    finally:
        db.close()


def migrate_service_ignored():
    """Migrasi penambahan kolom pembungkaman/abaikan layanan pada tabel services."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "services" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("services")}
    wanted = {
        "is_ignored": "TINYINT(1) DEFAULT 0",
        "ignored_until": "DATETIME NULL",
        "ignored_by": "VARCHAR(100) NULL",
        "ignored_reason": "VARCHAR(255) NULL",
        "ignore_mode": "VARCHAR(20) DEFAULT 'permanent'",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    if not missing:
        return
    db = SessionLocal()
    try:
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE services ADD COLUMN {col} {ddl}"))
        db.commit()
        logger.info("[startup] Kolom baru services (abaikan layanan): %s", ", ".join(missing))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[startup] Migrasi kolom service ignored gagal: %s", exc)
    finally:
        db.close()


def migrate_server_extras_specs():
    """Migrasi penambahan kolom spesifikasi perangkat keras pada tabel server_extras."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "server_extras" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("server_extras")}
    wanted = {
        "hardware_specs": "TEXT NULL",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    if not missing:
        return
    db = SessionLocal()
    try:
        for col, ddl in missing.items():
            db.execute(text(f"ALTER TABLE server_extras ADD COLUMN {col} {ddl}"))
        db.commit()
        logger.info("[startup] Kolom baru server_extras (hardware_specs): %s", ", ".join(missing))
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[startup] Migrasi kolom hardware_specs gagal: %s", exc)
    finally:
        db.close()


def migrate_server_groups_and_thresholds():
    """Migrasi penambahan kolom group_name, tags, custom_thresholds, is_proxmox_ha, platform_override, is_isolated_net, dan allow_web_terminal pada tabel servers."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "servers" not in inspector.get_table_names():
        return
    existing = {c["name"] for c in inspector.get_columns("servers")}
    wanted = {
        "group_name": "VARCHAR(64) NULL DEFAULT NULL",
        "tags": "VARCHAR(255) NULL",
        "custom_thresholds": "TEXT NULL",
        "is_proxmox_ha": "TINYINT NOT NULL DEFAULT 0",
        "platform_override": "VARCHAR(20) NULL DEFAULT NULL",
        "is_isolated_net": "TINYINT NOT NULL DEFAULT 0",
        "allow_web_terminal": "TINYINT NOT NULL DEFAULT 0",
    }
    missing = {k: v for k, v in wanted.items() if k not in existing}
    db = SessionLocal()
    try:
        if missing:
            for col, ddl in missing.items():
                db.execute(text(f"ALTER TABLE servers ADD COLUMN {col} {ddl}"))
            logger.info("[startup] Kolom baru servers: %s", ", ".join(missing))
        # Bersihkan sisa grup 'Default' jika ada
        db.execute(text("UPDATE servers SET group_name = NULL WHERE group_name = 'Default' OR group_name = ''"))
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[startup] Migrasi kolom servers gagal: %s", exc)
    finally:
        db.close()


def get_existing_groups_and_tags(db: Session) -> tuple[list[str], list[str]]:
    """Ambil daftar grup dan tag unik dari semua server untuk auto-complete / chips."""
    servers = db.query(Server).all()
    groups = set()
    tags = set()
    for s in servers:
        if s.group_name and s.group_name.strip() and s.group_name.strip().lower() != "default":
            groups.add(s.group_name.strip())
        if s.tags:
            for t in s.tags.split(","):
                t_clean = t.strip()
                if t_clean:
                    tags.add(t_clean)
    return sorted(list(groups)), sorted(list(tags))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _SECRET_KEY
    _SECRET_KEY = settings.resolve_secret_key()
    Base.metadata.create_all(bind=engine)
    migrate_server_groups_and_thresholds()
    migrate_server_extras_specs()
    migrate_server_problem_ignored()
    migrate_service_ignored()
    migrate_log_request_input()
    migrate_api_keys()
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

MONTHS_ID = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")


def _fmt_dt(dt: datetime | None, with_sec: bool = True) -> str:
    """Format tanggal dan waktu rinci dalam bahasa Indonesia: DD Mon YYYY HH:MM:SS (tanpa nama hari)."""
    if not dt or not isinstance(dt, datetime):
        return "—"
    mon = MONTHS_ID[dt.month - 1]
    if with_sec:
        return f"{dt.day:02d} {mon} {dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    return f"{dt.day:02d} {mon} {dt.year} {dt.hour:02d}:{dt.minute:02d}"


templates.env.globals["_fmt_dt"] = _fmt_dt
templates.env.globals["getattr"] = getattr

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
        detail_info = str(exc) if (user and (getattr(user, "is_master_admin", lambda: False)() or getattr(user, "is_operator", lambda: False)())) else None

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
            "is_ro": bool(d.get("is_ro")),
            "read_kb_s": _clamp_float(d.get("read_kb_s"), 0.0, 0.0, 1e9),
            "write_kb_s": _clamp_float(d.get("write_kb_s"), 0.0, 0.0, 1e9),
            "read_iops": _clamp_float(d.get("read_iops"), 0.0, 0.0, 1e7),
            "write_iops": _clamp_float(d.get("write_iops"), 0.0, 0.0, 1e7),
            "io_util": _clamp_float(d.get("io_util"), 0.0, 0.0, 100.0),
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


OFFLINE_AFTER_SECONDS = 15


def _server_stale(srv) -> bool:
    """True bila server belum melapor terlalu lama / tidak pernah melapor / nonaktif."""
    if not srv or not getattr(srv, "is_active", 1):
        return True
    ls = getattr(srv, "last_seen", None)
    if ls is None:
        return True
    if ls.tzinfo is None:
        ls = ls.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ls).total_seconds() > OFFLINE_AFTER_SECONDS


def _check_server_online(db: Session, sid: int, is_json: bool = False, redirect_tab: str = ""):
    """Validasi server ada, aktif, dan online (agen terhubung). Tolak bila offline."""
    server = db.query(Server).filter(Server.id == sid).first()
    if not server or not getattr(server, "is_active", 1):
        if is_json:
            return None, JSONResponse({"ok": False, "detail": "Server tidak ditemukan atau dinonaktifkan"}, status_code=404)
        return None, RedirectResponse("/servers", status_code=303)
    if _server_stale(server):
        msg = "Server sedang offline. Aksi remote dinonaktifkan."
        if is_json:
            return None, JSONResponse({"ok": False, "detail": msg}, status_code=409)
        tab_param = f"?tab={redirect_tab}&error=server_offline" if redirect_tab else "?error=server_offline"
        return None, RedirectResponse(f"/servers/{sid}/services{tab_param}", status_code=303)
    return server, None


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

    # Pelacakan IP pelapor untuk mendeteksi konflik duplikasi agen / klon VM
    client_ip = request.client.host if request.client else ""
    body_ip = _clean_str(body.get("ip_address"), "", 45)
    reporter_ip = body_ip or client_ip or "unknown"
    now_epoch = time.time()

    with _agent_tracker_lock:
        server_ips = _agent_ip_tracker.setdefault(server.id, {})
        server_ips[reporter_ip] = now_epoch
        # Bersihkan IP yang tidak melapor lagi > 120 detik
        stale_ips = [ip for ip, ts in list(server_ips.items()) if (now_epoch - ts) > 120]
        for ip in stale_ips:
            del server_ips[ip]
        has_agent_conflict = len(server_ips) > 1
        active_conflict_ips = sorted(server_ips.keys()) if has_agent_conflict else []

    if has_agent_conflict:
        logger.warning(
            "[AGENT CONFLICT] Server ID %s (%s) menerima laporan simultan dari beberapa IP: %s",
            server.id, server.hostname, active_conflict_ips
        )

    server.hostname = _clean_str(body.get("hostname", server.hostname), server.hostname, 255)
    # Jangan flip-flop ip_address jika sedang konflik multi-IP
    if not has_agent_conflict or not server.ip_address:
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
        # Ambil status metrik terakhir sebelum menambahkan metrik baru
        last_m = (
            db.query(Metric).filter(Metric.service_id == service.id)
            .order_by(desc(Metric.timestamp)).first()
        )
        prev_status = last_m.status if last_m else None

        db.add(Metric(
            service_id=service.id,
            status=status,
            active_connections=active_connections,
            response_time_ms=response_time_ms,
            health_message=health_message or None,
        ))

        # Deteksi pemulihan / status aktif layanan
        if status == "up":
            # 1. Tutup masalah service_down seketika jika masih terbuka
            open_probs = db.query(ServerProblem).filter(
                ServerProblem.server_id == server.id,
                ServerProblem.key == f"service_down:{service.service_name}",
                ServerProblem.resolved_at.is_(None),
            ).all()
            for op in open_probs:
                op.resolved_at = datetime.utcnow()
                op.updated_at = datetime.utcnow()
                op.resolved_note = "auto"

            # 2. Jika sebelumnya bermasalah (down/offline), evaluasi pengabaian sesuai mode & catat audit
            if prev_status in ("down", "offline", "unknown"):
                svc_mode = getattr(service, "ignore_mode", None)
                if svc_mode == "incident":
                    # Mode insiden: hanya untuk satu insiden saat itu, reset ke normal saat layanan pulih
                    service.is_ignored = 0
                    service.ignored_until = None
                    service.ignored_reason = None
                    service.ignore_mode = None
                elif svc_mode == "duration":
                    # Mode durasi: jika batas waktu telah habis, kembalikan ke pemantauan normal
                    if not (service.ignored_until and service.ignored_until > datetime.utcnow()):
                        service.is_ignored = 0
                        service.ignored_until = None
                        service.ignored_reason = None
                        service.ignore_mode = None
                elif svc_mode == "permanent":
                    # Mode permanen: TETAP diabaikan (is_ignored = 1), tidak di-reset saat layanan pulih!
                    pass
                else:
                    if service.ignored_until and service.ignored_until <= datetime.utcnow():
                        service.is_ignored = 0
                        service.ignored_until = None
                        service.ignored_reason = None
                        service.ignore_mode = None

                try:
                    _audit(
                        db, "sistem", "service_recovered",
                        f"{server.hostname}:{service.service_name}",
                        "kembali aktif (pulih)",
                        server_id=server.id,
                    )
                except Exception as e:
                    logger.warning("[agent_report] Gagal catat audit service_recovered: %s", e)

    # Service yang sudah terdaftar tapi tidak dilaporkan lagi -> tandai down dengan redam flapping
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
            # 1. Bila terjadi konflik agen (multi-IP), tahan status DOWN jika host lain baru saja melapor UP
            if has_agent_conflict and last and last.status == "up":
                continue
            # 2. Toleransi jeda 45 detik untuk transisi status agar tidak flapping seketika
            if last and last.status == "up" and last.timestamp and (datetime.utcnow() - last.timestamp).total_seconds() < 45:
                continue
            db.add(Metric(
                service_id=svc.id,
                status="down",
                active_connections=0,
                health_message="Layanan tidak terdeteksi listening pada port atau proses tidak berjalan",
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

        # Heuristik Deteksi Otomatis Proxmox HA (Auto-Revive Heuristic):
        # Jika server baru saja diperintahkan 'poweroff_host' dalam 5 menit terakhir,
        # namun kembali hidup dan melapor dengan uptime rendah (< 180 detik),
        # berarti server dikelola dan dihidupkan kembali otomatis oleh cluster Proxmox HA.
        # Otomatis tandai server.is_proxmox_ha = 1 agar aksi Power OFF diblokir di UI/API.
        uptime_val = _clamp_int(sysd.get("uptime"), None, 0, 2 ** 63 - 1)
        if uptime_val is not None and uptime_val < 180 and getattr(server, "is_proxmox_ha", 0) == 0:
            recent_cutoff = datetime.utcnow() - timedelta(seconds=300)
            recent_poweroff = (
                db.query(Command)
                .filter(
                    Command.server_id == server.id,
                    Command.action == "poweroff_host",
                    Command.created_at >= recent_cutoff,
                )
                .order_by(desc(Command.created_at))
                .first()
            )
            if recent_poweroff:
                server.is_proxmox_ha = 1
                try:
                    _audit(
                        db,
                        "sistem",
                        "proxmox_ha_detected",
                        f"{server.hostname} ({server.ip_address})",
                        "Server terproteksi Proxmox HA.",
                        server_id=server.id,
                    )
                except Exception as exc:
                    logger.warning("[agent_report] Gagal catat audit proxmox_ha_detected: %s", exc)
                logger.info(
                    "[PROXMOX HA] Auto-revive terdeteksi pada server ID %s (%s) setelah poweroff (uptime: %ss). Otomatis set is_proxmox_ha=1.",
                    server.id, server.hostname, uptime_val
                )

    # Data berubah-sedikit: kernel, unit aktif, daftar akun
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
    if extras is None:
        extras = ServerExtras(server_id=server.id)
        db.add(extras)
    extras.kernel = _clean_str(body.get("kernel"), None, 100) or None
    extras.os_label = _clean_str(body.get("os_label"), None, 120) or None
    extras.arch = _clean_str(body.get("arch"), None, 24) or None
    extras.agent_version = _clean_str(body.get("agent_version"), None, 16) or None
    if "hardware_specs" in body and isinstance(body.get("hardware_specs"), dict):
        try:
            extras.hardware_specs = json.dumps(body["hardware_specs"])
        except Exception:
            pass

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
                raw_sessions = acc.get("sessions")
                clean_sessions = []
                if isinstance(raw_sessions, list):
                    for s in raw_sessions[:5]:
                        if isinstance(s, dict):
                            clean_sessions.append({
                                "tty": _clean_str(s.get("tty"), "", 32),
                                "from": _clean_str(s.get("from"), "", 64),
                            })
                clean_accounts.append({
                    "user": _clean_str(acc.get("user"), "", 64),
                    "uid": _clamp_int(acc.get("uid"), None, 0, 2 ** 31),
                    "shell": _clean_str(acc.get("shell"), "", 50),
                    "last_login": _clean_str(acc.get("last_login"), None, 32),
                    "sessions": clean_sessions,
                    "is_protected": bool(acc.get("is_protected")),
                    "is_locked": bool(acc.get("is_locked")),
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

    # Validasi & Simpan Tugas Terjadwal (Cron Jobs & Timers)
    if isinstance(body.get("cron_jobs"), dict):
        cj = body["cron_jobs"]
        clean_cron = {
            "jobs": [
                {
                    "type": _clean_str(item.get("type"), "cron", 20),
                    "source": _clean_str(item.get("source"), "", 120),
                    "line": _clamp_int(item.get("line"), 0, 0, 100000),
                    "schedule": _clean_str(item.get("schedule"), "", 60),
                    "user": _clean_str(item.get("user"), "root", 64),
                    "command": _clean_str(item.get("command"), "", 500),
                    "is_managed": bool(item.get("is_managed")),
                    "ident": _clean_str(item.get("ident"), "", 64),
                    "is_enabled": bool(item.get("is_enabled", True)),
                }
                for item in (cj.get("jobs") or [])[:100]
                if isinstance(item, dict)
            ],
            "timers": [
                {
                    "timer": _clean_str(t.get("timer"), "", 100),
                    "activates": _clean_str(t.get("activates"), "", 100),
                    "raw": _clean_str(t.get("raw"), "", 200),
                }
                for t in (cj.get("timers") or [])[:50]
                if isinstance(t, dict)
            ]
        }
        extras.cron_jobs = json.dumps(clean_cron)

    # Validasi & Simpan Konfigurasi Firewall
    if isinstance(body.get("firewall"), dict):
        fw = body["firewall"]
        clean_fw = {
            "backend": _clean_str(fw.get("backend"), "unknown", 20),
            "status": _clean_str(fw.get("status"), "inactive", 20),
            "rules": [
                _clean_str(r, "", 150)
                for r in (fw.get("rules") or [])[:100]
                if isinstance(r, str)
            ],
            "blocked_ips": [
                {
                    "num": _clean_str(b.get("num"), "", 10),
                    "pkts": _clean_str(b.get("pkts"), "", 20),
                    "bytes": _clean_str(b.get("bytes"), "", 20),
                    "source": _clean_str(b.get("source"), "", 50),
                }
                for b in (fw.get("blocked_ips") or [])[:100]
                if isinstance(b, dict)
            ]
        }
        extras.firewall = json.dumps(clean_fw)

    # Validasi & Simpan Listening Ports (ss -tulpn)
    if isinstance(body.get("listening_ports"), list):
        clean_ports = [
            {
                "proto": _clean_str(p.get("proto"), "tcp", 10),
                "ip": _clean_str(p.get("ip"), "", 64),
                "port": _clamp_int(p.get("port"), 0, 1, 65535),
                "proc": _clean_str(p.get("proc"), "", 100),
                "pid": _clamp_int(p.get("pid"), None, 1, 4194304) if p.get("pid") else None,
                "pname": _clean_str(p.get("pname"), "", 50),
                "is_loopback": bool(p.get("is_loopback")),
                "is_public": bool(p.get("is_public")),
            }
            for p in body["listening_ports"][:100]
            if isinstance(p, dict)
        ]
        extras.listening_ports = json.dumps(clean_ports)

    # Validasi & Simpan Sertifikat SSL/TLS
    if isinstance(body.get("ssl_certs"), list):
        clean_certs = [
            {
                "path": _clean_str(c.get("path"), "", 200),
                "subject": _clean_str(c.get("subject"), "", 200),
                "domains": [_clean_str(d, "", 100) for d in (c.get("domains") or [])[:20] if isinstance(d, str)],
                "issuer": _clean_str(c.get("issuer"), "", 200),
                "not_after": _clean_str(c.get("not_after"), "", 40),
                "days_left": _clamp_int(c.get("days_left"), 0, -10000, 10000),
                "is_expired": bool(c.get("is_expired")),
                "is_critical": bool(c.get("is_critical")),
                "is_warning": bool(c.get("is_warning")),
                "is_custom": bool(c.get("is_custom")),
            }
            for c in body["ssl_certs"][:50]
            if isinstance(c, dict)
        ]
        extras.ssl_certs = json.dumps(clean_certs)
    # Validasi & Simpan System Logs (kegagalan sistem journalctl)
    if isinstance(body.get("system_logs"), list):
        clean_logs = [
            {
                "time": _clean_str(l.get("time"), "", 30),
                "unit": _clean_str(l.get("unit"), "-", 80),
                "message": _clean_str(l.get("message"), "", 400),
                "priority": _clamp_int(l.get("priority"), 3, 0, 7),
            }
            for l in body["system_logs"][:60]
            if isinstance(l, dict)
        ]
        extras.system_logs = json.dumps(clean_logs)

    extras.updated_at = datetime.utcnow()

    db.commit()

    # Rekonsiliasi insiden server seketika pada saat laporan telemetri diterima
    try:
        services = db.query(Service).filter(Service.server_id == server.id).all()
        latest_map = _latest_metrics(db, (s.id for s in services))
        svc_data = [
            {
                "name": s.service_name,
                "status": latest_map[s.id].status if s.id in latest_map else "unknown",
                "port": s.port,
                "proc": s.process_name,
                "health_msg": latest_map[s.id].health_message if s.id in latest_map else None,
            }
            for s in services
        ]
        sync_server_problems(db, server, _problem_instances(server, extras, svc_data, db))
    except Exception as exc:
        logger.warning("[api_report] Error rekonsiliasi insiden untuk %s: %s", server.hostname, exc)

    return {"ok": True}


# ---------------------------------------------------------------------------
# Hardware formatting & specs helpers
# ---------------------------------------------------------------------------
def _format_bytes_gb(b: int | float | None) -> str:
    if b is None or b <= 0:
        return "—"
    gb = b / (1024 ** 3)
    if gb >= 1000:
        return f"{round(gb / 1024, 1)} TB"
    return f"{round(gb, 1)} GB"


def _format_uptime_str(secs: int | None) -> str:
    if secs is None or secs <= 0:
        return "—"
    days = secs // 86400
    hours = (secs % 86400) // 3600
    mins = (secs % 3600) // 60
    if days > 0:
        return f"{days}h {hours}j" if hours else f"{days} hari"
    if hours > 0:
        return f"{hours}j {mins}m"
    return f"{mins} mnt"


def _extract_disk_stats(disks_raw):
    if not disks_raw:
        return "—", "—", None
    try:
        data = json.loads(disks_raw) if isinstance(disks_raw, str) else disks_raw
        if not isinstance(data, list) or not data:
            return "—", "—", None
        root_d = next((d for d in data if d.get("mount") == "/"), data[0])
        tot = root_d.get("total", 0)
        used = root_d.get("used", 0)
        pct = root_d.get("pct", 0.0)
        avail = max(0, tot - used)
        return _format_bytes_gb(tot), _format_bytes_gb(avail), round(float(pct), 1)
    except Exception:
        return "—", "—", None


def _classify_platform(platform_dict: dict | None, override: str | None = None) -> dict:
    """Klasifikasi tipe platform host: LXC Container, VM (KVM/QEMU/dll), atau Baremetal."""
    if override in ("baremetal", "vm", "lxc"):
        if override == "baremetal":
            return {
                "type": "baremetal",
                "virt": "Baremetal",
                "label": "Baremetal",
                "short_label": "Baremetal",
                "badge_color": "#34d399",
                "badge_bg": "rgba(16,185,129,0.15)",
                "badge_border": "rgba(16,185,129,0.3)",
            }
        elif override == "vm":
            return {
                "type": "vm",
                "virt": "VM",
                "label": "Mesin Virtual (VM)",
                "short_label": "VM",
                "badge_color": "#c084fc",
                "badge_bg": "rgba(168,85,247,0.15)",
                "badge_border": "rgba(168,85,247,0.3)",
            }
        elif override == "lxc":
            return {
                "type": "lxc",
                "virt": "LXC",
                "label": "LXC Container",
                "short_label": "LXC",
                "badge_color": "#22d3ee",
                "badge_bg": "rgba(6,182,212,0.15)",
                "badge_border": "rgba(6,182,212,0.3)",
            }

    if not isinstance(platform_dict, dict):
        platform_dict = {}
    virt = str(platform_dict.get("virt") or "").strip().upper()
    vendor = str(platform_dict.get("vendor") or "").strip()
    product = str(platform_dict.get("product") or "").strip()

    # Kontainer (LXC / Docker / WSL / etc.)
    if virt in ("LXC", "LXC-LIBVIRT", "DOCKER", "PODMAN", "CONTAINER", "WSL", "SYSTEMD-NSPAWN"):
        label = "LXC Container" if virt in ("LXC", "LXC-LIBVIRT") else f"Container ({virt})"
        return {
            "type": "lxc",
            "virt": virt,
            "label": label,
            "short_label": "LXC" if virt in ("LXC", "LXC-LIBVIRT") else virt,
            "badge_color": "#22d3ee",
            "badge_bg": "rgba(6,182,212,0.15)",
            "badge_border": "rgba(6,182,212,0.3)",
        }

    # Mesin Virtual (KVM, QEMU, VMware, VirtualBox, etc.)
    vm_types = ("KVM", "QEMU", "VMWARE", "XEN", "VIRTUALBOX", "ORACLE", "HYPERV", "BOCHS", "BHYVE")
    is_vm = virt in vm_types or any(x in (vendor + product).upper() for x in ("QEMU", "KVM", "VMWARE", "VIRTUALBOX"))
    if is_vm:
        v_name = virt if virt in vm_types else "KVM"
        return {
            "type": "vm",
            "virt": v_name,
            "label": f"VM ({v_name})" if v_name != "VM" else "Virtual Machine",
            "short_label": f"VM ({v_name})" if v_name != "VM" else "VM",
            "badge_color": "#c084fc",
            "badge_bg": "rgba(168,85,247,0.15)",
            "badge_border": "rgba(168,85,247,0.3)",
        }

    # Baremetal / Server Fisik
    return {
        "type": "baremetal",
        "virt": "Baremetal",
        "label": "Baremetal",
        "short_label": "Baremetal",
        "badge_color": "#34d399",
        "badge_bg": "rgba(16,185,129,0.15)",
        "badge_border": "rgba(16,185,129,0.3)",
    }


def _get_hardware_specs_dict(server: Server, extra: ServerExtras | None, latest: SystemSnapshot | None) -> dict:
    if extra and extra.hardware_specs:
        try:
            parsed = json.loads(extra.hardware_specs)
            if isinstance(parsed, dict) and parsed.get("cpu"):
                # Koreksi Storage untuk LXC Container:
                # Kontainer LXC tidak memiliki block storage fisik host (mis. HPE DL380 sda 7.6T).
                # Bila terdeteksi LXC dan disk masih melaporkan disk host, koreksi dengan kuota rootfs dari snapshot.
                plat = parsed.get("platform", {})
                plat_ovr = getattr(server, "platform_override", None)
                is_lxc = (
                    plat_ovr == "lxc"
                    or (plat_ovr not in ("baremetal", "vm") and (str(plat.get("virt", "")).upper() == "LXC" or plat.get("platform_type") == "lxc"))
                )
                if is_lxc:
                    has_host_disk = any(d.get("name", "").startswith("sd") or "T" in str(d.get("size", "")) for d in parsed.get("disks", []))
                    if has_host_disk or not parsed.get("disks"):
                        root_total = 0
                        if latest and latest.disks:
                            try:
                                d_raw = json.loads(latest.disks) if isinstance(latest.disks, str) else latest.disks
                                for d in (d_raw if isinstance(d_raw, list) else []):
                                    if d.get("mount") == "/":
                                        root_total = d.get("total", 0)
                                        break
                            except Exception:
                                pass
                        if root_total > 0:
                            gb = root_total / (1024 ** 3)
                            sz_str = f"{round(gb / 1024, 1)}T" if gb >= 1024 else f"{round(gb, 1)}G"
                            parsed["disks"] = [{
                                "name": "rootfs",
                                "size": sz_str,
                                "type": "Virtual (LXC)",
                                "model": "Container Allocation",
                            }]
                return parsed
        except Exception:
            pass

    has_reported = bool(server.last_seen or latest)
    # Baseline fallback apabila agen belum mengirim hardware_specs (versi lama)
    disks_baseline = []
    if latest and latest.disks:
        try:
            disks_raw = json.loads(latest.disks) if isinstance(latest.disks, str) else latest.disks
            for d in (disks_raw if isinstance(disks_raw, list) else []):
                total_b = d.get("total", 0)
                sz_str = f"{round(total_b / (1024**3), 1)}G" if total_b > 0 else "-"
                disks_baseline.append({
                    "name": d.get("mount", "/"),
                    "size": sz_str,
                    "type": d.get("type", "Disk"),
                    "model": "Storage Partition"
                })
        except Exception:
            pass

    net_interfaces = []
    if latest and latest.net:
        try:
            net_raw = json.loads(latest.net) if isinstance(latest.net, str) else latest.net
            for n in (net_raw if isinstance(net_raw, list) else []):
                net_interfaces.append({
                    "name": n.get("iface", "eth0"),
                    "mac": "-",
                    "speed": ""
                })
        except Exception:
            pass
    if not net_interfaces and has_reported:
        net_interfaces = [{"name": "primary", "mac": "-", "speed": ""}]

    return {
        "cpu": {
            "model": f"Prosesor ({extra.arch if extra and extra.arch else 'x86_64'})" if has_reported else "—",
            "cores": 1 if has_reported else None,
            "arch": extra.arch if extra and extra.arch else ("x86_64" if has_reported else "—"),
            "mhz": "",
            "cache": "",
        },
        "platform": {
            "virt": "Virtual / Host Linux",
            "vendor": "-",
            "product": server.hostname,
            "bios_version": "-",
            "bios_date": "-",
        },
        "memory": {
            "ram_total": latest.mem_total if latest else 0,
            "swap_total": latest.swap_total if latest else 0,
        },
        "disks": disks_baseline,
        "network": {
            "gateway": "-",
            "dns": [],
            "interfaces": net_interfaces,
        },
        "os": {
            "os_name": extra.os_label if extra and extra.os_label else "Linux",
            "kernel": extra.kernel if extra and extra.kernel else "-",
            "hostname": server.hostname,
            "boot_time": "-",
        }
    }


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
        ex = extras_map.get(srv.id)
        # Evaluasi masalah server & deteksi layanan/masalah yang diabaikan
        prob_level, open_prob, _ = sync_server_problems(
            db, srv, _problem_instances(srv, ex, [{"name": s["name"], "status": s["status"]} for s in svc_list], db)
        )
        ignored_keys = {p.get("key") for p in open_prob if p.get("is_ignored")}
        svc_ignored_db = {s.service_name for s in services if getattr(s, "is_ignored", 0)}
        for s in svc_list:
            if (f"service_down:{s['name']}" in ignored_keys) or (s["name"] in svc_ignored_db):
                s["ignored"] = True

        stale = _server_stale(srv)
        active_svcs = [s for s in svc_list if not s.get("ignored")]
        if srv.is_maintenance:
            overall = "maintenance"
        elif not active_svcs:
            overall = "offline" if stale else "up"
        else:
            overall = "down" if not any(s["status"] == "up" for s in active_svcs) else "up"
        if stale:
            for s in svc_list:
                s["status"] = "offline"
            if not srv.is_maintenance:
                overall = "offline"

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
        down_svc_count = sum(1 for s in svc_list if s["status"] in ("down", "offline") and not s.get("ignored"))
        ignored_svc_count = sum(1 for s in svc_list if s["status"] in ("down", "offline") and s.get("ignored"))
        active_p = [p for p in open_prob if not p.get("is_ignored")]
        danger_p = [p for p in active_p if p.get("severity") == "danger"]
        average_p = [p for p in active_p if p.get("severity") == "average"]
        warning_p = [p for p in active_p if p.get("severity") == "warning"]
        info_p = [p for p in active_p if p.get("severity") == "info"]
        ignored_p = [p for p in open_prob if p.get("is_ignored")]

        danger_count = len(danger_p)
        average_count = len(average_p)
        warning_count = len(warning_p)
        info_count = len(info_p)
        active_prob_count = len(active_p)
        ignored_prob_count = len(ignored_p)
        danger_msgs = " • ".join(p.get("message", "") for p in danger_p)
        average_msgs = " • ".join(p.get("message", "") for p in average_p)
        warning_msgs = " • ".join(p.get("message", "") for p in warning_p)
        info_msgs = " • ".join(p.get("message", "") for p in info_p)
        ignored_msgs = " • ".join(p.get("message", "") for p in ignored_p)

        hw = _get_hardware_specs_dict(srv, ex, latest_sys)
        cpu_cores = hw.get("cpu", {}).get("cores") or hw.get("cpu", {}).get("logical_cores")
        cpu_cores_str = f"{cpu_cores} Core" if (srv.last_seen and cpu_cores) else "—"
        d_tot, d_avail, d_pct = _extract_disk_stats(latest_sys.disks if latest_sys else None)
        m_tot = _format_bytes_gb(latest_sys.mem_total if latest_sys else None)
        m_avail = _format_bytes_gb(latest_sys.mem_avail if latest_sys else None)
        m_used = _format_bytes_gb(latest_sys.mem_used if latest_sys else None)
        up_str = _format_uptime_str(latest_sys.uptime_secs if latest_sys else None)

        formatted_probs = []
        for p in open_prob:
            p_dict = dict(p)
            p_dict["server_id"] = srv.id
            p_dict["hostname"] = srv.hostname
            p_dict["group_name"] = srv.group_name or ""
            formatted_probs.append(p_dict)

        result.append({
            "id": srv.id, "hostname": srv.hostname, "ip_address": srv.ip_address,
            "group_name": srv.group_name or "",
            "is_active": srv.is_active,
            "is_maintenance": bool(srv.is_maintenance),
            "is_proxmox_ha": bool(srv.is_proxmox_ha),
            "platform_override": getattr(srv, "platform_override", None),
            "is_isolated_net": bool(getattr(srv, "is_isolated_net", 0)),
            "allow_web_terminal": bool(getattr(srv, "allow_web_terminal", 0)),
            "platform": _classify_platform(hw.get("platform", {}), getattr(srv, "platform_override", None)),
            "online": overall != "offline",
            "last_seen": srv.last_seen.isoformat() if srv.last_seen else None,
            "overall_status": overall, "services": svc_list,
            "problems": _serialize_problem_list(formatted_probs),
            "apt_upgradable": ex.apt_upgradable if ex else None,
            "apt_last_update": ex.apt_last_update.isoformat() if ex and ex.apt_last_update else None,
            "kernel": ex.kernel if ex else None,
            "os_label": ex.os_label if ex else None,
            "arch": ex.arch if ex else None,
            "cpu": cpu_pct,
            "cpu_cores": cpu_cores_str,
            "mem_pct": mem_pct,
            "mem_total_str": m_tot,
            "mem_avail_str": m_avail,
            "mem_used_str": m_used,
            "disk_total_str": d_tot,
            "disk_avail_str": d_avail,
            "disk_pct": d_pct,
            "uptime_secs": uptime_secs,
            "uptime_str": up_str,
            "down_svc_count": down_svc_count,
            "ignored_svc_count": ignored_svc_count,
            "problem_level": prob_level,
            "active_problem_count": active_prob_count,
            "ignored_problem_count": ignored_prob_count,
            "danger_count": danger_count,
            "average_count": average_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "danger_msgs": danger_msgs,
            "average_msgs": average_msgs,
            "warning_msgs": warning_msgs,
            "info_msgs": info_msgs,
            "ignored_msgs": ignored_msgs,
        })
    return result



def _get_server_actions(db, sid: int, limit: int = 50) -> list[dict]:
    """Mengambil riwayat tindakan terpadu (commands + audit_logs) untuk server tertentu."""
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return []

    services = db.query(Service).filter(Service.server_id == sid).all()
    svc_map = {s.id: s.service_name for s in services}

    rows = []

    # 1. Commands dari tabel commands
    cmds = (
        db.query(Command)
        .filter(Command.server_id == sid)
        .order_by(desc(Command.created_at))
        .limit(limit)
        .all()
    )
    for c in cmds:
        tgt_name = svc_map.get(c.service_id)
        if not tgt_name and c.params:
            try:
                p_dict = json.loads(c.params)
                uname = p_dict.get("username")
                if uname:
                    tgt_name = f"Akun {uname}"
                elif p_dict.get("ips"):
                    tgt_name = f"IP {', '.join(p_dict['ips'])}"
                elif p_dict.get("ident"):
                    tgt_name = f"Cron {p_dict['ident']}"
                elif p_dict.get("path"):
                    tgt_name = f"SSL {p_dict['path']}"
                elif p_dict.get("port"):
                    tgt_name = f"Port {p_dict['port']}"
                elif c.action == "update_agent":
                    ver = p_dict.get("version") or ""
                    h = p_dict.get("sha256") or ""
                    h_short = f" (SHA: {h[:8]}…)" if h else ""
                    tgt_name = f"OTA v{ver}{h_short}" if ver else (f"OTA{h_short}" if h_short else "Agen Pantau")
            except Exception:
                pass
        if not tgt_name:
            if c.action in ("restart_agent", "update_agent"):
                tgt_name = "Agen Pantau"
            else:
                tgt_name = "—"

        act_label = {
            "restart": "Restart Layanan",
            "stop": "Hentikan Layanan",
            "start": "Jalankan Layanan",
            "service_restart": "Restart Layanan",
            "service_stop": "Hentikan Layanan",
            "service_start": "Jalankan Layanan",
            "block_ip": "Blokir IP",
            "unblock_ip": "Buka Blokir IP",
            "restart_agent": "Restart Agen",
            "update_agent": "Pembaruan Agen (OTA)",
            "reboot_host": "Reboot Host",
            "poweroff_host": "Power Off Host",
            "user_create": "Buat Pengguna",
            "user_lock": "Kunci Akun",
            "user_unlock": "Buka Kunci Akun",
            "user_delete": "Hapus Pengguna",
            "cron_add": "Tambah Cron Job",
            "cron_toggle": "Ubah Status Cron",
            "cron_delete": "Hapus Cron Job",
            "firewall_enable": "Aktifkan Firewall",
            "firewall_disable": "Nonaktifkan Firewall",
            "firewall_reload": "Muat Ulang Firewall",
            "firewall_port_rule": "Aturan Port Firewall",
            "ssl_path_add": "Tambah Path SSL",
            "ssl_path_remove": "Hapus Path SSL",
        }.get(c.action, c.action.replace("_", " ").capitalize())

        status_cls = {
            "pending": "muted",
            "executing": "warn",
            "success": "up",
            "failed": "danger",
        }.get(c.status, "muted")

        status_label = {
            "pending": "menunggu…",
            "executing": "dieksekusi…",
            "success": "berhasil",
            "failed": "gagal",
        }.get(c.status, c.status)

        rows.append({
            "id": f"cmd-{c.id}",
            "time": c.created_at,
            "user": c.issued_by or "admin",
            "action": c.action,
            "action_label": act_label,
            "target": tgt_name,
            "status": c.status,
            "status_cls": status_cls,
            "status_label": status_label,
            "result": c.result or "—",
        })

    # 2. Audit logs dari tabel audit_logs
    audit_q = (
        db.query(AuditLog)
        .filter(
            (AuditLog.server_id == sid) |
            (AuditLog.target.like(f"%{server.hostname}%")) |
            (AuditLog.target.like(f"%ID {sid}%"))
        )
        .order_by(desc(AuditLog.created_at))
        .limit(limit)
        .all()
    )
    for a in audit_q:
        if a.action in (
            "service_restart", "service_stop", "service_start", "login",
            "server_add", "server_delete", "user_add", "user_delete",
            "user_create", "user_lock", "user_unlock", "block_ip", "unblock_ip",
            "reboot_host", "poweroff_host", "restart_agent", "agent_update", "update_agent",
        ) or a.action.startswith("masalah_"):
            continue

        act_label = {
            "problem_ignore": "Abaikan Masalah",
            "problem_unignore": "Pantau Kembali",
            "alert_ack": "Tandai Ditangani",
            "problem_resolve": "Selesaikan Masalah",
            "service_recovered": "Layanan Pulih",
            "maintenance_mode": "Mode Pemeliharaan",
            "service_add": "Tambah Layanan",
            "service_delete": "Hapus Layanan",
            "host_reboot": "Reboot OS",
            "host_poweroff": "Power Off",
            "apt_update": "Update OS (apt)",
            "apt_upgrade": "Upgrade OS (apt)",
            "apt_upgrade_interact": "Upgrade OS (interaktif)",
            "terminal_shell_open": "Buka Terminal Root",
            "file_save": "Simpan Berkas",
            "file_upload": "Unggah Berkas",
            "file_rm": "Hapus Berkas",
            "file_mkdir": "Buat Folder",
            "file_rename": "Ubah Nama Berkas",
            "file_chmod": "Ubah Izin Berkas",
            "file_chown": "Ubah Pemilik Berkas",
        }.get(a.action, a.action.replace("_", " ").capitalize())

        status_cls = "up"
        status_label = "berhasil"
        res_lower = (a.result or "").lower()
        if "gagal" in res_lower or "failed" in res_lower or "error" in res_lower:
            status_cls = "danger"
            status_label = "gagal"

        target_str = a.target or "—"
        if ":" in target_str:
            target_str = target_str.split(":", 1)[1]
        elif target_str == server.hostname or target_str == f"Server {server.hostname}":
            target_str = "—"

        rows.append({
            "id": f"audit-{a.id}",
            "time": a.created_at,
            "user": a.username,
            "action": a.action,
            "action_label": act_label,
            "target": target_str,
            "status": "failed" if status_label == "gagal" else "success",
            "status_cls": status_cls,
            "status_label": status_label,
            "result": a.result or "—",
        })

    rows.sort(key=lambda r: r["time"], reverse=True)
    return rows[:limit]


@app.get("/api/servers/{sid}/overview")
def api_server_overview(sid: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Ringkasan live (services + perintah terbaru) untuk polling UI halaman Services."""
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    services = db.query(Service).filter(Service.server_id == sid).order_by(Service.port).all()
    pending_cmds = (
        db.query(Command).filter(
            Command.server_id == sid,
            Command.status.in_(["pending", "executing"]),
        ).all()
    )
    pending_ids = {c.service_id for c in pending_cmds if c.service_id}
    pending_actions = {c.service_id: c.action for c in pending_cmds if c.service_id}

    # Cek perintah yang baru saja sukses (< 25 dtk) untuk override status seketika
    recent_cutoff = datetime.utcnow() - timedelta(seconds=25)
    recent_completed_cmds = (
        db.query(Command).filter(
            Command.server_id == sid,
            Command.status == "success",
            Command.executed_at >= recent_cutoff,
        ).order_by(desc(Command.executed_at)).all()
    )
    recent_svc_cmds = {}
    for rc in recent_completed_cmds:
        if rc.service_id and rc.service_id not in recent_svc_cmds:
            recent_svc_cmds[rc.service_id] = rc

    latest_map = _latest_metrics(db, (s.id for s in services))
    open_prob_map = {
        p.key: p for p in db.query(ServerProblem).filter(
            ServerProblem.server_id == sid,
            ServerProblem.resolved_at.is_(None),
        ).all()
    }
    svc_list = []
    for svc in services:
        latest = latest_map.get(svc.id)
        st = latest.status if latest else "unknown"

        # Terapkan override status jika ada command yang baru selesai sebelum agen mengirim metrik baru
        recent_cmd = recent_svc_cmds.get(svc.id)
        if recent_cmd:
            if recent_cmd.action in ("stop", "service_stop"):
                st = "down"
            elif recent_cmd.action in ("start", "service_start") and st != "up":
                st = "up"

        p_row = open_prob_map.get(f"service_down:{svc.service_name}")
        is_ign = bool(getattr(p_row, "is_ignored", 0)) if p_row else bool(getattr(svc, "is_ignored", 0))
        if st == "up" and getattr(svc, "ignore_mode", None) == "incident":
            is_ign = False
        p_id = p_row.id if p_row else None
        p_msg = p_row.message if p_row else None
        ign_until = None
        if getattr(svc, "ignored_until", None):
            ign_until = svc.ignored_until.isoformat()
        elif p_row and getattr(p_row, "ignored_until", None):
            ign_until = p_row.ignored_until.isoformat()

        svc_list.append({
            "id": svc.id, "name": svc.service_name, "port": svc.port,
            "status": st,
            "ignored": is_ign,
            "ignored_until": ign_until,
            "ignore_mode": getattr(svc, "ignore_mode", None),
            "problem_id": p_id,
            "problem_msg": p_msg,
            "connections": latest.active_connections if latest else 0,
            "response_time_ms": latest.response_time_ms if latest else None,
            "health_message": latest.health_message if latest else None,
            "pending": svc.id in pending_ids,
            "pending_action": pending_actions.get(svc.id),
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

    actions_raw = _get_server_actions(db, sid, limit=50)
    actions_list = [{
        "id": a["id"],
        "time": _fmt_dt(a["time"], with_sec=True) if a["time"] else "",
        "user": a["user"],
        "action": a["action"],
        "action_label": a["action_label"],
        "target": a["target"],
        "status": a["status"],
        "status_cls": a["status_cls"],
        "status_label": a["status_label"],
        "result": a["result"],
    } for a in actions_raw]
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
    if apt_run:
        apt_limit = timedelta(minutes=15) if "UPGRADE" in (apt_run.unit or "") else timedelta(minutes=4)
        ref_time = apt_run.updated_at or apt_run.created_at
        if ref_time and ref_time < (datetime.utcnow() - apt_limit):
            apt_run.status = "failed"
            apt_run.result = (apt_run.result or "").strip() + "\n[proses apt kedaluwarsa]"
            db.commit()
            apt_run = None
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
    svc_data = [{"name": s.service_name, "status": latest_map.get(s.id).status if latest_map.get(s.id) else "unknown"}
                for s in services]
    problem_level, open_problems, problem_history = sync_server_problems(
        db, server, _problem_instances(server, extras, svc_data, db))
    _enrich_problems_for_ui(open_problems, services, extras, user)
    open_prob_serialized = _serialize_problem_list(open_problems)
    hist_prob_serialized = _serialize_problem_list(problem_history)

    return {
        "services": svc_list, "commands": cmd_list, "actions": actions_list,
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
        "is_proxmox_ha": bool(server.is_proxmox_ha),
        "platform_override": getattr(server, "platform_override", None),
        "is_isolated_net": bool(getattr(server, "is_isolated_net", 0)),
        "allow_web_terminal": bool(getattr(server, "allow_web_terminal", 0)),
        "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
        "maintenance_reason": server.maintenance_reason,
        # Sesi Terminal Bawaan yang masih hidup (resume setelah reload).
        "shell_exec": {
            "id": shell_run.id,
            "started_ms": int(shell_run.created_at.replace(tzinfo=timezone.utc).timestamp() * 1000)
            if shell_run.created_at else None,
        } if shell_run else None,
        "problem_level": problem_level,
        "open_problems": open_prob_serialized,
        "problem_history": hist_prob_serialized,
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
    if not user or not user.has_perm("can_manage_servers"):
        raise HTTPException(status_code=403, detail="Akses ditolak: Hanya admin atau operator berizin yang dapat mengatur mode pemeliharaan")
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

    _audit(
        db, user.username, "maintenance_mode",
        target=server.hostname, result=detail_msg, server_id=server.id
    )
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
    request: Request,
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

    # Self-update OTA otomatis armada agen jika versi agen lebih lama dari dashboard
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
    if extras and extras.agent_version and _is_agent_outdated(extras.agent_version, settings.APP_VERSION):
        has_ota = any(c.action == "update_agent" for c in pending)
        if not has_ota:
            in_flight = (
                db.query(Command)
                .filter(Command.server_id == server.id, Command.action == "update_agent", Command.status == "executing")
                .first()
            )
            if not in_flight:
                recent_failed = (
                    db.query(Command)
                    .filter(
                        Command.server_id == server.id,
                        Command.action == "update_agent",
                        Command.status == "failed",
                        Command.created_at > datetime.utcnow() - timedelta(minutes=15)
                    )
                    .first()
                )
                if not recent_failed:
                    _, sha256_hash, version = _get_agent_code_and_sha256()
                    base_url = str(request.base_url).rstrip("/")
                    ota_params = {
                        "url": f"{base_url}/api/agent/latest-code",
                        "sha256": sha256_hash,
                        "version": version,
                    }
                    auto_cmd = Command(
                        server_id=server.id,
                        action="update_agent",
                        params=json.dumps(ota_params),
                        issued_by="system (auto-update)",
                        status="pending",
                    )
                    db.add(auto_cmd)
                    db.commit()
                    pending.append(auto_cmd)
                    logger.info("[AUTO-OTA] Otomatis mendispatch self-update agen v%s ke %s (ID %s)", version, server.hostname, server.id)

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

    # Jika aksi service stop sukses, segera sisipkan metrik down agar data live langsung sinkron tanpa jeda
    if cmd.service_id and cmd.action in ("stop", "service_stop") and status == "success":
        try:
            m = Metric(
                service_id=cmd.service_id,
                status="down",
                response_time_ms=None,
                active_connections=0,
                timestamp=datetime.utcnow(),
                health_message="Layanan dihentikan oleh operator",
            )
            db.add(m)
        except Exception as e:
            logger.warning("[cmd_result] Gagal menambah metrik down seketika: %s", e)

    # Jika aksi service start / restart sukses, segera sisipkan metrik up & tutup masalah seketika
    if cmd.service_id and cmd.action in ("start", "restart", "service_start", "service_restart") and status == "success":
        try:
            m = Metric(
                service_id=cmd.service_id,
                status="up",
                response_time_ms=1.0,
                active_connections=0,
                timestamp=datetime.utcnow(),
                health_message="Layanan berhasil dimulai oleh operator",
            )
            db.add(m)
            svc_obj = db.query(Service).filter(Service.id == cmd.service_id).first()
            if svc_obj:
                for op in db.query(ServerProblem).filter(
                    ServerProblem.server_id == cmd.server_id,
                    ServerProblem.key == f"service_down:{svc_obj.service_name}",
                    ServerProblem.resolved_at.is_(None),
                ).all():
                    op.resolved_at = datetime.utcnow()
                    op.updated_at = datetime.utcnow()
                    op.resolved_note = "operator_start"
                if getattr(svc_obj, "ignore_mode", None) != "permanent":
                    svc_obj.is_ignored = 0
                    svc_obj.ignored_until = None
                    svc_obj.ignored_reason = None
                    svc_obj.ignore_mode = None
        except Exception as e:
            logger.warning("[cmd_result] Gagal update metrik/problem up seketika: %s", e)

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


def _is_trusted_proxy(ip_str: str) -> bool:
    """Periksa apakah IP sumber merupakan proxy terpercaya (IP tunggal, CIDR, atau wildcard *)."""
    if not ip_str or ip_str == "unknown":
        return False
    trusted_set = settings.trusted_proxy_set
    if "*" in trusted_set or ip_str in trusted_set:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for t in trusted_set:
            try:
                if "/" in t and ip_obj in ipaddress.ip_network(t, strict=False):
                    return True
            except ValueError:
                pass
    except ValueError:
        pass
    return False


def _clean_ua(ua: str | None) -> str:
    """Ringkas User-Agent browser menjadi identitas perangkat/OS ringkas untuk sysadmin."""
    if not ua:
        return ""
    ua_lower = ua.lower()
    os_name = (
        "Windows" if "windows" in ua_lower
        else "macOS" if ("macintosh" in ua_lower or "mac os" in ua_lower)
        else "Android" if "android" in ua_lower
        else "iOS" if ("iphone" in ua_lower or "ipad" in ua_lower)
        else "Linux" if "linux" in ua_lower
        else "OS"
    )
    browser_name = (
        "Edge" if "edg/" in ua_lower
        else "Opera" if ("opr/" in ua_lower or "opera" in ua_lower)
        else "Chrome" if ("chrome/" in ua_lower and "chromium" not in ua_lower)
        else "Firefox" if "firefox/" in ua_lower
        else "Safari" if ("safari/" in ua_lower and "chrome" not in ua_lower)
        else "Browser"
    )
    return f"{browser_name} · {os_name}"


def _client_ip(request: Request) -> str:
    """Dapatkan IP asli klien. Mendukung CF-Connecting-IP, True-Client-IP, X-Forwarded-For, X-Real-IP dari proxy terpercaya."""
    real_ip = request.client.host if request.client else "unknown"
    if _is_trusted_proxy(real_ip):
        # 1. Header Cloudflare / Akamai
        for hdr in ("CF-Connecting-IP", "True-Client-IP"):
            val = request.headers.get(hdr)
            if val:
                return val.strip()[:45]
        # 2. X-Forwarded-For (ambil IP pertama)
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            candidate = xff.split(",")[0].strip()[:45]
            if candidate:
                return candidate
        # 3. X-Real-IP
        x_real = request.headers.get("X-Real-IP")
        if x_real:
            return x_real.strip()[:45]
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

    if not user.is_active:
        return tpl(request, "login.html", {"error": "Akun Anda telah dinonaktifkan oleh Administrator."})

    # Cek apakah akun mewajibkan verifikasi dua langkah (2FA / TOTP)
    if user.totp_enabled and user.totp_secret:
        preauth_tok = security_auth.create_preauth_token(user.id, _SECRET_KEY)
        resp = RedirectResponse("/login/2fa", status_code=303)
        resp.set_cookie(
            "preauth_session", preauth_tok, httponly=True, samesite="lax",
            secure=settings.SESSION_COOKIE_SECURE, max_age=300, path="/",
        )
        return resp

    row.fails = 0
    row.lock_until = None
    row.updated_at = datetime.utcnow()
    user.last_login_at = datetime.utcnow()
    user.last_login_ip = ip
    _prune_expired_sessions(db)
    sid = create_session(db, user.id, ip, request.headers.get("user-agent"))
    ua_summary = _clean_ua(request.headers.get("user-agent"))
    client_target = f"masuk dari {ip}" + (f" ({ua_summary})" if ua_summary else "")
    _audit(db, user.username, "login", client_target, "berhasil", meta={"ip": ip, "ua": request.headers.get("user-agent", ""), "browser": ua_summary})
    db.commit()
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE, sid, httponly=True, samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()), path="/",
    )
    return resp


@app.get("/login/2fa", response_class=HTMLResponse)
def login_2fa_page(request: Request, db: Session = Depends(get_db)):
    preauth_tok = request.cookies.get("preauth_session")
    uid = security_auth.verify_preauth_token(preauth_tok, _SECRET_KEY) if preauth_tok else None
    if not uid:
        return RedirectResponse("/login", status_code=303)
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or not user.totp_enabled:
        return RedirectResponse("/login", status_code=303)
    return tpl(request, "login_2fa.html", {"user": user})


@app.post("/login/2fa")
def login_2fa_submit(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = _client_ip(request)
    preauth_tok = request.cookies.get("preauth_session")
    uid = security_auth.verify_preauth_token(preauth_tok, _SECRET_KEY) if preauth_tok else None
    if not uid:
        return RedirectResponse("/login", status_code=303)
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or not user.totp_enabled:
        return RedirectResponse("/login", status_code=303)

    code_str = code.strip()
    is_valid = security_auth.verify_totp(user.totp_secret, code_str)
    used_recovery = False

    if not is_valid and user.recovery_codes:
        is_rec_valid, updated_hashes = security_auth.verify_and_consume_recovery_code(code_str, user.recovery_codes)
        if is_rec_valid:
            is_valid = True
            used_recovery = True
            user.recovery_codes = updated_hashes

    if not is_valid:
        return tpl(request, "login_2fa.html", {
            "user": user,
            "error": "Kode verifikasi 2FA atau kode cadangan darurat tidak cocok.",
        })

    user.last_login_at = datetime.utcnow()
    user.last_login_ip = ip
    _prune_expired_sessions(db)
    sid = create_session(db, user.id, ip, request.headers.get("user-agent"))
    action_note = "masuk via 2FA (Recovery Code)" if used_recovery else "masuk via 2FA (TOTP)"
    ua_summary = _clean_ua(request.headers.get("user-agent"))
    client_target = f"{action_note} dari {ip}" + (f" ({ua_summary})" if ua_summary else "")
    _audit(db, user.username, "login_2fa", client_target, "berhasil", meta={"ip": ip, "ua": request.headers.get("user-agent", ""), "browser": ua_summary})
    db.commit()

    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("preauth_session", path="/")
    resp.set_cookie(
        SESSION_COOKIE, sid, httponly=True, samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()), path="/",
    )
    return resp


@app.get("/logout")
@app.post("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        ip = _client_ip(request)
        ua_summary = _clean_ua(request.headers.get("user-agent"))
        client_target = f"keluar dari {ip}" + (f" ({ua_summary})" if ua_summary else "")
        _audit(db, user.username, "logout", client_target, "berhasil", meta={"ip": ip, "ua": request.headers.get("user-agent", ""), "browser": ua_summary})
        db.commit()
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        db.query(AppSession).filter(AppSession.sid == sid).delete(synchronize_session=False)
        db.commit()
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    resp.delete_cookie("preauth_session", path="/")
    return resp


# ---------------------------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)

    servers = db.query(Server).order_by(desc(Server.last_seen)).all()
    total = len(servers)
    up_count = 0
    down_services = 0
    ignored_services = 0
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
        # Sync problems terlebih dahulu agar status ignored diketahui
        srv._problem_level, srv._problems, _ph = sync_server_problems(
            db, srv, _problem_instances(srv, ex, srv._svc_data, db))
        active_probs = [p for p in srv._problems if not p.get("is_ignored")]
        danger_probs = [p for p in active_probs if p.get("severity") == "danger"]
        average_probs = [p for p in active_probs if p.get("severity") == "average"]
        warning_probs = [p for p in active_probs if p.get("severity") == "warning"]
        info_probs = [p for p in active_probs if p.get("severity") == "info"]
        ignored_probs = [p for p in srv._problems if p.get("is_ignored")]

        srv._danger_count = len(danger_probs)
        srv._average_count = len(average_probs)
        srv._warning_count = len(warning_probs)
        srv._info_count = len(info_probs)
        srv._ignored_count = len(ignored_probs)
        srv._danger_msgs = " • ".join(p.get("message", "") for p in danger_probs)
        srv._average_msgs = " • ".join(p.get("message", "") for p in average_probs)
        srv._warning_msgs = " • ".join(p.get("message", "") for p in warning_probs)
        srv._info_msgs = " • ".join(p.get("message", "") for p in info_probs)
        srv._ignored_msgs = " • ".join(p.get("message", "") for p in ignored_probs)

        ignored_keys = {p.get("key") for p in srv._problems if p.get("is_ignored")}
        svc_ignored_db = {s.service_name for s in services if getattr(s, "is_ignored", 0)}
        unignored_down = 0
        server_ignored_down = 0
        for d in srv._svc_data:
            if d.get("status") in ("down", "offline"):
                if f"service_down:{d['name']}" not in ignored_keys and d['name'] not in svc_ignored_db:
                    unignored_down += 1
                    down_services += 1
                else:
                    d["ignored"] = True
                    server_ignored_down += 1
                    ignored_services += 1
            elif d.get("name") in svc_ignored_db:
                d["ignored"] = True
        srv._unignored_down = unignored_down
        srv._ignored_down = server_ignored_down

        stale = _server_stale(srv)
        if stale:
            for d in srv._svc_data:
                d["status"] = "offline"
        if srv.is_maintenance:
            srv._status_label, srv._status_cls = "Pemeliharaan", "badge-warn"
        else:
            srv._status_label, srv._status_cls = _server_status(
                srv, stale, bool(srv._svc_data), any(d["status"] == "up" for d in srv._svc_data),
                has_unignored_down=(unignored_down > 0))
        latest_sys = (
            db.query(SystemSnapshot)
            .filter(SystemSnapshot.server_id == srv.id)
            .order_by(desc(SystemSnapshot.timestamp))
            .first()
        )
        srv._cpu = round(latest_sys.cpu, 1) if latest_sys else None
        srv._mem_pct = (
            round(latest_sys.mem_used / latest_sys.mem_total * 100, 1)
            if latest_sys and latest_sys.mem_total else None
        )
        srv._load1 = round(latest_sys.load1, 2) if (latest_sys and latest_sys.load1 is not None) else None

        hw = _get_hardware_specs_dict(srv, ex, latest_sys)
        cpu_cores = hw.get("cpu", {}).get("cores") or hw.get("cpu", {}).get("logical_cores")
        srv._cpu_cores_str = f"{cpu_cores} Core" if (srv.last_seen and cpu_cores) else "—"
        srv._platform = _classify_platform(hw.get("platform", {}), getattr(srv, "platform_override", None))
        d_tot, d_avail, d_pct = _extract_disk_stats(latest_sys.disks if latest_sys else None)
        srv._disk_total_str = d_tot
        srv._disk_avail_str = d_avail
        srv._disk_pct = d_pct
        srv._mem_total_str = _format_bytes_gb(latest_sys.mem_total if latest_sys else None)
        srv._mem_avail_str = _format_bytes_gb(latest_sys.mem_avail if latest_sys else None)
        srv._mem_used_str = _format_bytes_gb(latest_sys.mem_used if latest_sys else None)
        srv._uptime_str = _format_uptime_str(latest_sys.uptime_secs if latest_sys else None)
        srv._uptime_secs = latest_sys.uptime_secs if latest_sys else 0

        if srv._status_cls == "badge-up":
            up_count += 1

    last_metric = db.query(Metric.timestamp).order_by(desc(Metric.timestamp)).first()
    if last_metric:
        ts = last_metric[0]
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        last_update_secs = max(0, int((datetime.now(timezone.utc) - ts).total_seconds()))
    else:
        last_update_secs = -1

    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    group_counts = {}
    ungrouped_count = 0
    for srv in servers:
        if srv.group_name:
            group_counts[srv.group_name] = group_counts.get(srv.group_name, 0) + 1
        else:
            ungrouped_count += 1

    danger_total = sum(srv._danger_count for srv in servers)
    average_total = sum(srv._average_count for srv in servers)
    warning_total = sum(srv._warning_count for srv in servers)
    info_total = sum(srv._info_count for srv in servers)
    ignored_total = sum(srv._ignored_count for srv in servers)
    healthy_total = sum(1 for srv in servers if srv._status_cls == "badge-up" and (srv._danger_count + srv._average_count + srv._warning_count) == 0)

    problems_by_sev = {
        "danger": [],
        "average": [],
        "warning": [],
        "info": [],
        "ignored": [],
    }
    all_open_problems = []
    for srv in servers:
        for p in (srv._problems or []):
            is_ign = bool(p.get("is_ignored"))
            p_started = p.get("started_at")
            dur_str = "—"
            if p_started:
                diff_s = max(0, int((datetime.utcnow() - p_started).total_seconds()))
                if diff_s < 60: dur_str = f"{diff_s} dtk"
                elif diff_s < 3600: dur_str = f"{diff_s//60} mnt"
                elif diff_s < 86400: dur_str = f"{diff_s//3600} jam"
                else: dur_str = f"{diff_s//86400} hari"
            item = {
                "server_id": srv.id,
                "hostname": srv.hostname,
                "group_name": srv.group_name or "",
                "severity": p.get("severity", "warning"),
                "message": p.get("message", ""),
                "key": p.get("key", ""),
                "is_ignored": is_ign,
                "started_at": p_started.isoformat() if p_started else "",
                "started_at_str": p_started.strftime("%d %b %H:%M") if p_started else "—",
                "durasi": dur_str,
            }
            if is_ign:
                problems_by_sev["ignored"].append(item)
            else:
                sev = item["severity"]
                if sev in problems_by_sev:
                    problems_by_sev[sev].append(item)
                else:
                    problems_by_sev["warning"].append(item)
                all_open_problems.append(item)

    sev_order = {"danger": 0, "average": 1, "warning": 2, "info": 3}
    all_open_problems.sort(key=lambda p: (sev_order.get(p["severity"], 4), p["started_at"] or ""))

    top_cpu = sorted([s for s in servers if s._cpu is not None], key=lambda s: s._cpu, reverse=True)[:5]
    top_mem = sorted([s for s in servers if s._mem_pct is not None], key=lambda s: s._mem_pct, reverse=True)[:5]

    return tpl(request, "dashboard.html", {
        "user": user, "servers": servers, "total": total,
        "up_count": up_count, "down_count": total - up_count,
        "down_services": down_services, "ignored_services": ignored_services,
        "last_update_secs": last_update_secs,
        "all_groups": existing_groups,
        "all_tags": existing_tags,
        "group_counts": group_counts,
        "ungrouped_count": ungrouped_count,
        "danger_total": danger_total,
        "average_total": average_total,
        "warning_total": warning_total,
        "info_total": info_total,
        "ignored_total": ignored_total,
        "healthy_total": healthy_total,
        "all_open_problems": all_open_problems,
        "problems_by_sev": problems_by_sev,
        "top_cpu": top_cpu,
        "top_mem": top_mem,
        "global_thresholds": get_global_thresholds(db),
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
                "port": svc.port, "process": svc.process_name,
                "status": latest.status if latest else "unknown",
            })
        srv._problem_level, srv._problems, _ph = sync_server_problems(
            db, srv, _problem_instances(srv, ex, svc_data, db))
        ignored_keys = {p.get("key") for p in srv._problems if p.get("is_ignored")}
        svc_ignored_db = {s.service_name for s in services if getattr(s, "is_ignored", 0)}
        for d in svc_data:
            if f"service_down:{d['name']}" in ignored_keys or d['name'] in svc_ignored_db:
                d["ignored"] = True
        srv._svc_data = svc_data

        active_probs = [p for p in srv._problems if not p.get("is_ignored")]
        danger_probs = [p for p in active_probs if p.get("severity") == "danger"]
        average_probs = [p for p in active_probs if p.get("severity") == "average"]
        warning_probs = [p for p in active_probs if p.get("severity") == "warning"]
        info_probs = [p for p in active_probs if p.get("severity") == "info"]
        ignored_probs = [p for p in srv._problems if p.get("is_ignored")]
        srv._danger_count = len(danger_probs)
        srv._average_count = len(average_probs)
        srv._warning_count = len(warning_probs)
        srv._info_count = len(info_probs)
        srv._ignored_count = len(ignored_probs)
        srv._danger_msgs = " • ".join(p.get("message", "") for p in danger_probs)
        srv._average_msgs = " • ".join(p.get("message", "") for p in average_probs)
        srv._warning_msgs = " • ".join(p.get("message", "") for p in warning_probs)
        srv._info_msgs = " • ".join(p.get("message", "") for p in info_probs)
        srv._ignored_msgs = " • ".join(p.get("message", "") for p in ignored_probs)

        latest_sys = (
            db.query(SystemSnapshot)
            .filter(SystemSnapshot.server_id == srv.id)
            .order_by(desc(SystemSnapshot.timestamp))
            .first()
        )
        srv._cpu = round(latest_sys.cpu, 1) if latest_sys else None
        srv._mem_pct = (
            round(latest_sys.mem_used / latest_sys.mem_total * 100, 1)
            if latest_sys and latest_sys.mem_total else None
        )
        hw = _get_hardware_specs_dict(srv, ex, latest_sys)
        srv._platform = _classify_platform(hw.get("platform", {}), getattr(srv, "platform_override", None))

        unignored_down = [d for d in svc_data if d.get("status") in ("down", "offline") and not d.get("ignored")]
        if srv.is_maintenance:
            srv._status_label, srv._status_cls = "Pemeliharaan", "badge-warn"
        else:
            srv._status_label, srv._status_cls = _server_status(
                srv, not srv._online, bool(svc_data), any(d["status"] == "up" for d in svc_data),
                has_unignored_down=bool(unignored_down))

    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    group_counts = {}
    ungrouped_count = 0
    for srv in servers:
        if srv.group_name:
            group_counts[srv.group_name] = group_counts.get(srv.group_name, 0) + 1
        else:
            ungrouped_count += 1

    # Urutkan servers: grup bernama lebih dulu (abjad grup, lalu hostname), lalu tanpa grup (abjad hostname)
    servers.sort(key=lambda s: (0 if s.group_name else 1, (s.group_name or "").lower(), s.hostname.lower()))

    return tpl(request, "servers.html", {
        "user": user, "servers": servers,
        "all_groups": existing_groups,
        "all_tags": existing_tags,
        "group_counts": group_counts,
        "ungrouped_count": ungrouped_count,
    })


@app.get("/servers/add", response_class=HTMLResponse)
def server_add_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    global_th = get_global_thresholds(db)
    return tpl(request, "server_form.html", {
        "user": user, "server": None, "mode": "add",
        "existing_groups": existing_groups,
        "existing_tags": existing_tags,
        "global_thresholds": global_th,
        "custom_thresholds": {},
    })


@app.post("/servers/add")
def server_add_submit(
    request: Request,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    group_name: str = Form(default=""),
    tags: str = Form(default=""),
    platform_override: str = Form(default="auto"),
    is_proxmox_ha: int = Form(0),
    is_isolated_net: int = Form(0),
    allow_web_terminal: int = Form(0),
    th_cpu_warn: str = Form(default=""),
    th_cpu_danger: str = Form(default=""),
    th_ram_warn: str = Form(default=""),
    th_ram_danger: str = Form(default=""),
    th_disk_warn: str = Form(default=""),
    th_disk_danger: str = Form(default=""),
    th_swap_warn: str = Form(default=""),
    th_swap_danger: str = Form(default=""),
    th_ssh_fail_warn: str = Form(default=""),
    th_ssh_fail_danger: str = Form(default=""),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    hostname = _clean_str(hostname, "", 255)
    ip_address = _clean_str(ip_address, "", 45)[:45]
    group_name_clean = _clean_str(group_name, "", 64).strip()
    group_name = group_name_clean if group_name_clean and group_name_clean.lower() != "default" else None
    tags_clean = _clean_str(tags, "", 255).strip()
    tags = tags_clean if tags_clean else None
    if ip_address and not _validate_ip(ip_address):
        existing_groups, existing_tags = get_existing_groups_and_tags(db)
        return tpl(request, "server_form.html", {
            "user": user, "server": None, "mode": "add",
            "existing_groups": existing_groups,
            "existing_tags": existing_tags,
            "global_thresholds": get_global_thresholds(db),
            "custom_thresholds": {},
            "error": "Format IP address tidak valid. Gunakan IPv4 (contoh: 192.168.1.1) atau IPv6."
        })

    custom_th = {}
    for k, val in [("cpu_warn", th_cpu_warn), ("cpu_danger", th_cpu_danger),
                   ("ram_warn", th_ram_warn), ("ram_danger", th_ram_danger),
                   ("disk_warn", th_disk_warn), ("disk_danger", th_disk_danger),
                   ("swap_warn", th_swap_warn), ("swap_danger", th_swap_danger),
                   ("ssh_fail_warn", th_ssh_fail_warn), ("ssh_fail_danger", th_ssh_fail_danger)]:
        if val is not None and str(val).strip() != "":
            try:
                custom_th[k] = int(val) if "fail" in k else float(val)
            except ValueError:
                pass
    # Validasi dan auto-koreksi bila user terbalik mengisi warn > danger
    for metric in ("cpu", "ram", "disk", "swap", "ssh_fail"):
        w = custom_th.get(f"{metric}_warn")
        d = custom_th.get(f"{metric}_danger")
        if w is not None and d is not None and w > d:
            custom_th[f"{metric}_warn"], custom_th[f"{metric}_danger"] = d, w
    custom_th_json = json.dumps(custom_th) if custom_th else None

    plat_override_clean = (platform_override or "").strip().lower()
    if plat_override_clean not in ("baremetal", "vm", "lxc"):
        plat_override_clean = None

    raw = secrets.token_hex(32)
    srv = Server(
        hostname=hostname, ip_address=ip_address,
        group_name=group_name, tags=tags,
        is_proxmox_ha=1 if (is_proxmox_ha and plat_override_clean != "baremetal") else 0,
        platform_override=plat_override_clean,
        is_isolated_net=1 if is_isolated_net else 0,
        allow_web_terminal=1 if allow_web_terminal else 0,
        custom_thresholds=custom_th_json,
        api_key=hash_api_key(raw)
    )
    db.add(srv)
    _audit(db, user.username, "server_add", f"{hostname} ({ip_address})" + (f" [Grup: {group_name}]" if group_name else ""), "berhasil")
    db.commit()
    resp = tpl(request, "key_reveal.html", {"user": user, "server": srv, "api_key": raw})
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/servers/{sid}/edit", response_class=HTMLResponse)
def server_edit_page(request: Request, sid: int, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        return RedirectResponse("/servers", status_code=303)
    server._key_fp = api_key_fingerprint(server.api_key)
    existing_groups, existing_tags = get_existing_groups_and_tags(db)
    global_th = get_global_thresholds(db)
    custom_th = {}
    if server.custom_thresholds:
        try:
            custom_th = json.loads(server.custom_thresholds)
        except Exception:
            pass
    return tpl(request, "server_form.html", {
        "user": user, "server": server, "mode": "edit",
        "existing_groups": existing_groups,
        "existing_tags": existing_tags,
        "global_thresholds": global_th,
        "custom_thresholds": custom_th,
    })


@app.post("/servers/{sid}/edit")
def server_edit_submit(
    request: Request, sid: int,
    hostname: str = Form(...),
    ip_address: str = Form(...),
    group_name: str = Form(default=""),
    tags: str = Form(default=""),
    is_active: int = Form(1),
    platform_override: str = Form(default="auto"),
    is_proxmox_ha: int = Form(0),
    is_isolated_net: int = Form(0),
    allow_web_terminal: int = Form(0),
    th_cpu_warn: str = Form(default=""),
    th_cpu_danger: str = Form(default=""),
    th_ram_warn: str = Form(default=""),
    th_ram_danger: str = Form(default=""),
    th_disk_warn: str = Form(default=""),
    th_disk_danger: str = Form(default=""),
    th_swap_warn: str = Form(default=""),
    th_swap_danger: str = Form(default=""),
    th_ssh_fail_warn: str = Form(default=""),
    th_ssh_fail_danger: str = Form(default=""),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not (user.is_master_admin() or user.has_perm("can_manage_servers")):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if server:
        hostname = _clean_str(hostname, server.hostname, 255)
        ip_address = _clean_str(ip_address, server.ip_address, 45)[:45]
        group_name_clean = _clean_str(group_name, "", 64).strip()
        group_name = group_name_clean if group_name_clean and group_name_clean.lower() != "default" else None
        tags_clean = _clean_str(tags, "", 255).strip()
        tags = tags_clean if tags_clean else None
        if ip_address and not _validate_ip(ip_address):
            server._key_fp = api_key_fingerprint(server.api_key)
            existing_groups, existing_tags = get_existing_groups_and_tags(db)
            return tpl(request, "server_form.html", {
                "user": user, "server": server, "mode": "edit",
                "existing_groups": existing_groups,
                "existing_tags": existing_tags,
                "global_thresholds": get_global_thresholds(db),
                "custom_thresholds": {},
                "error": "Format IP address tidak valid. Gunakan IPv4 (contoh: 192.168.1.1) atau IPv6."
            })

        custom_th = {}
        for k, val in [("cpu_warn", th_cpu_warn), ("cpu_danger", th_cpu_danger),
                       ("ram_warn", th_ram_warn), ("ram_danger", th_ram_danger),
                       ("disk_warn", th_disk_warn), ("disk_danger", th_disk_danger),
                       ("swap_warn", th_swap_warn), ("swap_danger", th_swap_danger),
                       ("ssh_fail_warn", th_ssh_fail_warn), ("ssh_fail_danger", th_ssh_fail_danger)]:
            if val is not None and str(val).strip() != "":
                try:
                    custom_th[k] = int(val) if "fail" in k else float(val)
                except ValueError:
                    pass
        # Validasi dan auto-koreksi bila user terbalik mengisi warn > danger
        for metric in ("cpu", "ram", "disk", "swap", "ssh_fail"):
            w = custom_th.get(f"{metric}_warn")
            d = custom_th.get(f"{metric}_danger")
            if w is not None and d is not None and w > d:
                custom_th[f"{metric}_warn"], custom_th[f"{metric}_danger"] = d, w
        custom_th_json = json.dumps(custom_th) if custom_th else None

        plat_override_clean = (platform_override or "").strip().lower()
        if plat_override_clean not in ("baremetal", "vm", "lxc"):
            plat_override_clean = None

        server.hostname = hostname
        server.ip_address = ip_address
        server.group_name = group_name
        server.tags = tags
        server.custom_thresholds = custom_th_json
        server.is_active = 1 if is_active else 0
        server.platform_override = plat_override_clean
        server.is_proxmox_ha = 1 if (is_proxmox_ha and plat_override_clean != "baremetal") else 0
        server.is_isolated_net = 1 if is_isolated_net else 0
        server.allow_web_terminal = 1 if allow_web_terminal else 0
        _audit(db, user.username, "server_edit",
               f"id={server.id} {server.hostname} ({server.ip_address})" + (f" [Grup: {group_name}]" if group_name else ""), "berhasil")
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
    if not user or not user.is_master_admin():
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
    if not user or not user.is_master_admin():
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
    recent_cutoff = datetime.utcnow() - timedelta(seconds=25)
    recent_completed_cmds = (
        db.query(Command).filter(
            Command.server_id == sid,
            Command.status == "success",
            Command.executed_at >= recent_cutoff,
        ).order_by(desc(Command.executed_at)).all()
    )
    recent_svc_cmds = {}
    for rc in recent_completed_cmds:
        if rc.service_id and rc.service_id not in recent_svc_cmds:
            recent_svc_cmds[rc.service_id] = rc

    latest_map = _latest_metrics(db, (s.id for s in services))
    for svc in services:
        latest = latest_map.get(svc.id)
        svc._status = latest.status if latest else "unknown"
        recent_cmd = recent_svc_cmds.get(svc.id)
        if recent_cmd:
            if recent_cmd.action in ("stop", "service_stop"):
                svc._status = "down"
            elif recent_cmd.action in ("start", "service_start") and svc._status != "up":
                svc._status = "up"
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
    actions = _get_server_actions(db, sid, limit=50)
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    svc_data = [{"name": s.service_name, "status": getattr(s, "_status", "unknown")}
                for s in services]
    problem_level, open_problems, problem_history = sync_server_problems(
        db, server, _problem_instances(server, extra, svc_data, db))
    _enrich_problems_for_ui(open_problems, services, extra, user)
    prob_by_key = {p["key"]: p for p in open_problems}
    for svc in services:
        svc._problem = prob_by_key.get(f"service_down:{svc.service_name}")
        svc._is_ignored = bool(getattr(svc, "is_ignored", 0)) or (bool(svc._problem and svc._problem.get("is_ignored")))
        if getattr(svc, "_status", None) == "up" and getattr(svc, "ignore_mode", None) == "incident":
            svc._is_ignored = False
    top_p = {"cpu": [], "mem": []}
    if extra and extra.top_procs:
        try:
            top_p = json.loads(extra.top_procs)
        except Exception:
            pass

    cron_data = {"jobs": [], "timers": []}
    if extra and extra.cron_jobs:
        try:
            cron_data = json.loads(extra.cron_jobs)
        except Exception:
            pass

    fw_data = {"backend": "unknown", "status": "inactive", "rules": [], "blocked_ips": []}
    if extra and extra.firewall:
        try:
            fw_data = json.loads(extra.firewall)
        except Exception:
            pass

    ports_data = []
    if extra and extra.listening_ports:
        try:
            ports_data = json.loads(extra.listening_ports)
        except Exception:
            pass

    ssl_data = []
    if extra and extra.ssl_certs:
        try:
            ssl_data = json.loads(extra.ssl_certs)
        except Exception:
            pass

    sys_logs_data = []
    if extra and extra.system_logs:
        try:
            sys_logs_data = json.loads(extra.system_logs)
            if isinstance(sys_logs_data, list):
                # Urutkan selalu dari waktu terbaru ke terlama (descending)
                sys_logs_data.sort(key=lambda x: str(x.get("time") or ""), reverse=True)
        except Exception:
            pass

    accounts_data = []
    if extra and extra.accounts:
        try:
            accounts_data = json.loads(extra.accounts)
        except Exception:
            pass

    latest_sn = db.query(SystemSnapshot).filter(SystemSnapshot.server_id == sid).order_by(desc(SystemSnapshot.timestamp)).first()
    hw_specs = _get_hardware_specs_dict(server, extra, latest_sn)
    platform_info = _classify_platform(hw_specs.get("platform", {}), getattr(server, "platform_override", None))

    return tpl(request, "services.html", {
        "user": user, "server": server, "services": services, "commands": commands, "actions": actions,
        "agent_version": extra.agent_version if extra else None,
        "is_agent_outdated": _is_agent_outdated(extra.agent_version if extra else None, settings.APP_VERSION),
        "os_label": extra.os_label if extra else None,
        "kernel": extra.kernel if extra else None,
        "is_online": not _server_stale(server),
        "problem_level": problem_level, "open_problems": open_problems,
        "problem_history": problem_history,
        "top_procs": top_p,
        "accounts": accounts_data,
        "cron_jobs": cron_data,
        "firewall": fw_data,
        "listening_ports": ports_data,
        "ssl_certs": ssl_data,
        "system_logs": sys_logs_data,
        "hardware_specs": hw_specs,
        "platform_info": platform_info,
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
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_services"):
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
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
    server = db.query(Server).filter(Server.id == sid).first()
    _audit(db, user.username, "service_add", f"{server.hostname if server else sid}:{svc.service_name}", f"port {svc.port}", server_id=sid)
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
    if not user or not user.has_perm("can_services"):
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Akses ditolak: Anda tidak memiliki wewenang Layanan"}), status_code=403, media_type="application/json")
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="layanan")
    if err_resp:
        return err_resp
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
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    if existing:
        if is_json:
            return Response(json.dumps({"ok": True, "detail": f"Perintah restart {svc.service_name} sedang diproses."}), media_type="application/json")
        return RedirectResponse(f"/servers/{sid}/services?restarted=1", status_code=303)

    db.add(Command(
        server_id=sid, service_id=svc_id, action="restart", status="pending",
        issued_by=user.username,
    ))
    # Otomatis aktifkan kembali pemantauan saat admin merestart layanan (hanya bila bukan mode permanen)
    if getattr(svc, "ignore_mode", None) != "permanent":
        svc.is_ignored = 0
        svc.ignored_until = None
        svc.ignored_reason = None
        svc.ignore_mode = None
        prob = db.query(ServerProblem).filter(
            ServerProblem.server_id == sid,
            ServerProblem.key == f"service_down:{svc.service_name}",
            ServerProblem.resolved_at.is_(None),
        ).first()
        if prob:
            prob.is_ignored = 0
            prob.ignored_until = None
            prob.ignored_reason = None
            prob.ignore_mode = None
            prob.updated_at = datetime.utcnow()
    db.commit()
    if is_json:
        return Response(json.dumps({"ok": True, "detail": f"Perintah restart {svc.service_name} telah dikirim ke Agen Pantau."}), media_type="application/json")
    return RedirectResponse(f"/servers/{sid}/services?restarted=1", status_code=303)


def _service_action(request: Request, sid: int, svc_id: int, action: str, db, csrf_token: str = ""):
    """Helper bersama untuk start/stop layanan."""
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_services"):
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Akses ditolak: Anda tidak memiliki wewenang Layanan"}), status_code=403, media_type="application/json")
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="layanan")
    if err_resp:
        return err_resp
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
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    label_id = {"start": "mulai", "stop": "hentikan"}.get(action, action)
    if existing:
        if is_json:
            return Response(json.dumps({"ok": True, "detail": f"Perintah {label_id} {svc.service_name} sedang diproses."}), media_type="application/json")
        return RedirectResponse(f"/servers/{sid}/services?restarted=1", status_code=303)

    # Cek apakah layanan sudah dalam kondisi yang diminta
    latest_m = _latest_metrics(db, [svc_id]).get(svc_id)
    cur_st = latest_m.status if latest_m else "unknown"
    if action == "stop" and cur_st == "down":
        if is_json:
            return Response(json.dumps({"ok": True, "detail": f"Layanan {svc.service_name} sudah dalam kondisi berhenti."}), media_type="application/json")
        return RedirectResponse(f"/servers/{sid}/services", status_code=303)
    if action == "start" and cur_st == "up":
        if is_json:
            return Response(json.dumps({"ok": True, "detail": f"Layanan {svc.service_name} sudah dalam kondisi aktif."}), media_type="application/json")
        return RedirectResponse(f"/servers/{sid}/services", status_code=303)

    db.add(Command(
        server_id=sid, service_id=svc_id, action=action, status="pending",
        issued_by=user.username,
    ))
    server = db.query(Server).filter(Server.id == sid).first()
    _audit(db, user.username, f"service_{action}",
           f"{server.hostname if server else sid}:{svc.service_name}", "dikirim ke agen", server_id=sid)
    if action == "start":
        # Otomatis aktifkan kembali pemantauan saat admin memulai/menyalakan layanan (hanya bila bukan mode permanen)
        if getattr(svc, "ignore_mode", None) != "permanent":
            svc.is_ignored = 0
            svc.ignored_until = None
            svc.ignored_reason = None
            svc.ignore_mode = None
            prob = db.query(ServerProblem).filter(
                ServerProblem.server_id == sid,
                ServerProblem.key == f"service_down:{svc.service_name}",
                ServerProblem.resolved_at.is_(None),
            ).first()
            if prob:
                prob.is_ignored = 0
                prob.ignored_until = None
                prob.ignored_reason = None
                prob.ignore_mode = None
                prob.updated_at = datetime.utcnow()
    db.commit()
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
    """Antrekan command mitigasi atau server action tanpa service terkait."""
    params_str = json.dumps(params) if params else None
    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == action,
            Command.status == "pending",
            Command.params == params_str,
        )
        .first()
    )
    if not existing:
        db.add(Command(
            server_id=sid, service_id=None, action=action,
            params=params_str, status="pending",
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
    if not user or not user.has_perm("can_firewall"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="masalah")
    if err_resp:
        return err_resp
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


@app.post("/servers/{sid}/firewall/block")
def firewall_block_ip(
    request: Request, sid: int,
    ip: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Blokir manual sebuah IP dari tab Firewall."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_firewall"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="firewall")
    if err_resp:
        return err_resp
    ip_clean = ip.strip()
    try:
        a = ipaddress.ip_address(ip_clean)
        if a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified or a.is_reserved or ip_clean == server.ip_address:
            return RedirectResponse(f"/servers/{sid}/services?action=invalid_ip", status_code=303)
    except ValueError:
        return RedirectResponse(f"/servers/{sid}/services?action=invalid_ip", status_code=303)

    _enqueue_mitigation(db, sid, "block_ip", {"ips": [ip_clean]}, issued_by=user.username)
    _audit(db, user.username, "firewall_block", f"{server.hostname}: blokir {ip_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    return RedirectResponse(f"/servers/{sid}/services?action=block", status_code=303)


@app.post("/servers/{sid}/firewall/unblock")
def firewall_unblock_ip(
    request: Request, sid: int,
    ip: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Buka blokir sebuah IP dari tab Firewall."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_firewall"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="firewall")
    if err_resp:
        return err_resp
    ip_clean = ip.strip()
    _enqueue_mitigation(db, sid, "unblock_ip", {"ips": [ip_clean]}, issued_by=user.username)
    _audit(db, user.username, "firewall_unblock", f"{server.hostname}: buka blokir {ip_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    return RedirectResponse(f"/servers/{sid}/services?action=unblock", status_code=303)


@app.post("/servers/{sid}/firewall/enable")
def firewall_enable(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Aktifkan firewall (UFW) via agen."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_firewall"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="firewall")
    if err_resp:
        return err_resp
    _enqueue_mitigation(db, sid, "firewall_enable", issued_by=user.username)
    _audit(db, user.username, "firewall_enable", f"{server.hostname}: aktifkan firewall (UFW)", "dikirim ke agen", server_id=sid)
    db.commit()
    return RedirectResponse(f"/servers/{sid}/services?action=fw_enabled", status_code=303)


@app.post("/servers/{sid}/firewall/disable")
def firewall_disable(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Nonaktifkan firewall (UFW) via agen."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_firewall"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="firewall")
    if err_resp:
        return err_resp
    _enqueue_mitigation(db, sid, "firewall_disable", issued_by=user.username)
    _audit(db, user.username, "firewall_disable", f"{server.hostname}: nonaktifkan firewall (UFW)", "dikirim ke agen", server_id=sid)
    db.commit()
    return RedirectResponse(f"/servers/{sid}/services?action=fw_disabled", status_code=303)


@app.post("/servers/{sid}/firewall/reload")
def firewall_reload(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Muat ulang (reload) aturan firewall via agen."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_firewall"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="firewall")
    if err_resp:
        return err_resp
    _enqueue_mitigation(db, sid, "firewall_reload", issued_by=user.username)
    _audit(db, user.username, "firewall_reload", f"{server.hostname}: reload firewall", "dikirim ke agen", server_id=sid)
    db.commit()
    return RedirectResponse(f"/servers/{sid}/services?action=fw_reloaded", status_code=303)


@app.post("/servers/{sid}/processes/kill")
def process_kill(
    request: Request, sid: int,
    pid: int = Form(...),
    pname: str = Form(default=""),
    sig: str = Form(default="TERM"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Kirim sinyal hentikan proses (kill process) ke agen."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_processes"):
        if request.headers.get("accept") == "application/json":
            return JSONResponse({"ok": False, "detail": "Akses ditolak: Anda tidak memiliki wewenang Manajer Tugas"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    is_json = request.headers.get("accept") == "application/json"
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="proses")
    if err_resp:
        return err_resp

    sig_clean = sig.strip().upper()
    if sig_clean not in ("TERM", "KILL", "15", "9", "STOP", "19", "CONT", "18"):
        sig_clean = "TERM"

    sig_labels = {
        "TERM": "penghentian normal (SIGTERM)",
        "15": "penghentian normal (SIGTERM)",
        "KILL": "paksa henti (SIGKILL)",
        "9": "paksa henti (SIGKILL)",
        "STOP": "tangguhkan/pause (SIGSTOP)",
        "19": "tangguhkan/pause (SIGSTOP)",
        "CONT": "lanjutkan/resume (SIGCONT)",
        "18": "lanjutkan/resume (SIGCONT)",
    }
    sig_desc = sig_labels.get(sig_clean, f"sinyal SIG{sig_clean}")

    if pid <= 1:
        if request.headers.get("accept") == "application/json":
            return JSONResponse({"ok": False, "detail": "PID dilindungi atau tidak valid!"}, status_code=400)
        return RedirectResponse(f"/servers/{sid}/services?action=invalid_pid", status_code=303)

    pname_clean = (pname or "").strip()[:50]
    _enqueue_mitigation(
        db, sid, "kill_process",
        {"pid": str(pid), "signal": sig_clean, "pname": pname_clean},
        issued_by=user.username
    )
    _audit(
        db, user.username, "kill_process",
        f"PID {pid} ({pname_clean or 'proses'})",
        f"sinyal SIG{sig_clean} dikirim ke agen", server_id=sid
    )
    db.commit()

    if request.headers.get("accept") == "application/json":
        return JSONResponse({
            "ok": True,
            "detail": f"Perintah penghentian PID {pid} ({pname_clean}) dengan sinyal SIG{sig_clean} dikirim ke agen."
        })
    return RedirectResponse(f"/servers/{sid}/services?action=process_killed&pid={pid}", status_code=303)


@app.post("/servers/{sid}/problems/restart-agent")
def problem_restart_agent(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Mitigasi: restart agen (agent_pantau) jika tidak lagi melapor."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_services"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="masalah")
    if err_resp:
        return err_resp
    _enqueue_mitigation(db, sid, "restart_agent", issued_by=user.username)
    return RedirectResponse(f"/servers/{sid}/services?action=agent", status_code=303)


def _get_agent_code_and_sha256() -> tuple[bytes, str, str]:
    """Mengambil bytes berkas agen terbaru, hash kriptografis SHA-256, dan versi."""
    candidate_paths = [
        Path(__file__).parent.parent / "package" / "opt" / "pantau" / "agent" / "agent_pantau.py",
        Path(__file__).parent.parent / "agent" / "agent_pantau.py",
        Path("/opt/pantau/agent/agent_pantau.py"),
    ]
    for p in candidate_paths:
        if p.is_file():
            try:
                data = p.read_bytes()
                h = hashlib.sha256(data).hexdigest()
                return data, h, settings.APP_VERSION
            except Exception as e:
                logger.warning(f"[AGENT CODE] Gagal membaca {p}: {e}")
    raise HTTPException(status_code=404, detail="Berkas agen tidak ditemukan di dashboard")


@app.post("/servers/{sid}/agent/update")
def server_agent_update(
    request: Request, sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Kirim perintah pembaruan otomatis agen (Push Update OTA) dengan verifikasi kriptografi SHA-256 (admin)."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_ota"):
        if request.headers.get("accept") == "application/json" or request.headers.get("x-requested-with") == "XMLHttpRequest":
            raise HTTPException(status_code=403, detail="Akses ditolak: Anda tidak memiliki wewenang Dorong Pembaruan Agen (OTA)")
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    is_json = (
        request.headers.get("accept") == "application/json"
        or request.headers.get("x-requested-with") == "XMLHttpRequest"
    )
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="layanan")
    if err_resp:
        return err_resp

    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == "update_agent",
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    if existing:
        msg = "Pembaruan agen sedang diproses atau dalam antrean."
        if is_json:
            return JSONResponse({"ok": True, "status": "already_pending", "message": msg})
        return RedirectResponse(f"/servers/{sid}/services?action=agent_updating", status_code=303)

    _, sha256_hash, version = _get_agent_code_and_sha256()
    base_url = str(request.base_url).rstrip("/")
    download_url = f"{base_url}/api/agent/latest-code"

    ota_params = {
        "url": download_url,
        "sha256": sha256_hash,
        "version": version,
    }

    _enqueue_mitigation(db, sid, "update_agent", params=ota_params, issued_by=user.username)
    _audit(
        db, user.username, "agent_update",
        f"OTA v{version} (SHA: {sha256_hash[:8]}…)",
        f"Push OTA v{version} (SHA256: {sha256_hash[:12]}…)", server_id=sid
    )
    db.commit()

    msg = f"Perintah Push Update (OTA) v{version} berhasil dikirim ke {server.hostname} dengan verifikasi SHA-256."
    if is_json:
        return JSONResponse({
            "ok": True,
            "status": "dispatched",
            "version": version,
            "sha256": sha256_hash,
            "message": msg
        })
    return RedirectResponse(f"/servers/{sid}/services?action=agent_updated", status_code=303)


def _host_control(request: Request, sid: int, db: Session, action: str, csrf_token: str = "") -> Response:
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_server_control"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json)
    if err_resp:
        return err_resp
    if action == "poweroff_host" and getattr(server, "is_proxmox_ha", 0):
        _audit(db, user.username, "poweroff_host",
               f"{server.hostname} ({server.ip_address})", "Ditolak: Server terproteksi Proxmox HA", server_id=sid)
        db.commit()
        if is_json:
            return JSONResponse({
                "ok": False,
                "detail": "Server terproteksi Proxmox HA."
            }, status_code=400)
        at_epoch = int(datetime.now(timezone.utc).timestamp())
        return RedirectResponse(f"/servers/{sid}/services?action=poweroff_ha_blocked&at={at_epoch}", status_code=303)
    _enqueue_mitigation(db, sid, action, issued_by=user.username)
    _audit(db, user.username, action,
           f"{server.hostname} ({server.ip_address})", "dikirim ke agen", server_id=sid)
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


# ---------------------------------------------------------------------------
# Pengelolaan Pengguna Sistem (Linux Accounts)
# ---------------------------------------------------------------------------
@app.post("/servers/{sid}/system-users/create")
def server_user_create(
    request: Request, sid: int,
    username: str = Form(...),
    password: str = Form(default=""),
    shell: str = Form(default="/bin/bash"),
    is_sudo: bool = Form(default=False),
    comment: str = Form(default="Dibuat via Pantau Server"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()
    params = {
        "username": u_clean,
        "shell": shell.strip() or "/bin/bash",
        "is_sudo": "1" if is_sudo else "0",
        "comment": comment.strip() or "Dibuat via Pantau Server",
    }
    if password.strip():
        params["password"] = password.strip()

    _enqueue_mitigation(db, sid, "user_create", params, issued_by=user.username)
    _audit(db, user.username, "user_create", f"{server.hostname}: buat user {u_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah pembuatan pengguna '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=akun", status_code=303)


@app.post("/servers/{sid}/system-users/lock")
def server_user_lock(
    request: Request, sid: int,
    username: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()
    _enqueue_mitigation(db, sid, "user_lock", {"username": u_clean}, issued_by=user.username)
    _audit(db, user.username, "user_lock", f"{server.hostname}: kunci user {u_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah kunci akun '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=akun", status_code=303)


@app.post("/servers/{sid}/system-users/unlock")
def server_user_unlock(
    request: Request, sid: int,
    username: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()
    _enqueue_mitigation(db, sid, "user_unlock", {"username": u_clean}, issued_by=user.username)
    _audit(db, user.username, "user_unlock", f"{server.hostname}: buka kunci user {u_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah buka kunci akun '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=akun", status_code=303)


@app.post("/servers/{sid}/system-users/delete")
def server_user_delete(
    request: Request, sid: int,
    username: str = Form(...),
    remove_home: bool = Form(default=False),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()
    _enqueue_mitigation(db, sid, "user_delete", {"username": u_clean, "remove_home": "1" if remove_home else "0"}, issued_by=user.username)
    _audit(db, user.username, "user_delete", f"{server.hostname}: hapus user {u_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah hapus akun '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=akun", status_code=303)


# ---------------------------------------------------------------------------
# Pengelolaan Tugas Terjadwal (Cron Jobs)
# ---------------------------------------------------------------------------
@app.post("/servers/{sid}/cron/add")
def server_cron_add(
    request: Request, sid: int,
    ident: str = Form(...),
    minute: str = Form(default="*"),
    hour: str = Form(default="*"),
    dom: str = Form(default="*"),
    month: str = Form(default="*"),
    dow: str = Form(default="*"),
    user_target: str = Form(default="root"),
    command: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    id_clean = ident.strip()
    cmd_clean = command.strip()
    _enqueue_mitigation(db, sid, "cron_add", {
        "ident": id_clean,
        "minute": minute.strip() or "*",
        "hour": hour.strip() or "*",
        "dom": dom.strip() or "*",
        "month": month.strip() or "*",
        "dow": dow.strip() or "*",
        "user": user_target.strip() or "root",
        "command": cmd_clean,
    }, issued_by=user.username)
    _audit(db, user.username, "cron_add", f"{server.hostname}: tambah cron {id_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah tambah tugas cron '{id_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=cron", status_code=303)


@app.post("/servers/{sid}/cron/toggle")
def server_cron_toggle(
    request: Request, sid: int,
    ident: str = Form(...),
    mode: str = Form(default="enable"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    id_clean = ident.strip()
    m_clean = mode.strip().lower()
    _enqueue_mitigation(db, sid, "cron_toggle", {"ident": id_clean, "mode": m_clean}, issued_by=user.username)
    _audit(db, user.username, "cron_toggle", f"{server.hostname}: {m_clean} cron {id_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah ubah status cron '{id_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=cron", status_code=303)


@app.post("/servers/{sid}/cron/delete")
def server_cron_delete(
    request: Request, sid: int,
    ident: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    id_clean = ident.strip()
    _enqueue_mitigation(db, sid, "cron_delete", {"ident": id_clean}, issued_by=user.username)
    _audit(db, user.username, "cron_delete", f"{server.hostname}: hapus cron {id_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah hapus cron '{id_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=cron", status_code=303)


@app.post("/servers/{sid}/cron/run")
def server_cron_run(
    request: Request, sid: int,
    user_target: str = Form(default="root"),
    command: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    cmd_clean = command.strip()
    u_clean = user_target.strip() or "root"
    _enqueue_mitigation(db, sid, "cron_run_now", {"user": u_clean, "command": cmd_clean}, issued_by=user.username)
    _audit(db, user.username, "cron_run_now", f"{server.hostname}: uji jalankan cron ({u_clean}: {cmd_clean[:50]})", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": "Perintah uji jalankan tugas cron dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=cron", status_code=303)


# ---------------------------------------------------------------------------
# Pengelolaan Aturan Port Firewall
# ---------------------------------------------------------------------------
@app.post("/servers/{sid}/ports/rule")
def server_port_rule(
    request: Request, sid: int,
    port: str = Form(...),
    rule: str = Form(default="deny"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_firewall"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="ports")
    if err_resp:
        return err_resp
    p_clean = port.strip()
    r_clean = rule.strip().lower()
    pnum = p_clean.split("/")[0]
    if pnum in ("22", "8400") and r_clean in ("deny", "block"):
        if is_json: return JSONResponse({"ok": False, "detail": f"Port {pnum} dilindungi dan dilarang diblokir!"}, status_code=400)
        return RedirectResponse(f"/servers/{sid}/services?tab=ports&error=protected_port", status_code=303)

    _enqueue_mitigation(db, sid, "firewall_port_rule", {"port": p_clean, "rule": r_clean}, issued_by=user.username)
    _audit(db, user.username, "firewall_port_rule", f"{server.hostname}: aturan port {p_clean} ({r_clean})", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Aturan port '{p_clean}' ({r_clean}) dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=ports", status_code=303)


# ---------------------------------------------------------------------------
# Pengelolaan Path Sertifikat SSL Kustom
# ---------------------------------------------------------------------------
@app.post("/servers/{sid}/ssl/add-path")
def server_ssl_add_path(
    request: Request, sid: int,
    path: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_ssl"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        if is_json: return JSONResponse({"ok": False, "detail": "Server tidak ditemukan"}, status_code=404)
        return RedirectResponse("/servers", status_code=303)
    path_clean = path.strip()
    _enqueue_mitigation(db, sid, "ssl_path_add", {"path": path_clean}, issued_by=user.username)
    _audit(db, user.username, "ssl_path_add", f"{server.hostname}: tambah path SSL {path_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah tambah path sertifikat SSL '{path_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=ssl", status_code=303)


@app.post("/servers/{sid}/ssl/remove-path")
def server_ssl_remove_path(
    request: Request, sid: int,
    path: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_ssl"):
        if is_json: return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        if is_json: return JSONResponse({"ok": False, "detail": "Server tidak ditemukan"}, status_code=404)
        return RedirectResponse("/servers", status_code=303)
    path_clean = path.strip()
    _enqueue_mitigation(db, sid, "ssl_path_remove", {"path": path_clean}, issued_by=user.username)
    _audit(db, user.username, "ssl_path_remove", f"{server.hostname}: hapus path SSL {path_clean}", "dikirim ke agen", server_id=sid)
    db.commit()
    if is_json: return JSONResponse({"ok": True, "detail": f"Perintah hapus path sertifikat SSL '{path_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}/services?tab=ssl", status_code=303)


@app.post("/servers/{sid}/services/{svc_id}/delete")
def service_delete(
    request: Request, sid: int, svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_services"):
        if is_json:
            return Response(json.dumps({"ok": False, "detail": "Akses ditolak: Izin kontrol layanan diperlukan"}), status_code=403, media_type="application/json")
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if svc:
        server = db.query(Server).filter(Server.id == sid).first()
        svc_name = svc.service_name
        # Hapus seketika masalah terbuka untuk layanan ini agar tidak lagi dilaporkan
        db.query(ServerProblem).filter(
            ServerProblem.server_id == sid,
            ServerProblem.key.in_([f"service_down:{svc_name}", f"svc_no_data:{svc_name}"]),
            ServerProblem.resolved_at.is_(None)
        ).delete(synchronize_session=False)

        _audit(db, user.username, "service_delete",
               f"{server.hostname if server else sid}:{svc_name}", "berhasil", server_id=sid)
        db.delete(svc)
        db.commit()
        if is_json:
            return Response(json.dumps({"ok": True, "detail": f"Service {svc_name} dihapus"}), media_type="application/json")
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
    filter_group = (request.query_params.get("group") or "").strip()

    open_problems, recent_resolved = problems_aggregate(db)
    if filter_sid:
        open_problems = [p for p in open_problems if p["server_id"] == filter_sid]
        recent_resolved = [p for p in recent_resolved if p["server_id"] == filter_sid]
    if filter_group:
        if filter_group == "__none__":
            open_problems = [p for p in open_problems if not p.get("group_name")]
            recent_resolved = [p for p in recent_resolved if not p.get("group_name")]
        else:
            open_problems = [p for p in open_problems if (p.get("group_name") or "") == filter_group]
            recent_resolved = [p for p in recent_resolved if (p.get("group_name") or "") == filter_group]

    all_servers = db.query(Server).order_by(Server.hostname).all()
    servers_total = len(all_servers)
    active_open_servers = {p["server_id"] for p in open_problems if not p.get("is_ignored")}
    existing_groups, existing_tags = get_existing_groups_and_tags(db)

    global_thresholds = get_global_thresholds(db)

    res_durations = []
    auto_res_cnt = 0
    manual_res_cnt = 0
    for p in recent_resolved:
        st = p.get("started_at")
        res = p.get("resolved_at")
        if isinstance(st, datetime) and isinstance(res, datetime):
            res_durations.append(max(0, int((res - st).total_seconds())))
        if p.get("acknowledged_by"):
            manual_res_cnt += 1
        elif p.get("resolved_note") in ("auto", "server_offline"):
            auto_res_cnt += 1
        else:
            auto_res_cnt += 1
    avg_secs = int(sum(res_durations) / len(res_durations)) if res_durations else 0
    avg_mttr_str = _fmt_duration(datetime.min, datetime.min + timedelta(seconds=avg_secs)) if avg_secs > 0 else "—"

    resolved_stats = {
        "total": len(recent_resolved),
        "avg_mttr": avg_mttr_str,
        "auto_count": auto_res_cnt,
        "manual_count": manual_res_cnt,
    }

    return tpl(request, "problems.html", {
        "user": user,
        "open_problems": open_problems,
        "recent_resolved": recent_resolved,
        "resolved_stats": resolved_stats,
        "danger_open": sum(1 for p in open_problems if p["severity"] == "danger" and not p.get("is_ignored")),
        "average_open": sum(1 for p in open_problems if p["severity"] == "average" and not p.get("is_ignored")),
        "warning_open": sum(1 for p in open_problems if p["severity"] == "warning" and not p.get("is_ignored")),
        "info_open": sum(1 for p in open_problems if p["severity"] == "info" and not p.get("is_ignored")),
        "ignored_open": sum(1 for p in open_problems if p.get("is_ignored")),
        "ok_count": servers_total - len(active_open_servers),
        "all_servers": all_servers,
        "filter_sid": filter_sid,
        "filter_group": filter_group,
        "all_groups": existing_groups,
        "all_tags": existing_tags,
        "global_thresholds": global_thresholds,
        "default_thresholds": DEFAULT_THRESHOLDS,
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
OFFLINE_AFTER_SECONDS = 15
# Batas output apt update/upgrade yang disimpan/streaming (praktis tak terpotong;
# MEDIUMTEXT di DB kuota 16MB, ini masih jauh di bawahnya).
APT_STREAM_MAXCHARS = 4_000_000
APT_STREAM_MAXLINES = 120_000

# Ambang batas masalah default (Bawaan Pabrik)
DEFAULT_THRESHOLDS = {
    "cpu_warn": 85.0,
    "cpu_danger": 95.0,
    "ram_warn": 85.0,
    "ram_danger": 95.0,
    "disk_warn": 90.0,
    "disk_danger": 95.0,
    "swap_warn": 80.0,
    "swap_danger": 92.0,
    "ssh_fail_warn": 5,
    "ssh_fail_danger": 12,
}

# Alias kompatibilitas
SECURITY_DANGER_FAILED = 12
SECURITY_DANGER_INVALID = 4
SECURITY_WARNING_FAILED = 5
PROBLEM_RANK = {"ok": 0, "info": 1, "warning": 2, "average": 3, "danger": 4}
FRESH_SNAP_SECS = 90
RAM_DANGER_PCT = 95.0
RAM_WARNING_PCT = 85.0
SWAP_DANGER_PCT = 92.0
SWAP_WARNING_PCT = 80.0
CPU_DANGER_PCT = 95.0
CPU_WARNING_PCT = 85.0
DISK_DANGER_PCT = 95.0
DISK_WARNING_PCT = 90.0


def get_global_thresholds(db: Session | None = None) -> dict:
    """Ambil ambang batas global dari tabel system_settings (fallback ke DEFAULT_THRESHOLDS)."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
        if row and row.value:
            data = json.loads(row.value)
            res = dict(DEFAULT_THRESHOLDS)
            for k in res:
                if k in data and data[k] is not None and str(data[k]).strip() != "":
                    try:
                        res[k] = int(data[k]) if "fail" in k else float(data[k])
                    except (ValueError, TypeError):
                        pass
            return res
    except Exception as e:
        logger.warning("[thresholds] Gagal membaca global thresholds: %s", e)
    finally:
        if close_db:
            db.close()
    return dict(DEFAULT_THRESHOLDS)


def get_server_thresholds(srv, db: Session | None = None) -> dict:
    """Ambil ambang batas efektif untuk server tertentu (per-server override -> global -> default)."""
    global_th = get_global_thresholds(db)
    if not srv or not getattr(srv, "custom_thresholds", None):
        return global_th
    try:
        raw = srv.custom_thresholds
        custom = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(custom, dict):
            res = dict(global_th)
            for k in res:
                if k in custom and custom[k] is not None and str(custom[k]).strip() != "":
                    try:
                        res[k] = int(custom[k]) if "fail" in k else float(custom[k])
                    except (ValueError, TypeError):
                        pass
            return res
    except Exception:
        pass
    return global_th

RAM_TIP = ("Cek proses pemakan memori: sudo ps aux --sort=-%mem | head | Hentikan/mulai ulang proses: "
           "sudo systemctl restart <unit> | Tambah alokasi RAM. Server bisa crash/OOM bila dibiarkan.")
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
    if key.startswith("service_down:"):
        return 0   # Pemulihan layanan langsung seketika tanpa jeda penahanan
    if key == "agent_conflict":
        return 120  # Pertahankan peringatan konflik setidaknya 2 menit setelah stabil
    return 0


def _build_problem_context(key: str, srv, **kwargs) -> str | None:
    """Susun payload JSON diagnostik terstruktur dwibahasa (ID & EN) untuk ServerProblem.context."""
    try:
        now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

        # 1. Konflik Agen (Split-Brain Multi-IP)
        if key == "agent_conflict":
            ips = kwargs.get("ips") or []
            return json.dumps({
                "diagnosa": "Konflik API Key Agen (Split-Brain Telemetri)",
                "diagnosa_en": "Agent API Key Conflict (Split-Brain Telemetry)",
                "penyebab": f"Server {srv.hostname} menerima telemetri aktif dari {len(ips)} alamat IP berbeda ({', '.join(ips)}) secara bersamaan dalam waktu kurang dari 2 menit. Mesin kemungkinan telah dikloning atau API key dipasang pada lebih dari satu host.",
                "penyebab_en": f"Server {srv.hostname} receives active telemetry from {len(ips)} distinct IP addresses ({', '.join(ips)}) simultaneously within 2 minutes. Likely caused by a cloned VM or duplicate agent installation with the same API key.",
                "dampak": "Metrik status layanan dan performa sistem berfluktuasi/flapping tidak menentu karena host melaporkan status yang berbeda.",
                "dampak_en": "Service status and system performance metrics flap erratically because different hosts report conflicting states.",
                "data_teknis": {
                    "conflicting_ips": ips,
                    "server_id": srv.id,
                    "server_hostname": srv.hostname,
                    "waktu_deteksi": now_str,
                },
                "rekomendasi": [
                    f"Periksa host di jaringan dengan alamat IP: {', '.join(ips)}.",
                    "Jika salah satu host merupakan hasil klon VM / template pengujian, matikan agen: sudo systemctl stop agent_pantau && sudo systemctl disable agent_pantau.",
                    "Jika kedua host harus dipantau terpisah, daftarkan server baru di Pantau Server untuk memperoleh API Key yang terpisah."
                ],
                "rekomendasi_en": [
                    f"Inspect hosts in your network with IP addresses: {', '.join(ips)}.",
                    "If one host is a cloned VM or staging template, stop the agent: sudo systemctl stop agent_pantau && sudo systemctl disable agent_pantau.",
                    "If both hosts must be monitored independently, add a new server in Pantau Server to generate a dedicated API Key."
                ],
                "perintah_diagnosa": [
                    f"ssh <user>@{ips[0]} 'sudo systemctl status agent_pantau'" if ips else "",
                    f"ssh <user>@{ips[-1]} 'sudo systemctl status agent_pantau'" if len(ips) > 1 else "",
                ]
            }, ensure_ascii=False)

        # 2. Layanan Mati (Service Down)
        if key.startswith("service_down:"):
            svc_name = kwargs.get("service_name") or key.split(":", 1)[1]
            port = kwargs.get("port")
            proc = kwargs.get("proc")
            health_msg = kwargs.get("health_msg")
            conflict_ips = kwargs.get("conflict_ips")
            penyebab = f"Layanan {svc_name} tidak mendengarkan (listening) pada port {port or 'terkait'} atau proses tidak ditemukan."
            penyebab_en = f"Service {svc_name} is not listening on port {port or 'associated'} or process was not found running."
            if conflict_ips and len(conflict_ips) > 1:
                penyebab += f" Terdeteksi juga konflik multi-IP ({', '.join(conflict_ips)}) yang menyebabkan status layanan berfluktuasi."
                penyebab_en += f" Multi-IP agent conflict ({', '.join(conflict_ips)}) detected, causing service status to flap."
            elif health_msg:
                penyebab += f" Rincian pesan: {health_msg}"
                penyebab_en += f" Detail: {health_msg}"
            return json.dumps({
                "diagnosa": f"Layanan {svc_name} Tidak Aktif (DOWN)",
                "diagnosa_en": f"Service {svc_name} Inactive (DOWN)",
                "penyebab": penyebab,
                "penyebab_en": penyebab_en,
                "dampak": f"Aplikasi atau pengguna tidak dapat mengakses layanan {svc_name}" + (f" pada port {port}." if port else "."),
                "dampak_en": f"Clients or dependent systems cannot access service {svc_name}" + (f" on port {port}." if port else "."),
                "data_teknis": {
                    "service_name": svc_name,
                    "port": port,
                    "process_name": proc,
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "health_message": health_msg,
                    "conflicting_ips": conflict_ips,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Periksa status layanan: sudo systemctl status {svc_name}",
                    f"Lihat riwayat log galat layanan: sudo journalctl -u {svc_name} -n 50 --no-pager",
                    f"Pastikan port listening: ss -tulpn | grep :{port}" if port else f"Periksa proses: pgrep -fa {proc or svc_name}",
                    f"Coba mulai ulang layanan: sudo systemctl restart {svc_name}"
                ],
                "rekomendasi_en": [
                    f"Check service status: sudo systemctl status {svc_name}",
                    f"Inspect service error logs: sudo journalctl -u {svc_name} -n 50 --no-pager",
                    f"Verify listening port: ss -tulpn | grep :{port}" if port else f"Check process: pgrep -fa {proc or svc_name}",
                    f"Restart service: sudo systemctl restart {svc_name}"
                ],
                "perintah_diagnosa": [
                    f"sudo systemctl status {svc_name}",
                    f"sudo journalctl -u {svc_name} -n 50 --no-pager",
                    f"ss -tulpn | grep :{port}" if port else f"pgrep -fa {proc or svc_name}",
                    f"sudo systemctl restart {svc_name}"
                ]
            }, ensure_ascii=False)

        # 3. Layanan Belum Ada Data (Service Unknown / No Data)
        if key.startswith("svc_no_data:"):
            svc_name = kwargs.get("service_name") or key.split(":", 1)[1]
            port = kwargs.get("port")
            return json.dumps({
                "diagnosa": f"Layanan {svc_name} Belum Memiliki Data",
                "diagnosa_en": f"Service {svc_name} Has No Reported Data",
                "penyebab": f"Agen di server belum mendeteksi status atau metrik untuk layanan {svc_name}. Port atau proses mungkin belum aktif saat siklus pemindaian.",
                "penyebab_en": f"Agent on the server has not captured status or metrics for service {svc_name}. The port or process might not have been open during scan.",
                "dampak": "Metrik ketersediaan layanan belum dapat dihitung secara akurat.",
                "dampak_en": "Service availability metrics cannot be accurately computed.",
                "data_teknis": {
                    "service_name": svc_name,
                    "port": port,
                    "server_hostname": srv.hostname,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Pastikan layanan berjalan: sudo systemctl status {svc_name}",
                    f"Pastikan port listening: ss -tlnp | grep :{port}" if port else f"Cek proses: pgrep -fa {svc_name}",
                    "Tunggu siklus pemindaian agen berikutnya (berjalan tiap beberapa detik)."
                ],
                "rekomendasi_en": [
                    f"Ensure service is running: sudo systemctl status {svc_name}",
                    f"Ensure port is listening: ss -tlnp | grep :{port}" if port else f"Check process: pgrep -fa {svc_name}",
                    "Wait for the next agent reporting cycle (runs every few seconds)."
                ],
                "perintah_diagnosa": [
                    f"sudo systemctl status {svc_name}",
                    f"ss -tulpn | grep :{port}" if port else f"pgrep -fa {svc_name}",
                ]
            }, ensure_ascii=False)

        # 4. RAM Kritis / Tinggi
        if key in ("ram_usage", "ram_critical", "ram_high"):
            pct = kwargs.get("pct", 0)
            used = kwargs.get("used", 0)
            total = kwargs.get("total", 0)
            is_crit = ("critical" in key) or (kwargs.get("severity") == "danger") or (pct >= kwargs.get("threshold", 95))
            return json.dumps({
                "diagnosa": f"Konsumsi Memori RAM Kritis ({pct:.1f}%)" if is_crit else f"Konsumsi Memori RAM Tinggi ({pct:.1f}%)",
                "diagnosa_en": f"Critical RAM Memory Consumption ({pct:.1f}%)" if is_crit else f"High RAM Memory Consumption ({pct:.1f}%)",
                "penyebab": f"Pemakaian memori RAM mencapai {pct:.1f}% ({_fmt_size(used)} dari {_fmt_size(total)}). Sistem berisiko memicu kernel Out-Of-Memory (OOM Killer).",
                "penyebab_en": f"RAM memory usage reached {pct:.1f}% ({_fmt_size(used)} of {_fmt_size(total)}). The host is at risk of invoking the Linux OOM Killer.",
                "dampak": "Sistem melambat drastis, thrashing swap meningkat, dan service penting dapat dimatikan mendadak oleh kernel OOM Killer.",
                "dampak_en": "Extreme system slowdown, severe swap thrashing, and critical services risk being terminated abruptly by the OOM Killer.",
                "data_teknis": {
                    "mem_used": used,
                    "mem_total": total,
                    "mem_percent": round(pct, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Buka tab Proses untuk memeriksa proses pemakan memori teratas.",
                    "Jalankan di server: sudo ps aux --sort=-%mem | head -15",
                    "Mulai ulang aplikasi atau daemon yang memicu kebocoran memori (memory leak).",
                    "Pertimbangkan menambah alokasi RAM fisik atau swap bila beban kerja normal."
                ],
                "rekomendasi_en": [
                    "Open the Processes tab to inspect top memory-consuming processes.",
                    "Run on host: sudo ps aux --sort=-%mem | head -15",
                    "Restart daemon or application causing memory leaks.",
                    "Consider scaling up RAM capacity or swap space if standard workload demands it."
                ],
                "perintah_diagnosa": [
                    "free -h",
                    "ps aux --sort=-%mem | head -15",
                    "sudo journalctl -k -g 'oom' -n 20 --no-pager"
                ]
            }, ensure_ascii=False)

        # 5. Swap Kritis / Tinggi
        if key in ("swap_usage", "swap_critical", "swap_high"):
            pct = kwargs.get("pct", 0)
            used = kwargs.get("used", 0)
            total = kwargs.get("total", 0)
            is_crit = ("critical" in key) or (kwargs.get("severity") == "danger") or (pct >= kwargs.get("threshold", 92))
            return json.dumps({
                "diagnosa": f"Kapasitas Swap Hampir Penuh ({pct:.1f}%)" if is_crit else f"Pemakaian Swap Tinggi ({pct:.1f}%)",
                "diagnosa_en": f"Swap Space Nearly Full ({pct:.1f}%)" if is_crit else f"High Swap Space Usage ({pct:.1f}%)",
                "penyebab": f"Pemakaian swap mencapai {pct:.1f}% ({_fmt_size(used)} dari {_fmt_size(total)}). Memori RAM fisik menipis sehingga kernel memindahkan halaman memori ke disk.",
                "penyebab_en": f"Swap usage reached {pct:.1f}% ({_fmt_size(used)} of {_fmt_size(total)}). Physical RAM is exhausted, forcing kernel paging onto disk.",
                "dampak": "Kinerja I/O disk melonjak, latency sistem dan aplikasi meningkat tajam karena kecepatan swap jauh lebih lambat dari RAM.",
                "dampak_en": "Severe disk I/O bottleneck; system response latency spikes sharply due to disk-based memory paging.",
                "data_teknis": {
                    "swap_used": used,
                    "swap_total": total,
                    "swap_percent": round(pct, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Periksa proses yang menggunakan banyak memori: sudo ps aux --sort=-%mem | head -15",
                    "Bebaskan memori dengan me-restart proses yang boros RAM.",
                    "Bersihkan cache jika aman: sudo sync && sudo sysctl -w vm.drop_caches=3",
                    "Tingkatkan alokasi RAM server."
                ],
                "rekomendasi_en": [
                    "Inspect high memory processes: sudo ps aux --sort=-%mem | head -15",
                    "Release memory by restarting excessive memory consumer services.",
                    "Drop safe filesystem caches if needed: sudo sync && sudo sysctl -w vm.drop_caches=3",
                    "Upgrade physical RAM allocation."
                ],
                "perintah_diagnosa": [
                    "free -h",
                    "swapon --show",
                    "vmstat 1 5"
                ]
            }, ensure_ascii=False)

        # 6. CPU Jenuh / Tinggi
        if key in ("cpu_usage", "cpu_saturated", "cpu_high"):
            cpu_avg = kwargs.get("cpu_avg", 0)
            cpu_max = kwargs.get("cpu_max", 0)
            is_crit = ("saturated" in key) or (kwargs.get("severity") == "danger") or (cpu_avg >= kwargs.get("threshold", 95))
            return json.dumps({
                "diagnosa": "Saturasi Beban Prosesor (CPU Saturated)" if is_crit else "Beban Prosesor Tinggi (CPU High)",
                "diagnosa_en": "Processor Saturation (CPU Saturated)" if is_crit else "High Processor Load (CPU High)",
                "penyebab": f"Beban CPU rata-rata mencapai {cpu_avg:.1f}% (puncak {cpu_max:.1f}%) dalam rentang observasi terakhir.",
                "penyebab_en": f"Average CPU utilization reached {cpu_avg:.1f}% (peak {cpu_max:.1f}%) during recent observation window.",
                "dampak": "Antrean thread sistem melambat, response time layanan meningkat, potensi request timeout.",
                "dampak_en": "System thread queues stall, response latency deteriorates, elevated risk of connection timeouts.",
                "data_teknis": {
                    "cpu_avg": round(cpu_avg, 1),
                    "cpu_max": round(cpu_max, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Buka tab Proses untuk melihat proses dengan pemakaian CPU tertinggi.",
                    "Identifikasi proses intensif: top -b -n 1 | head -20",
                    "Periksa apakah ada loop eksekusi tak berujung (infinite loop) atau thread worker yang menggantung."
                ],
                "rekomendasi_en": [
                    "Open Processes tab to identify top CPU consumers.",
                    "Inspect active processes: top -b -n 1 | head -20",
                    "Investigate stuck worker threads or infinite execution loops."
                ],
                "perintah_diagnosa": [
                    "top -b -n 1 | head -20",
                    "ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -15"
                ]
            }, ensure_ascii=False)

        # 7. Partisi Disk Kritis / Tinggi
        if key.startswith("disk_usage:") or key.startswith("disk_critical:") or key.startswith("disk_high:"):
            mount = kwargs.get("mount") or key.split(":", 1)[1]
            used = kwargs.get("used", 0)
            total = kwargs.get("total", 0)
            pct = kwargs.get("pct", 0)
            is_crit = ("critical" in key) or (kwargs.get("severity") == "danger") or (pct >= kwargs.get("threshold", 95))
            return json.dumps({
                "diagnosa": f"Penyimpanan Partisi {mount} Hampir Penuh ({pct:.0f}%)" if is_crit else f"Penyimpanan Partisi {mount} Terisi Tinggi ({pct:.0f}%)",
                "diagnosa_en": f"Disk Partition {mount} Nearly Full ({pct:.0f}%)" if is_crit else f"Disk Partition {mount} High Usage ({pct:.0f}%)",
                "penyebab": f"Penggunaan partisi {mount} mencapai {pct:.0f}% ({_fmt_size(used)} terpakai dari kapasitas {_fmt_size(total)}).",
                "penyebab_en": f"Partition {mount} utilization reached {pct:.0f}% ({_fmt_size(used)} used out of {_fmt_size(total)}).",
                "dampak": "Aplikasi tidak dapat membuat file baru, database dapat read-only atau crash, sistem logging terhenti.",
                "dampak_en": "Applications cannot write new files, databases risk read-only state or crash, system logging halts.",
                "data_teknis": {
                    "mount_point": mount,
                    "disk_used": used,
                    "disk_total": total,
                    "disk_percent": round(pct, 1),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    f"Periksa penggunaan direktori terbesar: sudo du -xh --max-depth=2 {mount} | sort -rh | head -20",
                    "Bersihkan berkas log systemd lama: sudo journalctl --vacuum-size=200M",
                    "Bersihkan cache paket: sudo apt clean",
                    "Hapus berkas temporary lama di /tmp dan /var/tmp."
                ],
                "rekomendasi_en": [
                    f"Find largest directories: sudo du -xh --max-depth=2 {mount} | sort -rh | head -20",
                    "Vacuum journal logs: sudo journalctl --vacuum-size=200M",
                    "Clean APT package cache: sudo apt clean",
                    "Purge stale temporary files in /tmp and /var/tmp."
                ],
                "perintah_diagnosa": [
                    f"df -h {mount}",
                    f"sudo du -xh --max-depth=2 {mount} | sort -rh | head -15",
                    "sudo journalctl --disk-usage"
                ]
            }, ensure_ascii=False)

        # 8. Serangan SSH / Login Gagal
        if key in ("security_danger", "failed_logins"):
            failed = kwargs.get("failed", 0)
            invalid = kwargs.get("invalid", 0)
            source_ips = kwargs.get("source_ips") or {}
            top_ips = sorted(source_ips.items(), key=lambda x: x[1] if isinstance(x[1], int) else 0, reverse=True)[:10]
            ip_list = [f"{ip} ({cnt}x)" for ip, cnt in top_ips]
            is_crit = (key == "security_danger") or (kwargs.get("severity") == "danger") or (failed >= kwargs.get("threshold", 12)) or (invalid >= 4)
            return json.dumps({
                "diagnosa": "Indikasi Serangan SSH Brute-Force" if is_crit else "Percobaan Login SSH Gagal Repetitif",
                "diagnosa_en": "Suspected SSH Brute-Force Attack" if is_crit else "Repetitive Failed SSH Login Attempts",
                "penyebab": f"Terdeteksi {failed} percobaan login SSH gagal dan {invalid} percobaan user tidak valid dari {len(source_ips)} alamat IP sumber.",
                "penyebab_en": f"Detected {failed} failed SSH logins and {invalid} invalid username attempts originating from {len(source_ips)} source IPs.",
                "dampak": "Potensi pembobolan kredensial akun server bila password lemah, serta beban koneksi SSH yang tinggi.",
                "dampak_en": "Security risk of unauthorized account breach if weak passwords exist, alongside network socket overhead on sshd.",
                "data_teknis": {
                    "total_failed": failed,
                    "invalid_users": invalid,
                    "total_source_ips": len(source_ips),
                    "top_attacker_ips": ip_list,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Gunakan tombol 'Blokir IP' pada kolom tindakan untuk memblokir IP penyerang via iptables.",
                    "Pasang dan aktifkan fail2ban: sudo apt install fail2ban && sudo systemctl enable --now fail2ban",
                    "Perketat konfigurasi SSH (/etc/ssh/sshd_config): PasswordAuthentication no, gunakan SSH Key.",
                    "Ganti port default SSH dari port 22 ke port khusus non-standar."
                ],
                "rekomendasi_en": [
                    "Use the 'Block IPs' button in action column to immediately drop attacker IPs via iptables.",
                    "Install and enable fail2ban: sudo apt install fail2ban && sudo systemctl enable --now fail2ban",
                    "Harden SSH daemon (/etc/ssh/sshd_config): set PasswordAuthentication no, enforce SSH Keys.",
                    "Change default SSH listening port from 22 to a custom high port."
                ],
                "perintah_diagnosa": [
                    "sudo journalctl -u ssh -n 50 --no-pager",
                    "sudo iptables -L INPUT -v -n --line-numbers",
                    "sudo fail2ban-client status sshd"
                ]
            }, ensure_ascii=False)

        # 9. Agen Stale (Offline / Agen Tidak Melapor)
        if key == "agent_stale":
            return json.dumps({
                "diagnosa": "Agen Tidak Melapor",
                "diagnosa_en": "Agent Not Reporting",
                "penyebab": f"Agen Pantau pada server {srv.hostname} tidak mengirimkan telemetri metrik ke server pusat. Faktor penyebab mencakup server fisik/virtual mati atau dimatikan, koneksi jaringan terputus, service agent_pantau terhenti, atau terjadi pemblokiran firewall dan kendala keamanan.",
                "penyebab_en": f"Monitoring agent on server {srv.hostname} stopped transmitting telemetry to central server. Causes include powered-off / offline host, network disconnection, halted agent service, or firewall / security rule blocking.",
                "dampak": "Metrik kinerja hardware (CPU, RAM, Disk), status layanan, dan telemetri keamanan server tidak dapat diperbarui secara live di dashboard.",
                "dampak_en": "Hardware performance metrics (CPU, RAM, Disk), service states, and security telemetry are no longer live on the dashboard.",
                "data_teknis": {
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "terakhir_melapor": srv.last_seen.strftime("%Y-%m-%d %H:%M:%S UTC") if srv.last_seen else "Belum pernah",
                    "durasi_tidak_melapor_detik": kwargs.get("sec_silent"),
                    "level_eskalasi": (kwargs.get("escalation_level") or "").upper(),
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Verifikasi status daya fisik atau virtual mesin: pastikan server dalam kondisi aktif (Power ON).",
                    "Uji konektivitas jaringan: lakukan ping atau uji jangkauan SSH ke alamat host server.",
                    "Lakukan inspeksi keamanan & firewall: pastikan port telemetri atau akses keluar server tidak diblokir.",
                    "Bila server aktif dan dapat diakses, periksa status service agen: sudo systemctl status agent_pantau",
                    "Periksa log sistem dan agen untuk diagnosa mendalam: sudo journalctl -u agent_pantau -n 30 --no-pager"
                ],
                "rekomendasi_en": [
                    "Check host machine power status: ensure server is powered ON.",
                    "Check network connectivity: ping host or test console / SSH reachability.",
                    "Inspect security & firewall rules: verify agent outbound connection or SSH port is not blocked.",
                    "If machine is running, inspect agent daemon: sudo systemctl status agent_pantau",
                    "Inspect agent logs for detailed diagnosis: sudo journalctl -u agent_pantau -n 30 --no-pager"
                ],
                "perintah_diagnosa": [
                    "ping -c 3 " + (srv.ip_address or "127.0.0.1"),
                    "ssh -o ConnectTimeout=5 " + (srv.ip_address or srv.hostname),
                    "sudo systemctl status agent_pantau",
                    "sudo journalctl -u agent_pantau -n 30 --no-pager"
                ]
            }, ensure_ascii=False)

        # 10. Paket OS Butuh Pembaruan (APT Updates)
        if key == "apt_updates":
            upg_count = kwargs.get("upgradable", 0)
            return json.dumps({
                "diagnosa": f"{upg_count} Paket Pembaruan OS Tersedia",
                "diagnosa_en": f"{upg_count} OS Package Updates Available",
                "penyebab": f"Repositori sistem melaporkan terdapat {upg_count} paket software/kernel yang siap di-upgrade, termasuk potensi patch keamanan.",
                "penyebab_en": f"System package repositories report {upg_count} upgradable software/kernel packages, potentially including critical security patches.",
                "dampak": "Sistem berisiko terhadap kerentanan keamanan yang telah ditambal pada versi terbaru.",
                "dampak_en": "Host remains vulnerable to publicly known CVEs and software defects resolved in upstream updates.",
                "data_teknis": {
                    "paket_upgradable": upg_count,
                    "server_hostname": srv.hostname,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Gunakan tombol 'Update OS' pada antarmuka Pantau Server untuk menjalankan pembaruan otomatis.",
                    "Atau jalankan secara manual di server: sudo apt update && sudo apt upgrade -y",
                    "Periksa apakah diperlukan reboot setelah kernel diperbarui."
                ],
                "rekomendasi_en": [
                    "Use the 'Update OS' button in the dashboard to execute automated package updates.",
                    "Alternatively run manually on host: sudo apt update && sudo apt upgrade -y",
                    "Check if host reboot is required after kernel packages update."
                ],
                "perintah_diagnosa": [
                    "apt list --upgradable",
                    "sudo apt update && sudo apt upgrade -s"
                ]
            }, ensure_ascii=False)

        # 11. Agen Perlu Pembaruan (Agent Outdated)
        if key == "agent_outdated":
            agent_ver = kwargs.get("agent_version") or getattr(srv, "_agent_version", None) or "lama"
            app_ver = kwargs.get("app_version") or settings.APP_VERSION
            return json.dumps({
                "diagnosa": f"Versi Agen Pantau Usang (v{agent_ver})",
                "diagnosa_en": f"Outdated Pantau Agent Version (v{agent_ver})",
                "penyebab": f"Agen pemantau di host {srv.hostname} berjalan pada versi v{agent_ver}, sedangkan dashboard pusat berada pada versi v{app_ver}. Fitur telemetri terbaru, stabilitas proses snapshot, dan perbaikan agen belum aktif pada host ini.",
                "penyebab_en": f"Monitoring agent on host {srv.hostname} is running version v{agent_ver}, while central dashboard is running v{app_ver}. Latest telemetry capabilities, snapshot stability, and agent patches are not active on this host.",
                "dampak": "Metrik kinerja snapshot mungkin tidak lengkap dan berisiko mengalami anomali kompatibilitas.",
                "dampak_en": "System metrics telemetry may be incomplete and risks protocol discrepancies with the central server.",
                "data_teknis": {
                    "versi_agen_klien": f"v{agent_ver}",
                    "versi_dashboard_pusat": f"v{app_ver}",
                    "server_hostname": srv.hostname,
                    "server_ip": srv.ip_address,
                    "waktu_kejadian": now_str,
                },
                "rekomendasi": [
                    "Jalankan perintah pembaruan agen otomatis di terminal server klien.",
                    "Pastikan daemon agent_pantau kembali aktif setelah pembaruan: sudo systemctl status agent_pantau",
                    "Muat ulang dashboard setelah agen berhasil mengirimkan telemetri versi baru."
                ],
                "rekomendasi_en": [
                    "Execute the automated agent update command on the client server terminal.",
                    "Verify agent_pantau service is active following update: sudo systemctl status agent_pantau",
                    "Reload dashboard once the agent transmits updated telemetry."
                ],
                "perintah_diagnosa": [
                    "sudo curl -fsSL -o /opt/pantau/agent/agent_pantau.py https://raw.githubusercontent.com/azhuka/pantau-server/master/package/opt/pantau/agent/agent_pantau.py && sudo systemctl restart agent_pantau.service",
                    "sudo systemctl status agent_pantau",
                    "python3 /opt/pantau/agent/agent_pantau.py --version"
                ]
            }, ensure_ascii=False)

    except Exception as e:
        logger.warning("[CONTEXT] Gagal menyusun konteks masalah %s: %s", key, e)
    return None



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
SVC_DOWN_TIP = ("Cek status: sudo systemctl status {name} | Mulai ulang: "
                "sudo systemctl restart {name} | Log: journalctl -u {name} -n 50")
SVC_NODATA_TIP = "Pastikan service benar-benar ada & port terbuka (ss -tlnp); agen memindai ulang tiap siklus."
AGENT_STALE_TIP = ("Agen tidak melapor — mulai ulang: sudo systemctl restart agent_pantau | "
                   "Log: journalctl -u agent_pantau -n 30")
AGENT_OUTDATED_TIP = (
    "Versi agen di server ini lebih lama dari dashboard. Update via terminal server klien: "
    "sudo curl -fsSL -o /opt/pantau/agent/agent_pantau.py "
    "https://raw.githubusercontent.com/azhuka/pantau-server/master/package/opt/pantau/agent/agent_pantau.py "
    "&& sudo systemctl restart agent_pantau.service"
)


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

    th = get_server_thresholds(srv, db)

    # Kunci masalah yang saat ini aktif terbuka untuk server ini
    open_keys = {
        r[0] for r in db.query(ServerProblem.key).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).all()
    }

    # 1. Evaluasi Memori RAM (Unified Key: ram_usage)
    recent_mems = [
        (s.mem_used / s.mem_total * 100)
        for s in snaps[:3]
        if (s.mem_total or 0) > 0 and s.mem_used is not None
    ]
    if recent_mems:
        cur_ram = recent_mems[0]
        mem_total, mem_used = latest.mem_total or 0, latest.mem_used or 0
        is_ram_open = "ram_usage" in open_keys
        should_emit_ram = False
        ram_sev = "warning"

        if is_ram_open:
            if cur_ram >= th["ram_danger"]:
                should_emit_ram = True
                ram_sev = "danger"
            elif cur_ram >= th["ram_warn"]:
                should_emit_ram = True
                ram_sev = "warning"
        else:
            if len(recent_mems) >= 3 and all(m >= th["ram_warn"] for m in recent_mems):
                should_emit_ram = True
                ram_avg = sum(recent_mems) / len(recent_mems)
                if cur_ram >= th["ram_danger"] and ram_avg >= th["ram_danger"]:
                    ram_sev = "danger"
                else:
                    ram_sev = "warning"

        if should_emit_ram:
            active_th = th["ram_danger"] if ram_sev == "danger" else th["ram_warn"]
            label_text = f"RAM HAMPIR PENUH: {cur_ram:.0f}% (ambang {active_th:.0f}%)" if ram_sev == "danger" else f"RAM tinggi: {cur_ram:.0f}% (ambang {active_th:.0f}%)"
            inst.append({
                "key": "ram_usage",
                "severity": ram_sev,
                "message": f"{label_text} ({_fmt_size(mem_used)} / {_fmt_size(mem_total)})",
                "tip": RAM_TIP,
                "event_at": snaps[min(len(snaps) - 1, 2)].timestamp if not is_ram_open else None,
                "context": _build_problem_context("ram_usage", srv, pct=cur_ram, used=mem_used, total=mem_total, threshold=active_th, severity=ram_sev),
            })

    # 2. Evaluasi Swap Disk (Unified Key: swap_usage)
    recent_swaps = [
        (s.swap_used / s.swap_total * 100)
        for s in snaps[:3]
        if (s.swap_total or 0) > 0 and s.swap_used is not None
    ]
    if recent_swaps:
        cur_swap = recent_swaps[0]
        swap_total, swap_used = latest.swap_total or 0, latest.swap_used or 0
        is_swap_open = "swap_usage" in open_keys
        should_emit_swap = False
        swap_sev = "warning"

        if is_swap_open:
            if cur_swap >= th["swap_danger"]:
                should_emit_swap = True
                swap_sev = "danger"
            elif cur_swap >= th["swap_warn"]:
                should_emit_swap = True
                swap_sev = "warning"
        else:
            if len(recent_swaps) >= 3 and all(s >= th["swap_warn"] for s in recent_swaps):
                should_emit_swap = True
                swap_avg = sum(recent_swaps) / len(recent_swaps)
                if cur_swap >= th["swap_danger"] and swap_avg >= th["swap_danger"]:
                    swap_sev = "danger"
                else:
                    swap_sev = "warning"

        if should_emit_swap:
            active_th = th["swap_danger"] if swap_sev == "danger" else th["swap_warn"]
            label_text = f"Swap hampir penuh: {cur_swap:.0f}% (ambang {active_th:.0f}%) — RAM menipis" if swap_sev == "danger" else f"Swap terpakai tinggi: {cur_swap:.0f}% (ambang {active_th:.0f}%)"
            inst.append({
                "key": "swap_usage",
                "severity": swap_sev,
                "message": label_text,
                "tip": SWAP_TIP,
                "event_at": snaps[min(len(snaps) - 1, 2)].timestamp if not is_swap_open else None,
                "context": _build_problem_context("swap_usage", srv, pct=cur_swap, used=swap_used, total=swap_total, threshold=active_th, severity=swap_sev),
            })

    # 3. Evaluasi Prosesor CPU (Unified Key: cpu_usage)
    recent_cpus = [s.cpu for s in snaps[:3] if s.cpu is not None]
    if recent_cpus:
        cur_cpu = recent_cpus[0]
        recent_avg = sum(recent_cpus) / len(recent_cpus)
        is_cpu_open = "cpu_usage" in open_keys
        should_emit_cpu = False
        cpu_sev = "warning"

        if is_cpu_open:
            if cur_cpu >= th["cpu_danger"] or recent_avg >= th["cpu_danger"]:
                should_emit_cpu = True
                cpu_sev = "danger"
            elif cur_cpu >= th["cpu_warn"] or recent_avg >= th["cpu_warn"]:
                should_emit_cpu = True
                cpu_sev = "warning"
        else:
            if len(recent_cpus) >= 3 and (all(c >= th["cpu_warn"] for c in recent_cpus) or recent_avg >= th["cpu_warn"]):
                should_emit_cpu = True
                if recent_avg >= th["cpu_danger"] and cur_cpu >= th["cpu_danger"]:
                    cpu_sev = "danger"
                else:
                    cpu_sev = "warning"

        if should_emit_cpu:
            active_th = th["cpu_danger"] if cpu_sev == "danger" else th["cpu_warn"]
            label_text = f"CPU jenuh/saturasi: {cur_cpu:.0f}% (ambang {active_th:.0f}%) (rata-rata {recent_avg:.0f}%)" if cpu_sev == "danger" else f"CPU tinggi: {cur_cpu:.0f}% (ambang {active_th:.0f}%) (rata-rata {recent_avg:.0f}%)"
            inst.append({
                "key": "cpu_usage",
                "severity": cpu_sev,
                "message": label_text,
                "tip": CPU_TIP,
                "event_at": snaps[min(len(snaps) - 1, 2)].timestamp if not is_cpu_open else None,
                "context": _build_problem_context("cpu_usage", srv, cpu_avg=recent_avg, cpu_max=cur_cpu, threshold=active_th, severity=cpu_sev),
            })

    disks = None
    if latest.disks:
        try:
            disks = json.loads(latest.disks)
        except (TypeError, ValueError):
            disks = None
    for d in disks or []:
        mount = d.get("mount", "?")
        if d.get("is_ro"):
            inst.append({
                "key": f"disk_ro:{mount}", "severity": "danger",
                "message": f"Partisi disk {mount} READ-ONLY (sistem berkas terkunci — operasi tulis ditolak!)",
                "tip": f"Filesystem beralih ke mode read-only akibat proteksi kernel/error I/O. Cek kernel: 'dmesg -T | grep -i ext4'. Lakukan remount: 'sudo mount -o remount,rw {mount}'.",
                "context": _build_problem_context(f"disk_ro:{mount}", srv, mount=mount),
            })
        total, used = d.get("total") or 0, d.get("used") or 0
        if total <= 0:
            continue
        dpct = used / total * 100 if total else 0
        if dpct >= th["disk_danger"]:
            inst.append({
                "key": f"disk_usage:{mount}", "severity": "danger",
                "message": f"Disk {mount} HAMPIR PENUH: {dpct:.0f}% (ambang {th['disk_danger']:.0f}%) ({_fmt_size(used)} / {_fmt_size(total)})",
                "tip": DISK_TIP,
                "context": _build_problem_context(f"disk_usage:{mount}", srv, mount=mount, used=used, total=total, pct=dpct, threshold=th["disk_danger"], severity="danger"),
            })
        elif dpct >= th["disk_warn"]:
            inst.append({
                "key": f"disk_usage:{mount}", "severity": "warning",
                "message": f"Disk {mount} terisi tinggi: {dpct:.0f}% (ambang {th['disk_warn']:.0f}%)",
                "tip": DISK_TIP,
                "context": _build_problem_context(f"disk_usage:{mount}", srv, mount=mount, used=used, total=total, pct=dpct, threshold=th["disk_warn"], severity="warning"),
            })
    return inst


def _problem_instances(srv, extras, svc_data, db=None) -> list:
    """Masalah yang sedang terjadi -> [{key,severity,message,tip,context}] (Zabbix-like)."""
    inst: list = []

    # 1. Deteksi Konflik IP Agen (Multi-Agent / Klon VM Split-Brain)
    with _agent_tracker_lock:
        s_ips = dict(_agent_ip_tracker.get(srv.id, {}))
    now_ep = time.time()
    active_ips = [ip for ip, ts in s_ips.items() if (now_ep - ts) <= 120]
    if len(active_ips) > 1:
        active_ips_sorted = sorted(active_ips)
        inst.append({
            "key": "agent_conflict",
            "severity": "danger",
            "message": f"Konflik Agen Terdeteksi: API key aktif di beberapa host ({', '.join(active_ips_sorted)})",
            "tip": "Dua mesin berbeda melapor dengan API key yang sama (kemungkinan VM dikloning atau duplikat instalasi agen). "
                   "Hentikan agent_pantau di mesin kloningan atau daftarkan sebagai server baru.",
            "context": _build_problem_context("agent_conflict", srv, ips=active_ips_sorted),
        })

    if srv.last_seen is None:
        return inst

    # 2. Deteksi Host Terputus / Agen Tidak Melapor dengan Eskalasi Keparahan Dinamis
    ls = srv.last_seen
    if ls.tzinfo is None:
        ls = ls.replace(tzinfo=timezone.utc)
    sec_silent = (datetime.now(timezone.utc) - ls).total_seconds()

    if _server_stale(srv):
        # Eskalasi keparahan seiring bertambahnya waktu tidak melapor:
        # - Detik awal deteksi (> 15s) s/d menit 2 (< 120s): Warning (Peringatan awal selama 2 menit)
        # - Menit 2 s/d menit 5 (120s s/d 299s): Average (Down: server mati / mesin offline / jaringan terputus)
        # - Mulai detik awal setelah Average selesai (>= 300s / 5 mnt): Danger (Kritis / Gawat)
        if sec_silent >= 300:
            stale_sev = "danger"
            stale_msg = f"Agen tidak melapor (> {int(sec_silent // 60)} mnt)"
            stale_tip = "Segera lakukan inspeksi langsung pada fisik atau virtual mesin server, periksa suplai daya, dan verifikasi konektivitas jaringan."
        elif sec_silent >= 120:
            stale_sev = "average"
            stale_msg = f"Agen tidak melapor (> {int(sec_silent // 60)} mnt)"
            stale_tip = "Periksa suplai daya server, koneksi jaringan, atau status service agent_pantau."
        else:
            stale_sev = "warning"
            stale_msg = f"Agen tidak melapor (> {int(sec_silent)} dtk)"
            stale_tip = "Periksa latensi konektivitas jaringan atau pastikan service agent_pantau berjalan aktif."

        inst.append({
            "key": "agent_stale",
            "severity": stale_sev,
            "message": stale_msg,
            "tip": stale_tip,
            "event_at": srv.last_seen.replace(tzinfo=None) if srv.last_seen else None,
            "context": _build_problem_context(
                "agent_stale", srv,
                sec_silent=int(sec_silent),
                escalation_level=stale_sev,
                last_seen_str=ls.strftime("%d %b %Y %H:%M:%S UTC")
            )
        })
        # PENTING: Karena server mati/offline, HENTIKAN penambahan masalah layanan (service_down:*)
        # dan metrik resource hardware (CPU/RAM/Disk). Seluruh status layanan tersupresi oleh status server mati.
        return inst

    if db is not None:
        inst += _resource_problem_instances(db, srv)
    if extras is not None:
        th = get_server_thresholds(srv, db)
        if extras.agent_version and _is_agent_outdated(extras.agent_version, settings.APP_VERSION):
            inst.append({
                "key": "agent_outdated",
                "severity": "warning",
                "message": f"Versi Agen Pantau di {srv.hostname} (v{extras.agent_version}) lebih lama dari dashboard (v{settings.APP_VERSION}) — perlu update",
                "tip": AGENT_OUTDATED_TIP,
                "context": _build_problem_context("agent_outdated", srv, agent_version=extras.agent_version, app_version=settings.APP_VERSION),
            })
        if (extras.apt_upgradable or 0) > 0 and getattr(srv, "is_isolated_net", 0) != 1:
            inst.append({"key": "apt_updates", "severity": "info",
                         "message": f"{extras.apt_upgradable} paket menunggu upgrade",
                         "tip": APT_TIP,
                         "context": _build_problem_context("apt_updates", srv, upgradable=extras.apt_upgradable)})
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
            if invalid >= SECURITY_DANGER_INVALID or failed >= th["ssh_fail_danger"]:
                inst.append({"key": "failed_logins", "severity": "danger",
                             "message": f"Kemungkinan serangan SSH: {failed} login gagal (ambang >={th['ssh_fail_danger']}), "
                                         f"{invalid} user invalid, dari {nips} IP"
                                         + (f" · terakhir {_rel_dt(event_at)}" if event_at else ""),
                             "tip": SECURITY_TIPS["danger"], "event_at": event_at,
                             "context": _build_problem_context("failed_logins", srv, failed=failed, invalid=invalid, source_ips=sec.get("source_ips") or {}, threshold=th["ssh_fail_danger"], severity="danger")})
            elif failed >= th["ssh_fail_warn"]:
                inst.append({"key": "failed_logins", "severity": "warning",
                             "message": f"{failed} login SSH gagal dari {nips} IP (ambang >={th['ssh_fail_warn']})"
                                         + (f" · terakhir {_rel_dt(event_at)}" if event_at else "")
                                         + " — waspada brute force",
                             "tip": SECURITY_TIPS["warning"], "event_at": event_at,
                             "context": _build_problem_context("failed_logins", srv, failed=failed, invalid=invalid, source_ips=sec.get("source_ips") or {}, threshold=th["ssh_fail_warn"], severity="warning")})
            elif failed >= 1:
                inst.append({"key": "failed_logins", "severity": "info",
                             "message": f"{failed} login SSH gagal (ringan)"
                                         + (f" · terakhir {_rel_dt(event_at)}" if event_at else ""),
                             "tip": SECURITY_TIPS["info"], "event_at": event_at,
                             "context": _build_problem_context("failed_logins", srv, failed=failed, invalid=invalid, source_ips=sec.get("source_ips") or {}, severity="info")})
    for d in svc_data or []:
        name = d.get("name", "?")
        st = d.get("status")
        if st == "down":
            inst.append({
                "key": f"service_down:{name}", "severity": "average",
                "message": f"Layanan {name} down",
                "tip": SVC_DOWN_TIP.format(name=name),
                "context": _build_problem_context("service_down:", srv, service_name=name, port=d.get("port"), proc=d.get("proc"), health_msg=d.get("health_msg"), conflict_ips=active_ips if len(active_ips) > 1 else None),
            })
        elif st == "unknown":
            inst.append({"key": f"svc_no_data:{name}", "severity": "info",
                         "message": f"Layanan {name} belum ada data",
                         "tip": SVC_NODATA_TIP,
                         "context": _build_problem_context(f"svc_no_data:{name}", srv, service_name=name, port=d.get("port"))})
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


templates.env.globals["_rel_dt"] = _rel_dt


def _problem_component(key: str) -> str:
    if not key:
        return "Sistem"
    if key.startswith("service_down:") or key.startswith("svc_no_data:"):
        svc = key.split(":", 1)[1]
        return f"Layanan ({svc})"
    if key == "agent_stale":
        return "Agen / Host"
    if key in ("cpu_usage", "cpu_high", "cpu_saturated", "cpu_load"):
        return "Processor (CPU)"
    if key in ("ram_usage", "ram_high", "ram_critical", "swap_usage", "swap_high", "swap_critical", "mem_high"):
        return "Memori (RAM)"
    if key.startswith("disk_usage:") or key.startswith("disk_high:") or key.startswith("disk_critical:") or key.startswith("disk_ro:"):
        mount = key.split(":", 1)[1] if ":" in key else ""
        return f"Penyimpanan ({mount})" if mount else "Penyimpanan (Disk)"
    if key in ("security_danger", "failed_logins"):
        return "Keamanan (SSH)"
    if key == "apt_updates":
        return "Paket OS (APT)"
    if key == "agent_conflict":
        return "Jaringan / IP Agen"
    return "Sistem"


def _problem_row2dict(row) -> dict:
    end = row.resolved_at
    return {
        "id": row.id,
        "key": row.key, "severity": row.severity, "message": row.message,
        "tip": row.tip, "started_at": row.started_at, "resolved_at": end,
        "is_open": end is None,
        "component": _problem_component(row.key),
        "acknowledged_by": row.acknowledged_by,
        "acknowledged_at": row.acknowledged_at,
        "resolved_note": row.resolved_note,
        "durasi": _fmt_duration(row.started_at, end if end else datetime.utcnow()),
        "is_ignored": bool(getattr(row, "is_ignored", 0)),
        "ignored_until": getattr(row, "ignored_until", None),
        "ignored_by": getattr(row, "ignored_by", None),
        "ignored_reason": getattr(row, "ignored_reason", None),
        "ignore_mode": getattr(row, "ignore_mode", None),
        "context": getattr(row, "context", None),
    }


def _enrich_problems_for_ui(open_problems, services, extra, user_or_role="viewer"):
    """Enrich masalah terbuka dengan aksi tombol (restart, log, mitigate, apt_update) untuk UI."""
    svc_map = {s.service_name: s for s in services}
    log_units = {"SYSLOG", "AUTH", "SYSTEM"}
    try:
        log_units |= set(json.loads(extra.units) or []) if extra and extra.units else set()
    except (TypeError, ValueError):
        pass
    sec = _parse_extras_security(extra)
    can_apt = False
    if hasattr(user_or_role, "has_perm"):
        can_apt = user_or_role.has_perm("can_apt")
    elif isinstance(user_or_role, str):
        can_apt = user_or_role in ("admin", "master_admin")

    for r in open_problems:
        if r["key"].startswith("service_down:"):
            sname = r["key"].split(":", 1)[1]
            svc = svc_map.get(sname)
            r["action"] = "restart" if svc else None
            r["svc_id"] = svc.id if svc else None
            r["log_unit"] = sname
        elif r["key"].startswith("svc_no_data:"):
            sname = r["key"].split(":", 1)[1]
            r["action"] = "log"
            r["log_unit"] = sname
        elif r["key"] in ("security_danger", "failed_logins"):
            r["action"] = "mitigate"
            r["log_unit"] = "AUTH"
            r["ip_count"] = len(sec.get("source_ips") or {})
        elif r["key"] == "agent_stale":
            r["action"] = None
        elif r["key"] == "agent_outdated":
            r["action"] = "agent_update_cmd"
        elif r["key"] == "apt_updates":
            r["action"] = "apt_update" if can_apt else None
        else:
            r["action"] = None


def _serialize_problem_list(prob_list):
    """Konversi field datetime ke ISO string agar aman diserialisasikan ke JSON."""
    res = []
    for p in prob_list:
        d = dict(p)
        if isinstance(d.get("started_at"), datetime):
            d["started_at_str"] = _fmt_dt(d["started_at"], with_sec=True)
        if isinstance(d.get("resolved_at"), datetime):
            d["resolved_at_str"] = _fmt_dt(d["resolved_at"], with_sec=True)
        for k in ("started_at", "resolved_at", "acknowledged_at", "last_active_at", "ignored_until"):
            v = d.get(k)
            if isinstance(v, datetime):
                iso_str = v.isoformat()
                if not iso_str.endswith("Z") and not v.tzinfo:
                    iso_str += "Z"
                d[k] = iso_str
        if d.get("started_at"):
            d["started_at_iso"] = d["started_at"]
        res.append(d)
    return res


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

    # Migrasi transparan key lama (ram_high/ram_critical, dll) ke key terpadu (ram_usage, dll)
    LEGACY_KEY_MAP = {
        "ram_high": "ram_usage",
        "ram_critical": "ram_usage",
        "cpu_high": "cpu_usage",
        "cpu_saturated": "cpu_usage",
        "swap_high": "swap_usage",
        "swap_critical": "swap_usage",
        "security_danger": "failed_logins",
    }
    open_legacy = (
        db.query(ServerProblem)
        .filter(ServerProblem.server_id == srv.id, ServerProblem.resolved_at.is_(None))
        .all()
    )
    for r in open_legacy:
        tgt_key = LEGACY_KEY_MAP.get(r.key)
        if not tgt_key:
            if r.key.startswith("disk_high:"):
                tgt_key = "disk_usage:" + r.key.split(":", 1)[1]
            elif r.key.startswith("disk_critical:"):
                tgt_key = "disk_usage:" + r.key.split(":", 1)[1]
        if tgt_key:
            dupe = next((x for x in open_legacy if x.key == tgt_key and x.id != r.id), None)
            if dupe:
                db.delete(r)
            else:
                r.key = tgt_key

    current_keys = {p["key"] for p in instances}

    svc_map = {}
    try:
        for s in db.query(Service).filter(Service.server_id == srv.id).all():
            s_mode = getattr(s, "ignore_mode", None)
            if getattr(s, "is_ignored", 0) and s_mode == "duration" and s.ignored_until and s.ignored_until <= now:
                s.is_ignored = 0
                s.ignored_until = None
                s.ignored_reason = None
                s.ignore_mode = None
            svc_map[s.service_name] = s
    except Exception:
        pass

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

        svc_obj = None
        if p["key"].startswith("service_down:"):
            svc_name = p["key"].split(":", 1)[1]
            svc_obj = svc_map.get(svc_name)
        is_svc_ignored = bool(svc_obj and getattr(svc_obj, "is_ignored", 0))

        if row is None:
            start_time = ev if (ev and (p["key"] == "agent_stale" or "_usage" in p["key"] or p["key"] == "failed_logins")) else now
            new_row = ServerProblem(
                server_id=srv.id, key=p["key"], severity=p["severity"],
                message=p["message"], tip=p["tip"], started_at=start_time,
                last_active_at=active,
                context=p.get("context"),
            )
            # 1. Warisi pengabaian dari objek Service (jika masalah service_down)
            if is_svc_ignored:
                new_row.is_ignored = 1
                new_row.ignored_until = svc_obj.ignored_until
                new_row.ignored_by = svc_obj.ignored_by
                new_row.ignored_reason = svc_obj.ignored_reason
                new_row.ignore_mode = getattr(svc_obj, "ignore_mode", "permanent") or "permanent"
            else:
                # 2. Cek riwayat ServerProblem sebelumnya untuk key ini (termasuk non-service atau flappy)
                prev_prob = (
                    db.query(ServerProblem)
                    .filter(
                        ServerProblem.server_id == srv.id,
                        ServerProblem.key == p["key"],
                        ServerProblem.is_ignored == 1,
                    )
                    .order_by(desc(ServerProblem.updated_at))
                    .first()
                )
                if prev_prob:
                    prev_mode = getattr(prev_prob, "ignore_mode", None)
                    if prev_mode == "permanent" or (prev_mode is None and prev_prob.ignored_until is None):
                        new_row.is_ignored = 1
                        new_row.ignore_mode = "permanent"
                        new_row.ignored_until = None
                        new_row.ignored_by = prev_prob.ignored_by
                        new_row.ignored_reason = prev_prob.ignored_reason
                    elif prev_mode == "duration" and prev_prob.ignored_until and prev_prob.ignored_until > now:
                        new_row.is_ignored = 1
                        new_row.ignore_mode = "duration"
                        new_row.ignored_until = prev_prob.ignored_until
                        new_row.ignored_by = prev_prob.ignored_by
                        new_row.ignored_reason = prev_prob.ignored_reason

            db.add(new_row)
            try:
                audit_status = "diabaikan" if new_row.is_ignored else "aktif"
                _audit(db, "sistem", f"masalah_{p['severity']}", f"{srv.hostname}: terdeteksi [{p['severity'].upper()}] {p['message']}", audit_status, server_id=srv.id)
            except Exception:
                pass
        else:
            if getattr(row, "is_ignored", 0) and getattr(row, "ignore_mode", None) == "duration" and row.ignored_until and row.ignored_until <= now:
                row.is_ignored = 0
                row.ignored_until = None
                row.ignored_reason = None
                row.ignore_mode = None
            elif is_svc_ignored:
                row.is_ignored = 1
                row.ignored_until = svc_obj.ignored_until
                row.ignored_by = svc_obj.ignored_by
                new_row_reason = svc_obj.ignored_reason
                row.ignored_reason = new_row_reason
                row.ignore_mode = getattr(svc_obj, "ignore_mode", "permanent") or "permanent"

            if p["key"] == "agent_stale" and ev and (row.started_at > ev):
                row.started_at = ev

            if active > (row.last_active_at or row.started_at):
                row.last_active_at = active
            if (row.severity != p["severity"] or row.message != p["message"]
                    or row.tip != p["tip"]):
                old_sev = row.severity
                new_sev = p["severity"]
                row.severity, row.message, row.tip = p["severity"], p["message"], p["tip"]
                if old_sev != new_sev:
                    try:
                        _audit(db, "sistem", "eskalasi_insiden",
                               f"{srv.hostname}: eskalasi keparahan [{old_sev.upper()} → {new_sev.upper()}] — {p['message']}",
                               "eskalasi", server_id=srv.id)
                    except Exception:
                        pass
            if p.get("context") and (not row.context or p["severity"] in ("average", "danger")):
                row.context = p.get("context")
            row.updated_at = now

    for row in (
        db.query(ServerProblem).filter(
            ServerProblem.server_id == srv.id,
            ServerProblem.resolved_at.is_(None),
        ).all()
    ):
        if row.key in current_keys:
            continue

        # Jika masalah terkait layanan yang sudah dihapus/tidak ada lagi di daftar pantau server
        if row.key.startswith("service_down:") or row.key.startswith("svc_no_data:"):
            svc_name = row.key.split(":", 1)[1]
            if svc_name not in svc_map:
                # Layanan telah dihapus: bersihkan row problem seketika tanpa jeda 60s
                # dan JANGAN catat audit 'masalah_selesai' (karena layanan sengaja dihapus)
                db.delete(row)
                continue

        quiet = _quiet_secs_for(row.key)
        last = row.last_active_at or row.started_at
        if quiet <= 0 or (now - last).total_seconds() >= quiet:
            row.resolved_at = now
            row.updated_at = now
            if _server_stale(srv) and (row.key.startswith("service_down:") or row.key.startswith("svc_no_data:")):
                row.resolved_note = "server_offline"
            elif row.key == "agent_stale":
                row.resolved_note = "server_online"
            elif row.key.startswith("service_down:"):
                row.resolved_note = "service_up"
            else:
                row.resolved_note = "auto" if quiet > 0 else "resolved"
            audit_msg = f"{srv.hostname}: server kembali online dan aktif melapor" if row.key == "agent_stale" else f"{srv.hostname}: masalah '{row.message}' telah selesai"
            try:
                _audit(db, "sistem", "masalah_selesai", audit_msg, "selesai", server_id=srv.id)
            except Exception:
                pass

            if row.key.startswith("service_down:"):
                svc_name = row.key.split(":", 1)[1]
                svc_obj = svc_map.get(svc_name)
                if svc_obj:
                    svc_mode = getattr(svc_obj, "ignore_mode", None)
                    if svc_mode == "incident":
                        # Mode insiden: hanya untuk satu kejadian, reset saat layanan kembali normal
                        svc_obj.is_ignored = 0
                        svc_obj.ignored_until = None
                        svc_obj.ignored_reason = None
                        svc_obj.ignore_mode = None
                    elif svc_mode == "duration":
                        # Mode durasi: jika batas waktu telah lewat, kembalikan ke pemantauan normal
                        if not (svc_obj.ignored_until and svc_obj.ignored_until > now):
                            svc_obj.is_ignored = 0
                            svc_obj.ignored_until = None
                            svc_obj.ignored_reason = None
                            svc_obj.ignore_mode = None
                    elif svc_mode == "permanent":
                        # Mode permanen: TETAP diabaikan (is_ignored = 1), tidak di-reset saat layanan pulih!
                        pass
                    else:
                        if svc_obj.ignored_until and svc_obj.ignored_until <= now:
                            svc_obj.is_ignored = 0
                            svc_obj.ignored_until = None
                            svc_obj.ignored_reason = None
                            svc_obj.ignore_mode = None

    stale = now - timedelta(days=30)
    db.query(ServerProblem).filter(
        ServerProblem.server_id == srv.id,
        ServerProblem.resolved_at.isnot(None),
        ServerProblem.resolved_at < stale,
        (ServerProblem.is_ignored == 0) | (ServerProblem.is_ignored.is_(None)) | (ServerProblem.ignore_mode != "permanent"),
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
    active_unignored = [r for r in open_rows if not getattr(r, "is_ignored", 0)]
    level = "ok"
    if active_unignored:
        level = max((r.severity for r in active_unignored),
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
    d.update({
        "server_id": srv.id,
        "hostname": srv.hostname,
        "group_name": getattr(srv, "group_name", None) or None,
        "tags": getattr(srv, "tags", "") or "",
    })
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
    rank = {"danger": 4, "average": 3, "warning": 2, "info": 1}
    open_list.sort(key=lambda r: (rank.get(r["severity"], 0), r["started_at"]),
                   reverse=True)
    resolved_list.sort(key=lambda r: r["resolved_at"], reverse=True)
    return open_list, resolved_list



def _server_status(srv, stale: bool, has_services: bool, any_up: bool, has_unignored_down: bool = True):
    """Status server dalam satu kosakata untuk semua halaman.

    Kembalikan (label, kelas_badge) supaya Dashboard, Servers, dan Rincian
    tidak lagi berbeda-beda menampilkan server yang sama.
    """
    if not srv.is_active:
        return "nonaktif", "badge-muted"
    if stale:
        return ("offline", "badge-down") if srv.last_seen else ("-", "badge-muted")
    if not has_services:
        # agen melapor normal, hanya belum ada service yang terdeteksi
        return "online", "badge-up"
    if any_up or not has_unignored_down:
        return "online", "badge-up"
    return "service down", "badge-down"


# ---------------------------------------------------------------------------
# AUDIT LOG
# ---------------------------------------------------------------------------
AUDIT_ACTION_LABELS = {
    "login": "Login",
    "login_2fa": "Login 2FA",
    "logout": "Logout",
    "server_add": "Tambah Server",
    "server_edit": "Ubah Server",
    "server_delete": "Hapus Server",
    "key_regenerate": "Regenerasi Key",
    "service_add": "Tambah Layanan",
    "service_delete": "Hapus Layanan",
    "user_add": "Tambah Pengguna",
    "user_delete": "Hapus Pengguna",
    "apt_update": "Update Paket OS (apt)",
    "apt_upgrade": "Upgrade Paket OS (apt)",
    "apt_upgrade_interact": "APT Upgrade (Interaktif)",
    "apt_fix": "APT Fix",
    "alert_ack": "Akui Peringatan (Alert)",
    "restart": "Restart Layanan",
    "cmd:restart": "Restart Layanan",
    "start": "Mulai Layanan",
    "cmd:start": "Mulai Layanan",
    "stop": "Hentikan Layanan",
    "cmd:stop": "Hentikan Layanan",
    "block_ip": "Blokir IP",
    "cmd:block_ip": "Blokir IP",
    "unblock_ip": "Buka Blokir IP",
    "cmd:unblock_ip": "Buka Blokir IP",
    "firewall_block": "Blokir IP",
    "firewall_unblock": "Buka Blokir IP",
    "firewall_enable": "Aktifkan Firewall",
    "firewall_disable": "Nonaktifkan Firewall",
    "firewall_reload": "Muat Ulang Firewall",
    "cmd:firewall_enable": "Aktifkan Firewall",
    "cmd:firewall_disable": "Nonaktifkan Firewall",
    "cmd:firewall_reload": "Muat Ulang Firewall",
    "kill_process": "Hentikan Proses (Kill)",
    "cmd:kill_process": "Hentikan Proses (Kill)",
    "restart_agent": "Restart Agen",
    "cmd:restart_agent": "Restart Agen",
    "agent_update": "Pembaruan Agen (OTA)",
    "cmd:update_agent": "Pembaruan Agen (OTA)",
    "reboot_host": "Reboot Server",
    "cmd:reboot_host": "Reboot Server",
    "poweroff_host": "Power Off Server",
    "cmd:poweroff_host": "Power Off Server",
    "problem_ignore": "Abaikan Masalah",
    "problem_unignore": "Pantau Kembali Masalah",
    "problem_resolve": "Selesaikan Masalah",
    "maintenance_mode": "Mode Pemeliharaan",
    "terminal_shell_open": "Buka Terminal Root",
    "terminal_open": "Buka Terminal",
    "terminal_close": "Tutup Terminal",
    "file_save": "Simpan / Edit Berkas",
    "file_upload": "Unggah Berkas",
    "file_rm": "Hapus Berkas / Folder",
    "file_mkdir": "Buat Folder",
    "file_touch": "Buat Berkas",
    "file_rename": "Ubah Nama",
    "file_chmod": "Ubah Izin (chmod)",
    "file_chown": "Ubah Pemilik (chown)",
    # v4.0.0 — Pengelolaan akun pengguna sistem
    "user_create": "Buat Pengguna Sistem",
    "user_lock": "Kunci Akun Pengguna",
    "user_unlock": "Buka Kunci Akun",
    "user_delete": "Hapus Pengguna",
    "cmd:user_create": "Buat Pengguna Sistem",
    "cmd:user_lock": "Kunci Akun Pengguna",
    "cmd:user_unlock": "Buka Kunci Akun",
    "cmd:user_delete": "Hapus Pengguna",
    # v4.0.0 — Pengelolaan tugas terjadwal (cron)
    "cron_add": "Tambah Tugas Cron",
    "cron_toggle": "Ubah Status Cron",
    "cron_delete": "Hapus Tugas Cron",
    "cron_run_now": "Uji Jalankan Cron",
    "cmd:cron_add": "Tambah Tugas Cron",
    "cmd:cron_toggle": "Ubah Status Cron",
    "cmd:cron_delete": "Hapus Tugas Cron",
    "cmd:cron_run_now": "Uji Jalankan Cron",
    # v4.0.0 — Pengelolaan aturan port firewall
    "firewall_port_rule": "Aturan Port Firewall",
    "cmd:firewall_port_rule": "Aturan Port Firewall",
    # v4.0.0 — Pengelolaan path sertifikat SSL kustom
    "ssl_path_add": "Tambah Lokasi SSL",
    "ssl_path_remove": "Hapus Lokasi SSL",
    "cmd:ssl_path_add": "Tambah Lokasi SSL",
    "cmd:ssl_path_remove": "Hapus Lokasi SSL",
    # Layanan & proses
    "service_start": "Mulai Layanan",
    "service_stop": "Hentikan Layanan",
    # Kejadian insiden / masalah
    "masalah_selesai": "Masalah Selesai",
    "masalah_pulih": "Masalah Selesai",
    "masalah_warning": "Peringatan Masalah",
    "masalah_danger": "Bahaya Masalah",
    "masalah_info": "Informasi Masalah",
}

AUDIT_CATEGORIES = [
    {
        "id": "cat:auth",
        "name": "Autentikasi & Akun",
        "name_en": "Auth & User Accounts",
        "keys": ["login", "login_2fa", "logout", "user_create", "cmd:user_create", "user_lock", "cmd:user_lock", "user_unlock", "cmd:user_unlock", "user_delete", "cmd:user_delete", "user_add"],
        "actions": [
            ("login", "Login", "Login"),
            ("login_2fa", "Login 2FA", "2FA Login"),
            ("logout", "Logout", "Logout"),
            ("user_create", "Buat Pengguna Sistem", "Create System User"),
            ("user_lock", "Kunci Akun Pengguna", "Lock User Account"),
            ("user_unlock", "Buka Kunci Akun", "Unlock User Account"),
            ("user_delete", "Hapus Pengguna", "Delete User"),
            ("user_add", "Tambah Akun Web", "Add Web User"),
        ]
    },
    {
        "id": "cat:service",
        "name": "Layanan & Proses",
        "name_en": "Services & Processes",
        "keys": ["service_add", "service_delete", "restart", "cmd:restart", "start", "cmd:start", "stop", "cmd:stop", "kill_process", "cmd:kill_process"],
        "actions": [
            ("restart", "Restart Layanan", "Restart Service"),
            ("start", "Mulai Layanan", "Start Service"),
            ("stop", "Hentikan Layanan", "Stop Service"),
            ("service_add", "Tambah Layanan", "Add Service"),
            ("service_delete", "Hapus Layanan", "Delete Service"),
            ("kill_process", "Hentikan Proses (Kill)", "Kill Process"),
        ]
    },
    {
        "id": "cat:firewall",
        "name": "Firewall & Keamanan",
        "name_en": "Firewall & Security",
        "keys": ["firewall_block", "cmd:block_ip", "firewall_unblock", "cmd:unblock_ip", "firewall_enable", "cmd:firewall_enable", "firewall_disable", "cmd:firewall_disable", "firewall_reload", "cmd:firewall_reload", "firewall_port_rule", "cmd:firewall_port_rule"],
        "actions": [
            ("firewall_block", "Blokir IP", "Block IP"),
            ("firewall_unblock", "Buka Blokir IP", "Unblock IP"),
            ("firewall_enable", "Aktifkan Firewall", "Enable Firewall"),
            ("firewall_disable", "Nonaktifkan Firewall", "Disable Firewall"),
            ("firewall_reload", "Muat Ulang Firewall", "Reload Firewall"),
            ("firewall_port_rule", "Aturan Port Firewall", "Port Rule"),
        ]
    },
    {
        "id": "cat:files",
        "name": "Berkas & File Manager",
        "name_en": "Files & File Manager",
        "keys": ["file_save", "file_upload", "file_rm", "file_mkdir", "file_rename", "file_chmod", "file_chown"],
        "actions": [
            ("file_save", "Simpan / Edit Berkas", "Save / Edit File"),
            ("file_upload", "Unggah Berkas", "Upload File"),
            ("file_rm", "Hapus Berkas / Folder", "Delete File / Folder"),
            ("file_mkdir", "Buat Folder", "Create Folder"),
            ("file_rename", "Ubah Nama", "Rename File"),
            ("file_chmod", "Ubah Izin (chmod)", "Change Permissions"),
            ("file_chown", "Ubah Pemilik (chown)", "Change Owner"),
        ]
    },
    {
        "id": "cat:cron",
        "name": "Tugas Terjadwal (Cron)",
        "name_en": "Cron Jobs",
        "keys": ["cron_add", "cmd:cron_add", "cron_toggle", "cmd:cron_toggle", "cron_delete", "cmd:cron_delete", "cron_run_now", "cmd:cron_run_now"],
        "actions": [
            ("cron_add", "Tambah Tugas Cron", "Add Cron Job"),
            ("cron_toggle", "Ubah Status Cron", "Toggle Cron Job"),
            ("cron_delete", "Hapus Tugas Cron", "Delete Cron Job"),
            ("cron_run_now", "Uji Jalankan Cron", "Run Cron Now"),
        ]
    },
    {
        "id": "cat:ssl",
        "name": "Sertifikat SSL",
        "name_en": "SSL Certificates",
        "keys": ["ssl_path_add", "cmd:ssl_path_add", "ssl_path_remove", "cmd:ssl_path_remove"],
        "actions": [
            ("ssl_path_add", "Tambah Lokasi SSL", "Add SSL Path"),
            ("ssl_path_remove", "Hapus Lokasi SSL", "Remove SSL Path"),
        ]
    },
    {
        "id": "cat:apt",
        "name": "Pembaruan OS (APT)",
        "name_en": "OS Updates (APT)",
        "keys": ["apt_update", "apt_upgrade", "apt_upgrade_interact"],
        "actions": [
            ("apt_update", "Update Paket OS (apt)", "Update Packages (apt)"),
            ("apt_upgrade", "Upgrade Paket OS (apt)", "Upgrade Packages (apt)"),
        ]
    },
    {
        "id": "cat:server",
        "name": "Server & Pemeliharaan",
        "name_en": "Server & Maintenance",
        "keys": ["server_add", "server_edit", "server_delete", "key_regenerate", "reboot_host", "cmd:reboot_host", "poweroff_host", "cmd:poweroff_host", "restart_agent", "cmd:restart_agent", "agent_update", "cmd:update_agent", "terminal_shell_open", "maintenance_mode", "alert_ack", "problem_ignore", "problem_unignore", "problem_resolve"],
        "actions": [
            ("server_add", "Tambah Server", "Add Server"),
            ("server_edit", "Ubah Server", "Edit Server"),
            ("server_delete", "Hapus Server", "Delete Server"),
            ("key_regenerate", "Regenerasi Key", "Regenerate Key"),
            ("reboot_host", "Reboot Server", "Reboot Server"),
            ("poweroff_host", "Power Off Server", "Power Off Server"),
            ("restart_agent", "Restart Agen", "Restart Agent"),
            ("agent_update", "Pembaruan Agen (OTA)", "Agent Update (OTA)"),
            ("terminal_shell_open", "Buka Terminal Root", "Open Root Terminal"),
            ("maintenance_mode", "Mode Pemeliharaan", "Maintenance Mode"),
            ("alert_ack", "Akui Peringatan (Alert)", "Acknowledge Alert"),
            ("problem_ignore", "Abaikan Masalah", "Ignore Incident"),
            ("problem_unignore", "Pantau Kembali Masalah", "Cancel Ignore Incident"),
        ]
    }
]

AUDIT_ACTION_SET = dict(AUDIT_ACTION_LABELS)


def _audit_rows(db, limit: int = 500, q: str = "", action: str = "", user_filter: str = ""):
    """Gabungkan jejak audit_logs + tabel commands (aksi remote), urut turun waktu."""
    q = (q or "").strip().lower()
    user_filter = (user_filter or "").strip()
    rows: list[dict] = []

    server_map = {s.id: s.hostname for s in db.query(Server).all()}
    svc_map = {s.id: s.service_name for s in db.query(Service).all()}

    items = (
        db.query(AuditLog).order_by(desc(AuditLog.created_at)).limit(limit).all()
    )
    for a in items:
        srv_name = server_map.get(a.server_id) or ""
        tgt = (a.target or "").strip()
        if not srv_name and ":" in tgt:
            possible_host = tgt.split(":", 1)[0].strip()
            if any(possible_host == h for h in server_map.values()):
                srv_name = possible_host
                tgt = tgt.split(":", 1)[1].strip()
        elif srv_name and tgt.startswith(f"{srv_name}:"):
            tgt = tgt[len(srv_name) + 1:].strip()
        elif tgt.startswith("Server "):
            possible_host = tgt[7:].strip()
            if possible_host in server_map.values():
                if not srv_name:
                    srv_name = possible_host
                tgt = "-"

        # Bersihkan awalan aksi berulang agar kolom Target benar-benar hanya menampilkan entitas sasaran
        for pfx in ("blokir ", "buka blokir ", "buat user ", "kunci user ", "buka kunci user ",
                    "hapus user ", "tambah cron ", "hapus cron ", "tambah path ssl ", "hapus path ssl "):
            if tgt.lower().startswith(pfx):
                tgt = tgt[len(pfx):].strip()
                break

        if not tgt:
            tgt = "-"

        rows.append({
            "t": a.created_at, "user": a.username, "kind": "log",
            "label": AUDIT_ACTION_LABELS.get(a.action, a.action),
            "key": a.action,
            "server": srv_name or "-",
            "target": tgt, "status": None, "result": a.result or "",
        })

    cmds = (
        db.query(Command).order_by(desc(Command.created_at)).limit(limit).all()
    )
    label_map = {
        "restart": "cmd:restart", "start": "cmd:start", "stop": "cmd:stop",
        "block_ip": "cmd:block_ip", "unblock_ip": "cmd:unblock_ip",
        "restart_agent": "cmd:restart_agent",
        "update_agent": "cmd:update_agent",
        "reboot_host": "cmd:reboot_host", "poweroff_host": "cmd:poweroff_host",
        "firewall_enable": "cmd:firewall_enable", "firewall_disable": "cmd:firewall_disable",
        "firewall_reload": "cmd:firewall_reload", "kill_process": "cmd:kill_process",
        "user_create": "cmd:user_create", "user_lock": "cmd:user_lock",
        "user_unlock": "cmd:user_unlock", "user_delete": "cmd:user_delete",
        "cron_add": "cmd:cron_add", "cron_toggle": "cmd:cron_toggle",
        "cron_delete": "cmd:cron_delete", "cron_run_now": "cmd:cron_run_now",
        "firewall_port_rule": "cmd:firewall_port_rule",
        "ssl_path_add": "cmd:ssl_path_add", "ssl_path_remove": "cmd:ssl_path_remove",
    }
    for c in cmds:
        key = label_map.get(c.action, f"cmd:{c.action}")
        srv_name = server_map.get(c.server_id, f"server#{c.server_id}")
        tgt_parts = []
        if c.service_id and c.service_id in svc_map:
            tgt_parts.append(svc_map[c.service_id])
        if c.params:
            try:
                ps = json.loads(c.params)
                if isinstance(ps, dict):
                    if ps.get("ips"):
                        tgt_parts.append(f"{', '.join(str(i) for i in ps['ips'][:3])}{'…' if len(ps['ips']) > 3 else ''}")
                    elif ps.get("ip"):
                        tgt_parts.append(str(ps["ip"]))
                    elif ps.get("username"):
                        tgt_parts.append(str(ps["username"]))
                    elif ps.get("path"):
                        tgt_parts.append(str(ps["path"]))
                    elif ps.get("cron_id"):
                        tgt_parts.append(str(ps["cron_id"]))
                    elif ps.get("port"):
                        tgt_parts.append(str(ps["port"]))
                    elif c.action == "update_agent":
                        ver = ps.get("version") or ""
                        h = ps.get("sha256") or ""
                        h_short = f" (SHA: {h[:8]}…)" if h else ""
                        tgt_parts.append(f"OTA v{ver}{h_short}" if ver else (f"OTA{h_short}" if h_short else "Agen Pantau"))
            except (TypeError, ValueError):
                pass
        if not tgt_parts and c.action in ("restart_agent", "update_agent"):
            tgt = "Agen Pantau"
        else:
            tgt = " · ".join(tgt_parts) if tgt_parts else "-"
        status = (c.status or "").upper()
        short = (c.result or "").strip()
        if len(short) > 160:
            short = short[:160] + "…"
        rows.append({
            "t": c.created_at, "user": c.issued_by or "-", "kind": "cmd",
            "key": key,
            "label": AUDIT_ACTION_LABELS.get(key, AUDIT_ACTION_LABELS.get(c.action, c.action)),
            "server": srv_name,
            "target": tgt, "status": status, "result": short,
        })

    if q:
        rows = [r for r in rows if q in " ".join(
            [r["user"], r["label"], r.get("server", ""), r["target"], r["result"]]).lower()]

    if action:
        matched_keys = set()
        for cat in AUDIT_CATEGORIES:
            if cat["id"] == action:
                matched_keys.update(cat["keys"])
                break
        if not matched_keys:
            matched_keys.add(action)
            matched_keys.add(f"cmd:{action}")
            if action == "firewall_block": matched_keys.add("cmd:block_ip")
            elif action == "firewall_unblock": matched_keys.add("cmd:unblock_ip")
        rows = [r for r in rows if r["key"] in matched_keys or r["key"].replace("cmd:", "") == action]

    if user_filter:
        rows = [r for r in rows if r["user"].lower() == user_filter.lower()]

    rows.sort(key=lambda r: r["t"], reverse=True)
    return rows[:limit]


@app.get("/audit", response_class=HTMLResponse)
def audit_page(
    request: Request, db: Session = Depends(get_db),
    q: str = "", action: str = "", user: str = "",
):
    user_actor = get_current_user(request, db)
    if not user_actor:
        return RedirectResponse("/login", status_code=303)
    if not (user_actor.is_master_admin() or user_actor.has_perm("can_audit")):
        return RedirectResponse("/", status_code=303)

    user_clean = user.strip()
    rows = _audit_rows(db, limit=500, q=q, action=action, user_filter=user_clean)
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

        available_users = [u.username for u in db.query(User).filter(User.role == "operator").order_by(User.username).all()]
    else:
        available_users = [u.username for u in db.query(User).filter(User.role.in_(["master_admin", "operator"])).order_by(User.username).all()]

    return tpl(request, "audit.html", {
        "user": user_actor,
        "rows": rows,
        "q": q,
        "action": action,
        "selected_user": user_clean,
        "available_users": available_users,
        "categories": AUDIT_CATEGORIES,
        "actions": sorted(AUDIT_ACTION_LABELS.items()),
    })


# ---------------------------------------------------------------------------
# ALERT DANGER (popup yang tidak bisa diabaikan)
# ---------------------------------------------------------------------------
def _alert_dict(row, hostname: str, now: datetime) -> dict:
    ctx = row.context
    if isinstance(ctx, str) and ctx:
        try:
            ctx = json.loads(ctx)
        except Exception:
            pass
    s_iso = row.started_at.isoformat()
    if not s_iso.endswith("Z"):
        s_iso += "Z"
    return {
        "id": row.id,
        "server_id": row.server_id,
        "hostname": hostname,
        "key": row.key,
        "severity": row.severity,
        "message": row.message,
        "tip": row.tip,
        "started_at": s_iso,
        "durasi": _fmt_duration(row.started_at, now),
        "acknowledged": row.acknowledged_at is not None,
        "acknowledged_by": row.acknowledged_by,
        "context": ctx,
        "is_ignored": bool(getattr(row, "is_ignored", 0)),
        "ignore_mode": getattr(row, "ignore_mode", None),
        "ignored_until": row.ignored_until.isoformat() if getattr(row, "ignored_until", None) else None,
        "ignored_by": getattr(row, "ignored_by", None),
        "ignored_reason": getattr(row, "ignored_reason", None),
    }


@app.get("/api/alerts")
def api_alerts(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Insiden terbuka lintas semua tingkat keparahan (danger, average, warning, info)."""
    now = datetime.utcnow()
    # Pastikan server offline/stale langsung tersinkronisasi tanpa jeda background loop
    stale_servers = [s for s in db.query(Server).filter(Server.is_active == 1, Server.last_seen.isnot(None)).all() if _server_stale(s)]
    for st in stale_servers:
        try:
            sync_server_problems(db, st, _problem_instances(st, None, None, db))
        except Exception:
            pass

    host = {s.id: s.hostname for s in db.query(Server).all()}
    open_problems = (
        db.query(ServerProblem)
        .filter(
            ServerProblem.resolved_at.is_(None),
            (ServerProblem.is_ignored == 0) | (ServerProblem.is_ignored.is_(None)),
        )
        .order_by(desc(ServerProblem.started_at)).all()
    )

    open_danger = [r for r in open_problems if r.severity == "danger"]
    open_average = [r for r in open_problems if r.severity == "average"]
    open_warning = [r for r in open_problems if r.severity == "warning"]
    open_info = [r for r in open_problems if r.severity == "info"]

    unack_danger = [r for r in open_danger if r.acknowledged_at is None]
    unack_average = [r for r in open_average if r.acknowledged_at is None]
    unack_warning = [r for r in open_warning if r.acknowledged_at is None]

    # Filter Anti-Spike: Beban resource (CPU/RAM/Swap) yang menyentuh ambang batas
    # ditahan selama 60 detik sebelum memicu Alert Banner & Audio darurat
    RESOURCE_ALERT_DELAY_SECS = 60

    def _is_alert_banner_firing(r, now_dt):
        key = getattr(r, "key", "") or ""
        if key.startswith(("ram_", "cpu_", "swap_")):
            st = getattr(r, "started_at", None)
            if st and (now_dt - st).total_seconds() < RESOURCE_ALERT_DELAY_SECS:
                return False
        return True

    firing_danger = [r for r in unack_danger if _is_alert_banner_firing(r, now)]
    firing_average = [r for r in unack_average if _is_alert_banner_firing(r, now)]
    firing_warning = [r for r in unack_warning if _is_alert_banner_firing(r, now)]

    rank = {"danger": 4, "average": 3, "warning": 2, "info": 1}
    unack_operational = sorted(
        unack_danger + unack_average + unack_warning,
        key=lambda r: (rank.get(r.severity, 0), r.started_at),
        reverse=True,
    )
    firing_operational = sorted(
        firing_danger + firing_average + firing_warning,
        key=lambda r: (rank.get(r.severity, 0), r.started_at),
        reverse=True,
    )

    danger_alerts = [_alert_dict(r, host.get(r.server_id, "?"), now) for r in unack_danger]
    average_alerts = [_alert_dict(r, host.get(r.server_id, "?"), now) for r in unack_average]
    warning_alerts = [_alert_dict(r, host.get(r.server_id, "?"), now) for r in unack_warning]
    all_unack_alerts = [_alert_dict(r, host.get(r.server_id, "?"), now) for r in unack_operational]
    firing_alerts = [_alert_dict(r, host.get(r.server_id, "?"), now) for r in firing_operational]

    danger_hosts = sorted(list({host.get(r.server_id, f"Server #{r.server_id}") for r in open_danger if r.server_id}))
    average_hosts = sorted(list({host.get(r.server_id, f"Server #{r.server_id}") for r in open_average if r.server_id}))
    warning_hosts = sorted(list({host.get(r.server_id, f"Server #{r.server_id}") for r in open_warning if r.server_id}))

    host_danger_counts = {}
    for r in open_danger:
        hname = host.get(r.server_id) or f"Server #{r.server_id}"
        host_danger_counts[hname] = host_danger_counts.get(hname, 0) + 1

    host_average_counts = {}
    for r in open_average:
        hname = host.get(r.server_id) or f"Server #{r.server_id}"
        host_average_counts[hname] = host_average_counts.get(hname, 0) + 1

    host_warning_counts = {}
    for r in open_warning:
        hname = host.get(r.server_id) or f"Server #{r.server_id}"
        host_warning_counts[hname] = host_warning_counts.get(hname, 0) + 1

    if open_danger:
        highest_severity = "danger"
    elif open_average:
        highest_severity = "average"
    elif open_warning:
        highest_severity = "warning"
    elif open_info:
        highest_severity = "info"
    else:
        highest_severity = "ok"

    return {
        "alerts": danger_alerts,
        "all_alerts": all_unack_alerts,
        "danger_alerts": danger_alerts,
        "average_alerts": average_alerts,
        "warning_alerts": warning_alerts,
        "firing_alerts": firing_alerts,
        "unack_count": len(danger_alerts),
        "unack_danger_count": len(danger_alerts),
        "unack_average_count": len(average_alerts),
        "unack_warning_count": len(warning_alerts),
        "unack_total_count": len(all_unack_alerts),
        "firing_danger_count": len(firing_danger),
        "firing_average_count": len(firing_average),
        "firing_warning_count": len(firing_warning),
        "firing_total_count": len(firing_operational),
        "open_danger_count": len(open_danger),
        "open_average_count": len(open_average),
        "open_warning_count": len(open_warning),
        "open_info_count": len(open_info),
        "total_open_count": len(open_problems),
        "acked_count": len(open_danger) - len(danger_alerts),
        "danger_hosts": danger_hosts,
        "average_hosts": average_hosts,
        "warning_hosts": warning_hosts,
        "host_danger_counts": host_danger_counts,
        "host_average_counts": host_average_counts,
        "host_warning_counts": host_warning_counts,
        "highest_severity": highest_severity,
    }


@app.get("/api/problems")
def api_problems(
    server: int | None = None,
    group: str | None = None,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Endpoint realtime JSON untuk halaman /problems dan pemantauan aktif."""
    open_problems, recent_resolved = problems_aggregate(db)
    if server:
        open_problems = [p for p in open_problems if p.get("server_id") == server]
        recent_resolved = [p for p in recent_resolved if p.get("server_id") == server]
    if group:
        g_clean = group.strip()
        if g_clean == "__none__":
            open_problems = [p for p in open_problems if not p.get("group_name")]
            recent_resolved = [p for p in recent_resolved if not p.get("group_name")]
        else:
            open_problems = [p for p in open_problems if (p.get("group_name") or "") == g_clean]
            recent_resolved = [p for p in recent_resolved if (p.get("group_name") or "") == g_clean]

    def _serialize(prob):
        p = dict(prob)
        if isinstance(p.get("started_at"), datetime):
            p["started_at_iso"] = p["started_at"].replace(tzinfo=None).isoformat() + "Z"
            p["started_at_str"] = _fmt_dt(p["started_at"], with_sec=True)
            p["started_at"] = _fmt_dt(p["started_at"], with_sec=True)
        if isinstance(p.get("resolved_at"), datetime):
            p["resolved_at_iso"] = p["resolved_at"].replace(tzinfo=None).isoformat() + "Z"
            p["resolved_at_str"] = _fmt_dt(p["resolved_at"], with_sec=True)
            p["resolved_at"] = _fmt_dt(p["resolved_at"], with_sec=True)
        if isinstance(p.get("acknowledged_at"), datetime):
            p["acknowledged_at_str"] = _fmt_dt(p["acknowledged_at"], with_sec=True)
            p["acknowledged_at"] = _fmt_dt(p["acknowledged_at"], with_sec=True)
        if isinstance(p.get("ignored_until"), datetime):
            p["ignored_until_str"] = _fmt_dt(p["ignored_until"], with_sec=True)
            p["ignored_until"] = _fmt_dt(p["ignored_until"], with_sec=True)
        return p

    open_serialized = [_serialize(p) for p in open_problems]
    resolved_serialized = [_serialize(p) for p in recent_resolved]

    servers_total = db.query(Server).count()
    active_open_servers = {p["server_id"] for p in open_problems if not p.get("is_ignored")}

    res_durations = []
    auto_cnt = 0
    manual_cnt = 0
    for p in recent_resolved:
        st = p.get("started_at")
        res = p.get("resolved_at")
        if isinstance(st, datetime) and isinstance(res, datetime):
            res_durations.append(max(0, int((res - st).total_seconds())))
        if p.get("acknowledged_by"):
            manual_cnt += 1
        else:
            auto_cnt += 1
    avg_s = int(sum(res_durations) / len(res_durations)) if res_durations else 0
    avg_mttr_str = _fmt_duration(datetime.min, datetime.min + timedelta(seconds=avg_s)) if avg_s > 0 else "—"

    return {
        "open_problems": open_serialized,
        "recent_resolved": resolved_serialized,
        "summary": {
            "danger_open": sum(1 for p in open_problems if p.get("severity") == "danger" and not p.get("is_ignored")),
            "average_open": sum(1 for p in open_problems if p.get("severity") == "average" and not p.get("is_ignored")),
            "warning_open": sum(1 for p in open_problems if p.get("severity") == "warning" and not p.get("is_ignored")),
            "info_open": sum(1 for p in open_problems if p.get("severity") == "info" and not p.get("is_ignored")),
            "ignored_open": sum(1 for p in open_problems if p.get("is_ignored")),
            "ok_count": servers_total - len(active_open_servers),
            "total_open": len(open_problems),
            "total_resolved": len(recent_resolved),
            "avg_mttr": avg_mttr_str,
            "auto_resolved": auto_cnt,
            "manual_resolved": manual_cnt,
        }
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
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin melakukan tindakan pada insiden")
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Peringatan tidak ditemukan")
    row.acknowledged_at = datetime.utcnow()
    row.acknowledged_by = user.username
    _audit(
        db, user.username, "alert_ack",
        target=row.message[:100], result="diakui", server_id=row.server_id
    )
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
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin menyelesaikan insiden")
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
    _audit(
        db, user.username, "problem_resolve",
        target=row.message[:100], result="diselesaikan manual", server_id=row.server_id
    )
    db.commit()
    return {"ok": True, "id": pid, "resolved_by": user.username}


@app.post("/api/alerts/{pid}/ignore")
def api_alert_ignore(
    pid: int,
    request: Request,
    body: dict = Body(default={}),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Abaikan / bungkam peringatan atau masalah."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin mengabaikan insiden")
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Masalah tidak ditemukan")

    duration = str(body.get("duration", "24h")).lower().strip()
    reason = str(body.get("reason", "")).strip()[:255] or None

    now = datetime.utcnow()
    until = None
    ignore_mode = "duration"
    if duration == "2h":
        until = now + timedelta(hours=2)
    elif duration == "24h":
        until = now + timedelta(hours=24)
    elif duration == "7d":
        until = now + timedelta(days=7)
    elif duration == "30d":
        until = now + timedelta(days=30)
    elif duration in ("0", "perm", "permanent", "forever"):
        until = None
        ignore_mode = "permanent"
    elif duration == "incident":
        until = None
        ignore_mode = "incident"
    else:
        until = now + timedelta(hours=24)

    row.is_ignored = 1
    row.ignored_until = until
    row.ignored_by = user.username
    row.ignored_reason = reason
    row.ignore_mode = ignore_mode
    row.updated_at = now
    if not row.acknowledged_at:
        row.acknowledged_at = now
        row.acknowledged_by = user.username

    # Jika masalah ini adalah service_down, sinkronkan ke tabel Service
    if row.key.startswith("service_down:"):
        svc_name = row.key.split(":", 1)[1]
        svc = db.query(Service).filter(
            Service.server_id == row.server_id,
            Service.service_name == svc_name,
        ).first()
        if svc:
            svc.is_ignored = 1
            svc.ignored_until = until
            svc.ignored_by = user.username
            svc.ignored_reason = reason
            svc.ignore_mode = ignore_mode

    dur_label = f" ({duration})" if ignore_mode != "permanent" else " (permanen)"
    if ignore_mode == "incident":
        dur_label = " (hanya insiden saat ini)"
    res_str = f"diabaikan{dur_label}" + (f": {reason}" if reason else "")
    _audit(
        db, user.username, "problem_ignore",
        target=row.message[:100], result=res_str, server_id=row.server_id
    )
    db.commit()
    return {
        "ok": True,
        "id": pid,
        "is_ignored": True,
        "ignored_until": until.isoformat() if until else None,
        "ignore_mode": ignore_mode,
        "ignored_by": user.username,
        "ignored_reason": reason,
    }


@app.post("/api/alerts/{pid}/unignore")
def api_alert_unignore(
    pid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Batalkan pengabaian / aktifkan kembali pemantauan masalah."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin memulihkan pengabaian insiden")
    row = db.query(ServerProblem).filter(
        ServerProblem.id == pid,
        ServerProblem.resolved_at.is_(None),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Masalah tidak ditemukan")

    # Bersihkan seluruh riwayat pengabaian pada masalah ini dan key terkait di server ini
    db.query(ServerProblem).filter(
        ServerProblem.server_id == row.server_id,
        ServerProblem.key == row.key,
    ).update({
        ServerProblem.is_ignored: 0,
        ServerProblem.ignored_until: None,
        ServerProblem.ignored_reason: None,
        ServerProblem.ignore_mode: None,
    }, synchronize_session=False)

    row.is_ignored = 0
    row.ignored_until = None
    row.ignored_reason = None
    row.ignore_mode = None
    row.updated_at = datetime.utcnow()

    # Jika masalah ini adalah service_down, batalkan juga abaikan pada tabel Service
    if row.key.startswith("service_down:"):
        svc_name = row.key.split(":", 1)[1]
        svc = db.query(Service).filter(
            Service.server_id == row.server_id,
            Service.service_name == svc_name,
        ).first()
        if svc:
            svc.is_ignored = 0
            svc.ignored_until = None
            svc.ignored_reason = None
            svc.ignore_mode = None

    _audit(
        db, user.username, "problem_unignore",
        target=row.message[:100], result="pemantauan diaktifkan kembali", server_id=row.server_id
    )
    db.commit()
    return {"ok": True, "id": pid, "is_ignored": False}


@app.post("/api/servers/{sid}/services/{svc_id}/ignore")
def api_service_ignore(
    sid: int,
    svc_id: int,
    request: Request,
    body: dict = Body(default={}),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Abaikan pemantauan suatu layanan secara langsung (bisa permanen atau durasi)."""
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_services")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kontrol layanan diperlukan")
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Layanan tidak ditemukan")

    duration = str(body.get("duration", "permanent")).lower().strip()
    reason = str(body.get("reason", "")).strip()[:255] or None

    now = datetime.utcnow()
    until = None
    ignore_mode = "duration"
    if duration == "2h":
        until = now + timedelta(hours=2)
    elif duration == "24h":
        until = now + timedelta(hours=24)
    elif duration == "7d":
        until = now + timedelta(days=7)
    elif duration == "30d":
        until = now + timedelta(days=30)
    elif duration in ("0", "perm", "permanent", "forever"):
        until = None
        ignore_mode = "permanent"
    elif duration == "incident":
        until = None
        ignore_mode = "incident"
    else:
        until = None
        ignore_mode = "permanent"

    svc.is_ignored = 1
    svc.ignored_until = until
    svc.ignored_by = user.username
    svc.ignored_reason = reason
    svc.ignore_mode = ignore_mode

    prob = db.query(ServerProblem).filter(
        ServerProblem.server_id == sid,
        ServerProblem.key == f"service_down:{svc.service_name}",
        ServerProblem.resolved_at.is_(None),
    ).first()
    if prob:
        prob.is_ignored = 1
        prob.ignored_until = until
        prob.ignored_by = user.username
        prob.ignored_reason = reason
        prob.ignore_mode = ignore_mode
        prob.updated_at = now

    dur_label = f" ({duration})" if ignore_mode != "permanent" else " (permanen)"
    if ignore_mode == "incident":
        dur_label = " (hanya insiden saat ini)"
    res_str = f"diabaikan{dur_label}" + (f": {reason}" if reason else "")
    _audit(
        db, user.username, "problem_ignore",
        target=f"Layanan {svc.service_name}", result=res_str, server_id=sid
    )
    db.commit()
    return {
        "ok": True,
        "service_id": svc_id,
        "is_ignored": True,
        "ignored_until": until.isoformat() if until else None,
        "ignore_mode": ignore_mode,
        "ignored_by": user.username,
        "ignored_reason": reason,
    }


@app.post("/api/servers/{sid}/services/{svc_id}/unignore")
def api_service_unignore(
    sid: int,
    svc_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Aktifkan kembali pemantauan suatu layanan."""
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_services")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kontrol layanan diperlukan")
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Layanan tidak ditemukan")

    svc.is_ignored = 0
    svc.ignored_until = None
    svc.ignored_reason = None
    svc.ignore_mode = None

    # Bersihkan pengabaian pada seluruh riwayat ServerProblem untuk layanan ini
    db.query(ServerProblem).filter(
        ServerProblem.server_id == sid,
        ServerProblem.key == f"service_down:{svc.service_name}",
    ).update({
        ServerProblem.is_ignored: 0,
        ServerProblem.ignored_until: None,
        ServerProblem.ignored_reason: None,
        ServerProblem.ignore_mode: None,
    }, synchronize_session=False)

    _audit(
        db, user.username, "problem_unignore",
        target=f"Layanan {svc.service_name}", result="pemantauan diaktifkan kembali", server_id=sid
    )
    db.commit()
    return {"ok": True, "service_id": svc_id, "is_ignored": False}


@app.post("/api/settings/thresholds")
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
    float_keys = ["cpu_warn", "cpu_danger", "ram_warn", "ram_danger", "disk_warn", "disk_danger", "swap_warn", "swap_danger"]
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
            raise HTTPException(status_code=400, detail=f"Nilai Warning ({w_k}) tidak boleh lebih besar dari Danger ({d_k})")

    current_th = get_global_thresholds(db)
    current_th.update(new_th)

    row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
    if not row:
        row = SystemSetting(key="thresholds", value=json.dumps(current_th), updated_at=datetime.utcnow())
        db.add(row)
    else:
        row.value = json.dumps(current_th)
        row.updated_at = datetime.utcnow()

    _audit(db, user.username, "settings_update", target="Ambang Batas Masalah Global", result="disimpan")
    db.commit()
    return {"ok": True, "thresholds": current_th}


@app.post("/api/settings/thresholds/reset")
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
        _audit(db, user.username, "settings_reset", target="Ambang Batas Masalah Global", result="direset ke bawaan pabrik")
        db.commit()

    return {"ok": True, "thresholds": dict(DEFAULT_THRESHOLDS)}




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
    if req.unit == SHELL_UNIT:
        if not user.has_perm("can_terminal"):
            raise HTTPException(status_code=403, detail="Akses ditolak: izin terminal diperlukan")
    elif req.unit in APT_UNITS:
        if not user.has_perm("can_apt"):
            raise HTTPException(status_code=403, detail="Akses ditolak: izin APT diperlukan")
    else:
        if not (user.is_master_admin() or user.is_operator()):
            raise HTTPException(status_code=403, detail="Akses ditolak")
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
            parsed = None
            try:
                parsed = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
            except Exception:
                parsed = None

            extras = db.query(ServerExtras).filter(ServerExtras.server_id == server.id).first()
            if not extras:
                extras = ServerExtras(server_id=server.id)
                db.add(extras)

            if isinstance(parsed, dict) and "apt" in parsed:
                apt_info = parsed.get("apt")
                if isinstance(apt_info, dict):
                    if "upgradable" in apt_info:
                        extras.apt_upgradable = _clamp_int(apt_info.get("upgradable"), 0)
                    if "packages" in apt_info and isinstance(apt_info["packages"], list):
                        extras.apt_packages_json = json.dumps(apt_info["packages"][:200])
                    extras.apt_last_update = datetime.utcnow()
            elif req.unit in ("APT_UPGRADE", "APT_UPGRADE_INTERACT", "APT_DIST_UPGRADE"):
                extras.apt_upgradable = 0
                extras.apt_packages_json = "[]"
                extras.apt_last_update = datetime.utcnow()

            # Sinkronkan masalah apt_updates bila upgradable 0
            if (extras.apt_upgradable or 0) == 0:
                prob = db.query(ServerProblem).filter(
                    ServerProblem.server_id == server.id,
                    ServerProblem.key == "apt_updates",
                    ServerProblem.resolved_at.is_(None)
                ).first()
                if prob:
                    prob.resolved_at = datetime.utcnow()
                    prob.resolved_note = "auto (upgrade selesai)"
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
            func.sum(getattr(func, "if")(Metric.status == "up", 1, 0)),
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
        ups_count = int(ups or 0)
        up_ratio = (ups_count / n) if n else None
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
    net_list = parse_list(latest.net) if latest else []
    if net_list and server.ip_address:
        has_any_ip = any(n.get("ip_addrs") for n in net_list)
        if not has_any_ip:
            # Utamakan interface fisik yang aktif (bukan docker/veth/bridge)
            target_n = next((n for n in net_list if n.get("is_up") and not any(n.get("iface", "").startswith(p) for p in ("docker", "br-", "veth", "virbr", "lo"))), None)
            if not target_n:
                target_n = next((n for n in net_list if n.get("is_up")), None)
            if target_n:
                target_n["ip_addrs"] = [server.ip_address]

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
            "net": net_list,
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
        "hardware_specs": _get_hardware_specs_dict(server, extra, latest),
        "platform": _classify_platform(_get_hardware_specs_dict(server, extra, latest).get("platform", {}), getattr(server, "platform_override", None)),
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
    if _server_stale(server):
        raise HTTPException(status_code=409, detail="Server sedang offline. Permintaan eksekusi atau log dinonaktifkan.")
    if not VALID_UNIT_RE.match(unit):
        raise HTTPException(status_code=400, detail="Invalid unit name")

    is_apt = unit in APT_UNITS
    is_shell = unit == SHELL_UNIT
    if is_apt and not user.has_perm("can_apt"):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda tidak memiliki wewenang Update/Upgrade OS (APT)",
        )
    if is_shell and not user.has_perm("can_terminal"):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda tidak memiliki wewenang Terminal Shell Web",
        )
    if is_shell and getattr(server, "allow_web_terminal", 0) == 0:
        raise HTTPException(
            status_code=403,
            detail="Akses Terminal Web dinonaktifkan untuk server ini sesuai kebijakan keamanan",
        )
    if is_shell and not is_terminal_unlocked(user.id, sid):
        raise HTTPException(
            status_code=403,
            detail="Terminal terkunci: Memerlukan otentikasi kata sandi untuk membuka sesi",
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
               server.hostname, "dikirim ke agen", server_id=sid)
    elif is_shell:
        # Terminal Bawaan = root shell. Catat SIAPA membuka sesi di server mana.
        _audit(db, user.username, "terminal_shell_open", server.hostname,
               "membuka Terminal Bawaan (shell root)", server_id=sid)
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


@app.api_route("/api/agent/latest-code", methods=["GET", "HEAD"])
def api_agent_latest_code():
    """Unduh kode sumber Agen Pantau terbaru langsung dari dashboard dengan verifikasi SHA-256."""
    data, sha256_hash, version = _get_agent_code_and_sha256()
    return Response(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Agent-Version": version,
            "X-Checksum-SHA256": sha256_hash,
            "ETag": f'"{sha256_hash}"',
        },
    )


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
        self.detached = False
        self.detached_at = 0.0
        self.output_buffer: list[str] = []
        self.buffer_len = 0
        self.MAX_BUFFER_CHARS = 250000

    def append_output(self, chunk: str):
        self.output_buffer.append(chunk)
        self.buffer_len += len(chunk)
        while self.buffer_len > self.MAX_BUFFER_CHARS and self.output_buffer:
            removed = self.output_buffer.pop(0)
            self.buffer_len -= len(removed)

    def get_buffered_output(self) -> str:
        return "".join(self.output_buffer)


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

    async def open_or_attach_session(self, server_id: int, ws: WebSocket) -> tuple[TerminalSessionBridge, bool]:
        lock = self._get_lock()
        async with lock:
            old_sid = self._server_to_session.get(server_id)
            if old_sid and old_sid in self._sessions:
                existing = self._sessions[old_sid]
                if not existing.closed:
                    # Sesi shell masih aktif di server klien: sambungkan kembali browser baru
                    if existing.browser_ws and existing.browser_ws != ws:
                        try:
                            await existing.browser_ws.close(code=4409, reason="Replaced by new browser connection")
                        except Exception:
                            pass
                    existing.browser_ws = ws
                    existing.detached = False
                    existing.last_active = time.time()
                    return existing, True

            # Buat sesi baru jika belum ada atau sesi sebelumnya sudah ditutup
            sess_id = secrets.token_hex(16)
            bridge = TerminalSessionBridge(sess_id, server_id)
            bridge.browser_ws = ws
            self._sessions[sess_id] = bridge
            self._server_to_session[server_id] = sess_id
            self._pending_opens[server_id] = sess_id

            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            self._events[server_id].set()
            return bridge, False

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

    async def close_session_by_server(self, server_id: int):
        lock = self._get_lock()
        async with lock:
            sess_id = self._server_to_session.pop(server_id, None)
            if sess_id:
                bridge = self._sessions.pop(sess_id, None)
                if bridge:
                    bridge.closed = True
                    if bridge.browser_ws:
                        try:
                            await bridge.browser_ws.send_text(json.dumps({
                                "type": "stdout",
                                "data": "\r\n\x1b[33;1m[TERMINAL DIKUNCI] Operator telah mengunci sesi terminal ini.\x1b[0m\r\n"
                            }))
                            await bridge.browser_ws.close(code=4403, reason="Terminal locked by operator")
                        except Exception:
                            pass

term_dispatcher = TerminalBridgeDispatcher()


@app.get("/api/servers/{sid}/terminal/status")
def api_terminal_status(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cek status izin dan sisa durasi sewa (lease) otentikasi terminal untuk server ini."""
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    allow_term = bool(getattr(server, "allow_web_terminal", 0))
    user_can = user.has_perm("can_terminal")
    remaining = get_terminal_lease_remaining(user.id, sid)
    unlocked = remaining > 0

    return {
        "server_id": sid,
        "allow_web_terminal": allow_term,
        "can_terminal": user_can,
        "is_unlocked": unlocked,
        "remaining_seconds": remaining,
        "user_has_totp": bool(user.totp_enabled and user.totp_secret),
    }


@app.post("/api/servers/{sid}/terminal/unlock")
def api_terminal_unlock(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Buka kunci akses Web Terminal dengan tantangan kata sandi (sudo step-up auth) + TOTP."""
    _verify_csrf_header(request)

    if not user.has_perm("can_terminal"):
        raise HTTPException(status_code=403, detail="Akses ditolak: Anda tidak memiliki wewenang Terminal Shell Web")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    if getattr(server, "allow_web_terminal", 0) == 0:
        raise HTTPException(status_code=403, detail="Akses Web Terminal dinonaktifkan untuk server ini pada konfigurasi sistem")

    password = _clean_str(body.get("password"), "", 256)
    totp_code = _clean_str(body.get("totp"), "", 10)
    duration_minutes = _clamp_int(body.get("duration_minutes"), 15, 5, 120)
    reason = _clean_str(body.get("reason"), "", 255)

    if not password:
        raise HTTPException(status_code=400, detail="Kata sandi akun pengguna diperlukan")

    # Verifikasi kata sandi operator login
    if not pwd_ctx.verify(password, user.password_hash):
        _audit(db, user.username, "terminal_unlock_fail", f"{server.hostname} (kata sandi salah)", "gagal")
        db.commit()
        raise HTTPException(status_code=401, detail="Kata sandi akun salah. Akses terminal ditolak.")

    # Verifikasi TOTP 2FA jika akun mengaktifkannya
    if user.totp_enabled and user.totp_secret:
        if not totp_code or not security_auth.verify_totp(user.totp_secret, totp_code):
            _audit(db, user.username, "terminal_unlock_fail", f"{server.hostname} (kode 2FA salah)", "gagal")
            db.commit()
            raise HTTPException(status_code=401, detail="Kode 2FA / TOTP tidak valid atau telah kedaluwarsa")

    # Berikan lease otentikasi
    set_terminal_unlock(user.id, sid, duration_minutes)
    audit_detail = f"{server.hostname} [durasi: {duration_minutes}m" + (f", alasan: {reason}]" if reason else "]")
    _audit(db, user.username, "terminal_unlock", audit_detail, "berhasil")
    db.commit()

    return {
        "ok": True,
        "remaining_seconds": duration_minutes * 60,
        "message": f"Kunci terminal berhasil dibuka ({duration_minutes} menit)"
    }


@app.post("/api/servers/{sid}/terminal/lock")
async def api_terminal_lock(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Kunci kembali akses terminal dan putus sesi aktif jika ada."""
    _verify_csrf_header(request)

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    hostname = server.hostname if server else f"sid={sid}"

    revoke_terminal_unlock(user.id, sid)
    await term_dispatcher.close_session_by_server(sid)

    _audit(db, user.username, "terminal_lock", hostname, "berhasil")
    db.commit()

    return {"ok": True, "message": "Terminal berhasil dikunci"}


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
        if not user or not user.has_perm("can_terminal"):
            await websocket.close(code=4403)
            return
        server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
        if not server:
            await websocket.close(code=4404)
            return
        if getattr(server, "allow_web_terminal", 0) == 0:
            await websocket.close(code=4403, reason="Web terminal disabled for this server")
            return
        if not is_terminal_unlocked(user.id, sid):
            await websocket.close(code=4403, reason="Terminal locked: step-up auth required")
            return
        if _server_stale(server):
            await websocket.close(code=4409)
            return
        hostname = server.hostname
        username = user.username
        user_id = user.id
    finally:
        db.close()

    await websocket.accept()

    bridge, is_reconnected = await term_dispatcher.open_or_attach_session(sid, websocket)

    db = SessionLocal()
    try:
        audit_action = "terminal_reconnect" if is_reconnected else "terminal_open"
        _audit(db, username, audit_action, f"{hostname}:{bridge.session_id}", "berhasil")
        db.commit()
    finally:
        db.close()

    if is_reconnected:
        buf = bridge.get_buffered_output()
        if buf:
            try:
                await websocket.send_text(json.dumps({"type": "stdout", "data": buf}))
            except Exception:
                pass

    try:
        while not bridge.closed:
            if not is_terminal_unlocked(user_id, sid):
                try:
                    await websocket.send_text(json.dumps({
                        "type": "stdout",
                        "data": "\r\n\x1b[31;1m[SESI HABIS] Masa berlaku izin akses terminal telah kedaluwarsa. Sesi ditutup demi keamanan.\x1b[0m\r\n"
                    }))
                    await websocket.close(code=4403, reason="Terminal lease expired")
                except Exception:
                    pass
                break
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
        # Lepaskan browser_ws saat browser terputus / F5, namun JANGAN membunuh proses shell di server klien!
        lock = term_dispatcher._get_lock()
        async with lock:
            if bridge.browser_ws == websocket:
                bridge.browser_ws = None
                bridge.detached = True
                bridge.detached_at = time.time()
        db = SessionLocal()
        try:
            _audit(db, username, "terminal_detach", f"{hostname}:{bridge.session_id}", "selesai")
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
    if chunk:
        bridge.append_output(chunk)
        bridge.last_active = time.time()
        if bridge.browser_ws:
            try:
                await bridge.browser_ws.send_text(json.dumps({"type": "stdout", "data": chunk}))
            except Exception:
                bridge.browser_ws = None
                bridge.detached = True
                bridge.detached_at = time.time()

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
                await bridge.browser_ws.send_text(json.dumps({
                    "type": "stdout",
                    "data": "\r\n\x1b[90m[Sesi shell selesai]\x1b[0m\r\n"
                }))
                await bridge.browser_ws.close()
            except Exception:
                pass
        await term_dispatcher.close_session(session_id)
    return {"ok": True}


def _get_active_online_server(db: Session, sid: int) -> Server:
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    if _server_stale(server):
        raise HTTPException(
            status_code=409,
            detail="Server sedang offline. Operasi berkas dinonaktifkan sampai service agent_pantau kembali aktif."
        )
    return server


@app.get("/servers/{sid}/files", response_class=HTMLResponse)
def page_server_files(request: Request, sid: int, db: Session = Depends(get_db)):
    """Halaman antarmuka dedicated File Manager untuk server klien."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not user.has_perm("can_file_manager"):
        raise HTTPException(status_code=403, detail="Akses ditolak: Anda tidak memiliki wewenang File Manager")
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    return tpl(request, "file_manager.html", {
        "server": server,
        "user": user,
        "is_online": not _server_stale(server),
    })


@app.get("/api/servers/{sid}/files/ls")
async def api_server_files_ls(
    sid: int,
    path: str = "/",
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    server = _get_active_online_server(db, sid)

    res = await file_dispatcher.dispatch(sid, "ls", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membaca direktori"))
    return res


@app.get("/api/servers/{sid}/files/cat")
async def api_server_files_cat(
    sid: int,
    path: str,
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    server = _get_active_online_server(db, sid)

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
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    content = str(body.get("content", ""))
    make_backup = bool(body.get("make_backup", True))

    if not path:
        raise HTTPException(status_code=400, detail="Path file tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "write", {"path": path, "content": content, "make_backup": make_backup})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menyimpan file"))

    _audit(db, user.username, "file_save", f"{server.hostname}:{path}", "berhasil",
           {"size": len(content), "backup": res.get("backup_created")}, server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/mkdir")
async def api_server_files_mkdir(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    mode = str(body.get("mode", "0755")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "mkdir", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membuat direktori"))

    _audit(db, user.username, "file_mkdir", f"{server.hostname}:{path}", "berhasil", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/touch")
async def api_server_files_touch(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "touch", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membuat file"))

    _audit(db, user.username, "file_touch", f"{server.hostname}:{path}", "berhasil", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/rm")
async def api_server_files_rm(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "rm", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menghapus"))

    _audit(db, user.username, "file_rm", f"{server.hostname}:{path}", "berhasil", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/rename")
async def api_server_files_rename(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    old_path = str(body.get("old_path", "") or body.get("src", "")).strip()
    new_path = str(body.get("new_path", "") or body.get("dst", "")).strip()
    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="Path asal dan tujuan tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "rename", {"old_path": old_path, "new_path": new_path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengganti nama file/folder"))

    _audit(db, user.username, "file_rename", f"{server.hostname}:{old_path} -> {new_path}", "berhasil", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/chmod")
async def api_server_files_chmod(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    mode = str(body.get("mode", "")).strip()
    res = await file_dispatcher.dispatch(sid, "chmod", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah izin"))

    _audit(db, user.username, "file_chmod", f"{server.hostname}:{path}", f"mode={mode}", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/chown")
async def api_server_files_chown(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    owner = str(body.get("owner", "")).strip()
    group = str(body.get("group", "")).strip() or None
    res = await file_dispatcher.dispatch(sid, "chown", {"path": path, "owner": owner, "group": group})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah kepemilikan"))

    _audit(db, user.username, "file_chown", f"{server.hostname}:{path}", f"owner={owner}:{group}", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/upload")
async def api_server_files_upload(
    sid: int,
    request: Request,
    destination: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran file terlalu besar (maksimal 50 MB)")

    filename = os.path.basename(file.filename or "uploaded_file")
    target_path = os.path.join(destination.rstrip("/"), filename)
    b64_data = base64.b64encode(raw).decode("ascii")

    res = await file_dispatcher.dispatch(sid, "write_binary", {"path": target_path, "data_b64": b64_data}, timeout=35.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengunggah file"))

    _audit(db, user.username, "file_upload", f"{server.hostname}:{target_path}", f"{len(raw)} bytes", server_id=sid)
    db.commit()
    return {"ok": True, "path": target_path, "size": len(raw)}


@app.get("/api/servers/{sid}/files/download")
async def api_server_files_download(
    sid: int,
    path: str,
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    server = _get_active_online_server(db, sid)

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


@app.post("/api/servers/{sid}/files/copy")
async def api_server_files_copy(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    sources = body.get("sources", [])
    destination = str(body.get("destination", "")).strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sumber dan tujuan harus ditentukan")

    res = await file_dispatcher.dispatch(sid, "copy", {"sources": sources, "destination": destination}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menyalin file/folder"))

    _audit(db, user.username, "file_copy", f"{server.hostname}: {len(sources)} items -> {destination}", "berhasil", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/move")
async def api_server_files_move(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    sources = body.get("sources", [])
    destination = str(body.get("destination", "")).strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sumber dan tujuan harus ditentukan")

    res = await file_dispatcher.dispatch(sid, "move", {"sources": sources, "destination": destination}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal memindahkan file/folder"))

    _audit(db, user.username, "file_move", f"{server.hostname}: {len(sources)} items -> {destination}", "berhasil", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/batch-rm")
async def api_server_files_batch_rm(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    paths = body.get("paths", [])
    if not paths or not isinstance(paths, list):
        raise HTTPException(status_code=400, detail="Daftar file/folder yang akan dihapus tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "batch_rm", {"paths": paths}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menghapus beberapa item"))

    _audit(db, user.username, "file_batch_rm", f"{server.hostname}: {len(paths)} items", "berhasil", server_id=sid)
    db.commit()
    return res


@app.post("/api/servers/{sid}/files/batch-chmod")
async def api_server_files_batch_chmod(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    paths = body.get("paths", [])
    mode = str(body.get("mode", "")).strip()
    if not paths or not isinstance(paths, list) or not mode:
        raise HTTPException(status_code=400, detail="Daftar file/folder dan mode izin harus ditentukan")

    res = await file_dispatcher.dispatch(sid, "batch_chmod", {"paths": paths, "mode": mode}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah izin beberapa item"))

    _audit(db, user.username, "file_batch_chmod", f"{server.hostname}: {len(paths)} items, mode={mode}", "berhasil", server_id=sid)
    db.commit()
    return res



# ---------------------------------------------------------------------------
# PROFIL & KEAMANAN AKUN (SELF-SERVICE PROFILE & 2FA)
# ---------------------------------------------------------------------------
def _render_profile_page(
    request: Request,
    user: User,
    db: Session,
    newly_generated_codes: list = None,
    flash_ok: bool = None,
    flash_msg: str = None,
    active_tab: str = "me",
):
    raw_secret = ""
    formatted_secret = ""
    totp_uri = ""
    qr_data_url = ""
    if not user.totp_enabled:
        raw_secret = security_auth.generate_totp_secret()
        formatted_secret = security_auth.format_secret_display(raw_secret)
        totp_uri = security_auth.generate_totp_uri(raw_secret, user.username)
        qr_data_url = security_auth.generate_qr_data_url(totp_uri)

    rec_count = 0
    if user.recovery_codes:
        try:
            rec_count = len(json.loads(user.recovery_codes))
        except Exception:
            rec_count = 0

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")

    users_list = []
    if user.is_master_admin():
        users_list = db.query(User).order_by(User.id).all()
    elif can_manage_users:
        # Operator sama sekali tidak boleh melihat Master Admin
        users_list = db.query(User).filter(User.role != "master_admin").order_by(User.id).all()
    elif can_manage_viewers:
        users_list = db.query(User).filter(User.role == "viewer").order_by(User.id).all()

    return tpl(request, "profile.html", {
        "user": user,
        "users": users_list,
        "can_manage_users": can_manage_users,
        "can_manage_viewers": can_manage_viewers,
        "can_manage_any": can_manage_viewers,
        "all_perms": security_auth.OPERATOR_PERMISSIONS,
        "raw_secret": raw_secret,
        "secret_formatted": formatted_secret,
        "qr_data_url": qr_data_url,
        "recovery_codes_remaining": rec_count,
        "newly_generated_codes": newly_generated_codes,
        "flash_ok": flash_ok,
        "flash_msg": flash_msg,
        "active_tab": active_tab,
    })


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)

    flash_ok = request.query_params.get("ok")
    flash_msg = request.query_params.get("msg")
    flash_err = request.query_params.get("err")
    if flash_err:
        flash_ok = False
        flash_msg = flash_err
    elif flash_msg is not None:
        flash_ok = True
    elif flash_ok is not None:
        flash_ok = flash_ok == "1"

    active_tab = request.query_params.get("tab", "me")

    return _render_profile_page(
        request=request,
        user=user,
        db=db,
        flash_ok=flash_ok,
        flash_msg=flash_msg,
        active_tab=active_tab,
    )


@app.post("/profile/password")
def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if not pwd_ctx.verify(current_password, user.password_hash):
        return RedirectResponse("/profile" + _flash_qs(False, "Kata sandi saat ini tidak cocok"), status_code=303)

    if new_password != confirm_password:
        return RedirectResponse("/profile" + _flash_qs(False, "Konfirmasi kata sandi baru tidak cocok"), status_code=303)

    valid, err_msg = security_auth.validate_password_strength(new_password)
    if not valid:
        return RedirectResponse("/profile" + _flash_qs(False, err_msg), status_code=303)

    user.password_hash = pwd_ctx.hash(new_password)
    user.password_changed_at = datetime.utcnow()

    # Cabut seluruh sesi aktif lainnya untuk user ini di tabel sessions kecuali sesi saat ini
    cur_sid = request.cookies.get(SESSION_COOKIE)
    if cur_sid:
        db.query(AppSession).filter(AppSession.user_id == user.id, AppSession.sid != cur_sid).delete(synchronize_session=False)

    _audit(db, user.username, "change_password", "profil sendiri", "berhasil (sesi lain dicabut)")
    db.commit()
    return RedirectResponse("/profile" + _flash_qs(True, "Kata sandi berhasil diperbarui. Sesi perangkat lain telah dicabut."), status_code=303)


@app.post("/profile/2fa/enable")
def profile_enable_2fa(
    request: Request,
    secret: str = Form(...),
    code: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if not security_auth.verify_totp(secret, code):
        return RedirectResponse("/profile" + _flash_qs(False, "Kode konfirmasi 2FA salah. Pastikan jam perangkat Anda akurat."), status_code=303)

    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    user.totp_secret = secret.strip().replace(" ", "")
    user.totp_enabled = 1
    user.recovery_codes = json.dumps(hashed_codes)
    _audit(db, user.username, "2fa_enable", "profil sendiri", "berhasil")
    db.commit()

    return _render_profile_page(
        request=request,
        user=user,
        db=db,
        newly_generated_codes=plain_codes,
        flash_ok=True,
        flash_msg="2FA berhasil diaktifkan! Harap simpan kode cadangan darurat di bawah ini sekarang.",
    )


@app.post("/profile/2fa/disable")
def profile_disable_2fa(
    request: Request,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    user.totp_enabled = 0
    user.totp_secret = None
    user.recovery_codes = None
    _audit(db, user.username, "2fa_disable", "profil sendiri", "berhasil")
    db.commit()
    return RedirectResponse("/profile" + _flash_qs(True, "Perlindungan 2FA berhasil dinonaktifkan."), status_code=303)


@app.post("/profile/2fa/regenerate-recovery")
def profile_regenerate_recovery(
    request: Request,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if not user.totp_enabled:
        return RedirectResponse("/profile" + _flash_qs(False, "2FA belum aktif"), status_code=303)

    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    user.recovery_codes = json.dumps(hashed_codes)
    _audit(db, user.username, "2fa_regen_recovery", "profil sendiri", "berhasil")
    db.commit()

    return _render_profile_page(
        request=request,
        user=user,
        db=db,
        newly_generated_codes=plain_codes,
        flash_ok=True,
        flash_msg="Kode cadangan darurat baru berhasil dibuat. Kode lama sudah tidak berlaku.",
    )


# ---------------------------------------------------------------------------
# USERS (RBAC 3-TIER: MASTER ADMIN, OPERATOR, VIEWER)
# ---------------------------------------------------------------------------
@app.get("/users")
def users_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_manage_users") or user.has_perm("can_manage_viewers")):
        return RedirectResponse("/", status_code=303)
    # Alihkan ke halaman terpadu Profil & Keamanan (Tab Manajemen Pengguna)
    return RedirectResponse("/profile?tab=users", status_code=303)


@app.post("/users/add")
async def user_add_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("viewer"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        return RedirectResponse("/profile?tab=users", status_code=303)
    _verify_csrf_form(request, csrf_token)

    username = username.strip()
    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,50}$", username):
        return RedirectResponse(_flash_profile_users(False, "Username harus 3-50 karakter alfanumerik (hanya huruf, angka, _, -, .)"), status_code=303)

    # Validasi hak delegasi peran
    if not can_manage_users:
        # Hanya boleh membuat viewer
        role = "viewer"
    else:
        role = role if role in ("operator", "viewer") else "viewer"

    valid, err_msg = security_auth.validate_password_strength(password)
    if not valid:
        return RedirectResponse(_flash_profile_users(False, err_msg), status_code=303)

    if db.query(User).filter(User.username == username).first():
        return RedirectResponse(_flash_profile_users(False, f"Username '{username}' sudah digunakan"), status_code=303)

    perms_json = None
    if role == "operator":
        form_data = await request.form()
        perms_dict = {
            pk: bool(form_data.get(f"perm_{pk}"))
            for pk in security_auth.OPERATOR_PERMISSIONS
        }
        perms_json = json.dumps(perms_dict)

    new_u = User(
        username=username[:100],
        password_hash=pwd_ctx.hash(password),
        role=role,
        is_active=1,
        password_changed_at=datetime.utcnow(),
        permissions=perms_json,
    )
    db.add(new_u)
    _audit(db, user.username, "user_add", f"{username} (peran {role})", "berhasil")
    db.commit()
    return RedirectResponse(_flash_profile_users(True, f"Pengguna '{username}' berhasil didaftarkan sebagai {new_u.role_display()}"), status_code=303)


@app.post("/users/{uid}/edit")
async def user_edit_submit(
    request: Request, uid: int,
    username: str = Form(...),
    password: str = Form(default=""),
    role: str = Form("viewer"),
    is_active: str = Form(default="1"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        return RedirectResponse("/profile?tab=users", status_code=303)
    _verify_csrf_form(request, csrf_token)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    if target_u.is_master_admin() and not user.is_master_admin():
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    if not can_manage_users and target_u.role != "viewer":
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    # 1. Update username bila valid
    clean_user = username.strip()
    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,50}$", clean_user):
        return RedirectResponse(_flash_profile_users(False, "Username harus 3-50 karakter alfanumerik (hanya huruf, angka, _, -, .)"), status_code=303)
    if clean_user != target_u.username:
        dup = db.query(User).filter(User.username == clean_user, User.id != uid).first()
        if dup:
            return RedirectResponse(_flash_profile_users(False, f"Username '{clean_user}' sudah dipakai pengguna lain"), status_code=303)
        target_u.username = clean_user[:100]

    # 2. Update password baru bila diisi
    pwd_clean = password.strip()
    if pwd_clean:
        valid, err_msg = security_auth.validate_password_strength(pwd_clean)
        if not valid:
            return RedirectResponse(_flash_profile_users(False, err_msg), status_code=303)
        target_u.password_hash = pwd_ctx.hash(pwd_clean)
        target_u.password_changed_at = datetime.utcnow()
        # Cabut seluruh sesi aktif milik akun target
        db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)

    # 3. Update status aktif (kecuali Master Admin atau diri sendiri)
    if not target_u.is_master_admin() and uid != user.id:
        new_act = 1 if is_active in ("1", "true", "on") else 0
        if not new_act and target_u.is_active:
            db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)
        target_u.is_active = new_act

    # 4. Update peran & izin (kecuali Master Admin)
    if not target_u.is_master_admin():
        if role in ("operator", "viewer"):
            target_u.role = role
        if target_u.role == "operator":
            form_data = await request.form()
            perms_dict = {
                pk: bool(form_data.get(f"perm_{pk}"))
                for pk in security_auth.OPERATOR_PERMISSIONS
            }
            target_u.permissions = json.dumps(perms_dict)
        else:
            target_u.permissions = None

    _audit(db, user.username, "user_edit", f"{target_u.username} ({target_u.role})", "berhasil")
    db.commit()
    return RedirectResponse(_flash_profile_users(True, f"Akun '{target_u.username}' berhasil diperbarui"), status_code=303)


@app.post("/users/{uid}/delete")
def user_delete(
    request: Request, uid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        return RedirectResponse("/profile?tab=users", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if uid == user.id:
        return RedirectResponse(_flash_profile_users(False, "Tidak bisa menghapus akun Anda sendiri"), status_code=303)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    if target_u.is_master_admin():
        if not user.is_master_admin():
            return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)
        return RedirectResponse(_flash_profile_users(False, "Akun Master Administrator tidak dapat dihapus"), status_code=303)

    if not can_manage_users and target_u.role != "viewer":
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    # Cabut sesi pengguna yang dihapus
    db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)

    _audit(db, user.username, "user_delete", f"{target_u.username} ({target_u.role})", "berhasil")
    db.delete(target_u)
    db.commit()
    return RedirectResponse(_flash_profile_users(True, f"Pengguna '{target_u.username}' berhasil dihapus"), status_code=303)


@app.post("/users/{uid}/toggle-active")
def user_toggle_active(
    request: Request, uid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        return RedirectResponse("/profile?tab=users", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if uid == user.id:
        return RedirectResponse(_flash_profile_users(False, "Tidak bisa menonaktifkan akun sendiri"), status_code=303)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    if target_u.is_master_admin():
        if not user.is_master_admin():
            return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)
        return RedirectResponse(_flash_profile_users(False, "Status akun Master Administrator tidak dapat diubah"), status_code=303)

    if not can_manage_users and target_u.role != "viewer":
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    new_active = 0 if target_u.is_active else 1
    target_u.is_active = new_active
    status_label = "diaktifkan" if new_active else "dikunci/dinonaktifkan"

    if not new_active:
        # Cabut seluruh sesi aktif seketika
        db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)

    _audit(db, user.username, "user_toggle_active", f"{target_u.username} ({status_label})", "berhasil")
    db.commit()
    return RedirectResponse(_flash_profile_users(True, f"Akun '{target_u.username}' berhasil {status_label}"), status_code=303)


@app.post("/users/{uid}/edit-permissions")
async def user_edit_permissions(
    request: Request, uid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    if not can_manage_users:
        return RedirectResponse("/profile?tab=users", status_code=303)
    _verify_csrf_form(request, csrf_token)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u or target_u.role != "operator":
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    form_data = await request.form()
    perms_dict = {
        pk: bool(form_data.get(f"perm_{pk}"))
        for pk in security_auth.OPERATOR_PERMISSIONS
    }
    target_u.permissions = json.dumps(perms_dict)
    _audit(db, user.username, "user_edit_perms", f"{target_u.username} (wewenang diperbarui)", "berhasil")
    db.commit()
    return RedirectResponse(_flash_profile_users(True, f"Wewenang untuk operator '{target_u.username}' berhasil diperbarui"), status_code=303)


# ---------------------------------------------------------------------------
# PENGELOLAAN 2FA TERKELOLA OLEH ADMINISTRATOR / OPERATOR (TOTP RFC 6238)
# ---------------------------------------------------------------------------
@app.post("/api/users/{uid}/2fa/init")
def api_user_2fa_init(
    request: Request,
    uid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Inisialisasi pengaturan 2FA TOTP untuk pengguna (khusus Master Admin & Operator)."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin manajemen pengguna")

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        raise HTTPException(status_code=403, detail="Akses ditolak: izin manajemen pengguna diperlukan")

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    if target_u.is_master_admin() and not user.is_master_admin():
        raise HTTPException(status_code=403, detail="Akses ditolak: tidak dapat mengubah akun Master Admin")

    if not can_manage_users and target_u.role != "viewer":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya berwenang mengelola akun Viewer")

    secret = security_auth.generate_totp_secret()
    secret_display = security_auth.format_secret_display(secret)
    uri = security_auth.generate_totp_uri(secret, target_u.username, "Pantau Server")
    qr_data_url = security_auth.generate_qr_data_url(uri)

    return {
        "ok": True,
        "user_id": target_u.id,
        "username": target_u.username,
        "role": target_u.role,
        "secret": secret,
        "secret_display": secret_display,
        "qr_data_url": qr_data_url,
    }


@app.post("/api/users/{uid}/2fa/confirm")
def api_user_2fa_confirm(
    request: Request,
    uid: int,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Verifikasi 6-digit kode TOTP dari ponsel pengguna dan aktifkan 2FA secara permanen."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin manajemen pengguna")

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        raise HTTPException(status_code=403, detail="Akses ditolak: izin manajemen pengguna diperlukan")

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    if target_u.is_master_admin() and not user.is_master_admin():
        raise HTTPException(status_code=403, detail="Akses ditolak: tidak dapat mengubah akun Master Admin")

    if not can_manage_users and target_u.role != "viewer":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya berwenang mengelola akun Viewer")

    secret = str(body.get("secret", "")).strip().replace(" ", "")
    code = str(body.get("code", "")).strip().replace(" ", "")

    if not secret or not code:
        raise HTTPException(status_code=400, detail="Kunci rahasia (secret) dan kode verifikasi 6-digit wajib diisi")

    if not security_auth.verify_totp(secret, code):
        raise HTTPException(status_code=400, detail="Kode verifikasi 6-digit salah atau jam perangkat ponsel pengguna tidak sinkron.")

    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    target_u.totp_secret = secret
    target_u.totp_enabled = 1
    target_u.recovery_codes = json.dumps(hashed_codes)

    _audit(
        db, user.username, "user_2fa_enable",
        f"Pengguna {target_u.username} ({target_u.role})", "2FA berhasil diaktifkan oleh admin"
    )
    db.commit()

    return {
        "ok": True,
        "message": f"Perlindungan 2FA untuk pengguna '{target_u.username}' berhasil diaktifkan!",
        "recovery_codes": plain_codes,
        "username": target_u.username,
    }


@app.post("/api/users/{uid}/2fa/disable")
def api_user_2fa_disable(
    request: Request,
    uid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Nonaktifkan perlindungan 2FA untuk pengguna yang ditentukan."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin manajemen pengguna")

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        raise HTTPException(status_code=403, detail="Akses ditolak: izin manajemen pengguna diperlukan")

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    if target_u.is_master_admin() and not user.is_master_admin():
        raise HTTPException(status_code=403, detail="Akses ditolak: tidak dapat mengubah akun Master Admin")

    if not can_manage_users and target_u.role != "viewer":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya berwenang mengelola akun Viewer")

    target_u.totp_enabled = 0
    target_u.totp_secret = None
    target_u.recovery_codes = None

    _audit(
        db, user.username, "user_2fa_disable",
        f"Pengguna {target_u.username} ({target_u.role})", "2FA dinonaktifkan oleh admin"
    )
    db.commit()

    return {
        "ok": True,
        "message": f"Perlindungan 2FA untuk pengguna '{target_u.username}' telah dinonaktifkan.",
        "username": target_u.username,
    }


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
