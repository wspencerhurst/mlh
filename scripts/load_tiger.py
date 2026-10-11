"""Apply the Tiger Data schema, backfill data/cme/*.json, refresh the weekly aggregate, show curve_spreads.
Run:  python scripts/load_tiger.py   (needs TIGER_DATABASE_URL)
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qp_hedge import tiger
from qp_hedge.live import parse_cme


def main():
    if not tiger.enabled():
        sys.exit("set TIGER_DATABASE_URL (env var or .env file)")
    tiger.ensure_schema()
    n = 0
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "cme", "cme_*_*.json"))):
        m = re.match(r"cme_(\d+)_(\d{8})\.json", os.path.basename(path))
        if not m:
            continue
        df = parse_cme(json.load(open(path)))
        k = tiger.upsert_settlements(m.group(1), pd.Timestamp(m.group(2)), df)
        print(f"{os.path.basename(path)}: {k} rows")
        n += k
    print(f"loaded {n} rows")
    with tiger.connect(autocommit=True) as con:
        con.execute("CALL refresh_continuous_aggregate('cme_settlements_weekly', NULL, NULL)")
        rows = con.execute("SELECT * FROM curve_spreads ORDER BY trade_date DESC, product_id LIMIT 10").fetchall()
    print("trade_date product front_ym front_settle spread_2 spread_3")
    for r in rows:
        print(*r)


if __name__ == "__main__":
    main()
