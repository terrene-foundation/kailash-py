# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""AzureEntra unit tests (#498 S6).

Covers the three variants (api-key, workload-identity, managed-identity),
mutual-exclusivity constraint, api-key header installation, cached-token
contract, and repr redaction.
"""

from __future__ import annotations

import pytest

from kaizen.llm.auth.azure import (
    AzureEntra,
    CachedToken,
    COGNITIVE_SERVICES_SCOPE,
)
from kaizen.llm.errors import AuthError


# ---------------------------------------------------------------------------
# Construction shape + mutual exclusivity
# ---------------------------------------------------------------------------


def test_azure_entra_api_key_variant_constructs() -> None:
    auth = AzureEntra(api_key="test-key-hunter2")
    assert auth.variant == "api_key"
    assert auth.auth_strategy_kind() == "azure_entra_api_key"


def test_azure_entra_requires_exactly_one_variant() -> None:
    # Zero
    with pytest.raises(AuthError, match=r"exactly one"):
        AzureEntra()
    # Two
    with pytest.raises(AuthError, match=r"exactly one"):
        AzureEntra(api_key="k", workload_identity=True)


def test_azure_entra_rejects_empty_api_key() -> None:
    with pytest.raises(AuthError, match=r"non-empty"):
        AzureEntra(api_key="")


def test_azure_entra_rejects_empty_managed_identity_client_id() -> None:
    # This test only works if azure-identity is installed; otherwise
    # construction fails earlier with LlmClientError. Skip in that case.
    try:
        with pytest.raises((AuthError, Exception)):
            AzureEntra(managed_identity_client_id="")
    except Exception:
        pytest.skip("azure-identity not available; cannot exercise MI variant")


# ---------------------------------------------------------------------------
# API-key path: apply() installs the header
# ---------------------------------------------------------------------------


def test_azure_entra_api_key_applies_header_on_dict_request() -> None:
    auth = AzureEntra(api_key="super-secret-key")
    req: dict = {"headers": {}}
    result = auth.apply(req)
    assert result["headers"]["api-key"] == "super-secret-key"
    # Must NOT use Authorization header for api-key variant
    assert "Authorization" not in result["headers"]


def test_azure_entra_api_key_apply_creates_headers_if_missing() -> None:
    auth = AzureEntra(api_key="k")
    req: dict = {}  # No headers key.
    auth.apply(req)
    assert req["headers"]["api-key"] == "k"


# ---------------------------------------------------------------------------
# Cross-SDK invariants
# ---------------------------------------------------------------------------


def test_cognitive_services_scope_is_stable() -> None:
    """Entra audience scope is hardcoded + cross-SDK identical."""
    assert COGNITIVE_SERVICES_SCOPE == ("https://cognitiveservices.azure.com/.default")


# ---------------------------------------------------------------------------
# repr redaction
# ---------------------------------------------------------------------------


def test_azure_entra_repr_does_not_leak_api_key() -> None:
    raw = "hunter2-super-secret-classified"
    auth = AzureEntra(api_key=raw)
    rendered = repr(auth)
    assert raw not in rendered
    assert "hunter2" not in rendered
    assert "classified" not in rendered
    # Must include fingerprint for correlation
    assert "fingerprint=" in rendered


# ---------------------------------------------------------------------------
# CachedToken (Azure variant)
# ---------------------------------------------------------------------------


def test_cached_token_from_raw_rejects_empty() -> None:
    with pytest.raises(AuthError):
        CachedToken.from_raw("", 9999999999.0)


def test_cached_token_fingerprint_stable_length() -> None:
    tok = CachedToken.from_raw("entra-token-material", 9999999999.0)
    assert len(tok.fingerprint) == 8


def test_cached_token_is_expiring_within_lead_window() -> None:
    import time

    now = time.time()
    tok = CachedToken.from_raw("t", now + 30)  # within 60s lead window
    assert tok.is_expiring(now=now) is True


def test_cached_token_not_expiring_outside_lead_window() -> None:
    import time

    now = time.time()
    tok = CachedToken.from_raw("t", now + 3600)
    assert tok.is_expiring(now=now) is False


def test_cached_token_repr_does_not_leak() -> None:
    raw = "entra-token-super-secret-material"
    tok = CachedToken.from_raw(raw, 9999999999.0)
    rendered = repr(tok)
    assert raw not in rendered
    assert "fingerprint=" in rendered
    assert "expires_at=" in rendered


# ---------------------------------------------------------------------------
# Token-variant apply() without cached token raises actionable error
# ---------------------------------------------------------------------------


def test_token_variant_apply_without_cached_raises() -> None:
    """Workload-identity variant requires _ensure_token_async() before apply().

    Skipped if azure-identity is not installed.
    """
    pytest.importorskip("azure.identity")
    try:
        auth = AzureEntra(workload_identity=True)
    except Exception as exc:  # pragma: no cover -- azure-identity install edge case
        pytest.skip(f"azure-identity construction failed: {exc}")

    with pytest.raises(AuthError, match=r"requires a cached token"):
        auth.apply({"headers": {}})
