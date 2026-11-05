"""Glue between persisted scenarios and the pure financial engine."""

from __future__ import annotations

import logging
from typing import Any

from axiom_engine import AssumptionError, run_underwriting
from axiom_engine.risk import risk_assessment
from fastapi import HTTPException
from sqlalchemy import select

from ..deps import OrgContext
from ..models import Property, Scenario, UnderwritingResult

log = logging.getLogger("axiom.underwriting")


def engine_error(exc: AssumptionError) -> HTTPException:
    return HTTPException(422, {"message": "Invalid assumptions", "errors": exc.errors})


def calculate(assumptions: dict[str, Any], property_type: str) -> dict[str, Any]:
    """Run the engine and attach a risk assessment. Raises HTTP 422 on invalid input."""
    try:
        result = run_underwriting(assumptions)
    except AssumptionError as exc:
        raise engine_error(exc) from exc
    data = result.to_dict()
    data["risk"] = risk_assessment(result, property_type)
    return data


def get_scenario(ctx: OrgContext, prop: Property, scenario_id=None) -> Scenario:
    q = select(Scenario).where(Scenario.property_id == prop.id, Scenario.org_id == ctx.org.id,
                               Scenario.deleted_at.is_(None))
    if scenario_id:
        q = q.where(Scenario.id == scenario_id)
    else:
        q = q.order_by(Scenario.is_base.desc(), Scenario.created_at)
    sc = ctx.db.scalars(q).first()
    if sc is None:
        raise HTTPException(404, "Scenario not found")
    return sc


def run_and_store(ctx: OrgContext, prop: Property, scenario: Scenario) -> UnderwritingResult:
    """Run the engine and persist an immutable snapshot (inputs + outputs) for audit."""
    data = calculate(scenario.assumptions_json, prop.property_type)
    m = data["metrics"]
    row = UnderwritingResult(
        org_id=ctx.org.id,
        property_id=prop.id,
        scenario_id=scenario.id,
        calculated_by=ctx.user.id,
        engine_version=data["engine_version"],
        noi_year1=m["noi_year1"],
        cap_rate=m["going_in_cap_rate"],
        irr_unlevered=m["irr_unlevered"],
        irr_levered=m["irr_levered"],
        npv=m["npv_levered"],
        equity_multiple=m["equity_multiple_levered"],
        cash_on_cash=m["cash_on_cash_year1"],
        dscr=m["dscr_year1"],
        ltv=m["ltv"],
        risk_score=data["risk"]["score"],
        assumptions_snapshot=scenario.assumptions_json,
        full_cashflow_json=data,
    )
    ctx.db.add(row)
    ctx.db.flush()
    ctx.audit("underwriting.run", "underwriting_result", row.id, property_id=prop.id, scenario_id=str(scenario.id),
              scenario=scenario.name, engine_version=row.engine_version, calc_ms=round(data["calc_ms"], 2),
              irr_levered=row.irr_levered, noi_year1=row.noi_year1)
    log.info("underwriting.run property=%s scenario=%s calc_ms=%.2f", prop.id, scenario.id, data["calc_ms"])
    return row


def latest_result(ctx: OrgContext, prop: Property, scenario: Scenario | None = None) -> UnderwritingResult | None:
    q = select(UnderwritingResult).where(UnderwritingResult.property_id == prop.id,
                                         UnderwritingResult.org_id == ctx.org.id)
    if scenario is not None:
        q = q.where(UnderwritingResult.scenario_id == scenario.id)
    return ctx.db.scalars(q.order_by(UnderwritingResult.calculated_at.desc())).first()


def ensure_result(ctx: OrgContext, prop: Property, scenario: Scenario) -> UnderwritingResult:
    """Latest result for the scenario, recomputed if assumptions changed since it was stored."""
    row = latest_result(ctx, prop, scenario)
    if row is None or row.assumptions_snapshot != scenario.assumptions_json:
        row = run_and_store(ctx, prop, scenario)
        ctx.db.commit()
    return row


def headline(row: UnderwritingResult | None) -> dict[str, Any] | None:
    if row is None:
        return None
    m = row.full_cashflow_json["metrics"]
    return {
        "result_id": str(row.id),
        "scenario_id": str(row.scenario_id),
        "calculated_at": row.calculated_at.isoformat(),
        "noi_year1": row.noi_year1,
        "cap_rate": row.cap_rate,
        "irr_levered": row.irr_levered,
        "irr_unlevered": row.irr_unlevered,
        "npv": row.npv,
        "equity_multiple": row.equity_multiple,
        "cash_on_cash": row.cash_on_cash,
        "dscr": row.dscr,
        "ltv": row.ltv,
        "risk_score": row.risk_score,
        "risk_level": row.full_cashflow_json.get("risk", {}).get("level"),
        "price_per_unit": m.get("price_per_unit"),
        "price_per_sf": m.get("price_per_sf"),
        "equity_invested": m.get("equity_invested"),
        "exit_value": row.full_cashflow_json["exit"]["gross_sale_price"],
    }


def sync_property_to_scenarios(ctx: OrgContext, prop: Property, changed: dict[str, Any]) -> None:
    """Keep deal-level facts (price, hold, size) consistent across all scenarios."""
    mapping = {"purchase_price": "purchase_price", "hold_period_years": "hold_period_years", "units": "units",
               "rentable_sf": "rentable_sf"}
    updates = {mapping[k]: v for k, v in changed.items() if k in mapping and v is not None}
    if not updates:
        return
    for sc in ctx.db.scalars(select(Scenario).where(Scenario.property_id == prop.id, Scenario.deleted_at.is_(None))):
        a = dict(sc.assumptions_json)
        a.update(updates)
        sc.assumptions_json = a
