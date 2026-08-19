import { useEffect, useState } from "react";

import {
  getWalletBalance,
  listMyPayoutRequests,
  listWalletTransactions,
  requestPayout,
  type PayoutRequest,
  type WalletBalance,
  type WalletLedgerEntry,
} from "../api/credits";
import { ApiError } from "../api/client";
import { useAuth } from "../context/AuthContext";

const OWNER_TIER_ROLES = new Set(["owner", "admin"]);

// Shown on the Dashboard (reachable by every member regardless of plan
// tier or role) rather than the Marketplace page it used to live on —
// a wallet credit can land on an account that no longer has a paid plan
// at all (a plan-downgrade or invoice refund both credit the wallet and
// downgrade the plan in the same action), and the Marketplace page
// requires one, so that account could earn/receive money and then have
// no way to ever see or withdraw it.
export default function WalletSection() {
  const { claims } = useAuth();
  const canRequestPayout = claims ? OWNER_TIER_ROLES.has(claims.role) : false;

  const [wallet, setWallet] = useState<WalletBalance | null>(null);
  const [walletTransactions, setWalletTransactions] = useState<WalletLedgerEntry[]>([]);
  const [payoutRequests, setPayoutRequests] = useState<PayoutRequest[]>([]);
  const [payoutAmountUsd, setPayoutAmountUsd] = useState("");
  const [payoutDestination, setPayoutDestination] = useState("");
  const [payoutError, setPayoutError] = useState<string | null>(null);
  const [requestingPayout, setRequestingPayout] = useState(false);

  function refresh() {
    getWalletBalance().then(setWallet).catch(() => undefined);
    listWalletTransactions().then(setWalletTransactions).catch(() => undefined);
    listMyPayoutRequests().then(setPayoutRequests).catch(() => undefined);
  }

  useEffect(refresh, []);

  async function handleRequestPayout(e: React.FormEvent) {
    e.preventDefault();
    setPayoutError(null);
    setRequestingPayout(true);
    try {
      await requestPayout(Math.round(Number(payoutAmountUsd) * 100), payoutDestination);
      setPayoutAmountUsd("");
      setPayoutDestination("");
      refresh();
    } catch (err) {
      setPayoutError(err instanceof ApiError ? err.message : "Failed to request payout.");
    } finally {
      setRequestingPayout(false);
    }
  }

  return (
    <div className="mt-8">
      <h2 className="text-lg font-semibold">Your wallet</h2>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Real money from selling credits on the marketplace, plan downgrades, and invoice refunds lands here — request
        a payout any time to send it wherever you want.
      </p>
      <div className="mt-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
        <p className="text-sm text-slate-500 dark:text-slate-400">Wallet balance</p>
        <p className="mt-1 text-2xl font-semibold">{wallet ? `$${(wallet.balance_cents / 100).toFixed(2)}` : "—"}</p>
      </div>

      {canRequestPayout ? (
        <form onSubmit={handleRequestPayout} className="mt-4 flex flex-wrap items-end gap-3">
          <div>
            <input
              type="number"
              min={0.01}
              step="0.01"
              max={wallet ? wallet.balance_cents / 100 : undefined}
              required
              placeholder="Amount (USD)"
              value={payoutAmountUsd}
              onChange={(e) => setPayoutAmountUsd(e.target.value)}
              className="w-40 rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
            />
          </div>
          <input
            type="text"
            required
            placeholder="PayPal email or bank details"
            value={payoutDestination}
            onChange={(e) => setPayoutDestination(e.target.value)}
            className="w-64 rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
          />
          <button
            disabled={requestingPayout}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium hover:bg-brand-400 disabled:opacity-50"
          >
            {requestingPayout ? "Requesting..." : "Request payout"}
          </button>
        </form>
      ) : (
        <p className="mt-3 text-xs text-slate-500 dark:text-slate-400">Only an owner/admin can request a payout.</p>
      )}
      {payoutError && <p className="mt-2 text-sm text-red-600 dark:text-red-400">{payoutError}</p>}

      {payoutRequests.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-white dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
              <tr>
                <th className="px-4 py-2">Requested</th>
                <th className="px-4 py-2">Amount</th>
                <th className="px-4 py-2">Destination</th>
                <th className="px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {payoutRequests.map((p) => (
                <tr key={p.id} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="px-4 py-2">{new Date(p.requested_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2">${(p.amount_cents / 100).toFixed(2)}</td>
                  <td className="px-4 py-2">{p.destination}</td>
                  <td className="px-4 py-2 capitalize">{p.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {walletTransactions.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
          <table className="w-full text-sm">
            <thead className="bg-white dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
              <tr>
                <th className="px-4 py-2">Date</th>
                <th className="px-4 py-2">Reason</th>
                <th className="px-4 py-2">Change</th>
                <th className="px-4 py-2">Balance after</th>
              </tr>
            </thead>
            <tbody>
              {walletTransactions.map((t) => (
                <tr key={t.id} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="px-4 py-2">{new Date(t.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2 capitalize">{t.reason.replace(/_/g, " ")}</td>
                  <td className={`px-4 py-2 ${t.delta_cents >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"}`}>
                    {t.delta_cents >= 0 ? "+" : ""}
                    {(t.delta_cents / 100).toFixed(2)}
                  </td>
                  <td className="px-4 py-2">${(t.balance_after_cents / 100).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
