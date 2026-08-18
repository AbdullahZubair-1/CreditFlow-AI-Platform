import { apiFetch } from "./client";

export interface ModelUsageSummary {
  model: string;
  total_tokens: number;
  cost_cents: number;
  call_count: number;
}

export interface UsageSummary {
  account_id: string;
  period: string;
  plan_tier: string;
  used_tokens: number;
  quota_tokens: number;
  by_model: ModelUsageSummary[];
}

export function getUsageSummary() {
  return apiFetch<UsageSummary>("/usage/summary");
}
