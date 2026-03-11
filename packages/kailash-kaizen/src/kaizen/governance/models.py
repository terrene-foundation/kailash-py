"""
DataFlow Models for External Agent Approval Persistence.

Defines database schemas for approval request tracking using DataFlow.
Uses DataFlow @db.model decorator for automatic node generation.

Note: These are DataFlow model definitions, NOT traditional dataclasses.
DataFlow models:
- Use string IDs (not UUID types)
- Auto-generate 11 workflow nodes per model
- Use dict for complex types (JSON in database)
- Auto-manage created_at and updated_at fields

Example:
    from dataflow import DataFlow
    from kaizen.governance.models import register_approval_models

    db = DataFlow("postgresql://...")
    models = register_approval_models(db)

    # Now you can use:
    # - ExternalAgentApprovalRequestCreateNode
    # - ExternalAgentApprovalRequestReadNode
    # - ExternalAgentApprovalRequestUpdateNode
    # - ExternalAgentApprovalRequestDeleteNode
    # - ExternalAgentApprovalRequestListNode
    # - etc.
"""

from typing import Any, Dict, Optional, Type


def register_approval_models(db: "DataFlow") -> Dict[str, Type]:
    """
    Register approval-related DataFlow models with a DataFlow instance.

    This function registers the ExternalAgentApprovalRequest model
    with the provided DataFlow instance, which automatically generates
    11 workflow nodes for database operations.

    Args:
        db: DataFlow instance to register models with

    Returns:
        Dictionary mapping model names to model classes:
        - "ExternalAgentApprovalRequest": The approval request model

    Generated Nodes (11 per model):
        - ExternalAgentApprovalRequestCreateNode: Create single record
        - ExternalAgentApprovalRequestReadNode: Read by ID
        - ExternalAgentApprovalRequestUpdateNode: Update record
        - ExternalAgentApprovalRequestDeleteNode: Delete record
        - ExternalAgentApprovalRequestListNode: List with filters
        - ExternalAgentApprovalRequestUpsertNode: Insert or update
        - ExternalAgentApprovalRequestCountNode: Count records
        - ExternalAgentApprovalRequestBulkCreateNode: Bulk insert
        - ExternalAgentApprovalRequestBulkUpdateNode: Bulk update
        - ExternalAgentApprovalRequestBulkDeleteNode: Bulk delete
        - ExternalAgentApprovalRequestBulkUpsertNode: Bulk upsert

    Example:
        >>> from dataflow import DataFlow
        >>> db = DataFlow("sqlite:///approvals.db")
        >>> models = register_approval_models(db)
        >>> print(models.keys())
        dict_keys(['ExternalAgentApprovalRequest'])
    """
    from datetime import datetime

    @db.model
    class ExternalAgentApprovalRequest:
        """
        Persistent approval request for external agent invocations.

        Stores approval workflow state from request creation to decision.
        Uses JSONB for complex nested structures (approvers, metadata).

        Attributes:
            id: Unique approval request ID (UUID string, primary key)
            external_agent_id: ID of the external agent being invoked
            requested_by: User ID who requested the agent invocation
            approvers_json: JSON list of user IDs who can approve (stored as str)
            status: Current status (pending, approved, rejected, timeout)
            approval_reason: Human-readable reason for requiring approval
            request_metadata_json: JSON context about the request (stored as str)
            created_at: When request was created (auto-managed by DataFlow)
            approved_at: When request was approved/rejected (None if pending)
            approved_by: User ID who approved/rejected (None if pending)
            rejection_reason: Reason for rejection (None if not rejected)

        Database Schema (PostgreSQL):
            - id: TEXT PRIMARY KEY
            - external_agent_id: TEXT NOT NULL
            - requested_by: TEXT NOT NULL
            - approvers_json: TEXT (JSON array as string)
            - status: TEXT DEFAULT 'pending'
            - approval_reason: TEXT
            - request_metadata_json: TEXT (JSON object as string)
            - created_at: TIMESTAMP (auto-managed)
            - updated_at: TIMESTAMP (auto-managed)
            - approved_at: TIMESTAMP NULL
            - approved_by: TEXT NULL
            - rejection_reason: TEXT NULL

        Note on JSON Fields:
            DataFlow stores complex types (list, dict) as JSON strings.
            Use json.dumps() when saving and json.loads() when reading.
            The storage backend handles this conversion automatically.
        """

        # Primary key - must be named 'id' for DataFlow
        id: str

        # Core approval request fields
        external_agent_id: str
        requested_by: str

        # JSON fields stored as strings (DataFlow serialization)
        # Use json.dumps(list) to store, json.loads(str) to read
        approvers_json: str = "[]"  # JSON array: ["user1", "user2"]

        # Status: pending, approved, rejected, timeout
        status: str = "pending"

        # Approval context
        approval_reason: str = ""

        # JSON metadata stored as string
        # Use json.dumps(dict) to store, json.loads(str) to read
        request_metadata_json: str = "{}"  # JSON object

        # Timestamps - created_at and updated_at are auto-managed by DataFlow
        # We still define approved_at for tracking decision time
        approved_at: Optional[str] = None  # ISO format datetime string

        # Decision tracking
        approved_by: Optional[str] = None
        rejection_reason: Optional[str] = None

    return {
        "ExternalAgentApprovalRequest": ExternalAgentApprovalRequest,
    }


# Export model registration function
__all__ = [
    "register_approval_models",
]
