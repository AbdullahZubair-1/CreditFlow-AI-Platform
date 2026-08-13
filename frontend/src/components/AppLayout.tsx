import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import AccountSwitcher from "./AccountSwitcher";
import { useAuth } from "../context/AuthContext";

interface NavItem {
  to: string;
  label: string;
  ownerOnly?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard" },
  { to: "/dashboard/content", label: "Content Studio" },
  { to: "/dashboard/calendar", label: "Calendar" },
  { to: "/dashboard/linkedin", label: "LinkedIn" },
  { to: "/dashboard/team", label: "Team", ownerOnly: true },
  { to: "/dashboard/billing", label: "Billing", ownerOnly: true },
  { to: "/dashboard/credits", label: "Credits & Marketplace", ownerOnly: true },
];

const OWNER_ROLES = new Set(["owner", "admin"]);

export default function AppLayout({ children }: { children: ReactNode }) {
  const { claims, logout } = useAuth();
  const isOwner = claims ? OWNER_ROLES.has(claims.role) : false;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <div className="flex">
        <aside className="hidden w-56 shrink-0 border-r border-slate-800 px-4 py-6 sm:block">
          <NavLink to="/dashboard" className="mb-6 block text-lg font-semibold">
            CreditFlow
          </NavLink>
          <nav className="space-y-1">
            {NAV_ITEMS.filter((item) => !item.ownerOnly || isOwner).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/dashboard"}
                className={({ isActive }) =>
                  `block rounded-md px-3 py-2 text-sm ${
                    isActive ? "bg-indigo-500/20 text-indigo-300" : "text-slate-400 hover:bg-slate-900 hover:text-white"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
            {claims?.is_superadmin && (
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  `block rounded-md px-3 py-2 text-sm ${
                    isActive ? "bg-amber-500/20 text-amber-300" : "text-amber-400 hover:bg-slate-900"
                  }`
                }
              >
                SuperAdmin Console
              </NavLink>
            )}
          </nav>
        </aside>

        <div className="flex-1">
          <header className="flex items-center justify-between border-b border-slate-800 px-6 py-4">
            <span className="text-sm text-slate-400">Role: {claims?.role}</span>
            <div className="flex items-center gap-4">
              <AccountSwitcher />
              <button onClick={() => logout()} className="text-sm text-slate-400 hover:text-white">
                Log out
              </button>
            </div>
          </header>
          <main className="px-6 py-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
