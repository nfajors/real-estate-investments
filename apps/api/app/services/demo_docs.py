"""Generate fictional sample offering documents for the demo multifamily deal.

The figures here are internally consistent with the demo deal so the
extraction → verification → underwriting workflow can be exercised end to end.
Every document is stamped as demonstration material.
"""

from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Font
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

UNIT_TYPES = [
    # name, count, sf, in-place rent, market rent
    ("1BR/1BA", 96, 720, 1585.0, 1650.0),
    ("2BR/2BA", 112, 1040, 2045.0, 2125.0),
    ("3BR/2BA", 32, 1290, 2460.0, 2550.0),
]
VACANT_PER_TYPE = {"1BR/1BA": 5, "2BR/2BA": 5, "3BR/2BA": 2}

T12_LINES = [
    ("Gross Potential Rent", 5_519_040),
    ("Vacancy Loss", -275_952),
    ("Other Income", 318_000),
    ("Real Estate Taxes", 612_000),
    ("Insurance", 168_000),
    ("Utilities", 254_400),
    ("Repairs & Maintenance", 216_000),
    ("Payroll", 408_000),
    ("Management Fee", 166_833),
    ("General & Administrative", 72_000),
    ("Marketing", 38_400),
    ("Contract Services", 96_000),
]


def _stamp(c: canvas.Canvas, w: float, h: float) -> None:
    """Footer stamp (kept clear of body text so extracted citations stay clean)."""
    c.saveState()
    c.setFillColor(colors.HexColor("#B42318"))
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(w / 2, 0.5 * inch, "SAMPLE DOCUMENT – FICTIONAL DATA FOR DEMONSTRATION PURPOSES ONLY")
    c.restoreState()


def offering_memorandum_pdf() -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    w, h = LETTER
    navy = colors.HexColor("#0B1F3A")

    def page_header(title: str) -> None:
        c.setFillColor(navy)
        c.rect(0, h - 0.8 * inch, w, 0.8 * inch, fill=1, stroke=0)
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(0.75 * inch, h - 0.5 * inch, title)
        c.setFillColor(colors.black)

    def lines(y: float, items: list[str], size: int = 11, step: float = 18) -> float:
        c.setFont("Helvetica", size)
        for text in items:
            c.drawString(0.85 * inch, y, text)
            y -= step
        return y

    # Page 1 – cover / investment summary
    page_header("Harbor Point Residences – Offering Memorandum (SAMPLE)")
    y = lines(h - 1.4 * inch, [
        "DEMONSTRATION DOCUMENT – All names and figures are fictional.",
        "",
        "Investment Summary",
        "Property Name: Harbor Point Residences",
        "Address: 1200 Harbor Point Drive, Charlotte, NC 28203",
        "Asking Price: $58,500,000",
        "Total Units: 240",
        "Rentable Square Feet: 222,080",
        "Year Built: 2016",
        "Physical Occupancy: 95.0%",
        "Average In-Place Rent: $1,916 per unit per month",
    ])
    lines(y - 10, [
        "Harbor Point is a 240-unit, Class A garden community with structured parking, a resort-style",
        "pool and a 6,000 SF amenity center. The offering presents a mark-to-market opportunity as",
        "in-place rents trail the competitive set by roughly 4%.",
    ], size=10, step=14)
    _stamp(c, w, h)
    c.showPage()

    # Page 2 – financial summary (T12)
    page_header("Trailing Twelve Month Operating Statement (SAMPLE)")
    y = h - 1.4 * inch
    c.setFont("Helvetica-Bold", 11)
    c.drawString(0.85 * inch, y, "Line Item")
    c.drawRightString(w - 0.85 * inch, y, "T12 Total")
    y -= 20
    c.setFont("Helvetica", 11)
    for label, amount in T12_LINES:
        c.drawString(0.85 * inch, y, label)
        c.drawRightString(w - 0.85 * inch, y, f"${amount:,.0f}" if amount >= 0 else f"(${-amount:,.0f})")
        y -= 18
    total_opex = sum(a for label, a in T12_LINES[3:])
    egi = T12_LINES[0][1] + T12_LINES[1][1] + T12_LINES[2][1]
    c.setFont("Helvetica-Bold", 11)
    for label, amount in (("Total Operating Expenses", total_opex), ("Net Operating Income", egi - total_opex)):
        c.drawString(0.85 * inch, y, label)
        c.drawRightString(w - 0.85 * inch, y, f"${amount:,.0f}")
        y -= 18
    _stamp(c, w, h)
    c.showPage()

    # Page 3 – financing
    page_header("Proposed Financing (SAMPLE)")
    lines(h - 1.4 * inch, [
        "Agency financing quote (indicative, fictional):",
        "Loan Amount: $38,000,000",
        "Interest Rate: 5.45%",
        "Amortization: 30 years",
        "Loan Term: 10 years",
        "Interest-Only Period: 3 years",
        "Renovation Budget: $1,200,000",
    ])
    _stamp(c, w, h)
    c.showPage()
    c.save()
    return buf.getvalue()


def rent_roll_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Rent Roll"
    ws["A1"] = "Harbor Point Residences – Rent Roll (SAMPLE, fictional)"
    ws["A1"].font = Font(bold=True)
    headers = ["Unit", "Unit Type", "Sq Ft", "Status", "Market Rent", "Current Rent"]
    for i, hname in enumerate(headers, 1):
        ws.cell(row=3, column=i, value=hname).font = Font(bold=True)
    r = 4
    n = 100
    for name, count, sf, rent, market in UNIT_TYPES:
        vacant = VACANT_PER_TYPE[name]
        for k in range(count):
            n += 1
            is_vacant = k < vacant
            ws.cell(row=r, column=1, value=f"{n}")
            ws.cell(row=r, column=2, value=name)
            ws.cell(row=r, column=3, value=sf)
            ws.cell(row=r, column=4, value="Vacant" if is_vacant else "Occupied")
            ws.cell(row=r, column=5, value=market)
            ws.cell(row=r, column=6, value=0 if is_vacant else rent)
            r += 1
    ws.cell(row=r + 1, column=1, value="Total")

    t12 = wb.create_sheet("T12")
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    t12.cell(row=1, column=1, value="Line Item").font = Font(bold=True)
    for i, mth in enumerate(months, 2):
        t12.cell(row=1, column=i, value=mth).font = Font(bold=True)
    t12.cell(row=1, column=14, value="Total").font = Font(bold=True)
    for r_idx, (label, amount) in enumerate(T12_LINES, 2):
        t12.cell(row=r_idx, column=1, value=label)
        monthly = round(amount / 12, 2)
        for i in range(12):
            t12.cell(row=r_idx, column=2 + i, value=monthly)
        t12.cell(row=r_idx, column=14, value=amount)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


if __name__ == "__main__":  # pragma: no cover - writes samples for manual upload testing
    import pathlib
    import sys

    out = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "samples")
    out.mkdir(parents=True, exist_ok=True)
    (out / "Harbor-Point-OM-SAMPLE.pdf").write_bytes(offering_memorandum_pdf())
    (out / "Harbor-Point-RentRoll-T12-SAMPLE.xlsx").write_bytes(rent_roll_workbook())
    print(f"Wrote sample documents to {out}/")
