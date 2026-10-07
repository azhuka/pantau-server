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
7. [Standar Semantic Versioning (SemVer) Proyek](#7-standar-semantic-versioning-semver-proyek)
8. [Panduan Rilis & Workflow Pengembangan](#8-panduan-rilis--workflow-pengembangan)

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

### Fase v3.17.0: Pemantauan Infrastruktur Mendalam & Modernisasi UI/UX 2026
- **Pengawasan Throughput & Utilisasi Disk I/O Real-Time (`/proc/diskstats`):**
  - Agen menghitung delta laju baca/tulis (`Read / Write KB/s`), frekuensi operasi (`IOPS`), serta persentase keaktifan disk (`% I/O util`) tanpa modul eksternal.
  - Tabel Penyimpanan menyajikan metrik I/O real-time dengan kode warna ambang batas untuk mendeteksi *iowait* atau *disk bottleneck*.
- **Audit Log Galat Sistem Kritis (Systemd Journal Error Tracking):**
  - Tab baru **`📋 Log Sistem (Journal)`** menyajikan kejadian galat kritis sistem (`emerg`, `alert`, `crit`, `err`) via `journalctl -p 3 -o json`.
  - Berjalan aman dengan hak unprivileged di bawah grup `adm`.
- **Audit Port Listening & Proses Pengikat (`ss -tulpn`):**
  - Tab **`🔌 Port Listening`** mengaudit socket TCP/UDP aktif, proses pemilik, PID, dan klasifikasi keterbukaan akses (Publik vs Lokal/Loopback).
- **Pelacakan Masa Berlaku & Kedaluwarsa Sertifikat SSL/TLS:**
  - Tab **`🔒 Sertifikat SSL`** mendeteksi berkas sertifikat lokal, domain SAN, penerbit (CA), dan peringatan dini sebelum kedaluwarsa.
- **Pengelola Tugas Terjadwal (Cron & Systemd Timers) serta Firewall:**
  - Tab **`⏰ Tugas Terjadwal (Cron)`** memonitor jadwal cron crontab dan timer systemd.
  - Tab **`🛡️ Firewall`** menginspeksi status UFW/iptables dan daftar IP terblokir.
- **Modernisasi UI/UX Menyeluruh (Standar Enterprise Modern 2026):**
  - Palette tema dark yang lebih cerah, bersih, dan kontras dengan aksen neon lembut.
  - Floating glassmorphic tooltip engine responsif berkecepatan tinggi.
  - Hero toolbar dengan pengelompokan tombol terpadu (kontrol OS dan utilitas server).
- **Sinkronisasi Versi:**
  - Peningkatan versi Pantau Server dan Agen Pantau menjadi **v3.17.0**.

### Fase v3.18.0: Pengelolaan Visual Firewall & Mitigasi Cepat
- **Kontrol Penuh Firewall UFW:**
  - Penambahan tombol visual Aktifkan Firewall (`enable`), Nonaktifkan (`disable`), dan Muat Ulang Aturan (`reload`) pada Tab Firewall.
  - Fail-safe proteksi otomatis: membukakan akses port SSH (`22`), Dashboard Pantau (`8400`), HTTP (`80`), dan HTTPS (`443`) sebelum UFW diaktifkan.
- **Blokir & Buka Blokir IP Manual:**
  - Tombol modal "+ Blokir IP Baru" dengan validasi input IPv4 aman (mencegah blokir localhost/RFC1918/IP server).
  - Tombol aksi "Buka Blokir" (*unblock*) langsung per baris tabel IP yang ter-drop pada kernel iptables.

### Fase v3.19.0: Hentikan Proses Teratas (Process Termination / Kill Manager)
- **Tombol Aksi Kill per Baris Proses:**
  - Menambahkan kolom **Aksi (Kill)** pada tabel 5 & 20 proses penggunaan CPU dan Memori tertinggi.
- **Modal Dialog & Pemilihan Sinyal Aman:**
  - Pilihan sinyal **SIGTERM (15 - Hentikan Normal)** untuk penutupan proses bersih atau **SIGKILL (9 - Paksa Hentikan)** untuk proses yang hang/macet.
- **Proteksi Pengaman Sistem (*Kernel & Infra Guard*):**
  - Deny-list ketat di wrapper `pantau-restart kill`: memblokir pembunuhan PID 1 (`systemd`/`init`), proses SSH (`sshd`), dan proses agen monitor itu sendiri (`agent_pantau`).
- **Peningkatan Versi:**
  - Sinkronisasi versi server dan agen ke **v3.19.0**.

### Fase v3.20.0: Manajer Tugas Interaktif (Task Manager btop-style) & Penyatuan Masalah & Tindakan
- **Penyatuan Tab Riwayat Tindakan & Masalah (Masalah & Tindakan):**
  - Kartu Riwayat Tindakan dipindahkan dari tab Layanan ke dalam tab **Masalah & Tindakan**, menciptakan tab aktivitas terpadu yang memisahkan audit log eksekusi dari tabel konfigurasi layanan.
  - Tampilan tab Layanan menjadi lebih fokus, bersih, dan ringkas.
- **Redesain Tab Manajer Tugas (Task Manager ala btop):**
  - Perubahan nama tab: `Proses Teratas` $\rightarrow$ **`Manajer Tugas`**.
  - Tampilan awal default: **10 proses** teratas yang berjalan di server.
  - **Pilihan Limit / Pagination Modern:** tombol segmen cepat untuk menampilkan **10, 25, 50, 100, atau Semua** proses secara instan.
  - **Pengurutan Fleksibel:** dapat diurutkan berdasarkan konsumsi CPU tertinggi (`🔥 CPU`) atau konsumsi Memori tertinggi (`💾 Memori`).
  - **Pencarian Real-Time:** kotak pencarian instan berdasarkan nama proses (`comm`), nomor PID, atau user pemilik proses.
  - **Status Siklus Hidup Proses Linux (State Indicator):**
    - `R` (Running / Berjalan - badge hijau)
    - `S` (Sleeping / Menunggu - badge abu-abu)
    - `T` (Stopped / Ditangguhkan - badge kuning)
    - `Z` (Zombie - badge merah)
  - **Kontrol Sinyal Lengkap (Start / Pause / Kill):**
    - Tombol **Pause (`SIGSTOP` / 19)** untuk menangguhkan alokasi CPU proses sementara tanpa mematikannya.
    - Tombol **Lanjut / Resume (`SIGCONT` / 18)** untuk melanjutkan kembali proses yang sedang ditangguhkan.
    - Tombol **Kill (`SIGTERM` / `SIGKILL`)** dengan modal dialog interaktif.
    - Perlindungan deny-list tetap aktif untuk PID 1, `sshd`, dan `agent_pantau`.
- **Peningkatan Versi:**
  - Sinkronisasi versi server dan agen ke **v3.20.0**.

### Patch v3.20.1: Perbaikan Sintaks Templat services.html (Fix HTTP 500)
- **Perbaikan Bug TemplateSyntaxError:**
  - Menutup blok kondisional `{% if services %}` dan `{% if rows %}` dengan `{% endif %}` yang sebelumnya terpotong saat reorganisasi tab.
  - Mengatasi galat *Internal Server Error 500* ("Terjadi Kendala Sesaat (500)") saat mengakses halaman rincian server (`/servers/{id}/services`).
- **Peningkatan Versi:**
  - Sinkronisasi patch versi server dan agen ke **v3.20.1**.

### Minor Release v3.22.0: Best-Practice UI/UX Sysadmin, Pengurutan Interaktif Manajer Tugas & Dual Pagination
- **Penyempurnaan Penempatan & Glosarium Multi-Bahasa:**
  - Memindahkan tombol peralihan bahasa (`ID` / `EN`) ke header *sidebar brand* (sejajar dengan logo/toggle sidebar) sesuai best-practice antarmuka dashboard modern.
  - Menyesuaikan peristilahan kontekstual dunia sysadmin:
    - `Port Listening` (ID) / `Listening Ports` (EN) alih-alih port terbuka secara harfiah.
    - `Riwayat & Masalah` (ID) / `History & Incidents` (EN).
    - `Audit Trail`, `Log Aktivitas`, dan `Akun Pengguna`.
- **Restrukturisasi Urutan Tab Standar Sysadmin:**
  - Menempatkan tab `Riwayat & Masalah` tepat setelah tab `Kinerja` agar insiden dan kejadian penting dapat dipantau langsung setelah metrik performa utama.
  - Urutan tab terpadu: `Kinerja` | `Riwayat & Masalah` | `Layanan` | `Manajer Tugas` | `Akun Pengguna` | `Port Listening` | `Firewall` | `Sertifikat SSL` | `Tugas Terjadwal` | `Logging`.
- **Pengurutan Kolom Interaktif Manajer Tugas (Task Manager):**
  - Menghilangkan tombol terpisah "Urutkan: CPU / Memori".
  - Mengimplementasikan pengurutan langsung dengan mengklik header tabel kolom (`PID`, `User`, `Nama Perintah / Proses`, `Status`, `%CPU`, `%Memori`).
  - Indikator visual panah urutan interaktif (`▲` Ringan / A-Z, `▼` Berat / Z-A, `↕` Netral).
  - Urutan default saat load: `%CPU` terbesar ke terkecil (`▼`).
- **Dual Dropdown Pagination Modern:**
  - Menyediakan dropdown pemilihan limit proses (`20 proses`, `50 proses`, `100 proses`, `Semua proses`) di *toolbar* atas maupun *footer* bawah tabel.
  - Sinkronisasi instan dua arah antara dropdown atas dan bawah. Nilai bawaan default diatur ke 20 proses.
- **Perbaikan Akurasi Titik Indikator Tab Logging:**
  - Memperbaiki perhitungan titik merah berkedip pada tab `Logging`. Indikator kini hanya aktif jika terdapat galat kritis baru (`priority <= 3`) yang terjadi dalam rentang **2 jam terakhir** (mencegah false-positive akibat log lama berminggu-minggu lalu).
- **Peningkatan Versi:**
  - Peningkatan versi aplikasi dashboard dan agen pantau ke **v3.22.0**.

### Minor Release v3.21.0: Multibahasa (ID/EN), Logging Terpadu, Tab Neon Blue & Indikator Titik Peringatan
- **Fitur Dwi-Bahasa (Bilingual ID & EN):**
  - Switcher bahasa interaktif di sidebar (`ID` / `EN`) dengan persistensi `localStorage`.
  - Dukungan kamus translasi dinamis (`APP_TRANSLATIONS`) untuk navigasi sidebar, judul tab, status kesehatan sistem, dan label komponen.
- **Restrukturisasi & Penamaan Tab Baku:**
  - Susunan tab terstandardisasi: `Kinerja` | `Layanan` | `Manajer Tugas` | `Akun` | `Port Terbuka` | `Firewall` | `Sertifikat SSL` | `Tugas Terjadwal` | `Logging` | `Aktivitas & Masalah`.
  - Penamaan tab diperbarui: `Masalah & Tindakan` $\rightarrow$ **`Aktivitas & Masalah`**, `Port Listening` $\rightarrow$ **`Port Terbuka`**.
- **Penyatuan Logging Sistem & Layanan (Unified Logging Tab):**
  - Menggabungkan log unit layanan dan log galat sistem (journald) ke dalam 1 tab **Logging** yang bersih dengan *segmented control* switch cepat (⚙️ Log Layanan | 📋 Log Sistem Journal).
  - Integrasi pintasan `jumpToLog(unit)` yang otomatis beralih ke sub-tampilan Log Layanan dan fokus ke kartu log.
- **Konsistensi Tampilan Tab (Tema Biru Neon Terpadu):**
  - Menghapus pewarnaan tab lama yang acak/berbeda-beda. Seluruh tab yang aktif kini menggunakan palet modern **Biru Neon** (`#38bdf8`) dengan efek glow halus, bottom highlight bar, dan glassmorphism.
- **Indikator Titik Peringatan Berkedip pada Tab (Blinking Alert Dots):**
  - Penambahan animasi titik indikator berkedip (`.tab-warn-dot`) pada setiap tab:
    - `Kinerja`: menyala jika CPU > 85%, Memori > 90%, atau Load tinggi.
    - `Layanan`: menyala jika ada layanan penting yang down (tidak dibisukan).
    - `Aktivitas & Masalah`: menyala jika terdapat tiket masalah aktif yang belum selesai.
    - `Manajer Tugas`: menyala jika terdapat proses zombie atau beban ekstrem.
    - `Firewall`: menyala jika firewall terdeteksi tidak aktif.
    - `Sertifikat SSL`: menyala jika sertifikat mendekati kedaluwarsa atau telah kedaluwarsa.
    - `Tugas Terjadwal`: menyala jika terdapat cron job yang gagal.
    - `Logging`: menyala jika sistem mencatat galat kritis/error (journalctl priority $\le$ 3).
- **Kejelasan Riwayat Tindakan di Tab Aktivitas & Masalah:**
  - Penataan tabel Riwayat Tindakan yang berdampingan dan jelas di dalam tab **Aktivitas & Masalah**, lengkap dengan counter total tindakan dan pembaruan real-time saat polling.
- **Peningkatan Versi:**
  - Peningkatan versi aplikasi dashboard dan agen pantau ke **v3.21.0**.

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

---

## 7. Standar Semantic Versioning (SemVer) Proyek

Proyek **Pantau Server** dan **Agen Pantau** mengadopsi standar **Semantic Versioning (SemVer)** dengan format:

$$\textbf{vMAJOR . MINOR . PATCH}$$

Setiap perubahan kode yang dirilis **wajib dievaluasi tingkat dampaknya** oleh developer/AI assistant untuk menentukan kenaikan versi:

### 1. MAJOR (Angka Pertama, contoh: `v3.0.0` $\rightarrow$ `v4.0.0`)
- **Kapan dinaikkan:**
  - Terjadi perubahan arsitektur besar-besaran (*major architectural overhaul*).
  - Terjadi perubahan protokol komunikasi atau skema data yang **tidak kompatibel mundur (*breaking change*)** (misal agen lama tidak dapat berkomunikasi tanpa migrasi).
  - Transformasi paradigma produk (misalnya: evolusi penuh dari sekadar sistem *monitoring* baca-saja menjadi pusat kendali operasional visual penuh *management & control center*).
- **Aturan:** Reset `MINOR` dan `PATCH` menjadi 0.

### 2. MINOR (Angka Kedua, contoh: `v3.17.0` $\rightarrow$ `v3.18.0`)
- **Kapan dinaikkan:**
  - Penambahan **fitur baru atau kapabilitas operasional baru (*new feature*)** yang tetap kompatibel mundur (*backward-compatible*).
  - Contoh: Penambahan modul aksi tab Firewall (Block manual, Unblock, Enable/Disable UFW, Reload), penambahan handler kill process, manajemen sertifikat SSL baru, dll.
  - Perubahan atau pengayaan fungsionalitas yang substansial pada modul yang ada.
- **Aturan:** Reset `PATCH` menjadi 0.

### 3. PATCH (Angka Ketiga, contoh: `v3.18.0` $\rightarrow$ `v3.18.1`)
- **Kapan dinaikkan:**
  - **Perbaikan kesalahan (*bugfix*)**, penambalan celah keamanan minor, koreksi logika yang salah tanpa menambah konsep fitur baru.
  - Perbaikan styling/CSS, tooltip, perbaikan salah ketik (*typo*), atau penyesuaian aturan firewall bawaan (misal memastikan port 8400 otomatis terbuka saat UFW aktif).
- **Aturan:** Angka `MAJOR` dan `MINOR` tetap, angka `PATCH` ditambah 1.

---

## 8. Panduan Rilis & Workflow Pengembangan

Ketika melakukan perubahan kode atau menambahkan fitur baru, ikuti checklist berikut:

1. **Evaluasi & Sinkronisasi Versi:**
   - Evaluasi apakah perubahan termasuk `PATCH`, `MINOR`, atau `MAJOR`.
   - Ubah `APP_VERSION` pada [server/config.py](file:///home/bos/rj45/server/config.py).
   - Jika ada perubahan pada agen klien atau protokol perintah, ubah `AGENT_VERSION` pada [package/opt/pantau/agent/agent_pantau.py](file:///home/bos/rj45/package/opt/pantau/agent/agent_pantau.py).
   - **PENTING**: Jika server lokal (`rj45`) menjalankan agen produksi lokal, salin file agen ke `/opt/pantau/agent/agent_pantau.py` dan restart servicenya:
     ```bash
     sudo cp package/opt/pantau/agent/agent_pantau.py /opt/pantau/agent/agent_pantau.py
     sudo systemctl restart agent_pantau.service
     sudo systemctl restart pantau-server.service
     ```
2. **Sinkronisasi Skema Basis Data:**
   - Jika ada penambahan kolom/tabel pada `server/models.py`, perbarui juga berkas DDL [database/schema.sql](file:///home/bos/rj45/database/schema.sql).
3. **Pembaruan Dokumentasi Pengguna:**
   - Pastikan [README.md](file:///home/bos/rj45/README.md) diperbarui jika terdapat instruksi pengguna atau penambahan fitur baru yang berdampak ke operator/sysadmin.
4. **Pencatatan di DEVELOPMENT.md:**
   - Catat rincian fitur atau bugfix pada riwayat perubahan [DEVELOPMENT.md](file:///home/bos/rj45/DEVELOPMENT.md).
5. **Git Commit, Tag & Push:**
   - **Wajib sertakan git tag resmi** untuk setiap rilis versi:
   ```bash
   git add .
   git commit -m "feat/fix: <deskripsi perubahan>"
   git tag -a vX.Y.Z -m "Release vX.Y.Z"
   git push origin master --tags
   ```
