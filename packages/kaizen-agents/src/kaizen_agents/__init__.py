"""
kaizen-agents: PACT-governed L3 autonomous agent orchestration layer.

Provides LLM-driven intelligence on top of kailash-kaizen SDK primitives:
- GovernedSupervisor: progressive-disclosure entry point (model+budget → run)
- TaskDecomposer: objective → subtasks
- PlanComposer: subtasks → Plan DAG
- AgentDesigner: subtask → AgentSpec
- FailureDiagnoser: failed node → root cause
- Recomposer: failed plan → PlanModification
- EnvelopeAllocator: parent envelope → child ratios
- Protocols: delegation, clarification, escalation, completion
- Governance: accountability, clearance, cascade, vacancy, dereliction, bypass, budget
"""

__version__ = "0.2.0"

from kaizen_agents.supervisor import GovernedSupervisor, SupervisorResult

__all__ = ["GovernedSupervisor", "SupervisorResult"]
