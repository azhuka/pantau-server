# Pantau Server

Dashboard pemantauan dan pengelolaan multi-server Linux berbasis web (FastAPI + MariaDB) dengan daemon agen Python ringan tanpa dependensi eksternal. Dirancang untuk memudahkan sysadmin dan tim operasional mengawasi metrik performa, mengelola layanan, dan menangani insiden secara terpusat.

---

## Fitur Utama

- **Pemantauan Performa & Alur Kerja Real-Time:** Monitoring utilisasi CPU, RAM, Swap, Disk per partisi, Load Average, bandwidth, status layanan sistem, dan sesi login SSH secara seketika (detak 5 detik, pelaporan instan pasca-tindakan zero-delay, deteksi kejadian eksternal langsung) via polling background tanpa reload halaman.
- **Telemetri Perangkat Keras & Virtualisasi:** Deteksi otomatis model prosesor, jumlah core, clock speed, platform hypervisor (KVM, Proxmox LXC/VM, VMware, Baremetal), tipe media penyimpanan (SSD/HDD), default gateway, DNS, interface jaringan, MAC address, serta waktu aktif sistem (*uptime*).
- **Kesehatan Media Penyimpanan (S.M.A.R.T. & NVMe):** Pemantauan kesehatan drive fisik secara komprehensif via `smartctl` dan `nvme-cli` (status PASSED/FAILED, suhu operasional, persentase keausan SSD/NVMe, *reallocated sectors*, jam terbang kerja), disertai deteksi drive virtual pada hypervisor/cloud agar tidak memicu alarm palsu.
- **Pengujian Endpoint & Jaringan Terjadwal (Probing Engine):** Pengujian konektivitas HTTP/HTTPS, TCP Port, DNS, dan ICMP Ping dengan riwayat latensi, pencatatan kegagalan, dan audit trail otomatis.
- **Klasifikasi Level Operasional Server (3-Tier) & Banner Peringatan Multi-Level:**
  - **Tier 1 (Layanan Utama):** Server dengan prioritas tinggi. Gangguan memulai tahap keparahan Gawat selama 1 menit untuk tindakan mitigasi awal, kemudian bereskalasi ke Kritis serta mengaktifkan banner merah (`banner-danger`) dan alarm audio jika belum pulih.
  - **Tier 2 (Layanan Pendukung):** Server operasional sekunder. Gangguan memulai tahap Peringatan selama 1 menit sebelum bereskalasi ke Gawat. Banner peringatan multi-level (`banner-average` oranye & `banner-warning` kuning) memastikan operator selalu mengetahui insiden pada seluruh armada server tanpa terkecuali.
  - **Tier 3 (Layanan Non-Kritis / Pengujian):** Server tahap uji coba atau sementara. Gangguan dibatasi pada tingkat Peringatan.
  - **Tindakan Pemeliharaan Operator:** Penghentian layanan (*Stop Service*), mulai ulang (*Restart Service*), atau pemadaman/mulai ulang server (*Power Off / Reboot*) yang diinisiasi oleh operator dicatat sebagai Peringatan tanpa memicu alarm darurat. Label keparahan `PERINGATAN` tetap dipertahankan pada kartu Insiden Terkini dengan keterangan nama operator dan jenis tindakan, serta menyertakan lencana status `DIABAIKAN` atau `✓ DITANGANI` secara berdampingan bila opsi tersebut dipilih oleh operator.
- **Pembaruan Agen Otomatis (Fleet-Wide OTA Self-Update):** Pembaruan agen klien secara otomatis saat server pusat diperbarui. Dilengkapi verifikasi integritas hash SHA-256 dan restart otomatis via systemd watchdog.
- **Manajemen Layanan Systemd & Proses:** Memulai (*start*), menghentikan (*stop*), memulai ulang (*restart*), memantau log service, serta menghentikan proses sistem (*kill* via SIGTERM/SIGKILL) langsung dari antarmuka web dengan pengaman sistem (*guardrail*).
- **Terminal Web Terintegrasi (xterm.js):** Sesi shell Linux interaktif langsung di browser dengan dukungan warna ANSI, tombol shortcut Bash, nano/vim, htop, dan mode layar penuh.
- **File Manager Web:** Eksplorasi direktori remote, penyuntingan berkas konfigurasi dengan cadangan otomatis (`.bak`), upload, download, serta pengaturan izin (*chmod/chown*) dengan proteksi path sistem kritis.
- **Kontrol Hak Akses 3-Tier (RBAC):**
  - **Master Admin:** Otoritas penuh sistem (pengaturan pengguna, audit log, konfigurasi global). Akun terlindungi dari penghapusan atau penonaktifan.
  - **Operator:** Hak operasional harian yang dapat didelegasikan secara granular (layanan, terminal, file manager, firewall) dengan wewenang setara sudo.
  - **Viewer:** Hak observasi baca-saja (*read-only*) tanpa tombol aksi eksekusi.
- **Autentikasi Dua Langkah (2FA TOTP):** Dukungan Google Authenticator, Microsoft Authenticator, dan kode pemulihan cadangan (*recovery codes*).
- **Audit Trail Terpusat:** Pencatatan log seluruh aktivitas pengguna (siapa, kapan, perintah/tindakan, target, dan hasil eksekusi).
- **Sinkronisasi Antarmuka & Pembaruan Reaktif Tanpa Reload (Universal Zero-Reload NOC UI):** Pengawas telemetri otomatis di browser dan modul reaktif yang memperbarui insiden, kartu insiden terkini, tabel armada, kartu grid, siklus hidup pendaftaran/penghapusan server (*dynamic fleet add/remove*), status layanan, port listening, status firewall, tugas cron, sertifikat SSL, akun login SSH remote, serta metrik server secara seketika tanpa jeda dan tanpa mengharuskan operator me-reload halaman manapun. Dilengkapi mekanisme sliding session window 24/7 agar layar monitor NOC tidak pernah terputus atau kedaluwarsa secara sepihak. Seluruh aksi dan konfirmasi operator dieksekusi secara asinkron (AJAX).
- **Standarisasi Kontrol Interaksi Universal & Efisiensi Resource Browser:** Seluruh modal dialog pada antarmuka Pantau Server mendukung 3 metode penutupan standar (tombol Close 'X' yang konsisten, penekanan tombol Escape keyboard global, dan klik di luar area modal/backdrop). Polling asinkron (seperti streaming live log dan telemetri) dilengkapi proteksi kebocoran memori dengan suspensi otomatis saat tab tidak aktif (*visibilitychange* & tab switching).
- **Alur Kerja Pengabaian Cerdas Insiden Terkendali (Universal Incident Silencing & Triage):** Filosofi penanganan insiden operasional terpadu untuk segala tingkat keparahan (*danger, average, warning, info*). Ketika suatu insiden telah dikenali atau disengaja oleh operator (misalnya layanan *on-demand* yang hanya aktif saat digunakan user klien secara manual, sesi remote SSH resmi, atau jadwal pembaruan APT), operator dapat mengabaikannya (*Abaikan / Silence*). Sistem secara otomatis menyembunyikan insiden tersebut dari daftar tabel *Insiden Terkini* pada layar utama monitor NOC agar tidak mengaburkan fokus pengawasan, sementara indikator "Diabaikan" pada kartu *Insiden Aktif* tetap mencatatnya secara terstruktur sehingga operator dapat meninjau atau memulihkannya kapan saja melalui modal rincian *Diabaikan (Silenced / Ignored)*.
- **Standarisasi Terminologi & Ergonomi Antarmuka Baku:** Label status kolom masalah berstatus aman dikunci pada badge **Nihil**, tab navigasi rincian server menggunakan arsitektur 12 tab standar teknis baku (*Performa, Insiden, Services, Packages, Tasks, Users, Ports, Firewall, SSL/TLS, Cron Jobs, Cadangan, Logs*), kartu manajemen unit layanan OS Systemd (*Unit Layanan Systemd*), tab manajemen paket OS (*Packages*), dan seluruh kolom interaksi kontrol diekspresikan secara seragam dengan judul **Tindakan**.
- **Ergonomi & Kepadatan Data Tinggi NOC (High Density Pure SVG Icon Actions):** Seluruh tombol aksi operasional pada tabel armada server, manajemen pengguna, toolbar hero server, tabel layanan, proses/tasks, port, firewall, sertifikat SSL, tugas cron, modal diagnosa, dan aksi header server menggunakan tombol berikon SVG murni tanpa teks label mengambang, dilengkapi tooltip informatif (`title` dan `aria-label`) standar Bahasa Indonesia baku untuk navigasi yang bersih, cepat, dan presisi tanpa anomali visual.
- **Kepadatan Data Dasbor Adaptif & Ikon Salin Vektor:** Pengalih tata letak dasbor (Tabel Operasional & Kartu NOC) dan pengalih kepadatan baris (Mode Kompak 1-Baris & Mode Standar 2-Baris Rinci), serta ikon salin vektor SVG terpadu pada seluruh elemen alamat IP yang dapat disalin.
- **Hierarki Kolom Keparahan Dua Baris & Standardisasi Seluruh Tabel Insiden:** Format baku dua baris terstruktur untuk kolom keparahan di seluruh tabel insiden (dasbor utama, halaman insiden terpusat, dan kartu Status Masalah rincian server: baris utama badge keparahan 9.5px tebal; baris sekunder keterangan operator/penanganan 8px ringkas), eliminasi ikon tidak diminta pada label pengabaian, proporsionalitas lebar kolom tabel NOC, keterbacaan panduan solusi optimal hingga 3 baris teks (260px), perataan terstruktur kolom tindakan, serta integritas visual bebas glif rusak.
- **Reduksi Proporsional Tipografi Tabel Non-Dasbor & Keseragaman Mutlak Mode Dasbor (v4.7.8):** Reduksi terukur 2 tingkat pada seluruh teks tabel sekunder (daftar server, insiden terpusat, rincian server, pengguna, aktivitas, log, dan inspeksi probe) dari 12px/12.5px ke 9.5px–10.5px untuk kepadatan informasi NOC maksimal tanpa membuang ruang vertikal/horizontal. Keseragaman mutlak 100% ukuran font antara Mode Standar dan Mode Kompak pada tabel utama dasbor tanpa lonjakan font saat berganti mode.
- **Penyatuan Terpadu Manajemen Pengguna & Keamanan Kredensial (v4.7.9):** Penyatuan tab navigasi profil pengguna menjadi satu halaman terpadu berprinsip kepadatan data NOC. Mengeliminasi tab terpisah "Akun Saya" dengan mengintegrasikan kartu Informasi Identitas, Status Sesi, dan Autentikasi 2FA TOTP langsung ke bagian atas tab Manajemen Pengguna. Membedakan alur pengubahan kata sandi secara tegas: tombol Edit pada akun sendiri membuka modal Ubah Kata Sandi Saya (wajib verifikasi kata sandi saat ini/lama), sedangkan tombol Edit pada akun staf membuka modal Edit Hak Akses & Reset Kata Sandi (admin override tanpa kata sandi lama staf, dilengkapi konfirmasi kata sandi baru). Penegakan aturan akun tunggal Master Admin.
- **Integrasi Edit Akun Mandiri & Penyederhanaan Kontrol Simpan (v4.8.0):** Eliminasi tombol redundan pada kartu identitas ("Ubah Kata Sandi Saya"). Tombol Edit pada baris tabel pengguna kini menjadi titik kontrol tunggal terpadu untuk memperbarui kredensial (username dan kata sandi) dengan verifikasi kata sandi saat ini yang aman. Penyederhanaan label tombol konfirmasi pada seluruh modal manajemen pengguna menjadi lebih lugas dan profesional ("Simpan").
- **Tata Letak Vertikal Kolom Platform / IP Mode Standar Dasbor (v4.8.1):** Penataan ulang kolom "IP & Platform" pada tabel armada Status & Kinerja dasbor menjadi "Platform / IP" khusus mode standar dengan struktur vertikal proporsional (baris 1: tipe platform, baris 2: alamat IP host). Mempertahankan format baris ultra-ramping horizontal pada mode kompak tanpa perubahan apapun demi kesempurnaan ergonomi NOC.
- **Reduksi Ukuran Teks IP & Standarisasi Badge Indikator Warna Berukuran Kecil (v4.8.2):** Reduksi teks alamat IP pada seluruh tabel armada menjadi 9.5px monospace yang rapi dan elegan. Standarisasi seluruh badge indikator warna (ONLINE hijau, OFFLINE merah, PEMELIHARAAN kuning, NIHIL hijau, tier, platform, serta counter pill angka insiden 1, 2, ...) pada seluruh tabel menjadi ukuran kecil (8px) yang proporsional, hemat ruang, dan konsisten antara rendering template Jinja dan live polling JavaScript tanpa lonjakan visual.
- **Deteksi Cerdas Kegagalan Repositori APT & Eliminasi Alarm Sukses Palsu (v4.8.3):** Eliminasi anomali pelaporan sukses palsu (`✔ Selesai dengan sukses`) ketika `apt update` gagal mengunduh repositori karena kesalahan DNS (*Temporary failure resolving*) atau jaringan (*Connection refused*). Penguatan wrapper eksekusi (`script -qfec`) untuk meneruskan kode keluar asli, deteksi cerdas pola kegagalan unduh (*Failed to fetch / Some index files failed to download*) pada agen dan dasbor antarmuka, serta penyajian status peringatan kuning (`⚠ Selesai dengan peringatan`) yang akurat tanpa menipu operator.
- **Perbaikan Fungsi Kunci Terminal & Pemutusan Sesi Web Shell (v4.8.4):** Eliminasi galat runtime `ReferenceError` pada fungsi konfirmasi kunci terminal. Menjamin alur penguncian terminal, pencabutan masa sewa otentikasi (*ephemeral lease revocation*), pemutusan koneksi WebSocket seketika, penghentian proses shell PTY pada agen, penutupan jendela terminal, serta umpan balik notifikasi *toast* berjalan mulus tanpa macet atau membekukan antarmuka.
- **Arsitektur Keterhubungan Relasional Menyeluruh & Sinkronisasi Reaktif Dua Arah (v4.8.5):** Implementasi paradigma integritas relasional enterprise (*Omnidirectional Relational Integrity*). Deteksi reaktif perubahan paket di server klien via pemantauan timestamp file (*mtime* `/var/lib/dpkg/status` & `/var/lib/apt/lists`) tanpa jeda polling lambat; sinkronisasi dua arah seketika antara aksi langsung di server klien (SSH/konsol) dan aksi via dashboard; integrasi data-binding reaktif pada Tab Packages (badge tab, badge header, baris tabel, dan hero button); eliminasi jebakan logika `aptArmed`; penyegaran otomatis inventaris paket terpasang (`PKG_LIST`); update dinamis kolom OS Update pada tabel armada `/servers`; serta auto-discovery penambahan socket layanan aktif ke pengawasan utama.
- **Penuntasan Eksepsi Rollback Log Request APT & Penegakan Keterhubungan Relasional Menyeluruh (v4.8.6):** Eliminasi bug kritis `UnboundLocalError` yang memicu rollback pembatalan status penyelesaian tugas APT menjadi kedaluwarsa palsu (`[proses apt kedaluwarsa]`), pengamanan komit transaksi independen `LogRequest`, pembersihan menyeluruh sesi APT menggantung dengan prioritas pemantauan tugas aktif terbaru (`id desc`), standardisasi muatan JSON terstruktur pada agen klien, penyempurnaan ekstraksi pesan kesalahan modal antarmuka dari teks mentah terminal, serta sinkronisasi reaktif insiden `apt_updates` langsung dari laporan telemetri agen.
- **Benteng Proteksi Konflik Platform & Rekonsiliasi Otomatis Kesalahan Input Operator (v4.8.7 - v4.8.8):** Proteksi fail-safe alokasi storage kontainer LXC agar disk host fisik tidak bocor ke kontainer sekalipun disetel manual sebagai Baremetal; deteksi cerdas konflik platform (*Platform Mismatch Conflict Triage*) berstatus Peringatan dengan notifikasi "Konfigurasi Platform Server Tidak Sesuai" pada dasbor utama; aksi mitigasi 1-klik untuk menyinkronkan kembali konfigurasi ke Auto Deteksi; pembatasan ketat panjang catatan resolusi insiden database (*resolved_note sanitization*); panduan teks dinamis aktual pada formulir server (*Server ini terdeteksi sebagai platform VM (KVM)*); serta peringatan interaktif real-time pencegah salah konfigurasi platform.
- **Ekspansi Kapasitas Kolom Catatan Resolusi Insiden & Penuntasan Rollback Telemetri Klien (v4.8.9):** Ekspansi skema kolom basis data `server_problems.resolved_note` dari `VARCHAR(30)` ke `VARCHAR(100)` dan sanitasi menyeluruh pada seluruh titik resolusi otomatis/manual. Mengeliminasi galat fatal HTTP 500 (`Data too long for column 'resolved_note'`) saat agen klien menyelesaikan pembaruan paket sistem (`apt`), yang sebelumnya menyebabkan transaksi laporan telemetri bergulir balik (*rollback*), membekukan pembaruan metrik, dan menahan tampilan versi agen klien di dasbor. Pengelompokan kurung siku pada perintah salin pembaruan agen manual untuk integritas eksekusi shell POSIX.
- **Perbaikan Impor Modul SSL & Konfigurasi Handshake TLS Agen Klien (v4.8.10):** Menambahkan impor eksplisit pustaka standar `import ssl` pada agen klien guna mengeliminasi galat fatal `NameError: name 'ssl' is not defined` saat health-check mendeteksi layanan HTTPS/TLS; menyematkan konteks SSL permisif (`ssl._create_unverified_context()`) pada `_HTTP_OPENER` agar probe kesehatan HTTP/HTTPS lokal pada port 443/8443 berjalan mulus tanpa terblokir ketidaksesuaian nama host atau sertifikat internal.
- **Deteksi Cerdas Multi-Lapis Kontainer LXC & Eliminasi Status Baremetal Semu (v4.8.11):** Implementasi inspeksi multi-lapis tanpa dependensi root untuk identifikasi virtualisasi kontainer pada agen klien (mencakup inspeksi Proxmox LXCFS pada `/proc/mounts`, hierarki cgroup `/proc/1/cgroup` dan `/proc/self/cgroup`, profil AppArmor `/proc/self/attr/current`, dan fallback `sudo -n systemd-detect-virt`); eliminasi label *Baremetal* prematur pada server yang baru didaftarkan sebelum agen melapor dengan menyajikan status dan badge *Auto (Menunggu Laporan Agen)*; serta koreksi otomatis platform di server pusat berdasarkan metadata alokasi storage virtual *rootfs*.
- **Akurasi Riwayat Login Modern & Pemutusan Sesi SSH Terpusat (v4.8.12):** Mengatasi anomali *Login Sukses: 0* pada sistem Linux modern tanpa rsyslog (Ubuntu 24.04 LTS / Debian 12) dengan integrasi multi-sumber telemetri login (penggabungan akuntansi `wtmp/last -F`, sesi aktif real-time `utmp/who`, dan fallback `systemd-journald` terisolasi). Menyediakan fitur pengelolaan sesi terminal aktif terpusat: aksi pemutusan paksa sesi terminal SSH (*force terminate session*) 1-klik langsung dari Tab Users (`#tab-akun`), kartu Sesi Aktif halaman Aktivitas Pengguna (`user_activity.html`), maupun panel tindakan cepat Insiden Sesi Remote (`#tab-masalah`), didukung penguatan wrapper keamanan `/usr/local/sbin/pantau-user terminate-session` dengan validasi ketat nama TTY.
- **Perbaikan Evaluasi Izin Pengayaan Insiden Sesi Remote (v4.8.13):** Eliminasi galat runtime HTTP 500 (`name 'can_services' is not defined`) pada fungsi `_enrich_problems_for_ui`. Memperbaiki pemetaan izin penanganan sesi terminal aktif (`can_term`) secara aman berbasis objek atau string peran `user_or_role` (`can_users_sys`, `can_manage_servers`, atau `can_services`), menjamin dasbor dan tab insiden terbuka tanpa hambatan.
- **Relokasi Tombol Putus Sesi ke Kolom Tindakan Sesuai Standar UI/UX (v4.8.14):** Penegakan prinsip tata letak tabel terbaik (*table UX best practice*). Memindahkan seluruh tombol putus paksa sesi terminal SSH dari kolom data "Sesi Aktif" ke kolom khusus "Tindakan" pada tabel Akun Pengguna (`services.html`), baik saat render server Jinja maupun live polling JavaScript. Mensterilkan kartu ringkasan "Sesi Aktif" pada halaman Aktivitas Pengguna (`user_activity.html`) dari tombol selipan, dan memusatkan tombol kontrol pemutusan sesi ke bilah tindakan atas (*topbar*).
- **Standarisasi Ikon Pemutusan Sesi Terminal (Log-Out / Kick) (v4.8.15):** Mengganti ikon tombol pemutusan sesi dari ikon tombol power (*standby/power off*) yang membingungkan menjadi ikon standar *log-out* (pintu keluar dengan panah keluar) di seluruh antarmuka (Tabel Akun Pengguna, Bilah Tindakan Aktivitas Pengguna, dan Tombol Insiden Masalah Sesi Remote), mengeliminasi persepsi keliru pemadaman mesin host.
- **Perombakan Semantik Menyeluruh Ikon & Tombol Aksi Antarmuka (v4.8.16):** Mengeliminasi penggunaan ikon generik tambah ([ + ]) yang ambigu dan membingungkan di seluruh aplikasi (seperti pada tombol Blokir IP, Tambah Server, Tambah Layanan, Tambah Cron, Tambah SSL, dan Tambah Probing Endpoint). Mengganti ikon tombol Blokir IP menjadi `shield-x` dan Buka Blokir menjadi `unlock` (sebelumnya ikon tempat sampah `trash-2`), Tambah Server menjadi `server`, Tambah Layanan menjadi `layers`, Tambah Cron menjadi `clock`, Tambah Pengguna menjadi `user-plus`, Tambah SSL menjadi `folder-plus`, Promosi Port menjadi `activity`, serta menyematkan ikon semantik yang hidup pada File Manager (`folder-plus`, `file-plus`, `upload`, `clipboard`, `maximize`, navigasi panah SVG), formulir pendaftaran pengguna/server, modal konfirmasi, dan halaman login/2FA guna menghadirkan antarmuka NOC yang ergonomis, intuitif, dan menyenangkan.
- **Pemulihan Mandiri Otomatis Wrapper pantau-user & Titik Unduh Wrapper Pusat (v4.8.17):** Mengatasi kegagalan pemutusan sesi SSH (`gagal: ERROR: Aksi tidak dikenal: 'terminate-session'`) akibat wrapper usang pada server klien yang dipasang sebelum rilis v4.8.12. Mengimplementasikan mekanisme *Self-Healing Wrapper* pada agen klien (`agent_pantau.py`) yang secara otomatis mendeteksi dan memperbarui wrapper `/usr/local/sbin/pantau-user` saat startup agen, setelah pembaruan OTA, maupun saat pra-eksekusi aksi pengguna via root/pantau-file berizin `0750`. Menyediakan endpoint API pusat `/api/agent/wrapper/{wrapper_name}` untuk distribusi berkas wrapper resmi langsung dari server dashboard.
- **Standarisasi Ikon Upgrade Paket OS & Eliminasi Ikon Caret Ambigu (v4.8.18):** Mengeliminasi penggunaan ikon caret/chevron tunggal (`[ ^ ]`) pada tombol Upgrade Paket OS (`apt-upgrade-btn`) dan modal tindakan paket yang membingungkan dan tidak representatif. Menggantinya dengan ikon semantik `arrow-up-circle` (lingkaran dengan panah vertikal naik) yang seragam dengan tombol Upgrade All di Tab Packages dan baris tabel paket individual, memperjelas tooltip menjadi "Tingkatkan paket OS yang tersedia", serta menyematkan ikon 3D `package` pada header kartu Tab Packages guna mewujudkan hierarki visual yang kohesif dan ergonomis.
- **Penyempurnaan Menyeluruh Stabilitas Prober, Keamanan Zero-Dependency Agen, & Kepadatan Dasbor (v4.8.19):** Eliminasi pembekuan SLA uptime akibat benturan tipe data Decimal-Float, perbaikan evaluasi falsy uptime 0.0% pada prober sintetis, dukungan inspeksi sertifikat SSL remote internal/self-signed via binary DER dan PEM decoding, eliminasi kebocoran subproses zombi ICMP ping, penegakan prinsip zero-dependency agen klien tanpa modul eksternal cryptography (beralih ke standard library ssl dan CLI openssl bawaan sistem), penambahan dependensi server httpx dan qrcode, sinkronisasi penerusan kode keluar asli `-qfec` pada wrapper apt, pembersihan dan standarisasi konstanta agen `PANTAU_`, sinkronisasi otomatis 16 izin granular RBAC seeder, sinkronisasi lengkap skema basis data 16 tabel dan pelacakan git agen klien, serta penyematan lencana Proxmox HA pada dasbor dan optimasi regex linier $O(N)$ pembersihan stream ANSI terminal.
- **Penyempurnaan Penutupan Subproses Prober, Skema Basis Data, & Pemetaan CN Sertifikat SSL (v4.8.20):** Penutupan eksplisit transport subproses ping ICMP guna mengeliminasi peringatan sumber daya tak tertutup (*unclosed transport ResourceWarning*) dan galat penutupan loop kejadian (*RuntimeError: Event loop is closed*), pengayaan pemetaan kolom `backup_status` pada model ORM `ServerExtra` agar sinkron penuh dengan skema MariaDB, peningkatan ketahanan parsing stempel tanggal SSL berbagai varian format/zona waktu, ekstraksi CommonName (CN) sertifikat SSL untuk mengeliminasi string DN panjang pada antarmuka tabel NOC, serta standarisasi hirarki warna SLA uptime tabel probing (hijau `>=99%`, kuning `>=95%`, merah `<95%`).
- **Benteng Anti-Bricking Agen & Pemulihan Darurat Otomatis OTA (v4.8.21):** Implementasi mekanisme proteksi permanen anti-bricking pada sistem pembaruan Over-The-Air (OTA) agen pemantau. Mengganti validasi sintaks pasif dengan pengujian pra-eksekusi runtime penuh (*isolated runtime pre-flight execution check*) via subproses mandiri berbatas waktu 15 detik sebelum berkas target disentuh, pembuatan cadangan atomik otomatis (`.bak`) sebelum penimpaan berkas, verifikasi integritas pasca-penulisan (*post-write sanity check*) dengan rollback instan otomatis, serta integrasi direktif `ExecStartPre` berhak akses penuh pada unit layanan systemd `agent_pantau.service` guna mendeteksi dan memulihkan berkas utama dari cadangan `.bak` secara otomatis saat daemon mengalami kegagalan.
- **Penyelarasan Filosofi Dasbor NOC & Eliminasi Lencana Sekunder HA (v4.8.22):** Penegakan prinsip kemurnian dasbor pemantauan utama (*clean situational awareness*). Mengeliminasi lencana sekunder Proxmox HA pada tabel armada server dan tampilan kisi dasbor utama (`dashboard.html`), mengembalikan fokus tunggal halaman depan pada identitas esensial host, metrik kesehatan real-time, dan insiden aktif tanpa polusi ornamen arsitektural statis. Informasi ketahanan Proxmox HA tetap dipertahankan secara utuh dan proporsional pada inventaris server lengkap (`servers.html`) dan rincian telemetri mendalam (`services.html`).
- **Sistem Notifikasi Tugas Latar Belakang Lintas Halaman & Desktop OS (v4.8.23):** Implementasi jendela notifikasi mengambang ringkas (*NOC Floating Task Notification*) dengan durasi otomatis 5 detik, bilah hitung mundur interaktif (*5s animated countdown progress bar*), dan jeda otomatis saat diarahkan kursor (*pause-on-hover*). Mengintegrasikan arsitektur notifikasi dua lapis (*Dual-Layer Notification*): Lapisan Web In-App berprioritas tinggi (`z-index: 100001`) yang mengambang di atas seluruh antarmuka web, serta Lapisan Desktop OS via standar Web Notifications API (`window.Notification`) yang memunculkan jendela notifikasi sistem operasi di atas semua aplikasi yang sedang aktif di layar monitor operator (terminal, IDE, browser lain) ketika proses latar belakang (Update repositori APT, Upgrade paket OS, Pembaruan agen OTA, Pembersihan cache deb, dan Pemutusan sesi terminal SSH) selesai dijalankan. Dilengkapi sistem pelacakan tugas lintas halaman otomatis (*cross-page task tracker*) via `localStorage` yang memastikan notifikasi tetap terpicu meskipun operator berpindah halaman.
- **Proteksi Penguncian & Pembersihan Terminal Saat Proses Aktif (v4.8.24):** Implementasi mekanisme pengamanan status proses konsol terminal bawaan Linux secara realtime. Tombol Kunci Terminal (`#term-lock-btn`), Tombol Bersihkan Layar (`#term-clear-btn`), serta indikator kontrol kuning (`#term-dot-clear`) secara otomatis dinonaktifkan (*disabled*, kursor `not-allowed`, transparansi redup, dan tooltip informatif) saat ada proses atau tugas yang sedang dieksekusi di konsol (baik proses interaktif foreground, skrip shell, maupun tugas pembaruan repositori APT). Didukung oleh deteksi status ganda kernel POSIX (`os.tcgetpgrp` pada PTY dan pembacaan `tpgid` proses shell di `/proc/[pid]/stat`), sinkronisasi sinyal status seketika melalui WebSocket terminal bridge, penolakan tindakan berisiko secara preventif di sisi klien, serta standarisasi format durasi waktu notifikasi latar belakang menjadi format baku Indonesia (`⏱️ X dtk`).
- **Benteng Otentikasi Tindakan Operator Berat & Standarisasi UI/UX Enterprise (v4.8.25):** Implementasi benteng pengamanan ganda (*Step-Up Authentication & Guardrail System*) untuk tindakan operator berisiko tinggi dan katastropik. Seluruh tindakan destruktif permanen (Reboot Host, Power Off Host, Hapus Server dari monitoring, Regenerasi Kunci API Agen, Hapus Pengguna Linux Klien, Hapus Akun Staf Dashboard, dan Nonaktifkan 2FA Staf) kini diwajibkan melewati verifikasi kata sandi operator login (`pwd_ctx.verify`) dan kode 2FA TOTP di tingkat backend API sebelum perintah dieksekusi. Dilengkapi penyempurnaan dialog modal guardrail kelas enterprise (`#guardrail-modal`) dengan desain padat data tanpa teks bertele-tele, validasi pengetikan nama host untuk penghapusan server, penanganan submit keyboard `Enter`, serta pemisahan tegas antara tindakan wajib kata sandi (Level 1) dan tindakan tanggap darurat yang cukup menggunakan modal penegasan bahaya tanpa kata sandi (Level 2: Stop Service, Kill Process, Blokir IP, Terminate Session) guna menjaga kelincahan mitigasi insiden NOC.
- **Modal Konfirmasi Universal Enterprise & Eliminasi Dialog Bawaan Browser (v4.8.26):** Mengeliminasi 100% dialog konfirmasi popup bawaan browser (`window.confirm()` dan `window.alert()`) yang kaku, kuno, dan memblokir thread UI di seluruh halaman web aplikasi. Menggantikannya dengan komponen dialog modal konfirmasi universal kelas enterprise (`#app-confirm-modal`) berbasis HTML5/CSS modern dengan efek *smooth backdrop-blur*, palet warna gelap NOC (`#161b22`, border `#30363d`), animasi kemunculan halus (*cubic-bezier*), ikon SVG semantik tematik (Bahaya, Peringatan, Tindakan/Info), lencana sasaran monospaced (`Target: PID / IP / Endpoint / Pengguna`), pesan dampak satu baris yang padat dan lugas tanpa teks mubazir, navigasi papan ketik penuh (`Enter` untuk konfirmasi, `Esc` untuk pembatalan), serta pencegat pengiriman formulir otomatis (`data-confirm`) yang terintegrasi secara mulus di seluruh modul operasional (Hentikan Proses, Putus Sesi Terminal, Blokir/Buka IP Firewall, Uji Jalankan Cron, Hapus Cron, Hapus Pengawasan SSL, Kunci/Buka Pengguna, Reset Ambang Batas, Acknowledge Insiden, dan Pemulihan Berkas).
- **Transformasi Halaman Daftar Server Menjadi Direktori Inventaris Mesin Klien Lengkap (v4.8.27):** Memisahkan fungsi secara tegas antara Halaman Utama (Pusat Telemetri & Beban Real-Time) dengan Halaman Daftar Server sebagai Direktori Identitas & Inventaris Armada Klien Lengkap (*Fleet Machine Identity Directory*). Mengintegrasikan 12 kolom identitas komprehensif dalam satu tabel berkepadatan tinggi khas NOC tanpa teks mubazir: Server (Hostname, tautan rincian, dot status, lencana tier, catatan host), IP & Antarmuka Jaringan (IP tersalin, antarmuka primer seperti `ens18`/`eth0`/`eno1`, lencana Lokal), Platform & Mesin (LXC/VM/Baremetal, vendor & model perangkat keras Dell/HPE/QEMU, proteksi Proxmox HA), Distribusi OS & Kernel (Distro OS, versi kernel, dan arsitektur CPU), Prosesor (Model CPU bersih tanpa noise dan jumlah inti), Memori (Total RAM fisik dan kapasitas Swap), Penyimpanan Fisik (Daftar partisi dan kapasitas disk), Uptime & Waktu Boot, Versi Agen Pantau & Status Paket APT, Tag Kategori, Status Koneksi & Waktu Lapor Terakhir, serta Kolom Tindakan Cepat berperekat (*sticky action column*). Dilengkapi pencarian multivariabel cerdas (mendukung pencarian berdasarkan vendor, CPU, kernel, OS, interface, hingga catatan) serta pengurutan presisi tinggi berbasis nilai numerik (Uptime detik, kapasitas RAM bytes, dan stempel waktu ISO).
- **Sistem Kustomisasi Tampilan & Antarmuka Universal (v4.8.28):** Implementasi mesin personalisasi tampilan web bertaraf enterprise NOC (*Enterprise Theme, Accent, Typography & UI Customization Engine*). Menyediakan 4 mode tema utama: Midnight NOC (bawaan sistem gelap seimbang), Obsidian OLED (hitam pekat murni #000000 0% backlight glow), Deep Space (biru malam pekat khas Proxmox), dan Mode Terang (cerah, bersih, dan kontras tinggi untuk lingkungan kerja siang hari). Dilengkapi 5 palet warna aksen antarmuka (Sian, Indigo, Zamrud, Violet, Sunset Amber), pemilihan gaya tipografi font antarmuka (Sistem Bawaan, Inter, Geist Sans, Ubuntu/Fira) serta font monospace metrik (Sistem Monospace, JetBrains Mono, Fira Code), dan pengatur kerapatan tata letak (*UI Density*: Kompak NOC berdensitas data tinggi vs Normal Nyaman). Seluruh preferensi disimpan persisten per-peramban (`localStorage`) dengan arsitektur *Zero-FOUC* (bebas kedipan) dan pratinjau langsung secara seketika (*live instant preview*).
- **Standardisasi Kolom Tindakan Berperekat, Kerapatan Tabel, & Kontrol Paginasi Cerdas (v4.8.29):** Penyelarasan tata letak tabel bertaraf NOC enterprise di seluruh modul aplikasi. Mengimplementasikan kolom tindakan berperekat universal (*sticky right action column*) dengan efek bayangan elevasi (*box-shadow: -4px 0 8px*) yang adaptif pada 4 varian tema (Midnight, Obsidian, Deep Space Navy, dan Mode Terang), memastikan tombol operasional selalu dapat diakses seketika saat menggulir tabel lebar secara horizontal. Melakukan kalibrasi kerapatan sel dan batas lebar kolom (*padding & min-width*) pada Halaman Daftar Server (`servers.html`) demi proporsi tabel yang presisi dan bersih. Memperbaiki pemisahan ruang napas kolom Waktu Mulai dan Identitas Server pada Kartu Insiden Terbuka (`problems.html`) serta menstandarisasi kolom tindakan ke posisi paling kanan. Menetapkan batas default paginasi 10 baris pada seluruh tabel modul operasional dengan pengecualian tabel Konfigurasi Gateway & Resolver DNS (default 5 baris), disertai logika penyembunyian bilah paginasi cerdas (*auto-hide pagination footer*) otomatis saat data baris kurang dari 10 (atau kurang dari 5 pada DNS) untuk mengeliminasi kontrol antarmuka yang mubazir.
- **Sinkronisasi Kolom Insiden & Preservasi Kolom Berperekat Dinamis (v4.8.30):** Perbaikan anomali pertukaran posisi kolom Panduan Solusi dan Tindakan pada tabel Insiden Terbuka (`problems.html`) akibat ketidaksesuaian urutan sel antara rendering SSR Jinja dan pembaruan berkala JavaScript (`pollProblems()`). Menyelaraskan urutan kolom secara identik dengan menempatkan Panduan Solusi pada kolom ke-6 dan Tindakan pada kolom ke-7 (paling kanan berperekat). Mengintegrasikan kelas `col-act` secara permanen ke dalam seluruh mesin rendering dinamis JavaScript pada modul Rincian Server (`services.html`), mencakup tab Users/Akun (`#acc-table`), tab Ports (`#ports-table`), tab Cron Jobs (`#cron-table`), tab SSL/TLS (`#ssl-table`), dan tab Firewall (`#fw-blocked-table`). Memberikan penetapan batas lebar minimum tabel (`min-width: 750px–760px`) guna menjamin efek elevasi bayangan horizontal (*box-shadow elevation*) dan sifat berperekat (*sticky right*) tetap aktif secara konsisten setelah siklus polling latar belakang.
- **Perbaikan Transmisi Parameter Upgrade Paket Mandiri & Pelabelan Modal APT (v4.8.31):** Perbaikan kegagalan eksekusi tugas upgrade paket tunggal (`PKG_UPGRADE`) akibat hilangnya penerusan nama paket target (`detail`) pada payload permintaan frontend (`triggerAptTask`) ke endpoint `/api/logs/request`. Memperluas fungsi `triggerAptTask`, `aptFollow`, serta `openAptTaskModal` agar menyertakan parameter `detail`, sehingga daemon agen menerima identitas paket secara valid dan mengeksekusi `apt-get --only-upgrade install <pkg>` tanpa galat validasi nama paket. Menyelaraskan fungsi pelabelan modal dan notifikasi latar belakang (`aptLabel` dan `updateAptTaskTitles`) agar secara akurat menampilkan judul `Upgrade Paket: <nama_paket>` dan `──── apt install --only-upgrade <nama_paket> ────` (menggantikan label keliru bawaan `──── apt update ────`).
- **Pemulihan Integritas Skrip Halaman Rincian Server & Kebijakan Keamanan Font (v4.8.32):** Mengeliminasi galat sintaksis JavaScript (`SyntaxError: await is only valid in async functions`) pada modul Rincian Server (`services.html`) yang disebabkan oleh karakter penutup kurung kurawal berlebih pasca-registrasi notifikasi tugas pelacakan latar belakang, memulihkan seluruh fungsi interaktif antarmuka (siklus pembaruan metrik berkala, navigasi tab operasional, pembukaan dialog modal, dan eksekusi tugas terminal). Menyelaraskan direktif *Content-Security-Policy* (CSP) pada middleware keamanan backend (`server/main.py`) dengan mengizinkan domain Google Fonts (`https://fonts.googleapis.com` pada `style-src` dan `https://fonts.gstatic.com` pada `font-src`) guna menjamin pemuatan tipografi antarmuka kustom tanpa pelanggaran kebijakan keamanan peramban.
- **Transformasi Menyeluruh Modul Users & Groups ala ServerBox Enterprise (v4.8.33):** Perombakan mendalam tab Users pada modul Rincian Server terinspirasi dari arsitektur ServerBox mobile/desktop. Mengintegrasikan sub-navigasi terpadu (*Segmented Bar*) untuk beralih secara instan antara subview **Pengguna (*Users*)** dan **Grup Sistem (*Groups*)**. Di subview Pengguna, inventaris akun kini mencakup akun pengguna reguler dan seluruh akun sistem/layanan Linux (`/etc/passwd`), dilengkapi identitas numerik UID/GID, nama grup primer dan pil grup sekunder (supplementary), path direktori home, klasifikasi shell interaktif vs nologin, riwayat login terakhir (`lastlog`), lencana hak akses istimewa (Sudoer, Sistem, Reguler, Terkunci), serta bilah filter kategori cepat dan pencarian multivariabel. Di subview Grup, menyajikan inventaris lengkap grup sistem operasi (`/etc/group`), penanda grup istimewa (*privileged* seperti sudo, wheel, docker, adm, root), klasifikasi grup sistem vs pengguna, serta pemetaan menyeluruh seluruh anggota pengguna (*members*) per-grup. Didukung telemetri otomatis agen klien menggunakan pustaka standar Python `pwd` dan `grp` (*zero external dependency*) serta migrasi skema basis data MariaDB.
- **Perbaikan Sinkronisasi Filter Kategori & Pencarian Pengguna dan Grup dengan Paginasi (v4.8.34):** Menyelesaikan kendala malfungsi tombol filter kategori (Semua, Reguler, Sistem, Sesi Aktif pada Pengguna, serta Semua, Reguler, Sistem, Istimewa pada Grup) dan kotak pencarian instan pada modul Akun Pengguna & Grup Sistem (`services.html`). Mengintegrasikan atribut `data-filter-hidden` pada elemen baris tabel (`tr.dataset.filterHidden = isMatch ? '0' : '1'`) agar selaras dengan mesin paginasi universal (`attachTablePagination`), mencegah penimpaan visibilitas baris secara sepihak saat evaluasi halaman paginasi. Mengotomatiskan reset halaman pertama (`setPage(1)`) saat filter atau kata kunci berubah, memperbarui tampilan pesan kosong (*empty state message*) secara dinamis saat tidak ada hasil pencarian yang cocok, memelihara status filter aktif saat siklus polling latar belakang (`renderSystem`), serta memperbarui lencana jumlah entri hasil filter (`X / Y Pengguna` dan `X / Y Grup`) secara interaktif.
- **Stabilisasi Bilah Alat Filter Pengguna & Grup serta Standardisasi Terminologi Linux (v4.8.35):** Mengatasi anomali pergeseran tata letak antarmuka (*layout shift*) saat memilih filter Sistem atau kategori lainnya pada subview Pengguna dan Grup (`services.html`). Mengisolasi kendali filter cepat dan pencarian ke dalam bilah alat khusus (*dedicated full-width toolbar strip* `.table-toolbar`) yang independen dari judul kartu (*card-header*), menjamin posisi tombol filter 100% stabil dengan pergeseran 0.00 piksel (*Zero Layout Shift*). Menyelaraskan seluruh terminologi antarmuka ke Bahasa Indonesia baku yang lugas dan mudah dipahami sysadmin tanpa kekakuan: mengganti istilah kaku "Istimewa" menjadi istilah teknis standar dunia **Privileged** untuk grup berakses administratif (`sudo`, `wheel`, `root`, `docker`, `adm`), menstandarkan klasifikasi tipe grup menjadi **Sistem** dan **Reguler**, serta memperjelas kolom menjadi **Grup Utama & Sekunder** dan **Anggota (Members)**.
- **Penyediaan Rute Pintasan /servers/{sid} & Perbaikan Tautan Notifikasi Alert (v4.8.36):** Menambahkan handler rute pintasan server `@app.get("/servers/{sid}")` pada backend FastAPI (`server/main.py`) yang secara otomatis mengalihkan permintaan (*HTTP 303 Redirect*) ke halaman rincian layanan server `/servers/{sid}/services` dengan tetap memelihara parameter query URL (*query string* seperti `?tab=users`). Mengeliminasi galat *404 Not Found (Halaman Tidak Ditemukan)* ketika pengguna mengakses URL server secara langsung, membuka bookmark, atau mengeklik tautan insiden. Menyelaraskan seluruh tautan notifikasi banner alert kritis dan tombol aksi modal detail masalah pada template dasar (`server/templates/base.html`) agar mengarah langsung ke target `/servers/{server_id}/services`.
- **Standarisasi Arsitektur RESTful Kanonikal Rincian Server & Sinkronisasi URL Tab Instan (v4.8.37):** Menetapkan rute kanonikal bersih `/servers/{sid}` sebagai endpoint primer halaman rincian server pada backend FastAPI (`server/main.py`) yang langsung merender antarmuka tanpa hop redirect tambahan (HTTP 200 OK langsung). Mengonfigurasi sub-rute `/servers/{sid}/services` secara semantik sebagai alias kompatibel ke belakang yang secara otomatis mengarahkan ke tab Layanan (`/servers/{sid}?tab=layanan`). Mengintegrasikan mekanisme sinkronisasi riwayat peramban instan (`history.replaceState`) pada fungsi `showTab()` di `services.html` sehingga pergantian tab (Users, Services, Firewall, Ports, Cron, Logs) memperbarui bilah URL secara real-time tanpa memicu pemuatan ulang halaman. Menyelaraskan seluruh tautan entitas terkait pada Dashboard (`dashboard.html`), Daftar Server (`servers.html`), Riwayat Insiden (`problems.html`), Probing (`probing.html`), File Manager (`file_manager.html`), dan Notifikasi Sistem (`base.html`) menuju rute kanonikal bersih `/servers/{sid}`.
- **Sinkronisasi Penghentian Unit Systemd oleh Operator & Kesadaran Dependensi Layanan (v4.8.38):** Menghubungkan secara dua arah tindakan penghentian unit systemd oleh operator (`/api/servers/{sid}/systemd/stop`) dengan mesin deteksi insiden (`_problem_instances`), tabel layanan (`Service`), dan rekonsiliasi masalah (`sync_server_problems`). Mengeliminasi eskalasi keliru insiden kritis (`Layanan Down (KRITIS)`) pada server Tier-1 saat operator sengaja mematikan layanan melalui tab Systemd, dengan mengklasifikasikannya secara tepat sebagai Peringatan (*Warning*) terencana berlabel "Layanan {nama} dimatikan oleh operator ({username})" serta menekan alarm darurat dan sirene merah. Menyematkan intelijen dependensi lintas layanan (*Cross-Service Dependency Awareness*): jika suatu layanan inti gagal atau down di server yang sama sementara ada layanan prasyarat (seperti basis data atau daemon pendukung) yang sedang dihentikan sengaja oleh operator, sistem secara otomatis melampirkan konteks diagnosa `[INFO DEPENDENSI]` pada panduan solusi dan muatan JSON terstruktur rincian insiden. Menghadirkan lencana status khusus `DIHENTIKAN OPERATOR` pada tabel unit Systemd dan tabel Layanan terpantau guna memberikan visibilitas penuh bahwa sistem mengenali tindakan operator secara akurat.
- **Standarisasi Label Peringatan Tindakan Operator, Lencana Subordinat, dan Integrasi Status Reboot (v4.8.39):** Memperbaiki rendering keparahan pada Dasbor Utama (`dashboard.html`), Riwayat Insiden (`problems.html`), dan Rincian Server (`services.html`) agar label primer (`KRITIS`, `GAWAT`, `PERINGATAN`, `INFO`) selalu dipertahankan di posisi teratas meskipun diabaikan atau ditangani. Menampilkan lencana subordinat `DIABAIKAN` dan/atau `✓ DITANGANI` secara berdampingan di bawah label primer. Memastikan anomali tindakan operator pada server klien tetap dipantau pada kartu Insiden Terkini halaman utama. Memperluas deteksi ketidakaktifan agen untuk mengenali perintah reboot dari operator sebagai Peringatan berlabel `Server sedang di-reboot oleh operator`, serta menghapus clutter string diagnostik yang tidak diperlukan.
- **Penyempurnaan Tata Letak, Desain Visual, dan Tipografi Tabel Insiden Terkini Dasbor (v4.8.40):** Mengimplementasikan arsitektur tata letak tetap (`table-layout: fixed`) dengan pendefinisian `<colgroup>` khusus pada tabel kartu *Insiden Terkini* di halaman Dasbor Utama. Mengisolasi tata letak tabel insiden dasbor ke namespace kelas independen (`.dash-col-time`, `.dash-col-server`, `.dash-col-sev`, `.dash-col-desc`, `.dash-col-durasi`, `.dash-col-action`) guna mengatasi anomali tumpang-tindih teks antara lencana status subordinat (`DIABAIKAN` / `✓ DITANGANI`) dan kolom deskripsi masalah akibat batasan kelas global. Menambahkan indikator status host (`●` aktif/down/globe), lencana grup sistem, pemformatan durasi insiden ke dalam badge pill monospasi NOC yang kontras, indikator baris interaktif (`.dash-row-arrow`), penautan langsung tombol "Riwayat Lengkap →" ke `/problems`, sinkronisasi dinamis status ikon kartu dengan insiden terbuka, serta pembersihan duplikasi durasi pada teks status stale di backend.
- **Standarisasi Tata Letak, Desain Visual, dan Kebahasaan Baku Tabel Insiden Terbuka (v4.8.41):** Mengimplementasikan tata letak tetap (`table-layout: fixed !important`) dengan pendefinisian `<colgroup>` terukur (`115px`, `175px`, `165px`, `auto`, `120px`, `260px`, `95px`) pada tabel kartu *Insiden Terbuka* di halaman Insiden (`problems.html`). Mengisolasi dan memperluas kolom keparahan (`165px`) guna mengeliminasi tumpang-tindih lencana subordinat (`DIABAIKAN` / `✓ DITANGANI`) terhadap kolom kejadian. Menghadirkan indikator titik status host (`●` aktif/down/globe) dan grup sistem, memformat durasi insiden dengan badge pill monospasi NOC yang terlindungi dari pembaruan timer berkala, membersihkan inkonsistensi bahasa asing ke Bahasa Indonesia baku (`Kritis`, `Peringatan`), serta mengoptimalkan elevasi header kartu dan perataan tombol tindakan 24x24 px.
- **Pengawas Pola Log Kritis Kernel & Sistem, Deteksi OOM Killer, Galat Storage I/O, dan Korelasi Akar Masalah Layanan (v4.8.42):** Menghadirkan subsistem pengawasan mendalam terhadap anomali fatal kernel Linux pada mesin klien (zero external dependency) yang mencakup pembunuhan proses akibat kehabisan memori (*OOM Killer* via `/proc/vmstat` dan `journalctl -k`), kegagalan baca/tulis media penyimpanan (*Storage Disk I/O Error*), crash memori aplikasi (*Segmentation Fault*), dan *Kernel Panic*. Mengintegrasikan korelasi cerdas lintas-entitas (*Root Cause Analysis*) pada mesin backend: kegagalan layanan down yang dipicu oleh OOM killer secara otomatis dilabeli secara transparan (`Layanan {name} Down — Dihentikan paksa oleh Kernel (OOM Killer)`). Menyematkan visualisasi metrik operasional OOM Kills pada kartu *Kapasitas Memori*, lencana sorotan keparahan pada tabel Log Sistem Journal, serta lencana status `OOM KILLED` merah tegas pada tabel layanan dan unit Systemd.
- **Perbaikan Kritis Monopoli Connection Pool Basis Data & Pencegahan Pemblokiran Event Loop Asinkron (v4.8.43):** Mengeliminasi kendala saturasi 100% pada *QueuePool* SQLAlchemy MariaDB dan pemblokiran fatal *event loop* asyncio Uvicorn yang dipicu oleh endpoint *long-polling* agen (`/api/agent/file-requests`, `/api/agent/terminal-requests`). Mengimplementasikan validasi API key berbasis *in-memory cache* 120 detik (`_get_cached_server_id`), melepaskan seluruh pengikatan sesi DB sebelum jeda asinkron `asyncio.wait_for(...)`, memperbesar kapasitas pool koneksi (`POOL_SIZE=25`, `POOL_MAX_OVERFLOW=50`), serta menetapkan `pool_timeout=10` guna mencegah deadlock. Memulihkan latensi respons dasbor menjadi ~4 ms dan menuntaskan insiden keliru `Probe Pantau Web Dashboard GAGAL` serta `Agen tidak melapor`.

---

## 1. Pemasangan Dashboard (Server Pusat)

Dukungan sistem operasi: Ubuntu 20.04/22.04/24.04 LTS atau Debian 11/12.

```bash
# 1. Perbarui paket dan pasang dependensi dasar
sudo apt update && sudo apt install -y git python3 python3-venv python3-pip mariadb-server rsync
sudo systemctl enable --now mariadb

# 2. Clone repositori dan jalankan installer
git clone https://github.com/azhuka/pantau-server.git
cd pantau-server
sudo bash install-server.sh
```

Skrip installer otomatis melakukan konfigurasi:
- Membuat pengguna sistem `pantau`
- Menyiapkan database MariaDB
- Memasang dan mengaktifkan service systemd `pantau-server.service`
- Meminta kata sandi awal untuk akun administrator

Setelah instalasi selesai, akses dashboard melalui browser:
- **Alamat:** `http://<IP-SERVER>:8400`
- **Username:** `admin`
- **Password:** kata sandi yang ditentukan saat instalasi

**Memeriksa Status Service Dashboard:**
```bash
sudo systemctl status pantau-server.service
```

**Reset Kata Sandi Admin via CLI:**
```bash
sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py \
  --username admin --role admin --password 'password-baru'
```

---

## 2. Pemasangan Agen pada Server Klien

Agen Pantau beroperasi dengan metode **Outbound Pull** (koneksi keluar dari klien ke server pusat setiap 5–10 detik via HTTP/HTTPS POST). Klien tidak memerlukan port inbound terbuka dan dapat berjalan di balik NAT, firewall, atau jaringan privat (LAN/VPN).

1. Buka dashboard: Masuk ke menu **Daftar Server → Tambah Server**, kemudian salin **API Key** (64 karakter hex).
2. Di server klien yang akan dipantau, unduh dan jalankan installer agen:

```bash
sudo curl -fsSL -o /tmp/pantau-install.sh \
  https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh
sudo bash /tmp/pantau-install.sh
```

Installer akan meminta konfigurasi interaktif:
- **URL Dashboard:** Masukkan URL server pusat (contoh LAN/VPN: `http://172.30.1.40:8400` atau domain `https://pantau.domainanda.com`).
- **API Key:** Masukkan API Key yang telah disalin dari dashboard.

Skrip installer klien otomatis melakukan:
- Validasi konektivitas dan autentikasi token ke Dashboard.
- Menulis konfigurasi aman pada `/etc/pantau/config.json` (izin `0640`, owner `root:pantau`).
- Memasang dan mengaktifkan service systemd `agent_pantau.service` di bawah pengguna `pantau`.

*(Mode non-interaktif untuk skrip automasi/Ansible: `sudo bash /tmp/pantau-install.sh "http://<IP-DASHBOARD>:8400" "<API_KEY>"`)*

Server klien akan terdeteksi dan berstatus online di dashboard dalam ±10 detik.

**Pemeriksaan Service dan Log Agen Klien:**
```bash
sudo systemctl status agent_pantau.service
sudo journalctl -u agent_pantau -f
```

---

## Panduan Antarmuka & Navigasi

### Dashboard Utama
- **Ringkasan Armada:** Jumlah server aktif, server offline, layanan bermasalah, dan beban rata-rata sistem.
- **Tabel Status & Kinerja:** Tampilan ringkas status koneksi, CPU, RAM, Storage, dan layanan per server, dilengkapi pencarian dan filter grup.
- **Insiden Terkini:** Daftar insiden aktif terpusat yang diurutkan berdasarkan tingkat keparahan (*Kritis*, *Gawat*, *Peringatan*).

### Rincian Server
- **Tab Kinerja & Spesifikasi:** Utilisasi CPU, memori, swap, partisi storage, throughput interface jaringan, serta grafik riwayat beban sistem (1 jam hingga 30 hari).
- **Tab Riwayat & Masalah:** Riwayat insiden pada server, rekomendasi penanganan teknis, opsi abaikan sementara (*mute/silence*), dan konfirmasi penanganan (*acknowledge*).
- **Tab Layanan:** Kontrol unit systemd (Mulai, Hentikan, Restart, Tambah Layanan), penandaan layanan utama (*core*) vs sekunder, serta akses log service.
- **Tab Manajer Tugas:** Daftar proses sistem teratas berdasarkan pemakaian CPU dan RAM, dilengkapi opsi terminasi proses (*SIGTERM* atau *SIGKILL*).
- **Tab Akun Pengguna:** Daftar akun lokal Linux, status kunci (*lock/unlock*), dan pembuatan akun baru.
- **Tab Port Listening:** Audit socket jaringan TCP dan UDP yang sedang terbuka beserta proses pemiliknya.
- **Tab Firewall:** Status UFW, aturan firewall, daftar alamat IP yang diblokir pada tingkat kernel via iptables, serta tombol blokir/buka blokir IP.
- **Tab Sertifikat SSL:** Pemantauan tanggal kedaluwarsa berkas sertifikat SSL lokal dan sertifikat web server.
- **Tab Tugas Terjadwal:** Manajemen entri cron sistem pada `/etc/cron.d/`.
- **Tab Cadangan:** Pemantauan status integritas berkas dump basis data (MySQL, MariaDB, PostgreSQL) dan arsip cadangan sistem di direktori standar/kustom, deteksi berkas 0-byte, serta verifikasi usia cadangan.
- **Tab Logging:** Log viewer terpadu untuk berkas log sistem dan journald.
- **Terminal Web (`>_ Terminal`):** Akses shell root interaktif langsung di browser.
- **File Manager (`File Manager`):** Remote file explorer untuk membaca, mengunggah, mengunduh, dan menyunting berkas konfigurasi.

---

## Model Kontrol Akses (RBAC 3-Tier)

| Fitur / Tindakan | Master Admin | Operator (Sudo) | Viewer |
|:---|:---:|:---:|:---:|
| Melihat Dashboard, Metrik & Log | Ya | Ya | Ya |
| Kelola Server & Layanan (Start/Stop/Restart) | Ya | Sesuai Izin | Tidak |
| Akses Terminal Web & File Manager | Ya | Sesuai Izin | Tidak |
| Restart Sistem (Reboot) & Update OS | Ya | Sesuai Izin | Tidak |
| Kelola Firewall (UFW) & Blokir IP | Ya | Sesuai Izin | Tidak |
| Manajemen Pengguna (Tambah, Edit, Kunci) | Ya | Sesuai Izin | Tidak |
| Audit Trail Aktivitas Pengguna | Ya | Sesuai Izin | Tidak |
| Menghapus / Mengubah Akun Master Admin | Ya (Pribadi) | Ditolak | Tidak |
| Profil Akun Pribadi & Konfigurasi 2FA | Ya | Ya | Tidak |

---

## Klasifikasi Level Operasional & Keparahan Insiden

Pantau Server menerapkan hierarki evaluasi insiden berdasarkan tingkat kepentingan operasional server:

### 1. Klasifikasi Level Operasional
- **Tier 1 (Layanan Utama):** Server dengan beban kerja vital yang memerlukan ketersediaan tinggi. Gangguan sistem bereskalasi hingga tingkat **KRITIS**, memicu banner merah global dan alarm audio.
- **Tier 2 (Layanan Pendukung):** Server pendukung operasional yang memiliki toleransi pemulihan. Gangguan sistem bereskalasi maksimal hingga tingkat **GAWAT**, tanpa memicu banner global atau alarm audio.
- **Tier 3 (Layanan Sementara / Uji Coba):** Server pengembangan, staging, atau pengujian. Gangguan sistem dibatasi pada tingkat **PERINGATAN**.

### 2. Matriks Keparahan Insiden

| Kondisi / Insiden Sistem | Tier 1 (Utama) | Tier 2 (Pendukung) | Tier 3 (Sementara) | Catatan Operasional |
|:---|:---:|:---:|:---:|:---|
| **Server Klien Offline (Tidak Melapor)** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Banner merah & alarm audio hanya aktif untuk Tier 1 |
| **Partisi Disk Read-Only** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Menandakan proteksi kernel akibat kegagalan I/O |
| **Penyimpanan Disk Penuh (100%)** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Menghambat penulisan data dan transaksi database |
| **Layanan Utama (*Core Service*) Down** | 🔴 **KRITIS** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Berlaku untuk layanan berstatus Utama |
| **Layanan Sekunder Down** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | Layanan pendukung (misal cache/worker) |
| **Tindakan Pemeliharaan Operator** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | 🟡 **PERINGATAN** | Server shutdown atau service stop yang disengaja |
| **Penggunaan RAM / CPU $\ge 90\%$** | 🟠 **GAWAT** | 🟠 **GAWAT** | 🟡 **PERINGATAN** | Utilisasi sumber daya mendekati batas kapasitas |
| **Pembaruan Paket Sistem Tersedia** | 🔵 **INFO** | 🔵 **INFO** | 🔵 **INFO** | Pembaruan paket keamanan atau rilis distro Linux |

---

## Pembaruan Sistem (Update)

### 1. Pembaruan Server Pusat
Jalankan di server dashboard:
```bash
cd /opt/pantau/server/pantau-server   # sesuaikan path repositori lokal
git pull
sudo bash install-server.sh
```
*Berkas konfigurasi `.env` dan database MariaDB tidak akan terhapus saat pembaruan dijalankan.*

### 2. Pembaruan Otomatis Armada Agen (Fleet-Wide OTA)
Saat server pusat diperbarui ke versi baru, seluruh agen klien secara otomatis mengunduh pembaruan pada siklus pelaporan berikutnya (dalam ~5 detik):
1. Server mendeteksi versi agen klien lebih lama daripada versi dashboard.
2. Server mengirimkan instruksi pembaruan beserta URL berkas agen dan hash SHA-256 resmi.
3. Agen klien mengunduh berkas pembaruan, memeriksa validitas hash SHA-256, menguji sintaks via `py_compile`, memperbarui berkas `/opt/pantau/agent/agent_pantau.py`, lalu me-restart service secara mandiri.

### 3. Pembaruan Agen Manual
- **Melalui Dashboard:** Klik tombol **`⚡ Push Update (OTA)`** pada halaman rincian server.
- **Melalui Terminal Klien:**
  ```bash
  sudo curl -fsSL -o /tmp/pantau-install.sh https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh && sudo bash /tmp/pantau-install.sh
  ```

---

## Konfigurasi Reverse Proxy Nginx & SSL (Produksi)

Secara bawaan dashboard berjalan pada port HTTP 8400. Untuk lingkungan produksi, disarankan menggunakan reverse proxy Nginx dengan enkripsi HTTPS (SSL/TLS). Berkas template konfigurasi tersedia di direktori `deploy/`.

```bash
# 1. Pasang konfigurasi Nginx
sudo cp deploy/nginx/pantau-server.conf /etc/nginx/sites-available/pantau-server
sudo nano /etc/nginx/sites-available/pantau-server   # Sesuaikan server_name dengan domain Anda

# 2. Aktifkan konfigurasi
sudo ln -s /etc/nginx/sites-available/pantau-server /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# 3. Pasang sertifikat SSL Let's Encrypt
sudo certbot --nginx -d pantau.domainanda.com

# 4. Aktifkan flag cookie aman pada /opt/pantau/server/.env
# Ubah: SESSION_COOKIE_SECURE=True
sudo systemctl restart pantau-server.service
```

---

## Pencadangan, Pemulihan & Retensi Data

### Cadangan dan Pemulihan Database
Data metrik dan konfigurasi tersimpan di MariaDB (`pantau_db`) dan berkas `/opt/pantau/server/.env`.

```bash
# Backup database & environment
sudo mysqldump -u root pantau_db | gzip > pantau_db_$(date +%F).sql.gz
sudo cp /opt/pantau/server/.env .env_$(date +%F)

# Restore database dari file backup
gunzip -c pantau_db_YYYY-MM-DD.sql.gz | sudo mysql -u root pantau_db
sudo systemctl restart pantau-server.service
```

### Kebijakan Retensi Data Otomatis
Sistem secara berkala membersihkan data lama setiap jam agar kapasitas penyimpanan tetap terjaga:
- **Snapshot Metrik Mentah (5-10 detik):** 24 jam (agregasi rata-rata per jam disimpan selama 90 hari).
- **Log Permintaan Selesai:** 30 hari.
- **Insiden yang Terselesaikan (*Resolved*):** 90 hari.
- **Riwayat Perintah Remote:** 180 hari.
- **Audit Trail Pengguna:** 365 hari (1 tahun).

---

## Panduan Penyelesaian Masalah (Troubleshooting)

| Gejala Masalah | Kemungkinan Penyebab & Solusi |
|:---|:---|
| Server klien berstatus `Offline` | Periksa service agen: `sudo systemctl status agent_pantau.service`. Pastikan klien dapat menjangkau port 8400 server pusat (uji via `curl -Iv http://<IP-SERVER>:8400`). |
| Akses terminal ditolak (`403 Forbidden`) | Akun pengguna belum memiliki izin terminal (`can_terminal`). Hubungi Master Admin untuk memperbarui hak akses. |
| Terminal menampilkan error `409 Conflict` | Terdapat sesi terminal lain yang sedang aktif pada server tersebut (dibatasi 1 sesi aktif per server demi keamanan). |
| Pembaruan OS (APT) terkunci | Terdapat proses APT/dpkg lain yang sedang berjalan di klien. Buka terminal web dan jalankan `sudo dpkg --configure -a`. |
| Tombol Push OTA tidak muncul | Versi agen pada klien sudah mutakhir atau identik dengan versi dashboard server. |
| Gagal autentikasi 2FA / Kehilangan perangkat | Buka terminal server pusat dan jalankan: `sudo /opt/pantau/server/env/bin/python /opt/pantau/server/seed_admin.py --username <user> --reset-2fa`. |
