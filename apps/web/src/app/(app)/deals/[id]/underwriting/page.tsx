"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Calculator, ChevronDown, Plus, RotateCcw, Save, Trash2 } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { Callout, ErrorBlock, LoadingBlock } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { CashFlowChart, CashFlowTable, ExitSummary, HeadlineMetrics, RiskPanel, SectionCard, SourcesUses } from "@/components/deal-widgets";
import { NumberField } from "@/components/fields";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/overlays";
import { Badge, Card, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey, useScenarioResult } from "@/hooks/queries";
import { api, ApiError } from "@/lib/api";
import { isNum, pct, usd } from "@/lib/format";
import type { Assumptions, Loan, Scenario, UnderwritingResult } from "@/lib/types";
import { cn } from "@/lib/utils";

type Errors = Record<string, string>;

function Section({ title, children, defaultOpen = true }: { title: string; children: React.ReactNode; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="border-b last:border-0">
      <button
        type="button"
        className="flex w-full items-center justify-between px-4 py-3 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground hover:text-foreground"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        {title}
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="space-y-3 px-4 pb-4">{children}</div>}
    </div>
  );
}

const DEFAULT_LOAN: Loan = {
  name: "Senior loan",
  loan_type: "permanent",
  rate_type: "fixed",
  ltv: 0.6,
  amount: null,
  interest_rate: 0.06,
  index_rate: 0,
  spread: 0,
  amortization_years: 30,
  term_years: 10,
  io_years: 0,
  origination_fee_pct: 0.01,
  exit_fee_pct: 0,
};

export default function UnderwritingPage() {
  const { scenarios, base } = useDeal();
  const [scenarioId, setScenarioId] = useState(base?.id ?? "");
  const scenario = scenarios.find((s) => s.id === scenarioId) ?? base;
  if (!scenario) return null;
  // Keyed by scenario version: switching scenarios or saving re-initialises the editor cleanly.
  return <Editor key={`${scenario.id}:${scenario.updated_at}`} scenario={scenario} onScenarioChange={setScenarioId} />;
}

function Editor({ scenario, onScenarioChange }: { scenario: Scenario; onScenarioChange: (id: string) => void }) {
  const { property, scenarios, canEdit } = useDeal();
  const setScenarioId = onScenarioChange;
  const stored = useScenarioResult(scenario.id);
  const [draft, setDraft] = useState<Assumptions>(() => structuredClone(scenario.assumptions));
  const [preview, setPreview] = useState<UnderwritingResult | null>(null);
  const [errors, setErrors] = useState<Errors>({});
  const [calcError, setCalcError] = useState<string | null>(null);
  const [calculating, setCalculating] = useState(false);
  const qc = useQueryClient();
  const org = useOrgKey();
  const seq = useRef(0);

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(scenario.assumptions), [draft, scenario]);

  // Debounced live recalculation through the deterministic engine.
  useEffect(() => {
    if (!dirty) return;
    const mySeq = ++seq.current;
    const t = setTimeout(async () => {
      setCalculating(true);
      try {
        const r = await api<UnderwritingResult>("/api/underwriting/calculate", {
          body: { assumptions: draft, property_type: property.property_type },
        });
        if (mySeq === seq.current) {
          setPreview(r);
          setErrors({});
          setCalcError(null);
        }
      } catch (e) {
        if (mySeq !== seq.current) return;
        if (e instanceof ApiError && e.status === 422) {
          const map: Errors = {};
          e.fieldErrors.forEach((fe) => (map[fe.field] = fe.message));
          setErrors(map);
          setCalcError(e.fieldErrors.length ? null : e.message);
        } else setCalcError(e instanceof Error ? e.message : String(e));
      } finally {
        if (mySeq === seq.current) setCalculating(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [draft, dirty, property.property_type]);

  const save = useMutation({
    mutationFn: () => api(`/api/scenarios/${scenario.id}`, { method: "PATCH", body: { assumptions: draft } }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: [org] });
      toast.success("Assumptions saved — underwriting re-run and snapshot stored.");
    },
    onError: (e) => toast.error(e.message),
  });

  if (stored.isLoading) return <LoadingBlock rows={8} />;
  if (stored.error) return <ErrorBlock error={stored.error} />;
  const result: UnderwritingResult | undefined = (dirty && preview) || stored.data;
  const set = <K extends keyof Assumptions>(k: K, v: Assumptions[K]) => setDraft({ ...draft, [k]: v });
  const setLoan = (patch: Partial<Loan>) => setDraft({ ...draft, loan: { ...(draft.loan ?? DEFAULT_LOAN), ...patch } });
  const loan = draft.loan;
  const hasErrors = dirty && Object.keys(errors).length > 0;

  return (
    <div className="grid gap-5 xl:grid-cols-[400px_minmax(0,1fr)]">
      {/* ----------------------------------------------------------- Editor */}
      <div className="xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto">
        <Card className="overflow-hidden">
          <div className="space-y-3 border-b bg-muted/40 p-4">
            <div className="flex items-center gap-2">
              <Label htmlFor="uw-scenario" className="shrink-0">
                Scenario
              </Label>
              <Select id="uw-scenario" value={scenario.id} onChange={(e) => setScenarioId(e.target.value)}>
                {scenarios.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.name}
                    {s.is_base ? " (base)" : ""}
                  </option>
                ))}
              </Select>
            </div>
            <div className="flex items-center gap-2">
              {dirty ? (
                <Badge variant="warning">Unsaved changes · live preview</Badge>
              ) : (
                <Badge variant="success">Saved · matches stored snapshot</Badge>
              )}
              {calculating && <span className="text-xs text-muted-foreground">Calculating…</span>}
              <div className="ml-auto flex gap-1.5">
                <Button size="sm" variant="ghost" disabled={!dirty} onClick={() => setDraft(structuredClone(scenario.assumptions))}>
                  <RotateCcw /> Discard
                </Button>
                {canEdit && (
                  <Button size="sm" disabled={!dirty || hasErrors} loading={save.isPending} onClick={() => save.mutate()}>
                    <Save /> Save
                  </Button>
                )}
              </div>
            </div>
            {!canEdit && <p className="text-xs text-muted-foreground">Viewer access: you can explore what-ifs but not save them.</p>}
          </div>

          <Section title="Acquisition">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Purchase price" kind="usd" value={draft.purchase_price} onChange={(v) => set("purchase_price", v ?? 0)} error={errors.purchase_price} className="col-span-2" />
              <NumberField label="Hold period (yrs)" kind="int" value={draft.hold_period_years} onChange={(v) => set("hold_period_years", v ?? 0)} error={errors.hold_period_years} />
              <NumberField label="Closing costs" kind="pct" value={draft.closing_costs_pct} onChange={(v) => set("closing_costs_pct", v ?? 0)} error={errors.closing_costs_pct} />
              <NumberField label="Upfront capex" kind="usd" value={draft.upfront_capex} onChange={(v) => set("upfront_capex", v ?? 0)} error={errors.capex} />
              <NumberField label="Units" kind="int" value={draft.units ?? null} nullable onChange={(v) => set("units", v)} />
              <NumberField label="Rentable SF" kind="num" value={draft.rentable_sf ?? null} nullable onChange={(v) => set("rentable_sf", v)} error={errors.rentable_sf} />
            </div>
          </Section>

          <Section title="Revenue">
            <div className="space-y-1">
              <Label htmlFor="rev-mode">Revenue basis</Label>
              <Select id="rev-mode" value={draft.revenue_mode} onChange={(e) => set("revenue_mode", e.target.value as Assumptions["revenue_mode"])}>
                <option value="unit_mix">Unit mix (rent roll)</option>
                <option value="per_sf">Rent per SF</option>
                <option value="lump_sum">Gross potential rent (lump sum)</option>
              </Select>
            </div>
            {draft.revenue_mode === "unit_mix" && <UnitMixEditor draft={draft} set={set} error={errors.unit_mix} />}
            {draft.revenue_mode === "per_sf" && (
              <NumberField label="Rent per SF (annual)" kind="usd" value={draft.rent_psf_annual} onChange={(v) => set("rent_psf_annual", v ?? 0)} error={errors.rent_psf_annual} />
            )}
            {draft.revenue_mode === "lump_sum" && (
              <NumberField label="Gross potential rent (Y1)" kind="usd" value={draft.gross_potential_rent} onChange={(v) => set("gross_potential_rent", v ?? 0)} error={errors.gross_potential_rent} />
            )}
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Rent growth" kind="pct" value={draft.rent_growth} onChange={(v) => set("rent_growth", v ?? 0)} error={errors.rent_growth} />
              <NumberField label="Vacancy" kind="pct" value={draft.vacancy_rate} onChange={(v) => set("vacancy_rate", v ?? 0)} error={errors.vacancy_rate} />
              <NumberField label="Credit loss" kind="pct" value={draft.credit_loss_rate} onChange={(v) => set("credit_loss_rate", v ?? 0)} error={errors.credit_loss_rate} />
              <NumberField label="Other income (Y1)" kind="usd" value={draft.other_income} onChange={(v) => set("other_income", v ?? 0)} error={errors.other_income} />
              <NumberField label="Other income growth" kind="pct" value={draft.other_income_growth} onChange={(v) => set("other_income_growth", v ?? 0)} />
            </div>
            <GrowthSchedule draft={draft} set={set} error={errors.rent_growth_by_year} />
          </Section>

          <Section title="Operating expenses">
            <div className="space-y-1">
              <Label htmlFor="opex-mode">Expense basis</Label>
              <Select id="opex-mode" value={draft.opex_mode} onChange={(e) => set("opex_mode", e.target.value as Assumptions["opex_mode"])}>
                <option value="line_items">Line items</option>
                <option value="ratio">Percent of EGI</option>
              </Select>
            </div>
            {draft.opex_mode === "ratio" ? (
              <NumberField label="Opex ratio (% of EGI)" kind="pct" value={draft.opex_ratio} onChange={(v) => set("opex_ratio", v ?? 0)} error={errors.opex_ratio} />
            ) : (
              <ExpenseEditor draft={draft} set={set} />
            )}
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Management fee (% EGI)" kind="pct" value={draft.management_fee_pct} onChange={(v) => set("management_fee_pct", v ?? 0)} error={errors.management_fee_pct} />
              <NumberField label="Expense growth" kind="pct" value={draft.opex_growth} onChange={(v) => set("opex_growth", v ?? 0)} error={errors.opex_growth} />
              <NumberField label="Capital reserve (Y1)" kind="usd" value={draft.capex_reserve_annual} onChange={(v) => set("capex_reserve_annual", v ?? 0)} />
              <NumberField label="Reserve growth" kind="pct" value={draft.capex_growth} onChange={(v) => set("capex_growth", v ?? 0)} error={errors.capex_growth} />
            </div>
          </Section>

          <Section title="Exit & discounting">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Exit cap rate" kind="pct" value={draft.exit_cap_rate} onChange={(v) => set("exit_cap_rate", v ?? 0)} error={errors.exit_cap_rate} />
              <NumberField label="Selling costs" kind="pct" value={draft.selling_costs_pct} onChange={(v) => set("selling_costs_pct", v ?? 0)} error={errors.selling_costs_pct} />
              <NumberField label="Discount rate" kind="pct" value={draft.discount_rate} onChange={(v) => set("discount_rate", v ?? 0)} error={errors.discount_rate} />
            </div>
          </Section>

          <Section title="Financing">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" className="accent-[var(--accent)]" checked={!!loan} onChange={(e) => set("loan", e.target.checked ? { ...DEFAULT_LOAN } : null)} />
              Senior loan
            </label>
            {loan && (
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2 space-y-1">
                  <Label htmlFor="loan-sizing">Sizing</Label>
                  <Select
                    id="loan-sizing"
                    value={loan.amount !== null && loan.amount !== undefined ? "amount" : "ltv"}
                    onChange={(e) =>
                      setLoan(
                        e.target.value === "amount"
                          ? { amount: Math.round((loan.ltv ?? 0.6) * draft.purchase_price), ltv: null }
                          : { ltv: (loan.amount ?? 0) / draft.purchase_price || 0.6, amount: null },
                      )
                    }
                  >
                    <option value="ltv">By LTV</option>
                    <option value="amount">Fixed amount</option>
                  </Select>
                </div>
                {loan.amount !== null && loan.amount !== undefined ? (
                  <NumberField label="Loan amount" kind="usd" value={loan.amount} onChange={(v) => setLoan({ amount: v ?? 0 })} error={errors["loan.amount"]} className="col-span-2" />
                ) : (
                  <NumberField label="LTV" kind="pct" value={loan.ltv ?? 0} onChange={(v) => setLoan({ ltv: v ?? 0 })} error={errors["loan.ltv"] ?? errors["loan.amount"]} />
                )}
                <div className="space-y-1">
                  <Label htmlFor="loan-rt">Rate type</Label>
                  <Select id="loan-rt" value={loan.rate_type ?? "fixed"} onChange={(e) => setLoan({ rate_type: e.target.value as "fixed" | "floating" })}>
                    <option value="fixed">Fixed</option>
                    <option value="floating">Floating</option>
                  </Select>
                </div>
                {loan.rate_type === "floating" ? (
                  <>
                    <NumberField label="Index rate" kind="pct" value={loan.index_rate ?? 0} onChange={(v) => setLoan({ index_rate: v ?? 0 })} error={errors["loan.interest_rate"]} />
                    <NumberField label="Spread" kind="pct" value={loan.spread ?? 0} onChange={(v) => setLoan({ spread: v ?? 0 })} />
                  </>
                ) : (
                  <NumberField label="Interest rate" kind="pct" value={loan.interest_rate ?? 0} onChange={(v) => setLoan({ interest_rate: v ?? 0 })} error={errors["loan.interest_rate"]} />
                )}
                <NumberField label="Amortization (yrs, 0=IO)" kind="int" value={loan.amortization_years ?? 30} onChange={(v) => setLoan({ amortization_years: v ?? 0 })} error={errors["loan.amortization_years"]} />
                <NumberField label="Term (yrs)" kind="int" value={loan.term_years ?? 10} onChange={(v) => setLoan({ term_years: v ?? 1 })} error={errors["loan.term_years"]} />
                <NumberField label="Interest-only (yrs)" kind="num" value={loan.io_years ?? 0} onChange={(v) => setLoan({ io_years: v ?? 0 })} error={errors["loan.io_years"]} />
                <NumberField label="Origination fee" kind="pct" value={loan.origination_fee_pct ?? 0} onChange={(v) => setLoan({ origination_fee_pct: v ?? 0 })} error={errors["loan.fees"]} />
                <NumberField label="Min DSCR covenant" kind="num" value={loan.min_dscr_covenant ?? null} nullable onChange={(v) => setLoan({ min_dscr_covenant: v })} />
              </div>
            )}
            <p className="text-[11px] text-muted-foreground">Compare and activate alternative structures in the Financing tab.</p>
          </Section>
        </Card>
      </div>

      {/* ---------------------------------------------------------- Results */}
      <div className="min-w-0 space-y-5">
        {dirty && calcError && <Callout tone="danger">{calcError}</Callout>}
        {hasErrors && (
          <Callout tone="danger" title="Invalid assumptions – results show the last valid calculation">
            {Object.entries(errors).map(([k, v]) => (
              <div key={k}>
                <span className="font-mono text-xs">{k}</span>: {v}
              </div>
            ))}
          </Callout>
        )}
        {result && (
          <>
            <div className={cn("transition-opacity", calculating && "opacity-60")}>
              <HeadlineMetrics r={result} />
            </div>
            {dirty && preview && (
              <p className="text-xs text-muted-foreground">
                Live preview computed in {result.calc_ms.toFixed(1)} ms by engine v{result.engine_version}. Save to store an auditable snapshot.
              </p>
            )}
            <Tabs defaultValue="cashflow">
              <TabsList>
                <TabsTrigger value="cashflow">Cash flow</TabsTrigger>
                <TabsTrigger value="capital">Capital & exit</TabsTrigger>
                <TabsTrigger value="debt">Debt schedule</TabsTrigger>
                <TabsTrigger value="audit">Audit trace</TabsTrigger>
              </TabsList>
              <TabsContent value="cashflow" className="mt-4 space-y-4">
                <SectionCard title="NOI and cash flow to equity">
                  <CashFlowChart r={result} />
                </SectionCard>
                <Card>
                  <CashFlowTable r={result} showDetail />
                </Card>
              </TabsContent>
              <TabsContent value="capital" className="mt-4 grid gap-4 lg:grid-cols-2">
                <SectionCard title="Sources & uses">
                  <SourcesUses r={result} />
                </SectionCard>
                <SectionCard title={`Exit · year ${result.exit.exit_year}`}>
                  <ExitSummary r={result} />
                </SectionCard>
                <SectionCard title="Risk screen" className="lg:col-span-2">
                  <RiskPanel r={result} />
                </SectionCard>
                <SectionCard title="Cash flow vectors" description="Year 0 … N, used for IRR / NPV." className="lg:col-span-2">
                  <Table className="text-xs">
                    <THead>
                      <TR>
                        <TH />
                        {result.levered_cash_flows.map((_, i) => (
                          <TH key={i} className="text-right">
                            Y{i}
                          </TH>
                        ))}
                      </TR>
                    </THead>
                    <TBody>
                      {(
                        [
                          ["Unlevered", result.unlevered_cash_flows],
                          ["Levered", result.levered_cash_flows],
                        ] as const
                      ).map(([k, row]) => (
                        <TR key={k}>
                          <TD className="font-medium">{k}</TD>
                          {row.map((v, i) => (
                            <TD key={i} className="text-right tabular">
                              {usd(v)}
                            </TD>
                          ))}
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </SectionCard>
              </TabsContent>
              <TabsContent value="debt" className="mt-4">
                <Card>
                  {result.debt_schedule.length === 0 ? (
                    <p className="p-5 text-sm text-muted-foreground">No senior debt in this scenario.</p>
                  ) : (
                    <Table className="text-xs">
                      <THead>
                        <TR>
                          {["Year", "Beginning balance", "Interest", "Principal", "Debt service", "Ending balance", "DSCR", "Debt yield"].map((h) => (
                            <TH key={h} className={h === "Year" ? "" : "text-right"}>
                              {h}
                            </TH>
                          ))}
                        </TR>
                      </THead>
                      <TBody>
                        {result.debt_schedule.map((d, i) => (
                          <TR key={d.year}>
                            <TD>{d.year}</TD>
                            <TD className="text-right">{usd(d.beginning_balance)}</TD>
                            <TD className="text-right">{usd(d.interest)}</TD>
                            <TD className="text-right">{usd(d.principal)}</TD>
                            <TD className="text-right font-medium">{usd(d.debt_service)}</TD>
                            <TD className="text-right">{usd(d.ending_balance)}</TD>
                            <TD className="text-right">{isNum(result.annual[i]?.dscr) ? `${result.annual[i].dscr!.toFixed(2)}x` : "—"}</TD>
                            <TD className="text-right">{pct(result.annual[i]?.debt_yield)}</TD>
                          </TR>
                        ))}
                      </TBody>
                    </Table>
                  )}
                </Card>
              </TabsContent>
              <TabsContent value="audit" className="mt-4">
                <Card>
                  <div className="flex items-center gap-2 border-b px-5 py-3 text-xs text-muted-foreground">
                    <Calculator className="size-4" /> Every headline figure with the formula and inputs the engine used.
                  </div>
                  <Table className="text-xs">
                    <THead>
                      <TR>
                        <TH>Metric</TH>
                        <TH>Formula</TH>
                        <TH className="text-right">Value</TH>
                      </TR>
                    </THead>
                    <TBody>
                      {result.audit_trace.map((t) => (
                        <TR key={t.metric}>
                          <TD className="font-medium">{t.metric}</TD>
                          <TD>
                            <div>{t.formula}</div>
                            {t.inputs && !Array.isArray(t.inputs) && Object.keys(t.inputs).length > 0 && !("cash_flows" in t.inputs) && (
                              <div className="mt-0.5 text-muted-foreground">
                                {Object.entries(t.inputs)
                                  .map(([k, v]) => `${k} = ${typeof v === "number" ? (Math.abs(v) < 1 ? v.toFixed(4) : usd(v)) : String(v)}`)
                                  .join(" · ")}
                              </div>
                            )}
                          </TD>
                          <TD className="text-right font-medium tabular">
                            {typeof t.value === "number" ? (Math.abs(t.value) < 10 ? t.value.toFixed(4) : usd(t.value)) : "—"}
                          </TD>
                        </TR>
                      ))}
                    </TBody>
                  </Table>
                </Card>
              </TabsContent>
            </Tabs>
          </>
        )}
      </div>
    </div>
  );
}

type Setter = <K extends keyof Assumptions>(k: K, v: Assumptions[K]) => void;

function UnitMixEditor({ draft, set, error }: { draft: Assumptions; set: Setter; error?: string }) {
  const mix = draft.unit_mix;
  const update = (i: number, patch: Partial<Assumptions["unit_mix"][number]>) =>
    set("unit_mix", mix.map((u, j) => (j === i ? { ...u, ...patch } : u)));
  const total = mix.reduce((s, u) => s + (u.units || 0), 0);
  const gpr = mix.reduce((s, u) => s + (u.units || 0) * (u.in_place_rent_monthly || 0) * 12, 0);
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_64px_92px_28px] gap-1.5 text-[11px] font-medium text-muted-foreground">
        <span>Unit type</span>
        <span>Units</span>
        <span>Rent / mo</span>
        <span />
      </div>
      {mix.map((u, i) => (
        <div key={i} className="grid grid-cols-[1fr_64px_92px_28px] items-center gap-1.5">
          <Input className="h-8 text-xs" value={u.name} aria-label={`Unit type ${i + 1} name`} onChange={(e) => update(i, { name: e.target.value })} />
          <NumberField compact label={`Units for ${u.name}`} kind="int" value={u.units} onChange={(v) => update(i, { units: v ?? 0 })} />
          <NumberField compact label={`Rent for ${u.name}`} kind="num" value={u.in_place_rent_monthly} onChange={(v) => update(i, { in_place_rent_monthly: v ?? 0 })} />
          <Button size="icon-sm" variant="ghost" aria-label={`Remove ${u.name}`} onClick={() => set("unit_mix", mix.filter((_, j) => j !== i))}>
            <Trash2 />
          </Button>
        </div>
      ))}
      <div className="flex items-center justify-between">
        <Button size="sm" variant="ghost" onClick={() => set("unit_mix", [...mix, { name: "New type", units: 1, in_place_rent_monthly: 1000 }])}>
          <Plus /> Add unit type
        </Button>
        <span className="text-xs text-muted-foreground tabular">
          {total} units · GPR {usd(gpr)}
        </span>
      </div>
      {error && <p className="text-[11px] text-destructive">{error}</p>}
    </div>
  );
}

function ExpenseEditor({ draft, set }: { draft: Assumptions; set: Setter }) {
  const lines = draft.expense_lines;
  const update = (i: number, patch: Partial<Assumptions["expense_lines"][number]>) =>
    set("expense_lines", lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_104px_64px_28px] gap-1.5 text-[11px] font-medium text-muted-foreground">
        <span>Line item</span>
        <span>Year 1</span>
        <span>Growth</span>
        <span />
      </div>
      {lines.map((l, i) => (
        <div key={i} className="grid grid-cols-[1fr_104px_64px_28px] items-center gap-1.5">
          <Input className="h-8 text-xs" value={l.name} aria-label={`Expense ${i + 1} name`} onChange={(e) => update(i, { name: e.target.value })} />
          <NumberField compact label={`${l.name} amount`} kind="num" value={l.amount_annual} onChange={(v) => update(i, { amount_annual: v ?? 0 })} />
          <NumberField compact label={`${l.name} growth`} kind="pct" value={l.growth ?? null} nullable onChange={(v) => update(i, { growth: v })} />
          <Button size="icon-sm" variant="ghost" aria-label={`Remove ${l.name}`} onClick={() => set("expense_lines", lines.filter((_, j) => j !== i))}>
            <Trash2 />
          </Button>
        </div>
      ))}
      <div className="flex items-center justify-between">
        <Button size="sm" variant="ghost" onClick={() => set("expense_lines", [...lines, { name: "New expense", amount_annual: 0 }])}>
          <Plus /> Add line
        </Button>
        <span className="text-xs text-muted-foreground tabular">Total {usd(lines.reduce((s, l) => s + (l.amount_annual || 0), 0))}</span>
      </div>
      <p className="text-[11px] text-muted-foreground">Blank growth uses the default expense growth rate.</p>
    </div>
  );
}

function GrowthSchedule({ draft, set, error }: { draft: Assumptions; set: Setter; error?: string }) {
  const schedule = draft.rent_growth_by_year ?? [];
  const years = Math.max(0, draft.hold_period_years);
  const [open, setOpen] = useState(schedule.length > 0);
  if (!open)
    return (
      <Button size="sm" variant="link" onClick={() => setOpen(true)}>
        Add year-specific rent growth
      </Button>
    );
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <Label>Year-specific rent growth (overrides default)</Label>
        <Button
          size="sm"
          variant="link"
          onClick={() => {
            set("rent_growth_by_year", null);
            setOpen(false);
          }}
        >
          Clear
        </Button>
      </div>
      <div className="grid grid-cols-4 gap-1.5">
        {Array.from({ length: years }).map((_, i) => (
          <NumberField
            key={i}
            label={`Y${i + 2}`}
            kind="pct"
            nullable
            value={schedule[i] ?? null}
            onChange={(v) => {
              const next = [...schedule];
              while (next.length <= i) next.push(draft.rent_growth);
              next[i] = v ?? draft.rent_growth;
              set("rent_growth_by_year", next);
            }}
          />
        ))}
      </div>
      {error && <p className="text-[11px] text-destructive">{error}</p>}
    </div>
  );
}
