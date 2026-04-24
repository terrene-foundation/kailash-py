# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for ``fingerprint_secret`` (issue #613).

Closes CodeQL findings ``py/weak-sensitive-data-hashing`` at
``packages/kailash-kaizen/src/kaizen/llm/auth/azure.py:166`` and
``packages/kailash-mcp/src/kailash_mcp/auth/providers.py:190``. Those
call sites used ``hashlib.sha256(api_key.encode()).hexdigest()[:8]`` to
derive a short, non-reversible fingerprint for log/__repr__ correlation
— NOT for credential verification. CodeQL cannot distinguish that
intent from misused password hashing and flags the sites as HIGH.

The fix routes every fingerprint use-case through
``kailash.utils.url_credentials.fingerprint_secret`` which uses BLAKE2b
and carries a docstring pinning the intent (correlation, not
verification). Password verification MUST use argon2-cffi / bcrypt —
see helper docstring for the rationale.
"""

from __future__ import annotations

import pytest

from kailash.utils.url_credentials import fingerprint_secret


class TestFingerprintSecret:
    def test_returns_hex_of_requested_length(self) -> None:
        assert len(fingerprint_secret("sk-1234567890abcdef")) == 8
        assert len(fingerprint_secret("x", length=16)) == 16
        assert len(fingerprint_secret("x", length=4)) == 4

    def test_deterministic(self) -> None:
        """Same input always produces the same fingerprint (correlation)."""
        a = fingerprint_secret("sk-1234567890abcdef")
        b = fingerprint_secret("sk-1234567890abcdef")
        assert a == b

    def test_distinct_inputs_produce_distinct_fingerprints(self) -> None:
        a = fingerprint_secret("sk-api-alice")
        b = fingerprint_secret("sk-api-bob")
        # 32-bit output = ~1 in 4 billion collision probability
        assert a != b

    def test_empty_input(self) -> None:
        """Empty string yields a stable sentinel rather than a secret-
        derived value. Ensures log lines are still grep-able when the
        source value is missing without falsely implying a hashed secret."""
        assert fingerprint_secret("") == "00000000"

    def test_hex_only(self) -> None:
        """Output contains only lowercase hex characters — safe for IDs,
        log fields, and URL path components."""
        out = fingerprint_secret("sk-1234567890abcdef", length=16)
        assert all(c in "0123456789abcdef" for c in out)

    def test_not_reversible(self) -> None:
        """Sanity: the output is NOT the input (non-reversible)."""
        secret = "sk-1234567890abcdef"
        assert fingerprint_secret(secret) != secret[:8]


class TestFingerprintSecretCallSites:
    """Verify the CodeQL-flagged call sites route through the helper
    and produce correlation-grade fingerprints.

    These Tier-1 unit tests import the call sites through the framework
    facades and assert the fingerprint shape downstream consumers will see.
    """

    def test_azure_entra_api_key_fingerprint(self) -> None:
        pytest.importorskip(
            "kaizen.llm.auth.azure", reason="kailash-kaizen not installed editable"
        )
        from kaizen.llm.auth.azure import AzureEntra

        a = AzureEntra(api_key="sk-alice-api-key-1234567890")
        # Non-empty, 8-char hex fingerprint.
        fp = a._api_key_fingerprint
        assert isinstance(fp, str) and len(fp) == 8
        assert all(c in "0123456789abcdef" for c in fp)
        # Deterministic — two constructions for the same api_key produce
        # the same fingerprint.
        b = AzureEntra(api_key="sk-alice-api-key-1234567890")
        assert a._api_key_fingerprint == b._api_key_fingerprint

    def test_mcp_api_key_provider_user_id_shape(self) -> None:
        pytest.importorskip(
            "kailash_mcp.auth.providers",
            reason="kailash-mcp not installed editable",
        )
        from kailash_mcp.auth.providers import APIKeyAuth

        provider = APIKeyAuth(keys={"test-key-xyz": {"permissions": ["r"]}})
        result = provider.authenticate({"api_key": "test-key-xyz"})
        assert result["user_id"].startswith("api_key_")
        # "api_key_" + 8 hex chars.
        assert len(result["user_id"]) == len("api_key_") + 8
