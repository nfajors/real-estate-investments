"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight, ExternalLink, Pencil, RefreshCw, ShieldAlert, ShieldCheck, Undo2, X } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { ErrorBlock, LoadingBlock } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import { Badge, Card, Input, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/tooltip";
import { useExtractionFields, useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { pct, usd } from "@/lib/format";
import type { DocumentRec, Extraction, FieldDef, Page, UnitType } from "@/lib/types";
import { cn } from "@/lib/utils";

function formatValue(v: unknown, def?: FieldDef): string {
  if (v === null || v === undefined) return "—";
  if (!def) return String(v);
  if (def.kind === "unit_mix" && Array.isArray(v)) return `${(v as UnitType[]).reduce((s, u) => s + u.units, 0)} units · ${v.length} types`;
  if (typeof v !== "number") return String(v);
  if (def.kind === "currency") return usd(v);
  if (def.kind === "percent") return pct(v);
  if (def.kind === "years") return `${v} yrs`;
  if (def.kind === "integer") return def.label.toLowerCase().includes("year") ? String(v) : v.toLocaleString();
  return v.toLocaleString();
}

const STATUS_BADGE: Record<string, { variant: "default" | "success" | "danger" | "warning" | "outline"; label: string }> = {
  pending: { variant: "outline", label: "Pending" },
  accepted: { variant: "success", label: "Accepted" },
  edited: { variant: "success", label: "Edited" },
  rejected: { variant: "danger", label: "Rejected" },
  superseded: { variant: "default", label: "Superseded" },
};

export default function ReviewPage() {
  const { docId } = useParams<{ docId: string }>();
  const { property, canEdit } = useDeal();
  const org = useOrgKey();
  const qc = useQueryClient();
  const fields = useExtractionFields();
  const doc = useQuery({ queryKey: [org, "document", docId], queryFn: () => api<DocumentRec>(`/api/documents/${docId}`) });
  const pages = useQuery({ queryKey: [org, "pages", docId], queryFn: () => api<Page[]>(`/api/documents/${docId}/pages`), staleTime: 240_000 });
  const rows = useQuery({ queryKey: [org, "doc-extractions", docId], queryFn: () => api<Extraction[]>(`/api/documents/${docId}/extractions`) });
  const [selected, setSelected] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<"all" | "pending" | "reviewed">("all");
  const [minConf, setMinConf] = useState(0.7);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: [org, "doc-extractions", docId] });
    qc.invalidateQueries({ queryKey: [org, "extractions", property.id] });
  };
  const review = useMutation({
    mutationFn: ({ id, action, value }: { id: string; action: string; value?: unknown }) =>
      api<Extraction>(`/api/extractions/${id}`, { method: "PATCH", body: { action, value } }),
    onSuccess: invalidate,
    onError: (e) => toast.error(e.message),
  });
  const bulk = useMutation({
    mutationFn: () => api<Extraction[]>(`/api/documents/${docId}/extractions/bulk`, { body: { min_confidence: minConf, action: "accept", verified_citations_only: true } }),
    onSuccess: (r) => {
      invalidate();
      toast.success(`Accepted ${r.length} fields with verified citations and confidence ≥ ${pct(minConf, 0)}.`);
    },
    onError: (e) => toast.error(e.message),
  });
  const rerun = useMutation({
    mutationFn: () => api(`/api/documents/${docId}/extract`, { method: "POST" }),
    onSuccess: () => {
      toast.success("Re-extraction started");
      setTimeout(invalidate, 1500);
    },
  });

  const sel = rows.data?.find((r) => r.id === selected) ?? null;
  const select = (r: Extraction | undefined) => {
    if (!r) return;
    setSelected(r.id);
    if (r.source_page) setPage(r.source_page);
  };

  const grouped = useMemo(() => {
    const out = new Map<string, Extraction[]>();
    for (const r of rows.data ?? []) {
      if (filter === "pending" && r.status !== "pending") continue;
      if (filter === "reviewed" && r.status === "pending") continue;
      const g = fields.data?.[r.field_path]?.group ?? "Other";
      out.set(g, [...(out.get(g) ?? []), r]);
    }
    return out;
  }, [rows.data, fields.data, filter]);

  // Keyboard workflow: j/k to move, a = accept, r = reject.
  const flat = useMemo(() => Array.from(grouped.values()).flat(), [grouped]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.target as HTMLElement)?.tagName === "INPUT" || (e.target as HTMLElement)?.tagName === "SELECT") return;
      const idx = flat.findIndex((r) => r.id === selected);
      if (e.key === "j") select(flat[Math.min(flat.length - 1, idx + 1)]);
      if (e.key === "k") select(flat[Math.max(0, idx - 1)]);
      if (canEdit && sel && e.key === "a") review.mutate({ id: sel.id, action: "accept" });
      if (canEdit && sel && e.key === "r") review.mutate({ id: sel.id, action: "reject" });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [flat, selected, sel, canEdit, review]);

  if (doc.isLoading || pages.isLoading || rows.isLoading) return <LoadingBlock rows={8} />;
  if (doc.error) return <ErrorBlock error={doc.error} />;
  if (!doc.data || !pages.data || !rows.data) return null;
  const d = doc.data;
  const current = pages.data.find((p) => p.page_number === page) ?? pages.data[0];
  const pendingCount = rows.data.filter((r) => r.status === "pending").length;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Link href={`/deals/${property.id}/documents`} className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
          <ChevronLeft className="size-3.5" /> Documents
        </Link>
        <h2 className="truncate text-sm font-semibold">{d.name}</h2>
        <Badge variant="outline">{d.extractor}</Badge>
        <span className="text-xs text-muted-foreground">
          {rows.data.length} proposals · {pendingCount} pending
        </span>
        <div className="ml-auto flex flex-wrap items-center gap-2">
          <OpenOriginal docId={docId} />
          {canEdit && (
            <>
              <Button size="sm" variant="ghost" onClick={() => rerun.mutate()} loading={rerun.isPending}>
                <RefreshCw /> Re-extract
              </Button>
              <Select value={String(minConf)} onChange={(e) => setMinConf(Number(e.target.value))} className="h-8 w-28 text-xs" aria-label="Minimum confidence for bulk accept">
                {[0.6, 0.7, 0.8, 0.9].map((v) => (
                  <option key={v} value={v}>
                    ≥ {pct(v, 0)}
                  </option>
                ))}
              </Select>
              <Button size="sm" onClick={() => bulk.mutate()} loading={bulk.isPending} disabled={!pendingCount}>
                <Check /> Accept verified
              </Button>
            </>
          )}
        </div>
      </div>
      {d.error && <div className="rounded-md border border-warning/30 bg-warning/8 px-3 py-2 text-xs text-warning">{d.error}</div>}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {/* --------------------------------------------------- Viewer */}
        <Card className="overflow-hidden xl:sticky xl:top-20 xl:max-h-[calc(100vh-6rem)] xl:overflow-y-auto">
          <div className="flex items-center justify-between border-b px-4 py-2 text-xs">
            <span className="font-medium">
              {current?.label ? `Sheet: ${current.label}` : `Page ${current?.page_number} of ${pages.data.length}`}
            </span>
            <div className="flex items-center gap-1">
              <Button size="icon-sm" variant="ghost" aria-label="Previous page" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft />
              </Button>
              <Button size="icon-sm" variant="ghost" aria-label="Next page" disabled={page >= pages.data.length} onClick={() => setPage(page + 1)}>
                <ChevronRight />
              </Button>
            </div>
          </div>
          {current && <Viewer page={current} selection={sel?.source_page === current.page_number ? sel : null} />}
        </Card>

        {/* --------------------------------------------------- Fields */}
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {(["all", "pending", "reviewed"] as const).map((f) => (
              <Button key={f} size="sm" variant={filter === f ? "secondary" : "ghost"} onClick={() => setFilter(f)} className="capitalize">
                {f}
              </Button>
            ))}
            <span className="ml-auto hidden text-[11px] text-muted-foreground md:inline">Keys: j/k move · a accept · r reject</span>
          </div>
          {rows.data.length === 0 && <p className="text-sm text-muted-foreground">No fields were extracted from this document.</p>}
          {Array.from(grouped.entries()).map(([group, items]) => (
            <div key={group}>
              <div className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{group}</div>
              <div className="space-y-2">
                {items.map((r) => (
                  <FieldRow
                    key={r.id}
                    r={r}
                    def={fields.data?.[r.field_path]}
                    active={r.id === selected}
                    canEdit={canEdit}
                    onSelect={() => select(r)}
                    onAction={(action, value) => review.mutate({ id: r.id, action, value })}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function OpenOriginal({ docId }: { docId: string }) {
  const [busy, setBusy] = useState(false);
  return (
    <Button
      size="sm"
      variant="outline"
      loading={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const { url } = await api<{ url: string }>(`/api/documents/${docId}/url`);
          window.open(url, "_blank", "noopener");
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "Could not open document");
        } finally {
          setBusy(false);
        }
      }}
    >
      <ExternalLink /> Original
    </Button>
  );
}

function Viewer({ page, selection }: { page: Page; selection: Extraction | null }) {
  const box = selection?.source_bbox;
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (box && ref.current) ref.current.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [box]);

  if (page.cells) return <SheetViewer page={page} selection={selection} />;
  return (
    <div className="space-y-3 p-4">
      {page.image_url && (
        <div className="relative mx-auto max-w-[720px] overflow-hidden rounded border bg-white">
          {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL, not optimizable */}
          <img src={page.image_url} alt={`Page ${page.page_number}`} className="block w-full" />
          {box && (
            <div
              ref={ref}
              className="pointer-events-none absolute rounded-sm ring-2 ring-[var(--chart-2)]"
              style={{
                left: `${box.x0 * 100 - 0.6}%`,
                top: `${box.top * 100 - 0.4}%`,
                width: `${(box.x1 - box.x0) * 100 + 1.2}%`,
                height: `${(box.bottom - box.top) * 100 + 0.8}%`,
                background: "color-mix(in oklab, var(--chart-2) 22%, transparent)",
              }}
              aria-label="Highlighted source"
            />
          )}
        </div>
      )}
      <details className="text-xs" open={!page.image_url}>
        <summary className="cursor-pointer text-muted-foreground">Extracted page text</summary>
        <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded bg-muted p-3 font-mono text-[11px] leading-relaxed">
          <Highlighted text={page.text || "(no text layer – scanned page or image)"} needle={selection?.source_excerpt ?? ""} />
        </pre>
      </details>
    </div>
  );
}

function Highlighted({ text, needle }: { text: string; needle: string }) {
  const words = needle.trim().split(/\s+/).filter(Boolean);
  if (!words.length) return <>{text}</>;
  const pattern = new RegExp(words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("\\s+"), "i");
  const m = pattern.exec(text);
  if (!m) return <>{text}</>;
  return (
    <>
      {text.slice(0, m.index)}
      <mark className="rounded-sm bg-[color-mix(in_oklab,var(--chart-2)_35%,transparent)] px-0.5 text-foreground">{m[0]}</mark>
      {text.slice(m.index + m[0].length)}
    </>
  );
}

function parseRange(ref: string | null | undefined): { cols: Set<string>; r0: number; r1: number; cells: Set<string> } | null {
  if (!ref) return null;
  const part = ref.includes("!") ? ref.split("!")[1] : ref;
  const [a, b] = part.split(":");
  const m1 = /^([A-Z]+)(\d+)$/.exec(a);
  if (!m1) return null;
  const m2 = b ? /^([A-Z]+)(\d+)$/.exec(b) : m1;
  if (!m2) return null;
  return { cols: new Set([m1[1], m2[1]]), r0: Number(m1[2]), r1: Number(m2[2]), cells: new Set([a, b].filter(Boolean)) };
}

function SheetViewer({ page, selection }: { page: Page; selection: Extraction | null }) {
  const cells = page.cells ?? [];
  const grid = new Map<number, Map<string, unknown>>();
  const colSet = new Set<string>();
  for (const [ref, v] of cells) {
    const m = /^([A-Z]+)(\d+)$/.exec(ref);
    if (!m) continue;
    colSet.add(m[1]);
    const row = Number(m[2]);
    if (!grid.has(row)) grid.set(row, new Map());
    grid.get(row)!.set(m[1], v);
  }
  const cols = Array.from(colSet).sort((a, b) => a.length - b.length || a.localeCompare(b));
  const range = parseRange(selection?.source_ref);
  const rowsAll = Array.from(grid.keys()).sort((a, b) => a - b);
  // Show a window around the selection for very long sheets.
  const focus = range?.r0 ?? rowsAll[0] ?? 1;
  const visible = rowsAll.length > 80 ? rowsAll.filter((r) => r >= focus - 5 && r <= focus + 60) : rowsAll;
  const hl = (row: number, col: string) => {
    if (!range) return false;
    const inRows = row >= range.r0 && row <= range.r1;
    if (range.r0 === range.r1 && range.cells.size === 1) return inRows && range.cols.has(col);
    const colIdx = cols.indexOf(col);
    const c0 = Math.min(...Array.from(range.cols).map((c) => cols.indexOf(c)));
    const c1 = Math.max(...Array.from(range.cols).map((c) => cols.indexOf(c)));
    return inRows && colIdx >= c0 && colIdx <= c1;
  };
  return (
    <div className="max-h-[70vh] overflow-auto">
      <Table className="text-[11px]">
        <THead>
          <TR className="hover:bg-transparent">
            <TH className="sticky top-0 bg-card">#</TH>
            {cols.map((c) => (
              <TH key={c} className="sticky top-0 bg-card">
                {c}
              </TH>
            ))}
          </TR>
        </THead>
        <TBody>
          {visible.map((r) => (
            <TR key={r}>
              <TD className="text-muted-foreground">{r}</TD>
              {cols.map((c) => {
                const v = grid.get(r)?.get(c);
                return (
                  <TD key={c} className={cn("whitespace-nowrap", hl(r, c) && "bg-[color-mix(in_oklab,var(--chart-2)_28%,transparent)] font-medium")}>
                    {v === undefined ? "" : typeof v === "number" ? v.toLocaleString() : String(v)}
                  </TD>
                );
              })}
            </TR>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function FieldRow({
  r,
  def,
  active,
  canEdit,
  onSelect,
  onAction,
}: {
  r: Extraction;
  def?: FieldDef;
  active: boolean;
  canEdit: boolean;
  onSelect: () => void;
  onAction: (action: string, value?: unknown) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState("");
  const st = STATUS_BADGE[r.status];
  const conf = Math.round(r.confidence * 100);
  const changed = JSON.stringify(r.value) !== JSON.stringify(r.original_value);
  return (
    <Card
      role="button"
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => e.key === "Enter" && onSelect()}
      className={cn("cursor-pointer px-3.5 py-3 transition-colors hover:bg-muted/40", active && "ring-2 ring-[var(--ring)]")}
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{r.label ?? r.field_path}</span>
            <Badge variant={st.variant}>{st.label}</Badge>
            {r.citation_verified ? (
              <Tooltip content="The cited excerpt was found verbatim in the parsed document (or read directly from the cell).">
                <span className="inline-flex items-center gap-0.5 text-[11px] text-success">
                  <ShieldCheck className="size-3.5" /> Citation verified
                </span>
              </Tooltip>
            ) : (
              <Tooltip content="The excerpt could not be located in the document text. Confidence has been capped – check the source manually.">
                <span className="inline-flex items-center gap-0.5 text-[11px] text-warning">
                  <ShieldAlert className="size-3.5" /> Unverified citation
                </span>
              </Tooltip>
            )}
          </div>
          {editing ? (
            <form
              className="mt-2 flex gap-2"
              onClick={(e) => e.stopPropagation()}
              onSubmit={(e) => {
                e.preventDefault();
                let value: unknown = text;
                if (def?.kind === "unit_mix") {
                  try {
                    value = JSON.parse(text);
                  } catch {
                    toast.error("Unit mix must be valid JSON");
                    return;
                  }
                }
                onAction("edit", value);
                setEditing(false);
              }}
            >
              <Input autoFocus value={text} onChange={(e) => setText(e.target.value)} className="h-8 text-sm" aria-label={`New value for ${r.label}`} />
              <Button size="sm" type="submit">
                Save
              </Button>
              <Button size="sm" type="button" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            </form>
          ) : (
            <div className="mt-1 text-lg font-semibold tabular">
              {formatValue(r.value, def)}
              {changed && (
                <span className="ml-2 text-xs font-normal text-muted-foreground line-through">{formatValue(r.original_value, def)}</span>
              )}
            </div>
          )}
          {def?.kind === "unit_mix" && Array.isArray(r.value) && (
            <div className="mt-2 overflow-hidden rounded border text-xs">
              <table className="w-full tabular">
                <thead className="bg-muted/60 text-muted-foreground">
                  <tr>
                    <th className="px-2 py-1 text-left font-medium">Type</th>
                    <th className="px-2 py-1 text-right font-medium">Units</th>
                    <th className="px-2 py-1 text-right font-medium">In-place</th>
                    <th className="px-2 py-1 text-right font-medium">Market</th>
                    <th className="px-2 py-1 text-right font-medium">SF</th>
                  </tr>
                </thead>
                <tbody>
                  {(r.value as UnitType[]).map((u) => (
                    <tr key={u.name} className="border-t">
                      <td className="px-2 py-1">{u.name}</td>
                      <td className="px-2 py-1 text-right">{u.units}</td>
                      <td className="px-2 py-1 text-right">{usd(u.in_place_rent_monthly)}</td>
                      <td className="px-2 py-1 text-right">{usd(u.market_rent_monthly)}</td>
                      <td className="px-2 py-1 text-right">{u.sf_per_unit ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="mt-1.5 text-xs text-muted-foreground">
            <span className="font-medium text-foreground/80">{r.source_ref ?? (r.source_page ? `Page ${r.source_page}` : "No location")}</span>
            {r.source_excerpt && <span className="ml-1.5 italic">“{r.source_excerpt}”</span>}
          </div>
        </div>
        <div className="w-20 shrink-0 text-right">
          <div className="text-[11px] text-muted-foreground">Confidence</div>
          <div className="text-sm font-semibold tabular">{conf}%</div>
          <div className="mt-1 h-1 overflow-hidden rounded-full bg-muted" role="meter" aria-valuenow={conf} aria-valuemin={0} aria-valuemax={100} aria-label="Confidence">
            <div className="h-full rounded-full" style={{ width: `${conf}%`, background: "var(--chart-1)" }} />
          </div>
        </div>
      </div>
      {canEdit && (
        <div className="mt-2.5 flex flex-wrap gap-1.5" onClick={(e) => e.stopPropagation()}>
          {r.status !== "accepted" && (
            <Button size="sm" variant="outline" onClick={() => onAction("accept")}>
              <Check /> Accept
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              setText(def?.kind === "unit_mix" ? JSON.stringify(r.value) : def?.kind === "percent" && typeof r.value === "number" ? `${(r.value * 100).toFixed(2)}%` : String(r.value ?? ""));
              setEditing(true);
            }}
          >
            <Pencil /> Edit
          </Button>
          {r.status !== "rejected" && (
            <Button size="sm" variant="ghost" onClick={() => onAction("reject")}>
              <X /> Reject
            </Button>
          )}
          {r.status !== "pending" && (
            <Button size="sm" variant="ghost" onClick={() => onAction("reset")}>
              <Undo2 /> Reset
            </Button>
          )}
          <span className="ml-auto self-center text-[11px] text-muted-foreground">
            {r.extractor} · v{r.version}
          </span>
        </div>
      )}
    </Card>
  );
}
