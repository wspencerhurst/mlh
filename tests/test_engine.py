"""Core guarantees of the replay engine.

  1. No look-ahead: scrambling all prices after date D cannot change any action taken on or
     before D (actions on day t may only use information through t-1).
  2. Accounting: physical + futures + costs + financing == total P&L, and the dense
     step rewards telescope to realized P&L minus the opening mark.
Run:  python -m pytest -q   (or: python tests/test_engine.py)
"""
from __future__ import annotations

import copy
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qp_hedge.contracts import Book, PhysicalContract
from qp_hedge.env import EnvConfig, build_episode, run_episode
from qp_hedge.market import load_gold
from qp_hedge.policies import FORWARD_OPTIMAL_WAIT, ParamPolicy

CFG = EnvConfig(cost_per_bbl=0.12, sign_months_before=2, funding_spread=0.015)
P = PhysicalContract.load("contracts/gold_purchase.json")
S = PhysicalContract.load("contracts/gold_sale.json")
_M = None


def market():
    global _M
    if _M is None:
        _M = load_gold()
    return _M


class Recorder(ParamPolicy):
    def reset(self, ep):
        super().reset(ep)
        self.log = []

    def act(self, obs):
        a = super().act(obs)
        self.log.append((obs.date, a.elect, a.provisional, a.hedge_ratio, tuple(np.round(obs.opt_value, 9))))
        return a


def test_no_lookahead():
    m = market()
    ym = 202003
    ep = build_episode(m, Book([P.for_delivery(ym), S.for_delivery(ym)]), CFG)
    cut = ep.dates[len(ep.dates) // 2]
    pol = Recorder(FORWARD_OPTIMAL_WAIT)
    run_episode(ep, pol)
    base = [x for x in pol.log if x[0] <= cut]

    m2 = copy.deepcopy(m)
    j = m2.j_of(cut) + 1                      # everything strictly after `cut`
    rng = np.random.default_rng(0)
    m2.F[j:] *= rng.uniform(0.5, 1.5, size=m2.F[j:].shape)
    m2.I[j:] *= rng.uniform(0.5, 1.5, size=m2.I[j:].shape)
    m2._features()
    ep2 = build_episode(m2, Book([P.for_delivery(ym), S.for_delivery(ym)]), CFG)
    pol2 = Recorder(FORWARD_OPTIMAL_WAIT)
    run_episode(ep2, pol2)
    pert = [x for x in pol2.log if x[0] <= cut]
    assert base == pert, "an action on/before the cut depended on later prices"


def test_accounting_identities():
    m = market()
    for ym in (200803, 201506, 202503):
        ep = build_episode(m, Book([P.for_delivery(ym), S.for_delivery(ym)]), CFG)
        r = run_episode(ep, ParamPolicy(FORWARD_OPTIMAL_WAIT))
        parts = r["physical"] + r["futures"] + r["costs"] + r["financing"]
        assert abs(parts - r["pnl"]) < 1e-6
        assert abs(r["rewards"].sum() + r["mtm0"] - r["pnl"]) < 1e-6


if __name__ == "__main__":
    test_no_lookahead()
    test_accounting_identities()
    print("ok")
