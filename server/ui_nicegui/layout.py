"""
Komponen Layout Induk Antarmuka NOC (Cetak Biru Kanonikal Pantau Server)
======================================================================
Menyediakan tata letak baku Pusat Operasi Jaringan (NOC) yang 100% selaras
dengan arsitektur matang konsep Pantau Server (v4.8.0 - v4.8.148).
Sidebar 230px di sisi kiri dengan seksi navigasi 'Menu' dan 'Kelola',
footer profil pengguna, penanda badge insiden/probing/pemeliharaan terpadu,
serta area konten widescreen 100% fluid tanpa topbar desktop yang redundan.
"""

from datetime import datetime
import json
from nicegui import ui
from starlette.requests import Request

from config import settings
from models import MaintenanceWindow, ProbeTarget, ServerProblem, User
from .common import apply_noc_head_styles, get_now_local, get_system_tz_label


def render_layout(request: Request, user: User, active_tab: str = "servers", counts: dict = None):
    """Render tata letak kanonikal NOC 1:1 sesuai konsep matang Pantau Server."""
    ui.dark_mode().enable()
    apply_noc_head_styles()

    username = user.username if user else "Tamu"
    role_display = user.role_display() if user else "Viewer"
    tz_label = get_system_tz_label()
    now_utc = datetime.utcnow()
    utc_str = now_utc.strftime("%H:%M")

    # Helper navigasi aktif
    def _act(tab_name: str) -> str:
        return "active" if active_tab == tab_name else ""

    # Hitung badge hitungan jika belum diberikan
    counts = counts or {}
    prob_badge_html = ""
    if counts.get("open_problems", 0) > 0:
        prob_badge_html = f'<span class="badge badge-danger" style="margin-left:auto;font-size:10px;font-weight:700;padding:1px 6px;border-radius:10px">{counts["open_problems"]}</span>'

    probe_badge_html = ""
    if counts.get("down_probes", 0) > 0:
        probe_badge_html = f'<span class="badge badge-down" style="margin-left:auto;font-size:10px;font-weight:700;padding:1px 5px;border-radius:8px">{counts["down_probes"]}</span>'

    maint_badge_html = ""
    if counts.get("active_maintenance", 0) > 0:
        maint_badge_html = f'<span class="badge badge-warn" style="margin-left:auto;font-size:10px;font-weight:700;padding:1px 5px;border-radius:8px">{counts["active_maintenance"]}</span>'

    # Role badge styling
    badge_role_color = "#f87171" if (user and user.is_master_admin()) else ("#38bdf8" if (user and user.is_operator()) else "#94a3b8")
    badge_role_bg = "rgba(239,68,68,0.15)" if (user and user.is_master_admin()) else ("rgba(56,189,248,0.15)" if (user and user.is_operator()) else "rgba(148,163,184,0.15)")
    badge_role_border = "rgba(239,68,68,0.3)" if (user and user.is_master_admin()) else ("rgba(56,189,248,0.3)" if (user and user.is_operator()) else "rgba(148,163,184,0.3)")

    # -------------------------------------------------------------------------
    # 1. Header Aplikasi Mobile Terpadu (Hanya muncul saat layar < 640px)
    # -------------------------------------------------------------------------
    ui.html(f"""
    <header class="mob-header">
      <button type="button" class="mob-hamburger-btn" onclick="document.querySelector('.q-drawer') && document.querySelector('.q-drawer').__vueParentComponent && document.querySelector('.q-drawer').__vueParentComponent.ctx && document.querySelector('.q-drawer').__vueParentComponent.ctx.toggle ? document.querySelector('.q-drawer').__vueParentComponent.ctx.toggle() : toggleSb()" aria-label="Buka navigasi menu">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="3" y1="12" x2="21" y2="12"></line><line x1="3" y1="6" x2="21" y2="6"></line><line x1="3" y1="18" x2="21" y2="18"></line></svg>
      </button>
      <a href="/" class="mob-brand">
        <span class="brand-dot"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--blue);vertical-align:middle"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="3" fill="currentColor"></circle></svg></span>
        <span>Pantau Server</span>
      </a>
      <div class="mob-header-right" style="display:flex;align-items:center;gap:8px">
        <button type="button" class="btn btn-ghost btn-sm" onclick="openThemeModal()" style="padding:4px 8px;font-size:11px" title="Kustomisasi Tema, Warna &amp; Font" aria-label="Tema">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10a10 10 0 0 0 10-10c0-5.51-4.49-10-10-10zM3.47 12.6c0-.2.03-.4.07-.6A8.53 8.53 0 0 1 12 3.5a8.5 8.5 0 0 1 8.5 8.5c0 1.25-.46 2.4-1.23 3.32-.45.54-1.12.88-1.87.88H15a2 2 0 0 0-2 2v.4c0 .88-.72 1.6-1.6 1.6-.74 0-1.4-.41-1.72-1.07A6.47 6.47 0 0 1 9.4 17.5c-3.27 0-5.93-2.66-5.93-4.9z"/></svg>
        </button>
        <span class="mob-user-chip" title="Login: {username}">
          {username[:1].upper()}
        </span>
      </div>
    </header>
    """)

    # -------------------------------------------------------------------------
    # 2. Sidebar Bilah Sisi Kanonikal 230px (Left Drawer NOC)
    # -------------------------------------------------------------------------
    with ui.left_drawer(value=True, fixed=True, bordered=True).classes(
        "bg-[#162032] border-r border-slate-800 text-white p-0 flex flex-col justify-between"
    ).props("width=230 breakpoint=640 show-if-above"):

        sidebar_html = f"""
        <aside class="sidebar" id="appSidebar" style="position:static;height:100%;display:flex;flex-direction:column;justify-content:space-between;border:none;width:100%">
          <!-- Brand Header -->
          <div class="sidebar-brand">
            <span class="brand-dot"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color:var(--blue);vertical-align:middle"><circle cx="12" cy="12" r="10"></circle><circle cx="12" cy="12" r="3" fill="currentColor"></circle></svg></span>
            <span class="brand-label">Pantau Server</span>
            <button class="sb-toggle" id="sbToggle" onclick="toggleSb()" title="Minimalkan sidebar" aria-label="Minimalkan sidebar" type="button">
              <svg class="sb-icon-collapse" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line><path d="M15 15l-3-3 3-3"></path></svg>
              <svg class="sb-icon-expand" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><line x1="9" y1="3" x2="9" y2="21"></line><path d="M13 9l3 3-3 3"></path></svg>
            </button>
          </div>

          <!-- Navigasi Menu & Kelola -->
          <nav class="sidebar-nav" style="flex:1;overflow-y:auto">
            <div class="nav-section">Menu</div>
            <a href="/" class="nav-link {_act('dashboard')}" title="Dashboard Pemantauan Pusat">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg></span>
              <span class="nav-label">Dashboard</span>
            </a>

            <a href="/servers" class="nav-link {_act('servers')}" title="Daftar Server Terpadu">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="2" width="20" height="8" rx="2" ry="2"></rect><rect x="2" y="14" width="20" height="8" rx="2" ry="2"></rect><line x1="6" y1="6" x2="6.01" y2="6"></line><line x1="6" y1="18" x2="6.01" y2="18"></line></svg></span>
              <span class="nav-label">Daftar Server</span>
            </a>

            <a href="/problems" class="nav-link {_act('problems')}" title="Pusat Insiden &amp; Gangguan">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg></span>
              <span class="nav-label">Insiden</span>
              {prob_badge_html}
            </a>

            <a href="/probing" class="nav-link {_act('probing')}" title="Pemantauan Endpoint &amp; Jaringan">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="2"></circle><path d="M16.24 7.76a6 6 0 0 1 0 8.49m-8.48-.01a6 6 0 0 1 0-8.49m11.31-2.82a10 10 0 0 1 0 14.14m-14.14 0a10 10 0 0 1 0-14.14"></path></svg></span>
              <span class="nav-label">Pantau Endpoint</span>
              {probe_badge_html}
            </a>

            <a href="/logs" class="nav-link {_act('logs')}" title="Log Sistem Server">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"></polyline><line x1="12" y1="19" x2="20" y2="19"></line></svg></span>
              <span class="nav-label">Log</span>
            </a>

            <div class="nav-section">Kelola</div>

            <a href="/maintenance" class="nav-link {_act('maintenance')}" title="Jendela Pemeliharaan Terjadwal">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"></rect><line x1="16" y1="2" x2="16" y2="6"></line><line x1="8" y1="2" x2="8" y2="6"></line><line x1="3" y1="10" x2="21" y2="10"></line></svg></span>
              <span class="nav-label">Pemeliharaan</span>
              {maint_badge_html}
            </a>

            <a href="/audit" class="nav-link {_act('audit')}" title="Riwayat Tindakan &amp; Jejak Audit">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg></span>
              <span class="nav-label">Riwayat Tindakan</span>
            </a>

            <a href="/profile" class="nav-link {_act('profile')}" title="Akun Pengguna, Keamanan &amp; Hak Akses">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle></svg></span>
              <span class="nav-label">Akun Pengguna</span>
            </a>

            <a href="javascript:void(0)" onclick="openThemeModal()" class="nav-link" id="nav-btn-theme" title="Kustomisasi Tema, Warna &amp; Font">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"></circle><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"></circle><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"></circle><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"></circle><path d="M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10a10 10 0 0 0 10-10c0-5.51-4.49-10-10-10zM3.47 12.6c0-.2.03-.4.07-.6A8.53 8.53 0 0 1 12 3.5a8.5 8.5 0 0 1 8.5 8.5c0 1.25-.46 2.4-1.23 3.32-.45.54-1.12.88-1.87.88H15a2 2 0 0 0-2 2v.4c0 .88-.72 1.6-1.6 1.6-.74 0-1.4-.41-1.72-1.07A6.47 6.47 0 0 1 9.4 17.5c-3.27 0-5.93-2.66-5.93-4.9z"></path></svg></span>
              <span class="nav-label">Kustomisasi UI</span>
            </a>

            <a href="/logout" class="nav-link" title="Keluar dari Sistem">
              <span class="nav-icon"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg></span>
              <span class="nav-label" style="color:var(--red)">Keluar</span>
            </a>
          </nav>

          <!-- Sidebar Footer -->
          <div class="sidebar-footer">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:6px">
              <div style="font-size:11px;color:var(--dim)">v{settings.APP_VERSION} · UTC <span id="clockUtc">{utc_str}</span></div>
              <button type="button" onclick="openThemeModal()" class="btn btn-ghost btn-sm" style="padding:2px 6px;font-size:10px;line-height:1" title="Kustomisasi Tema, Warna &amp; Font" aria-label="Tema">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10a10 10 0 0 0 10-10c0-5.51-4.49-10-10-10zM3.47 12.6c0-.2.03-.4.07-.6A8.53 8.53 0 0 1 12 3.5a8.5 8.5 0 0 1 8.5 8.5c0 1.25-.46 2.4-1.23 3.32-.45.54-1.12.88-1.87.88H15a2 2 0 0 0-2 2v.4c0 .88-.72 1.6-1.6 1.6-.74 0-1.4-.41-1.72-1.07A6.47 6.47 0 0 1 9.4 17.5c-3.27 0-5.93-2.66-5.93-4.9z"/></svg>
              </button>
            </div>
            <div style="margin-bottom:6px;line-height:1.4">
              <div style="font-weight:700;color:var(--text);font-family:ui-monospace,monospace;font-size:12px">{username}</div>
              <div style="margin-top:2px">
                <span class="badge" style="background:{badge_role_bg};color:{badge_role_color};border:1px solid {badge_role_border};font-size:10px;padding:1px 6px">{role_display}</span>
              </div>
            </div>
            <div style="font-size:11px;margin-top:4px">
              <a href="/logout" style="color:var(--red)">Keluar</a>
            </div>
          </div>
        </aside>
        """
        ui.html(sidebar_html)

    # -------------------------------------------------------------------------
    # 3. Modal Kustomisasi Tema & Modal Global (Diinjeksi ke DOM)
    # -------------------------------------------------------------------------
    ui.html("""
    <!-- Modal Kustomisasi UI & Tema -->
    <div id="theme-customizer-modal" class="modal-backdrop" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.65);z-index:99999;align-items:center;justify-content:center;backdrop-filter:blur(3px);padding:16px" onclick="if(event.target===this)closeThemeModal()">
      <div class="card" style="width:100%;max-width:540px;background:var(--modal-bg);border:1px solid var(--modal-border);border-radius:12px;padding:22px;box-shadow:var(--shadow-lg);color:var(--text)">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;border-bottom:1px solid var(--border);padding-bottom:12px">
          <h3 style="margin:0;font-size:16px;font-weight:700;display:flex;align-items:center;gap:8px">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color:var(--blue)"><circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/><circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/><circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/><circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/><path d="M12 2C6.49 2 2 6.49 2 12s4.49 10 10 10a10 10 0 0 0 10-10c0-5.51-4.49-10-10-10zM3.47 12.6c0-.2.03-.4.07-.6A8.53 8.53 0 0 1 12 3.5a8.5 8.5 0 0 1 8.5 8.5c0 1.25-.46 2.4-1.23 3.32-.45.54-1.12.88-1.87.88H15a2 2 0 0 0-2 2v.4c0 .88-.72 1.6-1.6 1.6-.74 0-1.4-.41-1.72-1.07A6.47 6.47 0 0 1 9.4 17.5c-3.27 0-5.93-2.66-5.93-4.9z"/></svg>
            Kustomisasi Antarmuka NOC
          </h3>
          <button type="button" class="btn btn-ghost btn-sm" onclick="closeThemeModal()" style="font-size:18px;line-height:1;padding:2px 8px">&times;</button>
        </div>

        <div style="display:flex;flex-direction:column;gap:14px;max-height:70vh;overflow-y:auto;padding-right:4px">
          <div>
            <label style="font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:0.5px">Tema Warna Utama</label>
            <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:8px;margin-top:6px">
              <button type="button" id="theme-card-dark" class="btn btn-ghost btn-sm active" onclick="onThemeModeSelect('dark')" style="border:1px solid var(--border);padding:8px 4px;font-size:11px;text-align:center">Dark (NOC)</button>
              <button type="button" id="theme-card-obsidian" class="btn btn-ghost btn-sm" onclick="onThemeModeSelect('obsidian')" style="border:1px solid var(--border);padding:8px 4px;font-size:11px;text-align:center">Obsidian</button>
              <button type="button" id="theme-card-navy" class="btn btn-ghost btn-sm" onclick="onThemeModeSelect('navy')" style="border:1px solid var(--border);padding:8px 4px;font-size:11px;text-align:center">Deep Navy</button>
              <button type="button" id="theme-card-light" class="btn btn-ghost btn-sm" onclick="onThemeModeSelect('light')" style="border:1px solid var(--border);padding:8px 4px;font-size:11px;text-align:center">Light</button>
            </div>
          </div>

          <div>
            <label style="font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:0.5px">Aksen Warna (Highlight)</label>
            <div style="display:flex;gap:8px;margin-top:6px;flex-wrap:wrap">
              <button type="button" id="accent-pill-cyan" class="btn btn-ghost btn-sm active" onclick="onAccentSelect('cyan')" style="border:1px solid var(--blue);color:var(--blue);font-size:11px">Cyan Blue</button>
              <button type="button" id="accent-pill-emerald" class="btn btn-ghost btn-sm" onclick="onAccentSelect('emerald')" style="border:1px solid #10b981;color:#10b981;font-size:11px">Emerald</button>
              <button type="button" id="accent-pill-amber" class="btn btn-ghost btn-sm" onclick="onAccentSelect('amber')" style="border:1px solid #f59e0b;color:#f59e0b;font-size:11px">Amber</button>
              <button type="button" id="accent-pill-indigo" class="btn btn-ghost btn-sm" onclick="onAccentSelect('indigo')" style="border:1px solid #6366f1;color:#6366f1;font-size:11px">Indigo</button>
              <button type="button" id="accent-pill-violet" class="btn btn-ghost btn-sm" onclick="onAccentSelect('violet')" style="border:1px solid #a855f7;color:#a855f7;font-size:11px">Violet</button>
            </div>
          </div>

          <div>
            <label style="font-size:11px;font-weight:700;color:var(--dim);text-transform:uppercase;letter-spacing:0.5px">Kepadatan Baris (Density)</label>
            <div style="display:flex;gap:8px;margin-top:6px">
              <button type="button" id="density-opt-compact" class="btn btn-ghost btn-sm active" onclick="onThemeDensityChange('compact')" style="border:1px solid var(--border);font-size:11px">Kompak (High Density NOC)</button>
              <button type="button" id="density-opt-comfortable" class="btn btn-ghost btn-sm" onclick="onThemeDensityChange('comfortable')" style="border:1px solid var(--border);font-size:11px">Nyaman (Comfortable)</button>
            </div>
          </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:18px;border-top:1px solid var(--border);padding-top:14px">
          <button type="button" class="btn btn-ghost btn-sm" onclick="resetThemeDefaults()" style="color:var(--dim);font-size:11px">Reset Default</button>
          <button type="button" class="btn btn-primary btn-sm" onclick="closeThemeModal()">Simpan &amp; Tutup</button>
        </div>
      </div>
    </div>
    """)

    ui.add_body_html("""
    <script>
    function openThemeModal() {
      const m = document.getElementById('theme-customizer-modal');
      if (m) m.style.display = 'flex';
      if (typeof updateThemeModalUI === 'function') updateThemeModalUI(getThemeSettings());
    }
    function closeThemeModal() {
      const m = document.getElementById('theme-customizer-modal');
      if (m) m.style.display = 'none';
    }
    </script>
    """)

    # Mengembalikan kontainer halaman utama (Widescreen fluid 100% width)
    return ui.column().classes("w-full max-w-full min-w-0 px-6 py-4 gap-4 items-stretch")
