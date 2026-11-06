import numpy_financial as npf
import pytest
from axiom_engine.tvm import discount_factors, irr, npv, pmt, remaining_balance, safe_div


class TestNPV:
    def test_matches_hand_calculation(self):
        # -100 + 60/1.1 + 60/1.21
        assert npv(0.10, [-100, 60, 60]) == pytest.approx(-100 + 54.545454545 + 49.586776859, abs=1e-6)

    def test_matches_numpy_financial(self):
        flows = [-1_000_000, 80_000, 82_000, 85_000, 1_300_000]
        assert npv(0.075, flows) == pytest.approx(npf.npv(0.075, flows), rel=1e-12)

    def test_zero_rate_is_sum(self):
        assert npv(0.0, [-5, 2, 4]) == 1

    def test_invalid_rate(self):
        with pytest.raises(ValueError):
            npv(-1.0, [1, 2])

    def test_discount_factors(self):
        assert discount_factors(0.1, 3) == pytest.approx([1.0, 1 / 1.1, 1 / 1.21])
        with pytest.raises(ValueError):
            discount_factors(-1.5, 2)


class TestIRR:
    @pytest.mark.parametrize(
        "flows",
        [
            [-100, 110],
            [-1_000_000, 60_000, 62_000, 64_000, 66_000, 1_250_000],
            [-500, 100, 100, 100, 100, 100, 100],
            [-100, -50, 30, 80, 120],
            [-1000, 10, 10, 10, 10],  # negative IRR
        ],
    )
    def test_matches_numpy_financial(self, flows):
        assert irr(flows) == pytest.approx(npf.irr(flows), abs=1e-8)

    def test_simple_exact(self):
        assert irr([-100, 110]) == pytest.approx(0.10, abs=1e-10)

    def test_npv_at_irr_is_zero(self):
        flows = [-2_500_000, 150_000, 155_000, 160_000, 3_100_000]
        assert npv(irr(flows), flows) == pytest.approx(0.0, abs=1e-4)

    def test_no_sign_change_returns_none(self):
        assert irr([100, 100]) is None
        assert irr([-100, -100]) is None

    def test_exact_grid_root(self):
        # IRR of exactly 0% lands on a grid point.
        assert irr([-100, 100]) == pytest.approx(0.0, abs=1e-9)

    def test_root_at_upper_grid_end(self):
        # -1 + 101/(1+100) = 0 → IRR exactly 100 (10,000%)
        assert irr([-1, 101]) == pytest.approx(100.0)

    def test_no_root_in_search_range(self):
        # IRR would be 200x – outside the searchable range.
        assert irr([-1, 1000]) is None

    def test_multiple_roots_closest_to_guess(self):
        # Roots at 10% and 20%: (1+r)^2 - 2.3(1+r) + 1.32 = 0
        flows = [-1, 2.3, -1.32]
        assert irr(flows, guess=0.09) == pytest.approx(0.10, abs=1e-8)
        assert irr(flows, guess=0.25) == pytest.approx(0.20, abs=1e-8)

    def test_long_monthly_series(self):
        flows = [-1000.0] + [12.0] * 119 + [1012.0]
        assert irr(flows, guess=0.01) == pytest.approx(npf.irr(flows), abs=1e-9)


class TestPMT:
    def test_matches_numpy_financial(self):
        # 30-year mortgage, 6% annual, monthly payments
        assert pmt(0.06 / 12, 360, 6_500_000) == pytest.approx(-npf.pmt(0.06 / 12, 360, 6_500_000), rel=1e-12)

    def test_zero_rate(self):
        assert pmt(0.0, 10, 1000) == 100

    def test_invalid_periods(self):
        with pytest.raises(ValueError):
            pmt(0.01, 0, 100)


class TestRemainingBalance:
    def test_matches_numpy_financial(self):
        rate, n, pv, k = 0.06 / 12, 360, 1_000_000, 60
        expected = -npf.fv(rate, k, -pmt(rate, n, pv), pv)
        assert remaining_balance(rate, n, pv, k) == pytest.approx(expected, rel=1e-10)

    def test_fully_paid(self):
        assert remaining_balance(0.01, 12, 1000, 12) == 0.0

    def test_zero_rate(self):
        assert remaining_balance(0.0, 10, 1000, 4) == pytest.approx(600)


def test_safe_div():
    assert safe_div(1, 2) == 0.5
    assert safe_div(1, 0) is None
    assert safe_div(1, float("nan")) is None
