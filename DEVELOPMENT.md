# Dokumentasi Pengembangan & Standar Arsitektur Pantau Server

Dokumen ini merupakan panduan teknis resmi bagi developer dan system administrator (sysadmin) yang merangkum seluruh prinsip fundamental, standar arsitektur, filosofi keamanan, metodologi data retention, serta best practices dalam pengembangan ekosistem **Pantau Server** dan **Agent Pantau**.

---

# Bagian I: Prinsip Fundamental, Standar Desain & Best Practices

## 1. Arsitektur Komunikasi Multi-Server (Pull-Based Inverted Heartbeat)

### Filosofi Desain: Outbound Pull vs Inbound Push
Dalam merancang sistem monitoring dan kontrol terdistribusi multi-server, keputusan arsitektur paling mendasar adalah arah inisiasi koneksi. Sistem monitoring lawas atau berbasis script ad-hoc umumnya mengandalkan server monitoring pusat yang membuka sesi SSH masuk (*inbound SSH*) ke setiap server client. Pendekatan tersebut memiliki kelemahan kritis:
1. **Eksposur Port & Attack Surface Luas**: Mengharuskan port SSH atau port agent terbuka ke internet/jaringan publik pada setiap mesin client.
2. **Kerapuhan NAT & Topologi Jaringan**: Memerlukan VPN rumit, port forwarding, atau IP publik statis untuk server-server di balik NAT, firewall korporat, atau VPC cloud yang terisolasi.
3. **Penyimpanan Kredensial Terpusat Berisiko Tinggi**: Server monitoring harus menyimpan private key SSH atau password root untuk seluruh server target. Jika server monitoring terkompromi, seluruh server klien menjadi rentan terhadap akses tidak sah.

**Prinsip Desain Pantau Server:**
Pantau Server mengadopsi model **Pull-Based Inverted Heartbeat** yang sepenuhnya terbalik (*inversion of control*):
- **Agent Menginisiasi Koneksi Keluar (*Outbound Only*)**: Agent client secara periodik (setiap 5–10 detik) mengirim HTTP POST request (`/api/report`) ke server dashboard pusat.
- **Zero Inbound Ports**: Agent client tidak membuka listening port apapun ke jaringan publik. Server client dapat berada di balik NAT bertingkat atau firewall ketat selama memiliki akses keluar (*egress*) ke server dashboard.
- **Kredensial Terisolasi Per-Server**: Setiap agent hanya memegang token API spesifik (`api_key`) yang di-hash dengan SHA-256 di database server (`sha256:<hash>`). Key agent tidak memiliki hak akses pada server lain.

```mermaid
flowchart TD
    subgraph Klien["Node Agent Client (Linux Server)"]
        A["Daemon Agent (agent_pantau.py)"]
        W["Sudo Wrappers (/usr/local/sbin/pantau-*)"]
        OS["Sistem Operasi (/proc, systemd, ufw)"]
    end

    subgraph Server["Server Pusat Dashboard (Pantau Server)"]
        API["FastAPI REST & WebSocket Hub"]
        DB[("Database Relasional MariaDB")]
        UI["Web Dashboard UI"]
    end

    A -->|"1. Outbound Heartbeat HTTP POST (/api/report)"| API
    API -->|"2. Simpan Telemetri & Return Pending Command"| A
    API <-->|"Baca / Tulis Metrik & Antrean"| DB
    UI -->|"Trigger Admin Action (Pending)"| API
    A -->|"3. Eksekusi Perintah Terbatas (shell=False)"| W
    W -->|"4. Akses Hak Akses Minimal (Least Privilege)"| OS
    A -->|"5. Lapor Balik Hasil pada Heartbeat Berikutnya"| API
```

### Siklus Hidup Perintah Asinkron (Asynchronous Command Lifecycle)
Karena koneksi bersifat outbound-pull, eksekusi perintah (seperti restart service, kill process, modifikasi firewall, add user, push update OTA) ditangani melalui antrean perintah asinkron (*asynchronous command queue*):
1. **Penerbitan (*Issue*)**: Operator memicu aksi dari web dashboard. Server dashboard memvalidasi permission dan memasukkan perintah ke tabel [`commands`](file:///home/bos/rj45/server/models.py#L88-L111) dengan status `pending`.
2. **Pengambilan (*Polling/Heartbeat*)**: Saat agent melakukan heartbeat berikutnya, server menyertakan pending command dalam payload response JSON.
3. **Eksekusi Lokal**: Agent memproses command secara lokal, menjalankan binary terkait melalui sudo wrapper terisolasi, dan menangkap status serta output (*stdout/stderr*).
4. **Pelaporan Hasil (*Callback Report*)**: Pada heartbeat berikutnya, agent melaporkan balik hasil eksekusi (`success` atau `failed`) beserta output log ke server untuk di-update di database dan ditampilkan di web dashboard.

### Agent Mandiri Tanpa Dependensi Eksternal (Zero-Dependency Python Agent)
Agent client ([`agent/agent_pantau.py`](file:///home/bos/rj45/agent/agent_pantau.py)) dibangun dengan prinsip **Zero External Dependencies**:
- Hanya menggunakan Python standard library (`urllib.request`, `subprocess`, `json`, `os`, `sys`, `platform`, `hashlib`, `shutil`, `socket`).
- Tidak menggunakan third-party library seperti `psutil` yang membutuhkan compiler C (`gcc`, `python3-dev`) dan rentan gagal saat dipasang pada instalasi distro Linux minimalis.
- Metrik sistem dibaca langsung dari pseudo-filesystem Linux (`/proc/stat`, `/proc/meminfo`, `/proc/loadavg`, `/proc/net/dev`, `/proc/diskstats`, `/sys/class/net/`) dan utilitas core Linux (`df`, `systemctl`, `journalctl`, `ss`, `ufw`).
- Hal ini menjamin agent dapat di-deploy seketika di semua distro Linux modern (Ubuntu 18.04+, Debian 10+, CentOS 7+, RHEL, AlmaLinux, Rocky Linux) dalam hitungan detik.

---

## 2. Model Keamanan & Hak Akses Minimal (Principle of Least Privilege)

### Isolasi Akun Tanpa Hak Istimewa (Unprivileged Daemon)
- Agent Pantau tidak pernah dijalankan sebagai user `root`.
- Agent beroperasi di bawah system user terisolasi `pantau` (`User=pantau`, `Group=pantau`) yang dibuat otomatis oleh installer [`package/install.sh`](file:///home/bos/rj45/package/install.sh).
- File konfigurasi agent (`/etc/pantau/config.json`) diamankan dengan permission `0600` milik `pantau:pantau`.

### Pencegahan Shell Injection (`shell=False` & Argument Vectors)
- Standar mutlak kode agent melarang penggunaan `subprocess.run(..., shell=True)` atau `os.system(...)`.
- Semua eksekusi binary sistem diwajibkan menggunakan argument vector (`list` of strings):
  ```python
  # BENAR (Aman dari shell injection):
  subprocess.run(["/usr/local/sbin/pantau-user", "lock", username], shell=False, check=True)

  # DILARANG KERAS (Rentan Command Injection):
  # subprocess.run(f"/usr/local/sbin/pantau-user lock {username}", shell=True)
  ```
- Pendekatan ini mengeliminasi celah eksekusi perintah arbitrari (*arbitrary command execution*) melalui metakarakter shell (seperti `;`, `&&`, `|`, `` ` ``, `$()`, `\n`).

### Granularitas Sudo Wrapper Khusus (`/usr/local/sbin/pantau-*`)
Untuk menjalankan tindakan administratif sistem tanpa memberikan hak sudo root penuh (`ALL=(ALL) ALL`), Agent Pantau menggunakan script wrapper terisolasi di `/usr/local/sbin/`. Konfigurasi sudoers di [`/etc/sudoers.d/pantau-agent`](file:///home/bos/rj45/package/etc/sudoers.d/pantau-agent) hanya mengizinkan eksekusi tanpa password untuk file-file ini:
- [`pantau-service`](file:///home/bos/rj45/package/usr/local/sbin/pantau-restart): Mengontrol status service systemd (start, stop, restart, reload) dengan whitelist validasi unit.
- [`pantau-user`](file:///home/bos/rj45/package/usr/local/sbin/pantau-user): Manajemen user Linux (buat user, lock user via `usermod -L`, unlock user via `usermod -U`, delete user via `userdel`).
- [`pantau-cron`](file:///home/bos/rj45/package/usr/local/sbin/pantau-cron): Tambah, enable/disable, delete, dan eksekusi instan cron job.
- [`pantau-firewall`](file:///home/bos/rj45/package/usr/local/sbin/pantau-firewall): Manajemen firewall UFW (enable, disable, reload, block IP, unblock IP, rule audit).
- [`pantau-ssl`](file:///home/bos/rj45/package/usr/local/sbin/pantau-ssl): Pembacaan dan inspeksi sertifikat SSL/TLS lokal via OpenSSL CLI.
- [`pantau-apt`](file:///home/bos/rj45/package/usr/local/sbin/pantau-apt): Update cache repository (`apt-get update`) dan upgrade paket (`apt-get upgrade -y`).
- [`pantau-host`](file:///home/bos/rj45/package/usr/local/sbin/pantau-host): Reboot OS dan shutdown terjadwal dengan safety delay agar status report sempat terkirim sebelum mesin mati.
- [`pantau-file`](file:///home/bos/rj45/package/usr/local/sbin/pantau-file): Operasi file aman dengan batasan path directory.

### Guardrail Proteksi Proses Kritis Sistem
Sistem memiliki guardrail perlindungan ganda (di dashboard dan agent) yang menolak mutlak perintah kill atau modifikasi pada komponen kritis:
1. **PID 1 (`init` / `systemd`)**: Tidak dapat dihentikan atau dikirimi sinyal terminasi.
2. **Daemon SSH (`sshd`)**: Tidak dapat di-kill melalui task manager agar sysadmin tidak terkunci dari server.
3. **Daemon Agent Pantau (`agent_pantau`)**: Dilindungi dari kill paksa via web UI guna menjaga kontinuitas monitoring.
4. **Port Kunci (Port 22 SSH, 80/443 Web, 8400 Pantau)**: Sebelum firewall UFW diaktifkan, sistem secara otomatis memastikan rule allow untuk port-port ini sudah terpasang.

### Pengamanan Web File Manager
- **Guardrails System Path**: Akses langsung ke directory sensitif kernel dan hardware (`/proc`, `/sys`, `/dev`, `/boot`) diblokir ketat.
- **Auto Backup File Berstempel Waktu**: Setiap kali file teks diedit dan disimpan via web UI, file original otomatis dibackup ke `.bak.<timestamp>` sebelum file ditimpa.

### Model Kontrol Akses Berbasis Role 3-Tier (3-Tier RBAC Architecture)
Untuk mendukung tata kelola keamanan enterprise, Pantau Server menerapkan sistem otorisasi berbasis role 3-tier dengan prinsip segregation of duties:

```mermaid
flowchart TD
    subgraph MasterAdmin["1. Master Admin (Otoritas Tertinggi / Setara Root)"]
        MA["Akses Penuh Seluruh Fitur"]
        MA_Audit["Akses Eksklusif Audit Trail (/audit)"]
        MA_Users["Manajemen Operator & Delegasi Izin Sudo"]
    end

    subgraph Operator["2. Operator (User Operasional Harian)"]
        OP["Hak Akses Dibatasi Granular oleh Master Admin"]
        OP_Perms["Izin Terpilih: Terminal, Services, File Manager, dll."]
        OP_Viewer["Bisa Membuat/Kelola Viewer (Bila Diberi Izin)"]
    end

    subgraph Viewer["3. Viewer / Guest (Pengawas & Auditor)"]
        VW["Akses Baca Murni (Read-Only)"]
        VW_Block["Blokir Mutlak Seluruh Tombol Kontrol & Eksekusi"]
    end

    MasterAdmin -->|"Delegasikan Izin & Akun"| Operator
    MasterAdmin -->|"Membuat & Mengelola"| Viewer
    Operator -.->|"Dapat Membuat (Jika can_manage_viewers aktif)"| Viewer
```

1. **Master Administrator (`master_admin`)**:
   - **Kedudukan**: Akun dengan hak akses administratif penuh.
   - **Hak Khusus**:
     - Satu-satunya role yang memiliki visibilitas atas kartu counter dan data akun Master Admin di tabel user.
     - Akses penuh catatan audit trail ([`/audit`](file:///home/bos/rj45/server/templates/audit.html)).
     - Hak membuat, mengedit izin granular/sudo, dan me-lock akun Operator serta Viewer.
     - Kontrol tak terbatas atas seluruh armada server, terminal, file manager, dan eksekusi command.
   - **Proteksi Akun Administrator & Isolasi Informasi**: Akun Master Admin tidak dapat dihapus atau dinonaktifkan via antarmuka web. Keberadaan akun Master Admin disembunyikan dari antarmuka pengguna Operator dan Viewer.

2. **Operator (`operator`)**:
   - **Kedudukan**: Akun harian tim operasional/SRE. Akun dibuat dan dikonfigurasi langsung oleh Master Admin atau Operator dengan wewenang sudo.
   - **Konsep Otoritas Sudo Operator (*Sudo-like Authority*)**:
     Seperti prinsip user biasa di Linux yang tergabung dalam grup `sudo` (*wheel*), Master Admin dapat mendelegasikan wewenang penuh kepada Operator (termasuk akses audit trail dan user management) sehingga akun Master Admin tidak perlu digunakan setiap hari. Akun Operator dengan hak sudo penuh dapat mengelola operasional armada server dan user lain secara mandiri.
   - **Prinsip Zero-Knowledge Master Admin**:
     Operator sama sekali tidak mengetahui keberadaan user Master Admin:
     - Counter kartu statistik jumlah Master Admin disembunyikan dari Operator.
     - Baris akun Master Admin tidak muncul pada tabel user yang diakses Operator.
     - Jika Operator mencoba memanipulasi ID Master Admin secara sengaja via API/POST (`/delete`, `/toggle-active`, `/edit`), sistem merespons netral `"User tidak ditemukan"` untuk mencegah user enumeration.
     - Pada halaman Audit Trail, aktivitas Master Admin disamarkan sebagai `"Sistem"`.
   - **Matriks Izin Granular (*Granular Delegated Permissions*)**:
     Setiap Operator memiliki hak eksekusi yang diatur via permission matrix atau preset **⚡ Hak Sudo Penuh**:
     - `can_terminal`: Akses web terminal PTY interaktif xterm.js.
     - `can_file_manager`: Browse directory, edit file, dan manajemen file remote.
     - `can_manage_servers`: Add server, rename, edit threshold, atau delete server.
     - `can_services`: Start, stop, restart, dan reload service systemd.
     - `can_processes`: Kill dan stop process di task manager.
     - `can_firewall`: Manage port rule, block/unblock IP via UFW.
     - `can_users_sys`: Add user Linux, lock, unlock, dan delete user host.
     - `can_cron`: Add, toggle, delete, dan run now cron job.
     - `can_ssl`: Manage custom SSL path monitoring.
     - `can_server_control`: Reboot OS dan poweroff mesin host.
     - `can_apt`: Update repository cache dan upgrade paket APT.
     - `can_ota`: Trigger push update agent massal (OTA update).
     - `can_audit`: Akses membaca audit trail dan log aktivitas keamanan ([`/audit`](file:///home/bos/rj45/server/templates/audit.html)).
     - `can_manage_users`: Manage akun user (Operator & Viewer), reset password, ganti username, dan set permission.
     - `can_manage_viewers`: Izin terbatas untuk membuat, mengunci, atau menghapus akun Viewer (tamu monitoring).
   - **Batasan Mutlak**: Operator **tidak dapat** menghapus Master Admin, tidak dapat me-lock Master Admin, tidak dapat mengganti username/password Master Admin, serta tidak dapat mempromosikan user manapun menjadi `master_admin`.

3. **Viewer (`viewer`)**:
   - **Kedudukan**: Akun pengawas pasif untuk stakeholder, manajemen, external auditor, atau tim monitoring murni.
   - **Isolasi Mutlak (*Zero Administrative Authority & Information Isolation*)**:
     - User Viewer sama sekali tidak mengetahui keberadaan user Operator maupun Master Admin.
     - Tidak memiliki menu **Profil & Keamanan** di web UI, dan seluruh akses ke `/profile` diblokir permanen (redirect ke `/`).
     - Viewer tidak dapat mengubah password, profil, atau 2FA sendiri. Seluruh kredensial akun Viewer dikelola dari luar oleh Master Admin atau Operator.
     - Seluruh tombol kontrol, aksi eksekusi, terminal, file manager, dan form modifikasi disembunyikan dan di-block di backend. Viewer murni hanya memiliki hak read-only metrik.

---

### Unifikasi User Management ke Menu Profil & Keamanan
1. **Navigasi Terpadu**:
   - Menu terpisah "User" di sidebar utama dihapus agar navigasi tetap ringkas dan terfokus.
   - Manajemen user dan delegasi wewenang disatukan ke dalam halaman **Profil & Keamanan** ([`/profile`](file:///home/bos/rj45/server/templates/profile.html)):
     - **Tab 1: Profil & Keamanan Saya**: Info identitas, ganti password pribadi, dan manajemen 2FA (TOTP) serta backup recovery codes.
     - **Tab 2: Manajemen User & Hak Akses**: Muncul otomatis untuk Master Admin atau Operator yang memiliki wewenang user management (`can_manage_users` / `can_manage_viewers`).
2. **Antarmuka Tabel User Interaktif**:
   - **Tombol "👁️ Lihat"**: Modal inspeksi profil akun dan visualisasi matriks izin (*✔ Diizinkan* vs *✖ Ditolak*).
   - **Tombol "✏️ Edit"**: Modal untuk edit username, reset password sesuai standar NIST, ganti role, serta checklist permission dengan preset instan **⚡ Hak Sudo Penuh**.
   - **Tombol "🔒 Kunci / 🔓 Buka"**: Lock user instan dengan revoke session seketika.
   - **Tombol "🗑️ Hapus"**: Delete akun permanen dengan proteksi kekebalan Master Admin.

---

### Penguatan Keamanan Akun & Autentikasi (Authentication Hardening)

1. **Standar Kompleksitas Password (NIST SP 800-63B)**:
   - Panjang minimum **12 karakter**.
   - Wajib kombinasi huruf besar (A-Z), huruf kecil (a-z), angka (0-9), dan simbol (!@#$%^&*...).
   - Validasi blacklist dictionary terhadap password pasaran dan nama username.
   - Visual password strength meter realtime di form web.

2. **Two-Factor Authentication (2FA / TOTP RFC 6238)**:
   - Support aplikasi authenticator standar (Google Authenticator, Aegis, Authy, 1Password, Bitwarden).
   - Secret key Base32 160-bit cryptographically secure.
   - QR code generator otomatis dengan URI `otpauth://totp/...`.
   - Time-step 30 detik dengan drift window toleransi ±1 step.
   - **10 Backup Recovery Codes (Single-Use)**:
     - Diberikan saat aktivasi 2FA untuk situasi darurat ketika device authenticator hilang.
     - Disimpan dalam bentuk hash SHA-256 / bcrypt di database.
     - Sekali pakai (*single-use*) dan otomatis hangus setelah dipakai login.
   - **Regenerate Backup Codes**: Fitur pembuatan ulang 10 recovery codes baru via web modal dengan konfirmasi password tanpa harus reset 2FA.

3. **Alur Login Dua Tahap Terisolasi (Two-Stage Pre-Auth Flow)**:
   - Setelah username dan password valid, server **tidak langsung memberikan session cookie aplikasi utama**.
   - Server menerbitkan temporary HMAC signed token (`preauth_session`) dengan masa berlaku 5 menit.
   - User diredirect ke [`/login/2fa`](file:///home/bos/rj45/server/templates/login_2fa.html). Session dashboard penuh baru diterbitkan setelah token TOTP atau recovery code valid dimasukkan.

4. **Revoke Session Seketika & Proteksi Akun**:
   - **Revoke Session saat Ganti Password**: Setiap kali user mengganti password di [`/profile`](file:///home/bos/rj45/server/templates/profile.html), seluruh active session di device lain otomatis di-revoke dari database untuk mencegah pembajakan session lama.
   - **Lock User Instan**: Ketika admin me-lock akun user melalui [`/profile`](file:///home/bos/rj45/server/templates/profile.html), seluruh session aktif user tersebut langsung dimatikan pada detik yang sama.

5. **CLI Emergency Seed & Recovery Tool**:
   - Script administrasi lokal ([`server/seed_admin.py`](file:///home/bos/rj45/server/seed_admin.py)) untuk eksekusi via terminal server dashboard: create master admin, ganti username (`--rename-from`), hingga emergency reset 2FA (`--reset-2fa`).

---

## 3. Remote OTA Agent Update (Enterprise Over-The-Air Update)

Update armada agent pada puluhan server tidak boleh bergantung pada SSH manual per-server:

### Protokol Transmisi Kriptografis
1. **Penerbitan Hash Resmi**: Dashboard mengetahui file binary agent resmi dan hash SHA-256 nya.
2. **Instruksi Terautentikasi**: Ketika trigger OTA diklik (`Push Update (OTA)`), dashboard mengirim payload terstruktur ke command queue:
   ```json
   {
     "action": "update_agent",
     "url": "https://dashboard.domain.com/api/agent/download",
     "sha256": "386f3e7b2354c7d0d0840b3ff646e29783f609b185e493e9bbf04ae78f6920f0",
     "version": "4.2.4"
   }
   ```

### Verifikasi Integritas & Safety Check di Sisi Client
1. **Download Sementara**: File baru di-download ke temporary path (`/opt/pantau/agent/agent_pantau.py.tmp`).
2. **Validasi Hash SHA-256**: Agent mencocokkan checksum SHA-256 file temporary dengan hash dari dashboard. Jika tidak cocok, file langsung dihapus dan security alert dilaporkan ke audit trail.
3. **Validasi Sintaks Python (`py_compile`)**: Agent menguji file via `py_compile.compile()` sebelum instalasi agar tidak terjadi bricked agent jika script error syntax.
4. **Penggantian File Atomik (`os.replace`) & Permission**: File diganti secara atomik (`os.replace`) ke `/opt/pantau/agent/agent_pantau.py` dengan permission `0755` milik `pantau:pantau`.
5. **Watchdog Restart & Auto Report**: Agent me-restart servicenya via systemd watchdog dan melapor dengan `agent_version` baru pada heartbeat berikutnya.

---

## 4. Strategi Retensi Data & Dynamic Query Downsampling

Untuk mencegah database bloat pada pengumpulan metrik periodik:

### Arsitektur Data Retention 4-Tier
| Tier | Tabel Database | Granularitas Data | Retensi | Frekuensi Pruning | Peruntukan |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Tier 1 (Raw Snapshots)** | [`sys_snapshots`](file:///home/bos/rj45/server/models.py#L113-L138) | Penuh (5–10 detik) | **24 Jam** | Tiap laporan agent (`now - 24h`) | Realtime metric, grafik 1h/6h/24h, spike investigation. |
| **Tier 2 (Hourly Rollups)** | [`sys_snapshots_hourly`](file:///home/bos/rj45/server/models.py#L140-L170) | 1 sampel per jam | **90 Hari** | Dihitung per jam; prune `> 90d` | Capacity planning, grafik 7d & 30d hemat storage. |
| **Tier 3 (Service Metrics)** | [`metrics`](file:///home/bos/rj45/server/models.py#L70-L86) | Status per-laporan | **7 Hari** | Pruning tiap 24 jam (`now - 7d`) | Uptime tracking, status service, latency history. |
| **Tier 4A (Audit Logs)** | [`audit_logs`](file:///home/bos/rj45/server/models.py#L262-L281) | Audit trail user | **365 Hari (1 Tahun)** | Hourly background prune | Kepatuhan audit regulasi dan investigasi forensik. |
| **Tier 4B (Command History)**| [`commands`](file:///home/bos/rj45/server/models.py#L88-L111) | History command | **180 Hari** | Hourly background prune | History maintenance remote per server. |
| **Tier 4C (Resolved Incidents)** | [`server_problems`](file:///home/bos/rj45/server/models.py#L196-L227) | Tiket resolved | **90 Hari** | Hourly background prune | MTTR (*Mean Time To Resolution*) analytics. |
| **Tier 4D (Sessions & Rate Limit)**| [`sessions`](file:///home/bos/rj45/server/models.py#L283-L299), [`login_attempts`](file:///home/bos/rj45/server/models.py#L301-L309) | Auth session | **12 Jam / 1 Hari** | Hourly background prune | Keamanan auth dan pembersihan token kedaluwarsa. |

### Dynamic Query Downsampling
Grafik riwayat kinerja 24h, 7d, atau 30d menggunakan downsampling SQL adaptif di database engine sehingga browser selalu menerima payload ringan (~120 data points, < 50 KB) tanpa browser lag.

---

## 5. Manajemen Siklus Hidup Insiden, Klasifikasi Aset 3-Tier & Anti-Flapping

- **Arsitektur Klasifikasi Level Operasional (3-Tier)**:
  - **Tier 1 (Layanan Utama / Kritis)**: Server dengan prioritas operasional tertinggi. Insiden server offline atau core service down memulai tahap **GAWAT (`average`)** selama 1 menit sebagai waktu mitigasi awal operator, kemudian bereskalasi ke **KRITIS (`danger`)** jika belum pulih. Tahap Kritis ini merupakan satu-satunya level yang mengaktifkan Banner Merah `#alertBanner` dan alarm audio. Kerusakan sistem fatal seperti Disk Read-Only atau Disk 100% langsung berstatus KRITIS.
  - **Tier 2 (Layanan Pendukung)**: Server operasional pendukung. Insiden memulai tahap **PERINGATAN (`warning`)** selama 1 menit sebelum bereskalasi ke **GAWAT (`average`)**. Tingkat keparahan maksimal dibatasi pada Gawat (tidak memicu banner merah atau alarm audio).
  - **Tier 3 (Layanan Non-Kritis / Pengujian)**: Server staging atau uji coba. Insiden dibatasi pada tingkat **PERINGATAN (`warning`)**.
- **Tindakan Pemeliharaan oleh Operator**:
  - Pemadaman server (*Power Off Host*) atau penghentian layanan (*Stop Service*) yang dilakukan secara sengaja oleh operator melalui dashboard diklasifikasikan sebagai **PERINGATAN (`warning`)**, dengan `is_ignored = 0` (tetap aktif tercatat pada kartu insiden terkini bersama nama operator yang bertindak) tanpa memicu banner merah atau alarm audio.
- **Toleransi Anti-Flapping**: Layanan tidak langsung memicu alarm pada kegagalan transien sesaat. Sistem menerapkan jendela evaluasi (30–45 detik) sebelum status dikonfirmasi.
- **Resolusi Otomatis saat Penghapusan Layanan**: Menghapus layanan dari konfigurasi monitoring secara otomatis menutup tiket insiden terkait dengan catatan `Dihapus dari konfigurasi`.
- **Mode Pemeliharaan (Maintenance Mode) & Silence**: Mendukung mode pemeliharaan tingkat server untuk menonaktifkan alert sementara saat maintenance OS, serta opsi heningkan (*silence/mute*) alert layanan tertentu (2 jam, 24 jam, 7 hari, 30 hari, atau permanen).

---

## 6. Telemetri Real-Time & Web Terminal

- **PTY Linux Terminal**: Direct `/bin/bash` Pseudo-Terminal via Python standard `pty` dan streaming WebSocket dispatcher. Full ANSI color, VT100 control sequences, auto-completion, dan dynamic window resize (`SIGWINCH`).
- **Dedicated WebSocket Channel**: Traffic terminal dan journal stream dipisahkan dari HTTP REST reporting agar tidak mengganggu metrik sistem.

---

## 7. Audit Trail & Investigasi Forensik

- **End-to-End Traceability**: Setiap tindakan administratif mencatat Actor (username), Timestamp UTC, Target (server/service/user/file/port), Action (`restart_service`, `kill_process`, `block_ip`, dll.), dan Outcome (`success`/`failed` + output log).
- **Sensitive Parameter Redaction**: Password dan secret key otomatis disensor sebelum disimpan ke tabel [`audit_logs`](file:///home/bos/rj45/server/models.py#L262-L281).
- **User Activity Auditing**: Tab Manajemen User menyediakan tombol `📋 Audit` cepat dan modal inspect untuk mengisolasi riwayat aksi per operator di [`/users/{id}/activity`](file:///home/bos/rj45/server/templates/user_activity.html).

---

## 8. UX Sysadmin & Standar Bahasa Teknis

- **Bahasa Sysadmin Natural**: Menggunakan terminologi standar dunia IT dan sysadmin: *server*, *user*, *service*, *file*, *folder*, *username*, *password*, *root*, *sudo*, *terminal*, *CPU*, *RAM*, *I/O*, *UFW*, *SSL*, *cron job*, *reboot*, *kill process*.
- **Hierarki Navigasi Alur Sysadmin**:
  `Kinerja Ringkas → Riwayat & Masalah → Service & Process → Konfigurasi (User, Port, Firewall, SSL, Cron) → Logging & Diagnostik`.
- **Status Visual Tegas**:
  - Hijau (`success`): Service/host sehat dan normal.
  - Kuning (`warning`): Warning threshold atau SSL mendekati expired.
  - Merah (`danger`): Critical incident, service down, brute-force alert.
  - Biru Neon (`#38bdf8`): Aksen navigasi dan elemen aktif.

---

# Bagian II: Catatan Riwayat Perubahan Versi (Changelog)

## Versi 4.8.42

- **Tipe Rilis:** Pengawas Pola Log Kritis Kernel & Sistem, Deteksi OOM Killer, Galat Storage I/O, dan Korelasi Akar Masalah Layanan (*Kernel Critical Log Pattern Monitor, OOM Killer Detection, Storage Disk I/O Errors, and Root-Cause Correlation*)
- **Fokus Utama:** Menghadirkan subsistem pengawasan mendalam terhadap anomali fatal level kernel Linux pada mesin klien (zero external dependency) yang mencakup pembunuhan proses akibat kehabisan memori (*OOM Killer*), kegagalan baca/tulis sektor media penyimpanan (*Storage Disk I/O Error*), crash memori aplikasi (*Segmentation Fault*), dan *Kernel Panic*, serta menghubungkan secara otomatis status kegagalan layanan dengan pemicu akar masalah kernel:
  1. **Mesin Pengumpul Log Kritis Kernel Zero-Dependency (`agent_pantau.py`):**
     - Membaca pembacaan mutlak insiden OOM dari penghitung kernel Linux `/proc/vmstat` (`oom_kill`).
     - Memindai riwayat *kernel ring buffer* pada sesi *boot* berjalan via `journalctl -k -b 0 -n 80 --no-pager -o json` dengan ekspresi reguler (Regex) presisi tinggi untuk menangkap korban OOM killer (`_RE_OOM_KERNEL` dan `_RE_OOM_SYSTEMD`), galat fisik I/O penyimpanan (`blk_update_request: I/O error`, `Buffer I/O error`, `EXT4-fs error`, remount *read-only*), segmentasi memori ilegal (`segfault`), dan *kernel panic*.
     - Menerapkan *monotonic timestamp cache* 25 detik guna mencegah beban berlebih (*overhead* CPU mendekati 0%) serta memanfaatkan hak akses grup `adm` sistem tanpa memerlukan eskalasi root/sudo berlebih.
  2. **Ekstensi Skema Relasional & Model Data (`models.py` & `main.py`):**
     - Menambahkan kolom `kernel_events MEDIUMTEXT NULL` pada tabel basis data `server_extras` di MariaDB dengan inspeksi otomatis skema runtime (`_ensure_server_extras_columns`).
     - Melakukan sanitasi, validasi, dan pembatasan muatan telemetri kernel pada endpoint penerimaan laporan agen `/api/report`.
  3. **Mesin Evaluasi Insiden & Korelasi Akar Masalah Cerdas (`server/main.py`):**
     - Mengidentifikasi dan menerbitkan kejadian insiden fatal sistem (`oom_kill:{proc}`, `disk_io_error:{dev}`, `kernel_panic`, `segfault:{proc}`) dengan keparahan berjenjang berdasarkan Tier Server (Tier 1: Kritis/Danger, Tier 2: Gawat/Average, Tier 3: Peringatan/Warning).
     - Menetapkan jendela tenang (*quiet window*) terukur: 900 detik untuk OOM, 1200 detik untuk Storage I/O Error, 1800 detik untuk Kernel Panic, dan 600 detik untuk Segfault.
     - **Korelasi Lintas-Entitas (Root Cause Analysis):** Mengorelasikan status layanan *down* dengan insiden OOM killer pada nama layanan atau proses biner terkait (`oom_event_map`), secara otomatis mentransformasikan pesan insiden menjadi:
       `Layanan {name} Down — Dihentikan paksa oleh Kernel (OOM Killer)`,
       lengkap dengan rekomendasi investigasi RAM/Swap fisik pada kartu panduan insiden.
     - Menetapkan label komponen masalah terstruktur (`Kernel / OOM ({proc})`, `Penyimpanan (I/O {dev})`, `Kernel / Sistem`, `Aplikasi Crash ({proc})`) serta tautan tombol aksi terarah ke unit log terkait.
  4. **Peningkatan Kepadatan Informasi NOC Antarmuka Pengguna (`services.html`):**
     - Menambahkan baris metrik operasional `OOM Kills` pada kartu *Kapasitas Memori* di tab Performa (`#spec-oom-count`), menampilkan lencana hijau `0 (Nihil)` pada kondisi normal dan lencana merah `X Kejadian` bila terdeteksi pembunuhan proses oleh kernel.
     - Menyematkan lencana sorotan keparahan pada tabel Log Sistem Journal (`#sublog-panel-sys`): lencana merah `OOM`, `DISK I/O`, `PANIC`, serta lencana oranye `SEGFAULT`.
     - Menampilkan lencana status `OOM KILLED` merah tegas pada tabel layanan terpantau dan daftar unit Systemd saat layanan menjadi korban kehabisan memori.
  5. **Otomasi Pembaruan SemVer v4.8.42:**
     - Menaikkan versi sistem menjadi `v4.8.42` secara sinkron dan identik di 7 berkas proyek sesuai standar operasional baku Pantau Server.

## Versi 4.8.41

- **Tipe Rilis:** Standarisasi Tata Letak, Desain Visual, dan Kebahasaan Baku Tabel Insiden Terbuka (*Layout Standardization, Visual Polish, and Language Consistency of Open Incidents Table*)
- **Fokus Utama:** Menyempurnakan tata letak dan visual tabel kartu *Insiden Terbuka* serta bilah filter triase pada halaman Insiden (`problems.html`), mengeliminasi benturan lencana status terhadap kolom deskripsi kejadian, menghadirkan indikator status host, menstandardisasi durasi dengan badge pill monospasi NOC, serta membersihkan inkonsistensi bahasa:
  1. **Arsitektur Tata Letak Tetap & Eliminasi Benturan Lencana (`problems.html`):**
     - Mengimplementasikan `table-layout: fixed !important` dengan pendefinisian `<colgroup>` terukur (`115px`, `175px`, `165px`, `auto`, `120px`, `260px`, `95px`) untuk mencegah pergeseran kolom saat pembaruan data dinamis.
     - Memperluas lebar kolom keparahan (`#probtable th.col-sev, #probtable td.col-sev`) menjadi `165px` (min-width `155px`) dengan perataan tengah dan flex wrap yang rapi, memberikan ruang leluasa bagi lencana subordinat (`DIABAIKAN` / `✓ DITANGANI`) sehingga tidak lagi bertumpuk atau meluap ke kolom `KEJADIAN`.
  2. **Indikator Titik Status Host & Pelengkap Telemetri Armada:**
     - Menghadirkan indikator titik status host (`●` hijau jika server aktif, merah jika server offline, atau ikon bola dunia SVG biru jika endpoint probing) berdampingan dengan nama host dan lencana grup (`CLONE`) pada kolom `SERVER` baik dalam SSR Jinja maupun poller JavaScript dinamis.
     - Menyediakan atribut `is_offline` dan `ip_address` secara konsisten pada payload server data `_agg_row` di `server/main.py`.
  3. **Standardisasi Tipografi Monospasi & Badge Pill Durasi NOC:**
     - Memformat durasi kejadian insiden ke dalam chip badge pill monospasi NOC (`background: rgba(148, 163, 184, 0.08); border: 1px solid rgba(148, 163, 184, 0.18)`), serta mengamankan fungsi `tickAllDurations()` pada `server/templates/base.html` agar tidak menghapus elemen `<span>` badge pill saat detak pewaktu berjalan.
  4. **Pembersihan Inkonsistensi Bahasa Asing ke Bahasa Indonesia Baku:**
     - Menstandardisasi istilah bahasa Inggris pada bilah filter atas, filter pill triase, opsi dropdown keparahan, serta riwayat tabel insiden (`Critical` → `Kritis`, `Warning` → `Peringatan`) selaras dengan pedoman baku proyek NOC.
  5. **Elevasi Header Kartu & Penyelarasan Status Real-Time:**
     - Menambahkan kontainer ikon SVG status responsif (`#prob-active-icon`), subjudul informatif, serta lencana status dinamis (`#prob-active-badge` dan `#prob-ignored-badge`) pada header kartu *Insiden Terbuka*, disinkronkan langsung via `poll()` JavaScript.
  6. **Penyempurnaan Kolom Panduan Solusi & Tindakan:**
     - Memastikan teks panduan teknis tampil terstruktur dan rapi dengan tipografi monospasi pada perintah command line (`sudo systemctl ...`).
     - Menata tombol tindakan operasional (`.action-btn-mini`) secara proporsional berukuran 24x24 piksel dengan pemusatan horizontal yang presisi.
  7. **Otomasi Pembaruan SemVer v4.8.41:**
     - Menaikkan versi sistem menjadi `v4.8.41` secara sinkron dan identik di 7 berkas proyek sesuai standar operasional baku Pantau Server.

## Versi 4.8.40

- **Tipe Rilis:** Penyempurnaan Tata Letak, Desain Visual, dan Tipografi Tabel Insiden Terkini Dasbor (*Layout, Visual Design, and Typography Polish of Dashboard Recent Incidents Table*)
- **Fokus Utama:** Menyempurnakan tata letak dan ergonomi visual tabel pada kartu *Insiden Terkini* di halaman Dashboard Utama (`dashboard.html`), mengeliminasi benturan lencana status terhadap kolom deskripsi masalah, menambahkan indikator status host, memformat durasi menjadi badge pill NOC, serta menyelaraskan status kartu insiden secara real-time:
  1. **Arsitektur Tata Letak Tetap & Isolasi Namespace Kolom (`dashboard.html`):**
     - Mengimplementasikan `table-layout: fixed` dengan pendefinisian `<colgroup>` khusus (`115px`, `180px`, `165px`, `auto`, `120px`, `36px`) guna mengeliminasi pergeseran tata letak dan memastikan lebar kolom presisi secara konsisten.
     - Mengisolasi tata letak kolom tabel insiden dasbor dengan namespace kelas khusus (`.dash-col-time`, `.dash-col-server`, `.dash-col-sev`, `.dash-col-desc`, `.dash-col-durasi`, `.dash-col-action`).
     - Menyelesaikan kendala tumpang-tindih teks antara lencana subordinat (`DIABAIKAN` / `✓ DITANGANI`) dan teks deskripsi masalah yang sebelumnya dipicu oleh pembatasan `max-width: 100px !important` dari kelas global `.col-sev` di `base.html`.
  2. **Indikator Titik Status Host & Lencana Grup Sistem:**
     - Menghadirkan indikator titik status host (`●` hijau jika server aktif, merah jika server offline, atau ikon bola dunia SVG biru jika endpoint probing) berdampingan dengan nama host dan lencana grup (`CLONE`) pada kolom `SERVER`.
  3. **Standardisasi Tipografi Monospasi & Badge Pill Durasi NOC:**
     - Mengonversi format durasi insiden ke dalam chip badge pill monospasi NOC yang kontras, bersih, dan berorientasi operasional (`background: rgba(148, 163, 184, 0.08); border: 1px solid rgba(148, 163, 184, 0.18)`), selaras sempurna antara rendering SSR Jinja dan pembaruan berkala live polling JavaScript.
  4. **Efek Interaktif Baris & Indikator Aksi Chevron:**
     - Menambahkan efek hover baris halus (`background: rgba(255, 255, 255, 0.035)`) dan indikator panah interaktif (`.dash-row-arrow` / `→`) yang bertransisi dinamis untuk memperjelas bahwa seluruh baris dapat diklik untuk membuka rincian server atau endpoint probing terkait.
  5. **Sinkronisasi Dinamis Status Ikon & Header Kartu Insiden Terkini:**
     - Menyelaraskan logika perhitungan status kartu insiden dengan seluruh insiden terbuka (`all_open_problems` / `allProblems`), sehingga ikon header secara akurat menampilkan segitiga peringatan kuning saat ada insiden terbuka (termasuk tindakan operator) dan lencana jumlah insiden aktif (`X INSIDEN`).
     - Menautkan tombol pintasan "Riwayat Lengkap →" langsung ke halaman `/problems`.
  6. **Pembersihan Duplikasi Durasi Pesan Stale Backend (`server/main.py`):**
     - Menghapus penyertaan teks durasi redundan `(> {dur_txt})` pada string status stale pemadaman (`poweroff_host`) dan reboot (`reboot_host`), sehingga pesan terbaca lugas (`Host dimatikan oleh operator (OPERATOR)` dan `Server sedang di-reboot oleh operator (OPERATOR)`), menghindari pengulangan informasi durasi yang telah tersaji di kolom `DURASI`.
     - Melengkapi payload kamus insiden SSR dengan atribut status `is_offline` dan `ip_address`.
  7. **Otomasi Pembaruan SemVer v4.8.40:**
     - Menaikkan versi sistem menjadi `v4.8.40` secara sinkron dan identik di 7 berkas proyek sesuai standar operasional baku.

## Versi 4.8.39

- **Tipe Rilis:** Standarisasi Label Peringatan Tindakan Operator, Lencana Status Subordinat, dan Integrasi Status Reboot (*Standardization of Operator Action Warning Labels, Subordinate Badges, and Host Reboot Integration*)
- **Fokus Utama:** Menyempurnakan visibilitas tindakan sadar operator pada kartu Insiden Terkini halaman utama, memastikan label keparahan primer tidak terhapus saat diabaikan atau ditangani, menyelaraskan deskripsi aksi sesuai tindakan aktual, serta mengeliminasi teks diagnostik yang membingungkan:
  1. **Pertahanan Label Keparahan Primer (`PERINGATAN`) & Lencana Subordinat (`dashboard.html`, `problems.html`, `services.html`):**
     - Memperbaiki logika rendering badge keparahan (baik SSR Jinja maupun poller dynamic JavaScript) agar lencana keparahan primer (`KRITIS`, `GAWAT`, `PERINGATAN`, `INFO`) **selalu tampil di posisi teratas** dan tidak pernah digantikan atau dihilangkan saat insiden diabaikan (`is_ignored = 1`) atau ditangani (`acknowledged_by`).
     - Menampilkan lencana status subordinat **`DIABAIKAN`** dan/atau **`✓ DITANGANI`** secara proporsional dan berdampingan di bawah label keparahan primer tanpa merusak kepadatan vertikal sel tabel NOC (~30–34px).
  2. **Pelaporan Terpusat Tindakan Operator pada Kartu Insiden Terkini (`server/main.py` & `dashboard.html`):**
     - Memastikan seluruh anomali atau kondisi terbuka yang dipicu oleh tindakan operator pada server klien (penghentian layanan, restart layanan, reboot host, power off host) tetap tampil pada tabel kartu *Insiden Terkini* di halaman Dashboard, bahkan jika status pengabaian (*ignored*) aktif, dengan atribut `is_operator_action`.
     - Insiden non-operator yang diabaikan tetap disembunyikan dari layar utama demi menjaga kebersihan monitor NOC.
  3. **Integrasi Status Host Reboot (`_problem_instances` & `sync_server_problems`):**
     - Memperluas deteksi ketidakaktifan agen (*agent_stale*) agar mengenali perintah `reboot_host` dari operator selain `poweroff_host`.
     - Mengklasifikasikan mesin yang sedang dalam siklus mulai ulang resmi sebagai tingkat keparahan **Peringatan (*Warning*)** dengan pesan deskriptif: `Server sedang di-reboot oleh operator ({OPERATOR}) (> {durasi})` dan rekomendasi teknis yang tepat tanpa memicu sirine darurat atau banner merah.
  4. **Penyelarasan Deskripsi Aksi Spesifik:**
     - Menyesuaikan keterangan insiden secara presisi berdasarkan tindakan aktual operator: penghentian layanan (`dimatikan oleh operator`), restart layanan (`di-restart oleh operator`), pemadaman host (`dimatikan oleh operator`), dan reboot host (`sedang di-reboot oleh operator`).
  5. **Pembersihan Teks Diagnostik Clutter (`[INFO DEPENDENSI]`):**
     - Menghapus sepenuhnya string `[INFO DEPENDENSI]` dan saran dependensi silang yang tidak diperlukan dari modul diagnosa dan rekomendasi teknis agar antarmuka tetap bersih, fokus, dan mudah dipahami operator.

## Versi 4.8.38

- **Tipe Rilis:** Sinkronisasi Penghentian Unit Systemd oleh Operator & Kesadaran Dependensi Layanan (*Systemd Operator Action Synchronization & Cross-Service Dependency Awareness*)
- **Fokus Utama:** Mengatasi anomali alarm kritis ketika operator secara sadar menghentikan unit systemd, menyinkronkan status pemeliharaan operator di seluruh model entitas, dan memberikan konteks dependensi cerdas:
  1. **Sinkronisasi Tindakan Penghentian Systemd (`server/main.py`):**
     - Memperluas handler API systemd `@app.post("/api/servers/{sid}/systemd/{action}")` agar saat operator menghentikan (`stop`) suatu unit, sistem secara otomatis menormalisasi nama unit (`.service`), mencocokkannya ke tabel `Service`, menetapkan alasan pengabaian sadar (`ignored_reason = "LAYANAN DIMATIKAN OLEH OPERATOR ({USER})"`), menyisipkan metrik `down` dengan pesan kesehatan informatif, serta mendaftarkan atau memperbarui rekaman `ServerProblem` berstatus **Peringatan (*Warning*)**.
     - Mengaitkan foreign key `service_id` pada perintah tabel `Command` secara langsung ke entitas `Service` terkait.
     - Memulihkan status pemeliharaan dan menutup insiden terbuka secara bersih dengan catatan `operator_start` saat operator menjalankan perintah `start` atau `restart`.
  2. **Deteksi Cerdas Operator Intent & Pelindung Alarm Palsu (`_problem_instances` & `sync_server_problems`):**
     - Mengintegrasikan pemindaian ganda dari tabel `Service` dan riwayat perintah terkini tabel `Command` (`action in ("stop", "start", "restart")`) sebelum menghasilkan daftar masalah terbuka.
     - Menyaring agar layanan yang saat ini aktif (*up*) tidak salah diidentifikasi sebagai berhenti.
     - Mengunci tingkat keparahan tindakan terencana operator pada level **Peringatan (*Warning*)**, menekan eskalasi otomatis ke tingkat Gawat (*Average*) maupun Kritis (*Danger*), serta mencegah pemicuan sirine darurat dan banner merah (`banner-danger`).
  3. **Kesadaran Ketergantungan Lintas Layanan (*Cross-Service Dependency Awareness*):**
     - Ketika layanan inti pada server mengalami gangguan (*down*) sementara ada layanan lain di server yang sama yang sedang dihentikan sengaja oleh operator, sistem secara otomatis menambahkan konteks diagnosa `[INFO DEPENDENSI]` pada panduan solusi (`svc_tip`) dan muatan JSON rincian konteks teknis (`context.operator_stopped_dependencies`).
     - Memandu operator bahwa kegagalan layanan terkait kemungkinan besar dipicu oleh penghentian layanan prasyarat tersebut.
  4. **Visibilitas Status Operator pada Antarmuka (`server/templates/services.html`):**
     - Menyematkan lencana status khusus berlatar belakang amber **`DIHENTIKAN OPERATOR`** pada tabel Unit Layanan Systemd dan tabel Layanan terpantau saat layanan nonaktif akibat tindakan operator.
     - Memperbarui peta reaktif JavaScript `_opStoppedSvcMap` seketika saat tombol Stop/Start/Restart systemd dieksekusi tanpa memerlukan reload halaman.

## Versi 4.8.37

- **Tipe Rilis:** Standarisasi Arsitektur RESTful Kanonikal Rincian Server & Sinkronisasi URL Tab Instan (*Canonical RESTful Server Details Architecture & Seamless Tab URL Deep-Linking*)
- **Fokus Utama:** Menyempurnakan hierarki semantik URL, mengeliminasi redirect hop yang tidak perlu, dan menyelaraskan seluruh tautan entitas navigasi ke rute kanonikal bersih:
  1. **Rute Kanonikal Primer Langsung (`server/main.py`):**
     - Menetapkan rute kanonikal bersih `@app.get("/servers/{sid}", response_class=HTMLResponse)` sebagai handler utama halaman rincian server (`services_page`), mengembalikan kode status **HTTP 200 OK** secara langsung tanpa redirect tambahan.
     - Mengonfigurasi `@app.get("/servers/{sid}/services")` sebagai alias semantik kompatibel ke belakang; mengarahkan secara mulus ke tab Layanan (`/servers/{sid}?tab=layanan`) jika diakses tanpa query parameter atau mempertahankan parameter query bila disertakan.
     - Memperbarui seluruh pengalihan pasca-aksi (tambah/hapus layanan, firewall, pengguna, cron, port, SSL, kontrol host) agar mengarah langsung ke `/servers/{sid}` dengan parameter tab atau aksi terkait.
  2. **Sinkronisasi Bilah Alamat Peramban Real-Time (`server/templates/services.html`):**
     - Mengintegrasikan pemanggilan `window.history.replaceState` ke dalam fungsi `showTab()` sehingga saat operator berpindah antar-tab (Users, Services, Firewall, Tasks, Ports, Cron, Logs), parameter `?tab=...` langsung diperbarui di bilah URL tanpa memicu reload halaman.
     - Menghapus parameter `?tab` secara otomatis saat kembali ke tab Performa sehingga URL kembali ke bentuk bersih `/servers/{sid}`.
  3. **Penyelarasan Tautan Lintas Modul Antarmuka:**
     - Menstandarisasikan seluruh tautan rincian server pada modul Dashboard (`dashboard.html`), Daftar Server (`servers.html`), Riwayat Insiden (`problems.html`), Pengujian Jaringan (`probing.html`), Manajer Berkas (`file_manager.html`), dan Aktivitas Pengguna (`user_activity.html`) menuju URL kanonikal bersih `/servers/{sid}`.

## Versi 4.8.36

- **Tipe Rilis:** Penyediaan Rute Pintasan Server & Perbaikan Tautan Notifikasi (*Server Shortcut Route & Alert Notification Links Routing Resilience*)
- **Fokus Utama:** Mengeliminasi galat 404 Not Found ketika pengguna mengakses URL langsung `/servers/{sid}`, membuka bookmark lama, atau mengeklik tautan navigasi insiden pada antarmuka web:
  1. **Rute Pintasan Server Otomatis pada Backend (`server/main.py`):**
     - Mengimplementasikan handler endpoint `@app.get("/servers/{sid}", response_class=HTMLResponse)` yang memvalidasi otentikasi sesi pengguna dan keberadaan server di basis data.
     - Mengalihkan (*HTTP 303 Redirect*) permintaan secara mulus ke rute kanonikal `/servers/{sid}/services` dengan mempertahankan seluruh parameter query URL (*query string* seperti `?tab=users`, `?tab=systemd`, dll.).
     - Mengalihkan pengguna non-otentikasi ke `/login` dan server yang tidak ditemukan ke `/servers`.
  2. **Standardisasi Tautan Notifikasi Alert Kritis & Modal Masalah (`server/templates/base.html`):**
     - Memperbarui tautan nama server pada kartu notifikasi baris alert kritis (`#alertTable tbody`) dari `/servers/{sid}` menjadi `/servers/{sid}/services`.
     - Memperbarui tombol tindakan "Buka Server" / "View Server" pada footer modal rincian masalah (`problemDetailModal`) agar mengarah langsung ke `/servers/{sid}/services`, menghindari beban redirect tambahan di sisi klien.

## Versi 4.8.35

- **Tipe Rilis:** Stabilisasi Bilah Alat Filter Pengguna & Grup serta Standardisasi Terminologi Linux (*Users & Groups Zero-Shift Toolbar Architecture & Linux Terminology Standardization*)
- **Fokus Utama:** Mengatasi anomali pergeseran tata letak tombol (*layout shift*) saat memilih filter Sistem atau kategori lainnya pada subview Pengguna dan Grup, serta menyelaraskan bahasa antarmuka ke standar Bahasa Indonesia yang lugas dan mudah dipahami sysadmin (`server/templates/services.html`):
  1. **Arsitektur Bilah Alat Berpindah Nol (*Zero Layout Shift Toolbar Strip*):**
     - Mengeliminasi penempatan kontrol filter dan pencarian dari dalam `card-header` yang sebelumnya rentan turun baris (*wrap*) hingga meloncat ~600px saat teks lencana jumlah entri melebar.
     - Mengimplementasikan bilah alat khusus (`.table-toolbar`) dengan lebar penuh di bawah judul kartu untuk menaungi tombol filter cepat di sisi kiri dan kotak pencarian instan di sisi kanan.
     - Hasil pengujian koordinat DOM membuktikan posisi tombol filter 100% terkunci stabil dengan pergeseran tepat **0.00 piksel** (*Zero Layout Shift*), mencegah tombol bergerak saat diklik oleh operator.
  2. **Penyelarasan Bahasa Indonesia yang Alami & Terminologi Standar Sysadmin:**
     - Mengganti istilah kaku "Istimewa" menjadi istilah teknis internasional standar **Privileged** pada tombol filter grup, lencana tabel, dan metadata tooltip untuk grup berakses administratif (`sudo`, `wheel`, `root`, `docker`, `adm`).
     - Menyederhanakan klasifikasi tipe grup menjadi **Sistem** (GID < 1000) dan **Reguler** (GID ≥ 1000), selaras dengan tombol filter dan istilah umum sistem operasi Linux.
     - Menyempurnakan label kolom dan deskripsi menjadi lebih lugas: **Grup Utama & Sekunder**, **Anggota (Members)**, serta deskripsi judul yang bersih tanpa kalimat bertele-tele.

## Versi 4.8.34

- **Tipe Rilis:** Perbaikan Sinkronisasi Filter Kategori & Pencarian Pengguna dan Grup dengan Paginasi (*Users & Groups Filter-Hidden Synchronization & Live Pagination Resilience*)
- **Fokus Utama:** Menyelesaikan kendala malfungsi tombol filter kategori (`Semua`, `Reguler`, `Sistem`, `Sesi Aktif` pada Pengguna dan `Semua`, `Reguler`, `Sistem`, `Istimewa` pada Grup) serta kotak pencarian instan pada subview Pengguna & Grup Sistem (`server/templates/services.html`):
  1. **Integrasi Atribut Filter Terhadap Mesin Paginasi Universal:**
     - Menetapkan atribut `dataset.filterHidden = isMatch ? '0' : '1'` pada setiap baris tabel (`#acc-table` dan `#groups-table`) di dalam fungsi `searchUsersTable()` dan `searchGroupsTable()`.
     - Memastikan mesin paginasi universal (`attachTablePagination`) membaca visibilitas baris secara akurat melalui `tr.dataset.filterHidden`, mengeliminasi bug di mana paginasi sebelumnya menimpa visibilitas baris dan membatalkan hasil filter kategori.
  2. **Pengelolaan Halaman & Pesan Status Kosong Dinamis (*Dynamic Empty State*):**
     - Mengotomatiskan pemanggilan `setPage(1)` saat tombol kategori diklik atau saat kata kunci pencarian diubah sehingga tampilan langsung melompat ke halaman pertama dari subset hasil filter.
     - Menyediakan penanganan kondisi tanpa hasil (*empty state*) secara dinamis; menyembunyikan tabel dan menampilkan pesan informatif baku (`Tidak ada pengguna/grup yang cocok dengan filter atau kata kunci pencarian.`) saat `matchCount === 0`, serta memulihkan tampilan tabel seketika saat pencarian dibersihkan.
  3. **Preservasi Status Filter pada Siklus Polling Latar Belakang (`renderSystem`):**
     - Mengintegrasikan eksekusi `searchUsersTable(false)` dan `searchGroupsTable(false)` pada fungsi pembaruan berkala `renderSystem(data)` pasca-rendering `tbody.innerHTML`, menjamin filter kategori dan kata kunci pencarian tetap bertahan tanpa ter-reset saat telemetri baru diterima dari agen.
     - Memperbarui teks lencana jumlah entri secara interaktif (`X / Y Pengguna` dan `X / Y Grup`) untuk memberikan umpan balik visual seketika kepada operator NOC.

## Versi 4.8.33

- **Tipe Rilis:** Transformasi Modul Users & Groups ala ServerBox Enterprise (*ServerBox-Inspired Users & Groups Modular Architecture*)
- **Fokus Utama:** Perombakan komprehensif tab Users pada modul Rincian Server untuk menyajikan visibilitas total seluruh pengguna reguler, akun sistem Linux, dan inventaris grup sistem operasi:
  1. **Sub-Navigasi Terpadu (*Segmented Bar*) & Dua Subview Modular (`server/templates/services.html`):**
     - Mengimplementasikan bilah kendali sub-tab ringkas untuk beralih instan antara tampilan **Pengguna (*Users*)** dan **Grup Sistem (*Groups*)** tanpa reload halaman.
     - **Subview Pengguna (*Users*)**: Menyajikan seluruh akun sistem operasi (`/etc/passwd`), mencakup pengguna reguler/manusia maupun daemon sistem (seperti `www-data`, `daemon`, `nobody`), disertai informasi UID/GID numerik, grup primer dan pil grup sekunder (*supplementary groups*), direktori home, klasifikasi visual shell interaktif vs nologin, riwayat login terakhir (`lastlog`), lencana hak akses (Sudoer, Sistem, Reguler, Terkunci), serta bilah filter kategori cepat (`Semua`, `Reguler`, `Sistem`, `Sesi Aktif`) dan pencarian instan multivariabel.
     - **Subview Grup (*Groups*)**: Menampilkan inventaris lengkap grup Linux (`/etc/group`), nomor GID, klasifikasi grup sistem vs kustom, lencana grup berhak istimewa (*privileged* seperti `sudo`, `wheel`, `root`, `docker`, `adm`), dan daftar seluruh pengguna terdaftar (*members*) per grup disertai jumlah anggota.
     - Menstandarisasi kolom tindakan berperekat (*sticky right action column*) dan paginasi terpadu 10 baris per halaman pada kedua tabel.
  2. **Pengayaan Telemetri Agen Klien (`agent/agent_pantau.py`):**
     - Memperbarui fungsi `collect_accounts()` agar mengumpulkan seluruh akun pengguna Linux tanpa mendiskualifikasi akun sistem, memetakan GID ke nama grup primer, mengumpulkan daftar grup sekunder pengguna, direktori home, dan status hak sudo.
     - Menambahkan fungsi `collect_groups()` untuk mengumpulkan seluruh grup Linux dari `grp.getgrall()`, mendeteksi grup berhak istimewa, serta memetakan keanggotaan grup secara timbal balik (*bidirectional member mapping*).
     - Mempertahankan prinsip *zero external dependency* hanya dengan modul bawaan Python standard library (`pwd`, `grp`).
  3. **Migrasi Skema Basis Data & API Backend (`server/models.py`, `server/main.py`):**
     - Menambahkan kolom `system_groups` berkapasitas `MEDIUMTEXT` pada tabel `server_extras` dan memperluas kapasitas kolom `accounts` menjadi `MEDIUMTEXT` guna menampung telemetri akun dan grup skala besar tanpa risiko pemotongan data.
     - Mengintegrasikan penanganan ingest payload `groups` pada endpoint `api_report`, penyertaan `system_groups` pada endpoint `api_server_system` dan `services_page`, serta memperkaya statistik identitas akun pada halaman rincian aktivitas pengguna (`user_activity.html`).

## Versi 4.8.32

- **Tipe Rilis:** Pemulihan Integritas Skrip Halaman Rincian Server & Kebijakan Keamanan Tipografi (*Server Details Script Integrity Recovery & Typography Security Policy Alignment*)
- **Fokus Utama:** Mengatasi galat eksekusi skrip antarmuka pada modul Rincian Server dan menyelaraskan kebijakan keamanan konten (*Content Security Policy*) peramban:
  1. **Eliminasi Galat Sintaksis JavaScript (`server/templates/services.html`):**
     - Menghapus karakter kurung kurawal penutup berlebih (`}`) pada blok pendaftaran tugas latar belakang di dalam fungsi `aptFollow`. Karakter berlebih tersebut sebelumnya menyebabkan penutupan fungsi asinkron lebih awal dan memicu galat kritis `SyntaxError: await is only valid in async functions and the top level bodies of modules` pada tingkat parsing peramban, yang melumpuhkan seluruh skrip interaktif modul Rincian Server (navigasi tab, pembaruan metrik berkala `poll()`, grafik performa, dan modal operasional).
     - Memastikan seluruh 11 tab navigasi (`perf`, `masalah`, `layanan`, `packages`, `proses`, `akun`, `ports`, `firewall`, `ssl`, `cron`, `log`) berfungsi responsif tanpa galat konsol.
  2. **Penyelarasan Direktif CSP untuk Tipografi Kustom (`server/main.py`):**
     - Memperbarui header middleware `Content-Security-Policy` dengan menyertakan domain `https://fonts.googleapis.com` pada direktif `style-src` dan `https://fonts.gstatic.com` pada direktif `font-src`. Hal ini mengeliminasi pemblokiran berkas gaya tipografi font kustom (Inter, Fira Code, JetBrains Mono) oleh kebijakan keamanan peramban.
  3. **Pengujian Menyeluruh & Sinkronisasi SemVer 7 Berkas:**
     - Menjalankan uji verifikasi komprehensif menggunakan headless Chromium browser via Selenium melintasi seluruh tab operasional dengan hasil 0 galat kritis (*zero severe/warning console errors*).
     - Menaikkan versi sistem menjadi `v4.8.32` secara sinkron dan identik di 7 berkas proyek sesuai standar operasional baku.

## Versi 4.8.31

- **Tipe Rilis:** Perbaikan Transmisi Parameter Upgrade Paket Mandiri & Pelabelan Modal APT (*Single Package Upgrade Parameter Transmission & Modal Labeling Fix*)
- **Fokus Utama:** Menyelesaikan masalah kegagalan eksekusi upgrade paket tunggal dari tab Packages dan memperbaiki kekeliruan judul/header modal tugas latar belakang:
  1. **Transmisi Parameter Paket Target pada Frontend (`server/templates/services.html`):**
     - Memperbaiki deklarasi fungsi `triggerAptTask(kind, detail = '')` dan `aptFollow(rid, kind, startedMs, detail = '')` agar menyertakan parameter `detail`.
     - Mengirimkan kolom `detail: pkgName` dalam payload JSON permintaan `fetch('/api/logs/request')` saat fungsi `upgradeSinglePkg(pkgName)` dieksekusi.
     - Menyimpan parameter `detail` ke dalam variabel sesi pelacakan `aptTaskDetail` serta menyertakannya pada pemanggilan API resume `apt_exec` di backend (`server/main.py`), mengeliminasi galat validasi agen `nama paket tidak valid untuk upgrade: ''`.
  2. **Standardisasi Label Header Modal & Notifikasi Desktop OS (`server/templates/services.html`):**
     - Memperbarui fungsi `aptLabel(kind, detail)` agar mengembalikan label perintah riil `apt install --only-upgrade <paket>` untuk tugas bertipe `PKG_UPGRADE`, mengeliminasi kemunculan label keliru bawaan `──── apt update ────`.
     - Menyesuaikan fungsi `updateAptTaskTitles(kind, detail)` dan notifikasi latar belakang desktop OS via `window.notifyBackgroundTaskComplete` agar secara akurat menampilkan judul `Upgrade Paket: <nama_paket>` baik saat proses dimulai, sedang berjalan, berhasil, maupun mengalami kegagalan.
  3. **Sinkronisasi SemVer 7 Berkas & Pengujian Runtime:**
     - Menaikkan versi aplikasi menjadi `v4.8.31` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.30

- **Tipe Rilis:** Sinkronisasi Kolom Insiden & Preservasi Kolom Berperekat Dinamis (*Incident Column Alignment & Dynamic Sticky Action Column Preservation*)
- **Fokus Utama:** Menyelesaikan masalah pertukaran posisi kolom saat polling latar belakang dan menjamin retensi kolom berperekat pada rendering dinamis JavaScript:
  1. **Sinkronisasi Urutan Kolom Insiden Terbuka (`server/templates/problems.html`):**
     - Memperbaiki ketidaksesuaian (*mismatch*) urutan kolom antara rendering awal Jinja SSR dengan pembaruan dinamis klien (`pollProblems()`).
     - Menyinkronkan urutan kolom secara konsisten: kolom ke-6 adalah *Panduan Solusi* (`col-tips`) dan kolom ke-7 adalah *Tindakan* (`col-act`).
     - Mengeliminasi anomali pertukaran posisi kolom setelah beberapa detik siklus polling berjalan, menjaga stabilitas posisi data panduan solusi dan tombol tindakan penanganan secara permanen.
  2. **Preservasi Kelas Berperekat pada Rendering Dinamis JavaScript (`server/templates/services.html`):**
     - Memperbaiki seluruh fungsi rendering dinamis JavaScript agar tetap menyematkan kelas `col-act` pada elemen `<td>` hasil mapping data telemetri:
       - Tab Users / Akun Linux: Menambahkan kelas `col-act` pada baris tabel `#acc-table` di fungsi `renderSys`.
       - Tab Ports / Socket Terbuka: Menambahkan kelas `col-act` pada baris tabel `#ports-table` di fungsi `renderPorts`.
       - Tab Cron Jobs: Menambahkan kelas `col-act` pada baris tabel `#cron-table` di fungsi `renderCron`.
       - Tab SSL/TLS: Menambahkan kelas `col-act` pada baris tabel `#ssl-table` di fungsi `renderSsl`.
       - Tab Firewall: Menambahkan kelas `col-act` pada baris tabel `#fw-blocked-table` di fungsi `renderFirewall`.
     - Menetapkan batas lebar minimum tabel (`min-width: 760px` pada `#acc-table` dan `min-width: 750px` pada `#ports-table`) serta lebar proporsional pada setiap kolom header, memastikan kolom tindakan berperekat (*sticky right*) dengan elevasi bayangan horizontal (`box-shadow: -4px 0 8px rgba(0,0,0,0.45)`) tetap aktif, presisi, dan tidak hilang setelah proses polling data latar belakang.
  3. **Sinkronisasi SemVer 7 Berkas & Pengujian Runtime:**
     - Menaikkan versi aplikasi menjadi `v4.8.30` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.29

- **Tipe Rilis:** Standardisasi Kolom Tindakan Berperekat, Kerapatan Tabel, & Kontrol Paginasi Cerdas (*Universal Sticky Action Column, Table Spacing Calibration & Smart Pagination Controls*)
- **Fokus Utama:** Menyempurnakan kerapatan, keterbacaan, dan ergonomi navigasi tabel pemantauan NOC di seluruh modul web aplikasi Pantau Server:
  1. **Kolom Tindakan Berperekat Universal (Universal Sticky Right Action Column):**
     - Mengimplementasikan aturan CSS universal bertaraf enterprise untuk `th.col-act, td.col-act, th.th-actions, td.td-actions, td.fm-actions-cell` dengan properti `position: sticky !important; right: 0 !important;` dan efek bayangan elevasi horizontal `box-shadow: -4px 0 8px rgba(0, 0, 0, 0.45) !important`.
     - Mendukung adaptasi warna latar belakang penuh di seluruh 4 mode tema: Midnight NOC (`#0b111e` / `#141e30`), Obsidian OLED (`#0d0d10` / `#17171f`), Deep Space Navy (`#131c31` / `#1b2642`), dan Mode Terang (`#ffffff` / `#f1f5f9` dengan bayangan lembut `rgba(0,0,0,0.08)`).
     - Memastikan tombol operasional cepat (Rincian, Terminal, Web SSH, File Manager, Restart, Hapus, dll.) selalu dapat diakses seketika tanpa perlu menggulir horizontal bolak-balik pada layar dengan resolusi terbatas.
     - Diterapkan secara konsisten di seluruh tabel: Halaman Daftar Server (`servers.html`), Insiden Server (`problems.html`), Pengelola Berkas (`file_manager.html`), Modal Keparahan Dasbor (`dashboard.html`), Probing Sintetis (`probing.html`), Profil/Pengguna (`profile.html`, `users.html`), serta seluruh tab modul Rincian Server (`services.html`): Layanan Inti, Unit Systemd, Paket Perangkat Lunak, Task Manager, Cron Job, Akun Pengguna Linux, Port Jaringan, Pengawasan SSL, dan Firewall Blocklist.
  2. **Kalibrasi Kerapatan & Presisi Kolom Daftar Server (`servers.html`):**
     - Menyelaraskan padding sel header `#servers-table th` menjadi `4px 5px` dan sel data `#servers-table td` menjadi `3px 5px`.
     - Merapatkan `min-width` seluruh kolom header secara proporsional (~10–20px lebih rapat): Server (`120px`), IP & Antarmuka (`95px`), Platform (`110px`), OS & Kernel (`115px`), Prosesor (`105px`), Memori RAM (`80px`), Penyimpanan (`90px`), Uptime (`80px`), Agen & APT (`75px`), Tag (`55px`), Status (`75px`), dan Tindakan (`88px`).
     - Menghilangkan celah kosong berlebih antar kolom tanpa mengorbankan keterbacaan teks dan angka metrik, menghasilkan tabel berkepadatan tinggi yang rapi, bersih, dinamis, dan presisi.
  3. **Penyempurnaan Ruang Napas Kolom Insiden Server (`problems.html`):**
     - Memberikan jarak proporsional antara kolom Waktu Mulai (`col-time`: `padding: 4px 14px 4px 6px`) dan Identitas Server (`col-server`: `padding: 4px 8px 4px 10px`) pada Kartu Insiden Terbuka (`#probtable`).
     - Memindahkan posisi kolom *Panduan Solusi* (`col-tips`) ke sebelum kolom *Tindakan* (`col-act`), memastikan kolom tindakan selalu menjadi kolom paling kanan yang berperekat sempurna tanpa menutupi tips penanganan.
  4. **Standarisasi Kontrol Paginasi Cerdas & Pengecualian Gateway/DNS:**
     - Menstandarisasi batas default paginasi 10 baris (`pageSize: 10`) pada seluruh tabel modul aplikasi (Unit Systemd, Paket APT, Riwayat Tindakan Operator, Daftar Insiden, Cron Job, Task Manager, dll.).
     - Menetapkan pengecualian khusus pada tabel *Konfigurasi Gateway & Resolver DNS* (`#spec-ifaces-table`) di tab Spesifikasi dengan batas default 5 baris (`defaultLimit: 5`, opsi `[5, 10, 25, 'all']`).
     - Mengimplementasikan logika auto-hide bilah paginasi cerdas pada helper `attachTablePagination` dan paginasi kustom: jika total baris data yang cocok kurang dari ambang batas (10 baris, atau 5 baris pada tabel DNS/Gateway), bar paginasi disembunyikan otomatis (`display: none`) untuk membebaskan ruang tampilan vertikal dan mengeliminasi kontrol navigasi yang mubazir.
  5. **Sinkronisasi SemVer 7 Berkas & Pengujian Runtime:**
     - Menaikkan versi aplikasi menjadi `v4.8.29` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.28

- **Tipe Rilis:** Sistem Kustomisasi Tampilan & Antarmuka Universal (*Enterprise Theme, Accent Palette, Typography & UI Customization Engine*)
- **Fokus Utama:** Menyediakan kontrol personalisasi antarmuka web menyeluruh bagi operator dan sysadmin agar dapat menyesuaikan tema visual, warna aksen, gaya font antarmuka & monospace, serta tingkat kerapatan tata letak (*density*) demi kenyamanan pengamatan monitor NOC di berbagai kondisi pencahayaan (ruangan gelap NOC vs ruangan terang siang hari):
  1. **Multi-Mode Tema Visual (Theme Engine):**
     - **Midnight NOC (Bawaan):** Tema gelap seimbang khas monitor NOC dengan gradien radial biru malam pekat.
     - **Obsidian OLED:** Tema hitam pekat murni (`#000000`) dengan 0% backlight glow dan kontras tinggi untuk efisiensi panel OLED dan kenyamanan mata di malam hari.
     - **Deep Space:** Tema biru malam pekat khas Proxmox / Grafana dengan aksen border biru transparan.
     - **Mode Terang (Light Modern):** Tema terang cerah dan bersih (`#f8fafc` & `#ffffff`) dengan bayangan kartu halus dan kontras teks tinggi (`#0f172a`), ideal untuk lingkungan kerja siang hari.
  2. **Palet Warna Aksen Antarmuka (Accent Palette):**
     - Mendukung 5 warna aksen primer: Sian (`#38bdf8` - Bawaan), Indigo (`#6366f1`), Zamrud (`#10b981`), Violet (`#a855f7`), dan Sunset Amber (`#f59e0b`).
     - Mengubah variabel CSS aksen (`--blue`, `--blue-hover`, `--blue-bg`, `--accent`) secara global dan real-time di seluruh komponen (navigasi aktif, lencana, fokus input, tombol, dan border).
  3. **Tipografi & Gaya Font Fleksibel:**
     - **Font Antarmuka (UI):** Sistem Bawaan (*San Francisco, Segoe UI, Roboto*), Inter (Modern & Presisi), Geist Sans (Tech & Minimalis), dan Ubuntu / Fira Sans (Khas Linux).
     - **Font Monospace (Data, IP, Metrik):** Sistem Monospace (*Consolas, SFMono*), JetBrains Mono (Khas IDE), dan Fira Code (Presisi Teknis).
  4. **Kerapatan Tata Letak Antarmuka (UI Density):**
     - **Kompak NOC (Bawaan):** Kepadatan data tinggi dengan padding sel rapat 3px-6px dan ruang vertikal minimal khas ruang kendali jaringan.
     - **Normal Nyaman:** Ruang spasi dan padding kartu lebih lega untuk peninjauan santai.
  5. **Arsitektur Zero-FOUC & Pratinjau Instan (Live Preview):**
     - Script inisialisasi awal di `<head>` mengevaluasi `localStorage` sebelum kalkulasi DOM dan rendering CSS peramban, mengeliminasi efek kedipan (*Flash of Unstyled Content*).
     - Seluruh perubahan pada modal kustomisasi langsung diaplikasikan ke DOM secara live tanpa reload halaman.
     - Dialog kustomisasi tema dapat dibuka melalui menu sidebar *Kustomisasi UI*, tombol cepat tema pada footer sidebar, header mobile, serta profil akun pengguna. Dilengkapi tombol *Kembalikan Bawaan* dan dukungan tombol `Escape`.
  6. **Sinkronisasi SemVer 7 Berkas & Pengujian Runtime:**
     - Menaikkan versi aplikasi menjadi `v4.8.28` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.27

- **Tipe Rilis:** Transformasi Halaman Daftar Server Menjadi Direktori Inventaris Mesin Klien Lengkap (*Fleet Client Machine Identity & Inventory Directory*)
- **Fokus Utama:** Membedakan fungsi secara tegas antara Halaman Utama (`dashboard.html`) sebagai Pusat Telemetri & Beban Real-Time dengan Halaman Daftar Server (`servers.html`) sebagai Direktori Inventaris & Identitas Armada Server Klien Lengkap (*Fleet Machine Identity Directory*) dalam 1 tabel terpadu berdensitas tinggi kelas enterprise khas NOC:
  1. **Rekayasa Ulang Tabel Daftar Server (`server/templates/servers.html`):**
     - Mentransformasikan tabel daftar server menjadi 12 kolom identitas teknis mesin klien yang padat, rapi, proporsional, dan informatif tanpa teks mubazir atau pengulangan metrik beban sekunder:
       1. **Server:** Hostname sebagai tautan navigasi langsung ke `/services`, dot status realtime (Online, Pemeliharaan, Offline), lencana tier (`tier-1`, `tier-2`, `tier-3`), dan catatan singkat host.
       2. **IP & Interface:** Alamat IP primer tersalin instan (`copyable-ip`) berwarna `#58a6ff`, antarmuka fisik utama terdeteksi (seperti `ens18`, `eth0`, `eno1`), serta lencana `Lokal` untuk host jaringan terisolasi.
       3. **Platform & Mesin:** Lencana platform virtualisasi (`BAREMETAL`, `VM (KVM)`, `LXC`), lencana proteksi Proxmox HA (`HA`), serta vendor dan tipe model perangkat keras mesin klien (misal `Dell Inc. PowerEdge R440`, `HPE ProLiant DL380 Gen11`, `QEMU KVM Guest`, `ASUSTeK COMPUTER INC.`).
       4. **Sistem Operasi:** Nama lengkap distribusi OS (misal `Ubuntu 24.04.5 LTS`, `Debian GNU/Linux 12`), versi kernel yang sedang berjalan (misal `7.0.14-11-pve`, `6.8.0-147-generic`, `5.15.0-181-generic`), dan arsitektur CPU (`x86_64`).
       5. **Prosesor:** Nama model prosesor bersih dari karakter derau registrasi (seperti `Intel Xeon Gold 6430`, `Intel Xeon Bronze 3104`, `Intel Xeon E-2234`) dan jumlah inti CPU (`X Cores`).
       6. **Memori:** Kapasitas total memori utama (RAM) dan alokasi kapasitas Swap.
       7. **Penyimpanan:** Ringkasan seluruh partisi dan kapasitas penyimpanan fisik klien (misal `195.8G (rootfs)`, `50G (sda)`, `931G (sda)`).
       8. **Uptime & Boot:** Durasi aktif sistem dalam format baku Indonesia (`Xh Yj`, `Xj Ym`) serta stempel waktu boot sistem terakhir.
       9. **Agen & APT:** Versi agen pemantau klien (`v4.8.27`, dengan indikator panah oranye jika usang) dan lencana status ketersediaan pembaruan paket sistem operasi (`X paket` / `mutakhir`).
       10. **Tag:** Lencana pengelompokan tag server klien.
       11. **Status & Lapor:** Lencana status operasional (Online, Pemeliharaan, Offline) dan waktu relatif laporan terakhir (`X dtk lalu`, `X mnt lalu`).
       12. **Tindakan (Sticky Column):** Kolom tindakan berperekat (*sticky right column*) dengan efek bayangan halus (`box-shadow`) yang memastikan tombol aksi cepat (Buka Rincian Layanan, Edit Konfigurasi Server, dan Hapus Server berbasis dialog Guardrail) selalu terlihat dan mudah diakses di seluruh resolusi layar.
  2. **Ekstraksi & Sanitasi Identitas Perangkat Keras di Backend (`server/main.py`):**
     - Menambahkan fungsi pembersih `_clean_cpu_model()` untuk mengeliminasi derau simbolis (`(R)`, `(TM)`, clock rate `@ X.XXGHz`, dll.) agar nama model prosesor tampil rapi dan standar enterprise.
     - Menambahkan ekstraktor penyimpanan fisik `_extract_disks_summary()` dari struktur `hardware_specs.disks`.
     - Menambahkan ekstraktor model perangkat keras `_extract_hw_model()` yang menggabungkan vendor dan produk sistem host.
     - Menambahkan detektor antarmuka jaringan primer `_extract_primary_interface()` yang menyaring virtual bridge (`br-`, `docker`, `veth`, `lo`) dan mendeteksi NIC fisik utama.
     - Memperkaya endpoint API `/api/servers` (`api_servers`) dan perender Jinja `/servers` (`servers_page`) dengan atribut identitas perangkat keras lengkap, durasi uptime numerik (`uptime_secs`), serta kapasitas RAM dalam bytes.
  3. **Pencarian Cerdas Multivariabel & Pengurutan Berbasis Nilai Numerik Akurat:**
     - Memperluas atribut pencarian `data-srv-filter` pada setiap baris sehingga operator dapat mencari server secara instan berdasarkan nama host, IP, nama antarmuka (`ens18`), nama model prosesor (`Xeon`), vendor mesin (`Dell`, `HPE`), distro OS (`Ubuntu`, `Debian`), kernel, versi agen, tag, hingga catatan host.
     - Menyempurnakan pengurutan tabel (`th.sortable`) dengan evaluasi nilai numerik murni: pengurutan Uptime menggunakan `data-uptime-secs`, kapasitas RAM menggunakan `data-ram-bytes`, jumlah core CPU menggunakan `data-cpu-cores`, dan waktu lapor menggunakan stempel ISO `data-last-seen`.
  4. **Sinkronisasi SemVer 7 Berkas & Pengujian Runtime:**
     - Menaikkan versi aplikasi menjadi `v4.8.27` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.26

- **Tipe Rilis:** Modal Konfirmasi Universal Enterprise & Eliminasi Dialog Bawaan Browser (*Enterprise Universal Confirmation Modal & Native Browser Dialog Elimination*)
- **Fokus Utama:** Mengeliminasi 100% dialog popup bawaan browser (`window.confirm()` dan `window.alert()`) yang kaku, kuno, dan memblokir thread UI di seluruh halaman web aplikasi, serta menggantikannya dengan dialog modal konfirmasi sentral berbasis HTML5/CSS modern berstandar enterprise NOC:
  1. **Komponen Dialog Modal Universal Sentral (`#app-confirm-modal` di `server/templates/base.html`):**
     - Membangun komponen modal konfirmasi universal di berkas tata letak utama (`base.html`), siap dipakai di seluruh halaman web Pantau Server (`dashboard`, `services`, `probing`, `problems`, `profile`, `users`, `file_manager`, dan `user_activity`).
     - Desain visual bertaraf enterprise NOC: latar belakang gelap `#161b22`, border rapi `#30363d`, efek *smooth backdrop-blur* (4px), bayangan halus (`0 24px 60px rgba(0,0,0,0.85)`), dan animasi kemunculan kurva *cubic-bezier* (`appModalIn`).
     - Ikon SVG tematik adaptif: ikon Peringatan Segitiga Merah (`danger`), Perisai Amber (`warning`), dan Lingkaran Informasi/Jalankan Biru (`primary`/`info`).
     - Lencana target monospaced eksplisit (`Target: PID / IP / Endpoint / Pengguna`) untuk memastikan operator mengetahui persis objek yang akan diproses tanpa kalimat ambigu.
     - Pesan dampak tindakan ringkas 1 baris berorientasi teknis tanpa kata-kata berlebihan atau teks mubazir.
     - Tombol aksi jelas: tombol batal *ghost* dan tombol konfirmasi proporsional (`btn-danger`, `btn-warning`, `btn-primary`).
     - Aksesibilitas dan navigasi papan ketik penuh: penekanan tombol `Enter` langsung mengeksekusi konfirmasi, penekanan tombol `Esc` atau klik di luar kartu membatalkan dialog. Terintegrasi penuh dengan pengendali modal universal `dismissActiveModal()`.
  2. **API Global Asinkron & Otomatisasi Formulir Deklaratif:**
     - Menyediakan API berbasis Promise `window.showConfirmModal(opts)` dan `window.closeAppConfirmModal(result)` yang mengembalikan nilai boolean secara asinkron tanpa memblokir thread JavaScript browser.
     - Mencegat secara deklaratif seluruh formulir HTML yang memiliki atribut `data-confirm`: menghentikan submit default secara transparan, memunculkan modal `#app-confirm-modal`, dan meneruskan submit (`f.requestSubmit()`) setelah dikonfirmasi oleh operator.
  3. **Migrasi Menyeluruh di 8 Berkas Antarmuka Web:**
     - `server/templates/base.html`: konfirmasi *Acknowledge* masal insiden kritis (`alertAckAll`), pengaktifan kembali pemantauan (`unignoreProblem`), dan pencegatan formulir `data-confirm`.
     - `server/templates/services.html`: delegasi `showSvcConfirmModal`, penghentian proses via sinyal (`sendProcDirectSignal`), kunci/buka kunci pengguna Linux (`lockLinuxUser`), pemutusan sesi terminal (`terminateSession`), *acknowledge* insiden individual (`ackProblemInDetail`), aturan port firewall (`submitPortRule`), reload/enable/disable firewall UFW (`submitFirewallAction`), buka blokir IP (`submitFirewallUnblock`), uji coba jalankan tugas cron (`submitCronRun`), hapus tugas cron (`submitCronDelete`), hapus pengawasan sertifikat SSL (`submitSslRemovePath`), blokir masal IP penyerang (`submitProblemBlockAttackerIps`), pembersihan cache deb paket (`clearPkgCache`), dan peningkatan versi paket OS (`upgradeSinglePkg`).
     - `server/templates/probing.html`: penghapusan endpoint pemantauan SLA (`deleteProbe`) dan konversi notifikasi galat ke sistem *toast*.
     - `server/templates/problems.html`: reset ambang batas global ke pengaturan pabrik (`resetThresholds`) dan penanganan insiden (*acknowledge*).
     - `server/templates/file_manager.html`: penguncian sesi File Manager (`lockFileManagerSession`), pemulihan berkas dari cadangan `.bak` (`fmRestoreBak`), dan konversi seluruh pesan alert ke toast non-blocking.
     - `server/templates/profile.html`: pembuatan ulang kode pemulihan 2FA, penonaktifan 2FA, serta penguncian dan pembukaan akun staf via formulir `data-confirm`.
     - `server/templates/users.html`: penguncian dan pembukaan kembali akun pengguna staf via atribut deklaratif `data-confirm`.
     - `server/templates/user_activity.html`: pemutusan paksa sesi terminal aktif (`terminateSession`) dan penggantian alert ke toast.
  4. **Sinkronisasi SemVer 7 Berkas & Kebijakan Zero-Dependency:**
     - Menaikkan versi aplikasi menjadi `v4.8.26` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.25

- **Tipe Rilis:** Benteng Otentikasi Tindakan Operator Berat & Standarisasi UI/UX Enterprise (*Privileged Operator Action Step-Up Authentication & Enterprise Guardrail System*)
- **Fokus Utama:** Mengamankan seluruh tindakan operator berisiko tinggi dan katastropik melalui verifikasi kata sandi akun operator (Step-Up Auth) dan kode 2FA TOTP di tingkat backend, serta menata ulang antarmuka dialog konfirmasi (*Guardrail Modal*) dengan standar enterprise berdensitas tinggi tanpa teks mubazir:
  1. **Validasi Wajib Kata Sandi Operator di Backend API (`server/main.py`):**
     - Mengimplementasikan helper otentikasi sentral `_verify_operator_password()` yang memvalidasi hash kata sandi operator login (`pwd_ctx.verify`) dan kode TOTP 2FA akun sebelum tindakan dieksekusi, serta mencatat pencatatan audit kegagalan (`_audit`) jika otentikasi tidak sah.
     - Menerapkan benteng otentikasi pada seluruh tindakan Tingkat 1 (Katastropik & Permanen):
       - `POST /servers/{sid}/host/reboot` (Reboot Sistem Operasi Host)
       - `POST /servers/{sid}/host/poweroff` (Matikan Daya Host)
       - `POST /servers/{sid}/delete` (Hapus Server dari Pantau + validasi ketik ulang nama host)
       - `POST /servers/{sid}/regenerate-key` (Regenerasi Kunci API Server)
       - `POST /servers/{sid}/system-users/delete` (Hapus Pengguna Linux Klien)
       - `POST /users/{uid}/delete` (Hapus Akun Staf Dashboard)
       - `POST /api/users/{uid}/2fa/disable` (Nonaktifkan 2FA Akun Staf)
  2. **Penyempurnaan Dialog Guardrail Enterprise (`server/templates/base.html`):**
     - Menata ulang komponen `#guardrail-modal` dengan tata letak padat, kontras tinggi, dan pesan lugas tanpa kalimat bertele-tele.
     - Menyediakan input kata sandi operator, input kode 2FA TOTP otomatis (terbuka jika akun staf mengaktifkan 2FA), input konfirmasi nama host, serta penolakan tombol submit secara dinamis sebelum parameter wajib terisi lengkap.
     - Mendukung penyerahan instan melalui penekanan tombol `Enter` pada kolom kata sandi dan indikator animasi pemrosesan (*loading spinner*).
     - Menyediakan API berbasis Promise `window.showGuardrailPasswordModal(options)` untuk integrasi mulus dengan pemanggilan asinkron fetch/AJAX di seluruh antarmuka.
  3. **Pemisahan Tegas Tingkat 1 (Kata Sandi) vs Tingkat 2 (Penegasan Bahaya):**
     - Mempertahankan kelincahan respons insiden NOC (*Incident Response Velocity*): tindakan mitigasi cepat seperti Stop/Restart Service, Kill Process, Blokir/Buka Blokir IP Firewall, dan Pemutusan Sesi SSH tetap menggunakan dialog konfirmasi bahaya tanpa hambatan kata sandi agar pemulihan darurat tidak terhambat.
  4. **Sinkronisasi SemVer 7 Berkas & Kebijakan Zero-Dependency:**
     - Menaikkan versi aplikasi menjadi `v4.8.25` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.24

- **Tipe Rilis:** Proteksi Penguncian & Pembersihan Terminal Saat Proses Konsol Aktif (*Terminal Process Safety Guard & Execution State Detection*)
- **Fokus Utama:** Mengamankan operasional web terminal bawaan Linux dari pemutusan sesi atau pembersihan layar yang tidak disengaja saat ada proses yang sedang berjalan di konsol:
  1. **Proteksi Dinamis Tombol Kunci & Bersihkan Layar (`server/templates/services.html`):**
     - Mengubah status Tombol Kunci Terminal (`#term-lock-btn`), Tombol Bersihkan Layar Konsol (`#term-clear-btn`), dan titik kontrol pembersih layar kuning (`#term-dot-clear`) secara otomatis menjadi *disabled* (atribut `disabled = true`, transparansi redup `opacity: 0.35`, kursor `not-allowed`, dan penonaktifan pointer events) ketika ada perintah shell atau tugas APT yang sedang berjalan di konsol terminal.
     - Menyematkan perlindungan preventif berlapis: fungsi `clearScreen()` dan `openTerminalLockConfirmModal()` secara otomatis menolak eksekusi dan memunculkan toast peringatan jika dipanggil saat proses konsol masih aktif.
     - Menyematkan responsivitas instan di sisi klien: mendeteksi penekanan tombol Enter (`\r` atau `\n`) pada masukan kursor untuk langsung melumpuhkan tombol secara optimistik sebelum sinyal jaringan kembali dari agen.
  2. **Deteksi Status Proses Konsol POSIX & Proc Stat Kernel (`agent/agent_pantau.py`):**
     - Mengimplementasikan fungsi pelacak status proses konsol ganda: inspeksi grup proses foreground POSIX `os.tcgetpgrp(master_fd)` untuk shell PTY langsung, serta pemindaian status `/proc/[pid]/stat` (evaluasi field `pgrp` vs `tpgid`) untuk mendeteksi proses anak yang berjalan di bawah wrapper `pantau-shell` dan session manager tmux tanpa memerlukan eskalasi sudo.
     - Mengirimkan status `busy: bool` secara realtime dari thread pembaca PTY agen ke backend server saat ada luaran chunk stdout maupun saat konsol kembali idle setelah menyelesaikan eksekusi perintah.
  3. **Penyempurnaan WebSocket Bridge & Format Durasi Notifikasi Baku:**
     - Menghubungkan transmisi flag `busy` dari endpoint HTTP POST `/api/agent/terminal/{session_id}/stdout` ke sesi WebSocket browser aktif melalui `bridge.browser_ws`.
     - Memperbaiki penamaan durasi proses latar belakang pada kartu toast mengambang dan notifikasi desktop di `base.html` dari format singkatan `${durationSecs}s` menjadi format baku Bahasa Indonesia `⏱️ ${durationSecs} dtk` dengan tooltip informatif "Durasi eksekusi proses: X detik".
  4. **Sinkronisasi SemVer 7 Berkas & Kebijakan Zero-Dependency:**
     - Menaikkan versi aplikasi menjadi `v4.8.24` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.23

- **Tipe Rilis:** Sistem Notifikasi Tugas Latar Belakang Lintas Halaman & Desktop OS (*Cross-Page Background Task Notification & Native OS Desktop Alerts*)
- **Fokus Utama:** Membangun sistem notifikasi penyelesaian tugas latar belakang mandiri berarsitektur dua lapis (*Dual-Layer Notification System*) dengan durasi otomatis 5 detik, bilah hitung mundur interaktif (*animated countdown bar*), dan jeda otomatis saat kursor mouse diarahkan (*pause on hover*):
  1. **Lapisan Desktop OS (Web Notifications API):**
     - Mengintegrasikan API standar W3C `window.Notification` untuk memunculkan notifikasi native sistem operasi (Windows Action Center, GNOME Shell, KDE, macOS Notification) langsung di atas semua aplikasi aktif di layar pengguna saat tugas berdurasi panjang selesai (Update indeks APT, Upgrade paket OS, Pembaruan agen OTA, Pembersihan cache paket, dan Pemutusan sesi terminal SSH).
     - Menutup notifikasi desktop secara otomatis setelah 5 detik (`setTimeout(5000)`) dan memfokuskan kembali tab aplikasi saat notifikasi diklik.
     - Menyediakan fungsi permintaan izin terisolasi `requestDesktopNotificationPermission()` yang dipanggil secara proaktif saat operator memicu tugas sistem.
  2. **Lapisan Web In-App Mengambang (`server/templates/base.html`):**
     - Menyediakan kontainer notifikasi mengambang `#pantau-bg-notifier-root` dengan prioritas z-index tertinggi (`z-index: 100001`) yang diposisikan di pojok kanan atas layar di atas seluruh elemen web dan modal dialog.
     - Menghadirkan kartu toast mini bergaya NOC modern (`.pantau-bg-toast`) lengkap dengan ikon status SVG, badge server, indikator durasi proses, pesan hasil ringkas, tombol tutup (`×`), dan garis susut waktu 5 detik (`@keyframes pantauToastProgress`).
     - Menyediakan interaksi intuitif: kursor diarahkan (*mouseenter*) menjeda hitung mundur dan animasi, serta melanjutkan kembali saat kursor keluar (*mouseleave*).
  3. **Pelacak Tugas Latar Belakang Lintas Halaman (*Cross-Page Background Task Tracker*):**
     - Mengimplementasikan `registerTrackedBackgroundTask` dan `unregisterTrackedBackgroundTask` berbasis `localStorage` (`pantau_tracked_tasks`) dan poller otomatis di `base.html`.
     - Memastikan jika operator berpindah halaman (misalnya dari halaman detail server ke Dashboard atau Insiden) saat proses upgrade atau update sedang berjalan, notifikasi penyelesaian tetap muncul seketika di halaman tujuan saat proses selesai.
  4. **Sinkronisasi SemVer 7 Berkas & Kebijakan Zero-Dependency:**
     - Menaikkan versi aplikasi menjadi `v4.8.23` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.22

- **Tipe Rilis:** Penyelarasan Filosofi Dasbor NOC & Eliminasi Lencana Sekunder HA (*NOC Dashboard Situational Awareness Alignment & HA Secondary Badge Elimination*)
- **Fokus Utama:** Mengembalikan filosofi murni halaman utama dasbor pemantauan NOC (`dashboard.html`) yang berfokus tunggal pada kesadaran situasi operasional (*situational awareness*), identitas esensial host, metrik performa real-time, dan insiden aktif:
  1. **Eliminasi Lencana Proxmox HA pada Dasbor Utama (`server/templates/dashboard.html`):**
     - Menghapus rendering Server-Side (SSR) lencana emas Proxmox HA (`is_proxmox_ha`) baik pada tampilan tabel armada server (`#dash-fleet-table`) maupun pada tampilan kartu kisi server (`#dash-grid-container`).
     - Menyederhanakan fungsi pembantu JavaScript `getPlatformBadgeHtml(plat)` pada siklus polling dinamis `pollNocDashboard()` agar mengembalikan murni badge platform inti (`LXC`, `VM (KVM)`, `BAREMETAL`) tanpa menyisipkan lencana HA sekunder.
     - Membersihkan seluruh pemanggilan `getPlatformBadgeHtml(srv.platform)` di tabel dan kartu dasbor.
  2. **Preservasi Informasi HA pada Tampilan Detail & Inventaris:**
     - Informasi proteksi Proxmox HA tetap dipertahankan secara utuh dan proporsional pada inventaris lengkap (`servers.html`), halaman rincian telemetri mendalam (`services.html`), dan formulir pengaturan server (`server_form.html`).
  3. **Sinkronisasi SemVer 7 Berkas & Stabilitas Sistem:**
     - Menaikkan versi aplikasi menjadi `v4.8.22` secara sinkron dan identik di 7 berkas: `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.

## Versi 4.8.21

- **Tipe Rilis:** Benteng Anti-Bricking Agen & Mekanisme Pemulihan Otomatis OTA (*Agent Anti-Bricking Fortress & Automatic OTA Recovery Mechanism*)
- **Fokus Utama:** Mengimplementasikan benteng proteksi permanen anti-bricking pada sistem pembaruan Over-The-Air (OTA) agen monitoring agar agen tidak pernah mati total akibat pembaruan rusak di masa depan:
  1. **Pengujian Pra-Eksekusi Runtime Terisolasi (*Pre-flight Isolated Runtime Execution Check*):**
     - Menggantikan validasi statis pasif yang sebelumnya hanya mengandalkan `py_compile.compile` dengan pengujian eksekusi runtime penuh di subproses mandiri terisolasi berbatas waktu 15 detik:
       `subprocess.run([sys.executable, tmp_path, "--test-runtime"], capture_output=True, text=True, timeout=15)`.
     - Menambahkan flag CLI resmi bawaan `--test-runtime`, `--check-syntax-only`, `-v`/`--version`, dan `-h`/`--help` pada agen klien: interpreter memvalidasi seluruh hierarki modul dan konstanta inti (`AGENT_VERSION`, `main`, `_exec_update_agent`) secara eksplisit tanpa mengandalkan pernyataan `assert` (kebal terhadap eksekusi Python mode teroptimasi `-O`), lalu keluar seketika dengan `sys.exit(0)` tanpa memicu worker latar belakang, permintaan jaringan HTTP, atau thread loop.
     - Jika subproses menghasilkan kode keluar != 0 (melempar `NameError`, `ImportError`, `SyntaxError`, atau `TimeoutExpired`), agen seketika MENOLAK instruksi pembaruan, menghapus berkas sementara, dan membiarkan berkas aktif `/opt/pantau/agent/agent_pantau.py` tetap berjalan utuh melayani telemetri NOC tanpa terputus.
  2. **Cadangan Atomik Otomatis & Validasi Pra-Tulis (*Atomic Backup & Pre-Write Validation*):**
     - Sebelum menyalin berkas pembaruan baru ke `/opt/pantau/agent/agent_pantau.py`, agen secara otomatis membuat salinan cadangan berkas aktif yang saat ini berjalan ke `/opt/pantau/agent/agent_pantau.py.bak` melalui berkas sementara atomik (`os.replace`) maupun via wrapper `pantau-file`.
     - Menjalankan uji validasi runtime pra-tulis pada berkas cadangan (`--test-runtime`): jika berkas cadangan gagal divalidasi atau gagal dibuat, instruksi pembaruan dibatalkan seketika dan berkas target tidak disentuh.
  3. **Penulisan Atomik POSIX & Verifikasi Pasca-Penulisan (*POSIX Atomic Write & Strict Auto-Rollback*):**
     - Menggunakan mekanisme penulisan atomik direktori lokal (`open` temp -> `fsync` -> `chmod 0755` -> `os.replace`) untuk mengeliminasi risiko berkas kosong/terpotong akibat kegagalan disk I/O.
     - Melakukan verifikasi runtime sekunder pada `/opt/pantau/agent/agent_pantau.py` dengan penanganan eksepsi ketat: jika subproses gagal atau mengalami batas waktu (*timeout*), agen membatalkan pembaruan, melakukan rollback instan ke cadangan sehat yang tersedia, dan menolak merestart agen dengan berkas rusak.
  4. **Pemulihan Darurat Bertingkat Unit Layanan Systemd (*Multi-Layer Service Auto-Recovery via ExecStartPre*):**
     - Menambahkan direktif `ExecStartPre=+-/bin/sh -c '...'` berhak akses penuh (`+`) pada unit systemd `agent_pantau.service` dan templat otomatis `clean_service_unit`.
     - Menyediakan pencarian cadangan bertingkat (*multi-layer backup fallback*): jika berkas utama `/opt/pantau/agent/agent_pantau.py` rusak/hilang, systemd mengevaluasi cadangan `.bak` utama dan seluruh cadangan berkala bertanda waktu (`.bak.*`) dari yang terbaru. Berkas cadangan pertama yang lolos pengujian runtime `--test-runtime` dipulihkan secara otomatis dengan log pencatatan `logger -t agent_pantau` ke syslog, memastikan daemon selalu pulih tanpa intervensi manual.
  5. **Sinkronisasi SemVer 7 Berkas & Kebijakan Zero-Dependency:**
     - Sinkronisasi versi v4.8.21 secara menyeluruh dan identik pada `server/config.py`, `server/templates/base.html`, `package/opt/pantau/agent/agent_pantau.py`, `agent/agent_pantau.py`, `package/install.sh`, `README.md`, dan `DEVELOPMENT.md`.
     - Menjamin agen pemantau tetap 100% mematuhi prinsip *zero external dependency* (Python 3.10+ standard library).

## Versi 4.8.20

- **Tipe Rilis:** Penyempurnaan Penutupan Subproses Prober, Skema Basis Data, & Pemetaan CN Sertifikat SSL (*Prober Subprocess Clean-up, Database Schema Synchronization, & SSL CN Extraction*)
- **Fokus Utama:** Menyempurnakan stabilitas operasional pada prober ICMP ping, model relasional basis data, ketahanan parser sertifikat SSL, dan hierarki visual SLA dasbor:
  1. **Penutupan Eksplisit Subproses Transport Prober (`server/prober.py`):**
     - Menambahkan penutupan eksplisit `proc._transport.close()` setelah `proc.communicate()` serta pada blok `asyncio.TimeoutError` dan `Exception` di `probe_icmp`.
     - Mengeliminasi peringatan sumber daya `ResourceWarning: unclosed transport` dan galat fatal `RuntimeError: Event loop is closed` saat event loop Python ditutup atau saat subproses di-garbage collect.
  2. **Sinkronisasi Kolom `backup_status` pada Model Basis Data (`server/models.py`):**
     - Menambahkan definisi kolom `backup_status = Column(MEDIUMTEXT, nullable=True)` pada model `ServerExtra`.
     - Menyelaraskan seluruh 16 tabel dan kolom secara 100% identik antara model SQLAlchemy `server/models.py`, berkas skema resmi `database/schema.sql`, dan basis data MariaDB aktif.
  3. **Peningkatan Ketahanan Parser Tanggal SSL Remote (`server/prober.py`):**
     - Mengimplementasikan fungsi pembantu `_parse_cert_date` dengan dukungan multi-format baku (`%b %d %H:%M:%S %Y %Z`, `%b %d %H:%M:%S %Y GMT`, `%b %d %H:%M:%S %Y UTC`, `%Y%m%d%H%M%SZ`, `%Y-%m-%d %H:%M:%S`).
     - Menyaring alamat IP pada `inspect_remote_ssl_certificate` agar tidak mengirim header SNI (RFC 6066) saat target berupa literal IPv4/IPv6, dan membersihkan skema URL otomatis.
  4. **Ekstraksi CommonName (CN) Sertifikat SSL & Normalisasi Tanggal Agen (`agent/agent_pantau.py` & `package/opt/pantau/agent/agent_pantau.py`):**
     - Menambahkan ekstraksi `commonName` (CN) pada `collect_ssl_certs` saat sertifikat tidak memiliki ekstensi SAN DNS, mencegah tampilan LDAP Distinguished Name (DN) panjang yang merusak kepadatan tabel NOC.
     - Menyediakan parser tanggal tangguh `_parse_agent_cert_date` pada agen klien untuk menangani variasi format OpenSSL antar distro.
     - Menyinkronkan konstanta `PANTAU_APT_SCRIPT_BODY` lengkap dengan dokumentasi operasional dan komentar per-mode sesuai berkas `package/usr/local/sbin/pantau-apt`.
  5. **Standarisasi Hirarki Visual SLA Uptime Prober (`server/templates/probing.html`):**
     - Mengimplementasikan standar tiga warna NOC pada kolom ketersediaan uptime: Hijau (`>= 99.0%`), Kuning (`>= 95.0%`), dan Merah tebal (`< 95.0%`, termasuk `0.0%`).
     - Menyematkan pembulatan format desimal konsisten `.toFixed(1)` dan pewarnaan dinamis adaptif pada kartu KPI rata-rata uptime (`#kpi-uptime`) serta modal riwayat analitik (`hist-up-24` dan `hist-up-30`).

## Versi 4.8.19

- **Tipe Rilis:** Penyempurnaan Menyeluruh Stabilitas Prober, Keamanan Zero-Dependency Agen, & Kepadatan Dasbor (*Prober Resilience, Zero-Dependency Agent Hardening, & Dashboard NOC Density*)
- **Fokus Utama:** Menyelesaikan 11 area perbaikan struktural pada mesin probing sintetis, agen klien, skema basis data, dan antarmuka dasbor:
  1. **Eliminasi Pembekuan SLA Rolling Uptime Prober (`server/prober.py`):**
     - Mengonversi nilai `stats_24h.up_cnt`, `stats_24h.total`, `stats_30d.up_cnt`, dan `stats_30d.total` ke tipe `float` secara eksplisit pada fungsi `calculate_rolling_uptime`.
     - Mencegah galat `TypeError` akibat percampuran tipe `Decimal` dari MariaDB `func.sum()` dengan tipe `float` Python yang sebelumnya membekukan pembaruan persentase SLA uptime prober.
  2. **Koreksi Evaluasi Falsy Uptime 0.0% (`server/main.py` & `server/templates/probing.html`):**
     - Mengubah evaluasi nilai falsy `or 100.0` dan `|| 100` menjadi pengecekan eksistensi nilai eksplisit (`is not None` pada backend dan `!== undefined && !== null` pada antarmuka frontend).
     - Menjamin endpoint yang mengalami downtime total (uptime 0.0%) ditampilkan secara akurat 0.0% pada API list probe, API detail probe, kartu KPI ringkasan, dan modal riwayat inspeksi tanpa keliru melompat menjadi 100.0%.
  3. **Penguatan Mesin Inspeksi SSL Remote pada Mode CERT_NONE (`server/prober.py`):**
     - Menggunakan `ssock.getpeercert(binary_form=True)` dan konversi PEM via `ssl.DER_cert_to_PEM_cert` pada fungsi `inspect_remote_ssl_certificate`.
     - Mengintegrasikan parser decoding standar `ssl._ssl._test_decode_cert` serta fallback CLI sistem `openssl x509 -enddate` untuk membaca masa berlaku sertifikat SSL remote internal, IP lokal, atau *self-signed* tanpa kegagalan verifikasi CA.
  4. **Eliminasi Kebocoran Subproses Zombi pada Prober ICMP Ping (`server/prober.py`):**
     - Menambahkan terminasi paksa `proc.kill()` dan penuaian asinkron `await proc.wait()` pada blok `asyncio.TimeoutError` dan `Exception` di fungsi `probe_icmp`.
     - Mencegah akumulasi proses ping defunct/zombi di sistem operasi saat probe timeout atau host target tidak merespons.
  5. **Penegakan Kepatuhan Zero-Dependency Agen Klien (`package/opt/pantau/agent/agent_pantau.py` & `agent/agent_pantau.py`):**
     - Menghapus ketergantungan impor pustaka eksternal `cryptography` pada fungsi `collect_ssl_certs`.
     - Menggantinya dengan decoding berbasis pustaka standar bawaan Python `ssl._ssl._test_decode_cert` dan fallback CLI sistem `openssl x509`, menjamin agen berjalan 100% mandiri pada instalasi Linux minimalis tanpa paket Python eksternal.
  6. **Kelengkapan Dependensi Server (`server/requirements.txt`):**
     - Mendaftarkan paket `httpx==0.28.1` dan `qrcode==8.2` pada berkas `requirements.txt`.
     - Memastikan instalasi dan pembaruan lingkungan produksi via `install-server.sh` berjalan sukses tanpa kendala impor yang hilang.
  7. **Sinkronisasi Penerusan Kode Keluar Wrapper APT (`package/usr/local/sbin/pantau-apt`):**
     - Memperbarui seluruh pemanggilan pty cangkang dari `/usr/bin/script -qfc` menjadi `/usr/bin/script -qfec` (penambahan opsi `-e`).
     - Menyinkronkan wrapper paket dengan konstanta agen `PANTAU_APT_SCRIPT_BODY` dan endpoint unduh wrapper pusat `/api/agent/wrapper/pantau-apt` agar kode keluar error APT diteruskan secara transparan.
  8. **Pembersihan dan Standarisasi Konstanta Agen Klien (`package/opt/pantau/agent/agent_pantau.py` & `agent/agent_pantau.py`):**
     - Menstandarisasi penamaan konstanta wrapper perintah dari prefiks `PANTUAN_` menjadi `PANTAU_` (`PANTAU_RESTART`, `PANTAU_FIREWALL`, `PANTAU_USER_CMD`, `PANTAU_CRON_CMD`, `PANTAU_SSL_CMD`, `PANTAU_APT_CMD`, `PANTAU_HISTORY_CMD`, `PANTAU_HOST_CMD`, `PANTAU_SHELL_CMD`).
     - Menghapus kode mati `PANTUAN_UNAME = "agent_pantau"`.
  9. **Sinkronisasi Izin Granular RBAC Seeder (`server/seed_admin.py`):**
     - Menghubungkan konstanta `ALL_OPERATOR_PERMS` secara langsung ke `list(OPERATOR_PERMISSIONS.keys())` dari `security_auth.py`.
     - Memastikan seluruh 16 izin granular operator (termasuk `can_audit`, `can_manage_users`, dan `can_probing`) terdaftar secara otomatis saat akun operator di-seed via CLI.
  10. **Sinkronisasi Penuh Skema Basis Data & Pelacakan Git (`database/schema.sql` & `.gitignore`):**
      - Memperbarui `database/schema.sql` dengan dump skema resmi MariaDB 16 tabel yang sinkron dengan `server/models.py` (melengkapi 3 tabel `probe_targets`, `probe_logs`, `system_settings` dan 24+ kolom yang tertinggal).
      - Menyesuaikan `.gitignore` dengan aturan negasi `!/agent/agent_pantau.py` agar berkas agen klien di root direktori tetap terlacak oleh sistem version control git tanpa menyertakan artefak lawas.
  11. **Penyematan Indikator Proxmox HA Dasbor & Optimasi Regex ANSI Stream (`server/templates/dashboard.html` & `server/main.py`):**
      - Menyematkan lencana visual Proxmox HA (`badge badge-ha` kuning 7.5px) pada tampilan tabel, tampilan kartu, dan siklus pembaruan dinamis JavaScript di dasbor utama (`dashboard.html`).
      - Mengoptimalkan fungsi sanitasi stream terminal `_clean_terminal` dari iterasi penggantian string kuadratik $O(N^2)$ menjadi ekspresi reguler linier $O(N)$ via `_TERM_STASH_RE.sub()`, melenyapkan lonjakan CPU dan beban memori saat streaming log instalasi APT besar.

## Versi 4.8.18

- **Tipe Rilis:** Standarisasi Ikon Upgrade Paket OS & Eliminasi Ikon Caret Ambigu (*OS Package Upgrade Semantic Icon & Visual Cohesion*)
- **Fokus Utama:** Mengeliminasi seluruh penggunaan ikon caret/chevron tunggal `[ ^ ]` pada tombol aksi Upgrade Paket OS yang ambigu dan tidak mencerminkan fungsi peningkatan versi perangkat lunak:
  1. **Penggantian Ikon Tombol Upgrade OS Header (`apt-upgrade-btn` di `services.html`):**
     - Mengganti ikon caret garis tunggal `polyline points="18 15 12 9 6 15"` (`^`) menjadi ikon semantik `arrow-up-circle` (`<circle cx="12" cy="12" r="10"></circle><polyline points="16 12 12 8 8 12"></polyline><line x1="12" y1="16" x2="12" y2="8"></line>`), menghadirkan simbol panah vertikal tegas dalam lingkaran lencana yang secara universal merepresentasikan upgrade versi sistem.
     - Memperbarui teks tooltip tombol menjadi *"Tingkatkan paket OS yang tersedia (X pembaruan)"* dan aria-label menjadi *"Upgrade Paket OS"*, membedakannya secara tegas dari tombol *Update Repositori OS* di sebelahnya.
  2. **Harmonisasi Ikon Upgrade pada Modal & Tab Packages (`services.html`):**
     - Mengganti ikon caret pada tombol Upgrade modal proses APT (`apt-task-upgrade-btn`) dengan ikon `arrow-up-circle` yang identik.
     - Menyematkan ikon 3D `package` representatif pada judul kartu Tab Packages (`#tab-packages`) guna menegaskan identitas visual modul manajemen paket.
     - Memastikan seluruh tombol upgrade di seluruh aplikasi (`apt-upgrade-btn`, `btn-pkg-upgrade-all`, dan `upgradeSinglePkg`) kini menggunakan bahasa visual yang 100% seragam dan konsisten.

## Versi 4.8.17

- **Tipe Rilis:** Pemulihan Mandiri Otomatis Wrapper pantau-user & Titik Unduh Wrapper Pusat (*Self-Healing Wrapper & Central Wrapper API*)
- **Fokus Utama:** Mengatasi kendala eksekusi pemutusan sesi terminal SSH (`gagal: ERROR: Aksi tidak dikenal: 'terminate-session'`) akibat wrapper `/usr/local/sbin/pantau-user` yang usang pada server klien yang dipasang sebelum rilis v4.8.12:
  1. **Mekanisme Pemulihan Mandiri Wrapper (`agent_pantau.py`):**
     - Menyematkan kode sumber cangkang resmi wrapper bash `PANTAU_USER_SCRIPT_BODY` ke dalam agen Python klien.
     - Mengimplementasikan fungsi `ensure_pantau_user_updated(force: bool = False) -> bool` yang secara otomatis memeriksa keberadaan opsi `terminate-session` pada `/usr/local/sbin/pantau-user`. Jika wrapper belum mendukung atau terjadi galat penolakan aksi, agen akan langsung memperbarui berkas wrapper secara atomik melalui hak root langsung atau via wrapper `pantau-file` dengan izin akses `0750`.
     - Mengintegrasikan pemanggilan `ensure_pantau_user_updated()` pada saat booting agen (`main()`), pada saat siklus pembaruan OTA selesai (`_exec_update_agent`), dan pada saat pemanggilan aksi pengguna (`_exec_user_action`).
     - Menyematkan logika percobaan ulang otomatis (*auto-retry on outdated wrapper*): jika panggilan wrapper pertama menghasilkan galat `Aksi tidak dikenal`, agen secara instan memaksa pembaruan wrapper mandiri dan mengeksekusi ulang aksi tanpa perlu intervensi operator.
  2. **Penyediaan Titik Unduh Wrapper Pusat (`server/main.py`):**
     - Menambahkan endpoint REST API `@app.api_route("/api/agent/wrapper/{wrapper_name}")` yang memungkinkan klien atau skrip pemeliharaan mengunduh seluruh wrapper resmi (`pantau-user`, `pantau-apt`, `pantau-cron`, `pantau-file`, `pantau-firewall`, `pantau-history`, `pantau-host`, `pantau-restart`, `pantau-shell`, `pantau-ssl`) langsung dari dashboard dengan header validasi `X-Checksum-SHA256` dan `ETag`.

## Versi 4.8.16

- **Tipe Rilis:** Perombakan Semantik Menyeluruh Ikon & Tombol Aksi Antarmuka (*System-Wide Semantic Icon & Action Button Overhaul*)
- **Fokus Utama:** Mengeliminasi seluruh penggunaan ikon generik tambah `(+)`, ikon ambigu, dan ikon tidak representatif pada tombol-tombol aksi di seluruh ekosistem Pantau Server, menghadirkan antarmuka NOC yang ergonomis, intuitif, dan komunikatif:
  1. **Eliminasi Ambiguitas Ikon Tambah pada Tindakan Restriktif / Blokir IP (`services.html`):**
     - Mengganti ikon generik `(+)` pada tombol "Blokir IP" (`#btn-fw-block-modal`) yang membingungkan menjadi ikon perisai silang `shield-x` (`<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path><line x1="9.5" y1="9.5" x2="14.5" y2="14.5"></line><line x1="14.5" y1="9.5" x2="9.5" y2="14.5"></line>`) yang tegas merepresentasikan pemblokiran/penutupan akses jaringan.
     - Mengganti ikon tempat sampah (`trash-2`) pada aksi "Buka Blokir IP" (`submitFirewallUnblock`) baik pada template Jinja maupun rendering live polling JavaScript menjadi ikon gembok terbuka `unlock` (`<rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 9.9-1"></path>`), mencerminkan pembukaan akses firewall alih-alih penghapusan entitas.
  2. **Ikon Semantik Kontekstual untuk Setiap Penambahan Entitas (`services.html`, `servers.html`, `probing.html`):**
     - **Tambah Server (`servers.html` & `server_form.html`):** Mengganti `(+)` polos menjadi ikon rak server representatif (`server`).
     - **Tambah Layanan (`services.html`):** Mengganti `(+)` polos pada header tabel layanan menjadi ikon tumpukan layanan (`layers`).
     - **Tambah Tugas Cron (`services.html`):** Mengganti `(+)` polos pada header tabel cron menjadi ikon jam penjadwalan waktu (`clock`).
     - **Tambah Pengguna Sistem (`services.html` & `users.html`):** Mengganti `(+)` polos menjadi ikon pengguna berperingkat (`user-plus`).
     - **Tambah Lokasi SSL (`services.html`):** Mengganti `(+)` polos menjadi ikon folder berkas (`folder-plus`).
     - **Tambah Endpoint Probing (`probing.html`):** Mengganti `(+)` polos menjadi ikon bola dunia jaringan (`globe`).
     - **Promosi Port Aktif ke Layanan Pantau (`svgAddSvc` di `services.html`):** Mengganti `(+)` polos menjadi ikon detak telemetri (`activity`).
  3. **Penguatan Visual Tombol Modal & Form Aksi Sistem:**
     - Menghadirkan ikon semantik pada seluruh tombol submit modal: `layers` pada Modal Tambah Layanan, `zap` pada Modal Kelola Sinyal Proses, `shield-x` pada Modal Blokir IP, `user-plus` pada Modal Buat Pengguna, `clock` pada Modal Tambah Cron, `folder-plus` pada Modal Tambah SSL, dan `save` pada Modal Endpoint Probing.
     - Mengintegrasikan penanganan status pemrosesan asinkron (`btnText`) agar teks loading ("Membuat...") tidak menghapus ikon SVG tombol.
  4. **Pembaruan Ikon Visual File Manager & Autentikasi (`file_manager.html`, `users.html`, `login.html`, `login_2fa.html`):**
     - Mengganti entitas teks unicode kuno pada navigasi File Manager (`&larr;`, `&rarr;`, `&uarr;`, `&#8962;`, `&#8635;`, `&#9998;`) menjadi ikon vektor SVG modern (`arrow-left`, `arrow-right`, `arrow-up`, `home`, `rotate-cw`, `edit-2`).
     - Mengganti teks tombol polos `+ Folder Baru`, `+ Berkas Baru`, `Unggah Berkas`, dan `Tempel` pada bilah alat File Manager menjadi tombol ber-ikon semantik (`folder-plus`, `file-plus`, `upload`, `clipboard`).
     - Menyematkan ikon `shield`, `lock`, `unlock`, dan `trash-2` pada baris tabel pengguna (`users.html`), serta ikon `log-in` pada tombol Masuk dan `shield-check` pada tombol Verifikasi 2FA.

## Versi 4.8.15

- **Tipe Rilis:** Standarisasi Ikon Pemutusan Sesi Terminal Log-Out (*Session Disconnect Log-Out Icon Standardization*)
- **Fokus Utama:** Mengeliminasi ambiguitas visual pada tombol pemutusan sesi terminal SSH:
  1. **Penggantian Ikon Daya Menjadi Ikon Keluar / Putus Sesi (`services.html` & `user_activity.html`):**
     - Mengganti seluruh representasi ikon tombol pemutusan sesi (`terminate_session`) yang sebelumnya keliru menggunakan ikon tombol power (*standby/power-off*) menjadi ikon baku *log-out* (`<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line>`).
     - Mengeliminasi kekhawatiran operator bahwa tombol tersebut akan mematikan sistem host fisik, dan memperjelas fungsi aksi murni sebagai terminasi sesi terminal login (*kick / log out*).
     - Menstandarisasi ikon baru pada seluruh titik interaksi: Tabel Akun Pengguna, Bilah Tindakan Aktivitas Pengguna, dan Tombol Cepat Insiden Masalah Sesi Remote.

## Versi 4.8.14

- **Tipe Rilis:** Relokasi Tombol Putus Sesi ke Kolom Tindakan Sesuai Standar UI/UX (*Session Disconnect Action Button Relocation to Dedicated Actions Column*)
- **Fokus Utama:** Menegakkan prinsip tata letak data tabel (*table UI/UX best practice*) dan eliminasi clutter visual:
  1. **Relokasi Tombol Aksi Tabel Akun Pengguna (`services.html`):**
     - Memindahkan tombol aksi putus paksa sesi terminal SSH dari kolom data "Sesi Aktif" ke kolom resmi "Tindakan".
     - Kolom data "Sesi Aktif" kini murni menyajikan data status koneksi berupa teks dan badge badge-muted (`pts/0 @ IP`) tanpa tombol interaktif yang menyusup di dalam sel data.
     - Kolom "Tindakan" kini menjadi pusat kontrol tunggal yang menampung tombol *Rincian*, tombol merah *Putus Sesi* (`svgPower`), tombol *Kunci/Buka Kunci*, dan tombol *Hapus Pengguna* secara rapi dan seragam, baik pada initial render Jinja maupun siklus live polling JavaScript.
  2. **Penyempurnaan Halaman Aktivitas Pengguna (`user_activity.html`):**
     - Mensterilkan kartu ringkasan metrik "Sesi Aktif" dari tombol inline, menyajikannya murni sebagai kartu statistik jumlah dan daftar terminal.
     - Menempatkan tombol aksi pemutusan sesi terminal aktif secara elegan pada area bilah tindakan atas (*topbar action area*).

## Versi 4.8.13

- **Tipe Rilis:** Perbaikan Evaluasi Izin Pengayaan Insiden Sesi Remote (*Remote Session Incident Permission Scope Bugfix & HTTP 500 Elimination*)
- **Fokus Utama:** Mengeliminasi galat fatal internal HTTP 500 yang terjadi saat merender halaman insiden/dasbor yang memuat sesi SSH remote:
  1. **Perbaikan Cakupan Variabel Izin Pengguna (`server/main.py`):**
     - Mengeliminasi galat `NameError: name 'can_services' is not defined` pada fungsi `_enrich_problems_for_ui`.
     - Menginisialisasi variabel evaluasi izin `can_term` secara aman dari parameter `user_or_role` (memeriksa izin `can_users_sys`, `can_manage_servers`, `can_services`, atau status master admin jika bertipe User model, serta fallback ke peran string `admin`/`master_admin`).
     - Menjamin status aksi tombol perbaikan insiden (`terminate_session` untuk operator berwenang atau `inspect_sessions` untuk viewer) terisi secara deterministik tanpa melempar eksepsi.

## Versi 4.8.12

- **Tipe Rilis:** Akurasi Riwayat Login Modern & Pemutusan Sesi SSH Terpusat (*Modern Linux Login Telemetry Multi-Source Ingestion & Centralized Remote Session Termination*)
- **Fokus Utama:** Mengatasi kendala angka *Login Sukses: 0* pada server Linux modern tanpa `rsyslog` serta menyediakan kapabilitas mitigasi dan terminasi sesi terminal SSH langsung dari dasbor monitoring:
  1. **Multi-Source Telemetri Login Linux Modern (`agent_pantau.py`):**
     - Mengatasi hilangnya file fisik `/var/log/auth.log` pada rilis Linux mutakhir (seperti Ubuntu 24.04 LTS Noble dan Debian 12) yang tidak memasang `rsyslog` secara bawaan.
     - Mengintegrasikan pembacaan multi-lapis:
       - **Sesi Aktif (`_parse_who()` / utmp):** Menjamin seluruh sesi pengguna yang sedang tersambung seketika tercatat sebagai `sukses` dan `aktif`.
       - **Akuntansi Login Linux (`last -n 80 -F` / wtmp):** Mengekstrak rekaman riwayat sesi login lengkap dengan timestamp, terminal TTY, dan IP asal.
       - **Log Otentikasi Terperinci (`systemd-journald` / fallback):** Mengekstraksi event `Accepted`, `Failed password`, `Invalid user`, dan eksekusi perintah `sudo` langsung dari journald tanpa bergantung pada file log tradisional.
     - Menyempurnakan pembacaan unit log `AUTH` dan `SYSLOG` dengan fallback transparan ke `journalctl`.
  2. **Aksi Pemutusan Paksa Sesi SSH (*Force Session Termination*):**
     - Menambahkan aksi `terminate-session <tty>` pada wrapper `/usr/local/sbin/pantau-user` dengan sanitasi regex ketat `^(pts/[0-9]+|tty[0-9]+)$` yang mengeksekusi `pkill -9 -t "$TTY"` dan `fuser -k -9 "/dev/$TTY"`.
     - Mengembangkan endpoint pusat `POST /servers/{sid}/system-users/terminate-session` dan `/api/servers/{sid}/sessions/terminate` dengan pemeriksaan izin hak akses (`can_users_sys` / `can_manage_servers`).
     - Mencatat audit log terstruktur berlabel "Putus Sesi Terminal" pada kategori Autentikasi & Akun.
  3. **Antarmuka Interaktif Pengelolaan Sesi Terminal (UI):**
     - **Tab Users (`#tab-akun`):** Menyajikan badge sesi aktif lengkap dengan tombol putus sesi cepat (`&times;`) pada tabel pengguna, baik saat initial render Jinja maupun siklus live polling JavaScript.
     - **Halaman Aktivitas Pengguna (`user_activity.html`):** Menampilkan rincian terminal sesi aktif pada kartu statistik dengan kontrol tombol pemutusan langsung, serta menjamin chip *Login Sukses* mencerminkan jumlah akurat.
     - **Tab Masalah (`#tab-masalah`):** Menyediakan tombol mitigasi cepat 1-klik berwarna merah (*Terminate Session*) pada baris insiden `ssh_active_session` untuk memutus akses remote seketika.

## Versi 4.8.11

- **Tipe Rilis:** Deteksi Cerdas Multi-Lapis Kontainer LXC & Eliminasi Status Baremetal Semu (*Multi-Layer LXC Container Auto-Detection & Pending Platform Baseline*)
- **Fokus Utama:** Mengatasi kesalahan deteksi platform server di mana kontainer LXC teridentifikasi sebagai Baremetal saat registrasi atau eksekusi agen:
  1. **Inspeksi Virtualisasi Multi-Lapis Bebas Izin Root (`agent_pantau.py`):**
     - Menambahkan heuristik pemindaian Proxmox LXCFS pada `/proc/mounts` dan `/proc/self/mountinfo` (`lxcfs`, `fuse.lxcfs`).
     - Menginspeksi hierarki cgroup `/proc/1/cgroup` dan `/proc/self/cgroup` (`/lxc/`, `lxc.payload`, `lxc.monitor`, `machine-lxc`).
     - Membaca profil AppArmor container `/proc/self/attr/current`.
     - Menyediakan eskalasi pembacaan virtualisasi `sudo -n systemd-detect-virt` pada daftar whitelist `/etc/sudoers.d/pantau-agent`.
  2. **Eliminasi Label Baremetal Prematur Saat Registrasi (`server/main.py` & template dasbor):**
     - Memperbaiki fallback `_get_hardware_specs_dict` dan `_classify_platform` saat server baru ditambahkan dan belum mengirimkan laporan telemetri pertama (`server.last_seen is None`).
     - Mengubah status default platform yang sebelumnya salah menampilkan *Baremetal* menjadi status informatif **Auto Deteksi (Menunggu Agen)** dengan badge abu-abu rapi bertuliskan `AUTO`.
  3. **Koreksi Retroaktif Berbasis Alokasi Storage Virtual (`server/main.py`):**
     - Menambahkan verifikasi rekonsiliasi disk: jika spesifikasi perangkat keras memuat perangkat penyimpanan bertipe `Virtual (LXC)` atau `Container Allocation`, platform secara otomatis dikoreksi menjadi `LXC Container` meskipun string DMI vendor/product menampilkan nama perangkat keras fisik server host (seperti Dell PowerEdge atau HPE ProLiant).

## Versi 4.8.10

- **Tipe Rilis:** Perbaikan Impor Modul SSL & Konfigurasi Handshake TLS Agen Klien (*Client Agent SSL Import Bugfix & Permissive TLS Opener Context*)
- **Fokus Utama:** Mengeliminasi crash fatal pada pemindaian kesehatan layanan agen klien (`run_health_check`):
  1. **Impor Modul Standar `ssl` (`package/opt/pantau/agent/agent_pantau.py` & `agent/agent_pantau.py`):**
     - Menambahkan impor eksplisit `import ssl` pada agen klien.
     - Mengeliminasi galat runtime `NameError: name 'ssl' is not defined. Did you forget to import 'ssl'` yang terjadi saat blok penanganan eksepsi `except ssl.SSLError as e:` dievaluasi ketika probe HTTP menguji socket layanan HTTPS/TLS.
  2. **Konteks SSL Handshake Permisif untuk Health-Check (`_HTTP_OPENER`):**
     - Mengonfigurasi `urllib.request.HTTPSHandler(context=ssl._create_unverified_context())` pada `_HTTP_OPENER` probe kesehatan.
     - Menjamin probe layanan web HTTPS pada `localhost`/IP internal (seperti port 443 atau 8443) dapat membaca kode status HTTP tanpa terhambat penolakan verifikasi sertifikat lokal/self-signed.

## Versi 4.8.9

- **Tipe Rilis:** Ekspansi Kapasitas Kolom Catatan Resolusi Insiden & Penuntasan Rollback Telemetri Klien (*Incident Resolution Note Capacity Expansion, Telemetry Rollback Elimination & POSIX Shell Command Hardening*)
- **Fokus Utama:** Mengeliminasi galat fatal HTTP 500 yang menyebabkan rollback berkala pada transaksi laporan telemetri agen klien (`POST /api/report`):
  1. **Ekspansi Skema Basis Data Kolom `resolved_note` (`server/models.py` & MariaDB DDL):**
     - Memperluas kapasitas kolom `resolved_note` pada tabel `server_problems` dari `VARCHAR(30)` menjadi `VARCHAR(100)`.
     - Mengeliminasi galat `pymysql.err.DataError: (1406, "Data too long for column 'resolved_note' at row 1")` saat resolusi otomatis insiden paket sistem APT menyetel nilai `"auto (upgrade selesai di klien)"` (31 karakter).
     - Menjamin seluruh transaksi pelaporan telemetri agen klien (`/api/report`), pembaruan versi agen di dasbor (`ServerExtras.agent_version`), snapshot metrik sistem (`SystemSnapshot`), dan penyelesaian insiden berjalan sukses tanpa kendala HTTP 500.
  2. **Sanitasi Komprehensif Catatan Resolusi Insiden (`server/main.py`):**
     - Menerapkan helper `_clean_str` dengan batas maksimum 100 karakter pada seluruh titik penugasan `resolved_note` (resolusi APT di klien, reset platform otomatis, resolusi manual oleh operator, dan penyelesaian pembaruan paket massal).
  3. **Penguatan Eksekusi Shell Perintah Update Agen Manual (`server/templates/services.html`):**
     - Membungkus alternatif unduh `curl` lokal dan fallback GitHub dengan tanda kurung `(...)` sebelum operator chaining `&& sudo systemctl restart agent_pantau.service`, memastikan prioritas eksekusi shell POSIX berjalan deterministik.

## Versi 4.8.8

- **Tipe Rilis:** Penyesuaian Sanitasi Panjang Catatan Resolusi Insiden Platform (*Platform Conflict Resolution Note Length Sanitization*)
- **Fokus Utama:** Memastikan integritas transaksi basis data saat pemulihan otomatis konflik platform:
  1. **Sanitasi String `resolved_note` (`server/main.py`):**
     - Membatasi panjang teks `prob.resolved_note` pada endpoint `POST /api/servers/{sid}/reset-platform-auto` menggunakan helper `_clean_str` agar tidak melebihi kapasitas kolom `VARCHAR(30)` pada skema tabel `server_problems`.
     - Mencegah timbulnya `pymysql.err.DataError: (1406, "Data too long for column 'resolved_note'")` ketika nama pengguna operator pengeksekusi reset dipetakan ke dalam riwayat penyelesaian insiden.

## Versi 4.8.7

- **Tipe Rilis:** Benteng Proteksi Konflik Platform & Rekonsiliasi Otomatis Kesalahan Input Operator (*Platform Mismatch Conflict Triage, Fail-Safe Storage & Form Dynamic Guidance*)
- **Fokus Utama:** Mengantisipasi kemungkinan terburuk dari kesalahan manusia (*human error*) saat operator mendaftarkan atau mengedit server dengan memilih opsi Fisik / Baremetal padahal server tersebut sebenarnya adalah Kontainer LXC atau Mesin Virtual (VM):
  1. **Fail-Safe Alokasi Storage & Kuota Kontainer LXC (`server/main.py`):**
     - Memperkuat logika fungsi `_get_hardware_specs_dict` agar selalu mengutamakan deteksi definitif agen (`virt == "LXC"`, `container=lxc`, atau `platform_type == "lxc"`).
     - Menjamin kuota virtual `rootfs` kontainer tetap diterapkan secara deterministik dan mencegah kebocoran disk host fisik (misalnya harddisk host Proxmox 7.6 TB) ke dalam antarmuka kontainer LXC meskipun operator salah menyetel override `baremetal`.
  2. **Deteksi Konflik Platform Otomatis (*Platform Mismatch Conflict Triage*):**
     - Memperkenalkan evaluasi otomatis insiden `platform_conflict` berkategori `Peringatan` (warning) pada fungsi `_problem_instances`.
     - Ketika operator menyetel platform manual yang bertentangan dengan hasil pemindaian riil agen (seperti menyetel Baremetal padahal agen mendeteksi VM KVM atau LXC Container), sistem secara otomatis memunculkan insiden dengan judul **"Konfigurasi Platform Server Tidak Sesuai"** pada kartu Insiden Terkini halaman utama dasbor.
     - Melengkapi insiden dengan payload konteks diagnostik dwibahasa (ID & EN) terstruktur yang memuat rincian server, tipe konfigurasi manual, tipe deteksi aktual agen, dampak teknis, rekomendasi penanganan, dan perintah inspeksi kernel (`systemd-detect-virt`).
  3. **Aksi Mitigasi 1-Klik Pemulihan Platform (`server/main.py` & `services.html`):**
     - Menyediakan endpoint API `POST /api/servers/{sid}/reset-platform-auto` yang aman, terverifikasi CSRF, dan ter-audit.
     - Menghadirkan tombol aksi langsung pada tabel rincian insiden yang memungkinkan operator menyinkronkan kembali konfigurasi platform ke "Auto Deteksi" hanya dengan satu kali klik tanpa perlu membuka form edit manual.
  4. **Panduan Visual Dinamis pada Formulir Server (`server_form.html`):**
     - Mempertahankan dan menegaskan opsi default dropdown sebagai `Auto Deteksi (Laporan Agen) — Direkomendasikan`.
     - Menampilkan teks bantuan dinamis real-time tepat di bawah pilihan dropdown: `(Server ini terdeteksi sebagai platform VM (KVM))` bila agen telah pernah terhubung dan melapor.
     - Menyematkan kotak peringatan interaktif visual berwarna kuning bila operator memilih opsi manual yang berkonflik dengan tipe platform yang dideteksi agen.

## Versi 4.8.6

- **Tipe Rilis:** Penuntasan Eksepsi Rollback Log Request APT, Pemulihan Timeout Sesi Menggantung, dan Penyempurnaan Error Parsing Modal (*APT Log Request Rollback Exception Fix, Stale Session Timeout Recovery & Modal Error Parsing Refinement*)
- **Fokus Utama:** Mengeliminasi bug kritis di mana tugas pembaruan repositori APT (`apt update` / `apt upgrade`) yang telah selesai dieksekusi secara sukses oleh agen malah berstatus gagal dengan pesan `[proses apt kedaluwarsa]` dan memunculkan toast potongan teks repositori mentah:
  1. **Penanganan Eksepsi `UnboundLocalError` pada Sinkronisasi Insiden APT (`server/main.py`):**
     - Memperbaiki bug kritis pada endpoint `POST /api/logs/{rid}/result` di mana variabel `prob` dievaluasi pada cabang `else:` (`if prob:`) sebelum di-query dari basis data, memicu `UnboundLocalError: cannot access local variable 'prob' where it is not associated with a value`.
     - Memastikan `prob` di-query secara benar dari tabel `ServerProblem` untuk kunci `apt_updates` sebelum dilakukan modifikasi atau inisialisasi entitas baru.
  2. **Isolasi Transaksi Database & Komit Permanen Status Tugas (`server/main.py`):**
     - Memisahkan penyimpanan status empiris `LogRequest` dari operasi pembaruan sekunder (`ServerExtras`, `ServerProblem`, `AuditLog`).
     - Melakukan `db.commit()` seketika pada `LogRequest` agar status tugas yang dilaporkan agen (`success` atau `failed`) tersimpan permanen dan terlindungi dari pembatalan transaksi (`db.rollback()`) bila terjadi kegagalan kalkulasi turunan.
  3. **Penyempurnaan Pembersihan Sesi Kadaluwarsa & Pengambilan Tugas Aktif Terkini (`server/main.py`):**
     - Mengubah pengurutan `apt_run` pada `api_server_overview` dari `.order_by(LogRequest.created_at)` (mengambil tugas tertua) menjadi `.order_by(LogRequest.id.desc())` (mengambil tugas aktif terbaru).
     - Menambahkan loop pembersihan komprehensif (*garbage collection*) untuk seluruh permintaan APT menggantung yang melebihi batas toleransi waktu tanpa memblokir pemantauan tugas baru yang sedang berjalan.
  4. **Sinkronisasi Reaktif Insiden `apt_updates` pada Laporan Berkala Agen (`server/main.py`):**
     - Memperluas pembaruan entitas `ServerProblem` ("apt_updates") langsung pada endpoint `POST /api/report` ketika agen mendeteksi jumlah paket yang butuh pembaruan (`upgradable > 0`), menjamin konsistensi relasional penuh saat operator menjalankan upgrade langsung via terminal klien.
  5. **Standardisasi Output Terstruktur JSON pada Agen Klien (`agent_pantau.py`):**
     - Agen kini selalu mengembalikan muatan terstruktur JSON (`type`, `output`, `apt`, `error`, `rc`) baik dalam kondisi berhasil, peringatan repositori (`rc=100`), maupun kegagalan fatal.
     - Menghindarkan pengiriman teks terminal mentah tanpa struktur yang membingungkan lapisan antarmuka.
  6. **Penyempurnaan Ekstraksi Pesan Kesalahan pada Antarmuka Modal (`services.html`):**
     - Mengeliminasi anomali tampilan di mana baris awal repositori (`Hit:1 http://...`) terpotong dan dijadikan judul pesan error pada modal serta notifikasi *toast*.
     - Menyediakan parser ekstraksi cerdas: memprioritaskan properti `error` JSON, menangkap keterangan kedaluwarsa batas waktu secara presisi, serta mengekstrak baris kesalahan eksplisit (`E: ...`, `Error: ...`) dengan pesan fallback yang elegan dan komunikatif.

## Versi 4.8.5

- **Tipe Rilis:** Arsitektur Keterhubungan Relasional Menyeluruh dan Sinkronisasi Reaktif Dua Arah (*Omnidirectional Relational Integrity & Reactive Dual-Directional Synchronization Architecture*)
- **Fokus Utama:** Membangun integritas relasional enterprise pada seluruh alur monitoring dan status sistem, menjamin kesetaraan respon ketika tindakan terjadi via Web Dashboard maupun langsung di sisi server klien (via SSH/konsol lokal):
  1. **Deteksi Reaktif Perubahan Paket di Server Klien (*File State Watcher*):**
     - Mengimplementasikan `_get_pkg_state_signature()` pada Agen Pantau (`agent_pantau.py`) untuk memantau stempel waktu modifikasi (*mtime*) `/var/lib/dpkg/status` dan `/var/lib/apt/lists`.
     - Kapan pun operator menjalankan `apt install`, `apt upgrade`, atau `apt remove` langsung di terminal SSH klien, agen seketika mendeteksi perubahannya dalam waktu <5 detik tanpa menunggu siklus lambat 30–60 detik, dan menyematkan flag `packages_changed` ke server pusat.
  2. **Data-Binding Reaktif Antarmuka Tab Packages (`services.html`):**
     - Memperkenalkan fungsi sentral `syncPackagesTabApt(count, packages)` yang terikat langsung ke siklus live-polling `/api/servers/{id}/system`.
     - Kapan pun paket di-upgrade (baik dari tombol dashboard maupun langsung di terminal klien), badge tab `#tab-packages-badge`, badge header `#pkg-upg-badge`, peta `_upgMap`, baris tabel paket, dan tombol hero `#apt-upgrade-btn` otomatis sinkron seketika ke status mutakhir tanpa perlu me-reload peramban (F5).
     - Mengeliminasi jebakan logika `aptArmed` yang sebelumnya memaksa menimpa status paket 0 kembali ke angka lama.
  3. **Penyelarasan Masalah dan Inventaris Paket Terpasang Otomatis (`server/main.py`):**
     - Ketika laporan status paket mutakhir (0) diterima, insiden `apt_updates` di tabel `ServerProblem` otomatis diselesaikan (*resolved*).
     - Server secara otomatis menjadwalkan tugas latar belakang `PKG_LIST` ketika mendeteksi flag `packages_changed` agar inventaris `extras.installed_packages` tetap akurat mencatat paket baru yang dipasang di host klien.
  4. **Pembaruan Dinamis Tabel Armada (`servers.html`):**
     - Menyematkan ID dinamis `srv-apt-{{ srv.id }}` dan fungsi pembaruan JavaScript live polling pada kolom *OS Update* di halaman `/servers` (beralih live antara badge kuning "X paket" dan badge hijau "mutakhir").
  5. **Auto-Discovery Layanan Aktif Baru dari Socket Terbuka:**
     - Menghubungkan soket pendengar aktif pada tab *Ports* dengan fungsi modal `openAddSvcModal()` terisi otomatis, memungkinkan penambahan daemon/port baru yang baru saja diinstal di server klien ke pemantauan layanan utama (*Services*) hanya dengan satu klik.

## Versi 4.8.4

- **Tipe Rilis:** Perbaikan Fungsi Kunci Terminal dan Pemutusan Sesi Web Shell (*Web Terminal Locking Workflow & Session Severing Bugfix*)
- **Fokus Utama:** Menyelesaikan kendala antarmuka web terminal macet (*stuck*) saat operator mengklik tombol konfirmasi "Kunci Terminal & Putus Sesi?":
  1. **Eliminasi Galat Runtime JavaScript (`ReferenceError: finishUpgradeSession is not defined`):**
     - Menghapus pemanggilan fungsi *legacy* `finishUpgradeSession()` yang tidak terdefinisi di dalam `proceedLockTerminalSession()` pada berkas `server/templates/services.html`.
     - Sebelumnya, pengecualian (*unhandled exception*) ini menghentikan eksekusi kode JavaScript sebelum permintaan POST ke API `/api/servers/{sid}/terminal/lock` dikirim, menyebabkan koneksi WebSocket tidak tertutup, hitung mundur masa sewa tidak berhenti, dan jendela terminal tidak tersembunyi.
  2. **Penguatan Penanganan Respons & Notifikasi Toast:**
     - Menambahkan penanganan respons HTTP yang komprehensif pada pemanggilan endpoint `/api/servers/{sid}/terminal/lock` dengan notifikasi *toast* interaktif berbahasa Indonesia baku ("Terminal berhasil dikunci dan sesi koneksi diputus.") dan bahasa Inggris ("Terminal locked and session disconnected.").
     - Menjamin penutupan WebSocket (`term.close()`), penyembunyian antarmuka terminal (`term.hideViewOnly()`), pembaruan status ke "Terminal telah dikunci", penghentian timer sewa (`stopTermLeaseCountdown()`), dan penonaktifan banner sesi aktif (`setTerminalSessionActive(false)`) tereksekusi secara deterministik.

## Versi 4.8.3

- **Tipe Rilis:** Deteksi Cerdas Kegagalan Repositori APT dan Eliminasi Alarm Sukses Palsu (*APT Repository Failure Intelligent Detection & False Success Alarm Elimination*)
- **Fokus Utama:** Mengeliminasi anomali pelaporan sukses palsu (`✔ Selesai dengan sukses`) ketika `apt update` gagal mengunduh repositori karena kesalahan DNS (*Temporary failure resolving*) atau kegagalan jaringan:
  1. **Penguatan Wrapper Eksekusi Terminal (`script -qfec`):**
     - Memperbaiki wrapper `/usr/local/sbin/pantau-apt` dari `/usr/bin/script -qfc` menjadi `/usr/bin/script -qfec` (penambahan opsi `-e`), memastikan kode keluar (*exit status code*) dari sub-proses APT diteruskan secara akurat dan tidak disamarkan menjadi 0.
  2. **Deteksi Cerdas Pola Kegagalan Unduh Repositori pada Agen Klien (`agent_pantau.py`):**
     - Menambahkan inspeksi string kegagalan pada output APT (`W: Some index files failed to download`, `W: Failed to fetch`, `Temporary failure resolving`, `Could not resolve`, `Connection refused`).
     - Menyematkan diagnosa spesifik (`has_fetch_err`, `fetch_err_reason`) ke dalam payload hasil eksekusi agar dasbor memahami secara persis penyebab kegagalan (misalnya resolusi DNS atau penolakan koneksi jaringan).
  3. **Penyempurnaan Penanganan Modal & Status Antarmuka Dasbor (`services.html`):**
     - Menghapus penambahan mutlak string hijau `✔ Selesai dengan sukses` bila ditemukan kegagalan pengunduhan indeks.
     - Memperkenalkan status `warning` pada modal tugas APT dengan indikator visual kuning (`⚠ Selesai dengan peringatan`) yang menampilkan alasan kegagalan secara transparan.
     - Menghindari klaim keliru "Semua paket OS sudah mutakhir" ketika pembaruan repositori gagal, serta memberikan catatan bahwa data paket yang tampil merupakan data cache lama.
  4. **Proteksi Integritas Timestamp Terakhir Pembaruan (`main.py`):**
     - Mencegah pembaruan `apt_last_update` menjadi waktu sekarang jika proses pembaruan repositori gagal mengunduh indeks, mempertahankan keakuratan riwayat pemeriksaan terakhir.

## Versi 4.8.2

- **Tipe Rilis:** Reduksi Ukuran Teks IP dan Standarisasi Badge Indikator Warna Berukuran Kecil pada Seluruh Tabel (*IP Text Size Reduction & Unified Small Colored Indicator Badges Across All Fleet Tables*)
- **Fokus Utama:** Mengoptimalkan kepadatan visual dan konsistensi representasi warna status pada seluruh tabel monitoring NOC:
  1. **Reduksi Teks Alamat IP Menjadi Kecil (9.5px Monospace):**
     - Mengubah ukuran tipografi teks alamat IP pada seluruh tabel armada (`.copyable-ip`, `.tbl-ip-wrap`) menjadi `9.5px` monospace.
     - Menjadikan alamat IP terlihat rapi, bersih, dan sekunder dibandingkan nama host tanpa mengurangi fungsionalitas salin cepat satu kali klik.
  2. **Standarisasi Seluruh Indikator Warna Menjadi Berukuran Kecil (8px):**
     - Memperkecil seluruh teks badge berstatus warna (seperti `ONLINE` hijau, `OFFLINE` merah, `PEMELIHARAAN` kuning, `NIHIL` hijau, `TIER-1/2/3`, badge platform `VM (KVM)`, `LXC`, `BAREMETAL`, dan tingkat keparahan insiden) menjadi `8px` dengan padding `0.5px 4.5px`, font-weight `700`, dan letter-spacing proporsional.
     - Rasional desain: Warna badge telah secara visual mengomunikasikan status dengan sangat jelas kepada operator (hijau = normal/online/nihil, merah = kritis/offline, oranye = gawat, kuning = peringatan, biru = info). Teks kecil mempertahankan kepadatan informasi tinggi dan mencegah tabel terlihat penuh/membingungkan operator.
  3. **Penyempurnaan Badge Pill Angka Insiden (`.badge-count`):**
     - Menstandarisasi counter angka insiden (`1`, `2`, `3`...) menjadi mini pill/lingkaran kompak (`min-width: 14px`, `height: 14px`, `font-size: 8px`, `border-radius: 7px`) yang estetis dan rapi.
  4. **Sinkronisasi Total Jinja Template & JavaScript Live Polling Loop:**
     - Menghilangkan anomali lompatan font (*font-size jump*) saat siklus live polling telemetri masuk pada dasbor utama (`dashboard.html`) dan daftar server (`servers.html`), mengunci konsistensi ukuran 8px secara permanen.

## Versi 4.8.1

- **Tipe Rilis:** Penataan Ulang Kolom Platform / IP Vertikal Proporsional pada Mode Standar Dasbor, dan Preservasi Total Mode Kompak (*Standard Mode Dashboard Platform / IP Vertical Layout & Total Compact Mode Preservation*)
- **Fokus Utama:** Menyempurnakan keterbacaan data armada pada kartu Status & Kinerja dasbor utama (`dashboard.html`):
  1. **Penataan Vertikal Dua Baris Kolom Platform / IP Mode Standar:**
     - Mengubah judul kolom dari *IP & Platform* menjadi **Platform / IP** pada Mode Standar agar selaras dengan hierarki konten sel.
     - Menyusun isi sel menjadi dua baris vertikal rapi: Baris 1 menampilkan badge jenis platform (misal `VM (KVM)`, `LXC Container`, atau `Baremetal`), dan Baris 2 menampilkan alamat IP host (`172.30.1.40`) yang dapat disalin secara instan.
     - Penataan dua baris ini menciptakan proporsionalitas dan keseimbangan vertikal yang harmonis dengan kolom CPU, RAM, dan Penyimpanan (Storage) yang juga berformat dua baris.
  2. **Preservasi Total Tata Letak Mode Kompak Tanpa Perubahan:**
     - Menjaga integritas Mode Kompak secara ketat (`jangan ubah apapun pada mode kompak`).
     - Pada Mode Kompak, tabel tetap mempertahankan judul *IP & Platform*, tata letak satu baris horizontal rapat (`flex-direction: row; line-height: 1; height: 25px`), dan keseragaman ukuran font tanpa ada pergeseran visual.
  3. **Integritas Tabel Lain Bebas Disrupsi:**
     - Mempertahankan tabel-tabel satu baris lainnya (`servers.html`, `problems.html`, `services.html`, dan `profile.html`) tetap pada format aslinya yang bersih, proporsional, dan elegan tanpa pemecahan baris yang tidak perlu.

## Versi 4.8.0

- **Tipe Rilis:** Eliminasi Tombol Ubah Sandi pada Kartu Identitas, Integrasi Edit Akun Mandiri Terpadu via Tabel Pengguna, dan Penyederhanaan Tombol Simpan (*Account Card Password Action Elimination, Unified Self-Service Edit via User Table, and Streamlined Modal Save Controls*)
- **Fokus Utama:** Menyederhanakan dan merapikan antarmuka manajemen pengguna sesuai standar UI/UX profesional:
  1. **Eliminasi Tombol "Ubah Kata Sandi Saya" pada Kartu Identitas (`profile.html`):**
     - Menghapus tombol redundan "Ubah Kata Sandi Saya" dari panel kartu *Informasi Identitas & Status*. Panel kini murni menyajikan ringkasan identitas, peran, sesi aktif, dan wewenang pengguna tanpa tombol aksi yang membingungkan.
     - Mengubah label tab personal non-pengelola dari "Profil & Hak Akses Saya" menjadi "Profil & Hak Akses" yang lebih formal dan baku.
  2. **Integrasi Edit Akun Mandiri Terpadu (Username & Kata Sandi) via Tombol Edit Tabel (`profile.html` & `main.py`):**
     - Tombol **Edit** pada baris akun yang sedang login di tabel pengguna (`#users-table`) menjadi satu-satunya titik kontrol (*single point of entry*) untuk pembaruan kredensial pribadi.
     - Membuka modal dialog **Edit Akun: [username]** dengan ikon pensil standar, yang memungkinkan pengubahan username dan/atau penggantian kata sandi dengan validasi kata sandi saat ini (kata sandi lama) demi keamanan sesi.
     - Menjadikan kolom kata sandi baru bersifat opsional bila operator hanya bermaksud mengubah username.
     - Endpoint backend `POST /users/{uid}/edit` diperkuat untuk memvalidasi kata sandi saat ini pada akun sendiri saat mengubah username atau password, memastikan konsistensi dan integritas data.
  3. **Penyederhanaan Label Tombol Konfirmasi Menjadi "Simpan":**
     - Menyederhanakan label tombol submit pada modal edit akun mandiri dari *"Simpan Kata Sandi Baru"* menjadi **"Simpan"**.
     - Menyederhanakan label tombol submit pada modal edit akun staf dari *"Simpan Perubahan"* menjadi **"Simpan"** demi konsistensi visual dan kemudahan operasional NOC.

## Versi 4.7.9

- **Tipe Rilis:** Penyatuan Terpadu Manajemen Pengguna & Keamanan Kredensial, Eliminasi Tab Berlebih, Penegasan Alur Ubah Kata Sandi Pribadi vs Reset Sandi Staf, dan Penegakan Akun Tunggal Master Admin (*Unified User & Access Management UI, Tab Redundancy Elimination, Strict Self-Service vs Administrative Password Reset Segregation, and Enforced Single Master Admin Topology*)
- **Fokus Utama:** Menyempurnakan alur operasional manajemen akun pengguna dan keamanan kredensial sesuai hierarki RBAC 3-tier:
  1. **Penyatuan Halaman Profil Menjadi Tab Terpadu Manajemen Pengguna (`profile.html`):**
     - Mengeliminasi tab terpisah "Akun Saya" yang membuat navigasi ganda dan tidak efisien bagi administrator.
     - Memindahkan kartu "Informasi Identitas & Status" serta kartu "Autentikasi Dua Langkah (2FA / TOTP)" akun aktif ke bagian atas tab Manajemen Pengguna dalam format grid 2 kolom berkepadatan tinggi (*high density*).
     - Menampilkan wewenang operasional aktif dan status 2FA secara seketika tanpa perlu berpindah tab.
     - Bagi peran Operator tanpa izin kelola pengguna, halaman otomatis beradaptasi menampilkan profil pribadi dan pengaturan kredensial tanpa tabel pengguna lain.
  2. **Pemisahan Tegas Alur Ubah Kata Sandi Pribadi vs Reset Kata Sandi Staf:**
     - Tombol **Edit** pada baris akun yang sedang login (`u.id == user.id`) kini membuka modal khusus **Ubah Kata Sandi Saya** yang mewajibkan verifikasi kata sandi saat ini (kata sandi lama), kata sandi baru, dan konfirmasi kata sandi baru. Menghilangkan celah bypass kata sandi lama pada akun sendiri.
     - Tombol **Edit** pada baris akun pengguna lain (`u.id != user.id`) membuka modal **Edit Akun & Hak Akses** yang berfokus pada pendelegasian peran, wewenang operator, status akun, serta opsi **Reset Kata Sandi Pengguna (Admin Override)** dengan konfirmasi kata sandi baru tanpa menanyakan kata sandi lama milik staf tersebut.
  3. **Penegakan Aturan Tunggal Master Admin & Pembersihan Akun Sisa Pengujian:**
     - Mengidentifikasi dan menghapus secara permanen akun-akun sisa pengujian sebelumnya (`test_operator` dan `admin`) dari basis data beserta seluruh sesinya.
     - Memastikan kepatuhan total prinsip *least privilege* dengan hanya 1 akun Master Admin resmi di sistem (`master-admin`).

## Versi 4.7.8

- **Tipe Rilis:** Reduksi Tipografi Tabel Non-Dasbor 2 Tingkat, Keseragaman Mutlak Tipografi Mode Dasbor (Standar vs Kompak), dan Optimalisasi Ruang Tabel NOC Dinamis (*Non-Dashboard Table 2-Step Typography Reduction, Strict Dashboard Typography Mode Parity, and Dynamic High-Density NOC Table Spacing*)
- **Fokus Utama:** Menyelesaikan kebutuhan efisiensi ruang dan keterbacaan data operasional pada seluruh tabel sistem tanpa membuang ruang horizontal maupun vertikal:
  1. **Reduksi 2 Tingkat Ukuran Font Tabel Non-Dasbor:**
     - Menurunkan ukuran font dasar seluruh tabel selain tabel dasbor armada (`servers.html`, `problems.html`, `services.html`, `users.html`, `user_activity.html`, `logs.html`, `audit.html`, `probing.html`, `file_manager.html`, dan `profile.html`) sebesar 2 level (dari 12px/12.5px ke 9.5px–10.5px untuk body dan 9.5px untuk header).
     - Menyesuaikan padding sel tabel menjadi lebih kompak (padding 3.5px–5px) sehingga data dapat ditampilkan lebih padat, rapi, dan efisien tanpa adanya kolom yang saling menimpa (*zero overlapping*).
  2. **Keseragaman Mutlak 100% Tipografi Mode Standar & Mode Kompak Dasbor (`dashboard.html`):**
     - Menghapus seluruh override ukuran font pada `.tbl-compact` (`th`, `td`, `strong.mono`, `.badge`, `.copyable-ip`) sehingga ukuran font antara Mode Standar dan Mode Kompak sepenuhnya identik matematis (11.5px untuk header, 12px untuk cell, 12.5px untuk hostname, 12px untuk nilai metrik, 9px untuk badge, 11.5px untuk IP dan uptime).
     - Mode Kompak kini hanya memodifikasi padding baris (`padding: 2px 6px` vs `5px 8px`), tinggi baris tetap (`height: 25px`), dan menyembunyikan subline metrik (`.tbl-metric-subline`), memastikan tidak ada lonjakan ukuran font saat operator berpindah mode.
  3. **Efisiensi Ruang Tabel Dinamis & Responsif:**
     - Memastikan seluruh kontainer tabel dibungkus dengan scroll horizontal dinamis (`overflow-x: auto`) agar tidak merusak tata letak dasbor pada resolusi viewport terbatas.
     - Kolom konten utama (deskripsi insiden, perintah, panduan solusi) menggunakan alokasi proporsional fleksibel dengan `min-width` dan `word-break: break-word`.
     - Standardisasi paginasi tabel sekunder dengan default limit 10 baris dan penonaktifan paginasi otomatis apabila data kurang dari 5 baris.

## Versi 4.7.7

- **Tipe Rilis:** Penyempurnaan Visual Universal Antarmuka NOC, Koreksi Proporsi Kolom & Tipografi Tabel, Eliminasi Indikator Ganda pada Tab Bar, Standardisasi Paginasi 10 Baris, dan Pemisahan Semantik Ikon Tindakan (*Universal NOC Density Refinement, Table Typography & Proportion Optimization, Tab Double-Indicator Elimination, Universal 10-Row Pagination Threshold & Distinct Action Icon Semantics*)
- **Fokus Utama:** Menyelesaikan secara tuntas 14 anomali visual, inkonsistensi tata letak, dan perubahan antarmuka yang dikeluhkan pengguna:
  1. **Standardisasi Ukuran Jejeran Tombol Tindakan Header Rincian Server (`services.html`):**
     - Mempertahankan susunan dan posisi tombol tindakan di bilah atas (*topbar*) halaman rincian server tanpa pergeseran tata letak.
     - Menyeragamkan dimensi tombol Edit, Hapus, dan Kembali ke Daftar Server ke ukuran NOC kompak standar (`height: 26px; padding: 4px 8px; font-size: 11px`).
  2. **Relokasi Indikator Identitas Server ke Baris Khusus di Bawah Spesifikasi Singkat (`services.html`):**
     - Memisahkan elemen identitas server (badge Grup, proteksi Proxmox HA, badge Jaringan Terisolasi, badge tag, dan chip catatan ringkas) dari spesifikasi sistem operasi (`.hero-meta-sys`).
     - Menempatkan seluruh elemen identitas pada baris tersendiri (`.hero-tags-bar`) tepat di bawah spesifikasi sistem operasi dengan penataan vertikal yang rapi.
  3. **Penataan Proporsional Kolom Tabel Status Masalah (`services.html` & `base.html`):**
     - Mengubah tabel `#probtable` menjadi `table-layout: fixed; width: 100%;` untuk mencegah kolom Kejadian meregang secara berlebihan pada resolusi layar lebar.
     - Menyeimbangkan proporsi kolom secara harmonis: Waktu (135px), Keparahan (96px terpusat), Kejadian (40% fleksibel, min 250px), Durasi (85px), Tindakan (95px), dan Saran (30% fleksibel, min 200px) dengan pembungkusan kata rapi (`word-break: break-word`).
  4. **Hierarki Tipografi Teks Sekunder pada Seluruh Tabel:**
     - Menyelaraskan teks sekunder (sub-timestamp, keterangan tambahan, unit, dan catatan kecil) ke ukuran 10.5px–11px atau teks teredam 8px–9px agar hirarki informasi antara data utama dan pelengkap terlihat tegas bagi operator.
  5. **Konsistensi Ukuran Teks Mode Standar & Mode Kompak pada Tabel Status & Kinerja (`dashboard.html`):**
     - Menyeragamkan ukuran font th (11.5px), td (12px), hostname (12.5px), metrik monospaced (12px), alamat IP (11.5px), dan badge (9px) secara identik antara Mode Standar dan Mode Kompak.
     - Mode Kompak kini murni mengendalikan tinggi baris (`25px`), padding rapat (`2px 6px`), dan penyembunyian sub-metrik tanpa pergeseran atau lonjakan ukuran teks yang mengganggu mata.
  6. **Penyelarasan & Standarisasi Penamaan Kolom Antar-Tabel:**
     - Mengganti seluruh istilah `User` menjadi `Pengguna` secara konsisten pada tabel riwayat tindakan (`services.html`), tabel manajer tugas (`services.html`), dan tabel aktivitas login (`user_activity.html`).
     - Mengganti istilah `MAC Address` menjadi `Alamat MAC` dan `IP Address` menjadi `Alamat IP` pada tabel spesifikasi perangkat keras dan jaringan (`services.html`).
  7. **Diferensiasi Ikon Tombol Tindakan pada Tabel Daftar Server (`servers.html`):**
     - Mengubah ikon tindakan Rincian menjadi ikon Mata (*Eye* icon) yang jelas dan representatif.
     - Mengubah ikon tindakan Edit menjadi ikon Pensil murni (*Pencil* icon tanpa kotak) sehingga sangat mudah dibedakan dari tombol rincian maupun tombol hapus (*Trash*).
     - Menyelaraskan ikon pada render Jinja server-side dan fungsi poll AJAX client-side.
  8. **Penyempurnaan Kerapian Visual Tabel Daftar Server (`servers.html`):**
     - Menstandarisasi padding sel rapat (6px 8px untuk th, 5px 8px untuk td), tinggi baris efisien, serta ketepatan perataan teks numerik dan monospaced.
  9. **Eliminasi Indikator Ganda (Titik Merah/Kuning) pada Bilah Tab Rincian Server (`services.html`):**
     - Menghapus titik indikator peringatan (`tab-warn-dot`) dari seluruh tab rincian server (Performa, Insiden, Services, Packages, Tasks, Users, Ports, Firewall, SSL/TLS, Cron, Logs) untuk menghilangkan redundansi visual ganda karena badge angka telah mewakili status insiden dan paket secara akurat.
  10. **Standarisasi Ambang Batas Paginasi Universal (Default 10 Baris & Sembunyikan jika < 5):**
      - Mengatur nilai default paginasi universal pada mesin `attachTablePagination` dan tabel Status Masalah menjadi 10 item per halaman.
      - Menerapkan aturan otomatisasi sembunyikan bilah paginasi (`display: none`) apabila jumlah baris yang tampil kurang dari 5 baris.
  11. **Pencegahan Teks Terpotong pada Header Brand Dashboard (`dashboard.html`):**
      - Memperbaiki kontainer `.dash-brand-wrap` dari tinggi statis kaku (`height: 64px`) menjadi `min-height: 64px; height: auto; gap: 3px;`.
      - Memperbaiki `line-height` nama unit organisasi (`org_unit`) menjadi `1.35` sehingga teks panjang seperti "Bidang Aplikasi dan Informatika" tampil utuh tanpa terpotong (*no clipping*).
  12. **Kepastian Semantik Ikon Interaktif:**
      - Memverifikasi bahwa setiap ikon tombol tindakan di seluruh sistem mewakili fungsinya secara intuitif tanpa memicu keraguan operator.
  13. **Kepatuhan Konsistensi Warna NOC:**
      - Memastikan penegakan palet warna baku (Kritis = Merah, Gawat = Oranye, Peringatan = Kuning, Online/Normal = Hijau, Informasi = Biru, Diabaikan = Abu-abu).
  14. **Pencegahan Tumpang Tindih Teks Kolom (*Column Overlap Prevention*):**
      - Memastikan setiap kolom tabel memiliki batas lebar minimum, perataan yang tepat, dan pembungkusan kata yang terkontrol agar tidak saling menimpa teks kolom tetangga.

## Versi 4.7.6

- **Tipe Rilis:** Sinkronisasi Universal Kolom Keparahan Dua Baris pada Seluruh Kartu Insiden, Proporsionalitas Kolom Kartu Status Masalah, dan Eliminasi Ikon Tidak Diminta pada Label Pengabaian (*Universal Two-Line Severity Column Synchronization Across All Incident Cards, Status Masalah Card Proportion Standardization & Unprompted Ignored Icon Removal*)
- **Fokus Utama:** Menyempurnakan dan menyelaraskan seluruh tampilan kartu insiden di seluruh aplikasi agar konsisten 100% dengan prinsip proporsionalitas antarmuka NOC:
  1. **Standardisasi Menyeluruh Kolom Keparahan Dua Baris pada Kartu Status Masalah (`services.html`):**
     - Menerapkan format hierarki visual dua baris terstruktur pada kolom Keparahan tabel `#probtable` di kartu Status Masalah rincian server: Baris 1 menampilkan badge status utama (`DIABAIKAN` / `KRITIS` / `GAWAT` / `PERINGATAN` / `INFO`) berukuran font proporsional 9.5px tebal, dan Baris 2 menampilkan informasi sekunder (`(oleh <operator>)` atau badge `✓ DITANGANI`) berukuran 8px teredam (`var(--dim)`).
     - Menyelaraskan logika Jinja2 awal dan fungsi perender dinamis JavaScript (`renderProblemsTab`) sehingga seluruh pembaruan live mempertahankan format dua baris yang presisi dan identik.
  2. **Standardisasi Proporsi Kolom dan Tata Letak Tabel Kartu Status Masalah (`services.html`):**
     - Mengoptimalkan proporsi lebar kolom `#probtable`: Kolom Waktu (145px), Kolom Keparahan (96px, rata tengah), Kolom Kejadian (auto, fleksibel), Kolom Durasi (90px), Kolom Tindakan (90px), dan Kolom Saran (260px).
     - Mencegah tumpang tindih (*overlap*) antara kolom saran dan kolom tindakan dengan menyelaraskan kelas `.col-tips` serta padding sel yang seimbang dan proporsional.
  3. **Penghapusan Ikon Tidak Diminta pada Label Pengabaian Dasbor (`dashboard.html`):**
     - Menghapus glif/ikon lonceng hening SVG yang tidak diminta dari kartu ringkasan KPI insiden Diabaikan (`zbx-tile-ignored`), label Jinja2 baris insiden terbuka, dan perender dinamis JavaScript `pollNocDashboard`.
     - Mengembalikan label menjadi teks bersih `Diabaikan` / `DIABAIKAN` murni sesuai desain ergonomis baku yang telah disetujui.
  4. **Pemberlakuan CSS Universal Dua Baris Keparahan (`base.html`):**
     - Menetapkan aturan styling global untuk `th.col-sev`, `td.col-sev`, `.col-sev-sub-text`, dan `.badge-sub` di berkas template dasar agar seluruh modul antarmuka mematuhi standar hierarki yang sama secara konsisten.

## Versi 4.7.5

- **Tipe Rilis:** Restorasi Menyeluruh Kepadatan Antarmuka NOC, Pengalih Mode Dasbor Empat Kontrol, Eliminasi Teks Coret Riwayat Insiden, dan Penyelarasan Tombol Aksi Berbasis Ikon (*Comprehensive NOC Interface Density Restoration, 4-Control Dashboard Switcher, Clean Incident History Rendering & Universal Icon Action Button Polish*)
- **Fokus Utama:** Menyempurnakan dan menegakkan konsistensi visual di seluruh modul aplikasi sesuai standar baku pemantauan NOC:
  1. **Pemulihan Penuh Pengalih Mode & Kepadatan Dasbor (`dashboard.html`):**
     - Memulihkan kontrol pengalih kepadatan baris tabel (`dash-density-switcher`) dengan 4 tombol terpadu: Tabel Operasional, Kartu NOC, Mode Kompak (1 Baris Ringkas), dan Mode Standar (2 Baris Rinci).
     - Menjamin status switcher tersimpan persisten di `localStorage` dan reaktif seketika tanpa memicu pemuatan ulang halaman.
  2. **Standardisasi Hierarki Kolom Keparahan Dua Baris Proporsional (`problems.html` & `dashboard.html`):**
     - Menerapkan hierarki visual 2 baris terstruktur pada kolom Keparahan tabel insiden terbuka: Baris 1 menampilkan status utama (`DIABAIKAN` / Keparahan Insiden) dengan badge proporsional dan tebal, dan Baris 2 menampilkan informasi sekunder opsional (`(oleh <operator>)` atau status penanganan) dengan ukuran teks lebih kecil dan warna teredam (`var(--dim)`).
  3. **Pembersihan Teks Coret pada Riwayat Insiden Teratasi (`problems.html` & `services.html`):**
     - Menghapus efek dekorasi coret (`text-decoration: line-through`) pada deskripsi masalah yang telah selesai, menyajikan riwayat insiden secara bersih, jelas terbaca, dan elegan menggunakan peredaman warna (`color: var(--dim)`).
  4. **Penyelarasan Universal Tombol Tindakan Berikon SVG Murni (`servers.html` & `services.html`):**
     - Memastikan seluruh tabel utama menggunakan tombol tindakan berbasis ikon vektor SVG murni dengan tooltip informatif baku (*Buka Rincian Layanan Server*, *Edit Konfigurasi Server*, *Hapus Server dari Pantau*).
     - Menyelaraskan tombol aksi di bilah judul rincian server (`services.html`) menjadi tombol ikon ringkas dengan tooltip dan tautan kembali `← Daftar Server`.
  5. **Integritas Arsitektur & Peniadaan Fitur Tanpa Permintaan:**
     - Menjaga repositori dan berkas agen tetap murni pada arsitektur telemetri yang telah teruji tanpa injeksi modul cadangan yang tidak diminta.

## Versi 4.7.4

- **Tipe Rilis:** Restorasi Menyeluruh Tombol Tindakan Ikon SVG Murni Tanpa Label Teks, Normalisasi Pengguna Otentikasi, dan Penyempurnaan Konteks Operator Insiden (*Universal Pure SVG Icon Action Buttons Standardization, Authentication User Normalization & Incident Operator Context Polish*)
- **Fokus Utama:** Menegakkan aturan baku ergonomi NOC bahwa seluruh tombol tindakan tabel di seluruh aplikasi wajib berupa ikon SVG murni dengan tooltip informatif tanpa label teks tampak, normalisasi otentikasi login, serta penyelarasan nama operator insiden:
  1. **Restorasi Menyeluruh Tombol Tindakan Berikon SVG Murni pada Tabel Armada Server (`servers.html`):**
     - Mengeliminasi label teks tampak (`Rincian`, `Edit`, `Hapus`) pada kolom tindakan tabel daftar server, menggantikannya dengan tombol ikon vektor SVG murni yang presisi (`width: 12px; height: 12px; stroke-width: 2`).
     - Menyematkan tooltip informatif melalui atribut `title` dan `aria-label` berbahasa Indonesia baku (*Buka Rincian Layanan Server*, *Edit Konfigurasi Server*, *Hapus Server*).
     - Menstandarkan lebar kolom `Tindakan` (`width: 95px; min-width: 85px; text-align: center`) dengan perataan tengah terpusat (`justify-content: center`).
     - Menyelaraskan pembangun baris dinamis JavaScript (`srvPoll`) agar menghasilkan tombol berikon SVG murni identik dengan render awal Jinja2.
  2. **Restorasi Menyeluruh Tombol Tindakan Manajemen Pengguna (`profile.html` & `users.html`):**
     - Menghapus elemen teks tampak (`<span>Lihat</span>`, `<span>+2FA</span>`, `<span>Reset</span>`, `<span>Audit</span>`, `<span>Edit</span>`) dari seluruh tombol tindakan tabel pengguna.
     - Mengubah seluruh tombol aksi pengguna menjadi ikon SVG murni (`user-act-btn` dan `user-act-icon-btn` berukuran 24x24px, radius 4px) dengan tooltip informatif baku (*Lihat detail hak akses*, *Setup 2FA*, *Reset 2FA*, *Matikan 2FA*, *Audit*, *Edit wewenang*, *Kunci/Buka Akun*, dan *Hapus*).
     - Memusatkan perataan kolom tindakan tabel pengguna ke tengah dengan tata letak flexbox rapat (`gap: 4px; justify-content: center`).
  3. **Penyelarasan Operator Pengabaian Insiden (`dashboard.html`):**
     - Memperbaiki binding variabel penampil nama operator pada baris kedua kolom keparahan: saat insiden berstatus diabaikan (`is_ignored`), sistem secara presisi menampilkan nama akun operator yang mengabaikan (`ign_op` / `p.ignored_by`) alih-alih `ack_op`.
  4. **Normalisasi Kredensial & Pemulihan Akses Login Administratif:**
     - Menyelaraskan akun administrator `admin` dan `master-admin` dengan hash otentikasi kata sandi standar yang valid.
     - Membersihkan pembatasan tingkat upaya (*rate-limit lockout*) pada tabel `login_attempts` untuk memulihkan akses login tanpa hambatan.

## Versi 4.7.3

- **Tipe Rilis:** Standardisasi Tata Letak Dua Baris Kolom Keparahan, Ekspansi Proporsi Panduan Solusi, dan Restorasi Menyeluruh Ikon Vektor Dasbor (*Two-Line Severity Hierarchy Standardization, Solution Advice Layout Expansion & Universal Dashboard Vector SVG Icon Restoration*)
- **Fokus Utama:** Memperbaiki proporsionalitas antarmuka pada seluruh tabel insiden dan dasbor NOC, menerapkan hierarki tipografi dua baris baku, serta memulihkan ikon vektor SVG murni:
  1. **Standardisasi Hierarki Dua Baris Kolom Keparahan (`.col-sev` di `base.html`, `services.html`, `problems.html`, `dashboard.html`):**
     - Menerapkan arsitektur dua baris terstruktur: Baris 1 memuat badge keparahan utama (`DIABAIKAN`, `KRITIS`, `GAWAT`, `PERINGATAN`, `INFO`) dengan ukuran teks proporsional (9.5px, `font-weight: 700`, padding 1.5px 5.5px, uppercase). Baris 2 memuat informasi penanganan atau operator sekunder (`(oleh master-admin)` atau `✓ DITANGANI`) dengan teks ringkas (8px, `color: var(--dim)` atau badge hijau 8px).
     - Menetapkan lebar optimal kolom keparahan (`width: 96px; min-width: 90px; max-width: 105px; text-align: center`) agar muat rapi tanpa pembungkusan kata yang canggung atau pelebaran horizontal yang boros ruang.
  2. **Ekspansi Keterbacaan Kolom Saran & Panduan Solusi (`.col-tips`):**
     - Memperluas lebar kolom saran dari 190px menjadi 260px (`min-width: 200px; max-width: 320px; font-size: 11px`) dan menaikkan batas klem teks dari 2 baris menjadi 3 baris (`-webkit-line-clamp: 3`), sehingga rekomendasi teknis sysadmin dapat dibaca utuh tanpa terpotong terlalu dini.
  3. **Penyempurnaan Penyelarasan Kolom Tindakan (`.col-act`):**
     - Menstandarkan lebar kolom tindakan (`width: 90px; min-width: 85px`) dengan perataan tengah terpusat (`text-align: center; justify-content: center`) untuk tombol kontrol berikon SVG murni.
  4. **Restorasi Menyeluruh Ikon Vektor SVG Dasbor (`dashboard.html`):**
     - Memulihkan ikon lonceng hening SVG pada ubin *Diabaikan* di bilah keparahan dasbor (`zbx-tile-ignored`) dan badge insiden diabaikan.
     - Mengganti titik polos pada modal keparahan (`SEV_CONFIG` & `openSevDetailModal`) dengan ikon vektor SVG yang tajam dan representatif untuk kategori Kritis, Gawat, Peringatan, Info, dan Diabaikan.
     - Menyematkan ikon aktivitas armada server pada header kartu *Status & Kinerja*.
     - Menampilkan ikon globe SVG pada nama host endpoint probing eksternal di dasbor dan modal rincian.

## Versi 4.7.2

- **Tipe Rilis:** Restorasi Pengalih Kepadatan Dasbor, Glif Salin Vektor SVG, Proporsionalitas Tabel Insiden, dan Eliminasi Anomali Cadangan (*Restoration of Dashboard Density Switcher, SVG Vector Copy Glyph, Incident Table Proportionality & Automated Backup Telemetry Anomaly Elimination*)
- **Fokus Utama:** Menyelesaikan pemulihan kontrol ergonomi dasbor, standardisasi ikon interaktif tanpa font tofu, penyempurnaan proporsionalitas kolom tabel dan tipografi, serta eliminasi total alarm palsu pemantauan cadangan di seluruh modul:
  1. **Restorasi Pengalih Kepadatan Baris Dasbor (`#dash-density-switcher` di `dashboard.html`):**
     - Mengembalikan 2 tombol pengalih kepadatan baris tabel (*Mode Kompak 1-Baris Ringkas* dan *Mode Standar 2-Baris Rinci*) berdampingan dengan pengalih tata letak dasbor (`#dash-view-switcher`), sehingga bilah kontrol dasbor kembali lengkap dengan 4 tombol kontrol operasional NOC.
     - Menyinkronkan preferensi kerapatan tabel dengan penyimpanan lokal peramban (`localStorage: 'dash_table_density'`).
  2. **Restorasi Ikon Salin Vektor SVG Terpadu (`base.html`):**
     - Menggantikan glif rusak tofu yang sebelumnya dihapus dengan ikon salin vektor SVG murni berbasis CSS `-webkit-mask` / `mask` pada pseudo-elemen `.copyable-ip::after`.
     - Menyediakan indikator visual yang jelas, elegan, dan lintas platform tanpa ketergantungan pada font sistem, lengkap dengan animasi transisi hover dan perbesaran proporsional.
  3. **Penyempurnaan Proporsionalitas Kolom Tabel & Tipografi Badge Insiden (`services.html` & `problems.html`):**
     - Menata ulang proporsi kolom tabel `#probtable`: menghilangkan lebar inline statis yang berlebihan pada kolom Waktu (200px), Durasi (120px), dan Tindakan (160px).
     - Menetapkan kolom Kejadian (`.col-event`) sebagai kolom elastis utama dengan ruang keterbacaan terluas, memadatkan kolom Tindakan (`.col-act`) menjadi 80px ringkas untuk tombol aksi berikon SVG tanpa celah kosong, serta merapikan kolom Panduan Solusi (`.col-tips`) menjadi 190px dengan pembatasan baris teks rapi (`.prob-tip-text`).
     - Mengganti teks polos `Mulai`/`Selesai` menjadi badge terstruktur `<span class="badge badge-muted">MULAI</span>` dan `<span class="badge badge-up">SELESAI</span>` dengan pemisahan jarak flexbox (`gap: 5px`) dan font monospace, mencegah penggumpalan teks (*smushed text*) seperti `MULAI24 Okt 2026`.
  4. **Eliminasi Alarm Palsu Pemantauan Cadangan Sistem (`agent_pantau.py` & `main.py`):**
     - Menambahkan filter pengecualian berkas administratif dan rotasi internal sistem operasi Debian/Ubuntu (`alternatives.*`, `apt.extended_states*`, `dpkg.*`, `gshadow*`, `passwd*`, `shadow*`, `group*`, `subgid*`, `subuid*`, `debconf*`, `infodir*`) pada fungsi `collect_backup_status` di agen klien.
     - Menghapus pembuatan insiden otomatis palsu (`backup_stale`, `backup_corrupted`, `backup_missing`) dari mesin kalkulasi insiden server pusat, mempertahankan data cadangan sebagai telemetri informatif murni pada tab Cadangan.
     - Membersihkan seluruh catatan insiden cadangan usang yang tersisa pada basis data `server_problems`.

---

## Versi 4.7.1

- **Tipe Rilis:** Eliminasi Total Glif Rusak Tofu `copyable-ip`, Duplikasi Label UTC, dan Restorasi Estetika Antarmuka (*Complete Elimination of copyable-ip Tofu Glyphs, UTC Redundancy Elimination & Action Button Aesthetics Restoration*)
- **Fokus Utama:** Menyelesaikan pembersihan visual menyeluruh dari seluruh anomali visual yang tampak pada antarmuka web, menghilangkan glif rusak (*tofu box*), redundansi teks jam, dan menyelaraskan estetika tombol tindakan sesuai prinsip kepadatan tinggi NOC:
  1. **Eliminasi Total Glif Rusak Tofu pada Seluruh Alamat IP (`base.html`):**
     - Menghapus aturan pseudo-elemen `.copyable-ip::after { content: '\2398'; }` yang merender kotak rusak hampa (`□`) pada seluruh alamat IP di Dashboard, Daftar Server, dan Rincian Server bagi pengguna Linux dan sistem tanpa font simbol khusus.
     - Mempertahankan fungsionalitas salin cepat IP dengan efek interaksi latar hover yang bersih dan rapi.
  2. **Eliminasi Redundansi Label UTC pada Footer Sidebar (`base.html`):**
     - Memperbaiki duplikasi teks `UTC` pada footer sidebar (`v4.7.0 · UTC 07:34 UTC`) menjadi format ringkas dan elegan: `v4.7.1 · 07:34 UTC`.
  3. **Restorasi Estetika Tombol Header & Nomenklatur Navigasi (`services.html`):**
     - Mengubah tombol `Edit` dan `Hapus` pada header rincian server menjadi ikon SVG murni yang presisi dengan tooltip deskriptif dan atribut `aria-label`, harmonis dengan bilah alat hero server.
     - Mengubah tautan kembali navigasi `&larr; Servers` dari Bahasa Inggris menjadi Bahasa Indonesia baku `&larr; Daftar Server`.
  4. **Pencegahan Alarm Palsu Titik Peringatan Tab Pengguna (`services.html` & `base.html`):**
     - Menambahkan kelas penanda status informatif `.tab .tab-warn-dot.info-blue` (biru tenang) untuk sesi login remote SSH sysadmin (`#tab-dot-akun`), mengeliminasi titik merah menyala (*danger red*) yang sebelumnya memicu salah persepsi kegawatan sistem.
  5. **Pembersihan Glif dan Emoji Sisa pada Seluruh Template:**
     - Mengganti simbol unicode `⛨` pada port dilindungi di `services.html` dengan ikon SVG shield vektor murni.
     - Mengganti emoji direktori `📁` pada panel direktori cadangan di `services.html` dengan ikon SVG folder murni.
     - Mengganti emoji `ℹ️` pada alasan pemeliharaan di `servers.html` dengan SVG info circle.
     - Mengganti glif `⛶`, `⚙`, dan `⚠️` di `file_manager.html` dengan SVG standar beresolusi tinggi.
     - Mengganti emoji petir `⚡` dan gerigi `⚙️` di `probing.html` serta banner pembaruan di `base.html` dengan SVG zap dan cog vektor bersih.

---

## Versi 4.7.0

- **Tipe Rilis:** Fitur Baru: Pemantauan Status Cadangan Otomatis Terpusat (*Central Automated Backup Monitoring, Database Dump & Archive Integrity Verification*)
- **Fokus Utama:** Mengimplementasikan modul pemantauan status cadangan otomatis (*automated backup monitoring*) untuk mendeteksi ketersediaan, integritas ukuran, dan kebaruan berkas cadangan database (MySQL, MariaDB, PostgreSQL) serta arsip sistem di seluruh server klien:
  1. **Agen Klien Mandiri Tanpa Dependensi Eksternal (`agent_pantau.py`):**
     - Mengimplementasikan `collect_backup_status()` yang secara otomatis memindai direktori cadangan standar (`/var/backups`, `/backups`, `/backup`, `/data/backup`, `/var/lib/mysql/backup`, `/var/lib/postgresql/backup`) dan jalur kustom terkonfigurasi.
     - Memindai berkas cadangan dengan ekstensi dump dan arsip terkompresi (`.sql`, `.sql.gz`, `.sql.bz2`, `.sql.xz`, `.sql.zst`, `.dump`, `.dmp`, `.tar.gz`, `.tgz`, `.tar.bz2`, `.tar.xz`, `.tar.zst`, `.tar`, `.zip`, `.vma.zst`, `.qcow2.bak`).
     - Mengumpulkan metadata lengkap: nama berkas, jalur absolut, direktori, ukuran byte, ukuran ramah manusia (*human-readable*), timestamp modifikasi (*mtime*), dan usia berkas (*age in hours*).
     - Mendeteksi proses basis data aktif (`mariadb`, `mysql`, `postgresql`, `redis`, `mongodb`) untuk korelasi audit ketersediaan cadangan.
     - Memindai tugas cron dan systemd timer aktif yang menjalankan perintah pencadangan (`mysqldump`, `pg_dump`, `rsync`, `tar`, `borg`, `restic`).
     - Menerapkan mekanisme cache 60 detik (*12 reporting ticks*) sehingga konsumsi I/O disk dan CPU agen tetap nol.
  2. **Skema Basis Data & Backend FastAPI (`models.py` & `main.py`):**
     - Menambahkan kolom `backup_status` bertipe `MEDIUMTEXT` pada tabel `server_extras` dengan migrasi otomatis saat server dihidupkan (*auto-migration on startup*).
     - Menangani payload `backup_status` pada rute `/api/report` dan menyimpannya secara terstruktur.
     - Mengintegrasikan evaluasi insiden cadangan pada `_problem_instances`:
       * **Kritis / Bahaya (Danger):** Berkas cadangan berukuran 0 Byte (`backup_corrupted`) memicu tiket insiden bahaya.
       * **Peringatan (Warning):** Berkas cadangan terakhir berusia > 24 jam (`backup_stale`) memicu tiket insiden peringatan.
       * **Informasi (Info):** Basis data aktif terdeteksi namun belum ada berkas cadangan di direktori standar (`backup_missing`).
     - Menyusun konteks diagnostik dwibahasa (ID/EN) pada `_build_problem_context` lengkap dengan rekomendasi dan perintah investigasi terminal (`ls -la`, `df -h`, `journalctl`).
  3. **Antarmuka Pengguna Berprinsip Kepadatan NOC (`services.html`):**
     - Menambahkan tab navigasi baru **Cadangan** (*Backups*) di halaman rincian server dengan indikator titik peringatan (*warn dot*) otomatis.
     - Kartu Ringkasan KPI Cadangan: Status mutakhir/usang/gagal/nihil, nama berkas terbaru, waktu pembuatan, usia relatif, dan total kapasitas penyimpanan cadangan.
     - Tabel Berkas Cadangan Terkini (`#tbl-cadangan`) berprinsip *NOC-density* (tinggi baris rapat ~32px, padding sel 5px 6px, badge proporsional 9.5px, format monospace).
     - Tabel Tugas Cadangan Terjadwal (Cron & Systemd Timer) yang mendeteksi orkestrasi cadangan lokal.
     - Panel Direktori Pemantauan Cadangan yang memandu operator mengenai lokasi pemindaian dan dukungan konfigurasi kustom.
     - Integrasi paginasi terpadu (`attachTablePagination`) dan reaktivitas polling live (`renderBackupStatus`).

---

## Versi 4.6.24

- **Tipe Rilis:** Eliminasi Total Glif Rusak Tofu (Emoji), Standardisasi Status Nihil, dan Penyelarasan Kepadatan Antarmuka (*Total Elimination of Broken Tofu Box Glyphs, Standardization of Zero-Incident "Nihil" Badges & Interface Density Optimization*)
- **Fokus Utama:** Menyelesaikan pembersihan visual menyeluruh dari seluruh anomali tampilan, glif rusak (*tofu square box*), inkonsistensi terminologi, dan redundansi kontrol antarmuka di seluruh modul aplikasi:
  1. **Eliminasi Total Glif Rusak Tofu (Raw Emoji Replacement):** Mengganti seluruh karakter emoji mentah (`🔕`, `🚨`, `⚠️`, `⚡`, `ℹ️`, `🔍`, `🔒`, `👑`, `🛡️`, dll.) yang mereduksi menjadi kotak hampa rusak (`□`) pada sistem Linux tanpa font emoji warna:
     - Di `dashboard.html`: Mengganti `Diabaikan 🔕` pada strip keparahan insiden dan modal diagnosa dengan teks bersih dan dot warna styled CSS murni.
     - Di `problems.html`: Menghapus emoji mentah dari badge ringkasan, pill filter triage (`Semua`, `Critical`, `Gawat`, `Warning`, `Info`, `Diabaikan`), opsi dropdown `<select>`, serta badge sel tabel Jinja2 dan perender JS live (`DIABAIKAN`).
     - Di `services.html`: Menghapus emoji mentah dari badge tab insiden (`tab-masalah-badge`), filter status keparahan, badge sel masalah terbuka/teratasi, badge status layanan (`down` & `up` tanpa `🔕`), badge disk S.M.A.R.T. (`Rusak` tanpa `🚨`), dan ikon pencarian input (`🔍` diganti SVG murni).
     - Di `base.html`: Mengganti emoji pulse `🚨` pada banner darurat dengan SVG alert triangle beranimasi denyut murni, membersihkan label modal diagnosa masalah PDM (`🔍`, `📌`, `📊`, `🛠️`, `💻`) menjadi ikon SVG inline terstruktur, serta menyelaraskan judul tab browser menjadi format ASCII bersih `(!)`.
     - Di `users.html`, `profile.html`, `error.html`, dan `file_manager.html`: Mengganti emoji gembok, pencarian, dan layar penuh dengan penanda status bulat dan SVG vektor tajam.
     - Di backend `server/main.py`: Menghapus prefix emoji `🌐` pada pelabelan hostname probe eksternal yang sebelumnya menyebabkan tampilan nama probe rusak menjadi `□`.
  2. **Standardisasi Status Tanpa Masalah ("Nihil"):** Menyelaraskan status insiden nol pada daftar server (`servers.html`) dari teks `Normal` menjadi `Nihil` (`None` pada bahasa Inggris), konsisten 100% dengan standar operasional NOC pada dasbor utama.
  3. **Penyempurnaan Kepadatan & Pencegahan Overflow Bilah Gulir Horizontal (`servers.html`):** Menyesuaikan lebar kolom header tabel (`th`), padding sel (`5px 8px`), ukuran font hostname (`13px`), serta tombol tindakan cepat (`Rincian`, `Edit`, `Hapus` pada `10.5px; padding: 2px 5px`) sehingga seluruh tabel server pas sempurna pada resolusi 1280px-1440px tanpa memunculkan bilah gulir horizontal (*horizontal scrollbar*) yang memotong kolom tindakan.
  4. **Pembersihan Redundansi Bilah Kontrol Dasbor (`dashboard.html`):** Menghapus toggle pengalih kepadatan baris (`#dash-density-switcher`) yang membingungkan operator karena menampilkan ikon garis sejajar berdampingan dengan pengalih tata letak (`#dash-view-switcher`), mempertahankan tabel kompak 1 baris sebagai standar baku operasional NOC.
  5. **Restorasi Ikon Tombol Segarkan Manajer Tugas (`services.html`):** Mengganti tombol teks `&#8635;&nbsp;Segarkan` pada Manajer Tugas (`#btn-top-procs-refresh`) menjadi tombol ikon SVG segarkan murni yang identik dan harmonis dengan bilah kontrol paket OS lainnya.
  6. **Pelebaran Kolom Tindakan Insiden Selesai (`problems.html`):** Memperlebar kolom tindakan `#prob-resolved-table-wrap th.col-act` dari 45px menjadi 75px untuk mencegah pemotongan teks header `TINDAKAN`.

---

## Versi 4.6.23

- **Tipe Rilis:** Restorasi Menyeluruh Tombol Antarmuka Menjadi Ikon SVG Murni Tanpa Teks & Pengayaan Tooltip Informatif (*Comprehensive Restoration of All UI Action Buttons to Pure SVG Icons with Informative Tooltips*)
- **Fokus Utama:** Mengeliminasi seluruh teks label tombol yang memadati visual antarmuka dan memulihkan desain mapan kepadatan tinggi NOC (*high-density NOC UI*) menjadi tombol berikon SVG murni dengan tooltip standar Bahasa Indonesia baku:
  1. **Restorasi Bilah Alat Hero Server (`services.html`):** Mengembalikan seluruh tombol pada bilah alat atas server (`#apt-term-toggle-btn`, `#hero-fm-btn`, `#btn-maint`, `#apt-update-btn`, `#apt-upgrade-btn`, `#hero-reboot-btn`, `#hero-poweroff-btn`) menjadi ikon SVG murni tanpa teks bertumpuk, dengan padding rapat 5px 8px serta tooltip informatif dan atribut `aria-label` yang jelas.
  2. **Restorasi Bilah Alat Terminal Web (`services.html`):** Mengeliminasi teks label tombol header terminal (`#term-lock-btn`, tombol bersihkan layar, `#term-fullscreen-btn`, dan tombol tutup terminal), menggantinya dengan ikon SVG murni dan tooltip terstruktur (`Bersihkan Layar Konsol`, `Layar Penuh`, `Tutup Jendela Terminal`).
  3. **Restorasi Tombol Tambah Modal & Aksi Unduh Log:** Mengubah tombol pemicu modal (`#btn-add-svc-modal`, `#btn-create-user-modal`, `#btn-fw-block-modal`, `#btn-add-ssl-path-modal`, `#btn-add-cron-modal`) dan tombol unduh log (`#log-dl-btn`) menjadi ikon SVG murni `+` dan unduh dengan tooltip deskriptif.
  4. **Restorasi Tombol Tindakan Seluruh Tabel Layanan & Sistem:** Menghapus seluruh teks span pada tombol tindakan baris tabel: Layanan (`#tbl-services`: Restart, Start, Stop, Log, Abaikan/Pantau, Hapus), Tasks/Proses (`#tbl-task-manager`: Pause, Lanjut, Kill), Akun Pengguna (`#acc-table`: Rincian, Buka Kunci, Kunci, Hapus), Port (`#ports-table`: Kill PID, Blokir Port, Buka Port), Firewall (`#fw-blocked-table`: Buka Blokir), SSL (`#ssl-table`: Hapus), dan Tugas Terjadwal (`#cron-table`: Jeda/Aktifkan, Jalankan, Hapus).
  5. **Restorasi Tombol Modal Diagnosa Dashboard (`dashboard.html`):** Mengubah tombol teks `Diagnosa` dan `Periksa →` pada tabel modal keparahan insiden dashboard (`#sdm-table`) menjadi tombol berikon SVG kaca pembesar dan panah rincian dengan tooltip presisi.
  6. **Restorasi Tombol Kunci Sesi File Manager (`file_manager.html`):** Menyelaraskan tombol kunci sesi file manager menjadi ikon SVG gembok murni dengan penanda visual status sesi yang elegan.

---

## Versi 4.6.22

- **Tipe Rilis:** Pemulihan Baku Tata Letak Baris Tunggal Tabel, Eliminasi Total Istilah "Dibisukan", Standardisasi Paginasi Default 5 & Ikon Tindakan Murni (*Restoration of Single-Row Table Layouts, Zero-Tolerance Elimination of "Dibisukan", Default 5 Pagination Standardization & Pure SVG Action Icons*)
- **Fokus Utama:** Menyempurnakan pemulihan menyeluruh atas seluruh keputusan desain ergonomis dan aturan baku operasional NOC yang telah ditetapkan:
  1. **Eliminasi Total Istilah "Dibisukan":** Mengganti seluruh sisa teks tooltip mode pemeliharaan menjadi `'Aktifkan atau jadwalkan mode pemeliharaan agar notifikasi insiden diabaikan sementara'` selaras dengan aturan mutlak operasional NOC.
  2. **Restorasi Tata Letak Baris Tunggal Tabel Akun Pengguna & Cron:** Mencegah pembungkusan baris tabel Akun Pengguna (`#acc-table`) dan Tugas Cron (`#cron-table`) menjadi 2 baris (`white-space: nowrap`), memisahkan sesi multi-login dengan koma horizontal (bukan tag baris baru `<br>`), serta menata tombol aksi kontrol secara rapat mendatar (`display: inline-flex; flex-wrap: nowrap; gap: 4px; align-items: center`).
  3. **Standardisasi Batas Paginasi Default 5 (dan Default 10 untuk Riwayat):** Memperbaiki nilai paginasi bawaan di seluruh tab detail server (`#tbl-services`, `#tbl-task-manager`, `#acc-table`, `#ports-table`, `#cron-table`, `#systemd-timers-table`, `#ssl-table`, `#fw-rules-table`, `#fw-blocked-table`, `#tbl-system-logs`, `#disks-table`, `#net-table`, `#spec-disks-table`, `#spec-ifaces-table`, dan `#tab-packages`) menjadi `defaultLimit: 5` dengan opsi `[5, 10, 25, 50, ...]`, serta mempertahankan `defaultLimit: 10` khusus untuk Riwayat Tindakan (`#acc-action-table`) dan Riwayat Insiden.
  4. **Harmonisasi Tombol Aksi Tabel Status Masalah (Ikon SVG Murni Tanpa Text Span):** Menghapus seluruh teks span pembungkus (`<span>Diagnosa</span>`, `<span>Log</span>`, `<span>Restart</span>`, `<span>Blokir IP</span>`, `<span>Update OS</span>`, `<span>Update Agen</span>`, `<span>Abaikan</span>`, `<span>Pantau Kembali</span>`) pada tabel Status Masalah di `services.html` (baik Jinja2 pra-render maupun perender JS live), menyelaraskan ke standar ikon SVG murni dengan tooltip informatif dan rata kiri rapi.
  5. **Standardisasi Mikro-Tipografi Badge Header Server:** Menyelaraskan ukuran badge tier (`tier-1`, `tier-2`, `tier-3`) dan versi agen klien pada 8.5px dengan padding rapat 1px 5px.
  6. **Pemurnian Nomenklatur Header Tabel:** Memastikan seluruh judul kolom tabel kontrol antarmuka menggunakan istilah baku **`Tindakan`** (zero `Aksi`).

---

## Versi 4.6.21

- **Tipe Rilis:** Pemulihan Menyeluruh Tab Packages, Kartu Unit Layanan Systemd, Nomenklatur Insiden Baku & Ergonomi NOC (*Full Restoration of Packages Tab, Systemd Units Card, Standard Incident Nomenclature & NOC Micro-Typography*)
- **Fokus Utama:** Melakukan pemulihan total terhadap seluruh modul, komponen antarmuka, dan kontrol interaktif yang sebelumnya terhapus akibat regresi historis `git checkout`:
  1. **Restorasi Arsitektur 11 Tab Navigasi Baku (`services.html`):** Mengembalikan struktur 11 tab navigasi rincian server secara utuh: `[ Performa ] [ Insiden ] [ Services ] [ Packages ] [ Tasks ] [ Users ] [ Ports ] [ Firewall ] [ SSL/TLS ] [ Cron Jobs ] [ Logs ]`.
  2. **Restorasi Tab Manajemen Paket OS (`#tab-packages`):** Mengembalikan panel inventaris paket perangkat lunak sistem operasi dan pustaka terpasang lengkap dengan pencarian real-time, filter tipe (Pengguna/Sistem), filter status (running, exited, failed, inactive, installed, upgradable), pengurutan dinamis, paginator mandiri, pintasan filter dua arah (`PAKET` & `PEMBARUAN`), serta tindakan kontrol (Bersihkan cache via sapu/sparkles, Lihat log riwayat dpkg modal, dan Upgrade paket).
  3. **Restorasi Kartu Unit Layanan Systemd (`#card-systemd-units`):** Mengembalikan kartu manajemen unit daemon OS Systemd di dalam tab `Services` lengkap dengan filter status/boot, pengurutan memori/status/nama, paginator terpadu, pintasan filter dua arah (`UNIT`, `RUNNING`, `FAILED`), serta tindakan kontrol (Restart, Start, Stop, Reload, Enable/Disable boot, dan Log journalctl).
  4. **Harmonisasi Status Insiden & Eliminasi Total Istilah "Diakui":** Menyelaraskan status penanganan insiden pada kolom `Keparahan` (`.col-sev`) yang menampilkan badge `✓ DITANGANI` (hijau) `(oleh master-admin)` dan `DIABAIKAN 🔕` (abu-abu), mengeliminasi badge `✓ diakui` secara permanen dari kolom `Kejadian`, memformat badge `kambuh X×` secara proporsional (font 7.5px), serta membakukan tombol tindakan insiden menjadi ikon checklist merah `Tangani Insiden` saat belum ditangani dan checklist hijau `Insiden Ditangani` saat telah ditangani.
  5. **Standardisasi Micro-Typography & Ergonomi NOC:** Menyelaraskan font subtitle hero metadata (`.hero-meta-sys` & `.hero-meta-bar`) pada 11px, serta badge platform/HA/tags pada 8.5px dengan padding rapat 1px 4.5px.
  6. **Klarifikasi Deskripsi Bantuan Probing Endpoint (`probing.html`):** Menyempurnakan teks bantuan tautan server: `Aplikasi yang berjalan server klien. Kosongkan jika memantau aplikasi atau perangkat jaringan yang tidak anda kendalikan.`.

---

## Versi 4.6.20

- **Tipe Rilis:** Pemulihan Integritas Nomenklatur Baku Antarmuka, Restorasi Status Masalah Nihil & Penguncian Aturan Tata Letak (*Restoration of Standard UI Nomenclature, Dashboard Nihil Problem Status & Layout Rules Enforcement*)
- **Fokus Utama:** Memulihkan dan mengunci secara permanen seluruh keputusan desain baku, terminologi ergonomis, dan konvensi antarmuka yang sebelumnya telah ditetapkan oleh operator/developer namun sempat tergeser atau tertimpa selama proses refactoring:
  1. **Restorasi Status Masalah "Nihil" di Dashboard:** Mengembalikan teks badge kolom masalah berstatus aman pada tabel armada server dan kartu grid NOC menjadi **`Nihil`** (atau `None` dalam bahasa Inggris) sesuai instruksi asli, menggantikan teks `Normal`.
  2. **Restorasi Nama Tab Rincian Server (`services.html`):** Menyelaraskan kembali judul navigasi 10 tab rincian server sesuai nomenklatur teknis baku yang telah disepakati: `[ Performa ] [ Insiden ] [ Services ] [ Tasks ] [ Users ] [ Ports ] [ Firewall ] [ SSL/TLS ] [ Cron Jobs ] [ Logs ]`.
  3. **Standarisasi Menyeluruh Kolom "Tindakan":** Mengganti seluruh judul kolom tabel kontrol antarmuka di seluruh berkas template (`dashboard.html`, `services.html`, `problems.html`, `servers.html`, `profile.html`, `users.html`, `file_manager.html`, `probing.html`, `base.html`) dari istilah `Aksi` menjadi istilah baku **`Tindakan`**.
  4. **Proteksi & Larangan Mutlak Terhadap Improvisasi Liar:** Menetapkan guardrail ketat bahwa seluruh perbaikan di masa mendatang wajib menerapkan prinsip perubahan bedah minimal (*surgical patch*) tanpa merombak atau menulis ulang fungsi, tata letak, atau terminologi yang sudah mapan.

---

## Versi 4.6.19

- **Tipe Rilis:** Standarisasi Pengabaian Insiden Universal & Dekomisioning Insiden Dikenal dari Kartu Insiden Terkini (*Universal Incident Silencing Standardization & Decommissioning Recognized Incidents from Recent Incidents Card*)
- **Fokus Utama:** Menerapkan prinsip operasional NOC sejati di mana operator yang memantau layar utama tidak boleh dibebani oleh tampilan insiden yang sudah dikenali atau disengaja (seperti layanan *on-demand* yang sengaja dihentikan hingga dipanggil manual oleh pengguna server klien, sesi remote SSH resmi, atau proses terjadwal). Seluruh insiden dari tingkat keparahan apapun (*kritis, gawat, peringatan, info*) yang diabaikan oleh operator (`is_ignored = 1`) secara otomatis dan mutlak disembunyikan dari tabel *Insiden Terkini*, sementara kartu *Insiden Aktif* mencatatnya secara terpusat pada indikator *"Diabaikan 🔕"* yang dapat ditinjau melalui modal rincian *Diabaikan (Silenced / Ignored 🔕)*.

### Rangkuman Pembaruan:
1. **Penyembunyian Mutlak Insiden Diabaikan dari Kartu Insiden Terkini (`server/main.py` & `server/templates/dashboard.html`):**
   - Agregasi `all_open_problems` (sisi server) dan `allProblems` (sisi polling live client) kini secara tegas memfilter keluar seluruh insiden yang memiliki status `is_ignored = 1` tanpa memandang tingkat keparahannya.
   - Mengeliminasi sisa baris redup (*opacity: 0.8*) ber-badge `DIABAIKAN 🔕` yang sebelumnya masih mencemari tabel *Insiden Terkini*. Tabel *Insiden Terkini* kini 100% murni hanya menyajikan anomali aktif yang memerlukan perhatian atau intervensi operator.
   - Bila seluruh anomali telah terselesaikan atau diabaikan secara sadar, tabel *Insiden Terkini* secara otomatis menampilkan panel hijau `Seluruh server beroperasi prima. Tidak ada gangguan atau insiden aktif saat ini. 100% NORMAL`.
2. **Pencatatan Terpusat pada Indikator "Diabaikan 🔕" Kartu Insiden Aktif:**
   - Seluruh insiden yang diabaikan (layanan down, SSH remote, APT, metrik hardware, dan probe target) secara otomatis tercatat pada counter `ignored_total` / `ignTot` pada kartu *Insiden Aktif*.
   - Tile *Diabaikan 🔕* pada Zabbix severity strip aktif menyala (`is-active`) saat terdapat insiden diabaikan, dan total insiden global (`dash-total-prob`) menjumlahkan seluruh insiden aktif ditambah insiden diabaikan secara matematis akurat.
   - Modal rincian *Diabaikan (Silenced / Ignored 🔕)* menyajikan seluruh daftar kejadian diabaikan secara komprehensif, dilengkapi pill keparahan asal (KRITIS/GAWAT/PERINGATAN/INFO), alasan pengabaian (*ignored_reason*), durasi berlangsung, serta tombol pintas diagnosa dan periksa layanan.
3. **Penyelarasan Server Fleet & Halaman Masalah (`server/main.py`, `problems.html`):**
   - Indikator baris dan kartu grid armada server kini secara akurat menampilkan badge abu-abu berisi jumlah insiden diabaikan pada server terkait.
   - Halaman `/problems` memisahkan secara bersih antara insiden aktif per tingkat keparahan dengan insiden non-aktif pada pill triage `Diabaikan`.
4. **Verifikasi Otomatis End-to-End dengan Selenium Headless:**
   - Pengujian live otomatis memvalidasi alur kerja pengabaian insiden multi-level: pengabaian insiden SSH (info) dan layanan down (warning), validasi hilangnya baris dari tabel *Insiden Terkini*, kenaikan counter *Diabaikan 🔕* ke angka 1 lalu 2, validasi modal *Diabaikan (Silenced / Ignored 🔕)*, validasi status *100% NORMAL* saat seluruh insiden diabaikan, serta pemulihan seketika saat di-unignore.

---

## Versi 4.6.18

- **Tipe Rilis:** Penyelarasan Alur Kerja Pengabaian Insiden Severity INFO (*Workflow Alignment for Ignored Severity INFO Incidents*)
- **Fokus Utama:** Menyempurnakan logika bisnis dan perilaku antarmuka saat operator sengaja mengabaikan insiden dengan severity `INFO` (seperti notifikasi ketersediaan paket pembaruan APT atau sesi login remote SSH aktif). Insiden INFO yang diabaikan secara otomatis disingkirkan dari tabel *Insiden Terkini* pada dashboard utama agar tidak mengaburkan fokus pemantauan NOC, namun tetap dipertahankan dan terhitung secara akurat pada kartu *Insiden Aktif* (termasuk badge jumlah Info dan modal rincian Info dengan indikator status `Diabaikan 🔕`).

### Rangkuman Pembaruan:
1. **Penyelarasan Logika Pengabaian Severity INFO di Backend (`server/main.py`):**
   - Mengubah komputasi `info_p`, `info_probs`, dan `info_open` agar tetap mencatat seluruh insiden berkategori `INFO` terlepas dari status pengabaian (`is_ignored`).
   - Memastikan koleksi `all_open_problems` (sumber data tabel Insiden Terkini) secara ketat memfilter insiden INFO yang berstatus `is_ignored = 1` sehingga tabel tetap bersih dan berfokus pada gangguan operasional aktual.
   - Memasukkan insiden INFO yang diabaikan ke dalam daftar `problems_by_sev["info"]` sekaligus `problems_by_sev["ignored"]`, memastikan data tersedia secara utuh baik saat operator memeriksa kartu Info maupun kartu Diabaikan.
2. **Sinkronisasi Reaktif di Frontend Dashboard (`server/templates/dashboard.html`):**
   - Menyesuaikan fungsi `pollNocDashboard()` agar insiden INFO yang diabaikan tetap menginkrementasi counter `infoTot` (bukan dipindahkan secara sepihak ke `ignTot`), mempertahankan badge Info biru pada kartu *Insiden Aktif*.
   - Menyinkronkan struktur `newProblemsBySev.info` dengan menyertakan insiden INFO yang diabaikan sehingga modal rincian keparahan menampilkan baris kejadian dengan badge `Diabaikan 🔕`.
   - Mempertahankan filter pencegah pada agregasi `allProblems` (`if (isIgn && pSev === 'info') return;`) agar polling background tidak memasukkan kembali insiden INFO yang telah diabaikan ke tabel *Insiden Terkini*.
3. **Penyempurnaan Halaman Masalah & Filter Keparahan (`server/templates/problems.html`, `base.html`, `services.html`):**
   - Menyelaraskan filter keparahan `probFilter()` pada pill triage: pemilihan filter `info` kini menampilkan seluruh insiden informatif (termasuk yang diabaikan), sementara pemilihan filter `ignored` tetap menampilkan seluruh insiden non-aktif yang diabaikan.
   - Menyesuaikan perhitungan jumlah aktif pada header halaman masalah (`open_problems|length - ignored_open`).
4. **Verifikasi Otomatis End-to-End Melalui Selenium Headless:**
   - Melakukan pengujian simulasi skenario operator: verifikasi kemunculan awal insiden INFO pada kedua tempat, eksekusi tombol 'Abaikan', validasi hilangnya insiden dari tabel *Insiden Terkini*, validasi bertahannya counter pada kartu *Insiden Aktif*, validasi keberadaan item beserta badge `DIABAIKAN 🔕` di dalam modal Info, serta pemulihan reaktif saat di-unignore. Seluruh pengujian lulus 100%.

---

## Versi 4.6.17

- **Tipe Rilis:** Standarisasi Universal Modal Dismissal, Tombol Close 'X', Pintasan ESC Global, dan Pencegahan Kebocoran Resource Streaming Log (*Universal Modal Dismissal Standardization, Close 'X' Controls, Global ESC Shortcuts, & Log Streaming Resource Leak Prevention*)
- **Fokus Utama:** Menyelesaikan permasalahan inkonsistensi interaksi modal dialog di seluruh halaman Pantau Server (memastikan setiap modal dialog dapat ditutup melalui 3 metode standar: tombol Close 'X' yang konsisten, penekanan tombol Escape keyboard global, dan klik di luar area dialog/backdrop), merestrukturisasi penempatan DOM modal dialog yang sebelumnya terjebak di dalam kontainer tab tersembunyi (*hidden tab scoping bug*), serta menghentikan kebocoran resource polling background pada streaming log saat operator beralih tab atau meminimalkan browser.

### Rangkuman Pembaruan:
1. **Standarisasi Kontrol Universal Modal Dismissal (`base.html`):**
   - Mengimplementasikan pengendali global `dismissActiveModal(target)` yang mendukung penutupan lebih dari 24 ragam modal dialog di seluruh aplikasi secara seragam.
   - Mengintegrasikan event listener tombol `Escape` keyboard global yang secara otomatis mengenali dan menutup modal dialog teratas yang sedang aktif.
   - Mengintegrasikan deteksi klik pada area latar belakang modal (`modal-backdrop` / `modal`) sehingga klik di luar kotak dialog akan menutup modal secara halus.
2. **Penyempurnaan Tombol Close 'X' pada Seluruh Modal Dialog:**
   - Memastikan setiap header modal dialog pada seluruh antarmuka (`services.html`, `problems.html`, `users.html`, `profile.html`, `file_manager.html`) memiliki tombol Close berikon '×' yang terhubung langsung ke pengendali penutup modal.
3. **Restrukturisasi DOM Modal Dialog Rincian Server (`services.html`):**
   - Memindahkan 7 modal operasional (`add-svc-modal`, `svc-confirm-modal`, `kill-proc-modal`, `block-ip-modal`, `create-user-modal`, `add-cron-modal`, `add-ssl-path-modal`) dari dalam kontainer sub-tab individual yang berstatus `hidden` ke level root global dokumen HTML.
   - Menghilangkan bug di mana modal tidak dapat dirender atau interaksi terblokir saat operator memanggil aksi dari luar tab asal.
4. **Eliminasi Kebocoran Resource Polling Streaming Log (`services.html`):**
   - Memperbaiki bug kritis pada fungsi `pollSystem` (interval 5 detik) yang sebelumnya selalu memicu pemanggilan `startAutoLog()` tanpa memverifikasi visibilitas tab Logging, mengakibatkan spam request `POST /api/logs/request` ke MariaDB setiap 4 detik meskipun tab Logging tidak aktif.
   - Menambahkan mekanisme `pauseAutoLog()` saat operator berpindah dari tab Logging ke tab lain, dan `resumeAutoLog()` saat tab Logging kembali dibuka.
   - Menambahkan listener `visibilitychange` dokumen untuk menghentikan interval streaming log saat browser diminimalkan atau tab browser tidak aktif.
5. **Verifikasi Komprehensif Melalui Selenium Headless Automated Test:**
   - Pengujian otomatis pada seluruh modal di `/dashboard`, `/problems`, `/servers/1/services`, dan `/probes` memastikan keberhasilan 100%: verifikasi 0 severe console error, seluruh 10 tab beralih mulus, tombol Close 'X' merespons, tombol ESC menutup modal, dan klik backdrop menutup modal.
   - Sinkronisasi versi 4.6.17 di seluruh 7 berkas inti ekosistem Pantau Server.

---

## Versi 4.6.16

- **Tipe Rilis:** Manajemen Siklus Hidup Armada Dinamis (Tambah/Hapus Server) & Reaktivitas Multi-Layar NOC Tanpa Reload (*Dynamic Fleet Lifecycle Management & Multi-Screen Zero-Reload NOC Reactivity*)
- **Fokus Utama:** Menjamin layar monitor utama NOC (Layar 1) yang beroperasi 24/7 tanpa reload selalu sinkron secara seketika terhadap seluruh mutasi armada server yang dilakukan operator pada Layar 2 (penambahan host baru, penghapusan host, perubahan hostname/IP/tier/grup/platform), serta eliminasi sisa fallback `location.reload()` pada alur aksi insiden.

### Rangkuman Pembaruan:
1. **Manajemen Siklus Hidup Armada Dinamis Tanpa Reload (`dashboard.html` & `servers.html`):**
   - Mengimplementasikan deteksi otomatis penambahan dan penghapusan server pada polling background AJAX.
   - Server yang dihapus dari database seketika dipangkas dari DOM tabel armada dan kartu grid NOC tanpa reload.
   - Server baru yang didaftarkan langsung dikonstruksi secara dinamis ke dalam tabel armada dan kartu grid NOC beserta seluruh indikator metrik, platform, dan badge status.
   - Pembaruan live atribut pencarian, penyaringan grup, serta sinkronisasi nilai counter KPI Total Host secara otomatis.
2. **Sinkronisasi Reaktif Metadata Host (`dashboard.html`):**
   - Hostname, IP address, tier prioritas, platform hypervisor, dan nama grup diperbarui seketika pada baris tabel dan kartu grid bila terjadi perubahan konfigurasi di server detail/edit.
3. **Penyempurnaan Signature Anti-Jitter Insiden (`dashboard.html`):**
   - Menambahkan identitas unik `p.id` dan `p.ignored_reason` ke dalam signature anti-jitter tabel insiden terkini untuk menjamin perubahan status penanganan (*acknowledged*) atau catatan pengabaian (*ignored reason*) langsung memicu re-render baris tanpa reload.
4. **Eliminasi Total Sisa Fallback `location.reload()` (`base.html` & `problems.html`):**
   - Menggantikan fallback hard reload pada aksi *acknowledge*, *ignore*, dan *unignore* dengan pemanggilan asinkron `window.poll()` dan `pollNocDashboard()`, mematuhi aturan baku zero-reload NOC.
5. **Verifikasi Simulasi Nyata Multi-Layar Headless Browser:**
   - Diuji dan diverifikasi 100% lulus melalui simulasi multi-layar Selenium Headless: Layar 1 terbuka tanpa reload, Layar 2 menambah host baru dan Layar 1 langsung menampilkan host baru dalam 2 detik, kemudian Layar 2 menghapus host dan Layar 1 memangkas elemen dalam 3 detik tanpa reload.
   - Sinkronisasi versi 4.6.16 di seluruh 7 berkas inti ekosistem Pantau Server.

---

## Versi 4.6.15

- **Tipe Rilis:** Sinkronisasi Dinamis Signature Pesan Insiden Tanpa Reload & Pembaruan Seketika Masalah APT (*Dynamic Incident Message Signature for Zero-Reload & Instant APT Problems Sync*)
- **Fokus Utama:** Menyelesaikan permasalahan multi-layar NOC di mana pembaruan teks/kuantitas insiden aktif (seperti penambahan paket upgrade OS dari 1 menjadi 2 pasca `apt update`) tidak langsung tercermin di Layar 1 (Dashboard monitor utama) tanpa reload karena hashing anti-jitter signature mengabaikan perubahan teks `message`, serta memastikan backend meng-commit pembaruan status `ServerProblem` seketika saat agen melaporkan hasil eksekusi tindakan operasional.

### Rangkuman Pembaruan:
1. **Penyertaan Dinamis `message` pada Signature Anti-Jitter Tabel Insiden (`dashboard.html`):**
   - Menambahkan `${p.message || ''}` ke dalam generator `newSig` dan atribut Jinja2 `data-sig` pada elemen `#dash-problems-tbody`.
   - Mengubah kuantitas atau pesan insiden seketika (seperti "1 paket menunggu upgrade" menjadi "2 paket menunggu upgrade") langsung memperbarui baris tabel insiden terkini di layar utama dalam siklus detak 3 detik tanpa mengharuskan operator me-reload halaman.
2. **Sinkronisasi Langsung Masalah APT ke Database Pasca-Eksekusi Tindakan (`server/main.py`):**
   - Pada penanganan callback hasil perintah `APT_UPDATE` dan `APT_UPGRADE`, status baris `ServerProblem` dengan kunci `apt_updates` langsung diperbarui (pesan, konteks, dan timestamp) atau ditandai selesai jika 0 paket, lalu di-commit ke database secara seketika.
3. **Persistensi Transaksi Polling API Servers (`server/main.py`):**
   - Menambahkan `db.commit()` pada akhir endpoint `/api/servers` dan `problems_aggregate` untuk menjamin hasil rekonsiliasi `sync_server_problems` tersimpan permanen dan tidak ter-rollback pada request GET berikutnya.
4. **Validasi Simulasi Nyata Multi-Layar Headless Browser:**
   - Telah diuji melalui simulasi 2 layar otomatis via Selenium Headless Chrome: Layar 1 terbuka tanpa disentuh/tanpa reload, Layar 2 memicu pembaruan paket dari 1 menjadi 2, dan Layar 1 terbukti sukses memperbarui teks dan menghapusnya saat upgrade selesai dalam hitungan detik.
   - Sinkronisasi versi 4.6.15 di seluruh 7 berkas inti ekosistem Pantau Server.

---

## Versi 4.6.14

- **Tipe Rilis:** Standardisasi Universal Penutupan Modal (ESC & Backdrop), Resolusi Route Alias Endpoint Probing, dan Handler Favicon (*Universal Modal ESC/Backdrop Handlers, Endpoint Probing Route Alias & Favicon 204*)
- **Fokus Utama:** Hasil pengujian simulasi interaktif headless browser menyeluruh: memastikan seluruh jendela modal (Diagnosa & Rincian Masalah, Ambang Batas, Pengabaian, Severity Strip, dan Probing) dapat ditutup secara andal via tombol [X], tombol Escape (ESC), maupun klik backdrop latar belakang, menambahkan route alias `/probes` & perbaikan tautan dashboard ke `/probing` untuk mencegah HTTP 404, serta menangani rute `/favicon.ico` dengan status 204 No Content untuk menghilangkan galat konsol browser.

### Rangkuman Pembaruan:
1. **Universal Keyboard Shortcut Penutupan Modal (ESC & Backdrop) (`base.html`):**
   - Menambahkan *event listener* Escape terpadu pada `base.html` yang secara berurutan dan aman menutup modal Diagnosa (`#problem-detail-modal`), Ambang Batas (`#threshold-modal`), Pengabaian (`#ignore-problem-modal`), Severity Strip (`#sev-detail-modal`), serta Probing (`#probeModalBackdrop` & `#historyModalBackdrop`).
2. **Resolusi Route Alias Endpoint Probing (`server/main.py` & `dashboard.html`):**
   - Menambahkan route decorator ganda `@app.get("/probes")` di samping `@app.get("/probing")` dan memperbarui tautan tabel insiden dashboard ke `/probing` sehingga operator tidak pernah mengalami galat 404 saat bernavigasi dari insiden endpoint probe.
3. **Penyediaan Rute Favicon Tanpa Galat (`server/main.py`):**
   - Menambahkan endpoint `@app.get("/favicon.ico")` dengan respon 204 No Content untuk mencegah pencatatan galat 404 otomatis pada konsol browser.
4. **Verifikasi Simulasi Interaktif & Kepatuhan SOP Pantau:**
   - Seluruh 19 uji simulasi interaktif browser berbasis Selenium lulus 100% tanpa error JavaScript runtime.
   - Sinkronisasi versi 4.6.14 di seluruh 7 berkas inti ekosistem Pantau Server.

---

## Versi 4.6.13

- **Tipe Rilis:** Peniadaan Pemuatan Ulang Paksa Halaman pada Modal Ambang Batas Insiden (*Elimination of Forced Page Reload on Incident Thresholds Modal & Zero-Reload Completion*)
- **Fokus Utama:** Menyempurnakan prinsip *zero manual reload* pada antarmuka operator dengan mengganti pemanggilan `location.reload()` pada saat menyimpan atau mereset ambang batas insiden (`problems.html`) dengan eksekusi polling asinkron reaktif `window.poll()`, memastikan seluruh tindakan operator di semua halaman berjalan instan tanpa interupsi layar.

### Rangkuman Pembaruan:
1. **Reaktivitas Tanpa Reload pada Modal Ambang Batas (`problems.html`):**
   - Mengganti `setTimeout(() => location.reload(), 600)` pada fungsi `submitThresholds` dan `resetThresholds` dengan pemanggilan asinkron reaktif `if (typeof window.poll === 'function') window.poll()`.
   - Data insiden, badge keparahan, dan tabel diperbarui secara mulus di latar belakang tanpa me-refresh jendela browser.
2. **Sinkronisasi Versi SemVer dan Kepatuhan SOP Pantau:**
   - Sinkronisasi versi 4.6.13 di seluruh 7 berkas ekosistem Pantau Server sesuai standar operasional baku.

---

## Versi 4.6.12

- **Tipe Rilis:** Implementasi Sliding Session Window 24/7 dan Audit Total Runtime Engine Pengawas Tanpa Reload (*24/7 NOC Sliding Session Window & Comprehensive Runtime Engine Audit*)
- **Fokus Utama:** Memastikan workstation dan layar display NOC yang berjalan 24/7 tidak pernah mengalami pemutusan sesi (*session timeout*) atau pembekuan antarmuka secara sepihak setelah 12 jam, memperbaiki penanganan error runtime pada live version watcher (`let _CLIENT_APP_VER`), serta menghilangkan catch block senyap pada alur polling alerts agar stabilitas operasional pemantauan layar lebar terjamin penuh tanpa reload.

### Rangkuman Pembaruan:
1. **Sliding Session Window 24/7 pada Backend (`server/main.py`):**
   - Sesi aktif operator NOC yang melakukan request berulang diperpanjang secara otomatis jika sisa masa aktif kurang dari separuh masa berlakunya (`SESSION_TTL / 2` = 6 jam), mencegah layar display 24/7 ter-logout atau membeku setelah 12 jam pemantauan terus-menerus.
   - Penambahan `try-except` dan rollback pengaman saat pembersihan sesi kedaluwarsa maupun perpanjangan sesi sliding window di database.
2. **Resolusi Eksepsi Runtime Variabel Konstan pada Version Watcher (`base.html`):**
   - Mengubah deklarasi `const _CLIENT_APP_VER` menjadi `let _CLIENT_APP_VER` pada live version watcher engine. Hal ini mencegah timbulnya `TypeError: Assignment to constant variable` saat antarmuka menyinkronkan status versi server baru secara reaktif di latar belakang tanpa reload.
3. **Penghapusan Penelanan Error Senyap (*Silent Catch Elimination*):**
   - Mengganti catch block senyap pada fungsi `alertFetch()` dan `checkServerVersion()` dengan pencatatan `console.error` dan `console.warn` terstruktur agar jika terjadi kendala jaringan atau kegagalan parsing, teknisi dapat langsung menganalisisnya dari konsol browser.
4. **Sinkronisasi Versi SemVer dan Kepatuhan SOP Pantau:**
   - Sinkronisasi versi 4.6.12 di seluruh 7 berkas inti ekosistem Pantau Server sesuai standar operasional baku NOC.

---

## Versi 4.6.11

- **Tipe Rilis:** Peniadaan Polusi Visual Warna Baris Tabel & Penjagaan Desain Bersih Standar NOC (*Elimination of Table Row Background Tinting & Restoration of Clean NOC Ergonomics*)
- **Fokus Utama:** Menghapus pewarnaan latar belakang baris tabel armada server (`<tr>`) dan pemutasian kelas kartu grid NOC yang berlebihan. Mengembalikan tata visual tabel armada ke standar ergonomi NOC enterprise yang bersih, tenang, seragam, dan kontras tinggi tanpa polusi warna-warni (*no rainbow striping*), dengan tetap mempertahankan indikator status pada kolom Status dan kolom Insiden serta pembaruan data real-time tanpa reload.

### Rangkuman Pembaruan:
1. **Peniadaan Polusi Warna Latar Belakang Baris Tabel (`dash-tr-`):**
   - Menghapus manipulasi `style.background` dinamis pada baris tabel di dalam fungsi `pollNocDashboard` dan menghapus inline style background bersyarat pada template Jinja2. Seluruh baris tabel kembali menggunakan warna gelap seragam standar NOC yang bersih dan nyaman dipandang mata.
2. **Peniadaan Mutasi Kelas Berlebih pada Kartu Grid NOC:**
   - Menghapus manipulasi kelas warna-warni pada kartu grid NOC (`card-srv-`) agar tata visual kartu tetap tenang dan tidak memicu kelelahan visual (*visual fatigue*).
3. **Fokus Indikator Presisi pada Tempatnya:**
   - Indikator masalah dan status operasional tetap terpantau akurat melalui lencana keparahan di kolom **Insiden**, status dot di kolom **Status**, dan daftar insiden di kartu **Insiden Terkini** tanpa memerlukan pewarnaan seluruh area baris.

---

## Versi 4.6.10

- **Tipe Rilis:** Perbaikan Kritis Pipeline Polling Real-Time Dashboard NOC Layar Lebar (*Critical Live Polling Pipeline & DOM Reactivity Fix for NOC Display*)
- **Fokus Utama:** Menyelesaikan akar masalah fatal pada fungsi `pollNocDashboard` di mana variabel penghitung keparahan per-server (`dCnt`, `avgCnt`, `wCnt`, `iCnt`, `ignCnt`) tidak terdefinisi pada loop pemrosesan DOM sehingga memicu unhandled `ReferenceError: dCnt is not defined`. Kesalahan ini secara senyap membatalkan seluruh siklus pembaruan DOM real-time pada kartu KPI, Zabbix Severity Strip, Tabel Insiden Terkini, dan Tabel/Grid armada server pada layar pantauan NOC tanpa reload.

### Rangkuman Pembaruan:
1. **Resolusi Fatal `ReferenceError: dCnt is not defined` pada `pollNocDashboard` (`dashboard.html`):**
   - Menginsersi inisialisasi variabel keparahan `dCnt`, `avgCnt`, `wCnt`, `iCnt`, dan `ignCnt` pada siklus iterasi DOM per-server (`list.forEach`) sehingga evaluasi status `hasIncident`, agregasi `totActive`, serta pembuatan lencana keparahan berjalan mulus tanpa eksepsi runtime.
2. **Pembaruan Reaktif Visual Background Baris & Kartu Grid (`dashboard.html`):**
   - Menambahkan pembaruan dinamis `dash-tr-${srv.id}.style.background` untuk mengubah rona warna baris tabel armada secara langsung saat insiden terdeteksi (merah untuk bahaya/offline, oranye untuk gawat, kuning untuk peringatan, biru langit untuk info) dan mengembalikan ke normal saat pulih.
   - Menambahkan atribut `id="card-srv-{{ srv.id }}"` pada kartu grid dan menyinkronkan status kelas (`is-danger`, `is-average`, `is-warn`, `is-offline`, `is-healthy`) secara seketika.
3. **Penguatan Penanganan Error & Fungsi Escape Mandiri (`_dashEsc`):**
   - Mengganti catch block senyap `catch(e) {}` dengan `console.error('[NOC Polling Error]:', e)` agar kesalahan eksekusi di browser terpantau jelas di console pengembang.
   - Menambahkan fungsi sanitasi string `_dashEsc` mandiri di dalam blok skrip dashboard untuk mencegah dependensi siklik atau kegagalan fungsi escape eksternal.
4. **Penyelarasan Anti-Jitter Signature Masalah:**
   - Menjamin nilai default string kosong `(p.key || '')` dan `(p.severity || '')` pada pemetaan signature anti-jitter tabel insiden terkini agar tidak menghasilkan nilai `undefined`.

---

## Versi 4.6.9

- **Tipe Rilis:** Reaktivitas Penuh Seluruh Halaman Tanpa Reload & Asinkronisasi Menyeluruh Aksi Operator (*Universal Zero-Reload Autonomous Monitoring & Asynchronous Action Architecture*)
- **Fokus Utama:** Mewujudkan prinsip fundamental pemantauan NOC: Operator tidak perlu me-reload halaman manapun di bawah kondisi apapun. Seluruh kejadian eksternal (sesi login SSH remote, service stop/crash, perubahan port/firewall) dan seluruh aksi dari dalam aplikasi (Reboot OS, Power Off, mitigasi IP, manajemen firewall, penambahan layanan, tugas cron, sertifikat SSL) dilaporkan dan direfleksikan secara seketika (*real-time zero-reload*).

### Rangkuman Pembaruan:
1. **Pembaruan Reaktif Tab Rincian Server (`services.html`):**
   - Menambahkan fungsi perender dinamis `renderPorts`, `renderFirewall`, `renderCron`, dan `renderSsl` yang diperbarui secara otomatis setiap siklus polling `/api/servers/{sid}/system` tanpa reload.
   - Tab "Akun Pengguna" kini secara instan memperbarui lencana jumlah sesi aktif (SSH) serta mengaktifkan dot peringatan tab (`tab-dot-akun`) secara seketika saat ada sesi login remote baru.
   - Tab "Firewall", "Sertifikat SSL", dan "Tugas Terjadwal" mengaktifkan dot peringatan tab jika terdeteksi anomali/status nonaktif.
2. **Asinkronisasi Penuh Aksi Operator (Zero Page Reload on Action):**
   - Mengubah seluruh aksi form berbasis `<form method="post">` (Reboot OS, Matikan Daya/Power Off, Blokir IP, Buka Blokir, Tambah Layanan, Tambah Tugas Cron, Jeda/Aktifkan Cron, Tambah Lokasi SSL, Aturan Port, Restart Layanan) menjadi eksekusi AJAX asinkron dengan respon instan, notifikasi toast, dan pemicuan fast-polling latar belakang.
3. **Penyelarasan Backend API (`server/main.py`):**
   - Memperkaya endpoint `/api/servers/{sid}/system` dengan telemetri `listening_ports`, `firewall`, `cron_jobs`, `ssl_certs`, `accounts`, dan `active_sessions_count`.
   - Menambahkan dukungan respons JSON (`is_json`) pada seluruh endpoint mutasi: `service_add_submit`, `_host_control` (reboot & poweroff), `problem_block_ip`, `firewall_block_ip`, `firewall_unblock_ip`, `firewall_enable`, `firewall_disable`, dan `firewall_reload`.
4. **Percepatan Polling & Anti-Cache Global pada Daftar Armada (`servers.html`, `dashboard.html`, `user_activity.html`):**
   - Mempercepat polling `servers.html` dari 10 detik menjadi 3 detik, menambahkan `id="srv-dot-{{ srv.id }}"` untuk update status dot online/offline/maintenance secara langsung tanpa refresh.
   - Menambahkan parameter anti-cache `?_=${Date.now()}` dan `cache: 'no-store'` pada seluruh polling `fetch` dashboard dan daftar server.
   - Mempercepat pembaruan riwayat aktivitas pengguna (`user_activity.html`) dari 60 detik menjadi 5 detik.

---

## Versi 4.6.8

- **Tipe Rilis:** Pemulihan Total Desain Asli Banner Darurat Kritis Tier-1 (*Restoration of Canonical Tier-1 Critical Red Banner Architecture*)
- **Fokus Utama:** Mengembalikan fungsi Alert Banner atas (`#alertBanner`) persis 100% ke spesifikasi arsitektur asli Pantau Server: Banner hanya memicu warna Merah Darurat (`banner-danger`) khusus untuk insiden Kritis (`danger`) pada layanan Tier-1 (atau bencana fatal), menghapus seluruh pemicuan banner untuk tingkat Gawat (`average`) dan Peringatan (`warning`), serta menghapus kelas CSS varian non-kritis.

### Rangkuman Pembaruan:
1. **Pemulihan Murni Banner Merah Kritis Tier-1 (*Canonical Tier-1 Red Emergency Banner*):**
   - Mengembalikan fungsi `renderAlerts` pada `base.html` agar secara ketat hanya mengaktifkan banner bila `dangerN > 0 && dangerList.length > 0`.
   - Menghapus percabangan `average` dan `warning` pada pemicuan banner atas. Layanan Tier-2 (Gawat) dan Tier-3 (Peringatan) secara ketat tidak pernah memicu banner atas, mengeliminasi alarm palsu (*alert fatigue*).
   - Menghapus class CSS `.alert-banner.banner-average` dan `.alert-banner.banner-warning`.
2. **Penyelarasan Backend Alerting (*Backend Tier-1 Danger Enforcement*):**
   - Menyelaraskan filter `open_danger` dan `_is_alert_banner_firing` pada `server/main.py` agar secara ketat hanya meloloskan insiden keparahan `danger` pada layanan berstatus Tier-1.

---

## Versi 4.6.7

- **Tipe Rilis:** Pemurnian Standar Arsitektur NOC Enterprise, Eliminasi Banner Info & Pemulihan Integritas Status Armada (*Enterprise NOC Banner Hygiene, Clean Host Status Restoration & Noise Elimination*)
- **Fokus Utama:** Menghapus implementasi banner untuk tingkat keparahan Info (seperti sesi remote SSH) yang tidak sesuai standar best practice enterprise monitoring dan menyebabkan banner menempel permanen, mengembalikan status armada pada tabel pengawasan ke status murni konektivitas dan daemon (Online / Offline / Pemeliharaan), memulihkan integritas warna badge dan dot standar, serta menghapus lonceng audio sintetis dan popup berlebih agar layar pemantauan tetap bersih, akurat, dan profesional.

### Rangkuman Pembaruan:
1. **Pembersihan Total Banner Peringatan Info (*Elimination of Info Severity Banner*):**
   - Menghapus varian banner info (`banner-info`) dari `base.html`, `server/main.py`, dan CSS global. Banner darurat atas dikembalikan khusus untuk insiden operasional nyata: Kritis (`banner-danger` merah), Gawat (`banner-average` oranye), dan Peringatan (`banner-warning` kuning).
   - Menghilangkan anomali banner persisten yang menempel terus-menerus di bagian atas antarmuka saat terdeteksi aktivitas sesi SSH atau telemetri informasi.
2. **Pemulihan Status Murni Armada (*Clean Host Status & Badge Integrity*):**
   - Mengembalikan `_server_status` pada `server/main.py`, `dashboard.html`, dan `servers.html` ke nilai status murni (Online / Offline / Pemeliharaan / Nonaktif) tanpa menimpa (*override*) label status server dengan tingkat keparahan insiden ("Info", "Kritis", dsb.).
   - Menghapus arsiran warna latar belakang baris tabel yang mengganggu estetika dan keterbacaan data ringkas (*NOC-density*).
3. **Penghapusan Polusi Suara & Notifikasi Liar (*Audio & Toast Noise Elimination*):**
   - Menghapus nada dering sintetis (`playNocChime`) dan kemunculan toast otomatis pada siklus polling latar belakang, menjaga ketenangan lingkungan operasional NOC.
   - Kejadian operasional dan anomali tetap terpantau secara mandiri dan reaktif pada tabel Insiden Terkini tanpa reload halaman.

---

## Versi 4.6.6

- **Tipe Rilis:** Transformasi Reaktivitas Visual NOC, Refleksi Status Riil Armada & Audio-Visual Alerting Tanpa Reload (*True Operational Health Reflection, Real-Time Event Ticker & Autonomous NOC UX*)
- **Fokus Utama:** Mengeliminasi tampilan status palsu "Normal/Online" saat ada insiden operasional/keamanan aktif, merefleksikan status kesehatan riil server pada tabel armada (Kritis, Gawat, Peringatan, Info, Normal), memperluas Alert Banner ke level Info Keamanan (sesi remote SSH), menambahkan deteksi diferensial kejadian seketika dengan notifikasi melayang (Toast) dan lonceng audio sintetis (Web Audio API), serta menghapus seluruh sisa reload paksa saat pembaruan sistem.

### Rangkuman Pembaruan:
1. **Refleksi Status Kesehatan Riil Server pada Tabel Armada (*Truthful Operational Status*):**
   - Memperbarui `_server_status` di `server/main.py` dan `pollNocDashboard` di `dashboard.html` agar status server dan warna indikator dot tidak lagi terkunci pada "Online" hijau bila terdapat masalah aktif.
   - Status server kini secara otomatis berubah warna dan label: Kritis (merah), Gawat (oranye), Peringatan (kuning), Info (biru), Normal (hijau), dan baris tabel diarsir halus sesuai keparahan kejadian.
2. **Banner Alert Multi-Level untuk Aktivitas Keamanan & Sesi Remote (`banner-info`):**
   - Memperluas Alert Banner di `base.html` dengan styling `.banner-info` (biru cyan) yang aktif menampilkan kejadian keamanan penting (seperti sesi remote SSH aktif) ketika tidak ada alarm darurat kritis yang sedang berjalan.
3. **Deteksi Diferensial Kejadian Seketika & Notifikasi Audio-Visual (*Live Event Ticker & Web Audio Chime*):**
   - Mengimplementasikan pelacakan diferensial kejadian per siklus polling (3 detik) pada `dashboard.html`. Saat ada insiden baru muncul atau terselesaikan, sistem secara mandiri menampilkan notifikasi mengambang (Toast) dan membunyikan nada lonceng distingtif tanpa reload.
4. **Eliminasi Total Reload Otomatis pada Pembaruan Sistem (*Zero Auto-Reload Guarantee*):**
   - Menghapus pemanggilan `window.location.reload()` pada fungsi `promptReload` di `base.html`, menggantikannya dengan sinkronisasi reaktif badge versi pada DOM agar layar operator tidak pernah terganggu atau ter-reload saat backend diperbarui.

---

## Versi 4.6.5

- **Tipe Rilis:** Eliminasi Total Caching Browser, Penghapusan Sisa Reload Paksa & Reaktivitas Penuh Antarmuka (*Zero-Reload Reactive Telemetry, Anti-Cache Middleware & Full Dynamic UX*)
- **Fokus Utama:** Mengeliminasi seluruh keharusan me-reload halaman untuk melihat perubahan status/kejadian pada antarmuka web, menerapkan middleware anti-cache global pada seluruh endpoint API agar browser tidak menyajikan data usang (*stale HTTP cache*), menghapus sisa pemanggilan `location.reload()` pada aksi penanganan peringatan, serta menambahkan polling latar belakang otomatis pada tab Manajer Tugas (Proses).

### Rangkuman Pembaruan:
1. **Middleware Anti-Cache Global pada Seluruh REST API (*No-Store HTTP Headers*):**
   - Menambahkan header `Cache-Control: no-store, no-cache, must-revalidate, max-age=0`, `Pragma: no-cache`, dan `Expires: 0` secara global untuk setiap respons pada path `/api/*` di `server/main.py`.
   - Mengatasi akar masalah heuristik browser caching yang selama ini membuat browser menyajikan cache memori lokal sehingga operator tidak melihat pembaruan data sebelum menekan tombol reload secara manual.
2. **Penghapusan Sisa `location.reload()` pada Aksi Operator (*Zero-Reload Action Confirmation*):**
   - Mengganti `location.reload()` pada fungsi `alertAck()` di `base.html` dengan pembaruan DOM reaktif seketika (`showToast`, `window.poll()`, `poll()`, `pollNocDashboard()`, `alertFetch()`).
3. **Reaktivitas Latar Belakang Tab Manajer Tugas (*Auto-Refreshing Process Manager*):**
   - Menambahkan interval polling otomatis (setiap 4 detik) untuk fungsi `fetchTopProcs()` saat tab Manajer Tugas (`tab-proses`) sedang aktif ditampilkan di layar operator, sehingga proses baru, pemakaian CPU/RAM proses, dan terminasi proses terbarui secara mandiri tanpa intervensi reload.

---

## Versi 4.6.4

- **Tipe Rilis:** Transparansi Telemetri Menyeluruh, Eliminasi Pembatasan Pelaporan & Banner Peringatan Multi-Level (*Full Telemetry Transparency, Zero Suppression & Fleet-Wide Multi-Level Alerting*)
- **Fokus Utama:** Memastikan seluruh kejadian dan anomali server klien (perubahan status unit systemd, sesi login/logout SSH, peningkatan beban, kegagalan layanan) terdeteksi dan tersaji secara seketika tanpa peredaman atau pembatasan siklus, memperluas Alert Banner ke tingkat Gawat (Average) dan Peringatan (Warning) untuk seluruh server, serta menyinkronkan urutan kronologis insiden antara backend dan antarmuka.

### Rangkuman Pembaruan:
1. **Banner Peringatan Multi-Level Seluruh Armada (*Fleet-Wide Multi-Level Alert Banner*):**
   - Memperluas cakupan Alert Banner di `base.html` dan `/api/alerts` agar tidak hanya terpaku pada insiden Kritis Tier-1, melainkan juga menampilkan insiden Gawat (`banner-average` oranye) dan Peringatan (`banner-warning` kuning) pada seluruh tingkatan server (Tier 1, Tier 2, Tier 3).
   - Menjamin kewaspadaan operator NOC terhadap kejadian server klien secara langsung dari satu halaman tanpa ada kejadian yang teredam.
2. **Penghapusan Pembatasan Deteksi Layanan (*Unsuppressed Service Event Reporting*):**
   - Menghapus peredaman waktu `< 3` detik pada `agent_report` di `server/main.py` sehingga kejadian layanan eksternal yang berhenti atau crash langsung dicatat seketika pada detak pelaporan pertama.
   - Mengeliminasi pembatasan modulo siklus (`_tick % 3 == 1`) pada pengumpulan unit layanan di daemon `agent_pantau.py`, sehingga unit systemd dilaporkan di setiap siklus bersama dengan telemetri akun dan sesi pengguna.
3. **Penyelarasan Pengurutan Kronologis & Transparansi Status Armada (*Synchronized Sorting & Truthful Status*):**
   - Menyelaraskan pengurutan daftar `all_open_problems` pada backend Python (`dashboard()`) dengan antarmuka JavaScript agar mengurutkan insiden terbaru di urutan paling atas (waktu mulai *descending*), menghilangkan efek lompatan baris (*jitter*) pada saat render awal.
   - Memperbaiki kalkulasi status tabel server agar memperhitungkan seluruh kategori kejadian (Danger, Average, Warning, Info) sehingga baris server tidak pernah menampilkan status hijau "Normal" secara keliru saat ada sesi SSH aktif atau pembaruan paket yang belum diproses.
   - Memperbarui indikator status icon insiden header (`dash-inc-icon`) untuk mengenali kondisi informasi aktif (`info`) dengan warna biru yang proporsional.

---

## Versi 4.6.3

- **Tipe Rilis:** Penghapusan Reload Paksa Antarmuka, Penyelarasan Reaktif & Deduplikasi Masalah (*Zero-Reload Incident Handling, Reactive Polling & Incident Deduplication*)
- **Fokus Utama:** Mengeliminasi seluruh pemanggilan reload paksa (`location.reload()`) pada aksi penanganan insiden dan pengabaian pemantauan, menerapkan pembaruan reaktif tanpa reload pada seluruh tabel insiden dan dashboard, mempercepat sinkronisasi saat tab peramban aktif (`visibilitychange`), serta membasmi duplikasi rekaman masalah di basis data.

### Rangkuman Pembaruan:
1. **Penghapusan Reload Paksa pada Tindakan Operator (*Zero-Reload Incident Handling*):**
   - Menghapus pemanggilan `location.reload()` pada fungsi `unignoreProblem()` dan `submitIgnoreProblem()` di `base.html`, serta `ackProblem()` di `problems.html`.
   - Menggantikannya dengan pola *reactive polling* instan (`window.poll()` / `pollNocDashboard()`), sehingga operator mendapatkan konfirmasi toast dan pembaruan baris seketika tanpa kehilangan fokus, posisi scroll, atau filter aktif.
2. **Pencegahan & Pembersihan Duplikasi Rekaman Insiden (*Incident Deduplication*):**
   - Menerapkan penguncian dan deduplikasi pada `sync_server_problems` di `server/main.py` sehingga jika terjadi eksekusi bersamaan, baris terbuka lama untuk key yang sama tidak diduplikasi, dan rekaman berlebih langsung ditutup otomatis (`duplicate_cleanup`).
   - Menerapkan filter `seen_open_keys` pada `problems_aggregate` agar daftar masalah terbuka dijamin unik per server dan per key anomali.
   - Membersihkan catatan duplikat yang ada pada basis data.
3. **Peningkatan Responsivitas Halaman Insiden (*Instant Tab Resync & Fast Polling*):**
   - Menambahkan event listener `visibilitychange` pada `problems.html` agar seketika melakukan sinkronisasi data saat tab kembali difokuskan oleh operator, mengatasi pembatasan throttling 60 detik bawaan peramban modern.
   - Mempercepat siklus polling latar belakang halaman masalah dari 5 detik menjadi 3 detik.

---

## Versi 4.6.2

- **Tipe Rilis:** Optimalisasi Responsivitas Real-Time & Eliminasi Jeda Status (*Zero-Delay Command Dispatch, Instant Telemetry & Real-Time Event Sync*)
- **Fokus Utama:** Mengeliminasi seluruh jeda buatan (*artificial delays*) dan pembatasan siklus pelaporan telemetri, sehingga seluruh aksi operator (dari dalam dashboard) maupun kejadian eksternal pada server klien (dari luar dashboard seperti SSH/CLI atau service crash) tercermin seketika secara real-time tanpa perlu reload halaman.

### Rangkuman Pembaruan:
1. **Responsivitas Eksekusi Perintah Seketika (*Zero-Delay Command Dispatch*):**
   - **Pelaporan Telemetri Instan Pasca-Eksekusi:** Pada loop worker perintah agen (`_command_worker_loop`), setelah perintah (seperti restart, stop, start, reboot, kill) selesai dieksekusi, agen langsung mengirimkan laporan telemetri terbaru (`run_once(cfg)`) dengan jeda transisi systemd hanya 300ms, tanpa menunggu jadwal interval siklus utama.
   - **Peningkatan Frekuensi Polling Perintah:** Interval polling perintah pada daemon agen ditingkatkan dari 1.5 detik menjadi 1.0 detik untuk eksekusi yang lebih cepat dan responsif.
2. **Eliminasi Kunci Antarmuka Operasi Layanan (*UI Pending Lock Clearance*):**
   - **Penanganan Status Restart pada UI:** Memperbaiki logika `patch(data)` pada `services.html` yang sebelumnya tidak menghapus kunci operasi pending untuk aksi `restart` saat status layanan kembali `up`. Hal ini sebelumnya menyebabkan baris layanan terkunci dalam status *"me-restart..."* selama 30 detik kecuali pengguna me-reload halaman.
   - **Pemangkasan Batas Waktu Kunci Pending:** Mengurangi batas waktu penguncian tombol operasi restart dari 30 detik menjadi 10 detik sebagai proteksi gagal (*fail-safe*).
   - **Sinkronisasi Status Overview:** Menambahkan pengenalan perintah `restart` dan `service_restart` pada `api_server_overview` agar badge metrik ringkasan langsung mencerminkan status aktif pasca-tindakan.
3. **Pendeteksian Seketika Kejadian Eksternal (*External Event Detection*):**
   - **Penghapusan Jeda Buatan Transisi Down:** Menghapus penahanan status metrik 45 detik pada server pusat saat layanan mati/berhenti dari luar (misal dimatikan via SSH/CLI atau crash). Waktu toleransi dipangkas menjadi 3 detik, sehingga server pusat langsung mendeteksi dan mencatat status `down` saat agen melaporkannya.
   - **Telemetri Sesi Pengguna & SSH Real-Time:** Menghapus pembatasan siklus (`_tick % 3 == 1`) pada pengumpulan akun dan sesi login pengguna (`collect_accounts()`). Agen kini memeriksa dan melaporkan sesi aktif di setiap siklus detak, mendeteksi login/logout SSH secara seketika.
4. **Peningkatan Frekuensi Telemetri & Polling Dashboard:**
   - **Interval Detak Agen 5 Detik:** Menurunkan interval telemetri default agen dari 10 detik menjadi 5 detik pada seluruh konfigurasi baru (`package/install.sh`, `agent_pantau.py`, `/etc/pantau/config.json`).
   - **Polling Cepat Dashboard:** Mengurangi interval polling background dashboard dari 5.0 detik menjadi 3.0 detik, serta menambahkan event listener `visibilitychange` agar dashboard seketika melakukan polling saat operator kembali fokus ke tab peramban.

---

## Versi 4.6.1

- **Tipe Rilis:** Sinkronisasi Antarmuka Otomatis (*Live Version Watcher, Anti-Stale Caching & Real-Time Badge Updating*)
- **Fokus Utama:** Mengeliminasi kebutuhan reload manual (F5) oleh operator dengan menyematkan pengawas versi live latar belakang di browser, proteksi form aktif, header anti-stale cache, serta penyegaran dinamis badge Tier dan paket APT.

### Rangkuman Pembaruan:
1. **Mesin Sinkronisasi Otomatis (*Live Version Watcher*):**
   - **Endpoint Versi & Waktu Boot Backend (`/api/system/version`):** Menyediakan metadata versi aktif dan waktu boot server pusat untuk pemantauan latar belakang oleh browser klien.
   - **Penyegaran Mulus di Browser (`base.html`):** Setiap tab browser memantau versi dan waktu hidup server. Ketika terjadi pembaruan rilis atau restart layanan backend, antarmuka otomatis menyinkronkan diri dan memuat ulang halaman secara mulus disertai notifikasi toast informatif.
   - **Proteksi Pengguna Sedang Berinteraksi (*Interaction Guard*):** Jika pengguna sedang mengetik dalam formulir input, membuka modal dialog, atau menjalankan terminal aktif, auto-reload otomatis ditangguhkan dan digantikan dengan banner mengambang yang tidak mengganggu alur kerja.
2. **Penghapusan Cache Usang Browser (*Anti-Stale Caching*):**
   - Menambahkan header `Cache-Control: no-cache, no-store, must-revalidate`, `Pragma: no-cache`, dan `Expires: 0` pada seluruh respons render template Jinja (`tpl()`) untuk memastikan browser tidak menahan salinan HTML usang.
3. **Penyelarasan Dinamis Badge Tier & Status APT Tanpa Reload:**
   - Menghubungkan badge prioritas server klien (`#hero-tier-badge`) ke dalam siklus polling `patch(data)` di halaman rincian server, sehingga perubahan Tier langsung diperbarui seketika tanpa perlu reload.
   - Menjalankan pembaruan dinamis status dan tombol paket APT secara periodik di dalam `pollSystem()`.

---

## Versi 4.6.0

- **Tipe Rilis:** Fitur Mayor Pemantauan S.M.A.R.T. & NVMe, Engine Probing Jaringan, Step-Up Auth File Manager, dan Optimalisasi Antarmuka NOC
- **Fokus Utama:** Implementasi telemetri kesehatan fisik drive penyimpanan (S.M.A.R.T. dan NVMe) dengan deteksi virtual host, perbaikan proses diagnostik pembaruan APT yang macet, standardisasi ukuran badge server klien menjadi ringkas dan proporsional, serta integrasi aturan baku pengembangan (*Antigravity Skill & Rule SOP*).

### Rangkuman Pembaruan:
1. **Telemetri Kesehatan Drive S.M.A.R.T. & NVMe:**
   - **Kolektor Telemetri Agen:** Agen mengumpulkan telemetri status kesehatan hard drive dan solid state drive menggunakan utilitas `smartctl` dan `nvme-cli`.
   - **Deteksi Drive Virtual & Pencegahan Alarm Palsu:** Mengidentifikasi disk virtual pada lingkungan Proxmox VM/QEMU, KVM, VirtIO, dan LXC container dengan label `Virtual (Host)` sehingga tidak memicu kesalahan diagnostik atau alarm palsu.
   - **Evaluasi Masalah Penyimpanan Otomatis:** Sistem mengevaluasi drive failing (`disk_smart_failing`), suhu kritis di atas 60°C (`disk_smart_temp`), keausan media penyimpanan dengan sisa usia di bawah 10% (`disk_smart_wear`), dan sektor rusak bertambah (`disk_smart_sectors`) lengkap dengan rincian diagnosa akar masalah dan saran mitigasi sysadmin.
   - **Tabel Penyimpanan Terpadu:** Antarmuka rincian server menampilkan tabel partisi mount point berdampingan dengan kolom Model Drive, Status S.M.A.R.T., Suhu, Sisa Usia, dan Jam Kerja (*Power-on Hours*).
2. **Perbaikan Pemeriksaan Paket Pembaruan APT:**
   - **Pra-render Sisi Server:** Mengeliminasi tampilan teks menggantung *"Memeriksa pembaruan…"* saat memuat halaman dengan melakukan pra-render status paket dari database cache.
   - **Perbaikan Pemanggilan Pagination:** Memperbaiki kesalahan fatal JavaScript `TypeError: pag.refresh is not a function` menjadi `pag.update()` pada modul `renderApt()` yang sebelumnya menyebabkan eksekusi antarmuka terhenti.
3. **Penyelarasan & Kepadatan Badge Header Server:**
   - Mengubah ukuran badge prioritas server klien menjadi 9.5px, dengan penulisan huruf kecil natural (`tier-1`, `tier-2`, `tier-3`) dan padding rapat (1px 6px) agar hemat ruang vertikal dan tidak mengalihkan perhatian operator.
   - Menyelaraskan badge versi agen klien (`agen v4.6.0`) dengan ukuran font 9.5px yang serasi dan konsisten.
4. **Mesin Probing Endpoint Jaringan Terjadwal:**
   - Modul pengujian berkala endpoint HTTP/HTTPS, port TCP, resolusi DNS, dan ICMP Ping dengan riwayat latensi terperinci, grafik tren, serta pencatatan audit log otomatis.
5. **Otentikasi Bertingkat (Step-Up Auth) File Manager:**
   - Perlindungan sesi penjelajahan berkas dengan kata sandi akun untuk akses file sensitif dan tombol kunci/buka sesi yang terintegrasi.
6. **Integrasi SOP Baku & Kustomisasi Antigravity:**
   - Pembuatan skill resmi `.agents/skills/sop-pantau/SKILL.md` dan aturan *always-on* `GEMINI.md` untuk mengunci prosedur wajib kenaikan SemVer, verifikasi sintaksis, serta siklus otomatis commit, tag, dan GitHub Release.

---

## Versi 4.5.32

- **Tipe Rilis:** Penyelarasan Posisi Tengah Layar Header Dashboard & Logo Utuh (*Dashboard Header Centering & Uncropped Logo*)
- **Fokus Utama:** Memposisikan tiga baris judul dan identitas organisasi (`PANTAU SERVER`, `Nama Organisasi`, `Nama Unit Kerja`) tepat di tengah layar (*absolute horizontal center*), menempatkan logo organisasi di sebelah kiri tanpa memotong gambar (*object-fit: contain*), serta menyelaraskan struktur serupa pada halaman login dan menu pratinjau profil.

### Rangkuman Pembaruan:
1. **Posisi Tengah Layar Penuh pada Header Dashboard:**
   - Menyusun kontainer teks identitas (`.dash-brand-wrap`) tepat di sumbu tengah halaman, dengan logo diletakkan di sisi kiri secara presisi (`position: absolute; right: calc(100% + 18px)`).
   - Menjamin seluruh teks identitas dan pengumuman operasional berada tepat di garis tengah layar tanpa tergeser oleh lebar logo.
2. **Pencegahan Logo Terpotong pada Halaman Login & Dashboard:**
   - Memastikan logo menggunakan `object-fit: contain` dengan lebar dinamis proporsional (`max-width: 130px; height: 100%`) sehingga logo tidak terpotong pada format gambar apa pun (16:9, persegi, maupun vertikal).
   - Batas atas dan bawah logo tetap menyentuh batas judul dan unit kerja secara presisi.
3. **Penyelarasan Pratinjau pada Menu Setel Organisasi:**
   - Memperbarui komponen simulasi pratinjau login dan dashboard di menu Profil agar menggunakan struktur tengah dan penanganan logo utuh yang sama.

---

## Versi 4.5.31

- **Tipe Rilis:** Pembaruan Posisi & Teks Hak Cipta (*Copyright Positioning & Text Standardization*)
- **Fokus Utama:** Menempatkan baris hak cipta selalu di posisi paling bawah layar/halaman (termasuk halaman login dan verifikasi 2FA) dan membakukan teks hak cipta menjadi `© 2026 Pantau-Server`.

### Rangkuman Pembaruan:
1. **Penataan Posisi Hak Cipta Paling Bawah Layar:**
   - Menyusun kontainer halaman login (`login.html`) dan verifikasi 2FA (`login_2fa.html`) menggunakan flexbox vertikal berjarak fleksibel (`margin: auto 0` pada kartu form login dan `margin-top: auto` pada footer), sehingga elemen hak cipta selalu berada di dasar layar/halaman (*bottom of screen*).
2. **Standardisasi Teks Hak Cipta:**
   - Mengubah redaksi hak cipta di seluruh aplikasi (`base.html`, `login.html`, `login_2fa.html`, serta pratinjau login pada `profile.html`) menjadi:
     `&copy; 2026 Pantau-Server`.

---

## Versi 4.5.30

- **Tipe Rilis:** Presisi dan Keseimbangan Tata Letak Header Login (*Login Header Precision & Balanced Layout*)
- **Fokus Utama:** Penyelarasan presisi pada halaman login sehingga kartu form login berada tepat di tengah bawah nama unit kerja dan judul `PANTAU SERVER`, dengan logo organisasi di sisi kiri yang membentang rata dari sisi atas judul hingga sisi bawah nama unit kerja.

### Rangkuman Pembaruan:
1. **Presisi Sumbu Tengah Kartu Login:**
   - Menyeimbangkan kontainer baris identitas (`.brand-row`) menggunakan elemen penyeimbang simetris (`.brand-spacer`), sehingga sumbu tengah teks (`PANTAU SERVER`, `Nama Organisasi`, `Nama Unit Kerja`) dan kartu form login berada tepat pada satu garis tengah vertikal (*centerDelta = 0*).
   - Memastikan kartu login berada tepat di tengah bawah unit kerja.
2. **Kesejajaran Vertikal Logo Organisasi:**
   - Logo organisasi di sisi kiri membentang dengan skala proporsional penuh (*64px*) dari batas atas judul `PANTAU SERVER` hingga batas bawah `Nama Unit Kerja` (*topDelta = 0, bottomDelta = 0*).
   - Menambahkan penyesuaian adaptif ketinggian otomatis (*44px*) jika unit kerja tidak diisi.
3. **Penyelarasan Pratinjau Login di Menu Setel Organisasi:**
   - Memperbarui simulasi pratinjau login di menu Profil agar menggunakan struktur seimbang yang identik dengan halaman login produksi.

---

## Versi 4.5.29

- **Tipe Rilis:** Penyelarasan Tata Letak Header Dashboard (*Dashboard Header Layout Alignment*)
- **Fokus Utama:** Penerapan tata letak identitas organisasi yang seragam pada dashboard utama, menempatkan logo organisasi di sisi kiri blok teks (`PANTAU SERVER`, `Nama Organisasi`, dan `Nama Unit Kerja`) dengan ketinggian vertikal sejajar, serta penyelarasan pratinjau dashboard di menu Setel Organisasi.

### Rangkuman Pembaruan:
1. **Penerapan Header Identitas Seragam pada Dashboard Utama:**
   - Menyusun kontainer baris fleksibel (`.dash-brand-row`) pada header dashboard saat identitas organisasi aktif.
   - Logo organisasi ditempatkan di sisi kiri dengan skala proporsional yang membentang dari batas atas judul `PANTAU SERVER` hingga batas bawah `Nama Unit Kerja`.
   - Menjaga tampilan pengumuman operasional `("...")` tetap terpusat di bawah blok identitas saat toggle tampilan aktif.
2. **Penyelarasan Pratinjau Dashboard di Menu Profil:**
   - Memperbarui komponen `Pratinjau Dashboard` pada tab *Setel Organisasi* agar mengadopsi struktur logo kiri dan judul `PANTAU SERVER` yang selaras dengan tampilan dashboard produksi.

---

## Versi 4.5.28

- **Tipe Rilis:** Penyempurnaan Tata Letak Header Login (*Login Header Layout Enhancement*)
- **Fokus Utama:** Penataan logo organisasi di sisi kiri blok teks header login dengan ketinggian yang selaras dari batas atas judul (*PANTAU SERVER*) hingga batas bawah unit kerja (*Bidang Aplikasi dan Informatika*), serta penyelarasan pratinjau profil.

### Rangkuman Pembaruan:
1. **Penataan Logo di Sisi Kiri Header Login:**
   - Menyusun kontainer baris fleksibel (`.brand-row`) pada header halaman login dengan logo organisasi berada di sebelah kiri.
   - Sisi atas logo sejajar secara vertikal dengan judul utama `PANTAU SERVER`.
   - Sisi tengah logo sejajar dengan `Nama Organisasi`.
   - Sisi bawah logo sejajar dengan `Nama Unit Kerja`.
   - Logo otomatis menyesuaikan tinggi kolom teks secara proporsional (`height: 100%; max-height: 64px; max-width: 85px; object-fit: contain;`).
2. **Penyelarasan Pratinjau Interaktif Menu Profil:**
   - Memperbarui simulasi `Pratinjau Halaman Login` di tab *Setel Organisasi* agar mengadopsi struktur logo di sisi kiri sejajar dengan blok teks.

---

## Versi 4.5.27

- **Tipe Rilis:** Pembersihan Visual Antarmuka (*UI Visual Cleanup*)
- **Fokus Utama:** Penghapusan indikator badge `● live` pada header dashboard (baik saat identitas organisasi aktif maupun saat teks default), pratinjau profil dashboard, serta header halaman daftar server, menghasilkan tampilan atas yang lebih bersih, fokus, dan rapi tanpa elemen kedip yang mendistraksi.

### Rangkuman Pembaruan:
1. **Penghapusan Indikator `● live` pada Dashboard:**
   - Menghilangkan badge `● live` dari baris Nama Organisasi pada header dashboard utama terpusat.
   - Menghilangkan badge `● live` dari judul default `Dashboard`.
2. **Penyelarasan Pratinjau Profil (Live Preview):**
   - Menghapus badge `● live` pada pratinjau header dashboard di menu Setel Organisasi.
3. **Pembersihan pada Halaman Daftar Server:**
   - Menghapus badge `● live` pada toolbar daftar server (`servers.html`).

---

## Versi 4.5.26

- **Tipe Rilis:** Penyempurnaan Tampilan & Standarisasi Terminologi Antarmuka (*UI Refinement & Terminology Standardization*)
- **Fokus Utama:** Penyempurnaan layout header dashboard (tengah, tanpa kartu, tanpa tombol kelola), standarisasi 1 baris teks organisasi pada halaman login, pengecilan ikon overview/logo, konsistensi istilah "Setel Organisasi" dan "Pengumuman", pengikatan toggle tampilan khusus untuk pengumuman, serta simplifikasi tombol simpan.

### Rangkuman Pembaruan:
1. **Standarisasi Tata Letak Halaman Login (1 Baris Nama Organisasi):**
   - Menyesuaikan lebar kontainer `.login-box` (hingga 720px) dengan kartu login tetap proporsional (390px centered).
   - Menetapkan aturan `white-space: nowrap; overflow: hidden; text-overflow: ellipsis;` agar nama organisasi panjang selalu tersaji rapi dalam 1 baris di halaman login dan pratinjau.
2. **Rekonfigurasi Header Dashboard Terpusat (Centered Overview Header):**
   - Menggantikan teks default (*"Dashboard & Ringkasan kondisi terkini..."*) dengan header identitas terpusat saat nama organisasi diatur.
   - Menghilangkan container kartu banner dan tombol "Kelola" untuk tampilan yang lebih bersih, elegan, dan profesional.
   - Menyusun hierarki vertikal terpusat: Baris 1: Nama Organisasi (dengan ikon live & logo ringkas maks 22px), Baris 2: Unit Kerja, Baris 3: Pengumuman berformat `("...")`.
3. **Penyempurnaan Ikon Overview / Logo Dashboard:**
   - Mengecilkan ukuran logo pada header dashboard (`max-height: 22px; max-width: 70px; object-fit: contain`) agar proporsional dan tidak mendominasi layar.
4. **Konsistensi Terminologi & Pengaturan (Strict Naming Standards):**
   - Mengganti seluruh frasa tab, heading, audit trail, dan pesan flash menjadi **"Setel Organisasi"**.
   - Menghapus penggunaan kata ambigu seperti "lembaga", "pesan operasional", dan "MOTD", digantikan secara konsisten dengan istilah **"organisasi"** dan **"pengumuman"**.
   - Menyederhanakan tombol aksi simpan menjadi **"SIMPAN"**.
5. **Cakupan Khusus Toggle Tampilan:**
   - Memastikan toggle tampilan hanya mengatur visibilitas baris pengumuman `("...")`, sedangkan nama organisasi, unit kerja, dan logo tetap ditampilkan.

---

## Versi 4.5.25

- **Tipe Rilis:** Rilis Fitur & Personalisasi Antarmuka (*Feature & Branding Logo Upload*)
- **Fokus Utama:** Fitur unggah logo organisasi kustom (PNG, SVG, JPG, WebP), pratinjau instan sebelum simpan, opsi hapus logo kustom kembali ke lambang bawaan, serta integrasi visual logo pada halaman login dan bilah dashboard.

### Rangkuman Pembaruan:
1. **Fitur Unggah Logo Organisasi (Custom Logo Upload):**
   - Menambahkan input berkas logo pada form pengaturan identitas di menu Profil.
   - Mendukung format gambar standar (`.png`, `.svg`, `.jpg`, `.jpeg`, `.webp`, `.ico`) dengan batas ukuran hingga 2 MB.
   - Manajemen berkas aman tersimpan di direktori `server/static/uploads/` dengan pencegahan duplikasi file lama.
   - Opsi *Hapus Logo* untuk mengembalikan tampilan ke lambang SVG minimalis standar.
2. **Pratinjau Logo Interaktif (Live Client-Side Preview):**
   - Menggunakan FileReader HTML5 untuk menampilkan pratinjau logo secara instan pada simulasi halaman login dan bilah dashboard seketika saat berkas dipilih oleh operator.
3. **Penyajian Logo Responsif pada Antarmuka:**
   - Menampilkan logo kustom pada header halaman login di antara judul `PANTAU SERVER` dan nama instansi/organisasi.
   - Menampilkan logo kustom pada bilah pengumuman operasional (MOTD banner) di dashboard utama.

---

## Versi 4.5.24

- **Tipe Rilis:** Rilis Fitur & Personalisasi Antarmuka (*Feature & Branding Personalization*)
- **Fokus Utama:** Kustomisasi interaktif identitas organisasi (Nama Lembaga, Unit Kerja), pesan operasional harian (MOTD), toggle tampilan pengumuman, perapian tata letak halaman login minimalis, dan penambahan copyright universal seluruh halaman sistem.

### Rangkuman Pembaruan:
1. **Pengaturan Identitas & Pengumuman Organisasi (Branding & MOTD):**
   - Penambahan tab interaktif baru *Identitas & Pengumuman* pada menu Profil untuk Master Admin dan Operator.
   - Manajemen 4 parameter: Nama Organisasi, Unit Kerja, Pesan Operasional (MOTD), dan Toggle Tampilan (Checkbox).
   - Fitur pratinjau interaktif langsung (*Live Interactive Preview*) untuk mensimulasikan header login dan bilah MOTD dashboard secara instan saat operator mengetik.
   - Penyimpanan persisten ke tabel `system_settings` dengan pencatatan audit log `branding_update`.
2. **Standardisasi Halaman Login Bersih & Rapi:**
   - Menata ulang header login terpusat: `PANTAU SERVER` &rarr; `<Logo Organisasi>` &rarr; `<Nama Organisasi / Unit Kerja>`.
   - Menjaga kartu otentikasi tetap minimalis, bersih, dan elegan tanpa elemen visual yang berlebihan.
3. **Bilah Operasional Dashboard (MOTD Banner):**
   - Menampilkan bilah status operasional di bawah topbar dashboard ketika opsi toggle tampilan aktif.
   - Dilengkapi tautan kelola cepat bagi pengguna dengan hak akses operator.
4. **Hak Cipta Terpusat Universal (Universal Copyright Footer):**
   - Menambahkan footer hak cipta `© 2026 Azhuka Praja Muda Karana` pada bagian bawah tengah di seluruh halaman aplikasi (`base.html`, `login.html`, `login_2fa.html`).

---

## Versi 4.5.23

- **Tipe Rilis:** Rilis Pemeliharaan & Standardisasi Bahasa (*Maintenance & Documentation Standards*)
- **Fokus Utama:** Penyederhanaan redaksi kalimat antarmuka (UI/UX), standarisasi terminologi teknis sysadmin pada seluruh dokumentasi (`README.md`, `DEVELOPMENT.md`), serta perapian informasi catatan rilis GitHub.

### Rangkuman Pembaruan:
1. **Penyempurnaan Bahasa & Nomenklatur Aplikasi:**
   - Mengubah istilah non-standar atau hiperbolis (seperti *gawat darurat*, *penyerang*, *kebal*, *mati*) menjadi istilah teknis yang baku (*Insiden Kritis*, *Alamat IP Sumber*, *Akun Terlindungi*, *Shutdown*).
   - Menyederhanakan 12 label dan subtitle antarmuka agar lebih ringkas, informatif, dan tidak memakan ruang visual berlebih.
   - Menyelaraskan teks banner insiden global, modal peringatan, dan diagnosa teknis agar menggunakan bahasa Indonesia yang lugas dan profesional.
2. **Restrukturisasi Dokumentasi Proyek:**
   - Menulis ulang `README.md` dengan struktur yang lebih bersih, mudah dipahami oleh sysadmin, dan mencerminkan kapabilitas sistem terkini (termasuk eskalasi 1 menit Tier-1).
   - Memperbarui panduan arsitektur pada `DEVELOPMENT.md` agar bebas dari analogi yang membingungkan serta menggunakan istilah teknis yang tepat.
3. **Penyelarasan Catatan Rilis GitHub:**
   - Merapikan judul dan ringkasan catatan rilis pada repositori GitHub agar terstruktur dan mudah dipelajari oleh publik maupun tim internal.

---

## Versi 4.4.1

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — *Offline Server Incident Ignore Support & Operator Intentional Action Ignore Lifecycle Correction*.

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.4.1
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 4  (Minor) : Sistem Klasifikasi Kepentingan Layanan (Level Operasional Tier 1/2/3), Matriks Keparahan Insiden Multi-Tier, Pembagian Peran Layanan Utama/Sekunder, dan Klasifikasi Sadar Operator
 └── 1  (Patch) : Perbaikan Tombol Abaikan pada Server Offline, Siklus Hidup Pengabaian Tindakan Operator, & Penyempurnaan Label Level Operasional
```

---

### Peningkatan & Perbaikan Bug — Versi 4.4.1 (Patch Release)

1. **Dukungan Pengabaian (*Ignore / Mute*) Insiden pada Server Offline:**
   - **Latar Belakang Masalah:** Pada halaman Rincian Server (`/servers/{sid}/services`) tab *Riwayat & Masalah*, tombol "Abaikan" tidak dapat diklik atau memunculkan pesan toast peringatan ketika server berstatus offline, padahal tombol abaikan pada menu Insiden Global (`/problems`) berfungsi normal.
   - **Solusi Implementasi:**
     - Menghapus guardrail frontend `typeof IS_ONLINE !== 'undefined' && !IS_ONLINE` pada fungsi `openIgnoreModal` dan `unignoreProblem` di [`server/templates/base.html`](file:///home/bos/rj45/server/templates/base.html).
     - Menghapus pembatasan atribut `disabled` berbasis kondisi offline pada tombol Abaikan dan Pantau layanan di [`server/templates/services.html`](file:///home/bos/rj45/server/templates/services.html) (baik pada saat SSR Jinja2 maupun re-render dinamis JS `renderServiceActions`).
     - Aksi pengabaian insiden merupakan mutasi data operasional di database dashboard pusat yang tidak memerlukan interaksi soket RPC langsung ke agen klien, sehingga kini dapat dioperasikan secara konsisten di seluruh halaman tanpa terhalang status online/offline host.

2. **Perbaikan Siklus Hidup Pengabaian Tindakan Sadar Operator (*Operator Intentional Action Lifecycle*):**
   - **Latar Belakang Masalah:** Ketika operator sengaja mematikan server (*Power Off Host*) atau mematikan layanan (*Stop Service*), insiden berhasil diklasifikasikan ke keparahan **🟡 PERINGATAN (`warning`)** sebagai insiden aktif (`is_ignored = 0`). Namun, ketika operator secara eksplisit mengklik tombol "Abaikan", insiden tidak dapat berpindah ke daftar keparahan *Diabaikan* dan tidak keluar dari total insiden Peringatan karena fungsi sinkronisasi periodik `sync_server_problems` secara terus-menerus menimpa dan me-reset `is_ignored = 0`.
   - **Solusi Implementasi:**
     - Memperbaiki logika rekonsiliasi pada [`server/main.py`](file:///home/bos/rj45/server/main.py) fungsi `sync_server_problems`: status awal saat terdeteksi tindakan sadar operator tetap berstatus aktif (`is_ignored = 0`), tetapi apabila operator telah melakukan pengabaian manual (`row.is_ignored == 1`), status pengabaian tersebut dipertahankan dan tidak di-reset ke 0.
     - Insiden tindakan sadar yang diabaikan kini secara tepat keluar dari total/daftar keparahan aktif Peringatan dan masuk ke kategori *Diabaikan* (`is_ignored = 1`).
     - Jika operator memilih "Pantau Kembali", insiden kembali ke status aktif keparahan Peringatan.
     - Menyempurnakan endpoint API `api_alert_ignore` dan `api_service_ignore` agar mempertahankan riwayat alasan operator (`row.ignored_reason = reason or row.ignored_reason`) apabila modal abaikan disubmit tanpa mengisi alasan khusus baru.

3. **Penyempurnaan Label Klasifikasi Kepentingan Layanan (Level Operasional):**
   - Menyelaraskan teks pada form input server (`server_form.html`), badge rincian server (`services.html`), dan tooltip dashboard agar ringkas dan on-point:
     - `Tier 1 — Layanan Utama / Prioritas` (Layanan vital & Prioritas).
     - `Tier 2 — Layanan Pendukung / Sekunder` (Layanan Pendukung operasional).
     - `Tier 3 — Layanan Sementara / Non-Kritis` (Layanan bersifat sementara/uji coba).

4. **Tombol Aksi Cepat Edit & Hapus pada Halaman Rincian Server (`services.html`):**
   - Menambahkan tombol **Edit** dan **Hapus** langsung pada topbar header halaman rincian server ([`server/templates/services.html`](file:///home/bos/rj45/server/templates/services.html)) di samping tombol navigasi `← Servers`.
   - Tombol Hapus server dilengkapi dialog konfirmasi proteksi sistem (*guardrail modal*) dengan perlindungan token CSRF.
   - Memutakhirkan endpoint `POST /servers/{sid}/delete` di [`server/main.py`](file:///home/bos/rj45/server/main.py) agar dapat diakses oleh Master Admin dan Operator yang memiliki hak izin `can_manage_servers`.
   - Operator tidak perlu lagi beralih kembali ke halaman daftar server hanya untuk mengubah konfigurasi atau menghapus server yang sedang diperiksa.

5. **Penyelarasan Nama Kolom Tabel Daftar Server Menjadi INSIDEN:**
   - Mengubah judul kolom tabel pada [`server/templates/servers.html`](file:///home/bos/rj45/server/templates/servers.html) dari sebelumnya **Masalah** menjadi **Insiden** agar sinkron dengan terminologi global aplikasi (*Menu Insiden*, *Kartu Insiden Terkini*, badge status keparahan).

---

## Versi 4.4.0

- **Release Label:** None
- **Tipe Rilis:** Rilis Minor (*Minor Release*) — *Klasifikasi Kepentingan Layanan (Level Operasional), Core vs Secondary Service Role Segmentation, and Operator Action Warning Classification*.

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.4.0
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 4  (Minor) : Sistem Klasifikasi Kepentingan Layanan (Level Operasional), Matriks Keparahan Insiden Multi-Tier, Pembagian Peran Layanan Utama/Sekunder, dan Klasifikasi Sadar Operator
 └── 0  (Patch) : Rilis Awal Arsitektur 4.4.0
```

---

### Fitur Baru & Peningkatan Arsitektur — Versi 4.4.0 (Minor Release)

1. **Sistem Klasifikasi Kepentingan Layanan (Level Operasional):**
   - **Tier 1 — Layanan Utama / Prioritas:** Server dengan fungsi dan peran vital utama yang tidak boleh terhenti. Bencana fatal (host offline $\ge 300\text{s}$, partisi disk read-only, disk penuh 100%, core service crash) dievaluasi sebagai **🔴 KRITIS (`danger`)**. Menjadi **satu-satunya** tier yang memicu Banner Merah `#alertBanner` dan Sirene Audio Darurat NOC.
   - **Tier 2 — Layanan Pendukung / Sekunder:** Server pendukung kelancaran operasional sistem. Host offline $\ge 120\text{s}$ atau layanan inti down dievaluasi sebagai **🟠 GAWAT (`average`)**, dan secara ketat tidak pernah memicu banner merah maupun sirene darurat.
   - **Tier 3 — Layanan Sementara / Non-Kritis:** Server pengujian, staging, atau sementara yang tidak berdampak langsung ke operasional sistem. Gangguan atau pemadaman server maksimal hanya berstatus **🟡 PERINGATAN (`warning`)**, mengeliminasi alarm palsu (*alert fatigue*).

2. **Klasifikasi Peran Layanan (Core vs Secondary Services):**
   - Penambahan kolom `is_core` (default 1) pada tabel `services` untuk membedakan layanan utama aplikasi (*Core Service*) dari layanan pendukung (*Secondary Service*, seperti Redis cache, Zabbix agent, systemd-resolve).
   - Layanan sekunder yang mati pada server Tier 1 hanya menghasilkan keparahan **🟡 PERINGATAN (`warning`)**, bukan KRITIS, menjaga proporsionalitas respon tim NOC.
   - Penambahan toggle cepat 1-klik peran layanan (`POST /servers/{sid}/services/{svc_id}/toggle-core`) dan badge visual `UTAMA` / `SEKUNDER` pada halaman detail service.

3. **Klasifikasi Tindakan Sadar Operator (Operator Intentional Action Classification):**
   - Seluruh tindakan pemadaman yang disengaja oleh operator (*Power Off Host* atau *Stop Service*) otomatis diklasifikasikan sebagai **🟡 PERINGATAN (`warning`)** di semua tier.
   - Insiden tetap berstatus aktif (`is_ignored = 0`) dan dicatat transparan di kartu *Insiden Terkini* dengan label `DIMATIKAN OLEH OPERATOR (Nama Operator)`, namun secara ketat **tidak memicu** banner merah `#alertBanner` maupun sirene audio darurat.

4. **Migrasi Skema Database Relasional:**
   - `ALTER TABLE servers ADD COLUMN tier SMALLINT NOT NULL DEFAULT 2 AFTER group_name;`
   - `ALTER TABLE services ADD COLUMN is_core SMALLINT NOT NULL DEFAULT 1 AFTER process_name;`
   - Pemutakhiran model ORM SQLAlchemy [`Server`](file:///home/bos/rj45/server/models.py#L32) dan [`Service`](file:///home/bos/rj45/server/models.py#L52).

5. **Penyempurnaan UI/UX & Tampilan Dashboard:**
   - Penambahan input seleksi Tier Aset pada formulir pendaftaran dan edit server (`server_form.html`).
   - Badge visual Tier (`TIER 1`, `TIER 2`, `TIER 3`) pada tabel armada server, grid view card, dan inventory list.
   - Desain kartu insiden terkini satu-baris (*single line*) yang bersih, bebas tumpukan teks (*layout shift*), dan sinkronisasi realtime dengan strip total widget Zabbix-style.

---

## Versi 4.2.21

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Penguatan Keamanan Web Terminal Root via *Sudo-Style Step-Up Authentication* & *Ephemeral Lease Session*, Nonaktifkan Akses Terminal secara Bawaan (*Disabled by Default*), dan Pembersihan Ikon UI Minimalis Bebas Emoji Berlebihan

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.21
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 21 (Patch) : Sudo-Style Step-Up Challenge & Ephemeral Lease Terminal Root, Safe-by-Default allow_web_terminal, dan Standarisasi Ikon SVG Minimalis
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.21 (Patch Release)

1. **Penguatan Keamanan Web Terminal Root (*Sudo-Style Step-Up Challenge*):**
   - Akses web terminal interaktif root pada detail server kini terkunci secara bawaan dan mewajibkan otentikasi ulang (*step-up authentication challenge*) menggunakan kata sandi akun pengguna dan kode 2FA TOTP (bila akun mengaktifkan 2FA).
   - Menghasilkan sewa akses sementara (*ephemeral lease*) dengan durasi terukur (15, 30, atau 60 menit) serta kolom catatan tujuan/alasan akses yang diaudit secara transparan ke tabel audit log.
   - Endpoint WebSocket `/ws/servers/{sid}/terminal` dan API runner memvalidasi status lease aktif secara ketat dan otomatis memutuskan sesi shell seketika saat masa berlaku habis atau dikunci manual oleh operator.

2. **Safe-by-Default (*Default 0* untuk Web Terminal Server):**
   - Nilai bawaan izin Web Terminal (`allow_web_terminal`) pada formulir tambah server baru dan migrasi skema database diubah menjadi `0` (Nonaktif).
   - Mencegah server klien membuka akses terminal root tanpa persetujuan eksplisit dari Master Admin/Operator.

3. **Pembersihan Ikon Antarmuka (*Zero Lebay Emojis*):**
   - Menghapus penggunaan emoji yang berlebihan (*lebay*) pada dropdown platform override, opsi kebijakan server, header Task Manager, modal sinyal proses, modal mode pemeliharaan, banner pembaruan agen, dan Guardrail Dialogue.
   - Menggantikannya dengan ikon vektor SVG yang bersih, tajam, profesional, dan serasi dengan palet desain gelap antarmuka Pantau Server.

4. **Kontrol Sesi Realtime & Countdown Badge:**
   - Ditambahkan indikator sisa durasi masa sewa (*countdown badge*) pada titlebar terminal bawaan Linux.
   - Tombol "Kunci" instan pada titlebar memungkinkan operator mencabut izin sesi dan memutus koneksi terminal secara langsung sewaktu-waktu.

---

## Versi 4.2.20

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Restrukturisasi Kebijakan & Karakteristik Server (Platform Override, Proxmox HA Dinamis, Isolasi Jaringan, Pembatasan Web Terminal) dan Implementasi Universal *Guardrail Dialogue* untuk Proteksi Server Produksi Ber-SLA Tinggi

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.20
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 20 (Patch) : Karakteristik & Kebijakan Server Kompak, Proteksi Proxmox HA Dinamis, dan Universal Guardrail Dialogue untuk Infrastruktur Produksi Ber-SLA Tinggi
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.20 (Patch Release)

1. **Filosofi Proteksi Produksi Universal (Zero SLA Segmentation):**
   - Seluruh server yang terdaftar pada Pantau Server diperlakukan sebagai **Server Produksi dengan SLA Tinggi**, tanpa memecah server ke dalam kategori/tier artificial ("uji coba" vs "produksi").
   - Tindakan berdampak tinggi (Reboot Host, Power Off, Hapus Server, Hapus Pengguna, Regenerate API Key) diproteksi secara universal oleh mekanisme **Guardrail Dialogue** terintegrasi, bukan dengan checkbox izin seadanya.

2. **Universal Guardrail Dialogue Modal (`base.html`):**
   - Menggantikan dialog konfirmasi bawaan browser (`window.confirm`) yang rentan keliru diklik dengan dialog modal interaktif bertema gelap (*dark-mode*) yang elegan dan sengaja (*deliberate*).
   - Menampilkan judul tindakan, badge kategori (`SLA PRODUKSI`), target host/pengguna, rincian konsekuensi operasional terhadap ketersediaan layanan, serta **kotak centang persetujuan risiko operasional** yang wajib dicentang sebelum tombol eksekusi aktif.

3. **Restrukturisasi Form Tambah & Edit Server (`server_form.html`):**
   - Menghapus kotak kuning besar Proxmox HA yang sebelumnya terisolasi dan terlalu dominan.
   - Menggantinya dengan kartu ringkas dan profesional: **Karakteristik & Kebijakan Operasional**:
     - **Tipe Platform Lingkungan (`platform_override`):** Pilihan ringkas antara `🤖 Auto Deteksi (Laporan Agen)`, `🖥️ Fisik / Baremetal`, `☁️ Mesin Virtual (VM)`, dan `📦 Kontainer (LXC)`.
     - **🛡️ Terproteksi Proxmox HA (`is_proxmox_ha`):** Tampil dinamis hanya jika platform adalah VM, LXC, atau Auto. Otomatis disembunyikan dan di-uncheck bila platform disetel ke Fisik / Baremetal.
     - **🌐 Server Terisolasi (`is_isolated_net`):** Menandai server dalam jaringan lokal tertutup tanpa akses internet luar, sehingga notifikasi repositori paket OS eksternal (APT) disupresi secara otomatis.
     - **💻 Kebijakan Web Terminal Root (`allow_web_terminal`):** Opsi kepatuhan keamanan untuk menonaktifkan shell interaktif web pada host sensitif.

4. **Penegakan Keamanan & Integrasi Dashboard (`services.html`, `servers.html`, `main.py`):**
   - Tombol Web Terminal di hero toolbar `services.html` otomatis dinonaktifkan dengan tooltip kepatuhan keamanan bila `allow_web_terminal == 0`.
   - Endpoint WebSocket (`/ws/servers/{sid}/terminal`) dan permintaan log interaktif (`api_logs_request`) menolak akses terminal (HTTP 403) jika web terminal dinonaktifkan pada server tersebut.
   - Menambahkan badge visual `Jaringan Terisolasi` / `Lokal` pada daftar server dan rincian server bila host berstatus jaringan tertutup.
   - Migrasi skema database otomatis pada saat startup (`ALTER TABLE servers ADD COLUMN IF NOT EXISTS ...`) untuk menambahkan kolom `platform_override`, `is_isolated_net`, dan `allow_web_terminal`.

---

## Versi 4.2.19

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Optimasi Layout Tab Manajemen Pengguna & Hak Akses: Kartu Tambah Pengguna Diperkecil, Tabel Pengguna Terdaftar Muat Penuh Tanpa Scroll Samping

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.19
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 19 (Patch) : Optimasi Layout Tab Manajemen Pengguna (Asymmetric Grid 1fr 330px, Aksi Kompak, Zero Horizontal Scroll)
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.19 (Patch Release)

1. **Perkecil Ukuran Kartu Tambah Pengguna Baru:**
   - Mengubah layout grid dari pembagian seimbang 50%/50% (`repeat(auto-fit, minmax(420px, 1fr))`) menjadi grid asimetris cerdas: tabel utama mendapatkan porsi maksimal (`minmax(0, 1fr)`) dan kartu form diset ramping tetap pada lebar `330px`.
   - Mengurangi padding kartu dari `24px` menjadi `16px 18px`, merapikan spasi antar form group dari `14px-16px` menjadi `10px`, serta membatasi tinggi checklist wewenang operator (`max-height: 220px`) agar kartu form tampak ringkas dan proporsional.
   - Menambahkan breakpoint responsif (`@media (max-width: 1080px)`) agar tata letak otomatis bertumpuk 1 kolom penuh di layar tablet dan perangkat mobile.

2. **Perbaikan Tabel Kartu Daftar Pengguna Terdaftar (Bebas Scroll Samping):**
   - **Akar Masalah:** Tombol aksi pada setiap baris pengguna sebelumnya memuat teks panjang lengkap side-by-side (*Lihat*, *Setup 2FA* / *Reset 2FA* + *Matikan 2FA*, *Audit*, *Edit*, *Kunci*, *Hapus*) yang menyita lebih dari 430px sendiri, menyebabkan lebar total tabel menembus batas kartu dan memaksa scroll samping.
   - **Solusi:**
     - Menata tombol aksi menjadi lebih kompak: tombol aman primer (*Lihat*, *Edit*, *Audit*, *+2FA* / *Reset*) menggunakan teks ringkas bersanding dengan icon, sedangkan tombol toggle/destruktif (*Kunci*, *Buka*, *Hapus*, *Matikan 2FA*) menggunakan icon button presisi dengan tooltip deskriptif (`title="..."`).
     - Lebar kolom aksi berhasil dirampingkan dari ~430px menjadi ~230px tanpa menghilangkan fungsi apa pun.
     - Lebar total tabel menyusut rapi menjadi ~660px, sehingga dapat tertampung sempurna di dalam kartu tanpa memicu scroll horizontal (scroll samping) pada tampilan desktop.

---

## Versi 4.2.18

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Eskalasi Presisi Peringatan Gawat Darurat (Zero-Bypass Escalation), Ticker Realtime 1 Detik Durasi Terputus Tanpa Reload, dan Sinkronisasi Timestamp Dimulai Sejak Kehilangan Kontak

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.18
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 18 (Patch) : Eskalasi Presisi Alert Gawat Darurat (Warning -> Average -> Danger), Durasi Terputus Live Realtime Ticker, dan Fix Waktu Hilang Kontak Agen
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.18 (Patch Release)

1. **Eskalasi Presisi Peringatan Gawat Darurat (Zero-Bypass Escalation):**
   - **Akar Masalah:** Sebelumnya endpoint `/api/alerts` memuat klausa `or_(ServerProblem.severity == 'danger', ServerProblem.key == 'agent_stale')` serta menambahkan setiap server stale (> 15 detik) ke `danger_hosts`. Hal ini mengakibatkan modal popup *"PERINGATAN GAWAT DARURAT — DIPERLUKAN TINDAKAN SEGERA"* langsung muncul pada detik ke-16 saat agen baru pertama kali terlambat mengirimkan sinyal, melangkahi tahapan eskalasi normal.
   - **Solusi:** Endpoint `/api/alerts` kini secara ketat dan konsisten hanya menyaring insiden dengan `ServerProblem.severity == 'danger'`. Tahapan eskalasi 3 tingkat kini dihormati penuh:
     - **0–119 detik (15s–2m):** Severity `Warning` (Peringatan Awal) — tidak memicu popup gawat darurat atau banner merah.
     - **120–299 detik (2m–5m):** Severity `Average` (Server Down / Offline) — tidak memicu popup gawat darurat atau banner merah.
     - **>= 300 detik (5m+):** Severity `Danger` (Kritis / Gawat Darurat) — barulah modal darurat dan banner merah ditampilkan ke operator.

2. **Perbaikan Waktu Terputus Presisi (`started_at`):**
   - Menetapkan `event_at` pada insiden `agent_stale` persis merujuk pada `srv.last_seen` naive UTC (waktu aktual saat kontak komunikasi hilang), bukan saat loop deteksi dijalankan (`now`).
   - Mencegah durasi awal terputus muncul sebagai "0 dtk" palsu.
   - Menyertakan akhiran ISO `Z` pada serialisasi timestamp agar parsing browser `Date.parse()` selalu memperlakukan waktu sebagai UTC tanpa pergeseran zona waktu lokal.

3. **Ticker Realtime Dinamis 1 Detik pada UI Tanpa Reload Halaman:**
   - **Akar Masalah:** Komponen tabel modal alert tidak memiliki atribut pengait waktu dan siklus render memblokir pembaruan HTML jika ID dan status acknowledged tidak berubah, menyebabkan tulisan "Durasi Terputus" beku selamanya di "0 dtk" tanpa reload browser.
   - **Solusi:**
     - Mengimplementasikan ticker interval client-side 1 detik (`tickAllDurations()`) di `base.html` yang secara aktif memperbarui seluruh elemen dengan atribut `[data-start]`.
     - Menambahkan atribut `data-start` pada kolom durasi terputus di modal peringatan darurat serta tabel kartu masalah di dashboard.
     - Durasi bertambah naik secara mulus setiap detik (contoh: *5 mnt 1 dtk*, *5 mnt 2 dtk*, dst.) secara live realtime tanpa kedipan dan tanpa memerlukan reload halaman browser.

---

## Versi 4.2.17

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Deteksi Otomatis Platform (LXC, VM, Baremetal), Koreksi Telemetri Storage Kontainer LXC (rootfs vs host sda), Heuristik Deteksi Auto-Revive Proxmox HA, dan Redaksi Komunikasi Sysadmin Profesional

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.17
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 17 (Patch) : Deteksi Platform Presisi (LXC / VM / Baremetal), Perbaikan Alokasi Disk Kontainer LXC, Auto-Revive Heuristic Proxmox HA, dan Standardisasi Pesan Profesional Sysadmin
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.17 (Patch Release)

1. **Deteksi Otomatis Platform Host (LXC Container vs VM vs Baremetal):**
   - **Agent Telemetry:** Mengimplementasikan inspeksi mendalam pada `agent_pantau.py` via `systemd-detect-virt`, pembacaan descriptor `/run/systemd/container`, dan `/proc/1/environ` untuk mendeteksi tipe platform secara presisi: `LXC Container`, `VM (KVM/QEMU/dll)`, atau `Baremetal` (server fisik).
   - **Tampilan Badge Platform pada Seluruh Tampilan:**
     - Menampilkan badge platform berwarna cerah (`📦 LXC`, `☁️ VM (KVM)`, `🖥️ Baremetal`) pada hero header halaman detail server (`services.html`), tabel server utama (`servers.html`), tabel dasbor (`dashboard.html`), dan grid kartu dasbor.
     - Mengintegrasikan kata kunci platform ke dalam filter pencarian adaptif (`data-srv-filter`) di tabel server.

2. **Koreksi Telemetri Storage Kontainer LXC (Rootfs vs Disk Fisik Host):**
   - **Masalah:** Pada kontainer unprivileged LXC, eksekusi `lsblk` membaca disk fisik host Proxmox (mis. HPE ProLiant DL380 Gen11 RAID `sda 7.6T`), bukan kuota alokasi sebenarnya yang diberikan ke kontainer (mis. `97.9G`).
   - **Solusi:** Agen mendeteksi apakah lingkungan berjalan di kontainer LXC. Jika LXC, agen mengumpulkan alokasi partisi container (`statvfs('/')`) dan menampilkannya sebagai `rootfs` berkapasitas presisi, bukan disk blok fisik host.
   - **Backend Fallback:** Dashboard server secara cerdas mendeteksi dan mengoreksi data riwayat kontainer LXC yang masih mencatat disk blok host, memastikan tampilan kapasitas penyimpanan kontainer langsung akurat seketika.

3. **Heuristik Deteksi Otomatis Proxmox HA (Auto-Revive Detection):**
   - **Mekanisme Otomatis:** Ketika operator mengeksekusi perintah `poweroff_host` pada VM atau kontainer, jika mesin tersebut hidup kembali dan melapor dalam waktu < 5 menit dengan uptime rendah (< 180 detik), Pantau Server secara otomatis menandai `is_proxmox_ha = 1` tanpa memerlukan konfigurasi manual operator.
   - **Audit Trail:** Mencatat entri otomatis pada `audit_logs` dengan aksi `proxmox_ha_detected`.

4. **Standardisasi Redaksi Pesan Profesional Sysadmin:**
   - Menghapus redaksi penjelasan berlebih (*"mencegah loop restart"*) sesuai standar profesional operator NOC/sysadmin.
   - Menyeragamkan seluruh tooltip, alert penolakan, banner konfirmasi, dan modal proteksi Proxmox HA menjadi satu kalimat tegas dan profesional:
     > *"Server terproteksi Proxmox HA. Matikan langsung pada dashboard Proxmox VE (state: stopped)."*

---

## Versi 4.2.16

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Proteksi Proxmox HA (High Availability), Disable Tombol Power OFF + Tooltip Edukatif, dan Mitigasi Siklus Auto-Revive Hypervisor

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.16
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 16 (Patch) : Proteksi Proxmox HA Terintegrasi (is_proxmox_ha), Disable Tombol Power OFF dengan Tooltip Edukatif, Penolakan Guardrail Backend & Audit Log, dan Tampilan Badge HA pada Dasbor
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.16 (Patch Release)

1. **Proteksi & Mitigasi Siklus Auto-Revive Proxmox HA (High Availability):**
   - Mengidentifikasi dan memitigasi perilaku kontainer LXC / VM yang dikelola oleh Proxmox HA (`pve-ha-crm`/`pve-ha-lrm`): ketika dimatikan dari dalam OS (`systemctl poweroff`), Proxmox HA menganggap kontainer mati akibat *crash* tak terduga dan membangkitkannya kembali secara otomatis dalam siklus ±5 detik.
   - Menambahkan kolom database `is_proxmox_ha TINYINT(1) DEFAULT 0` pada tabel `servers` dan model `Server`.
   - **Form Pengaturan Server:** Menambahkan toggle proteksi *"Terdaftar di Proxmox HA (High Availability)"* pada halaman tambah dan edit server (`server_form.html`).

2. **Frontend Guardrail & Edukasi UI/UX:**
   - **Penonaktifan Tombol Power OFF:** Pada server dengan flag Proxmox HA aktif, tombol **Power OFF** di hero banner dinonaktifkan (`disabled`, latar belakang transparan bergaris putus-putus, kursor `not-allowed`) untuk mencegah salah klik operator.
   - **Tooltip & Badge Informatif:** Menampilkan badge `[Proxmox HA]` dan tooltip panduan teknis yang menjelaskan bahwa pemadaman mesin HA harus dilakukan melalui host Proxmox VE (state `stopped`) agar tidak menyala kembali.
   - **Pemutakhiran Live Updater JS:** Memastikan skrip sinkronisasi realtime pada `services.html` tidak mengaktifkan kembali tombol yang dilindungi pembungkus `.ha-protected-wrapper`.
   - **Badge Dasbor & Filter:** Menampilkan badge penanda `HA` di samping nama host pada tabel `servers.html`, tabel dasbor, dan kartu rincian, serta mendukung filter pencarian `ha`.

3. **Keamanan & Guardrail Sisi Server (Backend):**
   - Menolak eksekusi `poweroff_host` di backend `_host_control` jika `server.is_proxmox_ha == 1`, baik untuk request form HTML (redirect dengan notifikasi banner peringatan kuning `action=poweroff_ha_blocked`) maupun pemanggilan API JSON (respons status 400 Bad Request).
   - Mencatat penolakan tindakan secara transparan ke dalam tabel `audit_logs`.
   - Tombol **Reboot OS** tetap diizinkan karena alur reboot memang bertujuan menyalakan kembali server.

---

## Versi 4.2.14

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Auto-Healing Wrapper Host Shutdown & Penanganan False-Positive Degraded State pada Proxmox LXC Container

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.14
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 14 (Patch) : Auto-Healing Wrapper pantau-host pada Sistem Degraded, Pengakuan Validitas Systemd di Proxmox LXC Container, dan Perbaikan Eksekusi Power Off
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.14 (Patch Release)

1. **Auto-Healing Wrapper Host Control (`pantau-host`) pada Proxmox LXC & Status Degraded:**
   - Memperbaiki kegagalan perintah **Power OFF** dan **Reboot** pada instance Proxmox LXC Container (seperti `e-kinerja-clone`) yang sebelumnya dibatalkan dengan pesan salah *"systemd TIDAK berjalan sebagai host"*.
   - Penyebab akar: Klien yang diinstal sebelum v4.2.1 masih menggunakan skrip wrapper lama yang memeriksa `systemctl is-system-running`. Jika ada unit layanan berstatus *degraded*, evaluasi kode keluar menghasilkan nilai non-zero sehingga skrip keliru menganggap mesin tersebut bukan host.
   - Solusi: Agen kini mendeteksi direktori `/run/systemd/system`. Jika direktori tersebut ada, agen mengenali bahwa systemd aktif dan siap menerima shutdown (termasuk pada namespace LXC). Agen secara otomatis memperbarui (*auto-heal*) berkas `/usr/local/sbin/pantau-host` dengan skrip terbaru dan melanjutkan eksekusi pemadaman secara sukses.

---

## Versi 4.2.13

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Rincian Lengkap Kolom Waktu Riwayat Insiden dan Riwayat Tindakan (Tanggal, Jam, Menit, Detik)

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.13
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 13 (Patch) : Presisi Rinci Kolom Waktu Riwayat Insiden & Riwayat Tindakan (Tanggal, Jam, Menit, Detik tanpa Nama Hari), Format Tanggal Terpadu (_fmt_dt), dan Penguncian Lebar Kolom .col-time-detailed
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.13 (Patch Release)

1. **Rincian Presisi Kolom Waktu Riwayat Insiden & Riwayat Tindakan:**
   - Memperbarui tampilan kolom waktu pada **Kartu Riwayat Insiden** (`prob-resolved-card` di menu Insiden) dan **Kartu Riwayat Tindakan** (`tbl-action-history` serta `acc-action-tbody` di menu Rincian Server) agar menampilkan tanggal, jam, menit, dan detik secara lengkap (contoh: `13 Okt 2026 10:15:32`).
   - Meniadakan nama hari (Senin/Selasa/dst.) guna mempertahankan tampilan ringkas, profesional, dan seragam.
   - Pada kartu riwayat insiden, waktu ditampilkan dengan label status yang jelas: waktu **Mulai** dan waktu **Selesai / Pulih** hingga satuan detik.

2. **Format Tanggal Terpadu Backend & Frontend (`_fmt_dt`):**
   - Menambahkan fungsi helper `_fmt_dt` di backend FastAPI dengan singkatan bulan bahasa Indonesia standar (`Jan`, `Feb`, `Mar`, `Apr`, `Mei`, `Jun`, `Jul`, `Agu`, `Sep`, `Okt`, `Nov`, `Des`) dan mendaftarkannya ke Jinja globals.
   - Memperbaiki serialisasi endpoint `/api/servers/{sid}/overview` agar data `time` riwayat tindakan tidak lagi terpotong menjadi hanya `HH:MM:SS` saat polling/live refresh.
   - Memperbarui fungsi JavaScript `fmtProbDate` agar mempertahankan format lengkap tanggal dan detik saat re-render interaktif.

3. **Gaya CSS Lebar Kolom `.col-time-detailed`:**
   - Menambahkan kelas CSS `.col-time-detailed` pada `base.html` dengan lebar proporsional (`width: 200px !important; min-width: 190px !important; white-space: nowrap !important; font-variant-numeric: tabular-nums !important;`) sehingga teks timestamp rinci tidak terpotong atau tertekan aturan `.col-time` lama.

---

## Versi 4.2.12

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Restorasi Presisi Lebar Kolom Hostname, Eliminasi Void Kosong Melebar, dan Keselarasan Vertikal Metrik Sistem

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.12
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 12 (Patch) : Restorasi Presisi Lebar Kolom Hostname (150px–180px), Eliminasi Peregangan Kolom Tak Wajar, Penyelarasan Posisi Metrik Terpusat, dan Proporsionalitas Tabel Dinamis
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.12 (Patch Release)

1. **Restorasi Presisi Lebar Kolom Hostname & Server (*Eliminate Stretched Void*):**
   - Menghapus aturan `width: auto` pada kolom Hostname di tabel server dashboard (`dash-server-table`), daftar server (`servers-table`), dan kolom Server (`col-server`) pada seluruh tabel insiden. Aturan `width: auto` sebelumnya menyebabkan browser mengalokasikan seluruh ruang kosong horizontal tabel (hingga 600px–700px) hanya pada kolom Hostname.
   - Mengunci lebar kolom Hostname ke dimensi presisi dan proporsional:
     - Dashboard (`dash-server-table`): `width: 150px; min-width: 140px; max-width: 180px;`.
     - Daftar Server (`servers-table`): `width: 180px; min-width: 160px; max-width: 210px;` (cukup untuk nama host, dot status, dan badge versi agen tanpa terpotong).
     - Kolom Server pada Tabel Insiden (`.col-server`): `width: 150px; min-width: 135px; max-width: 180px;`.
   - Mengalihkan sifat fleksibel dinamis (`width: auto`) secara tepat hanya ke kolom deskriptif seperti **Kejadian / Deskripsi Masalah** pada tabel insiden dan **Keterangan** pada tabel layanan, sehingga teks penjelasan dapat membaca ruang bebas tanpa mendistorsi kolom identitas.

2. **Penyelarasan Vertikal Metrik Sistem Dashboard (*Center-Aligned Metric Values*):**
   - Menyelaraskan teks nilai sub-kolom metrik (CPU Core, RAM Total/Tersedia, Disk Total/Tersedia) dan mini-meter bar persentase secara terpusat (*center-aligned*) tepat di bawah judul sub-header masing-masing.
   - Tampilan visual tabel kini rapi, padat, simetris, dan mencerminkan antarmuka sistem monitoring kelas profesional.

---

## Versi 4.2.11

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Penataan Ulang Lebar Kolom Seluruh Tabel, Perampingan Kolom Grup & Uptime, serta Kolom Hostname Adaptif Fleksibel

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.11
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 11 (Patch) : Penataan Ulang Lebar Kolom Seluruh Tabel, Perampingan Kolom Grup & Uptime, Kolom Hostname Adaptif Bebas Truncation, dan Eliminasi Ruang Kosong Berlebih
```

---

### Perbaikan Masalah & Peningkatan UX — Versi 4.2.11 (Patch Release)

1. **Lebar Kolom Hostname Adaptif Sesuai Panjang Teks (*Adaptive Hostname Columns*):**
   - Menghapus pembatasan lebar kaku (fixed pixel constraint) pada kolom Hostname di tabel server dashboard (`dash-server-table`), daftar server (`servers-table`), dan tabel insiden (`probtable`).
   - Menerapkan `min-width: 130px; width: auto; white-space: nowrap;` sehingga lebar kolom Hostname dapat melebar secara proporsional dan elegan menyesuaikan panjang karakter nama host tanpa terpotong maupun memakan ruang kosong berlebih.

2. **Perampingan Kolom Grup dan Uptime (*Compact Group & Uptime Columns*):**
   - Merampingkan lebar kolom **Grup** dari `110px` menjadi `85px` (`min-width: 80px`) dengan badge teks terpusat (*center-aligned*) rapi.
   - Merampingkan lebar kolom **Uptime** dari `130px` menjadi `100px` (`min-width: 90px`) dengan penataan teks terpusat dan pemisahan dari aturan durasi insiden (`col-durasi`).

3. **Optimalisasi dan Standardisasi Lebar Seluruh Tabel Sistem:**
   - Menyelaraskan seluruh metrik sub-kolom (CPU Core, Beban CPU, RAM Total/Beban/Tersedia, Disk Total/Beban/Tersedia, Layanan, Insiden, Task Manager `%CPU` / `%Memori`, dan Ports) agar memiliki ruang margin yang pas, padat, dan proporsional.
   - Menghilangkan ruang kosong mubazir (*wasted whitespace*) di seluruh tabel aplikasi sehingga tampilan terlihat jauh lebih rapi, bersih, seimbang, dan profesional di berbagai resolusi layar.

---

## Versi 4.2.10

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Stabilisasi Lebar Kolom Tabel dan Eliminasi Efek Pergeseran Ukuran Dinamis (Anti-Jitter)

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.10
 │
 ├── 4  (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2  (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 10 (Patch) : Stabilisasi Lebar Kolom Tabel (Anti-Jitter), Penguncian Dimensi Kolom Durasi, Penyelarasan Timer Global, dan Penerapan Tabular Figures
```

---

### Perbaikan Masalah & Patch — Versi 4.2.10 (Patch Release)

1. **Penguncian Permanen Lebar Kolom Durasi & Waktu (*Anti-Jitter Column Stabilization*):**
   - Mengatasi masalah kolom tabel yang terus membesar dan mengecil secara dinamis mengikuti panjang nilai teks durasi (contoh: transisi teks dari detik ke menit atau jam).
   - Menerapkan aturan lebar kolom terkunci (`width: 130px; min-width: 130px; max-width: 130px; white-space: nowrap`) pada seluruh sel durasi (`td.col-durasi`, `td[data-start]`) di tabel insiden terbuka, riwayat insiden teratasi, dan tab Riwayat & Masalah rincian server.
   - Mengaktifkan `font-variant-numeric: tabular-nums` pada font monospace agar setiap angka memiliki lebar glif yang identik, menghilangkan getaran mikro (*micro-jitter*) saat nilai waktu bertambah.

2. **Harmonisasi Timer Pembaruan Durasi Global:**
   - Menghilangkan konflik duplikasi `setInterval` lokal di halaman insiden dan layanan yang sebelumnya berebut memperbarui teks durasi dengan format yang berbeda dari timer sentral `base.html`.
   - Menyatukan kalkulasi dan penulisan teks durasi pada fungsi sentral `fmtDur(secs, isEn)` di template dasar (`base.html`), menghasilkan pembaruan realtime yang mulus, stabil, dan konsisten setiap 1 detik.

3. **Stabilisasi Lebar Kolom Tabel Lintas Modul:**
   - Menetapkan lebar pasti dan proporsional untuk kolom-kolom metrik dan informasi di seluruh tabel utama (Daftar Server, Daftar Layanan, Tabel Masalah Dasbor, dan Pemantau Server Utama) agar struktur tabel kokoh dan tidak bergeser saat data telemetri diperbarui via polling latar belakang.

---

## Versi 4.2.9

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Standarisasi Kolom Keparahan Seluruh Tabel Insiden dan Penyeragaman Kolom Host Server

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.9
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 9 (Patch) : Penyeragaman Menyeluruh Kolom Keparahan (Menggantikan Level & Tingkat) Serta Pembakuan Kolom Host Menjadi "Server" pada Ringkasan Dasbor
```

---

### Perbaikan Masalah & Patch — Versi 4.2.9 (Patch Release)

1. **Standarisasi Kolom Anomali & Insiden Menjadi "Keparahan":**
   - Menghilangkan variasi penamaan kolom penunjuk tingkat kegawatan insiden (`Level` dan `Tingkat`) pada antarmuka dashboard Pantau Server.
   - Membakukan seluruh judul kolom penunjuk urgensi masalah di tabel insiden terbuka (`/problems`), riwayat insiden teratasi, dan tab Riwayat & Masalah rincian server (`/servers/{id}/services`) menjadi **Keparahan** (dengan padanan bahasa Inggris: **Severity**).
   - Menyelaraskan opsi filter dropdown dari *Semua level* menjadi *Semua keparahan* (*All severities*) agar selaras secara kontekstual.

2. **Pembakuan Nama Kolom Host pada Kartu Masalah Dasbor Menjadi "Server":**
   - Mengubah judul kolom *Server Terkendala* pada tabel ringkasan masalah terbuka di halaman utama Dasbor (`/dashboard`) menjadi **Server** agar konsisten dengan struktur tabel insiden di seluruh menu lainnya.

---

## Versi 4.2.8

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Standarisasi Penuh Penamaan Kolom Aksi dan Penyederhanaan Sistem Tombol Berprinsip Semantik Konsisten

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.8
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 8 (Patch) : Standarisasi Seluruh Kolom Tombol Interaktif Menjadi "Aksi", Eliminasi Tombol Over-Designed (Mengadopsi Gaya Sederhana btn-ghost), dan Harmonisasi Bobot Tipografi Serta Ikon
```

---

### Perbaikan Masalah & Patch — Versi 4.2.8 (Patch Release)

1. **Standarisasi Menyeluruh Penamaan Kolom Tabel Interaktif Menjadi "Aksi":**
   - Menghilangkan ketidakkonsistenan penamaan kolom antara istilah "Tindakan" dan "Aksi" pada tabel-tabel di seluruh dashboard Pantau Server.
   - Seluruh kolom tabel yang memuat tombol operasi interaktif dibakukan menjadi **Aksi** (termasuk pada File Manager, Manajemen Pengguna, Sesi Profil, Status Masalah, Daftar Layanan, Blokir Firewall, Port Terbuka, dan Emergency Alert Overlay).
   - Kolom riwayat audit dan log masa lalu tetap mempertahankan label semantik deskriptif ("Tindakan") untuk merujuk pada jenis peristiwa/perintah yang telah tereksekusi.

2. **Penyederhanaan Sistem Tombol Masalah Berprinsip Semantik Bersih & Konsisten:**
   - Mengeliminasi gaya tombol kustom yang berlebihan (*over-designed*, gradien tebal, dan border kaku) pada tabel insiden/masalah, menggantikannya dengan desain sederhana, bersih, dan profesional yang identik dengan tombol `Log` dan `Abaikan` pada kartu Daftar Layanan (`.btn.btn-ghost.btn-sm` dengan border lembut dan latar transparan).
   - Menerapkan pembagian semantik warna dan bentuk yang memiliki filosofi jelas:
     - **Inspeksi / Netral:** `Log`, `Diagnosa`, `Rincian`, `Update Agen`, `Abaikan`, `Pantau Kembali` menggunakan varian netral `.btn.btn-ghost.btn-sm`.
     - **Operasi Aktif:** `Restart`, `Update OS` menggunakan varian aksen utama `.btn.btn-primary.btn-sm`.
     - **Operasi Kritis / Destruktif:** `Blokir IP`, `Hapus` menggunakan varian peringatan bahaya `.btn.btn-danger.btn-sm`.
     - **Penyelesaian / Triase:** `Ditangani` menggunakan varian status sukses `.btn.btn-success.btn-sm`.
   - Menyelaraskan ukuran font (12px), bobot teks semi-bold (600), dan dimensi ikon SVG monokrom inline (12px) secara presisi di seluruh elemen tombol agar kenyamanan visual dan pengalaman pengguna konsisten.

---

## Versi 4.2.7

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Restrukturisasi Tombol Layanan, Kedalaman Visual Modern, dan Harmonisasi Kolom Aksi Insiden Terbuka

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.7
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 7 (Patch) : Restrukturisasi Tombol Layanan Selalu Tampil (Disabled State), Peningkatan Kedalaman Visual (Non-Flat Glow), Penataan 2 Baris Insiden, dan Pembersihan Kolom Aksi Insiden Terbuka
```

---

### Perbaikan Masalah & Patch — Versi 4.2.7 (Patch Release)

1. **Restrukturisasi Total Kolom Aksi Daftar Layanan (*Always-Visible Action Buttons with Disabled States*):**
   - Menampilkan seluruh tombol kontrol layanan (`Restart`, `▶ Start`, `■ Stop`, `Log`, `🔕 Abaikan`/`🔔 Pantau`, `Hapus`) secara persisten pada tabel daftar layanan di Tab Layanan halaman Rincian Server, tanpa menyembunyikan tombol secara kondisional.
   - Mengaktifkan status *disabled* (`disabled`, opasitas redup, kursor *not-allowed*) beserta *tooltip* informatif ketika aksi tidak valid (contoh: tombol `Start` dinonaktifkan jika layanan sudah aktif/`up`, tombol `Stop` dinonaktifkan jika layanan sudah terhenti/`down`, tombol `Abaikan` dinonaktifkan jika layanan berjalan normal).
   - Menstandardisasi seluruh tombol aksi layanan dengan ikon SVG monokrom inline yang serasi (menghilangkan campuran emoji `🔕`/`🔔` dan karakter unicode mentah `▶`/`■`), menghasilkan tampilan kontrol yang simetris, seragam, dan profesional.

2. **Penggantian Nama Kolom "Kesehatan" Menjadi "Keterangan":**
   - Mengubah judul kolom tabel `Kesehatan` menjadi `Keterangan` pada kartu Daftar Layanan di Tab Layanan halaman Rincian Server untuk mencerminkan informasi diagnostik dan pesan status layanan secara lebih tepat dan lugas.

3. **Penyempurnaan Kedalaman Visual & Eliminasi Desain Flat (*Modern Depth & Neon Glow*):**
   - Memperbarui gaya tombol tindakan masalah (`.prob-btn`) dengan memberikan dimensi kedalaman visual (*gradient background*, *inner border highlight*, bayangan halus, dan pendaran neon halus sesuai kategori semantik).
   - Menghilangkan kesan "flat/dull gray" saat tombol berada dalam kondisi *idle*, sehingga setiap varian tombol (`primary`, `danger`, `warn`, `success`, dan badge `status-ack`) memiliki identitas visual yang kaya dan menyatu harmonis dengan tema gelap modern dashboard Pantau.

4. **Penataan Baku 2 Baris Kolom Tindakan Status Masalah (*Strict Two-Row Toolbar Layout*):**
   - Mengunci tata letak tombol tindakan pada kartu Riwayat & Masalah menjadi tepat 2 baris non-wrapping (`prob-act-tools` di Baris 1 dan `prob-act-ops` di Baris 2) untuk mencegah tombol memanjang ke samping atau patah menjadi 3–4 baris yang tidak beraturan.

5. **Pembersihan Kolom Aksi Kartu Insiden Terbuka Menu Insiden:**
   - Menghapus tombol `Diagnosa` dari kolom aksi tabel Insiden Terbuka di menu utama Insiden (`/problems`), menyisakan tombol navigasi `Rincian` dan tombol alur penanganan (`Ditangani`, `Abaikan`/`Pantau Kembali`) agar antarmuka ringkas dan terfokus pada triase insiden lintas server.

---

## Versi 4.2.6

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Harmonisasi Desain Bingkai & Standardisasi Ikon SVG Tombol Tindakan Status Masalah

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.6
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 6 (Patch) : Harmonisasi Bingkai Seragam, Standardisasi Ikon SVG Monokrom, dan Penataan Proporsional Tombol Tindakan Status Masalah
```

---

### Perbaikan Masalah & Patch — Versi 4.2.6 (Patch Release)

1. **Harmonisasi Desain Bingkai & Keserasian Tombol (*Unified Frame Design Language*):**
   - Menghilangkan disparitas visual pada tombol tindakan di mana sebelumnya terdapat perbedaan bingkai yang mencolok (sebagian tombol memiliki border cyan neon, tombol restart berwarna biru pekat kontras, dan tombol lainnya berwarna abu-abu transparan).
   - Menstandarkan seluruh tombol ke dalam sistem bingkai yang 100% serasi dan elegan:
     - Dimensi dan bentuk seragam: tinggi `26px`, border radius `6px`, padding `3px 9px`, font `11.5px (weight 500)`.
     - Permukaan awal netral: bingkai `1px solid rgba(255, 255, 255, 0.12)`, background `rgba(255, 255, 255, 0.04)`, dan warna teks konsisten `#e2e8f0`.
     - Interaksi hover semantik halus (*subtle micro-interaction*): tombol bertransformasi dengan aksen warna konteks (cyan untuk Diagnosa/Restart, putih untuk Log, merah untuk Blokir IP, hijau emerald untuk Ditangani, amber untuk Abaikan) tanpa merusak keserasian tata letak saat diam.

2. **Standardisasi Penuh Ikonografi SVG Monokrom (*Zero Mismatched Emojis*):**
   - Mengganti seluruh emoji campuran (`🔍`, `🔕`, `🔔`, `📋`) dan melengkapi tombol yang sebelumnya tanpa ikon (`Log`, `Restart`, `Ditangani`) dengan ikon SVG inline monokrom standar 13x13px (`stroke-width: 2`, `stroke="currentColor"`).
   - Setiap tombol kini memiliki anatomi seragam: `[ <svg 13px> <Label> ]` sehingga antarmuka tampak rapi, bersih, dan berkelas enterprise.
   - Badge status `Ditangani` diformat presisi dengan dimensi yang identik dengan tombol lainnya menggunakan aksen hijau lembut, menjaga keseimbangan baris tanpa lonjakan tinggi elemen.

3. **Penataan Bertingkat Proporsional & Ergonomis:**
   - Memisahkan secara logis antara tombol teknis insiden dan perbaikan sistem di Baris 1 (`Diagnosa`, `Log`, `Restart`/`Blokir IP`) dengan tombol alur penanganan status administratif di Baris 2 (`Ditangani`, `Abaikan`/`Pantau Kembali`).
   - Mencegah baris tabel meluber ke samping sekaligus menghilangkan ketimpangan susunan tombol, menciptakan tampilan yang nyaman dan sedap dipandang mata.

---

## Versi 4.2.5

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Restrukturisasi Tata Letak Tombol Aksi Status Masalah Menjadi Bertingkat Ringkas & Rapi

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.5
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 5 (Patch) : Restrukturisasi Tata Letak Tombol Tindakan Status Masalah Menjadi Bertingkat Ringkas, Bersih, dan Profesional
```

---

### Perbaikan Masalah & Patch — Versi 4.2.5 (Patch Release)

1. **Restrukturisasi Tata Letak Tombol Aksi Status Masalah (*Compact 2-Tier Incident Action Toolbar*):**
   - Mengatasi kendala tata letak tombol tindakan pada kartu **Status Masalah** di Tab Riwayat & Masalah ([`services.html`](file:///home/bos/rj45/server/templates/services.html)) serta tabel Insiden Terbuka ([`problems.html`](file:///home/bos/rj45/server/templates/problems.html)) yang sebelumnya tersusun memanjang secara horizontal (`white-space: nowrap`) hingga memakan lebar kolom lebih dari 400px dan menekan kolom informasi lainnya.
   - Mengelompokkan tombol ke dalam dua tingkat terstruktur (*2-tier layout*):
     - **Tingkat 1 (Investigasi & Observabilitas - Aman/Read-Only):** Tombol `🔍 Diagnosa` dan `Log` (atau `Log auth`) dengan desain *ghost accent* modern.
     - **Tingkat 2 (Remediasi & Status Triage):** Tombol tindakan operasional (`Restart`, `Blokir IP`, `Update OS`, atau `Update Agen`) berdampingan secara harmonis dengan tombol penanganan status (`🔕 Abaikan`/`🔔 Pantau` dan `Ditangani`/badge `✓ Ditangani`).
   - Menyediakan class CSS khusus `.prob-act-cell`, `.prob-act-wrap`, `.prob-act-row`, `.prob-btn`, dan `.prob-badge-ack` di [`base.html`](file:///home/bos/rj45/server/templates/base.html) dengan dimensi kompak (tinggi 24px, padding 3px 8px, font 11.5px) yang membatasi lebar kolom tindakan stabil di kisaran 160–220px tanpa *overflow*.

2. **Konsistensi Visual Rendering SSR dan JavaScript Real-Time:**
   - Menyelaraskan struktur HTML antara *Server-Side Rendering* (SSR Jinja2) dan *Client-Side Rendering* (`renderProblemsTab` di `services.html` dan `renderLiveProblems` di `problems.html`), memastikan perpindahan status atau pembaruan berkala via WebSocket/AJAX mempertahankan tata letak bertingkat yang rapi.
   - Mempertahankan aturan keamanan peran **Viewer** secara ketat (tanpa tombol mutasi/kontrol tindakan, hanya menampilkan instrumen analisis dan badge status).

---

## Versi 4.2.4

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Standardisasi Ketersediaan Tombol Diagnosa Log Layanan untuk Seluruh Peran Pengguna & Penyelarasan Unit Log Dinamis

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.4
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 4 (Patch) : Standardisasi Tombol Log Layanan untuk Seluruh Peran Pengguna & Penyelarasan Unit Log Dinamis
```

---

### Perbaikan Masalah & Patch — Versi 4.2.4 (Patch Release)

1. **Standardisasi Akses Tombol Log Layanan untuk Seluruh Peran Pengguna:**
   - Memperbaiki ketidakkonsistenan tampilan tombol `Log` pada kartu Riwayat & Masalah Terbuka ([`services.html`](file:///home/bos/rj45/server/templates/services.html)).
   - Sebelumnya, tombol `Log` untuk pengguna non-viewer (Master Admin dan Operator) bersarang di dalam blok kondisional `p.action === 'restart' && CAN_SERVICES`. Akibatnya, jika suatu masalah layanan tidak memiliki aksi restart atau terjadi pada wewenang terbatas, tombol `Log` tidak muncul untuk admin/operator, sementara pada pengguna viewer tombol `Log` selalu muncul.
   - Tombol `Log` kini dipisahkan dari logika aksi kontrol dan diposisikan berdampingan dengan tombol `🔍 Diagnosa` sebagai instrumen observasi (*read-only*) standar yang dapat diakses oleh seluruh peran (**Master Admin, Operator, dan Viewer**).
   - Menambahkan tombol `Log` pada daftar layanan (Tab Layanan) untuk memudahkan penelusuran log journalctl setiap layanan secara langsung tanpa harus berpindah manual ke tab Logging.

2. **Penyelarasan Unit Log Layanan Otomatis (*Dynamic Service Log Unit Mapping*):**
   - Pada backend ([`server/main.py`](file:///home/bos/rj45/server/main.py)), penetapan `log_unit` untuk insiden `service_down:` dan `svc_no_data:` kini langsung diarahkan ke nama unit layanan sistem operasi, tidak lagi dibatasi oleh daftar statis `extra.units`.
   - Pada frontend ([`server/templates/base.html`](file:///home/bos/rj45/server/templates/base.html)), fungsi `jumpToLog(unit)` kini secara dinamis menambahkan opsi unit ke elemen dropdown `<select id="log-unit">` jika unit belum terdaftar, mencegah peringatan salah (*false alert*) unit tidak tersedia dan langsung memicu kueri log ke agen klien.

---

## Versi 4.2.3

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Perbaikan Sintaksis JavaScript Global Halaman Detail Server, Pemulihan Navigasi Tab Interaktif & Rendering Telemetri Kinerja

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.3
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 3 (Patch) : Perbaikan Deklarasi Dobel Lingkup Global JavaScript, Pemulihan Interaksi Tab, & Penanganan Sanitasi Karakter Template
```

---

### Perbaikan Masalah & Patch — Versi 4.2.3 (Patch Release)

1. **Perbaikan Kesalahan Fatal Sintaksis JavaScript Global (*Duplicate Identifier SyntaxError Fix*):**
   - Mengeliminasi deklarasi ganda `const IS_VIEWER` pada skrip halaman [`services.html`](file:///home/bos/rj45/server/templates/services.html) dan [`problems.html`](file:///home/bos/rj45/server/templates/problems.html).
   - Sebelumnya, keberadaan `const IS_VIEWER` di dalam berkas template anak memicu galat browser kritis `Uncaught SyntaxError: Identifier 'IS_VIEWER' has already been declared` karena konstanta ini telah dideklarasikan di lingkup global template induk [`base.html`](file:///home/bos/rj45/server/templates/base.html).
   - Galat sintaksis tersebut menyebabkan mesin JavaScript peramban menghentikan seluruh kompilasi blok skrip pada halaman detail server.
   - Dengan perbaikan ini, seluruh logika interaktif kembali berjalan normal:
     - Navigasi tab (*tab switching*) menggunakan tombol tab (`#detail-tabs .tab`) maupun parameter URL (`?tab=...`) pulih sepenuhnya.
     - Tab **Kinerja & Spesifikasi** kembali menampilkan data telemetri vital secara live (utilisasi CPU, RAM, Swap, Load, Disk, sparkline grafik, dan rincian perangkat keras).

2. **Sanitasi dan Pencegahan Escaping Entitas HTML pada Variabel JavaScript Template:**
   - Memperbaiki ekspresi variabel filter grup pada [`problems.html`](file:///home/bos/rj45/server/templates/problems.html) menjadi `{{ (filter_group or '') | tojson }}`.
   - Mencegah mekanisme autoescaping Jinja mengubah string kosong menjadi entitas HTML `&#39;&#39;` yang sebelumnya dapat memicu kegagalan parsing skrip `SyntaxError: Unexpected token '&'`.

3. **Peningkatan Keandalan Penanganan Event DOM (*Defensive Event Listener Guard*):**
   - Menambahkan pengecekan null (`if (pre)`) sebelum mendaftarkan pendengar event scroll pada elemen log viewer [`services.html`](file:///home/bos/rj45/server/templates/services.html) guna memastikan inisialisasi skrip tetap kokoh pada berbagai kondisi DOM.

---

## Versi 4.2.2

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Penguatan Isolasi Hak Akses Viewer (Zero-Control) & Pengelolaan 2FA TOTP Terkelola oleh Administrator

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.2
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 2 (Patch) : Isolasi Menyeluruh Hak Akses Akun Viewer & Pengelolaan 2FA TOTP Terkelola oleh Administrator
```

---

### Perbaikan Masalah & Patch — Versi 4.2.2 (Patch Release)

1. **Penguatan Menyeluruh Isolasi Hak Akses Akun Viewer (*Zero-Control Strict Viewer Isolation*):**
   - Menjamin seluruh akun dengan peran (*role*) `viewer` beroperasi murni sebagai pemantau (*read-only*) tanpa kemampuan melakukan kontrol operasional atau mengubah status sistem apapun.
   - **Proteksi Backend (FastAPI Guard):** Menambahkan verifikasi ketat `user.is_viewer()` yang melempar `HTTP 403 Forbidden` pada rute:
     - `POST /api/alerts/{pid}/ack` (Penanganan insiden / Acknowledge alert)
     - `POST /api/alerts/{pid}/resolve` (Penyelesaian insiden / Resolve alert)
     - `POST /api/alerts/{pid}/ignore` & `unignore` (Pengabaian alert insiden)
     - `POST /api/servers/{sid}/services/{svc_id}/ignore` & `unignore` (Pengabaian pemantauan service)
   - **Pembersihan Antarmuka Web (UI/UX):**
     - Menyembunyikan seluruh tombol aksi penanganan (*Abaikan, Pantau Kembali, Ditangani*) pada tabel Insiden Terbuka (`problems.html`) baik saat render SSR maupun rendering asinkron JavaScript (`IS_VIEWER`).
     - Menyembunyikan tombol aksi penanganan massal (*Ack All*) pada banner modal insiden kritis di layout utama (`base.html`).
     - Menyembunyikan seluruh kontrol aksi service (*Restart, Start, Stop, Ignore*) dan kontrol insiden pada halaman detail server (`services.html`).
     - Menampilkan indikator peran `Viewer` yang jelas dan informatif pada panel navigasi.

2. **Pengelolaan 2FA TOTP Terkelola untuk Pengguna Viewer oleh Administrator (*Managed 2FA by Admin*):**
   - Mengingat peran `viewer` tidak memiliki akses mandiri ke halaman profil/pengaturan akun (`/profile`), aktivasi dan konfigurasi 2FA TOTP (RFC 6238) kini dikelola langsung oleh administrator / operator utama via menu Manajemen Pengguna.
   - **Rute API Terproteksi Baru:**
     - `POST /api/users/{uid}/2fa/init`: Menghasilkan rahasia Base32 TOTP, QR code Data URL, dan teks kunci rahasia terformat untuk dipindai oleh aplikasi autentikator di ponsel pengguna viewer (Google Authenticator / Microsoft Authenticator).
     - `POST /api/users/{uid}/2fa/confirm`: Memverifikasi kode 6-digit pertama dari ponsel pengguna viewer, mengaktifkan status `totp_enabled = 1`, menerbitkan 8 kode pemulihan darurat (*recovery codes*), serta mencatat jejak audit `USER_2FA_ENABLED_BY_ADMIN`.
     - `POST /api/users/{uid}/2fa/disable`: Mematikan status 2FA pengguna jika diperlukan penggantian perangkat dengan pencatatan audit `USER_2FA_DISABLED_BY_ADMIN`.
   - **Modal Interaktif Manajemen Pengguna (`profile.html`):**
     - Menampilkan badge status 2FA (`● 2FA Aktif` / `● 2FA Nonaktif`) pada tabel daftar pengguna.
     - Menyediakan tombol aksi `🔐 Setup 2FA`, `🔄 Reset 2FA`, dan `🚫 Matikan 2FA` pada setiap baris pengguna.
     - Modal terstruktur 2 tahap: Tahap 1 menampilkan instruksi jelas, QR code terpusat, salin teks kunci, dan input verifikasi 6 digit; Tahap 2 menampilkan daftar kode pemulihan darurat dengan tombol salin dan unduh berkas teks.
   - **Autentikasi Login Terintegrasi:** Akun viewer dengan status 2FA aktif secara otomatis diwajibkan memasukkan kode 6 digit TOTP saat proses login (`/login/2fa`), memperkuat keamanan akun observasi dari potensi penyalahgunaan kredensial.

---

## Versi 4.2.1

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) — Pembaruan Mandiri Armada Agen Otomatis (Fleet Self-Update OTA), Perbaikan Preflight Reboot Host (Degraded State), Pembersihan Antrean Paket Macet, & Pencegahan Auto-Connect Terminal Root Shell

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.1
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 1 (Patch) : Fleet-Wide OTA Self-Update, Perbaikan Preflight Reboot Host (Degraded State), Auto-Expire Antrean APT, & Penertiban Terminal Shell
```

---

### Perbaikan Masalah & Patch — Versi 4.2.1 (Patch Release)

1. **Pembaruan Mandiri Armada Agen Otomatis (*Fleet-Wide Agent Self-Update OTA*):**
   - Mengeliminasi keharusan administrator menekan tombol update secara manual satu per satu di setiap server client.
   - Endpoint `/api/commands` kini secara cerdas mendeteksi apabila versi agen client (`extras.agent_version`) lebih lama dari versi dashboard (`settings.APP_VERSION`).
   - Server secara otomatis mengantrekan perintah `update_agent` dengan payload URL binary dan verifikasi hash SHA-256 resmi.
   - Agen client mengunduh, memverifikasi hash SHA-256, menguji kompilasi sintaks Python (`py_compile`), menimpa berkas secara atomik, dan me-restart dirinya sendiri via systemd watchdog.
   - Dilengkapi proteksi anti-looping: jika pembaruan gagal, sistem tidak akan mencoba ulang otomatis selama 15 menit.

2. **Perbaikan Pra-Pemeriksaan (*Preflight Check*) Reboot Host pada Sistem Degraded:**
   - Memperbaiki wrapper `package/usr/local/sbin/pantau-host` yang sebelumnya menolak perintah reboot dengan pesan *"systemd TIDAK berjalan sebagai host"* ketika status systemd mesin klien berstatus `degraded`.
   - Mengganti evaluasi kode keluar `systemctl is-system-running` dengan pengecekan direktori standar Linux `[ -d /run/systemd/system ]`.
   - Perintah reboot dan shutdown kini dieksekusi dengan andal di seluruh varian status operasional systemd (`running`, `degraded`, `starting`).

3. **Pembersihan Otomatis Antrean Paket Macet (*Auto-Expire APT Requests*):**
   - Menambahkan mekanisme kadaluwarsa otomatis (4–15 menit) untuk entri `LogRequest` pembaruan paket (`APT_UPDATE` / `APT_UPGRADE`).
   - Mencegah terjebaknya antrean status `executing` yang sebelumnya menyebabkan jendela terminal terus terbuka dan memicu proses pembaruan berulang saat halaman detail server dimuat ulang.

4. **Pencegahan Pembukaan Terminal Root Shell Otomatis:**
   - Memperbaiki siklus hidup terminal pada fungsi `resumeAfterApt()` di `services.html`.
   - Proses update paket yang selesai atau dibatalkan tidak lagi secara otomatis membuka sesi WebSocket root shell interaktif, menjaga kenyamanan dan keamanan operator.
   - Menambahkan proteksi pengecekan fungsi pada `getTerm().attach(...)`.

---

## Versi 4.2.0

- **Release Label:** None
- **Tipe Rilis:** Rilis Minor (*Minor Release*) — Penambahan Telemetri Spesifikasi Hardware Mendalam, Sistem Insiden Kritis & Emergency Overlay, Kompatibilitas Proxy/Cloudflare, dan Standardisasi Instalasi Fleksibel Interaktif

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.2.0
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier, 2FA TOTP RFC 6238, dan Isolasi Akun
 ├── 2 (Minor) : Sistem Insiden Kritis Global, Emergency Alert Modal, Telemetri Spek Hardware Mendalam, Dukungan Proxy/Cloudflare & Instalasi Interaktif
 └── 0 (Patch) : Initial Release Minor 4.2.0
```

---

### Perubahan Minor — Versi 4.2.0 (Minor Release)

1. **Telemetri Spesifikasi Hardware & Platform Mendalam (`hardware_specs`):**
   - **Zero-Dependency Native Inspection**: Agen mengumpulkan data perangkat keras dan sistem operasi tanpa paket library pihak ketiga:
     - **CPU**: Model prosesor (`model name`), frekuensi clock (`cpu MHz`), dan ukuran cache (`cache size`) langsung dari `/proc/cpuinfo`.
     - **Platform & Virtualisasi**: Deteksi hypervisor/virtualisasi platform via `systemd-detect-virt` dan DMI (`sys_vendor`, `product_name`, `bios_version`, `bios_date` dari `/sys/class/dmi/id/`).
     - **Kapasitas Memori**: Kapasitas total memori fisik (`MemTotal`) dan swap (`SwapTotal`) dari `/proc/meminfo`.
     - **Penyimpanan Blok**: Pemindaian block device storage melalui `lsblk` untuk mendeteksi tipe drive (`SSD` vs `HDD`), model, dan kapasitas partisi.
     - **Jaringan Host**: Default gateway dari `/proc/net/route`, server DNS dari `/etc/resolv.conf`, serta daftar antarmuka fisik (`/sys/class/net/*`) lengkap dengan MAC address dan link speed.
     - **Waktu Boot**: Kalkulasi tepat stempel waktu boot sistem dari `/proc/uptime`.
   - **Cache Throttling**: Caching selama 45 detik di sisi agen untuk memastikan beban I/O dan CPU tetap minimal.

2. **Sistem Insiden Kritis Global & Modal Peringatan Darurat (`alertOverlay`):**
   - **Eskalasi Insiden Bertingkat**: Otomasi eskalasi insiden agen terputus (*agent stale*):
     - Warning (> 3 menit) → Average (> 5 menit) → Critical (> 15 menit).
   - **Standardisasi Keterangan Insiden**: Penyeragaman pesan insiden global menjadi `"Agen tidak melapor (> X mnt)"` untuk seluruh tingkat keparahan insiden terputus.
   - **Emergency Alert Overlay**:
     - Modal siaga darurat berstatus Critical langsung muncul di dashboard secara realtime tanpa mewajibkan pengguna me-refresh halaman peramban.
     - Menampilkan judul baku `[CRITICAL] Agen Tidak Melapor`, ringkasan keterputusan telemetri (koneksi terputus, agen bermasalah, atau server offline), serta panduan mitigasi inspeksi fisik/virtual mesin langsung.
     - Tabel daftar server terdampak dengan kolom ringkas: *Server Terdampak | Durasi Terputus | Tindakan*.
     - Tombol penanganan langsung `[Tandai ditangani]` dengan konfirmasi API (`/api/incidents/{id}/acknowledge`) yang menyembunyikan modal sementara dari layar kerja tanpa menghapus catatan insiden.
     - Tombol diagnosa dieliminasi dari modal darurat dan tetap dipertahankan secara spesifik pada menu Insiden (`/problems` - Kartu Insiden Terbuka).

3. **Kompatibilitas Reverse Proxy & Cloudflare WAF (Custom User-Agent):**
   - Mengatasi galat `HTTP 403 Forbidden (Error 1010 / Browser Integrity Check)` dari Cloudflare saat agen atau installer mengakses dashboard melalui domain berproksi.
   - Menambahkan header `User-Agent: AgentPantau-Installer/4.2.0` pada skrip instalasi [`package/install.sh`](file:///home/bos/rj45/package/install.sh).
   - Menambahkan header `User-Agent: AgentPantau/4.2.0` pada fungsi request HTTP daemon agen [`package/opt/pantau/agent/agent_pantau.py`](file:///home/bos/rj45/package/opt/pantau/agent/agent_pantau.py) (`http_json_request`).

4. **Standardisasi Alur Instalasi Agen Satu Langkah Interaktif:**
   - Menjadikan alur instalasi interaktif sebagai panduan baku:
     `sudo curl -fsSL -o /tmp/pantau-install.sh https://raw.githubusercontent.com/azhuka/pantau-server/master/package/install.sh`
     `sudo bash /tmp/pantau-install.sh`
   - Installer memandu input URL Dashboard dan API Key secara interaktif tanpa mengharuskan pengguna melakukan hardcode argumen pada CLI.
   - Otomatisasi pengujian konektivitas soket dan validasi HTTP 200 API Key ke Dashboard sebelum file konfigurasi `/etc/pantau/config.json` disimpan.
   - Rekomendasi penggunaan alamat internal LAN/VPN (`http://<IP-LAN>:8400`) untuk komunikasi agen pada subnet privat yang sama.

---

## Versi 4.1.1

- **Release Label:** None
- **Tipe Rilis:** Rilis Patch (*Patch Release*) & Konsolidasi Rilis SemVer (Mayor 4, Minor 1, Patch 1)

### Struktur Rilis SemVer (Major.Minor.Patch)

```
v4.1.1
 │
 ├── 4 (Mayor) : Restrukturisasi Keamanan & Arsitektur RBAC 3-Tier
 ├── 1 (Minor) : Delegasi Izin Sudo Granular, User Activity Audit & Fast Polling Cascade
 └── 1 (Patch) : Bugfix Delay Service, Auto-Unignore SSH, dan Standardisasi Status Biner
```

---

### I. Perubahan Mayor — Versi 4.0.0 (Major Release)
Fokus pada perombakan fondasi keamanan, arsitektur hak akses (RBAC), dan isolasi akun:

1. **Arsitektur Keamanan RBAC 3-Tier (Enterprise Sudo Model):**
   - **Tiga Role Hierarkis**: Pengenalan role baku **Master Admin**, **Operator** (dengan wewenang terdelegasi), dan **Viewer**.
   - **Prinsip Zero-Knowledge Account Isolation**:
     - User Operator dan Viewer sama sekali tidak mengetahui keberadaan user Master Admin. Counter kartu statistik Master Admin, data akun, dan riwayat Master Admin disembunyikan sepenuhnya dari pandangan mereka.
     - User Viewer diisolasi total dari keberadaan Operator dan tidak memiliki akses ke menu Profil & Keamanan. Kredensial akun Viewer dikelola 100% oleh Master Admin atau Operator berwenang.
   - **Proteksi Akun Master Admin Mutlak**: Operator dengan izin tertinggi sekalipun dilarang keras mengubah username, mengubah role, me-lock, atau menghapus akun Master Admin (mirip proteksi akun root di Linux).

2. **Autentikasi Dua Faktor (2FA) TOTP RFC 6238:**
   - Standar Time-based One-Time Password yang kompatibel dengan seluruh aplikasi authenticator (Google Authenticator, Microsoft Authenticator, Aegis, Bitwarden, 1Password).
   - **Two-Stage Pre-Auth Flow**: Validasi username/password awal menerbitkan temporary HMAC token (`preauth_session`) 5 menit sebelum session dashboard utama diberikan.
   - **10 Backup Recovery Codes**: Dihasilkan secara acak kriptografis dan disimpan dalam format hash SHA-256 untuk login darurat saat handphone/authenticator tidak dapat diakses.
   - **Emergency CLI Seed**: Perintah `python3 seed_admin.py --reset-2fa` di server dashboard untuk membuka blokir darurat administrator.

3. **Penyatuan User Management ke Menu "Profil & Keamanan":**
   - Menghapus menu terpisah "User" dari sidebar navigasi dan menyatukan seluruh user management ke rute terpadu `/profile`.
   - Satu pintu untuk ganti password pribadi, setup 2FA, serta administrasi user bagi role yang memiliki izin.

4. **Host Management Suite (Manajemen Sistem Klien Interaktif):**
   - Manajemen user Linux lokal host (add user, lock/unlock via `usermod`, delete user, proteksi root).
   - Manajemen cron job (add, toggle enable/disable, delete, dan run now).
   - Manajemen listening port (kill process pemilik port dan block IP/port via UFW).
   - Manajemen custom path monitoring SSL dan update wrapper sudo berprinsip *least privilege*.

---

### II. Perubahan Minor — Versi 4.1.0 (Minor Release)
Fokus pada penambahan kapabilitas pendelegasian wewenang operator, audit jejak tindakan, dan akselerasi responsivitas UI:

1. **Delegasi Hak Akses Granular Operator (*Sudo-like Privileges*):**
   - Master Admin dapat mendelegasikan wewenang spesifik kepada Operator: manajemen server, kontrol service (Start/Stop/Restart), akses Web Terminal, File Manager, hingga user management.
   - **Modal Inspeksi Izin ("Lihat")**: Tombol untuk review permission matrix yang aktif pada akun user.
   - **Formulir Manajemen Granular ("Edit")**: UI terpadu untuk edit username, reset password standar NIST, ganti role, serta checklist izin dengan tombol instan **⚡ Hak Sudo Penuh**.

2. **User Activity Audit Trail Terdedikasi:**
   - Halaman pelacakan terdedikasi (`/users/{id}/activity`) untuk menginspeksi secara detail seluruh tindakan operasional yang dijalankan oleh masing-masing operator atau user.
   - Akuntabilitas penuh terhadap aksi stop service, ubah konfigurasi, eksekusi command terminal, dan penanganan insiden.

3. **Regenerate Backup Codes Mandiri:**
   - Fasilitas pembuatan ulang 10 recovery codes baru langsung dari web profile tanpa harus mematikan dan setup ulang 2FA.
   - Dilindungi verifikasi konfirmasi password sebelum recovery code baru digenerate.

4. **Optimistic UI Service Control & Fast Polling Cascade:**
   - **Optimistic UI**: Tombol Start, Stop, dan Restart pada Tab Service merespons klik seketika dengan loading spinner dan status visual transisi tanpa menunggu round-trip network.
   - **Fast Polling Cascade**: Dashboard mempercepat interval polling status service ke 1 detik secara berjenjang setelah user melakukan aksi, sehingga perubahan status unit systemd langsung tertangkap tanpa delay normal 10 detik.

---

### III. Perbaikan Masalah & Patch — Versi 4.1.1 (Patch Release)
Fokus pada eliminasi bug siklus hidup service, auto-unignore pemulihan SSH, dan perbaikan UI keamanan:

1. **Penyelesaian Masalah Delay Visual & Pencegahan Klik Ganda Service:**
   - Mengatasi desinkronisasi visual antara Tab Service dan Tab Riwayat & Masalah saat service dihentikan/dimulai.
   - Mencegah klik ganda beruntun oleh operator yang sebelumnya dapat memicu galat `Unit service not loaded. systemctl stop gagal`.

2. **Otomatisasi Pembatalan Pengabaian Service (*Auto-Unignore on Service Recovery*):**
   - Mengatasi anomali di mana service yang sebelumnya dihentikan dan diabaikan (*ignored*) dinyalakan kembali secara manual via SSH terminal oleh sysadmin, namun tombol "abaikan" tetap melekat di web UI.
   - Engine monitoring kini otomatis mendeteksi saat service pulih menjadi aktif (*active/running*), mencabut status pengabaian (*auto-unignore*) secara instan, dan mencatat riwayat pemulihan service ke riwayat tindakan.

3. **Standardisasi Status Riwayat Tindakan Menjadi Nilai Biner:**
   - Menghilangkan pencatatan status non-standar (seperti status bertuliskan "diabaikan" di kolom status riwayat tindakan).
   - Kolom status dibakukan secara tegas hanya memiliki 2 nilai biner: **Berhasil** (*success*) atau **Gagal** (*failed*), dengan rincian aksi dicatat pada kolom hasil/keterangan (misalnya: `"diabaikan (permanen)"`).

4. **Perbaikan Rute & Payload Dialog Regenerate Backup Code 2FA:**
   - Memperbaiki error `422 Unprocessable Entity` (`missing body password`) saat mengklik pembuatan ulang backup code 2FA.
   - Mengganti navigasi langsung peramban dengan alur modal dialog password interaktif dan request AJAX POST terautentikasi.

5. **Penyelarasan UX & Fungsi Tombol Salin/Unduh Backup Code:**
   - Memperbaiki tombol "Salin Semua Kode" dan "Unduh File Teks" agar berfungsi andal di seluruh browser.
   - Menyeragamkan seluruh visual tombol aksi di menu Profil & Keamanan dengan desain tombol standar aplikasi.

---

## Versi 3.23.0

### Fitur Baru & Peningkatan
- **Pembaruan Agent Otomatis Jarak Jauh (Enterprise Over-The-Air / OTA Update):**
  - Penambahan tombol aksi **`⚡ Push Update (OTA)`** pada banner deteksi versi agent usang di halaman Detail Server.
  - **Protokol Transmisi Kriptografis Aman**: Dashboard mengirimkan URL download kode agent terbaru, target versi, dan hash **SHA-256** ke agent client.
  - **Verifikasi Integritas SHA-256 Ketat**: Agent men-download file dan memverifikasi checksum SHA-256; jika hash tidak cocok, proses dibatalkan seketika dengan Security Alert di audit trail.
  - **Validasi Sintaks Python Pra-Pemasangan**: Pengujian sintaks melalui `py_compile` sebelum instalasi untuk mencegah bricked agent.
  - **Penggantian File Atomik & Auto-Restart**: File `/opt/pantau/agent/agent_pantau.py` diganti secara atomik (`chmod 0755`), dilanjutkan auto-restart via systemd watchdog tanpa memutus data historis.
- **Pencatatan Jejak Audit Trail & Riwayat Komprehensif:**
  - Seluruh aktivitas update agent tercatat pada **Audit Trail** global dan tabel **Riwayat Tindakan** per server dengan label `Pembaruan Agent (OTA)`, target versi dan potongan hash (`OTA v3.23.0 (SHA: 386f3e7b…)`), serta status dan response output agent.
- **Siklus Hidup Visual Realtime (Auto-Polling & Banner State):**
  - Tombol `⚡ Push Update (OTA)` dilengkapi animasi loading status (*Mengirim Push OTA…*) dan toast konfirmasi.
  - Auto-polling background otomatis mendeteksi report pertama agent versi baru dan menghilangkan banner versi usang seketika setelah agent aktif kembali.
- **Penyelarasan Siklus Hidup Insiden pada Hapus Service:**
  - Saat service yang bermasalah dihapus dari konfigurasi monitoring, status insiden terkait langsung dibersihkan dan riwayat tindakan mencatat penghapusan service dengan benar.
- **Paginasi Komprehensif pada Tab Riwayat & Masalah:**
  - Penambahan kontrol limit ganda (atas dan bawah tabel) untuk tabel **Status Masalah** (5, 10, 25, 50, Semua) dan tabel **Riwayat Tindakan** (10, 25, 50, 100, Semua).
- **Pembersihan Efek Visual Tab Aktif:**
  - Penghapusan animasi titik berkedip pada tab aktif untuk tampilan yang lebih bersih dan tenang.
- **Modernisasi Sub-Tombol Logging:**
  - Penyelarasan tampilan sub-panel *Log Service* dan *Log System (Journal)* dengan tema biru neon modern.
- **Standardisasi Bahasa Teknis & Eliminasi Dynamic Translation:**
  - Penghapusan mesin alih bahasa dinamis regex dan kamus DOM yang menyebabkan teks gado-gado.

---

## Versi 3.22.0

### Peningkatan Antarmuka & UX
- **Restrukturisasi Urutan Tab Sysadmin:**
  - Susunan tab: *Kinerja* | *Riwayat & Masalah* | *Service* | *Task Manager* | *User Host* | *Listening Port* | *Firewall* | *SSL Certificate* | *Cron Job* | *Logging*.
- **Sorting Kolom Interaktif pada Task Manager:**
  - Sorting langsung dengan klik header kolom (*PID*, *User*, *Command / Process Name*, *Status*, *%CPU*, *%Memory*) dengan indikator panah (▲/▼).
- **Dual Pagination Task Manager:**
  - Menu limit baris di bagian atas dan bawah tabel proses secara tersinkronisasi.
- **Akurasi Indikator Alert Tab Logging:**
  - Titik merah pada tab *Logging* hanya aktif jika terdapat error sistem kritis (priority $\le$ 3) dalam rentang 2 jam terakhir.

---

## Versi 3.21.0

### Fitur Baru
- **Penyatuan Logging System & Service:**
  - Penggabungan log unit systemd dan log journald ke dalam satu tab terpadu dengan switch button.
- **Standardisasi Tema Visual Biru Neon:**
  - Penyeragaman warna aksen tab aktif menggunakan palet biru neon (`#38bdf8`).
- **Indikator Warning Dot pada Tab:**
  - Penanda visual pada tab yang mendeteksi anomali (high load pada Kinerja, service down pada Service, insiden terbuka pada Masalah, firewall nonaktif pada Firewall, dan SSL expired pada SSL).

---

## Versi 3.20.1

### Perbaikan Sistem
- **Fix Template SyntaxError services.html:**
  - Menutup conditional block `{% if %}` yang terpotong pada pengorganisasian kartu service.

---

## Versi 3.20.0

### Fitur Baru
- **Task Manager Interaktif (ala btop):**
  - Default 10 proses dengan opsi pagination modern (10, 25, 50, 100, Semua).
  - Status lifecycle proses Linux (*Running*, *Sleeping*, *Stopped*, *Zombie*).
  - Kontrol sinyal proses langsung dari web: pause (*SIGSTOP*), resume (*SIGCONT*), dan kill (*SIGTERM* / *SIGKILL*).
- **Penyatuan Tab Riwayat Tindakan & Masalah:**
  - Memindahkan audit riwayat tindakan dari tab Service ke tab Masalah agar tab Service lebih bersih dan fokus.

---

## Versi 3.19.0

### Fitur Baru
- **Process Kill Manager:**
  - Action button kill process pada tabel top process pemakan CPU & Memory.
  - Dialog pemilihan sinyal antara terminate (*SIGTERM*) dan force kill (*SIGKILL*).
  - Safety guardrail untuk melindungi proses kritis (*PID 1*, *sshd*, *agent_pantau*).

---

## Versi 3.18.0

### Fitur Baru
- **Visual Firewall Control:**
  - Kontrol visual untuk enable, disable, dan reload firewall UFW.
  - Auto-allow port krusial (SSH 22, Web 80/443, Dashboard 8400) sebelum aktivasi firewall.
  - Form manual block IP dan unblock IP langsung per baris tabel.

---

## Versi 3.17.0

### Fitur Baru & Monitoring Mendalam
- **Monitoring Throughput Disk I/O:**
  - Metrik read/write speed (*KB/s*), IOPS, dan persentase utilisasi disk (*% I/O util*).
- **Journal Error Log Tracking:**
  - Monitoring error kritis sistem (*emerg*, *alert*, *crit*, *err*) dari systemd journald.
- **Audit Listening Port:**
  - Socket aktif, process owner, PID, dan klasifikasi akses (Public vs Local).
- **SSL/TLS Expiry Tracking:**
  - File certificate lokal, domain SAN, CA issuer, dan warning sebelum expired.
- **Cron Jobs & Systemd Timers Monitoring:**
  - Monitoring crontab sistem dan systemd active timer.
- **Dark Theme 2026:**
  - Tema gelap modern dengan grafik area gradient glow.

---

## Versi 3.16.0

### Fitur Baru
- **Socket Activation Support (SSH):**
  - Support unit socket pendamping (`ssh.socket`) saat service dihentikan atau direstart.
- **Flexible Service Muting:**
  - Mute alert service secara permanen atau temporary (2h, 24h, 7d, 30d).
- **Status Counter Service di Dashboard:**
  - Counter service running, stopped, dan muted pada tabel dashboard utama.

---

## Versi 3.15.0

### Fitur Baru & Production Readiness
- **Top 20 Process Snapshot:**
  - Pengumpulan data proses pemakai CPU & RAM tertinggi pada agent client.
- **Maintenance Mode:**
  - Mute alert insiden saat server sedang dalam scheduled maintenance/reboot.
- **Normalisasi Unit Systemd & Cgroup:**
  - Resolusi nama unit asli via cgroup lookup untuk akurasi tracking service.
- **Production Configs:**
  - Nginx reverse proxy template (WebSocket TLS) dan logrotate Uvicorn.
  - Auto pruning tiket masalah yang sudah selesai.

---

## Versi 3.14.0

### Fitur Baru
- **WebSocket Terminal via xterm.js:**
  - Web terminal berbasis xterm.js dengan latensi rendah dan dynamic resize.

---

## Versi 3.13.0

### Fitur Baru
- **Web File Manager:**
  - Directory browser, text file editor (auto backup `.bak`), file upload, dan download.
  - Safety guardrails pada directory core sistem Linux.

---

## Versi 3.11.0 – 3.12.0

### Fitur Baru
- **Native Linux PTY Shell Integration:**
  - Membuka shell `/bin/bash` dengan emulasi VT100 control sequences via Python `pty`.

---

## Versi 3.7.0 – 3.10.0

### Fitur Baru & Keamanan
- **Remote OS Update:**
  - Eksekusi `apt update` dan `apt upgrade` via web dashboard.
  - Penguatan sudo permission agent (*least privilege*) dan validasi token CSRF.

---

## Versi 3.6.0

### Fitur Baru
- **Host Control (Reboot OS & Power Off):**
  - Command reboot dan poweroff dengan delayed execution agar report terkirim sebelum host mati.

---

## Versi 1.0.0 – 3.5.0

### Fondasi Awal
- Pembangunan dashboard monitoring berbasis FastAPI dan MariaDB.
- Pengembangan agent client Python standar untuk telemetri metrik CPU, Memory, Swap, Disk, dan Network.
