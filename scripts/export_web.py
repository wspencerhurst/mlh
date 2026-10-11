"""Compact engine outputs into data/desk.json for the web app (imported at build time).

    python scripts/export_web.py
"""
import json
import logging
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qp_hedge import cortex  # noqa: E402

PREV: dict = {}  # explanations already in data/desk.json, kept when Cortex is off or fails
MONTH_CODES = "FGHJKMNQUVXZ"
POLICIES = [  # (engine name, label, role)
    ("Forward-optimal, declare now", "Rule: best forward month, hedged", "baseline"),
    ("CEM-learned (synthetic-trained)", "Learned policy, hedged", "learned"),
    ("Default QP, hedged", "Default month, hedged", "default"),
    ("ML rolling-12m ridge, unhedged", "12-month ML pick, unhedged", "ml"),
]


def load(name):
    with open(os.path.join(ROOT, "outputs", name)) as f:
        return json.load(f)


def symbol(product: str, ym: int) -> str:
    return f"{product}{MONTH_CODES[ym % 100 - 1]}{str(ym // 100)[-2:]}"


def market(kind: str, product: str) -> dict:
    res, live = load(f"results_{kind}.json"), load(f"live_{kind}.json")
    by = {}
    for r in res["episodes_test"]:
        by.setdefault(r["policy"], []).append(r)
    track = []
    for name, label, role in POLICIES:
        rows = sorted(by.get(name, []), key=lambda r: r["delivery"])
        cum, pts = 0.0, []
        for r in rows:
            cum += r["pnl"] / 1e6
            pts.append([r["delivery"], round(cum, 4), round(r["pnl"] / 1e6, 4), r["elected"]])
        track.append({"label": label, "role": role, "points": pts})
    summ = {r["policy"]: r for r in res["summary_test"]}
    score = []
    for name, label, role in POLICIES:
        s = summ.get(name)
        if s:
            score.append({"label": label, "role": role, "mean": s["mean"], "std": s["std"], "worst": s["worst"],
                          "vs_base": s["vs_bench_mean"], "ci_lo": s["vs_bench_ci_lo"], "ci_hi": s["vs_bench_ci_hi"],
                          "win": s["win_rate"]})
    keep = ("asof", "spot", "rate", "funding", "delivery", "deadline", "days_to_deadline", "sale_qp", "quantity",
            "default_qp", "options", "best", "edge_vs_default", "declare_now", "margin", "wait_threshold",
            "tickets", "plans", "curve", "unit", "lot", "exchange", "deal", "name", "product",
            "days", "ltd_map", "vol_spread", "cost_per_unit", "funding_spread", "terms",
            "basis_z", "curve_slope", "wait_value")
    lv = {k: live[k] for k in keep if k in live}
    lv["outcomes"] = live["mc"]["unhedged"]
    lv["vol_ann"] = res.get("vol_ann")
    lv["hedge_err"] = res.get("hedge_err") or res.get("hedge_error")
    lv["n_paths"] = live["mc"]["n_paths"]
    for legs in lv["tickets"].values():
        for t in legs:
            t["symbol"] = symbol(product, t["ym"])
    ex = (cortex.explain(live["name"], live) if cortex.enabled() else None) or PREV.get(kind)
    if ex:
        lv["explanation"] = ex
    deliveries = [p[0] for p in track[0]["points"]]
    return {"product": product, "name": live["name"], "unit": live["unit"],
            "metric": "bps" if res.get("metric") == "pnl_bps" else f"$/{live['unit']}",
            "test_period": f"{deliveries[0] // 100}–{deliveries[-1] // 100}", "n_test": res["n_test"],
            "train_window": res["train_window"], "live": lv, "track": track, "scorecard": score,
            "theta": res["theta"], "lambda": res.get("lambda", 0.5),
            "policy_choice": OVERRIDE.get(kind, policy_choice(res)),
            "policy_basis": "override" if kind in OVERRIDE else "training",
            "random_terms": random_summary(res)}


# Desk decision to deploy the learned policy despite the training-period gate. Gold: it beat the rule
# out of sample (+1.7 bps, smaller worst case) but its training-period edge was not statistically clear.
OVERRIDE = {"gold": "learned"}


def policy_choice(res) -> str:
    """Deploy the learned policy only if it beat the rule in the TRAINING-period replay (no test leakage)."""
    row = next((r for r in res.get("summary_train", []) if r["policy"] == "CEM-learned (synthetic-trained)"), None)
    return "learned" if row and row["vs_bench_ci_lo"] > 0 else "rule"


def random_summary(res):
    rows = {r["policy"]: r for r in res.get("summary_random_terms", [])}
    r = rows.get("CEM-learned (synthetic-trained)")
    return None if not r else {"n": res.get("n_random"), "vs_rule": r["vs_bench_mean"], "ci_lo": r["vs_bench_ci_lo"],
                               "ci_hi": r["vs_bench_ci_hi"]}


def previous_explanations() -> dict:
    try:
        with open(os.path.join(ROOT, "data", "desk.json")) as f:
            ms = json.load(f)["markets"]
        return {k: m["live"]["explanation"] for k, m in ms.items() if m["live"].get("explanation")}
    except (OSError, ValueError, KeyError):
        return {}


def main():
    PREV.update(previous_explanations())
    props = load("proposals.json")
    for p in props:
        d = p["details"]
        p["market"] = "gold" if d.get("unit") == "oz" else "crude"
        if p["kind"] == "FUTURES_ORDER":
            prod = d["instrument"].split(" ")[0]
            sym = None
            for legs in load(f"live_{p['market']}.json")["tickets"].values():
                for t in legs:
                    if t["contract"] == d["instrument"]:
                        sym = symbol(prod, t["ym"])
            p["checker"] = {"instrumentPair": sym, "side": d["side"], "quantity": d["lots"],
                            "clientOrderId": p["id"], "tags": ["qp-hedge"]}
    out = {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "markets": {"gold": market("gold", "GC"), "crude": market("crude", "CL")},
           "proposals": props}
    path = os.path.join(ROOT, "data", "desk.json")
    with open(path, "w") as f:
        json.dump(out, f, separators=(",", ":"), default=float)
    print(f"{path}  {os.path.getsize(path) / 1024:.0f} KB")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
