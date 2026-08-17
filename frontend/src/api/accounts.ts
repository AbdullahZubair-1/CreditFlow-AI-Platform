import { apiFetch } from "./client";

export interface Account {
  id: string;
  type: "individual" | "team";
  name: string;
  plan_tier: string;
  role: string;
}

export function listMyAccounts() {
  return apiFetch<Account[]>("/me/accounts");
}

export function createTeamAccount(name: string) {
  return apiFetch<Account>("/accounts", { method: "POST", body: { name } });
}

export function acceptInvite(token: string) {
  return apiFetch<{ account_id: string; role: string }>(`/invites/${token}/accept`, {
    method: "POST",
  });
}

export interface Member {
  user_id: string;
  role: string;
  joined_at: string;
}

export function listMembers(accountId: string) {
  return apiFetch<Member[]>(`/accounts/${accountId}/members`);
}

export function inviteMember(accountId: string, email: string, role: string) {
  return apiFetch<{ invite_id: string }>(`/accounts/${accountId}/invite`, {
    method: "POST",
    body: { email, role },
  });
}

export function updateMemberRole(accountId: string, userId: string, role: string) {
  return apiFetch<Member>(`/accounts/${accountId}/members/${userId}`, {
    method: "PATCH",
    body: { role },
  });
}

export function removeMember(accountId: string, userId: string) {
  return apiFetch<void>(`/accounts/${accountId}/members/${userId}`, { method: "DELETE" });
}
