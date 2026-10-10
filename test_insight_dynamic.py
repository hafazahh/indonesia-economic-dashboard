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


def make(pdb, inf, trd, year=2025):
    def latest(code, v):
        return {code: {"name": code, "data": [], "latest": {"value": v, "year": year}}}
    d = {}
    d.update(latest(GDP, pdb))
    d.update(latest(INF, inf))
    d.update(latest(TRD, trd))
    return d


scenarios = [
    ("Data sekarang (nyata 2025)", make(5.108, 1.913, 29649335679.15)),
    ("PDB turun ke 3.2% (lemah)",  make(3.2, 1.913, 29649335679.15)),
    ("Inflasi naik ke 6.5% (tinggi)", make(5.108, 6.5, 29649335679.15)),
    ("Trade balance defisit",      make(5.108, 1.913, -12500000000.0)),
    ("Semua indikator memburuk",   make(2.0, 8.0, -5000000000.0)),
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
base = texts[0]
checks = [
    ("PDB 3.2% memicu frasa 'tumbuh moderat'", "tumbuh moderat" in texts[1]),
    ("PDB 5.1% memicu frasa 'masih solid'", "masih solid" in texts[0]),
    ("Inflasi 6.5% memicu 'di luar target BI'", "di luar target BI" in texts[2]),
    ("Inflasi 1.9% memicu 'dalam target BI'", "dalam target BI" in texts[0]),
    ("Trade negatif memicu 'defisit'", "defisit" in texts[3]),
    ("Trade positif memicu 'surplus'", "surplus" in texts[0]),
    ("Angka tahun ikut tampil", "(2025)" in texts[0]),
    ("Angka nilai ikut tampil", "5.1%" in texts[0] and "1.9%" in texts[0]),
    # Konsistensi kesimpulan dengan data (bug yang ditemukan lewat test ini)
    ("Inflasi tinggi -> 'lebih ketat', bukan 'akomodatif'",
     "lebih ketat" in texts[2] and "akomodatif" not in texts[2]),
    ("Inflasi dalam target -> 'akomodatif'",
     "akomodatif" in texts[0]),
    ("PDB lemah -> tidak klaim 'ekspansi pasar domestik'",
     "ekspansi pasar domestik" not in texts[1]),
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
