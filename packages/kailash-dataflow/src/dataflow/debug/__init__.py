"""
DataFlow AI Debug Agent - Production-ready debugging assistance for DataFlow errors.

Components:
- DebugAgent: 5-stage pipeline orchestrator (Capture → Categorize → Analyze → Suggest → Format)
- KnowledgeBase: Pattern storage and learning
- Shared data types: Diagnosis, ErrorSolution, RankedSolution, WorkflowContext, NodeInfo
"""

from dataflow.debug.data_structures import (
    Diagnosis,
    ErrorAnalysis,
    ErrorSolution,
    NodeInfo,
    RankedSolution,
    WorkflowContext,
)
from dataflow.debug.debug_agent import DebugAgent
from dataflow.debug.knowledge_base import KnowledgeBase

__all__ = [
    "DebugAgent",
    "KnowledgeBase",
    "ErrorAnalysis",
    "ErrorSolution",
    "RankedSolution",
    "Diagnosis",
    "WorkflowContext",
    "NodeInfo",
]
