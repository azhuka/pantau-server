# Catatan Perubahan Versi Pantau Server

Dokumen ini memuat catatan riwayat perubahan, penambahan fitur, serta perbaikan sistem untuk setiap versi aplikasi **Pantau Server** dan **Agen Pantau**.

---

## Versi 4.0.0

### Rilis Mayor & Penambahan Fitur Manajemen Sistem Interaktif
- **Manajemen Akun Pengguna (System Users):**
  - Pembuatan akun pengguna sistem baru.
  - Penguncian akun (lock), pembukaan kunci akun (unlock), dan penghapusan akun.
  - Proteksi otomatis terhadap akun sistem dan root.
- **Manajemen Tugas Terjadwal (Cron Jobs):**
  - Penambahan jadwal cron baru (mendukung ekspresi standar).
  - Kemampuan untuk mengaktifkan/menonaktifkan (toggle), menghapus, dan mengeksekusi langsung tugas cron (*Run Now*).
- **Manajemen Port Terbuka (Listening Ports):**
  - Aksi interaktif untuk menghentikan proses (*Kill Process*) yang menduduki port.
  - Aksi interaktif untuk memblokir port secara langsung melalui UFW (*Block Port*).
- **Manajemen Sertifikat SSL:**
  - Penambahan pantauan path sertifikat SSL kustom.
  - Penghapusan pantauan sertifikat SSL kustom.
- **Peningkatan Kapabilitas Agen & Keamanan:**
  - Pembaruan *wrapper* sudo (`pantau-user`, `pantau-cron`, `pantau-ssl`, `pantau-firewall`) untuk eksekusi perintah secara aman dengan hak akses minimal yang terukur.
  - Penambahan pendeteksian status akun terkunci (*locked user*) dan tombol aksi buka kunci (*unlock*) secara interaktif.
  - Pembaruan skrip penginstal agen klien (`package/install.sh`) agar memasang seluruh biner pendukung secara otomatis.
- **Penerapan Dwi-Bahasa Penuh untuk Seluruh Komponen v4.0.0:**
  - Pemutakhiran kamus terjemahan untuk seluruh formulir modal, tombol aksi, dan badge fitur baru (ID/EN).
- **Pemutakhiran Nama & Konsistensi:**
  - Konsistensi penggunaan Bahasa Indonesia formal di seluruh dokumen rilis, terkecuali nama aplikasi **Pantau Server** yang dipertahankan.

---

## Versi 3.23.0

### Fitur Baru & Peningkatan
- **Ekspansi Sistem Dwi-Bahasa (Indonesia & Inggris) Menyeluruh:**
  - Penerapan penerjemahan teks dinamis ke seluruh antarmuka sistem (dasbor kesehatan server, daftar server, bilah pencarian, kartu metrik, header tabel, tombol aksi, dan pesan status).
  - Penyesuaian peristilahan kontekstual sysadmin (*Listening Ports*, *History & Incidents*, *Task Manager*, *User Accounts*, *Audit Trail*).
  - Penambahan pengamat mutasi DOM (*MutationObserver*) agar elemen yang diperbarui secara langsung melalui mekanisme *live polling* tetap konsisten dalam bahasa yang dipilih tanpa kembali ke bahasa asal.
- **Paginasi Komprehensif pada Tab Riwayat & Masalah:**
  - Penambahan kontrol batas tampilan ganda (di bagian atas dan bawah tabel) untuk tabel **Status Masalah** dengan opsi 5 masalah (bawaan), 10 masalah, 25 masalah, 50 masalah, dan Semua masalah.
  - Penambahan kontrol batas tampilan ganda untuk tabel **Riwayat Tindakan** dengan opsi 10 tindakan (bawaan), 25 tindakan, 50 tindakan, 100 tindakan, dan Semua tindakan.
  - Navigasi halaman terpadu yang dilengkapi tombol *Sebelumnya*, nomor *Halaman*, tombol *Berikutnya*, serta informasi jumlah data yang ditampilkan.
- **Pembersihan Efek Visual Tab Aktif:**
  - Penghapusan animasi titik berkedip pada tab yang sedang aktif untuk menyajikan tampilan yang lebih bersih, tenang, dan profesional.
- **Modernisasi Sub-Tombol Logging:**
  - Penyelarasan tampilan tombol sub-panel *Log Layanan* dan *Log Sistem (Journal)* dengan tema biru neon modern.
- **Standardisasi Dokumentasi:**
  - Penulisan seluruh panduan dan catatan rilis menggunakan kaidah Bahasa Indonesia yang baku dan lugas.

---

## Versi 3.22.0

### Peningkatan Antarmuka & UX
- **Reposisi Pengubah Bahasa:**
  - Tombol pengubah bahasa (*ID / EN*) dipindahkan ke area header sidebar sejajar dengan nama brand untuk aksesibilitas yang lebih cepat dan ergonomis.
- **Restrukturisasi Urutan Tab Sysadmin:**
  - Tab *Riwayat & Masalah* ditempatkan tepat setelah tab *Kinerja* agar operator dapat langsung meninjau insiden penting setelah memeriksa performa server.
  - Susunan tab: *Kinerja* | *Riwayat & Masalah* | *Layanan* | *Manajer Tugas* | *Akun Pengguna* | *Port Listening* | *Firewall* | *Sertifikat SSL* | *Tugas Terjadwal* | *Logging*.
- **Pengurutan Kolom Interaktif pada Manajer Tugas:**
  - Pengurutan langsung dilakukan dengan mengeklik header kolom tabel (*PID*, *User*, *Nama Perintah / Proses*, *Status*, *%CPU*, *%Memori*) dengan indikator panah naik (▲) dan turun (▼).
- **Paginasi Ganda Manajer Tugas:**
  - Penyediaan menu pilihan batas baris di bagian atas dan bawah tabel proses secara tersinkronisasi.
- **Akurasi Indikator Peringatan Tab Logging:**
  - Titik merah berkedip pada tab *Logging* hanya diaktifkan jika terdapat catatan galat sistem berkategori kritis (*priority* $\le$ 3) dalam rentang 2 jam terakhir untuk menghindari alarm palsu dari log lama.

---

## Versi 3.21.0

### Fitur Baru
- **Dukungan Dwi-Bahasa (Bilingual ID & EN):**
  - Implementasi pengalihan bahasa antarmuka secara instan dengan penyimpanan preferensi pada peramban (*localStorage*).
- **Penyatuan Logging Sistem & Layanan:**
  - Penggabungan log unit systemd dan log journald ke dalam satu tab terpadu dengan navigasi tombol alih cepat.
- **Standardisasi Tema Visual Biru Neon:**
  - Penyeragaman warna aksen seluruh tab aktif menggunakan palet biru neon (`#38bdf8`) dengan efek pendar halus.
- **Indikator Titik Peringatan Berkedip pada Tab:**
  - Penambahan penanda visual pada tab yang mendeteksi anomali (beban tinggi pada tab Kinerja, layanan down pada tab Layanan, insiden terbuka pada tab Riwayat & Masalah, firewall nonaktif pada tab Firewall, dan sertifikat kedaluwarsa pada tab SSL).

---

## Versi 3.20.1

### Perbaikan Sistem
- **Perbaikan Sintaks Templat services.html:**
  - Menutup blok kondisional `{% if %}` yang terpotong pada pengorganisasian kartu layanan untuk mengatasi galat *Internal Server Error (500)* pada halaman rincian server.

---

## Versi 3.20.0

### Fitur Baru
- **Manajer Tugas Interaktif (Task Manager ala btop):**
  - Perubahan nama tab *Proses Teratas* menjadi *Manajer Tugas*.
  - Tampilan awal 10 proses dengan opsi paginasi modern (10, 25, 50, 100, atau Semua proses).
  - Indikator status siklus hidup proses Linux (*Running*, *Sleeping*, *Stopped*, *Zombie*).
  - Kontrol sinyal proses langsung dari web: penangguhan proses sementara (*SIGSTOP* / Pause), pelanjutan proses (*SIGCONT* / Resume), dan penghentian proses (*SIGTERM* / *SIGKILL*).
- **Penyatuan Tab Riwayat Tindakan & Masalah:**
  - Memindahkan audit rekam jejak tindakan dari tab Layanan ke tab Masalah sehingga tab Layanan lebih bersih dan fokus.

---

## Versi 3.19.0

### Fitur Baru
- **Manajemen Penghentian Proses Interaktif (Kill Manager):**
  - Tombol tindakan penghentian pada tabel proses teratas pemakan CPU dan Memori.
  - Dialog pemilihan sinyal antara penghentian normal (*SIGTERM*) dan pemaksaan (*SIGKILL*).
  - Proteksi pengaman sistem untuk mencegah penghentian proses kritis (*PID 1*, *sshd*, dan *agent_pantau*).

---

## Versi 3.18.0

### Fitur Baru
- **Kontrol Visual Firewall:**
  - Penambahan tombol visual untuk mengaktifkan, menonaktifkan, dan memuat ulang aturan firewall UFW.
  - Fitur penguncian otomatis port krusial (SSH 22, Web 80/443, Dashboard 8400) sebelum aktivasi firewall guna mencegah terputusnya akses server.
  - Penambahan formulir pemblokiran alamat IP sumber secara manual dan tombol buka blokir langsung per baris tabel.

---

## Versi 3.17.0

### Fitur Baru & Pemantauan Mendalam
- **Pemantauan Utilisasi & Throughput Disk I/O:**
  - Pembacaan metrik laju baca/tulis (*KB/s*), frekuensi operasi (*IOPS*), dan persentase utilisasi disk (*% I/O util*) tanpa ketergantungan modul eksternal.
- **Audit Log Galat Sistem Kritis:**
  - Penyajian kejadian galat kritis sistem (*emerg*, *alert*, *crit*, *err*) dari systemd journald.
- **Audit Port Listening:**
  - Pemeriksaan socket aktif, proses pemilik, PID, dan klasifikasi akses (Publik vs Lokal).
- **Pelacakan Masa Berlaku Sertifikat SSL/TLS:**
  - Pemeriksaan berkas sertifikat lokal, domain SAN, penerbit (CA), dan peringatan dini sebelum masa aktif berakhir.
- **Pengawasan Tugas Terjadwal (Cron & Systemd Timers):**
  - Pemantauan berkala terhadap jadwal crontab sistem dan timer aktif.
- **Penyegaran Tampilan Antarmuka 2026:**
  - Pembaruan tema gelap modern dengan grafik riwayat kinerja berbasis gradien bercahaya.

---

## Versi 3.16.0

### Fitur Baru
- **Dukungan Socket Activation Layanan (SSH):**
  - Penanganan unit socket pendamping (`ssh.socket`) saat layanan dihentikan atau dijalankan ulang sehingga port socket benar-benar tertutup saat layanan nonaktif.
- **Pengabaian Peringatan Layanan Fleksibel:**
  - Fitur pembungkaman alarm untuk layanan tertentu secara permanen maupun berdasarkan batas waktu (2 jam, 24 jam, 7 hari, 30 hari).
- **Transparansi Status Layanan pada Dasbor:**
  - Penambahan rincian jumlah layanan berjalan, terhenti, dan dibisukan pada tabel dasbor utama.

---

## Versi 3.15.0

### Fitur Baru & Kesiapan Produksi
- **Snapshot 20 Proses Teratas:**
  - Pengumpulan data proses lokal pemakai CPU dan RAM tertinggi pada agen klien dan penyajian ringkas di antarmuka.
- **Mode Pemeliharaan (Maintenance Mode):**
  - Meredam kemunculan alarm tiket masalah saat server sedang dalam perbaikan terencana.
- **Normalisasi Unit Systemd & Cgroup:**
  - Pemetaan nama unit asli melalui pembacaan cgroup untuk akurasi pelacakan layanan.
- **Konfigurasi Produksi:**
  - Penyediaan templat reverse proxy Nginx dengan dukungan WebSocket SSL dan rotasi log Uvicorn.
  - Pembersihan otomatis tiket masalah lampau yang telah selesai.

---

## Versi 3.14.0

### Fitur Baru
- **Terminal Web Berbasis WebSocket & xterm.js:**
  - Migrasi antarmuka terminal ke pustaka standar xterm.js dengan latensi rendah.
  - Streaming data dua arah menggunakan WebSocket dispatcher.
  - Penyesuaian ukuran jendela terminal secara dinamis (*resize*).

---

## Versi 3.13.0

### Fitur Baru
- **File Manager Berbasis Web:**
  - Penjelajahan direktori, penyuntingan berkas teks, pengunggahan, dan pengunduhan berkas.
  - Batasan pengaman sistem (*guardrail*) pada direktori inti sistem dan pembuatan cadangan otomatis bertanda waktu saat berkas diedit.

---

## Versi 3.11.0 – 3.12.0

### Fitur Baru
- **Integrasi Terminal Shell PTY Asli:**
  - Penggunaan modul PTY Python standar untuk membuka shell `/bin/bash` dengan emulasi kontrol karakter VT100.

---

## Versi 3.7.0 – 3.10.0

### Fitur Baru & Pengerasan Keamanan
- **Pembaruan OS Jarak Jauh:**
  - Eksekusi pembaruan dan upgrade paket (*apt*) dari web dashboard.
  - Pengerasan hak akses sudo agen klien (*least privilege*) dan proteksi token CSRF.

---

## Versi 3.6.0

### Fitur Baru
- **Kendali Host (Reboot OS & Power Off):**
  - Penambahan perintah restart dan matikan mesin dengan eksekusi tertunda agar laporan konfirmasi berhasil terkirim sebelum sistem padam.

---

## Versi 1.0.0 – 3.5.0

### Fondasi Awal
- Pembangunan dasbor monitoring berbasis FastAPI dan basis data relasional.
- Pengembangan agen klien Python standar untuk pengumpulan metrik CPU, Memori, Swap, Disk, dan Jaringan.
