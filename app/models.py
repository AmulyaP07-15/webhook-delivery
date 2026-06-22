"""The three core tables plus an immutable attempt log.

Endpoint   : a subscriber. Where to deliver, what to deliver, the signing secret.
Event      : something that happened. Immutable.
Delivery   : one event aimed at one endpoint. Carries the current delivery state.
Attempt    : one immutable record per delivery try. This is the audit log.

The split between Delivery (mutable current state) and Attempt (append-only
history) is deliberate: Delivery answers "where does this stand right now",
Attempt answers "show me everything that happened". That separation is what
makes a clean delivery-log feature possible later.
"""

from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DeliveryStatus(str, Enum):
    PENDING = "pending"        # created, waiting in the queue for its turn
    DELIVERING = "delivering"  # a worker has claimed it and is sending now
    SUCCEEDED = "succeeded"    # receiver returned 2xx
    FAILED = "failed"          # last attempt failed, more retries remain
    DEAD = "dead"              # retries exhausted, given up


class Endpoint(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    url: str
    secret: str                                  # used to sign deliveries
    event_types: list[str] = Field(sa_column=Column(JSON))  # ["order.created", ...] or ["*"]
    is_active: bool = True
    created_at: datetime = Field(default_factory=_now)


class Event(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    event_type: str
    payload: dict = Field(sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)


class Delivery(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    event_id: str = Field(foreign_key="event.id", index=True)
    endpoint_id: str = Field(foreign_key="endpoint.id", index=True)
    status: DeliveryStatus = Field(default=DeliveryStatus.PENDING)
    attempt_count: int = 0
    max_attempts: int = 6
    next_attempt_at: datetime = Field(default_factory=_now)
    last_status_code: int | None = None
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Attempt(SQLModel, table=True):
    id: str = Field(default_factory=_uuid, primary_key=True)
    delivery_id: str = Field(foreign_key="delivery.id", index=True)
    attempt_number: int
    status_code: int | None = None
    response_body: str | None = None   # truncated, just for debugging
    error: str | None = None
    latency_ms: int | None = None
    attempted_at: datetime = Field(default_factory=_now)