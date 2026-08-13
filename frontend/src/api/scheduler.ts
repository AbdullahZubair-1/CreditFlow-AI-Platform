import { apiFetch } from "./client";

export interface ScheduledPost {
  id: string;
  account_id: string;
  content_id: string;
  publish_at: string;
  status: "scheduled" | "fired" | "cancelled";
  recurrence: "none" | "daily" | "weekly" | "monthly";
  occurrences_fired: number;
  created_at: string;
}

export function listScheduled(start: Date, end: Date) {
  const params = new URLSearchParams({ start: start.toISOString(), end: end.toISOString() });
  return apiFetch<ScheduledPost[]>(`/scheduled?${params.toString()}`);
}

export function createSchedule(contentId: string, publishAt: Date, recurrence: string) {
  return apiFetch<ScheduledPost>("/scheduled", {
    method: "POST",
    body: { content_id: contentId, publish_at: publishAt.toISOString(), recurrence },
  });
}

export function reschedule(id: string, publishAt?: Date, recurrence?: string) {
  return apiFetch<ScheduledPost>(`/scheduled/${id}`, {
    method: "PATCH",
    body: {
      ...(publishAt ? { publish_at: publishAt.toISOString() } : {}),
      ...(recurrence ? { recurrence } : {}),
    },
  });
}

export function cancelSchedule(id: string) {
  return apiFetch<void>(`/scheduled/${id}`, { method: "DELETE" });
}
