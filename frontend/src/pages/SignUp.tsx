import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { signup } from "../api/auth";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";

export default function SignUp() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [devToken, setDevToken] = useState<string | null>(null);
  const navigate = useNavigate();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await signup(email, password);
      // Dev-only: the Notification Service (a later slice) will email this
      // link instead of returning it directly in the response.
      if (res.dev_verification_token) {
        setDevToken(res.dev_verification_token);
      } else {
        navigate("/login");
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  if (devToken) {
    return (
      <AuthLayout title="Verify your email">
        <p className="text-sm text-slate-400">
          A verification link would normally be emailed to you. For now, click below to verify:
        </p>
        <Link
          to={`/verify-email?token=${devToken}`}
          className="mt-4 block w-full rounded-md bg-indigo-500 px-4 py-2 text-center font-medium hover:bg-indigo-400"
        >
          Verify email
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Create your account">
      <form onSubmit={handleSubmit} className="space-y-4">
        <input
          type="email"
          required
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        {error && <p className="text-sm text-red-400">{error}</p>}
        <button className="w-full rounded-md bg-indigo-500 px-4 py-2 font-medium hover:bg-indigo-400">
          Sign up
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-400">
        Already have an account?{" "}
        <Link to="/login" className="text-indigo-400 hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}
