# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Credential scrubber for natural-language brief inputs.

User-supplied briefs ("a workflow that reads from
``postgres://admin:hunter2@db:5432/app`` and ...") routinely embed live
credentials. Logging the raw brief, sending the raw brief to an LLM,
or persisting the raw brief in a workspace artifact each leaks those
credentials into a log aggregator, a third-party LLM provider's
training set, or a long-lived audit trail.

``scrub_brief()`` is the single function every ``from_brief()``
primitive MUST run BEFORE any logging or LLM call. Per
``rules/security.md`` § "No secrets in logs" and § "Credential Decode
Helpers", credentials in URLs route through the shared
``kailash.utils.url_credentials`` module so the masking contract is
uniform across the codebase.

Origin: issue #1125 — the brief is the user's natural-language intent
AND a credential-shaped attack surface; scrubbing on intake is the
structural defense.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit, urlunsplit

__all__ = ["scrub_brief"]


# Compile-once patterns. Order matters: URL with credentials is checked
# first (it is the most specific shape); standalone API-key shapes are
# checked second (they may appear alone, without a URL); bearer-token
# headers and AWS access keys are checked last.

# URL with embedded userinfo: ``scheme://user:password@host[:port][/path]``.
# Captures the entire URL for replacement. The credential portion is
# extracted from the captured URL via ``urlsplit`` so the masking
# matches what ``kailash.utils.url_credentials.mask_url`` would emit.
_URL_WITH_CREDS = re.compile(
    r"(?P<url>[A-Za-z][A-Za-z0-9+.\-]*://[^\s:/]+:[^\s@]+@[^\s]+)"
)

# OpenAI/Anthropic-style API-key shape: ``sk-`` followed by ≥20 chars of
# base64-ish content. Matches ``sk-proj-…``, ``sk-ant-…``, plain ``sk-…``.
# The 20-char floor avoids matching short literals like ``sk-1`` in
# documentation text.
_API_KEY_SK = re.compile(r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}\b")

# Bearer-token header value: ``Bearer <token>`` where token is ≥20 chars.
# Captures both the prefix and the token so the prefix can be preserved
# in the scrubbed output (the prefix is not sensitive; the token is).
_BEARER_TOKEN = re.compile(r"\b(Bearer)\s+[A-Za-z0-9._\-]{20,}\b")

# AWS access-key shape: 20-char string starting with ``AKIA``.
_AWS_ACCESS_KEY = re.compile(r"\bAKIA[A-Z0-9]{16}\b")

# Standalone ``password=<value>`` or ``api_key=<value>`` kv-pair shapes.
# Captures the prefix so the kv-key is preserved; the value is replaced.
_KV_SECRET = re.compile(
    r"\b(password|api[_-]?key|apikey|secret|token)\s*=\s*\S+",
    re.IGNORECASE,
)


_REDACTED = "[REDACTED]"


def _mask_url_credentials(url: str) -> str:
    """Return ``url`` with the userinfo portion replaced by ``***``.

    Uses :func:`urllib.parse.urlsplit` to preserve scheme, host, port,
    path, query, and fragment exactly. Only the userinfo segment is
    replaced. Matches the canonical mask shape from
    ``kailash.utils.url_credentials`` (``scheme://***@host[:port]/path``).
    """
    try:
        parts = urlsplit(url)
    except ValueError:
        # Unparseable URL — return the redaction sentinel for the
        # whole match. This branch is defensive; the regex above only
        # matches strings that should parse, but a pathological input
        # MUST NOT propagate the credential through the helper.
        return _REDACTED
    if not parts.hostname:
        return _REDACTED
    host = parts.hostname
    if parts.port:
        host = f"{host}:{parts.port}"
    netloc = f"***@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def scrub_brief(brief: str) -> str:
    """Replace credential-shaped substrings in ``brief`` with sentinels.

    Runs five mechanical sweeps over the input in this order:

    1. URLs with embedded ``user:password@`` — replaced with the
       canonical masked form ``scheme://***@host[:port]/path``.
    2. ``sk-…`` API keys — replaced with ``[REDACTED]``.
    3. ``Bearer <token>`` headers — token replaced with ``[REDACTED]``,
       the ``Bearer`` prefix preserved.
    4. AWS access keys (``AKIA…``) — replaced with ``[REDACTED]``.
    5. ``password=<value>`` / ``api_key=<value>`` kv-pairs — value
       replaced with ``[REDACTED]``, the key preserved.

    The function is **idempotent**: every sentinel is itself a no-op
    under the patterns, so ``scrub_brief(scrub_brief(x)) ==
    scrub_brief(x)`` for every input.

    Args:
        brief: The user's natural-language brief, possibly containing
            credentials.

    Returns:
        The brief with credential substrings replaced by sentinels.
        The structural prose of the brief is preserved so the LLM
        downstream can still reason about the intent (a brief saying
        "connect to ``postgres://***@db/app``" still tells the LLM
        what database technology is in play).
    """
    if not brief:
        return brief

    # Pass 1: URL with credentials.
    def _url_sub(match: re.Match[str]) -> str:
        return _mask_url_credentials(match.group("url"))

    scrubbed = _URL_WITH_CREDS.sub(_url_sub, brief)

    # Pass 2: standalone API keys.
    scrubbed = _API_KEY_SK.sub(_REDACTED, scrubbed)

    # Pass 3: bearer tokens — preserve the ``Bearer`` prefix.
    scrubbed = _BEARER_TOKEN.sub(lambda m: f"{m.group(1)} {_REDACTED}", scrubbed)

    # Pass 4: AWS access keys.
    scrubbed = _AWS_ACCESS_KEY.sub(_REDACTED, scrubbed)

    # Pass 5: kv-pair secrets — preserve the key.
    scrubbed = _KV_SECRET.sub(lambda m: f"{m.group(1)}={_REDACTED}", scrubbed)

    return scrubbed
