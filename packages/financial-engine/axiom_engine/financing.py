"""Side-by-side comparison of financing structures (PRD 4.8)."""

from __future__ import annotations

import copy
from typing import Any

from .assumptions import Loan
from .underwriting import run_underwriting


def compare_structures(base: dict[str, Any], structures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Run the base assumptions once per capital structure.

    Each structure is ``{"name": str, "loan": {...} | None, "preferred_equity": {...} | None}``.
    An all-cash structure (no loan) is always useful as a reference and can be
    passed with ``loan: None``.
    """
    out = []
    for s in structures:
        scenario = copy.deepcopy(base)
        scenario["loan"] = copy.deepcopy(s.get("loan"))
        scenario["preferred_equity"] = copy.deepcopy(s.get("preferred_equity"))
        r = run_underwriting(scenario)
        m = r.metrics
        out.append(
            {
                "name": s.get("name", "Structure"),
                "loan_amount": m.loan_amount,
                "preferred_equity": r.sources_and_uses.preferred_equity,
                "equity_invested": m.equity_invested,
                "ltv": m.ltv,
                "ltc": m.ltc,
                "rate": Loan(**scenario["loan"]).all_in_rate if scenario["loan"] else None,
                "debt_service_year1": r.annual[0].debt_service,
                "dscr_year1": m.dscr_year1,
                "min_dscr": m.min_dscr,
                "debt_yield_year1": m.debt_yield_year1,
                "cash_on_cash_year1": m.cash_on_cash_year1,
                "irr_levered": m.irr_levered,
                "equity_multiple_levered": m.equity_multiple_levered,
                "npv_levered": m.npv_levered,
                "balloon_at_exit": r.exit.loan_payoff,
                "covenant_breaches": r.covenant_breaches,
                "warnings": r.warnings,
            }
        )
    return out
