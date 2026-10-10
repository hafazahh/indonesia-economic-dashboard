"""Fetch economic data from World Bank API and store in SQLite."""
import requests
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from models import init_db, upsert_indicator, set_last_updated

INDICATORS = {
    "NY.GDP.MKTP.KD.ZG": "PDB Growth",
    "FP.CPI.TOTL.ZG": "Inflasi",
    "BN.GSR.GNFS.CD": "Trade Balance",
}

API_BASE = "https://api.worldbank.org/v2/country/IDN/indicator"


def fetch_indicator(code, name):
    """Fetch data for one indicator from World Bank API."""
    url = f"{API_BASE}/{code}?format=json&per_page=100"
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if len(data) < 2 or not data[1]:
            print(f"  {name} ({code}): no data returned")
            return 0
        count = 0
        for entry in data[1]:
            value = entry.get("value")
            year = entry.get("date")
            if value is not None and year:
                upsert_indicator(code, name, value, int(year))
                count += 1
        print(f"  {name} ({code}): {count} rows stored")
        return count
    except Exception as e:
        print(f"  {name} ({code}): ERROR {e}")
        return 0


def fetch_all():
    """Fetch all indicators and update metadata."""
    init_db()
    total = 0
    for code, name in INDICATORS.items():
        total += fetch_indicator(code, name)
    if total > 0:
        set_last_updated()
    print(f"Total: {total} rows stored")
    return total


if __name__ == "__main__":
    fetch_all()
