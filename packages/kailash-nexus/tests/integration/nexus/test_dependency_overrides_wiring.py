# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 2 wiring tests for ``Nexus.dependency_overrides`` (AC 3).

Drives a REAL Nexus HTTP gateway via Starlette's ``TestClient`` — the full
ASGI stack (request-capture middleware -> workflow route -> HandlerNode ->
resolver chain -> handler) executes end to end against the live override map.
NO MOCKING (the ``DependencyOverrideMap`` IS the test-injection surface under
test; replacing a real dependency with a test callable is exactly its job).

Per ``rules/facade-manager-detection.md`` (manager-shape ``*Map`` exposed as a
facade attribute -> ``*_wiring.py`` test that exercises through the facade) and
``rules/testing.md`` § "One Direct Test Per Variant In Every Delegating Pair"
(``override`` / ``set`` / ``clear`` / ``clear_all`` each get a direct test).

Covers (spec §144-171):
- Context-manager ``override`` changes resolution end-to-end AND restores after
  the block (real resolution returns once the block exits).
- Restore-after-exception: the override is removed even when the block raises.
- Imperative ``set`` / ``clear`` / ``clear_all`` — direct + end-to-end effect.
- Concurrent overrides from two threads at setup (serialised by the map lock).
- Runtime-mutation guard: mutating the map from INSIDE a handler (active
  request) raises ``DependencyOverrideRuntimeMutationError`` with the 3-field
  message.
"""

import asyncio
import itertools
import socket
import threading

import pytest
from fastapi.testclient import TestClient

from nexus import Nexus
from nexus.extractors import (
    DependencyOverrideMap,
    DependencyOverrideRuntimeMutationError,
    Depends,
    Request,
)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _client_for(app: Nexus) -> TestClient:
    """Register handler routes on the live gateway and return a TestClient."""
    asyncio.run(app._http_transport.start(app._registry))
    assert app.fastapi_app is not None
    return TestClient(app.fastapi_app, raise_server_exceptions=False)


def _handler_output(resp_json: dict) -> dict:
    """Extract the handler node output from the WorkflowAPI execute response."""
    return resp_json["outputs"]["handler"]


# Module-level dependency callables so the SAME object identity is used as the
# override key across requests (Depends keys on the callable object).
def get_user(request: Request) -> dict:
    return {"id": request.headers.get("x-user-id", "anonymous"), "source": "real"}


# Monotonic nonce so every _invoke produces a UNIQUE request body. The gateway
# deduplicator fingerprints the request body and serves a cached response for an
# identical body within its TTL; the override/clear tests invoke the SAME
# endpoint repeatedly to observe a resolution CHANGE, so each call MUST be a
# cache miss to exercise the live resolver chain rather than a stale envelope.
_nonce = itertools.count()


def _invoke(client: TestClient, path: str = "whoami") -> dict:
    resp = client.post(
        f"/workflows/{path}/execute",
        json={"inputs": {"_nonce": next(_nonce)}},
        headers={"X-User-Id": "u-1"},
    )
    assert resp.status_code == 200, resp.text
    return _handler_output(resp.json())


# --------------------------------------------------------------------------- #
# Context-manager override + restore                                          #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_context_manager_override_changes_resolution_then_restores():
    """`override` swaps the dependency end-to-end; restores after the block."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def whoami(user: dict = Depends(get_user)) -> dict:
        return {"user": user}

    app.handler_extract("whoami", whoami)
    client = _client_for(app)

    # Before: real resolution.
    before = _invoke(client)
    assert before == {"user": {"id": "u-1", "source": "real"}}, before

    # Inside the block: the mock callable resolves in place of the real one.
    def mock_user() -> dict:
        return {"id": "test-user", "source": "mock"}

    with app.dependency_overrides.override(get_user, mock_user):
        during = _invoke(client)
        assert during == {"user": {"id": "test-user", "source": "mock"}}, during

    # After the block: real resolution again (restore verified end-to-end).
    after = _invoke(client)
    assert after == {"user": {"id": "u-1", "source": "real"}}, after


@pytest.mark.integration
def test_override_restored_after_block_body_raises():
    """The override is removed even when the `with` block body raises."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def whoami(user: dict = Depends(get_user)) -> dict:
        return {"user": user}

    app.handler_extract("whoami", whoami)
    client = _client_for(app)

    def mock_user() -> dict:
        return {"id": "test-user", "source": "mock"}

    class _Boom(RuntimeError):
        pass

    with pytest.raises(_Boom):
        with app.dependency_overrides.override(get_user, mock_user):
            # The override is live here.
            assert app.dependency_overrides[get_user] is mock_user
            raise _Boom("block body failed")

    # Despite the exception, the override was restored (removed).
    assert get_user not in app.dependency_overrides
    after = _invoke(client)
    assert after == {"user": {"id": "u-1", "source": "real"}}, after


@pytest.mark.integration
def test_override_restores_prior_override_not_just_absence():
    """Nested override restores the PRIOR override, not bare absence."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    def outer_mock() -> dict:
        return {"id": "outer", "source": "mock"}

    def inner_mock() -> dict:
        return {"id": "inner", "source": "mock"}

    app.dependency_overrides.set(get_user, outer_mock)
    try:
        with app.dependency_overrides.override(get_user, inner_mock):
            assert app.dependency_overrides[get_user] is inner_mock
        # Exiting the block restores the OUTER override, not absence.
        assert app.dependency_overrides[get_user] is outer_mock
    finally:
        app.dependency_overrides.clear(get_user)


# --------------------------------------------------------------------------- #
# Imperative set / clear / clear_all — direct + end-to-end                    #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_set_overrides_resolution_end_to_end():
    """`set` is imperative: it persists until cleared and changes resolution."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def whoami(user: dict = Depends(get_user)) -> dict:
        return {"user": user}

    app.handler_extract("whoami", whoami)
    client = _client_for(app)

    def mock_user() -> dict:
        return {"id": "set-user", "source": "mock"}

    # Direct effect on the map.
    app.dependency_overrides.set(get_user, mock_user)
    assert get_user in app.dependency_overrides
    assert app.dependency_overrides[get_user] is mock_user

    # End-to-end effect through the live gateway.
    out = _invoke(client)
    assert out == {"user": {"id": "set-user", "source": "mock"}}, out


@pytest.mark.integration
def test_clear_removes_single_override_and_is_idempotent():
    """`clear` removes one override end-to-end; second call is a no-op."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def whoami(user: dict = Depends(get_user)) -> dict:
        return {"user": user}

    app.handler_extract("whoami", whoami)
    client = _client_for(app)

    def mock_user() -> dict:
        return {"id": "set-user", "source": "mock"}

    app.dependency_overrides.set(get_user, mock_user)
    assert _invoke(client)["user"]["source"] == "mock"

    # Direct: clear removes it.
    app.dependency_overrides.clear(get_user)
    assert get_user not in app.dependency_overrides
    # Idempotent: clearing an absent override is a no-op (no raise).
    app.dependency_overrides.clear(get_user)

    # End-to-end: real resolution restored.
    out = _invoke(client)
    assert out == {"user": {"id": "u-1", "source": "real"}}, out


@pytest.mark.integration
def test_clear_all_removes_every_override_end_to_end():
    """`clear_all` empties the map end-to-end."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    async def whoami(user: dict = Depends(get_user)) -> dict:
        return {"user": user}

    app.handler_extract("whoami", whoami)
    client = _client_for(app)

    def mock_a() -> dict:
        return {"id": "a", "source": "mock"}

    def mock_b() -> dict:
        return {"id": "b", "source": "mock"}

    # Two distinct overrides set.
    app.dependency_overrides.set(get_user, mock_a)

    def other_dep() -> str:
        return "other"

    app.dependency_overrides.set(other_dep, mock_b)
    assert len(app.dependency_overrides) == 2

    # Direct: clear_all empties the map.
    app.dependency_overrides.clear_all()
    assert len(app.dependency_overrides) == 0
    assert get_user not in app.dependency_overrides

    # End-to-end: real resolution restored.
    out = _invoke(client)
    assert out == {"user": {"id": "u-1", "source": "real"}}, out


# --------------------------------------------------------------------------- #
# Concurrent overrides from two threads at setup                              #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_concurrent_overrides_from_two_threads():
    """Two threads each set a distinct override; the map lock serialises them.

    No request is active during this setup-window mutation, so the runtime
    guard does not fire. After both threads join, both overrides are present —
    the lock guarantees no interleaved write lost an entry.
    """
    overrides = DependencyOverrideMap()

    def dep_a() -> str:
        return "a"

    def dep_b() -> str:
        return "b"

    def mock_a() -> str:
        return "mock-a"

    def mock_b() -> str:
        return "mock-b"

    barrier = threading.Barrier(2)

    def worker_a() -> None:
        barrier.wait()
        for _ in range(200):
            overrides.set(dep_a, mock_a)

    def worker_b() -> None:
        barrier.wait()
        for _ in range(200):
            overrides.set(dep_b, mock_b)

    ta = threading.Thread(target=worker_a)
    tb = threading.Thread(target=worker_b)
    ta.start()
    tb.start()
    ta.join()
    tb.join()

    assert overrides[dep_a] is mock_a
    assert overrides[dep_b] is mock_b
    assert len(overrides) == 2


# --------------------------------------------------------------------------- #
# Runtime-mutation guard (spec §169, MED-1)                                   #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_runtime_mutation_from_inside_handler_raises_three_field_error():
    """Mutating the override map DURING a request raises the typed guard error.

    A handler that calls ``app.dependency_overrides.override(...)`` is mutating
    the test-only surface while a request is bound. The guard raises
    ``DependencyOverrideRuntimeMutationError`` naming (a) the callable
    ``__qualname__``, (b) the active request correlation id, (c) the
    operator-audit lookup hint.
    """
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    captured: dict = {}

    async def mutating_handler() -> dict:
        # Mutate the override map from inside the active request — BLOCKED.
        try:
            app.dependency_overrides.set(get_user, lambda: {"id": "x"})
        except DependencyOverrideRuntimeMutationError as exc:
            captured["error"] = str(exc)
            return {"guard": "raised", "message": str(exc)}
        return {"guard": "did-not-raise"}

    app.handler_extract("mutate", mutating_handler)
    client = _client_for(app)

    out = _invoke(client, path="mutate")
    assert out["guard"] == "raised", out

    message = captured["error"]
    # Field (a): the overridden callable's __qualname__.
    assert "get_user" in message, message
    # Field (b): the active request correlation id marker (X-Request-ID absent
    # here, so the server-minted request-active:<uuid> marker is used).
    assert "request-active:" in message or "active request" in message, message
    # Field (c): operator-audit lookup hint pointing at the server log.
    assert "server log" in message, message
    # The op name is named in the message.
    assert "DependencyOverrideMap.set" in message, message


@pytest.mark.integration
def test_runtime_mutation_uses_x_request_id_header_when_present():
    """The guard message carries the inbound X-Request-ID as correlation id."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    captured: dict = {}

    async def mutating_handler() -> dict:
        try:
            app.dependency_overrides.clear_all()
        except DependencyOverrideRuntimeMutationError as exc:
            captured["error"] = str(exc)
            return {"guard": "raised"}
        return {"guard": "did-not-raise"}

    app.handler_extract("mutate2", mutating_handler)
    client = _client_for(app)

    resp = client.post(
        "/workflows/mutate2/execute",
        json={"inputs": {}},
        headers={"X-Request-ID": "corr-12345"},
    )
    assert resp.status_code == 200, resp.text
    out = _handler_output(resp.json())
    assert out["guard"] == "raised", out

    message = captured["error"]
    assert "corr-12345" in message, message
    # clear_all names the synthetic <all overrides> token (no single callable).
    assert "<all overrides>" in message, message
    assert "DependencyOverrideMap.clear_all" in message, message


@pytest.mark.integration
def test_mutation_outside_request_does_not_raise():
    """Mutating the map with NO active request is the normal test path."""
    app = Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)

    def mock_user() -> dict:
        return {"id": "ok", "source": "mock"}

    # No request bound — all four mutators succeed.
    app.dependency_overrides.set(get_user, mock_user)
    app.dependency_overrides.clear(get_user)
    app.dependency_overrides.clear_all()
    with app.dependency_overrides.override(get_user, mock_user):
        assert app.dependency_overrides[get_user] is mock_user
    assert get_user not in app.dependency_overrides
