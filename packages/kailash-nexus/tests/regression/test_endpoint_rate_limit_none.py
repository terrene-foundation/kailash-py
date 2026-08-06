# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: a None rate limit MUST mean "unlimited", not a per-request 500.

``Nexus.endpoint()`` resolves its limit as::

    if rate_limit is None:
        rate_limit = self.rate_limit_config.get("default_rate_limit", 100)

``rate_limit_config`` is ``Dict[str, Any]``, so an explicit
``{"default_rate_limit": None}`` resolves to None here rather than to the 100
default -- the key EXISTS, so ``.get()`` never reaches its default. The request
wrapper then evaluated ``rate_limit > 0``, raising::

    TypeError: '>' not supported between instances of 'NoneType' and 'int'

inside request handling, i.e. an unconditional HTTP 500 on every call to the
endpoint, reachable purely through the public ``Nexus(rate_limit_config=...)``
constructor kwarg. ``endpoint()``'s own docstring documents
``rate_limit`` as "None=unlimited", so the correct behaviour is to skip rate
limiting, not to crash.

Surfaced as pyright errors at ``core.py`` 2256/2263/2313 (``Operator ">" not
supported for "None"``) and confirmed reachable at runtime before the fix.
"""

import logging

import pytest
from fastapi.testclient import TestClient
from nexus import Nexus


def _client(app: Nexus) -> TestClient:
    """Build a TestClient, asserting the gateway actually initialised."""
    fastapi_app = app.fastapi_app
    assert fastapi_app is not None, (
        "Nexus.fastapi_app is None -- the enterprise gateway was not "
        "initialised, so the endpoint cannot be exercised."
    )
    return TestClient(fastapi_app)


@pytest.mark.regression
def test_none_default_rate_limit_means_unlimited_not_500():
    """An explicit ``{"default_rate_limit": None}`` MUST serve, not 500.

    Falsifying result: before the fix this request raised
    ``TypeError: '>' not supported between instances of 'NoneType' and 'int'``
    out of the rate-limit wrapper.
    """
    app = Nexus(
        api_port=8241,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
        rate_limit_config={"default_rate_limit": None},
    )

    @app.endpoint("/probe-unlimited", methods=["GET"])
    async def probe():
        return {"ok": True}

    try:
        response = _client(app).get("/probe-unlimited")
        assert response.status_code == 200, response.text
        assert response.json() == {"ok": True}
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_none_rate_limit_does_not_rate_limit_across_many_requests():
    """ "Unlimited" MUST actually be unlimited, not silently capped.

    Guards the wrong fix (coercing None to the 100 default): 120 sequential
    requests would then start returning 429.
    """
    app = Nexus(
        api_port=8242,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
        rate_limit_config={"default_rate_limit": None},
    )

    @app.endpoint("/probe-many", methods=["GET"])
    async def probe():
        return {"ok": True}

    try:
        client = _client(app)
        statuses = {client.get("/probe-many").status_code for _ in range(120)}
        assert statuses == {200}, f"expected only 200s, saw {sorted(statuses)}"
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_positive_rate_limit_still_enforced():
    """The None fix MUST NOT disable rate limiting where it IS configured.

    Guards the opposite wrong fix (treating every limit as unlimited): a
    configured limit of 5 must still produce a 429 once exceeded.

    The handler declares ``request: Request`` deliberately -- the wrapper can
    only rate-limit when it finds a FastAPI ``Request`` in the handler's
    args/kwargs, so a handler without one is never limited. That precondition
    is PRE-EXISTING and is pinned by
    ``test_rate_limit_no_op_without_request_parameter`` below.
    """
    from fastapi import Request

    app = Nexus(
        api_port=8243,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    @app.endpoint("/probe-limited", methods=["GET"], rate_limit=5)
    async def probe(request: Request):
        return {"ok": True}

    try:
        client = _client(app)
        statuses = [client.get("/probe-limited").status_code for _ in range(12)]
        assert (
            429 in statuses
        ), f"rate limit of 5 was never enforced over 12 requests: {statuses}"
        assert statuses[0] == 200, f"first request should succeed, got {statuses[0]}"
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_inert_rate_limit_warns_at_registration(caplog):
    """A configured limit that CANNOT engage MUST warn loudly at registration.

    A documented ``rate_limit=`` kwarg with zero effect on the body is the
    silent-fallback mode at the API surface (zero-tolerance Rule 3c). Making
    limiting unconditional would change security behaviour for every existing
    endpoint, so per security.md's secure-default pattern the enforcement is
    unchanged and the SILENCE is what ends: one loud WARN at registration
    naming the OFF protection and its exact wiring.

    Falsifying result: before the fix, registering a limited endpoint with no
    ``Request`` parameter emitted nothing at all.
    """
    app = Nexus(
        api_port=8246,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-inert", methods=["GET"], rate_limit=5)
            async def probe():
                return {"ok": True}

        inert = [r for r in caplog.records if "rate_limit_inert" in r.getMessage()]
        assert inert, (
            "no rate_limit_inert warning emitted; messages were: "
            f"{[r.getMessage() for r in caplog.records]}"
        )
        message = inert[0].getMessage()
        # The warning MUST name the OFF protection AND the exact wiring.
        assert "NO rate limiting will be applied" in message, message
        assert "request: Request" in message, message
        assert "probe" in message, message
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_engaged_rate_limit_does_not_warn(caplog):
    """A limit that CAN engage MUST stay silent -- no false alarm.

    Guards the over-broad fix (warning on every limited endpoint), which would
    train operators to ignore the warning.
    """
    from fastapi import Request

    app = Nexus(
        api_port=8247,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-engaged", methods=["GET"], rate_limit=5)
            async def probe(request: Request):
                return {"ok": True}

        inert = [r for r in caplog.records if "rate_limit_inert" in r.getMessage()]
        assert not inert, f"false alarm: {[r.getMessage() for r in inert]}"
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_unlimited_endpoint_does_not_warn(caplog):
    """An UNLIMITED endpoint MUST stay silent regardless of Request parameter.

    Nothing is being silently dropped when no limit was asked for, so warning
    there would be noise.
    """
    app = Nexus(
        api_port=8248,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
        rate_limit_config={"default_rate_limit": None},
    )

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-unlimited-quiet", methods=["GET"])
            async def probe():
                return {"ok": True}

        inert = [r for r in caplog.records if "rate_limit_inert" in r.getMessage()]
        assert not inert, f"false alarm on an unlimited endpoint: {inert}"
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_rate_limit_no_op_without_request_parameter():
    """Pins the PRE-EXISTING precondition that makes rate limiting engage.

    The wrapper rate-limits only when it can find a FastAPI ``Request`` in the
    handler's args/kwargs, so a handler declaring no ``Request`` parameter is
    never limited regardless of the configured limit. This is surprising and
    pre-existing (NOT introduced by the None fix); it is pinned here so the
    sibling test's ``request: Request`` parameter reads as load-bearing rather
    than incidental, and so that making rate limiting unconditional fails
    loudly here and forces both tests to be revisited together.
    """
    app = Nexus(
        api_port=8245,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    @app.endpoint("/probe-no-request", methods=["GET"], rate_limit=2)
    async def probe():
        return {"ok": True}

    try:
        client = _client(app)
        statuses = [client.get("/probe-no-request").status_code for _ in range(8)]
        assert statuses == [200] * 8, (
            "rate limiting engaged for a handler with no Request parameter; "
            f"the documented precondition changed: {statuses}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_non_int_rate_limit_config_raises_loudly_at_registration():
    """A misconfigured non-int limit MUST fail at registration, not per request.

    Before the fix a string limit produced the same per-request TypeError as
    None. Silently treating it as unlimited would be a silent fallback, so it
    raises where the operator can see it.
    """
    app = Nexus(
        api_port=8244,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
        rate_limit_config={"default_rate_limit": "fifty"},
    )

    try:
        with pytest.raises(ValueError, match="rate_limit must be an int or None"):

            @app.endpoint("/probe-bad-config", methods=["GET"])
            async def probe():
                return {"ok": True}

    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_rate_limit_enforced_when_request_param_is_not_named_request():
    """A ``Request`` parameter under ANY name MUST actually rate-limit.

    The registration predicate accepts a parameter by its ANNOTATION
    (``req: Request`` qualifies), but the request wrapper resolved the Request
    only via the literal key ``kwargs["request"]`` and then scanned ``args`` --
    which FastAPI leaves EMPTY, because it invokes the endpoint as
    ``dependant.call(**values)``. ``kwargs.values()`` was never scanned.

    So for the idiomatic ``async def costly(req: Request, ...)``:

    * predicate -> True  => no inert-limit WARN
    * runtime   -> Request never found => ``request`` stays None
      => no counting, no 429, UNBOUNDED

    while the registration log still advertises ``rate_limit=N/min``. The
    endpoint is unlimited, the log says limited, and the WARN that exists
    precisely to end that silence stays silent.

    Falsifying result: before the fix all 12 responses are 200.
    """
    from fastapi import Request

    app = Nexus(
        api_port=8249,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    # Deliberately NOT named `request` -- `req` is idiomatic and common.
    @app.endpoint("/probe-req-alias", methods=["GET"], rate_limit=5)
    async def probe(req: Request):
        return {"ok": True}

    try:
        client = _client(app)
        statuses = [client.get("/probe-req-alias").status_code for _ in range(12)]
        assert 429 in statuses, (
            "rate_limit=5 was never enforced for a handler whose Request "
            f"parameter is named `req` rather than `request`: {statuses}"
        )
        assert statuses[0] == 200, f"first request should succeed, got {statuses[0]}"
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_predicate_and_runtime_agree_no_warn_implies_enforcement(caplog):
    """The WARN's core invariant: silence MUST mean enforcement really happens.

    The registration predicate and the request wrapper are two independent
    tests for "is there a Request here". When they disagree, the WARN reports
    on a property the runtime does not implement -- accurate-looking silence
    over a broken feature. This pins them together for a non-conventional
    parameter name, which is exactly where they diverged.
    """
    from fastapi import Request

    app = Nexus(
        api_port=8250,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
    )

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-agreement", methods=["GET"], rate_limit=3)
            async def probe(req: Request):
                return {"ok": True}

        warned = [r for r in caplog.records if "rate_limit_inert" in r.getMessage()]
        client = _client(app)
        statuses = [client.get("/probe-agreement").status_code for _ in range(9)]
        enforced = 429 in statuses

        # The predicate stayed silent, so enforcement MUST be real.
        assert not warned, "predicate warned; this test covers the silent case"
        assert enforced, (
            "predicate did NOT warn (claiming rate limiting applies) but the "
            f"runtime never enforced it: {statuses}"
        )
    finally:
        if app._running:
            app.stop()
