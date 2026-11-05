import pytest

from axiom_engine import Loan, run_underwriting
from axiom_engine.debt import build_schedule
from axiom_engine.development import DevelopmentAssumptions, run_development
from axiom_engine.financing import compare_structures
from axiom_engine.montecarlo import InputDistribution, run_monte_carlo
from axiom_engine.risk import risk_assessment
from axiom_engine.scenarios import (
    apply_overrides,
    centered_range,
    default_scenarios,
    get_path,
    metric_value,
    sensitivity_table,
    set_path,
    shift_assumptions,
)
from axiom_engine.tvm import pmt
from axiom_engine.valuation import (
    Comparable,
    cost_approach,
    dcf_value,
    direct_capitalization,
    reconcile,
    sales_comparison,
    valuation_summary,
)


# ----------------------------------------------------------------- debt
class TestDebt:
    def test_amortizing_schedule_reconciles(self):
        s = build_schedule(Loan(interest_rate=0.06, amortization_years=30), 1_000_000, 10)
        for y in s.years:
            assert y.beginning_balance - y.principal == pytest.approx(y.ending_balance)
            assert y.debt_service == pytest.approx(pmt(0.005, 360, 1_000_000) * 12)
        assert s.balance_at_end_of(0) == 1_000_000
        assert s.debt_service(1) == s.years[0].debt_service

    def test_short_amortization_pays_off(self):
        s = build_schedule(Loan(interest_rate=0.05, amortization_years=2, term_years=5), 100_000, 4)
        assert s.years[1].ending_balance == pytest.approx(0, abs=1e-6)
        assert s.years[3].debt_service == pytest.approx(0, abs=1e-6)

    def test_interest_only(self):
        s = build_schedule(Loan(interest_rate=0.06, amortization_years=0), 1_000_000, 3)
        assert all(y.principal == 0 and y.debt_service == pytest.approx(60_000) for y in s.years)
        assert s.monthly_payment_amortizing == 0


# ------------------------------------------------------------ scenarios
class TestScenarios:
    def test_path_helpers(self, levered_mf):
        assert get_path(levered_mf, "loan.interest_rate") == 0.06
        set_path(levered_mf, "loan.interest_rate", 0.07)
        assert levered_mf["loan"]["interest_rate"] == 0.07
        with pytest.raises(KeyError):
            get_path(levered_mf, "loan.nope")
        with pytest.raises(KeyError):
            get_path(levered_mf, "purchase_price.deeper")
        with pytest.raises(KeyError):
            set_path(levered_mf, "nothing.here", 1)

    def test_apply_overrides_does_not_mutate(self, simple_mf):
        out = apply_overrides(simple_mf, {"vacancy_rate": 0.1})
        assert out["vacancy_rate"] == 0.1 and simple_mf["vacancy_rate"] == 0.05

    def test_shift_floors_vacancy(self, simple_mf):
        out = shift_assumptions(simple_mf, {"vacancy_rate": -0.5, "rent_growth": 0.01})
        assert out["vacancy_rate"] == 0.0
        assert out["rent_growth"] == pytest.approx(0.04)

    def test_default_scenarios_are_ordered(self, levered_mf):
        sc = default_scenarios(levered_mf)
        irrs = {k: run_underwriting(v).metrics.irr_levered for k, v in sc.items()}
        assert irrs["Conservative"] < irrs["Base"] < irrs["Optimistic"]

    def test_sensitivity_grid(self, levered_mf):
        rows = centered_range(0.03, 0.01, 3)
        cols = centered_range(0.055, 0.0025, 3)
        assert rows == [0.02, 0.03, 0.04]
        t = sensitivity_table(levered_mf, "rent_growth", rows, "exit_cap_rate", cols, "irr_levered")
        g = t["grid"]
        assert len(g) == 3 and len(g[0]) == 3
        assert g[1][1] == pytest.approx(run_underwriting(levered_mf).metrics.irr_levered)
        assert g[2][0] > g[0][2]  # higher growth & lower exit cap → higher IRR
        assert g[0][0] < g[2][0]

    def test_sensitivity_rejects_bad_metric(self, levered_mf):
        with pytest.raises(ValueError):
            sensitivity_table(levered_mf, "rent_growth", [0.02], "exit_cap_rate", [0.05], "magic")
        with pytest.raises(ValueError):
            metric_value(run_underwriting(levered_mf), "magic")


# ----------------------------------------------------------- monte carlo
class TestMonteCarlo:
    DISTS = [
        {"path": "rent_growth", "kind": "normal", "std": 0.01},
        {"path": "exit_cap_rate", "kind": "triangular", "low": 0.05, "mode": 0.055, "high": 0.065},
        {"path": "vacancy_rate", "kind": "uniform", "low": 0.03, "high": 0.08},
    ]

    def test_reproducible_with_seed(self, levered_mf):
        a = run_monte_carlo(levered_mf, self.DISTS, iterations=50, seed=7)
        b = run_monte_carlo(levered_mf, self.DISTS, iterations=50, seed=7)
        assert a == b
        assert a["completed"] == 50 and a["rejected"] == 0
        p = a["irr_levered"]["percentiles"]
        assert p["p5"] <= p["p50"] <= p["p95"]
        assert sum(h["count"] for h in a["irr_levered"]["histogram"]) == 50
        assert 0 <= a["prob_loss"] <= 1

    def test_invalid_samples_rejected(self, levered_mf):
        dists = [InputDistribution(path="exit_cap_rate", kind="normal", mean=-0.01, std=0.0001)]
        out = run_monte_carlo(levered_mf, dists, iterations=10)
        assert out["completed"] == 0 and out["rejected"] == 10
        assert out["irr_levered"]["mean"] is None
        assert out["prob_loss"] is None and out["prob_irr_below_discount_rate"] is None

    def test_undefined_irr_rejected(self, levered_mf):
        # Huge vacancy → negative cash flows every year → IRR undefined
        dists = [{"path": "vacancy_rate", "kind": "uniform", "low": 0.90, "high": 0.94}]
        out = run_monte_carlo(levered_mf, dists, iterations=10)
        assert out["rejected"] == 10

    def test_normal_with_bounds_and_defaults(self, levered_mf):
        dists = [{"path": "rent_growth", "kind": "normal", "std": 0.05, "low": 0.0, "high": 0.04},
                 {"path": "opex_growth", "kind": "triangular"} | {"low": 0.02, "high": 0.03},
                 {"path": "selling_costs_pct", "kind": "triangular", "low": 0.01, "high": 0.03, "mode": 0.02}]
        out = run_monte_carlo(levered_mf, dists, iterations=20)
        assert out["completed"] == 20

    @pytest.mark.parametrize(
        "dist",
        [
            {"path": "rent_growth", "kind": "triangular", "low": 0.05, "mode": 0.01, "high": 0.06},
            {"path": "rent_growth", "kind": "triangular"},
            {"path": "rent_growth", "kind": "uniform", "low": 0.05},
            {"path": "rent_growth", "kind": "lognormal"},
        ],
    )
    def test_bad_distributions(self, levered_mf, dist):
        with pytest.raises(ValueError):
            run_monte_carlo(levered_mf, [dist], iterations=10)

    def test_bad_iterations_or_empty(self, levered_mf):
        with pytest.raises(ValueError):
            run_monte_carlo(levered_mf, self.DISTS, iterations=5)
        with pytest.raises(ValueError):
            run_monte_carlo(levered_mf, [], iterations=10)


# ------------------------------------------------------------- valuation
class TestValuation:
    def test_direct_cap(self):
        assert direct_capitalization(550_000, 0.055) == pytest.approx(10_000_000)
        with pytest.raises(ValueError):
            direct_capitalization(1, 0)

    def test_dcf_value_equals_npv_plus_cost(self, simple_mf):
        r = run_underwriting(simple_mf)
        # NPV of the deal = DCF value − total unlevered cost
        assert dcf_value(r, 0.08) - 10_200_000 == pytest.approx(r.metrics.npv_unlevered)

    def test_sales_comparison_per_unit(self):
        comps = [Comparable("A", 20_000_000, units=100), {"name": "B", "sale_price": 9_000_000, "units": 50,
                                                          "adjustment_pct": 0.1, "weight": 2},
                 {"name": "no size", "sale_price": 1}]
        out = sales_comparison(comps, subject_units=50, subject_sf=None)
        expected_pp = (200_000 * 1 + 198_000 * 2) / 3
        assert out["price_per"] == pytest.approx(expected_pp)
        assert out["value"] == pytest.approx(expected_pp * 50)
        assert len(out["comps"]) == 2

    def test_sales_comparison_per_sf_and_errors(self):
        out = sales_comparison([{"name": "A", "sale_price": 1_000_000, "sf": 10_000}], None, 5_000)
        assert out["basis"] == "sf" and out["value"] == pytest.approx(500_000)
        with pytest.raises(ValueError):
            sales_comparison([{"name": "A", "sale_price": 1}], None, None)
        with pytest.raises(ValueError):
            sales_comparison([{"name": "A", "sale_price": 1, "units": 2}], None, 100)

    def test_cost_approach(self):
        out = cost_approach(2_000_000, 8_000_000, 0.25, 100_000, 50_000, 0.10)
        improvements = 8_800_000
        assert out["total_depreciation"] == pytest.approx(improvements * 0.25 + 150_000)
        assert out["value"] == pytest.approx(2_000_000 + improvements * 0.75 - 150_000)
        with pytest.raises(ValueError):
            cost_approach(1, 1, 1.5)

    def test_reconcile(self):
        out = reconcile({"a": 100.0, "b": 200.0, "c": None}, {"a": 1, "b": 3, "c": 5})
        assert out["reconciled_value"] == pytest.approx(175)
        assert out["range"] == {"low": 100.0, "high": 200.0}
        with pytest.raises(ValueError):
            reconcile({"a": None}, {"a": 1})

    def test_summary(self, simple_mf):
        r = run_underwriting(simple_mf)
        out = valuation_summary(
            r, 0.055, 0.08, 10_000_000,
            comps=[{"name": "A", "sale_price": 10_500_000, "units": 50}], subject_units=50,
            cost={"land_value": 2_000_000, "replacement_cost": 9_000_000, "physical_depreciation_pct": 0.2},
            weights={"direct_cap": 1, "dcf": 1, "sales_comparison": 1, "cost": 1},
        )
        assert set(out["details"]) == {"sales_comparison", "cost"}
        assert out["values"]["direct_cap"] == pytest.approx(555_000 / 0.055)
        assert out["premium_discount_to_value"] == pytest.approx(
            (10_000_000 - out["reconciled_value"]) / out["reconciled_value"])
        default = valuation_summary(r, 0.055, 0.08, 10_000_000)
        assert set(default["weights"]) == {"direct_cap", "dcf"}


# ------------------------------------------------------------- financing
def test_compare_structures(simple_mf):
    structures = [
        {"name": "All cash", "loan": None},
        {"name": "Agency", "loan": {"ltv": 0.65, "interest_rate": 0.055, "amortization_years": 30}},
        {"name": "Bridge", "loan": {"ltv": 0.75, "loan_type": "bridge", "rate_type": "floating", "index_rate": 0.043,
                                    "spread": 0.03, "amortization_years": 0, "term_years": 3}},
        {"name": "Agency + Pref", "loan": {"ltv": 0.6, "interest_rate": 0.055},
         "preferred_equity": {"amount": 1_000_000, "pref_rate": 0.1}},
    ]
    out = compare_structures(simple_mf, structures)
    assert [o["name"] for o in out] == ["All cash", "Agency", "Bridge", "Agency + Pref"]
    assert out[0]["rate"] is None and out[0]["dscr_year1"] is None
    assert out[2]["rate"] == pytest.approx(0.073)
    assert out[1]["equity_invested"] < out[0]["equity_invested"]
    assert any(w["field"] == "loan.term_years" for w in out[2]["warnings"])
    assert out[3]["preferred_equity"] == 1_000_000


# ----------------------------------------------------------- development
class TestDevelopment:
    BASE = dict(land_cost=3_000_000, hard_costs=20_000_000, stabilized_noi=2_000_000, exit_cap_rate=0.055,
                construction_months=18, lease_up_months=12, loan_to_cost=0.6, construction_rate=0.08)

    def test_budget_and_returns(self):
        out = run_development(self.BASE)
        b = out["budget"]
        assert b["soft_costs"] == pytest.approx(4_000_000)
        assert b["contingency"] == pytest.approx(1_200_000)
        assert b["total_cost"] == pytest.approx(
            28_200_000 + b["interest_reserve"] + b["loan_fees"])
        assert b["interest_reserve"] > 0
        # Converged: the reserve equals interest actually accrued on the loan balance.
        assert out["capital"]["loan_balance_at_exit"] == pytest.approx(
            out["capital"]["construction_loan"], rel=1e-6)
        assert out["capital"]["construction_loan"] == pytest.approx(b["total_cost"] * 0.6)
        r = out["returns"]
        assert r["yield_on_cost"] == pytest.approx(2_000_000 / b["total_cost"])
        assert r["stabilized_value"] == pytest.approx(2_000_000 / 0.055)
        assert r["development_spread_bps"] == pytest.approx((r["yield_on_cost"] - 0.055) * 10_000)
        assert r["irr"] > 0 and r["equity_multiple"] > 1

    def test_no_lease_up_and_dataclass_input(self):
        out = run_development(DevelopmentAssumptions(**{**self.BASE, "lease_up_months": 0}))
        assert len(out["monthly_equity_cash_flows"]) == 19

    def test_unprofitable_project_irr_none(self):
        out = run_development({**self.BASE, "stabilized_noi": 1, "loan_to_cost": 0.0})
        assert out["returns"]["irr"] is None or out["returns"]["irr"] < 0

    @pytest.mark.parametrize(
        "patch",
        [{"hard_costs": 0}, {"construction_months": 0}, {"loan_to_cost": 0.95}, {"exit_cap_rate": 0},
         {"stabilized_noi": 0}],
    )
    def test_validation(self, patch):
        with pytest.raises(ValueError):
            run_development({**self.BASE, **patch})


# ------------------------------------------------------------------ risk
class TestRisk:
    def test_healthy_dscr_not_penalised(self, levered_mf):
        out = risk_assessment(run_underwriting(levered_mf), "multifamily")
        assert "dscr" not in {f["factor"] for f in out["factors"]}

    def test_conservative_deal_is_low_risk(self, simple_mf):
        out = risk_assessment(run_underwriting(simple_mf), "multifamily")
        assert out["level"] == "low"

    def test_aggressive_deal_is_high_risk(self, levered_mf):
        levered_mf.update(rent_growth=0.07, exit_cap_rate=0.045)
        levered_mf["expense_lines"] = [{"name": "Taxes", "amount_annual": 100_000}]
        levered_mf["loan"].update(ltv=0.8, interest_rate=0.085, io_years=0, term_years=3, min_dscr_covenant=1.5)
        out = risk_assessment(run_underwriting(levered_mf), "multifamily")
        keys = {f["factor"] for f in out["factors"]}
        assert {"leverage", "cap_compression", "rent_growth", "expense_ratio", "covenants", "refinance"} <= keys
        assert out["level"] == "high"

    def test_dscr_bands_and_negative_returns(self, levered_mf):
        levered_mf["loan"].update(ltv=0.79, interest_rate=0.12, io_years=0)
        out = risk_assessment(run_underwriting(levered_mf), "unknown_type")
        f = {x["factor"]: x for x in out["factors"]}
        assert f["dscr"]["points"] == 30
        assert "breakeven" in f
        levered_mf["loan"].update(ltv=0.70, interest_rate=0.068)
        f = {x["factor"]: x for x in risk_assessment(run_underwriting(levered_mf))["factors"]}
        assert f["dscr"]["points"] == 15

    def test_negative_returns_flagged(self, simple_mf):
        simple_mf.update(exit_cap_rate=0.2, vacancy_rate=0.5)
        out = risk_assessment(run_underwriting(simple_mf))
        assert "returns" in {f["factor"] for f in out["factors"]}
        assert out["level"] in ("moderate", "high")
