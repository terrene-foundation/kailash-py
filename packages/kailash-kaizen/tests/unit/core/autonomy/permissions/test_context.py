"""
Unit tests for ExecutionContext.

Tests budget tracking, tool usage recording, and thread safety.
Following TDD methodology: Write tests FIRST, then implement.
"""

from concurrent.futures import ThreadPoolExecutor

from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.types import PermissionMode


class TestExecutionContext:
    """Test ExecutionContext class (15 tests as per spec)"""

    def test_create_default_context(self):
        """Test creating ExecutionContext with defaults"""
        ctx = ExecutionContext()

        assert ctx.mode == PermissionMode.DEFAULT
        assert ctx.budget_limit is None
        assert ctx.budget_used == 0.0
        assert ctx.allowed_tools == set()
        assert ctx.denied_tools == set()
        assert ctx.tool_usage_count == {}

    def test_create_context_with_mode(self):
        """Test creating context with specific permission mode"""
        ctx = ExecutionContext(mode=PermissionMode.PLAN)

        assert ctx.mode == PermissionMode.PLAN

    def test_create_context_with_budget_limit(self):
        """Test creating context with budget limit"""
        ctx = ExecutionContext(budget_limit=10.0)

        assert ctx.budget_limit == 10.0
        assert ctx.budget_used == 0.0

    def test_create_context_with_allowed_tools(self):
        """Test creating context with allowed tools"""
        allowed = {"Read", "Grep", "Glob"}
        ctx = ExecutionContext(allowed_tools=allowed)

        assert ctx.allowed_tools == allowed

    def test_create_context_with_denied_tools(self):
        """Test creating context with denied tools"""
        denied = {"Bash", "PythonCode"}
        ctx = ExecutionContext(denied_tools=denied)

        assert ctx.denied_tools == denied

    def test_can_use_tool_allowed(self):
        """Test can_use_tool() returns True for allowed tool"""
        ctx = ExecutionContext(allowed_tools={"Read", "Grep"})

        assert ctx.can_use_tool("Read") is True
        assert ctx.can_use_tool("Grep") is True

    def test_can_use_tool_denied(self):
        """Test can_use_tool() returns False for denied tool"""
        ctx = ExecutionContext(denied_tools={"Bash", "PythonCode"})

        assert ctx.can_use_tool("Bash") is False
        assert ctx.can_use_tool("PythonCode") is False

    def test_can_use_tool_not_in_lists(self):
        """Test can_use_tool() returns True when tool not in any list (default allow)"""
        ctx = ExecutionContext(
            allowed_tools={"Read"},
            denied_tools={"Bash"},
        )

        # Tool not in either list - should be allowed by default
        assert ctx.can_use_tool("Write") is True

    def test_record_tool_usage_increments_count(self):
        """Test record_tool_usage() increments usage count"""
        ctx = ExecutionContext()

        ctx.record_tool_usage("Read", cost_usd=0.0)
        assert ctx.tool_usage_count["Read"] == 1

        ctx.record_tool_usage("Read", cost_usd=0.0)
        assert ctx.tool_usage_count["Read"] == 2

    def test_record_tool_usage_tracks_budget(self):
        """Test record_tool_usage() updates budget_used"""
        ctx = ExecutionContext(budget_limit=10.0)

        ctx.record_tool_usage("Read", cost_usd=1.5)
        assert ctx.budget_used == 1.5

        ctx.record_tool_usage("Write", cost_usd=2.0)
        assert ctx.budget_used == 3.5

    def test_has_budget_with_no_limit(self):
        """Test has_budget() returns True when no budget limit set"""
        ctx = ExecutionContext()

        assert ctx.has_budget(estimated_cost=100.0) is True

    def test_has_budget_within_limit(self):
        """Test has_budget() returns True when within budget"""
        ctx = ExecutionContext(budget_limit=10.0)
        ctx.record_tool_usage("Read", cost_usd=3.0)

        # Estimated 5.0 + used 3.0 = 8.0 < 10.0
        assert ctx.has_budget(estimated_cost=5.0) is True

    def test_has_budget_exceeds_limit(self):
        """Test has_budget() returns False when would exceed budget"""
        ctx = ExecutionContext(budget_limit=10.0)
        ctx.record_tool_usage("Read", cost_usd=8.0)

        # Estimated 5.0 + used 8.0 = 13.0 > 10.0
        assert ctx.has_budget(estimated_cost=5.0) is False

    def test_add_tool_permission_to_allowed(self):
        """Test add_tool_permission() adds to allowed_tools"""
        ctx = ExecutionContext()

        ctx.add_tool_permission("Read", action="allow")

        assert "Read" in ctx.allowed_tools
        assert "Read" not in ctx.denied_tools

    def test_add_tool_permission_to_denied(self):
        """Test add_tool_permission() adds to denied_tools"""
        ctx = ExecutionContext()

        ctx.add_tool_permission("Bash", action="deny")

        assert "Bash" in ctx.denied_tools
        assert "Bash" not in ctx.allowed_tools


class TestExecutionContextThreadSafety:
    """Test ExecutionContext thread safety (3 concurrent scenarios)"""

    def test_concurrent_budget_tracking(self):
        """Test budget tracking is thread-safe with concurrent updates"""
        ctx = ExecutionContext(budget_limit=100.0)

        def record_usage():
            for _ in range(10):
                ctx.record_tool_usage("TestTool", cost_usd=0.5)

        # Run 10 threads, each recording 10 usages = 100 total
        # Total cost: 100 * 0.5 = 50.0
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(record_usage) for _ in range(10)]
            for future in futures:
                future.result()

        # Verify no race conditions
        assert ctx.budget_used == 50.0
        assert ctx.tool_usage_count["TestTool"] == 100

    def test_concurrent_tool_usage_counting(self):
        """Test tool usage counting is thread-safe"""
        ctx = ExecutionContext()

        def record_multiple_tools():
            for i in range(5):
                ctx.record_tool_usage(f"Tool{i % 3}", cost_usd=0.0)

        # Multiple threads recording different tools
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(record_multiple_tools) for _ in range(5)]
            for future in futures:
                future.result()

        # Verify counts are correct (5 threads * 5 calls, distributed across 3 tools)
        total_count = sum(ctx.tool_usage_count.values())
        assert total_count == 25

    def test_concurrent_permission_updates(self):
        """Test adding permissions is thread-safe"""
        ctx = ExecutionContext()

        def add_permissions():
            for i in range(10):
                ctx.add_tool_permission(f"Tool{i}", action="allow")

        # Multiple threads adding permissions
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(add_permissions) for _ in range(5)]
            for future in futures:
                future.result()

        # Verify all tools added (each thread adds same 10 tools, but sets should dedupe)
        assert len(ctx.allowed_tools) == 10
