"""Endpoint (subscriber) management.

Registration runs the SSRF guard before anything is stored, and generates a signing
secret that is returned exactly once. The secret is what the subscriber uses to
verify deliveries; we never show it again.
"""

import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.database import get_session
from app.models import Endpoint
from app.schemas import EndpointCreate, EndpointCreated, EndpointRead
from app.security.ssrf import UnsafeURLError, validate_url

router = APIRouter(prefix="/endpoints", tags=["endpoints"])


@router.post("", response_model=EndpointCreated, status_code=201)
def register_endpoint(body: EndpointCreate, session: Session = Depends(get_session)):
    try:
        validate_url(body.url)
    except UnsafeURLError as exc:
        raise HTTPException(status_code=400, detail=f"unsafe url: {exc}") from exc

    endpoint = Endpoint(
        url=body.url,
        secret=secrets.token_urlsafe(32),
        event_types=body.event_types,
    )
    session.add(endpoint)
    session.commit()
    session.refresh(endpoint)
    return EndpointCreated(
        id=endpoint.id,
        url=endpoint.url,
        event_types=endpoint.event_types,
        secret=endpoint.secret,
        is_active=endpoint.is_active,
    )


@router.get("", response_model=list[EndpointRead])
def list_endpoints(session: Session = Depends(get_session)):
    return session.exec(select(Endpoint)).all()
