import { Link } from "react-router-dom";

export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white transition-colors duration-200 dark:border-slate-800 dark:bg-slate-950">
      <div className="mx-auto max-w-6xl px-8 py-10">
        <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
          <div className="flex items-center gap-2">
            <img src="/logo-icon.png" alt="" className="h-7 w-7" />
            <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">CreditFlow</span>
          </div>
          <nav className="flex flex-wrap items-center justify-center gap-x-6 gap-y-2 text-sm text-slate-500 dark:text-slate-400">
            <a href="#pricing" className="transition-colors hover:text-slate-900 dark:hover:text-white">
              Pricing
            </a>
            <Link to="/login" className="transition-colors hover:text-slate-900 dark:hover:text-white">
              Log in
            </Link>
            <Link to="/signup" className="transition-colors hover:text-slate-900 dark:hover:text-white">
              Sign up
            </Link>
          </nav>
        </div>
        <p className="mt-8 text-center text-xs text-slate-500 dark:text-slate-400 dark:text-slate-600">
          &copy; {new Date().getFullYear()} CreditFlow. All rights reserved.
        </p>
      </div>
    </footer>
  );
}
