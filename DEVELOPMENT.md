# Dokumentasi Pengembangan Pantau Server (Developer Guide & Changelog)

Dokumentasi ini ditujukan khusus bagi pengembang (*developer*) untuk melacak, memahami, dan memelihara arsitektur, sejarah evolusi, keputusan desain teknis, serta panduan operasional kode dari aplikasi **Pantau Server** dan **Agen Pantau**.

---

## Daftar Isi

1. [Filosofi Desain & Prinsip Arsitektur](#1-filosofi-desain--prinsip-arsitektur)
2. [Peta Struktur Repositori](#2-peta-struktur-repositori)
3. [Alur Komunikasi & Protokol Data](#3-alur-komunikasi--protokol-data)
4. [Evolusi Versi & Kronologi Pengembangan](#4-evolusi-versi--kronologi-pengembangan)
   - [Fase Awal (v1.0 – v3.5)](#fase-awal-v10--v35-fondasi-monitoring)
   - [Fase Kontrol Host & Stabilitas (v3.6)](#fase-kontrol-host--stabilitas-v36)
   - [Fase Pembaruan OS & Hardening (v3.7 – v3.10)](#fase-pembaruan-os--hardening-v37--v310)
   - [Fase Terminal Bawaan & Shell PTY (v3.11 – v3.12)](#fase-terminal-bawaan--shell-pty-v311--v312)
   - [Fase File Manager & Audit Keamanan (v3.13)](#fase-file-manager--audit-keamanan-v313)
   - [Fase WebSocket Terminal & Realtime Streaming (v3.14)](#fase-websocket-terminal--realtime-streaming-v314)
   - [Fase v3.15.0: Top Procs, Mode Pemeliharaan & Kesiapan Produksi](#fase-v3150-top-procs-mode-pemeliharaan--kesiapan-produksi)
5. [Bedah Teknis Komponen Kritis](#5-bedah-teknis-komponen-kritis)
   - [TerminalBridgeDispatcher & WebSocket Engine](#terminalbridgedispatcher--websocket-engine)
   - [Wrapper Keamanan Sudoers](#wrapper-keamanan-sudoers)
   - [Normalisasi Service Systemd & Cgroup](#normalisasi-service-systemd--cgroup)
   - [Sistem Retensi Basis Data Otomatis](#sistem-retensi-basis-data-otomatis)
6. [Skema Basis Data & Konfigurasi](#6-skema-basis-data--konfigurasi)
7. [Panduan Rilis & Workflow Pengembangan](#7-panduan-rilis--workflow-pengembangan)

---

## 1. Filosofi Desain & Prinsip Arsitektur

Pantau Server dirancang dengan prinsip-prinsip operasional berikut:

1. **Inbound-Only dari Sisi Dashboard (Zero Inbound ke Klien):**
   - Dashboard pusat **tidak pernah** membuka koneksi SSH atau socket langsung ke server klien.
   - Server klien bisa berada di balik NAT, firewall ketat, atau jaringan privat tanpa IP publik. Seluruh komunikasi diinisiasi oleh Agen Pantau yang melapor keluar (*outbound polling*) ke Dashboard.
2. **Kemandirian Agen Klien (Python Standard Library Only):**
   - Agen klien (`agent_pantau.py`) **tidak bergantung pada pustaka eksternal pihak ketiga (tanpa `pip install`, tanpa `virtualenv`)**. Agen murni menggunakan pustaka bawaan Python 3 (`urllib.request`, `subprocess`, `pty`, `os`, `json`, dll.) agar tidak membebani sistem klien dan terhindar dari konflik dependensi.
3. **Prinsip Hak Akses Terkecil (*Least Privilege*):**
   - Agen berjalan di bawah user non-root `pantau`.
   - Tindakan yang membutuhkan wewenang root dibatasi melalui berkas `/etc/sudoers.d/pantau-agent` yang hanya mengizinkan eksekusi biner wrapper spesifik (`pantau-shell`, `pantau-apt`, `pantau-file`, `pantau-host`, `pantau-restart`).
4. **Single Source of Truth pada Frontend:**
   - Data status, metrik, dan masalah disinkronkan melalui satu sumber status di backend FastAPI. Tidak ada ambiguitas status antar halaman.

---

## 2. Peta Struktur Repositori

```
/home/bos/rj45/
├── server/                           # Backend Dashboard (FastAPI + Jinja2 Templates)
│   ├── main.py                       # Routing API, WebSocket Dispatcher, Controller Web
│   ├── models.py                     # Skema ORM SQLAlchemy (MariaDB)
│   ├── config.py                     # Konfigurasi aplikasi & APP_VERSION
│   ├── schemas.py                    # Validasi skema data Pydantic
│   ├── seed_admin.py                 # Utilitas inisialisasi / reset user admin
│   ├── static/                       # Aset statis frontend (CSS, JS, xterm vendor)
│   │   ├── css/                      # Gaya antarmuka (dashboard, terminal, services)
│   │   └── js/                       # Skrip dinamis (services.js, xterm.js, fit-addon)
│   └── templates/                    # Templat HTML Jinja2 (dashboard, services, files, dll.)
│
├── package/                          # Paket Distribusi Agen Klien
│   ├── install.sh                    # Skrip penginstal agen klien otomatis
│   ├── etc/
│   │   └── sudoers.d/
│   │       └── pantau-agent          # Konfigurasi izin sudo NOPASSWD untuk wrapper
│   ├── opt/pantau/agent/
│   │   └── agent_pantau.py           # Daemon agen klien (Stdlib Python 3)
│   └── usr/local/sbin/               # Skrip wrapper keamanan agen
│       ├── pantau-apt                # Eksekusi operasi APT terkontrol
│       ├── pantau-file               # Operasi berkas & manipulasi izin berguardrail
│       ├── pantau-host               # Eksekusi tertunda reboot & power off
│       ├── pantau-restart            # Restart layanan dengan proteksi deny-list
│       └── pantau-shell              # Inisialisasi shell bash root via PTY
│
├── database/
│   └── schema.sql                    # Skema DDL MariaDB bersih versi terbaru
│
├── deploy/                           # Konfigurasi Deployment Produksi
│   ├── nginx/
│   │   └── pantau-server.conf        # Konfigurasi reverse-proxy Nginx + SSL + WebSocket
│   └── logrotate/
│       └── pantau-server             # Konfigurasi rotasi log Uvicorn
│
├── install-server.sh                 # Skrip installer otomatis Dashboard pusat
├── README.md                         # Dokumentasi panduan operasional pengguna
└── DEVELOPMENT.md                    # Dokumentasi teknis & pelacakan pengembangan (file ini)
```

---

## 3. Alur Komunikasi & Protokol Data

### A. Pelaporan Metrik Reguler
```
[ Agen Pantau Klien ]
        │
        │ HTTP POST /api/report (Interval: ~10s)
        │ Headers: X-API-Key: <sha256-verified-key>
        │ Payload: { cpu, mem, swap, disk, net, services, extras, top_procs }
        ▼
[ FastAPI Server ] ──> Validasi API Key ──> Simpan ke DB (`metrics`, `servers`)
```

### B. Eksekusi Perintah Remote (APT / Service / Host)
```
1. Admin menekan tombol di Dashboard UI.
2. Dashboard membuat baris baru di tabel `command_queue` (Status: `pending`).
3. Agen melakukan polling: `GET /api/agent/command`.
4. Jika ada perintah tertunda, Agen mengeksekusi wrapper terkait.
5. Agen melaporkan status/output balik via: `POST /api/agent/command/result`.
```

### C. Alur Sesi Terminal Bawaan (WebSocket Streaming)
```
[ Peramban Admin ]
        │
        │  WebSocket ws[s]://host/ws/servers/{id}/terminal
        │  (Mengirim keystroke, resize terminal, ping)
        ▼
[ TerminalBridgeDispatcher (FastAPI Server) ]
   ├── queue_in  (Antrean perintah dari UI ke agen)
   └── queue_out (Antrean output shell dari agen ke UI)
        ▲
        │  HTTP Long-Polling Stream (Decoupled from DB)
        ▼
[ Agen Pantau Klien ]
        │  pty.openpty() + TIOCSCTTY
        ▼
[ /usr/local/sbin/pantau-shell ] ──> /bin/bash (root)
```

---

## 4. Evolusi Versi & Kronologi Pengembangan

### Fase Awal (v1.0 – v3.5): Fondasi Monitoring
- Pembuatan server dashboard berbasis FastAPI dan MariaDB.
- Agen klien awal berbasis Python untuk membaca utilisasi sumber daya (`/proc/stat`, `/proc/meminfo`, `df`, `ip`).
- Implementasi sistem basis data awal untuk menyimpan metrik historis, status layanan, dan tiket masalah (*problems*).

### Fase Kontrol Host & Stabilitas (v3.6)
- **Fitur Baru:** Penambahan kendali `Reboot OS` dan `Power Off` langsung dari web UI.
- **Tantangan Teknis:** Saat server dimatikan, proses agen ikut mati seketika sehingga respon HTTP tidak sempat dikirim kembali ke dashboard.
- **Solusi:**
  - Pembuatan skrip `pantau-host` dengan eksekusi tertunda (*delayed rebound*) ±4 detik di latar belakang, memberi jeda bagi agen untuk mengirim sinyal konfirmasi ke dashboard sebelum sistem benar-benar reboot/padam.
  - Implementasi deteksi status mesin berbasis *recency* `last_seen_ago_ms` (jendela 30 detik), sehingga dashboard secara akurat mengenali status `REBOOT SUKSES`, `MATI`, maupun `HIDUP KEMBALI`.

### Fase Pembaruan OS & Hardening (v3.7 – v3.10)
- **Fitur Baru:** Operasi `Update OS` dan `Upgrade Paket` via dashboard.
- **Tantangan Teknis:** Perintah `apt upgrade` seringkali menggantung (*hang*) tanpa batas waktu karena menunggu prompt interaktif `dpkg` (misalnya pemilihan berkas konfigurasi konflik `conffile`).
- **Solusi:**
  - Penambahan skrip wrapper `pantau-apt` yang menangani flag non-interaktif dan isolasi proses APT.
  - Integrasi terminal interaktif sederhana di dashboard agar admin dapat merespon konfirmasi `Y/n` atau pertanyaan `dpkg`.
  - Pengerasan keamanan sistem: proteksi deny-list pada service krusial (mencegah SSH, firewall, atau agen itu sendiri dimatikan sembarangan), rate limiting persisten di basis data, dan token proteksi CSRF berbasis HMAC.

### Fase Terminal Bawaan & Shell PTY (v3.11 – v3.12)
- **Evolusi:** Pengguna membutuhkan kemampuan administrasi shell menyeluruh tanpa dibatasi oleh whitelist perintah web.
- **Implementasi:**
  - Pembuatan PTY asli menggunakan pustaka standar Python `pty.openpty()` dan `termios`.
  - Wrapper `pantau-shell` yang menjalankan `/bin/bash` dengan profil terisolasi (`HISTFILE=/dev/null` agar jejak riwayat tidak tersimpan di disk).
  - Emulasi kontrol karakter VT100 untuk penanganan `Backspace`, `Ctrl+C` (sinyal `SIGINT` nyata), autokompleksi `Tab`, dan kursor aktif.

### Fase File Manager & Audit Keamanan (v3.13)
- **Fitur Baru:** File Manager berbasis web yang terintegrasi di `/servers/{id}/files`.
- **Implementasi:**
  - Wrapper `pantau-file` untuk menjalankan operasi berkas remote: penjelajahan direktori, baca/tulis berkas teks, unggah/unduh berkas biner, dan pengaturan `chmod`/`chown`.
  - **Sistem Pengaman (Guardrail):** Pencegahan penyuntingan/penghapusan pada direktori inti sistem (`/boot`, `/dev`, `/proc`, `/sys`, `/etc/sudoers.d`).
  - **Fitur Pencadangan Otomatis:** Setiap kali berkas diedit dan disimpan via File Manager, sistem otomatis membuat salinan `.bak` bertanda waktu.

### Fase WebSocket Terminal & Realtime Streaming (v3.14)
- **Masalah:** Terminal berbasis polling HTTP lambat merespon ketikan cepat, rentan *lag*, dan sulit menampilkan aplikasi layar penuh seperti `nano`, `htop`, atau `vim`.
- **Refactoring Besar:**
  - Migrasi frontend ke emulator terminal standar industri **xterm.js** dan addon **fit-addon** (disimpan lokal secara *vendorized* tanpa dependensi CDN eksternal).
  - Arsitektur backend **TerminalBridgeDispatcher**: WebSocket streaming dua arah berkecepatan tinggi dengan antrean memori *decoupled*.
  - Dukungan manipulasi ukuran jendela terminal (*window resize*) dinamis dari peramban ke PTY klien.
  - Mekanisme pembersihan otomatis (*auto-cleanup*) untuk membunuh sesi PTY dan child process di server klien saat koneksi WebSocket peramban ditutup.

### Fase v3.15.0: Top Procs, Mode Pemeliharaan & Kesiapan Produksi
- **Mode Pemeliharaan (Maintenance Mode):**
  - Penambahan kolom `is_maintenance`, `maintenance_until`, dan `maintenance_reason` pada tabel `servers`.
  - Meredam alarm baru saat server klien sedang dalam jadwal servis terencana.
- **Snapshot 20 Proses Teratas (Top Processes Live):**
  - Kolektor proses berbasis Python stdlib pada agen: `ps -eo pid,user,comm,%cpu,%mem --sort=-%cpu`.
  - Ditransmisikan melalui laporan reguler dan disimpan di `server_extras.top_procs`.
  - UI responsif: menampilkan 5 proses teratas secara ringkas dengan opsi tautan ekspansi ke 20 proses.
- **Normalisasi Service Systemd & Cgroup:**
  - Membaca nama unit asli via cgroup PID (`/sys/fs/cgroup/systemd/...`) untuk mengatasi inkonsistensi alias unit seperti `postfix` vs `master` dan `zabbix-agent` vs `zabbix-agent2`.
- **Kesiapan Produksi:**
  - Migrasi `SECRET_KEY` acak menjadi statis via berkas `.env`.
  - Pembersihan otomatis retensi basis data (*retention pruning*) setiap jam.
  - Templat reverse proxy Nginx (`deploy/nginx/pantau-server.conf`) dan Logrotate (`deploy/logrotate/pantau-server`).
  - Git tag resmi `v3.15.0` dan rilis GitHub.

### Peningkatan Estetika & Stabilitas (Post-v3.15.0)
- **Mode Full Screen Terminal Bawaan:**
  - Penambahan tombol Full Screen pada bar aksi terminal (`#term-fullscreen-btn`) dan dukungan shortcut `Esc`.
  - Menggunakan overlay CSS fixed viewport (`.terminal-window.is-fullscreen`) yang terhubung langsung ke `fitAddon.fit()`, memastikan emulasi PTY xterm.js menyesuaikan resolusi monitor secara presisi dan zero-latency.
- **Redesain Total Riwayat Kinerja (Tab Riwayat):**
  - Transformasi SVG polyline sederhana menjadi **modern area-gradient glow chart** (menggunakan `<defs><linearGradient>` dan polygon fill bercahaya).
  - Pembungkus sub-kartu metrik `.perf-metric-card` dengan header indikator statistik instan: nilai terkini (*latest*), rata-rata rentang (*avg*), dan nilai puncak (*max*).
  - Pemilih rentang waktu dirombak menjadi segmented control modern.
- **Resolusi Deteksi IP Jaringan Klien:**
  - Mengganti parser usang `/proc/net/fib_trie` pada agen klien dengan modul `collect_net()` modern berbasis `ip -j addr show` / `ip -br addr show` / socket `ioctl(SIOCGIFADDR)`.
  - Penambahan mekanisme fallback cerdas di backend FastAPI (`api_server_system`) agar server klien yang belum sempat memperbarui agen tetap menampilkan IP address utama secara otomatis.
- **Perbaikan Validasi CSRF Aktivitas Pengguna:**
  - Memperbaiki kegagalan permintaan `POST /api/logs/request` pada `user_activity.html` dengan menyertakan header `X-CSRF-Token: getCsrf()`.
- **Reaktivitas UI Live Tanpa Reload (Live Problem Reactivity & Auto-Resolution):**
  - Payload polling berkala `/api/servers/{id}/overview` kini menyertakan `problem_level`, `open_problems`, dan `problem_history` yang tersinkronisasi.
  - Fungsi `renderProblemsTab()` pada `services.html` memperbarui tab Status Masalah, badge counter pada tombol tab, serta baris-baris masalah secara instan di sisi klien.
  - Saat operasi upgrade paket OS (`pantau-apt`) selesai dieksekusi, backend otomatis menandai masalah `apt_updates` sebagai selesai (*resolved*) dan mengenolkan `apt_upgradable`. Frontend segera memicu `poll()` instan agar notifikasi pembaruan langsung hilang tanpa reload peramban.
  - Aksi "Ditangani" (*acknowledge*) dan "Selesaikan" (*resolve*) tiket masalah di `services.html` dan `problems.html` diperbarui menjadi aksi in-place dengan toast notifikasi tanpa me-reload peramban (`location.reload()`).
- **Peningkatan Penanganan Penghentian Layanan (Stop Standalone Processes & Scopes):**
  - Skrip wrapper [package/usr/local/sbin/pantau-restart](file:///home/bos/rj45/package/usr/local/sbin/pantau-restart) ditingkatkan dengan fallback cerdas saat menghentikan layanan non-systemd service (misalnya proses mandiri / user scope seperti browser headless `chrome` atau worker kustom).
  - Jika `systemctl stop <unit>` gagal karena unit bukan `.service` standar, skrip secara otomatis mendeteksi scope systemd (`systemctl list-units --type=scope`) serta PID proses via `pgrep`/`pidof`, lalu mengirimkan sinyal `SIGTERM` dan `SIGKILL` secara aman dengan tetap mengunci proteksi deny-list (SSH, firewall, agent).
- **Fitur Abaikan Masalah (Problem Silence / Mute):**
  - Mengatasi kendala *Alert Fatigue* di mana masalah tertentu sengaja dibiarkan (misalnya proses non-aktif yang memang tidak dipakai atau kapasitas disk backup khusus) tanpa membuat dashboard terus-menerus berwarna merah/kuning (*Warning/Danger*).
  - Penambahan kolom `is_ignored`, `ignored_until`, `ignored_by`, dan `ignored_reason` pada tabel `server_problems` dengan skrip migrasi otomatis saat startup aplikasi (`migrate_server_problem_ignored`).
  - Endpoint backend `POST /api/alerts/{id}/ignore` (pilihan durasi 2 jam, 24 jam, 7 hari, 30 hari, atau permanen, disertai alasan opsional) dan `POST /api/alerts/{id}/unignore`.
  - Masalah yang diabaikan secara otomatis dieksklusikan dari kalkulasi keparahan server (`problem_level`), tidak memicu modal peringatan DANGER, dan baris masalah diberi penanda badge `🔕 diabaikan` dengan opsi filter tersendiri `Diabaikan (🔕)`.
  - Dilengkapi tombol `🔔 Pantau Kembali` (*Unmute*) yang sewaktu-waktu dapat digunakan untuk mengembalikan alarm ke pemantauan aktif.
- **Isolasi Masalah Diabaikan & Sinkronisasi Status Server (Dashboard & Rincian):**
  - Mengisolasi layanan yang mengalami down tetapi masalahnya telah diabaikan (`is_ignored = 1`) agar tidak lagi menaikkan `down_svc_count`, tidak memicu status server menjadi "service down" / "Masalah" pada menu Dashboard maupun halaman Daftar Server.
  - Memperbaiki kolom Masalah dan Layanan pada `dashboard.html` serta polling `/api/servers` agar memperbarui `problem_level` dan status layanan secara live dengan penanda hening `OK 🔕`.
  - Memisahkan penghitungan badge masalah aktif dan masalah diabaikan pada tombol Tab Masalah dan header kartu Status Masalah di `services.html` (`${activeCount} masalah aktif · ${ignoredCount} diabaikan (🔕)`), sehingga saat seluruh masalah diabaikan statusnya tetap bersih `OK` dan tidak memicu badge merah/kuning.
  - Memperbaiki topbar statistik di `/problems` agar hanya menghitung masalah aktif tanpa menyertakan masalah yang dibungkam dalam counter Warning/Danger.
  - Menetapkan label tombol unmute secara baku menjadi **`🔔 Pantau Kembali`** pada semua templat UI dan skrip frontend.
- **Standarisasi Bahasa & UX Konsisten (Bahasa Indonesia Jernih & Kolom Tindakan)**:
  - Mengeliminasi pencampuran bahasa (Indo-Inggris) pada tooltip dan teks keterangan antarmuka (misalnya `"1 Layanan down diabaikan"` dan `"Layanan down tetapi alarm sedang diabaikan"` distandarisasi menjadi `"layanan berhenti (peringatan dibisukan)"` dan `"Layanan berhenti, peringatan dibisukan"`).
  - Standarisasi penamaan header kolom aksi pada seluruh tabel antarmuka sistem secara konsisten menjadi **"Tindakan"**.
- **Koreksi Status Mode Pemeliharaan (Maintenance State Isolation)**:
  - Menyelaraskan status server yang berada dalam mode pemeliharaan (`is_maintenance = True`) di semua halaman (Dashboard, Daftar Server, dan Rincian Server).
  - Backend FastAPI (`/api/servers`) memastikan `overall_status = "maintenance"` dan tidak ter-overwrite menjadi `"offline"` saat heartbeat server stale.
  - Antarmuka menampilkan indikator warna kuning berlabel tegas **"Pemeliharaan"** / **"pemeliharaan"** alih-alih berstatus online hijau yang menyesatkan.
- **Integrasi Tombol Tindakan Abaikan / Pantau Kembali di Tab Layanan (Cross-Tab Quick Actions)**:
  - Tombol tindakan `🔕 Abaikan` dan `🔔 Pantau Kembali` kini terintegrasi langsung pada kolom Tindakan di **Tab Layanan** (`services.html`), berdampingan dengan tombol kontrol Restart/Stop.
  - Operator tidak perlu lagi berpindah ke Tab Masalah hanya untuk membisukan peringatan layanan yang sedang down atau mengaktifkannya kembali.
  - Data referensi masalah layanan (`problem_id`, `problem_msg`, `ignored`) disertakan dalam payload overview dan dirender secara dinamis baik pada saat inisialisasi templat maupun saat live polling JavaScript (`renderServiceActions()`).
- **Mekanisme Siklus Hidup Restart Layanan yang Diabaikan**:
  - Jika layanan yang sedang diabaikan direstart dan sukses hidup kembali (`status == 'up'`), sistem deteksi otomatis (`sync_server_problems`) akan menutup dan menandai tiket masalah tersebut sebagai *resolved* (teratasi).
### Fase v3.16.0: Dukungan Socket Activation, Kontrol Abaikan Layanan Fleksibel & Transparansi Dashboard
- **Dukungan Socket Activation untuk Layanan (SSH Shutdown Aman):**
  - Perbaikan pada skrip pembantu agen `package/usr/local/sbin/pantau-restart` via fungsi `run_unit_with_socket()`.
  - Menghentikan dan menyalakan unit socket pendamping (seperti `ssh.socket` pada Ubuntu 22.04/24.04) saat perintah `stop`/`start`/`restart` dieksekusi, memastikan port (seperti port 22) benar-benar tertutup saat dihentikan.
- **Fitur Abaikan Layanan Fleksibel (Permanen / Berdasarkan Rentang Waktu):**
  - Penambahan kolom `is_ignored`, `ignored_until`, `ignored_by`, `ignored_reason`, dan `ignore_mode` pada tabel `services` serta migrasi otomatis via `migrate_service_ignored()`.
  - Dukungan mode abaikan permanen (hingga diaktifkan manual kembali), 2 jam, 24 jam, 7 hari, 30 hari, dan sekali saja (insiden).
  - Layanan on-demand yang berulang kali mati-hidup tidak lagi memunculkan false alarm baru ketika berstatus diabaikan.
  - Tombol aksi `🔕 Abaikan` dan `🔔 Pantau Kembali` dapat digunakan langsung dari Tab Layanan bahkan saat layanan sedang UP.
- **Transparansi Status Layanan di Dashboard:**
  - Kolom **Layanan** di Dashboard kini menampilkan pil rincian lengkap dalam satu tampilan:
    `[ X total ]` `[ Y up ]` `[ Z down ]` `[ W diabaikan 🔕 ]`.
  - Kolom **Masalah** menampilkan badge level keparahan berdampingan dengan pil status masalah yang diabaikan.
  - Kartu statistik atas kini menyertakan metrik **Layanan Diabaikan (🔕)** secara real-time.
- **Sinkronisasi Versi:**
  - Peningkatan versi Pantau Server dan Agen Pantau menjadi **v3.16.0**.

---

## 5. Bedah Teknis Komponen Kritis

### TerminalBridgeDispatcher & WebSocket Engine
Berada di [server/main.py](file:///home/bos/rj45/server/main.py):
- Kelas `TerminalBridgeDispatcher` mengelola *state* sesi terminal dalam memori (`sessions[server_id]`).
- Mencegah *race condition* dengan mengisolasi antrean masukan (`input_queue`) dan keluaran (`output_queue`).
- Otentikasi sesi WebSocket membaca cookie sesi admin; penolakan otomatis `403` jika bukan admin dan `409` jika server telah memiliki sesi terminal aktif.

### Wrapper Keamanan Sudoers
Berada di [package/usr/local/sbin/](file:///home/bos/rj45/package/usr/local/sbin/) dan [package/etc/sudoers.d/pantau-agent](file:///home/bos/rj45/package/etc/sudoers.d/pantau-agent):
- Pengguna `pantau` hanya diizinkan menjalankan 5 berkas wrapper tersebut dengan opsi `NOPASSWD`.
- Skrip wrapper memverifikasi argumen masukan sebelum meneruskannya ke perintah sistem untuk mencegah *command injection*.

### Normalisasi Service Systemd & Cgroup
- Saat agen memeriksa port yang terbuka (`ss -tulpn`), sistem seringkali hanya menemukan nama biner dasar (misal `master` untuk Postfix).
- Agen kini menelusuri cgroup systemd untuk mendapatkan nama unit `.service` yang valid sebelum dilaporkan ke dashboard, memastikan aksi Start/Stop/Restart di UI selalu mengarah ke unit yang benar.

### Sistem Retensi Basis Data Otomatis
Fungsi `_retention_prune()` di [server/main.py](file:///home/bos/rj45/server/main.py) dieksekusi secara asynchronous setiap jam:
```python
# Retensi:
# - login_attempts: 1 hari
# - metrics (raw): 2 hari (agregat per jam disimpan 90 hari)
# - request_logs: 30 hari
# - problems (resolved): 90 hari
# - command_history: 180 hari
# - audit_logs: 365 hari
```

---

## 6. Skema Basis Data & Konfigurasi

Basis data menggunakan MariaDB (`pantau_db`) dengan tabel-tabel utama:
- `servers`: Metadata server, status online, API key hash, mode maintenance.
- `server_extras`: Informasi tambahan (versi agen, top 20 processes JSON, OS label, kernel).
- `metrics`: Data riwayat kinerja (CPU, RAM, swap, load, disk, net).
- `metrics_hourly`: Agregasi kinerja jangka panjang.
- `services`: Unit layanan yang dimonitor per server beserta statusnya.
- `problems`: Rekam jejak alarm/kendala (level: Info, Warning, Danger, status ack/resolve).
- `audit_logs`: Jejak audit setiap aksi administratif pengguna.
- `users`: Pengguna dashboard (bcrypt password hash, role `admin` / `viewer`).
- `user_sessions`: Sesi login aktif berbasis basis data.

---

## 7. Panduan Rilis & Workflow Pengembangan

Ketika melakukan perubahan kode atau menambahkan fitur baru, ikuti checklist berikut:

1. **Sinkronisasi Versi:**
   - Ubah `APP_VERSION` pada [server/config.py](file:///home/bos/rj45/server/config.py).
   - Jika ada perubahan pada agen klien, ubah `AGENT_VERSION` pada [package/opt/pantau/agent/agent_pantau.py](file:///home/bos/rj45/package/opt/pantau/agent/agent_pantau.py).
2. **Sinkronisasi Skema Basis Data:**
   - Jika ada penambahan kolom/tabel pada `server/models.py`, perbarui juga berkas DDL [database/schema.sql](file:///home/bos/rj45/database/schema.sql).
3. **Pembaruan Dokumentasi Pengguna:**
   - Pastikan [README.md](file:///home/bos/rj45/README.md) diperbarui jika terdapat instruksi pengguna atau penambahan fitur baru yang berdampak ke operator/sysadmin.
4. **Pencatatan di DEVELOPMENT.md:**
   - Catat keputusan arsitektur baru, perbaikan bug kritis, atau perubahan protokol data pada berkas [DEVELOPMENT.md](file:///home/bos/rj45/DEVELOPMENT.md) ini.
5. **Git Commit, Tag & Push:**
   ```bash
   git add .
   git commit -m "feat/fix: <deskripsi perubahan>"
   # Jika rilis versi baru:
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin master --tags
   ```
