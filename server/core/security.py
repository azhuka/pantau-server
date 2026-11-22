import jwt
import bcrypt
import threading
from datetime import datetime, timedelta
from typing import Optional, Callable
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from config import settings
from core.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not plain_password or not hashed_password:
        return False
    try:
        # bcrypt.checkpw requires bytes
        plain_bytes = plain_password.encode("utf-8")
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(plain_bytes, hash_bytes)
    except Exception as e:
        return False

def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")
    return encoded_jwt

def decode_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sesi Unlock Web Terminal (Ephemeral Lease) - Zero Unattended Hijack
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
# Sesi Unlock Remote File Manager (Ephemeral Lease) - Zero Unattended Hijack
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

