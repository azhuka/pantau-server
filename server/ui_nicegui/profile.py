"""
Modul Profil Akun & Keamanan (Personal Profile & 2FA TOTP Settings)
===================================================================
Menyediakan pengelolaan identitas akun pribadi, pembaruan kata sandi
standar NIST, konfigurasi autentikasi dua faktor (2FA TOTP via QR Code),
serta pencetakan & pengelolaan kode pemulihan darurat (Emergency Recovery Codes).
"""

from datetime import datetime
import json
from nicegui import ui
from passlib.context import CryptContext
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, User
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
    """Mendaftarkan rute profil pengguna dan 2FA ke NiceGUI engine."""

    @ui.page("/profile")
    def page_profile(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username
            u_role = user.role_display()
            u_created = user.created_at.strftime("%d %b %Y %H:%M") if user.created_at else "—"
            u_last_login = user.last_login_at.strftime("%d %b %Y %H:%M:%S") if user.last_login_at else "—"
            u_last_ip = user.last_login_ip or "Lokal"
            totp_active = bool(user.totp_enabled)

        render_layout(request, user, active_tab="")

        container = ui.column().classes("w-full max-w-5xl mx-auto p-6 gap-6")

        # ---------------------------------------------------------------------
        # Dialog Modal: Tampilkan Kode Pemulihan 2FA Baru
        # ---------------------------------------------------------------------
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
                    ui.label(c).classes("font-mono text-xs font-bold text-sky-400 bg-slate-900 px-3 py-1.5 rounded text-center border border-slate-800")
            codes_dlg.open()

        # ---------------------------------------------------------------------
        # Dialog Modal: Wizard Aktivasi 2FA TOTP
        # ---------------------------------------------------------------------
        setup_2fa_dlg = ui.dialog()
        setup_state = {"secret": "", "uri": ""}

        with setup_2fa_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
            ui.label("Aktivasi Autentikasi Dua Langkah (2FA)").classes("text-base font-bold text-white")
            ui.label("Pindai kode QR berikut menggunakan aplikasi Google Authenticator, Authy, atau 1Password:").classes("text-xs text-slate-300")

            qr_img = ui.image().classes("w-48 h-48 mx-auto rounded border border-slate-700 bg-white p-2")
            secret_display_lbl = ui.label("").classes("font-mono text-xs text-center text-amber-400 select-all")

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

                # Sukses verifikasi, buat recovery codes
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

        # ---------------------------------------------------------------------
        # Dialog Modal: Konfirmasi Nonaktifkan 2FA
        # ---------------------------------------------------------------------
        disable_2fa_dlg = ui.dialog()
        with disable_2fa_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/40"):
            ui.label("Nonaktifkan Autentikasi Dua Langkah (2FA)").classes("text-base font-bold text-white")
            ui.label("Masukkan kata sandi akun Anda untuk mengonfirmasi penonaktifan perlindungan 2FA:").classes("text-xs text-slate-300")
            inp_dis_pwd = ui.input("Kata Sandi Akun", password=True).classes("w-full").props("dense outlined dark")

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

        # ---------------------------------------------------------------------
        # Dialog Modal: Regenerasi Kode Pemulihan 2FA
        # ---------------------------------------------------------------------
        regen_codes_dlg = ui.dialog()
        with regen_codes_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
            ui.label("Regenerasi Kode Pemulihan 2FA").classes("text-base font-bold text-white")
            ui.label("Kode pemulihan lama akan seketika hangus. Masukkan kata sandi akun Anda untuk melanjutkan:").classes("text-xs text-slate-300")
            inp_reg_pwd = ui.input("Kata Sandi Akun", password=True).classes("w-full").props("dense outlined dark")

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

        # ---------------------------------------------------------------------
        # TAMPILAN HALAMAN PROFIL
        # ---------------------------------------------------------------------
        with container:
            # Header
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Akun Pengguna & Keamanan").classes("text-xl font-bold text-white")
                    ui.label("Kelola kredensial akun, perlindungan dua langkah (2FA), dan riwayat akses").classes("text-xs text-slate-400")

            # Grid Informasi Identitas & Pengaturan
            with ui.row().classes("w-full grid grid-cols-1 md:grid-cols-3 gap-6"):

                # Panel 1: Ringkasan Identitas
                with ui.card().classes("p-6 custom-card flex flex-col justify-between gap-4"):
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
                                ui.badge("AKTIF & TERLINDUNGI" if totp_active else "NONAKTIF", color="emerald-9" if totp_active else "rose-9").classes("text-[9px] font-bold")

                            with ui.row().classes("justify-between w-full"):
                                ui.label("Terdaftar:").classes("text-slate-400")
                                ui.label(u_created).classes("text-slate-200 font-mono")

                            with ui.row().classes("justify-between w-full"):
                                ui.label("Login Terakhir:").classes("text-slate-400")
                                ui.label(u_last_login).classes("text-slate-200 font-mono")

                            with ui.row().classes("justify-between w-full"):
                                ui.label("IP Login:").classes("text-slate-400")
                                ui.label(u_last_ip).classes("text-slate-200 font-mono")

                # Panel 2: Ganti Kata Sandi (NIST Standard)
                with ui.card().classes("md:col-span-2 p-6 custom-card flex flex-col gap-4"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("lock", size="20px").classes("text-sky-400")
                        ui.label("Perbarui Kata Sandi").classes("text-base font-bold text-white")

                    with ui.column().classes("w-full gap-3"):
                        inp_cur_pwd = ui.input("Kata Sandi Saat Ini *", password=True, password_toggle_button=True).classes("w-full").props("dense outlined dark")
                        inp_new_pwd = ui.input("Kata Sandi Baru *", password=True, password_toggle_button=True).classes("w-full").props("dense outlined dark")
                        inp_cf_pwd = ui.input("Konfirmasi Kata Sandi Baru *", password=True, password_toggle_button=True).classes("w-full").props("dense outlined dark")

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

                    with ui.row().classes("w-full justify-end mt-2"):
                        ui.button("Perbarui Kata Sandi", icon="save", on_click=_change_password).props("dense unelevated color=primary no-caps")

            # Panel 3: Autentikasi Dua Langkah (2FA TOTP)
            with ui.card().classes("w-full p-6 custom-card flex flex-col gap-4"):
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("security", size="22px").classes("text-emerald-400" if totp_active else "text-amber-400")
                        ui.label("Perlindungan Autentikasi Dua Langkah (2FA TOTP)").classes("text-base font-bold text-white")
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
