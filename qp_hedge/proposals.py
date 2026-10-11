"""Trade proposals: the hand-off between the decision engine, a human approver (front end)
and an execution / settlement rail (Checker stablecoin payments - integration TBD).

Lifecycle:  PENDING_APPROVAL -> APPROVED | REJECTED -> SUBMITTED -> FILLED | FAILED
Every proposal carries the deterministic rationale (forward values, deadline, risk) so an
approver can see *why* before approving. Nothing is executed without an explicit approval.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

STATUSES = ("PENDING_APPROVAL", "APPROVED", "REJECTED", "SUBMITTED", "FILLED", "FAILED")


@dataclass
class Proposal:
    id: str
    kind: str                       # "QP_DECLARATION" | "FUTURES_ORDER" | "SETTLEMENT_PAYMENT"
    deal: str
    summary: str
    details: dict
    rationale: dict
    group: str                      # proposals approved together (e.g. declaration + its hedge)
    status: str = "PENDING_APPROVAL"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))
    history: list = field(default_factory=list)
    execution: dict = field(default_factory=lambda: {"rail": None, "ref": None})

    def transition(self, new: str, actor: str, note: str = ""):
        allowed = {"PENDING_APPROVAL": {"APPROVED", "REJECTED"}, "APPROVED": {"SUBMITTED"},
                   "SUBMITTED": {"FILLED", "FAILED"}}
        if new not in allowed.get(self.status, set()):
            raise ValueError(f"{self.status} -> {new} not allowed")
        self.history.append({"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                             "from": self.status, "to": new, "by": actor, "note": note})
        self.status = new


def _pid(*parts) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:10]


def from_live(rec: dict, deal: str) -> list[Proposal]:
    """Turn a live recommendation (qp_hedge.live.recommend) into an approval group."""
    best = rec["best"]
    unit = rec["unit"]
    opt = next(o for o in rec["options"] if o["name"] == best)
    group = _pid(deal, rec["asof"], best)
    why = {"asof": rec["asof"], f"hedged_value_per_{unit}": {o["name"]: round(o["hedged_value"], 2) for o in rec["options"]},
           f"edge_vs_default_per_{unit}": round(rec["edge_vs_default"], 2), "deadline": rec["deadline"],
           "declare_now": rec["declare_now"], "funding_rate": rec["funding"]}
    when = "now" if rec["declare_now"] else f"by {rec['deadline']} (hedge provisionally now)"
    out = [Proposal(_pid(group, "qp"), "QP_DECLARATION", deal,
                    f"Declare {best} ({opt['qp_month']} average) {when}",
                    {"qp": best, "qp_month": opt["qp_month"], "deadline": rec["deadline"],
                     "quantity": rec["quantity"], "unit": unit}, why, group)]
    for leg in rec["tickets"][best]:
        out.append(Proposal(_pid(group, leg["contract"]), "FUTURES_ORDER", deal,
                            f"{leg['side']} {abs(leg['lots'])} {leg['contract']}",
                            {"instrument": leg["contract"], "exchange": rec["exchange"], "side": leg["side"],
                             "lots": abs(leg["lots"]), "lot_size": rec["lot"], "unit": unit, "order_type": "TAS",
                             "ref_price": leg["settle"],
                             "notional_usd": round(abs(leg["lots"]) * rec["lot"] * leg["settle"], 2)}, why, group))
    return out


class CheckerRail:
    """Placeholder for the Checker stablecoin payments API (settlement of approved
    physical payments / margin). Intentionally not implemented yet."""

    def submit(self, p: Proposal) -> dict:
        if p.status != "APPROVED":
            raise PermissionError("only APPROVED proposals can be submitted")
        raise NotImplementedError("Checker integration pending")


def save(proposals: list[Proposal], path: str):
    with open(path, "w") as f:
        json.dump([asdict(p) for p in proposals], f, indent=1, default=str)
