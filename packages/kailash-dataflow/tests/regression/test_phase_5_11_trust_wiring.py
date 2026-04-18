# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for Phase 5.11 — trust integration wiring.

These tests lock in the contract that the DataFlow trust subsystem
(CARE-019/020/021) is:

1. Dormant by default — constructing a ``DataFlow`` without trust kwargs
   leaves ``_trust_executor`` and ``_audit_store`` as ``None`` and the
   Express path behaves identically to pre-trust DataFlow.
   ``TenantTrustManager`` is NOT attached as a ``db.*`` facade (removed
   2026-04-18 per rules/orphan-detection.md MUST 3 — zero production
   call sites). Consumers that need cross-tenant verification instantiate
   ``dataflow.trust.multi_tenant.TenantTrustManager`` directly.
2. Instantiable via the new ``trust_enforcement_mode`` and
   ``trust_audit_enabled`` kwargs (or the equivalent ``SecurityConfig``
   fields), without requiring a live database connection.
3. Invoked by every Express CRUD method — a stub executor installed on
   the DataFlow instance observes ``check_read_access`` /
   ``check_write_access`` calls and ``record_query_success`` /
   ``record_query_failure`` calls for each operation.
4. Able to deny queries via ``PermissionError`` in enforcing mode, and
   to merge additional filters from the access plan into the real
   query.
5. Able to write a ``SignedAuditRecord`` into the ``DataFlowAuditStore``
   when ``trust_audit_enabled=True``.

The tests use a lightweight stub executor rather than the full
TrustAwareQueryExecutor + Kaizen stack so they can run in Tier 1 with
SQLite and no external dependencies.
"""

import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import pytest

from dataflow import DataFlow
from dataflow.core.agent_context import async_agent_context
from dataflow.trust.audit import DataFlowAuditStore
from dataflow.trust.query_wrapper import QueryAccessResult, TrustAwareQueryExecutor

pytestmark = pytest.mark.regression


@pytest.fixture
def sqlite_file_url():
    """Yield a file-backed SQLite URL scoped to a single test.

    ``sqlite:///:memory:`` cannot be used because DataFlow's migration
    lock table is created lazily on a separate connection and
    ``:memory:`` databases are not shared across connections.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, f"tf_{uuid.uuid4().hex}.db")
        yield f"sqlite:///{path}"


# ---------------------------------------------------------------------------
# Stub executor used to observe the wiring without needing Kaizen/Core SDK
# ---------------------------------------------------------------------------


def _pass_through_plan(
    *,
    additional_filters: Optional[Dict[str, Any]] = None,
    row_limit: Optional[int] = None,
    pii: Optional[List[str]] = None,
    allowed: bool = True,
    denied_reason: Optional[str] = None,
) -> QueryAccessResult:
    return QueryAccessResult(
        allowed=allowed,
        filtered_columns=[],
        additional_filters=additional_filters or {},
        row_limit=row_limit,
        denied_reason=denied_reason,
        applied_constraints=[],
        pii_columns_filtered=pii or [],
        sensitive_columns_flagged=[],
    )


class _RecordingExecutor:
    """Observer executor that mimics the TrustAwareQueryExecutor surface.

    Every Express CRUD method calls one of these methods. The recorder
    lets tests assert exactly which model/operation/plan was seen.
    """

    def __init__(
        self,
        *,
        read_plan: Optional[QueryAccessResult] = None,
        write_plan: Optional[QueryAccessResult] = None,
        deny_writes: bool = False,
    ) -> None:
        self.read_plan = read_plan or _pass_through_plan()
        self.write_plan = write_plan or _pass_through_plan()
        self.deny_writes = deny_writes
        self.read_checks: List[Dict[str, Any]] = []
        self.write_checks: List[Dict[str, Any]] = []
        self.successes: List[Dict[str, Any]] = []
        self.failures: List[Dict[str, Any]] = []

    async def check_read_access(
        self,
        *,
        model_name: str,
        filter: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
    ) -> QueryAccessResult:
        self.read_checks.append(
            {"model": model_name, "filter": filter, "agent_id": agent_id}
        )
        return self.read_plan

    async def check_write_access(
        self,
        *,
        model_name: str,
        operation: str,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
    ) -> QueryAccessResult:
        self.write_checks.append(
            {"model": model_name, "operation": operation, "agent_id": agent_id}
        )
        if self.deny_writes:
            raise PermissionError(f"{operation} denied by test stub")
        return self.write_plan

    def apply_result_filter(self, data: Any, plan: QueryAccessResult) -> Any:
        if not plan.pii_columns_filtered:
            return data
        if isinstance(data, list):
            return [
                (
                    {k: v for k, v in row.items() if k not in plan.pii_columns_filtered}
                    if isinstance(row, dict)
                    else row
                )
                for row in data
            ]
        if isinstance(data, dict):
            return {k: v for k, v in data.items() if k not in plan.pii_columns_filtered}
        return data

    async def record_query_success(
        self,
        *,
        model_name: str,
        operation: str,
        plan: QueryAccessResult,
        agent_id: Optional[str] = None,
        trust_context: Any = None,
        rows_affected: int = 0,
        query_params: Any = None,
    ) -> Optional[str]:
        self.successes.append(
            {
                "model": model_name,
                "operation": operation,
                "agent_id": agent_id,
                "rows_affected": rows_affected,
            }
        )
        return "success-event-id"

    async def record_query_failure(
        self,
        *,
        model_name: str,
        operation: str,
        plan: Optional[QueryAccessResult],
        agent_id: Optional[str] = None,
        trust_context: Any = None,
        error: Optional[str] = None,
        query_params: Any = None,
    ) -> None:
        self.failures.append(
            {
                "model": model_name,
                "operation": operation,
                "agent_id": agent_id,
                "error": error,
            }
        )


# ---------------------------------------------------------------------------
# 1. Dormancy
# ---------------------------------------------------------------------------


def test_trust_disabled_by_default():
    """Default DataFlow has trust subsystems dormant.

    ``_tenant_trust_manager`` is NOT an attribute on DataFlow (removed
    2026-04-18 per rules/orphan-detection.md MUST 3). The class remains
    available at ``dataflow.trust.multi_tenant.TenantTrustManager`` for
    standalone consumer use.
    """
    db = DataFlow("sqlite:///:memory:")
    try:
        assert db._trust_executor is None
        assert db._audit_store is None
        assert not hasattr(db, "_tenant_trust_manager"), (
            "_tenant_trust_manager facade should NOT exist on DataFlow until "
            "a production call site is wired (rules/orphan-detection.md MUST 3)."
        )
        assert db.config.security.trust_enforcement_mode == "disabled"
        assert db.config.security.trust_audit_enabled is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_create_without_trust_unchanged(sqlite_file_url):
    """Express.create works unchanged when trust is disabled."""
    db = DataFlow(sqlite_file_url)

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        result = await db.express.create("_Widget", {"id": 1, "name": "alpha"})
        assert result is not None
        got = await db.express.read("_Widget", "1")
        assert got is not None
        assert got.get("name") == "alpha"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 2. Instantiation
# ---------------------------------------------------------------------------


def test_trust_enforcement_mode_kwarg_instantiates_executor():
    db = DataFlow("sqlite:///:memory:", trust_enforcement_mode="enforcing")
    try:
        assert db._trust_executor is not None
        assert isinstance(db._trust_executor, TrustAwareQueryExecutor)
        assert db.config.security.trust_enforcement_mode == "enforcing"
    finally:
        db.close()


def test_trust_audit_enabled_kwarg_instantiates_store():
    db = DataFlow("sqlite:///:memory:", trust_audit_enabled=True)
    try:
        assert db._audit_store is not None
        assert isinstance(db._audit_store, DataFlowAuditStore)
        # Audit enabled forces executor instantiation for unified wiring.
        assert db._trust_executor is not None
    finally:
        db.close()


def test_tenant_trust_manager_not_attached_as_facade():
    """Regression: ``_tenant_trust_manager`` was removed from the DataFlow
    facade on 2026-04-18 because no framework hot path invoked its
    methods (Phase 5.11-shaped orphan). When a production call site is
    wired, the facade MUST be re-added in the SAME PR. Until then, this
    test asserts the facade is absent so reintroducing it without a
    call site fails loudly.

    See rules/orphan-detection.md MUST 1+3, specs/dataflow-core.md § 21.2,
    workspaces/issues-492-497/journal/0003-RISK-tenant-trust-manager-orphan.md.
    """
    db = DataFlow(
        "sqlite:///:memory:",
        multi_tenant=True,
        trust_enforcement_mode="permissive",
    )
    try:
        assert not hasattr(db, "_tenant_trust_manager"), (
            "Re-adding _tenant_trust_manager without a production call site "
            "recreates the Phase 5.11 orphan. Wire into features/express.py "
            "in the SAME PR."
        )
        # The class itself remains importable for standalone consumer use.
        from dataflow.trust.multi_tenant import TenantTrustManager

        assert TenantTrustManager is not None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 3. Express wiring — stub executor observes every CRUD operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_express_read_invokes_trust_executor(sqlite_file_url):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        recorder = _RecordingExecutor()
        db._trust_executor = recorder

        await db.express.create("_Widget", {"id": 42, "name": "zeta"})
        async with async_agent_context("agent-A"):
            got = await db.express.read("_Widget", "42")

        assert got is not None
        # Read check recorded with agent context.
        read_events = [c for c in recorder.read_checks if c["agent_id"] == "agent-A"]
        assert read_events, "expected read check under agent context"
        # Success audit fired for the read.
        read_successes = [
            s
            for s in recorder.successes
            if s["operation"] == "read" and s["agent_id"] == "agent-A"
        ]
        assert read_successes, "expected read success audit"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_write_invokes_trust_executor(sqlite_file_url):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        recorder = _RecordingExecutor()
        db._trust_executor = recorder

        async with async_agent_context("agent-B"):
            await db.express.create("_Widget", {"id": 7, "name": "bravo"})
            await db.express.update("_Widget", "7", {"name": "bravo-2"})
            await db.express.delete("_Widget", "7")

        ops_seen = {c["operation"] for c in recorder.write_checks}
        assert {"create", "update", "delete"}.issubset(ops_seen)
        success_ops = {s["operation"] for s in recorder.successes}
        assert {"create", "update", "delete"}.issubset(success_ops)
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_list_merges_additional_filters_from_plan(sqlite_file_url):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str
        department: str

    try:
        await db.initialize()
        await db.express.create(
            "_Widget", {"id": 1, "name": "alpha", "department": "finance"}
        )
        await db.express.create(
            "_Widget", {"id": 2, "name": "beta", "department": "engineering"}
        )

        recorder = _RecordingExecutor(
            read_plan=_pass_through_plan(
                additional_filters={"department": "finance"},
            )
        )
        db._trust_executor = recorder

        async with async_agent_context("agent-C"):
            rows = await db.express.list("_Widget")

        names = {r["name"] for r in rows}
        assert (
            "alpha" in names and "beta" not in names
        ), f"expected plan filter to scope list to finance rows, got {names}"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_list_honours_row_limit_from_plan(sqlite_file_url):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        for i in range(5):
            await db.express.create("_Widget", {"id": i + 1, "name": f"w{i}"})

        recorder = _RecordingExecutor(read_plan=_pass_through_plan(row_limit=2))
        db._trust_executor = recorder

        async with async_agent_context("agent-D"):
            rows = await db.express.list("_Widget", limit=100)

        assert len(rows) == 2, f"expected row_limit=2 to tighten list, got {len(rows)}"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_read_applies_pii_filter_from_plan(sqlite_file_url):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str
        email: str

    try:
        await db.initialize()
        await db.express.create(
            "_Widget", {"id": 1, "name": "alpha", "email": "a@x.io"}
        )

        recorder = _RecordingExecutor(read_plan=_pass_through_plan(pii=["email"]))
        db._trust_executor = recorder

        async with async_agent_context("agent-E"):
            got = await db.express.read("_Widget", "1", cache_ttl=0)

        assert got is not None
        assert "email" not in got, "email should be stripped by PII filter"
        assert got.get("name") == "alpha"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 4. Permission denial
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforcing_denial_raises_permission_error(sqlite_file_url):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        recorder = _RecordingExecutor(deny_writes=True)
        db._trust_executor = recorder

        async with async_agent_context("agent-X"):
            with pytest.raises(PermissionError):
                await db.express.create("_Widget", {"id": 1, "name": "denied"})
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 5. Audit store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_store_records_query_event(sqlite_file_url):
    db = DataFlow(sqlite_file_url, trust_audit_enabled=True)

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        assert db._audit_store is not None

        async with async_agent_context("agent-Y"):
            await db.express.create("_Widget", {"id": 1, "name": "alpha"})

        # The audit store should have at least one record for the create.
        records = db._audit_store.get_records()
        assert any(
            r.operation == "create" and r.agent_id == "agent-Y" for r in records
        ), f"expected create audit under agent-Y, saw {records}"
    finally:
        db.close()
