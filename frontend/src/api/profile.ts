import { apiFetch } from "./client";

export interface Profile {
  user_id: string;
  email: string;
  name: string | null;
  email_verified: boolean;
}

export function getProfile() {
  return apiFetch<Profile>("/auth/profile");
}

export function updateProfile(name: string) {
  return apiFetch<Profile>("/auth/profile", { method: "PATCH", body: { name } });
}

export function deleteAccount(password: string) {
  return apiFetch<void>("/auth/account", { method: "DELETE", body: { password } });
}
