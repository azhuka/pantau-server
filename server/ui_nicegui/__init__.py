"""
Paket Antarmuka NiceGUI Pure Python (Pantau Server NOC Frontend Engine)
======================================================================
Arsitektur modular frontend murni Python berbasis NiceGUI + Quasar UI
yang mengadaptasi seluruh konsep desain matang Pusat Operasi Jaringan (NOC).
"""

import os
from fastapi.staticfiles import StaticFiles
from nicegui import ui

from config import settings
from .audit import setup_audit_routes
from .auth import setup_auth_routes
from .dashboard import setup_dashboard_routes
from .logs_server import setup_logs_server_routes
from .maintenance import setup_maintenance_routes
from .probing import setup_probing_routes
from .problems import setup_problems_routes
from .profile import setup_profile_routes
from .servers import setup_servers_routes
from .server_detail import setup_server_detail_routes
from .users import setup_users_routes


def setup_nicegui(fastapi_app, session_factory):
    """Menginisialisasi seluruh modul antarmuka NiceGUI dan mengaitkannya ke FastAPI."""
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        fastapi_app.mount("/static", StaticFiles(directory=static_dir), name="static")

    setup_auth_routes(session_factory)
    setup_dashboard_routes(session_factory)
    setup_servers_routes(session_factory)
    setup_server_detail_routes(session_factory)
    setup_problems_routes(session_factory)
    setup_probing_routes(session_factory)
    setup_maintenance_routes(session_factory)
    setup_audit_routes(session_factory)
    setup_users_routes(session_factory)
    setup_profile_routes(session_factory)
    setup_logs_server_routes(session_factory)

    ui.run_with(
        fastapi_app,
        mount_path="/",
        storage_secret=settings.SECRET_KEY,
        title="Pantau Server - NOC Mandiri",
        dark=True,
    )


__all__ = ["setup_nicegui"]
