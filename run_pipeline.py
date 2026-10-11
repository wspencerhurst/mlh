"""End-to-end: validate data -> calibrate synthetic -> train policy on synthetic ->
walk-forward historical replay vs benchmarks -> 'predict the best QP' ML test ->
contract-terms sensitivity. Writes outputs/<kind>/*.csv and outputs/results_<kind>.json.

    python run_pipeline.py gold        # primary prototype
    python run_pipeline.py crude       # second commodity (curve + basis risk)
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

import numpy as np
import pandas as pd

from qp_hedge.contracts import PhysicalContract
from qp_hedge.env import EnvConfig, option_values, run_episode
from qp_hedge.evaluate import cvar, make_episodes, run_policies, summarize
from qp_hedge.market import load_gold, load_market
from qp_hedge.ml import PlannedQP, episode_table, walk_forward_choices
from qp_hedge.policies import (FORWARD_OPTIMAL_NOW, FORWARD_OPTIMAL_WAIT, PARAM_NAMES, FixedQP,
                               ParamPolicy)
from qp_hedge.synthetic import CarryModel, CurveModel, stylized_facts
from qp_hedge.terms import random_terms
from qp_hedge.train import cem
from qp_hedge.validation import ltd_alignment_test

SETUPS = {
    "gold": dict(train=("2001-01-01", "2009-12-31"), test_from=201001, metric="pnl_bps",
                 purchase="contracts/gold_purchase.json", sale="contracts/gold_sale.json",
                 cfg=EnvConfig(cost_per_bbl=0.12, sign_months_before=2, funding_spread=0.015),
                 syn_delivery=210204),
    "crude": dict(train=("1987-01-01", "2004-12-31"), test_from=200501, metric="pnl_unit",
                  purchase="contracts/crude_purchase.json", sale="contracts/crude_sale.json",
                  cfg=EnvConfig(), syn_delivery=210205, ltd=("CL", ["CL1", "CL2", "CL3", "CL4"])),
}
BASELINE = "Forward-optimal, declare now"      # primary benchmark (deterministic)
NAIVE = "Default QP, hedged"
LAM = 0.5


def main(kind: str, n_syn: int = 160, iters: int = 8, pop: int = 24):
    S = SETUPS[kind]
    out = f"outputs/{kind}"
    os.makedirs(out, exist_ok=True)
    t0 = time.time()
    m = load_gold() if kind == "gold" else load_market(kind)
    P, Sa = PhysicalContract.load(S["purchase"]), PhysicalContract.load(S["sale"])
    cfg = S["cfg"]
    metric = S["metric"]
    print(f"[{kind}] market {m.dates[0].date()}..{m.dates[-1].date()}  ({time.time()-t0:.0f}s)")
    ltd_test = ltd_alignment_test(*S["ltd"]) if "ltd" in S else None

    # ---- synthetic: calibrate on training window only ----
    rng = np.random.default_rng(42)
    if kind == "gold":
        cm = CarryModel(m, *S["train"])
        syn_markets = [cm.simulate(rng, n_days=460, lease_sd=0.02) for _ in range(n_syn)]
        fact_fn = lambda x, a=None, b=None: _gold_facts(x, a, b)
    else:
        cm = CurveModel(m, *S["train"])
        shift_sd = float(cm.states["b"].std())
        syn_markets = [cm.simulate(rng, n_days=460, regime_shift_sd=shift_sd) for _ in range(n_syn)]
        fact_fn = stylized_facts
    facts = pd.DataFrame({
        "historical (train)": fact_fn(m, *S["train"]),
        "synthetic": pd.DataFrame([fact_fn(x) for x in syn_markets[:60]]).mean(),
        "historical (test)": fact_fn(m, S["train"][1], None),
    })
    print(facts.round(4))
    # train across randomized, realistic contract terms (one cargo per simulated market)
    syn_eps = []
    trng = np.random.default_rng(7)
    for sm in syn_markets:
        Pr, Sr, spread = random_terms(kind, trng)
        c2 = copy.deepcopy(cfg)
        c2.funding_spread = spread
        syn_eps += make_episodes(sm, Pr, Sr, c2, S["syn_delivery"], S["syn_delivery"])
    print(f"  synthetic episodes: {len(syn_eps)}   model: {cm.describe()}")

    # ---- policy search on synthetic (risk-adjusted objective, normalised P&L) ----
    theta, hist = cem(syn_eps, lam=LAM, iters=iters, pop=pop, init=FORWARD_OPTIMAL_WAIT, workers=12,
                      metric="bps" if metric == "pnl_bps" else "unit")
    print("  learned theta:", dict(zip(PARAM_NAMES, np.round(theta, 3))))

    # ---- historical replay ----
    eps = make_episodes(m, P, Sa, cfg)
    test_eps = [e for e in eps if e.delivery >= S["test_from"]]
    train_eps = [e for e in eps if e.delivery < S["test_from"]]
    d = P.default_qp
    opts = [o.name for o in P.qp_options]
    policies = [FixedQP(d, 0.0, "Default QP, unhedged"),
                FixedQP(d, 1.0, NAIVE),
                ParamPolicy(FORWARD_OPTIMAL_NOW, BASELINE),
                ParamPolicy(FORWARD_OPTIMAL_WAIT, "Forward-optimal, wait to deadline"),
                ParamPolicy(theta, "CEM-learned (synthetic-trained)")]
    if "M+1" in opts and d != "M+1":
        policies.insert(0, FixedQP("M+1", 0.0, "Matched QP (no hedge needed)"))

    tab = episode_table(eps)
    n_opt = len(opts)
    fwd_cols = [f"fwd_{o}" for o in range(n_opt)]
    plans = {"Forward-optimal at deadline, unhedged": tab[fwd_cols].values.argmax(1),
             "ML rolling-12m ridge, unhedged": walk_forward_choices(tab, n_opt, 12).values,
             "ML expanding ridge, unhedged": walk_forward_choices(tab, n_opt, None).values,
             "Last-12m most frequent winner, unhedged": walk_forward_choices(tab, n_opt, 12, kind="winner").values,
             "Perfect foresight (upper bound, NOT tradable)": tab[[f"real_{o}" for o in range(n_opt)]].values.argmax(1)}
    for name, choice in plans.items():
        policies.append(PlannedQP(pd.Series(choice, index=tab["delivery"].values), opts, 0.0, name))

    res = {}
    for label, E in (("test", test_eps), ("train", train_eps)):
        df = run_policies(E, policies)
        df.to_csv(f"{out}/episodes_{label}.csv", index=False)
        summ = summarize(df, BASELINE, LAM, metric)
        summ_naive = summarize(df, NAIVE, LAM, metric)
        summ.to_csv(f"{out}/summary_{label}.csv")
        print(f"\n  == historical replay, {label}: {len(E)} cargoes, {metric}, vs '{BASELINE}' ==")
        with pd.option_context("display.width", 220, "display.max_columns", 20):
            print(summ.round(3))
        res[label] = (df, summ, summ_naive)

    # ---- robustness: real history, randomized contract terms (seeded per cargo) ----
    rnd_eps = []
    for e in test_eps:
        Pr, Sr, spread = random_terms(kind, np.random.default_rng(e.delivery))
        c2 = copy.deepcopy(cfg)
        c2.funding_spread = spread
        rnd_eps += make_episodes(m, Pr, Sr, c2, e.delivery, e.delivery)
    df_r = run_policies(rnd_eps, [ParamPolicy(FORWARD_OPTIMAL_NOW, BASELINE),
                                  ParamPolicy(theta, "CEM-learned (synthetic-trained)"),
                                  ParamPolicy(FORWARD_OPTIMAL_WAIT, "Forward-optimal, wait to deadline")])
    summ_r = summarize(df_r, BASELINE, LAM, metric)
    print(f"\n  == randomized contract terms, real history: {len(rnd_eps)} cargoes ==")
    with pd.option_context("display.width", 220, "display.max_columns", 20):
        print(summ_r.round(3))

    # ---- hedge error by month gap: realized hedged P&L minus forward value at signing ----
    # (what a full hedge leaves behind: futures-vs-physical basis, rolls, fixing-day gaps)
    errs = {}
    for e in test_eps:
        fwd = option_values(e, 0)
        px = abs(m.front_px[e.j0 - 1])
        sale_off = next(l.contract.option(l.option).month_offset for l in e.fixed_legs if l.sign > 0)
        for i, o in enumerate(e.options):
            r = run_episode(e, FixedQP(o, 1.0))
            gap = e.decision.option(o).month_offset - sale_off
            errs.setdefault(gap, []).append(1e4 * (r["pnl"] / r["qty"] - fwd[i]) / px)
    hedge_err = {int(g): {"n": len(v), "mean_bps": float(np.mean(v)), "std_bps": float(np.std(v)),
                          "cvar5_bps": float(cvar(np.array(v)))} for g, v in sorted(errs.items())}
    vol = np.diff(np.log(m.I[np.isfinite(m.I) & (m.I > 0)][-2520:]))
    print("  hedge error by gap (bps):", {g: round(v["std_bps"], 1) for g, v in hedge_err.items()})
    ep = test_eps[-1]
    r = run_episode(ep, ParamPolicy(theta), record=True)
    r["ledger"].to_csv(f"{out}/ledger_{ep.delivery}_learned.csv")

    df_test, summ_test, summ_test_naive = res["test"]
    payload = {
        "kind": kind, "market": m.name, "unit": m.unit, "metric": metric,
        "train_window": S["train"], "test_from": S["test_from"],
        "baseline": BASELINE, "naive": NAIVE, "lambda": LAM, "ltd_test": ltd_test,
        "facts": facts.round(5).reset_index().to_dict("records"),
        "synthetic_model": {k: float(v) for k, v in cm.describe().items()},
        "theta": dict(zip(PARAM_NAMES, map(float, theta))), "cem_history": hist,
        "summary_test": summ_test.round(4).reset_index().to_dict("records"),
        "summary_test_naive": summ_test_naive.round(4).reset_index().to_dict("records"),
        "summary_train": res["train"][1].round(4).reset_index().to_dict("records"),
        "episodes_test": df_test.assign(elect_date=df_test["elect_date"].astype(str)).round(4).to_dict("records"),
        "summary_random_terms": summ_r.round(4).reset_index().to_dict("records"), "n_random": len(rnd_eps),
        "hedge_error": hedge_err, "vol_ann": float(np.std(vol) * np.sqrt(252)),
        "n_test": len(test_eps), "n_train": len(train_eps),
        "contracts": {"purchase": P.__dict__ | {"qp_options": [o.__dict__ for o in P.qp_options]},
                      "sale": Sa.__dict__ | {"qp_options": [o.__dict__ for o in Sa.qp_options]}},
        "cfg": cfg.__dict__,
    }
    with open(f"outputs/results_{kind}.json", "w") as f:
        json.dump(payload, f, default=str)
    print(f"[{kind}] done in {time.time()-t0:.0f}s")


def _gold_facts(m, start=None, end=None) -> dict:
    sel = np.ones(len(m.dates), bool)
    if start:
        sel &= m.dates >= start
    if end:
        sel &= m.dates <= end
    S = m.I[sel]
    S = S[np.isfinite(S) & (S > 0)]
    r = np.diff(np.log(S))
    rr = m.r[sel]
    b = getattr(m, "gc_basis", None)
    bsd = float(np.nanstd(b[sel]) * 100) if b is not None else np.nan
    return {"spot_vol_ann": r.std() * np.sqrt(252), "excess_kurtosis": pd.Series(r).kurt(),
            "basis_sd_pct": bsd,
            "abs_ret_autocorr": pd.Series(np.abs(r)).autocorr(),
            "max_drawdown_60d": float(pd.Series(np.log(S)).diff(60).min()),
            "mean_rate": float(np.nanmean(rr)), "rate_vol_bp": float(np.nanstd(np.diff(rr)) * np.sqrt(252) * 1e4)}


if __name__ == "__main__":
    for k in (sys.argv[1:] or ["gold"]):
        main(k)
