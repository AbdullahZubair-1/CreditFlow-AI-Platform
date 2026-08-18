import { useState } from "react";

import { useAccount } from "../context/AccountContext";
import { useAuth } from "../context/AuthContext";

export default function AccountSwitcher() {
  const { claims, switchAccount } = useAuth();
  const { accounts } = useAccount();
  const [switching, setSwitching] = useState(false);

  if (accounts.length === 0) return null;

  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const accountId = e.target.value;
    if (accountId === claims?.account_id) return;
    setSwitching(true);
    try {
      await switchAccount(accountId);
    } catch {
      // stay on the current account if the switch fails
    } finally {
      setSwitching(false);
    }
  }

  return (
    <select
      value={claims?.account_id ?? ""}
      onChange={handleChange}
      disabled={switching}
      className="rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-1.5 text-sm outline-none disabled:opacity-50"
    >
      {accounts.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name} ({a.role})
        </option>
      ))}
    </select>
  );
}
