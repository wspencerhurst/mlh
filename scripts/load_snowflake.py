"""Load settlements, backtest episodes and today's recommendations into Snowflake and deploy the dashboard.
Run:  python scripts/load_snowflake.py   (needs SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_API_KEY)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qp_hedge import cortex, warehouse


def main():
    if not cortex.enabled():
        sys.exit("set SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER and SNOWFLAKE_API_KEY (env var or .env file)")
    for table, n in warehouse.load().items():
        print(f"{table}: {n} rows")
    with cortex.connect(database="goldmine", schema="public") as con:
        rows = con.cursor().execute("SELECT market, policy, cargoes, mean_unit, worst_unit FROM policy_scorecard "
                                    "ORDER BY market, mean_unit DESC").fetchall()
    print("market policy cargoes mean_unit worst_unit")
    for r in rows:
        print(*r)


if __name__ == "__main__":
    main()
