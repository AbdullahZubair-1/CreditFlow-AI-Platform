import { decodeJwt } from "./jwt";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";

export class ApiError extends Error {
  code: string;
  status: number;
  details?: unknown;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

// Access token lives in memory only, per the spec ("access token in
// memory, refresh token in an httpOnly cookie set by the Gateway"). The
// refresh token itself never reaches this file at all — the Gateway
// (see services/gateway/app/cookie_auth.py) strips it out of every
// login/refresh/switch-account response and sets it as an httpOnly cookie
// instead, so no JS running on this page can ever read or exfiltrate it.
//
// A full-page navigation (e.g. the LinkedIn OAuth connect redirect) still
// clears this in-memory variable, same as any page reload would — but
// unlike the earlier sessionStorage-based approach, that's fine here: the
// httpOnly cookie survives the reload on its own, and AuthProvider calls
// tryRestoreSession() on mount to silently exchange it for a fresh access
// token, so the user never has to re-authenticate.
let accessToken: string | null = null;
let onTokensChanged: ((access: string | null) => void) | null = null;

export function setAccessToken(access: string | null) {
  accessToken = access;
  onTokensChanged?.(access);
}

function getCurrentAccountId(): string | null {
  if (!accessToken) return null;
  return decodeJwt(accessToken)?.account_id ?? null;
}

export function getAccessToken() {
  return accessToken;
}

export function subscribeToTokenChanges(cb: (access: string | null) => void) {
  onTokensChanged = cb;
}

async function parseErrorBody(res: Response): Promise<ApiError> {
  try {
    const body = await res.json();
    const err = body?.error ?? {};
    return new ApiError(err.code ?? "unknown_error", err.message ?? res.statusText, res.status, err.details);
  } catch {
    return new ApiError("unknown_error", res.statusText, res.status);
  }
}

// The refresh token cookie is httpOnly, so it's attached to this request
// by the browser automatically (credentials: "include") — this file never
// sees its value. account_id is passed so silent refresh doesn't reset the
// user back to their default account if they'd switched away from it.
//
// Single-flight: refresh tokens rotate on use (Auth revokes the old one in
// the same transaction that issues a new pair), so two concurrent calls to
// this function racing on the same not-yet-rotated cookie value is a real
// failure mode, not a hypothetical one — a page that mounts several
// components at once (AuthContext's own mount-time refresh, plus every
// other one's 401-triggered refresh) all fire independently the moment the
// access token has expired, which is exactly what happens after returning
// from a real, multi-minute Stripe Checkout redirect. Only the first
// request to reach Auth succeeds; every other one gets rejected as an
// already-used token and calls setAccessToken(null) — and if that failure
// resolves *after* the winning call's success, it wipes the just-restored
// session, incorrectly bouncing an actually-still-logged-in user to
// /login. Sharing one in-flight promise across every concurrent caller
// means only one real request ever goes out.
let refreshPromise: Promise<boolean> | null = null;

export async function refreshAccessToken(): Promise<boolean> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const accountId = getCurrentAccountId();
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ account_id: accountId }),
    });
    if (!res.ok) {
      setAccessToken(null);
      return false;
    }
    const data = await res.json();
    setAccessToken(data.access_token);
    return true;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

export async function apiFetch<T>(
  path: string,
  options: { method?: string; body?: unknown; auth?: boolean } = {}
): Promise<T> {
  const { method = "GET", body, auth = true } = options;

  const doRequest = async (): Promise<Response> => {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`;
    return fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      credentials: "include",
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  };

  let res = await doRequest();

  if (res.status === 401 && auth) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      res = await doRequest();
    }
  }

  if (!res.ok) {
    throw await parseErrorBody(res);
  }

  if (res.status === 204) {
    return undefined as T;
  }

  return res.json() as Promise<T>;
}
