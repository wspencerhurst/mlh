"""Refresh public data: EIA history (crude/ULSD), FRED T-bill (via Nimble), today's COMEX curves (via Nimble).

    python scripts/fetch_data.py
"""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qp_hedge.live import latest_cme_curve
from qp_hedge.market import EIA_FILES, RAW_NAMES, eia_url, load_fred

os.makedirs("data/eia", exist_ok=True)
for key in EIA_FILES:
    path = f"data/eia/{RAW_NAMES.get(key, key)}.xls"
    urllib.request.urlretrieve(eia_url(key), path)
    print("EIA", key, os.path.getsize(path))

if os.path.exists("data/fred/DTB3.csv"):
    os.remove("data/fred/DTB3.csv")
print("FRED DTB3 rows", len(load_fred("DTB3")))

for pid, name in (("437", "gold"), ("425", "WTI"), ("426", "ULSD")):
    day, df = latest_cme_curve(pid)
    print(f"CME {name}: {day.date()} {len(df)} contracts (archived in data/cme/)")
