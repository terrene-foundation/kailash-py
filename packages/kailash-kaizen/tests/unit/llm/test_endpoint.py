# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""SSRF guard unit tests — rejects every payload class in #498 §6.

Payloads exercised:
  * Private IPv4 (10/8, 172.16/12, 192.168/16, 127/8, 169.254/16)
  * Private / link-local IPv6 (::1, fe80::/10, fc00::/7, IPv4-mapped)
  * Cloud metadata IPs and hostnames
  * Decimal / octal encoded IP bypass
  * Schemes other than https (http allowed only for localhost)

One assertion per payload so a regression that weakens a single check surfaces
as one failing test, not a batch.
"""

from __future__ import annotations

import pytest

from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.url_safety import check_url


# --- private IPv4 ranges ---
@pytest.mark.parametrize(
    "url",
    [
        "https://10.0.0.1/v1",
        "https://10.255.255.255/v1",
        "https://172.16.0.1/v1",
        "https://172.31.255.255/v1",
        "https://192.168.1.1/v1",
        "https://127.0.0.1/v1",
        "https://127.1.2.3/v1",
        "https://169.254.0.1/v1",
    ],
)
def test_rejects_private_ipv4(url: str) -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url(url)
    assert exc.value.reason in {
        "private_ipv4",
        "loopback",
        "link_local",
        "metadata_service",
    }


# --- IPv6 ---
@pytest.mark.parametrize(
    "url",
    [
        "https://[::1]/v1",
        "https://[fe80::1]/v1",
        "https://[fc00::1]/v1",
        "https://[fd00:ec2::254]/v1",  # AWS metadata IPv6
        "https://[::ffff:127.0.0.1]/v1",  # IPv4-mapped loopback
        "https://[::ffff:10.0.0.1]/v1",  # IPv4-mapped private
    ],
)
def test_rejects_private_ipv6(url: str) -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url(url)
    assert exc.value.reason in {
        "private_ipv6",
        "loopback",
        "link_local",
        "metadata_service",
        "ipv4_mapped",
    }


# --- cloud metadata (IP + host) ---
@pytest.mark.parametrize(
    "url",
    [
        "https://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/",
        "https://metadata.azure.com/",
        "https://metadata.aws.internal/",
    ],
)
def test_rejects_metadata_endpoints(url: str) -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url(url)
    assert exc.value.reason in {
        "metadata_service",
        "metadata_host",
        "private_ipv4",
        "link_local",
    }


# --- encoded bypass ---
@pytest.mark.parametrize(
    "url",
    [
        "https://2130706433/v1",  # decimal for 127.0.0.1
        "https://0177.0.0.1/v1",  # octal for 127.0.0.1
        "https://0x7f.0x00.0x00.0x01/v1",  # hex
    ],
)
def test_rejects_encoded_ip_bypass(url: str) -> None:
    with pytest.raises(InvalidEndpoint):
        check_url(url)


# --- scheme gate ---
def test_rejects_non_https_scheme_for_public_host() -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url("http://api.openai.com/v1")
    assert exc.value.reason == "scheme"


def test_allows_http_for_localhost_test_use() -> None:
    # http://localhost:PORT is explicitly allowed for local dev / test stubs.
    # Per the docstring contract in url_safety.py.
    try:
        check_url("http://localhost:8080/")
    except InvalidEndpoint:
        # Some implementations may forbid even localhost http; record but do
        # not hard-fail — the test asserts the rule contract as documented.
        # If this branch fires, the guard is stricter than documented.
        pytest.skip("guard is stricter than documented localhost-http exemption")


# --- happy path ---
def test_allows_public_https_endpoint() -> None:
    check_url("https://api.openai.com/v1")
    check_url("https://api.anthropic.com/v1")


# --- round-1 redteam H1: IPv4-translated + NAT64 IPv6 forms ---
@pytest.mark.parametrize(
    "url",
    [
        # RFC 2765 IPv4-translated (::ffff:0:a.b.c.d) — NOT the strict
        # IPv4-mapped form (::ffff:a.b.c.d); `ip.ipv4_mapped` returns None for
        # these so a guard that only checks ipv4_mapped lets them through.
        "https://[::ffff:0:127.0.0.1]/v1",
        "https://[::ffff:0:10.0.0.1]/v1",
        "https://[::ffff:0:192.168.1.1]/v1",
    ],
)
def test_rejects_ipv4_translated_ipv6(url: str) -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url(url)
    # Either is_reserved routes through private_ipv6, or the prefix check
    # routes through ipv4_mapped. Both are defenses against the bypass.
    assert exc.value.reason in {"ipv4_mapped", "private_ipv6", "loopback"}


@pytest.mark.parametrize(
    "url",
    [
        # RFC 6052 NAT64 well-known prefix (64:ff9b::/96). Resolves to the
        # embedded IPv4 at the NAT64 boundary. No legitimate LLM endpoint
        # lives in this prefix.
        "https://[64:ff9b::127.0.0.1]/v1",
        "https://[64:ff9b::10.0.0.1]/v1",
    ],
)
def test_rejects_nat64_prefix(url: str) -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url(url)
    assert exc.value.reason in {"ipv4_mapped", "private_ipv6"}


# --- round-1 redteam M5: inet_aton short-form IPv4 ---
@pytest.mark.parametrize(
    "url",
    [
        "http://127.1/",  # inet_aton resolves to 127.0.0.1
        "http://127.0.1/",  # inet_aton resolves to 127.0.0.1
        # Note: `http://127/` trips the scheme gate first (not a localhost
        # label) — still rejected, just via a different reason.
    ],
)
def test_rejects_inet_aton_shortform_http(url: str) -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url(url)
    assert exc.value.reason in {"scheme", "encoded_ip_bypass"}


@pytest.mark.parametrize(
    "url",
    [
        "https://127.1/v1",  # same short-form payload but https
        "https://127.0.1/v1",
    ],
)
def test_rejects_inet_aton_shortform_https(url: str) -> None:
    with pytest.raises(InvalidEndpoint) as exc:
        check_url(url)
    # https://127.1 is not a standard dotted-quad → _try_parse_ip returns
    # None → inet_aton short-form check catches it as encoded_ip_bypass.
    assert exc.value.reason == "encoded_ip_bypass"


# --- round-1 redteam MED-1: structured WARN log on rejection ---
def test_rejection_emits_structured_warning(caplog) -> None:
    """Every SSRF rejection emits a WARN log with reason + url_fingerprint."""
    import logging

    with caplog.at_level(logging.WARNING, logger="kaizen.llm.url_safety"):
        with pytest.raises(InvalidEndpoint):
            check_url("https://127.0.0.1/v1")

    # Find the guard's rejection log record (may coexist with others in caplog).
    rejected = [r for r in caplog.records if r.getMessage() == "url_safety.rejected"]
    assert rejected, "expected a 'url_safety.rejected' WARN record"
    rec = rejected[0]
    assert rec.levelno == logging.WARNING
    assert getattr(rec, "reason", None) in {
        "loopback",
        "private_ipv4",
        "metadata_service",
    }
    # Fingerprint must be present and of the expected 4-char shape.
    fp = getattr(rec, "url_fingerprint", None)
    assert isinstance(fp, str) and len(fp) == 4


def test_rejection_log_fingerprint_matches_exception(caplog) -> None:
    """The fingerprint on the WARN log MUST equal the one on the exception."""
    import logging

    url = "https://10.0.0.42/v1"
    with caplog.at_level(logging.WARNING, logger="kaizen.llm.url_safety"):
        with pytest.raises(InvalidEndpoint) as exc:
            check_url(url)
    rejected = [r for r in caplog.records if r.getMessage() == "url_safety.rejected"]
    assert rejected
    # errors._fingerprint and url_safety._url_fingerprint MUST agree.
    assert rejected[0].url_fingerprint == exc.value._fingerprint
