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
from kaizen_agents.patterns import core  # noqa: F401
from kaizen_agents.patterns.models import (
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
from kaizen_agents.patterns.pipeline import Pipeline, SequentialPipeline
from kaizen_agents.patterns.registry import (
    AgentRegistry,
    AgentRegistryConfig,
    RegistryEvent,
    RegistryEventType,
)
from kaizen_agents.patterns.runtime import (
    AgentStatus,
    ErrorHandlingMode,
    OrchestrationRuntime,
    OrchestrationRuntimeConfig,
    RetryPolicy,
    RoutingStrategy,
)

# Multi-agent patterns
try:
    from kaizen_agents.patterns.patterns import (
        BaseMultiAgentPattern,
        ConsensusPattern,
        DebatePattern,
        HandoffPattern,
        SequentialPipelinePattern,
        SupervisorWorkerPattern,
        create_consensus_pattern,
        create_debate_pattern,
        create_handoff_pattern,
        create_sequential_pipeline,
        create_supervisor_worker_pattern,
    )
except ImportError:
    BaseMultiAgentPattern = None  # type: ignore[assignment,misc]
    ConsensusPattern = None  # type: ignore[assignment,misc]
    DebatePattern = None  # type: ignore[assignment,misc]
    HandoffPattern = None  # type: ignore[assignment,misc]
    SequentialPipelinePattern = None  # type: ignore[assignment,misc]
    SupervisorWorkerPattern = None  # type: ignore[assignment,misc]
    create_consensus_pattern = None  # type: ignore[assignment,misc]
    create_debate_pattern = None  # type: ignore[assignment,misc]
    create_handoff_pattern = None  # type: ignore[assignment,misc]
    create_sequential_pipeline = None  # type: ignore[assignment,misc]
    create_supervisor_worker_pattern = None  # type: ignore[assignment,misc]

__all__ = [
    # Core modules
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
    # Multi-agent patterns
    "BaseMultiAgentPattern",
    "SupervisorWorkerPattern",
    "ConsensusPattern",
    "DebatePattern",
    "HandoffPattern",
    "SequentialPipelinePattern",
    "create_supervisor_worker_pattern",
    "create_consensus_pattern",
    "create_debate_pattern",
    "create_handoff_pattern",
    "create_sequential_pipeline",
]
