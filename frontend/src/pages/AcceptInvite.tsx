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
    // Stashed here rather than carried as a URL query param through
    // login/signup: signup doesn't log the user in immediately (email
    // verification sits in between), so a query param would be lost the
    // moment they navigate away to check their inbox. localStorage
    // survives that whole trip regardless of how many pages it spans —
    // CreateOrJoinAccount.tsx (the page every successful login/signup
    // lands on) checks for this and auto-accepts before ever rendering
    // its own "create or join" choices.
    function stashAndGo(path: string) {
      localStorage.setItem("pending_invite_token", token);
      navigate(path);
    }

    return (
      <AuthLayout title="Accept invite">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Log in or sign up first — you'll join the team automatically once you do.
        </p>
        <button
          onClick={() => stashAndGo("/login")}
          className="mt-4 w-full rounded-md bg-brand-500 px-4 py-2 text-sm font-medium hover:bg-brand-400"
        >
          Log in
        </button>
        <button
          onClick={() => stashAndGo("/signup")}
          className="mt-3 w-full rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Sign up
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
        className="mt-4 w-full rounded-md bg-brand-500 px-4 py-2 text-sm font-medium hover:bg-brand-400 disabled:opacity-50"
      >
        {status === "accepting" ? "Joining..." : "Accept invite"}
      </button>
    </AuthLayout>
  );
}
