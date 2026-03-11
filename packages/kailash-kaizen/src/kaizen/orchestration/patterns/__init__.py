"""
Kaizen Orchestration Patterns

Multi-agent coordination patterns for complex workflows.

Patterns:
- SupervisorWorkerPattern: Hierarchical coordination with task routing
- ConsensusPattern: Democratic decision-making across agents
- DebatePattern: Adversarial discussion for robust conclusions
- HandoffPattern: Sequential task handoff between specialists
- SequentialPipelinePattern: Pipeline execution across multiple agents
"""

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
    TaskExecutionSignature,
    create_handoff_pattern,
)
from kaizen.orchestration.patterns.sequential import (
    PipelineStageAgent,
    SequentialPipelinePattern,
    StageProcessingSignature,
    create_sequential_pipeline,
)
from kaizen.orchestration.patterns.supervisor_worker import (
    CoordinatorAgent,
    ProgressMonitoringSignature,
    ResultAggregationSignature,
    SupervisorAgent,
    SupervisorWorkerPattern,
    TaskDelegationSignature,
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
]
