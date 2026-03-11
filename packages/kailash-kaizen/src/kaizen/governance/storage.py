"""
DataFlow Storage Backend for External Agent Approval Persistence.

Provides persistent storage for ExternalAgentApprovalRequest using DataFlow.
Implements save, update, load, and query operations with automatic
node generation from the registered model.

Architecture:
- Uses DataFlow for zero-config database operations
- Automatically generates 11 workflow nodes per model
- Built-in support for PostgreSQL, MySQL, and SQLite
- String IDs preserved (no UUID conversion)
- JSON serialization for complex types (list, dict)

Example:
    from dataflow import DataFlow
    from kaizen.governance.storage import ExternalAgentApprovalStorage
    from kaizen.governance.approval_manager import (
        ExternalAgentApprovalRequest,
        ApprovalStatus,
    )

    # Initialize storage
    db = DataFlow("postgresql://user:pass@localhost/mydb")
    storage = ExternalAgentApprovalStorage(db)

    # Save approval request
    request = ExternalAgentApprovalRequest(
        id="req-123",
        external_agent_id="agent-456",
        requested_by="user-789",
        approvers=["approver-1", "approver-2"],
        status=ApprovalStatus.PENDING,
        approval_reason="Production deployment requires approval",
        request_metadata={"cost": 15.0, "environment": "production"},
        created_at=datetime.now(timezone.utc),
    )
    await storage.save(request)

    # Load approval request
    loaded = await storage.load("req-123")

    # Update approval request
    loaded.status = ApprovalStatus.APPROVED
    loaded.approved_by = "approver-1"
    loaded.approved_at = datetime.now(timezone.utc)
    await storage.update(loaded)

    # Query pending requests
    pending = await storage.list_by_status(ApprovalStatus.PENDING)
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

from kaizen.governance.approval_manager import (
    ApprovalStatus,
    ExternalAgentApprovalRequest,
)
from kaizen.governance.models import register_approval_models

logger = logging.getLogger(__name__)


class ExternalAgentApprovalStorage:
    """
    DataFlow storage backend for ExternalAgentApprovalRequest persistence.

    Provides CRUD operations for approval requests using DataFlow-generated
    workflow nodes. Handles JSON serialization for complex fields (approvers,
    request_metadata).

    Performance Characteristics:
    - save(): ~5-10ms (single record insert)
    - load(): ~2-5ms (primary key lookup)
    - update(): ~5-10ms (single record update)
    - list_by_status(): ~10-20ms (filtered query)
    - list_by_approver(): ~10-20ms (filtered query)
    - list_pending_for_agent(): ~10-20ms (filtered query)

    Thread Safety:
    - Uses AsyncLocalRuntime for async-safe execution
    - Each method creates fresh WorkflowBuilder (no shared state)
    - Safe for concurrent use from multiple async tasks

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("sqlite:///approvals.db")
        >>> storage = ExternalAgentApprovalStorage(db)
        >>>
        >>> # Save a new request
        >>> request = ExternalAgentApprovalRequest(
        ...     id="req-001",
        ...     external_agent_id="agent-123",
        ...     requested_by="user-456",
        ...     approvers=["lead-789"],
        ...     status=ApprovalStatus.PENDING,
        ...     approval_reason="Cost exceeds threshold",
        ...     request_metadata={"cost": 25.0},
        ...     created_at=datetime.now(timezone.utc),
        ... )
        >>> await storage.save(request)
        >>>
        >>> # Load by ID
        >>> loaded = await storage.load("req-001")
        >>> print(loaded.status)  # ApprovalStatus.PENDING
    """

    # Model name used for node naming convention
    MODEL_NAME = "ExternalAgentApprovalRequest"

    def __init__(self, db: "DataFlow"):
        """
        Initialize the storage backend with a DataFlow instance.

        Registers the ExternalAgentApprovalRequest model with DataFlow,
        which automatically generates 11 workflow nodes for database
        operations.

        Args:
            db: DataFlow instance (connected to database)

        Raises:
            ValueError: If db is not a DataFlow instance

        Example:
            >>> from dataflow import DataFlow
            >>> db = DataFlow("postgresql://localhost/mydb")
            >>> storage = ExternalAgentApprovalStorage(db)
        """
        try:
            from dataflow import DataFlow as DataFlowClass

            if not isinstance(db, DataFlowClass):
                raise ValueError(f"Expected DataFlow instance, got {type(db)}")
        except ImportError:
            raise ValueError(
                "DataFlow not installed. Install with: pip install kailash-dataflow"
            )

        self.db = db

        # Register models with DataFlow (generates 11 nodes)
        self._models = register_approval_models(db)

        # Runtime for executing workflows
        self.runtime = AsyncLocalRuntime()

        logger.debug(
            f"ExternalAgentApprovalStorage initialized with model: {self.MODEL_NAME}"
        )

    def _to_db_record(self, request: ExternalAgentApprovalRequest) -> Dict[str, Any]:
        """
        Convert ExternalAgentApprovalRequest to database record format.

        Serializes complex fields (approvers, request_metadata) to JSON strings
        for storage in DataFlow model.

        Args:
            request: ExternalAgentApprovalRequest to convert

        Returns:
            Dictionary suitable for DataFlow CreateNode/UpdateNode

        Note:
            - approvers list -> approvers_json string
            - request_metadata dict -> request_metadata_json string
            - datetime -> ISO format string
        """
        return {
            "id": request.id,
            "external_agent_id": request.external_agent_id,
            "requested_by": request.requested_by,
            "approvers_json": json.dumps(request.approvers),
            "status": request.status.value,
            "approval_reason": request.approval_reason,
            "request_metadata_json": json.dumps(request.request_metadata),
            "approved_at": (
                request.approved_at.isoformat() if request.approved_at else None
            ),
            "approved_by": request.approved_by,
            "rejection_reason": request.rejection_reason,
        }

    def _from_db_record(self, record: Dict[str, Any]) -> ExternalAgentApprovalRequest:
        """
        Convert database record to ExternalAgentApprovalRequest.

        Deserializes JSON strings back to Python types (list, dict).

        Args:
            record: Database record from DataFlow ReadNode/ListNode

        Returns:
            ExternalAgentApprovalRequest instance

        Note:
            - approvers_json string -> approvers list
            - request_metadata_json string -> request_metadata dict
            - ISO format string -> datetime
        """
        # Parse JSON fields
        approvers_json = record.get("approvers_json", "[]")
        if isinstance(approvers_json, str):
            approvers = json.loads(approvers_json)
        else:
            approvers = approvers_json or []

        metadata_json = record.get("request_metadata_json", "{}")
        if isinstance(metadata_json, str):
            request_metadata = json.loads(metadata_json)
        else:
            request_metadata = metadata_json or {}

        # Parse status enum
        status_str = record.get("status", "pending")
        status = ApprovalStatus(status_str)

        # Parse datetime fields
        created_at_str = record.get("created_at")
        if isinstance(created_at_str, str):
            created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        elif isinstance(created_at_str, datetime):
            created_at = created_at_str
        else:
            created_at = datetime.now(timezone.utc)

        approved_at_str = record.get("approved_at")
        approved_at = None
        if approved_at_str:
            if isinstance(approved_at_str, str):
                approved_at = datetime.fromisoformat(
                    approved_at_str.replace("Z", "+00:00")
                )
            elif isinstance(approved_at_str, datetime):
                approved_at = approved_at_str

        return ExternalAgentApprovalRequest(
            id=record["id"],
            external_agent_id=record.get("external_agent_id", ""),
            requested_by=record.get("requested_by", ""),
            approvers=approvers,
            status=status,
            approval_reason=record.get("approval_reason", ""),
            request_metadata=request_metadata,
            created_at=created_at,
            approved_at=approved_at,
            approved_by=record.get("approved_by"),
            rejection_reason=record.get("rejection_reason"),
        )

    async def save(self, request: ExternalAgentApprovalRequest) -> str:
        """
        Save a new approval request to the database.

        Uses DataFlow CreateNode for atomic insert operation.

        Args:
            request: ExternalAgentApprovalRequest to save

        Returns:
            The request ID (for confirmation)

        Raises:
            Exception: If database operation fails

        Example:
            >>> request = ExternalAgentApprovalRequest(
            ...     id="req-001",
            ...     external_agent_id="agent-123",
            ...     requested_by="user-456",
            ...     approvers=["lead-789"],
            ...     status=ApprovalStatus.PENDING,
            ...     approval_reason="Cost threshold exceeded",
            ...     request_metadata={"cost": 25.0},
            ...     created_at=datetime.now(timezone.utc),
            ... )
            >>> request_id = await storage.save(request)
            >>> print(request_id)  # "req-001"
        """
        record = self._to_db_record(request)

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}CreateNode",
            "create_request",
            record,
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
            logger.debug(f"Saved approval request: {request.id}")
            return request.id
        except Exception as e:
            logger.error(f"Failed to save approval request {request.id}: {e}")
            raise

    async def update(self, request: ExternalAgentApprovalRequest) -> None:
        """
        Update an existing approval request in the database.

        Uses DataFlow UpdateNode with filter on ID for atomic update.

        Args:
            request: ExternalAgentApprovalRequest with updated fields

        Raises:
            Exception: If database operation fails

        Example:
            >>> request = await storage.load("req-001")
            >>> request.status = ApprovalStatus.APPROVED
            >>> request.approved_by = "lead-789"
            >>> request.approved_at = datetime.now(timezone.utc)
            >>> await storage.update(request)
        """
        record = self._to_db_record(request)

        # Remove 'id' from fields (it's the filter, not an update field)
        update_fields = {k: v for k, v in record.items() if k != "id"}

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}UpdateNode",
            "update_request",
            {
                "filter": {"id": request.id},
                "fields": update_fields,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )
            logger.debug(f"Updated approval request: {request.id}")
        except Exception as e:
            logger.error(f"Failed to update approval request {request.id}: {e}")
            raise

    async def load(self, request_id: str) -> Optional[ExternalAgentApprovalRequest]:
        """
        Load an approval request by ID.

        Uses DataFlow ReadNode for primary key lookup.

        Args:
            request_id: Unique approval request ID

        Returns:
            ExternalAgentApprovalRequest if found, None otherwise

        Example:
            >>> request = await storage.load("req-001")
            >>> if request:
            ...     print(f"Status: {request.status.value}")
            ... else:
            ...     print("Request not found")
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ReadNode",
            "read_request",
            {"id": request_id},
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            # Access result using string-based pattern
            result = results.get("read_request", {})

            # Handle different result formats from DataFlow
            if "result" in result:
                record = result["result"]
            elif "data" in result:
                record = result["data"]
            else:
                record = result

            if not record or not record.get("id"):
                logger.debug(f"Approval request not found: {request_id}")
                return None

            return self._from_db_record(record)
        except Exception as e:
            logger.error(f"Failed to load approval request {request_id}: {e}")
            raise

    async def delete(self, request_id: str) -> bool:
        """
        Delete an approval request by ID.

        Uses DataFlow DeleteNode for atomic delete operation.

        Args:
            request_id: Unique approval request ID

        Returns:
            True if deleted, False if not found

        Example:
            >>> deleted = await storage.delete("req-001")
            >>> print(f"Deleted: {deleted}")
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}DeleteNode",
            "delete_request",
            {"id": request_id},
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("delete_request", {})
            deleted = result.get("deleted", False) or result.get("success", False)

            if deleted:
                logger.debug(f"Deleted approval request: {request_id}")
            else:
                logger.debug(f"Approval request not found for deletion: {request_id}")

            return deleted
        except Exception as e:
            logger.error(f"Failed to delete approval request {request_id}: {e}")
            raise

    async def list_by_status(
        self,
        status: ApprovalStatus,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ExternalAgentApprovalRequest]:
        """
        List approval requests by status.

        Uses DataFlow ListNode with status filter.

        Args:
            status: ApprovalStatus to filter by
            limit: Maximum number of results (default: 100)
            offset: Offset for pagination (default: 0)

        Returns:
            List of ExternalAgentApprovalRequest matching the status

        Example:
            >>> pending = await storage.list_by_status(ApprovalStatus.PENDING)
            >>> print(f"Pending requests: {len(pending)}")
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ListNode",
            "list_requests",
            {
                "filter": {"status": status.value},
                "limit": limit,
                "offset": offset,
                "order_by": "created_at",
                "ascending": False,  # Most recent first
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("list_requests", {})
            records = result.get("records", [])

            return [self._from_db_record(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to list approval requests by status {status}: {e}")
            raise

    async def list_by_approver(
        self,
        approver_id: str,
        status: Optional[ApprovalStatus] = None,
        limit: int = 100,
    ) -> List[ExternalAgentApprovalRequest]:
        """
        List approval requests where user is an approver.

        Note: This performs a LIKE query on approvers_json to find
        requests containing the approver ID. For production use with
        high volumes, consider a separate approver-request junction table.

        Args:
            approver_id: User ID to search for in approvers list
            status: Optional status filter (default: all statuses)
            limit: Maximum number of results (default: 100)

        Returns:
            List of ExternalAgentApprovalRequest where user is an approver

        Example:
            >>> # Get all pending requests for an approver
            >>> requests = await storage.list_by_approver(
            ...     "lead-789",
            ...     status=ApprovalStatus.PENDING
            ... )
        """
        # Build filter - DataFlow supports $like operator for string matching
        filters: Dict[str, Any] = {"approvers_json": {"$like": f"%{approver_id}%"}}
        if status:
            filters["status"] = status.value

        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ListNode",
            "list_requests",
            {
                "filter": filters,
                "limit": limit,
                "order_by": "created_at",
                "ascending": False,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("list_requests", {})
            records = result.get("records", [])

            # Filter in Python to ensure exact match (LIKE may match substrings)
            matching_requests = []
            for record in records:
                request = self._from_db_record(record)
                if approver_id in request.approvers:
                    matching_requests.append(request)

            return matching_requests
        except Exception as e:
            logger.error(
                f"Failed to list approval requests for approver {approver_id}: {e}"
            )
            raise

    async def list_pending_for_agent(
        self,
        external_agent_id: str,
        limit: int = 100,
    ) -> List[ExternalAgentApprovalRequest]:
        """
        List pending approval requests for a specific external agent.

        Args:
            external_agent_id: External agent ID to filter by
            limit: Maximum number of results (default: 100)

        Returns:
            List of pending ExternalAgentApprovalRequest for the agent

        Example:
            >>> pending = await storage.list_pending_for_agent("agent-123")
            >>> print(f"Pending for agent: {len(pending)}")
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ListNode",
            "list_requests",
            {
                "filter": {
                    "external_agent_id": external_agent_id,
                    "status": ApprovalStatus.PENDING.value,
                },
                "limit": limit,
                "order_by": "created_at",
                "ascending": False,
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("list_requests", {})
            records = result.get("records", [])

            return [self._from_db_record(r) for r in records]
        except Exception as e:
            logger.error(
                f"Failed to list pending requests for agent {external_agent_id}: {e}"
            )
            raise

    async def count_by_status(self, status: ApprovalStatus) -> int:
        """
        Count approval requests by status.

        Uses DataFlow CountNode for efficient counting.

        Args:
            status: ApprovalStatus to count

        Returns:
            Number of requests with the given status

        Example:
            >>> pending_count = await storage.count_by_status(ApprovalStatus.PENDING)
            >>> print(f"Pending requests: {pending_count}")
        """
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}CountNode",
            "count_requests",
            {"filter": {"status": status.value}},
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("count_requests", {})
            return result.get("count", 0)
        except Exception as e:
            logger.error(f"Failed to count requests by status {status}: {e}")
            raise

    async def get_expired_pending_requests(
        self,
        timeout_seconds: int = 3600,
        limit: int = 100,
    ) -> List[ExternalAgentApprovalRequest]:
        """
        Get pending requests that have exceeded their timeout.

        Useful for the timeout enforcement background task.

        Args:
            timeout_seconds: Timeout threshold in seconds (default: 3600)
            limit: Maximum number of results (default: 100)

        Returns:
            List of pending requests older than timeout_seconds

        Example:
            >>> # Get requests pending for more than 1 hour
            >>> expired = await storage.get_expired_pending_requests(3600)
            >>> for req in expired:
            ...     await manager.timeout_request(req.id)
        """
        from datetime import timedelta

        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds)
        cutoff_iso = cutoff_time.isoformat()

        # DataFlow supports $lt operator for comparison
        workflow = WorkflowBuilder()
        workflow.add_node(
            f"{self.MODEL_NAME}ListNode",
            "list_requests",
            {
                "filter": {
                    "status": ApprovalStatus.PENDING.value,
                    "created_at": {"$lt": cutoff_iso},
                },
                "limit": limit,
                "order_by": "created_at",
                "ascending": True,  # Oldest first
            },
        )

        try:
            results, _ = await self.runtime.execute_workflow_async(
                workflow.build(), inputs={}
            )

            result = results.get("list_requests", {})
            records = result.get("records", [])

            return [self._from_db_record(r) for r in records]
        except Exception as e:
            logger.error(f"Failed to get expired pending requests: {e}")
            raise


# Export storage class
__all__ = [
    "ExternalAgentApprovalStorage",
]
