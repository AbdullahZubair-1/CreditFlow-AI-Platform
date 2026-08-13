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
import { useAuth } from "../context/AuthContext";

const PUBLISH_ROLES = new Set(["owner", "admin"]);

export default function ContentStudio() {
  const { claims } = useAuth();
  const canPublish = claims ? PUBLISH_ROLES.has(claims.role) : false;

  const [models, setModels] = useState<Record<string, string>>({});
  const [prompt, setPrompt] = useState("");
  const [model, setModel] = useState("fast");
  const [streaming, setStreaming] = useState(false);
  const [streamedText, setStreamedText] = useState("");
  const [currentJobId, setCurrentJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Content[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);
  const stopStreamRef = useRef<(() => void) | null>(null);

  function refreshDrafts() {
    listContent().then(setDrafts).catch(() => undefined);
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
    setStreaming(true);

    try {
      const { job_id } = await createGeneration(prompt, model, "post");
      setCurrentJobId(job_id);

      stopStreamRef.current = streamGeneration(
        job_id,
        (event: GenerationStreamEvent) => {
          if (event.type === "token") {
            setStreamedText((prev) => prev + event.content);
          } else if (event.type === "error") {
            setError(event.message);
          }
        },
        () => {
          setStreaming(false);
          refreshDrafts();
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
    try {
      const { image_url } = await generateImage(currentJobId, prompt);
      await updateContent(contentId, { image_url });
      refreshDrafts();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to generate image.");
    }
  }

  async function handlePublishStep(content: Content) {
    const next = content.status === "draft" ? "approved" : "published";
    setError(null);
    try {
      await updateContentStatus(content.id, next);
      refreshDrafts();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update status.");
    }
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
          className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <div className="flex items-center gap-3">
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none"
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
          <button
            disabled={streaming}
            className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400 disabled:opacity-50"
          >
            {streaming ? "Generating..." : "Generate"}
          </button>
        </div>
      </form>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      {(streaming || streamedText) && (
        <div className="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-4">
          <p className="whitespace-pre-wrap text-sm">{streamedText}</p>
          {!streaming && generatedContent && (
            <div className="mt-4 flex gap-3">
              <button
                onClick={() => handleGenerateImage(generatedContent.id)}
                className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
              >
                Generate image for this post
              </button>
            </div>
          )}
        </div>
      )}

      <h2 className="mt-10 text-lg font-semibold">Drafts</h2>
      <div className="mt-3 space-y-3">
        {drafts.map((content) => (
          <div key={content.id} className="rounded-lg border border-slate-800 p-4">
            <div className="flex items-start justify-between gap-4">
              <div>
                <p className="font-medium">{content.title}</p>
                <p className="mt-1 text-sm text-slate-400">{content.body.slice(0, 200)}</p>
                {content.image_url && (
                  <img src={content.image_url} alt="" className="mt-2 max-h-40 rounded-md" />
                )}
              </div>
              <div className="flex shrink-0 flex-col items-end gap-2">
                <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs capitalize text-slate-300">
                  {content.status}
                </span>
                {canPublish && content.status !== "published" && (
                  <button
                    onClick={() => handlePublishStep(content)}
                    className="text-xs text-indigo-400 hover:underline"
                  >
                    {content.status === "draft" ? "Approve" : "Publish"}
                  </button>
                )}
                <button onClick={() => setDeleteTarget(content.id)} className="text-xs text-red-400 hover:underline">
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
    </AppLayout>
  );
}
