import type { QueryFilters, QueryResponse, UnsupportedResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";

export type QueryResult =
  | { ok: true; data: QueryResponse }
  | { ok: false; kind: "unsupported"; data: UnsupportedResponse }
  | { ok: false; kind: "error"; message: string };

/** Minimal runtime guard so a malformed 200 body surfaces a clear error instead of crashing later. */
function isQueryResponse(b: unknown): b is QueryResponse {
  if (!b || typeof b !== "object") return false;
  const r = b as Record<string, unknown>;
  const viz = r.visualization as Record<string, unknown> | undefined;
  return (
    typeof r.query === "string" &&
    typeof r.interpretation === "object" &&
    r.interpretation !== null &&
    typeof viz === "object" &&
    viz !== null &&
    typeof viz.type === "string" &&
    "data" in viz &&
    typeof viz.metadata === "object" &&
    Array.isArray(r.citations)
  );
}

/** Drop empty strings / arrays / NaN years so only meaningful filters reach the API. */
function cleanFilters(filters?: QueryFilters): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(filters ?? {})) {
    if (value === undefined || value === null) continue;
    if (typeof value === "string") {
      if (value.trim() === "") continue;
      out[key] = value.trim();
    } else if (Array.isArray(value)) {
      if (value.length === 0) continue;
      out[key] = value;
    } else if (typeof value === "number") {
      if (Number.isNaN(value)) continue;
      out[key] = value;
    }
  }
  return out;
}

export async function runQuery(
  query: string,
  forceQueryType?: string,
  filters?: QueryFilters,
): Promise<QueryResult> {
  const payload: Record<string, unknown> = { query, ...cleanFilters(filters) };
  if (forceQueryType) payload.force_query_type = forceQueryType;
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/query`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch (err) {
    return { ok: false, kind: "error", message: `Network error: ${String(err)}` };
  }

  const body = await resp.json().catch(() => null);
  if (resp.ok) {
    if (isQueryResponse(body)) return { ok: true, data: body };
    return { ok: false, kind: "error", message: "The server returned an unexpected response shape." };
  }
  if (resp.status === 422 && body && body.error === "unsupported_query") {
    return { ok: false, kind: "unsupported", data: body as UnsupportedResponse };
  }
  const message =
    (body && (body.message || body.detail)) || `Request failed (${resp.status})`;
  return { ok: false, kind: "error", message: typeof message === "string" ? message : "Request failed" };
}

export async function getEvent(eventId: string): Promise<QueryResult> {
  let resp: Response;
  try {
    resp = await fetch(`${API_BASE}/events/${eventId}`);
  } catch (err) {
    return { ok: false, kind: "error", message: `Network error: ${String(err)}` };
  }
  if (resp.status === 404) {
    return { ok: false, kind: "error", message: "This saved result was not found." };
  }
  const body = await resp.json().catch(() => null);
  if (!resp.ok || !body) {
    return { ok: false, kind: "error", message: "Failed to load the saved result." };
  }
  if (body.error === "unsupported_query") {
    return { ok: false, kind: "unsupported", data: body as UnsupportedResponse };
  }
  if (isQueryResponse(body)) return { ok: true, data: body };
  return { ok: false, kind: "error", message: "The saved result is malformed." };
}
