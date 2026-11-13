"""Full underwriting model export (.xlsx) with working, linked formulas.

The workbook re-derives every figure from the Assumptions sheet using Excel
formulas, mirroring the engine's methodology exactly. A "Reconciliation" block
compares each formula result with the engine's stored value so reviewers can
confirm the model ties out.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

NAVY = "0B1F3A"
GOLD = "C9A227"
GREY = "F2F4F7"
INPUT_BLUE = "1F4E9D"

FMT_USD = '_($* #,##0_);_($* (#,##0);_($* "-"??_);_(@_)'
FMT_USD2 = '_($* #,##0.00_);_($* (#,##0.00);_($* "-"??_);_(@_)'
FMT_PCT = "0.00%"
FMT_X = '0.00"x"'
FMT_NUM = "#,##0"

thin = Side(style="thin", color="D0D5DD")
BORDER_BOTTOM = Border(bottom=thin)
TOTAL_BORDER = Border(top=Side(style="thin", color="101828"))


def _header(ws, title: str, subtitle: str, demo: bool) -> None:
    ws["A1"] = title
    ws["A1"].font = Font(name="Calibri", size=16, bold=True, color=NAVY)
    ws["A2"] = subtitle
    ws["A2"].font = Font(size=10, color="667085")
    if demo:
        ws["A3"] = "FOR DEMONSTRATION PURPOSES ONLY – fictional sample data"
        ws["A3"].font = Font(size=10, bold=True, color="B42318")


def _section(ws, row: int, text: str, width: int = 6) -> None:
    for c in range(1, width + 1):
        ws.cell(row=row, column=c).fill = PatternFill("solid", fgColor=NAVY)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = Font(bold=True, color="FFFFFF")


def build_workbook(prop: Any, scenario_name: str, a: dict[str, Any], result: dict[str, Any],
                   sensitivity: dict[str, Any] | None = None) -> bytes:
    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    demo = bool(prop.is_demo)
    n = int(a["hold_period_years"])
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subtitle = f"{prop.name} · {scenario_name} · generated {stamp} · Axiom engine v{result['engine_version']}"

    # ------------------------------------------------------------ Assumptions
    ws = wb.active
    ws.title = "Assumptions"
    _header(ws, "Underwriting Assumptions", subtitle, demo)
    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 18
    ws.column_dimensions["C"].width = 16
    ws.column_dimensions["D"].width = 16
    ws.column_dimensions["E"].width = 18
    ref: dict[str, str] = {}
    loan = a.get("loan") or {}
    pref = a.get("preferred_equity") or {}
    loan_amount = result["metrics"]["loan_amount"]
    rate = (loan.get("index_rate", 0) + loan.get("spread", 0)) if loan.get("rate_type") == "floating" else \
        loan.get("interest_rate", 0)

    rows: list[tuple[str, str, Any, str]] = [
        ("Acquisition", "", None, ""),
        ("purchase_price", "Purchase price", a["purchase_price"], FMT_USD),
        ("closing_costs_pct", "Closing costs (% of price)", a.get("closing_costs_pct", 0), FMT_PCT),
        ("upfront_capex", "Upfront capital expenditures", a.get("upfront_capex", 0), FMT_USD),
        ("hold", "Hold period (years)", n, FMT_NUM),
        ("Revenue", "", None, ""),
        ("other_income", "Other income (Year 1)", a.get("other_income", 0), FMT_USD),
        ("rent_growth", "Rent growth (default, per year)", a.get("rent_growth", 0), FMT_PCT),
        ("other_income_growth", "Other income growth", a.get("other_income_growth", 0), FMT_PCT),
        ("vacancy", "Vacancy rate", a.get("vacancy_rate", 0), FMT_PCT),
        ("credit_loss", "Credit loss rate", a.get("credit_loss_rate", 0), FMT_PCT),
        ("Expenses", "", None, ""),
        ("mgmt_pct", "Management fee (% of EGI)", a.get("management_fee_pct", 0), FMT_PCT),
        ("opex_ratio", "Opex ratio (% of EGI, ratio mode)", a.get("opex_ratio", 0) if a.get("opex_mode") == "ratio"
         else 0, FMT_PCT),
        ("opex_growth", "Expense growth (default)", a.get("opex_growth", 0), FMT_PCT),
        ("capex_reserve", "Capital reserve (Year 1)", a.get("capex_reserve_annual", 0), FMT_USD),
        ("capex_growth", "Capital reserve growth", a.get("capex_growth", 0), FMT_PCT),
        ("Exit & Discounting", "", None, ""),
        ("exit_cap", "Exit cap rate", a["exit_cap_rate"], FMT_PCT),
        ("selling_pct", "Selling costs (% of sale)", a.get("selling_costs_pct", 0), FMT_PCT),
        ("discount_rate", "Discount rate", a["discount_rate"], FMT_PCT),
        ("Financing", "", None, ""),
        ("loan_amount", "Senior loan amount", loan_amount, FMT_USD),
        ("rate", "All-in interest rate", rate, FMT_PCT),
        ("amort", "Amortization (years, 0 = IO)", loan.get("amortization_years", 30) if loan else 0, FMT_NUM),
        ("io_years", "Interest-only period (years)", loan.get("io_years", 0) if loan else 0, "0.00"),
        ("orig_fee", "Origination fee (% of loan)", loan.get("origination_fee_pct", 0) if loan else 0, FMT_PCT),
        ("exit_fee", "Exit fee (% of payoff)", loan.get("exit_fee_pct", 0) if loan else 0, FMT_PCT),
        ("pref_amount", "Preferred equity", pref.get("amount", 0), FMT_USD),
        ("pref_rate", "Preferred current-pay rate", pref.get("pref_rate", 0), FMT_PCT),
        ("pref_accrual", "Preferred accrual rate (paid at exit)", pref.get("accrual_rate", 0), FMT_PCT),
    ]
    r = 5
    for key, label, value, fmt in rows:
        if value is None and label == "":
            r += 1
            _section(ws, r, key, 5)
            r += 1
            continue
        ws.cell(row=r, column=1, value=label)
        c = ws.cell(row=r, column=2, value=value)
        c.number_format = fmt
        c.font = Font(color=INPUT_BLUE)
        ref[key] = f"Assumptions!$B${r}"
        r += 1

    # Revenue build-up
    r += 1
    _section(ws, r, "Revenue build-up (Year 1 Gross Potential Rent)", 5)
    r += 1
    mode = a.get("revenue_mode", "unit_mix")
    if mode == "unit_mix":
        for i, h in enumerate(("Unit type", "Units", "In-place rent / mo", "Market rent / mo", "Annual GPR"), 1):
            ws.cell(row=r, column=i, value=h).font = Font(bold=True)
        r += 1
        first = r
        for u in a.get("unit_mix", []):
            ws.cell(row=r, column=1, value=u["name"])
            ws.cell(row=r, column=2, value=u["units"]).font = Font(color=INPUT_BLUE)
            ws.cell(row=r, column=3, value=u["in_place_rent_monthly"]).number_format = FMT_USD2
            ws.cell(row=r, column=3).font = Font(color=INPUT_BLUE)
            ws.cell(row=r, column=4, value=u.get("market_rent_monthly")).number_format = FMT_USD2
            ws.cell(row=r, column=5, value=f"=B{r}*C{r}*12").number_format = FMT_USD
            r += 1
        last = r - 1
        ws.cell(row=r, column=1, value="Total / GPR (Year 1)").font = Font(bold=True)
        ws.cell(row=r, column=2, value=f"=SUM(B{first}:B{last})")
        gpr_cell = ws.cell(row=r, column=5, value=f"=SUM(E{first}:E{last})")
    elif mode == "per_sf":
        ws.cell(row=r, column=1, value="Rentable SF")
        ws.cell(row=r, column=2, value=a.get("rentable_sf")).number_format = FMT_NUM
        ws.cell(row=r + 1, column=1, value="Rent per SF (annual)")
        ws.cell(row=r + 1, column=2, value=a.get("rent_psf_annual")).number_format = FMT_USD2
        r += 2
        ws.cell(row=r, column=1, value="GPR (Year 1)").font = Font(bold=True)
        gpr_cell = ws.cell(row=r, column=5, value=f"=B{r - 2}*B{r - 1}")
    else:
        ws.cell(row=r, column=1, value="GPR (Year 1, input)").font = Font(bold=True)
        gpr_cell = ws.cell(row=r, column=5, value=a.get("gross_potential_rent", 0))
        gpr_cell.font = Font(color=INPUT_BLUE)
    gpr_cell.number_format = FMT_USD
    gpr_cell.font = Font(bold=True)
    ref["gpr1"] = f"Assumptions!$E${r}"
    r += 2

    # Expense lines
    _section(ws, r, "Operating expense line items (Year 1)", 5)
    r += 1
    expense_refs: list[tuple[str, str, str]] = []
    if a.get("opex_mode", "line_items") == "line_items":
        for i, h in enumerate(("Line item", "Year 1 amount", "Annual growth"), 1):
            ws.cell(row=r, column=i, value=h).font = Font(bold=True)
        r += 1
        for line in a.get("expense_lines", []):
            ws.cell(row=r, column=1, value=line["name"])
            amt = ws.cell(row=r, column=2, value=line["amount_annual"])
            amt.number_format = FMT_USD
            amt.font = Font(color=INPUT_BLUE)
            g = ws.cell(row=r, column=3, value=line["growth"] if line.get("growth") is not None
                        else f"={ref['opex_growth']}")
            g.number_format = FMT_PCT
            expense_refs.append((line["name"], f"Assumptions!$B${r}", f"Assumptions!$C${r}"))
            r += 1
    else:
        ws.cell(row=r, column=1, value="Ratio mode: operating expenses = EGI × opex ratio")
        r += 1
    ws.cell(row=r + 1, column=1, value="Blue = input. Black = formula.").font = Font(italic=True, color="667085")

    # --------------------------------------------------------------- Debt
    wd = wb.create_sheet("Debt")
    _header(wd, "Debt Schedule (monthly)", subtitle, demo)
    heads = ("Month", "Year", "Beginning balance", "Interest", "Principal", "Payment", "Ending balance")
    for i, h in enumerate(heads, 1):
        c = wd.cell(row=5, column=i, value=h)
        c.font = Font(bold=True)
        c.border = BORDER_BOTTOM
        wd.column_dimensions[get_column_letter(i)].width = 18
    wd["I5"] = "Level P&I payment"
    wd["I5"].font = Font(bold=True)
    wd["J5"] = (f"=IF(OR({ref['amort']}=0,{ref['loan_amount']}=0),0,IF({ref['rate']}=0,{ref['loan_amount']}/"
                f"({ref['amort']}*12),PMT({ref['rate']}/12,{ref['amort']}*12,-{ref['loan_amount']})))")
    wd["J5"].number_format = FMT_USD2
    months = n * 12
    for m in range(1, months + 1):
        row = 5 + m
        wd.cell(row=row, column=1, value=m)
        wd.cell(row=row, column=2, value=f"=ROUNDUP(A{row}/12,0)")
        wd.cell(row=row, column=3, value=f"={ref['loan_amount']}" if m == 1 else f"=G{row - 1}")
        wd.cell(row=row, column=4, value=f"=C{row}*{ref['rate']}/12")
        wd.cell(row=row, column=5, value=(f"=IF(OR(A{row}<=ROUND({ref['io_years']}*12,0),{ref['amort']}=0),0,"
                                          f"MIN($J$5-D{row},C{row}))"))
        wd.cell(row=row, column=6, value=f"=D{row}+E{row}")
        wd.cell(row=row, column=7, value=f"=C{row}-E{row}")
        for col in range(3, 8):
            wd.cell(row=row, column=col).number_format = FMT_USD
    debt_last = 5 + months

    # ------------------------------------------------------------ Cash Flow
    wc = wb.create_sheet("Cash Flow")
    _header(wc, "Annual Cash Flow Projection", subtitle, demo)
    wc.column_dimensions["A"].width = 36
    years = n + 1  # final column = forward year for terminal value
    col = lambda y: get_column_letter(1 + y)  # noqa: E731 - year 1 → column B
    for y in range(1, years + 1):
        c = wc.cell(row=5, column=1 + y, value=f"Year {y}" + (" (fwd)" if y == years else ""))
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(horizontal="right")
        wc.column_dimensions[col(y)].width = 15
    wc.cell(row=5, column=1, value="").fill = PatternFill("solid", fgColor=NAVY)

    growth_schedule = a.get("rent_growth_by_year") or []
    R: dict[str, int] = {}
    row = 6

    def line(key: str, label: str, fn, fmt: str = FMT_USD, bold: bool = False, last_year: int | None = None):
        nonlocal row
        R[key] = row
        wc.cell(row=row, column=1, value=label).font = Font(bold=bold)
        for y in range(1, (last_year or years) + 1):
            v = fn(y)
            c = wc.cell(row=row, column=1 + y, value=v)
            c.number_format = fmt
            if bold:
                c.font = Font(bold=True)
                c.border = TOTAL_BORDER
        row += 1

    line("growth", "Rent growth applied", lambda y: None if y == 1 else (
        growth_schedule[y - 2] if y - 2 < len(growth_schedule) else f"={ref['rent_growth']}"), FMT_PCT)
    line("gpr", "Gross potential rent", lambda y: f"={ref['gpr1']}" if y == 1 else
         f"={col(y - 1)}{R['gpr']}*(1+{col(y)}{R['growth']})")
    line("vacancy", "Less: vacancy", lambda y: f"=-{col(y)}{R['gpr']}*{ref['vacancy']}")
    line("credit", "Less: credit loss", lambda y: f"=-{col(y)}{R['gpr']}*{ref['credit_loss']}")
    line("other", "Other income", lambda y: f"={ref['other_income']}" if y == 1 else
         f"={col(y - 1)}{R['other']}*(1+{ref['other_income_growth']})")
    line("egi", "Effective gross income", lambda y: f"=SUM({col(y)}{R['gpr']}:{col(y)}{R['other']})", bold=True)
    first_exp = row
    if expense_refs:
        for i, (name, amt_ref, g_ref) in enumerate(expense_refs):
            line(f"exp{i}", name, lambda y, amt_ref=amt_ref, g_ref=g_ref: f"={amt_ref}*(1+{g_ref})^({y}-1)")
    else:
        line("exp_ratio", "Operating expenses (ratio of EGI)", lambda y: f"={col(y)}{R['egi']}*{ref['opex_ratio']}")
    line("mgmt", "Management fee", lambda y: f"={col(y)}{R['egi']}*{ref['mgmt_pct']}")
    line("opex", "Total operating expenses", lambda y: f"=SUM({col(y)}{first_exp}:{col(y)}{R['mgmt']})", bold=True)
    line("noi", "Net operating income", lambda y: f"={col(y)}{R['egi']}-{col(y)}{R['opex']}", bold=True)
    line("capex", "Capital reserve", lambda y: f"={ref['capex_reserve']}" if y == 1 else
         f"={col(y - 1)}{R['capex']}*(1+{ref['capex_growth']})")
    line("cfbd", "Cash flow before debt service", lambda y: f"={col(y)}{R['noi']}-{col(y)}{R['capex']}", bold=True,
         last_year=n)
    line("ds", "Debt service", lambda y: f"=SUMIF(Debt!$B$6:$B${debt_last},{y},Debt!$F$6:$F${debt_last})",
         last_year=n)
    line("pref", "Preferred equity distribution", lambda y: f"={ref['pref_amount']}*{ref['pref_rate']}", last_year=n)
    line("btcf", "Before-tax cash flow to common equity",
         lambda y: f"={col(y)}{R['cfbd']}-{col(y)}{R['ds']}-{col(y)}{R['pref']}", bold=True, last_year=n)
    line("dscr", "DSCR", lambda y: f"=IFERROR({col(y)}{R['noi']}/{col(y)}{R['ds']},\"n/a\")", FMT_X, last_year=n)
    wc.freeze_panes = "B6"

    # -------------------------------------------------------------- Returns
    wr = wb.create_sheet("Returns")
    _header(wr, "Sources & Uses, Exit and Returns", subtitle, demo)
    wr.column_dimensions["A"].width = 38
    for c in "BCDEFGHIJKLMNOPQRSTUVWXYZ":
        wr.column_dimensions[c].width = 15
    cf = "'Cash Flow'!"
    fwd = col(n + 1)
    items = [
        ("Sources & Uses", None, None),
        ("Purchase price", f"={ref['purchase_price']}", FMT_USD),
        ("Closing costs", f"={ref['purchase_price']}*{ref['closing_costs_pct']}", FMT_USD),
        ("Upfront capex", f"={ref['upfront_capex']}", FMT_USD),
        ("Loan fees", f"={ref['loan_amount']}*{ref['orig_fee']}", FMT_USD),
        ("Total uses", "=SUM(B7:B10)", FMT_USD),
        ("Senior loan", f"={ref['loan_amount']}", FMT_USD),
        ("Preferred equity", f"={ref['pref_amount']}", FMT_USD),
        ("Common equity", "=B11-B12-B13", FMT_USD),
        ("Exit (end of year N)", None, None),
        ("Forward NOI (Year N+1)", f"={cf}{fwd}{R['noi']}", FMT_USD),
        ("Gross sale price", f"=B16/{ref['exit_cap']}", FMT_USD),
        ("Selling costs", f"=B17*{ref['selling_pct']}", FMT_USD),
        ("Net sale proceeds", "=B17-B18", FMT_USD),
        ("Loan payoff", f"=IF({ref['loan_amount']}=0,0,Debt!G{debt_last})", FMT_USD),
        ("Loan exit fee", f"=B20*{ref['exit_fee']}", FMT_USD),
        ("Preferred redemption", f"={ref['pref_amount']}*(1+{ref['pref_accrual']})^{ref['hold']}", FMT_USD),
        ("Net proceeds to common equity", "=B19-B20-B21-B22", FMT_USD),
    ]
    rr = 5
    for label, formula, fmt in items:
        rr += 1
        if formula is None:
            _section(wr, rr, label, 3)
            continue
        wr.cell(row=rr, column=1, value=label)
        c = wr.cell(row=rr, column=2, value=formula)
        c.number_format = fmt
    # rows: 6 header, 7..14 S&U, 15 header, 16..23 exit
    rr = 26
    _section(wr, rr, "Cash flows", n + 2)
    rr += 1
    wr.cell(row=rr, column=1, value="Year").font = Font(bold=True)
    for y in range(0, n + 1):
        wr.cell(row=rr, column=2 + y, value=y).font = Font(bold=True)
    unlev_row, lev_row = rr + 1, rr + 2
    wr.cell(row=unlev_row, column=1, value="Unlevered cash flow")
    wr.cell(row=lev_row, column=1, value="Levered cash flow (common equity)")
    wr.cell(row=unlev_row, column=2, value="=-(B7+B8+B9)")
    wr.cell(row=lev_row, column=2, value="=-B14")
    for y in range(1, n + 1):
        cc = col(y)
        extra_u = "+B19" if y == n else ""
        extra_l = "+B23" if y == n else ""
        wr.cell(row=unlev_row, column=2 + y, value=f"={cf}{cc}{R['cfbd']}{extra_u}")
        wr.cell(row=lev_row, column=2 + y, value=f"={cf}{cc}{R['btcf']}{extra_l}")
    for y in range(0, n + 1):
        wr.cell(row=unlev_row, column=2 + y).number_format = FMT_USD
        wr.cell(row=lev_row, column=2 + y).number_format = FMT_USD
    last_col = get_column_letter(2 + n)
    u_rng = f"B{unlev_row}:{last_col}{unlev_row}"
    l_rng = f"B{lev_row}:{last_col}{lev_row}"
    u_rng1 = f"C{unlev_row}:{last_col}{unlev_row}"
    l_rng1 = f"C{lev_row}:{last_col}{lev_row}"

    m = result["metrics"]
    metrics = [
        ("NOI (Year 1)", f"={cf}B{R['noi']}", m["noi_year1"], FMT_USD),
        ("Going-in cap rate", f"={cf}B{R['noi']}/B7", m["going_in_cap_rate"], FMT_PCT),
        ("Unlevered IRR", f"=IRR({u_rng})", m["irr_unlevered"], FMT_PCT),
        ("Levered IRR", f"=IRR({l_rng})", m["irr_levered"], FMT_PCT),
        ("NPV unlevered @ discount rate", f"=B{unlev_row}+NPV({ref['discount_rate']},{u_rng1})",
         m["npv_unlevered"], FMT_USD),
        ("NPV levered @ discount rate", f"=B{lev_row}+NPV({ref['discount_rate']},{l_rng1})", m["npv_levered"],
         FMT_USD),
        ("Equity multiple (unlevered)", f"=SUM({u_rng1})/-B{unlev_row}", m["equity_multiple_unlevered"], FMT_X),
        ("Equity multiple (levered)", f"=SUM({l_rng1})/B14", m["equity_multiple_levered"], FMT_X),
        ("Cash-on-cash (Year 1)", f"={cf}B{R['btcf']}/B14", m["cash_on_cash_year1"], FMT_PCT),
        ("DSCR (Year 1)", f"=IFERROR({cf}B{R['noi']}/{cf}B{R['ds']},\"n/a\")", m["dscr_year1"], FMT_X),
        ("Debt yield (Year 1)", f"=IFERROR({cf}B{R['noi']}/B12,\"n/a\")", m["debt_yield_year1"], FMT_PCT),
        ("LTV", "=IFERROR(B12/B7,\"n/a\")", m["ltv"], FMT_PCT),
        ("LTC", "=IFERROR(B12/B11,\"n/a\")", m["ltc"], FMT_PCT),
    ]
    rr = lev_row + 2
    _section(wr, rr, "Returns – formula vs. Axiom engine (reconciliation)", 4)
    rr += 1
    for i, h in enumerate(("Metric", "Model (formula)", "Engine (stored)", "Variance"), 1):
        wr.cell(row=rr, column=i, value=h).font = Font(bold=True)
    for label, formula, engine_value, fmt in metrics:
        rr += 1
        wr.cell(row=rr, column=1, value=label)
        f = wr.cell(row=rr, column=2, value=formula)
        f.number_format = fmt
        e = wr.cell(row=rr, column=3, value=engine_value if engine_value is not None else "n/a")
        e.number_format = fmt
        v = wr.cell(row=rr, column=4, value=f"=IFERROR(B{rr}-C{rr},\"\")")
        v.number_format = fmt

    # --------------------------------------------------------- Sensitivity
    if sensitivity:
        wsx = wb.create_sheet("Sensitivity")
        _header(wsx, f"Sensitivity – {sensitivity['metric']}", subtitle + " · values computed by Axiom engine", demo)
        wsx.cell(row=5, column=1, value=f"{sensitivity['row_path']} ↓ / {sensitivity['col_path']} →").font = Font(
            bold=True)
        for j, cv in enumerate(sensitivity["col_values"]):
            c = wsx.cell(row=5, column=2 + j, value=cv)
            c.number_format = FMT_PCT
            c.font = Font(bold=True)
        for i, rv in enumerate(sensitivity["row_values"]):
            c = wsx.cell(row=6 + i, column=1, value=rv)
            c.number_format = FMT_PCT
            c.font = Font(bold=True)
            for j, val in enumerate(sensitivity["grid"][i]):
                cell = wsx.cell(row=6 + i, column=2 + j, value=val)
                cell.number_format = FMT_PCT if "irr" in sensitivity["metric"] or "rate" in sensitivity["metric"] \
                    else FMT_USD
        wsx.column_dimensions["A"].width = 34

    # ---------------------------------------------------------- Audit trace
    wa = wb.create_sheet("Audit Trace")
    _header(wa, "Calculation Audit Trace", subtitle, demo)
    wa.column_dimensions["A"].width = 32
    wa.column_dimensions["B"].width = 60
    wa.column_dimensions["C"].width = 20
    for i, h in enumerate(("Metric", "Formula", "Engine value"), 1):
        wa.cell(row=5, column=i, value=h).font = Font(bold=True)
    for i, t in enumerate(result.get("audit_trace", []), start=6):
        wa.cell(row=i, column=1, value=t["metric"])
        wa.cell(row=i, column=2, value=t["formula"])
        v = t.get("value")
        wa.cell(row=i, column=3, value=v if isinstance(v, (int, float)) else (str(v) if v is not None else "n/a"))
    for ws_ in wb.worksheets:
        ws_.sheet_view.showGridLines = False
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
