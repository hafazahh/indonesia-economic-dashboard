"""Buktikan insight berubah otomatis saat data berubah.
Menjalankan generate_insight() dengan beberapa skenario data dan membandingkan
teks yang dihasilkan. Kalau teksnya ikut berubah, berarti insight dinamis.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import app as appmod

GDP = "NY.GDP.MKTP.KD.ZG"
INF = "FP.CPI.TOTL.ZG"
TRD = "BN.GSR.GNFS.CD"


def make(pdb, inf, trd, year=2025, pdb_prev=None, inf_prev=None, trd_prev=None):
    def latest(code, v, prev_v=None):
        # Order DESC by year (matches get_indicator_data SQL ORDER BY year DESC)
        data = [{"value": v, "year": year}]
        if prev_v is not None:
            data.append({"value": prev_v, "year": year - 1})
        return {code: {"name": code, "data": data, "latest": {"value": v, "year": year}}}
    d = {}
    d.update(latest(GDP, pdb, pdb_prev))
    d.update(latest(INF, inf, inf_prev))
    d.update(latest(TRD, trd, trd_prev))
    return d


scenarios = [
    ("Data sekarang (nyata 2025)", make(5.108, 1.913, 29649335679.15, pdb_prev=4.9, inf_prev=2.5, trd_prev=25000000000.0)),
    ("PDB naik (membaik)",       make(5.5, 1.913, 29649335679.15, pdb_prev=4.9)),
    ("PDB turun tapi >=5%",       make(5.1, 1.913, 29649335679.15, pdb_prev=5.5)),
    ("PDB 4.5-5% (melambat)",    make(4.7, 1.913, 29649335679.15, pdb_prev=5.0)),
    ("PDB <4.5% (moderat)",      make(3.2, 1.913, 29649335679.15, pdb_prev=4.0)),
    ("Inflasi <2% (bawah)",      make(5.108, 1.5, 29649335679.15)),
    ("Inflasi 2-4% (dalam)",     make(5.108, 3.0, 29649335679.15)),
    ("Inflasi >4% (atas)",       make(5.108, 6.5, 29649335679.15)),
    ("Trade surplus besar",      make(5.108, 1.913, 25000000000.0)),
    ("Trade surplus moderat",    make(5.108, 1.913, 15000000000.0)),
    ("Trade surplus kecil",      make(5.108, 1.913, 5000000000.0)),
    ("Trade defisit",            make(5.108, 1.913, -12500000000.0)),
    ("Trade surplus melebar",    make(5.108, 1.913, 30000000000.0, trd_prev=20000000000.0)),
    ("Trade surplus menyempit",  make(5.108, 1.913, 20000000000.0, trd_prev=30000000000.0)),
    ("Trade defisit melebar",    make(5.108, 1.913, -15000000000.0, trd_prev=-5000000000.0)),
    ("Trade defisit menyempit",  make(5.108, 1.913, -5000000000.0, trd_prev=-15000000000.0)),
    ("Trade berubah dari defisit", make(5.108, 1.913, 5000000000.0, trd_prev=-5000000000.0)),
    ("Trade berubah dari surplus", make(5.108, 1.913, -5000000000.0, trd_prev=5000000000.0)),
    ("Kombinasi: growth tinggi + inflasi rendah", make(5.5, 1.5, 29649335679.15)),
    ("Kombinasi: growth melambat + inflasi tinggi", make(4.0, 6.5, 29649335679.15)),
    ("Semua indikator memburuk", make(2.0, 8.0, -5000000000.0)),
]

print("=" * 78)
results = []
for name, data in scenarios:
    insight = appmod.generate_insight(data)
    results.append((name, insight))
    print(f"\n### {name}")
    print(insight)

print()
print("=" * 78)
print("ANALISIS")
print("=" * 78)

texts = [t for _, t in results]
unique = len(set(texts))

print(f"Skenario diuji           : {len(scenarios)}")
print(f"Teks insight unik        : {unique}")

# Cek frasa kunci ikut berubah
checks = [
    # PDB trend
    ("PDB naik -> 'solid dan membaik'", "solid dan membaik" in texts[1]),
    ("PDB turun >=5% -> 'masih solid meskipun melambat'", "masih solid meskipun melambat" in texts[2]),
    ("PDB 4.5-5% -> 'melambat'", "melambat" in texts[3]),
    ("PDB <4.5% -> 'moderat'", "moderat" in texts[4]),
    # Inflasi 3 kondisi
    ("Inflasi <2% -> 'di bawah target BI'", "di bawah target BI" in texts[5]),
    ("Inflasi <2% -> 'akomodatif'", "akomodatif" in texts[5]),
    ("Inflasi 2-4% -> 'dalam target BI'", "dalam target BI" in texts[6]),
    ("Inflasi >4% -> 'di atas target BI'", "di atas target BI" in texts[7]),
    ("Inflasi >4% -> 'menekan ruang'", "menekan ruang" in texts[7]),
    # Trade magnitude
    ("Surplus besar -> 'surplus besar'", "surplus besar" in texts[8]),
    ("Surplus moderat -> 'surplus moderat'", "surplus moderat" in texts[9]),
    ("Surplus kecil -> 'surplus kecil'", "surplus kecil" in texts[10]),
    ("Defisit -> 'defisit'", "defisit" in texts[11]),
    # Trade YoY
    ("Surplus melebar -> 'surplus melebar'", "surplus melebar" in texts[12]),
    ("Surplus menyempit -> 'surplus menyempit'", "surplus menyempit" in texts[13]),
    ("Defisit melebar -> 'defisit melebar'", "defisit melebar" in texts[14]),
    ("Defisit menyempit -> 'defisit menyempit'", "defisit menyempit" in texts[15]),
    ("Berubah dari defisit -> 'berubah dari defisit'", "berubah dari defisit" in texts[16]),
    ("Berubah dari surplus -> 'berubah dari surplus'", "berubah dari surplus" in texts[17]),
    # Kombinasi
    ("Growth tinggi + inflasi rendah -> 'mendukung ekspansi'", "mendukung ekspansi" in texts[18]),
    ("Growth melambat + inflasi tinggi -> 'kehati-hatian'", "kehati-hatian" in texts[19]),
    # Konsistensi
    ("Inflasi tinggi -> tidak klaim 'akomodatif'", "akomodatif" not in texts[7]),
    ("PDB lemah -> tidak klaim 'ekspansi pasar domestik'", "ekspansi pasar domestik" not in texts[4]),
    ("Angka tahun ikut tampil", "(2025)" in texts[0]),
    ("Angka nilai ikut tampil", "5.1%" in texts[0] and "1.9%" in texts[0]),
]

print()
allok = True
for label, ok in checks:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        allok = False

print()
if unique == len(scenarios) and allok:
    print("KESIMPULAN: insight DINAMIS — setiap perubahan data menghasilkan teks berbeda.")
else:
    print("KESIMPULAN: insight TIDAK sepenuhnya dinamis.")
    sys.exit(1)

# ---------- BPS inflation (bulanan) diprioritaskan ----------
print()
print("=" * 78)
print("TES BPS INFLASI (bulanan)")
print("=" * 78)

# Skenario: data World Bank inflasi 1.91% (2025), tapi BPS 3.28% (Sep 2026)
bps_data = make(5.108, 1.913, 29649335679.15, pdb_prev=4.9, inf_prev=2.5)
bps_infl = {"value": 3.28, "date": "2026-09-01"}

insight_wb = appmod.generate_insight(bps_data)
insight_bps = appmod.generate_insight(bps_data, bps_inflation=bps_infl)

print(f"\nTanpa BPS: {insight_wb}")
print(f"\nDengan BPS: {insight_bps}")

bps_checks = [
    ("BPS: teks berbeda dari World Bank", insight_wb != insight_bps),
    ("BPS: memakai nilai 3.28%", "3.28%" in insight_bps),
    ("BPS: memakai label BPS", "BPS" in insight_bps),
    ("BPS: memakai bulan September 2026", "September 2026" in insight_bps),
    ("BPS: status dalam target BI", "dalam target BI" in insight_bps),
    ("WB: memakai nilai 1.9%", "1.9%" in insight_wb),
    ("WB: memakai tahun 2025", "2025" in insight_wb),
]

bps_ok = True
for label, ok in bps_checks:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        bps_ok = False

# Skenario BPS di bawah target
bps_low = {"value": 1.20, "date": "2026-09-01"}
insight_low = appmod.generate_insight(bps_data, bps_inflation=bps_low)
print(f"\nBPS di bawah target: {insight_low}")
bps_checks2 = [
    ("BPS <1.5%: status di bawah target", "di bawah target BI" in insight_low),
    ("BPS <1.5%: akomodatif", "akomodatif" in insight_low),
]
for label, ok in bps_checks2:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        bps_ok = False

# Skenario BPS di atas target
bps_high = {"value": 5.50, "date": "2026-09-01"}
insight_high = appmod.generate_insight(bps_data, bps_inflation=bps_high)
print(f"\nBPS di atas target: {insight_high}")
bps_checks3 = [
    ("BPS >3.5%: status di atas target", "di atas target BI" in insight_high),
    ("BPS >3.5%: menekan ruang", "menekan ruang" in insight_high),
]
for label, ok in bps_checks3:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}")
    if not ok:
        bps_ok = False

print()
if bps_ok:
    print("KESIMPULAN: BPS inflation override bekerja dengan benar.")
else:
    print("KESIMPULAN: BPS inflation override GAGAL.")
    sys.exit(1)
