"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Copy, Dices, Grid3x3, Plus, Star, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { AXIS_PROPS, BAR_RADIUS, ChartTooltip, divergingColor, GRID_PROPS, SERIES } from "@/components/charts";
import { Callout, LoadingBlock, Metric } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { SectionCard } from "@/components/deal-widgets";
import { NumberField } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Badge, Card, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useFeature, useOrgKey, useScenarioComparison } from "@/hooks/queries";
import { api } from "@/lib/api";
import { mult, pct, usd, usdShort } from "@/lib/format";
import { cn } from "@/lib/utils";

const AXES: Record<string, { label: string; kind: "pct" | "int" | "usd" }> = {
  rent_growth: { label: "Rent growth", kind: "pct" },
  exit_cap_rate: { label: "Exit cap rate", kind: "pct" },
  vacancy_rate: { label: "Vacancy", kind: "pct" },
  opex_growth: { label: "Expense growth", kind: "pct" },
  discount_rate: { label: "Discount rate", kind: "pct" },
  "loan.interest_rate": { label: "Interest rate", kind: "pct" },
  hold_period_years: { label: "Hold period (yrs)", kind: "int" },
  purchase_price: { label: "Purchase price", kind: "usd" },
};

const METRICS: Record<string, { label: string; kind: "pct" | "usd" | "x" }> = {
  irr_levered: { label: "Levered IRR", kind: "pct" },
  irr_unlevered: { label: "Unlevered IRR", kind: "pct" },
  equity_multiple_levered: { label: "Equity multiple", kind: "x" },
  npv_levered: { label: "NPV (levered)", kind: "usd" },
  cash_on_cash_year1: { label: "Cash-on-cash Y1", kind: "pct" },
  dscr_year1: { label: "DSCR Y1", kind: "x" },
};

const fmtAxis = (v: number, kind: string) => (kind === "pct" ? pct(v) : kind === "usd" ? usdShort(v) : String(v));
const fmtMetric = (v: number | null, kind: string) => (kind === "pct" ? pct(v) : kind === "usd" ? usdShort(v) : mult(v));

export default function ScenariosPage() {
  const { property, scenarios, canEdit } = useDeal();
  const comparison = useScenarioComparison(property.id);
  const qc = useQueryClient();
  const org = useOrgKey();
  const mcEnabled = useFeature("monte_carlo");
  const [newOpen, setNewOpen] = useState(false);

  const invalidate = () => qc.invalidateQueries({ queryKey: [org] });
  const defaults = useMutation({
    mutationFn: () => api<unknown[]>(`/api/properties/${property.id}/scenarios/defaults`, { method: "POST" }),
    onSuccess: (r) => {
      invalidate();
      toast.success(r.length ? `Created ${r.length} scenarios` : "Conservative and Optimistic cases already exist");
    },
    onError: (e) => toast.error(e.message),
  });
  const makeBase = useMutation({
    mutationFn: (id: string) => api(`/api/scenarios/${id}/make-base`, { method: "POST" }),
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/scenarios/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  });

  const rows = comparison.data ?? [];
  const chart = rows.map((r) => ({ name: r.name, irr: r.metrics?.irr_levered ?? null }));

  return (
    <div className="space-y-5">
      <SectionCard
        title="Scenario manager"
        description="Conservative / Base / Optimistic cases, or your own. Each scenario is a full assumption set with its own stored results."
        action={
          canEdit && (
            <div className="flex gap-2">
              <Button size="sm" variant="outline" onClick={() => defaults.mutate()} loading={defaults.isPending}>
                <Copy /> Create default cases
              </Button>
              <Button size="sm" onClick={() => setNewOpen(true)}>
                <Plus /> New scenario
              </Button>
            </div>
          )
        }
      >
        {comparison.isLoading ? (
          <LoadingBlock />
        ) : (
          <div className="grid gap-5 2xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Table className="text-xs">
              <THead>
                <TR className="hover:bg-transparent">
                  <TH>Scenario</TH>
                  <TH className="text-right">Rent growth</TH>
                  <TH className="text-right">Vacancy</TH>
                  <TH className="text-right">Opex growth</TH>
                  <TH className="text-right">Exit cap</TH>
                  <TH className="text-right">Lev. IRR</TH>
                  <TH className="text-right">Multiple</TH>
                  <TH className="text-right">NPV</TH>
                  <TH className="text-right">DSCR</TH>
                  <TH />
                </TR>
              </THead>
              <TBody>
                {rows.map((r) => {
                  const k = r.key_assumptions;
                  return (
                    <TR key={r.scenario_id}>
                      <TD>
                        <div className="flex items-center gap-1.5 font-medium">
                          {r.name}
                          {r.is_base && <Badge variant="accent">Base</Badge>}
                        </div>
                        <div className="max-w-56 truncate text-[11px] text-muted-foreground">
                          {scenarios.find((s) => s.id === r.scenario_id)?.description}
                        </div>
                      </TD>
                      <TD className="text-right">{pct(k.rent_growth)}</TD>
                      <TD className="text-right">{pct(k.vacancy_rate)}</TD>
                      <TD className="text-right">{pct(k.opex_growth)}</TD>
                      <TD className="text-right">{pct(k.exit_cap_rate)}</TD>
                      <TD className="text-right font-semibold">{pct(r.metrics?.irr_levered)}</TD>
                      <TD className="text-right">{mult(r.metrics?.equity_multiple)}</TD>
                      <TD className="text-right">{usdShort(r.metrics?.npv)}</TD>
                      <TD className="text-right">{mult(r.metrics?.dscr)}</TD>
                      <TD className="text-right">
                        {canEdit && !r.is_base && (
                          <div className="flex justify-end gap-1">
                            <Button size="icon-sm" variant="ghost" aria-label={`Make ${r.name} the base case`} onClick={() => makeBase.mutate(r.scenario_id)}>
                              <Star />
                            </Button>
                            <Button
                              size="icon-sm"
                              variant="ghost"
                              aria-label={`Delete ${r.name}`}
                              onClick={() => confirm(`Delete scenario ${r.name}?`) && remove.mutate(r.scenario_id)}
                            >
                              <Trash2 />
                            </Button>
                          </div>
                        )}
                      </TD>
                    </TR>
                  );
                })}
              </TBody>
            </Table>
            <div className="h-56">
              <ResponsiveContainer>
                <BarChart data={chart} layout="vertical" margin={{ left: 8, right: 16 }}>
                  <CartesianGrid {...GRID_PROPS} vertical horizontal={false} />
                  <XAxis type="number" {...AXIS_PROPS} tickFormatter={(v) => pct(v, 0)} />
                  <YAxis type="category" dataKey="name" {...AXIS_PROPS} width={96} axisLine={false} />
                  <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={(v) => pct(v)} />} />
                  <Bar dataKey="irr" name="Levered IRR" fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={22} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}
      </SectionCard>
      <Sensitivity />
      {mcEnabled === false ? (
        <Callout title="Monte Carlo simulation is not enabled for this workspace">Upgrade the plan or enable the feature in Settings.</Callout>
      ) : (
        <MonteCarlo />
      )}
      <NewScenarioDialog open={newOpen} onOpenChange={setNewOpen} />
    </div>
  );
}

interface SensTable {
  metric: string;
  row_path: string;
  row_values: number[];
  col_path: string;
  col_values: number[];
  grid: (number | null)[][];
  base_row: number;
  base_col: number;
}

function Sensitivity() {
  const { property, scenarios, base } = useDeal();
  const [scenarioId, setScenarioId] = useState(base?.id ?? "");
  const [row, setRow] = useState("rent_growth");
  const [col, setCol] = useState("exit_cap_rate");
  const [metric, setMetric] = useState("irr_levered");
  const run = useMutation({
    mutationFn: () =>
      api<SensTable>(`/api/properties/${property.id}/sensitivity`, {
        body: { scenario_id: scenarioId, row_path: row, col_path: col, metric },
      }),
    onError: (e) => toast.error(e.message),
  });
  const t = run.data;
  const flat = (t?.grid.flat().filter((v): v is number => v !== null) ?? []) as number[];
  const baseIdx = t ? [t.row_values.findIndex((v) => Math.abs(v - t.base_row) < 1e-9), t.col_values.findIndex((v) => Math.abs(v - t.base_col) < 1e-9)] : [-1, -1];
  const baseVal = t && baseIdx[0] >= 0 && baseIdx[1] >= 0 ? t.grid[baseIdx[0]][baseIdx[1]] : null;
  const spread = flat.length ? Math.max(...flat.map((v) => Math.abs(v - (baseVal ?? 0)))) : 0;
  const mk = METRICS[t?.metric ?? metric];
  const hasLoan = !!scenarios.find((s) => s.id === scenarioId)?.assumptions.loan;

  return (
    <SectionCard title="Sensitivity analysis" description="Two-way table, every cell a full engine run. The outlined cell is the scenario as entered.">
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="space-y-1">
          <Label htmlFor="s-sc">Scenario</Label>
          <Select id="s-sc" value={scenarioId} onChange={(e) => setScenarioId(e.target.value)} className="w-44">
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-row">Rows</Label>
          <Select id="s-row" value={row} onChange={(e) => setRow(e.target.value)} className="w-44">
            {Object.entries(AXES)
              .filter(([k]) => hasLoan || !k.startsWith("loan."))
              .map(([k, v]) => (
                <option key={k} value={k} disabled={k === col}>
                  {v.label}
                </option>
              ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-col">Columns</Label>
          <Select id="s-col" value={col} onChange={(e) => setCol(e.target.value)} className="w-44">
            {Object.entries(AXES)
              .filter(([k]) => hasLoan || !k.startsWith("loan."))
              .map(([k, v]) => (
                <option key={k} value={k} disabled={k === row}>
                  {v.label}
                </option>
              ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="s-metric">Output</Label>
          <Select id="s-metric" value={metric} onChange={(e) => setMetric(e.target.value)} className="w-44">
            {Object.entries(METRICS).map(([k, v]) => (
              <option key={k} value={k}>
                {v.label}
              </option>
            ))}
          </Select>
        </div>
        <Button onClick={() => run.mutate()} loading={run.isPending}>
          <Grid3x3 /> Run table
        </Button>
      </div>
      {!t && !run.isPending && <p className="text-sm text-muted-foreground">Choose two drivers and run the table.</p>}
      {t && (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-[2px] text-center text-xs tabular">
            <thead>
              <tr>
                <th className="p-2 text-left text-[11px] font-medium text-muted-foreground">
                  {AXES[t.row_path]?.label ?? t.row_path} ↓ · {AXES[t.col_path]?.label ?? t.col_path} →
                </th>
                {t.col_values.map((c) => (
                  <th key={c} className="p-2 font-semibold">
                    {fmtAxis(c, AXES[t.col_path]?.kind ?? "pct")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {t.row_values.map((rv, i) => (
                <tr key={rv}>
                  <th className="p-2 text-left font-semibold">{fmtAxis(rv, AXES[t.row_path]?.kind ?? "pct")}</th>
                  {t.grid[i].map((v, j) => {
                    const isBase = i === baseIdx[0] && j === baseIdx[1];
                    return (
                      <td
                        key={j}
                        className={cn("rounded-[4px] p-2.5 font-medium", isBase && "outline-2 outline-foreground")}
                        style={{ background: divergingColor(v, baseVal ?? 0, spread) }}
                        title={`${AXES[t.row_path]?.label} ${fmtAxis(rv, AXES[t.row_path]?.kind ?? "pct")}, ${AXES[t.col_path]?.label} ${fmtAxis(t.col_values[j], AXES[t.col_path]?.kind ?? "pct")}: ${fmtMetric(v, mk.kind)}`}
                      >
                        {fmtMetric(v, mk.kind)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 flex items-center gap-3 text-[11px] text-muted-foreground">
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-[3px]" style={{ background: "color-mix(in oklab, var(--div-neg) 70%, var(--div-mid))" }} /> Worse than as-entered
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-[3px] border" style={{ background: "var(--div-mid)" }} /> Similar
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="size-2.5 rounded-[3px]" style={{ background: "color-mix(in oklab, var(--div-pos) 70%, var(--div-mid))" }} /> Better
            </span>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

interface Summary {
  mean: number | null;
  std: number | null;
  min?: number;
  max?: number;
  percentiles: Record<string, number>;
  histogram: { bin_start: number; bin_end: number; count: number }[];
}
interface MCResult {
  iterations: number;
  completed: number;
  rejected: number;
  seed: number;
  irr_levered: Summary;
  irr_unlevered: Summary;
  npv_levered: Summary;
  equity_multiple_levered: Summary;
  prob_irr_below_discount_rate: number | null;
  prob_loss: number | null;
  distributions: { path: string; kind: string; std?: number; low?: number; high?: number }[];
}

function MonteCarlo() {
  const { property, scenarios, base } = useDeal();
  const [scenarioId, setScenarioId] = useState(base?.id ?? "");
  const [iterations, setIterations] = useState(1000);
  const [seed, setSeed] = useState(42);
  const [sd, setSd] = useState({ rent_growth: 0.01, vacancy_rate: 0.015, opex_growth: 0.0075, exit_cap_rate: 0.004 });
  const run = useMutation({
    mutationFn: () =>
      api<MCResult>(`/api/properties/${property.id}/monte-carlo`, {
        body: {
          scenario_id: scenarioId,
          iterations,
          seed,
          distributions: [
            { path: "rent_growth", kind: "normal", std: sd.rent_growth },
            { path: "vacancy_rate", kind: "normal", std: sd.vacancy_rate, low: 0, high: 0.5 },
            { path: "opex_growth", kind: "normal", std: sd.opex_growth },
            { path: "exit_cap_rate", kind: "normal", std: sd.exit_cap_rate, low: 0.03 },
          ],
        },
      }),
    onError: (e) => toast.error(e.message),
  });
  const r = run.data;
  const discount = scenarios.find((s) => s.id === scenarioId)?.assumptions.discount_rate;
  const hist = r?.irr_levered.histogram.map((h) => ({ mid: (h.bin_start + h.bin_end) / 2, label: `${pct(h.bin_start, 1)} – ${pct(h.bin_end, 1)}`, count: h.count })) ?? [];

  return (
    <SectionCard
      title="Monte Carlo simulation"
      description="Normal distributions around the scenario's own values (σ below). Seeded, so results are reproducible and auditable."
    >
      <div className="mb-4 grid gap-3 sm:grid-cols-3 lg:grid-cols-8 lg:items-end">
        <div className="space-y-1 lg:col-span-2">
          <Label htmlFor="mc-sc">Scenario</Label>
          <Select id="mc-sc" value={scenarioId} onChange={(e) => setScenarioId(e.target.value)}>
            {scenarios.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </Select>
        </div>
        <NumberField label="σ rent growth" kind="pct" value={sd.rent_growth} onChange={(v) => setSd({ ...sd, rent_growth: v ?? 0 })} />
        <NumberField label="σ vacancy" kind="pct" value={sd.vacancy_rate} onChange={(v) => setSd({ ...sd, vacancy_rate: v ?? 0 })} />
        <NumberField label="σ opex growth" kind="pct" value={sd.opex_growth} onChange={(v) => setSd({ ...sd, opex_growth: v ?? 0 })} />
        <NumberField label="σ exit cap" kind="pct" value={sd.exit_cap_rate} onChange={(v) => setSd({ ...sd, exit_cap_rate: v ?? 0 })} />
        <div className="space-y-1">
          <Label htmlFor="mc-it">Iterations</Label>
          <Select id="mc-it" value={iterations} onChange={(e) => setIterations(Number(e.target.value))}>
            {[250, 500, 1000, 2500, 5000].map((n) => (
              <option key={n} value={n}>
                {n.toLocaleString()}
              </option>
            ))}
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="mc-seed">Seed</Label>
          <Input id="mc-seed" type="number" value={seed} onChange={(e) => setSeed(Number(e.target.value))} />
        </div>
      </div>
      <Button onClick={() => run.mutate()} loading={run.isPending}>
        <Dices /> Run simulation
      </Button>
      {r && (
        <div className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <Metric label="Mean levered IRR" value={pct(r.irr_levered.mean)} sub={`σ ${pct(r.irr_levered.std)}`} />
            <Metric label="P10 / P90 IRR" value={<span className="text-base">{pct(r.irr_levered.percentiles.p10, 1)} / {pct(r.irr_levered.percentiles.p90, 1)}</span>} />
            <Metric label="Median multiple" value={mult(r.equity_multiple_levered.percentiles.p50)} />
            <Metric label="Median NPV" value={usdShort(r.npv_levered.percentiles.p50)} />
            <Metric label={`P(IRR < ${pct(discount, 1)})`} value={pct(r.prob_irr_below_discount_rate, 1)} hint="Probability the levered IRR falls short of the discount rate." />
            <Metric label="P(loss of capital)" value={pct(r.prob_loss, 1)} tone={(r.prob_loss ?? 0) > 0.1 ? "bad" : undefined} hint="Share of runs with equity multiple below 1.0x." />
          </div>
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Card className="p-4">
              <div className="mb-2 text-sm font-medium">Distribution of levered IRR</div>
              <div className="h-60">
                <ResponsiveContainer>
                  <BarChart data={hist} barCategoryGap={2}>
                    <CartesianGrid {...GRID_PROPS} />
                    <XAxis dataKey="mid" {...AXIS_PROPS} tickFormatter={(v) => pct(v, 0)} interval="preserveStartEnd" />
                    <YAxis {...AXIS_PROPS} axisLine={false} width={36} allowDecimals={false} />
                    <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={(v) => `${v} runs`} labelFormat={(l) => hist.find((h) => String(h.mid) === l)?.label ?? l} />} />
                    {r.irr_levered.percentiles.p50 !== undefined && <ReferenceLine x={hist.reduce((best, h) => (Math.abs(h.mid - r.irr_levered.percentiles.p50) < Math.abs(best - r.irr_levered.percentiles.p50) ? h.mid : best), hist[0]?.mid ?? 0)} stroke="var(--muted-foreground)" strokeDasharray="3 3" label={{ value: "P50", fill: "var(--muted-foreground)", fontSize: 10, position: "top" }} />}
                    <Bar dataKey="count" name="Runs" fill={SERIES[0]} radius={BAR_RADIUS} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
            <Card className="p-4">
              <div className="mb-2 text-sm font-medium">Percentiles</div>
              <Table className="text-xs">
                <THead>
                  <TR>
                    <TH>Pctl</TH>
                    <TH className="text-right">Lev. IRR</TH>
                    <TH className="text-right">Unlev. IRR</TH>
                    <TH className="text-right">Multiple</TH>
                    <TH className="text-right">NPV</TH>
                  </TR>
                </THead>
                <TBody>
                  {["p5", "p10", "p25", "p50", "p75", "p90", "p95"].map((p) => (
                    <TR key={p}>
                      <TD className="uppercase">{p}</TD>
                      <TD className="text-right">{pct(r.irr_levered.percentiles[p])}</TD>
                      <TD className="text-right">{pct(r.irr_unlevered.percentiles[p])}</TD>
                      <TD className="text-right">{mult(r.equity_multiple_levered.percentiles[p])}</TD>
                      <TD className="text-right">{usd(r.npv_levered.percentiles[p])}</TD>
                    </TR>
                  ))}
                </TBody>
              </Table>
              <p className="mt-2 text-[11px] text-muted-foreground">
                {r.completed.toLocaleString()} of {r.iterations.toLocaleString()} runs valid · {r.rejected} rejected (invalid sampled inputs) · seed {r.seed}
              </p>
            </Card>
          </div>
        </div>
      )}
    </SectionCard>
  );
}

function NewScenarioDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { property, scenarios, base } = useDeal();
  const qc = useQueryClient();
  const org = useOrgKey();
  const [name, setName] = useState("");
  const [from, setFrom] = useState(base?.id ?? "");
  const create = useMutation({
    mutationFn: () => api(`/api/properties/${property.id}/scenarios`, { body: { name, clone_from: from } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success("Scenario created — edit its assumptions in the Underwriting tab.");
      onOpenChange(false);
      setName("");
    },
    onError: (e) => toast.error(e.message),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New scenario" description="Starts as a copy of an existing scenario.">
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="space-y-1.5">
            <Label htmlFor="ns-name">Name</Label>
            <Input id="ns-name" required value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Value-add renovation" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="ns-from">Copy from</Label>
            <Select id="ns-from" value={from} onChange={(e) => setFrom(e.target.value)}>
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
          </div>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
