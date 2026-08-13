import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

import * as authApi from "../api/auth";
import { getAccessToken, setTokens, subscribeToTokenChanges } from "../api/client";
import { decodeJwt, type JwtClaims } from "../api/jwt";

interface AuthContextValue {
  claims: JwtClaims | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  switchAccount: (accountId: string) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

// Refresh token is kept in an httpOnly cookie in production (set by the
// Gateway); for this dev slice — where the Gateway only proxies bearer
// tokens rather than setting cookies — we persist it in memory only.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [claims, setClaims] = useState<JwtClaims | null>(() => {
    const token = getAccessToken();
    return token ? decodeJwt(token) : null;
  });

  useEffect(() => {
    subscribeToTokenChanges((access) => {
      setClaims(access ? decodeJwt(access) : null);
    });
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await authApi.login(email, password);
    setTokens(tokens.access_token, tokens.refresh_token);
  }, []);

  const logout = useCallback(async () => {
    const token = getAccessToken();
    if (token) {
      await authApi.logout(token).catch(() => undefined);
    }
    setTokens(null, null);
  }, []);

  const switchAccount = useCallback(async (accountId: string) => {
    const token = getAccessToken();
    if (!token) throw new Error("Not authenticated");
    const tokens = await authApi.switchAccount(token, accountId);
    setTokens(tokens.access_token, tokens.refresh_token);
  }, []);

  const value = useMemo(
    () => ({ claims, isAuthenticated: claims !== null, login, logout, switchAccount }),
    [claims, login, logout, switchAccount]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
