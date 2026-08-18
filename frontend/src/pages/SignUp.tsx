import { useState } from "react";
import { Link } from "react-router-dom";

import { signup } from "../api/auth";
import { ApiError } from "../api/client";
import AuthLayout from "../components/AuthLayout";

export default function SignUp() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await signup(email, password);
      setSubmitted(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    }
  }

  if (submitted) {
    return (
      <AuthLayout title="Check your email">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          We sent a verification link to <span className="font-medium">{email}</span>. Click it to activate your
          account, then log in.
        </p>
        <Link
          to="/login"
          className="mt-4 block w-full rounded-md bg-indigo-500 px-4 py-2 text-center font-medium hover:bg-indigo-400"
        >
          Go to login
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
          className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <input
          type="password"
          required
          minLength={8}
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
        <button className="w-full rounded-md bg-indigo-500 px-4 py-2 font-medium hover:bg-indigo-400">
          Sign up
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-slate-500 dark:text-slate-400">
        Already have an account?{" "}
        <Link to="/login" className="text-indigo-600 dark:text-indigo-400 hover:underline">
          Log in
        </Link>
      </p>
    </AuthLayout>
  );
}
