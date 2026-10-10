# PRD: Indonesia Economic Dashboard

**Versi:** 1.1  
**Tanggal:** 10 Oktober 2026  
**Stack:** Python Flask  
**Status:** Ready for Development  
**Target User:** Akademis (Mahasiswa & Dosen) dan Pebisnis

## 1. Ringkasan Produk

Dashboard web sederhana berbasis Flask untuk menampilkan kondisi ekonomi Indonesia, fokus pada tiga indikator utama: **Pertumbuhan PDB**, **Inflasi**, dan **Neraca Perdagangan**. Dirancang khusus untuk kebutuhan **akademis** (tugas, penelitian, referensi) dan **pebisnis** (pengambilan keputusan cepat). Dashboard menampilkan data historis (5 tahun terakhir), grafik tren, perbandingan YoY, proyeksi, serta insight singkat yang mudah dipahami.

## 2. Tujuan

- Memberikan gambaran cepat dan akurat kondisi ekonomi Indonesia.
- Memudahkan mahasiswa/dosen mengakses data resmi untuk keperluan akademik.
- Membantu pebisnis memahami dampak indikator makro terhadap keputusan bisnis.
- Data selalu ter-update secara otomatis dari sumber kredibel.
- Desain bersih, informatif, dan mudah dipahami oleh non-ahli.

## 3. Target User

### Akademis
- Mahasiswa (Ekonomi, Bisnis, Statistik, Hubungan Internasional)
- Dosen dan peneliti
- Kebutuhan: data akurat, sumber jelas, grafik yang bisa digunakan untuk presentasi/tugas

### Pebisnis
- Pemilik UMKM dan perusahaan
- Manajer dan analis bisnis
- Investor
- Kebutuhan: insight cepat, dampak terhadap bisnis, tren yang mudah dibaca

## 4. Scope

### In Scope
- 3 indikator utama: PDB Growth, Inflasi (YoY), Neraca Perdagangan
- Grafik 5 tahun terakhir
- KPI cards dengan nilai terbaru + perubahan
- Bagian proyeksi (forecast)
- **Insight singkat** untuk akademis dan pebisnis
- Auto-update data dari API
- Sumber data jelas + last updated
- Tombol download data (CSV) untuk keperluan akademik

### Out of Scope
- Data regional (provinsi)
- Indikator tambahan (pengangguran, BI Rate, komoditas, dll.)
- Login / user management
- Laporan PDF otomatis
- Aplikasi mobile native

## 5. Fitur Utama

| Fitur | Deskripsi | Target User | Prioritas |
|-------|-----------|-------------|-----------|
| KPI Cards | Nilai terbaru + perubahan + status (dalam/di luar target) | Semua | Tinggi |
| Grafik 5 Tahun | Line chart tren PDB Growth dan Inflasi | Semua | Tinggi |
| Detail Charts | Chart terpisah PDB & Inflasi | Semua | Tinggi |
| Proyeksi | Tabel/chart historis + forecast | Semua | Tinggi |
| Insight Box | Ringkasan singkat dampak terhadap bisnis / konteks akademik | Akademis & Pebisnis | Tinggi |
| Download Data | Tombol unduh data dalam format CSV | Akademis | Sedang |
| Sumber Data | Footer dengan sumber + last updated | Semua | Tinggi |
| Responsive | Tampilan baik di desktop dan mobile | Semua | Sedang |

## 6. Sumber Data

| Indikator | Sumber Utama | Alternatif | Catatan |
|-----------|--------------|------------|--------|
| PDB Growth | World Bank API (`NY.GDP.MKTP.KD.ZG`) | BPS | Gratis, tanpa API key |
| Inflasi | World Bank API (`FP.CPI.TOTL.ZG`) | BPS | Gratis, tanpa API key |
| Neraca Perdagangan | World Bank API | BPS | Bisa gunakan ekspor-impor |
| Proyeksi | IMF WEO / DataMapper | - | Bisa hardcode dulu atau fetch berkala |

**Catatan Teknis:**
- World Bank API tidak memerlukan API key.
- Data disimpan lokal (SQLite).
- Update setiap 6–12 jam.

## 7. Layout Dashboard

```
Header
└── Judul: Indonesia Economic Dashboard
└── Subtitle: Data Makro untuk Akademisi & Pebisnis

KPI Cards (3 kolom)
├── PDB Growth (nilai + perubahan + status)
├── Inflasi (nilai + perubahan + status vs target BI)
└── Trade Balance (nilai + perubahan)

Insight Box (di bawah KPI)
└── 2–3 kalimat singkat: dampak terhadap bisnis + konteks akademik

Grafik Utama
└── Line Chart 5 Tahun (PDB Growth + Inflasi)

Detail Charts (2 kolom)
├── PDB Growth (Detail)
└── Inflasi (YoY)

Proyeksi
└── Tabel (Historis + Forecast) + catatan singkat

Footer
├── Sumber Data (World Bank, IMF, BPS)
├── Last Updated
└── Tombol Download CSV
```

## 8. Contoh Insight Box

**Contoh konten Insight:**
- “Pertumbuhan PDB sebesar 5,1% menunjukkan perekonomian masih solid. Bagi pebisnis, kondisi ini mendukung ekspansi pasar domestik. Bagi akademisi, data ini dapat digunakan untuk analisis siklus bisnis Indonesia.”
- “Inflasi berada di kisaran target BI. Ini memberikan ruang bagi Bank Indonesia untuk menjaga kebijakan moneter yang akomodatif.”

## 9. Kebutuhan Teknis

### Backend
- **Framework:** Flask
- **Database:** SQLite
- **Scheduler:** APScheduler
- **HTTP Client:** `requests`
- **Data Processing:** `pandas`

### Frontend
- HTML + CSS (Bootstrap atau Tailwind)
- Chart: Plotly (disarankan)
- Template: Jinja2

### Struktur Folder
```
project/
├── app.py
├── models.py
├── data_fetcher.py
├── scheduler.py
├── templates/
│   └── dashboard.html
├── static/
│   └── style.css
├── requirements.txt
└── README.md
```

## 10. Alur Auto-Update

1. Scheduler aktif saat aplikasi dijalankan.
2. Setiap 6–12 jam, data diambil dari World Bank API.
3. Data disimpan di SQLite.
4. Dashboard membaca dari database lokal.
5. Tampilkan “Last Updated” di footer.

## 11. Non-Functional Requirements

- Waktu load < 2 detik.
- Error handling jika API gagal (gunakan data terakhir).
- Kode bersih dan mudah dimaintain.
- Ada `requirements.txt` dan instruksi di README.

## 12. Acceptance Criteria

- [ ] Dashboard menampilkan 3 KPI cards dengan data terkini.
- [ ] Ada grafik 5 tahun untuk PDB Growth dan Inflasi.
- [ ] Ada bagian proyeksi.
- [ ] Ada Insight Box yang relevan untuk akademis dan pebisnis.
- [ ] Data di-update otomatis.
- [ ] Sumber data dan last updated tercantum.
- [ ] Ada tombol download data (CSV).
- [ ] Aplikasi bisa dijalankan dengan `flask run` atau `python app.py`.

---

**Catatan untuk Agent:**  
Fokus pada kesederhanaan, kejelasan sumber data, dan insight yang berguna bagi mahasiswa serta pebisnis. Prioritaskan World Bank API untuk data historis. Untuk proyeksi, hardcode dari data IMF terbaru jika API lebih rumit.
