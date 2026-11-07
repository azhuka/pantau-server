"""
Modul Autentikasi & Keamanan Akses Antarmuka (Login & 2FA TOTP)
==============================================================
Menyediakan validasi sesi login, antarmuka otentikasi kredensial pengguna,
dan verifikasi dua langkah (Two-Factor Authentication / Recovery Code).
"""

from datetime import datetime
from typing import Optional
from nicegui import ui
from starlette.requests import Request
from starlette.responses import RedirectResponse
from sqlalchemy.orm import Session

from models import AppSession, User
from .common import apply_noc_head_styles, get_db


def get_auth_user(request: Request, db: Session) -> Optional[User]:
    """Mengambil data User terotentikasi berdasarkan session_id cookie aktif."""
    sid = request.cookies.get("session_id")
    if not sid:
        return None
    session_row = (
        db.query(AppSession)
        .filter(AppSession.sid == sid, AppSession.expires_at > datetime.utcnow())
        .first()
    )
    if not session_row:
        return None
    return db.query(User).filter(User.id == session_row.user_id, User.is_active == 1).first()


def setup_auth_routes(session_factory):
    """Mendaftarkan rute halaman login dan 2FA ke NiceGUI engine."""

    @ui.page("/login")
    def page_login(request: Request):
        with get_db(session_factory) as db:
            user = get_auth_user(request, db)
            if user:
                return RedirectResponse("/")

        ui.dark_mode().enable()
        apply_noc_head_styles()
        err_msg = request.query_params.get("error")

        with ui.column().classes("w-full min-h-screen flex items-center justify-center p-4 bg-slate-950"):
            with ui.card().classes(
                "w-full max-w-md p-8 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl flex flex-col gap-5"
            ):
                with ui.column().classes("w-full items-center gap-1.5 mb-2"):
                    ui.icon("dns", size="44px").classes("text-blue-500")
                    ui.label("PANTAU SERVER").classes("text-xl font-bold tracking-wider text-white")
                    ui.label("Network Operations Center · Dinas Kominfo Barru").classes(
                        "text-xs text-slate-400 font-mono"
                    )

                if err_msg:
                    with ui.row().classes(
                        "w-full items-center gap-2 bg-rose-950/70 border border-rose-800 p-2.5 rounded text-rose-300 text-xs"
                    ):
                        ui.icon("error", size="18px").classes("text-rose-400")
                        ui.label(err_msg).classes("font-medium")

                with ui.element("form").props('action="/login" method="post"').classes("w-full flex flex-col gap-4"):
                    with ui.column().classes("w-full gap-1"):
                        ui.label("Nama Pengguna").classes("text-xs font-semibold text-slate-300")
                        ui.html("""
                            <input type="text" name="username" placeholder="Masukkan username" required autofocus
                                   class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-white text-sm focus:outline-none focus:border-blue-500" />
                        """)

                    with ui.column().classes("w-full gap-1"):
                        ui.label("Kata Sandi").classes("text-xs font-semibold text-slate-300")
                        ui.html("""
                            <input type="password" name="password" placeholder="Masukkan password" required
                                   class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-white text-sm focus:outline-none focus:border-blue-500" />
                        """)

                    ui.html("""
                        <button type="submit"
                                class="w-full mt-2 py-2.5 px-4 bg-blue-600 hover:bg-blue-500 active:bg-blue-700 text-white font-semibold rounded text-sm transition-colors cursor-pointer shadow-lg">
                            Masuk ke Sistem NOC
                        </button>
                    """)

                with ui.row().classes("w-full justify-center mt-2"):
                    ui.label("Sistem Pemantauan Infrastruktur Terpusat & Keamanan Jaringan").classes(
                        "text-[10px] text-slate-500 text-center"
                    )

    @ui.page("/login/2fa")
    def page_login_2fa(request: Request):
        ui.dark_mode().enable()
        apply_noc_head_styles()
        err_msg = request.query_params.get("error")

        with ui.column().classes("w-full min-h-screen flex items-center justify-center p-4 bg-slate-950"):
            with ui.card().classes(
                "w-full max-w-md p-8 bg-slate-900 border border-slate-800 rounded-xl shadow-2xl flex flex-col gap-5"
            ):
                with ui.column().classes("w-full items-center gap-1.5 mb-2"):
                    ui.icon("security", size="44px").classes("text-emerald-500")
                    ui.label("VERIFIKASI 2FA").classes("text-xl font-bold tracking-wider text-white")
                    ui.label("Masukkan 6 Digit Token TOTP / Recovery Code").classes("text-xs text-slate-400")

                if err_msg:
                    with ui.row().classes(
                        "w-full items-center gap-2 bg-rose-950/70 border border-rose-800 p-2.5 rounded text-rose-300 text-xs"
                    ):
                        ui.icon("error", size="18px").classes("text-rose-400")
                        ui.label(err_msg).classes("font-medium")

                with ui.element("form").props('action="/login/2fa" method="post"').classes("w-full flex flex-col gap-4"):
                    with ui.column().classes("w-full gap-1"):
                        ui.label("Kode Verifikasi (TOTP / Cadangan)").classes("text-xs font-semibold text-slate-300")
                        ui.html("""
                            <input type="text" name="code" placeholder="Contoh: 123456" required autofocus
                                   class="w-full px-3 py-2 bg-slate-950 border border-slate-700 rounded text-white text-center text-lg font-mono tracking-widest focus:outline-none focus:border-emerald-500" />
                        """)

                    ui.html("""
                        <button type="submit"
                                class="w-full mt-2 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white font-semibold rounded text-sm transition-colors cursor-pointer shadow-lg">
                            Verifikasi & Lanjutkan
                        </button>
                    """)

                with ui.row().classes("w-full justify-center mt-1"):
                    ui.button("Kembali ke Halaman Login", on_click=lambda: ui.navigate.to("/login")).props(
                        "dense flat no-caps size=sm color=grey-5"
                    ).classes("text-xs")
