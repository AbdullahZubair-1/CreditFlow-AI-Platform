import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { acceptInvite, createTeamAccount, listMyAccounts, type Account } from "../api/accounts";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";
import { PLANS } from "../data/plans";

const FREE_PLAN = PLANS[0];

export default function CreateOrJoinAccount() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [teamName, setTeamName] = useState("");
  const [inviteToken, setInviteToken] = useState("");
  const [error, setError] = useState<string | null>(null);
  // Every successful login/signup lands here — if the user actually came
  // from an invite link (see AcceptInvite.tsx's stashAndGo), this page
  // should never even flash the normal "create or join" choices in front
  // of them; it should just finish the join and move on.
  const [resumingInvite, setResumingInvite] = useState(() => localStorage.getItem("pending_invite_token") !== null);
  const navigate = useNavigate();

  useEffect(() => {
    const pendingToken = localStorage.getItem("pending_invite_token");
    if (!pendingToken) return;

    acceptInvite(pendingToken)
      .then(() => {
        localStorage.removeItem("pending_invite_token");
        navigate("/dashboard");
      })
      .catch((err) => {
        localStorage.removeItem("pending_invite_token");
        setError(err instanceof ApiError ? err.message : "This invite is invalid or has expired.");
        setResumingInvite(false);
      });
  }, [navigate]);

  useEffect(() => {
    if (resumingInvite) return;
    listMyAccounts().then(setAccounts).catch(() => undefined);
  }, [resumingInvite]);

  if (resumingInvite) {
    return (
      <AuthLayout title="Joining team...">
        <p className="text-center text-sm text-slate-500 dark:text-slate-400">
          You followed a team invite link — joining automatically, one moment.
        </p>
      </AuthLayout>
    );
  }

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

      <div className="mb-6 rounded-lg border border-slate-200 bg-slate-50 p-4 dark:border-slate-800 dark:bg-slate-900/60">
        <p className="text-sm font-medium">New accounts start on the {FREE_PLAN.name} plan — {FREE_PLAN.credits}</p>
        <ul className="mt-2 space-y-1 text-sm text-slate-600 dark:text-slate-400">
          {FREE_PLAN.features.map((f) => (
            <li key={f} className="flex items-start gap-2">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="mt-0.5 h-4 w-4 shrink-0 text-brand-500">
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
              {f}
            </li>
          ))}
        </ul>
        <a href="/#pricing" className="mt-3 inline-block text-xs font-medium text-brand-600 hover:underline dark:text-brand-400">
          See Pro/Team plans for scheduling, LinkedIn publishing, and the marketplace →
        </a>
      </div>

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
