"""Core deterministic underwriting engine (PRD section 8).

``run_underwriting`` projects ``hold_period_years + 1`` years of operations
(the extra year provides forward NOI for the terminal value), builds unlevered
and levered cash flows and returns every metric together with an audit trace
of the formulas used.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

from . import ENGINE_VERSION
from .assumptions import AssumptionError, Assumptions, resolve_loan_amount
from .debt import DebtSchedule, build_schedule
from .tvm import irr, npv, safe_div


@dataclass
class YearCashFlow:
    year: int
    gross_potential_rent: float
    vacancy_loss: float
    credit_loss: float
    other_income: float
    effective_gross_income: float
    operating_expenses: float
    expense_detail: dict[str, float]
    noi: float
    capex_reserve: float
    cash_flow_before_debt: float
    debt_service: float
    interest: float
    principal: float
    pref_distribution: float
    btcf: float
    loan_balance: float
    dscr: float | None
    debt_yield: float | None
    cash_on_cash: float | None


@dataclass
class SourcesAndUses:
    purchase_price: float
    closing_costs: float
    upfront_capex: float
    loan_fees: float
    total_uses: float
    senior_loan: float
    preferred_equity: float
    common_equity: float
    total_sources: float


@dataclass
class ExitSummary:
    exit_year: int
    forward_noi: float
    exit_cap_rate: float
    gross_sale_price: float
    selling_costs: float
    net_sale_proceeds: float
    loan_payoff: float
    loan_exit_fee: float
    pref_redemption: float
    net_proceeds_to_equity: float


@dataclass
class Metrics:
    noi_year1: float
    egi_year1: float
    opex_year1: float
    expense_ratio_year1: float | None
    going_in_cap_rate: float
    exit_cap_rate: float
    irr_unlevered: float | None
    irr_levered: float | None
    npv_unlevered: float
    npv_levered: float
    equity_multiple_unlevered: float | None
    equity_multiple_levered: float | None
    cash_on_cash_year1: float | None
    avg_cash_on_cash: float | None
    dscr_year1: float | None
    min_dscr: float | None
    debt_yield_year1: float | None
    ltv: float | None
    ltc: float | None
    loan_amount: float
    equity_invested: float
    total_project_cost: float
    price_per_unit: float | None
    price_per_sf: float | None
    breakeven_occupancy: float | None
    profit_levered: float
    profit_unlevered: float


@dataclass
class UnderwritingResult:
    engine_version: str
    metrics: Metrics
    annual: list[YearCashFlow]
    sources_and_uses: SourcesAndUses
    exit: ExitSummary
    unlevered_cash_flows: list[float]
    levered_cash_flows: list[float]
    debt_schedule: list[dict[str, float]]
    warnings: list[dict[str, str]]
    covenant_breaches: list[dict[str, Any]]
    audit_trace: list[dict[str, Any]]
    calc_ms: float = 0.0
    assumptions: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------------
# Revenue & expense building blocks
# ----------------------------------------------------------------------
def year1_gpr(a: Assumptions) -> float:
    """Gross Potential Rent, year 1."""
    if a.revenue_mode == "unit_mix":
        return sum(u.units * u.in_place_rent_monthly * 12.0 for u in a.unit_mix)
    if a.revenue_mode == "per_sf":
        return float(a.rentable_sf or 0.0) * a.rent_psf_annual
    return float(a.gross_potential_rent)


def market_gpr(a: Assumptions) -> float | None:
    """GPR at market rents (unit-mix mode only) – used for loss-to-lease."""
    if a.revenue_mode != "unit_mix" or not a.unit_mix:
        return None
    return sum(
        u.units * (u.market_rent_monthly if u.market_rent_monthly is not None else u.in_place_rent_monthly) * 12.0
        for u in a.unit_mix
    )


def rent_growth_for_year(a: Assumptions, year: int) -> float:
    """Growth applied going *into* ``year`` (year >= 2)."""
    schedule = a.rent_growth_by_year or []
    idx = year - 2
    if 0 <= idx < len(schedule):
        return schedule[idx]
    return a.rent_growth


def total_units(a: Assumptions) -> int | None:
    if a.units is not None:
        return a.units
    if a.unit_mix:
        return sum(u.units for u in a.unit_mix)
    return None


def project_operations(a: Assumptions, years: int) -> list[dict[str, Any]]:
    """Annual operating projection (no debt) for ``years`` years."""
    rows: list[dict[str, Any]] = []
    gpr = year1_gpr(a)
    other = a.other_income
    capex = a.capex_reserve_annual
    for y in range(1, years + 1):
        if y > 1:
            gpr *= 1.0 + rent_growth_for_year(a, y)
            other *= 1.0 + a.other_income_growth
            capex *= 1.0 + a.capex_growth
        vacancy = gpr * a.vacancy_rate
        credit = gpr * a.credit_loss_rate
        egi = gpr - vacancy - credit + other
        detail: dict[str, float] = {}
        if a.opex_mode == "ratio":
            detail["Operating expenses (ratio of EGI)"] = egi * a.opex_ratio
        else:
            for line in a.expense_lines:
                g = a.opex_growth if line.growth is None else line.growth
                detail[line.name] = line.amount_annual * (1.0 + g) ** (y - 1)
        if a.management_fee_pct:
            detail["Management fee"] = egi * a.management_fee_pct
        opex = sum(detail.values())
        noi = egi - opex
        rows.append(
            {
                "year": y,
                "gross_potential_rent": gpr,
                "vacancy_loss": vacancy,
                "credit_loss": credit,
                "other_income": other,
                "effective_gross_income": egi,
                "operating_expenses": opex,
                "expense_detail": detail,
                "noi": noi,
                "capex_reserve": capex,
                "cash_flow_before_debt": noi - capex,
            }
        )
    return rows


# ----------------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------------
def run_underwriting(assumptions: Assumptions | dict[str, Any]) -> UnderwritingResult:
    started = time.perf_counter()
    a = assumptions if isinstance(assumptions, Assumptions) else Assumptions.from_dict(assumptions)
    warnings = a.validate()
    n = a.hold_period_years
    ops = project_operations(a, n + 1)

    # --- Capital structure ---------------------------------------------
    loan_amount = resolve_loan_amount(a.loan, a.purchase_price) if a.loan else 0.0
    schedule: DebtSchedule | None = build_schedule(a.loan, loan_amount, n) if a.loan and loan_amount > 0 else None
    closing_costs = a.purchase_price * a.closing_costs_pct
    loan_fees = loan_amount * a.loan.origination_fee_pct if a.loan else 0.0
    total_uses = a.purchase_price + closing_costs + a.upfront_capex + loan_fees
    pref = a.preferred_equity.amount if a.preferred_equity else 0.0
    common_equity = total_uses - loan_amount - pref
    if common_equity <= 0:
        raise AssumptionError([{"field": "loan", "message": "Debt and preferred equity exceed total project cost"}])
    su = SourcesAndUses(
        purchase_price=a.purchase_price,
        closing_costs=closing_costs,
        upfront_capex=a.upfront_capex,
        loan_fees=loan_fees,
        total_uses=total_uses,
        senior_loan=loan_amount,
        preferred_equity=pref,
        common_equity=common_equity,
        total_sources=loan_amount + pref + common_equity,
    )
    pref_rate = a.preferred_equity.pref_rate if a.preferred_equity else 0.0
    pref_accrual = a.preferred_equity.accrual_rate if a.preferred_equity else 0.0

    # --- Annual rows -----------------------------------------------------
    annual: list[YearCashFlow] = []
    covenant_breaches: list[dict[str, Any]] = []
    for row in ops[:n]:
        y = row["year"]
        ds = schedule.debt_service(y) if schedule else 0.0
        interest = schedule.years[y - 1].interest if schedule else 0.0
        principal = schedule.years[y - 1].principal if schedule else 0.0
        balance = schedule.balance_at_end_of(y) if schedule else 0.0
        pref_dist = pref * pref_rate
        btcf = row["cash_flow_before_debt"] - ds - pref_dist
        dscr = safe_div(row["noi"], ds) if ds else None
        debt_yield = safe_div(row["noi"], schedule.balance_at_end_of(y - 1)) if schedule else None
        annual.append(
            YearCashFlow(
                **row,
                debt_service=ds,
                interest=interest,
                principal=principal,
                pref_distribution=pref_dist,
                btcf=btcf,
                loan_balance=balance,
                dscr=dscr,
                debt_yield=debt_yield,
                cash_on_cash=safe_div(btcf, common_equity),
            )
        )
        if a.loan and a.loan.min_dscr_covenant and dscr is not None and dscr < a.loan.min_dscr_covenant:
            covenant_breaches.append(
                {"year": y, "covenant": "min_dscr", "threshold": a.loan.min_dscr_covenant, "actual": dscr}
            )

    # --- Exit ------------------------------------------------------------
    forward_noi = ops[n]["noi"]
    gross_sale = forward_noi / a.exit_cap_rate
    selling_costs = gross_sale * a.selling_costs_pct
    net_sale = gross_sale - selling_costs
    payoff = schedule.balance_at_end_of(n) if schedule else 0.0
    exit_fee = payoff * a.loan.exit_fee_pct if a.loan else 0.0
    pref_redemption = pref * (1.0 + pref_accrual) ** n if pref else 0.0
    to_equity = net_sale - payoff - exit_fee - pref_redemption
    exit_summary = ExitSummary(
        exit_year=n,
        forward_noi=forward_noi,
        exit_cap_rate=a.exit_cap_rate,
        gross_sale_price=gross_sale,
        selling_costs=selling_costs,
        net_sale_proceeds=net_sale,
        loan_payoff=payoff,
        loan_exit_fee=exit_fee,
        pref_redemption=pref_redemption,
        net_proceeds_to_equity=to_equity,
    )
    if a.loan and a.loan.max_ltv_covenant and loan_amount:
        ltv_at_exit = safe_div(payoff, gross_sale)
        if ltv_at_exit is not None and ltv_at_exit > a.loan.max_ltv_covenant:
            covenant_breaches.append(
                {"year": n, "covenant": "max_ltv", "threshold": a.loan.max_ltv_covenant, "actual": ltv_at_exit}
            )

    # --- Cash flow vectors ----------------------------------------------
    unlevered_equity = a.purchase_price + closing_costs + a.upfront_capex
    unlevered = [-unlevered_equity] + [r.cash_flow_before_debt for r in annual]
    unlevered[-1] += net_sale
    levered = [-common_equity] + [r.btcf for r in annual]
    levered[-1] += to_equity

    # --- Metrics ---------------------------------------------------------
    y1 = annual[0]
    gpr1 = y1.gross_potential_rent
    ds1 = y1.debt_service
    dist_lev = sum(levered[1:])
    dist_unlev = sum(unlevered[1:])
    units = total_units(a)
    metrics = Metrics(
        noi_year1=y1.noi,
        egi_year1=y1.effective_gross_income,
        opex_year1=y1.operating_expenses,
        expense_ratio_year1=safe_div(y1.operating_expenses, y1.effective_gross_income),
        going_in_cap_rate=y1.noi / a.purchase_price,
        exit_cap_rate=a.exit_cap_rate,
        irr_unlevered=irr(unlevered),
        irr_levered=irr(levered),
        npv_unlevered=npv(a.discount_rate, unlevered),
        npv_levered=npv(a.discount_rate, levered),
        equity_multiple_unlevered=safe_div(dist_unlev, unlevered_equity),
        equity_multiple_levered=safe_div(dist_lev, common_equity),
        cash_on_cash_year1=y1.cash_on_cash,
        avg_cash_on_cash=safe_div(sum(r.btcf for r in annual) / n, common_equity),
        dscr_year1=y1.dscr,
        min_dscr=min((r.dscr for r in annual if r.dscr is not None), default=None),
        debt_yield_year1=y1.debt_yield,
        ltv=safe_div(loan_amount, a.purchase_price) if loan_amount else None,
        ltc=safe_div(loan_amount, total_uses) if loan_amount else None,
        loan_amount=loan_amount,
        equity_invested=common_equity,
        total_project_cost=total_uses,
        price_per_unit=safe_div(a.purchase_price, units) if units else None,
        price_per_sf=safe_div(a.purchase_price, a.rentable_sf) if a.rentable_sf else None,
        breakeven_occupancy=safe_div(y1.operating_expenses + ds1 + y1.pref_distribution, gpr1 + y1.other_income),
        profit_levered=dist_lev - common_equity,
        profit_unlevered=dist_unlev - unlevered_equity,
    )

    trace = _audit_trace(a, metrics, y1, exit_summary, su, unlevered, levered)
    result = UnderwritingResult(
        engine_version=ENGINE_VERSION,
        metrics=metrics,
        annual=annual,
        sources_and_uses=su,
        exit=exit_summary,
        unlevered_cash_flows=unlevered,
        levered_cash_flows=levered,
        debt_schedule=[asdict(d) for d in schedule.years] if schedule else [],
        warnings=warnings,
        covenant_breaches=covenant_breaches,
        audit_trace=trace,
        assumptions=a.to_dict(),
    )
    result.calc_ms = (time.perf_counter() - started) * 1000.0
    return result


def _audit_trace(
    a: Assumptions,
    m: Metrics,
    y1: YearCashFlow,
    ex: ExitSummary,
    su: SourcesAndUses,
    unlevered: list[float],
    levered: list[float],
) -> list[dict[str, Any]]:
    """Human-readable record of how each headline figure was produced."""
    return [
        {"metric": "Gross Potential Rent (Y1)", "formula": _gpr_formula(a), "value": y1.gross_potential_rent},
        {"metric": "Vacancy Loss (Y1)", "formula": "GPR × vacancy rate",
         "inputs": {"gpr": y1.gross_potential_rent, "vacancy_rate": a.vacancy_rate}, "value": y1.vacancy_loss},
        {"metric": "Effective Gross Income (Y1)", "formula": "GPR − Vacancy − Credit Loss + Other Income",
         "inputs": {"gpr": y1.gross_potential_rent, "vacancy": y1.vacancy_loss, "credit_loss": y1.credit_loss,
                    "other_income": y1.other_income}, "value": y1.effective_gross_income},
        {"metric": "Operating Expenses (Y1)",
         "formula": "EGI × opex ratio" if a.opex_mode == "ratio" else "Σ expense line items (+ management fee % × EGI)",
         "inputs": y1.expense_detail, "value": y1.operating_expenses},
        {"metric": "NOI (Y1)", "formula": "EGI − Operating Expenses",
         "inputs": {"egi": y1.effective_gross_income, "opex": y1.operating_expenses}, "value": y1.noi},
        {"metric": "Going-in Cap Rate", "formula": "NOI (Y1) ÷ Purchase Price",
         "inputs": {"noi": y1.noi, "purchase_price": a.purchase_price}, "value": m.going_in_cap_rate},
        {"metric": "Total Uses", "formula": "Price + Closing Costs + Upfront Capex + Loan Fees",
         "inputs": {"price": su.purchase_price, "closing": su.closing_costs, "capex": su.upfront_capex,
                    "loan_fees": su.loan_fees}, "value": su.total_uses},
        {"metric": "Common Equity", "formula": "Total Uses − Senior Loan − Preferred Equity",
         "inputs": {"total_uses": su.total_uses, "loan": su.senior_loan, "pref": su.preferred_equity},
         "value": su.common_equity},
        {"metric": "Debt Service (Y1)", "formula": "Σ monthly payments (interest-only during IO, then level P&I)",
         "inputs": {"rate": a.loan.all_in_rate if a.loan else 0.0, "loan_amount": m.loan_amount},
         "value": y1.debt_service},
        {"metric": "DSCR (Y1)", "formula": "NOI ÷ Debt Service",
         "inputs": {"noi": y1.noi, "debt_service": y1.debt_service}, "value": m.dscr_year1},
        {"metric": "Cash-on-Cash (Y1)", "formula": "(NOI − Capex − Debt Service − Pref) ÷ Common Equity",
         "inputs": {"btcf": y1.btcf, "equity": su.common_equity}, "value": m.cash_on_cash_year1},
        {"metric": "Terminal Value", "formula": f"Year {ex.exit_year + 1} NOI ÷ Exit Cap Rate",
         "inputs": {"forward_noi": ex.forward_noi, "exit_cap_rate": ex.exit_cap_rate}, "value": ex.gross_sale_price},
        {"metric": "Net Sale Proceeds", "formula": "Terminal Value × (1 − selling costs %)",
         "inputs": {"gross": ex.gross_sale_price, "selling_costs_pct": a.selling_costs_pct},
         "value": ex.net_sale_proceeds},
        {"metric": "Unlevered IRR", "formula": "Rate r where NPV(r, unlevered cash flows) = 0",
         "inputs": {"cash_flows": unlevered}, "value": m.irr_unlevered},
        {"metric": "Levered IRR", "formula": "Rate r where NPV(r, levered cash flows) = 0",
         "inputs": {"cash_flows": levered}, "value": m.irr_levered},
        {"metric": "NPV (levered)", "formula": "Σ CFₜ ÷ (1 + discount rate)ᵗ, t = 0…N",
         "inputs": {"discount_rate": a.discount_rate}, "value": m.npv_levered},
        {"metric": "Equity Multiple (levered)", "formula": "Σ distributions ÷ common equity",
         "inputs": {"distributions": sum(levered[1:]), "equity": su.common_equity}, "value": m.equity_multiple_levered},
    ]


def _gpr_formula(a: Assumptions) -> str:
    if a.revenue_mode == "unit_mix":
        return "Σ units × in-place monthly rent × 12"
    if a.revenue_mode == "per_sf":
        return "Rentable SF × annual rent per SF"
    return "Gross potential rent (lump sum input)"
