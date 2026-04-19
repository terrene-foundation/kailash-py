# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``nexus.service_client``.

Coverage:

* Exception hierarchy — every typed subclass inherits from the base.
* Eager header validation — CRLF / control bytes / empty / non-string
  rejected at ``__init__``.
* Bearer-token validation — CRLF / empty rejected at ``__init__``.
* Path joining — malformed paths raise ServiceClientInvalidPathError.
* SSRF propagation — a blocked URL from the underlying HttpClient surfaces
  as ServiceClientHttpError.
"""

from __future__ import annotations

import pytest

from nexus.service_client import (
    ServiceClient,
    ServiceClientDeserializeError,
    ServiceClientError,
    ServiceClientHttpError,
    ServiceClientHttpStatusError,
    ServiceClientInvalidHeaderError,
    ServiceClientInvalidPathError,
    ServiceClientSerializeError,
)


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TestExceptionHierarchy:
    """Every typed failure mode inherits from ``ServiceClientError``.

    Backwards-compat guarantee — a caller that catches
    ``ServiceClientError`` MUST catch every subclass.
    """

    def test_http_error_is_service_client_error(self) -> None:
        assert issubclass(ServiceClientHttpError, ServiceClientError)

    def test_http_status_error_is_service_client_error(self) -> None:
        assert issubclass(ServiceClientHttpStatusError, ServiceClientError)

    def test_serialize_error_is_service_client_error(self) -> None:
        assert issubclass(ServiceClientSerializeError, ServiceClientError)

    def test_deserialize_error_is_service_client_error(self) -> None:
        assert issubclass(ServiceClientDeserializeError, ServiceClientError)

    def test_invalid_path_error_is_service_client_error(self) -> None:
        assert issubclass(ServiceClientInvalidPathError, ServiceClientError)

    def test_invalid_header_error_is_service_client_error(self) -> None:
        assert issubclass(ServiceClientInvalidHeaderError, ServiceClientError)

    def test_status_error_truncates_body(self) -> None:
        """Body over 512 bytes must be truncated in the exception message.

        This is defence against a provider that echoes the submitted
        Authorization header in a 4xx body — the full token should not
        appear in str(err).
        """
        long_body = b"x" * 2048
        err = ServiceClientHttpStatusError(
            status_code=403, body=long_body, url="https://api.example.com/x"
        )
        assert err.status_code == 403
        assert err.body == long_body  # raw preserved
        assert "...[truncated]" in str(err)
        # Message length bounded.
        assert len(str(err)) < 1024

    def test_status_error_does_not_echo_full_url(self) -> None:
        err = ServiceClientHttpStatusError(
            status_code=500,
            body=b"",
            url="https://api.example.com/secret/path/xyz?token=abc123",
        )
        assert "secret" not in str(err)
        assert "abc123" not in str(err)
        assert "api.example.com" in str(err)


# ---------------------------------------------------------------------------
# Base URL validation
# ---------------------------------------------------------------------------


class TestBaseUrlValidation:
    def test_empty_base_url_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidPathError):
            ServiceClient("")

    def test_non_http_base_url_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidPathError):
            ServiceClient("file:///etc/passwd")

    def test_no_host_base_url_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidPathError):
            ServiceClient("https://")

    def test_base_url_trailing_slash_normalised(self) -> None:
        client = ServiceClient("https://api.example.com")
        assert client.base_url == "https://api.example.com/"

    def test_base_url_with_path_preserved(self) -> None:
        client = ServiceClient("https://api.example.com/v1")
        assert client.base_url == "https://api.example.com/v1/"


# ---------------------------------------------------------------------------
# Eager header validation — CRLF / control / empty
# ---------------------------------------------------------------------------


class TestEagerHeaderValidation:
    """Non-negotiable per issue #473: invalid headers fail at __init__.

    BLOCKED patterns: CRLF injection, empty name, empty value, control
    bytes, non-string types. Every rejection must happen BEFORE the first
    request dispatches.
    """

    def test_crlf_in_header_value_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X-Good": "value\r\nX-Bad: 1"},
            )

    def test_lone_lf_in_header_value_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X-Good": "value\nX-Bad: 1"},
            )

    def test_lone_cr_in_header_value_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X-Good": "value\rX-Bad: 1"},
            )

    def test_null_byte_in_header_value_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X-Good": "value\x00bypass"},
            )

    def test_empty_header_name_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"": "value"},
            )

    def test_empty_header_value_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X-Good": ""},
            )

    def test_space_in_header_name_rejected(self) -> None:
        """RFC 7230 token — whitespace in names is injection bait."""
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X Bad": "value"},
            )

    def test_control_byte_in_header_name_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X-\x00Bad": "value"},
            )

    def test_non_string_header_name_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={42: "value"},  # type: ignore[dict-item]
            )

    def test_non_string_header_value_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                headers={"X-Good": 42},  # type: ignore[dict-item]
            )

    def test_valid_headers_accepted(self) -> None:
        client = ServiceClient(
            "https://api.example.com",
            headers={"X-Client": "my-app", "X-Request-Source": "test"},
        )
        assert client.base_url == "https://api.example.com/"

    def test_header_error_message_does_not_echo_raw_value(self) -> None:
        """The rejection message must not put the CRLF payload into logs."""
        try:
            ServiceClient(
                "https://api.example.com",
                headers={"X-Bad": "legit-value\r\nX-Sensitive-Token: abc123xyz"},
            )
            raise AssertionError("expected rejection")
        except ServiceClientInvalidHeaderError as exc:
            msg = str(exc)
            assert "abc123xyz" not in msg
            assert "X-Sensitive-Token" not in msg


# ---------------------------------------------------------------------------
# Bearer-token validation — CRLF / empty
# ---------------------------------------------------------------------------


class TestBearerTokenValidation:
    def test_crlf_in_bearer_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                bearer_token="good\r\nX-Injected: 1",
            )

    def test_empty_bearer_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                bearer_token="",
            )

    def test_null_byte_bearer_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                bearer_token="tok\x00bypass",
            )

    def test_non_string_bearer_rejected(self) -> None:
        with pytest.raises(ServiceClientInvalidHeaderError):
            ServiceClient(
                "https://api.example.com",
                bearer_token=42,  # type: ignore[arg-type]
            )

    def test_valid_bearer_accepted(self) -> None:
        client = ServiceClient(
            "https://api.example.com", bearer_token="valid-token-xyz"
        )
        assert client.has_auth is True

    def test_none_bearer_means_no_auth(self) -> None:
        client = ServiceClient("https://api.example.com", bearer_token=None)
        assert client.has_auth is False


# ---------------------------------------------------------------------------
# Path joining
# ---------------------------------------------------------------------------


class TestPathJoining:
    @pytest.mark.asyncio
    async def test_empty_path_rejected_at_request(self) -> None:
        async with ServiceClient("https://api.example.com") as client:
            with pytest.raises(ServiceClientInvalidPathError):
                await client.get_raw("")

    @pytest.mark.asyncio
    async def test_non_string_path_rejected(self) -> None:
        async with ServiceClient("https://api.example.com") as client:
            with pytest.raises(ServiceClientInvalidPathError):
                await client.get_raw(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SSRF propagation — blocked URL surfaces as ServiceClientHttpError
# ---------------------------------------------------------------------------


class TestSsrfPropagation:
    @pytest.mark.asyncio
    async def test_private_ip_base_url_blocked(self) -> None:
        async with ServiceClient("http://10.0.0.1") as client:
            with pytest.raises(ServiceClientHttpError) as exc_info:
                await client.get_raw("/api")
            # Cause is the underlying InvalidEndpointError
            assert exc_info.value.cause is not None

    @pytest.mark.asyncio
    async def test_imds_base_url_blocked(self) -> None:
        async with ServiceClient("http://169.254.169.254") as client:
            with pytest.raises(ServiceClientHttpError):
                await client.get_raw("/latest/meta-data/")

    @pytest.mark.asyncio
    async def test_allowlisted_private_ip_still_blocked(self) -> None:
        """Issue #473 non-negotiable 1 — allowlist does not bypass SSRF."""
        async with ServiceClient(
            "http://10.0.0.1", allowed_hosts=["10.0.0.1"]
        ) as client:
            with pytest.raises(ServiceClientHttpError):
                await client.get_raw("/api")


# ---------------------------------------------------------------------------
# Serialize error
# ---------------------------------------------------------------------------


class _Unserializable:
    """An object whose `__dict__` contains a non-JSON-serialisable value."""

    def __init__(self) -> None:
        self.bad = object()


class TestSerializeError:
    @pytest.mark.asyncio
    async def test_unserialisable_body_raises_serialize_error(self) -> None:
        async with ServiceClient(
            "https://api.example.com", allow_loopback=False
        ) as client:
            with pytest.raises(ServiceClientSerializeError):
                # object() is not JSON-serialisable
                await client.post_raw("/x", {"obj": object()})
