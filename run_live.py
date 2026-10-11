"""Live recommendations for the next gold and crude cargoes.

    python run_live.py            -> outputs/live_gold.json, outputs/live_crude.json, outputs/proposals.json
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from qp_hedge.calendar import ym_add, ym_of
from qp_hedge.contracts import PhysicalContract
from qp_hedge.live import PRODUCTS, latest_cme_curve, news, recommend
from qp_hedge.market import load_eia_series, load_fred, load_gold, load_gold_spot, load_market
from qp_hedge.proposals import from_live, save

SETUP = {
    "gold": dict(product="GC", purchase="contracts/gold_purchase.json", sale="contracts/gold_sale.json",
                 months_ahead=2, deal="AU doré cargo", news="gold price COMEX London premium lease rates"),
    "crude": dict(product="CL", purchase="contracts/crude_purchase.json", sale="contracts/crude_sale.json",
                  months_ahead=3, deal="WTI cargo", news="WTI crude oil futures curve contango backwardation"),
}


def run(kind: str) -> dict:
    S = SETUP[kind]
    spec = PRODUCTS[S["product"]]
    rates = load_fred("DTB3")
    if kind == "gold":
        spot, m = load_gold_spot(), load_gold()
    else:
        spot, m = load_eia_series("WTI_SPOT"), load_market("crude")
    day, curve = latest_cme_curve(spec["cme_id"])
    delivery = ym_add(ym_of(day), S["months_ahead"])
    res_path = f"outputs/results_{kind}.json"
    theta = json.load(open(res_path))["theta"] if os.path.exists(res_path) else None
    vs = m.vol_spread[-500:]
    P, Sa = PhysicalContract.load(S["purchase"]), PhysicalContract.load(S["sale"])
    rec = recommend(S["product"], spot, rates, curve, day, P, Sa, delivery,
                    theta=theta, vol_spread=float(np.nanmedian(vs)))
    rec["deal"] = f"{S['deal']} {rec['delivery']} ({int(rec['quantity']):,} {rec['unit']})"
    # today's index-vs-futures gap as a z-score (gold: spot vs COMEX; crude history ends 2024, so neutral)
    rec["basis_z"] = float(m.basis_z[-1]) if kind == "gold" else 0.0
    try:
        rec["news"] = news(S["news"], 4)
    except Exception as e:  # context only; never block a recommendation
        rec["news"] = []
        print("news unavailable:", e)
    with open(f"outputs/live_{kind}.json", "w") as f:
        json.dump(rec, f, default=float)
    print(f"[{kind}] {rec['deal']}: declare {rec['best']} ({'now' if rec['declare_now'] else 'at deadline'}), "
          f"edge vs default {rec['edge_vs_default']:+.2f}/{rec['unit']}, margin {rec['margin']:.2f} vs wait threshold {rec['wait_threshold']:.2f}")
    for o in rec["options"]:
        print("   ", o["name"], o["qp_month"], round(o["hedged_value"], 2), rec["tickets"][o["name"]])
    return rec


if __name__ == "__main__":
    recs = [run(k) for k in ("gold", "crude")]
    save([p for r in recs for p in from_live(r, r["deal"])], "outputs/proposals.json")
