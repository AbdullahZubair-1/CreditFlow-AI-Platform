# CreditFlow AI Platform

A credit-based SaaS platform where teams generate AI content and publish it straight to LinkedIn — with billing, scheduling, and a web scraper built in.

For a deep technical dive (per-service architecture, every bug found and fixed, verification steps), see [ARCHITECTURE.md](ARCHITECTURE.md).

## What it does

- **AI content generation** — write posts with AI (streamed live as it types), plus AI-generated images. Optionally pulls in automatic web research on a topic before writing, no URL needed.
- **Credits & billing** — Free/Pro/Team plans via Stripe, a credit ledger, a peer-to-peer credits marketplace, and refunds (7-day window, 95% back) — with an email for every one of these: receipts, refunds, marketplace sales/purchases.
- **Teams** — multi-account support, roles (owner/admin/member), invite-by-email.
- **Scheduling & publishing** — plan posts on a calendar (showing what's actually scheduled, not just when) and auto-publish them to LinkedIn, including images.
- **Web scraper** — a backend service for pulling content from any URL, one-off or on a recurring schedule; also powers the AI content generator's automatic research.
- **Admin console** — a platform-wide SuperAdmin view: every account, every user, revenue, live sessions, audit log — in its own dedicated interface, separate from the regular team dashboard.
- **Email notifications** — verification, invites, receipts, refunds, and alerts, sent for real (only logging in with a verified email is allowed).

## Tech stack

| Layer | Technology |
|---|---|
| Backend | 13 independent FastAPI microservices behind one API Gateway |
| Frontend | React + Vite + Tailwind |
| Database | PostgreSQL (one schema per service) + MongoDB (scraper only) |
| Messaging | RabbitMQ |
| Cache / sessions | Redis |
| AI | Groq (chat) + Pollinations.ai (images) |
| Payments | Stripe |
| Email | SMTP (e.g. Gmail) |
| Deployment | Docker Compose behind nginx, tunneled publicly via ngrok |

## Quick start

1. **Copy the environment file:**
   ```
   cp .env.example .env
   ```
2. **Fill in `.env`** — at minimum you'll need a JWT keypair (instructions in the file) to sign in at all. Everything else (Stripe, Groq, LinkedIn, SMTP, ngrok) has a safe placeholder and can be added later as you need each feature.
3. **Start everything:**
   ```
   docker-compose up --build
   ```
4. **Open the app:**

   | What | URL |
   |---|---|
   | App | http://localhost:5173 |
   | API | http://localhost:8080 |
   | RabbitMQ dashboard | http://localhost:15672 (guest/guest) |
   | Public tunnel info | http://localhost:4040 |

That's it — sign up in the browser, verify your email (required before you can log in), and you're in. Postgres, Redis, RabbitMQ, and MongoDB all run in Docker too, so there's nothing to install separately.

## Going public (LinkedIn login, Stripe webhooks)

LinkedIn's login flow and Stripe's webhooks both need a real internet address to call back to — `localhost` won't work for them. This repo already runs everything behind **ngrok**, so once you add a free ngrok account's token and static domain to `.env`, the app is reachable at a real `https://` URL automatically (shown at http://localhost:4040). You'll also need to register that same URL as the redirect address in your LinkedIn Developer App settings.

## Project layout

```
services/       13 backend microservices (one folder each)
frontend/       React app
libs/py-shared/ shared code every backend service uses (JWT, messaging, errors)
nginx/          reverse proxy config
docker-compose.yml
.env.example
```

## Status

Every service in the spec is built and working, plus a few bonus features (AI images, image publishing, recurring schedules, a credits marketplace). See [ARCHITECTURE.md](ARCHITECTURE.md) for the full list and the reasoning behind every design choice.
