"""Antarmuka Baru Pantau Server Berbasis NiceGUI (Python Murni).

Menyediakan antarmuka NOC mandiri berdensitas tinggi, tema gelap modern,
dan tata letak tabel dinamis tanpa ketergantungan pada template Jinja atau CSS manual.
"""

import json
from datetime import datetime
from starlette.requests import Request
from starlette.responses import RedirectResponse
from nicegui import ui, app

from models import (
    Server, ServerExtras, Service, Metric, SystemSnapshot,
    ServerProblem, AuditLog, User, ProbeTarget, MaintenanceWindow, AppSession
)
from config import settings


def _get_auth_user(request: Request, db):
    """Verifikasi sesi pengguna dari cookie session_id."""
    sid = request.cookies.get("session_id")
    if not sid:
        return None
    session_row = db.query(AppSession).filter(AppSession.sid == sid).first()
    if not session_row:
        return None
    if datetime.utcnow() > session_row.expires_at:
        return None
    return db.query(User).filter(User.id == session_row.user_id).first()


def _render_layout(request: Request, user: User, active_tab: str = "servers"):
    """Render layout umum NOC (Header & Tab Navigasi Terpusat)."""
    ui.dark_mode().enable()

    # Head CSS global untuk standar kepadatan NOC (High Density)
    ui.add_head_html("""
    <style>
        body { background-color: #0b1120; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, monospace; }
        .q-table__container { background-color: #0f172a !important; border: 1px solid #1e293b !important; border-radius: 8px; }
        .q-table thead th { font-size: 11px !important; font-weight: 700 !important; color: #94a3b8 !important; text-transform: uppercase; background-color: #0f172a !important; padding: 7px 12px !important; letter-spacing: 0.05em; }
        .q-table tbody td { font-size: 11.5px !important; padding: 6px 12px !important; border-color: #1e293b !important; color: #e2e8f0; }
        .q-table tbody tr:hover { background-color: rgba(30, 41, 59, 0.75) !important; }
        .q-table__bottom { font-size: 11px !important; color: #94a3b8 !important; border-top: 1px solid #1e293b !important; padding: 4px 12px !important; }
        .custom-card { background-color: #0f172a; border: 1px solid #1e293b; border-radius: 8px; }
    </style>
    """)

    # Top Header
    with ui.header().classes("bg-slate-900 border-b border-slate-800 text-white px-6 py-2 flex items-center justify-between sticky top-0 z-50"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("dns", size="24px").classes("text-blue-400")
            with ui.column().classes("gap-0"):
                ui.label("PANTAU SERVER").classes("text-base font-bold tracking-wider leading-tight text-white")
                ui.label("NOC MANDIRI · DINAS KOMINFO BARRU").classes("text-[10px] text-slate-400 font-mono")
            ui.badge("NOC", color="blue-9").classes("text-[10px] font-bold px-1.5 py-0.5 ml-1")

        with ui.row().classes("items-center gap-3"):
            ui.badge(f"v{settings.APP_VERSION}", color="slate-800").classes("text-slate-400 text-[11px] font-mono border border-slate-700")
            if user:
                with ui.row().classes("items-center gap-1.5 bg-slate-800/80 px-2.5 py-1 rounded border border-slate-700"):
                    ui.icon("account_circle", size="16px").classes("text-slate-300")
                    ui.label(user.username).classes("text-xs font-semibold text-slate-200")
                    ui.badge(user.role_display() if hasattr(user, "role_display") else user.role, color="slate-700").classes("text-[9px] uppercase")
            ui.button("Keluar", icon="logout", on_click=lambda: ui.navigate.to("/logout")).props("dense flat no-caps size=sm color=red-4").classes("text-xs")

    # Navigation Tabs
    tabs_data = [
        ("Dashboard", "/", "dashboard"),
        ("Daftar Server", "/servers", "storage"),
        ("Insiden & Masalah", "/problems", "warning"),
        ("Riwayat Tindakan", "/audit", "history"),
        ("Probing Endpoint", "/probing", "network_check"),
        ("Pemeliharaan", "/maintenance", "build"),
        ("Pengguna", "/users", "group"),
    ]
    with ui.row().classes("w-full bg-slate-950/80 border-b border-slate-800/80 px-6 py-1 gap-1 items-center"):
        for label, url, icon_name in tabs_data:
            is_cur = (url == active_tab) or (active_tab == "dashboard" and url == "/")
            btn_props = "dense flat no-caps size=sm"
            cls = "px-3 py-1 font-semibold text-xs rounded transition-colors "
            if is_cur:
                cls += "bg-blue-600/20 text-blue-400 border border-blue-500/30"
            else:
                cls += "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50"
            ui.button(label, icon=icon_name, on_click=lambda u=url: ui.navigate.to(u)).props(btn_props).classes(cls)


def setup_nicegui(fastapi_app, session_factory):
    """Inisialisasi antarmuka NiceGUI dan kaitkan ke aplikasi FastAPI."""

    # -------------------------------------------------------------------------
    # 0. Halaman Login (/login)
    # -------------------------------------------------------------------------
    @ui.page("/login")
    def page_login(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        db.close()
        if user:
            return RedirectResponse("/")

        ui.dark_mode().enable()
        ui.add_head_html("""
        <style>
            body { background-color: #0b1120; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; }
        </style>
        """)

        err_msg = request.query_params.get("error")

        with ui.column().classes("w-full min-h-screen flex items-center justify-center p-4"):
            with ui.card().classes("w-full max-w-md p-8 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl flex flex-col gap-5"):
                with ui.column().classes("w-full items-center gap-1.5 mb-2"):
                    ui.icon("dns", size="44px").classes("text-blue-500")
                    ui.label("PANTAU SERVER").classes("text-xl font-bold tracking-wider text-white")
                    ui.label("NOC Mandiri · Otentikasi Operator").classes("text-xs text-slate-400")

                if err_msg:
                    with ui.row().classes("w-full items-center gap-2 bg-rose-950/70 border border-rose-800 p-2.5 rounded text-rose-300 text-xs"):
                        ui.icon("error", size="18px").classes("text-rose-400")
                        ui.label(err_msg).classes("font-medium")

                with ui.element("form").props('action="/login" method="post"').classes("w-full flex flex-col gap-4"):
                    with ui.column().classes("w-full gap-1"):
                        ui.label("Nama Pengguna").classes("text-xs font-semibold text-slate-300")
                        ui.html("""
                            <input type="text" name="username" placeholder="Masukkan username" required
                                   class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-white text-sm focus:outline-none focus:border-blue-500" />
                        """)

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Kata Sandi").classes("text-xs font-semibold text-slate-300")
                        ui.html("""
                            <input type="password" name="password" placeholder="Masukkan password" required
                                   class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-white text-sm focus:outline-none focus:border-blue-500" />
                        """)

                    ui.html("""
                        <button type="submit"
                                class="w-full mt-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white font-semibold rounded text-sm transition-colors cursor-pointer shadow-lg">
                            Masuk ke Sistem NOC
                        </button>
                    """)

                with ui.row().classes("w-full justify-center mt-2"):
                    ui.label("Sistem Pemantauan Infrastruktur Terpusat & Keamanan Jaringan").classes("text-[10px] text-slate-500 text-center")

    # -------------------------------------------------------------------------
    # 1. Halaman Dashboard (Root / dan /dashboard)
    # -------------------------------------------------------------------------
    @ui.page("/")
    @ui.page("/dashboard")
    def page_dashboard(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="dashboard")

        servers = db.query(Server).all()
        now = datetime.utcnow()
        online_count = sum(1 for s in servers if s.last_seen and (now - s.last_seen).total_seconds() < 45)
        total_servers = len(servers)
        
        open_problems = db.query(ServerProblem).filter(ServerProblem.resolved_at == None).order_by(ServerProblem.started_at.desc()).all()
        probe_count = db.query(ProbeTarget).count()
        audit_count = db.query(AuditLog).count()
        
        # Peta server ID ke nama
        srv_map = {s.id: s.hostname for s in servers}
        db.close()

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
            # Metric Cards
            with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4"):
                # Total Server
                with ui.card().classes("p-4 custom-card flex items-center justify-between"):
                    with ui.column().classes("gap-1"):
                        ui.label("TOTAL SERVER").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                        ui.label(str(total_servers)).classes("text-2xl font-bold text-white")
                    ui.icon("dns", size="36px").classes("text-blue-400/40")

                # Online
                with ui.card().classes("p-4 custom-card flex items-center justify-between"):
                    with ui.column().classes("gap-1"):
                        ui.label("SERVER ONLINE").classes("text-[10px] font-bold text-emerald-400 uppercase tracking-wider")
                        ui.label(f"{online_count} / {total_servers}").classes("text-2xl font-bold text-emerald-400")
                    ui.icon("check_circle", size="36px").classes("text-emerald-400/40")

                # Insiden Terbuka
                with ui.card().classes("p-4 custom-card flex items-center justify-between"):
                    with ui.column().classes("gap-1"):
                        ui.label("INSIDEN AKTIF").classes("text-[10px] font-bold text-amber-400 uppercase tracking-wider")
                        ui.label(str(len(open_problems))).classes("text-2xl font-bold text-amber-400")
                    ui.icon("warning", size="36px").classes("text-amber-400/40")

                # Synthetic Probing
                with ui.card().classes("p-4 custom-card flex items-center justify-between"):
                    with ui.column().classes("gap-1"):
                        ui.label("TARGET PROBING").classes("text-[10px] font-bold text-purple-400 uppercase tracking-wider")
                        ui.label(str(probe_count)).classes("text-2xl font-bold text-purple-400")
                    ui.icon("network_check", size="36px").classes("text-purple-400/40")

            # Quick Fleet Status Grid
            with ui.column().classes("w-full gap-2 mt-2"):
                ui.label("Ringkasan Armada Server").classes("text-base font-bold text-white")
                with ui.row().classes("w-full grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3"):
                    for s in servers:
                        is_up = bool(s.last_seen and (now - s.last_seen).total_seconds() < 45)
                        border_color = "border-emerald-600/40 hover:border-emerald-500" if is_up else "border-rose-600/40 hover:border-rose-500"
                        with ui.card().classes(f"p-3 custom-card {border_color} cursor-pointer transition-all").on("click", lambda sid=s.id: ui.navigate.to(f"/servers/{sid}")):
                            with ui.row().classes("items-center justify-between w-full"):
                                with ui.row().classes("items-center gap-1.5"):
                                    ui.icon("circle", size="10px").classes("text-emerald-400" if is_up else "text-rose-400")
                                    ui.label(s.hostname).classes("text-xs font-bold text-white truncate max-w-[110px]")
                                ui.badge("PROD" if s.tier == 1 else "DEV", color="slate-800").classes("text-[9px] font-mono border border-slate-700")
                            ui.label(s.ip_address or "—").classes("text-[10.5px] text-slate-400 font-mono mt-1")

            # Insiden Terbuka Table
            with ui.column().classes("w-full gap-2 mt-4"):
                with ui.row().classes("w-full justify-between items-center"):
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Insiden & Masalah Aktif").classes("text-base font-bold text-white")
                        ui.badge(str(len(open_problems)), color="amber-9").classes("text-[10px] font-bold")
                    ui.button("Lihat Semua Insiden", on_click=lambda: ui.navigate.to("/problems")).props("dense flat no-caps size=sm color=primary").classes("text-xs")

                prob_cols = [
                    {"name": "time", "label": "WAKTU MULAI", "field": "time", "align": "left", "sortable": True},
                    {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                    {"name": "severity", "label": "KEPARAHAN", "field": "severity", "align": "center"},
                    {"name": "message", "label": "PESAN MASALAH", "field": "message", "align": "left"},
                    {"name": "duration", "label": "DURASI", "field": "duration", "align": "right"},
                ]
                prob_rows = []
                for p in open_problems[:12]:
                    dur_sec = int((now - p.started_at).total_seconds()) if p.started_at else 0
                    dur_str = f"{dur_sec // 60} mnt" if dur_sec >= 60 else f"{dur_sec} dtk"
                    srv_name = srv_map.get(p.server_id, f"Server #{p.server_id}") if p.server_id else "Global / Probe"
                    prob_rows.append({
                        "id": p.id,
                        "time": p.started_at.strftime("%d %b %H:%M:%S") if p.started_at else "—",
                        "server": srv_name,
                        "severity": (p.severity or "warning").upper(),
                        "message": p.message or "—",
                        "duration": dur_str,
                    })

                t_prob = ui.table(columns=prob_cols, rows=prob_rows, row_key="id").props("dense flat bordered wrap-cells").classes("w-full")
                t_prob.add_slot("body-cell-severity", """
                    <q-td :props="props">
                        <span :class="props.value === 'DANGER' || props.value === 'CRITICAL' || props.value === 'GAWAT' ? 'bg-rose-950 text-rose-400 border-rose-800' : (props.value === 'WARNING' || props.value === 'PERINGATAN' ? 'bg-amber-950 text-amber-400 border-amber-800' : 'bg-blue-950 text-blue-400 border-blue-800')"
                              class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                            {{ props.value }}
                        </span>
                    </q-td>
                """)

    # -------------------------------------------------------------------------
    # 2. Halaman Daftar Server (/servers)
    # -------------------------------------------------------------------------
    @ui.page("/servers")
    def page_servers(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="/servers")

        servers = db.query(Server).order_by(Server.id.asc()).all()
        extras_map = {e.server_id: e for e in db.query(ServerExtras).all()}
        db.close()

        now = datetime.utcnow()

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Daftar Server").classes("text-xl font-bold text-white")
                    ui.label("Monitoring status kesehatan armada server, sistem operasi, dan agen secara real-time").classes("text-xs text-slate-400")
                with ui.row().classes("gap-2 items-center"):
                    ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to("/servers")).props("dense outline no-caps size=sm").classes("text-xs text-slate-300")

            columns = [
                {"name": "server", "label": "SERVER", "field": "hostname", "align": "left", "sortable": True},
                {"name": "ip", "label": "IP ADDRESS", "field": "ip", "align": "left"},
                {"name": "platform", "label": "PLATFORM / HARDWARE", "field": "platform", "align": "left"},
                {"name": "os", "label": "SISTEM OPERASI", "field": "os", "align": "left"},
                {"name": "cpu", "label": "PROSESOR", "field": "cpu", "align": "left"},
                {"name": "agent", "label": "AGEN", "field": "agent", "align": "left"},
                {"name": "status", "label": "STATUS", "field": "status", "align": "center", "sortable": True},
                {"name": "actions", "label": "TINDAKAN", "field": "actions", "align": "right"},
            ]

            rows = []
            for s in servers:
                ext = extras_map.get(s.id)
                hw = {}
                if ext and ext.hardware_specs:
                    try:
                        hw = json.loads(ext.hardware_specs)
                    except Exception:
                        pass
                
                plat_str = s.platform_override or "Linux"
                if hw.get("system_model"):
                    plat_str += f" ({hw.get('system_model')})"

                cpu_str = "—"
                if hw.get("cpu_model"):
                    cores = f" ({hw.get('cpu_cores')} Cores)" if hw.get('cpu_cores') else ""
                    cpu_str = f"{hw.get('cpu_model')}{cores}"

                os_str = ext.os_label if ext and ext.os_label else "Linux"
                if ext and ext.kernel:
                    os_str += f" {ext.kernel}"

                is_online = bool(s.last_seen and (now - s.last_seen).total_seconds() < 45)
                env_label = "PROD" if s.tier == 1 else "DEV"

                rows.append({
                    "id": s.id,
                    "hostname": s.hostname,
                    "env": env_label,
                    "ip": s.ip_address or "—",
                    "platform": plat_str,
                    "os": os_str,
                    "cpu": cpu_str,
                    "agent": ext.agent_version if ext and ext.agent_version else "—",
                    "status": "ONLINE" if is_online else "OFFLINE",
                })

            with ui.row().classes("w-full justify-between items-center mb-1"):
                search_input = ui.input(placeholder="Cari server, IP, OS, atau platform...").props("dense outlined debounce=300 clearable").classes("w-80 text-xs bg-slate-900")

            table = ui.table(columns=columns, rows=rows, row_key="id", pagination=15).props("dense flat bordered wrap-cells").classes("w-full")
            search_input.bind_value(table, "filter")
            
            table.add_slot("body-cell-server", """
                <q-td :props="props">
                    <div class="flex items-center gap-2">
                        <span :class="props.row.status === 'ONLINE' ? 'text-green-400' : 'text-red-400'">●</span>
                        <a :href="'/servers/' + props.row.id" class="font-bold text-white text-xs hover:text-blue-400 cursor-pointer no-underline">{{ props.row.hostname }}</a>
                        <span class="text-[9px] px-1 py-0.2 rounded bg-slate-800 text-slate-400 border border-slate-700 uppercase font-mono">{{ props.row.env }}</span>
                    </div>
                </q-td>
            """)

            table.add_slot("body-cell-status", """
                <q-td :props="props">
                    <span :class="props.value === 'ONLINE' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800'"
                          class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                        {{ props.value }}
                    </span>
                </q-td>
            """)

            table.add_slot("body-cell-actions", """
                <q-td :props="props">
                    <div class="flex justify-end gap-1">
                        <q-btn dense flat round icon="visibility" size="xs" color="blue-4" :to="'/servers/' + props.row.id" />
                    </div>
                </q-td>
            """)

    # -------------------------------------------------------------------------
    # 3. Halaman Detail Server (/servers/{server_id})
    # -------------------------------------------------------------------------
    @ui.page("/servers/{server_id}")
    def page_server_detail(request: Request, server_id: int):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="/servers")

        sid_int = int(server_id) if str(server_id).isdigit() else 0
        srv = db.query(Server).filter(Server.id == sid_int).first()
        if not srv:
            db.close()
            with ui.column().classes("w-full max-w-4xl mx-auto p-6 gap-4"):
                ui.label("Server Tidak Ditemukan").classes("text-xl font-bold text-rose-400")
                ui.button("Kembali ke Daftar Server", on_click=lambda: ui.navigate.to("/servers"))
            return

        ext = db.query(ServerExtras).filter(ServerExtras.server_id == sid_int).first()
        snap = db.query(SystemSnapshot).filter(SystemSnapshot.server_id == sid_int).order_by(SystemSnapshot.id.desc()).first()
        services = db.query(Service).filter(Service.server_id == sid_int).order_by(Service.service_name.asc()).all()
        
        # Ambil metrik layanan terakhir
        svc_metrics = {}
        for svc in services:
            m = db.query(Metric).filter(Metric.service_id == svc.id).order_by(Metric.id.desc()).first()
            if m:
                svc_metrics[svc.id] = m

        db.close()

        now = datetime.utcnow()
        is_up = bool(srv.last_seen and (now - srv.last_seen).total_seconds() < 45)

        hw = {}
        if ext and ext.hardware_specs:
            try:
                hw = json.loads(ext.hardware_specs)
            except Exception:
                pass

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6"):
            # Header Bar
            with ui.row().classes("w-full items-center justify-between"):
                with ui.row().classes("items-center gap-3"):
                    ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/servers")).props("dense flat round size=sm").classes("text-slate-300")
                    ui.icon("dns", size="28px").classes("text-blue-400")
                    with ui.column().classes("gap-0"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(srv.hostname).classes("text-2xl font-bold text-white")
                            ui.badge("ONLINE" if is_up else "OFFLINE", color="emerald-9" if is_up else "rose-9").classes("text-xs font-bold")
                            ui.badge("PROD" if srv.tier == 1 else "DEV", color="slate-800").classes("text-[10px] font-mono border border-slate-700")
                        ui.label(f"IP: {srv.ip_address} · Terakhir terlihat: {srv.last_seen.strftime('%d %b %Y %H:%M:%S') if srv.last_seen else '—'}").classes("text-xs text-slate-400 font-mono")

                ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to(f"/servers/{server_id}")).props("dense outline no-caps size=sm").classes("text-xs text-slate-300")

            # Metrics Cards (CPU, RAM, DISK, UPTIME)
            with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4"):
                cpu_val = f"{snap.cpu:.1f}%" if snap and snap.cpu is not None else "—"
                mem_pct = round(snap.mem_used / snap.mem_total * 100, 1) if snap and snap.mem_total else 0
                mem_val = f"{mem_pct}%" if snap and snap.mem_total else "—"
                upt_str = f"{snap.uptime_secs // 86400} hari" if snap and snap.uptime_secs else "—"
                
                with ui.card().classes("p-4 custom-card"):
                    ui.label("BEBAN CPU").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                    ui.label(cpu_val).classes("text-2xl font-bold text-white mt-1")
                    if snap and snap.load1 is not None:
                        ui.label(f"Load: {snap.load1:.2f} (1m)").classes("text-[10px] text-slate-500 font-mono")

                with ui.card().classes("p-4 custom-card"):
                    ui.label("PENGGUNAAN MEMORI").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                    ui.label(mem_val).classes("text-2xl font-bold text-white mt-1")
                    if snap and snap.mem_total:
                        used_gb = snap.mem_used / (1024**3)
                        tot_gb = snap.mem_total / (1024**3)
                        ui.label(f"{used_gb:.1f} GB / {tot_gb:.1f} GB").classes("text-[10px] text-slate-500 font-mono")

                with ui.card().classes("p-4 custom-card"):
                    ui.label("WAKTU AKTIF (UPTIME)").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                    ui.label(upt_str).classes("text-2xl font-bold text-white mt-1")
                    ui.label("Sistem Berjalan Normal").classes("text-[10px] text-emerald-400 font-mono")

                with ui.card().classes("p-4 custom-card"):
                    ui.label("AGEN TELEMETRI").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                    ui.label(ext.agent_version if ext and ext.agent_version else "—").classes("text-2xl font-bold text-white mt-1")
                    ui.label("Protokol V2 Aktif").classes("text-[10px] text-blue-400 font-mono")

            # Hardware & System Info Box
            with ui.card().classes("w-full p-4 custom-card"):
                ui.label("Informasi Sistem & Spesifikasi Perangkat Keras").classes("text-sm font-bold text-white mb-3")
                with ui.row().classes("w-full grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono"):
                    with ui.column().classes("gap-1"):
                        ui.label("SISTEM OPERASI:").classes("text-slate-500 text-[10px]")
                        ui.label(ext.os_label if ext and ext.os_label else "Linux").classes("text-slate-200")
                        ui.label("KERNEL:").classes("text-slate-500 text-[10px] mt-1")
                        ui.label(ext.kernel if ext and ext.kernel else "—").classes("text-slate-200")

                    with ui.column().classes("gap-1"):
                        ui.label("PROSESOR:").classes("text-slate-500 text-[10px]")
                        ui.label(hw.get("cpu_model", "—")).classes("text-slate-200")
                        ui.label("ARSITEKTUR & INTI:").classes("text-slate-500 text-[10px] mt-1")
                        cores_info = f"{hw.get('cpu_cores')} Cores ({ext.arch if ext else ''})" if hw.get('cpu_cores') else (ext.arch if ext else "—")
                        ui.label(cores_info).classes("text-slate-200")

                    with ui.column().classes("gap-1"):
                        ui.label("MODEL / PLATFORM:").classes("text-slate-500 text-[10px]")
                        ui.label(hw.get("system_model") or srv.platform_override or "Linux Host").classes("text-slate-200")
                        ui.label("UPDATE SISTEM (APT):").classes("text-slate-500 text-[10px] mt-1")
                        apt_info = f"{ext.apt_upgradable} paket dapat di-upgrade" if ext and ext.apt_upgradable else "Sistem mutakhir"
                        ui.label(apt_info).classes("text-emerald-400" if (not ext or not ext.apt_upgradable) else "text-amber-400")

            # Services Monitoring Table
            with ui.column().classes("w-full gap-2"):
                with ui.row().classes("w-full justify-between items-center"):
                    ui.label("Daftar Layanan Terpantau").classes("text-base font-bold text-white")
                    ui.badge(f"{len(services)} Layanan", color="slate-800").classes("text-xs border border-slate-700")

                svc_cols = [
                    {"name": "service", "label": "LAYANAN", "field": "service", "align": "left", "sortable": True},
                    {"name": "port", "label": "PORT", "field": "port", "align": "center"},
                    {"name": "process", "label": "PROSES", "field": "process", "align": "left"},
                    {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                    {"name": "latency", "label": "LATENSI", "field": "latency", "align": "right"},
                    {"name": "health", "label": "DIAGNOSTIK KESEHATAN", "field": "health", "align": "left"},
                ]

                svc_rows = []
                for svc in services:
                    m = svc_metrics.get(svc.id)
                    st = (m.status if m else "unknown").upper()
                    rt = f"{m.response_time_ms} ms" if m and m.response_time_ms is not None else "—"
                    msg = m.health_message if m and m.health_message else "—"
                    svc_rows.append({
                        "id": svc.id,
                        "service": svc.service_name,
                        "port": svc.port,
                        "process": svc.process_name,
                        "status": st,
                        "latency": rt,
                        "health": msg,
                    })

                t_svc = ui.table(columns=svc_cols, rows=svc_rows, row_key="id").props("dense flat bordered wrap-cells").classes("w-full")
                t_svc.add_slot("body-cell-status", """
                    <q-td :props="props">
                        <span :class="props.value === 'UP' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800'"
                              class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                            {{ props.value }}
                        </span>
                    </q-td>
                """)

    # -------------------------------------------------------------------------
    # 4. Halaman Insiden & Masalah (/problems)
    # -------------------------------------------------------------------------
    @ui.page("/problems")
    def page_problems(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="/problems")

        problems = db.query(ServerProblem).order_by(ServerProblem.started_at.desc()).limit(200).all()
        servers = db.query(Server).all()
        srv_map = {s.id: s.hostname for s in servers}
        db.close()

        now = datetime.utcnow()

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Insiden & Masalah Sistem").classes("text-xl font-bold text-white")
                    ui.label("Catatan telemetri insiden, alarm gangguan layanan, dan riwayat pemulihan otomatis").classes("text-xs text-slate-400")
                ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to("/problems")).props("dense outline no-caps size=sm").classes("text-xs text-slate-300")

            prob_cols = [
                {"name": "time", "label": "WAKTU MULAI", "field": "time", "align": "left", "sortable": True},
                {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                {"name": "severity", "label": "KEPARAHAN", "field": "severity", "align": "center"},
                {"name": "message", "label": "PESAN MASALAH", "field": "message", "align": "left"},
                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                {"name": "duration", "label": "DURASI", "field": "duration", "align": "right"},
            ]

            prob_rows = []
            for p in problems:
                is_open = (p.resolved_at is None)
                if is_open:
                    dur_sec = int((now - p.started_at).total_seconds()) if p.started_at else 0
                    dur_str = f"{dur_sec // 60} mnt" if dur_sec >= 60 else f"{dur_sec} dtk"
                else:
                    dur_sec = int((p.resolved_at - p.started_at).total_seconds()) if (p.resolved_at and p.started_at) else 0
                    dur_str = f"{dur_sec // 60} mnt (Selesai)"

                srv_name = srv_map.get(p.server_id, f"Server #{p.server_id}") if p.server_id else "Global / Probe"
                prob_rows.append({
                    "id": p.id,
                    "time": p.started_at.strftime("%d %b %H:%M:%S") if p.started_at else "—",
                    "server": srv_name,
                    "severity": (p.severity or "warning").upper(),
                    "message": p.message or "—",
                    "status": "TERBUKA" if is_open else "SELESAI",
                    "duration": dur_str,
                })

            search_prob = ui.input(placeholder="Cari insiden, pesan, atau server...").props("dense outlined debounce=300 clearable").classes("w-80 text-xs bg-slate-900")
            t_prob = ui.table(columns=prob_cols, rows=prob_rows, row_key="id", pagination=20).props("dense flat bordered wrap-cells").classes("w-full")
            search_prob.bind_value(t_prob, "filter")

            t_prob.add_slot("body-cell-severity", """
                <q-td :props="props">
                    <span :class="props.value === 'DANGER' || props.value === 'CRITICAL' || props.value === 'GAWAT' ? 'bg-rose-950 text-rose-400 border-rose-800' : (props.value === 'WARNING' || props.value === 'PERINGATAN' ? 'bg-amber-950 text-amber-400 border-amber-800' : 'bg-blue-950 text-blue-400 border-blue-800')"
                          class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                        {{ props.value }}
                    </span>
                </q-td>
            """)

            t_prob.add_slot("body-cell-status", """
                <q-td :props="props">
                    <span :class="props.value === 'TERBUKA' ? 'bg-amber-950 text-amber-400 border-amber-800' : 'bg-slate-800 text-slate-400 border-slate-700'"
                          class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                        {{ props.value }}
                    </span>
                </q-td>
            """)

    # -------------------------------------------------------------------------
    # 5. Halaman Riwayat Tindakan / Audit (/audit)
    # -------------------------------------------------------------------------
    @ui.page("/audit")
    def page_audit(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="/audit")

        audits = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(200).all()
        servers = db.query(Server).all()
        srv_map = {s.id: s.hostname for s in servers}
        db.close()

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Riwayat Tindakan").classes("text-xl font-bold text-white")
                    ui.label("Catatan jejak audit aktivitas operator, kontrol layanan, dan eksekusi perintah").classes("text-xs text-slate-400")
                ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to("/audit")).props("dense outline no-caps size=sm").classes("text-xs text-slate-300")

            audit_cols = [
                {"name": "time", "label": "WAKTU", "field": "time", "align": "left", "sortable": True},
                {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                {"name": "action", "label": "TINDAKAN", "field": "action", "align": "left"},
                {"name": "target", "label": "TARGET", "field": "target", "align": "left"},
                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
            ]
            audit_rows = []
            for a in audits:
                srv_name = srv_map.get(a.server_id, "Sistem") if a.server_id else "Sistem"
                res_str = (a.result or "").lower()
                is_ok = ("berhasil" in res_str or "success" in res_str or "ok" in res_str)
                status_str = "BERHASIL" if is_ok else (a.result.upper() if a.result else "BERHASIL")
                audit_rows.append({
                    "id": a.id,
                    "time": a.created_at.strftime("%d %b %H:%M:%S") if a.created_at else "—",
                    "user": a.username or "sistem",
                    "server": srv_name,
                    "action": a.action or "—",
                    "target": a.target or "—",
                    "status": status_str,
                })

            search_audit = ui.input(placeholder="Cari jejak audit, pengguna, atau tindakan...").props("dense outlined debounce=300 clearable").classes("w-80 text-xs bg-slate-900")
            t_aud = ui.table(columns=audit_cols, rows=audit_rows, row_key="id", pagination=20).props("dense flat bordered wrap-cells").classes("w-full")
            search_audit.bind_value(t_aud, "filter")

            t_aud.add_slot("body-cell-status", """
                <q-td :props="props">
                    <span :class="props.value === 'BERHASIL' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800'"
                          class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                        {{ props.value }}
                    </span>
                </q-td>
            """)

    # -------------------------------------------------------------------------
    # 6. Halaman Probing Endpoint (/probing)
    # -------------------------------------------------------------------------
    @ui.page("/probing")
    def page_probing(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="/probing")

        probes = db.query(ProbeTarget).all()
        servers = db.query(Server).all()
        srv_map = {s.id: s.hostname for s in servers}
        db.close()

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Synthetic Probing Endpoint").classes("text-xl font-bold text-white")
                    ui.label("Pengawasan endpoint eksternal, HTTP/HTTPS, port TCP, dan latensi ICMP Ping secara berkala").classes("text-xs text-slate-400")
                ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to("/probing")).props("dense outline no-caps size=sm").classes("text-xs text-slate-300")

            probe_cols = [
                {"name": "name", "label": "NAMA TARGET", "field": "name", "align": "left", "sortable": True},
                {"name": "type", "label": "TIPE", "field": "type", "align": "center"},
                {"name": "target", "label": "ENDPOINT TARGET", "field": "target", "align": "left"},
                {"name": "server", "label": "SERVER ASAL", "field": "server", "align": "left"},
                {"name": "latency", "label": "LATENSI", "field": "latency", "align": "right"},
                {"name": "uptime", "label": "UPTIME 24J", "field": "uptime", "align": "right"},
                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
            ]

            probe_rows = []
            for pb in probes:
                srv_name = srv_map.get(pb.server_id, "Independen") if pb.server_id else "Independen"
                lat_str = f"{pb.last_latency_ms:.1f} ms" if pb.last_latency_ms is not None else "—"
                probe_rows.append({
                    "id": pb.id,
                    "name": pb.name,
                    "type": pb.probe_type.upper(),
                    "target": pb.target,
                    "server": srv_name,
                    "latency": lat_str,
                    "uptime": f"{pb.uptime_24h:.1f}%",
                    "status": pb.status.upper() if pb.status else "UNKNOWN",
                })

            search_probe = ui.input(placeholder="Cari target probing...").props("dense outlined debounce=300 clearable").classes("w-80 text-xs bg-slate-900")
            t_pb = ui.table(columns=probe_cols, rows=probe_rows, row_key="id", pagination=15).props("dense flat bordered wrap-cells").classes("w-full")
            search_probe.bind_value(t_pb, "filter")

            t_pb.add_slot("body-cell-status", """
                <q-td :props="props">
                    <span :class="props.value === 'UP' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800'"
                          class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                        {{ props.value }}
                    </span>
                </q-td>
            """)

    # -------------------------------------------------------------------------
    # 7. Halaman Pemeliharaan (/maintenance)
    # -------------------------------------------------------------------------
    @ui.page("/maintenance")
    def page_maintenance(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="/maintenance")

        mws = db.query(MaintenanceWindow).order_by(MaintenanceWindow.start_time.desc()).all()
        servers = db.query(Server).all()
        srv_map = {s.id: s.hostname for s in servers}
        db.close()

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Jendela Pemeliharaan Sistem").classes("text-xl font-bold text-white")
                    ui.label("Jadwal perawatan rutin, pemadaman terencana, dan penekanan notifikasi alarm").classes("text-xs text-slate-400")
                ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to("/maintenance")).props("dense outline no-caps size=sm").classes("text-xs text-slate-300")

            mw_cols = [
                {"name": "title", "label": "JUDUL PEMELIHARAAN", "field": "title", "align": "left", "sortable": True},
                {"name": "server", "label": "SERVER SASARAN", "field": "server", "align": "left"},
                {"name": "start", "label": "WAKTU MULAI", "field": "start", "align": "left"},
                {"name": "end", "label": "WAKTU SELESAI", "field": "end", "align": "left"},
                {"name": "type", "label": "TIPE", "field": "type", "align": "center"},
                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
            ]

            mw_rows = []
            for m in mws:
                srv_name = srv_map.get(m.server_id, "Semua Server") if m.server_id else "Semua Server"
                mw_rows.append({
                    "id": m.id,
                    "title": m.title,
                    "server": srv_name,
                    "start": m.start_time.strftime("%d %b %Y %H:%M") if m.start_time else "—",
                    "end": m.end_time.strftime("%d %b %Y %H:%M") if m.end_time else "—",
                    "type": m.schedule_type.upper() if m.schedule_type else "ONCE",
                    "status": m.status.upper() if m.status else "SCHEDULED",
                })

            if not mw_rows:
                with ui.card().classes("w-full p-6 custom-card items-center justify-center text-center"):
                    ui.icon("event_available", size="36px").classes("text-slate-500 mb-2")
                    ui.label("Tidak ada jadwal pemeliharaan sistem yang sedang berlangsung atau terjadwal.").classes("text-sm text-slate-400")
            else:
                ui.table(columns=mw_cols, rows=mw_rows, row_key="id").props("dense flat bordered wrap-cells").classes("w-full")

    # -------------------------------------------------------------------------
    # 8. Halaman Pengguna (/users)
    # -------------------------------------------------------------------------
    @ui.page("/users")
    def page_users(request: Request):
        db = session_factory()
        user = _get_auth_user(request, db)
        if not user:
            db.close()
            return RedirectResponse("/login")

        _render_layout(request, user, active_tab="/users")

        users = db.query(User).all()
        db.close()

        with ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4"):
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Manajemen Pengguna & Operator").classes("text-xl font-bold text-white")
                    ui.label("Daftar akun operator sistem NOC, peran otorisasi, dan status keamanan 2FA").classes("text-xs text-slate-400")
                ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to("/users")).props("dense outline no-caps size=sm").classes("text-xs text-slate-300")

            usr_cols = [
                {"name": "username", "label": "NAMA PENGGUNA", "field": "username", "align": "left", "sortable": True},
                {"name": "role", "label": "PERAN / HAK AKSES", "field": "role", "align": "left"},
                {"name": "totp", "label": "2FA TOTP", "field": "totp", "align": "center"},
                {"name": "last_login", "label": "LOGIN TERAKHIR", "field": "last_login", "align": "left"},
                {"name": "ip", "label": "IP ASAL", "field": "ip", "align": "left"},
                {"name": "status", "label": "STATUS AKUN", "field": "status", "align": "center"},
            ]

            usr_rows = []
            for u in users:
                usr_rows.append({
                    "id": u.id,
                    "username": u.username,
                    "role": u.role_display() if hasattr(u, "role_display") else u.role,
                    "totp": "AKTIF" if u.totp_enabled else "NONAKTIF",
                    "last_login": u.last_login_at.strftime("%d %b %Y %H:%M") if u.last_login_at else "—",
                    "ip": u.last_login_ip or "—",
                    "status": "AKTIF" if u.is_active else "DIBLOKIR",
                })

            t_usr = ui.table(columns=usr_cols, rows=usr_rows, row_key="id").props("dense flat bordered wrap-cells").classes("w-full")
            t_usr.add_slot("body-cell-status", """
                <q-td :props="props">
                    <span :class="props.value === 'AKTIF' ? 'bg-emerald-950 text-emerald-400 border-emerald-800' : 'bg-rose-950 text-rose-400 border-rose-800'"
                          class="text-[10px] font-bold px-2 py-0.5 rounded border font-mono">
                        {{ props.value }}
                    </span>
                </q-td>
            """)

    # Mount NiceGUI ke root aplikasi FastAPI
    ui.run_with(
        fastapi_app,
        mount_path="/",
        title="Pantau Server - NOC Mandiri",
        dark=True,
        language="id",
        tailwind=True
    )
