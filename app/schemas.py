"""Request and response shapes for the API. Kept separate from the DB models so
the wire contract is explicit. Note EndpointCreated returns the secret exactly
once (on registration); it is never echoed again, the same way an API key works."""

from datetime import datetime

from pydantic import BaseModel


class EndpointCreate(BaseModel):
    url: str
    event_types: list[str]  # specific types, or ["*"] for everything


class EndpointCreated(BaseModel):
    id: str
    url: str
    event_types: list[str]
    secret: str  # shown once, store it now
    is_active: bool


class EndpointRead(BaseModel):
    id: str
    url: str
    event_types: list[str]
    is_active: bool
    created_at: datetime


class EventCreate(BaseModel):
    event_type: str
    payload: dict


class EventAccepted(BaseModel):
    event_id: str
    deliveries_created: int


class DeliveryRead(BaseModel):
    id: str
    event_id: str
    endpoint_id: str
    status: str
    attempt_count: int
    max_attempts: int
    next_attempt_at: datetime
    last_status_code: int | None
    last_error: str | None
