"""Tiger Data storage of CME settlements, against TIGER_DATABASE_URL (skips when unset).

  1. Idempotency: upserting the same curve twice leaves the row count unchanged.
  2. curve_spreads: front settle and 2nd/3rd-contract spreads vs the front are correct.
Run:  python tests/test_tiger.py
"""
from __future__ import annotations

import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qp_hedge import tiger

PID = "test_prod"
D1, D2 = pd.Timestamp("2020-01-02"), pd.Timestamp("2020-01-03")


def curve(settles, start=202003):
    return pd.DataFrame({"ym": [start + i for i in range(len(settles))], "settle": settles,
                         "volume": 10.0, "oi": 20.0})


def count(con):
    return con.execute("SELECT count(*) FROM cme_settlements WHERE product_id = %s", (PID,)).fetchone()[0]


def load():
    tiger.upsert_settlements(PID, D1, curve([100.0, 103.0, 107.0, 112.0]))
    tiger.upsert_settlements(PID, D2, curve([101.0, 100.5, 99.0]))


def main():
    if not tiger.enabled():
        print("TIGER_DATABASE_URL not set: skipping")
        return
    tiger.ensure_schema()
    tiger.ensure_schema()  # schema is idempotent
    with tiger.connect() as con:
        con.execute("DELETE FROM cme_settlements WHERE product_id = %s", (PID,))
    try:
        load()
        with tiger.connect() as con:
            n1 = count(con)
        load()
        with tiger.connect() as con:
            n2 = count(con)
            rows = con.execute("SELECT trade_date, front_ym, front_settle, spread_2, spread_3 FROM curve_spreads "
                               "WHERE product_id = %s", (PID,)).fetchall()
        assert n1 == n2 == 7, (n1, n2)
        assert [r[0] for r in rows] == [D1.date(), D2.date()], rows
        assert rows[0][1:] == (202003, 100.0, 3.0, 7.0), rows[0]
        assert rows[1][1:] == (202003, 101.0, -0.5, -2.0), rows[1]
        print("ok: upsert idempotent, curve_spreads correct")
    finally:
        with tiger.connect() as con:
            con.execute("DELETE FROM cme_settlements WHERE product_id = %s", (PID,))


if __name__ == "__main__":
    main()
