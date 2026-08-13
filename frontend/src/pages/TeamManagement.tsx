import { useEffect, useState } from "react";

import { inviteMember, listMembers, removeMember, updateMemberRole, type Member } from "../api/accounts";
import { ApiError } from "../api/client";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";
import { useAuth } from "../context/AuthContext";

export default function TeamManagement() {
  const { claims } = useAuth();
  const accountId = claims?.account_id ?? "";

  const [members, setMembers] = useState<Member[]>([]);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("member");
  const [devInviteToken, setDevInviteToken] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  function refresh() {
    if (!accountId) return;
    listMembers(accountId).then(setMembers).catch(() => undefined);
  }

  useEffect(refresh, [accountId]);

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const res = await inviteMember(accountId, email, role);
      // Dev-only: the Notification Service normally emails this link.
      setDevInviteToken(res.dev_invite_token);
      setEmail("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to send invite.");
    }
  }

  async function handleRoleChange(userId: string, newRole: string) {
    setError(null);
    try {
      await updateMemberRole(accountId, userId, newRole);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update role.");
    }
  }

  async function confirmRemove() {
    if (!removeTarget) return;
    setError(null);
    try {
      await removeMember(accountId, removeTarget);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to remove member.");
    } finally {
      setRemoveTarget(null);
    }
  }

  return (
    <AppLayout>
      <h1 className="text-2xl font-semibold">Team Management</h1>

      <form onSubmit={handleInvite} className="mt-6 flex flex-wrap items-end gap-3">
        <input
          type="email"
          required
          placeholder="teammate@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none"
        >
          <option value="member">Member</option>
          <option value="admin">Admin</option>
        </select>
        <button className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400">
          Send invite
        </button>
      </form>

      {devInviteToken && (
        <p className="mt-3 text-sm text-slate-400">
          Dev-only: invite token (normally emailed) —{" "}
          <span className="font-mono text-indigo-400">{devInviteToken}</span>
        </p>
      )}
      {error && <p className="mt-3 text-sm text-red-400">{error}</p>}

      <div className="mt-8 overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-left text-slate-400">
            <tr>
              <th className="px-4 py-2">User</th>
              <th className="px-4 py-2">Role</th>
              <th className="px-4 py-2">Joined</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.user_id} className="border-t border-slate-800">
                <td className="px-4 py-2 font-mono text-xs">{m.user_id}</td>
                <td className="px-4 py-2">
                  <select
                    value={m.role}
                    onChange={(e) => handleRoleChange(m.user_id, e.target.value)}
                    className="rounded-md border border-slate-700 bg-slate-800 px-2 py-1 text-sm outline-none"
                  >
                    <option value="owner">Owner</option>
                    <option value="admin">Admin</option>
                    <option value="member">Member</option>
                  </select>
                </td>
                <td className="px-4 py-2 text-slate-400">{new Date(m.joined_at).toLocaleDateString()}</td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => setRemoveTarget(m.user_id)}
                    className="text-sm text-red-400 hover:underline"
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={removeTarget !== null}
        title="Remove team member"
        message="This member will immediately lose access to this account. This can't be undone from here."
        confirmLabel="Remove member"
        onConfirm={confirmRemove}
        onCancel={() => setRemoveTarget(null)}
      />
    </AppLayout>
  );
}
