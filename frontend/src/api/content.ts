import { apiFetch, getAccessToken } from "./client";

export interface Content {
  id: string;
  account_id: string;
  created_by_user_id: string;
  title: string;
  body: string;
  image_url: string | null;
  status: "draft" | "approved" | "published";
  source_generation_job_id: string | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export function listContent() {
  return apiFetch<Content[]>("/content");
}

export function getContent(id: string) {
  return apiFetch<Content>(`/content/${id}`);
}

export function createContent(title: string, body: string) {
  return apiFetch<Content>("/content", { method: "POST", body: { title, body } });
}

export function updateContent(id: string, fields: Partial<Pick<Content, "title" | "body" | "image_url">>) {
  return apiFetch<Content>(`/content/${id}`, { method: "PATCH", body: fields });
}

export function updateContentStatus(id: string, status: string) {
  return apiFetch<Content>(`/content/${id}/status`, { method: "POST", body: { status } });
}

export function deleteContent(id: string) {
  return apiFetch<void>(`/content/${id}`, { method: "DELETE" });
}

export async function uploadContentImage(id: string, file: File): Promise<{ image_url: string }> {
  // Multipart upload bypasses apiFetch's JSON body handling, but still
  // needs the same bearer token.
  const formData = new FormData();
  formData.append("file", file);

  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";
  const token = getAccessToken();
  const res = await fetch(`${API_BASE_URL}/content/${id}/image`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.error?.message ?? "Image upload failed");
  }
  return res.json();
}
