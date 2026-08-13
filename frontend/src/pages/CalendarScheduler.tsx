import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { listContent, type Content } from "../api/content";
import { cancelSchedule, createSchedule, listScheduled, reschedule, type ScheduledPost } from "../api/scheduler";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";

// A lightweight custom month grid rather than pulling in FullCalendar/React
// Big Calendar (the spec's two suggested options) — avoids adding a new
// npm dependency that can't be installed-and-verified in this environment.
// Functionally equivalent for this scope: a month view of scheduled posts
// with schedule/reschedule/cancel actions.
export default function CalendarScheduler() {
  const [monthStart, setMonthStart] = useState(() => startOfMonth(new Date()));
  const [scheduled, setScheduled] = useState<ScheduledPost[]>([]);
  const [drafts, setDrafts] = useState<Content[]>([]);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [selectedContentId, setSelectedContentId] = useState("");
  const [recurrence, setRecurrence] = useState("none");
  const [error, setError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<string | null>(null);

  const monthEnd = useMemo(() => endOfMonth(monthStart), [monthStart]);

  function refresh() {
    listScheduled(monthStart, monthEnd).then(setScheduled).catch(() => undefined);
  }

  useEffect(refresh, [monthStart]);
  useEffect(() => {
    listContent().then((all) => setDrafts(all.filter((c) => c.status !== "published"))).catch(() => undefined);
  }, []);

  const days = useMemo(() => buildMonthGrid(monthStart), [monthStart]);

  async function handleSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDate || !selectedContentId) return;
    setError(null);
    try {
      const publishAt = new Date(selectedDate);
      publishAt.setHours(9, 0, 0, 0);
      await createSchedule(selectedContentId, publishAt, recurrence);
      setSelectedDate(null);
      setSelectedContentId("");
      setRecurrence("none");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to schedule content.");
    }
  }

  async function handleReschedule(post: ScheduledPost, newDate: Date) {
    setError(null);
    try {
      await reschedule(post.id, newDate);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to reschedule.");
    }
  }

  async function confirmCancel() {
    if (!cancelTarget) return;
    try {
      await cancelSchedule(cancelTarget);
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to cancel.");
    } finally {
      setCancelTarget(null);
    }
  }

  return (
    <AppLayout>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Calendar</h1>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setMonthStart((d) => addMonths(d, -1))}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
          >
            Prev
          </button>
          <span className="text-sm text-slate-300">
            {monthStart.toLocaleString(undefined, { month: "long", year: "numeric" })}
          </span>
          <button
            onClick={() => setMonthStart((d) => addMonths(d, 1))}
            className="rounded-md border border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-800"
          >
            Next
          </button>
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-7 gap-1 text-xs text-slate-500">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
          <div key={d} className="px-2 py-1">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => {
          const inMonth = day.getMonth() === monthStart.getMonth();
          const postsToday = scheduled.filter((p) => sameDay(new Date(p.publish_at), day));
          return (
            <button
              key={day.toISOString()}
              onClick={() => setSelectedDate(day)}
              className={`min-h-24 rounded-md border p-2 text-left align-top ${
                inMonth ? "border-slate-800 bg-slate-900" : "border-slate-900 bg-slate-950 text-slate-600"
              } hover:border-indigo-500`}
            >
              <span className="text-xs">{day.getDate()}</span>
              <div className="mt-1 space-y-1">
                {postsToday.map((p) => (
                  <div
                    key={p.id}
                    className={`truncate rounded px-1.5 py-0.5 text-xs ${
                      p.status === "fired"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : p.status === "cancelled"
                        ? "bg-slate-700 text-slate-400 line-through"
                        : "bg-indigo-500/20 text-indigo-300"
                    }`}
                  >
                    {new Date(p.publish_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                    {p.recurrence !== "none" && ` (${p.recurrence})`}
                  </div>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {selectedDate && (
        <div className="mt-6 rounded-lg border border-slate-800 bg-slate-900 p-5">
          <h2 className="text-lg font-semibold">Schedule content for {selectedDate.toLocaleDateString()}</h2>

          <div className="mt-3 space-y-2">
            {scheduled
              .filter((p) => sameDay(new Date(p.publish_at), selectedDate))
              .map((p) => (
                <div key={p.id} className="flex items-center justify-between rounded-md border border-slate-800 p-3">
                  <div>
                    <p className="text-sm">Scheduled at {new Date(p.publish_at).toLocaleTimeString()}</p>
                    <p className="text-xs text-slate-500">status: {p.status}</p>
                  </div>
                  {p.status === "scheduled" && (
                    <div className="flex gap-3">
                      <button
                        onClick={() => {
                          const time = window.prompt("New time (HH:MM, 24h)");
                          if (!time) return;
                          const [h, m] = time.split(":").map(Number);
                          const newDate = new Date(selectedDate);
                          newDate.setHours(h || 0, m || 0);
                          handleReschedule(p, newDate);
                        }}
                        className="text-xs text-indigo-400 hover:underline"
                      >
                        Reschedule
                      </button>
                      <button onClick={() => setCancelTarget(p.id)} className="text-xs text-red-400 hover:underline">
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
              ))}
          </div>

          <form onSubmit={handleSchedule} className="mt-4 flex flex-wrap items-end gap-3">
            <select
              required
              value={selectedContentId}
              onChange={(e) => setSelectedContentId(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none"
            >
              <option value="">Choose content...</option>
              {drafts.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
            <select
              value={recurrence}
              onChange={(e) => setRecurrence(e.target.value)}
              className="rounded-md border border-slate-700 bg-slate-800 px-3 py-2 text-sm outline-none"
            >
              <option value="none">One-off</option>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
            <button className="rounded-md bg-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-400">
              Schedule (9am)
            </button>
          </form>
        </div>
      )}

      <ConfirmDialog
        open={cancelTarget !== null}
        title="Cancel scheduled post"
        message="This post will not be published at its scheduled time."
        confirmLabel="Cancel post"
        onConfirm={confirmCancel}
        onCancel={() => setCancelTarget(null)}
      />
    </AppLayout>
  );
}

function startOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth(), 1);
}
function endOfMonth(d: Date) {
  return new Date(d.getFullYear(), d.getMonth() + 1, 0, 23, 59, 59);
}
function addMonths(d: Date, n: number) {
  return new Date(d.getFullYear(), d.getMonth() + n, 1);
}
function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}
function buildMonthGrid(monthStart: Date): Date[] {
  const firstWeekday = monthStart.getDay();
  const gridStart = new Date(monthStart);
  gridStart.setDate(gridStart.getDate() - firstWeekday);

  return Array.from({ length: 42 }, (_, i) => {
    const day = new Date(gridStart);
    day.setDate(gridStart.getDate() + i);
    return day;
  });
}
