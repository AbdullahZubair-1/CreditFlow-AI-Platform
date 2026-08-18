import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { acceptInvite, createTeamAccount, listMyAccounts, type Account } from "../api/accounts";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";

export default function CreateOrJoinAccount() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [teamName, setTeamName] = useState("");
  const [inviteToken, setInviteToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    listMyAccounts().then(setAccounts).catch(() => undefined);
  }, []);

  async function handleCreateTeam(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createTeamAccount(teamName);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  async function handleAcceptInvite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await acceptInvite(inviteToken);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  const inputClass =
    "w-full rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none focus:border-brand-500";

  return (
    <AuthLayout title="Create or join an account">
      {accounts.length > 0 && (
        <div className="mb-6">
          <p className="mb-2 text-sm text-slate-500 dark:text-slate-400">You already belong to:</p>
          <ul className="space-y-1">
            {accounts.map((a) => (
              <li key={a.id} className="text-sm text-slate-600 dark:text-slate-300">
                {a.name} <span className="text-slate-500">({a.type}, {a.role})</span>
              </li>
            ))}
          </ul>
          <button
            onClick={() => navigate("/dashboard")}
            className="mt-4 w-full rounded-md bg-brand-500 px-4 py-2 font-medium hover:bg-brand-400"
          >
            Continue to dashboard
          </button>
        </div>
      )}

      <form onSubmit={handleCreateTeam} className="space-y-3">
        <p className="text-sm text-slate-500 dark:text-slate-400">Create a team account</p>
        <input
          required
          placeholder="Team name"
          value={teamName}
          onChange={(e) => setTeamName(e.target.value)}
          className={inputClass}
        />
        <button className="w-full rounded-md border border-slate-300 dark:border-slate-700 px-4 py-2 font-medium hover:bg-slate-100 dark:hover:bg-slate-800">
          Create team
        </button>
      </form>

      <div className="my-6 border-t border-slate-200 dark:border-slate-800" />

      <form onSubmit={handleAcceptInvite} className="space-y-3">
        <p className="text-sm text-slate-500 dark:text-slate-400">Accept a team invite</p>
        <input
          required
          placeholder="Invite token"
          value={inviteToken}
          onChange={(e) => setInviteToken(e.target.value)}
          className={inputClass}
        />
        <button className="w-full rounded-md border border-slate-300 dark:border-slate-700 px-4 py-2 font-medium hover:bg-slate-100 dark:hover:bg-slate-800">
          Accept invite
        </button>
      </form>

      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}
    </AuthLayout>
  );
}
