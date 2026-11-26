# Project Rules: Pantau Server Application

Aturan teknis baku (*always-on project rules*) untuk **Pantau Server** (`/home/bos/pantau-server`). Panduan operasional ringkas tersedia di [`AGENTS.md`](file:///home/bos/pantau-server/AGENTS.md). Seluruh ketentuan di bawah ini wajib dipatuhi tanpa pengecualian dan dijaga tetap ringkas agar tidak pernah terpotong oleh batas konteks.

---

## 1. Esensi Sistem & Batas Cakupan
- **Dasbor Murni Pasif & Zero-Hidden (`DashboardView.vue`):** Khusus pemantauan makro 24/7/365 (KPI 3-kartu, insiden aktif, inventaris utuh). Dilarang menambah kolom/tombol aksi atau paginasi di dasbor; navigasi host hanya via klik baris pasif.
- **Jendela Kontrol Mengambang (`ServerWorkspaceModal.vue`):** Seluruh kontrol aktif dan investigasi per host berada eksklusif di dalam modal mengambang.
- **Kemandirian Agen Klien:** `agent/agent_pantau.py` wajib *zero external dependency* (hanya pustaka standar Python 3.10+).
- **Bahasa Antarmuka Eksklusif Bahasa Inggris:** Seluruh UI web dan pesan respons API wajib Bahasa Inggris baku NOC/sysadmin; dilarang men-hardcode teks non-Inggris.
- **Prioritas Browser:** Gunakan Moli (`moli-webfetch` / `moli-cdp-server`) terlebih dahulu; Chrome DevTools hanya cadangan.
- **Otomasi Rilis Otonom (`sop-pantau`):** Setiap selesai perbaikan bug/fitur (dan teruji `py_compile` + `npm run build`), wajib langsung mengeksekusi alur [`sop-pantau`](file:///home/bos/pantau-server/.agents/skills/sop-pantau/SKILL.md) secara penuh tanpa menunggu perintah tambahan: naikkan SemVer via [`tools/sop_release.py`](file:///home/bos/pantau-server/tools/sop_release.py), perbarui `DEVELOPMENT.md`/`README.md`, restart daemon `pantau-server`, commit & push Git/GitHub Release, serta verifikasi database.

## 2. Paginasi, Tabel & Ergonomi Tombol
- **Paginasi Tabel Sekunder ($\le 10$ Baris Sembunyi):** Pada tabel selain Dasbor, jika total baris $\le 10$ maka bilah paginasi wajib disembunyikan (`NocTablePagination`). Dilarang `alwaysShow: true`.
- **Header & Kolom Tindakan:** Header kolom wajib Title Case (`Actions`, `Triggered At`, `Incident Description`, `Severity`, `Duration`, `Solution`). Tabel dengan $>2$ jenis aksi wajib memakai dropdown `Actions ▾` (`z-index: 9999`); tabel dengan $1$–$2$ aksi memakai tombol inline `26x26px`; peran Viewer hanya ikon lihat `26x26px`.
- **Disabled States & Zero-Emoji:** Tombol non-aktif wajib `opacity: 0.38`, `cursor: not-allowed`, klik diblokir, dan `title="..."` alasan jelas. Dilarang memakai emoji bergambar/simbol non-SVG di UI; gunakan ikon SVG vektor tipis.
- **Zero-Floating Overlays & Kontras Multi-Tema:** Dilarang menempatkan tombol melayang menutupi teks log/tabel; warna wajib memakai CSS variabel semantik agar tajam di Dark/Light mode.
- **Proteksi Penutupan Modal (No Backdrop Click-to-Close):** Seluruh modal tidak boleh tertutup saat operator mengklik area luar (*backdrop*); modal hanya boleh ditutup melalui tombol *Close* atau tombol `Esc`, dan proses latar belakang yang sedang berjalan tidak boleh terhenti saat modal ditutup.

## 3. Proteksi Proxmox HA & RBAC Parity
- **Proxmox HA:** Host dengan `is_proxmox_ha = 1` dilarang dimatikan dari dalam via `Power OFF` (tombol non-aktif + ditolak backend).
- **Zero-Knowledge Master Admin:** Akun `master-admin` disembunyikan mutlak dari Operator/Viewer (counter disembunyikan, tabel disaring, API membalas `404 Not Found`, Audit Trail disamarkan sebagai `System`).
- **RBAC 3-Tier:** Operator tidak boleh mengubah izin operator lain atau menghapus dirinya sendiri/`master-admin`. Viewer murni *read-only* (*no self-edit*).

## 4. Keandalan Auto-OTA & Verifikasi Lapangan
- **Zero-Cooldown & Auto-Heal:** Tidak ada cooldown global yang memblokir OTA; `update_agent` yang tersangkut di `executing` $>2$ menit wajib otomatis di-failkan; heartbeat `/api/report` otomatis menyelesaikan status `update_agent` ke `success` saat versi baru melapor. Jeda terminasi proses lama minimal 4 detik.
- **Verifikasi Lapangan Mutlak:** Setelah rilis agen, wajib menjalankan kueri SQL ke `pantau_db` untuk membuktikan 100% aset aktif telah melapor pada versi baru.

## 5. Arsitektur Agnostik, Zero-Hardcode & Supremasi Blueprint
- **Penemuan Dinamis (*Dynamic Discovery*):** Layanan, port, proses, log, paket, dan integritas berkas wajib bersumber dari kondisi riil kernel Linux (`/proc`, `/sys`, socket, systemd), bukan kamus statis/hardcode.
- **Zero-Workaround & Zero-Hack:** Dilarang memakai jalan pintas, SQLite, regex substring hack rapuh di UI, data dummy, atau label spekulatif `"v2"`. Wajib menjaga pemisahan lapisan (`routers/` transport, `services/` domain logic, `models/` skema InnoDB, `components/` $<250$ baris).
- **Supremasi Blueprint & Zero-Touch App Lama:** Wajib memeriksa rujukan di `/home/bos/rj45` secara *read-only* sebelum mengubah/menambah UI atau alur kerja di `/home/bos/pantau-server`, tanpa pernah menyentuh satu byte pun berkas atau proses di `/home/bos/rj45`.
- **Web Terminal:** Wajib menggunakan `xterm.js` + `FitAddon` (dilarang `<input>` satu baris), *keep-alive* saat diminimalkan, dan pembersihan PTY bersih saat terputus.

## 6. Glosarium, Taksonomi Insiden & Dokumentasi
- **Istilah Baku:** `pantau-server`, `pantau-agent`, `Assets` (dilarang *fleet*/*armada*), `Incidents` / `Active Incidents` (dilarang *insiden terbuka*/*Problem*), istilah baku NOC/Linux (`Actions`, `Server Details`, `Listening Ports`, `Firewall Rules`, `Load Average`, `Latency`, `Uptime`, `MTTR`). Dilarang prefiks `// ` pada UI atau istilah karangan (*investigate*, *magic*, *tactical*).
- **Severity 4-Tingkat:** `info` (biru: non-ancaman seperti update OS atau sesi SSH sah), `warning` (kuning: potensi gangguan/ancaman seperti brute-force awal atau kapasitas mendekati batas), `critical` (oranye: layanan utama terganggu/mati, brute-force tinggi), `danger` (merah: host offline, disk read-only, kernel panic).
- **Dokumentasi (`README.md` & `DEVELOPMENT.md`):** Dilarang menyebut/membandingkan app lama di kedua dokumen ini (*clean slate*). Setiap perubahan arsitektur/konvensi baru wajib langsung dicatat ke `DEVELOPMENT.md`.
- **Eksekusi `/learn`:** Instruksi `/learn` langsung dibukukan ke aturan yang tepat (global vs proyek) tanpa menunda atau meminta konfirmasi berbelit.
- **Zero-Unrequested UI & Zero-Placeholder:** Dilarang menambah tab, tombol, ikon, atau fitur UI yang tidak diminta atau belum berfungsi penuh. Setiap elemen kontrol yang tampil ke operator wajib berfungsi nyata, jelas tujuannya, serta memakai ikon dan label yang tidak ambigu.
- **Zero-Foolishness & Strict Scope Mandate:** Dilarang keras mengarang fitur/UI/abstraksi di luar permintaan, menaruh tombol/fitur setengah jadi atau ikon ambigu, menebak tanpa memeriksa kode/runtime nyata, atau menelan error diam-diam. Setiap perubahan wajib diminta, minimal, tuntas, dan terverifikasi penuh.
- **Nalar Rekayasa Pragmatis:** Gunakan nalar rekayasa perangkat lunak sebelum bertindak—pertimbangkan dampak operasional, kejelasan UX bagi operator manusia, serta efek samping (loop sia-sia, kegagalan tersembunyi, kompleksitas berlebih), bukan sekadar menempel pola secara mekanis.
- **Kepatuhan Penuh & Zero-Shortcut:** Tegakkan seluruh aturan global dan proyek secara utuh dari awal hingga akhir—tanpa melewati langkah, tanpa memotong verifikasi, dan tanpa pengerjaan setengah-setengah.
