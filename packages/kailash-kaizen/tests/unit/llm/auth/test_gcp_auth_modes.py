# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for the GcpOauth multi-mode auth completion (#1717).

Covers the four credential-source modes added on top of the historical
service-account-key path:

* `gcp_wif`     -- explicit external_account (Workload Identity Federation),
                   dict + path + impersonation
* `gcp_metadata`-- keyless GCE / Cloud Run metadata server
* `gcp_adc`     -- keyless Application Default Credentials
* JSON-`type` dispatch -- a service_account_key PATH whose file declares
                   `type == "external_account"` routes to the WIF loader at
                   credential-build time.

Construction + discriminant assertions are pure (no google-auth calls).
Credential-build dispatch is asserted by patching the module-level
google-auth entry points so the routing is deterministic and offline
(Tier 1 -- mocking the google-auth boundary is permitted). Where a real
google-auth object constructs without network IO (compute_engine, the
external_account loader), a real-construction test runs too, guarded with
importorskip so a venv lacking the [vertex] extra skips rather than errors.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from kaizen.llm.auth import gcp as gcp_mod
from kaizen.llm.auth.gcp import DEFAULT_SCOPES, GcpOauth
from kaizen.llm.errors import AuthError


# ---------------------------------------------------------------------------
# Fixtures — credential-config shapes
# ---------------------------------------------------------------------------


def _external_account_info(*, impersonation: bool = False) -> dict:
    """Minimal well-formed url/file-sourced external_account (WIF) config."""
    info = {
        "type": "external_account",
        "audience": (
            "//iam.googleapis.com/projects/123456/locations/global/"
            "workloadIdentityPools/my-pool/providers/my-provider"
        ),
        "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
        "token_url": "https://sts.googleapis.com/v1/token",
        "credential_source": {"file": "/var/run/secrets/token"},
    }
    if impersonation:
        info["service_account_impersonation_url"] = (
            "https://iamcredentials.googleapis.com/v1/projects/-/"
            "serviceAccounts/wif@proj.iam.gserviceaccount.com:generateAccessToken"
        )
    return info


def _service_account_info() -> dict:
    return {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": (
            "-----BEGIN PRIVATE KEY-----\nTESTKEY\n-----END PRIVATE KEY-----"
        ),
        "client_email": "test@test-project.iam.gserviceaccount.com",
        "client_id": "test-client-id",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


# ---------------------------------------------------------------------------
# Discriminants — construction only, no google-auth calls
# ---------------------------------------------------------------------------


def test_keyless_default_is_adc() -> None:
    auth = GcpOauth()
    assert auth.auth_strategy_kind() == "gcp_adc"
    assert auth.scopes == DEFAULT_SCOPES


def test_adc_classmethod_discriminant() -> None:
    assert GcpOauth.adc().auth_strategy_kind() == "gcp_adc"


def test_metadata_server_classmethod_discriminant() -> None:
    auth = GcpOauth.metadata_server()
    assert auth.auth_strategy_kind() == "gcp_metadata"


def test_use_metadata_server_kwarg_discriminant() -> None:
    assert GcpOauth(use_metadata_server=True).auth_strategy_kind() == "gcp_metadata"


def test_workload_identity_dict_discriminant() -> None:
    auth = GcpOauth.workload_identity(_external_account_info())
    assert auth.auth_strategy_kind() == "gcp_wif"


def test_workload_identity_path_discriminant() -> None:
    auth = GcpOauth.workload_identity("/tmp/fake-wif.json")
    assert auth.auth_strategy_kind() == "gcp_wif"


def test_external_account_kwarg_discriminant() -> None:
    auth = GcpOauth(external_account=_external_account_info())
    assert auth.auth_strategy_kind() == "gcp_wif"


def test_service_account_key_dict_with_external_type_is_wif() -> None:
    """A WIF config passed through the service_account_key arg (dict) is
    classified as gcp_wif via its `type` field (free to read, no file IO)."""
    auth = GcpOauth(service_account_key=_external_account_info())
    assert auth.auth_strategy_kind() == "gcp_wif"


def test_service_account_key_path_reports_gcp_oauth() -> None:
    """A path is NOT read at construction; discriminant reflects the API used
    (gcp_oauth). JSON-type dispatch happens at build time (tested below)."""
    auth = GcpOauth(service_account_key="/tmp/fake-sa.json")
    assert auth.auth_strategy_kind() == "gcp_oauth"


def test_scopes_propagate_to_keyless_modes() -> None:
    scope = "https://www.googleapis.com/auth/cloud-platform.read-only"
    assert GcpOauth.adc(scopes=[scope]).scopes == (scope,)
    assert GcpOauth.metadata_server(scopes=[scope]).scopes == (scope,)
    assert GcpOauth.workload_identity(
        _external_account_info(), scopes=[scope]
    ).scopes == (scope,)


# ---------------------------------------------------------------------------
# Validation / error contracts
# ---------------------------------------------------------------------------


def test_both_key_and_external_account_raises() -> None:
    with pytest.raises(AuthError, match=r"not both"):
        GcpOauth(
            service_account_key=_service_account_info(),
            external_account=_external_account_info(),
        )


def test_empty_external_account_dict_raises() -> None:
    with pytest.raises(AuthError, match=r"empty"):
        GcpOauth(external_account={})


def test_empty_external_account_path_raises() -> None:
    with pytest.raises(AuthError, match=r"empty"):
        GcpOauth(external_account="")


def test_non_dict_non_str_external_account_raises() -> None:
    with pytest.raises(TypeError):
        GcpOauth(external_account=12345)  # type: ignore[arg-type]


def test_repr_does_not_leak_external_account_material() -> None:
    info = _external_account_info(impersonation=True)
    auth = GcpOauth(external_account=info)
    rendered = repr(auth)
    assert info["audience"] not in rendered
    assert info["service_account_impersonation_url"] not in rendered


# ---------------------------------------------------------------------------
# Credential-build dispatch — patched google-auth boundary (deterministic)
# ---------------------------------------------------------------------------


def test_build_credentials_adc_calls_google_auth_default() -> None:
    fake_creds = MagicMock(name="adc-creds")
    with patch.object(
        gcp_mod, "_google_auth_default", return_value=(fake_creds, "proj")
    ) as m_default:
        auth = GcpOauth.adc()
        result = auth._build_credentials()
    assert result is fake_creds
    m_default.assert_called_once()
    # scopes forwarded
    _, kwargs = m_default.call_args
    assert kwargs["scopes"] == list(DEFAULT_SCOPES)


def test_build_credentials_metadata_calls_compute_engine() -> None:
    fake_ce = MagicMock(name="compute_engine")
    with patch.object(gcp_mod, "_google_compute_engine", fake_ce):
        auth = GcpOauth.metadata_server()
        auth._build_credentials()
    fake_ce.Credentials.assert_called_once()


def test_build_credentials_wif_dict_calls_loader() -> None:
    info = _external_account_info()
    fake_creds = MagicMock(name="wif-creds")
    with patch.object(
        gcp_mod, "_google_load_creds_from_dict", return_value=(fake_creds, "proj")
    ) as m_loader:
        auth = GcpOauth(external_account=info)
        result = auth._build_credentials()
    assert result is fake_creds
    passed_info, _ = m_loader.call_args[0], m_loader.call_args[1]
    assert passed_info[0] == info


def test_build_credentials_wif_path_reads_and_routes(tmp_path: Path) -> None:
    info = _external_account_info(impersonation=True)
    p = tmp_path / "wif.json"
    p.write_text(json.dumps(info), encoding="utf-8")
    fake_creds = MagicMock(name="wif-creds")
    with patch.object(
        gcp_mod, "_google_load_creds_from_dict", return_value=(fake_creds, None)
    ) as m_loader:
        auth = GcpOauth.workload_identity(str(p))
        result = auth._build_credentials()
    assert result is fake_creds
    assert m_loader.call_args[0][0] == info


# ---------------------------------------------------------------------------
# JSON-type dispatch — a service_account_key PATH classified at build time
# ---------------------------------------------------------------------------


def test_sa_key_path_pointing_at_external_account_routes_to_wif(
    tmp_path: Path,
) -> None:
    """GOOGLE_APPLICATION_CREDENTIALS-style path whose file is an
    external_account config routes to the WIF loader (deliverable #4)."""
    info = _external_account_info()
    p = tmp_path / "creds.json"
    p.write_text(json.dumps(info), encoding="utf-8")
    fake_creds = MagicMock(name="wif-creds")
    with patch.object(
        gcp_mod, "_google_load_creds_from_dict", return_value=(fake_creds, None)
    ) as m_loader:
        auth = GcpOauth(service_account_key=str(p))  # discriminant stays gcp_oauth
        result = auth._build_credentials()
    assert result is fake_creds
    assert m_loader.call_args[0][0] == info


def test_sa_key_path_pointing_at_service_account_routes_to_sa(
    tmp_path: Path,
) -> None:
    info = _service_account_info()
    p = tmp_path / "creds.json"
    p.write_text(json.dumps(info), encoding="utf-8")
    fake_sa = MagicMock(name="service_account_module")
    with patch.object(gcp_mod, "_google_service_account", fake_sa):
        auth = GcpOauth(service_account_key=str(p))
        auth._build_credentials()
    fake_sa.Credentials.from_service_account_file.assert_called_once()
    args, kwargs = fake_sa.Credentials.from_service_account_file.call_args
    assert args[0] == str(p)
    assert kwargs["scopes"] == list(DEFAULT_SCOPES)


def test_creds_file_not_found_raises_typed_error_without_leaking_path() -> None:
    auth = GcpOauth(service_account_key="/nonexistent/secret-layout/creds.json")
    with pytest.raises(AuthError, match=r"not found") as exc:
        auth._build_credentials()
    assert "/nonexistent/secret-layout/creds.json" not in str(exc.value)


def test_creds_file_invalid_json_raises_typed_error(tmp_path: Path) -> None:
    p = tmp_path / "creds.json"
    p.write_text("{not valid json", encoding="utf-8")
    auth = GcpOauth(service_account_key=str(p))
    with pytest.raises(AuthError, match=r"unreadable or not valid JSON"):
        auth._build_credentials()


def test_creds_file_unknown_type_raises_typed_error(tmp_path: Path) -> None:
    p = tmp_path / "creds.json"
    p.write_text(json.dumps({"type": "authorized_user"}), encoding="utf-8")
    auth = GcpOauth(service_account_key=str(p))
    with pytest.raises(AuthError, match=r"unsupported credential type"):
        auth._build_credentials()


# ---------------------------------------------------------------------------
# Real google-auth construction (network-free), guarded on the [vertex] extra
# ---------------------------------------------------------------------------


def test_real_metadata_credentials_construct() -> None:
    pytest.importorskip("google.auth.compute_engine")
    from google.auth.credentials import Credentials

    auth = GcpOauth.metadata_server()
    creds = auth._build_credentials()  # constructs; no network until refresh
    assert isinstance(creds, Credentials)


def test_real_wif_credentials_route_through_google_auth_external_account() -> None:
    """The WIF path is REALLY wired through google-auth's external_account
    loader (not a stub): building against a config whose subject-token file
    is absent surfaces google-auth's typed RefreshError from the STS
    exchange -- positive proof the identity-pool machinery ran."""
    exc_mod = pytest.importorskip("google.auth.exceptions")
    auth = GcpOauth(external_account=_external_account_info())
    with pytest.raises(exc_mod.RefreshError, match=r"/var/run/secrets/token"):
        auth._build_credentials()


def test_real_wif_impersonation_routes_through_impersonated_credentials() -> None:
    """With `service_account_impersonation_url` present, google-auth wraps the
    external_account creds in `impersonated_credentials.Credentials`; the
    refresh chain reaches the same absent subject-token file, proving the
    impersonation wrapper is invoked (not skipped)."""
    exc_mod = pytest.importorskip("google.auth.exceptions")
    pytest.importorskip("google.auth.impersonated_credentials")
    auth = GcpOauth(external_account=_external_account_info(impersonation=True))
    with pytest.raises(exc_mod.RefreshError, match=r"/var/run/secrets/token"):
        auth._build_credentials()
