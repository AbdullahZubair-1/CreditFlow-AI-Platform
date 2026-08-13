import { useEffect, useState } from "react";

import { listMyAccounts, type Account } from "../api/accounts";
import { useAuth } from "../context/AuthContext";

export default function AccountSwitcher() {
  const { claims, switchAccount } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    listMyAccounts()
      .then(setAccounts)
      .catch(() => undefined);
  }, [claims?.account_id]);

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
      className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm outline-none disabled:opacity-50"
    >
      {accounts.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name} ({a.role})
        </option>
      ))}
    </select>
  );
}
