"""
Modul Pusat Operasi Server Detail (Server Operations Center & Sub-Tabs)
======================================================================
Menyediakan inspeksi mendalam terhadap satu node server dengan hero header
kontrol operasional (Reboot, Poweroff, OTA Update), dan 11 sub-tab komprehensif:
1. Performa (Metrik Real-time & Riwayat ECharts utilisasi CPU/RAM/Load)
2. Layanan (+ Tambah Layanan, Start, Stop, Restart, Core toggle, Ignore toggle, Hapus)
3. Insiden & Masalah (Filter keparahan, durasi, dan aksi Tandai Selesai)
4. Paket OS (Upgrade per-paket, Update cache APT, Upgrade seluruh paket)
5. Proses (Top CPU & Top RAM dengan aksi Sinyal Hentikan/Kill SIGTERM/SIGKILL)
6. Port Jaringan (Daftar listening ports & proses aktif ss -tulpn)
7. Pengguna & Sesi (+ Tambah Pengguna Linux, Kunci/Buka, Hapus, Putuskan Sesi)
8. Firewall (+ Blokir IP, + Aturan Port, Buka Blokir, Aktifkan/Matikan/Reload)
9. Cron & Timer (+ Tambah Tugas Cron, Jalankan Sekarang, Toggle, Hapus)
10. SSL/TLS & Cadangan (+ Tambah Path Sertifikat, Hapus Path, Status Cadangan)
11. Log Sistem (Journalctl error logs)
"""

from datetime import datetime
import json
import re
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from config import settings
from models import AuditLog, Command, LogRequest, Metric, Server, ServerExtras, ServerProblem, Service, SystemSnapshot
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
            can_manage = user.is_master_admin() or user.has_perm("can_server_control")

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

            # Ambil data snapshot terbaru, riwayat snapshot (30 terakhir), dan extras
            snap = (
                db.query(SystemSnapshot)
                .filter(SystemSnapshot.server_id == srv_id)
                .order_by(SystemSnapshot.id.desc())
                .first()
            )
            history_snaps = (
                db.query(SystemSnapshot)
                .filter(SystemSnapshot.server_id == srv_id)
                .order_by(SystemSnapshot.id.desc())
                .limit(30)
                .all()
            )
            history_snaps.reverse()

            ext = db.query(ServerExtras).filter(ServerExtras.server_id == srv_id).first()
            services = db.query(Service).filter(Service.server_id == srv_id).all()
            problems = (
                db.query(ServerProblem)
                .filter(ServerProblem.server_id == srv_id)
                .order_by(ServerProblem.started_at.desc())
                .all()
            )

        with render_layout(request, user, active_tab="servers"):
            container = ui.column().classes("w-full max-w-full min-w-0 gap-4")

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

            installed_packages = []
            if ext and ext.installed_packages:
                try:
                    installed_packages = json.loads(ext.installed_packages) if isinstance(ext.installed_packages, str) else ext.installed_packages
                except Exception:
                    pass
            inst_pkg_map = {p.get("name"): p for p in installed_packages if isinstance(p, dict) and p.get("name")}

            ssl_certs = []
            if ext and ext.ssl_certs:
                try:
                    ssl_certs = json.loads(ext.ssl_certs) if isinstance(ext.ssl_certs, str) else ext.ssl_certs
                except Exception:
                    pass

            backup_status = []
            if ext and ext.backup_status:
                try:
                    backup_status = json.loads(ext.backup_status) if isinstance(ext.backup_status, str) else ext.backup_status
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

            # Helper Eksekusi Permintaan APT (via LogRequest)
            def _queue_apt_request(unit_name: str, detail_val: str | None = None, note: str = ""):
                with get_db(session_factory) as db:
                    req = LogRequest(
                        server_id=srv_id,
                        unit=unit_name,
                        detail=detail_val,
                        status="pending",
                    )
                    db.add(req)
                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=srv_id,
                        action=f"apt_{unit_name.lower()}",
                        target=f"{srv_host} ({note})",
                        result="pending",
                    )
                    db.add(audit)
                    db.commit()
                    notify_success(f"Permintaan APT '{unit_name}' ({note}) dikirim ke agen.")

            # ---------------------------------------------------------------------
            # MODAL DIALOGS KONTROL OPERASIONAL
            # ---------------------------------------------------------------------

            # 1. Dialog Kontrol Host (Reboot / Poweroff)
            host_dlg = ui.dialog()
            host_state = {"action": "", "title": "", "msg": "", "color": "primary"}
            with host_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/40"):
                host_title_label = ui.label("").classes("text-base font-bold text-white")
                host_msg_label = ui.label("").classes("text-xs text-slate-300 leading-relaxed")

                def _confirm_host_action():
                    act = host_state["action"]
                    _queue_command(act, note=host_state["title"])
                    host_dlg.close()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=host_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Konfirmasi Eksekusi", icon="check", on_click=_confirm_host_action).props("dense unelevated color=negative no-caps")

            def _open_host_dialog(action: str):
                if action == "reboot_host":
                    host_state["action"] = "reboot_host"
                    host_state["title"] = "Reboot Host OS"
                    host_title_label.set_text("Konfirmasi Reboot Host Server")
                    host_msg_label.set_text(
                        f"Apakah Anda yakin ingin melakukan REBOOT pada server '{srv_host}' ({srv_ip})? "
                        "Seluruh layanan yang berjalan akan dihentikan sementara dan sistem operasi akan dimulai ulang."
                    )
                else:
                    host_state["action"] = "poweroff_host"
                    host_state["title"] = "Poweroff Host OS"
                    host_title_label.set_text("PERINGATAN: Poweroff Host Server")
                    host_msg_label.set_text(
                        f"PERINGATAN KRITIS: Anda akan MEMATIKAN SISTEM OPERASI server '{srv_host}' ({srv_ip}). "
                        "Server akan mati total dan memerlukan akses fisik, saklar daya pintar (PDU), IPMI/iLO/iDRAC, atau kontrol Hypervisor untuk menyala kembali!"
                    )
                host_dlg.open()

            # 2. Dialog Tambah Layanan Terpantau Baru
            add_svc_dlg = ui.dialog()
            with add_svc_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                ui.label("Tambah Layanan Baru Untuk Dipantau").classes("text-base font-bold text-white")
                with ui.column().classes("w-full gap-3"):
                    inp_svc_name = ui.input("Nama Layanan (Systemd)", placeholder="mis. nginx, mariadb, redis-server").classes("w-full").props("dense outlined dark stack-label")
                    inp_svc_port = ui.number("Port Listening", value=80, min=1, max=65535).classes("w-full").props("dense outlined dark stack-label")
                    inp_svc_proc = ui.input("Nama Proses", placeholder="mis. nginx, mysqld, redis-server").classes("w-full").props("dense outlined dark stack-label")
                    cb_svc_core = ui.checkbox("Layanan Utama / Kritis (Core Service)", value=True).props("dense dark")

                def _submit_new_service():
                    s_name = inp_svc_name.value.strip()
                    s_port = int(inp_svc_port.value or 0)
                    s_proc = inp_svc_proc.value.strip()
                    if not s_name or not s_proc:
                        notify_error("Nama layanan dan nama proses wajib diisi.")
                        return
                    with get_db(session_factory) as db:
                        existing = db.query(Service).filter(Service.server_id == srv_id, Service.service_name == s_name).first()
                        if existing:
                            notify_error(f"Layanan '{s_name}' sudah terdaftar pada server ini.")
                            return
                        new_svc = Service(
                            server_id=srv_id,
                            service_name=s_name,
                            port=s_port,
                            process_name=s_proc,
                            is_core=1 if cb_svc_core.value else 0,
                        )
                        db.add(new_svc)
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            server_id=srv_id,
                            action="add_service",
                            target=f"{s_name} ({srv_host})",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                        notify_success(f"Layanan '{s_name}' berhasil ditambahkan ke daftar pemantauan.")
                    add_svc_dlg.close()
                    ui.navigate.to(f"/servers/{srv_id}")

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=add_svc_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Simpan Layanan", icon="check", on_click=_submit_new_service).props("dense unelevated color=primary no-caps")

            # 3. Dialog Hentikan Proses (Kill Process)
            kill_dlg = ui.dialog()
            kill_state = {"pid": None, "proc": "", "user": ""}
            with kill_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/40"):
                ui.label("Hentikan Proses (Kill Process)").classes("text-base font-bold text-white")
                kill_info_label = ui.label("").classes("text-xs text-slate-300 font-mono")
                sel_signal = ui.select({
                    "TERM": "SIGTERM (15) - Penghentian Teratur (Graceful)",
                    "KILL": "SIGKILL (9) - Paksa Berhenti Seketika (Force Kill)",
                }, value="TERM", label="Sinyal Proses").classes("w-full").props("dense outlined dark")

                def _confirm_kill():
                    pid = kill_state["pid"]
                    if not pid:
                        return
                    sig = sel_signal.value
                    _queue_command("kill_process", params={"pid": pid, "signal": sig}, note=f"Kill PID {pid} ({kill_state['proc']})")
                    kill_dlg.close()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=kill_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Kirim Sinyal", icon="cancel", on_click=_confirm_kill).props("dense unelevated color=negative no-caps")

            def _open_kill_dialog(pid: int, proc_name: str, user_name: str):
                kill_state["pid"] = pid
                kill_state["proc"] = proc_name
                kill_state["user"] = user_name
                kill_info_label.set_text(f"Target: PID {pid} · Proses: {proc_name} · Pengguna: {user_name}")
                kill_dlg.open()

            # 4. Dialog Tambah Pengguna Linux Baru
            add_user_dlg = ui.dialog()
            with add_user_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                ui.label("Buat Pengguna Linux Baru").classes("text-base font-bold text-white")
                with ui.column().classes("w-full gap-3"):
                    inp_u_name = ui.input("Nama Pengguna (Username) *", placeholder="mis. sysadmin2").classes("w-full").props("dense outlined dark stack-label")
                    inp_u_pwd = ui.input("Kata Sandi Akun", password=True, password_toggle_button=True, placeholder="Minimal 8 karakter").classes("w-full").props("dense outlined dark stack-label")
                    inp_u_shell = ui.select(["/bin/bash", "/bin/sh", "/bin/zsh", "/usr/sbin/nologin"], value="/bin/bash", label="Default Shell").classes("w-full").props("dense outlined dark stack-label")
                    cb_u_sudo = ui.checkbox("Berikan Hak Akses Sudo (Root/Administrator)").props("dense dark")
                    inp_u_comm = ui.input("Deskripsi / Keterangan", placeholder="Nama Lengkap / Unit Kerja").classes("w-full").props("dense outlined dark stack-label")

                def _submit_new_user():
                    u_name = inp_u_name.value.strip().lower()
                    u_pwd = inp_u_pwd.value.strip()
                    if not u_name:
                        notify_error("Username wajib diisi.")
                        return
                    _queue_command("user_create", params={
                        "username": u_name,
                        "password": u_pwd,
                        "shell": inp_u_shell.value,
                        "is_sudo": 1 if cb_u_sudo.value else 0,
                        "comment": inp_u_comm.value.strip() or "Dibuat via Pantau Server",
                    }, note=f"Buat akun {u_name}")
                    add_user_dlg.close()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=add_user_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Buat Pengguna", icon="person_add", on_click=_submit_new_user).props("dense unelevated color=primary no-caps")

            # 5. Dialog Blokir Alamat IP Firewall
            block_ip_dlg = ui.dialog()
            with block_ip_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                ui.label("Blokir Alamat IP Sumber").classes("text-base font-bold text-white")
                inp_block_ip = ui.input("Alamat IPv4", placeholder="mis. 198.51.100.25").classes("w-full").props("dense outlined dark stack-label")

                def _submit_block_ip():
                    ip_target = inp_block_ip.value.strip()
                    if not ip_target:
                        notify_error("Alamat IP wajib diisi.")
                        return
                    _queue_command("block_ip", params={"ip": ip_target}, note=f"Blokir IP {ip_target}")
                    block_ip_dlg.close()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=block_ip_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Blokir Sekarang", icon="block", on_click=_submit_block_ip).props("dense unelevated color=negative no-caps")

            # 6. Dialog Tambah Tugas Cron
            add_cron_dlg = ui.dialog()
            with add_cron_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4"):
                ui.label("Tambah Tugas Terjadwal (Cron Job)").classes("text-base font-bold text-white")
                with ui.column().classes("w-full gap-3"):
                    inp_c_ident = ui.input("Identitas Tugas (ID) *", placeholder="mis. backup-database").classes("w-full").props("dense outlined dark stack-label")
                    with ui.row().classes("w-full gap-2"):
                        inp_c_min = ui.input("Menit", value="0").classes("flex-1").props("dense outlined dark stack-label")
                        inp_c_hour = ui.input("Jam", value="2").classes("flex-1").props("dense outlined dark stack-label")
                        inp_c_dom = ui.input("Tanggal", value="*").classes("flex-1").props("dense outlined dark stack-label")
                        inp_c_mon = ui.input("Bulan", value="*").classes("flex-1").props("dense outlined dark stack-label")
                        inp_c_dow = ui.input("Hari", value="*").classes("flex-1").props("dense outlined dark stack-label")
                    inp_c_user = ui.input("Eksekusi Sebagai Pengguna", value="root").classes("w-full").props("dense outlined dark stack-label")
                    inp_c_cmd = ui.input("Perintah Shell / Skrip *", placeholder="mis. /opt/scripts/backup.sh").classes("w-full").props("dense outlined dark stack-label")

                def _submit_new_cron():
                    ident = inp_c_ident.value.strip()
                    cmd_str = inp_c_cmd.value.strip()
                    if not ident or not cmd_str:
                        notify_error("Identitas dan perintah tugas wajib diisi.")
                        return
                    _queue_command("cron_add", params={
                        "ident": ident,
                        "minute": inp_c_min.value.strip() or "*",
                        "hour": inp_c_hour.value.strip() or "*",
                        "dom": inp_c_dom.value.strip() or "*",
                        "month": inp_c_mon.value.strip() or "*",
                        "dow": inp_c_dow.value.strip() or "*",
                        "user": inp_c_user.value.strip() or "root",
                        "command": cmd_str,
                    }, note=f"Tambah tugas cron {ident}")
                    add_cron_dlg.close()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=add_cron_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Simpan Tugas", icon="schedule", on_click=_submit_new_cron).props("dense unelevated color=primary no-caps")

            # 7. Dialog Tambah Path Sertifikat SSL
            add_ssl_dlg = ui.dialog()
            with add_ssl_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                ui.label("Tambah Path Sertifikat SSL/TLS").classes("text-base font-bold text-white")
                inp_ssl_path = ui.input("Path Berkas Sertifikat (CRT/PEM)", placeholder="mis. /etc/letsencrypt/live/domain/fullchain.pem").classes("w-full").props("dense outlined dark stack-label")

                def _submit_ssl_path():
                    p = inp_ssl_path.value.strip()
                    if not p:
                        notify_error("Path berkas sertifikat wajib diisi.")
                        return
                    _queue_command("ssl_path_add", params={"path": p}, note=f"Tambah path SSL {p}")
                    add_ssl_dlg.close()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=add_ssl_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Simpan Path", icon="add", on_click=_submit_ssl_path).props("dense unelevated color=primary no-caps")

            # ---------------------------------------------------------------------
            # TAMPILAN UTAMA & HERO HEADER
            # ---------------------------------------------------------------------
            with container:
                now = datetime.utcnow()
                is_online = bool(srv_last_seen and (now - srv_last_seen).total_seconds() < 45)
                tier_label = "PROD" if srv_tier == 1 else "DEV"
                open_problems = [p for p in problems if p.resolved_at is None]
                apt_cnt = ext.apt_upgradable if ext and ext.apt_upgradable is not None else 0

                with ui.card().classes("w-full p-3.5 custom-card"):
                    with ui.row().classes("w-full items-center justify-between gap-4"):
                        with ui.row().classes("items-center gap-3"):
                            ui.button(icon="arrow_back", on_click=lambda: ui.navigate.to("/servers")).props("dense flat round size=sm color=slate-4").tooltip("Kembali ke Daftar Server")
                            ui.icon("dns", size="28px").classes("text-blue-400")
                            with ui.column().classes("gap-0"):
                                with ui.row().classes("items-center gap-2"):
                                    ui.label(srv_host).classes("text-lg font-bold text-white leading-tight")
                                    ui.badge("ONLINE" if is_online else "OFFLINE", color="emerald-9" if is_online else "rose-9").classes("text-[9px] font-bold px-1.5 py-0.5")
                                    ui.badge(tier_label, color="slate-800").classes("text-[9px] font-mono border border-slate-700 px-1.5 py-0.5")
                                    if srv_is_maint:
                                        ui.badge("PEMELIHARAAN", color="amber-9").classes("text-[9px] font-bold px-1.5 py-0.5")
                                ui.label(f"IP: {srv_ip} · Platform: {srv_platform} · Terakhir terlihat: {srv_last_seen.strftime('%d %b %Y %H:%M:%S') if srv_last_seen else '—'}").classes("text-[11px] text-slate-400 font-mono")

                        # Tombol Aksi Hero Header (Kompak NOC)
                        with ui.row().classes("items-center gap-1.5 flex-wrap"):
                            ui.button("Segarkan", icon="refresh", on_click=lambda: ui.navigate.to(f"/servers/{srv_id}")).props("dense outline no-caps size=sm color=slate-4").classes("text-xs")

                            if ext and ext.agent_version and ext.agent_version != settings.APP_VERSION:
                                ui.button(
                                    f"OTA v{settings.APP_VERSION}",
                                    icon="system_update_alt",
                                    on_click=lambda: _queue_command("update_agent", params={"version": settings.APP_VERSION}, note="Enterprise OTA Update"),
                                ).props("dense unelevated no-caps size=sm color=primary").classes("text-xs font-semibold")

                            ui.button("Reboot Host", icon="restart_alt", on_click=lambda: _open_host_dialog("reboot_host")).props("dense outline no-caps size=sm color=amber-4").classes("text-xs")
                            ui.button("Poweroff", icon="power_settings_new", on_click=lambda: _open_host_dialog("poweroff_host")).props("dense outline no-caps size=sm color=rose-4").classes("text-xs")

                            # Dialog Mode Pemeliharaan
                            maint_dlg = ui.dialog()
                            with maint_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4"):
                                ui.label(f"Mode Pemeliharaan: {srv_host}").classes("text-base font-bold text-white")
                                maint_dur = ui.number("Durasi Pemeliharaan (Menit)", value=60, min=5, max=1440).classes("w-full").props("dense outlined dark stack-label")
                                maint_reason = ui.input("Alasan Pemeliharaan", value=srv_maint_reason or "Perawatan rutin server").classes("w-full").props("dense outlined dark stack-label")

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
                                        ui.button("Nonaktifkan Pemeliharaan", on_click=lambda: _toggle_maintenance(False)).props("dense unelevated color=emerald-7 no-caps")
                                    else:
                                        ui.button("Aktifkan Pemeliharaan", on_click=lambda: _toggle_maintenance(True)).props("dense unelevated color=amber-7 no-caps")

                            ui.button("Pemeliharaan", icon="build", on_click=maint_dlg.open).props("dense outline no-caps size=sm color=primary").classes("text-xs")

                # -----------------------------------------------------------------
                # 11 SUB-TAB NAVIGASI DETAIL SERVER
                # -----------------------------------------------------------------
                with ui.tabs().props("dense inline-label outside-arrows mobile-arrows active-color=primary indicator-color=primary align=left").classes("w-full max-w-full min-w-0 bg-slate-900 border-b border-slate-800 text-slate-400") as tabs:
                    t_perf = ui.tab("perf", label="Performa", icon="speed")
                    t_svc = ui.tab("svc", label=f"Layanan ({len(services)})", icon="dns")
                    t_prob = ui.tab("prob", label=f"Insiden ({len(open_problems)})", icon="warning")
                    t_pkg = ui.tab("pkg", label=f"Paket OS ({apt_cnt})", icon="inventory_2")
                    t_proc = ui.tab("proc", label="Proses", icon="memory")
                    t_port = ui.tab("port", label="Port Jaringan", icon="lan")
                    t_user = ui.tab("user", label="Pengguna & Sesi", icon="people")
                    t_fw = ui.tab("fw", label="Firewall", icon="security")
                    t_cron = ui.tab("cron", label="Cron & Timer", icon="schedule")
                    t_ssl = ui.tab("ssl", label=f"SSL & Cadangan ({len(ssl_certs)})", icon="lock")
                    t_log = ui.tab("log", label="Log Sistem", icon="receipt_long")

                tab_map = {
                    "perf": t_perf, "performa": t_perf,
                    "svc": t_svc, "layanan": t_svc, "services": t_svc,
                    "prob": t_prob, "insiden": t_prob, "problems": t_prob,
                    "pkg": t_pkg, "paket": t_pkg, "packages": t_pkg,
                    "proc": t_proc, "proses": t_proc, "processes": t_proc,
                    "port": t_port, "ports": t_port, "jaringan": t_port,
                    "user": t_user, "users": t_user, "pengguna": t_user, "akun": t_user,
                    "fw": t_fw, "firewall": t_fw,
                    "cron": t_cron, "timer": t_cron,
                    "ssl": t_ssl, "cadangan": t_ssl,
                    "log": t_log, "logs": t_log,
                }
                req_tab = request.query_params.get("tab", "").lower()
                init_tab = tab_map.get(req_tab, t_perf)

                with ui.tab_panels(tabs, value=init_tab).classes("w-full bg-transparent p-0"):

                    # =============================================================
                    # SUB-TAB 1: PERFORMA (METRIK & GRAFIK TREN ECHARTS)
                    # =============================================================
                    with ui.tab_panel(t_perf).classes("gap-4 flex flex-col p-0"):
                        # 4 Kartu Metrik Ringkas
                        with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"):
                            # CPU
                            with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                                ui.label("Penggunaan CPU").classes("text-xs text-slate-400 font-medium")
                                cpu_val = f"{snap.cpu:.1f}%" if snap and snap.cpu is not None else "—"
                                ui.label(cpu_val).classes("text-2xl font-bold text-sky-400")
                                cpu_pct = (snap.cpu / 100.0) if snap and snap.cpu is not None else 0.0
                                ui.linear_progress(value=cpu_pct, color="primary", show_value=False).classes("w-full h-1.5 rounded")

                            # RAM
                            with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                                ui.label("Penggunaan Memori (RAM)").classes("text-xs text-slate-400 font-medium")
                                ram_str = "—"
                                ram_pct = 0.0
                                if snap and snap.mem_total:
                                    used_gb = snap.mem_used / (1024**3)
                                    tot_gb = snap.mem_total / (1024**3)
                                    ram_pct = snap.mem_used / snap.mem_total
                                    ram_str = f"{used_gb:.1f} GB / {tot_gb:.1f} GB ({ram_pct*100:.1f}%)"
                                ui.label(ram_str).classes("text-base font-bold text-emerald-400")
                                ui.linear_progress(value=ram_pct, color="positive", show_value=False).classes("w-full h-1.5 rounded")

                            # Load Average
                            with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                                ui.label("Beban Rata-Rata (1 / 5 / 15m)").classes("text-xs text-slate-400 font-medium")
                                load_str = f"{snap.load1:.2f} / {snap.load5:.2f} / {snap.load15:.2f}" if snap and snap.load1 is not None else "—"
                                ui.label(load_str).classes("text-lg font-bold text-amber-400")

                            # Swap
                            with ui.card().classes("p-4 custom-card flex flex-col gap-1"):
                                ui.label("Memori Virtual (Swap)").classes("text-xs text-slate-400 font-medium")
                                swap_str = "—"
                                swap_pct = 0.0
                                if snap and snap.swap_total and snap.swap_total > 0:
                                    s_used_gb = snap.swap_used / (1024**3)
                                    s_tot_gb = snap.swap_total / (1024**3)
                                    swap_pct = snap.swap_used / snap.swap_total
                                    swap_str = f"{s_used_gb:.1f} GB / {s_tot_gb:.1f} GB ({swap_pct*100:.1f}%)"
                                else:
                                    swap_str = "0 GB (Nonaktif)"
                                ui.label(swap_str).classes("text-base font-bold text-purple-400")
                                ui.linear_progress(value=swap_pct, color="purple", show_value=False).classes("w-full h-1.5 rounded")

                        # Riwayat Kinerja ECharts (CPU, RAM, Load)
                        with ui.card().classes("w-full p-4 custom-card flex flex-col gap-2"):
                            with ui.row().classes("w-full items-center justify-between"):
                                with ui.column().classes("gap-0"):
                                    ui.label("Riwayat Kinerja (Historical Performance Trends)").classes("text-sm font-bold text-white")
                                    ui.label("Grafik utilisasi CPU, Memori RAM, dan Beban Sistem pada 30 snapshot terakhir").classes("text-xs text-slate-400")

                            if history_snaps:
                                t_labels = [s.timestamp.strftime("%H:%M:%S") if s.timestamp else "—" for s in history_snaps]
                                c_data = [round(s.cpu, 1) if s.cpu is not None else 0 for s in history_snaps]
                                m_data = [round((s.mem_used / s.mem_total * 100), 1) if (s.mem_used and s.mem_total) else 0 for s in history_snaps]
                                l_data = [round(s.load1, 2) if s.load1 is not None else 0 for s in history_snaps]

                                echart_opts = {
                                    "backgroundColor": "transparent",
                                    "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
                                    "legend": {"top": 0, "right": "4%", "data": ["CPU (%)", "RAM (%)", "Load 1m"], "textStyle": {"color": "#94a3b8", "fontSize": 11}},
                                    "grid": {"left": "3%", "right": "3%", "bottom": 36, "top": 38, "containLabel": True},
                                    "xAxis": {
                                        "type": "category",
                                        "data": t_labels,
                                        "axisLine": {"lineStyle": {"color": "#334155"}},
                                        "axisLabel": {"color": "#64748b", "fontSize": 10},
                                    },
                                    "yAxis": [
                                        {
                                            "type": "value",
                                            "max": 100,
                                            "name": "Persen (%)",
                                            "axisLine": {"lineStyle": {"color": "#334155"}},
                                            "splitLine": {"lineStyle": {"color": "#1e293b"}},
                                            "axisLabel": {"color": "#64748b", "fontSize": 10},
                                        },
                                        {
                                            "type": "value",
                                            "name": "Beban (Load)",
                                            "axisLine": {"lineStyle": {"color": "#334155"}},
                                            "splitLine": {"show": False},
                                            "axisLabel": {"color": "#64748b", "fontSize": 10},
                                        },
                                    ],
                                    "series": [
                                        {"name": "CPU (%)", "type": "line", "smooth": True, "data": c_data, "color": "#38bdf8", "areaStyle": {"opacity": 0.15}},
                                        {"name": "RAM (%)", "type": "line", "smooth": True, "data": m_data, "color": "#34d399", "areaStyle": {"opacity": 0.15}},
                                        {"name": "Load 1m", "type": "line", "smooth": True, "yAxisIndex": 1, "data": l_data, "color": "#fbbf24"},
                                    ],
                                }
                                ui.echart(echart_opts).classes("w-full h-64")
                            else:
                                ui.label("Belum ada data riwayat snapshot performa untuk server ini.").classes("text-xs text-slate-500 py-4")

                        # Tabel Media Penyimpanan & Partisi Disk
                        with ui.card().classes("w-full p-4 custom-card"):
                            ui.label("Partisi Media Penyimpanan (Disks)").classes("text-sm font-bold text-white mb-2")
                            if not disks_data:
                                ui.label("Data partisi disk belum tersedia.").classes("text-xs text-slate-500")
                            else:
                                disk_cols = [
                                    {"name": "mount", "label": "TITIK MOUNT", "field": "mount", "align": "left"},
                                    {"name": "dev", "label": "PERANGKAT", "field": "dev", "align": "left"},
                                    {"name": "fs", "label": "SISTEM BERKAS", "field": "fs", "align": "center"},
                                    {"name": "used", "label": "TERPAKAI", "field": "used", "align": "left"},
                                    {"name": "total", "label": "TOTAL", "field": "total", "align": "left"},
                                    {"name": "pct", "label": "PERSENTASE", "field": "pct_num", "align": "center"},
                                ]
                                disk_rows = []
                                for d in disks_data:
                                    pct_val = float(d.get("pct", 0))
                                    disk_rows.append({
                                        "mount": d.get("mount", "—"),
                                        "dev": d.get("dev") or d.get("device") or ("rootfs" if d.get("mount") == "/" else d.get("mount", "—")),
                                        "fs": d.get("type") or d.get("fs", "—"),
                                        "used": format_bytes(d.get("used", 0)),
                                        "total": format_bytes(d.get("total", 0)),
                                        "pct_num": pct_val,
                                    })
                                dtbl = ui.table(columns=disk_cols, rows=disk_rows, row_key="mount").classes("w-full bg-slate-900")
                                dtbl.add_slot("body-cell-pct", """
                                    <q-td :props="props">
                                        <div class="flex items-center gap-1.5 justify-center">
                                            <span class="font-mono text-[11px] w-9 text-slate-200">{{ props.row.pct_num.toFixed(1) }}%</span>
                                            <div class="meter-mini-track">
                                                <div class="meter-mini-bar" :class="props.row.pct_num < 70 ? 'green' : (props.row.pct_num < 90 ? 'yellow' : 'red')" :style="'width:' + Math.min(props.row.pct_num, 100) + '%'"></div>
                                            </div>
                                        </div>
                                    </q-td>
                                """)

                    # =============================================================
                    # SUB-TAB 2: DAFTAR LAYANAN TERPANTAU
                    # =============================================================
                    with ui.tab_panel(t_svc).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            with ui.row().classes("w-full items-center justify-between mb-3"):
                                with ui.column().classes("gap-0"):
                                    ui.label("Daftar Layanan Terpantau").classes("text-sm font-bold text-white")
                                    ui.label("Kontrol status layanan systemd, restart daemon, dan ubah aturan pemantauan").classes("text-xs text-slate-400")

                                with ui.row().classes("items-center gap-2"):
                                    ui.button("Tambah Layanan", icon="add", on_click=add_svc_dlg.open).props("dense unelevated size=sm color=primary no-caps").classes("text-xs font-semibold")
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
                                            <q-btn dense flat round size="xs" color="emerald-4" icon="play_arrow"
                                                   @click="() => $parent.$emit('start_svc', props.row.id)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Start Layanan</q-tooltip>
                                            </q-btn>
                                            <q-btn dense flat round size="xs" color="rose-4" icon="stop"
                                                   @click="() => $parent.$emit('stop_svc', props.row.id)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Stop Layanan</q-tooltip>
                                            </q-btn>
                                            <q-btn dense flat round size="xs" color="amber-4" icon="restart_alt"
                                                   @click="() => $parent.$emit('restart_svc', props.row.id)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Restart Layanan</q-tooltip>
                                            </q-btn>
                                            <q-btn dense flat round size="xs" :icon="props.row.is_core ? 'star' : 'star_border'" color="blue-4"
                                                   @click="() => $parent.$emit('toggle_core', props.row.id)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Ubah Prioritas (Core/Secondary)</q-tooltip>
                                            </q-btn>
                                            <q-btn dense flat round size="xs" :icon="props.row.is_ignored ? 'visibility' : 'visibility_off'" color="slate-4"
                                                   @click="() => $parent.$emit('toggle_ignore', props.row.id)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">{{ props.row.is_ignored ? 'Pantau Kembali' : 'Abaikan Masalah' }}</q-tooltip>
                                            </q-btn>
                                            <q-btn dense flat round size="xs" icon="delete" color="rose-5"
                                                   @click="() => $parent.$emit('delete_svc', props.row.id)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Hapus Dari Pemantauan</q-tooltip>
                                            </q-btn>
                                        </div>
                                    </q-td>
                                """)

                                def _delete_svc(svc_id: int):
                                    with get_db(session_factory) as db:
                                        s = db.query(Service).filter(Service.id == svc_id).first()
                                        if s:
                                            db.delete(s)
                                            db.commit()
                                            notify_success("Layanan berhasil dihapus dari pemantauan.")
                                    ui.navigate.to(f"/servers/{srv_id}")

                                def _toggle_ignore(svc_id: int):
                                    with get_db(session_factory) as db:
                                        s = db.query(Service).filter(Service.id == svc_id).first()
                                        if s:
                                            s.is_ignored = 0 if s.is_ignored else 1
                                            db.commit()
                                            notify_info(f"Status pengabaian layanan {s.service_name} diperbarui.")
                                    ui.navigate.to(f"/servers/{srv_id}")

                                stbl.on("start_svc", lambda e: _queue_command("start", service_id=e.args, note="Start layanan"))
                                stbl.on("stop_svc", lambda e: _queue_command("stop", service_id=e.args, note="Stop layanan"))
                                stbl.on("restart_svc", lambda e: _queue_command("restart", service_id=e.args, note="Restart layanan"))
                                stbl.on("toggle_core", lambda e: _toggle_core(e.args))
                                stbl.on("toggle_ignore", lambda e: _toggle_ignore(e.args))
                                stbl.on("delete_svc", lambda e: _delete_svc(e.args))

                                def _toggle_core(svc_id: int):
                                    with get_db(session_factory) as db:
                                        s = db.query(Service).filter(Service.id == svc_id).first()
                                        if s:
                                            s.is_core = 0 if s.is_core else 1
                                            db.commit()
                                            notify_info(f"Prioritas layanan {s.service_name} diubah.")
                                    ui.navigate.to(f"/servers/{srv_id}")

                    # =============================================================
                    # SUB-TAB 3: RIWAYAT INSIDEN & GANGGUAN SERVER
                    # =============================================================
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

                    # =============================================================
                    # SUB-TAB 4: INVENTARIS PAKET & PEMBARUAN APT
                    # =============================================================
                    with ui.tab_panel(t_pkg).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            with ui.row().classes("w-full items-center justify-between mb-3"):
                                with ui.column().classes("gap-0"):
                                    ui.label("Inventaris Paket & Pembaruan APT").classes("text-sm font-bold text-white")
                                    last_up = ext.apt_last_update.strftime("%Y-%m-%d %H:%M:%S") if ext and ext.apt_last_update else "—"
                                    ui.label(f"Status: {apt_cnt} paket dapat di-upgrade · Pembaruan cache terakhir: {last_up}").classes("text-xs text-slate-400")

                                with ui.row().classes("items-center gap-2"):
                                    ui.button("Perbarui Cache APT", icon="sync", on_click=lambda: _queue_apt_request("APT_UPDATE", note="apt-get update")).props("dense outline no-caps size=sm color=primary").classes("text-xs")
                                    ui.button("Upgrade Seluruh Paket", icon="system_update_alt", on_click=lambda: _queue_apt_request("APT_UPGRADE", note="apt-get upgrade -y")).props("dense unelevated no-caps size=sm color=emerald-8").classes("text-xs")

                            if not apt_packages:
                                ui.label("Seluruh repositori dan paket sistem telah mutakhir (Up to Date).").classes("text-xs text-emerald-400")
                            else:
                                pkg_cols = [
                                    {"name": "pkg", "label": "NAMA PAKET", "field": "pkg", "align": "left"},
                                    {"name": "cur", "label": "VERSI SAAT INI", "field": "cur", "align": "left"},
                                    {"name": "new", "label": "VERSI BARU", "field": "new", "align": "left"},
                                    {"name": "arch", "label": "ARSITEKTUR", "field": "arch", "align": "center"},
                                    {"name": "actions", "label": "AKSI", "field": "actions", "align": "center"},
                                ]
                                pkg_rows = []
                                for itm in apt_packages:
                                    if isinstance(itm, dict):
                                        pkg_name = itm.get("name", "—")
                                        inst_info = inst_pkg_map.get(pkg_name, {})
                                        cur_ver = itm.get("current_version") or inst_info.get("version") or "—"
                                        new_ver = itm.get("new_version") or itm.get("version") or "Tersedia"
                                        arch_val = itm.get("arch") or inst_info.get("arch") or "amd64"
                                        pkg_rows.append({
                                            "pkg": pkg_name,
                                            "cur": cur_ver,
                                            "new": new_ver,
                                            "arch": arch_val,
                                        })
                                    else:
                                        p_str = str(itm)
                                        inst_info = inst_pkg_map.get(p_str, {})
                                        pkg_rows.append({
                                            "pkg": p_str,
                                            "cur": inst_info.get("version") or "—",
                                            "new": "Tersedia",
                                            "arch": inst_info.get("arch") or "amd64"
                                        })

                                pk_tbl = ui.table(columns=pkg_cols, rows=pkg_rows, row_key="pkg").classes("w-full bg-slate-900")
                                pk_tbl.add_slot("body-cell-actions", """
                                    <q-td :props="props">
                                        <q-btn dense outline size="xs" color="emerald-4" icon="upgrade" label="Upgrade" no-caps
                                               @click="() => $parent.$emit('upgrade_pkg', props.row.pkg)">
                                            <q-tooltip class="bg-slate-900 text-[10px]">Upgrade paket ini saja</q-tooltip>
                                        </q-btn>
                                    </q-td>
                                """)
                                pk_tbl.on("upgrade_pkg", lambda e: _queue_apt_request("PKG_UPGRADE", detail_val=e.args, note=f"Upgrade paket {e.args}"))

                    # =============================================================
                    # SUB-TAB 5: PROSES SISTEM TERATAS (TOP PROCESSES)
                    # =============================================================
                    with ui.tab_panel(t_proc).classes("gap-4 flex flex-col p-0"):
                        with ui.row().classes("w-full grid grid-cols-1 lg:grid-cols-2 gap-4"):
                            # Top CPU
                            with ui.card().classes("w-full p-4 custom-card"):
                                ui.label("Proses Pemakaian CPU Terbesar").classes("text-sm font-bold text-white mb-2")
                                cpu_procs = top_procs.get("cpu", []) if isinstance(top_procs, dict) else []
                                if not cpu_procs:
                                    ui.label("Tidak ada data proses CPU.").classes("text-xs text-slate-500")
                                else:
                                    cp_cols = [
                                        {"name": "pid", "label": "PID", "field": "pid", "align": "center"},
                                        {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                                        {"name": "cpu", "label": "CPU %", "field": "cpu", "align": "center"},
                                        {"name": "cmd", "label": "PERINTAH / PROSES", "field": "cmd", "align": "left"},
                                        {"name": "actions", "label": "AKSI", "field": "actions", "align": "center"},
                                    ]
                                    cp_rows = []
                                    for pr in cpu_procs:
                                        cp_rows.append({
                                            "pid": pr.get("pid", "—"),
                                            "user": pr.get("user", "—"),
                                            "cpu": f"{pr.get('cpu', 0)}%",
                                            "cmd": pr.get("comm") or pr.get("cmd") or pr.get("name") or "—",
                                        })
                                    cp_tbl = ui.table(columns=cp_cols, rows=cp_rows, row_key="pid").classes("w-full bg-slate-900")
                                    cp_tbl.add_slot("body-cell-actions", """
                                        <q-td :props="props">
                                            <q-btn dense flat round size="xs" color="rose-4" icon="cancel"
                                                   @click="() => $parent.$emit('kill_proc', props.row)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Hentikan Proses (Kill)</q-tooltip>
                                            </q-btn>
                                        </q-td>
                                    """)
                                    cp_tbl.on("kill_proc", lambda e: _open_kill_dialog(int(e.args["pid"]), e.args["cmd"], e.args["user"]))

                            # Top Mem
                            with ui.card().classes("w-full p-4 custom-card"):
                                ui.label("Proses Pemakaian Memori Terbesar").classes("text-sm font-bold text-white mb-2")
                                mem_procs = top_procs.get("mem", []) if isinstance(top_procs, dict) else []
                                if not mem_procs:
                                    ui.label("Tidak ada data proses Memori.").classes("text-xs text-slate-500")
                                else:
                                    mp_cols = [
                                        {"name": "pid", "label": "PID", "field": "pid", "align": "center"},
                                        {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                                        {"name": "mem", "label": "MEM %", "field": "mem", "align": "center"},
                                        {"name": "cmd", "label": "PERINTAH / PROSES", "field": "cmd", "align": "left"},
                                        {"name": "actions", "label": "AKSI", "field": "actions", "align": "center"},
                                    ]
                                    mp_rows = []
                                    for pr in mem_procs:
                                        mp_rows.append({
                                            "pid": pr.get("pid", "—"),
                                            "user": pr.get("user", "—"),
                                            "mem": f"{pr.get('mem', 0)}%",
                                            "cmd": pr.get("comm") or pr.get("cmd") or pr.get("name") or "—",
                                        })
                                    mp_tbl = ui.table(columns=mp_cols, rows=mp_rows, row_key="pid").classes("w-full bg-slate-900")
                                    mp_tbl.add_slot("body-cell-actions", """
                                        <q-td :props="props">
                                            <q-btn dense flat round size="xs" color="rose-4" icon="cancel"
                                                   @click="() => $parent.$emit('kill_proc', props.row)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Hentikan Proses (Kill)</q-tooltip>
                                            </q-btn>
                                        </q-td>
                                    """)
                                    mp_tbl.on("kill_proc", lambda e: _open_kill_dialog(int(e.args["pid"]), e.args["cmd"], e.args["user"]))

                    # =============================================================
                    # SUB-TAB 6: PORT JARINGAN TERBUKA (LISTENING PORTS)
                    # =============================================================
                    with ui.tab_panel(t_port).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            ui.label("Port Jaringan Listening (ss -tulpn)").classes("text-sm font-bold text-white mb-2")
                            if not listening_ports:
                                ui.label("Data port listening belum dilaporkan oleh agen.").classes("text-xs text-slate-500")
                            else:
                                port_cols = [
                                    {"name": "proto", "label": "PROTO", "field": "proto", "align": "center"},
                                    {"name": "port", "label": "PORT", "field": "port", "align": "center"},
                                    {"name": "addr", "label": "ALAMAT BIND", "field": "addr", "align": "left"},
                                    {"name": "proc", "label": "PROSES / DAEMON", "field": "proc", "align": "left"},
                                    {"name": "pid", "label": "PID", "field": "pid", "align": "center"},
                                ]
                                port_rows = []
                                for p in listening_ports:
                                    port_rows.append({
                                        "proto": p.get("proto", "—").upper(),
                                        "port": p.get("port", "—"),
                                        "addr": p.get("address", p.get("ip", "—")),
                                        "proc": p.get("pname") or p.get("proc") or p.get("process") or "—",
                                        "pid": p.get("pid", "—"),
                                    })
                                ui.table(columns=port_cols, rows=port_rows, row_key="port").classes("w-full bg-slate-900")

                    # =============================================================
                    # SUB-TAB 7: PENGGUNA LINUX & SESI AKTIF
                    # =============================================================
                    with ui.tab_panel(t_user).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            with ui.row().classes("w-full items-center justify-between mb-3"):
                                with ui.column().classes("gap-0"):
                                    ui.label("Pengguna Sistem Linux & Sesi Terminal Aktif").classes("text-sm font-bold text-white")
                                    ui.label("Manajemen akun login sistem operasi dan kontrol pemutusan sesi SSH/TTY").classes("text-xs text-slate-400")

                                ui.button("Buat Pengguna Baru", icon="person_add", on_click=add_user_dlg.open).props("dense unelevated size=sm color=primary no-caps").classes("text-xs font-semibold")

                            # Sesi Terminal Aktif
                            active_sessions = []
                            for acc in accounts_data:
                                sess_list = acc.get("sessions", [])
                                for ses in sess_list:
                                    active_sessions.append({
                                        "user": acc.get("user", "—"),
                                        "tty": ses.get("tty", ses.get("line", "—")),
                                        "from": ses.get("from", ses.get("host", "Lokal")),
                                        "login_at": ses.get("time", ses.get("login_time", "—")),
                                    })

                            if active_sessions:
                                ui.label("Sesi Terminal Aktif (SSH / Console):").classes("text-xs font-bold text-amber-400 mt-2")
                                ses_cols = [
                                    {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                                    {"name": "tty", "label": "TERMINAL / TTY", "field": "tty", "align": "center"},
                                    {"name": "from", "label": "DARI IP / HOST", "field": "from", "align": "left"},
                                    {"name": "login_at", "label": "WAKTU LOGIN", "field": "login_at", "align": "left"},
                                    {"name": "actions", "label": "AKSI", "field": "actions", "align": "center"},
                                ]
                                ses_tbl = ui.table(columns=ses_cols, rows=active_sessions, row_key="tty").classes("w-full bg-slate-900 mb-4")
                                ses_tbl.add_slot("body-cell-actions", """
                                    <q-td :props="props">
                                        <q-btn dense outline size="xs" color="rose-4" icon="logout" label="Putuskan Sesi" no-caps
                                               @click="() => $parent.$emit('terminate_session', props.row.tty)" />
                                    </q-td>
                                """)
                                ses_tbl.on("terminate_session", lambda e: _queue_command("terminate_session", params={"tty": e.args}, note=f"Putuskan sesi {e.args}"))

                            # Daftar Akun Pengguna
                            ui.label("Daftar Akun Pengguna Terdaftar:").classes("text-xs font-bold text-slate-300")
                            acc_cols = [
                                {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                                {"name": "uid", "label": "UID:GID", "field": "uid", "align": "center"},
                                {"name": "shell", "label": "DEFAULT SHELL", "field": "shell", "align": "left"},
                                {"name": "home", "label": "HOME DIR", "field": "home", "align": "left"},
                                {"name": "last_login", "label": "LOGIN TERAKHIR", "field": "last_login", "align": "left"},
                                {"name": "actions", "label": "AKSI", "field": "actions", "align": "center"},
                            ]
                            acc_rows = []
                            for ac in accounts_data:
                                acc_rows.append({
                                    "user": ac.get("user", "—"),
                                    "uid": f"{ac.get('uid', '—')}:{ac.get('gid', '—')}",
                                    "shell": ac.get("shell", "—"),
                                    "home": ac.get("home", "—"),
                                    "last_login": ac.get("last_login", "—"),
                                })
                            acc_tbl = ui.table(columns=acc_cols, rows=acc_rows, row_key="user").classes("w-full bg-slate-900")
                            acc_tbl.add_slot("body-cell-actions", """
                                <q-td :props="props">
                                    <div class="row items-center justify-center gap-1">
                                        <q-btn dense flat round size="xs" color="amber-4" icon="lock"
                                               @click="() => $parent.$emit('lock_user', props.row.user)">
                                            <q-tooltip class="bg-slate-900 text-[10px]">Kunci Akun</q-tooltip>
                                        </q-btn>
                                        <q-btn dense flat round size="xs" color="emerald-4" icon="lock_open"
                                               @click="() => $parent.$emit('unlock_user', props.row.user)">
                                            <q-tooltip class="bg-slate-900 text-[10px]">Buka Kunci Akun</q-tooltip>
                                        </q-btn>
                                        <q-btn dense flat round size="xs" color="rose-4" icon="delete"
                                               @click="() => $parent.$emit('del_user', props.row.user)">
                                            <q-tooltip class="bg-slate-900 text-[10px]">Hapus Akun Pengguna</q-tooltip>
                                        </q-btn>
                                    </div>
                                </q-td>
                            """)
                            acc_tbl.on("lock_user", lambda e: _queue_command("user_lock", params={"username": e.args}, note=f"Kunci akun {e.args}"))
                            acc_tbl.on("unlock_user", lambda e: _queue_command("user_unlock", params={"username": e.args}, note=f"Buka kunci akun {e.args}"))
                            acc_tbl.on("del_user", lambda e: _queue_command("user_delete", params={"username": e.args, "remove_home": 1}, note=f"Hapus akun {e.args}"))

                    # =============================================================
                    # SUB-TAB 8: FIREWALL SISTEM (UFW & IPTABLES)
                    # =============================================================
                    with ui.tab_panel(t_fw).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            with ui.row().classes("w-full items-center justify-between mb-3"):
                                with ui.column().classes("gap-0"):
                                    ui.label("Pengaturan Firewall Sistem (UFW / iptables)").classes("text-sm font-bold text-white")
                                    fw_status = firewall_data.get("status", "unknown").upper()
                                    ui.label(f"Status Firewall: {fw_status}").classes("text-xs text-slate-400")

                                with ui.row().classes("items-center gap-2"):
                                    ui.button("Blokir Alamat IP", icon="block", on_click=block_ip_dlg.open).props("dense unelevated size=sm color=negative no-caps").classes("text-xs")
                                    ui.button("Aktifkan", icon="power", on_click=lambda: _queue_command("firewall_enable", note="Aktifkan UFW")).props("dense outline size=sm color=positive no-caps").classes("text-xs")
                                    ui.button("Matikan", icon="power_off", on_click=lambda: _queue_command("firewall_disable", note="Matikan UFW")).props("dense outline size=sm color=warning no-caps").classes("text-xs")
                                    ui.button("Muat Ulang", icon="refresh", on_click=lambda: _queue_command("firewall_reload", note="Reload UFW")).props("dense outline size=sm color=slate-4 no-caps").classes("text-xs")

                            # Aturan Firewall
                            fw_rules = firewall_data.get("rules", [])
                            if not fw_rules:
                                ui.label("Belum ada aturan khusus firewall yang terdeteksi.").classes("text-xs text-slate-500")
                            else:
                                f_cols = [
                                    {"name": "to", "label": "TUJUAN (PORT/SERVICE)", "field": "to", "align": "left"},
                                    {"name": "action", "label": "TINDAKAN (ACTION)", "field": "action", "align": "center"},
                                    {"name": "from", "label": "DARI SUMBER (FROM)", "field": "from", "align": "left"},
                                    {"name": "actions", "label": "AKSI", "field": "actions", "align": "center"},
                                ]
                                f_rows = []
                                for r in fw_rules:
                                    f_rows.append({
                                        "to": r.get("to", "—"),
                                        "action": r.get("action", "—").upper(),
                                        "from": r.get("from", "Anywhere"),
                                    })
                                f_tbl = ui.table(columns=f_cols, rows=f_rows, row_key="to").classes("w-full bg-slate-900")
                                f_tbl.add_slot("body-cell-actions", """
                                    <q-td :props="props">
                                        <q-btn v-if="props.row.action.includes('DENY') || props.row.action.includes('DROP')"
                                               dense outline size="xs" color="emerald-4" icon="lock_open" label="Buka Blokir" no-caps
                                               @click="() => $parent.$emit('unblock_ip', props.row.from)" />
                                    </q-td>
                                """)
                                f_tbl.on("unblock_ip", lambda e: _queue_command("unblock_ip", params={"ip": e.args}, note=f"Buka blokir IP {e.args}"))

                    # =============================================================
                    # SUB-TAB 9: TUGAS TERJADWAL CRON & SYSTEMD TIMERS
                    # =============================================================
                    with ui.tab_panel(t_cron).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            with ui.row().classes("w-full items-center justify-between mb-3"):
                                with ui.column().classes("gap-0"):
                                    ui.label("Tugas Terjadwal (Cron & Systemd Timers)").classes("text-sm font-bold text-white")
                                    ui.label("Manajemen penjadwalan otomatisasi dan pemeliharaan rutin node").classes("text-xs text-slate-400")

                                ui.button("Tambah Tugas Cron", icon="add", on_click=add_cron_dlg.open).props("dense unelevated size=sm color=primary no-caps").classes("text-xs font-semibold")

                            # Crontab Jobs
                            crons = cron_data.get("jobs", cron_data.get("crontab", [])) if isinstance(cron_data, dict) else []
                            if not crons:
                                ui.label("Tidak ada tugas crontab terdaftar.").classes("text-xs text-slate-500 mb-4")
                            else:
                                ui.label("Tugas Crontab:").classes("text-xs font-bold text-slate-300 mb-1")
                                c_cols = [
                                    {"name": "sched", "label": "JADWAL (M H DoM M DoW)", "field": "sched", "align": "center"},
                                    {"name": "user", "label": "PENGGUNA", "field": "user", "align": "left"},
                                    {"name": "cmd", "label": "PERINTAH SKRIP", "field": "cmd", "align": "left"},
                                    {"name": "actions", "label": "KONTROL AKSI", "field": "actions", "align": "center"},
                                ]
                                c_rows = []
                                for idx, c in enumerate(crons):
                                    sched_str = c.get("schedule") or f"{c.get('minute','*')} {c.get('hour','*')} {c.get('dom','*')} {c.get('month','*')} {c.get('dow','*')}"
                                    c_rows.append({
                                        "id": idx,
                                        "sched": sched_str,
                                        "user": c.get("user", "root"),
                                        "cmd": c.get("command", c.get("cmd", "—")),
                                        "ident": c.get("ident") or f"job-{idx}",
                                    })
                                c_tbl = ui.table(columns=c_cols, rows=c_rows, row_key="id").classes("w-full bg-slate-900 mb-6")
                                c_tbl.add_slot("body-cell-actions", """
                                    <q-td :props="props">
                                        <div class="row items-center justify-center gap-1">
                                            <q-btn dense outline size="xs" color="emerald-4" icon="play_arrow" label="Jalankan" no-caps
                                                   @click="() => $parent.$emit('run_cron', props.row)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Jalankan sekarang di background</q-tooltip>
                                            </q-btn>
                                            <q-btn dense flat round size="xs" color="rose-4" icon="delete"
                                                   @click="() => $parent.$emit('del_cron', props.row.ident)">
                                                <q-tooltip class="bg-slate-900 text-[10px]">Hapus tugas cron</q-tooltip>
                                            </q-btn>
                                        </div>
                                    </q-td>
                                """)
                                c_tbl.on("run_cron", lambda e: _queue_command("cron_run_now", params={"user": e.args["user"], "command": e.args["cmd"]}, note=f"Jalankan cron {e.args['cmd']}"))
                                c_tbl.on("del_cron", lambda e: _queue_command("cron_delete", params={"ident": e.args}, note=f"Hapus cron {e.args}"))

                            # Systemd Timers
                            timers = cron_data.get("timers", cron_data.get("systemd_timers", [])) if isinstance(cron_data, dict) else []
                            if timers:
                                ui.label("Systemd Timers:").classes("text-xs font-bold text-slate-300 mb-1")
                                t_cols = [
                                    {"name": "unit", "label": "NAMA TIMER UNIT", "field": "unit", "align": "left"},
                                    {"name": "next", "label": "EKSEKUSI BERIKUTNYA", "field": "next", "align": "left"},
                                    {"name": "last", "label": "EKSEKUSI TERAKHIR", "field": "last", "align": "left"},
                                    {"name": "activates", "label": "TARGET SERVICE", "field": "activates", "align": "left"},
                                ]
                                t_rows = []
                                for tm in timers:
                                    t_rows.append({
                                        "unit": tm.get("timer", tm.get("unit", "—")),
                                        "next": tm.get("next", "—"),
                                        "last": tm.get("last", "—"),
                                        "activates": tm.get("activates", "—"),
                                    })
                                ui.table(columns=t_cols, rows=t_rows, row_key="unit").classes("w-full bg-slate-900")

                    # =============================================================
                    # SUB-TAB 10: SERTIFIKAT SSL/TLS & STATUS CADANGAN (BACKUP)
                    # =============================================================
                    with ui.tab_panel(t_ssl).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            with ui.row().classes("w-full items-center justify-between mb-3"):
                                with ui.column().classes("gap-0"):
                                    ui.label("Sertifikat SSL/TLS & Keamanan Domain").classes("text-sm font-bold text-white")
                                    ui.label("Pengawasan tanggal kedaluwarsa sertifikat SSL/TLS untuk mencegah outage").classes("text-xs text-slate-400")

                                ui.button("Tambah Path Sertifikat", icon="add", on_click=add_ssl_dlg.open).props("dense unelevated size=sm color=primary no-caps").classes("text-xs font-semibold")

                            if not ssl_certs:
                                ui.label("Belum ada sertifikat SSL/TLS yang terdeteksi atau didaftarkan pada server ini.").classes("text-xs text-slate-500 mb-4")
                            else:
                                ssl_cols = [
                                    {"name": "domain", "label": "DOMAIN / CN", "field": "domain", "align": "left"},
                                    {"name": "path", "label": "PATH BERKAS", "field": "path", "align": "left"},
                                    {"name": "issuer", "label": "PENERBIT (ISSUER)", "field": "issuer", "align": "left"},
                                    {"name": "expiry", "label": "KEDALUWARSA", "field": "expiry", "align": "left"},
                                    {"name": "days", "label": "SISA HARI", "field": "days", "align": "center"},
                                    {"name": "actions", "label": "AKSI", "field": "actions", "align": "center"},
                                ]
                                ssl_rows = []
                                for c in ssl_certs:
                                    days_val = c.get("days_left", 0)
                                    # Ekstrak domain bersih
                                    dom_list = c.get("domains")
                                    if dom_list and isinstance(dom_list, list):
                                        clean_dom = ", ".join(str(d) for d in dom_list)
                                    else:
                                        sub_str = c.get("subject", "")
                                        m_cn = re.search(r'(?:CN|commonName)\s*=\s*([^,]+)', sub_str, re.IGNORECASE) if isinstance(sub_str, str) else None
                                        clean_dom = m_cn.group(1).strip() if m_cn else (c.get("domain") or sub_str[:40] or "—")

                                    # Ekstrak penerbit (issuer) bersih
                                    iss_str = c.get("issuer", "")
                                    if isinstance(iss_str, str) and iss_str:
                                        m_o = re.search(r'(?:O|organizationName)\s*=\s*([^,]+)', iss_str, re.IGNORECASE)
                                        m_icn = re.search(r'(?:CN|commonName)\s*=\s*([^,]+)', iss_str, re.IGNORECASE)
                                        if m_o and m_icn:
                                            clean_iss = f"{m_o.group(1).strip()} ({m_icn.group(1).strip()})"
                                        elif m_icn:
                                            clean_iss = m_icn.group(1).strip()
                                        elif m_o:
                                            clean_iss = m_o.group(1).strip()
                                        else:
                                            clean_iss = iss_str[:40]
                                    else:
                                        clean_iss = "—"

                                    ssl_rows.append({
                                        "domain": clean_dom,
                                        "path": c.get("path", "—"),
                                        "issuer": clean_iss,
                                        "expiry": c.get("not_after", c.get("expiry", "—")),
                                        "days": days_val,
                                        "is_warn": days_val <= 14,
                                    })
                                ssl_tbl = ui.table(columns=ssl_cols, rows=ssl_rows, row_key="path").classes("w-full bg-slate-900 mb-6")
                                ssl_tbl.add_slot("body-cell-days", """
                                    <q-td :props="props">
                                        <q-badge :color="props.row.is_warn ? 'rose-9' : 'emerald-9'" class="text-[9.5px] font-bold px-2 py-0.5">
                                            {{ props.row.days }} hari
                                        </q-badge>
                                    </q-td>
                                """)
                                ssl_tbl.add_slot("body-cell-actions", """
                                    <q-td :props="props">
                                        <q-btn dense flat round size="xs" color="rose-4" icon="delete"
                                               @click="() => $parent.$emit('remove_ssl', props.row.path)">
                                            <q-tooltip class="bg-slate-900 text-[10px]">Hapus pemantauan path SSL ini</q-tooltip>
                                        </q-btn>
                                    </q-td>
                                """)
                                ssl_tbl.on("remove_ssl", lambda e: _queue_command("ssl_path_remove", params={"path": e.args}, note=f"Hapus path SSL {e.args}"))

                        # Tabel Status Berkas Cadangan (Backup)
                        with ui.card().classes("w-full p-4 custom-card"):
                            ui.label("Status Berkas Cadangan (Database & System Backup)").classes("text-sm font-bold text-white mb-2")
                            if not backup_status:
                                ui.label("Belum ada telemetri status berkas cadangan dari node ini.").classes("text-xs text-slate-500")
                            else:
                                if isinstance(backup_status, dict):
                                    summary_txt = backup_status.get("summary", "Status pemindaian cadangan aktif.")
                                    db_types = ", ".join(backup_status.get("database_types", [])) or "Tidak terdeteksi"
                                    tot_files = backup_status.get("total_files", 0)
                                    tot_size = backup_status.get("total_size_human", "0 B")

                                    with ui.row().classes("w-full items-center gap-4 bg-slate-950 p-3 rounded border border-slate-800 text-xs mb-3"):
                                        with ui.column().classes("gap-0.5"):
                                            ui.label("Ringkasan Cadangan:").classes("text-slate-400 font-semibold")
                                            ui.label(summary_txt).classes("text-slate-200")
                                        with ui.column().classes("gap-0.5"):
                                            ui.label("Basis Data Terdeteksi:").classes("text-slate-400 font-semibold")
                                            ui.badge(db_types, color="blue-9").classes("text-[9px] font-mono")
                                        with ui.column().classes("gap-0.5"):
                                            ui.label("Total Cadangan:").classes("text-slate-400 font-semibold")
                                            ui.label(f"{tot_files} berkas ({tot_size})").classes("text-emerald-400 font-bold")

                                    recent_files = backup_status.get("recent_files", [])
                                    if recent_files:
                                        bk_cols = [
                                            {"name": "file", "label": "BERKAS CADANGAN", "field": "file", "align": "left"},
                                            {"name": "size", "label": "UKURAN", "field": "size", "align": "left"},
                                            {"name": "mtime", "label": "WAKTU MODIFIKASI", "field": "mtime", "align": "left"},
                                        ]
                                        bk_rows = []
                                        for b in recent_files:
                                            if isinstance(b, dict):
                                                bk_rows.append({
                                                    "file": b.get("path", b.get("file", "—")),
                                                    "size": format_bytes(b.get("size_bytes", 0)) if b.get("size_bytes") else b.get("size_human", "—"),
                                                    "mtime": b.get("mtime", b.get("time", "—")),
                                                })
                                            else:
                                                bk_rows.append({"file": str(b), "size": "—", "mtime": "—"})
                                        ui.table(columns=bk_cols, rows=bk_rows, row_key="file").classes("w-full bg-slate-900")
                                    else:
                                        ui.label("Tidak ada berkas cadangan ditemukan pada direktori yang dipindai (/var/backups).").classes("text-xs text-slate-500")
                                elif isinstance(backup_status, list):
                                    bk_cols = [
                                        {"name": "target", "label": "TARGET CADANGAN", "field": "target", "align": "left"},
                                        {"name": "file", "label": "BERKAS TERAKHIR", "field": "file", "align": "left"},
                                        {"name": "size", "label": "UKURAN", "field": "size", "align": "left"},
                                        {"name": "mtime", "label": "WAKTU CADANGAN", "field": "mtime", "align": "left"},
                                        {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                                    ]
                                    bk_rows = []
                                    for b in backup_status:
                                        if isinstance(b, dict):
                                            bk_rows.append({
                                                "target": b.get("name", b.get("target", "—")),
                                                "file": b.get("latest_file", "—"),
                                                "size": format_bytes(b.get("size_bytes", 0)),
                                                "mtime": b.get("latest_mtime", "—"),
                                                "status": b.get("status", "OK").upper(),
                                            })
                                    ui.table(columns=bk_cols, rows=bk_rows, row_key="target").classes("w-full bg-slate-900")

                    # =============================================================
                    # SUB-TAB 11: LOG SISTEM (SYSTEM JOURNAL ERRORS)
                    # =============================================================
                    with ui.tab_panel(t_log).classes("gap-4 flex flex-col p-0"):
                        with ui.card().classes("w-full p-4 custom-card"):
                            ui.label("Log Kegagalan Sistem Terkini (Journalctl)").classes("text-sm font-bold text-white mb-2")
                            if not system_logs:
                                ui.label("Tidak ada catatan kegagalan sistem penting pada journal.").classes("text-xs text-emerald-400")
                            else:
                                log_cols = [
                                    {"name": "time", "label": "WAKTU", "field": "time", "align": "left"},
                                    {"name": "unit", "label": "UNIT / SERVICE", "field": "unit", "align": "left"},
                                    {"name": "msg", "label": "PESAN LOG SISTEM", "field": "msg", "align": "left"},
                                ]
                                log_rows = []
                                for entry in system_logs:
                                    if isinstance(entry, dict):
                                        log_rows.append({
                                            "time": entry.get("time", entry.get("timestamp", "—")),
                                            "unit": entry.get("unit", "systemd"),
                                            "msg": entry.get("message", "—"),
                                        })
                                    else:
                                        log_rows.append({"time": "—", "unit": "systemd", "msg": str(entry)})
                                ui.table(columns=log_cols, rows=log_rows, row_key="msg").classes("w-full bg-slate-900")
