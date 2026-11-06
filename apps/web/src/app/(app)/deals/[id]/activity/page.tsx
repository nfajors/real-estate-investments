"use client";

import { History } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState, ErrorBlock, LoadingBlock } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import { Badge, Card, CardContent } from "@/components/ui/primitives";
import { type AuditEntry, useAudit } from "@/hooks/queries";
import { dateTime, isNum, num, pct, relativeTime, usd } from "@/lib/format";
import { cn } from "@/lib/utils";

// ------------------------------------------------------------- categories
const CATEGORIES = [
  { key: "all", label: "All", prefixes: [] as string[] },
  { key: "underwriting", label: "Underwriting", prefixes: ["underwriting.", "risk.", "valuation.", "development."] },
  { key: "documents", label: "Documents & verification", prefixes: ["document.", "extraction."] },
  { key: "scenarios", label: "Scenarios", prefixes: ["scenario."] },
  { key: "financing", label: "Financing", prefixes: ["financing."] },
  { key: "reports", label: "Reports", prefixes: ["report."] },
] as const;
type CategoryKey = (typeof CATEGORIES)[number]["key"];

const ACTION_LABELS: Record<string, string> = {
  "underwriting.run": "ran underwriting",
  "risk.monte_carlo": "ran a Monte Carlo simulation",
  "valuation.update": "updated valuation inputs",
  "development.update": "saved the development model",
  "property.create": "created the deal",
  "property.update": "updated deal details",
  "property.delete": "deleted the deal",
  "document.upload": "uploaded a document",
  "document.extract": "extracted data from a document",
  "document.delete": "deleted a document",
  "extraction.accept": "verified an extracted field",
  "extraction.edit": "corrected an extracted field",
  "extraction.reject": "rejected an extracted field",
  "extraction.reset": "reset an extracted field for review",
  "extraction.apply": "applied verified data to the base scenario",
  "scenario.create": "created a scenario",
  "scenario.create_defaults": "created default scenarios",
  "scenario.update": "updated scenario assumptions",
  "scenario.delete": "deleted a scenario",
  "scenario.make_base": "set the base scenario",
  "financing.create": "added a financing structure",
  "financing.update": "edited a financing structure",
  "financing.delete": "deleted a financing structure",
  "financing.activate": "activated a financing structure",
  "report.excel": "exported the Excel model",
  "report.one_pager": "exported the one-page summary",
  "report.ic_memo": "generated the IC memorandum",
  "analyst.question": "asked the AI analyst a question",
};

const humanise = (action: string) => ACTION_LABELS[action] ?? action.replace(/[._]/g, " ");
const categoryOf = (action: string) =>
  CATEGORIES.find((c) => c.key !== "all" && c.prefixes.some((p) => action.startsWith(p)))?.key;

// --------------------------------------------------------------- details
const PCT_KEY = /rate|pct|growth|vacancy|ratio|loss|ltv|ltc|yield/i;
const USD_KEY = /price|capex|income|rent|amount|cost|noi|value|fee$/i;

/** Compact display of an arbitrary audit value (display only). */
function fmtValue(key: string, v: unknown): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    if (PCT_KEY.test(key) && Math.abs(v) < 1) return pct(v, 2);
    if (USD_KEY.test(key)) return usd(v);
    return num(v, Number.isInteger(v) ? 0 : 2);
  }
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "string") return v.length > 60 ? `${v.slice(0, 57)}…` : v;
  if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? "" : "s"}`;
  const s = JSON.stringify(v);
  return s.length > 60 ? `${s.slice(0, 57)}…` : s;
}

const labelKey = (k: string) => k.replace(/_/g, " ");

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1 rounded border bg-muted/50 px-1.5 py-0.5 text-[11px] text-muted-foreground tabular">
      {children}
    </span>
  );
}

function KV({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <Chip>
      <span>{k}</span>
      <span className="font-medium text-foreground">{v}</span>
    </Chip>
  );
}

type Changes = Record<string, { before: unknown; after: unknown }>;

function ChangeList({ changes }: { changes: Changes }) {
  const entries = Object.entries(changes);
  if (!entries.length) return <span className="text-[11px] text-muted-foreground">No assumption values changed</span>;
  const shown = entries.slice(0, 8);
  return (
    <ul className="space-y-0.5 text-xs">
      {shown.map(([k, c]) => (
        <li key={k} className="flex flex-wrap items-baseline gap-x-1.5 tabular">
          <code className="text-[11px] text-foreground">{k}</code>
          <span className="text-muted-foreground line-through decoration-muted-foreground/50">{fmtValue(k, c?.before)}</span>
          <span className="text-muted-foreground" aria-label="changed to">
            →
          </span>
          <span className="font-medium">{fmtValue(k, c?.after)}</span>
        </li>
      ))}
      {entries.length > shown.length && <li className="text-[11px] text-muted-foreground">+{entries.length - shown.length} more</li>}
    </ul>
  );
}

function Details({ e }: { e: AuditEntry }) {
  const d = (e.details ?? {}) as Record<string, unknown>;
  const a = e.action;

  if (a === "underwriting.run")
    return (
      <div className="flex flex-wrap gap-1.5">
        {typeof d.scenario === "string" && <KV k="Scenario" v={d.scenario} />}
        <KV k="Levered IRR" v={pct(d.irr_levered as number | null, 2)} />
        <KV k="Yr 1 NOI" v={usd(d.noi_year1 as number | null)} />
        {isNum(d.calc_ms) && <KV k="Calc" v={`${num(d.calc_ms, 1)} ms`} />}
        {typeof d.engine_version === "string" && <KV k="Engine" v={d.engine_version} />}
      </div>
    );

  if (a.startsWith("extraction.")) {
    if (a === "extraction.apply") {
      const fields = Array.isArray(d.fields) ? (d.fields as string[]) : [];
      return (
        <div className="flex flex-wrap gap-1.5">
          {fields.slice(0, 10).map((f) => (
            <Chip key={f}>
              <code>{f}</code>
            </Chip>
          ))}
          {fields.length > 10 && <Chip>+{fields.length - 10} more</Chip>}
        </div>
      );
    }
    const after = d.after as { value?: unknown } | undefined;
    const before = d.before as { value?: unknown } | undefined;
    const fp = typeof d.field_path === "string" ? d.field_path : "";
    return (
      <div className="flex flex-wrap items-center gap-1.5">
        {fp && (
          <Chip>
            <code className="text-foreground">{fp}</code>
          </Chip>
        )}
        {a === "extraction.edit" && after && (
          <span className="text-xs tabular text-muted-foreground">
            {fmtValue(fp, before?.value)} → <span className="font-medium text-foreground">{fmtValue(fp, after.value)}</span>
          </span>
        )}
      </div>
    );
  }

  if ((a === "scenario.update" || a === "property.update") && d.changes && typeof d.changes === "object")
    return <ChangeList changes={d.changes as Changes} />;

  // Generic: up to five primitive values.
  const prim = Object.entries(d).filter(
    ([k, v]) => ["string", "number", "boolean"].includes(typeof v) && !k.endsWith("_id") && !["name", "extractor"].includes(k),
  );
  if (!prim.length) return null;
  return (
    <div className="flex flex-wrap gap-1.5">
      {prim.slice(0, 5).map(([k, v]) => (
        <KV key={k} k={labelKey(k)} v={fmtValue(k, v)} />
      ))}
    </div>
  );
}

// ------------------------------------------------------------------- page
function dayLabel(iso: string) {
  const d = new Date(iso);
  const today = new Date();
  const yest = new Date();
  yest.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return "Today";
  if (d.toDateString() === yest.toDateString()) return "Yesterday";
  return d.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    ...(d.getFullYear() !== today.getFullYear() && { year: "numeric" }),
  });
}

export default function ActivityPage() {
  const { property } = useDeal();
  const { data, isLoading, error } = useAudit(property.id);
  const [cat, setCat] = useState<CategoryKey>("all");

  const counts = useMemo(() => {
    const c: Partial<Record<CategoryKey, number>> = { all: data?.length ?? 0 };
    for (const e of data ?? []) {
      const k = categoryOf(e.action);
      if (k) c[k] = (c[k] ?? 0) + 1;
    }
    return c;
  }, [data]);

  const groups = useMemo(() => {
    const rows = (data ?? []).filter((e) => cat === "all" || categoryOf(e.action) === cat);
    const out: { day: string; items: AuditEntry[] }[] = [];
    for (const e of rows) {
      const day = dayLabel(e.created_at);
      const last = out.at(-1);
      if (last && last.day === day) last.items.push(e);
      else out.push({ day, items: [e] });
    }
    return out;
  }, [data, cat]);

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h2 className="text-base font-semibold tracking-tight">Activity</h2>
          <p className="mt-0.5 text-sm text-muted-foreground">Immutable audit trail of calculations, verifications, edits and exports on this deal.</p>
        </div>
        <div role="group" aria-label="Filter activity by category" className="flex flex-wrap gap-1">
          {CATEGORIES.map((c) => (
            <Button
              key={c.key}
              size="sm"
              variant={cat === c.key ? "secondary" : "ghost"}
              aria-pressed={cat === c.key}
              onClick={() => setCat(c.key)}
              className={cn(cat === c.key && "font-semibold")}
            >
              {c.label}
              {data && <span className="tabular text-muted-foreground">{counts[c.key] ?? 0}</span>}
            </Button>
          ))}
        </div>
      </div>

      {isLoading && <LoadingBlock rows={6} />}
      {error && <ErrorBlock error={error} />}
      {data && data.length === 0 && (
        <EmptyState icon={History} title="No activity yet" description="Underwriting runs, document verification, scenario edits and exports will appear here." />
      )}
      {data && data.length > 0 && groups.length === 0 && (
        <EmptyState icon={History} title="No matching activity" description="Nothing in this category yet. Choose another filter." />
      )}

      {groups.map((g) => (
        <section key={g.day} aria-label={g.day}>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{g.day}</h3>
          <Card>
            <CardContent className="px-0 pb-0">
              <ol className="divide-y">
                {g.items.map((e) => (
                  <li key={e.id} className="flex gap-3 px-5 py-3">
                    <span
                      className={cn(
                        "mt-1.5 size-2 shrink-0 rounded-full",
                        e.action === "underwriting.run" ? "bg-accent" : "bg-muted-foreground/40",
                      )}
                      aria-hidden
                    />
                    <div className="min-w-0 flex-1 space-y-1.5">
                      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 text-sm">
                        <span className="font-medium">{e.user_name ?? "System"}</span>
                        <span className="text-muted-foreground">{humanise(e.action)}</span>
                        {typeof e.details?.name === "string" && e.action !== "underwriting.run" && (
                          <span className="font-medium">{e.details.name as string}</span>
                        )}
                        {e.action === "document.extract" && typeof e.details?.extractor === "string" && (
                          <Badge variant="outline">{e.details.extractor as string}</Badge>
                        )}
                      </div>
                      <Details e={e} />
                    </div>
                    <time dateTime={e.created_at} title={dateTime(e.created_at)} className="shrink-0 text-xs text-muted-foreground tabular">
                      {relativeTime(e.created_at)}
                    </time>
                  </li>
                ))}
              </ol>
            </CardContent>
          </Card>
        </section>
      ))}
      {data && data.length >= 200 && <p className="text-center text-xs text-muted-foreground">Showing the most recent 200 events.</p>}
    </div>
  );
}
