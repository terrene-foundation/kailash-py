# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Error sanitizer for LLM provider exceptions.

Strips API keys, bearer tokens, URL-embedded credentials, and internal
paths from provider exception messages before they are exposed to callers
or logged in multi-tenant environments.

See D5 in workspaces/byok-hardening for the threat model.
"""

from __future__ import annotations

import re
from typing import List

__all__ = [
    "sanitize_provider_error",
    "generic_provider_error",
]

# Compiled regex patterns for credential detection
_CREDENTIAL_PATTERNS: List[re.Pattern] = [
    # OpenAI keys (sk-..., sk-proj-...)
    re.compile(r"sk-[a-zA-Z0-9_-]{20,}", re.ASCII),
    # Anthropic keys (sk-ant-...)
    re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}", re.ASCII),
    # Google API keys (AIza...)
    re.compile(r"AIza[a-zA-Z0-9_-]{30,}", re.ASCII),
    # Perplexity keys (pplx-...)
    re.compile(r"pplx-[a-zA-Z0-9]{20,}", re.ASCII),
    # AWS access-key IDs (AKIA + 16 upper-alnum) — Bedrock provider path (#1960).
    re.compile(r"AKIA[0-9A-Z]{16}", re.ASCII),
    # Generic hex tokens (32+ chars, common in Azure/other services).
    # #1960: case-INSENSITIVE ([a-fA-F0-9]) — the prior lowercase-only rule let
    # uppercase/mixed-case hex (e.g. "A1B2C3...") slip through unredacted.
    re.compile(r"\b[a-fA-F0-9]{32,}\b", re.ASCII),
    # Slack tokens (#1974). The full `xox[baprse]-` family: bot / app / user /
    # refresh / session / token-rotation. Segment separators ("-") break the
    # 40-char contiguous-run rule below, so no other pattern claims these.
    # The family letter is enumerated (NOT [a-z]) so ordinary hyphenated prose
    # such as "xoxo-..." is not swept up.
    re.compile(r"\bxox[baprse]-[A-Za-z0-9-]{10,}", re.ASCII),
    # Bare (non-"Bearer") JWTs (#1974). The three-segment
    # header.payload.signature structure is what makes this discriminating:
    # "eyJ" is merely base64 for '{"', so ANY base64-encoded JSON object starts
    # with it. Requiring two "."-separated follow-on segments means an ordinary
    # base64 payload in an error string is NOT redacted, while a real token is.
    # Base64URL alphabet ([A-Za-z0-9_-]) — "-"/"_"/"." all break the 40-char
    # contiguous-run rule below, which is why bare JWTs previously slipped.
    re.compile(
        r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}", re.ASCII
    ),
    # GitHub PATs / OAuth tokens. Structurally identical to the Slack rule
    # above: an opaque secret behind a fixed vendor prefix whose "_" separator
    # breaks the 40-char contiguous-run rule below. A ``ghp_`` body is exactly
    # 36 chars — four short of the threshold — so nothing previously claimed it.
    # The "_" also defeats the generic-hex rule above (``\b`` cannot fire
    # between "_" and the body), even for an all-hex-alphabet body.
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}", re.ASCII),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}", re.ASCII),
    # Stripe secret / restricted keys. The ``sk-`` rule at the top of this list
    # requires a HYPHEN; Stripe spells its prefix with an UNDERSCORE
    # (``sk_live_`` / ``rk_test_``), so the underscore form was never matched
    # and the body is well under the 40-char contiguous-run threshold.
    re.compile(r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}", re.ASCII),
    # AWS 40-char base64 secret access keys ([A-Za-z0-9/+]{40}) — #1960.
    #
    # FALSE-POSITIVE-vs-SENSITIVITY DECISION: we deliberately ACCEPT broad
    # over-redaction here rather than anchor to AWS-secret context. Rationale:
    #   (1) A sanitizer MUST err toward over-redacting secrets — under-redaction
    #       leaks a live credential (the strictly worse failure); over-redaction
    #       only blanks a token in an error string a human still gets the gist of.
    #   (2) A 40+ char contiguous run of [A-Za-z0-9/+] essentially never occurs
    #       in legitimate human-readable error prose (words are space-separated,
    #       ~<=20 chars). The only 40-char contiguous runs are tokens / secrets /
    #       hashes / signed-URL query tokens — all safe (indeed desirable) to
    #       redact. Negative-vector tests confirm normal error text is untouched.
    #   (3) Anchoring to an "aws"/"secret" keyword would MISS a secret that
    #       appears bare in a raw exception string — the common real case.
    # {40,} is greedy, so it spans the whole run (no partial mid-token match).
    re.compile(r"[A-Za-z0-9/+]{40,}", re.ASCII),
    # Bearer tokens in error messages
    re.compile(r"Bearer\s+[a-zA-Z0-9._-]+", re.ASCII),
    # Partial key exposure (OpenAI style: "sk-tenA...B12C")
    re.compile(r"sk-[a-zA-Z0-9]{3,4}\.\.\.[a-zA-Z0-9]{3,4}", re.ASCII),
]

# URL-embedded credentials (user:pass@host).
#
# #1974: the scheme is ANY RFC-3986 scheme, not just http(s). Connection
# strings for postgres / redis / mongodb / mysql / amqp all embed credentials
# in the same userinfo position, and the prior `https?://` anchor left every
# one of them unredacted. The scheme class `[A-Za-z][A-Za-z0-9+.-]*` also
# covers driver-qualified forms (`postgresql+asyncpg://`, `mongodb+srv://`).
#
# The userinfo quantifiers are `*`, NOT `+`. `redis://:pass@host` — a DSN with
# an EMPTY username — is the conventional redis/rediss shape, and `+` requires a
# non-empty username, so it would leak exactly the vector #1974 gap 1 names.
# `*` costs no precision: the match still requires a literal `:`, a terminating
# `@`, and the scheme prefix, which do not co-occur in a credential-free URL
# (a bare `host:port/path` URL has no `@` to anchor on).
#
# The userinfo character class is `[^\s]`, NOT `[^@\s]`. RFC 3986 requires an
# `@` inside userinfo to be percent-encoded, but real-world DSNs routinely carry
# a literal one in either half (`user:p@ssw0rd@host`, `ad@corp.com:pw@host`).
# Excluding `@` stops the match at the FIRST one and redacts only the prefix,
# leaving the rest of the secret in the output — a partial leak. Because both
# halves are greedy and `\s` still terminates them, the match extends to the
# LAST `@` of the same whitespace-delimited token, so the whole credential goes.
# This trades a little over-redaction for no under-redaction, per the
# false-positive-vs-sensitivity decision documented above.
#
# Both halves are LENGTH-BOUNDED ({0,256}), which is a DoS bound, not a
# coverage one. Two adjacent unbounded greedy runs joined by a literal make the
# no-match case quadratic in token length: on a colon-dense token with no `@`
# the engine retries every `:` against every suffix. Measured on a synthetic
# 32 KB `http://a:a:a:...` string that is O(seconds) of CPU per call on an
# error path an attacker can influence (a provider echoing back user input).
# The bound makes the per-start-position work constant, so the whole scan is
# linear. 256 is ~an order of magnitude above any real DSN userinfo.
#
# The bound alone would leave a COVERAGE HOLE, so it is paired with the
# overflow rule below. (An earlier revision of this comment claimed a longer
# secret "is claimed by the 40-char contiguous-run rule above instead" — that
# is FALSE for any secret containing `-`, `_` or `.`, since those are outside
# `[A-Za-z0-9/+]` and break the run. A 272-char hyphenated DSN password leaked
# in full. Verified, not assumed.)
#
# Group 1 (the scheme) is preserved by the replacement, so no replacement-side
# change is needed for the broadened scheme.
_URL_WITH_AUTH = re.compile(
    r"([A-Za-z][A-Za-z0-9+.-]{0,31}://)[^\s]{0,256}:[^\s]{0,256}@", re.ASCII
)

# Overflow companion to `_URL_WITH_AUTH` — catches a userinfo LONGER than the
# 256-char DoS bound above (e.g. a Cloud SQL IAM OAuth access token used as the
# DSN password), which that rule's bound would otherwise leak in full.
#
# The FIRST run excludes `:` as well as `@`/whitespace, and that exclusion is
# load-bearing for COMPLEXITY, not for matching. An earlier revision used
# `[^\s@]*:[^\s@]*@` — allowing `:` in the first run — which is QUADRATIC on a
# colon-dense non-matching token: the first run matches to the end, then retries
# against every interior `:`, and for each split the second run rescans the
# tail. Measured on `"http://" + "a:"*n`: 4 KB → 59 ms, 16 KB → 923 ms,
# 64 KB → 14.8 s. Stopping the first run at the FIRST `:` makes the split point
# deterministic, so the scan is linear (same input: single-digit ms).
# Do NOT "simplify" this back to `[^\s@]*` — that reintroduces the DoS.
#
# The `@`-INSIDE-userinfo case is deliberately NOT handled here — the bounded
# rule above already owns it, and secrets long enough to overflow that bound
# overwhelmingly carry no literal `@`.
#
# The `:` is REQUIRED so this stays credential-shaped: without it an ordinary
# `https://example.com/@handle` (a very common profile URL) would be redacted.
_URL_WITH_AUTH_OVERFLOW = re.compile(
    r"([A-Za-z][A-Za-z0-9+.-]{0,31}://)[^\s@:]*:[^\s@]*@", re.ASCII
)

# Userinfo with NO password half — `scheme://<token>@host`.
#
# BOTH rules above require a `:`, so a bare token in the USERNAME position was
# never redacted by either. That is the standard shape for git-over-HTTPS with a
# PAT (`https://<token>@github.com/org/repo`) and for APIs that accept a token as
# HTTP-basic username. Only credentials carrying a recognised vendor prefix were
# incidentally caught (by `_CREDENTIAL_PATTERNS`); an opaque token leaked in full.
# Pre-existing — the original `https?://[^@\s]+:[^@\s]+@` required the colon too.
#
# `/` is excluded from the userinfo class so a PATH segment can never be mistaken
# for userinfo: `https://example.com/@handle` (a common profile URL) stops at the
# `/` and does not match, and neither does `git://host/user@thing`.
# Only the scheme is kept — there is no user/pass split to preserve here.
#
# ACCEPTED RESIDUAL (documented deliberately, per the false-positive-vs-
# sensitivity posture above): a userinfo token CONTAINING `/` and shorter than
# 40 chars is NOT claimed — e.g. `https://AbCd+9/xYz123456789@api.example.com`.
# Three reasons this is accepted rather than closed:
#   1. RFC 3986 ends the authority at the first `/`, so a `/` before the `@`
#      means the `@` is in the PATH, not userinfo — the shape is malformed as a
#      URL, not a well-formed credential-bearing one.
#   2. Admitting `/` here would redact `https://example.com/some/path/@handle`,
#      a common and entirely credential-free shape, destroying diagnostics on
#      the far more frequent case.
#   3. A `/`-bearing token of 40+ contiguous `[A-Za-z0-9/+]` IS already claimed
#      by the AWS-secret rule above, so only the short-and-slashed window is
#      open — and base64 secrets in that window are below every provider's key
#      length.
# If a real leak of this shape is ever observed, the correct fix is a
# LENGTH-ANCHORED companion (`[^\s@]{N,}@`), not widening this class.
_URL_WITH_USERINFO_ONLY = re.compile(
    r"([A-Za-z][A-Za-z0-9+.-]{0,31}://)[^\s@:/]+@", re.ASCII
)

# Azure OpenAI endpoint hostname (#1960). The <resource> subdomain is the
# customer's Azure resource name — sensitive infra identity that reveals the
# tenant. Redact the resource while keeping the ".openai.azure.com" suffix so
# the message still reads as "an Azure OpenAI endpoint".
_AZURE_OPENAI_ENDPOINT = re.compile(
    r"https://[A-Za-z0-9][A-Za-z0-9-]*\.openai\.azure\.com", re.ASCII
)

# Internal file paths that could reveal infrastructure
_INTERNAL_PATH_PATTERNS: List[re.Pattern] = [
    re.compile(r"/home/[a-zA-Z0-9_-]+/", re.ASCII),
    re.compile(r"/Users/[a-zA-Z0-9_-]+/", re.ASCII),
    re.compile(r"C:\\Users\\[a-zA-Z0-9_-]+\\", re.ASCII),
]


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
    raw = str(error)
    sanitized = raw

    # Replace credential patterns
    for pattern in _CREDENTIAL_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)

    # Replace URL-embedded credentials. The bounded rule runs FIRST because it
    # is the one that handles a literal `@` inside the userinfo; the overflow
    # companion then claims any userinfo too long for that rule's DoS bound.
    sanitized = _URL_WITH_AUTH.sub(r"\1[REDACTED]:[REDACTED]@", sanitized)
    sanitized = _URL_WITH_AUTH_OVERFLOW.sub(r"\1[REDACTED]:[REDACTED]@", sanitized)
    # Runs LAST: the two user:pass rules above have already rewritten their
    # matches to `scheme://[REDACTED]:[REDACTED]@`, which contains a `:` and so
    # is not re-matched by this no-colon rule. Ordering therefore keeps the
    # user/pass shape visible where one existed, and only collapses userinfo
    # that genuinely had no password half.
    sanitized = _URL_WITH_USERINFO_ONLY.sub(r"\1[REDACTED]@", sanitized)

    # Redact the resource name in Azure OpenAI endpoints (keep the suffix).
    sanitized = _AZURE_OPENAI_ENDPOINT.sub(
        "https://[REDACTED].openai.azure.com", sanitized
    )

    # Replace internal file paths
    for pattern in _INTERNAL_PATH_PATTERNS:
        sanitized = pattern.sub("[PATH]/", sanitized)

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
