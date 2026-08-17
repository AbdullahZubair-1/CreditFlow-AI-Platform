import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import {
  createScrapeJob,
  getScrapeJob,
  getScrapeJobDocument,
  listScrapeJobs,
  type ScrapedDocument,
  type ScrapeJob,
} from "../api/scraper";
import AppLayout from "../components/AppLayout";

const STATUS_STYLES: Record<string, string> = {
  pending: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300",
  scheduled: "bg-amber-100 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
  completed: "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
  failed: "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300",
};

export default function ScraperJobs() {
  const [jobs, setJobs] = useState<ScrapeJob[]>([]);
  const [targetUrl, setTargetUrl] = useState("");
  const [jobType, setJobType] = useState("generic");
  const [recurrence, setRecurrence] = useState("none");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [docTarget, setDocTarget] = useState<ScrapedDocument | null>(null);
  const [docError, setDocError] = useState<string | null>(null);

  function refresh() {
    listScrapeJobs().then(setJobs).catch(() => undefined);
  }

  useEffect(refresh, []);

  // Jobs finish asynchronously (crawled by a background worker consuming
  // scrape.requested off RabbitMQ) so the list needs to poll rather than
  // rely on a one-shot fetch to ever show "completed".
  useEffect(() => {
    const hasInFlight = jobs.some((j) => j.status === "pending" || j.status === "scheduled");
    if (!hasInFlight) return;
    const timer = setInterval(refresh, 4000);
    return () => clearInterval(timer);
  }, [jobs]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const job = await createScrapeJob(targetUrl, jobType, recurrence);
      setJobs((prev) => [job, ...prev]);
      setTargetUrl("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create scrape job.");
    } finally {
      setSubmitting(false);
    }
  }

  async function viewDocument(jobId: string) {
    setDocError(null);
    setDocTarget(null);
    try {
      const latest = await getScrapeJob(jobId);
      if (latest.status !== "completed") {
        setDocError("This job hasn't finished scraping yet.");
        return;
      }
      const doc = await getScrapeJobDocument(jobId);
      setDocTarget(doc);
    } catch (err) {
      setDocError(err instanceof ApiError ? err.message : "Failed to load scraped document.");
    }
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Web Scraper</h1>
      <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">
        Scrape a page for reference material — completed scrapes are automatically turned into a draft in
        Content Studio.
      </p>

      <form onSubmit={handleCreate} className="mt-6 flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[240px]">
          <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Target URL</label>
          <input
            type="url"
            required
            placeholder="https://example.com/article"
            value={targetUrl}
            onChange={(e) => setTargetUrl(e.target.value)}
            className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Type</label>
          <select
            value={jobType}
            onChange={(e) => setJobType(e.target.value)}
            className="rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
          >
            <option value="generic">Generic page</option>
            <option value="article">Article</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-slate-400">Repeat</label>
          <select
            value={recurrence}
            onChange={(e) => setRecurrence(e.target.value)}
            className="rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
          >
            <option value="none">Once</option>
            <option value="daily">Daily</option>
            <option value="weekly">Weekly</option>
          </select>
        </div>
        <button
          disabled={submitting}
          className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400 disabled:opacity-50"
        >
          {submitting ? "Starting…" : "Start scrape"}
        </button>
      </form>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-8 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-white dark:bg-slate-900 text-left text-slate-500 dark:text-slate-400">
            <tr>
              <th className="px-4 py-2">URL</th>
              <th className="px-4 py-2">Type</th>
              <th className="px-4 py-2">Repeat</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Created</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-t border-slate-200 dark:border-slate-800">
                <td className="max-w-xs truncate px-4 py-2" title={job.target_url}>
                  {job.target_url}
                </td>
                <td className="px-4 py-2 capitalize">{job.job_type}</td>
                <td className="px-4 py-2 capitalize">{job.recurrence}</td>
                <td className="px-4 py-2">
                  <span
                    className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${
                      STATUS_STYLES[job.status] ?? STATUS_STYLES.pending
                    }`}
                  >
                    {job.status}
                  </span>
                  {job.status === "failed" && job.error_reason && (
                    <p className="mt-1 text-xs text-red-500 dark:text-red-400">{job.error_reason}</p>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-500 dark:text-slate-400">
                  {new Date(job.created_at).toLocaleString()}
                </td>
                <td className="px-4 py-2 text-right">
                  {job.status === "completed" && (
                    <button
                      onClick={() => viewDocument(job.id)}
                      className="text-sm text-indigo-600 dark:text-indigo-400 hover:underline"
                    >
                      View result
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-500 dark:text-slate-400">
                  No scrape jobs yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {(docTarget || docError) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
          <div className="w-full max-w-2xl max-h-[80vh] overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
            {docError ? (
              <p className="text-sm text-red-600 dark:text-red-400">{docError}</p>
            ) : (
              docTarget && (
                <>
                  <h2 className="text-lg font-semibold">{docTarget.title || "Untitled page"}</h2>
                  <a
                    href={docTarget.url}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-1 block text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
                  >
                    {docTarget.url}
                  </a>
                  <p className="mt-4 whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">
                    {docTarget.text_content}
                  </p>
                </>
              )
            )}
            <div className="mt-6 flex justify-end">
              <button
                onClick={() => {
                  setDocTarget(null);
                  setDocError(null);
                }}
                className="rounded-md border border-slate-300 dark:border-slate-700 px-4 py-2 text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
