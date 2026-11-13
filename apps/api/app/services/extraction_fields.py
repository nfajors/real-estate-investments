"""Catalogue of extraction targets and how verified values map into assumptions."""

from __future__ import annotations

from typing import Any

# kind: currency | percent | integer | number | years | text | unit_mix
FIELDS: dict[str, dict[str, Any]] = {
    "property.name": {"label": "Property name", "kind": "text", "group": "Property"},
    "property.address": {"label": "Street address", "kind": "text", "group": "Property"},
    "property.city": {"label": "City", "kind": "text", "group": "Property"},
    "property.state": {"label": "State", "kind": "text", "group": "Property"},
    "property.year_built": {"label": "Year built", "kind": "integer", "group": "Property"},
    "property.units": {"label": "Total units", "kind": "integer", "group": "Property"},
    "property.rentable_sf": {"label": "Rentable square feet", "kind": "number", "group": "Property"},
    "property.occupancy": {"label": "Occupancy", "kind": "percent", "group": "Property"},
    "deal.asking_price": {"label": "Asking / purchase price", "kind": "currency", "group": "Deal"},
    "revenue.unit_mix": {"label": "Unit mix (rent roll)", "kind": "unit_mix", "group": "Revenue"},
    "revenue.gross_potential_rent": {"label": "Gross potential rent", "kind": "currency", "group": "Revenue"},
    "revenue.rent_psf_annual": {"label": "Average rent ($/SF/yr)", "kind": "number", "group": "Revenue"},
    "revenue.other_income": {"label": "Other income", "kind": "currency", "group": "Revenue"},
    "revenue.vacancy_rate": {"label": "Vacancy rate", "kind": "percent", "group": "Revenue"},
    "expenses.real_estate_taxes": {"label": "Real estate taxes", "kind": "currency", "group": "Expenses"},
    "expenses.insurance": {"label": "Insurance", "kind": "currency", "group": "Expenses"},
    "expenses.utilities": {"label": "Utilities", "kind": "currency", "group": "Expenses"},
    "expenses.repairs_maintenance": {"label": "Repairs & maintenance", "kind": "currency", "group": "Expenses"},
    "expenses.payroll": {"label": "Payroll", "kind": "currency", "group": "Expenses"},
    "expenses.management_fee": {"label": "Management fee", "kind": "currency", "group": "Expenses"},
    "expenses.general_admin": {"label": "General & administrative", "kind": "currency", "group": "Expenses"},
    "expenses.marketing": {"label": "Marketing", "kind": "currency", "group": "Expenses"},
    "expenses.contract_services": {"label": "Contract services", "kind": "currency", "group": "Expenses"},
    "expenses.total_operating_expenses": {"label": "Total operating expenses", "kind": "currency",
                                          "group": "Expenses"},
    "historical.noi": {"label": "Historical NOI (T12)", "kind": "currency", "group": "Historical"},
    "debt.loan_amount": {"label": "Loan amount", "kind": "currency", "group": "Debt"},
    "debt.interest_rate": {"label": "Interest rate", "kind": "percent", "group": "Debt"},
    "debt.amortization_years": {"label": "Amortization (years)", "kind": "years", "group": "Debt"},
    "debt.term_years": {"label": "Loan term (years)", "kind": "years", "group": "Debt"},
    "debt.io_years": {"label": "Interest-only period (years)", "kind": "years", "group": "Debt"},
    "capex.upfront_capex": {"label": "Planned capital improvements", "kind": "currency", "group": "Capex"},
    "capex.reserve_per_unit": {"label": "Replacement reserve ($/unit/yr)", "kind": "currency", "group": "Capex"},
}

EXPENSE_LINE_NAMES = {
    "expenses.real_estate_taxes": "Real estate taxes",
    "expenses.insurance": "Insurance",
    "expenses.utilities": "Utilities",
    "expenses.repairs_maintenance": "Repairs & maintenance",
    "expenses.payroll": "Payroll",
    "expenses.management_fee": "Management fee",
    "expenses.general_admin": "General & administrative",
    "expenses.marketing": "Marketing",
    "expenses.contract_services": "Contract services",
}


def coerce(field_path: str, value: Any) -> Any:
    """Validate/coerce a (human-edited or extracted) value to the field's kind."""
    kind = FIELDS[field_path]["kind"]
    if value is None:
        return None
    if kind == "text":
        return str(value).strip()
    if kind == "unit_mix":
        if not isinstance(value, list):
            raise ValueError("Unit mix must be a list")
        out = []
        for u in value:
            out.append({
                "name": str(u.get("name") or "Unit"),
                "units": int(u["units"]),
                "in_place_rent_monthly": float(u["in_place_rent_monthly"]),
                "market_rent_monthly": float(u["market_rent_monthly"]) if u.get("market_rent_monthly") else None,
                "sf_per_unit": float(u["sf_per_unit"]) if u.get("sf_per_unit") else None,
            })
            if out[-1]["units"] < 0 or out[-1]["in_place_rent_monthly"] < 0:
                raise ValueError("Units and rents must be non-negative")
        return out
    num = float(str(value).replace(",", "").replace("$", "").replace("%", "")) if isinstance(value, str) else float(value)
    if kind == "percent":
        if isinstance(value, str) and "%" in value or num > 1:
            num = num / 100.0
        if not 0 <= num <= 1:
            raise ValueError("Percentage must be between 0% and 100%")
        return num
    if kind == "integer":
        return int(round(num))
    if num < 0:
        raise ValueError("Value cannot be negative")
    return num


def apply_to_assumptions(assumptions: dict[str, Any], accepted: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Merge verified values into an assumption set. Returns (new assumptions, change log)."""
    a = dict(assumptions)
    log: list[str] = []

    def setv(key: str, value: Any, why: str) -> None:
        a[key] = value
        log.append(f"{key} ← {why}")

    if "deal.asking_price" in accepted:
        setv("purchase_price", accepted["deal.asking_price"], "verified asking price")
    if "property.units" in accepted:
        setv("units", accepted["property.units"], "verified unit count")
    if "property.rentable_sf" in accepted:
        setv("rentable_sf", accepted["property.rentable_sf"], "verified rentable SF")
    if "revenue.unit_mix" in accepted and accepted["revenue.unit_mix"]:
        setv("unit_mix", accepted["revenue.unit_mix"], "verified rent roll")
        a["revenue_mode"] = "unit_mix"
    elif "revenue.rent_psf_annual" in accepted and a.get("rentable_sf"):
        setv("rent_psf_annual", accepted["revenue.rent_psf_annual"], "verified rent per SF")
        a["revenue_mode"] = "per_sf"
    elif "revenue.gross_potential_rent" in accepted:
        setv("gross_potential_rent", accepted["revenue.gross_potential_rent"], "verified GPR")
        a["revenue_mode"] = "lump_sum"
    if "revenue.other_income" in accepted:
        setv("other_income", accepted["revenue.other_income"], "verified other income")
    if "revenue.vacancy_rate" in accepted:
        setv("vacancy_rate", accepted["revenue.vacancy_rate"], "verified vacancy rate")
    elif "property.occupancy" in accepted:
        setv("vacancy_rate", round(1.0 - accepted["property.occupancy"], 6), "1 − verified occupancy")

    lines = [{"name": EXPENSE_LINE_NAMES[k], "amount_annual": v} for k, v in accepted.items()
             if k in EXPENSE_LINE_NAMES and v is not None]
    if lines:
        setv("expense_lines", lines, f"{len(lines)} verified expense line items")
        a["opex_mode"] = "line_items"
        if "expenses.management_fee" in accepted:
            a["management_fee_pct"] = 0.0  # fee captured as a verified line item
    elif "expenses.total_operating_expenses" in accepted:
        setv("expense_lines", [{"name": "Total operating expenses (T12)",
                                "amount_annual": accepted["expenses.total_operating_expenses"]}],
             "verified total operating expenses")
        a["opex_mode"] = "line_items"
        a["management_fee_pct"] = 0.0

    if "capex.upfront_capex" in accepted:
        setv("upfront_capex", accepted["capex.upfront_capex"], "verified capital plan")
    if "capex.reserve_per_unit" in accepted and a.get("units"):
        setv("capex_reserve_annual", accepted["capex.reserve_per_unit"] * a["units"], "reserve/unit × units")

    debt_keys = {"debt.loan_amount": "amount", "debt.interest_rate": "interest_rate",
                 "debt.amortization_years": "amortization_years", "debt.term_years": "term_years",
                 "debt.io_years": "io_years"}
    if any(k in accepted for k in debt_keys):
        loan = dict(a.get("loan") or {"name": "Senior Loan (from documents)", "loan_type": "permanent",
                                      "rate_type": "fixed", "amortization_years": 30, "term_years": 10})
        for k, lk in debt_keys.items():
            if k in accepted:
                v = accepted[k]
                loan[lk] = int(round(v)) if lk in ("amortization_years", "term_years") else v
        if "amount" in loan and loan.get("amount") is not None:
            loan["ltv"] = None
        setv("loan", loan, "verified debt terms")
    return a, log
