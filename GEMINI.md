# Workspace Rules: Pantau Server Development

Berkas ini adalah aturan baku permanen (*always-on project rules*) bagi asisten AI dalam memelihara dan mengembangkan proyek **Pantau Server**. Seluruh ketentuan di bawah ini wajib dipatuhi secara ketat tanpa pengecualian.

---

## 1. Esensi Sistem Pantau Server & Batas Cakupan (Scope Boundary)
- **Sistem Monitoring NOC Mandiri:** Berorientasi pada kemudahan observasi, stabilitas operasional jangka panjang, dan kepadatan data tinggi (*high density*).
- **Halaman Dasbor Terisolasi (Proteksi Mutlak):** Berkas `server/templates/dashboard.html` **DILARANG KERAS disentuh atau dimodifikasi** tanpa instruksi eksplisit dan perencanaan khusus tersendiri.
- **Kemandirian Agen Klien:** Agen klien (`agent_pantau.py`) wajib mempertahankan prinsip *zero external dependency* (hanya pustaka standar Python 3.10+).
- **Standar Bahasa & Terminologi:** Seluruh judul commit, rilis GitHub, dokumentasi (`README.md`, `DEVELOPMENT.md`), dan antarmuka web wajib menggunakan **Bahasa Indonesia yang baku, terstruktur, dan lugas**, dengan tetap mempertahankan istilah teknis komputer/sysadmin standar dunia (CPU, RAM, S.M.A.R.T., NVMe, Daemon, Systemd, Root, Sudo, dll.).
- **Protokol Kecepatan & Efisiensi Eksekusi (Anti-Bekerja Berjam-jam):**
  - Tugas perbaikan bug atau penambahan fitur terfokus wajib diselesaikan secara terarah dan terencana (target 2–4 *turns*, durasi di bawah 5 menit).
  - Dilarang melakukan eksplorasi database/file secara berulang-ulang tanpa arah (*trial-and-error*).
  - Wajib memanfaatkan skrip otomasi [`tools/sop_release.py`](file:///home/bos/rj45/tools/sop_release.py) untuk seluruh alur rilis produksi agar proses build, restart, dan deployment selesai dalam hitungan detik.

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
- **Skala Ukuran Font & Spasi Rapat:**
  - Data pelengkap/sekunder/non-esensial menggunakan font kecil (`10px`–`11px`).
  - Nilai sel atau badge yang sudah memiliki indikator warna tegas (hijau, kuning, merah) menggunakan font ringkas (`9px`–`10px`) karena warna visual sudah langsung menyampaikan status kepada operator.
  - Padding sel rapat (3px–6px), tinggi baris ~30–34px, ukuran font badge proporsional 9.5px, hindari whitespace berlebihan.

---

## 5. Aturan Arsitektur Render (Dual-Render Synchronization)
- **Sinkronisasi Wajib Server-Side & Client-Side:**
  - Setiap tabel yang dirender awal oleh server (Jinja HTML) dan dirender ulang oleh klien (JavaScript via WebSocket, Polling, atau Filter) **wajib dimodifikasi secara sinkron dan identik**. Dilarang keras hanya mengubah salah satunya.

---

## 6. Protokol Baku Pengembangan UI/UX (Anti-Kebutaan Piksel & Multi-Theme Contrast)
- **Larangan Keras "Asal Lulus Sintaks" (*Anti-Blind Code Generation*):**
  - Kelulusan pengujian teknis (`py_compile`, `bash -n`, HTTP 200) **bukan bukti bahwa antarmuka selesai atau layak digunakan manusia**. Asisten dilarang menganggap tugas selesai hanya karena kode berjalan tanpa error teknis.
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
  - **Pengujian Kasus Ekstrem Visual:** Wajib menguji tampilan pada kondisi ekstrem (teks sangat panjang > 2000 karakter, kondisi data kosong/empty state, responsivitas layar sempit, serta keselarasan Dark Mode & Light Mode).

---

## 7. Kebijakan Khusus Proxmox HA & Proteksi Mesin
- VM atau LXC dengan `is_proxmox_ha = 1` dilarang dimatikan dari dalam via tombol *Power OFF*.
- Tombol *Power OFF* dinonaktifkan (`disabled`, kursor `not-allowed`) dan backend menolak request dengan pesan peringatan resmi.

---

## 8. Alur Kerja Wajib (Workflow) & Otomasi Rilis

### A. Sebelum & Saat Men-generate Kode
- Pertahankan prinsip *zero external dependency* pada agen klien.
- Hindari eksekusi shell tanpa sanitasi (`shell=False`, least-privilege).
- **Audit Menyeluruh (Anti-Pekerjaan Parsial):** Dilarang melakukan perbaikan sepotong (*local patch*). Asisten wajib melakukan pencarian global (`grep`) ke seluruh berkas proyek (`server/templates/`, `server/static/`) untuk memastikan aturan telah diterapkan konsisten pada semua halaman dan tab yang relevan sebelum pekerjaan dinyatakan selesai.

### B. Setelah Men-generate Kode (Wajib Otomatis Menggunakan Skrip Rilis)
Setiap kali menyelesaikan pekerjaan (bugfix/fitur baru/refactor):
**Wajib menggunakan skrip otomatisasi satu perintah [`tools/sop_release.py`](file:///home/bos/rj45/tools/sop_release.py)** agar seluruh rangkaian berikut selesai secara atomik dalam **15–30 detik**:
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
