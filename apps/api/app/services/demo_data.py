"""Clearly-labelled, fictional demo portfolio (PRD §12).

Every demo property has ``is_demo=True`` and a "[DEMO]" name prefix; all exports
of demo deals carry a "For Demonstration Purposes Only" watermark.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import date
from typing import Any

from axiom_engine.scenarios import DEFAULT_SCENARIO_SHIFTS, shift_assumptions
from sqlalchemy.orm import Session

from ..deps import OrgContext
from ..models import Document, FinancingStructure, Organization, Property, Scenario, User
from .demo_docs import UNIT_TYPES, offering_memorandum_pdf, rent_roll_workbook
from .storage import get_storage
from .underwriting import run_and_store

DEMO_PREFIX = "[DEMO] "

HARBOR_POINT: dict[str, Any] = {
    "property": dict(name="Harbor Point Residences", property_type="multifamily", address="1200 Harbor Point Drive",
                     city="Charlotte", state="NC", zip_code="28203", status="underwriting", purchase_price=58_500_000,
                     hold_period_years=7, units=240, rentable_sf=222_080, year_built=2016,
                     acquisition_date=date(2027, 3, 31),
                     description="Fictional 240-unit Class A garden community used to demonstrate Axiom.",
                     attributes={"class": "A", "avg_unit_sf": 925, "parking_spaces": 410,
                                 "amenities": "Resort pool, fitness center, structured parking"}),
    "assumptions": {
        "purchase_price": 58_500_000, "hold_period_years": 7, "closing_costs_pct": 0.015, "upfront_capex": 1_200_000,
        "units": 240, "rentable_sf": 222_080, "revenue_mode": "unit_mix",
        "unit_mix": [{"name": n, "units": c, "in_place_rent_monthly": r, "market_rent_monthly": m, "sf_per_unit": sf}
                     for n, c, sf, r, m in UNIT_TYPES],
        "other_income": 318_000, "rent_growth": 0.035, "rent_growth_by_year": [0.045, 0.04],
        "other_income_growth": 0.025, "vacancy_rate": 0.05, "credit_loss_rate": 0.01, "opex_mode": "line_items",
        "expense_lines": [
            {"name": "Real estate taxes", "amount_annual": 612_000, "growth": 0.035},
            {"name": "Insurance", "amount_annual": 168_000, "growth": 0.05},
            {"name": "Utilities", "amount_annual": 254_400},
            {"name": "Repairs & maintenance", "amount_annual": 216_000},
            {"name": "Payroll", "amount_annual": 408_000},
            {"name": "General & administrative", "amount_annual": 72_000},
            {"name": "Marketing", "amount_annual": 38_400},
            {"name": "Contract services", "amount_annual": 96_000},
        ],
        "management_fee_pct": 0.03, "opex_growth": 0.03, "capex_reserve_annual": 72_000, "capex_growth": 0.025,
        "exit_cap_rate": 0.0575, "selling_costs_pct": 0.015, "discount_rate": 0.085,
        "loan": {"name": "Agency 10-yr fixed", "loan_type": "permanent", "rate_type": "fixed", "amount": 38_000_000,
                 "interest_rate": 0.0545, "amortization_years": 30, "term_years": 10, "io_years": 3,
                 "origination_fee_pct": 0.01, "min_dscr_covenant": 1.25},
    },
    "financing": [
        dict(name="Agency 10-yr fixed", type="permanent", rate_type="fixed", loan_amount=38_000_000,
             interest_rate=0.0545, term_years=10, amortization_years=30, io_period=3,
             fees={"origination_fee_pct": 0.01}, covenants={"min_dscr": 1.25}, is_active=True),
        dict(name="Bridge (SOFR + 325)", type="bridge", rate_type="floating", ltv=0.72, index_rate=0.0405,
             spread=0.0325, term_years=3, amortization_years=0, io_period=3,
             fees={"origination_fee_pct": 0.0125, "exit_fee_pct": 0.005}, covenants={"min_dscr": 1.10}),
        dict(name="Agency + 10% pref equity", type="permanent", rate_type="fixed", ltv=0.60, interest_rate=0.0535,
             term_years=10, amortization_years=30, io_period=5, fees={"origination_fee_pct": 0.01},
             covenants={"min_dscr": 1.25},
             preferred_equity={"amount": 5_850_000, "pref_rate": 0.10, "accrual_rate": 0.02}),
    ],
    "valuation": {
        "market_cap_rate": 0.0575,
        "comps": [
            {"name": "[DEMO] Southend Lofts (sold 2026)", "sale_price": 61_200_000, "units": 252, "adjustment_pct": 0.0,
             "weight": 1},
            {"name": "[DEMO] Lakeview Commons (sold 2026)", "sale_price": 47_300_000, "units": 204,
             "adjustment_pct": 0.03, "weight": 1},
            {"name": "[DEMO] Noda Flats (sold 2025)", "sale_price": 66_000_000, "units": 268, "adjustment_pct": -0.02,
             "weight": 0.5},
        ],
        "cost": {"land_value": 9_600_000, "replacement_cost": 54_000_000, "physical_depreciation_pct": 0.12},
        "weights": {"direct_cap": 0.35, "dcf": 0.35, "sales_comparison": 0.3, "cost": 0.0},
    },
}

GATEWAY: dict[str, Any] = {
    "property": dict(name="Gateway Logistics Center", property_type="industrial", address="4800 Distribution Pkwy",
                     city="Dallas", state="TX", zip_code="75241", status="ic", purchase_price=68_000_000,
                     hold_period_years=10, rentable_sf=412_000, year_built=2021,
                     description="Fictional two-building, rear-load distribution center used to demonstrate Axiom.",
                     attributes={"clear_height_ft": 36, "loading_docks": 68, "drive_in_doors": 4,
                                 "office_finish_pct": 0.05, "walt_years": 6.2, "lease_type": "NNN"}),
    "assumptions": {
        "purchase_price": 68_000_000, "hold_period_years": 10, "closing_costs_pct": 0.0125, "upfront_capex": 350_000,
        "rentable_sf": 412_000, "revenue_mode": "per_sf", "rent_psf_annual": 9.85, "other_income": 120_000,
        "rent_growth": 0.035, "other_income_growth": 0.02, "vacancy_rate": 0.05, "credit_loss_rate": 0.005,
        "opex_mode": "line_items",
        "expense_lines": [
            {"name": "Non-recoverable opex", "amount_annual": 145_000},
            {"name": "Structural reserve & repairs", "amount_annual": 82_400},
            {"name": "Insurance (unrecovered)", "amount_annual": 41_200, "growth": 0.045},
        ],
        "management_fee_pct": 0.015, "opex_growth": 0.03, "capex_reserve_annual": 61_800, "capex_growth": 0.025,
        "exit_cap_rate": 0.06, "selling_costs_pct": 0.015, "discount_rate": 0.0775,
        "loan": {"name": "Life Co 10-yr", "loan_type": "permanent", "rate_type": "fixed", "ltv": 0.55,
                 "interest_rate": 0.0565, "amortization_years": 30, "term_years": 10, "io_years": 2,
                 "origination_fee_pct": 0.005, "min_dscr_covenant": 1.35},
    },
    "financing": [
        dict(name="Life Co 10-yr", type="permanent", rate_type="fixed", ltv=0.55, interest_rate=0.0565, term_years=10,
             amortization_years=30, io_period=2, fees={"origination_fee_pct": 0.005}, covenants={"min_dscr": 1.35},
             is_active=True),
        dict(name="CMBS 10-yr full IO", type="interest_only", rate_type="fixed", ltv=0.62, interest_rate=0.0595,
             term_years=10, amortization_years=0, io_period=10, fees={"origination_fee_pct": 0.01},
             covenants={"min_dscr": 1.25}),
    ],
    "valuation": {
        "market_cap_rate": 0.0575,
        "comps": [
            {"name": "[DEMO] I-20 Commerce Park", "sale_price": 52_500_000, "sf": 318_000, "weight": 1},
            {"name": "[DEMO] Southport Crossdock", "sale_price": 41_800_000, "sf": 265_000, "adjustment_pct": 0.04,
             "weight": 1},
        ],
        "weights": {"direct_cap": 0.4, "dcf": 0.4, "sales_comparison": 0.2, "cost": 0.0},
    },
}

OTHERS: list[dict[str, Any]] = [
    {
        "property": dict(name="Meridian Office Plaza", property_type="office", city="Denver", state="CO",
                         status="passed", purchase_price=41_000_000, hold_period_years=7, rentable_sf=186_000,
                         year_built=1999, attributes={"class": "B", "floors": 9, "walt_years": 3.1}),
        "assumptions": {"purchase_price": 41_000_000, "hold_period_years": 7, "rentable_sf": 186_000,
                        "revenue_mode": "per_sf", "rent_psf_annual": 31.0, "vacancy_rate": 0.18,
                        "credit_loss_rate": 0.01, "rent_growth": 0.015, "opex_mode": "ratio", "opex_ratio": 0.42,
                        "management_fee_pct": 0.03, "opex_growth": 0.03, "capex_reserve_annual": 186_000,
                        "upfront_capex": 3_500_000, "exit_cap_rate": 0.0825, "discount_rate": 0.10,
                        "loan": {"ltv": 0.60, "interest_rate": 0.0675, "amortization_years": 25, "term_years": 5,
                                 "min_dscr_covenant": 1.30}},
    },
    {
        "property": dict(name="Oakridge Self Storage", property_type="self_storage", city="Phoenix", state="AZ",
                         status="closed", purchase_price=18_750_000, hold_period_years=7, units=780,
                         rentable_sf=98_500, year_built=2012, attributes={"climate_controlled_pct": 0.45}),
        "assumptions": {"purchase_price": 18_750_000, "hold_period_years": 7, "units": 780, "rentable_sf": 98_500,
                        "revenue_mode": "unit_mix",
                        "unit_mix": [{"name": "10x10", "units": 420, "in_place_rent_monthly": 145},
                                     {"name": "10x20 CC", "units": 360, "in_place_rent_monthly": 240}],
                        "other_income": 54_000, "vacancy_rate": 0.09, "credit_loss_rate": 0.01, "rent_growth": 0.035,
                        "opex_mode": "ratio", "opex_ratio": 0.30, "management_fee_pct": 0.06, "opex_growth": 0.03,
                        "capex_reserve_annual": 19_700, "exit_cap_rate": 0.06, "discount_rate": 0.085,
                        "loan": {"ltv": 0.60, "interest_rate": 0.0585, "amortization_years": 30, "term_years": 10,
                                 "io_years": 2}},
    },
    {
        "property": dict(name="Riverside Commons", property_type="retail", city="Atlanta", state="GA",
                         status="sourcing", purchase_price=26_400_000, hold_period_years=10, rentable_sf=142_000,
                         year_built=2004, attributes={"center_type": "Neighborhood", "anchor_tenants": "Grocer (fictional)",
                                                      "walt_years": 5.4}),
        "assumptions": {"purchase_price": 26_400_000, "hold_period_years": 10, "rentable_sf": 142_000,
                        "revenue_mode": "per_sf", "rent_psf_annual": 19.25, "other_income": 95_000,
                        "vacancy_rate": 0.07, "credit_loss_rate": 0.01, "rent_growth": 0.025, "opex_mode": "ratio",
                        "opex_ratio": 0.18, "management_fee_pct": 0.035, "opex_growth": 0.025,
                        "capex_reserve_annual": 35_500, "exit_cap_rate": 0.0725, "discount_rate": 0.085,
                        "loan": {"ltv": 0.60, "interest_rate": 0.061, "amortization_years": 30, "term_years": 10}},
    },
]


def _create(ctx: OrgContext, spec: dict[str, Any], with_scenarios: bool) -> Property:
    p = dict(spec["property"])
    p["name"] = DEMO_PREFIX + p["name"]
    prop = Property(org_id=ctx.org.id, is_demo=True, created_by=ctx.user.id, updated_by=ctx.user.id,
                    owner_id=ctx.user.id, valuation_inputs=spec.get("valuation", {}), **p)
    ctx.db.add(prop)
    ctx.db.flush()
    base_assumptions = {"closing_costs_pct": 0.02, "selling_costs_pct": 0.02, **spec["assumptions"]}
    base = Scenario(org_id=ctx.org.id, property_id=prop.id, name="Base Case", is_base=True,
                    description="Demo base case (fictional figures).", assumptions_json=base_assumptions,
                    created_by=ctx.user.id)
    ctx.db.add(base)
    ctx.db.flush()
    run_and_store(ctx, prop, base)
    if with_scenarios:
        for name, shifts in DEFAULT_SCENARIO_SHIFTS.items():
            sc = Scenario(org_id=ctx.org.id, property_id=prop.id, name=name,
                          description="Base case with " + ", ".join(f"{k} {v:+.2%}" for k, v in shifts.items()),
                          assumptions_json=shift_assumptions(base_assumptions, shifts), created_by=ctx.user.id)
            ctx.db.add(sc)
            ctx.db.flush()
            run_and_store(ctx, prop, sc)
    for f in spec.get("financing", []):
        ctx.db.add(FinancingStructure(org_id=ctx.org.id, property_id=prop.id, **f))
    ctx.audit("property.create", "property", prop.id, property_id=prop.id, name=prop.name, demo=True)
    return prop


def _attach_documents(ctx: OrgContext, prop: Property) -> list[uuid.UUID]:
    storage = get_storage()
    ids = []
    for name, mime, dtype, data in (
        ("Harbor-Point-OM-SAMPLE.pdf", "application/pdf", "om", offering_memorandum_pdf()),
        ("Harbor-Point-RentRoll-T12-SAMPLE.xlsx",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "rent_roll", rent_roll_workbook()),
    ):
        doc_id = uuid.uuid4()
        key = f"{ctx.org.id}/{prop.id}/{doc_id}"
        storage.put(key, data, mime)
        ctx.db.add(Document(id=doc_id, org_id=ctx.org.id, property_id=prop.id, name=name, type=dtype, mime_type=mime,
                            size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), file_url=key,
                            status="uploaded", uploaded_by=ctx.user.id))
        ids.append(doc_id)
    return ids


def seed_demo_portfolio(db: Session, org: Organization, user: User, process_documents: bool = True) -> None:
    ctx = OrgContext(user=user, org=org, role="owner", db=db)
    hp = _create(ctx, HARBOR_POINT, with_scenarios=True)
    _create(ctx, GATEWAY, with_scenarios=True)
    for spec in OTHERS:
        _create(ctx, spec, with_scenarios=False)
    doc_ids = _attach_documents(ctx, hp)
    db.commit()
    if process_documents:
        from .extraction import process_document

        for d in doc_ids:
            # Demo documents use the deterministic extractor so seeding never depends on AI availability.
            process_document(d, org.id, user.id, force_heuristic=True)
