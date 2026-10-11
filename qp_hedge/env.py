"""Episode precomputation (deterministic engine) and the daily replay environment.

Timing convention (no look-ahead):
  * The agent acts on trading day t using information through the settlement of t-1.
  * Futures trades execute at the settlement price of day t (Trade-At-Settlement,
    which NYMEX offers for CL and HO), paying a per-bbl cost.
  * The index fixing of day t is the published index for day t.

Everything in this module is deterministic given prices and the agent's actions:
fixing schedules, exposure (futures-equivalent delta by contract month), forward
valuation of each QP option, financing, hedge sizing, lot rounding, risk limits,
execution, variation margin and the P&L ledger.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .calendar import month_start, ym_add
from .contracts import Book, PhysicalContract
from .market import MarketData

WARMUP = 260  # trading days of history required before the signing date


@dataclass
class EnvConfig:
    cost_per_bbl: float = 0.015        # commission + half bid/ask on TAS, per bbl per side
    max_lots_per_month: int = 2_000    # per-contract-month position limit (lots)
    max_gross_lots: int = 3_000        # gross futures position limit (lots)
    max_open_delta_bbl: float = 1e12   # flat-price risk limit on un-hedged delta (off by default)
    sign_months_before: int = 3        # book (and decision window) opens on first bday of M-3
    rate: float | None = None          # financing rate (simple, act/360); None -> market rate
    funding_spread: float = 0.0        # trader's funding spread over the market short rate
    record: bool = False               # keep a daily ledger (for audit / verification)


@dataclass
class Action:
    elect: str | None = None           # declare this QP now (irrevocable)
    provisional: str | None = None     # QP to hedge as if elected (before declaring)
    hedge_ratio: float = 1.0           # fraction of the deterministic min-variance hedge


@dataclass
class Obs:
    date: pd.Timestamp                 # execution day t (info is through t-1)
    can_elect: bool
    bdays_to_deadline: int
    elected: str | None
    options: list[str]
    offsets: np.ndarray                # QP month offsets of the options
    sale_offset: int
    default: str
    opt_value: np.ndarray              # forward-implied deal value, $/bbl, financed, per option
    price: float                       # front futures price
    vol_front: float                   # daily $ stdev of front futures (60d)
    vol_spread: float                  # daily $ stdev of C3-C1 spread changes (60d)
    slope: float                       # (C2-C1)/C1
    slope_mom: float                   # 20-day change in slope
    beta: float                        # min-variance hedge ratio index~futures (250d)
    basis_z: float                     # index-vs-futures gap, z-score vs trailing 250d
    switch_cost: float                 # cost per unit of re-hedging (both sides)
    history: "HistoryView"


class HistoryView:
    """Read-only access to market history strictly up to row `j_last`."""

    def __init__(self, market: MarketData, j_last: int):
        self._m, self._j = market, j_last

    def series(self, name: str, n: int) -> np.ndarray:
        arr = getattr(self._m, name)
        return np.asarray(arr[max(0, self._j - n + 1): self._j + 1])


@dataclass
class Leg:
    contract: PhysicalContract
    option: str
    sign: int
    qty: float
    adder: float                 # differential + premium
    N: int                       # number of fixing days
    R: np.ndarray                # [T+1, K] remaining fixing days after local t, by contract
    S: np.ndarray                # [T+1] sum of fixings through local t
    nfix: np.ndarray             # [T+1] number of fixings through local t
    g_pay: float                 # financing factor from payment date to horizon
    pay_date: pd.Timestamp
    prov_pct: float = 0.0        # provisional payment fraction (paid at arrival)
    g_prov: float = 1.0          # financing factor of the provisional payment date
    prov_t: int = 0              # local t when the provisional price is known
    prov_k: int = 0              # contract the provisional price tracks before then
    prov_px: float = np.nan      # realized provisional price


@dataclass
class EpisodeData:
    market: MarketData
    book: Book
    cfg: EnvConfig
    delivery: int
    j0: int
    jE: int
    dates: pd.DatetimeIndex      # local t=0..T  <->  global j0-1 .. jE
    months: list[int]
    F: np.ndarray                # [T+1, K]
    I: np.ndarray                # [T+1]
    ltd: np.ndarray              # [K] datetime64
    g: np.ndarray                # [T+1] financing factor to horizon
    deadline: pd.Timestamp
    horizon: pd.Timestamp
    fixed_legs: list[Leg]
    opt_legs: list[Leg]          # one per option of the decision contract
    decision: PhysicalContract
    options: list[str] = field(default_factory=list)


def build_episode(market: MarketData, book: Book, cfg: EnvConfig) -> EpisodeData | None:
    dec = book.decision
    M = dec.delivery_month
    cal = market.cal
    sign_date = cal.first_bday_of_month(ym_add(M, -cfg.sign_months_before))
    if cfg.rate is not None:
        rate = cfg.rate
    elif market.r is not None:   # term funding locked at signing: point-in-time
        rate = float(market.r[max(0, market.j_of(sign_date) - 1)]) + cfg.funding_spread
    else:
        rate = market.rate + cfg.funding_spread
    qmonths = [c.qp_month(o.name) for c in book.contracts for o in c.qp_options]
    q_lo, q_hi = min(dec.qp_month(o.name) for o in dec.qp_options), max(qmonths)
    deadline = cal.bdays_before(month_start(q_lo), dec.deadline_bdays_before_earliest_qp)
    j0 = market.j_of(sign_date)
    jE = market.j_of(month_start(ym_add(q_hi, 1))) - 1
    if j0 < WARMUP or market.j_of(month_start(ym_add(q_hi, 1))) >= len(market.dates):
        return None  # not enough history before, or the last QP is not fully observed
    js = np.arange(j0 - 1, jE + 1)
    dates = market.dates[js]
    months = []
    k = market.front[j0 - 1]
    while k <= market.front[jE]:
        months.append(k)
        k = ym_add(k, 1)
    kidx = {m: i for i, m in enumerate(months)}
    F = np.column_stack([market.F[js, market.col[m]] if m in market.col else np.full(len(js), np.nan)
                         for m in months])
    I = market.I[js]

    pays = {}
    for c in book.contracts:
        for o in c.qp_options:
            q = c.qp_month(o.name)
            base = cal.last_bday_of_month(q if c.payment_rule == "after_qp" else c.delivery_month)
            pays[(c.contract_id, o.name)] = cal.shift(base, c.payment_lag_bdays)
    horizon = max(pays.values())
    g = 1.0 + rate * (horizon - dates).days.values / 360.0

    def make_leg(c: PhysicalContract, oname: str) -> Leg:
        q = c.qp_month(oname)
        fj = np.arange(market.j_of(month_start(q)), market.j_of(month_start(ym_add(q, 1))))
        fk = np.array([kidx[market.front[j]] for j in fj])
        t_of = fj - (j0 - 1)
        T1 = len(js)
        R = np.zeros((T1, len(months)))
        S = np.zeros(T1)
        nfix = np.zeros(T1)
        for tf, kf, j in zip(t_of, fk, fj):
            R[:tf, kf] += 1        # planned (exchange) day still to fix for local t < tf
            if np.isfinite(market.I[j]):   # realized: only days the index was published
                S[tf:] += market.I[j]
                nfix[tf:] += 1
        pay = pays[(c.contract_id, oname)]
        leg = Leg(c, oname, c.sign, c.quantity, c.differential + c.option(oname).premium,
                  len(fj), R, S, nfix, 1.0 + rate * (horizon - pay).days / 360.0, pay)
        if c.provisional_pct > 0:
            pd_ = cal.last_bday_of_month(c.delivery_month)          # arrival / provisional pricing
            pj = min(market.j_of(pd_), jE)
            leg.prov_pct = c.provisional_pct
            leg.g_prov = 1.0 + rate * (horizon - cal.shift(pd_, c.payment_lag_bdays)).days / 360.0
            leg.prov_t = pj - (j0 - 1)
            leg.prov_k = kidx.get(market.front[pj], 0)
            back = market.I[max(0, pj - 5): pj + 1]
            back = back[np.isfinite(back)]
            leg.prov_px = back[-1] if len(back) else np.nan
        return leg

    fixed = [make_leg(c, c.default_qp) for c in book.contracts if c is not dec]
    opts = [make_leg(dec, o.name) for o in dec.qp_options]
    if min(l.nfix[-1] for l in fixed + opts) < 5:
        return None  # index essentially unpublished in a QP month
    ltd = np.array([np.datetime64(market.ltd(m)) for m in months])
    return EpisodeData(market, book, cfg, M, j0, jE, dates, months, F, I, ltd, g, deadline,
                       horizon, fixed, opts, dec, [o.name for o in dec.qp_options])


# ---- deterministic valuation ----------------------------------------------------

def _px_row(F_row: np.ndarray, basis_hat: float) -> np.ndarray:
    """Forward price per contract month; months not yet listed are extrapolated flat
    from the last listed month (and hedged there: 'stack and roll')."""
    p = F_row.copy()
    fin = np.where(np.isfinite(p))[0]
    if len(fin) == 0:
        return np.full_like(p, np.nan)
    p[: fin[0]] = p[fin[0]]
    for i in range(fin[0] + 1, len(p)):
        if not np.isfinite(p[i]):
            p[i] = p[i - 1]
    return p + basis_hat


def leg_value(leg: Leg, t: int, px: np.ndarray) -> float:
    """Financed value at the horizon of a pricing leg using info through local t."""
    rem = leg.R[t]
    exp_avg = (leg.S[t] + rem @ px) / (leg.nfix[t] + rem.sum())
    v = (exp_avg + leg.adder) * leg.g_pay
    if leg.prov_pct:
        p = leg.prov_px if t >= leg.prov_t else px[leg.prov_k]
        v += leg.prov_pct * p * (leg.g_prov - leg.g_pay)   # financing cost of paying early
    return leg.sign * leg.qty * v


def leg_realized(leg: Leg) -> float:
    """Financed realized value of a leg after all fixings."""
    T = len(leg.S) - 1
    v = (leg.S[T] / leg.nfix[T] + leg.adder) * leg.g_pay
    if leg.prov_pct:
        v += leg.prov_pct * leg.prov_px * (leg.g_prov - leg.g_pay)
    return leg.sign * leg.qty * v


def leg_exposure(leg: Leg, t: int, g_t: float) -> np.ndarray:
    """Futures-equivalent price exposure (bbl, + = long price) by contract month for
    fixings after local t, tailed for financing."""
    return leg.sign * leg.qty * leg.R[t] / (leg.nfix[t] + leg.R[t].sum()) * leg.g_pay / g_t


def option_values(ep: EpisodeData, t: int) -> np.ndarray:
    """Forward-implied financed deal value ($/bbl) per QP option, info through local t."""
    j = ep.j0 - 1 + t
    px = _px_row(ep.F[t], ep.market.basis_hat[j])
    fixed = sum(leg_value(l, t, px) for l in ep.fixed_legs)
    return np.array([(fixed + leg_value(l, t, px)) / ep.decision.quantity for l in ep.opt_legs])


def realized_values(ep: EpisodeData) -> np.ndarray:
    """Realized financed deal value ($/bbl) per QP option if left unhedged (ex post)."""
    fixed = sum(leg_realized(l) for l in ep.fixed_legs)
    return np.array([(fixed + leg_realized(l)) / ep.decision.quantity for l in ep.opt_legs])


def deadline_t(ep: EpisodeData) -> int:
    return int(np.searchsorted(ep.dates.values, np.datetime64(ep.deadline), "left"))


# ---- environment ----------------------------------------------------------------

def run_episode(ep: EpisodeData, policy, record: bool | None = None) -> dict:
    m, cfg = ep.market, ep.cfg
    record = cfg.record if record is None else record
    K, T = len(ep.months), len(ep.dates) - 1
    lot = m.lot
    pos = np.zeros(K)
    for ym, q in ep.book.futures.items():
        if ym in ep.months:
            pos[ep.months.index(ym)] = q
    last_px = ep.F[0].copy()
    cash_vm = cash_cost = vm_raw = cost_raw = 0.0
    elected, elect_date = None, None
    names = ep.options
    dec_q = ep.decision.quantity
    offsets = np.array([ep.decision.option(o).month_offset for o in names])
    sale_off = next((l.contract.option(l.option).month_offset for l in ep.fixed_legs if l.sign > 0), 0)
    policy.reset(ep)
    rows = []
    rewards = []
    px0 = _px_row(ep.F[0], m.basis_hat[ep.j0 - 1])
    mtm0 = sum(leg_value(l, 0, px0) for l in ep.fixed_legs + [ep.opt_legs[names.index(ep.decision.default_qp)]])
    mtm_prev = mtm0
    for t in range(1, T + 1):
        j = ep.j0 - 1 + t
        date = ep.dates[t]
        # --- observation (info through t-1) ---
        px_prev = _px_row(ep.F[t - 1], m.basis_hat[j - 1])
        fixed_val = sum(leg_value(l, t - 1, px_prev) for l in ep.fixed_legs)
        opt_val = np.array([(fixed_val + leg_value(l, t - 1, px_prev)) / dec_q for l in ep.opt_legs])
        can_elect = elected is None and date <= ep.deadline
        obs = Obs(date, can_elect, max(0, m.cal.pos(ep.deadline) - m.cal.pos(date)) if can_elect else -1,
                  elected, names, offsets, sale_off, ep.decision.default_qp, opt_val,
                  m.front_px[j - 1], m.vol_front[j - 1], m.vol_spread[j - 1], m.slope[j - 1],
                  m.slope_mom[j - 1], m.beta[j - 1], m.basis_z[j - 1], 2 * cfg.cost_per_bbl, HistoryView(m, j - 1))
        act: Action = policy.act(obs)
        if can_elect and act.elect in names:
            elected, elect_date = act.elect, date
        prov = elected or (act.provisional if act.provisional in names else ep.decision.default_qp)
        legs = ep.fixed_legs + [ep.opt_legs[names.index(prov)]]

        # --- variation margin on yesterday's positions ---
        Ft = ep.F[t]
        ok = np.isfinite(Ft)
        held = ok & (pos != 0)
        vm = float(np.sum(pos[held] * (Ft[held] - last_px[held])))
        last_px[ok] = Ft[ok]
        vm_raw += vm
        cash_vm += vm * ep.g[t]

        # --- deterministic hedge target ---
        expo = sum(leg_exposure(l, t, ep.g[t]) for l in legs)
        beta = m.beta[j - 1]
        h = float(np.clip(act.hedge_ratio, 0.0, 1.5))
        net = beta * expo.sum()
        if abs((1 - h) * net) > cfg.max_open_delta_bbl:          # risk limit
            h = 1 - np.sign(1 - h) * cfg.max_open_delta_bbl / abs(net)
        alive = (ep.ltd >= np.datetime64(date)) & np.isfinite(ep.F[t - 1])
        stackable = alive & (ep.ltd > np.datetime64(date))
        target = np.zeros(K)
        for k in range(K):
            if expo[k] == 0:
                continue
            kk = k
            if not stackable[k]:  # not yet listed -> hedge in nearest earlier listed month
                cand = np.where(stackable[:k])[0]
                cand = cand if len(cand) else np.where(stackable)[0]
                kk = cand[-1] if len(cand) else k
            target[kk] += -beta * h * expo[k]
        target = np.clip(target, -cfg.max_lots_per_month * lot, cfg.max_lots_per_month * lot)
        gross = np.abs(target).sum()
        if gross > cfg.max_gross_lots * lot:
            target *= cfg.max_gross_lots * lot / gross
        target = np.round(target / lot) * lot
        target[~alive] = 0.0
        expiring = ep.ltd == np.datetime64(date)
        target[expiring] = 0.0
        trade = target - pos
        trade[~ok & ~expiring] = 0.0  # no price today: cannot trade (data gap)
        cost = float(np.abs(trade).sum() * cfg.cost_per_bbl)
        cost_raw += cost
        cash_cost += cost * ep.g[t]
        pos = pos + trade

        # --- mark to market (info through t) ---
        px_t = _px_row(ep.F[t], m.basis_hat[j])
        phys = sum(leg_value(l, t, px_t) for l in legs)
        mtm = cash_vm - cash_cost + phys
        rewards.append(mtm - mtm_prev)   # dense reward: change in financed MTM
        mtm_prev = mtm
        if record:
            rows.append({"date": date, "provisional": prov, "elected": elected, "hedge_ratio": h,
                         "beta": beta, "index": ep.I[t], "vm": vm, "cost": cost, "mtm": mtm,
                         **{f"F_{mm}": ep.F[t, i] for i, mm in enumerate(ep.months)},
                         **{f"pos_{mm}": pos[i] for i, mm in enumerate(ep.months)},
                         **{f"trade_{mm}": trade[i] for i, mm in enumerate(ep.months)}})
        if elected is None and date >= ep.deadline:
            elected, elect_date = ep.decision.default_qp, date   # default applies

    # all fixings done -> physical legs are realized; close any residual futures
    if np.any(pos != 0):
        cost = float(np.abs(pos).sum() * cfg.cost_per_bbl)
        cost_raw += cost
        cash_cost += cost * ep.g[T]
        pos[:] = 0
    legs = ep.fixed_legs + [ep.opt_legs[names.index(elected)]]
    phys_fin = sum(leg_realized(l) for l in legs)
    phys_raw = sum(l.sign * l.qty * (l.S[T] / l.nfix[T] + l.adder) for l in legs)
    total = phys_fin + cash_vm - cash_cost
    rewards.append(total - mtm_prev)
    out = {
        "delivery": ep.delivery, "elected": elected, "elect_date": elect_date,
        "pnl": total, "physical": phys_raw, "futures": vm_raw, "costs": -cost_raw,
        "financing": (phys_fin - phys_raw) + (cash_vm - vm_raw) - (cash_cost - cost_raw),
        "qty": dec_q, "rewards": np.array(rewards), "mtm0": mtm0,
        "notional": dec_q * abs(m.front_px[ep.j0 - 1]),
    }
    if record:
        out["ledger"] = pd.DataFrame(rows).set_index("date")
    return out
