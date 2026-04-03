# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
SSRF protection — validate URLs against private IP ranges.

Used by RestSourceAdapter and OAuth2Auth to prevent Server-Side Request
Forgery attacks (doc 01-redteam H4).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

__all__ = ["validate_url_safe", "SSRFError"]


class SSRFError(ValueError):
    """Raised when a URL targets a private/reserved IP range."""

    pass


# Private and reserved IP ranges that should not be accessed from source adapters
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),  # IPv6 private
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def validate_url_safe(url: str) -> str:
    """Validate that a URL does not target private/reserved IP ranges.

    Args:
        url: The URL to validate.

    Returns:
        The normalized URL if safe.

    Raises:
        SSRFError: If the URL targets a blocked IP range.
        ValueError: If the URL is malformed.
    """
    parsed = urlparse(url)

    if not parsed.scheme or parsed.scheme not in ("http", "https"):
        raise ValueError(f"URL must use http or https scheme, got: {parsed.scheme!r}")

    if not parsed.hostname:
        raise ValueError(f"URL has no hostname: {url!r}")

    hostname = parsed.hostname

    # Normalize path to prevent traversal
    if ".." in (parsed.path or ""):
        raise SSRFError(f"Path traversal detected in URL: {url!r}")

    # Check if hostname is an IP address literal
    try:
        addr = ipaddress.ip_address(hostname)
    except ValueError:
        # hostname is a domain name — resolve it to check for DNS rebinding
        _check_resolved_addresses(hostname, url)
    else:
        _check_ip_blocked(addr, url)

    return url


def _check_ip_blocked(
    addr: ipaddress.IPv4Address | ipaddress.IPv6Address, url: str
) -> None:
    """Check a single IP address against blocked networks."""
    for network in _BLOCKED_NETWORKS:
        if addr in network:
            raise SSRFError(f"URL targets blocked IP range {network}: {url!r}")


def _check_resolved_addresses(hostname: str, url: str) -> None:
    """Resolve DNS and check all returned addresses against blocked ranges.

    Prevents DNS rebinding attacks where a domain resolves to private IPs.
    """
    try:
        results = socket.getaddrinfo(
            hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM
        )
        for family, _, _, _, sockaddr in results:
            ip_str = sockaddr[0]
            try:
                addr = ipaddress.ip_address(ip_str)
                _check_ip_blocked(addr, url)
            except ValueError:
                continue
    except socket.gaierror:
        # DNS resolution failed — hostname doesn't exist. Allow the request
        # to proceed so the HTTP client produces a clear connection error.
        pass
