"""
Modul Pemantauan Sintetis & Probing Endpoint (Synthetic Endpoint Monitoring)
==========================================================================
Menyediakan pengujian ketersediaan berkala terhadap HTTP/HTTPS, ICMP Ping, dan
TCP Port, dilengkapi kontrol penambahan, pengeditan, penjedaan, dan penghapusan
target serta pengujian instan real-time 100% selaras dengan konsep kanonikal NOC.
"""

from datetime import datetime
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, ProbeLog, ProbeTarget, Server
from prober import execute_probe, record_probe_execution
from .auth import get_auth_user
from .common import format_duration, get_db, notify_error, notify_info, notify_success
from .layout import render_layout


def setup_probing_routes(session_factory):
    """Mendaftarkan rute pemantauan endpoint sintetis ke NiceGUI engine."""

    @ui.page("/probing")
    def page_probing(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if not user:
                return RedirectResponse("/login")
            current_user_id = user.id
            current_username = user.username

        with render_layout(request, user, active_tab="probing"):
            container = ui.column().classes("w-full gap-3")

            # -----------------------------------------------------------------
            # Dialog 1: Modal Tambah Target Probing Baru
            # -----------------------------------------------------------------
            add_dlg = ui.dialog()
            with add_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4"):
                ui.label("Tambah Target Probing Endpoint").classes("text-base font-bold text-white")

                with ui.column().classes("w-full gap-3"):
                    with ui.column().classes("w-full gap-1"):
                        ui.label("Nama Target (Deskripsi)").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        inp_name = ui.input(placeholder="misal: Portal Web Kominfo").classes("w-full").props("dense outlined dark")

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Tipe Probing").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        sel_type = ui.select(
                            {"https": "HTTPS Endpoint", "http": "HTTP Endpoint", "ping": "ICMP Ping", "tcp": "TCP Port"},
                            value="https"
                        ).classes("w-full").props("dense outlined dark options-dense")

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Target Host / URL").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        inp_target = ui.input(placeholder="misal: https://barrukab.go.id atau 172.30.1.1").classes("w-full").props("dense outlined dark")

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Port Khusus (Opsional untuk TCP)").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        inp_port = ui.number(placeholder="Default: 80 / 443", value=None).classes("w-full").props("dense outlined dark")

                    with ui.row().classes("w-full grid grid-cols-2 gap-2"):
                        with ui.column().classes("w-full gap-1"):
                            ui.label("Interval (Detik)").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                            inp_interval = ui.number(value=60, min=10).classes("w-full").props("dense outlined dark")
                        with ui.column().classes("w-full gap-1"):
                            ui.label("Timeout (Detik)").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                            inp_timeout = ui.number(value=5, min=1).classes("w-full").props("dense outlined dark")

                def _save_probe_target():
                    name = (inp_name.value or "").strip()
                    t_val = (inp_target.value or "").strip()
                    if not name or not t_val:
                        notify_error("Nama dan Host/URL target wajib diisi.")
                        return

                    with get_db(session_factory) as db:
                        pt = ProbeTarget(
                            name=name,
                            probe_type=sel_type.value,
                            target=t_val,
                            port=int(inp_port.value) if inp_port.value else None,
                            interval_seconds=int(inp_interval.value or 60),
                            timeout_seconds=int(inp_timeout.value or 5),
                            is_active=1,
                            tier=1,
                        )
                        db.add(pt)
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            action="add_probe_target",
                            target=f"{name} ({t_val})",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                        notify_success(f"Target probing '{name}' berhasil didaftarkan.")
                    add_dlg.close()
                    inp_name.set_value("")
                    inp_target.set_value("")
                    _reload_probing()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=add_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Daftarkan Target", on_click=_save_probe_target).props("dense unelevated color=primary no-caps")

            # -----------------------------------------------------------------
            # Dialog 2: Modal Edit Target Probing
            # -----------------------------------------------------------------
            edit_dlg = ui.dialog()
            edit_state = {"id": None}
            with edit_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4"):
                edit_dlg_title = ui.label("Edit Target Probing").classes("text-base font-bold text-white")

                with ui.column().classes("w-full gap-3"):
                    with ui.column().classes("w-full gap-1"):
                        ui.label("Nama Target").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        edit_name = ui.input().classes("w-full").props("dense outlined dark")

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Tipe Probing").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        edit_type = ui.select(
                            {"https": "HTTPS Endpoint", "http": "HTTP Endpoint", "ping": "ICMP Ping", "tcp": "TCP Port"}
                        ).classes("w-full").props("dense outlined dark options-dense")

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Target Host / URL").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        edit_target = ui.input().classes("w-full").props("dense outlined dark")

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Port Khusus").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                        edit_port = ui.number(value=None).classes("w-full").props("dense outlined dark")

                    with ui.row().classes("w-full grid grid-cols-2 gap-2"):
                        with ui.column().classes("w-full gap-1"):
                            ui.label("Interval (Detik)").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                            edit_interval = ui.number(min=10).classes("w-full").props("dense outlined dark")
                        with ui.column().classes("w-full gap-1"):
                            ui.label("Timeout (Detik)").classes("text-[11px] font-bold text-slate-300 uppercase tracking-wide")
                            edit_timeout = ui.number(min=1).classes("w-full").props("dense outlined dark")

                def _save_edited_target():
                    tid = edit_state["id"]
                    if not tid:
                        return
                    name = (edit_name.value or "").strip()
                    t_val = (edit_target.value or "").strip()
                    if not name or not t_val:
                        notify_error("Nama dan Host/URL target wajib diisi.")
                        return

                    with get_db(session_factory) as db:
                        pt = db.query(ProbeTarget).filter(ProbeTarget.id == tid).first()
                        if not pt:
                            return
                        pt.name = name
                        pt.probe_type = edit_type.value
                        pt.target = t_val
                        pt.port = int(edit_port.value) if edit_port.value else None
                        pt.interval_seconds = int(edit_interval.value or 60)
                        pt.timeout_seconds = int(edit_timeout.value or 5)
                        db.commit()
                        notify_success(f"Target '{name}' berhasil diperbarui.")
                    edit_dlg.close()
                    _reload_probing()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=edit_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Simpan Perubahan", on_click=_save_edited_target).props("dense unelevated color=primary no-caps")

            def _open_edit_dialog(tid: int):
                with get_db(session_factory) as db:
                    pt = db.query(ProbeTarget).filter(ProbeTarget.id == tid).first()
                    if not pt:
                        return
                    edit_state["id"] = pt.id
                    edit_dlg_title.set_text(f"Edit Target Probing: {pt.name}")
                    edit_name.set_value(pt.name)
                    edit_type.set_value(pt.probe_type)
                    edit_target.set_value(pt.target)
                    edit_port.set_value(pt.port)
                    edit_interval.set_value(pt.interval_seconds)
                    edit_timeout.set_value(pt.timeout_seconds)
                edit_dlg.open()

            # -----------------------------------------------------------------
            # Dialog 3: Modal Hapus Target Probing
            # -----------------------------------------------------------------
            del_dlg = ui.dialog()
            del_state = {"id": None, "name": ""}
            with del_dlg, ui.card().classes("w-full max-w-md p-6 custom-card flex flex-col gap-4 border border-rose-500/50"):
                ui.label("Hapus Target Probing").classes("text-base font-bold text-white")
                del_msg_label = ui.label("").classes("text-xs text-slate-300 leading-relaxed")

                def _confirm_delete():
                    tid = del_state["id"]
                    if not tid:
                        return
                    with get_db(session_factory) as db:
                        pt = db.query(ProbeTarget).filter(ProbeTarget.id == tid).first()
                        if pt:
                            t_name = pt.name
                            db.query(ProbeLog).filter(ProbeLog.target_id == tid).delete()
                            db.delete(pt)
                            db.commit()
                            notify_success(f"Target probing '{t_name}' berhasil dihapus.")
                    del_dlg.close()
                    _reload_probing()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=del_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Hapus Permanen", icon="delete", on_click=_confirm_delete).props("dense unelevated color=negative no-caps")

            def _open_delete_dialog(tid: int):
                with get_db(session_factory) as db:
                    pt = db.query(ProbeTarget).filter(ProbeTarget.id == tid).first()
                    if not pt:
                        return
                    del_state["id"] = pt.id
                    del_state["name"] = pt.name
                    del_msg_label.set_text(f"Apakah Anda yakin ingin menghapus target probing '{pt.name}' ({pt.target})? Riwayat telemetri probe juga akan dihapus.")
                del_dlg.open()

            def _toggle_active(tid: int):
                with get_db(session_factory) as db:
                    pt = db.query(ProbeTarget).filter(ProbeTarget.id == tid).first()
                    if pt:
                        pt.is_active = 0 if pt.is_active else 1
                        act_str = "diaktifkan" if pt.is_active else "dijeda"
                        db.commit()
                        notify_info(f"Target '{pt.name}' {act_str}.")
                _reload_probing()

            # -----------------------------------------------------------------
            # Header Halaman
            # -----------------------------------------------------------------
            with container:
                with ui.row().classes("w-full items-center justify-between mb-1"):
                    with ui.column().classes("gap-0"):
                        ui.label("Pemantauan Probing Endpoint Sintetis").classes("text-lg font-bold text-white")
                        ui.label("Pemeriksaan ketersediaan berkala HTTP/HTTPS, ICMP Ping, dan port TCP eksternal/internal").classes("text-xs text-slate-400")

                    with ui.row().classes("items-center gap-2"):
                        ui.button("Tambah Target Probing", icon="add", on_click=add_dlg.open).props("dense unelevated no-caps size=sm color=primary").classes("text-xs font-semibold")

                table_container = ui.column().classes("w-full")

            async def _test_probe_now(target_id: int):
                with get_db(session_factory) as db:
                    target = db.query(ProbeTarget).filter(ProbeTarget.id == target_id).first()
                    if not target:
                        notify_error("Target tidak ditemukan.")
                        return
                    p_data = {
                        "id": target.id,
                        "probe_type": target.probe_type,
                        "target": target.target,
                        "port": target.port,
                        "timeout_seconds": target.timeout_seconds,
                    }
                    t_name = target.name

                notify_info(f"Mengirim probe instan ke {t_name}...")
                try:
                    res = await execute_probe(p_data)
                    with get_db(session_factory) as db:
                        record_probe_execution(db, target_id, res)
                    status_str = "BERHASIL (UP)" if res.is_up else "GAGAL (DOWN)"
                    lat_str = f"{res.latency_ms:.1f} ms" if res.latency_ms else "—"
                    notify_success(f"Hasil Probe {t_name}: {status_str} · Latensi: {lat_str}")
                except Exception as e:
                    notify_error(f"Gagal mengeksekusi probe: {str(e)[:100]}")
                _reload_probing()

            def _reload_probing():
                table_container.clear()
                with get_db(session_factory) as db:
                    targets = db.query(ProbeTarget).all()

                total_t = len(targets)
                up_t = sum(1 for t in targets if t.status == "up")
                deg_t = sum(1 for t in targets if t.status == "degraded")
                down_t = sum(1 for t in targets if t.status == "down")
                latencies = [t.last_latency_ms for t in targets if t.last_latency_ms is not None]
                avg_lat = round(sum(latencies) / len(latencies), 1) if latencies else 0.0

                rows = []
                for t in targets:
                    status_label = (t.status or "UNKNOWN").upper()
                    rows.append({
                        "id": t.id,
                        "name": t.name,
                        "type": t.probe_type.upper(),
                        "target": t.target,
                        "interval": f"{t.interval_seconds}s",
                        "status": status_label,
                        "is_active": bool(t.is_active),
                        "latency": f"{t.last_latency_ms:.1f} ms" if t.last_latency_ms is not None else "—",
                        "uptime_24h": f"{t.uptime_24h:.1f}%" if t.uptime_24h is not None else "—",
                        "last_checked": t.last_checked_at.strftime("%Y-%m-%d %H:%M:%S") if t.last_checked_at else "—",
                    })

                cols = [
                    {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                    {"name": "name", "label": "TARGET PROBING", "field": "name", "align": "left"},
                    {"name": "type", "label": "METODE", "field": "type", "align": "center"},
                    {"name": "latency", "label": "LATENSI", "field": "latency", "align": "center"},
                    {"name": "uptime_24h", "label": "KETERSEDIAAN (24J)", "field": "uptime_24h", "align": "center"},
                    {"name": "interval", "label": "INTERVAL", "field": "interval", "align": "center"},
                    {"name": "last_checked", "label": "TERAKHIR DICEK", "field": "last_checked", "align": "left"},
                    {"name": "actions", "label": "TINDAKAN", "field": "actions", "align": "center"},
                ]

                with table_container:
                    # 5 KPI Ringkasan Metrik Probing Kanonikal
                    with ui.row().classes("w-full grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3 items-stretch").style("width: 100% !important"):
                        with ui.card().classes("p-3.5 custom-card border-l-4 border-l-blue-500 flex flex-col gap-1"):
                            ui.label("TOTAL TARGET").classes("text-[10px] font-bold text-slate-400 tracking-wider")
                            ui.label(str(total_t)).classes("text-2xl font-black font-mono text-white")

                        with ui.card().classes("p-3.5 custom-card border-l-4 border-l-emerald-500 flex flex-col gap-1"):
                            ui.label("TARGET ONLINE").classes("text-[10px] font-bold text-emerald-400 tracking-wider")
                            ui.label(str(up_t)).classes("text-2xl font-black font-mono text-emerald-400")

                        with ui.card().classes("p-3.5 custom-card border-l-4 border-l-amber-500 flex flex-col gap-1"):
                            ui.label("DEGRADASI").classes("text-[10px] font-bold text-amber-400 tracking-wider")
                            ui.label(str(deg_t)).classes("text-2xl font-black font-mono text-amber-400")

                        with ui.card().classes("p-3.5 custom-card border-l-4 border-l-rose-500 flex flex-col gap-1"):
                            ui.label("OFFLINE / GAGAL").classes("text-[10px] font-bold text-rose-400 tracking-wider")
                            ui.label(str(down_t)).classes("text-2xl font-black font-mono text-rose-400")

                        with ui.card().classes("p-3.5 custom-card border-l-4 border-l-purple-500 flex flex-col gap-1"):
                            ui.label("RATA-RATA LATENSI").classes("text-[10px] font-bold text-purple-400 tracking-wider")
                            ui.label(f"{avg_lat} ms").classes("text-2xl font-black font-mono text-purple-300")

                    if not rows:
                        with ui.card().classes("w-full p-8 custom-card flex flex-col items-center justify-center gap-2"):
                            ui.icon("wifi_tethering_off", size="36px").classes("text-slate-500")
                            ui.label("Belum ada target probing yang didaftarkan.").classes("text-sm text-slate-400 font-medium")
                    else:
                        ptbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full bg-slate-900")

                        ptbl.add_slot("body-cell-status", """
                            <q-td :props="props" style="text-align:center">
                                <q-badge :color="props.row.status === 'UP' ? 'emerald-9' : (props.row.status === 'DEGRADED' ? 'amber-9' : 'rose-9')"
                                         class="text-[9.5px] font-bold px-2 py-0.5">
                                    {{ props.row.status }}
                                </q-badge>
                            </q-td>
                        """)

                        ptbl.add_slot("body-cell-name", """
                            <q-td :props="props">
                                <div class="flex flex-col gap-0.5 justify-start">
                                    <span class="font-bold text-white text-xs">{{ props.row.name }}</span>
                                    <span class="font-mono text-[10px] text-slate-400">{{ props.row.target }}</span>
                                </div>
                            </q-td>
                        """)

                        ptbl.add_slot("body-cell-type", """
                            <q-td :props="props" style="text-align:center">
                                <q-badge color="blue-9" class="text-[9px] font-bold px-1.5 py-0.5">
                                    {{ props.row.type }}
                                </q-badge>
                            </q-td>
                        """)

                        # Custom Slot Actions: 4 Tombol Baku (Uji, Edit, Jeda, Hapus)
                        ptbl.add_slot("body-cell-actions", """
                            <q-td :props="props" style="white-space: nowrap; width: 120px; text-align: center;">
                                <div class="action-btn-group justify-center gap-1">
                                    <q-btn dense flat round size="sm" icon="play_arrow" color="emerald-4"
                                           @click="() => $parent.$emit('test_probe', props.row.id)">
                                        <q-tooltip class="bg-slate-900 text-[10px]">Uji Sekarang</q-tooltip>
                                    </q-btn>
                                    <q-btn dense flat round size="sm" icon="edit" color="slate-4"
                                           @click="() => $parent.$emit('edit_probe', props.row.id)">
                                        <q-tooltip class="bg-slate-900 text-[10px]">Edit Target</q-tooltip>
                                    </q-btn>
                                    <q-btn dense flat round size="sm" :icon="props.row.is_active ? 'pause' : 'play_circle'" :color="props.row.is_active ? 'amber-4' : 'blue-4'"
                                           @click="() => $parent.$emit('toggle_probe', props.row.id)">
                                        <q-tooltip class="bg-slate-900 text-[10px]">{{ props.row.is_active ? 'Jeda Pemantauan' : 'Aktifkan Kembali' }}</q-tooltip>
                                    </q-btn>
                                    <q-btn dense flat round size="sm" icon="delete" color="rose-4"
                                           @click="() => $parent.$emit('del_probe', props.row.id)">
                                        <q-tooltip class="bg-slate-900 text-[10px]">Hapus Target</q-tooltip>
                                    </q-btn>
                                </div>
                            </q-td>
                        """)

                        ptbl.on("test_probe", lambda e: _test_probe_now(e.args))
                        ptbl.on("edit_probe", lambda e: _open_edit_dialog(e.args))
                        ptbl.on("toggle_probe", lambda e: _toggle_active(e.args))
                        ptbl.on("del_probe", lambda e: _open_delete_dialog(e.args))

            _reload_probing()
