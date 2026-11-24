import json
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from config import settings
import security_auth
from core.database import get_db
from core.security import verify_password, create_access_token, decode_access_token, oauth2_scheme
from models.user import User, LoginAttempt
from models.misc import AuditLog

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

LOGIN_MAX_FAILS = 5
LOGIN_LOCK_DURATIONS = [60, 300, 1800, 7200]

def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

def _login_trial(db: Session, ip: str) -> LoginAttempt:
    row = db.query(LoginAttempt).filter(LoginAttempt.ip_address == ip).first()
    if row is None:
        row = LoginAttempt(ip_address=ip, fails=0, updated_at=datetime.utcnow())
        db.add(row)
        db.flush()
    return row

def _lock_remaining(row: LoginAttempt) -> int:
    if row.lock_until is None:
        return 0
    rem = int((row.lock_until - datetime.utcnow()).total_seconds())
    return max(0, rem)

class LoginRequest(BaseModel):
    username: str
    password: str

class Login2faRequest(BaseModel):
    preauth_token: str
    code: str

class TokenResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[dict] = None
    requires_2fa: bool = False
    preauth_token: Optional[str] = None
    username: Optional[str] = None

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    username = payload.get("sub")
    if not username:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    user = db.query(User).filter(User.username == username, User.is_active == 1).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    return user

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    trial = _login_trial(db, ip)
    remaining = _lock_remaining(trial)
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Terlalu banyak percobaan login gagal. Silakan tunggu {remaining} detik."
        )

    clean_username = req.username.strip()
    user = db.query(User).filter(User.username == clean_username).first()
    if not user or not verify_password(req.password, user.password_hash):
        trial.fails = (trial.fails or 0) + 1
        trial.updated_at = datetime.utcnow()
        if trial.fails >= LOGIN_MAX_FAILS:
            lock_secs = LOGIN_LOCK_DURATIONS[min(trial.fails - LOGIN_MAX_FAILS, len(LOGIN_LOCK_DURATIONS) - 1)]
            trial.lock_until = datetime.utcnow() + timedelta(seconds=lock_secs)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")

    # If 2FA is active, issue short-lived pre-auth token (300 seconds)
    if user.totp_enabled and user.totp_secret:
        preauth_tok = security_auth.create_preauth_token(user.id, settings.SECRET_KEY, ttl_seconds=300)
        return {
            "requires_2fa": True,
            "preauth_token": preauth_tok,
            "username": user.username,
            "token_type": "bearer",
        }

    trial.fails = 0
    trial.lock_until = None
    trial.updated_at = datetime.utcnow()
    user.last_login_at = datetime.utcnow()

    # Catat log audit login berhasil
    audit = AuditLog(
        username=user.username,
        action="user_login",
        target=user.username,
        result="success",
        meta=json.dumps({"ip": ip}),
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    token = create_access_token(data={"sub": user.username, "role": user.role, "uid": user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "requires_2fa": False,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "is_master_admin": user.is_master_admin,
            "is_operator": user.is_operator,
            "is_viewer": user.is_viewer,
            "totp_enabled": bool(user.totp_enabled),
            "permissions": user.get_permissions(),
            "allowed_server_ids": user.get_allowed_server_ids()
        }
    }

@router.post("/login-2fa", response_model=TokenResponse)
def login_2fa(req: Login2faRequest, request: Request, db: Session = Depends(get_db)):
    ip = _client_ip(request)
    uid = security_auth.verify_preauth_token(req.preauth_token, settings.SECRET_KEY)
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="2FA session has expired or is invalid. Please sign in again."
        )

    user = db.query(User).filter(User.id == uid).first()
    if not user or not user.is_active or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is invalid or 2FA is not enabled."
        )

    clean_code = req.code.strip()
    is_valid = False

    # 1. Try 6-digit TOTP code
    totp_clean = clean_code.replace(" ", "").replace("-", "")
    if len(totp_clean) == 6 and totp_clean.isdigit():
        if security_auth.verify_totp(user.totp_secret, totp_clean):
            is_valid = True

    # 2. Try Emergency Recovery Code if TOTP didn't match
    if not is_valid and user.recovery_codes:
        ok_rec, next_hashes_json = security_auth.verify_and_consume_recovery_code(clean_code, user.recovery_codes)
        if ok_rec:
            is_valid = True
            user.recovery_codes = next_hashes_json

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 2FA authenticator code or emergency recovery code."
        )

    trial = _login_trial(db, ip)
    trial.fails = 0
    trial.lock_until = None
    trial.updated_at = datetime.utcnow()
    user.last_login_at = datetime.utcnow()

    audit = AuditLog(
        username=user.username,
        action="user_login_2fa",
        target=user.username,
        result="success",
        meta=json.dumps({"ip": ip}),
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    token = create_access_token(data={"sub": user.username, "role": user.role, "uid": user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "requires_2fa": False,
        "user": {
            "id": user.id,
            "username": user.username,
            "role": user.role,
            "is_master_admin": user.is_master_admin,
            "is_operator": user.is_operator,
            "is_viewer": user.is_viewer,
            "totp_enabled": bool(user.totp_enabled),
            "permissions": user.get_permissions(),
            "allowed_server_ids": user.get_allowed_server_ids()
        }
    }

@router.post("/logout")
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    audit = AuditLog(
        username=user.username,
        action="user_logout",
        target=user.username,
        result="success",
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()
    return {"ok": True, "message": "Logged out successfully"}

@router.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_master_admin": user.is_master_admin,
        "is_operator": user.is_operator,
        "is_viewer": user.is_viewer,
        "totp_enabled": bool(user.totp_enabled),
        "permissions": user.get_permissions(),
        "allowed_server_ids": user.get_allowed_server_ids()
    }
