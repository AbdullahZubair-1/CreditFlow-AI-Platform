import { apiFetch } from "./client";

export interface ConnectionStatus {
  connected: boolean;
  linkedin_member_urn: string | null;
  expires_at: string | null;
}

export interface PublishJob {
  id: string;
  scheduled_post_id: string;
  content_id: string;
  status: "pending" | "published" | "failed";
  linkedin_post_id: string | null;
  error_reason: string | null;
  created_at: string;
  completed_at: string | null;
}

export function getConnectionStatus() {
  return apiFetch<ConnectionStatus>("/social/connections");
}

export function disconnectLinkedIn() {
  return apiFetch<void>("/social/connections", { method: "DELETE" });
}

export function startLinkedInConnect() {
  // The redirect target after LinkedIn's OAuth flow completes is fixed
  // server-side (Social Publishing's FRONTEND_CONNECTIONS_URL config),
  // not something this call configures per-request.
  return apiFetch<{ authorize_url: string }>("/social/linkedin/connect", { method: "POST" });
}

export function listPublishJobs() {
  return apiFetch<PublishJob[]>("/social/publish-jobs");
}
