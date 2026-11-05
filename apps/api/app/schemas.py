"""Pydantic request/response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import PROPERTY_STATUSES, ROLES
from .services.property_types import PROPERTY_TYPES

Role = Literal["owner", "admin", "analyst", "viewer"]


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------- auth
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    organization_name: str = Field(min_length=2, max_length=200)
    seed_demo_data: bool = True


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(ORM):
    id: uuid.UUID
    email: str
    name: str


class MembershipOut(BaseModel):
    org_id: uuid.UUID
    org_name: str
    org_slug: str
    role: str
    plan: str


class MeOut(BaseModel):
    user: UserOut
    memberships: list[MembershipOut]


# ---------------------------------------------------------------- orgs
class OrgOut(ORM):
    id: uuid.UUID
    name: str
    slug: str
    plan: str
    created_at: datetime


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    feature_overrides: dict[str, bool] | None = None


class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)


class MemberOut(BaseModel):
    user_id: uuid.UUID
    email: str
    name: str
    role: str
    joined_at: datetime


class MemberUpdate(BaseModel):
    role: Role


class InvitationIn(BaseModel):
    email: EmailStr
    role: Role = "analyst"

    @field_validator("role")
    @classmethod
    def no_owner_invites(cls, v: str) -> str:
        if v == "owner":
            raise ValueError("Ownership is transferred, not invited")
        return v


class InvitationOut(ORM):
    id: uuid.UUID
    email: str
    role: str
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None


class InvitationCreated(InvitationOut):
    token: str
    accept_url: str


class AcceptInvitationIn(BaseModel):
    token: str
    # For invitees without an account:
    name: str | None = None
    password: str | None = Field(default=None, min_length=10, max_length=200)


# ---------------------------------------------------------- properties
class PropertyBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    property_type: str
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    status: str = "sourcing"
    purchase_price: float | None = Field(default=None, gt=0)
    acquisition_date: date | None = None
    hold_period_years: int = Field(default=10, ge=1, le=30)
    units: int | None = Field(default=None, ge=0)
    rentable_sf: float | None = Field(default=None, ge=0)
    year_built: int | None = Field(default=None, ge=1700, le=2100)
    description: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("property_type")
    @classmethod
    def valid_type(cls, v: str) -> str:
        if v not in PROPERTY_TYPES:
            raise ValueError(f"Unknown property type. Use one of: {', '.join(PROPERTY_TYPES)}")
        return v

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        if v not in PROPERTY_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(PROPERTY_STATUSES)}")
        return v


class PropertyCreate(PropertyBase):
    purchase_price: float = Field(gt=0)
    owner_id: uuid.UUID | None = None


class PropertyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip_code: str | None = None
    status: str | None = None
    purchase_price: float | None = Field(default=None, gt=0)
    acquisition_date: date | None = None
    hold_period_years: int | None = Field(default=None, ge=1, le=30)
    units: int | None = Field(default=None, ge=0)
    rentable_sf: float | None = Field(default=None, ge=0)
    year_built: int | None = Field(default=None, ge=1700, le=2100)
    description: str | None = None
    attributes: dict[str, Any] | None = None
    owner_id: uuid.UUID | None = None
    valuation_inputs: dict[str, Any] | None = None

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str | None) -> str | None:
        if v is not None and v not in PROPERTY_STATUSES:
            raise ValueError(f"Status must be one of: {', '.join(PROPERTY_STATUSES)}")
        return v


class PropertyOut(ORM):
    id: uuid.UUID
    name: str
    property_type: str
    address: str | None
    city: str | None
    state: str | None
    zip_code: str | None
    status: str
    purchase_price: float | None
    acquisition_date: date | None
    hold_period_years: int
    units: int | None
    rentable_sf: float | None
    year_built: int | None
    description: str | None
    attributes: dict[str, Any]
    valuation_inputs: dict[str, Any]
    is_demo: bool
    owner_id: uuid.UUID | None
    created_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class PropertySummary(PropertyOut):
    owner_name: str | None = None
    latest: dict[str, Any] | None = None  # headline metrics of the base scenario


# ----------------------------------------------------------- scenarios
class ScenarioIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    assumptions: dict[str, Any] | None = None  # defaults to a copy of the base scenario
    clone_from: uuid.UUID | None = None


class ScenarioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None
    assumptions: dict[str, Any] | None = None


class ScenarioOut(ORM):
    id: uuid.UUID
    property_id: uuid.UUID
    name: str
    description: str | None
    is_base: bool
    assumptions: dict[str, Any] = Field(validation_alias="assumptions_json")
    created_at: datetime
    updated_at: datetime


class CalculateIn(BaseModel):
    assumptions: dict[str, Any]
    property_type: str = "multifamily"


class SensitivityIn(BaseModel):
    scenario_id: uuid.UUID | None = None
    row_path: str = "rent_growth"
    row_values: list[float] | None = None
    col_path: str = "exit_cap_rate"
    col_values: list[float] | None = None
    metric: str = "irr_levered"


class MonteCarloIn(BaseModel):
    scenario_id: uuid.UUID | None = None
    iterations: int = Field(default=1000, ge=10, le=10000)
    seed: int = 42
    distributions: list[dict[str, Any]] | None = None


class ResultOut(ORM):
    id: uuid.UUID
    property_id: uuid.UUID
    scenario_id: uuid.UUID
    calculated_at: datetime
    engine_version: str
    noi_year1: float
    cap_rate: float
    irr_unlevered: float | None
    irr_levered: float | None
    npv: float | None
    equity_multiple: float | None
    cash_on_cash: float | None
    dscr: float | None
    ltv: float | None
    risk_score: float | None


# ----------------------------------------------------------- financing
class FinancingIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: Literal["permanent", "bridge", "construction", "interest_only"] = "permanent"
    rate_type: Literal["fixed", "floating"] = "fixed"
    loan_amount: float | None = Field(default=None, ge=0)
    ltv: float | None = Field(default=None, ge=0, lt=1)
    interest_rate: float = Field(default=0.0, ge=0, lt=0.5)
    index_rate: float = Field(default=0.0, ge=0, lt=0.5)
    spread: float = Field(default=0.0, ge=0, lt=0.5)
    term_years: int = Field(default=10, ge=1, le=40)
    amortization_years: int = Field(default=30, ge=0, le=40)
    io_period: float = Field(default=0.0, ge=0, le=40)
    fees: dict[str, float] = Field(default_factory=dict)
    covenants: dict[str, float] = Field(default_factory=dict)
    preferred_equity: dict[str, float] | None = None
    is_active: bool = False


class FinancingOut(ORM, FinancingIn):
    id: uuid.UUID
    property_id: uuid.UUID


# ------------------------------------------------------------ documents
class DocumentOut(ORM):
    id: uuid.UUID
    property_id: uuid.UUID
    name: str
    type: str
    mime_type: str
    size_bytes: int
    status: str
    page_count: int | None
    extractor: str | None
    error: str | None
    created_at: datetime


class PageOut(BaseModel):
    page_number: int
    label: str | None
    text: str
    width: float | None
    height: float | None
    image_url: str | None
    cells: list[Any] | None


class ExtractionOut(ORM):
    id: uuid.UUID
    document_id: uuid.UUID
    property_id: uuid.UUID
    field_path: str
    label: str | None
    value: Any
    original_value: Any
    unit: str | None
    confidence: float
    source_page: int | None
    source_ref: str | None
    source_excerpt: str | None
    source_bbox: dict[str, float] | None
    citation_verified: bool
    extractor: str
    status: str
    verified_by: uuid.UUID | None
    verified_at: datetime | None
    version: int


class ExtractionReview(BaseModel):
    action: Literal["accept", "reject", "edit", "reset"]
    value: Any = None


class BulkReview(BaseModel):
    ids: list[uuid.UUID] | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=1)
    action: Literal["accept", "reject"] = "accept"
    verified_citations_only: bool = True


class ApplyExtractionsIn(BaseModel):
    scenario_id: uuid.UUID | None = None
    update_property: bool = True


# -------------------------------------------------------------- analyst
class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    scenario_id: uuid.UUID | None = None


class ChatMessageOut(ORM):
    id: uuid.UUID
    role: str
    content: str
    model: str | None
    created_at: datetime


ROLES_LIST = list(ROLES)
