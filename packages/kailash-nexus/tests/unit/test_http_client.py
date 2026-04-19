# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for ``nexus.http_client``.

Coverage:

* SSRF URL validation — every blocked pattern from the guard.
* Config default shape — follow_redirects=False, blocked_networks defaults,
  request_id_header naming.
* InvalidEndpointError contract — reason allowlist, URL fingerprint only.
* SSRF ordering — private-IP check runs BEFORE host allowlist per issue
  #473 non-negotiable 1.
"""

from __future__ import annotations

import ipaddress

import pytest

from nexus.http_client import (
    HttpClient,
    HttpClientConfig,
    InvalidEndpointError,
    check_url,
)


# ---------------------------------------------------------------------------
# Config defaults
# ---------------------------------------------------------------------------


class TestHttpClientConfigDefaults:
    """The config's defaults encode the SSRF posture.

    Regression checkpoint: follow_redirects MUST default to False because
    every redirect is a fresh SSRF surface. blocked_networks MUST include
    the RFC1918 + loopback + link-local + IMDS set by default.
    """

    def test_follow_redirects_defaults_false(self) -> None:
        config = HttpClientConfig()
        assert config.follow_redirects is False

    def test_blocked_networks_include_rfc1918(self) -> None:
        config = HttpClientConfig()
        networks = list(config.blocked_networks or ())
        assert any(
            ipaddress.IPv4Address("10.1.2.3") in n for n in networks
        ), "RFC1918 10/8 must be in default blocklist"
        assert any(
            ipaddress.IPv4Address("172.20.0.1") in n for n in networks
        ), "RFC1918 172.16/12 must be in default blocklist"
        assert any(
            ipaddress.IPv4Address("192.168.1.1") in n for n in networks
        ), "RFC1918 192.168/16 must be in default blocklist"

    def test_blocked_networks_include_loopback(self) -> None:
        config = HttpClientConfig()
        networks = list(config.blocked_networks or ())
        assert any(ipaddress.IPv4Address("127.0.0.1") in n for n in networks)

    def test_blocked_networks_include_link_local_and_imds(self) -> None:
        config = HttpClientConfig()
        networks = list(config.blocked_networks or ())
        assert any(
            ipaddress.IPv4Address("169.254.169.254") in n for n in networks
        ), "AWS IMDS 169.254.169.254 must be in default blocklist"

    def test_blocked_networks_include_ipv6_private(self) -> None:
        config = HttpClientConfig()
        networks = list(config.blocked_networks or ())
        assert any(ipaddress.IPv6Address("::1") in n for n in networks)
        assert any(
            ipaddress.IPv6Address("fd00::1") in n for n in networks
        ), "ULA fc00::/7 must be in default blocklist"

    def test_request_id_header_default(self) -> None:
        config = HttpClientConfig()
        assert config.request_id_header == "X-Request-ID"

    def test_structured_log_prefix_default(self) -> None:
        config = HttpClientConfig()
        assert config.structured_log_prefix == "nexus.http"


# ---------------------------------------------------------------------------
# SSRF rejection — blocked patterns
# ---------------------------------------------------------------------------


class TestCheckUrlBlockedPatterns:
    """Every blocked SSRF pattern must produce an InvalidEndpointError."""

    def test_rfc1918_10_8_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://10.0.0.1/api")
        assert exc_info.value.reason == "private_ipv4"

    def test_rfc1918_172_16_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://172.16.0.1/api")
        assert exc_info.value.reason == "private_ipv4"

    def test_rfc1918_192_168_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://192.168.1.1/api")
        assert exc_info.value.reason == "private_ipv4"

    def test_loopback_127_0_0_1_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://127.0.0.1/api")
        assert exc_info.value.reason == "loopback"

    def test_aws_imds_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://169.254.169.254/latest/meta-data/")
        assert exc_info.value.reason == "metadata_service"

    def test_link_local_169_254_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://169.254.1.1/")
        # Either link_local or metadata_service is acceptable — 169.254.169.254
        # is metadata specifically; other link-local IPs surface as link_local.
        assert exc_info.value.reason in ("link_local", "private_ipv4")

    def test_ipv6_loopback_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://[::1]/api")
        assert exc_info.value.reason == "loopback"

    def test_ipv6_ula_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://[fd00::1]/api")
        assert exc_info.value.reason == "private_ipv6"

    def test_ipv6_link_local_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://[fe80::1]/api")
        assert exc_info.value.reason == "link_local"

    def test_ipv4_mapped_ipv6_loopback_rejected(self) -> None:
        """``::ffff:127.0.0.1`` wraps loopback — must still reject."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://[::ffff:127.0.0.1]/api")
        assert exc_info.value.reason == "ipv4_mapped"

    def test_nat64_wellknown_rejected(self) -> None:
        """RFC 6052 64:ff9b::/96 NAT64 wrapper — reject unconditionally."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://[64:ff9b::1]/api")
        assert exc_info.value.reason == "ipv4_mapped"

    def test_metadata_hostname_google_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://metadata.google.internal/computeMetadata/v1/")
        assert exc_info.value.reason == "metadata_host"

    def test_metadata_hostname_aws_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://metadata.aws.internal/")
        assert exc_info.value.reason == "metadata_host"

    def test_metadata_hostname_azure_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://metadata.azure.com/")
        assert exc_info.value.reason == "metadata_host"

    def test_decimal_encoded_ip_rejected(self) -> None:
        """``2130706433`` = 127.0.0.1 in inet_aton decimal form."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://2130706433/")
        assert exc_info.value.reason == "encoded_ip_bypass"

    def test_octal_encoded_ip_rejected(self) -> None:
        """``0177.0.0.1`` = 127.0.0.1 in inet_aton octal form."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://0177.0.0.1/")
        assert exc_info.value.reason == "encoded_ip_bypass"

    def test_hex_encoded_ip_rejected(self) -> None:
        """``0x7f.0.0.1`` = 127.0.0.1 in inet_aton hex form."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://0x7f.0.0.1/")
        assert exc_info.value.reason == "encoded_ip_bypass"

    def test_inet_aton_shortform_loopback_rejected(self) -> None:
        """``127.1`` resolves to 127.0.0.1 via libc. Guard must catch it."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://127.1/")
        assert exc_info.value.reason == "encoded_ip_bypass"

    def test_non_http_scheme_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("file:///etc/passwd")
        assert exc_info.value.reason == "scheme"

    def test_gopher_scheme_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("gopher://example.com/")
        assert exc_info.value.reason == "scheme"

    def test_ftp_scheme_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("ftp://example.com/")
        assert exc_info.value.reason == "scheme"

    def test_empty_url_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("")
        assert exc_info.value.reason == "malformed_url"

    def test_non_string_url_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError):
            check_url(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# SSRF — public hosts pass
# ---------------------------------------------------------------------------


class TestCheckUrlPublicHosts:
    """Public hosts must NOT be rejected by the SSRF guard."""

    def test_public_ip_allowed(self) -> None:
        # 8.8.8.8 is Google DNS; a public IP. resolve_dns=False keeps this
        # test offline and deterministic.
        check_url("https://8.8.8.8/", resolve_dns=False)

    def test_public_hostname_allowed_with_resolve_dns_off(self) -> None:
        check_url("https://example.com/", resolve_dns=False)


# ---------------------------------------------------------------------------
# allow_loopback carve-out
# ---------------------------------------------------------------------------


class TestAllowLoopback:
    """``allow_loopback=True`` permits ONLY 127.0.0.1 / localhost / ::1.

    Every other private range stays blocked so allow_loopback cannot be
    mis-used as a wildcard disable switch.
    """

    def test_loopback_permitted_when_enabled(self) -> None:
        check_url(
            "http://127.0.0.1:8080/x",
            allow_loopback=True,
            resolve_dns=False,
        )

    def test_private_ipv4_still_rejected_when_allow_loopback_set(
        self,
    ) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url("http://10.0.0.1/", allow_loopback=True, resolve_dns=False)
        assert exc_info.value.reason == "private_ipv4"

    def test_metadata_still_rejected_when_allow_loopback_set(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url(
                "http://169.254.169.254/",
                allow_loopback=True,
                resolve_dns=False,
            )
        assert exc_info.value.reason == "metadata_service"


# ---------------------------------------------------------------------------
# SSRF ordering — issue #473 non-negotiable 1
# ---------------------------------------------------------------------------


class TestSsrfBeforeAllowlist:
    """An allowlisted private IP must STILL be rejected.

    Per issue #473 non-negotiable 1: the private-IP / metadata check runs
    BEFORE the host allowlist. The allowlist narrows the already-safe
    public set; it is NOT a bypass path.
    """

    def test_allowlisted_private_ip_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url(
                "http://10.0.0.1/",
                host_allowlist=["10.0.0.1"],
                resolve_dns=False,
            )
        # private_ipv4, not host_not_allowlisted — ordering proof.
        assert exc_info.value.reason == "private_ipv4"

    def test_allowlisted_imds_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url(
                "http://169.254.169.254/",
                host_allowlist=["169.254.169.254"],
                resolve_dns=False,
            )
        assert exc_info.value.reason == "metadata_service"

    def test_allowlisted_loopback_rejected(self) -> None:
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url(
                "http://127.0.0.1/",
                host_allowlist=["127.0.0.1"],
                resolve_dns=False,
            )
        assert exc_info.value.reason == "loopback"

    def test_public_host_not_in_allowlist_rejected(self) -> None:
        """Once SSRF passes, a non-allowlisted host is rejected."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url(
                "https://attacker.example.com/",
                host_allowlist=["api.example.com"],
                resolve_dns=False,
            )
        assert exc_info.value.reason == "host_not_allowlisted"

    def test_public_host_in_allowlist_allowed(self) -> None:
        check_url(
            "https://api.example.com/",
            host_allowlist=["api.example.com"],
            resolve_dns=False,
        )

    def test_allowlist_is_case_insensitive(self) -> None:
        check_url(
            "https://API.Example.Com/",
            host_allowlist=["api.example.com"],
            resolve_dns=False,
        )


# ---------------------------------------------------------------------------
# InvalidEndpointError contract
# ---------------------------------------------------------------------------


class TestInvalidEndpointErrorContract:
    def test_reason_echoes_nothing_sensitive(self) -> None:
        """Raw URL must NEVER appear in str(exc) — only the fingerprint."""
        with pytest.raises(InvalidEndpointError) as exc_info:
            check_url(
                "http://127.0.0.1:8080/secret-token-abc123",
                resolve_dns=False,
            )
        msg = str(exc_info.value)
        assert "secret-token-abc123" not in msg
        assert "url_fingerprint=" in msg

    def test_unknown_reason_coerces_to_malformed(self) -> None:
        """Defensive — if a future caller passes an off-allowlist reason."""
        err = InvalidEndpointError("not_a_real_reason", raw_url="http://x/")
        assert err.reason == "malformed_url"

    def test_fingerprint_is_8_hex_chars(self) -> None:
        err = InvalidEndpointError("scheme", raw_url="http://example.com/")
        assert err.url_fingerprint is not None
        assert len(err.url_fingerprint) == 8
        # hex
        int(err.url_fingerprint, 16)

    def test_no_fingerprint_when_no_url(self) -> None:
        err = InvalidEndpointError("malformed_url", raw_url=None)
        assert err.url_fingerprint is None
        assert "url_fingerprint" not in str(err)


# ---------------------------------------------------------------------------
# HttpClient lifecycle
# ---------------------------------------------------------------------------


class TestHttpClientLifecycle:
    @pytest.mark.asyncio
    async def test_is_closed_false_initially(self) -> None:
        client = HttpClient(HttpClientConfig())
        try:
            assert client.is_closed is False
        finally:
            await client.aclose()
        assert client.is_closed is True

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self) -> None:
        client = HttpClient(HttpClientConfig())
        await client.aclose()
        await client.aclose()  # second call should not raise
        assert client.is_closed is True

    @pytest.mark.asyncio
    async def test_use_after_close_raises(self) -> None:
        client = HttpClient(HttpClientConfig())
        await client.aclose()
        with pytest.raises(RuntimeError):
            await client.get("https://example.com/")

    @pytest.mark.asyncio
    async def test_context_manager_closes(self) -> None:
        async with HttpClient(HttpClientConfig()) as client:
            assert client.is_closed is False
        assert client.is_closed is True


# ---------------------------------------------------------------------------
# HttpClient request validation
# ---------------------------------------------------------------------------


class TestHttpClientRequestValidation:
    """Request-layer SSRF rejection is observable via InvalidEndpointError."""

    @pytest.mark.asyncio
    async def test_private_ip_raises_invalid_endpoint(self) -> None:
        async with HttpClient(HttpClientConfig()) as client:
            with pytest.raises(InvalidEndpointError):
                await client.get("http://10.0.0.1/api")

    @pytest.mark.asyncio
    async def test_imds_raises_invalid_endpoint(self) -> None:
        async with HttpClient(HttpClientConfig()) as client:
            with pytest.raises(InvalidEndpointError):
                await client.get("http://169.254.169.254/")

    @pytest.mark.asyncio
    async def test_scheme_raises_invalid_endpoint(self) -> None:
        async with HttpClient(HttpClientConfig()) as client:
            with pytest.raises(InvalidEndpointError):
                await client.get("file:///etc/passwd")
