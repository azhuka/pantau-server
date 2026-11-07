"""Host dashboard system metrics and internal proc telemetry."""

import hashlib
import logging
import os
from pathlib import Path
import re
import socket
import time
from typing import Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

try:
    from config import settings
    from models import LogRequest
    from core.database import SessionLocal
except ImportError:
    from server.config import settings
    from server.models import LogRequest
    from server.core.database import SessionLocal

_SERVER_BOOT_TIME: int = int(time.time())

PROC_CACHE: dict = {"t": 0.0, "pt": 0.0, "cput": 0, "cpub": 0, "procs": {}}


def _proc_uptime() -> float:
    try:
        with open("/proc/uptime") as f:
            return float(f.read().split()[0])
    except OSError:
        return 0.0


def _proc_loadavg() -> list:
    try:
        with open("/proc/loadavg") as f:
            return [float(x) for x in f.read().split()[:3]]
    except OSError:
        return []


def _proc_cpu() -> dict:
    now = time.time()
    try:
        with open("/proc/stat") as f:
            parts = f.readline().split()
    except OSError:
        return {"cpu_percent": None, "cores": 0}
    if not parts or parts[0] != "cpu":
        return {"cpu_percent": None, "cores": 0}
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
    info = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                p = line.split()
                if len(p) >= 2:
                    info[p[0].rstrip(":")] = int(p[1])
    except OSError:
        return {}
    total = info.get("MemTotal", 0)
    avail = info.get("MemAvailable", info.get("MemFree", 0))
    swap_total = info.get("SwapTotal", 0)
    swap_free = info.get("SwapFree", 0)
    kb = 1024
    return {
        "total": total * kb,
        "available": avail * kb,
        "used": max(0, total - avail) * kb,
        "swap_total": swap_total * kb,
        "swap_used": max(0, swap_total - swap_free) * kb,
    }


def _proc_disks() -> list:
    mounts = []
    seen = set()
    try:
        with open("/proc/mounts") as f:
            rows = [l.split() for l in f]
    except OSError:
        return mounts
    for r in rows:
        if len(r) < 3:
            continue
        fstype = r[2]
        if not (
            fstype.startswith(("ext", "xfs", "btrfs", "vfat", "ntfs", "zfs"))
            or fstype == "overlay"
        ):
            continue
        mp = r[1]
        if mp in seen:
            continue
        seen.add(mp)
        try:
            st = os.statvfs(mp)
        except OSError:
            continue
        if mp == "/":
            row = {"mount": mp, "fstype": fstype if fstype != "overlay" else "rootfs"}
        else:
            row = {"mount": mp, "fstype": fstype}
        total = st.f_blocks * st.f_frsize
        used = (st.f_blocks - st.f_bavail) * st.f_frsize
        row["total"] = total
        row["used"] = used
        row["percent"] = round(used / total * 100, 1) if total else 0.0
        mounts.append(row)
    return mounts[:8]


def _proc_top(n: int = 8) -> list:
    clk = os.sysconf("SC_CLK_TCK") or 100
    pagesize = os.sysconf("SC_PAGE_SIZE") or 4096
    prev = PROC_CACHE["procs"]
    cur = {}
    rows = []
    try:
        pids = [p for p in os.listdir("/proc") if p.isdigit()]
    except OSError:
        return rows
    ncpu = os.cpu_count() or 1
    for pid in pids:
        try:
            with open(f"/proc/{pid}/stat") as f:
                fields = f.read().rstrip(")").rsplit(")", 1)[1].split()
            with open(f"/proc/{pid}/comm") as f:
                comm = f.read().strip()[:30]
            if len(fields) < 13:
                continue
            state = fields[0]
            utime = int(fields[11])
            stime = int(fields[12])
            with open(f"/proc/{pid}/statm") as f:
                rss = int(f.read().split()[1]) * pagesize
        except (OSError, ValueError, IndexError):
            continue
        cur[pid] = (utime, stime)
        dt = PROC_CACHE["t"] - PROC_CACHE["pt"]
        if pid in prev and dt > 0:
            pu, ps = prev[pid]
            ticks = (utime - pu) + (stime - ps)
            if ticks >= 0:
                pct = min(round(ticks / (dt * clk) * 100, 1), ncpu * 100)
                rows.append({"pid": int(pid), "comm": comm, "state": state, "cpu": pct, "rss": rss})
    PROC_CACHE["procs"] = cur
    rows.sort(key=lambda x: x["cpu"], reverse=True)
    return rows[:n]


# ---------------------------------------------------------------------------
# Konstanta Unit Log & Interaktivitas
# ---------------------------------------------------------------------------
VALID_UNIT_RE = re.compile(r"^[A-Za-z0-9@_.:+-]{1,100}$")
APT_UNITS = (
    "APT_UPDATE",
    "APT_UPGRADE",
    "APT_UPGRADE_INTERACT",
    "APT_DIST_UPGRADE",
    "APT_FIX",
    "PKG_UPGRADE",
    "PKG_CLEAN",
)
SHELL_UNIT = "SHELL"
INTERACTIVE_UNITS = APT_UNITS + (SHELL_UNIT,)
SHELL_INPUT_MAX = 64 * 1024
SYSLOG_FILE = "/var/log/syslog"
AUTH_FILE = "/var/log/auth.log"


def _req_is_shell(db: Session, rid: int, server_id: int) -> bool:
    """True bila rid adalah sesi shell milik server ini dan masih hidup."""
    row = (
        db.query(LogRequest.unit, LogRequest.status)
        .filter(LogRequest.id == rid, LogRequest.server_id == server_id)
        .first()
    )
    return bool(row) and row[0] == SHELL_UNIT and row[1] == "executing"


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
        tables = [{"table": r[0], "size_mb": float(r[1]), "rows": int(r[2])} for r in rows]
        total_size = sum(t["size_mb"] for t in tables)
        return {
            "ok": True,
            "total_size_mb": round(total_size, 2),
            "tables": tables,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "tables": [], "total_size_mb": 0.0}


def _get_agent_code_and_sha256() -> tuple[bytes, str, str]:
    """Mengambil bytes berkas agen terbaru, hash kriptografis SHA-256, dan versi."""
    root_dir = Path(__file__).resolve().parent.parent.parent
    candidate_paths = [
        root_dir / "package" / "opt" / "pantau" / "agent" / "agent_pantau.py",
        root_dir / "agent" / "agent_pantau.py",
        Path("/opt/pantau/agent/agent_pantau.py"),
    ]
    for p in candidate_paths:
        if p.is_file():
            try:
                data = p.read_bytes()
                h = hashlib.sha256(data).hexdigest()
                code_str = data.decode("utf-8", errors="replace")
                m = re.search(r'AGENT_VERSION\s*=\s*["\']([^"\']+)["\']', code_str)
                file_version = m.group(1) if m else settings.APP_VERSION
                return data, h, file_version
            except Exception as e:
                pass
    raise HTTPException(status_code=404, detail="Berkas agen tidak ditemukan di dashboard")

