import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

import AccountSwitcher from "./AccountSwitcher";
import ThemeToggle from "./ThemeToggle";
import { useAccount } from "../context/AccountContext";
import { useAuth } from "../context/AuthContext";

interface NavItem {
  to: string;
  label: string;
  icon: string;
  ownerOnly?: boolean;
  requiresPaidPlan?: boolean;
  requiresTeamPlan?: boolean;
}

// Simple, consistent 24x24 stroke icon paths (Heroicons-style) — kept as
// raw path data rather than pulling in an icon library dependency.
const ICON_PATHS: Record<string, string> = {
  dashboard: "M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6",
  content: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  calendar: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
  linkedin: "M13 10V3L4 14h7v7l9-11h-7z",
  team: "M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-2.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4",
  billing: "M3 10h18M7 15h1m4 0h1m-7 4h12a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z",
  credits: "M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V6m0 10v2m9-8a9 9 0 11-18 0 9 9 0 0118 0z",
  marketplace: "M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z",
  profile: "M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z",
};

function NavIcon({ name }: { name: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      className="h-5 w-5 shrink-0"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d={ICON_PATHS[name]} />
    </svg>
  );
}

const NAV_ITEMS: NavItem[] = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/dashboard/content", label: "Content Studio", icon: "content" },
  { to: "/dashboard/calendar", label: "Calendar", icon: "calendar", requiresPaidPlan: true },
  { to: "/dashboard/linkedin", label: "LinkedIn", icon: "linkedin", requiresPaidPlan: true },
  { to: "/dashboard/team", label: "Team", icon: "team", ownerOnly: true, requiresTeamPlan: true },
  // Not ownerOnly: members can view billing/credits/marketplace (balance,
  // invoices, listings) — they just can't buy/sell credits or change the
  // plan, which is gated inside each page and enforced server-side.
  { to: "/dashboard/billing", label: "Billing", icon: "billing" },
  { to: "/dashboard/credits", label: "Credits", icon: "credits" },
  { to: "/dashboard/marketplace", label: "Marketplace", icon: "marketplace", requiresPaidPlan: true },
];

const OWNER_ROLES = new Set(["owner", "admin"]);
const PAID_TIERS = new Set(["pro", "team"]);

const PLAN_LABELS: Record<string, string> = { free: "Free", pro: "Pro", team: "Team" };

export default function AppLayout({ children }: { children: ReactNode }) {
  const { claims, logout } = useAuth();
  const { planTier, currentAccount } = useAccount();
  const isSuperAdmin = claims?.is_superadmin ?? false;
  const isOwner = claims ? OWNER_ROLES.has(claims.role) : false;
  const hasPaidPlan = planTier !== null && PAID_TIERS.has(planTier);
  // Team Management needs a genuine team-type account, not just the Team
  // plan_tier — see PlanGateRoute.tsx's comment for why those are
  // separate axes and why conflating them let an "individual" account
  // gain a second member.
  const hasTeamPlan = planTier === "team" && currentAccount?.type === "team";
  const planLabel = planTier ? PLAN_LABELS[planTier] ?? planTier : null;

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 transition-colors duration-200 dark:bg-slate-950 dark:text-slate-100">
      <div className="flex">
        <aside className="hidden w-60 shrink-0 border-r border-slate-200 px-4 py-6 transition-colors duration-200 dark:border-slate-800 sm:block">
          <NavLink to={isSuperAdmin ? "/admin" : "/dashboard"} className="mb-6 flex items-center gap-2 px-2 text-lg font-semibold">
            <img src="/logo-icon.png" alt="" className="h-8 w-8" />
            CreditFlow
          </NavLink>
          <nav className="space-y-1">
            {!isSuperAdmin &&
              NAV_ITEMS.filter(
                (item) =>
                  (!item.ownerOnly || isOwner) &&
                  (!item.requiresPaidPlan || hasPaidPlan) &&
                  (!item.requiresTeamPlan || hasTeamPlan)
              ).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.to === "/dashboard"}
                  className={({ isActive }) =>
                    `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                      isActive
                        ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300"
                        : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-900 dark:hover:text-white"
                    }`
                  }
                >
                  <NavIcon name={item.icon} />
                  {item.label}
                </NavLink>
              ))}
            {claims?.is_superadmin && (
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                    isActive
                      ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
                      : "text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-slate-900"
                  }`
                }
              >
                <NavIcon name="team" />
                SuperAdmin Console
              </NavLink>
            )}
            {claims?.is_superadmin && (
              <NavLink
                to="/admin/directory"
                className={({ isActive }) =>
                  `flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150 ${
                    isActive
                      ? "bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300"
                      : "text-amber-600 hover:bg-amber-50 dark:text-amber-400 dark:hover:bg-slate-900"
                  }`
                }
              >
                <NavIcon name="team" />
                Users
              </NavLink>
            )}
          </nav>
        </aside>

        <div className="flex-1">
          <header className="flex items-center justify-between border-b border-slate-200 bg-white/80 px-6 py-4 backdrop-blur transition-colors duration-200 dark:border-slate-800 dark:bg-slate-950/80">
            <div className="flex items-center gap-3 text-sm text-slate-500 dark:text-slate-400">
              {isSuperAdmin ? (
                <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-500/20 dark:text-amber-300">
                  Role: SuperAdmin
                </span>
              ) : (
                <>
                  <span className="capitalize">Role: {claims?.role}</span>
                  {planLabel && (
                    <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-xs font-medium text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
                      {planLabel} plan
                    </span>
                  )}
                  {currentAccount?.type === "team" && (
                    <span>
                      {currentAccount.member_count} member{currentAccount.member_count === 1 ? "" : "s"}
                    </span>
                  )}
                </>
              )}
            </div>
            <div className="flex items-center gap-3">
              <AccountSwitcher />
              <ThemeToggle />
              <NavLink
                to="/dashboard/profile"
                title="Profile"
                className={({ isActive }) =>
                  `flex h-9 w-9 items-center justify-center rounded-md border transition-colors duration-200 ${
                    isActive
                      ? "border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-700 dark:bg-brand-500/15 dark:text-brand-300"
                      : "border-slate-300 text-slate-600 hover:bg-slate-100 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
                  }`
                }
              >
                <NavIcon name="profile" />
              </NavLink>
              <button
                onClick={() => logout()}
                className="rounded-md px-3 py-1.5 text-sm text-slate-500 transition-colors duration-200 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-white"
              >
                Log out
              </button>
            </div>
          </header>
          <main className="animate-fade-in px-6 py-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
