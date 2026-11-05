import time

import numpy_financial as npf
import pytest

from axiom_engine import AssumptionError, Assumptions, run_underwriting
from axiom_engine.tvm import pmt, remaining_balance
from axiom_engine.underwriting import market_gpr, rent_growth_for_year, total_units, year1_gpr


def independent_noi(year: int) -> float:
    """Re-derivation of the SIMPLE_MF NOI by hand, independent of the engine."""
    gpr = 50 * 1500 * 12 * 1.03 ** (year - 1)
    return gpr * 0.95 - 300_000 * 1.025 ** (year - 1)


class TestYear1:
    def test_income_statement(self, simple_mf):
        r = run_underwriting(simple_mf)
        y1 = r.annual[0]
        assert y1.gross_potential_rent == pytest.approx(900_000)
        assert y1.vacancy_loss == pytest.approx(45_000)
        assert y1.effective_gross_income == pytest.approx(855_000)
        assert y1.operating_expenses == pytest.approx(300_000)
        assert y1.noi == pytest.approx(555_000)
        assert r.metrics.going_in_cap_rate == pytest.approx(0.0555)
        assert r.metrics.expense_ratio_year1 == pytest.approx(300_000 / 855_000)
        assert r.metrics.price_per_unit == pytest.approx(200_000)
        assert r.metrics.price_per_sf is None

    def test_growth_in_later_years(self, simple_mf):
        r = run_underwriting(simple_mf)
        for row in r.annual:
            assert row.noi == pytest.approx(independent_noi(row.year))


class TestAllCash:
    def test_cash_flows_and_returns(self, simple_mf):
        r = run_underwriting(simple_mf)
        equity = 10_200_000
        terminal = independent_noi(6) / 0.055
        net_sale = terminal * 0.98
        expected = [-equity] + [independent_noi(y) for y in range(1, 6)]
        expected[-1] += net_sale
        assert r.unlevered_cash_flows == pytest.approx(expected)
        assert r.levered_cash_flows == pytest.approx(expected)  # no debt
        assert r.metrics.irr_unlevered == pytest.approx(npf.irr(expected), abs=1e-8)
        assert r.metrics.npv_unlevered == pytest.approx(npf.npv(0.08, expected))
        assert r.metrics.equity_multiple_unlevered == pytest.approx(sum(expected[1:]) / equity)
        assert r.exit.gross_sale_price == pytest.approx(terminal)
        assert r.exit.net_sale_proceeds == pytest.approx(net_sale)
        assert r.metrics.dscr_year1 is None
        assert r.metrics.ltv is None and r.metrics.ltc is None
        assert r.metrics.min_dscr is None
        assert r.debt_schedule == []
        assert r.sources_and_uses.total_sources == pytest.approx(r.sources_and_uses.total_uses)

    def test_profit(self, simple_mf):
        r = run_underwriting(simple_mf)
        assert r.metrics.profit_unlevered == pytest.approx(sum(r.unlevered_cash_flows))


class TestLevered:
    def test_debt_service_and_sources_uses(self, levered_mf):
        r = run_underwriting(levered_mf)
        loan = 6_500_000
        assert r.metrics.loan_amount == loan
        assert r.metrics.equity_invested == pytest.approx(10_200_000 - loan)
        # IO for 24 months
        assert r.annual[0].debt_service == pytest.approx(loan * 0.06)
        assert r.annual[1].debt_service == pytest.approx(loan * 0.06)
        amort = pmt(0.005, 360, loan) * 12
        assert r.annual[2].debt_service == pytest.approx(amort)
        assert r.annual[4].loan_balance == pytest.approx(remaining_balance(0.005, 360, loan, 36))
        assert r.metrics.dscr_year1 == pytest.approx(555_000 / 390_000)
        assert r.metrics.debt_yield_year1 == pytest.approx(555_000 / loan)
        assert r.metrics.ltv == pytest.approx(0.65)
        assert r.metrics.ltc == pytest.approx(loan / 10_200_000)
        assert r.metrics.min_dscr == pytest.approx(min(row.noi / row.debt_service for row in r.annual))

    def test_levered_cash_flows(self, levered_mf):
        r = run_underwriting(levered_mf)
        equity = 3_700_000
        flows = [-equity] + [row.noi - row.debt_service for row in r.annual]
        flows[-1] += r.exit.net_sale_proceeds - r.exit.loan_payoff
        assert r.levered_cash_flows == pytest.approx(flows)
        assert r.metrics.irr_levered == pytest.approx(npf.irr(flows), abs=1e-8)
        assert r.metrics.cash_on_cash_year1 == pytest.approx((555_000 - 390_000) / equity)
        assert r.metrics.equity_multiple_levered == pytest.approx(sum(flows[1:]) / equity)
        assert r.metrics.irr_levered > r.metrics.irr_unlevered  # positive leverage

    def test_breakeven_occupancy(self, levered_mf):
        r = run_underwriting(levered_mf)
        assert r.metrics.breakeven_occupancy == pytest.approx((300_000 + 390_000) / 900_000)

    def test_explicit_loan_amount_and_fees(self, levered_mf):
        levered_mf["loan"] = {"amount": 6_000_000, "interest_rate": 0.065, "amortization_years": 0,
                              "term_years": 5, "origination_fee_pct": 0.01, "exit_fee_pct": 0.01}
        r = run_underwriting(levered_mf)
        assert r.sources_and_uses.loan_fees == pytest.approx(60_000)
        assert r.metrics.equity_invested == pytest.approx(10_200_000 + 60_000 - 6_000_000)
        assert all(row.principal == 0 for row in r.annual)  # full IO
        assert r.exit.loan_payoff == pytest.approx(6_000_000)
        assert r.exit.loan_exit_fee == pytest.approx(60_000)

    def test_covenant_breach_detection(self, levered_mf):
        levered_mf["loan"].update(ltv=0.75, interest_rate=0.075, min_dscr_covenant=1.30, max_ltv_covenant=0.60)
        r = run_underwriting(levered_mf)
        kinds = {b["covenant"] for b in r.covenant_breaches}
        assert kinds == {"min_dscr", "max_ltv"}

    def test_covenants_respected(self, levered_mf):
        levered_mf["loan"].update(min_dscr_covenant=1.0, max_ltv_covenant=0.9)
        assert run_underwriting(levered_mf).covenant_breaches == []

    def test_zero_loan_amount_is_all_cash(self, simple_mf):
        simple_mf["loan"] = {"amount": 0, "interest_rate": 0.06}
        r = run_underwriting(simple_mf)
        assert r.debt_schedule == []
        assert r.metrics.ltv is None

    def test_preferred_equity(self, levered_mf):
        levered_mf["preferred_equity"] = {"amount": 1_000_000, "pref_rate": 0.08, "accrual_rate": 0.02}
        r = run_underwriting(levered_mf)
        assert r.sources_and_uses.common_equity == pytest.approx(2_700_000)
        assert r.annual[0].pref_distribution == pytest.approx(80_000)
        assert r.annual[0].btcf == pytest.approx(555_000 - 390_000 - 80_000)
        assert r.exit.pref_redemption == pytest.approx(1_000_000 * 1.02**5)

    def test_capital_stack_exceeding_cost_rejected(self, levered_mf):
        levered_mf["preferred_equity"] = {"amount": 4_000_000, "pref_rate": 0.08}
        with pytest.raises(AssumptionError):
            run_underwriting(levered_mf)


class TestRevenueAndExpenseModes:
    def test_per_sf_ratio_mode(self, industrial):
        r = run_underwriting(industrial)
        y1 = r.annual[0]
        gpr = 200_000 * 9.5
        egi = gpr * (1 - 0.04 - 0.01) + 50_000
        assert y1.gross_potential_rent == pytest.approx(gpr)
        assert y1.credit_loss == pytest.approx(gpr * 0.01)
        assert y1.effective_gross_income == pytest.approx(egi)
        assert y1.operating_expenses == pytest.approx(egi * 0.12 + egi * 0.03)
        assert y1.cash_flow_before_debt == pytest.approx(y1.noi - 30_000)
        assert r.annual[1].capex_reserve == pytest.approx(30_000 * 1.025)
        assert r.annual[1].other_income == pytest.approx(50_000 * 1.02)
        assert r.metrics.price_per_sf == pytest.approx(120)
        assert r.metrics.price_per_unit is None
        assert r.sources_and_uses.loan_fees == pytest.approx(24_000_000 * 0.55 * 0.01)

    def test_floating_rate(self, industrial):
        r = run_underwriting(industrial)
        loan = 24_000_000 * 0.55
        assert r.annual[0].debt_service == pytest.approx(pmt(0.0605 / 12, 300, loan) * 12)

    def test_lump_sum_mode(self, simple_mf):
        simple_mf.update(revenue_mode="lump_sum", gross_potential_rent=1_000_000, unit_mix=[], units=40)
        r = run_underwriting(simple_mf)
        assert r.annual[0].gross_potential_rent == 1_000_000
        assert r.metrics.price_per_unit == pytest.approx(250_000)

    def test_expense_line_growth_override(self, simple_mf):
        simple_mf["expense_lines"].append({"name": "Insurance", "amount_annual": 50_000, "growth": 0.10})
        r = run_underwriting(simple_mf)
        assert r.annual[1].expense_detail["Insurance"] == pytest.approx(55_000)
        assert r.annual[1].expense_detail["Taxes"] == pytest.approx(300_000 * 1.025)

    def test_rent_growth_schedule(self, simple_mf):
        simple_mf["rent_growth_by_year"] = [0.10, 0.0]
        r = run_underwriting(simple_mf)
        assert r.annual[1].gross_potential_rent == pytest.approx(990_000)
        assert r.annual[2].gross_potential_rent == pytest.approx(990_000)
        assert r.annual[3].gross_potential_rent == pytest.approx(990_000 * 1.03)

    def test_helpers(self, simple_mf):
        a = Assumptions.from_dict(simple_mf)
        assert year1_gpr(a) == 900_000
        assert market_gpr(a) == 50 * 1600 * 12
        assert total_units(a) == 50
        assert rent_growth_for_year(a, 2) == 0.03
        a.unit_mix[0].market_rent_monthly = None
        assert market_gpr(a) == 900_000
        a.revenue_mode = "per_sf"
        assert market_gpr(a) is None
        a.unit_mix = []
        assert total_units(a) is None
        a.units = 12
        assert total_units(a) == 12


class TestOutputs:
    def test_audit_trace_covers_headline_metrics(self, levered_mf):
        r = run_underwriting(levered_mf)
        names = {t["metric"] for t in r.audit_trace}
        for required in ("NOI (Y1)", "Going-in Cap Rate", "Levered IRR", "Unlevered IRR", "DSCR (Y1)",
                         "Terminal Value", "Equity Multiple (levered)"):
            assert required in names
        noi = next(t for t in r.audit_trace if t["metric"] == "NOI (Y1)")
        assert noi["value"] == pytest.approx(555_000)

    @pytest.mark.parametrize("mode,expected", [("unit_mix", "units"), ("per_sf", "SF"), ("lump_sum", "lump")])
    def test_gpr_formula_text(self, industrial, simple_mf, mode, expected):
        data = industrial if mode == "per_sf" else simple_mf
        if mode == "lump_sum":
            data.update(revenue_mode="lump_sum", gross_potential_rent=900_000)
        assert expected in run_underwriting(data).audit_trace[0]["formula"]

    def test_ratio_mode_trace(self, industrial):
        trace = run_underwriting(industrial).audit_trace
        assert "ratio" in next(t for t in trace if t["metric"] == "Operating Expenses (Y1)")["formula"]

    def test_serialisable_snapshot(self, levered_mf):
        d = run_underwriting(levered_mf).to_dict()
        assert d["assumptions"]["purchase_price"] == 10_000_000
        assert len(d["annual"]) == 5
        assert d["engine_version"] == "1.0.0"

    def test_accepts_assumptions_object(self, simple_mf):
        assert run_underwriting(Assumptions.from_dict(simple_mf)).metrics.noi_year1 == pytest.approx(555_000)

    def test_performance_ten_year_under_500ms(self, levered_mf):
        levered_mf["hold_period_years"] = 10
        start = time.perf_counter()
        r = run_underwriting(levered_mf)
        assert (time.perf_counter() - start) < 0.5
        assert r.calc_ms < 500
