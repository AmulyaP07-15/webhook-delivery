"""Event ingestion.

This is the fast path. It persists the event, fans out to every active endpoint
subscribed to this event type, creates one Delivery per match, enqueues each into
the Redis queue scored for "now", and returns immediately. No HTTP delivery happens
here; that is the worker's job. Keeping delivery off this path is what stops a slow
or dead receiver from ever slowing down event production.
"""

import time

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.config import settings
from app.database import get_session
from app.models import Delivery, Endpoint, Event
from app.queue import DeliveryQueue
from app.schemas import EventAccepted, EventCreate

router = APIRouter(prefix="/events", tags=["events"])
queue = DeliveryQueue()


def _matches(endpoint: Endpoint, event_type: str) -> bool:
    return "*" in endpoint.event_types or event_type in endpoint.event_types


@router.post("", response_model=EventAccepted, status_code=202)
def ingest_event(body: EventCreate, session: Session = Depends(get_session)):
    event = Event(event_type=body.event_type, payload=body.payload)
    session.add(event)

    endpoints = session.exec(select(Endpoint).where(Endpoint.is_active == True)).all()  # noqa: E712
    targets = [e for e in endpoints if _matches(e, body.event_type)]

    deliveries = []
    for endpoint in targets:
        delivery = Delivery(
            event_id=event.id,
            endpoint_id=endpoint.id,
            max_attempts=settings.default_max_attempts,
        )
        session.add(delivery)
        deliveries.append(delivery)

    session.commit()

    # Enqueue only after the rows are safely committed.
    now = time.time()
    for delivery in deliveries:
        queue.enqueue(delivery.id, due_at=now)

    return EventAccepted(event_id=event.id, deliveries_created=len(deliveries))
