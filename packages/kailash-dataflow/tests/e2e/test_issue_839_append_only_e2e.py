"""End-to-end tests for issue #839 — @db.model(append_only=True) flag.

Tier 3 (E2E) regression covering the append-only contract against real
Postgres infrastructure. Sibling of the Tier 2 structural tests at
`tests/integration/test_issue_839_append_only_flag.py` — this file
exercises the actual database surface so the rejection-before-SQL
contract is observable end-to-end.

Coverage:

1. Successful Create / Read / List / Count against an append-only
   model registered against real Postgres.
2. Every express mutation method (`update`, `delete`, `upsert`,
   `bulk_update`, `bulk_delete`, `bulk_upsert`) raises
   `AppendOnlyViolationError` BEFORE any SQL is executed against
   Postgres — verified by asserting the underlying row count is
   unchanged after each rejection.
3. Workflow-builder `add_node("<Model>UpdateNode", ...)` raises
   `AppendOnlyViolationError` at construction, against the real
   DataFlow node registry.
4. Mutable models (default `append_only=False`) operate normally
   against the same Postgres instance — invariant proves the
   feature is gated, not globally applied.

Per `rules/testing.md` Tier 3 NO MOCKING and `rules/build-repo-release-discipline.md`
End-to-End Pipeline Regression — required before the kailash-dataflow 2.8.0
release that ships #839 as a public API.
"""

from __future__ import annotations

import pytest

from tests.infrastructure.test_harness import IntegrationTestSuite


@pytest.fixture
async def test_suite():
    """Create complete E2E test suite with real Postgres infrastructure."""
    suite = IntegrationTestSuite()
    async with suite.session():
        yield suite


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_append_only_create_read_list_count_succeed_against_postgres(test_suite):
    """Read-side operations on an append-only model work normally
    against real Postgres — the append-only flag MUST NOT regress
    the supported operations."""
    from dataflow import DataFlow

    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model(append_only=True)
    class EventLogE2ECrud:
        event_type: str
        payload: str

    await db.initialize()

    created = await db.express.create(
        "EventLogE2ECrud",
        {"event_type": "login", "payload": "user-42 logged in"},
    )
    assert created["id"] is not None
    event_id = created["id"]

    fetched = await db.express.read("EventLogE2ECrud", event_id)
    assert fetched["event_type"] == "login"
    assert fetched["payload"] == "user-42 logged in"

    await db.express.create(
        "EventLogE2ECrud",
        {"event_type": "logout", "payload": "user-42 logged out"},
    )

    listed = await db.express.list("EventLogE2ECrud", {})
    assert len(listed) >= 2

    count = await db.express.count("EventLogE2ECrud", {})
    assert count >= 2


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_append_only_express_mutation_methods_raise_before_sql(test_suite):
    """Every express mutation method MUST raise AppendOnlyViolationError
    BEFORE any SQL is dispatched against Postgres. The row count after
    each rejection MUST equal the row count before — proving the
    rejection is pre-SQL, not post-rollback."""
    from dataflow import DataFlow
    from dataflow.exceptions import AppendOnlyViolationError

    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model(append_only=True)
    class EventLogE2EMutation:
        event_type: str
        payload: str

    await db.initialize()

    # Postgres tables persist across runs; capture the pre-seed count
    # and assert the seed adds exactly one row. The post-mutation
    # invariant is "count never moves from baseline" — robust to prior
    # test residue.
    pre_seed_count = await db.express.count("EventLogE2EMutation", {})

    seed = await db.express.create(
        "EventLogE2EMutation",
        {"event_type": "seed", "payload": "initial event"},
    )
    seed_id = seed["id"]

    baseline_count = await db.express.count("EventLogE2EMutation", {})
    assert baseline_count == pre_seed_count + 1

    # Each mutation method MUST raise; row count MUST NOT change.
    with pytest.raises(AppendOnlyViolationError):
        await db.express.update("EventLogE2EMutation", seed_id, {"payload": "tampered"})
    assert await db.express.count("EventLogE2EMutation", {}) == baseline_count

    with pytest.raises(AppendOnlyViolationError):
        await db.express.delete("EventLogE2EMutation", seed_id)
    assert await db.express.count("EventLogE2EMutation", {}) == baseline_count

    with pytest.raises(AppendOnlyViolationError):
        await db.express.upsert(
            "EventLogE2EMutation",
            {"id": seed_id, "event_type": "seed", "payload": "tampered"},
        )
    assert await db.express.count("EventLogE2EMutation", {}) == baseline_count

    # bulk_update signature: records list with key_field (default "id");
    # remaining fields are the values to set.
    with pytest.raises(AppendOnlyViolationError):
        await db.express.bulk_update(
            "EventLogE2EMutation",
            [{"id": seed_id, "payload": "tampered"}],
        )
    assert await db.express.count("EventLogE2EMutation", {}) == baseline_count

    # bulk_delete signature: list of ids (cast to str for portability).
    with pytest.raises(AppendOnlyViolationError):
        await db.express.bulk_delete(
            "EventLogE2EMutation",
            [str(seed_id)],
        )
    assert await db.express.count("EventLogE2EMutation", {}) == baseline_count

    with pytest.raises(AppendOnlyViolationError):
        await db.express.bulk_upsert(
            "EventLogE2EMutation",
            [{"id": seed_id, "event_type": "seed", "payload": "tampered"}],
        )
    assert await db.express.count("EventLogE2EMutation", {}) == baseline_count

    # The seed row's payload MUST still be the original value — no
    # mutation slipped through any path.
    fetched = await db.express.read("EventLogE2EMutation", seed_id)
    assert fetched["payload"] == "initial event"


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_append_only_workflow_mutation_node_construction_raises(test_suite):
    """Mutation node classes for an append-only model MUST raise
    AppendOnlyViolationError on construction (the same point the
    Tier-2 sibling test asserts at
    ``tests/integration/test_issue_839_append_only_flag.py``).

    ``WorkflowBuilder.add_node("<NodeType>", "<id>", {...})`` with a
    string node-type stores a ``{"type": str, "config": dict}`` record
    and defers instantiation to ``workflow.build()`` — the rejection
    fires when the runtime instantiates the node class. We exercise
    that exact construction surface here so the SQL-emission gate is
    proven, and we additionally assert build-time rejection so
    ``WorkflowBuilder`` callers see the typed exception before any
    runtime is invoked."""
    from kailash.workflow.builder import WorkflowBuilder

    from dataflow import DataFlow
    from dataflow.exceptions import AppendOnlyViolationError

    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model(append_only=True)
    class EventLogE2EWorkflow:
        event_type: str
        payload: str

    await db.initialize()

    # Read-side construction: CreateNode is permitted.
    create_cls = db._nodes["EventLogE2EWorkflowCreateNode"]
    create_cls()  # MUST NOT raise.

    # Mutation-side: every mutation node class MUST raise on construction.
    for node_name in (
        "EventLogE2EWorkflowUpdateNode",
        "EventLogE2EWorkflowDeleteNode",
        "EventLogE2EWorkflowUpsertNode",
        "EventLogE2EWorkflowBulkUpdateNode",
        "EventLogE2EWorkflowBulkDeleteNode",
        "EventLogE2EWorkflowBulkUpsertNode",
    ):
        node_class = db._nodes[node_name]
        with pytest.raises(AppendOnlyViolationError):
            node_class()

    # WorkflowBuilder consumer surface: add_node stores the spec as a
    # dict and defers instantiation to build(). The rejection fires the
    # moment the runtime instantiates the class — Workflow.add_node's
    # exception handler wraps the underlying AppendOnlyViolationError
    # in NodeConfigurationError, and WorkflowBuilder.build re-wraps that
    # in WorkflowValidationError. The original typed error MUST survive
    # in the __cause__ chain so callers can introspect the rejection.
    workflow = WorkflowBuilder()
    workflow.add_node(
        "EventLogE2EWorkflowCreateNode",
        "create_event",
        {"event_type": "audit", "payload": "ok"},
    )
    workflow.add_node(
        "EventLogE2EWorkflowUpdateNode",
        "forbidden_update",
        {"filter": {"id": 1}, "fields": {"payload": "tampered"}},
    )

    with pytest.raises(Exception) as excinfo:
        workflow.build()

    # Walk the __cause__ chain and assert AppendOnlyViolationError is
    # the originating exception — the typed contract MUST surface even
    # through the framework's wrapping.
    chain = []
    err: BaseException | None = excinfo.value
    while err is not None and len(chain) < 8:
        chain.append(type(err).__name__)
        err = err.__cause__
    assert (
        "AppendOnlyViolationError" in chain
    ), f"AppendOnlyViolationError missing from __cause__ chain: {chain}"


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.timeout(30)
async def test_append_only_does_not_apply_to_default_models(test_suite):
    """Models registered without append_only=True (or with the default
    False) MUST permit mutation operations against the same Postgres
    instance — proves the feature is gated, not globally applied."""
    from dataflow import DataFlow

    db = DataFlow(test_suite.config.url, auto_migrate=True)

    @db.model
    class MutableRecordE2E:
        name: str
        value: int

    await db.initialize()

    created = await db.express.create(
        "MutableRecordE2E",
        {"name": "alpha", "value": 1},
    )
    record_id = created["id"]

    # Update is permitted on a non-append-only model.
    await db.express.update(
        "MutableRecordE2E",
        record_id,
        {"name": "alpha-updated", "value": 2},
    )

    fetched = await db.express.read("MutableRecordE2E", record_id)
    assert fetched["name"] == "alpha-updated"
    assert fetched["value"] == 2

    # Delete is permitted.
    await db.express.delete("MutableRecordE2E", record_id)
    assert await db.express.count("MutableRecordE2E", {"id": record_id}) == 0
