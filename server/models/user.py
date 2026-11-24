from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime, TIMESTAMP, SmallInteger, func
from core.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(30), default="operator")  # master_admin, operator, viewer
    is_active = Column(SmallInteger, default=1)
    password_changed_at = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)
    totp_secret = Column(String(64), nullable=True)
    totp_enabled = Column(SmallInteger, default=0)
    recovery_codes = Column(Text, nullable=True)
    permissions = Column(Text, nullable=True)  # JSON or comma-separated permissions
    created_at = Column(TIMESTAMP, server_default=func.now())
    created_by = Column(String(100), nullable=True)
    allowed_server_ids = Column(Text, nullable=True)

    @property
    def is_master_admin(self) -> bool:
        return self.role in ("master_admin", "master-admin")

    @property
    def is_operator(self) -> bool:
        return self.role in ("operator", "operator_utama", "operator-utama", "operator_pembantu", "operator-pembantu")

    @property
    def is_viewer(self) -> bool:
        return self.role in ("viewer", "guest", "tamu")

    def get_permissions(self) -> dict:
        """Kembalikan dictionary izin aktif untuk operator."""
        if self.is_master_admin or self.role in ("operator_utama", "operator-utama"):
            # Master Admin dan Operator Utama memiliki seluruh 16 izin penuh
            from security_auth import OPERATOR_PERMISSIONS
            return {k: True for k in OPERATOR_PERMISSIONS.keys()}
        if self.is_viewer:
            return {}
        if not self.permissions:
            return {}
        try:
            import json
            parsed = json.loads(self.permissions)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    def has_perm(self, perm: str) -> bool:
        """Evaluasi apakah pengguna memiliki hak izin granular tertentu."""
        if not self.is_active:
            return False
        if self.is_master_admin or self.role in ("operator_utama", "operator-utama"):
            return True
        if self.is_viewer:
            return False
        perms = self.get_permissions()
        if perm == "can_manage_viewers" and perms.get("can_manage_users"):
            return True
        return bool(perms.get(perm, False))

    def get_allowed_server_ids(self) -> list[int] | None:
        """Mengembalikan list ID server yang diizinkan, atau None jika akses global (seluruh armada)."""
        if self.is_master_admin or self.role in ("operator_utama", "operator-utama"):
            return None
        if self.allowed_server_ids is None:
            return None
        raw = str(self.allowed_server_ids).strip()
        if not raw or raw in ("[]", "null", "None"):
            return None
        try:
            import json
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                if not parsed:
                    return None
                return [int(x) for x in parsed]
        except Exception:
            pass
        try:
            res = [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]
            return res if res else None
        except Exception:
            return None

    def can_access_server(self, server_id: int) -> bool:
        # master-admin dan operator utama memiliki akses penuh global ke seluruh armada
        if not self.is_active:
            return False
        if self.is_master_admin or self.role in ("operator_utama", "operator-utama"):
            return True
        allowed = self.get_allowed_server_ids()
        if allowed is None:
            return True
        return server_id in allowed

class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    ip_address = Column(String(45), primary_key=True)
    fails = Column(Integer, default=0, nullable=False)
    lock_until = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), onupdate=func.now())

class AppSession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    sid = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(Integer, index=True, nullable=False)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
