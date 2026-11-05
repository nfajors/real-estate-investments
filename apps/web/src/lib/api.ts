/**
 * API client. Access tokens live in memory only; the refresh token is an
 * httpOnly cookie scoped to /api/auth (same-origin via the Next.js rewrite).
 */

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
  get fieldErrors(): { field: string; message: string }[] {
    const d = this.detail as { errors?: { field: string; message: string }[] } | undefined;
    return d?.errors ?? [];
  }
}

let accessToken: string | null = null;
let orgId: string | null = null;
let refreshing: Promise<boolean> | null = null;
const listeners = new Set<() => void>();

const ORG_KEY = "axiom.org";

export function setAccessToken(t: string | null) {
  accessToken = t;
}

export function getOrgId(): string | null {
  if (orgId === null && typeof window !== "undefined") orgId = window.localStorage.getItem(ORG_KEY);
  return orgId;
}

export function setOrgId(id: string | null) {
  orgId = id;
  if (typeof window === "undefined") return;
  if (id) window.localStorage.setItem(ORG_KEY, id);
  else window.localStorage.removeItem(ORG_KEY);
}

export function onSessionExpired(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

export async function refreshSession(): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      try {
        const r = await fetch("/api/auth/refresh", { method: "POST", credentials: "same-origin" });
        if (!r.ok) return false;
        const data = await r.json();
        accessToken = data.access_token;
        return true;
      } catch {
        return false;
      } finally {
        setTimeout(() => {
          refreshing = null;
        }, 0);
      }
    })();
  }
  return refreshing;
}

function buildHeaders(extra?: HeadersInit): Headers {
  const h = new Headers(extra);
  if (accessToken) h.set("Authorization", `Bearer ${accessToken}`);
  const org = getOrgId();
  if (org) h.set("X-Org-Id", org);
  return h;
}

async function errorFrom(r: Response): Promise<ApiError> {
  let detail: unknown = undefined;
  let message = `${r.status} ${r.statusText}`;
  try {
    const body = await r.json();
    detail = body.detail;
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) message = detail.map((d: { msg?: string }) => d.msg).join("; ");
    else if (detail && typeof detail === "object" && "message" in detail) {
      const d = detail as { message: string; errors?: { field: string; message: string }[] };
      message = d.errors?.length
        ? `${d.message}: ${d.errors.map((e) => `${e.field} – ${e.message}`).join("; ")}`
        : d.message;
    }
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(r.status, message, detail);
}

export async function rawFetch(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const r = await fetch(path, { ...init, headers: buildHeaders(init.headers), credentials: "same-origin" });
  if (r.status === 401 && retry && !path.startsWith("/api/auth/")) {
    if (await refreshSession()) return rawFetch(path, init, false);
    listeners.forEach((fn) => fn());
  }
  return r;
}

export async function api<T = unknown>(
  path: string,
  opts: { method?: string; body?: unknown; form?: FormData; signal?: AbortSignal } = {},
): Promise<T> {
  const init: RequestInit = {
    method: opts.method ?? (opts.body !== undefined || opts.form ? "POST" : "GET"),
    signal: opts.signal,
  };
  if (opts.form) init.body = opts.form;
  else if (opts.body !== undefined) {
    init.body = JSON.stringify(opts.body);
    init.headers = { "Content-Type": "application/json" };
  }
  const r = await rawFetch(path, init);
  if (!r.ok) throw await errorFrom(r);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

/** Download an authenticated file (reports) through a temporary blob URL. */
export async function download(path: string, fallbackName: string) {
  const r = await rawFetch(path);
  if (!r.ok) throw await errorFrom(r);
  const blob = await r.blob();
  const cd = r.headers.get("Content-Disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(cd)?.[1] ?? fallbackName;
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type StreamEvent = { type: string; text?: string; [k: string]: unknown };

/** POST and consume a server-sent-events stream. */
export async function streamEvents(
  path: string,
  body: unknown,
  onEvent: (e: StreamEvent) => void,
  signal?: AbortSignal,
) {
  const r = await rawFetch(path, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    signal,
  });
  if (!r.ok || !r.body) throw await errorFrom(r);
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx = buf.indexOf("\n\n");
    while (idx >= 0) {
      const chunk = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of chunk.split("\n")) {
        if (line.startsWith("data: ")) onEvent(JSON.parse(line.slice(6)) as StreamEvent);
      }
      idx = buf.indexOf("\n\n");
    }
  }
}
