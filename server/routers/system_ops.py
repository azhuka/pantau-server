"""
Router Operasi Sistem & Mitigasi Server Pantau.
Menangani kontrol firewall host (enable/disable/reload/block/unblock),
manajemen proses (kill process / sinyal POSIX), reboot & poweroff OS dengan verifikasi sudo,
manajemen akun pengguna Linux jarak jauh (create/lock/unlock/delete/terminate-session),
pengelolaan cron job host (add/toggle/delete/run), aturan port, path sertifikat SSL,
serta distribusi & pembaruan Agen Pantau (Push OTA, latest-code, wrapper binary).
"""

from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from config import settings
from core.database import get_db
from core.security import (
    get_current_user,
    _verify_csrf_form,
    _verify_operator_password,
)
from models import (
    Server,
    ServerExtras,
    Command,
    ServerProblem,
)
from services.audit_service import _audit
from services.problem_service import _parse_extras_security
from services.server_service import _check_server_online

logger = logging.getLogger("pantau.system_ops")

router = APIRouter(tags=["System Operations"])


def _enqueue_mitigation(db: Session, sid: int, action: str, params: dict | None = None, issued_by=None) -> None:
    """Antrekan command mitigasi atau server action tanpa service terkait."""
    params_str = json.dumps(params) if params else None
    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == action,
            Command.status == "pending",
            Command.params == params_str,
        )
        .first()
    )
    if not existing:
        db.add(
            Command(
                server_id=sid,
                service_id=None,
                action=action,
                params=params_str,
                status="pending",
                issued_by=issued_by,
            )
        )
        db.commit()


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
                logger.warning("[AGENT CODE] Gagal membaca %s: %s", p, e)
    raise HTTPException(status_code=404, detail="File agen tidak ditemukan di dashboard")


# ---------------------------------------------------------------------------
# FIREWALL OPERATIONS
# ---------------------------------------------------------------------------
def _sync_firewall_cache_ip(db: Session, sid: int, ip: str, action: str):
    """Sinkronisasi seketika snapshot firewall di ServerExtras agar UI realtime."""
    try:
        extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
        if not extra:
            return
        fw_dict = {}
        if extra.firewall:
            try:
                fw_dict = json.loads(extra.firewall)
            except Exception:
                fw_dict = {}
        if not isinstance(fw_dict, dict):
            fw_dict = {"backend": "iptables", "status": "active", "rules": [], "blocked_ips": []}

        blocked = fw_dict.get("blocked_ips") or []
        if action == "block":
            if not any(isinstance(b, dict) and b.get("source") == ip for b in blocked):
                blocked.append({
                    "num": str(len(blocked) + 1),
                    "source": ip,
                    "pkts": "0",
                    "bytes": "0",
                })
                fw_dict["blocked_ips"] = blocked
                extra.firewall = json.dumps(fw_dict)
        elif action == "unblock":
            blocked = [b for b in blocked if isinstance(b, dict) and b.get("source") != ip]
            for idx, b in enumerate(blocked, start=1):
                b["num"] = str(idx)
            fw_dict["blocked_ips"] = blocked
            extra.firewall = json.dumps(fw_dict)
    except Exception:
        pass


def _sync_firewall_status(db: Session, sid: int, new_status: str):
    """Sinkronisasi seketika status aktif/nonaktif firewall di ServerExtras."""
    try:
        extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
        if not extra:
            return
        fw_dict = {}
        if extra.firewall:
            try:
                fw_dict = json.loads(extra.firewall)
            except Exception:
                fw_dict = {}
        if not isinstance(fw_dict, dict):
            fw_dict = {"backend": "ufw", "status": "inactive", "rules": [], "blocked_ips": []}

        fw_dict["status"] = new_status
        if new_status == "inactive":
            fw_dict["rules"] = []
        extra.firewall = json.dumps(fw_dict)
    except Exception:
        pass


@router.post("/servers/{sid}/problems/block")
def problem_block_ip(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Mitigasi: blokir IP sumber serangan SSH (iptables) via agen."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_firewall"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="masalah")
    if err_resp:
        return err_resp
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    sec = _parse_extras_security(extra)

    def _safe_block_ip(s: str) -> bool:
        try:
            a = ipaddress.ip_address(s)
        except ValueError:
            return False
        if a.is_loopback or a.is_link_local or a.is_multicast or a.is_unspecified or a.is_reserved:
            return False
        return s != server.ip_address

    is_json = (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "xmlhttprequest"
    )
    all_ips = list((sec.get("source_ips") or {}).keys())
    ips = [s for s in all_ips[:40] if _safe_block_ip(s)][:10]
    if not ips:
        if is_json:
            return JSONResponse({"ok": False, "detail": "Tidak ada IP valid yang dapat diblokir"}, status_code=400)
        return RedirectResponse(f"/servers/{sid}?action=noips", status_code=303)
    for ip_item in ips:
        _sync_firewall_cache_ip(db, sid, ip_item, "block")
    _enqueue_mitigation(db, sid, "block_ip", {"ips": ips}, issued_by=user.username)
    if is_json:
        return JSONResponse(
            {"ok": True, "detail": f"Perintah mitigasi blokir {len(ips)} IP penyerang dikirim ke agen."}
        )
    return RedirectResponse(f"/servers/{sid}?action=block", status_code=303)


@router.post("/servers/{sid}/firewall/block")
def firewall_block_ip(
    request: Request,
    sid: int,
    ip: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Blokir manual sebuah IP dari tab Firewall."""
    user = get_current_user(request, db)
    is_json = (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "xmlhttprequest"
    )
    if not user or not user.has_perm("can_firewall"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="firewall")
    if err_resp:
        return err_resp
    ip_clean = ip.strip()
    try:
        a = ipaddress.ip_address(ip_clean)
        if (
            a.is_loopback
            or a.is_link_local
            or a.is_multicast
            or a.is_unspecified
            or a.is_reserved
            or ip_clean == server.ip_address
        ):
            if is_json:
                return JSONResponse(
                    {"ok": False, "detail": f"Alamat IP {ip_clean} tidak diizinkan untuk diblokir"}, status_code=400
                )
            return RedirectResponse(f"/servers/{sid}?action=invalid_ip", status_code=303)
    except ValueError:
        if is_json:
            return JSONResponse({"ok": False, "detail": "Format IP tidak valid"}, status_code=400)
        return RedirectResponse(f"/servers/{sid}?action=invalid_ip", status_code=303)

    _sync_firewall_cache_ip(db, sid, ip_clean, "block")
    _enqueue_mitigation(db, sid, "block_ip", {"ips": [ip_clean]}, issued_by=user.username)
    _audit(
        db,
        user.username,
        "firewall_block",
        f"{server.hostname}: blokir {ip_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah blokir IP '{ip_clean}' dikirim ke agen. Menunggu eksekusi (~5–10 detik)."})
    return RedirectResponse(f"/servers/{sid}?action=block", status_code=303)


@router.post("/servers/{sid}/firewall/unblock")
def firewall_unblock_ip(
    request: Request,
    sid: int,
    ip: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Lepas blokir sebuah IP dari tab Firewall."""
    user = get_current_user(request, db)
    is_json = (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "xmlhttprequest"
    )
    if not user or not user.has_perm("can_firewall"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="firewall")
    if err_resp:
        return err_resp
    ip_clean = ip.strip()
    _sync_firewall_cache_ip(db, sid, ip_clean, "unblock")
    _enqueue_mitigation(db, sid, "unblock_ip", {"ips": [ip_clean]}, issued_by=user.username)
    _audit(
        db,
        user.username,
        "firewall_unblock",
        f"{server.hostname}: lepas blokir {ip_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah lepas blokir IP '{ip_clean}' dikirim ke agen. Menunggu eksekusi (~5–10 detik)."})
    return RedirectResponse(f"/servers/{sid}?action=unblock", status_code=303)


@router.post("/servers/{sid}/firewall/enable")
def firewall_enable(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Aktifkan firewall (UFW) via agen."""
    user = get_current_user(request, db)
    is_json = (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "xmlhttprequest"
    )
    if not user or not user.has_perm("can_firewall"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="firewall")
    if err_resp:
        return err_resp

    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    fw_status = "inactive"
    if extra and extra.firewall:
        try:
            fw_dict = json.loads(extra.firewall)
            if isinstance(fw_dict, dict):
                fw_status = fw_dict.get("status", "inactive")
        except Exception:
            pass

    if fw_status == "active":
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": "Firewall UFW sudah dalam status aktif (melindungi)."},
                status_code=400,
            )
        return RedirectResponse(f"/servers/{sid}?action=fw_already_active#tab-firewall", status_code=303)

    pending_cmd = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == "firewall_enable",
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    if pending_cmd:
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": "Perintah aktifkan firewall sedang dalam antrean atau sedang diproses oleh agen."},
                status_code=400,
            )
        return RedirectResponse(f"/servers/{sid}?action=fw_pending#tab-firewall", status_code=303)

    _sync_firewall_status(db, sid, "active")
    _enqueue_mitigation(db, sid, "firewall_enable", issued_by=user.username)
    _audit(
        db,
        user.username,
        "firewall_enable",
        f"{server.hostname}: aktifkan firewall (UFW)",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": "Perintah aktifkan firewall (UFW) dikirim ke agen. Menunggu eksekusi (~5–10 detik)."})
    return RedirectResponse(f"/servers/{sid}?action=fw_enabled#tab-firewall", status_code=303)


@router.post("/servers/{sid}/firewall/disable")
def firewall_disable(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Nonaktifkan firewall (UFW) via agen."""
    user = get_current_user(request, db)
    is_json = (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "xmlhttprequest"
    )
    if not user or not user.has_perm("can_firewall"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="firewall")
    if err_resp:
        return err_resp

    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    fw_status = "active"
    if extra and extra.firewall:
        try:
            fw_dict = json.loads(extra.firewall)
            if isinstance(fw_dict, dict):
                fw_status = fw_dict.get("status", "inactive")
        except Exception:
            pass

    if fw_status == "inactive":
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": "Firewall UFW sudah dalam status nonaktif."},
                status_code=400,
            )
        return RedirectResponse(f"/servers/{sid}?action=fw_already_inactive#tab-firewall", status_code=303)

    pending_cmd = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == "firewall_disable",
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    if pending_cmd:
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": "Perintah nonaktifkan firewall sedang dalam antrean atau sedang diproses oleh agen."},
                status_code=400,
            )
        return RedirectResponse(f"/servers/{sid}?action=fw_pending#tab-firewall", status_code=303)

    _sync_firewall_status(db, sid, "inactive")
    _enqueue_mitigation(db, sid, "firewall_disable", issued_by=user.username)
    _audit(
        db,
        user.username,
        "firewall_disable",
        f"{server.hostname}: nonaktifkan firewall (UFW)",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": "Perintah nonaktifkan firewall (UFW) dikirim ke agen. Menunggu eksekusi (~5–10 detik)."})
    return RedirectResponse(f"/servers/{sid}?action=fw_disabled#tab-firewall", status_code=303)


@router.post("/servers/{sid}/firewall/reload")
def firewall_reload(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Muat ulang (reload) aturan firewall via agen."""
    user = get_current_user(request, db)
    is_json = (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "xmlhttprequest"
    )
    if not user or not user.has_perm("can_firewall"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="firewall")
    if err_resp:
        return err_resp

    pending_cmd = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == "firewall_reload",
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    if pending_cmd:
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": "Perintah reload aturan firewall sedang dalam antrean atau sedang diproses oleh agen."},
                status_code=400,
            )
        return RedirectResponse(f"/servers/{sid}?action=fw_pending#tab-firewall", status_code=303)

    _enqueue_mitigation(db, sid, "firewall_reload", issued_by=user.username)
    _audit(
        db,
        user.username,
        "firewall_reload",
        f"{server.hostname}: reload firewall",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": "Perintah muat ulang (reload) firewall dikirim ke agen. Menunggu eksekusi (~5–10 detik)."})
    return RedirectResponse(f"/servers/{sid}?action=fw_reloaded#tab-firewall", status_code=303)


# ---------------------------------------------------------------------------
# PROCESS MANAGEMENT
# ---------------------------------------------------------------------------
@router.post("/servers/{sid}/processes/kill")
def process_kill(
    request: Request,
    sid: int,
    pid: int = Form(...),
    pname: str = Form(default=""),
    sig: str = Form(default="TERM"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Kirim sinyal hentikan proses (kill process) ke agen."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_processes"):
        if request.headers.get("accept") == "application/json":
            return JSONResponse(
                {"ok": False, "detail": "Akses ditolak: Anda tidak memiliki wewenang Task Manager"}, status_code=403
            )
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    is_json = request.headers.get("accept") == "application/json"
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="proses")
    if err_resp:
        return err_resp

    sig_clean = sig.strip().upper()
    if sig_clean not in ("TERM", "KILL", "15", "9", "STOP", "19", "CONT", "18"):
        sig_clean = "TERM"

    if pid <= 1:
        if request.headers.get("accept") == "application/json":
            return JSONResponse({"ok": False, "detail": "PID dilindungi atau tidak valid!"}, status_code=400)
        return RedirectResponse(f"/servers/{sid}?action=invalid_pid", status_code=303)

    pname_clean = (pname or "").strip()[:50]
    _enqueue_mitigation(
        db,
        sid,
        "kill_process",
        {"pid": str(pid), "signal": sig_clean, "pname": pname_clean},
        issued_by=user.username,
    )
    _audit(
        db,
        user.username,
        "kill_process",
        f"PID {pid} ({pname_clean or 'proses'})",
        f"sinyal SIG{sig_clean} dikirim ke agen",
        server_id=sid,
    )
    db.commit()

    if request.headers.get("accept") == "application/json":
        return JSONResponse(
            {
                "ok": True,
                "detail": f"Perintah penghentian PID {pid} ({pname_clean}) dengan sinyal SIG{sig_clean} dikirim ke agen.",
            }
        )
    return RedirectResponse(f"/servers/{sid}?action=process_killed&pid={pid}", status_code=303)


# ---------------------------------------------------------------------------
# AGENT REMOTE CONTROL & OTA UPDATE
# ---------------------------------------------------------------------------
@router.post("/servers/{sid}/problems/restart-agent")
def problem_restart_agent(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Mitigasi: restart agen (agent_pantau) jika tidak lagi melapor."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_services"):
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=False, redirect_tab="masalah")
    if err_resp:
        return err_resp
    _enqueue_mitigation(db, sid, "restart_agent", issued_by=user.username)
    return RedirectResponse(f"/servers/{sid}?action=agent", status_code=303)


@router.post("/servers/{sid}/agent/update")
def server_agent_update(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Kirim perintah pembaruan otomatis agen (Push Update OTA) dengan verifikasi kriptografi SHA-256."""
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_ota"):
        if (
            request.headers.get("accept") == "application/json"
            or request.headers.get("x-requested-with") == "XMLHttpRequest"
        ):
            raise HTTPException(
                status_code=403,
                detail="Akses ditolak: Anda tidak memiliki wewenang Dorong Pembaruan Agen (OTA)",
            )
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    is_json = (
        request.headers.get("accept") == "application/json"
        or request.headers.get("x-requested-with") == "XMLHttpRequest"
    )
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="layanan")
    if err_resp:
        return err_resp

    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == "update_agent",
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    if existing:
        msg = "Pembaruan agen sedang diproses atau dalam antrean queue."
        if is_json:
            return JSONResponse({"ok": True, "status": "already_pending", "message": msg})
        return RedirectResponse(f"/servers/{sid}?action=agent_updating", status_code=303)

    _, sha256_hash, version = _get_agent_code_and_sha256()
    base_url = str(request.base_url).rstrip("/")
    download_url = f"{base_url}/api/agent/latest-code"

    ota_params = {
        "url": download_url,
        "sha256": sha256_hash,
        "version": version,
    }

    _enqueue_mitigation(db, sid, "update_agent", params=ota_params, issued_by=user.username)
    _audit(
        db,
        user.username,
        "agent_update",
        f"OTA v{version} (SHA: {sha256_hash[:8]}…)",
        f"Push OTA v{version} (SHA256: {sha256_hash[:12]}…)",
        server_id=sid,
    )
    db.commit()

    msg = f"Perintah Push Update (OTA) v{version} berhasil dikirim ke {server.hostname} dengan verifikasi SHA-256."
    if is_json:
        return JSONResponse(
            {
                "ok": True,
                "status": "dispatched",
                "version": version,
                "sha256": sha256_hash,
                "message": msg,
            }
        )
    return RedirectResponse(f"/servers/{sid}?action=agent_updated", status_code=303)


# ---------------------------------------------------------------------------
# HOST POWER CONTROL (REBOOT / POWEROFF)
# ---------------------------------------------------------------------------
def _host_control(
    request: Request,
    sid: int,
    db: Session,
    action: str,
    csrf_token: str = "",
    password: str = "",
    totp: str = "",
) -> Response:
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_server_control"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json)
    if err_resp:
        return err_resp

    try:
        _verify_operator_password(
            user,
            password,
            totp_code=totp,
            action_name=action,
            target_info=f"{server.hostname} ({server.ip_address})",
            db=db,
        )
    except HTTPException as exc:
        if is_json:
            return JSONResponse({"ok": False, "detail": exc.detail}, status_code=exc.status_code)
        at_epoch = int(datetime.now(timezone.utc).timestamp())
        return RedirectResponse(
            f"/servers/{sid}?action=auth_error&msg={quote(exc.detail)}&at={at_epoch}", status_code=303
        )

    if action == "poweroff_host" and getattr(server, "is_proxmox_ha", 0):
        _audit(
            db,
            user.username,
            "poweroff_host",
            f"{server.hostname} ({server.ip_address})",
            "Ditolak: Server terproteksi Proxmox HA",
            server_id=sid,
        )
        db.commit()
        if is_json:
            return JSONResponse(
                {
                    "ok": False,
                    "detail": "Server terproteksi Proxmox HA.",
                },
                status_code=400,
            )
        at_epoch = int(datetime.now(timezone.utc).timestamp())
        return RedirectResponse(f"/servers/{sid}?action=poweroff_ha_blocked&at={at_epoch}", status_code=303)
    _enqueue_mitigation(db, sid, action, issued_by=user.username)
    if action == "poweroff_host":
        op_name = (user.username if user else "OPERATOR").upper()
        prob = (
            db.query(ServerProblem)
            .filter(
                ServerProblem.server_id == sid,
                ServerProblem.key == "agent_stale",
                ServerProblem.resolved_at.is_(None),
            )
            .first()
        )
        if prob:
            prob.is_ignored = 1
            prob.ignored_until = None
            prob.ignored_by = user.username
            prob.ignored_reason = f"SERVER DIMATIKAN OLEH OPERATOR ({op_name})"
            prob.ignore_mode = "permanent"
            prob.updated_at = datetime.utcnow()
    _audit(
        db,
        user.username,
        action,
        f"{server.hostname} ({server.ip_address})",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    flag = "reboot" if action == "reboot_host" else "poweroff"
    at_epoch = int(datetime.now(timezone.utc).timestamp())
    if is_json:
        label = "Mulai ulang (reboot)" if action == "reboot_host" else "Matikan daya (power off)"
        return JSONResponse(
            {
                "ok": True,
                "action": flag,
                "at": at_epoch,
                "detail": f"Perintah {label} server klien telah dikirim ke agen.",
            }
        )
    return RedirectResponse(f"/servers/{sid}?action={flag}&at={at_epoch}", status_code=303)


@router.post("/servers/{sid}/host/reboot")
def host_reboot(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    password: str = Form(default=""),
    totp: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Reboot OS server klien (admin). Wajib password operator."""
    return _host_control(request, sid, db, "reboot_host", csrf_token, password, totp)


@router.post("/servers/{sid}/host/poweroff")
def host_poweroff(
    request: Request,
    sid: int,
    csrf_token: str = Form(default=""),
    password: str = Form(default=""),
    totp: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Poweroff OS server klien (admin). Wajib password operator."""
    return _host_control(request, sid, db, "poweroff_host", csrf_token, password, totp)


# ---------------------------------------------------------------------------
# LINUX SYSTEM USERS MANAGEMENT
# ---------------------------------------------------------------------------
@router.post("/servers/{sid}/system-users/create")
def server_user_create(
    request: Request,
    sid: int,
    username: str = Form(...),
    password: str = Form(default=""),
    shell: str = Form(default="/bin/bash"),
    is_sudo: bool = Form(default=False),
    comment: str = Form(default="Dibuat via Pantau Server"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()
    params = {
        "username": u_clean,
        "shell": shell.strip() or "/bin/bash",
        "is_sudo": "1" if is_sudo else "0",
        "comment": comment.strip() or "Dibuat via Pantau Server",
    }
    if password.strip():
        params["password"] = password.strip()

    _enqueue_mitigation(db, sid, "user_create", params, issued_by=user.username)
    _audit(
        db,
        user.username,
        "user_create",
        f"{server.hostname}: buat user {u_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah pembuatan pengguna '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=akun", status_code=303)


@router.post("/servers/{sid}/system-users/lock")
def server_user_lock(
    request: Request,
    sid: int,
    username: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if extra and extra.accounts:
        try:
            acc_list = json.loads(extra.accounts)
            for a in acc_list:
                if str(a.get("user", "")).lower() == u_clean:
                    a["is_locked"] = True
            extra.accounts = json.dumps(acc_list)
        except Exception:
            pass
    _enqueue_mitigation(db, sid, "user_lock", {"username": u_clean}, issued_by=user.username)
    _audit(
        db,
        user.username,
        "user_lock",
        f"{server.hostname}: kunci user {u_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah kunci akun '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=akun", status_code=303)


@router.post("/servers/{sid}/system-users/unlock")
def server_user_unlock(
    request: Request,
    sid: int,
    username: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if extra and extra.accounts:
        try:
            acc_list = json.loads(extra.accounts)
            for a in acc_list:
                if str(a.get("user", "")).lower() == u_clean:
                    a["is_locked"] = False
            extra.accounts = json.dumps(acc_list)
        except Exception:
            pass
    _enqueue_mitigation(db, sid, "user_unlock", {"username": u_clean}, issued_by=user.username)
    _audit(
        db,
        user.username,
        "user_unlock",
        f"{server.hostname}: buka kunci user {u_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah buka kunci akun '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=akun", status_code=303)


@router.post("/servers/{sid}/system-users/delete")
def server_user_delete(
    request: Request,
    sid: int,
    username: str = Form(...),
    remove_home: bool = Form(default=False),
    csrf_token: str = Form(default=""),
    password: str = Form(default=""),
    totp: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_users_sys"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    u_clean = username.strip().lower()

    try:
        _verify_operator_password(
            user,
            password,
            totp_code=totp,
            action_name="system_user_delete",
            target_info=f"{server.hostname}: user {u_clean}",
            db=db,
        )
    except HTTPException as exc:
        if is_json:
            return JSONResponse({"ok": False, "detail": exc.detail}, status_code=exc.status_code)
        return RedirectResponse(
            f"/servers/{sid}?tab=akun&action=auth_error&msg={quote(exc.detail)}", status_code=303
        )
    extra = db.query(ServerExtras).filter(ServerExtras.server_id == sid).first()
    if extra and extra.accounts:
        try:
            acc_list = json.loads(extra.accounts)
            acc_list = [a for a in acc_list if str(a.get("user", "")).lower() != u_clean]
            extra.accounts = json.dumps(acc_list)
        except Exception:
            pass
    _enqueue_mitigation(
        db,
        sid,
        "user_delete",
        {"username": u_clean, "remove_home": "1" if remove_home else "0"},
        issued_by=user.username,
    )
    _audit(
        db,
        user.username,
        "user_delete",
        f"{server.hostname}: hapus user {u_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah hapus akun '{u_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=akun", status_code=303)


@router.post("/servers/{sid}/system-users/terminate-session")
@router.post("/api/servers/{sid}/sessions/terminate")
@router.post("/servers/{sid}/sessions/terminate")
async def server_session_terminate(
    request: Request,
    sid: int,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "") or "application/json" in request.headers.get("content-type", "")
    if not user or not (
        user.has_perm("can_users_sys") or user.has_perm("can_manage_servers") or user.is_master_admin()
    ):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)

    tty = ""
    username = ""
    csrf_token = ""
    if "application/json" in request.headers.get("content-type", ""):
        try:
            body = await request.json()
        except Exception:
            body = {}
        tty = str(body.get("tty", ""))
        username = str(body.get("user") or body.get("username", ""))
    else:
        form = await request.form()
        tty = str(form.get("tty", ""))
        username = str(form.get("username", ""))
        csrf_token = str(form.get("csrf_token", ""))

    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="akun")
    if err_resp:
        return err_resp
    clean_tty = tty.strip().lstrip("/dev/")
    if not re.match(r"^(pts/\d+|tty\d+)$", clean_tty):
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": f"Format terminal TTY '{clean_tty}' tidak valid."}, status_code=400
            )
        return RedirectResponse(f"/servers/{sid}?tab=akun", status_code=303)

    u_clean = (username or "").strip().lower()
    _enqueue_mitigation(
        db, sid, "session_terminate", {"tty": clean_tty, "username": u_clean}, issued_by=user.username
    )
    audit_target = f"{server.hostname}: putus sesi terminal {clean_tty}" + (f" ({u_clean})" if u_clean else "")
    _audit(db, user.username, "session_terminate", audit_target, "dikirim ke agen", server_id=sid)
    db.commit()

    detail_msg = f"Perintah pemutusan sesi terminal '{clean_tty}' berhasil dikirim ke agen."
    if is_json:
        return JSONResponse({"ok": True, "detail": detail_msg})
    return RedirectResponse(f"/servers/{sid}?tab=akun", status_code=303)


# ---------------------------------------------------------------------------
# CRON JOBS MANAGEMENT
# ---------------------------------------------------------------------------
@router.post("/servers/{sid}/cron/add")
def server_cron_add(
    request: Request,
    sid: int,
    ident: str = Form(...),
    minute: str = Form(default="*"),
    hour: str = Form(default="*"),
    dom: str = Form(default="*"),
    month: str = Form(default="*"),
    dow: str = Form(default="*"),
    user_target: str = Form(default="root"),
    command: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    id_clean = ident.strip()
    cmd_clean = command.strip()
    _enqueue_mitigation(
        db,
        sid,
        "cron_add",
        {
            "ident": id_clean,
            "minute": minute.strip() or "*",
            "hour": hour.strip() or "*",
            "dom": dom.strip() or "*",
            "month": month.strip() or "*",
            "dow": dow.strip() or "*",
            "user": user_target.strip() or "root",
            "command": cmd_clean,
        },
        issued_by=user.username,
    )
    _audit(
        db,
        user.username,
        "cron_add",
        f"{server.hostname}: tambah cron {id_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah tambah cron job '{id_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=cron", status_code=303)


@router.post("/servers/{sid}/cron/toggle")
def server_cron_toggle(
    request: Request,
    sid: int,
    ident: str = Form(...),
    mode: str = Form(default="enable"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    id_clean = ident.strip()
    m_clean = mode.strip().lower()
    _enqueue_mitigation(
        db, sid, "cron_toggle", {"ident": id_clean, "mode": m_clean}, issued_by=user.username
    )
    _audit(
        db,
        user.username,
        "cron_toggle",
        f"{server.hostname}: {m_clean} cron {id_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah ubah status cron '{id_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=cron", status_code=303)


@router.post("/servers/{sid}/cron/delete")
def server_cron_delete(
    request: Request,
    sid: int,
    ident: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    id_clean = ident.strip()
    _enqueue_mitigation(db, sid, "cron_delete", {"ident": id_clean}, issued_by=user.username)
    _audit(
        db,
        user.username,
        "cron_delete",
        f"{server.hostname}: hapus cron {id_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Perintah hapus cron '{id_clean}' dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=cron", status_code=303)


@router.post("/servers/{sid}/cron/run")
def server_cron_run(
    request: Request,
    sid: int,
    user_target: str = Form(default="root"),
    command: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_cron"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="cron")
    if err_resp:
        return err_resp
    cmd_clean = command.strip()
    u_clean = user_target.strip() or "root"
    _enqueue_mitigation(
        db, sid, "cron_run_now", {"user": u_clean, "command": cmd_clean}, issued_by=user.username
    )
    _audit(
        db,
        user.username,
        "cron_run_now",
        f"{server.hostname}: uji jalankan cron ({u_clean}: {cmd_clean[:50]})",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": "Perintah uji jalankan cron job dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=cron", status_code=303)


# ---------------------------------------------------------------------------
# FIREWALL PORT RULES
# ---------------------------------------------------------------------------
@router.post("/servers/{sid}/ports/rule")
def server_port_rule(
    request: Request,
    sid: int,
    port: str = Form(...),
    rule: str = Form(default="deny"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_firewall"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="ports")
    if err_resp:
        return err_resp
    p_clean = port.strip()
    r_clean = rule.strip().lower()
    pnum = p_clean.split("/")[0]
    if pnum in ("22", "8400") and r_clean in ("deny", "block"):
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": f"Port {pnum} dilindungi dan dilarang diblokir!"}, status_code=400
            )
        return RedirectResponse(f"/servers/{sid}?tab=ports&error=protected_port", status_code=303)

    _enqueue_mitigation(
        db, sid, "firewall_port_rule", {"port": p_clean, "rule": r_clean}, issued_by=user.username
    )
    _audit(
        db,
        user.username,
        "firewall_port_rule",
        f"{server.hostname}: aturan port {p_clean} ({r_clean})",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Aturan port '{p_clean}' ({r_clean}) dikirim ke agen."})
    return RedirectResponse(f"/servers/{sid}?tab=ports", status_code=303)


# ---------------------------------------------------------------------------
# SSL CERTIFICATES PATHS
# ---------------------------------------------------------------------------
@router.post("/servers/{sid}/ssl/add-path")
def server_ssl_add_path(
    request: Request,
    sid: int,
    path: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_ssl"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        if is_json:
            return JSONResponse({"ok": False, "detail": "Server tidak ditemukan"}, status_code=404)
        return RedirectResponse("/servers", status_code=303)
    path_clean = path.strip()
    _enqueue_mitigation(db, sid, "ssl_path_add", {"path": path_clean}, issued_by=user.username)
    _audit(
        db,
        user.username,
        "ssl_path_add",
        f"{server.hostname}: tambah path SSL {path_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse(
            {"ok": True, "detail": f"Perintah tambah path sertifikat SSL '{path_clean}' dikirim ke agen."}
        )
    return RedirectResponse(f"/servers/{sid}?tab=ssl", status_code=303)


@router.post("/servers/{sid}/ssl/remove-path")
def server_ssl_remove_path(
    request: Request,
    sid: int,
    path: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_ssl"):
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)
    server = db.query(Server).filter(Server.id == sid).first()
    if not server:
        if is_json:
            return JSONResponse({"ok": False, "detail": "Server tidak ditemukan"}, status_code=404)
        return RedirectResponse("/servers", status_code=303)
    path_clean = path.strip()
    _enqueue_mitigation(db, sid, "ssl_path_remove", {"path": path_clean}, issued_by=user.username)
    _audit(
        db,
        user.username,
        "ssl_path_remove",
        f"{server.hostname}: hapus path SSL {path_clean}",
        "dikirim ke agen",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse(
            {"ok": True, "detail": f"Perintah hapus path sertifikat SSL '{path_clean}' dikirim ke agen."}
        )
    return RedirectResponse(f"/servers/{sid}?tab=ssl", status_code=303)


# ---------------------------------------------------------------------------
# AGENT DISTRIBUTION (LATEST CODE & WRAPPERS)
# ---------------------------------------------------------------------------
@router.api_route("/api/agent/latest-code", methods=["GET", "HEAD"])
def api_agent_latest_code():
    """Download source code Agen Pantau terbaru langsung dari dashboard dengan verifikasi SHA-256."""
    data, sha256_hash, version = _get_agent_code_and_sha256()
    return Response(
        content=data,
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Agent-Version": version,
            "X-Checksum-SHA256": sha256_hash,
            "ETag": f'"{sha256_hash}"',
        },
    )


@router.api_route("/api/agent/wrapper/{wrapper_name}", methods=["GET", "HEAD"])
def api_agent_wrapper(wrapper_name: str):
    """Download file wrapper resmi Agen Pantau (mis. pantau-user, pantau-apt, dll.)."""
    allowed_wrappers = {
        "pantau-user",
        "pantau-apt",
        "pantau-cron",
        "pantau-file",
        "pantau-firewall",
        "pantau-history",
        "pantau-host",
        "pantau-restart",
        "pantau-shell",
        "pantau-ssl",
    }
    clean_name = os.path.basename(wrapper_name.strip())
    if clean_name not in allowed_wrappers:
        raise HTTPException(status_code=404, detail=f"Wrapper '{clean_name}' tidak ditemukan.")

    root_dir = Path(__file__).resolve().parent.parent.parent
    wrapper_path = root_dir / "package" / "usr" / "local" / "sbin" / clean_name
    if not wrapper_path.is_file():
        wrapper_path = Path("/usr/local/sbin") / clean_name

    if not wrapper_path.is_file():
        raise HTTPException(status_code=404, detail=f"File wrapper '{clean_name}' tidak tersedia di server.")

    content = wrapper_path.read_bytes()
    sha256_hash = hashlib.sha256(content).hexdigest()
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={
            "X-Wrapper-Name": clean_name,
            "X-Checksum-SHA256": sha256_hash,
            "ETag": f'"{sha256_hash}"',
        },
    )
