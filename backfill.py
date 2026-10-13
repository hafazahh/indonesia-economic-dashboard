"""Backfill historical data for gold_gram, usd_idr, ikk, bbm_* series.

Idempotent: INSERT OR REPLACE, safe to run multiple times.
Run manually: python3 backfill.py
Or during bootstrap: import backfill; backfill.run()

Data sources:
  - Gold: logam-mulia-api.iamutaki.workers.dev/api/prices/anekalogam/history (paginated)
  - USD/IDR: api.frankfurter.app (daily rates, sampled monthly)
  - IKK: known BI survey data (monthly)
  - BBM: known historical prices (government regulated changes)
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, date
from collections import defaultdict

sys.path.insert(0, os.path.dirname(__file__))
from models import init_db, init_time_series, upsert_series, set_series_metadata
from macro_fetcher import INFLATION_YOY_KNOWN

GOLD_HISTORY_URL = "https://logam-mulia-api.iamutaki.workers.dev/api/prices/anekalogam/history"
USD_IDR_URL = "https://api.frankfurter.app/2024-01-01..2026-10-13?from=USD&to=IDR"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
}

# Known historical gold prices (Rp/gram, weight=1, from academic paper + news)
# Source: "Pengaruh Inflasi, Nilai Tukar Dolar AS, dan Suku Bunga" (2020-2024)
# + logammulia.com news (2025) + API (2026)
GOLD_KNOWN = {
    # 2024 (from academic paper)
    "2024-01-01": 1129000,
    "2024-02-01": 1143000,
    "2024-03-01": 1142000,
    "2024-04-01": 1254000,
    "2024-05-01": 1310000,
    "2024-06-01": 1336000,
    "2024-07-01": 1363000,
    "2024-11-01": 1547000,  # from ANTARA news
    # 2025 (from logammulia.com)
    "2025-01-01": 1608000,
    "2025-10-01": 2400000,
}

# Known IKK data from BI surveys (monthly)
# Source: BI news releases + Kontan data
IKK_KNOWN = {
    # 2024
    "2024-01-01": 123.8,
    "2024-02-01": 123.1,
    "2024-03-01": 123.8,
    "2024-04-01": 127.7,
    "2024-05-01": 125.2,
    "2024-06-01": 123.3,
    "2024-07-01": 124.3,
    "2024-08-01": 124.4,
    "2024-09-01": 123.5,
    "2024-10-01": 121.1,
    "2024-11-01": 125.9,
    "2024-12-01": 127.7,
    # 2025
    "2025-01-01": 127.2,
    "2025-02-01": 126.4,
    "2025-03-01": 121.1,
    "2025-04-01": 121.7,
    "2025-05-01": 117.5,
    "2025-06-01": 117.8,
    "2025-07-01": 118.1,
    "2025-08-01": 117.2,
    "2025-09-01": 115.0,
    "2025-10-01": 121.2,
    "2025-12-01": 123.5,
    # 2026
    "2026-09-01": 118.1,
}

# Known BBM historical prices (Rp/liter, national average)
# Source: government regulated price changes (2014-2026)
BBM_KNOWN = {
    "Pertalite": {
        "2020-01-01": 7500,
        "2021-01-01": 8000,
        "2022-01-01": 10000,
        "2023-01-01": 10000,
        "2024-01-01": 10000,
        "2025-01-01": 10000,
        "2026-01-01": 10000,
        "2026-10-01": 10000,
    },
    "Pertamax": {
        "2020-01-01": 12500,
        "2021-01-01": 12500,
        "2022-01-01": 12500,
        "2023-01-01": 14950,
        "2024-01-01": 14950,
        "2025-01-01": 15950,
        "2026-01-01": 15950,
        "2026-10-01": 15950,
    },
    "Pertamax Turbo": {
        "2020-01-01": 15000,
        "2021-01-01": 15000,
        "2022-01-01": 15000,
        "2023-01-01": 18550,
        "2024-01-01": 18550,
        "2025-01-01": 19600,
        "2026-01-01": 19600,
        "2026-10-01": 19600,
    },
    "Dexlite": {
        "2020-01-01": 10000,
        "2021-01-01": 10000,
        "2022-01-01": 10000,
        "2023-01-01": 23700,
        "2024-01-01": 23700,
        "2025-01-01": 23700,
        "2026-01-01": 23700,
        "2026-10-01": 23700,
    },
    "Solar": {
        "2020-01-01": 6500,
        "2021-01-01": 6500,
        "2022-01-01": 6500,
        "2023-01-01": 6800,
        "2024-01-01": 6800,
        "2025-01-01": 6800,
        "2026-01-01": 6800,
        "2026-10-01": 6800,
    },
}

# BBM per daerah current prices (from micro_fetcher.py)
BBM_PER_DAERAH = {
    "jawa": {
        "Pertalite": 10000,
        "Pertamax": 15950,
        "Pertamax Turbo": 19600,
        "Dexlite": 23700,
        "Solar": 6800,
    },
    "aceh_sumut": {
        "Pertalite": 10000,
        "Pertamax": 16300,
        "Pertamax Turbo": 19600,
        "Dexlite": 24200,
        "Solar": 6800,
    },
    "sumbar_riau": {
        "Pertalite": 10000,
        "Pertamax": 16650,
        "Pertamax Turbo": 20450,
        "Dexlite": 24200,
        "Solar": 6800,
    },
    "indonesia_timur": {
        "Pertalite": 10000,
        "Pertamax": 14950,
        "Pertamax Turbo": 18550,
        "Dexlite": 23700,
        "Solar": 6800,
    },
}


def fetch_gold_history():
    """Fetch gold history from paginated API. Returns {date_str: price}."""
    monthly = {}
    for page in range(1, 75):
        url = f"{GOLD_HISTORY_URL}?page={page}&length=20"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success") or not data.get("data"):
                break
            for item in data["data"]:
                if item.get("weight") == 1 and item.get("material") == "gold":
                    date_str = item.get("recordedDate", "")
                    price = item.get("sellPrice")
                    if date_str and price:
                        # Group by month: YYYY-MM -> last value
                        month_key = date_str[:7]
                        monthly[month_key] = (date_str, float(price))
            # Stop if we've gone past 2024
            last_date = data["data"][-1].get("recordedDate", "")
            if last_date < "2024-01-01":
                break
            time.sleep(0.1)  # be nice to the API
        except Exception as e:
            print(f"  Gold API page {page}: ERROR {e}")
            break
    # Convert to {date_str: price}
    result = {}
    for month_key, (date_str, price) in monthly.items():
        result[date_str] = price
    return result


def fetch_usd_idr_history():
    """Fetch USD/IDR from Frankfurter. Returns {date_str: rate} (monthly first day)."""
    try:
        resp = requests.get(USD_IDR_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        rates = data.get("rates", {})
        # Group by month, take first day
        monthly = {}
        for date_str in sorted(rates.keys()):
            if date_str >= "2024-01-01":
                month_key = date_str[:7]
                if month_key not in monthly:
                    monthly[month_key] = (date_str, float(rates[date_str]["IDR"]))
        result = {}
        for month_key, (date_str, rate) in monthly.items():
            result[date_str] = rate
        return result
    except Exception as e:
        print(f"  USD/IDR API: ERROR {e}")
        return {}


def backfill_gold():
    """Backfill gold_gram series."""
    print("=== Gold (gold_gram) ===")
    # Fetch from API
    api_data = fetch_gold_history()
    print(f"  API: {len(api_data)} monthly samples")
    # Merge with known data (API takes precedence for overlapping months)
    merged = dict(GOLD_KNOWN)
    for date_str, price in api_data.items():
        merged[date_str] = price
    # Upsert
    count = 0
    for date_str, price in sorted(merged.items()):
        upsert_series("gold_gram", date_str, price)
        count += 1
    print(f"  Stored: {count} rows")
    return count


def backfill_usd_idr():
    """Backfill usd_idr series."""
    print("=== USD/IDR (usd_idr) ===")
    data = fetch_usd_idr_history()
    print(f"  API: {len(data)} monthly samples")
    count = 0
    for date_str, rate in sorted(data.items()):
        upsert_series("usd_idr", date_str, rate)
        count += 1
    print(f"  Stored: {count} rows")
    return count


def backfill_ikk():
    """Backfill ikk series."""
    print("=== IKK (ikk) ===")
    count = 0
    for date_str, value in sorted(IKK_KNOWN.items()):
        upsert_series("ikk", date_str, value)
        count += 1
    print(f"  Stored: {count} rows")
    return count


def backfill_bbm():
    """Backfill bbm_* series for all daerah."""
    print("=== BBM (bbm_*) ===")
    count = 0
    for daerah, prices in BBM_PER_DAERAH.items():
        for product, current_price in prices.items():
            series_key = f"bbm_{product.lower().replace(' ', '_')}__{daerah}"
            history = BBM_KNOWN.get(product, {})
            for date_str, price in sorted(history.items()):
                upsert_series(series_key, date_str, float(price))
                count += 1
            # Ensure current price is stored
            today = date.today().isoformat()
            upsert_series(series_key, today, float(current_price))
            count += 1
    print(f"  Stored: {count} rows")
    return count


def backfill_inflation():
    """Backfill inflation_yoy series with BPS monthly data (Jan 2025 – Sep 2026)."""
    print("=== Inflasi Bulanan (inflation_yoy) ===")
    count = 0
    for date_str, value in sorted(INFLATION_YOY_KNOWN.items()):
        upsert_series("inflation_yoy", date_str, value)
        count += 1
    print(f"  Stored: {count} rows")
    return count


def run():
    """Run all backfills. Idempotent."""
    init_db()
    init_time_series()
    total = 0
    total += backfill_gold()
    total += backfill_usd_idr()
    total += backfill_ikk()
    total += backfill_bbm()
    total += backfill_inflation()
    set_series_metadata("backfill_last_run", datetime.utcnow().isoformat())
    print(f"\nBackfill complete: {total} rows stored")
    return total


if __name__ == "__main__":
    run()
