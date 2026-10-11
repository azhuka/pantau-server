"""Modul Keamanan & Autentikasi Pantau Server (Security Hardening, RBAC, 2FA/TOTP)."""

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

import qrcode

# Daftar kata sandi populer yang dilarang
COMMON_PASSWORDS_BLACKLIST = {
    "password", "password123", "password1234", "admin123", "admin1234",
    "pantauserver", "pantau123", "pantau2026", "qwertyuiop", "1234567890",
    "administrator", "masteradmin", "root1234", "secret123", "rahasia123",
    "server123", "linux123", "indonesia123"
}

# Definisi Izin Granular Operator
OPERATOR_PERMISSIONS: Dict[str, Dict[str, str]] = {
    "can_terminal": {
        "label": "Terminal Shell Web",
        "desc": "Akses terminal shell PTY (/bin/bash) interaktif ke server klien.",
    },
    "can_file_manager": {
        "label": "File Manager Web",
        "desc": "Jelajahi, sunting berkas teks, unduh, dan unggah berkas pada server klien.",
    },
    "can_services": {
        "label": "Kontrol Layanan Systemd",
        "desc": "Mulai (start), hentikan (stop), restart, dan reload layanan sistem.",
    },
    "can_processes": {
        "label": "Manajer Tugas & Sinyal Proses",
        "desc": "Hentikan proses (kill), tangguhkan (SIGSTOP), atau lanjutkan proses (SIGCONT).",
    },
    "can_firewall": {
        "label": "Kontrol Firewall (UFW)",
        "desc": "Aktifkan/nonaktifkan UFW, blokir IP penyerang, dan buka blokir IP.",
    },
    "can_users_sys": {
        "label": "Manajemen User Sistem Host",
        "desc": "Buat akun Linux baru, kunci (lock), buka kunci (unlock), atau hapus akun Linux.",
    },
    "can_cron": {
        "label": "Tugas Terjadwal (Cron)",
        "desc": "Tambah jadwal cron baru, aktifkan/nonaktifkan, jalankan instan, atau hapus cron.",
    },
    "can_ssl": {
        "label": "Manajemen Sertifikat SSL",
        "desc": "Tambah atau hapus pemantauan berkas sertifikat SSL lokal.",
    },
    "can_server_control": {
        "label": "Kontrol Host (Reboot / Shutdown)",
        "desc": "Jalankan restart atau matikan mesin server target.",
    },
    "can_apt": {
        "label": "Pembaruan Paket OS (APT)",
        "desc": "Jalankan pembaruan repositori (apt-get update) dan peningkatan paket (apt upgrade).",
    },
    "can_ota": {
        "label": "Dorong Pembaruan Agen (OTA)",
        "desc": "Kirim instruksi Push Update biner agen terbaru via verifikasi SHA-256.",
    },
    "can_manage_servers": {
        "label": "Kelola Server Pantau",
        "desc": "Tambah server baru, ubah hostname/IP, dan atur mode pemeliharaan.",
    },
    "can_audit": {
        "label": "Akses Audit Trail (/audit)",
        "desc": "Lihat seluruh catatan riwayat audit kepatuhan dan log aktivitas sistem.",
    },
    "can_manage_users": {
        "label": "Manajemen Pengguna Sistem",
        "desc": "Kelola akun pengguna (Operator & Viewer), atur hak akses/izin, dan setel ulang kata sandi.",
    },
    "can_manage_viewers": {
        "label": "Kelola Akun Viewer",
        "desc": "Tambah dan hapus akun pengguna berkategori Viewer (tamu pemantau).",
    },
}


def validate_password_strength(password: str) -> Tuple[bool, str]:
    """Validasi kekuatan kata sandi standar NIST SP 800-63B."""
    if not password:
        return False, "Password tidak boleh kosong."
    if len(password) < 12:
        return False, "Password minimal 12 karakter."
    if len(password) > 128:
        return False, "Password maksimal 128 karakter."
    if not re.search(r"[A-Z]", password):
        return False, "Password harus memuat minimal 1 huruf kapital (A-Z)."
    if not re.search(r"[a-z]", password):
        return False, "Password harus memuat minimal 1 huruf kecil (a-z)."
    if not re.search(r"[0-9]", password):
        return False, "Password harus memuat minimal 1 angka (0-9)."
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]", password):
        return False, "Password harus memuat minimal 1 simbol khusus (!@#$%^&*...)."
    
    low = password.lower()
    for bad in COMMON_PASSWORDS_BLACKLIST:
        if bad in low:
            return False, f"Password terlalu mudah ditebak (mengandung kata umum '{bad}')."
            
    return True, ""


# ---------------------------------------------------------------------------
# RFC 6238 / RFC 4226 TOTP (Two-Factor Authentication)
# ---------------------------------------------------------------------------

def generate_totp_secret() -> str:
    """Hasilkan secret key 160-bit Base32 untuk TOTP."""
    # 20 bytes = 160 bits (rekomendasi RFC 4226)
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
    """Hasilkan Data URL Base64 PNG dari QR Code."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=6,
        border=2,
    )
    qr.add_data(uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0f172a", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


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
    """Verifikasi kode cadangan darurat dan hapus (consume) kode jika cocok.
    
    Mengembalikan (is_valid, updated_hashes_json).
    """
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


# ---------------------------------------------------------------------------
# Pre-Auth Signed Token (Langkah Verifikasi 2FA saat Login)
# ---------------------------------------------------------------------------

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
