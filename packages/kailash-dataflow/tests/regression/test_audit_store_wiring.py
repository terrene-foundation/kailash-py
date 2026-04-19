# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests — ``db.audit_store`` facade wiring.

Per rules/facade-manager-detection.md MUST Rule 2, every manager-shape
class exposed as a property on the framework's top-level class MUST have
a Tier 2 test file named ``test_<lowercase_manager>_wiring.py``. This
file covers ``DataFlowAuditStore`` (``db._audit_store``). Split from the
former monolithic ``test_phase_5_11_trust_wiring.py`` (issue #499 Finding 8).

All tests import via the framework facade (``db._audit_store``), never
via ``from dataflow.trust.audit import DataFlowAuditStore`` in the
production path — the facade is the wiring contract.

Origin: Phase 5.11 orphan fix (2026-04-18).
"""

import pytest

from dataflow import DataFlow
from dataflow.core.agent_context import async_agent_context
from dataflow.trust.audit import DataFlowAuditStore

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Instantiation
# ---------------------------------------------------------------------------


def test_trust_audit_enabled_kwarg_instantiates_store():
    db = DataFlow("sqlite:///:memory:", trust_audit_enabled=True)
    try:
        assert db._audit_store is not None
        assert isinstance(db._audit_store, DataFlowAuditStore)
        # Audit enabled forces executor instantiation for unified wiring.
        assert db._trust_executor is not None
    finally:
        db.close()


# ---------------------------------------------------------------------------
# End-to-end — the framework actually writes audit rows via the facade
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
