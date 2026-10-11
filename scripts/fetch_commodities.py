"""Fetch EODHD commodity price history into data/commodities.parquet.

Usage: EODHD_API_TOKEN=... python3 scripts/fetch_commodities.py
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

# code -> (group, finest interval EODHD serves for it)
SERIES = {
    "WTI": ("oil", "daily"),
    "BRENT": ("oil", "daily"),
    "GASOLINE_US": ("fuel", "weekly"),
    "DIESEL_USGULF": ("fuel", "daily"),
    "HEATING_OIL_NYH": ("fuel", "daily"),
    "JET_FUEL_USGULF": ("fuel", "daily"),
    "PROPANE_MBTX": ("gas", "daily"),
    "NATURAL_GAS": ("gas", "daily"),
    "NATGAS_EU": ("gas", "monthly"),
    "LNG_ASIA": ("gas", "monthly"),
    "ALUMINUM": ("metal", "monthly"),
    "COPPER": ("metal", "monthly"),
    "WHEAT": ("agri", "monthly"),
}

BASE = "https://eodhd.com/api/commodities/historical"
OUT = Path(__file__).resolve().parent.parent / "data" / "commodities.parquet"


def get(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=60) as r:
        return json.loads(r.read())


def fetch(code: str, interval: str, token: str) -> tuple[dict, list[dict]]:
    """Return (meta, rows) for one series, following page[offset] pagination."""
    rows: list[dict] = []
    offset = 0
    while True:
        q = urllib.parse.urlencode(
            {"api_token": token, "fmt": "json", "interval": interval, "page[offset]": offset}
        )
        d = get(f"{BASE}/{code}?{q}")
        rows += d["data"]
        meta = d["meta"]
        offset += meta["limit"]
        if offset >= meta["total"]:
            break
    if len(rows) != meta["total"]:
        sys.exit(f"{code}: got {len(rows)} rows, expected {meta['total']}")
    return meta, rows


def main() -> None:
    token = os.environ.get("EODHD_API_TOKEN")
    if not token:
        sys.exit("EODHD_API_TOKEN is not set")

    frames = []
    for code, (group, interval) in SERIES.items():
        meta, rows = fetch(code, interval, token)
        if meta["interval"] != interval:
            sys.exit(f"{code}: asked for {interval}, got {meta['interval']}")
        df = pd.DataFrame(rows)
        df["code"] = code
        df["group"] = group
        df["interval"] = interval
        df["unit"] = meta["unit"]
        df["name"] = meta["name"]
        frames.append(df)
        print(f"{code:16} {interval:7} {len(df):6} rows  {df['date'].min()} .. {df['date'].max()}")

    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"])
    out = (
        out[["code", "group", "date", "value", "interval", "unit", "name"]]
        .drop_duplicates(["code", "date"])
        .sort_values(["code", "date"], ignore_index=True)
    )
    out.to_parquet(OUT, index=False)
    print(f"wrote {len(out)} rows to {OUT}")


if __name__ == "__main__":
    main()
