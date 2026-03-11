"""
Unit tests for PermissionPolicy decision engine.

Tests all 8 decision layers of the permission system with comprehensive coverage.
Following strict TDD methodology: Tests written BEFORE implementation.

Test Structure:
- Layer 1 (BYPASS mode): Tests 1-4
- Layer 2 (ACCEPT_EDITS mode): Tests 5-8
- Layer 3 (PLAN mode): Tests 9-12
- Layer 4 (Denied tools): Tests 13-15
- Layer 5 (Allowed tools): Tests 16-18
- Layer 6 (Permission rules): Tests 19-21
- Layer 7 (Budget exhaustion): Tests 22-24
- Layer 8 (ASK fallback): Test 25
"""

from kaizen.core.autonomy.permissions.context import ExecutionContext
from kaizen.core.autonomy.permissions.policy import PermissionPolicy
from kaizen.core.autonomy.permissions.types import (
    PermissionMode,
    PermissionRule,
    PermissionType,
)

# ──────────────────────────────────────────────────────────────
# LAYER 1: BYPASS MODE (Tests 1-4)
# ──────────────────────────────────────────────────────────────


def test_bypass_mode_allows_all_tools():
    """Test 1: BYPASS mode allows all tools without checks."""
    context = ExecutionContext(mode=PermissionMode.BYPASS)
    policy = PermissionPolicy(context)

    # Should allow any tool, even risky ones
    allowed, reason = policy.check_permission("Bash", {"command": "rm -rf /"}, 0.0)

    assert allowed is True
    assert reason is None


def test_bypass_mode_ignores_budget():
    """Test 2: BYPASS mode ignores budget limits."""
    context = ExecutionContext(
        mode=PermissionMode.BYPASS,
        budget_limit=1.0,
    )
    # Set budget to exceeded state
    context.budget_used = 10.0
    policy = PermissionPolicy(context)

    # Should still allow tools despite budget exceeded
    allowed, reason = policy.check_permission("LLMNode", {}, estimated_cost=5.0)

    assert allowed is True
    assert reason is None


def test_bypass_mode_ignores_denied_tools():
    """Test 3: BYPASS mode ignores denied tools list."""
    context = ExecutionContext(
        mode=PermissionMode.BYPASS,
        denied_tools={"Write", "Bash"},
    )
    policy = PermissionPolicy(context)

    # Should allow even explicitly denied tools
    allowed, reason = policy.check_permission("Write", {"path": "test.txt"}, 0.0)

    assert allowed is True
    assert reason is None


def test_bypass_mode_performance():
    """Test 4: BYPASS mode early exit for performance."""
    context = ExecutionContext(
        mode=PermissionMode.BYPASS,
        budget_limit=1.0,
        denied_tools={"Bash"},
    )
    context.budget_used = 10.0  # Exceeded budget
    policy = PermissionPolicy(context)

    # Should exit early without checking budget or denied tools
    allowed, reason = policy.check_permission("Bash", {}, 5.0)

    assert allowed is True
    assert reason is None


# ──────────────────────────────────────────────────────────────
# LAYER 2: ACCEPT_EDITS MODE (Tests 5-8)
# ──────────────────────────────────────────────────────────────


def test_accept_edits_mode_allows_write():
    """Test 5: ACCEPT_EDITS mode auto-approves Write tool."""
    context = ExecutionContext(mode=PermissionMode.ACCEPT_EDITS)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Write", {"path": "test.txt"}, 0.0)

    assert allowed is True
    assert reason is None


def test_accept_edits_mode_allows_edit():
    """Test 6: ACCEPT_EDITS mode auto-approves Edit tool."""
    context = ExecutionContext(mode=PermissionMode.ACCEPT_EDITS)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Edit", {"path": "test.py"}, 0.0)

    assert allowed is True
    assert reason is None


def test_accept_edits_mode_asks_for_bash():
    """Test 7: ACCEPT_EDITS mode asks for Bash approval."""
    context = ExecutionContext(mode=PermissionMode.ACCEPT_EDITS)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Bash", {"command": "ls"}, 0.0)

    assert allowed is None
    assert reason is None


def test_accept_edits_mode_asks_for_pythoncode():
    """Test 8: ACCEPT_EDITS mode asks for PythonCode approval."""
    context = ExecutionContext(mode=PermissionMode.ACCEPT_EDITS)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission(
        "PythonCode", {"code": "print('hi')"}, 0.0
    )

    assert allowed is None
    assert reason is None


# ──────────────────────────────────────────────────────────────
# LAYER 3: PLAN MODE (Tests 9-12)
# ──────────────────────────────────────────────────────────────


def test_plan_mode_allows_read():
    """Test 9: PLAN mode allows Read tool."""
    context = ExecutionContext(mode=PermissionMode.PLAN)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Read", {"path": "data.txt"}, 0.0)

    assert allowed is True
    assert reason is None


def test_plan_mode_allows_grep():
    """Test 10: PLAN mode allows Grep tool."""
    context = ExecutionContext(mode=PermissionMode.PLAN)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Grep", {"pattern": "test"}, 0.0)

    assert allowed is True
    assert reason is None


def test_plan_mode_denies_write():
    """Test 11: PLAN mode denies Write tool."""
    context = ExecutionContext(mode=PermissionMode.PLAN)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Write", {"path": "test.txt"}, 0.0)

    assert allowed is False
    assert reason is not None
    assert "Plan mode" in reason
    assert "Write" in reason


def test_plan_mode_denies_bash():
    """Test 12: PLAN mode denies Bash tool."""
    context = ExecutionContext(mode=PermissionMode.PLAN)
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Bash", {"command": "ls"}, 0.0)

    assert allowed is False
    assert reason is not None
    assert "Plan mode" in reason


# ──────────────────────────────────────────────────────────────
# LAYER 4: DENIED TOOLS (Tests 13-15)
# ──────────────────────────────────────────────────────────────


def test_denied_tools_blocks_explicitly_denied():
    """Test 13: Explicitly denied tools are blocked."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        denied_tools={"Bash"},
    )
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("Bash", {"command": "ls"}, 0.0)

    assert allowed is False
    assert reason is not None
    assert "Bash" in reason
    assert "disallowed" in reason.lower()


def test_denied_tools_blocks_multiple():
    """Test 14: Multiple denied tools all blocked."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        denied_tools={"Bash", "Write", "Edit"},
    )
    policy = PermissionPolicy(context)

    # All denied tools should be blocked
    for tool_name in ["Bash", "Write", "Edit"]:
        allowed, reason = policy.check_permission(tool_name, {}, 0.0)
        assert allowed is False
        assert tool_name in reason


def test_denied_tools_priority_over_mode():
    """Test 15: Denied tools take priority over mode defaults."""
    context = ExecutionContext(
        mode=PermissionMode.ACCEPT_EDITS,  # Would normally allow Write
        denied_tools={"Write"},
    )
    policy = PermissionPolicy(context)

    # Write should be denied despite ACCEPT_EDITS mode
    allowed, reason = policy.check_permission("Write", {"path": "test.txt"}, 0.0)

    assert allowed is False
    assert "Write" in reason


# ──────────────────────────────────────────────────────────────
# LAYER 5: ALLOWED TOOLS (Tests 16-18)
# ──────────────────────────────────────────────────────────────


def test_allowed_tools_permits_explicitly_allowed():
    """Test 16: Explicitly allowed tools are permitted."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        allowed_tools={"CustomTool"},
    )
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("CustomTool", {}, 0.0)

    assert allowed is True
    assert reason is None


def test_allowed_tools_priority_over_rules():
    """Test 17: Allowed tools take priority over permission rules."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        allowed_tools={"Bash"},
    )
    policy = PermissionPolicy(context)

    # Bash would normally ask, but allowed_tools permits it
    allowed, reason = policy.check_permission("Bash", {"command": "ls"}, 0.0)

    assert allowed is True
    assert reason is None


def test_allowed_tools_multiple_permissions():
    """Test 18: Multiple allowed tools all permitted."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        allowed_tools={"Tool1", "Tool2", "Tool3"},
    )
    policy = PermissionPolicy(context)

    # All allowed tools should be permitted
    for tool_name in ["Tool1", "Tool2", "Tool3"]:
        allowed, reason = policy.check_permission(tool_name, {}, 0.0)
        assert allowed is True
        assert reason is None


# ──────────────────────────────────────────────────────────────
# LAYER 6: PERMISSION RULES (Tests 19-21)
# ──────────────────────────────────────────────────────────────


def test_permission_rules_allow_pattern():
    """Test 19: Permission rules with ALLOW pattern."""
    rule = PermissionRule(
        pattern="read_.*",
        permission_type=PermissionType.ALLOW,
        reason="Safe read operations",
        priority=5,
    )
    context = ExecutionContext(mode=PermissionMode.DEFAULT)
    context.rules = [rule]
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("read_file", {}, 0.0)

    assert allowed is True
    assert reason is None


def test_permission_rules_deny_pattern():
    """Test 20: Permission rules with DENY pattern."""
    rule = PermissionRule(
        pattern="bash_.*",
        permission_type=PermissionType.DENY,
        reason="Dangerous bash operations",
        priority=10,
    )
    context = ExecutionContext(mode=PermissionMode.DEFAULT)
    context.rules = [rule]
    policy = PermissionPolicy(context)

    allowed, reason = policy.check_permission("bash_command", {}, 0.0)

    assert allowed is False
    assert reason is not None
    assert "bash_.*" in reason


def test_permission_rules_priority_order():
    """Test 21: Permission rules evaluated in priority order (high to low)."""
    # High priority DENY should be checked before low priority ALLOW
    rules = [
        PermissionRule(
            pattern=".*",  # Match all
            permission_type=PermissionType.ALLOW,
            reason="Allow all (low priority)",
            priority=0,
        ),
        PermissionRule(
            pattern="bash_.*",
            permission_type=PermissionType.DENY,
            reason="Deny bash (high priority)",
            priority=10,
        ),
    ]
    context = ExecutionContext(mode=PermissionMode.DEFAULT)
    context.rules = rules
    policy = PermissionPolicy(context)

    # bash_command should be denied (high priority rule)
    allowed, reason = policy.check_permission("bash_command", {}, 0.0)
    assert allowed is False
    assert "bash_.*" in reason

    # other_tool should be allowed (low priority rule)
    allowed, reason = policy.check_permission("other_tool", {}, 0.0)
    assert allowed is True


# ──────────────────────────────────────────────────────────────
# LAYER 7: BUDGET EXHAUSTION (Tests 22-24)
# ──────────────────────────────────────────────────────────────


def test_budget_enforcement_blocks_when_exceeded():
    """Test 22: Budget check blocks tool when budget exceeded."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        budget_limit=10.0,
    )
    context.budget_used = 9.5
    policy = PermissionPolicy(context)

    # Tool needs $1.00, budget only has $0.50 remaining
    allowed, reason = policy.check_permission("LLMNode", {}, estimated_cost=1.0)

    assert allowed is False
    assert reason is not None
    assert "Budget exceeded" in reason
    assert "$9.5" in reason or "$9.50" in reason
    assert "$0.5" in reason or "$0.50" in reason


def test_budget_enforcement_allows_when_within_limit():
    """Test 23: Budget check allows tool when within budget."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        budget_limit=10.0,
    )
    context.budget_used = 8.0
    policy = PermissionPolicy(context)

    # Tool needs $1.00, budget has $2.00 remaining
    allowed, reason = policy.check_permission("Read", {}, estimated_cost=1.0)

    # Should not be blocked by budget (Read is safe tool in DEFAULT mode)
    assert allowed is True
    assert reason is None


def test_budget_enforcement_unlimited_budget():
    """Test 24: No budget limit means unlimited budget."""
    context = ExecutionContext(
        mode=PermissionMode.DEFAULT,
        budget_limit=None,  # Unlimited
    )
    context.budget_used = 1000.0
    policy = PermissionPolicy(context)

    # Should allow any cost with unlimited budget
    allowed, reason = policy.check_permission("Read", {}, estimated_cost=9999.0)

    assert allowed is True
    assert reason is None


# ──────────────────────────────────────────────────────────────
# LAYER 8: ASK FALLBACK (Test 25)
# ──────────────────────────────────────────────────────────────


def test_default_mode_asks_for_risky_tools():
    """Test 25: DEFAULT mode asks for approval on risky tools (fallback)."""
    context = ExecutionContext(mode=PermissionMode.DEFAULT)
    policy = PermissionPolicy(context)

    # Risky tools should require approval
    risky_tools = ["Bash", "PythonCode", "Write", "Edit", "DeleteFileNode"]

    for tool_name in risky_tools:
        allowed, reason = policy.check_permission(tool_name, {}, 0.0)
        assert allowed is None, f"{tool_name} should require approval"
        assert reason is None, f"{tool_name} should have no reason (ASK)"
