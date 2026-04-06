"""
kaizen-agents: PACT-governed autonomous agent engines built on Kailash Kaizen SDK.

Layer 2 (ENGINES) — LLM judgment layer on top of Layer 1 primitives (kailash-kaizen).

Provides:
- Agent: Canonical async-first unified Agent API
- GovernedSupervisor: progressive-disclosure entry point (model+budget → run)
- Specialized agents: ReAct, RAG, ToT, CoT, vision, audio, streaming
- Multi-agent patterns: debate, supervisor-worker, pipeline, consensus, ensemble
- Journey orchestration: multi-pathway user journeys with intent detection
- Workflow templates: enterprise workflow patterns
- Orchestration: planner, protocols, recovery, monitoring
- Governance: accountability, clearance, cascade, vacancy, dereliction, bypass, budget
"""

__version__ = "0.7.0"

from kaizen_agents.supervisor import GovernedSupervisor, SupervisorResult

# Delegate facade — the primary entry point for autonomous AI execution
from kaizen_agents.delegate import Delegate

# Canonical async Agent API (moved from kailash-kaizen api/)
try:
    from kaizen_agents.api.agent import Agent
except ImportError:
    Agent = None  # type: ignore[assignment, misc]

# Key re-exports for convenience
try:
    from kaizen_agents.agents.specialized.react import ReActAgent
    from kaizen_agents.patterns.pipeline import Pipeline
except ImportError:
    ReActAgent = None  # type: ignore[assignment, misc]
    Pipeline = None  # type: ignore[assignment, misc]

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
    "Delegate",
    "GovernedSupervisor",
    "SupervisorResult",
    "Agent",
    "ReActAgent",
    "Pipeline",
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
