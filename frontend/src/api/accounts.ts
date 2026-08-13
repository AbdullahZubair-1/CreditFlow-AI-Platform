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
