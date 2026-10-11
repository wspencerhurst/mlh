"""Parsed physical contract schema (the output an upstream contract parser / LLM
extraction step would produce, after human verification).

Pricing is the arithmetic average of a daily index over a Quotation Period (QP)
plus a differential. QP options are expressed relative to the delivery month M
("M-1", "M", "M+1"...). One party holds the right to declare the QP before a
deadline; if it does not, the default QP applies.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from .calendar import ym_add


@dataclass
class QPOption:
    name: str               # e.g. "M+1"
    month_offset: int       # QP calendar month = delivery month + offset
    premium: float = 0.0    # $/bbl added to price if this QP is elected


@dataclass
class PhysicalContract:
    contract_id: str
    side: str                       # "buy" (we pay the price) or "sell" (we receive it)
    quantity: float                 # bbl
    index: str                      # pricing index name, e.g. "WTI_CUSHING_SPOT"
    differential: float             # $/bbl added to the QP average
    qp_options: list[QPOption]
    default_qp: str
    declaring_party: str = "us"     # "us" -> our decision; "counterparty" -> treated as default
    deadline_bdays_before_earliest_qp: int = 5
    payment_rule: str = "after_qp"  # "after_qp" (final invoice after QP) | "after_delivery"
    payment_lag_bdays: int = 5
    provisional_pct: float = 0.0    # share paid at arrival (end of delivery month) at the then index
    delivery_month: int | None = None   # yyyymm; templates leave it None
    meta: dict = field(default_factory=dict)

    @property
    def sign(self) -> int:
        """+1 if we receive the floating price, -1 if we pay it."""
        return 1 if self.side == "sell" else -1

    @property
    def is_decision(self) -> bool:
        return self.declaring_party == "us" and len(self.qp_options) > 1

    def option(self, name: str) -> QPOption:
        return next(o for o in self.qp_options if o.name == name)

    def qp_month(self, name: str) -> int:
        return ym_add(self.delivery_month, self.option(name).month_offset)

    def for_delivery(self, ym: int) -> "PhysicalContract":
        d = dict(self.__dict__)
        d["delivery_month"] = ym
        d["contract_id"] = f"{self.contract_id}-{ym}"
        return PhysicalContract(**d)

    @staticmethod
    def from_dict(d: dict) -> "PhysicalContract":
        d = dict(d)
        d["qp_options"] = [QPOption(**o) for o in d["qp_options"]]
        return PhysicalContract(**d)

    @staticmethod
    def load(path: str) -> "PhysicalContract":
        with open(path) as f:
            return PhysicalContract.from_dict(json.load(f))


@dataclass
class Book:
    """Trader's book for one cargo: the physical contracts + existing futures (bbl by
    contract month, + long / - short)."""
    contracts: list[PhysicalContract]
    futures: dict[int, float] = field(default_factory=dict)

    @property
    def decision(self) -> PhysicalContract | None:
        ds = [c for c in self.contracts if c.is_decision]
        assert len(ds) <= 1, "prototype supports one QP decision per book"
        return ds[0] if ds else None
