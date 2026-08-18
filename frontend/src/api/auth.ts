import { apiFetch } from "./client";

// refresh_token is intentionally absent here — the Gateway strips it out
// of every response and sets it as an httpOnly cookie instead (see
// services/gateway/app/cookie_auth.py), so it never reaches frontend JS.
export interface TokenPair {
  access_token: string;
  token_type: string;
}

export function signup(email: string, password: string) {
  return apiFetch<{ user_id: string; email: string }>("/auth/signup", {
    method: "POST",
    body: { email, password },
    auth: false,
  });
}

export function login(email: string, password: string) {
  return apiFetch<TokenPair>("/auth/login", {
    method: "POST",
    body: { email, password },
    auth: false,
  });
}

export function logout(accessToken: string) {
  return apiFetch<void>("/auth/logout", {
    method: "POST",
    body: { access_token: accessToken },
    auth: false,
  });
}

export function verifyEmail(token: string) {
  return apiFetch<void>("/auth/verify-email", {
    method: "POST",
    body: { token },
    auth: false,
  });
}

export function forgotPassword(email: string) {
  return apiFetch<void>("/auth/forgot-password", {
    method: "POST",
    body: { email },
    auth: false,
  });
}

export function resetPassword(email: string, otp: string, newPassword: string) {
  return apiFetch<void>("/auth/reset-password", {
    method: "POST",
    body: { email, otp, new_password: newPassword },
    auth: false,
  });
}

export function switchAccount(accessToken: string, accountId: string) {
  return apiFetch<TokenPair>("/auth/switch-account", {
    method: "POST",
    body: { access_token: accessToken, account_id: accountId },
    auth: false,
  });
}
