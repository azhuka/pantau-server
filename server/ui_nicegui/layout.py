"""
Komponen Layout Induk Antarmuka NOC (Header, Jam Digital, & Navigasi)
=====================================================================
Menyediakan tata letak baku yang seragam, berorientasi observabilitas NOC,
disertai jam digital real-time dinamis sesuai zona waktu server lokal.
"""

from datetime import datetime
from nicegui import ui
from starlette.requests import Request

from config import settings
from models import User
from .common import apply_noc_head_styles, get_now_local, get_system_tz_label


def render_layout(request: Request, user: User, active_tab: str = "servers"):
    """Render layout umum NOC (Header, Jam Digital Dinamis, dan Tab Navigasi)."""
    ui.dark_mode().enable()
    apply_noc_head_styles()

    # -------------------------------------------------------------------------
    # Top Header NOC
    # -------------------------------------------------------------------------
    with ui.header().classes(
        "bg-slate-900 border-b border-slate-800 text-white px-6 py-2 flex items-center justify-between sticky top-0 z-50"
    ):
        # Brand & Title
        with ui.row().classes("items-center gap-3"):
            ui.icon("dns", size="24px").classes("text-blue-400")
            with ui.column().classes("gap-0"):
                ui.label("PANTAU SERVER").classes("text-base font-bold tracking-wider leading-tight text-white")
                ui.label("NOC MANDIRI · DINAS KOMINFO BARRU").classes("text-[10px] text-slate-400 font-mono")
            ui.badge("NOC", color="blue-9").classes("text-[10px] font-bold px-1.5 py-0.5 ml-1")

        # Jam Digital Real-Time Dinamis (WITA/WIB/Sistem Lokal)
        with ui.row().classes(
            "items-center gap-2 bg-slate-950/70 px-3 py-1 rounded border border-slate-800 font-mono text-xs flex"
        ):
            ui.icon("schedule", size="16px").classes("text-emerald-400")
            lbl_time = ui.label("--:--:--").classes("font-bold text-emerald-400 text-sm")
            lbl_tz = ui.badge(get_system_tz_label(), color="slate-800").classes(
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

        # Profil & Aksi Pengguna
        with ui.row().classes("items-center gap-3"):
            ui.badge(f"v{settings.APP_VERSION}", color="slate-800").classes(
                "text-slate-400 text-[11px] font-mono border border-slate-700"
            )
            if user:
                with ui.row().classes(
                    "items-center gap-1.5 bg-slate-800/80 px-2.5 py-1 rounded border border-slate-700"
                ):
                    ui.icon("account_circle", size="18px").classes("text-slate-300")
                    ui.label(user.username).classes("text-xs font-semibold text-slate-200")
                    ui.badge(user.role_display().upper(), color="slate-700").classes(
                        "text-[9.5px] font-bold text-slate-300 ml-1"
                    )

                ui.button("Keluar", icon="logout", on_click=lambda: ui.navigate.to("/logout")).props(
                    "dense flat no-caps size=sm color=negative"
                ).classes("text-xs")

    # -------------------------------------------------------------------------
    # Bilah Navigasi Utama (Tabs)
    # -------------------------------------------------------------------------
    with ui.row().classes("w-full bg-slate-950/90 border-b border-slate-800/80 px-6 py-1.5 items-center gap-1"):
        nav_items = [
            ("dashboard", "Dashboard", "dashboard", "/dashboard"),
            ("servers", "Daftar Server", "dns", "/servers"),
            ("problems", "Insiden & Masalah", "warning", "/problems"),
            ("audit", "Riwayat Tindakan", "history", "/audit"),
            ("probing", "Probing Endpoint", "wifi_tethering", "/probing"),
            ("maintenance", "Pemeliharaan", "build", "/maintenance"),
        ]
        if user and (user.is_master_admin() or user.has_perm("can_manage_users")):
            nav_items.append(("users", "Pengguna", "group", "/users"))

        for key, label, icon_name, target_url in nav_items:
            is_active = (active_tab == key)
            btn_props = "unelevated color=primary" if is_active else "flat color=grey-4"
            active_class = "font-bold text-white shadow-sm" if is_active else "text-slate-400 hover:text-white"
            ui.button(
                label,
                icon=icon_name,
                on_click=lambda url=target_url: ui.navigate.to(url)
            ).props(f"dense no-caps size=sm {btn_props}").classes(f"text-xs px-3 py-1 rounded {active_class}")
