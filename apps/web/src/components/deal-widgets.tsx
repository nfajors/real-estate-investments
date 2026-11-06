"use client";

/** Reusable deal-level result widgets (used by Overview and Underwriting). */
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_PROPS, BAR_RADIUS, ChartTooltip, GRID_PROPS, Legend, SERIES } from "@/components/charts";
import { Metric } from "@/components/common";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { isNum, mult, pct, usd, usdShort } from "@/lib/format";
import type { UnderwritingResult } from "@/lib/types";
import { cn } from "@/lib/utils";

export function HeadlineMetrics({ r }: { r: UnderwritingResult }) {
  const m = r.metrics;
  return (
    <div className="@container">
      <div className="grid grid-cols-2 gap-3 @2xl:grid-cols-4 @6xl:grid-cols-8">
      <Metric label="NOI (Y1)" value={usdShort(m.noi_year1)} sub={`Expense ratio ${pct(m.expense_ratio_year1, 1)}`} />
      <Metric label="Going-in cap" value={pct(m.going_in_cap_rate)} sub={`Exit ${pct(m.exit_cap_rate)}`} hint="Year-1 NOI ÷ purchase price." />
      <Metric
        label="Levered IRR"
        value={pct(m.irr_levered)}
        tone={isNum(m.irr_levered) && m.irr_levered < 0 ? "bad" : undefined}
        sub={`Unlevered ${pct(m.irr_unlevered)}`}
        hint="Rate at which NPV of levered (common equity) cash flows is zero."
      />
      <Metric label="Equity multiple" value={mult(m.equity_multiple_levered)} sub={`Profit ${usdShort(m.profit_levered)}`} />
      <Metric label="Cash-on-cash (Y1)" value={pct(m.cash_on_cash_year1)} sub={`Avg ${pct(m.avg_cash_on_cash)}`} />
      <Metric
        label="DSCR (Y1)"
        value={mult(m.dscr_year1)}
        tone={isNum(m.min_dscr) && m.min_dscr < 1.2 ? "warn" : undefined}
        sub={`Min ${mult(m.min_dscr)}`}
        hint="NOI ÷ annual debt service."
      />
      <Metric label="LTV / LTC" value={m.ltv ? pct(m.ltv, 1) : "—"} sub={m.ltc ? `LTC ${pct(m.ltc, 1)}` : "Unlevered"} />
      <Metric label="NPV (levered)" value={usdShort(m.npv_levered)} tone={m.npv_levered < 0 ? "bad" : undefined} sub={`@ ${pct(r.assumptions.discount_rate)} discount`} />
      </div>
    </div>
  );
}

export function CashFlowChart({ r, height = 240 }: { r: UnderwritingResult; height?: number }) {
  const data = r.annual.map((y) => ({ year: `Y${y.year}`, NOI: y.noi, "Cash flow to equity": y.btcf }));
  const levered = r.metrics.loan_amount > 0;
  return (
    <div>
      {levered && (
        <div className="mb-2">
          <Legend
            items={[
              { label: "NOI", color: SERIES[0] },
              { label: "Cash flow to equity", color: SERIES[1] },
            ]}
          />
        </div>
      )}
      <div style={{ height }}>
        <ResponsiveContainer>
          <BarChart data={data} barGap={2} barCategoryGap="25%">
            <CartesianGrid {...GRID_PROPS} />
            <XAxis dataKey="year" {...AXIS_PROPS} />
            <YAxis {...AXIS_PROPS} axisLine={false} width={60} tickFormatter={(v) => usdShort(v)} />
            <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={(v) => usd(v)} />} />
            <Bar dataKey="NOI" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={28} />
            {levered && <Bar dataKey="Cash flow to equity" fill={SERIES[1]} radius={BAR_RADIUS} maxBarSize={28} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function SourcesUses({ r }: { r: UnderwritingResult }) {
  const su = r.sources_and_uses;
  const tot = su.total_uses || 1;
  const uses = [
    ["Purchase price", su.purchase_price],
    ["Closing costs", su.closing_costs],
    ["Upfront capex", su.upfront_capex],
    ["Loan fees", su.loan_fees],
  ] as const;
  const sources = [
    ["Senior loan", su.senior_loan],
    ["Preferred equity", su.preferred_equity],
    ["Common equity", su.common_equity],
  ] as const;
  const block = (title: string, rows: readonly (readonly [string, number])[], total: number) => (
    <div>
      <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{title}</div>
      <dl className="space-y-1.5 text-sm">
        {rows
          .filter(([, v]) => v > 0)
          .map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3">
              <dt className="text-muted-foreground">{k}</dt>
              <dd className="tabular">
                {usd(v)} <span className="text-xs text-muted-foreground">{pct(v / tot, 1)}</span>
              </dd>
            </div>
          ))}
        <div className="flex justify-between gap-3 border-t pt-1.5 font-medium">
          <dt>Total</dt>
          <dd className="tabular">{usd(total)}</dd>
        </div>
      </dl>
    </div>
  );
  return (
    <div className="grid gap-6 sm:grid-cols-2">
      {block("Uses", uses, su.total_uses)}
      {block("Sources", sources, su.total_sources)}
    </div>
  );
}

export function RiskPanel({ r }: { r: UnderwritingResult }) {
  const risk = r.risk;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="text-3xl font-semibold tabular">{Math.round(risk.score)}</div>
        <div>
          <Badge variant={risk.level === "high" ? "danger" : risk.level === "moderate" ? "warning" : "success"}>{risk.level} risk</Badge>
          <div className="mt-0.5 text-xs text-muted-foreground">Screening score, 0 (low) – 100 (high)</div>
        </div>
      </div>
      <ul className="space-y-1.5 text-sm">
        {risk.factors.length === 0 && <li className="text-muted-foreground">No screening flags triggered.</li>}
        {risk.factors.map((f) => (
          <li key={f.factor} className="flex gap-2">
            <span className="mt-0.5 rounded bg-muted px-1.5 text-[11px] font-medium tabular">+{f.points}</span>
            <span>{f.message}</span>
          </li>
        ))}
      </ul>
      {(r.warnings.length > 0 || r.covenant_breaches.length > 0) && (
        <div className="space-y-1.5 border-t pt-3 text-sm">
          {r.warnings.map((w, i) => (
            <div key={i} className="flex gap-2 text-warning">
              <span aria-hidden>▲</span>
              <span>
                <span className="font-medium">Assumption flag:</span> {w.message}
              </span>
            </div>
          ))}
          {r.covenant_breaches.map((b, i) => (
            <div key={i} className="flex gap-2 text-destructive">
              <span aria-hidden>●</span>
              <span>
                Projected {b.covenant.replace("_", " ")} breach in year {b.year}: {b.covenant === "min_dscr" ? mult(b.actual) : pct(b.actual)} vs{" "}
                {b.covenant === "min_dscr" ? mult(b.threshold) : pct(b.threshold)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const CF_ROWS: { key: string; label: string; sign?: -1; strong?: boolean; fmt?: "x" | "pct" }[] = [
  { key: "gross_potential_rent", label: "Gross potential rent" },
  { key: "vacancy_loss", label: "Vacancy", sign: -1 },
  { key: "credit_loss", label: "Credit loss", sign: -1 },
  { key: "other_income", label: "Other income" },
  { key: "effective_gross_income", label: "Effective gross income", strong: true },
  { key: "operating_expenses", label: "Operating expenses", sign: -1 },
  { key: "noi", label: "Net operating income", strong: true },
  { key: "capex_reserve", label: "Capital reserve", sign: -1 },
  { key: "cash_flow_before_debt", label: "Cash flow before debt", strong: true },
  { key: "debt_service", label: "Debt service", sign: -1 },
  { key: "pref_distribution", label: "Preferred distribution", sign: -1 },
  { key: "btcf", label: "Cash flow to equity", strong: true },
  { key: "dscr", label: "DSCR", fmt: "x" },
  { key: "cash_on_cash", label: "Cash-on-cash", fmt: "pct" },
];

export function CashFlowTable({ r, showDetail = false }: { r: UnderwritingResult; showDetail?: boolean }) {
  const years = r.annual;
  const detailKeys = Object.keys(years[0]?.expense_detail ?? {});
  return (
    <Table className="text-xs">
      <THead>
        <TR className="hover:bg-transparent">
          <TH className="sticky left-0 min-w-48 bg-card">($)</TH>
          {years.map((y) => (
            <TH key={y.year} className="text-right">
              Year {y.year}
            </TH>
          ))}
        </TR>
      </THead>
      <TBody>
        {CF_ROWS.flatMap((row) => {
          if (row.key === "pref_distribution" && years.every((y) => !y.pref_distribution)) return [];
          if (row.key === "credit_loss" && years.every((y) => !y.credit_loss)) return [];
          const main = (
            <TR key={row.key} className={cn(row.strong && "bg-muted/40 font-semibold")}>
              <TD className={cn("sticky left-0 bg-card", row.strong && "bg-muted/40")}>{row.label}</TD>
              {years.map((y) => {
                const v = (y as unknown as Record<string, number | null>)[row.key];
                const text =
                  row.fmt === "x" ? mult(v) : row.fmt === "pct" ? pct(v, 1) : isNum(v) ? usd(row.sign ? -v : v) : "—";
                return (
                  <TD key={y.year} className={cn("text-right tabular", isNum(v) && row.sign && v !== 0 && "text-muted-foreground")}>
                    {text}
                  </TD>
                );
              })}
            </TR>
          );
          if (row.key === "operating_expenses" && showDetail) {
            return [
              main,
              ...detailKeys.map((k) => (
                <TR key={`d-${k}`} className="text-muted-foreground">
                  <TD className="sticky left-0 bg-card pl-6">{k}</TD>
                  {years.map((y) => (
                    <TD key={y.year} className="text-right tabular">
                      {usd(-(y.expense_detail[k] ?? 0))}
                    </TD>
                  ))}
                </TR>
              )),
            ];
          }
          return [main];
        })}
      </TBody>
    </Table>
  );
}

export function ExitSummary({ r }: { r: UnderwritingResult }) {
  const e = r.exit;
  const rows: [string, number][] = [
    [`Forward NOI (Y${e.exit_year + 1})`, e.forward_noi],
    [`Gross sale @ ${pct(e.exit_cap_rate)} cap`, e.gross_sale_price],
    ["Selling costs", -e.selling_costs],
    ["Loan payoff", -e.loan_payoff],
    ["Exit fee", -e.loan_exit_fee],
    ["Preferred redemption", -e.pref_redemption],
  ];
  return (
    <dl className="space-y-1.5 text-sm">
      {rows
        .filter(([, v]) => v !== 0)
        .map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3">
            <dt className="text-muted-foreground">{k}</dt>
            <dd className="tabular">{usd(v)}</dd>
          </div>
        ))}
      <div className="flex justify-between gap-3 border-t pt-1.5 font-medium">
        <dt>Net proceeds to equity</dt>
        <dd className="tabular">{usd(e.net_proceeds_to_equity)}</dd>
      </div>
    </dl>
  );
}

export function SectionCard({
  title,
  description,
  children,
  className,
  action,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
}) {
  return (
    <Card className={className}>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>{title}</CardTitle>
          {description && <CardDescription>{description}</CardDescription>}
        </div>
        {action}
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}
