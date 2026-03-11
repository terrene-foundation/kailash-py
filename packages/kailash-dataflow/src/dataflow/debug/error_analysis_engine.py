"""
Error Analysis Engine for DataFlow AI Debug Agent.

Analyzes errors using ErrorEnhancer and extracts actionable insights.

Responsibilities:
- Extract error details from EnhancedDataFlowError
- Identify error category (parameter, connection, migration, etc.)
- Extract 3-5 possible causes from error catalog
- Extract 3-5 solutions from error catalog
- Provide context-aware error summary

Performance:
- No LLM calls (pure delegation to ErrorEnhancer)
- <1ms per error analysis
- No network requests
"""

from typing import TYPE_CHECKING

from dataflow.debug.data_structures import ErrorAnalysis, ErrorSolution
from dataflow.exceptions import EnhancedDataFlowError
from dataflow.exceptions import ErrorSolution as ExceptionErrorSolution

if TYPE_CHECKING:
    from dataflow.core.error_enhancer import DataFlowErrorEnhancer


class ErrorAnalysisEngine:
    """
    Analyzes errors using ErrorEnhancer.

    Responsibilities:
    - Extract error details from EnhancedDataFlowError
    - Identify error category (parameter, connection, migration, etc.)
    - Extract 3-5 possible causes from error catalog
    - Extract 3-5 solutions from error catalog
    - Provide context-aware error summary
    """

    def __init__(self, error_enhancer: "DataFlowErrorEnhancer"):
        """
        Initialize ErrorAnalysisEngine.

        Args:
            error_enhancer: ErrorEnhancer instance (60+ error types)
        """
        self.error_enhancer = error_enhancer

    def analyze_error(self, error: EnhancedDataFlowError) -> ErrorAnalysis:
        """
        Analyze error and extract insights.

        Args:
            error: Enhanced error from ErrorEnhancer

        Returns:
            ErrorAnalysis with:
            - error_code: DF-XXX code
            - category: parameter, connection, migration, runtime, etc.
            - message: Human-readable error message
            - context: Extracted context (node_id, parameter, etc.)
            - causes: 3-5 possible causes from catalog
            - solutions: 3-5 solutions from catalog
            - severity: error, warning
            - docs_url: Documentation link

        Performance:
        - No LLM calls
        - <1ms per analysis
        - Pure delegation to ErrorEnhancer
        """
        return ErrorAnalysis(
            error_code=error.error_code,
            category=self._extract_category(error.error_code),
            message=error.message,
            context=error.context,
            causes=error.causes,
            solutions=self._convert_solutions(error.solutions),
            severity=self._extract_severity(error),
            docs_url=error.docs_url,
        )

    def _extract_category(self, error_code: str) -> str:
        """
        Map error code to category.

        DF-1XX -> parameter
        DF-2XX -> connection
        DF-3XX -> migration
        DF-4XX -> configuration
        DF-5XX -> runtime
        DF-6XX -> model
        DF-7XX -> node
        DF-8XX -> workflow
        DF-9XX -> validation

        Args:
            error_code: DF-XXX error code

        Returns:
            Category name (parameter, connection, etc.)
        """
        # Extract first digit from XXX
        # Example: "DF-101" -> "1", "DF-201" -> "2"
        prefix = error_code.split("-")[1][:1]

        return {
            "1": "parameter",
            "2": "connection",
            "3": "migration",
            "4": "configuration",
            "5": "runtime",
            "6": "model",
            "7": "node",
            "8": "workflow",
            "9": "validation",
        }.get(prefix, "unknown")

    def _extract_severity(self, error: EnhancedDataFlowError) -> str:
        """
        Extract severity from error.

        Args:
            error: Enhanced error

        Returns:
            Severity level ("error" or "warning")
        """
        # Severity is not stored on the error object
        # All DataFlow errors default to "error" severity
        return "error"

    def _convert_solutions(self, solutions: list) -> list:
        """
        Convert raw solution dicts to ErrorSolution objects.

        Args:
            solutions: List of solution dicts from ErrorEnhancer

        Returns:
            List of ErrorSolution objects
        """
        result = []
        for sol in solutions:
            # If already an ErrorSolution object (from debug or exceptions), convert it
            if isinstance(sol, (ErrorSolution, ExceptionErrorSolution)):
                # Convert to our ErrorSolution format
                result.append(
                    ErrorSolution(
                        description=sol.description,
                        code_template=sol.code_template,
                        auto_fixable=sol.auto_fixable,
                        priority=sol.priority,
                    )
                )
            # If a dict, convert it
            elif isinstance(sol, dict):
                result.append(
                    ErrorSolution(
                        description=sol.get("description", ""),
                        code_template=sol.get("code_template", ""),
                        auto_fixable=sol.get("auto_fixable", False),
                        priority=sol.get("priority", 1),
                    )
                )
            else:
                # Unexpected type - skip it
                pass
        return result
