# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""`Endpoint` construction is config parsing — it MUST NOT touch DNS.

Regression pin for the `reason=resolution_failed` class that made
`tests/unit/llm/test_deployment_resolver_azure.py` (Tier 1, offline)
depend on a live resolver: `Endpoint._validate_base_url` called
`url_safety.check_url(v)` with the default `resolve_dns=True`, so building
an `LlmDeployment` for `https://myfoundry.services.ai.azure.com` raised
`InvalidEndpoint(reason="resolution_failed")` wherever that name does not
resolve, while the sibling `https://myresource.openai.azure.com` passed
only because a real wildcard `*.openai.azure.com` A record answered.

Two halves are asserted here, and they are the reason the change does not
widen the SSRF posture:

1. **Nothing decidable offline was given up.** Every scheme / literal-IP /
   metadata / encoded-IP rejection still fires at construction, with the
   same reason code.
2. **The resolve-time gate is still the one that matters.**
   `SafeDnsResolver.check_host` re-resolves and re-classifies immediately
   before the TCP SYN, so a hostname that resolves into a private range is
   still refused — just at request time, where the answer is actually
   current, rather than at parse time, where it is not.

Tier 1, offline: `socket.getaddrinfo` is monkeypatched to RAISE if the
construction path calls it, so this test fails loudly if a future change
reintroduces resolution at parse time.

Differential evidence, 46 probes, pre- vs post-change
-----------------------------------------------------

Construction alone is not the security surface — a URL is egressed only if
BOTH gates admit it. Measuring construction alone shows one reject->ALLOW
and would read as a widening:

    AT CONSTRUCTION   TOTAL 46   DIFFERENCES 8   reject->ALLOW: 1
       'https://myfoundry.services.ai.azure.com'
           reject:resolution_failed -> ALLOW

Measuring the composite (`Endpoint(...)` AND
`SafeDnsResolver.check_host(host)`, i.e. "does this reach a TCP SYN") shows
what actually changed — the gate moved, the verdict did not:

    MODE real     REACHES_WIRE before=5 after=5   WIDENING AT THE WIRE: 0
       'https://myfoundry.services.ai.azure.com'
           reject@parse:resolution_failed -> reject@connect:resolution_failed

    MODE rebind   REACHES_WIRE before=2 after=2   WIDENING AT THE WIRE: 0
       (every hostname forced to resolve to 169.254.169.254)
       'https://api.openai.com/v1'
           reject@parse:metadata_service -> reject@connect:metadata_service
       'https://example.com/v1'                  (same move)
       'https://myresource.openai.azure.com'     (same move)
       'https://myfoundry.services.ai.azure.com' (same move)

The `rebind` mode is the discriminating half: it is the DNS-rebinding
scenario live DNS cannot produce on demand, and it is where a genuine
widening would surface as `REACHES_WIRE`. It does not. Same reason code,
same rejection, one gate later.

The other seven differences are the reason-code reclassifications this
branch already recorded in
`test_url_safety_shared_guard_consolidation.py` (three scheme-ordering
moves from the consolidation, four IMDS-wrapper moves from #2136) —
reproduced unchanged here, all reject->reject.
"""

from __future__ import annotations

import socket

import pytest

from kaizen.llm.deployment import Endpoint
from kaizen.llm.errors import InvalidEndpoint
from kaizen.llm.http_client import SafeDnsResolver

# Deliberately NOT resolvable — this is the shape that regressed.
_UNRESOLVABLE = "https://myfoundry.services.ai.azure.com"


@pytest.fixture
def _dns_is_a_landmine(monkeypatch: pytest.MonkeyPatch):
    """Any `getaddrinfo` call during the test explodes with a named error."""

    def _boom(*args, **kwargs):  # pragma: no cover - the assertion is the raise
        raise AssertionError(
            "Endpoint construction resolved DNS. Endpoint construction is "
            "config parsing, not egress — the resolve-time gate is "
            "SafeDnsResolver on the LlmHttpClient transport."
        )

    monkeypatch.setattr(socket, "getaddrinfo", _boom)


# ---------------------------------------------------------------------------
# 1. Construction does not resolve.
# ---------------------------------------------------------------------------


def test_endpoint_construction_does_not_resolve_dns(_dns_is_a_landmine) -> None:
    """A well-formed https endpoint builds with the resolver disarmed."""
    ep = Endpoint(base_url=_UNRESOLVABLE)
    assert "myfoundry.services.ai.azure.com" in str(ep.base_url)


def test_unresolvable_host_is_not_resolution_failed(_dns_is_a_landmine) -> None:
    """The exact regression: an NXDOMAIN name is a valid endpoint to PARSE."""
    ep = Endpoint(base_url=_UNRESOLVABLE, path_prefix="/models")
    assert ep.path_prefix == "/models"


def test_localhost_label_still_permitted_over_http(_dns_is_a_landmine) -> None:
    """The Ollama / Docker-Model-Runner default keeps working, offline."""
    ep = Endpoint(base_url="http://localhost:11434")
    assert "localhost" in str(ep.base_url)


# ---------------------------------------------------------------------------
# 2. Every offline-decidable rejection still fires at construction.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected_reason",
    [
        # HTTPS-only, except the `localhost` LABEL (kaizen policy, runs first).
        ("http://api.openai.com/v1", "scheme"),
        # The carve-out is label-only: a literal loopback IP is still refused.
        ("http://127.0.0.1:11434", "loopback"),
        ("https://127.0.0.1:11434", "loopback"),
        ("https://[::1]:11434", "loopback"),
        # Non-http(s) schemes.
        ("file:///etc/passwd", "scheme"),
        # RFC1918 / link-local literals.
        ("https://10.0.0.1/v1", "private_ipv4"),
        ("https://192.168.1.1/v1", "private_ipv4"),
        ("https://172.16.0.1/v1", "private_ipv4"),
        # Cloud metadata, by IP and by name.
        ("https://169.254.169.254/latest/meta-data", "metadata_service"),
        ("https://metadata.google.internal/v1", "metadata_host"),
        # Encoded-IP bypass forms.
        ("https://2130706433/v1", "encoded_ip_bypass"),
        ("https://0177.0.0.1/v1", "encoded_ip_bypass"),
        ("https://127.1/v1", "encoded_ip_bypass"),
        # IPv6 embedded-IPv4 wrappers.
        ("https://[::ffff:127.0.0.1]/v1", "ipv4_mapped"),
    ],
)
def test_offline_decidable_rejections_still_fire_at_construction(
    url: str, expected_reason: str, _dns_is_a_landmine
) -> None:
    """Disabling resolution gave up nothing that parse time could decide."""
    with pytest.raises(InvalidEndpoint) as exc_info:
        Endpoint(base_url=url)
    assert exc_info.value.reason == expected_reason, (
        f"{url!r}: expected reason={expected_reason!r}, "
        f"got {exc_info.value.reason!r}"
    )


# ---------------------------------------------------------------------------
# 3. The resolve-time gate still refuses a rebinding host.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "resolved_ip,expected_reason",
    [
        ("127.0.0.1", "private_ipv4"),
        ("10.0.0.5", "private_ipv4"),
        ("169.254.169.254", "metadata_service"),
    ],
)
def test_safe_dns_resolver_still_refuses_the_host_construction_admitted(
    monkeypatch: pytest.MonkeyPatch, resolved_ip: str, expected_reason: str
) -> None:
    """Construction admits the NAME; the connect-time gate refuses the ADDRESS.

    This is the half that makes `resolve_dns=False` at construction safe: the
    URL is admitted into config, and then refused before the TCP SYN by the
    gate that re-resolves at the moment of use.
    """
    ep = Endpoint(base_url="https://rebinding.example.com/v1")
    host = str(ep.base_url).split("://", 1)[1].split("/", 1)[0]

    def _fake_getaddrinfo(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (resolved_ip, 443))]

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo)

    with pytest.raises(InvalidEndpoint) as exc_info:
        SafeDnsResolver().check_host(host)
    assert exc_info.value.reason == expected_reason
