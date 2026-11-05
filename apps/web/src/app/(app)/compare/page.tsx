"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Award, GitCompareArrows, Search, X } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { PolarAngleAxis, PolarGrid, PolarRadiusAxis, Radar, RadarChart, ResponsiveContainer, Tooltip } from "recharts";
import type { TooltipContentProps } from "recharts";

import { Legend, SERIES } from "@/components/charts";
import { Callout, DemoBadge, EmptyState, ErrorBlock, LoadingBlock, PageHeader, RiskBadge, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle, Input, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useFeatures, useOrgKey, useProperties } from "@/hooks/queries";
import { api } from "@/lib/api";
import { isNum, mult, num, pct, stripDemo, TYPE_LABELS, usd, usdShort } from "@/lib/format";
import type { Headline, Property, RiskFactor } from "@/lib/types";
import { cn } from "@/lib/utils";

const MAX_DEALS = 8;

type CompareRow = {
  property_id: string;
  name: string;
  property_type: string;
  city: string | null;
  state: string | null;
  status: string;
  is_demo: boolean;
  purchase_price: number | null;
  units: number | null;
  rentable_sf: number | null;
  risk_factors: RiskFactor[];
} & Partial<Headline>;

type Dir = "high" | "low" | null;

interface MetricRow {
  key: string;
  label: string;
  dir: Dir;
  value: (r: CompareRow) => number | null | undefined;
  fmt: (v: number) => string;
  /** Hide the row when no selected deal has a value (e.g. $/SF for a multifamily-only set). */
  optional?: boolean;
}

const METRICS: MetricRow[] = [
  { key: "price", label: "Purchase price", dir: null, value: (r) => r.purchase_price, fmt: usdShort },
  { key: "ppu", label: "Price / unit", dir: "low", value: (r) => r.price_per_unit, fmt: (v) => usd(v), optional: true },
  { key: "ppsf", label: "Price / SF", dir: "low", value: (r) => r.price_per_sf, fmt: (v) => usd(v, 2), optional: true },
  { key: "noi", label: "NOI (Year 1)", dir: null, value: (r) => r.noi_year1, fmt: usdShort },
  { key: "cap", label: "Going-in cap rate", dir: "high", value: (r) => r.cap_rate, fmt: (v) => pct(v) },
  { key: "irr_l", label: "Levered IRR", dir: "high", value: (r) => r.irr_levered, fmt: (v) => pct(v, 1) },
  { key: "irr_u", label: "Unlevered IRR", dir: "high", value: (r) => r.irr_unlevered, fmt: (v) => pct(v, 1) },
  { key: "em", label: "Equity multiple", dir: "high", value: (r) => r.equity_multiple, fmt: mult },
  { key: "coc", label: "Cash-on-cash (Y1)", dir: "high", value: (r) => r.cash_on_cash, fmt: (v) => pct(v, 1) },
  { key: "dscr", label: "DSCR (Y1)", dir: "high", value: (r) => r.dscr, fmt: mult },
  { key: "ltv", label: "LTV", dir: "low", value: (r) => r.ltv, fmt: (v) => pct(v, 1) },
  { key: "npv", label: "NPV", dir: "high", value: (r) => r.npv, fmt: usdShort },
  { key: "risk", label: "Risk score", dir: "low", value: (r) => r.risk_score, fmt: (v) => num(v) },
];

interface Axis {
  label: string;
  value: (r: CompareRow) => number | null | undefined;
  raw: (r: CompareRow) => string;
}

const AXES: Axis[] = [
  { label: "Levered IRR", value: (r) => r.irr_levered, raw: (r) => pct(r.irr_levered, 1) },
  { label: "Equity multiple", value: (r) => r.equity_multiple, raw: (r) => mult(r.equity_multiple) },
  { label: "Cash-on-cash", value: (r) => r.cash_on_cash, raw: (r) => pct(r.cash_on_cash, 1) },
  { label: "DSCR", value: (r) => r.dscr, raw: (r) => mult(r.dscr) },
  { label: "Cap rate", value: (r) => r.cap_rate, raw: (r) => pct(r.cap_rate) },
  {
    label: "Low risk",
    value: (r) => (isNum(r.risk_score) ? 100 - r.risk_score : null),
    raw: (r) => (isNum(r.risk_score) ? `risk score ${num(r.risk_score)}` : "—"),
  },
];

function location(r: { city: string | null; state: string | null }) {
  return [r.city, r.state].filter(Boolean).join(", ") || "—";
}

/** Best value(s) in a row, or null when direction is neutral, fewer than 2 values exist, or all values tie. */
function bestOf(values: (number | null | undefined)[], dir: Dir): number | null {
  if (!dir) return null;
  const nums = values.filter(isNum);
  if (nums.length < 2) return null;
  const max = Math.max(...nums);
  const min = Math.min(...nums);
  if (max === min) return null;
  return dir === "high" ? max : min;
}

// -------------------------------------------------------------------- page
function CompareInner() {
  const params = useSearchParams();
  const router = useRouter();
  const org = useOrgKey();
  const features = useFeatures();
  const enabled = features.data ? features.data.deal_comparison?.enabled === true : undefined;
  const properties = useProperties();
  const [picked, setPicked] = useState<string[] | null>(() => {
    const ids = params.get("ids")?.split(",").filter(Boolean);
    return ids?.length ? ids.slice(0, MAX_DEALS) : null;
  });

  const byId = useMemo(() => new Map((properties.data ?? []).map((p) => [p.id, p])), [properties.data]);
  const defaults = useMemo(() => {
    const active = (properties.data ?? []).filter((p) => p.status !== "passed");
    return [...active.filter((p) => p.latest), ...active.filter((p) => !p.latest)].slice(0, 4).map((p) => p.id);
  }, [properties.data]);
  const selected = useMemo(
    () => (properties.data ? (picked ?? defaults).filter((id) => byId.has(id)) : []),
    [picked, defaults, byId, properties.data],
  );
  const idsKey = selected.join(",");

  const setSelection = (next: string[]) => {
    setPicked(next);
    router.replace(next.length ? `/compare?ids=${next.join(",")}` : "/compare", { scroll: false });
  };
  const toggle = (id: string) => {
    if (selected.includes(id)) setSelection(selected.filter((x) => x !== id));
    else if (selected.length < MAX_DEALS) setSelection([...selected, id]);
  };

  const compare = useQuery({
    queryKey: [org, "compare", idsKey],
    queryFn: () => api<CompareRow[]>(`/api/compare?ids=${idsKey}`),
    enabled: enabled === true && selected.length > 0,
    placeholderData: keepPreviousData,
  });

  // Keep column order (and therefore colours) tied to selection order, even while placeholder data is shown.
  const rows = useMemo(() => {
    const data = compare.data ?? [];
    return selected.map((id) => data.find((r) => r.property_id === id)).filter((r): r is CompareRow => !!r);
  }, [compare.data, selected]);
  const colorOf = (id: string) => {
    const i = selected.indexOf(id);
    return i >= 0 && i < SERIES.length ? SERIES[i] : undefined;
  };

  const header = (
    <PageHeader
      title="Compare deals"
      description="Side-by-side base-case returns, leverage and risk for up to eight deals."
    />
  );

  if (features.isLoading || properties.isLoading)
    return (
      <>
        {header}
        <LoadingBlock rows={6} />
      </>
    );
  if (features.error || properties.error)
    return (
      <>
        {header}
        <ErrorBlock error={features.error ?? properties.error} />
      </>
    );
  if (enabled === false)
    return (
      <>
        {header}
        <Callout title="Multi-deal comparison is not enabled for this workspace">
          Deal comparison is included in the Professional and Enterprise plans. An owner can upgrade the plan or enable the
          feature under{" "}
          <Link href="/settings?tab=billing" className="font-medium text-foreground underline underline-offset-2">
            Settings → Billing &amp; plan
          </Link>
          .
        </Callout>
      </>
    );
  if (!properties.data?.length)
    return (
      <>
        {header}
        <EmptyState
          icon={GitCompareArrows}
          title="No deals to compare"
          description="Create at least two deals to compare their returns side by side."
          action={
            <Button asChild>
              <Link href="/deals?new=1">Create a deal</Link>
            </Button>
          }
        />
      </>
    );

  return (
    <>
      {header}
      <div className="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
        <DealPicker
          deals={properties.data}
          selected={selected}
          onToggle={toggle}
          onClear={() => setSelection([])}
          colorOf={colorOf}
        />
        <div className="min-w-0 space-y-4">
          {selected.length === 0 && (
            <EmptyState icon={GitCompareArrows} title="Select deals to compare" description={`Choose up to ${MAX_DEALS} deals from the list.`} />
          )}
          {selected.length > 0 && compare.isLoading && <LoadingBlock rows={8} />}
          {selected.length > 0 && compare.error && <ErrorBlock error={compare.error} />}
          {selected.length > 0 && rows.length > 0 && (
            <>
              <MetricsTable rows={rows} colorOf={colorOf} updating={compare.isFetching} />
              <div className="grid gap-4 xl:grid-cols-5">
                <RadarCard rows={rows} className="xl:col-span-3" />
                <RiskFactors rows={rows} colorOf={colorOf} className="xl:col-span-2" />
              </div>
            </>
          )}
        </div>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ picker
function DealPicker({
  deals,
  selected,
  onToggle,
  onClear,
  colorOf,
}: {
  deals: Property[];
  selected: string[];
  onToggle: (id: string) => void;
  onClear: () => void;
  colorOf: (id: string) => string | undefined;
}) {
  const [q, setQ] = useState("");
  const needle = q.trim().toLowerCase();
  const list = needle
    ? deals.filter((d) => `${d.name} ${d.city ?? ""} ${d.state ?? ""} ${TYPE_LABELS[d.property_type] ?? ""}`.toLowerCase().includes(needle))
    : deals;
  const full = selected.length >= MAX_DEALS;
  return (
    <Card className="self-start lg:sticky lg:top-4">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between gap-2">
          <CardTitle id="picker-title">Deals</CardTitle>
          <span className="text-xs tabular text-muted-foreground" aria-live="polite">
            {selected.length} / {MAX_DEALS} selected
          </span>
        </div>
        <div className="relative mt-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
          <Input
            type="search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Filter deals…"
            className="pl-8"
            aria-label="Filter deals"
          />
        </div>
      </CardHeader>
      <CardContent className="px-2 pb-2">
        <fieldset aria-labelledby="picker-title">
          <ul className="max-h-[22rem] space-y-0.5 overflow-y-auto lg:max-h-[calc(100vh-16rem)]">
            {list.map((d) => {
              const checked = selected.includes(d.id);
              const disabled = !checked && full;
              const color = colorOf(d.id);
              return (
                <li key={d.id}>
                  <label
                    className={cn(
                      "flex cursor-pointer items-start gap-2.5 rounded-md px-3 py-2 text-sm transition-colors hover:bg-muted",
                      checked && "bg-muted/60",
                      disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
                    )}
                  >
                    <input
                      type="checkbox"
                      className="mt-0.5 size-4 shrink-0 accent-[var(--primary)]"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => onToggle(d.id)}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-1.5">
                        <span className="truncate font-medium">{stripDemo(d.name)}</span>
                        {d.is_demo && <DemoBadge />}
                      </span>
                      <span className="block truncate text-xs text-muted-foreground">
                        {TYPE_LABELS[d.property_type] ?? d.property_type} · {location(d)}
                        {d.status === "passed" && " · Passed"}
                        {!d.latest && " · Not calculated"}
                      </span>
                    </span>
                    {checked && color && <span className="mt-1.5 size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} aria-hidden />}
                  </label>
                </li>
              );
            })}
            {list.length === 0 && <li className="px-3 py-4 text-center text-xs text-muted-foreground">No deals match.</li>}
          </ul>
        </fieldset>
        {full && <p className="px-3 pt-2 text-xs text-muted-foreground">Maximum of {MAX_DEALS} deals. Deselect one to add another.</p>}
        {selected.length > 0 && (
          <div className="px-1 pt-2">
            <Button variant="ghost" size="sm" onClick={onClear} className="w-full">
              <X /> Clear selection
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------ metrics table
function MetricsTable({
  rows,
  colorOf,
  updating,
}: {
  rows: CompareRow[];
  colorOf: (id: string) => string | undefined;
  updating: boolean;
}) {
  const metrics = METRICS.filter((m) => !m.optional || rows.some((r) => isNum(m.value(r))));
  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between gap-3">
        <div>
          <CardTitle>Returns &amp; risk</CardTitle>
          <CardDescription>Base scenario, latest calculation. The best value in each row is marked.</CardDescription>
        </div>
        {updating && (
          <span className="shrink-0 text-xs text-muted-foreground" aria-live="polite">
            Updating…
          </span>
        )}
      </CardHeader>
      <Table>
        <caption className="sr-only">
          Metric comparison across {rows.length} selected deals. The best value per row is marked “best”.
        </caption>
        <THead>
          <TR className="hover:bg-transparent">
            <TH scope="col" className="sticky left-0 z-10 min-w-40 bg-card">
              Metric
            </TH>
            {rows.map((r) => {
              const color = colorOf(r.property_id);
              return (
                <TH key={r.property_id} scope="col" className="min-w-36 py-2 align-top normal-case tracking-normal">
                  <div className="flex items-center gap-1.5">
                    {color && <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} aria-hidden />}
                    <Link
                      href={`/deals/${r.property_id}`}
                      className="truncate text-[13px] font-semibold text-foreground hover:underline"
                    >
                      {stripDemo(r.name)}
                    </Link>
                  </div>
                  <div className="mt-0.5 text-[11px] font-normal text-muted-foreground">
                    {TYPE_LABELS[r.property_type] ?? r.property_type} · {location(r)}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-1">
                    <StatusBadge status={r.status} />
                    {r.is_demo && <DemoBadge />}
                  </div>
                </TH>
              );
            })}
          </TR>
        </THead>
        <TBody>
          {metrics.map((m) => {
            const values = rows.map(m.value);
            const best = bestOf(values, m.dir);
            return (
              <TR key={m.key}>
                <TH scope="row" className="sticky left-0 z-10 h-auto bg-card py-2 normal-case tracking-normal">
                  <div className="text-[13px] font-medium text-foreground">{m.label}</div>
                  <div className="text-[11px] font-normal text-muted-foreground">
                    {m.dir === "high" ? "Higher is better" : m.dir === "low" ? "Lower is better" : "For reference"}
                  </div>
                </TH>
                {rows.map((r, i) => {
                  const v = values[i];
                  const isBest = best !== null && v === best;
                  return (
                    <TD key={r.property_id} className={cn(isBest && "bg-success/8")}>
                      {m.key === "risk" ? (
                        <span className={cn("inline-flex items-center gap-1.5", isBest && "font-semibold")}>
                          <RiskBadge level={r.risk_level} score={r.risk_score} />
                          {isBest && <BestMarker />}
                        </span>
                      ) : (
                        <span className={cn("inline-flex items-center gap-1.5", isBest && "font-semibold")}>
                          {isNum(v) ? m.fmt(v) : <span className="text-muted-foreground">—</span>}
                          {isBest && <BestMarker />}
                        </span>
                      )}
                    </TD>
                  );
                })}
              </TR>
            );
          })}
        </TBody>
      </Table>
      {rows.some((r) => !r.result_id) && (
        <div className="border-t px-5 py-2.5 text-xs text-muted-foreground">
          “—” means the deal has no calculation yet. Run underwriting on the deal to populate its metrics.
        </div>
      )}
    </Card>
  );
}

function BestMarker() {
  return (
    <>
      <Award className="size-3.5 text-success" aria-hidden />
      <span className="sr-only">(best)</span>
    </>
  );
}

// ------------------------------------------------------------------- radar
type RadarDatum = Record<string, string | number>;

function RadarTooltip({ active, payload }: Partial<TooltipContentProps<number, string>>) {
  if (!active || !payload?.length) return null;
  const datum = payload[0]?.payload as RadarDatum | undefined;
  return (
    <div className="rounded-md border bg-card px-3 py-2 text-xs shadow-md">
      {datum && <div className="mb-1 font-medium text-foreground">{String(datum.axis)}</div>}
      <div className="space-y-0.5">
        {payload.map((p) => (
          <div key={String(p.dataKey)} className="flex items-center gap-2">
            <span className="size-2 rounded-[2px]" style={{ background: p.color }} aria-hidden />
            <span className="max-w-40 truncate text-muted-foreground">{p.name}</span>
            <span className="ml-auto pl-3 font-medium tabular text-foreground">{String(datum?.[`raw:${String(p.dataKey)}`] ?? "—")}</span>
            <span className="w-12 text-right tabular text-muted-foreground">{typeof p.value === "number" ? p.value : "—"}/100</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RadarCard({ rows, className }: { rows: CompareRow[]; className?: string }) {
  const charted = rows.slice(0, SERIES.length);
  const data = useMemo<RadarDatum[]>(
    () =>
      AXES.map((a) => {
        const vals = rows.map(a.value);
        const nums = vals.filter(isNum);
        const min = nums.length ? Math.min(...nums) : 0;
        const max = nums.length ? Math.max(...nums) : 0;
        const d: RadarDatum = { axis: a.label };
        rows.forEach((r, i) => {
          const v = vals[i];
          d[r.property_id] = !isNum(v) ? 0 : max === min ? 50 : Math.round(((v - min) / (max - min)) * 100);
          d[`raw:${r.property_id}`] = a.raw(r);
        });
        return d;
      }),
    [rows],
  );

  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Relative profile</CardTitle>
        <CardDescription>Normalized 0–100 score per dimension. Hover for the underlying values.</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length < 2 ? (
          <p className="py-10 text-center text-sm text-muted-foreground">Select at least two deals to see the relative profile.</p>
        ) : (
          <figure className="space-y-3">
            <Legend items={charted.map((r, i) => ({ label: stripDemo(r.name), color: SERIES[i] }))} />
            <div className="h-80" role="img" aria-label={`Radar chart comparing ${charted.length} deals across ${AXES.length} normalized dimensions. See the table above for exact values.`}>
              <ResponsiveContainer>
                <RadarChart data={data} outerRadius="72%" margin={{ top: 8, right: 24, bottom: 8, left: 24 }}>
                  <PolarGrid stroke="var(--chart-grid)" />
                  <PolarAngleAxis dataKey="axis" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
                  <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} tickCount={5} />
                  <Tooltip content={<RadarTooltip />} />
                  {charted.map((r, i) => (
                    <Radar
                      key={r.property_id}
                      name={stripDemo(r.name)}
                      dataKey={r.property_id}
                      stroke={SERIES[i]}
                      fill={SERIES[i]}
                      fillOpacity={0.12}
                      strokeWidth={2}
                      dot={{ r: 2.5, fill: SERIES[i], strokeWidth: 0 }}
                      isAnimationActive={false}
                    />
                  ))}
                </RadarChart>
              </ResponsiveContainer>
            </div>
            <figcaption className="text-xs text-muted-foreground">
              Scores are relative to the selected deals: for each dimension the best deal scores 100 and the weakest 0
              (min–max scaling); equal values score 50 and missing values plot at 0. “Low risk” is 100 − risk score.
              {rows.length > charted.length &&
                ` The chart shows the first ${charted.length} selected deals; all ${rows.length} appear in the table.`}
            </figcaption>
          </figure>
        )}
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------ risk factors
function RiskFactors({
  rows,
  colorOf,
  className,
}: {
  rows: CompareRow[];
  colorOf: (id: string) => string | undefined;
  className?: string;
}) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle>Key risk factors</CardTitle>
        <CardDescription>Largest contributors to each deal&apos;s risk score.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {rows.map((r) => {
          const factors = [...(r.risk_factors ?? [])].sort((a, b) => b.points - a.points).slice(0, 4);
          const color = colorOf(r.property_id);
          return (
            <section key={r.property_id} aria-labelledby={`rf-${r.property_id}`}>
              <div className="flex items-center gap-2">
                {color && <span className="size-2.5 shrink-0 rounded-[3px]" style={{ background: color }} aria-hidden />}
                <h4 id={`rf-${r.property_id}`} className="min-w-0 truncate text-sm font-medium">
                  {stripDemo(r.name)}
                </h4>
                {r.is_demo && <DemoBadge />}
                <span className="ml-auto shrink-0">
                  <RiskBadge level={r.risk_level} score={r.risk_score} />
                </span>
              </div>
              {factors.length === 0 ? (
                <p className="mt-1 text-xs text-muted-foreground">
                  {r.result_id ? "No risk factors flagged." : "Not calculated yet."}
                </p>
              ) : (
                <ul className="mt-1.5 space-y-1">
                  {factors.map((f, i) => (
                    <li key={`${f.factor}-${i}`} className="flex items-start gap-2 text-xs">
                      <span className="mt-1.5 size-1 shrink-0 rounded-full bg-muted-foreground" aria-hidden />
                      <span className="min-w-0 flex-1 text-muted-foreground">{f.message}</span>
                      <span className="shrink-0 tabular text-foreground">+{num(f.points)}</span>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          );
        })}
      </CardContent>
    </Card>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<LoadingBlock rows={6} />}>
      <CompareInner />
    </Suspense>
  );
}
