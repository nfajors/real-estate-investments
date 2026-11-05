"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FileSearch, Pencil, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Callout, ErrorBlock, LoadingBlock } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { CashFlowChart, ExitSummary, HeadlineMetrics, RiskPanel, SectionCard, SourcesUses } from "@/components/deal-widgets";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Input, Label, Select, Textarea } from "@/components/ui/primitives";
import { useOrgKey, usePropertyTypes, useScenarioComparison, useScenarioResult } from "@/hooks/queries";
import { api } from "@/lib/api";
import { dateTime, mult, pct, usd } from "@/lib/format";

export default function OverviewPage() {
  const { property: p, base, canEdit } = useDeal();
  const result = useScenarioResult(base?.id);
  const comparison = useScenarioComparison(p.id);
  const types = usePropertyTypes();
  const typeDef = types.data?.find((t) => t.key === p.property_type);
  const [editing, setEditing] = useState(false);

  if (result.isLoading) return <LoadingBlock rows={6} />;
  if (result.error) return <ErrorBlock error={result.error} />;
  if (!result.data || !base) return null;
  const r = result.data;
  const isTemplate = base.description?.startsWith("Template");

  return (
    <div className="space-y-5">
      {isTemplate && (
        <Callout tone="warn" title="Template assumptions">
          This base case still uses generic property-type defaults.{" "}
          <Link href={`/deals/${p.id}/documents`} className="font-medium text-foreground underline underline-offset-2">
            Upload offering materials
          </Link>{" "}
          and verify the extracted data, or{" "}
          <Link href={`/deals/${p.id}/underwriting`} className="font-medium text-foreground underline underline-offset-2">
            edit assumptions
          </Link>
          .
        </Callout>
      )}
      <HeadlineMetrics r={r} />
      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard
          title="Operating cash flow"
          description={`${base.name} · calculated ${dateTime(r.calculated_at)} · engine v${r.engine_version}`}
          className="xl:col-span-2"
          action={
            <Button size="sm" variant="outline" asChild>
              <Link href={`/deals/${p.id}/underwriting`}>
                <SlidersHorizontal /> Model
              </Link>
            </Button>
          }
        >
          <CashFlowChart r={r} />
        </SectionCard>
        <SectionCard title="Risk screen" description="Deterministic flags from the engine output.">
          <RiskPanel r={r} />
        </SectionCard>
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard title="Sources & uses" className="xl:col-span-2">
          <SourcesUses r={r} />
        </SectionCard>
        <SectionCard title={`Exit · year ${r.exit.exit_year}`}>
          <ExitSummary r={r} />
        </SectionCard>
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <SectionCard
          title="Property facts"
          className="xl:col-span-1"
          action={
            canEdit && (
              <Button size="sm" variant="ghost" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
            )
          }
        >
          <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
            <Fact k="Year built" v={p.year_built ?? "—"} />
            <Fact k="Units" v={p.units?.toLocaleString() ?? "—"} />
            <Fact k="Rentable SF" v={p.rentable_sf?.toLocaleString() ?? "—"} />
            <Fact k="Hold period" v={`${p.hold_period_years} years`} />
            <Fact k="Price / unit" v={usd(r.metrics.price_per_unit)} />
            <Fact k="Price / SF" v={usd(r.metrics.price_per_sf, 2)} />
            {typeDef?.fields.map((f) => {
              const v = p.attributes?.[f.key];
              if (v === undefined || v === null || v === "") return null;
              return <Fact key={f.key} k={f.label} v={f.type === "percent" && typeof v === "number" ? pct(v, 0) : String(v)} />;
            })}
          </dl>
          {p.description && <p className="mt-3 border-t pt-3 text-sm text-muted-foreground">{p.description}</p>}
        </SectionCard>
        <SectionCard
          title="Scenarios"
          description="Headline returns for each assumption set."
          className="xl:col-span-2"
          action={
            <Button size="sm" variant="outline" asChild>
              <Link href={`/deals/${p.id}/scenarios`}>Manage</Link>
            </Button>
          }
        >
          <div className="grid gap-2 sm:grid-cols-3">
            {(comparison.data ?? []).map((s) => (
              <div key={s.scenario_id} className="rounded-md border p-3">
                <div className="flex items-center justify-between text-sm font-medium">
                  {s.name}
                  {s.is_base && <span className="text-[10px] uppercase tracking-wide text-muted-foreground">Base</span>}
                </div>
                <div className="mt-2 grid grid-cols-2 gap-1 text-xs">
                  <span className="text-muted-foreground">Lev. IRR</span>
                  <span className="text-right font-semibold tabular">{pct(s.metrics?.irr_levered, 1)}</span>
                  <span className="text-muted-foreground">Multiple</span>
                  <span className="text-right tabular">{mult(s.metrics?.equity_multiple)}</span>
                  <span className="text-muted-foreground">Exit cap</span>
                  <span className="text-right tabular">{pct(s.key_assumptions.exit_cap_rate)}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4">
            <Button size="sm" variant="ghost" asChild>
              <Link href={`/deals/${p.id}/documents`}>
                <FileSearch /> Review source documents
              </Link>
            </Button>
          </div>
        </SectionCard>
      </div>
      <EditFactsDialog open={editing} onOpenChange={setEditing} />
    </div>
  );
}

function Fact({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <>
      <dt className="text-muted-foreground">{k}</dt>
      <dd className="text-right tabular">{v}</dd>
    </>
  );
}

function EditFactsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { property: p } = useDeal();
  const types = usePropertyTypes();
  const typeDef = types.data?.find((t) => t.key === p.property_type);
  const qc = useQueryClient();
  const org = useOrgKey();
  const [f, setF] = useState(() => ({
    name: p.name,
    address: p.address ?? "",
    city: p.city ?? "",
    state: p.state ?? "",
    zip_code: p.zip_code ?? "",
    year_built: p.year_built?.toString() ?? "",
    units: p.units?.toString() ?? "",
    rentable_sf: p.rentable_sf?.toString() ?? "",
    description: p.description ?? "",
    attributes: { ...p.attributes } as Record<string, unknown>,
  }));
  const save = useMutation({
    mutationFn: () =>
      api(`/api/properties/${p.id}`, {
        method: "PATCH",
        body: {
          name: f.name,
          address: f.address || null,
          city: f.city || null,
          state: f.state || null,
          zip_code: f.zip_code || null,
          year_built: f.year_built ? Number(f.year_built) : null,
          units: f.units ? Number(f.units) : null,
          rentable_sf: f.rentable_sf ? Number(f.rentable_sf) : null,
          description: f.description || null,
          attributes: f.attributes,
        },
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success("Property updated");
      onOpenChange(false);
    },
    onError: (e) => toast.error(e.message),
  });
  const text = (k: "name" | "address" | "city" | "state" | "zip_code" | "year_built" | "units" | "rentable_sf") => ({
    value: f[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value }),
  });
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Edit property facts" className="max-w-2xl">
        <form
          className="grid grid-cols-2 gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="ef-name">Name</Label>
            <Input id="ef-name" required {...text("name")} />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="ef-address">Address</Label>
            <Input id="ef-address" {...text("address")} />
          </div>
          {(
            [
              ["city", "City"],
              ["state", "State"],
              ["zip_code", "ZIP"],
              ["year_built", "Year built"],
              ["units", "Units"],
              ["rentable_sf", "Rentable SF"],
            ] as const
          ).map(([k, label]) => (
            <div key={k} className="space-y-1.5">
              <Label htmlFor={`ef-${k}`}>{label}</Label>
              <Input id={`ef-${k}`} {...text(k)} />
            </div>
          ))}
          {typeDef?.fields.map((fd) => (
            <div key={fd.key} className="space-y-1.5">
              <Label htmlFor={`ef-a-${fd.key}`}>{fd.label}</Label>
              {fd.type === "select" ? (
                <Select
                  id={`ef-a-${fd.key}`}
                  value={String(f.attributes[fd.key] ?? "")}
                  onChange={(e) => setF({ ...f, attributes: { ...f.attributes, [fd.key]: e.target.value } })}
                >
                  <option value="">—</option>
                  {fd.options?.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </Select>
              ) : (
                <Input
                  id={`ef-a-${fd.key}`}
                  value={
                    fd.type === "percent" && typeof f.attributes[fd.key] === "number"
                      ? String((f.attributes[fd.key] as number) * 100)
                      : String(f.attributes[fd.key] ?? "")
                  }
                  placeholder={fd.type === "percent" ? "%" : undefined}
                  onChange={(e) => {
                    const raw = e.target.value;
                    const v = fd.type === "text" ? raw : raw === "" ? null : fd.type === "percent" ? Number(raw) / 100 : Number(raw);
                    setF({ ...f, attributes: { ...f.attributes, [fd.key]: v } });
                  }}
                />
              )}
            </div>
          ))}
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="ef-desc">Description</Label>
            <Textarea id="ef-desc" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} />
          </div>
          <div className="col-span-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={save.isPending}>
              Save
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
