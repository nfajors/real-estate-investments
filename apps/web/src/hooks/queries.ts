"use client";

import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type {
  DocumentRec,
  Feature,
  FieldDef,
  Financing,
  Property,
  PropertyTypeDef,
  Scenario,
  ScenarioComparisonRow,
  StoredResult,
} from "@/lib/types";

/** Query keys are namespaced by organization so switching workspaces never shows stale tenant data. */
export function useOrgKey() {
  return useAuth().org?.org_id ?? "none";
}

export function useProperties(params: Record<string, string | undefined> = {}) {
  const org = useOrgKey();
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v) as [string, string][]).toString();
  return useQuery({
    queryKey: [org, "properties", qs],
    queryFn: () => api<Property[]>(`/api/properties${qs ? `?${qs}` : ""}`),
  });
}

export function useProperty(id: string) {
  const org = useOrgKey();
  return useQuery({ queryKey: [org, "property", id], queryFn: () => api<Property>(`/api/properties/${id}`) });
}

export function useScenarios(propertyId: string) {
  const org = useOrgKey();
  return useQuery({
    queryKey: [org, "scenarios", propertyId],
    queryFn: () => api<Scenario[]>(`/api/properties/${propertyId}/scenarios`),
  });
}

export function useScenarioResult(scenarioId: string | undefined) {
  const org = useOrgKey();
  return useQuery({
    queryKey: [org, "result", scenarioId],
    queryFn: () => api<StoredResult>(`/api/scenarios/${scenarioId}/result`),
    enabled: !!scenarioId,
  });
}

export function useScenarioComparison(propertyId: string) {
  const org = useOrgKey();
  return useQuery({
    queryKey: [org, "scenario-comparison", propertyId],
    queryFn: () => api<ScenarioComparisonRow[]>(`/api/properties/${propertyId}/scenario-comparison`),
  });
}

export function useDocuments(propertyId: string, poll = false) {
  const org = useOrgKey();
  return useQuery({
    queryKey: [org, "documents", propertyId],
    queryFn: () => api<DocumentRec[]>(`/api/properties/${propertyId}/documents`),
    refetchInterval: (q) =>
      poll || q.state.data?.some((d) => d.status === "uploaded" || d.status === "processing") ? 2000 : false,
  });
}

export function useFinancing(propertyId: string) {
  const org = useOrgKey();
  return useQuery({
    queryKey: [org, "financing", propertyId],
    queryFn: () => api<Financing[]>(`/api/properties/${propertyId}/financing`),
  });
}

export function useFeatures() {
  const org = useOrgKey();
  return useQuery({
    queryKey: [org, "features"],
    queryFn: () => api<Record<string, Feature>>("/api/features"),
    staleTime: 60_000,
  });
}

export function useFeature(key: string): boolean | undefined {
  const { data } = useFeatures();
  return data ? data[key]?.enabled : undefined;
}

export function usePropertyTypes() {
  return useQuery({
    queryKey: ["property-types"],
    queryFn: () => api<PropertyTypeDef[]>("/api/property-types"),
    staleTime: Infinity,
  });
}

export function useExtractionFields() {
  return useQuery({
    queryKey: ["extraction-fields"],
    queryFn: () => api<Record<string, FieldDef>>("/api/extraction-fields"),
    staleTime: Infinity,
  });
}

export interface AuditEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string | null;
  property_id: string | null;
  details: Record<string, unknown>;
  user_name: string | null;
  created_at: string;
}

export function useAudit(propertyId?: string) {
  const org = useOrgKey();
  return useQuery({
    queryKey: [org, "audit", propertyId ?? "all"],
    queryFn: () => api<AuditEntry[]>(`/api/org/audit?limit=200${propertyId ? `&property_id=${propertyId}` : ""}`),
  });
}
