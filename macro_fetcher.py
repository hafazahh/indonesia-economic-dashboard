"""Fetch macro indicators: BI-Rate, USD/IDR, Gini, dan komposit kesejahteraan.

Data sources:
  - BI-Rate: scrape HTML Bank Indonesia (tabel BI-Rate)
  - USD/IDR: frankfurter.app (free, no API key) — fallback exchangerate.host
  - Gini, Life Expectancy, Education, Literacy: World Bank API
"""
import os
import re
import sys
import requests

sys.path.insert(0, os.path.dirname(__file__))
from models import (
    init_db, init_time_series, upsert_series,
    get_latest_series, set_series_metadata,
)

WB_API = "https://api.worldbank.org/v2/country/IDN/indicator"

# World Bank indicator codes
GINI_CODE = "SI.POV.GINI"
LIFE_EXP_CODE = "SP.DYN.LE00.IN"
EDU_EXP_CODE = "SE.XPD.TOTL.GD.ZS"
LITERACY_CODE = "SE.ADT.LITR.ZS"

BI_RATE_URL = "https://www.bi.go.id/id/statistik/indikator/bi-rate.aspx"
USD_IDR_URL = "https://api.frankfurter.app/latest?from=USD&to=IDR"

# BI-Rate fallback data (scraped 2026-10-13, bi.go.id)
BI_RATE_KNOWN = [
    ("2026-09-23", 5.75), ("2026-08-19", 5.75), ("2026-07-22", 5.75),
    ("2026-06-18", 5.75), ("2026-06-09", 5.50), ("2026-05-20", 5.25),
    ("2026-04-22", 4.75), ("2026-03-17", 4.75), ("2026-02-19", 4.75),
    ("2026-01-21", 4.75),
]

# Headers to avoid connection-abort from anti-bot protection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


def _parse_bi_rate_html(html):
    """Parse BI-Rate from BI HTML table.

    Table rows (BI renders as SharePoint table with td elements):
      <tr><td>1</td><td>23 September 2026</td><td>5.75 %</td><td>...</td></tr>
    Returns list of (date_str, rate_float) sorted newest first.
    """
    # Pattern: <td>23 September 2026</td><td>5.75 %</td>
    pattern = re.compile(
        r'<td[^>]*>\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})\s*</td>\s*<td[^>]*>\s*([\d.]+)\s*%',
        re.I | re.S,
    )
    bulan_map = {
        'januari': 1, 'februari': 2, 'maret': 3, 'april': 4,
        'mei': 5, 'juni': 6, 'juli': 7, 'agustus': 8,
        'september': 9, 'oktober': 10, 'november': 11, 'desember': 12,
    }
    results = []
    for m in pattern.finditer(html):
        day, bulan, year, rate = m.group(1), m.group(2).lower(), m.group(3), float(m.group(4))
        month = bulan_map.get(bulan)
        if month is None:
            continue
        date_str = f"{year}-{month:02d}-{int(day):02d}"
        results.append((date_str, rate))
    return results


def fetch_bi_rate():
    """Fetch BI-Rate from Bank Indonesia. Returns count of new rows."""
    try:
        resp = requests.get(BI_RATE_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        rows = _parse_bi_rate_html(resp.text)
        if not rows:
            print("  BI-Rate: no rows parsed from BI page, using fallback")
            rows = BI_RATE_KNOWN
        count = 0
        for date_str, rate in rows:
            upsert_series("bi_rate", date_str, rate)
            count += 1
        print(f"  BI-Rate: {count} rows stored (latest={rows[0][1]}% on {rows[0][0]})")
        return count
    except Exception as e:
        print(f"  BI-Rate: ERROR {e}, using fallback")
        count = 0
        for date_str, rate in BI_RATE_KNOWN:
            upsert_series("bi_rate", date_str, rate)
            count += 1
        print(f"  BI-Rate: {count} fallback rows stored")
        return count


def fetch_usd_idr():
    """Fetch USD/IDR exchange rate. Returns 1 on success, 0 on failure."""
    try:
        resp = requests.get(USD_IDR_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rate = data["rates"]["IDR"]
        date_str = data.get("date", "")
        if date_str:
            upsert_series("usd_idr", date_str, float(rate))
            print(f"  USD/IDR: {rate} on {date_str}")
            return 1
        print("  USD/IDR: no date in response")
        return 0
    except Exception as e:
        print(f"  USD/IDR: ERROR {e}")
        return 0


# World Bank fallback data (scraped 2026-10-13)
WB_FALLBACK = {
    "life_exp": [("2023-12-31", 71.9), ("2022-12-31", 71.7), ("2021-12-31", 71.3),
                 ("2020-12-31", 71.0), ("2019-12-31", 71.5)],
    "edu_exp": [("2023-12-31", 3.0), ("2022-12-31", 3.1), ("2021-12-31", 3.0),
                ("2020-12-31", 3.0), ("2019-12-31", 3.0)],
}


def _fetch_wb_indicator(code, series_key):
    """Fetch a World Bank indicator and store as time_series."""
    url = f"{WB_API}/{code}?format=json&per_page=100"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2 or not data[1]:
            print(f"  {series_key} ({code}): no data, using fallback")
            rows = WB_FALLBACK.get(series_key, [])
            for date_str, value in rows:
                upsert_series(series_key, date_str, value)
            print(f"  {series_key}: {len(rows)} fallback rows")
            return len(rows)
        count = 0
        for entry in data[1]:
            value = entry.get("value")
            year = entry.get("date")
            if value is not None and year:
                # Annual: use year-12-31 as date for sorting
                upsert_series(series_key, f"{year}-12-31", float(value))
                count += 1
        print(f"  {series_key} ({code}): {count} rows")
        return count
    except Exception as e:
        print(f"  {series_key} ({code}): ERROR {e}, using fallback")
        rows = WB_FALLBACK.get(series_key, [])
        for date_str, value in rows:
            upsert_series(series_key, date_str, value)
        print(f"  {series_key}: {len(rows)} fallback rows")
        return len(rows)


def fetch_gini():
    """Fetch Gini coefficient (World Bank)."""
    return _fetch_wb_indicator(GINI_CODE, "gini")


def fetch_life_expectancy():
    """Fetch life expectancy (World Bank)."""
    return _fetch_wb_indicator(LIFE_EXP_CODE, "life_exp")


def fetch_education_exp():
    """Fetch education expenditure % GDP (World Bank)."""
    return _fetch_wb_indicator(EDU_EXP_CODE, "edu_exp")


def fetch_literacy():
    """Fetch adult literacy rate (World Bank)."""
    return _fetch_wb_indicator(LITERACY_CODE, "literacy")


def fetch_all_macro():
    """Fetch all macro indicators."""
    init_db()
    init_time_series()
    total = 0
    total += fetch_bi_rate()
    total += fetch_usd_idr()
    total += fetch_gini()
    total += fetch_life_expectancy()
    total += fetch_education_exp()
    total += fetch_literacy()
    if total > 0:
        set_series_metadata("macro_last_updated", __import__('datetime').datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    print(f"Macro total: {total} rows stored")
    return total


if __name__ == "__main__":
    fetch_all_macro()
