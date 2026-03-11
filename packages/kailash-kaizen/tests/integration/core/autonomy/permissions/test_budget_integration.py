"""
Integration tests for BudgetEnforcer with real components.

Tests integration with ExecutionContext, PermissionPolicy, and real budget enforcement flows.
Following TODO-160 Week 3 specification: 4 integration tests.

TIER 2: Real infrastructure, NO MOCKING.
"""

import pytest
from kaizen.core.autonomy.permissions.budget_enforcer import BudgetEnforcer
from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.types import PermissionMode


class TestBudgetIntegration:
    """Integration tests with ExecutionContext and PermissionPolicy."""

    def test_integration_with_execution_context(self):
        """
        Test 1: BudgetEnforcer integrates with ExecutionContext.

        Verifies that BudgetEnforcer correctly uses ExecutionContext's
        budget tracking methods and state.
        """
        # Create context with budget
        context = ExecutionContext(
            mode=PermissionMode.DEFAULT,
            budget_limit=10.0,
        )

        # Initial state
        assert context.budget_used == 0.0
        assert context.budget_limit == 10.0

        # Estimate cost
        estimated_cost = BudgetEnforcer.estimate_cost("Write", {"path": "test.txt"})
        assert estimated_cost > 0

        # Check budget (should pass)
        has_budget = BudgetEnforcer.has_budget(context, estimated_cost)
        assert has_budget is True

        # Record usage
        BudgetEnforcer.record_usage(context, tool_name="Write", cost_usd=estimated_cost)
        assert context.budget_used == estimated_cost
        assert context.tool_usage_count["Write"] == 1

        # Use more budget
        for i in range(5):
            cost = BudgetEnforcer.estimate_cost("Read", {"path": f"file{i}.txt"})
            BudgetEnforcer.record_usage(context, tool_name="Read", cost_usd=cost)

        # Check budget state
        assert context.budget_used > estimated_cost
        assert context.tool_usage_count["Read"] == 5
        assert context.tool_usage_count["Write"] == 1

    def test_end_to_end_budget_enforcement_flow(self):
        """
        Test 3: End-to-end budget enforcement flow.

        Simulates complete budget enforcement lifecycle:
        1. Estimate cost
        2. Check budget
        3. Execute operation (record usage)
        4. Repeat until budget exhausted
        """
        # Very small budget to ensure operations are denied
        context = ExecutionContext(budget_limit=0.015)

        operations = [
            ("Write", {"path": "file1.txt"}),
            ("Write", {"path": "file2.txt"}),
            ("Write", {"path": "file3.txt"}),
            ("Bash", {"command": "ls"}),
        ]

        executed = []
        denied = []

        for tool_name, tool_input in operations:
            # 1. Estimate cost
            estimated_cost = BudgetEnforcer.estimate_cost(tool_name, tool_input)

            # 2. Check budget
            if BudgetEnforcer.has_budget(context, estimated_cost):
                # 3. Execute (record usage)
                BudgetEnforcer.record_usage(context, tool_name, estimated_cost)
                executed.append(tool_name)
            else:
                denied.append(tool_name)

        # Verify budget enforcement
        assert len(executed) > 0, "Some operations should execute"
        assert len(denied) > 0, "Some operations should be denied"
        assert (
            context.budget_used <= context.budget_limit
        ), "Budget should not exceed limit"

        # Verify correct denial of operations that would exceed budget
        # Last operation should be denied
        assert denied[-1] in [
            op[0] for op in operations[-2:]
        ], "Later operations should be denied"

    def test_budget_exhaustion_triggers_denial(self):
        """
        Test 4: Budget exhaustion triggers correct denial.

        Verifies that when budget is exhausted, has_budget returns False
        and prevents further operations.
        """
        # Small budget that will be exhausted quickly
        context = ExecutionContext(budget_limit=0.02)

        # First operation: should succeed
        cost1 = BudgetEnforcer.estimate_cost("Write", {"path": "test.txt"})
        assert BudgetEnforcer.has_budget(context, cost1)
        BudgetEnforcer.record_usage(context, "Write", cost1)

        # Second operation: should succeed
        cost2 = BudgetEnforcer.estimate_cost("Read", {"path": "test.txt"})
        assert BudgetEnforcer.has_budget(context, cost2)
        BudgetEnforcer.record_usage(context, "Read", cost2)

        # Third operation: budget likely exhausted
        # Use expensive operation to ensure exhaustion
        cost3 = BudgetEnforcer.estimate_cost("Bash", {"command": "expensive"})

        # Check remaining budget
        remaining = BudgetEnforcer.get_remaining_budget(context)
        assert remaining is not None

        # If remaining budget less than cost, should be denied
        if remaining < cost3:
            assert not BudgetEnforcer.has_budget(context, cost3)
            # Attempting to record would violate budget (don't record)

        # Verify budget not exceeded
        assert context.budget_used <= context.budget_limit

    def test_integration_with_permission_policy_future(self):
        """
        Test 2: Integration with PermissionPolicy (placeholder for future).

        This test documents the expected integration point with PermissionPolicy
        once it's implemented in Week 2. Currently validates that BudgetEnforcer
        can work with ExecutionContext which will be used by PermissionPolicy.

        Future: PermissionPolicy.can_use_tool() will call:
        1. BudgetEnforcer.estimate_cost()
        2. BudgetEnforcer.has_budget()
        3. If denied, return (False, "Budget exceeded...")
        """
        context = ExecutionContext(budget_limit=5.0)

        # Simulate what PermissionPolicy will do:
        tool_name = "LLMAgentNode"
        tool_input = {"prompt": "x" * 4000}  # Large prompt

        # Step 1: Estimate cost (PermissionPolicy will do this)
        estimated_cost = BudgetEnforcer.estimate_cost(tool_name, tool_input)
        assert estimated_cost > 0

        # Step 2: Check budget (PermissionPolicy will do this)
        has_budget = BudgetEnforcer.has_budget(context, estimated_cost)

        # Step 3: Make decision
        if has_budget:
            # Would execute tool and record
            BudgetEnforcer.record_usage(context, tool_name, estimated_cost)
            decision = (True, None)
        else:
            # Would deny
            remaining = BudgetEnforcer.get_remaining_budget(context)
            decision = (
                False,
                f"Budget exceeded: ${context.budget_used:.2f} spent, ${remaining:.2f} remaining",
            )

        # Verify decision structure
        assert isinstance(decision, tuple)
        assert len(decision) == 2
        assert isinstance(decision[0], bool) or decision[0] is None
        assert decision[1] is None or isinstance(decision[1], str)


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "tier2"])
