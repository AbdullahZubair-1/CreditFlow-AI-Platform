import { BrowserRouter, Route, Routes } from "react-router-dom";

import OwnerRoute from "./components/OwnerRoute";
import ProtectedRoute from "./components/ProtectedRoute";
import SuperAdminRoute from "./components/SuperAdminRoute";
import { AuthProvider } from "./context/AuthContext";
import AcceptInvite from "./pages/AcceptInvite";
import AdminConsole from "./pages/AdminConsole";
import BillingInvoices from "./pages/BillingInvoices";
import CalendarScheduler from "./pages/CalendarScheduler";
import ContentStudio from "./pages/ContentStudio";
import CreateOrJoinAccount from "./pages/CreateOrJoinAccount";
import CreditsMarketplace from "./pages/CreditsMarketplace";
import Dashboard from "./pages/Dashboard";
import ForgotPassword from "./pages/ForgotPassword";
import Home from "./pages/Home";
import LinkedInConnections from "./pages/LinkedInConnections";
import Login from "./pages/Login";
import SignUp from "./pages/SignUp";
import TeamManagement from "./pages/TeamManagement";
import VerifyEmail from "./pages/VerifyEmail";

export default function App() {
  return (
    <AuthProvider>
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
            path="/dashboard/calendar"
            element={
              <ProtectedRoute>
                <CalendarScheduler />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard/linkedin"
            element={
              <ProtectedRoute>
                <LinkedInConnections />
              </ProtectedRoute>
            }
          />
          {/* OAuth redirect target (Social Publishing's FRONTEND_CONNECTIONS_URL) — same page, different path */}
          <Route
            path="/linkedin-connections"
            element={
              <ProtectedRoute>
                <LinkedInConnections />
              </ProtectedRoute>
            }
          />

          {/* Owner-only */}
          <Route
            path="/dashboard/team"
            element={
              <OwnerRoute>
                <TeamManagement />
              </OwnerRoute>
            }
          />
          <Route
            path="/dashboard/billing"
            element={
              <OwnerRoute>
                <BillingInvoices />
              </OwnerRoute>
            }
          />
          <Route
            path="/dashboard/credits"
            element={
              <OwnerRoute>
                <CreditsMarketplace />
              </OwnerRoute>
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
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
