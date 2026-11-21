# Engineering Lessons & Self-Improvement Log

Dokumen ini mencatat setiap pembelajaran dari koreksi operator dan temuan teknis agar kesalahan yang sama tidak pernah berulang (`[CDiP]`).

---

## Lesson 1: Hindari Pustaka Abstraksi Usang (Native Over Broken Wrapper)
- **Konteks:** `passlib.context.CryptContext` memicu `AttributeError: module 'bcrypt' has no attribute '__about__'` pada `bcrypt >= 4.1.0`, menyebabkan kegagalan otentikasi login 401.
- **Akar Masalah:** `passlib` tidak lagi dipelihara secara aktif dan bergantung pada atribut internal versi `bcrypt` lama.
- **Aturan Pencegahan `[DM, SFT]`:** Gunakan langsung pustaka native standar industri (`bcrypt.checkpw` dan `bcrypt.hashpw`) tanpa wrapper usang.

---

## Lesson 2: Mandat Kepemilikan Teknis Penuh (Full Technical Ownership)
- **Konteks:** Menyerahkan kembali pilihan arsitektur kepada operator atau bersikap pasif.
- **Akar Masalah:** Pelanggaran peran sebagai Principal Software Engineer. Operator adalah penguji pengalaman (*experiential validator*), bukan pemrogram.
- **Aturan Pencegahan `[SF, PCF]`:** Asisten wajib menganalisis akar masalah, menetapkan arsitektur terbaik secara mandiri, mengeksekusi end-to-end, dan menyajikan hasil siap pakai serta roadmap yang transparan.

---

## Lesson 3: Disiplin Penomoran Versi (Clean Baseline SemVer)
- **Konteks:** Menyematkan label `v5.0` pada proyek yang baru dibangun ulang dari nol.
- **Akar Masalah:** Ketidaksesuaian persepsi siklus rilis. Proyek yang dibangun ulang harus mencerminkan baseline yang jujur dan bertahap.
- **Aturan Pencegahan `[ISA]`:** Bangun ulang fondasi dimulai dari `v0.1.0` (arsitektur baseline baru) sebelum naik secara bertahap seiring kelengkapan fitur.

---

## Lesson 4: Standar Bahasa Antarmuka & Komunikasi Operator
- **Konteks:** Asisten sempat keliru beralih ke bahasa Inggris dalam merespons operator.
- **Akar Masalah:** Mengabaikan aturan komunikasi pengguna.
- **Aturan Pencegahan `[RAT]`:** Komunikasi dengan operator wajib 100% menggunakan Bahasa Indonesia yang baku, terstruktur, lugas, dan rendah hati, dengan tetap mempertahankan istilah teknis komputer/sysadmin standar dunia (CPU, RAM, Kernel, Daemon, Root, Sudo, SSH, TTY, dll.).

---

## Lesson 5: Paradigma Interaksi Inspeksi Server (Floating Workspace over Full-Page Reload)
- **Konteks:** Mengklik baris server sempat mengalihkan tampilan ke halaman baru (`activeTab = 'detail'`), memutus sesi terminal dan menghilangkan konteks armada.
- **Akar Masalah:** Menerapkan navigasi halaman penuh seperti aplikasi web biasa, bukan standar NOC.
- **Aturan Pencegahan `[SF, CA]`:** Terapkan standar interaksi jendela mengambang (`.modal-workspace`). Matriks armada tetap terlihat di latar belakang, server dibuka di jendela modal fleksibel, lengkap dengan navigasi antar-host langsung (`[` dan `]`), tombol maksimalkan/layar penuh (`⛶`), serta kemampuan minimalkan ke bilah rak bawah.

---

## Lesson 6: Keselarasan Blueprint Dasbor Pasif & Larangan Kartu Spekulatif
- **Konteks:** Menambahkan kartu fiktif/spekulatif "HUMAN SSH INTERCEPTS" mandiri di dasbor tanpa server yang jelas.
- **Akar Masalah:** Menyimpang dari spesifikasi baku dasbor pasif dan menciptakan fitur spekulatif tanpa arsitektur data yang jelas.
- **Aturan Pencegahan `[PEC, SF]`:** Dasbor adalah area **MURNI PASIF** untuk observasi makro dan triase insiden. Banner atas wajib setia pada proporsi asimetris baku 3 kartu: Card 1 Total Server (`minmax(210px, 240px)`), Card 2 Insiden Aktif dengan 5 Tile Keparahan Zabbix (`1fr`), Card 3 Waktu Sistem Presisi (`minmax(280px, 320px)`). Sesi SSH disajikan terstruktur sebagai tiket insiden biasa di tabel insiden atau di jendela taktis host.

---

## Lesson 7: Standarisasi Tipografi NOC & Larangan Keras Font Mikroskopis
- **Konteks:** Teks antarmuka tampak sangat kecil/buram pada resolusi standar (skala 100%), memaksa pengguna memicingkan mata atau melakukan pembesaran (zoom).
- **Akar Masalah:** Penggunaan kelas Tailwind mikroskopis (`text-[9px]`, `text-[10px]`, `text-[11px]`) dan memaksakan font monospace (`font-mono`) pada seluruh badan teks antarmuka. Monospace memiliki glif sempit dan tipis yang sulit dibaca bila ukurannya kecil.
- **Aturan Pencegahan `[RP, Anti-User QA]`:** Seluruh antarmuka wajib terbaca jelas, tajam, dan proporsional pada skala 100% (standar keterbacaan NOC skala 100%):
  1. Base font antarmuka menggunakan Sans-Serif modern (`Inter`, system UI: `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif`).
  2. Font monospace (`font-mono`) **HANYA** digunakan untuk metrik telemetri, IP address, port, kode status, atau terminal shell.
  3. Skala tipografi baku: Judul kartu/seksi 15px–16px (`text-base`), isi sel tabel 13.5px–14px (`text-sm`), label kolom / header tabel 12px (`text-xs font-bold uppercase`), badge status 12px (`text-xs font-bold`), dan metrik angka KPI 24px–28px (`text-2xl`–`text-3xl font-extrabold`). Dilarang keras menggunakan ukuran font di bawah 12px.
  4. Padding kartu dan sel tabel dirancang proporsional dan nyaman (`py-2.5 px-4` per sel; `p-3 px-4` per kartu), tidak berdesak-desakan.

---

## Lesson 8: Standar Bahasa Antarmuka (English Default dengan i18n Reaktif)
- **Konteks:** Antarmuka web menampilkan teks bahasa Indonesia secara default dan teks bercampur bahasa Indonesia di beberapa komponen modal/tabel ("kan bahasa inggris, kenapa ada bahasa indonesia").
- **Akar Masalah:** String antarmuka sempat di-hardcode dalam bahasa Indonesia di beberapa komponen Vue (`App.vue`, `LoginModal.vue`, `AuditView.vue`, `SettingsView.vue`), alih-alih menggunakan kamus translasi.
- **Aturan Pencegahan `[RP, I18N, DM]`:**
  1. Standar default antarmuka NOC adalah **Bahasa Inggris** (`en`) agar terminologi teknis sysadmin (Overview, Incidents, Services, Tasks, Ports, Firewall, Automation, Users & SSH, Total Servers, Active Incidents, System Clock, Fleet Inventory) terasa natural, bersih, dan presisi.
  2. Disediakan tombol toggle instan multi-bahasa (`[ 🌐 EN | ID ]`) di Navbar yang reaktif seketika tanpa reload dan tersimpan di `localStorage`.
  3. Dilarang keras men-hardcode string teks langsung di template komponen Vue. Seluruh teks antarmuka, header kolom, tombol aksi, tooltip, pesan peringatan, dan dialog konfirmasi wajib dipanggil melalui fungsi translasi `t('key')` dengan sumber kamus terpusat di `frontend/src/i18n/`.

---

## Lesson 9: Isolasi Total dari Kontaminasi Data Warisan (Clean Slate Architecture)
- **Konteks:** Menghubungkan langsung aplikasi baru ke basis data warisan atau menduplikasi database yang tidak terstandarisasi.
- **Akar Masalah:** Terjebak dalam ilusi "memanfaatkan data eksisting", padahal skema warisan sarat dengan anomali, kolom terpecah tanpa relasi yang bersih, dan artefak peninggalan masa lalu yang mengotori arsitektur baru.
- **Aturan Pencegahan `[SF, PCF, Absolute Data Integrity]`:**
  1. **Spesifikasi Murni, Bukan Data Warisan:** Aplikasi baru beroperasi murni berdasarkan spesifikasi domain, alur kerja (*workflow*), dan visual UI/UX tanpa membawa data kotor masa lalu.
  2. **Dilarang Keras Menduplikasi atau Mengaitkan Data Warisan:** Jangan pernah menyalin atau menghubungkan langsung database warisan ke aplikasi baru.
  3. **Basis Data Mandiri & Bersih (*Clean Slate Database*):** Sistem baru wajib memiliki basis data mandiri yang bersih (`pantau_server_db` dengan skema terisolasi), di mana setiap tabel, relasi, tipe data, dan indeks didesain murni sesuai *Clean Architecture*, tanpa membawa kompromi peninggalan masa lalu.
  4. **Validasi Melalui Kontrak Data Murni:** Tahap validasi konsep UI dan alur sistem dilakukan menggunakan data bersih yang terstruktur presisi sesuai kontrak API baru, sehingga kelemahan data lama tidak mengotori atau membingungkan pengujian sistem baru.

---

## Lesson 10: Anti-Jalan Praktis & Standar Rekayasa Produksi Sejati
- **Konteks:** Mengusulkan SQLite semata-mata karena alasan "mudah berkas tunggal dan zero-setup" untuk sistem NOC.
- **Akar Masalah:** Kemalasan berpikir (*lazy engineering shortcut*) yang mengabaikan beban kerja riil, konkurensi tulis simultan dari banyak klien, dan integritas data 24/7/365.
- **Aturan Pencegahan `[SF, PGE, Systems Thinking]`:**
  1. Seorang Principal Software Engineer sejati dilarang keras memilih jalan pintas kompromis yang rapuh.
  2. Selalu gunakan arsitektur standar produksi sejati (MySQL/MariaDB InnoDB dengan connection pooling dan row-level locking) untuk menangani semburan telemetri armada secara simultan.

---

## Lesson 11: Larangan Spekulasi Nomenklatur "v2" & Disiplin SemVer v0.1.0
- **Konteks:** Menamai database atau berasumsi sebutan `pantau_v2_db` / `v2` padahal aplikasi berstatus baseline `v0.1.0`.
- **Akar Masalah:** Spekulasi liar dan halusinasi penamaan versi yang tidak bersumber dari fakta rilis resmi.
- **Aturan Pencegahan `[ISA, SSoT]`:**
  1. Aplikasi ini adalah **Pantau Server** yang sedang dibangun dari baseline awal **`v0.1.0`**.
  2. DILARANG KERAS melabeli, menamai variabel, database, branch, atau berkas dengan istilah "v2" dalam bentuk apa pun.

---

## Lesson 12: Eksekusi Instan Mandat `/learn` Tanpa Konfirmasi
- **Konteks:** Mengeluarkan usulan proposal `/learn` dan meminta konfirmasi persetujuan dari operator ("mohon tinjauan Anda...").
- **Akar Masalah:** Sikap pasif birokratis yang membebani operator dengan prosedur konfirmasi berbelit-belit.
- **Aturan Pencegahan `[CDiP, FTO]`:**
  1. Perintah `/learn` dari operator adalah instruksi mutlak.
  2. Begitu `/learn` diberikan, asisten wajib langsung membukukan, menerapkan, dan mengunci aturan tersebut ke berkas tata kelola sistem seketika tanpa meminta persetujuan ulang.

---

## Lesson 13: Larangan Keras Teks Angka Statis & Klaim Fiktif (Dynamic State Integrity)
- **Konteks:** Dasbor menampilkan teks *"All 10 fleet servers are operating normally"* padahal aplikasi masih kosong (0 server).
- **Akar Masalah:** Men-hardcode string statis yang mengasumsikan jumlah server tertentu ke dalam kamus i18n (`dash_incidents_empty`), melanggar prinsip *Zero-Fake Data* dan *Dynamic State*.
- **Aturan Pencegahan `[Absolute Data Integrity, Universal Zero-Hardcode Standard]`:**
  1. Dilarang keras men-hardcode angka jumlah host atau klaim status statis di kamus teks maupun template.
  2. Seluruh status wajib dihitung murni secara dinamis dari `servers.length`:
     - Jika 0: Tampilkan secara jujur *"No fleet servers connected yet"*.
     - Jika > 0: Gunakan parameter dinamis `{count: servers.length}` sehingga angka mencerminkan fakta riil.

---

## Lesson 14: Seleksi Teks Universal & Larangan Over-Engineering Tooltip (Standard Selectable Tooltip Engine)
- **Konteks:** Sempat membuat tooltip yang berlebihan (*over-engineered*) berupa jendela/kartu mengambang dengan banner header "INFORMASI", tombol salin, dan footer petunjuk shortcut, yang merusak estetika dan mengotori antarmuka. Selain itu, kelas `select-none` sempat diletakkan di root container (`App.vue`) sehingga teks antarmuka tidak bisa disalin.
- **Akar Masalah:**
  1. *Over-engineering* dan kegagalan memahami ergonomi antarmuka sysadmin/NOC: Tooltip profesional bukanlah jendela modal/kartu melayang dengan tombol, melainkan bubble tooltip ringkas dan presisi yang menempel langsung pada atribut standar HTML (`title` atau `data-tooltip`).
  2. Penempatan kelas CSS `select-none` di root aplikasi mengunci seleksi kursor pada data fakta fisik.
- **Aturan Pencegahan `[SF, Ergonomics, Anti-Overengineering]`:**
  1. **Larangan Mutlak Widget Modal/Tombol untuk Tooltip:** Dilarang keras membuat komponen kartu mengambang, banner kategori, atau menyematkan tombol salin di dalam tooltip. Tooltip harus tetap berupa bubble tooltip standar yang bersih, ringkas, dan tidak mengganggu.
  2. **Mesin Tooltip Global Berbasis Atribut Standar:** Gunakan satu mesin listener DOM global (`initTooltipEngine`) yang secara otomatis mengintersepsi atribut native HTML `title="..."` atau `data-tooltip="..."` di seluruh aplikasi tanpa memerlukan komponen pembungkus tambahan.
  3. **Kemampuan Seleksi Kursor Alami (Hover-to-Select):** Tooltip memiliki toleransi jeda hover (160ms show / 180ms hide) dan `pointer-events: auto; user-select: text !important;`, sehingga operator dapat secara natural menggerakkan kursor ke dalam tooltip untuk menyorot (*highlight*) dan menyalin (*copy*) teks secara langsung.
  4. **Universal Text Copyability:** Seluruh teks antarmuka (IP, port, log, PID, telemetri, perintah) wajib dapat disorot dan disalin secara bebas (`user-select: text`). Kelas `select-none` HANYA diizinkan untuk tombol kontrol klik murni atau bilah seret (*drag handle*).

---

## Lesson 15: Mandat Estetika Taktis Orisinal (Tactical Cyber Command Room vs Replika Visual Usang)
- **Konteks:** Meniru secara mentah (*plek ketiplek*) struktur HTML/CSS tabel dan tombol dari aplikasi rujukan lama, sehingga antarmuka tampak generik dan membosankan, alih-alih mewujudkan atmosfer *Tactical Cyber Command Room / Nuansa Mata-Mata* yang telah diamanatkan sejak awal perancangan.
- **Akar Masalah:** Sikap pasif dalam perancangan visual (*design passivity*) dan kerancuan batas adopsi: Yang diadopsi dari sistem acuan murni hanyalah **alur kerja operasional (*workflow*)**, kepadatan telemetri NOC, pasif dasbor, dan jendela kontrol terisolasi. Menyalin tampilan visual jadulnya adalah sebuah kemunduran rekayasa.
- **Aturan Pencegahan `[SF, Lead UI/UX, FTO]`:**
  1. **Kepemilikan Penuh Perancangan Visual (Lead UI/UX Ownership):** Asisten berdiri sebagai Senior Software Engineer & Lead UI/UX Designer sejati yang bertanggung jawab penuh merancang dan mengembangkan antarmuka sistem dari awal hingga akhir dengan estetika berkelas, modern, dan presisi.
  2. **Penegakan Estetika Tactical Cyber Operations Deck:**
     - Kanvas *Obsidian Slate* (`#050811`, `#090e1a`) dengan aksen mikro-grid HUD dan aksen sudut laser (*HUD corner brackets*).
     - Indikator radar berpendar (*pulsing live radar beacons*) untuk node armada dan status anomali.
     - Pengukur telemetri taktis (*cyber progress bars*) dengan gradien warna semantik (cyan, emerald, amber, crimson) untuk CPU, RAM, dan Storage.
     - Monospace terstruktur (*JetBrains Mono / tabular figures*) untuk seluruh koordinat IP, port, PID, latensi, dan stempel waktu.
     - Navigasi dan tindakan berbasis konsol intelijen (`[ 01 // DASHBOARD ]`, `[ ⚡ INVESTIGATE ]`).
  3. **Larangan Keras Memindahkan Template Visual Usang:** Jangan pernah lagi menyalin layout HTML/CSS usang secara mentah dari aplikasi rujukan. Selalu rancang antarmuka orisinal yang segar, kokoh, dan ergonomis sesuai standar *Tactical Cyber Command Room*.

---

## Lesson 17: Hierarki Layout Jendela Kontrol Taktis, Penempatan Window Chrome, dan Pemisahan Konsol Khusus (Terminal & File Manager)
- **Konteks:** Kontrol jendela (minimize, maximize, close) dan bilah switcher armada terbungkus (*flex-wrap*) ke baris kedua di sebelah kiri, serta adanya duplikasi tombol Terminal & File Manager pada bilah tab horizontal biasa.
- **Akar Masalah:**
  1. Menggabungkan informasi identitas host, tombol aksi hero, dan kontrol jendela ke dalam kontainer flexbox tunggal yang mengizinkan *flex-wrap*, sehingga elemen kontrol jendela terdorong ke posisi yang aneh saat lebar layar menyempit.
  2. Menempatkan konsol interaktif khusus (Terminal dan File Manager) sebagai sub-tab telemetri horizontal biasa, alih-alih memperlakukannya sebagai jendela kerja mengambang mandiri (*floating console window*).
- **Aturan Pencegahan `[RP, Anti-User QA, Systems Thinking]`:**
  1. **Pemisahan Tegas Tiga Layer Header Modal:**
     - *Baris 1 (Window Chrome & Fleet Navigator):* Memuat identitas target dan telemetri di kiri, Switcher Armada terpusat dengan dropdown ber-z-index tinggi, dan tombol kontrol jendela (`—`, `⛶`, `✕`) **wajib terkunci permanen di sudut kanan atas jendela** tanpa terkena *wrap*.
     - *Baris 2 (Dedicated Command Deck):* Bilah khusus berisi tombol tindakan hero (Terminal, File Manager, Mode Pemeliharaan di kiri; Update, Upgrade, Reboot, Power Off di kanan).
     - *Baris 3 (Tactical Tabbar):* Murni navigasi 11 sub-konsol telemetri fisik; **dilarang menyematkan tombol Terminal & File Manager di bilah tab horizontal**.
  2. **Konsol Khusus Terminal & File Manager Sebagai Jendela Mengambang Mandiri:**
     - Terminal dan File Manager dibuka dalam jendela mengambang terpisah (*floating modal*) yang dilengkapi kontrol lengkap: *Clear Screen*, *Full Window*, *Fullscreen*, *Buka Jendela Terpisah / Pop-out Window* (ala Proxmox/noVNC), dan *Close*.
  3. **Inspeksi Visual Mandiri Berbasis Alat Otomasi (Anti-Kebutaan Piksel):**
     - Wajib menggunakan alat uji visual otomatis berbasis peramban (`tools/capture_ui_suite.js` via headless Chrome) untuk mengambil dan memverifikasi tangkapan layar antarmuka nyata sebelum menyatakan pekerjaan selesai kepada operator.

---

## Lesson 18: Ergonomi Tombol, Tipologi Ikonografi, Label, dan Tooltip Presisi (4-Tier Button Ergonomics Standard)
- **Konteks:** Inkonsistensi penggunaan tombol di berbagai seksi antarmuka: sebagian tombol menggunakan label teks panjang yang memboroskan ruang pada fungsi universal (seperti minimize, maximize, close, full window), sementara aksi spesifik pada baris tabel tidak memiliki tooltip informatif mengenai objek target yang akan dieksekusi.
- **Akar Masalah:** Tidak adanya taksonomi hierarki tombol yang baku untuk membedakan kapan sebuah tombol cukup berupa ikon saja, kapan wajib memiliki label, kapan memerlukan tooltip ringkas, dan kapan wajib memiliki label + tooltip penjelasan mendalam.
- **Aturan Pencegahan `[SF, Ergonomics, NOC Data Density]`:**
  Seluruh komponen antarmuka wajib menerapkan **Taksonomi Tombol 4-Tier**:
  1. **Tier 1: Tombol + Ikon Saja (Universal Known Actions):**
     - Untuk fungsi aksi yang sudah dikenal secara universal dan intuitif di seluruh dunia komputer/web.
     - Contoh: Minimize, Maximize/Restore, Close, Sync/Refresh, Clear Screen, Navigasi panah, Download.
     - Menggunakan tooltip hover standar (`title="..."`). Dilarang menambahkan label teks yang memboroskan ruang horizontal.
  2. **Tier 2: Tombol + Ikon + Label (Domain Functional Navigation):**
     - Untuk tombol aksi atau tab navigasi yang bukan merupakan fungsi umum komputer biasa, sehingga label teks diperlukan untuk memperjelas konteks domain.
     - Contoh: Sub-tabs fungsional (Performance, Incidents, Services & Ports), tombol switch mode (Table / Grid), tombol aksi pembuka rincian aset (`View` dengan ikon SVG Eye).
  3. **Tier 3: Tombol + Ikon Saja + Tooltip Informatif (Contextual Compact Actions):**
     - Tombol aksi dengan ikon umum namun dieksekusi terhadap objek target spesifik di ruang sempit (seperti baris tabel atau toolbar padat) untuk menghemat ruang kolom, TETAPI wajib dilengkapi tooltip informatif yang menyebutkan target aksi secara presisi.
     - Contoh: Tombol shortcut metrik (SVG chart + tooltip: `"Performance & Metrics"`), shortcut terminal (SVG terminal + tooltip: `"Web Terminal"`), tombol probe (SVG sync + tooltip: `"Probe Telemetry"`), tombol menu more (SVG dots + tooltip: `"More Actions"`).
  4. **Tier 4: Tombol + Ikon + Label + Tooltip Informatif (Critical / System Impact Actions):**
     - Tombol operasional yang memiliki dampak nyata terhadap stabilitas sistem, alur kerja multi-step, atau risiko operasional.
     - Wajib memiliki label teks yang tegas agar operator tidak salah tekan, PLUS tooltip informatif yang merinci fungsi, efek samping, atau informasi prasyarat secara singkat dan padat.
     - Contoh:
       - `Update OS` (tooltip: "Update operating system package index (apt update)")
       - `Upgrade OS` (tooltip: "Upgrade available OS packages (apt upgrade)")
       - `Reboot` (tooltip: "Reboot host operating system")
       - `Power Off` (tooltip: "Power off host machine (Shutdown)")
       - `Maintenance Mode` (tooltip: "Configure maintenance mode for this host")

---

## Lesson 19: Eliminasi Total Emoji Kartun, Standardisasi Ikon Vektor SVG Halus, dan Larangan Keras Label Berlebih / Fiktif (Investigate -> View & Pop-out Window Uniformity)
- **Konteks:**
  1. Header jendela Web Terminal & File Manager menampilkan tombol `[ ↗ Pop-out Window ]` yang memanjang sendirian di antara deretan tombol ikon jendela lainnya, dengan teks tombol yang sama persis dengan isi tooltip (`Pop-out Window` di atas `Pop-out Window`), sehingga cacat ergonomi dan redundan.
  2. Tombol baris armada dan dasbor diberi label melodramatis `INVESTIGATE` dengan emoji petir `⚡`, padahal fungsinya murni untuk membuka rincian aset (`View`).
  3. Masih terdapat emoji kartun berwarna bawaan sistem operasi yang mencolok dan merusak atmosfer profesional *Tactical Cyber Command Room*.
- **Akar Masalah:**
  1. Kurangnya rasa kepekaan estetika dan ergonomi: mencampur tombol teks memanjang di dalam deretan tombol kontrol jendela yang semestinya seragam berupa ikon persegi.
  2. Istilah dramatisasi fiktif yang tidak tepat konteks (*Investigate* alih-alih *View*).
  3. Penggunaan karakter emoji bawaan OS alih-alih vektor SVG tipis monokromatik.
- **Aturan Pencegahan `[Lead UI/UX, SF, NOC Data Density, Zero-Fictitious]`:**
  1. **Aksi Rincian Aset Bernama "View" (Bukan "Investigate"):** Seluruh tombol pembuka jendela modal rincian aset di dasbor dan tabel armada menggunakan label baku **"View"** dengan ikon SVG mata (*Eye*), bukan "Investigate" atau emoji petir.
  2. **Keseragaman Tombol Kontrol Jendela (Icon-Only + Tooltip As Label):** Seluruh tombol pada bilah kontrol jendela (termasuk *Pop-out*, *Clear Screen*, *Full Window*, *Fullscreen*, *Close*) **wajib seragam berupa tombol ikon SVG tanpa label teks horizontal**, di mana *tooltip* (`title="..."`) berfungsi sebagai label penjelas. Dilarang menduplikasi teks label yang sama persis dengan isi tooltip.
  3. **Larangan Mutlak Emoji Kartun (Zero-Emoji Mandate):** Seluruh elemen UI wajib menggunakan **vektor SVG inline monokromatik/semantik** (stroke 1.5–2px, adaptif terhadap warna tema NOC) dan DILARANG KERAS menggunakan karakter emoji bergambar.





