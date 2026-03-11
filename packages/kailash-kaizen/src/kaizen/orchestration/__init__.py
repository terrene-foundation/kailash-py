"""
Kaizen Orchestration - Multi-Agent Coordination and Pipelines

This module provides orchestration patterns for coordinating multiple agents
and creating composable pipelines.

Submodules:
- patterns: Multi-agent coordination patterns (SupervisorWorker, Consensus, etc.)
- core: Core orchestration infrastructure (patterns, teams)
- pipeline: Pipeline infrastructure for composability
- runtime: Orchestration runtime for 10-100 agent scaling
- registry: Agent registry for 100+ agent distributed scaling
- models: DataFlow state models for workflow persistence (NEW - Phase 2)
"""

# Explicit exports from core modules
from kaizen.orchestration import core, patterns  # noqa: F401
from kaizen.orchestration.models import (
    AGENT_STATUS_VALUES,
    CHECKPOINT_TYPE_VALUES,
    ROUTING_STRATEGY_VALUES,
    WORKFLOW_STATUS_VALUES,
    AgentExecutionRecord,
    WorkflowCheckpoint,
    WorkflowState,
    validate_agent_execution_record,
    validate_workflow_checkpoint,
    validate_workflow_state,
)
from kaizen.orchestration.pipeline import Pipeline, SequentialPipeline
from kaizen.orchestration.registry import (
    AgentRegistry,
    AgentRegistryConfig,
    RegistryEvent,
    RegistryEventType,
)
from kaizen.orchestration.runtime import (
    AgentStatus,
    ErrorHandlingMode,
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
    RetryPolicy,
    RoutingStrategy,
)

__all__ = [
    # Core modules
    "patterns",
    "core",
    # Pipeline infrastructure
    "Pipeline",
    "SequentialPipeline",
    # Orchestration runtime
    "OrchestrationRuntime",
    "OrchestrationRuntimeConfig",
    "RetryPolicy",
    "AgentStatus",
    "RoutingStrategy",
    "ErrorHandlingMode",
    # Agent registry
    "AgentRegistry",
    "AgentRegistryConfig",
    "RegistryEvent",
    "RegistryEventType",
    # DataFlow state models (Phase 2)
    "WorkflowState",
    "AgentExecutionRecord",
    "WorkflowCheckpoint",
    "validate_workflow_state",
    "validate_agent_execution_record",
    "validate_workflow_checkpoint",
    "WORKFLOW_STATUS_VALUES",
    "AGENT_STATUS_VALUES",
    "CHECKPOINT_TYPE_VALUES",
    "ROUTING_STRATEGY_VALUES",
]
