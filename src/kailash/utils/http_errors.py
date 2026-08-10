"""Client-safe HTTP error details with server-side diagnostic retention.

An exception rendered into an HTTP response body travels to the CLIENT. That
makes it strictly worse than the same exception in a log line: a driver or
transport error reaching a request handler routinely carries a DSN
(``postgres://user:password@host/db``), a bearer token, or an internal path,
and a raw ``detail=str(e)`` hands all of it to whoever made the request --
over unauthenticated routes, to anyone at all.

This module is the SINGLE helper every handler routes through, per
``rules/security.md`` § Credential Decode Helpers: hand-rolled per-call-site
scrubbing is BLOCKED, because N copies of a filter drift into N different
filters and the weakest one defines the exposure.

What it does NOT do is swallow the error (``rules/zero-tolerance.md`` Rule 3).
The exception is still fully reported SERVER-side; only the client-facing body
is reduced. A short reference id appears in BOTH, so an operator handed
``reference: 4f2a9c1b8e07`` by a user can grep the logs straight to the
originating exception. Sanitizing without that id would trade a security bug
for an unsupportable service.

Fail-closed by default (``rules/security.md`` § Secure-Default For A New
Security Feature): the client gets a generic message UNLESS the exception's
type is explicitly named in ``safe_types``. Adding a type to that allowlist is
a deliberate act asserting "this exception's message is written FOR end users",
the same contract PACT's ``_sanitize_error`` applies to ``PactError``.

Returns a plain ``str`` and raises nothing, deliberately. This is plain core:
``fastapi`` is not a required dependency (core requires only jsonschema /
pydantic / pyyaml / click), and ``kailash-nexus`` depends on ``kailash``, so
importing either here would add an optional dep to the core path or invert the
package dependency. A string also serves every response shape at once --
``HTTPException(detail=...)``, ``ProblemDetail(detail=...)``, and a
``JSONResponse`` content dict -- which a raise-helper bound to one of them
could not. Do NOT re-add a framework import to this module.

Why the server-side record is masked rather than raw: the repo's measured
position -- see the comment at ``visualization/api.py`` in ``start_monitoring``
-- is that ``mask_error_text`` covers exactly two credential carriers (URL
userinfo and sensitive query parameters) and is porous over unbounded input.
So the log combines it with two BOUNDED, structurally inert fields
(``safe_type_name`` and ``safe_exception_frames``) that together are the
diagnostic an operator actually needs: what failed, and where.
"""

from __future__ import annotations

import logging
import uuid
from typing import Iterable, Optional

from kailash.utils.secure_logging import safe_exception_frames, safe_type_name
from kailash.utils.url_credentials import mask_error_text

__all__ = [
    "new_error_reference",
    "safe_http_detail",
]

# Kept generic on purpose: a per-status message must not narrate internal
# state. "which run" / "which backend" / "which query" is the log's job.
_GENERIC_BY_STATUS = {
    400: "Invalid request",
    401: "Authentication required",
    403: "Access denied",
    404: "Resource not found",
    409: "Conflicting request",
    422: "Request could not be processed",
    429: "Too many requests",
    500: "Internal server error",
    502: "Upstream service error",
    503: "Service unavailable",
    504: "Upstream service timed out",
}

_DEFAULT_GENERIC = "Internal server error"


def new_error_reference() -> str:
    """Return a short, unique id correlating a client response to a log record."""
    return uuid.uuid4().hex[:12]


def safe_http_detail(
    exc: BaseException,
    *,
    logger: logging.Logger,
    context: str,
    status_code: int = 500,
    safe_types: Iterable[type[BaseException]] = (),
    reference: Optional[str] = None,
) -> str:
    """Log ``exc`` server-side and return a client-safe ``detail`` string.

    Args:
        exc: The caught exception. Reported in full server-side, never verbatim
            to the client unless its type is listed in ``safe_types``.
        logger: Logger of the calling module -- the server-side record lands
            here, so it stays attributable to the handler that failed.
        context: Short operator-facing description of the failed operation
            ("list runs", "create token"). MUST NOT be caller-controlled input.
        status_code: Selects the generic client message.
        safe_types: Exception types whose ``str()`` is written for end users.
            Empty by default: unlisted types get the generic message.
        reference: Reuse an existing correlation id instead of minting one.

    Returns:
        The string to hand to ``HTTPException(detail=...)``.
    """
    ref = reference or new_error_reference()

    # Server-side record first: if the caller's raise is what runs next, the
    # diagnostic is already durable.
    logger.error(
        "%s failed [reference=%s]: %s: %s at %s",
        context,
        ref,
        safe_type_name(exc),
        mask_error_text(exc),
        safe_exception_frames(exc, limit=5),
    )

    safe_tuple = tuple(safe_types)
    if safe_tuple and isinstance(exc, safe_tuple):
        # Allowlisted: the message is designed for users. Still masked --
        # defense in depth costs nothing on a message that should not have
        # carried a credential in the first place.
        return f"{mask_error_text(exc)} (reference: {ref})"

    generic = _GENERIC_BY_STATUS.get(status_code, _DEFAULT_GENERIC)
    return f"{generic} (reference: {ref})"
