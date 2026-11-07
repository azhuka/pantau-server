"""
Modul Daftar Server Terpadu (Fleet Management & Inventory)
==========================================================
Menyajikan tabel inventaris seluruh armada server dengan kepadatan data tinggi,
bilah multi-filter dinamis (status, lingkungan/tier, grup, dan pencarian),
modal penambahan server baru, pengungkapan kunci API & perintah instalasi,
regenerasi kunci API, penghapusan server, serta pengeditan metadata operasional.
"""

from datetime import datetime
import hashlib
import json
import secrets
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy import func

from models import AuditLog, Server, ServerExtras, SystemSnapshot
from .auth import get_auth_user
from .common import format_bytes, get_db, notify_error, notify_info, notify_success
from .layout import render_layout


def setup_servers_routes(session_factory):
    """Mendaftarkan rute daftar armada server ke NiceGUI engine."""

    @ui.page("/servers")
    def page_servers(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username
            can_manage = user.is_master_admin() or user.has_perm("can_manage_servers")

        render_layout(request, user, active_tab="servers")

        container = ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4")

        # ---------------------------------------------------------------------
        # Dialog 1: Modal Pengungkapan Kunci API & Perintah Instalasi
        # ---------------------------------------------------------------------
        reveal_dlg = ui.dialog()
        reveal_state = {"host": "", "ip": "", "key": "", "cmd": ""}

        with reveal_dlg, ui.card().classes("w-full max-w-2xl p-6 custom-card flex flex-col gap-4 border border-emerald-500/50"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("vpn_key", size="24px").classes("text-emerald-400")
                ui.label("Kunci API & Perintah Instalasi Agen").classes("text-base font-bold text-white")

            with ui.card().classes("w-full p-3 bg-amber-500/10 border border-amber-500/30 rounded text-xs text-amber-200 flex flex-col gap-1"):
                ui.label("PENTING: Salin kunci API dan simpan sekarang!").classes("font-bold")
                ui.label("Demi keamanan, kunci API ini HANYA DITAMPILKAN SATU KALI SAJA dan tidak dapat dilihat kembali setelah dialog ini ditutup.")

            reveal_target_label = ui.label("").classes("text-xs font-mono text-slate-300")

            ui.label("Token Kunci API:").classes("text-xs font-semibold text-slate-400 mt-1")
            with ui.row().classes("w-full items-center gap-2 bg-slate-950 p-2.5 rounded border border-slate-800"):
                reveal_key_label = ui.label("").classes("font-mono text-xs text-emerald-400 break-all flex-grow select-all")
                ui.button(icon="content_copy", on_click=lambda: _copy_text(reveal_state["key"], "Kunci API")).props("dense flat round size=sm color=slate-4")

            ui.label("Perintah Instalasi Satu Baris (Jalankan di Server Klien):").classes("text-xs font-semibold text-slate-400 mt-1")
            with ui.column().classes("w-full gap-2 bg-slate-950 p-2.5 rounded border border-slate-800"):
                reveal_cmd_label = ui.label("").classes("font-mono text-xs text-sky-300 break-all select-all")
                with ui.row().classes("w-full justify-end"):
                    ui.button("Salin Perintah", icon="content_copy", on_click=lambda: _copy_text(reveal_state["cmd"], "Perintah instalasi")).props("dense unelevated size=sm color=primary no-caps")

            with ui.row().classes("w-full justify-end mt-2"):
                ui.button("Selesai & Tutup", on_click=lambda: (reveal_dlg.close(), _reload_table())).props("dense unelevated color=emerald-7 no-caps")

        def _copy_text(text: str, label_name: str):
            if text:
                ui.run_javascript(f"navigator.clipboard.writeText({json.dumps(text)})")
                notify_success(f"{label_name} berhasil disalin ke clipboard.")

        def _open_reveal_dialog(hostname: str, ip: str, raw_key: str):
            host_header = request.headers.get("host", "127.0.0.1:8400")
            install_cmd = f"curl -sSL http://{host_header}/install.sh | sudo bash -s -- --key {raw_key}"
            reveal_state["host"] = hostname
            reveal_state["ip"] = ip
            reveal_state["key"] = raw_key
            reveal_state["cmd"] = install_cmd
            reveal_target_label.set_text(f"Server Target: {hostname} ({ip})")
            reveal_key_label.set_text(raw_key)
            reveal_cmd_label.set_text(install_cmd)
            reveal_dlg.open()

        # ---------------------------------------------------------------------
        # Dialog 2: Modal Tambah Server Baru (Onboarding)
        # ---------------------------------------------------------------------
        add_dlg = ui.dialog()
        with add_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4"):
            with ui.row().classes("items-center gap-2"):
                ui.icon("add_circle", size="22px").classes("text-primary")
                ui.label("Tambah Server Baru").classes("text-base font-bold text-white")

            with ui.column().classes("w-full gap-3"):
                add_hostname = ui.input("Nama Host (Hostname) *", placeholder="mis. srv-prod-db01").classes("w-full").props("dense outlined dark")
                add_ip = ui.input("Alamat IP Server *", placeholder="mis. 192.168.10.50").classes("w-full").props("dense outlined dark")
                add_group = ui.input("Nama Grup", placeholder="mis. Database, Produksi, Staging (Opsional)").classes("w-full").props("dense outlined dark")
                add_tier = ui.select({1: "Produksi (Tier 1 - Kritis & Vital)", 2: "Non-Produksi (Tier 2 - Standar / Dev)"}, value=2, label="Lingkungan / Tier").classes("w-full").props("dense outlined dark")
                add_platform = ui.select({"auto": "Deteksi Otomatis", "baremetal": "Baremetal Host", "vm": "Virtual Machine (KVM/QEMU)", "lxc": "LXC Container"}, value="auto", label="Override Platform").classes("w-full").props("dense outlined dark")
                add_terminal = ui.checkbox("Izinkan Akses Terminal Root Web (Bawaan)").props("dense dark")
                add_notes = ui.textarea("Catatan Operasional", placeholder="Keterangan server, lokasi rak, dll.").classes("w-full").props("dense outlined dark rows=2")

            def _submit_new_server():
                host_val = add_hostname.value.strip()
                ip_val = add_ip.value.strip()
                if not host_val or not ip_val:
                    notify_error("Nama host dan Alamat IP wajib diisi!")
                    return

                raw_token = secrets.token_hex(32)
                hashed_token = "sha256:" + hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

                with get_db(session_factory) as db:
                    # Validasi apakah hostname atau api_key sudah ada
                    existing_s = db.query(Server).filter(Server.hostname == host_val).first()
                    if existing_s:
                        notify_error(f"Server dengan hostname '{host_val}' sudah terdaftar.")
                        return

                    new_s = Server(
                        hostname=host_val,
                        ip_address=ip_val,
                        api_key=hashed_token,
                        group_name=add_group.value.strip() or None,
                        tier=int(add_tier.value or 2),
                        platform_override=None if add_platform.value == "auto" else add_platform.value,
                        allow_web_terminal=1 if add_terminal.value else 0,
                        notes=add_notes.value.strip() or None,
                        is_active=1,
                        is_maintenance=0,
                        created_at=datetime.utcnow(),
                    )
                    db.add(new_s)
                    db.flush()

                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=new_s.id,
                        action="create_server",
                        target=new_s.hostname,
                        result="berhasil",
                    )
                    db.add(audit)
                    db.commit()

                    notify_success(f"Server {new_s.hostname} berhasil didaftarkan!")

                add_dlg.close()
                add_hostname.set_value("")
                add_ip.set_value("")
                add_group.set_value("")
                add_notes.set_value("")
                _open_reveal_dialog(host_val, ip_val, raw_token)

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Batal", on_click=add_dlg.close).props("dense flat no-caps color=grey-5")
                ui.button("Daftarkan Server", icon="check", on_click=_submit_new_server).props("dense unelevated color=primary no-caps")

        # ---------------------------------------------------------------------
        # Dialog 3: Modal Regenerasi Kunci API
        # ---------------------------------------------------------------------
        regen_dlg = ui.dialog()
        regen_state = {"id": None, "host": "", "ip": ""}
        with regen_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/40"):
            with ui.row().classes("items-center gap-2 text-rose-400"):
                ui.icon("warning", size="24px")
                ui.label("Regenerasi Kunci API").classes("text-base font-bold text-white")

            regen_msg_label = ui.label("").classes("text-xs text-slate-300 leading-relaxed")

            def _confirm_regen_key():
                sid = regen_state["id"]
                if not sid:
                    return
                raw_token = secrets.token_hex(32)
                hashed_token = "sha256:" + hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

                with get_db(session_factory) as db:
                    s = db.query(Server).filter(Server.id == sid).first()
                    if not s:
                        notify_error("Server tidak ditemukan.")
                        return
                    s.api_key = hashed_token
                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=s.id,
                        action="regenerate_api_key",
                        target=s.hostname,
                        result="berhasil",
                    )
                    db.add(audit)
                    db.commit()
                    target_host = s.hostname
                    target_ip = s.ip_address

                regen_dlg.close()
                notify_success(f"Kunci API server {target_host} berhasil diregenerasi.")
                _open_reveal_dialog(target_host, target_ip, raw_token)

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Batal", on_click=regen_dlg.close).props("dense flat no-caps color=grey-5")
                ui.button("Ya, Regenerasi Kunci", icon="vpn_key", on_click=_confirm_regen_key).props("dense unelevated color=negative no-caps")

        def _open_regen_dialog(sid: int):
            with get_db(session_factory) as db:
                s = db.query(Server).filter(Server.id == sid).first()
                if not s:
                    return
                regen_state["id"] = s.id
                regen_state["host"] = s.hostname
                regen_state["ip"] = s.ip_address
                regen_msg_label.set_text(
                    f"Apakah Anda yakin ingin meregenerasi Kunci API untuk server '{s.hostname}' ({s.ip_address})? "
                    "PERINGATAN: Kunci API yang lama akan seketika hangus dan agen monitoring pada server tersebut akan terputus "
                    "sampai token baru dikonfigurasi ulang."
                )
            regen_dlg.open()

        # ---------------------------------------------------------------------
        # Dialog 4: Modal Hapus Server (Decommissioning)
        # ---------------------------------------------------------------------
        del_dlg = ui.dialog()
        del_state = {"id": None, "host": "", "ip": ""}
        with del_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/60"):
            with ui.row().classes("items-center gap-2 text-rose-400"):
                ui.icon("delete_forever", size="24px")
                ui.label("Hapus Server Dari Inventaris").classes("text-base font-bold text-white")

            del_msg_label = ui.label("").classes("text-xs text-slate-300 leading-relaxed")

            def _confirm_delete_server():
                sid = del_state["id"]
                if not sid:
                    return
                with get_db(session_factory) as db:
                    s = db.query(Server).filter(Server.id == sid).first()
                    if not s:
                        notify_error("Server tidak ditemukan.")
                        return
                    hostname = s.hostname
                    db.delete(s)
                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=sid,
                        action="delete_server",
                        target=hostname,
                        result="berhasil",
                    )
                    db.add(audit)
                    db.commit()
                    notify_success(f"Server '{hostname}' berhasil dihapus dari sistem.")
                del_dlg.close()
                _reload_table()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Batal", on_click=del_dlg.close).props("dense flat no-caps color=grey-5")
                ui.button("Hapus Permanen", icon="delete", on_click=_confirm_delete_server).props("dense unelevated color=negative no-caps")

        def _open_delete_dialog(sid: int):
            with get_db(session_factory) as db:
                s = db.query(Server).filter(Server.id == sid).first()
                if not s:
                    return
                del_state["id"] = s.id
                del_state["host"] = s.hostname
                del_state["ip"] = s.ip_address
                del_msg_label.set_text(
                    f"Anda akan menghapus server '{s.hostname}' ({s.ip_address}) secara permanen. "
                    "Seluruh riwayat snapshot performa, metrik layanan, dan log audit server ini akan terhapus. "
                    "Tindakan ini TIDAK DAPAT DIBATALKAN."
                )
            del_dlg.open()

        # ---------------------------------------------------------------------
        # Dialog 5: Modal Edit Metadata Server
        # ---------------------------------------------------------------------
        edit_dlg = ui.dialog()
        with edit_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4"):
            dlg_title = ui.label("Edit Metadata Server").classes("text-base font-bold text-white")
            sel_server_id = {"id": None}

            with ui.column().classes("w-full gap-3"):
                inp_hostname = ui.input("Nama Host (Hostname)").classes("w-full").props("dense outlined dark")
                inp_ip = ui.input("Alamat IP").classes("w-full").props("dense outlined dark")
                inp_group = ui.input("Nama Grup").classes("w-full").props("dense outlined dark")
                sel_tier = ui.select({1: "Produksi (Tier 1 - Kritis)", 2: "Non-Produksi (Tier 2 - Standar)"}, label="Lingkungan / Tier").classes("w-full").props("dense outlined dark")
                sel_platform = ui.select({"auto": "Deteksi Otomatis", "baremetal": "Baremetal Host", "vm": "Virtual Machine (KVM/QEMU)", "lxc": "LXC Container"}, label="Override Platform").classes("w-full").props("dense outlined dark")
                cb_terminal = ui.checkbox("Izinkan Akses Terminal Root Web (Bawaan)").props("dense dark")
                inp_notes = ui.textarea("Catatan Operasional").classes("w-full").props("dense outlined dark rows=2")

            def _save_server_metadata():
                sid = sel_server_id["id"]
                if not sid:
                    return
                with get_db(session_factory) as db:
                    s = db.query(Server).filter(Server.id == sid).first()
                    if not s:
                        notify_error("Server tidak ditemukan.")
                        return
                    s.hostname = inp_hostname.value.strip() or s.hostname
                    s.ip_address = inp_ip.value.strip() or s.ip_address
                    s.group_name = inp_group.value.strip() or None
                    s.tier = int(sel_tier.value or 2)
                    s.platform_override = None if sel_platform.value == "auto" else sel_platform.value
                    s.allow_web_terminal = 1 if cb_terminal.value else 0
                    s.notes = inp_notes.value.strip() or None

                    audit = AuditLog(
                        user_id=current_user_id,
                        username=current_username,
                        server_id=s.id,
                        action="update_server_meta",
                        target=s.hostname,
                        result="berhasil",
                    )
                    db.add(audit)
                    db.commit()
                    notify_success(f"Metadata server {s.hostname} berhasil diperbarui.")
                edit_dlg.close()
                _reload_table()

            with ui.row().classes("w-full justify-end gap-2 mt-2"):
                ui.button("Batal", on_click=edit_dlg.close).props("dense flat no-caps color=grey-5")
                ui.button("Simpan Perubahan", on_click=_save_server_metadata).props("dense unelevated color=primary no-caps")

        def _open_edit_dialog(sid: int):
            with get_db(session_factory) as db:
                s = db.query(Server).filter(Server.id == sid).first()
                if not s:
                    return
                sel_server_id["id"] = s.id
                dlg_title.set_text(f"Edit Metadata: {s.hostname}")
                inp_hostname.set_value(s.hostname)
                inp_ip.set_value(s.ip_address)
                inp_group.set_value(s.group_name or "")
                sel_tier.set_value(s.tier)
                sel_platform.set_value(s.platform_override or "auto")
                cb_terminal.set_value(bool(s.allow_web_terminal))
                inp_notes.set_value(s.notes or "")
            edit_dlg.open()

        # ---------------------------------------------------------------------
        # Header Halaman & Bilah Multi-Filter
        # ---------------------------------------------------------------------
        with container:
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Daftar Server Terpadu").classes("text-xl font-bold text-white")
                    ui.label("Pusat pengawasan kesehatan armada server, spesifikasi sistem operasi, dan kontrol siklus node").classes("text-xs text-slate-400")

                with ui.row().classes("items-center gap-2"):
                    if can_manage:
                        ui.button("Tambah Server", icon="add", on_click=add_dlg.open).props("dense unelevated no-caps size=sm color=primary").classes("text-xs font-semibold")
                    ui.button("Segarkan", icon="refresh", on_click=lambda: _reload_table()).props("dense outline no-caps size=sm color=slate-4").classes("text-xs")

            # Bilah Multi-Filter Terpadu
            with ui.card().classes("w-full p-3 custom-card"):
                with ui.row().classes("w-full items-center gap-3"):
                    search_box = ui.input(placeholder="Cari server, IP, spek, tag, OS...").props("dense outlined dark clearable").classes("flex-grow")
                    with ui.row().classes("items-center gap-2"):
                        ui.label("Filter:").classes("text-xs text-slate-400 font-medium")
                        status_filter = ui.select(["Semua Status", "Online", "Offline"], value="Semua Status").props("dense outlined dark options-dense").classes("w-36")
                        tier_filter = ui.select(["Semua Lingkungan", "Produksi", "Non-Produksi"], value="Semua Lingkungan").props("dense outlined dark options-dense").classes("w-40")
                        group_filter = ui.select(["Semua Grup"], value="Semua Grup").props("dense outlined dark options-dense").classes("w-36")
                        ui.button("Reset", icon="filter_alt_off", on_click=lambda: _reset_filters()).props("dense flat no-caps size=sm color=grey-4")

            table_container = ui.column().classes("w-full")

        def _reset_filters():
            search_box.set_value("")
            status_filter.set_value("Semua Status")
            tier_filter.set_value("Semua Lingkungan")
            group_filter.set_value("Semua Grup")
            _reload_table()

        search_box.on("update:model-value", lambda: _reload_table())
        status_filter.on("update:model-value", lambda: _reload_table())
        tier_filter.on("update:model-value", lambda: _reload_table())
        group_filter.on("update:model-value", lambda: _reload_table())

        def _reload_table():
            table_container.clear()
            with get_db(session_factory) as db:
                servers = db.query(Server).all()
                extras = {e.server_id: e for e in db.query(ServerExtras).all()}

                # Mengambil snapshot terbaru via subquery terindeks
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

                # Kumpulkan grup unik dinamis dari database
                distinct_groups = sorted(list({s.group_name for s in servers if s.group_name}))
                curr_options = ["Semua Grup"] + distinct_groups
                group_filter.options = curr_options

                now = datetime.utcnow()
                q = (search_box.value or "").strip().lower()
                st_val = status_filter.value
                tr_val = tier_filter.value
                grp_val = group_filter.value

                rows = []
                for s in servers:
                    is_online = bool(s.last_seen and (now - s.last_seen).total_seconds() < 45)
                    ext = extras.get(s.id)
                    snap = latest_snaps.get(s.id)

                    # Filter Status
                    if st_val == "Online" and not is_online:
                        continue
                    if st_val == "Offline" and is_online:
                        continue

                    # Filter Tier
                    if tr_val == "Produksi" and s.tier != 1:
                        continue
                    if tr_val == "Non-Produksi" and s.tier != 2:
                        continue

                    # Filter Grup
                    if grp_val != "Semua Grup" and (s.group_name or "") != grp_val:
                        continue

                    # Filter Query Pencarian
                    os_str = f"{ext.os_label or ''} {ext.kernel or ''} {ext.arch or ''}" if ext else ""
                    searchable = f"{s.hostname} {s.ip_address} {s.notes or ''} {os_str}".lower()
                    if q and q not in searchable:
                        continue

                    # Format CPU & RAM
                    mem_str = "—"
                    if snap and snap.mem_total:
                        used_gb = snap.mem_used / (1024**3)
                        tot_gb = snap.mem_total / (1024**3)
                        pct = round(snap.mem_used / snap.mem_total * 100, 1)
                        mem_str = f"{used_gb:.1f}G / {tot_gb:.1f}G\n({pct}%)"

                    # Disk Persen
                    disk_pct_str = "—"
                    if snap and snap.disks:
                        try:
                            d_list = json.loads(snap.disks)
                            if d_list and isinstance(d_list, list):
                                root_d = next((d for d in d_list if d.get("mount") == "/"), d_list[0])
                                disk_pct_str = f"{root_d.get('pct', '—')}%"
                        except Exception:
                            pass

                    # Uptime
                    upt_str = f"{snap.uptime_secs // 86400} hari" if snap and snap.uptime_secs else "—"

                    rows.append({
                        "id": s.id,
                        "hostname": s.hostname,
                        "ip": s.ip_address,
                        "tier": "PROD" if s.tier == 1 else "DEV",
                        "notes": s.notes or "",
                        "platform": s.platform_override or "Linux",
                        "os": f"{ext.os_label or 'Linux'} {ext.kernel or ''}" if ext else "Linux",
                        "cpu": f"{snap.cpu:.1f}%" if snap and snap.cpu is not None else "—",
                        "memory": mem_str,
                        "disk": disk_pct_str,
                        "uptime": upt_str,
                        "agent": f"v{ext.agent_version}" if ext and ext.agent_version else "—",
                        "is_online": is_online,
                        "status": "ONLINE" if is_online else "OFFLINE",
                    })

            columns = [
                {"name": "server", "label": "SERVER", "field": "hostname", "align": "left"},
                {"name": "ip", "label": "IP & ANTARMUKA", "field": "ip", "align": "left"},
                {"name": "platform", "label": "PLATFORM / HARDWARE", "field": "platform", "align": "left"},
                {"name": "os", "label": "SISTEM OPERASI", "field": "os", "align": "left"},
                {"name": "cpu", "label": "PROSESOR", "field": "cpu", "align": "center"},
                {"name": "memory", "label": "MEMORI", "field": "memory", "align": "left"},
                {"name": "disk", "label": "DISK", "field": "disk", "align": "center"},
                {"name": "uptime", "label": "UPTIME", "field": "uptime", "align": "left"},
                {"name": "agent", "label": "AGEN", "field": "agent", "align": "center"},
                {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                {"name": "actions", "label": "TINDAKAN", "field": "actions", "align": "center"},
            ]

            with table_container:
                tbl = ui.table(columns=columns, rows=rows, row_key="id").classes("w-full bg-slate-900")
                
                # Custom Slot Server Cell
                tbl.add_slot("body-cell-server", """
                    <q-td :props="props">
                        <div class="row items-center gap-2">
                            <q-icon name="circle" size="8px" :class="props.row.is_online ? 'text-emerald-400' : 'text-rose-500'" />
                            <span class="font-bold text-slate-100">{{ props.row.hostname }}</span>
                            <q-badge :color="props.row.tier === 'PROD' ? 'blue-9' : 'slate-8'" class="text-[8px] font-mono">
                                {{ props.row.tier }}
                            </q-badge>
                            <q-icon v-if="props.row.notes" name="info" size="14px" class="text-slate-500">
                                <q-tooltip class="bg-slate-900 border border-slate-700 text-xs">{{ props.row.notes }}</q-tooltip>
                            </q-icon>
                        </div>
                    </q-td>
                """)

                # Custom Slot IP Cell (With Copy Button)
                tbl.add_slot("body-cell-ip", """
                    <q-td :props="props">
                        <div class="row items-center gap-1 font-mono text-slate-300">
                            <span>{{ props.row.ip }}</span>
                            <q-btn dense flat round size="xs" icon="content_copy" color="slate-5"
                                   @click="navigator.clipboard.writeText(props.row.ip)">
                                <q-tooltip class="bg-slate-900 text-[10px]">Salin Alamat IP</q-tooltip>
                            </q-btn>
                        </div>
                    </q-td>
                """)

                # Custom Slot Status Cell
                tbl.add_slot("body-cell-status", """
                    <q-td :props="props">
                        <q-badge :color="props.row.is_online ? 'emerald-9' : 'rose-9'" class="text-[9.5px] font-bold px-2 py-0.5">
                            {{ props.row.status }}
                        </q-badge>
                    </q-td>
                """)

                # Custom Slot Actions Cell
                tbl.add_slot("body-cell-actions", """
                    <q-td :props="props">
                        <div class="row items-center justify-center gap-1">
                            <q-btn dense flat round size="sm" icon="visibility" color="blue-4"
                                   @click="() => $parent.$emit('view_detail', props.row.id)">
                                <q-tooltip class="bg-slate-900 text-[10px]">Rincian Server</q-tooltip>
                            </q-btn>
                            <q-btn dense flat round size="sm" icon="edit" color="slate-4"
                                   @click="() => $parent.$emit('edit_meta', props.row.id)">
                                <q-tooltip class="bg-slate-900 text-[10px]">Edit Metadata</q-tooltip>
                            </q-btn>
                            <q-btn dense flat round size="sm" icon="vpn_key" color="amber-4"
                                   @click="() => $parent.$emit('regen_key', props.row.id)">
                                <q-tooltip class="bg-slate-900 text-[10px]">Regenerasi Kunci API</q-tooltip>
                            </q-btn>
                            <q-btn dense flat round size="sm" icon="delete" color="rose-4"
                                   @click="() => $parent.$emit('del_server', props.row.id)">
                                <q-tooltip class="bg-slate-900 text-[10px]">Hapus Server</q-tooltip>
                            </q-btn>
                        </div>
                    </q-td>
                """)

                tbl.on("view_detail", lambda e: ui.navigate.to(f"/servers/{e.args}"))
                tbl.on("edit_meta", lambda e: _open_edit_dialog(e.args))
                tbl.on("regen_key", lambda e: _open_regen_dialog(e.args))
                tbl.on("del_server", lambda e: _open_delete_dialog(e.args))

        _reload_table()
