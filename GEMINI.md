# Project Rules: Pantau Server Application

Berkas ini adalah spesifikasi teknis dan aturan baku permanen (*always-on project rules*) khusus bagi aplikasi **Pantau Server** (`/home/bos/pantau-server`). Untuk panduan ringkas operasional AI agent, baca [`AGENTS.md`](file:///home/bos/pantau-server/AGENTS.md). Seluruh ketentuan di bawah ini wajib dipatuhi secara ketat tanpa pengecualian.

---

## 1. Esensi Sistem Pantau Server & Batas Cakupan (Scope Boundary)
- **Sistem Monitoring NOC Mandiri:** Berorientasi pada kemudahan observasi, stabilitas operasional jangka panjang, dan kepadatan data tinggi (*high density*).
- **Halaman Dasbor Murni Pasif (Proteksi Mutlak):** Berkas `DashboardView.vue` adalah area **MURNI PASIF** untuk pemantauan makro, banner KPI 3-kartu (Total Servers, Active Incidents 5-strip, System Clock), dan tabel insiden pasif. Dilarang keras menambahkan kolom aksi ("Actions" / "Tindakan") atau tombol aksi (seperti tombol `View` atau mutasi) di halaman dasbor. Navigasi menuju rincian host bersifat pasif murni melalui klik baris data (`cursor-pointer`) dengan penunjuk chevron navigasi halus `>`, persis seperti perilaku unggul di aplikasi lama.
- **Jendela Kontrol Taktis Mengambang (Workspace Modal):** Seluruh aksi kontrol aktif dan investigasi per host (restart service, kill task, putus sesi SSH, audit port, firewall, cron) berada eksklusif di dalam modal mengambang `ServerWorkspaceModal.vue`.
- **Kemandirian Agen Klien:** Agen klien (`agent_pantau.py`) wajib mempertahankan prinsip *zero external dependency* (hanya pustaka standar Python 3.10+).
- **Standar Bahasa Antarmuka (English Default & i18n Reaktif):** Antarmuka web default menggunakan **Bahasa Inggris (`en`)** baku NOC/sysadmin (Overview, Incidents, Services, Tasks, Ports, Firewall, Total Servers, Active Incidents, System Clock, Fleet Inventory) dengan sakelar reaktif instan ke **Bahasa Indonesia (`id`)** (`[ 🌐 EN | ID ]`). Dilarang keras men-hardcode teks lokal di template komponen.
- **Prioritas Browser (Moli First):** Setiap pengujian tampilan web atau otomasi browser wajib memprioritaskan Moli (`moli fetch` / `moli-webfetch`). Gunakan Chrome DevTools hanya jika Moli gagal.
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
- **Standar Ergonomi Tombol & Tipologi 4-Tier (4-Tier Button Ergonomics Standard):**
  1. *Tier 1 (Ikon Saja + Tooltip Standar):* Khusus aksi universal yang sudah dipahami luas tanpa perlu membaca teks (minimize, maximize/restore, close, clear screen, sync/refresh, chevrons nav, download). Wajib menggunakan ikon SVG vektor tipis monokromatik. Dilarang menyematkan label teks panjang yang memboroskan ruang.
  2. *Tier 2 (Ikon + Label):* Khusus tab navigasi dan kontrol domain fungsional yang memerlukan kejelasan nama (`[ Maintenance Mode ]`, `[ Performance ]`, `[ Services & Ports ]`, `[ View ]` dengan ikon SVG Eye untuk membuka rincian aset). Dilarang keras menggunakan kata fiktif/dramatis seperti *Investigate* atau emoji petir.
  3. *Tier 3 (Ikon Saja + Tooltip Informatif):* Tombol aksi baris tabel atau kontrol padat di mana label disembunyikan demi efisiensi kepadatan data (*NOC Data Density*), namun wajib memiliki atribut `title="..."` informatif yang menyebutkan target objek secara presisi (contoh: SVG chart dengan tooltip `"Performance & Metrics"`, SVG terminal dengan tooltip `"Web Terminal"`, SVG sync dengan tooltip `"Probe Telemetry"`, SVG dots dengan tooltip `"More Actions"`).
  4. *Tier 4 (Ikon + Label + Tooltip Penjelasan):* Kontrol berkategori kritis atau berdampak sistemik tinggi (`Update OS`, `Upgrade OS`, `Reboot`, `Power Off`). Wajib memiliki label teks tegas dan tooltip informatif yang menjelaskan konsekuensi/rincian aksi.
- **Keseragaman Kontrol Jendela (Window Chrome Uniformity):**
  - Seluruh tombol kontrol pada bilah judul jendela konsol (termasuk *Pop-out Window*, *Clear Screen*, *Full Window*, *Fullscreen*, *Close*) **wajib seragam berupa tombol ikon SVG tanpa label teks horizontal**, dengan tooltip sebagai penjelas. Dilarang membuat tombol teks memanjang di dalam deretan tombol kontrol jendela atau menduplikasi teks yang sama persis antara label dan tooltip.
- **Larangan Mutlak Emoji Kartun (Zero-Emoji Mandate):**
  - Seluruh antarmuka Pantau Server wajib menggunakan **vektor SVG inline monokromatik/semantik** (stroke 1.5–2px, adaptif terhadap warna tema NOC) dan DILARANG KERAS menggunakan karakter emoji bergambar bawaan OS.

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
- **Eksekusi Langsung:** Setiap kali operator mengetikkan perintah `/learn`, hal tersebut merupakan **instruksi aturan mutlak** yang wajib langsung dibukukan, diterapkan, dan dikunci secara permanen ke dalam `GEMINI.md`.
- **Larangan Meminta Konfirmasi Ulang:** Dilarang keras menunda eksekusi, bersikap pasif, atau meminta konfirmasi/persetujuan berbelit-belit kepada operator saat `/learn` telah diberikan. Catat dan terapkan seketika.

---

## 16. Kemurnian Konseptual & Isolasi Data Mutlak (Clean Slate Architecture)
- **Spesifikasi Standar Operasional NOC:** Seluruh alur kerja (*workflow*), tata letak kartu, navigasi interaksi, hierarki telemetri NOC, dan jendela taktis mengambang diwujudkan secara utuh sebagai standar baku orisinal Pantau Server.
- **Isolasi Mutlak (Clean Slate Database):** Sistem beroperasi dengan skema dan basis data mandiri murni (`pantau_server_db`). Dilarang keras menyalin, mengaitkan, atau menduplikasi struktur tidak konsisten atau data historis kotor dari lingkungan pengujian apa pun.

---

## 17. Standar Mutlak Web Terminal: Mandat Global Multi-Tab Terminal Dock (xterm.js)
- **Kepatuhan Konsep Aplikasi Lama:** Web Terminal wajib mengadopsi 100% konsep dan arsitektur UX unggul dari aplikasi pantau lama berupa **Global Multi-Tab Terminal Dock** berbasis `xterm.js` dan `xterm-addon-fit.js`.
- **Fitur Utama Dock:**
  1. *Multi-Tab Fleet Management:* Pengguna dapat membuka banyak tab terminal lintas server secara simultan dalam satu jendela dock.
  2. *Tab Switcher & Status Dot:* Setiap tab menampilkan nama host server, indikator status koneksi (dot hijau = terhubung, dot merah = terputus), serta tombol tutup tab `✕`.
  3. *Tombol Tambah Tab (`+`):* Dilengkapi menu dropdown pencarian host untuk membuka koneksi terminal ke server armada lain secara langsung.
  4. *Kontrol Jendela Standar:* Mendukung minimize ke rak dock bawah (dengan koneksi *keep-alive* tidak terputus), maximize/fullscreen, dan pop-out ke jendela terpisah.
- **Larangan Keras Terminal Model Baru / Fake Input Box:**
  - Dilarang keras membuat terminal tiruan baru berupa kotak teks `<input>` satu baris dengan tombol submit. Terminal wajib berupa emulator PTY sejati berbasis `xterm.js` yang mendukung interaksi keyboard langsung (TAB completion, Ctrl+C, Ctrl+D, nano/vim, htop).

---

## 18. Prinsip Rekayasa Rekanara (Ponytail, Anti-Bloat & Verifikasi Mandiri)
- **Prinsip Ponytail (Lazy Senior Dev Mode — Anti-Bloat):**
  - Selesaikan setiap tugas dengan **diff terkecil yang menuntaskan masalah secara menyeluruh**.
  - Dilarang keras membuat abstraksi prematur, kelas wrapper spekulatif, atau opsi konfigurasi yang tidak diminta.
  - Gunakan pustaka standar Python 3.10+ atau utilitas bawaan FastAPI/Vue yang sudah ada sebelum mengusulkan dependensi baru.
  - Jika membuat simplifikasi yang disengaja demi kecepatan dengan upgrade path yang jelas, beri komentar bertanda:
    `# ponytail: <alasan simplifikasi>, <kapan harus di-upgrade>` atau `// ponytail: ...`
- **Pencegahan Kesalahan Runtime (Anti-Hallucination & Root Cause):**
  - **SQLAlchemy Session Hygiene:** Wajib mencegah `DetachedInstanceError`. Jangan biarkan objek ORM diakses di luar cakupan sesi database yang masih terbuka; gunakan *eager loading* atau petakan langsung ke skema Pydantic.
  - **Subproses & Sesi PTY:** Wajib memastikan alur pembersihan (*graceful cleanup*) proses child/PTY saat koneksi WebSocket terminal terputus agar tidak memicu proses *zombie*.
  - Selidiki *root cause* dan periksa seluruh *caller* fungsi yang disentuh sebelum mengubah kode. Dilarang melakukan *trial-and-error* acak.
- **Mandat Verifikasi Mandiri Sebelum Melapor Selesai:**
  - Dilarang mengklaim tugas selesai hanya karena kode telah ditulis.
  - Wajib membuktikan validitas sintaksis backend (`python3 -m py_compile server/**/*.py`) dan kelulusan *build* frontend (`npm run build --prefix frontend`).

---

## 19. Prinsip Supremasi Konsep, Workflow & UX Aplikasi Lama (~/rj45)
- **Kebenaran Mutlak Workflow Lama:** Konsep dasar, hierarki fitur, alur kerja operasional (*workflow*), dan pengalaman pengguna (*UX*) dari aplikasi pantau lama (`/home/bos/rj45`) adalah **konsep yang BENAR dan sudah matang**.
- **Hakikat Proyek Pantau Server Baru (~/pantau-server):**
  - Aplikasi baru ini adalah **perombakan dan penyempurnaan dari sisi UI/Frontend saja** (mengganti monolitik Jinja HTML/JS/CSS yang kacau di aplikasi lama dengan SPA Vue 3 modern, arsitektur modular terstruktur `<250` baris per file, dan komponen bersih) **ditambah perbaikan serta penguatan backend/layanan yang diperlukan**.
  - **Dilarang Keras Mengarang Alur Kerja Baru:** Dilarang keras mengarang model interaksi asing, mengganti alur kontrol yang sudah terbukti di aplikasi lama, atau membuang workflow yang sudah matang demi alasan spekulatif.
  - Setiap kali merancang atau membangun komponen antarmuka (Dasbor Pasif, Tabel Armada, Jendela Rincian Aset, Tab Metrik, Tab Services/Ports, Tab Tasks/Proses, Tab Firewall/Cron, Web Terminal Dock, Remote File Manager, Tombol Power/Reboot/Maintenance), **wajib selalu mengacu 100% pada alur kerja dan UX aplikasi lama di `/home/bos/rj45` sebagai sumber kebenaran visual dan fungsional**.

---

## 20. Glosarium Baku, Taksonomi Insiden & Hierarki Pengguna (Definisi Resmi)
Seluruh penamaan modul, variabel, teks antarmuka, dokumentasi, dan logika sistem wajib tunduk pada definisi resmi berikut:
1. **Identitas Sistem & Komponen:**
   - **`pantau-server`**: Nama resmi aplikasi platform pusat kendali operasional NOC (*backend* FastAPI, *frontend* Vue 3 SPA, basis data, dan orkestrasi armada).
   - **`pantau-agent`**: Nama resmi agen telemetri yang terpasang pada node/aset klien Linux (`agent_pantau.py`).
2. **Terminologi Kejadian Sistem:**
   - **`insiden` (`incident`)**: Masalah, gangguan, anomali, kejadian, atau peristiwa yang terdeteksi pada sistem/aset.
   - **`insiden aktif` (`active incident`)**: Masalah/gangguan/anomali/kejadian/peristiwa yang sedang terjadi dan masih aktif (anomali fisik sedang berlangsung). **Dilarang keras menggunakan istilah "insiden terbuka"**.
3. **Taksonomi & Visualisasi Tingkat Keparahan (`severity`):**
   Tingkat, ukuran, atau level keparahan sebuah insiden/kejadian diatur sebagai berikut:
   - **`info` (Biru / Blue):** Tingkat paling rendah dalam sebuah insiden dan tidak dikategorikan sebagai ancaman. Bersifat pemberitahuan insiden normal namun sangat layak dan penting disampaikan ke operator (contoh: informasi paket pembaruan OS / *package update* yang tersedia).
   - **`warning` / Peringatan (Kuning / Yellow):** Insiden yang berpotensi menjadi sebuah ancaman atau sudah menjadi gangguan, namun **tidak menyebabkan layanan utama berhenti beroperasi** (contoh: sesi remote SSH aktif dari pengguna legal, penggunaan memori/disk yang mendekati batas awal).
   - **`critical` / Gawat atau Kritis (Oranye Pekat / Deep Orange):** Insiden yang menyebabkan layanan utama menjadi terganggu atau berhenti beroperasi (contoh: service Nginx mati, database MySQL down, percobaan login SSH brute-force / akses dari user ilegal).
   - **`danger` / Bahaya (Merah / Red):** Insiden besar yang menyebabkan **lumpuhnya sebuah sistem utama** (contoh: server mati / offline tidak melapor, filesystem beralih ke *read-only*, kernel panic, storage I/O physical error).
4. **Hierarki & Otoritas Akun Pengguna (RBAC Structure):**
   - **`master-admin`**: Akun administrator utama (*root*), satu-satunya pemegang otoritas absolut sistem. Keberadaannya terlindungi mutlak: tidak dapat dihapus, tidak dapat di-lock, dan keberadaannya diisolasi dari penglihatan operator biasa.
   - **`operator`**: Akun pengguna dan pengelola harian sistem aplikasi:
     - **`operator utama`**: Akun operasional tingkat tinggi yang dibuat langsung oleh `master-admin` dengan peran luas (memiliki hak delegasi sudo penuh) untuk mengelola armada dan pengguna harian, namun **dilarang keras dan tidak bisa menggantikan atau menghapus akun `master-admin`**.
     - **`operator pembantu`**: Akun operasional yang dibuat oleh `operator utama` dengan hak akses terbatas (*least privilege*) sesuai matriks tugas dan fungsi spesifiknya (contoh: hanya melihat metrik, atau hanya mengelola service tertentu).
   - **`tamu` (`guest` / `viewer`)**: Akun pengunjung dengan peran sebagai peninjau murni (*read-only*) yang hanya dapat melihat metrik/status tanpa memiliki hak akses mutasi, kontrol daya, eksekusi terminal, atau perubahan konfigurasi apa pun.




