"""
External Agent Approval Manager for Kaizen Framework.

Extends ToolApprovalManager patterns for external agent invocation approvals.
Supports cost-based, environment-based, and sensitivity-based approval triggers.

Design Principle: Leverage existing Kaizen permission systems while extending
for external agent contexts (Copilot, custom enterprise tools, third-party AI).
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.permissions.context import ExecutionContext

logger = logging.getLogger(__name__)


class ApprovalLevel(Enum):
    """
    Approval routing levels for external agent invocations.

    Determines which users/roles are authorized to approve external agent requests.
    """

    TEAM_LEAD = "team_lead"
    """
    Route approval to team lead(s) of the requesting user.

    Use case: Standard operations within team scope
    """

    ADMIN = "admin"
    """
    Route approval to organization administrator(s).

    Use case: Organization-wide sensitive operations
    """

    OWNER = "owner"
    """
    Route approval to organization owner.

    Use case: Critical operations requiring highest authority
    """

    CUSTOM = "custom"
    """
    Route approval to custom approver list.

    Use case: Specific approval workflows with designated approvers
    """


@dataclass
class ApprovalRequirement:
    """
    Configuration for when external agent approval is required.

    Defines trigger conditions based on cost, environment, data classification,
    and operation type. Multiple conditions can be specified (OR logic).

    Examples:
        >>> # Require approval for production environments
        >>> req = ApprovalRequirement(
        ...     require_for_environments=["production"],
        ...     approval_level=ApprovalLevel.TEAM_LEAD,
        ...     approval_timeout_seconds=3600
        ... )

        >>> # Require approval for high-cost operations
        >>> req = ApprovalRequirement(
        ...     require_for_cost_above=10.0,
        ...     approval_level=ApprovalLevel.ADMIN,
        ...     approval_timeout_seconds=1800
        ... )

        >>> # Require approval for confidential data
        >>> req = ApprovalRequirement(
        ...     require_for_data_classifications=["confidential", "restricted"],
        ...     approval_level=ApprovalLevel.OWNER,
        ...     approval_timeout_seconds=7200
        ... )
    """

    approval_level: ApprovalLevel
    """Which level/role should approve (TEAM_LEAD, ADMIN, OWNER, CUSTOM)"""

    require_for_environments: list[str] = field(default_factory=list)
    """
    Require approval when executing in these environments.

    Example: ["production", "staging"]
    """

    require_for_cost_above: Optional[float] = None
    """
    Require approval when estimated cost exceeds this threshold (USD).

    Example: 10.0 = require approval if cost > $10.00
    """

    require_for_data_classifications: list[str] = field(default_factory=list)
    """
    Require approval when accessing data with these classifications.

    Example: ["confidential", "restricted", "pii"]
    """

    require_for_operations: list[str] = field(default_factory=list)
    """
    Require approval for these specific operations.

    Example: ["delete", "export", "bulk_update"]
    """

    custom_approvers: list[str] = field(default_factory=list)
    """
    Custom approver user IDs (only used when approval_level=CUSTOM).

    Example: ["user_001", "user_002"]
    """

    approval_timeout_seconds: int = 3600
    """
    Timeout for approval decision (default: 1 hour).

    After timeout, approval request is marked as TIMEOUT and execution denied.
    """

    approval_reason: Optional[str] = None
    """
    Human-readable reason for requiring approval.

    Example: "Production deployment requires team lead approval"
    """


class ApprovalStatus(Enum):
    """Status of an external agent approval request."""

    PENDING = "pending"
    """Approval request created, awaiting decision"""

    APPROVED = "approved"
    """Approval granted by authorized approver"""

    REJECTED = "rejected"
    """Approval denied by authorized approver"""

    TIMEOUT = "timeout"
    """Approval request timed out without decision"""


@dataclass
class ExternalAgentApprovalRequest:
    """
    Represents a pending or completed approval request.

    This dataclass is used for in-memory representation. For persistence,
    use the DataFlow model (ExternalAgentApprovalRequestModel).
    """

    id: str
    """Unique approval request ID"""

    external_agent_id: str
    """ID of the external agent being invoked"""

    requested_by: str
    """User ID who requested the agent invocation"""

    approvers: list[str]
    """List of user IDs authorized to approve this request"""

    status: ApprovalStatus
    """Current approval status"""

    approval_reason: str
    """Reason why approval is required"""

    request_metadata: dict[str, Any]
    """Metadata about the request (cost, environment, operation, etc.)"""

    created_at: datetime
    """When the approval request was created"""

    approved_at: Optional[datetime] = None
    """When the approval was granted/rejected (None if pending)"""

    approved_by: Optional[str] = None
    """User ID who made the approval decision (None if pending)"""

    rejection_reason: Optional[str] = None
    """Reason for rejection (only if status=REJECTED)"""


class ExternalAgentApprovalManager:
    """
    Manages approval workflows for external agent invocations.

    Extends ToolApprovalManager patterns with external agent-specific features:
    - Cost-based approval triggers
    - Environment-based approval routing
    - Data classification-based approvals
    - Async approval tracking with timeouts
    - Approval decision recording with audit trail

    This manager integrates with:
    - ControlProtocol: For bidirectional approval communication
    - ExecutionContext: For budget and permission state
    - DataFlow: For persistent approval request storage (optional)

    Examples:
        >>> # Setup with Control Protocol
        >>> transport = CLITransport()
        >>> protocol = ControlProtocol(transport=transport)
        >>> await protocol.start(tg)
        >>>
        >>> manager = ExternalAgentApprovalManager(protocol)
        >>>
        >>> # Configure approval requirement
        >>> requirement = ApprovalRequirement(
        ...     require_for_environments=["production"],
        ...     approval_level=ApprovalLevel.TEAM_LEAD,
        ...     approval_timeout_seconds=1800
        ... )
        >>> manager.add_requirement("copilot_agent_001", requirement)
        >>>
        >>> # Check if approval required
        >>> metadata = {
        ...     "cost": 15.00,
        ...     "environment": "production",
        ...     "operation": "data_export"
        ... }
        >>> required, req = manager.determine_if_approval_required(
        ...     "copilot_agent_001",
        ...     metadata
        ... )
        >>> if required:
        ...     # Request approval
        ...     request_id = await manager.request_approval(
        ...         "copilot_agent_001",
        ...         "user_123",
        ...         metadata
        ...     )
        ...     # Wait for approval (with timeout)
        ...     approved = await manager.wait_for_approval(request_id, timeout=1800)
    """

    def __init__(
        self,
        control_protocol: Optional[ControlProtocol] = None,
        storage_backend=None,
    ):
        """
        Initialize External Agent Approval Manager.

        Args:
            control_protocol: Control Protocol instance for bidirectional communication
                             (optional for testing, required for production)
            storage_backend: DataFlow storage backend for persistent approval tracking
                           (optional, uses in-memory storage if None)
        """
        self.protocol = control_protocol
        self.storage = storage_backend

        # In-memory approval requirements (external_agent_id -> ApprovalRequirement)
        self._requirements: dict[str, ApprovalRequirement] = {}

        # In-memory approval requests (request_id -> ExternalAgentApprovalRequest)
        self._requests: dict[str, ExternalAgentApprovalRequest] = {}

        # Mock user/team data for approval routing (production would use database)
        self._user_teams: dict[str, str] = {}  # user_id -> team_id
        self._team_leads: dict[str, list[str]] = {}  # team_id -> [user_ids]
        self._org_admins: list[str] = []
        self._org_owner: Optional[str] = None

        logger.debug("ExternalAgentApprovalManager initialized")

    def add_requirement(
        self, external_agent_id: str, requirement: ApprovalRequirement
    ) -> None:
        """
        Add approval requirement for an external agent.

        Args:
            external_agent_id: ID of the external agent
            requirement: Approval requirement configuration

        Examples:
            >>> requirement = ApprovalRequirement(
            ...     require_for_cost_above=10.0,
            ...     approval_level=ApprovalLevel.ADMIN
            ... )
            >>> manager.add_requirement("copilot_001", requirement)
        """
        self._requirements[external_agent_id] = requirement
        logger.info(
            f"Added approval requirement for agent '{external_agent_id}': "
            f"level={requirement.approval_level.value}"
        )

    def determine_if_approval_required(
        self, external_agent_id: str, metadata: dict[str, Any]
    ) -> tuple[bool, Optional[ApprovalRequirement]]:
        """
        Determine if approval is required for external agent invocation.

        Checks all trigger conditions in ApprovalRequirement:
        - Cost threshold (require_for_cost_above)
        - Environment (require_for_environments)
        - Data classification (require_for_data_classifications)
        - Operation type (require_for_operations)

        Returns True if ANY condition matches (OR logic).

        Args:
            external_agent_id: ID of the external agent
            metadata: Request metadata with cost, environment, operation, etc.

        Returns:
            Tuple of (approval_required: bool, requirement: ApprovalRequirement or None)

        Examples:
            >>> metadata = {
            ...     "cost": 15.00,
            ...     "environment": "production",
            ...     "operation": "export"
            ... }
            >>> required, req = manager.determine_if_approval_required(
            ...     "copilot_001",
            ...     metadata
            ... )
            >>> if required:
            ...     print(f"Approval needed: {req.approval_reason}")
        """
        # Check if agent has approval requirement configured
        requirement = self._requirements.get(external_agent_id)
        if not requirement:
            logger.debug(
                f"No approval requirement for agent '{external_agent_id}', approval not required"
            )
            return False, None

        # Extract metadata fields
        cost = metadata.get("cost", 0.0)
        environment = metadata.get("environment", "")
        data_classifications = metadata.get("data_classifications", [])
        operation = metadata.get("operation", "")

        # Check cost threshold
        if requirement.require_for_cost_above is not None:
            if cost > requirement.require_for_cost_above:
                logger.info(
                    f"Approval required for '{external_agent_id}': "
                    f"cost ${cost:.2f} > ${requirement.require_for_cost_above:.2f}"
                )
                return True, requirement

        # Check environment
        if requirement.require_for_environments:
            if environment in requirement.require_for_environments:
                logger.info(
                    f"Approval required for '{external_agent_id}': "
                    f"environment '{environment}' requires approval"
                )
                return True, requirement

        # Check data classifications (any overlap)
        if requirement.require_for_data_classifications:
            if set(data_classifications) & set(
                requirement.require_for_data_classifications
            ):
                logger.info(
                    f"Approval required for '{external_agent_id}': "
                    f"data classifications {data_classifications} include restricted classifications"
                )
                return True, requirement

        # Check operation type
        if requirement.require_for_operations:
            if operation in requirement.require_for_operations:
                logger.info(
                    f"Approval required for '{external_agent_id}': "
                    f"operation '{operation}' requires approval"
                )
                return True, requirement

        # No conditions matched
        logger.debug(
            f"No approval conditions matched for '{external_agent_id}', approval not required"
        )
        return False, None

    async def request_approval(
        self,
        external_agent_id: str,
        requested_by: str,
        metadata: dict[str, Any],
    ) -> str:
        """
        Create approval request and route to appropriate approvers.

        Creates ExternalAgentApprovalRequest record, determines approvers based on
        approval_level, and optionally sends notifications via webhook/email.

        Args:
            external_agent_id: ID of the external agent
            requested_by: User ID requesting the invocation
            metadata: Request metadata (cost, environment, operation, etc.)

        Returns:
            Approval request ID (UUID string)

        Raises:
            ValueError: If no approval requirement configured for agent
            ValueError: If no approvers found for approval level

        Examples:
            >>> request_id = await manager.request_approval(
            ...     "copilot_001",
            ...     "user_123",
            ...     {"cost": 15.00, "environment": "production"}
            ... )
            >>> print(f"Approval request created: {request_id}")
        """
        # Get approval requirement
        requirement = self._requirements.get(external_agent_id)
        if not requirement:
            raise ValueError(
                f"No approval requirement configured for agent '{external_agent_id}'"
            )

        # Determine approvers
        approvers = self._get_approvers(
            requirement.approval_level, requested_by, requirement.custom_approvers
        )
        if not approvers:
            raise ValueError(
                f"No approvers found for approval level '{requirement.approval_level.value}'"
            )

        # Generate request ID
        import uuid

        request_id = str(uuid.uuid4())

        # Create approval request
        approval_request = ExternalAgentApprovalRequest(
            id=request_id,
            external_agent_id=external_agent_id,
            requested_by=requested_by,
            approvers=approvers,
            status=ApprovalStatus.PENDING,
            approval_reason=requirement.approval_reason
            or "External agent invocation requires approval",
            request_metadata=metadata,
            created_at=datetime.now(timezone.utc),
        )

        # Store in memory (or database if storage_backend configured)
        self._requests[request_id] = approval_request
        if self.storage:
            await self.storage.save(approval_request)

        logger.info(
            f"Created approval request {request_id} for agent '{external_agent_id}' "
            f"requested by '{requested_by}', approvers: {approvers}"
        )

        # Send notifications to approvers (if protocol configured)
        if self.protocol:
            await self.send_approval_notification(request_id, approvers)

        return request_id

    def _get_approvers(
        self,
        approval_level: ApprovalLevel,
        user_id: str,
        custom_approvers: list[str],
    ) -> list[str]:
        """
        Get list of approver user IDs based on approval level.

        Routing logic:
        - TEAM_LEAD: Query team leads for user's team
        - ADMIN: Query organization administrators
        - OWNER: Query organization owner
        - CUSTOM: Use custom_approvers list

        Args:
            approval_level: Approval level (TEAM_LEAD, ADMIN, OWNER, CUSTOM)
            user_id: User ID requesting approval
            custom_approvers: Custom approver list (for CUSTOM level)

        Returns:
            List of approver user IDs

        Examples:
            >>> # Team lead approval
            >>> manager._user_teams = {"user_123": "team_001"}
            >>> manager._team_leads = {"team_001": ["lead_001", "lead_002"]}
            >>> approvers = manager._get_approvers(
            ...     ApprovalLevel.TEAM_LEAD,
            ...     "user_123",
            ...     []
            ... )
            >>> assert approvers == ["lead_001", "lead_002"]
        """
        if approval_level == ApprovalLevel.TEAM_LEAD:
            # Get user's team
            team_id = self._user_teams.get(user_id)
            if not team_id:
                logger.warning(
                    f"User '{user_id}' not assigned to any team, cannot determine team leads"
                )
                return []

            # Get team leads for team
            leads = self._team_leads.get(team_id, [])
            logger.debug(f"Team '{team_id}' leads: {leads}")
            return leads

        elif approval_level == ApprovalLevel.ADMIN:
            logger.debug(f"Organization admins: {self._org_admins}")
            return self._org_admins.copy()

        elif approval_level == ApprovalLevel.OWNER:
            if not self._org_owner:
                logger.warning("Organization owner not configured")
                return []
            logger.debug(f"Organization owner: {self._org_owner}")
            return [self._org_owner]

        elif approval_level == ApprovalLevel.CUSTOM:
            logger.debug(f"Custom approvers: {custom_approvers}")
            return custom_approvers.copy()

        else:
            logger.error(f"Unknown approval level: {approval_level}")
            return []

    async def send_approval_notification(
        self, approval_request_id: str, approvers: list[str]
    ) -> None:
        """
        Send approval notification to approvers via webhook or email.

        Sends notification containing:
        - Approval request ID
        - External agent name
        - Requested by user
        - Cost estimate
        - Environment
        - Operation
        - Approve/reject URLs (or CLI commands)

        Args:
            approval_request_id: ID of the approval request
            approvers: List of approver user IDs

        Examples:
            >>> await manager.send_approval_notification(
            ...     "req_123",
            ...     ["approver_001", "approver_002"]
            ... )
        """
        request = self._requests.get(approval_request_id)
        if not request:
            logger.error(
                f"Cannot send notification: approval request '{approval_request_id}' not found"
            )
            return

        # Build notification payload
        notification = {
            "approval_request_id": approval_request_id,
            "external_agent_id": request.external_agent_id,
            "requested_by": request.requested_by,
            "approval_reason": request.approval_reason,
            "metadata": request.request_metadata,
            "created_at": request.created_at.isoformat(),
            "approve_url": f"/api/approvals/{approval_request_id}/approve",
            "reject_url": f"/api/approvals/{approval_request_id}/reject",
        }

        logger.info(
            f"Sending approval notification for request '{approval_request_id}' "
            f"to {len(approvers)} approvers: {approvers}"
        )

        # Send to each approver (via Control Protocol or webhook)
        for approver_id in approvers:
            # TODO: Implement webhook/email notification
            logger.debug(
                f"Would send notification to approver '{approver_id}': {notification}"
            )

    async def approve_request(self, approval_request_id: str, approver_id: str) -> None:
        """
        Approve an approval request.

        Updates approval status to APPROVED, records approver identity and timestamp.

        Args:
            approval_request_id: ID of the approval request
            approver_id: User ID of the approver

        Raises:
            ValueError: If approval request not found
            ValueError: If approver not authorized
            ValueError: If request already decided (approved/rejected/timeout)

        Examples:
            >>> await manager.approve_request("req_123", "approver_001")
        """
        request = self._requests.get(approval_request_id)
        if not request:
            raise ValueError(f"Approval request '{approval_request_id}' not found")

        # Check if approver is authorized
        if approver_id not in request.approvers:
            raise ValueError(
                f"User '{approver_id}' not authorized to approve request '{approval_request_id}'"
            )

        # Check if already decided
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Approval request '{approval_request_id}' already decided: {request.status.value}"
            )

        # Update approval status
        request.status = ApprovalStatus.APPROVED
        request.approved_by = approver_id
        request.approved_at = datetime.now(timezone.utc)

        logger.info(
            f"Approval request '{approval_request_id}' APPROVED by '{approver_id}'"
        )

        # Persist to storage if configured
        if self.storage:
            await self.storage.update(request)

    async def reject_request(
        self, approval_request_id: str, approver_id: str, reason: str
    ) -> None:
        """
        Reject an approval request.

        Updates approval status to REJECTED, records approver identity, timestamp,
        and rejection reason.

        Args:
            approval_request_id: ID of the approval request
            approver_id: User ID of the approver
            reason: Reason for rejection

        Raises:
            ValueError: If approval request not found
            ValueError: If approver not authorized
            ValueError: If request already decided

        Examples:
            >>> await manager.reject_request(
            ...     "req_123",
            ...     "approver_001",
            ...     "Cost exceeds budget"
            ... )
        """
        request = self._requests.get(approval_request_id)
        if not request:
            raise ValueError(f"Approval request '{approval_request_id}' not found")

        # Check if approver is authorized
        if approver_id not in request.approvers:
            raise ValueError(
                f"User '{approver_id}' not authorized to reject request '{approval_request_id}'"
            )

        # Check if already decided
        if request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Approval request '{approval_request_id}' already decided: {request.status.value}"
            )

        # Update approval status
        request.status = ApprovalStatus.REJECTED
        request.approved_by = approver_id
        request.approved_at = datetime.now(timezone.utc)
        request.rejection_reason = reason

        logger.info(
            f"Approval request '{approval_request_id}' REJECTED by '{approver_id}': {reason}"
        )

        # Persist to storage if configured
        if self.storage:
            await self.storage.update(request)

    async def timeout_pending_approvals(self) -> int:
        """
        Background task: Mark pending approvals as TIMEOUT if expired.

        Should be run periodically (e.g., every 60 seconds) to enforce timeout policy.

        Returns:
            Number of approvals timed out

        Examples:
            >>> # Run in background task
            >>> while True:
            ...     count = await manager.timeout_pending_approvals()
            ...     if count > 0:
            ...         logger.info(f"Timed out {count} pending approvals")
            ...     await asyncio.sleep(60)
        """
        now = datetime.now(timezone.utc)
        timed_out_count = 0

        for request_id, request in self._requests.items():
            if request.status != ApprovalStatus.PENDING:
                continue

            # Get timeout from requirement
            requirement = self._requirements.get(request.external_agent_id)
            if not requirement:
                continue

            timeout_seconds = requirement.approval_timeout_seconds
            # Handle both timezone-aware and timezone-naive created_at
            created_at = request.created_at
            if created_at.tzinfo is None:
                # Convert naive datetime to UTC
                created_at = created_at.replace(tzinfo=timezone.utc)
            timeout_at = created_at + timedelta(seconds=timeout_seconds)

            if now >= timeout_at:
                # Mark as TIMEOUT
                request.status = ApprovalStatus.TIMEOUT
                request.approved_at = now
                timed_out_count += 1

                logger.warning(
                    f"Approval request '{request_id}' timed out after {timeout_seconds}s"
                )

                # Persist to storage if configured
                if self.storage:
                    await self.storage.update(request)

        return timed_out_count

    async def wait_for_approval(
        self, approval_request_id: str, timeout: float = 3600.0
    ) -> bool:
        """
        Wait for approval decision with timeout.

        Polls approval status until APPROVED, REJECTED, or TIMEOUT.

        Args:
            approval_request_id: ID of the approval request
            timeout: Maximum seconds to wait (default: 1 hour)

        Returns:
            True if approved, False if rejected or timed out

        Examples:
            >>> request_id = await manager.request_approval(...)
            >>> approved = await manager.wait_for_approval(request_id, timeout=1800)
            >>> if approved:
            ...     # Execute external agent
            ...     pass
            >>> else:
            ...     # Deny execution
            ...     raise PermissionError("Approval required but not granted")
        """
        start_time = datetime.now(timezone.utc)
        poll_interval = 1.0  # Poll every 1 second

        while True:
            request = self._requests.get(approval_request_id)
            if not request:
                logger.error(f"Approval request '{approval_request_id}' not found")
                return False

            # Check status
            if request.status == ApprovalStatus.APPROVED:
                logger.info(f"Approval request '{approval_request_id}' approved")
                return True
            elif request.status in (ApprovalStatus.REJECTED, ApprovalStatus.TIMEOUT):
                logger.warning(
                    f"Approval request '{approval_request_id}' {request.status.value}"
                )
                return False

            # Check timeout
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            if elapsed >= timeout:
                logger.warning(
                    f"Wait for approval '{approval_request_id}' timed out after {timeout}s"
                )
                return False

            # Wait before next poll
            await asyncio.sleep(poll_interval)

    def get_request(
        self, approval_request_id: str
    ) -> Optional[ExternalAgentApprovalRequest]:
        """
        Get approval request by ID.

        Args:
            approval_request_id: ID of the approval request

        Returns:
            ExternalAgentApprovalRequest or None if not found

        Examples:
            >>> request = manager.get_request("req_123")
            >>> if request:
            ...     print(f"Status: {request.status.value}")
        """
        return self._requests.get(approval_request_id)

    def get_pending_approvals(
        self, approver_id: str
    ) -> list[ExternalAgentApprovalRequest]:
        """
        Get all pending approval requests for an approver.

        Args:
            approver_id: User ID of the approver

        Returns:
            List of pending approval requests

        Examples:
            >>> pending = manager.get_pending_approvals("approver_001")
            >>> print(f"Pending approvals: {len(pending)}")
        """
        return [
            request
            for request in self._requests.values()
            if request.status == ApprovalStatus.PENDING
            and approver_id in request.approvers
        ]


# Export all public types
__all__ = [
    "ApprovalLevel",
    "ApprovalRequirement",
    "ApprovalStatus",
    "ExternalAgentApprovalRequest",
    "ExternalAgentApprovalManager",
]
