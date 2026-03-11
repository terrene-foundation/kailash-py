"""
DataFlow AI Debug Agent - Production-ready debugging assistance for DataFlow errors.

Week 10 Task 4.2: DebugAgent Base Class Implementation
Week 10 Task 4.3: Error Pattern Recognition

Components:
- DebugAgent: Main agent class extending Kaizen KaizenNode
- ErrorAnalysisEngine: Error analysis using ErrorEnhancer
- PatternRecognitionEngine: Error pattern recognition and similarity matching
- DebugAgentSignature: Signature for AI debugging task
- KnowledgeBase: Pattern storage and learning

Architecture:
- Extends Kaizen BaseAgent with signature-based programming
- Integrates with ErrorEnhancer (delegate to it, no modifications)
- Core agent methods: analyze_error, suggest_solutions, diagnose_workflow
"""

from dataflow.debug.agent import DebugAgent
from dataflow.debug.data_structures import (
    Diagnosis,
    ErrorAnalysis,
    ErrorSolution,
    KnowledgeBase,
    NodeInfo,
    RankedSolution,
    WorkflowContext,
)
from dataflow.debug.error_analysis_engine import ErrorAnalysisEngine
from dataflow.debug.pattern_recognition import PatternRecognitionEngine
from dataflow.debug.signatures import DebugAgentSignature

__all__ = [
    "DebugAgent",
    "DebugAgentSignature",
    "ErrorAnalysisEngine",
    "PatternRecognitionEngine",
    "ErrorAnalysis",
    "ErrorSolution",
    "RankedSolution",
    "Diagnosis",
    "KnowledgeBase",
    "WorkflowContext",
    "NodeInfo",
]
