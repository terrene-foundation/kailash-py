# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shadow Mode Observer for zero-config observation of AI activity.

Records tool calls during AI-assisted sessions, classifies them into
categories, evaluates what WOULD have happened under constraint
enforcement, and generates structured reports.

Shadow mode does NOT require ``attest init`` — it works zero-config.
Shadow data goes to ``.trust-plane/shadow.db`` (separate from trust.db).

Usage:
    >>> from kailash.trust.plane.shadow import ShadowObserver, ShadowSession
    >>> observer = ShadowObserver()
    >>> session = ShadowSession(session_id="s1")
    >>> observer.record(session, action="Read", resource="/src/main.py")
    >>> print(observer.generate_report(session))
"""

from __future__ import annotations

import fnmatch
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.trust.plane.models import (
    CommunicationConstraints,
    ConstraintEnvelope,
    DataAccessConstraints,
    FinancialConstraints,
    OperationalConstraints,
    TemporalConstraints,
)
from kailash.trust.plane.templates import get_template

logger = logging.getLogger(__name__)

__all__ = [
    "ShadowObserver",
    "ShadowSession",
    "ShadowToolCall",
    "generate_report",
    "generate_report_json",
    "infer_constraints",
]

# Category classification rules: (category, action_patterns, resource_patterns)
_CATEGORY_RULES: list[tuple[str, list[str], list[str]]] = [
    ("file_read", ["Read", "read_file", "cat", "head", "tail", "less", "more"], []),
    (
        "file_write",
        ["Write", "Edit", "write_file", "edit_file", "create_file", "save"],
        [],
    ),
    (
        "shell_command",
        ["Bash", "bash", "shell", "exec", "run", "subprocess", "terminal"],
        [],
    ),
    (
        "web_request",
        [
            "WebFetch",
            "WebSearch",
            "web_fetch",
            "web_search",
            "http",
            "curl",
            "wget",
            "fetch",
        ],
        [],
    ),
]

# Resource-based classification fallbacks
_RESOURCE_CATEGORY_RULES: list[tuple[str, list[str]]] = [
    (
        "file_read",
        [
            "*.py",
            "*.js",
            "*.ts",
            "*.md",
            "*.txt",
            "*.json",
            "*.yaml",
            "*.yml",
            "*.toml",
        ],
    ),
    ("file_write", []),
    ("web_request", ["http://*", "https://*"]),
]


def _classify_category(action: str, resource: str) -> str:
    """Classify a tool call into a category based on action and resource.

    Categories: file_read, file_write, shell_command, web_request, other.
    """
    action_lower = action.lower()

    # Check action-based rules first
    for category, action_patterns, _resource_patterns in _CATEGORY_RULES:
        for pattern in action_patterns:
            if action_lower == pattern.lower() or action_lower.startswith(
                pattern.lower()
            ):
                return category

    # Check resource-based fallbacks
    resource_lower = resource.lower()
    for category, patterns in _RESOURCE_CATEGORY_RULES:
        for pattern in patterns:
            if fnmatch.fnmatch(resource_lower, pattern):
                return category

    return "other"


def _evaluate_against_envelope(
    action: str,
    resource: str,
    category: str,
    envelope: ConstraintEnvelope,
) -> tuple[bool, bool, Optional[str]]:
    """Evaluate whether a tool call would be blocked or held.

    Returns:
        Tuple of (would_be_blocked, would_be_held, reason).
    """
    would_be_blocked = False
    would_be_held = False
    reason: Optional[str] = None

    # Check operational constraints
    if action in envelope.operational.blocked_actions:
        would_be_blocked = True
        reason = f"Action '{action}' is in blocked_actions"
        return would_be_blocked, would_be_held, reason

    # Check data access constraints
    if resource:
        # Check blocked paths
        for blocked_path in envelope.data_access.blocked_paths:
            if resource.startswith(blocked_path) or resource == blocked_path:
                would_be_blocked = True
                reason = f"Resource '{resource}' matches blocked path '{blocked_path}'"
                return would_be_blocked, would_be_held, reason

        # Check blocked patterns
        for pattern in envelope.data_access.blocked_patterns:
            if fnmatch.fnmatch(resource, pattern):
                would_be_blocked = True
                reason = f"Resource '{resource}' matches blocked pattern '{pattern}'"
                return would_be_blocked, would_be_held, reason

        # Check write path constraints for file_write
        if category == "file_write" and envelope.data_access.write_paths:
            in_allowed_path = any(
                resource.startswith(wp) for wp in envelope.data_access.write_paths
            )
            if not in_allowed_path:
                would_be_held = True
                reason = f"Write to '{resource}' not in allowed write paths"

        # Check read path constraints for file_read
        if category == "file_read" and envelope.data_access.read_paths:
            in_allowed_path = any(
                resource.startswith(rp) for rp in envelope.data_access.read_paths
            )
            if not in_allowed_path:
                would_be_held = True
                reason = f"Read from '{resource}' not in allowed read paths"

    # Check communication constraints
    if category == "web_request":
        if action in envelope.communication.blocked_channels:
            would_be_blocked = True
            reason = f"Channel '{action}' is blocked"
        elif action in envelope.communication.requires_review:
            would_be_held = True
            reason = f"Channel '{action}' requires review"

    return would_be_blocked, would_be_held, reason


@dataclass
class ShadowToolCall:
    """A single observed tool call during shadow observation.

    Attributes:
        action: The tool/action name (e.g., "Read", "Bash", "Edit").
        resource: The resource acted upon (e.g., file path, URL).
        category: Classified category (file_read, file_write,
            shell_command, web_request, other).
        timestamp: When the call was observed.
        would_be_blocked: Whether this call would be blocked
            under the default constraint template.
        would_be_held: Whether this call would be held for review.
        reason: Explanation of why the call would be blocked/held.
    """

    action: str
    resource: str
    category: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    would_be_blocked: bool = False
    would_be_held: bool = False
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "action": self.action,
            "resource": self.resource,
            "category": self.category,
            "timestamp": self.timestamp.isoformat(),
            "would_be_blocked": self.would_be_blocked,
            "would_be_held": self.would_be_held,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShadowToolCall:
        """Deserialize from dictionary."""
        if "action" not in data:
            raise ValueError("ShadowToolCall requires 'action' field")
        if "resource" not in data:
            raise ValueError("ShadowToolCall requires 'resource' field")
        if "category" not in data:
            raise ValueError("ShadowToolCall requires 'category' field")
        return cls(
            action=data["action"],
            resource=data["resource"],
            category=data["category"],
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if "timestamp" in data
                else datetime.now(timezone.utc)
            ),
            would_be_blocked=data.get("would_be_blocked", False),
            would_be_held=data.get("would_be_held", False),
            reason=data.get("reason"),
        )


@dataclass
class ShadowSession:
    """A shadow observation session.

    Attributes:
        session_id: Unique session identifier.
        started_at: When the session started.
        ended_at: When the session ended (None if still active).
        tool_calls: List of observed tool calls.
    """

    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    tool_calls: deque = field(default_factory=lambda: deque(maxlen=10_000))

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "session_id": self.session_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ShadowSession:
        """Deserialize from dictionary."""
        if "session_id" not in data:
            raise ValueError("ShadowSession requires 'session_id' field")
        return cls(
            session_id=data["session_id"],
            started_at=(
                datetime.fromisoformat(data["started_at"])
                if "started_at" in data
                else datetime.now(timezone.utc)
            ),
            ended_at=(
                datetime.fromisoformat(data["ended_at"])
                if data.get("ended_at")
                else None
            ),
            tool_calls=deque(
                (ShadowToolCall.from_dict(tc) for tc in data.get("tool_calls", [])),
                maxlen=10_000,
            ),
        )


class ShadowObserver:
    """Stateless observer that records and evaluates tool calls.

    The ShadowObserver classifies tool calls into categories, evaluates
    them against a reference constraint envelope (defaulting to the
    "software" template), and produces structured reports.

    The observer itself does not persist data — use
    :class:`~trustplane.shadow_store.ShadowStore` for persistence.

    Example:
        >>> observer = ShadowObserver()
        >>> session = ShadowSession()
        >>> observer.record(session, action="Read", resource="/src/main.py")
        >>> observer.record(session, action="Bash", resource="ls -la")
        >>> print(observer.generate_report(session))
    """

    def __init__(
        self,
        envelope: Optional[ConstraintEnvelope] = None,
        template_name: str = "software",
    ) -> None:
        """Initialize the shadow observer.

        Args:
            envelope: Custom constraint envelope to evaluate against.
                If None, uses the template specified by ``template_name``.
            template_name: Name of the constraint template to use as
                the reference envelope. Defaults to "software".
        """
        if envelope is not None:
            self._envelope = envelope
        else:
            try:
                self._envelope = get_template(template_name)
            except KeyError:
                logger.warning(
                    "Template '%s' not found, using empty envelope", template_name
                )
                self._envelope = ConstraintEnvelope()

    @property
    def envelope(self) -> ConstraintEnvelope:
        """The reference constraint envelope used for evaluation."""
        return self._envelope

    def record(
        self,
        session: ShadowSession,
        action: str,
        resource: str,
        category: Optional[str] = None,
    ) -> ShadowToolCall:
        """Record a tool call in the session.

        Classifies the call, evaluates it against the reference envelope,
        and appends it to the session's tool_calls list.

        Args:
            session: The session to record in.
            action: The tool/action name.
            resource: The resource being acted upon.
            category: Override the auto-classified category.

        Returns:
            The created ShadowToolCall.
        """
        if category is None:
            category = _classify_category(action, resource)

        would_be_blocked, would_be_held, reason = _evaluate_against_envelope(
            action, resource, category, self._envelope
        )

        tool_call = ShadowToolCall(
            action=action,
            resource=resource,
            category=category,
            would_be_blocked=would_be_blocked,
            would_be_held=would_be_held,
            reason=reason,
        )
        session.tool_calls.append(tool_call)

        if would_be_blocked:
            logger.info(
                "[SHADOW] WOULD BLOCK: action=%s resource=%s reason=%s",
                action,
                resource,
                reason,
            )
        elif would_be_held:
            logger.info(
                "[SHADOW] WOULD HOLD: action=%s resource=%s reason=%s",
                action,
                resource,
                reason,
            )

        return tool_call

    def generate_report(self, session: ShadowSession) -> str:
        """Generate a Markdown report for a shadow session.

        Args:
            session: The session to report on.

        Returns:
            Markdown-formatted report string.
        """
        return generate_report(session)

    def generate_report_json(self, session: ShadowSession) -> Dict[str, Any]:
        """Generate a JSON-serializable report for a shadow session.

        Args:
            session: The session to report on.

        Returns:
            Dictionary with report data.
        """
        return generate_report_json(session)

    def infer_constraints(self, session: ShadowSession) -> ConstraintEnvelope:
        """Infer a minimal ConstraintEnvelope from observed behavior.

        Args:
            session: The session to analyze.

        Returns:
            A ConstraintEnvelope covering the observed actions and resources.
        """
        return infer_constraints(session)


def generate_report(session: ShadowSession) -> str:
    """Generate a Markdown report for a shadow session.

    Groups tool calls by category, highlights blocked/held actions,
    and provides summary statistics.

    Args:
        session: The session to report on.

    Returns:
        Markdown-formatted report string.
    """
    calls = session.tool_calls
    total = len(calls)
    blocked = sum(1 for c in calls if c.would_be_blocked)
    held = sum(1 for c in calls if c.would_be_held)
    passed = total - blocked - held

    # Group by category
    categories: Dict[str, List[ShadowToolCall]] = {}
    for call in calls:
        categories.setdefault(call.category, []).append(call)

    lines: list[str] = []
    lines.append("# Shadow Mode Report")
    lines.append("")
    lines.append(f"**Session**: {session.session_id}")
    lines.append(f"**Started**: {session.started_at.isoformat()}")
    if session.ended_at:
        duration = session.ended_at - session.started_at
        lines.append(f"**Ended**: {session.ended_at.isoformat()}")
        lines.append(f"**Duration**: {duration}")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append(f"- **Total tool calls**: {total}")
    lines.append(f"- **Would pass**: {passed}")
    lines.append(f"- **Would be held**: {held}")
    lines.append(f"- **Would be blocked**: {blocked}")
    if total > 0:
        block_rate = (blocked / total) * 100
        lines.append(f"- **Block rate**: {block_rate:.1f}%")
    lines.append("")

    lines.append("## By Category")
    lines.append("")
    for cat in sorted(categories.keys()):
        cat_calls = categories[cat]
        cat_blocked = sum(1 for c in cat_calls if c.would_be_blocked)
        cat_held = sum(1 for c in cat_calls if c.would_be_held)
        lines.append(f"### {cat}")
        lines.append(f"  - Count: {len(cat_calls)}")
        if cat_blocked:
            lines.append(f"  - Would be blocked: {cat_blocked}")
        if cat_held:
            lines.append(f"  - Would be held: {cat_held}")
        lines.append("")

    # Detail blocked/held calls
    flagged_calls = [c for c in calls if c.would_be_blocked or c.would_be_held]
    if flagged_calls:
        lines.append("## Flagged Actions")
        lines.append("")
        for call in flagged_calls:
            status = "BLOCKED" if call.would_be_blocked else "HELD"
            lines.append(f"- **[{status}]** `{call.action}` on `{call.resource}`")
            if call.reason:
                lines.append(f"  - Reason: {call.reason}")
        lines.append("")

    return "\n".join(lines)


def generate_report_json(session: ShadowSession) -> Dict[str, Any]:
    """Generate a JSON-serializable report for a shadow session.

    Args:
        session: The session to report on.

    Returns:
        Dictionary with structured report data.
    """
    calls = session.tool_calls
    total = len(calls)
    blocked = sum(1 for c in calls if c.would_be_blocked)
    held = sum(1 for c in calls if c.would_be_held)
    passed = total - blocked - held

    # Group by category
    categories: Dict[str, int] = {}
    for call in calls:
        categories[call.category] = categories.get(call.category, 0) + 1

    flagged = [c.to_dict() for c in calls if c.would_be_blocked or c.would_be_held]

    return {
        "session_id": session.session_id,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "summary": {
            "total_calls": total,
            "passed": passed,
            "held": held,
            "blocked": blocked,
            "block_rate": (blocked / total * 100) if total > 0 else 0.0,
        },
        "categories": categories,
        "flagged_actions": flagged,
        "tool_calls": [c.to_dict() for c in calls],
    }


def infer_constraints(session: ShadowSession) -> ConstraintEnvelope:
    """Infer a minimal ConstraintEnvelope from observed behavior.

    Analyzes all tool calls in the session and produces a constraint
    envelope that would allow the observed behavior while blocking
    unobserved action types.

    Args:
        session: The session to analyze.

    Returns:
        A ConstraintEnvelope configured based on observed patterns.
    """
    observed_actions: set[str] = set()
    read_paths: set[str] = set()
    write_paths: set[str] = set()

    for call in session.tool_calls:
        observed_actions.add(call.action)

        if call.category == "file_read" and call.resource:
            # Extract directory prefix for read paths
            parts = call.resource.rsplit("/", 1)
            if len(parts) > 1:
                read_paths.add(parts[0] + "/")
            else:
                read_paths.add(call.resource)

        elif call.category == "file_write" and call.resource:
            parts = call.resource.rsplit("/", 1)
            if len(parts) > 1:
                write_paths.add(parts[0] + "/")
            else:
                write_paths.add(call.resource)

    return ConstraintEnvelope(
        operational=OperationalConstraints(
            allowed_actions=sorted(observed_actions),
            blocked_actions=[],
        ),
        data_access=DataAccessConstraints(
            read_paths=sorted(read_paths),
            write_paths=sorted(write_paths),
            blocked_paths=[],
            blocked_patterns=["*.key", "*.env", "credentials*"],
        ),
        financial=FinancialConstraints(budget_tracking=True),
        temporal=TemporalConstraints(),
        communication=CommunicationConstraints(),
        signed_by="shadow-inferred",
    )
