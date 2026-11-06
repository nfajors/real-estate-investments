"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Eraser, Send, Sparkles, User } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Callout } from "@/components/common";
import { useDeal } from "@/components/deal-context";
import { Button } from "@/components/ui/button";
import { Badge, Card, Select, Textarea } from "@/components/ui/primitives";
import { useOrgKey } from "@/hooks/queries";
import { api, streamEvents } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Msg {
  id: string;
  role: "user" | "assistant";
  content: string;
  model?: string | null;
}

const SUGGESTIONS = [
  "Explain how the levered IRR is calculated for this deal.",
  "What are the biggest risks in these assumptions?",
  "Is debt service coverage comfortable? Walk me through DSCR and debt yield.",
  "Which sensitivity ranges should I test before IC?",
  "Draft an investment thesis paragraph for the IC memo.",
  "Compare going-in and exit cap rates – are we assuming compression?",
];

/** Minimal, safe markdown: **bold**, _italic_, bullet lists, paragraphs. No HTML injection. */
function Markdown({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/);
  const inline = (s: string, key: string) =>
    s.split(/(\*\*[^*]+\*\*|_[^_]+_)/g).map((part, i) =>
      part.startsWith("**") && part.endsWith("**") ? (
        <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>
      ) : part.startsWith("_") && part.endsWith("_") && part.length > 2 ? (
        <em key={`${key}-${i}`} className="text-muted-foreground">
          {part.slice(1, -1)}
        </em>
      ) : (
        <span key={`${key}-${i}`}>{part}</span>
      ),
    );
  return (
    <div className="space-y-2 text-sm leading-relaxed">
      {blocks.map((b, i) => {
        const lines = b.split("\n");
        if (lines.every((l) => /^\s*[-•*]\s+/.test(l)))
          return (
            <ul key={i} className="list-disc space-y-1 pl-5">
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(/^\s*[-•*]\s+/, ""), `${i}-${j}`)}</li>
              ))}
            </ul>
          );
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <span key={j}>
                {inline(l.replace(/^#+\s*/, ""), `${i}-${j}`)}
                {j < lines.length - 1 && <br />}
              </span>
            ))}
          </p>
        );
      })}
    </div>
  );
}

export default function AnalystPage() {
  const { property, scenarios, base, canEdit } = useDeal();
  const org = useOrgKey();
  const qc = useQueryClient();
  const status = useQuery({ queryKey: ["analyst-status"], queryFn: () => api<{ ai_available: boolean; model: string }>("/api/analyst/status") });
  const history = useQuery({
    queryKey: [org, "chat", property.id],
    queryFn: () => api<Msg[]>(`/api/properties/${property.id}/analyst/messages`),
  });
  // Persisted history comes from the server; `live` holds the in-flight exchange until history refetches.
  const [live, setLive] = useState<Msg[]>([]);
  const messages = [...(history.data ?? []), ...live];
  const setMessages = setLive;
  const [input, setInput] = useState("");
  const [scenarioId, setScenarioId] = useState(base?.id ?? "");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, live]);
  useEffect(() => () => abort.current?.abort(), []);

  async function send(text: string) {
    const q = text.trim();
    if (!q || busy) return;
    setInput("");
    setBusy(true);
    const replyId = `pending-${Date.now()}`;
    setMessages((m) => [...m, { id: `u-${Date.now()}`, role: "user", content: q }, { id: replyId, role: "assistant", content: "" }]);
    abort.current = new AbortController();
    try {
      await streamEvents(
        `/api/properties/${property.id}/analyst/chat`,
        { message: q, scenario_id: scenarioId },
        (e) => {
          if (e.type === "delta" && e.text) setMessages((m) => m.map((x) => (x.id === replyId ? { ...x, content: x.content + e.text } : x)));
          if (e.type === "done") setMessages((m) => m.map((x) => (x.id === replyId ? { ...x, model: String(e.model ?? "") } : x)));
        },
        abort.current.signal,
      );
    } catch (e) {
      if (!(e instanceof DOMException && e.name === "AbortError")) toast.error(e instanceof Error ? e.message : "Analyst unavailable");
    } finally {
      await qc.invalidateQueries({ queryKey: [org, "chat", property.id] });
      setLive([]);
      setBusy(false);
    }
  }

  async function clear() {
    if (!confirm("Clear the conversation history for this deal?")) return;
    await api(`/api/properties/${property.id}/analyst/messages`, { method: "DELETE" });
    setLive([]);
    qc.invalidateQueries({ queryKey: [org, "chat", property.id] });
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
      <Card className="flex h-[calc(100vh-17rem)] min-h-[480px] flex-col">
        <div className="flex items-center gap-2 border-b px-4 py-2.5">
          <Sparkles className="size-4 text-accent" />
          <span className="text-sm font-medium">AI Investment Analyst</span>
          {status.data && (
            <Badge variant={status.data.ai_available ? "success" : "outline"}>
              {status.data.ai_available ? status.data.model : "Rule-based mode"}
            </Badge>
          )}
          <div className="ml-auto flex items-center gap-2">
            <Select value={scenarioId} onChange={(e) => setScenarioId(e.target.value)} className="h-8 w-44 text-xs" aria-label="Scenario context">
              {scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </Select>
            {canEdit && (
              <Button size="icon-sm" variant="ghost" onClick={clear} aria-label="Clear conversation" disabled={busy || !messages.length}>
                <Eraser />
              </Button>
            )}
          </div>
        </div>
        <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4" aria-live="polite">
          {messages.length === 0 && (
            <div className="mx-auto max-w-md py-10 text-center">
              <Bot className="mx-auto mb-3 size-8 text-muted-foreground" />
              <div className="text-sm font-medium">Ask about this deal</div>
              <p className="mt-1 text-sm text-muted-foreground">
                The analyst sees this scenario&apos;s engine output, assumptions, audit trace and verified document data — and nothing else. It never
                invents figures.
              </p>
            </div>
          )}
          {messages.map((m) => (
            <div key={m.id} className={cn("flex gap-3", m.role === "user" && "flex-row-reverse")}>
              <div className={cn("flex size-7 shrink-0 items-center justify-center rounded-full", m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted")}>
                {m.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
              </div>
              <div className={cn("max-w-[85%] rounded-lg px-3.5 py-2.5", m.role === "user" ? "bg-primary text-primary-foreground" : "border bg-card")}>
                {m.role === "assistant" ? (
                  m.content ? (
                    <Markdown text={m.content} />
                  ) : (
                    <span className="inline-flex gap-1" aria-label="Analyst is typing">
                      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground" />
                      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:120ms]" />
                      <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:240ms]" />
                    </span>
                  )
                ) : (
                  <p className="whitespace-pre-wrap text-sm">{m.content}</p>
                )}
                {m.role === "assistant" && m.model && <div className="mt-1.5 text-[10px] uppercase tracking-wide text-muted-foreground">{m.model}</div>}
              </div>
            </div>
          ))}
          <div ref={bottom} />
        </div>
        <form
          className="flex items-end gap-2 border-t p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <Textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(input);
              }
            }}
            placeholder="Ask about returns, risks, debt coverage… (Enter to send, Shift+Enter for a new line)"
            className="min-h-11 resize-none"
            rows={2}
            maxLength={4000}
            aria-label="Message the analyst"
          />
          <Button type="submit" size="icon" disabled={!input.trim() || busy} aria-label="Send">
            <Send />
          </Button>
        </form>
      </Card>
      <div className="space-y-4">
        <Card className="p-4">
          <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Suggested questions</div>
          <div className="space-y-1.5">
            {SUGGESTIONS.map((s) => (
              <button
                key={s}
                type="button"
                disabled={busy}
                onClick={() => send(s)}
                className="w-full rounded-md border px-3 py-2 text-left text-xs transition-colors hover:bg-muted disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        </Card>
        <Callout title="Guardrails">
          Answers may only cite numbers from the engine output, your assumptions and human-verified document data. Calculations are never overridden
          by the model.
          {status.data && !status.data.ai_available && " No model credentials are configured, so a deterministic template analyst answers instead."}
        </Callout>
      </div>
    </div>
  );
}
