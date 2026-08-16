"""Tier-1 unit-test conftest for kailash-kaizen.

Holds the autouse fixtures that keep the unit tier offline: an LLM stub
(``_stub_trait_derivation``, below) and a DNS stub (``_hermetic_dns``, at the
foot of this file). Both exist for the same reason — ``rules/testing.md``
§ 3-Tier requires Tier-1 tests to run with no live service and no network.

Issue #829: trait derivation is now LLM-first via ``RoleToTraitsSignature``.
Tier-1 unit tests MUST NOT depend on a live LLM (``rules/testing.md``
§ 3-Tier Testing). The autouse fixture below stubs
``Kaizen._generate_role_based_traits`` with a deterministic default for the
duration of every unit test.

Tier-2 integration and Tier-3 e2e tests live below their own conftests and
DO NOT inherit this stub — derivation runs against the real LLM there.

Tests that want to exercise the LLM derivation explicitly can either:
1. Pass ``behavior_traits=[...]`` in config (skips derivation entirely — the
   documented user-facing escape hatch).
2. Override the autouse fixture via a sibling conftest.

The stub returns the same default list the keyword classifier returned for
"unmatched" roles before this fix, so any unit test that spot-checks
``agent.behavior_traits`` for the default keeps working.
"""

from __future__ import annotations

import errno
import ipaddress
import os
import socket
from typing import Any, Dict, List, Tuple

import pytest

# Unit-tier deterministic model default (issue-822 pattern): agent/framework
# construction resolves the model from the environment and raises
# kaizen.errors.EnvModelMissing otherwise. No CI lane or committed .env
# supplies KAIZEN_DEFAULT_MODEL, so unit tests that construct agents without
# an explicit model fail on clean environments. setdefault preserves any
# operator/.env value; the env-model discipline tests
# (test_kaizen_default_model_env.py) monkeypatch.delenv/setenv per test and
# are unaffected.
os.environ.setdefault("KAIZEN_DEFAULT_MODEL", "gpt-4o-mini")

_DEFAULT_TIER1_TRAITS: List[str] = ["professional", "reliable", "adaptive"]


@pytest.fixture(autouse=True)
def _stub_trait_derivation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``Kaizen._generate_role_based_traits`` with a deterministic stub.

    Per Issue #829, real derivation calls an LLM. Tier-1 unit tests MUST NOT
    require a working LLM provider. This stub returns a fixed list so tests
    that rely on the default-derivation path stay deterministic and offline.
    """
    from kaizen.core.framework import Kaizen

    def _stub(self, role: str) -> List[str]:
        return list(_DEFAULT_TIER1_TRAITS)

    monkeypatch.setattr(Kaizen, "_generate_role_based_traits", _stub)


# ---------------------------------------------------------------------------
# Hermetic DNS
# ---------------------------------------------------------------------------
#
# ``Endpoint.base_url`` routes every URL through ``url_safety.check_url()``,
# whose DNS-rebinding defense calls ``socket.getaddrinfo``. Constructing an
# endpoint therefore performs a LIVE DNS LOOKUP, so any unit test that builds
# a deployment/preset silently depends on a working resolver — a Tier-1
# network dependency (``rules/testing.md`` § 3-Tier: unit tests MUST NOT touch
# the network).
#
# The dependency was invisible because the fake fixture hostnames split by
# accident: ``myresource.openai.azure.com`` RESOLVES (Azure publishes a
# wildcard record for ``*.openai.azure.com``) while the equally-fake
# ``myfoundry.services.ai.azure.com`` does NOT. Measured on an air-gapped
# runner (``socket.getaddrinfo`` raising for every host), 255 of 1615 tests
# under ``tests/unit/llm`` plus 6 under ``tests/unit/providers`` failed — the
# handful of Azure-AI-Foundry failures were only the visible corner.
#
# The stub below removes the dependency without touching production code.
# Whether a DNS lookup belongs inside endpoint construction at all is a real
# design question, tracked separately; this fixture does not prejudge it.

# Returned for every host without an explicit mapping. It must be an address
# the guard classifies as PUBLIC, which rules out the RFC 5737 documentation
# ranges (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24): Python's
# ``ipaddress`` reports all three as ``.is_private``, so ``_is_private_ipv4``
# would reject them and every endpoint construction would fail.
_STUB_PUBLIC_IPV4 = "93.184.216.34"

# Hosts whose real-world address the guard is expected to act on. The cloud
# metadata hostnames are already rejected by NAME (``_METADATA_HOSTNAMES``)
# before resolution runs, so these entries are defense-in-depth: if that
# name check is ever narrowed, the resolution-path ``_METADATA_IPS`` check
# still fires under the stub instead of silently passing.
_STUB_DNS: Dict[str, Tuple[str, ...]] = {
    "localhost": ("127.0.0.1", "::1"),
    "metadata.google.internal": ("169.254.169.254",),
    "metadata.azure.com": ("169.254.169.254",),
    "metadata.aws.internal": ("169.254.169.254",),
}


def _addrinfo(ip: str, port: int) -> Tuple[Any, ...]:
    """One ``getaddrinfo`` 5-tuple: (family, type, proto, canonname, sockaddr)."""
    if ":" in ip:
        sockaddr: Tuple[Any, ...] = (ip, port, 0, 0)
        family = socket.AF_INET6
    else:
        sockaddr = (ip, port)
        family = socket.AF_INET
    return (family, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", sockaddr)


def _stub_getaddrinfo(host: Any, port: Any = None, *args: Any, **kwargs: Any) -> list:
    """Deterministic in-process stand-in for ``socket.getaddrinfo``.

    Unknown hosts resolve to a fixed public address rather than raising. An
    explicit allowlist was rejected: it would have to enumerate every fixture
    hostname in the tier and would fail closed the moment a test introduced a
    new one — re-creating exactly the trap this fixture removes.

    A host that is ALREADY a literal IP is returned unchanged, matching real
    ``getaddrinfo``. Remapping it would silently redirect every loopback
    client in the tier: the ollama fallback dials ``127.0.0.1:11434`` and,
    when that was rewritten to a public address, spent 75s black-holed across
    its retry budget instead of being refused in 0.05s.
    """
    host_s = str(host).strip("[]")
    port_num = port if isinstance(port, int) else 0

    try:
        ipaddress.ip_address(host_s)
    except ValueError:
        ips = _STUB_DNS.get(host_s.lower(), (_STUB_PUBLIC_IPV4,))
    else:
        ips = (host_s,)

    return [_addrinfo(ip, port_num) for ip in ips]


_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _is_loopback(address: Any) -> bool:
    """True if an AF_INET/AF_INET6 sockaddr points at loopback."""
    if not isinstance(address, tuple) or not address:
        return False
    try:
        return ipaddress.ip_address(str(address[0]).strip("[]")).is_loopback
    except ValueError:
        return False


def _refuse(self: socket.socket, address: Any) -> Any:
    """Refuse non-loopback TCP/UDP connects the way a closed port would."""
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
        raise ConnectionRefusedError(
            errno.ECONNREFUSED,
            "Tier-1 unit tests MUST NOT touch the network "
            f"(blocked connect to {address!r}); see tests/unit/conftest.py",
        )
    return _real_connect(self, address)


def _refuse_ex(self: socket.socket, address: Any) -> Any:
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(address):
        return errno.ECONNREFUSED
    return _real_connect_ex(self, address)


@pytest.fixture(autouse=True)
def _hermetic_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every Tier-1 unit test resolve hostnames in-process.

    Patches the same seam the SSRF rebinding tests already use
    (``monkeypatch.setattr(socket, "getaddrinfo", ...)``), so a test that
    needs to drive resolution itself simply re-patches inside its own body —
    the function-scoped patch applied later wins for that test's duration.

    Only the DNS-rebinding branch of ``check_url`` is affected. Every other
    rejection (scheme, ``metadata_host``, encoded-IP bypass, inet_aton
    short-form, literal-IP range checks) runs BEFORE resolution and is
    exercised unchanged.

    Non-loopback connects are refused as well. Resolving a name is only half
    the dependency: several tests deliberately drive an ungoverned egress and
    swallow the result (``except Exception: pass``), so they were fast only
    because the lookup failed first. Once the name resolves, the same tests
    black-hole for their full 60s timeout — and on a runner where the address
    is reachable they would issue a REAL request from the unit tier. Refusing
    the connect gives them the same fast, offline failure they always relied
    on. Loopback is left alone so an in-process helper server still works.
    """
    monkeypatch.setattr(socket, "getaddrinfo", _stub_getaddrinfo)
    monkeypatch.setattr(socket.socket, "connect", _refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", _refuse_ex)
