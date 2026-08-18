import { BrowserRouter, Route, Routes } from "react-router-dom";

import OwnerRoute from "./components/OwnerRoute";
import PlanGateRoute from "./components/PlanGateRoute";
import ProtectedRoute from "./components/ProtectedRoute";
import SuperAdminRoute from "./components/SuperAdminRoute";
import { AccountProvider } from "./context/AccountContext";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import AcceptInvite from "./pages/AcceptInvite";
import AdminConsole from "./pages/AdminConsole";
import BillingInvoices from "./pages/BillingInvoices";
import CalendarScheduler from "./pages/CalendarScheduler";
import ContentStudio from "./pages/ContentStudio";
import CreateOrJoinAccount from "./pages/CreateOrJoinAccount";
import CreditsPage from "./pages/CreditsPage";
import Dashboard from "./pages/Dashboard";
import ForgotPassword from "./pages/ForgotPassword";
import Home from "./pages/Home";
import LinkedInConnections from "./pages/LinkedInConnections";
import Login from "./pages/Login";
import MarketplacePage from "./pages/MarketplacePage";
import ProfilePage from "./pages/ProfilePage";
import SignUp from "./pages/SignUp";
import SuperAdminUsers from "./pages/SuperAdminUsers";
import TeamManagement from "./pages/TeamManagement";
import VerifyEmail from "./pages/VerifyEmail";

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <AccountProvider>
          <BrowserRouter>
            <Routes>
            {/* Public */}
            <Route path="/" element={<Home />} />
            <Route path="/signup" element={<SignUp />} />
            <Route path="/login" element={<Login />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/verify-email" element={<VerifyEmail />} />
            <Route path="/accept-invite" element={<AcceptInvite />} />

            {/* Onboarding */}
            <Route
              path="/onboarding"
              element={
                <ProtectedRoute>
                  <CreateOrJoinAccount />
                </ProtectedRoute>
              }
            />

            {/* Owner + Member */}
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/content"
              element={
                <ProtectedRoute>
                  <ContentStudio />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/profile"
              element={
                <ProtectedRoute>
                  <ProfilePage />
                </ProtectedRoute>
              }
            />
            {/* Calendar and LinkedIn require the Pro or Team plan */}
            <Route
              path="/dashboard/calendar"
              element={
                <ProtectedRoute>
                  <PlanGateRoute requireTier="paid">
                    <CalendarScheduler />
                  </PlanGateRoute>
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/linkedin"
              element={
                <ProtectedRoute>
                  <PlanGateRoute requireTier="paid">
                    <LinkedInConnections />
                  </PlanGateRoute>
                </ProtectedRoute>
              }
            />
            {/* OAuth redirect target (Social Publishing's FRONTEND_CONNECTIONS_URL) — same page, different path */}
            <Route
              path="/linkedin-connections"
              element={
                <ProtectedRoute>
                  <PlanGateRoute requireTier="paid">
                    <LinkedInConnections />
                  </PlanGateRoute>
                </ProtectedRoute>
              }
            />

            {/* Owner-only */}
            {/* Team Management additionally requires the Team plan */}
            <Route
              path="/dashboard/team"
              element={
                <OwnerRoute>
                  <PlanGateRoute requireTier="team">
                    <TeamManagement />
                  </PlanGateRoute>
                </OwnerRoute>
              }
            />
            {/* Billing/Credits/Marketplace: any member can view (balance,
                invoices, listings); the owner/admin-only actions within
                them (change plan, buy/sell credits) are gated inside each
                page and enforced server-side — see Gateway's
                _require_owner_tier and Credits' own copy of it. */}
            <Route
              path="/dashboard/billing"
              element={
                <ProtectedRoute>
                  <BillingInvoices />
                </ProtectedRoute>
              }
            />
            <Route
              path="/dashboard/credits"
              element={
                <ProtectedRoute>
                  <CreditsPage />
                </ProtectedRoute>
              }
            />
            {/* Marketplace additionally requires the Pro or Team plan */}
            <Route
              path="/dashboard/marketplace"
              element={
                <ProtectedRoute>
                  <PlanGateRoute requireTier="paid">
                    <MarketplacePage />
                  </PlanGateRoute>
                </ProtectedRoute>
              }
            />

            {/* SuperAdmin-only */}
            <Route
              path="/admin"
              element={
                <SuperAdminRoute>
                  <AdminConsole />
                </SuperAdminRoute>
              }
            />
            <Route
              path="/admin/directory"
              element={
                <SuperAdminRoute>
                  <SuperAdminUsers />
                </SuperAdminRoute>
              }
            />
            </Routes>
          </BrowserRouter>
        </AccountProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
