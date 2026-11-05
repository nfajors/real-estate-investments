"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Building2, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { AXIS_PROPS, BAR_RADIUS, ChartTooltip, GRID_PROPS, SERIES } from "@/components/charts";
import { EmptyState, ErrorBlock, LoadingBlock, Metric, PageHeader, StatusBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Select } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Property } from "@/lib/types";
import { pct, relativeTime, STATUS_LABELS, stripDemo, TYPE_LABELS, usdShort } from "@/lib/format";

interface Dashboard {
  totals: {
    deals: number;
    active_deals: number;
    pipeline_volume: number;
    aum: number;
    weighted_avg_cap_rate: number | null;
    irr_min: number | null;
    irr_max: number | null;
    irr_median: number | null;
    demo_deals: number;
  };
  pipeline: { status: string; count: number; volume: number }[];
  exposure_by_type: { key: string; value: number }[];
  exposure_by_state: { key: string; value: number }[];
  alerts: { property_id: string; name: string; severity: string; message: string }[];
  recent_activity: {
    action: string;
    entity_type: string;
    user_name: string | null;
    property_name: string | null;
    property_id: string | null;
    created_at: string;
    details: Record<string, unknown>;
  }[];
}

const ACTION_LABELS: Record<string, string> = {
  "underwriting.run": "ran underwriting",
  "property.create": "created deal",
  "property.update": "updated deal",
  "document.upload": "uploaded a document to",
  "document.extract": "extracted data from a document on",
  "extraction.accept": "verified a field on",
  "extraction.edit": "edited a field on",
  "extraction.reject": "rejected a field on",
  "extraction.apply": "applied verified data to",
  "scenario.create": "created a scenario on",
  "scenario.update": "updated assumptions on",
  "financing.activate": "activated financing on",
  "report.excel": "exported the Excel model for",
  "report.one_pager": "exported the one-pager for",
  "report.ic_memo": "generated the IC memo for",
  "analyst.question": "asked the analyst about",
};

export default function DashboardPage() {
  const org = useOrgKey();
  const { hasRole } = useAuth();
  const [type, setType] = useState("");
  const [status, setStatus] = useState("");
  const qs = new URLSearchParams({ ...(type && { property_type: type }), ...(status && { status }) }).toString();
  const { data, isLoading, error } = useQuery({
    queryKey: [org, "dashboard", qs],
    queryFn: () => api<Dashboard>(`/api/dashboard${qs ? `?${qs}` : ""}`),
  });

  return (
    <>
      <PageHeader
        title="Investment Dashboard"
        description="Pipeline, exposure and portfolio returns across your workspace."
        actions={
          <>
            <Select value={type} onChange={(e) => setType(e.target.value)} className="w-40" aria-label="Filter by property type">
              <option value="">All property types</option>
              {Object.entries(TYPE_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
            <Select value={status} onChange={(e) => setStatus(e.target.value)} className="w-40" aria-label="Filter by status">
              <option value="">All statuses</option>
              {Object.entries(STATUS_LABELS).map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
            </Select>
            {hasRole("analyst") && (
              <Button asChild>
                <Link href="/deals?new=1">
                  <Plus /> New deal
                </Link>
              </Button>
            )}
          </>
        }
      />
      {isLoading && <LoadingBlock rows={6} />}
      {error && <ErrorBlock error={error} />}
      {data && data.totals.deals === 0 && (
        <EmptyState
          icon={Building2}
          title="No deals yet"
          description="Create your first deal to start underwriting, or reset filters."
          action={
            hasRole("analyst") ? (
              <Button asChild>
                <Link href="/deals?new=1">Create a deal</Link>
              </Button>
            ) : undefined
          }
        />
      )}
      {data && data.totals.deals > 0 && (
        <div className="space-y-6">
          {data.totals.demo_deals > 0 && (
            <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive">
              <AlertTriangle className="size-3.5" />
              {data.totals.demo_deals} of {data.totals.deals} deals are fictional demo data, shown for demonstration purposes only.
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Metric label="Active deals" value={data.totals.active_deals} sub={`${data.totals.deals} total`} />
            <Metric label="Pipeline volume" value={usdShort(data.totals.pipeline_volume)} sub="Sourcing → IC" />
            <Metric label="AUM (closed)" value={usdShort(data.totals.aum)} hint="Sum of purchase prices of closed deals." />
            <Metric
              label="Wtd. avg cap rate"
              value={pct(data.totals.weighted_avg_cap_rate)}
              hint="Going-in cap rates weighted by purchase price (excludes passed deals)."
            />
            <Metric label="Median levered IRR" value={pct(data.totals.irr_median, 1)} hint="Base scenarios, latest calculation." />
            <Metric
              label="IRR range"
              value={
                <span className="text-base">
                  {pct(data.totals.irr_min, 1)} – {pct(data.totals.irr_max, 1)}
                </span>
              }
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader>
                <CardTitle>Pipeline by stage</CardTitle>
                <CardDescription>Deal volume (purchase price) at each stage.</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="h-56">
                  <ResponsiveContainer>
                    <BarChart data={data.pipeline.map((p) => ({ ...p, label: STATUS_LABELS[p.status] }))} barCategoryGap="30%">
                      <CartesianGrid {...GRID_PROPS} />
                      <XAxis dataKey="label" {...AXIS_PROPS} />
                      <YAxis {...AXIS_PROPS} tickFormatter={(v) => usdShort(v)} width={64} axisLine={false} />
                      <Tooltip cursor={{ fill: "var(--muted)" }} content={<ChartTooltip format={usdShort} />} />
                      <Bar dataKey="volume" name="Volume" fill={SERIES[0]} radius={BAR_RADIUS} maxBarSize={48} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <div className="mt-3 grid grid-cols-5 gap-2 text-center text-xs">
                  {data.pipeline.map((p) => (
                    <Link
                      key={p.status}
                      href={`/deals?status=${p.status}`}
                      className="rounded-md border px-2 py-1.5 transition-colors hover:bg-muted"
                    >
                      <div className="text-muted-foreground">{STATUS_LABELS[p.status]}</div>
                      <div className="text-sm font-semibold tabular">{p.count}</div>
                    </Link>
                  ))}
                </div>
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Exposure by property type</CardTitle>
                <CardDescription>Share of purchase price, excluding passed deals.</CardDescription>
              </CardHeader>
              <CardContent>
                <ExposureBars rows={data.exposure_by_type.map((r) => ({ ...r, key: TYPE_LABELS[r.key] ?? r.key }))} />
                <div className="mt-5 mb-2 text-xs font-medium text-muted-foreground">By state</div>
                <ExposureBars rows={data.exposure_by_state} />
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 xl:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Alerts</CardTitle>
                <CardDescription>Risk-screen flags and projected covenant breaches.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {data.alerts.length === 0 && <p className="text-sm text-muted-foreground">No alerts. All deals clear the screening thresholds.</p>}
                {data.alerts.map((a, i) => (
                  <Link
                    key={i}
                    href={`/deals/${a.property_id}`}
                    className="flex items-start gap-3 rounded-md border px-3 py-2.5 text-sm transition-colors hover:bg-muted"
                  >
                    <AlertTriangle className={a.severity === "high" ? "mt-0.5 size-4 text-destructive" : "mt-0.5 size-4 text-warning"} aria-label={a.severity} />
                    <div className="min-w-0">
                      <div className="font-medium">{stripDemo(a.name)}</div>
                      <div className="text-muted-foreground">{a.message}</div>
                    </div>
                    <Badge variant={a.severity === "high" ? "danger" : "warning"} className="ml-auto shrink-0">
                      {a.severity}
                    </Badge>
                  </Link>
                ))}
              </CardContent>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Recent activity</CardTitle>
                <CardDescription>Audit trail across the workspace.</CardDescription>
              </CardHeader>
              <CardContent>
                <ol className="space-y-2.5">
                  {data.recent_activity.map((a, i) => (
                    <li key={i} className="flex items-start gap-3 text-sm">
                      <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-accent" aria-hidden />
                      <div className="min-w-0 flex-1">
                        <span className="font-medium">{a.user_name ?? "System"}</span>{" "}
                        <span className="text-muted-foreground">{ACTION_LABELS[a.action] ?? a.action}</span>{" "}
                        {a.property_id && a.property_name ? (
                          <Link href={`/deals/${a.property_id}`} className="font-medium hover:underline">
                            {stripDemo(a.property_name)}
                          </Link>
                        ) : null}
                      </div>
                      <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(a.created_at)}</span>
                    </li>
                  ))}
                </ol>
              </CardContent>
            </Card>
          </div>
          <RecentDeals />
        </div>
      )}
    </>
  );
}

function ExposureBars({ rows }: { rows: { key: string; value: number }[] }) {
  const total = rows.reduce((s, r) => s + r.value, 0) || 1;
  return (
    <ul className="space-y-2">
      {rows.slice(0, 6).map((r) => (
        <li key={r.key}>
          <div className="mb-1 flex justify-between text-xs">
            <span>{r.key}</span>
            <span className="tabular text-muted-foreground">
              {usdShort(r.value)} · {pct(r.value / total, 0)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted" role="presentation">
            <div className="h-full rounded-full" style={{ width: `${(r.value / total) * 100}%`, background: SERIES[0] }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function RecentDeals() {
  const org = useOrgKey();
  const { data } = useQuery({
    queryKey: [org, "properties", ""],
    queryFn: () => api<Property[]>("/api/properties"),
  });
  if (!data?.length) return null;
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Recently updated deals</CardTitle>
          <CardDescription>Latest base-case returns.</CardDescription>
        </div>
        <Button variant="ghost" size="sm" asChild>
          <Link href="/deals">
            All deals <ArrowRight />
          </Link>
        </Button>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data.slice(0, 6).map((p) => (
          <Link key={p.id} href={`/deals/${p.id}`} className="rounded-md border p-3.5 transition-colors hover:bg-muted/60">
            <div className="flex items-center gap-2">
              <span className="truncate text-sm font-medium">{stripDemo(p.name)}</span>
              {p.is_demo && <Badge variant="demo">Demo</Badge>}
              <span className="ml-auto">
                <StatusBadge status={p.status} />
              </span>
            </div>
            <div className="mt-0.5 text-xs text-muted-foreground">
              {TYPE_LABELS[p.property_type]} · {[p.city, p.state].filter(Boolean).join(", ")}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
              <div>
                <div className="text-muted-foreground">Price</div>
                <div className="font-semibold tabular">{usdShort(p.purchase_price)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Cap rate</div>
                <div className="font-semibold tabular">{pct(p.latest?.cap_rate)}</div>
              </div>
              <div>
                <div className="text-muted-foreground">Lev. IRR</div>
                <div className="font-semibold tabular">{pct(p.latest?.irr_levered, 1)}</div>
              </div>
            </div>
          </Link>
        ))}
      </CardContent>
    </Card>
  );
}

