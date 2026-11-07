"""
Modul Jadwal & Jendela Pemeliharaan Sistem (Maintenance Windows Management)
==========================================================================
Menyediakan pengelolaan periode pemeliharaan terencana (Scheduled Maintenance),
penekanan alarm/notifikasi palsu saat pemeliharaan, serta pembatalan jadwal.
"""

from datetime import datetime, timedelta
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, MaintenanceWindow, Server
from .auth import get_auth_user
from .common import get_db, notify_error, notify_success
from .layout import render_layout


def setup_maintenance_routes(session_factory):
    """Mendaftarkan rute jendela pemeliharaan ke NiceGUI engine."""

    @ui.page("/maintenance")
    def page_maintenance(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username

        render_layout(request, user, active_tab="maintenance")

        container = ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4")

        # Dialog Modal Buat Jadwal Pemeliharaan
        add_dlg = ui.dialog()
        with add_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4"):
            ui.label("Buat Jadwal Pemeliharaan Baru").classes("text-base font-bold text-white")

            with get_db(session_factory) as db:
                servers_list = db.query(Server).all()
                server_options = {0: "Seluruh Armada Server"}
                for s in servers_list:
                    server_options[s.id] = f"{s.hostname} ({s.ip_address})"

            with ui.column().classes("w-full gap-3"):
                inp_title = ui.input("Judul / Alasan Pemeliharaan").classes("w-full").props("dense outlined dark")
                sel_server = ui.select(server_options, value=0, label="Cakupan Server Target").classes("w-full").props("dense outlined dark")
                inp_dur = ui.number("Durasi Pemeliharaan (Menit)", value=60, min=5, max=10080).classes("w-full").props("dense outlined dark")
                inp_desc = ui.textarea("Deskripsi / Rencana Tindakan").classes("w-full").props("dense outlined dark rows=2")

            def _save_maintenance_window():
                title = inp_title.value.strip()
                if not title:
                    notify_error("Judul pemeliharaan wajib diisi.")
                    return

                start_dt = datetime.utcnow()
                end_dt = start_dt + timedelta(minutes=int(inp_dur.value or 60))
                sid_val = int(sel_server.value)
                scope = "all" if sid_val == 0 else "server"
                target_server_id = None if sid_val == 0 else sid_val

                with get_db(session_factory) as db:
                    mw = MaintenanceWindow(
                        title=title,
                        description=inp_desc.value.strip() or None,
                        scope_type=scope,
                        server_id=target_server_id,
                        schedule_type="once",
                        start_time=start_dt,
                        end_time=end_dt,
                        is_active=1,
                        status="active",
                        created_by=current_username,
                    )
                    db.add(mw)

                    # Update status is_maintenance pada server bersangkutan
                    if target_server_id:
                        srv = db.query(Server).filter(Server.id == target_server_id).first()
                        if srv:
                            srv.is_maintenance = 1
                            srv.maintenance_reason = title
                    else:
                        for s in db.query(Server).all():
                            s.is_maintenance = 1
                            s.maintenance_reason = title

                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=target_server_id,
                        action="create_maintenance_window",
                        target=title,
                        result="berhasil",
                    )
                    db.add(audit)
                    db.commit()
                    notify_success(f"Jadwal pemeliharaan '{title}' berhasil diaktifkan.")
                add_dlg.close()
                _reload_maintenance()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Batal", on_click=add_dlg.close).props("dense flat no-caps color=grey-5")
                ui.button("Aktifkan Jadwal", on_click=_save_maintenance_window).props("dense unelevated color=primary no-caps")

        with container:
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Jendela Pemeliharaan Sistem (Maintenance Windows)").classes("text-xl font-bold text-white")
                    ui.label("Penjadwalan perawatan berkala, perbaikan perangkat lunak, dan penekanan eskalasi alarm palsu").classes("text-xs text-slate-400")

                with ui.row().classes("items-center gap-2"):
                    ui.button("Segarkan", icon="refresh", on_click=lambda: _reload_maintenance()).props("dense outline no-caps size=sm color=primary").classes("text-xs")
                    ui.button("+ Buat Pemeliharaan", icon="add", on_click=add_dlg.open).props("dense unelevated no-caps size=sm color=primary").classes("text-xs")

            table_container = ui.column().classes("w-full")

        def _cancel_maintenance(mw_id: int):
            with get_db(session_factory) as db:
                mw = db.query(MaintenanceWindow).filter(MaintenanceWindow.id == mw_id).first()
                if mw:
                    mw.status = "cancelled"
                    mw.is_active = 0
                    if mw.server_id:
                        srv = db.query(Server).filter(Server.id == mw.server_id).first()
                        if srv:
                            srv.is_maintenance = 0
                            srv.maintenance_reason = None
                    else:
                        for s in db.query(Server).all():
                            s.is_maintenance = 0
                            s.maintenance_reason = None

                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=mw.server_id,
                        action="cancel_maintenance",
                        target=mw.title,
                        result="berhasil",
                    )
                    db.add(audit)
                    db.commit()
                    notify_success(f"Pemeliharaan '{mw.title}' berhasil diakhiri/dibatalkan.")
            _reload_maintenance()

        def _reload_maintenance():
            table_container.clear()
            with get_db(session_factory) as db:
                windows = db.query(MaintenanceWindow).order_by(MaintenanceWindow.id.desc()).all()
                srv_map = {s.id: s.hostname for s in db.query(Server).all()}

            rows = []
            for w in windows:
                scope_str = "Seluruh Armada" if w.scope_type == "all" else srv_map.get(w.server_id, f"Server #{w.server_id}")
                rows.append({
                    "id": w.id,
                    "title": w.title,
                    "scope": scope_str,
                    "start": w.start_time.strftime("%Y-%m-%d %H:%M:%S") if w.start_time else "—",
                    "end": w.end_time.strftime("%Y-%m-%d %H:%M:%S") if w.end_time else "—",
                    "status": w.status.upper(),
                    "by": w.created_by or "Sistem",
                    "is_active": bool(w.is_active and w.status == "active"),
                })

            cols = [
                {"name": "title", "label": "JUDUL / ALASAN PEMELIHARAAN", "field": "title", "align": "left"},
                {"name": "scope", "label": "CAKUPAN SERVER", "field": "scope", "align": "left"},
                {"name": "start", "label": "WAKTU MULAI", "field": "start", "align": "left"},
                {"name": "end", "label": "WAKTU SELESAI", "field": "end", "align": "left"},
                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                {"name": "by", "label": "DIBUAT OLEH", "field": "by", "align": "center"},
                {"name": "action", "label": "AKSI", "field": "action", "align": "center"},
            ]

            with table_container:
                if not rows:
                    with ui.card().classes("w-full p-8 custom-card flex flex-col items-center justify-center gap-2"):
                        ui.icon("event_busy", size="36px").classes("text-slate-500")
                        ui.label("Belum ada jadwal pemeliharaan yang terdaftar.").classes("text-sm text-slate-400 font-medium")
                else:
                    mtbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full bg-slate-900")
                    mtbl.add_slot("body-cell-status", """
                        <q-td :props="props">
                            <q-badge :color="props.row.status === 'ACTIVE' ? 'emerald-9' : (props.row.status === 'SCHEDULED' ? 'blue-9' : 'slate-8')"
                                     class="text-[9px] font-bold px-1.5 py-0.5">
                                {{ props.row.status }}
                            </q-badge>
                        </q-td>
                    """)
                    mtbl.add_slot("body-cell-action", """
                        <q-td :props="props">
                            <q-btn v-if="props.row.is_active" dense outline size="xs" color="rose-4" icon="close" label="Akhiri" no-caps
                                   @click="() => $parent.$emit('cancel_mw', props.row.id)" />
                            <span v-else class="text-xs text-slate-500 font-mono">—</span>
                        </q-td>
                    """)
                    mtbl.on("cancel_mw", lambda e: _cancel_maintenance(e.args))

        _reload_maintenance()
