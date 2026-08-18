import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { verifyEmail } from "../api/auth";
import AuthLayout from "../components/AuthLayout";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");
  // /verify-email is a one-shot server mutation (the token gets marked
  // used on first success), not an idempotent read — so React 18 Strict
  // Mode's deliberate double-invoke of effects in development would fire
  // it twice: the first call succeeds, the second (same, now-used token)
  // correctly gets rejected, and whichever response resolved last used to
  // win the displayed status. This ref makes the real request fire only
  // once per token no matter how many times the effect re-runs.
  const requestedTokenRef = useRef<string | null>(null);

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    if (requestedTokenRef.current === token) {
      return;
    }
    requestedTokenRef.current = token;

    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <AuthLayout title="Email verification">
      {status === "pending" && <p className="text-center text-sm text-slate-500 dark:text-slate-400">Verifying...</p>}
      {status === "success" && (
        <div className="text-center">
          <p className="text-sm text-slate-600 dark:text-slate-300">Your email has been verified.</p>
          <Link to="/login" className="mt-4 inline-block text-indigo-600 dark:text-indigo-400 hover:underline">
            Continue to log in
          </Link>
        </div>
      )}
      {status === "error" && (
        <p className="text-center text-sm text-red-600 dark:text-red-400">
          This verification link is invalid or has expired.
        </p>
      )}
    </AuthLayout>
  );
}
