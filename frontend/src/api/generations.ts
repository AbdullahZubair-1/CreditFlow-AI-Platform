import { apiFetch, getAccessToken } from "./client";

export interface GenerationJob {
  id: string;
  model: string;
  status: string;
  prompt: string;
  response: string;
  total_tokens: number;
  cost_cents: number;
  error_reason: string | null;
  created_at: string;
  completed_at: string | null;
}

export function listModels() {
  return apiFetch<Record<string, string>>("/models");
}

export function createGeneration(prompt: string, model: string, purpose = "post") {
  return apiFetch<{ job_id: string; status: string }>("/generations", {
    method: "POST",
    body: { prompt, model, purpose },
  });
}

export function getGeneration(jobId: string) {
  return apiFetch<GenerationJob>(`/generations/${jobId}`);
}

export function cancelGeneration(jobId: string) {
  return apiFetch<void>(`/generations/${jobId}/cancel`, { method: "POST" });
}

export function generateImage(jobId: string, prompt: string) {
  return apiFetch<{ id: string; image_url: string }>(`/generations/${jobId}/image`, {
    method: "POST",
    body: { prompt },
  });
}

export type GenerationStreamEvent =
  | { type: "token"; content: string }
  | { type: "done"; total_tokens: number }
  | { type: "cancelled" }
  | { type: "error"; message: string };

/** EventSource can't set an Authorization header, so the access token
 * travels via query string for this one endpoint (see the Gateway's
 * require_jwt_from_header_or_query). */
export function streamGeneration(
  jobId: string,
  onEvent: (event: GenerationStreamEvent) => void,
  onClose: () => void
): () => void {
  const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8080";
  const token = getAccessToken();
  const source = new EventSource(`${API_BASE_URL}/sse/${jobId}?access_token=${encodeURIComponent(token ?? "")}`);

  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as GenerationStreamEvent;
      onEvent(event);
      if (event.type === "done" || event.type === "cancelled" || event.type === "error") {
        source.close();
        onClose();
      }
    } catch {
      // ignore malformed chunks
    }
  };

  source.onerror = () => {
    source.close();
    onClose();
  };

  return () => source.close();
}
