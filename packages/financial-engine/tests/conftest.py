import copy

import pytest

# Simple, hand-checkable multifamily deal (fictional).
SIMPLE_MF = {
    "purchase_price": 10_000_000,
    "hold_period_years": 5,
    "closing_costs_pct": 0.02,
    "revenue_mode": "unit_mix",
    "unit_mix": [{"name": "1BR", "units": 50, "in_place_rent_monthly": 1500, "market_rent_monthly": 1600}],
    "vacancy_rate": 0.05,
    "rent_growth": 0.03,
    "other_income": 0,
    "opex_mode": "line_items",
    "expense_lines": [{"name": "Taxes", "amount_annual": 300_000}],
    "opex_growth": 0.025,
    "exit_cap_rate": 0.055,
    "selling_costs_pct": 0.02,
    "discount_rate": 0.08,
}


@pytest.fixture
def simple_mf():
    return copy.deepcopy(SIMPLE_MF)


@pytest.fixture
def levered_mf():
    d = copy.deepcopy(SIMPLE_MF)
    d["loan"] = {"ltv": 0.65, "interest_rate": 0.06, "amortization_years": 30, "io_years": 2, "term_years": 10}
    return d


@pytest.fixture
def industrial():
    return {
        "purchase_price": 24_000_000,
        "hold_period_years": 7,
        "revenue_mode": "per_sf",
        "rentable_sf": 200_000,
        "rent_psf_annual": 9.5,
        "other_income": 50_000,
        "vacancy_rate": 0.04,
        "credit_loss_rate": 0.01,
        "opex_mode": "ratio",
        "opex_ratio": 0.12,
        "management_fee_pct": 0.03,
        "capex_reserve_annual": 30_000,
        "exit_cap_rate": 0.06,
        "discount_rate": 0.075,
        "loan": {"ltv": 0.55, "rate_type": "floating", "index_rate": 0.043, "spread": 0.0175,
                 "amortization_years": 25, "term_years": 7, "origination_fee_pct": 0.01, "exit_fee_pct": 0.005,
                 "min_dscr_covenant": 1.25},
    }
