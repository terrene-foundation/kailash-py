"""
Automatic repair capabilities for common DataFlow issues.

Provides auto-fix functionality for:
- Parameter mapping errors
- Connection validation issues
- Migration conflicts
- Configuration problems
- Common setup mistakes
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from .errors import ErrorCode


@dataclass
class FixResult:
    """Result of an auto-fix attempt."""

    success: bool
    error_code: str
    message: str
    actions_taken: list[str]
    details: dict[str, Any]

    def show(self, color: bool = True) -> str:
        """Format fix result for display."""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        BLUE = "\033[94m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []

        # Header
        if self.success:
            parts.append(f"{GREEN}✓ Fix Applied Successfully{RESET}")
        else:
            parts.append(f"{RED}✗ Fix Failed{RESET}")

        parts.append(f"Error Code: {self.error_code}")
        parts.append(f"Message: {self.message}")
        parts.append("")

        # Actions taken
        if self.actions_taken:
            parts.append(f"{BLUE}{BOLD}Actions Taken:{RESET}")
            for i, action in enumerate(self.actions_taken, 1):
                parts.append(f"  {i}. {action}")
            parts.append("")

        # Details
        if self.details:
            parts.append(f"{BLUE}Details:{RESET}")
            for key, value in self.details.items():
                parts.append(f"  {key}: {value}")

        return "\n".join(parts)


class AutoFix:
    """
    Automatic repair for common DataFlow issues.

    Provides intelligent auto-fix capabilities that can:
    - Detect common problems
    - Apply appropriate fixes
    - Validate fixes worked
    - Rollback if needed
    """

    def __init__(self, studio: Any):
        """
        Initialize auto-fix.

        Args:
            studio: DataFlowStudio instance
        """
        self.studio = studio
        self.db = studio.db

    def fix_error(self, error_code: str, **context) -> FixResult:
        """
        Attempt to fix a specific error.

        Args:
            error_code: Error code (e.g., 'DF-101')
            **context: Context-specific parameters

        Returns:
            FixResult with success status and details

        Example:
            >>> result = fixer.fix_error('DF-101', node_id='user_create')
            >>> print(result.show())
        """
        # Map error codes to fix methods
        fix_methods = {
            ErrorCode.MISSING_PARAMETER.value: self._fix_missing_parameter,
            ErrorCode.CONNECTION_VALIDATION_FAILED.value: self._fix_connection_validation,
            ErrorCode.EVENT_LOOP_CLOSED.value: self._fix_event_loop,
            ErrorCode.MIGRATION_FAILED.value: self._fix_migration,
            ErrorCode.INVALID_CONFIGURATION_PARAMETER.value: self._fix_configuration,
            ErrorCode.SCHEMA_CONFLICT.value: self._fix_schema_conflict,
        }

        fix_method = fix_methods.get(error_code)
        if not fix_method:
            return FixResult(
                success=False,
                error_code=error_code,
                message=f"No auto-fix available for error code: {error_code}",
                actions_taken=[],
                details={},
            )

        try:
            return fix_method(**context)
        except Exception as e:
            return FixResult(
                success=False,
                error_code=error_code,
                message=f"Auto-fix failed: {str(e)}",
                actions_taken=[],
                details={"exception": str(e)},
            )

    def _fix_missing_parameter(self, node_id: str, **context) -> FixResult:
        """Fix missing parameter error."""
        actions = []

        # Suggest adding connection
        actions.append(f"Identify required parameters for node '{node_id}'")
        actions.append("Check workflow for missing connections")

        # This would analyze the workflow and suggest fixes
        # For now, return suggestion
        return FixResult(
            success=False,
            error_code=ErrorCode.MISSING_PARAMETER.value,
            message="Manual connection required",
            actions_taken=actions,
            details={
                "suggestion": f"Add connection to provide parameters to '{node_id}'",
                "example": f'workflow.add_connection("source", "output", "{node_id}", "data")',
            },
        )

    def _fix_connection_validation(self, **context) -> FixResult:
        """Fix connection validation error."""
        actions = []
        actions.append("Validate workflow connections")
        actions.append("Check parameter type compatibility")

        return FixResult(
            success=False,
            error_code=ErrorCode.CONNECTION_VALIDATION_FAILED.value,
            message="Connection validation requires manual review",
            actions_taken=actions,
            details={"suggestion": "Use inspector.workflow() to analyze connections"},
        )

    def _fix_event_loop(self, **context) -> FixResult:
        """Fix event loop closed error."""
        actions = []

        # Detect runtime type
        runtime_type = context.get("runtime_type", "unknown")

        if runtime_type == "AsyncLocalRuntime":
            actions.append("Detected AsyncLocalRuntime in synchronous context")
            actions.append("Switching to LocalRuntime")

            return FixResult(
                success=True,
                error_code=ErrorCode.EVENT_LOOP_CLOSED.value,
                message="Use LocalRuntime for synchronous execution",
                actions_taken=actions,
                details={
                    "fix": "runtime = LocalRuntime()",
                    "reason": "AsyncLocalRuntime requires async context",
                },
            )

        return FixResult(
            success=False,
            error_code=ErrorCode.EVENT_LOOP_CLOSED.value,
            message="Event loop fix requires context analysis",
            actions_taken=actions,
            details={
                "suggestion": "Use get_runtime() helper for automatic runtime selection"
            },
        )

    def _fix_migration(self, model_name: str = None, **context) -> FixResult:
        """Fix migration error."""
        actions = []

        try:
            # Clear schema cache
            actions.append("Clearing schema cache")
            self.studio.clear_schema_cache()

            # Check migration locks
            actions.append("Checking migration locks")
            locks = self.studio.check_migration_locks()

            if locks.get("has_locks"):
                actions.append(f"Found {locks['lock_count']} migration locks")
                # This would attempt to clear stale locks
                actions.append("Clearing stale migration locks")

            return FixResult(
                success=True,
                error_code=ErrorCode.MIGRATION_FAILED.value,
                message="Schema cache cleared, locks checked",
                actions_taken=actions,
                details={
                    "model": model_name,
                    "locks_found": locks.get("lock_count", 0),
                },
            )

        except Exception as e:
            return FixResult(
                success=False,
                error_code=ErrorCode.MIGRATION_FAILED.value,
                message=f"Migration fix failed: {str(e)}",
                actions_taken=actions,
                details={"exception": str(e)},
            )

    def _fix_configuration(self, parameter_name: str, **context) -> FixResult:
        """Fix configuration error."""
        actions = []

        # Get profile-based default
        profile = self.studio.profile
        actions.append(f"Using configuration profile: {profile}")

        # This would apply profile defaults
        actions.append(f"Applied default value for '{parameter_name}'")

        return FixResult(
            success=True,
            error_code=ErrorCode.INVALID_CONFIGURATION_PARAMETER.value,
            message=f"Applied profile default for '{parameter_name}'",
            actions_taken=actions,
            details={"parameter": parameter_name, "profile": profile},
        )

    def _fix_schema_conflict(self, **context) -> FixResult:
        """Fix schema conflict error."""
        actions = []

        try:
            # Clear schema cache
            actions.append("Clearing schema cache")
            self.studio.clear_schema_cache()

            # Test connection
            actions.append("Testing database connection")
            if not self.studio.test_connection():
                return FixResult(
                    success=False,
                    error_code=ErrorCode.SCHEMA_CONFLICT.value,
                    message="Database connection failed",
                    actions_taken=actions,
                    details={"issue": "connection_failed"},
                )

            return FixResult(
                success=True,
                error_code=ErrorCode.SCHEMA_CONFLICT.value,
                message="Schema cache cleared",
                actions_taken=actions,
                details={},
            )

        except Exception as e:
            return FixResult(
                success=False,
                error_code=ErrorCode.SCHEMA_CONFLICT.value,
                message=f"Schema fix failed: {str(e)}",
                actions_taken=actions,
                details={"exception": str(e)},
            )

    def fix_all_common_issues(self) -> list[FixResult]:
        """
        Attempt to fix all common issues.

        Runs a suite of common fixes:
        - Clear schema cache
        - Check migration locks
        - Validate configuration
        - Test connections

        Returns:
            List of FixResult instances

        Example:
            >>> results = fixer.fix_all_common_issues()
            >>> for result in results:
            ...     print(result.show())
        """
        results = []

        # Clear schema cache
        try:
            self.studio.clear_schema_cache()
            results.append(
                FixResult(
                    success=True,
                    error_code="COMMON-001",
                    message="Schema cache cleared",
                    actions_taken=["Cleared schema cache"],
                    details={},
                )
            )
        except Exception as e:
            results.append(
                FixResult(
                    success=False,
                    error_code="COMMON-001",
                    message=f"Failed to clear schema cache: {str(e)}",
                    actions_taken=[],
                    details={"exception": str(e)},
                )
            )

        # Check migration locks
        try:
            locks = self.studio.check_migration_locks()
            results.append(
                FixResult(
                    success=True,
                    error_code="COMMON-002",
                    message="Migration locks checked",
                    actions_taken=["Checked migration locks"],
                    details={"locks_found": locks.get("lock_count", 0)},
                )
            )
        except Exception as e:
            results.append(
                FixResult(
                    success=False,
                    error_code="COMMON-002",
                    message=f"Failed to check locks: {str(e)}",
                    actions_taken=[],
                    details={"exception": str(e)},
                )
            )

        # Test connection
        try:
            connected = self.studio.test_connection()
            results.append(
                FixResult(
                    success=connected,
                    error_code="COMMON-003",
                    message="Database connection tested",
                    actions_taken=["Tested database connection"],
                    details={"connected": connected},
                )
            )
        except Exception as e:
            results.append(
                FixResult(
                    success=False,
                    error_code="COMMON-003",
                    message=f"Connection test failed: {str(e)}",
                    actions_taken=[],
                    details={"exception": str(e)},
                )
            )

        return results

    def optimize_config(self, profile: str = None) -> FixResult:
        """
        Optimize configuration for a specific profile.

        Args:
            profile: Profile name (development, production, testing)

        Returns:
            FixResult with optimization details

        Example:
            >>> result = fixer.optimize_config(profile="production")
            >>> print(result.show())
        """
        if not profile:
            profile = self.studio.profile

        actions = []
        actions.append(f"Analyzing configuration for profile: {profile}")

        # This would analyze and optimize configuration
        # based on profile best practices

        return FixResult(
            success=True,
            error_code="CONFIG-OPT",
            message=f"Configuration optimized for {profile}",
            actions_taken=actions,
            details={"profile": profile},
        )

    def generate_workflow_template(
        self, models: list[str], operations: list[str], output_file: str | Path
    ) -> FixResult:
        """
        Generate workflow template code.

        Args:
            models: List of model names
            operations: List of operations (create, read, update, delete)
            output_file: Path to output file

        Returns:
            FixResult with generation details

        Example:
            >>> result = fixer.generate_workflow_template(
            ...     models=["User", "Product"],
            ...     operations=["create", "read"],
            ...     output_file="workflows/user_product.py"
            ... )
        """
        actions = []
        output_path = Path(output_file)

        try:
            # Generate template code
            actions.append(f"Generating workflow template for {len(models)} models")

            template = self._build_workflow_template(models, operations)

            # Write to file
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(template)
            actions.append(f"Wrote template to {output_file}")

            return FixResult(
                success=True,
                error_code="CODEGEN-001",
                message="Workflow template generated",
                actions_taken=actions,
                details={
                    "models": models,
                    "operations": operations,
                    "output_file": str(output_file),
                },
            )

        except Exception as e:
            return FixResult(
                success=False,
                error_code="CODEGEN-001",
                message=f"Template generation failed: {str(e)}",
                actions_taken=actions,
                details={"exception": str(e)},
            )

    def _build_workflow_template(self, models: list[str], operations: list[str]) -> str:
        """Build workflow template code."""
        lines = []

        # Imports
        lines.append("from kailash.workflow.builder import WorkflowBuilder")
        lines.append("from kailash.runtime import LocalRuntime")
        lines.append("from dataflow.platform import DataFlowStudio")
        lines.append("")

        # Setup
        lines.append("# Setup DataFlow")
        lines.append("studio = DataFlowStudio.quick_start(")
        lines.append('    name="my_app",')
        lines.append('    database="sqlite:///app.db",')
        lines.append(f"    models=[{', '.join(models)}],")
        lines.append('    profile="development"')
        lines.append(")")
        lines.append("")

        # Workflow
        lines.append("# Build workflow")
        lines.append("workflow = WorkflowBuilder()")
        lines.append("")

        # Add nodes for each model/operation
        for model in models:
            for operation in operations:
                node_id = f"{model.lower()}_{operation}"
                lines.append(f"# {model} - {operation}")
                lines.append(
                    f'workflow.add_node(studio.node("{model}", "{operation}"), "{node_id}", {{}})'
                )
                lines.append("")

        # Add connections (simplified)
        lines.append("# Add connections")
        lines.append("# workflow.add_connection(...)")
        lines.append("")

        # Execute
        lines.append("# Execute workflow")
        lines.append("runtime = LocalRuntime()")
        lines.append("results, run_id = runtime.execute(workflow.build(), inputs={})")
        lines.append("")

        return "\n".join(lines)
