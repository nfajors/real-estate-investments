"""Deterministic, rule-based extractor.

Used when AI extraction is unavailable (no credentials / disabled) and as a
cross-check. Every candidate carries the exact line or cell it came from, so
citations are always verifiable. Confidence is deliberately modest – a human
must still accept each value.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .extraction_fields import FIELDS
from .parsing import ParsedPage

EXTRACTOR_NAME = "heuristic-v1"


@dataclass
class Candidate:
    field_path: str
    value: Any
    confidence: float
    source_page: int
    source_excerpt: str
    source_ref: str | None = None
    unit: str | None = None


# (field_path, label regex). Order matters: more specific labels first.
LABELS: list[tuple[str, str]] = [
    ("deal.asking_price", r"(asking|offering|list|purchase|guidance)\s+price"),
    ("revenue.gross_potential_rent", r"gross\s+potential\s+(rent|rental\s+income)|gross\s+scheduled\s+rent|\bGPR\b"),
    ("revenue.other_income", r"(total\s+)?other\s+income|ancillary\s+income"),
    ("revenue.vacancy_rate", r"vacancy\s+(rate|factor|allowance)"),
    ("expenses.total_operating_expenses", r"total\s+(operating\s+)?expenses|total\s+opex"),
    ("expenses.real_estate_taxes", r"(real\s+estate|property)\s+tax(es)?"),
    ("expenses.insurance", r"\binsurance\b"),
    ("expenses.utilities", r"\butilities\b"),
    ("expenses.repairs_maintenance", r"repairs?\s*(&|and)\s*maint(enance)?|\bR&M\b"),
    ("expenses.payroll", r"\bpayroll\b|salaries(\s*(&|and)\s*wages)?"),
    ("expenses.management_fee", r"management\s+fees?"),
    ("expenses.general_admin", r"general\s*(&|and)\s*admin(istrative)?|\bG&A\b"),
    ("expenses.marketing", r"\bmarketing\b|\badvertising\b"),
    ("expenses.contract_services", r"contract(ed)?\s+services"),
    ("historical.noi", r"net\s+operating\s+income|\bNOI\b"),
    ("debt.loan_amount", r"(proposed\s+|senior\s+)?loan\s+(amount|proceeds)"),
    ("debt.interest_rate", r"interest\s+rate|note\s+rate|\bcoupon\b"),
    ("debt.amortization_years", r"amortization"),
    ("debt.io_years", r"interest[\s-]+only(\s+period)?"),
    ("debt.term_years", r"(loan\s+)?term(?!inal)"),
    ("capex.upfront_capex", r"(renovation|capital\s+improvements?|value[\s-]add|capex)\s+(budget|plan|program)"),
    ("capex.reserve_per_unit", r"replacement\s+reserves?\s*(\(|per|/)\s*unit"),
    ("property.year_built", r"year\s+built|built\s+in"),
    ("property.units", r"(total\s+|number\s+of\s+)?(apartment\s+)?units\b|unit\s+count"),
    ("property.rentable_sf", r"(net\s+)?rentable\s+(area|square\s+feet|sf)|\bNRA\b|\bGLA\b|building\s+size"),
    ("property.occupancy", r"(physical\s+|economic\s+|current\s+)?occupancy|%\s*leased|percent\s+leased"),
]
COMPILED = [(f, re.compile(p, re.I)) for f, p in LABELS]

NUMBER = re.compile(r"(\()?\$?\s*(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?)\s*(\))?\s*(%|mm\b|m\b|million\b|k\b|years?\b|yrs?\b|months?\b|mos?\b)?",
                    re.I)


def _numbers(text: str) -> list[tuple[float, str, str]]:
    out = []
    for m in NUMBER.finditer(text):
        raw = m.group(2).replace(",", "")
        try:
            v = float(raw)
        except ValueError:  # pragma: no cover - regex guarantees numeric
            continue
        if m.group(1) and m.group(3):
            v = -v
        suffix = (m.group(4) or "").lower()
        if suffix in ("mm", "m", "million"):
            v *= 1_000_000
        elif suffix == "k":
            v *= 1_000
        out.append((v, suffix, m.group(0)))
    return out


def _pick(field_path: str, nums: list[tuple[float, str, str]]) -> float | None:
    kind = FIELDS[field_path]["kind"]
    if not nums:
        return None
    if kind == "percent":
        pct = [v for v, s, _ in nums if s == "%"]
        if pct:
            return pct[0] / 100.0
        small = [v for v, _, _ in nums if 0 < v <= 1]
        return small[0] if small else None
    if kind == "years":
        for v, s, _ in nums:
            if s.startswith("month") or s.startswith("mo"):
                return v / 12.0
            if 0 < v <= 40:
                return v
        return None
    if kind == "integer":
        if field_path == "property.year_built":
            years = [v for v, _, _ in nums if 1800 <= v <= 2100]
            return years[0] if years else None
        ints = [v for v, s, _ in nums if v > 0 and s != "%" and float(v).is_integer()]
        return ints[0] if ints else None
    values = [v for v, s, _ in nums if s not in ("%",) and not (s.startswith("year") or s.startswith("yr"))]
    values = [v for v in values if not (1900 <= v <= 2100 and float(v).is_integer() and len(values) > 1)]
    if not values:
        return None
    # T12 / OM rows list monthly or per-unit figures alongside the annual total: take the largest.
    return max(values, key=abs)


def extract_text_pages(pages: list[ParsedPage]) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    for page in pages:
        for line in page.text.splitlines():
            stripped = line.strip()
            if not stripped or len(stripped) > 400:
                continue
            for field_path, rx in COMPILED:
                m = rx.search(stripped)
                if not m:
                    continue
                # "120 Units" (number before label) or "Units: 120" (after label)
                after = stripped[m.end():]
                nums = _numbers(after)
                if not nums and field_path == "property.units":
                    nums = _numbers(stripped[: m.start()])[-1:]
                value = _pick(field_path, nums)
                if value is None:
                    continue
                if FIELDS[field_path]["kind"] == "integer":
                    value = int(value)
                conf = 0.72 if m.start() < 3 else 0.6
                if field_path not in found or found[field_path].confidence < conf:
                    found[field_path] = Candidate(field_path, value, conf, page.page_number, stripped)
                break  # one field per line
    return list(found.values())


# ---------------------------------------------------------------- sheets
RENT_ROLL_HEADERS = {
    "unit": re.compile(r"^(unit|unit\s*#|unit\s*no\.?|apt|suite)$", re.I),
    "type": re.compile(r"(unit\s*type|floor\s*plan|type|bed|plan)", re.I),
    "sf": re.compile(r"(sq\.?\s*ft|sf|square\s*feet|size)", re.I),
    "rent": re.compile(r"(in[\s-]*place\s+rent|current\s+rent|contract\s+rent|actual\s+rent|^rent$|lease\s+rent)", re.I),
    "market": re.compile(r"(market\s+rent|asking\s+rent)", re.I),
    "status": re.compile(r"(status|occupancy|occupied|vacant)", re.I),
}


def _rent_roll(page: ParsedPage) -> list[Candidate]:
    rows = page.rows
    for h_idx, row in enumerate(rows[:20]):
        cols: dict[str, str] = {}
        for ref, v in row:
            if not isinstance(v, str):
                continue
            col = re.sub(r"\d+", "", ref)
            for key, rx in RENT_ROLL_HEADERS.items():
                if key not in cols and rx.search(v) and not (key == "type" and "unit" in cols and
                                                             cols["unit"] == col):
                    if key == "rent" and RENT_ROLL_HEADERS["market"].search(v):
                        continue
                    cols[key] = col
                    break
        if "unit" in cols and "rent" in cols:
            break
    else:
        return []
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    first_ref = last_ref = None
    total = occupied = 0
    for row in rows[h_idx + 1:]:
        vals = {re.sub(r"\d+", "", ref): (ref, v) for ref, v in row}
        if cols["unit"] not in vals:
            if total:
                break
            continue
        unit_label = str(vals[cols["unit"]][1])
        if re.search(r"total|summary|average", unit_label, re.I):
            break
        rent = vals.get(cols["rent"], (None, 0))[1]
        rent = float(rent) if isinstance(rent, (int, float)) else 0.0
        status = str(vals.get(cols.get("status", ""), (None, ""))[1]).lower()
        is_vacant = "vacant" in status or rent <= 0
        unit_type = str(vals.get(cols.get("type", ""), (None, "All units"))[1])
        market = vals.get(cols.get("market", ""), (None, None))[1]
        sf = vals.get(cols.get("sf", ""), (None, None))[1]
        groups[unit_type].append({"rent": rent, "vacant": is_vacant,
                                  "market": float(market) if isinstance(market, (int, float)) else None,
                                  "sf": float(sf) if isinstance(sf, (int, float)) else None})
        total += 1
        occupied += 0 if is_vacant else 1
        first_ref = first_ref or vals[cols["unit"]][0]
        last_ref = row[-1][0]
    if total == 0:
        return []
    mix = []
    for name, units in groups.items():
        rents = [u["rent"] for u in units if not u["vacant"]]
        markets = [u["market"] for u in units if u["market"]]
        sfs = [u["sf"] for u in units if u["sf"]]
        in_place = sum(rents) / len(rents) if rents else (sum(markets) / len(markets) if markets else 0.0)
        mix.append({"name": name, "units": len(units), "in_place_rent_monthly": round(in_place, 2),
                    "market_rent_monthly": round(sum(markets) / len(markets), 2) if markets else None,
                    "sf_per_unit": round(sum(sfs) / len(sfs), 1) if sfs else None})
    ref = f"{page.label}!{first_ref}:{last_ref}"
    excerpt = f"Rent roll on sheet '{page.label}': {total} units in {len(mix)} unit types, {occupied} occupied"
    return [
        Candidate("revenue.unit_mix", mix, 0.8, page.page_number, excerpt, ref),
        Candidate("property.units", total, 0.85, page.page_number, excerpt, ref),
        Candidate("property.occupancy", round(occupied / total, 4), 0.8, page.page_number, excerpt, ref),
    ]


def extract_sheet_pages(pages: list[ParsedPage]) -> list[Candidate]:
    found: dict[str, Candidate] = {}
    for page in pages:
        for c in _rent_roll(page):
            found.setdefault(c.field_path, c)
        for row in page.rows:
            labels = [(ref, v) for ref, v in row if isinstance(v, str)]
            nums = [(ref, float(v)) for ref, v in row if isinstance(v, (int, float)) and not isinstance(v, bool)]
            if not labels or not nums:
                continue
            label_ref, label = labels[0]
            for field_path, rx in COMPILED:
                if not rx.search(label):
                    continue
                kind = FIELDS[field_path]["kind"]
                if kind == "currency" and len(nums) == 12:
                    value = sum(v for _, v in nums)
                    ref = f"{page.label}!{nums[0][0]}:{nums[-1][0]}"
                    note = " (sum of 12 monthly columns)"
                else:
                    ref_v = nums[-1] if kind == "currency" else nums[0]
                    value = ref_v[1]
                    ref = f"{page.label}!{ref_v[0]}"
                    note = ""
                if kind == "percent" and value > 1:
                    value /= 100.0
                if kind == "integer":
                    value = int(round(value))
                excerpt = f"{label}: {value:,.2f}{note}" if kind != "percent" else f"{label}: {value:.2%}"
                cand = Candidate(field_path, value, 0.75, page.page_number, excerpt, ref)
                if field_path not in found:
                    found[field_path] = cand
                break
    return list(found.values())


def extract(pages: list[ParsedPage], is_sheet: bool) -> list[Candidate]:
    return extract_sheet_pages(pages) if is_sheet else extract_text_pages(pages)
