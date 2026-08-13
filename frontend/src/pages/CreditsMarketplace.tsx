import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import {
  cancelListing,
  createListing,
  getBalance,
  listMarketplaceListings,
  listTransactions,
  purchaseListing,
  type Balance,
  type LedgerEntry,
  type Listing,
} from "../api/credits";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";
import { useAuth } from "../context/AuthContext";

export default function CreditsMarketplace() {
  const { claims } = useAuth();
  const [params] = useSearchParams();

  const [balance, setBalance] = useState<Balance | null>(null);
  const [transactions, setTransactions] = useState<LedgerEntry[]>([]);
  const [listings, setListings] = useState<Listing[]>([]);
  const [creditsAmount, setCreditsAmount] = useState("");
  const [priceCents, setPriceCents] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<string | null>(null);
  const [busyListingId, setBusyListingId] = useState<string | null>(null);

  function refresh() {
    getBalance().then(setBalance).catch(() => undefined);
    listTransactions().then(setTransactions).catch(() => undefined);
    listMarketplaceListings().then(setListings).catch(() => undefined);
  }

  useEffect(refresh, []);

  async function handleCreateListing(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createListing(Number(creditsAmount), Math.round(Number(priceCents) * 100));
      setCreditsAmount("");
      setPriceCents("");
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
      <h1 className="text-2xl font-semibold">Credits &amp; Marketplace</h1>

      {params.get("purchase") === "success" && (
        <p className="mt-4 rounded-md bg-emerald-500/10 px-4 py-2 text-sm text-emerald-400">
          Purchase complete — credits will settle once Stripe confirms the payment.
        </p>
      )}
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-5">
        <p className="text-sm text-slate-400">Current balance</p>
        <p className="mt-1 text-3xl font-semibold">{balance ? balance.balance.toLocaleString() : "—"} credits</p>
      </div>

      <h2 className="mt-8 text-lg font-semibold">List surplus credits for sale</h2>
      <form onSubmit={handleCreateListing} className="mt-3 flex flex-wrap items-end gap-3">
        <input
          type="number"
          min={1}
          required
          placeholder="Credits amount"
          value={creditsAmount}
          onChange={(e) => setCreditsAmount(e.target.value)}
          className="w-40 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none"
        />
        <input
          type="number"
          min={0.01}
          step="0.01"
          required
          placeholder="Price (USD)"
          value={priceCents}
          onChange={(e) => setPriceCents(e.target.value)}
          className="w-40 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none"
        />
        <button className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400">
          List for sale
        </button>
      </form>

      <h2 className="mt-10 text-lg font-semibold">Marketplace</h2>
      <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
        {listings.map((listing) => {
          const isOwn = listing.seller_account_id === claims?.account_id;
          return (
            <div key={listing.id} className="flex items-center justify-between rounded-lg border border-slate-800 p-4">
              <div>
                <p className="font-medium">{listing.credits_amount.toLocaleString()} credits</p>
                <p className="text-sm text-slate-400">${(listing.price_cents / 100).toFixed(2)}</p>
              </div>
              {isOwn ? (
                <button onClick={() => setCancelTarget(listing.id)} className="text-sm text-red-400 hover:underline">
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

      <h2 className="mt-10 text-lg font-semibold">Transaction history</h2>
      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-left text-slate-400">
            <tr>
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2">Reason</th>
              <th className="px-4 py-2">Change</th>
              <th className="px-4 py-2">Balance after</th>
            </tr>
          </thead>
          <tbody>
            {transactions.map((t) => (
              <tr key={t.id} className="border-t border-slate-800">
                <td className="px-4 py-2">{new Date(t.created_at).toLocaleDateString()}</td>
                <td className="px-4 py-2 capitalize">{t.reason.replace(/_/g, " ")}</td>
                <td className={`px-4 py-2 ${t.delta >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                  {t.delta >= 0 ? "+" : ""}
                  {t.delta.toLocaleString()}
                </td>
                <td className="px-4 py-2">{t.balance_after.toLocaleString()}</td>
              </tr>
            ))}
            {transactions.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                  No transactions yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
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
