"""Permission rule engine for kz tool access control.

Provides glob-pattern-based permission rules that determine whether a
tool call should be allowed, require user confirmation (ask), or be
denied outright. Rules are loaded from ``.kz/config.toml`` or from
``.kz/rules/permissions.toml``.

Precedence: deny > ask > allow. If multiple rules match, the most
restrictive action wins.

Example TOML configuration::

    [[permissions.rules]]
    tool = "bash_*"
    action = "ask"

    [[permissions.rules]]
    tool = "file_write"
    args_contain = ["/etc/", "/usr/"]
    action = "deny"
"""

from __future__ import annotations

import enum
import fnmatch
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]


class PermissionAction(enum.Enum):
    """The action to take for a matching permission rule."""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


# Precedence order: higher number = more restrictive
_ACTION_PRECEDENCE: dict[PermissionAction, int] = {
    PermissionAction.ALLOW: 0,
    PermissionAction.ASK: 1,
    PermissionAction.DENY: 2,
}


@dataclass(frozen=True)
class PermissionRule:
    """A single permission rule.

    Attributes
    ----------
    tool:
        Glob pattern matching tool names (e.g., ``bash_*``, ``file_write``).
    action:
        What to do when the rule matches: allow, ask, or deny.
    args_contain:
        Optional list of substring patterns. If provided, the rule only
        matches when the tool arguments (serialized) contain at least one
        of these substrings.
    description:
        Optional human-readable description for logging/display.
    """

    tool: str
    action: PermissionAction
    args_contain: list[str] = field(default_factory=list)
    description: str = ""


class PermissionEngine:
    """Evaluates permission rules against tool calls.

    Rules are evaluated in order. Multiple rules can match a single tool
    call. The most restrictive matching action wins (deny > ask > allow).

    If no rules match, the default action is ``allow``.
    """

    def __init__(self, rules: list[PermissionRule] | None = None) -> None:
        self._rules: list[PermissionRule] = list(rules) if rules else []

    @property
    def rules(self) -> list[PermissionRule]:
        """The current list of rules."""
        return list(self._rules)

    def add_rule(self, rule: PermissionRule) -> None:
        """Add a rule to the engine."""
        self._rules.append(rule)

    def evaluate(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> PermissionAction:
        """Evaluate permission rules for a tool call.

        Parameters
        ----------
        tool_name:
            The name of the tool being called.
        arguments:
            The tool call arguments (used for args_contain matching).

        Returns
        -------
        The resolved action: allow, ask, or deny.
        If no rules match, returns allow.
        """
        matching_actions: list[PermissionAction] = []

        # Serialize arguments for substring matching
        args_str = ""
        if arguments:
            args_str = _serialize_arguments(arguments)

        for rule in self._rules:
            if not self._matches_tool(rule.tool, tool_name):
                continue

            if rule.args_contain and not self._matches_args(rule.args_contain, args_str):
                continue

            matching_actions.append(rule.action)

        if not matching_actions:
            return PermissionAction.ALLOW

        # Return the most restrictive action
        return max(matching_actions, key=lambda a: _ACTION_PRECEDENCE[a])

    def is_allowed(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> bool:
        """Check if a tool call is allowed (no confirmation needed).

        Returns True only if the resolved action is ``allow``.
        """
        return self.evaluate(tool_name, arguments) == PermissionAction.ALLOW

    def is_denied(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> bool:
        """Check if a tool call is denied.

        Returns True if the resolved action is ``deny``.
        """
        return self.evaluate(tool_name, arguments) == PermissionAction.DENY

    def requires_confirmation(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> bool:
        """Check if a tool call requires user confirmation.

        Returns True if the resolved action is ``ask``.
        """
        return self.evaluate(tool_name, arguments) == PermissionAction.ASK

    @staticmethod
    def _matches_tool(pattern: str, tool_name: str) -> bool:
        """Check if a tool name matches a glob pattern."""
        return fnmatch.fnmatch(tool_name, pattern)

    @staticmethod
    def _matches_args(patterns: list[str], args_str: str) -> bool:
        """Check if serialized arguments contain any of the patterns."""
        args_lower = args_str.lower()
        return any(p.lower() in args_lower for p in patterns)


def _serialize_arguments(arguments: dict[str, Any]) -> str:
    """Serialize tool arguments to a string for substring matching.

    Concatenates all string values and string representations of
    other values for pattern matching.
    """
    parts: list[str] = []
    _collect_strings(arguments, parts)
    return " ".join(parts)


def _collect_strings(obj: Any, out: list[str]) -> None:
    """Recursively collect string representations from a nested structure."""
    if isinstance(obj, str):
        out.append(obj)
    elif isinstance(obj, dict):
        for value in obj.values():
            _collect_strings(value, out)
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            _collect_strings(item, out)
    else:
        out.append(str(obj))


def load_permission_rules(
    raw_config: dict[str, Any] | None = None,
    rules_path: Path | None = None,
) -> list[PermissionRule]:
    """Load permission rules from config dict and/or a rules file.

    Parameters
    ----------
    raw_config:
        A TOML-loaded config dict. Rules are under
        ``permissions.rules`` as a list of dicts.
    rules_path:
        Path to a dedicated permissions TOML file
        (e.g., ``.kz/rules/permissions.toml``).

    Returns
    -------
    List of PermissionRule instances. Rules from the config dict are
    loaded first, then rules from the file (file rules take precedence
    since they are evaluated later).
    """
    rules: list[PermissionRule] = []

    if raw_config:
        rules.extend(_parse_rules_from_dict(raw_config))

    if rules_path and rules_path.is_file():
        file_data = tomllib.loads(rules_path.read_text(encoding="utf-8"))
        rules.extend(_parse_rules_from_dict(file_data))

    return rules


def _parse_rules_from_dict(data: dict[str, Any]) -> list[PermissionRule]:
    """Parse permission rules from a dict (TOML section)."""
    rules: list[PermissionRule] = []
    rules_list = data.get("permissions", {}).get("rules", [])

    if not isinstance(rules_list, list):
        logger.warning("permissions.rules is not a list, skipping")
        return rules

    for entry in rules_list:
        if not isinstance(entry, dict):
            logger.warning("Permission rule entry is not a dict, skipping")
            continue

        tool = entry.get("tool")
        action_str = entry.get("action")

        if not tool or not action_str:
            logger.warning("Permission rule missing 'tool' or 'action': %s", entry)
            continue

        try:
            action = PermissionAction(action_str.lower())
        except ValueError:
            logger.warning(
                "Unknown permission action %r in rule for tool %r",
                action_str,
                tool,
            )
            continue

        args_contain = entry.get("args_contain", [])
        if isinstance(args_contain, str):
            args_contain = [args_contain]

        rules.append(
            PermissionRule(
                tool=tool,
                action=action,
                args_contain=args_contain,
                description=entry.get("description", ""),
            )
        )

    return rules
