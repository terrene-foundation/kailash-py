"""Debug Agent orchestrator for complete error analysis pipeline.

This module provides the DebugAgent that orchestrates all 5 Debug Agent stages:
Capture → Categorize → Analyze → Suggest → Format.
"""

import time
from typing import Optional

from dataflow.debug.context_analyzer import ContextAnalyzer
from dataflow.debug.debug_report import DebugReport
from dataflow.debug.error_capture import ErrorCapture
from dataflow.debug.error_categorizer import ErrorCategorizer
from dataflow.debug.knowledge_base import KnowledgeBase
from dataflow.debug.solution_generator import SolutionGenerator
from dataflow.platform.inspector import Inspector


class DebugAgent:
    """Orchestrates all Debug Agent pipeline stages.

    The DebugAgent provides a single entry point for the complete error
    analysis pipeline, coordinating all 5 stages:

    1. **Capture**: Extract error details (ErrorCapture)
    2. **Categorize**: Identify error pattern (ErrorCategorizer)
    3. **Analyze**: Extract workflow context (ContextAnalyzer)
    4. **Suggest**: Generate solutions (SolutionGenerator)
    5. **Format**: Create DebugReport (this class)

    Usage:
        kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
        inspector = Inspector(dataflow_instance)
        agent = DebugAgent(kb, inspector)

        # Debug an exception
        try:
            runtime.execute(workflow.build())
        except Exception as e:
            report = agent.debug(e)
            print(report.to_cli_format())

    Example:
        >>> agent = DebugAgent(knowledge_base, inspector)
        >>> report = agent.debug(exception)
        >>> print(f"Found {len(report.suggested_solutions)} solutions")
        Found 2 solutions
    """

    def __init__(
        self, knowledge_base: KnowledgeBase, inspector: Optional[Inspector] = None
    ):
        """Initialize DebugAgent with KnowledgeBase and Inspector.

        Args:
            knowledge_base: KnowledgeBase instance with patterns and solutions
            inspector: Optional Inspector for workflow introspection

        Example:
            >>> kb = KnowledgeBase("patterns.yaml", "solutions.yaml")
            >>> inspector = Inspector(db)
            >>> agent = DebugAgent(kb, inspector)
        """
        self.knowledge_base = knowledge_base
        self.inspector = inspector

        # Initialize pipeline components
        self.capture = ErrorCapture()
        self.categorizer = ErrorCategorizer(knowledge_base)
        self.analyzer = ContextAnalyzer(inspector) if inspector else None
        self.generator = SolutionGenerator(knowledge_base)

    def debug(
        self, exception: Exception, max_solutions: int = 5, min_relevance: float = 0.3
    ) -> DebugReport:
        """Run complete debug pipeline on exception.

        Orchestrates all 5 pipeline stages:
        1. Capture error details
        2. Categorize error pattern
        3. Analyze workflow context (if Inspector available)
        4. Generate ranked solutions
        5. Return DebugReport

        Args:
            exception: Exception to debug
            max_solutions: Maximum solutions to return (default: 5)
            min_relevance: Minimum relevance score 0.0-1.0 (default: 0.3)

        Returns:
            DebugReport with all pipeline results

        Example:
            >>> try:
            ...     runtime.execute(workflow.build())
            ... except Exception as e:
            ...     report = agent.debug(e)
            ...     print(report.to_cli_format())
        """
        start_time = time.time()

        try:
            # Stage 1: Capture error details
            captured = self.capture.capture(exception)

            # Stage 2: Categorize error pattern
            category = self.categorizer.categorize(captured)

            # Stage 3: Analyze workflow context
            if self.analyzer:
                analysis = self.analyzer.analyze(captured, category)
            else:
                # Fallback: Create basic AnalysisResult without Inspector
                from dataflow.debug.analysis_result import AnalysisResult

                analysis = AnalysisResult(
                    root_cause=captured.message,
                    affected_nodes=[],
                    affected_models=[],
                    context_data={},
                )

            # Stage 4: Generate solutions
            solutions = self.generator.generate_solutions(
                analysis,
                category,
                max_solutions=max_solutions,
                min_relevance=min_relevance,
            )

            # Stage 5: Create DebugReport
            execution_time = (time.time() - start_time) * 1000  # milliseconds
            report = DebugReport(
                captured_error=captured,
                error_category=category,
                analysis_result=analysis,
                suggested_solutions=solutions,
                execution_time=execution_time,
            )

            return report

        except Exception as e:
            # If pipeline fails, return minimal report
            return self._handle_pipeline_error(e, exception, start_time)

    def debug_from_string(
        self,
        error_message: str,
        error_type: str = "RuntimeError",
        max_solutions: int = 5,
        min_relevance: float = 0.3,
    ) -> DebugReport:
        """Run debug pipeline on error message string.

        Useful for debugging logged errors without exception objects.

        Args:
            error_message: Error message string
            error_type: Error type name (default: "RuntimeError")
            max_solutions: Maximum solutions to return (default: 5)
            min_relevance: Minimum relevance score 0.0-1.0 (default: 0.3)

        Returns:
            DebugReport with all pipeline results

        Example:
            >>> report = agent.debug_from_string(
            ...     "NOT NULL constraint failed: users.id",
            ...     error_type="DatabaseError"
            ... )
            >>> print(f"Category: {report.error_category.category}")
            Category: PARAMETER
        """
        # Create synthetic exception
        exception = Exception(error_message)

        # Run debug pipeline
        report = self.debug(
            exception, max_solutions=max_solutions, min_relevance=min_relevance
        )

        # Override error_type in captured error (can't set __class__.__name__ on Exception)
        report.captured_error.error_type = error_type

        return report

    def _handle_pipeline_error(
        self,
        pipeline_error: Exception,
        original_exception: Exception,
        start_time: float,
    ) -> DebugReport:
        """Handle errors that occur during pipeline execution.

        Creates a minimal DebugReport with the original error details
        and a note about the pipeline failure.

        Args:
            pipeline_error: Exception that occurred in pipeline
            original_exception: Original exception being debugged
            start_time: Pipeline start time (for execution tracking)

        Returns:
            Minimal DebugReport with error information

        Example:
            >>> report = agent._handle_pipeline_error(
            ...     ValueError("Pipeline failed"),
            ...     original_exception,
            ...     start_time
            ... )
            >>> report.error_category.category
            'UNKNOWN'
        """
        from dataflow.debug.analysis_result import AnalysisResult
        from dataflow.debug.error_capture import CapturedError
        from dataflow.debug.error_categorizer import ErrorCategory

        # Capture original error
        captured = self.capture.capture(original_exception)

        # Create UNKNOWN category
        category = ErrorCategory(
            category="UNKNOWN",
            pattern_id="UNKNOWN",
            confidence=0.0,
            features={"pipeline_error": str(pipeline_error)},
        )

        # Create basic analysis
        analysis = AnalysisResult(
            root_cause=f"Error during debug pipeline: {str(pipeline_error)}",
            affected_nodes=[],
            affected_models=[],
            context_data={"original_error": captured.message},
        )

        # No solutions for pipeline errors
        solutions = []

        execution_time = (time.time() - start_time) * 1000

        return DebugReport(
            captured_error=captured,
            error_category=category,
            analysis_result=analysis,
            suggested_solutions=solutions,
            execution_time=execution_time,
        )
