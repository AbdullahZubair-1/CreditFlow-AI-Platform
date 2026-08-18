import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { useAccount } from "../context/AccountContext";
import AppLayout from "./AppLayout";

const PAID_TIERS = new Set(["pro", "team"]);

interface PlanGateRouteProps {
  children: ReactNode;
  requireTier: "paid" | "team";
}

// Route guarding is a UX convenience, not a security boundary — the
// Gateway re-checks plan tier on every call to these features regardless
// (see services/gateway/app/plan_access.py), same pattern as
// OwnerRoute/SuperAdminRoute.
export default function PlanGateRoute({ children, requireTier }: PlanGateRouteProps) {
  const { planTier, currentAccount } = useAccount();

  if (planTier === null) return null; // still loading the account's plan

  // Team Management specifically also needs a genuine team-type account,
  // not just the Team plan_tier — those are separate axes (an individual
  // account can subscribe to any plan, including Team), and inviting
  // members onto a personal account broke the "individual accounts have
  // exactly one member" invariant the rest of the system assumes. The
  // real enforcement is server-side (see User/Tenant's invite_member); this
  // is the same "UX convenience, not a security boundary" pattern as the
  // rest of this component.
  const isTeamTypeAccount = currentAccount?.type === "team";
  const needsTeamAccount = requireTier === "team" && planTier === "team" && !isTeamTypeAccount;
  const allowed = requireTier === "team" ? planTier === "team" && isTeamTypeAccount : PAID_TIERS.has(planTier);
  if (allowed) return <>{children}</>;

  return (
    <AppLayout>
      <div className="mx-auto mt-16 max-w-md rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
        <h1 className="text-xl font-semibold">{needsTeamAccount ? "Team account required" : "Upgrade required"}</h1>
        <p className="mt-2 text-sm text-slate-400">
          {needsTeamAccount
            ? "This is your personal account, not a team account. Create a team account first to invite members."
            : requireTier === "team"
            ? "This feature requires the Team plan."
            : "This feature requires the Pro or Team plan."}
        </p>
        <Link
          to={needsTeamAccount ? "/onboarding" : "/dashboard/billing"}
          className="mt-4 inline-block rounded-md bg-brand-500 px-4 py-2 text-sm font-medium hover:bg-brand-400"
        >
          {needsTeamAccount ? "Create a team account" : "View plans"}
        </Link>
      </div>
    </AppLayout>
  );
}
