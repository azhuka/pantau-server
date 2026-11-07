"""
Modul Manajemen Pengguna & Hak Akses (User Management & Role RBAC)
==================================================================
Menyediakan pengelolaan akun operator NOC, pembuatan akun dengan hash bcrypt,
penetapan peran hierarkis (Master Admin, Operator, Viewer), dan reset sandi.
"""

from datetime import datetime
from nicegui import ui
from passlib.context import CryptContext
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, User
from .auth import get_auth_user
from .common import get_db, notify_error, notify_success
from .layout import render_layout

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


def setup_users_routes(session_factory):
    """Mendaftarkan rute manajemen pengguna ke NiceGUI engine."""

    @ui.page("/users")
    def page_users(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            if not (user.is_master_admin() or user.has_perm("can_manage_users")):
                return RedirectResponse("/dashboard")
            current_user_id = user.id
            current_username = user.username

        with render_layout(request, user, active_tab="users"):
            container = ui.column().classes("w-full gap-3")

            # Dialog Modal Tambah Pengguna Baru
            add_user_dlg = ui.dialog()
            with add_user_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                ui.label("Tambah Pengguna NOC Baru").classes("text-base font-bold text-white")

                with ui.column().classes("w-full gap-3"):
                    inp_uname = ui.input("Nama Pengguna (Username)").classes("w-full").props("dense outlined dark stack-label")
                    inp_pwd = ui.input("Kata Sandi Awal", password=True).classes("w-full").props("dense outlined dark stack-label")
                    sel_role = ui.select(
                        {"viewer": "Viewer (Hanya Baca)", "operator": "Operator NOC", "master_admin": "Master Admin"},
                        value="viewer", label="Peran / Hak Akses"
                    ).classes("w-full").props("dense outlined dark stack-label")

                def _save_new_user():
                    uname = inp_uname.value.strip()
                    pwd = inp_pwd.value.strip()
                    if not uname or not pwd:
                        notify_error("Username dan password tidak boleh kosong.")
                        return
                    if len(pwd) < 8:
                        notify_error("Kata sandi minimal 8 karakter.")
                        return

                    with get_db(session_factory) as db:
                        existing = db.query(User).filter(User.username == uname).first()
                        if existing:
                            notify_error(f"Username '{uname}' sudah digunakan.")
                            return

                        new_u = User(
                            username=uname,
                            password_hash=pwd_ctx.hash(pwd),
                            role=sel_role.value,
                            is_active=1,
                            created_by=current_username,
                        )
                        db.add(new_u)
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            action="create_user",
                            target=f"{uname} ({sel_role.value})",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                        notify_success(f"Akun pengguna '{uname}' berhasil dibuat.")
                    add_user_dlg.close()
                    _reload_users()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=add_user_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Buat Pengguna", on_click=_save_new_user).props("dense unelevated color=primary no-caps")

            # Dialog Modal Edit Peran (Role RBAC)
            edit_role_dlg = ui.dialog()
            edit_user_target = {"id": None, "uname": ""}
            with edit_role_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                edit_role_title = ui.label("Ubah Peran Akses Pengguna").classes("text-base font-bold text-white")
                with ui.column().classes("w-full gap-3"):
                    role_sel_edit = ui.select(
                        {"viewer": "Viewer (Hanya Baca)", "operator": "Operator NOC", "master_admin": "Master Admin"},
                        label="Pilih Peran Baru"
                    ).classes("w-full").props("dense outlined dark stack-label")

                def _save_role_change():
                    uid = edit_user_target["id"]
                    if not uid:
                        return
                    new_r = role_sel_edit.value
                    with get_db(session_factory) as db:
                        u = db.query(User).filter(User.id == uid).first()
                        if u:
                            u.role = new_r
                            audit = AuditLog(
                                user_id=current_user_id,
                                username=current_username,
                                action="change_user_role",
                                target=f"{u.username} -> {new_r}",
                                result="berhasil",
                            )
                            db.add(audit)
                            db.commit()
                            notify_success(f"Peran akun {u.username} berhasil diubah menjadi {new_r}.")
                    edit_role_dlg.close()
                    _reload_users()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=edit_role_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Simpan Peran", on_click=_save_role_change).props("dense unelevated color=primary no-caps")

            # Dialog Modal Reset Kata Sandi
            reset_pwd_dlg = ui.dialog()
            reset_user_target = {"id": None, "uname": ""}
            with reset_pwd_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                reset_pwd_title = ui.label("Reset Kata Sandi Pengguna").classes("text-base font-bold text-white")
                with ui.column().classes("w-full gap-3"):
                    new_pwd_inp = ui.input("Kata Sandi Baru", password=True).classes("w-full").props("dense outlined dark stack-label")

                def _save_password_reset():
                    uid = reset_user_target["id"]
                    if not uid:
                        return
                    pwd_val = new_pwd_inp.value.strip()
                    if not pwd_val or len(pwd_val) < 8:
                        notify_error("Kata sandi baru minimal 8 karakter.")
                        return
                    with get_db(session_factory) as db:
                        u = db.query(User).filter(User.id == uid).first()
                        if u:
                            u.password_hash = pwd_ctx.hash(pwd_val)
                            audit = AuditLog(
                                user_id=current_user_id,
                                username=current_username,
                                action="reset_user_password",
                                target=u.username,
                                result="berhasil",
                            )
                            db.add(audit)
                            db.commit()
                            notify_success(f"Kata sandi untuk pengguna {u.username} berhasil direset.")
                    reset_pwd_dlg.close()
                    _reload_users()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=reset_pwd_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Simpan Sandi", on_click=_save_password_reset).props("dense unelevated color=primary no-caps")

            # Dialog Modal Hapus Pengguna
            del_user_dlg = ui.dialog()
            del_user_target = {"id": None, "uname": ""}
            with del_user_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/50"):
                del_user_title = ui.label("Hapus Akun Pengguna").classes("text-base font-bold text-rose-400")
                del_user_msg = ui.label("").classes("text-xs text-slate-300 leading-relaxed")

                def _confirm_delete_user():
                    uid = del_user_target["id"]
                    if not uid:
                        return
                    if uid == current_user_id:
                        notify_error("Anda tidak dapat menghapus akun Anda sendiri.")
                        return
                    with get_db(session_factory) as db:
                        u = db.query(User).filter(User.id == uid).first()
                        if u:
                            if u.is_master_admin() or u.role == "master_admin":
                                notify_error("Akun Master Admin tidak dapat dihapus.")
                                return
                            u_name = u.username
                            db.delete(u)
                            audit = AuditLog(
                                user_id=current_user_id,
                                username=current_username,
                                action="delete_user",
                                target=u_name,
                                result="berhasil",
                            )
                            db.add(audit)
                            db.commit()
                            notify_success(f"Akun pengguna '{u_name}' berhasil dihapus.")
                    del_user_dlg.close()
                    _reload_users()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=del_user_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Hapus Akun", on_click=_confirm_delete_user).props("dense unelevated color=negative no-caps")

            def _open_edit_role(uid: int, uname: str, curr_role: str):
                edit_user_target["id"] = uid
                edit_user_target["uname"] = uname
                edit_role_title.set_text(f"Ubah Peran: {uname}")
                role_sel_edit.set_value(curr_role.lower())
                edit_role_dlg.open()

            def _open_reset_pwd(uid: int, uname: str):
                reset_user_target["id"] = uid
                reset_user_target["uname"] = uname
                reset_pwd_title.set_text(f"Reset Sandi: {uname}")
                new_pwd_inp.set_value("")
                reset_pwd_dlg.open()

            def _open_del_user(uid: int, uname: str):
                del_user_target["id"] = uid
                del_user_target["uname"] = uname
                del_user_title.set_text(f"Hapus Akun: {uname}")
                del_user_msg.set_text(f"Apakah Anda yakin ingin menghapus akun pengguna '{uname}' secara permanen? Akses login pengguna ini akan dicabut total.")
                del_user_dlg.open()

            with container:
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0.5"):
                        ui.label("Manajemen Pengguna & Hak Akses (RBAC)").classes("text-xl font-bold text-white")
                        ui.label("Pengelolaan otorisasi akun personel NOC, peran akses, dan status keamanan autentikasi").classes("text-xs text-slate-400")

                    with ui.row().classes("items-center gap-2"):
                        ui.button("Segarkan", icon="refresh", on_click=lambda: _reload_users()).props("dense outline no-caps size=sm color=primary").classes("text-xs")
                        ui.button("+ Tambah Pengguna Baru", icon="person_add", on_click=add_user_dlg.open).props("dense unelevated no-caps size=sm color=primary").classes("text-xs")

                table_container = ui.column().classes("w-full")

            def _toggle_status(uid: int):
                if uid == current_user_id:
                    notify_error("Anda tidak dapat menonaktifkan akun sendiri.")
                    return
                with get_db(session_factory) as db:
                    u = db.query(User).filter(User.id == uid).first()
                    if u:
                        u.is_active = 0 if u.is_active else 1
                        act_txt = "diaktifkan" if u.is_active else "dinonaktifkan"
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            action="toggle_user_status",
                            target=f"{u.username} ({act_txt})",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                        notify_success(f"Akun pengguna {u.username} berhasil {act_txt}.")
                _reload_users()

            def _reload_users():
                table_container.clear()
                with get_db(session_factory) as db:
                    users_list = db.query(User).order_by(User.id.asc()).all()

                rows = []
                for u in users_list:
                    rows.append({
                        "id": u.id,
                        "username": u.username,
                        "role": u.role_display().upper(),
                        "raw_role": u.role or "viewer",
                        "is_master": bool(u.role in ["master_admin", "admin"] or u.is_master_admin()),
                        "is_self": bool(u.id == current_user_id),
                        "is_active": bool(u.is_active),
                        "status": "AKTIF" if u.is_active else "NONAKTIF",
                        "totp": "AKTIF" if u.totp_enabled else "NONAKTIF",
                        "last_login": u.last_login_at.strftime("%Y-%m-%d %H:%M:%S") if u.last_login_at else "Belum Pernah",
                        "last_ip": u.last_login_ip or "—",
                        "created_by": u.created_by or "Sistem",
                    })

                cols = [
                    {"name": "id", "label": "ID", "field": "id", "align": "center"},
                    {"name": "username", "label": "NAMA PENGGUNA", "field": "username", "align": "left"},
                    {"name": "role", "label": "PERAN / AKSES", "field": "role", "align": "center"},
                    {"name": "status", "label": "STATUS AKUN", "field": "status", "align": "center"},
                    {"name": "totp", "label": "2FA TOTP", "field": "totp", "align": "center"},
                    {"name": "last_login", "label": "LOGIN TERAKHIR", "field": "last_login", "align": "left"},
                    {"name": "last_ip", "label": "IP TERAKHIR", "field": "last_ip", "align": "left"},
                    {"name": "action", "label": "TINDAKAN", "field": "action", "align": "center"},
                ]

                with table_container:
                    utbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full bg-slate-900")
                    utbl.add_slot("body-cell-role", """
                        <q-td :props="props">
                            <q-badge :color="props.row.role === 'MASTER ADMIN' ? 'rose-9' : (props.row.role === 'OPERATOR' ? 'blue-9' : 'slate-8')"
                                     class="text-[9px] font-bold px-1.5 py-0.5">
                                {{ props.row.role }}
                            </q-badge>
                        </q-td>
                    """)
                    utbl.add_slot("body-cell-status", """
                        <q-td :props="props">
                            <q-badge :color="props.row.is_active ? 'emerald-9' : 'rose-9'" class="text-[9px] font-bold px-1.5 py-0.5">
                                {{ props.row.status }}
                            </q-badge>
                        </q-td>
                    """)
                    utbl.add_slot("body-cell-totp", """
                        <q-td :props="props">
                            <q-badge :color="props.row.totp === 'AKTIF' ? 'emerald-9' : 'slate-8'" class="text-[9px] font-mono">
                                {{ props.row.totp }}
                            </q-badge>
                        </q-td>
                    """)
                    utbl.add_slot("body-cell-action", """
                        <q-td :props="props">
                            <div class="row items-center justify-center q-gutter-xs">
                                <q-btn dense flat round size="xs" color="sky-4" icon="edit"
                                       @click="() => $parent.$emit('edit_role', props.row)">
                                    <q-tooltip class="bg-slate-900 text-[10px]">Ubah Peran Akses</q-tooltip>
                                </q-btn>
                                <q-btn dense flat round size="xs" color="amber-4" icon="key"
                                       @click="() => $parent.$emit('reset_pwd', props.row)">
                                    <q-tooltip class="bg-slate-900 text-[10px]">Reset Sandi</q-tooltip>
                                </q-btn>
                                <q-btn v-if="!props.row.is_master && !props.row.is_self"
                                       dense flat round size="xs"
                                       :color="props.row.is_active ? 'rose-4' : 'emerald-4'"
                                       :icon="props.row.is_active ? 'lock' : 'lock_open'"
                                       @click="() => $parent.$emit('toggle_status', props.row.id)">
                                    <q-tooltip class="bg-slate-900 text-[10px]">{{ props.row.is_active ? 'Kunci / Nonaktifkan Akun' : 'Buka Kunci Akun' }}</q-tooltip>
                                </q-btn>
                                <q-btn v-if="!props.row.is_master && !props.row.is_self"
                                       dense flat round size="xs" color="rose-5" icon="delete"
                                       @click="() => $parent.$emit('del_user', props.row)">
                                    <q-tooltip class="bg-slate-900 text-[10px]">Hapus Akun Pengguna</q-tooltip>
                                </q-btn>
                                <span v-if="props.row.is_self" class="text-[10px] text-sky-400 font-semibold px-1">(Akun Anda)</span>
                                <span v-else-if="props.row.is_master" class="text-[10px] text-slate-500 font-semibold px-1">(Master)</span>
                            </div>
                        </q-td>
                    """)
                    utbl.on("edit_role", lambda e: _open_edit_role(e.args["id"], e.args["username"], e.args["raw_role"]))
                    utbl.on("reset_pwd", lambda e: _open_reset_pwd(e.args["id"], e.args["username"]))
                    utbl.on("del_user", lambda e: _open_del_user(e.args["id"], e.args["username"]))
                    utbl.on("toggle_status", lambda e: _toggle_status(e.args))

            _reload_users()
