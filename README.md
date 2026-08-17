# CreditFlow AI Platform

Multi-tenant, credit-based SaaS platform for AI-assisted content generation and social publishing, built as independently deployable FastAPI microservices behind a single API Gateway, communicating over RabbitMQ, with Redis for caching/session state/rate limiting and a shared Postgres instance (one schema per service).

This repo is being built incrementally, slice by slice, rather than all 13 services at once.

- **Slice 1**: signup → email verification → login → JWT issuance → account creation → account switcher, through the Gateway, consumed by a minimal React frontend.
- **Slice 2**: Billing Service — Stripe sandbox subscriptions/checkout/refunds via the transactional outbox pattern, with the Gateway now doing real Stripe webhook verification + relay instead of a 501 stub.
- **Slice 3**: Credits/Marketplace Service — append-only credits ledger, credit grants on `invoice.paid`, refund clawbacks, and peer-to-peer marketplace listing/purchase settled through a one-time Stripe Checkout Session that Billing creates on Credits' behalf.
- **Slice 4**: Usage/Metering Service — Redis quota counters for fast pre-checks, a durable Postgres usage ledger reconciled against Redis every minute, and 80%/100% threshold detection. Introduces the `ai_events` exchange that the (not-yet-built) AI Generation Service will publish to.
- **Slice 5**: AI Generation Service — Groq streaming completions (the spec names OpenRouter; this project uses Groq instead, same OpenAI-compatible shape) fanned out over Redis pub/sub, re-streamed to the frontend as SSE through the Gateway (now a real relay instead of a 501 stub), gated by a synchronous call to Usage's precheck endpoint, plus bonus Pollinations.ai image generation.
- **Slice 6**: Content Service — versioned draft/approved/published content, auto-created from `ai.generation_completed` (finally closing the loop AI Generation's events opened), manual image upload to a local-volume dev stand-in for S3.
- **Slice 7**: Scheduler Service — Celery + Celery Beat calendar (three containers: REST API, worker, beat, sharing one image), a Redis-locked periodic scan that fires due posts and emits `content.scheduled`, plus the bonus recurring-schedules feature (daily/weekly/monthly cadences).
- **Slice 8**: Social Publishing Service — LinkedIn OAuth 2.0/OIDC connect flow, encrypted token storage, consumes `content.scheduled` to publish text or text+image UGC posts (the bonus image-publishing feature), a token-refresh background job, and Gateway support for a truly public OAuth callback route.
- **Slice 9**: Scraper Service — the first MongoDB-backed service, Playwright-driven crawling with robots.txt compliance and per-domain rate limiting, an internal (non-Celery) recurring-scan loop, RabbitMQ job queue (`scrape.requested` → `scrape.completed`/`scrape.failed`).
- **Slice 10**: Notification Service — consumes nearly every domain event across the platform (across four separate exchanges) to send real transactional email via Resend, finally replacing the dev-only OTP/verification-token logging from Slice 1. Also fixes a real security gap found while wiring this up: the Gateway's catch-all proxy routes would have happily forwarded a public request straight through to any service's new internal-only `/internal/*` endpoints.
- **Slice 11** (this pass, final backend service): Admin/Ops Service — live Redis session listing/revocation, a cross-service per-account overview, and an audit log consuming literally every exchange in the platform (topic-bound `#`). Introduces a genuine platform-level SuperAdmin concept (a new JWT claim, independent of the account-scoped `role` every other service already used) and four small `/internal/*` aggregation endpoints on other services to support it.

## Architecture

```
frontend (React + Vite + Tailwind, :5173)
   │  REST
   ▼
gateway (FastAPI, :8080)  ── JWT verification, Redis rate limiting, proxies to:
   │                          - /auth/*                          -> auth service
   │                          - /me/*, /accounts/*, /invites/*    -> user-tenant service
   │                          - /billing/*                        -> billing service
   │                          - /credits/*                        -> credits service
   │                          - /usage/*                          -> usage service
   │                          - /generations, /models              -> ai-generation service
   │                          - /content/*                         -> content service
   │                          - /uploads/*                         -> content service (static files,
   │                                                                 unauthenticated, same trust level
   │                                                                 as Pollinations image URLs)
   │                          - /scheduled, /scheduled/*            -> scheduler service
   │                          - /social/linkedin/connect,
   │                            /social/connections,
   │                            /social/publish-jobs                -> social-publishing service (protected)
   │                          - /social/linkedin/callback            -> social-publishing service (PUBLIC —
   │                                                                 LinkedIn's browser redirect can't carry
   │                                                                 our Authorization header)
   │                          - /scrape-jobs, /scraped-documents/*   -> scraper service
   │                          - /admin/*                             -> admin service
   │                          - every catch-all proxy rejects any /internal/* path with 404,
   │                            regardless of destination service (see _reject_internal_paths)
   │                          - /sse/{job_id}                      -> subscribes to the same Redis
   │                                                                 pub/sub channel ai-generation
   │                                                                 publishes to, re-streams as SSE
   │                          - /webhooks/stripe                  -> verifies signature, dedups via
   │                                                                 Redis SETNX, relays to RabbitMQ
   │                          - /webhooks/linkedin, /webhooks/groq -> 501 stubs (the Groq one stays
   │                                                                 permanent — chat completions have no
   │                                                                 webhook delivery model to receive from)
   ├─► auth (FastAPI, :8001)        — users, credentials, refresh_tokens,
   │      email_verification_tokens, password_reset_tokens (schema: auth)
   │      publishes: user.registered, user.logged_in, user.password_reset_requested
   │
   ├─► user-tenant (FastAPI, :8002) — accounts, account_members, invites,
   │      processed_events (schema: usertenant)
   │      consumes: user.registered  →  creates an individual Account + owner membership
   │      publishes: account.created, member.joined
   │
   ├─► billing (FastAPI, :8003) — billing_accounts, subscriptions, invoices, refunds,
   │      outbox_events, subscription_events, processed_events (schema: billing)
   │      consumes: account.created (creates Stripe Customer + free-tier Subscription row)
   │                billing.# (all Stripe webhook events, relayed by the Gateway)
   │      publishes (via transactional outbox): invoice.paid, payment.failed,
   │                subscription.updated, refund.issued, marketplace.payment_completed
   │      also exposes POST /checkout-sessions/one-time — an internal, non-Gateway-fronted
   │      endpoint Credits calls directly to charge a buyer for a marketplace purchase,
   │      since only Billing holds Stripe customer/credential context
   │
   ├─► credits (FastAPI, :8004) — credits_ledger, marketplace_listings, processed_events
   │      (schema: credits)
   │      consumes: invoice.paid (grants credits per plan_tier), refund.issued (claws
   │                back the matching grant), marketplace.payment_completed (settles a
   │                marketplace sale — debits seller, credits buyer, atomically)
   │      publishes: credits.credited, credits.debited, credits.low_balance
   │
   └─► usage (FastAPI, :8005) — usage_ledger, account_plans, threshold_flags,
          processed_events (schema: usage); Redis db 1 (separate from the Gateway/
          Auth's db 0) holds the live per-account monthly token counters
          consumes: ai.generation_completed (from the ai_events exchange — not
                    published by anything yet; AI Generation, a later slice, will
                    be the producer), subscription.updated (caches plan_tier locally
                    so the hot precheck path never makes a live cross-service call)
          publishes: usage.threshold_reached (once per account/period/threshold,
                    guarded by threshold_flags)
          exposes: POST /usage/precheck — the synchronous quota check the AI
                    Generation Service will call before every generation

   └─► ai-generation (FastAPI, :8006) — generation_jobs, prompt_history,
          image_generation_jobs (bonus) (schema: ai_generation)
          calls Usage's /precheck synchronously before accepting a generation request,
          then Groq's streaming chat completions endpoint
          publishes each token chunk to Redis pub/sub (channel `generation:{job_id}`)
          for the Gateway's /sse/{job_id} to re-stream to the frontend
          publishes (best-effort, not outboxed): ai.generation_completed, ai.generation_failed
          consumes: none

   └─► content (FastAPI, :8007) — content, content_versions, processed_events (schema: content);
          manually uploaded images land on a local Docker volume, served back via a
          StaticFiles mount — a dev stand-in for S3
          consumes: ai.generation_completed (only "post"-purpose ones) → creates a draft
                    Content row + its first ContentVersion snapshot
          publishes: content.created, content.updated

   └─► scheduler — three containers sharing one image (schema: scheduler):
          scheduler (FastAPI, :8008, calendar REST API)
          scheduler-worker (Celery worker)
          scheduler-beat (Celery Beat, scans scheduled_posts every 60s)
          Celery broker + result backend: Redis db 2 (separate from Gateway/Auth's
          db 0 and Usage's db 1)
          consumes: content.created (into a local available_content cache, so
                    scheduling validates a content_id without a live cross-service call)
          publishes: content.scheduled — deliberately NOT best-effort (see notes below)

   └─► social-publishing (FastAPI, :8009) — social_connections (Fernet-encrypted tokens),
          publish_jobs, post_media, processed_events (schema: social_publishing)
          consumes: content.scheduled → fetches the post from Content, uploads its
                    image via LinkedIn's Assets API if present, publishes a UGC post
          publishes: post.published, post.failed
          background job: refreshes LinkedIn access tokens ahead of expiry

   └─► scraper (FastAPI, :8010) — MongoDB only, no Postgres schema at all:
          collections scrape_jobs, scraped_documents, processed_events
          consumes: scrape.requested (published by this service's own REST endpoint,
                    and by its internal recurring-job loop)
          publishes: scrape.completed, scrape.failed
          background job: an internal asyncio loop (not the Scheduler Service's Celery
                    Beat) re-triggers daily/weekly recurring scrape jobs

   └─► notification (FastAPI, :8011) — notification_log, processed_events (schema:
          notification); mostly a consumer, minimal REST surface (just /healthz),
          per the spec
          consumes across FOUR separate exchanges:
            user_events: user.registered (verification email)
            domain_events: invite.created, member.joined, usage.threshold_reached
            billing_events: invoice.paid, payment.failed
            social_events: post.published, post.failed
          publishes: notification.sent
          calls Auth's and User/Tenant's new /internal/* endpoints directly
          (service-to-service) to resolve an email address from a user_id or account_id —
          most of these events don't carry an email address themselves
          optional: posts payment.failed/post.failed as Slack ops alerts (logs instead
          if SLACK_WEBHOOK_URL is unset)

   └─► admin (FastAPI, :8012) — audit_log, processed_events (schema: admin); owns no
          other domain data — everything else is a live read of Redis or another
          service's new /internal/* endpoint
          consumes: every event on every exchange in the platform (topic-bound #) →
                    one audit_log row per event, regardless of source
          publishes: none
          reads directly: Redis (jti:* session keys — "sourced live from Redis" per
                    the spec, no local mirror), User/Tenant's, Billing's, Credits', and
                    Usage's new /internal/* endpoints for the per-account overview

Infra: postgres (:5432, one instance/many schemas — runs natively on the host, not in Docker;
       see "Local setup"), redis (:6379), rabbitmq (:5672, mgmt UI :15672), mongo (:27017, Scraper
       Service only)
```

### Billing Service notes

- **Transactional Outbox**: every domain-event-worthy DB write (invoice recorded, subscription updated, refund issued) inserts an `outbox_events` row in the *same transaction*. A background poller (`app/outbox.py`, started in `main.py`'s lifespan) picks up unpublished rows every 2s, publishes them to the `billing_events` exchange with publisher confirms, and marks them published — so a crash between the DB write and the publish can never lose or double-emit an event.
- **Webhook flow**: the Gateway verifies the Stripe signature, deduplicates by Stripe event id (Redis `SETNX`, 24h TTL), and relays the raw event onto a `webhook_events` topic exchange with routing key `billing.<stripe event type>`. Billing consumes `billing.#`, persists every event to `subscription_events` *before* any further processing (per the reliability requirements), then updates `invoices`/`subscriptions` accordingly.
- **Stripe credentials are placeholders** (`sk_test_placeholder`, `price_pro_placeholder`, `price_team_placeholder`, `whsec_placeholder` in `.env`/`.env.example`) — the checkout/webhook code paths are fully wired but will only actually reach Stripe once you drop in real test-mode keys and Price IDs from your own Stripe sandbox account, and register a webhook endpoint (or run `stripe listen --forward-to localhost:8080/webhooks/stripe`) to get a matching `STRIPE_WEBHOOK_SECRET`.
- **Dunning is partially implemented**: `invoice.payment_failed` records a `grace_period_ends_at` on the subscription row and emits `payment.failed`, but automatically emitting `subscription.downgraded` once the grace period elapses needs a periodic scanner — that arrives with the Scheduler Service slice (Celery Beat). Until then the deadline is visible via `GET /billing/subscription`.

### Credits/Marketplace Service notes

- **Ledger is append-only**: `credits_ledger` rows are never updated or deleted; each row's `balance_after` is the running balance, computed once at write time from the previous row rather than a separately-mutated counter.
- **Credit grants**: consuming `invoice.paid` looks up `PLAN_CREDIT_GRANTS` (placeholder: `pro`→1000, `team`→5000, `free`→0) by the `plan_tier` Billing includes in that event's payload, and appends a `purchase_grant` ledger row. `refund.issued` claws back the same amount (capped at the current balance, so a refund can never take an account negative if the credits were already spent — a documented simplification rather than a hard error).
- **Marketplace settlement flow**: an account lists surplus credits (`POST /credits/marketplace/listings`, balance-checked but not locked — a known race-condition simplification noted in the code); a buyer calls `POST /credits/marketplace/listings/{id}/purchase`, which has Credits call **Billing directly** (service-to-service, bypassing the Gateway) at `POST /checkout-sessions/one-time` to create a real one-time Stripe Checkout Session for the listing price, tagged with metadata identifying the listing/buyer/seller. Billing's webhook consumer recognizes `checkout.session.completed` events carrying that metadata and emits a `marketplace.payment_completed` domain event (via its outbox) instead of treating it as a subscription event; Credits consumes that to atomically debit the seller and credit the buyer in one transaction, guarded by the listing's `pending_payment`→`sold` status transition so a duplicate webhook redelivery is a no-op.
- **No real payout to the seller**: the buyer's payment is real (Stripe Checkout, test mode), but nothing here transfers money to the seller's bank account — that needs Stripe Connect (connected accounts + transfers), which is out of scope for this slice's placeholder Stripe setup. The seller's ledger is credited with platform credits, not cash; documented here the same way the dunning-downgrade gap is in Billing.
- **Event publishing here is best-effort, not outboxed**: unlike Billing, Credits publishes `credits.credited`/`credits.debited`/`credits.low_balance` directly after committing the ledger write, with a try/except that logs and moves on if RabbitMQ is unreachable. The spec's Transactional Outbox requirement is scoped explicitly to the Billing Service; the ledger write itself (the source of truth) is still fully committed and correct even if a notification is dropped.
- **Found and fixed while building this slice**: the Gateway's Stripe webhook relay and Billing's webhook queue binding originally used the AMQP topic pattern `billing.*`, which only matches a routing key with exactly one word after `billing.` — but Stripe event types are themselves dot-separated (`invoice.paid`, `checkout.session.completed`), so the actual relayed keys have 2-3 segments and `billing.*` was silently matching **nothing**. Fixed to `billing.#` (matches zero or more words) in both places.

### Usage/Metering Service notes

- **Quota model is a placeholder**: per-plan-tier *monthly token* quotas (`PLAN_TOKEN_QUOTAS`: free 50k, pro 500k, team 2M) are tracked independently of the Credits Service's credit balance — Usage meters volume/rate, Credits meters spend. Whether these two should eventually be unified (e.g. quota derived from remaining credit balance instead of a separate token budget) is a product decision left open for a later pass.
- **Two data stores, reconciled**: Redis (db 1, separate from the Gateway/Auth's rate-limit/jti Redis usage on db 0) holds the live per-account-per-month token counter that `POST /usage/precheck` reads synchronously; Postgres's `usage_ledger` is the durable, append-only source of truth written when `ai.generation_completed` is consumed. A background loop (`app/reconciliation.py`) recomputes each active account's Redis counter from the Postgres ledger every 60s, so a crash between the ledger write and the Redis increment self-heals within one interval rather than drifting forever.
- **This slice has no producer yet**: it consumes from a new `ai_events` exchange (routing key `ai.generation_completed`) that nothing publishes to until the AI Generation Service slice exists — the consumer, queue, and DLX are all live and correctly bound, just idle. `subscription.updated` (from Billing's existing outbox) already has a real producer, so the plan-tier cache populates correctly today.
- **Threshold detection is idempotent per period**: crossing 80% or 100% of quota emits `usage.threshold_reached` exactly once per `(account_id, period, threshold)` via a unique-constrained `threshold_flags` table — redelivery of the same `ai.generation_completed` event (caught earlier by the standard `processed_events` idempotency check) can't double-fire it, and neither can two generation calls in the same period that both push usage past 80%.

### AI Generation Service notes

- **Groq instead of OpenRouter**: the platform spec names OpenRouter as the text AI provider; this project uses [Groq](https://console.groq.com) instead — same OpenAI-compatible streaming chat completions shape, just a different host, key, and model catalog (Groq's is also known for very fast inference). A real key from [console.groq.com/keys](https://console.groq.com/keys) is needed to actually reach a model; the placeholder (`gsk_placeholder`) lets the service boot and fail gracefully instead. Two model choices are pre-configured (`fast` → Llama 3.1 8B Instant, `quality` → Llama 3.3 70B Versatile) and selectable by key name (`"fast"`/`"quality"`) rather than a raw Groq model slug, so the frontend never has to know the underlying slug.
- **Streaming path**: `POST /generations` synchronously calls Usage's `/precheck` first (rejecting with `429 quota_exceeded` if over quota), then creates a `generation_jobs` row and kicks off a FastAPI `BackgroundTask` that streams from Groq, publishing each token to a Redis pub/sub channel (`generation:{job_id}`) as it arrives. The Gateway's `/sse/{job_id}` subscribes to that same channel and re-streams it to the browser as Server-Sent Events — the Gateway never talks to Groq directly, it's a pure relay.
- **EventSource can't set headers**: browsers' native `EventSource` API has no way to attach an `Authorization` header, so `/sse/{job_id}` is the one Gateway route that also accepts the access token via `?access_token=` query string (see `require_jwt_from_header_or_query` in `services/gateway/app/identity.py`) — every other protected route still requires the header only. The Gateway also confirms the caller actually owns the job (via AI Generation's existing per-account-scoped `GET /generations/{job_id}`) before subscribing, even though `job_id` is an unguessable UUID.
- **Known race, not fully solved**: a generation's background task can in principle start publishing tokens before the frontend's SSE `EventSource` has finished subscribing, since Redis pub/sub delivers only to subscribers already attached with no replay buffer. In practice Groq's network round-trip (Groq is fast, so this window is narrow) means this hasn't been observed to matter, but it's a real gap, not a proven-safe design — a fix (e.g. buffering early tokens in a short-lived Redis list until first subscriber attaches) is a candidate fast-follow if it turns out to matter.
- **Cancellation** is cooperative: `POST /generations/{job_id}/cancel` just sets a Redis flag; the streaming loop checks it between chunks and stops, persisting whatever partial response had accumulated with `status=cancelled`. There's necessarily a small window where a chunk already in flight from Groq still gets published after cancellation is requested.
- **Bonus image generation**: `POST /generations/{job_id}/image` hotlinks a Pollinations.ai URL (no API key, no upload step) rather than downloading and re-hosting the image — the Content Service (a later slice) will decide whether to keep hotlinking or mirror images into object storage.
- **Placeholder pricing**: `cost_cents` is a flat illustrative 1¢ per 100 tokens (`CENTS_PER_100_TOKENS` in `app/generation.py`) — Groq's real per-model rates vary widely and aren't wired up, same treatment as Billing's plan prices and Credits' grant amounts.
- **Event publishing here is best-effort, not outboxed** — same tradeoff as Credits: the `generation_jobs`/`prompt_history` rows are the committed source of truth; a dropped `ai.generation_completed` publish just delays Usage's ledger entry for that call rather than losing anything permanently.

### Content Service notes

- **`purpose` and `response_text` were added to `ai.generation_completed` retroactively**: Slice 4 (Usage) and Slice 5 (AI Generation) shipped before Content existed, and Content needs the actual generated text plus a way to tell "this was meant to become a post" apart from other future generation purposes (ad-hoc chat, etc.) — neither was in the original event payload. `CreateGenerationRequest.purpose` (default `"post"`) and the full `response_text` were added to AI Generation's request schema, `GenerationJob` model, and completed-event payload; Usage's existing consumer ignores the new fields harmlessly (additive, non-breaking).
- **Versioning is append-only**: every edit (including image uploads) increments `content.version` and inserts a new `content_versions` snapshot rather than mutating history — `GET /content/{id}/versions` returns the full timeline.
- **Publish permission is role-gated**: only `owner`/`admin` can move content between `draft`→`approved`→`published` (and back to `draft`); any member can create/edit drafts. The allowed-transition table (`draft→approved`, `approved→published`, `approved→draft`, `published→draft`) is enforced server-side in `app/api/routes.py`, not just hinted at by the frontend.
- **Local-volume "object storage"**: `POST /content/{id}/image` (multipart) writes to a Docker volume mounted at `/app/uploads` and serves it back at `/uploads/{filename}` via a `StaticFiles` mount — explicitly a dev stand-in for S3 (see `app/storage.py`'s docstring); swapping in real S3 later only touches that one file.
- **Draft creation is idempotent by construction**: the `ai.generation_completed` consumer checks for an existing `Content` row with the same `source_generation_job_id` before creating one, on top of the standard `processed_events` idempotency check — belt-and-suspenders against redelivery.
- **AI-generated images aren't wired into Content yet**: AI Generation's bonus `POST /generations/{job_id}/image` (Slice 5) produces a Pollinations.ai URL but nothing currently attaches it to the Content record that same generation created — a manual `PATCH /content/{id}` with that URL works today; auto-attaching it is a small fast-follow, not yet done.

### Scheduler Service notes

- **Three containers, one image**: `scheduler` (the REST/calendar API), `scheduler-worker` (a Celery worker), and `scheduler-beat` (Celery Beat, which enqueues a scan task every 60s per `settings.beat_scan_interval_seconds`) all build from `services/scheduler/Dockerfile` — only the `command:` differs per container in `docker-compose.yml`. Celery's broker and result backend are Redis db 2, kept separate from the Gateway/Auth/AI-Generation's db 0 and Usage's db 1, per the spec's explicit call-out for this service.
- **Recurring schedules (bonus)**: `recurrence` is one of `none`/`daily`/`weekly`/`monthly`. A recurring post's `publish_at` advances by a fixed `timedelta` (`RECURRENCE_DELTAS` in `app/tasks.py`) each time it fires and stays `status=scheduled` for its next occurrence, rather than moving to `fired` like a one-off. `monthly` is a placeholder 30-day interval, not calendar-month-accurate (no Feb-28-vs-31st handling) — good enough to demonstrate the feature, not production calendar math.
- **Double-fire protection**: before firing, the task tries a Redis `SET NX EX` lock keyed on `(scheduled_post_id, publish_at)` with a 55s TTL — shorter than the 60s scan interval, so a lock can never outlive the window where the next scan would need it. This protects against both an overlapping slow scan and, if ever scaled beyond one, multiple beat/worker replicas.
- **`content.scheduled` publish failures are NOT swallowed here** — a deliberate exception to this codebase's usual "best-effort, log and continue" pattern for non-Billing event publishing (see Credits/AI Generation/Content's notes above). If the publish raises, `app/tasks.py` never commits the "fired" state change; the occurrence stays `status=scheduled` and gets retried on the next scan once the lock expires. Losing this specific event would mean a post silently never reaches Social Publishing, which is worse than a delayed retry.
- **Content ownership cache, not a live check**: `POST /scheduled` validates `content_id` against a local `available_content` table populated by consuming `content.created`, rather than calling the Content Service directly — matches the spec's framing that Scheduler "knows what is available to schedule" from that event, and avoids a cross-service call on every schedule request. It does mean a content item briefly won't be schedulable if Scheduler's consumer hasn't processed its `content.created` event yet (normally sub-second).
- **No cross-service content details on the calendar view**: `GET /scheduled` returns `content_id`, not the post's title/body — fetching that is left to the frontend calling Content directly, rather than Scheduler doing an N+1 fan-out of cross-service calls per calendar render.

### Social Publishing Service notes

- **LinkedIn credentials are placeholders** (`linkedin-client-id/secret-placeholder`) — per the spec, every developer registers their own LinkedIn Developer App for local testing (LinkedIn issues API access per app, not shared across a team), enabling the "Sign In with LinkedIn using OpenID Connect" and "Share on LinkedIn" products with scopes `openid profile email w_member_social`. `LINKEDIN_REDIRECT_URI` must exactly match a redirect URL registered on that app.
- **The OAuth callback is genuinely public, by necessity**: LinkedIn's browser redirect back to `/social/linkedin/callback` can't carry an `Authorization` header, so unlike almost every other route in this platform, the Gateway proxies it unauthenticated. The caller's identity instead travels in a signed `state` param — `POST /social/linkedin/connect` (a normal protected route) creates it via a dedicated Fernet key (`OAUTH_STATE_KEY`, separate from the key used to encrypt stored tokens) with a 10-minute TTL baked into the Fernet token itself, and the callback verifies+decrypts it to recover `account_id`/`user_id` with no database lookup needed.
- **Tokens are encrypted at rest** (Fernet, `TOKEN_ENCRYPTION_KEY`) — `social_connections.access_token_encrypted`/`refresh_token_encrypted` are never stored in plaintext; they're only decrypted in memory for the duration of an outbound LinkedIn API call (`app/crypto.py`).
- **Image publishing (bonus)**: when `content.scheduled` resolves to a post with an `image_url`, the consumer registers an upload via LinkedIn's Assets API, downloads the image bytes (from Content's `/uploads/*` or a Pollinations.ai URL — either works, it's just an HTTP GET), `PUT`s them to LinkedIn's returned upload URL, and references the resulting asset URN in the UGC post payload — producing a text+image post instead of text-only, exactly as the bonus feature describes.
- **Retry semantics split on failure type**: a transient LinkedIn failure (rate limit, 5xx, network error) re-raises out of the consumer, which lets `py_shared.rabbitmq`'s existing bounded-retry-then-DLX mechanism handle it (no separate custom backoff timer — the platform-wide mechanism already covers "retry with backoff... route to DLQ after max attempts"). A permanent failure (no LinkedIn connection, content deleted) is caught locally, recorded, and emits `post.failed` immediately without retrying — retrying something that will fail identically every time would just waste the bounded-retry budget.
- **Token refresh is honest about a real LinkedIn constraint**: `app/token_refresh.py` runs hourly and refreshes any connection with a stored `refresh_token`, but LinkedIn's default 3-legged OAuth token doesn't grant refresh tokens unless your specific Developer App has been approved for that capability — most test/local apps won't have it. Connections without a `refresh_token` just log a warning near expiry rather than erroring; the user will need to reconnect once the (typically ~60-day) access token actually expires.
- **Cross-service content fetch, not an event payload**: `content.scheduled`'s payload only carries `content_id` (not the post text), so the consumer calls Content's `GET /content/{id}` directly (service-to-service, bypassing the Gateway) rather than requiring Content to duplicate its own data into every event — same pattern as Credits calling Billing.

### Scraper Service notes

- **The first (and only) MongoDB-backed service**: per the spec's data-ownership table, Scraper owns no Postgres schema at all — `scrape_jobs`, `scraped_documents`, and even its own `processed_events` idempotency collection all live in MongoDB (`app/mongo.py`, via Motor's async driver). The `py_shared.rabbitmq.consume()` idempotency hooks are plain async callables, so backing them with Mongo instead of Postgres required zero changes to the shared library — proof the abstraction was right.
- **Playwright over Crawl4AI**: the spec allows either; Playwright was simpler for this scope's "load the page, grab title/text/html" need with no extra wrapper. The Dockerfile deliberately uses Microsoft's official `mcr.microsoft.com/playwright/python` base image (browsers + OS deps pre-installed) instead of `playwright install` on a bare `python:3.11-slim`, which reliably fails without a list of extra apt packages that image already has.
- **robots.txt compliance is real, not decorative**: `app/robots.py` fetches `robots.txt` itself via httpx (async) and hands the raw lines to `urllib.robotparser.RobotFileParser.parse()`, avoiding that library's own blocking `urlopen` call — `crawl()` in `app/crawler.py` refuses to proceed if disallowed, and treats that as a **permanent** failure (no retry — robots.txt won't change its mind on redelivery), distinct from a transient crawl error which does retry via the standard bounded-retry-then-DLX path.
- **Per-domain rate limiting is in-process, not distributed**: `app/rate_limiter.py` tracks the last request time per hostname in a plain dict guarded by an `asyncio.Lock`, sufficient for the single-worker deployment this scope assumes — scaling to multiple scraper worker replicas later would need this moved to a shared store (Redis) to stay accurate across them, which isn't done here.
- **Recurring jobs use a genuinely different mechanism than Scheduler**: the spec calls for "an internal scheduler" here, as opposed to the dedicated Scheduler Service's Celery Beat setup — so `app/recurring.py` is a plain asyncio loop inside this one service (started in `main.py`'s lifespan, no extra containers), scanning for `scrape_jobs` documents whose `next_run_at` has passed. Each firing inserts a fresh one-off (`recurrence: "none"`) job document for that occurrence and advances the parent's `next_run_at`, mirroring the pattern Scheduler uses but self-contained.

### Notification Service notes

- **Retroactive fixes this slice needed to make elsewhere work**: most consumed events only carry an `account_id` or `user_id`, not an email — and a couple of email flows the spec explicitly calls for (working verification links, team-invite emails) were never actually wired end-to-end because Notification didn't exist yet when Auth and User/Tenant shipped. Three small additions, all backward-compatible:
  - Auth's `user.registered` event now includes `verification_token` (previously only returned in the dev-only `dev_verification_token` API response field) — Notification builds the real `/verify-email?token=...` link from it.
  - User/Tenant's `POST /accounts/{id}/invite` now actually publishes an `invite.created` event (`{invite_id, account_id, email, token, role}`) — previously it created the `Invite` row and returned a dev token but published nothing at all, so nothing could ever have emailed the invitee even once Notification existed.
  - Two new **internal-only** endpoints: Auth's `GET /internal/users/{user_id}` (resolve email from user_id) and User/Tenant's `GET /internal/accounts/{account_id}/owner` (resolve the owner's user_id from account_id) — chained together (`app/identity_resolver.py`) to turn an `account_id`-only event into a recipient email.
- **Real security gap found and fixed while wiring this up**: the Gateway's catch-all proxy routes (`/auth/{path:path}` etc.) matched on path prefix alone, so a public request to `/auth/internal/users/{id}` would have been happily forwarded straight through to Auth's new unauthenticated internal endpoint — trivially leaking any user's email to anyone on the internet. Fixed with `_reject_internal_paths()` in the Gateway's `app/api/routes.py`, applied to every proxy route (both the shared `_proxy_protected` helper and the standalone `/auth/*` proxy), rejecting any path segment starting with `internal` before it ever reaches `forward()`. Verified directly: `GET /auth/internal/users/<uuid>` now returns `404` from the Gateway itself, never reaching Auth.
- **Four separate exchange bindings, one shared idempotency table**: `app/events.py` declares four independent queues (one per exchange: `user_events`, `domain_events`, `billing_events`, `social_events`), each with its own routing keys and DLX, but all four route through the same `processed_events` table for idempotency — safe because `event_id` is a UUID, globally unique regardless of which exchange it arrived on.
- **Email failures are swallowed, not retried**: unlike most consumers in this codebase, `app/notify.py`'s `send_and_log()` never re-raises on a Resend API failure — it logs the failure to `notification_log` (status=`failed`) and returns normally. Emails are treated as inherently best-effort here (there's no real harm in occasionally missing one, unlike e.g. Scheduler's `content.scheduled`), so retrying via the bounded-retry-then-DLX mechanism wasn't judged worth the added complexity for this scope.
- **Resend and the Slack webhook are both placeholders** (`re_placeholder`, empty `SLACK_WEBHOOK_URL`) — email sends will fail against the placeholder key (logged to `notification_log` as `status=failed`, per the point above) until a real Resend API key is set; Slack alerts just log a warning instead of posting when no webhook URL is configured, so ops alerts are still visible somewhere even unconfigured.

### Admin/Ops Service notes

- **A genuinely new, platform-level concept had to be introduced**: every other service's JWT `role` claim (`owner`/`admin`/`member`) is account-scoped, but the spec calls for "a SuperAdmin role, platform-level, not account-scoped." That required touching the shared library every service depends on: `py_shared/jwt.py`'s `TokenClaims`/`issue_access_token()` gained an `is_superadmin` field (defaulting `False`, so every existing call site kept working unchanged); Auth's `User` model gained an `is_platform_admin` column (an operator-only flag — no signup flow sets it, flip it directly in the DB for whoever operates this platform); the Gateway's `Identity` and its `_proxy_protected()` helper now read and forward it as `X-Is-Superadmin`. `TenantAdmin` (the spec's other role, restricted to one's own account) maps onto the existing account-scoped `owner`/`admin` roles rather than inventing a third role system — see `require_access_to_account()` in `app/identity.py`.
- **Four small `/internal/*` endpoints added elsewhere, purely to support this service**: User/Tenant's `GET /internal/accounts` (cross-account directory) and `GET /internal/accounts/{id}/summary` (name/type/plan_tier/member_count), Billing's `GET /internal/accounts/{id}/subscription`, Credits' `GET /internal/accounts/{id}/balance`, and Usage's `GET /internal/accounts/{id}/summary` — each mirrors an existing identity-scoped endpoint but takes an explicit `account_id` instead of trusting the caller's own identity, since Admin needs to read *any* account's data, not just its own. All four are unreachable from the public internet via the same `_reject_internal_paths()` mechanism Notification's slice introduced.
- **Session listing has no secondary index**: Auth's `jti:*` Redis keys were enriched (`{"user_id":..., "account_id":...}` JSON instead of a bare user_id string) so `GET /admin/accounts/{id}/sessions` can filter by account, but there's no reverse index from account_id → jti — listing does a full `SCAN jti:*` and filters client-side. Fine at this scope's session volume; a real secondary index (or moving this to a proper session store) would matter at much larger scale.
- **The audit consumer has no way to discover exchanges dynamically**: `AUDITED_EXCHANGES` in `app/events.py` is a hardcoded list of every topic exchange that exists across the platform today (`user_events`, `domain_events`, `billing_events`, `social_events`, `scraper_events`, `ai_events`, `webhook_events`) — RabbitMQ's client API has no "list exchanges" call without broker management permissions this service intentionally doesn't have, so a future slice that introduces a new exchange needs a one-line addition here or its events silently won't reach the audit log.
- **One shared idempotency table across seven queues**: like Notification, all seven exchange-bound queues route through the same `processed_events` table — safe because every event's `event_id` is a UUID, globally unique regardless of which exchange or queue delivered it.

Every FastAPI service shares `libs/py-shared`:
- `jwt.py` — RS256 issue/decode helpers (Auth Service holds the private key; Gateway only needs the public key)
- `rabbitmq.py` — durable topic-exchange publish with publisher confirms, and a consume() helper that enforces idempotent processing (via each service's own `processed_events` table) and bounded-retry-then-DLX delivery
- `errors.py` — the `{error: {code, message, details}}` response schema used by every service

The Gateway verifies the JWT once and forwards trusted `X-User-Id` / `X-Account-Id` / `X-Role` headers to downstream services, so internal services don't duplicate JWT verification.

**Fixed since Slice 1** (right before the frontend fill-in pass, since nearly every account-scoped page would have broken against it): `POST /auth/login` originally issued a JWT with `account_id` set to a placeholder (the user's own id acting as their individual account scope), because Auth and User/Tenant didn't coordinate to look up the user's *real* account id at login time. Auth now calls a new User/Tenant internal endpoint (`GET /internal/users/{user_id}/accounts`) to resolve the real default account (the first one returned, which is the user's individual account on their first-ever login) — falling back to the old placeholder only in the rare case User/Tenant hasn't yet consumed `user.registered` (a sub-second race right after signup). `POST /auth/switch-account` (new) validates membership in a target account via the same lookup and issues a freshly-scoped token, backing the frontend's Account Switcher exactly as the spec describes ("Account Switcher... triggers a new account-scoped JWT"). `POST /auth/refresh` also gained an optional `account_id` field so silent refresh (every ~15 minutes, since that's the access token TTL) doesn't reset a switched-away-from-default account back to the default.

## Local setup

Postgres runs **natively on the host**, not as a container — every other piece of infrastructure (Redis, RabbitMQ, MongoDB) is still fully containerized. This was a deliberate choice for this environment (an already-installed native Postgres), not a spec requirement; swapping back to a containerized Postgres is a small `docker-compose.yml` change (see the git history around the commit that made this switch) if you'd rather have a fully self-contained stack.

1. Install PostgreSQL locally (this was built against PostgreSQL 18 on Windows) and make sure it's running on port 5432.
2. Create the app's role and database:
   ```
   psql -U postgres -c "CREATE ROLE creditflow LOGIN PASSWORD 'creditflow';"
   psql -U postgres -c "CREATE DATABASE creditflow OWNER creditflow;"
   ```
3. Docker containers reach the host via `host.docker.internal`, which arrives as a different source IP than `localhost` — Postgres's `pg_hba.conf` needs a rule allowing it, or every service's `DATABASE_URL` connection will fail with an auth/connection error that's easy to mistake for a code bug. Append (adjust the range if your Docker/WSL2 setup differs) and reload:
   ```
   host    all             all             172.16.0.0/12           scram-sha-256
   host    all             all             192.168.0.0/16          scram-sha-256
   ```
   then `SELECT pg_reload_conf();` (no restart needed — `pg_hba.conf` changes apply on reload).
4. Copy `.env.example` to `.env`. Generate a dev RS256 keypair and paste the PEM contents in (see the comment in `.env.example` for the exact `openssl` commands), or reuse the one already generated for this session.
5. `docker-compose up --build`
6. Frontend: http://localhost:5173 — Gateway: http://localhost:8080 — RabbitMQ management UI: http://localhost:15672 (guest/guest)

**This has now actually been run, end-to-end, on a real machine** — not just statically verified. All 19 containers (13 backend services + Gateway + frontend + Redis/RabbitMQ/MongoDB + the Scheduler's worker/beat pair) come up and stay up; every service's `/healthz` returns `200`; a real signup through the Gateway creates rows in Postgres and — via a real RabbitMQ round-trip — an individual account and owner membership in the User/Tenant service, confirmed by querying Postgres directly afterward. Three real bugs surfaced during this pass and are already fixed (see "Bugs found via live testing" below); nothing here is theoretical anymore.

### Bugs found via live testing (already fixed)

Everything up to this point in the document had only been statically verified (imports, `py_compile`, `TestClient` hits with no real infrastructure behind them) — the following three only surfaced once the full stack actually ran together, which is exactly the gap a live test is supposed to close:

1. **Scraper's Dockerfile pinned an incompatible Python version.** It's built on Playwright's official image (`mcr.microsoft.com/playwright/python:v1.45.0-jammy`), which ships Python 3.10 — but `libs/py-shared`'s `pyproject.toml` declared `requires-python = ">=3.11"` with no actual technical basis (nothing in the shared library uses 3.11-only syntax; every file already has `from __future__ import annotations`). Lowered to `>=3.10`.
2. **Scraper's own code used `datetime.UTC`**, a constant that doesn't exist before Python 3.11 — a second, deeper layer of the same version mismatch, invisible to every previous check in this repo because those all ran against a local Python 3.14 interpreter, never the actual Playwright base image. Fixed by switching to the version-portable `datetime.timezone.utc` in Scraper's three affected files (`app/api/routes.py`, `app/events.py`, `app/recurring.py`) — every other service stays on `datetime.UTC` since they run on `python:3.11-slim` and have no such constraint.
3. **Every RabbitMQ consumer had a silent, unrecoverable startup race.** `libs/py-shared/py_shared/rabbitmq.py`'s `get_connection()` had no retry logic on the *first* connection attempt — and on a real `docker-compose up --build` cold start, nearly every one of the 13 consumer-declaring services hit "Connection refused" at least once, because Docker's healthcheck can report RabbitMQ "healthy" before its AMQP listener actually accepts connections. Since every service starts its consumer via a bare `asyncio.create_task(...)` with no supervisor above it, that first failure killed the consumer forever — HTTP endpoints kept responding normally the whole time, so nothing *looked* broken; events just silently stopped being processed. Fixed with exponential-backoff retry (10 attempts, 1s→30s) in the one shared `get_connection()` function every service's consumer goes through, rather than patching each service individually. Verified after the fix: a genuine cold `docker-compose down && docker-compose up --build -d` now brings up all 20 real RabbitMQ queues with exactly one active consumer each and zero stuck messages, confirmed via the RabbitMQ management API — not just "the container says Up."

## Verifying Slice 1 end-to-end

1. `docker-compose up --build` brings up redis/rabbitmq/gateway/auth/user-tenant/frontend cleanly (Postgres runs natively on the host — see "Local setup" above).
2. Sign up via the frontend (or `POST /auth/signup` on the Gateway) → a row appears in `auth.users`; a `user.registered` event is visible in the RabbitMQ management UI; the User/Tenant service consumes it exactly once, creating rows in `usertenant.accounts` and `usertenant.account_members` (check no duplicate account rows if you restart the `user-tenant` container mid-flow — the `processed_events` table should prevent double-processing).
3. Log in → the returned JWT (paste into [jwt.io](https://jwt.io) to inspect) contains `user_id`, `account_id`, `role`, `jti`; the `jti` is present in Redis (`redis-cli KEYS 'jti:*'`) with a TTL matching the access token expiry.
4. Log out → the `jti` is removed from Redis; a subsequent request with the old access token is rejected at the Gateway with `401 invalid_token`.
5. Forgot-password → the OTP is returned in the dev-only `dev_otp` response field (and the reset flow works with it). This stays dev-only permanently, not just until a later slice: the platform spec's Notification Service event contract doesn't include `user.password_reset_requested` among its consumed events, so — unlike the verification-email flow, which Slice 10 wires to real email — password-reset OTPs are out of Notification's actual scope.
6. `GET /me/accounts` (via the Account Switcher UI, or directly) returns every account a multi-account test user belongs to.

### Verifying Slice 2 (Billing) end-to-end

1. After signup (Slice 1 flow), the `billing` service's consumer picks up `account.created` and creates a `billing.billing_accounts` row + a `billing.subscriptions` row with `plan_tier=free` — check via `docker exec` into postgres, or `GET /billing/subscription` through the Gateway (with a valid access token).
2. With real Stripe test keys/Price IDs in `.env`, `POST /billing/checkout-session` (Owner role required) returns a real Stripe Checkout URL; completing it in test mode fires `checkout.session.completed`/`invoice.paid` webhooks.
3. Send a test webhook (`stripe trigger invoice.paid`, or replay one from the Stripe dashboard) at the Gateway's `/webhooks/stripe` — confirm: (a) it's rejected with `400 invalid_signature` if the signature doesn't match `STRIPE_WEBHOOK_SECRET`; (b) sending the exact same event twice only relays to RabbitMQ once (Redis `SETNX` dedup — check `redis-cli KEYS 'webhook_dedup:*'`); (c) the Billing service's `subscription_events` table has exactly one row for that Stripe event id even if RabbitMQ redelivers it (processed_events idempotency).
4. `POST /billing/refunds` on a paid invoice creates a real Stripe test-mode refund, a `billing.refunds` row, and an outbox row that gets published as `refund.issued` within ~2s (check the RabbitMQ management UI or the `published` column on `outbox_events`).
5. Kill the `billing` container mid-webhook-burst and restart it — confirm no invoice/subscription rows are duplicated and no outbox events are double-published (Definition of Done's forced-restart requirement, checked here for one service ahead of the full hardening pass).

### Verifying Slice 3 (Credits/Marketplace) end-to-end

1. Complete a Stripe test-mode checkout for a Pro/Team plan (Slice 2 flow) → within ~2s the buyer's account gets a `purchase_grant` row in `credits.credits_ledger` and `GET /credits/balance` reflects the plan's placeholder grant (1000 for Pro, 5000 for Team).
2. Refund that invoice via `POST /billing/refunds` → a matching `refund_clawback` row appears and the balance drops back down (capped at 0 if some credits were already spent).
3. As account A: `POST /credits/marketplace/listings` with a `credits_amount` ≤ your balance → appears in `GET /credits/marketplace/listings` for any authenticated user.
4. As account B: `POST /credits/marketplace/listings/{id}/purchase` → returns a real Stripe Checkout URL (test mode); the listing flips to `pending_payment`. Completing checkout fires `checkout.session.completed`, which Billing recognizes via its `marketplace_purchase` metadata and turns into `marketplace.payment_completed`; Credits then atomically debits A and credits B, and the listing flips to `sold` — confirm both ledger rows and the listing status.
5. Send the same `checkout.session.completed` webhook twice (replay from the Stripe dashboard, or reuse a captured payload) — confirm the listing only settles once (it's a no-op the second time since it's no longer `pending_payment`) and no duplicate ledger rows appear.
6. Kill the `credits` container mid-settlement and restart it — confirm the listing doesn't end up split between `pending_payment` and `sold` in a way that loses or double-credits currency (same forced-restart check as Slice 2, now for this service).

### Verifying Slice 4 (Usage/Metering) end-to-end

1. `GET /usage/precheck` (body `{"model": "gpt-4o-mini"}`, any authenticated account) returns `allowed=true`, `used_tokens=0`, `quota_tokens` matching the account's cached plan tier (defaults to `free`→50000 if `subscription.updated` hasn't fired for that account yet).
2. Manually publish a fake `ai.generation_completed` event to the `ai_events` exchange (routing key `ai.generation_completed`, e.g. via the RabbitMQ management UI's "Publish message" on that exchange) with a body like `{"event_id": "<uuid>", "event_type": "ai.generation_completed", "data": {"account_id": "<uuid>", "model": "gpt-4o-mini", "prompt_tokens": 100, "completion_tokens": 200, "total_tokens": 300, "cost_cents": 5}}` — confirm a row appears in `usage.usage_ledger` and `redis-cli -n 1 GET usage:<account_id>:<YYYY-MM>` shows `300`.
3. Repeat step 2 enough times to cross 80% of the account's quota — confirm exactly one `usage.threshold_reached` event is emitted (visible in the RabbitMQ management UI on the `domain_events` exchange) and one row lands in `usage.threshold_flags`; publishing more events past 100% emits a second, distinct threshold event but never re-fires the 80% one.
4. Stop the `usage` container, manually `INCR` the Redis key to simulate drift, then restart — within ~60s the reconciliation loop should overwrite it back to match the Postgres ledger's sum for the current month.
5. Trigger a real `subscription.updated` (e.g. upgrade a plan via `PATCH /billing/subscription`) — confirm `usage.account_plans` picks up the new `plan_tier` and a subsequent `/usage/precheck` reflects the new quota.

### Verifying Slice 5 (AI Generation) end-to-end

1. With a real `GROQ_API_KEY` in `.env`, `GET /models` (through the Gateway) returns `{"fast": "...", "quality": "..."}`; `POST /generations` with `{"prompt": "...", "model": "fast"}` returns `202` and a `job_id` immediately (before generation finishes).
2. Open `GET /sse/{job_id}?access_token=<access_token>` (a plain browser tab or `curl -N` works — it's SSE, not WebSocket) and confirm `data: {"type":"token",...}` lines arrive token-by-token, followed by a terminal `data: {"type":"done",...}` line that ends the stream.
3. `GET /generations/{job_id}` (through the Gateway, header auth) shows `status=completed`, the full accumulated `response`, and non-zero `total_tokens`/`cost_cents`; a matching row exists in `ai_generation.generation_jobs` and `ai_generation.prompt_history`.
4. Without a real Groq key (placeholder), confirm the job instead ends with `status=failed` and a populated `error_reason`, and that `GET /sse/{job_id}` correctly terminates on the `data: {"type":"error",...}` message rather than hanging.
5. Start a generation, then immediately call `POST /generations/{job_id}/cancel` — confirm the job settles at `status=cancelled` with whatever partial response had streamed so far, and the SSE stream terminates on a `data: {"type":"cancelled"}` message.
6. Exceed the account's Usage quota (Slice 4), then call `POST /generations` again — confirm it's rejected with `429 quota_exceeded` before any Groq call is made.
7. `POST /generations/{job_id}/image` with a prompt returns a working Pollinations.ai image URL (open it in a browser — it should render an image with no auth) and a row in `ai_generation.image_generation_jobs`.
8. Once a generation completes, confirm Usage's `usage_ledger` picks up a matching row via the `ai_events` exchange (the consumer Slice 4 built with no producer at the time) — this is the first end-to-end proof that wiring was correct.

### Verifying Slice 6 (Content) end-to-end

1. Run a `POST /generations` with the default `purpose: "post"` (Slice 5) through to completion — confirm a `content.content` row appears automatically with `status=draft`, `source_generation_job_id` matching the job, and a title derived from the first ~60 characters of the response; a matching `content.content_versions` row (version 1) also exists.
2. Run a generation with `purpose` set to something else (e.g. `"chat"`) — confirm no Content row is created for it.
3. `PATCH /content/{id}` as any member (body: `{"body": "edited text"}`) — confirm `version` increments to 2 and `GET /content/{id}/versions` shows both snapshots.
4. As a `member` role, attempt `POST /content/{id}/status` with `{"status": "approved"}` — confirm `403 forbidden`; repeat as `owner`/`admin` — confirm it succeeds and `content.updated` is published (visible in the RabbitMQ management UI on `domain_events`).
5. Attempt an invalid transition, e.g. `draft` → `published` directly — confirm `409 invalid_transition`.
6. `POST /content/{id}/image` (multipart, any small image file) — confirm the returned `image_url` (e.g. `/uploads/<uuid>.jpg`) resolves to the actual image when opened through the Gateway (`http://localhost:8080/uploads/<uuid>.jpg`), and that the file persists across a `docker-compose restart content` (the `content_uploads` named volume).
7. Kill the `content` container mid-way through consuming a burst of `ai.generation_completed` events and restart it — confirm no duplicate draft Content rows for any single `generation_job_id`.

### Verifying Slice 7 (Scheduler) end-to-end

1. Create a piece of content (Slice 6), then `POST /scheduled` with its `content_id` and a near-future `publish_at` (e.g. 90 seconds out, timezone-aware ISO 8601) and `recurrence: "none"` — confirm `201` and a `scheduler.scheduled_posts` row with `status=scheduled`.
2. Wait for the next Beat scan (`scheduler-beat` logs should show the task firing every 60s) — confirm the row flips to `status=fired`, `occurrences_fired=1`, and a `content.scheduled` event appears on the RabbitMQ management UI's `domain_events` exchange with the right `content_id`.
3. Repeat with `recurrence: "weekly"` — confirm that after it fires, `status` stays `scheduled`, `occurrences_fired` increments, and `publish_at` has advanced by exactly 7 days rather than moving to `fired`.
4. `PATCH /scheduled/{id}` to push `publish_at` further out, or change `recurrence` — confirm it only works while `status=scheduled` (`409` once `fired`/`cancelled`).
5. `DELETE /scheduled/{id}` before it's due — confirm `status=cancelled` and that the next Beat scan skips it (no `content.scheduled` emitted for it).
6. `GET /scheduled?start=...&end=...` — confirm it returns only the caller's account's items within the window, ordered by `publish_at`.
7. Stop `rabbitmq` (or block network to it) right as a post becomes due, let Beat's scan attempt fire, then restore connectivity — confirm the post is still `status=scheduled` (not incorrectly marked `fired`) and the *next* scan successfully fires it once the lock (55s TTL) has expired.
8. Schedule two posts for the same `publish_at`, then manually run two overlapping scans in quick succession (e.g. trigger the Celery task twice back-to-back) — confirm each post only ends up firing (and emitting `content.scheduled`) once, not twice.

### Verifying Slice 8 (Social Publishing) end-to-end

1. With a real LinkedIn Developer App configured (Client ID/Secret, redirect URI registered exactly matching `LINKEDIN_REDIRECT_URI`), `POST /social/linkedin/connect` returns an `authorize_url`; opening it, approving the requested scopes, and being redirected back should land on `FRONTEND_CONNECTIONS_URL?connected=true` with a new `social_publishing.social_connections` row (encrypted tokens — confirm the stored value isn't your plaintext access token if you peek at the DB).
2. `GET /social/connections` reflects `connected=true` with the right `linkedin_member_urn` and `expires_at`; `DELETE /social/connections` removes it and a subsequent `GET` reflects `connected=false`.
3. Schedule a piece of content with no image (Slice 6 + 7) for a near-future time — once Scheduler fires it, confirm a text-only UGC post appears on the connected LinkedIn account, a `publish_jobs` row shows `status=published` with a real `linkedin_post_id`, and `post.published` is visible on the RabbitMQ management UI's `social_events` exchange (its own dedicated exchange, matching Billing's `billing_events` — the `content.scheduled` it consumed to trigger this still comes in via the shared `domain_events` exchange).
4. Repeat with a piece of content that has an `image_url` (either a manually uploaded Content image or an AI-generated Pollinations.ai one) — confirm the resulting LinkedIn post has an attached image (not text-only), and a `post_media` row records the LinkedIn asset URN.
5. Schedule content for an account with **no** LinkedIn connection — confirm the `publish_jobs` row goes straight to `status=failed` with a clear `error_reason`, `post.failed` is emitted, and — importantly — it does **not** get retried (check the DLQ/retry count stays at 0, since this is a permanent failure).
6. Temporarily point `LINKEDIN_UGC_POSTS_URL` (or block network access) to simulate a transient LinkedIn outage — confirm the job retries (via the standard bounded-retry mechanism) up to the configured max before landing in the `domain_events.dlx`/`social_publishing.content_scheduled.dlq` (the consumer side's DLQ — distinct from the `social_events` exchange this service publishes its own domain events to), rather than failing immediately like step 5.
7. Manually set a `social_connections.expires_at` a few days out with a (fake) `refresh_token_encrypted` populated — confirm the token-refresh background job attempts a refresh on its next hourly pass (check logs); with no `refresh_token`, confirm it logs a warning instead of erroring.

### Verifying Slice 9 (Scraper) end-to-end

1. `POST /scrape-jobs` with a real, scrape-friendly `target_url` and `recurrence: "none"` — confirm `202`, a `scrape_jobs` document with `status=pending`, and within a few seconds (crawl time + the 5s-per-domain politeness delay) it flips to `status=completed` with a linked `scraped_documents` entry containing real `title`/`text_content`/`html`.
2. `GET /scrape-jobs/{id}` and `GET /scraped-documents/{document_id}` return the expected data, scoped to the caller's account (a different account's token gets `404`, not someone else's document).
3. Target a URL whose `robots.txt` disallows crawling (or one that returns a disallow-all robots.txt) — confirm the job goes straight to `status=failed` with a robots-related `error_reason`, and does **not** get retried (check the retry count / DLQ stays untouched, same distinction as Social Publishing's permanent-vs-transient split).
4. Target an unreachable host (or briefly block network access) — confirm the job retries via the standard bounded-retry-then-DLX mechanism before eventually landing in `scraper_events.dlx`, rather than failing immediately like step 3.
5. Issue two scrape jobs targeting the same domain back-to-back — confirm (via timestamps in `scraped_documents` or scraper logs) they're at least `MIN_SECONDS_BETWEEN_REQUESTS_PER_DOMAIN` apart, not fired simultaneously.
6. `POST /scrape-jobs` with `recurrence: "daily"` — confirm the parent job document persists with a `next_run_at` roughly 24h out; manually backdate `next_run_at` in Mongo to force it due, and confirm the next recurring-scan pass (every 60s) creates a new one-off job document, fires it, and pushes the parent's `next_run_at` forward by another 24h.

### Verifying Slice 10 (Notification) end-to-end

1. With a real `RESEND_API_KEY`, sign up a new user (Slice 1) — confirm a real verification email arrives with a **working** link (not just the `dev_verification_token` API field), and a `notification.notification_log` row with `status=sent` and a `provider_message_id`.
2. Invite a teammate (`POST /accounts/{id}/invite`) — confirm the invitee receives a real invite email with a working accept link, sourced from the new `invite.created` event (previously this endpoint published nothing at all).
3. Accept that invite — confirm the new member receives a "welcome to the team" email, resolved via `member.joined` → Auth's `/internal/users/{id}` lookup.
4. Complete a Stripe checkout (Slice 2) — confirm the account owner receives a receipt email, resolved via `invoice.paid` → User/Tenant's `/internal/accounts/{id}/owner` → Auth's `/internal/users/{id}` (two chained internal calls).
5. Trigger a `payment.failed`, or a `post.failed` (Slice 8) — confirm both an email to the owner **and** a Slack alert (or, with no `SLACK_WEBHOOK_URL` configured, a warning-level log line) fire.
6. **Security check**: `curl http://localhost:8080/auth/internal/users/<any-uuid>` directly at the Gateway — confirm it returns `404` and never reaches Auth's actual endpoint (this was a real gap found while building this slice; confirm it stays fixed). Repeat for any other service's `/internal/*` path reachable through a Gateway catch-all.
7. Stop the `notification` container mid-event-burst across all four exchanges (`user_events`, `domain_events`, `billing_events`, `social_events`) and restart it — confirm no duplicate emails send for any single event, and that events from all four exchanges resume being consumed (check each queue's consumer count in the RabbitMQ management UI).

### Verifying Slice 11 (Admin/Ops) end-to-end — the last backend service

1. Flip `is_platform_admin=true` directly in `auth.users` for a test user (no signup flow sets this, by design), log in again to get a token with `is_superadmin=true`, and confirm `GET /admin/accounts` returns every account on the platform.
2. As that same SuperAdmin, `GET /admin/accounts/{any_account_id}/overview` for an account you don't belong to — confirm it succeeds and returns `plan_tier`, `member_count`, `subscription_status`, `credit_balance`, and `usage_this_period_tokens`/`usage_quota_tokens` all populated from four different services' new `/internal/*` endpoints.
3. As a plain `owner`/`admin` of your *own* account (not SuperAdmin), confirm the same overview/sessions/audit-log endpoints work for your own `account_id` but return `403 forbidden` for any other account's.
4. `GET /admin/accounts/{id}/sessions` — confirm it lists every currently active JWT for that account (matching what you'd see doing a manual `redis-cli SCAN jti:*` and filtering by account); log in from a second browser/device and confirm a new session appears.
5. `POST /admin/sessions/{jti}/revoke` on one of those sessions — confirm the corresponding access token is immediately rejected at the Gateway with `401 invalid_token` on its next request, without waiting for natural expiry.
6. Generate activity across several services (signup, a Stripe payment, a LinkedIn post, a scrape job) and confirm `GET /admin/audit-log` (SuperAdmin) shows all of it in one searchable timeline, each row's `source_exchange` correctly identifying which exchange it came from; confirm `GET /admin/accounts/{id}/audit-log` for a TenantAdmin only ever shows that one account's events.
7. Kill the `admin` container mid-event-burst across all seven exchanges and restart it — confirm no duplicate `audit_log` rows for any single `event_id`, and that all seven queues resume being consumed.

**This closes out all 13 backend services from the spec.** What's left, per the roadmap below, is entirely frontend fill-in, a cross-service reliability pass, and the AWS deployment bonus — no more new backend services.

## Repo layout

```
services/
  gateway/  auth/  user-tenant/  billing/  credits/  usage/  ai-generation/  content/  scheduler/
    social-publishing/  scraper/  notification/  admin/
frontend/
libs/py-shared/
docker-compose.yml
.env.example
```

## Slice 12: Frontend fill-in

Fills in every page the spec calls for beyond Slice 1's marketing/auth/onboarding skeleton: Owner Dashboard, Team Management, Billing & Invoices, Credits & Marketplace (all Owner-only), Content Studio with real SSE streaming, Calendar/Scheduler, LinkedIn Connections (Owner + Member), and a SuperAdmin Console. Also fixes the Slice 1 placeholder `account_id` bug (see the "Fixed since Slice 1" note above) — nearly every page in this slice would have broken against it otherwise.

### Notes

- **Node.js was installed partway through this slice**, so unlike every prior slice this one got real tooling verification rather than manual-only review: `npm install`, `npx tsc -b` (zero type errors), `npm run build` (production Vite build succeeds), and `npm run dev` (dev server boots cleanly) were all run and passed. What's still unverified is the actual click-through against a live backend — Docker isn't available in this environment, so no service has been reachable from the browser to test real data flowing through these pages. Run `docker-compose up` on a machine with Docker for that last mile.
- **No new npm dependencies were added.** The spec's calendar suggestions (FullCalendar, React Big Calendar) weren't pulled in, since a new dependency can't be installed-and-verified without Node available — `CalendarScheduler.tsx` is a small hand-rolled month grid instead, functionally equivalent for this scope (click a day, see what's scheduled, create/reschedule/cancel) but without drag-and-drop or week view.
- **Account Switcher now does what the spec asks**: selecting a different account calls the new `POST /auth/switch-account` (added alongside the account_id fix) and replaces both tokens — previously it only displayed accounts without actually switching context.
- **Route guards are UX only, not a security boundary** — `OwnerRoute`/`SuperAdminRoute` (new, alongside the existing `ProtectedRoute`) redirect away from pages a role shouldn't see, but every real authorization check happens server-side per the spec's explicit framing ("the frontend restriction is a UX convenience, not a security boundary"); a `member` calling an owner-only backend endpoint directly still gets `403` regardless of what the frontend shows.
- **Confirmation dialogs**: a new shared `ConfirmDialog` component gates every destructive action the spec calls out by name — revoking a session, removing a team member, cancelling a scheduled post — plus a couple more in the same spirit (deleting content, cancelling a marketplace listing, disconnecting LinkedIn).
- **Content Studio's "save as draft" is implicit, not a button**: every AI generation with the default `purpose: "post"` already becomes a draft automatically server-side (Slice 6's `ai.generation_completed` → `content.created` flow) — there's no separate "save" step to wire up; the page's Drafts list is just `GET /content` filtered client-side to non-published items.
- **A known minor gap, not fixed here**: `AcceptInvite.tsx`'s "log in first" redirect doesn't carry the invite token back through login — a user who isn't already authenticated has to click the emailed invite link again after logging in, rather than resuming automatically. `LoginRequest`/`Login.tsx` don't currently support a post-login redirect target.

### Verifying Slice 12 (Frontend) end-to-end

1. `docker-compose up --build`, then walk the full loop in a browser: sign up → verify (dev token from Slice 1) → create/join a team → land on the Owner Dashboard and confirm plan tier/credit balance/team size/usage all populate from four different backend calls.
2. Generate a post in the Content Studio and watch tokens stream in live (open the Network tab — confirm it's an `EventSource`/SSE connection to `/sse/{job_id}`, not polling); confirm the resulting draft appears in the Drafts list without any extra "save" action.
3. Schedule that draft on the Calendar for a near-future time with `recurrence: "weekly"` — confirm it appears in the correct day cell, and that Reschedule/Cancel only show up while `status=scheduled`.
4. Connect a real LinkedIn Developer App via LinkedIn Connections, then let the scheduled post fire — confirm the Publish History table shows it, and that a real image attaches if the content has one.
5. As an Owner, invite a teammate from Team Management (dev invite token since Resend is a placeholder), accept it in another browser/incognito session, and confirm the new member can reach Content Studio/Calendar/LinkedIn but gets redirected away from Team/Billing/Credits.
6. Switch between two accounts via the Account Switcher and confirm the Dashboard/Content Studio data actually changes to match — not just the dropdown label.
7. Flip `is_platform_admin=true` for a test user directly in Postgres, log in again, and confirm the SuperAdmin Console nav item appears and the console lets you browse any account's overview/sessions/audit log, while a non-SuperAdmin owner is redirected away from `/admin` entirely.

## Slice 13: Reliability hardening pass

The Definition of Done requires every service to survive a forced consumer restart with no data loss or duplication. Each slice's own verification steps spot-checked this per-service as it was built, but this pass went through every event consumer in the platform specifically looking for the one gap that pattern doesn't automatically close (see below), rather than re-verifying things already covered (DLX/retry, publisher confirms, durable delivery — all structurally enforced by `py_shared.rabbitmq` itself and unchanged here).

### What "restart-safe" actually requires, and where it was missing

`py_shared.rabbitmq.consume()` runs `handler(payload)`, and only *after* it returns successfully does it call `mark_processed(event_id)`; only after *that* does it ack the message back to the broker. That ordering means the shared `processed_events` idempotency check reliably catches redelivery *after* both of those have committed — but a crash landing *between* the handler's own commit and the `mark_processed` commit (exactly what "kill the container mid-burst" probes) leaves `is_processed()` still `False`, so redelivery re-runs the handler's business logic in full. The processed_events table is necessary but not sufficient — **every handler needs its own idempotency check against its own schema**, and auditing for that specifically turned up four real duplication bugs and one related false-failure bug that had gone unnoticed because nothing had actually forced this exact crash timing yet:

- **User/Tenant's `user.registered` handler** created an individual Account + owner membership with no check for one already existing — redelivery in that crash window would have given one user two individual accounts. Fixed: skip if the user already has *any* account membership (a brand-new user has zero, so this is a reliable signal).
- **Credits' `invoice.paid` handler** appended a `purchase_grant` ledger row with no check — redelivery would double-credit the account. **`refund.issued`** had the same gap for `refund_clawback` rows. Both fixed with an existence check keyed on `(reference_id, reason)`. (`marketplace.payment_completed` was already correct — it was built checking listing status from the start.)
- **Usage's `ai.generation_completed` handler** inserted a `usage_ledger` row with no check — redelivery would permanently double-count that call's cost/tokens (Redis alone would self-heal via the reconciliation loop; the durable Postgres row would not). Fixed with a check keyed on `generation_job_id`.
- **Billing's Stripe webhook handler** actually had the right idempotency signal already sitting right there — inserting the `SubscriptionEvent` audit row happens in the *same transaction* as every `_apply_*` side effect and its outbox-event insert, so "a SubscriptionEvent row for this stripe_event_id already exists" is a fully valid, atomic guard. The bug was that the code checked for it but never `return`ed early, so `_apply_payment_failed`/`_apply_subscription_updated`/`_apply_checkout_session_completed` ran again on redelivery regardless — re-extending a dunning grace period and double-emitting `payment.failed`/`subscription.updated`/`marketplace.payment_completed` outbox events every time. Fixed by returning immediately when the row already exists.
- **Scraper's `scrape.requested` handler** — `scraped_documents` and the `scrape_jobs` status update are two separate MongoDB writes (no multi-document transaction wraps them), so a crash between them left the job at `status=pending`; without a check, redelivery re-crawled and inserted a *second* document. Fixed: if a document already exists for that `scrape_job_id`, just finish the status update instead of re-crawling.
- **Admin's audit-log handler** was a different failure mode entirely: `AuditLog.event_id` already has a unique DB constraint, so redelivery in that same crash window wouldn't have silently duplicated the row — it would have hit an `IntegrityError`, which the outer `consume()` loop treats as a genuine handler failure and retries pointlessly until the (already-correctly-recorded) event lands in the DLQ as a false failure. Fixed with the same existence-check pattern, avoiding the wasted retries.
- **`py_shared/rabbitmq.py`'s `consume()` docstring** now spells out this exact nuance directly, so the next new consumer gets built with it in mind instead of this pass needing to be repeated by hand.

Everything above was found and fixed by code review, then confirmed by re-importing every touched service's app with its real dependencies (catching, among other things, a missing `select` import in the User/Tenant fix that would otherwise have been a `NameError` at the exact moment the fix was needed) — not by an actual `docker-compose` forced-restart run, since Docker isn't available in this environment. The verification steps below describe exactly that run for whoever has Docker to do it.

### Two gaps found but deliberately *not* "fixed"

Two consumers have a structurally different problem this pass's fix pattern can't close, and no attempt was made to half-fix them with something that wouldn't actually be correct:

- **Social Publishing's `content.scheduled` handler** calls LinkedIn's UGC Posts API *before* marking the `publish_jobs` row `published`. A crash in that exact window — after LinkedIn successfully creates the post, before the DB commit — means redelivery re-runs the whole handler and creates a **second real LinkedIn post**. This is an external, non-idempotent side effect, not an internal DB write; closing it properly needs either a client-supplied idempotency key LinkedIn's API would need to support (not something this integration currently sends) or a "posting-in-progress" pre-commit plus a reconciliation check against LinkedIn's own post history, which is real scope beyond this pass.
- **Notification's `send_and_log()`** sends the email *before* logging it, for the same reason: there's no dedup key to check before an email send, and marking "about to send" before calling the provider still doesn't prevent redelivery mid-flight from sending twice. A user could get one duplicate email in this exact crash window.

Both are documented here rather than silently left alongside the fixed ones, since "found and consciously deferred with a stated reason" is a materially different, more honest status than "not found."

### Verifying Slice 13 end-to-end

For each of the six fixed handlers above, on a machine with Docker: manually publish (or trigger via the normal flow) the relevant event, kill `-9` the consuming service's container after its handler's own commit would plausibly have happened but before the next scan/poll interval, restart it, and confirm via the relevant table (`account_members`, `credits_ledger`, `usage_ledger`, `subscription_events`+`outbox_events`, `scraped_documents`, `audit_log`) that no duplicate row exists and the event's effects landed exactly once. For the two acknowledged gaps, the honest verification is confirming the failure mode reproduces under that exact timing (a duplicate LinkedIn post / a duplicate email) — not that it's absent, since it isn't fully closed.

## Roadmap (remaining work)

AWS deployment (bonus, via the `main` branch release-PR pipeline described in the Git Workflow section) is the only Definition of Done / bonus item left unaddressed.

Git workflow: `main` (protected, production) / `dev` (protected, integration) / `feature/*` / `fix/*`, PR + at least one review + passing CI before merge into `dev`; release PRs from `dev` to `main` trigger the AWS deployment pipeline. Conventional Commits (`feat:`, `fix:`, `chore:`, ...) throughout.
