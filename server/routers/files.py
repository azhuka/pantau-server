import os
import stat
import pwd
import grp
import shutil
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Body, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from core.database import get_db
from routers.auth import get_current_user
from models.user import User
from models.server import Server
from models.misc import AuditLog

router = APIRouter(prefix="/api/servers/{sid}/files", tags=["Files"])

def check_file_manager_access(user: User, sid: int) -> None:
    """Validasi otentikasi node scope dan izin RBAC can_file_manager."""
    if not user.can_access_server(sid):
        raise HTTPException(status_code=403, detail="Access denied: You do not have permission for this server.")
    if not user.has_perm("can_file_manager"):
        raise HTTPException(status_code=403, detail="Access denied: File Manager permission (can_file_manager) is required.")

PROTECTED_SYSTEM_PATHS = {
    "/", "/root", "/home", "/etc", "/var", "/usr", "/bin", "/sbin", "/boot",
    "/dev", "/sys", "/proc", "/lib", "/lib64", "/run"
}


@router.get("")
def list_server_files(
    sid: int,
    path: str = "/home/bos",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Daftar berkas dan direktori pada server."""
    check_file_manager_access(user, sid)

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
                        "path": entry.path,
                        "is_dir": is_dir,
                        "size": st.st_size if not is_dir else 0,
                        "size_human": f"{st.st_size / (1024*1024):.2f} MB" if st.st_size > 1024*1024 else f"{st.st_size / 1024:.1f} KB" if not is_dir else "-",
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


@router.get("/content")
def read_file_content(
    sid: int,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Membaca isi berkas teks (maksimal 2MB)."""
    check_file_manager_access(user, sid)

    target_path = os.path.abspath(path)
    if not os.path.isfile(target_path):
        raise HTTPException(status_code=404, detail="File not found")

    if not os.access(target_path, os.R_OK):
        raise HTTPException(status_code=403, detail="Permission denied reading file")

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


@router.post("/save")
def save_file_content(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Menyimpan modifikasi isi berkas."""
    check_file_manager_access(user, sid)

    path = body.get("path")
    content = body.get("content", "")
    make_backup = bool(body.get("make_backup", True))
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")

    target_path = os.path.abspath(path)
    try:
        backup_created = None
        if make_backup and os.path.exists(target_path):
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


@router.post("/touch")
def touch_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Membuat file kosong baru."""
    check_file_manager_access(user, sid)

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


@router.post("/mkdir")
def mkdir_server_dir(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Membuat direktori baru."""
    check_file_manager_access(user, sid)

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


@router.post("/rm")
def remove_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Menghapus file atau direktori dengan proteksi path vital."""
    check_file_manager_access(user, sid)

    path = body.get("path")
    if not path:
        raise HTTPException(status_code=400, detail="Path is required")

    target_path = os.path.abspath(path)
    if target_path in PROTECTED_SYSTEM_PATHS:
        raise HTTPException(status_code=400, detail="Protected system path cannot be deleted")

    if not os.path.exists(target_path):
        raise HTTPException(status_code=404, detail="File or directory not found")

    try:
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


@router.get("/download")
def download_server_file(
    sid: int,
    path: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengunduh berkas dari server."""
    check_file_manager_access(user, sid)

    target_path = os.path.abspath(path)
    if not (os.path.exists(target_path) and os.path.isfile(target_path)):
        raise HTTPException(status_code=404, detail="File not found")

    if not os.access(target_path, os.R_OK):
        raise HTTPException(status_code=403, detail="Permission denied reading file")

    filename = os.path.basename(target_path)
    return FileResponse(target_path, filename=filename)


@router.post("/rename")
def rename_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengganti nama berkas atau direktori."""
    check_file_manager_access(user, sid)

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


@router.post("/chmod")
def chmod_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Mengubah izin berkas atau direktori (mode oktal, misal '0644' atau '0755')."""
    check_file_manager_access(user, sid)

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


@router.post("/copy")
def copy_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Menyalin berkas atau direktori."""
    check_file_manager_access(user, sid)

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


@router.post("/move")
def move_server_files(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Memindahkan berkas atau direktori (cut-paste)."""
    check_file_manager_access(user, sid)

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


@router.post("/duplicate")
def duplicate_server_file(
    sid: int,
    body: dict = Body(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Duplikasi kloning lokal berkas/folder pada server."""
    check_file_manager_access(user, sid)

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


@router.post("/upload")
async def upload_server_file(
    sid: int,
    destination: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Unggah berkas ke server."""
    check_file_manager_access(user, sid)

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
