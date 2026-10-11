"""Policy search (Cross-Entropy Method) in the simulator.

CEM is a derivative-free RL method: sample policy parameters, roll out full episodes,
keep the elite by the risk-adjusted objective, refit the sampling distribution.
It suits this problem because the action space is tiny and decisions are sparse
(one declaration + a hedge-ratio schedule), so gradient-based deep RL buys little
and costs interpretability. Common random numbers (same episodes for every
candidate) make comparisons low-variance.
"""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .env import run_episode
from .evaluate import objective
from .policies import PARAM_HI, PARAM_LO, ParamPolicy

_EPS = None


def _init(eps):
    global _EPS
    _EPS = eps


def _score(args):
    theta, lam, metric = args
    pol = ParamPolicy(theta)
    rs = [run_episode(ep, pol) for ep in _EPS]
    if metric == "bps":   # P&L in basis points of notional: comparable across price levels
        x = np.array([1e4 * r["pnl"] / r["notional"] for r in rs])
    else:
        x = np.array([r["pnl"] / r["qty"] for r in rs])
    return objective(x, lam)


def cem(eps, lam=0.5, iters=8, pop=24, elite=6, seed=0, init=None, workers=8, log=print, metric="unit"):
    rng = np.random.default_rng(seed)
    mu = np.array(init if init is not None else (PARAM_LO + PARAM_HI) / 2, float)
    sd = (PARAM_HI - PARAM_LO) / 3
    history = []
    with ProcessPoolExecutor(workers, initializer=_init, initargs=(eps,)) as ex:
        for it in range(iters):
            cand = np.clip(mu + sd * rng.standard_normal((pop, len(mu))), PARAM_LO, PARAM_HI)
            cand[0] = mu  # always evaluate the current mean
            scores = np.array(list(ex.map(_score, [(c, lam, metric) for c in cand])))
            idx = np.argsort(scores)[::-1][:elite]
            mu = cand[idx].mean(0)
            sd = np.maximum(cand[idx].std(0), (PARAM_HI - PARAM_LO) * 0.02)
            history.append({"iter": it, "best": float(scores[idx[0]]), "mean_elite": float(scores[idx].mean()),
                            "theta": mu.round(3).tolist()})
            log(f"  CEM iter {it}: best {scores[idx[0]]:.4f}  elite mean {scores[idx].mean():.4f}  mu {np.round(mu, 3)}")
    return mu, history
