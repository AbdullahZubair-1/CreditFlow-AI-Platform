import { Link } from "react-router-dom";

import Footer from "../components/Footer";
import ThemeToggle from "../components/ThemeToggle";
import { PLANS } from "../data/plans";

const ICON_PATHS: Record<string, string> = {
  content: "M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z",
  research: "M21 21l-4.35-4.35M11 19a8 8 0 100-16 8 8 0 000 16z",
  calendar: "M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z",
  linkedin: "M13 10V3L4 14h7v7l9-11h-7z",
  marketplace: "M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z",
  team: "M17 20h5v-2a4 4 0 00-3-3.87M9 20H4v-2a4 4 0 013-3.87m6-2.13a4 4 0 10-4-4 4 4 0 004 4zm6 0a4 4 0 10-4-4",
};

function FeatureIcon({ name }: { name: string }) {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.75} className="h-6 w-6">
      <path strokeLinecap="round" strokeLinejoin="round" d={ICON_PATHS[name]} />
    </svg>
  );
}

const FEATURES = [
  { title: "AI Content Studio", body: "Stream AI-generated posts token by token, with images generated to match.", icon: "content" },
  { title: "Automatic Web Research", body: "Optionally ground a post in real facts pulled in automatically — no URL needed.", icon: "research" },
  { title: "Calendar Scheduling", body: "Plan, reschedule, and recur posts on a visual calendar.", icon: "calendar" },
  { title: "LinkedIn Publishing", body: "Scheduled posts go out to LinkedIn automatically, images included.", icon: "linkedin" },
  { title: "Credits Marketplace", body: "Buy credits directly, or trade them peer-to-peer with other accounts.", icon: "marketplace" },
  { title: "Team Accounts", body: "Invite teammates by email with owner/admin/member roles.", icon: "team" },
];

const STEPS = [
  { step: "1", title: "Describe the post", body: "Give it a topic — optionally let it research the web first for facts to ground it in." },
  { step: "2", title: "Review and approve", body: "Watch it stream in live, edit if needed, then approve it for scheduling." },
  { step: "3", title: "Schedule and publish", body: "Pick a time on the calendar — it publishes to LinkedIn automatically, on your credits." },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col overflow-x-hidden bg-white text-slate-900 transition-colors duration-200 dark:bg-slate-950 dark:text-slate-100">
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-slate-200/70 bg-white/80 px-8 py-5 backdrop-blur-md transition-colors duration-200 dark:border-slate-800/70 dark:bg-slate-950/80">
        <span className="flex items-center gap-2 text-xl font-semibold">
          <img src="/logo-icon.png" alt="" className="h-8 w-8" />
          CreditFlow
        </span>
        <nav className="flex items-center gap-5">
          <a
            href="#features"
            className="hidden text-sm font-medium text-slate-600 transition-colors hover:text-slate-900 dark:text-slate-300 dark:hover:text-white sm:inline"
          >
            Features
          </a>
          <a
            href="#pricing"
            className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
          >
            Pricing
          </a>
          <Link
            to="/login"
            className="text-sm font-medium text-slate-600 transition-colors hover:text-slate-900 dark:text-slate-300 dark:hover:text-white"
          >
            Log in
          </Link>
          <Link
            to="/signup"
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-brand-500 hover:shadow-md"
          >
            Sign up
          </Link>
          <ThemeToggle />
        </nav>
      </header>

      <main className="relative isolate mx-auto max-w-4xl animate-fade-in px-8 py-24 text-center">
        {/* Soft brand-colored glow behind the hero — the same lime-to-teal
            hue sweep as the logo's own gradient, not a generic radial. */}
        <div
          aria-hidden
          className="absolute inset-x-0 -top-24 -z-10 h-[32rem] bg-[radial-gradient(ellipse_at_center,theme(colors.brand.400/0.25),transparent_65%)] blur-3xl dark:bg-[radial-gradient(ellipse_at_center,theme(colors.brand.500/0.2),transparent_65%)]"
        />
        <span className="inline-flex items-center gap-1.5 rounded-full border border-brand-200 bg-brand-50 px-3 py-1 text-xs font-medium text-brand-700 dark:border-brand-800 dark:bg-brand-500/10 dark:text-brand-300">
          <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
          AI-powered content, from prompt to published post
        </span>
        <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-6xl">
          AI content, scheduled and published{" "}
          <span className="bg-gradient-to-r from-brand-600 via-brand-500 to-brand-400 bg-clip-text text-transparent">
            on your credits.
          </span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600 dark:text-slate-400">
          Generate content with AI, optionally grounded in real web research, schedule it, publish to LinkedIn, and
          trade credits with other accounts on the marketplace.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <Link
            to="/signup"
            className="rounded-md bg-brand-600 px-6 py-3 font-medium text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-brand-500 hover:shadow-lg hover:shadow-brand-500/30"
          >
            Get started free
          </Link>
          <a
            href="#pricing"
            className="rounded-md border border-slate-300 px-6 py-3 font-medium text-slate-700 transition-colors duration-200 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-900"
          >
            See pricing
          </a>
        </div>
      </main>

      <section id="features" className="mx-auto grid max-w-5xl grid-cols-1 gap-6 px-8 pb-24 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="group rounded-xl border border-slate-200 bg-white p-6 text-left shadow-sm transition-all duration-200 hover:-translate-y-1 hover:border-brand-300 hover:shadow-lg hover:shadow-brand-500/10 dark:border-slate-800 dark:bg-slate-900 dark:hover:border-brand-700"
          >
            <span className="inline-flex h-11 w-11 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-sm">
              <FeatureIcon name={f.icon} />
            </span>
            <h3 className="mt-4 font-semibold">{f.title}</h3>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{f.body}</p>
          </div>
        ))}
      </section>

      <section className="border-y border-slate-200 bg-slate-50 transition-colors duration-200 dark:border-slate-800 dark:bg-slate-900/40">
        <div className="mx-auto max-w-4xl px-8 py-20">
          <h2 className="text-center text-2xl font-bold">How it works</h2>
          <div className="mt-12 grid grid-cols-1 gap-10 sm:grid-cols-3">
            {STEPS.map((s, i) => (
              <div key={s.step} className="relative text-center">
                <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-brand-600 text-sm font-bold text-white shadow-sm">
                  {s.step}
                </span>
                {i < STEPS.length - 1 && (
                  <span className="absolute left-[calc(50%+1.5rem)] top-5 hidden h-px w-[calc(100%-3rem)] bg-gradient-to-r from-brand-300 to-transparent dark:from-brand-800 sm:block" />
                )}
                <h3 className="mt-4 font-semibold">{s.title}</h3>
                <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{s.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section id="pricing" className="mx-auto max-w-4xl px-8 py-24">
        <h2 className="text-center text-2xl font-bold">Pricing</h2>
        <p className="mt-2 text-center text-sm text-slate-500 dark:text-slate-400">
          Every plan includes a free signup bonus of 50 credits to try things out.
        </p>
        <div className="mt-10 grid grid-cols-1 gap-8 sm:grid-cols-3">
          {PLANS.map((plan) => (
            <div
              key={plan.name}
              className={`relative flex flex-col rounded-xl border p-6 text-center shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-lg ${
                plan.highlight
                  ? "border-brand-400 bg-brand-50/50 shadow-brand-500/10 dark:border-brand-600 dark:bg-brand-500/10"
                  : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
              }`}
            >
              {plan.highlight && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-full bg-brand-600 px-3 py-0.5 text-xs font-medium text-white shadow-sm">
                  Most popular
                </span>
              )}
              <h3 className="font-semibold">{plan.name}</h3>
              <p className="mt-2 text-3xl font-bold">
                {plan.price}
                <span className="text-sm font-normal text-slate-500 dark:text-slate-400">/mo</span>
              </p>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{plan.tagline}</p>
              <p className="mt-4 text-sm font-medium text-slate-700 dark:text-slate-300">{plan.credits}</p>
              <ul className="mt-4 flex-1 space-y-1.5 text-left text-sm text-slate-600 dark:text-slate-400">
                {plan.features.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="mt-0.5 h-4 w-4 shrink-0 text-brand-500">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    {f}
                  </li>
                ))}
              </ul>
              <Link
                to="/signup"
                className={`mt-6 rounded-md px-4 py-2 text-sm font-medium transition-colors duration-200 ${
                  plan.highlight
                    ? "bg-brand-600 text-white hover:bg-brand-500"
                    : "border border-brand-500 text-brand-600 hover:bg-brand-500 hover:text-white dark:text-brand-400"
                }`}
              >
                Get started
              </Link>
            </div>
          ))}
        </div>
      </section>

      <Footer />
    </div>
  );
}
