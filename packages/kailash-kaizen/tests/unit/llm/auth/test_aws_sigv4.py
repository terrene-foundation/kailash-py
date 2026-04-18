# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for `AwsSigV4` (#498 Session 3, S4b-i).

Covers:

* Signing delegates to `botocore.auth.SigV4Auth`
* Region allowlist enforcement
* Clock-skew window (5 minutes)
* Streaming content-sha256 header
* Credential rotation under `asyncio.Lock`
* `auth_strategy_kind` == "aws_sigv4"
* `__repr__` does NOT leak credentials
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from pydantic import SecretStr

from kaizen.llm.auth.aws import AwsCredentials, AwsSigV4, ClockSkew, RegionNotAllowed
from kaizen.llm.errors import AuthError


def _make_credentials(region: str = "us-east-1") -> AwsCredentials:
    return AwsCredentials(
        access_key_id=SecretStr("AKIAIOSFODNN7EXAMPLE"),
        secret_access_key=SecretStr("wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"),
        session_token=None,
        region=region,
    )


# ---------------------------------------------------------------------------
# Construction + region allowlist
# ---------------------------------------------------------------------------


def test_aws_sigv4_constructs() -> None:
    sig = AwsSigV4(_make_credentials())
    assert sig.auth_strategy_kind() == "aws_sigv4"
    assert sig.credentials.region == "us-east-1"


def test_aws_sigv4_rejects_unknown_region() -> None:
    bad = AwsCredentials(
        access_key_id=SecretStr("AKIA1"),
        secret_access_key=SecretStr("s1"),
        session_token=None,
        region="mars-east-1",
    )
    with pytest.raises(RegionNotAllowed):
        AwsSigV4(bad)


def test_aws_sigv4_rejects_non_awscredentials() -> None:
    with pytest.raises(TypeError):
        AwsSigV4({"access_key_id": "x"})  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Signing delegates to botocore
# ---------------------------------------------------------------------------


def test_aws_sigv4_sign_delegates_to_botocore() -> None:
    """Invariant 6: SigV4 canonicalization routes through
    `botocore.auth.SigV4Auth.add_auth`. We spy on `add_auth` and assert
    it is invoked exactly once per sign() call.
    """
    sig = AwsSigV4(_make_credentials())
    with patch(
        "kaizen.llm.auth.aws._BotocoreSigV4Auth",
        autospec=True,
    ) as mock_cls:
        mock_instance = MagicMock()
        mock_cls.return_value = mock_instance
        signed = sig.sign(
            method="POST",
            url="https://bedrock-runtime.us-east-1.amazonaws.com/model/x/invoke",
            headers={"Content-Type": "application/json"},
            body=b'{"prompt": "hello"}',
        )
    mock_cls.assert_called_once()
    mock_instance.add_auth.assert_called_once()
    # Headers passthrough on the returned dict (botocore is mocked out so
    # the headers don't have actual signature fields, but the dict shape
    # is preserved).
    assert isinstance(signed, dict)


def test_aws_sigv4_sign_produces_real_signature_with_botocore() -> None:
    """Integration-flavored unit test: actually run botocore.SigV4Auth and
    observe the resulting Authorization header. This is the contract-level
    test that would catch a botocore API drift.
    """
    sig = AwsSigV4(_make_credentials())
    signed = sig.sign(
        method="POST",
        url="https://bedrock-runtime.us-east-1.amazonaws.com/model/x/invoke",
        headers={"Content-Type": "application/json"},
        body=b'{"prompt": "hello"}',
    )
    # botocore's SigV4 sets 'Authorization' starting with 'AWS4-HMAC-SHA256'
    assert "Authorization" in signed
    assert signed["Authorization"].startswith("AWS4-HMAC-SHA256")
    # The canonical sigv4 flow also installs x-amz-date.
    assert "X-Amz-Date" in signed or "x-amz-date" in signed


# ---------------------------------------------------------------------------
# Streaming content-sha256 header (invariant 9)
# ---------------------------------------------------------------------------


def test_aws_sigv4_streaming_sets_content_sha256_header() -> None:
    sig = AwsSigV4(_make_credentials())
    signed = sig.sign(
        method="POST",
        url="https://bedrock-runtime.us-east-1.amazonaws.com/model/x/invoke-with-response-stream",
        headers={"Content-Type": "application/vnd.amazon.eventstream"},
        body=b"",
        streaming=True,
    )
    # Header keys are case-insensitive in HTTP; botocore lower-cases.
    content_sha = signed.get("x-amz-content-sha256") or signed.get(
        "X-Amz-Content-SHA256"
    )
    assert content_sha == "STREAMING-AWS4-HMAC-SHA256-PAYLOAD"


def test_aws_sigv4_non_streaming_does_not_force_streaming_hash() -> None:
    sig = AwsSigV4(_make_credentials())
    signed = sig.sign(
        method="POST",
        url="https://bedrock-runtime.us-east-1.amazonaws.com/model/x/invoke",
        headers={"Content-Type": "application/json"},
        body=b'{"p": "x"}',
        streaming=False,
    )
    content_sha = signed.get("x-amz-content-sha256") or signed.get(
        "X-Amz-Content-SHA256"
    )
    # Non-streaming: botocore may or may not set this header; whatever it
    # does, it MUST NOT be the streaming sentinel.
    if content_sha is not None:
        assert content_sha != "STREAMING-AWS4-HMAC-SHA256-PAYLOAD"


# ---------------------------------------------------------------------------
# Clock skew (invariant 7)
# ---------------------------------------------------------------------------


def test_aws_sigv4_rejects_request_outside_clock_skew_window() -> None:
    """Invariant 7: 5-minute window enforced; requests outside raise
    `ClockSkew`.
    """
    sig = AwsSigV4(_make_credentials())
    # Pin "now" to 1 hour ago relative to real time.
    import time

    skewed = time.time() - 3700  # > 5 minutes off
    with pytest.raises(ClockSkew):
        sig._check_clock_skew(now_epoch=skewed)


def test_aws_sigv4_accepts_request_inside_clock_skew_window() -> None:
    sig = AwsSigV4(_make_credentials())
    import time

    inside = time.time() - 30  # 30s skew -> inside 5-minute window
    sig._check_clock_skew(now_epoch=inside)  # must not raise


def test_aws_sigv4_sign_raises_clock_skew_when_check_fails() -> None:
    """sign() fires `_check_clock_skew` before botocore signing."""
    sig = AwsSigV4(_make_credentials())
    import time

    with patch("kaizen.llm.auth.aws.time.time", return_value=time.time() - 3700):
        with pytest.raises(ClockSkew):
            sig.sign(
                method="POST",
                url="https://bedrock-runtime.us-east-1.amazonaws.com/",
                headers={},
                body=b"",
            )


# ---------------------------------------------------------------------------
# Credential rotation (invariant 8)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aws_sigv4_refresh_swaps_credentials_under_lock() -> None:
    """Invariant 8: rotation via `asyncio.Lock` guarding an immutable
    `AwsCredentials` slot.
    """
    sig = AwsSigV4(_make_credentials())

    new_botocore_creds = MagicMock()
    new_botocore_creds.access_key = "AKIANEW"
    new_botocore_creds.secret_key = "NEWSECRET"
    new_botocore_creds.token = "NEWSESSION"

    session_mock = MagicMock()
    session_mock.get_credentials.return_value = new_botocore_creds

    # The refresh() path does `from botocore.session import Session` inside
    # the lock; patch that import.
    with patch("botocore.session.Session", return_value=session_mock):
        await sig.refresh()

    assert sig.credentials.access_key_id.get_secret_value() == "AKIANEW"
    assert sig.credentials.secret_access_key.get_secret_value() == "NEWSECRET"
    assert sig.credentials.session_token is not None
    assert sig.credentials.session_token.get_secret_value() == "NEWSESSION"
    # Region is preserved across rotation.
    assert sig.credentials.region == "us-east-1"


@pytest.mark.asyncio
async def test_aws_sigv4_refresh_concurrent_calls_serialize() -> None:
    """Concurrent refresh calls under the asyncio.Lock serialize; each call
    invokes botocore's session independently (the lock orders them, it
    does NOT coalesce them). The important property is the STORED
    credential state stays consistent (no torn reads) and no race-based
    crashes.
    """
    sig = AwsSigV4(_make_credentials())

    call_count = {"n": 0}

    def _make_session(*args, **kwargs):
        call_count["n"] += 1
        session_mock = MagicMock()
        creds = MagicMock()
        creds.access_key = f"AKIA{call_count['n']:03d}"
        creds.secret_key = f"SECRET{call_count['n']:03d}"
        creds.token = None
        session_mock.get_credentials.return_value = creds
        return session_mock

    with patch("botocore.session.Session", side_effect=_make_session):
        await asyncio.gather(sig.refresh(), sig.refresh(), sig.refresh())

    # All three refresh calls invoked the session (lock orders them; it
    # does not coalesce). Final credential belongs to one of the callers.
    assert call_count["n"] == 3
    assert sig.credentials.access_key_id.get_secret_value().startswith("AKIA")


@pytest.mark.asyncio
async def test_aws_sigv4_refresh_raises_auth_error_on_empty_creds() -> None:
    sig = AwsSigV4(_make_credentials())
    session_mock = MagicMock()
    session_mock.get_credentials.return_value = None

    with patch("botocore.session.Session", return_value=session_mock):
        with pytest.raises(AuthError):
            await sig.refresh()


# ---------------------------------------------------------------------------
# repr redaction
# ---------------------------------------------------------------------------


def test_aws_sigv4_repr_does_not_leak_credentials() -> None:
    creds = AwsCredentials(
        access_key_id=SecretStr("AKIASECRETLEAKTEST"),
        secret_access_key=SecretStr("verysecretvalue-dont-leak"),
        session_token=SecretStr("session-token-dont-leak"),
        region="us-east-1",
    )
    sig = AwsSigV4(creds)
    rendered = repr(sig)
    assert "AKIASECRETLEAKTEST" not in rendered
    assert "verysecretvalue-dont-leak" not in rendered
    assert "session-token-dont-leak" not in rendered
    assert "us-east-1" in rendered


def test_aws_credentials_repr_does_not_leak() -> None:
    creds = AwsCredentials(
        access_key_id=SecretStr("AKIASHOULDNOTLEAK"),
        secret_access_key=SecretStr("secret-must-not-leak-xxx"),
        session_token=SecretStr("session-must-not-leak-yyy"),
        region="us-east-1",
    )
    rendered = repr(creds)
    # pydantic SecretStr renders as '**********' in default repr.
    assert "AKIASHOULDNOTLEAK" not in rendered
    assert "secret-must-not-leak-xxx" not in rendered
    assert "session-must-not-leak-yyy" not in rendered


# ---------------------------------------------------------------------------
# apply() entrypoint -- dict + object paths
# ---------------------------------------------------------------------------


def test_aws_sigv4_apply_signs_dict_request() -> None:
    sig = AwsSigV4(_make_credentials())
    req = {
        "method": "POST",
        "url": "https://bedrock-runtime.us-east-1.amazonaws.com/model/x/invoke",
        "headers": {"Content-Type": "application/json"},
        "body": b'{"prompt": "hi"}',
    }
    returned = sig.apply(req)
    assert returned is req
    assert "Authorization" in req["headers"]


def test_aws_sigv4_apply_rejects_missing_url() -> None:
    sig = AwsSigV4(_make_credentials())
    with pytest.raises(TypeError, match=r"url"):
        sig.apply({"method": "POST", "headers": {}})
