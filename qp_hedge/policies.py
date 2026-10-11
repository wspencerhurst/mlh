"""Decision policies. All receive only an `Obs` (information through t-1).

Benchmarks
  FixedQP(qp, h)      declare a fixed QP on day one; hedge ratio h (0 = unhedged).
Deterministic optimiser
  ParamPolicy with theta = FORWARD_OPTIMAL_*: pick the QP with the best forward-implied,
  financed, cost-adjusted value; hedge it fully; either declare at once or keep the
  option open until the deadline (switching the provisional QP with hysteresis).
Learned
  ParamPolicy with theta tuned by policy search (see train.py).
"""
from __future__ import annotations

import math

import numpy as np

from .env import Action, Obs


class FixedQP:
    def __init__(self, qp: str, hedge_ratio: float = 1.0, name: str | None = None):
        self.qp, self.h = qp, hedge_ratio
        self.name = name or f"Fixed {qp} h={hedge_ratio:g}"

    def reset(self, ep):
        pass

    def act(self, obs: Obs) -> Action:
        return Action(elect=self.qp if obs.can_elect else None, provisional=self.qp, hedge_ratio=self.h)


PARAM_NAMES = ["hysteresis", "h_pre", "h_post", "tilt", "wait_k", "basis_k", "slope_k"]
PARAM_LO = np.array([0.0, 0.0, 0.0, -3.0, -2.0, -0.3, -1.0])
PARAM_HI = np.array([0.5, 1.2, 1.2, 3.0, 4.0, 0.3, 1.0])
# wait_k is log10: declare once the value of waiting < 10**wait_k x the cost of switching hedges.
# 4 -> threshold far above any waiting value (declare at once); -2 -> almost never early.
FORWARD_OPTIMAL_NOW = np.array([0.0, 1.0, 1.0, 0.0, 4.0, 0.0, 0.0])
FORWARD_OPTIMAL_WAIT = np.array([0.05, 1.0, 1.0, 0.0, -2.0, 0.0, 0.0])


def _phi(z: float) -> float:
    return math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)


def _Phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def waiting_value(lead: float, sd: float) -> float:
    """Value of keeping the choice open: expected gain from the runner-up overtaking the leader by the
    deadline, when their gap moves like a Brownian motion with total s.d. `sd` (Bachelier option on the gap)."""
    if sd <= 1e-12:
        return 0.0
    z = lead / sd
    return sd * _phi(z) - lead * _Phi(-z)


class ParamPolicy:
    """Interpretable policy family (7 learned numbers).

    score_o   = forward value_o + tilt * slope_mom($) * (offset_o - sale_offset)
    provisional QP = argmax score, switched only if it beats the current one by > hysteresis
    declare   when the value of waiting (option on the gap between the best two months, Bachelier)
              is below 10**wait_k * switching cost * exp(slope_k * curve slope in %) - an optimal-stopping
              rule: keep the option only while it is worth more than what using it would cost;
              always on the deadline
    hedge     ratio = h_pre (before declaring) or h_post (after) + basis_k * gap z-score: hedge more or
              less when the index-vs-futures gap is unusually wide
    """

    def __init__(self, theta, name: str = "Param"):
        self.theta = np.clip(np.asarray(theta, float), PARAM_LO, PARAM_HI)
        self.name = name

    def reset(self, ep):
        self.prov = None

    def _ratio(self, base: float, obs: Obs) -> float:
        return float(np.clip(base + self.theta[5] * np.clip(obs.basis_z, -3, 3), 0.0, 1.5))

    def act(self, obs: Obs) -> Action:
        hyst, h_pre, h_post, tilt, wait_k, basis_k, slope_k = self.theta
        if obs.elected is not None:
            return Action(provisional=obs.elected, hedge_ratio=self._ratio(h_post, obs))
        score = obs.opt_value + tilt * obs.slope_mom * obs.price * (obs.offsets - obs.sale_offset) / 10.0
        best = int(np.argmax(score))
        if self.prov is None or score[best] > score[self.prov] + hyst:
            self.prov = best
        elect = None
        if obs.can_elect:
            if obs.bdays_to_deadline == 0 or len(score) < 2:
                elect = obs.options[self.prov]
            else:
                others = np.delete(np.arange(len(score)), self.prov)
                second = others[int(np.argmax(score[others]))]
                lead = float(score[self.prov] - score[second])
                gap_months = max(1, abs(int(obs.offsets[self.prov] - obs.offsets[second])))
                sd = obs.vol_spread * gap_months / 2.0 * math.sqrt(obs.bdays_to_deadline)
                threshold = 10.0 ** wait_k * obs.switch_cost * math.exp(slope_k * float(np.clip(obs.slope * 100, -3, 3)))
                if waiting_value(lead, sd) <= threshold:
                    elect = obs.options[self.prov]
        h = self._ratio(h_post if elect else h_pre, obs)
        return Action(elect=elect, provisional=obs.options[self.prov], hedge_ratio=h)