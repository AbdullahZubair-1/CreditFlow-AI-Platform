import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export default function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-950 text-slate-100">
      <div className="w-full max-w-sm">
        <Link to="/" className="mb-8 block text-center text-xl font-semibold">
          CreditFlow
        </Link>
        <div className="rounded-lg border border-slate-800 bg-slate-900 p-8">
          <h1 className="mb-6 text-center text-lg font-semibold">{title}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}
