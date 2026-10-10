# Brief untuk Lead Engineer — Indonesia Economic Dashboard

## Konteks

Project baru. PRD lengkap ada di `docs/PRD.md` (baca dulu, itu acuan utama).

**Lokasi project:** `/home/choirulhaq/venvProject/indonesia-economic-dashboard/`
**Venv:** `/home/choirulhaq/venvProject/venv` (aktifkan sebelum kerja)
**Planning files** sudah ada di root project: `task_plan.md`, `findings.md`, `progress.md`
— baca dan UPDATE ketiganya, jangan buat ulang.

## Tugas kamu (Fase 1 — Design & Breakdown)

1. Baca `docs/PRD.md` lengkap.
2. Verifikasi kode indikator World Bank API benar-benar mengembalikan data untuk Indonesia:
   - PDB Growth: `NY.GDP.MKTP.KD.ZG`
   - Inflasi: `FP.CPI.TOTL.ZG`
   - Neraca Perdagangan: tentukan kode yang tepat (PRD belum mematok)
   Endpoint: `https://api.worldbank.org/v2/country/IDN/indicator/<KODE>?format=json&per_page=100`
   Tulis hasil verifikasi nyata ke `findings.md` (bukan asumsi).
3. Putuskan 3 pertanyaan terbuka di `task_plan.md`:
   - Kode indikator Neraca Perdagangan
   - Proyeksi: hardcode IMF atau hitung dari tren
   - Frontend: Bootstrap atau Tailwind
4. Rancang breakdown fase implementasi yang konkret di `task_plan.md`
   (data layer → backend → frontend → verifikasi). Sertakan acceptance criteria
   per fase.
5. Delegasikan implementasi ke opencode per fase:
   `/home/choirulhaq/.opencode/bin/opencode` — pakai model default free, JANGAN `--model`,
   bungkus dengan `timeout`.
6. Setelah implementasi selesai: minta review `@programmer`, lalu verifikasi
   end-to-end (jalankan app, cek tiap acceptance criteria PRD §12 dengan bukti nyata).

## Aturan wajib

- Semua perintah terminal lewat `rtk`.
- Jangan `pip install` di system Python — pakai venv.
- Jangan `python3 -c` — tulis script ke file.
- Update planning files setelah tiap fase. Log semua error.
- Komunikasi ke user: Bahasa Indonesia, caveman mode.
- Verifikasi: jangan percaya self-report. Jalankan dan buktikan.

## Definisi selesai

Semua item Acceptance Criteria PRD §12 terpenuhi, dibuktikan dengan output nyata
(app jalan, KPI tampil, chart render, CSV ter-download, data ter-update).
Laporan akhir ke user berisi: apa yang dibuat, bukti verifikasi, apa yang belum.
