# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Shadow enforcement for gradual EATP rollout.

Runs VERIFY operations but never blocks execution. Logs all verdicts
and collects metrics for analysis. Designed for gradual enterprise
rollout: deploy in shadow mode, review verdicts, then switch to strict.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.trust.chain import VerificationResult
from kailash.trust.enforce.strict import EnforcementRecord, StrictEnforcer, Verdict

logger = logging.getLogger(__name__)


@dataclass
class ShadowMetrics:
    """Metrics collected during shadow enforcement."""

    total_checks: int = 0
    auto_approved_count: int = 0
    flagged_count: int = 0
    held_count: int = 0
    blocked_count: int = 0
    first_check: Optional[datetime] = None
    last_check: Optional[datetime] = None

    # Reasoning trace metrics
    reasoning_present_count: int = 0
    reasoning_absent_count: int = 0
    reasoning_verification_failed_count: int = 0

    # Verdict change tracking
    verdict_changes: int = 0
    last_verdict: Optional[str] = None

    @property
    def change_rate(self) -> float:
        """Rate of verdict changes between consecutive checks.

        Returns 0.0 if fewer than 2 checks. Otherwise returns the ratio
        of verdict transitions to possible transitions (total_checks - 1).
        """
        possible_transitions = self.total_checks - 1
        if possible_transitions <= 0:
            return 0.0
        return self.verdict_changes / possible_transitions

    @property
    def block_rate(self) -> float:
        """Percentage of checks that would have been blocked."""
        if self.total_checks == 0:
            return 0.0
        return (self.blocked_count / self.total_checks) * 100

    @property
    def hold_rate(self) -> float:
        """Percentage of checks that would have been held."""
        if self.total_checks == 0:
            return 0.0
        return (self.held_count / self.total_checks) * 100

    @property
    def pass_rate(self) -> float:
        """Percentage of checks that passed (auto_approved + flagged)."""
        if self.total_checks == 0:
            return 0.0
        passed = self.auto_approved_count + self.flagged_count
        return (passed / self.total_checks) * 100


class ShadowEnforcer:
    """Shadow mode enforcer that logs but never blocks.

    Runs the same classification logic as StrictEnforcer but always
    allows execution. Collects metrics on what WOULD have been blocked,
    held, or flagged for analysis before switching to strict enforcement.

    Example:
        >>> from kailash.trust.enforce.shadow import ShadowEnforcer
        >>> shadow = ShadowEnforcer()
        >>> # Always returns verdict without raising
        >>> verdict = shadow.check(agent_id="agent-001", action="read_data", result=result)
        >>> # After collecting data:
        >>> print(shadow.report())
    """

    def __init__(self, flag_threshold: int = 1, maxlen: int = 10_000):
        """Initialize shadow enforcer.

        Args:
            flag_threshold: Violation count that would trigger HELD in strict mode
            maxlen: Maximum number of records to retain (oldest 10% trimmed on overflow)
        """
        self._classifier = StrictEnforcer(flag_threshold=flag_threshold)
        self._metrics = ShadowMetrics()
        self._records: List[EnforcementRecord] = []
        self._max_records = maxlen

    def check(
        self,
        agent_id: str,
        action: str,
        result: VerificationResult,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Verdict:
        """Check a verification result without enforcing.

        Always allows execution. Logs what would have happened under
        strict enforcement and updates metrics.

        Args:
            agent_id: The agent being verified
            action: The action being verified
            result: The verification result
            metadata: Additional context

        Returns:
            The verdict that WOULD have been enforced
        """
        now = datetime.now(timezone.utc)
        self._metrics.total_checks += 1
        if self._metrics.first_check is None:
            self._metrics.first_check = now
        self._metrics.last_check = now

        try:
            verdict = self._classifier.classify(result)
        except Exception:
            logger.exception(
                f"[SHADOW] Classification failed for agent={agent_id} action={action} — returning BLOCKED as fail-safe"
            )
            verdict = Verdict.BLOCKED

        record = EnforcementRecord(
            agent_id=agent_id,
            action=action,
            verdict=verdict,
            verification_result=result,
            timestamp=now,
            metadata=metadata or {},
        )
        self._records.append(record)

        # Bounded memory: trim oldest 10% when exceeding maxlen
        if len(self._records) > self._max_records:
            trim_count = self._max_records // 10
            self._records = self._records[trim_count:]

        # Track verdict changes
        verdict_value = verdict.value
        if self._metrics.last_verdict is not None and verdict_value != self._metrics.last_verdict:
            self._metrics.verdict_changes += 1
        self._metrics.last_verdict = verdict_value

        if verdict == Verdict.AUTO_APPROVED:
            self._metrics.auto_approved_count += 1
        elif verdict == Verdict.FLAGGED:
            self._metrics.flagged_count += 1
            logger.info(f"[SHADOW] WOULD FLAG: agent={agent_id} action={action} violations={len(result.violations)}")
        elif verdict == Verdict.HELD:
            self._metrics.held_count += 1
            logger.warning(f"[SHADOW] WOULD HOLD: agent={agent_id} action={action} violations={len(result.violations)}")
        elif verdict == Verdict.BLOCKED:
            self._metrics.blocked_count += 1
            logger.warning(f"[SHADOW] WOULD BLOCK: agent={agent_id} action={action} reason={result.reason}")

        # Track reasoning trace metrics (only when explicitly set, not None)
        if result.reasoning_present is True:
            self._metrics.reasoning_present_count += 1
        elif result.reasoning_present is False:
            self._metrics.reasoning_absent_count += 1
        # None means legacy result — do not count

        if result.reasoning_verified is False:
            self._metrics.reasoning_verification_failed_count += 1

        return verdict

    @property
    def metrics(self) -> ShadowMetrics:
        """Get current shadow metrics."""
        return self._metrics

    @property
    def records(self) -> List[EnforcementRecord]:
        """Get all shadow enforcement records."""
        return list(self._records)

    def report(self) -> str:
        """Generate a human-readable shadow enforcement report.

        Returns:
            Formatted report string
        """
        m = self._metrics
        lines = [
            "EATP Shadow Enforcement Report",
            "=" * 40,
            f"Total checks:     {m.total_checks}",
            f"Auto-approved:    {m.auto_approved_count} ({m.pass_rate:.1f}% pass rate)",
            f"Flagged:          {m.flagged_count}",
            f"Would hold:       {m.held_count} ({m.hold_rate:.1f}%)",
            f"Would block:      {m.blocked_count} ({m.block_rate:.1f}%)",
        ]

        if m.first_check and m.last_check:
            duration = m.last_check - m.first_check
            lines.append(f"Observation period: {duration}")

        # Top blocked agents
        blocked_agents: Dict[str, int] = {}
        for record in self._records:
            if record.verdict == Verdict.BLOCKED:
                blocked_agents[record.agent_id] = blocked_agents.get(record.agent_id, 0) + 1

        if blocked_agents:
            lines.append("")
            lines.append("Top blocked agents:")
            for agent_id, count in sorted(blocked_agents.items(), key=lambda x: x[1], reverse=True)[:5]:
                lines.append(f"  {agent_id}: {count} blocks")

        # Reasoning trace metrics
        reasoning_total = m.reasoning_present_count + m.reasoning_absent_count
        if reasoning_total > 0:
            lines.append("")
            lines.append("Reasoning trace metrics:")
            lines.append(f"  Reasoning present:  {m.reasoning_present_count}")
            lines.append(f"  Reasoning absent:   {m.reasoning_absent_count}")
            if m.reasoning_verification_failed_count > 0:
                lines.append(f"  Reasoning verification failures: {m.reasoning_verification_failed_count}")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset metrics and records."""
        self._metrics = ShadowMetrics()
        self._records.clear()


__all__ = [
    "ShadowEnforcer",
    "ShadowMetrics",
]
