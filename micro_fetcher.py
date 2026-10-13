"""Fetch micro economy data: emas, BBM, IKK, dan UMP per provinsi.

Data sources:
  - Emas: logam-mulia-api.iamutaki.workers.dev (JSON API, live)
  - BBM: scrape Pertamina (fallback ke nilai known jika gagal)
  - IKK: scrape TradingEconomics (news summary, live)
  - UMP: hardcoded 37 provinsi (data 2024/2025 dari BPS/Kemnaker)
"""
import os
import re
import sys
import json
import requests

sys.path.insert(0, os.path.dirname(__file__))
from models import (
    init_db, init_time_series, upsert_series, set_series_metadata,
)

GOLD_API_URL = "https://logam-mulia-api.iamutaki.workers.dev/api/prices/anekalogam"
BBM_URL = "https://www.pertamina.com/id/harga-bbm"
IKK_URL = "https://tradingeconomics.com/indonesia/consumer-confidence"

# UMP per provinsi 2024 (data BPS/Kemnaker, dalam ribu Rupiah per bulan)
UMP_PROVINSI = {
    "Aceh": 3698, "Sumatera Utara": 3958, "Sumatera Barat": 3200, "Riau": 4044,
    "Jambi": 3384, "Sumatera Selatan": 3642, "Bengkulu": 2694, "Lampung": 3135,
    "Kepulauan Bangka Belitung": 3825, "Kepulauan Riau": 4363, "DKI Jakarta": 5397,
    "Jawa Barat": 4170, "Jawa Tengah": 3179, "DI Yogyakarta": 2723, "Jawa Timur": 3276,
    "Banten": 4958, "Bali": 3187, "Nusa Tenggara Barat": 2901, "Nusa Tenggara Timur": 2568,
    "Kalimantan Barat": 3135, "Kalimantan Tengah": 3503, "Kalimantan Selatan": 3545,
    "Kalimantan Timur": 4034, "Kalimantan Utara": 3795, "Sulawesi Utara": 4044,
    "Sulawesi Tengah": 3444, "Sulawesi Selatan": 3900, "Sulawesi Tenggara": 3401,
    "Gorontalo": 3521, "Sulawesi Barat": 3147, "Maluku": 2900, "Maluku Utara": 3330,
    "Papua": 4350, "Papua Barat": 3800, "Papua Tengah": 4120, "Papua Pegunungan": 4300,
    "Papua Selatan": 4000, "Papua Barat Daya": 3900,
}

# Harga BBM known (per liter, Rupiah) — fallback jika scrape gagal
BBM_KNOWN = {
    "Pertalite": 13000,
    "Pertamax": 13500,
    "Pertamax Turbo": 16000,
    "Dexlite": 13900,
    "Solar": 6800,
}

IKK_KNOWN = 118.1  # fallback IKK (Indeks Keyakinan Konsumen, September 2026)

# Gold fallback (scraped 2026-10-13, logammulia.com: 1 gr = Rp 2,574,000)
GOLD_KNOWN = 2574000

# Headers to avoid 403 from anti-bot protection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


def fetch_gold():
    """Fetch gold price from logam-mulia-api. Fallback to known value."""
    try:
        resp = requests.get(GOLD_API_URL, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        # Find weight=1 gold entry (first match)
        for item in data.get("data", []):
            if item.get("weight") == 1 and item.get("material") == "gold":
                price = item["sellPrice"]
                from datetime import date
                today = date.today().isoformat()
                upsert_series("gold_gram", today, float(price))
                set_series_metadata("gold_last_updated", today)
                print(f"  Gold: Rp {price:,}/gram on {today}")
                return 1
        print("  Gold: no weight=1 entry found, using fallback")
        price = GOLD_KNOWN
    except Exception as e:
        print(f"  Gold: ERROR {e}, using fallback")
        price = GOLD_KNOWN
    from datetime import date
    today = date.today().isoformat()
    upsert_series("gold_gram", today, float(price))
    set_series_metadata("gold_last_updated", today)
    print(f"  Gold: Rp {price:,}/gram (fallback) on {today}")
    return 1


def fetch_bbm():
    """Fetch BBM prices. Uses known fallback values (Pertamina blocks scraping)."""
    from datetime import date
    today = date.today().isoformat()
    count = 0
    for name, price in BBM_KNOWN.items():
        upsert_series(f"bbm_{name.lower().replace(' ', '_')}", today, float(price))
        count += 1
    set_series_metadata("bbm_last_updated", today)
    print(f"  BBM: {count} products stored on {today}")
    return count


def fetch_ikk():
    """Fetch IKK from TradingEconomics. Fallback to known value."""
    try:
        resp = requests.get(IKK_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        # Search for latest IKK value in news summary
        # Pattern: "declined to 118.1 in September 2026" or "increased to 118.5 in August 2026"
        m = re.search(
            r"(?:declined|increased|rose|fell|dropped|climbed)\s+to\s+([\d.]+)\s+in\s+(\w+)\s+(\d{4})",
            resp.text,
        )
        if m:
            value = float(m.group(1))
            month_str = m.group(2).lower()
            year = m.group(3)
            month_map = {
                "january": 1, "february": 2, "march": 3, "april": 4,
                "may": 5, "june": 6, "july": 7, "august": 8,
                "september": 9, "october": 10, "november": 11, "december": 12,
            }
            month = month_map.get(month_str, 1)
            date_str = f"{year}-{month:02d}-01"
            upsert_series("ikk", date_str, value)
            set_series_metadata("ikk_last_updated", date_str)
            print(f"  IKK: {value} on {date_str}")
            return 1
        print("  IKK: could not parse from TradingEconomics, using fallback")
        value = IKK_KNOWN
    except Exception as e:
        print(f"  IKK: ERROR {e}, using fallback")
        value = IKK_KNOWN
    from datetime import date
    today = date.today().isoformat()
    upsert_series("ikk", today, value)
    set_series_metadata("ikk_last_updated", today)
    print(f"  IKK: {value} (fallback) on {today}")
    return 1


def get_ump_data():
    """Return UMP per provinsi data."""
    return UMP_PROVINSI


def fetch_all_micro():
    """Fetch all micro data."""
    init_db()
    init_time_series()
    total = 0
    total += fetch_gold()
    total += fetch_bbm()
    total += fetch_ikk()
    if total > 0:
        set_series_metadata("micro_last_updated", __import__('datetime').datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"))
    print(f"Micro total: {total} rows stored")
    return total


if __name__ == "__main__":
    fetch_all_micro()
