export interface JwtClaims {
  user_id: string;
  account_id: string;
  role: string;
  jti: string;
  exp: number;
}

export function decodeJwt(token: string): JwtClaims | null {
  try {
    const [, payload] = token.split(".");
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  } catch {
    return null;
  }
}
