import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { forgotPassword, resetPassword } from "../api/auth";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";

export default function ForgotPassword() {
  const [step, setStep] = useState<"request" | "reset">("request");
  const [email, setEmail] = useState("");
  const [otp, setOtp] = useState("");
  const [devOtp, setDevOtp] = useState<string | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleRequest(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await forgotPassword(email);
      // Dev-only: the Notification Service (a later slice) will email this
      // OTP instead of returning it directly in the response.
      setDevOtp(res.dev_otp ?? null);
      setStep("reset");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  async function handleReset(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await resetPassword(email, otp, newPassword);
      navigate("/login");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  const inputClass =
    "w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500";

  if (step === "request") {
    return (
      <AuthLayout title="Forgot password">
        <form onSubmit={handleRequest} className="space-y-4">
          <input
            type="email"
            required
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
          />
          {error && <p className="text-sm text-red-400">{error}</p>}
          <button className="w-full rounded-md bg-indigo-500 px-4 py-2 font-medium hover:bg-indigo-400">
            Send code
          </button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Reset password">
      {devOtp && (
        <p className="mb-4 text-sm text-slate-400">
          A one-time code would normally be emailed to you. For now, your code is: <br />
          <span className="font-mono text-indigo-400">{devOtp}</span>
        </p>
      )}
      <form onSubmit={handleReset} className="space-y-4">
        <input
          required
          placeholder="One-time code"
          value={otp}
          onChange={(e) => setOtp(e.target.value)}
          className={inputClass}
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="New password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className={inputClass}
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button className="w-full rounded-md bg-indigo-500 px-4 py-2 font-medium hover:bg-indigo-400">
          Reset password
        </button>
      </form>
    </AuthLayout>
  );
}
