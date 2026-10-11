"""Supervised 'which QP will be cheapest?' models, evaluated walk-forward.

Target (per option o, relative to the sale-matched QP): realized value minus the
forward-implied value at the declaration deadline, i.e. the *forecast error of the
forward curve*. If forwards are unbiased this is unpredictable noise and the best
model predicts ~0, recovering the deterministic forward-optimal decision.

Leakage control: a training example is usable only after its last QP fixing date
(its label is not known before then), not merely after its delivery month began.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .env import Action, deadline_t, option_values, realized_values


def episode_table(eps) -> pd.DataFrame:
    rows = []
    for ep in eps:
        m = ep.market
        t = deadline_t(ep)
        j = ep.j0 - 1 + t - 1                       # information through the day before
        fwd = option_values(ep, t - 1)
        real = realized_values(ep)
        offs = [ep.decision.option(o).month_offset for o in ep.options]
        sale_offs = [l.contract.option(l.option).month_offset for l in ep.fixed_legs if l.sign > 0]
        ref = offs.index(sale_offs[0]) if sale_offs and sale_offs[0] in offs else len(fwd) - 1
        mo = ep.delivery % 100
        p = m.front_px[max(0, j - 60): j + 1]
        rows.append({
            "delivery": ep.delivery, "deadline": ep.deadline, "label_known": ep.dates[-1], "ref": ref,
            **{f"fwd_{i}": fwd[i] - fwd[ref] for i in range(len(fwd))},
            **{f"real_{i}": real[i] - real[ref] for i in range(len(real))},
            "slope": m.slope[j], "slope_mom": m.slope_mom[j],
            "vol": m.vol_front[j] / max(abs(m.front_px[j]), 1e-6),
            "ret60": np.log(p[-1] / p[0]) if p[0] > 0 and p[-1] > 0 else 0.0,
            "mo_sin": np.sin(2 * np.pi * mo / 12), "mo_cos": np.cos(2 * np.pi * mo / 12),
        })
    return pd.DataFrame(rows)


BASE_FEATS = ["slope", "slope_mom", "vol", "ret60", "mo_sin", "mo_cos"]


def walk_forward_choices(tab: pd.DataFrame, n_opt: int, window_months: int | None,
                         min_train: int = 6, kind: str = "ridge") -> pd.Series:
    """Choose a QP index per episode using only examples whose labels were known
    at that episode's deadline. window_months=None -> expanding window."""
    choices = {}
    for i, r in tab.iterrows():
        known = tab[tab["label_known"] < r["deadline"]]
        if window_months is not None:
            known = known[known["label_known"] >= r["deadline"] - pd.DateOffset(months=window_months)]
        fwd = np.array([r[f"fwd_{o}"] for o in range(n_opt)])
        if len(known) < min_train:
            choices[r["delivery"]] = int(np.argmax(fwd))
            continue
        if kind == "winner":   # "the QP that won most often recently"
            wins = np.argmax(known[[f"real_{o}" for o in range(n_opt)]].values, axis=1)
            choices[r["delivery"]] = int(np.bincount(wins, minlength=n_opt).argmax())
            continue
        pred = np.zeros(n_opt)
        feats = [f"fwd_{o}" for o in range(n_opt) if o != r["ref"]] + BASE_FEATS
        for o in range(n_opt):
            if o == r["ref"]:
                continue
            y = known[f"real_{o}"] - known[f"fwd_{o}"]
            mdl = make_pipeline(StandardScaler(), Ridge(alpha=10.0)).fit(known[feats].values, y.values)
            pred[o] = mdl.predict(r[feats].values.reshape(1, -1).astype(float))[0]
        choices[r["delivery"]] = int(np.argmax(fwd + pred))
    return pd.Series(choices)


class PlannedQP:
    """Declares a pre-computed QP (per delivery month) at the deadline, hedge ratio h."""

    def __init__(self, plan: pd.Series, options: list[str], h: float, name: str):
        self.plan, self.options, self.h, self.name = plan, options, h, name

    def reset(self, ep):
        self.qp = self.options[int(self.plan[ep.delivery])]

    def act(self, obs):
        elect = self.qp if obs.can_elect and obs.bdays_to_deadline == 0 else None
        return Action(elect=elect, provisional=self.qp, hedge_ratio=self.h)
