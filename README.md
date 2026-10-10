# Indonesia Economic Dashboard

Dashboard web Flask menampilkan 3 indikator ekonomi Indonesia: PDB Growth, Inflasi YoY, dan Neraca Perdagangan.

## Fitur
- KPI cards dengan nilai terbaru + perubahan YoY + status vs target BI
- Grafik tren 5 tahun PDB Growth & Inflasi (Plotly)
- Detail chart per indikator (Plotly)
- Proyeksi IMF WEO (hardcoded)
- Insight box untuk akademisi & pebisnis
- Download CSV (untuk keperluan akademik)
- Auto-update dari World Bank API (setiap 6 jam via APScheduler)
- Penyimpanan SQLite lokal

## Menjalankan

```bash
# Aktifkan venv
source /home/choirulhaq/venvProject/venv/bin/activate

# Install dependencies
pip install -r requirements.txt
# Jika pip diblokir RTK/Tirith:
uv pip install -r requirements.txt

# Jalankan (otomatis fetch data + start scheduler)
python app.py
```

Buka http://localhost:5000

## Endpoint
| Path | Fungsi |
|------|--------|
| `/` | Dashboard utama |
| `/download/csv` | Unduh seluruh data (CSV) |
| `/health` | Health check (JSON) |

## Sumber Data
- World Bank API (PDB Growth, Inflasi, Trade Balance) — tanpa API key
- IMF WEO (proyeksi, hardcoded)
- BPS (alternatif)

Kode indikator:
| Indikator | Kode World Bank |
|-----------|-----------------|
| PDB Growth | `NY.GDP.MKTP.KD.ZG` |
| Inflasi YoY | `FP.CPI.TOTL.ZG` |
| Neraca Perdagangan | `BN.GSR.GNFS.CD` (BoP, current US$) |

## Struktur
```
app.py                  — Flask app + routes + chart builder
models.py               — SQLite schema + queries
data_fetcher.py         — World Bank API fetcher
scheduler.py            — Auto-update via APScheduler
templates/dashboard.html — Jinja2 template
requirements.txt        — Python dependencies
economic_data.db        — SQLite database (auto-generated)
verify_acceptance.py    — Verifikasi independen acceptance criteria PRD §12
dashboard_screenshot.png — Bukti render dashboard
```

## Verifikasi

```bash
python app.py &                     # jalankan server
python verify_acceptance.py         # 15/15 PASS
```

## Catatan Teknis
- Data disimpan di SQLite (`economic_data.db`), update tiap 6 jam.
- Jika API gagal, dashboard tetap menampilkan data terakhir dari DB
  (error handling di `data_fetcher.fetch_indicator`).
- Chart dibangun server-side dengan Plotly dan di-embed sebagai inline HTML.
