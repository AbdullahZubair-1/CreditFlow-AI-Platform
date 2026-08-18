import { useEffect, useState } from "react";

import { listAllUsers, type UserDirectoryEntry } from "../api/admin";
import { ApiError } from "../api/client";
import AppLayout from "../components/AppLayout";
import StatCard from "../components/StatCard";

export default function SuperAdminUsers() {
  const [users, setUsers] = useState<UserDirectoryEntry[]>([]);
  const [totalRevenueCents, setTotalRevenueCents] = useState(0);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listAllUsers()
      .then((data) => {
        setUsers(data.users);
        setTotalRevenueCents(data.total_revenue_cents);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load users."));
  }, []);

  const filtered = users.filter((u) => u.email.toLowerCase().includes(search.toLowerCase()));
  const verifiedCount = users.filter((u) => u.email_verified).length;

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Users</h1>
      <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
        Every user on the platform, independent of accounts or plans.
      </p>
      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total platform revenue" value={`$${(totalRevenueCents / 100).toFixed(2)}`} />
        <StatCard label="Total users" value={users.length.toString()} />
        <StatCard label="Verified users" value={`${verifiedCount} / ${users.length}`} />
      </div>

      <input
        placeholder="Search by email..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        className="mt-6 w-full max-w-sm rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
      />

      <div className="mt-4 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-3 py-2">Email</th>
              <th className="px-3 py-2">Verified</th>
              <th className="px-3 py-2">Signed up</th>
              <th className="px-3 py-2">Role</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => (
              <tr key={u.user_id} className="border-t border-slate-200 dark:border-slate-800">
                <td className="px-3 py-2">{u.email}</td>
                <td className="px-3 py-2">
                  {u.email_verified ? (
                    <span className="text-emerald-600 dark:text-emerald-400">Yes</span>
                  ) : (
                    <span className="text-amber-600 dark:text-amber-400">No</span>
                  )}
                </td>
                <td className="px-3 py-2 text-xs text-slate-500 dark:text-slate-400">
                  {new Date(u.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2">
                  {u.is_platform_admin ? (
                    <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-xs text-amber-600 dark:text-amber-400">
                      SuperAdmin
                    </span>
                  ) : (
                    <span className="text-xs text-slate-500">Member</span>
                  )}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={4} className="px-3 py-6 text-center text-slate-500">
                  No users found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </AppLayout>
  );
}
