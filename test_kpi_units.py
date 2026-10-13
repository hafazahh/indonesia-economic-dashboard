"""Test untuk bug unit KPI + perbaikan dari code review.

Fokus: membuktikan "+8295823081.86 pp" tidak bisa terjadi lagi, dan bahwa
perbaikan review (try/finally, CSV safe, data kosong) benar-benar bekerja.
"""
import os
import sys
import csv
import io

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

failures = []


def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    print(f"[{status}] {name}" + (f": {detail}" if detail else ""))
    if not cond:
        failures.append(name)


# ---------- Bug utama: unit salah pada perubahan Trade Balance ----------
import app as appmod

TRADE = "BN.GSR.GNFS.CD"
INFLASI = "FP.CPI.TOTL.ZG"
PDB = "NY.GDP.MKTP.KD.ZG"

# Nilai nyata dari World Bank: trade balance 2025 vs 2024 (USD)
tb_now, tb_prev = 29649335679.1509, 21353512597.294
data = {
    TRADE: {"name": "Trade Balance", "data": [
        {"value": tb_now, "year": 2025},
        {"value": tb_prev, "year": 2024},
    ], "latest": {"value": tb_now, "year": 2025}},
    INFLASI: {"name": "Inflasi", "data": [
        {"value": 1.91333443295079, "year": 2025},
        {"value": 2.18151273615188, "year": 2024},
    ], "latest": {"value": 1.91333443295079, "year": 2025}},
    PDB: {"name": "PDB Growth", "data": [
        {"value": 5.10808904438025, "year": 2025},
        {"value": 5.03257477088519, "year": 2024},
    ], "latest": {"value": 5.10808904438025, "year": 2025}},
}

kpis = {k["code"]: k for k in appmod.compute_kpis(data)}

tb_change = kpis[TRADE]["formatted_change"]
check("Trade Balance TIDAK memakai satuan 'pp'", "pp" not in tb_change, f"='{tb_change}'")
check("Trade Balance perubahan dalam miliar USD", "miliar USD" in tb_change, f"='{tb_change}'")

# Nilai benar: (29649335679.1509 - 21353512597.294) / 1e9 = 8.3
expected = f"{abs(tb_now - tb_prev) / 1e9:.1f} miliar USD"
check("Trade Balance nilai perubahan benar", tb_change == expected,
      f"dapat='{tb_change}' harus='{expected}'")

# INFLASI (World Bank) HARUS dihapus dari compute_kpis — BPS card ditambah di dashboard()
check("Inflasi World Bank TIDAK di compute_kpis", INFLASI not in kpis,
      f"codes={list(kpis.keys())}")
check("PDB tetap pakai 'pp'", "pp" in kpis[PDB]["formatted_change"],
      f"='{kpis[PDB]['formatted_change']}'")

# Semua card non-inflasi punya comparison_label 'vs tahun lalu'
for code, kpi in kpis.items():
    check(f"Card {code} punya comparison_label", kpi.get("comparison_label") == "vs tahun lalu",
          f"='{kpi.get('comparison_label')}'")

# Angka absurd tidak boleh muncul lagi
check("Tidak ada angka mentah USD di label perubahan",
      "8295823081" not in tb_change, f"='{tb_change}'")

# ---------- S3: data kurang dari 2 baris ----------
data_one = {PDB: {"name": "PDB Growth", "data": [
    {"value": 5.1, "year": 2025}], "latest": {"value": 5.1, "year": 2025}}}
k_one = appmod.compute_kpis(data_one)[0]
check("Satu baris data -> 'Data tidak cukup'", k_one["formatted_change"] == "Data tidak cukup",
      f"='{k_one['formatted_change']}'")
check("Satu baris data -> arrow kosong", k_one["change_arrow"] == "", f"='{k_one['change_arrow']}'")

# ---------- W1: koneksi tidak bocor saat exception ----------
import models
import sqlite3

conn = models.get_db()
conn.close()

leaked = False
try:
    with models.db() as c:
        c.execute("SELECT * FROM tabel_yang_tidak_ada")
except sqlite3.OperationalError:
    pass
# Kalau context manager benar, tidak ada koneksi menggantung. Uji dengan
# memastikan kita masih bisa membuka koneksi baru berkali-kali tanpa error.
try:
    for _ in range(60):
        with models.db() as c:
            c.execute("SELECT 1")
    check("W1: 60 koneksi berturut-turut tanpa kebocoran", True)
except Exception as e:
    check("W1: 60 koneksi berturut-turut tanpa kebocoran", False, str(e))

# ---------- W3: CSV injection ----------
cases = [
    ("=CMD|' /C calc'!A0", True),
    ("+1234567890", True),
    ("-1+2", True),
    ("@SUM(A1)", True),
    ("PDB Growth", False),
    ("5.10808904438025", False),
]
for raw, should_quote in cases:
    out = appmod._csv_safe(raw)
    quoted = out.startswith("'")
    check(f"W3 CSV safe: {raw[:18]!r} -> quoted={quoted}", quoted == should_quote, f"='{out}'")

# ---------- W2: dashboard dengan data kosong ----------
from flask import render_template
with appmod.app.test_request_context("/"):
    html = render_template(
        "dashboard.html",
        kpis=[], insight="x", last_updated="x", projection=[],
        main_chart="", pdb_chart="", inflasi_chart="", data_unavailable=True,
    )
    check("W2: template menampilkan peringatan data kosong",
          "Data belum tersedia" in html, "alert alert-warning ada")
    check("W2: template tanpa peringatan saat data ada",
          "Data belum tersedia" not in render_template(
              "dashboard.html", kpis=[], insight="x", last_updated="x",
              projection=[], main_chart="", pdb_chart="", inflasi_chart="",
              data_unavailable=False))

print()
print("=" * 60)
if failures:
    print(f"GAGAL: {len(failures)} test")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("SEMUA TEST LULUS")
