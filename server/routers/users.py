"""
Router Manajemen Pengguna Operator & Profil Akun (RBAC 3-Tier).
Menangani pendaftaran dan delegasi hak akses pengguna (Master Admin, Operator, Viewer),
manajemen perizinan modular per-operator, reset kata sandi, aktivasi/deaktivasi akun,
otentikasi dua faktor (TOTP RFC 6238) mandiri maupun terkelola,
serta pengaturan branding & identitas organisasi.
"""

from datetime import datetime
import json
import logging
from pathlib import Path
import re
import time

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import security_auth
from core.database import get_db
from core.security import (
    pwd_ctx,
    SESSION_COOKIE,
    get_current_user,
    require_user,
    _verify_csrf_form,
    _verify_csrf_header,
    _verify_operator_password,
)
from core.templates import (
    tpl,
    get_branding_settings,
    invalidate_branding_cache,
)
from core.utils import (
    _flash_qs,
    _flash_profile_users,
    _flash_profile_branding,
)
from models import (
    AppSession,
    SystemSetting,
    User,
)
from services.audit_service import _audit

logger = logging.getLogger("pantau.users")

router = APIRouter(tags=["Users"])


def _render_profile_page(
    request: Request,
    user: User,
    db: Session,
    newly_generated_codes: list = None,
    flash_ok: bool = None,
    flash_msg: str = None,
    active_tab: str = "users",
):
    raw_secret = ""
    formatted_secret = ""
    totp_uri = ""
    qr_data_url = ""
    if not user.totp_enabled:
        raw_secret = security_auth.generate_totp_secret()
        formatted_secret = security_auth.format_secret_display(raw_secret)
        totp_uri = security_auth.generate_totp_uri(raw_secret, user.username)
        qr_data_url = security_auth.generate_qr_data_url(totp_uri)

    rec_count = 0
    if user.recovery_codes:
        try:
            rec_count = len(json.loads(user.recovery_codes))
        except Exception:
            rec_count = 0

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    can_manage_branding = user.is_master_admin() or user.role == "operator"

    users_list = []
    if user.is_master_admin():
        users_list = db.query(User).order_by(User.id).all()
    elif can_manage_users:
        users_list = db.query(User).filter(User.role != "master_admin").order_by(User.id).all()
    elif can_manage_viewers:
        users_list = db.query(User).filter(User.role == "viewer").order_by(User.id).all()

    now_utc = datetime.utcnow()
    active_sessions_map = {}
    try:
        for uid_cnt in (
            db.query(AppSession.user_id, func.count(AppSession.id))
            .filter(AppSession.expires_at > now_utc)
            .group_by(AppSession.user_id)
            .all()
        ):
            active_sessions_map[uid_cnt[0]] = uid_cnt[1]
    except Exception:
        pass

    for u in users_list:
        u._active_sessions = active_sessions_map.get(u.id, 0)
        rec_cnt = 0
        if u.recovery_codes:
            try:
                rec_cnt = len(json.loads(u.recovery_codes))
            except Exception:
                rec_cnt = 0
        u._recovery_codes_count = rec_cnt

    return tpl(
        request,
        "profile.html",
        {
            "user": user,
            "users": users_list,
            "can_manage_users": can_manage_users,
            "can_manage_viewers": can_manage_viewers,
            "can_manage_any": can_manage_viewers,
            "can_manage_branding": can_manage_branding,
            "brand": get_branding_settings(db),
            "all_perms": security_auth.OPERATOR_PERMISSIONS,
            "raw_secret": raw_secret,
            "secret_formatted": formatted_secret,
            "qr_data_url": qr_data_url,
            "recovery_codes_remaining": rec_count,
            "newly_generated_codes": newly_generated_codes,
            "flash_ok": flash_ok,
            "flash_msg": flash_msg,
            "active_tab": active_tab,
        },
    )


# ---------------------------------------------------------------------------
# PROFILE & SELF-SERVICE 2FA
# ---------------------------------------------------------------------------
@router.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)

    flash_ok = request.query_params.get("ok")
    flash_msg = request.query_params.get("msg")
    flash_err = request.query_params.get("err")
    if flash_err:
        flash_ok = False
        flash_msg = flash_err
    elif flash_msg is not None:
        flash_ok = True
    elif flash_ok is not None:
        flash_ok = flash_ok == "1"

    active_tab = request.query_params.get("tab", "users")
    if active_tab == "me":
        active_tab = "users"

    return _render_profile_page(
        request=request,
        user=user,
        db=db,
        flash_ok=flash_ok,
        flash_msg=flash_msg,
        active_tab=active_tab,
    )


@router.post("/profile/password")
def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if not pwd_ctx.verify(current_password, user.password_hash):
        return RedirectResponse(_flash_profile_users(False, "Kata sandi saat ini tidak cocok"), status_code=303)

    if new_password != confirm_password:
        return RedirectResponse(
            _flash_profile_users(False, "Konfirmasi kata sandi baru tidak cocok"), status_code=303
        )

    valid, err_msg = security_auth.validate_password_strength(new_password)
    if not valid:
        return RedirectResponse(_flash_profile_users(False, err_msg), status_code=303)

    user.password_hash = pwd_ctx.hash(new_password)
    user.password_changed_at = datetime.utcnow()

    cur_sid = request.cookies.get(SESSION_COOKIE)
    if cur_sid:
        db.query(AppSession).filter(AppSession.user_id == user.id, AppSession.sid != cur_sid).delete(
            synchronize_session=False
        )

    _audit(db, user.username, "change_password", "profil sendiri", "berhasil (sesi lain dicabut)")
    db.commit()
    return RedirectResponse(
        _flash_profile_users(True, "Kata sandi berhasil diperbarui. Sesi perangkat lain telah dicabut."),
        status_code=303,
    )


@router.post("/profile/2fa/enable")
def profile_enable_2fa(
    request: Request,
    secret: str = Form(...),
    code: str = Form(...),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if not security_auth.verify_totp(secret, code):
        return RedirectResponse(
            "/profile"
            + _flash_qs(False, "Kode konfirmasi 2FA salah. Pastikan jam perangkat Anda akurat."),
            status_code=303,
        )

    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    user.totp_secret = secret.strip().replace(" ", "")
    user.totp_enabled = 1
    user.recovery_codes = json.dumps(hashed_codes)
    _audit(db, user.username, "2fa_enable", "profil sendiri", "berhasil")
    db.commit()

    return _render_profile_page(
        request=request,
        user=user,
        db=db,
        newly_generated_codes=plain_codes,
        flash_ok=True,
        flash_msg="2FA berhasil diaktifkan! Harap simpan kode cadangan darurat di bawah ini sekarang.",
    )


@router.post("/profile/2fa/disable")
def profile_disable_2fa(
    request: Request,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    user.totp_enabled = 0
    user.totp_secret = None
    user.recovery_codes = None
    _audit(db, user.username, "2fa_disable", "profil sendiri", "berhasil")
    db.commit()
    return RedirectResponse("/profile" + _flash_qs(True, "Perlindungan 2FA berhasil dinonaktifkan."), status_code=303)


@router.post("/profile/2fa/regenerate-recovery")
def profile_regenerate_recovery(
    request: Request,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer():
        return RedirectResponse("/", status_code=303)
    _verify_csrf_form(request, csrf_token)

    if not user.totp_enabled:
        return RedirectResponse("/profile" + _flash_qs(False, "2FA belum aktif"), status_code=303)

    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    user.recovery_codes = json.dumps(hashed_codes)
    _audit(db, user.username, "2fa_regen_recovery", "profil sendiri", "berhasil")
    db.commit()

    return _render_profile_page(
        request=request,
        user=user,
        db=db,
        newly_generated_codes=plain_codes,
        flash_ok=True,
        flash_msg="Kode cadangan darurat baru berhasil dibuat. Kode lama sudah tidak berlaku.",
    )


@router.post("/profile/branding")
async def profile_update_branding(
    request: Request,
    csrf_token: str = Form(default=""),
    org_name: str = Form(default=""),
    org_unit: str = Form(default=""),
    dash_motd: str = Form(default=""),
    show_motd: str = Form(default=""),
    remove_logo: str = Form(default=""),
    logo_file: UploadFile | None = File(default=None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Simpan identitas organisasi, logo, unit kerja, pesan operasional (MOTD), dan preferensi tampilan."""
    _verify_csrf_form(request, csrf_token)
    if not (user.is_master_admin() or user.role == "operator"):
        raise HTTPException(
            status_code=403, detail="Hanya Master Admin atau Operator yang dapat mengubah identitas sistem."
        )

    clean_org_name = (org_name or "").strip()[:100]
    clean_org_unit = (org_unit or "").strip()[:100]
    clean_dash_motd = (dash_motd or "").strip()[:500]
    is_show = True if show_motd in ("on", "1", "true", "True") else False

    current_brand = get_branding_settings(db)
    logo_url = current_brand.get("logo_url", "")

    upload_dir = Path(__file__).resolve().parent.parent / "static" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    if remove_logo in ("1", "true", "on"):
        for old_f in upload_dir.glob("org_logo_*"):
            try:
                old_f.unlink()
            except Exception:
                pass
        logo_url = ""

    if logo_file and logo_file.filename:
        filename = logo_file.filename.strip()
        if filename:
            ext = Path(filename).suffix.lower()
            ALLOWED_LOGO_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".ico"}
            if ext not in ALLOWED_LOGO_EXTS:
                return RedirectResponse(
                    _flash_profile_branding(
                        False, "Format logo harus berupa berkas gambar raster/aman (.png, .jpg, .jpeg, .webp, .ico)"
                    ),
                    status_code=303,
                )

            content = await logo_file.read()
            if len(content) > 2 * 1024 * 1024:
                return RedirectResponse(
                    _flash_profile_branding(False, "Ukuran berkas logo maksimal 2 MB"),
                    status_code=303,
                )

            if len(content) > 0:
                for old_f in upload_dir.glob("org_logo_*"):
                    try:
                        old_f.unlink()
                    except Exception:
                        pass

                ts = int(time.time())
                new_fname = f"org_logo_{ts}{ext}"
                target_path = upload_dir / new_fname
                target_path.write_bytes(content)
                logo_url = f"/static/uploads/{new_fname}?v={ts}"

    new_brand = {
        "org_name": clean_org_name,
        "org_unit": clean_org_unit,
        "dash_motd": clean_dash_motd,
        "show_motd": is_show,
        "logo_url": logo_url,
    }

    row = db.query(SystemSetting).filter(SystemSetting.key == "branding").first()
    if not row:
        row = SystemSetting(key="branding", value=json.dumps(new_brand), updated_at=datetime.utcnow())
        db.add(row)
    else:
        row.value = json.dumps(new_brand)
        row.updated_at = datetime.utcnow()

    _audit(
        db,
        user.username,
        "branding_update",
        target="Setel Organisasi",
        result=f"Disimpan (Organisasi: {clean_org_name or '-'}, Unit: {clean_org_unit or '-'}, Pengumuman: {'Aktif' if (is_show and clean_dash_motd) else 'Nonaktif'}, Logo: {'Ada' if logo_url else 'Bawaan'})",
    )
    db.commit()
    invalidate_branding_cache()

    return RedirectResponse(
        _flash_profile_branding(True, "Pengaturan organisasi berhasil disimpan."), status_code=303
    )


# ---------------------------------------------------------------------------
# USERS (RBAC 3-TIER: MASTER ADMIN, OPERATOR, VIEWER)
# ---------------------------------------------------------------------------
@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse("/login", status_code=303)
    if user.is_viewer() or not (
        user.is_master_admin() or user.has_perm("can_manage_users") or user.has_perm("can_manage_viewers")
    ):
        return RedirectResponse("/", status_code=303)
    return RedirectResponse("/profile?tab=users", status_code=303)


@router.post("/users/add")
async def user_add_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("viewer"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        return RedirectResponse("/profile?tab=users", status_code=303)
    _verify_csrf_form(request, csrf_token)

    username = username.strip()
    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,50}$", username):
        return RedirectResponse(
            _flash_profile_users(
                False, "Username harus 3-50 karakter alfanumerik (hanya huruf, angka, _, -, .)"
            ),
            status_code=303,
        )

    if not can_manage_users:
        role = "viewer"
    else:
        role = role if role in ("operator", "viewer") else "viewer"

    valid, err_msg = security_auth.validate_password_strength(password)
    if not valid:
        return RedirectResponse(_flash_profile_users(False, err_msg), status_code=303)

    if db.query(User).filter(User.username == username).first():
        return RedirectResponse(
            _flash_profile_users(False, f"Username '{username}' sudah digunakan"), status_code=303
        )

    perms_json = None
    if role == "operator":
        form_data = await request.form()
        perms_dict = {
            pk: bool(form_data.get(f"perm_{pk}")) for pk in security_auth.OPERATOR_PERMISSIONS
        }
        perms_json = json.dumps(perms_dict)

    new_u = User(
        username=username[:100],
        password_hash=pwd_ctx.hash(password),
        role=role,
        is_active=1,
        password_changed_at=datetime.utcnow(),
        permissions=perms_json,
        created_by=user.username,
    )
    db.add(new_u)
    _audit(db, user.username, "user_add", f"{username} (peran {role})", "berhasil")
    db.commit()
    return RedirectResponse(
        _flash_profile_users(
            True, f"Pengguna '{username}' berhasil didaftarkan sebagai {new_u.role_display()}"
        ),
        status_code=303,
    )


@router.post("/users/{uid}/edit")
async def user_edit_submit(
    request: Request,
    uid: int,
    username: str = Form(...),
    password: str = Form(default=""),
    confirm_password: str = Form(default=""),
    current_password: str = Form(default=""),
    role: str = Form("viewer"),
    is_active: str = Form(default="1"),
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if uid != user.id and not can_manage_viewers:
        return RedirectResponse("/profile?tab=users", status_code=303)
    _verify_csrf_form(request, csrf_token)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    if target_u.is_master_admin() and not user.is_master_admin():
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    if uid != user.id and not can_manage_users and target_u.role != "viewer":
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    clean_user = username.strip()
    if not re.match(r"^[a-zA-Z0-9_\-\.]{3,50}$", clean_user):
        return RedirectResponse(
            _flash_profile_users(
                False, "Username harus 3-50 karakter alfanumerik (hanya huruf, angka, _, -, .)"
            ),
            status_code=303,
        )

    if clean_user != target_u.username:
        if uid == user.id:
            cur_pwd = current_password.strip()
            if not cur_pwd or not pwd_ctx.verify(cur_pwd, user.password_hash):
                return RedirectResponse(
                    _flash_profile_users(False, "Kata sandi saat ini tidak cocok"), status_code=303
                )
        dup = db.query(User).filter(User.username == clean_user, User.id != uid).first()
        if dup:
            return RedirectResponse(
                _flash_profile_users(False, f"Username '{clean_user}' sudah dipakai pengguna lain"), status_code=303
            )
        target_u.username = clean_user[:100]

    pwd_clean = password.strip()
    if pwd_clean:
        if uid == user.id:
            cur_pwd = current_password.strip()
            if not cur_pwd or not pwd_ctx.verify(cur_pwd, user.password_hash):
                return RedirectResponse(
                    _flash_profile_users(False, "Kata sandi saat ini tidak cocok"), status_code=303
                )

        conf_pwd = confirm_password.strip()
        if pwd_clean != conf_pwd:
            return RedirectResponse(
                _flash_profile_users(False, "Konfirmasi kata sandi baru tidak cocok"), status_code=303
            )

        valid, err_msg = security_auth.validate_password_strength(pwd_clean)
        if not valid:
            return RedirectResponse(_flash_profile_users(False, err_msg), status_code=303)
        target_u.password_hash = pwd_ctx.hash(pwd_clean)
        target_u.password_changed_at = datetime.utcnow()
        if uid == user.id:
            cur_sid = request.cookies.get(SESSION_COOKIE)
            db.query(AppSession).filter(AppSession.user_id == uid, AppSession.sid != cur_sid).delete(
                synchronize_session=False
            )
        else:
            db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)

    if not target_u.is_master_admin() and uid != user.id:
        new_act = 1 if is_active in ("1", "true", "on") else 0
        if not new_act and target_u.is_active:
            db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)
        target_u.is_active = new_act

    if not target_u.is_master_admin() and uid != user.id:
        if role in ("operator", "viewer"):
            target_u.role = role
        if target_u.role == "operator":
            form_data = await request.form()
            perms_dict = {
                pk: bool(form_data.get(f"perm_{pk}")) for pk in security_auth.OPERATOR_PERMISSIONS
            }
            target_u.permissions = json.dumps(perms_dict)
        else:
            target_u.permissions = None

    _audit(db, user.username, "user_edit", f"{target_u.username} ({target_u.role})", "berhasil")
    db.commit()
    return RedirectResponse(
        _flash_profile_users(True, f"Akun '{target_u.username}' berhasil diperbarui"), status_code=303
    )


@router.post("/users/{uid}/delete")
def user_delete(
    request: Request,
    uid: int,
    csrf_token: str = Form(default=""),
    password: str = Form(default=""),
    totp: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or user.is_viewer():
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/profile?tab=users", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)

    if uid == user.id:
        msg = "Tidak bisa menghapus akun Anda sendiri"
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=400)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        msg = "Pengguna tidak ditemukan"
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=404)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    if target_u.is_master_admin():
        msg = (
            "Akun Master Administrator tidak dapat dihapus"
            if user.is_master_admin()
            else "Pengguna tidak ditemukan"
        )
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=400)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    if not can_manage_users and target_u.role != "viewer":
        msg = "Pengguna tidak ditemukan"
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=404)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    try:
        _verify_operator_password(
            user,
            password,
            totp_code=totp,
            action_name="user_delete",
            target_info=f"{target_u.username} ({target_u.role})",
            db=db,
        )
    except HTTPException as exc:
        if is_json:
            return JSONResponse({"ok": False, "detail": exc.detail}, status_code=exc.status_code)
        return RedirectResponse(_flash_profile_users(False, exc.detail), status_code=303)

    db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)

    _audit(db, user.username, "user_delete", f"{target_u.username} ({target_u.role})", "berhasil")
    db.delete(target_u)
    db.commit()
    msg = f"Pengguna '{target_u.username}' berhasil dihapus"
    if is_json:
        return JSONResponse({"ok": True, "detail": msg})
    return RedirectResponse(_flash_profile_users(True, msg), status_code=303)


@router.post("/users/{uid}/toggle-active")
def user_toggle_active(
    request: Request,
    uid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    is_json = "application/json" in request.headers.get("accept", "")
    if not user or user.is_viewer():
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/", status_code=303)
    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        if is_json:
            return JSONResponse({"ok": False, "detail": "Akses ditolak"}, status_code=403)
        return RedirectResponse("/profile?tab=users", status_code=303)
    token = csrf_token or request.headers.get("X-CSRF-Token", "")
    _verify_csrf_form(request, token)

    if uid == user.id:
        msg = "Tidak bisa menonaktifkan akun sendiri"
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=400)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        msg = "Pengguna tidak ditemukan"
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=404)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    if target_u.is_master_admin():
        msg = (
            "Status akun Master Administrator tidak dapat diubah"
            if user.is_master_admin()
            else "Pengguna tidak ditemukan"
        )
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=400)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    if not can_manage_users and target_u.role != "viewer":
        msg = "Pengguna tidak ditemukan"
        if is_json:
            return JSONResponse({"ok": False, "detail": msg}, status_code=404)
        return RedirectResponse(_flash_profile_users(False, msg), status_code=303)

    new_active = 0 if target_u.is_active else 1
    target_u.is_active = new_active
    status_label = "diaktifkan" if new_active else "dikunci/dinonaktifkan"

    if not new_active:
        db.query(AppSession).filter(AppSession.user_id == uid).delete(synchronize_session=False)

    _audit(db, user.username, "user_toggle_active", f"{target_u.username} ({status_label})", "berhasil")
    db.commit()
    msg = f"Akun '{target_u.username}' berhasil {status_label}"
    if is_json:
        return JSONResponse({"ok": True, "detail": msg, "is_active": bool(new_active)})
    return RedirectResponse(_flash_profile_users(True, msg), status_code=303)


@router.post("/users/{uid}/edit-permissions")
async def user_edit_permissions(
    request: Request,
    uid: int,
    csrf_token: str = Form(default=""),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user or user.is_viewer():
        return RedirectResponse("/", status_code=303)
    if not user.is_master_admin():
        return RedirectResponse(
            _flash_profile_users(False, "Hanya Master Admin yang berhak mengelola wewenang operator"),
            status_code=303,
        )
    if uid == user.id:
        return RedirectResponse(
            _flash_profile_users(False, "Anda tidak dapat mengubah wewenang akun Anda sendiri"),
            status_code=303,
        )
    _verify_csrf_form(request, csrf_token)

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u or target_u.role != "operator":
        return RedirectResponse(_flash_profile_users(False, "Pengguna tidak ditemukan"), status_code=303)

    form_data = await request.form()
    perms_dict = {
        pk: bool(form_data.get(f"perm_{pk}")) for pk in security_auth.OPERATOR_PERMISSIONS
    }
    target_u.permissions = json.dumps(perms_dict)
    _audit(db, user.username, "user_edit_perms", f"{target_u.username} (wewenang diperbarui)", "berhasil")
    db.commit()
    return RedirectResponse(
        _flash_profile_users(
            True, f"Wewenang untuk operator '{target_u.username}' berhasil diperbarui"
        ),
        status_code=303,
    )


# ---------------------------------------------------------------------------
# MANAGED 2FA (ADMIN/OPERATOR CONTROLLED TOTP)
# ---------------------------------------------------------------------------
@router.post("/api/users/{uid}/2fa/init")
def api_user_2fa_init(
    request: Request,
    uid: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Inisialisasi pengaturan 2FA TOTP untuk pengguna (khusus Master Admin & Operator)."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin manajemen pengguna")

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        raise HTTPException(status_code=403, detail="Akses ditolak: izin manajemen pengguna diperlukan")

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    if target_u.is_master_admin() and not user.is_master_admin():
        raise HTTPException(status_code=403, detail="Akses ditolak: tidak dapat mengubah akun Master Admin")

    if not can_manage_users and target_u.role != "viewer":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya berwenang mengelola akun Viewer")

    secret = security_auth.generate_totp_secret()
    secret_display = security_auth.format_secret_display(secret)
    uri = security_auth.generate_totp_uri(secret, target_u.username, "Pantau Server")
    qr_data_url = security_auth.generate_qr_data_url(uri)

    return {
        "ok": True,
        "user_id": target_u.id,
        "username": target_u.username,
        "role": target_u.role,
        "secret": secret,
        "secret_display": secret_display,
        "qr_data_url": qr_data_url,
    }


@router.post("/api/users/{uid}/2fa/confirm")
def api_user_2fa_confirm(
    request: Request,
    uid: int,
    body: dict = Body(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Verifikasi 6-digit kode TOTP dari ponsel pengguna dan aktifkan 2FA secara permanen."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin manajemen pengguna")

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        raise HTTPException(status_code=403, detail="Akses ditolak: izin manajemen pengguna diperlukan")

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    if target_u.is_master_admin() and not user.is_master_admin():
        raise HTTPException(status_code=403, detail="Akses ditolak: tidak dapat mengubah akun Master Admin")

    if not can_manage_users and target_u.role != "viewer":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya berwenang mengelola akun Viewer")

    secret = str(body.get("secret", "")).strip().replace(" ", "")
    code = str(body.get("code", "")).strip().replace(" ", "")

    if not secret or not code:
        raise HTTPException(status_code=400, detail="Kunci rahasia (secret) dan kode verifikasi 6-digit wajib diisi")

    if not security_auth.verify_totp(secret, code):
        raise HTTPException(
            status_code=400,
            detail="Kode verifikasi 6-digit salah atau jam perangkat ponsel pengguna tidak sinkron.",
        )

    plain_codes, hashed_codes = security_auth.generate_recovery_codes(8)
    target_u.totp_secret = secret
    target_u.totp_enabled = 1
    target_u.recovery_codes = json.dumps(hashed_codes)

    _audit(
        db,
        user.username,
        "user_2fa_enable",
        f"Pengguna {target_u.username} ({target_u.role})",
        "2FA berhasil diaktifkan oleh admin",
    )
    db.commit()

    return {
        "ok": True,
        "message": f"Perlindungan 2FA untuk pengguna '{target_u.username}' berhasil diaktifkan!",
        "recovery_codes": plain_codes,
        "username": target_u.username,
    }


@router.post("/api/users/{uid}/2fa/disable")
def api_user_2fa_disable(
    request: Request,
    uid: int,
    body: dict = Body(default={}),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    """Nonaktifkan perlindungan 2FA untuk pengguna yang ditentukan."""
    _verify_csrf_header(request)
    if user.is_viewer():
        raise HTTPException(status_code=403, detail="Akses ditolak: Viewer tidak memiliki izin manajemen pengguna")

    can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")
    can_manage_viewers = can_manage_users or user.has_perm("can_manage_viewers")
    if not can_manage_viewers:
        raise HTTPException(status_code=403, detail="Akses ditolak: izin manajemen pengguna diperlukan")

    target_u = db.query(User).filter(User.id == uid).first()
    if not target_u:
        raise HTTPException(status_code=404, detail="Pengguna tidak ditemukan")

    if target_u.is_master_admin() and not user.is_master_admin():
        raise HTTPException(status_code=403, detail="Akses ditolak: tidak dapat mengubah akun Master Admin")

    if not can_manage_users and target_u.role != "viewer":
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya berwenang mengelola akun Viewer")

    _verify_operator_password(
        user,
        body.get("password", ""),
        totp_code=body.get("totp", ""),
        action_name="user_2fa_disable",
        target_info=f"Pengguna {target_u.username} ({target_u.role})",
        db=db,
    )

    target_u.totp_enabled = 0
    target_u.totp_secret = None
    target_u.recovery_codes = None

    _audit(
        db,
        user.username,
        "user_2fa_disable",
        f"Pengguna {target_u.username} ({target_u.role})",
        "2FA dinonaktifkan oleh admin",
    )
    db.commit()

    return {
        "ok": True,
        "message": f"Perlindungan 2FA untuk pengguna '{target_u.username}' telah dinonaktifkan.",
        "username": target_u.username,
    }
