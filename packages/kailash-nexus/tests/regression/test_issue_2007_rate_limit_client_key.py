"""Issue #2007 — the trusted-proxy resolver was dead code.

``extractors/middleware.py`` calls ``resolve_client_host`` on every request and stores the
answer as ``request._nexus_resolved_client_host``. Repo-wide that attribute had exactly ONE
mention — the write. Nothing read it. Meanwhile all four rate-limit key derivations
hand-rolled the raw TCP peer::

    client_ip = request.client.host if request.client else "unknown"

So ``Nexus(trusted_proxy_cidrs=[...])`` — accepted, documented, and validated fail-fast —
affected no behaviour, and behind any reverse proxy every client shared ONE bucket.

Scoped honestly: this was never a spoofing bypass. The TCP peer cannot be forged, so limits
were not evadable via ``X-Forwarded-For``; the old keying erred fail-SAFE. What it was is an
availability defect in the standard production topology plus a dead operator-facing control.

The fix routes all four sites through ONE owner, ``proxy.client_key_for_request``, so a future
site cannot re-derive the key and drift — the same single-owner shape ``_public_tool_view``
uses in kailash-mcp.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
from typing import Optional

import pytest

from nexus.extractors.proxy import (
    client_key_for_request,
    resolve_client_host,
)


class _Client:
    """Stand-in for Starlette's immutable ``request.client``."""

    def __init__(self, host: str) -> None:
        self.host = host


class _Request:
    """Deterministic Protocol-satisfying stand-in for a Starlette Request.

    Not a mock: it exposes exactly the attributes the key derivation reads, with fixed
    values, so the assertion is about the derivation and not about a mock's configuration.
    """

    def __init__(
        self,
        peer: Optional[str],
        resolved: Optional[str] = None,
        headers: Optional[dict] = None,
    ) -> None:
        self.client = _Client(peer) if peer is not None else None
        if resolved is not None:
            self._nexus_resolved_client_host = resolved
        self.headers = _Headers(headers or {})

        class _State:
            user = None

        self.state = _State()


class _Headers:
    def __init__(self, mapping: dict) -> None:
        self._m = {k.lower(): v for k, v in mapping.items()}

    def get(self, name: str, default=None):
        return self._m.get(name.lower(), default)


# ---------------------------------------------------------------------------
# The single owner
# ---------------------------------------------------------------------------


class TestClientKeyForRequest:
    def test_prefers_the_middleware_resolved_host(self) -> None:
        """The whole point: the resolved originating client wins over the peer."""
        req = _Request(peer="10.0.0.1", resolved="203.0.113.7")
        assert client_key_for_request(req) == "203.0.113.7"

    def test_falls_back_to_peer_when_middleware_did_not_run(self) -> None:
        """The limiter is usable without the extractor middleware installed."""
        req = _Request(peer="198.51.100.4")
        assert client_key_for_request(req) == "198.51.100.4"

    def test_unknown_sentinel_preserved_when_there_is_no_client(self) -> None:
        """Preserves the pre-existing sentinel rather than raising or returning None."""
        req = _Request(peer=None)
        assert client_key_for_request(req) == "unknown"

    def test_empty_resolved_host_does_not_shadow_the_peer(self) -> None:
        """A falsy resolved value must not produce an empty key shared by every caller."""
        req = _Request(peer="198.51.100.4", resolved="")
        assert client_key_for_request(req) == "198.51.100.4"


# ---------------------------------------------------------------------------
# Behaviour preservation + the anti-spoofing property
# ---------------------------------------------------------------------------


class TestTrustPosture:
    def test_unconfigured_deployment_key_is_byte_identical_to_the_peer(self) -> None:
        """With no trusted CIDRs (the default) the key must not change at all.

        This is what makes the fix safe to ship: `resolve_client_host` returns the peer
        whenever the peer is untrusted, so an operator who configured nothing sees the
        exact key they saw before.
        """
        peer = "198.51.100.4"
        resolved = resolve_client_host(
            peer, _Headers({"X-Forwarded-For": "203.0.113.7"}), []
        )
        assert resolved == peer
        assert client_key_for_request(_Request(peer=peer, resolved=resolved)) == peer

    def test_untrusted_peer_sending_xff_cannot_move_its_own_bucket(self) -> None:
        """The anti-spoofing property the old code got right MUST survive the fix."""
        peer = "198.51.100.4"
        resolved = resolve_client_host(
            peer,
            _Headers({"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "5.6.7.8"}),
            ["10.0.0.0/8"],  # peer is NOT in here
        )
        assert resolved == peer
        assert client_key_for_request(_Request(peer=peer, resolved=resolved)) == peer

    def test_trusted_peer_forwards_the_originating_client(self) -> None:
        peer = "10.0.0.1"
        resolved = resolve_client_host(
            peer, _Headers({"X-Forwarded-For": "203.0.113.7"}), ["10.0.0.0/8"]
        )
        assert resolved == "203.0.113.7"
        assert client_key_for_request(_Request(peer=peer, resolved=resolved)) == (
            "203.0.113.7"
        )

    def test_two_clients_behind_one_trusted_proxy_get_separate_keys(self) -> None:
        """The availability defect this issue is really about."""
        keys = {
            client_key_for_request(
                _Request(
                    peer="10.0.0.1",
                    resolved=resolve_client_host(
                        "10.0.0.1",
                        _Headers({"X-Forwarded-For": origin}),
                        ["10.0.0.0/8"],
                    ),
                )
            )
            for origin in ("203.0.113.7", "203.0.113.8")
        }
        assert keys == {
            "203.0.113.7",
            "203.0.113.8",
        }, "distinct originating clients behind one proxy must not share a bucket"


# ---------------------------------------------------------------------------
# The two directly-callable rate-limit key functions
# ---------------------------------------------------------------------------


class TestRateLimitIdentifierExtractors:
    def test_auth_middleware_identifier_uses_the_resolved_host(self) -> None:
        from nexus.auth.rate_limit.middleware import RateLimitMiddleware

        req = _Request(peer="10.0.0.1", resolved="203.0.113.7")
        got = RateLimitMiddleware._default_identifier_extractor(None, req)
        assert (
            got == "ip:203.0.113.7"
        ), "the auth rate-limit middleware still keys on the raw peer"

    def test_decorator_default_identifier_uses_the_resolved_host(self) -> None:
        from nexus.auth.rate_limit import decorators as _dec

        src = inspect.getsource(_dec)
        assert (
            "client_key_for_request" in src
        ), "decorators.py does not route through the single owner"


# ---------------------------------------------------------------------------
# Structural guard — a FIFTH site must not land silently
# ---------------------------------------------------------------------------

_RATE_LIMIT_KEY_SITES = (
    "sse.py",
    "core.py",
    "auth/rate_limit/middleware.py",
    "auth/rate_limit/decorators.py",
)

_HAND_ROLLED = 'request.client.host if request.client else "unknown"'


@pytest.mark.regression
def test_no_rate_limit_site_rederives_the_peer_directly() -> None:
    """Pin the single-owner property.

    ``_public_tool_view``'s lesson, one package over: a projection that each surface
    hand-writes drifts the moment one of them is fixed. The literal below is the exact
    expression all four sites carried; its absence is what makes the owner load-bearing.
    """
    import nexus

    root = pathlib.Path(nexus.__file__).parent
    offenders = [
        site
        for site in _RATE_LIMIT_KEY_SITES
        if _HAND_ROLLED in (root / site).read_text()
    ]
    assert offenders == [], (
        "these rate-limit sites still re-derive the client key instead of calling "
        f"proxy.client_key_for_request: {offenders}"
    )


@pytest.mark.regression
def test_client_key_for_request_is_exported() -> None:
    """A helper absent from ``__all__`` invites the next author to re-roll their own."""
    from nexus.extractors import proxy

    assert "client_key_for_request" in proxy.__all__


@pytest.mark.regression
def test_resolved_host_attribute_now_has_a_reader() -> None:
    """The defect in one assertion: the attribute was WRITE-ONLY repo-wide.

    Guards the regression directly — if a future refactor drops the read, the
    trusted-proxy machinery silently becomes dead code again.
    """
    import nexus

    root = pathlib.Path(nexus.__file__).parent
    attr = "_nexus_resolved_client_host"
    writes, reads = 0, 0
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(), str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == attr:
                if isinstance(node.ctx, ast.Store):
                    writes += 1
                else:
                    reads += 1
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "getattr"
                and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and node.args[1].value == attr
            ):
                reads += 1
    assert writes >= 1, "the middleware no longer resolves the client host"
    assert reads >= 1, (
        f"{attr} is WRITE-ONLY again ({writes} writes, {reads} reads) — the "
        "trusted-proxy resolver is dead code and trusted_proxy_cidrs has no effect"
    )
