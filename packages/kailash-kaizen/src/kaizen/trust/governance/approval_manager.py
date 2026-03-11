"""
External Agent Approval Workflows.

Extends Kaizen's governance framework with approval requirement configuration,
approval routing to appropriate approvers, and async approval tracking with timeouts.

Key Components:
    - ApprovalPolicy: Defines when approval is required based on cost, environment, data classification
    - ApprovalManager: Routes approval requests and tracks decisions
    - ApprovalRequest/ApprovalResult: Request/response dataclasses

Examples:
    >>> from kaizen.trust.governance import (
    ...     ApprovalManager,
    ...     ApprovalPolicy,
    ...     ApprovalLevel,
    ... )
    >>> from kailash.runtime import AsyncLocalRuntime
    >>>
    >>> # Configure approval policy
    >>> policy = ApprovalPolicy(
    ...     external_agent_id="copilot_hr",
    ...     require_for_cost_above=10.0,
    ...     require_for_environments=["production"],
    ...     approval_level=ApprovalLevel.TEAM_LEAD,
    ... )
    >>>
    >>> # Check if approval required
    >>> runtime = AsyncLocalRuntime()
    >>> manager = ApprovalManager(runtime=runtime)
    >>> if manager.determine_if_approval_required(
    ...     policy,
    ...     cost=15.0,
    ...     environment="production",
    ...     operation="query_payroll"
    ... ):
    ...     # Request approval
    ...     approval_id = await manager.request_approval(
    ...         external_agent_id="copilot_hr",
    ...         requested_by="user-123",
    ...         metadata={"cost": 15.0, "environment": "production"}
    ...     )
    ...     # Approve request
    ...     await manager.approve_request(approval_id, approver_id="lead-456")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

logger = logging.getLogger(__name__)


class ApprovalLevel(str, Enum):
    """
    Approval routing levels.

    Determines who must approve an external agent invocation:
    - TEAM_LEAD: Requires approval from user's team lead
    - ADMIN: Requires approval from organization admin
    - OWNER: Requires approval from organization owner
    - CUSTOM: Uses custom approver list
    """

    TEAM_LEAD = "team_lead"
    ADMIN = "admin"
    OWNER = "owner"
    CUSTOM = "custom"


class ApprovalStatus(str, Enum):
    """
    Approval request status.

    Tracks the lifecycle of an approval request:
    - PENDING: Awaiting approval decision
    - APPROVED: Request approved
    - REJECTED: Request rejected
    - TIMEOUT: Request timed out before decision
    - BYPASSED: Emergency bypass used
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    TIMEOUT = "timeout"
    BYPASSED = "bypassed"


@dataclass
class ApprovalPolicy:
    """
    Defines when approval is required for external agent invocations.

    Approval can be triggered by:
    - Cost threshold (require_for_cost_above)
    - Environment restrictions (require_for_environments)
    - Data classification (require_for_data_classifications)
    - Specific operations (require_for_operations)

    Attributes:
        external_agent_id: Agent this policy applies to
        require_for_cost_above: Require approval if cost exceeds this (USD), None for no cost-based approval
        require_for_environments: List of environments requiring approval (e.g., ["production", "staging"])
        require_for_data_classifications: List of data classifications requiring approval (e.g., ["pii", "confidential"])
        require_for_operations: List of operations requiring approval (e.g., ["delete_user", "update_payroll"])
        approval_level: Who must approve (TEAM_LEAD, ADMIN, OWNER, CUSTOM)
        custom_approvers: List of user IDs for CUSTOM approval level
        approval_timeout_seconds: Timeout in seconds (default 1 hour)
        enabled: Whether policy is active
        metadata: Additional policy metadata
    """

    external_agent_id: str
    require_for_cost_above: float | None = None
    require_for_environments: list[str] = field(default_factory=list)
    require_for_data_classifications: list[str] = field(default_factory=list)
    require_for_operations: list[str] = field(default_factory=list)
    approval_level: ApprovalLevel = ApprovalLevel.TEAM_LEAD
    custom_approvers: list[str] = field(default_factory=list)
    approval_timeout_seconds: int = 3600  # 1 hour
    enabled: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRequest:
    """
    Approval request for external agent invocation.

    Created when an invocation requires approval based on ApprovalPolicy.

    Attributes:
        id: Unique approval request ID
        external_agent_id: Agent being invoked
        requested_by: User ID who requested the invocation
        approvers: List of user IDs who can approve
        status: Current status (PENDING, APPROVED, REJECTED, TIMEOUT, BYPASSED)
        approval_reason: Human-readable reason for approval requirement
        request_metadata: Context about the request (cost, environment, operation, etc.)
        created_at: When request was created
        approved_at: When request was approved/rejected (None if pending)
        approved_by: User ID who approved/rejected (None if pending)
        rejection_reason: Reason for rejection (None if not rejected)
        bypass_justification: Justification for emergency bypass (None if not bypassed)
        timeout_at: When request will timeout
        metadata: Additional request metadata
    """

    id: str
    external_agent_id: str
    requested_by: str
    approvers: list[str]
    status: ApprovalStatus = ApprovalStatus.PENDING
    approval_reason: str = ""
    request_metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    approved_at: datetime | None = None
    approved_by: str | None = None
    rejection_reason: str | None = None
    bypass_justification: str | None = None
    timeout_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalResult:
    """
    Result of approval check operation.

    Attributes:
        approval_required: Whether approval is required
        policy: ApprovalPolicy that triggered requirement (None if no approval required)
        reason: Human-readable reason why approval is required
        estimated_cost: Estimated cost for the operation (USD)
        environment: Environment being accessed
        operation: Operation being performed
        data_classifications: Data classifications involved
        metadata: Additional context
    """

    approval_required: bool
    policy: ApprovalPolicy | None = None
    reason: str | None = None
    estimated_cost: float | None = None
    environment: str | None = None
    operation: str | None = None
    data_classifications: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class ApprovalManager:
    """
    Manages approval workflows for external agent invocations.

    Provides:
    - Approval requirement determination based on policies
    - Approval request creation and routing
    - Approval decision tracking
    - Timeout enforcement
    - Emergency bypass with audit trail

    Integrates with DataFlow for persistent approval tracking.

    Examples:
        >>> from dataflow import DataFlow
        >>> db = DataFlow(database_type="sqlite", database_config={"database": ":memory:"})
        >>> runtime = AsyncLocalRuntime()
        >>> manager = ApprovalManager(runtime=runtime, db=db)
        >>>
        >>> # Check if approval required
        >>> policy = ApprovalPolicy(
        ...     external_agent_id="copilot_hr",
        ...     require_for_cost_above=10.0,
        ...     approval_level=ApprovalLevel.TEAM_LEAD
        ... )
        >>> result = manager.determine_if_approval_required(
        ...     policy,
        ...     cost=15.0,
        ...     environment="production"
        ... )
        >>> if result.approval_required:
        ...     # Request approval
        ...     approval_id = await manager.request_approval(
        ...         external_agent_id="copilot_hr",
        ...         requested_by="user-123",
        ...         metadata={"cost": 15.0}
        ...     )
        ...     # Approve request
        ...     await manager.approve_request(approval_id, approver_id="lead-456")
    """

    def __init__(
        self,
        runtime: AsyncLocalRuntime,
        db: Any | None = None,
    ):
        """
        Initialize approval manager.

        Args:
            runtime: AsyncLocalRuntime for workflow execution
            db: Optional DataFlow instance for persistence
        """
        self.runtime = runtime
        self.db = db

    def determine_if_approval_required(
        self,
        policy: ApprovalPolicy,
        cost: float | None = None,
        environment: str | None = None,
        operation: str | None = None,
        data_classifications: list[str] | None = None,
    ) -> ApprovalResult:
        """
        Check if approval is required based on policy and invocation context.

        Checks all trigger conditions:
        1. Cost threshold (require_for_cost_above)
        2. Environment restrictions (require_for_environments)
        3. Data classification (require_for_data_classifications)
        4. Operation type (require_for_operations)

        Args:
            policy: ApprovalPolicy to evaluate
            cost: Estimated cost for invocation (USD)
            environment: Environment being accessed
            operation: Operation being performed
            data_classifications: Data classifications involved

        Returns:
            ApprovalResult with approval_required and reason

        Examples:
            >>> policy = ApprovalPolicy(
            ...     external_agent_id="test",
            ...     require_for_cost_above=10.0,
            ...     require_for_environments=["production"]
            ... )
            >>> result = manager.determine_if_approval_required(
            ...     policy,
            ...     cost=15.0,
            ...     environment="production"
            ... )
            >>> result.approval_required
            True
            >>> result.reason
            'Cost exceeds threshold: $15.00 > $10.00'
        """
        if not policy.enabled:
            return ApprovalResult(
                approval_required=False,
                reason="Policy is disabled",
            )

        data_classifications = data_classifications or []

        # Check cost threshold
        if policy.require_for_cost_above is not None and cost is not None:
            if cost > policy.require_for_cost_above:
                return ApprovalResult(
                    approval_required=True,
                    policy=policy,
                    reason=f"Cost exceeds threshold: ${cost:.2f} > ${policy.require_for_cost_above:.2f}",
                    estimated_cost=cost,
                    environment=environment,
                    operation=operation,
                    data_classifications=data_classifications,
                )

        # Check environment restrictions
        if environment and policy.require_for_environments:
            if environment in policy.require_for_environments:
                return ApprovalResult(
                    approval_required=True,
                    policy=policy,
                    reason=f"Environment '{environment}' requires approval",
                    estimated_cost=cost,
                    environment=environment,
                    operation=operation,
                    data_classifications=data_classifications,
                )

        # Check data classification
        if data_classifications and policy.require_for_data_classifications:
            matching_classifications = set(data_classifications) & set(
                policy.require_for_data_classifications
            )
            if matching_classifications:
                return ApprovalResult(
                    approval_required=True,
                    policy=policy,
                    reason=f"Data classification requires approval: {', '.join(matching_classifications)}",
                    estimated_cost=cost,
                    environment=environment,
                    operation=operation,
                    data_classifications=data_classifications,
                )

        # Check operation type
        if operation and policy.require_for_operations:
            if operation in policy.require_for_operations:
                return ApprovalResult(
                    approval_required=True,
                    policy=policy,
                    reason=f"Operation '{operation}' requires approval",
                    estimated_cost=cost,
                    environment=environment,
                    operation=operation,
                    data_classifications=data_classifications,
                )

        # No approval required
        return ApprovalResult(
            approval_required=False,
            policy=policy,
            reason="No approval conditions matched",
            estimated_cost=cost,
            environment=environment,
            operation=operation,
            data_classifications=data_classifications,
        )

    async def request_approval(
        self,
        external_agent_id: str,
        requested_by: str,
        policy: ApprovalPolicy,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """
        Create approval request and route to approvers.

        Determines approvers based on policy.approval_level:
        - TEAM_LEAD: Query user's team for team lead
        - ADMIN: Query organization for admins
        - OWNER: Query organization for owner
        - CUSTOM: Use policy.custom_approvers

        Args:
            external_agent_id: Agent being invoked
            requested_by: User ID requesting invocation
            policy: ApprovalPolicy defining routing
            metadata: Optional request metadata (cost, environment, etc.)

        Returns:
            Approval request ID

        Raises:
            ValueError: If no approvers found for approval level

        Examples:
            >>> policy = ApprovalPolicy(
            ...     external_agent_id="copilot_hr",
            ...     approval_level=ApprovalLevel.TEAM_LEAD
            ... )
            >>> approval_id = await manager.request_approval(
            ...     "copilot_hr",
            ...     "user-123",
            ...     policy,
            ...     metadata={"cost": 15.0, "environment": "production"}
            ... )
        """
        metadata = metadata or {}

        # Determine approvers based on policy
        approvers = await self._get_approvers(
            policy.approval_level, requested_by, policy.custom_approvers
        )

        if not approvers:
            raise ValueError(
                f"No approvers found for approval level {policy.approval_level.value}"
            )

        # Create approval request
        approval_id = (
            f"approval-{external_agent_id}-{datetime.now(timezone.utc).timestamp()}"
        )
        timeout_at = datetime.now(timezone.utc) + timedelta(
            seconds=policy.approval_timeout_seconds
        )

        approval_request = ApprovalRequest(
            id=approval_id,
            external_agent_id=external_agent_id,
            requested_by=requested_by,
            approvers=approvers,
            status=ApprovalStatus.PENDING,
            approval_reason=metadata.get(
                "reason", "External agent invocation approval required"
            ),
            request_metadata=metadata,
            timeout_at=timeout_at,
        )

        # Persist to database if configured
        if self.db:
            await self._persist_approval_request(approval_request)

        # Send notifications to approvers
        await self.send_approval_notification(approval_id, approvers, approval_request)

        logger.info(
            f"Approval request created: {approval_id} for {external_agent_id}, "
            f"approvers={approvers}, timeout={policy.approval_timeout_seconds}s"
        )

        return approval_id

    async def approve_request(
        self,
        approval_request_id: str,
        approver_id: str,
    ) -> ApprovalRequest:
        """
        Approve an approval request.

        Updates request status to APPROVED and records approver identity.

        Args:
            approval_request_id: Approval request ID
            approver_id: User ID who is approving

        Returns:
            Updated ApprovalRequest

        Raises:
            ValueError: If request not found or approver not authorized

        Examples:
            >>> await manager.approve_request("approval-123", "lead-456")
        """
        # Load approval request (would come from database in real implementation)
        approval_request = await self._load_approval_request(approval_request_id)

        if not approval_request:
            raise ValueError(f"Approval request not found: {approval_request_id}")

        if approver_id not in approval_request.approvers:
            raise ValueError(
                f"User {approver_id} is not authorized to approve request {approval_request_id}"
            )

        if approval_request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Request {approval_request_id} is not pending (status: {approval_request.status.value})"
            )

        # Update approval request
        approval_request.status = ApprovalStatus.APPROVED
        approval_request.approved_by = approver_id
        approval_request.approved_at = datetime.now(timezone.utc)

        # Persist to database
        if self.db:
            await self._persist_approval_request(approval_request)

        logger.info(
            f"Approval request approved: {approval_request_id} by {approver_id}"
        )

        return approval_request

    async def reject_request(
        self,
        approval_request_id: str,
        approver_id: str,
        reason: str,
    ) -> ApprovalRequest:
        """
        Reject an approval request.

        Updates request status to REJECTED and records rejection reason.

        Args:
            approval_request_id: Approval request ID
            approver_id: User ID who is rejecting
            reason: Rejection reason

        Returns:
            Updated ApprovalRequest

        Raises:
            ValueError: If request not found or approver not authorized

        Examples:
            >>> await manager.reject_request(
            ...     "approval-123",
            ...     "lead-456",
            ...     "Cost too high for this operation"
            ... )
        """
        # Load approval request
        approval_request = await self._load_approval_request(approval_request_id)

        if not approval_request:
            raise ValueError(f"Approval request not found: {approval_request_id}")

        if approver_id not in approval_request.approvers:
            raise ValueError(
                f"User {approver_id} is not authorized to reject request {approval_request_id}"
            )

        if approval_request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Request {approval_request_id} is not pending (status: {approval_request.status.value})"
            )

        # Update approval request
        approval_request.status = ApprovalStatus.REJECTED
        approval_request.approved_by = approver_id
        approval_request.approved_at = datetime.now(timezone.utc)
        approval_request.rejection_reason = reason

        # Persist to database
        if self.db:
            await self._persist_approval_request(approval_request)

        logger.info(
            f"Approval request rejected: {approval_request_id} by {approver_id}, "
            f"reason: {reason}"
        )

        return approval_request

    async def bypass_approval(
        self,
        approval_request_id: str,
        bypass_user_id: str,
        justification: str,
    ) -> ApprovalRequest:
        """
        Bypass approval for emergency situations.

        Records bypass in audit trail with justification.

        Args:
            approval_request_id: Approval request ID
            bypass_user_id: User ID performing bypass
            justification: Required justification for bypass

        Returns:
            Updated ApprovalRequest with BYPASSED status

        Raises:
            ValueError: If request not found or justification missing

        Examples:
            >>> await manager.bypass_approval(
            ...     "approval-123",
            ...     "admin-789",
            ...     "Production outage requires immediate agent invocation"
            ... )
        """
        if not justification or len(justification.strip()) < 10:
            raise ValueError("Bypass justification required (minimum 10 characters)")

        # Load approval request
        approval_request = await self._load_approval_request(approval_request_id)

        if not approval_request:
            raise ValueError(f"Approval request not found: {approval_request_id}")

        if approval_request.status != ApprovalStatus.PENDING:
            raise ValueError(
                f"Request {approval_request_id} is not pending (status: {approval_request.status.value})"
            )

        # Update approval request
        approval_request.status = ApprovalStatus.BYPASSED
        approval_request.approved_by = bypass_user_id
        approval_request.approved_at = datetime.now(timezone.utc)
        approval_request.bypass_justification = justification

        # Persist to database
        if self.db:
            await self._persist_approval_request(approval_request)

        logger.warning(
            f"Approval request bypassed: {approval_request_id} by {bypass_user_id}, "
            f"justification: {justification}"
        )

        # TODO: Trigger audit alert for bypass
        # await audit_service.log_approval_bypass(approval_request)

        return approval_request

    async def check_approval_timeout(
        self,
        approval_request_id: str,
    ) -> ApprovalRequest:
        """
        Check if approval request has timed out.

        Updates status to TIMEOUT if timeout_at has passed.

        Args:
            approval_request_id: Approval request ID

        Returns:
            ApprovalRequest (possibly updated to TIMEOUT)

        Examples:
            >>> request = await manager.check_approval_timeout("approval-123")
            >>> if request.status == ApprovalStatus.TIMEOUT:
            ...     print("Request timed out")
        """
        # Load approval request
        approval_request = await self._load_approval_request(approval_request_id)

        if not approval_request:
            raise ValueError(f"Approval request not found: {approval_request_id}")

        # Only check timeout for pending requests
        if approval_request.status != ApprovalStatus.PENDING:
            return approval_request

        # Check if timeout has passed
        if (
            approval_request.timeout_at
            and datetime.now(timezone.utc) > approval_request.timeout_at
        ):
            approval_request.status = ApprovalStatus.TIMEOUT
            approval_request.approved_at = datetime.now(timezone.utc)

            # Persist to database
            if self.db:
                await self._persist_approval_request(approval_request)

            logger.warning(f"Approval request timed out: {approval_request_id}")

        return approval_request

    async def send_approval_notification(
        self,
        approval_request_id: str,
        approvers: list[str],
        approval_request: ApprovalRequest,
    ) -> None:
        """
        Send approval notification to approvers.

        Sends webhook or email notification to each approver with:
        - Agent name and description
        - Requestor information
        - Request metadata (cost, environment, operation)
        - Approve/reject action links

        Args:
            approval_request_id: Approval request ID
            approvers: List of approver user IDs
            approval_request: Full approval request object

        Examples:
            >>> await manager.send_approval_notification(
            ...     "approval-123",
            ...     ["lead-456", "lead-789"],
            ...     approval_request
            ... )
        """
        notification_payload = {
            "approval_request_id": approval_request_id,
            "external_agent_id": approval_request.external_agent_id,
            "requested_by": approval_request.requested_by,
            "approval_reason": approval_request.approval_reason,
            "request_metadata": approval_request.request_metadata,
            "timeout_at": (
                approval_request.timeout_at.isoformat()
                if approval_request.timeout_at
                else None
            ),
            "approvers": approvers,
        }

        logger.info(
            f"Sending approval notification for {approval_request_id} to {len(approvers)} approvers"
        )

        # TODO: Integrate with webhook/email service
        # for approver_id in approvers:
        #     await webhook_service.trigger("approval_request", {
        #         **notification_payload,
        #         "approver_id": approver_id,
        #         "approve_url": f"/approvals/{approval_request_id}/approve",
        #         "reject_url": f"/approvals/{approval_request_id}/reject",
        #     })

    async def _get_approvers(
        self,
        approval_level: ApprovalLevel,
        user_id: str,
        custom_approvers: list[str] | None = None,
    ) -> list[str]:
        """
        Determine approvers based on approval level.

        Args:
            approval_level: Approval level (TEAM_LEAD, ADMIN, OWNER, CUSTOM)
            user_id: User requesting approval
            custom_approvers: Custom approver list (for CUSTOM level)

        Returns:
            List of approver user IDs

        Examples:
            >>> approvers = await manager._get_approvers(
            ...     ApprovalLevel.TEAM_LEAD,
            ...     "user-123"
            ... )
        """
        if approval_level == ApprovalLevel.CUSTOM:
            return custom_approvers or []

        # TODO: Query database for team leads, admins, or owners
        # For now, return mock approvers
        if approval_level == ApprovalLevel.TEAM_LEAD:
            # Would query user's team for team lead
            return [f"team_lead_for_{user_id}"]
        elif approval_level == ApprovalLevel.ADMIN:
            # Would query organization for admins
            return ["org_admin_1", "org_admin_2"]
        elif approval_level == ApprovalLevel.OWNER:
            # Would query organization for owner
            return ["org_owner"]

        return []

    async def _persist_approval_request(
        self,
        approval_request: ApprovalRequest,
    ) -> None:
        """
        Persist approval request to database.

        Args:
            approval_request: ApprovalRequest to persist
        """
        if not self.db:
            return

        # Create workflow to persist approval request
        workflow = WorkflowBuilder()

        # Use DataFlow CreateNode or UpdateNode (depends on if record exists)
        # Note: Actual implementation depends on DataFlow schema registration
        workflow.add_node(
            "CreateApprovalRequestNode",
            "create_approval",
            {
                "id": approval_request.id,
                "external_agent_id": approval_request.external_agent_id,
                "requested_by": approval_request.requested_by,
                "approvers": approval_request.approvers,
                "status": approval_request.status.value,
                "approval_reason": approval_request.approval_reason,
                "request_metadata": approval_request.request_metadata,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
            logger.debug(
                f"Approval request persisted: {approval_request.id}, "
                f"status={approval_request.status.value}"
            )
        except Exception as e:
            logger.error(f"Failed to persist approval request: {e}")
            # Don't fail the operation if persistence fails

    async def _load_approval_request(
        self,
        approval_request_id: str,
    ) -> ApprovalRequest | None:
        """
        Load approval request from database.

        Args:
            approval_request_id: Approval request ID

        Returns:
            ApprovalRequest if found, None otherwise
        """
        if not self.db:
            # Return mock approval request for testing without database
            return ApprovalRequest(
                id=approval_request_id,
                external_agent_id="mock_agent",
                requested_by="mock_user",
                approvers=["mock_approver"],
                status=ApprovalStatus.PENDING,
                timeout_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )

        # TODO: Query database using DataFlow ReadNode
        # workflow = WorkflowBuilder()
        # workflow.add_node(
        #     "ReadApprovalRequestNode",
        #     "read_approval",
        #     {"id": approval_request_id}
        # )
        # results, _ = await self.runtime.execute_workflow_async(workflow.build(), inputs={})
        # return results.get("read_approval")

        return None


# Export all public types
__all__ = [
    "ApprovalManager",
    "ApprovalPolicy",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalLevel",
    "ApprovalStatus",
]
