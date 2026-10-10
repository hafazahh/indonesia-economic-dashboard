# Indonesia Economic Dashboard — Fase 1: Design & Breakdown, lalu implementasi

## Project
- **Lokasi:** `/home/choirulhaq/venvProject/indonesia-economic-dashboard/`
- **Venv:** `/home/choirulhaq/venvProject/venv` — aktifkan: `source /home/choirulhaq/venvProject/venv/bin/activate`
- **PRD lengkap:** `docs/PRD.md` — BACA DULU, ini acuan utama.
- **Brief detail:** `docs/BRIEF_LEADENGINEER.md` — baca juga.
- **Planning files** sudah ada: `task_plan.md`, `findings.md`, `progress.md`. Baca dan UPDATE, jangan buat ulang.

## Yang diminta

Dashboard web Flask menampilkan 3 indikator ekonomi Indonesia (PDB Growth, Inflasi YoY,
Neraca Perdagangan): KPI cards, line chart 5 tahun, detail charts, proyeksi, insight box,
download CSV, sumber data + last updated, auto-update via APScheduler dari World Bank API,
penyimpanan SQLite.

## Tugas Fase 1 (wajib sebelum coding)

1. Baca `docs/PRD.md` dan `docs/BRIEF_LEADENGINEER.md`.
2. **Verifikasi nyata** kode indikator World Bank API untuk Indonesia — jangan asumsi:
   - PDB Growth: `NY.GDP.MKTP.KD.ZG`
   - Inflasi: `FP.CPI.TOTL.ZG`
   - Neraca Perdagangan: tentukan sendiri kode yang tepat (PRD belum mematok)
   Endpoint: `https://api.worldbank.org/v2/country/IDN/indicator/<KODE>?format=json&per_page=100`
   Catat hasil nyata (tahun terbaru + nilai) ke `findings.md`.
3. Putuskan 3 pertanyaan terbuka di `task_plan.md`:
   - kode indikator Neraca Perdagangan
   - proyeksi: hardcode IMF WEO atau hitung dari tren
   - frontend: Bootstrap atau Tailwind
4. Tulis breakdown fase implementasi konkret di `task_plan.md` dengan acceptance
   criteria per fase (data layer → backend → frontend → verifikasi).
5. Implementasi tiap fase — delegasikan ke opencode:
   `/home/choirulhaq/.opencode/bin/opencode`
   - pakai model default free, JANGAN pakai `--model`
   - bungkus dengan `timeout` biar tidak hang
   - kalau opencode gagal/timeout → kerjakan langsung dengan patch/write_file
6. Review hasil oleh `@programmer`.
7. Verifikasi end-to-end: jalankan app, buktikan tiap item Acceptance Criteria PRD §12.

## Aturan wajib
- Semua perintah terminal lewat `rtk`.
- Jangan `pip install` di system Python — pakai venv.
- Jangan `python3 -c` — tulis script ke file, jalankan `python3 file.py`.
- Update planning files setelah tiap fase. Log semua error (attempt + resolusi).
- Verifikasi: jangan percaya self-report. Jalankan dan buktikan dengan output nyata.
- Komunikasi ke user: Bahasa Indonesia, caveman mode (padat, teknis).

## Definisi selesai
Semua Acceptance Criteria PRD §12 terpenuhi dengan bukti nyata:
dashboard jalan, 3 KPI cards tampil, chart 5 tahun render, proyeksi ada,
insight box relevan, auto-update jalan, sumber data + last updated tercantum,
tombol CSV berfungsi, app bisa dijalankan `python app.py`.

Tulis laporan akhir di `progress.md` dan balas ke user: apa yang dibuat,
bukti verifikasi, apa yang belum.
