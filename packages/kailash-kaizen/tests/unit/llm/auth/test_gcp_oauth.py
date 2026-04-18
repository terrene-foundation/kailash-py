# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""GcpOauth shape + repr redaction tests (#498 S5)."""

from __future__ import annotations

import os

import pytest

from kaizen.llm.auth.gcp import (
    CLOUD_PLATFORM_SCOPE,
    DEFAULT_SCOPES,
    GcpOauth,
)
from kaizen.llm.errors import AuthError, LlmClientError, MissingCredential


def _sa_dict() -> dict:
    """Minimal valid shape for a service-account dict stub.

    This is not a real key — it just has the fields google-auth inspects
    at construction time. Production tokens require google-auth actually
    calling the GCP token endpoint, which we don't do in unit tests.
    """
    return {
        "type": "service_account",
        "project_id": "unit-test-project",
        "private_key_id": "stub",
        "private_key": "-----BEGIN PRIVATE KEY-----\nSTUB\n-----END PRIVATE KEY-----\n",
        "client_email": "stub@unit-test-project.iam.gserviceaccount.com",
        "client_id": "0",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_gcp_oauth_accepts_dict_key() -> None:
    auth = GcpOauth(service_account_key=_sa_dict())
    assert auth.auth_strategy_kind() == "gcp_oauth"


def test_gcp_oauth_accepts_path_string() -> None:
    auth = GcpOauth(service_account_key="/path/to/key.json")
    assert auth.auth_strategy_kind() == "gcp_oauth"


def test_gcp_oauth_rejects_empty_dict() -> None:
    with pytest.raises(AuthError):
        GcpOauth(service_account_key={})


def test_gcp_oauth_rejects_empty_path() -> None:
    with pytest.raises(AuthError):
        GcpOauth(service_account_key="")


def test_gcp_oauth_rejects_wrong_type() -> None:
    with pytest.raises(TypeError):
        GcpOauth(service_account_key=42)  # type: ignore[arg-type]


def test_gcp_oauth_custom_scopes() -> None:
    scopes = ["https://www.googleapis.com/auth/cloud-platform.read-only"]
    auth = GcpOauth(service_account_key=_sa_dict(), scopes=scopes)
    # strategy_kind is stable regardless of scope
    assert auth.auth_strategy_kind() == "gcp_oauth"


def test_gcp_oauth_rejects_empty_scopes_list() -> None:
    with pytest.raises(AuthError):
        GcpOauth(service_account_key=_sa_dict(), scopes=[])


def test_gcp_oauth_rejects_non_string_scope() -> None:
    with pytest.raises(AuthError):
        GcpOauth(service_account_key=_sa_dict(), scopes=[""])  # empty string


def test_gcp_oauth_repr_does_not_leak_key() -> None:
    auth = GcpOauth(service_account_key=_sa_dict())
    r = repr(auth)
    # Raw key bytes MUST NOT appear.
    assert "STUB" not in r
    assert "BEGIN PRIVATE KEY" not in r


def test_cloud_platform_scope_is_stable() -> None:
    assert CLOUD_PLATFORM_SCOPE == "https://www.googleapis.com/auth/cloud-platform"
    assert DEFAULT_SCOPES == (CLOUD_PLATFORM_SCOPE,)


def test_gcp_oauth_from_env_requires_google_application_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    with pytest.raises((MissingCredential, LlmClientError, AuthError)):
        GcpOauth.from_env()


def test_gcp_oauth_from_env_reads_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/some/path/to/key.json")
    auth = GcpOauth.from_env()
    assert auth.auth_strategy_kind() == "gcp_oauth"
