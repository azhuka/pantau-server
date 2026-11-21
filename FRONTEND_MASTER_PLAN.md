# RENCANA INDUK PENGEMBANGAN FRONTEND (FRONTEND MASTER PLAN)
## Pantau Server: Next-Gen Cyber Operations & Tactical Control Center

**Dokumen Rujukan Desain Antarmuka & Ergonomi Visual Pengguna**  
*Konsep Visual: "Tactical Cyber Command Center / Ruang Operasi Intelijen"*  
*Prinsip Utama: Seluruh Alur Kerja (Workflow) Aplikasi Lama (~/rj45) adalah Blueprint Concept*  
*Aturan Baku Dasbor: Murni Aksi Pasif (Observasi & Navigasi). Bebas dari Tombol Kontrol/Mutasi Aktif*  
*Bahasa Default: English (Multi-Bahasa: EN / ID Toggle)*

---

## 1. Filosofi Estetika: "Tactical Cyber Command Room" (Nuansa Ruang Intelijen / Kontrol)

Bukan sekadar tema gelap datar (*flat dark theme*) yang kaku, melainkan antarmuka pusat kendali taktis (*tactical operations center*) yang memberikan sensasi berada di dalam **ruang kendali operasi siber (*cyber reconnaissance & control deck*)**:

### 1.1 Palet Warna & Atmosfer (Atmospheric Depth)
* **Kanvas Dasar (*The Void*):** `#06090f` (Obsidian hitam dingin dengan sentuhan mikro-grid taktis `rgba(56, 189, 248, 0.02)` menyerupai radar HUD).
* **Permukaan Kartu & Panel (*Carbon Slate*):** `#0c121e` hingga `#111a2d` dengan garis tepi berpresisi tinggi (`border: 1px solid rgba(51, 65, 85, 0.6)`).
* **Header & Toolbar Taktis:** `#0e1626` dengan aksen garis pemisah tipis *cyan* halus (`rgba(14, 165, 233, 0.3)`).
* **Aksen Semantik Berpendar (*Phosphor & Neon Luminescence*):**
  * **Status Normal / Sehat:** *Phosphor Emerald* (`#10b981`) — denyut hijau lembut yang stabil.
  * **Identitas & Telemetri:** *Cyber Sky / Cyan* (`#38bdf8`, `#06b6d4`) — untuk alamat IP, soket, dan fokus navigasi.
  * **Peringatan / Radar Manusia:** *Tungsten Amber* (`#f59e0b`, `#fbbf24`) — lampu kuning siaga saat mendeteksi sesi SSH manusia yang masuk ke server.
  * **Bahaya / Ancaman Kritis:** *Crimson Alert* (`#f43f5e`) — merah radar untuk node offline atau kelebihan beban kritis.
  * **Tugas Otomatisasi:** *Cryptic Violet* (`#a855f7`) — ungu untuk cron jobs dan systemd timers.

### 1.2 Detail Visual Taktis (Tactical Micro-Accents)
* **Lencana Sudut HUD (*Corner Bracket Accents*):** Sudut kartu penting memiliki aksen geometris halus ala konsol pemantauan satelit/server.
* **Denyut Detak Jantung (*Live Heartbeat Beacon*):** Lencana status node memiliki titik berpendar yang berdenyut (*pulse*) sinkron dengan siklus telemetri agen (setiap 3–5 detik), menegaskan bahwa armada terpantau secara aktif.
* **Tipografi Berdisiplin Ganda:**
  * Antarmuka umum: Font sans-serif tajam (*Inter / System UI*).
  * Data teknis (IP, Port, PID, Angka Persentase, Nilai Memori, Waktu): Font monospace proporsional (*JetBrains Mono / Fira Code*), dengan perataan tabular (*tabular figures*) agar angka tidak bergeser saat nilainya diperbarui.

---

## 2. Sistem Multi-Bahasa (*Multi-Language i18n: English Default & Indonesian*)

Aplikasi menggunakan **Bahasa Inggris secara default** agar terminologi komputasi/sysadmin terasa natural, ringkas, dan baku, dengan kemampuan beralih seketika ke **Bahasa Indonesia**:
* **Penyemat di Bilah Atas (Navbar):** Tersedia tombol sakelar taktis `[ 🌐 EN | ID ]`.
* **Mekanisme Reaktif (*Zero-Reload*):** Kamus kosakata disimpan di memori klien (Vue Reactive Dictionary). Saat bahasa dialihkan, seluruh teks berubah seketika tanpa memuat ulang browser, dan preferensi tersimpan di `localStorage`.

---

## 3. Peta Navigasi 4 Halaman Berbasis Blueprint Alur Kerja Lama

```
┌────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│ NAVBAR SENTRAL                                                                                         │
│ [⛊ PANTAU NOC]   [1: Dashboard]   [2: Fleet Inventory]   [3: Audit Trail]   [4: Settings]   [🌐 EN|ID] │
└────────────────────────────────────────────────────────────────────────────────────────────────────────┘
          │                   │                                  │                   │
          ▼                   ▼                                  ▼                   ▼
┌───────────────────┐ ┌────────────────────────────────────────┐ ┌─────────────────┐ ┌───────────────────┐
│ 1. DASHBOARD      │ │ 2. FLEET INVENTORY TABLE               │ │ 3. AUDIT TRAIL  │ │ 4. SETTINGS & RBAC│
│ (MURNI PASIF:     │ │ (Inventaris Lengkap - Belum Kontrol)   │ │ (Rekam Jejak    │ │ (Otoritas & Hak   │
│ Observasi Situasi │ │ - Tabel Kolom Rapat & Presisi          │ │  Aksi Operator) │ │  Akses Operator)  │
│ & Triage Pasif)   │ │ - Klaster Tombol Aksi ala Pantau:      │ │ - Timeline Aksi │ │ - Kelola Akun     │
│ - KPI Ribbon      │ │   [ View ] ────────┐                   │ │ - Aktor/User    │ │ - Izin Granular   │
│ - Insiden Terkini │ │   [ 📊 ] [ 🖥️ ]     │                   │ │ - Target Host   │ │ - Kunci API Agen  │
│ - Mini Fleet Grid │ │   [ 🔄 ] [ ⋮ ]     │                   │ │ - Parameter     │ │ - Thresholds      │
└───────────────────┘ └────────────────────┼───────────────────┘ └─────────────────┘ └───────────────────┘
                                           │ Klik [ View ] pada baris server
                                           ▼
                      ┌────────────────────────────────────────┐
                      │ JENDELA TAKTIS MENGAMBANG              │
                      │ (SATU-SATUNYA RANAH KONTROL AKTIF)     │
                      │ - Mengambang 86vw x 86vh               │
                      │ - Host Switcher Cepat: Tombol [ dan ]  │
                      │ - Sub-Panel: Overview, Services, Procs,│
                      │   Ports, Firewall, Cron, SSH, Terminal │
                      │ - Eksekusi Aksi Aktif: Restart Service,│
                      │   Kill Task, Sever SSH, Rules Firewall │
                      │ - Minimalkan ke Bilah Rak Bawah (_)    │
                      └────────────────────────────────────────┘
```

---

### DETAIL HALAMAN 1: DASBOR (DASHBOARD — MURNI PASIF)
*Persis seperti konsep dasbor lama `dashboard.html` di `~/rj45`. Dikhususkan sebagai layar pemantauan situasional dan triase pasif. DILARANG ADA TOMBOL AKSI AKTIF (seperti restart atau kill).*

1. **Bilah Kartu Ringkasan KPI (Atas):**
   * **Total Server:** Total armada terdaftar, rasio node online vs offline.
   * **Ringkasan Insiden:** Penghitung tiket aktif terpilah berdasarkan tingkat keparahan (*Critical, High, Warning, Info, Active SSH*).
   * **Jam Presisi NOC & Heartbeat:** Waktu sistem real-time dan latensi lapor telemetri.
2. **Kartu Insiden Terkini (*Recent Incidents Card* — Tabel Pasif):**
   * Persis format tabel insiden dasbor lama:
     * `WAKTU` (Waktu kejadian)
     * `SERVER` (Hostname & badge grup)
     * `KEPARAHAN` (Lencana Kritis, Gawat, Peringatan, Sesi SSH)
     * `DESKRIPSI INSIDEN` (Pesan anomali murni fakta kernel)
     * `DURASI` (Berapa lama insiden telah berlangsung)
     * `NAVIGASI` (Ikon panah halus `›` untuk membuka server terkait di ranah kontrol)
   * **Murni Pasif:** Tidak ada tombol mutasi atau eksekusi perintah di baris insiden dasbor.
3. **Matriks Armada Mini (*Mini Fleet Status Grid / Table*):**
   * Tampilan visual kartu/tabel ringkas seluruh node untuk pemindaian status 3 detik pertama.

---

### DETAIL HALAMAN 2: RINCIAN ARMADA (FLEET INVENTORY TABLE — BELUM KONTROL)
*Persis seperti tabel `servers.html` di `~/rj45`, menampilkan inventaris teknis lengkap seluruh armada. Kontrol aktif baru dimulai saat tombol aksi diklik.*

1. **Toolbar Atas:** Pencarian instan (Host, IP, OS, Grup), filter status cepat (`All`, `Online`, `Offline`, `SSH Active`).
2. **Tabel Rincian Armada (Kolom Padat & Presisi):**
   * `Status` (Titik hijau/merah berdenyut)
   * `Node / Server` (Hostname, grup, tier)
   * `Network (IP / Iface)` (Alamat IP & antarmuka fisik)
   * `Platform & Arch` (Baremetal/KVM/LXC, x86_64)
   * `OS & Kernel` (Distro Linux, versi kernel)
   * `CPU` (Model, Cores, bar utilisasi & Load Average)
   * `Memory` (RAM & Swap terpakai / total)
   * `Storage` (Partisi root `/` & persentase terpakai)
   * `Uptime` (Lama aktif sejak boot)
   * `Agent & Packages` (Versi agen & paket APT upgradable)
   * `Last Contact` (Waktu lapor relatif & latensi)
3. **Kolom Tindakan (*Action Cluster* per Baris ala Aplikasi Pantau):**
   * **`[ View / Buka Rincian ]`:** Membuka Jendela Kerja Taktis Mengambang untuk masuk ke **kontrol penuh**.
   * **`[ 📊 Metrics ]`:** Langsung membuka tab grafik telemetri.
   * **`[ 🖥️ Terminal ]`:** Langsung membuka konsol terminal web PTY.
   * **`[ 🔄 Sync / Probe ]`:** Meminta agen memindai seketika.
   * **`[ ⋮ More ]`:** Dropdown tindakan pendukung (*Edit Host, Catatan, Uji SSH, Maintenance Mode*).

---

### DETAIL JENDELA KERJA MENGAMBANG: SATU-SATUNYA RANAH KONTROL AKTIF
*Muncul mengambang di atas tabel armada (`86vw` x `86vh`) ketika tombol `[ View ]` diklik. Di sinilah satu-satunya tempat operator mengeksekusi kendali aktif.*

* **Host Switcher Terintegrasi:** Tombol `◀` / `▶` dan tombol keyboard `[` dan `]` untuk berpindah antar-server seketika tanpa menutup jendela.
* **10 Sub-Panel Kontrol Mandiri:**
  1. `Overview`: Gauges CPU, RAM, Swap, Disks, Hardware Specs.
  2. `Incidents`: Tiket masalah host aktif.
  3. `Services`: Manajemen systemd (**Aksi Aktif:** Restart, Start, Stop, Reload).
  4. `Tasks`: Proses Linux teratas & sinyal kill (**Aksi Aktif:** SIGTERM, SIGKILL terproteksi).
  5. `Ports`: Sockets listening (Local vs Public).
  6. `Firewall`: Aturan UFW (**Aksi Aktif:** Add rule, delete rule, block IP).
  7. `Automation`: Crontab & systemd timers.
  8. `Access & SSH`: Akun lokal & sesi remote SSH (**Aksi Aktif:** Putus Paksa Sesi SSH).
  9. `Web Terminal`: PTY console via WebSocket (**Aksi Aktif:** Terminal interaktif).
  10. `File Manager`: Penjelajah berkas (**Aksi Aktif:** Edit aman dengan `.bak`).
* **Bilah Rak Bawah (*Workspace Shelf*):** Jendela dapat diminimalkan (`_`) ke sudut kanan bawah agar operator bebas meninjau tabel armada dan membukanya kembali kapan saja.

---

### DETAIL HALAMAN 3 & 4: LOG AUDIT & PENGATURAN SISTEM
* **Halaman 3: Log Audit (Audit Trail):** Rekam jejak permanen seluruh aksi operator di armada (siapa, kapan, host target, jenis perintah, parameter, hasil eksekusi).
* **Halaman 4: Pengaturan (Settings & RBAC):** Manajemen operator, izin granular (`can_*`), dan token API agen.
