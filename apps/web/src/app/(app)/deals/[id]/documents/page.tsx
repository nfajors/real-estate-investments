"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, FileSpreadsheet, FileText, Image as ImageIcon, Loader2, Trash2, Upload, Wand2, XCircle } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { toast } from "sonner";

import { Callout, EmptyState, ErrorBlock, LoadingBlock } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { SectionCard } from "@/components/deal-widgets";
import { Button } from "@/components/ui/button";
import { Badge, Card, Select, Table, TBody, TD, TH, THead, TR } from "@/components/ui/primitives";
import { useDocuments, useOrgKey } from "@/hooks/queries";
import { api } from "@/lib/api";
import { dateTime } from "@/lib/format";
import type { DocumentRec, Extraction } from "@/lib/types";
import { cn } from "@/lib/utils";

const DOC_TYPES: Record<string, string> = {
  om: "Offering memorandum",
  t12: "T12 operating statement",
  rent_roll: "Rent roll",
  appraisal: "Appraisal",
  loan_doc: "Loan document / term sheet",
  model: "Financial model",
  image: "Image of table",
  other: "Other",
};

function DocIcon({ mime }: { mime: string }) {
  if (mime === "application/pdf") return <FileText className="size-4 text-muted-foreground" />;
  if (mime.startsWith("image/")) return <ImageIcon className="size-4 text-muted-foreground" />;
  return <FileSpreadsheet className="size-4 text-muted-foreground" />;
}

function StatusPill({ d }: { d: DocumentRec }) {
  if (d.status === "uploaded" || d.status === "processing")
    return (
      <Badge>
        <Loader2 className="size-3 animate-spin" /> {d.status === "uploaded" ? "Queued" : "Extracting"}
      </Badge>
    );
  if (d.status === "failed")
    return (
      <Badge variant="danger">
        <XCircle className="size-3" /> Failed
      </Badge>
    );
  return (
    <Badge variant="success">
      <CheckCircle2 className="size-3" /> Extracted
    </Badge>
  );
}

export default function DocumentsPage() {
  const { property, base, canEdit } = useDeal();
  const org = useOrgKey();
  const qc = useQueryClient();
  const docs = useDocuments(property.id);
  const extractions = useQuery({
    queryKey: [org, "extractions", property.id],
    queryFn: () => api<Extraction[]>(`/api/properties/${property.id}/extractions`),
    refetchInterval: docs.data?.some((d) => d.status === "uploaded" || d.status === "processing") ? 2000 : false,
  });
  const [docType, setDocType] = useState("om");
  const [dragging, setDragging] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  const upload = useMutation({
    mutationFn: async (files: File[]) => {
      for (const f of files) {
        const form = new FormData();
        form.append("file", f);
        form.append("doc_type", docType);
        await api(`/api/properties/${property.id}/documents`, { form });
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [org, "documents", property.id] });
      qc.invalidateQueries({ queryKey: [org, "extractions", property.id] });
      toast.success("Uploaded. Extraction runs in the background — review proposals when ready.");
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: string) => api(`/api/documents/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [org, "documents", property.id] }),
    onError: (e) => toast.error(e.message),
  });
  const apply = useMutation({
    mutationFn: () => api<{ applied_fields: string[]; changes: string[] }>(`/api/properties/${property.id}/extractions/apply`, { body: { scenario_id: base?.id } }),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: [org] });
      toast.success(`Applied ${r.applied_fields.length} verified fields to the base case and re-ran underwriting.`);
    },
    onError: (e) => toast.error(e.message),
  });

  const byDoc = new Map<string, Extraction[]>();
  (extractions.data ?? []).forEach((e) => byDoc.set(e.document_id, [...(byDoc.get(e.document_id) ?? []), e]));
  const verified = (extractions.data ?? []).filter((e) => e.status === "accepted" || e.status === "edited").length;
  const pending = (extractions.data ?? []).filter((e) => e.status === "pending").length;

  const onFiles = (list: FileList | null) => {
    if (list?.length) upload.mutate(Array.from(list));
  };

  return (
    <div className="space-y-5">
      <Callout title="AI proposes, you verify">
        Extracted values never enter the model until a person accepts or edits them. Every value links back to the page and excerpt (or
        spreadsheet cell) it came from.
      </Callout>
      <div className="grid gap-4 lg:grid-cols-3">
        {canEdit && (
          <Card
            className={cn("flex flex-col items-center justify-center border-dashed p-6 text-center transition-colors lg:col-span-2", dragging && "border-accent bg-accent/5")}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              onFiles(e.dataTransfer.files);
            }}
          >
            <Upload className="mb-2 size-6 text-muted-foreground" />
            <div className="text-sm font-medium">Drop offering materials here</div>
            <p className="mt-1 text-xs text-muted-foreground">PDF (OM, appraisal, loan docs), Excel / CSV (rent rolls, T12s, models), images of tables · up to 50 MB</p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              <Select value={docType} onChange={(e) => setDocType(e.target.value)} className="w-56" aria-label="Document type">
                {Object.entries(DOC_TYPES).map(([k, v]) => (
                  <option key={k} value={k}>
                    {v}
                  </option>
                ))}
              </Select>
              <Button onClick={() => input.current?.click()} loading={upload.isPending}>
                <Upload /> Choose files
              </Button>
              <input
                ref={input}
                type="file"
                multiple
                className="hidden"
                accept=".pdf,.xlsx,.xlsm,.csv,.png,.jpg,.jpeg,.webp"
                onChange={(e) => {
                  onFiles(e.target.files);
                  e.target.value = "";
                }}
              />
            </div>
          </Card>
        )}
        <SectionCard title="Verification status" description="Across all documents for this deal." className={canEdit ? "" : "lg:col-span-3"}>
          <dl className="grid grid-cols-2 gap-3 text-sm">
            <div>
              <dt className="text-xs text-muted-foreground">Verified fields</dt>
              <dd className="text-2xl font-semibold tabular">{verified}</dd>
            </div>
            <div>
              <dt className="text-xs text-muted-foreground">Awaiting review</dt>
              <dd className="text-2xl font-semibold tabular">{pending}</dd>
            </div>
          </dl>
          {canEdit && (
            <Button className="mt-4 w-full" variant="accent" disabled={!verified} loading={apply.isPending} onClick={() => apply.mutate()}>
              <Wand2 /> Apply verified data to base case
            </Button>
          )}
          <p className="mt-2 text-[11px] text-muted-foreground">Only accepted or edited values are applied. The change is audited and a new underwriting snapshot is stored.</p>
        </SectionCard>
      </div>

      {docs.isLoading && <LoadingBlock />}
      {docs.error && <ErrorBlock error={docs.error} />}
      {docs.data?.length === 0 && <EmptyState icon={FileText} title="No documents yet" description="Upload an OM, T12 or rent roll to begin AI-assisted extraction." />}
      {!!docs.data?.length && (
        <Card>
          <Table>
            <THead>
              <TR className="hover:bg-transparent">
                <TH>Document</TH>
                <TH>Type</TH>
                <TH>Status</TH>
                <TH>Extractor</TH>
                <TH className="text-right">Fields</TH>
                <TH>Uploaded</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {docs.data.map((d) => {
                const ex = byDoc.get(d.id) ?? [];
                const reviewed = ex.filter((e) => e.status !== "pending").length;
                return (
                  <TR key={d.id}>
                    <TD>
                      <div className="flex items-center gap-2">
                        <DocIcon mime={d.mime_type} />
                        <div className="min-w-0">
                          <div className="truncate font-medium">{d.name}</div>
                          <div className="text-xs text-muted-foreground">
                            {(d.size_bytes / 1024).toFixed(0)} KB{d.page_count ? ` · ${d.page_count} ${d.mime_type === "application/pdf" ? "pages" : "sheets"}` : ""}
                          </div>
                        </div>
                      </div>
                      {d.error && <div className="mt-1 text-xs text-warning">{d.error}</div>}
                    </TD>
                    <TD className="text-muted-foreground">{DOC_TYPES[d.type] ?? d.type}</TD>
                    <TD>
                      <StatusPill d={d} />
                    </TD>
                    <TD className="text-xs text-muted-foreground">{d.extractor ?? "—"}</TD>
                    <TD className="text-right tabular">
                      {ex.length ? (
                        <span>
                          {reviewed}/{ex.length} reviewed
                        </span>
                      ) : (
                        "—"
                      )}
                    </TD>
                    <TD className="text-xs text-muted-foreground">{dateTime(d.created_at)}</TD>
                    <TD className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button size="sm" variant={ex.some((e) => e.status === "pending") ? "default" : "outline"} asChild disabled={d.status !== "extracted"}>
                          <Link href={`/deals/${property.id}/documents/${d.id}`}>Review</Link>
                        </Button>
                        {canEdit && (
                          <Button size="icon-sm" variant="ghost" aria-label={`Delete ${d.name}`} onClick={() => confirm(`Delete ${d.name}?`) && remove.mutate(d.id)}>
                            <Trash2 />
                          </Button>
                        )}
                      </div>
                    </TD>
                  </TR>
                );
              })}
            </TBody>
          </Table>
        </Card>
      )}
    </div>
  );
}
