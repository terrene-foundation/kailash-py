"""Tests for /plan command wired to GovernedSupervisor.

Covers:
- _plan_handler: usage message, preview mode, supervisor context, last_result display
- _plan_preview: plan preview formatting
- _format_plan: ASCII plan rendering from SupervisorResult
"""

from __future__ import annotations

import pytest

from kaizen_agents.delegate.builtins import _plan_handler, _format_plan, _plan_preview
from kaizen_agents.types import (
    AgentSpec,
    Plan,
    PlanNode,
    PlanNodeState,
)


# ---------------------------------------------------------------------------
# _plan_handler
# ---------------------------------------------------------------------------


class TestPlanHandler:
    """Test the /plan command handler dispatch logic."""

    def test_no_args_returns_usage(self):
        result = _plan_handler("")
        assert "Usage:" in result

    def test_no_supervisor_returns_preview(self):
        result = _plan_handler("analyze codebase", model="gpt-4o")
        assert "Plan preview" in result
        assert "analyze codebase" in result

    def test_no_supervisor_preview_includes_model(self):
        result = _plan_handler("analyze codebase", model="gpt-4o")
        assert "gpt-4o" in result

    def test_no_supervisor_preview_shows_configuration_hint(self):
        result = _plan_handler("analyze codebase", model="gpt-4o")
        assert "GovernedSupervisor" in result

    def test_with_supervisor_no_result(self):
        class FakeSupervisor:
            _model = "test-model"

        result = _plan_handler("test objective", supervisor=FakeSupervisor())
        assert "test-model" in result or "Plan" in result

    def test_with_supervisor_and_last_result_shows_plan(self):
        spec = AgentSpec(
            spec_id="s1",
            name="task1",
            description="Do the thing",
        )
        node = PlanNode(
            node_id="node1",
            agent_spec=spec,
            state=PlanNodeState.COMPLETED,
            output={"result": "done"},
        )
        plan = Plan(nodes={"node1": node}, edges=[])

        class FakeResult:
            success = True
            plan = None  # will be set below

        fake_result = FakeResult()
        fake_result.plan = plan

        class FakeSupervisor:
            _model = "test-model"

        result = _plan_handler(
            "do something",
            supervisor=FakeSupervisor(),
            last_result=fake_result,
        )
        assert "[done]" in result
        assert "1/1 completed" in result

    def test_with_supervisor_and_no_plan_in_result(self):
        class FakeSupervisor:
            _model = "test-model"

        class FakeResultNoPlan:
            success = True
            plan = None

        result = _plan_handler(
            "do something",
            supervisor=FakeSupervisor(),
            last_result=FakeResultNoPlan(),
        )
        # Should fall through to the info message (no plan to format)
        assert "test-model" in result or "Plan created" in result


# ---------------------------------------------------------------------------
# _plan_preview
# ---------------------------------------------------------------------------


class TestPlanPreview:
    """Test plan preview when no supervisor is configured."""

    def test_preview_includes_objective(self):
        output = _plan_preview("build a web app", {"model": "gpt-4o"})
        assert "build a web app" in output

    def test_preview_includes_model(self):
        output = _plan_preview("analyze code", {"model": "claude-sonnet"})
        assert "claude-sonnet" in output

    def test_preview_includes_configuration_hint(self):
        output = _plan_preview("test", {"model": "gpt-4o"})
        assert "GovernedSupervisor" in output

    def test_preview_with_no_model_in_context(self):
        output = _plan_preview("test", {})
        assert "unknown" in output


# ---------------------------------------------------------------------------
# _format_plan
# ---------------------------------------------------------------------------


class TestFormatPlan:
    """Test ASCII plan rendering from SupervisorResult-like objects."""

    def test_format_empty_plan(self):
        class FakeResult:
            success = True
            plan = Plan(nodes={}, edges=[])

        output = _format_plan(FakeResult())
        assert "0 nodes" in output or "0/" in output
        assert "SUCCESS" in output

    def test_format_plan_with_completed_node(self):
        spec = AgentSpec(
            spec_id="s1",
            name="task1",
            description="Test task",
        )
        node = PlanNode(
            node_id="node1",
            agent_spec=spec,
            state=PlanNodeState.COMPLETED,
            output={"result": "done"},
        )

        class FakeResult:
            success = True
            plan = Plan(nodes={"node1": node}, edges=[])

        output = _format_plan(FakeResult())
        assert "[done]" in output
        assert "1/1 completed" in output
        assert "SUCCESS" in output

    def test_format_plan_with_failed_node(self):
        spec = AgentSpec(
            spec_id="s2",
            name="failing-task",
            description="This will fail",
        )
        node = PlanNode(
            node_id="fail1",
            agent_spec=spec,
            state=PlanNodeState.FAILED,
            error="Connection timeout",
        )

        class FakeResult:
            success = False
            plan = Plan(nodes={"fail1": node}, edges=[])

        output = _format_plan(FakeResult())
        assert "[FAIL]" in output
        assert "Connection timeout" in output
        assert "INCOMPLETE" in output
        assert "1 failed" in output

    def test_format_plan_with_held_node(self):
        spec = AgentSpec(
            spec_id="s3",
            name="held-task",
            description="Awaiting approval",
        )
        node = PlanNode(
            node_id="held1",
            agent_spec=spec,
            state=PlanNodeState.HELD,
        )

        class FakeResult:
            success = False
            plan = Plan(nodes={"held1": node}, edges=[])

        output = _format_plan(FakeResult())
        assert "[HELD]" in output
        assert "Awaiting approval" in output  # from status line
        assert "1 held" in output

    def test_format_plan_with_pending_node(self):
        spec = AgentSpec(
            spec_id="s4",
            name="pending-task",
            description="Not started",
        )
        node = PlanNode(
            node_id="pend1",
            agent_spec=spec,
            state=PlanNodeState.PENDING,
        )

        class FakeResult:
            success = False
            plan = Plan(nodes={"pend1": node}, edges=[])

        output = _format_plan(FakeResult())
        assert "[    ]" in output
        assert "0/1 completed" in output

    def test_format_plan_mixed_states(self):
        spec_done = AgentSpec(spec_id="sd", name="done", description="Step 1")
        spec_fail = AgentSpec(spec_id="sf", name="fail", description="Step 2")
        spec_held = AgentSpec(spec_id="sh", name="held", description="Step 3")

        nodes = {
            "n1": PlanNode(
                node_id="n1", agent_spec=spec_done, state=PlanNodeState.COMPLETED, output="ok"
            ),
            "n2": PlanNode(
                node_id="n2", agent_spec=spec_fail, state=PlanNodeState.FAILED, error="boom"
            ),
            "n3": PlanNode(node_id="n3", agent_spec=spec_held, state=PlanNodeState.HELD),
        }

        class FakeResult:
            success = False
            plan = Plan(nodes=nodes, edges=[])

        output = _format_plan(FakeResult())
        assert "3 nodes" in output or "3)" in output
        assert "1/3 completed" in output
        assert "1 failed" in output
        assert "1 held" in output
        assert "INCOMPLETE" in output

    def test_format_plan_output_preview_truncated(self):
        """Long output should be truncated in the preview."""
        spec = AgentSpec(spec_id="sl", name="long-output", description="Big result")
        long_output = "x" * 200
        node = PlanNode(
            node_id="long1",
            agent_spec=spec,
            state=PlanNodeState.COMPLETED,
            output=long_output,
        )

        class FakeResult:
            success = True
            plan = Plan(nodes={"long1": node}, edges=[])

        output = _format_plan(FakeResult())
        # The output preview should be truncated to 80 chars
        lines = output.split("\n")
        preview_lines = [l for l in lines if "->" in l]
        assert len(preview_lines) == 1
        # The preview should not contain the full 200-char string
        assert long_output not in output

    def test_format_plan_uses_description_from_agent_spec(self):
        spec = AgentSpec(
            spec_id="sd",
            name="desc-task",
            description="Analyze the repository structure",
        )
        node = PlanNode(
            node_id="desc1",
            agent_spec=spec,
            state=PlanNodeState.PENDING,
        )

        class FakeResult:
            success = False
            plan = Plan(nodes={"desc1": node}, edges=[])

        output = _format_plan(FakeResult())
        assert "Analyze the repository structure" in output
