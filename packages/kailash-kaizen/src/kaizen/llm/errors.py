# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Error taxonomy for the LLM deployment abstraction.

Mirrors the Rust `LlmClientError` enum at the semantic level while remaining
Pythonic. Every error class accepting user-controlled input MUST route it
through a fingerprint before any human-visible string (repr, str, args) is
produced. Raw keys, raw URLs, or raw hostnames MUST NEVER appear verbatim in
the error message.

Taxonomy (ADR-0001 D5):

    LlmClientError
    |-- LlmError
    |   |-- Timeout
    |   |-- RateLimited
    |   |-- ProviderError
    |   `-- InvalidResponse
    |-- AuthError
    |   |-- Invalid
    |   |-- Expired
    |   `-- MissingCredential
    |-- EndpointError
    |   |-- InvalidEndpoint
    |   `-- Unreachable
    `-- ModelGrammarError
        `-- Invalid

Cross-SDK parity: class names track `LlmClientError::*` variants in
kailash-rs/crates/kaizen/src/llm/errors.rs. Semantic match only — the Python
idiom favours subclassing over a single sum-type.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional


def _fingerprint(raw: str | bytes, length: int = 8) -> str:
    """Produce a deterministic non-reversible tag for a sensitive value.

    8 hex chars (32 bits) matches the cross-SDK contract in
    ``rules/event-payload-classification.md`` § 2 and DataFlow's
    ``format_record_id_for_event`` helper, so a fingerprint emitted by a
    Python service and one emitted by a Rust service can be joined in the
    same forensic query. At ~1000 unique tags, birthday collision is
    ~0.01%, vs the 35% collision rate of the prior 4-char form.
    """
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:length]


# Credential-pattern scrub applied defensively to `ProviderError.body_snippet`
# before truncation. Providers occasionally echo the submitted Authorization
# header in 4xx error bodies (OpenAI, Anthropic, various third-party wrappers).
# The primary defense is caller-side redaction (per `ProviderError` docstring),
# but a 256-char body window is wide enough for a full sk-proj-* key to fit
# through, so a scrub here is the structural last-line defense. Round-1
# redteam M1 (security).
_CRED_PATTERNS = (
    re.compile(r"sk-proj-[A-Za-z0-9_\-]{20,}"),  # OpenAI project keys first
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{20,}"),  # Anthropic
    re.compile(r"sk-[A-Za-z0-9_\-]{20,}"),  # OpenAI standard (after the
    # more-specific patterns so sk-proj-* / sk-ant-* aren't
    # partially matched by the generic sk- rule)
    re.compile(r"AIza[0-9A-Za-z\-_]{35}"),  # Google
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key id
    re.compile(r"ASIA[0-9A-Z]{16}"),  # AWS STS temporary
    re.compile(r"Bearer\s+[A-Za-z0-9_\-.=]{20,}"),  # generic Bearer
    # JWT — three base64url segments separated by dots. Azure Entra access
    # tokens, Google OAuth2 id_tokens, and any HS256/RS256 bearer all match.
    # Catches the under-match gap from round-2 security M-N2.
    re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"),
    # Azure storage SAS token pattern (sig= parameter in a query string).
    re.compile(r"sig=[A-Za-z0-9%+/=_\-]{20,}"),
)


def _scrub_credentials(text: str) -> str:
    """Replace known credential patterns with a sentinel.

    Applied defensively before any body truncation so a provider that echoes
    the submitted token in its 4xx error body does not leak the full token
    into `ProviderError.body_snippet` / `str(err)` / tracing spans.
    """
    for pat in _CRED_PATTERNS:
        text = pat.sub("[REDACTED-CRED]", text)
    return text


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class LlmClientError(Exception):
    """Base class for every error raised from the LLM deployment layer."""


# ---------------------------------------------------------------------------
# LlmError — provider / wire errors
# ---------------------------------------------------------------------------


class LlmError(LlmClientError):
    """Provider-side LLM errors (timeouts, rate limits, bad responses)."""


class Timeout(LlmError):
    """The provider call exceeded the configured deadline."""

    def __init__(self, timeout_s: Optional[float] = None) -> None:
        self.timeout_s = timeout_s
        if timeout_s is not None:
            super().__init__(f"llm call timed out after {timeout_s:.2f}s")
        else:
            super().__init__("llm call timed out")


class RateLimited(LlmError):
    """The provider reported a rate limit. `retry_after` is seconds."""

    def __init__(self, retry_after: Optional[float] = None) -> None:
        self.retry_after = retry_after
        if retry_after is not None:
            super().__init__(f"rate limited; retry_after={retry_after:.2f}s")
        else:
            super().__init__("rate limited; no retry_after hint")


class ProviderError(LlmError):
    """The provider returned a non-2xx response.

    `body_snippet` is defensively scrubbed for known credential patterns
    (OpenAI / Anthropic / Google / AWS / Bearer) BEFORE truncation, and
    truncated to 256 chars afterwards. Callers are still encouraged to
    redact at the source; the scrub here is defense-in-depth for the
    common case where a provider echoes the submitted Authorization header
    in its 4xx error body.
    """

    _SNIPPET_LIMIT = 256

    def __init__(self, status: int, body_snippet: str = "") -> None:
        self.status = status
        # Credential scrub MUST run before truncation — if the key straddles
        # the truncation boundary, `_scrub_credentials` on the truncated
        # substring would miss the partial match. Round-1 redteam M1.
        body_snippet = _scrub_credentials(body_snippet)
        if len(body_snippet) > self._SNIPPET_LIMIT:
            body_snippet = body_snippet[: self._SNIPPET_LIMIT] + "...[truncated]"
        self.body_snippet = body_snippet
        super().__init__(f"provider error: status={status} body={body_snippet!r}")


class InvalidResponse(LlmError):
    """The provider response did not match the expected schema."""

    def __init__(self, reason: str = "") -> None:
        self.reason = reason
        super().__init__(
            f"invalid response: {reason}" if reason else "invalid response"
        )


# ---------------------------------------------------------------------------
# AuthError — credential problems
# ---------------------------------------------------------------------------


class AuthError(LlmClientError):
    """Credential / authentication errors."""


class Invalid(AuthError):
    """A credential was rejected by the provider.

    The raw key MUST NOT appear in any human-visible field. We store ONLY the
    4-char fingerprint for forensic correlation with the rotation log.
    """

    def __init__(self, raw_credential: str) -> None:
        # Defensive: fingerprint at construction, drop the raw reference.
        self.fingerprint = _fingerprint(raw_credential)
        # Deliberately do not keep `raw_credential` as an attribute; a future
        # reviewer shouldn't find a back door to the credential via `err.args`.
        super().__init__(
            f"credential rejected by provider (fingerprint={self.fingerprint})"
        )


class Expired(AuthError):
    """A credential is past its expiry window (e.g. an Entra access token)."""

    def __init__(self) -> None:
        super().__init__("credential expired; refresh required")


class MissingCredential(AuthError):
    """No credential was discovered for the deployment.

    `source_hint` is a human-readable description of the envelope that was
    searched (e.g. "OPENAI_API_KEY" or "AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY").
    The hint MUST NOT be a user-supplied string — it is a constant chosen by
    the loader.
    """

    def __init__(self, source_hint: str) -> None:
        self.source_hint = source_hint
        super().__init__(f"no credential found; checked envelope: {source_hint}")


# ---------------------------------------------------------------------------
# EndpointError — URL / reachability problems
# ---------------------------------------------------------------------------


class EndpointError(LlmClientError):
    """Endpoint (base_url / host / network) errors."""


class InvalidEndpoint(EndpointError):
    """The supplied endpoint failed validation.

    `reason` is a short code from a fixed set ("scheme", "private_ip",
    "metadata_service", "malformed_url", ...). `reason` MUST NOT contain the
    user-supplied URL; the URL MAY appear in the exception's private
    `_fingerprint` attribute for log correlation.
    """

    _REASON_ALLOWLIST = {
        "scheme",
        "private_ipv4",
        "private_ipv6",
        "loopback",
        "link_local",
        "metadata_service",
        "metadata_host",
        "malformed_url",
        "resolution_failed",
        "ipv4_mapped",
        "encoded_ip_bypass",
    }

    def __init__(self, reason: str, raw_url: Optional[str] = None) -> None:
        if reason not in self._REASON_ALLOWLIST:
            # Defensive — a caller who passed a raw URL as `reason` by mistake
            # would otherwise leak the URL into str(err). Enforce the allowlist.
            reason = "malformed_url"
        self.reason = reason
        self._fingerprint = _fingerprint(raw_url) if raw_url else None
        if self._fingerprint is not None:
            super().__init__(
                f"invalid endpoint: reason={reason} url_fingerprint={self._fingerprint}"
            )
        else:
            super().__init__(f"invalid endpoint: reason={reason}")


class Unreachable(EndpointError):
    """The endpoint resolved but could not be reached."""

    def __init__(self, host_fingerprint: Optional[str] = None) -> None:
        self.host_fingerprint = host_fingerprint
        if host_fingerprint is not None:
            super().__init__(
                f"endpoint unreachable (host_fingerprint={host_fingerprint})"
            )
        else:
            super().__init__("endpoint unreachable")


# ---------------------------------------------------------------------------
# ModelGrammarError — bad model / deployment grammar
# ---------------------------------------------------------------------------


class ModelGrammarError(LlmClientError):
    """The model string or deployment grammar is malformed."""


class ModelGrammarInvalid(ModelGrammarError):
    """`reason` is a short, caller-controlled error code.

    The reason MUST NOT echo user-supplied model strings verbatim; callers who
    want to include the name should pass a fingerprint.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"invalid model grammar: {reason}")


__all__ = [
    "LlmClientError",
    "LlmError",
    "Timeout",
    "RateLimited",
    "ProviderError",
    "InvalidResponse",
    "AuthError",
    "Invalid",
    "Expired",
    "MissingCredential",
    "EndpointError",
    "InvalidEndpoint",
    "Unreachable",
    "ModelGrammarError",
    "ModelGrammarInvalid",
]
