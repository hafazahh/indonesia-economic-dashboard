"""Main Flask application for Indonesia Economic Dashboard."""
import csv
import io
import os
import sys
from datetime import datetime
from flask import Flask, render_template, Response

sys.path.insert(0, os.path.dirname(__file__))
from models import init_db, get_all_data, get_last_updated, count_rows
from data_fetcher import fetch_all
from scheduler import start_scheduler, stop_scheduler, scheduler_running

app = Flask(__name__)

# Indicator codes. Defined once so a typo cannot silently desynchronise the
# formatting logic from the fetch/schema logic.
GDP_GROWTH_CODE = "NY.GDP.MKTP.KD.ZG"
INFLATION_CODE = "FP.CPI.TOTL.ZG"
TRADE_BALANCE_CODE = "BN.GSR.GNFS.CD"


def format_value(code, value):
    """Format an indicator value with its correct unit."""
    if code == TRADE_BALANCE_CODE:
        # Trade balance is stored in USD; display in billions USD
        return f"{value / 1e9:.1f} miliar USD"
    return f"{value:.2f}%"


def format_change(code, change):
    """Format the year-over-year change with the indicator's own unit.

    Percentage indicators change in percentage points ("pp"); the trade balance
    changes in USD, so it must be shown as an absolute amount. Labelling a USD
    delta as "pp" produces nonsense like "+8295823081.86 pp".
    """
    if code == TRADE_BALANCE_CODE:
        return f"{abs(change) / 1e9:.1f} miliar USD"
    return f"{abs(change):.2f} pp"


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
        arrow = "+" if change > 0 else ("-" if change < 0 else "")
        change_badge = "bg-success" if change >= 0 else "bg-danger"
        if code == "FP.CPI.TOTL.ZG":
            # Inflation: 3 granular conditions
            if latest["value"] < 2.0:
                status = "Di bawah target BI"
                status_badge = "bg-info"
            elif latest["value"] <= 4.0:
                status = "Dalam target BI"
                status_badge = "bg-success"
            else:
                status = "Di atas target BI"
                status_badge = "bg-danger"
            change_badge = "bg-danger" if change > 0 else "bg-success"
        else:
            status = None
            status_badge = None
        # With fewer than two data points there is no meaningful YoY change.
        has_prev = prev is not None
        kpis.append({
            "code": code,
            "name": info["name"],
            "formatted_value": format_value(code, latest["value"]),
            "formatted_change": format_change(code, change) if has_prev else "Data tidak cukup",
            "change_arrow": arrow if has_prev else "",
            "change_badge_class": change_badge if has_prev else "bg-secondary",
            "status": status,
            "status_badge_class": status_badge,
        })
    return kpis


def generate_insight(data):
    """Generate insight text from the latest data.

    Recomputed on every request from whatever is in the database, so the text
    follows the data automatically after each scheduled refresh.
    """
    pdb_info = data.get(GDP_GROWTH_CODE, {})
    inflasi_info = data.get(INFLATION_CODE, {})
    trade_info = data.get(TRADE_BALANCE_CODE, {})

    pdb = pdb_info.get("latest")
    inflasi = inflasi_info.get("latest")
    trade = trade_info.get("latest")

    # Previous-year rows for trend analysis (data is ordered year DESC).
    pdb_rows = pdb_info.get("data", [])
    inflasi_rows = inflasi_info.get("data", [])
    trade_rows = trade_info.get("data", [])

    pdb_prev = pdb_rows[1] if len(pdb_rows) > 1 else None
    inflasi_prev = inflasi_rows[1] if len(inflasi_rows) > 1 else None
    trade_prev = trade_rows[1] if len(trade_rows) > 1 else None

    parts = []

    # 1. PDB Growth — dengan konteks tren YoY
    if pdb:
        val = pdb["value"]
        if pdb_prev:
            change = val - pdb_prev["value"]
            if change > 0:
                trend = "solid dan membaik"
            elif val >= 5.0:
                trend = "masih solid meskipun melambat"
            elif val >= 4.5:
                trend = "melambat"
            else:
                trend = "moderat"
        else:
            trend = "solid" if val >= 5.0 else "moderat"

        parts.append(
            f"Pertumbuhan PDB {val:.1f}% ({pdb['year']}) menunjukkan "
            f"perekonomian Indonesia {trend}. "
            f"Bagi pebisnis, kondisi ini "
            f"{'mendukung ekspansi pasar domestik' if val >= 5.0 else 'mendorong kehati-hatian dalam ekspansi'}."
        )

    # 2. Inflasi — 3 kondisi granular
    if inflasi:
        val = inflasi["value"]
        if val < 2.0:
            kondisi = "di bawah target BI (2-4%), memberi ruang kebijakan moneter yang akomodatif"
        elif val <= 4.0:
            kondisi = "berada dalam target BI (2-4%)"
        else:
            kondisi = "di atas target BI (2-4%), menekan ruang kebijakan moneter"

        parts.append(
            f"Inflasi {val:.1f}% ({inflasi['year']}) {kondisi}."
        )

    # 3. Trade Balance — magnitude + YoY trend
    if trade:
        val = trade["value"]
        surplus = val > 0
        magnitude = abs(val) / 1e9

        if surplus:
            if magnitude >= 20:
                desc = "surplus besar"
            elif magnitude >= 10:
                desc = "surplus moderat"
            else:
                desc = "surplus kecil"
        else:
            if magnitude >= 20:
                desc = "defisit besar"
            elif magnitude >= 10:
                desc = "defisit moderat"
            else:
                desc = "defisit kecil"

        # YoY trend
        yoy_text = ""
        if trade_prev:
            prev_val = trade_prev["value"]
            if surplus and prev_val > 0:
                if val > prev_val:
                    yoy_text = ", surplus melebar"
                else:
                    yoy_text = ", surplus menyempit"
            elif not surplus and prev_val < 0:
                if val < prev_val:
                    yoy_text = ", defisit melebar"
                else:
                    yoy_text = ", defisit menyempit"
            elif surplus and prev_val <= 0:
                yoy_text = ", berubah dari defisit"
            elif not surplus and prev_val >= 0:
                yoy_text = ", berubah dari surplus"

        parts.append(
            f"Neraca perdagangan mencatat {desc} "
            f"{magnitude:.1f} miliar USD ({trade['year']}){yoy_text}, "
            f"mencerminkan {'kinerja ekspor yang kuat' if surplus else 'tekanan pada sektor perdagangan'}."
        )

    # 4. Kombinasi kondisi makro
    if pdb and inflasi:
        pdb_val = pdb["value"]
        inf_val = inflasi["value"]
        if pdb_val >= 5.0 and inf_val < 2.0:
            parts.append("Kombinasi pertumbuhan tinggi dan inflasi rendah menciptakan kondisi makro yang mendukung ekspansi.")
        elif pdb_val < 4.5 and inf_val > 4.0:
            parts.append("Pertumbuhan yang melambat dengan inflasi tinggi memerlukan kehati-hatian dalam pengambilan keputusan.")

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
    pdb_rows = sorted(data[GDP_GROWTH_CODE]["data"], key=lambda r: r["year"])
    inflasi_rows = sorted(data[INFLATION_CODE]["data"], key=lambda r: r["year"])
    years = [r["year"] for r in pdb_rows]
    pdb_values = [r["value"] for r in pdb_rows]
    inflasi_values = [r["value"] for r in inflasi_rows]

    # If the World Bank API was unreachable at boot the DB is empty. Say so
    # explicitly instead of rendering blank cards with no explanation.
    data_unavailable = not kpis
    if data_unavailable:
        insight = (
            "Data belum tersedia. Sumber World Bank API tidak dapat dihubungi saat "
            "aplikasi dijalankan. Data akan dimuat otomatis pada pembaruan berikutnya "
            "(setiap 6 jam)."
        )

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
        data_unavailable=data_unavailable,
    )


def _csv_safe(value):
    """Neutralise spreadsheet formula injection.

    Excel/Sheets treat a cell starting with = + - @ as a formula. Prefixing with
    an apostrophe keeps the value as text. Values here come from the World Bank
    API (numbers), so this is defence in depth rather than a live hole.
    """
    text = "" if value is None else str(value)
    if text[:1] in ("=", "+", "-", "@"):
        return "'" + text
    return text


@app.route("/download/csv")
def download_csv():
    data = get_all_data()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Indicator", "Code", "Year", "Value", "Fetched At"])
    for code, info in data.items():
        for row in info["data"]:
            writer.writerow([
                _csv_safe(info["name"]),
                _csv_safe(code),
                row["year"],
                row["value"],
                _csv_safe(row["fetched_at"]),
            ])
    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=indonesia_economic_data.csv"},
    )


@app.route("/health")
@app.route("/healthz")
def health():
    """Health check. Reports scheduler state so a deploy can be verified.

    Served at both /health and /healthz: Render's default Health Check Path is
    /healthz, and a 404 there makes Render treat the deploy as failed.
    """
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "scheduler_running": scheduler_running(),
        "rows_stored": count_rows(),
    }


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
