# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #2114 -- non-ASCII ``X-API-Key`` traceback flood.

``secrets.compare_digest`` raises ``TypeError`` when either ``str`` argument
contains a character outside ASCII::

    TypeError: comparing strings with non-ASCII characters is not supported

Starlette decodes request headers as **latin-1**, so any header byte ``>= 0x80``
reaches Python as a non-ASCII ``str`` and lands in
``server_auth._make_api_key_validator._validate``. The raise was caught -- the
request was correctly refused with 401 -- but it was caught by
``logger.exception``, writing a **full traceback per request** on a path that is
unauthenticated, attacker-drivable with one header byte, and unbounded.

What is RED before the fix
--------------------------
The 401 is NOT the measurement: the pre-fix tree already returns 401. The
measurement is the **traceback**, and
:func:`test_non_ascii_api_key_emits_no_traceback` is the load-bearing test --
pre-fix it observes a ``TypeError`` record carrying ``exc_info``.
:func:`test_non_ascii_configured_key_is_rejected_at_construction` is the second
RED: a non-ASCII CONFIGURED key made *every* comparison raise, so no key at all
could authenticate while each request logged a traceback.

Discrimination controls
-----------------------
:func:`test_valid_ascii_key_still_authenticates` hits the same route with a
valid key and gets 200. Without it, the 401 in the load-bearing tests could
equally be a broken route or a mis-installed middleware. And
:func:`test_ascii_rejection_path_emits_no_traceback` establishes that an
ordinary wrong key never produced a traceback either, so the traceback observed
for the non-ASCII key is attributable to the non-ASCII byte and nothing else.

No ``Mock`` appears in this file. A mock validator accepts every call and would
pass identically whether the guard is installed or not.
"""

import logging

import pytest
from fastapi.testclient import TestClient

from kailash.servers import WorkflowServer
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression

_ASCII_KEY = "issue-2114-ascii-api-key-value"

#: U+00E9. Sent on the wire as the single latin-1 byte 0xE9 -- Starlette decodes
#: request headers as latin-1, so this is exactly the ``str`` the validator sees.
#: One byte >= 0x80 is all it takes.
_NON_ASCII_KEY = "issue-2114-non-ascii-kéy"

#: httpx refuses to encode a non-ASCII ``str`` header value
#: (``UnicodeEncodeError: 'ascii' codec can't encode character '\xe9'``), so the
#: header is handed over as RAW BYTES -- which is what a client sends anyway.
#: The server-side ``str`` is then byte-identical to :data:`_NON_ASCII_KEY`.
_NON_ASCII_KEY_WIRE = _NON_ASCII_KEY.encode("latin-1")

_AUTH_ENV_NAMES = (
    "KAILASH_JWT_SECRET",
    "KAILASH_JWT_PUBLIC_KEY",
    "KAILASH_JWT_ALGORITHM",
    "KAILASH_AUTH_EXEMPT_PATHS",
)


@pytest.fixture(autouse=True)
def reset_failure_memo():
    """Clear the bounded-traceback memo around every test.

    ``_log_bounded_failure`` allows exactly ONE traceback per
    ``(event, exception type)`` per process. Without this reset a "no traceback"
    assertion would go green for the wrong reason as soon as any earlier test in
    the same process had already spent that one traceback -- the assertion would
    stop discriminating between a fixed validator and an unfixed one.

    The symbol is resolved defensively ON PURPOSE. It does not exist before the
    fix, and an autouse fixture that raised on it would turn every test in this
    file into a setup ERROR against the pre-fix tree -- destroying the
    behavioural RED (a traceback per request) these tests exist to measure and
    replacing it with an import failure, which proves nothing. Absent the
    symbol there is no memo to reset, so skipping the reset is exactly right.
    """
    try:
        from kailash.trust.auth.asgi import _reset_bounded_failures
    except ImportError:
        reset = None
    else:
        reset = _reset_bounded_failures

    if reset:
        reset()
    yield
    if reset:
        reset()


@pytest.fixture
def clean_auth_env(monkeypatch):
    """Remove every auth variable so a test's environment is what it sets.

    ``KAILASH_API_KEY_*`` is a prefix match, so the whole environment is swept:
    a stray key inherited from the developer's shell would otherwise satisfy
    the gate and turn a fail-closed assertion green for the wrong reason.
    """
    import os

    for name in _AUTH_ENV_NAMES:
        monkeypatch.delenv(name, raising=False)
    for name in [n for n in os.environ if n.startswith("KAILASH_API_KEY_")]:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


@pytest.fixture
def api_key_env(clean_auth_env):
    """An API-key-only deployment with one ASCII key configured."""
    clean_auth_env.setenv("KAILASH_API_KEY_SERVICE", _ASCII_KEY)
    return clean_auth_env


def _probe_workflow():
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "n", {"code": "result = {'ran': True}"})
    return wb.build()


def _server():
    server = WorkflowServer(title="issue-2114")
    server.register_workflow("probe", _probe_workflow())
    return server


def _client():
    """A client over the server's real ASGI app, with the auth stack installed."""
    return TestClient(_server().app)


def _tracebacks(caplog):
    """Records that carry an exception -- i.e. that render a stack trace.

    Reads ``record.exc_info`` rather than grepping the formatted text: the
    traceback is what ``logger.exception`` attaches, and a message that merely
    contains the word "Traceback" is not the same thing.
    """
    return [r for r in caplog.records if r.exc_info is not None]


def test_non_ascii_api_key_emits_no_traceback(api_key_env, caplog):
    """LOAD-BEARING. One header byte >= 0x80 must not cost a stack trace.

    Pre-fix this observes a ``TypeError: comparing strings with non-ASCII
    characters is not supported`` record with ``exc_info`` attached, emitted
    from ``jwt_auth_middleware.api_key_validator_failed``.
    """
    client = _client()
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"X-API-Key": _NON_ASCII_KEY_WIRE},
        )

    assert response.status_code == 401, response.text
    assert _tracebacks(caplog) == [], (
        "a non-ASCII X-API-Key wrote a traceback: "
        f"{[(r.name, r.getMessage()) for r in _tracebacks(caplog)]}"
    )


def test_non_ascii_api_key_is_repeatable_without_log_growth(api_key_env, caplog):
    """The flood is the defect: N attempts must not cost N stack traces."""
    client = _client()
    with caplog.at_level(logging.DEBUG):
        for _ in range(5):
            response = client.post(
                "/workflows/probe/execute",
                json={"inputs": {}},
                headers={"X-API-Key": _NON_ASCII_KEY_WIRE},
            )
            assert response.status_code == 401, response.text

    assert _tracebacks(caplog) == []


def test_ascii_rejection_path_emits_no_traceback(api_key_env, caplog):
    """CONTROL. An ordinary wrong key never wrote a traceback.

    This is what makes the load-bearing assertion attributable: the difference
    between this test and the one above is exactly one non-ASCII byte.
    """
    client = _client()
    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/workflows/probe/execute",
            json={"inputs": {}},
            headers={"X-API-Key": "issue-2114-wrong-but-ascii"},
        )

    assert response.status_code == 401, response.text
    assert _tracebacks(caplog) == []


def test_valid_ascii_key_still_authenticates(api_key_env):
    """CONTROL. Without this, the 401s above could be a broken route."""
    client = _client()
    response = client.post(
        "/workflows/probe/execute",
        json={"inputs": {}},
        headers={"X-API-Key": _ASCII_KEY},
    )
    assert response.status_code == 200, response.text


def test_non_ascii_key_does_not_authenticate(api_key_env):
    """The guard must fail CLOSED -- rejecting, never accepting."""
    client = _client()
    response = client.post(
        "/workflows/probe/execute",
        json={"inputs": {}},
        headers={"X-API-Key": _NON_ASCII_KEY_WIRE},
    )
    assert response.status_code == 401, response.text


def test_websocket_surface_rejects_non_ascii_key(api_key_env, caplog):
    """Enforcement-surface parity: the websocket handshake shares the validator.

    ``JWTWebSocketAuthMiddleware._api_key_ok`` wraps the same
    ``config.api_key_validator`` in its own ``logger.exception``, so a fix
    applied only to the HTTP dispatcher would leave this surface flooding.
    """
    from starlette.websockets import WebSocketDisconnect

    server = _server()

    @server.app.websocket("/ws")
    async def _ws(websocket):  # pragma: no cover -- must never be reached
        await websocket.accept()
        await websocket.send_text("reached")

    client = TestClient(server.app)
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws", headers={"X-API-Key": _NON_ASCII_KEY_WIRE}
            ) as ws:
                ws.receive_text()

    assert _tracebacks(caplog) == []


def test_non_ascii_configured_key_is_rejected_at_construction(clean_auth_env):
    """LOAD-BEARING. A non-ASCII CONFIGURED key is a dead deployment.

    Pre-fix, ``compare_digest`` raised on EVERY comparison -- including the
    operator's own correct key -- so the API-key path authenticated nobody
    while writing a traceback per request. Refusing to construct surfaces that
    at deploy time, which is the disposition this module already takes for an
    under-length ``KAILASH_JWT_SECRET``.
    """
    from kailash.utils.server_auth import (
        InvalidServerAuthSecretError,
        build_server_auth_config,
    )

    clean_auth_env.setenv("KAILASH_API_KEY_SERVICE", _NON_ASCII_KEY)

    with pytest.raises(InvalidServerAuthSecretError) as excinfo:
        build_server_auth_config()

    message = str(excinfo.value)
    # The operator needs the variable NAME to fix it -- and must never get the
    # value, which is the credential itself.
    assert "KAILASH_API_KEY_SERVICE" in message
    assert _NON_ASCII_KEY not in message


def test_caller_supplied_raising_validator_is_bounded(clean_auth_env, caplog):
    """A caller-supplied validator cannot be turned into a traceback amplifier.

    ``JWTConfig.api_key_validator`` is public configuration, so fixing only the
    shipped validator would leave every custom one exposed to the same #2114
    amplification. The FIRST failure keeps its full traceback -- the operator
    still learns what broke -- and the rest are bounded records.
    """
    from kailash.trust.auth.jwt import JWTConfig

    def _always_raises(api_key):
        raise RuntimeError("validator backend is down")

    server = WorkflowServer(
        title="issue-2114-custom",
        auth_config=JWTConfig(
            secret="issue-2114-regression-secret-key-at-least-32b",
            api_key_enabled=True,
            api_key_validator=_always_raises,
            exempt_paths=[],
        ),
    )
    server.register_workflow("probe", _probe_workflow())
    client = TestClient(server.app)

    with caplog.at_level(logging.DEBUG):
        for _ in range(6):
            response = client.post(
                "/workflows/probe/execute",
                json={"inputs": {}},
                headers={"X-API-Key": "any-ascii-key"},
            )
            assert response.status_code == 401, response.text

    traces = _tracebacks(caplog)
    assert len(traces) == 1, (
        "6 identical validator failures must cost exactly one traceback, got "
        f"{len(traces)}"
    )
    # The repeats are recorded, not swallowed: silence would hide a broken
    # validator entirely, which is the opposite defect.
    repeats = [
        r
        for r in caplog.records
        if r.getMessage() == "jwt_auth_middleware.api_key_validator_failed"
        and r.exc_info is None
    ]
    assert len(repeats) == 5
    assert getattr(repeats[-1], "occurrences", None) == 6
    assert getattr(repeats[-1], "error_type", None) == "RuntimeError"


def test_validator_rejects_non_str_without_raising(api_key_env):
    """A non-``str`` credential fails closed rather than raising ``TypeError``.

    ``compare_digest`` raises for a non-buffer argument too, which is the same
    log-flood shape reached through any caller that does not go through
    Starlette's header decoding.
    """
    from kailash.utils.server_auth import _make_api_key_validator

    validate = _make_api_key_validator({"KAILASH_API_KEY_SERVICE": _ASCII_KEY})

    assert validate(_ASCII_KEY) is True
    assert validate(None) is False
    assert validate(b"bytes-are-not-the-contract") is False
    assert validate(123) is False
