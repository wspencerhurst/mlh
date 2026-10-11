"""Trading calendar and contract-month arithmetic (deterministic).

Contract months are ints yyyymm. Business-day arithmetic is done on an explicit
trading calendar (the set of days the exchange publishes settlements), because
exchange holiday calendars are published in advance and so are not look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def ym_of(ts: pd.Timestamp) -> int:
    return ts.year * 100 + ts.month


def ym_add(k: int, n: int) -> int:
    y, m = divmod(k, 100)
    t = y * 12 + (m - 1) + n
    return (t // 12) * 100 + t % 12 + 1


def month_start(k: int) -> pd.Timestamp:
    return pd.Timestamp(year=k // 100, month=k % 100, day=1)


def ym_label(k: int) -> str:
    return month_start(k).strftime("%b%y")


class TradingCalendar:
    """Sorted trading days, extended with weekdays beyond the last observed date
    so that rules can be evaluated for contracts that expire after the data ends."""

    def __init__(self, dates, extend_days: int = 400):
        d = pd.DatetimeIndex(sorted(set(pd.DatetimeIndex(dates).normalize())))
        ext = pd.bdate_range(d[-1] + pd.Timedelta(days=1), periods=extend_days)
        self.dates = d.append(ext)
        self.n_obs = len(d)
        self._v = self.dates.values

    def pos(self, d) -> int:
        """Index of first trading day >= d."""
        return int(np.searchsorted(self._v, np.datetime64(pd.Timestamp(d)), "left"))

    def is_bday(self, d) -> bool:
        p = self.pos(d)
        return p < len(self.dates) and self.dates[p] == pd.Timestamp(d)

    def bdays_before(self, d, n: int) -> pd.Timestamp:
        """The trading day n business days before calendar date d."""
        return self.dates[self.pos(d) - n]

    def first_bday_of_month(self, k: int) -> pd.Timestamp:
        return self.dates[self.pos(month_start(k))]

    def last_bday_of_month(self, k: int) -> pd.Timestamp:
        return self.dates[self.pos(month_start(ym_add(k, 1))) - 1]

    def shift(self, d, n: int) -> pd.Timestamp:
        """n trading days after trading day d (n may be negative)."""
        return self.dates[self.pos(d) + n]


# ---- Exchange last-trading-day (LTD) rules -------------------------------------

def ltd_nymex_cl(cal: TradingCalendar, k: int) -> pd.Timestamp:
    """NYMEX WTI (CL): trading terminates 3 business days before the 25th calendar
    day of the month prior to the contract month; 4 if the 25th is not a business day."""
    pm = ym_add(k, -1)
    d25 = pd.Timestamp(year=pm // 100, month=pm % 100, day=25)
    return cal.bdays_before(d25, 3 if cal.is_bday(d25) else 4)


def ltd_nymex_ho(cal: TradingCalendar, k: int) -> pd.Timestamp:
    """NYMEX NY Harbor ULSD / heating oil (HO): last business day of the month prior
    to the contract month."""
    return cal.last_bday_of_month(ym_add(k, -1))


def ltd_comex_gc(cal: TradingCalendar, k: int) -> pd.Timestamp:
    """COMEX gold (GC): third-last business day of the contract month."""
    return cal.dates[cal.pos(month_start(ym_add(k, 1))) - 3]


LTD_RULES = {"CL": ltd_nymex_cl, "HO": ltd_nymex_ho, "GC": ltd_comex_gc}
