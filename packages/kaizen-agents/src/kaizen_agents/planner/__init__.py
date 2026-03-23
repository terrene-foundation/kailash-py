"""Planning intelligence: decompose objectives into governed multi-agent plans.

Modules:
    decomposer: TaskDecomposer — breaks objectives into subtasks via LLM.
    designer: AgentDesigner — translates subtasks into AgentSpec blueprints.
    composer: PlanComposer — assembles Plan DAGs from subtasks + specs.
"""

from kaizen_agents.planner.composer import PlanComposer, PlanValidator, ValidationError
from kaizen_agents.planner.decomposer import Subtask, TaskDecomposer
from kaizen_agents.planner.designer import (
    AgentDesigner,
    CapabilityMatch,
    CapabilityMatcher,
    SpawnDecision,
    SpawnPolicy,
)

__all__ = [
    "AgentDesigner",
    "CapabilityMatch",
    "CapabilityMatcher",
    "PlanComposer",
    "PlanValidator",
    "SpawnDecision",
    "SpawnPolicy",
    "Subtask",
    "TaskDecomposer",
    "ValidationError",
]
