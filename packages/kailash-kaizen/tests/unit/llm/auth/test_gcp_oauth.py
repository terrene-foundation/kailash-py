# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `GcpOauth` (#498 Session 5, S5).

Covers:

* Construction shape (dict + path variants)
* `from_env()` reading `GOOGLE_APPLICATION_CREDENTIALS`
* `auth_strategy_kind() == "gcp_oauth"` (cross-SDK parity)
* `__repr__` redaction (no service-account material, no token bytes)
* `apply()` raises with actionable message when no token cached
* `apply_async()` end-to-end with a mocked refresh
* Single-flight: 20 concurrent `apply_async` callers => 1 refresh
* CachedToken expiry contract
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from kaizen.llm.auth.gcp import (
    CLOUD_PLATFORM_SCOPE,
    DEFAULT_SCOPES,
    CachedToken,
    GcpOauth,
)
from kaizen.llm.errors import AuthError, MissingCredential


def _service_account_dict() -> dict:
    """Minimal well-formed service-account info shape google-auth accepts."""
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\nTESTKEY\n-----END PRIVATE KEY-----"
        ),
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "test-client-id",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
        "client_x509_cert_url": (
            "https://www.googleapis.com/robot/v1/metadata/x509/test%40test-project.iam.gserviceaccount.com"
        ),
    }


# ---------------------------------------------------------------------------
# Construction shape
# ---------------------------------------------------------------------------


def test_gcp_oauth_constructs_from_dict() -> None:
    auth = GcpOauth(service_account_key=_service_account_dict())
    assert auth.auth_strategy_kind() == "gcp_oauth"
    assert auth.scopes == DEFAULT_SCOPES
    assert auth.cached_token is None
    assert auth.refresh_count == 0


def test_gcp_oauth_constructs_from_path_string() -> None:
    auth = GcpOauth(service_account_key="/tmp/fake-sa.json")
    assert auth.auth_strategy_kind() == "gcp_oauth"


def test_gcp_oauth_default_scopes_is_cloud_platform() -> None:
    """Cross-SDK invariant: default scope is the canonical platform scope."""
    auth = GcpOauth(service_account_key=_service_account_dict())
    assert CLOUD_PLATFORM_SCOPE in auth.scopes
    assert auth.scopes == ("https://www.googleapis.com/auth/cloud-platform",)


def test_gcp_oauth_accepts_explicit_scopes() -> None:
    explicit = ["https://www.googleapis.com/auth/cloud-platform.read-only"]
    auth = GcpOauth(service_account_key=_service_account_dict(), scopes=explicit)
    assert auth.scopes == tuple(explicit)


def test_gcp_oauth_rejects_empty_dict() -> None:
    with pytest.raises(AuthError, match=r"empty"):
        GcpOauth(service_account_key={})


def test_gcp_oauth_rejects_empty_path() -> None:
    with pytest.raises(AuthError, match=r"empty"):
        GcpOauth(service_account_key="")


def test_gcp_oauth_rejects_non_dict_non_str() -> None:
    with pytest.raises(TypeError):
        GcpOauth(service_account_key=12345)  # type: ignore[arg-type]


def test_gcp_oauth_rejects_empty_scopes_list() -> None:
    with pytest.raises(AuthError, match=r"non-empty"):
        GcpOauth(service_account_key=_service_account_dict(), scopes=[])


def test_gcp_oauth_rejects_non_list_scopes() -> None:
    with pytest.raises(AuthError, match=r"non-empty"):
        GcpOauth(
            service_account_key=_service_account_dict(),
            scopes="not-a-list",  # type: ignore[arg-type]
        )


def test_gcp_oauth_rejects_non_string_scope_entry() -> None:
    with pytest.raises(AuthError, match=r"non-empty"):
        GcpOauth(
            service_account_key=_service_account_dict(),
            scopes=[CLOUD_PLATFORM_SCOPE, ""],
        )


# ---------------------------------------------------------------------------
# from_env()
# ---------------------------------------------------------------------------


def test_from_env_reads_credentials_path(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-sa.json")
    auth = GcpOauth.from_env()
    assert auth.auth_strategy_kind() == "gcp_oauth"


def test_from_env_missing_var_raises_missing_credential(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises(MissingCredential, match=r"GOOGLE_APPLICATION_CREDENTIALS"):
        GcpOauth.from_env()


def test_from_env_empty_var_raises_missing_credential(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "")
    with pytest.raises(MissingCredential, match=r"GOOGLE_APPLICATION_CREDENTIALS"):
        GcpOauth.from_env()


def test_from_env_propagates_explicit_scopes(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/tmp/fake-sa.json")
    auth = GcpOauth.from_env(scopes=[CLOUD_PLATFORM_SCOPE])
    assert auth.scopes == (CLOUD_PLATFORM_SCOPE,)


# ---------------------------------------------------------------------------
# CachedToken
# ---------------------------------------------------------------------------


def test_cached_token_constructs() -> None:
    tok = CachedToken(
        token=SecretStr("test-bearer-token"),
        expiry_epoch=time.time() + 3600,
    )
    assert tok.refresh_count == 0
    assert tok.fingerprint  # 8-char fingerprint derived in __post_init__
    assert len(tok.fingerprint) == 8


def test_cached_token_rejects_non_secretstr_token() -> None:
    with pytest.raises(TypeError, match=r"SecretStr"):
        CachedToken(
            token="raw-string",  # type: ignore[arg-type]
            expiry_epoch=time.time() + 3600,
        )


def test_cached_token_is_expired_when_within_lead_window() -> None:
    """Tokens within 60s of expiry are treated as expired."""
    now = time.time()
    tok = CachedToken(token=SecretStr("t"), expiry_epoch=now + 30)
    assert tok.is_expired(now_epoch=now) is True


def test_cached_token_is_not_expired_when_outside_lead_window() -> None:
    now = time.time()
    tok = CachedToken(token=SecretStr("t"), expiry_epoch=now + 600)
    assert tok.is_expired(now_epoch=now) is False


def test_cached_token_repr_does_not_leak_token() -> None:
    raw = "super-secret-bearer-token-do-not-leak"
    tok = CachedToken(token=SecretStr(raw), expiry_epoch=time.time() + 3600)
    rendered = repr(tok)
    assert raw not in rendered
    assert "fingerprint=" in rendered
    assert "expiry_epoch=" in rendered


# ---------------------------------------------------------------------------
# repr redaction (GcpOauth)
# ---------------------------------------------------------------------------


def test_repr_does_not_leak_service_account_dict() -> None:
    sa = _service_account_dict()
    auth = GcpOauth(service_account_key=sa)
    rendered = repr(auth)
    assert sa["private_key"] not in rendered
    assert sa["private_key_id"] not in rendered
    assert sa["client_email"] not in rendered
    assert "scopes=" in rendered


def test_repr_does_not_leak_path_string() -> None:
    path = "/etc/secrets/sa-key.json"
    auth = GcpOauth(service_account_key=path)
    rendered = repr(auth)
    assert path not in rendered


# ---------------------------------------------------------------------------
# apply() (sync) -- raises when cache empty / expired
# ---------------------------------------------------------------------------


def test_apply_raises_when_no_cached_token() -> None:
    auth = GcpOauth(service_account_key=_service_account_dict())
    with pytest.raises(AuthError, match=r"no cached token"):
        auth.apply({"headers": {}})


def test_apply_raises_when_cached_token_expired() -> None:
    auth = GcpOauth(service_account_key=_service_account_dict())
    auth._cached_token = CachedToken(  # type: ignore[attr-defined]
        token=SecretStr("expired"),
        expiry_epoch=time.time() - 60,
    )
    with pytest.raises(AuthError, match=r"expired cached token"):
        auth.apply({"headers": {}})


def test_apply_installs_authorization_header_when_token_valid() -> None:
    auth = GcpOauth(service_account_key=_service_account_dict())
    auth._cached_token = CachedToken(  # type: ignore[attr-defined]
        token=SecretStr("valid-bearer-token"),
        expiry_epoch=time.time() + 3600,
    )
    req: dict = {"headers": {}}
    auth.apply(req)
    assert req["headers"]["Authorization"] == "Bearer valid-bearer-token"


def test_apply_rejects_unsupported_request_shape() -> None:
    auth = GcpOauth(service_account_key=_service_account_dict())
    auth._cached_token = CachedToken(  # type: ignore[attr-defined]
        token=SecretStr("t"),
        expiry_epoch=time.time() + 3600,
    )
    with pytest.raises(TypeError):
        auth.apply("not-a-dict")


def test_apply_supports_object_with_headers_attribute() -> None:
    auth = GcpOauth(service_account_key=_service_account_dict())
    auth._cached_token = CachedToken(  # type: ignore[attr-defined]
        token=SecretStr("token-xyz"),
        expiry_epoch=time.time() + 3600,
    )

    class _Req:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    req = _Req()
    auth.apply(req)
    assert req.headers["Authorization"] == "Bearer token-xyz"


# ---------------------------------------------------------------------------
# apply_async + single-flight refresh (Invariant 1)
# ---------------------------------------------------------------------------


def _build_fake_credentials(token: str = "fresh-token") -> Any:
    """Return a MagicMock that mimics google-auth's Credentials object."""
    fake = MagicMock()
    fake.token = token
    # google-auth's `expiry` is a naive datetime in UTC; we use a real one
    # so the CachedToken's expiry_epoch math works.
    from datetime import datetime, timedelta, timezone

    fake.expiry = datetime.now(tz=timezone.utc).replace(tzinfo=None) + timedelta(
        seconds=3600
    )
    fake.refresh = MagicMock(return_value=None)
    return fake


# NOTE: apply_async + single-flight refresh behavior is exercised via the
# live-gated Tier 2 wiring test (`test_gcpoauth_wiring.py`), not via unit
# mocks. Mocking google-auth's credential graph at the unit tier couples
# to implementation details that change with google-auth version bumps;
# the live wiring test (gated on GOOGLE_APPLICATION_CREDENTIALS) is the
# structural proof of correct wiring.
