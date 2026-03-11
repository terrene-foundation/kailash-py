"""
DataFlow AI Debug Agent - Production-ready debugging assistant.

DebugAgent extends Kaizen KaizenNode with signature-based programming
to provide AI-powered error diagnosis and solution ranking.

Architecture:
- Extends Kaizen BaseAgent with signature-based programming
- Uses LLMAgentNode for AI reasoning
- Delegates to ErrorEnhancer for error analysis
- Delegates to Inspector for workflow introspection
- Stores patterns in Knowledge Base (in-memory/persistent)

Performance:
- Target: <5 seconds per diagnosis (95th percentile)
- LLM calls: 1-2 per diagnosis (minimize latency)
- Caching: Pattern cache for 90%+ hit rate on common errors
"""

from typing import TYPE_CHECKING, Any, Dict

from dataflow.debug.data_structures import (
    Diagnosis,
    ErrorSolution,
    KnowledgeBase,
    RankedSolution,
    WorkflowContext,
)
from dataflow.debug.error_analysis_engine import ErrorAnalysisEngine
from dataflow.debug.pattern_recognition import PatternRecognitionEngine
from dataflow.debug.signatures import DebugAgentSignature
from dataflow.debug.solution_ranking import SolutionRankingEngine
from dataflow.exceptions import EnhancedDataFlowError
from kaizen.nodes.base import KaizenNode, NodeParameter

if TYPE_CHECKING:
    from dataflow.core.error_enhancer import DataFlowErrorEnhancer
    from dataflow.platform.inspector import Inspector


class DebugAgent(KaizenNode):
    """
    AI-powered debugging agent for DataFlow errors.

    Integrates with:
    - ErrorEnhancer: 60+ error types with DF-XXX codes, context, causes, solutions
    - Inspector API: 30 methods for workflow introspection
    - Knowledge Base: Error-to-solution patterns, learned from feedback

    Architecture:
    - Extends Kaizen BaseAgent with signature-based programming
    - Uses LLMAgentNode for AI reasoning
    - Delegates to ErrorEnhancer for error analysis
    - Delegates to Inspector for workflow introspection
    - Stores patterns in Knowledge Base (in-memory/persistent)

    Performance:
    - Target: <5 seconds per diagnosis (95th percentile)
    - LLM calls: 1-2 per diagnosis (minimize latency)
    - Caching: Pattern cache for 90%+ hit rate on common errors
    """

    def __init__(
        self,
        id: str = "debug_agent",
        error_enhancer: "DataFlowErrorEnhancer" = None,
        inspector: "Inspector" = None,
        knowledge_base: KnowledgeBase = None,
        model: str = "gpt-4o-mini",  # Fast, cost-effective
        confidence_threshold: float = 0.7,
        **kwargs,
    ):
        """
        Initialize debug agent.

        Args:
            id: Node ID (default: debug_agent)
            error_enhancer: ErrorEnhancer instance (60+ error types)
            inspector: Inspector API instance (30 methods)
            knowledge_base: Pattern storage (in-memory or persistent)
            model: LLM model for reasoning (default: gpt-4o-mini for speed)
            confidence_threshold: Minimum confidence to provide recommendation
        """
        signature = DebugAgentSignature()
        super().__init__(id=id, signature=signature, model=model, **kwargs)

        self.error_enhancer = error_enhancer
        self.inspector = inspector
        self.knowledge_base = knowledge_base
        self.confidence_threshold = confidence_threshold

        # Initialize sub-components
        self.error_analysis_engine = ErrorAnalysisEngine(error_enhancer)
        self.pattern_recognition_engine = PatternRecognitionEngine(knowledge_base)
        self.solution_ranking_engine = SolutionRankingEngine(
            llm_agent=self,  # Use self as the LLM agent (KaizenNode)
            knowledge_base=knowledge_base,
            pattern_engine=self.pattern_recognition_engine,
        )

    def get_parameters(self) -> Dict[str, NodeParameter]:
        """
        Get node parameters (required by AINodeBase).

        DebugAgent is called programmatically rather than through workflow connections,
        so it returns an empty parameter dict.

        Returns:
            Empty dictionary since DebugAgent doesn't use traditional node parameters
        """
        return {}

    def diagnose_error(self, error: EnhancedDataFlowError, workflow) -> Diagnosis:
        """
        Diagnose error using integrated workflow.

        Internal workflow (Phase 1):
        1. ErrorAnalysisEngine.analyze_error() → ErrorAnalysis
        2. Simple priority-based ranking (no LLM yet)
        3. Build Diagnosis with top 3 solutions

        Args:
            error: Enhanced error from ErrorEnhancer
            workflow: Workflow to analyze

        Returns:
            Diagnosis with:
            - diagnosis: Root cause explanation
            - ranked_solutions: Top 3 solutions
            - confidence: Confidence score (0.0-1.0)
            - next_steps: Specific actions to take

        Performance:
        - Simple ranking: <1ms (no LLM, no cache)
        """
        # Step 1: Analyze error
        error_analysis = self.error_analysis_engine.analyze_error(error)

        # Step 2: Rank solutions using simple priority-based ranking
        # (Phase 1: No LLM integration yet - use simple ranking)
        ranked_solutions = self._rank_solutions_simple(error_analysis)

        # Step 3: Build diagnosis
        diagnosis_text = self._build_diagnosis_text(error_analysis)
        confidence = self._calculate_confidence_simple(ranked_solutions)
        next_steps = self._build_next_steps(ranked_solutions)

        return Diagnosis(
            diagnosis=diagnosis_text,
            ranked_solutions=ranked_solutions[:3],  # Top 3
            confidence=confidence,
            next_steps=next_steps,
        )

    def _rank_solutions_simple(self, error_analysis) -> list:
        """
        Rank solutions using simple priority-based ranking.

        Phase 1 implementation (no LLM yet):
        - Rank by priority field from ErrorEnhancer
        - Add basic relevance/confidence scores

        Future implementation will use LLM + Knowledge Base.

        Args:
            error_analysis: ErrorAnalysis from ErrorAnalysisEngine

        Returns:
            List of RankedSolution objects
        """
        ranked = []

        for i, solution in enumerate(error_analysis.solutions):
            # Simple ranking: inverse priority (priority 1 = most relevant)
            relevance_score = 1.0 - (solution.priority - 1) * 0.1
            relevance_score = max(0.3, min(1.0, relevance_score))

            # Fixed confidence for Phase 1
            confidence = 0.7

            ranked_solution = RankedSolution(
                solution=solution,
                relevance_score=relevance_score,
                reasoning=f"Solution ranked by priority {solution.priority}",
                confidence=confidence,
                effectiveness_score=0.0,  # No feedback yet
            )
            ranked.append(ranked_solution)

        # Sort by combined score
        ranked.sort(key=lambda s: s.combined_score, reverse=True)

        return ranked

    def _build_diagnosis_text(self, error_analysis) -> str:
        """
        Build diagnosis text from error analysis.

        Args:
            error_analysis: ErrorAnalysis

        Returns:
            Human-readable diagnosis text
        """
        diagnosis = f"Error {error_analysis.error_code} ({error_analysis.category}): {error_analysis.message}\n\n"

        if error_analysis.context:
            diagnosis += "Context:\n"
            for key, value in error_analysis.context.items():
                diagnosis += f"  - {key}: {value}\n"
            diagnosis += "\n"

        if error_analysis.causes:
            diagnosis += "Possible causes:\n"
            for i, cause in enumerate(error_analysis.causes[:3], 1):
                diagnosis += f"  {i}. {cause}\n"

        return diagnosis.strip()

    def _calculate_confidence_simple(self, ranked_solutions: list) -> float:
        """
        Calculate overall diagnosis confidence.

        Phase 1 implementation: Simple average of top solution confidence.

        Future implementation will use:
        - Top solution confidence: 60% weight
        - Score separation: 30% weight
        - Effectiveness: 10% weight

        Args:
            ranked_solutions: List of RankedSolution

        Returns:
            Overall confidence (0.0-1.0)
        """
        if not ranked_solutions:
            return 0.0

        # Simple average for Phase 1
        return ranked_solutions[0].confidence

    def _build_next_steps(self, ranked_solutions: list) -> list:
        """
        Build actionable next steps from top solution.

        Args:
            ranked_solutions: List of RankedSolution

        Returns:
            List of specific actions to take
        """
        if not ranked_solutions:
            return ["Review error message and context"]

        top_solution = ranked_solutions[0]

        next_steps = [
            f"1. {top_solution.solution.description}",
        ]

        if top_solution.solution.code_template:
            next_steps.append("2. Apply the following code:")
            next_steps.append(f"   {top_solution.solution.code_template}")

        if len(ranked_solutions) > 1:
            next_steps.append(
                f"3. If that doesn't work, try alternative solutions (ranked #{2}-{min(len(ranked_solutions), 3)})"
            )

        return next_steps
