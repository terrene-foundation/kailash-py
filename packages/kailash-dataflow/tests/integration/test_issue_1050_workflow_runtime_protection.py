# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression guard: write-protection enforces on the workflow-runtime
path AND ``ProtectionViolation`` survives the runtime's exception re-wrap as
its genuine type (issue #1050, AC#3 — the permanent guard for the red-team
CRITICAL).

Background
----------
``ProtectedDataFlow`` enforces write protection by wrapping every generated
CRUD node's ``async_run`` with a ``protection_engine.check_operation`` call
(``dataflow.core.protection_middleware.protect_dataflow_node``). On a BLOCK
the engine raises ``ProtectionViolation``.

The red-team CRITICAL was on the **workflow-runtime path** —
``runtime.execute(workflow.build())`` (plain ``LocalRuntime``) and
``AsyncLocalRuntime.execute_workflow_async(...)``. ``AsyncNode.execute_async``
(``kailash/nodes/base_async.py``) re-raises ``NodeValidationError`` /
``NodeExecutionError`` instances as-is but WRAPS every other ``Exception``
subclass in a fresh ``NodeExecutionError``. Before the Shard-1a fix,
``ProtectionViolation`` was a bare-``Exception`` subclass, so a block raised
from the async hot path on the workflow-runtime path was re-wrapped — every
``except ProtectionViolation`` caller silently stopped matching. The fix
re-based ``ProtectionViolation`` on ``kailash.sdk_exceptions.NodeExecutionError``
so it lands in ``execute_async``'s re-raise allowlist with type intact.

What this test pins
-------------------
1. Protection ENFORCES on the workflow-runtime path (spec
   ``dataflow-protection.md`` §2 path 2 + invariant I5): a generated
   ``*CreateNode`` for a model on a read-only ``ProtectedDataFlow`` raises
   ``ProtectionViolation`` to the caller through PLAIN ``LocalRuntime`` AND
   ``AsyncLocalRuntime`` — the exact runtimes where the re-wrap bug lived
   (NOT only ``ProtectedDataFlowRuntime``).
2. The raised exception ``isinstance(exc, NodeExecutionError)`` — pinning the
   Shard-1a taxonomy contract. If a future refactor un-bases
   ``ProtectionViolation`` from ``NodeExecutionError``, the re-wrap bug
   silently returns; this assertion fails loudly first.
3. Behavioral read-back: the blocked write never reaches the database — the
   model's row count is 0 after the blocked create (NOT a status-code check).
4. Observability contract: the block emits the
   ``protection_middleware.protection_violation`` ERROR log line
   (``observability.md`` § Mandatory Log Points — the operation's observable
   contract, asserted via ``caplog``).

Tier-2 discipline
------------------
Real PostgreSQL via the ``test_suite`` ``IntegrationTestSuite`` fixture
(``tests/CLAUDE.md``; port from the harness config, NOT hardcoded) AND
file-backed SQLite (``tempfile`` + ``sqlite:///<tmp>/test.db``, NEVER
``:memory:`` — the per-event-loop ``:memory:`` isolation is what masked the
orphan originally). NO mocking (Tier-2 rule). When PostgreSQL is unreachable
in the worktree the PG parametrization is infra-gated via ``pytest.skip``
(NOT mocked, NOT a fake backend) — the file-SQLite parametrization always
runs and fully exercises both runtimes.

See issue #1050, ``specs/dataflow-protection.md`` invariants I5,
``rules/testing.md`` § Tier 2, ``rules/orphan-detection.md`` § Tier-2
integration test.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import pytest

# Workflow runtime path requires the core SDK workflow builder + runtimes.
_wf = pytest.importorskip("kailash.workflow.builder")
WorkflowBuilder = _wf.WorkflowBuilder

from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import NodeExecutionError

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection import ProtectionViolation

pytestmark = pytest.mark.integration


# --------------------------------------------------------------------------
# Backend parametrization
#
# "sqlite_file"  — always runs. File-backed (tempfile), NEVER :memory:.
# "postgresql"   — real PG via the test_suite IntegrationTestSuite fixture;
#                  infra-gated with pytest.skip when PG is unreachable in the
#                  worktree (NOT mocked, NOT a fake backend per Tier-2 rule).
# --------------------------------------------------------------------------
_BACKENDS = ["sqlite_file", "postgresql"]

# Workflow runtimes that historically carried the re-wrap bug. The third
# slot is the entry-point name; both end on AsyncNode.execute_async ->
# async_run, the path the Shard-1a taxonomy fix protects.
_RUNTIMES = ["local_runtime", "async_local_runtime"]


def _resolve_backend_url(backend: str, request):
    """Return a real DB URL for ``backend``.

    For PostgreSQL the URL comes from the shared ``test_suite``
    IntegrationTestSuite fixture (real infra, no hardcoded port). If the
    suite cannot reach PostgreSQL the fixture setup raises ``ConnectionError``;
    we convert that to ``pytest.skip`` so the PG parametrization is
    infra-gated rather than mocked.

    For SQLite a file-backed temp database is created (NEVER ``:memory:`` —
    per-event-loop ``:memory:`` isolation is exactly what masked the
    orphan in the first place).
    """
    if backend == "sqlite_file":
        tmpdir = tempfile.mkdtemp(prefix="df_issue1050_")
        db_path = Path(tmpdir) / "test.db"
        return f"sqlite:///{db_path}", None

    if backend == "postgresql":
        # Real reachability probe (a genuine TCP connect — NOT a mock) BEFORE
        # touching the async `test_suite` fixture. Requesting the async-gen
        # fixture only to `pytest.skip` inside it leaks an un-awaited
        # coroutine (RuntimeWarning — zero-tolerance.md Rule 1). Probing the
        # port first means the async fixture is only instantiated when PG is
        # genuinely up.
        import socket

        from tests.infrastructure.test_harness import DatabaseConfig

        cfg = DatabaseConfig.from_environment()
        try:
            with socket.create_connection((cfg.host, cfg.port), timeout=2):
                pass
        except OSError as exc:
            pytest.skip(
                f"PostgreSQL not reachable at {cfg.host}:{cfg.port} — PG "
                f"parametrization infra-gated (NOT mocked): {exc}"
            )
        test_suite = request.getfixturevalue("test_suite")
        return test_suite.config.url, test_suite

    raise AssertionError(f"unknown backend {backend!r}")  # pragma: no cover


async def _run_workflow(runtime_kind: str, workflow):
    """Execute ``workflow`` through the requested PLAIN runtime.

    Deliberately NOT ``ProtectedDataFlowRuntime`` — the red-team CRITICAL
    was that the plain ``LocalRuntime`` / ``AsyncLocalRuntime`` workflow
    paths re-wrapped ``ProtectionViolation``. Exercising the plain runtimes
    is the whole point of this guard.
    """
    if runtime_kind == "local_runtime":
        # Context-manager form: the SDK-blessed pattern that opts out of the
        # "without context manager" DeprecationWarning (issue #1045 /
        # zero-tolerance.md Rule 1 — warnings are errors).
        with LocalRuntime() as runtime:
            return runtime.execute(workflow.build())
    if runtime_kind == "async_local_runtime":
        # execute_workflow_async(workflow, inputs) — inputs is a REQUIRED
        # positional arg (kailash.runtime.async_local). Empty dict: node
        # config carries the create payload; protection blocks before any
        # input is consumed. `async with` is the deprecation-free cleanup.
        async with AsyncLocalRuntime() as runtime:
            return await runtime.execute_workflow_async(workflow.build(), {})
    raise AssertionError(f"unknown runtime {runtime_kind!r}")  # pragma: no cover


def _assert_node_boundary_is_protection_violation(exc: BaseException) -> None:
    """Pin the Shard-1a taxonomy contract on the GENUINE node-boundary object.

    Why a plain "is a ProtectionViolation anywhere in the chain?" walk is
    INSUFFICIENT (it false-passes when the fix is reverted): Python implicit
    exception chaining (``__context__``) and explicit ``raise ... from e``
    (``__cause__``) BOTH preserve the original ``ProtectionViolation`` object
    somewhere in the chain even when ``AsyncNode.execute_async``'s
    ``except Exception`` arm WRAPS it in a fresh ``NodeExecutionError``. So
    "PV is somewhere in the chain" is true in BOTH the fixed and the reverted
    states — a useless assertion.

    The DISCRIMINATING contract (empirically verified, fixed vs un-based):

      * Shard-1a HELD  → ``execute_async`` re-raises the genuine PV via its
        ``except NodeExecutionError: raise`` allowlist. Walking ``__cause__``,
        the FIRST ``NodeExecutionError`` instance encountered IS the genuine
        ``ProtectionViolation``. Chain: ``[Runtime…, Workflow…,
        ProtectionViolation]``.
      * Shard-1a REVERTED (PV is bare ``Exception``) → ``execute_async``'s
        ``except Exception`` arm inserts a FRESH ``NodeExecutionError``
        wrapper at the node boundary; the genuine PV is demoted one level
        deeper. Chain: ``[Runtime…, Workflow…, NodeExecutionError,
        ProtectionViolation]`` — the first ``NodeExecutionError`` in the
        ``__cause__`` walk is the SDK wrapper, NOT a ``ProtectionViolation``.

    Therefore the contract is: the FIRST ``NodeExecutionError`` instance in
    the ``__cause__`` chain (the node-execution boundary object) MUST itself
    be a ``ProtectionViolation``. ``__cause__`` only (NOT ``__context__``) —
    ``__cause__`` is the explicit ``raise ... from e`` link the SDK builds
    deliberately; ``__context__`` is implicit and survives a re-wrap, which
    is exactly the false-pass we are eliminating.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, NodeExecutionError):
            # First node-boundary exception reached via the explicit
            # cause chain. Shard-1a HELDS iff this object IS a genuine
            # ProtectionViolation; a bare NodeExecutionError here is the
            # SDK re-wrap = the red-team CRITICAL regression.
            assert isinstance(cur, ProtectionViolation), (
                "Shard-1a taxonomy regressed (issue #1050 red-team CRITICAL): "
                "the node-execution-boundary exception in the workflow-runtime "
                f"__cause__ chain is a bare {type(cur).__name__!r}, NOT a "
                "ProtectionViolation. AsyncNode.execute_async's "
                "`except Exception` arm re-wrapped the genuine "
                "ProtectionViolation because it is no longer a "
                "NodeExecutionError subclass. Full top exception: "
                f"{type(exc).__name__}: {exc!r}"
            )
            return
        cur = cur.__cause__
    raise AssertionError(
        "No NodeExecutionError node-boundary exception in the raised "
        f"__cause__ chain (top = {type(exc).__name__}: {exc!r}). The "
        "workflow-runtime path did not propagate a node-execution exception "
        "at all — protection enforcement on the workflow-runtime path is "
        "broken (issue #1050, spec invariant I5). Walked __cause__ to "
        "exhaustion."
    )


@pytest.mark.regression
@pytest.mark.parametrize("backend", _BACKENDS)
@pytest.mark.parametrize("runtime_kind", _RUNTIMES)
async def test_issue_1050_workflow_runtime_protection_blocks_and_keeps_type(
    backend, runtime_kind, request, caplog
):
    """Write protection enforces on the workflow-runtime path AND
    ``ProtectionViolation`` survives ``execute_async``'s re-wrap.

    One parametrized test covers the {sqlite_file, postgresql} x
    {LocalRuntime, AsyncLocalRuntime} matrix. The PG slot is infra-gated
    (skip, never mock) when PostgreSQL is unreachable.
    """
    db_url, _suite = _resolve_backend_url(backend, request)

    db = ProtectedDataFlow(database_url=db_url, enable_protection=True)
    try:
        # Per-parametrization-UNIQUE model name. @db.model derives generated
        # node types from the class name (`{ClassName}CreateNode`). A name
        # reused across the 4 params collides in the shared DataFlow model
        # registry — the second+ declaration fails to register and the node
        # generator can fall back to a NON-protected node, silently breaking
        # the guard. A unique name per param is the structural fix.
        model_name = f"Issue1050Doc_{backend}_{runtime_kind}"
        model_cls = type(
            model_name,
            (),
            {"__annotations__": {"id": int, "title": str, "body": str}},
        )
        db.model(model_cls)

        create_node = f"{model_name}CreateNode"
        list_node = f"{model_name}ListNode"

        # Read-only mode: every write operation is BLOCKED globally
        # (spec dataflow-protection.md §2 path 2 / invariant I5).
        db.enable_read_only_mode("issue #1050 workflow-runtime regression guard")

        # ------------------------------------------------------------------
        # Surface 1 — PROPAGATING path: pytest.raises(...) on the genuine SDK
        # contract. The plain workflow runtimes re-raise a failed node's
        # exception only when the node has DEPENDENTS
        # (LocalRuntime._should_stop_on_error). A trivial downstream-dependent
        # *ListNode forces that propagating path so the block reaches the
        # caller as a raised exception (spec invariant I5: a block raises
        # ProtectionViolation to the caller). The runtime wraps it in
        # Runtime/WorkflowExecutionError; the GENUINE ProtectionViolation —
        # the object AsyncNode.execute_async re-raised via its
        # `except NodeExecutionError: raise` allowlist — is preserved in the
        # __cause__/__context__ chain ONLY because ProtectionViolation IS-A
        # NodeExecutionError (Shard-1a). If un-based, execute_async would have
        # re-wrapped it into a bare NodeExecutionError and the chain walk
        # below raises AssertionError — the permanent red-team-CRITICAL guard.
        raising_wf = WorkflowBuilder()
        raising_wf.add_node(
            create_node,
            "create_doc",
            {"title": "blocked", "body": "must never be written"},
        )
        raising_wf.add_node(list_node, "list_after", {})
        # Dependency edge: makes create_doc have a dependent so the runtime
        # propagates (raises) rather than swallowing into the result dict.
        raising_wf.add_connection("create_doc", "id", "list_after", "_unused")

        with caplog.at_level(
            logging.ERROR, logger="dataflow.core.protection_middleware"
        ):
            with pytest.raises(Exception) as exc_info:
                await _run_workflow(runtime_kind, raising_wf)

        # Taxonomy contract pin (PROPAGATING path): the node-execution
        # boundary object in the __cause__ chain MUST itself be a genuine
        # ProtectionViolation — the discriminating signal that fails loudly
        # iff Shard-1a regresses (a bare NodeExecutionError wrapper there =
        # the red-team CRITICAL re-wrap).
        _assert_node_boundary_is_protection_violation(exc_info.value)

        # Observability contract: the block emits the protection-violation
        # ERROR log line (observability.md § Mandatory Log Points). A test
        # that checks the effect but not the log lets the contract silently
        # break — production loses its debugging surface.
        assert any(
            r.name == "dataflow.core.protection_middleware"
            and "protection_middleware.protection_violation" in r.message
            for r in caplog.records
            if r.levelno >= logging.ERROR
        ), (
            "Blocked write did not emit the "
            "'protection_middleware.protection_violation' ERROR log line "
            "(observability.md § Mandatory Log Points)."
        )

        # ------------------------------------------------------------------
        # Surface 2 — SINGLE-NODE path. The two plain runtimes expose a
        # single-node block DIFFERENTLY, and the taxonomy MUST hold on BOTH:
        #
        #  * LocalRuntime: a no-dependents node is SWALLOWED — the genuine
        #    node exception is preserved under the private `_exception` key
        #    (issue #941 contract) and `error_type` records its class name.
        #    error_type MUST read "ProtectionViolation", NOT
        #    "NodeExecutionError", or the re-wrap silently returned.
        #  * AsyncLocalRuntime: `_execute_node_async` ALWAYS raises
        #    `WorkflowExecutionError ... from e` (no swallow contract). The
        #    genuine ProtectionViolation is preserved in the raised chain via
        #    `from e` — the same chain-walk taxonomy pin as Surface 1.
        #
        # Both branches assert a GENUINE ProtectionViolation that is also a
        # NodeExecutionError reaches the single-node caller path.
        single_wf = WorkflowBuilder()
        single_wf.add_node(
            create_node,
            "create_doc_single",
            {"title": "blocked2", "body": "must never be written"},
        )
        if runtime_kind == "local_runtime":
            single_results, _ = await _run_workflow(runtime_kind, single_wf)
            node_result = single_results.get("create_doc_single", {})
            preserved = node_result.get("_exception")
            assert isinstance(preserved, ProtectionViolation), (
                "LocalRuntime single-node path: the preserved node exception "
                f"is {type(preserved).__name__!r}, not a genuine "
                "ProtectionViolation. AsyncNode.execute_async re-wrapped it — "
                "the Shard-1a taxonomy contract regressed (issue #1050)."
            )
            assert isinstance(preserved, NodeExecutionError)
            assert node_result.get("error_type") == "ProtectionViolation", (
                "Runtime recorded error_type="
                f"{node_result.get('error_type')!r}; expected "
                "'ProtectionViolation'. The re-wrap collapsed the typed "
                "exception to its base."
            )
        else:
            # AsyncLocalRuntime single-node ALWAYS raises (no swallow
            # contract); pin the same discriminating node-boundary taxonomy
            # contract on the raised __cause__ chain.
            with pytest.raises(Exception) as single_exc:
                await _run_workflow(runtime_kind, single_wf)
            _assert_node_boundary_is_protection_violation(single_exc.value)

        # Behavioral read-back (NOT a status code): the blocked write never
        # reached the database. Count via a generated *ListNode through the
        # context-managed LocalRuntime (protection allows reads under
        # read-only mode; CM form keeps the deprecation surface clean).
        count_wf = WorkflowBuilder()
        count_wf.add_node(list_node, "list_docs", {})
        with LocalRuntime() as _cm_rt:
            list_results, _ = _cm_rt.execute(count_wf.build())

        rows = list_results.get("list_docs", {})
        # *ListNode result shape is implementation-detailed; normalize to a
        # list of records for the read-back assertion.
        if isinstance(rows, dict):
            records = (
                rows.get("result") or rows.get("records") or rows.get("data") or []
            )
        else:
            records = rows or []
        assert len(records) == 0, (
            "Protection was bypassed: the blocked create wrote a row "
            f"(read-back found {len(records)} rows). Workflow-runtime path "
            "did not enforce write protection (issue #1050, spec I5)."
        )
    finally:
        await db.close_async()
