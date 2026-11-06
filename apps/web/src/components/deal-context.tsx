"use client";

import { createContext, useContext } from "react";

import type { Property, Scenario } from "@/lib/types";

export interface DealCtx {
  property: Property;
  scenarios: Scenario[];
  base: Scenario | undefined;
  canEdit: boolean;
}

export const DealContext = createContext<DealCtx | null>(null);

/** Property, its scenarios and the base scenario – provided by app/(app)/deals/[id]/layout.tsx. */
export function useDeal(): DealCtx {
  const ctx = useContext(DealContext);
  if (!ctx) throw new Error("useDeal must be used inside the deal layout");
  return ctx;
}
