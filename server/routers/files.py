"""
Router Manajemen Berkas (File Manager) Pantau Server.
Menyediakan antarmuka penjelajah direktori jarak jauh, inspeksi berkas,
editor teks terintegrasi, unggah/unduh berkas biner, manipulasi berkas (mkdir, touch, rm, rename, chmod, chown),
operasi batch (batch-rm, batch-chmod), perlindungan sewa otentikasi (step-up auth),
serta RPC dispatch long-poll ke Agen Pantau klien.
"""

import asyncio
import base64
import json
import logging
import os
import secrets
import time
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

import security_auth
from core.database import get_db
from core.security import (
    pwd_ctx,
    get_current_user,
    require_user,
    require_file_manager,
    _verify_csrf_header,
    _get_cached_server_id,
    get_file_manager_lease_remaining,
    set_file_manager_unlock,
    revoke_file_manager_unlock,
)
from core.templates import tpl
from core.utils import _clean_str, _clamp_int, hash_api_key
from models import Server, User
from services.audit_service import _audit
from services.server_service import _server_stale

logger = logging.getLogger("pantau.files")

router = APIRouter(tags=["Files"])


# ---------------------------------------------------------------------------
# FILE MANAGER DISPATCHER (In-Memory RPC ke Agen via HTTP Long-Poll)
# ---------------------------------------------------------------------------
class FileManagerDispatcher:
    def __init__(self):
        self._pending: dict[int, list[dict]] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._waiters: dict[str, asyncio.Future] = {}
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_or_create_event(self, server_id: int) -> asyncio.Event:
        lock = self._get_lock()
        async with lock:
            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            return self._events[server_id]

    async def dispatch(self, server_id: int, action: str, params: dict, timeout: float = 25.0) -> dict:
        req_id = secrets.token_hex(16)
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        self._waiters[req_id] = fut

        req_item = {
            "id": req_id,
            "action": action,
            "params": params,
            "created_at": time.time(),
        }

        lock = self._get_lock()
        async with lock:
            if server_id not in self._pending:
                self._pending[server_id] = []
            self._pending[server_id].append(req_item)
            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            self._events[server_id].set()

        try:
            result = await asyncio.wait_for(fut, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Agen server tidak merespons permintaan berkas (timeout). Pastikan service agent_pantau aktif.",
            )
        finally:
            self._waiters.pop(req_id, None)

    async def pop_pending(self, server_id: int) -> list[dict]:
        lock = self._get_lock()
        async with lock:
            reqs = self._pending.pop(server_id, [])
            if server_id in self._events:
                self._events[server_id].clear()
            return reqs

    def resolve(self, req_id: str, result: dict) -> bool:
        fut = self._waiters.get(req_id)
        if fut and not fut.done():
            fut.set_result(result)
            return True
        return False


file_dispatcher = FileManagerDispatcher()


def _get_active_online_server(db: Session, sid: int) -> Server:
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")
    if _server_stale(server):
        raise HTTPException(
            status_code=409,
            detail="Server sedang offline. Operasi berkas dinonaktifkan sampai service agent_pantau kembali aktif.",
        )
    return server


# ---------------------------------------------------------------------------
# UI & STEP-UP AUTH ENDPOINTS
# ---------------------------------------------------------------------------
@router.get("/servers/{sid}/files", response_class=HTMLResponse)
def page_server_files(request: Request, sid: int, db: Session = Depends(get_db)):
    """Halaman antarmuka dedicated File Manager untuk server klien."""
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if not user.has_perm("can_file_manager"):
        raise HTTPException(status_code=403, detail="Akses ditolak: Anda tidak memiliki wewenang File Manager")
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    remaining = get_file_manager_lease_remaining(user.id, sid)
    return tpl(
        request,
        "file_manager.html",
        {
            "server": server,
            "user": user,
            "is_online": not _server_stale(server),
            "is_unlocked": remaining > 0,
            "remaining_seconds": remaining,
            "user_has_totp": bool(user.totp_enabled and user.totp_secret),
        },
    )


@router.get("/api/servers/{sid}/files/status")
def api_server_files_status(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Cek status izin dan sisa durasi sewa (lease) otentikasi File Manager untuk server ini."""
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    user_can = user.has_perm("can_file_manager")
    remaining = get_file_manager_lease_remaining(user.id, sid)
    unlocked = remaining > 0

    return {
        "server_id": sid,
        "can_file_manager": user_can,
        "is_unlocked": unlocked,
        "remaining_seconds": remaining,
        "user_has_totp": bool(user.totp_enabled and user.totp_secret),
    }


@router.post("/api/servers/{sid}/files/unlock")
def api_server_files_unlock(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Buka kunci akses File Manager dengan tantangan kata sandi (sudo step-up auth) + TOTP."""
    _verify_csrf_header(request)

    if not user.has_perm("can_file_manager"):
        raise HTTPException(status_code=403, detail="Akses ditolak: Anda tidak memiliki wewenang File Manager")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server tidak ditemukan")

    password = _clean_str(body.get("password"), "", 256)
    totp_code = _clean_str(body.get("totp"), "", 10)
    duration_minutes = _clamp_int(body.get("duration_minutes"), 15, 5, 120)
    reason = _clean_str(body.get("reason"), "", 255)

    if not password:
        raise HTTPException(status_code=400, detail="Kata sandi akun pengguna diperlukan")

    if not pwd_ctx.verify(password, user.password_hash):
        _audit(
            db,
            user.username,
            "file_manager_unlock_fail",
            f"{server.hostname} (kata sandi salah)",
            "gagal",
            server_id=sid,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Kata sandi akun salah. Akses File Manager ditolak.")

    if user.totp_enabled and user.totp_secret:
        if not totp_code or not security_auth.verify_totp(user.totp_secret, totp_code):
            _audit(
                db,
                user.username,
                "file_manager_unlock_fail",
                f"{server.hostname} (kode 2FA salah)",
                "gagal",
                server_id=sid,
            )
            db.commit()
            raise HTTPException(status_code=401, detail="Kode 2FA / TOTP tidak valid atau telah kedaluwarsa")

    set_file_manager_unlock(user.id, sid, duration_minutes)
    audit_detail = f"{server.hostname} [durasi: {duration_minutes}m" + (f", alasan: {reason}]" if reason else "]")
    _audit(db, user.username, "file_manager_unlock", audit_detail, "berhasil", server_id=sid)
    db.commit()

    return {
        "ok": True,
        "remaining_seconds": duration_minutes * 60,
        "message": f"Kunci File Manager berhasil dibuka ({duration_minutes} menit)",
    }


@router.post("/api/servers/{sid}/files/lock")
def api_server_files_lock(
    sid: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Kunci kembali sesi File Manager untuk server ini."""
    _verify_csrf_header(request)
    revoke_file_manager_unlock(user.id, sid)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    hostname = server.hostname if server else f"sid={sid}"
    _audit(db, user.username, "file_manager_lock", hostname, "berhasil", server_id=sid)
    db.commit()
    return {"ok": True, "message": "Sesi File Manager telah dikunci"}


# ---------------------------------------------------------------------------
# REMOTE FILE OPERATIONS (OPERATOR)
# ---------------------------------------------------------------------------
@router.get("/api/servers/{sid}/files/ls")
async def api_server_files_ls(
    sid: int,
    path: str = "/",
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    server = _get_active_online_server(db, sid)
    res = await file_dispatcher.dispatch(sid, "ls", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membaca direktori"))
    return res


@router.get("/api/servers/{sid}/files/cat")
async def api_server_files_cat(
    sid: int,
    path: str,
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    server = _get_active_online_server(db, sid)
    res = await file_dispatcher.dispatch(sid, "cat", {"path": path})
    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=res.get("error", "Gagal membaca file"),
            headers={"X-Is-Binary": "1" if res.get("is_binary") else "0"},
        )
    return res


@router.post("/api/servers/{sid}/files/write")
async def api_server_files_write(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    content = str(body.get("content", ""))
    make_backup = bool(body.get("make_backup", True))

    if not path:
        raise HTTPException(status_code=400, detail="Path file tidak boleh kosong")

    res = await file_dispatcher.dispatch(
        sid, "write", {"path": path, "content": content, "make_backup": make_backup}
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menyimpan file"))

    _audit(
        db,
        user.username,
        "file_save",
        f"{server.hostname}:{path}",
        "berhasil",
        {"size": len(content), "backup": res.get("backup_created")},
        server_id=sid,
    )
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/mkdir")
async def api_server_files_mkdir(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    mode = str(body.get("mode", "0755")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "mkdir", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membuat direktori"))

    _audit(db, user.username, "file_mkdir", f"{server.hostname}:{path}", "berhasil", server_id=sid)
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/touch")
async def api_server_files_touch(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "touch", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membuat file"))

    _audit(db, user.username, "file_touch", f"{server.hostname}:{path}", "berhasil", server_id=sid)
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/rm")
async def api_server_files_rm(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "rm", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menghapus"))

    _audit(db, user.username, "file_rm", f"{server.hostname}:{path}", "berhasil", server_id=sid)
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/rename")
async def api_server_files_rename(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    old_path = str(body.get("old_path", "") or body.get("src", "")).strip()
    new_path = str(body.get("new_path", "") or body.get("dst", "")).strip()
    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="Path asal dan tujuan tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "rename", {"old_path": old_path, "new_path": new_path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengganti nama file/folder"))

    _audit(
        db,
        user.username,
        "file_rename",
        f"{server.hostname}:{old_path} -> {new_path}",
        "berhasil",
        server_id=sid,
    )
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/chmod")
async def api_server_files_chmod(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    mode = str(body.get("mode", "")).strip()
    res = await file_dispatcher.dispatch(sid, "chmod", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah izin"))

    _audit(
        db,
        user.username,
        "file_chmod",
        f"{server.hostname}:{path}",
        f"mode={mode}",
        server_id=sid,
    )
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/chown")
async def api_server_files_chown(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    path = str(body.get("path", "")).strip()
    owner = str(body.get("owner", "")).strip()
    group = str(body.get("group", "")).strip() or None
    res = await file_dispatcher.dispatch(sid, "chown", {"path": path, "owner": owner, "group": group})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah kepemilikan"))

    _audit(
        db,
        user.username,
        "file_chown",
        f"{server.hostname}:{path}",
        f"owner={owner}:{group}",
        server_id=sid,
    )
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/upload")
async def api_server_files_upload(
    sid: int,
    request: Request,
    destination: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ukuran file terlalu besar (maksimal 50 MB)")

    filename = os.path.basename(file.filename or "uploaded_file")
    target_path = os.path.join(destination.rstrip("/"), filename)
    b64_data = base64.b64encode(raw).decode("ascii")

    res = await file_dispatcher.dispatch(
        sid, "write_binary", {"path": target_path, "data_b64": b64_data}, timeout=35.0
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengunggah file"))

    _audit(
        db,
        user.username,
        "file_upload",
        f"{server.hostname}:{target_path}",
        f"{len(raw)} bytes",
        server_id=sid,
    )
    db.commit()
    return {"ok": True, "path": target_path, "size": len(raw)}


@router.get("/api/servers/{sid}/files/download")
async def api_server_files_download(
    sid: int,
    path: str,
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    server = _get_active_online_server(db, sid)
    res = await file_dispatcher.dispatch(sid, "read_binary", {"path": path}, timeout=35.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal membaca file"))

    b64_data = res.get("data_b64", "")
    try:
        raw_bytes = base64.b64decode(b64_data)
    except Exception:
        raise HTTPException(status_code=500, detail="Gagal membaca data file dari agen")

    filename = os.path.basename(path)
    safe_name = quote(filename)
    return Response(
        content=raw_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}"; filename*=UTF-8\'\'{safe_name}',
            "Content-Length": str(len(raw_bytes)),
        },
    )


@router.post("/api/servers/{sid}/files/copy")
async def api_server_files_copy(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    sources = body.get("sources", [])
    destination = str(body.get("destination", "")).strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sumber dan tujuan harus ditentukan")

    res = await file_dispatcher.dispatch(
        sid, "copy", {"sources": sources, "destination": destination}, timeout=60.0
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menyalin file/folder"))

    _audit(
        db,
        user.username,
        "file_copy",
        f"{server.hostname}: {len(sources)} items -> {destination}",
        "berhasil",
        server_id=sid,
    )
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/move")
async def api_server_files_move(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    sources = body.get("sources", [])
    destination = str(body.get("destination", "")).strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sumber dan tujuan harus ditentukan")

    res = await file_dispatcher.dispatch(
        sid, "move", {"sources": sources, "destination": destination}, timeout=60.0
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal memindahkan file/folder"))

    _audit(
        db,
        user.username,
        "file_move",
        f"{server.hostname}: {len(sources)} items -> {destination}",
        "berhasil",
        server_id=sid,
    )
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/batch-rm")
async def api_server_files_batch_rm(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    paths = body.get("paths", [])
    if not paths or not isinstance(paths, list):
        raise HTTPException(status_code=400, detail="Daftar file/folder yang akan dihapus tidak boleh kosong")

    res = await file_dispatcher.dispatch(sid, "batch_rm", {"paths": paths}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal menghapus beberapa item"))

    _audit(
        db,
        user.username,
        "file_batch_rm",
        f"{server.hostname}: {len(paths)} items",
        "berhasil",
        server_id=sid,
    )
    db.commit()
    return res


@router.post("/api/servers/{sid}/files/batch-chmod")
async def api_server_files_batch_chmod(
    sid: int,
    request: Request,
    body: dict = Body(...),
    user: User = Depends(require_file_manager),
    db: Session = Depends(get_db),
):
    _verify_csrf_header(request)
    server = _get_active_online_server(db, sid)

    paths = body.get("paths", [])
    mode = str(body.get("mode", "")).strip()
    if not paths or not isinstance(paths, list) or not mode:
        raise HTTPException(status_code=400, detail="Daftar file/folder dan mode izin harus ditentukan")

    res = await file_dispatcher.dispatch(sid, "batch_chmod", {"paths": paths, "mode": mode}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Gagal mengubah izin beberapa item"))

    _audit(
        db,
        user.username,
        "file_batch_chmod",
        f"{server.hostname}: {len(paths)} items, mode={mode}",
        "berhasil",
        server_id=sid,
    )
    db.commit()
    return res


# ---------------------------------------------------------------------------
# AGENT FILE RPC POLLING & RESULT
# ---------------------------------------------------------------------------
@router.get("/api/agent/file-requests")
async def api_agent_file_requests(
    x_api_key: str = Header(alias="X-Api-Key"),
):
    """Agen mem-poll permintaan berkas secara cepat/long-poll (tahan hingga 15 dtk)."""
    server_id = _get_cached_server_id(x_api_key)
    if not server_id:
        raise HTTPException(status_code=401, detail="Invalid API key")

    reqs = await file_dispatcher.pop_pending(server_id)
    if reqs:
        return {"requests": reqs}

    event = await file_dispatcher.get_or_create_event(server_id)
    try:
        await asyncio.wait_for(event.wait(), timeout=15.0)
    except asyncio.TimeoutError:
        pass

    reqs = await file_dispatcher.pop_pending(server_id)
    return {"requests": reqs}


@router.post("/api/agent/file-requests/{req_id}/result")
async def api_agent_file_result(
    req_id: str,
    body: dict = Body(...),
    x_api_key: str = Header(alias="X-Api-Key"),
    db: Session = Depends(get_db),
):
    """Agen melaporkan hasil eksekusi operasi berkas."""
    server = db.query(Server).filter(Server.api_key == hash_api_key(x_api_key)).first()
    if not server:
        raise HTTPException(status_code=401, detail="Invalid API key")

    ok = file_dispatcher.resolve(req_id, body)
    return {"ok": ok}
