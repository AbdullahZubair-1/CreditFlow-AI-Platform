import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import { deleteAccount, getProfile, updateProfile, type Profile } from "../api/profile";
import AppLayout from "../components/AppLayout";
import { useAuth } from "../context/AuthContext";

export default function ProfilePage() {
  const { logout, claims } = useAuth();
  const isSuperAdmin = claims?.is_superadmin ?? false;

  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [deleteOpen, setDeleteOpen] = useState(false);
  const [confirmText, setConfirmText] = useState("");
  const [password, setPassword] = useState("");
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    getProfile()
      .then((p) => {
        setProfile(p);
        setName(p.name ?? "");
      })
      .catch(() => undefined);
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaved(false);
    setSaving(true);
    try {
      const updated = await updateProfile(name);
      setProfile(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to update profile.");
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(e: React.FormEvent) {
    e.preventDefault();
    setDeleteError(null);
    setDeleting(true);
    try {
      await deleteAccount(password);
      await logout();
      window.location.href = "/";
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Failed to delete account.");
      setDeleting(false);
    }
  }

  return (
    <AppLayout>
      <div className="mx-auto max-w-2xl animate-fade-in">
        <h1 className="text-2xl font-semibold text-slate-900 dark:text-slate-100">Profile</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Manage your personal account details.</p>

        <div className="mt-8 rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-colors dark:border-slate-800 dark:bg-slate-900">
          <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">Account details</h2>

          <form onSubmit={handleSave} className="mt-4 space-y-4">
            <div>
              <label className="block text-sm font-medium text-slate-600 dark:text-slate-400">Email</label>
              <input
                disabled
                value={profile?.email ?? ""}
                className="mt-1 w-full rounded-md border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
              />
              {profile && !profile.email_verified && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">Email not verified.</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-600 dark:text-slate-400">Display name</label>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 outline-none transition-colors focus:border-brand-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </div>

            {error && <p className="text-sm text-red-600 dark:text-red-400">{error}</p>}
            {saved && <p className="text-sm text-emerald-600 dark:text-emerald-400">Saved.</p>}

            <button
              disabled={saving}
              className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white transition-colors duration-200 hover:bg-brand-500 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save changes"}
            </button>
          </form>
        </div>

        <div className="mt-8 rounded-xl border border-red-200 bg-red-50/50 p-6 transition-colors dark:border-red-900/50 dark:bg-red-950/20">
          <h2 className="text-lg font-semibold text-red-700 dark:text-red-400">Danger zone</h2>

          {isSuperAdmin ? (
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
              SuperAdmin accounts cannot be deleted through self-service account deletion.
            </p>
          ) : (
            <>
              <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">
                Permanently delete your account. This cannot be undone.
              </p>

              {!deleteOpen ? (
                <button
                  onClick={() => setDeleteOpen(true)}
                  className="mt-4 rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 transition-colors duration-200 hover:bg-red-100 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950/40"
                >
                  Delete my account
                </button>
              ) : (
                <form onSubmit={handleDelete} className="mt-4 space-y-3 animate-slide-up">
                  <div>
                    <label className="block text-sm font-medium text-slate-600 dark:text-slate-400">
                      Type <span className="font-mono font-semibold">DELETE</span> to confirm
                    </label>
                    <input
                      required
                      value={confirmText}
                      onChange={(e) => setConfirmText(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-slate-600 dark:text-slate-400">
                      Confirm your password
                    </label>
                    <input
                      required
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      className="mt-1 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
                    />
                  </div>

                  {deleteError && <p className="text-sm text-red-600 dark:text-red-400">{deleteError}</p>}

                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={() => {
                        setDeleteOpen(false);
                        setConfirmText("");
                        setPassword("");
                        setDeleteError(null);
                      }}
                      className="rounded-md border border-slate-300 px-4 py-2 text-sm hover:bg-slate-100 dark:border-slate-700 dark:hover:bg-slate-800"
                    >
                      Cancel
                    </button>
                    <button
                      disabled={confirmText !== "DELETE" || deleting}
                      className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors duration-200 hover:bg-red-500 disabled:opacity-50"
                    >
                      {deleting ? "Deleting..." : "Permanently delete account"}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
