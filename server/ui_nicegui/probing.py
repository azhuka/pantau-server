"""
Modul Pemantauan Sintetis & Probing Endpoint (Synthetic Endpoint Monitoring)
==========================================================================
Menyediakan pengujian ketersediaan berkala terhadap HTTP/S, ICMP Ping, dan
TCP Port, dilengkapi kontrol penambahan target baru dan uji coba langsung.
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

            # Dialog Modal Tambah Target Probing
            add_dlg = ui.dialog()
            with add_dlg, ui.card().classes("w-full max-w-lg p-6 custom-card flex flex-col gap-4"):
                ui.label("Tambah Target Probing Endpoint").classes("text-base font-bold text-white")

                with ui.column().classes("w-full gap-3"):
                    inp_name = ui.input("Nama Target (misal: Portal Web Dinas)").classes("w-full").props("dense outlined dark stack-label")
                    sel_type = ui.select(
                        {"https": "HTTPS Endpoint", "http": "HTTP Endpoint", "ping": "ICMP Ping", "tcp": "TCP Port"},
                        value="https", label="Tipe Probing"
                    ).classes("w-full").props("dense outlined dark stack-label")
                    inp_target = ui.input("Target Host / URL (misal: https://barrukab.go.id)").classes("w-full").props("dense outlined dark stack-label")
                    inp_port = ui.number("Port Khusus (Opsional)", value=None).classes("w-full").props("dense outlined dark stack-label")
                    with ui.row().classes("w-full grid grid-cols-2 gap-2"):
                        inp_interval = ui.number("Interval (Detik)", value=60, min=10).classes("w-full").props("dense outlined dark stack-label")
                        inp_timeout = ui.number("Timeout (Detik)", value=5, min=1).classes("w-full").props("dense outlined dark stack-label")

                def _save_probe_target():
                    name = inp_name.value.strip()
                    t_val = inp_target.value.strip()
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
                    _reload_probing()

                with ui.row().classes("w-full justify-end gap-2 mt-2"):
                    ui.button("Batal", on_click=add_dlg.close).props("dense flat no-caps color=grey-5")
                    ui.button("Daftarkan Target", on_click=_save_probe_target).props("dense unelevated color=primary no-caps")

            with container:
                with ui.row().classes("w-full items-center justify-between"):
                    with ui.column().classes("gap-0.5"):
                        ui.label("Pemantauan Probing Endpoint Sintetis").classes("text-xl font-bold text-white")
                        ui.label("Pemeriksaan ketersediaan berkala HTTP/HTTPS, ICMP Ping, dan port TCP eksternal/internal").classes("text-xs text-slate-400")

                    with ui.row().classes("items-center gap-2"):
                        ui.button("Segarkan", icon="refresh", on_click=lambda: _reload_probing()).props("dense outline no-caps size=sm color=primary").classes("text-xs")
                        ui.button("+ Tambah Target Probing", icon="add", on_click=add_dlg.open).props("dense unelevated no-caps size=sm color=primary").classes("text-xs")

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
                        "latency": f"{t.last_latency_ms:.1f} ms" if t.last_latency_ms is not None else "—",
                        "uptime_24h": f"{t.uptime_24h:.1f}%" if t.uptime_24h is not None else "—",
                        "last_checked": t.last_checked_at.strftime("%Y-%m-%d %H:%M:%S") if t.last_checked_at else "—",
                    })

                cols = [
                    {"name": "name", "label": "TARGET", "field": "name", "align": "left"},
                    {"name": "type", "label": "TIPE", "field": "type", "align": "center"},
                    {"name": "target", "label": "ENDPOINT HOST / URL", "field": "target", "align": "left"},
                    {"name": "interval", "label": "INTERVAL", "field": "interval", "align": "center"},
                    {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                    {"name": "latency", "label": "LATENSI", "field": "latency", "align": "center"},
                    {"name": "uptime_24h", "label": "KETERSEDIAAN (24J)", "field": "uptime_24h", "align": "center"},
                    {"name": "last_checked", "label": "TERAKHIR DICEK", "field": "last_checked", "align": "left"},
                    {"name": "action", "label": "AKSI", "field": "action", "align": "center"},
                ]

                with table_container:
                    # 4 Ringkasan Metrik Probing
                    with ui.row().classes("w-full grid grid-cols-2 md:grid-cols-5 gap-3 mb-2"):
                        with ui.card().classes("p-3 custom-card"):
                            ui.label("TOTAL TARGET").classes("text-[9px] font-bold text-slate-400 uppercase tracking-wider")
                            ui.label(str(total_t)).classes("text-xl font-bold text-white font-mono mt-0.5")

                        with ui.card().classes("p-3 custom-card"):
                            ui.label("TARGET ONLINE").classes("text-[9px] font-bold text-emerald-400 uppercase tracking-wider")
                            ui.label(str(up_t)).classes("text-xl font-bold text-emerald-400 font-mono mt-0.5")

                        with ui.card().classes("p-3 custom-card"):
                            ui.label("DEGRADASI").classes("text-[9px] font-bold text-amber-400 uppercase tracking-wider")
                            ui.label(str(deg_t)).classes("text-xl font-bold text-amber-400 font-mono mt-0.5")

                        with ui.card().classes("p-3 custom-card"):
                            ui.label("OFFLINE / GAGAL").classes("text-[9px] font-bold text-rose-400 uppercase tracking-wider")
                            ui.label(str(down_t)).classes("text-xl font-bold text-rose-400 font-mono mt-0.5")

                        with ui.card().classes("p-3 custom-card"):
                            ui.label("RATA-RATA LATENSI").classes("text-[9px] font-bold text-purple-400 uppercase tracking-wider")
                            ui.label(f"{avg_lat} ms").classes("text-xl font-bold text-purple-400 font-mono mt-0.5")

                    if not rows:
                        with ui.card().classes("w-full p-8 custom-card flex flex-col items-center justify-center gap-2"):
                            ui.icon("wifi_tethering_off", size="36px").classes("text-slate-500")
                            ui.label("Belum ada target probing yang didaftarkan.").classes("text-sm text-slate-400 font-medium")
                    else:
                        ptbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full bg-slate-900")
                        ptbl.add_slot("body-cell-type", """
                            <q-td :props="props">
                                <q-badge color="blue-9" class="text-[9px] font-bold px-1.5 py-0.5">
                                    {{ props.row.type }}
                                </q-badge>
                            </q-td>
                        """)
                        ptbl.add_slot("body-cell-status", """
                            <q-td :props="props">
                                <q-badge :color="props.row.status === 'UP' ? 'emerald-9' : (props.row.status === 'DEGRADED' ? 'amber-9' : 'rose-9')"
                                         class="text-[9.5px] font-bold px-2 py-0.5">
                                    {{ props.row.status }}
                                </q-badge>
                            </q-td>
                        """)
                        ptbl.add_slot("body-cell-action", """
                            <q-td :props="props">
                                <q-btn dense outline size="xs" color="primary" icon="play_arrow" label="Uji Sekarang" no-caps
                                       @click="() => $parent.$emit('test_probe', props.row.id)" />
                            </q-td>
                        """)
                        ptbl.on("test_probe", lambda e: _test_probe_now(e.args))

            _reload_probing()
