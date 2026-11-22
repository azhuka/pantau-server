import json
import os
import re
import stat
import pwd
import grp
import shutil
import subprocess
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Body, Form, File, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
from core.database import get_db
from routers.auth import get_current_user
from models.user import User
from models.server import Server, ServerExtras, SystemSnapshot
from models.problem import ServerProblem
from models.command import Command
from models.misc import AuditLog
from services.problem_service import check_all_servers_stale

router = APIRouter(prefix="/api/servers", tags=["Servers"])

@router.get("")
def list_servers(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Daftar seluruh server armada NOC beserta ringkasan status real-time."""
    check_all_servers_stale(db)
    servers = db.query(Server).filter(Server.is_active == 1).order_by(Server.id.asc()).all()
    now = datetime.utcnow()
    result = []

    # Optimasi konkurensi & performa (Zero N+1 Query Batch Loading):
    # 1. Agregasi jumlah insiden aktif seluruh server dalam 1 kueri
    prob_counts = dict(
        db.query(ServerProblem.server_id, func.count(ServerProblem.id))
        .filter(ServerProblem.resolved_at == None)
        .group_by(ServerProblem.server_id)
        .all()
    )

    # 2. Ambil snapshot ID terbaru seluruh armada dalam 1 kueri batch
    server_ids = [s.id for s in servers]
    latest_snaps_map = {}
    if server_ids:
        latest_snap_ids = [
            sid for (sid,) in db.query(func.max(SystemSnapshot.id))
            .filter(SystemSnapshot.server_id.in_(server_ids))
            .group_by(SystemSnapshot.server_id)
            .all()
        ]
        if latest_snap_ids:
            snaps = db.query(SystemSnapshot).filter(SystemSnapshot.id.in_(latest_snap_ids)).all()
            latest_snaps_map = {sn.server_id: sn for sn in snaps}

    for s in servers:
        if not user.can_access_server(s.id):
            continue

        is_online = False
        if s.last_seen:
            diff_secs = (now - s.last_seen).total_seconds()
            is_online = diff_secs <= 60

        # Snapshot metrik terbaru dari map batch
        latest_snap = latest_snaps_map.get(s.id)

        cpu = latest_snap.cpu if latest_snap else 0.0
        mem_pct = 0.0
        if latest_snap and latest_snap.mem_total and latest_snap.mem_total > 0:
            mem_pct = round((latest_snap.mem_used / latest_snap.mem_total) * 100, 1)

        disk_pct = 0.0
        if latest_snap and latest_snap.disks:
            try:
                disks_data = json.loads(latest_snap.disks) if isinstance(latest_snap.disks, str) else latest_snap.disks
                if isinstance(disks_data, list) and disks_data:
                    root_d = next((d for d in disks_data if isinstance(d, dict) and d.get("mount") == "/"), disks_data[0])
                    if isinstance(root_d, dict):
                        disk_pct = float(root_d.get("pct") or root_d.get("used_percent") or root_d.get("percent") or 0.0)
            except Exception:
                disk_pct = 0.0

        # Hitung masalah aktif dari agregat batch
        active_problems_count = prob_counts.get(s.id, 0)

        # Auto-expire maintenance mode jika batas waktu terlewati
        if s.is_maintenance and s.maintenance_until and s.maintenance_until < now:
            s.is_maintenance = 0
            s.maintenance_until = None
            s.maintenance_reason = None
            db.commit()

        result.append({
            "id": s.id,
            "hostname": s.hostname,
            "ip_address": s.ip_address,
            "group_name": s.group_name or "Default",
            "tier": s.tier,
            "is_online": is_online,
            "last_seen": s.last_seen.isoformat() if s.last_seen else None,
            "cpu": cpu,
            "mem_pct": mem_pct,
            "disk_pct": disk_pct,
            "uptime_secs": latest_snap.uptime_secs if latest_snap else 0,
            "active_problems_count": active_problems_count,
            "is_maintenance": bool(s.is_maintenance),
            "maintenance_until": s.maintenance_until.isoformat() if s.maintenance_until else None,
            "maintenance_reason": s.maintenance_reason,
        })

    return {"ok": True, "servers": result}

@router.get("/{sid}")
def get_server_detail(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Rincian profil server, spesifikasi perangkat keras, dan snapshot."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    if server.is_maintenance and server.maintenance_until and server.maintenance_until < now:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        db.commit()

    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    latest_snap = (
        db.query(SystemSnapshot)
        .filter(SystemSnapshot.server_id == sid)
        .order_by(SystemSnapshot.id.desc())
        .first()
    )

    def _parse(val):
        if not val:
            return None
        try:
            return json.loads(val)
        except Exception:
            return val

    raw_disks = _parse(latest_snap.disks) if latest_snap else []
    normalized_disks = []
    if isinstance(raw_disks, list):
        for d in raw_disks:
            if isinstance(d, dict):
                d_copy = dict(d)
                pct = d_copy.get("percent") if d_copy.get("percent") is not None else (d_copy.get("pct") if d_copy.get("pct") is not None else d_copy.get("used_percent"))
                if pct is None and d_copy.get("total") and d_copy.get("used"):
                    try:
                        pct = round((d_copy["used"] / d_copy["total"]) * 100, 1)
                    except ZeroDivisionError:
                        pct = 0.0
                d_copy["percent"] = pct
                d_copy["used_percent"] = pct
                d_copy["pct"] = pct
                normalized_disks.append(d_copy)

    return {
        "ok": True,
        "server": {
            "id": server.id,
            "hostname": server.hostname,
            "ip_address": server.ip_address,
            "group_name": server.group_name or "Default",
            "tier": server.tier,
            "is_online": is_online,
            "last_seen": server.last_seen.isoformat() if server.last_seen else None,
            "is_maintenance": bool(server.is_maintenance),
            "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
            "maintenance_reason": server.maintenance_reason,
            "is_proxmox_ha": bool(server.is_proxmox_ha),
            "is_isolated_net": bool(server.is_isolated_net),
            "tags": server.tags,
            "notes": server.notes,
            "kernel": extras.kernel if extras else None,
            "os_label": extras.os_label if extras else None,
            "arch": extras.arch if extras else None,
            "agent_version": extras.agent_version if extras else None,
            "apt_upgradable": extras.apt_upgradable if extras else 0,
            "hardware": _parse(extras.hardware_specs) if extras else None,
            "metrics": {
                "cpu": latest_snap.cpu if latest_snap else 0.0,
                "load": [latest_snap.load1, latest_snap.load5, latest_snap.load15] if latest_snap else [0, 0, 0],
                "mem_total": latest_snap.mem_total if latest_snap else 0,
                "mem_used": latest_snap.mem_used if latest_snap else 0,
                "mem_avail": latest_snap.mem_avail if latest_snap else 0,
                "swap_total": latest_snap.swap_total if latest_snap else 0,
                "swap_used": latest_snap.swap_used if latest_snap else 0,
                "procs": latest_snap.procs if latest_snap else 0,
                "uptime_secs": latest_snap.uptime_secs if latest_snap else 0,
                "disks": normalized_disks,
                "net": _parse(latest_snap.net) if latest_snap else {},
            }
        }
    }

@router.get("/{sid}/services")
def get_server_services(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.systemd_units:
        return {"ok": True, "services": []}
    try:
        data = json.loads(extras.systemd_units)
        normalized = []
        if isinstance(data, list):
            for s in data:
                if isinstance(s, dict):
                    name = s.get("name") or s.get("service_name") or s.get("unit") or "service"
                    is_up = (s.get("status") == "up") or (s.get("active") == "active") or (s.get("sub") == "running")
                    active = "active" if is_up else (s.get("active") or "inactive")
                    sub = "running" if is_up else (s.get("sub") or "stopped")
                    desc = s.get("description") or (f"Port {s.get('port')}" if s.get("port") else "-")
                    normalized.append({
                        "name": name,
                        "active": active,
                        "sub": sub,
                        "description": desc,
                        "port": s.get("port")
                    })
                elif isinstance(s, str):
                    normalized.append({
                        "name": s,
                        "active": "active",
                        "sub": "running",
                        "description": "System service unit",
                        "port": None
                    })
        return {"ok": True, "services": normalized}
    except Exception:
        return {"ok": True, "services": []}

@router.get("/{sid}/processes")
def get_server_processes(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.top_procs:
        return {"ok": True, "processes": []}
    try:
        data = json.loads(extras.top_procs)
        if isinstance(data, dict):
            merged = []
            seen_pids = set()
            for p in (data.get("cpu") or []) + (data.get("mem") or []):
                pid = p.get("pid")
                if pid and pid not in seen_pids:
                    seen_pids.add(pid)
                    merged.append({
                        "pid": pid,
                        "user": p.get("user") or "unknown",
                        "cpu": p.get("cpu", 0.0),
                        "mem": p.get("mem", 0.0),
                        "cmd": p.get("comm") or p.get("cmd") or "-",
                    })
            return {"ok": True, "processes": merged}
        elif isinstance(data, list):
            return {"ok": True, "processes": data}
        return {"ok": True, "processes": []}
    except Exception:
        return {"ok": True, "processes": []}

@router.get("/{sid}/ports")
def get_server_ports(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.listening_ports:
        return {"ok": True, "ports": []}
    try:
        data = json.loads(extras.listening_ports)
        return {"ok": True, "ports": data}
    except Exception:
        return {"ok": True, "ports": []}

@router.get("/{sid}/accounts")
def get_server_accounts(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Mengembalikan akun pengguna lokal serta sesi SSH remote aktif."""
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.accounts:
        return {"ok": True, "accounts": []}
    try:
        data = json.loads(extras.accounts)
        return {"ok": True, "accounts": data}
    except Exception:
        return {"ok": True, "accounts": []}

@router.get("/{sid}/firewall")
def get_server_firewall(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Status UFW dan daftar aturan firewall."""
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.firewall:
        return {"ok": True, "firewall": {"status": "unknown", "rules": [], "blocked_ips": []}}
    try:
        data = json.loads(extras.firewall)
        return {"ok": True, "firewall": data}
    except Exception:
        return {"ok": True, "firewall": {"status": "unknown", "rules": [], "blocked_ips": []}}

@router.get("/{sid}/cron")
def get_server_cron(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Daftar crontab dan systemd timers."""
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.cron_jobs:
        return {"ok": True, "cron": {"jobs": []}}
    try:
        data = json.loads(extras.cron_jobs)
        return {"ok": True, "cron": data}
    except Exception:
        return {"ok": True, "cron": {"jobs": []}}

@router.get("/{sid}/problems")
def get_server_problems(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Insiden / anomali aktif khusus untuk server ini."""
    problems = (
        db.query(ServerProblem)
        .filter(ServerProblem.server_id == sid, ServerProblem.resolved_at == None)
        .order_by(ServerProblem.id.desc())
        .all()
    )
    result = []
    for prob in problems:
        result.append({
            "id": prob.id,
            "key": prob.key,
            "severity": prob.severity,
            "message": prob.message,
            "tip": prob.tip,
            "started_at": prob.started_at.isoformat() if prob.started_at else None,
            "is_active": prob.is_active,
        })
    return {"ok": True, "problems": result}

@router.post("/{sid}/actions")
def dispatch_server_action(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kirim perintah aksi kontrol ke server klien:
    - restart_service, stop_service, start_service
    - kill_process
    - terminate_ssh_session (putus paksa sesi remote)
    """
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    action = body.get("action")
    params = body.get("params") or {}
    now = datetime.utcnow()

    # Proteksi Proxmox HA pada aksi Power OFF
    if action == "poweroff_host":
        target_srv = db.query(Server).filter(Server.id == sid).first()
        if target_srv and getattr(target_srv, "is_proxmox_ha", 0) == 1:
            raise HTTPException(
                status_code=400,
                detail="Server dilindungi oleh Proxmox HA. Matikan mesin melalui Proxmox VE Web UI / Cluster Manager."
            )

    cmd = Command(
        server_id=sid,
        action=action,
        params=json.dumps(params, ensure_ascii=False),
        issued_by=user.username,
        status="pending",
        created_at=now
    )
    db.add(cmd)
    db.flush()

    # Log ke audit trail
    audit_entry = AuditLog(
        server_id=sid,
        username=user.username,
        action=action,
        target=str(params),
        result="antre",
        meta=f"Perintah {action} didaftarkan oleh {user.username}",
        created_at=now
    )
    db.add(audit_entry)
    db.commit()

    return {"ok": True, "command_id": cmd.id, "message": f"Perintah {action} berhasil dijadwalkan"}


def _format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}" if unit != 'B' else f"{size_bytes} B"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


@router.post("/{sid}/terminal/exec")
def execute_terminal_command(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Eksekusi perintah terminal pada server secara real-time."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    if server.is_maintenance and server.maintenance_until and server.maintenance_until < now:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        db.commit()

    cmd = (body.get("cmd") or "").strip()
    cwd = body.get("cwd") or "/root"
    if not cmd:
        return {"ok": False, "error": "Command is empty"}

    # Proteksi dasar perintah destruktif fatal
    dangerous_patterns = [r"\brm\s+-rf\s+/\b", r"\bmkfs\b", r"\bdd\s+if="]
    for pattern in dangerous_patterns:
        if re.search(pattern, cmd):
            raise HTTPException(status_code=400, detail="Command blocked by safety guardrails")

    now = datetime.utcnow()
    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="terminal_exec",
        target=cmd[:200],
        result="success",
        meta=f"Terminal command executed by {user.username}",
        created_at=now
    )
    db.add(audit)
    db.commit()

    try:
        run_cwd = cwd if (os.path.isdir(cwd) and os.access(cwd, os.R_OK | os.X_OK)) else os.path.expanduser("~")
        res = subprocess.run(
            cmd,
            shell=True,
            cwd=run_cwd,
            text=True,
            capture_output=True,
            timeout=15,
            executable="/bin/bash"
        )
        out = res.stdout
        if res.stderr:
            out = f"{out}\n{res.stderr}" if out else res.stderr
        return {
            "ok": True,
            "output": out if out else "(Command completed with no output)",
            "exit_code": res.returncode,
            "cwd": run_cwd
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "output": "Error: Command timed out after 15 seconds.",
            "exit_code": 124,
            "cwd": cwd
        }
    except Exception as e:
        return {
            "ok": False,
            "output": f"Execution error: {str(e)}",
            "exit_code": 1,
            "cwd": cwd
        }


@router.get("/{sid}/files")
def list_server_files(
    sid: int,
    path: str = "/home/bos",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Daftar berkas dan direktori pada server."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    target_path = os.path.abspath(path)
    if not (os.path.exists(target_path) and os.access(target_path, os.R_OK)):
        target_path = os.path.expanduser("~")

    items = []
    if target_path != "/":
        parent_dir = os.path.dirname(target_path)
        items.append({
            "name": ".. (parent)",
            "path": parent_dir,
            "is_dir": True,
            "size": 0,
            "size_human": "-",
            "perms": "drwxr-xr-x",
            "owner": "root:root",
            "mtime": "-"
        })

    try:
        with os.scandir(target_path) as it:
            entries = sorted(list(it), key=lambda e: (not e.is_dir(), e.name.lower()))
            for entry in entries:
                try:
                    st = entry.stat()
                    is_dir = entry.is_dir()
                    mode_str = stat.filemode(st.st_mode)
                    try:
                        owner_name = pwd.getpwuid(st.st_uid).pw_name
                        group_name = grp.getgrgid(st.st_gid).gr_name
                        owner = f"{owner_name}:{group_name}"
                    except Exception:
                        owner = f"{st.st_uid}:{st.st_gid}"

                    mtime_dt = datetime.fromtimestamp(st.st_mtime)
                    mtime_str = mtime_dt.strftime("%Y-%m-%d %H:%M")

                    items.append({
                        "name": entry.name,
                        "path": os.path.join(target_path, entry.name),
                        "is_dir": is_dir,
                        "size": st.st_size if not is_dir else 0,
                        "size_human": _format_size(st.st_size) if not is_dir else "Dir",
                        "perms": mode_str,
                        "owner": owner,
                        "mtime": mtime_str
                    })
                except (PermissionError, FileNotFoundError):
                    continue

        # Dynamic bookmark discovery (anti-hardcoding: only paths that actually exist on this host)
        candidate_bookmarks = [
            {"label": "~ Home", "path": os.path.expanduser("~"), "title": f"Home ({os.path.expanduser('~')})"},
            {"label": "/ Root", "path": "/", "title": "Root Filesystem (/)"},
            {"label": "/var/log", "path": "/var/log", "title": "System Logs (/var/log)"},
            {"label": "/etc", "path": "/etc", "title": "System Config (/etc)"},
            {"label": "/opt", "path": "/opt", "title": "Optional Software (/opt)"},
            {"label": "/var/www", "path": "/var/www", "title": "Web Data (/var/www)"},
            {"label": "/tmp", "path": "/tmp", "title": "Temporary Directory (/tmp)"},
        ]
        discovered_bookmarks = [
            bm for bm in candidate_bookmarks
            if os.path.exists(bm["path"]) and os.path.isdir(bm["path"])
        ]

        return {"ok": True, "path": target_path, "items": items, "bookmarks": discovered_bookmarks}
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied reading directory")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sid}/files/content")
def read_file_content(
    sid: int,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Membaca isi berkas teks (maksimal 2MB)."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    target_path = os.path.abspath(path)
    if not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="File not found")

    st = os.stat(target_path)
    if st.st_size > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large to open in web editor (max 2MB)")

    try:
        with open(target_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        return {
            "ok": True,
            "path": target_path,
            "content": content,
            "size": st.st_size,
            "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{sid}/files/save")
def save_file_content(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Menyimpan modifikasi isi berkas."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    path = body.get("path")
    content = body.get("content", "")
    make_backup = bool(body.get("make_backup", True))
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")

    target_path = os.path.abspath(path)
    try:
        backup_created = None
        if make_backup and os.path.exists(target_path):
            import shutil
            bak_path = target_path + ".bak"
            try:
                shutil.copy2(target_path, bak_path)
                backup_created = bak_path
            except Exception:
                pass

        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)

        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="file_save",
            target=target_path,
            result="success",
            meta=f"File {target_path} edited and saved by {user.username}" + (f" (backup: {backup_created})" if backup_created else ""),
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()

        return {"ok": True, "message": "File saved successfully", "backup_created": backup_created}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{sid}/files/touch")
def touch_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Membuat file kosong baru."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")

    target_path = os.path.abspath(path)
    if os.path.exists(target_path):
        raise HTTPException(status_code=400, detail="File or directory already exists")

    try:
        with open(target_path, "a", encoding="utf-8"):
            pass

        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="file_touch",
            target=target_path,
            result="success",
            meta=f"New file created by {user.username}",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
        return {"ok": True, "message": "File created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{sid}/files/mkdir")
def mkdir_server_dir(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Membuat direktori baru."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")

    target_path = os.path.abspath(path)
    if os.path.exists(target_path):
        raise HTTPException(status_code=400, detail="Directory or file already exists")

    try:
        os.makedirs(target_path, exist_ok=False)

        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="file_mkdir",
            target=target_path,
            result="success",
            meta=f"Directory created by {user.username}",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
        return {"ok": True, "message": "Directory created"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{sid}/files/rm")
def remove_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Menghapus file atau direktori."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")

    target_path = os.path.abspath(path)
    # Proteksi direktori sistem vital
    if target_path in ("/", "/root", "/home", "/etc", "/var", "/usr", "/bin", "/sbin", "/boot"):
        raise HTTPException(status_code=400, detail="Protected system path cannot be deleted")

    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="File or directory not found")

    try:
        import shutil
        if os.path.isdir(target_path):
            shutil.rmtree(target_path)
        else:
            os.remove(target_path)

        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="file_delete",
            target=target_path,
            result="success",
            meta=f"Deleted by {user.username}",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
        return {"ok": True, "message": "Deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{sid}/files/download")
def download_server_file(
    sid: int,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengunduh berkas dari server."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    target_path = os.path.abspath(path)
    if not (os.path.exists(target_path) and os.path.isfile(target_path)):
        raise HTTPException(status_code=404, detail="File not found")

    filename = os.path.basename(target_path)
    return FileResponse(target_path, filename=filename)


@router.post("/{sid}/files/rename")
def rename_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengganti nama berkas atau direktori."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    old_path = str(body.get("old_path", "")).strip()
    new_path = str(body.get("new_path", "")).strip()
    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="Old path and new path are required")

    target_old = os.path.abspath(old_path)
    target_new = os.path.abspath(new_path)

    if not os.path.exists(target_old):
        raise HTTPException(status_code=404, detail="Source file or directory not found")

    if os.path.exists(target_new):
        raise HTTPException(status_code=400, detail="Target path already exists")

    try:
        os.rename(target_old, target_new)
        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="file_rename",
            target=f"{target_old} -> {target_new}",
            result="success",
            meta=f"Renamed by {user.username}",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
        return {"ok": True, "message": "Renamed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{sid}/files/chmod")
def chmod_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengubah izin berkas atau direktori (mode oktal, misal '0644' atau '0755')."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    path = str(body.get("path", "")).strip()
    mode = str(body.get("mode", "")).strip()
    if not path or not mode:
        raise HTTPException(status_code=400, detail="Path and mode are required")

    target_path = os.path.abspath(path)
    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="File or directory not found")

    try:
        mode_int = int(mode, 8)
        os.chmod(target_path, mode_int)
        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="file_chmod",
            target=f"{target_path} (mode={mode})",
            result="success",
            meta=f"Chmod by {user.username}",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
        return {"ok": True, "message": "Permissions updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{sid}/files/copy")
def copy_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Menyalin berkas atau direktori."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    sources = body.get("sources", [])
    destination = str(body.get("destination", "")).strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sources and destination required")

    target_dest = os.path.abspath(destination)
    if not os.path.isdir(target_dest):
        raise HTTPException(status_code=404, detail="Destination directory not found")

    copied = []
    for src in sources:
        target_src = os.path.abspath(src)
        if not os.path.exists(target_src):
            continue
        dest_item = os.path.join(target_dest, os.path.basename(target_src))
        if os.path.isdir(target_src):
            shutil.copytree(target_src, dest_item, dirs_exist_ok=True)
        else:
            shutil.copy2(target_src, dest_item)
        copied.append(target_src)

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="file_copy",
        target=f"{len(copied)} items -> {target_dest}",
        result="success",
        meta=f"Copied by {user.username}",
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()
    return {"ok": True, "copied": copied}


@router.post("/{sid}/files/move")
def move_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Memindahkan berkas atau direktori (cut-paste)."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    sources = body.get("sources", [])
    destination = str(body.get("destination", "")).strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sources and destination required")

    target_dest = os.path.abspath(destination)
    if not os.path.isdir(target_dest):
        raise HTTPException(status_code=404, detail="Destination directory not found")

    moved = []
    for src in sources:
        target_src = os.path.abspath(src)
        if not os.path.exists(target_src):
            continue
        dest_item = os.path.join(target_dest, os.path.basename(target_src))
        shutil.move(target_src, dest_item)
        moved.append(target_src)

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="file_move",
        target=f"{len(moved)} items -> {target_dest}",
        result="success",
        meta=f"Moved by {user.username}",
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()
    return {"ok": True, "moved": moved}


@router.post("/{sid}/files/duplicate")
def duplicate_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Duplikasi kloning lokal berkas/folder pada server."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    source = str(body.get("source", "")).strip()
    target_name = str(body.get("target_name", "")).strip()
    if not source or not target_name:
        raise HTTPException(status_code=400, detail="Source and target_name required")

    target_src = os.path.abspath(source)
    if not os.path.exists(target_src):
        raise HTTPException(status_code=404, detail="Source not found")

    parent = os.path.dirname(target_src)
    target_dst = os.path.join(parent, target_name)
    if os.path.exists(target_dst):
        raise HTTPException(status_code=409, detail="Target name already exists")

    if os.path.isdir(target_src):
        shutil.copytree(target_src, target_dst)
    else:
        shutil.copy2(target_src, target_dst)

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="file_duplicate",
        target=f"{target_src} -> {target_dst}",
        result="success",
        meta=f"Duplicated by {user.username}",
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()
    return {"ok": True, "target_path": target_dst, "target_name": target_name}


@router.post("/{sid}/files/upload")
async def upload_server_file(
    sid: int,
    destination: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unggah berkas ke server."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    target_dest = os.path.abspath(destination)
    if not os.path.isdir(target_dest):
        raise HTTPException(status_code=404, detail="Destination directory not found")

    filename = os.path.basename(file.filename or "uploaded_file")
    target_path = os.path.join(target_dest, filename)

    raw = await file.read()
    if len(raw) > 100 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 100 MB)")

    with open(target_path, "wb") as f:
        f.write(raw)

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="file_upload",
        target=f"{target_path} ({len(raw)} bytes)",
        result="success",
        meta=f"Uploaded by {user.username}",
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()
    return {"ok": True, "path": target_path, "size": len(raw)}


@router.post("/{sid}/maintenance")
def toggle_server_maintenance(
    sid: int,
    body: dict = Body(default={}),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktifkan atau nonaktifkan status maintenance mode server."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Forbidden")

    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    if server.is_maintenance and server.maintenance_until and server.maintenance_until < now:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        db.commit()

    action = body.get("action", "toggle")
    try:
        duration = int(body.get("duration_minutes", 60) or 0)
    except (ValueError, TypeError):
        duration = 60
    reason = str(body.get("reason", "") or "").strip()[:255]

    if action == "toggle":
        action = "disable" if server.is_maintenance else "enable"

    if action == "enable":
        server.is_maintenance = 1
        server.maintenance_reason = reason or "Scheduled maintenance"
        if duration > 0:
            server.maintenance_until = now + timedelta(minutes=duration)
        else:
            server.maintenance_until = None
        detail_msg = f"Maintenance mode enabled ({duration}m, reason: {server.maintenance_reason})"
    else:
        server.is_maintenance = 0
        server.maintenance_until = None
        server.maintenance_reason = None
        detail_msg = "Maintenance mode disabled"

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="maintenance_mode",
        target=f"{server.hostname}: is_maintenance={server.is_maintenance}",
        result="success",
        meta=detail_msg,
        created_at=now
    )
    db.add(audit)
    db.commit()

    return {
        "ok": True,
        "is_maintenance": bool(server.is_maintenance),
        "maintenance_until": server.maintenance_until.isoformat() if server.maintenance_until else None,
        "maintenance_reason": server.maintenance_reason,
        "message": detail_msg
    }


@router.get("/{sid}/packages")
def get_server_packages(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.apt_packages:
        return {"ok": True, "packages": [], "upgradable_count": extras.apt_upgradable if extras else 0}
    try:
        data = json.loads(extras.apt_packages)
        return {"ok": True, "packages": data, "upgradable_count": extras.apt_upgradable or len(data)}
    except Exception:
        return {"ok": True, "packages": [], "upgradable_count": 0}


@router.get("/{sid}/ssl")
def get_server_ssl(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.ssl_certs:
        return {"ok": True, "certs": []}
    try:
        data = json.loads(extras.ssl_certs)
        return {"ok": True, "certs": data}
    except Exception:
        return {"ok": True, "certs": []}


@router.get("/{sid}/logs")
def get_server_logs(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.system_logs:
        return {"ok": True, "logs": []}
    try:
        data = json.loads(extras.system_logs)
        return {"ok": True, "logs": data}
    except Exception:
        return {"ok": True, "logs": []}


@router.get("/{sid}/fim")
def get_server_fim(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    extras = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if not extras or not extras.security:
        return {"ok": True, "fim": []}
    try:
        data = json.loads(extras.security)
        return {"ok": True, "fim": data}
    except Exception:
        return {"ok": True, "fim": []}
