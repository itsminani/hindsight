/**
 * Typed API client, generated from contract/openapi.yaml (see `npm run gen:api`).
 *
 * If the contract changes and this code no longer matches it, `tsc` fails the build:
 * the frontend is held to the same contract as the backend.
 */
import createClient, { type Middleware } from "openapi-fetch";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];
export type Problem = Schemas["Problem"];

/** One line in the request inspector: what was called, how it went, and its correlation ID. */
export interface CallRecord {
  id: number;
  method: string;
  path: string;
  status: number;
  ms: number;
  requestId: string | null;
  code: string | null;
  at: Date;
}

type Listener = (calls: CallRecord[]) => void;
type UnauthorizedListener = () => void;

let token: string | null = sessionStorage.getItem("hindsight.token");
let calls: CallRecord[] = [];
let nextCallId = 1;
const listeners = new Set<Listener>();
const unauthorizedListeners = new Set<UnauthorizedListener>();
const startedAt = new WeakMap<Request, number>();

/** Remember the access token for later requests (kept for this browser tab only). */
export function setToken(value: string | null): void {
  token = value;
  if (value) sessionStorage.setItem("hindsight.token", value);
  else sessionStorage.removeItem("hindsight.token");
}

/** The current access token, or null when signed out. */
export function getToken(): string | null {
  return token;
}

/** Subscribe to the call log; returns a function that unsubscribes. */
export function onCalls(listener: Listener): () => void {
  listeners.add(listener);
  listener(calls);
  return () => listeners.delete(listener);
}

/** Called when the API answers 401 (token expired or invalid), so the app can show sign-in again. */
export function onUnauthorized(listener: UnauthorizedListener): () => void {
  unauthorizedListeners.add(listener);
  return () => unauthorizedListeners.delete(listener);
}

/** Add one record to the call log (newest first, last 200 kept). */
function record(entry: Omit<CallRecord, "id" | "at">): void {
  calls = [{ ...entry, id: nextCallId++, at: new Date() }, ...calls].slice(0, 200);
  listeners.forEach((l) => l(calls));
}

/** Adds the Bearer token, times each call, and logs it with its X-Request-ID. */
const observe: Middleware = {
  onRequest({ request }) {
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    startedAt.set(request, performance.now());
    return request;
  },
  async onResponse({ request, response }) {
    let code: string | null = null;
    if (response.headers.get("content-type")?.includes("problem+json")) {
      code = ((await response.clone().json()) as Problem).code;
    }
    record({
      method: request.method,
      path: new URL(request.url).pathname.replace(/^\/api/, ""),
      status: response.status,
      ms: Math.round(performance.now() - (startedAt.get(request) ?? performance.now())),
      requestId: response.headers.get("X-Request-ID"),
      code,
    });
    if (response.status === 401 && !request.url.endsWith("/auth/token")) {
      setToken(null);
      unauthorizedListeners.forEach((l) => l());
    }
    return response;
  },
};

/** The client every screen uses. Paths, bodies and responses are all type-checked. */
export const api = createClient<paths>({ baseUrl: "/api" });
api.use(observe);

/** Turn an error body into a short message for the screen, preferring the contract's fields. */
export function describeProblem(error: unknown): string {
  const p = error as Partial<Problem> | undefined;
  if (p?.errors?.length) return p.errors.map((e) => `${e.field}: ${e.message}`).join(" · ");
  return p?.detail ?? p?.title ?? "Something went wrong";
}
