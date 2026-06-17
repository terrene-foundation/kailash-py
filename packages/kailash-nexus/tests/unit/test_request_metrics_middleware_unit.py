# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tier 1 unit tests for RequestMetricsMiddleware internals.

Covers the cardinality-control route-label helper and the middleware's
ASGI __call__ behavior against a fake inner app — exception-path status
recording, exclude-paths pass-through, and the prometheus-absent no-op —
without standing up a real Nexus instance.
"""

import types

import pytest

from nexus.middleware.request_metrics import RequestMetricsMiddleware, _route_label

# ---------------------------------------------------------------------------
# _route_label — cardinality control
# ---------------------------------------------------------------------------


def test_route_label_prefers_path_format():
    """A route exposing path_format returns the template, not a concrete path."""
    route = types.SimpleNamespace(path_format="/users/{id}", path="/users/{id}")
    scope = {"route": route}
    assert _route_label(scope) == "/users/{id}"


def test_route_label_falls_back_to_path():
    """When path_format is absent, the route's path attribute is used."""
    route = types.SimpleNamespace(path="/x")
    scope = {"route": route}
    assert _route_label(scope) == "/x"


def test_route_label_no_route_returns_sentinel():
    """No matched route collapses to the bounded __unmatched__ sentinel."""
    assert _route_label({}) == "__unmatched__"


def test_route_label_route_without_usable_template_returns_sentinel():
    """A route object with neither path_format nor path returns the sentinel."""
    route = types.SimpleNamespace(path_format=None, path=None)
    assert _route_label({"route": route}) == "__unmatched__"


# ---------------------------------------------------------------------------
# __call__ — exception path records status 500 and re-propagates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_records_500_on_unhandled_exception(monkeypatch):
    """An inner app raising before http.response.start is recorded as 500."""
    observed = {}

    def _fake_observe(method, route, status, duration):
        observed["method"] = method
        observed["route"] = route
        observed["status"] = status
        observed["duration"] = duration

    monkeypatch.setattr(
        "nexus.metrics.observe_http_request", _fake_observe, raising=True
    )

    async def boom(scope, receive, send):
        raise RuntimeError("handler exploded")

    mw = RequestMetricsMiddleware(boom)
    mw._enabled = True

    scope = {"type": "http", "path": "/boom", "method": "POST"}

    async def receive():
        return {"type": "http.request"}

    sent = []

    async def send(msg):
        sent.append(msg)

    with pytest.raises(RuntimeError, match="handler exploded"):
        await mw(scope, receive, send)

    # finally-block recorded the request before re-propagating
    assert observed["status"] == 500
    assert observed["method"] == "POST"
    assert observed["route"] == "__unmatched__"
    assert observed["duration"] >= 0.0


@pytest.mark.asyncio
async def test_call_records_response_start_status(monkeypatch):
    """A normal response records the status carried on http.response.start."""
    observed = {}

    monkeypatch.setattr(
        "nexus.metrics.observe_http_request",
        lambda method, route, status, duration: observed.update(
            method=method, route=route, status=status
        ),
        raising=True,
    )

    async def ok_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 201, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    mw = RequestMetricsMiddleware(ok_app)
    mw._enabled = True

    scope = {"type": "http", "path": "/ok", "method": "GET"}

    async def receive():
        return {"type": "http.request"}

    async def send(msg):
        pass

    await mw(scope, receive, send)
    assert observed["status"] == 201
    assert observed["method"] == "GET"


# ---------------------------------------------------------------------------
# __call__ — exclude paths + non-http + prometheus-absent pass-through
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_excludes_metrics_path(monkeypatch):
    """A request to an excluded path is passed through with no metric recorded."""
    called = {"observe": False}
    monkeypatch.setattr(
        "nexus.metrics.observe_http_request",
        lambda *a, **k: called.update(observe=True),
        raising=True,
    )

    inner_called = {"hit": False}

    async def inner(scope, receive, send):
        inner_called["hit"] = True

    mw = RequestMetricsMiddleware(inner)
    mw._enabled = True

    scope = {"type": "http", "path": "/metrics", "method": "GET"}
    await mw(scope, lambda: None, lambda m: None)

    assert inner_called["hit"] is True
    assert called["observe"] is False


@pytest.mark.asyncio
async def test_call_passthrough_for_non_http_scope(monkeypatch):
    """A non-http scope (websocket/lifespan) bypasses instrumentation."""
    called = {"observe": False}
    monkeypatch.setattr(
        "nexus.metrics.observe_http_request",
        lambda *a, **k: called.update(observe=True),
        raising=True,
    )

    inner_called = {"hit": False}

    async def inner(scope, receive, send):
        inner_called["hit"] = True

    mw = RequestMetricsMiddleware(inner)
    mw._enabled = True

    scope = {"type": "websocket", "path": "/ws"}
    await mw(scope, lambda: None, lambda m: None)

    assert inner_called["hit"] is True
    assert called["observe"] is False


@pytest.mark.asyncio
async def test_call_noop_when_prometheus_absent(monkeypatch):
    """With prometheus disabled the middleware passes through and never observes."""
    called = {"observe": False}
    monkeypatch.setattr(
        "nexus.metrics.observe_http_request",
        lambda *a, **k: called.update(observe=True),
        raising=True,
    )

    inner_called = {"hit": False}

    async def inner(scope, receive, send):
        inner_called["hit"] = True

    mw = RequestMetricsMiddleware(inner)
    # Force the prometheus-absent branch regardless of install state.
    mw._enabled = False

    scope = {"type": "http", "path": "/anything", "method": "GET"}
    await mw(scope, lambda: None, lambda m: None)

    assert inner_called["hit"] is True
    assert called["observe"] is False
