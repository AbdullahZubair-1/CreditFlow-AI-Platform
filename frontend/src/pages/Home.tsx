import { Link } from "react-router-dom";

export default function Home() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between px-8 py-6">
        <span className="text-xl font-semibold">CreditFlow</span>
        <nav className="flex items-center gap-4">
          <a href="#pricing" className="text-slate-300 hover:text-white">
            Pricing
          </a>
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

      <section id="pricing" className="mx-auto max-w-4xl px-8 pb-24">
        <h2 className="text-center text-2xl font-bold">Pricing</h2>
        <div className="mt-10 grid grid-cols-1 gap-8 sm:grid-cols-3">
          {[
            { name: "Free", price: "$0", tagline: "Try it out", credits: "No monthly credit grant" },
            { name: "Pro", price: "$19", tagline: "For solo creators", credits: "1,000 credits/month" },
            { name: "Team", price: "$49", tagline: "For teams", credits: "5,000 credits/month" },
          ].map((plan) => (
            <div key={plan.name} className="flex flex-col rounded-lg border border-slate-800 p-6 text-center">
              <h3 className="font-semibold">{plan.name}</h3>
              <p className="mt-2 text-3xl font-bold">
                {plan.price}
                <span className="text-sm font-normal text-slate-400">/mo</span>
              </p>
              <p className="mt-2 text-sm text-slate-400">{plan.tagline}</p>
              <p className="mt-4 text-sm text-slate-300">{plan.credits}</p>
              <Link
                to="/signup"
                className="mt-6 rounded-md border border-indigo-500 px-4 py-2 text-sm font-medium hover:bg-indigo-500"
              >
                Get started
              </Link>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
