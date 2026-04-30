# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier-1 unit tests for Connection.headers exposure (issue #673).

The ``Connection.headers`` Mapping is the consumer-side escape
hatch for custom enforcement beyond the SDK's static
``allowed_origins`` allowlist (e.g., per-tenant signed-token check,
custom auth header validation). The contract:

- Captured at handshake; NOT refreshed during the connection.
- Read-only Mapping — mutation attempts raise ``TypeError``.
- Case-insensitive lookup (``conn.headers["origin"]`` and
  ``conn.headers["Origin"]`` return the same value).
- Defaults to an empty Mapping when no headers are supplied (test
  fixtures, alternate transports) so handlers do NOT need to guard
  ``if conn.headers is not None``.
"""

from __future__ import annotations

import pytest

from nexus.websocket_handlers import Connection


def test_headers_default_is_empty_mapping() -> None:
    """Connection constructed without headers exposes empty Mapping."""
    conn = Connection(ws=None, connection_id="c1", path="/x")
    assert len(conn.headers) == 0
    assert "origin" not in conn.headers


def test_headers_origin_round_trip() -> None:
    conn = Connection(
        ws=None,
        connection_id="c1",
        path="/x",
        headers={"Origin": "https://app.example.com"},
    )
    assert conn.headers["origin"] == "https://app.example.com"


def test_headers_lookup_is_case_insensitive() -> None:
    conn = Connection(
        ws=None,
        connection_id="c1",
        path="/x",
        headers={"Origin": "https://app.example.com"},
    )
    # All three should return the same value
    assert conn.headers["Origin"] == "https://app.example.com"
    assert conn.headers["origin"] == "https://app.example.com"
    assert conn.headers["ORIGIN"] == "https://app.example.com"


def test_headers_contains_is_case_insensitive() -> None:
    conn = Connection(
        ws=None,
        connection_id="c1",
        path="/x",
        headers={"Sec-WebSocket-Key": "abc"},
    )
    assert "sec-websocket-key" in conn.headers
    assert "Sec-WebSocket-Key" in conn.headers
    assert "SEC-WEBSOCKET-KEY" in conn.headers


def test_headers_get_returns_default() -> None:
    conn = Connection(
        ws=None,
        connection_id="c1",
        path="/x",
        headers={"Origin": "https://x.com"},
    )
    assert conn.headers.get("origin") == "https://x.com"
    assert conn.headers.get("missing") is None
    assert conn.headers.get("missing", "fallback") == "fallback"


def test_headers_iteration_yields_lower_keys() -> None:
    """Iteration MUST be deterministic and case-normalized so
    handlers iterating over headers see one canonical form."""
    conn = Connection(
        ws=None,
        connection_id="c1",
        path="/x",
        headers={
            "Origin": "https://x.com",
            "Host": "x.com",
            "User-Agent": "test/1.0",
        },
    )
    keys = sorted(conn.headers)
    assert keys == ["host", "origin", "user-agent"]


def test_headers_mutation_raises_type_error() -> None:
    """Operators MUST NOT be able to falsify captured headers from
    inside on_connect — issue #673 immutability invariant."""
    conn = Connection(
        ws=None,
        connection_id="c1",
        path="/x",
        headers={"Origin": "https://app.example.com"},
    )
    with pytest.raises(TypeError):
        conn.headers["x"] = "y"  # type: ignore[index]


def test_headers_deletion_raises_type_error() -> None:
    conn = Connection(
        ws=None,
        connection_id="c1",
        path="/x",
        headers={"Origin": "https://app.example.com"},
    )
    with pytest.raises(TypeError):
        del conn.headers["origin"]  # type: ignore[attr-defined]


def test_headers_snapshot_isolated_from_source_mutation() -> None:
    """Mutating the dict passed at construction MUST NOT affect
    Connection.headers — defense against on_connect-time mutation
    by the surrounding code."""
    source = {"Origin": "https://app.example.com"}
    conn = Connection(ws=None, connection_id="c1", path="/x", headers=source)
    source["Origin"] = "https://evil.com"
    source["X-Injected"] = "yes"
    assert conn.headers["origin"] == "https://app.example.com"
    assert "x-injected" not in conn.headers


def test_headers_with_websockets_headers_object() -> None:
    """When the websockets library passes its own Headers object
    (which is already case-insensitive), Connection.headers wraps
    it in the case-insensitive snapshot."""
    from websockets.datastructures import Headers

    h = Headers([("Origin", "https://app.example.com"), ("Host", "x")])
    conn = Connection(ws=None, connection_id="c1", path="/x", headers=h)
    assert conn.headers["origin"] == "https://app.example.com"
    assert conn.headers["host"] == "x"


def test_connection_id_and_path_preserved() -> None:
    """Smoke check the new headers param did not regress the existing
    Connection contract."""
    conn = Connection(
        ws="ws-stub",
        connection_id="abc123",
        path="/events",
        headers={"Origin": "https://x.com"},
    )
    assert conn.connection_id == "abc123"
    assert conn.path == "/events"
    assert conn.ws == "ws-stub"
    assert conn.alive is True
