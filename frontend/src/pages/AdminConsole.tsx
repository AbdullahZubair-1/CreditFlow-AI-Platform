import { useEffect, useState } from "react";

import {
  completePayoutRequest,
  getAccountAuditLog,
  getAccountOverview,
  getPlatformAuditLog,
  listAccountSessions,
  listAllAccounts,
  listPayoutRequests,
  revokeSession,
  type AccountDirectoryEntry,
  type AccountOverview,
  type AdminSession,
  type AuditLogEntry,
  type PayoutRequest,
} from "../api/admin";
import { ApiError } from "../api/client";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";
import StatCard from "../components/StatCard";

export default function AdminConsole() {
  const [accounts, setAccounts] = useState<AccountDirectoryEntry[]>([]);
  const [search, setSearch] = useState("");
  const [selectedAccountId, setSelectedAccountId] = useState<string | null>(null);
  const [overview, setOverview] = useState<AccountOverview | null>(null);
  const [sessions, setSessions] = useState<AdminSession[]>([]);
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([]);
  const [payoutRequests, setPayoutRequests] = useState<PayoutRequest[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<string | null>(null);
  const [completePayoutTarget, setCompletePayoutTarget] = useState<string | null>(null);

  function refreshPayoutRequests() {
    listPayoutRequests().then(setPayoutRequests).catch(() => undefined);
  }

  useEffect(() => {
    listAllAccounts()
      .then(setAccounts)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load accounts."));
    getPlatformAuditLog().then(setAuditLog).catch(() => undefined);
    refreshPayoutRequests();
  }, []);

  useEffect(() => {
    if (!selectedAccountId) return;
    getAccountOverview(selectedAccountId).then(setOverview).catch(() => setOverview(null));
    listAccountSessions(selectedAccountId).then(setSessions).catch(() => setSessions([]));
    getAccountAuditLog(selectedAccountId).then(setAuditLog).catch(() => undefined);
  }, [selectedAccountId]);

  const filteredAccounts = accounts.filter((a) => a.name.toLowerCase().includes(search.toLowerCase()));
  const totalRevenueCents = accounts.reduce((sum, a) => sum + a.total_revenue_cents, 0);

  async function confirmRevoke() {
    if (!revokeTarget) return;
    try {
      await revokeSession(revokeTarget);
      if (selectedAccountId) setSessions(await listAccountSessions(selectedAccountId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to revoke session.");
    } finally {
      setRevokeTarget(null);
    }
  }

  async function confirmCompletePayout() {
    if (!completePayoutTarget) return;
    try {
      await completePayoutRequest(completePayoutTarget);
      refreshPayoutRequests();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to mark payout completed.");
    } finally {
      setCompletePayoutTarget(null);
    }
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">
        SuperAdmin Console
      </h1>
      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total platform revenue" value={`$${(totalRevenueCents / 100).toFixed(2)}`} />
        <StatCard label="Accounts" value={accounts.length.toString()} />
        <StatCard
          label="Paying accounts"
          value={accounts.filter((a) => a.total_revenue_cents > 0).length.toString()}
        />
      </div>

      <h2 className="mt-8 text-lg font-semibold">Pending wallet payout requests</h2>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Sellers' marketplace earnings, waiting to be sent by hand — mark one completed once you've actually paid it
        out.
      </p>
      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-white dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">Requested</th>
              <th className="px-4 py-2">Account</th>
              <th className="px-4 py-2">Amount</th>
              <th className="px-4 py-2">Destination</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {payoutRequests.map((p) => (
              <tr key={p.id} className="border-t border-slate-200 dark:border-slate-800">
                <td className="px-4 py-2">{new Date(p.requested_at).toLocaleDateString()}</td>
                <td className="px-4 py-2 font-mono text-xs">{p.account_id}</td>
                <td className="px-4 py-2">${(p.amount_cents / 100).toFixed(2)}</td>
                <td className="px-4 py-2">{p.destination}</td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => setCompletePayoutTarget(p.id)}
                    className="text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Mark completed
                  </button>
                </td>
              </tr>
            ))}
            {payoutRequests.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-500">
                  No pending payout requests.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-1">
          <h2 className="text-lg font-semibold">Cross-account directory</h2>
          <input
            placeholder="Search accounts..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="mt-2 w-full rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
          />
          <div className="mt-3 max-h-96 space-y-1 overflow-y-auto">
            {filteredAccounts.map((a) => (
              <button
                key={a.account_id}
                onClick={() => setSelectedAccountId(a.account_id)}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm ${
                  selectedAccountId === a.account_id
                    ? "bg-brand-500/20 text-brand-300"
                    : "text-slate-600 dark:text-slate-300 hover:bg-white dark:hover:bg-slate-900"
                }`}
              >
                <span className="font-medium">{a.name}</span>
                <span className="ml-2 text-xs text-slate-500">
                  {a.type} · {a.plan_tier}
                </span>
                {a.total_revenue_cents > 0 && (
                  <span className="ml-2 text-xs text-emerald-600 dark:text-emerald-400">
                    ${(a.total_revenue_cents / 100).toFixed(2)}
                  </span>
                )}
              </button>
            ))}
            {filteredAccounts.length === 0 && <p className="text-sm text-slate-500">No accounts found.</p>}
          </div>
        </div>

        <div className="lg:col-span-2">
          {!selectedAccountId ? (
            <p className="text-slate-500">Select an account to view its overview, sessions, and audit log.</p>
          ) : (
            <>
              <h2 className="text-lg font-semibold">Account overview</h2>
              <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard label="Plan" value={overview?.plan_tier ?? "—"} />
                <StatCard label="Members" value={overview?.member_count?.toString() ?? "—"} />
                <StatCard label="Credit balance" value={overview?.credit_balance?.toLocaleString() ?? "—"} />
                <StatCard
                  label="Usage"
                  value={
                    overview?.usage_this_period_tokens != null && overview?.usage_quota_tokens != null
                      ? `${overview.usage_this_period_tokens.toLocaleString()} / ${overview.usage_quota_tokens.toLocaleString()}`
                      : "—"
                  }
                />
                <StatCard
                  label="Revenue"
                  value={overview ? `$${(overview.total_revenue_cents / 100).toFixed(2)}` : "—"}
                />
              </div>

              <h2 className="mt-8 text-lg font-semibold">Owner profile</h2>
              <div className="mt-3 rounded-lg border border-slate-200 dark:border-slate-800 p-4 text-sm">
                {overview?.owner_email ? (
                  <div className="space-y-1">
                    <p>
                      <span className="text-slate-500 dark:text-slate-400">Email: </span>
                      {overview.owner_email}
                    </p>
                    <p>
                      <span className="text-slate-500 dark:text-slate-400">Verified: </span>
                      {overview.owner_email_verified ? (
                        <span className="text-emerald-600 dark:text-emerald-400">Yes</span>
                      ) : (
                        <span className="text-amber-600 dark:text-amber-400">No</span>
                      )}
                    </p>
                    <p>
                      <span className="text-slate-500 dark:text-slate-400">Signed up: </span>
                      {overview.owner_created_at ? new Date(overview.owner_created_at).toLocaleString() : "—"}
                    </p>
                  </div>
                ) : (
                  <p className="text-slate-500">Owner profile unavailable.</p>
                )}
              </div>

              <h2 className="mt-8 text-lg font-semibold">Active sessions</h2>
              <div className="mt-3 space-y-2">
                {sessions.map((s) => (
                  <div key={s.jti} className="flex items-center justify-between rounded-md border border-slate-200 dark:border-slate-800 p-3">
                    <div>
                      <p className="font-mono text-xs">{s.jti}</p>
                      <p className="text-xs text-slate-500">
                        user {s.user_id} · expires in {Math.round(s.expires_in_seconds / 60)}m
                      </p>
                    </div>
                    <button onClick={() => setRevokeTarget(s.jti)} className="text-xs text-red-600 dark:text-red-400 hover:underline">
                      Revoke
                    </button>
                  </div>
                ))}
                {sessions.length === 0 && <p className="text-sm text-slate-500">No active sessions.</p>}
              </div>
            </>
          )}

          <h2 className="mt-8 text-lg font-semibold">
            {selectedAccountId ? "Account audit log" : "Platform-wide audit log"}
          </h2>
          <div className="mt-3 max-h-96 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-white dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
                <tr>
                  <th className="px-3 py-2">Time</th>
                  <th className="px-3 py-2">Event</th>
                  <th className="px-3 py-2">Exchange</th>
                </tr>
              </thead>
              <tbody>
                {auditLog.map((entry) => (
                  <tr key={entry.id} className="border-t border-slate-200 dark:border-slate-800">
                    <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                      {new Date(entry.occurred_at).toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-xs">{entry.event_type}</td>
                    <td className="px-3 py-2 text-xs text-slate-500">{entry.source_exchange}</td>
                  </tr>
                ))}
                {auditLog.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-6 text-center text-slate-500">
                      No events yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={revokeTarget !== null}
        title="Revoke session"
        message="This will immediately invalidate the access token — the user will be signed out on their next request."
        confirmLabel="Revoke session"
        onConfirm={confirmRevoke}
        onCancel={() => setRevokeTarget(null)}
      />

      <ConfirmDialog
        open={completePayoutTarget !== null}
        title="Mark payout completed"
        message="Only confirm this after you've actually sent the money to the requester's destination — this cannot be undone."
        confirmLabel="Mark completed"
        onConfirm={confirmCompletePayout}
        onCancel={() => setCompletePayoutTarget(null)}
      />
    </AppLayout>
  );
}
