"""Data validation helpers."""
from __future__ import annotations

import numpy as np

from . import calendar as C
from .calendar import TradingCalendar
from .market import load_eia_series, panel_from_positions


def ltd_alignment_test(root: str, keys: list[str], since: str = "2000-01-01",
                       shifts=(-2, -1, 0, 1, 2)) -> dict[int, float]:
    """Mean absolute same-contract daily change under LTD rules shifted by n days.
    A wrong position->month mapping splices two contracts together and adds
    spread-sized jumps, so the correct rule should minimise this statistic."""
    futs = [load_eia_series(k) for k in keys]
    cal = TradingCalendar(futs[0].index)
    base = C.LTD_RULES[root]
    out = {}
    try:
        for sh in shifts:
            C.LTD_RULES[root] = lambda cal, k, sh=sh: cal.shift(base(cal, k), sh)
            p = panel_from_positions(futs, root, cal)
            p = p[p.index >= since]
            out[sh] = float(np.nanmean(p.diff().abs().values))
    finally:
        C.LTD_RULES[root] = base
    return out
