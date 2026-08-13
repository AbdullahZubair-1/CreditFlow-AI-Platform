import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import {
  disconnectLinkedIn,
  getConnectionStatus,
  listPublishJobs,
  startLinkedInConnect,
  type ConnectionStatus,
  type PublishJob,
} from "../api/social";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";

export default function LinkedInConnections() {
  const [params] = useSearchParams();
  const [status, setStatus] = useState<ConnectionStatus | null>(null);
  const [jobs, setJobs] = useState<PublishJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const [connecting, setConnecting] = useState(false);

  function refresh() {
    getConnectionStatus().then(setStatus).catch(() => undefined);
    listPublishJobs().then(setJobs).catch(() => undefined);
  }

  useEffect(refresh, []);

  async function handleConnect() {
    setError(null);
    setConnecting(true);
    try {
      const { authorize_url } = await startLinkedInConnect();
      window.location.href = authorize_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to start LinkedIn connection.");
      setConnecting(false);
    }
  }

  async function confirmDisconnectAction() {
    try {
      await disconnectLinkedIn();
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to disconnect.");
    } finally {
      setConfirmDisconnect(false);
    }
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">LinkedIn Connections</h1>

      {params.get("error") && (
        <p className="mt-4 rounded-md bg-red-500/10 px-4 py-2 text-sm text-red-400">
          LinkedIn connection failed ({params.get("error")}). Try again.
        </p>
      )}
      {params.get("connected") === "true" && (
        <p className="mt-4 rounded-md bg-emerald-500/10 px-4 py-2 text-sm text-emerald-400">
          LinkedIn account connected successfully.
        </p>
      )}
      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-5">
        {status?.connected ? (
          <div className="flex items-center justify-between">
            <div>
              <p className="font-medium text-emerald-400">Connected</p>
              <p className="mt-1 text-sm text-slate-400">{status.linkedin_member_urn}</p>
              {status.expires_at && (
                <p className="text-xs text-slate-500">
                  Token valid until {new Date(status.expires_at).toLocaleDateString()}
                </p>
              )}
            </div>
            <button
              onClick={() => setConfirmDisconnect(true)}
              className="rounded-md border border-red-500/50 px-4 py-2 text-sm text-red-400 hover:bg-red-500/10"
            >
              Disconnect
            </button>
          </div>
        ) : (
          <div className="flex items-center justify-between">
            <p className="text-slate-400">No LinkedIn account connected.</p>
            <button
              onClick={handleConnect}
              disabled={connecting}
              className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400 disabled:opacity-50"
            >
              {connecting ? "Redirecting..." : "Connect LinkedIn"}
            </button>
          </div>
        )}
      </div>

      <h2 className="mt-10 text-lg font-semibold">Publish history</h2>
      <div className="mt-3 overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-left text-slate-400">
            <tr>
              <th className="px-4 py-2">Date</th>
              <th className="px-4 py-2">Status</th>
              <th className="px-4 py-2">Detail</th>
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id} className="border-t border-slate-800">
                <td className="px-4 py-2">{new Date(job.created_at).toLocaleString()}</td>
                <td className="px-4 py-2 capitalize">{job.status}</td>
                <td className="px-4 py-2 text-slate-400">
                  {job.status === "published" ? job.linkedin_post_id : job.error_reason}
                </td>
              </tr>
            ))}
            {jobs.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-center text-slate-500">
                  No posts published yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={confirmDisconnect}
        title="Disconnect LinkedIn"
        message="Scheduled posts targeting LinkedIn won't be published until you reconnect."
        confirmLabel="Disconnect"
        onConfirm={confirmDisconnectAction}
        onCancel={() => setConfirmDisconnect(false)}
      />
    </AppLayout>
  );
}
