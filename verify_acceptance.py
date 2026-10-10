"""Verifikasi independen acceptance criteria PRD §12 — bukan self-report.

Dijalankan oleh ketua_agen terhadap app yang benar-benar hidup di :5000.
"""
import re
import csv
import io
import os
import requests

BASE = "http://127.0.0.1:5000"
results = []


def check(name, ok, detail):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")


# --- Ambil halaman dashboard ---
r = requests.get(BASE + "/", timeout=30)
html = r.text
check("Halaman dashboard HTTP 200", r.status_code == 200, f"status={r.status_code}, bytes={len(html)}")

# AC1: 3 KPI cards dengan data terkini
kpi_cards = html.count("kpi-card")
kpi_values = re.findall(r'class="kpi-value">([^<]+)<', html)
check("AC1 3 KPI cards", len(kpi_values) == 3, f"values={kpi_values}")
check("AC1 KPI ada nilai nyata", all(v.strip() and v.strip() != "-" for v in kpi_values), f"{kpi_values}")

# AC2: grafik 5 tahun PDB + Inflasi (Plotly)
n_plotly = html.count("plotly-graph-div") // 2  # plotly emits class twice per div
plotly_ids = re.findall(r'id="([0-9a-f-]{30,})"', html)
check("AC2 3 Plotly chart", html.count("Plotly.newPlot") >= 3,
      f"newPlot calls={html.count('Plotly.newPlot')}, graph divs~={n_plotly}")
check("AC2 chart punya data 5 tahun",
      all(y in html for y in ["2021", "2022", "2023", "2024", "2025"]),
      "tahun 2021-2025 ada di payload chart")
check("AC2 kedua indikator di chart utama",
      "PDB Growth (%)" in html and "Inflasi (%)" in html,
      "trace PDB Growth + Inflasi ada")

# AC3: proyeksi
has_proj = ("Proyeksi" in html) and ("2027" in html)
check("AC3 bagian proyeksi", has_proj, "kata 'Proyeksi' + tahun forecast 2027 ada" if has_proj else "tidak ada")

# AC4: insight box
insight_match = re.search(r'Insight:</strong>\s*(.*?)</div>', html, re.S)
insight_text = re.sub(r"<[^>]+>", "", insight_match.group(1)).strip() if insight_match else ""
n_sent = insight_text.count(".")
check("AC4 insight box relevan", bool(insight_text) and n_sent >= 2,
      f"{n_sent} kalimat; cuplikan={insight_text[:90]}...")

# AC5: auto-update — scheduler thread aktif, cek log proses nyata
import subprocess
pid_out = subprocess.run(["pgrep", "-f", "python3 app.py"], capture_output=True, text=True).stdout.split()
pid = pid_out[0] if pid_out else None
n_threads = 0
if pid:
    try:
        n_threads = len(os.listdir(f"/proc/{pid}/task"))
    except Exception:
        n_threads = 0
log = ""
try:
    with open("/tmp/ied_sched.log") as f:
        log = f.read()
except Exception:
    pass
has_sched = "Scheduler" in log or n_threads >= 2
check("AC5 auto-update scheduler aktif", has_sched,
      f"pid={pid}, threads={n_threads} (main + scheduler), log_has_Scheduler={'Scheduler' in log}")

# AC6: sumber data + last updated
has_src = "World Bank" in html
has_upd = "Last Updated" in html or "last_updated" in html or "Terakhir" in html
check("AC6 sumber data", has_src, "World Bank disebut di halaman")
check("AC6 last updated", has_upd, re.search(r'(?:Last Updated|Terakhir)[^<]*', html).group(0)[:80] if has_upd else "tidak ada")

# AC7: tombol download CSV
has_btn = "/download/csv" in html
check("AC7 tombol CSV ada di halaman", has_btn, "link /download/csv ditemukan")

r2 = requests.get(BASE + "/download/csv", timeout=30)
rows = list(csv.reader(io.StringIO(r2.text)))
header = rows[0] if rows else []
data_rows = rows[1:]
codes = {row[1] for row in data_rows if len(row) > 1}
check("AC7 CSV download berfungsi", r2.status_code == 200 and len(data_rows) > 0,
      f"status={r2.status_code}, rows={len(data_rows)}, header={header}")
check("AC7 CSV punya 3 indikator", len(codes) == 3, f"codes={sorted(codes)}")

# AC8: app jalan via python app.py
check("AC8 app jalan (python app.py)", r.status_code == 200, "server merespons di :5000")

print("\n" + "=" * 60)
passed = sum(1 for _, ok, _ in results if ok)
print(f"TOTAL: {passed}/{len(results)} PASS")
for name, ok, _ in results:
    if not ok:
        print(f"  GAGAL: {name}")
