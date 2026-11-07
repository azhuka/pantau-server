"""
Modul Log & Kesehatan Server Pusat (Master Pantau Server Health & Logs)
======================================================================
Menyajikan pengawasan real-time terhadap performa host server pusat (Master Node),
meliputi CPU, RAM, Swap, Load Average, proses tertinggi, dan log journal sistem.
"""

from datetime import datetime
import os
import socket
import subprocess
import time
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from .auth import get_auth_user
from .common import format_bytes, get_db, notify_error, notify_info, notify_success
from .layout import render_layout

_PROC_CACHE = {"t": 0.0, "cput": 0, "cpub": 0}


def _get_master_uptime() -> float:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except OSError:
        return 0.0


def _get_master_loadavg() -> list:
    try:
        with open("/proc/loadavg") as f:
            return [float(x) for x in f.read().split()[:3]]
    except OSError:
        return [0.0, 0.0, 0.0]


def _get_master_cpu() -> float:
    now = time.time()
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
    except OSError:
        return 0.0
    if not parts or parts[0] != "cpu":
        return 0.0
    vals = [int(x) for x in parts[1:8]]
    total = sum(vals)
    busy = total - (vals[3] + vals[4])
    pct = 0.0
    prev_t = _PROC_CACHE["t"]
    if prev_t:
        dt = now - prev_t
        nt = total - _PROC_CACHE["cput"]
        if dt > 0 and nt > 0:
            pct = round((busy - _PROC_CACHE["cpub"]) / nt * 100, 1)
    _PROC_CACHE["t"] = now
    _PROC_CACHE["cput"] = total
    _PROC_CACHE["cpub"] = busy
    return pct


def _get_master_mem() -> dict:
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2:
                    info[p[0].rstrip(":")] = int(p[1])
    except OSError:
        return {"total": 0, "used": 0, "pct": 0, "swap_total": 0, "swap_used": 0, "swap_pct": 0}
    tot = info.get("MemTotal", 0) * 1024
    avail = info.get("MemAvailable", info.get("MemFree", 0)) * 1024
    used = max(0, tot - avail)
    pct = round(used / tot * 100, 1) if tot > 0 else 0.0

    stot = info.get("SwapTotal", 0) * 1024
    sfree = info.get("SwapFree", 0) * 1024
    sused = max(0, stot - sfree)
    spct = round(sused / stot * 100, 1) if stot > 0 else 0.0

    return {
        "total": tot,
        "used": used,
        "pct": pct,
        "swap_total": stot,
        "swap_used": sused,
        "swap_pct": spct,
    }


def _get_master_top_processes(n: int = 10) -> list:
    rows = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return rows
    pagesize = os.sysconf("SC_PAGE_SIZE") or 4096

    for pid in pids[:150]:
        try:
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()[:24]
            with open(f"/proc/{pid}/statm") as f:
                rss = int(f.read().split()[1]) * pagesize
            with open(f"/proc/{pid}/status") as f:
                uid_str = "0"
                for line in f:
                    if line.startswith("Uid:"):
                        uid_str = line.split()[1]
                        break
            rows.append({
                "pid": int(pid),
                "comm": comm,
                "rss": rss,
                "uid": uid_str,
            })
        except OSError:
            continue

    rows.sort(key=lambda x: x["rss"], reverse=True)
    return rows[:n]


def setup_logs_server_routes(session_factory):
    """Mendaftarkan rute log server pusat ke NiceGUI engine."""

    @ui.page("/logs")
    def page_logs(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")

        with render_layout(request, user, active_tab="logs"):
            container = ui.column().classes("w-full gap-3")
            container = ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6")

            with container:
                # Header
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0.5"):
                        ui.label("Log & Kesehatan Server Pusat").classes("text-xl font-bold text-white")
                        host_name = socket.gethostname()
                        upt = int(_get_master_uptime())
                        upt_str = f"{upt // 86400} hari, {(upt % 86400) // 3600} jam, {(upt % 3600) // 60} menit"
                        ui.label(f"Node Pusat: {host_name} · Uptime: {upt_str}").classes("text-xs text-slate-400 font-mono")

                    ui.button("Segarkan", icon="refresh", on_click=lambda: _refresh_data()).props("dense outline no-caps size=sm color=primary").classes("text-xs")

                # 4 Kartu Metrik Server Pusat
                mem_data = _get_master_mem()
                load_data = _get_master_loadavg()
                cpu_val = _get_master_cpu()

                with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"):
                    with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                        ui.label("CPU Server Pusat").classes("text-xs text-slate-400 font-medium")
                        lbl_cpu = ui.label(f"{cpu_val:.1f}%").classes("text-2xl font-bold text-sky-400")
                        bar_cpu = ui.linear_progress(value=cpu_val / 100.0, color="primary").classes("w-full h-1.5 rounded")

                    with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                        ui.label("Memori RAM").classes("text-xs text-slate-400 font-medium")
                        lbl_mem = ui.label(f"{format_bytes(mem_data['used'])} / {format_bytes(mem_data['total'])} ({mem_data['pct']}%)").classes("text-base font-bold text-emerald-400")
                        bar_mem = ui.linear_progress(value=mem_data["pct"] / 100.0, color="positive").classes("w-full h-1.5 rounded")

                    with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                        ui.label("Beban Rata-Rata (1/5/15m)").classes("text-xs text-slate-400 font-medium")
                        lbl_load = ui.label(f"{load_data[0]:.2f} / {load_data[1]:.2f} / {load_data[2]:.2f}").classes("text-lg font-bold text-amber-400")

                    with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                        ui.label("Memori Virtual (Swap)").classes("text-xs text-slate-400 font-medium")
                        lbl_swap = ui.label(f"{format_bytes(mem_data['swap_used'])} / {format_bytes(mem_data['swap_total'])} ({mem_data['swap_pct']}%)").classes("text-base font-bold text-purple-400")
                        bar_swap = ui.linear_progress(value=mem_data["swap_pct"] / 100.0, color="purple").classes("w-full h-1.5 rounded")

                # Tabel Proses Terbesar Server Pusat
                with ui.card().classes("w-full p-4 custom-card"):
                    ui.label("Proses Penggunaan Memori Terbesar (Server Pusat)").classes("text-sm font-bold text-white mb-2")
                    procs = _get_master_top_processes(10)
                    p_cols = [
                        {"name": "pid", "label": "PID", "field": "pid", "align": "center"},
                        {"name": "comm", "label": "NAMA PROSES", "field": "comm", "align": "left"},
                        {"name": "rss", "label": "MEMORI (RSS)", "field": "rss", "align": "left"},
                        {"name": "uid", "label": "UID PENGGUNA", "field": "uid", "align": "center"},
                    ]
                    p_rows = []
                    for pr in procs:
                        p_rows.append({
                            "pid": pr["pid"],
                            "comm": pr["comm"],
                            "rss": format_bytes(pr["rss"]),
                            "uid": pr["uid"],
                        })
                    proc_table = ui.table(columns=p_cols, rows=p_rows, row_key="pid").classes("w-full bg-slate-900")

                # Log Layanan Journalctl (pantau-server.service)
                with ui.card().classes("w-full p-4 custom-card flex flex-col gap-2"):
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Log Layanan Pantau Server (systemd journal)").classes("text-sm font-bold text-white")
                        ui.button("Segarkan Log", icon="refresh", on_click=lambda: _load_journal_logs()).props("dense outline size=xs color=slate-4 no-caps")

                    log_area = ui.code(content="Memuat log...", language="bash").classes("w-full bg-slate-950 p-4 rounded text-xs font-mono text-slate-300 max-h-96 overflow-y-auto")

            def _load_journal_logs():
                try:
                    res = subprocess.run(
                        ["journalctl", "-u", "pantau-server.service", "-n", "80", "--no-pager"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                        check=False,
                    )
                    log_txt = res.stdout.strip() or res.stderr.strip() or "Tidak ada baris log tersedia."
                    log_area.set_content(log_txt)
                except Exception as e:
                    log_area.set_content(f"Gagal membaca journal log: {e}")

            def _refresh_data():
                c = _get_master_cpu()
                m = _get_master_mem()
                ld = _get_master_loadavg()
                lbl_cpu.set_text(f"{c:.1f}%")
                bar_cpu.set_value(c / 100.0)
                lbl_mem.set_text(f"{format_bytes(m['used'])} / {format_bytes(m['total'])} ({m['pct']}%)")
                bar_mem.set_value(m["pct"] / 100.0)
                lbl_load.set_text(f"{ld[0]:.2f} / {ld[1]:.2f} / {ld[2]:.2f}")
                lbl_swap.set_text(f"{format_bytes(m['swap_used'])} / {format_bytes(m['swap_total'])} ({m['swap_pct']}%)")
                bar_swap.set_value(m["swap_pct"] / 100.0)
                _load_journal_logs()
                notify_info("Data metrik server pusat diperbarui.")

            _load_journal_logs()
