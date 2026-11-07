"""
Modul Utilitas & Fungsi Bersama Antarmuka NiceGUI (Pantau Server NOC)
=====================================================================
Menyediakan pemformat data, deteksi zona waktu sistem, helper notifikasi,
dan injeksi gaya CSS standar kepadatan tinggi (High Density NOC).
"""

from contextlib import contextmanager
from datetime import datetime
import time
from typing import Generator
from nicegui import ui
from sqlalchemy.orm import Session

from config import settings


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
    """Terapkan CSS global kanonikal Pantau Server (pantau-theme.css) dengan cache-busting dinamis."""
    v_str = getattr(settings, "APP_VERSION", "latest")
    ui.add_head_html(f'<link rel="stylesheet" href="/static/pantau-theme.css?v={v_str}">')
    ui.add_head_html("""
    <script>
    function toggleSb() {
        document.body.classList.toggle('sb-collapsed');
        try {
            localStorage.setItem('sb', document.body.classList.contains('sb-collapsed') ? '1' : '0');
        } catch(e) {}
    }
    (function() {
        try {
            if (localStorage.getItem('sb') === '1') {
                document.body.classList.add('sb-collapsed');
            }
        } catch(e) {}
    })();
    </script>
    <style>
        /* Injeksi Fallback Kritis: Menjamin Layout Dashboard & Severity Strip Selalu Horizontal */
        .dash-kpi-grid {
            display: grid !important;
            grid-template-columns: minmax(190px, 220px) 1fr minmax(260px, 290px) !important;
            gap: 8px !important;
            width: 100% !important;
            margin-bottom: 8px !important;
            align-items: stretch !important;
        }
        @media (max-width: 900px) {
            .dash-kpi-grid {
                grid-template-columns: 1fr !important;
            }
        }
        .zbx-severity-strip {
            display: flex !important;
            flex-direction: row !important;
            gap: 4px !important;
            width: 100% !important;
            align-items: stretch !important;
        }
        .zbx-sev-tile {
            flex: 1 !important;
            min-width: 42px !important;
            display: flex !important;
            flex-direction: column !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 4px 2px !important;
            border-radius: 6px !important;
            border: 1px solid rgba(255, 255, 255, 0.1) !important;
            background: rgba(255, 255, 255, 0.03) !important;
            text-align: center !important;
            cursor: pointer !important;
        }
        .meter-mini-track {
            width: 50px !important;
            height: 5px !important;
            background: rgba(255, 255, 255, 0.08) !important;
            border-radius: 3px !important;
            overflow: hidden !important;
            display: inline-block !important;
            vertical-align: middle !important;
        }
        .meter-mini-bar {
            height: 100% !important;
            border-radius: 3px !important;
            transition: width 0.3s ease !important;
        }
        .meter-mini-bar.green { background: #22c55e !important; }
        .meter-mini-bar.yellow { background: #eab308 !important; }
        .meter-mini-bar.red { background: #ef4444 !important; }

        /* Penyesuaian Quasar & NiceGUI dengan Pantau Theme */
        html, body {
            overflow-x: hidden !important;
            max-width: 100vw !important;
        }
        .q-layout {
            background: transparent !important;
            min-height: 100vh;
            max-width: 100vw !important;
            overflow-x: hidden !important;
        }
        .q-page-container {
            background: transparent !important;
            min-height: 100vh;
            box-sizing: border-box;
            max-width: 100vw !important;
        }
        .q-drawer {
            background: var(--sidebar, #0e1526) !important;
        }
        .nicegui-content {
            padding: 0 !important;
            margin: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            min-height: 100%;
            display: block !important;
        }
        body {
            background: var(--bg, #111827) !important;
            color: var(--text, #f8fafc) !important;
            margin: 0 !important;
            padding: 0 !important;
            min-height: 100vh;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, monospace;
        }
        .main {
            margin-left: 0 !important;
            padding: 0 !important;
            width: 100% !important;
            max-width: 100% !important;
        }
        /* Custom card bridge */
        .custom-card {
            background: var(--card-bg, #1a2336);
            border: 1px solid var(--border);
            border-radius: var(--radius-md, 11px);
        }
        /* NiceGUI dialog fix */
        .q-dialog__inner > div {
            background: var(--card, #1a2336) !important;
            border: 1px solid var(--border) !important;
            border-radius: var(--radius-md, 11px) !important;
            color: var(--text, #f8fafc) !important;
        }
        /* ECharts container transparency */
        .echarts {
            background: transparent !important;
        }
        /* Quasar Table High Density NOC Bridge */
        .q-table__container {
            background: var(--card, #1a2336) !important;
            border: 1px solid var(--border) !important;
            border-radius: 6px !important;
            box-shadow: none !important;
        }
        .q-table thead tr {
            background: rgba(255, 255, 255, 0.02) !important;
            border-bottom: 1px solid var(--border) !important;
        }
        .q-table thead th {
            font-size: 10px !important;
            font-weight: 600 !important;
            color: var(--dim, #94a3b8) !important;
            text-transform: uppercase !important;
            letter-spacing: 0.5px !important;
            padding: 6px 10px !important;
            text-align: left !important;
            white-space: nowrap !important;
        }
        .q-table tbody td {
            font-size: 11.5px !important;
            padding: 5px 10px !important;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04) !important;
            color: var(--text, #e2e8f0) !important;
            text-align: left !important;
            line-height: 1.35 !important;
        }
        .q-table tbody tr:hover {
            background-color: rgba(255, 255, 255, 0.035) !important;
        }
        .q-table__bottom {
            font-size: 11px !important;
            color: var(--dim, #94a3b8) !important;
            border-top: 1px solid var(--border) !important;
            padding: 4px 12px !important;
            background: rgba(0, 0, 0, 0.15) !important;
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
