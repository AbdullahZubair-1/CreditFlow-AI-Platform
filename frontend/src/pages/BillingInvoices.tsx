import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  createCheckoutSession,
  createRefund,
  listInvoices,
  listPlans,
  getSubscription,
  updateSubscription,
  type Invoice,
  type Plan,
  type Subscription,
} from "../api/billing";
import { ApiError } from "../api/client";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";

export default function BillingInvoices() {
  const [params] = useSearchParams();
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyPlan, setBusyPlan] = useState<string | null>(null);
  const [refundTarget, setRefundTarget] = useState<Invoice | null>(null);
  const [refundedIds, setRefundedIds] = useState<Set<string>>(new Set());
  const [refunding, setRefunding] = useState(false);

  function refresh() {
    getSubscription().then(setSubscription).catch(() => undefined);
    listInvoices().then(setInvoices).catch(() => undefined);
  }

  useEffect(() => {
    listPlans().then(setPlans).catch(() => undefined);
    refresh();
  }, []);

  async function handleSelectPlan(tier: string) {
    if (tier === "free") return;
    setError(null);
    setBusyPlan(tier);
    try {
      if (subscription && subscription.plan_tier !== "free") {
        await updateSubscription(tier);
        refresh();
      } else {
        const { checkout_url } = await createCheckoutSession(tier);
        window.location.href = checkout_url;
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update plan.");
    } finally {
      setBusyPlan(null);
    }
  }

  async function confirmRefund() {
    if (!refundTarget) return;
    setRefunding(true);
    setError(null);
    try {
      await createRefund(refundTarget.id);
      setRefundedIds((prev) => new Set(prev).add(refundTarget.id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to issue refund.");
    } finally {
      setRefunding(false);
      setRefundTarget(null);
    }
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Billing &amp; Invoices</h1>

      {params.get("checkout") === "success" && (
        <p className="mt-4 rounded-md bg-emerald-500/10 px-4 py-2 text-sm text-emerald-600 dark:text-emerald-400">
          Checkout complete — your plan will update once Stripe confirms the payment.
        </p>
      )}
      {params.get("checkout") === "cancelled" && (
        <p className="mt-4 rounded-md bg-slate-100 dark:bg-slate-800 px-4 py-2 text-sm text-slate-500 dark:text-slate-400">Checkout was cancelled.</p>
      )}
      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        {plans.map((plan) => {
          const isCurrent = subscription?.plan_tier === plan.tier;
          return (
            <div
              key={plan.tier}
              className={`rounded-lg border p-5 ${
                isCurrent ? "border-indigo-500 bg-indigo-500/10" : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900"
              }`}
            >
              <h3 className="text-lg font-semibold capitalize">{plan.tier}</h3>
              <p className="mt-1 text-2xl font-semibold">
                ${(plan.display_price_cents / 100).toFixed(0)}
                <span className="text-sm text-slate-500 dark:text-slate-400">/mo</span>
              </p>
              <button
                disabled={isCurrent || busyPlan === plan.tier || plan.tier === "free"}
                onClick={() => handleSelectPlan(plan.tier)}
                className="mt-4 w-full rounded-md border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm font-medium hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
              >
                {isCurrent ? "Current plan" : busyPlan === plan.tier ? "Updating..." : "Choose plan"}
              </button>
            </div>
          );
        })}
      </div>

      {subscription?.grace_period_ends_at && (
        <p className="mt-4 rounded-md bg-amber-500/10 px-4 py-2 text-sm text-amber-600 dark:text-amber-400">
          A recent payment failed — please update your payment method before{" "}
          {new Date(subscription.grace_period_ends_at).toLocaleDateString()} to avoid a downgrade.
        </p>
      )}

      <h2 className="mt-10 text-lg font-semibold">Invoice history</h2>
      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-white dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2">Amount</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {invoices.map((inv) => {
              const refunded = refundedIds.has(inv.id);
              return (
                <tr key={inv.id} className="border-t border-slate-200 dark:border-slate-800">
                  <td className="px-4 py-2">{new Date(inv.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-2">
                    {(inv.amount_cents / 100).toFixed(2)} {inv.currency.toUpperCase()}
                  </td>
                  <td className="px-4 py-2 capitalize">{inv.status}</td>
                  <td className="px-4 py-2 text-right">
                    {refunded ? (
                      <span className="text-xs text-emerald-600 dark:text-emerald-400">Refund issued</span>
                    ) : (
                      inv.status === "paid" && (
                        <button
                          onClick={() => setRefundTarget(inv)}
                          className="text-xs text-red-600 dark:text-red-400 hover:underline"
                        >
                          Request refund
                        </button>
                      )
                    )}
                  </td>
                </tr>
              );
            })}
            {invoices.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                  No invoices yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={refundTarget !== null}
        title="Request refund"
        message={
          refundTarget
            ? `Refund ${(refundTarget.amount_cents / 100).toFixed(2)} ${refundTarget.currency.toUpperCase()} for this invoice via Stripe? This can't be undone.`
            : ""
        }
        confirmLabel={refunding ? "Refunding..." : "Refund invoice"}
        onConfirm={confirmRefund}
        onCancel={() => setRefundTarget(null)}
      />
    </AppLayout>
  );
}
