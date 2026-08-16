# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""The wire-reachability differential, as a runnable instrument.

`test_endpoint_construction_is_offline.py` records the measurement that
justifies `Endpoint._validate_base_url` passing `resolve_dns=False`. A
recorded number nobody can re-run is not evidence
(`instrument-discipline.md` MUST-1), and this is the result the whole change
rests on — so the probe corpus and both gates live here, executable.

# What is measured

Construction is NOT the security surface. A URL is egressed only if BOTH
gates admit it:

    Endpoint(base_url=...)                 -- parse time, offline-decidable
    SafeDnsResolver.check_host(host)       -- connect time, on the transport

Measuring construction alone shows `https://myfoundry.services.ai.azure.com`
moving `reject:resolution_failed -> ALLOW` and reads as a widening. The
composite shows what actually happened: the gate moved, the verdict did not.

# Why `rebind` mode is the discriminating half

Live DNS cannot be made to answer with a private address on demand, so a
real-DNS run cannot distinguish "the connect-time gate catches rebinding"
from "no host in the corpus happens to resolve private". `rebind` mode
forces every non-literal host to resolve to a blocked address, which is
exactly where a genuine widening would surface as `REACHES_WIRE`. If the
connect-time gate were absent, bypassed, or not on the transport, these
assertions FAIL — that is what makes them evidence rather than decoration.
"""

from __future__ import annotations

import socket
from urllib.parse import urlparse

import pytest

from kaizen.llm.deployment import Endpoint
from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.http_client import SafeDnsResolver

pytestmark = pytest.mark.unit

#: Forced resolution target in `rebind` mode -- the AWS/GCP IMDS address.
_REBIND_IP = "169.254.169.254"

#: Public hosts in the corpus. Under `rebind` these resolve to `_REBIND_IP`;
#: under real DNS they are the probes whose verdict depends on the resolver.
_PUBLIC_HOSTS = [
    "https://api.openai.com/v1",
    "https://example.com/v1",
    "https://myresource.openai.azure.com",
    "https://myfoundry.services.ai.azure.com",
]

#: Probes whose verdict is decidable OFFLINE -- no resolver consulted on
#: either gate, so the expected rejection is the same in both modes.
_OFFLINE_REJECTED = [
    # HTTPS-only, except the `localhost` LABEL (kaizen policy).
    ("http://api.openai.com/v1", "scheme"),
    ("http://example.com/", "scheme"),
    ("http://8.8.8.8/", "scheme"),
    ("http://metadata.google.internal/", "scheme"),
    # Non-http(s) schemes.
    ("ftp://example.com/", "scheme"),
    ("gopher://x/", "scheme"),
    ("file:///etc/passwd", "scheme"),
    ("javascript:alert(1)", "scheme"),
    # Malformed. `not-a-url` parses to an empty scheme, and the shared guard
    # orders the scheme check first -- one of the three reason-code moves
    # this branch recorded (was `malformed_url` pre-consolidation).
    ("not-a-url", "scheme"),
    ("", "malformed_url"),
    # Literal loopback -- the carve-out is LABEL-only.
    ("http://127.0.0.1:11434", "loopback"),
    ("https://127.0.0.1:8000/v1", "loopback"),
    ("http://[::1]:8000/", "loopback"),
    # RFC1918 / reserved / unspecified literals.
    ("https://10.1.2.3/v1", "private_ipv4"),
    ("https://192.168.1.1/v1", "private_ipv4"),
    ("https://172.16.0.1/v1", "private_ipv4"),
    ("https://224.0.0.1/", "private_ipv4"),
    ("https://0.0.0.0/", "private_ipv4"),
    ("https://169.254.0.1/", "link_local"),
    # Cloud metadata, by IP and by name.
    ("https://169.254.169.254/", "metadata_service"),
    ("https://[fd00:ec2::254]/", "metadata_service"),
    ("https://metadata.google.internal/", "metadata_host"),
    ("https://metadata.azure.com/", "metadata_host"),
    ("https://metadata.aws.internal/", "metadata_host"),
    # IPv6 private / link-local.
    ("https://[fe80::1]/", "link_local"),
    ("https://[fc00::1]/", "private_ipv6"),
    # IPv6 embedded-IPv4 wrappers, incl. the #2136 IMDS set.
    ("https://[::ffff:127.0.0.1]/", "ipv4_mapped"),
    ("https://[64:ff9b::7f00:1]/", "ipv4_mapped"),
    ("https://[64:ff9b::169.254.169.254]/", "metadata_service"),
    ("https://[::ffff:0:a9fe:a9fe]/", "metadata_service"),
    ("https://[64:ff9b::a9fe:a9fe]/", "metadata_service"),
    ("https://[::ffff:169.254.169.254]/", "link_local"),
    # Encoded-IP bypass forms.
    ("https://2130706433/", "encoded_ip_bypass"),
    ("https://0177.0.0.1/", "encoded_ip_bypass"),
    ("https://0x7f.0.0.1/", "encoded_ip_bypass"),
    ("https://127.1/", "encoded_ip_bypass"),
    ("https://127.0.1/", "encoded_ip_bypass"),
    # IDN homograph (Cyrillic 'е') -- rejected at the raw-string layer.
    ("https://api.opеnai.com/v1", "malformed_url"),
]


@pytest.fixture
def _rebind_dns(monkeypatch: pytest.MonkeyPatch):
    """Force every non-literal hostname to resolve to a blocked address.

    Literal IPs are passed through so the literal-IP probes still exercise
    the classifier rather than this fixture.
    """
    real = socket.getaddrinfo

    def _fake(host, port, *args, **kwargs):
        try:
            socket.inet_aton(str(host))
            return real(host, port, *args, **kwargs)
        except OSError:
            pass
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (_REBIND_IP, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake)


def _composite_verdict(url: str) -> str:
    """`REACHES_WIRE` iff BOTH gates admit the URL."""
    try:
        ep = Endpoint(base_url=url)
    except Exception as exc:
        return f"reject@parse:{_reason(exc)}"
    host = urlparse(str(ep.base_url)).hostname or ""
    try:
        SafeDnsResolver().check_host(host)
    except InvalidEndpoint as exc:
        return f"reject@connect:{exc.reason}"
    return "REACHES_WIRE"


def _reason(exc: Exception) -> str:
    reason = getattr(exc, "reason", None)
    if reason is None:
        reason = getattr(getattr(exc, "__cause__", None), "reason", None)
    return reason or type(exc).__name__


# ---------------------------------------------------------------------------
# 1. Offline-decidable probes: rejected at PARSE, in both DNS conditions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url,reason", _OFFLINE_REJECTED)
def test_offline_probes_reject_at_parse(url: str, reason: str) -> None:
    assert _composite_verdict(url) == f"reject@parse:{reason}"


@pytest.mark.parametrize("url,reason", _OFFLINE_REJECTED)
def test_offline_probes_reject_at_parse_under_rebinding(
    url: str, reason: str, _rebind_dns
) -> None:
    """Forcing DNS to lie changes nothing: these never consult a resolver."""
    assert _composite_verdict(url) == f"reject@parse:{reason}"


# ---------------------------------------------------------------------------
# 2. THE discriminating assertion: rebinding never reaches the wire.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("url", _PUBLIC_HOSTS)
def test_rebinding_host_never_reaches_the_wire(url: str, _rebind_dns) -> None:
    """Construction admits the NAME; the connect gate refuses the ADDRESS.

    This is the assertion that makes `resolve_dns=False` at construction
    defensible. It fails if the connect-time gate is removed, unhooked from
    the transport, or stops classifying the IMDS range.
    """
    assert _composite_verdict(url) == "reject@connect:metadata_service"


def test_the_rebind_fixture_actually_lies() -> None:
    """The instrument's own discrimination check.

    If the fixture silently stopped patching, every assertion above would
    still pass under real DNS for the hosts that do not resolve — and would
    be measuring nothing. This pins that the fixture changes the answer.
    """
    real_answer = SafeDnsResolver()
    with pytest.raises(InvalidEndpoint):
        # Under the patch this resolves to IMDS; unpatched, example.com is
        # public and check_host returns cleanly.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(
                socket,
                "getaddrinfo",
                lambda *a, **k: [
                    (socket.AF_INET, socket.SOCK_STREAM, 6, "", (_REBIND_IP, 443))
                ],
            )
            real_answer.check_host("example.com")


# ---------------------------------------------------------------------------
# 3. Public hosts that DO resolve publicly still reach the wire.
# ---------------------------------------------------------------------------


def test_public_literal_ip_still_reaches_the_wire() -> None:
    """No-false-positive polarity — the guard must not refuse legitimate use.

    Literal IPs so this asserts the classifier, not the local resolver.
    """
    for url in ("https://8.8.8.8/", "https://1.1.1.1/"):
        assert _composite_verdict(url) == "REACHES_WIRE", url


# ---------------------------------------------------------------------------
# 4. An unresolvable name is refused — at connect now, not at parse.
# ---------------------------------------------------------------------------


def test_unresolvable_name_is_refused_at_connect_not_at_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The one construction-surface verdict this change moved.

    `reject@parse:resolution_failed -> reject@connect:resolution_failed`:
    same reason code, one gate later, still never reaching a SYN.
    """

    def _nxdomain(*args, **kwargs):
        raise socket.gaierror(8, "nodename nor servname provided")

    monkeypatch.setattr(socket, "getaddrinfo", _nxdomain)
    verdict = _composite_verdict("https://myfoundry.services.ai.azure.com")
    assert verdict == "reject@connect:resolution_failed"
