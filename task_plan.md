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
| 10 | Custom domain `inthiseconomy.choirulhaq.com` | user | pending — DNS record belum ada |

**Kanban:** board `indonesia-economic-dashboard`, task `t_e2a1df69`, assignee leadengineer.
**Notifikasi:** Telegram DM user (subscribed).

---

## Status Live (2026-10-10)

| Item | Nilai |
|------|-------|
| URL live | https://inthiseconomy.onrender.com |
| Repo | https://github.com/hafazahh/indonesia-economic-dashboard |
| Verifikasi live | **15/15 PASS** (dijalankan terhadap URL produksi) |
| `/healthz` | `{"status":"ok","scheduler_running":true,"rows_stored":176}` |
| Render chart nyata | 3 chart Plotly, 5 titik data/trace, 9 SVG, 0 JS error |
| Cold start | 0.47 s |
| Custom domain | ⏳ belum — DNS record `inthiseconomy` belum dibuat di Cloudflare |

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
