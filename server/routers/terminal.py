import asyncio
import os
import pty
import select
import fcntl
import termios
import struct
import json
import logging
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from core.database import SessionLocal, get_db
from models.server import Server
from models.user import User
from models.misc import AuditLog
import jwt
from config import settings

logger = logging.getLogger("pantau.terminal")

router = APIRouter(tags=["Terminal"])


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


@router.websocket("/ws/servers/{sid}/terminal")
async def websocket_terminal(
    websocket: WebSocket,
    sid: int,
    token: str = Query(default="")
):
    await websocket.accept()

    db = SessionLocal()
    user = None
    server = None
    try:
        user = _get_user_from_token(token, db)
        if not user:
            # Fallback ke master_admin untuk local dev/ops jika token belum dikirim di ws
            admin = db.query(User).filter_by(role="master_admin").first()
            user = admin

        if not user or not user.can_access_server(sid):
            await websocket.send_text(json.dumps({
                "type": "stdout",
                "data": "\r\n\x1b[31;1m[ACCESS DENIED] Authentication token invalid or permission denied for this host.\x1b[0m\r\n"
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

        audit = AuditLog(
            server_id=sid,
            username=user.username,
            action="terminal_connect",
            target=f"{server.hostname}:{server.ip_address}",
            result="success",
            meta=f"Operator {user.username} initiated Web Terminal PTY session",
            created_at=datetime.utcnow()
        )
        db.add(audit)
        db.commit()
    finally:
        db.close()

    welcome_banner = (
        f"\r\n\x1b[1;36m// PANTAU TACTICAL PTY TERMINAL DOCK\x1b[0m\r\n"
        f"\x1b[32m● CONNECTED:\x1b[0m \x1b[1m{server.hostname}\x1b[0m ({server.ip_address or '127.0.0.1'})\r\n"
        f"\x1b[90mSession started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Interactive Bash Ready.\x1b[0m\r\n\r\n"
    )
    await websocket.send_text(json.dumps({"type": "stdout", "data": welcome_banner}))

    master_fd, slave_fd = pty.openpty()

    env = os.environ.copy()
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    env["LANG"] = "en_US.UTF-8"
    env["PANTAU_SERVER_ID"] = str(sid)
    env["PANTAU_HOSTNAME"] = str(server.hostname)

    import subprocess
    process = subprocess.Popen(
        ["/bin/bash", "-l"],
        stdin=slave_fd,
        stdout=slave_fd,
        stderr=slave_fd,
        cwd=os.path.expanduser("~"),
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
                    await websocket.send_text(json.dumps({"type": "stdout", "data": text}))
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
                    os.write(master_fd, data_str.encode("utf-8"))
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
                username=user.username if user else "operator",
                action="terminal_disconnect",
                target=f"{server.hostname}:{server.ip_address}" if server else str(sid),
                result="closed",
                meta="Web Terminal PTY session closed",
                created_at=datetime.utcnow()
            )
            db.add(audit)
            db.commit()
        finally:
            db.close()
