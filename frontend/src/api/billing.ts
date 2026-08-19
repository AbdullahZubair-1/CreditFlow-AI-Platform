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
  refunded_amount_cents: number | null;
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

export interface PlanChangeResult {
  checkout_url: string | null;
  subscription: Subscription | null;
  wallet_credit_cents: number | null;
}

export function updateSubscription(plan: string) {
  const origin = window.location.origin;
  return apiFetch<PlanChangeResult>("/billing/subscription", {
    method: "PATCH",
    body: {
      plan,
      success_url: `${origin}/dashboard/billing?checkout=success`,
      cancel_url: `${origin}/dashboard/billing?checkout=cancelled`,
    },
  });
}

export function listInvoices() {
  return apiFetch<Invoice[]>("/billing/invoices");
}

export interface Refund {
  id: string;
  amount_cents: number;
  status: string;
}

export function createRefund(invoiceId: string, reason?: string) {
  return apiFetch<Refund>("/billing/refunds", {
    method: "POST",
    body: { invoice_id: invoiceId, reason },
  });
}
