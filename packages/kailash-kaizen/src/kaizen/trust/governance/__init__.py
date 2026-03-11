"""
External Agent Governance.

Budget enforcement, cost estimation, reset scheduling, rate limiting, policy-based
access control, and approval workflows for external agents (Microsoft Copilot, custom REST APIs, third-party AI systems).

Key Components:
    - ExternalAgentCostEstimator: Platform-specific cost estimation
    - ExternalAgentBudgetEnforcer: Multi-dimensional budget tracking
    - BudgetResetService: Scheduled daily/monthly resets
    - ExternalAgentRateLimiter: Token-bucket rate limiting
    - ExternalAgentPolicyEngine: Attribute-Based Access Control (ABAC)
    - ApprovalManager: Approval workflows with routing and timeout

Examples:
    >>> from kaizen.trust.governance import (
    ...     ExternalAgentCostEstimator,
    ...     ExternalAgentBudgetEnforcer,
    ...     ExternalAgentBudget,
    ...     BudgetResetService,
    ...     ExternalAgentPolicyEngine,
    ...     ExternalAgentPolicy,
    ...     PolicyEffect,
    ...     ApprovalManager,
    ...     ApprovalPolicy,
    ...     ApprovalLevel,
    ... )
    >>> from kailash.runtime import AsyncLocalRuntime
    >>>
    >>> # Cost estimation
    >>> estimator = ExternalAgentCostEstimator()
    >>> cost = estimator.estimate_cost("copilot_studio", "hr_assistant", complexity="standard")
    >>> print(f"Estimated cost: ${cost:.4f}")
    >>>
    >>> # Budget enforcement
    >>> runtime = AsyncLocalRuntime()
    >>> enforcer = ExternalAgentBudgetEnforcer(runtime=runtime)
    >>> budget = ExternalAgentBudget(
    ...     external_agent_id="copilot_hr",
    ...     monthly_budget_usd=100.0,
    ...     monthly_spent_usd=50.0
    ... )
    >>> result = await enforcer.check_budget(budget, estimated_cost=10.0)
    >>> if result.allowed:
    ...     # Execute agent
    ...     await enforcer.record_usage(budget, actual_cost=9.5, execution_success=True)
    >>>
    >>> # Budget reset (scheduled)
    >>> reset_service = BudgetResetService(runtime=runtime)
    >>> await reset_service.reset_daily_budgets()
    >>>
    >>> # Policy-based access control
    >>> engine = ExternalAgentPolicyEngine(runtime=runtime)
    >>> policy = ExternalAgentPolicy(
    ...     policy_id="allow_copilot_prod",
    ...     name="Allow Copilot in Production",
    ...     effect=PolicyEffect.ALLOW,
    ...     conditions=[
    ...         ProviderCondition(allowed_providers=["copilot_studio"]),
    ...         EnvironmentCondition(allowed_environments=["production"])
    ...     ]
    ... )
    >>> engine.add_policy(policy)
    >>> result = await engine.evaluate_policies(context)
    >>>
    >>> # Approval workflows
    >>> manager = ApprovalManager(runtime=runtime)
    >>> policy = ApprovalPolicy(
    ...     external_agent_id="copilot_hr",
    ...     require_for_cost_above=10.0,
    ...     approval_level=ApprovalLevel.TEAM_LEAD
    ... )
    >>> approval_id = await manager.request_approval("copilot_hr", "user-123", policy)
    >>> await manager.approve_request(approval_id, "lead-456")
"""

from kaizen.trust.governance.approval_manager import (
    ApprovalLevel,
    ApprovalManager,
    ApprovalPolicy,
    ApprovalRequest,
    ApprovalResult,
    ApprovalStatus,
)
from kaizen.trust.governance.budget_enforcer import (
    BudgetCheckResult,
    ExternalAgentBudget,
    ExternalAgentBudgetEnforcer,
)
from kaizen.trust.governance.budget_reset import BudgetResetService
from kaizen.trust.governance.cost_estimator import (
    CostEstimate,
    ExternalAgentCostEstimator,
)
from kaizen.trust.governance.models import (
    ApprovalAuditLogModel,
    ApprovalPolicyModel,
    ApprovalRequestModel,
    BudgetAlertModel,
    BudgetHistoryModel,
    BudgetUsageLogModel,
    ExternalAgentBudgetModel,
)
from kaizen.trust.governance.policy_engine import (
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
from kaizen.trust.governance.policy_models import (
    ExternalAgentPolicyModel,
    PolicyEvaluationLogModel,
    PolicyViolationModel,
)
from kaizen.trust.governance.rate_limiter import (
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
    # Budget enforcement
    "ExternalAgentBudgetEnforcer",
    "ExternalAgentBudget",
    "BudgetCheckResult",
    # Budget reset
    "BudgetResetService",
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
    # Approval workflows
    "ApprovalManager",
    "ApprovalPolicy",
    "ApprovalRequest",
    "ApprovalResult",
    "ApprovalLevel",
    "ApprovalStatus",
    # Budget DataFlow models
    "ExternalAgentBudgetModel",
    "BudgetHistoryModel",
    "BudgetAlertModel",
    "BudgetUsageLogModel",
    # Policy DataFlow models
    "ExternalAgentPolicyModel",
    "PolicyEvaluationLogModel",
    "PolicyViolationModel",
    # Approval DataFlow models
    "ApprovalPolicyModel",
    "ApprovalRequestModel",
    "ApprovalAuditLogModel",
]
