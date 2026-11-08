"""Authentication and session lifecycle router."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

try:
    from config import settings
    from models import AppSession, LoginAttempt, User
    import security_auth
    from core.database import get_db
    from core.security import (
        SESSION_COOKIE,
        SESSION_TTL,
        create_session,
        get_current_user,
        get_secret_key,
        pwd_ctx,
        _csrf_token,
        _prune_expired_sessions,
    )
    from core.templates import tpl
    from core.utils import _clean_ua, _client_ip
    from services.audit_service import _audit
except ImportError:
    from server.config import settings
    from server.models import AppSession, LoginAttempt, User
    import server.security_auth as security_auth
    from server.core.database import get_db
    from server.core.security import (
        SESSION_COOKIE,
        SESSION_TTL,
        create_session,
        get_current_user,
        get_secret_key,
        pwd_ctx,
        _csrf_token,
        _prune_expired_sessions,
    )
    from server.core.templates import tpl
    from server.core.utils import _clean_ua, _client_ip
    from server.services.audit_service import _audit
    from server import security_auth
    from server.core.database import get_db
    from server.core.security import (
        SESSION_COOKIE,
        SESSION_TTL,
        create_session,
        get_current_user,
        get_secret_key,
        pwd_ctx,
        _prune_expired_sessions,
    )
    from server.core.templates import tpl
    from server.core.utils import _clean_ua, _client_ip
    from server.services.audit_service import _audit

logger = logging.getLogger("pantau.auth")

router = APIRouter(tags=["Authentication"])

LOGIN_MAX_FAILS = 5
LOGIN_LOCK_DURATIONS = [60, 300, 1800, 7200]  # 1 mnt, 5 mnt, 30 mnt, 2 jam


def _login_trial(db: Session, ip: str) -> LoginAttempt:
    row = db.query(LoginAttempt).filter(LoginAttempt.ip_address == ip).first()
    if row is None:
        row = LoginAttempt(ip_address=ip)
        db.add(row)
        db.flush()
    return row


def _lock_remaining(row: LoginAttempt) -> int:
    if row.lock_until is None:
        return 0
    return max(0, int((row.lock_until - datetime.utcnow()).total_seconds()))


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return tpl(request, "login.html", {"error": None})


@router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    is_json = "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with") == "XMLHttpRequest"
    ip = _client_ip(request)
    row = _login_trial(db, ip)
    if _lock_remaining(row) > 0:
        wait = int((row.lock_until - datetime.utcnow()).total_seconds())
        db.rollback()
        msg = f"Terlalu banyak percobaan. Coba lagi dalam {wait} detik."
        if is_json:
            return JSONResponse(status_code=429, content={"detail": msg})
        return tpl(request, "login.html", {"error": msg})

    user = db.query(User).filter(User.username == username).first()
    if not user or not pwd_ctx.verify(password, user.password_hash):
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
            logger.warning("[AUTH] Login gagal terlalu banyak dari IP %s — kunci %d detik", ip, lock_secs)
        db.commit()
        if is_json:
            return JSONResponse(status_code=400, content={"detail": "Username atau kata sandi salah."})
        return tpl(request, "login.html", {"error": "Username atau password salah"})

    if not user.is_active:
        if is_json:
            return JSONResponse(status_code=403, content={"detail": "Akun Anda telah dinonaktifkan oleh Administrator."})
        return tpl(request, "login.html", {"error": "Akun Anda telah dinonaktifkan oleh Administrator."})

    if user.totp_enabled and user.totp_secret:
        preauth_tok = security_auth.create_preauth_token(user.id, get_secret_key())
        if is_json:
            resp = JSONResponse({"ok": True, "requires_2fa": True, "redirect": "/login/2fa"})
        else:
            resp = RedirectResponse("/login/2fa", status_code=303)
        resp.set_cookie(
            "preauth_session",
            preauth_tok,
            httponly=True,
            samesite="lax",
            secure=settings.SESSION_COOKIE_SECURE,
            max_age=300,
            path="/",
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
    _audit(
        db,
        user.username,
        "login",
        client_target,
        "berhasil",
        meta={"ip": ip, "ua": request.headers.get("user-agent", ""), "browser": ua_summary},
    )
    db.commit()
    csrf_val = _csrf_token(sid)
    if is_json:
        resp = JSONResponse({"ok": True, "redirect": "/dashboard", "csrf_token": csrf_val})
    else:
        resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )
    resp.set_cookie(
        "pantau_csrf_token",
        csrf_val,
        httponly=False,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )
    return resp


@router.get("/login/2fa", response_class=HTMLResponse)
def login_2fa_page(request: Request, db: Session = Depends(get_db)):
    preauth_tok = request.cookies.get("preauth_session")
    uid = security_auth.verify_preauth_token(preauth_tok, get_secret_key()) if preauth_tok else None
    if not uid:
        return RedirectResponse("/login", status_code=303)
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or not user.totp_enabled:
        return RedirectResponse("/login", status_code=303)
    return tpl(request, "login_2fa.html", {"user": user})


@router.post("/login/2fa")
def login_2fa_submit(
    request: Request,
    code: str = Form(...),
    db: Session = Depends(get_db),
):
    is_json = "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with") == "XMLHttpRequest"
    ip = _client_ip(request)
    preauth_tok = request.cookies.get("preauth_session")
    uid = security_auth.verify_preauth_token(preauth_tok, get_secret_key()) if preauth_tok else None
    if not uid:
        if is_json:
            return JSONResponse(status_code=401, content={"detail": "Sesi pra-otentikasi 2FA telah kedaluwarsa. Silakan masuk kembali."})
        return RedirectResponse("/login", status_code=303)
    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or not user.totp_enabled:
        if is_json:
            return JSONResponse(status_code=401, content={"detail": "Pengguna tidak valid atau 2FA belum diaktifkan."})
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
        msg = "Kode verifikasi 2FA atau kode cadangan darurat tidak cocok."
        if is_json:
            return JSONResponse(status_code=400, content={"detail": msg})
        return tpl(
            request,
            "login_2fa.html",
            {
                "user": user,
                "error": msg,
            },
        )

    user.last_login_at = datetime.utcnow()
    user.last_login_ip = ip
    _prune_expired_sessions(db)
    sid = create_session(db, user.id, ip, request.headers.get("user-agent"))
    action_note = "masuk via 2FA (Recovery Code)" if used_recovery else "masuk via 2FA (TOTP)"
    ua_summary = _clean_ua(request.headers.get("user-agent"))
    client_target = f"{action_note} dari {ip}" + (f" ({ua_summary})" if ua_summary else "")
    _audit(
        db,
        user.username,
        "login_2fa",
        client_target,
        "berhasil",
        meta={"ip": ip, "ua": request.headers.get("user-agent", ""), "browser": ua_summary},
    )
    db.commit()

    csrf_val = _csrf_token(sid)
    if is_json:
        resp = JSONResponse({"ok": True, "redirect": "/dashboard", "csrf_token": csrf_val})
    else:
        resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("preauth_session", path="/")
    resp.set_cookie(
        SESSION_COOKIE,
        sid,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )
    resp.set_cookie(
        "pantau_csrf_token",
        csrf_val,
        httponly=False,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=int(SESSION_TTL.total_seconds()),
        path="/",
    )
    return resp


@router.get("/logout")
@router.post("/logout")
@router.post("/api/auth/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    is_json = "application/json" in request.headers.get("accept", "") or request.headers.get("x-requested-with") == "XMLHttpRequest"
    user = get_current_user(request, db)
    if user:
        ip = _client_ip(request)
        ua_summary = _clean_ua(request.headers.get("user-agent"))
        client_target = f"keluar dari {ip}" + (f" ({ua_summary})" if ua_summary else "")
        _audit(
            db,
            user.username,
            "logout",
            client_target,
            "berhasil",
            meta={"ip": ip, "ua": request.headers.get("user-agent", ""), "browser": ua_summary},
        )
        db.commit()
    sid = request.cookies.get(SESSION_COOKIE)
    if sid:
        db.query(AppSession).filter(AppSession.sid == sid).delete(synchronize_session=False)
        db.commit()
    if is_json:
        resp = JSONResponse({"ok": True, "redirect": "/login"})
    else:
        resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(SESSION_COOKIE, path="/")
    resp.delete_cookie("preauth_session", path="/")
    resp.delete_cookie("pantau_csrf_token", path="/")
    return resp


@router.get("/api/auth/me")
def api_auth_me(request: Request, db: Session = Depends(get_db)):
    """Mendapatkan data identitas pengguna saat ini untuk SPA."""
    user = get_current_user(request, db)
    if not user:
        return JSONResponse(status_code=401, content={"detail": "Belum terautentikasi"})
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "role_display": "MASTER ADMIN" if user.role == "master_admin" else ("OPERATOR" if user.role == "operator" else "VIEWER"),
        "is_master_admin": getattr(user, "is_master_admin", lambda: False)(),
        "is_operator": getattr(user, "is_operator", lambda: False)(),
    }
