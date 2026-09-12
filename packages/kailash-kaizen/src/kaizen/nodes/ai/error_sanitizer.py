# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Error sanitizer for LLM provider exceptions.

Strips API keys, bearer tokens, URL-embedded credentials, and internal
paths from provider exception messages before they are exposed to callers
or logged in multi-tenant environments.

The credential patterns themselves live in
``kaizen.utils.credential_scrub`` — the SINGLE scrub implementation shared
with ``kaizen.llm.errors.ProviderError``. This module owns only the
provider-error MESSAGE SHAPE ("<provider> error (<Type>): <sanitized>") and
the LOG-STRUCTURE BARRIER applied to it; it does NOT own a pattern list, and
it does NOT own a flatten implementation either — that is
``kailash.utils.secure_logging.sanitize_log_value``. A second pattern list is
exactly how the two scrubbers drifted apart in the first place (see that
module's docstring), and a hand-rolled flatten would be the same mistake one
surface over.

TWO SEPARATE PROPERTIES, in this order (issue #2111):

1. **Credential scrub**, over the WHOLE input, so no pattern can be split by
   a later bound.
2. **Log-structure barrier**, over the WHOLE composed message: single-line and
   length-bounded, because this string is interpolated into ``logger.*`` calls
   at 55 measured sites. Before #2111 a line terminator in a provider message
   travelled out of here intact and forged a second log record at every one.

Neither is a redaction step for the diagnostic text, which survives on purpose.

See D5 in workspaces/byok-hardening for the threat model.
"""

from __future__ import annotations

# Re-exported for the pattern-level regression suites, which assert against
# the compiled rules directly (e.g. tests/regression/test_issue_1974_*).
# These are the SHARED objects — importing them from here and from
# kaizen.utils.credential_scrub yields the same identities, so a pattern-level
# assertion made through this module is an assertion about the shared list.
from kailash.utils.secure_logging import sanitize_log_value
from kaizen.utils.credential_scrub import (  # noqa: F401
    _AZURE_OPENAI_ENDPOINT,
    _CREDENTIAL_PATTERNS,
    _INTERNAL_PATH_PATTERNS,
    _URL_WITH_AUTH,
    _URL_WITH_AUTH_OVERFLOW,
    _URL_WITH_USERINFO_ONLY,
    scrub_credentials,
)

__all__ = [
    "sanitize_provider_error",
    "generic_provider_error",
]

#: Replacement token for this surface. Distinct from the wire surface's
#: ``[REDACTED-CRED]`` so a redaction can be attributed to its origin in logs.
_PLACEHOLDER = "[REDACTED]"

#: Character bound passed EXPLICITLY to :func:`sanitize_log_value`, never
#: inherited from its 256-char default. CHOSEN, not copied -- see the
#: "why not the default" note in :func:`sanitize_provider_error`. It equals
#: ``secure_logging._MAX_LOG_VALUE_CHARS``, that function's hard ceiling, so
#: this is the largest bound the shared barrier can actually honour; a larger
#: number here would be silently clamped and would misdescribe the behaviour.
#: Pinned against the helper's real ceiling by
#: ``tests/regression/test_issue_2111_provider_error_log_forging.py`` so the
#: two cannot drift without a test failing.
_PROVIDER_ERROR_MAX_CHARS = 1024

#: Appended when -- and only when -- the bound above actually shortened the
#: message. ``sanitize_log_value`` truncates SILENTLY; a silently-shortened
#: exception message or returned error payload would be a diagnostic loss with
#: no trace (``rules/zero-tolerance.md`` Rule 3). Same ``<>`` vocabulary as
#: ``secure_logging.safe_log_text``. An attacker who writes a literal
#: ``<truncated>`` into a provider message forges a cosmetic suffix only --
#: never a record boundary, because the flatten above already ran.
_TRUNCATION_MARKER = "<truncated>"


def sanitize_provider_error(
    error: Exception,
    provider_name: str,
    *,
    include_error_type: bool = True,
) -> str:
    """Sanitize a provider error message to remove credential patterns.

    Strips API keys, bearer tokens, URL-embedded credentials, and internal
    paths from provider exception messages before they are exposed to callers.

    Args:
        error: The caught exception from a provider SDK.
        provider_name: Name of the provider (for the generic message prefix).
        include_error_type: Whether to include the exception class name.

    Returns:
        A sanitized, SINGLE-LINE error string safe for multi-tenant exposure
        and safe to interpolate into a log record.
    """
    # SCRUB BEFORE BOUNDING. The credential patterns must see the WHOLE string:
    # truncating first could cut a secret in half, leaving a fragment that no
    # pattern matches and that then survives into the output. This order also
    # keeps the ReDoS-linearity contract in ``credential_scrub`` measuring what
    # it has always measured -- the full input.
    sanitized = scrub_credentials(str(error), placeholder=_PLACEHOLDER)

    # Build the final message
    parts = [f"{provider_name} error"]
    if include_error_type:
        parts.append(f" ({type(error).__name__})")
    parts.append(f": {sanitized}")
    composed = "".join(parts)

    # FLATTEN LAST, OVER THE WHOLE COMPOSED MESSAGE (issue #2111).
    #
    # ``scrub_credentials`` removes credential SHAPES; it does not touch line
    # terminators, so before this call a provider exception whose text an
    # attacker influences could carry a raw "\n" straight out of this function
    # and FORGE A SECOND LOG RECORD at every call site that interpolates the
    # result -- 55 of them, measured, across 45 modules. Fixing 55 call sites
    # is the wrong shape; the barrier belongs here, once.
    #
    # Applied to ``composed`` rather than to ``sanitized`` alone because
    # ``provider_name`` is NOT always a literal: ``llm/routing/fallback.py``
    # passes ``self.model_used``, a configured model name. That is a second
    # injection vector into the same string and it gets the same barrier.
    #
    # ``sanitize_log_value`` is THE shared barrier (``rules/security.md``
    # section "Credential Decode Helpers"): a hand-rolled ``.replace("\n", " ")``
    # here would be the sixth copy, and its own docstring names that drift as
    # the defect. It also carries the exact ``.replace`` CALL SHAPE CodeQL's
    # ``LogInjection::ReplaceLineBreaksSanitizer`` recognizes, which a local
    # flatten would not.
    #
    # WHY NOT THE 256-CHAR DEFAULT. ``sanitize_log_value`` defaults to 256 and
    # truncates silently. That default is correct for its usual argument -- one
    # short field, a user id or an email -- and WRONG here: of the 127 call
    # sites, only 55 are log sinks. The other 72 put this string into a
    # ``raise RuntimeError(...)``, a returned ``{"error": ...}`` payload, or a
    # ``metadata["error_message"]`` field, where it is the only diagnostic the
    # caller gets. Inheriting 256 would silently amputate two thirds of the
    # consumers' error text. The bound is therefore passed EXPLICITLY, at the
    # largest value the helper will honour, and any truncation that does happen
    # is ANNOUNCED rather than silent.
    flattened = sanitize_log_value(composed, limit=_PROVIDER_ERROR_MAX_CHARS)
    if len(composed) > _PROVIDER_ERROR_MAX_CHARS:
        # The map inside ``sanitize_log_value`` is strictly 1 char -> 1 char,
        # so length is preserved except by the slice -- this comparison is an
        # exact test for "the bound bit", not an approximation.
        return f"{flattened}{_TRUNCATION_MARKER}"
    return flattened


def generic_provider_error(provider_name: str, error: Exception) -> str:
    """Return a fully generic error message with no message content.

    For maximum safety in multi-tenant scenarios. The caller should log
    the full error server-side before calling this function.

    Args:
        provider_name: Name of the provider.
        error: The caught exception.

    Returns:
        A generic error string with no sensitive content.
    """
    return (
        f"{provider_name} request failed ({type(error).__name__}). "
        "Check server logs for details."
    )
