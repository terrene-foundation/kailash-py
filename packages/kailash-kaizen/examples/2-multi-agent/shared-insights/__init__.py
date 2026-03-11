"""
Multi-Agent Shared Memory Collaboration Example.

This package demonstrates multi-agent collaboration using SharedMemoryPool.
"""

from .workflow import (
    AnalystAgent,
    ResearcherAgent,
    SynthesizerAgent,
    research_collaboration_workflow,
)

__all__ = [
    "ResearcherAgent",
    "AnalystAgent",
    "SynthesizerAgent",
    "research_collaboration_workflow",
]
