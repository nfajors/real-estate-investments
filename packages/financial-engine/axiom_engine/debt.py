"""Loan amortisation with interest-only periods, computed monthly and rolled up annually."""

from __future__ import annotations

from dataclasses import dataclass

from .assumptions import Loan
from .tvm import pmt


@dataclass(frozen=True)
class DebtYear:
    year: int
    beginning_balance: float
    interest: float
    principal: float
    debt_service: float
    ending_balance: float


@dataclass(frozen=True)
class DebtSchedule:
    loan_amount: float
    annual_rate: float
    monthly_payment_amortizing: float
    io_monthly_payment: float
    years: list[DebtYear]

    def balance_at_end_of(self, year: int) -> float:
        if year <= 0:
            return self.loan_amount
        return self.years[year - 1].ending_balance

    def debt_service(self, year: int) -> float:
        return self.years[year - 1].debt_service


def build_schedule(loan: Loan, loan_amount: float, years: int) -> DebtSchedule:
    """Monthly amortisation schedule for ``years`` years.

    * Months 1..io_months pay interest only.
    * Thereafter a level payment amortises the balance over ``amortization_years``
      (measured from the end of the IO period). ``amortization_years == 0`` means
      interest-only for the whole term.
    * After loan maturity (``term_years``) the schedule continues at the same
      payment so the hold-period model remains defined; the underwriting layer
      flags maturity-before-exit as refinance risk.
    """
    monthly_rate = loan.all_in_rate / 12.0
    io_months = int(round(loan.io_years * 12))
    amortizing = loan.amortization_years > 0
    amort_payment = pmt(monthly_rate, loan.amortization_years * 12, loan_amount) if amortizing else 0.0
    io_payment = loan_amount * monthly_rate

    balance = loan_amount
    out: list[DebtYear] = []
    month = 0
    for y in range(1, years + 1):
        begin = balance
        interest_total = principal_total = 0.0
        for _ in range(12):
            month += 1
            interest = balance * monthly_rate
            if month <= io_months or not amortizing:
                principal = 0.0
            else:
                principal = min(amort_payment - interest, balance)
            balance -= principal
            interest_total += interest
            principal_total += principal
        out.append(
            DebtYear(
                year=y,
                beginning_balance=begin,
                interest=interest_total,
                principal=principal_total,
                debt_service=interest_total + principal_total,
                ending_balance=balance,
            )
        )
    return DebtSchedule(
        loan_amount=loan_amount,
        annual_rate=loan.all_in_rate,
        monthly_payment_amortizing=amort_payment,
        io_monthly_payment=io_payment,
        years=out,
    )
