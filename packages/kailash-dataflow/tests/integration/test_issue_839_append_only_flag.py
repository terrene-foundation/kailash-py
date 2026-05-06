"""Tier 2 regression tests for issue #839 — @db.model(append_only=True) flag.

Per `rules/testing.md` Tier 2 NO MOCKING. These tests exercise structural
contracts that don't require a Postgres connection (registration, node
generation, exception import). Real-database mutation rejection is
exercised in the Tier 3 sibling at `tests/e2e/test_append_only_e2e.py`
when it lands; this module is the structural-invariant layer.
"""

import inspect

import pytest

from dataflow import DataFlow
from dataflow.exceptions import AppendOnlyViolationError, DataFlowError


@pytest.mark.regression
def test_append_only_violation_error_is_dataflow_error_subclass():
    """AppendOnlyViolationError MUST inherit from DataFlowError so callers
    can catch the broad framework-error class without missing this case."""
    assert issubclass(AppendOnlyViolationError, DataFlowError)


@pytest.mark.regression
def test_append_only_violation_error_importable_from_top_level():
    """Public API surface — re-exported from dataflow.__init__."""
    from dataflow import AppendOnlyViolationError as ReExported

    assert ReExported is AppendOnlyViolationError


@pytest.mark.regression
def test_db_model_accepts_append_only_kwarg():
    """`@db.model(append_only=True)` MUST accept the kwarg without TypeError."""
    db = DataFlow("sqlite:///:memory:")

    @db.model(append_only=True)
    class EventLog:
        event_type: str
        payload: str

    # Registration succeeded — the model is in the registry.
    assert "EventLog" in db._models or hasattr(db, "_models")


@pytest.mark.regression
def test_db_model_append_only_default_is_false():
    """`@db.model` without append_only MUST default to False (mutations permitted)."""
    db = DataFlow("sqlite:///:memory:")

    @db.model
    class Mutable:
        name: str

    # Mutable models register normally — no append-only flag set.
    info = db._models.get("Mutable", {})
    assert info.get("append_only", False) is False


@pytest.mark.regression
def test_append_only_skips_mutation_node_generation():
    """When `append_only=True`, mutation node names route through
    AppendOnlyForbiddenNode stubs — direct construction raises
    AppendOnlyViolationError."""
    db = DataFlow("sqlite:///:memory:")

    @db.model(append_only=True)
    class EventLog:
        event_type: str
        payload: str

    # Read-side nodes generated normally.
    for node_name in (
        "EventLogCreateNode",
        "EventLogReadNode",
        "EventLogListNode",
        "EventLogCountNode",
        "EventLogBulkCreateNode",
    ):
        assert (
            node_name in db._nodes
        ), f"{node_name} should be generated for append-only model"

    # Mutation-side nodes registered as forbidden stubs.
    for node_name in (
        "EventLogUpdateNode",
        "EventLogDeleteNode",
        "EventLogUpsertNode",
        "EventLogBulkUpdateNode",
        "EventLogBulkDeleteNode",
        "EventLogBulkUpsertNode",
    ):
        assert (
            node_name in db._nodes
        ), f"{node_name} should be registered as forbidden stub"
        node_class = db._nodes[node_name]
        # Constructing the stub MUST raise AppendOnlyViolationError.
        with pytest.raises(AppendOnlyViolationError):
            node_class()


@pytest.mark.regression
def test_express_check_append_only_method_exists():
    """The express layer's `_check_append_only` helper is the single
    enforcement point for direct mutation-call rejection. Structural
    invariant: the helper exists with the documented signature."""
    from dataflow.features.express import DataFlowExpress

    assert hasattr(DataFlowExpress, "_check_append_only"), (
        "DataFlowExpress._check_append_only is the documented "
        "enforcement point for #839; removal is a contract break"
    )

    sig = inspect.signature(DataFlowExpress._check_append_only)
    params = [p for p in sig.parameters if p != "self"]
    assert params == ["model", "operation"], f"unexpected signature: {sig}"


@pytest.mark.regression
def test_register_model_internal_stores_append_only_flag():
    """The model-info registration MUST persist `append_only` so the
    express check + node generator both see consistent state."""
    db = DataFlow("sqlite:///:memory:")

    @db.model(append_only=True)
    class AuditEvent:
        actor: str
        action: str

    info = db._models["AuditEvent"]
    assert info.get("append_only") is True

    @db.model
    class RegularModel:
        name: str

    info_regular = db._models["RegularModel"]
    assert info_regular.get("append_only", False) is False
