"""Regression: raw exceptions leaked to HTTP clients via ``detail=str(e)`` (#2015).

A driver/transport error reaching a request handler carries a DSN, a token, or
an internal path. Rendering it into the response body hands that to the CALLER
-- and on ``DashboardAPIServer`` the routes carried no authentication at all,
so the caller was anyone who could reach the port.

That last clause is no longer unconditionally true: #2112 gave
``DashboardAPIServer`` the same fail-closed gate as the six surfaces of #2072
(``src/kailash/visualization/api.py:141-266``, ``require_auth: bool = True``).
The leak still matters and is still tested, because the gate is opt-OUT-able
and because an authenticated low-privilege caller must not receive a DSN
either. ``_client`` below therefore constructs with ``require_auth=False`` --
the explicit opt-out, which is precisely the deployment where the original
"anyone who can reach the port" threat model still holds.

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
import pathlib
import types

import pytest

fastapi = pytest.importorskip(
    "fastapi", reason="visualization API needs the fastapi extra"
)
from fastapi.testclient import TestClient  # noqa: E402

import kailash.utils.http_errors as _http_errors_mod  # noqa: E402
from kailash.utils.http_errors import safe_http_detail  # noqa: E402
from kailash.visualization.api import DashboardAPIServer  # noqa: E402

# --- Subject-resolution guard -------------------------------------------
# This file resolves its subject two ways: the behavioural tests import
# `kailash.…` (resolved via pytest.ini's `pythonpath = src`, relative to
# ROOTDIR) while the AST sweep walks the tree relative to `__file__`. Those
# are the same tree only when rootdir is this checkout. Run with a different
# rootdir -- from the main checkout, or with an installed kailash winning the
# path -- and the behavioural tests exercise OTHER source while the sweep
# exercises this one, and the file still goes green. A test that passes while
# measuring the wrong tree is worse than no test, so the mismatch is made to
# RED here, before any test runs.
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SUBJECT = pathlib.Path(_http_errors_mod.__file__).resolve()
if _REPO_ROOT not in _SUBJECT.parents:
    raise RuntimeError(
        "these tests would measure a different tree than they assert over: "
        f"`kailash.utils.http_errors` resolved to {_SUBJECT}, which is not "
        f"under {_REPO_ROOT}. Run pytest with this checkout as rootdir."
    )

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
    # require_auth=False: this suite exercises ERROR-BODY SANITIZATION, not
    # the authentication gate #2112 added, and it must reach the handler to
    # read the 500 body. The opt-out is also the honest reproduction of the
    # threat model below -- a deployment that declined the gate is exactly the
    # one where "the caller is anyone who can reach the port" still holds.
    server = DashboardAPIServer(
        task_manager=_ExplodingTaskManager(exc), require_auth=False
    )
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
def test_allowlist_masking_covers_only_url_carriers_and_says_so():
    """Pin the allowlist's REAL reach, so no caller over-trusts it.

    The previous allowlist test used a DSN only, so it returned the same green
    whether the masking were credential-safe in general or URL-shaped-only.
    It could not discriminate its own name. This states the actual boundary:
    URL userinfo is masked, and bearer tokens / CLI flags / cloud keys /
    filesystem paths are NOT. That is why the allowlist is opt-in per type and
    why no site in this PR allowlists a type it does not control.
    """
    logger = logging.getLogger("test.http_errors.reach")

    def detail_for(message):
        return safe_http_detail(
            _UserFacingError(message),
            logger=logger,
            context="probe masking reach",
            status_code=400,
            safe_types=(_UserFacingError,),
        )

    # Masked: URL userinfo.
    assert SECRET not in detail_for(f"connect failed: {DSN}")

    # NOT masked -- documented limitation, asserted so a future change that
    # widens or narrows the reach has to update this test deliberately.
    for label, payload, token in [
        ("bearer", "Authorization: Bearer SYNTH_TOK_AAAA", "SYNTH_TOK_AAAA"),
        ("cli flag", "svc --token=SYNTH_VALUE", "SYNTH_VALUE"),
        ("cloud key", "AKIA_SYNTHETIC_EXAMPLE_KEY", "AKIA_SYNTHETIC_EXAMPLE_KEY"),
        ("path", "/home/op/.config/kailash/secrets.yaml", "secrets.yaml"),
    ]:
        assert token in detail_for(payload), (
            f"{label} is now masked -- the allowlist's reach widened. That is "
            "an improvement, but update this test and the module docstring so "
            "the documented boundary matches the code."
        )


@pytest.mark.regression
def test_helper_is_total_even_when_str_raises():
    """A sanitizer called from an `except` block must never raise (M1)."""
    logger = logging.getLogger("test.http_errors.total")

    class _Unrenderable(Exception):
        def __str__(self):
            raise RuntimeError("__str__ exploded")

    # Must not propagate: the caller is already handling another exception.
    detail = safe_http_detail(
        _Unrenderable(), logger=logger, context="probe totality", status_code=500
    )
    assert detail.startswith("Internal server error (reference: ")

    # Same on the allowlisted branch, which renders the message.
    allowed = safe_http_detail(
        _Unrenderable(),
        logger=logger,
        context="probe totality",
        status_code=400,
        safe_types=(_Unrenderable,),
    )
    assert "unrenderable" in allowed


@pytest.mark.regression
def test_mask_response_body_contract():
    """The masker itself: structure preserved, strings masked, recursion bounded."""
    from kailash.utils.http_errors import mask_response_body

    masked = mask_response_body({"error": f"connect failed: {DSN}", "code": 500})
    assert SECRET not in json.dumps(masked)
    assert masked["code"] == 500, "non-string leaves must survive unchanged"

    assert SECRET not in mask_response_body(f"connect failed: {DSN}")

    nested = mask_response_body({"errors": [{"detail": f"at {DSN}"}]})
    assert SECRET not in json.dumps(nested)

    # self-referential body must terminate rather than blow the stack
    cyclic: dict = {}
    cyclic["self"] = cyclic
    assert "truncated" in json.dumps(mask_response_body(cyclic))


@pytest.mark.regression
@pytest.mark.parametrize("body_shape", ["dict", "str"])
def test_typed_status_response_is_masked_through_the_real_handler(body_shape):
    """H3, driven through `_execute_sync` -- not through the masker.

    Asserting on `mask_response_body` alone cannot see this: unwiring the
    call sites leaves that helper's own tests green. A real
    NexusHandlerError carries a dict or str body, so those are exactly the
    two branches that fire in production, and they are the two that used to
    skip the mask. Both are driven here.
    """
    from kailash.api.workflow_api import WorkflowAPI, WorkflowRequest

    body = (
        {"error": f"connect failed: {DSN}", "code": 500}
        if body_shape == "dict"
        else f"connect failed: {DSN}"
    )

    class _TypedHandlerError(Exception):
        """Stands in for nexus' NexusHandlerError: status_code AND body."""

        status_code = 500

        def __init__(self):
            super().__init__("typed handler failure")
            self.body = body

    class _ExplodingRuntime:
        def execute(self, *a, **kw):
            raise _TypedHandlerError()

    stub = types.SimpleNamespace(
        runtime=_ExplodingRuntime(),
        workflow_graph=object(),
        _find_typed_status_exc=WorkflowAPI._find_typed_status_exc,
    )

    response = asyncio.run(WorkflowAPI._execute_sync(stub, WorkflowRequest(inputs={})))

    rendered = response.body.decode() if hasattr(response, "body") else str(response)
    assert response.status_code == 500
    assert SECRET not in rendered, f"typed {body_shape} body leaked: {rendered}"
    assert DSN not in rendered, f"typed {body_shape} body leaked the DSN: {rendered}"


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

    gateway = WorkflowAPIGateway(require_auth=False)
    gateway.mcp_servers["broken"] = _ExplodingMCPServer()

    response = TestClient(gateway.app, raise_server_exceptions=False).get("/mcp/tools")

    assert response.status_code == 200
    assert (
        SECRET not in response.text
    ), f"/mcp/tools leaked the credential: {response.text}"
    assert DSN not in response.text, f"/mcp/tools leaked the DSN: {response.text}"
    assert "reference:" in response.json()["broken"]["error"]


# ---------------------------------------------------------------------------
# Error paths must be EXECUTED, not just reasoned about
#
# `safe_http_detail` is called from inside `except` branches. A module that
# calls it without importing it raises NameError at request time -- while
# handling another exception -- and no test that fails to enter the branch
# can see that. So each converted branch below is actually driven.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_enterprise_health_probes_drive_their_except_branches():
    """All four /enterprise/health probes, each through its failure path.

    Called unbound against a stub `self`: that executes the real method
    bodies -- including the global lookup of `safe_http_detail` -- without
    standing up an entire enterprise server.
    """
    from kailash.servers.enterprise_workflow_server import EnterpriseWorkflowServer

    exc = ConnectionError(f"could not connect to {DSN}")

    class _ExplodingRegistry:
        def list_resources(self):
            return ["primary_db"]

        async def _is_healthy(self, name):
            raise exc

    # Per-resource failure -> degraded, with the driver error contained.
    resource_health = asyncio.run(
        EnterpriseWorkflowServer._check_resource_health(
            types.SimpleNamespace(resource_registry=_ExplodingRegistry())
        )
    )
    rendered = json.dumps(resource_health)
    assert SECRET not in rendered, f"resource health leaked the credential: {rendered}"
    assert resource_health["status"] == "degraded"
    assert "reference:" in resource_health["resources"]["primary_db"]["error"]

    # Enumeration itself failing -> the outer except branch.
    class _ExplodingEnumeration:
        def list_resources(self):
            raise exc

    outer = asyncio.run(
        EnterpriseWorkflowServer._check_resource_health(
            types.SimpleNamespace(resource_registry=_ExplodingEnumeration())
        )
    )
    assert SECRET not in json.dumps(outer)
    assert outer["status"] == "unhealthy"
    assert "reference:" in outer["error"]

    # Runtime + secret-manager probes: a raising attribute enters each except.
    class _RaisesOnAccess:
        def __getattr__(self, name):
            raise exc

    runtime_health = asyncio.run(
        EnterpriseWorkflowServer._check_runtime_health(_RaisesOnAccess())
    )
    assert SECRET not in json.dumps(runtime_health)
    assert "reference:" in runtime_health["error"]

    secret_health = asyncio.run(
        EnterpriseWorkflowServer._check_secret_manager_health(_RaisesOnAccess())
    )
    assert SECRET not in json.dumps(secret_health)
    assert "reference:" in secret_health["error"]


@pytest.mark.regression
def test_workflow_status_does_not_allowlist_bare_valueerror():
    """H1: `safe_types=(ValueError,)` under `except ValueError` was a no-op.

    Every exception that could reach that helper call was inside the allowlist
    by construction, so the fail-closed default was unreachable at that site --
    and because the `try:` also spanned the response-model construction, a
    `pydantic.ValidationError` (which subclasses `ValueError`) returned the
    offending INPUT VALUES to the caller.
    """
    import ast
    import inspect
    import textwrap

    from kailash.gateway import api as gateway_api

    # Asserted over the AST, not the source TEXT: the prose explaining why
    # the allowlist was removed necessarily contains the word `safe_types`,
    # so a substring check matches its own documentation and is not a test.
    tree = ast.parse(
        textwrap.dedent(inspect.getsource(gateway_api.get_workflow_status))
    )

    allowlisted = [
        kw
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        for kw in n.keywords
        if kw.arg == "safe_types"
    ]
    assert not allowlisted, (
        "get_workflow_status allowlists an exception type again; under an "
        "`except ValueError` that cannot fail closed"
    )

    # The lookup and the serialization must not share one `try:`, or a
    # ValidationError from the model is reported as a 404 not-found.
    tries = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
    assert len(tries) >= 2, (
        "the lookup and the response-model construction are back in one "
        "`try:`; a pydantic ValidationError would surface as a 404 carrying "
        "the offending input values"
    )


@pytest.mark.regression
def test_template_routes_never_catch_valueerror_around_an_execute():
    """H2: a ValueError arm must not span the DataFlow execute.

    These scaffold files cannot be imported (they import a `templates.*`
    package rooted at the app, not at this repo), so the contract is checked
    structurally. It is the shape that matters: any `try` whose handlers
    catch `ValueError` and whose body reaches `runtime.execute(...)` routes
    every ValueError SUBCLASS from the database layer -- pydantic
    ValidationError, JSONDecodeError, UnicodeDecodeError -- into a 400 body
    carrying the driver's message. Users copy these files, so the shape
    propagates outward.
    """
    import ast

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    template_dir = (
        repo_root
        / "packages"
        / "kailash-dataflow"
        / "templates"
        / "api_gateway_starter"
    )
    assert template_dir.is_dir(), f"template dir moved: {template_dir}"

    offenders = []
    for path in template_dir.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            catches_value_error = any(
                (isinstance(h.type, ast.Name) and h.type.id == "ValueError")
                or (
                    isinstance(h.type, ast.Tuple)
                    and any(
                        isinstance(e, ast.Name) and e.id == "ValueError"
                        for e in h.type.elts
                    )
                )
                for h in node.handlers
            )
            if not catches_value_error:
                continue
            reaches_execute = any(
                isinstance(c, ast.Call)
                and isinstance(c.func, ast.Attribute)
                and c.func.attr == "execute"
                for stmt in node.body
                for c in ast.walk(stmt)
            )
            if reaches_execute:
                offenders.append(f"{path.relative_to(repo_root)}:{node.lineno}")

    assert not offenders, (
        "a `try` catching ValueError spans a DataFlow execute; any ValueError "
        "subclass from the database layer is returned verbatim as a 400: "
        f"{offenders}"
    )


@pytest.mark.regression
def test_every_module_calling_the_helper_also_imports_it():
    """The import-omission class, swept structurally across all call sites.

    Driving every converted branch behaviourally is the ideal, but some sit
    behind servers that are expensive to stand up. This closes the same gap
    for ALL of them at once, and keeps closing it for sites added later:
    a module that calls `safe_http_detail` without importing it fails here
    even if no test ever reaches its except branch.
    """
    import ast

    repo_root = pathlib.Path(__file__).resolve().parents[2]

    # Scope to FIRST-PARTY source. `packages/*/` carries local `.venv` /
    # `site-packages` trees in a developer checkout, so an unscoped rglob walks
    # ~78k files instead of ~4.8k -- 94% of them third-party. That is not just
    # slow (6min vs seconds): this sweep asserts a property of OUR modules, so
    # auditing a vendored dependency's source can only produce a finding no one
    # in this repo can act on. CI checkouts have no such trees, which is exactly
    # why the cost is invisible there and only ever bites a local full-suite run.
    _VENDORED = {
        ".venv",
        "venv",
        "site-packages",
        "node_modules",
        "build",
        ".tox",
        "dist",
    }

    def _first_party(root: pathlib.Path):
        for p in root.rglob("*.py"):
            if _VENDORED.isdisjoint(p.parts):
                yield p

    offenders = []
    for path in list(_first_party(repo_root / "src")) + list(
        _first_party(repo_root / "packages")
    ):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue  # scaffold templates carry substitution tokens
        # Bare-name calls only bind if the name itself is imported. An
        # attribute call (`http_errors.safe_http_detail(...)`) binds via the
        # MODULE name instead, so it is collected separately rather than
        # silently skipped -- skipping it would make this sweep quietly
        # incomplete in exactly the way it exists to prevent.
        bare_calls = False
        attr_modules = set()
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            if isinstance(fn, ast.Name) and fn.id == "safe_http_detail":
                bare_calls = True
            elif (
                isinstance(fn, ast.Attribute)
                and fn.attr == "safe_http_detail"
                and isinstance(fn.value, ast.Name)
            ):
                attr_modules.add(fn.value.id)
        if not bare_calls and not attr_modules:
            continue
        bound = {
            alias.asname or alias.name
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom))
            for alias in n.names
        } | {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        if bare_calls and "safe_http_detail" not in bound:
            offenders.append(str(path.relative_to(repo_root)))
        for mod in attr_modules:
            if mod not in bound:
                offenders.append(f"{path.relative_to(repo_root)} (via {mod}.)")

    assert not offenders, (
        "these modules call safe_http_detail without importing it; each is a "
        f"NameError raised while handling another exception: {offenders}"
    )
