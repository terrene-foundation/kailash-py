"""
Multi-Agent Coordination Patterns (DEPRECATED)

⚠️ DEPRECATION WARNING:
This module has been moved to kaizen.orchestration.patterns
Please update your imports to use the new location:

OLD: from kaizen.agents.coordination import create_supervisor_worker_pattern
NEW: from kaizen.orchestration.patterns import create_supervisor_worker_pattern

This compatibility layer will be removed in v0.5.0

---

This module provides production-ready multi-agent coordination patterns
that can be used directly via factory functions.

Patterns provide zero-config defaults with progressive configuration support.

Usage:
    from kaizen.orchestration.patterns import create_supervisor_worker_pattern

    # Zero-config usage
    pattern = create_supervisor_worker_pattern()
    tasks = pattern.delegate("Process 100 documents")
    results = pattern.aggregate_results(tasks[0]["request_id"])

    # Progressive configuration
    pattern = create_supervisor_worker_pattern(
        num_workers=5,
        model="gpt-4"
    )

Creating Custom Patterns:
    See examples/guides/creating-custom-multi-agent-patterns/ for tutorials on:
    - Extending BaseMultiAgentPattern
    - Creating custom coordination logic
    - Implementing pattern factories
"""

import warnings

# Show deprecation warning
warnings.warn(
    "kaizen.agents.coordination is deprecated and will be removed in v0.5.0. "
    "Please use kaizen.orchestration.patterns instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from new location for backward compatibility
from kaizen.orchestration.patterns.base_pattern import BaseMultiAgentPattern
from kaizen.orchestration.patterns.consensus import (
    AggregatorAgent,
    ConsensusAggregationSignature,
    ConsensusPattern,
    ProposalCreationSignature,
    ProposerAgent,
    VoterAgent,
    VotingSignature,
    create_consensus_pattern,
)
from kaizen.orchestration.patterns.debate import (
    ArgumentConstructionSignature,
    DebatePattern,
    JudgeAgent,
    JudgmentSignature,
    OpponentAgent,
    ProponentAgent,
    RebuttalSignature,
    create_debate_pattern,
)
from kaizen.orchestration.patterns.handoff import (
    HandoffAgent,
    HandoffPattern,
    TaskEvaluationSignature,
    create_handoff_pattern,
)
from kaizen.orchestration.patterns.sequential import (
    PipelineStageAgent,
    SequentialPipelinePattern,
    StageProcessingSignature,
    create_sequential_pipeline,
)

# Note: TaskExecutionSignature exists in both handoff and supervisor_worker
# We export the one from supervisor_worker for backward compatibility
from kaizen.orchestration.patterns.supervisor_worker import (
    CoordinatorAgent,
    ProgressMonitoringSignature,
    ResultAggregationSignature,
    SupervisorAgent,
    SupervisorWorkerPattern,
    TaskDelegationSignature,
    TaskExecutionSignature,
    WorkerAgent,
    create_supervisor_worker_pattern,
)

__all__ = [
    "BaseMultiAgentPattern",
    "SupervisorWorkerPattern",
    "SupervisorAgent",
    "WorkerAgent",
    "CoordinatorAgent",
    "create_supervisor_worker_pattern",
    "TaskDelegationSignature",
    "TaskExecutionSignature",
    "ResultAggregationSignature",
    "ProgressMonitoringSignature",
    "ConsensusPattern",
    "ProposerAgent",
    "VoterAgent",
    "AggregatorAgent",
    "create_consensus_pattern",
    "ProposalCreationSignature",
    "VotingSignature",
    "ConsensusAggregationSignature",
    "DebatePattern",
    "ProponentAgent",
    "OpponentAgent",
    "JudgeAgent",
    "create_debate_pattern",
    "ArgumentConstructionSignature",
    "RebuttalSignature",
    "JudgmentSignature",
    "SequentialPipelinePattern",
    "PipelineStageAgent",
    "create_sequential_pipeline",
    "StageProcessingSignature",
    "HandoffPattern",
    "HandoffAgent",
    "create_handoff_pattern",
    "TaskEvaluationSignature",
    "TaskExecutionSignature",
]
