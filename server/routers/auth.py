from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from config import settings
import security_auth
from core.database import get_db
from core.security import verify_password, create_access_token, decode_access_token, oauth2_scheme
from models.user import User

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

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
def login(req: LoginRequest, db: Session = Depends(get_db)):
    clean_username = req.username.strip()
    user = db.query(User).filter(User.username == clean_username).first()
    if not user or not verify_password(req.password, user.password_hash):
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

    user.last_login_at = datetime.utcnow()
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
def login_2fa(req: Login2faRequest, db: Session = Depends(get_db)):
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

    user.last_login_at = datetime.utcnow()
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
