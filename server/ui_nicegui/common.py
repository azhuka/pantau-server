"""
Modul Utilitas & Fungsi Bersama Antarmuka NiceGUI (Pantau Server NOC)
=====================================================================
Menyediakan pemformat data, deteksi zona waktu sistem, helper notifikasi,
dan injeksi gaya CSS standar kepadatan tinggi (High Density NOC).
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import time
from typing import Any, Generator, Optional
from nicegui import ui
from sqlalchemy.orm import Session


def get_system_tz_label() -> str:
    """Mengambil nama zona waktu sistem operasi host secara dinamis (WITA, WIB, WIT, UTC, dll.)."""
    try:
        if time.daylight and len(time.tzname) > 1 and time.tzname[1]:
            return time.tzname[time.daylight]
        return time.tzname[0] or "LOKAL"
    except Exception:
        return "WITA"


def get_now_local() -> datetime:
    """Mengambil waktu saat ini pada mesin host server sesuai zona waktu lokal."""
    return datetime.now()


def format_bytes(num_bytes: int | float | None) -> str:
    """Format angka bita menjadi satuan biner manusiawi (B, KB, MB, GB, TB)."""
    if num_bytes is None:
        return "—"
    try:
        val = float(num_bytes)
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if abs(val) < 1024.0:
                return f"{val:.1f} {unit}"
            val /= 1024.0
        return f"{val:.1f} PB"
    except Exception:
        return "—"


def format_duration(dt: datetime | None, now: datetime | None = None) -> str:
    """Format selisih waktu menjadi teks durasi ringkas (dtk, mnt, jam, hari)."""
    if not dt:
        return "—"
    now = now or datetime.utcnow()
    diff = int((now - dt).total_seconds())
    if diff < 0:
        return "0 dtk"
    if diff < 60:
        return f"{diff} dtk"
    if diff < 3600:
        return f"{diff // 60} mnt"
    if diff < 86400:
        return f"{diff // 3600} jam"
    return f"{diff // 86400} hari"


def format_dt(dt: datetime | None) -> str:
    """Format timestamp ISO/UTC ke tampilan tanggal waktu standar NOC."""
    if not dt:
        return "—"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def notify_success(msg: str):
    """Tampilkan notifikasi toast hijau sukses."""
    ui.notify(msg, color="positive", icon="check_circle", position="top", timeout=3000)


def notify_error(msg: str):
    """Tampilkan notifikasi toast merah kesalahan."""
    ui.notify(msg, color="negative", icon="error", position="top", timeout=5000)


def notify_warning(msg: str):
    """Tampilkan notifikasi toast oranye peringatan."""
    ui.notify(msg, color="warning", icon="warning", position="top", timeout=4000)


def notify_info(msg: str):
    """Tampilkan notifikasi toast biru informasi."""
    ui.notify(msg, color="info", icon="info", position="top", timeout=3000)


def apply_noc_head_styles():
    """Terapkan CSS global standar NOC (kepadatan tinggi, dark mode, scrollbar tipis)."""
    ui.add_head_html("""
    <style>
        body {
            background-color: #0b1120;
            color: #f1f5f9;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, monospace;
        }
        .q-table__container {
            background-color: #0f172a !important;
            border: 1px solid #1e293b !important;
            border-radius: 8px;
        }
        .q-table thead th {
            font-size: 11px !important;
            font-weight: 700 !important;
            color: #94a3b8 !important;
            text-transform: uppercase;
            background-color: #0f172a !important;
            padding: 7px 12px !important;
            letter-spacing: 0.05em;
        }
        .q-table tbody td {
            font-size: 11.5px !important;
            padding: 6px 12px !important;
            border-color: #1e293b !important;
            color: #e2e8f0;
        }
        .q-table tbody tr:hover {
            background-color: rgba(30, 41, 59, 0.75) !important;
        }
        .q-table__bottom {
            font-size: 11px !important;
            color: #94a3b8 !important;
            border-top: 1px solid #1e293b !important;
            padding: 4px 12px !important;
        }
        .custom-card {
            background-color: #0f172a;
            border: 1px solid #1e293b;
            border-radius: 8px;
        }
        .zbx-strip-tile {
            cursor: pointer;
            transition: all 0.2s;
            border-radius: 6px;
            padding: 6px 12px;
        }
        .zbx-strip-tile:hover {
            filter: brightness(1.2);
            transform: translateY(-1px);
        }
        ::-webkit-scrollbar {
            width: 6px;
            height: 6px;
        }
        ::-webkit-scrollbar-track {
            background: #0b1120;
        }
        ::-webkit-scrollbar-thumb {
            background: #1e293b;
            border-radius: 3px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #334155;
        }
    </style>
    """)


@contextmanager
def get_db(session_factory) -> Generator[Session, None, None]:
    """Context manager aman untuk siklus hidup SQLAlchemy Session."""
    db: Session = session_factory()
    try:
        yield db
    finally:
        db.close()
