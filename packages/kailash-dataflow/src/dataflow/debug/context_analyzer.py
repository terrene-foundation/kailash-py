"""Context analyzer using Inspector for workflow introspection.

This module provides error context analysis by extracting workflow information
using the Inspector API to understand error root causes.
"""

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

from dataflow.debug.analysis_result import AnalysisResult
from dataflow.debug.error_capture import CapturedError
from dataflow.debug.error_categorizer import ErrorCategory
from dataflow.platform.inspector import Inspector


class ContextAnalyzer:
    """Analyzes error context using Inspector for workflow introspection.

    ContextAnalyzer is the Stage 3 (Analyze) component of the Debug Agent pipeline.
    It takes captured and categorized errors and extracts detailed workflow context
    using the Inspector API to provide:
    - Human-readable root cause descriptions
    - Affected workflow components (nodes, connections, models)
    - Structured context data for solution matching

    The analyzer dispatches to category-specific methods based on error type:
    - PARAMETER → _analyze_parameter_error()
    - CONNECTION → _analyze_connection_error()
    - MIGRATION → _analyze_migration_error()
    - CONFIGURATION → _analyze_configuration_error()
    - RUNTIME → _analyze_runtime_error()

    Usage:
        >>> inspector = Inspector(dataflow_instance)
        >>> analyzer = ContextAnalyzer(inspector)
        >>>
        >>> # Capture and categorize error
        >>> captured_error = error_capture.capture(exception)
        >>> category = categorizer.categorize(captured_error)
        >>>
        >>> # Analyze with workflow context
        >>> analysis = analyzer.analyze(captured_error, category)
        >>> print(analysis.root_cause)
        >>> print(analysis.affected_nodes)
    """

    def __init__(self, inspector: Inspector):
        """Initialize ContextAnalyzer with Inspector instance.

        Args:
            inspector: Inspector instance for workflow introspection

        Example:
            >>> from dataflow.platform.inspector import Inspector
            >>> inspector = Inspector(dataflow_instance)
            >>> analyzer = ContextAnalyzer(inspector)
        """
        self.inspector = inspector

    def analyze(self, error: CapturedError, category: ErrorCategory) -> AnalysisResult:
        """Analyze error with workflow context from Inspector.

        Dispatches to category-specific analyzer methods based on error category.
        Each method extracts relevant context using Inspector API and returns
        structured analysis result.

        Args:
            error: Captured error with full context (stacktrace, message, etc.)
            category: Categorized error with pattern match and confidence

        Returns:
            AnalysisResult with root cause, affected components, and context data

        Example:
            >>> analysis = analyzer.analyze(captured_error, category)
            >>> if category.category == "PARAMETER":
            ...     print(f"Root cause: {analysis.root_cause}")
            ...     print(f"Missing parameter: {analysis.context_data['missing_parameter']}")
        """
        # Dispatch to category-specific analyzer
        if category.category == "PARAMETER":
            return self._analyze_parameter_error(error, category)
        elif category.category == "CONNECTION":
            return self._analyze_connection_error(error, category)
        elif category.category == "MIGRATION":
            return self._analyze_migration_error(error, category)
        elif category.category == "CONFIGURATION":
            return self._analyze_configuration_error(error, category)
        elif category.category == "RUNTIME":
            return self._analyze_runtime_error(error, category)
        else:
            # Unknown or uncategorized error
            return AnalysisResult.unknown()

    def _analyze_parameter_error(
        self, error: CapturedError, category: ErrorCategory
    ) -> AnalysisResult:
        """Analyze parameter error with model schema context.

        Extracts node and model information using Inspector to identify:
        - Missing required parameters
        - Type mismatches
        - Invalid parameter values
        - Expected vs provided parameters

        Args:
            error: Captured parameter error
            category: Error category with pattern match

        Returns:
            AnalysisResult with parameter-specific context

        Context data includes:
        - node_type: Type of node (e.g., UserCreateNode)
        - model_name: Associated DataFlow model
        - model_schema: Full model schema from Inspector
        - missing_parameter: Name of missing parameter (if applicable)
        - field_type: Expected type of missing field
        - is_primary_key: Whether missing field is primary key
        - is_nullable: Whether field allows NULL
        - provided_parameters: Parameters that were provided
        """
        # Extract node_id from error context
        node_id = error.context.get("node_id")
        if not node_id:
            # Try to extract from stacktrace or error message
            node_id = self._extract_node_id_from_message(error.message)

        if not node_id:
            return AnalysisResult(
                root_cause="Parameter error detected but could not identify node",
                affected_nodes=[],
                affected_connections=[],
                affected_models=[],
                context_data={"error_message": error.message},
                suggestions=["Add node_id to error context for better analysis"],
            )

        # Try to get node type from workflow if available
        node_type = None
        workflow = self.inspector._get_workflow()
        if workflow and hasattr(workflow, "nodes") and node_id in workflow.nodes:
            # Get node instance from workflow
            node_instance = workflow.nodes[node_id]
            # Get node type from class name
            node_type = node_instance.__class__.__name__

        # Extract model name from node_type (if we got it) or node_id
        model_name = None
        if node_type:
            model_name = self._extract_model_name(node_type)
        if not model_name:
            model_name = self._extract_model_name(node_id)

        # Try to extract model name from error message (table name)
        if not model_name:
            model_name = self._extract_model_name_from_table(error.message)

        if not model_name:
            return AnalysisResult(
                root_cause=f"Parameter error in node '{node_id}' - could not determine model",
                affected_nodes=[node_id],
                affected_connections=[],
                affected_models=[],
                context_data={
                    "node_id": node_id,
                    "node_type": node_type,
                    "error_message": error.message,
                },
                suggestions=[
                    "Verify node type matches DataFlow model naming convention"
                ],
            )

        # Get model schema from Inspector
        try:
            model_info = self.inspector.model(model_name)
        except ValueError:
            # Model not found in Inspector
            return AnalysisResult(
                root_cause=f"Parameter error in node '{node_id}' for model '{model_name}' (model not registered)",
                affected_nodes=[node_id],
                affected_connections=[],
                affected_models=[model_name],
                context_data={
                    "node_id": node_id,
                    "model_name": model_name,
                    "error_message": error.message,
                },
                suggestions=[
                    f"Register model '{model_name}' with DataFlow using @db.model decorator"
                ],
            )

        # Extract missing parameter from error message
        missing_param = self._extract_parameter_name(error.message)

        # Get field schema if parameter identified
        field_type = None
        is_primary_key = False
        is_nullable = False

        if missing_param and missing_param in model_info.schema:
            field_schema = model_info.schema[missing_param]
            field_type = field_schema.get("type", "unknown")
            is_primary_key = field_schema.get("primary_key", False)
            is_nullable = field_schema.get("nullable", False)

        # Build human-readable root cause
        if missing_param:
            root_cause = (
                f"Node '{node_id}' is missing required parameter '{missing_param}'"
            )
            if is_primary_key:
                root_cause += " (primary key)"
        else:
            root_cause = f"Node '{node_id}' has parameter validation error"

        # Extract provided parameters from error context
        provided_params = error.context.get(
            "parameters", error.context.get("kwargs", {})
        )

        # Generate suggestions
        suggestions = []
        if missing_param:
            if is_primary_key:
                suggestions.append(
                    f"Add '{missing_param}' field (primary key, type: {field_type})"
                )
            else:
                suggestions.append(f"Add '{missing_param}' field (type: {field_type})")

            if field_type:
                suggestions.append(f"Expected type: {field_type}")
        else:
            suggestions.append("Check node parameters match model schema")
            suggestions.append(
                f"Review model '{model_name}' schema for required fields"
            )

        return AnalysisResult(
            root_cause=root_cause,
            affected_nodes=[node_id],
            affected_connections=[],
            affected_models=[model_name],
            context_data={
                "node_id": node_id,
                "node_type": node_id,  # For compatibility
                "model_name": model_name,
                "model_schema": model_info.schema,
                "missing_parameter": missing_param or "unknown",
                "field_type": field_type,
                "is_primary_key": is_primary_key,
                "is_nullable": is_nullable,
                "provided_parameters": provided_params,
                "table_name": model_info.table_name,
            },
            suggestions=suggestions,
        )

    def _extract_node_id_from_message(self, message: str) -> Optional[str]:
        """Extract node ID from error message.

        Args:
            message: Error message

        Returns:
            Node ID if found, None otherwise
        """
        # Try pattern: Node 'node_id'
        match = re.search(r"[Nn]ode ['\"]([^'\"]+)['\"]", message)
        if match:
            return match.group(1)

        # Try pattern: in node node_id
        match = re.search(r"in node ([^\s,:.]+)", message)
        if match:
            return match.group(1)

        return None

    def _extract_model_name(self, node_id: str) -> Optional[str]:
        """Extract model name from node ID.

        Node IDs follow pattern: ModelNameOperationNode (e.g., UserCreateNode)

        Args:
            node_id: Node identifier

        Returns:
            Model name if extracted, None otherwise

        Example:
            >>> _extract_model_name("UserCreateNode")
            'User'
            >>> _extract_model_name("OrderItemUpdateNode")
            'OrderItem'
        """
        # Pattern: ModelName + (Create|Read|Update|Delete|List|Count|Upsert|BulkCreate)Node
        match = re.search(
            r"^(.+?)(Create|Read|Update|Delete|List|Count|Upsert|BulkCreate|ReadById)Node$",
            node_id,
        )
        if match:
            return match.group(1)

        return None

    def _extract_parameter_name(self, message: str) -> Optional[str]:
        """Extract parameter name from error message.

        Args:
            message: Error message

        Returns:
            Parameter name if found, None otherwise

        Example:
            >>> _extract_parameter_name("Missing required parameter 'id'")
            'id'
            >>> _extract_parameter_name("NOT NULL constraint failed: users.id")
            'id'
        """
        # Try pattern: parameter 'name' or parameter "name"
        match = re.search(r"parameter ['\"]([^'\"]+)['\"]", message, re.IGNORECASE)
        if match:
            return match.group(1)

        # Try pattern: 'name' parameter
        match = re.search(r"['\"]([^'\"]+)['\"] parameter", message, re.IGNORECASE)
        if match:
            return match.group(1)

        # Try pattern: field 'name'
        match = re.search(r"field ['\"]([^'\"]+)['\"]", message, re.IGNORECASE)
        if match:
            return match.group(1)

        # Try pattern: NOT NULL constraint failed: table.column
        match = re.search(
            r"NOT NULL constraint failed: \w+\.(\w+)", message, re.IGNORECASE
        )
        if match:
            return match.group(1)

        # Try pattern: column 'name' or column name
        match = re.search(r"column ['\"]?(\w+)['\"]?", message, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _extract_model_name_from_table(self, message: str) -> Optional[str]:
        """Extract model name from table name in error message.

        Args:
            message: Error message containing table name

        Returns:
            Model name if found, None otherwise

        Example:
            >>> _extract_model_name_from_table("NOT NULL constraint failed: users.id")
            'User'
            >>> _extract_model_name_from_table("Table 'order_items' does not exist")
            'OrderItem'
        """
        # Try pattern: NOT NULL constraint failed: table.column
        match = re.search(
            r"NOT NULL constraint failed: (\w+)\.", message, re.IGNORECASE
        )
        if match:
            table_name = match.group(1)
            # Convert table name to model name (users -> User, order_items -> OrderItem)
            return self._table_name_to_model_name(table_name)

        # Try pattern: table 'name' or table name
        match = re.search(r"table ['\"]?(\w+)['\"]?", message, re.IGNORECASE)
        if match:
            table_name = match.group(1)
            return self._table_name_to_model_name(table_name)

        return None

    def _table_name_to_model_name(self, table_name: str) -> str:
        """Convert table name to model name.

        Args:
            table_name: Database table name (e.g., 'users', 'order_items')

        Returns:
            Model name (e.g., 'User', 'OrderItem')

        Example:
            >>> _table_name_to_model_name("users")
            'User'
            >>> _table_name_to_model_name("order_items")
            'OrderItem'
        """
        # Remove trailing 's' (users -> user)
        if table_name.endswith("s"):
            singular = table_name[:-1]
        else:
            singular = table_name

        # Convert snake_case to PascalCase
        parts = singular.split("_")
        return "".join(part.capitalize() for part in parts)

    def _analyze_connection_error(
        self, error: CapturedError, category: ErrorCategory
    ) -> AnalysisResult:
        """Analyze connection error with workflow structure.

        Extracts workflow graph information using Inspector to identify:
        - Missing source/target nodes
        - Invalid parameter connections
        - Similar node names (typo suggestions)
        - Available nodes in workflow

        Args:
            error: Captured connection error
            category: Error category with pattern match

        Returns:
            AnalysisResult with connection-specific context

        Context data includes:
        - source_node: Source node ID
        - target_node: Target node ID
        - missing_node: Which node is missing
        - available_nodes: List of all nodes in workflow
        - similar_nodes: Fuzzy matches for typo suggestions (with similarity scores)
        - connection_details: Connection parameter information
        """
        # Extract connection details from error context
        source_node = error.context.get("source_node")
        target_node = error.context.get("target_node")

        # Try to extract from error message if not in context
        if not source_node or not target_node:
            source_node, target_node = self._extract_connection_from_message(
                error.message
            )

        # Get workflow if available
        workflow = self.inspector._get_workflow()
        if workflow is None:
            return AnalysisResult(
                root_cause="Connection error detected but workflow not available for analysis",
                affected_nodes=[target_node] if target_node else [],
                affected_connections=(
                    [f"{source_node} → {target_node}"]
                    if source_node and target_node
                    else []
                ),
                affected_models=[],
                context_data={
                    "source_node": source_node,
                    "target_node": target_node,
                    "error_message": error.message,
                },
                suggestions=[
                    "Provide WorkflowBuilder instance to Inspector for connection analysis"
                ],
            )

        # Get all nodes in workflow
        available_nodes = []
        if hasattr(workflow, "nodes"):
            # WorkflowBuilder.nodes is a dict mapping node_id -> node_instance
            available_nodes = list(workflow.nodes.keys())

        # Determine which node is missing
        missing_node = None
        present_node = None

        if source_node and source_node not in available_nodes:
            missing_node = source_node
            present_node = target_node
        elif target_node and target_node not in available_nodes:
            missing_node = target_node
            present_node = source_node

        # Find similar node names for typo suggestions
        similar_nodes = []
        if missing_node:
            similar_nodes = self._find_similar_strings(missing_node, available_nodes)

        # Build human-readable root cause
        if missing_node:
            if similar_nodes:
                root_cause = f"Connection references non-existent node '{missing_node}' (did you mean '{similar_nodes[0][0]}'?)"
            else:
                root_cause = f"Connection references non-existent node '{missing_node}'"
        else:
            root_cause = "Connection error: invalid parameter connection"

        # Get connection details if available
        connection_details = {}
        if hasattr(workflow, "connections"):
            for conn in workflow.connections:
                # Handle both dict and object access
                if hasattr(conn, "get"):
                    conn_source = conn.get("source_node", "")
                    conn_target = conn.get("target_node", "")
                else:
                    conn_dict = getattr(conn, "__dict__", {})
                    conn_source = conn_dict.get("source_node", "")
                    conn_target = conn_dict.get("target_node", "")

                if conn_source == source_node and conn_target == target_node:
                    connection_details = {
                        "source_param": (
                            conn.get("source_parameter", "")
                            if hasattr(conn, "get")
                            else conn_dict.get("source_parameter", "")
                        ),
                        "target_param": (
                            conn.get("target_parameter", "")
                            if hasattr(conn, "get")
                            else conn_dict.get("target_parameter", "")
                        ),
                    }
                    break

        # Generate suggestions
        suggestions = []
        if missing_node and similar_nodes:
            suggestions.append(
                f"Replace '{missing_node}' with '{similar_nodes[0][0]}' (similarity: {similar_nodes[0][1]:.2f})"
            )
            if len(similar_nodes) > 1:
                suggestions.append(
                    f"Other options: {', '.join([n[0] for n in similar_nodes[1:3]])}"
                )
        elif missing_node:
            suggestions.append(
                f"Add node '{missing_node}' to workflow before creating connection"
            )
        else:
            suggestions.append("Verify source and target nodes exist in workflow")
            suggestions.append(
                "Check connection parameter names match node outputs/inputs"
            )

        if available_nodes:
            suggestions.append(f"Available nodes: {', '.join(available_nodes[:5])}")

        # Build affected components list
        affected_nodes = []
        if present_node:
            affected_nodes.append(present_node)
        if missing_node:
            affected_nodes.append(missing_node)

        connection_str = (
            f"{source_node} → {target_node}"
            if source_node and target_node
            else "unknown → unknown"
        )

        return AnalysisResult(
            root_cause=root_cause,
            affected_nodes=affected_nodes,
            affected_connections=[connection_str],
            affected_models=[],
            context_data={
                "source_node": source_node,
                "target_node": target_node,
                "missing_node": missing_node,
                "available_nodes": available_nodes,
                "similar_nodes": similar_nodes,
                "connection_details": connection_details,
                "error_message": error.message,
            },
            suggestions=suggestions,
        )

    def _extract_connection_from_message(
        self, message: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Extract source and target nodes from error message.

        Args:
            message: Error message

        Returns:
            Tuple of (source_node, target_node), either may be None

        Example:
            >>> _extract_connection_from_message("Connection from user_create to user_read failed")
            ('user_create', 'user_read')
        """
        # Try pattern: from source to target
        match = re.search(
            r"from ['\"]?(\w+)['\"]? to ['\"]?(\w+)['\"]?", message, re.IGNORECASE
        )
        if match:
            return match.group(1), match.group(2)

        # Try pattern: source -> target
        match = re.search(r"['\"]?(\w+)['\"]?\s*->\s*['\"]?(\w+)['\"]?", message)
        if match:
            return match.group(1), match.group(2)

        # Try pattern: connection source_node target_node
        match = re.search(
            r"connection ['\"]?(\w+)['\"]? ['\"]?(\w+)['\"]?", message, re.IGNORECASE
        )
        if match:
            return match.group(1), match.group(2)

        return None, None

    def _analyze_migration_error(
        self, error: CapturedError, category: ErrorCategory
    ) -> AnalysisResult:
        """Analyze migration error with schema context.

        Extracts schema and migration information to identify:
        - Missing tables
        - Schema mismatches
        - Constraint violations
        - Migration history issues

        Args:
            error: Captured migration error
            category: Error category with pattern match

        Returns:
            AnalysisResult with migration-specific context

        Context data includes:
        - table_name: Affected table name
        - existing_tables: List of existing tables
        - similar_tables: Fuzzy matches for typo suggestions
        - schema_info: Current schema information
        - migration_history: Migration status
        """
        # Extract table name from error message
        table_match = re.search(
            r"table ['\"]?(\w+)['\"]?", error.message, re.IGNORECASE
        )
        table_name = table_match.group(1) if table_match else "unknown"

        # Get all models
        try:
            models = (
                self.inspector.db._models.keys()
                if hasattr(self.inspector.db, "_models")
                else []
            )
            existing_tables = [name.lower() for name in models]
        except Exception:
            existing_tables = []

        # Find similar table names
        similar_tables = self._find_similar_strings(table_name, existing_tables)

        return AnalysisResult(
            root_cause=f"Migration error: Table '{table_name}' issue",
            affected_nodes=[],
            affected_connections=[],
            affected_models=[table_name] if table_name != "unknown" else [],
            context_data={
                "table_name": table_name,
                "existing_tables": existing_tables,
                "similar_tables": similar_tables,
                "error_message": error.message,
            },
            suggestions=[
                f"Check if table '{table_name}' exists in database",
                (
                    "Review migration history"
                    if not similar_tables
                    else f"Did you mean: {similar_tables[0][0]}?"
                ),
            ],
        )

    def _analyze_configuration_error(
        self, error: CapturedError, category: ErrorCategory
    ) -> AnalysisResult:
        """Analyze configuration error with environment context.

        Extracts configuration information to identify:
        - Invalid database URLs
        - Missing environment variables
        - Configuration file issues
        - Connection settings problems

        Args:
            error: Captured configuration error
            category: Error category with pattern match

        Returns:
            AnalysisResult with configuration-specific context

        Context data includes:
        - config_key: Configuration parameter that failed
        - expected_format: Expected configuration format
        - environment_vars: Related environment variables
        - config_file: Configuration file path (if applicable)
        """
        # Extract configuration issue from error message
        config_match = re.search(
            r"(database|url|config|environment)", error.message, re.IGNORECASE
        )
        config_type = config_match.group(1).lower() if config_match else "configuration"

        return AnalysisResult(
            root_cause=f"Configuration error: Invalid {config_type} settings",
            affected_nodes=[],
            affected_connections=[],
            affected_models=[],
            context_data={
                "config_type": config_type,
                "error_message": error.message,
            },
            suggestions=[
                f"Check {config_type} settings in environment variables",
                "Verify database URL format: postgresql://user:password@host:port/database",
                "Review configuration file for syntax errors",
            ],
        )

    def _analyze_runtime_error(
        self, error: CapturedError, category: ErrorCategory
    ) -> AnalysisResult:
        """Analyze runtime error with execution context.

        Extracts runtime information to identify:
        - Query timeouts
        - Resource exhaustion
        - Deadlocks
        - Performance issues

        Args:
            error: Captured runtime error
            category: Error category with pattern match

        Returns:
            AnalysisResult with runtime-specific context

        Context data includes:
        - runtime_issue: Type of runtime problem (timeout, resource, deadlock)
        - query_info: Query information (if available)
        - resource_usage: Resource usage indicators
        - performance_hints: Performance optimization suggestions
        """
        # Extract runtime issue type
        if "timeout" in error.message.lower():
            runtime_issue = "timeout"
            suggestions = [
                "Increase query timeout limit",
                "Optimize query with indexes",
                "Check database connection pool settings",
            ]
        elif "deadlock" in error.message.lower():
            runtime_issue = "deadlock"
            suggestions = [
                "Review transaction isolation level",
                "Optimize query execution order",
                "Reduce transaction duration",
            ]
        else:
            runtime_issue = "general"
            suggestions = [
                "Check database logs for details",
                "Monitor resource usage during query execution",
            ]

        return AnalysisResult(
            root_cause=f"Runtime error: {runtime_issue} detected during workflow execution",
            affected_nodes=[],
            affected_connections=[],
            affected_models=[],
            context_data={
                "runtime_issue": runtime_issue,
                "error_message": error.message,
            },
            suggestions=suggestions,
        )

    def _find_similar_strings(
        self, target: str, candidates: List[str], threshold: float = 0.5
    ) -> List[Tuple[str, float]]:
        """Find similar strings using Levenshtein distance for typo suggestions.

        Uses difflib.SequenceMatcher to compute similarity ratio between strings.
        Returns candidates with similarity > threshold, sorted by similarity.

        Args:
            target: String to find matches for
            candidates: List of candidate strings to match against
            threshold: Minimum similarity ratio (0.0-1.0, default 0.5)

        Returns:
            List of tuples (candidate, similarity_score) sorted by similarity (highest first)

        Example:
            >>> similar = analyzer._find_similar_strings("usr_create", ["user_create", "user_update"])
            >>> similar
            [('user_create', 0.85), ('user_update', 0.65)]
        """
        similarities = []
        for candidate in candidates:
            ratio = SequenceMatcher(None, target.lower(), candidate.lower()).ratio()
            if ratio > threshold:
                similarities.append((candidate, ratio))

        return sorted(similarities, key=lambda x: x[1], reverse=True)
