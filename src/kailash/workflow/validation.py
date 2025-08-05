"""
Comprehensive Validation and Linting for Cyclic Workflows.

This module provides extensive validation and linting capabilities to identify
common issues, performance anti-patterns, security vulnerabilities, and potential
problems in cyclic workflows before execution. It acts as a quality gate to
ensure workflow reliability and optimal performance.

Design Philosophy:
    Provides proactive quality assurance through comprehensive static analysis
    of workflow structures, configurations, and patterns. Identifies issues
    early in the development cycle with specific, actionable recommendations
    for resolution and optimization.

Key Features:
    - Multi-category validation (safety, performance, compatibility)
    - Severity-based issue classification (error, warning, info)
    - Specific error codes with documentation links
    - Actionable suggestions for issue resolution
    - Comprehensive reporting with categorization
    - Integration with development workflows

Validation Categories:
    - Convergence: Cycle termination and convergence conditions
    - Safety: Resource limits and infinite loop prevention
    - Performance: Anti-patterns and optimization opportunities
    - Parameter Mapping: Cycle parameter flow validation
    - Node Compatibility: Cycle-aware node validation
    - Resource Usage: Memory and file handle management

Issue Severity Levels:
    - ERROR: Critical issues that prevent execution or cause failures
    - WARNING: Potential issues that may impact performance or reliability
    - INFO: Suggestions for improvement and best practices

Core Components:
    - ValidationIssue: Structured issue representation with metadata
    - IssueSeverity: Enumeration of severity levels
    - CycleLinter: Main validation engine with comprehensive checks
    - Reporting system with categorization and filtering

Validation Algorithms:
    - Static analysis of cycle configurations
    - Pattern recognition for common anti-patterns
    - Resource usage analysis and leak detection
    - Security validation for parameter access
    - Performance bottleneck identification

Upstream Dependencies:
    - Workflow graph structure and cycle detection
    - Node implementations and configuration validation
    - Cycle configuration and safety systems

Downstream Consumers:
    - Development tools and IDEs for real-time validation
    - CI/CD pipelines for automated quality gates
    - Performance optimization tools
    - Security analysis and compliance systems
    - Educational and training materials

Examples:
    Basic workflow validation:

    >>> from kailash.workflow.validation import CycleLinter, IssueSeverity
    >>> linter = CycleLinter(workflow)
    >>> issues = linter.check_all()
    >>> # Filter by severity
    >>> errors = linter.get_issues_by_severity(IssueSeverity.ERROR)
    >>> warnings = linter.get_issues_by_severity(IssueSeverity.WARNING)
    >>> for error in errors:
    ...     print(f"ERROR {error.code}: {error.message}")
    ...     if error.suggestion:
    ...         print(f"  Suggestion: {error.suggestion}")

    Comprehensive reporting:

    >>> report = linter.generate_report()
    >>> print(f"Total issues: {report['summary']['total_issues']}")
    >>> print(f"Critical errors: {report['summary']['errors']}")
    >>> print(f"Affected cycles: {report['summary']['affected_cycles']}")
    >>> # Category-specific analysis
    >>> for category, issues in report['by_category'].items():
    ...     print(f"{category.upper()} ({len(issues)} issues):")
    ...     for issue in issues:
    ...         print(f"  {issue.code}: {issue.message}")

    Targeted validation:

    >>> # Validate specific cycle
    >>> cycle_issues = linter.get_issues_for_cycle("optimization_cycle")
    >>> # Validate specific node
    >>> node_issues = linter.get_issues_for_node("processor")
    >>> # Get recommendations
    >>> recommendations = report['recommendations']
    >>> for rec in recommendations:
    ...     print(f"  {rec}")

Validation Checks:
    The linter performs comprehensive checks including:

    - **CYC001-002**: Convergence condition validation
    - **CYC003-004**: Infinite loop prevention
    - **CYC005-006**: Safety limit configuration
    - **CYC007-009**: Performance anti-pattern detection
    - **CYC010-011**: Parameter mapping validation
    - **CYC012-013**: Node compatibility checks
    - **CYC014-015**: Convergence condition syntax validation
    - **CYC016-017**: Resource usage and leak detection

See Also:
    - :mod:`kailash.workflow.migration` for workflow optimization
    - :mod:`kailash.workflow.safety` for safety mechanisms
    - :doc:`/guides/validation` for validation best practices
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

# Note: Workflow import moved to individual methods to avoid circular imports
if TYPE_CHECKING:
    from kailash.workflow.graph import Workflow


class IssueSeverity(Enum):
    """Severity levels for validation issues."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Represents a validation issue found in a workflow."""

    severity: IssueSeverity
    category: str
    code: str
    message: str
    node_id: str | None = None
    cycle_id: str | None = None
    suggestion: str | None = None
    documentation_link: str | None = None


class ParameterDeclarationValidator:
    """Validator for node parameter declarations - detects silent parameter dropping issues.

    This validator addresses the critical issue where nodes with empty get_parameters()
    methods silently receive no workflow parameters, leading to debugging issues.

    Key validations:
    1. Empty parameter declarations (PAR001 - WARNING at build time, enforced at runtime)
    2. Undeclared parameter access attempts (PAR002 - WARNING)
    3. Parameter type validation issues (PAR003 - WARNING)
    4. Missing required parameters in workflow (PAR004 - WARNING at build time, ERROR at runtime)

    Usage:
        validator = ParameterDeclarationValidator()
        issues = validator.validate_node_parameters(node_instance, workflow_params)
    """

    validation_code = "PAR"

    def validate_node_parameters(
        self, node_instance, workflow_parameters: dict[str, Any]
    ) -> list[ValidationIssue]:
        """Check parameter declarations against workflow usage.

        Args:
            node_instance: Node instance to validate
            workflow_parameters: Parameters provided by workflow

        Returns:
            List of ValidationIssue objects for any problems found
        """
        issues = []

        try:
            declared_params = node_instance.get_parameters()
        except Exception as e:
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.ERROR,
                    category="parameter_declaration",
                    code="PAR000",
                    message=f"Node {node_instance.__class__.__name__} get_parameters() failed: {e}",
                    suggestion="Fix get_parameters() method implementation",
                    documentation_link="sdk-users/7-gold-standards/enterprise-parameter-passing-gold-standard.md",
                )
            )
            return issues

        # Critical: Empty parameter declarations (addresses gold standard issue #2)
        # For backwards compatibility, downgrade to WARNING at build time
        if not declared_params and workflow_parameters:
            workflow_param_names = list(workflow_parameters.keys())
            issues.append(
                ValidationIssue(
                    severity=IssueSeverity.WARNING,
                    category="parameter_declaration",
                    code="PAR001",
                    message=f"Node {node_instance.__class__.__name__} declares no parameters but workflow provides {workflow_param_names}",
                    suggestion="Add parameters to get_parameters() method - SDK only injects explicitly declared parameters",
                    documentation_link="sdk-users/7-gold-standards/enterprise-parameter-passing-gold-standard.md#parameter-declaration-security",
                )
            )

        # Security: Undeclared parameter access attempts (WITH auto_map_from support)
        if declared_params and workflow_parameters:
            # Build complete set of valid parameter names including auto_map_from
            valid_param_names = set(declared_params.keys())

            # Add all auto_map_from alternatives to valid set
            for param_name, param_def in declared_params.items():
                if hasattr(param_def, "auto_map_from") and param_def.auto_map_from:
                    valid_param_names.update(param_def.auto_map_from)

            # Check against expanded valid parameter set
            undeclared = set(workflow_parameters.keys()) - valid_param_names
            if undeclared:
                issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.WARNING,
                        category="parameter_declaration",
                        code="PAR002",
                        message=f"Workflow parameters {list(undeclared)} not declared in get_parameters() - will be ignored by SDK",
                        suggestion="Add missing parameters to get_parameters() or remove from workflow configuration",
                    )
                )

        # Validation: Parameter type issues
        if declared_params:
            for param_name, param_def in declared_params.items():
                if not hasattr(param_def, "type") or param_def.type is None:
                    issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.WARNING,
                            category="parameter_declaration",
                            code="PAR003",
                            message=f"Parameter '{param_name}' missing type definition",
                            suggestion=f"Add type field to NodeParameter: NodeParameter(name='{param_name}', type=str, ...)",
                        )
                    )

                # Check for required parameters without defaults
                if (
                    getattr(param_def, "required", False)
                    and param_name not in workflow_parameters
                ):
                    if getattr(param_def, "default", None) is None:
                        # For backwards compatibility, missing required parameters are WARNING at build time
                        # They'll still cause runtime errors when the node executes
                        issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="parameter_declaration",
                                code="PAR004",
                                message=f"Required parameter '{param_name}' not provided by workflow and has no default",
                                suggestion=f"Either provide '{param_name}' in workflow configuration or add default value",
                            )
                        )

        return issues

    def validate_workflow_node_parameters(self, workflow) -> list[ValidationIssue]:
        """Validate parameter declarations for all nodes in a workflow.

        Args:
            workflow: Workflow instance to validate

        Returns:
            List of all parameter declaration issues across the workflow
        """
        all_issues = []

        # This would need workflow.nodes to be iterable with node instances
        # For now, we'll focus on the single-node validation method
        # Implementation would depend on workflow structure

        return all_issues


class CycleLinter:
    """
    Comprehensive linter for cyclic workflows.

    Analyzes workflows for common issues, performance anti-patterns,
    and potential problems specific to cyclic execution.
    """

    def __init__(self, workflow: "Workflow"):
        """
        Initialize linter with target workflow.

        Args:
            workflow: The workflow to analyze
        """
        self.workflow = workflow
        self.graph = workflow.graph
        self.issues: list[ValidationIssue] = []

    def check_all(self) -> list[ValidationIssue]:
        """
        Run all validation checks on the workflow.

        Returns:
            List of all validation issues found

        Example:
            >>> workflow = create_problematic_workflow()
            >>> linter = CycleLinter(workflow)
            >>> issues = linter.check_all()
            >>> for issue in issues:
            ...     print(f"{issue.severity.value}: {issue.message}")
        """
        self.issues = []

        # Run all checks
        self._check_cycles_have_convergence()
        self._check_for_infinite_loop_potential()
        self._check_safety_limits()
        self._check_performance_anti_patterns()
        self._check_parameter_mapping()
        self._check_node_compatibility()
        self._check_convergence_conditions()
        self._check_resource_usage()

        return self.issues

    def _check_cycles_have_convergence(self):
        """Check that all cycles have appropriate convergence conditions."""
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                for source, target, edge_data in cycle_edges:
                    if not edge_data.get("convergence_check") and not edge_data.get(
                        "max_iterations"
                    ):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.ERROR,
                                category="convergence",
                                code="CYC001",
                                message=f"Cycle {cycle_id} lacks convergence condition and max_iterations",
                                cycle_id=cycle_id,
                                suggestion="Add convergence_check parameter or set max_iterations",
                                documentation_link="guide/reference/cheatsheet/019-cyclic-workflows-basics.md",
                            )
                        )

                    elif not edge_data.get("convergence_check"):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="convergence",
                                code="CYC002",
                                message=f"Cycle {cycle_id} relies only on max_iterations without convergence check",
                                cycle_id=cycle_id,
                                suggestion="Consider adding convergence_check for early termination",
                                documentation_link="guide/reference/cheatsheet/019-cyclic-workflows-basics.md",
                            )
                        )

    def _check_for_infinite_loop_potential(self):
        """Check for patterns that could lead to infinite loops."""
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                for source, target, edge_data in cycle_edges:
                    max_iter = edge_data.get("max_iterations")
                    convergence = edge_data.get("convergence_check")

                    # Check for very high or missing max_iterations
                    if max_iter is None or max_iter > 10000:
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="safety",
                                code="CYC003",
                                message=f"Cycle {cycle_id} has very high or no max_iterations limit",
                                cycle_id=cycle_id,
                                suggestion="Set reasonable max_iterations (e.g., 100-1000) as safety limit",
                                documentation_link="guide/mistakes/066-infinite-cycles.md",
                            )
                        )

                    # Check for potentially unreachable convergence conditions
                    if convergence:
                        if self._is_potentially_unreachable_condition(convergence):
                            self.issues.append(
                                ValidationIssue(
                                    severity=IssueSeverity.WARNING,
                                    category="convergence",
                                    code="CYC004",
                                    message=f"Convergence condition '{convergence}' may be unreachable",
                                    cycle_id=cycle_id,
                                    suggestion="Verify convergence condition is achievable",
                                    documentation_link="guide/mistakes/066-infinite-cycles.md",
                                )
                            )

    def _check_safety_limits(self):
        """Check for appropriate safety limits on cycles."""
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                for source, target, edge_data in cycle_edges:
                    # Check timeout
                    if not edge_data.get("timeout"):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.INFO,
                                category="safety",
                                code="CYC005",
                                message=f"Cycle {cycle_id} has no timeout limit",
                                cycle_id=cycle_id,
                                suggestion="Consider adding timeout parameter for safety",
                                documentation_link="guide/reference/cheatsheet/019-cyclic-workflows-basics.md",
                            )
                        )

                    # Check memory limit
                    if not edge_data.get("memory_limit"):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.INFO,
                                category="safety",
                                code="CYC006",
                                message=f"Cycle {cycle_id} has no memory limit",
                                cycle_id=cycle_id,
                                suggestion="Consider adding memory_limit parameter for safety",
                                documentation_link="guide/reference/cheatsheet/019-cyclic-workflows-basics.md",
                            )
                        )

    def _check_performance_anti_patterns(self):
        """Check for performance anti-patterns."""
        # Use the workflow's cycle detection
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                # Get unique nodes in the cycle
                cycle_nodes = set()
                for source, target, _ in cycle_edges:
                    cycle_nodes.add(source)
                    cycle_nodes.add(target)
                cycle_nodes = list(cycle_nodes)

                # Check for very small cycles (may have high overhead)
                if len(cycle_nodes) == 1:
                    node_id = cycle_nodes[0]
                    self.issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.INFO,
                            category="performance",
                            code="CYC007",
                            message=f"Single-node cycle {cycle_id} may have high overhead",
                            node_id=node_id,
                            cycle_id=cycle_id,
                            suggestion="Consider if cycle is necessary or if logic can be internal to node",
                            documentation_link="guide/reference/pattern-library/06-performance-patterns.md",
                        )
                    )

                # Check for very large cycles (may be hard to debug)
                elif len(cycle_nodes) > 10:
                    self.issues.append(
                        ValidationIssue(
                            severity=IssueSeverity.WARNING,
                            category="complexity",
                            code="CYC008",
                            message=f"Large cycle {cycle_id} with {len(cycle_nodes)} nodes may be hard to debug",
                            cycle_id=cycle_id,
                            suggestion="Consider breaking into smaller cycles or using nested workflows",
                            documentation_link="guide/reference/pattern-library/04-complex-patterns.md",
                        )
                    )

                # Check for cycles with expensive operations
                for node_id in cycle_nodes:
                    if self._is_expensive_operation(node_id):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="performance",
                                code="CYC009",
                                message=f"Expensive operation '{node_id}' in cycle {cycle_id}",
                                node_id=node_id,
                                cycle_id=cycle_id,
                                suggestion="Consider caching, optimization, or moving outside cycle",
                                documentation_link="guide/reference/pattern-library/06-performance-patterns.md",
                            )
                        )

    def _check_parameter_mapping(self):
        """Check for parameter mapping issues in cycles."""
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                # Get cycle nodes for checking
                cycle_nodes = set()
                for s, t, _ in cycle_edges:
                    cycle_nodes.add(s)
                    cycle_nodes.add(t)

                # Check each edge for issues
                for source, target, edge_data in cycle_edges:
                    mapping = edge_data.get("mapping", {})

                    # Check for identity mappings (common mistake)
                    for source_param, target_param in mapping.items():
                        if source_param == target_param:
                            self.issues.append(
                                ValidationIssue(
                                    severity=IssueSeverity.WARNING,
                                    category="parameter_mapping",
                                    code="CYC010",
                                    message=f"Identity mapping '{source_param}' -> '{target_param}' in cycle {cycle_id}",
                                    cycle_id=cycle_id,
                                    suggestion="Use 'result.field' -> 'field' pattern for cycle parameter propagation",
                                    documentation_link="guide/mistakes/063-cyclic-parameter-propagation-multi-fix.md",
                                )
                            )

                        # Check for potentially problematic mappings
                        if source_param in [
                            "result",
                            "output",
                            "data",
                        ] and target_param in ["result", "output", "data"]:
                            if source_param != target_param:
                                self.issues.append(
                                    ValidationIssue(
                                        severity=IssueSeverity.INFO,
                                        category="parameter_mapping",
                                        code="CYC010A",
                                        message=f"Generic parameter mapping '{source_param}' -> '{target_param}' in cycle {cycle_id}",
                                        cycle_id=cycle_id,
                                        suggestion="Consider using more specific parameter names for clarity",
                                        documentation_link="guide/mistakes/063-cyclic-parameter-propagation-multi-fix.md",
                                    )
                                )

                        # Check for dot notation in mappings
                        if (
                            "." in source_param
                            and target_param == source_param.split(".")[-1]
                        ):
                            # This is actually a good pattern - dot notation to specific field
                            pass
                        elif "." not in source_param and "." not in target_param:
                            # Simple mapping - check if it makes sense
                            if source_param.startswith(
                                "temp_"
                            ) or target_param.startswith("temp_"):
                                self.issues.append(
                                    ValidationIssue(
                                        severity=IssueSeverity.INFO,
                                        category="parameter_mapping",
                                        code="CYC010B",
                                        message=f"Temporary parameter mapping '{source_param}' -> '{target_param}' in cycle {cycle_id}",
                                        cycle_id=cycle_id,
                                        suggestion="Consider using permanent parameter names for production workflows",
                                        documentation_link="guide/mistakes/063-cyclic-parameter-propagation-multi-fix.md",
                                    )
                                )

                    # Check for missing parameter propagation
                    if not mapping and len(cycle_nodes) > 1:
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.INFO,
                                category="parameter_mapping",
                                code="CYC011",
                                message=f"Cycle {cycle_id} has no parameter mapping",
                                cycle_id=cycle_id,
                                suggestion="Consider if parameters need to propagate between iterations",
                                documentation_link="guide/reference/cheatsheet/019-cyclic-workflows-basics.md",
                            )
                        )

    def _check_node_compatibility(self):
        """Check for node compatibility issues with cycles."""
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                # Get unique nodes in the cycle
                cycle_nodes = set()
                for source, target, _ in cycle_edges:
                    cycle_nodes.add(source)
                    cycle_nodes.add(target)

                for node_id in cycle_nodes:
                    node = self.workflow.nodes.get(node_id)
                    if not node:
                        continue

                # Check if node supports cycle context
                if hasattr(node, "run"):
                    # Check if node accesses cycle context safely
                    if self._uses_unsafe_cycle_access(node):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.ERROR,
                                category="node_compatibility",
                                code="CYC012",
                                message=f"Node '{node_id}' uses unsafe cycle context access",
                                node_id=node_id,
                                cycle_id=cycle_id,
                                suggestion="Use context.get('cycle', {}) instead of direct access",
                                documentation_link="guide/reference/cheatsheet/022-cycle-debugging-troubleshooting.md",
                            )
                        )

                # Check for PythonCodeNode parameter access
                if hasattr(node, "code") and node.code:
                    if self._has_unsafe_parameter_access(node.code):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="node_compatibility",
                                code="CYC013",
                                message=f"PythonCodeNode '{node_id}' may have unsafe parameter access",
                                node_id=node_id,
                                cycle_id=cycle_id,
                                suggestion="Use try/except pattern for cycle parameter access",
                                documentation_link="guide/mistakes/064-pythoncodenode-none-input-validation-error.md",
                            )
                        )

    def _check_convergence_conditions(self):
        """Check convergence conditions for validity."""
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                for source, target, edge_data in cycle_edges:
                    convergence = edge_data.get("convergence_check")

                    if convergence:
                        # Check for valid Python syntax
                        if not self._is_valid_condition_syntax(convergence):
                            self.issues.append(
                                ValidationIssue(
                                    severity=IssueSeverity.ERROR,
                                    category="convergence",
                                    code="CYC014",
                                    message=f"Invalid convergence condition syntax: '{convergence}'",
                                    cycle_id=cycle_id,
                                    suggestion="Ensure condition is valid Python expression",
                                    documentation_link="guide/reference/cheatsheet/019-cyclic-workflows-basics.md",
                                )
                            )

                        # Check for common mistakes
                        if self._has_convergence_condition_issues(convergence):
                            self.issues.append(
                                ValidationIssue(
                                    severity=IssueSeverity.WARNING,
                                    category="convergence",
                                    code="CYC015",
                                    message=f"Potential issue in convergence condition: '{convergence}'",
                                    cycle_id=cycle_id,
                                    suggestion="Verify field names and comparison operators",
                                    documentation_link="guide/mistakes/066-infinite-cycles.md",
                                )
                            )

    def _check_resource_usage(self):
        """Check for potential resource usage issues."""
        if hasattr(self.workflow, "get_cycle_groups"):
            cycle_groups = self.workflow.get_cycle_groups()

            for cycle_id, cycle_edges in cycle_groups.items():
                # Get unique nodes in the cycle
                cycle_nodes = set()
                for source, target, _ in cycle_edges:
                    cycle_nodes.add(source)
                    cycle_nodes.add(target)

                # Check for potential memory leaks
                for node_id in cycle_nodes:
                    if self._may_have_memory_leak(node_id):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="resource_usage",
                                code="CYC016",
                                message=f"Node '{node_id}' may have memory leak in cycle",
                                node_id=node_id,
                                cycle_id=cycle_id,
                                suggestion="Ensure proper cleanup of resources in cyclic execution",
                                documentation_link="guide/mistakes/016-memory-leaks-in-long-running-processes.md",
                            )
                        )

                # Check for file handle management
                for node_id in cycle_nodes:
                    if self._may_leak_file_handles(node_id):
                        self.issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="resource_usage",
                                code="CYC017",
                                message=f"Node '{node_id}' may leak file handles in cycle",
                                node_id=node_id,
                                cycle_id=cycle_id,
                                suggestion="Use context managers (with statements) for file operations",
                                documentation_link="guide/mistakes/022-resource-cleanup-issues.md",
                            )
                        )

    def _get_cycle_id(self, cycle_nodes: list[str]) -> str:
        """Generate a cycle identifier from cycle nodes."""
        return f"cycle_{'-'.join(sorted(cycle_nodes))}"

    def _is_potentially_unreachable_condition(self, condition: str) -> bool:
        """Check if convergence condition might be unreachable."""
        # Simple heuristics for potentially problematic conditions
        problematic_patterns = [
            r".*==\s*True\s*$",  # exact boolean match
            r".*==\s*1\.0\s*$",  # exact float match
            r".*>\s*1\.0\s*$",  # probability > 1.0
            r".*<\s*0\.0\s*$",  # probability < 0.0
        ]

        for pattern in problematic_patterns:
            if re.search(pattern, condition):
                return True

        return False

    def _is_expensive_operation(self, node_id: str) -> bool:
        """Check if node represents an expensive operation."""
        expensive_keywords = [
            "train",
            "model",
            "neural",
            "deep",
            "learning",
            "api",
            "request",
            "http",
            "download",
            "upload",
            "database",
            "query",
            "sql",
            "file",
            "io",
            "read",
            "write",
        ]

        node_id_lower = node_id.lower()
        return any(keyword in node_id_lower for keyword in expensive_keywords)

    def _uses_unsafe_cycle_access(self, node) -> bool:
        """Check if node uses unsafe cycle context access."""
        # This would require more sophisticated code analysis
        # For now, return False as a placeholder
        return False

    def _has_unsafe_parameter_access(self, code: str) -> bool:
        """Check if PythonCodeNode has unsafe parameter access."""
        import re

        # Look for direct parameter access without try/except or safety checks
        lines = code.split("\n")

        # Common parameter names that might be unsafe
        unsafe_patterns = [
            r"\b(data|input|params|context|kwargs|args)\[",  # Direct indexing
            r"\b(data|input|params|context|kwargs|args)\.",  # Direct attribute access
            r"\b(data|input|params|context|kwargs|args)\.get\(",  # .get() without default
        ]

        # Safety patterns that indicate safe access
        safety_patterns = [
            r"try\s*:",
            r"except\s*:",
            r"if\s+.*\s+is\s+not\s+None\s*:",
            r"if\s+.*\s+in\s+",
            r"\.get\(.*,.*\)",  # .get() with default value
            r"isinstance\s*\(",
            r"hasattr\s*\(",
        ]

        has_unsafe_access = False
        has_safety_checks = False

        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                # Check for unsafe patterns
                for pattern in unsafe_patterns:
                    if re.search(pattern, line):
                        has_unsafe_access = True
                        break

                # Check for safety patterns
                for pattern in safety_patterns:
                    if re.search(pattern, line):
                        has_safety_checks = True
                        break

        # Also check for undefined variables (potential parameters)
        undefined_vars = self._find_undefined_variables(code)
        if undefined_vars:
            has_unsafe_access = True

        return has_unsafe_access and not has_safety_checks

    def _is_defined_before_use(self, var_name: str, code: str) -> bool:
        """Check if variable is defined before use in code."""
        lines = code.split("\n")
        defined = False

        for line in lines:
            line = line.strip()
            if line.startswith(f"{var_name} =") or line.startswith(f"{var_name}="):
                defined = True
            elif var_name in line and not defined:
                # Used before definition
                return False

        return True

    def _find_undefined_variables(self, code: str) -> list[str]:
        """Find variables that are used but not defined in the code."""
        import re

        lines = code.split("\n")
        defined_vars = set()
        used_vars = set()

        # Built-in variables and functions that don't need definition
        builtin_vars = {
            "len",
            "sum",
            "min",
            "max",
            "dict",
            "list",
            "set",
            "str",
            "int",
            "float",
            "bool",
            "sorted",
            "print",
            "isinstance",
            "type",
            "hasattr",
            "getattr",
            "True",
            "False",
            "None",
            "range",
            "enumerate",
            "zip",
            "any",
            "all",
        }

        for line in lines:
            line = line.strip()
            if line and not line.startswith("#"):
                # Find variable definitions
                if (
                    "=" in line
                    and not line.startswith("if")
                    and not line.startswith("elif")
                ):
                    var_match = re.match(r"^([a-zA-Z_]\w*)\s*=", line)
                    if var_match:
                        defined_vars.add(var_match.group(1))

                # Find variable uses
                variables = re.findall(r"\b([a-zA-Z_]\w*)\b", line)
                for var in variables:
                    if var not in builtin_vars and not var.startswith("_"):
                        used_vars.add(var)

        # Return variables that are used but not defined
        undefined = used_vars - defined_vars
        return list(undefined)

    def _is_valid_condition_syntax(self, condition: str) -> bool:
        """Check if convergence condition has valid Python syntax."""
        try:
            compile(condition, "<string>", "eval")
            return True
        except SyntaxError:
            return False

    def _has_convergence_condition_issues(self, condition: str) -> bool:
        """Check for common issues in convergence conditions."""
        # Check for undefined variables (common field names)
        undefined_vars = [
            "done",
            "converged",
            "finished",
            "complete",
            "quality",
            "error",
        ]

        for var in undefined_vars:
            if var in condition:
                # Might be using undefined variable
                return True

        return False

    def _may_have_memory_leak(self, node_id: str) -> bool:
        """Check if node might have memory leaks."""
        leak_keywords = ["accumulate", "collect", "gather", "cache", "store"]
        node_id_lower = node_id.lower()
        return any(keyword in node_id_lower for keyword in leak_keywords)

    def _may_leak_file_handles(self, node_id: str) -> bool:
        """Check if node might leak file handles."""
        file_keywords = ["file", "read", "write", "open", "csv", "json", "log"]
        node_id_lower = node_id.lower()
        return any(keyword in node_id_lower for keyword in file_keywords)

    def get_issues_by_severity(self, severity: IssueSeverity) -> list[ValidationIssue]:
        """Get all issues of a specific severity level."""
        return [issue for issue in self.issues if issue.severity == severity]

    def get_issues_by_category(self, category: str) -> list[ValidationIssue]:
        """Get all issues of a specific category."""
        return [issue for issue in self.issues if issue.category == category]

    def get_issues_for_cycle(self, cycle_id: str) -> list[ValidationIssue]:
        """Get all issues for a specific cycle."""
        return [issue for issue in self.issues if issue.cycle_id == cycle_id]

    def get_issues_for_node(self, node_id: str) -> list[ValidationIssue]:
        """Get all issues for a specific node."""
        return [issue for issue in self.issues if issue.node_id == node_id]

    def generate_report(self) -> dict[str, Any]:
        """
        Generate comprehensive validation report.

        Returns:
            Dict containing validation report with summary and details

        Example:
            >>> from kailash import Workflow
            >>> workflow = Workflow("test", "Test Workflow")
            >>> linter = CycleLinter(workflow)
            >>> linter.check_all()
            >>> report = linter.generate_report()
            >>> print(f"Found {report['summary']['total_issues']} issues")
        """
        errors = self.get_issues_by_severity(IssueSeverity.ERROR)
        warnings = self.get_issues_by_severity(IssueSeverity.WARNING)
        info = self.get_issues_by_severity(IssueSeverity.INFO)

        # Group by category
        by_category = {}
        for issue in self.issues:
            if issue.category not in by_category:
                by_category[issue.category] = []
            by_category[issue.category].append(issue)

        # Group by cycle
        by_cycle = {}
        for issue in self.issues:
            if issue.cycle_id:
                if issue.cycle_id not in by_cycle:
                    by_cycle[issue.cycle_id] = []
                by_cycle[issue.cycle_id].append(issue)

        return {
            "summary": {
                "total_issues": len(self.issues),
                "errors": len(errors),
                "warnings": len(warnings),
                "info": len(info),
                "categories": list(by_category.keys()),
                "affected_cycles": len(by_cycle),
            },
            "issues": self.issues,
            "by_severity": {"errors": errors, "warnings": warnings, "info": info},
            "by_category": by_category,
            "by_cycle": by_cycle,
            "recommendations": self._generate_recommendations(),
        }

    def _generate_recommendations(self) -> list[str]:
        """Generate high-level recommendations based on found issues."""
        recommendations = []

        errors = self.get_issues_by_severity(IssueSeverity.ERROR)
        if errors:
            recommendations.append(
                f"Fix {len(errors)} critical errors before deployment"
            )

        convergence_issues = self.get_issues_by_category("convergence")
        if convergence_issues:
            recommendations.append("Review convergence conditions for all cycles")

        performance_issues = self.get_issues_by_category("performance")
        if performance_issues:
            recommendations.append("Optimize cycles to improve performance")

        safety_issues = self.get_issues_by_category("safety")
        if safety_issues:
            recommendations.append(
                "Add safety limits (timeout, max_iterations) to cycles"
            )

        return recommendations
