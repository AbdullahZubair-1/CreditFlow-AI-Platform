import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { verifyEmail } from "../api/auth";
import AuthLayout from "../components/AuthLayout";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token");
  const [status, setStatus] = useState<"pending" | "success" | "error">("pending");

  useEffect(() => {
    if (!token) {
      setStatus("error");
      return;
    }
    verifyEmail(token)
      .then(() => setStatus("success"))
      .catch(() => setStatus("error"));
  }, [token]);

  return (
    <AuthLayout title="Email verification">
      {status === "pending" && <p className="text-center text-sm text-slate-400">Verifying...</p>}
      {status === "success" && (
        <div className="text-center">
          <p className="text-sm text-slate-300">Your email has been verified.</p>
          <Link to="/login" className="mt-4 inline-block text-indigo-400 hover:underline">
            Continue to log in
          </Link>
        </div>
      )}
      {status === "error" && (
        <p className="text-center text-sm text-red-400">
          This verification link is invalid or has expired.
        </p>
      )}
    </AuthLayout>
  );
}
