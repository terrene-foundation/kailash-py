"""
Unit tests for permission system types.

Tests PermissionMode enum and ToolPermission dataclass.
Following TDD methodology: Write tests FIRST, then implement.
"""

import pytest
from kaizen.core.autonomy.permissions.types import PermissionMode, ToolPermission


class TestPermissionMode:
    """Test PermissionMode enum (5 tests as per spec)"""

    def test_all_modes_defined(self):
        """Test all 4 permission modes are defined"""
        # All 4 modes from TODO-160 spec
        assert hasattr(PermissionMode, "DEFAULT")
        assert hasattr(PermissionMode, "ACCEPT_EDITS")
        assert hasattr(PermissionMode, "PLAN")
        assert hasattr(PermissionMode, "BYPASS")

    def test_default_mode_value(self):
        """Test DEFAULT mode has expected value"""
        mode = PermissionMode.DEFAULT
        assert mode == PermissionMode.DEFAULT
        assert mode.name == "DEFAULT"

    def test_accept_edits_mode_value(self):
        """Test ACCEPT_EDITS mode has expected value"""
        mode = PermissionMode.ACCEPT_EDITS
        assert mode == PermissionMode.ACCEPT_EDITS
        assert mode.name == "ACCEPT_EDITS"

    def test_plan_mode_value(self):
        """Test PLAN mode has expected value"""
        mode = PermissionMode.PLAN
        assert mode == PermissionMode.PLAN
        assert mode.name == "PLAN"

    def test_bypass_mode_value(self):
        """Test BYPASS mode has expected value"""
        mode = PermissionMode.BYPASS
        assert mode == PermissionMode.BYPASS
        assert mode.name == "BYPASS"


class TestToolPermission:
    """Test ToolPermission dataclass (8 tests as per spec)"""

    def test_create_allow_permission(self):
        """Test creating ALLOW permission"""
        perm = ToolPermission(
            tool_name="Read",
            permission_type="ALLOW",
            reason="Safe read operation",
        )

        assert perm.tool_name == "Read"
        assert perm.permission_type == "ALLOW"
        assert perm.reason == "Safe read operation"

    def test_create_deny_permission(self):
        """Test creating DENY permission"""
        perm = ToolPermission(
            tool_name="Bash",
            permission_type="DENY",
            reason="Risky system command",
        )

        assert perm.tool_name == "Bash"
        assert perm.permission_type == "DENY"
        assert perm.reason == "Risky system command"

    def test_create_ask_permission(self):
        """Test creating ASK permission"""
        perm = ToolPermission(
            tool_name="Write",
            permission_type="ASK",
            reason="Requires user approval",
        )

        assert perm.tool_name == "Write"
        assert perm.permission_type == "ASK"
        assert perm.reason == "Requires user approval"

    def test_permission_with_empty_reason(self):
        """Test permission with empty reason string"""
        perm = ToolPermission(
            tool_name="Read",
            permission_type="ALLOW",
            reason="",
        )

        assert perm.tool_name == "Read"
        assert perm.permission_type == "ALLOW"
        assert perm.reason == ""

    def test_permission_type_validation(self):
        """Test permission_type accepts all valid values"""
        valid_types = ["ALLOW", "DENY", "ASK"]

        for perm_type in valid_types:
            perm = ToolPermission(
                tool_name="TestTool",
                permission_type=perm_type,
                reason="Test",
            )
            assert perm.permission_type == perm_type

    def test_tool_name_case_sensitive(self):
        """Test tool names are case-sensitive"""
        perm1 = ToolPermission("Read", "ALLOW", "test")
        perm2 = ToolPermission("read", "ALLOW", "test")

        # Tool names should be case-sensitive
        assert perm1.tool_name != perm2.tool_name

    def test_permission_equality(self):
        """Test two permissions with same data are equal"""
        perm1 = ToolPermission("Read", "ALLOW", "Safe operation")
        perm2 = ToolPermission("Read", "ALLOW", "Safe operation")

        # Dataclasses have default __eq__
        assert perm1 == perm2

    def test_permission_inequality(self):
        """Test two permissions with different data are not equal"""
        perm1 = ToolPermission("Read", "ALLOW", "Safe")
        perm2 = ToolPermission("Write", "DENY", "Risky")

        assert perm1 != perm2


class TestPermissionType:
    """Test PermissionType enum (3 tests)"""

    def test_all_permission_types_defined(self):
        """Test all 3 permission types are defined"""
        from kaizen.core.autonomy.permissions.types import PermissionType

        # All 3 types from TODO-160 spec
        assert hasattr(PermissionType, "ALLOW")
        assert hasattr(PermissionType, "DENY")
        assert hasattr(PermissionType, "ASK")

    def test_permission_type_values(self):
        """Test permission types have expected values"""
        from kaizen.core.autonomy.permissions.types import PermissionType

        assert PermissionType.ALLOW.value == "ALLOW"
        assert PermissionType.DENY.value == "DENY"
        assert PermissionType.ASK.value == "ASK"

    def test_permission_type_comparison(self):
        """Test permission types can be compared"""
        from kaizen.core.autonomy.permissions.types import PermissionType

        allow1 = PermissionType.ALLOW
        allow2 = PermissionType.ALLOW
        deny = PermissionType.DENY

        assert allow1 == allow2
        assert allow1 != deny


class TestPermissionRule:
    """Test PermissionRule dataclass (15 tests as per spec)"""

    # ===== Basic Functionality (5 tests) =====

    def test_create_rule_with_pattern(self):
        """Test creating rule with basic pattern"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rule = PermissionRule(
            pattern="read_file",
            permission_type=PermissionType.ALLOW,
            reason="Safe read operation",
            priority=1,
        )

        assert rule.pattern == "read_file"
        assert rule.permission_type == PermissionType.ALLOW
        assert rule.reason == "Safe read operation"
        assert rule.priority == 1
        assert rule.conditions is None

    def test_rule_with_priority(self):
        """Test rule with different priority values"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        low_priority = PermissionRule(
            pattern=".*",
            permission_type=PermissionType.ASK,
            reason="Default",
            priority=0,
        )
        high_priority = PermissionRule(
            pattern="read_.*",
            permission_type=PermissionType.ALLOW,
            reason="Safe",
            priority=10,
        )

        assert low_priority.priority == 0
        assert high_priority.priority == 10
        assert high_priority.priority > low_priority.priority

    def test_rule_with_conditions(self):
        """Test rule with optional conditions"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rule = PermissionRule(
            pattern="bash",
            permission_type=PermissionType.ASK,
            reason="Conditional approval",
            priority=5,
            conditions={"max_cost": 0.01, "require_review": True},
        )

        assert rule.conditions is not None
        assert rule.conditions["max_cost"] == 0.01
        assert rule.conditions["require_review"] is True

    def test_rule_pattern_validation(self):
        """Test invalid regex pattern raises ValueError"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        # Invalid regex: unclosed bracket
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            PermissionRule(
                pattern="[invalid",
                permission_type=PermissionType.ALLOW,
                reason="Test",
            )

        # Invalid regex: unclosed parenthesis
        with pytest.raises(ValueError, match="Invalid regex pattern"):
            PermissionRule(
                pattern="(unclosed",
                permission_type=PermissionType.ALLOW,
                reason="Test",
            )

    def test_rule_equality(self):
        """Test two rules with same data are equal"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rule1 = PermissionRule(
            pattern="read_file",
            permission_type=PermissionType.ALLOW,
            reason="Safe",
            priority=1,
        )
        rule2 = PermissionRule(
            pattern="read_file",
            permission_type=PermissionType.ALLOW,
            reason="Safe",
            priority=1,
        )

        assert rule1 == rule2

    # ===== Pattern Matching (6 tests) =====

    def test_matches_exact_pattern(self):
        """Test exact pattern matching"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rule = PermissionRule(
            pattern="read_file",
            permission_type=PermissionType.ALLOW,
            reason="Exact match",
        )

        assert rule.matches("read_file") is True
        assert rule.matches("read_files") is False
        assert rule.matches("write_file") is False

    def test_matches_wildcard_pattern(self):
        """Test wildcard pattern matching"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        # Pattern: any tool ending in _file
        rule = PermissionRule(
            pattern=".*_file",
            permission_type=PermissionType.ALLOW,
            reason="File operations",
        )

        assert rule.matches("read_file") is True
        assert rule.matches("write_file") is True
        assert rule.matches("delete_file") is True
        assert rule.matches("bash_command") is False
        assert rule.matches("file_reader") is False

    def test_matches_prefix_pattern(self):
        """Test prefix pattern matching"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        # Pattern: all HTTP tools
        rule = PermissionRule(
            pattern="http_.*",
            permission_type=PermissionType.ASK,
            reason="HTTP operations",
        )

        assert rule.matches("http_get") is True
        assert rule.matches("http_post") is True
        assert rule.matches("http_delete") is True
        assert rule.matches("https_get") is False
        assert rule.matches("get_http") is False

    def test_matches_complex_pattern(self):
        """Test complex regex pattern matching"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        # Pattern: read, write, or delete operations on files
        rule = PermissionRule(
            pattern="(read|write|delete)_file",
            permission_type=PermissionType.ALLOW,
            reason="File operations",
        )

        assert rule.matches("read_file") is True
        assert rule.matches("write_file") is True
        assert rule.matches("delete_file") is True
        assert rule.matches("edit_file") is False
        assert rule.matches("read_files") is False

    def test_no_match_different_tool(self):
        """Test pattern doesn't match unrelated tool"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rule = PermissionRule(
            pattern="read_.*",
            permission_type=PermissionType.ALLOW,
            reason="Read operations",
        )

        assert rule.matches("read_file") is True
        assert rule.matches("read_config") is True
        assert rule.matches("write_file") is False
        assert rule.matches("bash_command") is False

    def test_case_sensitive_matching(self):
        """Test pattern matching is case-sensitive"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rule = PermissionRule(
            pattern="Read_file",
            permission_type=PermissionType.ALLOW,
            reason="Case test",
        )

        assert rule.matches("Read_file") is True
        assert rule.matches("read_file") is False
        assert rule.matches("READ_FILE") is False

    # ===== Edge Cases (4 tests) =====

    def test_empty_pattern_raises_error(self):
        """Test empty pattern raises ValueError"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        with pytest.raises(ValueError, match="Pattern cannot be empty"):
            PermissionRule(
                pattern="",
                permission_type=PermissionType.ALLOW,
                reason="Empty",
            )

    def test_invalid_regex_raises_error(self):
        """Test various invalid regex patterns raise ValueError"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        invalid_patterns = [
            "[invalid",  # Unclosed bracket
            "(unclosed",  # Unclosed parenthesis
            "*invalid",  # Invalid quantifier
            "(?P<invalid",  # Invalid group
        ]

        for pattern in invalid_patterns:
            with pytest.raises(ValueError, match="Invalid regex pattern"):
                PermissionRule(
                    pattern=pattern,
                    permission_type=PermissionType.ALLOW,
                    reason="Test",
                )

    def test_pattern_compilation_cached(self):
        """Test regex pattern is compiled once and cached"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rule = PermissionRule(
            pattern="read_.*",
            permission_type=PermissionType.ALLOW,
            reason="Cache test",
        )

        # Pattern should be compiled in __post_init__
        assert hasattr(rule, "_compiled_pattern")
        assert rule._compiled_pattern is not None

        # Multiple calls should use same compiled pattern
        first_pattern = rule._compiled_pattern
        rule.matches("read_file")
        rule.matches("read_config")
        second_pattern = rule._compiled_pattern

        # Should be exact same object (not re-compiled)
        assert first_pattern is second_pattern

    def test_multiple_rules_different_priorities(self):
        """Test multiple rules with different priorities"""
        from kaizen.core.autonomy.permissions.types import (
            PermissionRule,
            PermissionType,
        )

        rules = [
            PermissionRule(
                pattern=".*",
                permission_type=PermissionType.ASK,
                reason="Default",
                priority=0,
            ),
            PermissionRule(
                pattern="read_.*",
                permission_type=PermissionType.ALLOW,
                reason="Read",
                priority=5,
            ),
            PermissionRule(
                pattern="bash_.*",
                permission_type=PermissionType.DENY,
                reason="Dangerous",
                priority=10,
            ),
        ]

        # Sort by priority (higher first)
        sorted_rules = sorted(rules, key=lambda r: r.priority, reverse=True)

        assert sorted_rules[0].priority == 10  # bash_.*
        assert sorted_rules[1].priority == 5  # read_.*
        assert sorted_rules[2].priority == 0  # .*
