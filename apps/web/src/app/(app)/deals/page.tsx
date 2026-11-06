"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Columns3, Plus, Rows3, Search } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { toast } from "sonner";

import { DemoBadge, EmptyState, ErrorBlock, LoadingBlock, PageHeader, RiskBadge, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/overlays";
import { Card, Input, Label, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useOrgKey, useProperties, usePropertyTypes } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { mult, pct, STATUS_LABELS, STATUSES, stripDemo, TYPE_LABELS, usd, usdShort } from "@/lib/format";
import type { Property } from "@/lib/types";
import { cn } from "@/lib/utils";

function DealsInner() {
  const params = useSearchParams();
  const router = useRouter();
  const { hasRole } = useAuth();
  const [q, setQ] = useState("");
  const [type, setType] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [view, setView] = useState<"table" | "kanban">(() => {
    try {
      return window.localStorage.getItem("axiom.deals.view") === "kanban" ? "kanban" : "table";
    } catch {
      return "table";
    }
  });
  const [open, setOpen] = useState(params.get("new") === "1");
  const { data, isLoading, error } = useProperties({ q: q || undefined, property_type: type || undefined, status: status || undefined });

  const changeView = (v: "table" | "kanban") => {
    setView(v);
    try {
      window.localStorage.setItem("axiom.deals.view", v);
    } catch {
      /* ignore */
    }
  };

  return (
    <>
      <PageHeader
        title="Deals"
        description="Every opportunity in your pipeline, with base-case returns from the latest calculation."
        actions={
          hasRole("analyst") && (
            <Button onClick={() => setOpen(true)}>
              <Plus /> New deal
            </Button>
          )
        }
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-64">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input placeholder="Search name or market…" value={q} onChange={(e) => setQ(e.target.value)} className="pl-8" aria-label="Search deals" />
        </div>
        <Select value={type} onChange={(e) => setType(e.target.value)} className="w-44" aria-label="Property type">
          <option value="">All property types</option>
          {Object.entries(TYPE_LABELS).map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </Select>
        <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-44" aria-label="Status">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </Select>
        <div className="ml-auto inline-flex rounded-md border p-0.5" role="group" aria-label="View">
          <Button variant={view === "table" ? "secondary" : "ghost"} size="sm" onClick={() => changeView("table")} aria-pressed={view === "table"}>
            <Rows3 /> Table
          </Button>
          <Button variant={view === "kanban" ? "secondary" : "ghost"} size="sm" onClick={() => changeView("kanban")} aria-pressed={view === "kanban"}>
            <Columns3 /> Pipeline
          </Button>
        </div>
      </div>
      {isLoading && <LoadingBlock rows={6} />}
      {error && <ErrorBlock error={error} />}
      {data && data.length === 0 && (
        <EmptyState icon={Building2} title="No deals match" description="Adjust filters or create a new deal." />
      )}
      {data && data.length > 0 && (view === "table" ? <DealTable deals={data} onOpen={(id) => router.push(`/deals/${id}`)} /> : <Kanban deals={data} />)}
      <NewDealDialog open={open} onOpenChange={setOpen} />
    </>
  );
}

function DealTable({ deals, onOpen }: { deals: Property[]; onOpen: (id: string) => void }) {
  return (
    <Card>
      <Table>
        <THead>
          <TR className="hover:bg-transparent">
            <TH>Deal</TH>
            <TH>Type</TH>
            <TH>Status</TH>
            <TH className="text-right">Price</TH>
            <TH className="text-right">$/unit · $/SF</TH>
            <TH className="text-right">Cap rate</TH>
            <TH className="text-right">Lev. IRR</TH>
            <TH className="text-right">Eq. multiple</TH>
            <TH className="text-right">DSCR</TH>
            <TH>Risk</TH>
            <TH>Owner</TH>
          </TR>
        </THead>
        <TBody>
          {deals.map((p) => (
            <TR key={p.id} className="cursor-pointer" onClick={() => onOpen(p.id)}>
              <TD>
                <Link href={`/deals/${p.id}`} className="font-medium hover:underline" onClick={(e) => e.stopPropagation()}>
                  {stripDemo(p.name)}
                </Link>
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  {[p.city, p.state].filter(Boolean).join(", ") || "—"}
                  {p.is_demo && <DemoBadge />}
                </div>
              </TD>
              <TD className="text-muted-foreground">{TYPE_LABELS[p.property_type]}</TD>
              <TD>
                <StatusBadge status={p.status} />
              </TD>
              <TD className="text-right">{usdShort(p.purchase_price)}</TD>
              <TD className="text-right text-muted-foreground">
                {p.latest?.price_per_unit ? usd(p.latest.price_per_unit) : p.latest?.price_per_sf ? `${usd(p.latest.price_per_sf, 2)}/SF` : "—"}
              </TD>
              <TD className="text-right">{pct(p.latest?.cap_rate)}</TD>
              <TD className="text-right font-medium">{pct(p.latest?.irr_levered, 1)}</TD>
              <TD className="text-right">{mult(p.latest?.equity_multiple)}</TD>
              <TD className="text-right">{mult(p.latest?.dscr)}</TD>
              <TD>
                <RiskBadge level={p.latest?.risk_level} score={p.latest?.risk_score} />
              </TD>
              <TD className="text-muted-foreground">{p.owner_name ?? "—"}</TD>
            </TR>
          ))}
        </TBody>
      </Table>
    </Card>
  );
}

function Kanban({ deals }: { deals: Property[] }) {
  const qc = useQueryClient();
  const org = useOrgKey();
  const { hasRole } = useAuth();
  const [dragId, setDragId] = useState<string | null>(null);
  const move = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) => api(`/api/properties/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org] }),
    onError: (e) => toast.error(e.message),
  });
  return (
    <div className="grid gap-3 overflow-x-auto pb-2 md:grid-cols-5">
      {STATUSES.map((s) => {
        const col = deals.filter((d) => d.status === s);
        return (
          <div
            key={s}
            className={cn("min-w-56 rounded-lg border bg-muted/40 p-2", dragId && "outline-dashed outline-1 outline-border")}
            onDragOver={(e) => hasRole("analyst") && e.preventDefault()}
            onDrop={() => {
              if (dragId) move.mutate({ id: dragId, status: s });
              setDragId(null);
            }}
          >
            <div className="mb-2 flex items-center justify-between px-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              {STATUS_LABELS[s]}
              <span className="tabular">
                {col.length} · {usdShort(col.reduce((a, d) => a + (d.purchase_price ?? 0), 0))}
              </span>
            </div>
            <div className="space-y-2">
              {col.map((p) => (
                <Link
                  key={p.id}
                  href={`/deals/${p.id}`}
                  draggable={hasRole("analyst")}
                  onDragStart={() => setDragId(p.id)}
                  className="block rounded-md border bg-card p-3 shadow-xs transition-shadow hover:shadow-md"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="text-sm font-medium leading-snug">{stripDemo(p.name)}</div>
                    {p.is_demo && <DemoBadge />}
                  </div>
                  <div className="mt-0.5 text-xs text-muted-foreground">
                    {TYPE_LABELS[p.property_type]} · {p.city ?? "—"}
                  </div>
                  <div className="mt-2 flex items-center justify-between text-xs tabular">
                    <span>{usdShort(p.purchase_price)}</span>
                    <span className="font-medium">{pct(p.latest?.irr_levered, 1)} IRR</span>
                  </div>
                </Link>
              ))}
              {col.length === 0 && <div className="px-1.5 py-4 text-center text-xs text-muted-foreground">No deals</div>}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function NewDealDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const router = useRouter();
  const qc = useQueryClient();
  const org = useOrgKey();
  const types = usePropertyTypes();
  const [f, setF] = useState({
    name: "",
    property_type: "multifamily",
    address: "",
    city: "",
    state: "",
    purchase_price: "",
    hold_period_years: "10",
    units: "",
    rentable_sf: "",
    year_built: "",
  });
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setF({ ...f, [k]: e.target.value });
  const create = useMutation({
    mutationFn: () =>
      api<Property>("/api/properties", {
        body: {
          name: f.name,
          property_type: f.property_type,
          address: f.address || null,
          city: f.city || null,
          state: f.state || null,
          purchase_price: Number(f.purchase_price.replace(/[$,]/g, "")),
          hold_period_years: Number(f.hold_period_years),
          units: f.units ? Number(f.units) : null,
          rentable_sf: f.rentable_sf ? Number(f.rentable_sf.replace(/,/g, "")) : null,
          year_built: f.year_built ? Number(f.year_built) : null,
        },
      }),
    onSuccess: (p) => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success("Deal created with template assumptions. Upload documents to replace them with verified data.");
      onOpenChange(false);
      router.push(`/deals/${p.id}/documents`);
    },
    onError: (e) => toast.error(e.message),
  });
  const meta = types.data?.find((t) => t.key === f.property_type);
  const usesUnits = meta?.revenue_mode === "unit_mix";
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New deal" description="Starts with clearly-labelled template assumptions for the property type." className="max-w-xl">
        <form
          className="grid grid-cols-2 gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="nd-name">Deal name</Label>
            <Input id="nd-name" required value={f.name} onChange={set("name")} placeholder="e.g. Parkside Apartments" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-type">Property type</Label>
            <Select id="nd-type" value={f.property_type} onChange={set("property_type")}>
              {(types.data ?? []).map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-price">Purchase / asking price ($)</Label>
            <Input id="nd-price" required inputMode="numeric" value={f.purchase_price} onChange={set("purchase_price")} placeholder="25,000,000" />
          </div>
          <div className="col-span-2 space-y-1.5">
            <Label htmlFor="nd-address">Address</Label>
            <Input id="nd-address" value={f.address} onChange={set("address")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-city">City</Label>
            <Input id="nd-city" value={f.city} onChange={set("city")} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-state">State</Label>
            <Input id="nd-state" value={f.state} onChange={set("state")} maxLength={2} placeholder="TX" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-size">{usesUnits ? "Units" : "Rentable SF"}</Label>
            {usesUnits ? (
              <Input id="nd-size" inputMode="numeric" value={f.units} onChange={set("units")} />
            ) : (
              <Input id="nd-size" inputMode="numeric" value={f.rentable_sf} onChange={set("rentable_sf")} />
            )}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="nd-hold">Hold period (years)</Label>
            <Input id="nd-hold" type="number" min={1} max={30} value={f.hold_period_years} onChange={set("hold_period_years")} />
          </div>
          <div className="col-span-2 mt-2 flex justify-end gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" loading={create.isPending}>
              Create deal
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function DealsPage() {
  return (
    <Suspense>
      <DealsInner />
    </Suspense>
  );
}
