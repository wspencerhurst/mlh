"""Synthetic market generator (semi-parametric), calibrated only on a training window.

Curve model: for contract k on day t with time-to-expiry tau,
    ln F(t, k) = a_t + b_t * exp(-kappa * tau)
  a_t : long-end level   - random walk (zero drift)
  b_t : short-end premium (contango < 0 < backwardation) - mean-reverting AR(1)
Physical index: ln I_t = ln F_front(t) + x_t, x_t mean-reverting AR(1) (basis).
Shocks (e_a, e_b, e_x) are *jointly block-bootstrapped* from the historical
residuals, which keeps fat tails, cross-correlation and some volatility clustering.
Start states (a, b, x) are drawn from historical states, so curve shapes and price
levels are realistic. Contract terms can be synthesised freely (they are just payoff specs).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calendar import TradingCalendar, ym_add, ym_of
from .market import MarketData


class CurveModel:
    def __init__(self, market: MarketData, start: str, end: str,
                 kappas=np.arange(0.25, 6.01, 0.25)):
        m = market
        js = np.where((m.dates >= start) & (m.dates <= end))[0]
        taus, ys, ok = [], [], []
        for j in js:
            d = m.dates[j]
            ks = [ym_add(m.front[j], i) for i in range(6)]
            pts = [((m.ltd(k) - d).days / 365.25, m.price(j, k)) for k in ks]
            pts = [(t, np.log(p)) for t, p in pts if np.isfinite(p) and p > 0 and t >= 0]
            taus.append(np.array([p[0] for p in pts]))
            ys.append(np.array([p[1] for p in pts]))
            ok.append(len(pts) >= 3)
        best = None
        for kap in kappas:
            sse, ab = 0.0, []
            for t, y, g in zip(taus, ys, ok):
                if not g:
                    ab.append((np.nan, np.nan))
                    continue
                X = np.column_stack([np.ones_like(t), np.exp(-kap * t)])
                coef, res, *_ = np.linalg.lstsq(X, y, rcond=None)
                sse += float(np.sum((X @ coef - y) ** 2))
                ab.append(tuple(coef))
            if best is None or sse < best[0]:
                best = (sse, kap, np.array(ab))
        _, self.kappa, ab = best
        df = pd.DataFrame(ab, columns=["a", "b"], index=m.dates[js])
        I, Ff = m.I[js], m.front_px[js]
        df["x"] = np.where((I > 0) & (Ff > 0), np.log(np.where(I > 0, I, 1) / np.where(Ff > 0, Ff, 1)), np.nan)
        df = df.ffill().dropna()
        self.states = df
        d = df.diff().iloc[1:]
        lag = df.shift(1).iloc[1:]
        # AR(1) in differences: d_b = alpha + phi * b_{t-1} + e
        self.ar = {}
        for c in ["b", "x"]:
            X = np.column_stack([np.ones(len(lag)), lag[c].values])
            coef, *_ = np.linalg.lstsq(X, d[c].values, rcond=None)
            self.ar[c] = coef
        e = pd.DataFrame({
            "a": d["a"] - d["a"].mean(),
            "b": d["b"] - (self.ar["b"][0] + self.ar["b"][1] * lag["b"]),
            "x": d["x"] - (self.ar["x"][0] + self.ar["x"][1] * lag["x"]),
        })
        self.resid = e.values
        self.root, self.lot, self.rate = m.root, m.lot, m.rate
        self.window = (start, end)

    def describe(self) -> dict:
        hl = lambda phi: np.log(2) / -phi / 252 if phi < 0 else np.inf
        return {"kappa": self.kappa, "level_vol_ann": float(self.resid[:, 0].std() * np.sqrt(252)),
                "slope_halflife_yrs": float(hl(self.ar["b"][1])),
                "basis_halflife_days": float(hl(self.ar["x"][1]) * 252),
                "n_resid_days": len(self.resid)}

    def simulate(self, rng: np.random.Generator, start_date="2101-01-03", n_days: int = 420,
                 block: int = 20, n_listed: int = 4, name: str = "synthetic",
                 regime_shift_sd: float = 0.0) -> MarketData:
        """regime_shift_sd: domain randomisation - shift the long-run curve slope (b) of
        each path by N(0, sd), so policies are trained across contango/backwardation regimes."""
        dates = pd.bdate_range(start_date, periods=n_days)
        cal = TradingCalendar(dates)
        s0 = self.states.iloc[rng.integers(len(self.states))]
        shift = rng.normal(0.0, regime_shift_sd) if regime_shift_sd else 0.0
        a, b, x = s0["a"], s0["b"] + shift, s0["x"]
        n = len(self.resid)
        shocks = []
        while len(shocks) < n_days:
            i = rng.integers(0, n - block)
            shocks.extend(self.resid[i:i + block])
        shocks = np.array(shocks[:n_days])
        tmp = MarketData.__new__(MarketData)        # borrow LTD logic on the synthetic calendar
        tmp.cal, tmp._ltd = cal, {}
        from .calendar import LTD_RULES
        tmp._ltd_fn = LTD_RULES[self.root]
        fut, idx = {}, {}
        for t, d in enumerate(dates):
            if t:
                a = a + shocks[t, 0]
                b = b + self.ar["b"][0] + self.ar["b"][1] * (b - shift) + shocks[t, 1]
                x = x + self.ar["x"][0] + self.ar["x"][1] * x + shocks[t, 2]
            k = ym_of(d)
            while tmp.ltd(k) < d:
                k = ym_add(k, 1)
            for i in range(n_listed):
                kk = ym_add(k, i)
                tau = (tmp.ltd(kk) - d).days / 365.25
                fut.setdefault(kk, {})[d] = float(np.exp(a + b * np.exp(-self.kappa * tau)))
            front_tau = (tmp.ltd(k) - d).days / 365.25
            idx[d] = float(np.exp(a + b * np.exp(-self.kappa * front_tau) + x))
        panel = pd.DataFrame(fut).sort_index()
        return MarketData(name, self.root, panel, pd.Series(idx), cal=cal, lot_bbl=self.lot, rate=self.rate)


def stylized_facts(m: MarketData, start=None, end=None) -> dict:
    sel = np.ones(len(m.dates), bool)
    if start:
        sel &= m.dates >= start
    if end:
        sel &= m.dates <= end
    js = np.where(sel)[0]
    js = js[js > 0]
    r1, r4 = [], []
    for j in js:
        f = m.front[j - 1]
        for out, k in ((r1, f), (r4, ym_add(f, 3))):
            p0, p1 = m.price(j - 1, k), m.price(j, k)
            if np.isfinite(p0) and np.isfinite(p1) and p0 > 0 and p1 > 0:
                out.append(np.log(p1 / p0))
    r1, r4 = np.array(r1), np.array(r4)
    sl = m.slope[js]
    sl = sl[np.isfinite(sl)]
    lb = np.log(m.I[js] / m.front_px[js])
    lb = lb[np.isfinite(lb)]
    k1 = pd.Series(r1).kurt()
    return {"vol_front_ann": r1.std() * np.sqrt(252), "vol_c4_ann": r4.std() * np.sqrt(252),
            "samuelson_ratio": r1.std() / r4.std(), "excess_kurtosis": k1,
            "mean_slope_pct": 100 * sl.mean(), "sd_slope_pct": 100 * sl.std(),
            "pct_contango": 100 * (sl > 0).mean(),
            "slope_ar1": pd.Series(sl).autocorr(), "basis_sd_pct": 100 * lb.std()}


class CarryModel:
    """Synthetic gold: spot log-returns and short-rate changes are jointly
    block-bootstrapped from the training window; the forward curve is the
    cash-and-carry curve with a lease rate drawn per path (domain randomisation:
    lease spikes / backwardation episodes like 2025's London squeeze)."""

    def __init__(self, market: MarketData, start: str, end: str, lease: float = 0.005):
        m = market
        js = np.where((m.dates >= start) & (m.dates <= end))[0]
        S, r = m.I[js], m.r[js]
        x = getattr(m, "gc_basis", np.zeros(len(m.dates)))[js]   # real futures-vs-spot basis
        ok = np.isfinite(S) & np.isfinite(r) & np.isfinite(x) & (S > 0)
        S, r, x = S[ok], r[ok], x[ok]
        dx = np.diff(x)
        X = np.column_stack([np.ones(len(x) - 1), x[:-1]])
        self.ar_x = np.linalg.lstsq(X, dx, rcond=None)[0] if np.any(x) else np.zeros(2)
        ex = dx - X @ self.ar_x
        self.resid = np.column_stack([np.diff(np.log(S)), np.diff(r), ex])
        self.states = pd.DataFrame({"S": S, "r": r, "x": x})
        self.lease, self.root, self.lot = lease, m.root, m.lot
        self.window = (start, end)

    def describe(self) -> dict:
        return {"spot_vol_ann": float(self.resid[:, 0].std() * np.sqrt(252)),
                "rate_vol_bp_ann": float(self.resid[:, 1].std() * np.sqrt(252) * 1e4),
                "basis_sd_pct": float(self.states["x"].std() * 100),
                "lease_base": self.lease, "n_resid_days": len(self.resid)}

    def simulate(self, rng: np.random.Generator, start_date="2101-01-03", n_days: int = 420,
                 block: int = 20, name: str = "synthetic gold", lease_sd: float = 0.0,
                 S0: float | None = None, r0: float | None = None) -> MarketData:
        from .market import carry_panel
        dates = pd.bdate_range(start_date, periods=n_days)
        cal = TradingCalendar(dates)
        s0 = self.states.iloc[rng.integers(len(self.states))]
        lnS, r = np.log(S0 if S0 else s0["S"]), (r0 if r0 is not None else s0["r"])
        n = len(self.resid)
        shocks = []
        while len(shocks) < n_days:
            i = rng.integers(0, n - block)
            shocks.extend(self.resid[i:i + block])
        shocks = np.array(shocks[:n_days])
        shocks[0] = 0
        lnS = lnS + np.cumsum(shocks[:, 0] - shocks[:, 0].mean())   # driftless spot
        rr = np.maximum(r + np.cumsum(shocks[:, 1]), -0.005)
        x = np.empty(n_days)
        x[0] = s0["x"]
        for t in range(1, n_days):   # futures-vs-spot basis: mean-reverting, real shocks
            x[t] = x[t - 1] + self.ar_x[0] + self.ar_x[1] * x[t - 1] + shocks[t, 2]
        lease = self.lease + (abs(rng.normal(0, lease_sd)) if lease_sd else 0.0)
        S = np.exp(lnS)
        panel = carry_panel(dates, S, rr, lease, cal, self.root).mul(np.exp(x), axis=0)
        sm = MarketData(name, self.root, panel, pd.Series(S, index=dates), cal=cal,
                        lot_bbl=self.lot, rate_series=pd.Series(rr, index=dates), unit="oz")
        sm.gc_basis = x
        return sm