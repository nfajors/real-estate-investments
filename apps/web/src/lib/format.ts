/** Number formatting helpers. Display-only: never used for calculations. */

const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usd2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const num0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

export const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

export function usd(v: number | null | undefined, decimals = 0): string {
  if (!isNum(v)) return "—";
  return decimals ? usd2.format(v) : usd0.format(v);
}

export function usdShort(v: number | null | undefined): string {
  if (!isNum(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return usd0.format(v);
}

export function pct(v: number | null | undefined, d = 2): string {
  if (!isNum(v)) return "—";
  return `${(v * 100).toFixed(d)}%`;
}

export function bps(v: number | null | undefined): string {
  if (!isNum(v)) return "—";
  return `${(v * 10000).toFixed(0)} bps`;
}

export function mult(v: number | null | undefined): string {
  if (!isNum(v)) return "—";
  return `${v.toFixed(2)}x`;
}

export function num(v: number | null | undefined, d = 0): string {
  if (!isNum(v)) return "—";
  return d ? v.toLocaleString("en-US", { maximumFractionDigits: d, minimumFractionDigits: d }) : num0.format(v);
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function relativeTime(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export const STATUS_LABELS: Record<string, string> = {
  sourcing: "Sourcing",
  underwriting: "Underwriting",
  ic: "Investment Committee",
  closed: "Closed",
  passed: "Passed",
};

export const STATUSES = ["sourcing", "underwriting", "ic", "closed", "passed"] as const;

export const TYPE_LABELS: Record<string, string> = {
  multifamily: "Multifamily",
  industrial: "Industrial",
  office: "Office",
  retail: "Retail",
  mixed_use: "Mixed-Use",
  hospitality: "Hospitality",
  self_storage: "Self-Storage",
  student_housing: "Student Housing",
  land: "Development Land",
};

export function stripDemo(name: string): string {
  return name.replace(/^\[DEMO\]\s*/, "");
}
