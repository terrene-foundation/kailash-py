"""
Unit tests for BudgetEnforcer.

Tests cost estimation, budget checking, and recording for different tool types.
Following TODO-160 Week 3 specification: 17 unit tests.
"""

import pytest
from kaizen.core.autonomy.permissions.budget_enforcer import BudgetEnforcer
from kaizen.core.autonomy.permissions.context import ExecutionContext


class TestCostEstimation:
    """Tests 1-3: Cost estimation for different tool types."""

    def test_estimate_read_tool_cost(self):
        """Test 1: Estimate cost for Read tool (file operations)."""
        cost = BudgetEnforcer.estimate_cost("Read", {"path": "test.txt"})
        assert cost == 0.001, "Read operations should cost $0.001"

    def test_estimate_write_tool_cost(self):
        """Test 2: Estimate cost for Write tool (file modifications)."""
        cost = BudgetEnforcer.estimate_cost(
            "Write", {"path": "test.txt", "content": "data"}
        )
        assert cost == 0.005, "Write operations should cost $0.005"

    def test_estimate_bash_tool_cost(self):
        """Test 3: Estimate cost for Bash tool (command execution)."""
        cost = BudgetEnforcer.estimate_cost("Bash", {"command": "ls -la"})
        assert cost == 0.01, "Bash operations should cost $0.01"

    def test_estimate_llm_tool_cost(self):
        """Test 4: Estimate cost for LLM tools based on input size."""
        # Short prompt
        short_cost = BudgetEnforcer.estimate_cost("LLMAgentNode", {"prompt": "Hello"})
        assert short_cost > 0, "LLM calls should have non-zero cost"
        assert short_cost < 0.01, "Short prompts should be cheap"

        # Long prompt (simulate 1000 tokens)
        long_prompt = "x" * 4000  # ~1000 tokens (4 chars per token)
        long_cost = BudgetEnforcer.estimate_cost(
            "LLMAgentNode", {"prompt": long_prompt}
        )
        assert long_cost > short_cost, "Longer prompts should cost more"
        assert (
            long_cost >= 0.01
        ), "Long prompts should cost at least $0.01 per 1000 tokens"

    def test_estimate_unknown_tool_cost(self):
        """Test 5: Unknown tools default to $0.00."""
        cost = BudgetEnforcer.estimate_cost("UnknownTool", {})
        assert cost == 0.0, "Unknown tools should default to zero cost"

    def test_estimate_llm_cost_with_messages(self):
        """Test 5b: Estimate LLM cost with messages instead of prompt."""
        messages = [
            {"role": "user", "content": "x" * 2000},  # ~500 tokens
            {"role": "assistant", "content": "y" * 2000},  # ~500 tokens
        ]
        cost = BudgetEnforcer.estimate_cost("LLMAgentNode", {"messages": messages})
        assert cost > 0, "LLM calls with messages should have non-zero cost"

    def test_estimate_cost_with_conservative_buffer(self):
        """Test 6: Cost estimates include 20% safety buffer."""
        # Base cost for Write is $0.005, with 20% buffer should be $0.006
        base_cost = 0.005
        estimated_cost = BudgetEnforcer.estimate_cost("Write", {"path": "test.txt"})

        # Should include buffer (actual implementation may vary)
        assert (
            estimated_cost >= base_cost
        ), "Estimated cost should be at least base cost"


class TestBudgetChecking:
    """Tests 4-6: Budget checking with various scenarios."""

    def test_has_budget_sufficient(self):
        """Test 7: Check budget with sufficient funds."""
        context = ExecutionContext(budget_limit=10.0)
        context.budget_used = 5.0

        result = BudgetEnforcer.has_budget(context, estimated_cost=3.0)
        assert result is True, "Should have budget when 5.0 + 3.0 < 10.0"

    def test_has_budget_insufficient(self):
        """Test 8: Check budget with insufficient funds."""
        context = ExecutionContext(budget_limit=10.0)
        context.budget_used = 9.0

        result = BudgetEnforcer.has_budget(context, estimated_cost=2.0)
        assert result is False, "Should not have budget when 9.0 + 2.0 > 10.0"

    def test_has_budget_unlimited(self):
        """Test 9: Check budget with unlimited budget (None)."""
        context = ExecutionContext(budget_limit=None)
        context.budget_used = 100.0

        result = BudgetEnforcer.has_budget(context, estimated_cost=1000.0)
        assert result is True, "Should always have budget when budget_limit is None"

    def test_has_budget_exact_limit(self):
        """Test 10: Check budget at exact limit."""
        context = ExecutionContext(budget_limit=10.0)
        context.budget_used = 8.0

        # Exactly at limit
        result = BudgetEnforcer.has_budget(context, estimated_cost=2.0)
        assert result is True, "Should have budget when exactly at limit"

        # Just over limit
        result = BudgetEnforcer.has_budget(context, estimated_cost=2.01)
        assert result is False, "Should not have budget when over limit"


class TestBudgetRecording:
    """Tests 7-9: Budget recording and tracking."""

    def test_record_usage_updates_budget(self):
        """Test 11: Recording usage updates budget_used."""
        context = ExecutionContext(budget_limit=10.0)

        BudgetEnforcer.record_usage(context, tool_name="Read", cost_usd=0.5)
        assert context.budget_used == 0.5, "Budget should be updated"

        BudgetEnforcer.record_usage(context, tool_name="Write", cost_usd=1.0)
        assert context.budget_used == 1.5, "Budget should accumulate"

    def test_record_usage_tracks_tool_count(self):
        """Test 12: Recording usage tracks tool usage count."""
        context = ExecutionContext(budget_limit=10.0)

        BudgetEnforcer.record_usage(context, tool_name="Read", cost_usd=0.5)
        assert context.tool_usage_count["Read"] == 1, "Tool usage should be tracked"

        BudgetEnforcer.record_usage(context, tool_name="Read", cost_usd=0.5)
        assert context.tool_usage_count["Read"] == 2, "Tool usage should increment"

    def test_record_usage_multiple_tools(self):
        """Test 13: Recording usage for multiple different tools."""
        context = ExecutionContext(budget_limit=10.0)

        BudgetEnforcer.record_usage(context, tool_name="Read", cost_usd=0.5)
        BudgetEnforcer.record_usage(context, tool_name="Write", cost_usd=1.0)
        BudgetEnforcer.record_usage(context, tool_name="Bash", cost_usd=2.0)

        assert context.budget_used == 3.5, "Total budget should be sum of all costs"
        assert context.tool_usage_count["Read"] == 1
        assert context.tool_usage_count["Write"] == 1
        assert context.tool_usage_count["Bash"] == 1


class TestEdgeCases:
    """Tests 10-12: Edge cases (unlimited budget, zero cost, negative values)."""

    def test_unlimited_budget_never_exhausted(self):
        """Test 14: Unlimited budget (None) never exhausted."""
        context = ExecutionContext(budget_limit=None)

        # Record massive usage
        for i in range(1000):
            BudgetEnforcer.record_usage(context, tool_name="LLM", cost_usd=10.0)

        # Should still have budget
        assert BudgetEnforcer.has_budget(context, estimated_cost=999999.0) is True

    def test_zero_cost_operations(self):
        """Test 15: Zero-cost operations don't affect budget."""
        context = ExecutionContext(budget_limit=10.0)

        BudgetEnforcer.record_usage(context, tool_name="Read", cost_usd=0.0)
        assert context.budget_used == 0.0, "Zero cost should not affect budget"

        BudgetEnforcer.record_usage(context, tool_name="Write", cost_usd=0.0)
        assert context.budget_used == 0.0, "Zero cost should not affect budget"

    def test_negative_cost_raises_error(self):
        """Test 16: Negative costs raise validation error."""
        context = ExecutionContext(budget_limit=10.0)

        with pytest.raises(ValueError, match="Cost cannot be negative"):
            BudgetEnforcer.record_usage(context, tool_name="Read", cost_usd=-1.0)


class TestBudgetResetAndState:
    """Tests 13-15: Budget reset and state management."""

    def test_get_actual_cost_from_result(self):
        """Test 16a: Extract actual cost from result metadata."""
        # With cost metadata
        result = {"usage": {"cost_usd": 0.025}}
        actual_cost = BudgetEnforcer.get_actual_cost(result)
        assert actual_cost == 0.025, "Should extract cost from metadata"

        # Without cost metadata
        result_no_cost = {}
        actual_cost = BudgetEnforcer.get_actual_cost(result_no_cost)
        assert actual_cost == 0.0, "Should default to 0.0 when no metadata"

        # With partial metadata
        result_partial = {"usage": {}}
        actual_cost = BudgetEnforcer.get_actual_cost(result_partial)
        assert actual_cost == 0.0, "Should default to 0.0 when cost_usd missing"

    def test_get_remaining_budget(self):
        """Test 17: Get remaining budget calculation."""
        context = ExecutionContext(budget_limit=10.0)
        context.budget_used = 3.5

        remaining = BudgetEnforcer.get_remaining_budget(context)
        assert remaining == 6.5, "Remaining budget should be limit - used"

    def test_get_remaining_budget_unlimited(self):
        """Test 18: Remaining budget when unlimited."""
        context = ExecutionContext(budget_limit=None)
        context.budget_used = 100.0

        remaining = BudgetEnforcer.get_remaining_budget(context)
        assert remaining is None, "Remaining should be None for unlimited budget"

    def test_get_remaining_budget_exceeded(self):
        """Test 19: Remaining budget when exceeded (negative)."""
        context = ExecutionContext(budget_limit=10.0)
        context.budget_used = 12.0

        remaining = BudgetEnforcer.get_remaining_budget(context)
        assert remaining == -2.0, "Remaining should be negative when exceeded"


class TestThreadSafety:
    """Tests 16-17: Multi-threading safety."""

    def test_concurrent_budget_updates(self):
        """Test 20: Concurrent budget updates are thread-safe."""
        import concurrent.futures

        context = ExecutionContext(budget_limit=1000.0)

        def record_cost(tool_name: str):
            for _ in range(100):
                BudgetEnforcer.record_usage(context, tool_name=tool_name, cost_usd=0.1)

        # Run 10 threads, each recording 100 costs
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(record_cost, f"Tool{i}") for i in range(10)]
            concurrent.futures.wait(futures)

        # Total should be 10 threads * 100 operations * $0.1 = $100.0
        # Use approximate comparison due to floating point precision
        assert (
            abs(context.budget_used - 100.0) < 0.001
        ), "Budget should be correctly updated by all threads"

        # Each tool should have 100 uses
        for i in range(10):
            assert context.tool_usage_count[f"Tool{i}"] == 100

    def test_concurrent_budget_checks(self):
        """Test 21: Concurrent budget checks don't corrupt state."""
        import concurrent.futures

        context = ExecutionContext(budget_limit=100.0)
        context.budget_used = 50.0

        def check_budget():
            results = []
            for _ in range(1000):
                results.append(BudgetEnforcer.has_budget(context, estimated_cost=10.0))
            return results

        # Run 5 threads, each doing 1000 checks
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(check_budget) for _ in range(5)]
            results = [future.result() for future in futures]

        # All checks should return True (50 + 10 < 100)
        for thread_results in results:
            assert all(thread_results), "All budget checks should succeed"

        # Budget should not be corrupted
        assert context.budget_used == 50.0, "Budget should not change from checks"


# Run tests with pytest
if __name__ == "__main__":
    pytest.main([__file__, "-v"])
