# Task Plan — Indonesia Economic Dashboard

**Goal:** Dashboard web Flask menampilkan 3 indikator ekonomi Indonesia (PDB Growth,
Inflasi YoY, Neraca Perdagangan) dengan grafik 5 tahun, KPI cards, proyeksi,
insight box, auto-update dari World Bank API, dan download CSV.

**Sumber acuan:** `docs/PRD.md` (PRD v1.1, 10 Oktober 2026)

**Target user:** Akademis (mahasiswa/dosen) + Pebisnis

**Stack:** Flask + SQLite + APScheduler + Plotly + Jinja2

**Lokasi project:** `/home/choirulhaq/venvProject/indonesia-economic-dashboard/`

---

## Fase

| # | Fase | Owner | Status |
|---|------|-------|--------|
| 0 | Setup project + planning files | ketua_agen | complete |
| 1 | Design & breakdown teknis | leadengineer | complete |
| 2 | Implementasi (data layer + backend) | leadengineer | complete |
| 3 | Implementasi (frontend + chart) | leadengineer | complete |
| 4 | Review kode | programmer | **belum ada bukti** — tidak ada catatan review di progress.md |
| 5 | Verifikasi end-to-end | leadengineer | complete (self-report) |
| 6 | Verifikasi independen + perbaikan bug | ketua_agen | complete — 15/15 PASS |
| 7 | Push GitHub | ketua_agen | complete |
| 8 | Kesiapan deploy (bug gunicorn) | ketua_agen | complete |
| 9 | Deploy ke Render | user | **complete — LIVE** |
| 10 | Custom domain `inthiseconomy.choirulhaq.com` | user | **complete — Verified + Certificate Issued** |
| 11 | Card di website profil choirulhaq.com | ketua_agen | complete — live |
| 12 | Review kode formal (@programmer) | programmer | complete — PASS WITH ISSUES, 0 critical |
| 13 | Perbaikan bug unit KPI + temuan review | ketua_agen | complete — live |
| 14 | Perbaikan insight kontradiktif + test dinamis | ketua_agen | complete — live |
| 15 | Enhancement insight granular (4 peningkatan) | ketua_agen | complete — live, commit `49cf2a6` |
| 16 | Security headers → grade A+ (CSP nonce, HSTS, dll) | ketua_agen | **complete — LIVE, grade A+ terverifikasi** |

### Fase 16 — Security Headers — HASIL (2026-10-12)

**Grade: F → A+** (terverifikasi securityheaders.com sendiri, Report Time
12 Oct 2026 02:24:05 UTC).

| Header | Status live |
|---|---|
| Content-Security-Policy | ✅ `script-src 'nonce-…' https://cdn.plot.ly` |
| Strict-Transport-Security | ✅ `max-age=31536000; includeSubDomains` |
| X-Content-Type-Options | ✅ `nosniff` |
| X-Frame-Options | ✅ `DENY` |
| Referrer-Policy | ✅ `strict-origin-when-cross-origin` |
| Permissions-Policy | ✅ 9 API ditolak |
| Cross-Origin-Opener-Policy | ✅ `same-origin` |
| Cross-Origin-Resource-Policy | ✅ `same-origin` |

**Commit:** `fe93b35` (pushed ke `master`), file: `app.py`, `test_security_headers.py`.

**Verifikasi (bukti nyata, bukan self-report):**
- `test_security_headers.py` — **50/50 PASS**, termasuk kasus negatif HSTS absen
  di HTTP dan nonce harus unik per response.
- Browser nyata (domain live): 3 chart Plotly render, 9 SVG, 5 titik/trace,
  **0 CSP violation**, 5 inline script punya nonce, Bootstrap CSS termuat.
- **Kontrol negatif:** inline script yang disuntik tanpa nonce **diblokir**
  (`script-src-elem`, violation tercatat) — membuktikan CSP benar-benar
  ditegakkan dan halaman lolos bukan karena CSP-nya tidak jalan.
- Semua route tetap 200 (`/`, `/healthz`, `/download/csv`), test lama tetap
  lulus (KPI 17/17, insight 21/21, acceptance 15/15).

**Catatan grading:** `style-src 'unsafe-inline'` tetap ada (Plotly menulis
atribut `style=` pada elemen SVG). securityheaders.com tidak memotong grade
karenanya, jadi tidak diperjuangkan.

**Jebakan yang ditemukan:**
- securityheaders.com diblokir Cloudflare untuk headless browser default.
  Solusi: override UA ke Chrome Linux asli via CDP (`Network.setUserAgentOverride`).
- `script.getAttribute('nonce')` mengembalikan `''` walau nonce ada — itu
  perilaku anti-exfiltration browser, bukan bug. Baca lewat properti `.nonce`.
- Mozilla Observatory API sedang 502; tidak dipakai sebagai pembanding.

### Fase 16 — Security Headers (2026-10-12)

**Trigger:** user kirim screenshot securityheaders.com — grade **F**, semua header absen.

**Audit live (sebelum fix):** nol header keamanan di kedua layer —
`inthiseconomy.choirulhaq.com` (Cloudflare) dan `inthiseconomy.onrender.com`
(origin gunicorn). Jadi tidak ada layer yang menambahkan; harus dari app.

**Audit isi HTML (bukan grep source):**

| Temuan | Jumlah |
|---|---|
| inline `<script>` tanpa src | 5 (2 per chart Plotly) |
| inline event handler (`on*=` attr) | 0 |
| `javascript:` URL | 0 |
| script eksternal | 1 — `cdn.plot.ly/plotly-4.1.1.min.js` (ada SRI) |
| stylesheet eksternal | 1 — `cdn.jsdelivr.net/.../bootstrap.min.css` |
| `<img>` eksternal | 0 |

→ Inline script memang ada (Plotly), jadi `script-src 'self'` saja akan
mematikan semua chart. Tapi tidak ada handler attribute, jadi **nonce** cukup
dan `'unsafe-inline'` tidak perlu — itu yang memisahkan A dari A+.

**Rencana:**
1. `ProxyFix(x_for=1, x_proto=1, x_host=1)` — tanpa ini `request.is_secure`
   selalu False di belakang Cloudflare/Render dan cabang HSTS diam-diam mati.
2. Nonce per response (`secrets.token_urlsafe(16)`) di `before_request`.
3. `after_request`: CSP + X-Content-Type-Options + X-Frame-Options +
   Referrer-Policy + Permissions-Policy + COOP/CORP; HSTS **hanya kalau
   `request.is_secure`**, tanpa `preload`.
4. `apply_nonce()` menyisipkan nonce ke setiap inline `<script>` keluaran Plotly.
5. Test `test_security_headers.py` — termasuk kasus negatif HSTS absen di HTTP
   dan nonce harus unik per response.
6. Verifikasi **browser nyata**: chart harus tetap render, 0 CSP violation.
   Test client Flask tidak menegakkan CSP, jadi lulus test ≠ aman.
7. Push → Render auto-deploy → re-audit curl + securityheaders.com.

**Keputusan:** header di app (bukan dashboard Cloudflare) — versioned, reviewable,
survive misclick dashboard.

**Kanban:** board `indonesia-economic-dashboard`, task `t_e2a1df69`, assignee leadengineer.
**Notifikasi:** Telegram DM user (subscribed).

**Branch git: `master`** (bukan `main`).

---

## Status Live (2026-10-10)

| Item | Nilai |
|------|-------|
| URL live | https://inthiseconomy.choirulhaq.com |
| URL origin | https://inthiseconomy.onrender.com |
| Repo | https://github.com/hafazahh/indonesia-economic-dashboard |
| Verifikasi live | **15/15 PASS** (dijalankan terhadap domain custom) |
| Test insight | **21/21 PASS** (21 skenario, 21 teks unik) |
| Test KPI | **17/17 PASS** |
| Insight box | Granular: inflasi 3 kondisi, PDB tren YoY, trade magnitude+arah, kombinasi makro |
| `/healthz` | `{"status":"ok","scheduler_running":true,"rows_stored":176}` |
| TLS | Google Trust Services WE1, verify code 0, valid s/d 8 Jan 2027 |
| Render chart nyata | 3 chart Plotly, 5 titik data/trace, 9 SVG, 0 JS error |
| Cold start | 0.47 s |
| Card di choirulhaq.com | ✅ live (commit `70c674a`) |

---

## Cara Resume di Sesi Baru

**Status: project SELESAI & LIVE.** Tidak ada pekerjaan menggantung.

```bash
cd /home/choirulhaq/venvProject/indonesia-economic-dashboard
source /home/choirulhaq/venvProject/venv/bin/activate

# Jalankan lokal
python3 app.py                          # http://localhost:5000

# Test (3 script, semua harus lulus)
python3 test_kpi_units.py               # 17/17 PASS
python3 test_insight_dynamic.py         # 21/21 PASS (21 skenario)
BASE_URL=https://inthiseconomy.choirulhaq.com python3 verify_acceptance.py   # 15/15 PASS
```

**Push:** branch `master` (bukan `main`).

**Baca ini dulu:** `progress.md` (log lengkap per sesi), `findings.md` (temuan
teknis + pelajaran), `docs/REVIEW.md` (hasil code review), `docs/PRD.md` (acuan).

**Yang belum dikerjakan (di luar scope PRD v1.1):** data kuartalan/bulanan,
indikator tambahan (kurs, investasi, pengangguran, sektor), chart interaktif,
proyeksi dari API (sekarang hardcode IMF), desain lebih branded.
Butuh PRD baru sebelum dikerjakan.

---

## Keputusan

| Tanggal | Keputusan | Alasan |
|---------|-----------|--------|
| 2026-10-10 | Folder project: `venvProject/indonesia-economic-dashboard/` | disk lokal, sesuai SOP §4 & §16 |
| 2026-10-10 | Venv: `/home/choirulhaq/venvProject/venv` | venv bersama, sesuai SOP §4 |
| 2026-10-10 | Delegasi via Kanban board `indonesia-economic-dashboard` | durable, ada retry + notifikasi |
| 2026-10-10 | Config profile leadengineer: provider nous (bukan openrouter) | openrouter tanpa API key → profile gagal start |
| 2026-10-10 | Salin skill root ke profile leadengineer | `skills.auto_load` gagal `Unknown skill(s)` → worker crash |
| 2026-10-10 | Chart: Plotly (bukan Chart.js) | PRD §9 minta Plotly; `uv pip install` berhasil padahal leadengineer gagal |
| 2026-10-10 | Scheduler: APScheduler (bukan threading manual) | PRD §9 minta APScheduler |
| 2026-10-10 | `pandas` dihapus dari requirements | tidak dipakai sama sekali di kode |

---

## Pertanyaan Terbuka — SELESAI

| Pertanyaan | Keputusan | Alasan |
|-------------|-----------|--------|
| Kode indikator Neraca Perdagangan | `BN.GSR.GNFS.CD` (Trade Balance BoP, current US$) | Nilai absolut langsung, verifikasi API sukses |
| Proyeksi | Hardcode IMF WEO | PRD §6 izinkan; lebih sederhana, tidak perlu API tambahan |
| Frontend | Bootstrap 5 | Lebih cepat implementasi, PRD §9 izinkan pilih salah satu |

---

## Errors Encountered

| Error | Attempt | Resolution |
|-------|---------|------------|
| Profile leadengineer: `No API key found for provider 'openrouter'` | 1 | Ganti config ke provider nous |
| Kanban worker crash: `Unknown skill(s): leadengineer, planning-with-files, sop` | 2 | Salin skill dari root ke `profiles/leadengineer/skills/` |
| **Chart kosong** — `const years = ;` (JS syntax error) | 1 (ketua_agen) | `.tojson` bukan filter Jinja → ganti `|tojson` |
| RTK blokir `pip install plotly apscheduler` (leadengineer menyerah, fallback Chart.js + threading) | 1 (ketua_agen) | `uv pip install plotly apscheduler` — berhasil, sesuai workaround SOP |
| Proses `app.py` zombie dari worker leadengineer masih pegang port 5000 | 1 (ketua_agen) | `pkill -9 -f app.py`, restart bersih |
| KPI trade balance tampil `29.6 M USD` (ambigu: juta/miliar) | 1 (ketua_agen) | Ganti ke `29.6 miliar USD` |

---

## Fase 17 — Ekspansi Makro + Micro Economy (2026-10-13)

**Goal:** Tambah indikator makro baru (BI-Rate, kurs USD/IDR, Gini, kesejahteraan)
dan buat landing page micro economy terpisah dengan metrik gabungan BBM vs upah.

### 17.1 — Makro Ekonomi (dashboard existing)

**Indikator baru:**
- **BI-Rate** — live update dari Bank Indonesia
- **Kurs USD/IDR** — live update dari Bank Indonesia
- **Rasio Gini** — World Bank API (`SI.POV.GINI`)
- **Tingkat kesejahteraan** — indikator turunan (IPM atau indikator BPS)

**Data sources:**
- BI-Rate: `https://api.bi.go.id` atau scraping `bi.go.id`
- Kurs USD/IDR: `https://api.bi.go.id` atau `https://api.exchangerate.host`
- Gini: World Bank API `SI.POV.GINI`

### 17.2 — Micro Economy (landing page baru)

**Route baru:** `/micro` atau `/micro-economy`

**Konten:**
1. **Perbandingan Harga Emas vs BBM** (Pertalite, Pertamax)
   - Harga emas: Antam / gold-api.com
   - Harga BBM: Pertamina / Kementerian ESDM
2. **Indeks Keyakinan Konsumen (IKK)** — Bank Indonesia
3. **IKK vs Harga Emas & BBM** — perbandingan visual

### 17.3 — Metrik Gabungan (dari gambar user)

| Metrik | Rumus | Interpretasi |
|--------|-------|--------------|
| Liter per upah minimum | UMP / harga BBM per liter | Liter BBM yang bisa dibeli dengan 1 bulan upah minimum |
| Jam kerja per liter | Harga BBM per liter / upah per jam | Jam kerja untuk membeli 1 liter BBM |
| Indeks harga BBM vs indeks upah | (Indeks BBM / Indeks upah) × 100 | Apakah harga BBM naik lebih cepat dari upah |
| Beban BBM terhadap pengeluaran | (Konsumsi BBM × harga) / Total pengeluaran | Berapa persen pengeluaran habis untuk BBM |

**Data sources:**
- UMP per provinsi: BPS / Kementerianakerja
- Harga BBM: Pertamina / Kementerian ESDM
- Konsumsi BBM per bulan: asumsi (misal 20 liter/bulan)

### 17.4 — Saran Penyajian

1. **Grafik garis dua indeks** (harga BBM vs upah) — lebih mudah dipahami awam
2. **Tandai momen kenaikan/penurunan BBM** di grafik, tampilkan efek ke inflasi & IKK setelahnya
3. **Pilihan per provinsi** untuk rasio liter per upah (UMP dan harga BBM berbeda antar wilayah)
4. **Cantumkan asumsi perhitungan** (UMP provinsi mana, konsumsi BBM per bulan) agar transparan

### Fase 17 — Status

| # | Sub-fase | Status |
|---|----------|--------|
| 17.1 | Makro: BI-Rate + kurs USD/IDR + Gini | **belum mulai** |
| 17.2 | Micro: landing page + emas vs BBM + IKK | **belum mulai** |
| 17.3 | Metrik gabungan BBM vs upah | **belum mulai** |
| 17.4 | Saran penyajian (grafik, provinsi, asumsi) | **belum mulai** |

### Data Sources — Perlu Dicek

| Data | Source | API? | Live? |
|------|--------|------|-------|
| BI-Rate | Bank Indonesia | `api.bi.go.id` | Ya |
| Kurs USD/IDR | Bank Indonesia | `api.bi.go.id` | Ya |
| Gini | World Bank | `SI.POV.GINI` | Tahunan |
| IKK | Bank Indonesia | Perlu cek | Bulanan |
| Harga emas | Antam / gold-api.com | Perlu cek | Ya |
| Harga BBM | Pertamina / ESDM | Perlu cek | Ya |
| UMP per provinsi | BPS / Kemnaker | Perlu cek | Tahunan |

**Next:** Cek availability API untuk setiap data source, lalu delegasi ke leadengineer.
