"""Feature flags and subscription tiers.

Flags gate incomplete or plan-restricted modules. Resolution order:
platform default → plan entitlement → per-organization override
(``organizations.settings["feature_overrides"]``).
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from .models import Organization

FEATURES: dict[str, dict[str, Any]] = {
    "ai_extraction": {"label": "AI document extraction", "default": True, "phase": 1},
    "ai_analyst": {"label": "AI investment analyst chat", "default": True, "phase": 2},
    "scenarios": {"label": "Scenario manager & sensitivity", "default": True, "phase": 1},
    "monte_carlo": {"label": "Monte Carlo simulation", "default": True, "phase": 2},
    "valuation": {"label": "Valuation reconciliation", "default": True, "phase": 2},
    "financing_compare": {"label": "Financing structure comparison", "default": True, "phase": 2},
    "deal_comparison": {"label": "Multi-deal comparison", "default": True, "phase": 2},
    "ic_memo": {"label": "IC memorandum generator", "default": True, "phase": 2},
    "development": {"label": "Development feasibility (beta)", "default": True, "phase": 3},
    "portfolio_analytics": {"label": "Portfolio analytics", "default": False, "phase": 3},
    "sso": {"label": "Enterprise SSO", "default": False, "phase": 3},
}

PLANS: dict[str, dict[str, Any]] = {
    "starter": {
        "label": "Starter",
        "price_monthly": 0,
        "max_deals": 5,
        "max_members": 2,
        "features": {"ai_extraction", "scenarios"},
    },
    "professional": {
        "label": "Professional",
        "price_monthly": 499,
        "max_deals": 100,
        "max_members": 15,
        "features": {"ai_extraction", "ai_analyst", "scenarios", "monte_carlo", "valuation", "financing_compare",
                     "deal_comparison", "ic_memo", "development"},
    },
    "enterprise": {
        "label": "Enterprise",
        "price_monthly": None,
        "max_deals": None,
        "max_members": None,
        "features": set(FEATURES),
    },
}


def resolve_features(org: Organization) -> dict[str, bool]:
    plan = PLANS.get(org.plan, PLANS["starter"])
    overrides = (org.settings or {}).get("feature_overrides", {})
    out = {}
    for key, meta in FEATURES.items():
        enabled = bool(meta["default"]) and key in plan["features"]
        if key in overrides:
            enabled = bool(overrides[key])
        out[key] = enabled
    return out


def require_feature(org: Organization, key: str) -> None:
    if not resolve_features(org).get(key, False):
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"'{FEATURES[key]['label']}' is not enabled for this workspace (plan: {org.plan})",
        )
