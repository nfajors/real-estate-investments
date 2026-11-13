"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Landmark, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { AXIS_PROPS, BAR_RADIUS, ChartTooltip, GRID_PROPS, SERIES } from "@/components/charts";
import { Callout, EmptyState, ErrorBlock, LoadingBlock } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, Switch } from "@/components/ui/overlays";
import {
  Badge,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Select,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui/primitives";
import { Tooltip as UiTooltip } from "@/components/ui/tooltip";
import { useFeature, useFinancing, useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { isNum, mult, pct, usd, usdShort } from "@/lib/format";
import type { Financing, Flag } from "@/lib/types";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------------ types
interface Breach {
  year: number;
  covenant: string;
  threshold: number;
  actual: number;
}

interface CompareRow {
  name: string;
  loan_amount: number;
  preferred_equity: number;
  equity_invested: number;
  ltv: number | null;
  ltc: number | null;
  rate: number | null;
  debt_service_year1: number;
  dscr_year1: number | null;
  min_dscr: number | null;
  debt_yield_year1: number | null;
  cash_on_cash_year1: number | null;
  irr_levered: number | null;
  equity_multiple_levered: number | null;
  npv_levered: number;
  balloon_at_exit: number;
  covenant_breaches: Breach[];
  warnings: Flag[];
  financing_id: string | null;
  is_active: boolean;
}

type Better = "high" | "low" | null;

const METRIC_ROWS: { key: keyof CompareRow; label: string; fmt: (v: number | null) => string; better: Better; hint?: string }[] = [
  { key: "loan_amount", label: "Senior loan", fmt: (v) => usd(v), better: null },
  { key: "preferred_equity", label: "Preferred equity", fmt: (v) => usd(v), better: null },
  { key: "equity_invested", label: "Common equity invested", fmt: (v) => usd(v), better: null },
  { key: "ltv", label: "LTV", fmt: (v) => pct(v, 1), better: "low" },
  { key: "ltc", label: "LTC", fmt: (v) => pct(v, 1), better: "low" },
  { key: "rate", label: "All-in rate", fmt: (v) => pct(v, 2), better: "low" },
  { key: "debt_service_year1", label: "Debt service (Yr 1)", fmt: (v) => usd(v), better: null },
  { key: "dscr_year1", label: "DSCR (Yr 1)", fmt: (v) => mult(v), better: "high" },
  { key: "min_dscr", label: "Minimum DSCR", fmt: (v) => mult(v), better: "high", hint: "Lowest annual DSCR across the hold." },
  { key: "debt_yield_year1", label: "Debt yield (Yr 1)", fmt: (v) => pct(v, 2), better: "high" },
  { key: "cash_on_cash_year1", label: "Cash-on-cash (Yr 1)", fmt: (v) => pct(v, 2), better: "high" },
  { key: "irr_levered", label: "Levered IRR", fmt: (v) => pct(v, 2), better: "high" },
  { key: "equity_multiple_levered", label: "Equity multiple", fmt: (v) => mult(v), better: "high" },
  { key: "npv_levered", label: "Levered NPV", fmt: (v) => usd(v), better: "high" },
  { key: "balloon_at_exit", label: "Balloon at exit", fmt: (v) => usd(v), better: null },
];

const TYPE_LABEL: Record<Financing["type"], string> = {
  permanent: "Permanent",
  bridge: "Bridge",
  construction: "Construction",
  interest_only: "Interest-only",
};

const COVENANT_LABEL: Record<string, string> = { min_dscr: "Minimum DSCR", max_ltv: "Maximum LTV" };

function fmtCovenant(covenant: string, v: number) {
  return covenant === "max_ltv" ? pct(v, 1) : mult(v);
}

/** Best values among actual financing structures (the all-cash reference column is excluded). */
function bestValues(rows: CompareRow[]): Partial<Record<keyof CompareRow, number>> {
  const levered = rows.filter((r) => r.financing_id);
  const out: Partial<Record<keyof CompareRow, number>> = {};
  if (levered.length < 2) return out;
  for (const m of METRIC_ROWS) {
    if (!m.better) continue;
    const vals = levered.map((r) => r[m.key]).filter(isNum);
    if (vals.length < 2 || new Set(vals).size < 2) continue;
    out[m.key] = m.better === "high" ? Math.max(...vals) : Math.min(...vals);
  }
  return out;
}

// ------------------------------------------------------------------- page
export default function FinancingPage() {
  const { property, canEdit } = useDeal();
  const org = useOrgKey();
  const qc = useQueryClient();
  const compareEnabled = useFeature("financing_compare");
  const structures = useFinancing(property.id);
  const compare = useQuery({
    queryKey: [org, "financing-compare", property.id],
    queryFn: () => api<CompareRow[]>(`/api/properties/${property.id}/financing/compare`),
    enabled: compareEnabled === true,
  });

  const [editing, setEditing] = useState<Financing | "new" | null>(null);
  const [confirm, setConfirm] = useState<{ kind: "delete" | "activate"; f: Financing } | null>(null);

  const done = (msg: string) => {
    qc.invalidateQueries({ queryKey: [org] });
    toast.success(msg);
    setConfirm(null);
  };
  const remove = useMutation({
    mutationFn: (f: Financing) => api(`/api/financing/${f.id}`, { method: "DELETE" }),
    onSuccess: () => done("Financing structure deleted"),
    onError: (e) => toast.error(e.message),
  });
  const activate = useMutation({
    mutationFn: (f: Financing) => api<Financing>(`/api/financing/${f.id}/activate`, { method: "POST" }),
    onSuccess: (f) => done(`${f.name} is now the base scenario's capital stack. Underwriting re-run.`),
    onError: (e) => toast.error(e.message),
  });

  if (structures.isLoading) return <LoadingBlock rows={6} />;
  if (structures.error) return <ErrorBlock error={structures.error} />;
  const list = structures.data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Financing structures</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Compare capital stacks against the base scenario&apos;s operations. The active structure drives the base case.
          </p>
        </div>
        {canEdit && (
          <Button onClick={() => setEditing("new")}>
            <Plus /> Add structure
          </Button>
        )}
      </div>

      {list.length === 0 ? (
        <EmptyState
          icon={Landmark}
          title="No financing structures yet"
          description="Add senior debt and optional preferred equity structures to compare leverage, coverage and levered returns side by side."
          action={
            canEdit ? (
              <Button onClick={() => setEditing("new")}>
                <Plus /> Add structure
              </Button>
            ) : undefined
          }
        />
      ) : (
        <>
          {compareEnabled === false ? (
            <Callout title="Comparison not available on this plan">
              Side-by-side financing comparison is not enabled for this workspace. Structures can still be created and activated.
            </Callout>
          ) : compare.isLoading || compareEnabled === undefined ? (
            <LoadingBlock rows={8} />
          ) : compare.error ? (
            <ErrorBlock error={compare.error} />
          ) : compare.data ? (
            <Comparison rows={compare.data} />
          ) : null}

          <TermsTable
            list={list}
            canEdit={canEdit}
            onEdit={setEditing}
            onDelete={(f) => setConfirm({ kind: "delete", f })}
            onActivate={(f) => setConfirm({ kind: "activate", f })}
          />
        </>
      )}

      {canEdit && (
        <StructureDialog
          key={editing === null ? "closed" : editing === "new" ? "new" : editing.id}
          open={editing !== null}
          initial={editing === "new" ? null : editing}
          propertyId={property.id}
          onOpenChange={(o) => !o && setEditing(null)}
        />
      )}

      <Dialog open={confirm !== null} onOpenChange={(o) => !o && setConfirm(null)}>
        {confirm && (
          <DialogContent
            title={confirm.kind === "delete" ? `Delete “${confirm.f.name}”?` : `Make “${confirm.f.name}” active?`}
            description={
              confirm.kind === "delete"
                ? "The structure is removed from this deal. The base scenario keeps its current loan terms."
                : "This replaces the base scenario's senior loan and preferred equity with this structure and re-runs underwriting. Every view of the deal will update."
            }
          >
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirm(null)}>
                Cancel
              </Button>
              {confirm.kind === "delete" ? (
                <Button variant="destructive" loading={remove.isPending} onClick={() => remove.mutate(confirm.f)}>
                  Delete structure
                </Button>
              ) : (
                <Button loading={activate.isPending} onClick={() => activate.mutate(confirm.f)}>
                  Make active
                </Button>
              )}
            </div>
          </DialogContent>
        )}
      </Dialog>
    </div>
  );
}

// ------------------------------------------------------------- comparison
function Comparison({ rows }: { rows: CompareRow[] }) {
  const best = bestValues(rows);
  const chartData = rows.filter((r) => isNum(r.irr_levered)).map((r) => ({ name: r.name, irr: r.irr_levered as number }));
  const flagged = rows.filter((r) => r.covenant_breaches.length || r.warnings.length);

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Side-by-side comparison</CardTitle>
          <CardDescription>
            Base scenario run once per structure. Best value among financing structures is highlighted; all-cash is shown for reference.
          </CardDescription>
        </CardHeader>
        <CardContent className="px-0 pb-2">
          <Table>
            <caption className="sr-only">Financing structure comparison; structures are columns, metrics are rows.</caption>
            <THead>
              <TR className="hover:bg-transparent">
                <TH scope="col" className="sticky left-0 z-10 min-w-44 bg-card pl-5">
                  Metric
                </TH>
                {rows.map((r) => (
                  <TH key={r.financing_id ?? "cash"} scope="col" className="min-w-36 text-right normal-case tracking-normal">
                    <div className="flex flex-col items-end gap-1 py-1.5">
                      <span className="text-xs font-semibold text-foreground">{r.name}</span>
                      {r.is_active ? (
                        <Badge variant="success">Active</Badge>
                      ) : !r.financing_id ? (
                        <Badge variant="outline">Reference</Badge>
                      ) : null}
                    </div>
                  </TH>
                ))}
              </TR>
            </THead>
            <TBody>
              {METRIC_ROWS.map((m) => (
                <TR key={m.key}>
                  <TH scope="row" className="sticky left-0 z-10 bg-card pl-5 text-xs font-medium normal-case tracking-normal text-foreground">
                    {m.label}
                    {m.hint && <span className="block text-[11px] font-normal text-muted-foreground">{m.hint}</span>}
                  </TH>
                  {rows.map((r) => {
                    const v = r[m.key] as number | null;
                    const isBest = r.financing_id !== null && best[m.key] !== undefined && v === best[m.key];
                    return (
                      <TD
                        key={r.financing_id ?? "cash"}
                        className={cn(
                          "text-right",
                          !r.financing_id && "text-muted-foreground",
                          isBest && "bg-success/10 font-semibold text-success",
                        )}
                      >
                        {m.fmt(v)}
                        {isBest && <span className="sr-only"> (best)</span>}
                      </TD>
                    );
                  })}
                </TR>
              ))}
              <TR>
                <TH scope="row" className="sticky left-0 z-10 bg-card pl-5 text-xs font-medium normal-case tracking-normal text-foreground">
                  Covenant breaches
                </TH>
                {rows.map((r) => (
                  <TD key={r.financing_id ?? "cash"} className="text-right">
                    {r.covenant_breaches.length ? (
                      <Badge variant="danger">{r.covenant_breaches.length} projected</Badge>
                    ) : r.financing_id ? (
                      <span className="text-xs text-muted-foreground">None</span>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TD>
                ))}
              </TR>
              <TR>
                <TH scope="row" className="sticky left-0 z-10 bg-card pl-5 text-xs font-medium normal-case tracking-normal text-foreground">
                  Warnings
                </TH>
                {rows.map((r) => (
                  <TD key={r.financing_id ?? "cash"} className="text-right">
                    {r.warnings.length ? (
                      <Badge variant="warning">{r.warnings.length}</Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">None</span>
                    )}
                  </TD>
                ))}
              </TR>
            </TBody>
          </Table>
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-5">
        <Card className="xl:col-span-3">
          <CardHeader>
            <CardTitle>Levered IRR by structure</CardTitle>
            <CardDescription>All-cash bar is the unlevered reference.</CardDescription>
          </CardHeader>
          <CardContent>
            {chartData.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted-foreground">IRR could not be computed for these structures.</p>
            ) : (
              <div className="h-64" role="img" aria-label={`Levered IRR: ${chartData.map((d) => `${d.name} ${pct(d.irr, 1)}`).join(", ")}`}>
                <ResponsiveContainer>
                  <BarChart data={chartData} barCategoryGap="35%" margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                    <CartesianGrid {...GRID_PROPS} />
                    <XAxis dataKey="name" {...AXIS_PROPS} interval={0} />
                    <YAxis {...AXIS_PROPS} axisLine={false} width={52} tickFormatter={(v: number) => pct(v, 0)} />
                    <ReferenceLine y={0} stroke="var(--chart-axis)" />
                    <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={(v) => pct(v, 2)} />} />
                    <Bar dataKey="irr" name="Levered IRR" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={40} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>
        <Card className="xl:col-span-2">
          <CardHeader>
            <CardTitle>Covenants &amp; warnings</CardTitle>
            <CardDescription>Projected breaches against each structure&apos;s covenants.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {flagged.length === 0 && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <CheckCircle2 className="size-4 text-success" aria-hidden /> No projected covenant breaches or warnings.
              </p>
            )}
            {flagged.map((r) => (
              <div key={r.financing_id ?? "cash"}>
                <div className="mb-1.5 text-sm font-medium">{r.name}</div>
                <ul className="space-y-1.5 text-sm">
                  {r.covenant_breaches.map((b, i) => (
                    <li key={`b${i}`} className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" aria-label="Covenant breach" />
                      <span className="text-muted-foreground">
                        <span className="font-medium text-foreground">Year {b.year}</span>: {COVENANT_LABEL[b.covenant] ?? b.covenant}{" "}
                        {fmtCovenant(b.covenant, b.actual)} vs covenant {fmtCovenant(b.covenant, b.threshold)}
                      </span>
                    </li>
                  ))}
                  {r.warnings.map((w, i) => (
                    <li key={`w${i}`} className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning" aria-label="Warning" />
                      <span className="text-muted-foreground">{w.message}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ terms
function TermsTable({
  list,
  canEdit,
  onEdit,
  onDelete,
  onActivate,
}: {
  list: Financing[];
  canEdit: boolean;
  onEdit: (f: Financing) => void;
  onDelete: (f: Financing) => void;
  onActivate: (f: Financing) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Structure terms</CardTitle>
        <CardDescription>Inputs for each structure. {canEdit ? "Make a structure active to apply it to the base scenario." : ""}</CardDescription>
      </CardHeader>
      <CardContent className="px-0 pb-2">
        <Table>
          <THead>
            <TR className="hover:bg-transparent">
              <TH className="pl-5">Structure</TH>
              <TH>Type</TH>
              <TH className="text-right">Sizing</TH>
              <TH className="text-right">Rate</TH>
              <TH className="text-right">Term / amort.</TH>
              <TH className="text-right">IO</TH>
              <TH className="text-right">Fees (orig. / exit)</TH>
              <TH className="text-right">Covenants</TH>
              <TH className="text-right">Pref. equity</TH>
              {canEdit && <TH className="pr-5 text-right">Actions</TH>}
            </TR>
          </THead>
          <TBody>
            {list.map((f) => (
              <TR key={f.id}>
                <TD className="pl-5">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{f.name}</span>
                    {f.is_active && <Badge variant="success">Active</Badge>}
                  </div>
                </TD>
                <TD className="text-muted-foreground">{TYPE_LABEL[f.type] ?? f.type}</TD>
                <TD className="text-right">{f.loan_amount !== null ? usdShort(f.loan_amount) : `${pct(f.ltv, 1)} LTV`}</TD>
                <TD className="text-right">
                  {f.rate_type === "floating" ? (
                    <span>
                      {pct(f.index_rate, 2)} + {pct(f.spread, 2)}
                      <span className="block text-[11px] text-muted-foreground">floating</span>
                    </span>
                  ) : (
                    <span>
                      {pct(f.interest_rate, 2)}
                      <span className="block text-[11px] text-muted-foreground">fixed</span>
                    </span>
                  )}
                </TD>
                <TD className="text-right">
                  {f.term_years} yr / {f.amortization_years ? `${f.amortization_years} yr` : "IO"}
                </TD>
                <TD className="text-right">{f.io_period ? `${f.io_period} yr` : "—"}</TD>
                <TD className="text-right">
                  {pct(f.fees?.origination_fee_pct ?? 0, 2)} / {pct(f.fees?.exit_fee_pct ?? 0, 2)}
                </TD>
                <TD className="text-right text-xs">
                  {isNum(f.covenants?.min_dscr) && <div>DSCR ≥ {mult(f.covenants.min_dscr)}</div>}
                  {isNum(f.covenants?.max_ltv) && <div>LTV ≤ {pct(f.covenants.max_ltv, 1)}</div>}
                  {!isNum(f.covenants?.min_dscr) && !isNum(f.covenants?.max_ltv) && <span className="text-muted-foreground">—</span>}
                </TD>
                <TD className="text-right">
                  {f.preferred_equity?.amount ? (
                    <span>
                      {usdShort(f.preferred_equity.amount)}
                      <span className="block text-[11px] text-muted-foreground">
                        {pct(f.preferred_equity.pref_rate, 1)} pay
                        {f.preferred_equity.accrual_rate ? ` + ${pct(f.preferred_equity.accrual_rate, 1)} accr.` : ""}
                      </span>
                    </span>
                  ) : (
                    "—"
                  )}
                </TD>
                {canEdit && (
                  <TD className="pr-5">
                    <div className="flex items-center justify-end gap-1">
                      {!f.is_active && (
                        <Button size="sm" variant="outline" onClick={() => onActivate(f)}>
                          Make active
                        </Button>
                      )}
                      <UiTooltip content="Edit">
                        <Button size="icon-sm" variant="ghost" aria-label={`Edit ${f.name}`} onClick={() => onEdit(f)}>
                          <Pencil />
                        </Button>
                      </UiTooltip>
                      <UiTooltip content="Delete">
                        <Button size="icon-sm" variant="ghost" aria-label={`Delete ${f.name}`} onClick={() => onDelete(f)}>
                          <Trash2 />
                        </Button>
                      </UiTooltip>
                    </div>
                  </TD>
                )}
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------------- form
/** Human percent string ("5.5") from a stored decimal (0.055). */
const toPctStr = (v: number | null | undefined) => (isNum(v) ? String(Number((v * 100).toFixed(6))) : "");
const toNum = (s: string) => Number(s.replace(/[$,\s]/g, ""));
const fromPctStr = (s: string) => Number((toNum(s) / 100).toFixed(10));
const filled = (s: string) => s.trim() !== "";

interface FormState {
  name: string;
  type: Financing["type"];
  rate_type: Financing["rate_type"];
  sizing: "amount" | "ltv";
  loan_amount: string;
  ltv: string;
  interest_rate: string;
  index_rate: string;
  spread: string;
  term_years: string;
  amortization_years: string;
  io_period: string;
  origination_fee_pct: string;
  exit_fee_pct: string;
  min_dscr: string;
  max_ltv: string;
  pref_on: boolean;
  pref_amount: string;
  pref_rate: string;
  pref_accrual: string;
}

function initialForm(f: Financing | null): FormState {
  if (!f)
    return {
      name: "",
      type: "permanent",
      rate_type: "fixed",
      sizing: "ltv",
      loan_amount: "",
      ltv: "65",
      interest_rate: "6.25",
      index_rate: "",
      spread: "",
      term_years: "10",
      amortization_years: "30",
      io_period: "0",
      origination_fee_pct: "1",
      exit_fee_pct: "0",
      min_dscr: "1.25",
      max_ltv: "",
      pref_on: false,
      pref_amount: "",
      pref_rate: "",
      pref_accrual: "",
    };
  return {
    name: f.name,
    type: f.type,
    rate_type: f.rate_type,
    sizing: f.loan_amount !== null ? "amount" : "ltv",
    loan_amount: f.loan_amount !== null ? f.loan_amount.toLocaleString("en-US") : "",
    ltv: toPctStr(f.ltv),
    interest_rate: toPctStr(f.interest_rate),
    index_rate: toPctStr(f.index_rate),
    spread: toPctStr(f.spread),
    term_years: String(f.term_years),
    amortization_years: String(f.amortization_years),
    io_period: String(f.io_period),
    origination_fee_pct: toPctStr(f.fees?.origination_fee_pct ?? 0),
    exit_fee_pct: toPctStr(f.fees?.exit_fee_pct ?? 0),
    min_dscr: isNum(f.covenants?.min_dscr) ? String(f.covenants.min_dscr) : "",
    max_ltv: toPctStr(f.covenants?.max_ltv),
    pref_on: !!f.preferred_equity?.amount,
    pref_amount: f.preferred_equity?.amount ? f.preferred_equity.amount.toLocaleString("en-US") : "",
    pref_rate: toPctStr(f.preferred_equity?.pref_rate),
    pref_accrual: toPctStr(f.preferred_equity?.accrual_rate),
  };
}

function toBody(s: FormState, isActive: boolean) {
  const fees: Record<string, number> = {};
  if (filled(s.origination_fee_pct)) fees.origination_fee_pct = fromPctStr(s.origination_fee_pct);
  if (filled(s.exit_fee_pct)) fees.exit_fee_pct = fromPctStr(s.exit_fee_pct);
  const covenants: Record<string, number> = {};
  if (filled(s.min_dscr)) covenants.min_dscr = toNum(s.min_dscr);
  if (filled(s.max_ltv)) covenants.max_ltv = fromPctStr(s.max_ltv);
  const floating = s.rate_type === "floating";
  return {
    name: s.name.trim(),
    type: s.type,
    rate_type: s.rate_type,
    loan_amount: s.sizing === "amount" ? toNum(s.loan_amount) : null,
    ltv: s.sizing === "ltv" ? fromPctStr(s.ltv) : null,
    interest_rate: floating ? 0 : fromPctStr(s.interest_rate),
    index_rate: floating ? fromPctStr(s.index_rate) : 0,
    spread: floating ? fromPctStr(s.spread) : 0,
    term_years: Math.round(toNum(s.term_years)),
    amortization_years: Math.round(toNum(s.amortization_years || "0")),
    io_period: toNum(s.io_period || "0"),
    fees,
    covenants,
    preferred_equity:
      s.pref_on && filled(s.pref_amount)
        ? {
            amount: toNum(s.pref_amount),
            pref_rate: filled(s.pref_rate) ? fromPctStr(s.pref_rate) : 0,
            accrual_rate: filled(s.pref_accrual) ? fromPctStr(s.pref_accrual) : 0,
          }
        : null,
    is_active: isActive,
  };
}

function validate(s: FormState): string | null {
  if (!s.name.trim()) return "Give the structure a name.";
  const nums: [string, string][] = [
    ["Term", s.term_years],
    ["Amortization", s.amortization_years || "0"],
    ["IO period", s.io_period || "0"],
  ];
  if (s.sizing === "amount") nums.push(["Loan amount", s.loan_amount]);
  else nums.push(["LTV", s.ltv]);
  if (s.rate_type === "fixed") nums.push(["Interest rate", s.interest_rate]);
  else nums.push(["Index rate", s.index_rate], ["Spread", s.spread]);
  for (const k of ["origination_fee_pct", "exit_fee_pct", "min_dscr", "max_ltv"] as const)
    if (filled(s[k])) nums.push([k, s[k]]);
  if (s.pref_on) nums.push(["Preferred equity amount", s.pref_amount]);
  for (const [label, v] of nums) {
    if (!filled(v) || !Number.isFinite(toNum(v))) return `${label.replace(/_/g, " ")} must be a number.`;
  }
  return null;
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

function StructureDialog({
  open,
  initial,
  propertyId,
  onOpenChange,
}: {
  open: boolean;
  initial: Financing | null;
  propertyId: string;
  onOpenChange: (o: boolean) => void;
}) {
  const org = useOrgKey();
  const qc = useQueryClient();
  const [s, setS] = useState<FormState>(() => initialForm(initial));
  const [error, setError] = useState<string | null>(null);
  const set =
    <K extends keyof FormState>(k: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setS((prev) => ({ ...prev, [k]: e.target.value }));

  const save = useMutation({
    mutationFn: () => {
      const body = toBody(s, initial?.is_active ?? false);
      return initial
        ? api<Financing>(`/api/financing/${initial.id}`, { method: "PUT", body })
        : api<Financing>(`/api/properties/${propertyId}/financing`, { method: "POST", body });
    },
    onSuccess: (f) => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success(
        initial
          ? f.is_active
            ? `${f.name} updated. Base scenario re-run with the new terms.`
            : `${f.name} updated`
          : `${f.name} added`,
      );
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });

  const id = (k: string) => `fin-${k}`;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        title={initial ? `Edit ${initial.name}` : "Add financing structure"}
        description="Enter percentages as whole numbers (5.5 = 5.50%). Amortization of 0 means interest-only for the full term."
        className="max-w-2xl"
      >
        <form
          noValidate
          className="space-y-5"
          onSubmit={(e) => {
            e.preventDefault();
            const msg = validate(s);
            setError(msg);
            if (!msg) save.mutate();
          }}
        >
          <fieldset className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <legend className="sr-only">Structure</legend>
            <Field id={id("name")} label="Name" inputMode="text" required value={s.name} onChange={set("name")} placeholder="e.g. Agency 10-yr fixed" className="sm:col-span-3" />
            <div className="space-y-1.5">
              <Label htmlFor={id("type")}>Loan type</Label>
              <Select id={id("type")} value={s.type} onChange={set("type")}>
                {Object.entries(TYPE_LABEL).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={id("rate-type")}>Rate type</Label>
              <Select id={id("rate-type")} value={s.rate_type} onChange={set("rate_type")}>
                <option value="fixed">Fixed</option>
                <option value="floating">Floating (index + spread)</option>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor={id("sizing")}>Size loan by</Label>
              <Select id={id("sizing")} value={s.sizing} onChange={set("sizing")}>
                <option value="ltv">Loan-to-value</option>
                <option value="amount">Loan amount</option>
              </Select>
            </div>
          </fieldset>

          <fieldset className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Senior loan</legend>
            {s.sizing === "amount" ? (
              <Field id={id("amount")} label="Loan amount" suffix="$" value={s.loan_amount} onChange={set("loan_amount")} placeholder="16,000,000" />
            ) : (
              <Field id={id("ltv")} label="LTV" suffix="%" value={s.ltv} onChange={set("ltv")} />
            )}
            {s.rate_type === "fixed" ? (
              <Field id={id("rate")} label="Interest rate" suffix="%" value={s.interest_rate} onChange={set("interest_rate")} />
            ) : (
              <>
                <Field id={id("index")} label="Index rate" suffix="%" value={s.index_rate} onChange={set("index_rate")} hint="e.g. Term SOFR" />
                <Field id={id("spread")} label="Spread" suffix="%" value={s.spread} onChange={set("spread")} />
              </>
            )}
            <Field id={id("term")} label="Term" suffix="yrs" inputMode="numeric" value={s.term_years} onChange={set("term_years")} />
            <Field id={id("amort")} label="Amortization" suffix="yrs" inputMode="numeric" value={s.amortization_years} onChange={set("amortization_years")} hint="0 = interest-only" />
            <Field id={id("io")} label="Interest-only period" suffix="yrs" value={s.io_period} onChange={set("io_period")} />
            <Field id={id("orig")} label="Origination fee" suffix="%" value={s.origination_fee_pct} onChange={set("origination_fee_pct")} />
            <Field id={id("exit")} label="Exit fee" suffix="%" value={s.exit_fee_pct} onChange={set("exit_fee_pct")} />
          </fieldset>

          <fieldset className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <legend className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Covenants (optional)</legend>
            <Field id={id("min-dscr")} label="Minimum DSCR" suffix="x" value={s.min_dscr} onChange={set("min_dscr")} placeholder="1.25" />
            <Field id={id("max-ltv")} label="Maximum LTV" suffix="%" value={s.max_ltv} onChange={set("max_ltv")} placeholder="75" />
          </fieldset>

          <fieldset className="space-y-3">
            <legend className="sr-only">Preferred equity</legend>
            <div className="flex items-center gap-3">
              <Switch
                id={id("pref-on")}
                checked={s.pref_on}
                onCheckedChange={(v) => setS((prev) => ({ ...prev, pref_on: v }))}
              />
              <Label htmlFor={id("pref-on")} className="text-sm text-foreground">
                Include preferred equity
              </Label>
            </div>
            {s.pref_on && (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <Field id={id("pref-amount")} label="Amount" suffix="$" value={s.pref_amount} onChange={set("pref_amount")} />
                <Field id={id("pref-rate")} label="Current-pay rate" suffix="%" value={s.pref_rate} onChange={set("pref_rate")} />
                <Field id={id("pref-accrual")} label="Accrual rate" suffix="%" value={s.pref_accrual} onChange={set("pref_accrual")} hint="Accrued, paid at exit" />
              </div>
            )}
          </fieldset>

          {initial?.is_active && (
            <Callout tone="warn">This is the active structure. Saving re-applies it to the base scenario and re-runs underwriting.</Callout>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              {initial ? "Save changes" : "Add structure"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
