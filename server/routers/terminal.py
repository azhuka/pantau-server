import asyncio
import os
import pty
import select
import fcntl
import termios
import struct
import json
import logging
import re
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends, Body, Request
from sqlalchemy.orm import Session
from core.database import SessionLocal, get_db
from models.server import Server
from models.user import User
from models.misc import AuditLog
from routers.auth import get_current_user
from core.security import (
    verify_password,
    is_terminal_unlocked,
    get_terminal_lease_remaining,
    set_terminal_unlock,
    revoke_terminal_unlock,
)
import security_auth
import jwt
from config import settings

logger = logging.getLogger("pantau.terminal")

router = APIRouter(tags=["Terminal"])

# ---------------------------------------------------------------------------
# Pola escape sequence probe/query terminal (DA1, DA2, CPR, OSC color queries)
# Mencegah loop freeze dan karakter sampah pada xterm.js
# ---------------------------------------------------------------------------
DA_QUERY_PATTERN = re.compile(
    r"\x1b\[c|\x1b\[0c|\x1b\[>c|\x1b\[>0c|\x1b\[>q|\x1b\]1[01];\?(?:\x07|\x1b\\)"
)
DA_RESP_PATTERN = re.compile(
    r"\x1b\[[?>!][0-9;]*c|\x1b\[\??[0-9]+;[0-9]+R|\x1b\[[0-9]+n|\x1b\](?:10|11);[^\x07\x1b]*(?:\x07|\x1b\\)"
)


def _get_user_from_token(token: str, db: Session) -> User | None:
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        username = payload.get("sub")
        if not username:
            return None
        return db.query(User).filter(User.username == username, User.is_active == 1).first()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# OPERATOR STEP-UP AUTH & LEASE STATUS ENDPOINTS
# ---------------------------------------------------------------------------
@router.get("/api/servers/{sid}/terminal/status")
def api_terminal_status(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Cek status izin dan sisa durasi sewa (lease) otentikasi terminal untuk server ini."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    allow_term = bool(getattr(server, "allow_web_terminal", 1))
    user_can = user.has_perm("can_terminal")
    remaining = get_terminal_lease_remaining(user.id, sid)
    unlocked = remaining > 0 or user.is_master_admin

    return {
        "server_id": sid,
        "allow_web_terminal": allow_term,
        "can_terminal": user_can,
        "is_unlocked": unlocked,
        "remaining_seconds": remaining,
        "user_has_totp": bool(user.totp_enabled and user.totp_secret),
    }


@router.post("/api/servers/{sid}/terminal/unlock")
def api_terminal_unlock(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Buka kunci akses Web Terminal dengan tantangan password (step-up auth) + TOTP."""
    if not user.has_perm("can_terminal"):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda tidak memiliki wewenang Terminal Shell Web",
        )

    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    password = str(body.get("password") or "").strip()
    totp_code = str(body.get("totp") or "").strip()
    duration_minutes = int(body.get("duration_minutes") or 15)
    duration_minutes = max(5, min(120, duration_minutes))
    reason = str(body.get("reason") or "").strip()[:255]

    if not password:
        raise HTTPException(status_code=400, detail="Password akun pengguna diperlukan")

    if not verify_password(password, user.password_hash):
        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="terminal_unlock_fail",
            target=server.hostname,
            result="gagal",
            meta="Password salah saat membuka kunci terminal",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
        raise HTTPException(status_code=401, detail="Password akun salah. Akses terminal ditolak.")

    if user.totp_enabled and user.totp_secret:
        if not totp_code or not security_auth.verify_totp(user.totp_secret, totp_code):
            audit = AuditLog(
                server_id=sid,
                username=user.username,
                action="terminal_unlock_fail",
                target=server.hostname,
                result="gagal",
                meta="Kode 2FA salah saat membuka kunci terminal",
                created_at=datetime.utcnow()
            )
            db.add(audit)
            db.commit()
            raise HTTPException(status_code=401, detail="Kode 2FA / TOTP tidak valid atau telah kedaluwarsa")

    set_terminal_unlock(user.id, sid, duration_minutes)
    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="terminal_unlock",
        target=server.hostname,
        result="berhasil",
        meta=f"Durasi: {duration_minutes}m, alasan: {reason}" if reason else f"Durasi: {duration_minutes}m",
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    return {
        "ok": True,
        "remaining_seconds": duration_minutes * 60,
        "message": f"Kunci terminal berhasil dibuka ({duration_minutes} menit)",
    }


@router.post("/api/servers/{sid}/terminal/lock")
def api_terminal_lock(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Kunci kembali akses terminal dan putus sesi."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    revoke_terminal_unlock(user.id, sid)

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    hostname = server.hostname if server else f"sid={sid}"

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="terminal_lock",
        target=hostname,
        result="berhasil",
        meta="Sesi terminal dikunci kembali oleh operator",
        created_at=datetime.utcnow()
    )
    db.add(audit)
    db.commit()

    return {"ok": True, "message": "Terminal berhasil dikunci"}


@router.websocket("/ws/servers/{sid}/terminal")
async def websocket_terminal(
    websocket: WebSocket,
    sid: int,
    token: str = Query(default=""),
    cwd: str = Query(default="")
):
    await websocket.accept()

    db = SessionLocal()
    user = None
    server = None
    server_hostname = "Server"
    server_ip = "127.0.0.1"
    username = "operator"
    try:
        user = _get_user_from_token(token, db)
        if not user:
            await websocket.send_text(json.dumps({
                "type": "stdout",
                "data": "\r\n\x1b[31;1m[ACCESS DENIED] Valid authentication token is required to access Web Terminal.\x1b[0m\r\n"
            }))
            await websocket.close(code=4401)
            return

        if not user.can_access_server(sid):
            await websocket.send_text(json.dumps({
                "type": "stdout",
                "data": "\r\n\x1b[31;1m[ACCESS DENIED] You do not have permission to access terminal on this host.\x1b[0m\r\n"
            }))
            await websocket.close(code=4403)
            return

        if not user.has_perm("can_terminal"):
            await websocket.send_text(json.dumps({
                "type": "stdout",
                "data": "\r\n\x1b[31;1m[ACCESS DENIED] Izin Web Terminal (can_terminal) tidak aktif untuk akun Anda.\x1b[0m\r\n"
            }))
            await websocket.close(code=4403)
            return

        server = db.query(Server).filter(Server.id == sid).first()
        if not server:
            await websocket.send_text(json.dumps({
                "type": "stdout",
                "data": "\r\n\x1b[31;1m[HOST NOT FOUND] Invalid host ID.\x1b[0m\r\n"
            }))
            await websocket.close(code=4404)
            return

        server_hostname = str(server.hostname)
        server_ip = str(server.ip_address or "127.0.0.1")
        username = str(user.username)

        start_dir = os.path.expanduser("~")
        if cwd and os.path.isdir(cwd):
            start_dir = os.path.abspath(cwd)

        audit = AuditLog(
            server_id=sid,
            username=username,
            action="terminal_connect",
            target=f"{server_hostname}:{server_ip}",
            result="success",
            meta=f"Operator {username} initiated Web Terminal PTY session at {start_dir}",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
    finally:
        db.close()

    welcome_banner = (
        f"\r\n\x1b[1;36m// PANTAU TACTICAL PTY TERMINAL DOCK\x1b[0m\r\n"
        f"\x1b[32m● CONNECTED:\x1b[0m \x1b[1m{server_hostname}\x1b[0m ({server_ip})\r\n"
        f"\x1b[90mSession started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Interactive Bash Ready.\x1b[0m\r\n\r\n"
    )
    await websocket.send_text(json.dumps({"type": "stdout", "data": welcome_banner}))

    master_fd, slave_fd = pty.openpty()

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["LANG"] = "en_US.UTF-8"
    env["PANTAU_SERVER_ID"] = str(sid)
    env["PANTAU_HOSTNAME"] = server_hostname

    import subprocess
    process = subprocess.Popen(
        ["/bin/bash", "-l"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=start_dir,
        env=env,
        preexec_fn=os.setsid,
        close_fds=True,
    )
    os.close(slave_fd)

    flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    async def pty_reader():
        while not stop_event.is_set():
            try:
                def _read():
                    r, _, _ = select.select([master_fd], [], [], 0.05)
                    if r:
                        try:
                            return os.read(master_fd, 4096)
                        except OSError:
                            return b""
                    return None

                data = await loop.run_in_executor(None, _read)
                if data:
                    text = data.decode("utf-8", errors="replace")
                    cleaned = DA_QUERY_PATTERN.sub("", text)
                    if cleaned:
                        await websocket.send_text(json.dumps({"type": "stdout", "data": cleaned}))
                elif data == b"":
                    break
                else:
                    await asyncio.sleep(0.01)
            except Exception:
                break
        stop_event.set()

    reader_task = asyncio.create_task(pty_reader())

    try:
        while not stop_event.is_set():
            raw_msg = await websocket.receive_text()
            try:
                msg = json.loads(raw_msg)
            except Exception:
                msg = {"type": "input", "data": raw_msg}

            m_type = msg.get("type")
            if m_type == "input":
                data_str = msg.get("data", "")
                if data_str:
                    cleaned_in = DA_RESP_PATTERN.sub("", data_str)
                    if cleaned_in:
                        os.write(master_fd, cleaned_in.encode("utf-8"))
            elif m_type == "resize":
                cols = msg.get("cols", 80)
                rows = msg.get("rows", 24)
                try:
                    winsize = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
                except Exception:
                    pass
            elif m_type == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"Terminal session error: {e}")
    finally:
        stop_event.set()
        reader_task.cancel()
        try:
            os.close(master_fd)
        except Exception:
            pass
        try:
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

        db = SessionLocal()
        try:
            audit = AuditLog(
                server_id=sid,
                username=username,
                action="terminal_disconnect",
                target=f"{server_hostname}:{server_ip}",
                result="closed",
                meta="Web Terminal PTY session closed",
                created_at=datetime.utcnow()
            )
            db.add(audit)
            db.commit()
        finally:
            db.close()
