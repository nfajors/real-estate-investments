"use client";

import { useId, useState } from "react";

import { Input, Label } from "@/components/ui/primitives";
import { cn } from "@/lib/utils";

export type NumKind = "pct" | "usd" | "num" | "int";

function toText(v: number | null | undefined, kind: NumKind): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "";
  if (kind === "pct") return String(Number((v * 100).toFixed(6)));
  if (kind === "usd" || kind === "num") return v.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return String(Math.round(v));
}

function fromText(s: string, kind: NumKind): number | null {
  const clean = s.replace(/[$,%\s]/g, "");
  if (clean === "" || clean === "-") return null;
  const n = Number(clean);
  if (!Number.isFinite(n)) return null;
  if (kind === "pct") return n / 100;
  if (kind === "int") return Math.round(n);
  return n;
}

/**
 * Numeric input that displays human units (percent as 5.25, currency with
 * separators) but emits engine units (decimals, plain numbers).
 */
export function NumberField({
  label,
  value,
  onChange,
  kind = "num",
  error,
  hint,
  disabled,
  className,
  compact,
  nullable = false,
}: {
  label: string;
  value: number | null | undefined;
  onChange: (v: number | null) => void;
  kind?: NumKind;
  error?: string;
  hint?: string;
  disabled?: boolean;
  className?: string;
  compact?: boolean;
  nullable?: boolean;
}) {
  const id = useId();
  // Edit buffer exists only while focused; otherwise the field shows the formatted value.
  const [buffer, setBuffer] = useState<string | null>(null);
  const text = buffer ?? toText(value, kind);
  return (
    <div className={cn("space-y-1", className)}>
      <Label htmlFor={id} className={cn(compact && "sr-only")}>
        {label}
      </Label>
      <div className="relative">
        {kind === "usd" && <span className="pointer-events-none absolute left-2.5 top-2 text-sm text-muted-foreground">$</span>}
        <Input
          id={id}
          inputMode="decimal"
          value={text}
          disabled={disabled}
          aria-invalid={!!error}
          aria-describedby={error || hint ? `${id}-msg` : undefined}
          className={cn("tabular", kind === "usd" && "pl-6", kind === "pct" && "pr-7", compact && "h-8 text-xs")}
          onFocus={() => setBuffer(toText(value, kind))}
          onBlur={() => setBuffer(null)}
          onChange={(e) => {
            setBuffer(e.target.value);
            const n = fromText(e.target.value, kind);
            if (n !== null || nullable) onChange(n);
          }}
        />
        {kind === "pct" && <span className="pointer-events-none absolute right-2.5 top-2 text-sm text-muted-foreground">%</span>}
      </div>
      {(error || hint) && (
        <p id={`${id}-msg`} className={cn("text-[11px]", error ? "text-destructive" : "text-muted-foreground")}>
          {error ?? hint}
        </p>
      )}
    </div>
  );
}
