# Webhook Delivery System

Reliable webhook delivery: the layer between "something happened in my app" and "every subscriber was notified, even when their server is down." A minimal, self-hostable take on what Svix, Hookdeck, and Convoy do.

## What it does

Subscribers register an endpoint (a URL, the event types they care about, and a signing secret). When the app emits an event, the system fans it out to every matching subscriber and delivers it over HTTP with at-least-once guarantees: failed deliveries retry with exponential backoff and jitter, exhausted ones are dead-lettered, and every attempt is logged. Each delivery is HMAC-signed so the receiver can verify it is authentic and not replayed.

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

Event ingestion never makes an outbound HTTP call. It persists and enqueues, then returns. A slow or dead subscriber can never slow down event production. The worker owns all delivery.

## How a delivery works

1. `POST /events` writes the event and fans out one delivery per matching subscriber.
2. Each delivery is enqueued in a Redis sorted set, scored by the time it is due.
3. The worker claims due deliveries, signs the payload, and POSTs it with a hard timeout.
4. On a 2xx the delivery is marked succeeded. On failure it is rescheduled with backoff, or dead-lettered once attempts are exhausted.
5. Every attempt (status code, latency, error) is recorded in an append-only log.

## Quickstart

```bash
docker compose up --build
```

Register an endpoint:

```bash
curl -X POST localhost:8000/endpoints -H 'content-type: application/json' \
  -d '{"url": "https://your-app.example.com/hooks", "event_types": ["order.created"]}'
```

Emit an event:

```bash
curl -X POST localhost:8000/events -H 'content-type: application/json' \
  -d '{"event_type": "order.created", "payload": {"order_id": 42}}'
```

Inspect the delivery log at `GET /deliveries`, drill into one with `GET /deliveries/{id}`, and manually replay one with `POST /deliveries/{id}/redeliver`.

## Verifying deliveries (subscriber side)

A tiny dependency-free client library does it in one call:

```python
from webhook_receiver import verify, WebhookVerificationError

try:
    payload = verify(secret, raw_body, request.headers)
except WebhookVerificationError:
    ...  # reject

# payload is the trusted, parsed event
```

It recomputes the HMAC, rejects deliveries whose timestamp is too old (replay protection), and returns the parsed payload. See `client/` and the runnable receivers in `examples/`.

## Design decisions and tradeoffs

**At-least-once, not exactly-once.** Exactly-once delivery over a network is impossible, so deliveries carry a stable `Webhook-Id` and subscribers deduplicate on it. Every other decision follows from this.

**Redis sorted set as the scheduler.** Delivery ids are members scored by their next-attempt timestamp. "Retry in N seconds" becomes a one-line operation, and the worker just asks for everything due now.

**Backoff with jitter.** Jitter is not cosmetic. Without it, every delivery that failed during an outage retries at the same instant and re-overwhelms the subscriber the moment it recovers. Jitter smears the retries across a window.

**SSRF guard at registration.** Subscribers hand over arbitrary URLs. Each is resolved and rejected if it points at loopback, link-local (the cloud metadata endpoint), or private ranges. This is the highest-severity, most-skipped part of building this kind of system.

**Sync, sequential worker.** Chosen for clarity and easy reasoning over raw throughput. Per-destination concurrency and isolation are explicitly out of v1 scope.

**Split Delivery and Attempt tables.** Delivery holds current state ("where does this stand"); Attempt is an append-only history ("show me everything that happened"). That separation is what makes a clean, replayable delivery log possible.

## Deliberately out of scope (v1 roadmap)

Circuit breaking and auto-disabling chronically failing endpoints; per-destination concurrency and noisy-neighbor isolation; ordering guarantees (subscribers should order by timestamp); async delivery for throughput; multi-tenant accounts.

## Tech stack

FastAPI, PostgreSQL, Redis, httpx, Docker, docker-compose.