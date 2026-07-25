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

# URL-embedded credentials (user:pass@host)
_URL_WITH_AUTH = re.compile(r"(https?://)[^@\s]+:[^@\s]+@", re.ASCII)

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

    # Replace URL-embedded credentials
    sanitized = _URL_WITH_AUTH.sub(r"\1[REDACTED]:[REDACTED]@", sanitized)

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
