"""
Router Manajemen Layanan dan Operasi Systemd.
Menangani pendaftaran layanan yang dipantau, kontrol lifecycle layanan
(start/stop/restart/delete/toggle-core), tindakan unit systemd host (restart/start/stop/reload/enable/disable),
kebijakan pengabaian pemantauan layanan (ignore/unignore), serta riwayat uptime & latensi layanan.
"""

from datetime import datetime, timedelta
import json
import logging
import re

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import (
    get_current_user,
    require_user,
    _verify_csrf_form,
    _verify_csrf_header,
)
from core.utils import (
    _clean_str,
    _clamp_int,
    _flash_qs,
)
from models import (
    Server,
    Service,
    Metric,
    Command,
    ServerProblem,
    User,
)
from services.audit_service import _audit
from services.problem_service import _build_problem_context
from services.server_service import (
    _check_server_online,
    _latest_metrics,
)

logger = logging.getLogger("pantau.services")

router = APIRouter(tags=["Services"])


# ---------------------------------------------------------------------------
# SERVICES MANAGEMENT
# ---------------------------------------------------------------------------
@router.post("/servers/{sid}/services/add")
def service_add_submit(
    request: Request,
    sid: int,
    service_name: str = Form(...),
    port: int = Form(...),
    process_name: str = Form(...),
    is_core: int = Form(1),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = (
        "application/json" in request.headers.get("accept", "")
        or request.headers.get("x-requested-with") == "xmlhttprequest"
    )
    if not user or not user.has_perm("can_services"):
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": "Akses ditolak: Izin kontrol layanan diperlukan"},
                status_code=403,
            )
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    svc = Service(
        server_id=sid,
        service_name=_clean_str(service_name, "", 100),
        port=_clamp_int(port, 0, 1, 65535),
        process_name=_clean_str(process_name, "", 100),
        is_core=1 if is_core else 0,
    )
    if not svc.service_name or not (1 <= svc.port <= 65535):
        if is_json:
            return JSONResponse(
                {"ok": False, "detail": "Data service tidak lengkap: nama wajib & port 1-65535"},
                status_code=400,
            )
        return RedirectResponse(
            f"/servers/{sid}?tab=layanan" + _flash_qs(False, "Service tidak lengkap: nama wajib & port 1-65535"),
            status_code=303,
        )
    existing = (
        db.query(Service)
        .filter(Service.server_id == sid, Service.service_name == svc.service_name)
        .first()
    )
    if existing:
        if is_json:
            return JSONResponse({"ok": False, "detail": "Nama service sudah terdaftar di server ini"}, status_code=400)
        return RedirectResponse(
            f"/servers/{sid}?tab=layanan" + _flash_qs(False, "Nama service sudah ada"),
            status_code=303,
        )
    db.add(svc)
    server = db.query(Server).filter(Server.id == sid).first()
    _audit(
        db,
        user.username,
        "service_add",
        f"{server.hostname if server else sid}:{svc.service_name}",
        f"port {svc.port}",
        server_id=sid,
    )
    db.commit()
    if is_json:
        return JSONResponse({"ok": True, "detail": f"Service '{svc.service_name}' berhasil ditambahkan ke pemantauan."})
    return RedirectResponse(
        f"/servers/{sid}?tab=layanan" + _flash_qs(True, "Service ditambahkan"),
        status_code=303,
    )


@router.post("/servers/{sid}/services/{svc_id}/restart")
def service_restart(
    request: Request,
    sid: int,
    svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_services"):
        if is_json:
            return Response(
                json.dumps({"ok": False, "detail": "Akses ditolak: Anda tidak memiliki wewenang Layanan"}),
                status_code=403,
                media_type="application/json",
            )
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="layanan")
    if err_resp:
        return err_resp
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        if is_json:
            return Response(
                json.dumps({"ok": False, "detail": "Service tidak ditemukan"}),
                status_code=404,
                media_type="application/json",
            )
        return RedirectResponse(f"/servers/{sid}?tab=layanan", status_code=303)

    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.service_id == svc_id,
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    if existing:
        if is_json:
            return Response(
                json.dumps({"ok": True, "detail": f"Perintah restart {svc.service_name} sedang diproses."}),
                media_type="application/json",
            )
        return RedirectResponse(f"/servers/{sid}?tab=layanan&restarted=1", status_code=303)

    db.add(
        Command(
            server_id=sid,
            service_id=svc_id,
            action="restart",
            status="pending",
            issued_by=user.username,
        )
    )
    if getattr(svc, "ignore_mode", None) != "permanent":
        svc.is_ignored = 0
        svc.ignored_until = None
        svc.ignored_reason = None
        svc.ignore_mode = None
        prob = (
            db.query(ServerProblem)
            .filter(
                ServerProblem.server_id == sid,
                ServerProblem.key == f"service_down:{svc.service_name}",
                ServerProblem.resolved_at.is_(None),
            )
            .first()
        )
        if prob:
            prob.is_ignored = 0
            prob.ignored_until = None
            prob.ignored_reason = None
            prob.ignore_mode = None
            prob.updated_at = datetime.utcnow()
    db.commit()
    if is_json:
        return Response(
            json.dumps(
                {"ok": True, "detail": f"Perintah restart {svc.service_name} telah dikirim ke Agen Pantau."}
            ),
            media_type="application/json",
        )
    return RedirectResponse(f"/servers/{sid}?tab=layanan&restarted=1", status_code=303)


def _service_action(request: Request, sid: int, svc_id: int, action: str, db: Session, csrf_token: str = ""):
    """Helper bersama untuk start/stop layanan."""
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_services"):
        if is_json:
            return Response(
                json.dumps({"ok": False, "detail": "Akses ditolak: Anda tidak memiliki wewenang Layanan"}),
                status_code=403,
                media_type="application/json",
            )
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    server, err_resp = _check_server_online(db, sid, is_json=is_json, redirect_tab="layanan")
    if err_resp:
        return err_resp
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        if is_json:
            return Response(
                json.dumps({"ok": False, "detail": "Service tidak ditemukan"}),
                status_code=404,
                media_type="application/json",
            )
        return RedirectResponse(f"/servers/{sid}?tab=layanan", status_code=303)
    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.service_id == svc_id,
            Command.status.in_(["pending", "executing"]),
        )
        .first()
    )
    label_id = {"start": "mulai", "stop": "hentikan"}.get(action, action)
    if existing:
        if is_json:
            return Response(
                json.dumps({"ok": True, "detail": f"Perintah {label_id} {svc.service_name} sedang diproses."}),
                media_type="application/json",
            )
        return RedirectResponse(f"/servers/{sid}?tab=layanan&restarted=1", status_code=303)

    latest_m = _latest_metrics(db, [svc_id]).get(svc_id)
    cur_st = latest_m.status if latest_m else "unknown"
    if action == "stop" and cur_st == "down":
        if is_json:
            return Response(
                json.dumps({"ok": True, "detail": f"Layanan {svc.service_name} sudah dalam kondisi berhenti."}),
                media_type="application/json",
            )
        return RedirectResponse(f"/servers/{sid}?tab=layanan", status_code=303)
    if action == "start" and cur_st == "up":
        if is_json:
            return Response(
                json.dumps({"ok": True, "detail": f"Layanan {svc.service_name} sudah dalam kondisi aktif."}),
                media_type="application/json",
            )
        return RedirectResponse(f"/servers/{sid}?tab=layanan", status_code=303)

    db.add(
        Command(
            server_id=sid,
            service_id=svc_id,
            action=action,
            status="pending",
            issued_by=user.username,
        )
    )
    server = db.query(Server).filter(Server.id == sid).first()
    _audit(
        db,
        user.username,
        f"service_{action}",
        f"{server.hostname if server else sid}:{svc.service_name}",
        "dikirim ke agen",
        server_id=sid,
    )
    now_ts = datetime.utcnow()
    if action == "stop":
        op_name = (user.username if user else "OPERATOR").upper()
        reason_txt = f"LAYANAN DIMATIKAN OLEH OPERATOR ({op_name})"
        svc.is_ignored = 1
        svc.ignored_until = None
        svc.ignored_by = user.username
        svc.ignored_reason = reason_txt
        svc.ignore_mode = "permanent"

        db.add(
            Metric(
                service_id=svc_id,
                status="down",
                response_time_ms=None,
                active_connections=0,
                timestamp=now_ts,
                health_message=f"Layanan dihentikan oleh operator ({op_name})",
            )
        )

        sev = "warning"
        msg = f"Layanan {svc.service_name} dimatikan oleh operator ({op_name})"
        tip = "Layanan sengaja dihentikan melalui panel kontrol oleh operator."

        prob = (
            db.query(ServerProblem)
            .filter(
                ServerProblem.server_id == sid,
                ServerProblem.key == f"service_down:{svc.service_name}",
                ServerProblem.resolved_at.is_(None),
            )
            .first()
        )
        if prob:
            prob.severity = sev
            prob.message = msg
            prob.tip = tip
            prob.is_ignored = 1
            prob.ignored_until = None
            prob.ignored_by = user.username
            prob.ignored_reason = reason_txt
            prob.ignore_mode = "permanent"
            prob.updated_at = now_ts
        else:
            db.add(
                ServerProblem(
                    server_id=sid,
                    key=f"service_down:{svc.service_name}",
                    severity=sev,
                    message=msg,
                    tip=tip,
                    is_ignored=1,
                    ignore_mode="permanent",
                    ignored_reason=reason_txt,
                    ignored_by=user.username,
                    started_at=now_ts,
                    updated_at=now_ts,
                )
            )
    elif action == "start":
        svc.is_ignored = 0
        svc.ignored_until = None
        svc.ignored_reason = None
        svc.ignore_mode = None

        db.add(
            Metric(
                service_id=svc_id,
                status="up",
                response_time_ms=0,
                active_connections=0,
                timestamp=now_ts,
                health_message=f"Layanan dimulai oleh operator ({user.username})",
            )
        )

        prob = (
            db.query(ServerProblem)
            .filter(
                ServerProblem.server_id == sid,
                ServerProblem.key == f"service_down:{svc.service_name}",
                ServerProblem.resolved_at.is_(None),
            )
            .first()
        )
        if prob:
            prob.is_ignored = 0
            prob.ignored_until = None
            prob.ignored_reason = None
            prob.ignore_mode = None
            prob.resolved_at = now_ts
            prob.updated_at = now_ts
            prob.resolved_note = "operator_start"
    db.commit()
    if is_json:
        return Response(
            json.dumps(
                {"ok": True, "detail": f"Perintah {label_id} {svc.service_name} telah dikirim ke Agen Pantau."}
            ),
            media_type="application/json",
        )
    return RedirectResponse(f"/servers/{sid}?tab=layanan&restarted=1", status_code=303)


@router.post("/servers/{sid}/services/{svc_id}/start")
def service_start(
    request: Request,
    sid: int,
    svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Mulai layanan yang sedang stop (admin/operator)."""
    return _service_action(request, sid, svc_id, "start", db, csrf_token)


@router.post("/servers/{sid}/services/{svc_id}/stop")
def service_stop(
    request: Request,
    sid: int,
    svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    """Hentikan layanan yang sedang berjalan (admin/operator)."""
    return _service_action(request, sid, svc_id, "stop", db, csrf_token)


@router.post("/servers/{sid}/services/{svc_id}/delete")
def service_delete(
    request: Request,
    sid: int,
    svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_services"):
        if is_json:
            return Response(
                json.dumps({"ok": False, "detail": "Akses ditolak: Izin kontrol layanan diperlukan"}),
                status_code=403,
                media_type="application/json",
            )
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if svc:
        server = db.query(Server).filter(Server.id == sid).first()
        svc_name = svc.service_name
        db.query(ServerProblem).filter(
            ServerProblem.server_id == sid,
            ServerProblem.key.in_([f"service_down:{svc_name}", f"svc_no_data:{svc_name}"]),
            ServerProblem.resolved_at.is_(None),
        ).delete(synchronize_session=False)

        _audit(
            db,
            user.username,
            "service_delete",
            f"{server.hostname if server else sid}:{svc_name}",
            "berhasil",
            server_id=sid,
        )
        db.delete(svc)
        db.commit()
        if is_json:
            return Response(
                json.dumps({"ok": True, "detail": f"Layanan {svc_name} berhasil dilepas dari pengawasan dashboard"}),
                media_type="application/json",
            )
    elif is_json:
        return Response(
            json.dumps({"ok": False, "detail": "Layanan tidak ditemukan"}),
            status_code=404,
            media_type="application/json",
        )
    return RedirectResponse(f"/servers/{sid}?tab=layanan", status_code=303)


@router.post("/servers/{sid}/services/{svc_id}/toggle-core")
def service_toggle_core(
    request: Request,
    sid: int,
    svc_id: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or not user.has_perm("can_services"):
        if is_json:
            return Response(
                json.dumps({"ok": False, "detail": "Akses ditolak"}),
                status_code=403,
                media_type="application/json",
            )
        return RedirectResponse("/", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if svc:
        new_is_core = 0 if getattr(svc, "is_core", 1) else 1
        svc.is_core = new_is_core
        server = db.query(Server).filter(Server.id == sid).first()
        status_name = "Layanan Utama (Core)" if new_is_core else "Layanan Pendukung (Secondary)"
        _audit(
            db,
            user.username,
            "service_core_toggle",
            f"{server.hostname if server else sid}:{svc.service_name} -> {status_name}",
            "berhasil",
            server_id=sid,
        )
        db.commit()
        if is_json:
            return Response(
                json.dumps({"ok": True, "is_core": bool(new_is_core), "detail": f"Status diubah ke {status_name}"}),
                media_type="application/json",
            )
    elif is_json:
        return Response(
            json.dumps({"ok": False, "detail": "Service tidak ditemukan"}),
            status_code=404,
            media_type="application/json",
        )
    return RedirectResponse(f"/servers/{sid}?tab=layanan", status_code=303)


# ---------------------------------------------------------------------------
# SYSTEMD ACTIONS
# ---------------------------------------------------------------------------
@router.post("/api/servers/{sid}/systemd/{action}")
async def api_systemd_action(
    sid: int,
    action: str,
    request: Request,
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or not user.has_perm("can_services"):
        raise HTTPException(status_code=403, detail="Akses ditolak: Anda tidak memiliki wewenang Layanan")

    _verify_csrf_header(request)

    if action not in ("restart", "start", "stop", "reload", "enable", "disable"):
        raise HTTPException(status_code=400, detail="Aksi systemd tidak dikenal")

    try:
        body = await request.json()
    except Exception:
        body = {}

    unit = str(body.get("unit") or "").strip()
    if not unit or not re.fullmatch(r"^[a-zA-Z0-9@._:\-]{1,64}$", unit):
        raise HTTPException(status_code=400, detail="Nama unit tidak valid")

    if action == "stop" and unit.startswith(("agent_pantau", "agent-pantau")):
        raise HTTPException(
            status_code=400,
            detail="Unit agen pemantau (agent_pantau) dilindungi oleh sistem keamanan dan tidak boleh dihentikan.",
        )

    server, err_resp = _check_server_online(db, sid, is_json=True)
    if err_resp:
        return err_resp

    existing = (
        db.query(Command)
        .filter(
            Command.server_id == sid,
            Command.action == action,
            Command.status.in_(["pending", "executing"]),
        )
        .all()
    )
    for c in existing:
        p = json.loads(c.params) if c.params else {}
        if p.get("service_name") == unit or p.get("process_name") == unit:
            return {"ok": True, "detail": f"Perintah {action} unit {unit} sedang diproses oleh agen."}

    unit_clean = unit[:-8] if unit.endswith(".service") else unit
    op_name = (user.username if user else "OPERATOR").upper()
    now_ts = datetime.utcnow()

    matching_services = (
        db.query(Service)
        .filter(
            Service.server_id == sid,
            (Service.service_name.in_([unit, unit_clean])) | (Service.process_name.in_([unit, unit_clean])),
        )
        .all()
    )

    cmd = Command(
        server_id=sid,
        service_id=matching_services[0].id if matching_services else None,
        action=action,
        params=json.dumps({"service_name": unit, "process_name": unit}),
        issued_by=user.username,
        status="pending",
    )
    db.add(cmd)

    if action == "stop":
        reason_txt = f"LAYANAN DIMATIKAN OLEH OPERATOR ({op_name})"
        for svc in matching_services:
            svc.is_ignored = 1
            svc.ignored_until = None
            svc.ignored_by = user.username
            svc.ignored_reason = reason_txt
            svc.ignore_mode = "permanent"
            db.add(
                Metric(
                    service_id=svc.id,
                    status="down",
                    response_time_ms=None,
                    active_connections=0,
                    timestamp=now_ts,
                    health_message=f"Layanan dihentikan oleh operator ({op_name})",
                )
            )

        prob_keys = [f"service_down:{s.service_name}" for s in matching_services]
        if not prob_keys:
            prob_keys = [f"service_down:{unit_clean}"]

        for pk in prob_keys:
            prob = (
                db.query(ServerProblem)
                .filter(
                    ServerProblem.server_id == sid,
                    ServerProblem.key == pk,
                    ServerProblem.resolved_at.is_(None),
                )
                .first()
            )
            disp_name = pk.split(":", 1)[1]
            ctx_json = _build_problem_context(
                "service_down:",
                server,
                service_name=disp_name,
                port=None,
                proc=unit_clean,
                health_msg=f"Layanan dihentikan oleh operator ({op_name})",
                is_op_stop=True,
                op_by=op_name,
            )
            if prob:
                prob.severity = "warning"
                prob.message = f"Layanan {disp_name} dimatikan oleh operator ({op_name})"
                prob.tip = f"Unit {unit} sengaja dihentikan melalui panel kontrol oleh operator ({op_name}). Tindakan pemeliharaan tidak memicu alarm darurat."
                prob.is_ignored = 1
                prob.ignored_until = None
                prob.ignored_by = user.username
                prob.ignored_reason = reason_txt
                prob.ignore_mode = "permanent"
                prob.context = ctx_json
                prob.updated_at = now_ts
            else:
                db.add(
                    ServerProblem(
                        server_id=sid,
                        key=pk,
                        severity="warning",
                        message=f"Layanan {disp_name} dimatikan oleh operator ({op_name})",
                        tip=f"Unit {unit} sengaja dihentikan melalui panel kontrol oleh operator ({op_name}). Tindakan pemeliharaan tidak memicu alarm darurat.",
                        is_ignored=1,
                        ignore_mode="permanent",
                        ignored_reason=reason_txt,
                        ignored_by=user.username,
                        context=ctx_json,
                        started_at=now_ts,
                        updated_at=now_ts,
                    )
                )

    elif action in ("start", "restart"):
        for svc in matching_services:
            svc.is_ignored = 0
            svc.ignored_until = None
            svc.ignored_reason = None
            svc.ignore_mode = None
            db.add(
                Metric(
                    service_id=svc.id,
                    status="up",
                    response_time_ms=0,
                    active_connections=0,
                    timestamp=now_ts,
                    health_message=f"Layanan dimulai oleh operator ({user.username})",
                )
            )

        prob_keys = [f"service_down:{s.service_name}" for s in matching_services] + [f"service_down:{unit_clean}"]
        for pk in prob_keys:
            open_p = (
                db.query(ServerProblem)
                .filter(
                    ServerProblem.server_id == sid,
                    ServerProblem.key == pk,
                    ServerProblem.resolved_at.is_(None),
                )
                .all()
            )
            for op_p in open_p:
                op_p.is_ignored = 0
                op_p.ignored_until = None
                op_p.ignored_reason = None
                op_p.ignore_mode = None
                op_p.resolved_at = now_ts
                op_p.updated_at = now_ts
                op_p.resolved_note = "operator_start"

    _audit(
        db,
        user.username,
        "systemd_" + action,
        f"id={server.id} {server.hostname} unit={unit}",
        "berhasil",
    )
    db.commit()

    labels = {
        "restart": "restart",
        "start": "menyalakan",
        "stop": "menghentikan",
        "reload": "reload",
        "enable": "mengaktifkan boot",
        "disable": "menonaktifkan boot",
    }
    if action == "stop":
        detail_msg = f"Perintah penghentian unit {unit} telah dikirim ke agen. Status layanan dicatat sebagai pemeliharaan operator (Peringatan)."
    elif action in ("start", "restart"):
        detail_msg = f"Perintah {labels.get(action, action)} unit {unit} telah dikirim ke agen. Status pemeliharaan dipulihkan."
    else:
        detail_msg = f"Perintah {labels.get(action, action)} unit {unit} telah dikirim ke agen."
    return {"ok": True, "detail": detail_msg}


# ---------------------------------------------------------------------------
# SERVICE IGNORE & UNIGNORE
# ---------------------------------------------------------------------------
@router.post("/api/servers/{sid}/services/{svc_id}/ignore")
def api_service_ignore(
    sid: int,
    svc_id: int,
    request: Request,
    body: dict = Body(default={}),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Abaikan pemantauan suatu layanan secara langsung (bisa permanen atau durasi)."""
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_services")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kontrol layanan diperlukan")
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Layanan tidak ditemukan")

    duration = str(body.get("duration", "permanent")).lower().strip()
    reason = str(body.get("reason", "")).strip()[:255] or None

    now = datetime.utcnow()
    until = None
    ignore_mode = "duration"
    if duration == "2h":
        until = now + timedelta(hours=2)
    elif duration == "24h":
        until = now + timedelta(hours=24)
    elif duration == "7d":
        until = now + timedelta(days=7)
    elif duration == "30d":
        until = now + timedelta(days=30)
    elif duration in ("0", "perm", "permanent", "forever"):
        until = None
        ignore_mode = "permanent"
    elif duration == "incident":
        until = None
        ignore_mode = "incident"
    else:
        until = None
        ignore_mode = "permanent"

    svc.is_ignored = 1
    svc.ignored_until = until
    svc.ignored_by = user.username
    svc.ignored_reason = reason or f"diabaikan oleh {user.username}"
    svc.ignore_mode = ignore_mode

    prob = (
        db.query(ServerProblem)
        .filter(
            ServerProblem.server_id == sid,
            ServerProblem.key == f"service_down:{svc.service_name}",
            ServerProblem.resolved_at.is_(None),
        )
        .first()
    )
    if prob:
        prob.is_ignored = 1
        prob.ignored_until = until
        prob.ignored_by = user.username
        prob.ignored_reason = reason or f"diabaikan oleh {user.username}"
        prob.ignore_mode = ignore_mode
        prob.updated_at = now
        if not prob.acknowledged_at:
            prob.acknowledged_at = now
            prob.acknowledged_by = user.username

    dur_label = f" ({duration})" if ignore_mode != "permanent" else " (permanen)"
    if ignore_mode == "incident":
        dur_label = " (hanya insiden saat ini)"
    res_str = f"diabaikan{dur_label}" + (f": {reason}" if reason else "")
    _audit(
        db,
        user.username,
        "problem_ignore",
        target=f"Layanan {svc.service_name}",
        result=res_str,
        server_id=sid,
    )
    db.commit()
    return {
        "ok": True,
        "service_id": svc_id,
        "is_ignored": True,
        "ignored_until": until.isoformat() if until else None,
        "ignore_mode": ignore_mode,
        "ignored_by": user.username,
        "ignored_reason": reason,
    }


@router.post("/api/servers/{sid}/services/{svc_id}/unignore")
def api_service_unignore(
    sid: int,
    svc_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Aktifkan kembali pemantauan suatu layanan."""
    _verify_csrf_header(request)
    if user.is_viewer() or not (user.is_master_admin() or user.has_perm("can_services")):
        raise HTTPException(status_code=403, detail="Akses ditolak: izin kontrol layanan diperlukan")
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Layanan tidak ditemukan")

    svc.is_ignored = 0
    svc.ignored_until = None
    svc.ignored_reason = None
    svc.ignore_mode = None

    db.query(ServerProblem).filter(
        ServerProblem.server_id == sid,
        ServerProblem.key == f"service_down:{svc.service_name}",
    ).update(
        {
            ServerProblem.is_ignored: 0,
            ServerProblem.ignored_until: None,
            ServerProblem.ignored_reason: None,
            ServerProblem.ignore_mode: None,
        },
        synchronize_session=False,
    )

    _audit(
        db,
        user.username,
        "problem_unignore",
        target=f"Layanan {svc.service_name}",
        result="pemantauan diaktifkan kembali",
        server_id=sid,
    )
    db.commit()
    return {"ok": True, "service_id": svc_id, "is_ignored": False}


# ---------------------------------------------------------------------------
# SERVICE HISTORY API
# ---------------------------------------------------------------------------
@router.get("/api/servers/{sid}/services/{svc_id}/history")
def api_service_history(
    sid: int,
    svc_id: int,
    range: str = "24h",  # pylint: disable=redefined-builtin
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Riwayat metric service (status, koneksi, waktu respon) utk grafik layanan."""
    svc = db.query(Service).filter(Service.id == svc_id, Service.server_id == sid).first()
    if not svc:
        raise HTTPException(status_code=404, detail="Service tidak ditemukan")

    now = datetime.utcnow()
    if range == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        span = max(now - start, timedelta(minutes=5))
    else:
        span = {
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
        }.get(range)
        if not span:
            raise HTTPException(status_code=400, detail="Rentang tidak dikenal")
        start = now - span
    step_secs = max(int(span.total_seconds() / 120), 30)
    rows = (
        db.query(
            (func.floor(func.unix_timestamp(Metric.timestamp) / step_secs) * step_secs).label("tb"),
            func.count(Metric.id),
            func.sum(getattr(func, "if")(Metric.status == "up", 1, 0)),
            func.avg(Metric.active_connections),
            func.avg(Metric.response_time_ms),
        )
        .filter(
            Metric.service_id == svc_id,
            Metric.timestamp >= now - span,
            Metric.timestamp <= now,
        )
        .group_by("tb")
        .order_by("tb")
        .all()
    )
    points = []
    for tb, n, ups, conns, rt in rows:
        ups_count = int(ups or 0)
        up_ratio = (ups_count / n) if n else None
        points.append(
            {
                "t": int(tb),
                "up_ratio": round(up_ratio, 3) if up_ratio is not None else None,
                "samples": int(n),
                "conns": round(conns, 1) if conns is not None else 0,
                "rt": round(rt, 1) if rt is not None else None,
            }
        )

    latest = (
        db.query(Metric)
        .filter(Metric.service_id == svc_id)
        .order_by(desc(Metric.timestamp))
        .first()
    )
    return {
        "server_id": sid,
        "service": {"id": svc.id, "name": svc.service_name, "port": svc.port},
        "range": range,
        "from": int(start.timestamp()),
        "to": int(now.timestamp()),
        "now": {
            "status": latest.status if latest else "unknown",
            "connections": latest.active_connections if latest else 0,
            "response_time_ms": latest.response_time_ms if latest else None,
        },
        "points": points,
    }
