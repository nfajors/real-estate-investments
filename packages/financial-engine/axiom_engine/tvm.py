"""Time-value-of-money primitives.

All functions are pure and deterministic. Sign convention: cash outflows are
negative, inflows positive. ``npv`` discounts the first cash flow at t=0
(unlike Excel's ``NPV`` which starts at t=1; the Excel export compensates by
using ``CF0 + NPV(rate, CF1:CFn)``).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

IRR_TOLERANCE = 1e-14
_IRR_UPPER = 100.0


def npv(rate: float, cashflows: Sequence[float]) -> float:
    """Net present value with the first cash flow at t=0."""
    if rate <= -1.0:
        raise ValueError("Discount rate must be greater than -100%")
    total = 0.0
    factor = 1.0
    for cf in cashflows:
        total += cf / factor
        factor *= 1.0 + rate
    return total


def discount_factors(rate: float, periods: int) -> list[float]:
    """Discount factors 1/(1+r)^t for t = 0..periods-1."""
    if rate <= -1.0:
        raise ValueError("Discount rate must be greater than -100%")
    return [1.0 / (1.0 + rate) ** t for t in range(periods)]


def irr(cashflows: Sequence[float], guess: float = 0.10) -> float | None:
    """Internal rate of return.

    Returns ``None`` when no IRR exists (cash flows without a sign change).
    When multiple roots exist the root closest to ``guess`` is returned. The
    algorithm scans a fixed grid for NPV sign changes and refines each bracket
    by bisection, which is slower than Newton's method but always converges.
    """
    flows = list(cashflows)
    has_pos = any(cf > 0 for cf in flows)
    has_neg = any(cf < 0 for cf in flows)
    if not (has_pos and has_neg):
        return None

    grid = _IRR_GRID
    t = np.arange(len(flows), dtype=float)
    with np.errstate(over="ignore", divide="ignore", invalid="ignore"):
        values = (np.asarray(flows, dtype=float)[None, :] / (1.0 + grid[:, None]) ** t[None, :]).sum(axis=1)
    roots: list[float] = []
    for i in range(len(grid) - 1):
        fa, fb = float(values[i]), float(values[i + 1])
        if fa == 0.0:
            roots.append(float(grid[i]))
        elif fa * fb < 0.0:
            roots.append(_bisect(flows, float(grid[i]), float(grid[i + 1]), fa))
    if float(values[-1]) == 0.0:
        roots.append(float(grid[-1]))
    if not roots:
        return None
    return min(roots, key=lambda r: abs(r - guess))


def _build_irr_grid() -> np.ndarray:
    # Fine resolution where real-estate returns live, coarser beyond.
    # Built from integer steps so that 0% and whole percentages are exact grid points.
    fine = np.arange(-199, 200) * 0.005  # -99.5% … 99.5%
    coarse = 1.0 + np.arange(0, int((_IRR_UPPER - 1.0) / 0.25) + 1) * 0.25  # 100% … 10,000%
    return np.concatenate([fine, coarse])


_IRR_GRID = _build_irr_grid()


def _bisect(flows: list[float], lo: float, hi: float, f_lo: float) -> float:
    """Bisection on a bracket [lo, hi] known to contain a sign change."""
    mid = (lo + hi) / 2.0
    while (hi - lo) / 2.0 >= IRR_TOLERANCE:
        mid = (lo + hi) / 2.0
        f_mid = npv(mid, flows)
        if abs(f_mid) < IRR_TOLERANCE:
            break
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return mid


def pmt(rate: float, nper: int, pv: float) -> float:
    """Level payment that fully amortises ``pv`` over ``nper`` periods.

    Returns a positive number for a positive principal (the borrower's payment).
    """
    if nper <= 0:
        raise ValueError("Number of periods must be positive")
    if rate == 0:
        return pv / nper
    return pv * rate / (1.0 - (1.0 + rate) ** (-nper))


def remaining_balance(rate: float, nper: int, pv: float, periods_paid: int) -> float:
    """Outstanding principal after ``periods_paid`` level payments."""
    if periods_paid >= nper:
        return 0.0
    if rate == 0:
        return pv * (1.0 - periods_paid / nper)
    payment = pmt(rate, nper, pv)
    growth = (1.0 + rate) ** periods_paid
    return pv * growth - payment * (growth - 1.0) / rate


def safe_div(numerator: float, denominator: float) -> float | None:
    """Division that returns ``None`` instead of raising or returning inf."""
    if denominator == 0 or math.isnan(denominator):
        return None
    return numerator / denominator
