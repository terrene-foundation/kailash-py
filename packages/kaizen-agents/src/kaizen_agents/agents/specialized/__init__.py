"""Specialized single-purpose agents ready for production use."""

from typing import TYPE_CHECKING, Any

from kaizen_agents.agents.specialized.chain_of_thought import ChainOfThoughtAgent
from kaizen_agents.agents.specialized.code_generation import CodeGenerationAgent
from kaizen_agents.agents.specialized.memory_agent import MemoryAgent
from kaizen_agents.agents.specialized.planning import PlanningAgent, PlanningConfig
from kaizen_agents.agents.specialized.react import ReActAgent
from kaizen_agents.agents.specialized.simple_qa import SimpleQAAgent

if TYPE_CHECKING:
    # Static-analysis-only import so pyright / mypy / Sphinx resolve the symbol
    # without dragging RAGResearchAgent's optional numpy dependency into the
    # eager import path (see __getattr__ below).
    from kaizen_agents.agents.specialized.rag_research import RAGResearchAgent

__all__ = [
    "SimpleQAAgent",
    "ChainOfThoughtAgent",
    "ReActAgent",
    "PlanningAgent",
    "PlanningConfig",
    "RAGResearchAgent",
    "CodeGenerationAgent",
    "MemoryAgent",
]


def __getattr__(name: str) -> Any:
    """Lazily import optional-dependency agents (PEP 562).

    ``RAGResearchAgent`` pulls in ``kaizen.retrieval.vector_store``, which
    imports numpy — an OPTIONAL dependency that ships only under
    ``kailash-kaizen[rag]``. Importing any other specialized agent (or this
    package) must NOT require numpy, so RAGResearchAgent resolves lazily here
    instead of at module scope. When numpy is absent the underlying
    ``ImportError`` propagates with its original actionable message.
    """
    if name == "RAGResearchAgent":
        from kaizen_agents.agents.specialized.rag_research import RAGResearchAgent

        return RAGResearchAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
