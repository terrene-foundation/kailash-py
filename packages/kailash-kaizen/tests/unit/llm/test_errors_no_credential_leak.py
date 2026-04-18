# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Error taxonomy credential-leak tests (#498 S1).

Every error class that accepts user-controlled input (raw key, raw URL) MUST
route that input through a fingerprint before it reaches any human-visible
field (str, repr, args).
"""

from __future__ import annotations

import hashlib

from kaizen.llm.errors import Invalid, InvalidEndpoint, MissingCredential, ProviderError


def test_auth_error_invalid_does_not_echo_raw_key() -> None:
    raw = "sk-hunter2-classified-payload"
    err = Invalid(raw)
    s = str(err)
    assert raw not in s
    assert "hunter2" not in s
    assert "classified" not in s
    assert "payload" not in s
    # The fingerprint MUST be present for correlation.
    expected_fp = hashlib.sha256(raw.encode()).hexdigest()[:4]
    assert expected_fp in s
    # The `fingerprint` attribute is public for forensic correlation.
    assert err.fingerprint == expected_fp


def test_auth_error_invalid_does_not_store_raw_key() -> None:
    """There must be no back door to the raw credential via err attrs."""
    raw = "sk-hunter2-classified-payload"
    err = Invalid(raw)
    for attr_val in err.args:
        assert raw not in str(attr_val)


def test_invalid_endpoint_does_not_echo_raw_url() -> None:
    raw = "https://attacker.example.com/exfil?key=sk-hunter2"
    err = InvalidEndpoint(reason="private_ipv4", raw_url=raw)
    s = str(err)
    assert raw not in s
    assert "attacker.example.com" not in s
    assert "sk-hunter2" not in s


def test_invalid_endpoint_reason_allowlist() -> None:
    """Reason codes outside the allowlist fall back to 'malformed_url'."""
    evil_reason = "user\nsupplied\nmultiline\nreason"
    err = InvalidEndpoint(reason=evil_reason)
    assert err.reason == "malformed_url"
    assert evil_reason not in str(err)


def test_missing_credential_includes_source_hint() -> None:
    err = MissingCredential("OPENAI_API_KEY")
    s = str(err)
    assert "OPENAI_API_KEY" in s
    # Hint is caller-controlled (constant), so echoing is acceptable per
    # the class docstring.


def test_provider_error_truncates_long_body() -> None:
    big = "x" * 500
    err = ProviderError(status=500, body_snippet=big)
    assert len(err.body_snippet) <= 300  # 256 + truncation suffix
    assert "truncated" in err.body_snippet


# --- round-1 redteam M1 (security): credential scrub in ProviderError ---
def test_provider_error_scrubs_openai_key() -> None:
    """OpenAI sk-* key echoed in a 4xx body must NOT appear in str(err)."""
    body = "error: invalid key sk-hunter2xxxxxxxxxxxxxxxxxxxx"
    err = ProviderError(status=401, body_snippet=body)
    assert "sk-hunter2" not in str(err)
    assert "sk-hunter2" not in err.body_snippet
    assert "[REDACTED-CRED]" in err.body_snippet


def test_provider_error_scrubs_openai_project_key() -> None:
    """OpenAI sk-proj-* project key must be scrubbed."""
    body = (
        'error: {"message": "bad key: sk-proj-ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"}'
    )
    err = ProviderError(status=401, body_snippet=body)
    assert "sk-proj-" not in str(err)
    assert "[REDACTED-CRED]" in err.body_snippet


def test_provider_error_scrubs_anthropic_key() -> None:
    body = "error: bad key sk-ant-api-ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    err = ProviderError(status=401, body_snippet=body)
    assert "sk-ant-" not in str(err)
    assert "[REDACTED-CRED]" in err.body_snippet


def test_provider_error_scrubs_aws_access_key() -> None:
    body = 'error: {"message": "bad key: AKIAIOSFODNN7EXAMPLE"}'
    err = ProviderError(status=403, body_snippet=body)
    assert "AKIAIOSFODNN7EXAMPLE" not in str(err)
    assert "[REDACTED-CRED]" in err.body_snippet


def test_provider_error_scrubs_bearer_token() -> None:
    body = "Invalid Authorization header: Bearer abcdefghijklmnopqrstuvwxyz0123"
    err = ProviderError(status=401, body_snippet=body)
    assert "abcdefghijklmnopqrstuvwxyz0123" not in str(err)
    assert "[REDACTED-CRED]" in err.body_snippet


def test_provider_error_scrub_before_truncation() -> None:
    """Credential straddling the 256-char boundary must still be fully scrubbed."""
    # Put the key near the end so raw-truncate would chop it mid-pattern.
    filler = "x" * 240
    body = filler + "sk-hunter2xxxxxxxxxxxxxxxxxxxx"  # ~270 chars
    err = ProviderError(status=500, body_snippet=body)
    assert "sk-hunter2" not in str(err)
    assert "sk-hunter2" not in err.body_snippet


def test_provider_error_scrub_does_not_false_positive_on_short_sk() -> None:
    """A 'sk-' prefix with <20 chars after must NOT be matched by the pattern."""
    # This is a legit non-credential string — e.g., a name like "sk-abc"
    # should survive unscrubbed (20-char minimum on the pattern).
    body = "no credential here, sk-abc short"
    err = ProviderError(status=500, body_snippet=body)
    assert "sk-abc" in err.body_snippet
    assert "[REDACTED-CRED]" not in err.body_snippet
