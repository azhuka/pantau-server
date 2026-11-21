# MASTER PLAN: Pantau Server (Next-Generation NOC Control Plane)

**Dokumen Rujukan Utama & Aturan Baku Pembangunan Aplikasi**  
*Status: Disahkan sebagai Arsitektur Permanen & Cetak Biru Pengembangan*  
*Target: Sistem Kendali & Pemantauan Multi-Server Kelas Industri*

---

## 1. Filosofi & Hakikat Sistem

### 1.1 Hakikat Aplikasi
Pantau Server adalah **Pusat Kendali Operasional NOC (*Network Operations Center Control Plane*) Mandiri** untuk armada server Linux multi-node produksi.

Pantau Server **BUKAN**:
* Bukan aplikasi web CRUD standar.
* Bukan klon atau tiruan dangkal dari aplikasi generic web dashboard maupun Grafana.
* Bukan sekadar penampil grafik pasif, melainkan **platform kendali operasional aktif** yang memadukan pemantauan telemetri presisi kernel dengan eksekusi tindakan mitigasi cepat (*remediation*).

### 1.2 Nilai Rasa (*Feel*) & Pengalaman Pengguna (UX Target)
Aplikasi ini wajib memberikan rasa penggunaan yang:
1. **Solid & Berbobot:** Setiap elemen memiliki struktur tegas, tanpa animasi berlebihan yang memperlambat respon, dan tanpa jeda muat ulang yang memutus fokus operator.
2. **Profesional & Tenang:** Warna, tipografi, dan kontras dirancang ramah mata untuk pengawasan berjam-jam (anti-silau, anti-kebutaan piksel).
3. **Responsif & Presisi:** Pembaruan data metrik mengalir mulus tanpa kedip (*zero-flicker*); aksi kontrol memberikan umpan balik status seketika.
4. **Ergonomis:** Operator dapat beralih dari pengawasan armada makro (10+ server) ke inspeksi mikro (analisis proses atau sesi SSH pada 1 server) dalam hitungan milidetik tanpa kehilangan posisi kerja.

---

## 2. Bahasa Desain Visual & Ergonomi NOC (Bespoke UI Design System)

### 2.1 Palet Warna "Tactical Slate NOC"
Menolak palet warna generik/template cerah. Mengadopsi palet industri bertema gelap pekat dengan kontras fungsional tinggi:

* **Latar Belakang Dasar (Canvas):** `#080c14` (Hitam arang dingin, meminimalkan kelelahan mata OLED/IPS).
* **Kontainer & Kartu (Surface):** `#0f172a` (Deep Slate) dengan garis tepi tegas (`1px solid #1e293b`).
* **Header & Toolbar:** `#131d31` dengan elevasi visual subtil.
* **Aksen Semantik (Status-Driven Accents):**
  * *Normal / Sehat:* Emerald `#10b981` (Tegas, bukan neon mencolok).
  * *Peringatan / Siaga:* Amber `#f59e0b` (Untuk utilisasi tinggi 75–85% atau sesi SSH aktif).
  * *Bahaya / Kritis:* Rose-Crimson `#f43f5e` (Untuk node offline, beban > 85%, atau layanan down).
  * *Identitas & Jaringan:* Sky-Blue `#0ea5e9` & Cyan `#06b6d4` (Untuk IP address, port, dan interface).
  * *Aktivitas Sistem:* Violet `#8b5cf6` (Untuk cron jobs dan background timers).

### 2.2 Tipografi & Kepadatan Data (*Data Density*)
* **Tipografi UI:** Font Sans-serif bersih (`Inter`, `system-ui`) dengan bobot terukur (400 untuk pelengkap, 600 untuk label, 700 untuk judul).
* **Tipografi Data Teknis:** Font Monospace proporsional (`JetBrains Mono`, `Fira Code`, `ui-monospace`) untuk seluruh nilai teknis: Alamat IP, Port, PID, Angka Persentase, Ukuran Memori, dan Cap Waktu.
* **Tinggi Baris & Rapat Vertikal:**
  * Baris tabel berukuran 32–36px (rapat, terstruktur, bebas pemborosan ruang putih).
  * Informasi esensial tampil langsung di sel; detail sekunder (detik waktu penuh, path direktori panjang) diakses lewat tooltip melayang yang halus (`title="..."`).

### 2.3 Arsitektur Lapisan Antarmuka (Layered Ergonomics)
Antarmuka dibagi menjadi 4 lapisan kerja terpadu tanpa navigasi halaman penuh:

```
┌─────────────────────────────────────────────────────────────────┐
│ LAPISAN 1: Dasbor Armada Sentral (Global Fleet Matrix)           │
│ - Matriks kesehatan 10 server (Online, CPU, RAM, Uptime, Alert) │
│ - Bilah pencarian instan, filter grup & status                   │
│ - Pusat Tiket Insiden & Keamanan NOC                            │
└────────────────────────────────┬────────────────────────────────┘
                                 │ Mengklik Server
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAPISAN 2: Jendela Inspeksi Taktis (Tactical Workspace Modal)    │
│ - Mengambang luas di atas matriks armada (86vw x 86vh)          │
│ - Bilah Atas: Host Switcher terintegrasi (Prev [ / ] Next)      │
│ - Sub-Tab Khusus: Overview, Services, Procs, Ports, UFW, Cron,  │
│   Users & SSH, Terminal, File Manager                           │
│ - Kontrol: Minimize ke Rak (_), Maximize (⛶), Tutup (ESC)       │
└────────────────────────────────┬────────────────────────────────┘
                                 │ Diminimalkan
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│ LAPISAN 3: Bilah Rak Bawah (Workspace Shelf)                     │
│ - Rak mengambang di sudut bawah untuk server yang diminimalkan  │
│ - Memungkinkan operator memantau armada lain tanpa kehilangan   │
│   posisi kerja, scroll, atau tab server yang sedang diinspeksi  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Alur Kerja Operasional Multi-Server (Operational Workflows)

### 3.1 Alur 1: Pemindaian Situasional Cepat (3-Second Situational Awareness)
1. Operator membuka aplikasi: Dalam 3 detik pertama, status kesehatan seluruh armada (10 server) terbaca tuntas dari bilah ringkasan metrik dan warna indikator.
2. Anomali kritis (misalnya: Sesi Remote SSH Aktif pada server tertentu) langsung menyala di tab Insiden dengan lencana kuning-berkedip.

### 3.2 Alur 2: Triase Masalah & Tindakan Cepat (Incident Triage & Mitigation)
1. Tiket insiden mencantumkan detail teknis lengkap (User, IP asal, TTY, waktu koneksi).
2. Operator memiliki dua jalur:
   * **Jalur Cepat:** Klik tombol *"Putus Sesi SSH"* langsung dari kartu tiket insiden.
   * **Jalur Investigasi:** Klik tombol *"Inspeksi Server"* untuk membuka Jendela Taktis host tersebut, memeriksa proses apa yang sedang dijalankan oleh sesi tersebut di tab *Proses*, lalu memutus sesi secara terukur.

### 3.3 Alur 3: Navigasi Lintas-Armada Bebas Gangguan (Zero-Friction Host Flipping)
* Saat membuka Jendela Taktis pada Server A, operator dapat langsung melompat ke Server B atau Server C menggunakan tombol navigasi `◀` / `▶` (atau pintasan keyboard `[` dan `]`) atau *dropdown* pencarian cepat di bilah atas, tanpa perlu bolak-balik menutup dan membuka jendela.

### 3.4 Alur 4: Multitasking dengan Bilah Rak (Workspace Shelf)
* Operator sedang memeriksa log atau layanan pada Server A, tetapi ingin mengecek metrik Server B pada matriks armada.
* Operator menekan tombol minimalkan (`_`): Jendela Server A terlipat rapi menjadi *chip* aktif di pojok bawah.
* Operator leluasa meninjau matriks armada atau membuka Server B, lalu kapan saja dapat memulihkan Server A dengan sekali klik.

---

## 4. Arsitektur Teknis & Daur Hidup Data (Technical Blueprint)

### 4.1 Prinsip Desain: Clean Architecture & Anti-Monolith
* **Kemandirian Modul:** Seluruh komponen antarmuka (`.vue`) dibatasi maksimal 200–300 baris. Logika data, styling, dan template terisolasi rapi.
* **Backend Tanpa Render Template:** FastAPI 100% melayani murni REST API dan WebSocket; seluruh penyajian visual dikelola oleh Virtual DOM Vue 3.
* **Single Service Binary/Daemon:** Frontend dikompilasi ke aset statis (`dist/`) berukuran ultra-ringkas (< 200 KB) dan disajikan langsung oleh backend FastAPI sebagai satu daemon `systemd` yang ringan dan mandiri.

### 4.2 Daur Hidup Data (End-to-End Data Lifecycle)
1. **Physical Kernel Probing:** Agen (`agent_pantau.py`) membaca `/proc`, `/sys`, socket, dan `systemd` pada node klien.
2. **Secure Transport:** Telemetri dipaketkan dalam JSON ringkas dan dikirim via HTTP POST `/api/report` berotentikasi SHA256 API Key.
3. **Ingestion & Anomaly Evaluation:** Backend memvalidasi payload via Pydantic, memperbarui `sys_snapshots` dan `server_extras`, serta memicu `problem_service` untuk mengevaluasi ambang batas dan sesi SSH.
4. **Reactive Presentation:** Antarmuka SPA menyerap data via polling latar belakang/WebSocket, memperbarui Virtual DOM secara instan tanpa kedipan visual (*zero-flicker*).

### 4.3 Kebijakan Keamanan & Integritas Fisik (Zero-Fake Data & Safety Guardrails)
* **Kejujuran Data Mutlak:** Sistem hanya merekam data fisik yang terverifikasi. Tidak ada data fiktif atau rekaan.
* **Safety Guardrails:** Perintah kontrol ditolak permanen jika menargetkan:
  * PID 1 (`init` / `systemd`)
  * Daemon agen pemantau (`agent_pantau`)
  * Layanan kritis SSH host (`sshd`)
  * Jalur berkas sistem vital (`/boot`, `/etc/passwd`, `/etc/shadow`)

---

## 5. Peta Jalan Pengembangan Bertahap (Phased Roadmap)

```
FASE 1: Fondasi Arsitektur & Antarmuka Matriks Solid (Status: SELESAI & TERUJI)
  ├── Backend FastAPI modular (core, models, services, routers)
  ├── Isolasi basis data mandiri bersih (Clean Slate Persistence — larangan kontaminasi data lama)
  ├── Matriks Kesehatan Armada Klien (FleetTableView)
  ├── Pusat Tiket Insiden & Deteksi SSH Aktif (DashboardView pasif)
  └── Jendela Inspeksi Taktis Mengambang (ServerWorkspaceModal) + Bilah Rak

FASE 2: Pengayaan Sub-Panel & Ergonomi Kontrol Jendela (Fokus Saat Ini)
  ├── Sub-Tab Ringkasan: Visualisasi Gauge Utilisasi & Partisi Disk Presisi
  ├── Sub-Tab Layanan: Pencarian instan, filter status, kontrol Restart aman
  ├── Sub-Tab Proses: Monitoring CPU/RAM top processes & terminasi terproteksi
  ├── Sub-Tab Port: Audit socket listening (Local vs Public)
  ├── Sub-Tab Firewall: Pengelolaan rules UFW & status proteksi
  ├── Sub-Tab Cron: Inspeksi crontab & systemd timers terjadwal
  └── Sub-Tab Akun & SSH: Manajemen sesi remote aktif & terminasi instan

FASE 3: Terminal Web & Pengelola Berkas Tingkat Lanjut (Keep-Alive PTY)
  ├── Konsol Terminal Web interaktif berbasis xterm.js via WebSocket
  ├── Sesi terminal tetap hidup (keep-alive) saat jendela diminimalkan
  └── File Manager aman: penjelajahan direktori, izin chmod/chown, editor aman (.bak)

FASE 4: Keamanan Berkas (FIM) & Diagnostik Jaringan Antar-Armada
  ├── File Integrity Monitoring (FIM): deteksi perubahan berkas biner/sistem
  └── Matriks latensi ping ICMP/TCP antar-server armada

FASE 5: Hardening, Manajemen Akses (RBAC) & Pengujian Beban Produksi
  ├── Matriks hak akses operator (RBAC parity & proteksi akun)
  ├── Audit trail lengkap untuk setiap tindakan operator
  └── Pengalihan penuh lalu lintas produksi port 8400 ke arsitektur baru
```

---

## 6. Standar Penerimaan Operator (Definition of Done)
Sebuah fase atau fitur hanya dinyatakan selesai jika memenuhi 4 kriteria:
1. **Verifikasi Visual (UI):** Tampilan proporsional, rapi, kontras tajam ramah mata, tanpa elemen melayang yang menutupi konten.
2. **Verifikasi Pengalaman (UX):** Alur kerja mulus, waktu respon instan, navigasi intuitif, dan tidak ada aksi yang membuat operator bingung.
3. **Integritas Data:** Data yang disajikan 100% akurat sesuai fakta fisik kernel Linux server target.
4. **Stabilitas Produksi:** Armada klien aktif (10 server) beroperasi normal 100% tanpa gangguan (*zero-downtime*).
