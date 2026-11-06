"""Basic ground-up development feasibility (PRD 4.7, basic version).

Monthly model: land at month 0, hard/soft costs drawn straight-line over the
construction period, construction loan funds costs after equity (equity-first),
interest accrues to an interest reserve (capitalised), lease-up ramps NOI
linearly to stabilisation and the asset is sold at stabilisation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .tvm import irr, safe_div


@dataclass
class DevelopmentAssumptions:
    land_cost: float
    hard_costs: float
    soft_costs_pct: float = 0.20  # of hard costs
    contingency_pct: float = 0.05  # of hard + soft
    construction_months: int = 18
    lease_up_months: int = 12
    stabilized_noi: float = 0.0
    exit_cap_rate: float = 0.055
    selling_costs_pct: float = 0.02
    loan_to_cost: float = 0.60
    construction_rate: float = 0.08
    loan_fee_pct: float = 0.01

    def validate(self) -> None:
        problems = []
        if self.land_cost < 0 or self.hard_costs <= 0:
            problems.append("Land cost must be non-negative and hard costs positive")
        if not 1 <= self.construction_months <= 72 or not 0 <= self.lease_up_months <= 60:
            problems.append("Construction 1–72 months, lease-up 0–60 months")
        if not 0 <= self.loan_to_cost < 0.9:
            problems.append("Loan-to-cost must be between 0% and 90%")
        if not 0 < self.exit_cap_rate < 0.5:
            problems.append("Exit cap must be between 0% and 50%")
        if self.stabilized_noi <= 0:
            problems.append("Stabilized NOI must be positive")
        if problems:
            raise ValueError("; ".join(problems))


def run_development(inputs: DevelopmentAssumptions | dict[str, Any]) -> dict[str, Any]:
    d = inputs if isinstance(inputs, DevelopmentAssumptions) else DevelopmentAssumptions(**inputs)
    d.validate()
    soft = d.hard_costs * d.soft_costs_pct
    contingency = (d.hard_costs + soft) * d.contingency_pct
    base_cost = d.land_cost + d.hard_costs + soft + contingency

    # Fixed-point iteration: the interest reserve depends on the loan size, which
    # depends on total cost. The contraction ratio is ~LTC × rate × duration, so
    # 40 iterations converge far below a cent for any valid input.
    interest_reserve = 0.0
    for _ in range(40):
        loan_fee = (base_cost + interest_reserve) * d.loan_to_cost * d.loan_fee_pct
        total_cost = base_cost + interest_reserve + loan_fee
        loan_commitment = total_cost * d.loan_to_cost
        equity = total_cost - loan_commitment
        monthly_build = (d.hard_costs + soft + contingency) / d.construction_months
        months = d.construction_months + d.lease_up_months
        r = d.construction_rate / 12.0
        spent_equity = 0.0
        balance = 0.0
        interest_total = 0.0
        monthly_equity: list[float] = []
        for m in range(months + 1):
            cost = (d.land_cost + loan_fee) if m == 0 else (monthly_build if m <= d.construction_months else 0.0)
            interest = balance * r
            interest_total += interest
            need = cost + interest
            from_equity = min(need, max(0.0, equity - spent_equity))
            spent_equity += from_equity
            balance += need - from_equity
            monthly_equity.append(-from_equity)
        interest_reserve = interest_total

    # Lease-up NOI ramp (paid to equity, after interest which is reserved).
    ramp = []
    for m in range(months + 1):
        if m <= d.construction_months or d.lease_up_months == 0:
            ramp.append(0.0)
        else:
            frac = (m - d.construction_months) / d.lease_up_months
            ramp.append(d.stabilized_noi / 12.0 * frac)
    stabilized_value = d.stabilized_noi / d.exit_cap_rate
    net_sale = stabilized_value * (1.0 - d.selling_costs_pct)
    flows = [monthly_equity[m] + ramp[m] for m in range(months + 1)]
    flows[-1] += net_sale - balance
    monthly_irr = irr(flows, guess=0.01)
    annual_irr = (1.0 + monthly_irr) ** 12 - 1.0 if monthly_irr is not None else None
    distributions = sum(f for f in flows if f > 0)
    contributions = -sum(f for f in flows if f < 0)
    yield_on_cost = d.stabilized_noi / total_cost
    return {
        "inputs": asdict(d),
        "budget": {
            "land": d.land_cost,
            "hard_costs": d.hard_costs,
            "soft_costs": soft,
            "contingency": contingency,
            "loan_fees": loan_fee,
            "interest_reserve": interest_reserve,
            "total_cost": total_cost,
        },
        "capital": {"construction_loan": loan_commitment, "equity": equity, "loan_balance_at_exit": balance},
        "returns": {
            "yield_on_cost": yield_on_cost,
            "development_spread_bps": (yield_on_cost - d.exit_cap_rate) * 10000.0,
            "stabilized_value": stabilized_value,
            "profit": distributions - contributions,
            "profit_margin": safe_div(stabilized_value - total_cost, total_cost),
            "irr": annual_irr,
            "equity_multiple": safe_div(distributions, contributions),
        },
        "monthly_equity_cash_flows": flows,
    }
