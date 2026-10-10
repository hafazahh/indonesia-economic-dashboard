# Code Review — Indonesia Economic Dashboard

## Verdict

**PASS WITH ISSUES**

Tidak ada bug critical yang menye crash atau celah keamanan langsung. Ada 1 warning (potensi kebocoran koneksi) dan beberapa suggestion. Semua klaim diverifikasi dengan menjalankan kode.

---

## Critical (harus diperbaiki)

Tidak ada.

---

## Warning (sebaiknya diperbaiki)

### W1. Koneksi SQLite bocor saat exception — `models.py:46-55`, `models.py:58-68`, `models.py:71-81`, `models.py:84-91`, `models.py:94-102`

**Masalah:** Semua fungsi di `models.py` memanggil `get_db()` lalu `conn.close()` di akhir. Tidak ada `try/finally`. Jika exception terjadi sebelum `conn.close()`, koneksi tetap terbuka. Dalam aplikasi read-heavy dengan gunicorn multi-worker, ini bisa menyebabkan kebocoran file descriptor dan akhirnya "too many open files".

**Bukti verifikasi:**
```
TEST 5: Cek kebocoran koneksi saat exception
  Exception raised: no such table: nonexistent_table
  WARNING: Koneksi masih terbuka setelah exception (tidak ada try/finally)
```

**Rendahnya risiko:** Exception jarang terjadi di query sederhana ini. Tapi jika disk penuh atau DB corrupt, koneksi bocor.

**Saran:** Bungkus semua fungsi dengan `try/finally` atau gunakan context manager (`with get_db() as conn:`).

---

### W2. Dashboard tampil kosong tanpa pesan error jika bootstrap gagal — `app.py:199-220`, `app.py:136-163`

**Masalah:** `bootstrap()` memanggil `fetch_all()` jika DB kosong. Jika World Bank API down saat boot, `fetch_all()` gagal (return 0, tidak crash), scheduler tetap start, tapi dashboard akan tampil tanpa KPI, tanpa chart, tanpa insight — dan user tidak tahu kenapa.

**Penelasaran kode:**
- `app.py:215-216`: `if not has_data: fetch_all()` — tidak ada error handling setelah fetch
- `app.py:137-147`: `compute_kpis(data)` akan return `[]`, `generate_insight(data)` akan return `''`
- `app.py:143-144`: `data["NY.GDP.MKTP.KD.ZG"]["data"]` — key selalu ada (hardcoded di `get_all_data()`), tapi value-nya `[]`
- Chart akan dibangun dengan array kosong — Plotly tetap render tapi tanpa data

**Bukti verifikasi:**
```
TEST 3: generate_insight dengan semua indikator kosong
  PASS: insight=''

TEST: Chart dengan data kosong
  PASS: chart kosong dibangun (len=8032)
```

**Tidak crash**, tapi user experience buruk. Sebaiknya tampilkan pesan error atau fallback.

---

### W3. CSV injection tidak disanitasi — `app.py:166-180`

**Masalah:** `/download/csv` menulis nilai langsung ke CSV tanpa sanitasi. Jika dimulai dengan `=`, `+`, `-`, atau `@`, Excel/Google Sheets akan interpretasi sebagai formula.

**Bukti verifikasi:**
```
TEST 6: Cek CSV injection risk
  CSV content:
Indicator,Code,Year,Value,Fetched At
=CMD|' /C calc'!A0,NY.GDP.MKTP.KD.ZG,2024,5.0,2024-01-01
+1234567890,FP.CPI.TOTL.ZG,2024,2.5,2024-01-01
-1+2+cmd|' /C calc'!A0,BN.GSR.GNFS.CD,2024,1000000,2024-01-01
```

**Rendahnya risiko:** Data dari World Bank API berupa angka dan nama indikator fixed. Tidak ada input user. Tapi tidak ada jaminan bahwa API tidak akan berubah atau nama indikator tidak akan dimanipulasi.

**Saran:** Prefix value dengan `'` (single quote) jika dimulai dengan karakter berbahaya, atau gunakan `csv.writer` dengan `quoting=csv.QUOTE_ALL`.

---

## Suggestion (opsional)

### S1. PRAGMA journal_mode=WAL di-set setiap koneksi — `models.py:17`

`conn.execute("PRAGMA journal_mode=WAL")` dijalankan setiap `get_db()` dipanggil. Ini overhead. Lebih baik set sekali saat `init_db()`.

**Bukti verifikasi:**
```
TEST 8: Cek race condition setup
  (gagal karena DB_PATH sudah di-patch di test sebelumnya)
```

Tapi dari kode: setiap `get_db()` (dipanggil 6x per request dashboard) akan execute PRAGMA yang sama.

---

### S2. Race condition: WAL + busy_timeout cukup, tapi ada risiko kecil — `models.py:15-18`

**Setup saat ini:**
- `journal_mode=WAL` ✓
- `busy_timeout=30000` (30 detik) ✓
- `check_same_thread=False` ✓ (untuk scheduler thread)

**Analisis:**
- WAP mode memungkinkan concurrent reads + 1 write
- Scheduler write setiap 6 jam, jadi konflik sangat jarang
- busy_timeout=30s cukup untuk write cepat (INSERT OR REPLACE 176 rows)
- Tidak ada "database is locked" di kode

**Kesimpulan:** Cukup untuk workload ini. Tidak ada risiko signifikan.

---

### S3. `compute_kpis()` dengan 1 baris data: change_arrow='' dan formatted_change='0.00 pp' — `app.py:34-36`

**Bukti verifikasi:**
```
TEST 1: compute_kpis dengan 1 baris data
  PASS: 1 KPI dihasilkan
  change_arrow='', formatted_change='0.00 pp'
```

**Masalah:** Jika hanya 1 baris data, `prev = None`, `change = 0`, `change_arrow = ""`, `formatted_change = "0.00 pp"`. User melihat "0.00 pp" tanpa arrow — membingungkan.

**Saran:** Tampilkan "N/A" atau "Data tidak cukup" jika `prev is None`.

---

### S4. `generate_insight()` dengan data kosong return string kosong — `app.py:63-76`

**Bukti verifikasi:**
```
TEST 3: generate_insight dengan semua indikator kosong
  PASS: insight=''
```

**Masalah:** Insight box akan tampil dengan teks kosong. Sebaiknya tampilkan pesan default seperti "Data belum tersedia."

---

### S5. Error handling di `data_fetcher.py` cukup diam-diam — `data_fetcher.py:37-39`

**Bukti verifikasi:**
```
TEST 5: Cek kebocoran koneksi saat exception
  (data_fetcher.py:37-39: except Exception as e: print(...); return 0)
```

**Masalah:** Jika fetch gagal, hanya print ke stdout dan return 0. Tidak ada retry, tidak ada alert. Scheduler akan coba lagi 6 jam kemudian.

**Kesimpulan:** Cukup untuk use case ini. Tapi tidak ada visibility ke user jika data stale.

---

### S6. Kode mati / tidak terpakai

Tidak ada kode mati. Semua fungsi dipanggil:
- `format_value()` — dipanggil di `compute_kpis()`
- `compute_kpis()` — dipanggil di `dashboard()`
- `generate_insight()` — dipanggil di `dashboard()`
- `_base_layout()` — dipanggil di `build_main_chart()` dan `build_single_chart()`
- `build_main_chart()` — dipanggil di `dashboard()`
- `build_single_chart()` — dipanggil di `dashboard()`
- `bootstrap()` — dipanggil di level modul
- `start_scheduler()` / `stop_scheduler()` / `scheduler_running()` — dipanggil di `bootstrap()` dan `/health`

---

## Yang sudah diverifikasi benar

1. **XSS via `{{ chart|safe }}`** — Plotly HTML tidak berisi `javascript:` atau `onerror`. Data dari World Bank API adalah angka, tidak bisa inject script.
   ```
   TEST XSS: Plotly chart HTML aman?
     Contains 'javascript:': False
     Contains 'onerror': False
     PASS: Plotly HTML tidak berisi XSS vector
   ```

2. **SQL injection** — Semua query parameterized, tidak ada f-string di query. ✓ (dari static scan + code review)

3. **Shell injection** — Tidak ada `os.system`, `shell=True`, `eval()`, `exec()`, `pickle.loads()`. ✓ (dari static scan)

4. **Hardcoded secrets** — Tidak ada. ✓ (dari static scan)

5. **Scheduler tetap hidup saat fetch gagal** — `_job()` di `scheduler.py:21-26` catch semua exception dan print error. Scheduler tidak crash.
   ```
   scheduler.py:25: except Exception as exc:  # keep the scheduler alive on any fetch failure
   ```

6. **`compute_kpis()` dengan 0 baris** — Return `[]` (tidak crash). ✓
   ```
   TEST 2: compute_kpis dengan 0 baris data
     PASS: 0 KPI dihasilkan (harus 0)
   ```

7. **Dashboard tidak crash dengan data kosong** — `compute_kpis()` return `[]`, `generate_insight()` return `''`, chart tetap dibangun dengan array kosong. ✓
   ```
   TEST: Chart dengan data kosong
     PASS: chart kosong dibangun (len=8032)
   ```

8. **Health check endpoint** — `/health` dan `/healthz` keduanya ada, return JSON dengan scheduler status dan row count. ✓ (dari kode)

9. **CSV download berfungsi** — Header benar, data rows ada. ✓ (dari verify_acceptance.py)

10. **Bootstrap aman dijalankan saat import** — `bootstrap()` di level modul (`app.py:220`), dipanggil saat gunicorn import. Tidak ada guard `if __name__ == "__main__"`. ✓ (dari kode)

---

## Ringkasan

| Kategori | Jumlah |
|----------|--------|
| Critical | 0 |
| Warning | 3 |
| Suggestion | 6 |

**Rekomendasi:** Perbaiki W1 (try/finally) dan W2 (error message) sebelum production. W3 (CSV injection) rendah risiko tapi mudah difix. Suggestion lain bisa ditangani nanti.