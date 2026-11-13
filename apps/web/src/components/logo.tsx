import { cn } from "@/lib/utils";

/** Axiom mark: a precise gold apex over a navy foundation. Original artwork. */
export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <rect width="32" height="32" rx="7" fill="#0B1F3A" />
      <path d="M16 6 L26 25 H21.6 L16 14.4 L10.4 25 H6 Z" fill="#C9A227" />
      <rect x="12.2" y="20.2" width="7.6" height="2.4" rx="0.6" fill="#FFFFFF" opacity="0.92" />
    </svg>
  );
}

export function Logo({ className, light = false }: { className?: string; light?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <LogoMark />
      <span className={cn("text-[15px] font-semibold tracking-[0.18em]", light ? "text-white" : "text-foreground")}>
        AXIOM
      </span>
    </span>
  );
}
