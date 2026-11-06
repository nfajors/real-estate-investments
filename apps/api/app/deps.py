"""Request dependencies: authentication, organization context and RBAC."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db, set_tenant
from .models import ROLE_RANK, AuditLog, Organization, OrganizationMember, Property, User
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user_id = decode_access_token(creds.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.get(User, user_id)
    if user is None or not user.is_active or user.deleted_at is not None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found")
    return user


@dataclass
class OrgContext:
    user: User
    org: Organization
    role: str
    db: Session

    def require(self, role: str) -> None:
        if ROLE_RANK[self.role] < ROLE_RANK[role]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Requires {role} role or higher")

    @property
    def can_edit(self) -> bool:
        return ROLE_RANK[self.role] >= ROLE_RANK["analyst"]

    def audit(
        self,
        action: str,
        entity_type: str,
        entity_id: Any = None,
        property_id: uuid.UUID | None = None,
        **details: Any,
    ) -> None:
        self.db.add(
            AuditLog(
                org_id=self.org.id,
                user_id=self.user.id,
                action=action,
                entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                property_id=property_id,
                details=details,
            )
        )

    def get_property(self, property_id: uuid.UUID) -> Property:
        prop = self.db.get(Property, property_id)
        if prop is None or prop.org_id != self.org.id or prop.deleted_at is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Property not found")
        return prop


def get_org_context(
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgContext:
    q = select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    if x_org_id:
        try:
            q = q.where(OrganizationMember.org_id == uuid.UUID(x_org_id))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid X-Org-Id") from exc
    membership = db.scalars(q.order_by(OrganizationMember.joined_at)).first()
    if membership is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not a member of this organization")
    org = db.get(Organization, membership.org_id)
    if org is None or org.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Organization not found")
    set_tenant(db, org.id)
    return OrgContext(user=user, org=org, role=membership.role, db=db)


def require_role(role: str):
    def dep(ctx: OrgContext = Depends(get_org_context)) -> OrgContext:
        ctx.require(role)
        return ctx

    return dep


viewer = require_role("viewer")
analyst = require_role("analyst")
admin = require_role("admin")
owner = require_role("owner")
