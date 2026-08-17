import { apiFetch } from "./client";

export interface ScrapeJob {
  id: string;
  account_id: string;
  target_url: string;
  job_type: string;
  status: string;
  recurrence: string;
  error_reason: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface ScrapedDocument {
  id: string;
  scrape_job_id: string;
  url: string;
  title: string;
  text_content: string;
  created_at: string;
}

export function listScrapeJobs() {
  return apiFetch<ScrapeJob[]>("/scrape-jobs");
}

export function createScrapeJob(target_url: string, job_type: string, recurrence: string) {
  return apiFetch<ScrapeJob>("/scrape-jobs", {
    method: "POST",
    body: { target_url, job_type, recurrence },
  });
}

export function getScrapeJob(jobId: string) {
  return apiFetch<ScrapeJob>(`/scrape-jobs/${jobId}`);
}

export function getScrapedDocument(documentId: string) {
  return apiFetch<ScrapedDocument>(`/scraped-documents/${documentId}`);
}

export function getScrapeJobDocument(jobId: string) {
  return apiFetch<ScrapedDocument>(`/scrape-jobs/${jobId}/document`);
}
