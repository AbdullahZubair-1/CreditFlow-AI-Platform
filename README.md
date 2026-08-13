# CreditFlow AI Platform

Multi-tenant, credit-based SaaS platform for AI-assisted content generation and social publishing, built as independently deployable FastAPI microservices behind a single API Gateway, communicating over RabbitMQ, with Redis for caching/session state/rate limiting and a shared Postgres instance (one schema per service).

This repo is being built incrementally, slice by slice, rather than all 13 services at once.

- **Slice 1**: signup → email verification → login → JWT issuance → account creation → account switcher, through the Gateway, consumed by a minimal React frontend.
- **Slice 2**: Billing Service — Stripe sandbox subscriptions/checkout/refunds via the transactional outbox pattern, with the Gateway now doing real Stripe webhook verification + relay instead of a 501 stub.
- **Slice 3** (this pass): Credits/Marketplace Service — append-only credits ledger, credit grants on `invoice.paid`, refund clawbacks, and peer-to-peer marketplace listing/purchase settled through a one-time Stripe Checkout Session that Billing creates on Credits' behalf.

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
   │                          - /webhooks/stripe                  -> verifies signature, dedups via
   │                                                                 Redis SETNX, relays to RabbitMQ
   │                          - /webhooks/linkedin, /webhooks/openrouter, /sse/* -> 501 stubs (future slices)
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
   └─► credits (FastAPI, :8004) — credits_ledger, marketplace_listings, processed_events
          (schema: credits)
          consumes: invoice.paid (grants credits per plan_tier), refund.issued (claws
                    back the matching grant), marketplace.payment_completed (settles a
                    marketplace sale — debits seller, credits buyer, atomically)
          publishes: credits.credited, credits.debited, credits.low_balance

Infra: postgres (:5432, one instance/many schemas), redis (:6379), rabbitmq (:5672, mgmt UI :15672)
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

Every FastAPI service shares `libs/py-shared`:
- `jwt.py` — RS256 issue/decode helpers (Auth Service holds the private key; Gateway only needs the public key)
- `rabbitmq.py` — durable topic-exchange publish with publisher confirms, and a consume() helper that enforces idempotent processing (via each service's own `processed_events` table) and bounded-retry-then-DLX delivery
- `errors.py` — the `{error: {code, message, details}}` response schema used by every service

The Gateway verifies the JWT once and forwards trusted `X-User-Id` / `X-Account-Id` / `X-Role` headers to downstream services, so internal services don't duplicate JWT verification.

**Known limitation of this slice**: `POST /auth/login` currently issues a JWT with `account_id` set to a placeholder (the user's own id acting as their individual account scope), because Auth and User/Tenant don't yet coordinate to look up the user's *real* account id at login time. `GET /me/accounts` (via the User/Tenant service) already returns the real account records correctly. Wiring login to the real account id, and giving the frontend's Account Switcher the ability to request a new account-scoped JWT, is a fast-follow once the Billing/Credits slices exist and there's real per-account data worth scoping tokens to.

## Local setup

1. Copy `.env.example` to `.env`. Generate a dev RS256 keypair and paste the PEM contents in (see the comment in `.env.example` for the exact `openssl` commands), or reuse the one already generated for this session.
2. `docker-compose up --build`
3. Frontend: http://localhost:5173 — Gateway: http://localhost:8080 — RabbitMQ management UI: http://localhost:15672 (guest/guest)

> This environment (where the code was generated) does not have Docker or Node.js installed, so `docker-compose up` and the frontend build have **not** been run end-to-end here. What has been verified: every Python service's FastAPI app imports cleanly with its real dependencies installed, and the Gateway responds correctly to `TestClient` requests (health check, error-schema stub routes). Run the steps below on a machine with Docker to confirm the full flow.

## Verifying Slice 1 end-to-end

1. `docker-compose up --build` brings up postgres/redis/rabbitmq/gateway/auth/user-tenant/frontend cleanly.
2. Sign up via the frontend (or `POST /auth/signup` on the Gateway) → a row appears in `auth.users`; a `user.registered` event is visible in the RabbitMQ management UI; the User/Tenant service consumes it exactly once, creating rows in `usertenant.accounts` and `usertenant.account_members` (check no duplicate account rows if you restart the `user-tenant` container mid-flow — the `processed_events` table should prevent double-processing).
3. Log in → the returned JWT (paste into [jwt.io](https://jwt.io) to inspect) contains `user_id`, `account_id`, `role`, `jti`; the `jti` is present in Redis (`redis-cli KEYS 'jti:*'`) with a TTL matching the access token expiry.
4. Log out → the `jti` is removed from Redis; a subsequent request with the old access token is rejected at the Gateway with `401 invalid_token`.
5. Forgot-password → the OTP is returned in the dev-only `dev_otp` response field (and the reset flow works with it) since the Notification Service — which will send it by real email — doesn't exist until a later slice.
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

## Repo layout

```
services/
  gateway/       auth/       user-tenant/     billing/     credits/     (usage, ai-generation,
                                                                          content, scheduler, social-publishing,
                                                                          scraper, notification, admin — later slices)
frontend/
libs/py-shared/
docker-compose.yml
.env.example
```

## Roadmap (subsequent slices)

Usage/Metering → AI Generation (+ bonus image gen) → Content → Scheduler (+ bonus recurring schedules) → Social Publishing (+ bonus image publishing) → Scraper → Notification (replaces the dev-only OTP/verification-token logging from Slice 1 with real email) → Admin/Ops → frontend fill-in (dashboards, billing/credits pages, content studio, calendar, LinkedIn connections, SuperAdmin console) → reliability hardening pass (forced consumer restart with no data loss/duplication, across all services) → AWS deployment.

Git workflow: `main` (protected, production) / `dev` (protected, integration) / `feature/*` / `fix/*`, PR + at least one review + passing CI before merge into `dev`; release PRs from `dev` to `main` trigger the AWS deployment pipeline. Conventional Commits (`feat:`, `fix:`, `chore:`, ...) throughout.
