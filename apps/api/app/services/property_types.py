"""Property-type catalogue: type-specific fields and default assumptions (PRD 4.11).

Defaults are generic starting points for a new model, not market data; every
value is editable and labelled as a default in the UI.
"""

from __future__ import annotations

import copy
from typing import Any

FieldDef = dict[str, Any]

PROPERTY_TYPES: dict[str, dict[str, Any]] = {
    "multifamily": {
        "label": "Multifamily",
        "revenue_mode": "unit_mix",
        "fields": [
            {"key": "avg_unit_sf", "label": "Average unit size (SF)", "type": "number"},
            {"key": "parking_spaces", "label": "Parking spaces", "type": "number"},
            {"key": "class", "label": "Asset class", "type": "select", "options": ["A", "B", "C"]},
            {"key": "amenities", "label": "Key amenities", "type": "text"},
        ],
        "defaults": {"vacancy_rate": 0.05, "credit_loss_rate": 0.01, "rent_growth": 0.03, "opex_growth": 0.03,
                     "management_fee_pct": 0.03, "exit_cap_rate": 0.0575, "discount_rate": 0.08,
                     "capex_reserve_per_unit": 300},
    },
    "industrial": {
        "label": "Industrial",
        "revenue_mode": "per_sf",
        "fields": [
            {"key": "clear_height_ft", "label": "Clear height (ft)", "type": "number"},
            {"key": "loading_docks", "label": "Dock-high doors", "type": "number"},
            {"key": "drive_in_doors", "label": "Drive-in doors", "type": "number"},
            {"key": "office_finish_pct", "label": "Office finish (%)", "type": "percent"},
            {"key": "walt_years", "label": "WALT (years)", "type": "number"},
            {"key": "lease_type", "label": "Lease structure", "type": "select", "options": ["NNN", "Modified Gross", "Gross"]},
        ],
        "defaults": {"vacancy_rate": 0.05, "credit_loss_rate": 0.005, "rent_growth": 0.035, "opex_growth": 0.025,
                     "management_fee_pct": 0.02, "exit_cap_rate": 0.06, "discount_rate": 0.075,
                     "capex_reserve_psf": 0.15},
    },
    "office": {
        "label": "Office",
        "revenue_mode": "per_sf",
        "fields": [
            {"key": "class", "label": "Building class", "type": "select", "options": ["A", "B", "C"]},
            {"key": "floors", "label": "Floors", "type": "number"},
            {"key": "walt_years", "label": "WALT (years)", "type": "number"},
            {"key": "parking_ratio", "label": "Parking ratio (/1,000 SF)", "type": "number"},
        ],
        "defaults": {"vacancy_rate": 0.12, "credit_loss_rate": 0.01, "rent_growth": 0.02, "opex_growth": 0.03,
                     "management_fee_pct": 0.03, "exit_cap_rate": 0.0775, "discount_rate": 0.095,
                     "capex_reserve_psf": 0.50},
    },
    "retail": {
        "label": "Retail",
        "revenue_mode": "per_sf",
        "fields": [
            {"key": "anchor_tenants", "label": "Anchor tenants", "type": "text"},
            {"key": "walt_years", "label": "WALT (years)", "type": "number"},
            {"key": "sales_psf", "label": "Tenant sales ($/SF)", "type": "number"},
            {"key": "center_type", "label": "Center type", "type": "select",
             "options": ["Strip", "Neighborhood", "Community", "Power", "Single tenant"]},
        ],
        "defaults": {"vacancy_rate": 0.07, "credit_loss_rate": 0.01, "rent_growth": 0.025, "opex_growth": 0.025,
                     "management_fee_pct": 0.035, "exit_cap_rate": 0.07, "discount_rate": 0.085,
                     "capex_reserve_psf": 0.25},
    },
    "mixed_use": {
        "label": "Mixed-Use",
        "revenue_mode": "lump_sum",
        "fields": [
            {"key": "residential_units", "label": "Residential units", "type": "number"},
            {"key": "commercial_sf", "label": "Commercial SF", "type": "number"},
            {"key": "residential_share_pct", "label": "Residential share of revenue (%)", "type": "percent"},
        ],
        "defaults": {"vacancy_rate": 0.07, "credit_loss_rate": 0.01, "rent_growth": 0.03, "opex_growth": 0.03,
                     "management_fee_pct": 0.03, "exit_cap_rate": 0.0625, "discount_rate": 0.085},
    },
    "hospitality": {
        "label": "Hospitality",
        "revenue_mode": "lump_sum",
        "fields": [
            {"key": "keys", "label": "Keys", "type": "number"},
            {"key": "adr", "label": "ADR ($)", "type": "number"},
            {"key": "occupancy_pct", "label": "Occupancy (%)", "type": "percent"},
            {"key": "brand", "label": "Brand / flag", "type": "text"},
            {"key": "service_level", "label": "Service level", "type": "select",
             "options": ["Select service", "Full service", "Extended stay", "Luxury"]},
        ],
        "defaults": {"vacancy_rate": 0.0, "credit_loss_rate": 0.0, "rent_growth": 0.03, "opex_growth": 0.035,
                     "management_fee_pct": 0.03, "exit_cap_rate": 0.08, "discount_rate": 0.10,
                     "opex_mode": "ratio", "opex_ratio": 0.68},
    },
    "self_storage": {
        "label": "Self-Storage",
        "revenue_mode": "unit_mix",
        "fields": [
            {"key": "net_rentable_sf", "label": "Net rentable SF", "type": "number"},
            {"key": "climate_controlled_pct", "label": "Climate controlled (%)", "type": "percent"},
        ],
        "defaults": {"vacancy_rate": 0.10, "credit_loss_rate": 0.01, "rent_growth": 0.035, "opex_growth": 0.03,
                     "management_fee_pct": 0.06, "exit_cap_rate": 0.06, "discount_rate": 0.085},
    },
    "student_housing": {
        "label": "Student Housing",
        "revenue_mode": "unit_mix",
        "fields": [
            {"key": "beds", "label": "Beds", "type": "number"},
            {"key": "university", "label": "University", "type": "text"},
            {"key": "distance_to_campus_mi", "label": "Distance to campus (mi)", "type": "number"},
        ],
        "defaults": {"vacancy_rate": 0.06, "credit_loss_rate": 0.015, "rent_growth": 0.03, "opex_growth": 0.03,
                     "management_fee_pct": 0.035, "exit_cap_rate": 0.0625, "discount_rate": 0.085},
    },
    "land": {
        "label": "Development Land",
        "revenue_mode": "lump_sum",
        "fields": [
            {"key": "acres", "label": "Acres", "type": "number"},
            {"key": "zoning", "label": "Zoning", "type": "text"},
            {"key": "entitled_units", "label": "Entitled units / SF", "type": "number"},
            {"key": "entitlement_status", "label": "Entitlement status", "type": "select",
             "options": ["Raw", "In process", "Entitled", "Shovel ready"]},
        ],
        "defaults": {"vacancy_rate": 0.05, "credit_loss_rate": 0.0, "rent_growth": 0.03, "opex_growth": 0.03,
                     "management_fee_pct": 0.0, "exit_cap_rate": 0.06, "discount_rate": 0.11},
    },
}


def catalogue() -> list[dict[str, Any]]:
    return [{"key": k, **{kk: vv for kk, vv in v.items()}} for k, v in PROPERTY_TYPES.items()]


def default_assumptions(
    property_type: str,
    purchase_price: float,
    hold_period_years: int = 10,
    units: int | None = None,
    rentable_sf: float | None = None,
) -> dict[str, Any]:
    """Starter assumption set for a new deal (clearly a template, to be overwritten by verified data)."""
    meta = PROPERTY_TYPES[property_type]
    d = copy.deepcopy(meta["defaults"])
    capex_per_unit = d.pop("capex_reserve_per_unit", None)
    capex_psf = d.pop("capex_reserve_psf", None)
    opex_mode = d.pop("opex_mode", "line_items")
    opex_ratio = d.pop("opex_ratio", 0.40)
    out: dict[str, Any] = {
        "purchase_price": purchase_price,
        "hold_period_years": hold_period_years,
        "closing_costs_pct": 0.02,
        "upfront_capex": 0.0,
        "units": units,
        "rentable_sf": rentable_sf,
        "revenue_mode": meta["revenue_mode"],
        "unit_mix": [],
        "rent_psf_annual": 0.0,
        "gross_potential_rent": 0.0,
        "other_income": 0.0,
        "other_income_growth": 0.02,
        "opex_mode": opex_mode,
        "opex_ratio": opex_ratio,
        "expense_lines": [],
        "capex_reserve_annual": (capex_per_unit or 0) * (units or 0) + (capex_psf or 0) * (rentable_sf or 0),
        "capex_growth": 0.025,
        "selling_costs_pct": 0.02,
        "loan": None,
        "preferred_equity": None,
        **d,
    }
    # Starting revenue so a fresh model computes; replaced once documents are verified.
    implied_noi = purchase_price * out["exit_cap_rate"]
    if meta["revenue_mode"] == "unit_mix":
        n = units or 100
        rent = implied_noi / 0.55 / (1 - out["vacancy_rate"]) / 12 / n
        out["unit_mix"] = [{"name": "Average unit", "units": n, "in_place_rent_monthly": round(rent, 2),
                            "market_rent_monthly": round(rent, 2)}]
        out["units"] = n
    elif meta["revenue_mode"] == "per_sf":
        sf = rentable_sf or 100_000.0
        out["rentable_sf"] = sf
        out["rent_psf_annual"] = round(implied_noi / 0.80 / (1 - out["vacancy_rate"]) / sf, 2)
    else:
        out["gross_potential_rent"] = round(implied_noi / 0.55, 2)
    if opex_mode == "line_items":
        egi_guess = implied_noi / (0.80 if meta["revenue_mode"] == "per_sf" else 0.55)
        opex_total = egi_guess - implied_noi - egi_guess * out["management_fee_pct"]
        out["expense_lines"] = [
            {"name": "Real estate taxes", "amount_annual": round(opex_total * 0.40, 2)},
            {"name": "Insurance", "amount_annual": round(opex_total * 0.15, 2)},
            {"name": "Repairs & maintenance", "amount_annual": round(opex_total * 0.20, 2)},
            {"name": "Utilities", "amount_annual": round(opex_total * 0.15, 2)},
            {"name": "General & administrative", "amount_annual": round(opex_total * 0.10, 2)},
        ]
    return out
