"""The delivery worker. This is the reliability core.

Loop:
  1. Claim due deliveries from the Redis queue.
  2. For each, load its endpoint and event, sign the payload, POST it with a hard
     timeout (slow counts as failure).
  3. Record an immutable Attempt row either way.
  4. On 2xx -> mark SUCCEEDED.
     On failure with retries left -> compute backoff, set next_attempt_at,
       re-enqueue scored for the future.
     On failure with no retries left -> mark DEAD.

Sequential and synchronous on purpose: it is easy to reason about and easy to demo.
Per-destination concurrency and isolation are deliberately out of v1 scope.
"""

import json
import time
from datetime import datetime, timedelta, timezone

import httpx
from sqlmodel import Session

from app.config import settings
from app.database import engine, init_db
from app.models import Attempt, Delivery, DeliveryStatus, Endpoint, Event
from app.queue import DeliveryQueue
from app.security.signing import build_headers
from app.worker.backoff import next_delay

queue = DeliveryQueue()
MAX_BODY_LOG = 500  # only store a snippet of the receiver's response


def _deliver_one(session: Session, http: httpx.Client, delivery_id: str) -> None:
    delivery = session.get(Delivery, delivery_id)
    if delivery is None or delivery.status in (DeliveryStatus.SUCCEEDED, DeliveryStatus.DEAD):
        return

    endpoint = session.get(Endpoint, delivery.endpoint_id)
    event = session.get(Event, delivery.event_id)
    if endpoint is None or event is None:
        return

    delivery.status = DeliveryStatus.DELIVERING
    delivery.attempt_count += 1
    attempt_no = delivery.attempt_count
    session.add(delivery)
    session.commit()

    body = json.dumps({"id": event.id, "type": event.event_type, "data": event.payload})
    timestamp = str(int(time.time()))
    headers = build_headers(endpoint.secret, delivery.id, timestamp, body)

    status_code: int | None = None
    response_body: str | None = None
    error: str | None = None
    started = time.perf_counter()
    try:
        resp = http.post(endpoint.url, content=body, headers=headers)
        status_code = resp.status_code
        response_body = resp.text[:MAX_BODY_LOG]
    except httpx.RequestError as exc:
        error = f"{type(exc).__name__}: {exc}"
    latency_ms = int((time.perf_counter() - started) * 1000)

    session.add(Attempt(
        delivery_id=delivery.id,
        attempt_number=attempt_no,
        status_code=status_code,
        response_body=response_body,
        error=error,
        latency_ms=latency_ms,
    ))

    succeeded = status_code is not None and 200 <= status_code < 300
    delivery.last_status_code = status_code
    delivery.last_error = error
    delivery.updated_at = datetime.now(timezone.utc)

    if succeeded:
        delivery.status = DeliveryStatus.SUCCEEDED
        session.add(delivery)
        session.commit()
        print(f"[delivered] {delivery.id} -> {endpoint.url} ({status_code}) in {latency_ms}ms")
        return

    if attempt_no >= delivery.max_attempts:
        delivery.status = DeliveryStatus.DEAD
        session.add(delivery)
        session.commit()
        print(f"[dead] {delivery.id} after {attempt_no} attempts (last={status_code or error})")
        return

    delay = next_delay(attempt_no)
    delivery.status = DeliveryStatus.FAILED
    delivery.next_attempt_at = datetime.now(timezone.utc) + timedelta(seconds=delay)
    session.add(delivery)
    session.commit()
    queue.enqueue(delivery.id, due_at=time.time() + delay)
    print(f"[retry] {delivery.id} attempt {attempt_no} failed ({status_code or error}); "
          f"next in {delay:.1f}s")


def run() -> None:
    init_db()
    print("worker started, polling for due deliveries...")
    with httpx.Client(timeout=settings.http_timeout_seconds, follow_redirects=False) as http:
        while True:
            due = queue.claim_due(settings.worker_batch_size)
            if not due:
                time.sleep(settings.worker_poll_interval)
                continue
            with Session(engine) as session:
                for delivery_id in due:
                    try:
                        _deliver_one(session, http, delivery_id)
                    except Exception as exc:  # never let one bad delivery kill the loop
                        print(f"[error] processing {delivery_id}: {exc}")


if __name__ == "__main__":
    run()