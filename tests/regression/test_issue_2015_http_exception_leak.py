"""Regression: raw exceptions leaked to HTTP clients via ``detail=str(e)`` (#2015).

A driver/transport error reaching a request handler carries a DSN, a token, or
an internal path. Rendering it into the response body hands that to the CALLER
-- and on ``DashboardAPIServer`` the routes carry no auth dependency at all, so
the caller is anyone who can reach the port.

These are behavioral tests: they drive a real FastAPI app through a real
``TestClient`` and read the actual response body. A source grep asserting the
absence of ``detail=str(e)`` would pass against any rewrite that merely spelled
the leak differently, so it is not used as the assertion.

The paired assertion in every case is that the SERVER-side record still
carries the diagnostic (``rules/zero-tolerance.md`` Rule 3: sanitizing the
client body must not swallow the error), and that the reference id appearing
in the client body is the one in the log, so an operator can correlate them.
"""

import asyncio
import json
import logging

import pytest

fastapi = pytest.importorskip(
    "fastapi", reason="visualization API needs the fastapi extra"
)
from fastapi.testclient import TestClient  # noqa: E402

from kailash.utils.http_errors import safe_http_detail  # noqa: E402
from kailash.visualization.api import DashboardAPIServer  # noqa: E402

# A credential-bearing message of exactly the shape a driver raises.
DSN = "postgresql://svc_user:sup3rs3cret@db.internal:5432/kailash"
SECRET = "sup3rs3cret"


class _ExplodingTaskManager:
    """Task manager whose reads fail the way a real backing store fails.

    Not a mock of the HTTP layer -- the FastAPI app, routing, serialization and
    error handling under test are all real. This only supplies the failure.
    """

    def __init__(self, exc: Exception):
        self._exc = exc

    def list_runs(self, *a, **kw):
        raise self._exc

    def get_run(self, *a, **kw):
        raise self._exc

    def get_run_tasks(self, *a, **kw):
        raise self._exc


def _client(exc: Exception) -> TestClient:
    server = DashboardAPIServer(task_manager=_ExplodingTaskManager(exc))
    # raise_server_exceptions=False so a 500 comes back as a response to
    # inspect rather than re-raising into the test.
    return TestClient(server.app, raise_server_exceptions=False)


@pytest.mark.regression
def test_dsn_does_not_reach_an_unauthenticated_client(caplog):
    """The headline leak: unauthenticated GET, response body carries the DSN."""
    exc = ConnectionError(f"could not connect to {DSN}")

    with caplog.at_level(logging.ERROR):
        response = _client(exc).get("/api/v1/runs")

    assert response.status_code == 500
    body = response.text

    # The client must not receive the credential, the DSN, or the raw message.
    assert SECRET not in body, f"password reached the client: {body!r}"
    assert DSN not in body, f"DSN reached the client: {body!r}"
    assert (
        "could not connect" not in body
    ), f"raw exception text reached client: {body!r}"

    # ...but the failure is still reported, not swallowed.
    assert "reference:" in body, f"no correlation reference for the operator: {body!r}"
    assert caplog.records, "error was sanitized out of existence server-side"


@pytest.mark.regression
def test_server_log_retains_the_diagnostic_and_correlates_by_reference(caplog):
    """Debuggability is preserved: the log names the failure and shares the id."""
    exc = ConnectionError(f"could not connect to {DSN}")

    with caplog.at_level(logging.ERROR):
        response = _client(exc).get("/api/v1/runs")

    detail = response.json()["detail"]
    reference = detail.rsplit("reference: ", 1)[1].rstrip(")")
    assert reference, "reference id was empty"

    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert reference in logged, "client reference id is absent from the server log"
    assert "ConnectionError" in logged, "exception type missing from the server record"
    # The log keeps the diagnostic, with the credential carrier masked.
    assert SECRET not in logged, "credential was written to the server log"


@pytest.mark.regression
@pytest.mark.parametrize(
    "path",
    ["/api/v1/runs", "/api/v1/runs/some-run-id", "/api/v1/runs/some-run-id/tasks"],
)
def test_sibling_routes_do_not_leak_either(path, caplog):
    """Every converted route on this server, not just the first one."""
    exc = ConnectionError(f"could not connect to {DSN}")

    with caplog.at_level(logging.ERROR):
        response = _client(exc).get(path)

    assert response.status_code == 500
    assert SECRET not in response.text, f"{path} leaked the credential"
    assert DSN not in response.text, f"{path} leaked the DSN"


# ---------------------------------------------------------------------------
# The shared helper's own contract
# ---------------------------------------------------------------------------


class _UserFacingError(Exception):
    """Stands in for a type whose message is written for end users."""


@pytest.mark.regression
def test_helper_is_fail_closed_by_default(caplog):
    """An unlisted exception type never reaches the client, whatever it says."""
    logger = logging.getLogger("test.http_errors.failclosed")

    with caplog.at_level(logging.ERROR):
        detail = safe_http_detail(
            ConnectionError(f"connect failed: {DSN}"),
            logger=logger,
            context="probe backing store",
        )

    assert SECRET not in detail
    assert "connect failed" not in detail
    assert detail.startswith("Internal server error (reference: ")


@pytest.mark.regression
def test_helper_allowlist_is_opt_in_and_still_masks(caplog):
    """An allowlisted type's message passes -- with credential carriers masked."""
    logger = logging.getLogger("test.http_errors.allowlist")

    with caplog.at_level(logging.ERROR):
        passed = safe_http_detail(
            _UserFacingError("run id must be a uuid"),
            logger=logger,
            context="validate run id",
            status_code=400,
            safe_types=(_UserFacingError,),
        )
        masked = safe_http_detail(
            _UserFacingError(f"bad config: {DSN}"),
            logger=logger,
            context="validate config",
            status_code=400,
            safe_types=(_UserFacingError,),
        )

    assert passed.startswith("run id must be a uuid (reference: ")
    # Allowlisted, but a credential in the message is still not shipped.
    assert SECRET not in masked, f"allowlisted message leaked a credential: {masked!r}"


@pytest.mark.regression
def test_helper_status_code_selects_the_generic_message():
    logger = logging.getLogger("test.http_errors.status")
    exc = RuntimeError("internal")

    assert safe_http_detail(
        exc, logger=logger, context="c", status_code=404
    ).startswith("Resource not found")
    assert safe_http_detail(
        exc, logger=logger, context="c", status_code=403
    ).startswith("Access denied")
    # An unmapped status still fails closed rather than echoing the exception.
    assert safe_http_detail(
        exc, logger=logger, context="c", status_code=418
    ).startswith("Internal server error")


@pytest.mark.regression
def test_references_are_unique_per_call():
    logger = logging.getLogger("test.http_errors.unique")
    exc = RuntimeError("boom")
    a = safe_http_detail(exc, logger=logger, context="c")
    b = safe_http_detail(exc, logger=logger, context="c")
    assert a != b, "reference ids collided; correlation would be ambiguous"


# ---------------------------------------------------------------------------
# Sites the issue's `detail=str(e)` grep cannot see
#
# Each of these renders an exception into a response body without ever
# spelling `detail=`. They are the reason the fix is not a find-and-replace.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_pool_metrics_do_not_leak_the_dsn_to_the_metrics_endpoint():
    """GET /metrics and /pools return collect()'s dict verbatim.

    This is the likeliest site in the codebase to carry a real credential:
    the exception comes from a database driver, and driver connect failures
    quote the connection string.
    """
    from kailash.servers.connection_metrics_router import ConnectionMetricsProvider

    class _ExplodingPool:
        async def get_pool_statistics(self):
            raise ConnectionError(f"could not connect to {DSN}")

    provider = ConnectionMetricsProvider()
    provider.register_source("primary", _ExplodingPool())

    results = asyncio.run(provider.collect())

    rendered = json.dumps(results)
    assert SECRET not in rendered, f"pool metrics leaked the credential: {rendered}"
    assert DSN not in rendered, f"pool metrics leaked the DSN: {rendered}"
    # Still reported as unhealthy with a correlation id, not silently dropped.
    assert results["primary"]["health_score"] == 0
    assert "reference:" in results["primary"]["error"]


@pytest.mark.regression
def test_mcp_tools_listing_does_not_leak_server_exceptions():
    """GET /mcp/tools returns its per-server dict as the body."""
    from kailash.api.gateway import WorkflowAPIGateway

    class _ExplodingMCPServer:
        def list_tools(self):
            raise ConnectionError(f"MCP transport failed for {DSN}")

    gateway = WorkflowAPIGateway()
    gateway.mcp_servers["broken"] = _ExplodingMCPServer()

    response = TestClient(gateway.app, raise_server_exceptions=False).get("/mcp/tools")

    assert response.status_code == 200
    assert (
        SECRET not in response.text
    ), f"/mcp/tools leaked the credential: {response.text}"
    assert DSN not in response.text, f"/mcp/tools leaked the DSN: {response.text}"
    assert "reference:" in response.json()["broken"]["error"]
