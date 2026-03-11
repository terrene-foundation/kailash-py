"""
Governance layer for external agent management.

Provides approval workflows, rate limiting, budget enforcement, and policy-based
controls for external agent invocations (Microsoft Copilot, custom tools, third-party AI).

This module implements:
- TODO-EXTINT-002: External Agent Rate Limiting
- TODO-EXTINT-003: External Agent Approval Workflows
- TODO-EXTINT-004: External Agent Policy Engine (ABAC)
"""

from kaizen.governance.approval_manager import (
    ApprovalLevel,
    ApprovalRequirement,
    ApprovalStatus,
    ExternalAgentApprovalManager,
    ExternalAgentApprovalRequest,
)
from kaizen.governance.policy_engine import (
    ConflictResolutionStrategy,
    DataClassification,
    DataClassificationCondition,
    Environment,
    EnvironmentCondition,
    ExternalAgentPolicy,
    ExternalAgentPolicyContext,
    ExternalAgentPolicyEngine,
    ExternalAgentPrincipal,
    LocationCondition,
    PolicyCondition,
    PolicyDecision,
    PolicyEffect,
    ProviderCondition,
    TagCondition,
    TimeWindowCondition,
)
from kaizen.governance.rate_limiter import (
    ExternalAgentRateLimiter,
    RateLimitCheckResult,
    RateLimitConfig,
    RateLimitError,
    RateLimitMetrics,
)

# DataFlow persistence (optional - requires kailash-dataflow)
try:
    from kaizen.governance.models import register_approval_models
    from kaizen.governance.storage import ExternalAgentApprovalStorage

    _DATAFLOW_AVAILABLE = True
except ImportError:
    register_approval_models = None  # type: ignore
    ExternalAgentApprovalStorage = None  # type: ignore
    _DATAFLOW_AVAILABLE = False

__all__ = [
    # Approval management
    "ApprovalLevel",
    "ApprovalRequirement",
    "ApprovalStatus",
    "ExternalAgentApprovalRequest",
    "ExternalAgentApprovalManager",
    # Rate limiting
    "ExternalAgentRateLimiter",
    "RateLimitConfig",
    "RateLimitCheckResult",
    "RateLimitError",
    "RateLimitMetrics",
    # Policy engine (ABAC)
    "PolicyEffect",
    "ConflictResolutionStrategy",
    "Environment",
    "DataClassification",
    "ExternalAgentPrincipal",
    "ExternalAgentPolicyContext",
    "PolicyCondition",
    "TimeWindowCondition",
    "LocationCondition",
    "EnvironmentCondition",
    "ProviderCondition",
    "TagCondition",
    "DataClassificationCondition",
    "ExternalAgentPolicy",
    "PolicyDecision",
    "ExternalAgentPolicyEngine",
    # DataFlow persistence (optional)
    "register_approval_models",
    "ExternalAgentApprovalStorage",
    "_DATAFLOW_AVAILABLE",
]
