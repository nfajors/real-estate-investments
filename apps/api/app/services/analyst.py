"""Deal context assembly for the AI Analyst, plus a deterministic fallback analyst."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from ..deps import OrgContext
from ..models import Document, ExtractedData, Property, Scenario
from .report_pdf import mult, pct, usd

TRACE_KEYS = ("metric", "formula", "value")


def verified_fields(ctx: OrgContext, prop: Property) -> list[dict[str, Any]]:
    rows = ctx.db.execute(
        select(ExtractedData, Document.name).join(Document, Document.id == ExtractedData.document_id)
        .where(ExtractedData.property_id == prop.id, ExtractedData.status.in_(("accepted", "edited")))
        .order_by(ExtractedData.field_path)
    ).all()
    return [{"field_path": e.field_path, "label": e.label, "value": e.value, "status": e.status,
             "document": name, "source_page": e.source_page, "source_ref": e.source_ref,
             "source_excerpt": e.source_excerpt} for e, name in rows]


def build_context(ctx: OrgContext, prop: Property, scenario: Scenario, result: dict[str, Any],
                  scenarios: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    annual = [{k: round(v, 2) if isinstance(v, float) else v for k, v in row.items() if k != "expense_detail"}
              for row in result["annual"]]
    return {
        "deal": {"name": prop.name, "property_type": prop.property_type, "city": prop.city, "state": prop.state,
                 "status": prop.status, "units": prop.units, "rentable_sf": prop.rentable_sf,
                 "year_built": prop.year_built, "is_demo_data": prop.is_demo, "attributes": prop.attributes},
        "scenario": {"name": scenario.name, "is_base": scenario.is_base, "description": scenario.description},
        "assumptions": result["assumptions"],
        "metrics": result["metrics"],
        "sources_and_uses": result["sources_and_uses"],
        "exit": result["exit"],
        "annual_cash_flows": annual,
        "year1_expense_detail": result["annual"][0]["expense_detail"],
        "risk": result.get("risk"),
        "assumption_warnings": result.get("warnings"),
        "covenant_breaches": result.get("covenant_breaches"),
        "audit_trace": [{k: t.get(k) for k in TRACE_KEYS} for t in result.get("audit_trace", [])],
        "verified_document_data": verified_fields(ctx, prop),
        "other_scenarios": scenarios or [],
        "engine_version": result["engine_version"],
    }


def rules_answer(context: dict[str, Any], question: str) -> str:
    """Template answers drawn only from engine output – used when no AI model is configured."""
    q = question.lower()
    m, a, ex = context["metrics"], context["assumptions"], context["exit"]
    trace = {t["metric"]: t for t in context["audit_trace"]}
    demo = "\n\n_Note: this is fictional demo data._" if context["deal"]["is_demo_data"] else ""
    parts: list[str] = []
    if "irr" in q or "return" in q:
        parts.append(
            f"**Returns.** Levered IRR is **{pct(m['irr_levered'])}** and unlevered IRR is "
            f"**{pct(m['irr_unlevered'])}**. {trace['Levered IRR']['formula']}. The levered flows start with "
            f"{usd(-context['sources_and_uses']['common_equity'])} of common equity and end with "
            f"{usd(ex['net_proceeds_to_equity'])} of net sale proceeds to equity in year {ex['exit_year']}. "
            f"Equity multiple: {mult(m['equity_multiple_levered'])}.")
    if any(k in q for k in ("dscr", "debt", "coverage", "loan", "leverage", "ltv")):
        if m["dscr_year1"] is None:
            parts.append("**Debt.** The scenario is unlevered (no senior loan), so DSCR and debt yield do not apply.")
        else:
            parts.append(
                f"**Debt.** Year-1 DSCR is **{mult(m['dscr_year1'])}** (NOI {usd(m['noi_year1'])} ÷ debt service "
                f"{usd(context['annual_cash_flows'][0]['debt_service'])}); minimum over the hold is "
                f"{mult(m['min_dscr'])}. Debt yield {pct(m['debt_yield_year1'])}, LTV {pct(m['ltv'], 1)}, "
                f"LTC {pct(m['ltc'], 1)}.")
    if "cap" in q:
        spread = (a["exit_cap_rate"] - m["going_in_cap_rate"]) * 10000
        parts.append(
            f"**Cap rates.** Going-in cap rate is {pct(m['going_in_cap_rate'])} (Year-1 NOI ÷ price). Exit cap is "
            f"{pct(a['exit_cap_rate'])}, a {spread:+.0f} bps spread. "
            + ("Exit below entry assumes cap-rate compression – test a higher exit cap."
               if spread < 0 else "Exit above entry builds in a cushion for cap-rate expansion."))
    if any(k in q for k in ("noi", "income", "expense", "opex", "revenue")):
        detail = ", ".join(f"{k} {usd(v)}" for k, v in context["year1_expense_detail"].items())
        parts.append(
            f"**NOI build-up (Year 1).** {trace['Effective Gross Income (Y1)']['formula']} = "
            f"{usd(m['egi_year1'])}; operating expenses {usd(m['opex_year1'])} ({detail}); "
            f"NOI = {usd(m['noi_year1'])}. Expense ratio {pct(m['expense_ratio_year1'], 1)}.")
    if "risk" in q or "concern" in q or "weak" in q:
        risk = context.get("risk") or {}
        items = [f"- {f['message']}" for f in risk.get("factors", [])]
        items += [f"- Assumption flag: {w['message']}" for w in context.get("assumption_warnings") or []]
        parts.append(f"**Risk screen** (score {risk.get('score')} / 100, {risk.get('level')}):\n"
                     + ("\n".join(items) if items else "- No screening flags triggered."))
    if "sensitiv" in q or "stress" in q or "downside" in q:
        parts.append(
            "**Suggested sensitivity ranges** (run them in the Scenarios tab – I don't compute new figures):\n"
            f"- Rent growth {pct(a['rent_growth'] - 0.01)} – {pct(a['rent_growth'] + 0.01)}\n"
            f"- Exit cap {pct(a['exit_cap_rate'] - 0.005)} – {pct(a['exit_cap_rate'] + 0.005)}\n"
            f"- Vacancy {pct(a['vacancy_rate'])} – {pct(a['vacancy_rate'] + 0.03)}\n"
            f"- Expense growth {pct(a['opex_growth'])} – {pct(a['opex_growth'] + 0.01)}")
    if not parts:
        parts.append(
            f"**{context['deal']['name']} – {context['scenario']['name']}.** NOI {usd(m['noi_year1'])}, going-in cap "
            f"{pct(m['going_in_cap_rate'])}, levered IRR {pct(m['irr_levered'])}, equity multiple "
            f"{mult(m['equity_multiple_levered'])}, DSCR {mult(m['dscr_year1'])}.\n\nAsk me about returns, debt "
            "coverage, cap rates, the NOI build-up, risks, or sensitivity ranges.")
    return "\n\n".join(parts) + demo + "\n\n_Rule-based analyst (AI model not configured)._"
