"""
Modul Pusat Manajemen Insiden & Gangguan (Problems & Alerting Center)
====================================================================
Menyajikan seluruh insiden aktif dan riwayat anomali infrastruktur sistem,
dilengkapi ringkasan KPI keparahan Zabbix, bilah filter pil triage interaktif,
modal pengaturan ambang batas peringatan, serta kontrol resolusi instan.
"""

from datetime import datetime
import json
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse

from models import AuditLog, Server, ServerProblem, SystemSetting
from .auth import get_auth_user
from .common import format_duration, get_db, notify_error, notify_info, notify_success
from .layout import render_layout

DEFAULT_THRESHOLDS = {
    "cpu_warn": 85.0,
    "cpu_danger": 95.0,
    "ram_warn": 85.0,
    "ram_danger": 95.0,
    "disk_warn": 90.0,
    "disk_danger": 95.0,
    "swap_warn": 80.0,
    "swap_danger": 92.0,
    "ssh_fail_warn": 5,
    "ssh_fail_danger": 12,
}


def _get_current_thresholds(db) -> dict:
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
        if row and row.value:
            data = json.loads(row.value)
            res = dict(DEFAULT_THRESHOLDS)
            for k in res:
                if k in data and data[k] is not None:
                    try:
                        res[k] = int(data[k]) if "fail" in k else float(data[k])
                    except (ValueError, TypeError):
                        pass
            return res
    except Exception:
        pass
    return dict(DEFAULT_THRESHOLDS)


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
            can_manage = user.is_master_admin() or user.has_perm("can_manage_servers")

        with render_layout(request, user, active_tab="problems"):
            container = ui.column().classes("w-full gap-3")

            # -----------------------------------------------------------------
            # Dialog: Modal Pengaturan Ambang Batas Insiden Global
            # -----------------------------------------------------------------
            th_dialog = ui.dialog()
            with th_dialog, ui.card().classes("w-full max-w-xl p-5 custom-card flex flex-col gap-4"):
                with ui.row().classes("w-full items-center justify-between border-b border-slate-800 pb-2"):
                    with ui.row().classes("items-center gap-2"):
                        ui.icon("tune", size="20px").classes("text-primary")
                        ui.label("Ambang Batas Insiden Global").classes("text-base font-bold text-white")
                    ui.button(icon="close", on_click=th_dialog.close).props("dense flat round size=sm color=slate-4")

                ui.label("Pengaturan batas telemetri yang memicu insiden otomatis (Warning / Danger) di seluruh armada:").classes("text-xs text-slate-400")

                with get_db(session_factory) as db:
                    cur_th = _get_current_thresholds(db)

                with ui.column().classes("w-full gap-3 text-xs"):
                    # CPU
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("CPU Utilisation (%)").classes("font-semibold text-slate-300 w-44")
                        in_cpu_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("cpu_warn", 85.0), min=10, max=99, step=1).props("dense outlined dark").classes("w-36")
                        in_cpu_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("cpu_danger", 95.0), min=10, max=100, step=1).props("dense outlined dark").classes("w-36")

                    # RAM
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Memori RAM (%)").classes("font-semibold text-slate-300 w-44")
                        in_ram_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("ram_warn", 85.0), min=10, max=99, step=1).props("dense outlined dark").classes("w-36")
                        in_ram_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("ram_danger", 95.0), min=10, max=100, step=1).props("dense outlined dark").classes("w-36")

                    # Disk
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Partisi Disk (%)").classes("font-semibold text-slate-300 w-44")
                        in_disk_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("disk_warn", 90.0), min=10, max=99, step=1).props("dense outlined dark").classes("w-36")
                        in_disk_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("disk_danger", 95.0), min=10, max=100, step=1).props("dense outlined dark").classes("w-36")

                    # Swap
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Swap Memory (%)").classes("font-semibold text-slate-300 w-44")
                        in_swap_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("swap_warn", 80.0), min=10, max=99, step=1).props("dense outlined dark").classes("w-36")
                        in_swap_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("swap_danger", 92.0), min=10, max=100, step=1).props("dense outlined dark").classes("w-36")

                    # SSH Fail
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Gagal SSH (kali/mnt)").classes("font-semibold text-slate-300 w-44")
                        in_ssh_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("ssh_fail_warn", 5), min=1, max=50, step=1).props("dense outlined dark").classes("w-36")
                        in_ssh_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("ssh_fail_danger", 12), min=2, max=100, step=1).props("dense outlined dark").classes("w-36")

                def _save_thresholds():
                    if in_cpu_w.value >= in_cpu_d.value:
                        notify_error("CPU Warning tidak boleh lebih besar atau sama dengan Danger.")
                        return
                    if in_ram_w.value >= in_ram_d.value:
                        notify_error("RAM Warning tidak boleh lebih besar atau sama dengan Danger.")
                        return
                    if in_disk_w.value >= in_disk_d.value:
                        notify_error("Disk Warning tidak boleh lebih besar atau sama dengan Danger.")
                        return

                    new_val = {
                        "cpu_warn": float(in_cpu_w.value),
                        "cpu_danger": float(in_cpu_d.value),
                        "ram_warn": float(in_ram_w.value),
                        "ram_danger": float(in_ram_d.value),
                        "disk_warn": float(in_disk_w.value),
                        "disk_danger": float(in_disk_d.value),
                        "swap_warn": float(in_swap_w.value),
                        "swap_danger": float(in_swap_d.value),
                        "ssh_fail_warn": int(in_ssh_w.value),
                        "ssh_fail_danger": int(in_ssh_d.value),
                    }
                    with get_db(session_factory) as db:
                        row = db.query(SystemSetting).filter(SystemSetting.key == "thresholds").first()
                        if not row:
                            row = SystemSetting(key="thresholds", value=json.dumps(new_val), updated_at=datetime.utcnow())
                            db.add(row)
                        else:
                            row.value = json.dumps(new_val)
                            row.updated_at = datetime.utcnow()
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            action="update_thresholds",
                            target="Ambang Batas Global",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                    notify_success("Ambang batas insiden berhasil diperbarui.")
                    th_dialog.close()

                with ui.row().classes("w-full justify-end gap-2 border-t border-slate-800 pt-3"):
                    ui.button("Batal", on_click=th_dialog.close).props("dense flat no-caps color=slate-4")
                    ui.button("Simpan Ambang Batas", icon="save", on_click=_save_thresholds).props("dense unelevated no-caps color=primary")

            # -----------------------------------------------------------------
            # State & Kontrol Utama Halaman
            # -----------------------------------------------------------------
            filter_state = {"triage": "semua", "only_active": True, "search": ""}

            top_bar_wrap = ui.column().classes("w-full gap-2")
            filter_wrap = ui.column().classes("w-full")
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
                            target=f"Insiden #{p.id} ({p.message or p.key})",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                        notify_success(f"Insiden pada {srv_name} berhasil ditandai selesai.")
                _reload_problems()

            def _toggle_ignore(prob_id: int):
                with get_db(session_factory) as db:
                    p = db.query(ServerProblem).filter(ServerProblem.id == prob_id).first()
                    if p:
                        new_state = 0 if p.is_ignored else 1
                        p.is_ignored = new_state
                        p.ignored_by = current_username if new_state else None
                        p.ignored_until = None
                        act = "ignore_problem" if new_state else "unignore_problem"
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            server_id=p.server_id,
                            action=act,
                            target=f"Insiden #{p.id} ({p.message or p.key})",
                            result="berhasil",
                        )
                        db.add(audit)
                        db.commit()
                        msg = "Insiden diabaikan." if new_state else "Insiden dipulihkan dari daftar abaikan."
                        notify_info(msg)
                _reload_problems()

            def _reload_problems():
                top_bar_wrap.clear()
                filter_wrap.clear()
                table_container.clear()

                now = datetime.utcnow()
                with get_db(session_factory) as db:
                    all_probs = db.query(ServerProblem).order_by(ServerProblem.started_at.desc()).all()
                    servers = {s.id: s.hostname for s in db.query(Server).all()}
                    srv_list = db.query(Server).all()
                    online_srv_count = sum(1 for s in srv_list if s.last_seen and (now - s.last_seen).total_seconds() < 45)

                # Hitung statistik triage
                open_probs = [p for p in all_probs if p.resolved_at is None]
                danger_cnt = sum(1 for p in open_probs if p.severity in ("danger", "critical") and not p.is_ignored)
                avg_cnt = sum(1 for p in open_probs if p.severity in ("average", "gawat") and not p.is_ignored)
                warn_cnt = sum(1 for p in open_probs if p.severity in ("warning", "peringatan") and not p.is_ignored)
                info_cnt = sum(1 for p in open_probs if p.severity in ("info", "informasi") and not p.is_ignored)
                ign_cnt = sum(1 for p in open_probs if p.is_ignored)
                active_tot = danger_cnt + avg_cnt + warn_cnt + info_cnt

                # 1. Render Topbar dengan Summary Badges & Tombol Aksi
                with top_bar_wrap:
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3"):
                        with ui.column().classes("gap-0.5"):
                            ui.label("Pusat Insiden & Masalah").classes("text-xl font-bold text-white")
                            ui.label("Deteksi anomali real-time, pencatatan waktu henti, dan resolusi gangguan armada server").classes("text-xs text-slate-400")

                        with ui.row().classes("items-center gap-2 flex-wrap"):
                            # Badges Ringkasan
                            if danger_cnt > 0:
                                ui.html(f'<span class="badge badge-danger" style="font-size:10px;padding:3px 8px;font-weight:700">Kritis {danger_cnt}</span>')
                            if avg_cnt > 0:
                                ui.html(f'<span class="badge" style="background:rgba(249,115,22,0.18);border:1px solid rgba(249,115,22,0.6);color:#f97316;font-size:10px;padding:3px 8px;font-weight:700">Gawat {avg_cnt}</span>')
                            if warn_cnt > 0:
                                ui.html(f'<span class="badge badge-warn" style="font-size:10px;padding:3px 8px;font-weight:700">Peringatan {warn_cnt}</span>')
                            if info_cnt > 0:
                                ui.html(f'<span class="badge badge-info" style="font-size:10px;padding:3px 8px;font-weight:700">Info {info_cnt}</span>')
                            if ign_cnt > 0:
                                ui.html(f'<span class="badge badge-muted" style="font-size:10px;padding:3px 8px;font-weight:600">{ign_cnt} diabaikan</span>')
                            ui.html(f'<span class="badge badge-up" style="font-size:10px;padding:3px 8px;font-weight:600">✓ {online_srv_count} server normal</span>')

                            if can_manage:
                                ui.button("Ambang Batas Insiden", icon="tune", on_click=th_dialog.open).props(
                                    "dense outline no-caps size=sm color=slate-3"
                                ).classes("text-xs font-semibold")

                            ui.button("Segarkan", icon="refresh", on_click=_reload_problems).props(
                                "dense outline no-caps size=sm color=primary"
                            ).classes("text-xs")

                # 2. Render Bilah Filter & Triage Pills
                with filter_wrap:
                    with ui.card().classes("w-full p-3 custom-card flex flex-col gap-3"):
                        with ui.row().classes("w-full items-center justify-between flex-wrap gap-2"):
                            # Triage Pills
                            with ui.row().classes("items-center gap-1.5 flex-wrap"):
                                def _set_triage(val):
                                    filter_state["triage"] = val
                                    _reload_problems()

                                cur_t = filter_state["triage"]
                                t_all_cls = "bg-primary text-white" if cur_t == "semua" else "bg-slate-800 text-slate-300 hover:bg-slate-700"
                                t_dan_cls = "bg-red-900/60 border border-red-500 text-red-200" if cur_t == "danger" else "bg-slate-800 text-slate-300 hover:bg-slate-700"
                                t_avg_cls = "bg-orange-900/60 border border-orange-500 text-orange-200" if cur_t == "average" else "bg-slate-800 text-slate-300 hover:bg-slate-700"
                                t_war_cls = "bg-yellow-900/60 border border-yellow-500 text-yellow-200" if cur_t == "warning" else "bg-slate-800 text-slate-300 hover:bg-slate-700"
                                t_inf_cls = "bg-blue-900/60 border border-blue-500 text-blue-200" if cur_t == "info" else "bg-slate-800 text-slate-300 hover:bg-slate-700"
                                t_ign_cls = "bg-slate-700 text-slate-100" if cur_t == "ignored" else "bg-slate-800 text-slate-400 hover:bg-slate-700"

                                ui.button(f"Semua ({len(all_probs)})", on_click=lambda: _set_triage("semua")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_all_cls}")
                                ui.button(f"Kritis ({danger_cnt})", on_click=lambda: _set_triage("danger")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_dan_cls}")
                                ui.button(f"Gawat ({avg_cnt})", on_click=lambda: _set_triage("average")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_avg_cls}")
                                ui.button(f"Peringatan ({warn_cnt})", on_click=lambda: _set_triage("warning")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_war_cls}")
                                ui.button(f"Info ({info_cnt})", on_click=lambda: _set_triage("info")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_inf_cls}")
                                ui.button(f"Diabaikan ({ign_cnt})", on_click=lambda: _set_triage("ignored")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_ign_cls}")

                            # Switch & Search
                            with ui.row().classes("items-center gap-3"):
                                sw_act = ui.switch("Hanya Masalah Terbuka", value=filter_state["only_active"]).props("dense dark")

                                def _on_sw_change(e):
                                    filter_state["only_active"] = e.value
                                    _reload_problems()
                                sw_act.on("update:model-value", _on_sw_change)

                                s_inp = ui.input(placeholder="Cari server / pesan masalah...").props("dense outlined dark clearable").classes("w-64 text-xs")
                                s_inp.set_value(filter_state["search"])

                                def _on_s_change():
                                    filter_state["search"] = (s_inp.value or "").strip().lower()
                                    _reload_problems()
                                s_inp.on("update:model-value", lambda: _on_s_change())

                # 3. Filter data baris tabel
                q = filter_state["search"]
                t_mode = filter_state["triage"]
                only_act = filter_state["only_active"]

                rows = []
                for p in all_probs:
                    if only_act and p.resolved_at is not None:
                        continue

                    # Filter Keparahan / Triage
                    sev_raw = (p.severity or "warning").lower()
                    if t_mode == "ignored":
                        if not p.is_ignored:
                            continue
                    elif t_mode == "danger":
                        if sev_raw not in ("danger", "critical", "kritis") or p.is_ignored:
                            continue
                    elif t_mode == "average":
                        if sev_raw not in ("average", "gawat") or p.is_ignored:
                            continue
                    elif t_mode == "warning":
                        if sev_raw not in ("warning", "peringatan") or p.is_ignored:
                            continue
                    elif t_mode == "info":
                        if sev_raw not in ("info", "informasi") or p.is_ignored:
                            continue

                    srv_h = servers.get(p.server_id, f"Server #{p.server_id}")
                    msg_txt = p.message or p.tip or p.key or "Gangguan sistem"
                    if q and q not in f"{srv_h} {msg_txt}".lower():
                        continue

                    sev_label = "PERINGATAN"
                    if sev_raw in ("danger", "critical", "kritis"):
                        sev_label = "KRITIS"
                    elif sev_raw in ("average", "gawat"):
                        sev_label = "GAWAT"
                    elif sev_raw in ("info", "informasi"):
                        sev_label = "INFO"

                    rows.append({
                        "id": p.id,
                        "server": srv_h,
                        "sid": p.server_id,
                        "sev": sev_label,
                        "msg": msg_txt,
                        "started": p.started_at.strftime("%Y-%m-%d %H:%M:%S") if p.started_at else "—",
                        "resolved": p.resolved_at.strftime("%Y-%m-%d %H:%M:%S") if p.resolved_at else "—",
                        "dur": format_duration(p.started_at, p.resolved_at or now),
                        "is_open": p.resolved_at is None,
                        "is_ignored": bool(p.is_ignored),
                    })

                cols = [
                    {"name": "started", "label": "WAKTU MULAI", "field": "started", "align": "left"},
                    {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                    {"name": "sev", "label": "KEPARAHAN", "field": "sev", "align": "center"},
                    {"name": "msg", "label": "MASALAH / PEMICU GANGGUAN", "field": "msg", "align": "left"},
                    {"name": "dur", "label": "DURASI", "field": "dur", "align": "left"},
                    {"name": "status", "label": "STATUS", "field": "status", "align": "center"},
                    {"name": "action", "label": "TINDAKAN", "field": "action", "align": "center"},
                ]

                # 4. Render Tabel Insiden NOC
                with table_container:
                    if not rows:
                        with ui.card().classes("w-full p-8 custom-card flex flex-col items-center justify-center gap-2"):
                            ui.icon("check_circle", size="36px").classes("text-emerald-400")
                            ui.label("Tidak ada catatan insiden yang sesuai dengan kriteria filter.").classes("text-sm text-slate-300 font-medium")
                    else:
                        ptbl = ui.table(columns=cols, rows=rows, row_key="id").classes("w-full bg-slate-900").props("dense flat bordered")

                        ptbl.add_slot("body-cell-server", """
                            <q-td :props="props">
                                <a v-if="props.row.sid" :href="'/servers/' + props.row.sid" class="font-bold text-sky-400 hover:underline flex items-center gap-1">
                                    <q-icon name="dns" size="13px" class="text-slate-400" />
                                    <span>{{ props.row.server }}</span>
                                </a>
                                <span v-else class="font-mono text-slate-300">{{ props.row.server }}</span>
                            </q-td>
                        """)

                        ptbl.add_slot("body-cell-sev", """
                            <q-td :props="props">
                                <span class="badge" :class="props.row.sev === 'KRITIS' ? 'badge-danger' : (props.row.sev === 'GAWAT' ? 'badge-orange' : (props.row.sev === 'PERINGATAN' ? 'badge-warn' : 'badge-info'))" style="font-size:9.5px;padding:2px 7px;font-weight:700">
                                    {{ props.row.sev }}
                                </span>
                            </q-td>
                        """)

                        ptbl.add_slot("body-cell-status", """
                            <q-td :props="props">
                                <span v-if="!props.row.is_open" class="badge badge-muted" style="font-size:9px;padding:1px 6px">
                                    SELESAI
                                </span>
                                <span v-else-if="props.row.is_ignored" class="badge" style="background:rgba(148,163,184,0.15);border:1px solid rgba(148,163,184,0.4);color:var(--dim);font-size:9px;padding:1px 6px">
                                    DIABAIKAN
                                </span>
                                <span v-else class="badge badge-danger" style="font-size:9px;padding:1px 6px;font-weight:700">
                                    TERBUKA
                                </span>
                            </q-td>
                        """)

                        ptbl.add_slot("body-cell-action", """
                            <q-td :props="props" style="white-space: nowrap; min-width: 140px; text-align: center;">
                                <div class="flex items-center justify-center gap-1.5">
                                    <button v-if="props.row.is_open" class="btn btn-sm btn-ghost" style="color:var(--green);padding:2px 8px;font-size:11px;font-weight:600"
                                            @click="() => $parent.$emit('resolve', props.row.id)" title="Tandai insiden selesai">
                                        ✓ Selesaikan
                                    </button>
                                    <button v-if="props.row.is_open && !props.row.is_ignored" class="btn btn-sm btn-ghost" style="color:var(--dim);padding:2px 6px;font-size:11px"
                                            @click="() => $parent.$emit('ignore', props.row.id)" title="Abaikan alarm insiden ini">
                                        ⊘ Abaikan
                                    </button>
                                    <button v-if="props.row.is_open && props.row.is_ignored" class="btn btn-sm btn-ghost" style="color:var(--yellow);padding:2px 6px;font-size:11px"
                                            @click="() => $parent.$emit('ignore', props.row.id)" title="Pulihkan dari abaikan">
                                        ↺ Pulihkan
                                    </button>
                                    <span v-if="!props.row.is_open" class="text-slate-500 text-xs">—</span>
                                </div>
                            </q-td>
                        """)

                        ptbl.on("resolve", lambda e: _resolve_one(e.args))
                        ptbl.on("ignore", lambda e: _toggle_ignore(e.args))

            _reload_problems()
