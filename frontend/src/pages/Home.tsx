import { Link } from "react-router-dom";

import Footer from "../components/Footer";
import ThemeToggle from "../components/ThemeToggle";

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900 transition-colors duration-200 dark:bg-slate-950 dark:text-slate-100">
      <header className="flex items-center justify-between px-8 py-6">
        <span className="flex items-center gap-2 text-xl font-semibold">
          <img src="/logo-icon.png" alt="" className="h-8 w-8" />
          CreditFlow
        </span>
        <nav className="flex items-center gap-5">
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
            className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-indigo-500 hover:shadow-md"
          >
            Sign up
          </Link>
          <ThemeToggle />
        </nav>
      </header>

      <main className="mx-auto max-w-4xl animate-fade-in px-8 py-24 text-center">
        <span className="inline-block rounded-full bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 dark:bg-indigo-500/10 dark:text-indigo-300">
          AI-powered content, from prompt to published post
        </span>
        <h1 className="mt-6 text-4xl font-bold tracking-tight sm:text-5xl">
          AI content, scheduled and published on your credits.
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-slate-600 dark:text-slate-400">
          Generate content with AI, schedule it, publish to LinkedIn, and trade credits with other accounts on the
          marketplace.
        </p>
        <div className="mt-10 flex items-center justify-center gap-4">
          <Link
            to="/signup"
            className="rounded-md bg-indigo-600 px-6 py-3 font-medium text-white shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:bg-indigo-500 hover:shadow-lg"
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

      <section className="mx-auto grid max-w-4xl grid-cols-1 gap-8 px-8 pb-24 sm:grid-cols-3">
        {[
          { title: "AI Content Studio", body: "Stream AI-generated posts token by token.", icon: "✨" },
          { title: "Calendar Scheduling", body: "Plan and reschedule posts on a visual calendar.", icon: "📅" },
          { title: "Credits Marketplace", body: "Buy, sell, and transfer credits with other accounts.", icon: "🔄" },
        ].map((f) => (
          <div
            key={f.title}
            className="group rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-md dark:border-slate-800 dark:bg-slate-900"
          >
            <span className="text-2xl">{f.icon}</span>
            <h3 className="mt-3 font-semibold">{f.title}</h3>
            <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{f.body}</p>
          </div>
        ))}
      </section>

      <section id="pricing" className="mx-auto max-w-4xl px-8 pb-24">
        <h2 className="text-center text-2xl font-bold">Pricing</h2>
        <p className="mt-2 text-center text-sm text-slate-500 dark:text-slate-400">
          Every plan includes a free signup bonus of 50 credits to try things out.
        </p>
        <div className="mt-10 grid grid-cols-1 gap-8 sm:grid-cols-3">
          {[
            { name: "Free", price: "$0", tagline: "Try it out", credits: "50 signup bonus credits" },
            { name: "Pro", price: "$19", tagline: "For solo creators", credits: "1,000 credits/month" },
            { name: "Team", price: "$49", tagline: "For teams", credits: "5,000 credits/month", highlight: true },
          ].map((plan) => (
            <div
              key={plan.name}
              className={`flex flex-col rounded-xl border p-6 text-center shadow-sm transition-all duration-200 hover:-translate-y-1 hover:shadow-md ${
                plan.highlight
                  ? "border-indigo-300 bg-indigo-50/50 dark:border-indigo-700 dark:bg-indigo-500/10"
                  : "border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
              }`}
            >
              <h3 className="font-semibold">{plan.name}</h3>
              <p className="mt-2 text-3xl font-bold">
                {plan.price}
                <span className="text-sm font-normal text-slate-500 dark:text-slate-400">/mo</span>
              </p>
              <p className="mt-2 text-sm text-slate-500 dark:text-slate-400">{plan.tagline}</p>
              <p className="mt-4 text-sm text-slate-700 dark:text-slate-300">{plan.credits}</p>
              <Link
                to="/signup"
                className="mt-6 rounded-md border border-indigo-500 px-4 py-2 text-sm font-medium text-indigo-600 transition-colors duration-200 hover:bg-indigo-500 hover:text-slate-900 dark:hover:text-white dark:text-indigo-400"
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
