# Task Plan — Enhancement Insight Dashboard

**Goal:** Perkuat insight box dashboard dengan 4 enhancement:
1. Inflasi granular: 3 kondisi (<2%, 2-4%, >4%)
2. PDB Growth: konteks tren (naik/turun/melambat)
3. Trade Balance: bedakan surplus besar/kecil + YoY
4. Kombinasi kondisi (opsional): growth+inflasi → kesimpulan makro

**Fase:**
| # | Fase | Owner | Status |
|---|------|-------|--------|
| 1 | Baca kode insight existing | ketua_agen | complete |
| 2 | Implementasi 4 enhancement | ketua_agen | complete |
| 3 | Update test_insight_dynamic.py | ketua_agen | complete |
| 4 | Jalankan semua test | ketua_agen | complete — 21/21 PASS |
| 5 | Verifikasi live | ketua_agen | complete — commit 49cf2a6 pushed |

**Aturan khusus:**
- JANGAN commit sebelum user test
- Test harus cover SEMUA branch kondisi

**Hasil test:**
- test_insight_dynamic.py: 21/21 PASS (21 skenario unik)
- test_kpi_units.py: 17/17 PASS
- verify_acceptance.py: 15/15 PASS
