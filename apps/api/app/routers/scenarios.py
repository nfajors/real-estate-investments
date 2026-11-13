"""Scenarios (assumption sets) and stored underwriting results."""

from __future__ import annotations

import copy
import uuid

from axiom_engine import AssumptionError, Assumptions
from axiom_engine.scenarios import DEFAULT_SCENARIO_SHIFTS, shift_assumptions
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from ..deps import OrgContext, analyst, viewer
from ..features import require_feature
from ..models import Scenario, UnderwritingResult, utcnow
from ..schemas import CalculateIn, ResultOut, ScenarioIn, ScenarioOut, ScenarioUpdate
from ..services.underwriting import calculate, engine_error, get_scenario, run_and_store

router = APIRouter(tags=["scenarios"])


def _validate(assumptions: dict) -> None:
    try:
        Assumptions.from_dict(assumptions).validate()
    except AssumptionError as exc:
        raise engine_error(exc) from exc


@router.post("/underwriting/calculate")
def calculate_preview(body: CalculateIn, ctx: OrgContext = Depends(viewer)):
    """Stateless live calculation used by the assumptions editor (nothing is stored)."""
    return calculate(body.assumptions, body.property_type)


@router.get("/properties/{property_id}/scenarios", response_model=list[ScenarioOut])
def list_scenarios(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    prop = ctx.get_property(property_id)
    return ctx.db.scalars(select(Scenario).where(Scenario.property_id == prop.id, Scenario.deleted_at.is_(None))
                          .order_by(Scenario.is_base.desc(), Scenario.created_at)).all()


@router.post("/properties/{property_id}/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(property_id: uuid.UUID, body: ScenarioIn, ctx: OrgContext = Depends(analyst)):
    require_feature(ctx.org, "scenarios")
    prop = ctx.get_property(property_id)
    source = get_scenario(ctx, prop, body.clone_from)
    assumptions = body.assumptions if body.assumptions is not None else copy.deepcopy(source.assumptions_json)
    _validate(assumptions)
    sc = Scenario(org_id=ctx.org.id, property_id=prop.id, name=body.name, description=body.description,
                  assumptions_json=assumptions, created_by=ctx.user.id)
    ctx.db.add(sc)
    ctx.db.flush()
    run_and_store(ctx, prop, sc)
    ctx.audit("scenario.create", "scenario", sc.id, property_id=prop.id, name=sc.name)
    ctx.db.commit()
    return sc


@router.post("/properties/{property_id}/scenarios/defaults", response_model=list[ScenarioOut], status_code=201)
def create_default_scenarios(property_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    """Create Conservative / Optimistic cases from documented shifts to the base case."""
    require_feature(ctx.org, "scenarios")
    prop = ctx.get_property(property_id)
    base = get_scenario(ctx, prop)
    existing = {s.name for s in ctx.db.scalars(select(Scenario).where(Scenario.property_id == prop.id,
                                                                     Scenario.deleted_at.is_(None)))}
    created = []
    for name, shifts in DEFAULT_SCENARIO_SHIFTS.items():
        if name in existing:
            continue
        desc = "Base case with " + ", ".join(f"{k} {v:+.2%}" for k, v in shifts.items())
        sc = Scenario(org_id=ctx.org.id, property_id=prop.id, name=name, description=desc,
                      assumptions_json=shift_assumptions(base.assumptions_json, shifts), created_by=ctx.user.id)
        ctx.db.add(sc)
        ctx.db.flush()
        run_and_store(ctx, prop, sc)
        created.append(sc)
    ctx.audit("scenario.create_defaults", "property", prop.id, property_id=prop.id, count=len(created))
    ctx.db.commit()
    return created


def _scenario(ctx: OrgContext, scenario_id: uuid.UUID) -> Scenario:
    sc = ctx.db.get(Scenario, scenario_id)
    if sc is None or sc.org_id != ctx.org.id or sc.deleted_at is not None:
        raise HTTPException(404, "Scenario not found")
    ctx.get_property(sc.property_id)
    return sc


@router.get("/scenarios/{scenario_id}", response_model=ScenarioOut)
def get_scenario_route(scenario_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    return _scenario(ctx, scenario_id)


@router.patch("/scenarios/{scenario_id}", response_model=ScenarioOut)
def update_scenario(scenario_id: uuid.UUID, body: ScenarioUpdate, ctx: OrgContext = Depends(analyst)):
    sc = _scenario(ctx, scenario_id)
    prop = ctx.get_property(sc.property_id)
    changed: dict = {}
    if body.name is not None:
        sc.name = body.name
    if body.description is not None:
        sc.description = body.description
    if body.assumptions is not None:
        _validate(body.assumptions)
        before = sc.assumptions_json
        changed = {k: {"before": before.get(k), "after": v} for k, v in body.assumptions.items() if before.get(k) != v}
        sc.assumptions_json = body.assumptions
        if sc.is_base:
            # Deal-level facts follow the base case.
            for f in ("purchase_price", "hold_period_years"):
                if f in body.assumptions:
                    setattr(prop, f, body.assumptions[f])
    ctx.audit("scenario.update", "scenario", sc.id, property_id=sc.property_id, changes=changed)
    if body.assumptions is not None:
        run_and_store(ctx, prop, sc)
    ctx.db.commit()
    return sc


@router.post("/scenarios/{scenario_id}/make-base", response_model=ScenarioOut)
def make_base(scenario_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    sc = _scenario(ctx, scenario_id)
    for other in ctx.db.scalars(select(Scenario).where(Scenario.property_id == sc.property_id)):
        other.is_base = other.id == sc.id
    ctx.audit("scenario.make_base", "scenario", sc.id, property_id=sc.property_id)
    ctx.db.commit()
    return sc


@router.delete("/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    sc = _scenario(ctx, scenario_id)
    if sc.is_base:
        raise HTTPException(409, "The base scenario cannot be deleted")
    sc.deleted_at = utcnow()
    ctx.audit("scenario.delete", "scenario", sc.id, property_id=sc.property_id, name=sc.name)
    ctx.db.commit()
    return Response(status_code=204)


@router.post("/scenarios/{scenario_id}/run", response_model=ResultOut)
def run_scenario(scenario_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    sc = _scenario(ctx, scenario_id)
    row = run_and_store(ctx, ctx.get_property(sc.property_id), sc)
    ctx.db.commit()
    return row


@router.get("/scenarios/{scenario_id}/result")
def scenario_result(scenario_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    """Latest stored result with the full cash flow, audit trace and assumption snapshot."""
    sc = _scenario(ctx, scenario_id)
    prop = ctx.get_property(sc.property_id)
    from ..services.underwriting import ensure_result

    row = ensure_result(ctx, prop, sc) if ctx.can_edit else (
        ctx.db.scalars(select(UnderwritingResult).where(UnderwritingResult.scenario_id == sc.id)
                       .order_by(UnderwritingResult.calculated_at.desc())).first())
    if row is None:
        raise HTTPException(404, "No result yet")
    return {"id": str(row.id), "scenario_id": str(sc.id), "calculated_at": row.calculated_at.isoformat(),
            "stale": row.assumptions_snapshot != sc.assumptions_json, **row.full_cashflow_json}


@router.get("/properties/{property_id}/results", response_model=list[ResultOut])
def result_history(property_id: uuid.UUID, limit: int = 50, ctx: OrgContext = Depends(viewer)):
    prop = ctx.get_property(property_id)
    return ctx.db.scalars(select(UnderwritingResult).where(UnderwritingResult.property_id == prop.id)
                          .order_by(UnderwritingResult.calculated_at.desc()).limit(min(limit, 200))).all()


@router.get("/properties/{property_id}/scenario-comparison")
def scenario_comparison(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    """Headline metrics for every scenario of a deal, side by side."""
    from ..services.underwriting import ensure_result, headline, latest_result

    prop = ctx.get_property(property_id)
    out = []
    for sc in ctx.db.scalars(select(Scenario).where(Scenario.property_id == prop.id, Scenario.deleted_at.is_(None))
                             .order_by(Scenario.is_base.desc(), Scenario.created_at)):
        row = ensure_result(ctx, prop, sc) if ctx.can_edit else latest_result(ctx, prop, sc)
        a = sc.assumptions_json
        out.append({
            "scenario_id": str(sc.id), "name": sc.name, "is_base": sc.is_base,
            "key_assumptions": {k: a.get(k) for k in ("rent_growth", "vacancy_rate", "opex_growth", "exit_cap_rate",
                                                      "hold_period_years", "discount_rate")},
            "metrics": headline(row),
        })
    return out
