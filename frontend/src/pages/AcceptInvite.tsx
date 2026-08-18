import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { acceptInvite } from "../api/accounts";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";
import { useAuth } from "../context/AuthContext";

export default function AcceptInvite() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const { isAuthenticated } = useAuth();
  const [status, setStatus] = useState<"idle" | "accepting" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleAccept() {
    setStatus("accepting");
    setError(null);
    try {
      await acceptInvite(token);
      navigate("/dashboard");
    } catch (err) {
      setStatus("error");
      setError(err instanceof ApiError ? err.message : "This invite is invalid or has expired.");
    }
  }

  if (!isAuthenticated) {
    return (
      <AuthLayout title="Accept invite">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Log in or sign up first, then come back to this link to join the team.
        </p>
        <button
          onClick={() => navigate(`/login?redirect=/accept-invite?token=${token}`)}
          className="mt-4 w-full rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400"
        >
          Log in
        </button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Accept invite">
      <p className="text-sm text-slate-500 dark:text-slate-400">You've been invited to join a CreditFlow team.</p>
      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}
      <button
        onClick={handleAccept}
        disabled={status === "accepting"}
        className="mt-4 w-full rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400 disabled:opacity-50"
      >
        {status === "accepting" ? "Joining..." : "Accept invite"}
      </button>
    </AuthLayout>
  );
}
