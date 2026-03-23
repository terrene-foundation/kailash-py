"""Tests for kz.config.permissions — permission rule evaluation.

Tests cover:
- Rule matching with glob patterns
- Precedence: deny > ask > allow
- Argument pattern matching (args_contain)
- Rule loading from TOML-style dicts
- Edge cases: no rules, empty tool names, overlapping patterns
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from kaizen_agents.delegate.config.permissions import (
    PermissionAction,
    PermissionEngine,
    PermissionRule,
    load_permission_rules,
    _serialize_arguments,
)


# ---------------------------------------------------------------------------
# PermissionAction
# ---------------------------------------------------------------------------


class TestPermissionAction:
    def test_enum_values(self) -> None:
        assert PermissionAction.ALLOW.value == "allow"
        assert PermissionAction.ASK.value == "ask"
        assert PermissionAction.DENY.value == "deny"

    def test_from_string(self) -> None:
        assert PermissionAction("allow") == PermissionAction.ALLOW
        assert PermissionAction("deny") == PermissionAction.DENY

    def test_invalid_value(self) -> None:
        with pytest.raises(ValueError):
            PermissionAction("block")


# ---------------------------------------------------------------------------
# PermissionRule
# ---------------------------------------------------------------------------


class TestPermissionRule:
    def test_basic_rule(self) -> None:
        rule = PermissionRule(tool="bash", action=PermissionAction.ASK)
        assert rule.tool == "bash"
        assert rule.action == PermissionAction.ASK
        assert rule.args_contain == []

    def test_rule_with_args_contain(self) -> None:
        rule = PermissionRule(
            tool="file_write",
            action=PermissionAction.DENY,
            args_contain=["/etc/", "/usr/"],
        )
        assert len(rule.args_contain) == 2

    def test_rule_frozen(self) -> None:
        rule = PermissionRule(tool="x", action=PermissionAction.ALLOW)
        with pytest.raises(AttributeError):
            rule.tool = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PermissionEngine — basic evaluation
# ---------------------------------------------------------------------------


class TestPermissionEngineBasic:
    def test_no_rules_allows_everything(self) -> None:
        engine = PermissionEngine()
        assert engine.evaluate("bash") == PermissionAction.ALLOW
        assert engine.evaluate("file_read") == PermissionAction.ALLOW
        assert engine.is_allowed("anything")

    def test_exact_match(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="bash", action=PermissionAction.ASK),
            ]
        )
        assert engine.evaluate("bash") == PermissionAction.ASK
        assert engine.evaluate("file_read") == PermissionAction.ALLOW

    def test_glob_match_star(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="bash_*", action=PermissionAction.ASK),
            ]
        )
        assert engine.evaluate("bash_exec") == PermissionAction.ASK
        assert engine.evaluate("bash_tool") == PermissionAction.ASK
        assert engine.evaluate("file_read") == PermissionAction.ALLOW

    def test_glob_match_question_mark(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="file_?", action=PermissionAction.ASK),
            ]
        )
        assert engine.evaluate("file_x") == PermissionAction.ASK
        assert engine.evaluate("file_ab") == PermissionAction.ALLOW

    def test_glob_match_all(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="*", action=PermissionAction.ASK),
            ]
        )
        assert engine.evaluate("bash") == PermissionAction.ASK
        assert engine.evaluate("anything") == PermissionAction.ASK

    def test_deny_rule(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="dangerous", action=PermissionAction.DENY),
            ]
        )
        assert engine.is_denied("dangerous")
        assert not engine.is_allowed("dangerous")

    def test_allow_rule(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="safe_*", action=PermissionAction.ALLOW),
            ]
        )
        assert engine.is_allowed("safe_tool")


# ---------------------------------------------------------------------------
# PermissionEngine — precedence (deny > ask > allow)
# ---------------------------------------------------------------------------


class TestPermissionEnginePrecedence:
    def test_deny_beats_allow(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="bash", action=PermissionAction.ALLOW),
                PermissionRule(tool="bash", action=PermissionAction.DENY),
            ]
        )
        assert engine.evaluate("bash") == PermissionAction.DENY

    def test_deny_beats_ask(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="*", action=PermissionAction.ASK),
                PermissionRule(tool="bash", action=PermissionAction.DENY),
            ]
        )
        assert engine.evaluate("bash") == PermissionAction.DENY
        # Other tools still get ASK
        assert engine.evaluate("file_read") == PermissionAction.ASK

    def test_ask_beats_allow(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="*", action=PermissionAction.ALLOW),
                PermissionRule(tool="bash_*", action=PermissionAction.ASK),
            ]
        )
        assert engine.evaluate("bash_exec") == PermissionAction.ASK
        assert engine.evaluate("file_read") == PermissionAction.ALLOW

    def test_multiple_deny_rules(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="bash", action=PermissionAction.DENY),
                PermissionRule(tool="bash", action=PermissionAction.DENY),
            ]
        )
        assert engine.evaluate("bash") == PermissionAction.DENY

    def test_order_independent_precedence(self) -> None:
        """Precedence is by action type, not rule order."""
        # Allow first, deny second
        engine1 = PermissionEngine(
            [
                PermissionRule(tool="bash", action=PermissionAction.ALLOW),
                PermissionRule(tool="bash", action=PermissionAction.DENY),
            ]
        )
        # Deny first, allow second
        engine2 = PermissionEngine(
            [
                PermissionRule(tool="bash", action=PermissionAction.DENY),
                PermissionRule(tool="bash", action=PermissionAction.ALLOW),
            ]
        )
        assert engine1.evaluate("bash") == PermissionAction.DENY
        assert engine2.evaluate("bash") == PermissionAction.DENY


# ---------------------------------------------------------------------------
# PermissionEngine — argument matching
# ---------------------------------------------------------------------------


class TestPermissionEngineArguments:
    def test_args_contain_match(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(
                    tool="file_write",
                    action=PermissionAction.DENY,
                    args_contain=["/etc/"],
                ),
            ]
        )
        assert engine.evaluate("file_write", {"path": "/etc/passwd"}) == PermissionAction.DENY
        assert engine.evaluate("file_write", {"path": "/tmp/test"}) == PermissionAction.ALLOW

    def test_args_contain_multiple_patterns(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(
                    tool="file_write",
                    action=PermissionAction.DENY,
                    args_contain=["/etc/", "/usr/"],
                ),
            ]
        )
        assert engine.evaluate("file_write", {"path": "/etc/config"}) == PermissionAction.DENY
        assert engine.evaluate("file_write", {"path": "/usr/bin/x"}) == PermissionAction.DENY
        assert engine.evaluate("file_write", {"path": "/home/user"}) == PermissionAction.ALLOW

    def test_args_contain_case_insensitive(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(
                    tool="bash",
                    action=PermissionAction.DENY,
                    args_contain=["rm -rf"],
                ),
            ]
        )
        assert engine.evaluate("bash", {"command": "RM -RF /"}) == PermissionAction.DENY

    def test_args_contain_nested_values(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(
                    tool="complex_tool",
                    action=PermissionAction.DENY,
                    args_contain=["secret"],
                ),
            ]
        )
        args: dict[str, Any] = {"config": {"nested": {"deep": "contains secret value"}}}
        assert engine.evaluate("complex_tool", args) == PermissionAction.DENY

    def test_no_args_skips_args_contain(self) -> None:
        """Rules with args_contain should not match when no args provided."""
        engine = PermissionEngine(
            [
                PermissionRule(
                    tool="bash",
                    action=PermissionAction.DENY,
                    args_contain=["rm -rf"],
                ),
            ]
        )
        assert engine.evaluate("bash") == PermissionAction.ALLOW
        assert engine.evaluate("bash", None) == PermissionAction.ALLOW

    def test_rule_without_args_contain_matches_all_args(self) -> None:
        """Rules without args_contain should match regardless of arguments."""
        engine = PermissionEngine(
            [
                PermissionRule(tool="bash", action=PermissionAction.ASK),
            ]
        )
        assert engine.evaluate("bash", {"command": "anything"}) == PermissionAction.ASK


# ---------------------------------------------------------------------------
# PermissionEngine — convenience methods
# ---------------------------------------------------------------------------


class TestPermissionEngineConvenience:
    def test_is_allowed(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="safe", action=PermissionAction.ALLOW),
            ]
        )
        assert engine.is_allowed("safe")
        assert engine.is_allowed("other")  # No rule = allow

    def test_is_denied(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="blocked", action=PermissionAction.DENY),
            ]
        )
        assert engine.is_denied("blocked")
        assert not engine.is_denied("other")

    def test_requires_confirmation(self) -> None:
        engine = PermissionEngine(
            [
                PermissionRule(tool="bash", action=PermissionAction.ASK),
            ]
        )
        assert engine.requires_confirmation("bash")
        assert not engine.requires_confirmation("file_read")

    def test_add_rule(self) -> None:
        engine = PermissionEngine()
        assert engine.is_allowed("bash")

        engine.add_rule(PermissionRule(tool="bash", action=PermissionAction.DENY))
        assert engine.is_denied("bash")

    def test_rules_property(self) -> None:
        rules = [
            PermissionRule(tool="a", action=PermissionAction.ALLOW),
            PermissionRule(tool="b", action=PermissionAction.DENY),
        ]
        engine = PermissionEngine(rules)
        assert len(engine.rules) == 2
        # Should be a copy
        engine.rules.append(PermissionRule(tool="c", action=PermissionAction.ASK))
        assert len(engine.rules) == 2  # Original unchanged


# ---------------------------------------------------------------------------
# _serialize_arguments
# ---------------------------------------------------------------------------


class TestSerializeArguments:
    def test_simple_string_values(self) -> None:
        result = _serialize_arguments({"command": "ls -la", "dir": "/tmp"})
        assert "ls -la" in result
        assert "/tmp" in result

    def test_nested_dict(self) -> None:
        result = _serialize_arguments({"config": {"key": "secret_value"}})
        assert "secret_value" in result

    def test_list_values(self) -> None:
        result = _serialize_arguments({"items": ["one", "two", "three"]})
        assert "one" in result
        assert "three" in result

    def test_numeric_values(self) -> None:
        result = _serialize_arguments({"count": 42, "ratio": 3.14})
        assert "42" in result
        assert "3.14" in result

    def test_empty_dict(self) -> None:
        result = _serialize_arguments({})
        assert result == ""


# ---------------------------------------------------------------------------
# load_permission_rules
# ---------------------------------------------------------------------------


class TestLoadPermissionRules:
    def test_load_from_dict(self) -> None:
        raw = {
            "permissions": {
                "rules": [
                    {"tool": "bash_*", "action": "ask"},
                    {
                        "tool": "file_write",
                        "action": "deny",
                        "args_contain": ["/etc/", "/usr/"],
                    },
                ]
            }
        }
        rules = load_permission_rules(raw_config=raw)
        assert len(rules) == 2
        assert rules[0].tool == "bash_*"
        assert rules[0].action == PermissionAction.ASK
        assert rules[1].action == PermissionAction.DENY
        assert rules[1].args_contain == ["/etc/", "/usr/"]

    def test_load_empty_dict(self) -> None:
        rules = load_permission_rules(raw_config={})
        assert rules == []

    def test_load_none_config(self) -> None:
        rules = load_permission_rules(raw_config=None)
        assert rules == []

    def test_skips_invalid_entries(self) -> None:
        raw = {
            "permissions": {
                "rules": [
                    {"tool": "bash", "action": "ask"},
                    {"tool": "no_action"},  # Missing action
                    "not_a_dict",  # Invalid type
                    {"action": "deny"},  # Missing tool
                    {"tool": "bad", "action": "invalid_action"},  # Bad action
                ]
            }
        }
        rules = load_permission_rules(raw_config=raw)
        assert len(rules) == 1
        assert rules[0].tool == "bash"

    def test_load_from_file(self, tmp_path: Path) -> None:
        rules_file = tmp_path / "permissions.toml"
        rules_file.write_text(
            """
[[permissions.rules]]
tool = "bash"
action = "ask"

[[permissions.rules]]
tool = "file_write"
action = "deny"
args_contain = ["/etc/"]
""",
            encoding="utf-8",
        )

        rules = load_permission_rules(rules_path=rules_file)
        assert len(rules) == 2
        assert rules[0].tool == "bash"
        assert rules[1].args_contain == ["/etc/"]

    def test_load_from_both_sources(self, tmp_path: Path) -> None:
        """Rules from config dict AND file should be combined."""
        rules_file = tmp_path / "permissions.toml"
        rules_file.write_text(
            """
[[permissions.rules]]
tool = "from_file"
action = "deny"
""",
            encoding="utf-8",
        )

        raw = {
            "permissions": {
                "rules": [
                    {"tool": "from_config", "action": "ask"},
                ]
            }
        }

        rules = load_permission_rules(raw_config=raw, rules_path=rules_file)
        assert len(rules) == 2
        tools = [r.tool for r in rules]
        assert "from_config" in tools
        assert "from_file" in tools

    def test_args_contain_string_coerced_to_list(self) -> None:
        """A single string for args_contain should be wrapped in a list."""
        raw = {
            "permissions": {
                "rules": [
                    {"tool": "bash", "action": "deny", "args_contain": "/etc/"},
                ]
            }
        }
        rules = load_permission_rules(raw_config=raw)
        assert rules[0].args_contain == ["/etc/"]

    def test_nonexistent_file_ignored(self, tmp_path: Path) -> None:
        """A missing rules file should not cause an error."""
        missing = tmp_path / "does_not_exist.toml"
        rules = load_permission_rules(rules_path=missing)
        assert rules == []

    def test_with_description_field(self) -> None:
        raw = {
            "permissions": {
                "rules": [
                    {
                        "tool": "bash",
                        "action": "ask",
                        "description": "Require confirmation for shell commands",
                    },
                ]
            }
        }
        rules = load_permission_rules(raw_config=raw)
        assert rules[0].description == "Require confirmation for shell commands"
