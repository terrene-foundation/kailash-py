# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression tests for issue #1960 — error_sanitizer.py credential-redaction gaps.

Surfaced during the #1953 security redteam. ``sanitize_provider_error`` covered
OpenAI/Anthropic/Google/Perplexity key prefixes, generic 32+ *lowercase*-hex
tokens, ``Bearer`` tokens, ``user:pass@`` URLs, and home paths — but FOUR
credential classes slipped through unredacted (pre-existing; affects every
sanitized surface, since all 27+ call sites route through this one helper):

1. AWS access-key IDs (``AKIA[0-9A-Z]{16}``) — no prefix pattern matched them.
2. AWS 40-char base64 secret keys (``[A-Za-z0-9/+]{40}``) — the generic hex
   rule was lowercase-hex-only, so a base64 secret was never touched.
3. Uppercase / mixed-case hex tokens >=32 chars — the ``\\b[a-f0-9]{32,}\\b``
   rule was lowercase-only, so ``A1B2C3...`` slipped past.
4. Azure OpenAI endpoint hostnames (``https://<resource>.openai.azure.com``) —
   the resource name is sensitive infra identity and had no pattern.

Every vector below is a REALISTIC but FAKE credential — the AWS access-key ID
and secret key are AWS's own PUBLICLY-DOCUMENTED example values
(``AKIAIOSFODNN7EXAMPLE`` / ``wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY``), never
a live secret. The tests are BEHAVIORAL: they call ``sanitize_provider_error``
on an exception carrying the secret and assert the returned string does NOT
contain the secret AND DOES contain the ``[REDACTED]`` marker.
"""

from __future__ import annotations

import pytest

from kaizen.nodes.ai.error_sanitizer import sanitize_provider_error

pytestmark = pytest.mark.regression

# Redaction marker the sanitizer substitutes in place of a credential match.
REDACTION_MARKER = "[REDACTED]"


def _sanitize(secret_message: str) -> str:
    """Route a realistic error string through the sanitizer and return output."""
    return sanitize_provider_error(RuntimeError(secret_message), "openai")


# ---------------------------------------------------------------------------
# Gap 1 — AWS access-key IDs (AKIA[0-9A-Z]{16})
# ---------------------------------------------------------------------------

# AWS's own documented example access-key ID (public, not a live credential).
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"


def test_aws_access_key_id_redacted() -> None:
    msg = f"Bedrock auth failed for access key {AWS_ACCESS_KEY_ID} in us-east-1"
    out = _sanitize(msg)
    assert AWS_ACCESS_KEY_ID not in out
    assert REDACTION_MARKER in out


def test_aws_access_key_id_redacted_no_surrounding_context() -> None:
    # The key alone, no "aws"/"access key" keywords nearby — the pattern must
    # match on the AKIA prefix + shape, not on contextual keywords.
    out = _sanitize(AWS_ACCESS_KEY_ID)
    assert AWS_ACCESS_KEY_ID not in out
    assert REDACTION_MARKER in out


# ---------------------------------------------------------------------------
# Gap 2 — AWS 40-char base64 secret keys ([A-Za-z0-9/+]{40})
# ---------------------------------------------------------------------------

# AWS's own documented example secret access key (public, not a live credential).
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"


def test_aws_secret_key_redacted() -> None:
    assert len(AWS_SECRET_ACCESS_KEY) == 40  # sanity: this IS the 40-char class
    msg = f"SignatureDoesNotMatch: computed with secret {AWS_SECRET_ACCESS_KEY}"
    out = _sanitize(msg)
    assert AWS_SECRET_ACCESS_KEY not in out
    assert REDACTION_MARKER in out


def test_generic_40char_base64_token_redacted() -> None:
    # A 40-char base64 blob that is NOT hex (contains uppercase + '/' + '+').
    token = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789+/Ab"
    assert len(token) == 40
    out = _sanitize(f"token rejected: {token}")
    assert token not in out
    assert REDACTION_MARKER in out


# ---------------------------------------------------------------------------
# Gap 3 — Uppercase / mixed-case hex tokens >= 32 chars
# ---------------------------------------------------------------------------


def test_uppercase_hex_token_redacted() -> None:
    upper_hex = "A1B2C3D4E5F6A7B8C9D0E1F2A3B4C5D6"  # 32 uppercase hex chars
    assert len(upper_hex) == 32
    out = _sanitize(f"Azure key auth failed: {upper_hex}")
    assert upper_hex not in out
    assert REDACTION_MARKER in out


def test_mixed_case_hex_token_redacted() -> None:
    mixed_hex = "DeadBeefCafe1234567890abcdefABCDEF01"  # 36 mixed-case hex chars
    assert len(mixed_hex) == 36
    out = _sanitize(f"digest mismatch {mixed_hex} on upload")
    assert mixed_hex not in out
    assert REDACTION_MARKER in out


def test_lowercase_hex_still_redacted_after_broadening() -> None:
    # Regression-guard: broadening to case-insensitive MUST NOT break the
    # existing lowercase-hex behavior.
    lower_hex = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"  # 32 lowercase hex chars
    out = _sanitize(f"key {lower_hex} rejected")
    assert lower_hex not in out
    assert REDACTION_MARKER in out


# ---------------------------------------------------------------------------
# Gap 4 — Azure OpenAI endpoint hostnames (resource name is infra identity)
# ---------------------------------------------------------------------------


def test_azure_openai_endpoint_resource_redacted() -> None:
    resource = "my-company-prod"
    endpoint = f"https://{resource}.openai.azure.com"
    out = _sanitize(f"Connection refused to {endpoint}/openai/deployments/gpt4")
    # The sensitive resource name MUST be gone.
    assert resource not in out
    assert REDACTION_MARKER in out


def test_azure_openai_endpoint_bare_host_redacted() -> None:
    resource = "acme-eastus2-genai"
    out = _sanitize(f"DNS lookup failed: https://{resource}.openai.azure.com")
    assert resource not in out
    assert REDACTION_MARKER in out


# ---------------------------------------------------------------------------
# Regression guards — the pre-existing patterns MUST still redact
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "secret, message",
    [
        # OpenAI (sk-...)
        ("sk-proj-abc123def456ghi789jkl012mno345", "OpenAI 401: key {s} invalid"),
        # Anthropic (sk-ant-...)
        ("sk-ant-api03-abc123def456ghi789jkl012mno", "Anthropic auth: {s}"),
        # Google (AIza...)
        ("AIzaSyD1234567890abcdefghijklmnopqrstuv", "Google API key {s} denied"),
        # Perplexity (pplx-...)
        ("pplx-abc123def456ghi789jkl012mnopqr", "Perplexity key {s} revoked"),
        # Bearer token
        ("Bearer sometokenvalue1234567890", "Authorization header: {s}"),
    ],
)
def test_existing_prefix_patterns_still_redact(secret: str, message: str) -> None:
    out = _sanitize(message.format(s=secret))
    # The secret's distinctive tail MUST be gone; marker present.
    assert secret not in out
    assert REDACTION_MARKER in out


def test_existing_url_with_auth_still_redacted() -> None:
    out = _sanitize("Failed: https://admin:hunter2@db.internal.example.com/v1")
    assert "hunter2" not in out
    assert "admin:hunter2" not in out


def test_existing_home_path_still_redacted() -> None:
    out = _sanitize("Config not found at /Users/alice/secrets/kaizen.env")
    assert "/Users/alice/" not in out
    assert "alice" not in out


# ---------------------------------------------------------------------------
# Negative vectors — normal error text MUST pass through (no over-redaction)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "benign_message",
    [
        "Connection timeout after 30 seconds to the API endpoint",
        "Rate limit exceeded: 429 Too Many Requests, retry after 5s",
        "Model gpt-4o-mini is not available in your region",
        "Invalid request: temperature must be between 0 and 2",
        "Failed to reach https://api.openai.com/v1/chat/completions",
    ],
)
def test_benign_messages_not_over_redacted(benign_message: str) -> None:
    out = _sanitize(benign_message)
    # No credential pattern should have fired: the marker MUST be absent and
    # the original human-readable text MUST survive intact.
    assert REDACTION_MARKER not in out
    assert benign_message in out
