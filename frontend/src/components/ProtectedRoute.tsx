import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children }: { children: ReactNode }) {
  const { isAuthenticated, isRestoring } = useAuth();
  // Wait for the mount-time silent-refresh attempt (see AuthContext) before
  // deciding to redirect — otherwise every full page load (including
  // returning from the LinkedIn OAuth redirect) would flash straight to
  // /login before the httpOnly cookie has a chance to restore the session.
  if (isRestoring) return null;
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
