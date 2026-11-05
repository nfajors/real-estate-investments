"""Claude integration: structured document extraction and the deal-scoped analyst.

Design rules (PRD §9):
* The model proposes values; it never computes the financials. All numbers in
  analyst answers come from the deterministic engine output passed in context.
* Extraction must cite a verbatim excerpt; citations are verified against the
  parsed document text server-side and unverifiable values are down-weighted.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from collections.abc import Iterator
from typing import Any

from ..config import get_settings
from .extraction_fields import FIELDS
from .parsing import ParsedPage

log = logging.getLogger("axiom.ai")

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def ai_available() -> bool:
    s = get_settings()
    if not s.ai_enabled:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def _client():
    import anthropic

    return anthropic.Anthropic()


def model_name() -> str:
    return get_settings().ai_model


# ----------------------------------------------------------------- extraction
EXTRACTION_SYSTEM = """You extract underwriting data from commercial real estate documents \
(offering memoranda, T12 operating statements, rent rolls, appraisals, loan term sheets).

Rules:
- Only report values that are explicitly stated in the document. Never estimate, infer, compute or \
round values. If a field is not stated, omit it.
- Annual figures only for income/expense lines. If a T12 lists monthly columns and a total, use the total.
- Percentages as decimals (5.25% -> 0.0525). Currency as plain numbers in dollars.
- source_excerpt MUST be a short verbatim quote (copied character-for-character) from the page that \
contains the value. source_page is the page number shown in the [Page N] marker. For spreadsheets, \
also give source_ref as Sheet!Cell.
- confidence (0-1) reflects how unambiguous the value is in the source.
- For rent rolls, aggregate units by unit type into unit_mix (count, average in-place monthly rent of \
occupied units, average market rent if given, average SF if given) and use field revenue.unit_mix."""


def _schema() -> dict[str, Any]:
    unit = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "units": {"type": "integer"},
            "in_place_rent_monthly": {"type": "number"},
            "market_rent_monthly": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "sf_per_unit": {"anyOf": [{"type": "number"}, {"type": "null"}]},
        },
        "required": ["name", "units", "in_place_rent_monthly", "market_rent_monthly", "sf_per_unit"],
        "additionalProperties": False,
    }
    item = {
        "type": "object",
        "properties": {
            "field_path": {"type": "string", "enum": list(FIELDS)},
            "value_number": {"anyOf": [{"type": "number"}, {"type": "null"}]},
            "value_text": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "unit_mix": {"anyOf": [{"type": "array", "items": unit}, {"type": "null"}]},
            "confidence": {"type": "number"},
            "source_page": {"type": "integer"},
            "source_ref": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "source_excerpt": {"type": "string"},
        },
        "required": ["field_path", "value_number", "value_text", "unit_mix", "confidence", "source_page",
                     "source_ref", "source_excerpt"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"fields": {"type": "array", "items": item}},
        "required": ["fields"],
        "additionalProperties": False,
    }


def _field_guide() -> str:
    return "\n".join(f"- {k}: {v['label']} ({v['kind']})" for k, v in FIELDS.items())


def extract_with_ai(pages: list[ParsedPage], mime: str, raw: bytes, doc_name: str) -> list[dict[str, Any]]:
    """Return raw field proposals from Claude (validated/verified by the caller)."""
    content: list[dict[str, Any]] = []
    has_text = any(p.text.strip() for p in pages)
    if mime.startswith("image/"):
        content.append({"type": "image", "source": {"type": "base64", "media_type": mime,
                                                    "data": base64.b64encode(raw).decode()}})
    elif mime == "application/pdf" and not has_text:
        # Scanned PDF: let the model read the pages directly.
        content.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf",
                                                       "data": base64.b64encode(raw).decode()}})
    else:
        body = "\n\n".join(
            f"[Page {p.page_number}{' – sheet ' + p.label if p.label else ''}]\n{p.text}" for p in pages)
        content.append({"type": "text", "text": f"<document name=\"{doc_name}\">\n{body}\n</document>"})
    content.append({"type": "text", "text": "Extract every available field from this document. Field catalogue:\n"
                                            + _field_guide()})
    client = _client()
    with client.beta.messages.stream(
        model=model_name(),
        max_tokens=32000,
        system=EXTRACTION_SYSTEM,
        messages=[{"role": "user", "content": content}],
        output_config={"effort": get_settings().ai_effort, "format": {"type": "json_schema", "schema": _schema()}},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    ) as stream:
        message = stream.get_final_message()
    if message.stop_reason == "refusal":
        raise RuntimeError("The model declined to process this document")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("Extraction output was truncated; split the document and retry")
    text = next((b.text for b in message.content if b.type == "text"), "")
    data = json.loads(text)
    return data.get("fields", [])


# -------------------------------------------------------------------- analyst
ANALYST_SYSTEM = """You are Axiom's AI Investment Analyst, embedded in an institutional commercial real \
estate underwriting platform. You are scoped to ONE deal, described in the <deal_context> block.

Non-negotiable rules:
1. Every number you state must appear in <deal_context> (calculated engine output, assumptions, \
verified extracted data, or risk factors). Never compute new financial figures, never estimate, never \
invent market data or comps. If the user asks for a number that is not in context, say it is not \
available and explain how to obtain it in Axiom (e.g. run a sensitivity table or scenario).
2. When explaining a calculation, quote the formula from the audit trace and the inputs used.
3. Distinguish clearly between verified data (from documents a human accepted), user assumptions, \
template defaults, and engine outputs.
4. For risks, reference specific figures (e.g. expense ratio, DSCR, exit vs going-in cap) and suggest \
sensitivity ranges to test rather than asserting outcomes.
5. Be concise and professional, in the register of an investment committee memo. Use short paragraphs \
or bullets. You may draft narrative sections when asked, marking them as drafts for human review.
6. If the deal is marked as demo data, remind the user that figures are fictional when relevant."""


def stream_analyst(context: dict[str, Any], history: list[dict[str, str]], question: str) -> Iterator[str]:
    client = _client()
    system = [{"type": "text", "text": ANALYST_SYSTEM},
              {"type": "text", "text": "<deal_context>\n" + json.dumps(context, default=str, indent=1)
               + "\n</deal_context>", "cache_control": {"type": "ephemeral"}}]
    messages = [*history, {"role": "user", "content": question}]
    with client.beta.messages.stream(
        model=model_name(),
        max_tokens=16000,
        system=system,
        messages=messages,
        output_config={"effort": "low"},
        betas=[FALLBACK_BETA],
        fallbacks="default",
    ) as stream:
        for text in stream.text_stream:
            yield text
        final = stream.get_final_message()
    if final.stop_reason == "refusal":
        yield "\n\n_The model declined to answer this request._"


def draft_narrative(context: dict[str, Any], section: str) -> str:
    """Draft an IC-memo narrative section strictly from the supplied context."""
    chunks = list(stream_analyst(context, [], f"Draft the '{section}' section of an investment committee "
                                                 "memorandum for this deal in 120-180 words. Use only figures in "
                                                 "the deal context. Plain prose, no headings."))
    return "".join(chunks).strip()
