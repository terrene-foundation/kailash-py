# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
URL and secret masking helpers — single source of truth for redacting
credentials out of log lines, error messages, and exposition endpoints.

Phase 7.6: every log line that mentions a Redis URL, PostgreSQL URL,
MongoDB URL, or any other connection string carrying ``user:password``
userinfo MUST route that URL through :func:`mask_url` first. The
rule (see ``rules/security.md`` § "No secrets in logs") is that
credentials must never appear in logs; the enforcement is this
module, because centralizing the masker makes the audit a single
grep instead of N greps across N files.

History: prior to Phase 7.6, the fabric subsystem shipped its own
``_mask_url`` helper in ``fabric/cache.py``. Three other modules
imported the underscore-private symbol to reuse the logic. Phase 7.6
promotes it to ``dataflow/utils/masking.py`` so every future module
can import from one canonical location, and deprecates the
underscore-private alias in ``fabric/cache.py`` to re-export this
module's :func:`mask_url` for backward compatibility.
"""

from __future__ import annotations

from typing import Optional
from urllib.parse import urlparse, urlunparse

__all__ = [
    "mask_url",
    "mask_secret",
]


def mask_url(url: Optional[str]) -> str:
    """Replace the userinfo section of a URL with ``***``.

    Handles every URL scheme ``urllib.parse`` understands (redis://,
    rediss://, postgres://, postgresql://, mongodb://, mysql://,
    http://, https://, ws://, wss://, etc.). Returns:

    - ``""`` when ``url`` is ``None`` or empty — nothing to mask.
    - ``"<unparseable>"`` when ``urlparse`` raises on the input — we
      intentionally discard the raw input rather than echoing it,
      because the input might itself be the secret (a malformed
      connection string literal).
    - The URL unchanged when there's no ``user`` or ``password``
      component — nothing to mask in that case.
    - The URL with ``user:password`` replaced by ``***`` otherwise.

    Examples:
        >>> mask_url("redis://alice:wonderland@localhost:6379/0")
        'redis://***@localhost:6379/0'
        >>> mask_url("postgres://localhost:5432/db")
        'postgres://localhost:5432/db'
        >>> mask_url(None)
        ''
        >>> mask_url("")
        ''
        >>> mask_url("not a url")
        'not a url'

    This helper is deliberately NOT configurable — there is no
    "mask only the password" mode, no "mask only under certain log
    levels" mode. Credentials either appear in logs or they don't,
    and centralizing the enforcement here is the only way to audit
    it mechanically.
    """
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        if parsed.username or parsed.password:
            netloc = "***@" + (parsed.hostname or "")
            if parsed.port:
                netloc = f"{netloc}:{parsed.port}"
            return urlunparse(parsed._replace(netloc=netloc))
        return url
    except (ValueError, AttributeError):
        return "<unparseable>"


def mask_secret(value: Optional[str], *, keep_tail: int = 4) -> str:
    """Mask a bearer token, API key, or opaque secret.

    Returns the last ``keep_tail`` characters prefixed by ``***`` so
    operators can still correlate two log lines that reference the
    same secret without exposing the secret itself. When ``value`` is
    shorter than ``keep_tail`` characters, returns ``"***"`` flat so
    even a 1-character secret is not leaked.

    Examples:
        >>> mask_secret("sk-1234567890abcdef")
        '***cdef'
        >>> mask_secret("short")
        '***'
        >>> mask_secret(None)
        ''
        >>> mask_secret("")
        ''

    This is the secondary masker for values that don't have a URL
    structure; :func:`mask_url` handles the URL case because userinfo
    parsing is scheme-aware.
    """
    if not value:
        return ""
    if len(value) <= keep_tail:
        return "***"
    return "***" + value[-keep_tail:]
