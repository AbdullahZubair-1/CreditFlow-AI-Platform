import { useEffect, useRef, useState } from "react";

import { ApiError } from "../api/client";
import {
  deleteContent,
  listContent,
  updateContent,
  updateContentStatus,
  type Content,
} from "../api/content";
import {
  createGeneration,
  generateImage,
  listModels,
  streamGeneration,
  type GenerationStreamEvent,
} from "../api/generations";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";
import ContentDetailModal from "../components/ContentDetailModal";
import ContentVersionHistoryModal from "../components/ContentVersionHistoryModal";
import { useAuth } from "../context/AuthContext";

const APPROVE_ROLES = new Set(["owner", "admin"]);

export default function ContentStudio() {
  const { claims } = useAuth();
  const canApprove = claims ? APPROVE_ROLES.has(claims.role) : false;

  const [models, setModels] = useState<Record<string, string>>({});
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("fast");
  const [useWebResearch, setUseWebResearch] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState("");
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Content[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const [detailTarget, setDetailTarget] = useState<{ content: Content; mode: "read" | "edit" } | null>(null);
  const [historyTarget, setHistoryTarget] = useState<Content | null>(null);
  const [imageGenerating, setImageGenerating] = useState(false);
  const [generatedImageUrl, setGeneratedImageUrl] = useState<string | null>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);
  const lastEventTypeRef = useRef<GenerationStreamEvent["type"] | null>(null);

  function refreshDrafts() {
    return listContent().then(setDrafts).catch(() => undefined);
  }

  // The Content draft for a finished generation is created asynchronously
  // (AI Generation -> RabbitMQ -> Content Service), not synchronously
  // within the SSE stream, so it can lag a moment behind the "done" event.
  // A single refreshDrafts() right when streaming ends can miss it —
  // poll briefly instead of giving up after one check, otherwise the
  // "Generate image for this post" button (which needs the draft's id)
  // can simply never appear for that generation.
  async function waitForDraft(jobId: string) {
    for (let attempt = 0; attempt < 10; attempt++) {
      const all = await listContent().catch(() => []);
      setDrafts(all);
      if (all.some((d) => d.source_generation_job_id === jobId)) return;
      await new Promise((resolve) => setTimeout(resolve, 400));
    }
  }

  useEffect(() => {
    listModels().then(setModels).catch(() => undefined);
    refreshDrafts();
    return () => stopStreamRef.current?.();
  }, []);

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setStreamedText("");
    setGeneratedImageUrl(null);
    lastEventTypeRef.current = null;
    setStreaming(true);

    try {
      const { job_id } = await createGeneration(prompt, model, "post", useWebResearch);
      setCurrentJobId(job_id);

      stopStreamRef.current = streamGeneration(
        job_id,
        (event: GenerationStreamEvent) => {
          lastEventTypeRef.current = event.type;
          if (event.type === "token") {
            setStreamedText((prev) => prev + event.content);
          } else if (event.type === "error") {
            setError(event.message);
          }
        },
        () => {
          setStreaming(false);
          if (lastEventTypeRef.current === "done") {
            waitForDraft(job_id);
          } else {
            refreshDrafts();
          }
        }
      );
    } catch (err) {
      setStreaming(false);
      setError(err instanceof ApiError ? err.message : "Failed to start generation.");
    }
  }

  async function handleGenerateImage(contentId: string) {
    if (!currentJobId) return;
    setError(null);
    setImageGenerating(true);
    try {
      const { image_url } = await generateImage(currentJobId, prompt);
      setGeneratedImageUrl(image_url);
      await updateContent(contentId, { image_url });
      refreshDrafts();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate image.");
    } finally {
      setImageGenerating(false);
    }
  }

  async function handleApprove(content: Content) {
    setError(null);
    try {
      await updateContentStatus(content.id, "approved");
      refreshDrafts();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update status.");
    }
  }

  async function handleSaveDetail(fields: { title: string; body: string }) {
    if (!detailTarget) return;
    const updated = await updateContent(detailTarget.content.id, fields);
    setDetailTarget({ content: updated, mode: "read" });
    refreshDrafts();
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    try {
      await deleteContent(deleteTarget);
      refreshDrafts();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete content.");
    } finally {
      setDeleteTarget(null);
    }
  }

  const generatedContent = drafts.find((d) => d.source_generation_job_id === currentJobId);

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Content Studio</h1>

      <form onSubmit={handleGenerate} className="mt-6 space-y-3">
        <textarea
          required
          rows={4}
          placeholder="What should the AI write about?"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          className="w-full rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none focus:border-brand-500"
        />
        <div className="flex items-center gap-3">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
          >
            {Object.keys(models).length > 0 ? (
              Object.keys(models).map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))
            ) : (
              <>
                <option value="fast">fast</option>
                <option value="quality">quality</option>
              </>
            )}
          </select>
          <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400">
            <input
              type="checkbox"
              checked={useWebResearch}
              onChange={(e) => setUseWebResearch(e.target.checked)}
              className="rounded border-slate-300 dark:border-slate-700"
            />
            Research the web first (no URL needed)
          </label>
          <button
            disabled={streaming}
            className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium hover:bg-brand-400 disabled:opacity-50"
          >
            {streaming ? (useWebResearch ? "Researching & generating..." : "Generating...") : "Generate"}
          </button>
        </div>
      </form>

      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      {(streaming || streamedText) && (
        <div className="mt-6 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
          <p className="whitespace-pre-wrap text-sm">{streamedText}</p>
          {!streaming && lastEventTypeRef.current === "done" && (
            <div className="mt-4">
              {generatedImageUrl ? (
                <img src={generatedImageUrl} alt="" className="max-h-64 rounded-md" />
              ) : generatedContent ? (
                <button
                  onClick={() => handleGenerateImage(generatedContent.id)}
                  disabled={imageGenerating}
                  className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
                >
                  {imageGenerating ? "Generating image..." : "Generate image for this post"}
                </button>
              ) : (
                <p className="text-xs text-slate-500">Saving draft...</p>
              )}
            </div>
          )}
        </div>
      )}

      <h2 className="mt-10 text-lg font-semibold">Drafts</h2>
      <div className="mt-3 space-y-3">
        {drafts.map((content) => (
          <div key={content.id} className="rounded-lg border border-slate-200 dark:border-slate-800 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-medium">{content.title}</p>
                <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">{content.body.slice(0, 200)}</p>
                {content.image_url && (
                  <img src={content.image_url} alt="" className="mt-2 max-h-40 rounded-md" />
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <span className="rounded-full bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs capitalize text-slate-600 dark:text-slate-300">
                  {content.status}
                </span>
                <button
                  onClick={() => setDetailTarget({ content, mode: "read" })}
                  className="text-xs text-slate-600 dark:text-slate-300 hover:underline"
                >
                  Read
                </button>
                <button
                  onClick={() => setDetailTarget({ content, mode: "edit" })}
                  className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
                >
                  Edit
                </button>
                <button
                  onClick={() => setHistoryTarget(content)}
                  className="text-xs text-slate-600 dark:text-slate-300 hover:underline"
                >
                  History
                </button>
                {canApprove && content.status === "draft" && (
                  <button
                    onClick={() => handleApprove(content)}
                    className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
                  >
                    Approve
                  </button>
                )}
                {content.status === "approved" && (
                  <span className="text-xs text-slate-500">Approved — schedule it to publish</span>
                )}
                {content.status === "published" && (
                  <span className="text-xs text-emerald-600 dark:text-emerald-400">Published to LinkedIn</span>
                )}
                <button onClick={() => setDeleteTarget(content.id)} className="text-xs text-red-600 dark:text-red-400 hover:underline">
                  Delete
                </button>
              </div>
            </div>
          </div>
        ))}
        {drafts.length === 0 && <p className="text-sm text-slate-500">No content yet — generate something above.</p>}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete content"
        message="This content and its version history will be permanently deleted."
        confirmLabel="Delete"
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
      />

      {detailTarget && (
        <ContentDetailModal
          content={detailTarget.content}
          mode={detailTarget.mode}
          onClose={() => setDetailTarget(null)}
          onSave={handleSaveDetail}
        />
      )}

      {historyTarget && (
        <ContentVersionHistoryModal content={historyTarget} onClose={() => setHistoryTarget(null)} />
      )}
    </AppLayout>
  );
}
