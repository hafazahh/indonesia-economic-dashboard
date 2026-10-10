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

