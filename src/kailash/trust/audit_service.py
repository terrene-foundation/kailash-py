# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP Audit Query Service.

Provides high-level query and analysis capabilities for audit records,
enabling compliance reporting and forensic investigation.

Key Capabilities:
- Agent history queries with filtering
- Action chain reconstruction
- Compliance report generation
- Statistical analysis
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.trust.audit_store import AuditStore, AuditStoreError
from kailash.trust.chain import ActionResult, AuditAnchor


@dataclass
class ActionSummary:
    """Summary of a specific action type."""

    action: str
    total_count: int
    success_count: int
    failure_count: int
    denied_count: int
    partial_count: int
    first_occurrence: Optional[datetime] = None
    last_occurrence: Optional[datetime] = None


@dataclass
class AgentAuditSummary:
    """Summary of an agent's audit activity."""

    agent_id: str
    total_actions: int
    unique_actions: List[str]
    action_summaries: Dict[str, ActionSummary]
    first_action: Optional[datetime] = None
    last_action: Optional[datetime] = None
    success_rate: float = 0.0


@dataclass
class ComplianceReport:
    """
    Compliance report for a time period.

    Contains aggregate statistics and detailed breakdowns
    for compliance auditing purposes.
    """

    start_time: datetime
    end_time: datetime
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # High-level statistics
    total_actions: int = 0
    total_agents: int = 0
    unique_actions: int = 0

    # Result breakdown
    success_count: int = 0
    failure_count: int = 0
    denied_count: int = 0
    partial_count: int = 0

    # By-agent breakdown
    agent_summaries: Dict[str, AgentAuditSummary] = field(default_factory=dict)

    # By-action breakdown
    action_summaries: Dict[str, ActionSummary] = field(default_factory=dict)

    # Trust events
    trust_established_count: int = 0
    trust_delegated_count: int = 0
    trust_revoked_count: int = 0

    # Compliance flags
    any_violations: bool = False
    violation_details: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate overall success rate."""
        if self.total_actions == 0:
            return 0.0
        return self.success_count / self.total_actions

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "generated_at": self.generated_at.isoformat(),
            "total_actions": self.total_actions,
            "total_agents": self.total_agents,
            "unique_actions": self.unique_actions,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "denied_count": self.denied_count,
            "partial_count": self.partial_count,
            "success_rate": self.success_rate,
            "trust_established_count": self.trust_established_count,
            "trust_delegated_count": self.trust_delegated_count,
            "trust_revoked_count": self.trust_revoked_count,
            "any_violations": self.any_violations,
            "violation_count": len(self.violation_details),
        }


class AuditQueryService:
    """
    Service for querying and analyzing audit records.

    Provides high-level query capabilities on top of the audit store,
    enabling compliance reporting and forensic analysis.

    Example:
        >>> service = AuditQueryService(audit_store)
        >>>
        >>> # Get agent history
        >>> history = await service.get_agent_history(
        ...     "agent-001",
        ...     start_time=datetime(2025, 1, 1),
        ...     actions=["analyze_data", "generate_report"],
        ... )
        >>>
        >>> # Get action chain
        >>> chain = await service.get_action_chain("aud-001")
        >>>
        >>> # Generate compliance report
        >>> report = await service.generate_compliance_report(
        ...     start_time=datetime(2025, 1, 1),
        ...     end_time=datetime(2025, 1, 31),
        ... )
    """

    def __init__(self, audit_store: AuditStore):
        """
        Initialize AuditQueryService.

        Args:
            audit_store: The audit store to query
        """
        self.audit_store = audit_store

    async def get_agent_history(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        actions: Optional[List[str]] = None,
        results: Optional[List[ActionResult]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditAnchor]:
        """
        Get audit history for an agent with flexible filtering.

        Args:
            agent_id: Agent to query
            start_time: Filter by start time
            end_time: Filter by end time
            actions: Filter by action types
            results: Filter by action results
            limit: Maximum results
            offset: Pagination offset

        Returns:
            List of AuditAnchors ordered by timestamp descending
        """
        # Get from store
        anchors = await self.audit_store.get_agent_history(
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            actions=actions,
            limit=limit,
            offset=offset,
        )

        # Apply result filter if specified
        if results:
            anchors = [a for a in anchors if a.result in results]

        return anchors

    async def get_action_chain(
        self,
        anchor_id: str,
    ) -> List[AuditAnchor]:
        """
        Get the full chain of related actions.

        Traverses parent_anchor_id links to build the complete
        causal chain from root action to the specified anchor.

        Args:
            anchor_id: Starting anchor ID

        Returns:
            List of AuditAnchors from root to anchor_id (oldest first)
        """
        return await self.audit_store.get_action_chain(anchor_id)

    async def get_agent_summary(
        self,
        agent_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> AgentAuditSummary:
        """
        Get a summary of an agent's audit activity.

        Args:
            agent_id: Agent to summarize
            start_time: Filter by start time
            end_time: Filter by end time

        Returns:
            AgentAuditSummary with statistics
        """
        # Get all history for the agent (may need pagination for large histories)
        history = await self.audit_store.get_agent_history(
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000,  # Large limit to get full history
        )

        if not history:
            return AgentAuditSummary(
                agent_id=agent_id,
                total_actions=0,
                unique_actions=[],
                action_summaries={},
            )

        # Build action summaries
        action_stats = defaultdict(
            lambda: {
                "total": 0,
                "success": 0,
                "failure": 0,
                "denied": 0,
                "partial": 0,
                "first": None,
                "last": None,
            }
        )

        for anchor in history:
            stats = action_stats[anchor.action]
            stats["total"] += 1

            if anchor.result == ActionResult.SUCCESS:
                stats["success"] += 1
            elif anchor.result == ActionResult.FAILURE:
                stats["failure"] += 1
            elif anchor.result == ActionResult.DENIED:
                stats["denied"] += 1
            elif anchor.result == ActionResult.PARTIAL:
                stats["partial"] += 1

            if stats["first"] is None or anchor.timestamp < stats["first"]:
                stats["first"] = anchor.timestamp
            if stats["last"] is None or anchor.timestamp > stats["last"]:
                stats["last"] = anchor.timestamp

        # Build action summaries
        action_summaries = {}
        for action, stats in action_stats.items():
            action_summaries[action] = ActionSummary(
                action=action,
                total_count=stats["total"],
                success_count=stats["success"],
                failure_count=stats["failure"],
                denied_count=stats["denied"],
                partial_count=stats["partial"],
                first_occurrence=stats["first"],
                last_occurrence=stats["last"],
            )

        # Calculate totals
        total_actions = len(history)
        success_count = sum(1 for a in history if a.result == ActionResult.SUCCESS)

        return AgentAuditSummary(
            agent_id=agent_id,
            total_actions=total_actions,
            unique_actions=list(action_stats.keys()),
            action_summaries=action_summaries,
            first_action=min(a.timestamp for a in history) if history else None,
            last_action=max(a.timestamp for a in history) if history else None,
            success_rate=success_count / total_actions if total_actions > 0 else 0.0,
        )

    async def generate_compliance_report(
        self,
        start_time: datetime,
        end_time: datetime,
        authority_id: Optional[str] = None,
    ) -> ComplianceReport:
        """
        Generate a compliance report for a time period.

        Args:
            start_time: Report start time
            end_time: Report end time
            authority_id: Optional filter by authority

        Returns:
            ComplianceReport with aggregate statistics
        """
        report = ComplianceReport(
            start_time=start_time,
            end_time=end_time,
        )

        # Get all audits for the time period
        # Note: In production, this would need to be paginated and streamed
        all_anchors = await self._get_all_audits_in_range(start_time, end_time)

        if not all_anchors:
            return report

        # Track unique agents and actions
        agents = set()
        actions = set()
        action_stats = defaultdict(
            lambda: {
                "total": 0,
                "success": 0,
                "failure": 0,
                "denied": 0,
                "partial": 0,
            }
        )

        # Process all anchors
        for anchor in all_anchors:
            agents.add(anchor.agent_id)
            actions.add(anchor.action)
            report.total_actions += 1

            # Count by result
            if anchor.result == ActionResult.SUCCESS:
                report.success_count += 1
                action_stats[anchor.action]["success"] += 1
            elif anchor.result == ActionResult.FAILURE:
                report.failure_count += 1
                action_stats[anchor.action]["failure"] += 1
            elif anchor.result == ActionResult.DENIED:
                report.denied_count += 1
                action_stats[anchor.action]["denied"] += 1
                # Denied actions might indicate violations
                report.any_violations = True
                report.violation_details.append(
                    {
                        "anchor_id": anchor.id,
                        "agent_id": anchor.agent_id,
                        "action": anchor.action,
                        "timestamp": anchor.timestamp.isoformat(),
                        "reason": "Action denied",
                    }
                )
            elif anchor.result == ActionResult.PARTIAL:
                report.partial_count += 1
                action_stats[anchor.action]["partial"] += 1

            action_stats[anchor.action]["total"] += 1

            # Count trust events
            if anchor.action == "trust_established":
                report.trust_established_count += 1
            elif anchor.action == "trust_delegated":
                report.trust_delegated_count += 1
            elif anchor.action == "trust_revoked":
                report.trust_revoked_count += 1

        # Set aggregate values
        report.total_agents = len(agents)
        report.unique_actions = len(actions)

        # Build action summaries
        for action, stats in action_stats.items():
            report.action_summaries[action] = ActionSummary(
                action=action,
                total_count=stats["total"],
                success_count=stats["success"],
                failure_count=stats["failure"],
                denied_count=stats["denied"],
                partial_count=stats["partial"],
            )

        return report

    async def _get_all_audits_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
    ) -> List[AuditAnchor]:
        """
        Get all audits in a time range.

        Note: This is a simplified implementation. In production,
        this would need pagination and streaming for large datasets.

        Args:
            start_time: Start of range
            end_time: End of range

        Returns:
            List of all matching AuditAnchors
        """
        # Query by common actions (would need improvement for production)
        # In production, we'd have a dedicated time-range query method
        all_anchors = []

        # Get via different actions - this is a workaround
        # Ideally, AuditStore would have a time-range query
        common_actions = [
            "trust_established",
            "trust_delegated",
            "trust_received",
            "trust_revoked",
            "analyze_data",
            "generate_report",
            "query_data",
            "export_data",
        ]

        seen_ids = set()
        for action in common_actions:
            try:
                anchors = await self.audit_store.query_by_action(
                    action=action,
                    start_time=start_time,
                    end_time=end_time,
                    limit=10000,
                )
                for anchor in anchors:
                    if anchor.id not in seen_ids:
                        seen_ids.add(anchor.id)
                        all_anchors.append(anchor)
            except AuditStoreError:
                # Action may not exist, continue
                pass

        return all_anchors

    async def get_unattested_reasoning(self) -> List[AuditAnchor]:
        """
        Return audit anchors that are missing reasoning traces.

        Scans all audit records in the store and returns the AuditAnchor
        objects whose ``reasoning_trace`` field is None.  Useful for
        compliance queries such as "show all actions without reasoning
        traces".

        Returns:
            List of AuditAnchor objects that lack a reasoning trace.
        """
        missing: List[AuditAnchor] = []

        # The underlying store may be an AppendOnlyAuditStore (with
        # list_records) or an AuditStore ABC implementation.  We use
        # the common interface: list_records if available, otherwise
        # fall back to iterating via the internal _records list.
        if hasattr(self.audit_store, "list_records"):
            records = await self.audit_store.list_records(limit=100000)
            for record in records:
                if record.anchor.reasoning_trace is None:
                    missing.append(record.anchor)
        else:
            # For ABC implementations that may not have list_records,
            # we cannot iterate without a query. Raise a clear error.
            raise NotImplementedError(
                "get_unattested_reasoning() requires an audit store with "
                "list_records() support (e.g., AppendOnlyAuditStore). "
                f"Got: {type(self.audit_store).__name__}"
            )

        return missing

    async def find_related_actions(
        self,
        anchor_id: str,
        max_depth: int = 10,
    ) -> List[AuditAnchor]:
        """
        Find all actions related to a given anchor.

        Includes both ancestors (via parent_anchor_id) and
        potentially descendants (actions that reference this anchor).

        Args:
            anchor_id: Starting anchor ID
            max_depth: Maximum chain depth to traverse

        Returns:
            List of related AuditAnchors
        """
        related = []

        # Get ancestor chain
        try:
            chain = await self.get_action_chain(anchor_id)
            related.extend(chain)
        except AuditStoreError:
            pass

        return related

    async def get_audit_count_by_period(
        self,
        agent_id: str,
        start_time: datetime,
        end_time: datetime,
        period_hours: int = 24,
    ) -> List[Dict[str, Any]]:
        """
        Get audit counts grouped by time periods.

        Args:
            agent_id: Agent to query
            start_time: Start of range
            end_time: End of range
            period_hours: Size of each period in hours

        Returns:
            List of period summaries with counts
        """
        history = await self.audit_store.get_agent_history(
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
            limit=10000,
        )

        # Group by period
        from datetime import timedelta

        period_delta = timedelta(hours=period_hours)

        periods = []
        current_start = start_time

        while current_start < end_time:
            current_end = min(current_start + period_delta, end_time)

            # Count actions in this period
            period_anchors = [a for a in history if current_start <= a.timestamp < current_end]

            periods.append(
                {
                    "period_start": current_start.isoformat(),
                    "period_end": current_end.isoformat(),
                    "total_actions": len(period_anchors),
                    "success_count": sum(1 for a in period_anchors if a.result == ActionResult.SUCCESS),
                    "failure_count": sum(1 for a in period_anchors if a.result == ActionResult.FAILURE),
                }
            )

            current_start = current_end

        return periods
