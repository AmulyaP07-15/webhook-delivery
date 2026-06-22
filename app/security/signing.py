"""Payload signing.

Every delivery carries a signature so the receiver can verify two things:
  1. It really came from us (only someone with the shared secret can produce it).
  2. It was not tampered with in transit.

The signature is HMAC-SHA256 over "{timestamp}.{body}", not just the body. Signing
the timestamp is what gives replay protection: a receiver rejects deliveries whose
timestamp is too old, so a captured-and-resent request fails even though its
signature is technically valid.

The exact same signing function is what the client library will expose as verify(),
so producer and consumer agree byte-for-byte.
"""

import hashlib
import hmac


def sign(secret: str, timestamp: str, body: str) -> str:
    """Return the hex HMAC-SHA256 signature for this delivery."""
    signed_content = f"{timestamp}.{body}".encode()
    return hmac.new(secret.encode(), signed_content, hashlib.sha256).hexdigest()


def build_headers(secret: str, delivery_id: str, timestamp: str, body: str) -> dict[str, str]:
    """Headers attached to every outbound delivery."""
    return {
        "Content-Type": "application/json",
        "Webhook-Id": delivery_id,
        "Webhook-Timestamp": timestamp,
        "Webhook-Signature": sign(secret, timestamp, body),
    }


def verify(secret: str, timestamp: str, body: str, signature: str) -> bool:
    """Receiver-side check. Uses a constant-time compare to avoid timing leaks."""
    expected = sign(secret, timestamp, body)
    return hmac.compare_digest(expected, signature)
