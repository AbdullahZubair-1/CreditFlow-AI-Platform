import { apiFetch } from "./client";

export interface Balance {
  account_id: string;
  balance: number;
  sellable_balance: number;
}

export interface LedgerEntry {
  id: string;
  delta: number;
  reason: string;
  reference_id: string | null;
  balance_after: number;
  created_at: string;
}

export interface Listing {
  id: string;
  seller_account_id: string;
  credits_amount: number;
  price_cents: number;
  status: string;
  created_at: string;
}

export function getBalance() {
  return apiFetch<Balance>("/credits/balance");
}

export function listTransactions() {
  return apiFetch<LedgerEntry[]>("/credits/transactions");
}

export function listMarketplaceListings() {
  return apiFetch<Listing[]>("/credits/marketplace/listings");
}

export function createListing(creditsAmount: number, priceCents: number) {
  return apiFetch<Listing>("/credits/marketplace/listings", {
    method: "POST",
    body: { credits_amount: creditsAmount, price_cents: priceCents },
  });
}

export function cancelListing(listingId: string) {
  return apiFetch<void>(`/credits/marketplace/listings/${listingId}`, { method: "DELETE" });
}

export function purchaseListing(listingId: string) {
  const origin = window.location.origin;
  return apiFetch<{ checkout_url: string }>(`/credits/marketplace/listings/${listingId}/purchase`, {
    method: "POST",
    body: {
      success_url: `${origin}/dashboard/marketplace?purchase=success`,
      cancel_url: `${origin}/dashboard/marketplace?purchase=cancelled`,
    },
  });
}

export function getPlanGrants() {
  return apiFetch<Record<string, number>>("/credits/plan-grants");
}

export function getCreditsPricing() {
  return apiFetch<{ cents_per_credit: number }>("/billing/credits/pricing");
}

export function createDirectPurchaseCheckout(creditsAmount: number) {
  const origin = window.location.origin;
  return apiFetch<{ checkout_url: string }>("/billing/credits/checkout-session", {
    method: "POST",
    body: {
      credits_amount: creditsAmount,
      success_url: `${origin}/dashboard/credits?purchase=success`,
      cancel_url: `${origin}/dashboard/credits?purchase=cancelled`,
    },
  });
}

export interface WalletBalance {
  balance_cents: number;
}

export interface WalletLedgerEntry {
  id: string;
  delta_cents: number;
  reason: string;
  reference_id: string | null;
  balance_after_cents: number;
  created_at: string;
}

export interface PayoutRequest {
  id: string;
  account_id: string;
  amount_cents: number;
  destination: string;
  status: string;
  requested_at: string;
  completed_at: string | null;
}

export function getWalletBalance() {
  return apiFetch<WalletBalance>("/credits/wallet/balance");
}

export function listWalletTransactions() {
  return apiFetch<WalletLedgerEntry[]>("/credits/wallet/transactions");
}

export function listMyPayoutRequests() {
  return apiFetch<PayoutRequest[]>("/credits/wallet/payout-requests");
}

export function requestPayout(amountCents: number, destination: string) {
  return apiFetch<PayoutRequest>("/credits/wallet/payout-requests", {
    method: "POST",
    body: { amount_cents: amountCents, destination },
  });
}
