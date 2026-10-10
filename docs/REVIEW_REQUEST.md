# Review Request — Indonesia Economic Dashboard

Kamu adalah **reviewer independen**. Kamu tidak tahu bagaimana kode ini dibuat.
Tugasmu: temukan bug, risiko keamanan, dan masalah logika. Jangan puji.

## Project
- **Lokasi:** `/home/choirulhaq/venvProject/indonesia-economic-dashboard/`
- **Live:** https://inthiseconomy.choirulhaq.com
- **Stack:** Flask 3.1.3 + SQLite (WAL) + APScheduler 3.11.3 + Plotly 7.1.0 + gunicorn
- **Deploy:** Render free tier (Singapore), Cloudflare DNS
- **Sumber data:** World Bank API (tanpa API key)

## File yang direview
```
app.py              — Flask routes, KPI, insight, chart builder, bootstrap()
models.py           — SQLite schema + queries
data_fetcher.py     — World Bank API fetcher
scheduler.py        — APScheduler background job
templates/dashboard.html — Jinja2 template
verify_acceptance.py — 15 uji acceptance criteria
```

## Hasil static scan (sudah dijalankan, semua bersih)
- Hardcoded secrets: tidak ada
- Shell injection (`os.system`, `shell=True`): tidak ada
- `eval()` / `exec()`: tidak ada
- `pickle.loads()`: tidak ada
- SQL injection (f-string di query): tidak ada — semua query parameterized

## Konteks penting yang perlu kamu pertimbangkan
1. Free tier Render **tidak punya persistent disk** — `economic_data.db` hilang
   tiap restart. `bootstrap()` sengaja fetch ulang saat DB kosong.
2. App ini **read-only** — tidak ada input user, tidak ada auth, tidak ada form.
3. Scheduler berjalan sebagai thread di dalam proses gunicorn.

## Yang saya ingin kamu periksa khusus

**Logika & ketahanan:**
- `bootstrap()` di `app.py` — apakah aman dijalankan saat import? Bagaimana kalau
  World Bank API down saat boot?
- `compute_kpis()` di `app.py` — apakah perhitungan perubahan YoY benar? Perhatikan
  kasus data kurang dari 2 baris.
- `generate_insight()` — apakah bisa crash kalau salah satu indikator tidak ada data?
- `models.py` — apakah koneksi DB selalu ditutup? Ada risiko kebocoran koneksi?
- `scheduler.py` — apa yang terjadi kalau fetch gagal berulang?

**Race condition:**
- Scheduler thread menulis ke SQLite sementara request gunicorn membaca. Apakah
  WAL + busy_timeout sudah cukup? Ada risiko "database is locked"?

**Keamanan:**
- `templates/dashboard.html` memakai `{{ chart|safe }}` untuk menyisipkan HTML Plotly.
  Apakah ini XSS risk? (Plotly HTML dibangun server-side dari data API eksternal.)
- `/download/csv` — ada risiko CSV injection (formula injection)?
- Apakah ada data eksternal yang masuk ke HTML tanpa escaping?

**Kualitas:**
- Error handling di `data_fetcher.py` — apakah cukup? Apakah kegagalan diam-diam?
- Apakah ada kode mati atau tidak terpakai?

## Cara kerja
1. Baca file-file di atas.
2. Jalankan tes kalau perlu: `source /home/choirulhaq/venvProject/venv/bin/activate`
3. App bisa dijalankan: `python3 app.py` (port 5000). **Jangan** pakai port 5000
   kalau sudah terpakai — pakai PORT env.
4. Verifikasi klaimmu dengan menjalankan kode, jangan menebak.

## Aturan
- Semua perintah terminal lewat `rtk`.
- Jangan `python3 -c` — tulis script ke file.
- Jangan ubah kode. Review saja.

## Format laporan

Tulis laporan ke `REVIEW.md` di folder project, dengan struktur:

```markdown
# Code Review — Indonesia Economic Dashboard

## Verdict
PASS / PASS WITH ISSUES / FAIL

## Critical (harus diperbaiki)
- [file:baris] masalah — kenapa berbahaya — cara verifikasi

## Warning (sebaiknya diperbaiki)
- ...

## Suggestion (opsional)
- ...

## Yang sudah diverifikasi benar
- (sebutkan apa yang kamu UJI, bukan yang kamu baca)
```

Kalau tidak menemukan masalah critical, katakan demikian — jangan mengarang.
Sertakan bukti (output command) untuk setiap klaim.
