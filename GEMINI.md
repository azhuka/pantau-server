# Project Rules: Pantau Server Application

Berkas ini adalah spesifikasi teknis dan aturan baku permanen (*always-on project rules*) khusus bagi aplikasi **Pantau Server** (`/home/bos/pantau-server`). Seluruh ketentuan di bawah ini wajib dipatuhi secara ketat tanpa pengecualian.

---

## 1. Esensi Sistem Pantau Server & Batas Cakupan (Scope Boundary)
- **Sistem Monitoring NOC Mandiri:** Berorientasi pada kemudahan observasi, stabilitas operasional jangka panjang, dan kepadatan data tinggi (*high density*).
- **Halaman Dasbor Murni Pasif (Proteksi Mutlak):** Berkas `DashboardView.vue` adalah area **MURNI PASIF** untuk pemantauan makro, banner KPI 3-kartu (Total Servers, Active Incidents 5-strip, System Clock), dan tabel insiden pasif. Dilarang keras menambahkan tombol aksi aktif atau tombol mutasi di halaman dasbor.
- **Jendela Kontrol Taktis Mengambang (Workspace Modal):** Seluruh aksi kontrol aktif dan investigasi per host (restart service, kill task, putus sesi SSH, audit port, firewall, cron) berada eksklusif di dalam modal mengambang `ServerWorkspaceModal.vue`.
- **Kemandirian Agen Klien:** Agen klien (`agent_pantau.py`) wajib mempertahankan prinsip *zero external dependency* (hanya pustaka standar Python 3.10+).
- **Standar Bahasa Antarmuka (English Default & i18n Reaktif):** Antarmuka web default menggunakan **Bahasa Inggris (`en`)** baku NOC/sysadmin (Overview, Incidents, Services, Tasks, Ports, Firewall, Total Servers, Active Incidents, System Clock, Fleet Inventory) dengan sakelar reaktif instan ke **Bahasa Indonesia (`id`)** (`[ 🌐 EN | ID ]`). Dilarang keras men-hardcode teks lokal di template komponen.
- **Protokol Kecepatan & Efisiensi Eksekusi (Anti-Bekerja Berjam-jam):**
  - Tugas perbaikan bug atau penambahan fitur terfokus wajib diselesaikan secara terarah dan terencana (target 2–4 *turns*, durasi di bawah 5 menit).
  - Dilarang melakukan eksplorasi database/file secara berulang-ulang tanpa arah (*trial-and-error*).
  - Wajib memanfaatkan skrip otomasi [`tools/sop_release.py`](file:///home/bos/pantau-server/tools/sop_release.py) untuk seluruh alur rilis produksi agar proses build, restart, dan deployment selesai dalam hitungan detik.

---

## 2. Aturan Baku Paginasi Tabel (Jika-Maka $\le 10$ Baris)
- **Logika Otomatis Sembunyi/Tampil Universal:**
  - **JIKA** total baris data pada tabel kurang dari atau sama dengan 10 baris ($\le 10$), **MAKA** bilah kontrol paginasi (`.table-pagination-bar`) **wajib otomatis disembunyikan (`display: none !important`)**.
  - Bilah paginasi **HANYA boleh tampil (`display: flex`) JIKA** total baris data melebihi 10 baris ($> 10$).
- **Larangan Keras `alwaysShow: true`:**
  - Dilarang keras menyematkan opsi `alwaysShow: true` pada inisialisasi tabel apa pun kecuali ada instruksi tertulis eksplisit dari operator untuk tabel spesifik tersebut.
- **Integrasi Mesin Universal:**
  - Seluruh paginasi tabel wajib menggunakan mesin terpadu `attachTablePagination(table, options)` di `server/templates/base.html` dan didaftarkan pada kamus `_servicesTabPagination`.

---

## 3. Aturan Baku Tabel: Header Kolom & Kolom Tindakan
- **Format Penulisan Nama Kolom (Kapitalisasi):**
  - Seluruh nama kolom pada seluruh tabel **wajib diawali huruf besar dan sisanya huruf kecil** (Contoh: `Tindakan`, `Waktu`, `Pengguna`, `Status`, `Durasi`, `Kejadian`, dll. Dilarang keras menggunakan huruf kapital semua seperti *TINDAKAN* atau *AKSI*).
- **Standardisasi Header Kolom Kontrol:**
  - Nama header kolom kontrol tombol pada seluruh tabel diseragamkan menjadi **"Tindakan"**.
- **Keseragaman Tingkat Tabel untuk Isi Sel Kolom "Tindakan" (Bukan Per Baris):**
  - Pola tampilan tombol pada kolom "Tindakan" ditentukan pada **skala tabel secara utuh dan seragam**. Dilarang mencampuradukkan tombol langsung dengan menu dropdown dalam satu tabel yang sama.
  - **Tabel dengan > 2 Tombol Aksi:** Jika kapabilitas tindakan pada tabel tersebut menyediakan lebih dari 2 jenis tombol aksi, maka **seluruh baris pada tabel tersebut secara seragam menggunakan menu dropdown berlabel "Aksi ▾"** (`<details class="noc-act-dropdown">`).
  - **Tabel dengan 1 atau 2 Tombol Aksi:** Jika tabel hanya memiliki 1 atau 2 jenis tombol aksi (misalnya tabel Port yang hanya memiliki Hentikan & Lepas Blokir, atau tabel Proses), maka **seluruh baris menampilkan tombol aksi langsung secara sejajar (*inline*)**.
- **Pencegahan Menu Terpotong (*Stacking Context*):**
  - Setiap menu dropdown "Aksi ▾" wajib memiliki elevasi `z-index: 9999` saat dibuka agar tidak tertutup oleh sel *sticky* atau baris tabel di bawahnya.
- **Standar Ikon Umum Tanpa Label Teks Boros:**
  - Tombol-tombol aksi umum yang fungsinya telah dikenal luas (seperti Tutup, Hapus, Tambah, Salin, Muat Ulang/Refresh, Kunci, Lepas Kunci) cukup diwakili oleh ikon SVG baku yang bersih dan intuitif dengan tooltip `title="..."` yang informatif, tanpa label teks panjang yang memboroskan ruang tabel.

---

## 4. Aturan Kepadatan Data & Fleksibilitas Proporsi Kolom (NOC Data Density)
- **Proporsi Kolom Fleksibel (Tidak Kaku):**
  - Kolom informatif mendapatkan ruang lebih leluasa, kolom ringkas tidak boros ruang.
  - Pemecahan nama kolom menjadi 2 baris (`<br>`) atau penyingkatan dilakukan **secara kontekstual dan selektif**, HANYA jika nama kolom memang sangat panjang dan secara nyata melebarkan kolom sehingga memboroskan ruang layar. Kolom yang wajar dan proporsional (seperti `Uptime 24j`) **tetap dipertahankan 1 baris**.
- **Hierarki Data (Esensial vs Non-Esensial):**
  - **Data Esensial (Pokok/Inti):** Ditampilkan lengkap, jelas, dan proporsional bagi operator.
  - **Data Non-Esensial / Pelengkap / String Panjang:** (misalnya detail detik waktu, DN lengkap sertifikat SSL, path direktori panjang) diakali menggunakan pesan *tooltip* (`title="..."`) atau pemotongan rapi (*ellipsis*), tanpa merusak lebar kolom.
- **Format Kolom Waktu Ringkas:**
  - Waktu tabel tidak menampilkan detik non-esensial di dalam sel (`%H:%M` atau `%d %b %H:%M`). Rincian lengkap hingga detik dan tanggal penuh dialihkan ke tooltip hover `title="..."`.
- **Kolom Ukuran Direktori:**
  - Sel kolom Ukuran untuk direktori hanya menampilkan teks ringkas **`"Direktori"`** tanpa embel-embel jumlah file di dalam sel. Rincian penghitungan (*"X direktori, Y file"*) wajib ditampilkan melalui tooltip `title="..."`.
- **Skala Ukuran Font & Standar Keterbacaan 100% Zoom (Anti-Font Mikroskopis):**
  - Base font antarmuka menggunakan **Sans-Serif modern** (`Inter` / system sans-serif: `-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`). Font monospace (`font-mono`) **HANYA** untuk metrik angka telemetri, IP, port, kode status, atau terminal.
  - **Larangan Keras Font Mikroskopis (<12px):** Seluruh teks wajib terbaca tajam dan nyaman pada skala normal 100% tanpa zoom.
  - Skala tipografi baku: Judul kartu/seksi 15px–16px (`text-base`), isi sel tabel 13.5px–14px (`text-sm`), label/header kolom 12px (`text-xs font-bold uppercase`), badge status 12px (`text-xs font-bold`), angka KPI 24px–28px (`text-2xl`–`text-3xl font-extrabold`).
  - Padding sel dan kartu dirancang proporsional dan nyaman (`py-2.5 px-3` / `py-2.5 px-4` per sel, `p-3 px-4` per kartu), tidak berdesak-desakan.

---

## 5. Aturan Arsitektur Render (Dual-Render Synchronization)
- **Sinkronisasi Wajib Server-Side & Client-Side:**
  - Setiap tabel yang dirender awal oleh server (Jinja HTML) dan dirender ulang oleh klien (JavaScript via WebSocket, Polling, atau Filter) **wajib dimodifikasi secara sinkron dan identik**. Dilarang keras hanya mengubah salah satunya.

---

## 6. Protokol Baku Pengembangan UI/UX (Anti-Kebutaan Piksel & Multi-Theme Contrast)
- **Kemandirian Data Klien (Anti-Hardcode Opsi Fiktif):**
  - Seluruh opsi, tombol, dan menu pada antarmuka **wajib bersumber murni dari laporan telemetri fisik agen klien** (`agent_pantau.py`).
  - Dilarang keras men-hardcode opsi layanan yang tidak ada (misalnya menampilkan opsi log Apache pada server yang hanya memiliki Nginx).
- **Kepatuhan Kontras Multi-Tema (Anti-Teks Buta):**
  - Dilarang keras men-hardcode warna teks atau latar belakang statis yang menyebabkan benturan kontras (misal teks putih di latar putih, teks merah di latar merah, teks biru di latar biru, atau teks abu-abu gelap di latar hitam).
  - Seluruh elemen antarmuka wajib adaptif menggunakan variabel CSS semantik (`var(--card)`, `var(--text)`, `var(--dim)`, dll.) yang teruji kontrasnya secara tajam dan ramah mata pada Dark Mode maupun Light Mode.
- **Integritas Ergonomi Visual (No Obstructive Elements & Precision Layout):**
  - Dilarang menempatkan elemen melayang (*floating buttons/overlays*) yang menutupi baris teks, konsol, atau data tabel. Kontrol navigasi wajib diletakkan pada toolbar atas atau statusbar footer terstruktur.
  - Setiap tampilan berbasis baris/konsol terminal wajib menggunakan arsitektur baris terpadu flexbox (`.noc-log-row`) di mana nomor baris dan teks isi berada dalam kontainer yang sama, mencegah desinkronisasi atau nomor baris hantu (*phantom line numbers*) saat teks mengalami pembungkusan (*word-wrap*).
- **Protokol 2-Tahap: Visual Statis Dulu, Logika Belakangan:**
  - **Tahap 1 (Prototipe Visual Statis):** Untuk setiap perombakan antarmuka atau komponen baru (modal, tab, konsol), asisten wajib menyajikan dan memvalidasi prototipe visual (HTML/CSS) statis terlebih dahulu tanpa menghubungkan logika backend/database/WebSocket yang rumit.
  - **Tahap 2 (Persetujuan Operator):** Asisten dilarang melanjutkan ke manipulasi backend, skema database, atau endpoint telemetri sebelum operator secara eksplisit menyetujui estetika, proporsi, padding, tipografi, dan ergonomi visual pada Tahap 1.

---

## 7. Kebijakan Khusus Proxmox HA & Proteksi Mesin
- VM atau LXC dengan `is_proxmox_ha = 1` dilarang dimatikan dari dalam via tombol *Power OFF*.
- Tombol *Power OFF* dinonaktifkan (`disabled`, kursor `not-allowed`) dan backend menolak request dengan pesan peringatan resmi.

---

## 8. Aturan Baku Manajemen Pengguna & Kesetaraan Otoritas Operator (RBAC Parity)
- **Kesetaraan Fungsional Operator Penuh:** Akun `master_admin` berhak mengangkat akun `operator` dengan hak akses global penuh (seperti `sysadmin_sadri`) yang memiliki otoritas operasional identik dengan `master-admin` atas seluruh server klien di armada.
- **Proteksi Mutlak Integritas Akun:**
  - Akun operator DILARANG KERAS menghapus akun dirinya sendiri.
  - Akun operator DILARANG KERAS menghapus akun `master-admin`.
- **Tata Kelola Wewenang Berbasis Izin Granular (`can_*`):** Pembagian tugas di Pantau Server murni didasarkan pada matriks izin granular yang diberikan oleh administrator. Jika seluruh izin diberikan, akun tersebut adalah operator penuh tanpa diskriminasi kapabilitas teknis di lapangan.
- **Perlakuan Keamanan Setara:** Setiap fitur keamanan sistem (termasuk Web Terminal non-root, eskalasi `sudo`, penegakan 2FA/TOTP, dan kontrol daya) wajib memperlakukan operator berakses penuh secara setara dengan `master-admin`.

---

## 9. Alur Kerja Wajib (Workflow) & Otomasi Rilis
### A. Sebelum & Saat Men-generate Kode
- Pertahankan prinsip *zero external dependency* pada agen klien.
- Hindari eksekusi shell tanpa sanitasi (`shell=False`, least-privilege).
- **Audit Menyeluruh (Anti-Pekerjaan Parsial):** Dilarang melakukan perbaikan sepotong (*local patch*). Asisten wajib melakukan pencarian global (`grep`) ke seluruh berkas proyek (`server/templates/`, `server/static/`) untuk memastikan aturan telah diterapkan konsisten pada semua halaman dan tab yang relevan sebelum pekerjaan dinyatakan selesai.

### B. Setelah Men-generate Kode (Wajib Otomatis Menggunakan Skrip Rilis)
Setiap kali menyelesaikan pekerjaan (bugfix/fitur baru/refactor):
**Wajib menggunakan skrip otomatisasi satu perintah [`tools/sop_release.py`](file:///home/bos/pantau-server/tools/sop_release.py)** agar seluruh rangkaian berikut selesai secara atomik dalam **15–30 detik**:
```bash
./tools/sop_release.py [versi_baru] \
  --commit-msg "jenis(lingkup): deskripsi bahasa baku (vX.Y.Z)" \
  --title "vX.Y.Z - Judul Baku Bahasa Indonesia" \
  --notes "Rincian rilis untuk GitHub Releases" \
  --changelog "Blok catatan teknis untuk dimasukkan ke DEVELOPMENT.md" \
  --extra-files <berkas_tambahan_yang_diubah>
```

Skrip tersebut secara otomatis mengeksekusi 4 pilar SOP:
1. **Menaikkan Versi SemVer Secara Sinkron di 7 Berkas:**
   - `server/config.py` (`APP_VERSION`)
   - `server/templates/base.html` (`v{{ app_version ... }}`)
   - `package/opt/pantau/agent/agent_pantau.py` (`AGENT_VERSION`)
   - `agent/agent_pantau.py` (sinkron identik)
   - `package/install.sh` (User-Agent installer & meta-version)
   - `README.md` (deskripsi & fitur utama)
   - `DEVELOPMENT.md` (blok changelog rilis baru dengan format terstruktur)
2. **Kompilasi & Uji Sintaksis:**
   - `python3 -m py_compile` seluruh berkas python terkait.
   - `bash -n` seluruh berkas skrip shell terkait.
   - Uji sintaksis template Jinja / validasi HTML.
3. **Penyebaran Agen & Restart Service:**
   - Salin agen ke `/opt/pantau/agent/agent_pantau.py`.
   - `sudo systemctl restart agent_pantau.service`
   - `sudo systemctl restart pantau-server.service` dan pastikan status `active (running)`.
4. **Git, Tag & GitHub Release:**
   - `git add <berkas>`
   - `git commit -m "jenis(lingkup): deskripsi baku (vX.Y.Z)"`
   - `git push origin master`
   - `git tag -a vX.Y.Z -m "Release vX.Y.Z: Judul Baku"`
   - `git push origin vX.Y.Z`
   - `gh release create vX.Y.Z --title "vX.Y.Z - Judul Baku" --notes "..."`

---

## 10. Kebijakan Keandalan Auto-OTA Armada Klien & Validasi Lapangan Mutlak (Zero-Stall OTA)
- **Larangan Keras Klaim Selesai Buta (*Anti-Blind Completion Claim*):**
  - Dilarang keras berasumsi atau menyatakan tugas rilis selesai hanya karena perintah build atau skrip rilis berhasil.
  - Asisten **WAJIB melakukan kueri verifikasi lapangan nyata ke basis data** (`SELECT s.id, s.hostname, e.agent_version, s.last_seen FROM servers s LEFT JOIN server_extras e ON s.id=e.server_id ORDER BY s.id;`) untuk membuktikan 100% armada host klien aktif telah menerima, me-restart, dan melaporkan versi baru ke server sebelum menyatakan pekerjaan tuntas kepada operator.
- **Arsitektur Antrean OTA Bebas Penguncian (*Zero-Lockout Pipeline*):**
  - **Larangan Keras Cooldown Global:** Dilarang keras menaruh filter waktu tunggu kaku (seperti pemblokiran global 5 menit) pada `/api/commands` yang memblokir dispatch versi baru. Versi baru wajib dapat di-dispatch seketika (*instant dispatch*) pada heartbeat berikutnya.
  - **Auto-Heal Timeout Maksimal 2 Menit:** Setiap perintah `update_agent` yang tersangkut di status `executing` lebih dari 2 menit wajib otomatis di-failkan oleh server agar antrean pembaruan tidak tersumbat.
  - **Auto-Resolve via Heartbeat `/api/report`:** Server wajib otomatis menyelesaikan status perintah `update_agent` menjadi `success` begitu menerima telemetri aktif pertama dari agen klien yang membuktikan versi agennya telah naik.
  - **Jeda Restart Daemon Agen Minimal 4 Detik:** Jeda terminasi proses lama pada `_exec_restart_agent()` di `agent_pantau.py` wajib minimal 4 detik (`sleep 4; kill -TERM <pid>`), memberikan waktu yang aman bagi agen untuk mengirimkan status laporan hasil via HTTP POST ke server sebelum proses lama ditutup.

---

## 11. Daftar Ceklis Disiplin Teknis Sebelum Melapor (Pre-Flight System Checklist)
Sebelum asisten AI menyatakan pekerjaan selesai ke operator, wajib memverifikasi secara teknis:
1. **Proteksi Dasbor:** Apakah berkas `dashboard.html` tetap utuh dan tidak disentuh sama sekali? (**Wajib: YA**).
2. **Paginasi Universal:** Apakah aturan paginasi $\le 10$ baris disembunyikan otomatis (`display: none !important`) dipatuhi tanpa `alwaysShow: true`? (**Wajib: YA**).
3. **Standarisasi Tindakan:** Apakah header kolom tombol bernama "Tindakan" dengan kapitalisasi benar dan seragam se-tabel (inline jika $\le 2$ aksi, dropdown `Aksi ▾` jika $> 2$ aksi)? (**Wajib: YA**).
4. **Kontras Multi-Tema:** Apakah kontras multi-tema aman (tidak ada teks putih di latar putih / teks gelap di latar gelap)? (**Wajib: YA**).
5. **Dual-Render Sinkron:** Apakah dual-render Jinja server-side dan JS client-side disinkronkan identik tanpa selisih? (**Wajib: YA**).
6. **Otomasi SemVer 7 Berkas:** Apakah versi SemVer dinaikkan sinkron di 7 berkas via skrip `sop_release.py`? (**Wajib: YA**).
7. **Verifikasi Lapangan 100% Armada:** Apakah 100% server klien aktif telah diverifikasi nyata di basis data sudah melapor pada versi baru? (**Wajib: YA**).
8. **Kesetaraan Otoritas Operator (RBAC Parity):** Apakah perlindungan integritas akun (larangan hapus diri sendiri & master-admin) serta kesetaraan wewenang operator penuh dipatuhi? (**Wajib: YA**).
9. **Arsitektur Agnostik & Bebas Hardcode:** Apakah seluruh implementasi bebas dari hardcoding string/nama spesifik aplikasi pihak ketiga dan murni mengandalkan penemuan dinamis atau karakteristik fisik sistem? (**Wajib: YA**).

---

## 12. Arsitektur Agnostik & Larangan Mutlak Hardcoding Sistem (Universal Zero-Hardcode Standard)
- **Larangan Keras Asumsi Statis & Hardcoding Pihak Ketiga:**
  - Dilarang keras men-hardcode nama aplikasi, plugin, path berkas, nama layanan, atau pola vendor spesifik di dalam kode inti agen maupun server (seperti daftar statis path log, nama service pihak ketiga, atau pengecualian nama file).
  - Sistem Pantau Server adalah platform NOC mandiri yang wajib beroperasi secara **universal dan agnostik** terhadap sembarang server Linux dan tumpukan aplikasi apa pun.
- **Prinsip Penemuan Dinamis (*Dynamic Discovery over Static Guessing*):**
  - Seluruh pengenalan objek sistem (layanan, port, proses, log, paket, sertifikat) wajib bersumber dari **inspeksi dinamis kondisi riil host**:
    1. **Layanan & Port:** Dipetakan dari proses yang secara nyata sedang mendengarkan (*listening*) via `procfs`/socket kernel, bukan dari kamus port statis.
    2. **Log & Telemetri:** Diperoleh dari unit `systemd` aktif atau berkas log yang terkonfigurasi pada runtime, bukan menebak lokasi path statis.
    3. **Integritas Berkas & Keamanan:** Dievaluasi berbasis karakteristik atribut fisik objek (izin `chmod`, kepemilikan `chown`, tipe berkas, status eksekusi), bukan mencocokkan string nama file secara kaku.
    4. **Manajemen Paket & OS:** Menggunakan probing manajer paket dan lingkungan runtime riil host secara agnostik.
- **Audit & Eliminasi Hardcode Warisan:**
  - Setiap kali menyentuh modul yang masih menyimpan jalan pintas hardcode lama, asisten AI wajib merefaktornya secara bertahap menuju arsitektur penemuan dinamis tanpa memecah kontrak data.

---

## 13. Larangan Keras Jalan Praktis & Mandat Standar Produksi Sejati (Anti-Shortcut Mandate)
- **Larangan Mutlak Jalan Pintas Kompromis:** Dilarang keras memilih, mengusulkan, atau mengimplementasikan jalan pintas praktis (*lazy shortcuts*) yang mengorbankan ketangguhan arsitektur produksi (seperti mengusulkan SQLite untuk sistem pemantauan NOC yang melayani semburan telemetri simultan banyak server klien).
- **Standar Rekayasa Sejati:** Setiap keputusan teknis wajib berdiri tegak di atas prinsip rekayasa perangkat lunak sejati: merancang untuk konkurensi riil, integritas data tingkat kernel, efisiensi sumber daya, dan keandalan operasional 24/7/365.

---

## 14. Larangan Mutlak Nomenklatur Spekulatif "v2" & Kepatuhan SemVer v0.1.0
- **Larangan Keras Label "v2":** Aplikasi ini BUKAN v2 dan DILARANG KERAS melabeli, mendefinisikan, atau menamai basis data, variabel, branch, berkas, atau dokumentasi dengan istilah "v2" dalam bentuk apa pun.
- **Identitas Tunggal Sah:** Aplikasi ini bernama resmi **Pantau Server** yang sedang dibangun dari baseline awal **`v0.1.0`**.
- **Penamaan Objek Sistem:** Seluruh nama basis data, skema, dan variabel wajib mencerminkan identitas resmi aplikasi (misalnya `pantau_server` atau `pantau_clean_db`), tanpa embel-embel versi spekulatif.

---

## 15. Protokol Eksekusi Mandat `/learn` (Eksekusi Instan Tanpa Menunggu Konfirmasi)
- **Eksekusi Langsung:** Setiap kali operator mengetikkan perintah `/learn`, hal tersebut merupakan **instruksi aturan mutlak** yang wajib langsung dibukukan, diterapkan, dan dikunci secara permanen ke dalam berkas tata kelola (`GEMINI.md`, `AGENTS.md`, `tasks/lessons.md`).
- **Larangan Meminta Konfirmasi Ulang:** Dilarang keras menunda eksekusi, bersikap pasif, atau meminta konfirmasi/persetujuan berbelit-belit kepada operator saat `/learn` telah diberikan. Catat dan terapkan seketika.

---

## 16. Kemurnian Konseptual & Isolasi Data Mutlak (Clean Slate Architecture)
- **Spesifikasi Standar Operasional NOC:** Seluruh alur kerja (*workflow*), tata letak kartu, navigasi interaksi, hierarki telemetri NOC, dan jendela taktis mengambang diwujudkan secara utuh sebagai standar baku orisinal Pantau Server.
- **Isolasi Mutlak (Clean Slate Database):** Sistem beroperasi dengan skema dan basis data mandiri murni (`pantau_server_db`). Dilarang keras menyalin, mengaitkan, atau menduplikasi struktur tidak konsisten atau data historis kotor dari lingkungan pengujian apa pun.

---

## 17. Siklus Pembelajaran Mandiri & Pencatatan Kesalahan Permanen (CDiP)
- **Pencatatan Kesalahan Wajib:** Setiap kali terjadi kesalahan teknis, anomali logika, atau koreksi keras dari operator, asisten WAJIB mencatatnya secara permanen ke dalam [`tasks/lessons.md`](file:///home/bos/pantau-server/tasks/lessons.md) sebagai pengingat abadi.
- **Struktur Catatan:** Setiap entri pelajaran wajib memuat secara transparan: Konteks Kejadian, Akar Masalah (Root Cause), dan Aturan Pencegahan Konkret.
- **Larangan Mengulang Kesalahan:** Asisten dilarang keras mengulang kesalahan yang sudah pernah ditegur dan dicatat di dalam berkas pembelajaran.
