import { useEffect, useMemo, useState } from "react";

import { ApiError } from "../api/client";
import { listContent, type Content } from "../api/content";
import { cancelSchedule, createSchedule, listScheduled, reschedule, type ScheduledPost } from "../api/scheduler";
import AppLayout from "../components/AppLayout";
import ConfirmDialog from "../components/ConfirmDialog";

// A lightweight custom month/week grid rather than pulling in
// FullCalendar/React Big Calendar (the spec's two suggested options) —
// avoids adding a new npm dependency that can't be installed-and-verified
// in this environment. Functionally equivalent for this scope: month and
// week views of scheduled posts with schedule/reschedule/cancel actions.
export default function CalendarScheduler() {
  const [viewMode, setViewMode] = useState<"month" | "week">("month");
  const [monthStart, setMonthStart] = useState(() => startOfMonth(new Date()));
  const [weekStart, setWeekStart] = useState(() => startOfWeek(new Date()));
  const [scheduled, setScheduled] = useState<ScheduledPost[]>([]);
  const [allContent, setAllContent] = useState<Content[]>([]);
  const [selectedDate, setSelectedDate] = useState<Date | null>(null);
  const [selectedContentId, setSelectedContentId] = useState("");
  const [scheduleTime, setScheduleTime] = useState("09:00");
  const [error, setError] = useState<string | null>(null);
  const [cancelTarget, setCancelTarget] = useState<string | null>(null);

  const rangeStart = viewMode === "month" ? monthStart : weekStart;
  const rangeEnd = useMemo(
    () => (viewMode === "month" ? endOfMonth(monthStart) : endOfWeek(weekStart)),
    [viewMode, monthStart, weekStart]
  );

  function refresh() {
    listScheduled(rangeStart, rangeEnd).then(setScheduled).catch(() => undefined);
  }

  useEffect(refresh, [viewMode, monthStart, weekStart]);
  useEffect(() => {
    listContent().then(setAllContent).catch(() => undefined);
  }, []);

  // Only approved content can actually be scheduled (enforced server-side
  // too, see Scheduler's POST /scheduled) — a draft shouldn't show up as a
  // schedulable option before someone's approved it in Content Studio.
  // Already-fired/published posts are excluded from this list but not
  // from contentById below, since the calendar still needs their title.
  const schedulableContent = useMemo(() => allContent.filter((c) => c.status === "approved"), [allContent]);
  const contentById = useMemo(() => new Map(allContent.map((c) => [c.id, c])), [allContent]);

  const days = useMemo(
    () => (viewMode === "month" ? buildMonthGrid(monthStart) : buildWeekGrid(weekStart)),
    [viewMode, monthStart, weekStart]
  );

  function goPrev() {
    if (viewMode === "month") setMonthStart((d) => addMonths(d, -1));
    else setWeekStart((d) => addDays(d, -7));
  }
  function goNext() {
    if (viewMode === "month") setMonthStart((d) => addMonths(d, 1));
    else setWeekStart((d) => addDays(d, 7));
  }

  async function handleSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedDate || !selectedContentId) return;
    setError(null);
    try {
      const [hours, minutes] = scheduleTime.split(":").map(Number);
      const publishAt = new Date(selectedDate);
      publishAt.setHours(hours || 0, minutes || 0, 0, 0);
      // The time input's min attribute only restricts today's date, and
      // isn't enforced consistently across every browser/input method
      // (e.g. typing digits directly) — this is the actual guarantee that
      // a schedule request is never sent for a moment that's already passed.
      if (publishAt.getTime() <= Date.now()) {
        setError("That time has already passed — choose a time in the future.");
        return;
      }
      await createSchedule(selectedContentId, publishAt, "none");
      setSelectedDate(null);
      setSelectedContentId("");
      setScheduleTime("09:00");
      refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to schedule content.");
    }
  }

  async function handleReschedule(post: ScheduledPost, newDate: Date) {
    setError(null);
    if (newDate.getTime() <= Date.now()) {
      setError("That time has already passed — choose a time in the future.");
      return;
    }
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
          <div className="flex rounded-md border border-slate-300 dark:border-slate-700 text-sm">
            <button
              onClick={() => setViewMode("month")}
              className={`px-3 py-1.5 ${viewMode === "month" ? "bg-brand-500 text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}
            >
              Month
            </button>
            <button
              onClick={() => setViewMode("week")}
              className={`px-3 py-1.5 ${viewMode === "week" ? "bg-brand-500 text-white" : "hover:bg-slate-100 dark:hover:bg-slate-800"}`}
            >
              Week
            </button>
          </div>
          <button onClick={goPrev} className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
            Prev
          </button>
          <span className="text-sm text-slate-600 dark:text-slate-300">
            {viewMode === "month"
              ? monthStart.toLocaleString(undefined, { month: "long", year: "numeric" })
              : `${weekStart.toLocaleDateString(undefined, { month: "short", day: "numeric" })} – ${endOfWeek(
                  weekStart
                ).toLocaleDateString(undefined, { month: "short", day: "numeric" })}`}
          </span>
          <button onClick={goNext} className="rounded-md border border-slate-300 dark:border-slate-700 px-3 py-1.5 text-sm hover:bg-slate-100 dark:hover:bg-slate-800">
            Next
          </button>
        </div>
      </div>

      {error && <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>}

      <div className="mt-6 grid grid-cols-7 gap-1 text-xs text-slate-500">
        {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
          <div key={d} className="px-2 py-1">
            {d}
          </div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {days.map((day) => {
          const inMonth = viewMode === "week" || day.getMonth() === monthStart.getMonth();
          const postsToday = scheduled.filter((p) => sameDay(new Date(p.publish_at), day));
          return (
            <button
              key={day.toISOString()}
              onClick={() => {
                setSelectedDate(day);
                setScheduleTime(sameDay(day, new Date()) ? nextValidTime() : "09:00");
              }}
              className={`min-h-24 rounded-md border p-2 text-left align-top ${
                inMonth ? "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900" : "border-slate-200 dark:border-slate-900 bg-white dark:bg-slate-950 text-slate-600"
              } hover:border-brand-500`}
            >
              <span className="text-xs">{day.getDate()}</span>
              <div className="mt-1 space-y-1">
                {postsToday.map((p) => (
                  <div
                    key={p.id}
                    title={contentById.get(p.content_id)?.title}
                    className={`truncate rounded px-1.5 py-0.5 text-xs ${
                      p.status === "fired"
                        ? "bg-emerald-500/20 text-emerald-300"
                        : p.status === "cancelled"
                        ? "bg-slate-200 dark:bg-slate-700 text-slate-500 dark:text-slate-400 line-through"
                        : "bg-brand-500/20 text-brand-300"
                    }`}
                  >
                    {new Date(p.publish_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}
                    {p.recurrence !== "none" && ` (${p.recurrence})`}
                    {contentById.get(p.content_id) && ` · ${contentById.get(p.content_id)!.title}`}
                  </div>
                ))}
              </div>
            </button>
          );
        })}
      </div>

      {selectedDate && (
        <div className="mt-6 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5">
          <h2 className="text-lg font-semibold">Schedule content for {selectedDate.toLocaleDateString()}</h2>

          <div className="mt-3 space-y-2">
            {scheduled
              .filter((p) => sameDay(new Date(p.publish_at), selectedDate))
              .map((p) => {
                const content = contentById.get(p.content_id);
                return (
                <div key={p.id} className="flex items-center justify-between rounded-md border border-slate-200 dark:border-slate-800 p-3">
                  <div>
                    <p className="text-sm font-medium">{content?.title ?? "(content unavailable)"}</p>
                    {content && <p className="mt-0.5 max-w-md truncate text-xs text-slate-500">{content.body}</p>}
                    <p className="mt-1 text-sm">Scheduled at {new Date(p.publish_at).toLocaleTimeString()}</p>
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
                        className="text-xs text-brand-600 dark:text-brand-400 hover:underline"
                      >
                        Reschedule
                      </button>
                      <button onClick={() => setCancelTarget(p.id)} className="text-xs text-red-600 dark:text-red-400 hover:underline">
                        Cancel
                      </button>
                    </div>
                  )}
                </div>
                );
              })}
          </div>

          {isPastDay(selectedDate) ? (
            <p className="mt-4 text-sm text-slate-500 dark:text-slate-400">
              This date is in the past — content can only be scheduled for today or a future date.
            </p>
          ) : (
          <form onSubmit={handleSchedule} className="mt-4 flex flex-wrap items-end gap-3">
            <div>
              <select
                required
                value={selectedContentId}
                onChange={(e) => setSelectedContentId(e.target.value)}
                className="rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
              >
                <option value="">Choose content...</option>
                {schedulableContent.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.title}
                  </option>
                ))}
              </select>
              {schedulableContent.length === 0 && (
                <p className="mt-1 text-xs text-slate-500">
                  No approved content yet — approve a draft in Content Studio first.
                </p>
              )}
            </div>
            <input
              type="time"
              required
              min={sameDay(selectedDate, new Date()) ? nextValidTime() : undefined}
              value={scheduleTime}
              onChange={(e) => setScheduleTime(e.target.value)}
              className="rounded-md border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 px-3 py-2 text-sm outline-none"
            />
            <button className="rounded-md bg-brand-500 px-4 py-2 text-sm font-medium hover:bg-brand-400">
              Schedule
            </button>
          </form>
          )}
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
function startOfWeek(d: Date) {
  const start = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  start.setDate(start.getDate() - start.getDay());
  return start;
}
function endOfWeek(d: Date) {
  const end = addDays(startOfWeek(d), 6);
  end.setHours(23, 59, 59);
  return end;
}
function addDays(d: Date, n: number) {
  const result = new Date(d);
  result.setDate(result.getDate() + n);
  return result;
}
function buildWeekGrid(weekStart: Date): Date[] {
  return Array.from({ length: 7 }, (_, i) => addDays(weekStart, i));
}
// Rounds up to the next 5-minute mark so "now" never lands exactly on the
// input's min value only to be immediately invalidated by the clock
// ticking forward a second later.
function nextValidTime(): string {
  const d = new Date();
  d.setMinutes(Math.ceil((d.getMinutes() + 1) / 5) * 5, 0, 0); // setMinutes(60, ...) correctly rolls over to the next hour
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

function isPastDay(day: Date): boolean {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const compareDay = new Date(day);
  compareDay.setHours(0, 0, 0, 0);
  return compareDay < today;
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
