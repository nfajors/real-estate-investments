import pytest
from axiom_engine import AssumptionError, Assumptions, Loan, run_underwriting
from axiom_engine.assumptions import resolve_loan_amount


def fields_of(exc: AssumptionError) -> set[str]:
    return {e["field"] for e in exc.errors}


def expect_error(data: dict, field: str) -> None:
    with pytest.raises(AssumptionError) as ei:
        Assumptions.from_dict(data).validate()
    assert field in fields_of(ei.value), ei.value.errors


class TestParsing:
    def test_unknown_top_level(self, simple_mf):
        simple_mf["bogus"] = 1
        with pytest.raises(AssumptionError) as ei:
            Assumptions.from_dict(simple_mf)
        assert fields_of(ei.value) == {"bogus"}

    def test_missing_price(self):
        with pytest.raises(AssumptionError):
            Assumptions.from_dict({"hold_period_years": 5})

    def test_nested_unknown_field(self, simple_mf):
        simple_mf["unit_mix"][0]["color"] = "blue"
        with pytest.raises(AssumptionError) as ei:
            Assumptions.from_dict(simple_mf)
        assert "unit_mix.color" in fields_of(ei.value)

    def test_nested_not_object(self, simple_mf):
        simple_mf["loan"] = "big"
        with pytest.raises(AssumptionError):
            Assumptions.from_dict(simple_mf)

    def test_nested_missing_required(self, simple_mf):
        simple_mf["unit_mix"] = [{"name": "x"}]
        with pytest.raises(AssumptionError):
            Assumptions.from_dict(simple_mf)

    def test_accepts_dataclass_instances(self, simple_mf):
        simple_mf["loan"] = Loan(amount=1_000_000, interest_rate=0.05)
        a = Assumptions.from_dict(simple_mf)
        assert a.loan.amount == 1_000_000

    def test_preferred_equity_parsed(self, simple_mf):
        simple_mf["preferred_equity"] = {"amount": 10, "pref_rate": 0.1}
        assert Assumptions.from_dict(simple_mf).preferred_equity.amount == 10

    def test_round_trip(self, levered_mf):
        a = Assumptions.from_dict(levered_mf)
        assert Assumptions.from_dict(a.to_dict()).to_dict() == a.to_dict()


class TestValidation:
    @pytest.mark.parametrize(
        "patch,field",
        [
            ({"purchase_price": 0}, "purchase_price"),
            ({"hold_period_years": 0}, "hold_period_years"),
            ({"hold_period_years": -3}, "hold_period_years"),
            ({"hold_period_years": 2.5}, "hold_period_years"),
            ({"revenue_mode": "magic"}, "revenue_mode"),
            ({"opex_mode": "magic"}, "opex_mode"),
            ({"vacancy_rate": 1.2}, "vacancy_rate"),
            ({"vacancy_rate": 0.6, "credit_loss_rate": 0.5}, "vacancy_rate"),
            ({"rent_growth": 1.5}, "rent_growth"),
            ({"rent_growth_by_year": [0.02, 2.0]}, "rent_growth_by_year"),
            ({"exit_cap_rate": 0}, "exit_cap_rate"),
            ({"discount_rate": 1.5}, "discount_rate"),
            ({"upfront_capex": -1}, "capex"),
            ({"other_income": -1}, "other_income"),
            ({"unit_mix": []}, "unit_mix"),
            ({"unit_mix": [{"name": "a", "units": -1, "in_place_rent_monthly": 100}]}, "unit_mix[0]"),
            ({"expense_lines": [{"name": "a", "amount_annual": -1}]}, "expense_lines[0]"),
            ({"opex_mode": "ratio", "opex_ratio": 1.5}, "opex_ratio"),
            ({"revenue_mode": "per_sf"}, "rentable_sf"),
            ({"revenue_mode": "per_sf", "rentable_sf": 100, "rent_psf_annual": -2}, "rent_psf_annual"),
            ({"revenue_mode": "lump_sum", "gross_potential_rent": -5}, "gross_potential_rent"),
            ({"preferred_equity": {"amount": -1}}, "preferred_equity"),
        ],
    )
    def test_rejects_impossible_inputs(self, simple_mf, patch, field):
        simple_mf.update(patch)
        expect_error(simple_mf, field)

    @pytest.mark.parametrize(
        "loan_patch,field",
        [
            ({"loan_type": "magic"}, "loan.loan_type"),
            ({"rate_type": "magic"}, "loan.rate_type"),
            ({"ltv": None}, "loan.amount"),
            ({"ltv": None, "amount": -5}, "loan.amount"),
            ({"ltv": 1.2}, "loan.ltv"),
            ({"ltv": None, "amount": 20_000_000}, "loan.amount"),
            ({"interest_rate": 0.9}, "loan.interest_rate"),
            ({"amortization_years": 50}, "loan.amortization_years"),
            ({"term_years": 0}, "loan.term_years"),
            ({"io_years": 20}, "loan.io_years"),
            ({"origination_fee_pct": 0.5}, "loan.fees"),
        ],
    )
    def test_rejects_invalid_loans(self, levered_mf, loan_patch, field):
        levered_mf["loan"].update(loan_patch)
        expect_error(levered_mf, field)

    def test_valid_inputs_return_no_errors(self, levered_mf):
        assert isinstance(Assumptions.from_dict(levered_mf).validate(), list)

    def test_error_message_text(self, simple_mf):
        simple_mf["purchase_price"] = -1
        with pytest.raises(AssumptionError, match="purchase_price"):
            run_underwriting(simple_mf)


class TestWarnings:
    def flags(self, data):
        return {w["field"] for w in Assumptions.from_dict(data).warnings()}

    def test_base_case_is_clean(self, levered_mf):
        assert self.flags(levered_mf) == set()

    def test_extreme_assumptions_flagged(self, levered_mf):
        levered_mf.update(rent_growth=0.09, vacancy_rate=0.30, exit_cap_rate=0.03, opex_growth=0.02)
        levered_mf["loan"].update(ltv=0.85, term_years=3)
        assert self.flags(levered_mf) == {"rent_growth", "vacancy_rate", "exit_cap_rate", "opex_growth", "loan",
                                          "loan.term_years"}

    def test_growth_schedule_flagged(self, simple_mf):
        simple_mf["rent_growth_by_year"] = [0.12]
        assert "rent_growth" in self.flags(simple_mf)

    def test_tight_vacancy_flagged(self, simple_mf):
        simple_mf["vacancy_rate"] = 0.01
        assert "vacancy_rate" in self.flags(simple_mf)


def test_resolve_loan_amount():
    assert resolve_loan_amount(Loan(amount=5.0), 100) == 5.0
    assert resolve_loan_amount(Loan(ltv=0.5), 100) == 50.0
    assert resolve_loan_amount(Loan(), 100) == 0.0
