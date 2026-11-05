"""Report exports (Excel model, one-pager, IC memo) and the AI Analyst chat."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Iterator

from axiom_engine.scenarios import centered_range, sensitivity_table
from fastapi import APIRouter, Depends
from fastapi.responses import Response, StreamingResponse
from sqlalchemy import select

from ..db import SessionLocal, set_tenant
from ..deps import OrgContext, analyst, viewer
from ..features import require_feature
from ..models import ChatMessage, Property
from ..schemas import ChatIn, ChatMessageOut
from ..services import ai
from ..services.analyst import build_context, rules_answer, verified_fields
from ..services.report_excel import build_workbook
from ..services.report_pdf import ic_memo, one_pager
from ..services.underwriting import calculate, get_scenario
from .scenarios import scenario_comparison

router = APIRouter(tags=["reports"])


def _filename(prop: Property, suffix: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "-", prop.name).strip("-")[:60] or "deal"
    return f"{base}-{suffix}"


def _load(ctx: OrgContext, property_id: uuid.UUID, scenario_id: uuid.UUID | None):
    prop = ctx.get_property(property_id)
    sc = get_scenario(ctx, prop, scenario_id)
    return prop, sc, calculate(sc.assumptions_json, prop.property_type)


def _irr_sensitivity(a: dict) -> dict | None:
    try:
        return sensitivity_table(a, "rent_growth", centered_range(a["rent_growth"], 0.01),
                                 "exit_cap_rate", centered_range(a["exit_cap_rate"], 0.0025), "irr_levered")
    except Exception:  # noqa: BLE001 - extreme shifts may be invalid; omit the table
        return None


@router.get("/properties/{property_id}/reports/excel")
def export_excel(property_id: uuid.UUID, scenario_id: uuid.UUID | None = None, ctx: OrgContext = Depends(viewer)):
    prop, sc, result = _load(ctx, property_id, scenario_id)
    data = build_workbook(prop, sc.name, sc.assumptions_json, result, _irr_sensitivity(sc.assumptions_json))
    ctx.audit("report.excel", "property", prop.id, property_id=prop.id, scenario=sc.name)
    ctx.db.commit()
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(prop, "model.xlsx")}"'})


@router.get("/properties/{property_id}/reports/one-pager")
def export_one_pager(property_id: uuid.UUID, scenario_id: uuid.UUID | None = None,
                     ctx: OrgContext = Depends(viewer)):
    prop, sc, result = _load(ctx, property_id, scenario_id)
    data = one_pager(prop, sc.name, result)
    ctx.audit("report.one_pager", "property", prop.id, property_id=prop.id, scenario=sc.name)
    ctx.db.commit()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(prop, "summary.pdf")}"'})


@router.get("/properties/{property_id}/reports/ic-memo")
def export_ic_memo(property_id: uuid.UUID, scenario_id: uuid.UUID | None = None, ai_narrative: bool = False,
                   ctx: OrgContext = Depends(viewer)):
    require_feature(ctx.org, "ic_memo")
    prop, sc, result = _load(ctx, property_id, scenario_id)
    scenarios = scenario_comparison(property_id, ctx)
    narrative = None
    if ai_narrative and ai.ai_available():
        context = build_context(ctx, prop, sc, result, scenarios)
        narrative = {"executive_summary": ai.draft_narrative(context, "Executive Summary and Investment Thesis"),
                     "risks": ai.draft_narrative(context, "Key Risks and Mitigants")}
    data = ic_memo(prop, sc.name, result, scenarios, _irr_sensitivity(sc.assumptions_json),
                   verified_fields(ctx, prop), narrative)
    ctx.audit("report.ic_memo", "property", prop.id, property_id=prop.id, scenario=sc.name,
              ai_narrative=bool(narrative))
    ctx.db.commit()
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{_filename(prop, "IC-memo.pdf")}"'})


# ----------------------------------------------------------------- analyst
@router.get("/properties/{property_id}/analyst/messages", response_model=list[ChatMessageOut])
def chat_history(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    prop = ctx.get_property(property_id)
    return ctx.db.scalars(select(ChatMessage).where(ChatMessage.property_id == prop.id)
                          .order_by(ChatMessage.created_at).limit(200)).all()


@router.delete("/properties/{property_id}/analyst/messages", status_code=204)
def clear_chat(property_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    prop = ctx.get_property(property_id)
    for m in ctx.db.scalars(select(ChatMessage).where(ChatMessage.property_id == prop.id)):
        ctx.db.delete(m)
    ctx.db.commit()
    return Response(status_code=204)


@router.get("/analyst/status")
def analyst_status(ctx: OrgContext = Depends(viewer)):
    return {"ai_available": ai.ai_available(), "model": ai.model_name() if ai.ai_available() else "axiom-rules"}


@router.post("/properties/{property_id}/analyst/chat")
def chat(property_id: uuid.UUID, body: ChatIn, ctx: OrgContext = Depends(viewer)):
    """Server-sent events stream: {"type":"delta","text":...} … {"type":"done"}."""
    require_feature(ctx.org, "ai_analyst")
    prop, sc, result = _load(ctx, property_id, body.scenario_id)
    context = build_context(ctx, prop, sc, result,
                            [s for s in scenario_comparison(property_id, ctx) if s["scenario_id"] != str(sc.id)])
    history_rows = ctx.db.scalars(select(ChatMessage).where(ChatMessage.property_id == prop.id)
                                  .order_by(ChatMessage.created_at.desc()).limit(12)).all()
    history = [{"role": m.role, "content": m.content} for m in reversed(history_rows)]
    ctx.db.add(ChatMessage(org_id=ctx.org.id, property_id=prop.id, user_id=ctx.user.id, role="user",
                           content=body.message))
    ctx.audit("analyst.question", "property", prop.id, property_id=prop.id, scenario=sc.name)
    ctx.db.commit()
    org_id, user_id, prop_id = ctx.org.id, ctx.user.id, prop.id
    use_ai = ai.ai_available()

    def events() -> Iterator[str]:
        chunks: list[str] = []
        model = ai.model_name() if use_ai else "axiom-rules"
        try:
            if use_ai:
                for text in ai.stream_analyst(context, history, body.message):
                    chunks.append(text)
                    yield f"data: {json.dumps({'type': 'delta', 'text': text})}\n\n"
            else:
                text = rules_answer(context, body.message)
                for i in range(0, len(text), 40):
                    chunks.append(text[i:i + 40])
                    yield f"data: {json.dumps({'type': 'delta', 'text': text[i:i + 40]})}\n\n"
        except Exception as exc:  # noqa: BLE001 - surface a clean error to the client
            msg = f"\n\n_The analyst is unavailable right now ({type(exc).__name__}). Showing rule-based answer:_\n\n"
            fallback = msg + rules_answer(context, body.message)
            chunks.append(fallback)
            model = "axiom-rules"
            yield f"data: {json.dumps({'type': 'delta', 'text': fallback})}\n\n"
        db = SessionLocal()
        set_tenant(db, org_id)
        try:
            msg_row = ChatMessage(org_id=org_id, property_id=prop_id, user_id=user_id, role="assistant",
                                  content="".join(chunks), model=model)
            db.add(msg_row)
            db.commit()
            yield f"data: {json.dumps({'type': 'done', 'message_id': str(msg_row.id), 'model': model})}\n\n"
        finally:
            db.close()

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


