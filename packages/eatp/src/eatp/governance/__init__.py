# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
External Agent Governance.

Budget enforcement, cost estimation, reset scheduling, rate limiting, policy-based
access control, and approval workflows for external agents.

Key Components:
    - ExternalAgentCostEstimator: Platform-specific cost estimation
    - ExternalAgentRateLimiter: Token-bucket rate limiting
    - ExternalAgentPolicyEngine: Attribute-Based Access Control (ABAC)
    - ExternalAgentBudgetEnforcer: Multi-dimensional budget tracking (requires extraction)
    - ApprovalManager: Approval workflows with routing and timeout (requires extraction)
    - BudgetResetService: Scheduled daily/monthly resets (requires extraction)
"""

from eatp.governance.cost_estimator import (
    CostEstimate,
    ExternalAgentCostEstimator,
)
from eatp.governance.models import (
    ApprovalAuditLogModel,
    ApprovalPolicyModel,
    ApprovalRequestModel,
    BudgetAlertModel,
    BudgetHistoryModel,
    BudgetUsageLogModel,
    ExternalAgentBudgetModel,
)
from eatp.governance.policy_engine import (
    ConflictResolutionStrategy,
    EnvironmentCondition,
    ExternalAgentPolicy,
    ExternalAgentPolicyContext,
    ExternalAgentPolicyEngine,
    ExternalAgentPrincipal,
    LocationCondition,
    PolicyCondition,
    PolicyEffect,
    PolicyEvaluationResult,
    ProviderCondition,
    TagCondition,
    TimeWindowCondition,
)
from eatp.governance.policy_models import (
    ExternalAgentPolicyModel,
    PolicyEvaluationLogModel,
    PolicyViolationModel,
)
from eatp.governance.rate_limiter import (
    ExternalAgentRateLimiter,
    RateLimitCheckResult,
    RateLimitConfig,
    RateLimitError,
    RateLimitMetrics,
)

__all__ = [
    # Cost estimation
    "ExternalAgentCostEstimator",
    "CostEstimate",
    # Rate limiting
    "ExternalAgentRateLimiter",
    "RateLimitCheckResult",
    "RateLimitConfig",
    "RateLimitError",
    "RateLimitMetrics",
    # Policy engine
    "ExternalAgentPolicyEngine",
    "ExternalAgentPolicy",
    "ExternalAgentPolicyContext",
    "ExternalAgentPrincipal",
    "PolicyEvaluationResult",
    "PolicyEffect",
    "ConflictResolutionStrategy",
    # Policy conditions
    "PolicyCondition",
    "TimeWindowCondition",
    "LocationCondition",
    "EnvironmentCondition",
    "ProviderCondition",
    "TagCondition",
    # DataFlow models
    "ExternalAgentBudgetModel",
    "BudgetHistoryModel",
    "BudgetAlertModel",
    "BudgetUsageLogModel",
    "ExternalAgentPolicyModel",
    "PolicyEvaluationLogModel",
    "PolicyViolationModel",
    "ApprovalPolicyModel",
    "ApprovalRequestModel",
    "ApprovalAuditLogModel",
]
