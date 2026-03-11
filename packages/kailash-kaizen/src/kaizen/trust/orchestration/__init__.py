"""
Kaizen Trust Orchestration Module - Trust-Aware Multi-Agent Orchestration.

This module integrates EATP trust verification with Kaizen's orchestration
runtime, enabling trust-aware workflow execution across multiple agents.

Key Components:
- TrustExecutionContext: Carries trust state through workflow execution
- TrustPolicy: Defines trust requirements for orchestration
- TrustPolicyEngine: Evaluates policies before agent actions
- TrustAwareOrchestrationRuntime: Orchestration with trust verification

Example:
    from kaizen.trust.orchestration import (
        TrustAwareOrchestrationRuntime,
        TrustExecutionContext,
        TrustPolicy,
        TrustPolicyEngine,
    )

    # Create trust-aware runtime
    runtime = TrustAwareOrchestrationRuntime(
        trust_operations=trust_ops,
        agent_registry=registry,
        config=OrchestrationRuntimeConfig(max_concurrent_agents=10)
    )

    # Create execution context
    context = TrustExecutionContext.create(
        parent_agent_id="supervisor-001",
        task_id="workflow-123",
        delegated_capabilities=["analyze_data", "generate_report"],
    )

    # Execute with trust enforcement
    results = await runtime.execute_trusted_workflow(
        tasks=["analyze Q3 data", "generate summary"],
        context=context,
    )
"""

from kaizen.trust.orchestration.exceptions import (
    ConstraintLooseningError,
    ContextPropagationError,
    DelegationChainError,
    OrchestrationTrustError,
    PolicyViolationError,
    TrustVerificationFailedError,
)
from kaizen.trust.orchestration.execution_context import (
    ContextMergeStrategy,
    DelegationEntry,
    TrustExecutionContext,
)
from kaizen.trust.orchestration.policy import (
    PolicyResult,
    PolicyType,
    TrustPolicy,
    TrustPolicyEngine,
)
from kaizen.trust.orchestration.runtime import (
    TrustAwareOrchestrationRuntime,
    TrustAwareRuntimeConfig,
)

__all__ = [
    # Execution Context
    "TrustExecutionContext",
    "DelegationEntry",
    "ContextMergeStrategy",
    # Policy
    "TrustPolicy",
    "PolicyType",
    "PolicyResult",
    "TrustPolicyEngine",
    # Runtime
    "TrustAwareOrchestrationRuntime",
    "TrustAwareRuntimeConfig",
    # Exceptions
    "OrchestrationTrustError",
    "TrustVerificationFailedError",
    "PolicyViolationError",
    "ConstraintLooseningError",
    "DelegationChainError",
    "ContextPropagationError",
]
