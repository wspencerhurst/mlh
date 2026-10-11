"""Plain-English summary of a daily recommendation, written by Snowflake Cortex AI.

Calls SNOWFLAKE.CORTEX.COMPLETE through snowflake-connector-python. Credentials come from the
SNOWFLAKE_ACCOUNT / SNOWFLAKE_USER env vars plus SNOWFLAKE_API_KEY (a programmatic access token)
or SNOWFLAKE_PASSWORD (optional SNOWFLAKE_WAREHOUSE, SNOWFLAKE_ROLE) or a local .env file; the model from SNOWFLAKE_CORTEX_MODEL. Nothing is written into code
or outputs. Any failure is logged and yields None, so callers fall back to no summary.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

log = logging.getLogger(__name__)
DEFAULT_MODEL = "claude-sonnet-4-5"
REQUIRED = ("SNOWFLAKE_ACCOUNT", "SNOWFLAKE_USER")
SECRETS = ("SNOWFLAKE_API_KEY", "SNOWFLAKE_PASSWORD")
OPTIONAL = ("SNOWFLAKE_WAREHOUSE", "SNOWFLAKE_ROLE")
KEYS = REQUIRED + SECRETS + OPTIONAL + ("SNOWFLAKE_CORTEX_MODEL",)


def _env() -> dict:
    out = {k: os.environ[k] for k in KEYS if os.environ.get(k)}
    d = os.path.abspath(os.getcwd())
    while True:  # nearest .env in this or a parent directory (keeps keys out of the repo)
        p = os.path.join(d, ".env")
        if os.path.exists(p):
            for line in open(p):
                k, _, v = line.strip().partition("=")
                if k in KEYS and k not in out and v.strip():
                    out[k] = v.strip().strip("\"'")
        if os.path.dirname(d) == d:
            break
        d = os.path.dirname(d)
    return out


def enabled() -> bool:
    e = _env()
    return all(k in e for k in REQUIRED) and any(k in e for k in SECRETS)


def connect(**kw):
    import snowflake.connector

    e = _env()
    # a programmatic access token is accepted in place of the password
    secret = e.get("SNOWFLAKE_API_KEY") or e["SNOWFLAKE_PASSWORD"]
    return snowflake.connector.connect(password=secret, **{k[10:].lower(): e[k] for k in REQUIRED + OPTIONAL if k in e}, **kw)


def prompt(market: str, live: dict) -> str:
    unit = live.get("unit", "")
    opts = live["options"]
    best = next(o for o in opts if o["name"] == live["best"])
    dflt = next((o for o in opts if o["name"] == live.get("default_qp")), None)
    lines = [f"Market: {market} ({live.get('exchange', '')}), deal: {live.get('deal', '')}, as of {live.get('asof', '')}.",
             f"Spot {live['spot']:.2f}. Purchase delivery {live['delivery']}, sale priced on the {live['sale_qp']} average. "
             f"Declaration deadline {live['deadline']} ({live['days_to_deadline']} days).",
             f"Quotation period options, hedged deal value in $/{unit}:"]
    lines += [f"- {o['name']} ({o['qp_month']} average): {o['hedged_value']:+.2f}" for o in opts]
    lines.append(f"Chosen: {best['name']} ({best['qp_month']} average)"
                 + (f", {live['edge_vs_default']:+.2f} $/{unit} better than the default {dflt['name']}." if dflt else "."))
    lines.append("Decision: declare now." if live["declare_now"] else
                 f"Decision: wait to declare until the deadline ({live['wait_value']:+.3f} $/{unit} option value), hedge now.")
    legs = live.get("tickets", {}).get(best["name"], [])
    lines.append("Hedge: " + (", ".join(f"{t['side']} {abs(t['lots'])} {t['contract']} at {t['settle']:.2f}" for t in legs)
                              if legs else "none needed."))
    c = live.get("curve") or []
    if len(c) > 1:
        shape = "contango (later months higher)" if c[-1]["settle"] > c[0]["settle"] else "backwardation (later months lower)"
        lines.append(f"Futures curve: {c[0]['label']} {c[0]['settle']:.2f} to {c[-1]['label']} {c[-1]['settle']:.2f}, {shape}.")
    heads = [h.get("title", "") for h in live.get("news") or []]
    if any(heads):
        lines.append("Recent headlines:\n" + "\n".join(f"- {h}" for h in heads if h))
    return ("You are writing for a physical commodity trader. Explain in 3 to 4 plain sentences why this quotation "
            "period is recommended, whether to declare now or wait, what the hedge does, and what the curve shape and "
            "headlines imply. Use only numbers that appear below. No advice disclaimers, no headings, no bullet points.\n\n"
            + "\n".join(lines))


def explain(market: str, live: dict) -> dict | None:
    try:
        e = _env()
        model = e.get("SNOWFLAKE_CORTEX_MODEL", DEFAULT_MODEL)
        conn = connect()
        try:
            cur = conn.cursor()
            cur.execute("SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s)", (model, prompt(market, live)))
            text = str(cur.fetchone()[0]).strip()
        finally:
            conn.close()
        if not text:
            raise RuntimeError("empty completion")
        return {"text": text, "model": model, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    except Exception as ex:
        log.warning("Cortex explanation failed for %s: %s", market, ex)
        return None
