"""Main Flask application for Indonesia Economic Dashboard."""
import csv
import io
import os
import re
import secrets
import sys
from datetime import datetime
from flask import Flask, Response, g, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

sys.path.insert(0, os.path.dirname(__file__))
from models import (
    init_db, get_all_data, get_last_updated, count_rows,
    get_series, get_latest_series, get_series_metadata,
    get_indicator_last_updated, get_series_last_updated,
)
from data_fetcher import fetch_all
from macro_fetcher import (
    fetch_all_macro,
    fetch_inflation_yoy,
    BI_TARGET_LOW,
    BI_TARGET_HIGH,
    BI_TARGET_CENTER,
)
from micro_fetcher import fetch_all_micro, UMP_PROVINSI, BBM_PER_DAERAH
from backfill import run as backfill_run
from scheduler import start_scheduler, stop_scheduler, scheduler_running

app = Flask(__name__)

# Render terminates TLS and forwards to gunicorn over plain HTTP, so without
# ProxyFix request.is_secure is always False and the HSTS branch in
# apply_security_headers() would silently never fire. The =1 values mean
# "trust exactly one proxy hop" — raising them lets a client spoof the header.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# --- Security headers -------------------------------------------------------
#
# Graded by securityheaders.com. HSTS is sent over HTTPS only: sending it on a
# plain-HTTP response can pin a browser to a scheme the host does not serve.
# 'preload' is deliberately omitted — it is effectively irreversible and an
# owner decision, not a sensible default.
HSTS_VALUE = "max-age=31536000; includeSubDomains"

# Third-party origins this dashboard genuinely loads: Plotly's runtime from the
# plot.ly CDN, Bootstrap's stylesheet from jsDelivr. Nothing else is allowed.
PLOTLY_CDN = "https://cdn.plot.ly"
BOOTSTRAP_CDN = "https://cdn.jsdelivr.net"

PERMISSIONS_POLICY = ", ".join([
    "accelerometer=()", "autoplay=()", "camera=()", "geolocation=()",
    "gyroscope=()", "magnetometer=()", "microphone=()", "payment=()", "usb=()",
])

# Inline <script> blocks only. A tag carrying src= is covered by the host
# allowlist in script-src instead.
_INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*\bnonce=)", re.I)


def build_csp(nonce):
    """CSP for this response, allowing inline scripts only via this nonce.

    Plotly's to_html() emits inline blocks, so script-src cannot be a bare
    'self' — but a per-response nonce keeps 'unsafe-inline' out of the policy,
    which is what separates grade A from A+.
    """
    return "; ".join([
        "default-src 'self'",
        f"script-src 'nonce-{nonce}' {PLOTLY_CDN}",
        f"style-src 'self' 'unsafe-inline' {BOOTSTRAP_CDN}",
        f"font-src 'self' data: {BOOTSTRAP_CDN}",
        "img-src 'self' data:",
        "connect-src 'self'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "object-src 'none'",
        "form-action 'self'",
    ])


def apply_nonce(html, nonce):
    """Stamp every inline <script> in a rendered fragment with the CSP nonce.

    Without this the charts are blocked in every real browser while curl still
    sees a 200 — the failure is invisible outside a browser.
    """
    return _INLINE_SCRIPT_RE.sub(f'<script nonce="{nonce}"', html)


@app.before_request
def issue_csp_nonce():
    """A fresh nonce per response. A reused nonce is as good as 'unsafe-inline'."""
    g.csp_nonce = secrets.token_urlsafe(16)


@app.after_request
def apply_security_headers(response):
    """Attach the security header set to every response, HTML or not."""
    nonce = getattr(g, "csp_nonce", None)
    if nonce:
        response.headers.setdefault("Content-Security-Policy", build_csp(nonce))
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", PERMISSIONS_POLICY)
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    if request.is_secure:
        response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
    return response

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
        if code == INFLATION_CODE:
            # Inflasi World Bank dihapus dari card utama.
            # Card inflasi sekarang pakai data BPS bulanan (inflation_yoy)
            # yang ditambahkan di dashboard() sebagai card utama.
            continue
        rows = info["data"]  # desc by year
        if not rows:
            continue
        latest = rows[0]
        prev = rows[1] if len(rows) > 1 else None
        change = latest["value"] - prev["value"] if prev else 0
        arrow = "+" if change > 0 else ("-" if change < 0 else "")
        change_badge = "bg-success" if change >= 0 else "bg-danger"
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
            "comparison_label": "vs tahun lalu",
        })
    return kpis


def generate_insight(data, bps_inflation=None):
    """Generate insight text from the latest data.

    Recomputed on every request from whatever is in the database, so the text
    follows the data automatically after each scheduled refresh.

    bps_inflation: dict dari inflation_yoy latest (BPS bulanan). Jika ada,
    narasi inflasi pakai data BPS (bulanan) bukan World Bank (tahunan).
    """
    pdb_info = data.get(GDP_GROWTH_CODE, {})
    inflasi_info = data.get(INFLATION_CODE, {})
    trade_info = data.get(TRADE_BALANCE_CODE, {})

    pdb = pdb_info.get("latest")
    inflasi = bps_inflation or inflasi_info.get("latest")
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
    #    BPS bulanan (bps_inflation) diprioritaskan; fallback ke World Bank.
    if inflasi:
        val = inflasi["value"]
        if val < 2.0:
            kondisi = "di bawah target BI (2-4%), memberi ruang kebijakan moneter yang akomodatif"
        elif val <= 4.0:
            kondisi = "berada dalam target BI (2-4%)"
        else:
            kondisi = "di atas target BI (2-4%), menekan ruang kebijakan moneter"

        source_label = "BPS (IHK YoY)" if bps_inflation else f"{inflasi['year']}"
        date_label = _format_month_id(inflasi["date"]) if bps_inflation else inflasi["year"]
        # BPS bulanan: 2 desimal (3.28%). World Bank tahunan: 1 desimal (1.9%).
        val_str = f"{val:.2f}" if bps_inflation else f"{val:.1f}"

        # Fase 17.10: gabungkan BPS monthly + WB annual dalam 1 kalimat.
        wb_latest = inflasi_info.get("latest")
        if bps_inflation and wb_latest:
            wb_val = wb_latest["value"]
            wb_year = wb_latest["year"]
            wb_str = f"{wb_val:.1f}"
            if val > wb_val:
                direction = "naik dari"
                commentary = "Kenaikan ini menunjukkan tekanan inflasi lebih tinggi pada periode terbaru."
            elif val < wb_val:
                direction = "turun dari"
                commentary = "Penurunan ini menunjukkan tekanan inflasi lebih rendah pada periode terbaru."
            else:
                direction = "sama dengan"
                commentary = "Angka inflasi stabil dibanding rata-rata tahunan."
            parts.append(
                f"Inflasi {val_str}% ({date_label}, {source_label}), {kondisi}, "
                f"{direction} rata-rata tahunan {wb_year} sebesar {wb_str}% (World Bank). "
                f"{commentary}"
            )
        else:
            parts.append(
                f"Inflasi {val_str}% ({date_label}, {source_label}) {kondisi}."
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


def build_inflation_chart(dates, values):
    """Monthly inflation YoY chart with BI target corridor (1.5%–3.5%)."""
    import plotly.graph_objects as go

    fig = go.Figure()
    # Target corridor band
    fig.add_trace(go.Scatter(
        x=dates + dates[::-1],
        y=[BI_TARGET_HIGH] * len(dates) + [BI_TARGET_LOW] * len(dates),
        fill="toself", fillcolor="rgba(40,167,69,0.1)",
        line=dict(color="rgba(0,0,0,0)"), name="Target BI (1.5%–3.5%)",
        hoverinfo="skip",
    ))
    # Inflation line
    fig.add_trace(go.Scatter(
        x=dates, y=values, mode="lines+markers", name="Inflasi YoY (%)",
        line=dict(color="#dc3545", width=3), marker=dict(size=7),
    ))
    fig.update_layout(**_base_layout())
    fig.update_xaxes(title_text="Bulan", showgrid=False)
    fig.update_yaxes(title_text="Persen (%)", gridcolor="#e9ecef", zeroline=True)
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False})


def build_inflation_snapshot(latest, year_ago):
    """Build inflation insight snapshot text: current vs year-ago comparison."""
    if not latest:
        return ""
    val = latest["value"]
    date_str = latest["date"]
    month_year = _format_month_id(date_str)

    if BI_TARGET_LOW <= val <= BI_TARGET_HIGH:
        corridor_status = "masih berada di dalam target BI"
    elif val < BI_TARGET_LOW:
        corridor_status = "berada di bawah target BI"
    else:
        corridor_status = "berada di atas target BI"

    if year_ago:
        prev_val = year_ago["value"]
        prev_month_year = _format_month_id(year_ago["date"])
        delta = val - prev_val
        if abs(delta) < 0.005:
            trend = "sama dengan"
        elif delta > 0:
            trend = f"naik {delta:.2f} pp dari"
        else:
            trend = f"turun {abs(delta):.2f} pp dari"
        return (
            f"Inflasi {month_year} tercatat {val:.2f}% (yoy), "
            f"{corridor_status} ({BI_TARGET_CENTER:.1f}% ±1%). "
            f"Angka ini {trend} {prev_val:.2f}% pada {prev_month_year}."
        )
    else:
        return (
            f"Inflasi {month_year} tercatat {val:.2f}% (yoy), "
            f"{corridor_status} ({BI_TARGET_CENTER:.1f}% ±1%)."
        )


def _format_month_id(date_str):
    """Format '2026-09-01' → 'September 2026' (Indonesian month names)."""
    bulan = {
        "01": "Januari", "02": "Februari", "03": "Maret", "04": "April",
        "05": "Mei", "06": "Juni", "07": "Juli", "08": "Agustus",
        "09": "September", "10": "Oktober", "11": "November", "12": "Desember",
    }
    try:
        parts = date_str.split("-")
        return f"{bulan.get(parts[1], parts[1])} {parts[0]}"
    except (IndexError, AttributeError):
        return date_str


@app.route("/")
def dashboard():
    data = get_all_data()
    kpis = compute_kpis(data)

    # Inflasi BPS (bulanan) — diambil sebelum compute_kpis karena card ini
    # tidak berasal dari data World Bank tapi dari time_series inflation_yoy.
    inflation_yoy_latest = get_latest_series("inflation_yoy")
    inflation_yoy_data = get_series("inflation_yoy", limit=12)

    # Attach per-indicator last_updated timestamp to each KPI card
    for kpi in kpis:
        kpi["last_updated"] = get_indicator_last_updated(kpi["code"]) or "Belum pernah update"

    # Tambah card utama "Inflasi YoY (BPS)" dari data BPS bulanan.
    # Card ini sengaja di sini (bukan di macro_kpis) agar tampil sebagai
    # KPI utama, bukan indikator tambahan.
    # World Bank annual inflation di-attach sebagai sub-value (Fase 17.10).
    wb_inflasi_info = data.get(INFLATION_CODE, {})
    wb_inflasi_latest = wb_inflasi_info.get("latest")
    wb_inflasi_rows = wb_inflasi_info.get("data", [])
    wb_inflasi_prev = wb_inflasi_rows[1] if len(wb_inflasi_rows) > 1 else None

    if inflation_yoy_latest:
        val = inflation_yoy_latest["value"]
        month_year = _format_month_id(inflation_yoy_latest["date"])

        # Tentukan status target BI (corridor 1.5%–3.5%)
        if val < BI_TARGET_LOW:
            status = "Di bawah target BI"
            status_badge = "bg-info"
        elif val <= BI_TARGET_HIGH:
            status = "Dalam target BI"
            status_badge = "bg-success"
        else:
            status = "Di atas target BI"
            status_badge = "bg-danger"

        # Change vs bulan lalu (month-on-month change in pp)
        prev_row = inflation_yoy_data[-2] if len(inflation_yoy_data) >= 2 else None
        if prev_row:
            mom_change = val - prev_row["value"]
            arrow = "+" if mom_change > 0 else ("-" if mom_change < 0 else "")
            change_badge = "bg-danger" if mom_change > 0 else "bg-success"
            formatted_change = f"{arrow}{abs(mom_change):.2f} pp"
            comparison_label = "vs bulan lalu"
        else:
            change_badge = "bg-secondary"
            formatted_change = "Data tidak cukup"
            comparison_label = ""
            arrow = ""

        # Attach World Bank annual inflation as sub-value (Fase 17.10)
        wb_annual_value = None
        wb_annual_year = None
        wb_annual_prev_value = None
        wb_annual_prev_year = None
        if wb_inflasi_latest:
            wb_annual_value = wb_inflasi_latest["value"]
            wb_annual_year = wb_inflasi_latest["year"]
        if wb_inflasi_prev:
            wb_annual_prev_value = wb_inflasi_prev["value"]
            wb_annual_prev_year = wb_inflasi_prev["year"]

        kpis.insert(0, {
            "code": "inflation_yoy",
            "name": "Inflasi YoY (BPS)",
            "formatted_value": f"{val:.2f}%",
            "formatted_change": formatted_change,
            "change_arrow": arrow,
            "change_badge_class": change_badge,
            "status": status,
            "status_badge_class": status_badge,
            "comparison_label": comparison_label,
            "date_label": month_year,
            "source_label": "BPS",
            "last_updated": inflation_yoy_latest.get("fetched_at", "Belum pernah update"),
        })

    # Card "Inflasi Tahunan (World Bank)" — data tahunan dari World Bank.
    # Ditampilkan sebagai card terpisah dengan label dan sumber jelas.
    if wb_inflasi_latest:
        wb_val = wb_inflasi_latest["value"]
        wb_year = wb_inflasi_latest["year"]
        wb_change = wb_val - wb_inflasi_prev["value"] if wb_inflasi_prev else 0
        wb_arrow = "+" if wb_change > 0 else ("-" if wb_change < 0 else "")
        wb_change_badge = "bg-success" if wb_change >= 0 else "bg-danger"
        wb_formatted_change = f"{wb_arrow}{abs(wb_change):.2f} pp" if wb_inflasi_prev else "Data tidak cukup"
        kpis.insert(0, {
            "code": INFLATION_CODE,
            "name": "Inflasi Tahunan (World Bank)",
            "formatted_value": f"{wb_val:.2f}%",
            "formatted_change": wb_formatted_change,
            "change_arrow": wb_arrow,
            "change_badge_class": wb_change_badge,
            "status": None,
            "status_badge_class": None,
            "comparison_label": "vs tahun lalu" if wb_inflasi_prev else "",
            "date_label": str(wb_year),
            "source_label": "World Bank",
            "description": "Rata-rata inflasi seluruh tahun",
            "last_updated": get_indicator_last_updated(INFLATION_CODE) or "Belum pernah update",
        })

    insight = generate_insight(data, bps_inflation=inflation_yoy_latest)
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
    # Each block needs this response's nonce or the CSP blocks it in the browser.
    nonce = g.csp_nonce
    main_chart = apply_nonce(build_main_chart(years, pdb_values, inflasi_values), nonce)
    pdb_chart = apply_nonce(build_single_chart(years, pdb_values, "PDB Growth (%)", "#0d6efd"), nonce)
    inflasi_chart = apply_nonce(build_single_chart(years, inflasi_values, "Inflasi YoY (%)", "#dc3545"), nonce)

    # Macro indicators: BI-Rate, USD/IDR, Gini, kesejahteraan
    bi_rate_latest = get_latest_series("bi_rate")
    usd_idr_latest = get_latest_series("usd_idr")
    gini_latest = get_latest_series("gini")
    life_exp_latest = get_latest_series("life_exp")
    edu_exp_latest = get_latest_series("edu_exp")
    literacy_latest = get_latest_series("literacy")

    # Build macro KPI cards
    macro_kpis = []
    if bi_rate_latest:
        macro_kpis.append({
            "name": "BI-Rate",
            "value": f"{bi_rate_latest['value']:.2f}%",
            "date": bi_rate_latest["date"],
            "color": "text-success",
            "last_updated": bi_rate_latest.get("fetched_at", "Belum pernah update"),
        })
    if usd_idr_latest:
        macro_kpis.append({
            "name": "Kurs USD/IDR",
            "value": f"{usd_idr_latest['value']:,.0f}",
            "date": usd_idr_latest["date"],
            "color": "text-info",
            "last_updated": usd_idr_latest.get("fetched_at", "Belum pernah update"),
        })
    if gini_latest:
        macro_kpis.append({
            "name": "Rasio Gini",
            "value": f"{gini_latest['value']:.1f}",
            "date": gini_latest["date"],
            "color": "text-warning",
            "last_updated": gini_latest.get("fetched_at", "Belum pernah update"),
        })
    if life_exp_latest:
        macro_kpis.append({
            "name": "Usia Harapan Hidup",
            "value": f"{life_exp_latest['value']:.1f} thn",
            "date": life_exp_latest["date"],
            "color": "text-primary",
            "last_updated": life_exp_latest.get("fetched_at", "Belum pernah update"),
        })
    if edu_exp_latest:
        macro_kpis.append({
            "name": "Pendidikan (% PDB)",
            "value": f"{edu_exp_latest['value']:.1f}%",
            "date": edu_exp_latest["date"],
            "color": "text-secondary",
            "last_updated": edu_exp_latest.get("fetched_at", "Belum pernah update"),
            "description": (
                f"Alokasi belanja pendidikan Indonesia sebesar {edu_exp_latest['value']:.1f}% PDB "
                f"({edu_exp_latest['date'][:4]}). Angka ini menunjukkan kontribusi sektor "
                f"pendidikan terhadap ekonomi nasional."
            ),
            "source": "World Bank (SE.XPD.TOTL.GD.ZS)",
        })
    if literacy_latest:
        macro_kpis.append({
            "name": "Literasi",
            "value": f"{literacy_latest['value']:.1f}%",
            "date": literacy_latest["date"],
            "color": "text-dark",
            "last_updated": literacy_latest.get("fetched_at", "Belum pernah update"),
            "description": (
                f"Tingkat literasi dasar (baca tulis) Indonesia mencapai "
                f"{literacy_latest['value']:.1f}% ({literacy_latest['date'][:4]}). "
                f"Data BPS mengukur kemampuan penduduk usia 15+ untuk membaca dan menulis."
            ),
            "source": "World Bank (SE.ADT.LITR.ZS)",
        })

    # PISA 2022 Reading Literacy card
    macro_kpis.append({
        "name": "Literasi Membaca (PISA 2022)",
        "value": "359",
        "date": "2022",
        "color": "text-danger",
        "last_updated": "2022-12-31",
        "description": (
            "Skor membaca PISA 2022 Indonesia 359 (OECD avg 476). "
            "Hanya 25% siswa usia 15 thn memadai (OECD avg 74%). "
            "Peringkat 73/80 negara."
        ),
        "source": "OECD PISA 2022",
    })

    # Macro charts
    bi_rate_data = get_series("bi_rate", limit=12)
    usd_idr_data = get_series("usd_idr", limit=30)
    gini_data = get_series("gini", limit=10)

    if bi_rate_data:
        bi_dates = [r["date"] for r in bi_rate_data]
        bi_values = [r["value"] for r in bi_rate_data]
        bi_rate_chart = apply_nonce(
            build_single_chart(bi_dates, bi_values, "BI-Rate (%)", "#6f42c1"), nonce
        )
    else:
        bi_rate_chart = ""

    if usd_idr_data:
        usd_dates = [r["date"] for r in usd_idr_data]
        usd_values = [r["value"] for r in usd_idr_data]
        usd_idr_chart = apply_nonce(
            build_single_chart(usd_dates, usd_values, "USD/IDR", "#20c997"), nonce
        )
    else:
        usd_idr_chart = ""

    if gini_data:
        gini_dates = [r["date"] for r in gini_data]
        gini_values = [r["value"] for r in gini_data]
        gini_chart = apply_nonce(
            build_single_chart(gini_dates, gini_values, "Rasio Gini", "#fd7e14"), nonce
        )
    else:
        gini_chart = ""

    # Inflation YoY chart + snapshot (BPS monthly data — diambil di atas)
    inflation_snapshot = ""
    inflation_chart = ""

    if inflation_yoy_data:
        infl_dates = [r["date"] for r in inflation_yoy_data]
        infl_values = [r["value"] for r in inflation_yoy_data]
        inflation_chart = apply_nonce(
            build_inflation_chart(infl_dates, infl_values), nonce
        )
        # Year-ago comparison: find same month previous year
        latest_date = inflation_yoy_latest["date"]
        latest_year = int(latest_date[:4])
        latest_month = latest_date[5:7]
        year_ago_date = f"{latest_year - 1}-{latest_month}-01"
        year_ago = next(
            (r for r in inflation_yoy_data if r["date"] == year_ago_date),
            None
        )
        inflation_snapshot = build_inflation_snapshot(inflation_yoy_latest, year_ago)

    macro_updated = get_series_metadata("macro_last_updated") or "Belum pernah update"

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
        macro_kpis=macro_kpis,
        bi_rate_chart=bi_rate_chart,
        usd_idr_chart=usd_idr_chart,
        gini_chart=gini_chart,
        macro_updated=macro_updated,
        inflation_chart=inflation_chart,
        inflation_snapshot=inflation_snapshot,
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


# ---------------------------------------------------------------------------
# Micro economy helpers
# ---------------------------------------------------------------------------

def _build_micro_chart(dates, values_list, labels, colors, title, y_title):
    """Build a multi-line chart for micro economy data."""
    import plotly.graph_objects as go
    fig = go.Figure()
    for dates, values, label, color in zip(dates, values_list, labels, colors):
        fig.add_trace(go.Scatter(
            x=dates, y=values, mode="lines+markers", name=label,
            line=dict(color=color, width=3), marker=dict(size=6),
        ))
    fig.update_layout(**_base_layout())
    fig.update_xaxes(title_text="Tanggal", showgrid=False)
    fig.update_yaxes(title_text=y_title, gridcolor="#e9ecef", zeroline=True)
    return fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})


def _compute_micro_metrics(province=None, daerah="jawa"):
    """Compute combined micro metrics for a province (or national average)."""
    # Get latest BBM price (Pertalite) for the selected daerah
    pertalite = get_latest_series(f"bbm_pertalite__{daerah}")
    bbm_price = pertalite["value"] if pertalite else 10000

    # Get UMP for province
    if province and province in UMP_PROVINSI:
        ump = UMP_PROVINSI[province]
    else:
        # National average
        ump = int(sum(UMP_PROVINSI.values()) / len(UMP_PROVINSI))

    # Compute metrics
    ump_monthly = ump * 1000  # Convert to Rupiah
    ump_hourly = ump_monthly / 173  # ~173 working hours/month
    liters_per_ump = ump_monthly / bbm_price
    hours_per_liter = bbm_price / ump_hourly

    # BBM index vs wage index (simplified: assume 2020 baseline)
    bbm_index = 100.0  # baseline
    wage_index = 100.0  # baseline
    # Adjust based on current vs assumed 2020 values
    bbm_2020 = 6500  # Pertalite 2020
    ump_2020 = 2800  # avg 2020
    bbm_index = (bbm_price / bbm_2020) * 100
    wage_index = (ump / ump_2020) * 100
    bbm_vs_wage = (bbm_index / wage_index) * 100

    # BBM burden (assume 20 liters/month consumption, 5M monthly expenditure)
    monthly_consumption = 20
    monthly_consumption = 20  # asumsi konsumsi BBM per bulan (liter)
    monthly_expenditure = 5000000  # BPS Susenas 2024: rata-rata pengeluaran rumah tangga per bulan (national)
    bbm_burden = (monthly_consumption * bbm_price) / monthly_expenditure * 100

    return {
        "province": province or "Rata-rata Nasional",
        "ump_monthly": ump_monthly,
        "ump_hourly": ump_hourly,
        "bbm_price": bbm_price,
        "liters_per_ump": liters_per_ump,
        "hours_per_liter": hours_per_liter,
        "bbm_index": bbm_index,
        "wage_index": wage_index,
        "bbm_vs_wage": bbm_vs_wage,
        "bbm_burden": bbm_burden,
        "monthly_consumption": monthly_consumption,
        "monthly_expenditure": monthly_expenditure,
    }


# Aliases: common province/region names → BBM_PER_DAERAH keys
DAERAH_ALIASES = {
    "Aceh": "aceh_sumut",
    "Sumatera Utara": "aceh_sumut",
    "Sumut": "aceh_sumut",
    "Jambi": "aceh_sumut",
    "Bengkulu": "aceh_sumut",
    "Sumatera Selatan": "aceh_sumut",
    "Sumsel": "aceh_sumut",
    "Lampung": "aceh_sumut",
    "Bangka Belitung": "aceh_sumut",
    "Babel": "aceh_sumut",
    "Sumatera Barat": "sumbar_riau",
    "Sumbar": "sumbar_riau",
    "Riau": "sumbar_riau",
    "Kepulauan Riau": "sumbar_riau",
    "Kepri": "sumbar_riau",
    "Kalimantan Utara": "sumbar_riau",
    "Kalut": "sumbar_riau",
    "Jawa": "jawa",
    "Jawa Barat": "jawa",
    "Jabar": "jawa",
    "Jawa Tengah": "jawa",
    "Jateng": "jawa",
    "Jawa Timur": "jawa",
    "Jatim": "jawa",
    "DKI Jakarta": "jawa",
    "Jakarta": "jawa",
    "Banten": "jawa",
    "DI Yogyakarta": "jawa",
    "Yogyakarta": "jawa",
    "Bali": "jawa",
    "Nusa Tenggara Barat": "jawa",
    "NTB": "jawa",
    "Nusa Tenggara Timur": "indonesia_timur",
    "NTT": "indonesia_timur",
    "Maluku": "indonesia_timur",
    "Maluku Utara": "indonesia_timur",
    "Papua": "indonesia_timur",
    "Papua Barat": "indonesia_timur",
    "Papua Tengah": "indonesia_timur",
    "Papua Pegunungan": "indonesia_timur",
    "Papua Selatan": "indonesia_timur",
    "Papua Barat Daya": "indonesia_timur",
    "Sulawesi": "indonesia_timur",
    "Kalimantan": "indonesia_timur",
    "Indonesia Timur": "indonesia_timur",
}


@app.route("/micro")
@app.route("/micro-economy")
def micro_economy():
    """Micro economy landing page: emas vs BBM, IKK, metrik gabungan."""
    import plotly.graph_objects as go

    # Get selected daerah first (used for BBM series keys below)
    selected_daerah = request.args.get("daerah", "jawa").strip()
    # Resolve aliases (e.g., "Aceh" → "aceh_sumut")
    selected_daerah = DAERAH_ALIASES.get(selected_daerah, selected_daerah)
    if selected_daerah not in BBM_PER_DAERAH:
        selected_daerah = "jawa"

    # Get time series data
    gold_data = get_series("gold_gram", limit=30)
    pertalite_data = get_series(f"bbm_pertalite__{selected_daerah}", limit=30)
    pertamax_data = get_series(f"bbm_pertamax__{selected_daerah}", limit=30)
    ikk_data = get_series("ikk", limit=12)
    bi_rate_data = get_series("bi_rate", limit=12)
    usd_idr_data = get_series("usd_idr", limit=30)

    # Build charts
    nonce = g.csp_nonce

    # Gold vs BBM chart
    if gold_data and pertalite_data:
        gold_dates = [r["date"] for r in gold_data]
        gold_values = [r["value"] for r in gold_data]
        pertalite_dates = [r["date"] for r in pertalite_data]
        pertalite_values = [r["value"] for r in pertalite_data]
        # Normalize to index (first value = 100)
        gold_base = gold_values[0] if gold_values else 1
        pertalite_base = pertalite_values[0] if pertalite_values else 1
        gold_indexed = [(v / gold_base) * 100 for v in gold_values]
        pertalite_indexed = [(v / pertalite_base) * 100 for v in pertalite_values]
        emas_bbm_chart = _build_micro_chart(
            [gold_dates, pertalite_dates],
            [gold_indexed, pertalite_indexed],
            ["Emas (indeks)", "Pertalite (indeks)"],
            ["#FFD700", "#dc3545"],
            "Perbandingan Emas vs BBM (Indeks)",
            "Indeks (base=100)"
        )
    else:
        emas_bbm_chart = "<p class='text-muted'>Data tidak tersedia</p>"

    # IKK chart
    if ikk_data:
        ikk_dates = [r["date"] for r in ikk_data]
        ikk_values = [r["value"] for r in ikk_data]
        ikk_chart = _build_micro_chart(
            [ikk_dates], [ikk_values], ["IKK"], ["#0d6efd"],
            "Indeks Keyakinan Konsumen (IKK)", "IKK"
        )
    else:
        ikk_chart = "<p class='text-muted'>Data tidak tersedia</p>"

    # BI-Rate chart
    if bi_rate_data:
        bi_dates = [r["date"] for r in bi_rate_data]
        bi_values = [r["value"] for r in bi_rate_data]
        bi_rate_chart = _build_micro_chart(
            [bi_dates], [bi_values], ["BI-Rate"], ["#6f42c1"],
            "BI-Rate", "%"
        )
    else:
        bi_rate_chart = "<p class='text-muted'>Data tidak tersedia</p>"

    # USD/IDR chart
    if usd_idr_data:
        usd_dates = [r["date"] for r in usd_idr_data]
        usd_values = [r["value"] for r in usd_idr_data]
        usd_idr_chart = _build_micro_chart(
            [usd_dates], [usd_values], ["USD/IDR"], ["#20c997"],
            "Kurs USD/IDR", "IDR"
        )
    else:
        usd_idr_chart = "<p class='text-muted'>Data tidak tersedia</p>"

    # Apply nonce to all charts
    emas_bbm_chart = apply_nonce(emas_bbm_chart, nonce)
    ikk_chart = apply_nonce(ikk_chart, nonce)
    bi_rate_chart = apply_nonce(bi_rate_chart, nonce)
    usd_idr_chart = apply_nonce(usd_idr_chart, nonce)

    # Compute metrics for selected province + daerah (from query params)
    selected_province = request.args.get("province", "").strip()
    metrics = _compute_micro_metrics(selected_province or None, selected_daerah)

    # Get latest values for display
    gold_latest = get_latest_series("gold_gram")
    pertalite_latest = get_latest_series(f"bbm_pertalite__{selected_daerah}")
    pertamax_latest = get_latest_series(f"bbm_pertamax__{selected_daerah}")
    pertamax_turbo_latest = get_latest_series(f"bbm_pertamax_turbo__{selected_daerah}")
    dexlite_latest = get_latest_series(f"bbm_dexlite__{selected_daerah}")
    solar_latest = get_latest_series(f"bbm_solar__{selected_daerah}")
    ikk_latest = get_latest_series("ikk")
    bi_rate_latest = get_latest_series("bi_rate")
    usd_idr_latest = get_latest_series("usd_idr")

    # BBM vs wage chart with historical BBM price data + wage index
    # Historical BBM Pertalite prices (Rupiah/liter) — government regulated changes
    bbm_history = [
        ("2014-01-01", 8500), ("2014-11-01", 10500), ("2015-01-01", 7500),
        ("2015-05-01", 8500), ("2016-01-01", 6500), ("2016-07-01", 7500),
        ("2017-01-01", 7000), ("2018-01-01", 7500), ("2019-01-01", 7500),
        ("2020-01-01", 7500), ("2021-01-01", 8000), ("2022-04-01", 9500),
        ("2022-09-01", 12000), ("2023-01-01", 10500), ("2024-01-01", 11000),
        ("2025-01-01", 13000), ("2026-01-01", 13000),
    ]
    # Use daerah-specific Pertalite price for the latest historical point
    bbm_history[-1] = ("2026-01-01", BBM_PER_DAERAH[selected_daerah]["prices"]["Pertalite"])
    # UMP historical (avg, Rupiah thousands/month) — national average
    ump_history = [
        ("2014-01-01", 2200), ("2015-01-01", 2500), ("2016-01-01", 2800),
        ("2017-01-01", 3000), ("2018-01-01", 3200), ("2019-01-01", 3400),
        ("2020-01-01", 3400), ("2021-01-01", 3400), ("2022-01-01", 3500),
        ("2023-01-01", 3600), ("2024-01-01", 3700), ("2025-01-01", 3750),
        ("2026-01-01", 3800),
    ]
    bbm_dates = [d for d, _ in bbm_history]
    bbm_prices = [v for _, v in bbm_history]
    ump_dates = [d for d, _ in ump_history]
    ump_prices = [v for _, v in ump_history]

    # Normalize to index (2014 = 100)
    bbm_base = bbm_prices[0] if bbm_prices else 1
    ump_base = ump_prices[0] if ump_prices else 1
    bbm_idx = [(v / bbm_base) * 100 for v in bbm_prices]
    ump_idx = [(v / ump_base) * 100 for v in ump_prices]

    import plotly.graph_objects as go
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=bbm_dates, y=bbm_idx, mode="lines+markers", name="Indeks Harga BBM",
        line=dict(color="#dc3545", width=3), marker=dict(size=8),
    ))
    fig.add_trace(go.Scatter(
        x=ump_dates, y=ump_idx, mode="lines+markers", name="Indeks Upah Minimum",
        line=dict(color="#0d6efd", width=3), marker=dict(size=8),
    ))
    # Mark BBM price changes (significant jumps > 10%)
    for i in range(1, len(bbm_history)):
        prev_price = bbm_history[i-1][1]
        curr_price = bbm_history[i][1]
        if prev_price > 0 and abs(curr_price - prev_price) / prev_price > 0.10:
            direction = "↑" if curr_price > prev_price else "↓"
            fig.add_annotation(
                x=bbm_history[i][0], y=bbm_idx[i],
                text=f"{direction} BBM",
                showarrow=True, arrowhead=2, ax=0, ay=-30,
                font=dict(size=10, color="#dc3545"),
            )
    fig.update_layout(**_base_layout())
    fig.update_xaxes(title_text="Tahun", showgrid=False)
    fig.update_yaxes(title_text="Indeks (2014=100)", gridcolor="#e9ecef", zeroline=True)
    bbm_vs_wage_chart = fig.to_html(full_html=False, include_plotlyjs="cdn", config={"displayModeBar": False})
    bbm_vs_wage_chart = apply_nonce(bbm_vs_wage_chart, nonce)

    # Province + daerah selectors
    provinces = sorted(UMP_PROVINSI.keys())
    if selected_province not in provinces:
        selected_province = ""
    daerah_list = BBM_PER_DAERAH

    # Last updated
    macro_updated = get_series_metadata("macro_last_updated") or "Belum pernah update"
    micro_updated = get_series_metadata("micro_last_updated") or "Belum pernah update"

    # Attach per-indicator timestamp
    def _with_ts(latest_dict):
        if latest_dict:
            latest_dict["last_updated"] = latest_dict.get("fetched_at", "Belum pernah update")
        return latest_dict

    gold_latest = _with_ts(gold_latest)
    pertalite_latest = _with_ts(pertalite_latest)
    pertamax_latest = _with_ts(pertamax_latest)
    pertamax_turbo_latest = _with_ts(pertamax_turbo_latest)
    dexlite_latest = _with_ts(dexlite_latest)
    solar_latest = _with_ts(solar_latest)
    ikk_latest = _with_ts(ikk_latest)
    bi_rate_latest = _with_ts(bi_rate_latest)
    usd_idr_latest = _with_ts(usd_idr_latest)

    return render_template(
        "micro.html",
        emas_bbm_chart=emas_bbm_chart,
        ikk_chart=ikk_chart,
        bi_rate_chart=bi_rate_chart,
        usd_idr_chart=usd_idr_chart,
        metrics=metrics,
        gold_latest=gold_latest,
        pertalite_latest=pertalite_latest,
        pertamax_latest=pertamax_latest,
        pertamax_turbo_latest=pertamax_turbo_latest,
        dexlite_latest=dexlite_latest,
        solar_latest=solar_latest,
        ikk_latest=ikk_latest,
        bi_rate_latest=bi_rate_latest,
        usd_idr_latest=usd_idr_latest,
        provinces=provinces,
        selected_province=metrics["province"],
        macro_updated=macro_updated,
        micro_updated=micro_updated,
        bbm_vs_wage_chart=bbm_vs_wage_chart,
        daerah_list=daerah_list,
        selected_daerah=selected_daerah,
    )


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
        fetch_all_macro()
        fetch_all_micro()
    # Backfill historical data for charts (idempotent, safe to re-run)
    try:
        backfill_run()
    except Exception as exc:
        print(f"[Bootstrap] Backfill failed (non-fatal): {exc}")
    start_scheduler()


bootstrap()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    try:
        app.run(host="0.0.0.0", port=port, debug=False)
    finally:
        stop_scheduler()
