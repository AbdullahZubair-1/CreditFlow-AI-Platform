import { useEffect, useState } from "react";

import type { Content } from "../api/content";

interface ContentDetailModalProps {
  content: Content;
  mode: "read" | "edit";
  onClose: () => void;
  onSave: (fields: { title: string; body: string }) => Promise<void>;
}

// Shared by the Content Studio's "Read" and "Edit" actions — Read opens
// straight into the view below with fields disabled, Edit opens with them
// enabled; either one can switch to the other from inside the modal
// rather than forcing a close-and-reopen round trip.
export default function ContentDetailModal({ content, mode, onClose, onSave }: ContentDetailModalProps) {
  const [editing, setEditing] = useState(mode === "edit");
  const [title, setTitle] = useState(content.title);
  const [body, setBody] = useState(content.body);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setEditing(mode === "edit");
    setTitle(content.title);
    setBody(content.body);
    setError(null);
  }, [content, mode]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave({ title, body });
      setEditing(false);
    } catch {
      setError("Failed to save changes.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="max-h-[85vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-slate-800 bg-slate-900 p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{editing ? "Edit content" : "Read content"}</h2>
          <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs capitalize text-slate-300">
            {content.status}
          </span>
        </div>

        {editing ? (
          <div className="mt-4 space-y-3">
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm font-medium outline-none focus:border-indigo-500"
              placeholder="Title"
            />
            <textarea
              rows={12}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              className="w-full rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
              placeholder="Content"
            />
          </div>
        ) : (
          <div className="mt-4 space-y-3">
            <h3 className="text-base font-medium">{content.title}</h3>
            {content.image_url && (
              <img src={content.image_url} alt="" className="max-h-64 rounded-md" />
            )}
            <p className="whitespace-pre-wrap text-sm text-slate-300">{content.body}</p>
          </div>
        )}

        {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onClose}
            className="rounded-md border border-slate-700 px-4 py-2 text-sm hover:bg-slate-800"
          >
            Close
          </button>
          {editing ? (
            <button
              onClick={handleSave}
              disabled={saving}
              className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save"}
            </button>
          ) : (
            <button
              onClick={() => setEditing(true)}
              className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400"
            >
              Edit
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
