# Pantau Server

Sistem pemantauan infrastruktur server NOC (*Network Operation Center*) terpusat, observabilitas telemetri performa tinggi, investigasi integritas berkas (*File Integrity Monitoring* / FIM), audit kepatuhan layanan dan proses, serta manajemen operasional armada server Linux multi-node mandiri.

---

## 1. Bahasa Domain Tunggal (*Ubiquitous Language*)

Seluruh pengembang, asisten AI, kode sumber, skema basis data, antarmuka web, dan dokumentasi **wajib mematuhi istilah baku di bawah ini**. Dilarang keras menggunakan istilah padanan, sinonim rancu, atau istilah terjemahan bebas yang tercantum pada label *Hindari*.

### A. Infrastruktur & Arsitektur Inti

**Server Klien**:
Mesin server fisik, virtual machine (VPS/KVM), atau kontainer LXC berbasis sistem operasi Linux yang menjalankan daemon agen pemantau (`agent_pantau.py`) untuk mengirimkan telemetri berkala ke Pantau Server.
*Hindari*: Node, instance, slave, remote box, target server, client machine.

**Pantau Server**:
Aplikasi control plane terpusat berbasis Python (FastAPI/Uvicorn) dan basis data relasional (MariaDB/MySQL) yang bertugas menyerap telemetri agen, menyajikan antarmuka visual dasbor NOC, mengevaluasi peringatan insiden, mengelola antrean perintah OTA, dan memfasilitasi Web Terminal serta File Manager.
*Hindari*: Master host, central node, backend box, monitoring server.

**Dasbor NOC**:
Antarmuka operasional visual utama Pantau Server (`server/templates/dashboard.html`) yang menyajikan matriks kesehatan real-time seluruh armada Server Klien dalam kepadatan informasi tinggi (*high-density grid/table*). Komponen ini berstatus terisolasi dan dilindungi secara mutlak.
*Hindari*: Main page, overview window, monitor hub, home view.

**Agen Klien (`agent_pantau`)**:
Skrip daemon pemantau mandiri berbasis Python standar (Python 3.10+) tanpa dependensi pihak ketiga (*zero external dependency*) yang berjalan di `/opt/pantau/agent/agent_pantau.py` pada setiap Server Klien untuk mengumpulkan fakta fisik sistem dari `/proc`, `/sys`, socket kernel, dan systemd.
*Hindari*: Remote daemon, background scraper, collector script, client probe.

**Telemetri Heartbeat**:
Paket data JSON berkala yang dikirimkan oleh Agen Klien ke endpoint `/api/report` Pantau Server memuat metrik utilisasi CPU, alokasi memori fisik dan swap, kapasitas mount point disk, throughput I/O, statistik transmisi jaringan, inventaris proses teratas, serta status layanan aktif.
*Hindari*: Ping data, status scrape, poll report, periodic beacon.

**Arsitektur Transport**:
Saluran komunikasi satu arah terenkripsi HTTPS/TLS di mana Agen Klien bertindak sebagai inisiator permintaan (*outbound push*) ke Pantau Server melalui port aman (default 8400 / 443), meniadakan kebutuhan membuka port masuk (*inbound ports*) pada Server Klien.
*Hindari*: Inbound listener, reverse connection, agent socket.

---

### B. Observabilitas Layanan, Proses, & Jaringan

**Manajemen Layanan (*Services*)**:
Modul pengawasan dan audit unit systemd pada Server Klien untuk memantau status operasional (*active*, *inactive*, *failed*), waktu aktif (*uptime*), serta eksekusi kontrol layanan (*start*, *stop*, *restart*, *reload*).
*Hindari*: App supervisor, daemon manager, service checker.

**Socket Activation (SSH)**:
Dukungan pengelolaan unit socket pendamping (`ssh.socket` / `sshd.socket`) pada distro modern yang secara otomatis diselaraskan saat layanan SSH dihentikan atau di-restart guna mencegah kegagalan sesi shell remote.
*Hindari*: Port trigger, socket listener, helper socket.

**Peredaman Peringatan Layanan (*Service Muting*)**:
Mekanisme pengabaian peringatan deviasi atau kegagalan layanan tertentu secara permanen atau temporer (pilihan durasi: 2 jam, 24 jam, 7 hari, 30 hari) agar tidak memicu alarm palsu pada dasbor saat pemeliharaan.
*Hindari*: Silence rule, alarm disable, snooze alert, ignore list.

**Siklus Hidup Proses (*Process Lifecycle*)**:
Status kondisi eksekusi proses Linux pada Server Klien yang diklasifikasikan secara presisi sesuai kernel: *Running* (R), *Sleeping* (S/D), *Stopped* (T), dan *Zombie* (Z).
*Hindari*: Process state, task condition, PID status.

**Manajemen Proses & Sinyal Linux**:
Kapabilitas inspeksi dan manipulasi kontrol proses langsung dari antarmuka web melalui pengiriman sinyal POSIX resmi: penangguhan sementara (*SIGSTOP*), pemulihan (*SIGCONT*), terminasi santun (*SIGTERM*), dan pematian paksa (*SIGKILL*).
*Hindari*: Process killer, task terminator, shell stop.

**Safety Guardrail Proses**:
Mekanisme validasi proteksi mutlak pada backend dan agen yang memblokir pengiriman sinyal destruktif (*SIGKILL* / *SIGTERM*) ke proses-proses kritis sistem, mencakup *PID 1* (`systemd`/`init`), daemon remote shell (`sshd`), dan daemon pemantau (`agent_pantau`).
*Hindari*: Protected PID list, kill prevention, safety check.

**Pemantauan Integritas Berkas (*File Integrity Monitoring* / FIM)**:
Sub-sistem audit keamanan yang memantau perubahan atribut fisik (izin `chmod`, kepemilikan `chown`, ukuran berkas, timestamp `mtime`) dan integritas kriptografis hash SHA-256 pada berkas-berkas konfigurasi kritis di Server Klien.
*Hindari*: File audit, hash watcher, checksum scanner, integrity checker.

**Siklus Hidup Kejadian FIM**:
Tahapan penanganan anomali perubahan berkas yang tercatat dalam log FIM, meliputi status: *Terdeteksi* (belum ditinjau), *Ditinjau* (sedang dianalisis operator), *Disetujui* (perubahan sah diverifikasi), dan *Ditolak/Dipulihkan* (indikasi kompromi keamanan).
*Hindari*: FIM event status, incident progress, file diff state.

**Firewall UFW Visual**:
Modul manajemen grafis untuk antarmuka *Uncomplicated Firewall* (UFW) pada Server Klien yang memungkinkan pembacaan status, reload rule, pemblokiran alamat IP manual, serta pelepasan blokir per baris tabel.
*Hindari*: Port blocker, iptables visualizer, firewall toggle.

**Auto-Allow Port Krusial**:
Protokol keamanan otomatis yang mewajibkan penambahan izin akses port esensial (SSH 22, Web 80/443, Dashboard 8400) sebelum firewall diaktifkan guna mencegah operator terkunci keluar dari server (*anti-lockout protection*).
*Hindari*: Safe port opener, default port rule, anti-lockout bypass.

**Audit Port Terbuka (*Listening Ports*)**:
Daftar inventaris soket TCP/UDP aktif pada Server Klien hasil penemuan dinamis melalui pembacaan `/proc/net/*` atau utilitas `ss`, memetakan alamat ikat (*bind address*), nomor port, PID, nama proses pemilik, dan pengguna penanggung jawab.
*Hindari*: Open port list, netstat dump, socket scanner.

**Klasifikasi Akses Port (*Public vs Local*)**:
Kategori keterbukaan port jaringan: *Public* (terikat pada antarmuka publik `0.0.0.0` atau `::`) yang berisiko terpapar internet terbuka, versus *Local* (terikat ketat pada loopback `127.0.0.1` atau `::1`).
*Hindari*: Exposure type, port binding status, network scope.

**Sertifikat SSL/TLS Tracking**:
Pelacakan inventaris sertifikat TLS lokal pada Server Klien yang memindai tanggal kedaluwarsa, sisa hari aktif (*days left*), Subject Alternative Names (SAN), dan otoritas penerbit (CA Issuer) untuk mencegah insiden downtime akibat sertifikat kedaluwarsa.
*Hindari*: Cert monitor, SSL checker, HTTPS probe.

**Pemantauan Cron & Systemd Timers**:
Pengawasan jadwal tugas otomatis pada Server Klien yang mengekstrak konfigurasi crontab sistem (`/etc/cron*`, `/var/spool/cron`) dan unit `systemd.timer` aktif beserta jadwal eksekusi berikutnya (*next run*).
*Hindari*: Scheduled tasks, cron scraper, timer watcher.

---

### C. Manajemen Berkas & Terminal Remote

**Web File Manager**:
Modul penjelajah direktori dan manipulasi berkas interaktif pada Server Klien melalui antarmuka web, mendukung penjelajahan hierarki, unggah/unduh berkas, penyunting teks berbasis web, dan penghapusan aman.
*Hindari*: File browser, directory explorer, FTP web, web disk.

**Backup Berkas Otomatis (`.bak`)**:
Prosedur keselamatan mutlak pada Web File Manager yang otomatis membuat duplikat cadangan berkas dengan ekstensi `.bak` sebelum konten berkas diubah atau ditimpa oleh penyunting teks.
*Hindari*: Safe save, version copy, file history, auto backup.

**Path Terproteksi Inti Sistem**:
Daftar direktori sistem operasi Linux penting (`/boot`, `/sys`, `/proc`, `/dev`, direktori pustaka inti) yang dilindungi secara permanen dari operasi manipulasi destruktif (hapus, timpa, modifikasi izin) pada Web File Manager.
*Hindari*: Blacklisted path, restricted folder, system lock.

**Web Terminal (xterm.js)**:
Antarmuka konsol shell interaktif berbasis pustaka xterm.js di dalam peramban web yang terhubung ke sesi shell Server Klien melalui saluran WebSocket dengan latensi rendah dan dukungan *dynamic resize*.
*Hindari*: Web shell, console popup, terminal window.

**Native Linux PTY Shell**:
Mekanisme emulasi pseudoterminal Unix nyata (`/dev/pts/*`) menggunakan modul bawaan Python `pty` yang mendukung interpretasi lengkap karakter kontrol VT100, ANSI color codes, tab completion, dan sinyal interaktif (`SIGINT`/`Ctrl+C`).
*Hindari*: Raw bash pipe, pseudo shell, tty wrapper.

**Terminal Clipboard Bridge**:
Mekanisme penanganan papan klip (clipboard) dwiarah pada Web Terminal yang mengadopsi standar ADR-0027: penyalinan kontekstual (`Ctrl+C` teks seleksi vs sinyal `SIGINT`), penempelan aman `Ctrl+V`, penyalinan otomatis saat seleksi mouse (*copy-on-select* debounced), serta dialog konfirmasi penempelan multi-baris 3-arah (*Batal*, *🔗 Jadikan 1 Baris / Flatten*, *📋 Tempel Apa Adanya*).
*Hindari*: Terminal copy paste hack, raw multiline paste, uncontrolled shell clipboard.

**Terminal From Path**:
Aksi peluncuran sesi Web Terminal langsung dari antarmuka Web File Manager dengan navigasi otomatis `cd '<path>'` ke direktori aktif target (mengadopsi standar ADR-0026).
*Hindari*: Quick shell, folder shell, manual terminal cd.

---

### D. Audit, Insiden, & Kontrol Akses (RBAC)

**Tiket Masalah (*Problems*)**:
Entitas catatan insiden sistemik pada Pantau Server yang terpicu saat terdeteksi deviasi metrik (CPU/RAM/Disk melampaui batas ambang kritis), kegagalan layanan penting, anomali FIM, atau Server Klien berstatus *Offline*.
*Hindari*: Incident log, alert list, failure ticket, warning entry.

**Riwayat Tindakan (*Action History / Audit*)**:
Rekam jejak kronologis terpadu di dalam tab Masalah yang mencatat seluruh intervensi manual atau otomatis (restart service, kill process, block IP, edit file, login, dispatch OTA), mencakup nama aktor, target server, waktu eksekusi, dan hasil.
*Hindari*: Activity log, execution history, user audit, event log.

**Auto-Pruning Tiket & Riwayat**:
Mekanisme pembersihan berkala otomatis pada basis data Pantau Server untuk menghapus tiket masalah berstatus selesai (*resolved*) dan catatan audit lama yang telah melampaui batas waktu retensi terkonfigurasi.
*Hindari*: Auto purge, old log cleanup, TTL delete.

**Kontrol Akses Berbasis Peran (*RBAC Parity*)**:
Sistem otorisasi pengguna berbasis hak istimewa granular di mana pembagian wewenang operasional ditentukan secara transparan melalui matriks izin `can_*`.
*Hindari*: User permissions, role matrix, access level.

**Master Admin**:
Akun administrator utama tertinggi di Pantau Server yang memiliki wewenang mengelola konfigurasi sistem global, membuat/menghapus akun pengguna, dan memberikan hak izin operasional.
*Hindari*: Superuser, root user, main account, owner.

**Operator**:
Akun pengelola operasional yang dapat diberikan izin akses penuh oleh Master Admin (`can_* = 1`), memiliki otoritas operasional harian yang setara (*functional parity*) dengan Master Admin dalam mengelola Server Klien.
*Hindari*: Sub-admin, viewer, staff account, operator user.

**Izin Granular (`can_*`)**:
Daftar switch otorisasi spesifik pada profil pengguna (`can_terminal`, `can_manage_services`, `can_manage_files`, `can_manage_firewall`, `can_manage_processes`, `can_reboot`) yang menegakkan kontrol akses di tingkat endpoint API backend.
*Hindari*: User flags, capability switches, permission toggles.

**Proteksi Mutlak Integritas Akun**:
Aturan keamanan bawaan pada backend yang melarang keras akun Operator menghapus akun dirinya sendiri dan melarang keras akun Operator menghapus akun `master-admin`.
*Hindari*: Account self-defense, immutability rule, anti-delete flag.

---

### E. Desain Antarmuka, Tabel, & Paginasi

**Header Kolom Tindakan**:
Nama header kolom kontrol tindakan pada seluruh tabel antarmuka Pantau Server yang distandarisasikan secara seragam menjadi **"Tindakan"** (diawali huruf besar, sisanya huruf kecil).
*Hindari*: TINDAKAN, AKSI, Aksi, Operasi, Kontrol, Action, Tombol.

**Dropdown Aksi ▾**:
Pola penyajian menu kontrol tindakan terpadu (`<details class="noc-act-dropdown">`) yang **wajib digunakan secara seragam pada seluruh baris tabel yang menyediakan lebih dari 2 (> 2) jenis aksi**. Wajib diisolasi dengan elevasi `z-index: 9999` saat terbuka.
*Hindari*: Context menu, action dropdown, option list, action button group.

**Tombol Aksi Langsung (*Inline Action Buttons*)**:
Pola penyajian tombol kontrol tindakan sejajar yang **hanya digunakan pada tabel dengan 1 atau 2 (≤ 2) jenis aksi** (seperti tabel Port atau Proses). Seluruh baris dalam tabel tersebut wajib seragam tanpa mencampuradukkan dropdown.
*Hindari*: Direct buttons, row actions, inline triggers.

**Paginasi Universal ($\le 10$ Baris Sembunyi)**:
Standar logika navigasi data pada seluruh tabel di mana bilah paginasi (`.table-pagination-bar`) **wajib otomatis disembunyikan (`display: none !important`) jika jumlah baris data $\le 10$**, dan **hanya tampil (`display: flex`) jika baris data $> 10$**. Seluruh tabel wajib terhubung ke mesin `attachTablePagination()` di `base.html`.
*Hindari*: Table pager, row pagination, page switcher, static pagination.

**Kepadatan Data NOC (*NOC Data Density*)**:
Prinsip desain antarmuka ringkas berorientasi pusat kendali: padding sel rapat (3px–6px), tinggi baris proporsional (~30–34px), ukuran font badge 9.5px, string panjang dialihkan ke tooltip hover (`title="..."`), dan data esensial diutamakan tanpa pemborosan *whitespace*.
*Hindari*: Compact view, tight table, dense mode, small UI.

**Dual-Render Sinkron**:
Kewajiban arsitektur antarmuka di mana setiap komponen atau tabel yang dirender awal oleh backend (Jinja2 HTML) dan dirender ulang secara dinamis oleh frontend (JavaScript via WebSocket/AJAX) **wajib memiliki struktur HTML, class CSS, dan logika tampilan yang 100% identik**.
*Hindari*: Server-client parity, template-JS sync, double render mismatch.

**Adaptabilitas Kontras Multi-Tema**:
Penegakan kontras visual antarmuka menggunakan variabel CSS semantik (`var(--card)`, `var(--text)`, `var(--dim)`) yang teruji tajam dan ramah mata pada Dark Mode maupun Light Mode, melarang mutlak warna teks atau latar hardcoded statis yang memicu teks tidak terbaca (*blind text*).
*Hindari*: Theme switcher, dark mode fix, contrast toggle.

---

### F. Alur Kerja Rilis & Otomasi Pembaruan

**Otomasi SemVer 7 Berkas (`sop_release.py`)**:
Skrip otomasi produksi ([`tools/sop_release.py`](file:///home/bos/rj45/tools/sop_release.py)) yang mengeksekusi kenaikan versi SemVer secara atomik pada 7 berkas inti, pengujian sintaksis Python/Shell/Jinja, restart daemon lokal, dan publikasi Git/Tag/GitHub Release dalam 15–30 detik.
*Hindari*: Manual bump, release script, deploy tool, version pusher.

**Verifikasi Lapangan Mutlak 100% Armada**:
Prosedur pembuktian kualitas wajib di mana asisten/pengembang dilarang menyatakan rilis selesai sebelum melakukan kueri SQL langsung ke basis data (`SELECT s.id, s.hostname, e.agent_version, s.last_seen FROM servers s...`) yang membuktikan seluruh armada Server Klien telah memperbarui agen dan melaporkan versi baru.
*Hindari*: Blind deploy, silent release, assumption check.

**Arsitektur Antrean OTA Bebas Penguncian (*Zero-Lockout Pipeline*)**:
Saluran pembaruan Agen Klien jarak jauh yang bebas dari cooldown global, dilengkapi mekanisme *auto-heal* pembatalan perintah yang tersangkut >2 menit, dan *auto-resolve* status perintah menjadi `success` begitu menerima telemetri aktif pertama dari versi baru.
*Hindari*: OTA queue, agent updater, fleet upgrade channel.

**Arsitektur Agnostik & Zero-Hardcode Universal**:
Prinsip rekayasa mutlak di mana backend dan agen beroperasi secara universal terhadap sembarang tumpukan aplikasi Linux tanpa men-hardcode nama aplikasi pihak ketiga, path berkas kaku, atau daftar port vendor spesifik.
*Hindari*: Hardcoded checks, vendor patch, static map.

---

## 2. Prinsip Rekayasa Sistemik & Batas Cakupan (*System Boundaries*)

1. **Proteksi Mutlak Halaman Dasbor (`server/templates/dashboard.html`):**
   Berkas dasbor utama berstatus *frozen core*. Dilarang keras memodifikasi berkas ini tanpa instruksi tertulis eksplisit dan analisis dampak menyeluruh dari operator.
2. **Kemandirian Agen Klien (*Zero External Dependency*):**
   Agen klien (`agent_pantau.py`) wajib beroperasi murni menggunakan modul pustaka standar Python 3.10+ (`os`, `sys`, `socket`, `subprocess`, `urllib`, `ssl`, `json`, `hashlib`, `time`). Dilarang menginstal modul pip pihak ketiga (`psutil`, `requests`, dll.) pada Server Klien.
3. **Kejujuran Data & Anti-Atribusi Semu (*Zero-Fake Data*):**
   Sistem hanya boleh menampilkan data terukur fisik dari kernel. Dilarang menuduh akun pengguna melakukan pengubahan hanya berdasarkan kepemilikan berkas statis (`st_uid`), dilarang memalsukan status proses, dan dilarang menyamarkan ketiadaan instrumen ukur dengan tebakan semu.
4. **Eksekusi Shell Aman (*Least Privilege & Sanitized Execution*):**
   Seluruh pemanggilan subsistem shell pada agen dan backend wajib menggunakan daftar argumen eksplisit (`shell=False`) guna memitigasi risiko *command injection*.

---

## 3. Spesifikasi Baku Antarmuka Pengguna & Ergonomi Visual (UI/UX)

1. **Paginasi Universal ($\le 10$ Baris Sembunyi):**
   - Baris $\le 10$: Bilah kontrol paginasi (`.table-pagination-bar`) wajib otomatis disembunyikan (`display: none !important`).
   - Baris $> 10$: Bilah paginasi tampil (`display: flex`).
   - Dilarang keras menyematkan opsi `alwaysShow: true` tanpa instruksi eksplisit operator.
2. **Standardisasi Kolom Tindakan:**
   - Nama header kolom wajib **"Tindakan"** (Kapitalisasi huruf awal besar).
   - Baris dengan $> 2$ opsi aksi: Gunakan menu dropdown `Aksi ▾` (`<details class="noc-act-dropdown">`) dengan `z-index: 9999`.
   - Baris dengan $\le 2$ opsi aksi: Gunakan tombol inline sejajar. Pola wajib seragam di seluruh baris dalam satu tabel.
   - Ikon umum (Hapus, Salin, Tutup, Muat Ulang) menggunakan SVG bersih dengan `title="..."` tanpa teks boros.
3. **Kepadatan Informasi NOC:**
   - Kolom informatif mendapatkan ruang leluasa; kolom ringkas dioptimalkan rapat.
   - Detik waktu dihilangkan dari tampilan sel (`%H:%M` atau `%d %b %H:%M`) dan disematkan di tooltip `title="..."`.
   - Ukuran direktori hanya menampilkan teks `"Direktori"`; rincian file di dalam tooltip hover.
4. **Protokol 2-Tahap untuk Perombakan Visual:**
   - **Tahap 1:** Sajikan dan uji prototipe visual (HTML/CSS) statis terlebih dahulu.
   - **Tahap 2:** Implementasi logika backend dan skema basis data baru dieksekusi setelah operator menyetujui estetika visual pada Tahap 1.

---

## 4. Alur Kerja Standar Operasional (SOP) & Otomasi Rilis

Setiap kali menyelesaikan penambahan fitur, perbaikan bug, atau refactor:

1. **Pengujian Sintaksis Mandiri:**
   - Python: `python3 -m py_compile` pada seluruh berkas `.py` yang dimodifikasi.
   - Shell: `bash -n` pada seluruh skrip shell.
   - Jinja2: Uji kompilasi template di lingkungan virtualenv.
2. **Eksekusi Rilis Satu Perintah:**
   ```bash
   ./tools/sop_release.py [versi_baru] \
     --commit-msg "jenis(lingkup): deskripsi bahasa baku (vX.Y.Z)" \
     --title "vX.Y.Z - Judul Baku Bahasa Indonesia" \
     --notes "Rincian rilis untuk GitHub Releases" \
     --changelog "Blok catatan teknis untuk dimasukkan ke DEVELOPMENT.md" \
     --extra-files <berkas_tambahan>
   ```
3. **Verifikasi Lapangan Mutlak 100% Armada:**
   Kueri basis data untuk memastikan seluruh armada aktif telah melapor pada versi baru:
   ```bash
   PYTHONPATH=/home/bos/rj45/server /home/bos/rj45/env/bin/python -c "
   from sqlalchemy import create_engine, text
   from config import settings

   engine = create_engine(settings.database_url)
   with engine.connect() as conn:
       res = conn.execute(text('SELECT s.id, s.hostname, e.agent_version, s.last_seen FROM servers s LEFT JOIN server_extras e ON s.id=e.server_id ORDER BY s.id;')).fetchall()
       for row in res:
           print(row)
   "
   ```
4. **Penyampaian Hasil ke Operator:**
   Laporkan hasil secara lugas, terstruktur, ramah tampilan terminal, dan tunjukkan bukti verifikasi nyata tanpa retorika berlebihan.
