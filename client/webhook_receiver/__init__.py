"""webhook_receiver: verify webhooks delivered by the webhook-delivery service.

A subscriber receives a signed POST and needs to answer one question: is this real?
This library answers it in one call. It mirrors the server's signing exactly, so the
two sides agree byte-for-byte.

    from webhook_receiver import verify, WebhookVerificationError

    try:
        payload = verify(secret, raw_body, request.headers)
    except WebhookVerificationError:
        return 400  # reject

THE ONE GOTCHA: pass the RAW request body, exactly as received. Do not parse the
JSON and re-serialize it before verifying. JSON round-tripping can reorder keys or
change whitespace, which changes the bytes, which breaks the signature. The signature
is computed over the literal body that was sent, so you must verify over the literal
body you received.
"""

import hashlib
import hmac
import json
import time
from collections.abc import Mapping

ID_HEADER = "Webhook-Id"
TIMESTAMP_HEADER = "Webhook-Timestamp"
SIGNATURE_HEADER = "Webhook-Signature"

DEFAULT_TOLERANCE_SECONDS = 300  # reject deliveries older than 5 minutes


class WebhookVerificationError(Exception):
    """Raised when a delivery fails verification for any reason."""


def _header(headers: Mapping[str, str], name: str) -> str | None:
    """Case-insensitive header lookup (HTTP header casing varies by framework)."""
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def verify(
    secret: str,
    body: str | bytes,
    headers: Mapping[str, str],
    tolerance_seconds: int = DEFAULT_TOLERANCE_SECONDS,
    _now: float | None = None,
) -> dict:
    """Verify an incoming webhook and return its parsed JSON payload.

    Raises WebhookVerificationError if the headers are missing, the timestamp is
    outside the tolerance window (replay protection), the signature does not match,
    or the body is not valid JSON.
    """
    if isinstance(body, bytes):
        body = body.decode("utf-8")

    timestamp = _header(headers, TIMESTAMP_HEADER)
    signature = _header(headers, SIGNATURE_HEADER)
    if not timestamp or not signature:
        raise WebhookVerificationError("missing Webhook-Timestamp or Webhook-Signature header")

    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise WebhookVerificationError("Webhook-Timestamp is not an integer") from exc

    now = int(_now if _now is not None else time.time())
    age = abs(now - sent_at)
    if age > tolerance_seconds:
        raise WebhookVerificationError(
            f"timestamp outside tolerance: {age}s old, limit {tolerance_seconds}s (possible replay)"
        )

    expected = hmac.new(
        secret.encode(), f"{timestamp}.{body}".encode(), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise WebhookVerificationError("signature mismatch")

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise WebhookVerificationError("body is not valid JSON") from exc


__all__ = ["verify", "WebhookVerificationError", "ID_HEADER", "TIMESTAMP_HEADER", "SIGNATURE_HEADER"]
