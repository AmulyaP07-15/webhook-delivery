"""SSRF guard.

Customers hand you arbitrary URLs and your worker will make outbound requests to
them. Without this, someone registers http://169.254.169.254/ (the cloud metadata
endpoint) or an internal address and your server happily fetches it for them.

The defense has two parts:
  1. Only allow http/https.
  2. Resolve the hostname to its actual IPs and reject if ANY resolved IP is
     private, loopback, link-local, reserved, or multicast.

Resolving and checking the IP (not just the hostname string) is what defeats the
trick where a hostname looks public but resolves to an internal address. The same
re-resolution should be repeated at send time to fully close DNS rebinding; that
is a Day-2 hardening note.
"""

import ipaddress
import socket
from urllib.parse import urlparse

from app.config import settings


class UnsafeURLError(ValueError):
    """Raised when a URL fails the SSRF checks."""


def _is_blocked_ip(ip_str: str) -> bool:
    ip = ipaddress.ip_address(ip_str)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_url(url: str) -> None:
    """Raise UnsafeURLError if the URL is not a safe outbound destination."""
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"scheme must be http or https, got {parsed.scheme!r}")

    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")

    if settings.allow_private_urls:
        # Dev escape hatch for testing against localhost receivers.
        return

    try:
        resolved = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"could not resolve host {host!r}") from exc

    for entry in resolved:
        ip_str = entry[4][0]
        if _is_blocked_ip(ip_str):
            raise UnsafeURLError(
                f"host {host!r} resolves to blocked address {ip_str}"
            )
