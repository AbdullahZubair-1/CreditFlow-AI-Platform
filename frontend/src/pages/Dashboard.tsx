import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listMembers } from "../api/accounts";
import { getSubscription, type Subscription } from "../api/billing";
import { ApiError } from "../api/client";
import { getBalance, type Balance } from "../api/credits";
import { getUsageSummary, type UsageSummary } from "../api/usage";
import AppLayout from "../components/AppLayout";
import StatCard from "../components/StatCard";
import { useAuth } from "../context/AuthContext";

const OWNER_ROLES = new Set(["owner", "admin"]);

export default function Dashboard() {
  const { claims } = useAuth();
  const isOwner = claims ? OWNER_ROLES.has(claims.role) : false;

  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [balance, setBalance] = useState<Balance | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [memberCount, setMemberCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOwner || !claims) return;

    Promise.all([
      getSubscription().catch(() => null),
      getBalance().catch(() => null),
      getUsageSummary().catch(() => null),
      listMembers(claims.account_id).catch(() => null),
    ])
      .then(([sub, bal, use, members]) => {
        setSubscription(sub);
        setBalance(bal);
        setUsage(use);
        setMemberCount(members?.length ?? null);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load dashboard data."));
  }, [isOwner, claims?.account_id]);

  if (!isOwner) {
    return (
      <AppLayout>
        <h1 className="text-2xl font-semibold">Welcome</h1>
        <p className="mt-2 text-slate-400">
          Head to the{" "}
          <Link to="/dashboard/content" className="text-indigo-400 hover:underline">
            Content Studio
          </Link>{" "}
          to generate a post, or check the{" "}
          <Link to="/dashboard/calendar" className="text-indigo-400 hover:underline">
            calendar
          </Link>{" "}
          for what's scheduled.
        </p>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Owner Dashboard</h1>
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label="Plan tier" value={subscription?.plan_tier ?? "—"} hint={subscription?.status} />
        <StatCard label="Credit balance" value={balance ? balance.balance.toLocaleString() : "—"} />
        <StatCard label="Team size" value={memberCount !== null ? String(memberCount) : "—"} />
        <StatCard
          label="Usage this period"
          value={usage ? `${usage.used_tokens.toLocaleString()} / ${usage.quota_tokens.toLocaleString()}` : "—"}
          hint="tokens"
        />
      </div>

      {usage && usage.by_model.length > 0 && (
        <div className="mt-8">
          <h2 className="text-lg font-semibold">Usage by model</h2>
          <div className="mt-3 overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-left text-slate-400">
                <tr>
                  <th className="px-4 py-2">Model</th>
                  <th className="px-4 py-2">Tokens</th>
                  <th className="px-4 py-2">Cost</th>
                  <th className="px-4 py-2">Calls</th>
                </tr>
              </thead>
              <tbody>
                {usage.by_model.map((m) => (
                  <tr key={m.model} className="border-t border-slate-800">
                    <td className="px-4 py-2">{m.model}</td>
                    <td className="px-4 py-2">{m.total_tokens.toLocaleString()}</td>
                    <td className="px-4 py-2">${(m.cost_cents / 100).toFixed(2)}</td>
                    <td className="px-4 py-2">{m.call_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
