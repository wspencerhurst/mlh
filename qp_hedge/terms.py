"""Randomized but realistic contract terms, for training and robustness tests.

Ranges follow common physical practice:
  gold (dore / concentrate payable gold): 5k-50k oz, QP declared among 2-4 consecutive months
    from M to M+4, final payment 3-10 business days after the QP, provisional payment of 0%,
    50% or 90% at arrival, small seller premium for later months in some deals;
  crude (WTI cargoes / pipeline barrels): 300k-1M bbl, QP among months M-1..M+2, payment either
    after the QP or after delivery, no provisional payment.
The sale side is priced on one of the purchase's QP months (a back-to-back resale).
"""
from __future__ import annotations

import numpy as np

from .contracts import PhysicalContract, QPOption

GOLD_SETS = [[1, 2, 3], [0, 1, 2], [1, 2], [1, 2, 3, 4]]
CRUDE_SETS = [[-1, 0, 1], [0, 1], [-1, 0, 1, 2], [0, 1, 2]]


def _name(off: int) -> str:
    return "M" if off == 0 else f"M{off:+d}"


def random_terms(kind: str, rng: np.random.Generator) -> tuple[PhysicalContract, PhysicalContract, float]:
    """Returns (purchase, sale, funding_spread)."""
    if kind == "gold":
        offs = GOLD_SETS[rng.integers(len(GOLD_SETS))]
        qty = float(rng.integers(5, 51) * 1000)
        prov = float(rng.choice([0.0, 0.0, 0.5, 0.9]))
        diff_s = float(rng.uniform(0.5, 3.0))
        prem_unit = float(rng.uniform(0.0, 0.3)) if rng.random() < 0.3 else 0.0
        pay_rule = "after_qp"
        index = "XAUUSD"
    else:
        offs = CRUDE_SETS[rng.integers(len(CRUDE_SETS))]
        qty = float(rng.integers(6, 21) * 50_000)
        prov = 0.0
        diff_s = float(rng.uniform(0.1, 0.6))
        prem_unit = float(rng.uniform(0.0, 0.05)) if rng.random() < 0.3 else 0.0
        pay_rule = str(rng.choice(["after_qp", "after_delivery"]))
        index = "WTI_SPOT"
    lo = min(offs)
    opts = [QPOption(_name(o), o, round(prem_unit * (o - lo), 4)) for o in offs]
    sale_off = int(rng.choice(offs))
    lag = int(rng.integers(3, 11))
    purchase = PhysicalContract("PUR-RND", "buy", qty, index, 0.0, opts, opts[0].name, "us",
                                int(rng.integers(3, 11)), pay_rule, lag, prov)
    sale = PhysicalContract("SAL-RND", "sell", qty, index, round(diff_s, 3),
                            [QPOption(_name(sale_off), sale_off, 0.0)], _name(sale_off), "counterparty",
                            5, pay_rule, lag, 0.0)
    return purchase, sale, float(rng.uniform(0.005, 0.03))
