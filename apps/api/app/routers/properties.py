"""Properties / deals CRUD and pipeline listing."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, or_, select

from ..deps import OrgContext, admin, analyst, viewer
from ..features import PLANS
from ..models import Property, Scenario, UnderwritingResult, User
from ..schemas import PropertyCreate, PropertyOut, PropertySummary, PropertyUpdate
from ..services.property_types import catalogue, default_assumptions
from ..services.underwriting import headline, run_and_store, sync_property_to_scenarios

router = APIRouter(tags=["properties"])


@router.get("/property-types")
def property_types():
    return catalogue()


def _latest_by_property(ctx: OrgContext, ids: list[uuid.UUID]) -> dict[uuid.UUID, UnderwritingResult]:
    """Latest base-scenario result per property in one query."""
    if not ids:
        return {}
    base_ids = select(Scenario.id).where(Scenario.property_id.in_(ids), Scenario.is_base.is_(True),
                                         Scenario.deleted_at.is_(None))
    rows = ctx.db.scalars(
        select(UnderwritingResult)
        .where(UnderwritingResult.org_id == ctx.org.id, UnderwritingResult.scenario_id.in_(base_ids))
        .order_by(UnderwritingResult.calculated_at.desc())
    ).all()
    out: dict[uuid.UUID, UnderwritingResult] = {}
    for r in rows:
        out.setdefault(r.property_id, r)
    return out


@router.get("/properties", response_model=list[PropertySummary])
def list_properties(
    status: str | None = None,
    property_type: str | None = None,
    owner_id: uuid.UUID | None = None,
    q: str | None = None,
    ctx: OrgContext = Depends(viewer),
):
    stmt = select(Property, User.name).outerjoin(User, User.id == Property.owner_id).where(
        Property.org_id == ctx.org.id, Property.deleted_at.is_(None))
    if status:
        stmt = stmt.where(Property.status.in_(status.split(",")))
    if property_type:
        stmt = stmt.where(Property.property_type.in_(property_type.split(",")))
    if owner_id:
        stmt = stmt.where(Property.owner_id == owner_id)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(or_(func.lower(Property.name).like(like), func.lower(Property.city).like(like),
                              func.lower(Property.state).like(like)))
    rows = ctx.db.execute(stmt.order_by(Property.updated_at.desc())).all()
    latest = _latest_by_property(ctx, [p.id for p, _ in rows])
    return [
        PropertySummary(**PropertyOut.model_validate(p).model_dump(), owner_name=name, latest=headline(latest.get(p.id)))
        for p, name in rows
    ]


@router.post("/properties", response_model=PropertySummary, status_code=201)
def create_property(body: PropertyCreate, ctx: OrgContext = Depends(analyst)):
    plan = PLANS.get(ctx.org.plan, PLANS["starter"])
    count = ctx.db.scalar(select(func.count()).select_from(Property).where(
        Property.org_id == ctx.org.id, Property.deleted_at.is_(None))) or 0
    if plan["max_deals"] is not None and count >= plan["max_deals"]:
        raise HTTPException(402, f"The {plan['label']} plan allows {plan['max_deals']} active deals")
    data = body.model_dump(exclude={"owner_id"})
    prop = Property(org_id=ctx.org.id, created_by=ctx.user.id, updated_by=ctx.user.id,
                    owner_id=body.owner_id or ctx.user.id, **data)
    ctx.db.add(prop)
    ctx.db.flush()
    assumptions = default_assumptions(body.property_type, body.purchase_price, body.hold_period_years,
                                      body.units, body.rentable_sf)
    base = Scenario(org_id=ctx.org.id, property_id=prop.id, name="Base Case", is_base=True,
                    description="Template assumptions – replace with verified document data.",
                    assumptions_json=assumptions, created_by=ctx.user.id)
    ctx.db.add(base)
    ctx.db.flush()
    ctx.audit("property.create", "property", prop.id, property_id=prop.id, name=prop.name)
    row = run_and_store(ctx, prop, base)
    ctx.db.commit()
    return PropertySummary(**PropertyOut.model_validate(prop).model_dump(), owner_name=None, latest=headline(row))


@router.get("/properties/{property_id}", response_model=PropertySummary)
def get_property(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    prop = ctx.get_property(property_id)
    owner = ctx.db.get(User, prop.owner_id) if prop.owner_id else None
    latest = _latest_by_property(ctx, [prop.id]).get(prop.id)
    return PropertySummary(**PropertyOut.model_validate(prop).model_dump(), owner_name=owner.name if owner else None,
                           latest=headline(latest))


@router.patch("/properties/{property_id}", response_model=PropertyOut)
def update_property(property_id: uuid.UUID, body: PropertyUpdate, ctx: OrgContext = Depends(analyst)):
    prop = ctx.get_property(property_id)
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(prop, k) for k in changes}
    for k, v in changes.items():
        setattr(prop, k, v)
    prop.updated_by = ctx.user.id
    sync_property_to_scenarios(ctx, prop, changes)
    ctx.audit("property.update", "property", prop.id, property_id=prop.id,
              changes={k: {"before": _jsonable(before[k]), "after": _jsonable(v)} for k, v in changes.items()})
    ctx.db.commit()
    return prop


@router.delete("/properties/{property_id}", status_code=204)
def delete_property(property_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    from ..models import utcnow

    prop = ctx.get_property(property_id)
    prop.deleted_at = utcnow()
    ctx.audit("property.delete", "property", prop.id, property_id=prop.id, name=prop.name)
    ctx.db.commit()
    return Response(status_code=204)


def _jsonable(v):
    if isinstance(v, (str, int, float, bool, dict, list)) or v is None:
        return v
    return str(v)
