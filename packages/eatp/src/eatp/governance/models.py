# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
DataFlow models for External Agent Budget persistence.

Defines database schemas for budget tracking, usage history, and alerts.
Uses DataFlow @db.model decorator for automatic node generation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ExternalAgentBudgetModel:
    """
    Persistent budget configuration for external agents.

    Generated nodes (via DataFlow):
    - CreateExternalAgentBudgetNode
    - ReadExternalAgentBudgetNode
    - UpdateExternalAgentBudgetNode
    - DeleteExternalAgentBudgetNode
    - ListExternalAgentBudgetNode
    - CountExternalAgentBudgetNode
    - BulkCreateExternalAgentBudgetNode
    - BulkUpdateExternalAgentBudgetNode
    - BulkDeleteExternalAgentBudgetNode

    Attributes:
        external_agent_id: Unique identifier (primary key)
        monthly_budget_usd: Monthly spending limit
        monthly_spent_usd: Current month spending
        monthly_execution_limit: Max executions per month
        monthly_execution_count: Current month executions
        daily_budget_usd: Daily spending limit (optional)
        daily_spent_usd: Today's spending
        daily_execution_limit: Max executions per day (optional)
        daily_execution_count: Today's executions
        cost_per_execution: Estimated cost per invocation
        warning_threshold: Warn at this percentage (0.0-1.0)
        degradation_threshold: Degrade at this percentage (0.0-1.0)
        enforcement_mode: "hard" (block) or "soft" (warn)
        last_reset_monthly: Timestamp of last monthly reset
        last_reset_daily: Timestamp of last daily reset
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metadata: JSON metadata field
    """

    external_agent_id: str  # Primary key
    monthly_budget_usd: float
    monthly_spent_usd: float = 0.0
    monthly_execution_limit: int = 10000
    monthly_execution_count: int = 0
    daily_budget_usd: float | None = None
    daily_spent_usd: float = 0.0
    daily_execution_limit: int | None = None
    daily_execution_count: int = 0
    cost_per_execution: float = 0.05
    warning_threshold: float = 0.80
    degradation_threshold: float = 0.90
    enforcement_mode: str = "hard"
    last_reset_monthly: datetime | None = None
    last_reset_daily: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetHistoryModel:
    """
    Archived monthly budget data for reporting.

    Preserves historical budget usage for analysis and compliance.

    Generated nodes (via DataFlow):
    - CreateBudgetHistoryNode
    - ReadBudgetHistoryNode
    - ListBudgetHistoryNode
    - CountBudgetHistoryNode

    Attributes:
        id: Auto-generated primary key
        external_agent_id: Foreign key to ExternalAgentBudget
        year: Year of archived data
        month: Month of archived data (1-12)
        monthly_spent_usd: Total spending for the month
        monthly_execution_count: Total executions for the month
        archived_at: Timestamp when data was archived
        metadata: Additional context
    """

    id: str | None = None  # Auto-generated
    external_agent_id: str = ""
    year: int = 0
    month: int = 0
    monthly_spent_usd: float = 0.0
    monthly_execution_count: int = 0
    archived_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetAlertModel:
    """
    Budget alert records for threshold violations.

    Tracks when budgets exceed warning/degradation thresholds.

    Generated nodes (via DataFlow):
    - CreateBudgetAlertNode
    - ReadBudgetAlertNode
    - ListBudgetAlertNode
    - CountBudgetAlertNode

    Attributes:
        id: Auto-generated primary key
        external_agent_id: Agent that triggered alert
        alert_type: "warning", "degradation", or "exceeded"
        usage_percentage: Usage level when alert triggered (0.0-1.0)
        remaining_budget_usd: Remaining budget at alert time
        timestamp: When alert was triggered
        acknowledged: Whether alert has been reviewed
        acknowledged_by: User who acknowledged alert
        acknowledged_at: When alert was acknowledged
        metadata: Additional context
    """

    id: str | None = None  # Auto-generated
    external_agent_id: str = ""
    alert_type: str = "warning"  # warning, degradation, exceeded
    usage_percentage: float = 0.0
    remaining_budget_usd: float = 0.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BudgetUsageLogModel:
    """
    Detailed log of every budget usage event.

    Provides audit trail for all external agent executions.

    Generated nodes (via DataFlow):
    - CreateBudgetUsageLogNode
    - ReadBudgetUsageLogNode
    - ListBudgetUsageLogNode
    - CountBudgetUsageLogNode

    Attributes:
        id: Auto-generated primary key
        external_agent_id: Agent that executed
        execution_id: Unique execution identifier
        estimated_cost: Cost estimate before execution
        actual_cost: Actual cost after execution
        execution_success: Whether execution succeeded
        timestamp: Execution timestamp
        platform_type: Platform type (copilot_studio, etc.)
        complexity: Complexity level (simple, standard, complex)
        input_tokens: Input token count if applicable
        output_tokens: Output token count if applicable
        metadata: Additional execution context
    """

    id: str | None = None  # Auto-generated
    external_agent_id: str = ""
    execution_id: str = ""
    estimated_cost: float = 0.0
    actual_cost: float = 0.0
    execution_success: bool = True
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    platform_type: str = ""
    complexity: str = "standard"
    input_tokens: int | None = None
    output_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalPolicyModel:
    """
    Persistent approval policy configuration.

    Defines when approval is required for external agent invocations.

    Generated nodes (via DataFlow):
    - CreateApprovalPolicyNode
    - ReadApprovalPolicyNode
    - UpdateApprovalPolicyNode
    - DeleteApprovalPolicyNode
    - ListApprovalPolicyNode
    - CountApprovalPolicyNode
    - BulkCreateApprovalPolicyNode
    - BulkUpdateApprovalPolicyNode
    - BulkDeleteApprovalPolicyNode

    Attributes:
        external_agent_id: Agent this policy applies to (primary key)
        require_for_cost_above: Require approval if cost exceeds this (USD), None for no cost-based approval
        require_for_environments: JSON list of environments requiring approval
        require_for_data_classifications: JSON list of data classifications requiring approval
        require_for_operations: JSON list of operations requiring approval
        approval_level: Who must approve (team_lead, admin, owner, custom)
        custom_approvers: JSON list of user IDs for custom approval level
        approval_timeout_seconds: Timeout in seconds (default 3600)
        enabled: Whether policy is active
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metadata: JSON metadata field
    """

    external_agent_id: str  # Primary key
    require_for_cost_above: float | None = None
    require_for_environments: list[str] = field(default_factory=list)
    require_for_data_classifications: list[str] = field(default_factory=list)
    require_for_operations: list[str] = field(default_factory=list)
    approval_level: str = "team_lead"  # team_lead, admin, owner, custom
    custom_approvers: list[str] = field(default_factory=list)
    approval_timeout_seconds: int = 3600
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ApprovalRequestModel:
    """
    Approval request for external agent invocation.

    Tracks approval workflow from request to decision.

    Generated nodes (via DataFlow):
    - CreateApprovalRequestNode
    - ReadApprovalRequestNode
    - UpdateApprovalRequestNode
    - DeleteApprovalRequestNode
    - ListApprovalRequestNode
    - CountApprovalRequestNode
    - BulkCreateApprovalRequestNode
    - BulkUpdateApprovalRequestNode
    - BulkDeleteApprovalRequestNode

    Attributes:
        id: Unique approval request ID (primary key)
        external_agent_id: Agent being invoked
        requested_by: User ID who requested the invocation
        approvers: JSON list of user IDs who can approve
        status: Current status (pending, approved, rejected, timeout, bypassed)
        approval_reason: Human-readable reason for approval requirement
        request_metadata: JSON context about the request (cost, environment, operation, etc.)
        created_at: When request was created
        approved_at: When request was approved/rejected (None if pending)
        approved_by: User ID who approved/rejected (None if pending)
        rejection_reason: Reason for rejection (None if not rejected)
        bypass_justification: Justification for emergency bypass (None if not bypassed)
        timeout_at: When request will timeout
        metadata: Additional request metadata
    """

    id: str  # Primary key
    external_agent_id: str = ""
    requested_by: str = ""
    approvers: list[str] = field(default_factory=list)
    status: str = "pending"  # pending, approved, rejected, timeout, bypassed
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
class ApprovalAuditLogModel:
    """
    Audit log for all approval-related actions.

    Provides immutable audit trail for compliance.

    Generated nodes (via DataFlow):
    - CreateApprovalAuditLogNode
    - ReadApprovalAuditLogNode
    - ListApprovalAuditLogNode
    - CountApprovalAuditLogNode

    Attributes:
        id: Auto-generated primary key
        approval_request_id: Related approval request
        action: Action performed (created, approved, rejected, timeout, bypassed)
        actor_id: User who performed action
        timestamp: Action timestamp
        details: JSON details about the action
        metadata: Additional context
    """

    id: str | None = None  # Auto-generated
    approval_request_id: str = ""
    action: str = ""  # created, approved, rejected, timeout, bypassed
    actor_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# Export all models
__all__ = [
    "ExternalAgentBudgetModel",
    "BudgetHistoryModel",
    "BudgetAlertModel",
    "BudgetUsageLogModel",
    "ApprovalPolicyModel",
    "ApprovalRequestModel",
    "ApprovalAuditLogModel",
]
