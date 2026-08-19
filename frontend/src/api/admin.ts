import { apiFetch } from "./client";

export interface AccountDirectoryEntry {
  account_id: string;
  name: string;
  type: string;
  plan_tier: string;
  total_revenue_cents: number;
}

export interface AccountOverview {
  account_id: string;
  name: string | null;
  type: string | null;
  plan_tier: string | null;
  member_count: number | null;
  subscription_status: string | null;
  credit_balance: number | null;
  usage_this_period_tokens: number | null;
  usage_quota_tokens: number | null;
  total_revenue_cents: number;
  owner_email: string | null;
  owner_email_verified: boolean | null;
  owner_created_at: string | null;
}

export interface UserDirectoryEntry {
  user_id: string;
  email: string;
  email_verified: boolean;
  is_platform_admin: boolean;
  created_at: string;
}

export interface UserDirectory {
  total_revenue_cents: number;
  users: UserDirectoryEntry[];
}

export interface AdminSession {
  jti: string;
  user_id: string;
  account_id: string;
  expires_in_seconds: number;
}

export interface AuditLogEntry {
  id: string;
  event_id: string;
  event_type: string;
  source_exchange: string;
  account_id: string | null;
  payload: Record<string, unknown>;
  occurred_at: string;
  received_at: string;
}

export function listAllAccounts() {
  return apiFetch<AccountDirectoryEntry[]>("/admin/accounts");
}

export function listAllUsers() {
  return apiFetch<UserDirectory>("/admin/users");
}

export function getAccountOverview(accountId: string) {
  return apiFetch<AccountOverview>(`/admin/accounts/${accountId}/overview`);
}

export function listAccountSessions(accountId: string) {
  return apiFetch<AdminSession[]>(`/admin/accounts/${accountId}/sessions`);
}

export function revokeSession(jti: string) {
  return apiFetch<void>(`/admin/sessions/${jti}/revoke`, { method: "POST" });
}

export function getAccountAuditLog(accountId: string, limit = 100) {
  return apiFetch<AuditLogEntry[]>(`/admin/accounts/${accountId}/audit-log?limit=${limit}`);
}

export function getPlatformAuditLog(limit = 100) {
  return apiFetch<AuditLogEntry[]>(`/admin/audit-log?limit=${limit}`);
}
