# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: `Endpoint` construction performs no DNS lookup (#2168).

``Endpoint.base_url`` routed every URL through ``url_safety.check_url()`` with
the DNS-rebinding sweep enabled, so merely PARSING a deployment performed a
live ``socket.getaddrinfo`` call and failed closed (``resolution_failed``)
whenever the hostname did not resolve -- rejecting well-formed endpoints whose
DNS is simply unpublished, such as an unreleased AWS Bedrock region.

Root cause: construction is not the moment of egress. A name that resolves
public at parse time can resolve to loopback at connect time, so the
parse-time answer is stale before it is used, while
``http_client.SafeDnsResolver.check_host`` re-resolves and re-classifies
immediately before the TCP connect -- and it, not the validator, owns the
address the socket actually uses.

The fix passes ``resolve_dns=False`` at that ONE call site. It keeps every
check that is decidable offline (scheme, metadata hostname, encoded-IP and
``inet_aton`` short-form bypasses, literal-IP classification) at construction,
and drops only the duplicated DNS half.

THIS TEST HAS TEETH IN BOTH DIRECTIONS. The fix must NOT become a widening:

* construction no longer resolves, and admits an unpublished hostname
  (``test_construction_performs_no_dns_lookup`` /
  ``test_unpublished_hostname_constructs``); and
* every address the parse-time resolve used to reject is STILL rejected by
  the connect-time gate, with the same reason bucket
  (``test_connect_time_gate_still_rejects_every_rebinding_address``) -- the
  negative half, which fails if anyone removes or weakens
  ``SafeDnsResolver``; and
* the offline half still rejects at construction
  (``test_offline_rejections_survive_at_construction``) -- the negative half
  that fails if ``resolve_dns=False`` is ever mistaken for "skip the guard".

Tier 1, fully offline: ``socket.getaddrinfo`` is stubbed in every test, and a
sentinel asserts the construction path never calls it.
"""

from __future__ import annotations

import ipaddress
import pathlib
import socket
from typing import Any, Dict, List, Tuple

import pytest

from kaizen.llm.deployment import Endpoint
from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.http_client import SafeDnsResolver

pytestmark = pytest.mark.regression


# Hostname -> the addresses a hostile / misconfigured resolver hands back.
# "GAIERROR" models a name that does not resolve at all.
_REBINDING_HOSTS: Dict[str, Any] = {
    "rebind-loopback.example.com": (["127.0.0.1"], "loopback"),
    "rebind-v6loop.example.com": (["::1"], "loopback"),
    "rebind-metadata.example.com": (["169.254.169.254"], "metadata_service"),
    "rebind-private10.example.com": (["10.0.0.5"], "private_ipv4"),
    "rebind-private192.example.com": (["192.168.1.1"], "private_ipv4"),
    "rebind-linklocal.example.com": (["169.254.1.5"], "link_local"),
    "rebind-unspec.example.com": (["0.0.0.0"], "private_ipv4"),
    "rebind-v4mapped.example.com": (["::ffff:127.0.0.1"], "ipv4_mapped"),
    "rebind-nat64.example.com": (["64:ff9b::7f00:1"], "ipv4_mapped"),
    # A public address FIRST -- the rejection must not depend on the private
    # address being the one the resolver happens to return first.
    "mixed-public-then-loop.example.com": (["1.2.3.4", "127.0.0.1"], "loopback"),
    "mixed-public-then-meta.example.com": (
        ["1.2.3.4", "169.254.169.254"],
        "metadata_service",
    ),
}

_UNRESOLVABLE_HOSTS = (
    # DNS for an unreleased AWS region does not exist until AWS publishes it.
    "bedrock-runtime.xx-unreleased-1.amazonaws.com",
    "unpublished.example.com",
)


def _addrinfo(ip: str, port: Any) -> Tuple[Any, ...]:
    """One ``getaddrinfo`` 5-tuple: (family, type, proto, canonname, sockaddr)."""
    obj = ipaddress.ip_address(ip)
    if obj.version == 6:
        return (
            socket.AF_INET6,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            (ip, port or 0, 0, 0),
        )
    return (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port or 0))


@pytest.fixture
def dns(monkeypatch: pytest.MonkeyPatch) -> List[str]:
    """Stub ``socket.getaddrinfo`` and RECORD every host it is asked for.

    The returned list is the call log. A test asserting "construction performs
    no DNS" reads it directly, so the assertion is about an observed call, not
    about elapsed time or a network error.
    """
    calls: List[str] = []

    def _stub(host: Any, port: Any = None, *args: Any, **kwargs: Any) -> list:
        calls.append(str(host))
        if host in _UNRESOLVABLE_HOSTS:
            raise socket.gaierror(8, "stubbed: host does not resolve")
        entry = _REBINDING_HOSTS.get(str(host))
        if entry is not None:
            return [_addrinfo(ip, port) for ip in entry[0]]
        if str(host) == "empty-resolve.example.com":
            return []
        return [_addrinfo("93.184.216.34", port)]

    monkeypatch.setattr(socket, "getaddrinfo", _stub)
    return calls


# ---------------------------------------------------------------------------
# Instrument check: this file must be testing THIS checkout
# ---------------------------------------------------------------------------


def test_modules_under_test_resolve_to_this_checkout() -> None:
    """Guard against certifying an installed copy instead of this branch.

    ``kaizen`` and ``kailash`` are both pip-installed in the usual dev
    environment, so a run whose path is not set up resolves the modules from
    site-packages and reports a green that says nothing about the working
    tree. Every other assertion in this file is only meaningful if this one
    holds, so it is asserted rather than assumed.
    """
    import kailash.utils.network_guard as network_guard
    from kaizen.llm import deployment, http_client

    # <repo>/packages/kailash-kaizen/tests/regression/<this file>
    repo_root = pathlib.Path(__file__).resolve().parents[4]
    for module in (deployment, http_client, network_guard):
        resolved = pathlib.Path(module.__file__).resolve()
        assert resolved.is_relative_to(repo_root), (
            f"{module.__name__} was imported from {resolved}, which is outside "
            f"{repo_root} -- this run is testing an installed copy, not this branch"
        )


# ---------------------------------------------------------------------------
# The fix: construction does not resolve
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "https://myfoundry.services.ai.azure.com",
        "https://rebind-loopback.example.com/v1",
        "https://bedrock-runtime.xx-unreleased-1.amazonaws.com",
    ],
)
def test_construction_performs_no_dns_lookup(dns: List[str], url: str) -> None:
    """No ``getaddrinfo`` call is made while an `Endpoint` is constructed.

    Before the fix the call log held the hostname. Note the third case: a host
    that resolves to LOOPBACK still constructs -- construction is not where
    that verdict belongs, and
    ``test_connect_time_gate_still_rejects_every_rebinding_address`` is the
    half that proves it is still reached.
    """
    Endpoint(base_url=url)
    assert dns == [], f"Endpoint construction resolved DNS for {dns!r}"


@pytest.mark.parametrize("host", _UNRESOLVABLE_HOSTS)
def test_unpublished_hostname_constructs(dns: List[str], host: str) -> None:
    """A well-formed endpoint whose DNS is unpublished is no longer invalid.

    This is the usability half of #2168: an unreleased Bedrock region can be
    modelled before AWS publishes the record. It is NOT reachable -- see
    ``test_connect_time_gate_rejects_unresolvable_host``.
    """
    endpoint = Endpoint(base_url=f"https://{host}")
    assert host in str(endpoint.base_url)
    assert dns == []


# ---------------------------------------------------------------------------
# Negative half 1: the connect-time gate still rejects everything
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("host", sorted(_REBINDING_HOSTS))
def test_connect_time_gate_still_rejects_every_rebinding_address(
    dns: List[str], host: str
) -> None:
    """The load-bearing assertion of #2168.

    For every address the construction-time resolve used to reject, the
    connect-time gate rejects it independently and with the SAME reason
    bucket -- which is why dropping the construction-time resolve lets zero
    additional addresses reach a TCP SYN. If ``SafeDnsResolver`` is ever
    removed from the transport, or its ladder drifts from the shared
    classifiers, this test goes red.
    """
    expected_reason = _REBINDING_HOSTS[host][1]

    # Construction now admits it...
    Endpoint(base_url=f"https://{host}/v1")

    # ...and the gate that owns the socket refuses it.
    with pytest.raises(InvalidEndpoint) as excinfo:
        SafeDnsResolver().check_host(host)
    assert excinfo.value.reason == expected_reason
    assert host in dns, "connect-time gate did not resolve the host it is guarding"


@pytest.mark.parametrize("host", (*_UNRESOLVABLE_HOSTS, "empty-resolve.example.com"))
def test_connect_time_gate_rejects_unresolvable_host(dns: List[str], host: str) -> None:
    """An unpublished name constructs but still cannot be connected to.

    ``resolution_failed`` moved from construction to send time; it did not
    disappear. This is what keeps ``test_unpublished_hostname_constructs``
    from being a widening.
    """
    Endpoint(base_url=f"https://{host}")
    with pytest.raises(InvalidEndpoint) as excinfo:
        SafeDnsResolver().check_host(host)
    assert excinfo.value.reason == "resolution_failed"


# ---------------------------------------------------------------------------
# Negative half 2: the offline checks still run at construction
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,reason",
    [
        # Literal addresses -- classified from the string, no DNS needed.
        ("https://127.0.0.1/v1", "loopback"),
        ("https://[::1]/v1", "loopback"),
        ("https://169.254.169.254/v1", "metadata_service"),
        ("https://10.0.0.5/v1", "private_ipv4"),
        ("https://192.168.1.1/v1", "private_ipv4"),
        # Metadata hostnames are rejected BY NAME, before any resolution.
        ("https://metadata.google.internal/v1", "metadata_host"),
        # Encoded / short-form address bypasses.
        ("https://0x7f000001/v1", "encoded_ip_bypass"),
        ("https://2130706433/v1", "encoded_ip_bypass"),
        # kaizen's HTTPS-only transport policy.
        ("http://api.openai.com/v1", "scheme"),
        ("ftp://api.openai.com/v1", "scheme"),
        # IDN homograph (Cyrillic "е" in "opеnai").
        ("https://api.opеnai.com/v1", "malformed_url"),
    ],
)
def test_offline_rejections_survive_at_construction(
    dns: List[str], url: str, reason: str
) -> None:
    """`resolve_dns=False` must not be mistaken for "skip the guard".

    Every one of these is decidable without a resolver, so every one still
    raises at construction -- and still without touching DNS.
    """
    with pytest.raises(InvalidEndpoint) as excinfo:
        Endpoint(base_url=url)
    assert excinfo.value.reason == reason
    assert dns == [], f"an offline rejection resolved DNS for {dns!r}"


def test_localhost_label_still_constructs_over_http(dns: List[str]) -> None:
    """The documented localhost carve-out is untouched by this change.

    Local-runtime presets (ollama / lm_studio / llama_cpp) depend on it.
    """
    Endpoint(base_url="http://localhost:11434")
    assert dns == []
