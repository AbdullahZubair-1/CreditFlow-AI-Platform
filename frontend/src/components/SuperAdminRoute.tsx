import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import ProtectedRoute from "./ProtectedRoute";

export default function SuperAdminRoute({ children }: { children: ReactNode }) {
  const { claims } = useAuth();

  return (
    <ProtectedRoute>
      {claims?.is_superadmin ? <>{children}</> : <Navigate to="/dashboard" replace />}
    </ProtectedRoute>
  );
}
