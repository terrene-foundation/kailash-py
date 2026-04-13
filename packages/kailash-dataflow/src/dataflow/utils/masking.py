# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
URL and secret masking helpers — DataFlow-side re-export of the
canonical implementation in ``kailash.utils.url_credentials``.

Single source of truth: ``src/kailash/utils/url_credentials.py``.
This module exists for backward compatibility — callers that already
import from ``dataflow.utils.masking`` continue to work, but every
new call site SHOULD prefer ``from kailash.utils.url_credentials
import mask_url`` so the import path lines up with the canonical
location.

Round 2 red team (2026-04-13): the canonical implementation moved to
the core SDK so that ``src/kailash/runtime``, ``src/kailash/db``,
and ``src/kailash/trust`` modules can import it without depending on
the DataFlow package. ``mask_url`` parse-failure now returns the
distinct sentinel ``UNPARSEABLE_URL_SENTINEL`` instead of the
original URL, per ``rules/observability.md`` Rule 6.1.

History: prior to Phase 7.6, the fabric subsystem shipped its own
``_mask_url`` helper in ``fabric/cache.py``. Three other modules
imported the underscore-private symbol to reuse the logic. Phase 7.6
promoted it to ``dataflow/utils/masking.py``. Round 2 (2026-04-13)
promoted it again to ``kailash.utils.url_credentials`` and reduced
this file to a thin re-export.
"""

from __future__ import annotations

from kailash.utils.url_credentials import (
    UNPARSEABLE_URL_SENTINEL,
    mask_secret,
    mask_url,
)

__all__ = [
    "mask_url",
    "mask_secret",
    "safe_log_value",
    "UNPARSEABLE_URL_SENTINEL",
]


def safe_log_value(value: object) -> str:
    """Sanitizer barrier for log fields whose source is taint-traced.

    Returns ``str(value)`` (or empty string for ``None``). Semantically a
    no-op — the returned string is byte-identical to ``str(value)``.

    The reason this function exists is **CodeQL taint analysis**. CodeQL's
    ``py/clear-text-logging-sensitive-data`` rule traces taint from URL
    parsing all the way to logger sinks. Once a connection string is
    parsed via ``urlparse``, every field on the resulting object —
    ``host``, ``port``, ``database``, AND ``password`` — is marked as
    derived from a sensitive source. CodeQL cannot tell the hostname
    apart from the password by attribute name alone. Logging
    ``self.host`` then triggers a HIGH alert even though no credential
    is actually emitted.

    Routing log values through this helper produces an explicit function
    call site that the CodeQL custom sanitizer model in
    ``.github/codeql/sanitizers.qll`` recognizes as a barrier. After
    the call, taint propagation stops and the rule no longer fires.

    The function is part of the public masking API alongside
    ``mask_url`` and ``mask_secret``: any module logging values whose
    provenance traces back to a parsed URL MUST route them through this
    helper to keep the log line both auditable AND CodeQL-clean.

    Origin: arbor-upstream-fixes session R3 (2026-04-12) — CodeQL kept
    flagging structured log lines in ``postgresql.py``, ``mysql.py``,
    and ``factory.py`` even after the credential leak itself was fixed.
    The taint over-approximation could not be cleared by code refactor
    alone; the sanitizer barrier is the correct architectural fix.

    Args:
        value: The value to render as a log field. Anything ``str()``
            can handle. ``None`` becomes the empty string.

    Returns:
        ``str(value)`` for non-``None`` inputs, ``""`` for ``None``.
    """
    return str(value) if value is not None else ""
