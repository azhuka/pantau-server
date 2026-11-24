import asyncio
import os
import secrets
import time
import json
import logging
import re
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, HTTPException, Depends, Body, Request, Header
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
    _get_cached_server_id,
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


class TerminalSessionBridge:
    def __init__(self, session_id: str, server_id: int):
        self.session_id = session_id
        self.server_id = server_id
        self.browser_ws: WebSocket | None = None
        self.stdin_queue: asyncio.Queue = asyncio.Queue()
        self.created_at = time.time()
        self.last_active = time.time()
        self.closed = False
        self.detached = False
        self.detached_at = 0.0
        self.output_buffer: list[str] = []
        self.buffer_len = 0
        self.MAX_BUFFER_CHARS = 250000

    def append_output(self, chunk: str):
        if not chunk:
            return
        cleaned = DA_QUERY_PATTERN.sub("", chunk)
        if not cleaned:
            return
        self.output_buffer.append(cleaned)
        self.buffer_len += len(cleaned)
        while self.buffer_len > self.MAX_BUFFER_CHARS and self.output_buffer:
            removed = self.output_buffer.pop(0)
            self.buffer_len -= len(removed)

    def get_buffered_output(self) -> str:
        return DA_QUERY_PATTERN.sub("", "".join(self.output_buffer))


class TerminalBridgeDispatcher:
    def __init__(self):
        self._sessions: dict[str, TerminalSessionBridge] = {}
        self._server_to_session: dict[int, str] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._pending_opens: dict[int, str] = {}
        self._lock = None

    def _get_lock(self):
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_or_create_event(self, server_id: int) -> asyncio.Event:
        if server_id not in self._events:
            self._events[server_id] = asyncio.Event()
        return self._events[server_id]

    async def open_or_attach_session(self, server_id: int, ws: WebSocket) -> tuple[TerminalSessionBridge, bool]:
        lock = self._get_lock()
        async with lock:
            old_sid = self._server_to_session.get(server_id)
            if old_sid and old_sid in self._sessions:
                existing = self._sessions[old_sid]
                if not existing.closed:
                    if existing.browser_ws and existing.browser_ws != ws:
                        try:
                            await existing.browser_ws.close(code=4409, reason="Replaced by new browser connection")
                        except Exception:
                            pass
                    existing.browser_ws = ws
                    existing.detached = False
                    existing.last_active = time.time()
                    return existing, True

            sess_id = secrets.token_hex(16)
            bridge = TerminalSessionBridge(sess_id, server_id)
            bridge.browser_ws = ws
            self._sessions[sess_id] = bridge
            self._server_to_session[server_id] = sess_id
            self._pending_opens[server_id] = sess_id

            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            self._events[server_id].set()
            return bridge, False

    async def pop_pending_open(self, server_id: int) -> str | None:
        lock = self._get_lock()
        async with lock:
            sess_id = self._pending_opens.pop(server_id, None)
            if server_id in self._events:
                self._events[server_id].clear()
            return sess_id

    def get_session(self, sess_id: str) -> TerminalSessionBridge | None:
        return self._sessions.get(sess_id)

    async def close_session(self, sess_id: str):
        lock = self._get_lock()
        async with lock:
            bridge = self._sessions.pop(sess_id, None)
            if bridge:
                bridge.closed = True
                if self._server_to_session.get(bridge.server_id) == sess_id:
                    self._server_to_session.pop(bridge.server_id, None)

    async def close_session_by_server(self, server_id: int):
        lock = self._get_lock()
        async with lock:
            sess_id = self._server_to_session.pop(server_id, None)
            if sess_id:
                bridge = self._sessions.pop(sess_id, None)
                if bridge:
                    bridge.closed = True
                    if bridge.browser_ws:
                        try:
                            await bridge.browser_ws.send_text(
                                json.dumps(
                                    {
                                        "type": "stdout",
                                        "data": "\r\n\x1b[33;1m[TERMINAL DIKUNCI] Operator telah mengunci sesi terminal ini.\x1b[0m\r\n",
                                    }
                                )
                            )
                            await bridge.browser_ws.close(code=4403, reason="Terminal locked by operator")
                        except Exception:
                            pass


term_dispatcher = TerminalBridgeDispatcher()


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
async def api_terminal_lock(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Kunci kembali akses terminal dan putus sesi aktif jika ada."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    revoke_terminal_unlock(user.id, sid)
    await term_dispatcher.close_session_by_server(sid)

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    hostname = server.hostname if server else f"sid={sid}"

    audit = AuditLog(
        server_id=sid,
        username=user.username,
        action="terminal_lock",
        target=hostname,
        result="berhasil",
        meta="Sesi terminal dikunci kembali oleh operator",
        created_at=datetime.utcnow(),
    )
    db.add(audit)
    db.commit()

    return {"ok": True, "message": "Terminal berhasil dikunci"}


@router.websocket("/ws/servers/{sid}/terminal")
async def websocket_terminal(
    websocket: WebSocket,
    sid: int,
    token: str = Query(default=""),
    cwd: str = Query(default=""),
):
    """Koneksi terminal realtime browser WebSocket (xterm.js) melalui TerminalBridgeDispatcher."""
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
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "stdout",
                        "data": "\r\n\x1b[31;1m[ACCESS DENIED] Valid authentication token is required to access Web Terminal.\x1b[0m\r\n",
                    }
                )
            )
            await websocket.close(code=4401)
            return

        if not user.can_access_server(sid):
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "stdout",
                        "data": "\r\n\x1b[31;1m[ACCESS DENIED] You do not have permission to access terminal on this host.\x1b[0m\r\n",
                    }
                )
            )
            await websocket.close(code=4403)
            return

        if not user.has_perm("can_terminal"):
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "stdout",
                        "data": "\r\n\x1b[31;1m[ACCESS DENIED] Izin Web Terminal (can_terminal) tidak aktif untuk akun Anda.\x1b[0m\r\n",
                    }
                )
            )
            await websocket.close(code=4403)
            return

        server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
        if not server:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "stdout",
                        "data": "\r\n\x1b[31;1m[HOST NOT FOUND] Invalid host ID or server is inactive.\x1b[0m\r\n",
                    }
                )
            )
            await websocket.close(code=4404)
            return

        if getattr(server, "allow_web_terminal", 1) == 0:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "stdout",
                        "data": "\r\n\x1b[31;1m[ACCESS DENIED] Web Terminal dinonaktifkan untuk server ini pada konfigurasi sistem.\x1b[0m\r\n",
                    }
                )
            )
            await websocket.close(code=4403)
            return

        if not (user.is_master_admin or is_terminal_unlocked(user.id, sid)):
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "stdout",
                        "data": "\r\n\x1b[31;1m[TERMINAL TERKUNCI] Otentikasi sudo step-up diperlukan untuk membuka terminal.\x1b[0m\r\n",
                    }
                )
            )
            await websocket.close(code=4403)
            return

        server_hostname = str(server.hostname)
        server_ip = str(server.ip_address or "127.0.0.1")
        username = str(user.username)
        user_id = int(user.id)
        is_master = bool(user.is_master_admin)

        audit = AuditLog(
            server_id=sid,
            username=username,
            action="terminal_connect",
            target=f"{server_hostname}:{server_ip}",
            result="success",
            meta=f"Operator {username} initiated Web Terminal session",
            created_at=datetime.utcnow(),
        )
        db.add(audit)
        db.commit()
    finally:
        db.close()

    bridge, is_reconnected = await term_dispatcher.open_or_attach_session(sid, websocket)

    if not is_reconnected:
        welcome_banner = (
            f"\r\n\x1b[1;36m// PANTAU TACTICAL PTY TERMINAL DOCK\x1b[0m\r\n"
            f"\x1b[32m● CONNECTED:\x1b[0m \x1b[1m{server_hostname}\x1b[0m ({server_ip})\r\n"
            f"\x1b[90mSession started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Interactive Agent PTY Ready.\x1b[0m\r\n\r\n"
        )
        await websocket.send_text(json.dumps({"type": "stdout", "data": welcome_banner}))
    else:
        buf = bridge.get_buffered_output()
        if buf:
            try:
                await websocket.send_text(json.dumps({"type": "stdout", "data": buf}))
            except Exception:
                pass

    try:
        while not bridge.closed:
            if not (is_master or is_terminal_unlocked(user_id, sid)):
                try:
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "stdout",
                                "data": "\r\n\x1b[31;1m[SESI HABIS] Masa berlaku izin akses terminal telah kedaluwarsa. Sesi ditutup demi keamanan.\x1b[0m\r\n",
                            }
                        )
                    )
                    await websocket.close(code=4403, reason="Terminal lease expired")
                except Exception:
                    pass
                break

            raw = await websocket.receive_text()
            bridge.last_active = time.time()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"type": "input", "data": raw}

            if msg.get("type") == "input":
                data_str = msg.get("data", "")
                if isinstance(data_str, str):
                    cleaned = DA_RESP_PATTERN.sub("", data_str)
                    if not cleaned:
                        continue
                    msg["data"] = cleaned

            await bridge.stdin_queue.put(msg)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS TERM] Sesi {bridge.session_id} error: {e}")
    finally:
        lock = term_dispatcher._get_lock()
        async with lock:
            if bridge.browser_ws == websocket:
                bridge.browser_ws = None
                bridge.detached = True
                bridge.detached_at = time.time()

        db = SessionLocal()
        try:
            audit = AuditLog(
                server_id=sid,
                username=username,
                action="terminal_disconnect",
                target=f"{server_hostname}:{server_ip}",
                result="closed",
                meta=f"Web Terminal PTY session {bridge.session_id} detached",
                created_at=datetime.utcnow(),
            )
            db.add(audit)
            db.commit()
        finally:
            db.close()


# ---------------------------------------------------------------------------
# AGENT POLLING & STREAMING ENDPOINTS
# ---------------------------------------------------------------------------
@router.get("/api/agent/terminal-requests")
async def api_agent_terminal_requests(
    x_api_key: str = Header(alias="X-Api-Key"),
):
    """Agen mem-poll permintaan pembukaan terminal session realtime (long-poll 15 dtk)."""
    server_id = _get_cached_server_id(x_api_key)
    if not server_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    sess_id = await term_dispatcher.pop_pending_open(server_id)
    if sess_id:
        return {"session_id": sess_id}

    event = await term_dispatcher.get_or_create_event(server_id)
    try:
        await asyncio.wait_for(event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        pass

    sess_id = await term_dispatcher.pop_pending_open(server_id)
    return {"session_id": sess_id}


@router.get("/api/agent/terminal/{session_id}/stdin")
async def api_agent_terminal_stdin(
    session_id: str,
    x_api_key: str = Header(alias="X-Api-Key"),
):
    """Agen mengambil ketikan admin (stdin) atau sinyal resize dari dashboard."""
    server_id = _get_cached_server_id(x_api_key)
    if not server_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if not bridge or bridge.closed:
        raise HTTPException(status_code=410, detail="Sesi terminal sudah ditutup")
    if bridge.server_id != server_id:
        raise HTTPException(status_code=403, detail="Akses ditolak: Sesi terminal bukan milik server ini")

    try:
        while True:
            msg = await asyncio.wait_for(bridge.stdin_queue.get(), timeout=15.0)
            if msg.get("type") == "input":
                data_str = msg.get("data", "")
                if isinstance(data_str, str):
                    cleaned = DA_RESP_PATTERN.sub("", data_str)
                    if not cleaned:
                        continue
                    msg["data"] = cleaned
            return msg
    except asyncio.TimeoutError:
        return {"type": "ping"}


@router.post("/api/agent/terminal/{session_id}/stdout")
async def api_agent_terminal_stdout(
    session_id: str,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen mengirimkan potongan teks output terminal ke browser WebSocket."""
    server_id = _get_cached_server_id(x_api_key)
    if not server_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if not bridge or bridge.closed:
        raise HTTPException(status_code=410, detail="Sesi terminal sudah ditutup")
    if bridge.server_id != server_id:
        raise HTTPException(status_code=403, detail="Akses ditolak: Sesi terminal bukan milik server ini")

    chunk = body.get("chunk", "")
    busy = body.get("busy", None)

    if chunk or busy is not None:
        clean_chunk = DA_QUERY_PATTERN.sub("", chunk) if chunk else ""
        if clean_chunk:
            bridge.append_output(clean_chunk)
            bridge.last_active = time.time()
        if bridge.browser_ws:
            payload = {"type": "stdout", "data": clean_chunk}
            if busy is not None:
                payload["busy"] = bool(busy)
            try:
                await bridge.browser_ws.send_text(json.dumps(payload))
            except Exception:
                bridge.browser_ws = None
                bridge.detached = True
                bridge.detached_at = time.time()

    return {"ok": True}


@router.post("/api/agent/terminal/{session_id}/close")
async def api_agent_terminal_close(
    session_id: str,
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen melaporkan bahwa proses shell lokal telah selesai/ditutup."""
    server_id = _get_cached_server_id(x_api_key)
    if not server_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if bridge:
        if bridge.server_id != server_id:
            raise HTTPException(status_code=403, detail="Akses ditolak: Sesi terminal bukan milik server ini")
        if bridge.browser_ws:
            try:
                await bridge.browser_ws.send_text(
                    json.dumps({"type": "stdout", "data": "\r\n\x1b[90m[Sesi shell selesai]\x1b[0m\r\n"})
                )
                await bridge.browser_ws.close()
            except Exception:
                pass
        await term_dispatcher.close_session(session_id)
    return {"ok": True}

