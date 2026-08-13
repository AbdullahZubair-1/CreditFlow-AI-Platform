import AccountSwitcher from "../components/AccountSwitcher";
import { useAuth } from "../context/AuthContext";

// Stub: the real Owner Dashboard (usage, credits, team size, plan tier)
// arrives once the Billing/Credits/Usage service slices exist to power it.
export default function Dashboard() {
  const { claims, logout } = useAuth();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-800 px-8 py-4">
        <span className="text-lg font-semibold">CreditFlow</span>
        <div className="flex items-center gap-4">
          <AccountSwitcher />
          <button onClick={() => logout()} className="text-sm text-slate-400 hover:text-white">
            Log out
          </button>
        </div>
      </header>
      <main className="px-8 py-12">
        <h1 className="text-2xl font-semibold">Welcome</h1>
        <p className="mt-2 text-slate-400">Signed in as user {claims?.user_id}</p>
        <p className="mt-8 text-sm text-slate-500">
          Content Studio, Calendar, Billing, and Credits pages arrive with their respective service
          slices.
        </p>
      </main>
    </div>
  );
}
