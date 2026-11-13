"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { AXIS_PROPS, ChartTooltip, SERIES } from "@/components/charts";
import { Callout, ErrorBlock, LoadingBlock, Metric } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import {
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
  TH,
  THead,
  TR,
} from "@/components/ui/primitives";
import { useFeature, useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { isNum, num, pct, usd, usdShort } from "@/lib/format";
import type { Property } from "@/lib/types";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ types
type Approach = "direct_cap" | "dcf" | "sales_comparison" | "cost";
const APPROACHES: Approach[] = ["direct_cap", "dcf", "sales_comparison", "cost"];
const APPROACH_LABEL: Record<Approach, string> = {
  direct_cap: "Direct capitalization",
  dcf: "Discounted cash flow",
  sales_comparison: "Sales comparison",
  cost: "Cost approach",
};

interface CompIn {
  name: string;
  sale_price: number;
  units?: number | null;
  sf?: number | null;
  cap_rate?: number | null;
  adjustment_pct?: number;
  weight?: number;
}

interface CostIn {
  land_value: number;
  replacement_cost: number;
  physical_depreciation_pct?: number;
  functional_obsolescence?: number;
  external_obsolescence?: number;
  entrepreneurial_incentive_pct?: number;
}

interface ValuationInputs {
  market_cap_rate?: number;
  discount_rate?: number;
  comps?: CompIn[];
  cost?: CostIn;
  weights?: Partial<Record<Approach, number>>;
}

interface Valuation {
  reconciled_value: number;
  weights: Partial<Record<Approach, number>>;
  values: Record<Approach, number | null>;
  range: { low: number; high: number };
  details: {
    sales_comparison?: {
      basis: "unit" | "sf";
      price_per: number;
      value: number;
      comps: { name: string; raw_price_per: number; adjusted_price_per: number; weight: number }[];
    };
    cost?: {
      land_value: number;
      replacement_cost: number;
      total_depreciation: number;
      depreciated_improvements: number;
      value: number;
    };
  };
  purchase_price: number;
  premium_discount_to_value: number | null;
  inputs: ValuationInputs;
  scenario_id: string;
}

// ------------------------------------------------------------------- page
export default function ValuationPage() {
  const { property, base, canEdit } = useDeal();
  const org = useOrgKey();
  const enabled = useFeature("valuation");
  const q = useQuery({
    queryKey: [org, "valuation", property.id],
    queryFn: () => api<Valuation>(`/api/properties/${property.id}/valuation`),
    enabled: enabled === true,
    retry: false,
  });

  if (enabled === false)
    return (
      <Callout title="Valuation not available on this plan">
        Valuation reconciliation is not enabled for this workspace. An owner can upgrade the plan under Settings.
      </Callout>
    );
  if (enabled === undefined || q.isLoading) return <LoadingBlock rows={6} />;

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-base font-semibold tracking-tight">Valuation reconciliation</h2>
        <p className="mt-0.5 text-sm text-muted-foreground">
          Independent approaches to value, weighted into a reconciled conclusion
          {base ? <> for the base scenario ({base.name})</> : null}.
        </p>
      </div>
      {q.error ? (
        <>
          <ErrorBlock error={q.error} />
          {canEdit && <p className="text-sm text-muted-foreground">Review the valuation inputs below and save to recompute.</p>}
        </>
      ) : q.data ? (
        <Summary v={q.data} property={property} />
      ) : null}
      {canEdit ? (
        <InputsForm key={JSON.stringify(property.valuation_inputs ?? {})} property={property} defaults={base?.assumptions} />
      ) : (
        !q.error && <ReadOnlyInputs inputs={q.data?.inputs ?? {}} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------- summary
function Summary({ v, property }: { v: Valuation; property: Property }) {
  const prem = v.premium_discount_to_value;
  const chartData = APPROACHES.filter((a) => isNum(v.values[a])).map((a) => ({
    name: APPROACH_LABEL[a],
    value: v.values[a] as number,
  }));
  const sc = v.details.sales_comparison;
  const cost = v.details.cost;
  const basisLabel = sc?.basis === "unit" ? "unit" : "SF";

  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label="Reconciled value" value={usdShort(v.reconciled_value)} sub={usd(v.reconciled_value)} />
        <Metric label="Purchase price" value={usdShort(v.purchase_price)} sub={usd(v.purchase_price)} />
        <Metric
          label={isNum(prem) && prem < 0 ? "Discount to value" : "Premium to value"}
          value={isNum(prem) ? pct(Math.abs(prem), 1) : "—"}
          tone={isNum(prem) ? (prem > 0 ? "warn" : "good") : undefined}
          sub={isNum(prem) ? (prem > 0 ? "Price above reconciled value" : "Price at or below reconciled value") : undefined}
          hint="(Purchase price − reconciled value) ÷ reconciled value."
        />
        <Metric
          label="Value range"
          value={
            <span className="text-base">
              {usdShort(v.range.low)} – {usdShort(v.range.high)}
            </span>
          }
          sub="Lowest to highest weighted approach"
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Value by approach</CardTitle>
            <CardDescription>Dashed line marks the purchase price.</CardDescription>
          </CardHeader>
          <CardContent>
            <div
              className="h-60"
              role="img"
              aria-label={`Value by approach: ${chartData.map((d) => `${d.name} ${usdShort(d.value)}`).join(", ")}; purchase price ${usdShort(v.purchase_price)}`}
            >
              <ResponsiveContainer>
                <BarChart data={chartData} layout="vertical" barCategoryGap="30%" margin={{ top: 20, right: 24, left: 8, bottom: 0 }}>
                  <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
                  <XAxis type="number" {...AXIS_PROPS} tickFormatter={(x: number) => usdShort(x)} />
                  <YAxis type="category" dataKey="name" {...AXIS_PROPS} axisLine={false} width={150} />
                  <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={(x) => usd(x)} />} />
                  <Bar dataKey="value" name="Indicated value" fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={22} />
                  <ReferenceLine
                    x={v.purchase_price}
                    stroke="var(--foreground)"
                    strokeDasharray="4 3"
                    label={{ value: `Purchase ${usdShort(v.purchase_price)}`, position: "top", fill: "var(--muted-foreground)", fontSize: 11 }}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Reconciliation</CardTitle>
            <CardDescription>Weights are renormalised across approaches with a value.</CardDescription>
          </CardHeader>
          <CardContent className="px-0 pb-2">
            <Table>
              <THead>
                <TR className="hover:bg-transparent">
                  <TH className="pl-5">Approach</TH>
                  <TH className="text-right">Value</TH>
                  <TH className="pr-5 text-right">Weight</TH>
                </TR>
              </THead>
              <TBody>
                {APPROACHES.map((a) => {
                  const val = v.values[a];
                  const w = v.weights[a];
                  return (
                    <TR key={a} className={cn(!isNum(val) && "text-muted-foreground")}>
                      <TD className="pl-5">{APPROACH_LABEL[a]}</TD>
                      <TD className="text-right">{isNum(val) ? usd(val) : <span className="text-xs">Not provided</span>}</TD>
                      <TD className="pr-5 text-right">{isNum(w) ? pct(w, 0) : "—"}</TD>
                    </TR>
                  );
                })}
                <TR className="border-t-2 font-semibold hover:bg-transparent">
                  <TD className="pl-5">Reconciled value</TD>
                  <TD className="text-right">{usd(v.reconciled_value)}</TD>
                  <TD className="pr-5 text-right">100%</TD>
                </TR>
              </TBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {(sc || cost) && (
        <div className="grid gap-4 xl:grid-cols-2">
          {sc && (
            <Card>
              <CardHeader>
                <CardTitle>Sales comparison detail</CardTitle>
                <CardDescription>
                  Weighted adjusted {usd(sc.price_per)} per {basisLabel} × subject{" "}
                  {sc.basis === "unit" ? `${num(property.units)} units` : `${num(property.rentable_sf)} SF`} = {usd(sc.value)}
                </CardDescription>
              </CardHeader>
              <CardContent className="px-0 pb-2">
                <Table>
                  <THead>
                    <TR className="hover:bg-transparent">
                      <TH className="pl-5">Comparable</TH>
                      <TH className="text-right">Price / {basisLabel}</TH>
                      <TH className="text-right">Adjusted</TH>
                      <TH className="pr-5 text-right">Weight</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {sc.comps.map((c, i) => (
                      <TR key={`${c.name}-${i}`}>
                        <TD className="pl-5">{c.name}</TD>
                        <TD className="text-right">{usd(c.raw_price_per)}</TD>
                        <TD className="text-right">{usd(c.adjusted_price_per)}</TD>
                        <TD className="pr-5 text-right">{num(c.weight, 2)}</TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </CardContent>
            </Card>
          )}
          {cost && (
            <Card>
              <CardHeader>
                <CardTitle>Cost approach detail</CardTitle>
                <CardDescription>Land plus depreciated replacement cost of improvements.</CardDescription>
              </CardHeader>
              <CardContent className="px-0 pb-2">
                <Table>
                  <TBody>
                    {(
                      [
                        ["Land value", cost.land_value],
                        ["Replacement cost (incl. entrepreneurial incentive)", cost.replacement_cost],
                        ["Less: total depreciation & obsolescence", -cost.total_depreciation],
                        ["Depreciated improvements", cost.depreciated_improvements],
                      ] as [string, number][]
                    ).map(([l, val]) => (
                      <TR key={l}>
                        <TD className="pl-5">{l}</TD>
                        <TD className="pr-5 text-right">{usd(val)}</TD>
                      </TR>
                    ))}
                    <TR className="border-t-2 font-semibold hover:bg-transparent">
                      <TD className="pl-5">Indicated value</TD>
                      <TD className="pr-5 text-right">{usd(cost.value)}</TD>
                    </TR>
                  </TBody>
                </Table>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </>
  );
}

function ReadOnlyInputs({ inputs }: { inputs: ValuationInputs }) {
  const hasAny = Object.keys(inputs).length > 0;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Valuation inputs</CardTitle>
        <CardDescription>Read-only. Analysts can edit market rates, comparables, cost inputs and weights.</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
        {!hasAny && <p className="col-span-full text-muted-foreground">Using defaults: scenario exit cap and discount rate, standard weights.</p>}
        {isNum(inputs.market_cap_rate) && <KV k="Market cap rate" v={pct(inputs.market_cap_rate)} />}
        {isNum(inputs.discount_rate) && <KV k="Discount rate" v={pct(inputs.discount_rate)} />}
        {inputs.comps?.length ? <KV k="Comparables" v={String(inputs.comps.length)} /> : null}
        {inputs.cost ? <KV k="Cost approach" v="Provided" /> : null}
      </CardContent>
    </Card>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <div className="text-xs text-muted-foreground">{k}</div>
      <div className="font-medium tabular">{v}</div>
    </div>
  );
}

// ------------------------------------------------------------------- form
const toPctStr = (v: number | null | undefined) => (isNum(v) ? String(Number((v * 100).toFixed(6))) : "");
const toNum = (s: string) => Number(s.replace(/[$,\s]/g, ""));
const fromPctStr = (s: string) => Number((toNum(s) / 100).toFixed(10));
const filled = (s: string) => s.trim() !== "";
const moneyStr = (v: number | null | undefined) => (isNum(v) ? v.toLocaleString("en-US") : "");

interface CompRow {
  key: number;
  name: string;
  sale_price: string;
  size: string;
  adjustment: string;
  weight: string;
}

interface FormState {
  market_cap_rate: string;
  discount_rate: string;
  comps: CompRow[];
  cost: {
    land_value: string;
    replacement_cost: string;
    physical_depreciation_pct: string;
    functional_obsolescence: string;
    external_obsolescence: string;
    entrepreneurial_incentive_pct: string;
  };
  weights: Record<Approach, string>;
}

let rowSeq = 0;
const blankComp = (): CompRow => ({ key: ++rowSeq, name: "", sale_price: "", size: "", adjustment: "0", weight: "1" });

function initialForm(vi: ValuationInputs, basis: "unit" | "sf"): FormState {
  const c = vi.cost;
  return {
    market_cap_rate: toPctStr(vi.market_cap_rate),
    discount_rate: toPctStr(vi.discount_rate),
    comps: (vi.comps ?? []).map((x) => ({
      key: ++rowSeq,
      name: x.name ?? "",
      sale_price: moneyStr(x.sale_price),
      size: moneyStr(basis === "unit" ? x.units : x.sf),
      adjustment: toPctStr(x.adjustment_pct ?? 0),
      weight: isNum(x.weight) ? String(x.weight) : "1",
    })),
    cost: {
      land_value: moneyStr(c?.land_value),
      replacement_cost: moneyStr(c?.replacement_cost),
      physical_depreciation_pct: toPctStr(c?.physical_depreciation_pct),
      functional_obsolescence: moneyStr(c?.functional_obsolescence),
      external_obsolescence: moneyStr(c?.external_obsolescence),
      entrepreneurial_incentive_pct: toPctStr(c?.entrepreneurial_incentive_pct),
    },
    weights: {
      direct_cap: toPctStr(vi.weights?.direct_cap),
      dcf: toPctStr(vi.weights?.dcf),
      sales_comparison: toPctStr(vi.weights?.sales_comparison),
      cost: toPctStr(vi.weights?.cost),
    },
  };
}

function buildBody(s: FormState, basis: "unit" | "sf"): { body: ValuationInputs; error: string | null } {
  const bad = (label: string, v: string) => filled(v) && !Number.isFinite(toNum(v)) && `${label} must be a number.`;
  const body: ValuationInputs = {};
  for (const [k, label] of [
    ["market_cap_rate", "Market cap rate"],
    ["discount_rate", "Discount rate"],
  ] as const) {
    const e = bad(label, s[k]);
    if (e) return { body, error: e };
    if (filled(s[k])) body[k] = fromPctStr(s[k]);
  }

  const comps: CompIn[] = [];
  for (const [i, r] of s.comps.entries()) {
    if (![r.name, r.sale_price, r.size].some(filled)) continue;
    const n = i + 1;
    if (!r.name.trim()) return { body, error: `Comparable ${n}: enter a name.` };
    for (const [label, v] of [
      ["sale price", r.sale_price],
      [basis === "unit" ? "units" : "SF", r.size],
    ] as const) {
      if (!filled(v) || !Number.isFinite(toNum(v)) || toNum(v) <= 0)
        return { body, error: `Comparable ${n}: ${label} must be a positive number.` };
    }
    const e = bad(`Comparable ${n} adjustment`, r.adjustment) || bad(`Comparable ${n} weight`, r.weight);
    if (e) return { body, error: e };
    comps.push({
      name: r.name.trim(),
      sale_price: toNum(r.sale_price),
      ...(basis === "unit" ? { units: Math.round(toNum(r.size)) } : { sf: toNum(r.size) }),
      adjustment_pct: filled(r.adjustment) ? fromPctStr(r.adjustment) : 0,
      weight: filled(r.weight) ? toNum(r.weight) : 1,
    });
  }
  if (comps.length) body.comps = comps;

  const c = s.cost;
  if (Object.values(c).some(filled)) {
    if (!filled(c.land_value) || !filled(c.replacement_cost))
      return { body, error: "Cost approach: enter both land value and replacement cost (or clear the section)." };
    const fields: [string, string][] = [
      ["Land value", c.land_value],
      ["Replacement cost", c.replacement_cost],
      ["Physical depreciation", c.physical_depreciation_pct],
      ["Functional obsolescence", c.functional_obsolescence],
      ["External obsolescence", c.external_obsolescence],
      ["Entrepreneurial incentive", c.entrepreneurial_incentive_pct],
    ];
    for (const [l, v] of fields) {
      const e = bad(l, v);
      if (e) return { body, error: e };
    }
    body.cost = {
      land_value: toNum(c.land_value),
      replacement_cost: toNum(c.replacement_cost),
      physical_depreciation_pct: filled(c.physical_depreciation_pct) ? fromPctStr(c.physical_depreciation_pct) : 0,
      functional_obsolescence: filled(c.functional_obsolescence) ? toNum(c.functional_obsolescence) : 0,
      external_obsolescence: filled(c.external_obsolescence) ? toNum(c.external_obsolescence) : 0,
      entrepreneurial_incentive_pct: filled(c.entrepreneurial_incentive_pct) ? fromPctStr(c.entrepreneurial_incentive_pct) : 0,
    };
  }

  if (APPROACHES.some((a) => filled(s.weights[a]))) {
    const w: Partial<Record<Approach, number>> = {};
    for (const a of APPROACHES) {
      const e = bad(`${APPROACH_LABEL[a]} weight`, s.weights[a]);
      if (e) return { body, error: e };
      w[a] = filled(s.weights[a]) ? fromPctStr(s.weights[a]) : 0;
    }
    body.weights = w;
  }
  return { body, error: null };
}

function Field({
  id,
  label,
  suffix,
  hint,
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & { id: string; label: string; suffix?: string; hint?: string }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input id={id} inputMode="decimal" className={suffix ? "pr-9" : undefined} aria-describedby={hint ? `${id}-hint` : undefined} {...props} />
        {suffix && (
          <span className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground" aria-hidden>
            {suffix}
          </span>
        )}
      </div>
      {hint && (
        <p id={`${id}-hint`} className="text-[11px] text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

function InputsForm({ property, defaults }: { property: Property; defaults?: { exit_cap_rate: number; discount_rate: number } }) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const basis: "unit" | "sf" = property.units ? "unit" : "sf";
  const saved = (property.valuation_inputs ?? {}) as ValuationInputs;
  const [s, setS] = useState<FormState>(() => initialForm(saved, basis));
  const [error, setError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (body: ValuationInputs) => api<Valuation>(`/api/properties/${property.id}/valuation`, { method: "PUT", body }),
    onSuccess: (data) => {
      qc.setQueryData([org, "valuation", property.id], data);
      qc.invalidateQueries({ queryKey: [org, "property", property.id] });
      qc.invalidateQueries({ queryKey: [org, "audit", property.id] });
      toast.success("Valuation inputs saved and value recomputed");
    },
    onError: (e) => toast.error(e.message),
  });

  const setTop = (k: "market_cap_rate" | "discount_rate") => (e: React.ChangeEvent<HTMLInputElement>) =>
    setS((p) => ({ ...p, [k]: e.target.value }));
  const setCost = (k: keyof FormState["cost"]) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setS((p) => ({ ...p, cost: { ...p.cost, [k]: e.target.value } }));
  const setWeight = (k: Approach) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setS((p) => ({ ...p, weights: { ...p.weights, [k]: e.target.value } }));
  const setComp = (key: number, k: keyof Omit<CompRow, "key">) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setS((p) => ({ ...p, comps: p.comps.map((c) => (c.key === key ? { ...c, [k]: e.target.value } : c)) }));
  const sizeLabel = basis === "unit" ? "Units" : "Rentable SF";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Valuation inputs</CardTitle>
        <CardDescription>
          Enter percentages as whole numbers (5.5 = 5.50%). Blank fields fall back to scenario defaults; empty sections are omitted.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form
          noValidate
          className="space-y-6"
          onSubmit={(e) => {
            e.preventDefault();
            const { body, error: err } = buildBody(s, basis);
            setError(err);
            if (!err) save.mutate(body);
          }}
        >
          <fieldset className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Income approaches</legend>
            <Field
              id="val-cap"
              label="Market cap rate"
              suffix="%"
              value={s.market_cap_rate}
              onChange={setTop("market_cap_rate")}
              placeholder={defaults ? toPctStr(defaults.exit_cap_rate) : undefined}
              hint="Direct capitalization of Yr 1 NOI. Default: exit cap."
            />
            <Field
              id="val-disc"
              label="Discount rate"
              suffix="%"
              value={s.discount_rate}
              onChange={setTop("discount_rate")}
              placeholder={defaults ? toPctStr(defaults.discount_rate) : undefined}
              hint="DCF of unlevered cash flows. Default: scenario rate."
            />
          </fieldset>

          <fieldset>
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Sales comparables (price per {basis === "unit" ? "unit" : "SF"})
            </legend>
            {s.comps.length === 0 ? (
              <p className="mb-3 text-sm text-muted-foreground">No comparables. Add recent sales to include the sales comparison approach.</p>
            ) : (
              <div className="mb-3 overflow-x-auto">
                <table className="w-full min-w-[640px] text-sm tabular">
                  <thead>
                    <tr className="text-left text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
                      <th className="pb-1.5 pr-2 font-semibold">Name</th>
                      <th className="pb-1.5 pr-2 font-semibold">Sale price ($)</th>
                      <th className="pb-1.5 pr-2 font-semibold">{sizeLabel}</th>
                      <th className="pb-1.5 pr-2 font-semibold">Adjustment (%)</th>
                      <th className="pb-1.5 pr-2 font-semibold">Weight</th>
                      <th className="pb-1.5">
                        <span className="sr-only">Remove</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.comps.map((c, i) => (
                      <tr key={c.key}>
                        <td className="py-1 pr-2">
                          <Input aria-label={`Comparable ${i + 1} name`} value={c.name} onChange={setComp(c.key, "name")} placeholder="123 Main St" />
                        </td>
                        <td className="py-1 pr-2">
                          <Input aria-label={`Comparable ${i + 1} sale price`} inputMode="decimal" value={c.sale_price} onChange={setComp(c.key, "sale_price")} />
                        </td>
                        <td className="py-1 pr-2">
                          <Input aria-label={`Comparable ${i + 1} ${sizeLabel.toLowerCase()}`} inputMode="decimal" value={c.size} onChange={setComp(c.key, "size")} />
                        </td>
                        <td className="py-1 pr-2">
                          <Input aria-label={`Comparable ${i + 1} adjustment percent`} inputMode="decimal" value={c.adjustment} onChange={setComp(c.key, "adjustment")} />
                        </td>
                        <td className="py-1 pr-2">
                          <Input aria-label={`Comparable ${i + 1} weight`} inputMode="decimal" value={c.weight} onChange={setComp(c.key, "weight")} className="w-20" />
                        </td>
                        <td className="py-1">
                          <Button
                            type="button"
                            size="icon-sm"
                            variant="ghost"
                            aria-label={`Remove comparable ${i + 1}`}
                            onClick={() => setS((p) => ({ ...p, comps: p.comps.filter((x) => x.key !== c.key) }))}
                          >
                            <Trash2 />
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <Button type="button" variant="outline" size="sm" onClick={() => setS((p) => ({ ...p, comps: [...p.comps, blankComp()] }))}>
              <Plus /> Add comparable
            </Button>
            <p className="mt-2 text-[11px] text-muted-foreground">
              Adjustment is the net qualitative adjustment to the comparable&apos;s price per {basis === "unit" ? "unit" : "SF"} (e.g. −5 for a superior asset). Weights are relative.
            </p>
          </fieldset>

          <fieldset className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Cost approach (optional)</legend>
            <Field id="val-land" label="Land value" suffix="$" value={s.cost.land_value} onChange={setCost("land_value")} />
            <Field id="val-repl" label="Replacement cost" suffix="$" value={s.cost.replacement_cost} onChange={setCost("replacement_cost")} />
            <Field id="val-incent" label="Entrepreneurial incentive" suffix="%" value={s.cost.entrepreneurial_incentive_pct} onChange={setCost("entrepreneurial_incentive_pct")} />
            <Field id="val-phys" label="Physical depreciation" suffix="%" value={s.cost.physical_depreciation_pct} onChange={setCost("physical_depreciation_pct")} />
            <Field id="val-func" label="Functional obsolescence" suffix="$" value={s.cost.functional_obsolescence} onChange={setCost("functional_obsolescence")} />
            <Field id="val-ext" label="External obsolescence" suffix="$" value={s.cost.external_obsolescence} onChange={setCost("external_obsolescence")} />
          </fieldset>

          <fieldset className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Reconciliation weights</legend>
            {APPROACHES.map((a) => (
              <Field key={a} id={`val-w-${a}`} label={APPROACH_LABEL[a]} suffix="%" value={s.weights[a]} onChange={setWeight(a)} />
            ))}
            <p className="col-span-full text-[11px] text-muted-foreground">
              Leave all blank for the default 40 / 40 / 20 / 0. Weights are renormalised across approaches that produce a value.
            </p>
          </fieldset>

          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setS(initialForm(saved, basis));
                setError(null);
              }}
            >
              Reset
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save &amp; recompute
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
