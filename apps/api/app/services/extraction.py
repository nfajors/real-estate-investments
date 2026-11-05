"""Document processing pipeline: parse → extract (AI or rules) → verify citations → store."""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..db import SessionLocal, set_tenant
from ..features import resolve_features
from ..models import AuditLog, Document, DocumentPage, ExtractedData, Organization
from . import ai
from .extract_heuristic import EXTRACTOR_NAME, Candidate, extract
from .extraction_fields import FIELDS, coerce
from .parsing import CSV_TYPES, EXCEL_TYPES, PDF_TYPES, ParsedPage, find_bbox, normalize, parse, render_page_png
from .storage import get_storage

log = logging.getLogger("axiom.extraction")
UNVERIFIED_CONFIDENCE_CAP = 0.35
MAX_RENDERED_PAGES = 80


def _value_in_excerpt(value: Any, excerpt: str) -> bool:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return True
    digits = re.sub(r"[^\d.]", "", excerpt.replace(",", ""))
    forms = {f"{value:.0f}", f"{value:g}", f"{value * 100:g}", f"{value * 100:.1f}", f"{value * 100:.2f}",
             f"{value / 1_000_000:g}", f"{value:.2f}"}
    return any(f and f in digits for f in forms)


def verify_citation(pages: list[ParsedPage], page_no: int | None, excerpt: str) -> tuple[bool, int | None]:
    """True if the excerpt occurs verbatim (whitespace/case-insensitive) in the parsed text."""
    needle = normalize(excerpt)
    if len(needle) < 3:
        return False, page_no
    by_no = {p.page_number: normalize(p.text) for p in pages}
    if page_no in by_no and needle in by_no[page_no]:
        return True, page_no
    for n, text in by_no.items():
        if needle in text:
            return True, n
    return False, page_no


def _ai_candidates(pages: list[ParsedPage], doc: Document, raw: bytes) -> list[dict[str, Any]]:
    out = []
    for f in ai.extract_with_ai(pages, doc.mime_type, raw, doc.name):
        path = f.get("field_path")
        if path not in FIELDS:
            continue
        kind = FIELDS[path]["kind"]
        value = f.get("unit_mix") if kind == "unit_mix" else f.get("value_text") if kind == "text" else f.get(
            "value_number")
        if value is None:
            continue
        try:
            value = coerce(path, value)
        except (ValueError, TypeError, KeyError):
            continue
        excerpt = (f.get("source_excerpt") or "").strip()
        has_text = any(p.text.strip() for p in pages)
        verified, page_no = verify_citation(pages, f.get("source_page"), excerpt) if has_text else (False,
                                                                                                    f.get("source_page"))
        conf = max(0.0, min(1.0, float(f.get("confidence") or 0)))
        if not verified:
            conf = min(conf, UNVERIFIED_CONFIDENCE_CAP)
        elif not _value_in_excerpt(value, excerpt):
            conf *= 0.8
        out.append({"field_path": path, "value": value, "confidence": round(conf, 3), "source_page": page_no,
                    "source_ref": f.get("source_ref"), "source_excerpt": excerpt, "citation_verified": verified,
                    "extractor": f"ai:{ai.model_name()}"})
    return out


def _heuristic_candidates(pages: list[ParsedPage], is_sheet: bool) -> list[dict[str, Any]]:
    out = []
    for c in extract(pages, is_sheet):
        c: Candidate
        verified = True if is_sheet else verify_citation(pages, c.source_page, c.source_excerpt)[0]
        out.append({"field_path": c.field_path, "value": c.value, "confidence": c.confidence,
                    "source_page": c.source_page, "source_ref": c.source_ref, "source_excerpt": c.source_excerpt,
                    "citation_verified": verified, "extractor": EXTRACTOR_NAME})
    return out


def process_document(document_id: uuid.UUID, org_id: uuid.UUID, user_id: uuid.UUID | None,
                     force_heuristic: bool = False) -> None:
    """Background job. Uses its own session bound to the tenant."""
    db: Session = SessionLocal()
    set_tenant(db, org_id)
    try:
        _process(db, document_id, org_id, user_id, force_heuristic)
    except Exception as exc:  # noqa: BLE001 - job boundary: record failure on the document
        log.exception("extraction failed for document %s", document_id)
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error = f"{type(exc).__name__}: {exc}"[:2000]
            db.commit()
    finally:
        db.close()


def _process(db: Session, document_id: uuid.UUID, org_id: uuid.UUID, user_id, force_heuristic: bool) -> None:
    doc = db.get(Document, document_id)
    if doc is None or doc.org_id != org_id:
        return
    org = db.get(Organization, org_id)
    doc.status = "processing"
    doc.error = None
    db.commit()

    raw = get_storage().get(doc.file_url)
    pages = parse(raw, doc.mime_type)
    db.execute(delete(DocumentPage).where(DocumentPage.document_id == doc.id))
    for p in pages:
        db.add(DocumentPage(org_id=org_id, document_id=doc.id, page_number=p.page_number, label=p.label,
                            text=p.text, width=p.width, height=p.height, cells=p.cells))
    doc.page_count = len(pages)
    if doc.mime_type in PDF_TYPES:
        # Pre-render page images for the verification viewer (stored encrypted, served via signed URLs).
        storage = get_storage()
        for p in pages[:MAX_RENDERED_PAGES]:
            try:
                storage.put(f"{doc.file_url}.page{p.page_number}.png", render_page_png(raw, p.page_number),
                            "image/png")
            except Exception:  # noqa: BLE001 - viewer falls back to lazy rendering / text
                log.warning("could not render page %s of %s", p.page_number, doc.id)

    is_sheet = doc.mime_type in EXCEL_TYPES | CSV_TYPES
    use_ai = (not force_heuristic and ai.ai_available() and resolve_features(org).get("ai_extraction", False))
    notes = None
    if use_ai:
        try:
            candidates = _ai_candidates(pages, doc, raw)
            extractor = f"ai:{ai.model_name()}"
        except Exception as exc:  # noqa: BLE001 - degrade gracefully to rules
            log.warning("AI extraction failed (%s); falling back to rules", exc)
            candidates = _heuristic_candidates(pages, is_sheet)
            extractor = EXTRACTOR_NAME
            notes = f"AI extraction unavailable ({type(exc).__name__}); used rule-based extractor."
    elif doc.mime_type.startswith("image/"):
        candidates = []
        extractor = EXTRACTOR_NAME
        notes = "Image tables require AI extraction. Configure ANTHROPIC_API_KEY to enable it."
    else:
        candidates = _heuristic_candidates(pages, is_sheet)
        extractor = EXTRACTOR_NAME

    # Replace this document's unreviewed proposals; reviewed rows are kept for the audit trail.
    db.execute(delete(ExtractedData).where(ExtractedData.document_id == doc.id, ExtractedData.status == "pending"))
    for c in candidates:
        bbox = None
        if doc.mime_type in PDF_TYPES and c["citation_verified"] and c["source_page"]:
            bbox = find_bbox(raw, c["source_page"], c["source_excerpt"])
        prev = db.scalar(select(func.max(ExtractedData.version)).where(
            ExtractedData.property_id == doc.property_id, ExtractedData.field_path == c["field_path"])) or 0
        db.add(ExtractedData(org_id=org_id, document_id=doc.id, property_id=doc.property_id,
                             label=FIELDS[c["field_path"]]["label"], original_value=c["value"],
                             source_bbox=bbox, version=prev + 1, status="pending", **c))
    doc.status = "extracted"
    doc.extractor = extractor
    doc.error = notes
    db.add(AuditLog(org_id=org_id, user_id=user_id, action="document.extract", entity_type="document",
                    entity_id=str(doc.id), property_id=doc.property_id,
                    details={"extractor": extractor, "fields": len(candidates), "pages": len(pages),
                             "name": doc.name}))
    db.commit()
