# Webhook Delivery System

A minimal, self-hostable webhook delivery service: the reliable layer between
"something happened in my app" and "every subscriber was told about it, even when
their server is down." A small open-source take on what Svix, Hookdeck, and Convoy do.

## What it does

Subscribers register an endpoint (a URL, the event types they care about, and a
signing secret). When your app emits an event, the system fans it out to every
matching subscriber and delivers it over HTTP with at-least-once guarantees:
failed deliveries retry with exponential backoff and jitter, exhausted ones are
dead-lettered, and every attempt is logged. Each delivery is HMAC-signed so the
receiver can verify it is authentic and not replayed.

## Architecture

```
                 POST /events
                      |
                      v
        +-------------------------+        events + deliveries
        |   API (FastAPI)         |------------------------------+
        |   - register endpoints  |                              |
        |   - ingest + fan out    |                              v
        +-------------------------+                       +--------------+
                      |                                   |  Postgres    |
                      | enqueue (score = due time)        |  (durable)   |
                      v                                   +--------------+
              +----------------+                                 ^
              |  Redis ZSET    |  "what is due now?"             |
              |  delay queue   |<------------------+             |
              +----------------+                   |             |
                      |                            |             |
                      | claim due                  | reschedule  | record
                      v                            | (backoff)   | attempt
              +-------------------------+          |             |
              |   Worker                |----------+-------------+
              |   - sign + POST         |
              |   - retry / dead-letter |---> subscriber endpoints
              +-------------------------+
```

The event ingestion path never makes an outbound HTTP call. It persists and
enqueues, then returns. A slow or dead subscriber can never slow down event
production. The worker owns all delivery, retrying and dead-lettering on its own.

## Quickstart

```bash
docker compose up --build
```

Register an endpoint:

```bash
curl -X POST localhost:8000/endpoints \
  -H 'content-type: application/json' \
  -d '{"url": "https://your-app.example.com/hooks", "event_types": ["order.created"]}'
# returns a `secret` once; store it to verify deliveries
```

Emit an event:

```bash
curl -X POST localhost:8000/events \
  -H 'content-type: application/json' \
  -d '{"event_type": "order.created", "payload": {"order_id": 42}}'
```

Inspect deliveries at `GET /deliveries` and queue depth at `GET /health`.

## Verifying a delivery (subscriber side)

Each request carries `Webhook-Id`, `Webhook-Timestamp`, and `Webhook-Signature`.
Recompute `HMAC-SHA256(secret, "{timestamp}.{raw_body}")` and compare. Reject
deliveries whose timestamp is too old to prevent replay. A drop-in client library
with a `verify()` helper ships in the repo (see `client/`).

## Design decisions

- **At-least-once, not exactly-once.** Exactly-once over a network is impossible,
  so deliveries carry a stable `Webhook-Id` and subscribers deduplicate on it.
- **Redis sorted set as the scheduler.** Members are delivery ids, scored by their
  next-attempt timestamp. The worker asks for everything due now. This is what
  makes "retry in N seconds" a one-line operation.
- **Backoff with jitter.** Jitter prevents a synchronized retry storm against a
  subscriber that just recovered from an outage.
- **SSRF guard on registration.** Registered URLs are resolved and rejected if they
  point at loopback, link-local (cloud metadata), or private ranges.
- **Sync, sequential worker.** Chosen for clarity. Per-destination concurrency and
  isolation are deliberately out of v1 scope.

## Deliberately out of scope for v1 (roadmap)

Circuit breaking and auto-disabling chronically failing endpoints; per-destination
concurrency and noisy-neighbor isolation; ordering guarantees (subscribers should
order by timestamp); async delivery for throughput; multi-tenant accounts.
