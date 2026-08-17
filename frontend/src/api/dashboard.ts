import { apiFetch } from "./client";
import type { Account } from "./accounts";
import type { Subscription } from "./billing";
import type { Balance } from "./credits";
import type { UsageSummary } from "./usage";

export interface DashboardSummary {
  account: Account | null;
  credits_balance: Balance | null;
  usage: UsageSummary | null;
  subscription: Subscription | null;
}

export function getDashboardSummary() {
  return apiFetch<DashboardSummary>("/dashboard/summary");
}
