# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: ``Nexus.endpoint(rate_limit=...)`` MUST mean what it documents.

Two independent defects, both at the same public kwarg.

**Value semantics.** ``endpoint()``'s docstring says ``None=unlimited``, but
``None`` was also the "argument not supplied" marker, so an explicit
``rate_limit=None`` fell through to the config default and got limited at
100/min -- a documented kwarg with zero effect on the body (zero-tolerance
Rule 3c). The surrounding value handling had three more holes, all measured on
130 sequential requests before the fix:

===============================  ==========================================
configured value                 observed behaviour BEFORE the fix
===============================  ==========================================
``rate_limit=None`` (kwarg)      limited at 100/min -- NOT unlimited
``True`` (config)                ``isinstance(True, int)`` -> limit of 1/min
``False`` (config)               unlimited (fail-OPEN)
``50.0`` (config)                ``ValueError`` at REGISTRATION
``-5`` (config)                  unlimited (fail-OPEN)
===============================  ==========================================

``True``/``False`` are the security-relevant pair: a config carrying a boolean
where an int was meant either throttles every caller to 1/min or removes the
limit entirely, and neither says anything. ``50.0`` is the availability-relevant
one -- config loaded from JSON/YAML/env routinely yields a float, and raising
there takes the application down at import time.

**Predicate/runtime agreement.** The registration-time "will rate limiting
actually engage" predicate compared the annotation's BARE NAME against
``"Request"``, while the request wrapper resolves by
``isinstance(arg, fastapi.Request)``. Any class named ``Request`` -- a Pydantic
BODY model, most commonly -- satisfied the name comparison, so the predicate
reported ENFORCED and stayed silent while the runtime never found a
``fastapi.Request`` and left the endpoint completely UNLIMITED. That is the
false-SILENCE direction, and it is the direction that matters: a false WARN is
noise, a false silence is an unguarded endpoint whose registration log still
advertises ``rate_limit=N/min``.
"""

import logging

import pytest
from fastapi import Request as FastAPIRequest
from fastapi.exceptions import FastAPIError
from fastapi.testclient import TestClient
from pydantic import BaseModel

from nexus import Nexus


def _client(app: Nexus) -> TestClient:
    """Build a TestClient, asserting the gateway actually initialised."""
    fastapi_app = app.fastapi_app
    assert fastapi_app is not None, (
        "Nexus.fastapi_app is None -- the enterprise gateway was not "
        "initialised, so the endpoint cannot be exercised."
    )
    return TestClient(fastapi_app)


def _nexus(port: int, **kwargs) -> Nexus:
    return Nexus(
        api_port=port,
        enable_durability=False,
        enable_auth=False,
        enable_monitoring=False,
        **kwargs,
    )


# --------------------------------------------------------------------------
# Value semantics
# --------------------------------------------------------------------------


@pytest.mark.regression
def test_explicit_none_rate_limit_is_unlimited_not_the_config_default():
    """``rate_limit=None`` MUST be unlimited, as the docstring says.

    Falsifying result: before the fix, ``None`` was indistinguishable from
    "not supplied", so the config default (100) applied and request 101
    returned 429.
    """
    app = _nexus(8261)

    @app.endpoint("/probe-explicit-none", methods=["GET"], rate_limit=None)
    async def probe(request: FastAPIRequest):
        return {"ok": True}

    try:
        client = _client(app)
        statuses = [client.get("/probe-explicit-none").status_code for _ in range(130)]
        assert set(statuses) == {200}, (
            "rate_limit=None is documented as unlimited but was limited: "
            f"first non-200 at request {statuses.index(next(s for s in statuses if s != 200)) + 1}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_omitted_rate_limit_still_falls_back_to_the_config_default():
    """Not supplying the kwarg MUST still inherit the configured default.

    Guards the over-broad fix: making ``None`` mean unlimited must not also
    make the OMITTED case unlimited, which would silently drop the limit on
    every endpoint that relies on ``default_rate_limit``.
    """
    app = _nexus(8262, rate_limit_config={"default_rate_limit": 5})

    @app.endpoint("/probe-omitted", methods=["GET"])
    async def probe(request: FastAPIRequest):
        return {"ok": True}

    try:
        client = _client(app)
        statuses = [client.get("/probe-omitted").status_code for _ in range(12)]
        assert (
            429 in statuses
        ), f"configured default of 5 was never enforced: {statuses}"
        assert statuses[0] == 200, f"first request should pass, got {statuses[0]}"
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_bool_true_rate_limit_is_rejected_not_read_as_one_per_minute():
    """``True`` MUST raise, not silently become a limit of 1/min.

    Falsifying result: before the fix ``isinstance(True, int)`` is True, so
    ``True`` registered as a limit of 1 request per minute -- 129 of 130
    requests returned 429 with no diagnostic anywhere.
    """
    app = _nexus(8263, rate_limit_config={"default_rate_limit": True})

    try:
        with pytest.raises(ValueError, match="rate_limit"):

            @app.endpoint("/probe-bool-true", methods=["GET"])
            async def probe(request: FastAPIRequest):
                return {"ok": True}

    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_bool_false_rate_limit_is_rejected_not_silently_unlimited():
    """``False`` MUST raise, not silently disable rate limiting.

    Falsifying result: before the fix ``False`` reached the ``> 0`` guard as
    0 and resolved to unlimited -- the fail-OPEN direction, from a value that
    was plainly a misconfiguration.
    """
    app = _nexus(8264, rate_limit_config={"default_rate_limit": False})

    try:
        with pytest.raises(ValueError, match="rate_limit"):

            @app.endpoint("/probe-bool-false", methods=["GET"])
            async def probe(request: FastAPIRequest):
                return {"ok": True}

    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_integral_float_rate_limit_is_accepted_and_enforced():
    """``50.0`` MUST register and enforce 50/min, not raise at import.

    Falsifying result: before the fix this raised ``ValueError: rate_limit
    must be an int or None ...; got float`` at REGISTRATION -- i.e. the
    application failed to start -- for a value that config loaded from
    JSON/YAML/env routinely produces.
    """
    app = _nexus(8265, rate_limit_config={"default_rate_limit": 50.0})

    @app.endpoint("/probe-float", methods=["GET"])
    async def probe(request: FastAPIRequest):
        return {"ok": True}

    try:
        client = _client(app)
        statuses = [client.get("/probe-float").status_code for _ in range(60)]
        assert statuses[:50] == [200] * 50, (
            "50.0 should behave exactly as 50; the first 50 requests were not "
            f"all served: {statuses[:50]}"
        )
        assert 429 in statuses[50:], (
            "50.0 registered but never enforced a limit of 50: " f"{statuses[50:]}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_non_integral_float_rate_limit_is_rejected():
    """A fractional limit has no meaning and MUST raise loudly.

    Guards the over-broad fix (coercing every float via ``int()``, which
    would silently turn 0.5 into 0 -- i.e. unlimited).
    """
    app = _nexus(8266, rate_limit_config={"default_rate_limit": 50.5})

    try:
        with pytest.raises(ValueError, match="rate_limit"):

            @app.endpoint("/probe-float-frac", methods=["GET"])
            async def probe(request: FastAPIRequest):
                return {"ok": True}

    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_negative_rate_limit_is_rejected_not_silently_unlimited():
    """A negative limit MUST raise, not fail OPEN.

    Falsifying result: before the fix ``-5`` failed the ``> 0`` guard and
    resolved to unlimited, so an operator who typed a minus sign got NO rate
    limiting and no diagnostic.
    """
    app = _nexus(8267, rate_limit_config={"default_rate_limit": -5})

    try:
        with pytest.raises(ValueError, match="rate_limit"):

            @app.endpoint("/probe-negative", methods=["GET"])
            async def probe(request: FastAPIRequest):
                return {"ok": True}

    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_zero_rate_limit_remains_unlimited_and_is_documented():
    """``0`` stays "unlimited" -- deliberate, pinned, and documented.

    ``0`` has meant unlimited since the original ``rate_limit > 0`` guard.
    The alternative reading (0 requests allowed => reject everything) would
    turn an existing ``0`` config into a total outage on upgrade, so the
    pre-existing meaning is kept and stated in the docstring instead. This
    test is what makes that a decision rather than an accident.
    """
    app = _nexus(8268, rate_limit_config={"default_rate_limit": 0})

    @app.endpoint("/probe-zero", methods=["GET"], rate_limit=0)
    async def probe(request: FastAPIRequest):
        return {"ok": True}

    try:
        client = _client(app)
        statuses = {client.get("/probe-zero").status_code for _ in range(130)}
        assert statuses == {200}, f"0 should mean unlimited; saw {sorted(statuses)}"
    finally:
        if app._running:
            app.stop()


# --------------------------------------------------------------------------
# Predicate / runtime agreement -- the FALSE-SILENCE direction
# --------------------------------------------------------------------------


class Request(BaseModel):
    """A Pydantic BODY model that happens to be named ``Request``.

    Module scope on purpose: the annotation must resolve to THIS class, which
    is exactly the collision the bare-name predicate could not see.
    """

    value: str = "x"


@pytest.mark.regression
def test_body_model_named_request_does_not_silence_the_inert_warn(caplog):
    """A non-FastAPI class named ``Request`` MUST NOT buy silence.

    The predicate compared the annotation's bare NAME while the runtime
    resolves by ``isinstance(arg, fastapi.Request)``. A Pydantic body model
    named ``Request`` satisfied the name comparison, so the predicate reported
    ENFORCED, the WARN stayed silent, and the endpoint was UNLIMITED.

    The annotation is QUOTED deliberately, because that is the only shape in
    which the defect is reachable -- and it is not an exotic one. A live class
    object never matched the bare-name comparison, but ``from __future__
    import annotations`` turns EVERY annotation in a module into exactly this
    string, so any PEP-563 module declaring a body model named ``Request``
    lands here.

    Both halves are asserted together, because it is their DISAGREEMENT that
    is the defect: the runtime really is unlimited here, so the warning is
    the only thing standing between the operator and an unguarded endpoint.

    Falsifying result: before the fix no ``rate_limit_inert`` record is
    emitted at all, while all 8 requests return 200.
    """
    app = _nexus(8269)

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-body-model", methods=["POST"], rate_limit=2)
            async def probe(payload: "Request"):
                return {"ok": True}

        inert = [r for r in caplog.records if "rate_limit_inert" in r.getMessage()]

        client = _client(app)
        statuses = [
            client.post("/probe-body-model", json={"value": "x"}).status_code
            for _ in range(8)
        ]
        assert statuses == [200] * 8, (
            "precondition changed: the runtime now limits a handler with no "
            f"fastapi.Request parameter, so this test needs revisiting: {statuses}"
        )
        assert inert, (
            "the endpoint is UNLIMITED (8/8 served with rate_limit=2) yet the "
            "registration predicate stayed silent; messages were: "
            f"{[r.getMessage() for r in caplog.records]}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_fastapi_request_subclass_still_silences_the_warn(caplog):
    """A SUBCLASS of ``fastapi.Request`` MUST stay silent AND enforce.

    Guards the over-narrow fix (identity comparison only). FastAPI injects the
    request for any ``Request`` subclass annotation, so the runtime does find
    one and limiting genuinely engages -- warning here would be a false alarm.
    """

    class MyRequest(FastAPIRequest):
        pass

    app = _nexus(8270)

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-subclass", methods=["GET"], rate_limit=3)
            async def probe(request: MyRequest):
                return {"ok": True}

        inert = [r for r in caplog.records if "rate_limit_inert" in r.getMessage()]
        assert not inert, f"false alarm on a Request subclass: {inert}"

        statuses = [_client(app).get("/probe-subclass").status_code for _ in range(9)]
        assert 429 in statuses, (
            "the predicate stayed silent (claiming rate limiting applies) but "
            f"the runtime never enforced it: {statuses}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_string_annotation_of_real_request_still_silences_the_warn(caplog):
    """A QUOTED ``"Request"`` annotation resolving to the real class stays silent.

    This is the shape ``from __future__ import annotations`` produces for
    every annotation in a module. Registration and enforcement both work
    today (verified), so the predicate MUST resolve the string rather than
    give up on it -- otherwise the fix trades a false silence for a false
    alarm on every PEP-563 module.
    """
    app = _nexus(8271)

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-quoted", methods=["GET"], rate_limit=3)
            async def probe(request: "FastAPIRequest"):
                return {"ok": True}

        inert = [r for r in caplog.records if "rate_limit_inert" in r.getMessage()]
        assert not inert, f"false alarm on a quoted fastapi.Request annotation: {inert}"

        statuses = [_client(app).get("/probe-quoted").status_code for _ in range(9)]
        assert 429 in statuses, (
            "the predicate stayed silent but the runtime never enforced: " f"{statuses}"
        )
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_unresolvable_annotation_reports_unverifiable_not_a_false_verdict(caplog):
    """A handler whose annotations do not resolve MUST NOT get a false verdict.

    "Cannot prove the parameter is absent" is not "the parameter is absent",
    so the inert-limit WARN -- which asserts flatly that NO rate limiting will
    be applied -- must not fire on a question that was never answered.

    Silence is not the alternative either: a security control whose
    verification did not run must not look identical to one that passed
    (security.md fail-closed; instrument-discipline MUST-1). So the resolution
    failure is reported on its own, as what it is.
    """
    app = _nexus(8272)

    try:
        with caplog.at_level(logging.WARNING, logger="nexus.core"):

            @app.endpoint("/probe-unresolvable", methods=["GET"], rate_limit=3)
            async def probe(request: "NoSuchTypeAnywhere"):  # noqa: F821
                return {"ok": True}

        messages = [r.getMessage() for r in caplog.records]
        assert not [m for m in messages if "rate_limit_inert" in m], (
            "asserted that NO rate limiting applies, for an annotation it "
            f"could not resolve; absence was never proven: {messages}"
        )
        unverifiable = [m for m in messages if "rate_limit_unverifiable" in m]
        assert unverifiable, (
            "verification could not run and nothing was reported, so an "
            f"unverified endpoint reads exactly like a verified one: {messages}"
        )
        assert "NoSuchTypeAnywhere" in unverifiable[0], unverifiable[0]
    finally:
        if app._running:
            app.stop()


@pytest.mark.regression
def test_fastapi_rejects_a_union_request_annotation_at_registration():
    """A union-wrapped ``Request`` cannot reach the inert-WARN predicate.

    This pins a REFUTATION, and it is here so the same non-bug is not "fixed"
    again. An audit proposed unwrapping unions in the predicate, reasoning that
    ``Request | None`` resolves to a ``types.UnionType`` -- not a ``type`` --
    so the type-only test would false-negative and emit a bogus
    ``rate_limit_inert`` WARN for an endpoint that really does enforce.

    The premise is false. FastAPI special-cases a BARE ``Request`` for
    injection; wrapped in a union it is treated as a request-body field
    instead, and schema generation fails at REGISTRATION -- before the
    predicate runs. So the handler the warning would have been wrong about
    cannot be created at all, and the type-only test is sufficient.

    Falsifying result: were FastAPI to start accepting the union form, this
    test stops raising and FAILS, which is the signal that the predicate now
    genuinely needs to unwrap unions. That is the condition under which the
    proposed fix becomes correct.
    """
    app = _nexus(8276)

    try:
        with pytest.raises(FastAPIError, match="valid Pydantic field type"):

            @app.endpoint("/probe-union", methods=["GET"], rate_limit=3)
            async def probe(request: FastAPIRequest | None = None):
                return {"ok": True}

    finally:
        if app._running:
            app.stop()
