"""
Strict Mode Validator for DataFlow Models and Workflows.

Implements strict mode validation checks that enforce best practices
and catch configuration errors at model registration time.

Validation Checks:
- STRICT-001: Primary key must be named 'id'
- STRICT-002: No conflicts with auto-managed fields (created_at, updated_at, etc.)
- STRICT-005: Disconnected nodes detection
- STRICT-006: Workflow output validation
- STRICT-007: Field naming conventions (snake_case vs camelCase, SQL reserved words)
- STRICT-008: Cyclic dependency validation
- STRICT-009: Workflow structure quality checks
"""

from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Set, Type

if TYPE_CHECKING:
    from dataflow.decorators import ValidationResult

    from kailash.workflow.builder import WorkflowBuilder


# ==============================================================================
# StrictLevel Enum
# ==============================================================================


class StrictLevel(Enum):
    """Granularity of strict mode enforcement."""

    RELAXED = "relaxed"  # Only critical errors (primary key, auto-managed fields)
    MODERATE = "moderate"  # + connection validation, orphan detection (default)
    AGGRESSIVE = "aggressive"  # + all best practice warnings as errors


# Auto-managed fields that DataFlow handles automatically
AUTO_MANAGED_FIELDS = {
    "created_at": "timestamp of record creation",
    "updated_at": "timestamp of last update",
    "created_by": "user who created the record",
    "updated_by": "user who last updated the record",
}


class StrictModeValidator:
    """
    Validator for strict mode validation checks.

    Strict mode elevates critical validation warnings to errors, enforcing
    best practices at model registration time.
    """

    def __init__(self, cls: Type):
        """
        Initialize strict mode validator.

        Args:
            cls: SQLAlchemy model class to validate
        """
        self.cls = cls
        self.model_name = cls.__name__

    def validate(self, result: "ValidationResult") -> None:
        """
        Run all strict mode validation checks.

        This method elevates critical validation warnings to errors
        in strict mode.

        Args:
            result: ValidationResult to accumulate errors/warnings
        """
        self._validate_strict_primary_key(result)
        self._validate_strict_auto_managed_fields(result)

    def validate_workflow_structure(
        self, workflow: "WorkflowBuilder", enable_cycles: bool = False
    ) -> Dict[str, List[Any]]:
        """
        Validate workflow structure for strict mode.

        Checks:
        - STRICT-005: Disconnected nodes detection
        - STRICT-006: Workflow output validation
        - STRICT-008: Cyclic dependency detection
        - STRICT-009: Workflow structure quality

        Args:
            workflow: WorkflowBuilder instance to validate
            enable_cycles: Whether cyclic workflows are enabled

        Returns:
            Dict with 'errors' and 'warnings' lists
        """
        errors = []
        warnings = []

        # STRICT-005: Check for disconnected nodes
        errors.extend(self._check_disconnected_nodes(workflow))

        # STRICT-006: Check workflow outputs
        errors.extend(self._check_workflow_outputs(workflow))

        # STRICT-008: Check for cycles
        cycle_results = self._detect_cycles(workflow, enable_cycles)
        if enable_cycles:
            warnings.extend(cycle_results)  # Warnings if cycles enabled
        else:
            errors.extend(cycle_results)  # Errors if cycles disabled

        # STRICT-009: Check workflow quality
        warnings.extend(self._check_workflow_quality(workflow))

        return {"errors": errors, "warnings": warnings}

    def generate_workflow_health_report(
        self, workflow: "WorkflowBuilder"
    ) -> Dict[str, Any]:
        """
        Generate comprehensive workflow health report.

        Returns:
            Dict with workflow metrics and issues
        """
        nodes = workflow.nodes if hasattr(workflow, "nodes") else {}
        connections = workflow.connections if hasattr(workflow, "connections") else []

        # Calculate metrics
        node_count = len(nodes)
        connection_count = len(connections)

        # Find disconnected nodes
        disconnected = []
        for node_id in nodes.keys():
            has_incoming = any(conn.get("to_node") == node_id for conn in connections)
            has_outgoing = any(conn.get("from_node") == node_id for conn in connections)
            if not has_incoming and not has_outgoing:
                disconnected.append(node_id)

        # Find output nodes
        output_nodes = []
        for node_id in nodes.keys():
            has_outgoing = any(conn.get("from_node") == node_id for conn in connections)
            if not has_outgoing:
                output_nodes.append(node_id)

        # Calculate max depth
        max_depth = self._calculate_workflow_depth(workflow)

        # Collect all issues
        validation_results = self.validate_workflow_structure(workflow)
        issues = []

        for error in validation_results["errors"]:
            issues.append(
                {
                    "code": error.get("code", "UNKNOWN"),
                    "message": error.get("message", ""),
                    "severity": "error",
                }
            )

        for warning in validation_results["warnings"]:
            issues.append(
                {
                    "code": warning.get("code", "UNKNOWN"),
                    "message": warning.get("message", ""),
                    "severity": "warning",
                }
            )

        return {
            "node_count": node_count,
            "connection_count": connection_count,
            "disconnected_nodes": len(disconnected),
            "output_nodes": output_nodes,
            "max_depth": max_depth,
            "issues": issues,
        }

    def _validate_strict_primary_key(self, result: "ValidationResult") -> None:
        """
        STRICT-001: Validate primary key in strict mode.

        In strict mode, primary key issues are elevated from warnings to errors.

        Checks:
        - Primary key must exist
        - Primary key must be named 'id'
        - No composite primary keys

        Args:
            result: ValidationResult to accumulate errors/warnings
        """
        # Import here to avoid circular dependency
        try:
            from sqlalchemy import inspect as sa_inspect
        except ImportError:
            return

        # First try raw class attributes (before mapper is ready)
        pk_columns_raw = []
        for attr_name in dir(self.cls):
            if attr_name.startswith("_"):
                continue
            try:
                from sqlalchemy import Column

                attr = getattr(self.cls, attr_name)
                if isinstance(attr, Column) and attr.primary_key:
                    pk_columns_raw.append((attr_name, attr))
            except Exception:
                continue

        # If we found PK columns from raw attributes, validate those
        if pk_columns_raw:
            # Check for composite primary key
            if len(pk_columns_raw) > 1:
                pk_names = ", ".join([name for name, _ in pk_columns_raw])
                result.add_error(
                    "STRICT-001a",
                    f"Model '{self.model_name}' has composite primary key ({pk_names}). "
                    f"DataFlow strict mode requires single primary key named 'id'.",
                    field=None,
                )
                return

            # Check if primary key is named 'id'
            pk_name, _ = pk_columns_raw[0]
            if pk_name != "id":
                result.add_error(
                    "STRICT-001b",
                    f"Model '{self.model_name}' primary key is named '{pk_name}'. "
                    f"DataFlow strict mode REQUIRES primary key to be named 'id'. "
                    f"Rename '{pk_name}' to 'id'.",
                    field=pk_name,
                )
            return

        # If no raw columns found, try mapper inspection
        try:
            mapper = sa_inspect(self.cls)
            pk_columns = list(mapper.primary_key)

            # Check if primary key exists
            if not pk_columns:
                result.add_error(
                    "STRICT-001a",
                    f"Model '{self.model_name}' must have a primary key named 'id'. "
                    f"Add: id = Column(String, primary_key=True)",
                    field=None,
                )
                return

            # Check for composite primary key
            if len(pk_columns) > 1:
                pk_names = ", ".join([col.name for col in pk_columns])
                result.add_error(
                    "STRICT-001a",
                    f"Model '{self.model_name}' has composite primary key ({pk_names}). "
                    f"DataFlow strict mode requires single primary key named 'id'.",
                    field=None,
                )
                return

            # Check if primary key is named 'id'
            pk_column = pk_columns[0]
            if pk_column.name != "id":
                result.add_error(
                    "STRICT-001b",
                    f"Model '{self.model_name}' primary key is named '{pk_column.name}'. "
                    f"DataFlow strict mode REQUIRES primary key to be named 'id'. "
                    f"Rename '{pk_column.name}' to 'id'.",
                    field=pk_column.name,
                )
        except Exception:
            # If we can't inspect and found no raw columns, assume no PK
            result.add_error(
                "STRICT-001a",
                f"Model '{self.model_name}' must have a primary key named 'id'. "
                f"Add: id = Column(String, primary_key=True)",
                field=None,
            )

    def _validate_strict_auto_managed_fields(self, result: "ValidationResult") -> None:
        """
        STRICT-002: Validate auto-managed fields in strict mode.

        In strict mode, auto-managed field conflicts are elevated from warnings to errors.

        Checks:
        - No user-defined created_at, updated_at, created_by, updated_by fields

        Args:
            result: ValidationResult to accumulate errors/warnings
        """
        # First try raw class attributes
        columns_checked = set()
        for attr_name in dir(self.cls):
            if attr_name.startswith("_"):
                continue
            try:
                from sqlalchemy import Column

                attr = getattr(self.cls, attr_name)
                if isinstance(attr, Column):
                    field_name = attr_name.lower()
                    columns_checked.add(attr_name)
                    if field_name in AUTO_MANAGED_FIELDS:
                        result.add_error(
                            "STRICT-002",
                            f"Model '{self.model_name}' defines '{attr_name}' field. "
                            f"DataFlow automatically manages {AUTO_MANAGED_FIELDS[field_name]}. "
                            f"Strict mode FORBIDS user-defined auto-managed fields. "
                            f"Remove '{attr_name}' from model definition.",
                            field=attr_name,
                        )
            except Exception:
                continue

        # If no raw columns found, try mapper
        if not columns_checked:
            try:
                from sqlalchemy import inspect as sa_inspect

                mapper = sa_inspect(self.cls)
                for column in mapper.columns:
                    field_name = column.name.lower()
                    if field_name in AUTO_MANAGED_FIELDS:
                        result.add_error(
                            "STRICT-002",
                            f"Model '{self.model_name}' defines '{column.name}' field. "
                            f"DataFlow automatically manages {AUTO_MANAGED_FIELDS[field_name]}. "
                            f"Strict mode FORBIDS user-defined auto-managed fields. "
                            f"Remove '{column.name}' from model definition.",
                            field=column.name,
                        )
            except Exception:
                pass

    # ==========================================================================
    # Workflow Validation Helper Methods
    # ==========================================================================

    def _check_disconnected_nodes(
        self, workflow: "WorkflowBuilder"
    ) -> List[Dict[str, Any]]:
        """
        STRICT-005: Check for disconnected nodes (orphans).

        Args:
            workflow: WorkflowBuilder instance

        Returns:
            List of error dicts
        """
        errors = []
        nodes = workflow.nodes if hasattr(workflow, "nodes") else {}
        connections = workflow.connections if hasattr(workflow, "connections") else []

        for node_id in nodes.keys():
            has_incoming = any(conn.get("to_node") == node_id for conn in connections)
            has_outgoing = any(conn.get("from_node") == node_id for conn in connections)

            if not has_incoming and not has_outgoing:
                errors.append(
                    {
                        "code": "STRICT-005",
                        "message": f"Node '{node_id}' has no connections. "
                        f"This may be dead code or missing connections. "
                        f"Either connect it or remove it.",
                        "field": node_id,
                        "severity": "error",
                    }
                )

        return errors

    def _check_workflow_outputs(
        self, workflow: "WorkflowBuilder"
    ) -> List[Dict[str, Any]]:
        """
        STRICT-006: Check workflow has valid outputs.

        Args:
            workflow: WorkflowBuilder instance

        Returns:
            List of error dicts
        """
        errors = []
        nodes = workflow.nodes if hasattr(workflow, "nodes") else {}
        connections = workflow.connections if hasattr(workflow, "connections") else []

        if not nodes:
            return errors

        # Find output nodes (nodes with no outgoing connections)
        output_nodes = []
        for node_id in nodes.keys():
            has_outgoing = any(conn.get("from_node") == node_id for conn in connections)
            if not has_outgoing:
                output_nodes.append(node_id)

        if len(output_nodes) == 0:
            errors.append(
                {
                    "code": "STRICT-006",
                    "message": "Workflow has no output nodes. "
                    "At least one node must have no outgoing connections.",
                    "field": "workflow",
                    "severity": "error",
                }
            )

        return errors

    def _detect_cycles(
        self, workflow: "WorkflowBuilder", enable_cycles: bool
    ) -> List[Dict[str, Any]]:
        """
        STRICT-008: Detect cyclic dependencies.

        Args:
            workflow: WorkflowBuilder instance
            enable_cycles: Whether cycles are enabled

        Returns:
            List of error/warning dicts
        """
        errors = []
        nodes = workflow.nodes if hasattr(workflow, "nodes") else {}
        connections = workflow.connections if hasattr(workflow, "connections") else []

        # Build adjacency list
        graph = {node_id: [] for node_id in nodes.keys()}
        for conn in connections:
            from_node = conn.get("from_node")
            to_node = conn.get("to_node")
            if from_node and to_node:
                graph[from_node].append(to_node)

        # DFS to detect cycles
        visited = set()
        rec_stack = set()

        def has_cycle_dfs(node, path):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    if has_cycle_dfs(neighbor, path):
                        return True
                elif neighbor in rec_stack:
                    # Cycle detected
                    cycle_start = path.index(neighbor)
                    cycle_path = path[cycle_start:] + [neighbor]
                    cycle_str = " → ".join(cycle_path)

                    severity = "warning" if enable_cycles else "error"
                    message = (
                        f"Workflow contains cycle: {cycle_str}. "
                        if enable_cycles
                        else f"Workflow contains cycle: {cycle_str}. "
                        f"Remove cycle or enable enable_cycles=True."
                    )

                    errors.append(
                        {
                            "code": "STRICT-008",
                            "message": message,
                            "field": "workflow",
                            "severity": severity,
                        }
                    )
                    return True

            path.pop()
            rec_stack.remove(node)
            return False

        for node in nodes.keys():
            if node not in visited:
                has_cycle_dfs(node, [])

        return errors

    def _check_workflow_quality(
        self, workflow: "WorkflowBuilder"
    ) -> List[Dict[str, Any]]:
        """
        STRICT-009: Check workflow structure quality.

        Args:
            workflow: WorkflowBuilder instance

        Returns:
            List of warning dicts
        """
        warnings = []

        # Check workflow depth
        max_depth = self._calculate_workflow_depth(workflow)
        if max_depth > 5:
            warnings.append(
                {
                    "code": "STRICT-009a",
                    "message": f"Workflow is deeply nested (depth={max_depth}). "
                    f"Consider flattening to improve readability (max recommended: 5).",
                    "field": "workflow",
                    "severity": "warning",
                }
            )

        # Check for excessive fanout
        nodes = workflow.nodes if hasattr(workflow, "nodes") else {}
        connections = workflow.connections if hasattr(workflow, "connections") else []

        fanout_count = {node_id: 0 for node_id in nodes.keys()}
        for conn in connections:
            from_node = conn.get("from_node")
            if from_node:
                fanout_count[from_node] += 1

        for node_id, count in fanout_count.items():
            if count > 10:
                warnings.append(
                    {
                        "code": "STRICT-009b",
                        "message": f"Node '{node_id}' has excessive fanout ({count} connections). "
                        f"Consider refactoring (max recommended: 10).",
                        "field": node_id,
                        "severity": "warning",
                    }
                )

        # Check for missing error handling (optional check)
        has_error_handling = any(
            "error" in conn.get("from_output", "").lower()
            or "error" in conn.get("to_input", "").lower()
            for conn in connections
        )

        if not has_error_handling and len(nodes) > 2:
            warnings.append(
                {
                    "code": "STRICT-009c",
                    "message": "Workflow has no error handling connections. "
                    "Consider adding error handlers for robustness.",
                    "field": "workflow",
                    "severity": "warning",
                }
            )

        return warnings

    def _calculate_workflow_depth(self, workflow: "WorkflowBuilder") -> int:
        """
        Calculate maximum depth of workflow.

        Args:
            workflow: WorkflowBuilder instance

        Returns:
            Maximum depth
        """
        nodes = workflow.nodes if hasattr(workflow, "nodes") else {}
        connections = workflow.connections if hasattr(workflow, "connections") else []

        # Build adjacency list
        graph = {node_id: [] for node_id in nodes.keys()}
        for conn in connections:
            from_node = conn.get("from_node")
            to_node = conn.get("to_node")
            if from_node and to_node:
                graph[from_node].append(to_node)

        # Find max depth using BFS
        max_depth = 0
        visited = set()

        # Find root nodes (no incoming connections)
        root_nodes = set(nodes.keys())
        for conn in connections:
            to_node = conn.get("to_node")
            if to_node in root_nodes:
                root_nodes.remove(to_node)

        for root in root_nodes:
            queue = [(root, 1)]
            while queue:
                node, depth = queue.pop(0)
                if node in visited:
                    continue
                visited.add(node)
                max_depth = max(max_depth, depth)

                for neighbor in graph.get(node, []):
                    queue.append((neighbor, depth + 1))

        return max_depth
