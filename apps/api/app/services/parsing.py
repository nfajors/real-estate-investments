"""Document parsing: PDFs and spreadsheets to page text (+ cell grids), highlights, page images."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Any

PDF_TYPES = {"application/pdf"}
EXCEL_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel.sheet.macroEnabled.12",
}
CSV_TYPES = {"text/csv", "application/csv"}
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}
ALLOWED_TYPES = PDF_TYPES | EXCEL_TYPES | CSV_TYPES | IMAGE_TYPES

EXTENSION_TYPES = {
    ".pdf": "application/pdf",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xlsm": "application/vnd.ms-excel.sheet.macroEnabled.12",
    ".csv": "text/csv",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


@dataclass
class ParsedPage:
    page_number: int
    text: str
    label: str | None = None
    width: float | None = None
    height: float | None = None
    cells: list[list[Any]] | None = None  # [[ref, value], ...]
    rows: list[list[tuple[str, Any]]] = field(default_factory=list)  # spreadsheet rows of (ref, value)


def sniff_mime(filename: str, declared: str | None, data: bytes) -> str:
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if data[:2] == b"PK" and ext in (".xlsx", ".xlsm"):
        return EXTENSION_TYPES[ext]
    if ext == ".csv":
        return "text/csv"
    return declared or "application/octet-stream"


def parse(data: bytes, mime: str) -> list[ParsedPage]:
    if mime in PDF_TYPES:
        return _parse_pdf(data)
    if mime in EXCEL_TYPES:
        return _parse_xlsx(data)
    if mime in CSV_TYPES:
        return _parse_csv(data)
    if mime in IMAGE_TYPES:
        return [ParsedPage(page_number=1, text="", label="Image")]
    raise ValueError(f"Unsupported file type: {mime}")


def _parse_pdf(data: bytes) -> list[ParsedPage]:
    import pdfplumber

    pages = []
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            pages.append(ParsedPage(page_number=i, text=text, width=float(page.width), height=float(page.height)))
    return pages


def _col_letter(idx: int) -> str:
    s = ""
    idx += 1
    while idx:
        idx, rem = divmod(idx - 1, 26)
        s = chr(65 + rem) + s
    return s


def _rows_to_page(n: int, label: str, rows: list[list[tuple[str, Any]]]) -> ParsedPage:
    lines = []
    cells = []
    for row in rows:
        if not row:
            continue
        r_num = re.sub(r"[A-Z]+", "", row[0][0])
        lines.append(f"R{r_num}: " + " | ".join(f"{ref}={_fmt(v)}" for ref, v in row))
        cells.extend([[ref, v] for ref, v in row])
    return ParsedPage(page_number=n, text="\n".join(lines), label=label, cells=cells, rows=rows)


def _fmt(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6g}" if abs(v) < 1 else f"{v:,.2f}".rstrip("0").rstrip(".")
    return str(v)


def _parse_xlsx(data: bytes) -> list[ParsedPage]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    pages = []
    for n, ws in enumerate(wb.worksheets, start=1):
        rows: list[list[tuple[str, Any]]] = []
        for r_idx, row in enumerate(ws.iter_rows(values_only=True), start=1):
            if r_idx > 5000:
                break
            cells = []
            for c_idx, v in enumerate(row):
                if v is None or (isinstance(v, str) and not v.strip()):
                    continue
                if hasattr(v, "isoformat"):
                    v = v.isoformat()
                cells.append((f"{_col_letter(c_idx)}{r_idx}", v.strip() if isinstance(v, str) else v))
            rows.append(cells)
        pages.append(_rows_to_page(n, ws.title, rows))
    wb.close()
    return pages


def _parse_csv(data: bytes) -> list[ParsedPage]:
    text = data.decode("utf-8-sig", errors="replace")
    rows = []
    for r_idx, row in enumerate(csv.reader(io.StringIO(text)), start=1):
        cells = []
        for c_idx, v in enumerate(row):
            v = v.strip()
            if not v:
                continue
            num = _maybe_number(v)
            cells.append((f"{_col_letter(c_idx)}{r_idx}", num if num is not None else v))
        rows.append(cells)
    return [_rows_to_page(1, "CSV", rows)]


def _maybe_number(v: str) -> float | None:
    s = v.replace(",", "").replace("$", "").strip()
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    try:
        f = float(s)
    except ValueError:
        return None
    return -f if neg else f


# ------------------------------------------------------------- highlights
def normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def find_bbox(pdf_bytes: bytes, page_number: int, excerpt: str) -> dict[str, float] | None:
    """Locate an excerpt on a PDF page; returns a normalised (0–1) bounding box."""
    if not excerpt:
        return None
    import pdfplumber

    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if not 1 <= page_number <= len(pdf.pages):
            return None
        page = pdf.pages[page_number - 1]
        words = excerpt.strip().split()
        # Try the full excerpt, then progressively shorter prefixes.
        for n in (len(words), 8, 5, 3):
            if n > len(words) or n <= 0:
                continue
            candidate = " ".join(words[:n])
            try:
                hits = page.search(candidate, regex=False, case=False)
            except Exception:
                hits = []
            if hits:
                h = hits[0]
                return {"x0": h["x0"] / page.width, "top": h["top"] / page.height,
                        "x1": h["x1"] / page.width, "bottom": h["bottom"] / page.height}
    return None


def render_page_png(pdf_bytes: bytes, page_number: int, scale: float = 1.6) -> bytes:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        if not 1 <= page_number <= len(pdf):
            raise ValueError("Page out of range")
        bitmap = pdf[page_number - 1].render(scale=scale)
        img = bitmap.to_pil()
        buf = io.BytesIO()
        img.save(buf, format="PNG", optimize=True)
        return buf.getvalue()
    finally:
        pdf.close()
