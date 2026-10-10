"""Verifikasi kode indikator World Bank API untuk Indonesia (IDN)."""
import requests
import json

INDICATORS = {
    "PDB Growth": "NY.GDP.MKTP.KD.ZG",
    "Inflasi": "FP.CPI.TOTL.ZG",
    "Neraca Perdagangan (exports)": "NE.EXP.GNFS.ZS",
    "Neraca Perdagangan (imports)": "NE.IMP.GNFS.ZS",
    "Trade Balance (BoP)": "BN.GSR.GNFS.CD",
}

for name, code in INDICATORS.items():
    url = f"https://api.worldbank.org/v2/country/IDN/indicator/{code}?format=json&per_page=5"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
        entries = data[1] if len(data) > 1 and data[1] else []
        non_null = [e for e in entries if e.get("value") is not None]
        latest = non_null[0] if non_null else None
        if latest:
            print(f"{name} ({code}): latest={latest['date']} value={latest['value']}")
        else:
            print(f"{name} ({code}): no data (metadata pages={data[0]['pages']})")
    except Exception as e:
        print(f"{name} ({code}): ERROR {e}")
