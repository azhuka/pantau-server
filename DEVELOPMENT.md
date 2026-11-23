# Panduan Arsitektur, Filosofi & Arah Pembangunan: Pantau Server

Berkas ini adalah **Manifes Rekayasa, Rujukan Arsitektur Utama, dan Peta Jalan Pembangunan Permanen** untuk proyek pembangunan ulang **Pantau Server** (`/home/bos/pantau-server`). Dokumen ini mencatat secara menyeluruh definisi, filosofi, fungsi, konsep dasar, dan arah evolusi sistem agar selalu menjadi kompas bagi seluruh pengembang dan arsitek perangkat lunak yang berkontribusi pada proyek ini.

> [!NOTE]
> Berkas ini berbeda fungsi dengan `README.md` (yang ditujukan bagi pengguna akhir/sysadmin) dan berkas aturan agen (`GEMINI.md` / `AGENTS.md` yang berfungsi sebagai tata kelola kendali asisten AI). Berkas ini adalah **buku putih arsitektur perangkat lunak (*software architecture whitepaper*)**.

---

## 1. Definisi, Identitas & Hakikat Sistem (System Essence)

### 1.1 Definisi
**Pantau Server** adalah platform pusat kendali operasional NOC (*Network Operations Center Control Plane*) generasi baru yang bertugas mengawal ketersediaan, performa, dan keamanan armada server Linux multi-node mandiri secara *real-time* dengan akurasi fisik tingkat kernel (*kernel-grade precision*).

### 1.2 Filosofi Dasar Rekayasa
1. **Pengendalian di Atas Sekadar Pengamatan (*Control Over Mere Monitoring*):** Pantau Server bukan sekadar penampil grafik metrik statis, melainkan stasiun kerja taktis tempat operator dapat melakukan investigasi mendalam dan mengambil tindakan mitigasi instan (menghentikan proses anomali, me-restart unit layanan bermasalah, memutus sesi penyusupan SSH) langsung dari antarmuka sentral.
2. **Kemandirian Tanpa Vendor Lock-In (*Self-Hosted Independence*):** Menolak ketergantungan pada layanan cloud berbayar atau SaaS pihak ketiga. Seluruh telemetri, basis data, dan kendali berada 100% di bawah kedaulatan infrastruktur pengguna sendiri.
3. **Kejujuran Data Mutlak (*Absolute Data Integrity — Zero-Fake Data*):** Sistem hanya menampilkan dan menyimpan fakta fisik yang diukur langsung dari kernel Linux (`/proc`, `/sys`, socket, systemd). Tidak ada tebak-tebakan, manipulasi visual semu, atau data buatan yang menyesatkan operator.
4. **Kesederhanaan Murni & Anti-Monolit (*Simplicity First & Anti-Monolith*):** Setiap modul perangkat lunak memiliki satu tanggung jawab yang jelas (*Single Responsibility Principle*). Mengharamkan penumpukan belasan ribu baris kode campuran HTML/JS/CSS ke dalam satu berkas raksasa.

### 1.3 Standar Perancangan & Batasan Arsitektur
- **Kematangan Workflow & UX Baku:** Konsep dasar, hierarki fitur, alur kerja operasional (*workflow*), dan pengalaman pengguna (*UX*) Pantau Server berakar pada standar operasional NOC mandiri yang dirancang matang, presisi, dan tangguh untuk pengawasan infrastruktur multi-node.
- **Standar Arsitektur Modular:** Memisahkan secara mutlak antara antarmuka visual (Vue 3 SPA, komponen terisolasi `<250` baris, Tailwind CSS v4, xterm.js) dan backend kontrol (FastAPI, SQLAlchemy, MariaDB/MySQL `pantau_db`).
- **Kompas Rekayasa Mutlak:** Seluruh rancangan modul dan alur interaksi operator wajib mengedepankan kepadatan data (*NOC Data Density*), kecepatan respons, stabilitas jangka panjang 24/7/365, dan kejujuran data fisik tanpa memperkenalkan abstraksi spekulatif atau alur kerja buatan yang tidak perlu.

---

## 2. Prinsip Arsitektur: Fondasi Clean Architecture & Pemisahan Tanggung Jawab

Pantau Server dirancang dari nol (*from first principles*) dengan standar rekayasa perangkat lunak kelas industri untuk menyelesaikan tantangan operasional NOC modern:
* **Anti-Monolitik Spaghetti:** Memisahkan secara tegas antara antarmuka visual (Vue 3 SPA komponen kecil <250 baris), pengontrol API (FastAPI Routers tipis), logika evaluasi telemetri (Domain Services murni), dan persistensi data (SQLAlchemy Repositories). Mengharamkan penumpukan kode campuran HTML, CSS, dan skrip ke dalam berkas monolitik raksasa.
* **Ergonomi Tanpa Disrupsi (*Zero-Disruption Navigation*):** Menolak keras pola navigasi halaman penuh (*full page reload*) saat memeriksa rincian host. Navigasi halaman penuh memutus sesi Web Terminal aktif, menghilangkan posisi scroll armada, dan membuang waktu investigasi operator.
* **Integritas Skema & Normalisasi Data:** Basis data menggunakan skema relasional InnoDB yang ternormalisasi secara ketat. Dilarang menyimpan telemetri penting ke dalam kolom JSON mentah tak berstruktur yang rentan korupsi dan tidak dapat diindeks.

---

## 3. Paradigma Inti Antarmuka & Interaksi NOC (Core Interaction Paradigm)

Sistem antarmuka Pantau Server mengadopsi standar kontrol taktis mutakhir:

### A. Jendela Kerja Mengambang (*Floating Workspace Modal*)
* **Inspeksi Mikro Tanpa Kehilangan Konteks Makro:** Jendela taktis interaktif berdimensi luas (`85vw x 85vh`) yang terbuka mengambang di atas dasbor armada tanpa berpindah halaman atau memutus koneksi terminal.
* **Host Switcher Terintegrasi:** Berpindah antar server secara langsung dari bilah atas modal menggunakan pintasan keyboard `[` dan `]` atau pencarian cepat, menghemat waktu triase insiden.
* **Workspace Shelf (Bilah Rak Bawah):** Kemampuan meminimalkan jendela kerja ke rak bawah layar saat memantau dasbor dan membukanya kembali seketika tanpa kehilangan status tab aktif atau posisi scroll.
* **Zero-Flicker Reactive Rendering:** Pembaruan data terjadi di memori Virtual DOM tanpa kedipan visual yang mengganggu mata saat telemetri masuk setiap 3–5 detik.

### B. Dasbor Triase Murni Pasif
* **Observasi Situasional 24/7/365:** Dasbor dikhususkan sebagai layar pemantauan makro, menampilkan banner KPI 3-kartu asimetris (Total Servers, Active Incidents 5-strip Zabbix, Jam Presisi Sistem) dan tabel insiden pasif. Dilarang keras menambahkan tombol aksi aktif atau mutasi di halaman dasbor.
* **Kesetaraan Wewenang Operasional (*RBAC Parity*):** Operator berakses penuh memiliki kesetaraan fungsional dalam melakukan kontrol teknis armada, dengan proteksi mutlak terhadap integritas akun master dan akun diri sendiri.

---

## 4. Arsitektur Perangkat Lunak (Clean Architecture Breakdown)

Sistem dibangun dengan pemisahan lapisan tanggung jawab yang ketat (*Strict Separation of Concerns*):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PRESENTATION LAYER (Vue 3 SPA)                         │
│  Navbar • DashboardView (Pasif) • FleetTableView • WorkspaceModal • i18n    │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ REST API (JSON) / WebSocket
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    TRANSPORT LAYER (FastAPI Routers)                        │
│          routers/servers.py • routers/problems.py • routers/auth.py         │
│          (Hanya memvalidasi request/response via Pydantic Schemas)          │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ DTOs / Business Calls
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                    BUSINESS DOMAIN & SERVICE LAYER                          │
│          services/server_service.py • services/problem_service.py           │
│        (Evaluasi anomali, ambang batas, kalkulasi metrik & orkestrasi)      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │ Session Queries / Commits
┌──────────────────────────────────────▼──────────────────────────────────────┐
│                  DATA PERSISTENCE LAYER (SQLAlchemy 2.0)                    │
│             models/server.py • models/problem.py • Clean Slate DB           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 4.1 Lapisan Antarmuka (Frontend - Vue 3 + Tailwind CSS + Vite)
* Dibangun sebagai Single Page Application (SPA) mandiri.
* Ukuran komponen dijaga modular (< 150–250 baris per sub-komponen).
* Desain visual bertema gelap pekat (*Tactical Slate NOC*): Kanvas `#06090f`, Kartu `#0c121e`, Garis tepi tegas `#1f2937`, dan aksen semantik status (*Emerald, Amber, Rose, Cyan*).
* **Standar Keterbacaan 100% Zoom (Anti-Pixel Blindness):**
  - Base font menggunakan Sans-serif modern (`Inter` / system UI) untuk kenyamanan baca jangka panjang.
  - Font Monospace dikhususkan hanya untuk nilai teknis: IP, port, PID, angka telemetri, dan kode status.
  - Dilarang keras menggunakan font mikroskopis (<12px). Seluruh hierarki teks (12px badge/label, 13.5px–14px isi tabel, 15px–16px judul, 24px–30px KPI) terbaca tajam pada skala 100%.

### 4.2 Lapisan Transportasi (Backend - FastAPI)
* Backend murni melayani REST API berotentikasi JWT dan WebSocket, tanpa me-render template HTML di sisi server (*no server-side Jinja rendering*).
* Routers bersifat tipis (*thin controllers*), hanya bertugas memetakan rute HTTP dan memvalidasi kontrak skema input/output.
* Penanganan aset statis dikompilasi ke direktori `frontend/dist/` dan disajikan langsung oleh FastAPI, menghasilkan **arsitektur binary/daemon tunggal** yang mudah dipelihara via `systemd`.

### 4.3 Kebijakan Penyimpanan Data Bersih (*Clean Slate Persistence*)
* Sistem beroperasi dengan skema mandiri yang dibangun bersih dari nol (*clean slate*).
* Basis data menggunakan skema relasional InnoDB yang ternormalisasi secara elegan, di mana relasi antar Server, Snapshot Metrik, Tiket Insiden, dan Log Audit terhubung dengan *foreign keys* yang valid dan integritas referensial yang kuat.

---

## 5. Spesifikasi Teknis Agen Klien (`agent_pantau`)

Daemon agen di server klien adalah ujung tombak pengumpulan telemetri armada. Agen dirancang dengan prinsip rekayasa presisi:
* **Zero External Dependencies:** Beroperasi murni menggunakan pustaka standar Python 3.10+ tanpa memerlukan dependensi paket pihak ketiga (seperti `psutil`, `requests`, atau `curl`).
* **Target Desain Ramping:** Berukuran ringkas (< 600–800 baris Python modular) dengan konsumsi memori sangat hemat (RAM < 15–20 MB) dan beban CPU terukur < 0.1%.
* **Prinsip Operasional Kernel Langsung:** Membaca data langsung dari kernel interface Linux (`/proc/stat`, `/proc/meminfo`, `/proc/net/dev`, socket netlink) tanpa memicu pemanggilan *subprocess* berulang-ulang yang memboroskan sumber daya sistem produksi.
* **Protokol Telemetri Asinkron:** Mengirimkan payload snapshot terkompresi secara berkala (default interval 5 detik) melalui HTTP POST aman ke endpoint `/api/report`, dan menerima instruksi kendali melalui `/api/commands`.

---

## 6. Standar Versi SemVer & Peta Jalan Fase Pengembangan

Penomoran versi proyek mengikuti kaidah **Semantic Versioning (SemVer)**: `vMAJOR.MINOR.PATCH`.
* **Baseline Saat Ini:** **`v0.1.0`** (Fondasi Arsitektur Bersih, SPA 4 Halaman, & API Inti).

```
FASE 1: Fondasi Arsitektur & Antarmuka Taktis Solid (Status: SELESAI v0.1.0)
  ├── Backend FastAPI modular & clean slate database isolation
  ├── Mesin multi-bahasa reaktif (i18n EN default + ID toggle)
  ├── Dasbor Makro Murni Pasif (DashboardView)
  ├── Inventaris Armada Berdensitas Tinggi (FleetTableView)
  ├── Log Audit Akuntabilitas (AuditView) & Pengaturan RBAC (SettingsView)
  └── Jendela Taktis Mengambang (ServerWorkspaceModal) + Bilah Rak (Shelf)

FASE 2: Pengayaan Sub-Panel Kontrol & Mitigasi Presisi (Fokus Aktif v0.2.0)
  ├── Sub-Tab Services: Filter status instan & kontrol restart aman
  ├── Sub-Tab Tasks: Inventaris top process & terminasi terproteksi (SIGTERM/SIGKILL)
  ├── Sub-Tab Ports: Pemetaan socket listening (Localhost vs Public Interface)
  ├── Sub-Tab Firewall: Pengelolaan rules UFW real-time
  ├── Sub-Tab Cron: Audit crontab user & systemd timers
  └── Sub-Tab Users & SSH: Deteksi sesi remote seketika & pemutusan instan

FASE 3: Terminal Web Interaktif & Pengelola Berkas Tingkat Lanjut (v0.3.0)
  ├── Konsol Terminal Web berbasis WebSocket + xterm.js (Keep-Alive saat diminimalkan)
  └── File Manager aman: penjelajahan direktori, audit izin chmod/chown, editor berkas aman

FASE 4: Keamanan Sistem (FIM) & Diagnostik Jaringan Antar-Armada (v0.4.0)
  ├── File Integrity Monitoring (FIM): deteksi modifikasi berkas biner/sistem
  └── Matriks latensi ping TCP/ICMP real-time antar-node armada

FASE 5: Hardening Produksi & Peluncuran Resmi (v1.0.0)
  ├── Pengalihan penuh lalu lintas operasional produksi ke Pantau Server baru
  └── Penonaktifan resmi daemon lama dengan jaminan zero-downtime
```

---

## 7. Konvensi Rekayasa & Standar Kontribusi Git

Seluruh commit ke repositori Git wajib menggunakan standar **Conventional Commits**:

```
<type>(<scope>): <deskripsi lugas dalam bahasa baku>

[catatan rincian jika ada]
```

* **Types:**
  - `feat`: Penambahan fitur atau kapabilitas baru.
  - `fix`: Perbaikan bug atau penanganan kesalahan logika.
  - `docs`: Pembaruan atau penambahan dokumentasi.
  - `refactor`: Restrukturisasi kode tanpa mengubah fungsionalitas eksternal.
  - `perf`: Optimasi performa dan efisiensi sumber daya.
  - `style`: Penyesuaian styling, indentasi, atau tipografi.
  - `chore`: Pemeliharaan dependensi, konfigurasi build, atau skrip pembantu.
* **Scope:** `ui`, `api`, `auth`, `agent`, `fleet`, `workspace`, `i18n`, `core`.
* **Contoh:** `feat(workspace): tambahkan konfirmasi terminasi proses pada sub-tab tasks (v0.1.0)`.

---

Dokumen ini menjadi pegangan permanen bagi kelangsungan evolusi **Pantau Server**. Setiap penambahan fitur atau perombakan kode wajib tunduk pada filosofi dan arah arsitektur yang telah ditetapkan dalam dokumen ini.

---

## Catatan Perubahan (Changelog)

### Versi v0.1.18

- Menyelaraskan basis data operasional utama backend ke pantau_db sehingga seluruh 10 server klien armada Linux aktif langsung terpantau secara real-time via daemon systemd resmi.\n- Menegakkan Kebijakan Kemurnian Dokumentasi (Zero-Mention Policy) pada README.md dan DEVELOPMENT.md.\n- Memperbarui sistem pelaporan insiden, durasi insiden aktif, dan tooltip tindakan pada modal diagnosa insiden.\n- Memperbarui pembukuan aturan permanen sistemik di GEMINI.md dan AGENTS.md.


### Versi v0.1.17

- Memperbaiki bug 405 Method Not Allowed pada /api/commands/{cmd_id}/status dan endpoint file/terminal requests agen.\n- Memodularisasi 11 sub-tab modal workspace ke komponen terpisah di components/workspace/tabs/ sesuai aturan arsitektur (<250 baris).\n- Menegakkan Quality Gate i18n Anti-Hardcode pada WorkspacePackagesTab dan menyinkronkan kamus bilingual en/id.\n- Menguji integritas sistem dan algoritma telemetri dengan tingkat kelulusan 100%.


### Versi v0.1.16

### v0.1.16 - Fix Workspace Detail is_online State & Live Badge Parity
- Memperbaiki endpoint get_server_detail di server/routers/servers.py agar menghitung dan menyertakan atribut is_online, is_proxmox_ha, is_isolated_net, tags, dan notes.
- Menambahkan fungsi pengaman isServerOnline() pada ServerWorkspaceModal.vue sehingga status node LIVE atau DOWN selalu teruji akurat secara matematis dari last_seen.
- Mengonfirmasi badge status host tampil hijau [● LIVE] 100% sinkron antara dasbor, tabel armada, dan modal rincian aset.


### Versi v0.1.15

### v0.1.15 - Algorithmic Hardening, Tier-Aware Triaging & Performance Optimization
- Memperbaiki taksonomi insiden 4-tingkat keparahan (info, warning, critical, danger) dan menerapkannya pada matrix kartu KPI dasbor serta badge baris tabel.
- Menerapkan proteksi keparahan berbasis tier aset (Server Produksi vs Non-Produksi) dengan eskalasi danger hanya untuk produksi vital.
- Menerapkan deteksi server offline (agent_stale) otomatis dengan pemulihan seketika saat agen melapor kembali.
- Mengeliminasi N+1 query pada list_servers() dengan teknik agregasi batch loading (Zero N+1 Query).
- Memperbaiki penanganan peluncuran Web Terminal pada path direktori tertentu dari Remote File Manager.
- Menambahkan penanganan long-poll pada endpoint file-requests dan terminal-requests agen klien untuk efisiensi CPU dan I/O daemon.
- Mengintegrasikan koleksi skill anti-slop lokal dan test suite integritas sistem.


### Versi v0.1.14

### v0.1.14 - Pure Live Telemetry Ingestion & Official Glossary Enforcement
- Menghapus seluruh aset dummy dari database (hanya menyisakan node aktif nyata dari telemetri agen fisik).
- Memperbaiki parsing telemetri di telemetry_service.py dan servers.py agar membaca payload system, disks, procs, services, dan top_procs dari pantau-agent.
- Membersihkan fallback dummy 35% dan 85 procs di frontend Vue SPA.
- Membukukan glosarium resmi taksonomi insiden dan hierarki pengguna di GEMINI.md dan AGENTS.md.


### Versi v0.1.13

- Dialog taktis durasi pemeliharaan terukur (30m, 1h rekomendasi, 4h, 24h, atau manual).\n- Input alasan pemeliharaan dan pencatatan audit log.\n- Auto-expiry di basis data saat batas waktu tercapai.\n- Peredaman evaluasi insiden/alarm baru di problem_service saat mode pemeliharaan aktif.\n- Indikator status amber di header workspace, toolbar, tabel armada, dan dasbor makro pasif.


### Versi v0.1.12

Mengintegrasikan aksi 'Open Web Terminal at this path' dan 'Open in Terminal' folder agar mengangkat Terminal Dock ke lapisan teratas dan otomatis mengeksekusi cd ke direktori target.


### Versi v0.1.11

Memperbaiki kalkulasi posisi dropdown menu aksi pada Remote File Manager agar otomatis membuka ke atas (drop-up) jika ruang di bawah terbatas sehingga seluruh aksi tetap utuh di layar.


### Versi v0.1.10

### v0.1.10 — Dynamic Bookmarks Discovery & Modern 3-Dots Action Dropdown File Manager
- **Dynamic Bookmarks Detection:** Eliminasi hardcoding path bookmark. Jalur seperti /var/www, /opt, /var/log, /tmp dipindai secara fisik pada host aset klien dan hanya ditampilkan jika direktori fisik terbukti ada.
- **Modern 3-Dots Row Action Trigger:** Mengganti tombol teks kaku dengan ikon 3-dots (...) yang ramping dan ergonomis pada setiap baris berkas/folder.
- **Complete File Workflows:** Melengkapi alur Copy, Cut, Paste (bilah tempel & clipboard banner), Duplicate (penamaan timestamp aman), dan Upload File biner/teks dengan modal terintegrasi.


### Versi v0.1.9

- **Automated Quality Gate Anti-Hardcode**: Mengintegrasikan tools/lint_i18n.py ke dalam sop_release.py untuk memblokir rilis jika ditemukan string teks statis di template Vue.
- **Pembersihan Total Teks Mentah**: Menyelaraskan seluruh label tabel dan elemen UI ke kamus reaktif useI18n().
- **Verifikasi Pipa Otomatis**: Uji kompilasi, linter i18n, API lifecycle, dan UI Headless Chrome lulus 100%.


### Versi v0.1.8

- **Penegakan English Default**: Seluruh nama kolom dan tombol File Manager kini baku menggunakan Bahasa Inggris (Name, Size, Permissions, Owner : Group, Modified, Actions, Actions ▾).
- **Integrasi useI18n()**: Menghapus seluruh hardcode teks lokal dan menggantikannya dengan pemetaan dinamis en.js & id.js.
- **Uji E2E Puppeteer**: Memperbarui test_file_manager_ui.js untuk memvalidasi kepatuhan teks Bahasa Inggris.


### Versi v0.1.7

- **Eliminasi Tombol Redundant**: Menghapus tombol aksi 'Open Directory' yang tidak perlu; navigasi folder murni melalui klik nama folder atau tautan .. (Parent Directory) sesuai standar ergonomi file manager Linux.
- **Standarisasi Dropdown Tindakan**: Menerapkan menu dropdown seragam 'Aksi ▾' pada kolom 'Tindakan' untuk berkas dan direktori.
- **Dukungan Rename & Chmod**: Menambahkan modal Rename dan Permissions serta endpoint backend /rename dan /chmod.


### Versi v0.1.6

- **Remote File Manager Modular**: Ekstraksi modal berkas ke komponen mandiri RemoteFileManagerModal.vue dengan reaktivitas Vue 3 dan Tailwind CSS.
- **Kepatuhan Alur Kerja File Manager Baku**: Menyelaraskan navigasi breadcrumbs, bilah pintas folder cepat, dan status bar penyimpanan.
- **Backend File Ops & Backup**: Menambahkan endpoint /touch, /mkdir, /rm, /download, dan mekanisme pencadangan otomatis .bak sebelum penimpaan berkas.
- **Uji E2E Otomatis**: Menambahkan test_file_manager.py dan test_file_manager_ui.js.


### Versi v0.1.5

- Sinkronisasi Agen Resmi: Menempatkan agent/agent_pantau.py resmi di dalam repositori pantau-server dengan toleransi pembacaan config lokal tanpa izin root.
- Autentikasi Fleksibel API Key: Mendukung pencocokan API key raw maupun format ber-hash sha256: pada endpoint /api/report dan /api/commands.
- Telemetri Real-time Mandiri: Menjalankan pelaporan telemetri real-time host ke daemon server secara mandiri.


### Versi v0.1.4

- Perbaikan DetachedInstanceError PTY: Menyimpan nilai string atribut server dan user sebelum db.close() agar tidak memicu pemutusan sesi WebSocket mendadak.
- Auto-Open Host Default: Tombol terminal di navbar kini otomatis membuka sesi untuk host pertama di armada secara instan.
- Verifikasi Interaktif PTY: Memvalidasi aliran I/O shell /bin/bash interaktif secara end-to-end dengan uji eksekusi perintah.


### Versi v0.1.3

- Global Multi-Tab Web Terminal Dock: Arsitektur terminal dock mengambang multi-tab berbasis xterm.js dan FitAddon dengan PTY interaktif via WebSocket (/ws/servers/{sid}/terminal).
- Keep-Alive Shelf Tray: Kemampuan meminimalkan terminal dock ke bilah rak bawah tanpa memutus sesi PTY atau koneksi WebSocket aktif.
- Eliminasi Form Input Tiruan: Menghapus total form input perintah statis di ServerWorkspaceModal dan mengarahkannya ke dock terminal global.
- Multi-Host Fleet Switcher: Tab switcher dengan indikator status koneksi (hijau = aktif, kuning = menyambung, merah = putus), pencarian host armada, dan penambahan tab dinamis.
- Kontrol Jendela Standar: Dukungan tombol Clear Screen, Minimize to Dock, Maximize/Restore, Pop-out Window, dan Close Tab.


### Versi v0.1.2

- Web Terminal Live Execution: endpoint eksekusi shell real-time (/api/servers/{sid}/terminal/exec) dengan audit log dan safety guardrails.
- Remote File Manager Backend: endpoint penjelajahan direktori (/files), pembacaan berkas (/files/content), dan penyimpanan modifikasi berkas (/files/save) terhubung ke sistem berkas nyata.
- Kontrol Operasional & Maintenance: endpoint toggle status maintenance mode (/maintenance) dan dispatch perintah update_os / upgrade_os.
- Kelengkapan Subtab Telemetri: penyambungan endpoint data packages, ssl, logs, dan fim pada modal kerja aset.


### Versi v0.1.1

- Standarisasi kontrol window chrome: tombol ikon persegi seragam dengan SVG external-link pada konsol Web Terminal dan File Manager.
- Eliminasi total emoji kartun di seluruh antarmuka dan standardisasi vektor SVG monokromatik.
- Penegakan proteksi murni pasif pada dasbor (eliminasi kolom aksi dan tombol View di dasbor, navigasi pasif klik-baris).
- Standardisasi tombol aksi rincian armada menjadi 'View' dengan SVG Eye.
- Perombakan total berkas README.md menjadi standar dokumentasi produksi profesional.
- Pemulihan skrip otomatisasi rilis SemVer dan sinkronisasi versi aplikasi.


### Versi v0.1.0

- Peletakan fondasi arsitektur bersih (*Clean Architecture*) FastAPI dan database relasional mandiri (`pantau_db`).
- Rancang bangun antarmuka SPA Vue 3 berbasis tema *Tactical Cyber Command Room*.
- Banner metrik KPI asimetris, dasbor insiden pasif, dan tabel inventaris armada.
- Modal kerja aset mengambang (*Workspace Controller*) dengan sistem rak bawah (*shelf tray*).

