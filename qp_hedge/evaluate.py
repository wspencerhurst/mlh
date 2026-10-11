"""Historical replay, metrics and benchmark comparison."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .calendar import ym_add
from .contracts import Book, PhysicalContract
from .env import EnvConfig, build_episode, run_episode


def make_episodes(market, purchase: PhysicalContract, sale: PhysicalContract, cfg: EnvConfig,
                  start_ym: int | None = None, end_ym: int | None = None):
    eps = []
    k = start_ym or (market.dates[0].year * 100 + 1)
    end = end_ym or (market.dates[-1].year * 100 + 12)
    while k <= end:
        ep = build_episode(market, Book([purchase.for_delivery(k), sale.for_delivery(k)]), cfg)
        if ep is not None:
            eps.append(ep)
        k = ym_add(k, 1)
    return eps


def run_policies(eps, policies) -> pd.DataFrame:
    rows = []
    for p in policies:
        for ep in eps:
            r = run_episode(ep, p)
            q = r["qty"]
            rows.append({"policy": p.name, "delivery": r["delivery"], "elected": r["elected"],
                         "elect_date": r["elect_date"], "pnl": r["pnl"],
                         "pnl_unit": r["pnl"] / q, "pnl_bps": 1e4 * r["pnl"] / r["notional"],
                         "physical_unit": r["physical"] / q,
                         "futures_unit": r["futures"] / q, "costs_unit": r["costs"] / q,
                         "financing_unit": r["financing"] / q,
                         "reward_sd_unit": float(np.std(r["rewards"]) / q)})
    return pd.DataFrame(rows)


def cvar(x: np.ndarray, alpha: float = 0.05) -> float:
    """Expected shortfall: mean loss in the worst alpha tail (positive = loss)."""
    x = np.sort(np.asarray(x))
    n = max(1, int(np.ceil(alpha * len(x))))
    return float(-x[:n].mean())


def objective(x: np.ndarray, lam: float = 0.5, alpha: float = 0.05) -> float:
    """Risk-adjusted score used for training AND evaluation: mean - lam * CVaR_alpha."""
    return float(np.mean(x) - lam * cvar(x, alpha))


def block_bootstrap_ci(d: np.ndarray, block: int = 6, n: int = 4000, seed: int = 0):
    """95% CI of the mean of a serially-correlated series (overlapping episodes)."""
    rng = np.random.default_rng(seed)
    d = np.asarray(d)
    m = len(d)
    nb = int(np.ceil(m / block))
    means = np.empty(n)
    for i in range(n):
        starts = rng.integers(0, m - block + 1, nb)
        means[i] = np.concatenate([d[s:s + block] for s in starts])[:m].mean()
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def summarize(df: pd.DataFrame, benchmark: str, lam: float = 0.5, metric: str = "pnl_unit") -> pd.DataFrame:
    piv = df.pivot(index="delivery", columns="policy", values=metric)
    out = []
    for p in piv.columns:
        x = piv[p].values
        d = x - piv[benchmark].values
        lo, hi = block_bootstrap_ci(d)
        out.append({"policy": p, "n": len(x), "mean": x.mean(), "std": x.std(),
                    "cvar5": cvar(x), "worst": x.min(), "score": objective(x, lam),
                    "vs_bench_mean": d.mean(), "vs_bench_ci_lo": lo, "vs_bench_ci_hi": hi,
                    "win_rate": float((d > 1e-9).mean()),
                    "sharpe_like": float(x.mean() / x.std()) if x.std() > 1e-12 else np.nan})
    return pd.DataFrame(out).set_index("policy").sort_values("score", ascending=False)
