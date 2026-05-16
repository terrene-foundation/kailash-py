# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 end-to-end regression for the docs-taught TDD-mode pipeline.

Issue #1022. Value-anchor — `rules/testing.md` § "MUST: End-to-End
Pipeline Regression Above Unit + Integration" (verbatim): "Every
canonical pipeline the docs teach (README Quick Start, tutorial,
3-line example) MUST have a Tier-2+ regression test executing
DOCS-EXACT code against real infra, asserting the final user-visible
outcome."

The `DataFlow(tdd_mode=True)` + `@db.model` + `WorkflowBuilder` +
`AsyncLocalRuntime.execute_workflow_async()` pipeline is documented as
the canonical (Recommended) test-mode pattern in
`packages/kailash-dataflow/docs/adr/ADR-017-test-mode-api-spec.md`
§ 2.1. Before this test, no file in `tests/regression/` exercised it
end-to-end. The closest existing test
(`tests/unit/core/test_tdd_mode_propagates_to_node_generator.py`,
renamed from `test_real_tdd_integration.py` in PR #1021) patches 7
internal init phases — it asserts constructor metadata propagation,
NOT pipeline behavior. A future refactor of the node-generation or
runtime-execution path could break the user-facing quick-start with
zero test signal; this regression closes that gap.

DOCS-EXACT fidelity: the pipeline shape (model → WorkflowBuilder →
`<Model>CreateNode` → AsyncLocalRuntime → assert created field) mirrors
ADR-017 § 2.1 verbatim. The ONLY deviations are mandated by the test
rules, not by choice:
- DB URL comes from the `IntegrationTestSuite` real-Postgres harness,
  NOT the doc's literal `"postgresql://localhost/test_db"`
  (`tests/CLAUDE.md`: "NEVER hardcode database URLs").
- `tdd_mode=True` is passed EXPLICITLY rather than relying on pytest
  auto-detection, because #1022's acceptance names the explicit
  constructor kwarg as the API surface under regression.
- The model/table name is uniquified per test for isolation
  (`rules/testing.md` § Rules — isolated DBs).

Tier 2 (real PostgreSQL, NO mocking) per `rules/testing.md`
§ "3-Tier Testing". Skips cleanly when the shared PG infra on port
5434 is unreachable.
"""

from __future__ import annotations

import time
import uuid

import pytest
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from dataflow import DataFlow
from tests.infrastructure.test_harness import IntegrationTestSuite

pytestmark = [pytest.mark.regression, pytest.mark.integration]


@pytest.fixture
async def pg_test_suite():
    """IntegrationTestSuite against real Postgres (port 5434).

    Skips cleanly when the shared SDK Docker infra is unreachable —
    matches the integration-tier canonical-harness behavior.
    """
    suite = IntegrationTestSuite()
    try:
        async with suite.session():
            yield suite
    except Exception as exc:  # pragma: no cover - infra-availability guard
        pytest.skip(
            f"Cannot reach PostgreSQL test infra: {type(exc).__name__}: {exc}. "
            f"Ensure shared SDK Docker is running on port 5434."
        )


async def test_readme_tdd_mode_quickstart_executes_end_to_end(pg_test_suite):
    """DOCS-EXACT: DataFlow(tdd_mode=True) + @db.model + WorkflowBuilder
    + AsyncLocalRuntime executes end-to-end against real Postgres and the
    created record is both returned AND persisted (read-back verified).

    Pipeline mirrors ADR-017 § 2.1 (the Recommended test-mode pattern).
    """
    # Unique model/table for isolation (rules/testing.md § Rules).
    suffix = f"{int(time.time() * 1_000_000)}{uuid.uuid4().hex[:6]}"
    model_name = f"QuickstartUser{suffix}"

    # ---- DOCS-EXACT pipeline (ADR-017 § 2.1) -----------------------
    # tdd_mode=True passed explicitly (issue #1022 API surface);
    # URL from the real-PG harness (tests/CLAUDE.md mandate).
    db = DataFlow(pg_test_suite.config.url, tdd_mode=True)
    try:
        UserModel = type(
            model_name,
            (),
            {
                "__annotations__": {"id": str, "name": str},
            },
        )
        db.model(UserModel)

        await db.initialize()

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{model_name}CreateNode",
            "create",
            {"id": "user-1", "name": "Alice"},
        )

        runtime = AsyncLocalRuntime()
        # `inputs` is a REQUIRED parameter of execute_workflow_async (no
        # default). ADR-017 § 2.1 omitted it (doc bug — fixed in the same
        # commit as this regression); the canonical call per the repo
        # CLAUDE.md § Critical Execution Rules passes `inputs={}`.
        results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

        # Final user-visible outcome (ADR-017 § 2.1's own assertion shape).
        assert results["create"]["name"] == "Alice", (
            f"TDD-mode quick-start regression: CreateNode returned "
            f"{results.get('create')!r}; docs-taught pipeline broken."
        )
        assert results["create"]["id"] == "user-1"

        # Read-back verification — the record actually persisted, not
        # just echoed by the node (rules/testing.md § State Persistence
        # Verification). Independent read via the express surface.
        persisted = await db.express.read(model_name, "user-1")
        assert persisted is not None, (
            "TDD-mode quick-start regression: record not persisted — "
            "CreateNode returned success but read-back found nothing."
        )
        assert persisted["name"] == "Alice"
    finally:
        await db.close_async()
