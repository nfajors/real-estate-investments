"""Axiom financial engine: deterministic, audited CRE calculations.

AI layers never compute numbers – they call into this package.
"""

ENGINE_VERSION = "1.0.0"

from .assumptions import AssumptionError, Assumptions, ExpenseLine, Loan, PreferredEquity, UnitType  # noqa: E402
from .underwriting import UnderwritingResult, run_underwriting  # noqa: E402

__all__ = [
    "ENGINE_VERSION",
    "AssumptionError",
    "Assumptions",
    "ExpenseLine",
    "Loan",
    "PreferredEquity",
    "UnitType",
    "UnderwritingResult",
    "run_underwriting",
]
