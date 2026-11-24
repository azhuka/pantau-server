"""Host dashboard system metrics and internal proc telemetry for Pantau Server."""

import logging
import os
import time
from typing import Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("pantau.system_service")

_SERVER_BOOT_TIME: int = int(time.time())
PROC_CACHE: dict = {"t": 0.0, "pt": 0.0, "cput": 0, "cpub": 0, "procs": {}}


def _proc_uptime() -> float:
    """Mengambil uptime host lokal dari /proc/uptime."""
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except OSError:
        return 0.0


def _proc_loadavg() -> list:
    """Mengambil load average 1, 5, 15 menit dari /proc/loadavg."""
    try:
        with open("/proc/loadavg") as f:
            return [float(x) for x in f.read().split()[:3]]
    except OSError:
        return []


def _proc_cpu() -> dict:
    """Mengambil utilisasi CPU host lokal dari /proc/stat."""
    now = time.time()
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
    except OSError:
        return {"cpu_percent": None, "cores": os.cpu_count() or 1}
    if not parts or parts[0] != "cpu":
        return {"cpu_percent": None, "cores": os.cpu_count() or 1}
    vals = [int(x) for x in parts[1:8]]
    total = sum(vals)
    busy = total - (vals[3] + vals[4])  # idle + iowait
    pct = None
    prev_t = PROC_CACHE["t"]
    if prev_t:
        dt = now - prev_t
        nt = total - PROC_CACHE["cput"]
        if dt > 0 and nt > 0:
            pct = round((busy - PROC_CACHE["cpub"]) / nt * 100, 1)
    PROC_CACHE["pt"], PROC_CACHE["t"] = prev_t, now
    PROC_CACHE["cput"], PROC_CACHE["cpub"] = total, busy
    return {"cpu_percent": pct, "cores": os.cpu_count() or 1}


def _proc_memory() -> dict:
    """Mengambil penggunaan memori RAM host lokal dari /proc/meminfo."""
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2:
                    info[p[0].rstrip(":")] = int(p[1])
    except OSError:
        return {}
    total = info.get("MemTotal", 0) * 1024
    avail = info.get("MemAvailable", info.get("MemFree", 0)) * 1024
    used = total - avail
    pct = round(used / total * 100, 1) if total else 0.0
    return {
        "total": total,
        "used": used,
        "free": avail,
        "percent": pct,
    }


def _proc_disks() -> list:
    """Mengambil penggunaan partisi disk penyimpanan host lokal."""
    mounts = []
    try:
        with open("/proc/mounts") as f:
            lines = f.readlines()
    except OSError:
        return mounts
    seen = set()
    for line in lines:
        parts = line.split()
        if len(parts) < 3:
            continue
        dev, mp, fstype = parts[0], parts[1], parts[2]
        if not dev.startswith("/dev/"):
            continue
        if mp in seen or mp.startswith(("/boot", "/snap", "/var/lib/docker")):
            continue
        seen.add(mp)
        try:
            st = os.statvfs(mp)
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        used = (st.f_blocks - st.f_bavail) * st.f_frsize
        pct = round(used / total * 100, 1) if total else 0.0
        mounts.append({
            "mount": mp,
            "fstype": fstype,
            "total": total,
            "used": used,
            "percent": pct,
        })
    return mounts[:8]


# ---------------------------------------------------------------------------
# Master Control: Inspeksi & Pemeliharaan Database
# ---------------------------------------------------------------------------
def get_database_status(db: Session) -> dict:
    """Mengambil status ukuran tabel basis data untuk Master Control."""
    try:
        query = text("""
            SELECT table_name AS `table`,
                   round(((data_length + index_length) / 1024 / 1024), 2) `size_mb`,
                   table_rows `rows`
            FROM information_schema.TABLES
            WHERE table_schema = DATABASE()
            ORDER BY (data_length + index_length) DESC;
        """)
        rows = db.execute(query).fetchall()
        tables = []
        total_size = 0.0
        for r in rows:
            size = float(r[1]) if r[1] is not None else 0.0
            tables.append({"table": r[0], "size_mb": size, "rows": int(r[2]) if r[2] is not None else 0})
            total_size += size
        return {"tables": tables, "total_size_mb": round(total_size, 2)}
    except Exception as e:
        logger.error("[Master Control] Gagal membaca status database: %s", e)
        return {"tables": [], "total_size_mb": 0.0}
