"""Organizations, memberships, invitations, audit log, features and billing."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, set_tenant
from ..deps import OrgContext, admin, get_current_user, owner, viewer
from ..features import FEATURES, PLANS, resolve_features
from ..models import ROLE_RANK, AuditLog, Invitation, Organization, OrganizationMember, Property, User, utcnow
from ..schemas import (
    AcceptInvitationIn,
    InvitationCreated,
    InvitationIn,
    InvitationOut,
    MemberOut,
    MemberUpdate,
    OrgCreate,
    OrgOut,
    OrgUpdate,
    TokenOut,
)
from ..security import hash_password, hash_token, new_opaque_token, verify_password
from .auth import issue_tokens, slugify, validate_password_strength

router = APIRouter(tags=["organizations"])
INVITE_DAYS = 7


@router.post("/orgs", response_model=OrgOut, status_code=201)
def create_org(body: OrgCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    org = Organization(name=body.name.strip(), slug=slugify(body.name, db))
    db.add(org)
    db.flush()
    db.add(OrganizationMember(user_id=user.id, org_id=org.id, role="owner"))
    db.commit()
    return org


@router.get("/org", response_model=dict)
def get_org(ctx: OrgContext = Depends(viewer)) -> dict[str, Any]:
    return {
        **OrgOut.model_validate(ctx.org).model_dump(mode="json"),
        "role": ctx.role,
        "features": resolve_features(ctx.org),
        "feature_overrides": (ctx.org.settings or {}).get("feature_overrides", {}),
    }


@router.patch("/org", response_model=OrgOut)
def update_org(body: OrgUpdate, ctx: OrgContext = Depends(admin)):
    if body.name:
        ctx.org.name = body.name.strip()
    if body.feature_overrides is not None:
        ctx.require("owner")
        unknown = set(body.feature_overrides) - set(FEATURES)
        if unknown:
            raise HTTPException(422, f"Unknown features: {', '.join(sorted(unknown))}")
        settings = dict(ctx.org.settings or {})
        settings["feature_overrides"] = body.feature_overrides
        ctx.org.settings = settings
    ctx.audit("org.update", "organization", ctx.org.id, changes=body.model_dump(exclude_none=True))
    ctx.db.commit()
    return ctx.org


@router.get("/features")
def features(ctx: OrgContext = Depends(viewer)) -> dict[str, Any]:
    enabled = resolve_features(ctx.org)
    return {k: {**{kk: vv for kk, vv in v.items()}, "enabled": enabled[k]} for k, v in FEATURES.items()}


# ---------------------------------------------------------------- members
@router.get("/org/members", response_model=list[MemberOut])
def list_members(ctx: OrgContext = Depends(viewer)):
    rows = ctx.db.execute(
        select(OrganizationMember, User).join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.org_id == ctx.org.id).order_by(OrganizationMember.joined_at)
    ).all()
    return [MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, joined_at=m.joined_at) for m, u in rows]


def _membership(ctx: OrgContext, user_id: uuid.UUID) -> OrganizationMember:
    m = ctx.db.scalar(select(OrganizationMember).where(OrganizationMember.org_id == ctx.org.id,
                                                       OrganizationMember.user_id == user_id))
    if m is None:
        raise HTTPException(404, "Member not found")
    return m


def _owner_count(ctx: OrgContext) -> int:
    return ctx.db.scalar(select(func.count()).select_from(OrganizationMember).where(
        OrganizationMember.org_id == ctx.org.id, OrganizationMember.role == "owner")) or 0


@router.patch("/org/members/{user_id}", response_model=MemberOut)
def update_member(user_id: uuid.UUID, body: MemberUpdate, ctx: OrgContext = Depends(admin)):
    m = _membership(ctx, user_id)
    # Only owners may grant/revoke owner; admins cannot modify peers at or above their level.
    if (body.role == "owner" or m.role == "owner") and ctx.role != "owner":
        raise HTTPException(403, "Only owners can change ownership")
    if ctx.role != "owner" and ROLE_RANK[m.role] >= ROLE_RANK[ctx.role] and m.user_id != ctx.user.id:
        raise HTTPException(403, "Cannot modify a member with an equal or higher role")
    if m.role == "owner" and body.role != "owner" and _owner_count(ctx) <= 1:
        raise HTTPException(409, "An organization must keep at least one owner")
    before = m.role
    m.role = body.role
    ctx.audit("member.role_change", "member", user_id, before=before, after=body.role)
    ctx.db.commit()
    u = ctx.db.get(User, user_id)
    return MemberOut(user_id=u.id, email=u.email, name=u.name, role=m.role, joined_at=m.joined_at)


@router.delete("/org/members/{user_id}", status_code=204)
def remove_member(user_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    m = _membership(ctx, user_id)
    if m.role == "owner" and (ctx.role != "owner" or _owner_count(ctx) <= 1):
        raise HTTPException(409, "Cannot remove the last owner (or an owner, unless you are one)")
    if ctx.role == "admin" and m.role == "admin" and m.user_id != ctx.user.id:
        raise HTTPException(403, "Admins cannot remove other admins")
    ctx.db.delete(m)
    ctx.audit("member.remove", "member", user_id)
    ctx.db.commit()
    return Response(status_code=204)


# ------------------------------------------------------------ invitations
@router.get("/org/invitations", response_model=list[InvitationOut])
def list_invitations(ctx: OrgContext = Depends(admin)):
    return ctx.db.scalars(select(Invitation).where(Invitation.org_id == ctx.org.id)
                          .order_by(Invitation.created_at.desc())).all()


@router.post("/org/invitations", response_model=InvitationCreated, status_code=201)
def create_invitation(body: InvitationIn, request: Request, ctx: OrgContext = Depends(admin)):
    plan = PLANS.get(ctx.org.plan, PLANS["starter"])
    members = ctx.db.scalar(select(func.count()).select_from(OrganizationMember)
                            .where(OrganizationMember.org_id == ctx.org.id)) or 0
    if plan["max_members"] is not None and members >= plan["max_members"]:
        raise HTTPException(402, f"The {plan['label']} plan allows {plan['max_members']} members")
    if body.role == "admin" and ctx.role != "owner":
        raise HTTPException(403, "Only owners can invite admins")
    email = body.email.lower()
    existing_user = ctx.db.scalar(select(User).where(User.email == email))
    if existing_user and ctx.db.scalar(select(OrganizationMember.id).where(
            OrganizationMember.org_id == ctx.org.id, OrganizationMember.user_id == existing_user.id)):
        raise HTTPException(409, "This person is already a member")
    token, token_hash = new_opaque_token()
    inv = Invitation(org_id=ctx.org.id, email=email, role=body.role, token_hash=token_hash, invited_by=ctx.user.id,
                     expires_at=utcnow() + timedelta(days=INVITE_DAYS))
    ctx.db.add(inv)
    ctx.audit("invitation.create", "invitation", None, email=email, role=body.role)
    ctx.db.commit()
    origin = request.headers.get("origin") or get_settings().cors_origins[0]
    # Email delivery is pluggable; in development the accept link is returned to the inviter.
    return InvitationCreated(**InvitationOut.model_validate(inv).model_dump(), token=token,
                             accept_url=f"{origin}/invite/{token}")


@router.delete("/org/invitations/{invitation_id}", status_code=204)
def revoke_invitation(invitation_id: uuid.UUID, ctx: OrgContext = Depends(admin)):
    inv = ctx.db.get(Invitation, invitation_id)
    if inv is None or inv.org_id != ctx.org.id:
        raise HTTPException(404, "Invitation not found")
    inv.revoked_at = utcnow()
    ctx.audit("invitation.revoke", "invitation", invitation_id)
    ctx.db.commit()
    return Response(status_code=204)


def _valid_invitation(db: Session, token: str) -> Invitation:
    inv = db.scalar(select(Invitation).where(Invitation.token_hash == hash_token(token)))
    now = datetime.now(timezone.utc)
    if inv is None or inv.revoked_at or inv.accepted_at:
        raise HTTPException(404, "Invitation not found or already used")
    expires = inv.expires_at if inv.expires_at.tzinfo else inv.expires_at.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(410, "Invitation expired")
    return inv


@router.get("/invitations/{token}")
def preview_invitation(token: str, db: Session = Depends(get_db)) -> dict[str, Any]:
    inv = _valid_invitation(db, token)
    org = db.get(Organization, inv.org_id)
    has_account = db.scalar(select(User.id).where(User.email == inv.email)) is not None
    return {"email": inv.email, "role": inv.role, "organization": org.name, "has_account": has_account}


@router.post("/invitations/accept", response_model=TokenOut)
def accept_invitation(body: AcceptInvitationIn, response: Response, db: Session = Depends(get_db)):
    """Accept an invitation. Existing users must log in first and pass the token;
    new users supply a name and password to create their account."""
    inv = _valid_invitation(db, body.token)
    user = db.scalar(select(User).where(User.email == inv.email))
    if user is None:
        if not body.name or not body.password:
            raise HTTPException(422, "Name and password are required to create your account")
        validate_password_strength(body.password)
        user = User(email=inv.email, name=body.name.strip(), password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
    elif not body.password or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Enter your existing password to join this organization")
    if not db.scalar(select(OrganizationMember.id).where(OrganizationMember.org_id == inv.org_id,
                                                        OrganizationMember.user_id == user.id)):
        db.add(OrganizationMember(user_id=user.id, org_id=inv.org_id, role=inv.role, invited_at=inv.created_at))
    inv.accepted_at = utcnow()
    set_tenant(db, inv.org_id)  # audit_logs is RLS-protected
    db.add(AuditLog(org_id=inv.org_id, user_id=user.id, action="invitation.accept", entity_type="invitation",
                    entity_id=str(inv.id), details={"role": inv.role}))
    db.commit()
    return issue_tokens(db, user, response)


# --------------------------------------------------------------- audit log
@router.get("/org/audit")
def audit_log(limit: int = 100, property_id: uuid.UUID | None = None, ctx: OrgContext = Depends(viewer)):
    q = select(AuditLog, User.name).outerjoin(User, User.id == AuditLog.user_id).where(AuditLog.org_id == ctx.org.id)
    if property_id:
        q = q.where(AuditLog.property_id == property_id)
    rows = ctx.db.execute(q.order_by(AuditLog.created_at.desc()).limit(min(limit, 500))).all()
    return [
        {"id": str(a.id), "action": a.action, "entity_type": a.entity_type, "entity_id": a.entity_id,
         "property_id": str(a.property_id) if a.property_id else None, "details": a.details,
         "user_name": name, "created_at": a.created_at.isoformat()}
        for a, name in rows
    ]


# ----------------------------------------------------------------- billing
@router.get("/billing")
def billing(ctx: OrgContext = Depends(viewer)) -> dict[str, Any]:
    deals = ctx.db.scalar(select(func.count()).select_from(Property).where(
        Property.org_id == ctx.org.id, Property.deleted_at.is_(None))) or 0
    members = ctx.db.scalar(select(func.count()).select_from(OrganizationMember)
                            .where(OrganizationMember.org_id == ctx.org.id)) or 0
    s = get_settings()
    return {
        "plan": ctx.org.plan,
        "plans": {k: {**v, "features": sorted(v["features"]), "stripe_price_id": s.stripe_price_ids.get(k)}
                  for k, v in PLANS.items()},
        "usage": {"deals": deals, "members": members},
        "billing_mode": "stripe" if s.stripe_secret_key and s.billing_mode == "stripe" else "manual",
    }


@router.post("/billing/plan")
def change_plan(body: dict[str, str], ctx: OrgContext = Depends(owner)) -> dict[str, Any]:
    plan = body.get("plan")
    if plan not in PLANS:
        raise HTTPException(422, "Unknown plan")
    s = get_settings()
    if s.billing_mode == "stripe" and s.stripe_secret_key:
        price = body.get("price_id") or s.stripe_price_ids.get(plan)
        if not price:
            raise HTTPException(422, f"No Stripe price configured for the {plan} plan (AXIOM_STRIPE_PRICE_IDS)")
        origin = get_settings().cors_origins[0]
        resp = httpx.post(
            "https://api.stripe.com/v1/checkout/sessions",
            auth=(s.stripe_secret_key, ""),
            data={"mode": "subscription", "line_items[0][price]": price, "line_items[0][quantity]": 1,
                  "success_url": f"{origin}/settings?billing=success", "cancel_url": f"{origin}/settings",
                  "client_reference_id": str(ctx.org.id), "metadata[plan]": plan},
            timeout=20,
        )
        if resp.status_code >= 400:
            raise HTTPException(502, "Stripe checkout could not be created")
        return {"checkout_url": resp.json()["url"]}
    before = ctx.org.plan
    ctx.org.plan = plan
    ctx.audit("billing.plan_change", "organization", ctx.org.id, before=before, after=plan, mode="manual")
    ctx.db.commit()
    return {"plan": plan}

