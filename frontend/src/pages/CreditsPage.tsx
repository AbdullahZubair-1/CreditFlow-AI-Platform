import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { listPlans, type Plan } from "../api/billing";
import { ApiError } from "../api/client";
import {
  createDirectPurchaseCheckout,
  getBalance,
  getCreditsPricing,
  getPlanGrants,
  listTransactions,
  type Balance,
  type LedgerEntry,
} from "../api/credits";
import AppLayout from "../components/AppLayout";

export default function CreditsPage() {
  const [params] = useSearchParams();

  const [balance, setBalance] = useState<Balance | null>(null);
  const [transactions, setTransactions] = useState<LedgerEntry[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [planGrants, setPlanGrants] = useState<Record<string, number>>({});
  const [centsPerCredit, setCentsPerCredit] = useState<number | null>(null);
  const [purchaseAmount, setPurchaseAmount] = useState("");
  const [purchasing, setPurchasing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    getBalance().then(setBalance).catch(() => undefined);
    listTransactions().then(setTransactions).catch(() => undefined);
  }

  useEffect(() => {
    refresh();
    listPlans().then(setPlans).catch(() => undefined);
    getPlanGrants().then(setPlanGrants).catch(() => undefined);
    getCreditsPricing().then((p) => setCentsPerCredit(p.cents_per_credit)).catch(() => undefined);
  }, []);

  async function handleDirectPurchase(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setPurchasing(true);
    try {
      const { checkout_url } = await createDirectPurchaseCheckout(Number(purchaseAmount));
      window.location.href = checkout_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start purchase.");
      setPurchasing(false);
    }
  }

  const purchasePriceUsd =
    centsPerCredit && Number(purchaseAmount) > 0
      ? ((Number(purchaseAmount) * centsPerCredit) / 100).toFixed(2)
      : null;

  const paidPlans = plans.filter((p) => p.tier !== "free");

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Credits</h1>

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

      <h2 className="mt-10 text-lg font-semibold">Buy credits from us</h2>
      <p className="mt-1 text-sm text-slate-400">
        Every paid plan includes a monthly credit grant. Need more than your plan gives you? Buy extra credits
        directly below.
      </p>

      <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
        {paidPlans.map((plan) => (
          <div key={plan.tier} className="rounded-lg border border-slate-800 p-5">
            <p className="text-sm font-medium capitalize text-slate-300">{plan.tier} plan</p>
            <p className="mt-2 text-2xl font-semibold">
              {(planGrants[plan.tier] ?? 0).toLocaleString()} <span className="text-sm font-normal text-slate-400">credits/mo</span>
            </p>
            <p className="mt-1 text-sm text-slate-400">${(plan.display_price_cents / 100).toFixed(2)}/mo subscription</p>
          </div>
        ))}
      </div>

      <div className="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-5">
        <p className="text-sm font-medium text-slate-300">Need more credits right now?</p>
        <p className="mt-1 text-sm text-slate-400">
          Buy extra credits any time, on top of whatever your plan already grants
          {centsPerCredit ? ` — $${(centsPerCredit / 100).toFixed(2)} per credit` : ""}.
        </p>
        <form onSubmit={handleDirectPurchase} className="mt-4 flex flex-wrap items-end gap-3">
          <div>
            <input
              type="number"
              min={1}
              required
              placeholder="Credits amount"
              value={purchaseAmount}
              onChange={(e) => setPurchaseAmount(e.target.value)}
              className="w-40 rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none"
            />
            {purchasePriceUsd && <p className="mt-1 text-xs text-slate-500">Total: ${purchasePriceUsd}</p>}
          </div>
          <button
            disabled={purchasing}
            className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400 disabled:opacity-50"
          >
            {purchasing ? "Starting checkout..." : "Buy credits"}
          </button>
        </form>
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
    </AppLayout>
  );
}
