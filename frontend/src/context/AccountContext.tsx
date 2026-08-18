import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { listMyAccounts, type Account } from "../api/accounts";
import { useAuth } from "./AuthContext";

interface AccountContextValue {
  accounts: Account[];
  currentAccount: Account | null;
  planTier: string | null;
  refresh: () => void;
}

const AccountContext = createContext<AccountContextValue | undefined>(undefined);

// Fetched once here and shared, rather than each consumer (AccountSwitcher,
// AppLayout's nav filtering, plan-gated routes) re-fetching /me/accounts
// independently — they all need the same data: the caller's full account
// list and, most often, just the current account's plan_tier.
export function AccountProvider({ children }: { children: ReactNode }) {
  const { claims, isAuthenticated } = useAuth();
  const [accounts, setAccounts] = useState<Account[]>([]);

  function refresh() {
    if (!isAuthenticated) return;
    listMyAccounts()
      .then(setAccounts)
      .catch(() => undefined);
  }

  useEffect(refresh, [isAuthenticated, claims?.account_id]);

  const currentAccount = accounts.find((a) => a.id === claims?.account_id) ?? null;

  const value: AccountContextValue = {
    accounts,
    currentAccount,
    planTier: currentAccount?.plan_tier ?? null,
    refresh,
  };

  return <AccountContext.Provider value={value}>{children}</AccountContext.Provider>;
}

export function useAccount(): AccountContextValue {
  const ctx = useContext(AccountContext);
  if (!ctx) throw new Error("useAccount must be used within an AccountProvider");
  return ctx;
}
