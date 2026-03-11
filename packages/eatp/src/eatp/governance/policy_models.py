# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
DataFlow models for External Agent Policy persistence.

Defines database schemas for policies, conditions, and evaluation audit logs.
Uses DataFlow @db.model decorator for automatic node generation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ExternalAgentPolicyModel:
    """
    Persistent policy configuration for external agents.

    Generated nodes (via DataFlow):
    - CreateExternalAgentPolicyNode
    - ReadExternalAgentPolicyNode
    - UpdateExternalAgentPolicyNode
    - DeleteExternalAgentPolicyNode
    - ListExternalAgentPolicyNode
    - CountExternalAgentPolicyNode
    - BulkCreateExternalAgentPolicyNode
    - BulkUpdateExternalAgentPolicyNode
    - BulkDeleteExternalAgentPolicyNode

    Attributes:
        policy_id: Unique policy identifier (primary key)
        name: Human-readable policy name
        effect: Policy effect ("ALLOW" or "DENY")
        priority: Priority for conflict resolution (lower = higher priority)
        description: Optional policy description
        enabled: Whether policy is active
        conditions_json: JSON-encoded list of conditions
        org_id: Organization identifier
        created_by: User who created policy
        created_at: Creation timestamp
        updated_at: Last update timestamp
        metadata: Additional policy metadata
    """

    policy_id: str  # Primary key
    name: str
    effect: str  # "ALLOW" or "DENY"
    priority: int = 100
    description: str | None = None
    enabled: bool = True
    conditions_json: str = "{}"  # JSON-encoded conditions
    org_id: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyEvaluationLogModel:
    """
    Audit log for policy evaluations.

    Records every policy evaluation for compliance and debugging.

    Generated nodes (via DataFlow):
    - CreatePolicyEvaluationLogNode
    - ReadPolicyEvaluationLogNode
    - ListPolicyEvaluationLogNode
    - CountPolicyEvaluationLogNode

    Attributes:
        id: Auto-generated primary key
        external_agent_id: Agent that was evaluated
        action: Action that was attempted (invoke, configure, delete)
        effect: Final decision (ALLOW or DENY)
        reason: Human-readable reason for decision
        matched_policies: Comma-separated list of matched policy IDs
        evaluation_time_ms: Time taken to evaluate (milliseconds)
        conflict_resolution_strategy: Strategy used (deny_overrides, etc.)
        principal_provider: Agent provider
        principal_environment: Agent environment
        principal_tags: Comma-separated list of agent tags
        principal_location: JSON-encoded location data
        timestamp: Evaluation timestamp
        user_id: User who initiated request (if applicable)
        ip_address: Request IP address
        metadata: Additional evaluation context
    """

    id: str | None = None  # Auto-generated
    external_agent_id: str = ""
    action: str = "invoke"
    effect: str = "DENY"
    reason: str = ""
    matched_policies: str = ""  # Comma-separated policy IDs
    evaluation_time_ms: float = 0.0
    conflict_resolution_strategy: str = "deny_overrides"
    principal_provider: str = ""
    principal_environment: str = "development"
    principal_tags: str = ""  # Comma-separated tags
    principal_location: str = "{}"  # JSON-encoded location
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    ip_address: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyViolationModel:
    """
    Records policy violations for alerting and compliance.

    Tracks DENY decisions for security monitoring.

    Generated nodes (via DataFlow):
    - CreatePolicyViolationNode
    - ReadPolicyViolationNode
    - ListPolicyViolationNode
    - CountPolicyViolationNode

    Attributes:
        id: Auto-generated primary key
        external_agent_id: Agent that violated policy
        policy_id: Policy that was violated
        action: Action that was denied
        reason: Reason for denial
        timestamp: Violation timestamp
        user_id: User who attempted action
        ip_address: Request IP address
        acknowledged: Whether violation has been reviewed
        acknowledged_by: User who acknowledged violation
        acknowledged_at: When violation was acknowledged
        severity: Violation severity (low, medium, high, critical)
        metadata: Additional violation context
    """

    id: str | None = None  # Auto-generated
    external_agent_id: str = ""
    policy_id: str = ""
    action: str = "invoke"
    reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str | None = None
    ip_address: str | None = None
    acknowledged: bool = False
    acknowledged_by: str | None = None
    acknowledged_at: datetime | None = None
    severity: str = "medium"  # low, medium, high, critical
    metadata: dict[str, Any] = field(default_factory=dict)


# Export all models
__all__ = [
    "ExternalAgentPolicyModel",
    "PolicyEvaluationLogModel",
    "PolicyViolationModel",
]
