"""
Modul Pusat Manajemen Insiden & Gangguan (Problems & Alerting Center)
====================================================================
Menyajikan seluruh insiden aktif dan riwayat anomali infrastruktur sistem,
dilengkapi ringkasan KPI keparahan Zabbix, bilah filter pil triage interaktif,
modal pengaturan ambang batas peringatan, penanganan insiden (ACK), pengabaian alarm,
serta tabel riwayat insiden teratasi dengan metrik MTTR (Mean Time to Resolve).
"""

from datetime import datetime, timedelta
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

    # Import problems_aggregate dari server.main secara lokal untuk menghindari siklus impor
    from main import problems_aggregate

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
            container = ui.column().classes("w-full gap-4")

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
                        in_cpu_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("cpu_warn", 85.0), min=10, max=99, step=1).props("dense outlined dark stack-label").classes("w-36")
                        in_cpu_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("cpu_danger", 95.0), min=10, max=100, step=1).props("dense outlined dark stack-label").classes("w-36")

                    # RAM
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Memori RAM (%)").classes("font-semibold text-slate-300 w-44")
                        in_ram_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("ram_warn", 85.0), min=10, max=99, step=1).props("dense outlined dark stack-label").classes("w-36")
                        in_ram_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("ram_danger", 95.0), min=10, max=100, step=1).props("dense outlined dark stack-label").classes("w-36")

                    # Disk
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Partisi Disk (%)").classes("font-semibold text-slate-300 w-44")
                        in_disk_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("disk_warn", 90.0), min=10, max=99, step=1).props("dense outlined dark stack-label").classes("w-36")
                        in_disk_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("disk_danger", 95.0), min=10, max=100, step=1).props("dense outlined dark stack-label").classes("w-36")

                    # Swap
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Swap Memory (%)").classes("font-semibold text-slate-300 w-44")
                        in_swap_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("swap_warn", 80.0), min=10, max=99, step=1).props("dense outlined dark stack-label").classes("w-36")
                        in_swap_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("swap_danger", 92.0), min=10, max=100, step=1).props("dense outlined dark stack-label").classes("w-36")

                    # SSH Fail
                    with ui.row().classes("w-full items-center justify-between"):
                        ui.label("Gagal SSH (kali/mnt)").classes("font-semibold text-slate-300 w-44")
                        in_ssh_w = ui.number(label="Peringatan (Warn)", value=cur_th.get("ssh_fail_warn", 5), min=1, max=50, step=1).props("dense outlined dark stack-label").classes("w-36")
                        in_ssh_d = ui.number(label="Bahaya (Danger)", value=cur_th.get("ssh_fail_danger", 12), min=2, max=100, step=1).props("dense outlined dark stack-label").classes("w-36")

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
            # State & Kontrol Filter Halaman
            # -----------------------------------------------------------------
            filter_state = {"triage": "semua", "search": ""}

            top_bar_wrap = ui.column().classes("w-full gap-2")
            filter_wrap = ui.column().classes("w-full")
            open_container = ui.column().classes("w-full")
            resolved_container = ui.column().classes("w-full")

            def _toggle_ack(prob_id: int):
                """Acknowledge (tangani) insiden atau batalkan penanganan."""
                with get_db(session_factory) as db:
                    p = db.query(ServerProblem).filter(ServerProblem.id == prob_id).first()
                    if p:
                        if p.acknowledged_by:
                            p.acknowledged_by = None
                            p.acknowledged_at = None
                            act = "alert_unack"
                            res_txt = "batal ditangani"
                            msg = "Penanganan insiden dibatalkan."
                        else:
                            p.acknowledged_by = current_username
                            p.acknowledged_at = datetime.utcnow()
                            act = "alert_ack"
                            res_txt = "ditangani"
                            msg = f"Insiden ditandai ditangani oleh {current_username}."

                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            server_id=p.server_id,
                            action=act,
                            target=f"Insiden #{p.id} ({p.message or p.key})",
                            result=res_txt,
                        )
                        db.add(audit)
                        db.commit()
                        notify_info(msg)
                _reload_problems()

            def _toggle_ignore(prob_id: int):
                """Abaikan alarm insiden sementara atau pulihkan ke pemantauan aktif."""
                with get_db(session_factory) as db:
                    p = db.query(ServerProblem).filter(ServerProblem.id == prob_id).first()
                    if p:
                        new_state = 0 if p.is_ignored else 1
                        p.is_ignored = new_state
                        p.ignored_by = current_username if new_state else None
                        p.ignored_until = None
                        p.ignored_reason = f"Diabaikan oleh {current_username}" if new_state else None
                        if new_state and not p.acknowledged_by:
                            p.acknowledged_by = current_username
                            p.acknowledged_at = datetime.utcnow()

                        act = "ignore_problem" if new_state else "unignore_problem"
                        audit = AuditLog(
                            user_id=current_user_id,
                            username=current_username,
                            server_id=p.server_id,
                            action=act,
                            target=f"Insiden #{p.id} ({p.message or p.key})",
                            result="diabaikan" if new_state else "dipulihkan",
                        )
                        db.add(audit)
                        db.commit()
                        msg = "Insiden diabaikan (alarm dibisukan)." if new_state else "Insiden dipulihkan dari daftar abaikan."
                        notify_info(msg)
                _reload_problems()

            def _reload_problems():
                top_bar_wrap.clear()
                filter_wrap.clear()
                open_container.clear()
                resolved_container.clear()

                now = datetime.utcnow()
                with get_db(session_factory) as db:
                    open_list, resolved_list = problems_aggregate(db, res_period="24h")
                    srv_count = db.query(Server).count()

                # Statistik agregat triage
                danger_cnt = sum(1 for p in open_list if p.get("severity") in ("danger", "critical") and not p.get("is_ignored"))
                avg_cnt = sum(1 for p in open_list if p.get("severity") in ("average", "gawat") and not p.get("is_ignored"))
                warn_cnt = sum(1 for p in open_list if p.get("severity") in ("warning", "peringatan") and not p.get("is_ignored"))
                info_cnt = sum(1 for p in open_list if p.get("severity") in ("info", "informasi") and not p.get("is_ignored"))
                ign_cnt = sum(1 for p in open_list if p.get("is_ignored"))
                active_open_servers = {p["server_id"] for p in open_list if not p.get("is_ignored")}
                online_srv_count = max(0, srv_count - len(active_open_servers))

                # Hitung MTTR rata-rata untuk resolved_list
                res_durations = []
                manual_resolved_cnt = 0
                for p in resolved_list:
                    st = p.get("started_at")
                    res = p.get("resolved_at")
                    if isinstance(st, datetime) and isinstance(res, datetime):
                        res_durations.append(max(0, int((res - st).total_seconds())))
                    if p.get("acknowledged_by") or p.get("res_type") == "manual":
                        manual_resolved_cnt += 1
                avg_s = int(sum(res_durations) / len(res_durations)) if res_durations else 0
                if avg_s > 0:
                    m, s = divmod(avg_s, 60)
                    h, m = divmod(m, 60)
                    d, h = divmod(h, 24)
                    if d > 0:
                        avg_mttr_str = f"{d}h {h}j"
                    elif h > 0:
                        avg_mttr_str = f"{h}j {m}m"
                    elif m > 0:
                        avg_mttr_str = f"{m}m {s}d"
                    else:
                        avg_mttr_str = f"{s} detik"
                else:
                    avg_mttr_str = "—"

                # 1. Topbar Ringkasan Status & Tombol Aksi
                with top_bar_wrap:
                    with ui.row().classes("w-full items-center justify-between flex-wrap gap-3"):
                        with ui.column().classes("gap-0.5"):
                            ui.label("Pusat Insiden & Masalah").classes("text-xl font-bold text-white")
                            ui.label("Deteksi anomali real-time, pencatatan waktu henti, dan resolusi gangguan armada server").classes("text-xs text-slate-400")

                        with ui.row().classes("items-center gap-2 flex-wrap"):
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

                # 2. Bilah Filter & Triage Pills
                with filter_wrap:
                    with ui.card().classes("w-full p-3 custom-card flex flex-col gap-3"):
                        with ui.row().classes("w-full items-center justify-between flex-wrap gap-2"):
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

                                ui.button(f"Semua ({len(open_list)})", on_click=lambda: _set_triage("semua")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_all_cls}")
                                ui.button(f"Kritis ({danger_cnt})", on_click=lambda: _set_triage("danger")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_dan_cls}")
                                ui.button(f"Gawat ({avg_cnt})", on_click=lambda: _set_triage("average")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_avg_cls}")
                                ui.button(f"Peringatan ({warn_cnt})", on_click=lambda: _set_triage("warning")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_war_cls}")
                                ui.button(f"Info ({info_cnt})", on_click=lambda: _set_triage("info")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_inf_cls}")
                                ui.button(f"Diabaikan ({ign_cnt})", on_click=lambda: _set_triage("ignored")).props("dense unelevated size=sm no-caps").classes(f"rounded-full px-3 text-[11px] {t_ign_cls}")

                            s_inp = ui.input(placeholder="Cari server / pesan masalah...").props("dense outlined dark clearable").classes("w-72 text-xs")
                            s_inp.set_value(filter_state["search"])

                            def _on_s_change():
                                filter_state["search"] = (s_inp.value or "").strip().lower()
                                _reload_problems()
                            s_inp.on("update:model-value", lambda: _on_s_change())

                # 3. Filter Baris Insiden Terbuka
                q = filter_state["search"]
                t_mode = filter_state["triage"]

                open_rows = []
                for p in open_list:
                    sev_raw = (p.get("severity") or "warning").lower()
                    if t_mode == "ignored":
                        if not p.get("is_ignored"):
                            continue
                    elif t_mode == "danger":
                        if sev_raw not in ("danger", "critical", "kritis") or p.get("is_ignored"):
                            continue
                    elif t_mode == "average":
                        if sev_raw not in ("average", "gawat") or p.get("is_ignored"):
                            continue
                    elif t_mode == "warning":
                        if sev_raw not in ("warning", "peringatan") or p.get("is_ignored"):
                            continue
                    elif t_mode == "info":
                        if sev_raw not in ("info", "informasi") or p.get("is_ignored"):
                            continue

                    srv_h = p.get("hostname") or f"Server #{p.get('server_id')}"
                    msg_txt = p.get("message") or p.get("tip") or p.get("key") or "Gangguan sistem"
                    if q and q not in f"{srv_h} {msg_txt}".lower():
                        continue

                    sev_label = "PERINGATAN"
                    if sev_raw in ("danger", "critical", "kritis"):
                        sev_label = "KRITIS"
                    elif sev_raw in ("average", "gawat"):
                        sev_label = "GAWAT"
                    elif sev_raw in ("info", "informasi"):
                        sev_label = "INFO"

                    st_dt = p.get("started_at")
                    st_str = st_dt.strftime("%d %b %H:%M:%S") if isinstance(st_dt, datetime) else str(st_dt or "—")

                    open_rows.append({
                        "id": p.get("id"),
                        "server": srv_h,
                        "sid": p.get("server_id"),
                        "group": p.get("group_name") or "",
                        "is_offline": bool(p.get("is_offline")),
                        "sev": sev_label,
                        "msg": msg_txt,
                        "tip": p.get("tip") or "—",
                        "started": st_str,
                        "dur": p.get("durasi") or format_duration(st_dt, now),
                        "ack_by": p.get("acknowledged_by"),
                        "is_ignored": bool(p.get("is_ignored")),
                        "ignored_by": p.get("ignored_by"),
                        "ignored_reason": p.get("ignored_reason"),
                        "count_24h": p.get("count_24h") or 1,
                    })

                # 4. Render Tabel 1: Insiden Terbuka (Open Problems)
                with open_container:
                    with ui.card().classes("w-full p-0 custom-card overflow-hidden"):
                        with ui.row().classes("w-full items-center justify-between p-3 border-b border-slate-800 bg-white/[0.015]"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("warning", size="18px").classes("text-amber-400")
                                ui.label(f"Insiden Terbuka ({len(open_rows)})").classes("text-xs font-bold text-white uppercase tracking-wide")
                            ui.label("Klik ikon mata untuk investigasi ke rincian server").classes("text-[11px] text-slate-400")

                        if not open_rows:
                            with ui.row().classes("w-full items-center justify-center p-8 text-slate-400 gap-2"):
                                ui.icon("check_circle", size="28px").classes("text-emerald-400")
                                ui.label("Tidak ada insiden terbuka yang sesuai kriteria filter. Semua sistem normal.").classes("text-xs text-slate-300")
                        else:
                            open_cols = [
                                {"name": "started", "label": "WAKTU MULAI", "field": "started", "align": "left"},
                                {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                                {"name": "sev", "label": "KEPARAHAN", "field": "sev", "align": "left"},
                                {"name": "msg", "label": "KEJADIAN / MASALAH", "field": "msg", "align": "left"},
                                {"name": "dur", "label": "DURASI", "field": "dur", "align": "left"},
                                {"name": "tip", "label": "PANDUAN SOLUSI", "field": "tip", "align": "left"},
                                {"name": "action", "label": "TINDAKAN", "field": "action", "align": "center"},
                            ]

                            tbl_open = ui.table(columns=open_cols, rows=open_rows, row_key="id").classes("w-full bg-slate-900").props("dense flat bordered")

                            tbl_open.add_slot("body-cell-server", """
                                <q-td :props="props">
                                    <div class="inline-flex items-center gap-1.5">
                                        <span class="dot" :class="props.row.is_offline ? 'down' : 'up'"></span>
                                        <a v-if="props.row.sid" :href="'/servers/' + props.row.sid" class="font-bold text-sky-400 hover:underline">
                                            {{ props.row.server }}
                                        </a>
                                        <span v-else class="font-semibold text-white">{{ props.row.server }}</span>
                                        <span v-if="props.row.group" class="badge badge-muted text-[8px] px-1 py-0.5">
                                            {{ props.row.group }}
                                        </span>
                                    </div>
                                </q-td>
                            """)

                            tbl_open.add_slot("body-cell-sev", """
                                <q-td :props="props">
                                    <div class="inline-flex flex-col items-start gap-1">
                                        <span class="badge" :class="props.row.sev === 'KRITIS' ? 'badge-danger' : (props.row.sev === 'GAWAT' ? 'badge-orange' : (props.row.sev === 'PERINGATAN' ? 'badge-warn' : 'badge-info'))" style="font-size:9px;padding:2px 6px;font-weight:700">
                                            {{ props.row.sev }}
                                        </span>
                                        <div v-if="props.row.is_ignored || props.row.ack_by" class="inline-flex items-center gap-1">
                                            <span v-if="props.row.is_ignored" class="badge badge-muted text-[7.5px] px-1 py-0.5" :title="'Diabaikan oleh ' + (props.row.ignored_by || 'operator')">
                                                DIABAIKAN
                                            </span>
                                            <span v-if="props.row.ack_by" class="badge badge-up text-[7.5px] px-1 py-0.5" :title="'Ditangani oleh ' + props.row.ack_by">
                                                ✓ DITANGANI
                                            </span>
                                        </div>
                                    </div>
                                </q-td>
                            """)

                            tbl_open.add_slot("body-cell-msg", """
                                <q-td :props="props">
                                    <div class="flex items-center gap-1.5 flex-wrap">
                                        <span class="text-xs font-medium text-slate-100">{{ props.row.msg }}</span>
                                        <span v-if="props.row.count_24h > 1" class="badge badge-muted text-[8px] px-1" title="Kejadian berulang dalam 24 jam terakhir">
                                            kambuh {{ props.row.count_24h }}×
                                        </span>
                                    </div>
                                </q-td>
                            """)

                            tbl_open.add_slot("body-cell-tip", """
                                <q-td :props="props" class="max-w-xs">
                                    <span class="text-[11px] text-slate-400 truncate block" :title="props.row.tip">
                                        {{ props.row.tip }}
                                    </span>
                                </q-td>
                            """)

                            tbl_open.add_slot("body-cell-action", """
                                <q-td :props="props" style="white-space: nowrap; width: 110px; text-align: center;">
                                    <div class="inline-flex items-center justify-center gap-1">
                                        <!-- Buka Rincian Server -->
                                        <a v-if="props.row.sid" :href="'/servers/' + props.row.sid + '?tab=prob'"
                                           class="btn btn-ghost btn-sm p-1 text-slate-400 hover:text-sky-400 rounded transition"
                                           title="Buka Rincian Server &amp; Remediasi">
                                            <q-icon name="visibility" size="14px" />
                                        </a>

                                        <!-- Tangani Insiden (ACK / Un-ACK) -->
                                        <button v-if="props.row.ack_by"
                                                class="btn btn-ghost btn-sm p-1 text-emerald-400 hover:text-emerald-300 rounded transition"
                                                :title="'Insiden Ditangani oleh ' + props.row.ack_by + ' (Klik untuk batal)'"
                                                @click="() => $parent.$emit('toggle_ack', props.row.id)">
                                            <q-icon name="check_circle" size="14px" />
                                        </button>
                                        <button v-else
                                                class="btn btn-ghost btn-sm p-1 text-slate-500 hover:text-emerald-400 rounded transition"
                                                title="Tangani Insiden (Tandai sedang ditangani operator)"
                                                @click="() => $parent.$emit('toggle_ack', props.row.id)">
                                            <q-icon name="radio_button_unchecked" size="14px" />
                                        </button>

                                        <!-- Abaikan / Pulihkan (Ignore) -->
                                        <button v-if="props.row.is_ignored"
                                                class="btn btn-ghost btn-sm p-1 text-amber-400 hover:text-amber-300 rounded transition"
                                                title="Pulihkan dari daftar abaikan"
                                                @click="() => $parent.$emit('toggle_ignore', props.row.id)">
                                            <q-icon name="notifications" size="14px" />
                                        </button>
                                        <button v-else
                                                class="btn btn-ghost btn-sm p-1 text-slate-500 hover:text-amber-400 rounded transition"
                                                title="Abaikan insiden (bisukan alarm)"
                                                @click="() => $parent.$emit('toggle_ignore', props.row.id)">
                                            <q-icon name="notifications_off" size="14px" />
                                        </button>
                                    </div>
                                </q-td>
                            """)

                            tbl_open.on("toggle_ack", lambda e: _toggle_ack(e.args))
                            tbl_open.on("toggle_ignore", lambda e: _toggle_ignore(e.args))

                # 5. Render Tabel 2: Riwayat Insiden Teratasi (Resolved Problems & MTTR)
                resolved_rows = []
                for p in resolved_list:
                    srv_h = p.get("hostname") or f"Server #{p.get('server_id')}"
                    msg_txt = p.get("message") or p.get("key") or "Gangguan sistem"
                    if q and q not in f"{srv_h} {msg_txt}".lower():
                        continue

                    st_dt = p.get("started_at")
                    res_dt = p.get("resolved_at")
                    st_str = st_dt.strftime("%d %b %H:%M") if isinstance(st_dt, datetime) else str(st_dt or "—")
                    res_str = res_dt.strftime("%d %b %H:%M") if isinstance(res_dt, datetime) else str(res_dt or "—")

                    sev_raw = (p.get("severity") or "warning").lower()
                    sev_label = "PERINGATAN"
                    if sev_raw in ("danger", "critical", "kritis"):
                        sev_label = "KRITIS"
                    elif sev_raw in ("average", "gawat"):
                        sev_label = "GAWAT"
                    elif sev_raw in ("info", "informasi"):
                        sev_label = "INFO"

                    res_type_str = "Pulih Normal"
                    if p.get("res_type") == "manual" or p.get("acknowledged_by"):
                        res_type_str = f"Ditangani ({p.get('acknowledged_by') or 'operator'})"

                    resolved_rows.append({
                        "id": p.get("id"),
                        "server": srv_h,
                        "sid": p.get("server_id"),
                        "sev": sev_label,
                        "comp": p.get("component") or "Sistem",
                        "msg": msg_txt,
                        "dur": p.get("durasi") or "—",
                        "period": f"{st_str} → {res_str}",
                        "res_type": res_type_str,
                    })

                with resolved_container:
                    with ui.card().classes("w-full p-0 custom-card overflow-hidden"):
                        with ui.row().classes("w-full items-center justify-between p-3 border-b border-slate-800 bg-white/[0.015] flex-wrap gap-2"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("history", size="18px").classes("text-slate-400")
                                ui.label(f"Riwayat Insiden Teratasi ({len(resolved_rows)})").classes("text-xs font-bold text-white uppercase tracking-wide")
                                ui.label("· Rekapitulasi insiden yang telah pulih otomatis atau ditangani operator").classes("text-[11px] text-slate-400")

                            with ui.row().classes("items-center gap-2"):
                                ui.html(f'<span class="badge badge-up text-[10px] px-2 py-0.5">{len(resolved_rows)} Teratasi</span>')
                                if avg_mttr_str != "—":
                                    ui.html(f'<span class="badge badge-info text-[10px] px-2 py-0.5">MTTR: {avg_mttr_str}</span>')
                                if manual_resolved_cnt > 0:
                                    ui.html(f'<span class="badge badge-muted text-[10px] px-2 py-0.5">{manual_resolved_cnt} ditangani operator</span>')

                        if not resolved_rows:
                            with ui.row().classes("w-full items-center justify-center p-8 text-slate-400 gap-2"):
                                ui.icon("schedule", size="24px").classes("text-slate-500")
                                ui.label("Belum ada riwayat insiden teratasi dalam 24 jam terakhir.").classes("text-xs text-slate-400")
                        else:
                            res_cols = [
                                {"name": "period", "label": "WAKTU (MULAI → SELESAI)", "field": "period", "align": "left"},
                                {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                                {"name": "sev", "label": "KEPARAHAN", "field": "sev", "align": "left"},
                                {"name": "comp", "label": "KOMPONEN", "field": "comp", "align": "left"},
                                {"name": "msg", "label": "DESKRIPSI INSIDEN", "field": "msg", "align": "left"},
                                {"name": "dur", "label": "DURASI", "field": "dur", "align": "left"},
                                {"name": "res_type", "label": "RESOLUSI", "field": "res_type", "align": "left"},
                                {"name": "action", "label": "TINDAKAN", "field": "action", "align": "center"},
                            ]

                            tbl_res = ui.table(columns=res_cols, rows=resolved_rows, row_key="id").classes("w-full bg-slate-900").props("dense flat bordered")

                            tbl_res.add_slot("body-cell-server", """
                                <q-td :props="props">
                                    <a v-if="props.row.sid" :href="'/servers/' + props.row.sid" class="font-bold text-sky-400 hover:underline">
                                        {{ props.row.server }}
                                    </a>
                                    <span v-else class="text-white">{{ props.row.server }}</span>
                                </q-td>
                            """)

                            tbl_res.add_slot("body-cell-sev", """
                                <q-td :props="props">
                                    <span class="badge" :class="props.row.sev === 'KRITIS' ? 'badge-danger' : (props.row.sev === 'GAWAT' ? 'badge-orange' : (props.row.sev === 'PERINGATAN' ? 'badge-warn' : 'badge-info'))" style="font-size:8.5px;padding:1px 5px">
                                        {{ props.row.sev }}
                                    </span>
                                </q-td>
                            """)

                            tbl_res.add_slot("body-cell-res_type", """
                                <q-td :props="props">
                                    <span class="badge" :class="props.row.res_type.includes('Ditangani') ? 'badge-warn' : 'badge-up'" style="font-size:9px;padding:1px 6px">
                                        ✓ {{ props.row.res_type }}
                                    </span>
                                </q-td>
                            """)

                            tbl_res.add_slot("body-cell-action", """
                                <q-td :props="props" style="white-space: nowrap; width: 60px; text-align: center;">
                                    <a v-if="props.row.sid" :href="'/servers/' + props.row.sid"
                                       class="btn btn-ghost btn-sm p-1 text-slate-400 hover:text-sky-400 rounded transition"
                                       title="Buka Rincian Server">
                                        <q-icon name="visibility" size="14px" />
                                    </a>
                                </q-td>
                            """)

            _reload_problems()
