"""Document upload, signed downloads, page viewer data and the human verification workflow."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Response, UploadFile
from fastapi.responses import Response as RawResponse
from sqlalchemy import select

from ..config import get_settings
from ..deps import OrgContext, analyst, viewer
from ..models import Document, DocumentPage, ExtractedData, Scenario, utcnow
from ..schemas import (
    ApplyExtractionsIn,
    BulkReview,
    DocumentOut,
    ExtractionOut,
    ExtractionReview,
    PageOut,
)
from ..security import verify_signed
from ..services.extraction import process_document
from ..services.extraction_fields import FIELDS, apply_to_assumptions, coerce
from ..services.parsing import ALLOWED_TYPES, PDF_TYPES, render_page_png, sniff_mime
from ..services.storage import get_storage
from ..services.underwriting import engine_error, get_scenario, run_and_store

router = APIRouter(tags=["documents"])
DOC_TYPES = ("om", "t12", "rent_roll", "appraisal", "loan_doc", "model", "image", "other")


def _doc(ctx: OrgContext, document_id: uuid.UUID) -> Document:
    doc = ctx.db.get(Document, document_id)
    if doc is None or doc.org_id != ctx.org.id or doc.deleted_at is not None:
        raise HTTPException(404, "Document not found")
    return doc


@router.post("/properties/{property_id}/documents", response_model=DocumentOut, status_code=201)
async def upload_document(
    property_id: uuid.UUID,
    background: BackgroundTasks,
    file: UploadFile = File(...),
    doc_type: str = Form("other"),
    ctx: OrgContext = Depends(analyst),
):
    prop = ctx.get_property(property_id)
    if doc_type not in DOC_TYPES:
        raise HTTPException(422, f"doc_type must be one of {', '.join(DOC_TYPES)}")
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {get_settings().max_upload_mb} MB")
    if not data:
        raise HTTPException(422, "Empty file")
    name = (file.filename or "document").replace("/", "_").replace("\\", "_")[:300]
    mime = sniff_mime(name, file.content_type, data)
    if mime not in ALLOWED_TYPES:
        raise HTTPException(415, "Supported uploads: PDF, Excel (.xlsx/.xlsm), CSV, PNG/JPEG/WebP images")
    doc_id = uuid.uuid4()
    key = f"{ctx.org.id}/{prop.id}/{doc_id}"
    get_storage().put(key, data, mime)
    doc = Document(id=doc_id, org_id=ctx.org.id, property_id=prop.id, name=name,
                   type="image" if mime.startswith("image/") and doc_type == "other" else doc_type,
                   mime_type=mime, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), file_url=key,
                   status="uploaded", uploaded_by=ctx.user.id)
    ctx.db.add(doc)
    ctx.audit("document.upload", "document", doc.id, property_id=prop.id, name=name, size=len(data))
    ctx.db.commit()
    background.add_task(process_document, doc.id, ctx.org.id, ctx.user.id)
    return doc


@router.get("/properties/{property_id}/documents", response_model=list[DocumentOut])
def list_documents(property_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    prop = ctx.get_property(property_id)
    return ctx.db.scalars(select(Document).where(Document.property_id == prop.id, Document.deleted_at.is_(None))
                          .order_by(Document.created_at.desc())).all()


@router.get("/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    return _doc(ctx, document_id)


@router.post("/documents/{document_id}/extract", response_model=DocumentOut)
def reextract(document_id: uuid.UUID, background: BackgroundTasks, rules_only: bool = False,
              ctx: OrgContext = Depends(analyst)):
    doc = _doc(ctx, document_id)
    doc.status = "uploaded"
    ctx.db.commit()
    background.add_task(process_document, doc.id, ctx.org.id, ctx.user.id, rules_only)
    return doc


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(document_id: uuid.UUID, ctx: OrgContext = Depends(analyst)):
    doc = _doc(ctx, document_id)
    doc.deleted_at = utcnow()
    ctx.audit("document.delete", "document", doc.id, property_id=doc.property_id, name=doc.name)
    ctx.db.commit()
    return Response(status_code=204)


@router.get("/documents/{document_id}/url")
def document_url(document_id: uuid.UUID, download: bool = False, ctx: OrgContext = Depends(viewer)):
    doc = _doc(ctx, document_id)
    return {"url": get_storage().signed_url(doc.file_url, doc.name, doc.mime_type, inline=not download),
            "expires_in": get_settings().signed_url_seconds}


@router.get("/documents/{document_id}/pages", response_model=list[PageOut])
def document_pages(document_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    doc = _doc(ctx, document_id)
    pages = ctx.db.scalars(select(DocumentPage).where(DocumentPage.document_id == doc.id)
                           .order_by(DocumentPage.page_number)).all()
    storage = get_storage()
    out = []
    for p in pages:
        image_url = None
        if doc.mime_type in PDF_TYPES:
            image_url = storage.signed_url(f"{doc.file_url}.page{p.page_number}.png", f"page-{p.page_number}.png",
                                           "image/png")
        elif doc.mime_type.startswith("image/"):
            image_url = storage.signed_url(doc.file_url, doc.name, doc.mime_type)
        out.append(PageOut(page_number=p.page_number, label=p.label, text=p.text, width=p.width, height=p.height,
                           image_url=image_url, cells=p.cells))
    if not out and doc.mime_type.startswith("image/"):
        out.append(PageOut(page_number=1, label="Image", text="", width=None, height=None, cells=None,
                           image_url=storage.signed_url(doc.file_url, doc.name, doc.mime_type)))
    return out


@router.get("/files/{token}")
def serve_file(token: str):
    """Serve a stored object via a short-lived HMAC-signed token (no bearer token required)."""
    body = verify_signed(token)
    if body is None:
        raise HTTPException(403, "Link expired or invalid")
    storage = get_storage()
    key: str = body["k"]
    if ".page" in key and key.endswith(".png"):
        if not storage.exists(key):
            base_key, page_part = key.rsplit(".page", 1)
            page_no = int(page_part.removesuffix(".png"))
            png = render_page_png(storage.get(base_key), page_no)
            storage.put(key, png, "image/png")  # cached, encrypted like the source
            data = png
        else:
            data = storage.get(key)
    else:
        data = storage.get(key)
    disposition = "inline" if body.get("in", True) else "attachment"
    safe_name = body.get("fn", "file").replace('"', "")
    return RawResponse(content=data, media_type=body.get("ct", "application/octet-stream"),
                       headers={"Content-Disposition": f'{disposition}; filename="{safe_name}"',
                                "Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


# ----------------------------------------------------------- verification
@router.get("/extraction-fields")
def extraction_fields():
    return FIELDS


@router.get("/documents/{document_id}/extractions", response_model=list[ExtractionOut])
def document_extractions(document_id: uuid.UUID, ctx: OrgContext = Depends(viewer)):
    doc = _doc(ctx, document_id)
    rows = ctx.db.scalars(select(ExtractedData).where(ExtractedData.document_id == doc.id)).all()
    order = list(FIELDS)
    return sorted(rows, key=lambda r: (order.index(r.field_path) if r.field_path in order else 999, -r.version))


@router.get("/properties/{property_id}/extractions", response_model=list[ExtractionOut])
def property_extractions(property_id: uuid.UUID, status: str | None = None, ctx: OrgContext = Depends(viewer)):
    prop = ctx.get_property(property_id)
    q = select(ExtractedData).where(ExtractedData.property_id == prop.id)
    if status:
        q = q.where(ExtractedData.status.in_(status.split(",")))
    return ctx.db.scalars(q.order_by(ExtractedData.field_path, ExtractedData.version.desc())).all()


def _extraction(ctx: OrgContext, extraction_id: uuid.UUID) -> ExtractedData:
    row = ctx.db.get(ExtractedData, extraction_id)
    if row is None or row.org_id != ctx.org.id:
        raise HTTPException(404, "Extraction not found")
    return row


@router.patch("/extractions/{extraction_id}", response_model=ExtractionOut)
def review_extraction(extraction_id: uuid.UUID, body: ExtractionReview, ctx: OrgContext = Depends(analyst)):
    row = _extraction(ctx, extraction_id)
    before = {"status": row.status, "value": row.value}
    if body.action == "accept":
        row.status = "accepted"
    elif body.action == "reject":
        row.status = "rejected"
    elif body.action == "reset":
        row.status = "pending"
        row.value = row.original_value
        row.verified_by = None
        row.verified_at = None
    else:
        try:
            row.value = coerce(row.field_path, body.value)
        except (ValueError, TypeError, KeyError) as exc:
            raise HTTPException(422, f"Invalid value: {exc}") from exc
        row.status = "edited"
    if body.action != "reset":
        row.verified_by = ctx.user.id
        row.verified_at = utcnow()
        if body.action in ("accept", "edit"):
            # Only one verified value per field per property: supersede older verified versions.
            for other in ctx.db.scalars(select(ExtractedData).where(
                    ExtractedData.property_id == row.property_id, ExtractedData.field_path == row.field_path,
                    ExtractedData.id != row.id, ExtractedData.status.in_(("accepted", "edited")))):
                other.status = "superseded"
    ctx.audit(f"extraction.{body.action}", "extracted_data", row.id, property_id=row.property_id,
              field_path=row.field_path, before=before, after={"status": row.status, "value": row.value})
    ctx.db.commit()
    return row


@router.post("/documents/{document_id}/extractions/bulk", response_model=list[ExtractionOut])
def bulk_review(document_id: uuid.UUID, body: BulkReview, ctx: OrgContext = Depends(analyst)):
    doc = _doc(ctx, document_id)
    q = select(ExtractedData).where(ExtractedData.document_id == doc.id, ExtractedData.status == "pending")
    if body.ids:
        q = q.where(ExtractedData.id.in_(body.ids))
    rows = [r for r in ctx.db.scalars(q)
            if (body.min_confidence is None or r.confidence >= body.min_confidence)
            and (not body.verified_citations_only or r.citation_verified)]
    for r in rows:
        review_extraction(r.id, ExtractionReview(action=body.action), ctx)
    return rows


@router.post("/properties/{property_id}/extractions/apply")
def apply_extractions(property_id: uuid.UUID, body: ApplyExtractionsIn, ctx: OrgContext = Depends(analyst)):
    """Push human-verified values into a scenario's assumptions (and deal record). Never unverified ones."""
    prop = ctx.get_property(property_id)
    sc: Scenario = get_scenario(ctx, prop, body.scenario_id)
    rows = ctx.db.scalars(select(ExtractedData).where(ExtractedData.property_id == prop.id,
                                                      ExtractedData.status.in_(("accepted", "edited")))
                          .order_by(ExtractedData.version)).all()
    if not rows:
        raise HTTPException(409, "No verified values to apply. Accept or edit extracted fields first.")
    accepted: dict[str, Any] = {r.field_path: r.value for r in rows}  # latest version wins
    new_assumptions, changes = apply_to_assumptions(sc.assumptions_json, accepted)
    try:
        from axiom_engine import AssumptionError, Assumptions

        Assumptions.from_dict(new_assumptions).validate()
    except AssumptionError as exc:
        raise engine_error(exc) from exc
    sc.assumptions_json = new_assumptions
    if sc.is_base:
        prop.purchase_price = new_assumptions["purchase_price"]
    if body.update_property:
        for path, attr in (("property.units", "units"), ("property.rentable_sf", "rentable_sf"),
                           ("property.year_built", "year_built"), ("property.address", "address"),
                           ("property.city", "city"), ("property.state", "state")):
            if path in accepted and accepted[path] is not None:
                setattr(prop, attr, accepted[path])
    sc.description = "Assumptions include human-verified document data."
    row = run_and_store(ctx, prop, sc)
    ctx.audit("extraction.apply", "scenario", sc.id, property_id=prop.id, fields=sorted(accepted), changes=changes)
    ctx.db.commit()
    return {"scenario_id": str(sc.id), "applied_fields": sorted(accepted), "changes": changes,
            "result_id": str(row.id)}
