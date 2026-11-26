import json
import re
from datetime import datetime
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import verify_password, get_password_hash
from routers.auth import get_current_user
from models.user import User
from models.server import Server
from models.misc import AuditLog
from security_auth import OPERATOR_PERMISSIONS
import security_auth

router = APIRouter(prefix="/api/users", tags=["User Management"])


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------
class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class AdminResetPasswordRequest(BaseModel):
    new_password: str


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    role: str = Field("operator", pattern="^(operator|viewer)$")
    permissions: Optional[Dict[str, bool]] = None
    allowed_server_ids: Optional[List[int]] = None


class UserUpdateRequest(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    confirm_password: Optional[str] = None
    current_password: Optional[str] = None
    role: Optional[str] = Field(None, pattern="^(master_admin|operator|viewer)$")
    is_active: Optional[int] = Field(None, ge=0, le=1)
    permissions: Optional[Dict[str, bool]] = None
    allowed_server_ids: Optional[List[int]] = None


class UserStatusUpdateRequest(BaseModel):
    is_active: int = Field(..., ge=0, le=1)


class TotpConfirmRequest(BaseModel):
    secret: str
    code: str


class TotpDisableRequest(BaseModel):
    password: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: int
    totp_enabled: int = 0
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    password_changed_at: Optional[datetime] = None
    created_by: Optional[str] = None
    permissions: Optional[Dict[str, bool]] = None
    allowed_server_ids: Optional[List[int]] = None

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    id: int
    username: str
    role: str
    is_master_admin: bool
    is_active: int
    totp_enabled: int = 0
    recovery_codes_count: int = 0
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    password_changed_at: Optional[datetime] = None
    permissions: Optional[dict] = None
    allowed_server_ids: Optional[list] = None


def _enforce_password_strength(password: str) -> None:
    """Enforce NIST SP 800-63B password complexity via canonical security_auth."""
    ok, err_msg = security_auth.validate_password_strength(password)
    if not ok:
        raise HTTPException(status_code=400, detail=err_msg)


def _serialize_user(u: User) -> dict:
    """Serialize User ORM object to UserResponse dict."""
    return {
        "id": u.id,
        "username": u.username,
        "role": u.role,
        "is_active": u.is_active,
        "totp_enabled": int(u.totp_enabled or 0),
        "created_at": u.created_at,
        "last_login_at": u.last_login_at,
        "last_login_ip": getattr(u, "last_login_ip", None),
        "password_changed_at": getattr(u, "password_changed_at", None),
        "created_by": u.created_by,
        "permissions": u.get_permissions(),
        "allowed_server_ids": u.get_allowed_server_ids(),
    }


def _get_authorized_target_user(db: Session, actor: User, user_id: int) -> User:
    """Fetch target user enforcing RBAC permissions and Zero-Knowledge 404 masking."""
    can_manage_users = actor.is_master_admin or actor.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or actor.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have user management permissions."
        )

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    if target.is_master_admin and not actor.is_master_admin:
        raise HTTPException(status_code=404, detail="User not found.")
    if not can_manage_users and target.role != "viewer":
        raise HTTPException(status_code=404, detail="User not found.")
    return target


# ---------------------------------------------------------------------------
# Metadata Endpoints
# ---------------------------------------------------------------------------
@router.get("/metadata")
@router.get("/meta/metadata")
def get_user_metadata(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Kembalikan kamus matriks 16 izin granular dan daftar seluruh aset server aktif."""
    if not (user.is_master_admin or user.has_perm("can_manage_users") or user.has_perm("can_manage_viewers")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    servers = (
        db.query(Server.id, Server.hostname, Server.ip_address)
        .filter(Server.is_active == 1)
        .order_by(Server.hostname.asc())
        .all()
    )

    return {
        "permissions": OPERATOR_PERMISSIONS,
        "servers": [
            {"id": s.id, "hostname": s.hostname, "ip_address": s.ip_address}
            for s in servers
        ]
    }


# ---------------------------------------------------------------------------
# Current User Self-Service Endpoints
# ---------------------------------------------------------------------------
@router.get("/profile", response_model=UserProfileResponse)
@router.get("/me", response_model=UserProfileResponse)
def get_user_profile(user: User = Depends(get_current_user)):
    """Melihat profil akun yang sedang login."""
    rec_count = 0
    if user.recovery_codes:
        try:
            codes = json.loads(user.recovery_codes)
            rec_count = len(codes) if isinstance(codes, list) else 0
        except Exception:
            rec_count = 0
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_master_admin": user.is_master_admin,
        "is_active": user.is_active,
        "totp_enabled": int(user.totp_enabled or 0),
        "recovery_codes_count": rec_count,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
        "last_login_ip": getattr(user, "last_login_ip", None),
        "password_changed_at": getattr(user, "password_changed_at", None),
        "permissions": user.get_permissions(),
        "allowed_server_ids": user.get_allowed_server_ids(),
    }


@router.put("/me/password")
def change_own_password(
    req: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ganti kata sandi mandiri bagi pengguna yang sedang login."""
    if user.is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot change credentials directly. Managed by administrator."
        )

    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect."
        )

    _enforce_password_strength(req.new_password)

    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=400,
            detail="New password cannot be the same as the current password."
        )

    now = datetime.utcnow()
    user.password_hash = get_password_hash(req.new_password)
    user.password_changed_at = now
    db.add(AuditLog(
        username=user.username,
        action="user_password_change",
        target=user.username,
        result="success",
        created_at=now,
    ))
    db.commit()

    return {"ok": True, "message": "Password updated successfully."}


# ---------------------------------------------------------------------------
# User Administration Endpoints (Master Admin & Authorized Operators)
# ---------------------------------------------------------------------------
@router.get("", response_model=List[UserResponse])
def list_users(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Melihat seluruh daftar pengguna terdaftar lengkap dengan wewenang dan cakupan server."""
    if user.is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Viewers do not have user management permissions."
        )

    if user.is_master_admin:
        query = db.query(User)
    elif user.has_perm("can_manage_users"):
        # Zero-Knowledge: Master Admin disembunyikan total dari pandangan Operator
        query = db.query(User).filter(~User.role.in_(["master_admin", "master-admin"]))
    elif user.has_perm("can_manage_viewers"):
        # Operator terbatas hanya melihat akun berkategori viewer
        query = db.query(User).filter(User.role.in_(["viewer", "guest", "tamu"]))
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have user management permissions."
        )

    users = query.order_by(User.id.asc()).all()
    return [_serialize_user(u) for u in users]


@router.post("", response_model=UserResponse)
def create_user(
    req: UserCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Membuat akun pengguna baru (Operator dengan izin modular atau Viewer)."""
    if user.is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Viewers do not have user management permissions."
        )

    can_manage_users = user.is_master_admin or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")

    if not can_manage_viewers:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to create users."
        )

    clean_username = req.username.strip()
    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Username '{clean_username}' already exists."
        )

    _enforce_password_strength(req.password)

    # Larangan membuat akun master-admin
    if not user.is_master_admin and req.role in ("master_admin", "master-admin"):
        raise HTTPException(status_code=400, detail="Cannot create master-admin account.")

    # Operator terbatas hanya bisa membuat role viewer
    if not can_manage_users:
        assigned_role = "viewer"
    else:
        assigned_role = req.role if req.role in ("operator", "viewer") else "viewer"

    perms_json = None
    allowed_servers_json = None
    if assigned_role == "operator":
        if req.permissions is not None:
            if not user.is_master_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only master-admin can assign operator permissions.",
                )
            perms_json = json.dumps(req.permissions)
        creator_scope = user.get_allowed_server_ids()
        if creator_scope is not None:
            requested = sorted(req.allowed_server_ids or [])
            if not requested or not set(requested).issubset(set(creator_scope)):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Scoped operators can only assign assets within their own scope.",
                )
            allowed_servers_json = json.dumps(requested)
        elif req.allowed_server_ids is not None:
            allowed_servers_json = json.dumps(sorted(req.allowed_server_ids)) if req.allowed_server_ids else None

    now = datetime.utcnow()
    new_user = User(
        username=clean_username,
        password_hash=get_password_hash(req.password),
        role=assigned_role,
        is_active=1,
        created_by=user.username,
        password_changed_at=now,
        permissions=perms_json,
        allowed_server_ids=allowed_servers_json,
    )
    db.add(new_user)
    db.add(AuditLog(
        username=user.username,
        action="user_add",
        target=f"{clean_username} ({assigned_role})",
        result="success",
        created_at=now,
    ))
    db.commit()
    db.refresh(new_user)

    return _serialize_user(new_user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int,
    req: UserUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Menyunting akun pengguna: kredensial, peran, status, matriks wewenang granular, dan cakupan aset server."""
    # Self edit check
    if user_id == user.id:
        if user.is_viewer:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Viewers cannot edit account credentials directly."
            )
        target = user
    else:
        can_manage_users = user.is_master_admin or user.has_perm("can_manage_users")
        can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
        if not can_manage_viewers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You do not have permission to manage users."
            )

        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise HTTPException(status_code=404, detail="User not found.")

        # Zero-Knowledge Stealth: Non-Master-Admins cannot touch Master Admin (Must be 404!)
        if target.is_master_admin and not user.is_master_admin:
            raise HTTPException(status_code=404, detail="User not found.")

        # Operator terbatas hanya berwenang mengelola viewer (Must be 404!)
        if not can_manage_users and target.role != "viewer":
            raise HTTPException(status_code=404, detail="User not found.")

    # 1. Update Username
    if req.username and req.username.strip():
        clean_user = req.username.strip()
        if not re.match(r"^[a-zA-Z0-9_\-\.]{3,50}$", clean_user):
            raise HTTPException(
                status_code=400,
                detail="Username must be 3-50 alphanumeric characters (letters, numbers, _, -, .)."
            )
        if clean_user != target.username:
            if user_id == user.id:
                cur_pwd = (req.current_password or "").strip()
                if not cur_pwd or not verify_password(cur_pwd, target.password_hash):
                    raise HTTPException(
                        status_code=400,
                        detail="Current password is incorrect."
                    )
            dup = db.query(User).filter(User.username == clean_user, User.id != target.id).first()
            if dup:
                raise HTTPException(
                    status_code=400,
                    detail=f"Username '{clean_user}' is already taken."
                )
            target.username = clean_user

    # 2. Update Password (Self or Admin Override)
    if req.password and req.password.strip():
        pwd_clean = req.password.strip()
        if user_id == user.id:
            cur_pwd = (req.current_password or "").strip()
            if not cur_pwd or not verify_password(cur_pwd, target.password_hash):
                raise HTTPException(
                    status_code=400,
                    detail="Current password is incorrect."
                )
        if req.confirm_password and pwd_clean != req.confirm_password.strip():
            raise HTTPException(
                status_code=400,
                detail="New password and confirmation do not match."
            )
        _enforce_password_strength(pwd_clean)
        target.password_hash = get_password_hash(pwd_clean)
        target.password_changed_at = datetime.utcnow()

    # 3. Update Role, Status, Permissions, Scope (Only when editing OTHER users)
    if user_id != user.id:
        if target.is_master_admin:
            if req.role and req.role not in ("master_admin", "master-admin"):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot change role of master-admin account."
                )
        else:
            if req.role is not None:
                if req.role in ("master_admin", "master-admin"):
                    raise HTTPException(status_code=400, detail="Cannot promote user to master-admin.")
                if not (user.is_master_admin or user.has_perm("can_manage_users")):
                    req.role = "viewer"
                target.role = req.role

        if req.is_active is not None:
            if target.is_master_admin and req.is_active == 0:
                raise HTTPException(
                    status_code=400,
                    detail="The master-admin account cannot be deactivated."
                )
            target.is_active = req.is_active

        # Permissions: HANYA Master Admin yang berhak mengedit wewenang operator lain!
        if req.permissions is not None:
            if not user.is_master_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only master-admin can edit operator permissions."
                )
            if target.role in ("operator", "operator_utama", "operator_pembantu"):
                target.permissions = json.dumps(req.permissions)

        # Allowed server ids
        if req.allowed_server_ids is not None:
            if target.role in ("operator", "operator_utama", "operator_pembantu"):
                creator_scope = user.get_allowed_server_ids()
                if creator_scope is not None:
                    requested = sorted(req.allowed_server_ids or [])
                    if not requested or not set(requested).issubset(set(creator_scope)):
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Scoped operators can only assign assets within their own scope.",
                        )
                    target.allowed_server_ids = json.dumps(requested)
                else:
                    target.allowed_server_ids = json.dumps(sorted(req.allowed_server_ids)) if req.allowed_server_ids else None
            else:
                target.allowed_server_ids = None

        if target.role == "viewer":
            target.permissions = None
            target.allowed_server_ids = None

    # Record Audit Log
    db.add(AuditLog(
        username=user.username,
        action="user_update",
        target=f"{target.username} ({target.role})",
        result="success",
        meta=json.dumps({"target_id": target.id}),
        created_at=datetime.utcnow(),
    ))

    db.commit()
    db.refresh(target)

    return _serialize_user(target)


@router.put("/{user_id}/status")
def toggle_user_status(
    user_id: int,
    req: UserStatusUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Enable or disable a user account."""
    target = _get_authorized_target_user(db, user, user_id)

    if target.id == user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot change the active status of your own account."
        )

    if target.is_master_admin:
        raise HTTPException(
            status_code=400,
            detail="The master-admin account cannot be disabled."
        )

    target.is_active = req.is_active
    status_label = "activated" if req.is_active else "disabled"
    db.add(AuditLog(
        username=user.username,
        action="user_update",
        target=target.username,
        result="success",
        meta=f"Account {status_label}",
        created_at=datetime.utcnow(),
    ))
    db.commit()

    return {"ok": True, "message": f"User '{target.username}' has been {status_label}."}


@router.put("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    req: AdminResetPasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset another user's password by administrator."""
    target = _get_authorized_target_user(db, user, user_id)
    _enforce_password_strength(req.new_password)

    now = datetime.utcnow()
    target.password_hash = get_password_hash(req.new_password)
    target.password_changed_at = now
    db.add(AuditLog(
        username=user.username,
        action="user_password_reset",
        target=target.username,
        result="success",
        created_at=now,
    ))
    db.commit()

    return {"ok": True, "message": f"Password for user '{target.username}' has been reset successfully."}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a user account."""
    target = _get_authorized_target_user(db, user, user_id)

    if target.id == user.id:
        raise HTTPException(
            status_code=400,
            detail="You cannot delete your own account."
        )

    if target.is_master_admin:
        raise HTTPException(
            status_code=400,
            detail="The master-admin account cannot be deleted."
        )

    username_deleted = target.username
    db.delete(target)
    db.add(AuditLog(
        username=user.username,
        action="user_delete",
        target=username_deleted,
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()

    return {"ok": True, "message": f"User '{username_deleted}' has been deleted."}


# ---------------------------------------------------------------------------
# Two-Factor Authentication (2FA / TOTP RFC 6238) Endpoints
# ---------------------------------------------------------------------------
@router.post("/2fa/init")
def api_user_2fa_init(user: User = Depends(get_current_user)):
    """Inisialisasi setup 2FA TOTP (Google Authenticator / Aegis / dsb)."""
    if user.is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot configure 2FA. Managed by administrator."
        )

    raw_secret = security_auth.generate_totp_secret()
    formatted_secret = security_auth.format_secret_display(raw_secret)
    totp_uri = security_auth.generate_totp_uri(raw_secret, user.username)
    qr_data_url = security_auth.generate_qr_data_url(totp_uri)
    return {
        "ok": True,
        "raw_secret": raw_secret,
        "formatted_secret": formatted_secret,
        "totp_uri": totp_uri,
        "qr_data_url": qr_data_url,
    }


@router.post("/2fa/confirm")
def api_user_2fa_confirm(
    req: TotpConfirmRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Konfirmasi kode 6 digit untuk mengaktifkan 2FA."""
    if user.is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot configure 2FA. Managed by administrator."
        )

    if not security_auth.verify_totp(req.secret, req.code):
        raise HTTPException(status_code=400, detail="Invalid or expired 2FA authentication code.")

    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    user.totp_secret = req.secret
    user.totp_enabled = 1
    user.recovery_codes = json.dumps(hashed_codes)
    db.commit()
    return {
        "ok": True,
        "message": "Two-factor authentication (2FA) enabled successfully.",
        "recovery_codes": plain_codes,
    }


@router.post("/2fa/disable")
def api_user_2fa_disable(
    req: TotpDisableRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Disable 2FA for current user."""
    if user.is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot configure 2FA. Managed by administrator."
        )

    if not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect account password.")

    user.totp_secret = None
    user.totp_enabled = 0
    user.recovery_codes = None
    db.commit()
    return {"ok": True, "message": "2FA has been disabled successfully."}


@router.post("/2fa/regenerate-recovery")
def api_user_2fa_regenerate_recovery(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Regenerate 2FA recovery codes."""
    if user.is_viewer:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Viewers cannot configure 2FA. Managed by administrator."
        )

    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="2FA is not active for this account.")
    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    user.recovery_codes = json.dumps(hashed_codes)
    db.commit()
    return {"ok": True, "recovery_codes": plain_codes}


@router.post("/{user_id}/reset-2fa")
def api_admin_reset_user_2fa(
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Emergency 2FA reset for an operator by Master Admin."""
    if not user.is_master_admin:
        raise HTTPException(status_code=403, detail="Only master-admin can reset user 2FA.")
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")
    target.totp_secret = None
    target.totp_enabled = 0
    target.recovery_codes = None
    db.add(AuditLog(
        username=user.username,
        action="user_2fa_reset",
        target=target.username,
        result="success",
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"ok": True, "message": f"2FA for user '{target.username}' has been disabled."}
