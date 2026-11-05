"""Underwriting assumption model, parsing and validation.

Assumptions are plain dataclasses so the engine has no framework dependency.
``Assumptions.from_dict`` accepts the JSON stored in ``scenarios.assumptions_json``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from typing import Any

REVENUE_MODES = ("unit_mix", "per_sf", "lump_sum")
OPEX_MODES = ("line_items", "ratio")
LOAN_TYPES = ("permanent", "bridge", "construction", "interest_only")
RATE_TYPES = ("fixed", "floating")

# Thresholds for "extreme assumption" flags (PRD section 8, validation rules).
MAX_REASONABLE_RENT_GROWTH = 0.08
MAX_REASONABLE_VACANCY = 0.25
MIN_REASONABLE_EXIT_CAP = 0.035
MAX_REASONABLE_LTV = 0.80
MIN_REASONABLE_DSCR = 1.20


class AssumptionError(ValueError):
    """Raised when assumptions are invalid (impossible, not merely aggressive)."""

    def __init__(self, errors: list[dict[str, str]]):
        self.errors = errors
        super().__init__("; ".join(f"{e['field']}: {e['message']}" for e in errors))


@dataclass
class UnitType:
    name: str
    units: int
    in_place_rent_monthly: float
    market_rent_monthly: float | None = None
    sf_per_unit: float | None = None


@dataclass
class ExpenseLine:
    name: str
    amount_annual: float
    growth: float | None = None  # overrides Assumptions.opex_growth when set


@dataclass
class Loan:
    name: str = "Senior Loan"
    loan_type: str = "permanent"
    amount: float | None = None
    ltv: float | None = None  # used when amount is not given
    rate_type: str = "fixed"
    interest_rate: float = 0.0  # all-in rate for fixed loans
    index_rate: float = 0.0  # floating loans: rate = index + spread
    spread: float = 0.0
    amortization_years: int = 30  # 0 = interest only for the full term
    term_years: int = 10
    io_years: float = 0.0
    origination_fee_pct: float = 0.0
    exit_fee_pct: float = 0.0
    min_dscr_covenant: float | None = None
    max_ltv_covenant: float | None = None

    @property
    def all_in_rate(self) -> float:
        if self.rate_type == "floating":
            return self.index_rate + self.spread
        return self.interest_rate


@dataclass
class PreferredEquity:
    amount: float = 0.0
    pref_rate: float = 0.0  # current-pay annual return
    accrual_rate: float = 0.0  # additional accrued return paid at exit


@dataclass
class Assumptions:
    purchase_price: float
    hold_period_years: int = 10
    closing_costs_pct: float = 0.02
    upfront_capex: float = 0.0

    # Physical attributes (used for per-unit / per-SF metrics)
    units: int | None = None
    rentable_sf: float | None = None

    # Revenue
    revenue_mode: str = "unit_mix"
    unit_mix: list[UnitType] = field(default_factory=list)
    rent_psf_annual: float = 0.0
    gross_potential_rent: float = 0.0  # lump_sum mode
    other_income: float = 0.0
    rent_growth: float = 0.03
    rent_growth_by_year: list[float] | None = None
    other_income_growth: float = 0.02
    vacancy_rate: float = 0.05
    credit_loss_rate: float = 0.0

    # Expenses
    opex_mode: str = "line_items"
    expense_lines: list[ExpenseLine] = field(default_factory=list)
    opex_ratio: float = 0.40  # ratio mode: opex as % of EGI
    management_fee_pct: float = 0.0  # % of EGI, on top of line items
    opex_growth: float = 0.025
    capex_reserve_annual: float = 0.0
    capex_growth: float = 0.025

    # Exit and discounting
    exit_cap_rate: float = 0.055
    selling_costs_pct: float = 0.02
    discount_rate: float = 0.08

    # Capital structure
    loan: Loan | None = None
    preferred_equity: PreferredEquity | None = None

    # ------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Assumptions:
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise AssumptionError([{"field": k, "message": "Unknown assumption"} for k in unknown])
        kwargs = dict(data)
        if "purchase_price" not in kwargs:
            raise AssumptionError([{"field": "purchase_price", "message": "Required"}])
        kwargs["unit_mix"] = [_build(UnitType, u, "unit_mix") for u in kwargs.get("unit_mix") or []]
        kwargs["expense_lines"] = [
            _build(ExpenseLine, e, "expense_lines") for e in kwargs.get("expense_lines") or []
        ]
        if kwargs.get("loan") is not None:
            kwargs["loan"] = _build(Loan, kwargs["loan"], "loan")
        if kwargs.get("preferred_equity") is not None:
            kwargs["preferred_equity"] = _build(PreferredEquity, kwargs["preferred_equity"], "preferred_equity")
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    # ------------------------------------------------------------------
    def validate(self) -> list[dict[str, str]]:
        """Raise ``AssumptionError`` for impossible inputs; return warning flags otherwise."""
        errors: list[dict[str, str]] = []

        def err(f: str, m: str) -> None:
            errors.append({"field": f, "message": m})

        if self.purchase_price <= 0:
            err("purchase_price", "Must be greater than zero")
        if not isinstance(self.hold_period_years, int) or not 1 <= self.hold_period_years <= 30:
            err("hold_period_years", "Must be a whole number of years between 1 and 30")
        if self.revenue_mode not in REVENUE_MODES:
            err("revenue_mode", f"Must be one of {', '.join(REVENUE_MODES)}")
        if self.opex_mode not in OPEX_MODES:
            err("opex_mode", f"Must be one of {', '.join(OPEX_MODES)}")
        for name in ("vacancy_rate", "credit_loss_rate", "closing_costs_pct", "selling_costs_pct",
                     "management_fee_pct"):
            if not 0 <= getattr(self, name) < 1:
                err(name, "Must be between 0% and 100%")
        if self.opex_mode == "ratio" and not 0 <= self.opex_ratio < 1:
            err("opex_ratio", "Must be between 0% and 100%")
        if self.vacancy_rate + self.credit_loss_rate >= 1:
            err("vacancy_rate", "Vacancy plus credit loss must be below 100%")
        for name in ("rent_growth", "other_income_growth", "opex_growth", "capex_growth"):
            if not -0.5 < getattr(self, name) < 1:
                err(name, "Growth rate must be between -50% and 100%")
        if self.rent_growth_by_year is not None:
            if any(not -0.5 < g < 1 for g in self.rent_growth_by_year):
                err("rent_growth_by_year", "Each growth rate must be between -50% and 100%")
        if not 0 < self.exit_cap_rate < 0.5:
            err("exit_cap_rate", "Must be between 0% and 50%")
        if not -1 < self.discount_rate < 1:
            err("discount_rate", "Must be between -100% and 100%")
        if self.upfront_capex < 0 or self.capex_reserve_annual < 0:
            err("capex", "Capital expenditures cannot be negative")
        if self.other_income < 0:
            err("other_income", "Cannot be negative")
        if self.revenue_mode == "unit_mix":
            if not self.unit_mix:
                err("unit_mix", "At least one unit type is required in unit-mix revenue mode")
            for i, u in enumerate(self.unit_mix):
                if u.units < 0 or u.in_place_rent_monthly < 0:
                    err(f"unit_mix[{i}]", "Units and rents cannot be negative")
        elif self.revenue_mode == "per_sf":
            if not self.rentable_sf or self.rentable_sf <= 0:
                err("rentable_sf", "Required (> 0) in per-SF revenue mode")
            if self.rent_psf_annual < 0:
                err("rent_psf_annual", "Cannot be negative")
        elif self.revenue_mode == "lump_sum" and self.gross_potential_rent < 0:
            err("gross_potential_rent", "Cannot be negative")
        for i, e in enumerate(self.expense_lines):
            if e.amount_annual < 0:
                err(f"expense_lines[{i}]", "Expense amounts cannot be negative")
        if self.loan is not None:
            errors.extend(_validate_loan(self.loan, self.purchase_price))
        if self.preferred_equity is not None:
            pe = self.preferred_equity
            if pe.amount < 0 or not 0 <= pe.pref_rate < 1 or not 0 <= pe.accrual_rate < 1:
                err("preferred_equity", "Amount and rates must be non-negative and below 100%")
        if errors:
            raise AssumptionError(errors)
        return self.warnings()

    def warnings(self) -> list[dict[str, str]]:
        """Flags for aggressive-but-possible assumptions."""
        flags: list[dict[str, str]] = []

        def flag(f: str, severity: str, m: str) -> None:
            flags.append({"field": f, "severity": severity, "message": m})

        growth_rates = [self.rent_growth] + list(self.rent_growth_by_year or [])
        if max(growth_rates) > MAX_REASONABLE_RENT_GROWTH:
            flag("rent_growth", "high", f"Rent growth above {MAX_REASONABLE_RENT_GROWTH:.0%} is aggressive")
        if self.vacancy_rate > MAX_REASONABLE_VACANCY:
            flag("vacancy_rate", "medium", f"Vacancy above {MAX_REASONABLE_VACANCY:.0%} indicates distress")
        if self.vacancy_rate < 0.03:
            flag("vacancy_rate", "medium", "Vacancy below 3% leaves little cushion for turnover")
        if self.exit_cap_rate < MIN_REASONABLE_EXIT_CAP:
            flag("exit_cap_rate", "high", f"Exit cap below {MIN_REASONABLE_EXIT_CAP:.1%} is aggressive")
        if self.opex_growth < self.rent_growth - 0.02:
            flag("opex_growth", "medium", "Expenses grow much slower than rents, widening margins")
        if self.loan is not None:
            loan_amount = resolve_loan_amount(self.loan, self.purchase_price)
            if loan_amount / self.purchase_price > MAX_REASONABLE_LTV:
                flag("loan", "high", f"Leverage above {MAX_REASONABLE_LTV:.0%} LTV")
            if self.loan.term_years < self.hold_period_years:
                flag("loan.term_years", "medium", "Loan matures before the planned exit (refinance risk)")
        return flags


def resolve_loan_amount(loan: Loan, purchase_price: float) -> float:
    if loan.amount is not None:
        return float(loan.amount)
    return float(loan.ltv or 0.0) * purchase_price


def _validate_loan(loan: Loan, purchase_price: float) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    def err(f: str, m: str) -> None:
        errors.append({"field": f"loan.{f}", "message": m})

    if loan.loan_type not in LOAN_TYPES:
        err("loan_type", f"Must be one of {', '.join(LOAN_TYPES)}")
    if loan.rate_type not in RATE_TYPES:
        err("rate_type", f"Must be one of {', '.join(RATE_TYPES)}")
    if loan.amount is None and loan.ltv is None:
        err("amount", "Provide either a loan amount or an LTV")
    if loan.amount is not None and loan.amount < 0:
        err("amount", "Cannot be negative")
    if loan.ltv is not None and not 0 <= loan.ltv < 1:
        err("ltv", "Must be between 0% and 100%")
    if resolve_loan_amount(loan, purchase_price) >= purchase_price * 1.0 and purchase_price > 0:
        err("amount", "Loan cannot equal or exceed the purchase price")
    if not 0 <= loan.all_in_rate < 0.5:
        err("interest_rate", "All-in rate must be between 0% and 50%")
    if loan.amortization_years < 0 or loan.amortization_years > 40:
        err("amortization_years", "Must be between 0 (interest only) and 40")
    if loan.term_years < 1 or loan.term_years > 40:
        err("term_years", "Must be between 1 and 40")
    if loan.io_years < 0 or loan.io_years > loan.term_years:
        err("io_years", "Interest-only period must be within the loan term")
    if not 0 <= loan.origination_fee_pct < 0.1 or not 0 <= loan.exit_fee_pct < 0.1:
        err("fees", "Fees must be between 0% and 10%")
    return errors


def _build(cls: type, data: Any, path: str) -> Any:
    if isinstance(data, cls):
        return data
    if not isinstance(data, dict):
        raise AssumptionError([{"field": path, "message": "Must be an object"}])
    known = {f.name for f in fields(cls)}
    unknown = sorted(set(data) - known)
    if unknown:
        raise AssumptionError([{"field": f"{path}.{k}", "message": "Unknown field"} for k in unknown])
    try:
        return cls(**data)
    except TypeError as exc:
        raise AssumptionError([{"field": path, "message": str(exc)}]) from exc
