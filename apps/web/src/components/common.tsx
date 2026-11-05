"use client";

import { AlertTriangle, Info } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import * as React from "react";

import { Badge, Card, Skeleton } from "@/components/ui/primitives";
import { Tooltip } from "@/components/ui/tooltip";
import { STATUS_LABELS } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
  eyebrow,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  eyebrow?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <div className="mb-1 text-xs font-medium text-muted-foreground">{eyebrow}</div>}
        <h1 className="truncate text-xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Metric({
  label,
  value,
  sub,
  hint,
  tone,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  hint?: string;
  tone?: "good" | "bad" | "warn";
  className?: string;
}) {
  return (
    <Card className={cn("px-4 py-3.5", className)}>
      <div className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
        {hint && (
          <Tooltip content={hint}>
            <button type="button" aria-label={`About ${label}`} className="text-muted-foreground/70">
              <Info className="size-3" />
            </button>
          </Tooltip>
        )}
      </div>
      <div
        className={cn(
          "mt-1 text-xl font-semibold tabular tracking-tight",
          tone === "good" && "text-success",
          tone === "bad" && "text-destructive",
          tone === "warn" && "text-warning",
        )}
      >
        {value}
      </div>
      {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
    </Card>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
}: {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed px-6 py-14 text-center">
      <div className="mb-3 rounded-full bg-muted p-3">
        <Icon className="size-5 text-muted-foreground" />
      </div>
      <h3 className="text-sm font-semibold">{title}</h3>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

const STATUS_TONE: Record<string, "default" | "accent" | "success" | "warning" | "outline"> = {
  sourcing: "outline",
  underwriting: "default",
  ic: "accent",
  closed: "success",
  passed: "warning",
};

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={STATUS_TONE[status] ?? "default"}>{STATUS_LABELS[status] ?? status}</Badge>;
}

export function RiskBadge({ level, score }: { level?: string | null; score?: number | null }) {
  if (!level) return <span className="text-xs text-muted-foreground">—</span>;
  const variant = level === "high" ? "danger" : level === "moderate" ? "warning" : "success";
  return (
    <Badge variant={variant}>
      {level}
      {score !== undefined && score !== null && <span className="opacity-70">· {Math.round(score)}</span>}
    </Badge>
  );
}

export function DemoBadge() {
  return (
    <Tooltip content="Fictional sample data for demonstration only. Exports are watermarked.">
      <Badge variant="demo">Demo</Badge>
    </Tooltip>
  );
}

export function Callout({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: "info" | "warn" | "danger";
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  const Icon = tone === "info" ? Info : AlertTriangle;
  return (
    <div
      className={cn(
        "flex gap-3 rounded-md border px-3.5 py-3 text-sm",
        tone === "info" && "border-border bg-muted/60",
        tone === "warn" && "border-warning/30 bg-warning/8",
        tone === "danger" && "border-destructive/30 bg-destructive/8",
        className,
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 size-4 shrink-0",
          tone === "info" && "text-muted-foreground",
          tone === "warn" && "text-warning",
          tone === "danger" && "text-destructive",
        )}
      />
      <div className="min-w-0">
        {title && <div className="font-medium">{title}</div>}
        <div className="text-muted-foreground">{children}</div>
      </div>
    </div>
  );
}

export function LoadingBlock({ rows = 3, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-10 w-full" />
      ))}
    </div>
  );
}

export function ErrorBlock({ error }: { error: unknown }) {
  return (
    <Callout tone="danger" title="Something went wrong">
      {error instanceof Error ? error.message : String(error)}
    </Callout>
  );
}
