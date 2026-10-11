"""Rows loaded into Snowflake (no network): shapes match the table columns and the source files.
Run:  python tests/test_warehouse.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qp_hedge import warehouse


def main():
    s = warehouse.settlement_rows()
    assert s and all(len(r) == 6 for r in s), "settlements"
    assert {r[1] for r in s} >= {"425", "437"} and all(r[0].count("-") == 2 for r in s)
    for m in ("gold", "crude"):
        res = json.load(open(os.path.join(ROOT, "outputs", f"results_{m}.json")))
        e = warehouse.episode_rows(m)
        assert len(e) == len(res["episodes_test"]) and all(len(r) == 11 and r[0] == m for r in e), m
        rec = warehouse.recommendation_rows(m)
        assert rec and all(len(r) == 9 for r in rec) and sum(r[6] for r in rec) == 1, f"{m}: exactly one best QP"
    print("ok: warehouse rows")


if __name__ == "__main__":
    main()
