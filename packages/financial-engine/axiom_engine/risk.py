"""Deterministic risk scoring used for alerts and deal comparison.

The score is 0 (low risk) to 100 (high risk) and is the sum of transparent,
documented penalties – it is a screening heuristic, not a credit rating.
"""

from __future__ import annotations

from typing import Any

from .underwriting import UnderwritingResult

# Owner-borne operating expense ratios (share of EGI). Industrial and retail are
# typically net-leased, so most expenses are recovered from tenants.
EXPENSE_RATIO_BENCHMARKS = {
    "multifamily": 0.45,
    "industrial": 0.12,
    "office": 0.45,
    "retail": 0.20,
    "mixed_use": 0.42,
    "hospitality": 0.70,
    "self_storage": 0.40,
    "student_housing": 0.50,
    "land": 0.10,
}


def risk_assessment(result: UnderwritingResult, property_type: str = "multifamily") -> dict[str, Any]:
    m = result.metrics
    a = result.assumptions
    factors: list[dict[str, Any]] = []

    def add(key: str, points: float, message: str) -> None:
        factors.append({"factor": key, "points": round(points, 1), "message": message})

    if m.min_dscr is not None:
        if m.min_dscr < 1.0:
            add("dscr", 30, f"Minimum DSCR {m.min_dscr:.2f}x – NOI does not cover debt service")
        elif m.min_dscr < 1.25:
            add("dscr", 15, f"Minimum DSCR {m.min_dscr:.2f}x is below the 1.25x lender norm")
    if m.ltv is not None and m.ltv > 0.70:
        add("leverage", min(20.0, (m.ltv - 0.70) * 200), f"LTV of {m.ltv:.0%} exceeds 70%")
    if a["exit_cap_rate"] < m.going_in_cap_rate:
        add("cap_compression", 10, "Exit cap is below the going-in cap rate (assumes cap compression)")
    max_growth = max([a["rent_growth"]] + list(a.get("rent_growth_by_year") or []))
    if max_growth > 0.04:
        add("rent_growth", min(15.0, (max_growth - 0.04) * 500), f"Rent growth of {max_growth:.1%} exceeds 4%")
    bench = EXPENSE_RATIO_BENCHMARKS.get(property_type)
    if bench and m.expense_ratio_year1 is not None and m.expense_ratio_year1 < bench - 0.10:
        add("expense_ratio", 10, f"Expense ratio {m.expense_ratio_year1:.0%} is well below the {bench:.0%} benchmark")
    if m.breakeven_occupancy is not None and m.breakeven_occupancy > 0.85:
        add("breakeven", 10, f"Breakeven occupancy of {m.breakeven_occupancy:.0%} leaves a thin cushion")
    if result.covenant_breaches:
        add("covenants", 15, f"{len(result.covenant_breaches)} projected covenant breach(es)")
    if any(w["field"] == "loan.term_years" for w in result.warnings):
        add("refinance", 8, "Loan matures before exit")
    if m.irr_levered is None or m.irr_levered < 0:
        add("returns", 20, "Levered returns are negative or undefined")

    score = min(100.0, sum(f["points"] for f in factors))
    level = "low" if score < 20 else "moderate" if score < 45 else "high"
    return {"score": round(score, 1), "level": level, "factors": factors}
