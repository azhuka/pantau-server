"""
Router Terminal PTY Web dan WebSocket Bridge Pantau Server.
Menyediakan terminal interaktif root berbasis xterm.js (browser)
dengan proteksi autentikasi bertingkat (step-up auth / sudo password + TOTP 2FA),
manajemen lease sewa akses, streaming WebSocket memory-only (zero DB overhead),
serta long-polling/streaming stdin/stdout untuk agen klien.
"""

import asyncio
from datetime import datetime
import json
import logging
import re
import secrets
import time

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

import security_auth
from core.database import SessionLocal, get_db
from core.security import (
    pwd_ctx,
    require_user,
    SESSION_COOKIE,
    _verify_csrf_header,
    _get_cached_server_id,
    is_terminal_unlocked,
    get_terminal_lease_remaining,
    set_terminal_unlock,
    revoke_terminal_unlock,
)
from core.utils import _clean_str, _clamp_int, hash_api_key
from models import Server, AppSession, User
from services.audit_service import _audit
from services.server_service import _server_stale

logger = logging.getLogger("pantau.terminal")

router = APIRouter(tags=["Terminal"])

# ---------------------------------------------------------------------------
# Pola escape sequence probe/query terminal (DA1, DA2, CPR, OSC color queries)
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


# ---------------------------------------------------------------------------
# OPERATOR STEP-UP AUTH & STATUS ENDPOINTS
# ---------------------------------------------------------------------------
@router.get("/api/servers/{sid}/terminal/status")
def api_terminal_status(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cek status izin dan sisa durasi sewa (lease) otentikasi terminal untuk server ini."""
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    allow_term = bool(getattr(server, "allow_web_terminal", 0))
    user_can = user.has_perm("can_terminal")
    remaining = get_terminal_lease_remaining(user.id, sid)
    unlocked = remaining > 0

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
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Buka kunci akses Web Terminal dengan tantangan kata sandi (sudo step-up auth) + TOTP."""
    _verify_csrf_header(request)

    if not user.has_perm("can_terminal"):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda tidak memiliki wewenang Terminal Shell Web",
        )

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    if getattr(server, "allow_web_terminal", 0) == 0:
        raise HTTPException(
            status_code=403,
            detail="Akses Web Terminal dinonaktifkan untuk server ini pada konfigurasi sistem",
        )

    password = _clean_str(body.get("password"), "", 256)
    totp_code = _clean_str(body.get("totp"), "", 10)
    duration_minutes = _clamp_int(body.get("duration_minutes"), 15, 5, 120)
    reason = _clean_str(body.get("reason"), "", 255)

    if not password:
        raise HTTPException(status_code=400, detail="Kata sandi akun pengguna diperlukan")

    if not pwd_ctx.verify(password, user.password_hash):
        _audit(db, user.username, "terminal_unlock_fail", f"{server.hostname} (kata sandi salah)", "gagal")
        db.commit()
        raise HTTPException(status_code=401, detail="Kata sandi akun salah. Akses terminal ditolak.")

    if user.totp_enabled and user.totp_secret:
        if not totp_code or not security_auth.verify_totp(user.totp_secret, totp_code):
            _audit(db, user.username, "terminal_unlock_fail", f"{server.hostname} (kode 2FA salah)", "gagal")
            db.commit()
            raise HTTPException(status_code=401, detail="Kode 2FA / TOTP tidak valid atau telah kedaluwarsa")

    set_terminal_unlock(user.id, sid, duration_minutes)
    audit_detail = f"{server.hostname} [durasi: {duration_minutes}m" + (f", alasan: {reason}]" if reason else "]")
    _audit(db, user.username, "terminal_unlock", audit_detail, "berhasil")
    db.commit()

    return {
        "ok": True,
        "remaining_seconds": duration_minutes * 60,
        "message": f"Kunci terminal berhasil dibuka ({duration_minutes} menit)",
    }


@router.post("/api/servers/{sid}/terminal/lock")
async def api_terminal_lock(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Kunci kembali akses terminal dan putus sesi aktif jika ada."""
    _verify_csrf_header(request)
    if not (user.is_master_admin() or user.has_perm("can_terminal")):
        raise HTTPException(
            status_code=403,
            detail="Akses ditolak: Anda tidak memiliki wewenang Terminal Shell Web",
        )

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    hostname = server.hostname if server else f"sid={sid}"

    revoke_terminal_unlock(user.id, sid)
    await term_dispatcher.close_session_by_server(sid)

    _audit(db, user.username, "terminal_lock", hostname, "berhasil")
    db.commit()

    return {"ok": True, "message": "Terminal berhasil dikunci"}


# ---------------------------------------------------------------------------
# BROWSER REALTIME WEBSOCKET ENDPOINT
# ---------------------------------------------------------------------------
@router.websocket("/ws/servers/{sid}/terminal")
async def ws_server_terminal(websocket: WebSocket, sid: int):
    """Koneksi terminal realtime browser WebSocket (xterm.js)."""
    cookie_sid = websocket.cookies.get(SESSION_COOKIE)
    if not cookie_sid:
        await websocket.close(code=4401)
        return

    db = SessionLocal()
    try:
        row = db.query(AppSession).filter(AppSession.sid == cookie_sid).first()
        if not row or (row.expires_at and row.expires_at < datetime.utcnow()):
            await websocket.close(code=4401)
            return
        user = db.query(User).filter(User.id == row.user_id).first()
        if not user or not user.has_perm("can_terminal"):
            await websocket.close(code=4403)
            return
        server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
        if not server:
            await websocket.close(code=4404)
            return
        if getattr(server, "allow_web_terminal", 0) == 0:
            await websocket.close(code=4403, reason="Web terminal disabled for this server")
            return
        if not is_terminal_unlocked(user.id, sid):
            await websocket.close(code=4403, reason="Terminal locked: step-up auth required")
            return
        if _server_stale(server):
            await websocket.close(code=4409)
            return
        hostname = server.hostname
        username = user.username
        user_id = user.id
    finally:
        db.close()

    await websocket.accept()

    bridge, is_reconnected = await term_dispatcher.open_or_attach_session(sid, websocket)

    db = SessionLocal()
    try:
        audit_action = "terminal_reconnect" if is_reconnected else "terminal_open"
        _audit(db, username, audit_action, f"{hostname}:{bridge.session_id}", "berhasil")
        db.commit()
    finally:
        db.close()

    if is_reconnected:
        buf = bridge.get_buffered_output()
        if buf:
            try:
                await websocket.send_text(json.dumps({"type": "stdout", "data": buf}))
            except Exception:
                pass

    try:
        while not bridge.closed:
            if not is_terminal_unlocked(user_id, sid):
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
            _audit(db, username, "terminal_detach", f"{hostname}:{bridge.session_id}", "selesai")
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
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if not bridge or bridge.closed:
        raise HTTPException(status_code=410, detail="Sesi terminal sudah ditutup")
    if bridge.server_id != server.id:
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
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    bridge = term_dispatcher.get_session(session_id)
    if bridge:
        if bridge.server_id != server.id:
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
