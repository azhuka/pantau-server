"""
Modul Riwayat Tindakan & Jejak Audit (System Audit Trail & Compliance)
=====================================================================
Menyajikan catatan lengkap setiap intervensi administratif, reboot host,
perubahan konfigurasi, eksekusi perintah, dan autentikasi login pengguna.
"""

from datetime import datetime
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, Server
from .auth import get_auth_user
from .common import get_db
from .layout import render_layout


def setup_audit_routes(session_factory):
    """Mendaftarkan rute jejak audit ke NiceGUI engine."""

    @ui.page("/audit")
    def page_audit(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")

        render_layout(request, user, active_tab="audit")

        container = ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4")

        with container:
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Riwayat Tindakan & Jejak Audit").classes("text-xl font-bold text-white")
                    ui.label("Pencatatan kepatuhan keamanan seluruh intervensi administratif dan eksekusi perintah sistem").classes("text-xs text-slate-400")
                ui.button("Segarkan", icon="refresh", on_click=lambda: _reload_audit()).props("dense outline no-caps size=sm color=primary").classes("text-xs")

            # Filter Log
            with ui.card().classes("w-full p-3 custom-card"):
                with ui.row().classes("w-full items-center justify-between gap-4"):
                    search_box = ui.input(placeholder="Cari tindakan, operator, atau target...").props("dense outlined dark clearable").classes("flex-grow")

            table_container = ui.column().classes("w-full")

        search_box.on("update:model-value", lambda: _reload_audit())

        def _reload_audit():
            table_container.clear()
            with get_db(session_factory) as db:
                logs = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
                srv_map = {s.id: s.hostname for s in db.query(Server).all()}

            q = (search_box.value or "").strip().lower()

            rows = []
            for l in logs:
                srv_name = srv_map.get(l.server_id, "Pusat / Mandiri") if l.server_id else "Pusat / Mandiri"
                searchable = f"{l.username} {l.action} {l.target or ''} {srv_name} {l.result or ''}".lower()
                if q and q not in searchable:
                    continue

                rows.append({
                    "id": l.id,
                    "time": l.created_at.strftime("%Y-%m-%d %H:%M:%S") if l.created_at else "—",
                    "user": l.username or "Sistem",
                    "server": srv_name,
                    "action": l.action,
                    "target": l.target or "—",
                    "result": (l.result or "BERHASIL").upper(),
                })

            cols = [
                {"name": "time", "label": "WAKTU", "field": "time", "align": "left"},
                {"name": "user", "label": "OPERATOR", "field": "user", "align": "left"},
                {"name": "server", "label": "SERVER TARGET", "field": "server", "align": "left"},
                {"name": "action", "label": "TINDAKAN / AKSI", "field": "action", "align": "left"},
                {"name": "target", "label": "OBJEK TARGET", "field": "target", "align": "left"},
                {"name": "result", "label": "STATUS HASIL", "field": "result", "align": "center"},
            ]

            with table_container:
                if not rows:
                    with ui.card().classes("w-full p-8 custom-card flex flex-col items-center justify-center gap-2"):
                        ui.icon("history_toggle_off", size="36px").classes("text-slate-500")
                        ui.label("Belum ada riwayat jejak audit yang tercatat.").classes("text-sm text-slate-400 font-medium")
                else:
                    atbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full bg-slate-900")
                    atbl.add_slot("body-cell-result", """
                        <q-td :props="props">
                            <q-badge :color="props.row.result === 'BERHASIL' ? 'emerald-9' : (props.row.result === 'PENDING' ? 'blue-9' : 'rose-9')"
                                     class="text-[9px] font-bold px-1.5 py-0.5">
                                {{ props.row.result }}
                            </q-badge>
                        </q-td>
                    """)

        _reload_audit()
