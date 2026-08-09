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

    Scoped BY LOGGER so a failure names the sink under test rather than any
    sink in the stack. That scoping cannot hide a leak elsewhere:
    ``TestNoSinkAnywhereLeaksTheCredential`` below captures at ROOT with no
    filter and asserts the leaking-logger set is empty, so a sink outside these
    two modules -- including one added far from this package -- still fails.
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
class TestRateLimitInertWarn:
    """``Nexus.endpoint`` -- the OTHER rate-limit WARN.

    Distinct from the unverifiable one: this fires when the annotations DO
    resolve but declare no ``Request``, so it is reached by a configured
    callable object (whose ``get_type_hints`` returns its FIELD annotations)
    rather than by a partial.
    """

    def test_callable_object_handler_does_not_reach_the_inert_warn(self, caplog):
        caplog.set_level(logging.WARNING, logger=_CORE_LOGGER)
        app = _app()

        @dataclass(frozen=True)
        class _ConfiguredEndpoint:
            endpoint: str
            api_key: str

            async def __call__(self, item_id: str) -> dict:
                return {"ok": True}

        handler = _ConfiguredEndpoint(
            endpoint="https://api.example.invalid", api_key=_SENTINEL
        )
        app.endpoint("/inert", methods=["GET"], rate_limit=7)(handler)

        blob = rendered(caplog)
        assert "rate_limit_inert" in blob, blob
        assert _SENTINEL not in blob, blob
        # The operator still learns WHICH handler is unprotected.
        assert "_ConfiguredEndpoint" in blob, blob


@pytest.mark.integration
class TestUseMiddlewareRejection:
    """``Nexus.use_middleware`` -- the sync-function rejection message.

    Not a log sink: the name is interpolated into a ``TypeError`` the caller
    sees, and which rides into whatever logs the registration failure. It is
    interpolated TWICE, so a repr was emitted twice.
    """

    def test_partial_middleware_does_not_reach_the_rejection_message(self):
        app = _app()

        def sync_middleware(request, call_next, *, dsn: str):
            return None

        handler = functools.partial(sync_middleware, dsn=_LEAKY_DSN)

        with pytest.raises(TypeError) as excinfo:
            app.use_middleware(handler)

        message = str(excinfo.value)
        assert _SENTINEL not in message, message
        # The actionable diagnostic survives: WHICH function, and the fix.
        assert "sync_middleware" in message, message
        assert "async def" in message, message


@pytest.mark.integration
class TestNoSinkAnywhereLeaksTheCredential:
    """WHOLE-STACK assertion: not one log sink renders the credential.

    This replaces a containment pin that allowed exactly one logger --
    ``HandlerNode`` (``kailash/nodes/base_async.py``), which logged the
    propagated ``NexusHandlerError(...) from exc`` chain with ``exc_info``, so
    ``logging`` printed each chained ``str()`` and re-emitted the credential
    the resolver had just kept out of its own record. It was the last sink
    still leaking after the resolver was fixed.

    The pin did its job: closing that site made it FAIL rather than silently
    pass, which is the whole reason it asserted set EQUALITY instead of
    membership. It is now tightened to the empty set rather than widened, so
    it keeps working as a tripwire for any NEW sink -- including one added far
    from this package, since it captures at root with no logger filter.
    """

    def test_no_logger_in_the_whole_stack_renders_the_credential(self, caplog):
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
        assert leaking == set(), (
            "a log sink rendered a caller-supplied credential: " f"{sorted(leaking)}"
        )
        # Anti-vacuity: the request must actually have reached the failing
        # path, or every assertion above holds for a run that logged nothing.
        assert any(
            "resolver.dependency_failed" in record.getMessage()
            for record in caplog.records
        ), "the resolver failure path never fired; the assertion above is vacuous"

    def test_the_diagnostic_survives_at_the_node_execution_sink(self, caplog):
        """The node sink must still say WHICH node failed and WHERE.

        Dropping ``exc_info`` closes the leak; dropping the diagnostic with it
        would be trading one defect for another. The frames are the substitute,
        so this pins that they are actually emitted.
        """
        caplog.set_level(logging.DEBUG)
        app = _app()
        dependency = functools.partial(_get_db, dsn=_LEAKY_DSN)

        async def handler(db: str = Depends(dependency)) -> dict:
            return {"db": db}

        app.handler_extract("me", handler)
        _client_for(app).post("/workflows/me/execute", json={"inputs": {}})

        node_records = [
            _render_record(r) for r in caplog.records if r.name == "HandlerNode"
        ]
        assert node_records, "the node-execution sink never fired"
        blob = "\n".join(node_records)
        assert "execution failed" in blob, blob
        # The exception TYPE and the frame chain, both scalars.
        assert "NexusHandlerError" in blob, blob
        assert "_detect_pep563" in blob, blob
        assert _SENTINEL not in blob, blob

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
