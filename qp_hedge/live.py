"""Live decision support for the next cargo, from today's CME curve (fetched via Nimble).

Deterministic: expected index per fixing day from the live curve, forward value of each QP
option with financing, hedge ticket (lots per contract), and the learned declare-now-or-wait
rule. Stochastic: Monte Carlo of the index (block bootstrap of historical daily returns,
centred on the forwards) for the distribution of outcomes per QP, hedged vs unhedged.
Works for COMEX gold (GC) and NYMEX WTI (CL).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re

import numpy as np
import pandas as pd

from . import nimble, tiger
from .calendar import TradingCalendar, ltd_comex_gc, ltd_nymex_cl, month_start, ym_add, ym_label, ym_of
from .contracts import PhysicalContract

MONTHS = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}
PRODUCTS = {
    "GC": dict(cme_id="437", ltd=ltd_comex_gc, exchange="COMEX", name="Gold", unit="oz", lot=100.0, cost=0.12),
    "CL": dict(cme_id="425", ltd=ltd_nymex_cl, exchange="NYMEX", name="WTI crude", unit="bbl", lot=1000.0, cost=0.015),
}


def exchange_days(start, end) -> pd.DatetimeIndex:
    """Weekdays excluding the main US exchange holidays (published in advance)."""
    from pandas.tseries.holiday import (AbstractHolidayCalendar, GoodFriday, Holiday, USLaborDay,
                                        USMartinLutherKingJr, USMemorialDay, USPresidentsDay,
                                        USThanksgivingDay, nearest_workday)

    class _Cal(AbstractHolidayCalendar):
        rules = [Holiday("NewYear", month=1, day=1, observance=nearest_workday), USMartinLutherKingJr,
                 USPresidentsDay, GoodFriday, USMemorialDay,
                 Holiday("Juneteenth", month=6, day=19, start_date="2022-01-01", observance=nearest_workday),
                 Holiday("July4", month=7, day=4, observance=nearest_workday), USLaborDay,
                 USThanksgivingDay, Holiday("Christmas", month=12, day=25, observance=nearest_workday)]

    hol = _Cal().holidays(start, end)
    d = pd.bdate_range(start, end)
    return d[~d.isin(hol)]


def fetch_cme_settlements(product_id: str, trade_date: pd.Timestamp, cache_dir="data/cme") -> pd.DataFrame:
    """CME final settlements for one trade date (CME serves only the last few sessions,
    so we archive every pull: a point-in-time curve history that grows daily)."""
    path = os.path.join(cache_dir, f"cme_{product_id}_{trade_date:%Y%m%d}.json")
    if not os.path.exists(path):
        url = (f"https://www.cmegroup.com/CmeWS/mvc/Settlements/Futures/Settlements/{product_id}/FUT"
               f"?tradeDate={trade_date:%m/%d/%Y}")
        h = nimble.extract(url, formats=["html"])["data"].get("html") or ""
        try:
            j = json.loads(base64.b64decode(h))
        except Exception:
            j = json.loads(h)
        os.makedirs(cache_dir, exist_ok=True)
        json.dump(j, open(path, "w"))
    df = parse_cme(json.load(open(path)))
    if len(df) and tiger.enabled():
        try:
            tiger.upsert_settlements(product_id, trade_date, df)
        except Exception as e:
            logging.getLogger(__name__).warning("tiger upsert failed for %s %s: %s", product_id, trade_date.date(), e)
    return df


def parse_cme(j: dict) -> pd.DataFrame:
    """CME settlements JSON -> DataFrame with columns ym, settle, volume, oi."""
    rows = []
    for s in j.get("settlements", []):
        mm = re.match(r"([A-Z]{3}) (\d{2})", s["month"])
        if not mm or s["settle"] in ("-", ""):
            continue
        ym = (2000 + int(mm.group(2))) * 100 + MONTHS[mm.group(1)]
        num = lambda x: float(str(x).replace(",", "").rstrip("AB") or 0)
        rows.append({"ym": ym, "settle": num(s["settle"]), "volume": num(s["volume"]),
                     "oi": num(s["openInterest"])})
    return pd.DataFrame(rows, columns=["ym", "settle", "volume", "oi"]).sort_values("ym").reset_index(drop=True)


def latest_cme_curve(product_id="437", asof: pd.Timestamp | None = None, lookback=7):
    d = pd.Timestamp(asof or pd.Timestamp.today()).normalize()
    for i in range(lookback):
        day = d - pd.Timedelta(days=i)
        if day.dayofweek >= 5:
            continue
        df = fetch_cme_settlements(product_id, day)
        if len(df):
            return day, df
    raise RuntimeError("no CME settlements found")


def news(query="gold price lease rates COMEX London EFP", n=6) -> list[dict]:
    r = nimble.search(query, max_results=n)
    return [{"title": x.get("title", "")[:140], "url": x.get("url", "")} for x in r.get("results", [])[:n]]


def recommend(product: str, spot: pd.Series, rates: pd.Series, curve: pd.DataFrame, curve_date: pd.Timestamp,
              purchase: PhysicalContract, sale: PhysicalContract, delivery: int,
              funding_spread=0.015, theta: dict | None = None, vol_spread: float | None = None,
              n_paths=6000, seed=7) -> dict:
    spec = PRODUCTS[product]
    lot, cost_unit = spec["lot"], spec["cost"]
    asof = curve_date
    S0 = float(spot[spot.index <= asof].iloc[-1])
    r0 = float(rates[rates.index <= asof].iloc[-1])
    fund = r0 + funding_spread
    cal = TradingCalendar(exchange_days(asof - pd.Timedelta(days=10), asof + pd.Timedelta(days=600)))
    ltd = lambda k: spec["ltd"](cal, k)
    curve = curve.copy()
    curve["ltd"] = [ltd(k) for k in curve["ym"]]
    curve["tau"] = (curve["ltd"] - asof).dt.days / 365.0
    live = curve[(curve["tau"] > 0.005) & (curve["oi"] > 0)].reset_index(drop=True)
    # log-linear interpolation of the curve in time-to-expiry; spot anchors tau=0 for gold
    knots_t = list(live["tau"])
    knots_f = list(np.log(live["settle"]))
    if product == "GC":
        knots_t, knots_f = [0.0] + knots_t, [np.log(S0)] + knots_f
    fwd_tau = lambda t: float(np.exp(np.interp(t, knots_t, knots_f)))

    def front(d):
        k = ym_of(d)
        while ltd(k) < d:
            k = ym_add(k, 1)
        return k

    def exp_index(d):
        """Expected index on day d: gold spot = forward to d; WTI spot tracks the front future."""
        if product == "GC":
            return fwd_tau(max((d - asof).days, 0) / 365.0)
        return fwd_tau(max((ltd(front(d)) - asof).days, 0) / 365.0)

    P, Sa = purchase.for_delivery(delivery), sale.for_delivery(delivery)
    fixing_days = lambda q: exchange_days(month_start(q), month_start(ym_add(q, 1)) - pd.Timedelta(days=1))
    pay_date = lambda con, q: cal.shift(cal.last_bday_of_month(q if con.payment_rule == "after_qp" else con.delivery_month),
                                         con.payment_lag_bdays)
    qs = {o.name: P.qp_month(o.name) for o in P.qp_options}
    q_sale = Sa.qp_month(Sa.default_qp)
    horizon = max([pay_date(P, q) for q in qs.values()] + [pay_date(Sa, q_sale)])
    g = lambda d: 1 + fund * (horizon - d).days / 360.0
    deadline = cal.bdays_before(month_start(min(qs.values())), P.deadline_bdays_before_earliest_qp)
    days_left = int(((cal.dates > asof) & (cal.dates <= deadline)).sum())
    e_sale = np.mean([exp_index(d) for d in fixing_days(q_sale)])
    sale_val = (e_sale + Sa.differential) * g(pay_date(Sa, q_sale))
    prov_date = cal.shift(cal.last_bday_of_month(delivery), P.payment_lag_bdays)
    options = []
    for name, q in qs.items():
        e = np.mean([exp_index(d) for d in fixing_days(q)])
        cst = (e + P.differential + P.option(name).premium) * g(pay_date(P, q))
        if P.provisional_pct:
            cst += P.provisional_pct * exp_index(cal.last_bday_of_month(delivery)) * (g(prov_date) - g(pay_date(P, q)))
        options.append({"name": name, "qp_month": ym_label(q), "qp_ym": q, "exp_avg": e,
                        "value": sale_val - cst, "pay_date": str(pay_date(P, q).date())})

    # hedge ticket: each fixing day's exposure goes to a liquid contract alive on that day
    def hedge_month(d):
        alive = live[live["ltd"] >= d].head(3)
        if product == "CL":
            return int(alive.iloc[0]["ym"])
        return int(alive.loc[alive["oi"].idxmax(), "ym"])

    def legs(q, qty, sign):
        days = fixing_days(q)
        out = {}
        for d in days:
            k = hedge_month(d)
            out[k] = out.get(k, 0.0) + (-sign) * qty / len(days)
        return out

    tickets, plans = {}, {}
    for o in options:
        buy_leg = legs(o["qp_ym"], P.quantity, -1)     # we pay the purchase average -> long futures
        sell_leg = legs(q_sale, Sa.quantity, +1)       # we receive the sale average -> short futures
        t = dict(buy_leg)
        for k, v in sell_leg.items():
            t[k] = t.get(k, 0.0) + v
        covers = {}
        for k, v in buy_leg.items():
            covers.setdefault(k, []).append(f"purchase ({ym_label(o['qp_ym'])} average)")
        for k, v in sell_leg.items():
            covers.setdefault(k, []).append(f"sale ({ym_label(q_sale)} average)")
        tickets[o["name"]] = [{"contract": f"{product} {ym_label(k)}", "ym": k, "lots": int(round(v / lot)),
                               "side": "BUY" if v > 0 else "SELL",
                               "settle": float(live.loc[live.ym == k, "settle"].iloc[0]),
                               "covers": covers.get(k, [])}
                              for k, v in sorted(t.items()) if round(v / lot) != 0]
        # unwind schedule: as each day's price fixes, that day's share of the hedge is closed at settlement
        unwind = []
        if tickets[o["name"]]:
            for q, leg, sign, what in ((q_sale, sell_leg, +1, "sale"), (o["qp_ym"], buy_leg, -1, "purchase")):
                n_days = len(fixing_days(q))
                for k, v in sorted(leg.items()):
                    unwind.append({"month": ym_label(q), "ym": q, "contract": f"{product} {ym_label(k)}",
                                   "side": "SELL" if v > 0 else "BUY", "lots_total": int(round(abs(v) / lot)),
                                   "lots_per_day": round(P.quantity / n_days / lot, 1), "why": what})
            unwind.sort(key=lambda u: u["ym"])
        plans[o["name"]] = {"unwind": unwind,
                            "flat_by": str(fixing_days(max(o["qp_ym"], q_sale))[-1].date()) if unwind else None}
    for o in options:
        o["lots_traded"] = sum(abs(x["lots"]) for x in tickets[o["name"]])
        o["hedged_value"] = o["value"] - cost_unit * 2 * o["lots_traded"] * lot / P.quantity

    vals = np.array([o["hedged_value"] for o in options])
    order = np.argsort(vals)[::-1]
    best = int(order[0])
    dflt = [o["name"] for o in options].index(P.default_qp)
    margin = float(vals[order[0]] - vals[order[1]]) if len(vals) > 1 else np.inf

    # learned optimal-stopping rule: declare once the value of keeping the choice open is below what
    # switching hedges would cost, scaled by the learned factor and the curve's slope
    from .policies import waiting_value
    th = theta or {}
    gap = max(1, abs(P.option(options[order[0]]["name"]).month_offset - P.option(options[order[1]]["name"]).month_offset)) if len(vals) > 1 else 1
    sd = (vol_spread or 0.0) * gap / 2.0 * np.sqrt(max(days_left, 1))
    wait_val = waiting_value(margin, sd) if len(vals) > 1 else 0.0
    c1, c2 = live["settle"].iloc[0], live["settle"].iloc[1] if len(live) > 1 else live["settle"].iloc[0]
    slope = (c2 - c1) / abs(c1)
    threshold = 10.0 ** th.get("wait_k", 4.0) * 2 * cost_unit * np.exp(th.get("slope_k", 0.0) * np.clip(slope * 100, -3, 3))
    declare_now = days_left <= 0 or wait_val <= threshold

    # Monte Carlo of the index around the forwards (unhedged outcome distribution per QP)
    hist = spot[(spot.index <= asof) & (spot > 0)].dropna()
    rets = np.diff(np.log(hist.values[-252 * 15:]))
    rets = rets[np.isfinite(rets)]
    rng = np.random.default_rng(seed)
    end = max(fixing_days(q)[-1] for q in list(qs.values()) + [q_sale])
    days = exchange_days(asof + pd.Timedelta(days=1), end)
    n, blk, half = len(days), 20, n_paths // 2
    starts = rng.integers(0, len(rets) - blk, half * (n // blk + 1))
    sh = np.concatenate([rets[s:s + blk] for s in starts])[: half * n].reshape(half, n) - rets.mean()
    sh = np.concatenate([sh, -sh])                         # antithetic
    M = np.exp(np.cumsum(sh, axis=1))
    di = {d: i for i, d in enumerate(days)}

    def path_avg(q):
        ds = [d for d in fixing_days(q) if d in di]
        return (M[:, [di[d] for d in ds]] * np.array([exp_index(d) for d in ds])).mean(1)

    sale_paths = (path_avg(q_sale) + Sa.differential) * g(pay_date(Sa, q_sale))
    mc = {}
    for o in options:
        v = sale_paths - (path_avg(o["qp_ym"]) + P.differential) * g(pay_date(P, o["qp_ym"]))
        h, e = np.histogram(v, bins=40)
        mc[o["name"]] = {"mean": float(v.mean()), "std": float(v.std()),
                         **{str(p): float(np.percentile(v, p)) for p in (1, 5, 25, 50, 75, 95, 99)},
                         "hist": h.tolist(), "edges": e.round(3).tolist()}

    return {
        "product": product, "name": spec["name"], "unit": spec["unit"], "lot": lot, "exchange": spec["exchange"],
        "asof": str(asof.date()), "spot": S0, "rate": r0, "funding": fund,
        "delivery": ym_label(delivery), "deadline": str(deadline.date()), "days_to_deadline": days_left,
        "sale_qp": ym_label(q_sale), "quantity": P.quantity, "default_qp": P.default_qp,
        "options": options, "best": options[best]["name"],
        "edge_vs_default": float(vals[best] - vals[dflt]),
        "declare_now": bool(declare_now), "margin": margin, "wait_threshold": float(threshold),
        "wait_value": float(wait_val), "curve_slope": float(slope),
        "tickets": tickets, "plans": plans,
        "curve": [{"ym": int(r.ym), "label": ym_label(int(r.ym)), "settle": r.settle, "oi": r.oi,
                   "tau": r.tau, "ltd": str(r.ltd.date())} for r in curve.itertuples() if r.tau > 0],
        # inputs for the in-browser engine (contract form, risk settings)
        "days": [str(d.date()) for d in cal.dates if d > asof][:520],
        "ltd_map": {int(k): str(ltd(k).date()) for k in [ym_add(ym_of(asof), i) for i in range(-1, 26)]},
        "vol_spread": float(vol_spread or 0.0), "cost_per_unit": cost_unit, "funding_spread": funding_spread,
        "terms": {"delivery": int(delivery), "quantity": P.quantity,
                  "options": [{"name": o.name, "offset": o.month_offset, "premium": o.premium} for o in P.qp_options],
                  "default_qp": P.default_qp, "purchase_diff": P.differential,
                  "sale_offset": Sa.option(Sa.default_qp).month_offset, "sale_diff": Sa.differential,
                  "deadline_bdays": P.deadline_bdays_before_earliest_qp, "pay_lag": P.payment_lag_bdays,
                  "pay_rule": P.payment_rule, "provisional_pct": P.provisional_pct},
        "mc": {"n_paths": n_paths, "unhedged": mc},
    }
