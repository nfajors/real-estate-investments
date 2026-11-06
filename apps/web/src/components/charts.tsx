"use client";

/**
 * Chart conventions (validated palette, see globals.css):
 * categorical slots in fixed order, thin bars with 4px rounded data-ends,
 * recessive grid/axes, a legend whenever there are 2+ series, hover tooltips.
 * Text uses ink tokens, never series colors.
 */
import type { TooltipContentProps } from "recharts";

export const SERIES = [
  "var(--chart-1)",
  "var(--chart-2)",
  "var(--chart-3)",
  "var(--chart-4)",
  "var(--chart-5)",
  "var(--chart-6)",
];

export const AXIS_PROPS = {
  stroke: "var(--chart-axis)",
  tick: { fill: "var(--muted-foreground)", fontSize: 11 },
  tickLine: false,
} as const;

export const GRID_PROPS = { stroke: "var(--chart-grid)", vertical: false } as const;

export const BAR_RADIUS: [number, number, number, number] = [4, 4, 0, 0];

type Fmt = (v: number) => string;

/** Theme-aware tooltip body for Recharts. */
export function ChartTooltip({
  active,
  payload,
  label,
  format,
  labelFormat,
}: Partial<TooltipContentProps<number, string>> & { format?: Fmt; labelFormat?: (l: string) => string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border bg-card px-3 py-2 text-xs shadow-md">
      {label !== undefined && label !== "" && (
        <div className="mb-1 font-medium text-foreground">{labelFormat ? labelFormat(String(label)) : label}</div>
      )}
      <div className="space-y-0.5">
        {payload.map((p, i) => (
          <div key={`${p.dataKey}-${i}`} className="flex items-center gap-2">
            <span className="size-2 rounded-[2px]" style={{ background: p.color ?? p.fill }} aria-hidden />
            <span className="text-muted-foreground">{p.name}</span>
            <span className="ml-auto pl-3 font-medium tabular text-foreground">
              {typeof p.value === "number" && format ? format(p.value) : String(p.value)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** Inline legend rendered as HTML (keeps text in ink tokens). */
export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((it) => (
        <span key={it.label} className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[3px]" style={{ background: it.color }} aria-hidden />
          {it.label}
        </span>
      ))}
    </div>
  );
}

/** Diverging cell colour around a base value (better = blue arm, worse = orange arm, neutral midpoint). */
export function divergingColor(value: number | null, base: number, spread: number): string {
  if (value === null || !Number.isFinite(value) || spread === 0) return "var(--div-mid)";
  const t = Math.max(-1, Math.min(1, (value - base) / spread));
  const arm = t >= 0 ? "var(--div-pos)" : "var(--div-neg)";
  const pctMix = Math.round(Math.abs(t) * 70);
  return `color-mix(in oklab, ${arm} ${pctMix}%, var(--div-mid))`;
}
