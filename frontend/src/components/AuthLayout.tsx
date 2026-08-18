import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import ThemeToggle from "./ThemeToggle";

export default function AuthLayout({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 text-slate-900 transition-colors duration-200 dark:bg-slate-950 dark:text-slate-100">
      <div className="absolute right-6 top-6">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm animate-slide-up">
        <Link to="/" className="mb-8 flex items-center justify-center gap-2 text-xl font-semibold">
          <img src="/logo-icon.png" alt="" className="h-8 w-8" />
          CreditFlow
        </Link>
        <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm transition-colors duration-200 dark:border-slate-800 dark:bg-slate-900">
          <h1 className="mb-6 text-center text-lg font-semibold">{title}</h1>
          {children}
        </div>
      </div>
    </div>
  );
}
