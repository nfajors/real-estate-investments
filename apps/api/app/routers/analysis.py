"""Risk analysis, valuation, financing, development, deal comparison and dashboard."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Any

from axiom_engine import AssumptionError, run_underwriting
from axiom_engine.development import run_development
from axiom_engine.financing import compare_structures
from axiom_engine.montecarlo import run_monte_carlo
from axiom_engine.scenarios import SENSITIVITY_METRICS, centered_range, get_path, sensitivity_table
from axiom_engine.valuation import valuation_summary
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select

from ..deps import OrgContext, analyst, viewer
from ..features import require_feature
from ..models import AuditLog, FinancingStructure, Property, User
from ..schemas import FinancingIn, FinancingOut, MonteCarloIn, SensitivityIn
from ..services.underwriting import engine_error, ensure_result, get_scenario, headline, run_and_store
from .properties import _latest_by_property

router = APIRouter(tags=["analysis"])

# Step sizes for auto-generated sensitivity axes.
AXIS_STEPS = {"rent_growth": 0.01, "exit_cap_rate": 0.0025, "vacancy_rate": 0.01, "opex_growth": 0.005,
              "discount_rate": 0.005, "purchase_price": None, "loan.interest_rate": 0.005, "opex_ratio": 0.02,
              "other_income_growth": 0.01, "hold_period_years": 1}


def _axis(base: dict, path: str, values: list[float] | None) -> list[float]:
    if values:
        if len(values) > 9:
            raise HTTPException(422, "At most 9 values per axis")
        return values
    try:
        center = get_path(base, path)
    except KeyError as exc:
        raise HTTPException(422, f"Unknown assumption path '{path}'") from exc
    if not isinstance(center, (int, float)):
        raise HTTPException(422, f"'{path}' is not numeric")
    step = AXIS_STEPS.get(path)
    if path == "hold_period_years":
        return [v for v in (center - 2, center - 1, center, center + 1, center + 2) if 1 <= v <= 30]
    if step is None:
        step = abs(center) * 0.05 or 0.01
    return centered_range(float(center), step, 5)


@router.post("/properties/{property_id}/sensitivity")
def sensitivity(property_id: uuid.UUID, body: SensitivityIn, ctx: OrgContext = Depends(viewer)):
    require_feature(ctx.org, "scenarios")
    if body.metric not in SENSITIVITY_METRICS:
        raise HTTPException(422, f"metric must be one of {', '.join(SENSITIVITY_METRICS)}")
    prop = ctx.get_property(property_id)
    sc = get_scenario(ctx, prop, body.scenario_id)
    base = sc.assumptions_json
    rows = _axis(base, body.row_path, body.row_values)
    cols = _axis(base, body.col_path, body.col_values)
    if body.row_path == "hold_period_years":
        rows = [int(v) for v in rows]
    if body.col_path == "hold_period_years":
        cols = [int(v) for v in cols]
    try:
        table = sensitivity_table(base, body.row_path, rows, body.col_path, cols, body.metric)
    except AssumptionError as exc:
        raise engine_error(exc) from exc
    table["base_row"] = get_path(base, body.row_path)
    table["base_col"] = get_path(base, body.col_path)
    table["scenario_id"] = str(sc.id)
    return table


DEFAULT_MC = [
    {"path": "rent_growth", "kind": "normal", "std": 0.01},
    {"path": "vacancy_rate", "kind": "normal", "std": 0.015, "low": 0.0, "high": 0.5},
    {"path": "opex_growth", "kind": "normal", "std": 0.0075},
    {"path": "exit_cap_rate", "kind": "normal", "std": 0.004, "low": 0.03},
]


@router.post("/properties/{property_id}/monte-carlo")
def monte_carlo(property_id: uuid.UUID, body: MonteCarloIn, ctx: OrgContext = Depends(viewer)):
    require_feature(ctx.org, "monte_carlo")
    prop = ctx.get_property(property_id)
    sc = get_scenario(ctx, prop, body.scenario_id)
    try:
        out = run_monte_carlo(sc.assumptions_json, body.distributions or DEFAULT_MC, body.iterations, body.seed)
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    out["distributions"] = body.distributions or DEFAULT_MC
    out["scenario_id"] = str(sc.id)
    ctx.audit("risk.monte_carlo", "scenario", sc.id, property_id=prop.id, iterations=body.iterations, seed=body.seed)
    ctx.db.commit()
    return out


# --------------------------------------------------------------- valuation
@router.get("/properties/{property_id}/valuation")
def valuation(property_id: uuid.UUID, scenario_id: uuid.UUID | None = None, ctx: OrgContext = Depends(viewer)):
    require_feature(ctx.org, "valuation")
    prop = ctx.get_property(property_id)
    sc = get_scenario(ctx, prop, scenario_id)
    try:
        result = run_underwriting(sc.assumptions_json)
    except AssumptionError as exc:
        raise engine_error(exc) from exc
    vi = prop.valuation_inputs or {}
    a = sc.assumptions_json
    try:
        out = valuation_summary(
            result,
            market_cap_rate=vi.get("market_cap_rate", a["exit_cap_rate"]),
            discount_rate=vi.get("discount_rate", a["discount_rate"]),
            purchase_price=a["purchase_price"],
            comps=vi.get("comps") or None,
            subject_units=prop.units or a.get("units"),
            subject_sf=prop.rentable_sf or a.get("rentable_sf"),
            cost=vi.get("cost") or None,
            weights=vi.get("weights") or None,
        )
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc
    out["inputs"] = vi
    out["scenario_id"] = str(sc.id)
    return out


@router.put("/properties/{property_id}/valuation")
def save_valuation_inputs(property_id: uuid.UUID, body: dict[str, Any], ctx: OrgContext = Depends(analyst)):
    prop = ctx.get_property(property_id)
    allowed = {"market_cap_rate", "discount_rate", "comps", "cost", "weights"}
    unknown = set(body) - allowed
    if unknown:
        raise HTTPException(422, f"Unknown valuation inputs: {', '.join(sorted(unknown))}")
    prop.valuation_inputs = body
    ctx.audit("valuation.update", "property", prop.id, property_id=prop.id)
    ctx.db.commit()
    return valuation(property_id, None, ctx)


# --------------------------------------------------------------- financing
def _structure_to_engine(f: FinancingStructure) -> dict[str, Any]:
    loan = {
        "name": f.name, "loan_type": f.type, "rate_type": f.rate_type, "amount": f.loan_amount,
        "ltv": f.ltv if f.loan_amount is None else None, "interest_rate": f.interest_rate,
        "index_rate": f.index_rate, "spread": f.spread, "amortization_years": f.amortization_years,
        "term_years": f.term_years, "io_years": f.io_period,
        "origination_fee_pct": (f.fees or {}).get("origination_fee_pct", 0.0),
        "exit_fee_pct": (f.fees or {}).get("exit_fee_pct", 0.0),
        "min_dscr_covenant": (f.covenants or {}).get("min_dscr"),
        "max_ltv_covenant": (f.covenants or {}).get("max_ltv"),
    }
    return loan


@router.get("/properties/{property_id}/financing", response_model=list[FinancingOut])
def list_financing(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    prop = ctx.get_property(property_id)
    return ctx.db.scalars(select(FinancingStructure).where(FinancingStructure.property_id == prop.id)
                          .order_by(FinancingStructure.created_at)).all()


@router.post("/properties/{property_id}/financing", response_model=FinancingOut, status_code=201)
def create_financing(property_id: uuid.UUID, body: FinancingIn, ctx: OrgContext = Depends(analyst)):
    prop = ctx.get_property(property_id)
    if body.loan_amount is None and body.ltv is None:
        raise HTTPException(422, "Provide a loan amount or LTV")
    f = FinancingStructure(org_id=ctx.org.id, property_id=prop.id, **body.model_dump(exclude={"is_active"}))
    ctx.db.add(f)
    ctx.db.flush()
    _check_structure(prop, ctx, f)
    ctx.audit("financing.create", "financing_structure", f.id, property_id=prop.id, name=f.name)
    ctx.db.commit()
    if body.is_active:
        return activate_financing(f.id, ctx)
    return f


def _check_structure(prop: Property, ctx: OrgContext, f: FinancingStructure) -> None:
    sc = get_scenario(ctx, prop)
    a = dict(sc.assumptions_json)
    a["loan"] = _structure_to_engine(f)
    a["preferred_equity"] = f.preferred_equity
    try:
        run_underwriting(a)
    except AssumptionError as exc:
        ctx.db.rollback()
        raise engine_error(exc) from exc


@router.put("/financing/{financing_id}", response_model=FinancingOut)
def update_financing(financing_id: uuid.UUID, body: FinancingIn, ctx: OrgContext = Depends(analyst)):
    f = _financing(ctx, financing_id)
    for k, v in body.model_dump(exclude={"is_active"}).items():
        setattr(f, k, v)
    prop = ctx.get_property(f.property_id)
    _check_structure(prop, ctx, f)
    ctx.audit("financing.update", "financing_structure", f.id, property_id=f.property_id)
    ctx.db.commit()
    if f.is_active:
        return activate_financing(f.id, ctx)
    return f


def _financing(ctx: OrgContext, financing_id: uuid.UUID) -> FinancingStructure:
    f = ctx.db.get(FinancingStructure, financing_id)
    if f is None or f.org_id != ctx.org.id:
        raise HTTPException(404, "Financing structure not found")
    return f


@router.delete("/financing/{financing_id}", status_code=204)
def delete_financing(financing_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    f = _financing(ctx, financing_id)
    ctx.db.delete(f)
    ctx.audit("financing.delete", "financing_structure", financing_id, property_id=f.property_id)
    ctx.db.commit()
    return Response(status_code=204)


@router.post("/financing/{financing_id}/activate", response_model=FinancingOut)
def activate_financing(financing_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    """Make this structure the capital stack of the base scenario and re-run underwriting."""
    f = _financing(ctx, financing_id)
    prop = ctx.get_property(f.property_id)
    for other in ctx.db.scalars(select(FinancingStructure).where(FinancingStructure.property_id == prop.id)):
        other.is_active = other.id == f.id
    sc = get_scenario(ctx, prop)
    a = dict(sc.assumptions_json)
    a["loan"] = _structure_to_engine(f)
    a["preferred_equity"] = f.preferred_equity
    sc.assumptions_json = a
    run_and_store(ctx, prop, sc)
    ctx.audit("financing.activate", "financing_structure", f.id, property_id=prop.id, scenario_id=str(sc.id))
    ctx.db.commit()
    return f


@router.get("/properties/{property_id}/financing/compare")
def financing_compare(property_id: uuid.UUID, scenario_id: uuid.UUID | None = None,
                      ctx: OrgContext = Depends(viewer)):
    require_feature(ctx.org, "financing_compare")
    prop = ctx.get_property(property_id)
    sc = get_scenario(ctx, prop, scenario_id)
    structs = ctx.db.scalars(select(FinancingStructure).where(FinancingStructure.property_id == prop.id)
                             .order_by(FinancingStructure.created_at)).all()
    payload = [{"name": "All cash (unlevered)", "loan": None, "preferred_equity": None}]
    payload += [{"name": f.name, "loan": _structure_to_engine(f), "preferred_equity": f.preferred_equity}
                for f in structs]
    try:
        rows = compare_structures(sc.assumptions_json, payload)
    except AssumptionError as exc:
        raise engine_error(exc) from exc
    ids = [None] + [str(f.id) for f in structs]
    active = [False] + [f.is_active for f in structs]
    for r, i, act in zip(rows, ids, active):
        r["financing_id"] = i
        r["is_active"] = act
    return rows


# ------------------------------------------------------------- development
@router.post("/development/calculate")
def development(body: dict[str, Any], ctx: OrgContext = Depends(viewer)):
    require_feature(ctx.org, "development")
    try:
        return run_development(body)
    except (ValueError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put("/properties/{property_id}/development")
def save_development(property_id: uuid.UUID, body: dict[str, Any], ctx: OrgContext = Depends(analyst)):
    require_feature(ctx.org, "development")
    prop = ctx.get_property(property_id)
    out = development(body, ctx)
    attrs = dict(prop.attributes or {})
    attrs["development"] = body
    prop.attributes = attrs
    ctx.audit("development.update", "property", prop.id, property_id=prop.id,
              yield_on_cost=out["returns"]["yield_on_cost"])
    ctx.db.commit()
    return out


# ---------------------------------------------------------- deal comparison
@router.get("/compare")
def compare_deals(ids: str = Query(..., description="Comma-separated property ids"),
                  ctx: OrgContext = Depends(viewer)):
    require_feature(ctx.org, "deal_comparison")
    try:
        id_list = [uuid.UUID(i) for i in ids.split(",") if i]
    except ValueError as exc:
        raise HTTPException(422, "Invalid property id") from exc
    if not 1 <= len(id_list) <= 8:
        raise HTTPException(422, "Select between 1 and 8 deals")
    out = []
    for pid in id_list:
        prop = ctx.get_property(pid)
        sc = get_scenario(ctx, prop)
        row = ensure_result(ctx, prop, sc) if ctx.can_edit else _latest_by_property(ctx, [prop.id]).get(prop.id)
        h = headline(row) or {}
        out.append({
            "property_id": str(prop.id), "name": prop.name, "property_type": prop.property_type,
            "city": prop.city, "state": prop.state, "status": prop.status, "is_demo": prop.is_demo,
            "purchase_price": prop.purchase_price, "units": prop.units, "rentable_sf": prop.rentable_sf, **h,
            "risk_factors": (row.full_cashflow_json.get("risk", {}).get("factors", []) if row else []),
        })
    return out


# ---------------------------------------------------------------- dashboard
@router.get("/dashboard")
def dashboard(status: str | None = None, property_type: str | None = None, owner_id: uuid.UUID | None = None,
              ctx: OrgContext = Depends(viewer)):
    stmt = select(Property).where(Property.org_id == ctx.org.id, Property.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Property.status.in_(status.split(",")))
    if property_type:
        stmt = stmt.where(Property.property_type.in_(property_type.split(",")))
    if owner_id:
        stmt = stmt.where(Property.owner_id == owner_id)
    props = ctx.db.scalars(stmt).all()
    latest = _latest_by_property(ctx, [p.id for p in props])

    pipeline: dict[str, dict[str, float]] = defaultdict(lambda: {"count": 0, "volume": 0.0})
    by_type: dict[str, float] = defaultdict(float)
    by_state: dict[str, float] = defaultdict(float)
    aum = 0.0
    cap_num = cap_den = 0.0
    irrs: list[float] = []
    alerts = []
    for p in props:
        price = p.purchase_price or 0.0
        pipeline[p.status]["count"] += 1
        pipeline[p.status]["volume"] += price
        if p.status == "passed":
            continue
        by_type[p.property_type] += price
        by_state[p.state or "N/A"] += price
        if p.status == "closed":
            aum += price
        r = latest.get(p.id)
        if r is None:
            continue
        cap_num += r.cap_rate * price
        cap_den += price
        if r.irr_levered is not None:
            irrs.append(r.irr_levered)
        risk = r.full_cashflow_json.get("risk", {})
        if risk.get("level") == "high":
            alerts.append({"property_id": str(p.id), "name": p.name, "severity": "high",
                           "message": f"High risk score ({risk.get('score')}): " +
                           "; ".join(f["message"] for f in risk.get("factors", [])[:2])})
        for b in r.full_cashflow_json.get("covenant_breaches", [])[:1]:
            alerts.append({"property_id": str(p.id), "name": p.name, "severity": "medium",
                           "message": f"Projected {b['covenant']} covenant breach in year {b['year']}"})
        for w in r.full_cashflow_json.get("warnings", []):
            if w.get("severity") == "high":
                alerts.append({"property_id": str(p.id), "name": p.name, "severity": "medium",
                               "message": w["message"]})

    activity = ctx.db.execute(
        select(AuditLog, User.name, Property.name).outerjoin(User, User.id == AuditLog.user_id)
        .outerjoin(Property, Property.id == AuditLog.property_id)
        .where(AuditLog.org_id == ctx.org.id).order_by(AuditLog.created_at.desc()).limit(15)
    ).all()
    active = [p for p in props if p.status != "passed"]
    return {
        "totals": {
            "deals": len(props),
            "active_deals": len(active),
            "pipeline_volume": sum(p.purchase_price or 0 for p in active if p.status != "closed"),
            "aum": aum,
            "weighted_avg_cap_rate": cap_num / cap_den if cap_den else None,
            "irr_min": min(irrs) if irrs else None,
            "irr_max": max(irrs) if irrs else None,
            "irr_median": sorted(irrs)[len(irrs) // 2] if irrs else None,
            "demo_deals": sum(1 for p in props if p.is_demo),
        },
        "pipeline": [{"status": s, **pipeline.get(s, {"count": 0, "volume": 0.0})}
                     for s in ("sourcing", "underwriting", "ic", "closed", "passed")],
        "exposure_by_type": [{"key": k, "value": v} for k, v in sorted(by_type.items(), key=lambda x: -x[1])],
        "exposure_by_state": [{"key": k, "value": v} for k, v in sorted(by_state.items(), key=lambda x: -x[1])],
        "alerts": alerts[:12],
        "recent_activity": [
            {"action": a.action, "entity_type": a.entity_type, "user_name": u, "property_name": pn,
             "property_id": str(a.property_id) if a.property_id else None, "created_at": a.created_at.isoformat(),
             "details": {k: v for k, v in (a.details or {}).items() if k in ("name", "scenario", "irr_levered",
                                                                             "count", "field_path")}}
            for a, u, pn in activity
        ],
    }
