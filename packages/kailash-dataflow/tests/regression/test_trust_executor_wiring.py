# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — ``db.trust_executor`` facade wiring.

Per rules/facade-manager-detection.md MUST Rule 2, every manager-shape
class exposed as a property on the framework's top-level class MUST have
a Tier 2 test file named ``test_<lowercase_manager>_wiring.py``. This
file covers ``TrustAwareQueryExecutor`` (``db._trust_executor`` /
``db.trust_executor``). Split from the former monolithic
``test_phase_5_11_trust_wiring.py`` (issue #499 Finding 8).

All tests import via the framework facade (``db._trust_executor``), never
via ``from dataflow.trust import TrustAwareQueryExecutor`` directly — the
facade is the wiring contract.

Origin: Phase 5.11 orphan fix (2026-04-18).
"""

import pytest

from dataflow import DataFlow
from dataflow.core.agent_context import async_agent_context
from dataflow.trust.query_wrapper import TrustAwareQueryExecutor

# ``recording_executor`` + ``plan_factory`` + ``sqlite_file_url`` come from
# conftest.py fixtures (see rationale in that file's module docstring).

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Dormancy — facade is None when no trust kwargs supplied
# ---------------------------------------------------------------------------


def test_trust_disabled_by_default():
    """Default DataFlow has ``_trust_executor`` and ``_audit_store`` dormant.

    Covers the trust_executor half of the dormancy contract; the audit_store
    sibling has its own test in ``test_audit_store_wiring.py``.
    ``_tenant_trust_manager`` is NOT an attribute on DataFlow (facade
    removed 2026-04-18; class deleted 2026-04-27 per W6-006/F-B-05 per
    rules/orphan-detection.md MUST 3) — see ``test_trust_manager_wiring.py``.
    """
    db = DataFlow("sqlite:///:memory:")
    try:
        assert db._trust_executor is None
        assert db._audit_store is None
        assert db.config.security.trust_enforcement_mode == "disabled"
        assert db.config.security.trust_audit_enabled is False
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_create_without_trust_unchanged(sqlite_file_url):
    """Express.create works unchanged when trust_executor is dormant."""
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
# Instantiation
# ---------------------------------------------------------------------------


def test_trust_enforcement_mode_kwarg_instantiates_executor():
    db = DataFlow("sqlite:///:memory:", trust_enforcement_mode="enforcing")
    try:
        assert db._trust_executor is not None
        assert isinstance(db._trust_executor, TrustAwareQueryExecutor)
        assert db.config.security.trust_enforcement_mode == "enforcing"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Express wiring — stub executor observes every CRUD operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_express_read_invokes_trust_executor(sqlite_file_url, recording_executor):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        recorder = recording_executor()
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
async def test_express_write_invokes_trust_executor(
    sqlite_file_url, recording_executor
):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        recorder = recording_executor()
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
async def test_express_list_merges_additional_filters_from_plan(
    sqlite_file_url, recording_executor, plan_factory
):
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

        recorder = recording_executor(
            read_plan=plan_factory(
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
async def test_express_list_honours_row_limit_from_plan(
    sqlite_file_url, recording_executor, plan_factory
):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        for i in range(5):
            await db.express.create("_Widget", {"id": i + 1, "name": f"w{i}"})

        recorder = recording_executor(read_plan=plan_factory(row_limit=2))
        db._trust_executor = recorder

        async with async_agent_context("agent-D"):
            rows = await db.express.list("_Widget", limit=100)

        assert len(rows) == 2, f"expected row_limit=2 to tighten list, got {len(rows)}"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_express_read_applies_pii_filter_from_plan(
    sqlite_file_url, recording_executor, plan_factory
):
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

        recorder = recording_executor(read_plan=plan_factory(pii=["email"]))
        db._trust_executor = recorder

        async with async_agent_context("agent-E"):
            got = await db.express.read("_Widget", "1", cache_ttl=0)

        assert got is not None
        assert "email" not in got, "email should be stripped by PII filter"
        assert got.get("name") == "alpha"
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Permission denial
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_enforcing_denial_raises_permission_error(
    sqlite_file_url, recording_executor
):
    db = DataFlow(sqlite_file_url, trust_enforcement_mode="enforcing")

    @db.model
    class _Widget:
        id: int
        name: str

    try:
        await db.initialize()
        recorder = recording_executor(deny_writes=True)
        db._trust_executor = recorder

        async with async_agent_context("agent-X"):
            with pytest.raises(PermissionError):
                await db.express.create("_Widget", {"id": 1, "name": "denied"})
    finally:
        db.close()
