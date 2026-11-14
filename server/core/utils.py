"""String, datetime, sanitization, and hashing utility functions."""

import hashlib
import ipaddress
import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote
from fastapi import Request

try:
    from config import settings
except ImportError:
    from server.config import settings

# ---------------------------------------------------------------------------
# Konstanta Waktu & Format Bahasa Indonesia
# ---------------------------------------------------------------------------
MONTHS_ID = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")

KEY_PREFIX = "sha256:"

# Regex pembersih kontrol karakter & escape sequences
_CLEAN_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f]")
_TERM_SGR_RE = re.compile(r"\x1b\[[0-9;]*m")
_TERM_KEEP_RE = re.compile(r"\x1b\[(?:[0-9;]*m|2J|3J|H|1;1H|[0-2]?K|[0-9]*P|[0-9]*[A-D])")
_TERM_STASH_RE = re.compile(r"\ue000(\d+)\ue001")
_ANSI_ANY_RE = re.compile(r"\x1b(?:\[[0-9;?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\)|.)")


def _clean_str(value, default="", length: int = 100) -> str:
    """Normalisasi string: wajib str, whitespace dirapikan, potong panjang."""
    if value is None:
        return default
    if not isinstance(value, str):
        value = str(value)
    value = " ".join(value.split())
    if len(value) > length:
        value = value[:length]
    return value


def _parse_iso_dt(value, default=None) -> Optional[datetime]:
    """Parse ISO-8601 (opsional akhiran Z/offset) ke datetime naive UTC; fallback default."""
    if isinstance(value, datetime):
        return value
    if not isinstance(value, str) or not value:
        return default
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return default


def _parse_iso_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    """Parse string ISO datetime dari input form / API payload."""
    if not dt_str:
        return None
    try:
        s = dt_str.replace("Z", "").split("+")[0].strip()
        if "T" in s:
            parts = s.split("T")
            d_part = parts[0]
            t_part = parts[1]
            if len(t_part) == 5:
                t_part += ":00"
            return datetime.fromisoformat(f"{d_part}T{t_part}")
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except Exception:
        try:
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None


def _clean_result(value, maxchars: int = 40000, maxlines: int = 2000) -> str:
    """Sanitasi hasil log: PERTAHANKAN pemisah baris (LF), buang kontrol lain."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = _CLEAN_CTRL_RE.sub(" ", value)
    clean_lines = value.splitlines()
    if len(clean_lines) > maxlines:
        clean_lines = clean_lines[-maxlines:]
    clean = "\n".join(clean_lines)
    return clean[-maxchars:]


def _clean_terminal(value, maxchars: int = 200000, maxlines: int = 4000) -> str:
    """Sanitasi stream terminal (apt & shell) TANPA merusak tampilan warna dan kursor."""
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    def _keep_only(m: re.Match) -> str:
        return m.group(0) if _TERM_KEEP_RE.fullmatch(m.group(0)) else ""

    value = _ANSI_ANY_RE.sub(_keep_only, value)
    kept: list[str] = []

    def _stash(m: re.Match) -> str:
        kept.append(m.group(0))
        return f"\ue000{len(kept) - 1}\ue001"

    value = _TERM_KEEP_RE.sub(_stash, value)
    value = "".join(c for c in value if c >= " " or c in "\n\r\b\t\x0c\ue000\ue001")
    value = _TERM_STASH_RE.sub(lambda m: kept[int(m.group(1))] if int(m.group(1)) < len(kept) else "", value)
    lines = value.split("\n")
    if len(lines) > maxlines:
        lines = lines[-maxlines:]
    return "\n".join(lines)[-maxchars:]


def _clamp_int(value, default=None, lo: int = 0, hi: int = 2**31 - 1):
    """Koersi ke int dalam rentang aman; fallback default bila tak valid."""
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _clamp_float(value, default=None, lo: float = 0.0, hi: float = 2**31 - 1):
    """Koersi ke float dalam rentang aman; fallback default bila tak valid."""
    if value is None:
        return default
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return max(lo, min(hi, v))


def _validate_ip(value: str) -> bool:
    """Cek apakah string adalah IPv4 atau IPv6 yang valid."""
    try:
        ipaddress.ip_address(value.strip())
        return True
    except (ValueError, AttributeError):
        return False


def _is_agent_outdated(agent_ver: str | None, current_ver: str) -> bool:
    """Cek apakah versi agen lebih lama dari versi dashboard saat ini."""
    if not agent_ver:
        return False
    try:
        a_parts = [int(x) for x in re.findall(r"\d+", str(agent_ver))]
        c_parts = [int(x) for x in re.findall(r"\d+", str(current_ver))]
        max_len = max(len(a_parts), len(c_parts), 3)
        v_agent = tuple(a_parts + [0] * (max_len - len(a_parts)))
        v_curr = tuple(c_parts + [0] * (max_len - len(c_parts)))
        return v_agent < v_curr
    except Exception:
        return False


def hash_api_key(raw: str) -> str:
    """Hash raw API key menggunakan SHA-256 ber-prefix."""
    return KEY_PREFIX + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def api_key_fingerprint(api_key: str) -> str:
    """Tampilkan fingerprint aman dari API key."""
    h = api_key
    if h.startswith(KEY_PREFIX):
        h = h[len(KEY_PREFIX):]
    return h[:8] + "…" + h[-8:] if len(h) > 16 else h


def get_server_timezone_meta() -> dict:
    """Deteksi zona waktu lokal server pantau-server, singkatan nama, dan offset menit."""
    try:
        now_local = datetime.now().astimezone()
        tz_name = now_local.tzname() or "WITA"
        offset_sec = int(now_local.utcoffset().total_seconds()) if now_local.utcoffset() else 28800
        offset_min = offset_sec // 60
        return {
            "tz": tz_name,
            "offset_min": offset_min,
            "offset_sec": offset_sec,
        }
    except Exception:
        return {
            "tz": "WITA",
            "offset_min": 480,
            "offset_sec": 28800,
        }


def _fmt_dt(dt: datetime | None, with_sec: bool = True) -> str:
    """Format tanggal dan waktu rinci dalam waktu lokal server & bahasa Indonesia: DD Mon YYYY HH:MM:SS."""
    if not dt or not isinstance(dt, datetime):
        return "—"
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc).astimezone()
        else:
            dt = dt.astimezone()
    except Exception:
        pass
    mon = MONTHS_ID[dt.month - 1]
    if with_sec:
        return f"{dt.day:02d} {mon} {dt.year} {dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}"
    return f"{dt.day:02d} {mon} {dt.year} {dt.hour:02d}:{dt.minute:02d}"


def _fmt_short_dt(dt: datetime | None) -> str:
    """Format tanggal dan waktu ringkas dalam waktu lokal server: DD Mon HH:MM."""
    if not dt or not isinstance(dt, datetime):
        return "—"
    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc).astimezone()
        else:
            dt = dt.astimezone()
    except Exception:
        pass
    mon = MONTHS_ID[dt.month - 1]
    return f"{dt.day:02d} {mon} {dt.hour:02d}:{dt.minute:02d}"


def _rel_dt(dt: Optional[datetime], now: Optional[datetime] = None) -> str:
    """Waktu relatif (bebas zona waktu) untuk menampilkan aktivitas terakhir."""
    if not dt or not isinstance(dt, datetime):
        return "—"
    now = now or datetime.utcnow()
    s = int((now - dt).total_seconds())
    if s < 10:
        return "baru saja"
    if s < 60:
        return f"{s} dtk lalu"
    if s < 3600:
        return f"{s // 60} mnt lalu"
    if s < 86400:
        h, m = divmod(s // 60, 60)
        return f"{h} j {m} mnt lalu"
    return f"{s // 86400} h lalu"



def _flash_qs(ok: bool, text: str) -> str:
    """Query string notifikasi utk redirect (?msg=… / ?err=…), URL-encoded."""
    return f"?{('msg' if ok else 'err')}={quote(text)}"


def _flash_profile_users(ok: bool, text: str) -> str:
    return f"/profile{_flash_qs(ok, text)}&tab=users"


def _flash_profile_branding(ok: bool, text: str) -> str:
    return f"/profile{_flash_qs(ok, text)}&tab=branding"


def _is_trusted_proxy(ip_str: str) -> bool:
    """Periksa apakah IP sumber merupakan proxy terpercaya (IP tunggal, CIDR, atau wildcard *)."""
    if not ip_str or ip_str == "unknown":
        return False
    trusted_set = settings.trusted_proxy_set
    if "*" in trusted_set or ip_str in trusted_set:
        return True
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        for t in trusted_set:
            try:
                if "/" in t and ip_obj in ipaddress.ip_network(t, strict=False):
                    return True
            except ValueError:
                pass
    except ValueError:
        pass
    return False


def _clean_ua(ua: str | None) -> str:
    """Ringkas User-Agent browser menjadi identitas perangkat/OS ringkas untuk sysadmin."""
    if not ua:
        return ""
    ua_lower = ua.lower()
    os_name = (
        "Windows" if "windows" in ua_lower
        else "macOS" if ("macintosh" in ua_lower or "mac os" in ua_lower)
        else "Android" if "android" in ua_lower
        else "iOS" if ("iphone" in ua_lower or "ipad" in ua_lower)
        else "Linux" if "linux" in ua_lower
        else "OS"
    )
    browser_name = (
        "Edge" if "edg/" in ua_lower
        else "Opera" if ("opr/" in ua_lower or "opera" in ua_lower)
        else "Chrome" if ("chrome/" in ua_lower and "chromium" not in ua_lower)
        else "Firefox" if "firefox/" in ua_lower
        else "Safari" if ("safari/" in ua_lower and "chrome" not in ua_lower)
        else "Browser"
    )
    return f"{browser_name} · {os_name}"


def _client_ip(request: Request) -> str:
    """Dapatkan IP asli klien dari request proxy terpercaya."""
    real_ip = request.client.host if request.client else "unknown"
    if _is_trusted_proxy(real_ip):
        for hdr in ("CF-Connecting-IP", "True-Client-IP"):
            val = request.headers.get(hdr)
            if val:
                return val.strip()[:45]
        xff = request.headers.get("X-Forwarded-For")
        if xff:
            candidate = xff.split(",")[0].strip()[:45]
            if candidate:
                return candidate
        x_real = request.headers.get("X-Real-IP")
        if x_real:
            return x_real.strip()[:45]
    return real_ip

