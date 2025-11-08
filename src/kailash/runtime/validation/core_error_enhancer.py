"""
CoreErrorEnhancer: Error enhancement for Core SDK runtime errors.

Handles Core SDK runtime errors with KS-XXX error codes:
- Async runtime errors (event loop, thread pool)
- Workflow execution errors (validation, cycles)
- Connection errors (parameter validation)
- Node execution errors (timeout, resource exhaustion)

Usage:
    from kailash.runtime.validation import CoreErrorEnhancer

    enhancer = CoreErrorEnhancer()

    try:
        # Core SDK operation
        results, run_id = runtime.execute(workflow.build())
    except Exception as e:
        enhanced = enhancer.enhance_runtime_error(
            node_id="user_create",
            node_type="UserCreateNode",
            workflow_id="user_workflow",
            operation="execute",
            original_error=e
        )
        raise enhanced from e
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from kailash.runtime.validation.base_error_enhancer import (
    BaseErrorEnhancer,
    ErrorEnhancerConfig,
)


class EnhancedCoreError(Exception):
    """Enhanced Core SDK error with actionable solutions.

    Attributes:
        error_code: Error code (KS-XXX)
        message: Primary error message
        causes: Possible causes
        solutions: Actionable solutions
        docs_url: Documentation URL
        context: Error context dictionary
        original_error: Original exception
    """

    def __init__(
        self,
        error_code: str,
        message: str,
        causes: Optional[List[str]] = None,
        solutions: Optional[List[str]] = None,
        docs_url: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        original_error: Optional[Exception] = None,
    ):
        self.error_code = error_code
        self.message = message
        self.causes = causes or []
        self.solutions = solutions or []
        self.docs_url = docs_url
        self.context = context or {}
        self.original_error = original_error

        # Format complete error message
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        """Format complete error message with all details."""
        sections = []

        # Header with error code
        sections.append(f"🚨 Core SDK Error [{self.error_code}]: {self.message}")
        sections.append("=" * 70)

        # Context
        if self.context:
            sections.append("\n📋 Context:")
            for key, value in self.context.items():
                sections.append(f"    {key}: {value}")

        # Causes
        if self.causes:
            sections.append("\n🔍 Possible Causes:")
            for cause in self.causes:
                sections.append(f"    • {cause}")

        # Solutions
        if self.solutions:
            sections.append("\n💡 Solutions:")
            for i, solution in enumerate(self.solutions, 1):
                sections.append(f"    {i}. {solution}")

        # Documentation
        if self.docs_url:
            sections.append(f"\n📚 Documentation: {self.docs_url}")

        # Original error
        if self.original_error:
            sections.append(
                f"\n⚠️  Original error: {type(self.original_error).__name__}: {self.original_error}"
            )

        return "\n".join(sections)


class CoreErrorEnhancer(BaseErrorEnhancer):
    """Error enhancer for Core SDK runtime errors.

    Provides enhanced error messages for Core SDK operations:
    - Runtime execution errors (KS-501)
    - Async runtime errors (KS-502)
    - Workflow execution errors (KS-503)
    - Connection validation errors (KS-504)
    - Parameter errors (KS-505)
    - Node execution errors (KS-506)
    - Timeout errors (KS-507)
    - Resource exhaustion errors (KS-508)

    Error code prefix: "KS" (Kailash SDK)
    """

    BASE_DOCS_URL = "https://docs.kailash.ai/core/errors"

    def get_error_code_prefix(self) -> str:
        """Return Core SDK error code prefix."""
        return "KS"

    def get_catalog_path(self) -> Path:
        """Return path to Core SDK error catalog."""
        return Path(__file__).parent / "core_error_catalog.yaml"

    def enhance_runtime_error(
        self,
        node_id: Optional[str] = None,
        node_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
        operation: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedCoreError:
        """Enhance runtime execution errors.

        Args:
            node_id: Node identifier
            node_type: Node type name
            workflow_id: Workflow identifier
            operation: Operation being performed
            original_error: Original exception

        Returns:
            EnhancedCoreError with KS-501/502/503 error code
        """
        error_code = "KS-501"  # Runtime execution error by default

        # Detect specific error types
        if original_error:
            error_str = str(original_error).lower()
            if "event loop" in error_str or "asyncio" in error_str:
                error_code = "KS-502"  # Async runtime error
            elif "workflow" in error_str:
                error_code = "KS-503"  # Workflow execution failed

        # Build context
        context = {}
        if node_id:
            context["node_id"] = node_id
        if node_type:
            context["node_type"] = node_type
        if workflow_id:
            context["workflow_id"] = workflow_id
        if operation:
            context["operation"] = operation

        # Get error definition from catalog
        error_def = self._get_error_catalog().get(error_code, {})

        # Build message
        message = error_def.get("message", "Runtime execution failed")
        if node_id:
            message += f" in node '{node_id}'"

        # Get causes and solutions
        causes = error_def.get(
            "causes",
            [
                "Node execution raised an exception",
                "Invalid parameters provided to node",
                "Resource unavailable during execution",
            ],
        )

        solutions = error_def.get(
            "solutions",
            [
                "Check node parameters are valid",
                "Ensure required resources are available",
                "Review node implementation for errors",
                "Check logs for detailed error information",
            ],
        )

        docs_url = f"{self.BASE_DOCS_URL}/{error_code.lower()}"

        return EnhancedCoreError(
            error_code=error_code,
            message=message,
            causes=causes,
            solutions=solutions,
            docs_url=docs_url,
            context=context,
            original_error=original_error,
        )

    def enhance_connection_error(
        self,
        source_node: Optional[str] = None,
        target_node: Optional[str] = None,
        parameter_name: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedCoreError:
        """Enhance connection validation errors.

        Args:
            source_node: Source node identifier
            target_node: Target node identifier
            parameter_name: Parameter name
            original_error: Original exception

        Returns:
            EnhancedCoreError with KS-504 error code
        """
        error_code = "KS-504"

        # Build context
        context = {}
        if source_node:
            context["source_node"] = source_node
        if target_node:
            context["target_node"] = target_node
        if parameter_name:
            context["parameter_name"] = parameter_name

        # Get error definition
        error_def = self._get_error_catalog().get(error_code, {})

        # Build message
        message = "Connection validation failed"
        if source_node and target_node:
            message += f" between '{source_node}' and '{target_node}'"

        causes = error_def.get(
            "causes",
            [
                "Parameter type mismatch between connected nodes",
                "Missing required connection",
                "Invalid parameter name",
            ],
        )

        solutions = error_def.get(
            "solutions",
            [
                "Verify parameter types match between nodes",
                "Check connection parameter names are correct",
                "Ensure all required connections are defined",
                "Review workflow structure with Inspector.connections()",
            ],
        )

        docs_url = f"{self.BASE_DOCS_URL}/{error_code.lower()}"

        return EnhancedCoreError(
            error_code=error_code,
            message=message,
            causes=causes,
            solutions=solutions,
            docs_url=docs_url,
            context=context,
            original_error=original_error,
        )

    def enhance_parameter_error(
        self,
        node_id: Optional[str] = None,
        parameter_name: Optional[str] = None,
        expected_type: Optional[str] = None,
        actual_value: Optional[Any] = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedCoreError:
        """Enhance parameter validation errors.

        Args:
            node_id: Node identifier
            parameter_name: Parameter name
            expected_type: Expected parameter type
            actual_value: Actual value provided
            original_error: Original exception

        Returns:
            EnhancedCoreError with KS-505 error code
        """
        error_code = "KS-505"

        # Build context
        context = {}
        if node_id:
            context["node_id"] = node_id
        if parameter_name:
            context["parameter_name"] = parameter_name
        if expected_type:
            context["expected_type"] = expected_type
        if actual_value is not None:
            context["actual_type"] = type(actual_value).__name__

        # Get error definition
        error_def = self._get_error_catalog().get(error_code, {})

        # Build message
        message = "Parameter validation failed"
        if parameter_name:
            message += f" for parameter '{parameter_name}'"
        if node_id:
            message += f" in node '{node_id}'"

        causes = error_def.get(
            "causes",
            [
                "Invalid parameter type provided",
                "Missing required parameter",
                "Parameter value out of valid range",
            ],
        )

        solutions = error_def.get(
            "solutions",
            [
                "Check parameter type matches node requirements",
                "Ensure all required parameters are provided",
                "Verify parameter value is within valid range",
                "Review node documentation for parameter specifications",
            ],
        )

        docs_url = f"{self.BASE_DOCS_URL}/{error_code.lower()}"

        return EnhancedCoreError(
            error_code=error_code,
            message=message,
            causes=causes,
            solutions=solutions,
            docs_url=docs_url,
            context=context,
            original_error=original_error,
        )

    def enhance_timeout_error(
        self,
        node_id: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        operation: Optional[str] = None,
        original_error: Optional[Exception] = None,
    ) -> EnhancedCoreError:
        """Enhance timeout errors.

        Args:
            node_id: Node identifier
            timeout_seconds: Timeout duration
            operation: Operation that timed out
            original_error: Original exception

        Returns:
            EnhancedCoreError with KS-507 error code
        """
        error_code = "KS-507"

        # Build context
        context = {}
        if node_id:
            context["node_id"] = node_id
        if timeout_seconds:
            context["timeout_seconds"] = timeout_seconds
        if operation:
            context["operation"] = operation

        # Get error definition
        error_def = self._get_error_catalog().get(error_code, {})

        message = "Operation timed out"
        if operation:
            message += f" during {operation}"
        if timeout_seconds:
            message += f" after {timeout_seconds}s"

        causes = error_def.get(
            "causes",
            [
                "Operation took longer than configured timeout",
                "External service not responding",
                "Resource contention or blocking",
            ],
        )

        solutions = error_def.get(
            "solutions",
            [
                "Increase timeout duration if operation legitimately takes longer",
                "Check external service availability and response times",
                "Review node implementation for blocking operations",
                "Consider using async operations for long-running tasks",
            ],
        )

        docs_url = f"{self.BASE_DOCS_URL}/{error_code.lower()}"

        return EnhancedCoreError(
            error_code=error_code,
            message=message,
            causes=causes,
            solutions=solutions,
            docs_url=docs_url,
            context=context,
            original_error=original_error,
        )
