"""Cortex explanation client: prompt content, bound parameters, failure handling. No network.

Run:  python tests/test_cortex.py
"""
from __future__ import annotations

import json
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qp_hedge import cortex

LIVE = {
    "unit": "oz", "exchange": "COMEX", "deal": "AU dore cargo Dec26 (20,000 oz)", "asof": "2026-10-09", "spot": 4195.82,
    "delivery": "Dec26", "sale_qp": "Jan27", "deadline": "2026-12-24", "days_to_deadline": 53, "default_qp": "M+1",
    "options": [{"name": "M+1", "qp_month": "Jan27", "hedged_value": 1.51}, {"name": "M+3", "qp_month": "Mar27", "hedged_value": 8.17}],
    "best": "M+3", "edge_vs_default": 6.66, "declare_now": True, "wait_value": 0.0,
    "tickets": {"M+1": [], "M+3": [{"contract": "GC Feb27", "lots": -200, "side": "SELL", "settle": 4251.5},
                                   {"contract": "GC Apr27", "lots": 200, "side": "BUY", "settle": 4286.0}]},
    "curve": [{"label": "Oct26", "settle": 4191.0}, {"label": "Apr27", "settle": 4286.0}],
    "news": [{"title": "Gold hits record on rate cut bets", "url": "x"}],
}
CALLS = []


class Cur:
    def execute(self, sql, params=None):
        CALLS.append((sql, params))

    def fetchone(self):
        return (" Gold is in contango. ",)


class Conn:
    def cursor(self):
        return Cur()

    def close(self):
        CALLS.append("closed")


def fake_connector(connect):
    sf = types.ModuleType("snowflake")
    sf.connector = types.ModuleType("snowflake.connector")
    sf.connector.connect = connect
    sys.modules["snowflake"], sys.modules["snowflake.connector"] = sf, sf.connector


def set_env():
    os.environ.update(SNOWFLAKE_ACCOUNT="acct", SNOWFLAKE_USER="u", SNOWFLAKE_API_KEY="k", SNOWFLAKE_PASSWORD="p")


def test_prompt():
    p = cortex.prompt("Gold", LIVE)
    for s in ("M+3", "Mar27", "+8.17", "+6.66", "default M+1", "declare now", "SELL 200 GC Feb27", "BUY 200 GC Apr27",
              "contango", "Gold hits record on rate cut bets", "Dec26", "2026-12-24"):
        assert s in p, s
    assert "wait" not in cortex.prompt("Gold", {**LIVE, "declare_now": True}).split("Decision:")[1].split("\n")[0]
    assert "Decision: wait" in cortex.prompt("Gold", {**LIVE, "declare_now": False})
    back = cortex.prompt("Gold", {**LIVE, "curve": LIVE["curve"][::-1]})
    assert "backwardation" in back


def test_explain_binds_parameters():
    set_env()
    CALLS.clear()
    seen = {}
    fake_connector(lambda **kw: seen.update(kw) or Conn())
    out = cortex.explain("Gold", LIVE)
    assert out and out["text"] == "Gold is in contango." and out["model"] and out["generated_at"]
    sql, params = CALLS[0]
    assert sql == "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s)"
    assert params[0] == out["model"] and "M+3" in params[1]
    assert "M+3" not in sql and "closed" in CALLS
    assert seen["account"] == "acct" and seen["user"] == "u" and seen["password"] == "k"
    json.dumps(out)


def test_failure_returns_none():
    set_env()

    def boom(**kw):
        raise RuntimeError("no network")

    fake_connector(boom)
    assert cortex.explain("Gold", LIVE) is None


def test_enabled():
    for k in cortex.KEYS:
        os.environ.pop(k, None)
    cwd = os.getcwd()
    os.chdir("/")
    try:
        assert not cortex.enabled()
        os.environ.update(SNOWFLAKE_ACCOUNT="acct", SNOWFLAKE_USER="u")
        assert not cortex.enabled()
        os.environ["SNOWFLAKE_PASSWORD"] = "p"
        assert cortex.enabled()
        seen = {}
        fake_connector(lambda **kw: seen.update(kw) or Conn())
        assert cortex.explain("Gold", LIVE) and seen["password"] == "p"
    finally:
        os.chdir(cwd)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
