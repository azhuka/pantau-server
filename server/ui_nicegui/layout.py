"""
Komponen Layout Induk Antarmuka NOC (Header Sticky Interaktif & Menu Model Sidebar)
===================================================================================
Menyediakan tata letak baku Pusat Operasi Jaringan (NOC) yang profesional,
dilengkapi header sticky interaktif yang tetap berada di atas layar saat di-scroll,
jam digital real-time dinamis sesuai zona waktu server lokal, tombol toggle bilah sisi,
serta menu model sidebar (Left Drawer) berarsitektur kanonikal 230px dengan ikon vektor,
kelompok navigasi, penanda halaman aktif, dan footer status pengguna.
"""

from datetime import datetime
from nicegui import ui
from starlette.requests import Request

from config import settings
from models import User
from .common import apply_noc_head_styles, get_now_local, get_system_tz_label


def render_layout(request: Request, user: User, active_tab: str = "servers"):
    """Render layout umum NOC (Header Sticky Interaktif dan Menu Model Sidebar)."""
    ui.dark_mode().enable()
    apply_noc_head_styles()

    is_admin = bool(user and (user.is_master_admin() or user.has_perm("can_manage_users")))
    username = user.username if user else "Tamu"
    role_display = user.role_display() if user else "Viewer"
    tz_label = get_system_tz_label()
    curr_time = get_now_local().strftime("%H:%M:%S")

    # -------------------------------------------------------------------------
    # 1. Top Header NOC Sticky (Tetap Berada di Atas Saat di-Scroll)
    # -------------------------------------------------------------------------
    with ui.header().classes(
        "bg-slate-900/95 backdrop-blur border-b border-slate-800 text-white px-5 py-2 flex items-center justify-between sticky top-0 z-50 shadow-md"
    ):
        # Sisi Kiri: Tombol Toggle Sidebar & Brand
        with ui.row().classes("items-center gap-3"):
            # Tombol Toggle Bilah Sisi (Menu Hamburger)
            btn_toggle = ui.button(icon="menu").props("flat dense round color=slate-4")
            btn_toggle.tooltip("Tampilkan / Sembunyikan Menu Sidebar")

            ui.icon("dns", size="22px").classes("text-blue-400")
            with ui.column().classes("gap-0"):
                ui.label("PANTAU SERVER").classes("text-base font-bold tracking-wider leading-tight text-white")
                ui.label("NOC MANDIRI · DINAS KOMINFO BARRU").classes("text-[10px] text-slate-400 font-mono")
            ui.badge("NOC", color="blue-9").classes("text-[10px] font-bold px-1.5 py-0.5 ml-1")

        # Sisi Tengah: Jam Digital Real-Time Dinamis (WITA/WIB)
        with ui.row().classes(
            "items-center gap-2 bg-slate-950/70 px-3 py-1 rounded border border-slate-800 font-mono text-xs flex"
        ):
            ui.icon("schedule", size="16px").classes("text-emerald-400")
            lbl_time = ui.label("--:--:--").classes("font-bold text-emerald-400 text-sm")
            lbl_tz = ui.badge(tz_label, color="slate-800").classes(
                "text-[9px] text-slate-400 border border-slate-700 font-bold"
            )
            lbl_date = ui.label("---, -- --- ----").classes("text-[11px] text-slate-400 ml-1")

            def _tick_clock():
                now = get_now_local()
                lbl_time.set_text(now.strftime("%H:%M:%S"))
                days_id = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
                months_id = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
                d_name = days_id[now.weekday()]
                m_name = months_id[now.month - 1]
                lbl_date.set_text(f"{d_name}, {now.day:02d} {m_name} {now.year}")

            ui.timer(1.0, _tick_clock)
            _tick_clock()

        # Sisi Kanan: Versi Sistem, Profil Pengguna, & Logout
        with ui.row().classes("items-center gap-3"):
            ui.badge(f"v{settings.APP_VERSION}", color="slate-800").classes(
                "text-slate-400 text-[11px] font-mono border border-slate-700"
            )
            if user:
                with ui.row().classes(
                    "items-center gap-1.5 bg-slate-800/80 hover:bg-slate-700/80 cursor-pointer px-2.5 py-1 rounded border border-slate-700 transition"
                ).on("click", lambda: ui.navigate.to("/profile")):
                    ui.icon("account_circle", size="18px").classes("text-slate-300")
                    ui.label(user.username).classes("text-xs font-semibold text-slate-200 font-mono")
                    ui.badge(user.role_display().upper(), color="slate-700").classes(
                        "text-[9.5px] font-bold text-slate-300 ml-1"
                    )
                    ui.tooltip("Kelola Profil & Keamanan 2FA").classes("bg-slate-900 border border-slate-700 text-xs")

                ui.button("Keluar", icon="logout", on_click=lambda: ui.navigate.to("/logout")).props(
                    "dense flat no-caps size=sm color=negative"
                ).classes("text-xs")

    # -------------------------------------------------------------------------
    # 2. Menu Model Sidebar (Left Drawer Kanonikal NOC)
    # -------------------------------------------------------------------------
    with ui.left_drawer(value=True, fixed=True, bordered=True).classes(
        "bg-[#0e1526] border-r border-slate-800 text-white p-0 flex flex-col justify-between"
    ).props("width=230 breakpoint=640 show-if-above") as drawer:
        btn_toggle.on("click", drawer.toggle)

        # Helper navigasi aktif
        def _act(tab_name: str) -> str:
            return "active" if active_tab == tab_name else ""

        users_item_html = f"""
        <a href="/users" class="nav-link {_act('users')}" title="Manajemen Pengguna">
          <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg></span>
          <span class="nav-label">Pengguna</span>
        </a>
        """ if is_admin else ""

        badge_role_color = "#f87171" if (user and user.is_master_admin()) else ("#38bdf8" if (user and user.is_operator()) else "#94a3b8")
        badge_role_bg = "rgba(239,68,68,0.15)" if (user and user.is_master_admin()) else ("rgba(56,189,248,0.15)" if (user and user.is_operator()) else "rgba(148,163,184,0.15)")
        badge_role_border = "rgba(239,68,68,0.3)" if (user and user.is_master_admin()) else ("rgba(56,189,248,0.3)" if (user and user.is_operator()) else "rgba(148,163,184,0.3)")

        sidebar_content_html = f"""
        <div style="display:flex;flex-direction:column;height:100%;justify-content:space-between">
          <nav class="sidebar-nav" style="padding:12px 10px;flex:1;overflow-y:auto">
            <div class="nav-section" style="padding:6px 14px 4px;font-size:10px;font-weight:700;color:var(--dim-subtle);text-transform:uppercase;letter-spacing:1px">Menu Utama</div>

            <a href="/dashboard" class="nav-link {_act('dashboard')}" title="Dashboard Pemantauan Pusat">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg></span>
              <span class="nav-label">Dashboard</span>
            </a>

            <a href="/servers" class="nav-link {_act('servers')}" title="Daftar Server Terpadu">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg></span>
              <span class="nav-label">Daftar Server</span>
            </a>

            <a href="/problems" class="nav-link {_act('problems')}" title="Pusat Insiden &amp; Gangguan">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg></span>
              <span class="nav-label">Insiden &amp; Masalah</span>
            </a>

            <a href="/probing" class="nav-link {_act('probing')}" title="Probing Sintetis Terdistribusi">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><path d="M2 12h20"></path><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg></span>
              <span class="nav-label">Probing Endpoint</span>
            </a>

            <a href="/maintenance" class="nav-link {_act('maintenance')}" title="Jadwal Pemeliharaan Terencana">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg></span>
              <span class="nav-label">Pemeliharaan</span>
            </a>

            <a href="/logs" class="nav-link {_act('logs')}" title="Log Server Pusat">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg></span>
              <span class="nav-label">Log Server</span>
            </a>

            <a href="/audit" class="nav-link {_act('audit')}" title="Riwayat Tindakan &amp; Jejak Audit">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg></span>
              <span class="nav-label">Riwayat Tindakan</span>
            </a>

            <div class="nav-section" style="padding:14px 14px 4px;font-size:10px;font-weight:700;color:var(--dim-subtle);text-transform:uppercase;letter-spacing:1px">Pengaturan</div>

            {users_item_html}

            <a href="/profile" class="nav-link {_act('profile')}" title="Akun Pengguna &amp; Keamanan">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg></span>
              <span class="nav-label">Akun Pengguna</span>
            </a>

            <a href="/logout" class="nav-link" title="Keluar dari Sistem">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg></span>
              <span class="nav-label" style="color:var(--red)">Keluar</span>
            </a>
          </nav>

          <!-- Sidebar Footer -->
          <div class="sidebar-footer" style="padding:14px 16px;border-top:1px solid var(--border);font-size:11px;background:rgba(0,0,0,0.25)">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
              <span style="color:var(--dim)">v{settings.APP_VERSION}</span>
              <span style="color:var(--green);font-weight:600;font-size:10px">● AKTIF</span>
            </div>
            <div style="font-weight:700;color:var(--text);font-family:ui-monospace,monospace;font-size:11.5px;margin-bottom:2px">{username}</div>
            <div>
              <span class="badge" style="background:{badge_role_bg};color:{badge_role_color};border:1px solid {badge_role_border};font-size:9.5px;padding:1px 5px">{role_display}</span>
            </div>
          </div>
        </div>
        """
        ui.html(sidebar_content_html)

    # Mengembalikan kontainer halaman utama
    return ui.column().classes("w-full max-w-full min-w-0 px-6 py-4 gap-4")
