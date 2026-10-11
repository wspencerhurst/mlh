"""Snowflake data warehouse: CME settlements, walk-forward backtest episodes and daily recommendations.

Tables and views live in GOLDMINE.PUBLIC (schema in db/snowflake.sql). Each load replaces a table's
contents, so it can be rerun after every pipeline or live run. Credentials as in qp_hedge/cortex.py.
"""
from __future__ import annotations

import glob
import json
import os
import re

from . import cortex
from .live import parse_cme

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "db", "snowflake.sql")
APP = os.path.join(ROOT, "dashboard", "streamlit_app.py")


def ensure_schema(cur) -> None:
    text = "\n".join(l for l in open(SCHEMA).read().splitlines() if not l.lstrip().startswith("--"))
    for stmt in filter(None, (s.strip() for s in text.split(";"))):
        cur.execute(stmt)


def replace(cur, table: str, cols: tuple, rows: list) -> int:
    cur.execute(f"DELETE FROM {table}")
    if rows:
        cur.executemany(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", rows)
    return len(rows)


def settlement_rows() -> list:
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, "data", "cme", "cme_*_*.json"))):
        m = re.match(r"cme_(\d+)_(\d{4})(\d{2})(\d{2})\.json", os.path.basename(path))
        if m:
            d = f"{m.group(2)}-{m.group(3)}-{m.group(4)}"
            rows += [(d, m.group(1), int(r.ym), r.settle, r.volume, r.oi)
                     for r in parse_cme(json.load(open(path))).itertuples()]
    return rows


def episode_rows(market: str) -> list:
    res = json.load(open(os.path.join(ROOT, "outputs", f"results_{market}.json")))
    return [(market, e["policy"], int(e["delivery"]), str(e["elected"]), e.get("elect_date"), e["pnl"], e.get("pnl_unit"),
             e.get("physical_unit"), e.get("futures_unit"), e.get("costs_unit"), e.get("financing_unit"))
            for e in res["episodes_test"]]


def recommendation_rows(market: str) -> list:
    lv = json.load(open(os.path.join(ROOT, "outputs", f"live_{market}.json")))
    return [(market, lv["asof"], o["name"], o["qp_month"], int(o["qp_ym"]), o["hedged_value"], o["name"] == lv["best"],
             bool(lv["declare_now"]), lv["unit"]) for o in lv["options"]]


def load(markets=("gold", "crude"), app: bool = True) -> dict:
    """Apply the schema, replace every table's rows and (optionally) deploy the Streamlit dashboard."""
    n = {}
    with cortex.connect() as con:
        cur = con.cursor()
        ensure_schema(cur)
        n["cme_settlements"] = replace(cur, "cme_settlements", ("trade_date", "product_id", "ym", "settle", "volume", "oi"),
                                       settlement_rows())
        n["backtest_episodes"] = replace(cur, "backtest_episodes",
                                         ("market", "policy", "delivery", "elected", "elect_date", "pnl", "pnl_unit",
                                          "physical_unit", "futures_unit", "costs_unit", "financing_unit"),
                                         [r for m in markets for r in episode_rows(m)])
        n["recommendations"] = replace(cur, "recommendations",
                                       ("market", "asof", "qp", "qp_month", "qp_ym", "hedged_value", "is_best",
                                        "declare_now", "unit"),
                                       [r for m in markets for r in recommendation_rows(m)])
        if app:
            cur.execute(f"PUT 'file://{APP}' @app AUTO_COMPRESS = FALSE OVERWRITE = TRUE")
            wh = cortex._env().get("SNOWFLAKE_WAREHOUSE")
            cur.execute("CREATE OR REPLACE STREAMLIT goldmine_dashboard ROOT_LOCATION = '@goldmine.public.app' "
                        "MAIN_FILE = 'streamlit_app.py'" + (f" QUERY_WAREHOUSE = {wh}" if wh else ""))
    return n
