"""Main Flask application for Indonesia Economic Dashboard."""
import csv
import io
import os
import sys
from datetime import datetime
from flask import Flask, render_template, Response

sys.path.insert(0, os.path.dirname(__file__))
from models import init_db, get_all_data, get_last_updated
from data_fetcher import fetch_all
from scheduler import start_scheduler, stop_scheduler

app = Flask(__name__)


def format_value(code, value):
    """Format value for display."""
    if code == "BN.GSR.GNFS.CD":
        # Trade balance stored in USD; display in billions USD
        return f"{value / 1e9:.1f} miliar USD"
    return f"{value:.2f}%"


def compute_kpis(data):
    """Compute KPI cards from indicator data."""
    kpis = []
    for code, info in data.items():
        rows = info["data"]  # desc by year
        if not rows:
            continue
        latest = rows[0]
        prev = rows[1] if len(rows) > 1 else None
        change = latest["value"] - prev["value"] if prev else 0
        change_pct = abs(change)
        arrow = "+" if change > 0 else ("-" if change < 0 else "")
        change_badge = "bg-success" if change >= 0 else "bg-danger"
        if code == "FP.CPI.TOTL.ZG":
            # Inflation: lower is better (within target)
            if latest["value"] <= 4.0:
                status = "Dalam target BI"
                status_badge = "bg-success"
            else:
                status = "Di luar target BI"
                status_badge = "bg-danger"
            change_badge = "bg-danger" if change > 0 else "bg-success"
        else:
            status = None
            status_badge = None
        kpis.append({
            "code": code,
            "name": info["name"],
            "formatted_value": format_value(code, latest["value"]),
            "formatted_change": f"{change_pct:.2f} pp",
            "change_arrow": arrow,
            "change_badge_class": change_badge,
            "status": status,
            "status_badge_class": status_badge,
        })
    return kpis


def generate_insight(data):
    """Generate insight text from latest data."""
    pdb = data.get("NY.GDP.MKTP.KD.ZG", {}).get("latest")
    inflasi = data.get("FP.CPI.TOTL.ZG", {}).get("latest")
    trade = data.get("BN.GSR.GNFS.CD", {}).get("latest")
    parts = []
    if pdb:
        parts.append(f"Pertumbuhan PDB {pdb['value']:.1f}% ({pdb['year']}) menunjukkan perekonomian Indonesia {'masih solid' if pdb['value'] >= 5 else 'tumbuh moderat'}. Bagi pebisnis, kondisi ini {'mendukung ekspansi pasar domestik' if pdb['value'] >= 5 else 'menjaga stabilitas pasar'}.")
    if inflasi:
        parts.append(f"Inflasi {inflasi['value']:.1f}% ({inflasi['year']}) {'berada dalam target BI (2-4%)' if inflasi['value'] <= 4 else 'di luar target BI'}, memberikan ruang bagi kebijakan moneter yang stabil.")
    if trade:
        status = "surplus" if trade["value"] > 0 else "defisit"
        parts.append(f"Neraca perdagangan mencatat {status} {abs(trade['value']) / 1e9:.1f} miliar USD ({trade['year']}), mencerminkan {'kinerja ekspor yang kuat' if trade['value'] > 0 else 'tekanan pada sektor perdagangan'}.")
    return " ".join(parts)


# IMF WEO hardcoded projection (April 2026 WEO for Indonesia)
PROJECTION = [
    {"year": 2024, "pdb": 5.0, "inflasi": 2.5},
    {"year": 2025, "pdb": 5.1, "inflasi": 1.9},
    {"year": 2026, "pdb": 5.2, "inflasi": 2.3},
    {"year": 2027, "pdb": 5.3, "inflasi": 2.5},
]


def _base_layout():
    """Shared Plotly layout: clean, readable for non-experts."""
    return dict(
        margin=dict(l=50, r=20, t=20, b=40),
        height=320,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )


def build_main_chart(years, pdb_values, inflasi_values):
    """Combined 5-year line chart: PDB Growth + Inflasi (PRD §7)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years, y=pdb_values, mode="lines+markers", name="PDB Growth (%)",
        line=dict(color="#0d6efd", width=3), marker=dict(size=8),
    ))
    fig.add_trace(go.Scatter(
        x=years, y=inflasi_values, mode="lines+markers", name="Inflasi (%)",
        line=dict(color="#dc3545", width=3), marker=dict(size=8),
    ))
    fig.update_layout(**_base_layout())
    fig.update_xaxes(title_text="Tahun", showgrid=False)
    fig.update_yaxes(title_text="Persen (%)", gridcolor="#e9ecef", zeroline=True)
    return fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})


def build_single_chart(years, values, label, color):
    """Single-indicator line chart for the detail section (PRD §7)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years, y=values, mode="lines+markers", name=label,
        line=dict(color=color, width=3), marker=dict(size=8),
        fill="tozeroy", fillcolor="rgba(13,110,253,0.08)" if color == "#0d6efd" else "rgba(220,53,69,0.08)",
    ))
    fig.update_layout(**_base_layout())
    fig.update_xaxes(title_text="Tahun", showgrid=False)
    fig.update_yaxes(title_text="Persen (%)", gridcolor="#e9ecef", zeroline=True)
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


@app.route("/")
def dashboard():
    data = get_all_data()
    kpis = compute_kpis(data)
    insight = generate_insight(data)
    last_updated = get_last_updated() or "Belum pernah update"

    # Chart data: 5 years ascending
    pdb_rows = sorted(data["NY.GDP.MKTP.KD.ZG"]["data"], key=lambda r: r["year"])
    inflasi_rows = sorted(data["FP.CPI.TOTL.ZG"]["data"], key=lambda r: r["year"])
    years = [r["year"] for r in pdb_rows]
    pdb_values = [r["value"] for r in pdb_rows]
    inflasi_values = [r["value"] for r in inflasi_rows]

    # Plotly charts (PRD §9). Built server-side, embedded as inline HTML.
    main_chart = build_main_chart(years, pdb_values, inflasi_values)
    pdb_chart = build_single_chart(years, pdb_values, "PDB Growth (%)", "#0d6efd")
    inflasi_chart = build_single_chart(years, inflasi_values, "Inflasi YoY (%)", "#dc3545")

    return render_template(
        "dashboard.html",
        kpis=kpis,
        insight=insight,
        last_updated=last_updated,
        projection=PROJECTION,
        main_chart=main_chart,
        pdb_chart=pdb_chart,
        inflasi_chart=inflasi_chart,
    )


@app.route("/download/csv")
def download_csv():
    data = get_all_data()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Indicator", "Code", "Year", "Value", "Fetched At"])
    for code, info in data.items():
        for row in info["data"]:
            writer.writerow([info["name"], code, row["year"], row["value"], row["fetched_at"]])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=indonesia_economic_data.csv"},
    )


@app.route("/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


def bootstrap():
    """Initialise DB, load data if empty, and start the scheduler.

    Must run under BOTH `python app.py` and `gunicorn app:app` — on Render the
    app is imported by gunicorn, so anything inside `if __name__ == "__main__"`
    would never execute and the dashboard would serve an empty database.
    """
    init_db()
    # Only fetch when the DB is empty: Render's free tier restarts often and a
    # blocking network call on every import would delay startup for no benefit.
    try:
        existing = get_all_data()
        has_data = any(info["data"] for info in existing.values())
    except Exception as exc:
        print(f"[Bootstrap] DB read failed ({exc}); fetching fresh")
        has_data = False
    if not has_data:
        fetch_all()
    start_scheduler()


bootstrap()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        stop_scheduler()
