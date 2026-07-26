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
provider-error MESSAGE SHAPE ("<provider> error (<Type>): <sanitized>"); it
does NOT own a pattern list. A second pattern list is exactly how the two
scrubbers drifted apart in the first place (see that module's docstring).

See D5 in workspaces/byok-hardening for the threat model.
"""

from __future__ import annotations

# Re-exported for the pattern-level regression suites, which assert against
# the compiled rules directly (e.g. tests/regression/test_issue_1974_*).
# These are the SHARED objects — importing them from here and from
# kaizen.utils.credential_scrub yields the same identities, so a pattern-level
# assertion made through this module is an assertion about the shared list.
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
        A sanitized error string safe for multi-tenant exposure.
    """
    sanitized = scrub_credentials(str(error), placeholder=_PLACEHOLDER)

    # Build the final message
    parts = [f"{provider_name} error"]
    if include_error_type:
        parts.append(f" ({type(error).__name__})")
    parts.append(f": {sanitized}")

    return "".join(parts)


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
