import { useEffect, useState } from "react";

import { listMyAccounts, type Account } from "../api/accounts";

// NOTE: this displays every account the user belongs to, but switching
// selection here does not yet request a new account-scoped JWT — that
// requires Auth <-> User/Tenant coordination that arrives with the
// Billing/Credits slices, once there's real per-account data to scope to.
export default function AccountSwitcher() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selected, setSelected] = useState<string>("");

  useEffect(() => {
    listMyAccounts()
      .then((accs) => {
        setAccounts(accs);
        if (accs.length > 0) setSelected(accs[0].id);
      })
      .catch(() => undefined);
  }, []);

  if (accounts.length === 0) return null;

  return (
    <select
      value={selected}
      onChange={(e) => setSelected(e.target.value)}
      className="rounded-md border border-slate-700 bg-slate-800 px-3 py-1.5 text-sm outline-none"
    >
      {accounts.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name} ({a.role})
        </option>
      ))}
    </select>
  );
}
