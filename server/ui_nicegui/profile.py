"""
Modul Akun Pengguna, Keamanan 2FA, & Setel Organisasi (Branding)
===============================================================
Menyediakan antarmuka manajemen profil akun mandiri, perubahan kata sandi
berstandar NIST SP 800-63B, wizard autentikasi dua faktor (2FA TOTP),
regenerasi kode pemulihan darurat, serta penyesuaian identitas organisasi
resmi (dash-org-header & branding).
"""

from datetime import datetime
import json
import os
from pathlib import Path
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from passlib.context import CryptContext

from config import settings
from models import AuditLog, SystemSetting, User
from security_auth import (
    format_secret_display,
    generate_qr_data_url,
    generate_recovery_codes,
    generate_totp_secret,
    generate_totp_uri,
    validate_password_strength,
    verify_totp,
)
from .auth import get_auth_user
from .common import get_db, notify_error, notify_info, notify_success
from .layout import render_layout

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_profile_routes(session_factory):
    """Mendaftarkan rute profil pengguna & keamanan ke NiceGUI engine."""

    @ui.page("/profile")
    def page_profile(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username
            can_manage_branding = user.is_master_admin() or user.is_operator()
            u_role = user.role_display()
            u_created = user.created_at.strftime("%d %b %Y %H:%M") if user.created_at else "—"
            u_last_login = user.last_login_at.strftime("%d %b %Y %H:%M:%S") if user.last_login_at else "—"
            u_last_ip = user.last_login_ip or "Lokal"
            totp_active = bool(user.totp_enabled)

            # Ambil branding data
            brand_row = db.query(SystemSetting).filter(SystemSetting.key == "branding").first()
            brand_data = {}
            if brand_row and brand_row.value:
                try:
                    brand_data = json.loads(brand_row.value)
                except Exception:
                    pass

        with render_layout(request, user, active_tab="profile"):
            container = ui.column().classes("w-full gap-4")

            # -----------------------------------------------------------------
            # Dialog Modal: Tampilkan Kode Pemulihan 2FA Baru
            # -----------------------------------------------------------------
            codes_dlg = ui.dialog()
            codes_state = {"codes": []}

            with codes_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4 border border-amber-500/50"):
                with ui.row().classes("items-center gap-2 text-amber-400"):
                    ui.icon("vpn_key", size="24px")
                    ui.label("Kode Pemulihan Darurat 2FA").classes("text-base font-bold text-white")

                with ui.card().classes("w-full p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-200"):
                    ui.label("Simpan kode-kode ini di tempat yang aman sekarang! Setiap kode hanya dapat digunakan 1 kali untuk login jika Anda kehilangan akses ke aplikasi autentikator.")

                codes_grid = ui.column().classes("w-full grid grid-cols-2 gap-2 bg-slate-950 p-4 rounded border border-slate-800")

                def _copy_all_codes():
                    raw_text = "\n".join(codes_state["codes"])
                    ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(raw_text)})")
                    notify_success("Seluruh 8 kode pemulihan berhasil disalin ke clipboard.")

                with ui.row().classes("w-full justify-between items-center mt-2"):
                    ui.button("Salin Semua Kode", icon="content_copy", on_click=_copy_all_codes).props("dense outline size=sm color=amber-4 no-caps")
                    ui.button("Tutup & Selesai", on_click=lambda: (codes_dlg.close(), ui.navigate.to("/profile"))).props("dense unelevated size=sm color=primary no-caps")

            def _open_codes_dialog(plain_codes: list[str]):
                codes_state["codes"] = plain_codes
                codes_grid.clear()
                with codes_grid:
                    for c in plain_codes:
                        ui.label(c).classes("font-mono text-xs text-emerald-400 font-bold p-1 bg-slate-900 rounded border border-slate-800 text-center select-all")
                codes_dlg.open()

            # -----------------------------------------------------------------
            # Dialog Modal: Wizard Setup 2FA TOTP
            # -----------------------------------------------------------------
            setup_2fa_dlg = ui.dialog()
            setup_state = {"secret": "", "uri": ""}

            with setup_2fa_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-primary"):
                ui.label("Aktivasi Autentikasi Dua Langkah (2FA)").classes("text-base font-bold text-white")
                ui.label("Pindai kode QR di bawah ini menggunakan aplikasi Google Authenticator atau sejenisnya:").classes("text-xs text-slate-300 leading-relaxed")

                qr_container = ui.row().classes("w-full justify-center p-3 bg-white rounded")
                with qr_container:
                    qr_img = ui.image("").classes("w-48 h-48")

                secret_display_lbl = ui.label("").classes("font-mono text-[11px] text-center text-amber-300 bg-slate-950 p-2 rounded border border-slate-800 select-all")

                ui.label("Masukkan Kode 6 Digit Verifikasi:").classes("text-xs font-semibold text-slate-400 mt-2")
                inp_totp_code = ui.input(placeholder="mis. 123456").classes("w-full").props("dense outlined dark text-center font-mono text-lg maxlength=6")

                def _confirm_enable_2fa():
                    code_val = inp_totp_code.value.strip().replace(" ", "")
                    if not code_val or len(code_val) != 6:
                        notify_error("Masukkan 6 digit kode dari aplikasi autentikator.")
                        return

                    if not verify_totp(setup_state["secret"], code_val):
                        notify_error("Kode TOTP salah atau kedaluwarsa. Periksa sinkronisasi jam perangkat Anda.")
                        return

                    plain_codes, hashed_codes = generate_recovery_codes()

                    with get_db(session_factory) as db:
                        u = db.query(User).filter(User.id == current_user_id).first()
                        if u:
                            u.totp_secret = setup_state["secret"]
                            u.totp_enabled = 1
                            u.recovery_codes = json.dumps(hashed_codes)
                            audit = AuditLog(
                                user_id=current_user_id,
                                username=current_username,
                                action="enable_2fa",
                                target=current_username,
                                result="berhasil",
                            )
                            db.add(audit)
                            db.commit()

                    setup_2fa_dlg.close()
                    notify_success("Autentikasi Dua Langkah (2FA) berhasil diaktifkan!")
                    _open_codes_dialog(plain_codes)

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=setup_2fa_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Verifikasi & Aktifkan", icon="check", on_click=_confirm_enable_2fa).props("dense unelevated color=primary no-caps")

            def _open_setup_2fa_dialog():
                sec = generate_totp_secret()
                uri = generate_totp_uri(sec, current_username, issuer="Pantau Server")
                qr_data = generate_qr_data_url(uri)
                setup_state["secret"] = sec
                setup_state["uri"] = uri
                qr_img.set_source(qr_data)
                secret_display_lbl.set_text(f"Kunci Rahasia: {format_secret_display(sec)}")
                inp_totp_code.set_value("")
                setup_2fa_dlg.open()

            # -----------------------------------------------------------------
            # Dialog Modal: Konfirmasi Nonaktifkan 2FA
            # -----------------------------------------------------------------
            disable_2fa_dlg = ui.dialog()
            with disable_2fa_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/40"):
                ui.label("Nonaktifkan Autentikasi Dua Langkah (2FA)").classes("text-base font-bold text-white")
                ui.label("Masukkan kata sandi akun Anda untuk mengonfirmasi penonaktifan perlindungan 2FA:").classes("text-xs text-slate-300")
                with ui.column().classes("w-full gap-1"):
                    ui.label("KATA SANDI AKUN *").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                    inp_dis_pwd = ui.input(password=True, password_toggle_button=True).classes("w-full").props("dense outlined dark")

                def _confirm_disable_2fa():
                    pwd_val = inp_dis_pwd.value.strip()
                    if not pwd_val:
                        notify_error("Kata sandi wajib diisi.")
                        return
                    with get_db(session_factory) as db:
                        u = db.query(User).filter(User.id == current_user_id).first()
                        if not u or not pwd_ctx.verify(pwd_val, u.password_hash):
                            notify_error("Kata sandi salah.")
                            return
                        u.totp_enabled = 0
                        u.totp_secret = None
                        u.recovery_codes = None
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            action="disable_2fa",
                            target=current_username,
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                    disable_2fa_dlg.close()
                    notify_info("Perlindungan 2FA telah dinonaktifkan.")
                    ui.navigate.to("/profile")

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=disable_2fa_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Nonaktifkan 2FA", icon="lock_open", on_click=_confirm_disable_2fa).props("dense unelevated color=negative no-caps")

            # -----------------------------------------------------------------
            # Dialog Modal: Regenerasi Kode Pemulihan 2FA
            # -----------------------------------------------------------------
            regen_codes_dlg = ui.dialog()
            with regen_codes_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                ui.label("Regenerasi Kode Pemulihan 2FA").classes("text-base font-bold text-white")
                ui.label("Kode pemulihan lama akan seketika hangus. Masukkan kata sandi akun Anda untuk melanjutkan:").classes("text-xs text-slate-300")
                with ui.column().classes("w-full gap-1"):
                    ui.label("KATA SANDI AKUN *").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                    inp_reg_pwd = ui.input(password=True, password_toggle_button=True).classes("w-full").props("dense outlined dark")

                def _confirm_regen_codes():
                    pwd_val = inp_reg_pwd.value.strip()
                    if not pwd_val:
                        notify_error("Kata sandi wajib diisi.")
                        return
                    plain_codes, hashed_codes = generate_recovery_codes()
                    with get_db(session_factory) as db:
                        u = db.query(User).filter(User.id == current_user_id).first()
                        if not u or not pwd_ctx.verify(pwd_val, u.password_hash):
                            notify_error("Kata sandi salah.")
                            return
                        u.recovery_codes = json.dumps(hashed_codes)
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            action="regenerate_recovery_codes",
                            target=current_username,
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                    regen_codes_dlg.close()
                    notify_success("Kode pemulihan darurat baru berhasil dibuat.")
                    _open_codes_dialog(plain_codes)

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=regen_codes_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Regenerasi Kode", icon="vpn_key", on_click=_confirm_regen_codes).props("dense unelevated color=primary no-caps")

            # -----------------------------------------------------------------
            # TAMPILAN HALAMAN PROFIL
            # -----------------------------------------------------------------
            with container:
                # Topbar
                ui.html("""
                <div class="topbar">
                  <div>
                    <h2 style="font-size:18px;margin:0">Akun Pengguna &amp; Keamanan Sistem</h2>
                    <div style="font-size:12px;color:var(--dim);margin-top:2px">Kelola kredensial login, autentikasi dua langkah (2FA), pengguna NOC, serta identitas resmi organisasi.</div>
                  </div>
                </div>
                """)

                req_tab = request.query_params.get("tab", "account").lower()
                can_manage_users = user.is_master_admin() or user.has_perm("can_manage_users")

                # Tab Navigation
                with ui.tabs().classes("w-full bg-slate-900 border border-slate-800 rounded").props("dense inline-label active-color=primary indicator-color=primary align=left") as tabs:
                    tab_acc = ui.tab("account", label="Profil & Kredensial", icon="account_circle")
                    tab_sec = ui.tab("security", label="Keamanan & 2FA", icon="security")
                    if can_manage_users:
                        tab_users = ui.tab("users", label="Manajemen Pengguna", icon="people")
                    if can_manage_branding:
                        tab_brand = ui.tab("branding", label="Setel Organisasi", icon="corporate_fare")

                init_val = req_tab if req_tab in ("account", "security", "users", "branding") else "account"
                with ui.tab_panels(tabs, value=init_val).classes("w-full bg-transparent p-0"):

                    # Tab 1: Akun & Kredensial
                    with ui.tab_panel("account").classes("p-0 pt-3"):
                        with ui.row().classes("w-full grid grid-cols-1 md:grid-cols-3 gap-4"):
                            # Panel 1: Info Akun
                            with ui.card().classes("p-5 custom-card flex flex-col justify-between gap-4"):
                                with ui.column().classes("gap-3"):
                                    with ui.row().classes("items-center gap-3"):
                                        ui.icon("account_circle", size="42px").classes("text-sky-400")
                                        with ui.column().classes("gap-0"):
                                            ui.label(current_username).classes("text-lg font-bold text-white")
                                            ui.badge(u_role.upper(), color="blue-9").classes("text-[9px] font-bold px-2 py-0.5")

                                    ui.separator().classes("bg-slate-800")

                                    with ui.column().classes("gap-2 text-xs"):
                                        with ui.row().classes("justify-between w-full"):
                                            ui.label("Status 2FA:").classes("text-slate-400")
                                            ui.badge("AKTIF" if totp_active else "NONAKTIF", color="emerald-9" if totp_active else "rose-9").classes("text-[9px] font-bold")

                                        with ui.row().classes("justify-between w-full"):
                                            ui.label("Terdaftar:").classes("text-slate-400")
                                            ui.label(u_created).classes("text-slate-200 font-mono")

                                        with ui.row().classes("justify-between w-full"):
                                            ui.label("Login Terakhir:").classes("text-slate-400")
                                            ui.label(u_last_login).classes("text-slate-200 font-mono")

                                        with ui.row().classes("justify-between w-full"):
                                            ui.label("IP Login:").classes("text-slate-400")
                                            ui.label(u_last_ip).classes("text-slate-200 font-mono")

                            # Panel 2: Ganti Password
                            with ui.card().classes("md:col-span-2 p-5 custom-card flex flex-col gap-4"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("lock", size="20px").classes("text-sky-400")
                                    ui.label("Perbarui Kata Sandi (NIST SP 800-63B)").classes("text-sm font-bold text-white")

                                with ui.column().classes("w-full gap-3"):
                                    with ui.column().classes("w-full gap-1"):
                                        ui.label("KATA SANDI SAAT INI *").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                                        inp_cur_pwd = ui.input(password=True, password_toggle_button=True).classes("w-full").props("dense outlined dark")

                                    with ui.column().classes("w-full gap-1"):
                                        ui.label("KATA SANDI BARU *").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                                        inp_new_pwd = ui.input(password=True, password_toggle_button=True, placeholder="Minimal 8 karakter").classes("w-full").props("dense outlined dark")

                                    with ui.column().classes("w-full gap-1"):
                                        ui.label("KONFIRMASI KATA SANDI BARU *").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                                        inp_cf_pwd = ui.input(password=True, password_toggle_button=True).classes("w-full").props("dense outlined dark")

                                def _change_password():
                                    c_pwd = inp_cur_pwd.value.strip()
                                    n_pwd = inp_new_pwd.value.strip()
                                    cf_pwd = inp_cf_pwd.value.strip()

                                    if not c_pwd or not n_pwd or not cf_pwd:
                                        notify_error("Seluruh kolom kata sandi wajib diisi.")
                                        return

                                    if n_pwd != cf_pwd:
                                        notify_error("Konfirmasi kata sandi baru tidak cocok.")
                                        return

                                    valid, msg = validate_password_strength(n_pwd)
                                    if not valid:
                                        notify_error(msg)
                                        return

                                    with get_db(session_factory) as db:
                                        u = db.query(User).filter(User.id == current_user_id).first()
                                        if not u or not pwd_ctx.verify(c_pwd, u.password_hash):
                                            notify_error("Kata sandi saat ini salah.")
                                            return

                                        u.password_hash = pwd_ctx.hash(n_pwd)
                                        u.password_changed_at = datetime.utcnow()
                                        audit = AuditLog(
                                            user_id=current_user_id,
                                            username=current_username,
                                            action="change_password",
                                            target=current_username,
                                            result="berhasil",
                                        )
                                        db.add(audit)
                                        db.commit()

                                    inp_cur_pwd.set_value("")
                                    inp_new_pwd.set_value("")
                                    inp_cf_pwd.set_value("")
                                    notify_success("Kata sandi akun Anda berhasil diperbarui.")

                                with ui.row().classes("w-full justify-end mt-3 pr-2"):
                                    ui.button("Perbarui Kata Sandi", icon="save", on_click=_change_password).props("dense unelevated color=primary no-caps").classes("px-3")

                    # Tab 2: Keamanan 2FA
                    with ui.tab_panel("security").classes("p-0 pt-3"):
                        with ui.card().classes("w-full p-5 custom-card flex flex-col gap-4"):
                            with ui.row().classes("w-full items-center justify-between"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("security", size="22px").classes("text-emerald-400" if totp_active else "text-amber-400")
                                    ui.label("Perlindungan Autentikasi Dua Langkah (2FA TOTP)").classes("text-sm font-bold text-white")
                                ui.badge("AKTIF" if totp_active else "TIDAK AKTIF", color="emerald-9" if totp_active else "slate-7").classes("text-[10px] font-bold px-2 py-0.5")

                            if totp_active:
                                with ui.card().classes("w-full p-4 bg-emerald-500/10 border border-emerald-500/30 rounded"):
                                    ui.label("Akun Anda telah diamankan dengan autentikasi dua faktor. Setiap kali masuk, Anda wajib memasukkan kode satu kali (TOTP) dari aplikasi autentikator.").classes("text-xs text-emerald-200")

                                with ui.row().classes("gap-2 mt-2"):
                                    ui.button("Regenerasi Kode Pemulihan", icon="vpn_key", on_click=regen_codes_dlg.open).props("dense outline size=sm color=amber-4 no-caps").classes("text-xs")
                                    ui.button("Nonaktifkan 2FA", icon="lock_open", on_click=disable_2fa_dlg.open).props("dense outline size=sm color=rose-4 no-caps").classes("text-xs")
                            else:
                                with ui.card().classes("w-full p-4 bg-slate-950 border border-slate-800 rounded"):
                                    ui.label("Autentikasi dua langkah belum aktif pada akun ini. Sangat disarankan untuk mengaktifkan 2FA guna mencegah akses ilegal dari kebocoran kata sandi.").classes("text-xs text-slate-300")

                                with ui.row().classes("mt-2"):
                                    ui.button("Aktifkan 2FA TOTP Sekarang", icon="verified_user", on_click=_open_setup_2fa_dialog).props("dense unelevated size=sm color=primary no-caps").classes("text-xs font-semibold")

                    # Tab 3: Manajemen Pengguna (Admin / Operator)
                    if can_manage_users:
                        with ui.tab_panel("users").classes("p-0 pt-3"):
                            with ui.card().classes("w-full p-5 custom-card flex flex-col gap-4"):
                                with ui.row().classes("w-full items-center justify-between"):
                                    with ui.column().classes("gap-0"):
                                        ui.label("Manajemen Akun Pengguna & Hak Akses (RBAC)").classes("text-sm font-bold text-white")
                                        ui.label("Kelola pengguna terdaftar, peran akses, dan status operasional").classes("text-xs text-slate-400")

                                    ui.button("Buka Kelola Pengguna Lengkap", icon="manage_accounts", on_click=lambda: ui.navigate.to("/users")).props("dense unelevated size=sm color=primary no-caps").classes("text-xs font-semibold")

                                with get_db(session_factory) as db:
                                    all_u = db.query(User).order_by(User.id.asc()).all()
                                    u_rows = []
                                    for item in all_u:
                                        u_rows.append({
                                            "id": item.id,
                                            "username": item.username,
                                            "role": item.role_display(),
                                            "is_active": "Aktif" if item.is_active else "Nonaktif",
                                            "totp": "Aktif" if item.totp_enabled else "Nonaktif",
                                            "created_at": item.created_at.strftime("%d %b %Y") if item.created_at else "—",
                                        })

                                u_cols = [
                                    {"name": "username", "label": "PENGGUNA", "field": "username", "align": "left"},
                                    {"name": "role", "label": "PERAN", "field": "role", "align": "center"},
                                    {"name": "is_active", "label": "STATUS", "field": "is_active", "align": "center"},
                                    {"name": "totp", "label": "2FA", "field": "totp", "align": "center"},
                                    {"name": "created_at", "label": "TERDAFTAR", "field": "created_at", "align": "center"},
                                ]
                                utbl = ui.table(columns=u_cols, rows=u_rows, row_key="id").classes("w-full bg-slate-900").props("dense")
                                utbl.add_slot("body-cell-role", """
                                    <q-td :props="props">
                                        <q-badge :color="props.row.role === 'Master Admin' ? 'rose-9' : (props.row.role === 'Operator' ? 'blue-9' : 'slate-7')" class="text-[9px] font-bold px-1.5 py-0.5">
                                            {{ props.row.role }}
                                        </q-badge>
                                    </q-td>
                                """)

                    # Tab 4: Setel Organisasi (Branding)
                    if can_manage_branding:
                        with ui.tab_panel("branding").classes("p-0 pt-3"):
                            with ui.card().classes("w-full max-w-2xl p-5 custom-card flex flex-col gap-4"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.icon("corporate_fare", size="22px").classes("text-primary")
                                    ui.label("Identitas Resmi Organisasi & Branding Sistem").classes("text-sm font-bold text-white")

                                ui.label("Sesuaikan nama organisasi, unit kerja, serta logo resmi yang ditampilkan pada header dashboard.").classes("text-xs text-slate-400")

                                with ui.column().classes("w-full gap-3"):
                                    with ui.column().classes("w-full gap-1"):
                                        ui.label("NAMA ORGANISASI *").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                                        inp_org_name = ui.input(value=brand_data.get("org_name", "")).classes("w-full").props("dense outlined dark")

                                    with ui.column().classes("w-full gap-1"):
                                        ui.label("UNIT KERJA / BIDANG").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                                        inp_org_unit = ui.input(value=brand_data.get("org_unit", "")).classes("w-full").props("dense outlined dark")

                                    with ui.column().classes("w-full gap-1"):
                                        ui.label("PESAN OPERASIONAL / PENGUMUMAN (MOTD)").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                                        inp_motd = ui.textarea(value=brand_data.get("dash_motd", "")).classes("w-full").props("dense outlined dark rows=2")

                                    cb_motd = ui.checkbox("Tampilkan Pesan Pengumuman pada Dashboard", value=brand_data.get("show_motd", False)).props("dense dark")

                                def _save_branding():
                                    with get_db(session_factory) as db:
                                        row = db.query(SystemSetting).filter(SystemSetting.key == "branding").first()
                                        if not row:
                                            row = SystemSetting(key="branding", value="{}")
                                            db.add(row)
                                        current = {}
                                        try:
                                            current = json.loads(row.value or "{}")
                                        except Exception:
                                            pass
                                        current["org_name"] = inp_org_name.value.strip()
                                        current["org_unit"] = inp_org_unit.value.strip()
                                        current["dash_motd"] = inp_motd.value.strip()
                                        current["show_motd"] = bool(cb_motd.value)
                                        row.value = json.dumps(current)

                                        audit = AuditLog(
                                            user_id=current_user_id,
                                            username=current_username,
                                            action="branding_update",
                                            target="Setel Organisasi",
                                            result=f"Disimpan (Org: {current['org_name']})",
                                        )
                                        db.add(audit)
                                        db.commit()

                                    notify_success("Setelan identitas organisasi berhasil disimpan!")

                                with ui.row().classes("w-full justify-end mt-2"):
                                    ui.button("Simpan Setelan Organisasi", icon="save", on_click=_save_branding).props("dense unelevated color=primary no-caps")
