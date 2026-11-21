# TASK_LIST: Pantau Server (Clean Architecture Rebuild)

Dokumen pelacak kemajuan (*progress tracking*) implementasi Pantau Server baru (`/home/bos/pantau-server`) sesuai aturan `[CDiP]`.

---

## Status Fase Saat Ini: FASE 1 (Fondasi Frontend Taktis & 4 Halaman Lengkap) — PROGRES: 100%

### 1. Fondasi Backend (FastAPI + SQLAlchemy 2.0)
- [x] Inisialisasi struktur direktori bersih (`core`, `models`, `routers`, `services`). `[CA]`
- [x] Isolasi basis data mandiri (*Clean Slate Database* — skema `pantau_server_db` bersih dan terisolasi penuh). `[SF, PCF]`
- [x] Otentikasi aman JWT + native bcrypt (`core/security.py`). `[SFT]`
- [x] Endpoints Agen Telemetri: `POST /api/report`, `GET /api/commands`. `[IV]`
- [x] Mesin Deteksi Masalah: Evaluasi utilisasi dan deteksi sesi remote SSH aktif (`services/problem_service.py`). `[SFT]`
- [x] Seluruh endpoint API data riil armada (`/api/servers`, detail, services, procs, ports, accounts, firewall, cron, problems, actions). `[PA]`

### 2. Frontend Taktis ("Tactical Cyber Command Room" — SPA Vue 3 + Tailwind CSS)
- [x] **Mesin Multi-Bahasa Reaktif (`i18n`):** `[SF]`
  - [x] Default Bahasa Inggris (`en.js`) 100% konsisten untuk seluruh terminologi sysadmin/NOC + Bahasa Indonesia (`id.js`).
  - [x] Sakelar taktis `[ 🌐 EN | ID ]` di navbar, reaktif zero-reload dengan persistensi *localStorage*.
  - [x] Eliminasi seluruh teks hardcode di semua komponen (`App.vue`, `LoginModal.vue`, `AuditView.vue`, `SettingsView.vue`, `ServerWorkspaceModal.vue`, `FleetTableView.vue`, `DashboardView.vue`).
- [x] **Tipografi & Skala Ergonomis Proporsional (Standar Keterbacaan 100% Zoom):** `[RP, Ergonomics]`
  - [x] Penyelarasan base font ke Sans-Serif modern (`Inter` / system sans-serif) dan pembatasan `font-mono` khusus untuk metrik, IP, port, kode, dan angka tabular.
  - [x] Penghapusan total font mikroskopis (`text-[9px]`, `text-[10px]`, `text-[11px]`).
  - [x] Standarisasi hierarki tipografi: Judul 15px–16px (`text-base`), sel tabel 13.5px–14px (`text-sm`), label/header 12px (`text-xs font-bold uppercase`), badge 12px (`text-xs font-bold`), angka KPI 24px–28px (`text-2xl`–`text-3xl`).
  - [x] Penataan asimetris kartu KPI dasbor presisi: Total Server (`minmax(210px, 240px)`), Insiden Aktif (`1fr`), Waktu Sistem (`minmax(280px, 320px)`).
  - [x] Padding kartu (`p-3 px-4`) dan sel tabel (`py-2.5 px-3` / `py-2.5 px-4`) yang lega dan nyaman tanpa membuang kepadatan data.

- [x] **Navbar Taktis (`Navbar.vue`):**
  - [x] Navigasi 4 halaman: Dasbor, Rincian Armada, Log Audit, Pengaturan.
  - [x] Radar Intersepsi Sesi Manusia (`KEY_INTERCEPT ACTIVE`).
  - [x] Indikator denyut detak jantung telemetri (*Live Beacon Waveform*).
  - [x] Pintasan keyboard taktis: `1` (Dasbor), `2` (Armada), `3` (Audit), `4` (Pengaturan).
- [x] **Halaman 1: Dasbor Pasif (`DashboardView.vue` — Murni Pasif):** `[CA]`
  - [x] HUD Ribbon: Total node, status postur keamanan, radar sesi SSH aktif, jam presisi NOC.
  - [x] Kartu Insiden Terkini: Tabel pasif (Waktu, Server, Keparahan, Deskripsi, Durasi, Navigasi `›`).
  - [x] Matriks Pemantauan Visual Armada Mini (*Mini Fleet Grid*).
  - [x] Bebas dari aksi aktif/mutasi (persis seperti konsep dasbor lama).
- [x] **Halaman 2: Rincian Armada (`FleetTableView.vue` — Belum Kontrol):** `[CA]`
  - [x] Toolbar pencarian instan dan filter status (`All`, `Online`, `Offline`).
  - [x] Tabel berdensitas tinggi: Status, Node/Host, Network IP/Iface, Platform/Arch, OS/Kernel, CPU Cores/Load, Memory RAM/Swap, Storage, Uptime, Agen/APT, Last Seen.
  - [x] Klaster Tombol Aksi per baris ala aplikasi pantau: `[ View ]`, `[ 📊 ]`, `[ 🖥️ ]`, `[ 🔄 ]`, `[ ⋮ ]`.
- [x] **Halaman 3: Log Audit (`AuditView.vue` — Mutlak Akuntabilitas):** `[SFT]`
  - [x] Tabel jejak audit kronologis aksi operator.
- [x] **Halaman 4: Pengaturan & Otoritas (`SettingsView.vue` — Mutlak RBAC):** `[SFT]`
  - [x] Tinjauan kebijakan RBAC parity, proteksi akun, dan ambang batas anomali.
- [x] **Jendela Kontrol Mengambang (`ServerWorkspaceModal.vue` — Ranah Kontrol Penuh):** `[SF]`
  - [x] Muncul mengambang saat tombol `[ View ]` ditekan di tabel armada.
  - [x] Host Switcher (`[` dan `]`), minimalkan ke rak bawah (`_`), maksimalkan layar penuh (`⛶`).
  - [x] 10 Sub-panel kontrol aktif per host.
