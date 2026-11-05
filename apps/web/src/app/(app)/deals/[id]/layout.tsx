"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft } from "lucide-react";
import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { toast } from "sonner";

import { Callout, ErrorBlock, LoadingBlock, StatusBadge } from "@/components/common";
import { DealContext } from "@/components/deal-context";
import { Badge, Select } from "@/components/ui/primitives";
import { useFeatures, useOrgKey, useProperty, useScenarios } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { STATUS_LABELS, STATUSES, stripDemo, TYPE_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";

const TABS: { slug: string; label: string; feature?: string }[] = [
  { slug: "", label: "Overview" },
  { slug: "underwriting", label: "Underwriting" },
  { slug: "documents", label: "Documents" },
  { slug: "scenarios", label: "Scenarios & Risk", feature: "scenarios" },
  { slug: "financing", label: "Financing" },
  { slug: "valuation", label: "Valuation", feature: "valuation" },
  { slug: "development", label: "Development", feature: "development" },
  { slug: "analyst", label: "AI Analyst", feature: "ai_analyst" },
  { slug: "reports", label: "Reports" },
  { slug: "activity", label: "Activity" },
];

export default function DealLayout({ children }: { children: React.ReactNode }) {
  const { id } = useParams<{ id: string }>();
  const pathname = usePathname();
  const { hasRole } = useAuth();
  const org = useOrgKey();
  const qc = useQueryClient();
  const property = useProperty(id);
  const scenarios = useScenarios(id);
  const features = useFeatures();
  const canEdit = hasRole("analyst");

  const setStatus = useMutation({
    mutationFn: (status: string) => api(`/api/properties/${id}`, { method: "PATCH", body: { status } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success("Status updated");
    },
    onError: (e) => toast.error(e.message),
  });

  if (property.isLoading || scenarios.isLoading) return <LoadingBlock rows={8} />;
  if (property.error) return <ErrorBlock error={property.error} />;
  if (!property.data || !scenarios.data) return null;
  const p = property.data;
  const base = scenarios.data.find((s) => s.is_base) ?? scenarios.data[0];
  const root = `/deals/${id}`;
  const current = pathname === root ? "" : pathname.slice(root.length + 1).split("/")[0];

  return (
    <DealContext.Provider value={{ property: p, scenarios: scenarios.data, base, canEdit }}>
      <div className="mb-5">
        <Link href="/deals" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ChevronLeft className="size-3.5" /> Deals
        </Link>
        <div className="mt-2 flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="truncate text-xl font-semibold tracking-tight">{stripDemo(p.name)}</h1>
              {p.is_demo && <Badge variant="demo">Demo data</Badge>}
              <StatusBadge status={p.status} />
            </div>
            <p className="mt-1 text-sm text-muted-foreground">
              {TYPE_LABELS[p.property_type]} · {[p.address, p.city, p.state].filter(Boolean).join(", ") || "Location not set"}
              {p.units ? ` · ${p.units.toLocaleString()} units` : ""}
              {p.rentable_sf ? ` · ${p.rentable_sf.toLocaleString()} SF` : ""}
            </p>
          </div>
          {canEdit && (
            <div className="flex items-center gap-2">
              <label htmlFor="deal-status" className="text-xs text-muted-foreground">
                Stage
              </label>
              <Select
                id="deal-status"
                value={p.status}
                onChange={(e) => setStatus.mutate(e.target.value)}
                className="w-48"
                disabled={setStatus.isPending}
              >
                {STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {STATUS_LABELS[s]}
                  </option>
                ))}
              </Select>
            </div>
          )}
        </div>
        {p.is_demo && (
          <Callout tone="danger" className="mt-3 py-2">
            Fictional sample deal for demonstration purposes only. All figures are illustrative and every export is watermarked.
          </Callout>
        )}
        <nav className="mt-4 flex gap-1 overflow-x-auto border-b" aria-label="Deal sections">
          {TABS.filter((t) => !t.feature || features.data?.[t.feature]?.enabled !== false).map((t) => {
            const active = current === t.slug;
            return (
              <Link
                key={t.slug}
                href={t.slug ? `${root}/${t.slug}` : root}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "-mb-px whitespace-nowrap border-b-2 border-transparent px-3 py-2 text-sm text-muted-foreground transition-colors hover:text-foreground",
                  active && "border-accent font-medium text-foreground",
                )}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>
      </div>
      {children}
    </DealContext.Provider>
  );
}
