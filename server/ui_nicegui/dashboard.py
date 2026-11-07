"""
Modul Dashboard Pemantauan Pusat (Network Operations Center Overview)
====================================================================
Menyajikan ringkasan metrik kesehatan armada server secara real-time,
bilah keparahan insiden Zabbix (Severity Strip), grid status armada,
peringkat konsumsi sumber daya (CPU & RAM), serta tabel masalah aktif.
"""

from datetime import datetime
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy import func

from models import AuditLog, MaintenanceWindow, ProbeTarget, Server, ServerProblem, SystemSnapshot
from .auth import get_auth_user
from .common import format_bytes, format_duration, get_db, notify_success
from .layout import render_layout


def setup_dashboard_routes(session_factory):
    """Mendaftarkan rute dashboard utama ke NiceGUI engine."""

    @ui.page("/")
    @ui.page("/dashboard")
    def page_dashboard(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username

        render_layout(request, user, active_tab="dashboard")

        dash_container = ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6")

        def _resolve_problem(prob_id: int):
            with get_db(session_factory) as db:
                prob = db.query(ServerProblem).filter(ServerProblem.id == prob_id).first()
                if prob:
                    prob.resolved_at = datetime.utcnow()
                    srv = db.query(Server).filter(Server.id == prob.server_id).first()
                    srv_name = srv.hostname if srv else f"Server #{prob.server_id}"
                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=prob.server_id,
                        action="resolve_problem",
                        target=f"Insiden #{prob.id} ({prob.service_name or 'Sistem'})",
                        result="berhasil",
                    )
                    db.add(audit)
                    db.commit()
                    notify_success(f"Insiden pada {srv_name} berhasil ditandai selesai.")
            _refresh_dashboard_data()

        def _refresh_dashboard_data():
            dash_container.clear()
            with get_db(session_factory) as db:
                servers = db.query(Server).all()
                now = datetime.utcnow()
                online_count = sum(1 for s in servers if s.last_seen and (now - s.last_seen).total_seconds() < 45)
                total_servers = len(servers)
                avail_ratio = round((online_count / total_servers * 100), 1) if total_servers > 0 else 0.0

                open_problems = (
                    db.query(ServerProblem)
                    .filter(ServerProblem.resolved_at == None)
                    .order_by(ServerProblem.started_at.desc())
                    .all()
                )
                danger_cnt = sum(1 for p in open_problems if p.severity in ("danger", "critical", "gawat"))
                warn_cnt = sum(1 for p in open_problems if p.severity in ("warning", "peringatan"))
                info_cnt = sum(1 for p in open_problems if p.severity in ("info", "average"))
                ign_cnt = sum(1 for p in open_problems if p.is_ignored)

                probe_count = db.query(ProbeTarget).count()

                # Pengambilan snapshot terbaru tiap server via subquery terindeks (efisien, 1 query)
                subq = (
                    db.query(SystemSnapshot.server_id, func.max(SystemSnapshot.id).label("max_id"))
                    .group_by(SystemSnapshot.server_id)
                    .subquery()
                )
                snaps = (
                    db.query(SystemSnapshot)
                    .join(subq, SystemSnapshot.id == subq.c.max_id)
                    .all()
                )
                latest_snaps = {s.server_id: s for s in snaps}
                srv_map = {s.id: s.hostname for s in servers}

            with dash_container:
                # -------------------------------------------------------------
                # 1. 4 Kartu Metrik Ringkasan Utama NOC
                # -------------------------------------------------------------
                with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"):
                    # Total Server
                    with ui.card().classes("p-4 custom-card flex flex-col justify-between"):
                        with ui.column().classes("gap-1"):
                            ui.label("TOTAL SERVER").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                            with ui.row().classes("items-baseline gap-2"):
                                ui.label(str(total_servers)).classes("text-3xl font-extrabold text-white font-mono")
                                ui.label(f"{online_count} online").classes("text-xs font-semibold text-emerald-400")
                        with ui.row().classes("justify-end mt-2"):
                            ui.icon("dns", size="36px").classes("text-blue-500/40")

                    # Rasio Ketersediaan
                    with ui.card().classes("p-4 custom-card flex flex-col justify-between"):
                        with ui.column().classes("gap-1"):
                            ui.label("RASIO KETERSEDIAAN").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                            ui.label(f"{avail_ratio}%").classes("text-3xl font-extrabold text-emerald-400 font-mono")
                        with ui.row().classes("justify-end mt-2"):
                            ui.icon("check_circle", size="36px").classes("text-emerald-500/40")

                    # Insiden Aktif
                    with ui.card().classes("p-4 custom-card flex flex-col justify-between"):
                        with ui.column().classes("gap-1"):
                            ui.label("INSIDEN AKTIF").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                            prob_color = "text-rose-400" if danger_cnt > 0 else ("text-amber-400" if warn_cnt > 0 else "text-white")
                            ui.label(str(len(open_problems))).classes(f"text-3xl font-extrabold {prob_color} font-mono")
                        with ui.row().classes("justify-end mt-2"):
                            ui.icon("warning", size="36px").classes("text-amber-500/40")

                    # Target Probing
                    with ui.card().classes("p-4 custom-card flex flex-col justify-between"):
                        with ui.column().classes("gap-1"):
                            ui.label("TARGET PROBING").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                            ui.label(str(probe_count)).classes("text-3xl font-extrabold text-purple-400 font-mono")
                        with ui.row().classes("justify-end mt-2"):
                            ui.icon("wifi_tethering", size="36px").classes("text-purple-400/40")

                # -------------------------------------------------------------
                # 2. Ringkasan Keparahan Insiden Zabbix (Zabbix Severity Bar)
                # -------------------------------------------------------------
                with ui.card().classes("w-full p-4 custom-card"):
                    with ui.row().classes("w-full items-center justify-between mb-2"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("tune", size="18px").classes("text-slate-400")
                            ui.label("RINGKASAN KEPARAHAN INSIDEN (ZABBIX SEVERITY BAR)").classes(
                                "text-xs font-bold text-slate-300 uppercase tracking-wide"
                            )
                        ui.label(f"Total Masalah: {len(open_problems)}").classes("text-xs font-mono text-slate-400")

                    with ui.row().classes("w-full grid grid-cols-2 sm:grid-cols-5 gap-2"):
                        # Kritis
                        with ui.card().classes("zbx-strip-tile p-2.5 bg-rose-950/70 border border-rose-800 flex items-center justify-between"):
                            with ui.column().classes("gap-0"):
                                ui.label("KRITIS").classes("text-[9px] font-bold text-rose-300 uppercase")
                                ui.label(str(danger_cnt)).classes("text-xl font-bold text-rose-400 font-mono")
                            ui.icon("dangerous", size="24px").classes("text-rose-500/50")

                        # Gawat
                        with ui.card().classes("zbx-strip-tile p-2.5 bg-orange-950/70 border border-orange-800 flex items-center justify-between"):
                            with ui.column().classes("gap-0"):
                                ui.label("GAWAT").classes("text-[9px] font-bold text-orange-300 uppercase")
                                ui.label(str(sum(1 for p in open_problems if p.severity in ('average', 'gawat')))).classes(
                                    "text-xl font-bold text-orange-400 font-mono"
                                )
                            ui.icon("report_problem", size="24px").classes("text-orange-500/50")

                        # Peringatan
                        with ui.card().classes("zbx-strip-tile p-2.5 bg-amber-950/70 border border-amber-800 flex items-center justify-between"):
                            with ui.column().classes("gap-0"):
                                ui.label("PERINGATAN").classes("text-[9px] font-bold text-amber-300 uppercase")
                                ui.label(str(warn_cnt)).classes("text-xl font-bold text-amber-400 font-mono")
                            ui.icon("warning", size="24px").classes("text-amber-500/50")

                        # Informasi
                        with ui.card().classes("zbx-strip-tile p-2.5 bg-blue-950/70 border border-blue-800 flex items-center justify-between"):
                            with ui.column().classes("gap-0"):
                                ui.label("INFORMASI").classes("text-[9px] font-bold text-blue-300 uppercase")
                                ui.label(str(info_cnt)).classes("text-xl font-bold text-blue-400 font-mono")
                            ui.icon("info", size="24px").classes("text-blue-500/50")

                        # Diabaikan
                        with ui.card().classes("zbx-strip-tile p-2.5 bg-slate-900 border border-slate-700 flex items-center justify-between"):
                            with ui.column().classes("gap-0"):
                                ui.label("DIABAIKAN").classes("text-[9px] font-bold text-slate-400 uppercase")
                                ui.label(str(ign_cnt)).classes("text-xl font-bold text-slate-300 font-mono")
                            ui.icon("visibility_off", size="24px").classes("text-slate-500/50")

                # -------------------------------------------------------------
                # 3. Grid Armada Server & Pemanfaatan Sumber Daya Tertinggi
                # -------------------------------------------------------------
                with ui.row().classes("w-full grid grid-cols-1 lg:grid-cols-3 gap-4"):
                    # Armada Server Pantau (2/3 Kolom)
                    with ui.column().classes("lg:col-span-2 gap-2"):
                        with ui.row().classes("w-full items-center justify-between"):
                            ui.label("Armada Server Pantau").classes("text-sm font-bold text-white")
                            ui.button("Buka Daftar Server", on_click=lambda: ui.navigate.to("/servers")).props(
                                "dense flat no-caps size=sm color=primary"
                            ).classes("text-xs")

                        with ui.row().classes("w-full grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2.5"):
                            for s in servers:
                                is_up = bool(s.last_seen and (now - s.last_seen).total_seconds() < 45)
                                border_color = "border-emerald-600/40 hover:border-emerald-500" if is_up else "border-rose-600/40 hover:border-rose-500"
                                with ui.card().classes(f"p-2.5 custom-card {border_color} cursor-pointer transition-all").on(
                                    "click", lambda sid=s.id: ui.navigate.to(f"/servers/{sid}")
                                ):
                                    with ui.row().classes("items-center justify-between w-full"):
                                        with ui.row().classes("items-center gap-1.5"):
                                            ui.icon("circle", size="8px").classes("text-emerald-400 animate-pulse" if is_up else "text-rose-500")
                                            ui.label(s.hostname).classes("text-xs font-bold text-white truncate max-w-[90px]")
                                        tier_txt = "PROD" if s.tier == 1 else "DEV"
                                        ui.badge(tier_txt, color="slate-800").classes("text-[8px] font-mono border border-slate-700")

                                    with ui.row().classes("w-full justify-between items-center mt-2 text-[10px] text-slate-400 font-mono"):
                                        ui.label(s.ip_address).classes("truncate")

                    # Peringkat Sumber Daya Tertinggi (1/3 Kolom)
                    with ui.column().classes("gap-3"):
                        ui.label("Pemanfaatan Sumber Daya Tertinggi").classes("text-sm font-bold text-white")

                        # Top CPU
                        with ui.card().classes("p-3 custom-card w-full"):
                            ui.label("BEBAN CPU TERTINGGI").classes("text-[10px] font-bold text-slate-400 uppercase mb-2")
                            cpu_ranked = sorted(
                                [(srv_map.get(sid, f"Server #{sid}"), sn.cpu) for sid, sn in latest_snaps.items() if sn and sn.cpu is not None],
                                key=lambda x: x[1], reverse=True
                            )[:3]
                            if not cpu_ranked:
                                ui.label("Belum ada data telemetri CPU.").classes("text-xs text-slate-500")
                            else:
                                for hname, cpu_p in cpu_ranked:
                                    with ui.column().classes("w-full gap-0.5 mb-2"):
                                        with ui.row().classes("w-full justify-between text-xs"):
                                            ui.label(hname).classes("font-semibold text-slate-200")
                                            ui.label(f"{cpu_p:.1f}%").classes("font-mono text-blue-400")
                                        ui.linear_progress(cpu_p / 100.0, color="blue-5").props("size=4px rounded")

                        # Top RAM
                        with ui.card().classes("p-3 custom-card w-full"):
                            ui.label("PENGGUNAAN MEMORI TERTINGGI").classes("text-[10px] font-bold text-slate-400 uppercase mb-2")
                            mem_ranked = sorted(
                                [
                                    (
                                        srv_map.get(sid, f"Server #{sid}"),
                                        round(sn.mem_used / sn.mem_total * 100, 1) if sn.mem_total else 0,
                                        sn.mem_used, sn.mem_total
                                    )
                                    for sid, sn in latest_snaps.items() if sn and sn.mem_total
                                ],
                                key=lambda x: x[1], reverse=True
                            )[:3]
                            if not mem_ranked:
                                ui.label("Belum ada data telemetri RAM.").classes("text-xs text-slate-500")
                            else:
                                for hname, mem_p, m_used, m_tot in mem_ranked:
                                    with ui.column().classes("w-full gap-0.5 mb-2"):
                                        with ui.row().classes("w-full justify-between text-xs"):
                                            ui.label(hname).classes("font-semibold text-slate-200")
                                            ui.label(f"{mem_p:.1f}%").classes("font-mono text-purple-400")
                                        ui.linear_progress(mem_p / 100.0, color="purple-5").props("size=4px rounded")

                # -------------------------------------------------------------
                # 4. Tabel Masalah & Insiden Aktif Terkini
                # -------------------------------------------------------------
                with ui.card().classes("w-full p-4 custom-card"):
                    with ui.row().classes("w-full items-center justify-between mb-3"):
                        with ui.row().classes("items-center gap-2"):
                            ui.icon("report_problem", size="18px").classes("text-amber-400")
                            ui.label("Daftar Masalah Aktif Terkini").classes("text-sm font-bold text-white")
                        ui.button("Buka Halaman Masalah", on_click=lambda: ui.navigate.to("/problems")).props(
                            "dense flat no-caps size=sm color=primary"
                        ).classes("text-xs")

                    if not open_problems:
                        with ui.row().classes("w-full items-center justify-center p-6 text-slate-400 gap-2"):
                            ui.icon("check_circle", size="20px").classes("text-emerald-400")
                            ui.label("Seluruh armada server dan layanan beroperasi normal tanpa insiden terbuka.").classes("text-xs")
                    else:
                        prob_cols = [
                            {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                            {"name": "sev", "label": "KEPARAHAN", "field": "sev", "align": "center"},
                            {"name": "msg", "label": "MASALAH", "field": "msg", "align": "left"},
                            {"name": "started", "label": "DIMULAI", "field": "started", "align": "left"},
                            {"name": "dur", "label": "DURASI", "field": "dur", "align": "left"},
                            {"name": "action", "label": "AKSI", "field": "action", "align": "center"},
                        ]
                        prob_rows = []
                        for p in open_problems[:8]:
                            prob_rows.append({
                                "id": p.id,
                                "server": srv_map.get(p.server_id, f"Server #{p.server_id}"),
                                "sev": p.severity.upper() if p.severity else "PERINGATAN",
                                "msg": p.message or p.service_name or "Gangguan terdeteksi",
                                "started": p.started_at.strftime("%Y-%m-%d %H:%M:%S") if p.started_at else "—",
                                "dur": format_duration(p.started_at, now),
                            })

                        p_table = ui.table(columns=prob_cols, rows=prob_rows, row_key="id").classes("w-full bg-slate-900")
                        p_table.add_slot("body-cell-sev", """
                            <q-td :props="props">
                                <q-badge :color="props.row.sev === 'DANGER' || props.row.sev === 'CRITICAL' ? 'rose-9' : (props.row.sev === 'WARNING' ? 'amber-9' : 'blue-9')"
                                         class="text-[9px] font-bold px-1.5 py-0.5">
                                    {{ props.row.sev }}
                                </q-badge>
                            </q-td>
                        """)
                        p_table.add_slot("body-cell-action", """
                            <q-td :props="props">
                                <q-btn dense outline size="xs" color="emerald-4" icon="check" label="Selesai" no-caps
                                       @click="() => $parent.$emit('resolve', props.row.id)" />
                            </q-td>
                        """)
                        p_table.on("resolve", lambda e: _resolve_problem(e.args))

        _refresh_dashboard_data()
        ui.timer(10.0, _refresh_dashboard_data)
