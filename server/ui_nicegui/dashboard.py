"""
Modul Dashboard Pemantauan Pusat (Network Operations Center Overview)
====================================================================
Menyajikan identitas branding organisasi resmi (dash-org-header),
banner pemeliharaan aktif, bilah 3-kolom operasi asimetris (Total Server,
Zabbix Severity Strip, & Waktu Sistem), tabel insiden terkini berkepadatan tinggi,
serta kartu armada server terpadu dengan toggle mode Tabel / Grid NOC.
"""

from datetime import datetime
import json
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy import func

from config import settings
from models import AuditLog, MaintenanceWindow, ProbeTarget, Server, ServerProblem, SystemSetting, SystemSnapshot
from .auth import get_auth_user
from .common import format_bytes, format_duration, get_db, get_now_local, get_system_tz_label, notify_success
from .layout import render_layout


def _get_disk_pct(snap) -> float:
    """Mengambil persentase pemakaian disk partisi root '/' dari snapshot."""
    if not snap or not snap.disks:
        return 0.0
    try:
        d_list = json.loads(snap.disks) if isinstance(snap.disks, str) else snap.disks
        if d_list and isinstance(d_list, list):
            root_d = next((d for d in d_list if d.get("mount") == "/"), d_list[0])
            return float(root_d.get("pct", 0.0))
    except Exception:
        pass
    return 0.0


def get_branding(db) -> dict:
    """Mengambil setelan branding organisasi dari database."""
    defaults = {
        "org_name": "",
        "org_unit": "",
        "dash_motd": "",
        "show_motd": False,
        "logo_url": "",
    }
    try:
        row = db.query(SystemSetting).filter(SystemSetting.key == "branding").first()
        if row and row.value:
            data = json.loads(row.value)
            defaults["org_name"] = str(data.get("org_name", "") or "").strip()
            defaults["org_unit"] = str(data.get("org_unit", "") or "").strip()
            defaults["dash_motd"] = str(data.get("dash_motd", "") or "").strip()
            defaults["show_motd"] = bool(data.get("show_motd", False))
            defaults["logo_url"] = str(data.get("logo_url", "") or "").strip()
    except Exception:
        pass
    return defaults


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

        with render_layout(request, user, active_tab="dashboard"):
            dash_container = ui.column().classes("w-full gap-3")

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

            view_state = {"mode": "table", "search": "", "group": ""}

            def _refresh_dashboard_data():
                dash_container.clear()
                with get_db(session_factory) as db:
                    brand = get_branding(db)
                    servers = db.query(Server).all()
                    now = datetime.utcnow()
                    online_count = sum(1 for s in servers if s.last_seen and (now - s.last_seen).total_seconds() < 45)
                    total_servers = len(servers)
                    down_count = total_servers - online_count

                    # Pemeliharaan aktif
                    active_maint = (
                        db.query(MaintenanceWindow)
                        .filter(MaintenanceWindow.is_active == True)
                        .filter(MaintenanceWindow.start_time <= now)
                        .filter(MaintenanceWindow.end_time >= now)
                        .all()
                    )

                    # Insiden & Masalah terbuka
                    open_problems = (
                        db.query(ServerProblem)
                        .filter(ServerProblem.resolved_at == None)
                        .order_by(ServerProblem.started_at.desc())
                        .all()
                    )
                    danger_cnt = sum(1 for p in open_problems if p.severity in ("danger", "critical") and not p.is_ignored)
                    avg_cnt = sum(1 for p in open_problems if p.severity in ("average", "gawat") and not p.is_ignored)
                    warn_cnt = sum(1 for p in open_problems if p.severity in ("warning", "peringatan") and not p.is_ignored)
                    info_cnt = sum(1 for p in open_problems if p.severity in ("info", "informasi") and not p.is_ignored)
                    ign_cnt = sum(1 for p in open_problems if p.is_ignored)
                    total_active = danger_cnt + avg_cnt + warn_cnt + info_cnt

                    # Snapshot terbaru via subquery terindeks
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
                    all_groups = sorted(list({s.group_name for s in servers if s.group_name}))

                with dash_container:
                    # ---------------------------------------------------------
                    # 1. Header Identitas Organisasi Resmi (dash-org-header)
                    # ---------------------------------------------------------
                    if brand.get("org_name"):
                        logo_html = f'<img src="{brand["logo_url"]}" alt="Logo" style="max-height:56px;max-width:120px;width:auto;object-fit:contain;filter:drop-shadow(0 2px 8px rgba(0,0,0,0.4))">' if brand.get("logo_url") else """
                        <svg width="44" height="44" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" style="color:var(--blue);filter:drop-shadow(0 0 10px rgba(56,189,248,0.4))">
                          <path d="M12 2L2 7l10 5 10-5-10-5z"></path>
                          <path d="M2 17l10 5 10-5"></path>
                          <path d="M2 12l10 5 10-5"></path>
                        </svg>
                        """
                        motd_html = f'<div style="font-size:12px;color:var(--blue);margin-top:6px;font-weight:500">(&ldquo;{brand["dash_motd"]}&rdquo;)</div>' if (brand.get("show_motd") and brand.get("dash_motd")) else ""
                        ui.html(f"""
                        <div class="dash-org-header" style="text-align:center;margin:0 auto 12px auto;display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%">
                          <div class="dash-brand-wrap" style="position:relative;display:inline-flex;flex-direction:column;justify-content:center;gap:3px;text-align:center;min-height:56px;height:auto;max-width:calc(100% - 240px);padding:2px 0">
                            <div class="dash-brand-logo-box" style="position:absolute;right:calc(100% + 18px);top:50%;transform:translateY(-50%);display:flex;align-items:center;justify-content:flex-end;flex-shrink:0">
                              {logo_html}
                            </div>
                            <div class="dash-brand-title" style="font-size:18px;font-weight:800;letter-spacing:1.5px;color:var(--text-heading);text-transform:uppercase;line-height:1;margin:0">PANTAU SERVER</div>
                            <div style="font-size:14px;font-weight:700;color:var(--text-bright);letter-spacing:0.2px;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{brand['org_name']}</div>
                            <div style="font-size:12px;color:var(--dim);font-style:italic;line-height:1.35;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">{brand.get('org_unit') or 'Bidang Aplikasi dan Informatika'}</div>
                          </div>
                          {motd_html}
                        </div>
                        """).classes("w-full")
                    else:
                        ui.html("""
                        <div class="topbar">
                          <div>
                            <h2 style="font-size:18px;margin:0">Dashboard Pemantauan Pusat</h2>
                            <div style="font-size:12px;color:var(--dim);margin-top:2px">Ringkasan kondisi kesehatan seluruh server klien &amp; telemetri operasional NOC terpusat.</div>
                          </div>
                        </div>
                        """).classes("w-full")

                    # ---------------------------------------------------------
                    # 2. Banner Pemeliharaan Terencana Aktif (Bila Ada)
                    # ---------------------------------------------------------
                    if active_maint:
                        titles = ", ".join(m.title for m in active_maint if m.title)
                        ui.html(f"""
                        <div class="dash-maintenance-banner" style="background:rgba(234,179,8,0.1);border:1px solid rgba(234,179,8,0.3);border-radius:6px;padding:7px 12px;margin-bottom:8px;display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap">
                          <div style="display:flex;align-items:center;gap:8px">
                            <span class="badge badge-warn" style="font-size:9.5px;font-weight:700;padding:2px 6px">PEMELIHARAAN AKTIF</span>
                            <span style="font-size:12px;color:var(--text-bright)">Terdapat <strong>{len(active_maint)} jendela pemeliharaan aktif</strong>: <span style="color:var(--yellow)">{titles}</span>. Notifikasi alarm terkait ditekan terencana.</span>
                          </div>
                          <a href="/maintenance" class="btn btn-sm btn-ghost" style="color:var(--yellow);text-decoration:none">Kelola Jadwal &rarr;</a>
                        </div>
                        """).classes("w-full")

                    # ---------------------------------------------------------
                    # 3. Bilah 3-Kolom Operasi Asimetris (dash-kpi-grid)
                    # ---------------------------------------------------------
                    now_local = get_now_local()
                    days_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
                    months_id = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
                    day_name = days_id[now_local.weekday()]
                    date_str = f"{now_local.day:02d} {months_id[now_local.month - 1]} {now_local.year}"
                    clock_str = now_local.strftime("%H:%M:%S")
                    tz_label = get_system_tz_label()

                    prob_border = "var(--red)" if danger_cnt > 0 else ("var(--orange)" if avg_cnt > 0 else ("var(--yellow)" if warn_cnt > 0 else "var(--green)"))

                    ui.html(f"""
                    <div class="dash-kpi-grid" style="display:grid;grid-template-columns:minmax(190px, 220px) 1fr minmax(260px, 290px);gap:8px;width:100%;margin-bottom:8px;align-items:stretch">
                      <!-- Card 1: Total Server -->
                      <a href="/servers" id="kpi-card-total" class="card kpi-link-card" style="margin:0;padding:8px 14px;display:flex;flex-direction:column;justify-content:space-between;border-left:3px solid var(--blue);text-decoration:none;color:inherit;cursor:pointer">
                        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
                          <div style="font-size:10.5px;color:var(--dim);text-transform:uppercase;letter-spacing:0.04em;font-weight:700;display:flex;align-items:center;gap:5px">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="color:var(--blue);flex-shrink:0"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg>
                            <span>Total Server</span>
                          </div>
                        </div>
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
                          <div style="display:flex;align-items:baseline;gap:4px">
                            <span style="font-size:20px;font-weight:800;line-height:1;color:var(--text-bright);font-family:ui-monospace,monospace">{total_servers}</span>
                            <span style="font-size:11px;color:var(--dim);font-weight:500">host</span>
                          </div>
                          <div style="display:flex;gap:4px;align-items:center">
                            <span class="badge badge-up" style="font-size:10px;padding:1px 6px;font-weight:600">{online_count} up</span>
                            <span class="badge {'badge-danger' if down_count > 0 else 'badge-muted'}" style="font-size:10px;padding:1px 6px;font-weight:600">{down_count} down</span>
                          </div>
                        </div>
                      </a>

                      <!-- Card 2: Insiden Aktif (Zabbix Severity Strip) -->
                      <div class="card" id="kpi-card-prob" style="margin:0;padding:8px 14px;display:flex;flex-direction:column;justify-content:space-between;border-left:3px solid {prob_border}">
                        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
                          <div style="font-size:10.5px;color:var(--dim);text-transform:uppercase;letter-spacing:0.04em;font-weight:700;display:flex;align-items:center;gap:5px">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" style="color:var(--yellow);flex-shrink:0"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
                            <span>Insiden Aktif</span>
                          </div>
                          <span style="font-size:10px;color:var(--dim)">{total_active} insiden</span>
                        </div>
                        <div class="zbx-severity-strip" style="display:flex;flex-direction:row;gap:4px;width:100%;align-items:stretch">
                          <div class="zbx-sev-tile zbx-tile-danger {'is-active' if danger_cnt > 0 else ''}" onclick="window.location.href='/problems'" style="flex:1;min-width:42px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px 2px;cursor:pointer">
                            <span class="zbx-sev-count">{danger_cnt}</span>
                            <span class="zbx-sev-label">Kritis</span>
                          </div>
                          <div class="zbx-sev-tile zbx-tile-average {'is-active' if avg_cnt > 0 else ''}" onclick="window.location.href='/problems'" style="flex:1;min-width:42px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px 2px;cursor:pointer">
                            <span class="zbx-sev-count">{avg_cnt}</span>
                            <span class="zbx-sev-label">Gawat</span>
                          </div>
                          <div class="zbx-sev-tile zbx-tile-warning {'is-active' if warn_cnt > 0 else ''}" onclick="window.location.href='/problems'" style="flex:1;min-width:42px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px 2px;cursor:pointer">
                            <span class="zbx-sev-count">{warn_cnt}</span>
                            <span class="zbx-sev-label">Peringatan</span>
                          </div>
                          <div class="zbx-sev-tile zbx-tile-info {'is-active' if info_cnt > 0 else ''}" onclick="window.location.href='/problems'" style="flex:1;min-width:42px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px 2px;cursor:pointer">
                            <span class="zbx-sev-count">{info_cnt}</span>
                            <span class="zbx-sev-label">Info</span>
                          </div>
                          <div class="zbx-sev-tile zbx-tile-ignored {'is-active' if ign_cnt > 0 else ''}" onclick="window.location.href='/problems'" style="flex:1;min-width:42px;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:4px 2px;cursor:pointer">
                            <span class="zbx-sev-count">{ign_cnt}</span>
                            <span class="zbx-sev-label">Diabaikan</span>
                          </div>
                        </div>
                      </div>

                      <!-- Card 3: Waktu Sistem (Hari, Tanggal, Jam Digital) -->
                      <div class="card dash-clock-card" id="dashClockWidget" style="margin:0;padding:8px 14px;display:flex;flex-direction:column;justify-content:space-between;border-left:3px solid var(--green)">
                        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:3px">
                          <div style="font-size:10.5px;color:var(--dim);text-transform:uppercase;letter-spacing:0.04em;font-weight:700;display:flex;align-items:center;gap:5px">
                            <span class="dash-clock-live-ping"></span>
                            <span>Waktu Sistem</span>
                          </div>
                          <span class="dash-clock-tz">{tz_label}</span>
                        </div>
                        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
                          <div class="dash-clock-cal">
                            <div class="dash-clock-day">{day_name}</div>
                            <div class="dash-clock-date">{date_str}</div>
                          </div>
                          <div class="dash-clock-divider"></div>
                          <div class="dash-clock-digits">
                            <span id="dashClockTimeLive" class="font-mono">{clock_str}</span>
                          </div>
                        </div>
                      </div>
                    </div>
                    """).classes("w-full")

                    # ---------------------------------------------------------
                    # 4. Kartu Insiden Terkini (Masalah Terbuka)
                    # ---------------------------------------------------------
                    with ui.card().classes("w-full p-0 custom-card overflow-hidden"):
                        with ui.row().classes("w-full items-center justify-between p-3 border-b border-slate-800 bg-white/[0.015]"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("report_problem", size="18px").classes("text-amber-400")
                                ui.label("Insiden Terkini (Masalah Terbuka)").classes("text-xs font-bold text-white uppercase tracking-wide")
                            ui.button("Pusat Insiden →", on_click=lambda: ui.navigate.to("/problems")).props(
                                "dense flat no-caps size=sm color=primary"
                            ).classes("text-xs")

                        if not open_problems:
                            with ui.row().classes("w-full items-center justify-center p-6 text-slate-400 gap-2"):
                                ui.icon("check_circle", size="20px").classes("text-emerald-400")
                                ui.label("Tidak ada insiden terbuka saat ini. Seluruh sistem beroperasi normal.").classes("text-xs")
                        else:
                            prob_cols = [
                                {"name": "started", "label": "WAKTU", "field": "started", "align": "left"},
                                {"name": "server", "label": "SERVER", "field": "server", "align": "left"},
                                {"name": "sev", "label": "KEPARAHAN", "field": "sev", "align": "left"},
                                {"name": "msg", "label": "MASALAH / PEMICU", "field": "msg", "align": "left"},
                                {"name": "dur", "label": "DURASI", "field": "dur", "align": "left"},
                                {"name": "action", "label": "TINDAKAN", "field": "action", "align": "left"},
                            ]
                            prob_rows = []
                            for p in open_problems[:6]:
                                prob_rows.append({
                                    "id": p.id,
                                    "started": p.started_at.strftime("%H:%M:%S") if p.started_at else "—",
                                    "server": srv_map.get(p.server_id, f"Server #{p.server_id}"),
                                    "sid": p.server_id,
                                    "sev": p.severity.upper() if p.severity else "PERINGATAN",
                                    "msg": p.message or p.service_name or "Gangguan terdeteksi",
                                    "dur": format_duration(p.started_at, now),
                                })

                            p_table = ui.table(columns=prob_cols, rows=prob_rows, row_key="id").classes("w-full")
                            p_table.add_slot("body-cell-server", """
                                <q-td :props="props">
                                    <a :href="'/servers/' + props.row.sid" class="font-bold text-sky-400 hover:underline">
                                        {{ props.row.server }}
                                    </a>
                                </q-td>
                            """)
                            p_table.add_slot("body-cell-sev", """
                                <q-td :props="props">
                                    <span class="badge" :class="props.row.sev === 'DANGER' || props.row.sev === 'CRITICAL' ? 'badge-danger' : (props.row.sev === 'AVERAGE' || props.row.sev === 'GAWAT' ? 'badge-warn' : (props.row.sev === 'WARNING' ? 'badge-warn' : 'badge-muted'))" style="font-size:9.5px;padding:1px 6px">
                                        {{ props.row.sev }}
                                    </span>
                                </q-td>
                            """)
                            p_table.add_slot("body-cell-action", """
                                <q-td :props="props">
                                    <a :href="'/servers/' + props.row.sid + '?tab=prob'"
                                       class="inline-flex items-center gap-1 text-[11px] font-semibold text-sky-400 hover:text-sky-300 px-2 py-0.5 rounded hover:bg-sky-500/10 transition">
                                        <span>Detail</span>
                                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"></polyline></svg>
                                    </a>
                                </q-td>
                            """)

                    # ---------------------------------------------------------
                    # 5. Kartu Armada Server (Tabel / Grid NOC)
                    # ---------------------------------------------------------
                    with ui.card().classes("w-full p-0 custom-card overflow-hidden"):
                        with ui.row().classes("w-full items-center justify-between p-3 border-b border-slate-800 bg-white/[0.015] flex-wrap gap-2"):
                            with ui.row().classes("items-center gap-2"):
                                ui.icon("dns", size="18px").classes("text-blue-400")
                                ui.label("Armada Server (Ringkasan Kesehatan)").classes("text-xs font-bold text-white uppercase tracking-wide")

                            # Kontrol Filter & Switcher
                            with ui.row().classes("items-center gap-2"):
                                s_inp = ui.input(placeholder="Cari server / IP...").props("dense outlined dark").classes("w-44 text-xs")
                                s_inp.set_value(view_state["search"])

                                g_sel = ui.select(["Semua Grup"] + all_groups, value=view_state["group"] or "Semua Grup").props("dense outlined dark options-dense").classes("w-36 text-xs")

                                with ui.row().classes("view-switch-group"):
                                    btn_tbl = ui.button(icon="table_rows", on_click=lambda: _set_view("table")).props("dense flat size=sm").classes("view-btn " + ("active" if view_state["mode"] == "table" else ""))
                                    btn_grd = ui.button(icon="grid_view", on_click=lambda: _set_view("grid")).props("dense flat size=sm").classes("view-btn " + ("active" if view_state["mode"] == "grid" else ""))

                        fleet_body = ui.column().classes("w-full p-3")

                        def _set_view(m: str):
                            view_state["mode"] = m
                            _render_fleet_items()

                        def _on_filter_change():
                            view_state["search"] = s_inp.value.strip().lower()
                            view_state["group"] = "" if g_sel.value == "Semua Grup" else g_sel.value
                            _render_fleet_items()

                        s_inp.on("update:model-value", lambda: _on_filter_change())
                        g_sel.on("update:model-value", lambda: _on_filter_change())

                        def _render_fleet_items():
                            fleet_body.clear()
                            q = view_state["search"]
                            grp = view_state["group"]

                            filtered_servers = []
                            for s in servers:
                                if grp and s.group_name != grp:
                                    continue
                                if q and (q not in s.hostname.lower() and q not in (s.ip_address or "").lower() and q not in (s.notes or "").lower()):
                                    continue
                                filtered_servers.append(s)

                            with fleet_body:
                                if not filtered_servers:
                                    with ui.row().classes("w-full justify-center p-6 text-slate-500 text-xs"):
                                        ui.label("Tidak ada server yang cocok dengan kriteria filter.")
                                    return

                                if view_state["mode"] == "grid":
                                    # Mode Grid NOC
                                    with ui.row().classes("noc-grid w-full"):
                                        for s in filtered_servers:
                                            is_up = bool(s.last_seen and (now - s.last_seen).total_seconds() < 45)
                                            snap = latest_snaps.get(s.id)
                                            cpu_val = snap.cpu if snap and snap.cpu is not None else 0.0
                                            mem_val = round(snap.mem_used / snap.mem_total * 100, 1) if (snap and snap.mem_total) else 0.0
                                            disk_val = _get_disk_pct(snap)

                                            card_status_cls = "is-healthy" if is_up else "is-offline"
                                            with ui.element("div").classes(f"server-card {card_status_cls}").on("click", lambda sid=s.id: ui.navigate.to(f"/servers/{sid}")):
                                                with ui.row().classes("w-full items-center justify-between"):
                                                    with ui.row().classes("items-center gap-1.5"):
                                                        ui.html(f'<span class="dot {"dot-up" if is_up else "dot-down"}"></span>')
                                                        ui.label(s.hostname).classes("text-xs font-bold text-white")
                                                    ui.badge(s.group_name or "DEFAULT", color="slate-800").classes("text-[9px] font-mono border border-slate-700")

                                                ui.label(s.ip_address).classes("text-[10.5px] font-mono text-slate-400")

                                                # Mini Meters (CPU, RAM, Disk)
                                                with ui.column().classes("w-full gap-1 mt-1 text-[10px]"):
                                                    with ui.row().classes("w-full justify-between"):
                                                        ui.label("CPU").classes("text-slate-400 font-medium")
                                                        ui.label(f"{cpu_val:.1f}%").classes("font-mono text-slate-200")
                                                    ui.html(f'<div class="meter-track"><div class="meter-bar {"green" if cpu_val < 70 else ("yellow" if cpu_val < 90 else "red")}" style="width:{min(cpu_val, 100)}%"></div></div>')

                                                    with ui.row().classes("w-full justify-between mt-1"):
                                                        ui.label("RAM").classes("text-slate-400 font-medium")
                                                        ui.label(f"{mem_val:.1f}%").classes("font-mono text-slate-200")
                                                    ui.html(f'<div class="meter-track"><div class="meter-bar {"green" if mem_val < 70 else ("yellow" if mem_val < 90 else "red")}" style="width:{min(mem_val, 100)}%"></div></div>')
                                else:
                                    # Mode Tabel Kanonikal (#dash-server-table)
                                    fleet_cols = [
                                        {"name": "status", "label": "STATUS", "field": "status", "align": "left"},
                                        {"name": "hostname", "label": "NAMA SERVER", "field": "hostname", "align": "left"},
                                        {"name": "group", "label": "LINGKUP", "field": "group", "align": "left"},
                                        {"name": "ip", "label": "PLATFORM & IP", "field": "ip", "align": "left"},
                                        {"name": "cpu", "label": "CPU", "field": "cpu", "align": "left"},
                                        {"name": "ram", "label": "RAM", "field": "ram", "align": "left"},
                                        {"name": "disk", "label": "DISK", "field": "disk", "align": "left"},
                                        {"name": "action", "label": "AKSI", "field": "action", "align": "left"},
                                    ]
                                    fleet_rows = []
                                    for s in filtered_servers:
                                        is_up = bool(s.last_seen and (now - s.last_seen).total_seconds() < 45)
                                        snap = latest_snaps.get(s.id)
                                        cpu_p = snap.cpu if snap and snap.cpu is not None else 0.0
                                        mem_p = round(snap.mem_used / snap.mem_total * 100, 1) if (snap and snap.mem_total) else 0.0
                                        disk_p = _get_disk_pct(snap)
                                        fleet_rows.append({
                                            "id": s.id,
                                            "is_up": is_up,
                                            "hostname": s.hostname,
                                            "group": s.group_name or "Umum",
                                            "ip": s.ip_address,
                                            "cpu": cpu_p,
                                            "ram": mem_p,
                                            "disk": disk_p,
                                        })

                                    s_table = ui.table(columns=fleet_cols, rows=fleet_rows, row_key="id").classes("w-full")
                                    s_table.add_slot("body-cell-status", """
                                        <q-td :props="props">
                                            <span class="badge" :class="props.row.is_up ? 'badge-up' : 'badge-danger'" style="font-size:9.5px;padding:1px 6px">
                                                {{ props.row.is_up ? 'UP' : 'DOWN' }}
                                            </span>
                                        </q-td>
                                    """)
                                    s_table.add_slot("body-cell-hostname", """
                                        <q-td :props="props">
                                            <a :href="'/servers/' + props.row.id" class="font-bold text-sky-400 hover:underline">
                                                {{ props.row.hostname }}
                                            </a>
                                        </q-td>
                                    """)
                                    s_table.add_slot("body-cell-ip", """
                                        <q-td :props="props">
                                            <span class="font-mono text-slate-300 text-[11px]">{{ props.row.ip }}</span>
                                        </q-td>
                                    """)
                                    s_table.add_slot("body-cell-cpu", """
                                        <q-td :props="props">
                                            <div class="flex items-center gap-1.5">
                                                <span class="font-mono text-[11px] w-9">{{ props.row.cpu.toFixed(1) }}%</span>
                                                <div class="meter-mini-track">
                                                    <div class="meter-mini-bar" :class="props.row.cpu < 70 ? 'green' : (props.row.cpu < 90 ? 'yellow' : 'red')" :style="'width:' + Math.min(props.row.cpu, 100) + '%'"></div>
                                                </div>
                                            </div>
                                        </q-td>
                                    """)
                                    s_table.add_slot("body-cell-ram", """
                                        <q-td :props="props">
                                            <div class="flex items-center gap-1.5">
                                                <span class="font-mono text-[11px] w-9">{{ props.row.ram.toFixed(1) }}%</span>
                                                <div class="meter-mini-track">
                                                    <div class="meter-mini-bar" :class="props.row.ram < 70 ? 'green' : (props.row.ram < 90 ? 'yellow' : 'red')" :style="'width:' + Math.min(props.row.ram, 100) + '%'"></div>
                                                </div>
                                            </div>
                                        </q-td>
                                    """)
                                    s_table.add_slot("body-cell-disk", """
                                        <q-td :props="props">
                                            <div class="flex items-center gap-1.5">
                                                <span class="font-mono text-[11px] w-9">{{ props.row.disk.toFixed(1) }}%</span>
                                                <div class="meter-mini-track">
                                                    <div class="meter-mini-bar" :class="props.row.disk < 70 ? 'green' : (props.row.disk < 90 ? 'yellow' : 'red')" :style="'width:' + Math.min(props.row.disk, 100) + '%'"></div>
                                                </div>
                                            </div>
                                        </q-td>
                                    """)
                                    s_table.add_slot("body-cell-action", """
                                        <q-td :props="props">
                                            <a :href="'/servers/' + props.row.id" class="btn btn-sm btn-ghost" style="color:var(--blue);text-decoration:none;padding:1px 6px;font-size:11px">
                                                Detail &rarr;
                                            </a>
                                        </q-td>
                                    """)

                        _render_fleet_items()

            _refresh_dashboard_data()
            ui.timer(10.0, _refresh_dashboard_data)

            # Timer sinkronisasi jam digital Waktu Sistem tiap 1 detik
            def _tick_clock():
                now_loc = get_now_local()
                ui.run_javascript(f"""
                const el = document.getElementById('dashClockTimeLive');
                if (el) el.innerText = '{now_loc.strftime("%H:%M:%S")}';
                """)

            ui.timer(1.0, _tick_clock)
