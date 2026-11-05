import io
import json
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

import openpyxl
import pytest
from pypdf import PdfReader

from app.services.demo_docs import offering_memorandum_pdf, rent_roll_workbook

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def upload(s, pid, name, data, mime, doc_type="other"):
    r = s.post(f"/api/properties/{pid}/documents", files={"file": (name, data, mime)}, data={"doc_type": doc_type})
    assert r.status_code == 201, r.text
    return r.json()


def test_upload_extract_verify_apply(owner, prop):
    pid = prop["id"]
    om = upload(owner, pid, "om.pdf", offering_memorandum_pdf(), "application/pdf", "om")
    # TestClient runs background tasks before returning → extraction already complete
    doc = owner.get(f"/api/documents/{om['id']}").json()
    assert doc["status"] == "extracted" and doc["page_count"] == 3 and doc["extractor"] == "heuristic-v1"
    rows = owner.get(f"/api/documents/{om['id']}/extractions").json()
    by = {r["field_path"]: r for r in rows}
    assert by["deal.asking_price"]["value"] == 58_500_000
    assert by["deal.asking_price"]["citation_verified"] and by["deal.asking_price"]["source_page"] == 1
    assert by["deal.asking_price"]["source_bbox"]["x0"] < by["deal.asking_price"]["source_bbox"]["x1"]
    assert by["debt.interest_rate"]["value"] == pytest.approx(0.0545)
    assert all(r["status"] == "pending" for r in rows)

    # Applying before any verification is refused
    assert owner.post(f"/api/properties/{pid}/extractions/apply", json={}).status_code == 409

    rr = upload(owner, pid, "rentroll.xlsx", rent_roll_workbook(), XLSX, "rent_roll")
    sheet_rows = owner.get(f"/api/documents/{rr['id']}/extractions").json()
    mix = next(r for r in sheet_rows if r["field_path"] == "revenue.unit_mix")
    assert sum(u["units"] for u in mix["value"]) == 240
    assert mix["source_ref"].startswith("Rent Roll!")

    # Human review: accept, edit, reject
    assert owner.patch(f"/api/extractions/{by['deal.asking_price']['id']}",
                       json={"action": "edit", "value": "57,750,000"}).json()["value"] == 57_750_000
    assert owner.patch(f"/api/extractions/{by['historical.noi']['id']}", json={"action": "reject"}).json()[
        "status"] == "rejected"
    assert owner.patch(f"/api/extractions/{by['debt.interest_rate']['id']}",
                       json={"action": "edit", "value": "250%"}).status_code == 422
    bulk = owner.post(f"/api/documents/{rr['id']}/extractions/bulk", json={"min_confidence": 0.7}).json()
    assert len(bulk) == len(sheet_rows)
    for f in ("debt.loan_amount", "debt.interest_rate", "debt.amortization_years", "debt.term_years",
              "debt.io_years", "capex.upfront_capex"):
        assert owner.patch(f"/api/extractions/{by[f]['id']}", json={"action": "accept"}).status_code == 200

    applied = owner.post(f"/api/properties/{pid}/extractions/apply", json={}).json()
    assert "revenue.unit_mix" in applied["applied_fields"]
    base = owner.get(f"/api/properties/{pid}/scenarios").json()[0]
    a = base["assumptions"]
    assert a["purchase_price"] == 57_750_000
    assert a["revenue_mode"] == "unit_mix" and len(a["unit_mix"]) == 3
    assert a["vacancy_rate"] == pytest.approx(0.05)
    assert a["loan"]["amount"] == 38_000_000 and a["loan"]["io_years"] == 3
    assert {e["name"] for e in a["expense_lines"]} >= {"Real estate taxes", "Payroll", "Management fee"}
    result = owner.get(f"/api/scenarios/{base['id']}/result").json()
    # NOI now reflects the verified T12 expenses and rent roll
    expected_egi = 5_519_040 * (1 - 0.05 - a["credit_loss_rate"]) + 318_000
    assert result["metrics"]["egi_year1"] == pytest.approx(expected_egi)
    assert owner.get(f"/api/properties/{pid}").json()["units"] == 240

    # Re-review: older verified version gets superseded when a newer one is accepted
    pdf_units = by["property.units"]
    owner.patch(f"/api/extractions/{pdf_units['id']}", json={"action": "accept"})
    statuses = {r["status"] for r in owner.get(f"/api/properties/{pid}/extractions").json()
                if r["field_path"] == "property.units"}
    assert "superseded" in statuses
    reset = owner.patch(f"/api/extractions/{pdf_units['id']}", json={"action": "reset"}).json()
    assert reset["status"] == "pending" and reset["verified_by"] is None

    audit = owner.get(f"/api/org/audit?property_id={pid}").json()
    assert {"extraction.edit", "extraction.apply", "document.extract"} <= {x["action"] for x in audit}


def test_signed_urls_pages_and_reextract(owner, prop):
    pid = prop["id"]
    om = upload(owner, pid, "om.pdf", offering_memorandum_pdf(), "application/pdf")
    url = owner.get(f"/api/documents/{om['id']}/url").json()["url"]
    r = owner.c.get(url)  # no auth header – signed link
    assert r.status_code == 200 and r.content[:4] == b"%PDF"
    assert owner.c.get(url[:-3] + "abc").status_code == 403
    pages = owner.get(f"/api/documents/{om['id']}/pages").json()
    assert len(pages) == 3 and "Asking Price" in pages[0]["text"]
    img = owner.c.get(pages[1]["image_url"])
    assert img.status_code == 200 and img.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert owner.post(f"/api/documents/{om['id']}/extract?rules_only=true").status_code == 200
    assert owner.get(f"/api/documents/{om['id']}").json()["status"] == "extracted"
    assert owner.delete(f"/api/documents/{om['id']}").status_code == 204
    assert owner.get(f"/api/documents/{om['id']}").status_code == 404


def test_storage_is_encrypted_at_rest(owner, prop):
    from app.config import get_settings

    upload(owner, prop["id"], "om.pdf", offering_memorandum_pdf(), "application/pdf")
    files = [p for p in Path(get_settings().storage_path).rglob("*") if p.is_file()]
    assert files
    assert all(not f.read_bytes().startswith(b"%PDF") for f in files)


def test_upload_validation_and_image(owner, prop):
    pid = prop["id"]
    bad = owner.post(f"/api/properties/{pid}/documents", files={"file": ("x.exe", b"MZ\x90\x00", "application/x")})
    assert bad.status_code == 415
    empty = owner.post(f"/api/properties/{pid}/documents", files={"file": ("x.pdf", b"", "application/pdf")})
    assert empty.status_code == 422
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    doc = upload(owner, pid, "table.png", png, "image/png")
    d = owner.get(f"/api/documents/{doc['id']}").json()
    assert d["type"] == "image" and "require AI" in (d["error"] or "")
    csv_doc = upload(owner, pid, "t12.csv", b"Line Item,Total\nReal Estate Taxes,250000\nInsurance,90000\n", "text/csv")
    rows = owner.get(f"/api/documents/{csv_doc['id']}/extractions").json()
    assert {r["field_path"]: r["value"] for r in rows}["expenses.real_estate_taxes"] == 250_000


def test_viewer_cannot_upload_or_review(client, owner, prop):
    from conftest import PASSWORD, Session

    inv = owner.post("/api/org/invitations", json={"email": f"viewer.docs-{uuid.uuid4().hex[:8]}@example.com", "role": "viewer"}).json()
    tok = client.post("/api/invitations/accept", json={"token": inv["token"], "name": "V", "password": PASSWORD})
    viewer = Session(client, tok.json()["access_token"], owner.org_id)
    r = viewer.post(f"/api/properties/{prop['id']}/documents", files={"file": ("a.csv", b"a,b\n", "text/csv")})
    assert r.status_code == 403
    assert viewer.get(f"/api/properties/{prop['id']}/reports/one-pager").status_code == 200


# ------------------------------------------------------------------ reports
def test_pdf_reports_with_demo_watermark(demo):
    props = demo.get("/api/properties").json()
    mf = next(p for p in props if p["property_type"] == "multifamily")
    r = demo.get(f"/api/properties/{mf['id']}/reports/one-pager")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "FOR DEMONSTRATION" in text and "Levered IRR" in text
    memo = demo.get(f"/api/properties/{mf['id']}/reports/ic-memo")
    assert memo.status_code == 200
    reader = PdfReader(io.BytesIO(memo.content))
    memo_text = "".join(p.extract_text() for p in reader.pages)
    assert len(reader.pages) >= 3
    for section in ("Executive Summary", "Scenario Analysis", "Sensitivity", "Risk Factors",
                    "Sources & Verification", "Audit Trace", "FOR DEMONSTRATION"):
        assert section in memo_text, section


def test_non_demo_report_has_no_watermark(owner, prop):
    r = owner.get(f"/api/properties/{prop['id']}/reports/one-pager")
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "FOR DEMONSTRATION" not in text


def _excel_values(content: bytes):
    """Recalculate the workbook with LibreOffice (if installed) and read computed values."""
    if not shutil.which("soffice"):
        pytest.skip("LibreOffice not installed – cannot recalculate formulas")
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "model.xlsx"
        src.write_bytes(content)
        out = Path(d) / "out"
        subprocess.run(["soffice", "--headless", "--calc", "--convert-to", "xlsx", "--outdir", str(out), str(src)],
                       check=True, capture_output=True, timeout=120)
        return openpyxl.load_workbook(out / "model.xlsx", data_only=True)


@pytest.mark.parametrize("ptype", ["multifamily", "industrial"])
def test_excel_formulas_reconcile_with_engine(demo, ptype):
    props = demo.get("/api/properties").json()
    p = next(x for x in props if x["property_type"] == ptype)
    r = demo.get(f"/api/properties/{p['id']}/reports/excel")
    assert r.status_code == 200
    wb_formulas = openpyxl.load_workbook(io.BytesIO(r.content))
    assert set(wb_formulas.sheetnames) >= {"Assumptions", "Cash Flow", "Debt", "Returns", "Audit Trace"}
    ws = wb_formulas["Returns"]
    assert any(isinstance(c.value, str) and c.value.startswith("=IRR(") for row in ws.iter_rows() for c in row)
    assert "DEMONSTRATION" in wb_formulas["Assumptions"]["A3"].value

    wb = _excel_values(r.content)
    ws = wb["Returns"]
    checked = 0
    start = next(c.row for c in ws["A"] if c.value == "Metric")
    for row in ws.iter_rows(min_row=start + 1, max_col=4):
        label, model, engine = row[0].value, row[1].value, row[2].value
        if isinstance(model, (int, float)) and isinstance(engine, (int, float)):
            assert model == pytest.approx(engine, rel=1e-6, abs=1e-6), f"{label}: {model} vs {engine}"
            checked += 1
    assert checked >= 10


def test_analyst_rules_stream(demo):
    props = demo.get("/api/properties").json()
    mf = next(p for p in props if p["property_type"] == "multifamily")
    status = demo.get("/api/analyst/status").json()
    assert status["ai_available"] is False
    r = demo.post(f"/api/properties/{mf['id']}/analyst/chat", json={"message": "What are the main risks and DSCR?"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in r.text.splitlines() if line.startswith("data: ")]
    text = "".join(e.get("text", "") for e in events if e["type"] == "delta")
    assert events[-1]["type"] == "done" and events[-1]["model"] == "axiom-rules"
    assert "DSCR" in text and "Risk screen" in text and "fictional demo data" in text
    hist = demo.get(f"/api/properties/{mf['id']}/analyst/messages").json()
    assert [m["role"] for m in hist[-2:]] == ["user", "assistant"]
