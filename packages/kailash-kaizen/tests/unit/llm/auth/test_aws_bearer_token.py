# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `AwsBearerToken` (#498 Session 3, S4a).

Covers:

* Construction shape + header application
* Region allowlist enforcement (no default region, rejected on unknown)
* `from_env()` with `AWS_BEARER_TOKEN_BEDROCK` + `AWS_REGION`
* `__repr__` does NOT leak the raw token (fingerprint only)
* `auth_strategy_kind` == "aws_bearer_token" (cross-SDK parity)
"""

from __future__ import annotations

import pytest
from pydantic import SecretStr

from kaizen.llm.auth.aws import (
    BEDROCK_SUPPORTED_REGIONS,
    AwsBearerToken,
    RegionNotAllowed,
)
from kaizen.llm.auth.bearer import ApiKey
from kaizen.llm.errors import MissingCredential

# ---------------------------------------------------------------------------
# Shape + header application
# ---------------------------------------------------------------------------


def test_aws_bearer_token_constructs_with_str_token() -> None:
    t = AwsBearerToken(token="bedrock-bearer-token-abc123", region="us-east-1")
    assert t.region == "us-east-1"
    assert t.auth_strategy_kind() == "aws_bearer_token"


def test_aws_bearer_token_accepts_secretstr_token() -> None:
    t = AwsBearerToken(token=SecretStr("bedrock-bearer-xyz"), region="eu-west-1")
    assert t.region == "eu-west-1"


def test_aws_bearer_token_accepts_apikey_token() -> None:
    key = ApiKey("bedrock-bearer-pre-wrapped")
    t = AwsBearerToken(token=key, region="ap-southeast-1")
    # Fingerprint matches the pre-wrapped ApiKey's fingerprint.
    assert t.fingerprint == key.fingerprint


def test_aws_bearer_token_rejects_non_string_token() -> None:
    with pytest.raises(TypeError):
        AwsBearerToken(token=12345, region="us-east-1")  # type: ignore[arg-type]


def test_aws_bearer_token_rejects_empty_token() -> None:
    from kaizen.llm.errors import AuthError

    with pytest.raises(AuthError):
        AwsBearerToken(token="", region="us-east-1")


def test_aws_bearer_token_apply_sets_authorization_header_dict() -> None:
    t = AwsBearerToken(token="bedrock-abc", region="us-east-1")
    req: dict = {"headers": {}}
    returned = t.apply(req)
    assert returned is req  # mutates in place
    assert req["headers"]["Authorization"] == "Bearer bedrock-abc"


def test_aws_bearer_token_apply_sets_authorization_header_object() -> None:
    t = AwsBearerToken(token="bedrock-xyz", region="eu-west-1")

    class _Req:
        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

    req = _Req()
    t.apply(req)
    assert req.headers["Authorization"] == "Bearer bedrock-xyz"


def test_aws_bearer_token_apply_rejects_unsupported_request_shape() -> None:
    t = AwsBearerToken(token="bedrock-abc", region="us-east-1")
    with pytest.raises(TypeError):
        t.apply("not-a-dict-not-an-object-with-headers")


def test_aws_bearer_token_refresh_is_noop() -> None:
    t = AwsBearerToken(token="bedrock-abc", region="us-east-1")
    assert t.refresh() is None


# ---------------------------------------------------------------------------
# Region allowlist
# ---------------------------------------------------------------------------


def test_aws_bearer_token_accepts_all_published_regions() -> None:
    """Every region in the cross-SDK allowlist constructs successfully."""
    for region in BEDROCK_SUPPORTED_REGIONS:
        t = AwsBearerToken(token="bedrock-token", region=region)
        assert t.region == region


def test_aws_bearer_token_rejects_unknown_region() -> None:
    with pytest.raises(RegionNotAllowed, match=r"eu-central-2"):
        AwsBearerToken(token="bedrock-token", region="eu-central-2")


def test_aws_bearer_token_rejects_no_default_region() -> None:
    """Per env-models.md: there is NO default region; empty string rejects."""
    with pytest.raises(RegionNotAllowed):
        AwsBearerToken(token="bedrock-token", region="")


def test_aws_bearer_token_rejects_region_with_leading_whitespace() -> None:
    """Exact-match membership; no whitespace tolerance."""
    with pytest.raises(RegionNotAllowed):
        AwsBearerToken(token="bedrock-token", region=" us-east-1")


def test_aws_bearer_token_rejects_non_string_region() -> None:
    with pytest.raises(RegionNotAllowed):
        AwsBearerToken(token="bedrock-token", region=12345)  # type: ignore[arg-type]


def test_aws_bearer_token_rejects_host_shaped_region_string() -> None:
    """Defense-in-depth: an attacker-influenced region that looks like a
    hostname fragment MUST be rejected. Prevents the
    `bedrock-runtime.{region}.amazonaws.com` template from being abused.
    """
    with pytest.raises(RegionNotAllowed):
        AwsBearerToken(token="bedrock-token", region="attacker.com")


def test_region_allowlist_byte_identical_to_rust_spec() -> None:
    """The allowlist MUST byte-match the Rust SDK constant (cross-SDK parity).

    Source of truth:
    `kailash-rs/crates/kailash-kaizen/src/llm/deployment/bedrock.rs::BEDROCK_REGIONS`.
    """
    # Explicit enumeration -- refresh when the Rust list changes.
    rust_regions = (
        "us-east-1",
        "us-east-2",
        "us-west-2",
        "us-gov-east-1",
        "us-gov-west-1",
        "ca-central-1",
        "sa-east-1",
        "eu-central-1",
        "eu-west-1",
        "eu-west-2",
        "eu-west-3",
        "eu-north-1",
        "eu-south-1",
        "eu-south-2",
        "ap-south-1",
        "ap-southeast-1",
        "ap-southeast-2",
        "ap-southeast-3",
        "ap-southeast-4",
        "ap-southeast-5",
        "ap-northeast-1",
        "ap-northeast-2",
        "ap-northeast-3",
        "ap-east-1",
        "me-south-1",
        "me-central-1",
        "af-south-1",
    )
    assert BEDROCK_SUPPORTED_REGIONS == rust_regions


# ---------------------------------------------------------------------------
# from_env()
# ---------------------------------------------------------------------------


def test_from_env_reads_token_and_region(monkeypatch) -> None:
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-env-abc123")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-1")
    t = AwsBearerToken.from_env()
    assert t.region == "ap-northeast-1"
    assert t.auth_strategy_kind() == "aws_bearer_token"


def test_from_env_missing_token_raises_missing_credential(monkeypatch) -> None:
    monkeypatch.delenv("AWS_BEARER_TOKEN_BEDROCK", raising=False)
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    with pytest.raises(MissingCredential, match=r"AWS_BEARER_TOKEN_BEDROCK"):
        AwsBearerToken.from_env()


def test_from_env_empty_token_raises_missing_credential(monkeypatch) -> None:
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    with pytest.raises(MissingCredential, match=r"AWS_BEARER_TOKEN_BEDROCK"):
        AwsBearerToken.from_env()


def test_from_env_missing_region_raises_region_not_allowed(monkeypatch) -> None:
    """No default region; unset AWS_REGION rejects loudly."""
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-env-token")
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(RegionNotAllowed):
        AwsBearerToken.from_env()


def test_from_env_unknown_region_rejects(monkeypatch) -> None:
    monkeypatch.setenv("AWS_BEARER_TOKEN_BEDROCK", "bedrock-env-token")
    monkeypatch.setenv("AWS_REGION", "mars-east-1")
    with pytest.raises(RegionNotAllowed):
        AwsBearerToken.from_env()


# ---------------------------------------------------------------------------
# repr redaction -- token MUST NOT appear in any human-visible form
# ---------------------------------------------------------------------------


def test_repr_does_not_leak_token() -> None:
    secret = "bedrock-super-secret-token-long-enough-to-notice-12345"
    t = AwsBearerToken(token=secret, region="us-west-2")
    rendered = repr(t)
    assert secret not in rendered
    # Must still be grep-able by fingerprint for forensic correlation.
    assert t.fingerprint in rendered
    assert "us-west-2" in rendered


def test_str_does_not_leak_token() -> None:
    secret = "bedrock-ssshhh-secret-12345"
    t = AwsBearerToken(token=secret, region="us-east-1")
    assert secret not in str(t)
