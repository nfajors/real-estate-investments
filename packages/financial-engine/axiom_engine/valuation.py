"""Valuation approaches and reconciliation (PRD 4.6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .tvm import npv, safe_div
from .underwriting import UnderwritingResult


@dataclass
class Comparable:
    name: str
    sale_price: float
    units: int | None = None
    sf: float | None = None
    cap_rate: float | None = None
    adjustment_pct: float = 0.0  # net qualitative adjustment applied to the comp's unit price
    weight: float = 1.0


def direct_capitalization(noi: float, market_cap_rate: float) -> float:
    if market_cap_rate <= 0:
        raise ValueError("Market cap rate must be positive")
    return noi / market_cap_rate


def dcf_value(result: UnderwritingResult, discount_rate: float) -> float:
    """Present value of unlevered operating cash flows plus net reversion (excludes the purchase)."""
    flows = [0.0] + result.unlevered_cash_flows[1:]
    return npv(discount_rate, flows)


def sales_comparison(
    comps: list[Comparable | dict[str, Any]], subject_units: int | None, subject_sf: float | None
) -> dict[str, Any]:
    """Weighted adjusted price-per-unit (or per-SF) applied to the subject."""
    parsed = [c if isinstance(c, Comparable) else Comparable(**c) for c in comps]
    basis = "unit" if subject_units else "sf" if subject_sf else None
    if basis is None:
        raise ValueError("Subject needs units or square footage for a sales comparison")
    rows = []
    total_w = 0.0
    weighted = 0.0
    for c in parsed:
        denom = c.units if basis == "unit" else c.sf
        if not denom or c.weight <= 0:
            continue
        raw = c.sale_price / denom
        adjusted = raw * (1.0 + c.adjustment_pct)
        rows.append({"name": c.name, "raw_price_per": raw, "adjusted_price_per": adjusted, "weight": c.weight})
        total_w += c.weight
        weighted += adjusted * c.weight
    if not rows:
        raise ValueError(f"No comparables with price per {basis} available")
    price_per = weighted / total_w
    subject_size = subject_units if basis == "unit" else subject_sf
    return {"basis": basis, "price_per": price_per, "value": price_per * float(subject_size), "comps": rows}


def cost_approach(
    land_value: float,
    replacement_cost: float,
    physical_depreciation_pct: float = 0.0,
    functional_obsolescence: float = 0.0,
    external_obsolescence: float = 0.0,
    entrepreneurial_incentive_pct: float = 0.0,
) -> dict[str, float]:
    if not 0 <= physical_depreciation_pct <= 1:
        raise ValueError("Depreciation must be between 0% and 100%")
    improvements = replacement_cost * (1.0 + entrepreneurial_incentive_pct)
    depreciation = improvements * physical_depreciation_pct + functional_obsolescence + external_obsolescence
    depreciated = improvements - depreciation
    return {
        "land_value": land_value,
        "replacement_cost": improvements,
        "total_depreciation": depreciation,
        "depreciated_improvements": depreciated,
        "value": land_value + depreciated,
    }


def reconcile(values: dict[str, float | None], weights: dict[str, float]) -> dict[str, Any]:
    """Weighted reconciliation across available approaches; weights are renormalised."""
    usable = {k: v for k, v in values.items() if v is not None and weights.get(k, 0) > 0}
    if not usable:
        raise ValueError("No valuation approaches with positive weight")
    total_w = sum(weights[k] for k in usable)
    reconciled = sum(v * weights[k] for k, v in usable.items()) / total_w
    return {
        "reconciled_value": reconciled,
        "weights": {k: weights[k] / total_w for k in usable},
        "values": values,
        "range": {"low": min(usable.values()), "high": max(usable.values())},
    }


def valuation_summary(
    result: UnderwritingResult,
    market_cap_rate: float,
    discount_rate: float,
    purchase_price: float,
    comps: list[dict[str, Any]] | None = None,
    subject_units: int | None = None,
    subject_sf: float | None = None,
    cost: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
) -> dict[str, Any]:
    values: dict[str, float | None] = {
        "direct_cap": direct_capitalization(result.metrics.noi_year1, market_cap_rate),
        "dcf": dcf_value(result, discount_rate),
        "sales_comparison": None,
        "cost": None,
    }
    details: dict[str, Any] = {}
    if comps:
        sc = sales_comparison(comps, subject_units, subject_sf)
        values["sales_comparison"] = sc["value"]
        details["sales_comparison"] = sc
    if cost:
        ca = cost_approach(**cost)
        values["cost"] = ca["value"]
        details["cost"] = ca
    w = weights or {"direct_cap": 0.4, "dcf": 0.4, "sales_comparison": 0.2, "cost": 0.0}
    rec = reconcile(values, w)
    rec["details"] = details
    rec["purchase_price"] = purchase_price
    rec["premium_discount_to_value"] = safe_div(purchase_price - rec["reconciled_value"], rec["reconciled_value"])
    return rec
