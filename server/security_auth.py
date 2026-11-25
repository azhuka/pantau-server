"""Modul Keamanan & Autentikasi Pantau Server (Security Hardening, RBAC, 2FA/TOTP).
Diadopsi dari blueprint matang aplikasi induk ~/rj45.
"""

import base64
import hashlib
import hmac
import io
import json
import re
import secrets
import struct
import time
from typing import Optional, Tuple, List, Dict

try:
    import qrcode
    try:
        import qrcode.image.svg
    except Exception:
        pass
except ImportError:
    qrcode = None

# Daftar kata sandi populer yang dilarang
COMMON_PASSWORDS_BLACKLIST = {
    "password", "password123", "password1234", "admin123", "admin1234",
    "pantauserver", "pantau123", "pantau2026", "qwertyuiop", "1234567890",
    "administrator", "masteradmin", "root1234", "secret123", "rahasia123",
    "server123", "linux123", "indonesia123"
}

# Granular 16 Operator Permissions (RBAC Matrix)
OPERATOR_PERMISSIONS: Dict[str, Dict[str, str]] = {
    "can_terminal": {
        "label": "Web Shell Terminal",
        "desc": "Interactive PTY (/bin/bash) shell access to client servers.",
    },
    "can_file_manager": {
        "label": "Web File Manager",
        "desc": "Browse, edit text files, download, and upload files on client servers.",
    },
    "can_services": {
        "label": "Systemd Service Control",
        "desc": "Start, stop, restart, and reload systemd service units.",
    },
    "can_processes": {
        "label": "Process Manager",
        "desc": "Terminate (kill), suspend (SIGSTOP), or resume (SIGCONT) OS processes.",
    },
    "can_firewall": {
        "label": "Firewall Control (UFW)",
        "desc": "Enable or disable UFW and manage IP blocklist rules.",
    },
    "can_users_sys": {
        "label": "Host System User Management",
        "desc": "Create, lock, unlock, or delete Linux system accounts.",
    },
    "can_cron": {
        "label": "Cron Jobs (Scheduled Tasks)",
        "desc": "Add, enable/disable, run on-demand, or delete cron tasks.",
    },
    "can_ssl": {
        "label": "SSL/TLS Certificate Monitoring",
        "desc": "Add or remove local SSL/TLS certificate path monitoring.",
    },
    "can_server_control": {
        "label": "Host Power Control (Reboot / Shutdown)",
        "desc": "Reboot or power off target server hosts.",
    },
    "can_apt": {
        "label": "OS Package Management (APT)",
        "desc": "Run package index updates (apt-get update) and package upgrades (apt upgrade).",
    },
    "can_ota": {
        "label": "Agent OTA Update",
        "desc": "Dispatch verified SHA-256 agent binary updates to client hosts.",
    },
    "can_manage_servers": {
        "label": "Asset Management",
        "desc": "Register assets, edit hostname/IP/group/environment, and toggle maintenance mode.",
    },
    "can_audit": {
        "label": "Audit Trail Access",
        "desc": "View operator action audit logs, compliance records, and system logs.",
    },
    "can_manage_users": {
        "label": "User & RBAC Administration",
        "desc": "Manage Operator and Viewer accounts, permissions, and password resets.",
    },
    "can_manage_viewers": {
        "label": "Viewer Account Management",
        "desc": "Create and delete read-only Viewer accounts.",
    },
    "can_probing": {
        "label": "Endpoint & Network Probing",
        "desc": "Create, update, pause, and trigger HTTP/ICMP/TCP endpoint probes.",
    },
}


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Validate password strength per NIST SP 800-63B policy."""
    if not password:
        return False, "Password cannot be empty."
    if len(password) < 12:
        return False, "Password must be at least 12 characters long."
    if len(password) > 128:
        return False, "Password must be at most 128 characters long."
    if not re.search(r"[A-Z]", password):
        return False, "Password must include at least one uppercase letter (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password must include at least one lowercase letter (a-z)."
    if not re.search(r"[0-9]", password):
        return False, "Password must include at least one digit (0-9)."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]", password):
        return False, "Password must include at least one special character (!@#$%^&*...)."

    low = password.lower()
    for bad in COMMON_PASSWORDS_BLACKLIST:
        if bad in low:
            return False, f"Password is too predictable (contains common term '{bad}')."

    return True, ""


# ---------------------------------------------------------------------------
# RFC 6238 / RFC 4226 TOTP (Two-Factor Authentication)
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Hasilkan secret key 160-bit Base32 untuk TOTP."""
    raw = secrets.token_bytes(20)
    return base64.b32encode(raw).decode("ascii").replace("=", "")


def format_secret_display(secret: str) -> str:
    """Format string Base32 dengan spasi per 4 karakter agar mudah dibaca manusia."""
    s = secret.upper().replace(" ", "")
    return " ".join(s[i:i+4] for i in range(0, len(s), 4))


def generate_totp_uri(secret: str, username: str, issuer: str = "Pantau Server") -> str:
    """Hasilkan URI otpauth:// standard untuk Google Authenticator / Aegis / Authy."""
    clean_user = username.replace(":", "_").replace("@", "_")
    clean_issuer = issuer.replace(":", "_")
    return f"otpauth://totp/{clean_issuer}:{clean_user}?secret={secret}&issuer={clean_issuer}&algorithm=SHA1&digits=6&period=30"


def generate_qr_data_url(uri: str) -> str:
    """Hasilkan Data URL Base64 PNG atau SVG dari QR Code."""
    if qrcode is None:
        return ""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    try:
        img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        try:
            if hasattr(qrcode, "image") and hasattr(qrcode.image, "svg"):
                img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
                buf = io.BytesIO()
                img.save(buf)
                b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                return f"data:image/svg+xml;base64,{b64}"
        except Exception:
            pass
        return ""


def compute_totp(secret: str, interval: int = 30, for_time: Optional[int] = None) -> str:
    """Hitung kode 6-digit TOTP (RFC 6238) saat ini untuk secret key yang diberikan."""
    clean_sec = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(clean_sec) % 8) % 8)
    key = base64.b32decode(clean_sec + padding)
    t = int(for_time if for_time is not None else time.time()) // interval
    msg = struct.pack(">Q", t)
    h = hmac.new(key, msg, hashlib.sha1).digest()
    offset = h[-1] & 0x0F
    truncated = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(truncated % 1000000).zfill(6)


def verify_totp(secret: str, code: str, window: int = 1, interval: int = 30) -> bool:
    """Verifikasi kode 6-digit TOTP terhadap secret key dengan toleransi window pergeseran waktu."""
    if not secret or not code:
        return False
    code = code.strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False

    clean_sec = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(clean_sec) % 8) % 8)
    try:
        key = base64.b32decode(clean_sec + padding)
    except Exception:
        return False

    current_counter = int(time.time()) // interval
    for c in range(current_counter - window, current_counter + window + 1):
        msg = struct.pack(">Q", c)
        h = hmac.new(key, msg, hashlib.sha1).digest()
        offset = h[-1] & 0x0F
        truncated = struct.unpack(">I", h[offset:offset + 4])[0] & 0x7FFFFFFF
        expected = str(truncated % 1000000).zfill(6)
        if hmac.compare_digest(expected, code):
            return True
    return False


def generate_recovery_codes(count: int = 8) -> Tuple[List[str], List[str]]:
    """Hasilkan kode cadangan darurat (recovery codes) sekali pakai.
    
    Mengembalikan (plain_codes, hashed_codes).
    """
    plain_codes: List[str] = []
    hashed_codes: List[str] = []
    for _ in range(count):
        part1 = secrets.token_hex(2).upper()
        part2 = secrets.token_hex(2).upper()
        code = f"{part1}-{part2}"
        plain_codes.append(code)
        hashed_codes.append(hashlib.sha256(code.encode("ascii")).hexdigest())
    return plain_codes, hashed_codes


def verify_and_consume_recovery_code(submitted_code: str, stored_hashes_json: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Verifikasi kode cadangan darurat dan hapus (consume) kode jika cocok."""
    if not submitted_code or not stored_hashes_json:
        return False, stored_hashes_json
    clean_code = submitted_code.strip().replace(" ", "").upper()
    sub_hash = hashlib.sha256(clean_code.encode("ascii")).hexdigest()
    try:
        hashes: List[str] = json.loads(stored_hashes_json)
    except Exception:
        return False, stored_hashes_json

    if sub_hash in hashes:
        hashes.remove(sub_hash)
        return True, json.dumps(hashes)
    return False, stored_hashes_json


def create_preauth_token(user_id: int, secret_key: str, ttl_seconds: int = 300) -> str:
    """Buat token pre-autentikasi bertanda tangan HMAC untuk transisi login 2FA."""
    exp = int(time.time()) + ttl_seconds
    payload = f"{user_id}:{exp}"
    sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_preauth_token(token: str, secret_key: str) -> Optional[int]:
    """Verifikasi token pre-autentikasi 2FA. Mengembalikan user_id jika sah dan belum kedaluwarsa."""
    if not token or ":" not in token:
        return None
    parts = token.split(":")
    if len(parts) != 3:
        return None
    user_id_str, exp_str, sig = parts
    payload = f"{user_id_str}:{exp_str}"
    expected_sig = hmac.new(secret_key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return None
    try:
        exp = int(exp_str)
        if time.time() > exp:
            return None
        return int(user_id_str)
    except Exception:
        return None
