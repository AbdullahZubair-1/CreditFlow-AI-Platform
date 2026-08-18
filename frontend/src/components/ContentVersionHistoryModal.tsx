import { useEffect, useState } from "react";

import { listContentVersions, type Content, type ContentVersion } from "../api/content";

interface ContentVersionHistoryModalProps {
  content: Content;
  onClose: () => void;
}

export default function ContentVersionHistoryModal({ content, onClose }: ContentVersionHistoryModalProps) {
  const [versions, setVersions] = useState<ContentVersion[]>([]);
  const [selected, setSelected] = useState<ContentVersion | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listContentVersions(content.id)
      .then((v) => {
        setVersions(v);
        setSelected(v[0] ?? null);
      })
      .catch(() => setError("Failed to load version history."));
  }, [content.id]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4">
      <div className="flex max-h-[85vh] w-full max-w-4xl overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
        <div className="w-48 shrink-0 overflow-y-auto border-r border-slate-200 dark:border-slate-800 p-3">
          <p className="mb-2 px-1 text-xs font-medium uppercase text-slate-500 dark:text-slate-400">Versions</p>
          {versions.map((v) => (
            <button
              key={v.version_number}
              onClick={() => setSelected(v)}
              className={`mb-1 block w-full rounded-md px-2 py-1.5 text-left text-sm ${
                selected?.version_number === v.version_number
                  ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300"
                  : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              }`}
            >
              <span className="font-medium">v{v.version_number}</span>
              <span className="block text-xs text-slate-500 dark:text-slate-400">
                {new Date(v.created_at).toLocaleString()}
              </span>
            </button>
          ))}
          {versions.length === 0 && !error && (
            <p className="px-1 text-xs text-slate-500 dark:text-slate-400">Loading…</p>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">Version history</h2>
            <button
              onClick={onClose}
              className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
            >
              Close
            </button>
          </div>

          {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

          {selected && (
            <div className="mt-4 space-y-3">
              <h3 className="text-base font-medium">{selected.title}</h3>
              {selected.image_url && (
                <img src={selected.image_url} alt="" className="max-h-56 rounded-md" />
              )}
              <p className="whitespace-pre-wrap text-sm text-slate-600 dark:text-slate-300">{selected.body}</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
