# Hakikat & Arah Pengembangan Pantau Server (Software Engineering Perspective)

Dokumen ini adalah **Konstitusi Arsitektur dan Panduan Arah Pengembangan Permanen** untuk proyek pembangunan ulang **Pantau Server** (`/home/bos/pantau-server`). Seluruh pengembangan sistem, antarmuka, dan agen wajib berpedoman mutlak pada dokumen ini.

---

## 1. Hakikat Sistem (System Essence)
**Pantau Server bukan sekadar aplikasi web CRUD pemantauan biasa**, melainkan:
> **Pusat Kendali Operasional NOC (*Network Operations Center Control Plane*) Mandiri** yang bertugas mengawal ketersediaan, kestabilan, dan keamanan armada server Linux produksi selama 24/7/365 dengan presisi tingkat kernel (*kernel-grade precision*).

Sistem ini didesain khusus bagi tim NOC dan sysadmin untuk:
1. Mengawasi kesehatan armada server dari satu layar sentral secara *real-time*.
2. Mendeteksi anomali operasional dan keamanan secara instan (termasuk deteksi penyusupan atau sesi SSH manusia aktif).
3. Mengeksekusi tindakan mitigasi cepat (*fast remediation*) tanpa harus berpindah-pindah perkakas atau membuka terminal terpisah.

---

## 2. Hubungan dengan Aplikasi Referensi

### A. Pantau Server Lama (`~/rj45`) — Blueprint Fungsional & Domain Knowledge
* **Status:** Berfungsi sebagai **Blueprint Konseptual Murni** untuk seluruh kapabilitas fitur, alur kerja telemetri, dan domain bisnis NOC.
* **Yang Diadopsi & Dipertahankan (Konsep & Workflow Murni):**
  * Kelengkapan konsep fitur telemetri: Ringkasan Metrik, Systemd Units, Top Processes, Listening Ports, UFW Firewall, Crontab & Timers, User Accounts & Sesi SSH Aktif, FIM (File Integrity Monitoring), Probing jaringan, dan Audit Log.
  * Alur interaksi & tata kelola NOC: Dasbor pasif, jendela inspeksi taktis mengambang (*floating workspace modal*), RBAC parity.
  * Protokol konsep telemetri agen push (`POST /api/report` & `GET /api/commands`).
* **Yang Dilarang Keras & Ditinggalkan (Anti-Pola & Larangan Kontaminasi Data):**
  * ❌ *Larangan Keras Duplikasi / Sambungan Data Lama:* DILARANG KERAS mengimpor, menduplikasi, atau menyambungkan basis data lama (`pantau_db`) ke aplikasi baru. Database baru wajib *Clean Slate* agar inkonsistensi skema dan kekeliruan data historis lama tidak mengotori kemurnian sistem baru.
  * ❌ *Monolithic Spaghetti HTML/JS:* Mengharamkan berkas template tunggal belasan ribu baris (seperti `services.html` 15.537 baris) yang menggabungkan HTML, CSS, dan logika script tanpa batas.
  * ❌ *Full-Page Navigation Disruption:* Mengharamkan perpindahan halaman penuh saat memeriksa rincian server yang memutus sesi terminal, menghilangkan posisi scroll, dan memicu jeda muat ulang.
  * ❌ *Reactive Patching:* Mengharamkan penambalan lokal tanpa menguji daur hidup data end-to-end.

### B. Pantau Agentless Go (`~/pantau`) — Standar Emas Interaksi UI/UX
* **Status:** Berfungsi sebagai **Benchmark Interaksi Antarmuka & Ergonomi Pengguna**.
* **Yang Diadopsi & Direplikasi:**
  * ✨ **Floating Workspace Modal (`.modal-workspace`):** Alih-alih berpindah halaman atau URL penuh, inspeksi mendalam server dibuka melalui jendela mengambang interaktif berdimensi luas (`85vw` x `85vh`, rounded-xl, backdrop-blur) di atas dasbor armada.
  * ✨ **Host Switcher Terintegrasi:** Navigasi cepat antar server langsung dari header jendela mengambang via tombol Prev (`<` / `[`), Next (`>` / `]`), serta popover pencarian server tanpa perlu menutup jendela inspeksi.
  * ✨ **Kontrol Jendela Penuh:** Mendukung Minimalkan ke Bilah Rak (*Workspace Shelf*), Maksimalkan ke Layar Penuh (*Maximize / Restore*), dan Tutup cepat (`✕` / tombol `ESC`).
  * ✨ **Workspace Shelf (Bilah Rak Bawah):** Jendela inspeksi yang diminimalkan tersimpan rapi di bilah bawah layar, memungkinkan operator memantau dasbor armada dan membuka kembali jendela server dengan status tab & scroll yang tetap terjaga.
  * ✨ **Zero-Reload Tab Switching:** Seluruh sub-tab (Overview, Layanan, Proses, Port, Firewall, Cron, SSH, Terminal, Berkas) berpindah instan di memori klien.

---

## 3. Lima Pilar Strategis Rekayasa Sistem

### Pilar 1: Keandalan Ekstrem & Jejak Sumber Daya Rendah (*High Reliability, Low Footprint*)
* **Agen Klien (`agent_pantau.py`):** Wajib mempertahankan prinsip *zero external dependency* (murni pustaka standar Python 3.10+) dengan konsumsi RAM serendah mungkin (< 30–40 MB). Agen dilarang membebani server target produksi.
* **Server Pusat:** Backend FastAPI asinkron yang tangguh melayani semburan telemetri armada secara bersamaan tanpa *memory leak* dan tanpa *blocking I/O*.

### Pilar 2: Dekonstruksi Monolit Menuju Modularitas Murni (*Clean Architecture*)
* **Frontend:** Single Page Application (SPA) berbasis Vue 3 + Tailwind CSS.
  * Setiap tab dan fitur diisolasi dalam komponen kecil (< 150–250 baris).
  * State management reaktif di memori Virtual DOM, menghilangkan kedipan (*flicker*) saat data metrik diperbarui otomatis setiap beberapa detik.
* **Backend:** FastAPI terstruktur bersih (Routers → Services → Models → DB Pool).
  * Routers tipis hanya memvalidasi kontrak request/response.
  * Logika bisnis dan evaluasi anomali terisolasi di Service Layer (`telemetry_service.py`, `problem_service.py`).

### Pilar 3: Evolusi Bertahap Bebas Regresi (*Zero-Downtime & Zero-Regression*)
* Pembangunan dan pengujian berjalan berdampingan tanpa mengganggu layanan armada klien aktif.
* Database produksi (`pantau_db`) tetap terjaga integritasnya. Seluruh armada klien tetap dapat melapor dan menerima perintah tanpa gangguan.

### Pilar 4: Kepadatan Data & Ergonomi Operasional NOC (*High-Density & Zero-Flicker UX*)
* Tampilan visual dirancang untuk observasi cepat operator:
  * Informasi disajikan padat, proporsional, dan informatif (*high data density*).
  * Kontras multi-tema tajam dan ramah mata pada Dark Mode maupun Light Mode.
  * Tombol aksi kontrol dilengkapi umpan balik visual seketika.

### Pilar 5: Keamanan Berlapis & Kejujuran Data Fisik (*Security & Zero-Fake Data*)
* Sistem hanya merekam dan menampilkan fakta fisik riil dari kernel Linux (`/proc`, `/sys`, socket, systemd). Dilarang keras mengarang atribusi atau memalsukan status.
* Deteksi anomali kritis (seperti **Sesi Remote SSH Aktif**) diproses seketika sebagai insiden prioritas tinggi.
* Guardrails keamanan permanen: Backend menolak perintah berbahaya ke proses kritis (PID 1, sshd, agent daemon) dan direktori inti sistem operasi.

---

## 4. Pembagian Peran Kerja
1. **Operator (Pengguna):**
   * Peran: *Experiential Validator & Evaluator*.
   * Tugas: Mengawasi hasil pekerjaan melalui **Penglihatan (UI)** dan **Perasaan/Pengalaman (UX)**. Operator tidak dibebani pertanyaan teknis kode atau pilihan sintaks.
2. **AI Assistant (Antigravity):**
   * Peran: *Principal Software Engineer, System Architect, & Lead UI/UX Designer*.
   * Tugas: Mengambil kepemilikan teknis penuh (*full technical ownership*), mendiagnosis masalah hingga ke akar, merancang solusi komprehensif, mengeksekusi secara rapi di seluruh lapisan, dan menyajikan laporan arah pengembangan secara transparan dan lugas dalam Bahasa Indonesia yang baku dan terstruktur.
