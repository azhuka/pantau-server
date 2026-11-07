"""
Modul Daftar Server Terpadu (Fleet Management & Inventory)
==========================================================
Menyajikan tabel inventaris seluruh armada server dengan kepadatan data tinggi,
bilah multi-filter dinamis (status, lingkungan/tier, grup, dan pencarian),
serta modal interaktif pengeditan metadata operasional server.
"""

from datetime import datetime
import json
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy import func

from models import AuditLog, Server, ServerExtras, SystemSnapshot
from .auth import get_auth_user
from .common import format_bytes, get_db, notify_error, notify_success
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

        render_layout(request, user, active_tab="servers")

        container = ui.column().classes("w-full max-w-7xl mx-auto p-6 gap-4")

        # Dialog Modal Edit Metadata Server
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
                inp_notes.set_value(s.notes or "")
            edit_dlg.open()

        # Header Halaman
        with container:
            with ui.row().classes("w-full items-center justify-between"):
                with ui.column().classes("gap-0.5"):
                    ui.label("Daftar Server Terpadu").classes("text-xl font-bold text-white")
                    ui.label("Pusat pengawasan kesehatan armada server, spesifikasi sistem operasi, dan agen secara real-time").classes("text-xs text-slate-400")
                ui.button("Segarkan", icon="refresh", on_click=lambda: _reload_table()).props("dense outline no-caps size=sm color=primary").classes("text-xs")

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
                                   @click="() => $parent.$emit('view_detail', props.row.id)" />
                            <q-btn dense flat round size="sm" icon="edit" color="slate-4"
                                   @click="() => $parent.$emit('edit_meta', props.row.id)" />
                        </div>
                    </q-td>
                """)

                tbl.on("view_detail", lambda e: ui.navigate.to(f"/servers/{e.args}"))
                tbl.on("edit_meta", lambda e: _open_edit_dialog(e.args))

        _reload_table()
