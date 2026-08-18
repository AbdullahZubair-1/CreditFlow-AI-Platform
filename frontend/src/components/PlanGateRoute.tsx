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
  const { planTier } = useAccount();

  if (planTier === null) return null; // still loading the account's plan

  const allowed = requireTier === "team" ? planTier === "team" : PAID_TIERS.has(planTier);
  if (allowed) return <>{children}</>;

  return (
    <AppLayout>
      <div className="mx-auto mt-16 max-w-md rounded-lg border border-slate-800 bg-slate-900 p-8 text-center">
        <h1 className="text-xl font-semibold">Upgrade required</h1>
        <p className="mt-2 text-sm text-slate-400">
          {requireTier === "team"
            ? "This feature requires the Team plan."
            : "This feature requires the Pro or Team plan."}
        </p>
        <Link
          to="/dashboard/billing"
          className="mt-4 inline-block rounded-md bg-brand-500 px-4 py-2 text-sm font-medium hover:bg-brand-400"
        >
          View plans
        </Link>
      </div>
    </AppLayout>
  );
}
