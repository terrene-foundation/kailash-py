# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""Tests for PactEngine -- Dual Plane bridge for governed agent execution.

Tests follow TDD: written BEFORE implementation. Tests define the expected
behavior of PactEngine, WorkSubmission, WorkResult, CostTracker, and EventBus.

Covers:
- Construction from YAML path and dict
- Property access (governance, costs, events)
- Budget validation (NaN, Inf, negative)
- Submit without kaizen-agents returns error
- Sync convenience wrapper
- EventBus subscribe/emit and bounded history
- CostTracker record/spent/remaining/utilization
- WorkResult construction and from_dict
- WorkSubmission construction
"""

from __future__ import annotations

import asyncio
import math
from pathlib import Path
from typing import Any

import pytest

from pact.engine import PactEngine
from pact.work import WorkResult, WorkSubmission
from pact.costs import CostTracker
from pact.events import EventBus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "governance" / "fixtures"


@pytest.fixture
def minimal_yaml_path() -> Path:
    """Path to the minimal org YAML fixture."""
    return FIXTURES_DIR / "minimal-org.yaml"


@pytest.fixture
def minimal_org_dict() -> dict[str, Any]:
    """Minimal org definition as a dict (matching minimal-org.yaml)."""
    return {
        "org_id": "test-minimal-001",
        "name": "Minimal Test Org",
        "departments": [{"id": "d-engineering", "name": "Engineering"}],
        "teams": [{"id": "t-backend", "name": "Backend Team"}],
        "roles": [
            {"id": "r-cto", "name": "CTO", "heads": "d-engineering"},
            {
                "id": "r-lead",
                "name": "Tech Lead",
                "reports_to": "r-cto",
                "heads": "t-backend",
            },
            {"id": "r-dev", "name": "Developer", "reports_to": "r-lead"},
        ],
    }


@pytest.fixture
def engine_from_yaml(minimal_yaml_path: Path) -> PactEngine:
    """PactEngine constructed from a YAML file path."""
    return PactEngine(org=str(minimal_yaml_path))


@pytest.fixture
def engine_from_dict(minimal_org_dict: dict[str, Any]) -> PactEngine:
    """PactEngine constructed from a dict."""
    return PactEngine(org=minimal_org_dict)


# ---------------------------------------------------------------------------
# PactEngine Construction Tests
# ---------------------------------------------------------------------------


class TestPactEngineConstruction:
    """PactEngine construction from various org sources."""

    def test_create_engine_with_yaml_path(self, minimal_yaml_path: Path) -> None:
        """PactEngine should accept a string path to a YAML file."""
        engine = PactEngine(org=str(minimal_yaml_path))
        assert engine.governance is not None
        assert engine.governance.org_name == "Minimal Test Org"

    def test_create_engine_with_path_object(self, minimal_yaml_path: Path) -> None:
        """PactEngine should accept a Path object to a YAML file."""
        engine = PactEngine(org=minimal_yaml_path)
        assert engine.governance is not None
        assert engine.governance.org_name == "Minimal Test Org"

    def test_create_engine_with_dict(self, minimal_org_dict: dict[str, Any]) -> None:
        """PactEngine should accept a dict org definition."""
        engine = PactEngine(org=minimal_org_dict)
        assert engine.governance is not None
        assert engine.governance.org_name == "Minimal Test Org"

    def test_create_engine_with_model(self, minimal_yaml_path: Path) -> None:
        """PactEngine should store the model parameter."""
        engine = PactEngine(org=str(minimal_yaml_path), model="claude-sonnet-4-6")
        assert engine.model == "claude-sonnet-4-6"

    def test_create_engine_with_budget(self, minimal_yaml_path: Path) -> None:
        """PactEngine should configure budget via costs tracker."""
        engine = PactEngine(org=str(minimal_yaml_path), budget_usd=50.0)
        assert engine.costs is not None
        assert engine.costs.remaining == 50.0

    def test_create_engine_with_clearance(self, minimal_yaml_path: Path) -> None:
        """PactEngine should accept a clearance level string."""
        engine = PactEngine(org=str(minimal_yaml_path), clearance="confidential")
        assert engine.clearance == "confidential"

    def test_create_engine_default_clearance(self, minimal_yaml_path: Path) -> None:
        """PactEngine should default to 'restricted' clearance."""
        engine = PactEngine(org=str(minimal_yaml_path))
        assert engine.clearance == "restricted"

    def test_create_engine_invalid_org_path(self) -> None:
        """PactEngine should raise an error for a nonexistent YAML path."""
        with pytest.raises(Exception):
            PactEngine(org="/nonexistent/path/org.yaml")


# ---------------------------------------------------------------------------
# Property Tests
# ---------------------------------------------------------------------------


class TestPactEngineProperties:
    """PactEngine property access."""

    def test_governance_property_returns_engine(
        self, engine_from_yaml: PactEngine
    ) -> None:
        """The governance property should return the underlying GovernanceEngine."""
        from kailash.trust.pact.engine import GovernanceEngine

        gov = engine_from_yaml.governance
        assert isinstance(gov, GovernanceEngine)

    def test_costs_property_returns_tracker(self, engine_from_yaml: PactEngine) -> None:
        """The costs property should return a CostTracker."""
        costs = engine_from_yaml.costs
        assert isinstance(costs, CostTracker)

    def test_events_property_returns_bus(self, engine_from_yaml: PactEngine) -> None:
        """The events property should return an EventBus."""
        events = engine_from_yaml.events
        assert isinstance(events, EventBus)


# ---------------------------------------------------------------------------
# Budget Validation Tests
# ---------------------------------------------------------------------------


class TestBudgetValidation:
    """NaN, Inf, and negative budget rejection (per pact-governance.md rule 6)."""

    def test_nan_budget_rejected(self, minimal_yaml_path: Path) -> None:
        """PactEngine should reject NaN budget_usd."""
        with pytest.raises(ValueError, match="budget_usd must be finite"):
            PactEngine(org=str(minimal_yaml_path), budget_usd=float("nan"))

    def test_inf_budget_rejected(self, minimal_yaml_path: Path) -> None:
        """PactEngine should reject Inf budget_usd."""
        with pytest.raises(ValueError, match="budget_usd must be finite"):
            PactEngine(org=str(minimal_yaml_path), budget_usd=float("inf"))

    def test_negative_inf_budget_rejected(self, minimal_yaml_path: Path) -> None:
        """PactEngine should reject -Inf budget_usd."""
        with pytest.raises(ValueError, match="budget_usd must be finite"):
            PactEngine(org=str(minimal_yaml_path), budget_usd=float("-inf"))

    def test_negative_budget_rejected(self, minimal_yaml_path: Path) -> None:
        """PactEngine should reject negative budget_usd."""
        with pytest.raises(
            ValueError, match="budget_usd must be finite and non-negative"
        ):
            PactEngine(org=str(minimal_yaml_path), budget_usd=-10.0)

    def test_zero_budget_accepted(self, minimal_yaml_path: Path) -> None:
        """PactEngine should accept zero budget_usd (valid edge case)."""
        engine = PactEngine(org=str(minimal_yaml_path), budget_usd=0.0)
        assert engine.costs.remaining == 0.0


# ---------------------------------------------------------------------------
# Submit Tests
# ---------------------------------------------------------------------------


class TestSubmit:
    """PactEngine.submit() and submit_sync() behavior."""

    def test_submit_without_kaizen_returns_error(self, minimal_yaml_path: Path) -> None:
        """submit() without kaizen-agents installed should return error WorkResult."""
        from unittest.mock import patch

        # Create a fresh engine so _supervisor is None
        engine = PactEngine(org=str(minimal_yaml_path))

        # Patch the import inside _get_or_create_supervisor to simulate
        # kaizen-agents not being installed
        original_import = (
            __builtins__.__import__
            if hasattr(__builtins__, "__import__")
            else __import__
        )

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "kaizen_agents.supervisor":
                raise ImportError("No module named 'kaizen_agents'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = asyncio.run(engine.submit("Analyze Q3 data", role="D1-R1"))
        assert isinstance(result, WorkResult)
        # Without kaizen-agents supervisor, should indicate failure
        # but not raise an exception -- fail-closed with informative error
        assert result.success is False
        assert result.error is not None
        assert len(result.error) > 0
        assert "kaizen" in result.error.lower()

    def test_submit_sync_convenience(self, minimal_yaml_path: Path) -> None:
        """submit_sync() should be a synchronous wrapper around submit()."""
        from unittest.mock import patch

        engine = PactEngine(org=str(minimal_yaml_path))

        original_import = (
            __builtins__.__import__
            if hasattr(__builtins__, "__import__")
            else __import__
        )

        def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
            if name == "kaizen_agents.supervisor":
                raise ImportError("No module named 'kaizen_agents'")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=mock_import):
            result = engine.submit_sync("Analyze Q3 data", role="D1-R1")
        assert isinstance(result, WorkResult)
        # Same behavior as async version -- without kaizen, returns error
        assert result.success is False
        assert result.error is not None

    def test_submit_emits_events(self, engine_from_yaml: PactEngine) -> None:
        """submit() should emit events to the event bus."""
        result = engine_from_yaml.submit_sync("Test task", role="D1-R1")
        history = engine_from_yaml.events.get_history()
        # At minimum, a submission event should have been emitted
        assert len(history) > 0

    def test_submit_with_invalid_role_returns_blocked(
        self, engine_from_yaml: PactEngine
    ) -> None:
        """submit() with an invalid role should return blocked WorkResult (fail-closed)."""
        result = engine_from_yaml.submit_sync("Some task", role="NONEXISTENT-ROLE")
        assert isinstance(result, WorkResult)
        assert result.success is False


# ---------------------------------------------------------------------------
# EventBus Tests
# ---------------------------------------------------------------------------


class TestEventBus:
    """EventBus subscribe, emit, and history management."""

    def test_event_bus_subscribe_emit(self) -> None:
        """EventBus should deliver events to subscribers."""
        bus = EventBus()
        received: list[dict[str, Any]] = []
        bus.subscribe("test_event", lambda data: received.append(data))
        bus.emit("test_event", {"key": "value"})
        assert len(received) == 1
        assert received[0]["key"] == "value"

    def test_event_bus_multiple_subscribers(self) -> None:
        """EventBus should deliver events to all subscribers of a type."""
        bus = EventBus()
        received_a: list[dict] = []
        received_b: list[dict] = []
        bus.subscribe("test_event", lambda data: received_a.append(data))
        bus.subscribe("test_event", lambda data: received_b.append(data))
        bus.emit("test_event", {"key": "value"})
        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_event_bus_no_cross_talk(self) -> None:
        """Events of one type should not trigger subscribers of another type."""
        bus = EventBus()
        received: list[dict] = []
        bus.subscribe("type_a", lambda data: received.append(data))
        bus.emit("type_b", {"key": "value"})
        assert len(received) == 0

    def test_event_bus_get_history(self) -> None:
        """get_history() should return all events or filtered by type."""
        bus = EventBus()
        bus.emit("type_a", {"a": 1})
        bus.emit("type_b", {"b": 2})
        bus.emit("type_a", {"a": 3})

        all_events = bus.get_history()
        assert len(all_events) == 3

        type_a_events = bus.get_history(event_type="type_a")
        assert len(type_a_events) == 2
        assert all(e["event_type"] == "type_a" for e in type_a_events)

    def test_event_bus_bounded_history(self) -> None:
        """EventBus should enforce maxlen on history (per trust-plane-security.md rule 4)."""
        bus = EventBus(maxlen=10)
        for i in range(20):
            bus.emit("test", {"i": i})
        history = bus.get_history()
        assert len(history) <= 10
        # Oldest events should be evicted -- most recent should be present
        assert history[-1]["data"]["i"] == 19

    def test_event_bus_default_maxlen(self) -> None:
        """EventBus default maxlen should be 10000."""
        bus = EventBus()
        # We just verify it was constructed -- testing 10000 items would be slow
        assert bus._maxlen == 10000


# ---------------------------------------------------------------------------
# CostTracker Tests
# ---------------------------------------------------------------------------


class TestCostTracker:
    """CostTracker record, spent, remaining, utilization."""

    def test_cost_tracker_record(self) -> None:
        """CostTracker should track recorded costs."""
        tracker = CostTracker(budget_usd=100.0)
        tracker.record(10.0, "test operation")
        assert tracker.spent == 10.0

    def test_cost_tracker_multiple_records(self) -> None:
        """CostTracker should accumulate multiple records."""
        tracker = CostTracker(budget_usd=100.0)
        tracker.record(10.0, "op 1")
        tracker.record(20.0, "op 2")
        tracker.record(5.0, "op 3")
        assert tracker.spent == 35.0

    def test_cost_tracker_remaining(self) -> None:
        """remaining should return budget minus spent."""
        tracker = CostTracker(budget_usd=100.0)
        tracker.record(30.0)
        assert tracker.remaining == 70.0

    def test_cost_tracker_remaining_none_without_budget(self) -> None:
        """remaining should be None when no budget is configured."""
        tracker = CostTracker()
        tracker.record(10.0)
        assert tracker.remaining is None

    def test_cost_tracker_utilization(self) -> None:
        """utilization should return spent / budget as a fraction."""
        tracker = CostTracker(budget_usd=100.0)
        tracker.record(25.0)
        assert tracker.utilization == pytest.approx(0.25)

    def test_cost_tracker_utilization_none_without_budget(self) -> None:
        """utilization should be None when no budget is configured."""
        tracker = CostTracker()
        assert tracker.utilization is None

    def test_cost_tracker_history(self) -> None:
        """CostTracker should maintain a history of records."""
        tracker = CostTracker(budget_usd=100.0)
        tracker.record(10.0, "first")
        tracker.record(20.0, "second")
        assert len(tracker.history) == 2
        assert tracker.history[0]["amount"] == 10.0
        assert tracker.history[0]["description"] == "first"
        assert tracker.history[1]["amount"] == 20.0

    def test_cost_tracker_nan_record_rejected(self) -> None:
        """CostTracker should reject NaN cost amounts."""
        tracker = CostTracker(budget_usd=100.0)
        with pytest.raises(ValueError, match="must be finite"):
            tracker.record(float("nan"))

    def test_cost_tracker_inf_record_rejected(self) -> None:
        """CostTracker should reject Inf cost amounts."""
        tracker = CostTracker(budget_usd=100.0)
        with pytest.raises(ValueError, match="must be finite"):
            tracker.record(float("inf"))

    def test_cost_tracker_negative_record_rejected(self) -> None:
        """CostTracker should reject negative cost amounts."""
        tracker = CostTracker(budget_usd=100.0)
        with pytest.raises(ValueError, match="must be finite and non-negative"):
            tracker.record(-5.0)

    def test_cost_tracker_nan_budget_rejected(self) -> None:
        """CostTracker should reject NaN budget."""
        with pytest.raises(ValueError, match="budget_usd must be finite"):
            CostTracker(budget_usd=float("nan"))

    def test_cost_tracker_with_cost_model(self) -> None:
        """CostTracker should accept an optional CostModel."""
        from kaizen_agents.governance.cost_model import CostModel

        model = CostModel()
        tracker = CostTracker(budget_usd=100.0, cost_model=model)
        assert tracker.cost_model is model


# ---------------------------------------------------------------------------
# WorkResult Tests
# ---------------------------------------------------------------------------


class TestWorkResult:
    """WorkResult data class."""

    def test_work_result_defaults(self) -> None:
        """WorkResult should have sensible defaults."""
        result = WorkResult(success=True)
        assert result.success is True
        assert result.results == {}
        assert result.cost_usd == 0.0
        assert result.events == []
        assert result.error is None

    def test_work_result_with_error(self) -> None:
        """WorkResult should carry an error message."""
        result = WorkResult(success=False, error="Something went wrong")
        assert result.success is False
        assert result.error == "Something went wrong"

    def test_work_result_from_dict(self) -> None:
        """WorkResult.from_dict() should reconstruct from a dict."""
        data = {
            "success": True,
            "results": {"task-0": "Analysis complete"},
            "cost_usd": 0.42,
            "events": [{"type": "completed"}],
            "error": None,
        }
        result = WorkResult.from_dict(data)
        assert result.success is True
        assert result.results == {"task-0": "Analysis complete"}
        assert result.cost_usd == pytest.approx(0.42)
        assert len(result.events) == 1
        assert result.error is None

    def test_work_result_to_dict(self) -> None:
        """WorkResult.to_dict() should serialize to a dict."""
        result = WorkResult(
            success=True,
            results={"key": "value"},
            cost_usd=1.23,
            events=[{"type": "done"}],
        )
        data = result.to_dict()
        assert data["success"] is True
        assert data["results"] == {"key": "value"}
        assert data["cost_usd"] == pytest.approx(1.23)


# ---------------------------------------------------------------------------
# WorkSubmission Tests
# ---------------------------------------------------------------------------


class TestWorkSubmission:
    """WorkSubmission data class."""

    def test_work_submission_construction(self) -> None:
        """WorkSubmission should capture objective, role, and context."""
        sub = WorkSubmission(
            objective="Analyze Q3 data",
            role="D1-R1",
            context={"quarter": "Q3"},
        )
        assert sub.objective == "Analyze Q3 data"
        assert sub.role == "D1-R1"
        assert sub.context == {"quarter": "Q3"}

    def test_work_submission_defaults(self) -> None:
        """WorkSubmission should have sensible defaults."""
        sub = WorkSubmission(objective="Task", role="D1-R1")
        assert sub.context == {}
        assert sub.budget_usd is None

    def test_work_submission_frozen(self) -> None:
        """WorkSubmission should be immutable (frozen dataclass)."""
        sub = WorkSubmission(objective="Task", role="D1-R1")
        with pytest.raises(AttributeError):
            sub.objective = "Changed"  # type: ignore[misc]
