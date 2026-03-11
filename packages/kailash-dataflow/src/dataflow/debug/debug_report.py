"""Debug report with complete pipeline results.

This module provides the DebugReport data structure that aggregates results
from all 5 Debug Agent pipeline stages into a single actionable report.
"""

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from dataflow.debug.analysis_result import AnalysisResult
from dataflow.debug.error_capture import CapturedError
from dataflow.debug.error_categorizer import ErrorCategory
from dataflow.debug.suggested_solution import SuggestedSolution


@dataclass
class DebugReport:
    """Complete debug report from all pipeline stages.

    The DebugReport aggregates results from all 5 Debug Agent stages:
    - Stage 1: Capture (CapturedError)
    - Stage 2: Categorize (ErrorCategory)
    - Stage 3: Analyze (AnalysisResult)
    - Stage 4: Suggest (List[SuggestedSolution])
    - Stage 5: Format (this report)

    Attributes:
        captured_error: Error details from ErrorCapture
        error_category: Category and pattern from ErrorCategorizer
        analysis_result: Root cause and context from ContextAnalyzer
        suggested_solutions: Ranked solutions from SolutionGenerator
        execution_time: Total pipeline execution time in milliseconds

    Example:
        >>> report = DebugReport(
        ...     captured_error=captured,
        ...     error_category=category,
        ...     analysis_result=analysis,
        ...     suggested_solutions=solutions,
        ...     execution_time=23.5
        ... )
        >>> print(report.to_cli_format())
        [Formatted CLI output with colors and structure]
    """

    captured_error: CapturedError
    error_category: ErrorCategory
    analysis_result: AnalysisResult
    suggested_solutions: List[SuggestedSolution] = field(default_factory=list)
    execution_time: float = 0.0  # milliseconds

    def to_dict(self) -> Dict[str, Any]:
        """Convert DebugReport to dictionary for serialization.

        Returns:
            Dictionary representation with all fields

        Example:
            >>> report = DebugReport(...)
            >>> data = report.to_dict()
            >>> data["error_category"]["category"]
            'PARAMETER'
            >>> data["execution_time"]
            23.5
        """
        return {
            "captured_error": self.captured_error.to_dict(),
            "error_category": {
                "category": self.error_category.category,
                "pattern_id": self.error_category.pattern_id,
                "confidence": self.error_category.confidence,
                "features": self.error_category.features,
            },
            "analysis_result": self.analysis_result.to_dict(),
            "suggested_solutions": [
                solution.to_dict() for solution in self.suggested_solutions
            ],
            "execution_time": self.execution_time,
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert DebugReport to JSON string.

        Args:
            indent: JSON indentation level (default: 2)

        Returns:
            JSON string representation

        Example:
            >>> report = DebugReport(...)
            >>> json_str = report.to_json()
            >>> print(json_str)
            {
              "captured_error": {...},
              "error_category": {...},
              ...
            }
        """
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DebugReport":
        """Create DebugReport from dictionary.

        Args:
            data: Dictionary with report data

        Returns:
            DebugReport instance

        Example:
            >>> data = report.to_dict()
            >>> restored = DebugReport.from_dict(data)
            >>> restored.error_category.category
            'PARAMETER'
        """
        from datetime import datetime

        from dataflow.debug.error_capture import StackFrame

        # Reconstruct CapturedError
        captured_error = CapturedError(
            exception=Exception(data["captured_error"]["message"]),
            error_type=data["captured_error"]["error_type"],
            message=data["captured_error"]["message"],
            stacktrace=[
                StackFrame(
                    filename=frame["filename"],
                    line_number=frame["line_number"],
                    function_name=frame["function_name"],
                    code_context=frame["code_context"],
                )
                for frame in data["captured_error"]["stacktrace"]
            ],
            context=data["captured_error"]["context"],
            timestamp=datetime.fromisoformat(data["captured_error"]["timestamp"]),
        )

        # Reconstruct ErrorCategory
        error_category = ErrorCategory(
            category=data["error_category"]["category"],
            pattern_id=data["error_category"]["pattern_id"],
            confidence=data["error_category"]["confidence"],
            features=data["error_category"]["features"],
        )

        # Reconstruct AnalysisResult
        analysis_result = AnalysisResult(
            root_cause=data["analysis_result"]["root_cause"],
            affected_nodes=data["analysis_result"]["affected_nodes"],
            affected_connections=data["analysis_result"]["affected_connections"],
            affected_models=data["analysis_result"]["affected_models"],
            context_data=data["analysis_result"]["context_data"],
            suggestions=data["analysis_result"]["suggestions"],
        )

        # Reconstruct SuggestedSolution list
        suggested_solutions = [
            SuggestedSolution(
                solution_id=sol["solution_id"],
                title=sol["title"],
                category=sol["category"],
                description=sol["description"],
                code_example=sol["code_example"],
                explanation=sol["explanation"],
                references=sol.get("references", []),
                difficulty=sol.get("difficulty", "medium"),
                estimated_time=sol.get("estimated_time", 5),
                relevance_score=sol.get("relevance_score", 0.0),
                confidence=sol.get("confidence", 0.0),
            )
            for sol in data["suggested_solutions"]
        ]

        return cls(
            captured_error=captured_error,
            error_category=error_category,
            analysis_result=analysis_result,
            suggested_solutions=suggested_solutions,
            execution_time=data.get("execution_time", 0.0),
        )

    def to_cli_format(self) -> str:
        """Format DebugReport for CLI display.

        Note: This is a simple text representation. Use CLIFormatter
        for rich terminal output with colors and box drawing.

        Returns:
            Formatted string for terminal display

        Example:
            >>> report = DebugReport(...)
            >>> print(report.to_cli_format())
            ERROR: PARAMETER (Confidence: 92%)
            Message: NOT NULL constraint failed: users.id
            Root Cause: Node 'create_user' is missing required parameter 'id'
            ...
        """
        lines = []

        # Header
        lines.append(
            f"ERROR: {self.error_category.category} (Confidence: {int(self.error_category.confidence * 100)}%)"
        )
        lines.append(f"Message: {self.captured_error.message}")
        lines.append("")

        # Root cause
        lines.append(f"Root Cause: {self.analysis_result.root_cause}")
        lines.append("")

        # Affected components
        if self.analysis_result.affected_nodes:
            lines.append(
                f"Affected Nodes: {', '.join(self.analysis_result.affected_nodes)}"
            )
        if self.analysis_result.affected_models:
            lines.append(
                f"Affected Models: {', '.join(self.analysis_result.affected_models)}"
            )
        lines.append("")

        # Solutions
        if self.suggested_solutions:
            lines.append(f"Suggested Solutions ({len(self.suggested_solutions)}):")
            for i, solution in enumerate(self.suggested_solutions, 1):
                lines.append(f"  [{i}] {solution.title} ({solution.category})")
                lines.append(
                    f"      Relevance: {int(solution.relevance_score * 100)}% | Difficulty: {solution.difficulty} | Time: {solution.estimated_time} min"
                )
        else:
            lines.append("No solutions found")

        lines.append("")
        lines.append(f"Execution Time: {self.execution_time:.1f}ms")

        return "\n".join(lines)

    def __repr__(self) -> str:
        """Debug representation of DebugReport.

        Returns:
            String representation with category, solutions count, and execution time

        Example:
            >>> report = DebugReport(...)
            >>> repr(report)
            "DebugReport(category='PARAMETER', solutions=2, time=23.5ms)"
        """
        return (
            f"DebugReport("
            f"category='{self.error_category.category}', "
            f"solutions={len(self.suggested_solutions)}, "
            f"time={self.execution_time:.1f}ms)"
        )
