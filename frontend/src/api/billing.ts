import { apiFetch } from "./client";

export interface Plan {
  tier: string;
  display_price_cents: number;
  stripe_price_id: string | null;
}

export interface Subscription {
  account_id: string;
  plan_tier: string;
  status: string;
  grace_period_ends_at: string | null;
}

export interface Invoice {
  id: string;
  amount_cents: number;
  currency: string;
  status: string;
  created_at: string;
}

export function listPlans() {
  return apiFetch<Plan[]>("/billing/plans");
}

export function getSubscription() {
  return apiFetch<Subscription>("/billing/subscription");
}

export function createCheckoutSession(plan: string) {
  const origin = window.location.origin;
  return apiFetch<{ checkout_url: string }>("/billing/checkout-session", {
    method: "POST",
    body: {
      plan,
      success_url: `${origin}/dashboard/billing?checkout=success`,
      cancel_url: `${origin}/dashboard/billing?checkout=cancelled`,
    },
  });
}

export function updateSubscription(plan: string) {
  return apiFetch<Subscription>("/billing/subscription", { method: "PATCH", body: { plan } });
}

export function listInvoices() {
  return apiFetch<Invoice[]>("/billing/invoices");
}
