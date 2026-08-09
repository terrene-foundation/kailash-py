# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Dependency-injection callables must not have their ``repr`` logged.

The resolver names WHICH handler / dependency failed, via
``getattr(x, "__qualname__", repr(x))``. The ``getattr`` default is evaluated
eagerly but only USED when the attribute is absent -- and on a DI surface the
objects that lack ``__qualname__`` are precisely the ones that carry payloads.
``functools.partial(get_db, dsn="postgres://svc:<credential>@host/db")`` is the
IDIOMATIC way to pre-bind a connection string to a dependency, and it has
neither ``__name__`` nor ``__qualname__``.

Every case here is driven through the REAL Nexus HTTP gateway via Starlette's
``TestClient`` -- the full ASGI stack (request-capture middleware -> workflow
route -> HandlerNode -> resolver chain) executes end to end, and the assertions
read the REAL ``nexus.extractors.resolver`` logger. NO MOCKING: a mocked logger
would prove nothing about the sink that actually runs in production.

``_log_resolver_failure`` additionally passed ``exc_info=exc``. Two independent
payloads reach the record that way, both proven below:

1. The dependency's OWN exception -- a driver error naming the DSN it could not
   reach.
2. ``get_type_hints`` REFUSES a ``functools.partial`` with
   ``TypeError: functools.partial(<function get_db>, dsn='...') is not a
   module, class, method, or function`` -- the refusal message embeds the full
   repr. The resolver wraps that in ``ExtractorPEP563Error(...) from exc``, so
   the chained cause carries the credential even though the wrapper's own
   message does not.

Every credential is a synthetic sentinel: structurally credential-shaped,
self-describing, unusable. Hosts are RFC 2606 ``.invalid``.
"""

import asyncio
import functools
import logging
import socket
import traceback
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from nexus import Nexus
from nexus.extractors import Depends

_SENTINEL = "SYNTHETIC-NOT-A-REAL-CREDENTIAL-f11"
_LEAKY_DSN = f"postgres://svc:{_SENTINEL}@db.example.invalid:5432/app"

_RESOLVER_LOGGER = "nexus.extractors.resolver"
_CORE_LOGGER = "nexus.core"


def _render_record(record) -> str:
    """Everything a log sink could emit for one record.

    Deliberately NOT ``record.getMessage()``. The resolver puts its identity
    fields in ``extra=``, which never appears in the message but IS serialised
    by any structured sink (python-json-logger, structlog). Asserting on the
    message alone passes against every leak in this file, which is how they
    survived the original sweep.
    """
    parts = [record.getMessage()]
    for key, value in record.__dict__.items():
        if key not in ("args", "msg", "exc_info", "exc_text"):
            parts.append(f"{key}={value!r}")
    if record.exc_info:
        parts.append("".join(traceback.format_exception(*record.exc_info)))
    return "\n".join(parts)


def rendered(caplog, *loggers: str) -> str:
    """Render the records emitted by ``loggers`` (default: the ones under test).

    Scoped BY LOGGER on purpose. A resolver failure propagates out as
    ``NexusHandlerError(...) from exc``, and one sink further down the stack --
    ``HandlerNode.execute_async`` in ``kailash/nodes/base_async.py`` -- logs
    that chain with ``exc_info``, which re-renders the original cause's message
    verbatim. That is the SAME leak class as the sinks under test but a
    DIFFERENT site, in the core SDK's generic node-execution path rather than
    in Nexus, and it is pinned separately by
    ``TestKnownDownstreamReleak`` below so that scoping here cannot quietly
    bury it.
    """
    names = loggers or (_RESOLVER_LOGGER, _CORE_LOGGER)
    return "\n".join(
        _render_record(record) for record in caplog.records if record.name in names
    )


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _client_for(app: Nexus) -> TestClient:
    """Register handler routes on the live gateway and return a TestClient."""
    asyncio.run(app._http_transport.start(app._registry))
    assert app.fastapi_app is not None
    return TestClient(app.fastapi_app, raise_server_exceptions=False)


def _app() -> Nexus:
    return Nexus(api_port=_free_port(), auto_discovery=False, enable_auth=False)


def _get_db(dsn: str, tenant: str) -> str:
    """A dependency whose connection string is pre-bound by the caller."""
    return "connection"


@dataclass(frozen=True)
class _ConfiguredDep:
    """A callable-object dependency holding its own config.

    ``frozen=True`` makes it hashable, which it must be to survive the
    resolver's per-invocation memoisation cache (a plain ``@dataclass`` is
    unhashable and fails earlier, on the cache lookup).
    """

    endpoint: str
    api_key: str

    def __call__(self, tenant: str) -> str:
        return "connection"


@pytest.fixture
def resolver_logs(caplog):
    caplog.set_level(logging.DEBUG, logger=_RESOLVER_LOGGER)
    return caplog


@pytest.mark.integration
class TestDependencyIdentityFallback:
    """``_log_resolver_failure`` -- the ``dependency`` field."""

    def test_partial_dependency_bound_kwargs_do_not_reach_the_log(self, resolver_logs):
        """``Depends(functools.partial(get_db, dsn=...))`` -- the idiomatic shape."""
        app = _app()
        dependency = functools.partial(_get_db, dsn=_LEAKY_DSN)
        assert not hasattr(dependency, "__qualname__"), (
            "precondition: a functools.partial has no __qualname__, which is "
            "what sends it down the fallback path under test"
        )

        async def handler(db: str = Depends(dependency)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        assert response.status_code == 500, response.text
        blob = rendered(resolver_logs)
        # Anti-vacuity: without this the absence assertions hold trivially for
        # a resolver that logged nothing at all.
        assert "resolver.dependency_failed" in blob, blob
        assert _SENTINEL not in blob, blob
        # The diagnostic survives AND still resolves to the wrapped function.
        assert "_get_db" in blob, blob

    def test_callable_object_dependency_fields_do_not_reach_the_log(
        self, resolver_logs
    ):
        """An unhashable callable object fails on the memoisation lookup.

        The failure still routes through ``_log_resolver_failure``, so the
        dependency's ``repr`` -- every field, credential included -- reached
        the record.
        """
        app = _app()

        @dataclass
        class _UnhashableDep:
            endpoint: str
            api_key: str

            def __call__(self, tenant: str) -> str:
                return "connection"

        dependency = _UnhashableDep(
            endpoint="https://db.example.invalid", api_key=_SENTINEL
        )

        async def handler(db: str = Depends(dependency)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        assert response.status_code == 500, response.text
        blob = rendered(resolver_logs)
        assert "resolver.dependency_failed" in blob, blob
        assert _SENTINEL not in blob, blob
        assert "_UnhashableDep" in blob, blob


@pytest.mark.integration
class TestUnsatisfiableFlatParamFallback:
    """``_resolve_callable_kwargs`` -- the ``callable`` field."""

    def test_callable_object_fields_do_not_reach_the_unsatisfiable_log(
        self, resolver_logs
    ):
        """A hashable callable-object dependency with a required flat param.

        It survives the memoisation cache, is introspected, and its required
        ``tenant`` parameter has no source -- which is the branch that logs
        ``resolver.dependency_flat_param_unsatisfiable``.
        """
        app = _app()
        dependency = _ConfiguredDep(
            endpoint="https://db.example.invalid", api_key=_SENTINEL
        )

        async def handler(db: str = Depends(dependency)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        assert response.status_code == 500, response.text
        blob = rendered(resolver_logs)
        assert "resolver.dependency_flat_param_unsatisfiable" in blob, blob
        assert _SENTINEL not in blob, blob
        assert "_ConfiguredDep" in blob, blob
        # The param name is the other half of the diagnostic.
        assert "tenant" in blob, blob


@pytest.mark.integration
class TestHandlerIdentityFallback:
    """``_log_resolver_failure`` -- the ``handler`` field."""

    def test_callable_object_handler_fields_do_not_reach_the_log(self, resolver_logs):
        """The HANDLER itself is a configured callable object."""
        app = _app()

        def _explodes() -> str:
            raise RuntimeError("dependency backend unreachable")

        @dataclass(frozen=True)
        class _ConfiguredHandler:
            endpoint: str
            api_key: str

            async def __call__(self, db: str = Depends(_explodes)) -> dict:
                return {"db": db}

        handler = _ConfiguredHandler(
            endpoint="https://api.example.invalid", api_key=_SENTINEL
        )
        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        assert response.status_code == 500, response.text
        blob = rendered(resolver_logs)
        assert "resolver.dependency_failed" in blob, blob
        assert _SENTINEL not in blob, blob
        assert "_ConfiguredHandler" in blob, blob


@pytest.mark.integration
class TestResolverExcInfoReleak:
    """The traceback vector, isolated from the identity vector.

    Both cases use a dependency with a perfectly safe ``__qualname__``, so a
    failure here can only come from ``exc_info``.
    """

    def test_dependency_exception_message_does_not_reach_the_log(self, resolver_logs):
        """Vector 1: the dependency's own exception names its DSN."""
        app = _app()

        def get_db() -> str:
            raise RuntimeError(f"could not connect to {_LEAKY_DSN}")

        async def handler(db: str = Depends(get_db)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        assert response.status_code == 500, response.text
        blob = rendered(resolver_logs)
        assert "resolver.dependency_failed" in blob, blob
        assert _SENTINEL not in blob, blob
        # The exception TYPE is retained -- a class name, never content.
        assert "RuntimeError" in blob, blob

    def test_get_type_hints_refusal_message_does_not_reach_the_log(self, resolver_logs):
        """Vector 2: the introspection refusal embeds the partial's repr.

        ``get_type_hints`` rejects a ``functools.partial`` with a TypeError
        whose message contains the full repr. The resolver chains it with
        ``raise ExtractorPEP563Error(...) from exc``, so the credential rode
        the ``__cause__`` into the record independently of the identity field.
        """
        app = _app()
        dependency = functools.partial(_get_db, dsn=_LEAKY_DSN)

        async def handler(db: str = Depends(dependency)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        assert response.status_code == 500, response.text
        blob = rendered(resolver_logs)
        assert "resolver.dependency_failed" in blob, blob
        assert _SENTINEL not in blob, blob
        assert "ExtractorPEP563Error" in blob, blob


@pytest.mark.integration
class TestRateLimitUnverifiableWarn:
    """``Nexus.endpoint`` -- the registration-time rate-limit WARN.

    Both leaks live in ONE ``logger.warning`` call: the handler-identity
    fallback, and the interpolated ``exc`` whose ``get_type_hints`` refusal
    message embeds the same repr. Fixing either alone still ships the payload.
    """

    def test_partial_handler_does_not_reach_the_rate_limit_warn(self, caplog):
        caplog.set_level(logging.WARNING, logger=_CORE_LOGGER)
        app = _app()

        async def dashboard(request, dsn: str) -> dict:
            return {"ok": True}

        handler = functools.partial(dashboard, dsn=_LEAKY_DSN)
        app.endpoint("/dashboard", methods=["GET"], rate_limit=50)(handler)

        blob = rendered(caplog)
        assert "rate_limit_unverifiable" in blob, blob
        assert _SENTINEL not in blob, blob
        # The operator still learns WHICH handler could not be verified.
        assert "dashboard" in blob, blob


@pytest.mark.integration
class TestKnownDownstreamReleak:
    """Containment pin for a leak site OUTSIDE the resolver.

    A resolver dependency failure leaves the resolver as
    ``NexusHandlerError(...) from exc``. One sink further down the stack --
    ``HandlerNode.execute_async``, ``kailash/nodes/base_async.py`` -- logs that
    chain with ``exc_info``, and ``logging`` renders a chained exception by
    printing each ``str()``. So the credential the resolver no longer emits
    still reaches the log from the generic node-execution path.

    That site is the SAME class as the ones fixed here but a DIFFERENT file, in
    the core SDK rather than in Nexus. This test does not assert it is fixed;
    it asserts the leak is CONFINED to exactly that one known logger, so:

    * a NEW leaking sink makes this fail (the set grows), and
    * fixing ``base_async`` ALSO makes this fail (the set empties), forcing
      whoever fixes it to delete this pin rather than leave a stale claim.

    Either way the finding cannot be silently lost, which scoping ``rendered``
    by logger name would otherwise risk.
    """

    _KNOWN_LEAKING_LOGGERS = {"HandlerNode"}

    def test_releak_is_confined_to_the_known_downstream_sink(self, caplog):
        caplog.set_level(logging.DEBUG)
        app = _app()
        dependency = functools.partial(_get_db, dsn=_LEAKY_DSN)

        async def handler(db: str = Depends(dependency)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})
        assert response.status_code == 500, response.text

        leaking = {
            record.name
            for record in caplog.records
            if _SENTINEL in _render_record(record)
        }
        assert leaking == self._KNOWN_LEAKING_LOGGERS, (
            "the set of log sinks leaking a caller-supplied credential changed; "
            f"expected {sorted(self._KNOWN_LEAKING_LOGGERS)}, got {sorted(leaking)}"
        )

    def test_the_client_response_never_carries_the_credential(self, caplog):
        """The split-visibility contract to the CLIENT holds regardless.

        The downstream re-leak above is server-log-only. The 500 envelope
        carries the canonical shape plus a correlation id and nothing else --
        which is the half of spec §138 that faces an untrusted party.
        """
        caplog.set_level(logging.DEBUG)
        app = _app()
        dependency = functools.partial(_get_db, dsn=_LEAKY_DSN)

        async def handler(db: str = Depends(dependency)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        response = _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        assert response.status_code == 500
        assert _SENTINEL not in response.text, response.text
