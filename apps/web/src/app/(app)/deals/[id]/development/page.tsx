"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RotateCcw, Save } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { AXIS_PROPS, ChartTooltip, GRID_PROPS, SERIES } from "@/components/charts";
import { Callout, ErrorBlock, LoadingBlock, Metric } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Table,
  TBody,
  TD,
  TR,
} from "@/components/ui/primitives";
import { useFeature, useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { isNum, mult, num, pct, usd, usdShort } from "@/lib/format";
import type { Property, Scenario } from "@/lib/types";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ types
interface DevInputs {
  land_cost: number;
  hard_costs: number;
  soft_costs_pct: number;
  contingency_pct: number;
  construction_months: number;
  lease_up_months: number;
  stabilized_noi: number;
  exit_cap_rate: number;
  selling_costs_pct: number;
  loan_to_cost: number;
  construction_rate: number;
  loan_fee_pct: number;
}

interface DevResult {
  inputs: DevInputs;
  budget: {
    land: number;
    hard_costs: number;
    soft_costs: number;
    contingency: number;
    loan_fees: number;
    interest_reserve: number;
    total_cost: number;
  };
  capital: { construction_loan: number; equity: number; loan_balance_at_exit: number };
  returns: {
    yield_on_cost: number;
    development_spread_bps: number;
    stabilized_value: number;
    profit: number;
    profit_margin: number | null;
    irr: number | null;
    equity_multiple: number | null;
  };
  monthly_equity_cash_flows: number[];
}

type Kind = "usd" | "pct" | "months";
const FIELDS: { key: keyof DevInputs; label: string; kind: Kind; hint?: string; group: "cost" | "timing" | "exit" | "debt" }[] = [
  { key: "land_cost", label: "Land cost", kind: "usd", group: "cost" },
  { key: "hard_costs", label: "Hard costs", kind: "usd", group: "cost" },
  { key: "soft_costs_pct", label: "Soft costs", kind: "pct", hint: "% of hard costs", group: "cost" },
  { key: "contingency_pct", label: "Contingency", kind: "pct", hint: "% of hard + soft", group: "cost" },
  { key: "construction_months", label: "Construction period", kind: "months", group: "timing" },
  { key: "lease_up_months", label: "Lease-up period", kind: "months", group: "timing" },
  { key: "stabilized_noi", label: "Stabilized NOI", kind: "usd", hint: "Annual", group: "exit" },
  { key: "exit_cap_rate", label: "Exit cap rate", kind: "pct", group: "exit" },
  { key: "selling_costs_pct", label: "Selling costs", kind: "pct", group: "exit" },
  { key: "loan_to_cost", label: "Loan-to-cost", kind: "pct", group: "debt" },
  { key: "construction_rate", label: "Construction loan rate", kind: "pct", group: "debt" },
  { key: "loan_fee_pct", label: "Loan fee", kind: "pct", hint: "% of commitment", group: "debt" },
];

const GROUPS: { key: (typeof FIELDS)[number]["group"]; label: string }[] = [
  { key: "cost", label: "Development budget" },
  { key: "timing", label: "Timing" },
  { key: "exit", label: "Stabilization & exit" },
  { key: "debt", label: "Construction financing" },
];

type FormState = Record<keyof DevInputs, string>;

// ---------------------------------------------------------------- helpers
const roundTo = (v: number, step: number) => Math.max(step, Math.round(v / step) * step);

/** Starting inputs: saved model if present, otherwise illustrative defaults scaled from the deal's price. */
function defaultInputs(property: Property, base: Scenario | undefined): { inputs: DevInputs; saved: boolean } {
  const saved = (property.attributes?.development ?? null) as Partial<DevInputs> | null;
  const price = property.purchase_price && property.purchase_price > 0 ? property.purchase_price : 10_000_000;
  const isLand = property.property_type === "land";
  const fallback: DevInputs = {
    land_cost: isLand ? price : roundTo(price * 0.2, 10_000),
    hard_costs: isLand ? roundTo(price * 3, 10_000) : roundTo(price * 0.6, 10_000),
    soft_costs_pct: 0.2,
    contingency_pct: 0.05,
    construction_months: 18,
    lease_up_months: 12,
    stabilized_noi: roundTo((isLand ? price * 4 : price) * 0.07, 1_000),
    exit_cap_rate: base?.assumptions.exit_cap_rate ?? 0.055,
    selling_costs_pct: 0.02,
    loan_to_cost: 0.6,
    construction_rate: 0.08,
    loan_fee_pct: 0.01,
  };
  if (saved && typeof saved === "object") {
    const merged = { ...fallback };
    for (const f of FIELDS) {
      const v = saved[f.key];
      if (isNum(v)) merged[f.key] = v;
    }
    return { inputs: merged, saved: true };
  }
  return { inputs: fallback, saved: false };
}

const pctStr = (v: number) => String(Number((v * 100).toFixed(6)));
const toNum = (s: string) => Number(s.replace(/[$,\s]/g, ""));

function toForm(d: DevInputs): FormState {
  const out = {} as FormState;
  for (const f of FIELDS) {
    const v = d[f.key];
    out[f.key] = f.kind === "pct" ? pctStr(v) : f.kind === "usd" ? v.toLocaleString("en-US") : String(v);
  }
  return out;
}

function toBody(s: FormState): { body: DevInputs | null; invalid: string[] } {
  const body = {} as DevInputs;
  const invalid: string[] = [];
  for (const f of FIELDS) {
    const raw = s[f.key];
    const n = toNum(raw);
    if (raw.trim() === "" || !Number.isFinite(n)) {
      invalid.push(f.key);
      continue;
    }
    body[f.key] = f.kind === "pct" ? Number((n / 100).toFixed(10)) : f.kind === "months" ? Math.round(n) : n;
  }
  return invalid.length ? { body: null, invalid } : { body, invalid };
}

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

// ------------------------------------------------------------------- page
export default function DevelopmentPage() {
  const { property, base, canEdit } = useDeal();
  const org = useOrgKey();
  const qc = useQueryClient();
  const enabled = useFeature("development");
  const start = useMemo(() => defaultInputs(property, base), [property, base]);
  const [form, setForm] = useState<FormState>(() => toForm(start.inputs));
  const { body, invalid } = useMemo(() => toBody(form), [form]);
  const bodyKey = body ? JSON.stringify(body) : null;
  const debouncedKey = useDebounced(bodyKey, 400);

  const calc = useQuery({
    queryKey: [org, "development-calc", debouncedKey],
    queryFn: ({ signal }) =>
      api<DevResult>("/api/development/calculate", { method: "POST", body: JSON.parse(debouncedKey as string), signal }),
    enabled: enabled === true && debouncedKey !== null,
    placeholderData: keepPreviousData,
    retry: false,
    staleTime: Infinity,
  });

  const save = useMutation({
    mutationFn: (b: DevInputs) => api<DevResult>(`/api/properties/${property.id}/development`, { method: "PUT", body: b }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org, "property", property.id] });
      qc.invalidateQueries({ queryKey: [org, "audit", property.id] });
      toast.success("Development model saved to the deal");
    },
    onError: (e) => toast.error(e.message),
  });

  if (enabled === false)
    return (
      <Callout title="Development feasibility not available on this plan">
        The development module is not enabled for this workspace.
      </Callout>
    );
  if (enabled === undefined) return <LoadingBlock rows={6} />;

  const r = calc.data;
  const pending = calc.isFetching || bodyKey !== debouncedKey;
  const savedKey = start.saved ? JSON.stringify(toBody(toForm(start.inputs)).body) : null;
  const dirty = bodyKey !== savedKey;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight">Development feasibility</h2>
            <Badge variant="accent">Beta</Badge>
          </div>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Ground-up budget, construction financing and returns. Results recalculate as you type.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => setForm(toForm(start.inputs))} disabled={!dirty}>
            <RotateCcw /> {start.saved ? "Revert to saved" : "Reset defaults"}
          </Button>
          {canEdit && (
            <Button onClick={() => body && save.mutate(body)} loading={save.isPending} disabled={!body || !!calc.error}>
              <Save /> Save to deal
            </Button>
          )}
        </div>
      </div>

      <Callout title="Basic beta model">
        Simplifications: equity funds costs first, then the construction loan; hard and soft costs draw straight-line over the construction period; NOI ramps linearly through lease-up; the asset is sold at stabilization. Interest accrues to a capitalised reserve. Use for screening, not as a substitute for a full development pro forma.
        {!start.saved && " Starting inputs are illustrative defaults scaled from the deal's price."}
      </Callout>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <Card className="self-start">
          <CardHeader>
            <CardTitle>Inputs</CardTitle>
            <CardDescription>Percentages as whole numbers (20 = 20%).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {GROUPS.map((g) => (
              <fieldset key={g.key} className="grid grid-cols-2 gap-3">
                <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{g.label}</legend>
                {FIELDS.filter((f) => f.group === g.key).map((f) => {
                  const id = `dev-${f.key}`;
                  const bad = invalid.includes(f.key);
                  return (
                    <div key={f.key} className={cn("space-y-1.5", f.kind === "usd" && "col-span-2")}>
                      <Label htmlFor={id}>{f.label}</Label>
                      <div className="relative">
                        <Input
                          id={id}
                          inputMode={f.kind === "months" ? "numeric" : "decimal"}
                          value={form[f.key]}
                          aria-invalid={bad}
                          aria-describedby={f.hint ? `${id}-hint` : undefined}
                          onChange={(e) => setForm((p) => ({ ...p, [f.key]: e.target.value }))}
                          className="pr-14"
                        />
                        <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground" aria-hidden>
                          {f.kind === "usd" ? "$" : f.kind === "pct" ? "%" : "months"}
                        </span>
                      </div>
                      {f.hint && (
                        <p id={`${id}-hint`} className="text-[11px] text-muted-foreground">
                          {f.hint}
                        </p>
                      )}
                    </div>
                  );
                })}
              </fieldset>
            ))}
            {!canEdit && <p className="text-[11px] text-muted-foreground">You can explore inputs; saving to the deal requires analyst access.</p>}
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-4" aria-live="polite" aria-busy={pending}>
          {invalid.length > 0 && <Callout tone="warn">Enter a number in every input to recalculate.</Callout>}
          {calc.error && <ErrorBlock error={calc.error} />}
          {!r && !calc.error && <LoadingBlock rows={6} />}
          {r && <Outputs r={r} stale={pending || !!calc.error || invalid.length > 0} />}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- outputs
function Outputs({ r, stale }: { r: DevResult; stale: boolean }) {
  const ret = r.returns;
  const spread = ret.development_spread_bps;
  const chart = useMemo(
    () =>
      r.monthly_equity_cash_flows.reduce<{ month: number; cumulative: number }[]>(
        (acc, cf, m) => [...acc, { month: m, cumulative: (acc.at(-1)?.cumulative ?? 0) + cf }],
        [],
      ),
    [r.monthly_equity_cash_flows],
  );
  const cm = r.inputs.construction_months;

  return (
    <div className={cn("space-y-4 transition-opacity", stale && "opacity-60")}>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Metric label="Yield on cost" value={pct(ret.yield_on_cost, 2)} hint="Stabilized NOI ÷ total development cost." />
        <Metric
          label="Development spread"
          value={`${num(spread)} bps`}
          tone={isNum(spread) ? (spread > 0 ? "good" : "bad") : undefined}
          hint="Yield on cost minus exit cap rate."
        />
        <Metric label="Levered IRR" value={pct(ret.irr, 1)} hint="Annualised from monthly equity cash flows." />
        <Metric label="Equity multiple" value={mult(ret.equity_multiple)} />
        <Metric label="Stabilized value" value={usdShort(ret.stabilized_value)} sub={usd(ret.stabilized_value)} />
        <Metric label="Profit" value={usdShort(ret.profit)} tone={ret.profit < 0 ? "bad" : undefined} hint="Equity distributions less contributions." />
        <Metric label="Profit margin" value={pct(ret.profit_margin, 1)} hint="(Stabilized value − total cost) ÷ total cost." />
        <Metric label="Equity required" value={usdShort(r.capital.equity)} sub={usd(r.capital.equity)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Development budget</CardTitle>
          </CardHeader>
          <CardContent className="px-0 pb-2">
            <Table>
              <TBody>
                {(
                  [
                    ["Land", r.budget.land],
                    ["Hard costs", r.budget.hard_costs],
                    ["Soft costs", r.budget.soft_costs],
                    ["Contingency", r.budget.contingency],
                    ["Loan fees", r.budget.loan_fees],
                    ["Interest reserve", r.budget.interest_reserve],
                  ] as [string, number][]
                ).map(([l, v]) => (
                  <TR key={l}>
                    <TD className="pl-5">{l}</TD>
                    <TD className="pr-5 text-right">{usd(v)}</TD>
                  </TR>
                ))}
                <TR className="border-t-2 font-semibold hover:bg-transparent">
                  <TD className="pl-5">Total development cost</TD>
                  <TD className="pr-5 text-right">{usd(r.budget.total_cost)}</TD>
                </TR>
              </TBody>
            </Table>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Capital stack</CardTitle>
          </CardHeader>
          <CardContent className="px-0 pb-2">
            <Table>
              <TBody>
                <TR>
                  <TD className="pl-5">Construction loan commitment</TD>
                  <TD className="pr-5 text-right">{usd(r.capital.construction_loan)}</TD>
                </TR>
                <TR>
                  <TD className="pl-5">Equity</TD>
                  <TD className="pr-5 text-right">{usd(r.capital.equity)}</TD>
                </TR>
                <TR className="border-t-2 font-semibold hover:bg-transparent">
                  <TD className="pl-5">Total sources</TD>
                  <TD className="pr-5 text-right">{usd(r.budget.total_cost)}</TD>
                </TR>
                <TR>
                  <TD className="pl-5 text-muted-foreground">Loan balance repaid at sale</TD>
                  <TD className="pr-5 text-right text-muted-foreground">{usd(r.capital.loan_balance_at_exit)}</TD>
                </TR>
              </TBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Cumulative equity cash flow</CardTitle>
          <CardDescription>
            Monthly, from land closing (month 0) to sale at stabilization (month {chart.length - 1}). Dashed line marks construction completion.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="h-64" role="img" aria-label={`Cumulative equity cash flow over ${chart.length - 1} months, ending at ${usdShort(chart.at(-1)?.cumulative)}`}>
            <ResponsiveContainer>
              <AreaChart data={chart} margin={{ top: 16, right: 12, left: 0, bottom: 0 }}>
                <CartesianGrid {...GRID_PROPS} />
                <XAxis dataKey="month" {...AXIS_PROPS} tickFormatter={(m: number) => `M${m}`} minTickGap={24} />
                <YAxis {...AXIS_PROPS} axisLine={false} width={64} tickFormatter={(v: number) => usdShort(v)} />
                <ReferenceLine y={0} stroke="var(--chart-axis)" />
                <ReferenceLine
                  x={cm}
                  stroke="var(--muted-foreground)"
                  strokeDasharray="4 3"
                  label={{ value: "Construction complete", position: "insideTopLeft", fill: "var(--muted-foreground)", fontSize: 11 }}
                />
                <Tooltip content={<ChartTooltip format={(v) => usd(v)} labelFormat={(l) => `Month ${l}`} />} />
                <Area
                  type="linear"
                  dataKey="cumulative"
                  name="Cumulative equity"
                  stroke={SERIES[0]}
                  strokeWidth={2}
                  fill={SERIES[0]}
                  fillOpacity={0.12}
                  isAnimationActive={false}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
