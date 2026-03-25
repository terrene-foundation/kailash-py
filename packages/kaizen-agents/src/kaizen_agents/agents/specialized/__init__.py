"""Specialized single-purpose agents ready for production use."""

from kaizen_agents.agents.specialized.chain_of_thought import ChainOfThoughtAgent
from kaizen_agents.agents.specialized.code_generation import CodeGenerationAgent
from kaizen_agents.agents.specialized.memory_agent import MemoryAgent
from kaizen_agents.agents.specialized.planning import PlanningAgent, PlanningConfig
from kaizen_agents.agents.specialized.rag_research import RAGResearchAgent
from kaizen_agents.agents.specialized.react import ReActAgent
from kaizen_agents.agents.specialized.simple_qa import SimpleQAAgent

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
