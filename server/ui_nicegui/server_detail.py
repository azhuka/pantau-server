"""
Modul Pusat Operasi Server Detail (Server Operations Center & Sub-Tabs)
======================================================================
Menyediakan inspeksi mendalam terhadap satu node server dengan hero header
kontrol operasional, dan 10 sub-tab komprehensif tanpa data hardcode.
"""

from datetime import datetime
import json
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, Command, Metric, Server, ServerExtras, ServerProblem, Service, SystemSnapshot
from .auth import get_auth_user
from .common import format_bytes, format_duration, get_db, notify_error, notify_info, notify_success
from .layout import render_layout


def setup_server_detail_routes(session_factory):
    """Mendaftarkan rute detail server ke NiceGUI engine."""

    @ui.page("/servers/{server_id}")
    def page_server_detail(request: Request, server_id: int):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username

            server = db.query(Server).filter(Server.id == server_id).first()
            if not server:
                return RedirectResponse("/servers")

            srv_id = server.id
            srv_host = server.hostname
            srv_ip = server.ip_address
            srv_tier = server.tier
            srv_last_seen = server.last_seen
            srv_is_maint = bool(server.is_maintenance)
            srv_maint_reason = server.maintenance_reason or ""
            srv_platform = server.platform_override or "Linux"

            # Ambil data snapshot terbaru dan extras
            snap = (
                db.query(SystemSnapshot)
                .filter(SystemSnapshot.server_id == srv_id)
                .order_by(SystemSnapshot.id.desc())
                .first()
            )
            ext = db.query(ServerExtras).filter(ServerExtras.server_id == srv_id).first()
            services = db.query(Service).filter(Service.server_id == srv_id).all()
            problems = (
                db.query(ServerProblem)
                .filter(ServerProblem.server_id == srv_id)
                .order_by(ServerProblem.started_at.desc())
                .all()
            )

        render_layout(request, user, active_tab="servers")

        container = ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-6")

        # Parsing data JSON telemetri extras & snapshots
        disks_data = []
        if snap and snap.disks:
            try:
                disks_data = json.loads(snap.disks) if isinstance(snap.disks, str) else snap.disks
            except Exception:
                pass

        net_data = []
        if snap and snap.net:
            try:
                net_data = json.loads(snap.net) if isinstance(snap.net, str) else snap.net
            except Exception:
                pass

        hw_specs = {}
        if ext and ext.hardware_specs:
            try:
                hw_specs = json.loads(ext.hardware_specs) if isinstance(ext.hardware_specs, str) else ext.hardware_specs
            except Exception:
                pass

        top_procs = {}
        if ext and ext.top_procs:
            try:
                top_procs = json.loads(ext.top_procs) if isinstance(ext.top_procs, str) else ext.top_procs
            except Exception:
                pass

        cron_data = {}
        if ext and ext.cron_jobs:
            try:
                cron_data = json.loads(ext.cron_jobs) if isinstance(ext.cron_jobs, str) else ext.cron_jobs
            except Exception:
                pass

        firewall_data = {}
        if ext and ext.firewall:
            try:
                firewall_data = json.loads(ext.firewall) if isinstance(ext.firewall, str) else ext.firewall
            except Exception:
                pass

        listening_ports = []
        if ext and ext.listening_ports:
            try:
                listening_ports = json.loads(ext.listening_ports) if isinstance(ext.listening_ports, str) else ext.listening_ports
            except Exception:
                pass

        accounts_data = []
        if ext and ext.accounts:
            try:
                accounts_data = json.loads(ext.accounts) if isinstance(ext.accounts, str) else ext.accounts
            except Exception:
                pass

        system_logs = []
        if ext and ext.system_logs:
            try:
                system_logs = json.loads(ext.system_logs) if isinstance(ext.system_logs, str) else ext.system_logs
            except Exception:
                pass

        apt_packages = []
        if ext and ext.apt_packages:
            try:
                apt_packages = json.loads(ext.apt_packages) if isinstance(ext.apt_packages, str) else ext.apt_packages
            except Exception:
                pass

        # Helper Eksekusi Command ke Agen
        def _queue_command(action_name: str, service_id: int | None = None, params: dict | None = None, note: str = ""):
            with get_db(session_factory) as db:
                cmd = Command(
                    server_id=srv_id,
                    service_id=service_id,
                    action=action_name,
                    params=json.dumps(params) if params else None,
                    issued_by=current_username,
                    status="pending",
                )
                db.add(cmd)
                audit = AuditLog(
                    user_id=current_user_id,
                    username=current_username,
                    server_id=srv_id,
                    action=f"command_{action_name}",
                    target=f"{srv_host} ({note})",
                    result="pending",
                )
                db.add(audit)
                db.commit()
                notify_success(f"Perintah '{action_name}' berhasil dikirim ke antrean agen ({srv_host}).")

        with container:
            # -----------------------------------------------------------------
            # Hero Header Operasional Server
            # -----------------------------------------------------------------
            now = datetime.utcnow()
            is_online = bool(srv_last_seen and (now - srv_last_seen).total_seconds() < 45)
            tier_label = "PROD" if srv_tier == 1 else "DEV"

            with ui.card().classes("w-full p-6 custom-card flex flex-col md:flex-row items-start md:items-center justify-between gap-4"):
                with ui.row().classes("items-center gap-4"):
                    ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/servers")).props("dense flat round color=slate-4")
                    ui.icon("dns", size="36px").classes("text-blue-400")
                    with ui.column().classes("gap-1"):
                        with ui.row().classes("items-center gap-2"):
                            ui.label(srv_host).classes("text-2xl font-bold text-white")
                            ui.badge("ONLINE" if is_online else "OFFLINE", color="emerald-9" if is_online else "rose-9").classes("text-[10px] font-bold px-2 py-0.5")
                            ui.badge(tier_label, color="slate-800").classes("text-[10px] font-mono border border-slate-700")
                            if srv_is_maint:
                                ui.badge("PEMELIHARAAN", color="amber-9").classes("text-[10px] font-bold px-2 py-0.5")
                        ui.label(f"IP: {srv_ip} · Platform: {srv_platform} · Terakhir terlihat: {srv_last_seen.strftime('%d %b %Y %H:%M:%S') if srv_last_seen else '—'}").classes("text-xs text-slate-400 font-mono")

                # Tombol Aksi Header
                with ui.row().classes("items-center gap-2"):
                    ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to(f"/servers/{srv_id}")).props("dense outline no-caps size=sm color=primary").classes("text-xs")

                    # Dialog Mode Pemeliharaan
                    maint_dlg = ui.dialog()
                    with maint_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                        ui.label(f"Mode Pemeliharaan: {srv_host}").classes("text-base font-bold text-white")
                        maint_dur = ui.number("Durasi Pemeliharaan (Menit)", value=60, min=5, max=1440).props("dense outlined dark")
                        maint_reason = ui.input("Alasan Pemeliharaan", value=srv_maint_reason or "Perawatan rutin server").props("dense outlined dark")

                        def _toggle_maintenance(enable: bool):
                            with get_db(session_factory) as db:
                                s = db.query(Server).filter(Server.id == srv_id).first()
                                if s:
                                    s.is_maintenance = 1 if enable else 0
                                    s.maintenance_reason = maint_reason.value if enable else None
                                    db.commit()
                                    notify_success(f"Mode pemeliharaan {'diaktifkan' if enable else 'dinonaktifkan'}.")
                            maint_dlg.close()
                            ui.navigate.to(f"/servers/{srv_id}")

                        with ui.row().classes("w-full justify-end gap-2 mt-2"):
                            ui.button("Batal", on_click=maint_dlg.close).props("dense flat no-caps color=grey-5")
                            if srv_is_maint:
                                ui.button("Matikan Pemeliharaan", on_click=lambda: _toggle_maintenance(False)).props("dense unelevated color=emerald-8 no-caps")
                            else:
                                ui.button("Aktifkan Pemeliharaan", on_click=lambda: _toggle_maintenance(True)).props("dense unelevated color=amber-8 no-caps")

                    ui.button("Pemeliharaan", icon="build", on_click=maint_dlg.open).props("dense outline no-caps size=sm color=amber-4").classes("text-xs")

                    # Dialog Reboot Host
                    reboot_dlg = ui.dialog()
                    with reboot_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                        ui.label(f"Konfirmasi Reboot: {srv_host}").classes("text-base font-bold text-rose-400")
                        ui.label("Peringatan: Perintah ini akan mengirim instruksi reboot ke sistem operasi server. Seluruh proses aktif akan dihentikan.").classes("text-xs text-slate-300 leading-relaxed")

                        def _do_reboot():
                            _queue_command("reboot_host", note="Permintaan reboot host via dashboard NOC")
                            reboot_dlg.close()

                        with ui.row().classes("w-full justify-end gap-2 mt-2"):
                            ui.button("Batal", on_click=reboot_dlg.close).props("dense flat no-caps color=grey-5")
                            ui.button("Reboot Sekarang", on_click=_do_reboot).props("dense unelevated color=negative no-caps")

                    ui.button("Reboot Host", icon="restart_alt", on_click=reboot_dlg.open).props("dense outline no-caps size=sm color=rose-4").classes("text-xs")

            # -----------------------------------------------------------------
            # 10 Sub-Tabs Server Operations Center
            # -----------------------------------------------------------------
            with ui.tabs().classes("w-full bg-slate-900 border border-slate-800 rounded-lg text-slate-400") as detail_tabs:
                t_perf = ui.tab("Performa", icon="speed")
                t_svc = ui.tab("Layanan", icon="settings")
                t_prob = ui.tab("Insiden", icon="warning")
                t_pkg = ui.tab("Paket OS", icon="inventory_2")
                t_proc = ui.tab("Proses", icon="memory")
                t_port = ui.tab("Port Jaringan", icon="lan")
                t_sec = ui.tab("Pengguna & Sesi", icon="security")
                t_fw = ui.tab("Firewall", icon="shield")
                t_cron = ui.tab("Cron & Timer", icon="schedule")
                t_log = ui.tab("Log Sistem", icon="article")

            with ui.tab_panels(detail_tabs, value=t_perf).classes("w-full bg-transparent p-0"):

                # -------------------------------------------------------------
                # SUB-TAB 1: PERFORMA & SPESIFIKASI SISTEM
                # -------------------------------------------------------------
                with ui.tab_panel(t_perf).classes("gap-6 flex flex-col p-0"):
                    # 4 Kartu Metrik Performa (CPU, RAM, Uptime, Agen)
                    with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4"):
                        cpu_val = f"{snap.cpu:.1f}%" if snap and snap.cpu is not None else "—"
                        mem_pct = round(snap.mem_used / snap.mem_total * 100, 1) if snap and snap.mem_total else 0
                        mem_val = f"{mem_pct}%" if snap and snap.mem_total else "—"
                        upt_str = f"{snap.uptime_secs // 86400} hari" if snap and snap.uptime_secs else "—"

                        with ui.card().classes("p-4 custom-card"):
                            ui.label("BEBAN CPU").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                            ui.label(cpu_val).classes("text-2xl font-bold text-white mt-1")
                            if snap and snap.load1 is not None:
                                ui.label(f"Load 1m: {snap.load1:.2f} · 5m: {snap.load5 or 0:.2f}").classes("text-[10px] text-slate-500 font-mono")

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
                            ui.label("Sistem Beroperasi Stabil").classes("text-[10px] text-emerald-400 font-mono")

                        with ui.card().classes("p-4 custom-card"):
                            ui.label("AGEN TELEMETRI").classes("text-[10px] font-bold text-slate-400 uppercase tracking-wider")
                            ui.label(f"v{ext.agent_version if ext and ext.agent_version else '—'}").classes("text-2xl font-bold text-white mt-1")
                            ui.label("Protokol Outbound Pull Aktif").classes("text-[10px] text-blue-400 font-mono")

                    # Tabel Partisi Disk
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Penyimpanan & Partisi Disk").classes("text-sm font-bold text-white mb-2")
                        if not disks_data:
                            ui.label("Tidak ada data partisi disk yang dilaporkan.").classes("text-xs text-slate-500")
                        else:
                            d_cols = [
                                {"name": "mount", "label": "MOUNT POINT", "field": "mount", "align": "left"},
                                {"name": "type", "label": "TIPE FS", "field": "type", "align": "left"},
                                {"name": "used", "label": "TERPAKAI", "field": "used", "align": "right"},
                                {"name": "total", "label": "TOTAL", "field": "total", "align": "right"},
                                {"name": "pct", "label": "PERSENTASE", "field": "pct", "align": "center"},
                            ]
                            d_rows = []
                            for d in disks_data:
                                d_rows.append({
                                    "mount": d.get("mount", "—"),
                                    "type": d.get("type", "—"),
                                    "used": format_bytes(d.get("used")),
                                    "total": format_bytes(d.get("total")),
                                    "pct": f"{d.get('pct', 0)}%",
                                })
                            ui.table(columns=d_cols, rows=d_rows, row_key="mount").classes("w-full bg-slate-900")

                    # Tabel Antarmuka Jaringan
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Antarmuka Jaringan & Lalu Lintas (Network Interfaces)").classes("text-sm font-bold text-white mb-2")
                        if not net_data:
                            ui.label("Tidak ada data antarmuka jaringan yang dilaporkan.").classes("text-xs text-slate-500")
                        else:
                            net_cols = [
                                {"name": "iface", "label": "ANTARMUKA", "field": "iface", "align": "left"},
                                {"name": "rx", "label": "TOTAL RX (DITERIMA)", "field": "rx", "align": "right"},
                                {"name": "tx", "label": "TOTAL TX (DIKIRIM)", "field": "tx", "align": "right"},
                                {"name": "rx_rate", "label": "KECEPATAN RX", "field": "rx_rate", "align": "right"},
                                {"name": "tx_rate", "label": "KECEPATAN TX", "field": "tx_rate", "align": "right"},
                                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                            ]
                            net_rows = []
                            for n in net_data:
                                net_rows.append({
                                    "iface": n.get("iface", "—"),
                                    "rx": format_bytes(n.get("rx")),
                                    "tx": format_bytes(n.get("tx")),
                                    "rx_rate": f"{format_bytes(n.get('rx_rate'))}/s" if n.get("rx_rate") else "0 B/s",
                                    "tx_rate": f"{format_bytes(n.get('tx_rate'))}/s" if n.get("tx_rate") else "0 B/s",
                                    "status": "UP" if n.get("is_up") else "DOWN",
                                })
                            ntbl = ui.table(columns=net_cols, rows=net_rows, row_key="iface").classes("w-full bg-slate-900")
                            ntbl.add_slot("body-cell-status", """
                                <q-td :props="props">
                                    <q-badge :color="props.row.status === 'UP' ? 'emerald-9' : 'rose-9'" class="text-[9px] font-bold px-1.5 py-0.5">
                                        {{ props.row.status }}
                                    </q-badge>
                                </q-td>
                            """)

                    # Spesifikasi Perangkat Keras
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Spesifikasi Perangkat Keras & Mesin Host").classes("text-sm font-bold text-white mb-3")
                        with ui.row().classes("w-full grid grid-cols-1 md:grid-cols-3 gap-4 text-xs"):
                            with ui.column().classes("gap-1"):
                                ui.label("SISTEM OPERASI:").classes("text-[10px] font-bold text-slate-500")
                                ui.label(ext.os_label or "Linux" if ext else "Linux").classes("font-semibold text-slate-200")
                            with ui.column().classes("gap-1"):
                                ui.label("PROSESOR:").classes("text-[10px] font-bold text-slate-500")
                                ui.label(hw_specs.get("cpu_model", "—")).classes("font-semibold text-slate-200")
                            with ui.column().classes("gap-1"):
                                ui.label("MODEL / PLATFORM:").classes("text-[10px] font-bold text-slate-500")
                                ui.label(hw_specs.get("board", srv_platform)).classes("font-semibold text-slate-200")

                # -------------------------------------------------------------
                # SUB-TAB 2: DAFTAR LAYANAN TERPANTAU
                # -------------------------------------------------------------
                with ui.tab_panel(t_svc).classes("gap-4 flex flex-col p-0"):
                    with ui.card().classes("w-full p-4 custom-card"):
                        with ui.row().classes("w-full items-center justify-between mb-3"):
                            with ui.column().classes("gap-0"):
                                ui.label("Daftar Layanan Terpantau").classes("text-sm font-bold text-white")
                                ui.label("Kontrol status layanan systemd, restart daemon, dan ubah aturan pemantauan").classes("text-xs text-slate-400")
                            ui.badge(f"{len(services)} Layanan", color="slate-800").classes("text-xs font-mono border border-slate-700")

                        if not services:
                            ui.label("Belum ada layanan yang dikonfigurasi untuk dipantau pada server ini.").classes("text-xs text-slate-500")
                        else:
                            svc_cols = [
                                {"name": "name", "label": "LAYANAN", "field": "name", "align": "left"},
                                {"name": "port", "label": "PORT", "field": "port", "align": "center"},
                                {"name": "proc", "label": "PROSES", "field": "proc", "align": "left"},
                                {"name": "prio", "label": "PRIORITAS", "field": "prio", "align": "center"},
                                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                                {"name": "latency", "label": "LATENSI", "field": "latency", "align": "center"},
                                {"name": "health", "label": "DIAGNOSTIK KESEHATAN", "field": "health", "align": "left"},
                                {"name": "actions", "label": "KONTROL AKSI", "field": "actions", "align": "center"},
                            ]
                            svc_rows = []
                            with get_db(session_factory) as db:
                                for s in services:
                                    last_metric = (
                                        db.query(Metric)
                                        .filter(Metric.service_id == s.id)
                                        .order_by(Metric.id.desc())
                                        .first()
                                    )
                                    status_txt = "DIABAIKAN" if s.is_ignored else (last_metric.status.upper() if last_metric else "UNKNOWN")
                                    latency_txt = f"{last_metric.response_time_ms} ms" if last_metric and last_metric.response_time_ms is not None else "—"
                                    health_txt = last_metric.health_message if last_metric and last_metric.health_message else "TCP connect OK"

                                    svc_rows.append({
                                        "id": s.id,
                                        "name": s.service_name,
                                        "port": s.port,
                                        "proc": s.process_name,
                                        "is_core": bool(s.is_core),
                                        "prio": "UTAMA" if s.is_core else "PENDUKUNG",
                                        "is_ignored": bool(s.is_ignored),
                                        "status": status_txt,
                                        "latency": latency_txt,
                                        "health": health_txt,
                                    })

                            stbl = ui.table(columns=svc_cols, rows=svc_rows, row_key="id").classes("w-full bg-slate-900")
                            
                            stbl.add_slot("body-cell-prio", """
                                <q-td :props="props">
                                    <q-badge :color="props.row.is_core ? 'blue-9' : 'slate-7'" class="text-[9px] font-bold px-1.5 py-0.5">
                                        {{ props.row.prio }}
                                    </q-badge>
                                </q-td>
                            """)

                            stbl.add_slot("body-cell-status", """
                                <q-td :props="props">
                                    <q-badge :color="props.row.status === 'UP' ? 'emerald-9' : (props.row.status === 'DIABAIKAN' ? 'slate-8' : 'rose-9')"
                                             class="text-[9px] font-bold px-1.5 py-0.5">
                                        {{ props.row.status }}
                                    </q-badge>
                                </q-td>
                            """)

                            stbl.add_slot("body-cell-actions", """
                                <q-td :props="props">
                                    <div class="row items-center justify-center gap-1">
                                        <q-btn dense outline size="xs" color="amber-4" icon="restart_alt" label="Restart" no-caps
                                               @click="() => $parent.$emit('restart_svc', props.row.id)" />
                                        <q-btn dense flat round size="xs" :icon="props.row.is_core ? 'star' : 'star_border'" color="blue-4"
                                               @click="() => $parent.$emit('toggle_core', props.row.id)" />
                                    </div>
                                </q-td>
                            """)

                            def _restart_svc(svc_id: int):
                                _queue_command("restart", service_id=svc_id, note="Restart layanan via Web NOC")

                            def _toggle_core(svc_id: int):
                                with get_db(session_factory) as db:
                                    s = db.query(Service).filter(Service.id == svc_id).first()
                                    if s:
                                        s.is_core = 0 if s.is_core else 1
                                        db.commit()
                                        notify_info(f"Prioritas layanan {s.service_name} diubah.")
                                ui.navigate.to(f"/servers/{srv_id}")

                            stbl.on("restart_svc", lambda e: _restart_svc(e.args))
                            stbl.on("toggle_core", lambda e: _toggle_core(e.args))

                # -------------------------------------------------------------
                # SUB-TAB 3: RIWAYAT INSIDEN & GANGGUAN SERVER
                # -------------------------------------------------------------
                with ui.tab_panel(t_prob).classes("gap-4 flex flex-col p-0"):
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Riwayat Insiden & Gangguan Server").classes("text-sm font-bold text-white mb-2")
                        if not problems:
                            ui.label("Tidak ada catatan insiden pada server ini.").classes("text-xs text-slate-500")
                        else:
                            p_cols = [
                                {"name": "sev", "label": "KEPARAHAN", "field": "sev", "align": "center"},
                                {"name": "msg", "label": "MASALAH / PESAN", "field": "msg", "align": "left"},
                                {"name": "started", "label": "MULAI", "field": "started", "align": "left"},
                                {"name": "resolved", "label": "SELESAI", "field": "resolved", "align": "left"},
                                {"name": "dur", "label": "DURASI", "field": "dur", "align": "left"},
                                {"name": "action", "label": "STATUS / AKSI", "field": "action", "align": "center"},
                            ]
                            p_rows = []
                            for p in problems:
                                p_rows.append({
                                    "id": p.id,
                                    "sev": p.severity.upper() if p.severity else "PERINGATAN",
                                    "msg": p.message or p.service_name or "Gangguan terdeteksi",
                                    "started": p.started_at.strftime("%Y-%m-%d %H:%M:%S") if p.started_at else "—",
                                    "resolved": p.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if p.resolved_at else "—",
                                    "dur": format_duration(p.started_at, p.resolved_at or now),
                                    "is_open": p.resolved_at is None,
                                })

                            ptbl = ui.table(columns=p_cols, rows=p_rows, row_key="id").classes("w-full bg-slate-900")
                            ptbl.add_slot("body-cell-sev", """
                                <q-td :props="props">
                                    <q-badge :color="props.row.sev === 'DANGER' || props.row.sev === 'CRITICAL' ? 'rose-9' : 'amber-9'" class="text-[9px] font-bold px-1.5 py-0.5">
                                        {{ props.row.sev }}
                                    </q-badge>
                                </q-td>
                            """)
                            ptbl.add_slot("body-cell-action", """
                                <q-td :props="props">
                                    <span v-if="!props.row.is_open" class="text-xs text-slate-500 font-mono">Terselesaikan</span>
                                    <q-btn v-else dense outline size="xs" color="emerald-4" icon="check" label="Tandai Selesai" no-caps
                                           @click="() => $parent.$emit('resolve_prob', props.row.id)" />
                                </q-td>
                            """)

                            def _resolve_one_problem(prob_id: int):
                                with get_db(session_factory) as db:
                                    prob = db.query(ServerProblem).filter(ServerProblem.id == prob_id).first()
                                    if prob:
                                        prob.resolved_at = datetime.utcnow()
                                        db.commit()
                                        notify_success("Insiden ditandai selesai.")
                                ui.navigate.to(f"/servers/{srv_id}")

                            ptbl.on("resolve_prob", lambda e: _resolve_one_problem(e.args))

                # -------------------------------------------------------------
                # SUB-TAB 4: INVENTARIS PAKET & PEMBARUAN APT
                # -------------------------------------------------------------
                with ui.tab_panel(t_pkg).classes("gap-4 flex flex-col p-0"):
                    with ui.card().classes("w-full p-4 custom-card"):
                        with ui.row().classes("w-full items-center justify-between mb-3"):
                            with ui.column().classes("gap-0"):
                                ui.label("Inventaris Paket & Pembaruan APT").classes("text-sm font-bold text-white")
                                apt_cnt = ext.apt_upgradable if ext and ext.apt_upgradable is not None else 0
                                last_up = ext.apt_last_update.strftime("%Y-%m-%d %H:%M:%S") if ext and ext.apt_last_update else "—"
                                ui.label(f"Status: {apt_cnt} paket dapat di-upgrade · Pembaruan cache terakhir: {last_up}").classes("text-xs text-slate-400")

                            with ui.row().classes("items-center gap-2"):
                                ui.button("Perbarui Cache APT", icon="sync", on_click=lambda: _queue_command("apt_update", note="apt-get update")).props("dense outline no-caps size=sm color=primary").classes("text-xs")
                                ui.button("Upgrade Seluruh Paket", icon="system_update_alt", on_click=lambda: _queue_command("apt_upgrade", note="apt-get upgrade -y")).props("dense unelevated no-caps size=sm color=emerald-8").classes("text-xs")

                        if not apt_packages:
                            ui.label("Seluruh repositori dan paket sistem telah mutakhir (Up to Date).").classes("text-xs text-emerald-400")
                        else:
                            pkg_cols = [
                                {"name": "pkg", "label": "NAMA PAKET", "field": "pkg", "align": "left"},
                                {"name": "cur", "label": "VERSI SAAT INI", "field": "cur", "align": "left"},
                                {"name": "new", "label": "VERSI BARU", "field": "new", "align": "left"},
                                {"name": "arch", "label": "ARSITEKTUR", "field": "arch", "align": "center"},
                            ]
                            pkg_rows = []
                            for itm in apt_packages:
                                if isinstance(itm, dict):
                                    pkg_rows.append({
                                        "pkg": itm.get("name", "—"),
                                        "cur": itm.get("current_version", "—"),
                                        "new": itm.get("new_version", "—"),
                                        "arch": itm.get("arch", "—"),
                                    })
                                else:
                                    pkg_rows.append({"pkg": str(itm), "cur": "—", "new": "Tersedia", "arch": "—"})
                            ui.table(columns=pkg_cols, rows=pkg_rows, row_key="pkg").classes("w-full bg-slate-900")

                # -------------------------------------------------------------
                # SUB-TAB 5: PROSES SISTEM TERATAS (TOP PROCESSES)
                # -------------------------------------------------------------
                with ui.tab_panel(t_proc).classes("gap-4 flex flex-col p-0"):
                    with ui.row().classes("w-full grid grid-cols-1 lg:grid-cols-2 gap-4"):
                        # Top CPU
                        with ui.card().classes("w-full p-4 custom-card"):
                            ui.label("Proses Pemakaian CPU Terbesar").classes("text-sm font-bold text-white mb-2")
                            cpu_procs = top_procs.get("cpu", []) if isinstance(top_procs, dict) else []
                            if not cpu_procs:
                                ui.label("Tidak ada data proses CPU.").classes("text-xs text-slate-500")
                            else:
                                pr_cols = [
                                    {"name": "pid", "label": "PID", "field": "pid", "align": "center"},
                                    {"name": "user", "label": "USER", "field": "user", "align": "left"},
                                    {"name": "cpu", "label": "% CPU", "field": "cpu", "align": "right"},
                                    {"name": "cmd", "label": "PERINTAH", "field": "cmd", "align": "left"},
                                ]
                                pr_rows = [
                                    {
                                        "pid": p.get("pid", "—"),
                                        "user": p.get("user", "—"),
                                        "cpu": f"{p.get('cpu', 0)}%",
                                        "cmd": p.get("command", "—"),
                                    }
                                    for p in cpu_procs[:15]
                                ]
                                ui.table(columns=pr_cols, rows=pr_rows, row_key="pid").classes("w-full bg-slate-900")

                        # Top RAM
                        with ui.card().classes("w-full p-4 custom-card"):
                            ui.label("Proses Pemakaian Memori Terbesar").classes("text-sm font-bold text-white mb-2")
                            mem_procs = top_procs.get("mem", []) if isinstance(top_procs, dict) else []
                            if not mem_procs:
                                ui.label("Tidak ada data proses memori.").classes("text-xs text-slate-500")
                            else:
                                mpr_cols = [
                                    {"name": "pid", "label": "PID", "field": "pid", "align": "center"},
                                    {"name": "user", "label": "USER", "field": "user", "align": "left"},
                                    {"name": "mem", "label": "% MEM", "field": "mem", "align": "right"},
                                    {"name": "cmd", "label": "PERINTAH", "field": "cmd", "align": "left"},
                                ]
                                mpr_rows = [
                                    {
                                        "pid": p.get("pid", "—"),
                                        "user": p.get("user", "—"),
                                        "mem": f"{p.get('mem', 0)}%",
                                        "cmd": p.get("command", "—"),
                                    }
                                    for p in mem_procs[:15]
                                ]
                                ui.table(columns=mpr_cols, rows=mpr_rows, row_key="pid").classes("w-full bg-slate-900")

                # -------------------------------------------------------------
                # SUB-TAB 6: PORT JARINGAN LISTENING (SS -TULPN)
                # -------------------------------------------------------------
                with ui.tab_panel(t_port).classes("gap-4 flex flex-col p-0"):
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Port Jaringan Listening (ss -tulpn)").classes("text-sm font-bold text-white mb-2")
                        if not listening_ports:
                            ui.label("Tidak ada data port jaringan yang dilaporkan.").classes("text-xs text-slate-500")
                        else:
                            pt_cols = [
                                {"name": "proto", "label": "PROTOKOL", "field": "proto", "align": "center"},
                                {"name": "ip", "label": "IP LOKAL", "field": "ip", "align": "left"},
                                {"name": "port", "label": "PORT", "field": "port", "align": "center"},
                                {"name": "proc", "label": "PROSES / DAEMON", "field": "proc", "align": "left"},
                                {"name": "pid", "label": "PID", "field": "pid", "align": "center"},
                            ]
                            pt_rows = [
                                {
                                    "proto": str(p.get("proto", "TCP")).upper(),
                                    "ip": p.get("ip", "0.0.0.0"),
                                    "port": p.get("port", "—"),
                                    "proc": p.get("process", "—"),
                                    "pid": p.get("pid", "—"),
                                }
                                for p in listening_ports
                            ]
                            ui.table(columns=pt_cols, rows=pt_rows, row_key="port").classes("w-full bg-slate-900")

                # -------------------------------------------------------------
                # SUB-TAB 7: PENGGUNA SISTEM & SESI AKTIF
                # -------------------------------------------------------------
                with ui.tab_panel(t_sec).classes("gap-4 flex flex-col p-0"):
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Daftar Akun Pengguna Sistem Linux (/etc/passwd)").classes("text-sm font-bold text-white mb-2")
                        if not accounts_data:
                            ui.label("Tidak ada data akun Linux yang dilaporkan.").classes("text-xs text-slate-500")
                        else:
                            acc_cols = [
                                {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                                {"name": "uid", "label": "UID / GID", "field": "uid", "align": "center"},
                                {"name": "home", "label": "HOME DIR", "field": "home", "align": "left"},
                                {"name": "shell", "label": "SHELL", "field": "shell", "align": "left"},
                                {"name": "priv", "label": "HAK AKSES", "field": "priv", "align": "center"},
                            ]
                            acc_rows = [
                                {
                                    "user": a.get("user", "—"),
                                    "uid": f"{a.get('uid', '—')} / {a.get('gid', '—')}",
                                    "home": a.get("home", "—"),
                                    "shell": a.get("shell", "—"),
                                    "priv": "SUDO / ROOT" if a.get("uid") == 0 or "sudo" in a.get("groups", []) else "STANDAR",
                                }
                                for a in accounts_data
                            ]
                            ui.table(columns=acc_cols, rows=acc_rows, row_key="user").classes("w-full bg-slate-900")

                    # Sesi Login Aktif
                    active_sess = []
                    for a in accounts_data:
                        for s in a.get("sessions", []):
                            active_sess.append({
                                "user": a.get("user", "—"),
                                "tty": s.get("tty", s.get("line", "pts/0")),
                                "ip": s.get("ip", s.get("host", "127.0.0.1")),
                                "time": s.get("time", s.get("login_time", "—")),
                            })

                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Sesi Login Aktif (Active Sessions)").classes("text-sm font-bold text-white mb-2")
                        if not active_sess:
                            ui.label("Tidak ada sesi interaktif SSH/TTY yang sedang aktif.").classes("text-xs text-slate-500")
                        else:
                            sess_cols = [
                                {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                                {"name": "tty", "label": "TERMINAL / TTY", "field": "tty", "align": "center"},
                                {"name": "ip", "label": "IP ASAL", "field": "ip", "align": "left"},
                                {"name": "time", "label": "WAKTU LOGIN", "field": "time", "align": "left"},
                            ]
                            ui.table(columns=sess_cols, rows=active_sess, row_key="tty").classes("w-full bg-slate-900")

                # -------------------------------------------------------------
                # SUB-TAB 8: STATUS FIREWALL (UFW / IPTABLES)
                # -------------------------------------------------------------
                with ui.tab_panel(t_fw).classes("gap-4 flex flex-col p-0"):
                    with ui.card().classes("w-full p-4 custom-card"):
                        fw_status = firewall_data.get("status", "unknown") if isinstance(firewall_data, dict) else "unknown"
                        with ui.row().classes("items-center justify-between mb-3"):
                            ui.label("Status Firewall & Aturan Jaringan").classes("text-sm font-bold text-white")
                            ui.badge(f"STATUS: {fw_status.upper()}", color="emerald-9" if fw_status == "active" else "amber-9").classes("text-xs font-bold px-2 py-0.5")

                        fw_rules = firewall_data.get("rules", []) if isinstance(firewall_data, dict) else []
                        if not fw_rules:
                            ui.label("Tidak ada aturan firewall yang dilaporkan (atau firewall nonaktif).").classes("text-xs text-slate-500")
                        else:
                            fw_cols = [
                                {"name": "act", "label": "TINDAKAN", "field": "act", "align": "center"},
                                {"name": "from", "label": "DARI (SUMBER)", "field": "from", "align": "left"},
                                {"name": "to", "label": "KE (TUJUAN)", "field": "to", "align": "left"},
                                {"name": "proto", "label": "PORT / PROTOKOL", "field": "proto", "align": "center"},
                            ]
                            fw_rows = [
                                {
                                    "act": r.get("action", "ALLOW").upper(),
                                    "from": r.get("from", "Anywhere"),
                                    "to": r.get("to", "Anywhere"),
                                    "proto": r.get("port", "—"),
                                }
                                for r in fw_rules
                            ]
                            ui.table(columns=fw_cols, rows=fw_rows, row_key="to").classes("w-full bg-slate-900")

                # -------------------------------------------------------------
                # SUB-TAB 9: TUGAS TERJADWAL CRON & PEWAKTU SYSTEMD
                # -------------------------------------------------------------
                with ui.tab_panel(t_cron).classes("gap-4 flex flex-col p-0"):
                    # Crontab Jobs
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Tugas Terjadwal Crontab (/etc/cron* & crontab -l)").classes("text-sm font-bold text-white mb-2")
                        crons = cron_data.get("crontab", []) if isinstance(cron_data, dict) else []
                        if not crons:
                            ui.label("Tidak ada pekerjaan crontab yang dilaporkan.").classes("text-xs text-slate-500")
                        else:
                            cr_cols = [
                                {"name": "sched", "label": "JADWAL", "field": "sched", "align": "left"},
                                {"name": "user", "label": "USER", "field": "user", "align": "left"},
                                {"name": "cmd", "label": "PERINTAH", "field": "cmd", "align": "left"},
                            ]
                            cr_rows = [
                                {
                                    "sched": c.get("schedule", "—"),
                                    "user": c.get("user", "—"),
                                    "cmd": c.get("command", "—"),
                                }
                                for c in crons
                            ]
                            ui.table(columns=cr_cols, rows=cr_rows, row_key="cmd").classes("w-full bg-slate-900")

                    # Systemd Timers
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Pewaktu Systemd (Systemd Timers)").classes("text-sm font-bold text-white mb-2")
                        timers = cron_data.get("timers", []) if isinstance(cron_data, dict) else []
                        if not timers:
                            ui.label("Tidak ada unit timer systemd aktif yang dilaporkan.").classes("text-xs text-slate-500")
                        else:
                            tm_cols = [
                                {"name": "unit", "label": "NAMA TIMER", "field": "unit", "align": "left"},
                                {"name": "next", "label": "EKSEKUSI BERIKUTNYA", "field": "next", "align": "left"},
                                {"name": "left", "label": "WAKTU TERSISA", "field": "left", "align": "center"},
                                {"name": "last", "label": "EKSEKUSI TERAKHIR", "field": "last", "align": "left"},
                                {"name": "service", "label": "LAYANAN TERKAIT", "field": "service", "align": "left"},
                            ]
                            tm_rows = []
                            for tm in timers:
                                if isinstance(tm, dict):
                                    tm_rows.append({
                                        "unit": tm.get("unit", tm.get("timer", "—")),
                                        "next": tm.get("next", "—"),
                                        "left": tm.get("left", "—"),
                                        "last": tm.get("last", tm.get("passed", "—")),
                                        "service": tm.get("activates", tm.get("service", "—")),
                                    })
                                else:
                                    tm_rows.append({"unit": str(tm), "next": "—", "left": "—", "last": "—", "service": "—"})
                            ui.table(columns=tm_cols, rows=tm_rows, row_key="unit").classes("w-full bg-slate-900")

                # -------------------------------------------------------------
                # SUB-TAB 10: LOG KESALAHAN SISTEM (JOURNALCTL)
                # -------------------------------------------------------------
                with ui.tab_panel(t_log).classes("gap-4 flex flex-col p-0"):
                    with ui.card().classes("w-full p-4 custom-card"):
                        ui.label("Log Kesalahan Sistem (journalctl err/crit)").classes("text-sm font-bold text-white mb-2")
                        if not system_logs:
                            ui.label("Tidak ada catatan kegagalan sistem penting pada jurnal operasi.").classes("text-xs text-emerald-400")
                        else:
                            lg_cols = [
                                {"name": "time", "label": "WAKTU", "field": "time", "align": "left"},
                                {"name": "unit", "label": "UNIT / PROSES", "field": "unit", "align": "left"},
                                {"name": "prio", "label": "PRIORITAS", "field": "prio", "align": "center"},
                                {"name": "msg", "label": "PESAN LOG", "field": "msg", "align": "left"},
                            ]
                            lg_rows = [
                                {
                                    "time": l.get("time", "—"),
                                    "unit": l.get("unit", "kernel"),
                                    "prio": str(l.get("priority", "ERR")).upper(),
                                    "msg": l.get("message", "—"),
                                }
                                for l in system_logs[:30]
                            ]
                            ui.table(columns=lg_cols, rows=lg_rows, row_key="time").classes("w-full bg-slate-900")
