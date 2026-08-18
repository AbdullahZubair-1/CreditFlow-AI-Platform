import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import * as authApi from "../api/auth";
import { getAccessToken, refreshAccessToken, setAccessToken, subscribeToTokenChanges } from "../api/client";
import { decodeJwt, type JwtClaims } from "../api/jwt";

interface AuthContextValue {
  claims: JwtClaims | null;
  isAuthenticated: boolean;
  isRestoring: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  switchAccount: (accountId: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// The access token lives in memory only (see api/client.ts) and is lost on
// every full page load/navigation — including the LinkedIn OAuth connect
// redirect (app -> LinkedIn -> back to app). What survives that is the
// httpOnly refresh token cookie the Gateway sets, which this JS can't read
// but the browser attaches automatically. So on mount, before rendering
// anything that depends on auth state, silently try to exchange that
// cookie for a fresh access token — this is what keeps the user logged in
// across the redirect without ever storing a token in JS-readable storage.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [claims, setClaims] = useState<JwtClaims | null>(() => {
    const token = getAccessToken();
    return token ? decodeJwt(token) : null;
  });
  const [isRestoring, setIsRestoring] = useState(true);

  useEffect(() => {
    subscribeToTokenChanges((access) => {
      setClaims(access ? decodeJwt(access) : null);
    });
  }, []);

  useEffect(() => {
    refreshAccessToken().finally(() => setIsRestoring(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login(email, password);
    setAccessToken(tokens.access_token);
  }, []);

  const logout = useCallback(async () => {
    const token = getAccessToken();
    if (token) {
      await authApi.logout(token).catch(() => undefined);
    }
    setAccessToken(null);
  }, []);

  const switchAccount = useCallback(async (accountId: string) => {
    const token = getAccessToken();
    if (!token) throw new Error("Not authenticated");
    const tokens = await authApi.switchAccount(token, accountId);
    setAccessToken(tokens.access_token);
  }, []);

  const value = useMemo(
    () => ({ claims, isAuthenticated: claims !== null, isRestoring, login, logout, switchAccount }),
    [claims, isRestoring, login, logout, switchAccount]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
