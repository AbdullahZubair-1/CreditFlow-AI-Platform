import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import {
  cancelListing,
  createListing,
  getBalance,
  getCreditsPricing,
  listMarketplaceListings,
  purchaseListing,
  type Balance,
  type Listing,
} from "../api/credits";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";
import { useAuth } from "../context/AuthContext";

const MARKETPLACE_MIN_DISCOUNT_PERCENT = 5;

export default function MarketplacePage() {
  const { claims } = useAuth();
  const [params] = useSearchParams();

  const [balance, setBalance] = useState<Balance | null>(null);
  const [listings, setListings] = useState<Listing[]>([]);
  const [centsPerCredit, setCentsPerCredit] = useState<number | null>(null);
  const [creditsAmount, setCreditsAmount] = useState("");
  const [priceUsd, setPriceUsd] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<string | null>(null);
  const [busyListingId, setBusyListingId] = useState<string | null>(null);

  function refresh() {
    getBalance().then(setBalance).catch(() => undefined);
    listMarketplaceListings().then(setListings).catch(() => undefined);
  }

  useEffect(() => {
    refresh();
    getCreditsPricing().then((p) => setCentsPerCredit(p.cents_per_credit)).catch(() => undefined);
  }, []);

  const maxPricePerCreditUsd = centsPerCredit
    ? ((centsPerCredit * (100 - MARKETPLACE_MIN_DISCOUNT_PERCENT)) / 100 / 100).toFixed(4)
    : null;
  const maxTotalUsd =
    maxPricePerCreditUsd && Number(creditsAmount) > 0
      ? (Number(creditsAmount) * Number(maxPricePerCreditUsd)).toFixed(2)
      : null;

  async function handleCreateListing(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createListing(Number(creditsAmount), Math.round(Number(priceUsd) * 100));
      setCreditsAmount("");
      setPriceUsd("");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create listing.");
    }
  }

  async function confirmCancel() {
    if (!cancelTarget) return;
    try {
      await cancelListing(cancelTarget);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to cancel listing.");
    } finally {
      setCancelTarget(null);
    }
  }

  async function handlePurchase(listingId: string) {
    setError(null);
    setBusyListingId(listingId);
    try {
      const { checkout_url } = await purchaseListing(listingId);
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start purchase.");
      setBusyListingId(null);
    }
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Marketplace</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Buy and sell surplus credits between accounts — always at least {MARKETPLACE_MIN_DISCOUNT_PERCENT}% cheaper
        than buying directly from us.
      </p>

      {params.get("purchase") === "success" && (
        <p className="mt-4 rounded-md bg-emerald-500/10 px-4 py-2 text-sm text-emerald-600 dark:text-emerald-400">
          Purchase complete — credits will settle once Stripe confirms the payment.
        </p>
      )}
      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-6 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <p className="text-sm text-slate-500 dark:text-slate-400">Your balance</p>
        <p className="mt-1 text-2xl font-semibold">{balance ? balance.balance.toLocaleString() : "—"} credits</p>
        {balance && balance.sellable_balance < balance.balance && (
          <p className="mt-1 text-xs text-slate-500">
            {balance.sellable_balance.toLocaleString()} sellable — your free signup bonus can't be listed for sale.
          </p>
        )}
      </div>

      <h2 className="mt-8 text-lg font-semibold">List surplus credits for sale</h2>
      <form onSubmit={handleCreateListing} className="mt-3 flex flex-wrap items-end gap-3">
        <input
          type="number"
          min={1}
          max={balance?.sellable_balance}
          required
          placeholder="Credits amount"
          value={creditsAmount}
          onChange={(e) => setCreditsAmount(e.target.value)}
          className="w-40 rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
        />
        <div>
          <input
            type="number"
            min={0.01}
            step="0.01"
            required
            placeholder="Price (USD)"
            value={priceUsd}
            onChange={(e) => setPriceUsd(e.target.value)}
            className="w-40 rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
          />
          {maxTotalUsd && <p className="mt-1 text-xs text-slate-500">Max allowed: ${maxTotalUsd}</p>}
        </div>
        <button className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400">
          List for sale
        </button>
      </form>

      <h2 className="mt-10 text-lg font-semibold">Browse listings</h2>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {listings.map((listing) => {
          const isOwn = listing.seller_account_id === claims?.account_id;
          return (
            <div key={listing.id} className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-800 p-4">
              <div>
                <p className="font-medium">{listing.credits_amount.toLocaleString()} credits</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">${(listing.price_cents / 100).toFixed(2)}</p>
              </div>
              {isOwn ? (
                <button onClick={() => setCancelTarget(listing.id)} className="text-sm text-red-600 dark:text-red-400 hover:underline">
                  Cancel
                </button>
              ) : (
                <button
                  onClick={() => handlePurchase(listing.id)}
                  disabled={busyListingId === listing.id}
                  className="rounded-md bg-indigo-500 px-3 py-1.5 text-sm font-medium hover:bg-indigo-400 disabled:opacity-50"
                >
                  {busyListingId === listing.id ? "Starting checkout..." : "Buy"}
                </button>
              )}
            </div>
          );
        })}
        {listings.length === 0 && <p className="text-sm text-slate-500">No active listings right now.</p>}
      </div>

      <ConfirmDialog
        open={cancelTarget !== null}
        title="Cancel listing"
        message="This listing will be removed from the marketplace immediately."
        confirmLabel="Cancel listing"
        onConfirm={confirmCancel}
        onCancel={() => setCancelTarget(null)}
      />
    </AppLayout>
  );
}
