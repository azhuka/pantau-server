import re
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import verify_password, get_password_hash
from routers.auth import get_current_user
from models.user import User

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


class UserStatusUpdateRequest(BaseModel):
    is_active: int = Field(..., ge=0, le=1)


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    is_active: int
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class UserProfileResponse(BaseModel):
    id: int
    username: str
    role: str
    is_master_admin: bool
    is_active: int
    created_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long."
        )
    if not re.search(r"[A-Z]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one uppercase letter (A-Z)."
        )
    if not re.search(r"[a-z]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one lowercase letter (a-z)."
        )
    if not re.search(r"[0-9]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least one number (0-9)."
        )


# ---------------------------------------------------------------------------
# Current User Self-Service Endpoints
# ---------------------------------------------------------------------------
@router.get("/me", response_model=UserProfileResponse)
def get_user_profile(user: User = Depends(get_current_user)):
    """Melihat profil akun yang sedang login."""
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_master_admin": user.is_master_admin,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "last_login_at": user.last_login_at,
    }


@router.put("/me/password")
def change_own_password(
    req: PasswordChangeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Ganti kata sandi mandiri bagi pengguna yang sedang login."""
    if not verify_password(req.current_password, user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="Current password is incorrect."
        )

    validate_password_strength(req.new_password)

    if req.current_password == req.new_password:
        raise HTTPException(
            status_code=400,
            detail="New password cannot be the same as the current password."
        )

    user.password_hash = get_password_hash(req.new_password)
    user.password_changed_at = datetime.utcnow()
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
    """Melihat seluruh daftar pengguna terdaftar."""
    if not (user.is_master_admin or user.has_perm("can_manage_users") or user.has_perm("can_manage_viewers")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have user management permissions."
        )

    users = db.query(User).order_by(User.id.asc()).all()
    return users


@router.post("", response_model=UserResponse)
def create_user(
    req: UserCreateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Membuat akun pengguna baru (Operator atau Viewer)."""
    if not (user.is_master_admin or user.has_perm("can_manage_users")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to create users."
        )

    # Validasi nama pengguna unik
    clean_username = req.username.strip()
    existing = db.query(User).filter(User.username == clean_username).first()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Username '{clean_username}' already exists."
        )

    validate_password_strength(req.password)

    new_user = User(
        username=clean_username,
        password_hash=get_password_hash(req.password),
        role=req.role,
        is_active=1,
        created_by=user.username,
        password_changed_at=datetime.utcnow(),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.put("/{user_id}/status")
def toggle_user_status(
    user_id: int,
    req: UserStatusUpdateRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mengaktifkan atau menonaktifkan akun pengguna."""
    if not (user.is_master_admin or user.has_perm("can_manage_users")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to manage user status."
        )

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

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
    db.commit()

    status_label = "activated" if req.is_active else "disabled"
    return {"ok": True, "message": f"User '{target.username}' has been {status_label}."}


@router.put("/{user_id}/reset-password")
def reset_user_password(
    user_id: int,
    req: AdminResetPasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reset kata sandi pengguna lain oleh administrator."""
    if not (user.is_master_admin or user.has_perm("can_manage_users")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to reset user passwords."
        )

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

    if target.is_master_admin and not user.is_master_admin:
        raise HTTPException(
            status_code=403,
            detail="Only master-admin can reset the master-admin password."
        )

    validate_password_strength(req.new_password)

    target.password_hash = get_password_hash(req.new_password)
    target.password_changed_at = datetime.utcnow()
    db.commit()

    return {"ok": True, "message": f"Password for user '{target.username}' has been reset successfully."}


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Menghapus akun pengguna."""
    if not (user.is_master_admin or user.has_perm("can_manage_users")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: You do not have permission to delete users."
        )

    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="User not found.")

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
    db.commit()

    return {"ok": True, "message": f"User '{username_deleted}' has been deleted."}
