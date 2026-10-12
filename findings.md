# Findings — Indonesia Economic Dashboard

Catatan riset & temuan teknis. Tulis setelah setiap discovery.

---

## 2026-10-10 — PRD Review (ketua_agen)

**Ringkasan PRD v1.1:**

- 3 indikator: PDB Growth, Inflasi YoY, Neraca Perdagangan
- Rentang data: 5 tahun terakhir
- Sumber utama: World Bank API (gratis, tanpa API key)
- Auto-update: APScheduler, interval 6–12 jam
- Penyimpanan: SQLite lokal
- Chart: Plotly (disarankan PRD)
- Download CSV untuk keperluan akademik

**World Bank API — indikator kode (dari PRD §6):**

| Indikator | Kode |
|-----------|------|
| PDB Growth | `NY.GDP.MKTP.KD.ZG` |
| Inflasi | `FP.CPI.TOTL.ZG` |
| Neraca Perdagangan | belum dipatok — perlu ditentukan |

**Format endpoint World Bank (untuk diverifikasi):**
`https://api.worldbank.org/v2/country/IDN/indicator/<KODE>?format=json&per_page=100`

- Tanpa API key, rate limit longgar
- Response: array `[metadata, data[]]`, tiap entri punya `date`, `value`
- Nilai bisa `null` untuk tahun yang belum rilis — perlu handling

**Yang belum diverifikasi:** apakah kode indikator benar dan mengembalikan data
terbaru untuk Indonesia. Leadengineer/opencode harus cek langsung.

---

## 2026-10-10 — Verifikasi World Bank API (leadengineer)

Endpoint: `https://api.worldbank.org/v2/country/IDN/indicator/<KODE>?format=json&per_page=5`

| Indikator | Kode | Tahun Terbaru | Nilai |
|-----------|------|---------------|-------|
| PDB Growth | `NY.GDP.MKTP.KD.ZG` | 2025 | 5.10808904438025 |
| Inflasi | `FP.CPI.TOTL.ZG` | 2025 | 1.91333443295079 |
| Trade Balance (BoP) | `BN.GSR.GNFS.CD` | 2025 | 29649335679.1509 |
| Exports % GDP | `NE.EXP.GNFS.ZS` | 2025 | 22.8465482987858 |
| Imports % GDP | `NE.IMP.GNFS.ZS` | 2025 | 20.5446587523346 |

**Keputusan:** Neraca Perdagangan pakai `BN.GSR.GNFS.CD` (Trade Balance BoP, current US$).
Alasan: nilai absolut langsung, bukan persentase. Lebih mudah dipahami user.

---

## 2026-10-10 — Struktur folder (ketua_agen)

```
indonesia-economic-dashboard/
├── docs/PRD.md
├── task_plan.md
├── findings.md
├── progress.md
├── app.py
├── models.py
├── data_fetcher.py
├── scheduler.py
├── templates/dashboard.html
├── requirements.txt
└── README.md
```

Struktur file utama mengikuti PRD §9. Planning files di root project.

---

## 2026-10-10 — Bug: Jinja2 `.tojson` (ketua_agen, verifikasi independen)

**Gejala:** semua chart kosong di browser. HTML render `const years = ;`
— JS syntax error, seluruh `<script>` gagal.

**Root cause:** template memakai `{{ main_chart_data.tojson }}`.
Di Jinja2, `.tojson` adalah **method Python** milik objek list; dipanggil tanpa
argumen dan hasilnya bukan string JSON. Output menjadi string kosong.

**Fix:** `{{ main_chart_data|tojson }}` — pakai **filter** Jinja, bukan method.

**Pelajaran:** self-report "3 canvas chart ada" lolos karena canvas memang ada di
HTML. Yang tidak ada adalah **datanya**. Verifikasi harus cek nilai yang
di-render, bukan keberadaan elemen.

---

## 2026-10-10 — `uv pip install` menembus blokir RTK (ketua_agen)

Leadengineer gagal install `plotly` + `apscheduler` dan menyimpulkan "RTK blocks
pip install", lalu fallback ke Chart.js + threading manual — deviasi dari PRD §9.

**Yang benar:** `uv` sudah terpasang di `~/.local/bin/uv`, dan

```bash
uv pip install plotly apscheduler
```

berhasil tanpa hambatan. Ini sudah tercatat di skill `sop-programmer` sebagai
workaround resmi. Leadengineer tidak mencobanya.

**Pelajaran:** sebelum menyimpulkan "diblokir", coba semua workaround yang
tercatat di SOP. Jangan turunkan spesifikasi PRD karena satu percobaan gagal.

---

## 2026-10-10 — Dua bug yang lolos review + test otomatis (ketua_agen)

Kedua bug ini **lulus** code review independen `@programmer`, smoke test, dan
script acceptance 15/15. Yang menemukan: **user**, hanya dengan membaca output
di layar.

**Bug 1 — unit salah.** KPI Trade Balance menampilkan `+8295823081.86 pp`:
selisih USD mentah dilabeli "pp" karena satu helper format dipakai bersama
untuk semua indikator.

**Bug 2 — kalimat bertentangan dengan datanya.** Insight menulis
"Inflasi 6.5% **di luar target BI**, memberikan ruang bagi kebijakan moneter
yang stabil." Kondisi ("di luar target") ikut berubah bersama data, tapi
**kesimpulannya hardcoded**.

**Akar masalahnya sama:** verifikasi memeriksa **apakah sesuatu merespons /
tidak crash / format benar**, bukan **apakah isinya masuk akal**.

**Aturan:**
- Baca output yang benar-benar dirender — angka dan kalimatnya. Jangan cuma cek
  status code atau keberadaan elemen.
- Untuk teks yang dihasilkan dari data, **assert bahwa kesimpulan cocok dengan
  inputnya** — satu assertion per cabang.
- Uji **setiap cabang** dengan skenario yang benar-benar memicunya. Test yang
  hanya memakai nilai live saat itu hanya menutup satu cabang dan
  menyembunyikan sisanya.
- Code review otomatis tidak tahu satuan domainmu. Review hijau bukan bukti
  benar.

Contoh test yang benar: `test_insight_dynamic.py` — 5 skenario data, 11 assertion,
termasuk cek konsistensi logika (`"lebih ketat" in text_high and "akomodatif"
not in text_high`).


---

## Pelajaran: fixture test harus meniru urutan query nyata (2026-10-10)

Saat memperluas `test_insight_dynamic.py` untuk enhancement insight granular,
5 assertion langsung FAIL padahal kode `generate_insight()` benar.

**Sebab:** helper `make()` di test menyusun list data **ASC** (tahun lama dulu):
```python
 data = [{"value": prev_v, "year": year - 1}, {"value": v, "year": year}]
```
Padahal `get_indicator_data()` di `models.py` mengembalikan **DESC**:
```sql
ORDER BY year DESC LIMIT ?
```
Jadi `rows[1]` yang kode pakai sebagai "tahun sebelumnya" justru berisi nilai
terkini — tren YoY terbalik, dan frasa seperti "surplus melebar" salah muncul
sebagai "surplus menyempit".

**Fix:** `data = [{"value": v, "year": year}, {"value": prev_v, "year": year - 1}]`

**Aturan:** fixture test harus mereplikasi **urutan dan bentuk** data yang
benar-benar dihasilkan query produksi. Kalau tidak, test bisa gagal pada kode
yang benar — dan lebih berbahaya, bisa lulus pada kode yang salah.

Sumber urutan: `models.py` → `get_indicator_data()` → `ORDER BY year DESC`.

---

# Security Headers — temuan & pelajaran (2026-10-12)

## Kenapa grade-nya F

Tidak ada satu pun layer yang mengirim header keamanan: Cloudflare tidak
menambahkannya (bukan Cloudflare Pages, jadi tidak ada `_headers`), dan app
Flask tidak punya `after_request`. Dua layer, nol header.

## Inline script itu nyata — cek HTML ter-render, bukan source

Plotly `to_html()` menghasilkan **2 blok `<script>` inline per chart**
(3 chart = 6 tag; 5 terhitung di HTML final karena satu `<script src>` CDN).
Kalau `script-src 'self'` dipasang tanpa nonce, semua chart mati di browser
sementara `curl` tetap melihat HTTP 200 — kegagalan yang tidak terlihat di luar
browser.

Yang menyelamatkan: **nol** atribut `on*=` dan **nol** URL `javascript:`.
Handler attribute tidak bisa diselamatkan nonce (hanya `'unsafe-inline'` yang
bisa), jadi kalau ada handler, A+ tidak mungkin tanpa refactor ke
`addEventListener`. Di sini tidak ada, jadi nonce cukup.

## Nonce hiding — jangan tertipu

```js
script.getAttribute('nonce')   // '' — selalu, walau nonce ada
script.nonce                   // 'm_VdVFCa…' — ini yang benar
```

Browser menyembunyikan nilai atribut `nonce` supaya CSS selector tidak bisa
membacanya dan mengeksfiltrasi. Hasilnya: pengecekan DOM yang naif melaporkan
"semua script TANPA nonce" padahal nonce terpasang sempurna. Cek lewat properti
`.nonce`, atau grep body response dari curl.

## Kontrol negatif wajib

Halaman yang render bagus bisa berarti (a) CSP benar dan nonce cocok, atau
(b) CSP tidak ditegakkan sama sekali. Keduanya terlihat identik dari DOM.
Pembeda satu-satunya: suntik inline script **tanpa** nonce dan pastikan tidak
jalan.

```js
window.__noNonceRan = false;
const s = document.createElement('script');
s.textContent = 'window.__noNonceRan = true;';
document.body.appendChild(s);
// __noNonceRan tetap false + violation script-src-elem -> CSP memang hidup
```

Ini yang mengubah "sepertinya aman" menjadi bukti.

## Scanner-nya sendiri yang harus dijalankan

`curl` membuktikan header **terkirim**; tidak membuktikan **grade**.
securityheaders.com memblokir headless browser dengan Cloudflare challenge, dan
UA palsu di curl dapat 403. Yang berhasil: override UA ke Chrome desktop asli
lewat CDP `Network.setUserAgentOverride`, baru navigasi.

Jangan andalkan screenshot di halaman hasil scan — terlalu berat,
`Page.captureScreenshot` timeout 60 s. Baca `document.body.innerText`.

## `style-src 'unsafe-inline'` bukan target

Plotly menulis atribut `style=` pada elemen SVG, jadi `style-src` butuh
`'unsafe-inline'`. securityheaders.com **tidak** memotong grade karenanya
(dikonfirmasi dari hasil scan, bukan asumsi). Effort di situ sia-sia.

## HSTS: dua jebakan yang saling menutupi

1. Tanpa `ProxyFix`, `request.is_secure` selalu False di belakang TLS-terminating
   proxy → cabang HSTS tidak pernah jalan, dan konfigurasi **terlihat** benar.
2. HSTS di response HTTP bisa mem-pin browser ke skema yang host-nya tidak
   layani → situs tidak bisa diakses sampai `max-age` habis.

Keduanya harus diuji sebagai assertion: HSTS **ada** di HTTPS, **absen** di HTTP.

`preload` sengaja tidak dipasang — ireversibel berbulan-bulan, keputusan owner
bukan default yang wajar.
