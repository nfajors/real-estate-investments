"""Authentication: registration, login, rotating refresh tokens, logout."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db, set_tenant
from ..deps import get_current_user
from ..models import Organization, OrganizationMember, RefreshToken, User, utcnow
from ..schemas import LoginIn, MembershipOut, MeOut, RegisterIn, TokenOut, UserOut
from ..security import create_access_token, hash_password, hash_token, new_opaque_token, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "axiom_refresh"

# Basic in-process brute-force protection (per email+IP). Replace with Redis in multi-instance deployments.
_attempts: dict[str, deque[float]] = defaultdict(deque)
MAX_ATTEMPTS, WINDOW_SECONDS = 10, 300


def _rate_limit(key: str) -> None:
    now = time.time()
    q = _attempts[key]
    while q and q[0] < now - WINDOW_SECONDS:
        q.popleft()
    if len(q) >= MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many login attempts. Try again later.")
    q.append(now)


def slugify(name: str, db: Session) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "org"
    slug, i = base, 1
    while db.scalar(select(Organization.id).where(Organization.slug == slug)):
        i += 1
        slug = f"{base}-{i}"
    return slug


def validate_password_strength(password: str) -> None:
    if len(password) < 10 or not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        raise HTTPException(422, "Password must be at least 10 characters and include letters and numbers")


def issue_tokens(db: Session, user: User, response: Response) -> TokenOut:
    s = get_settings()
    access, expires_in = create_access_token(user.id)
    refresh, refresh_hash = new_opaque_token()
    db.add(RefreshToken(user_id=user.id, token_hash=refresh_hash,
                        expires_at=utcnow() + timedelta(days=s.refresh_token_days)))
    db.commit()
    response.set_cookie(
        REFRESH_COOKIE, refresh, httponly=True, secure=s.cookie_secure, samesite="lax",
        max_age=s.refresh_token_days * 86400, path="/api/auth",
    )
    return TokenOut(access_token=access, expires_in=expires_in)


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    validate_password_strength(body.password)
    email = body.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password))
    org = Organization(name=body.organization_name.strip(), slug=slugify(body.organization_name, db))
    db.add_all([user, org])
    db.flush()
    db.add(OrganizationMember(user_id=user.id, org_id=org.id, role="owner"))
    db.commit()
    if body.seed_demo_data and get_settings().seed_demo_on_register:
        from ..services.demo_data import seed_demo_portfolio

        set_tenant(db, org.id)
        seed_demo_portfolio(db, org, user)
        set_tenant(db, None)
    return issue_tokens(db, user, response)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    email = body.email.lower()
    _rate_limit(f"{email}|{request.client.host if request.client else ''}")
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(body.password, user.password_hash) or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return issue_tokens(db, user, response)


@router.post("/refresh", response_model=TokenOut)
def refresh(
    response: Response,
    axiom_refresh: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> TokenOut:
    if not axiom_refresh:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")
    token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(axiom_refresh)))
    now = datetime.now(timezone.utc)
    if token is None or token.revoked_at is not None or _aware(token.expires_at) < now:
        if token is not None and token.revoked_at is not None:
            # Reuse of a rotated token → revoke the whole family for this user.
            for t in db.scalars(select(RefreshToken).where(RefreshToken.user_id == token.user_id,
                                                           RefreshToken.revoked_at.is_(None))):
                t.revoked_at = now
            db.commit()
        response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid or expired")
    token.revoked_at = now
    user = db.get(User, token.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return issue_tokens(db, user, response)


@router.post("/logout", status_code=204)
def logout(response: Response, axiom_refresh: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if axiom_refresh:
        token = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == hash_token(axiom_refresh)))
        if token and token.revoked_at is None:
            token.revoked_at = utcnow()
            db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    rows = db.execute(
        select(OrganizationMember, Organization)
        .join(Organization, Organization.id == OrganizationMember.org_id)
        .where(OrganizationMember.user_id == user.id, Organization.deleted_at.is_(None))
        .order_by(OrganizationMember.joined_at)
    ).all()
    return MeOut(
        user=UserOut.model_validate(user),
        memberships=[
            MembershipOut(org_id=o.id, org_name=o.name, org_slug=o.slug, role=m.role, plan=o.plan) for m, o in rows
        ],
    )


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

