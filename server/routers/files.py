"""Remote File Manager API router (dispatches file operations to remote agent via long-poll RPC)."""

import asyncio
import base64
from datetime import datetime
import os
import secrets
import time
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

import security_auth
from core.database import get_db
from core.security import (
    get_file_manager_lease_remaining,
    is_file_manager_unlocked,
    revoke_file_manager_unlock,
    set_file_manager_unlock,
    verify_password,
)
from models.misc import AuditLog
from models.server import Server
from models.user import User
from routers.auth import get_current_user

router = APIRouter(prefix="/api/servers/{sid}/files", tags=["Files"])

DEFAULT_BOOKMARKS = [
    {"label": "/ Root", "path": "/", "title": "Root Filesystem (/)"},
    {"label": "/var/log", "path": "/var/log", "title": "System Logs (/var/log)"},
    {"label": "/etc", "path": "/etc", "title": "System Config (/etc)"},
    {"label": "/opt", "path": "/opt", "title": "Optional Software (/opt)"},
    {"label": "/var/www", "path": "/var/www", "title": "Web Data (/var/www)"},
    {"label": "/tmp", "path": "/tmp", "title": "Temporary Directory (/tmp)"},
]

PROTECTED_SYSTEM_PATHS = {
    "/", "/root", "/home", "/etc", "/var", "/usr", "/bin", "/sbin", "/boot",
    "/dev", "/sys", "/proc", "/lib", "/lib64", "/run",
}


class FileManagerDispatcher:
    """In-memory RPC dispatcher between control-plane API requests and remote agents."""

    def __init__(self) -> None:
        self._pending: dict[int, list[dict]] = {}
        self._events: dict[int, asyncio.Event] = {}
        self._waiters: dict[str, asyncio.Future] = {}
        self._lock: asyncio.Lock | None = None

    def _get_lock(self) -> asyncio.Lock:
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    async def get_or_create_event(self, server_id: int) -> asyncio.Event:
        async with self._get_lock():
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

        async with self._get_lock():
            self._pending.setdefault(server_id, []).append(req_item)
            if server_id not in self._events:
                self._events[server_id] = asyncio.Event()
            self._events[server_id].set()

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="Remote agent did not respond to file request (timeout). Ensure agent_pantau is running.",
            )
        finally:
            self._waiters.pop(req_id, None)
            async with self._get_lock():
                pending = self._pending.get(server_id)
                if pending:
                    self._pending[server_id] = [item for item in pending if item.get("id") != req_id]
                    if not self._pending[server_id] and server_id in self._events:
                        self._events[server_id].clear()

    async def pop_pending(self, server_id: int) -> list[dict]:
        async with self._get_lock():
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


def _check_access_and_online_server(
    user: User, sid: int, db: Session, require_unlock: bool = True
) -> Server:
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission for this server.")
    if not (user.is_master_admin or user.has_perm("can_file_manager")):
        raise HTTPException(status_code=403, detail="Access denied: File Manager permission (can_file_manager) is required.")
    if require_unlock and not is_file_manager_unlocked(user.id, sid):
        raise HTTPException(
            status_code=423,
            detail="File Manager session is locked. Please unlock with your password to continue.",
        )

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found.")

    now = datetime.utcnow()
    is_online = bool(server.last_seen and (now - server.last_seen).total_seconds() <= 60)
    if not is_online:
        raise HTTPException(
            status_code=409,
            detail="Server is offline. Remote file operations are disabled until agent_pantau reconnects.",
        )
    return server


def _record_file_audit(db: Session, sid: int, username: str, action: str, target: str, meta: str) -> None:
    try:
        db.add(AuditLog(
            server_id=sid,
            username=username,
            action=action,
            target=target[:255],
            result="success",
            meta=meta,
            created_at=datetime.utcnow(),
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise


@router.get("/status")
def get_file_manager_status(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Check File Manager permission and ephemeral step-up auth lease status."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Access denied")
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    user_can = bool(user.is_master_admin or user.has_perm("can_file_manager"))
    remaining = get_file_manager_lease_remaining(user.id, sid)
    return {
        "server_id": sid,
        "can_file_manager": user_can,
        "is_unlocked": remaining > 0,
        "remaining_seconds": remaining,
        "user_has_totp": bool(user.totp_enabled and user.totp_secret),
    }


@router.post("/unlock")
def unlock_file_manager(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Unlock Remote File Manager access via step-up password + TOTP verification."""
    if not (user.is_master_admin or user.has_perm("can_file_manager")):
        raise HTTPException(status_code=403, detail="Access denied: File Manager permission is required")
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Access denied")

    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    password = str(body.get("password") or "").strip()
    totp_code = str(body.get("totp") or "").strip()
    duration_minutes = max(5, min(120, int(body.get("duration_minutes") or 15)))
    reason = str(body.get("reason") or "").strip()[:255]

    if not password:
        raise HTTPException(status_code=400, detail="User account password is required")

    if not verify_password(password, user.password_hash):
        db.add(AuditLog(
            server_id=sid,
            username=user.username,
            action="file_manager_unlock_fail",
            target=server.hostname,
            result="failed",
            meta="Invalid password during File Manager unlock challenge",
            created_at=datetime.utcnow(),
        ))
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid account password. File Manager access denied.")

    if user.totp_enabled and user.totp_secret:
        if not totp_code or not security_auth.verify_totp(user.totp_secret, totp_code):
            db.add(AuditLog(
                server_id=sid,
                username=user.username,
                action="file_manager_unlock_fail",
                target=server.hostname,
                result="failed",
                meta="Invalid 2FA code during File Manager unlock challenge",
                created_at=datetime.utcnow(),
            ))
            db.commit()
            raise HTTPException(status_code=401, detail="Invalid or expired 2FA / TOTP code")

    set_file_manager_unlock(user.id, sid, duration_minutes)
    meta = f"Duration: {duration_minutes}m, reason: {reason}" if reason else f"Duration: {duration_minutes}m"
    _record_file_audit(db, sid, user.username, "file_manager_unlock", server.hostname, meta)
    return {
        "ok": True,
        "remaining_seconds": duration_minutes * 60,
        "message": f"File Manager unlocked for {duration_minutes} minutes",
    }


@router.post("/lock")
def lock_file_manager(
    sid: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Immediately lock Remote File Manager access and revoke the active lease."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Access denied")
    revoke_file_manager_unlock(user.id, sid)
    server = db.query(Server).filter(Server.id == sid, Server.is_active == 1).first()
    hostname = server.hostname if server else f"sid={sid}"
    _record_file_audit(db, sid, user.username, "file_manager_lock", hostname, "File Manager session locked by operator")
    return {"ok": True, "message": "File Manager locked successfully"}


@router.get("")
async def list_server_files(
    sid: int,
    path: str = "/",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List directory contents on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    res = await file_dispatcher.dispatch(sid, "ls", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to read remote directory"))
    if not res.get("path"):
        res["path"] = res.get("cwd") or path
    if "items" not in res and "entries" in res:
        res["items"] = res["entries"]
    if "bookmarks" not in res:
        res["bookmarks"] = DEFAULT_BOOKMARKS
    return res


@router.get("/content")
async def read_file_content(
    sid: int,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Read text file contents on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    res = await file_dispatcher.dispatch(sid, "cat", {"path": path})
    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=res.get("error", "Failed to read remote file"),
            headers={"X-Is-Binary": "1" if res.get("is_binary") else "0"},
        )
    return res


@router.post("/save")
async def save_file_content(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save text file contents on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    path = str(body.get("path") or "").strip()
    content = str(body.get("content") or "")
    make_backup = bool(body.get("make_backup", True))
    if not path:
        raise HTTPException(status_code=400, detail="File path is required")

    res = await file_dispatcher.dispatch(
        sid, "write", {"path": path, "content": content, "make_backup": make_backup}
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to save remote file"))

    _record_file_audit(db, sid, user.username, "file_save", path, f"Saved {len(content)} bytes via Remote File Manager")
    return {"ok": True, "path": path, "size": len(content), "backup_created": res.get("backup_created")}


@router.post("/touch")
async def touch_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create an empty file on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    path = str(body.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="File path is required")

    res = await file_dispatcher.dispatch(sid, "touch", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to create remote file"))

    _record_file_audit(db, sid, user.username, "file_touch", path, "Created empty file via Remote File Manager")
    return {"ok": True, "path": path}


@router.post("/mkdir")
async def mkdir_server_dir(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a directory on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    path = str(body.get("path") or "").strip()
    mode = str(body.get("mode") or "0755").strip()
    if not path:
        raise HTTPException(status_code=400, detail="Directory path is required")

    res = await file_dispatcher.dispatch(sid, "mkdir", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to create remote directory"))

    _record_file_audit(db, sid, user.username, "file_mkdir", path, "Created directory via Remote File Manager")
    return {"ok": True, "path": path}


@router.post("/rm")
async def remove_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a file or directory on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    path = str(body.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")
    if os.path.normpath(path) in PROTECTED_SYSTEM_PATHS:
        raise HTTPException(status_code=403, detail="Protected critical system directory cannot be deleted.")

    res = await file_dispatcher.dispatch(sid, "rm", {"path": path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to delete remote path"))

    _record_file_audit(db, sid, user.username, "file_rm", path, "Deleted via Remote File Manager")
    return {"ok": True, "path": path}


@router.get("/download")
async def download_server_file(
    sid: int,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Download a file from the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    res = await file_dispatcher.dispatch(sid, "read_binary", {"path": path}, timeout=35.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to read remote file"))

    try:
        raw_bytes = base64.b64decode(res.get("data_b64", ""))
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to decode binary file data from remote agent")

    filename = os.path.basename(path) or "download.bin"
    safe_name = quote(filename)
    return Response(
        content=raw_bytes,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename=\"{safe_name}\"; filename*=UTF-8''{safe_name}",
            "Content-Length": str(len(raw_bytes)),
        },
    )


@router.post("/rename")
async def rename_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a file or directory on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    old_path = str(body.get("old_path") or "").strip()
    new_path = str(body.get("new_path") or "").strip()
    if not old_path or not new_path:
        raise HTTPException(status_code=400, detail="Both old_path and new_path are required")
    if os.path.normpath(old_path) in PROTECTED_SYSTEM_PATHS:
        raise HTTPException(status_code=403, detail="Protected critical system directory cannot be renamed.")

    res = await file_dispatcher.dispatch(sid, "rename", {"old_path": old_path, "new_path": new_path})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to rename remote path"))

    _record_file_audit(db, sid, user.username, "file_rename", f"{old_path} -> {new_path}", "Renamed via Remote File Manager")
    return {"ok": True, "old_path": old_path, "new_path": new_path}


@router.post("/chmod")
async def chmod_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change file permissions on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    path = str(body.get("path") or "").strip()
    mode = str(body.get("mode") or "").strip()
    if not path or not mode:
        raise HTTPException(status_code=400, detail="Path and octal mode are required")

    res = await file_dispatcher.dispatch(sid, "chmod", {"path": path, "mode": mode})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to change permissions"))

    _record_file_audit(db, sid, user.username, "file_chmod", f"{path} ({mode})", "Changed permissions via Remote File Manager")
    return {"ok": True, "path": path, "mode": mode}


@router.post("/chown")
async def chown_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change file ownership (user/group) on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    path = str(body.get("path") or "").strip()
    owner = str(body.get("owner") or "").strip()
    group = str(body.get("group") or "").strip() or None
    if not path or not owner:
        raise HTTPException(status_code=400, detail="Path and owner are required")
    if os.path.normpath(path) in PROTECTED_SYSTEM_PATHS:
        raise HTTPException(status_code=403, detail="Protected critical system directory ownership cannot be changed.")

    res = await file_dispatcher.dispatch(sid, "chown", {"path": path, "owner": owner, "group": group})
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to change ownership"))

    target_owner = f"{owner}:{group}" if group else owner
    _record_file_audit(db, sid, user.username, "file_chown", f"{path} ({target_owner})", "Changed ownership via Remote File Manager")
    return {"ok": True, "path": path, "owner": owner, "group": group}


@router.post("/batch-rm")
async def batch_remove_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch delete files or directories on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    paths = body.get("paths") or []
    if not paths or not isinstance(paths, list):
        raise HTTPException(status_code=400, detail="Paths list cannot be empty")
    clean_paths = [str(p).strip() for p in paths if str(p).strip()]
    if not clean_paths:
        raise HTTPException(status_code=400, detail="Paths list cannot be empty")
    for p in clean_paths:
        if os.path.normpath(p) in PROTECTED_SYSTEM_PATHS:
            raise HTTPException(status_code=403, detail=f"Protected critical system directory cannot be deleted: {p}")

    res = await file_dispatcher.dispatch(sid, "batch_rm", {"paths": clean_paths}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to batch delete items"))

    _record_file_audit(db, sid, user.username, "file_batch_rm", f"{len(clean_paths)} items", f"Deleted {clean_paths}")
    return res


@router.post("/batch-chmod")
async def batch_chmod_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Batch change permissions on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    paths = body.get("paths") or []
    mode = str(body.get("mode") or "").strip()
    if not paths or not isinstance(paths, list) or not mode:
        raise HTTPException(status_code=400, detail="Paths list and octal mode are required")
    clean_paths = [str(p).strip() for p in paths if str(p).strip()]
    if not clean_paths:
        raise HTTPException(status_code=400, detail="Paths list cannot be empty")

    res = await file_dispatcher.dispatch(sid, "batch_chmod", {"paths": clean_paths, "mode": mode}, timeout=60.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to batch change permissions"))

    _record_file_audit(db, sid, user.username, "file_batch_chmod", f"{len(clean_paths)} items ({mode})", f"Chmod {mode} on {clean_paths}")
    return res


@router.post("/copy")
async def copy_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Copy files or directories on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    sources = body.get("sources") or []
    destination = str(body.get("destination") or "").strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sources and destination are required")

    res = await file_dispatcher.dispatch(
        sid, "copy", {"sources": sources, "destination": destination}, timeout=60.0
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to copy remote items"))

    _record_file_audit(db, sid, user.username, "file_copy", f"{len(sources)} items -> {destination}", f"Copied {sources}")
    return res


@router.post("/move")
async def move_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Move files or directories on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    sources = body.get("sources") or []
    destination = str(body.get("destination") or "").strip()
    if not sources or not isinstance(sources, list) or not destination:
        raise HTTPException(status_code=400, detail="Sources and destination are required")
    for s in sources:
        if os.path.normpath(str(s)) in PROTECTED_SYSTEM_PATHS:
            raise HTTPException(status_code=403, detail="Protected critical system directory cannot be moved.")

    res = await file_dispatcher.dispatch(
        sid, "move", {"sources": sources, "destination": destination}, timeout=60.0
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to move remote items"))

    _record_file_audit(db, sid, user.username, "file_move", f"{len(sources)} items -> {destination}", f"Moved {sources}")
    return res


@router.post("/duplicate")
async def duplicate_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Duplicate a file or directory on the remote target host via agent RPC."""
    _check_access_and_online_server(user, sid, db)
    source = str(body.get("source") or "").strip()
    raw_target = str(body.get("target_name") or "").strip()
    target_name = os.path.basename(raw_target) if raw_target else ""
    if not source:
        raise HTTPException(status_code=400, detail="Source path is required")
    if os.path.normpath(source) in PROTECTED_SYSTEM_PATHS:
        raise HTTPException(status_code=403, detail="Protected critical system directory cannot be duplicated.")

    res = await file_dispatcher.dispatch(
        sid, "duplicate", {"source_path": source, "target_name": target_name}, timeout=60.0
    )
    if not res.get("ok"):
        err_msg = res.get("error", "Failed to duplicate item")
        status_c = 400
        if "insufficient" in err_msg.lower() or "tidak mencukupi" in err_msg.lower():
            status_c = 507
        elif "exists" in err_msg.lower() or "sudah ada" in err_msg.lower():
            status_c = 409
        raise HTTPException(status_code=status_c, detail=err_msg)

    _record_file_audit(
        db, sid, user.username, "file_duplicate", f"{source} -> {res.get('target_name', target_name)}", "Duplicated via Remote File Manager"
    )
    return res


@router.post("/upload")
async def upload_server_file(
    sid: int,
    destination: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a file to the remote target host via agent RPC (max 50 MB)."""
    _check_access_and_online_server(user, sid, db)
    raw = await file.read()
    if len(raw) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 50 MB)")

    filename = os.path.basename(file.filename or "uploaded_file")
    dest_clean = destination.rstrip("/") or "/"
    target_path = f"{dest_clean}/{filename}" if dest_clean != "/" else f"/{filename}"
    b64_data = base64.b64encode(raw).decode("ascii")

    res = await file_dispatcher.dispatch(
        sid, "write_binary", {"path": target_path, "data_b64": b64_data}, timeout=35.0
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to upload file to remote host"))

    _record_file_audit(db, sid, user.username, "file_upload", f"{target_path} ({len(raw)} bytes)", "Uploaded via Remote File Manager")
    return {"ok": True, "path": target_path, "size": len(raw)}


@router.get("/storage-triage")
async def storage_triage_server(
    sid: int,
    mount: str = "/",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Inspect large files, deleted-open-file handles, and runaway logs on the remote host."""
    _check_access_and_online_server(user, sid, db, require_unlock=False)
    mount_clean = (mount or "/").strip() or "/"
    res = await file_dispatcher.dispatch(sid, "storage_triage", {"mount_path": mount_clean}, timeout=40.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Storage analysis failed"))
    return res


@router.post("/truncate-log")
async def truncate_remote_log(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Safely truncate a runaway log file to zero bytes on the remote host."""
    _check_access_and_online_server(user, sid, db, require_unlock=False)
    path = str(body.get("path") or "").strip()
    if not path:
        raise HTTPException(status_code=400, detail="Log file path is required")
    res = await file_dispatcher.dispatch(sid, "truncate_log", {"path": path}, timeout=15.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to truncate log file"))
    _record_file_audit(db, sid, user.username, "file_truncate_log", path, "Truncated runaway log via Storage Analysis")
    return res


@router.post("/storage-reclaim")
async def reclaim_remote_storage(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Reclaim disk space on the remote host (journal, apt_cache, or rotated_logs)."""
    _check_access_and_online_server(user, sid, db, require_unlock=False)
    target = str(body.get("target") or "").strip()
    if target not in ("journal", "apt_cache", "rotated_logs"):
        raise HTTPException(status_code=400, detail="Invalid reclaim target (must be journal, apt_cache, or rotated_logs)")
    res = await file_dispatcher.dispatch(sid, "storage_reclaim", {"target": target}, timeout=30.0)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Failed to reclaim storage"))
    _record_file_audit(db, sid, user.username, "storage_reclaim", f"target={target}", res.get("message", "Reclaimed storage"))
    return res
