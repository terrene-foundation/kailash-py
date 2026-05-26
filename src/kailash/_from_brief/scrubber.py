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

from kailash.utils.url_credentials import preencode_password_special_chars

__all__ = ["scrub_brief"]


# SEC-4: pre-encoder pre-pass. The URL regex below assumes the password
# is ``[^\s@]+`` — i.e. the @ character is the userinfo/host separator
# and CANNOT appear in the password. A raw ``@`` in the password
# (``postgres://admin:hunt@er#1@db/app``) defeats the regex's
# non-greedy non-@ class and the credential leaks. The shared helper
# at ``kailash.utils.url_credentials.preencode_password_special_chars``
# percent-encodes ``#$@?`` in the password portion BEFORE any regex
# runs, so the URL becomes well-formed and the existing mask path
# can redact it. Per
# workspaces/from-brief-1125/04-validate/round-02-security.md:108-124
# AND rules/security.md § "Credential Decode Helpers" rule 2
# (encode + decode in one helper module).
_URL_CANDIDATE = re.compile(r"[A-Za-z][A-Za-z0-9+.\-]*://\S+")


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

# SEC-3: extended credential corpus. Each pattern uses tight word
# boundaries to avoid false positives. Sources: GitHub Docs (PAT
# shapes), Google API key shape, Slack API tokens, RFC 7519 JWT
# compact serialization, Stripe API key documentation, Twilio
# access-token format. See
# workspaces/from-brief-1125/04-validate/round-02-security.md:78-103
# for the full threat model + corpus citation.

# GitHub tokens — legacy short prefixes (ghp_, gho_, ghu_, ghs_, ghr_)
# AND the new fine-grained ``github_pat_<11chars>_<59chars>`` form.
# Both are still issued by GitHub as of the 2026 PAT cohort.
_GITHUB_TOKEN = re.compile(
    r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b" r"|\bgithub_pat_[A-Za-z0-9_]{20,}\b"
)

# Google API key shape (39 chars total, ``AIza`` + 35 base64-ish).
_GOOGLE_API_KEY = re.compile(r"\bAIza[A-Za-z0-9_\-]{35}\b")

# Slack tokens — workspace bot/oauth/personal/refresh.
_SLACK_TOKEN = re.compile(r"\bxox[bopars]-[A-Za-z0-9\-]{10,}\b")

# JWT compact serialization — three base64url segments separated by
# dots. First two segments start with ``ey`` because JSON header /
# payload always begin with ``{"``. The third (signature) is opaque.
_JWT_TOKEN = re.compile(r"\bey[A-Za-z0-9_\-]+\.ey[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")

# Stripe API keys — live + test, publishable (pk_), secret (sk_),
# restricted (rk_) variants.
_STRIPE_KEY = re.compile(r"\b(?:sk|pk|rk)_(?:test|live)_[A-Za-z0-9]{20,}\b")

# Twilio account/auth tokens — start with ``SK`` then 32 hex chars.
_TWILIO_KEY = re.compile(r"\bSK[a-f0-9]{32}\b")

# Standalone ``password=<value>`` or ``api_key=<value>`` kv-pair shapes.
# Captures the prefix so the kv-key is preserved; the value is replaced.
_KV_SECRET = re.compile(
    r"\b(password|api[_-]?key|apikey|secret|token)\s*=\s*\S+",
    re.IGNORECASE,
)


_REDACTED = "[REDACTED]"

# SEC-7: maximum brief length before scrubbing. Applied at every
# `from_brief()` entry point (all 5 surfaces compose `scrub_brief`
# as Pass 0). The cap protects against (a) cost amplification on
# the LLM round-trip, (b) regex pathological-backtrack risk on a
# megabyte input, (c) DoS on any future MCP-exposed surface. The
# 64 KiB ceiling leaves room for prose + structured context;
# user-pasted briefs are typically <2 KiB. See
# workspaces/from-brief-1125/04-validate/round-02-security.md:168-175.
MAX_BRIEF_LENGTH: int = 64_000


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

    # SEC-7 length cap: fail loud BEFORE any regex / LLM call so a
    # 1 MB brief cannot exhaust cost / runtime budgets. Lazy import to
    # avoid a circular import (exceptions imports the validator which
    # imports the scrubber indirectly).
    if len(brief) > MAX_BRIEF_LENGTH:
        from kailash._from_brief.exceptions import BriefInterpretationError

        raise BriefInterpretationError(
            f"brief exceeds {MAX_BRIEF_LENGTH}-byte cap " f"(got {len(brief)} bytes)",
            malformed=True,
        )

    # SEC-4 Pass 0: pre-encode raw ``#$@?`` in passwords for every URL
    # candidate in the brief. The helper handles one URL at a time, so
    # we find URL-shaped substrings, route each through the helper,
    # and reassemble. This makes a brief containing
    # ``postgres://admin:hunt@er#1@db/app`` become
    # ``postgres://admin:hunt%40er%231@db/app`` BEFORE the URL regex
    # runs, so the regex's ``[^\s@]+`` password class matches cleanly.
    def _preencode(match: re.Match[str]) -> str:
        return preencode_password_special_chars(match.group(0))

    brief = _URL_CANDIDATE.sub(_preencode, brief)

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

    # SEC-3 passes 4a–4f: extended credential corpus. Each replaces
    # the matched substring with the canonical sentinel. Order between
    # these is irrelevant — the shapes do not overlap.
    scrubbed = _GITHUB_TOKEN.sub(_REDACTED, scrubbed)
    scrubbed = _GOOGLE_API_KEY.sub(_REDACTED, scrubbed)
    scrubbed = _SLACK_TOKEN.sub(_REDACTED, scrubbed)
    scrubbed = _JWT_TOKEN.sub(_REDACTED, scrubbed)
    scrubbed = _STRIPE_KEY.sub(_REDACTED, scrubbed)
    scrubbed = _TWILIO_KEY.sub(_REDACTED, scrubbed)

    # Pass 5: kv-pair secrets — preserve the key.
    scrubbed = _KV_SECRET.sub(lambda m: f"{m.group(1)}={_REDACTED}", scrubbed)

    return scrubbed
