"""Security, authentication, CSRF, and session dependencies."""

import hashlib
import hmac as _hmac
import secrets
import threading
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, Request
from passlib.context import CryptContext
from sqlalchemy.orm import Session

try:
    from config import settings
    from models import AppSession, Server, User
    import security_auth
    from core.database import SessionLocal, get_db
    from core.utils import _clean_str, hash_api_key
    from services.audit_service import _audit
except ImportError:
    from server.config import settings
    from server.models import AppSession, Server, User
    from server import security_auth
    from server.core.database import SessionLocal, get_db
    from server.core.utils import _clean_str, hash_api_key
    from server.services.audit_service import _audit

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
SESSION_COOKIE = "session_id"
SESSION_TTL = timedelta(hours=12)

_SECRET_KEY: str = ""


def set_secret_key(key: str) -> None:
    global _SECRET_KEY
    _SECRET_KEY = key


def get_secret_key() -> str:
    global _SECRET_KEY
    if not _SECRET_KEY:
        _SECRET_KEY = settings.resolve_secret_key()
    return _SECRET_KEY


# ---------------------------------------------------------------------------
# Sesi Unlock Web Terminal (Ephemeral Lease)
# ---------------------------------------------------------------------------
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


def set_terminal_unlock(user_id: int, server_id: int, duration_minutes: int) -> None:
    with _terminal_unlocks_lock:
        _terminal_unlocks[(user_id, server_id)] = datetime.utcnow() + timedelta(minutes=duration_minutes)


def revoke_terminal_unlock(user_id: int, server_id: int) -> None:
    with _terminal_unlocks_lock:
        _terminal_unlocks.pop((user_id, server_id), None)


# ---------------------------------------------------------------------------
# Sesi Unlock Remote File Manager (Ephemeral Lease)
# ---------------------------------------------------------------------------
_file_manager_unlocks: dict[tuple[int, int], datetime] = {}
_file_manager_unlocks_lock = threading.Lock()


def is_file_manager_unlocked(user_id: int, server_id: int) -> bool:
    with _file_manager_unlocks_lock:
        exp = _file_manager_unlocks.get((user_id, server_id))
        if not exp:
            return False
        if datetime.utcnow() > exp:
            _file_manager_unlocks.pop((user_id, server_id), None)
            return False
        return True


def get_file_manager_lease_remaining(user_id: int, server_id: int) -> int:
    with _file_manager_unlocks_lock:
        exp = _file_manager_unlocks.get((user_id, server_id))
        if not exp:
            return 0
        rem = int((exp - datetime.utcnow()).total_seconds())
        if rem <= 0:
            _file_manager_unlocks.pop((user_id, server_id), None)
            return 0
        return rem


def set_file_manager_unlock(user_id: int, server_id: int, duration_minutes: int) -> None:
    with _file_manager_unlocks_lock:
        _file_manager_unlocks[(user_id, server_id)] = datetime.utcnow() + timedelta(minutes=duration_minutes)


def revoke_file_manager_unlock(user_id: int, server_id: int) -> None:
    with _file_manager_unlocks_lock:
        _file_manager_unlocks.pop((user_id, server_id), None)


# ---------------------------------------------------------------------------
# Pelacak IP & Validasi Kunci Agen
# ---------------------------------------------------------------------------
_agent_ip_tracker: dict[int, dict[str, float]] = {}  # server_id -> {ip_str: timestamp_epoch}
_agent_tracker_lock = threading.Lock()
_AGENT_KEY_CACHE: dict[str, tuple[int, float]] = {}


def _get_cached_server_id(raw_key: str) -> Optional[int]:
    """Resolusi ID server dari API key dengan cache in-memory 120 detik non-blocking."""
    if not raw_key:
        return None
    hk = hash_api_key(raw_key)
    now = time.time()
    cached = _AGENT_KEY_CACHE.get(hk)
    if cached and cached[1] > now:
        return cached[0]
    with SessionLocal() as db:
        srv = db.query(Server.id).filter(Server.api_key == hk, Server.is_active == 1).first()
        if not srv:
            return None
        sid = srv[0]
        _AGENT_KEY_CACHE[hk] = (sid, now + 120.0)
        return sid


# ---------------------------------------------------------------------------
# Manajemen Sesi Persisten
# ---------------------------------------------------------------------------
def _prune_expired_sessions(db: Session) -> None:
    """Hapus sesi kedaluwarsa."""
    db.query(AppSession).filter(AppSession.expires_at < datetime.utcnow()).delete(
        synchronize_session=False
    )


def create_session(db: Session, user_id: int, ip: str, user_agent: Optional[str] = None) -> str:
    sid = secrets.token_hex(32)
    db.add(
        AppSession(
            sid=sid,
            user_id=user_id,
            ip_address=_clean_str(ip, None, 45),
            user_agent=_clean_str(user_agent, None, 255),
            expires_at=datetime.utcnow() + SESSION_TTL,
        )
    )
    return sid


def get_current_user(request: Request, db: Session) -> Optional[User]:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid:
        return None
    row = db.query(AppSession).filter(AppSession.sid == sid).first()
    if not row:
        return None
    now = datetime.utcnow()
    if now > row.expires_at:
        try:
            db.delete(row)
            db.commit()
        except Exception:
            db.rollback()
        return None

    # Sliding session window: perpanjang jika sisa < 6 jam
    if row.expires_at - now < (SESSION_TTL / 2):
        try:
            row.expires_at = now + SESSION_TTL
            db.commit()
        except Exception:
            db.rollback()

    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.is_active:
        return None
    return user


def require_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency FastAPI: wajib login."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(request: Request, db: Session = Depends(get_db)) -> User:
    """Dependency FastAPI: wajib Master Admin atau Operator."""
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
    """Dependency FastAPI: khusus pengguna dengan izin File Manager dan sesi aktif terotentikasi."""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Silakan login terlebih dahulu")
    if not user.has_perm("can_file_manager"):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin File Manager diperlukan")

    sid = request.path_params.get("sid")
    if sid:
        try:
            sid_int = int(sid)
            rem = get_file_manager_lease_remaining(user.id, sid_int)
            if rem <= 0:
                raise HTTPException(
                    status_code=423,
                    detail="Sesi File Manager terkunci. Diperlukan otentikasi kata sandi untuk mengakses berkas server klien.",
                )
        except ValueError:
            pass
    return user


# ---------------------------------------------------------------------------
# Proteksi CSRF
# ---------------------------------------------------------------------------
def _csrf_token(sid: str) -> str:
    """Generate CSRF token dari session ID menggunakan HMAC-SHA256."""
    sk = get_secret_key()
    if not sid or not sk:
        return ""
    return _hmac.new(
        sk.encode("utf-8"),
        sid.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _verify_csrf_form(request: Request, form_token: str) -> None:
    """Validasi CSRF token dari form field. Raise 403 jika tidak valid."""
    sid = request.cookies.get(SESSION_COOKIE, "")
    if not sid:
        return
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


def _verify_operator_password(
    user: User,
    password: str,
    totp_code: str = "",
    action_name: str = "privileged_action",
    target_info: str = "",
    db: Optional[Session] = None,
) -> None:
    """Verifikasi kata sandi operator login untuk tindakan berisiko tinggi (Step-Up Auth)."""
    clean_pwd = _clean_str(password, "", 256)
    if not clean_pwd:
        if db:
            _audit(db, user.username, f"{action_name}_fail", f"{target_info} (kata sandi tidak diisi)", "gagal")
            db.commit()
        raise HTTPException(status_code=401, detail="Kata sandi akun operator diperlukan")

    if not pwd_ctx.verify(clean_pwd, user.password_hash):
        if db:
            _audit(db, user.username, f"{action_name}_fail", f"{target_info} (kata sandi salah)", "gagal")
            db.commit()
        raise HTTPException(status_code=401, detail="Kata sandi akun operator salah")

    if user.totp_enabled and user.totp_secret:
        clean_totp = _clean_str(totp_code, "", 10)
        if not clean_totp or not security_auth.verify_totp(user.totp_secret, clean_totp):
            if db:
                _audit(db, user.username, f"{action_name}_fail", f"{target_info} (kode 2FA tidak valid)", "gagal")
                db.commit()
            raise HTTPException(status_code=401, detail="Kode 2FA / TOTP tidak valid atau kedaluwarsa")
