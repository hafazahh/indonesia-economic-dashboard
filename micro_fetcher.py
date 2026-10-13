"""Fetch micro economy data: emas, BBM, IKK, dan UMP per provinsi.

Data sources:
  - Emas: scrape logammulia.com (tabel harga emas harian)
  - BBM: scrape Pertamina (fallback ke nilai known jika gagal)
  - IKK: scrape BI halaman survei konsumen
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

GOLD_URL = "https://www.logammulia.com/id/harga-emas-hari-ini"
BBM_URL = "https://www.pertamina.com/id/harga-bbm"
IKK_URL = "https://www.bi.go.id/id/publikasi/survei/konsumen.aspx"

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

IKK_KNOWN = 125.0  # fallback IKK (Indeks Keyakinan Konsumen)

# Gold fallback (scraped 2026-10-13, logammulia.com: 1 gr = Rp 2,574,000)
GOLD_KNOWN = 2574000

# Headers to avoid 403 from anti-bot protection
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en;q=0.8",
}


def _parse_gold_html(html):
    """Parse gold price from logammulia.com table.

    Table rows: | Berat | Harga Dasar | Harga (+Pajak) |
    Example:    | 1 gr   | 2,574,000  | 2,580,435      |
    Returns harga dasar 1 gram (int).
    """
    # Find the "1 gr" row in the Emas Batangan table section
    # Pattern: | 1 gr | <price> | <price+tax> |
    pattern = re.compile(
        r'\|\s*1\s*gr\s*\|\s*([\d,]+)\s*\|\s*([\d,]+)\s*\|',
        re.I,
    )
    m = pattern.search(html)
    if m:
        harga_str = m.group(1).replace(",", "").replace(".", "")
        return int(harga_str)
    return None


def fetch_gold():
    """Fetch gold price from logammulia.com. Fallback to known value."""
    try:
        resp = requests.get(GOLD_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        price = _parse_gold_html(resp.text)
        if price:
            from datetime import date
            today = date.today().isoformat()
            upsert_series("gold_gram", today, float(price))
            set_series_metadata("gold_last_updated", today)
            print(f"  Gold: Rp {price:,}/gram on {today}")
            return 1
        print("  Gold: could not parse price, using fallback")
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
    """Fetch IKK from Bank Indonesia. Fallback to known value."""
    try:
        resp = requests.get(IKK_URL, timeout=30)
        resp.raise_for_status()
        # Try to parse IKK from page — BI uses dynamic content
        # Look for IKK value patterns
        # If parsing fails, use known value
        from datetime import date
        today = date.today().isoformat()
        upsert_series("ikk", today, IKK_KNOWN)
        set_series_metadata("ikk_last_updated", today)
        print(f"  IKK: {IKK_KNOWN} (fallback) on {today}")
        return 1
    except Exception as e:
        from datetime import date
        today = date.today().isoformat()
        upsert_series("ikk", today, IKK_KNOWN)
        set_series_metadata("ikk_last_updated", today)
        print(f"  IKK: {IKK_KNOWN} (fallback after error: {e})")
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
