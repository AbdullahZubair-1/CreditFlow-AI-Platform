import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import ProtectedRoute from "./ProtectedRoute";

const OWNER_ROLES = new Set(["owner", "admin"]);

// Route guarding is a UX convenience, not a security boundary — the
// Gateway/services re-check role on every call regardless, per the spec.
export default function OwnerRoute({ children }: { children: ReactNode }) {
  const { claims } = useAuth();

  return (
    <ProtectedRoute>
      {claims && OWNER_ROLES.has(claims.role) ? <>{children}</> : <Navigate to="/dashboard" replace />}
    </ProtectedRoute>
  );
}
