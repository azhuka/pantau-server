"""
Modul Pusat Manajemen Insiden & Gangguan (Problems & Alerting Center)
====================================================================
Menyajikan seluruh insiden aktif dan riwayat anomali infrastruktur sistem,
dilengkapi bilah filter tingkat keparahan, riwayat resolusi, serta aksi
penandaan penyelesaian insiden secara langsung (Instant Problem Resolve).
"""

from datetime import datetime
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, Server, ServerProblem
from .auth import get_auth_user
from .common import format_duration, get_db, notify_success
from .layout import render_layout


def setup_problems_routes(session_factory):
    """Mendaftarkan rute halaman manajemen masalah & insiden ke NiceGUI engine."""

    @ui.page("/problems")
    def page_problems(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username

        with render_layout(request, user, active_tab="problems"):
            container = ui.column().classes("w-full gap-3")

            with container:
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0.5"):
                        ui.label("Pusat Insiden & Gangguan").classes("text-xl font-bold text-white")
                        ui.label("Deteksi anomali real-time, pencatatan waktu henti, dan resolusi gangguan armada server").classes("text-xs text-slate-400")
                    ui.button("Segarkan", icon="refresh", on_click=lambda: _reload_problems()).props("dense outline no-caps size=sm color=primary").classes("text-xs")

                # Bilah Filter
                with ui.card().classes("w-full p-3 custom-card"):
                    with ui.row().classes("w-full items-center justify-between gap-4"):
                        with ui.row().classes("items-center gap-4"):
                            only_active_toggle = ui.switch("Hanya Insiden Aktif", value=True).props("dense dark")
                            sev_filter = ui.select(
                                ["Semua Keparahan", "Kritis", "Gawat", "Peringatan", "Informasi"],
                                value="Semua Keparahan"
                            ).props("dense outlined dark options-dense").classes("w-44")
                        search_box = ui.input(placeholder="Cari server atau pesan masalah...").props("dense outlined dark clearable").classes("w-72")

                table_container = ui.column().classes("w-full")

            def _resolve_one(prob_id: int):
                with get_db(session_factory) as db:
                    p = db.query(ServerProblem).filter(ServerProblem.id == prob_id).first()
                    if p:
                        p.resolved_at = datetime.utcnow()
                        srv = db.query(Server).filter(Server.id == p.server_id).first()
                        srv_name = srv.hostname if srv else f"Server #{p.server_id}"
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            server_id=p.server_id,
                            action="resolve_problem",
                            target=f"Insiden #{p.id} ({p.service_name or 'Sistem'})",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                        notify_success(f"Insiden pada {srv_name} berhasil ditandai selesai.")
                _reload_problems()

            only_active_toggle.on("update:model-value", lambda: _reload_problems())
            sev_filter.on("update:model-value", lambda: _reload_problems())
            search_box.on("update:model-value", lambda: _reload_problems())

            def _reload_problems():
                table_container.clear()
                with get_db(session_factory) as db:
                    query = db.query(ServerProblem).order_by(ServerProblem.started_at.desc())
                    if only_active_toggle.value:
                        query = query.filter(ServerProblem.resolved_at == None)

                    all_probs = query.all()
                    servers = {s.id: s.hostname for s in db.query(Server).all()}

                now = datetime.utcnow()
                q = (search_box.value or "").strip().lower()
                sf = sev_filter.value

                rows = []
                for p in all_probs:
                    sev_raw = (p.severity or "warning").lower()
                    sev_label = "Peringatan"
                    if sev_raw in ("danger", "critical", "kritis"):
                        sev_label = "Kritis"
                    elif sev_raw in ("average", "gawat"):
                        sev_label = "Gawat"
                    elif sev_raw in ("info", "informasi"):
                        sev_label = "Informasi"

                    if sf != "Semua Keparahan" and sev_label != sf:
                        continue

                    srv_h = servers.get(p.server_id, f"Server #{p.server_id}")
                    msg_txt = p.message or p.service_name or "Gangguan sistem"
                    if q and q not in f"{srv_h} {msg_txt}".lower():
                        continue

                    rows.append({
                        "id": p.id,
                        "server": srv_h,
                        "sev": sev_label.upper(),
                        "msg": msg_txt,
                        "started": p.started_at.strftime("%Y-%m-%d %H:%M:%S") if p.started_at else "—",
                        "resolved": p.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if p.resolved_at else "—",
                        "dur": format_duration(p.started_at, p.resolved_at or now),
                        "is_open": p.resolved_at is None,
                    })

                cols = [
                    {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                    {"name": "sev", "label": "KEPARAHAN", "field": "sev", "align": "center"},
                    {"name": "msg", "label": "MASALAH / PESAN GANGGUAN", "field": "msg", "align": "left"},
                    {"name": "started", "label": "MULAI", "field": "started", "align": "left"},
                    {"name": "resolved", "label": "SELESAI", "field": "resolved", "align": "left"},
                    {"name": "dur", "label": "DURASI", "field": "dur", "align": "left"},
                    {"name": "action", "label": "STATUS / RESOLUSI", "field": "action", "align": "center"},
                ]

                with table_container:
                    if not rows:
                        with ui.card().classes("w-full p-8 custom-card flex flex-col items-center justify-center gap-2"):
                            ui.icon("check_circle", size="36px").classes("text-emerald-400")
                            ui.label("Tidak ada catatan insiden yang sesuai dengan kriteria filter.").classes("text-sm text-slate-300 font-medium")
                    else:
                        ptbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full bg-slate-900")
                        ptbl.add_slot("body-cell-sev", """
                            <q-td :props="props">
                                <q-badge :color="props.row.sev === 'KRITIS' ? 'rose-9' : (props.row.sev === 'GAWAT' ? 'orange-9' : (props.row.sev === 'PERINGATAN' ? 'amber-9' : 'blue-9'))"
                                         class="text-[9.5px] font-bold px-2 py-0.5">
                                    {{ props.row.sev }}
                                </q-badge>
                            </q-td>
                        """)
                        ptbl.add_slot("body-cell-action", """
                            <q-td :props="props" style="white-space: nowrap; min-width: 120px; text-align: center;">
                                <q-badge v-if="!props.row.is_open" color="slate-8" class="text-[9px] font-mono text-slate-400">
                                    Terselesaikan
                                </q-badge>
                                <q-btn v-else dense outline size="xs" color="emerald-4" icon="check" label="Tandai Selesai" no-caps class="px-2 font-semibold" style="white-space: nowrap"
                                       @click="() => $parent.$emit('resolve', props.row.id)" />
                            </q-td>
                        """)
                        ptbl.on("resolve", lambda e: _resolve_one(e.args))

            _reload_problems()
