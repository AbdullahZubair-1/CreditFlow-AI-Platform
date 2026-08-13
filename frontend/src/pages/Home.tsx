import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between px-8 py-6">
        <span className="text-xl font-semibold">CreditFlow</span>
        <nav className="flex gap-4">
          <Link to="/login" className="text-slate-300 hover:text-white">
            Log in
          </Link>
          <Link to="/signup" className="rounded-md bg-indigo-500 px-4 py-2 font-medium hover:bg-indigo-400">
            Sign up
          </Link>
        </nav>
      </header>

      <main className="mx-auto max-w-4xl px-8 py-24 text-center">
        <h1 className="text-4xl font-bold sm:text-5xl">AI content, scheduled and published — on your credits.</h1>
        <p className="mt-6 text-lg text-slate-400">
          Generate content with AI, schedule it, publish to LinkedIn, and trade credits with other
          accounts on the marketplace.
        </p>
        <Link
          to="/signup"
          className="mt-10 inline-block rounded-md bg-indigo-500 px-6 py-3 font-medium hover:bg-indigo-400"
        >
          Get started free
        </Link>
      </main>

      <section className="mx-auto max-w-4xl grid grid-cols-1 gap-8 px-8 pb-24 sm:grid-cols-3">
        {[
          { title: "AI Content Studio", body: "Stream AI-generated posts token by token." },
          { title: "Calendar Scheduling", body: "Plan and reschedule posts on a visual calendar." },
          { title: "Credits Marketplace", body: "Buy, sell, and transfer credits with other accounts." },
        ].map((f) => (
          <div key={f.title} className="rounded-lg border border-slate-800 p-6">
            <h3 className="font-semibold">{f.title}</h3>
            <p className="mt-2 text-sm text-slate-400">{f.body}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
