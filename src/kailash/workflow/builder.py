"""Workflow builder implementation for the Kailash SDK."""

import logging
import uuid
from typing import TYPE_CHECKING, Any, Optional, Union

from kailash.nodes.base import Node, NodeRegistry
from kailash.sdk_exceptions import ConnectionError, WorkflowValidationError
from kailash.workflow.contracts import ConnectionContract, get_contract_registry
from kailash.workflow.graph import Workflow
from kailash.workflow.validation import (
    IssueSeverity,
    ParameterDeclarationValidator,
    ValidationIssue,
)

logger = logging.getLogger(__name__)


class WorkflowBuilder:
    """Builder pattern for creating Workflow instances."""

    def __init__(self, edge_config: dict[str, Any] | None = None):
        """Initialize an empty workflow builder.

        Args:
            edge_config: Optional edge infrastructure configuration
        """
        self.nodes: dict[str, dict[str, Any]] = {}
        self.connections: list[dict[str, str]] = []
        self._metadata: dict[str, Any] = {}
        # Parameter injection capabilities
        self.workflow_parameters: dict[str, Any] = {}
        self.parameter_mappings: dict[str, dict[str, str]] = {}

        # Edge infrastructure support
        self.edge_config = edge_config
        self._has_edge_nodes = False
        self._edge_infrastructure = None

        # Connection contracts support
        self.connection_contracts: dict[str, ConnectionContract] = {}
        self._contract_registry = get_contract_registry()

        # Parameter validation support
        self._param_validator = ParameterDeclarationValidator()

    def _is_sdk_node(self, node_class: type) -> bool:
        """Detect if node is SDK-provided vs custom implementation.

        SDK nodes are registered in the NodeRegistry via @register_node decorator.
        Custom nodes are not registered and require class reference usage.

        Args:
            node_class: The node class to check

        Returns:
            True if node is registered in SDK (can use string reference),
            False if custom node (must use class reference)
        """
        if not hasattr(node_class, "__name__"):
            return False

        # Check if the node class is registered in the NodeRegistry
        try:
            registered_class = NodeRegistry.get(node_class.__name__)
            # Check if it's the same class (identity check)
            return registered_class is node_class
        except Exception:
            # Node not found in registry = custom node
            return False

    def _generate_intelligent_node_warning(self, node_class: type, node_id: str) -> str:
        """Generate context-aware warnings based on node type.

        Args:
            node_class: The node class being added
            node_id: The node ID

        Returns:
            Appropriate warning message for the node type
        """
        if self._is_sdk_node(node_class):
            # SDK node using class reference - suggest string pattern
            return (
                f"SDK node detected. Consider using string reference for better compatibility:\n"
                f"  CURRENT: add_node({node_class.__name__}, '{node_id}', {{...}})\n"
                f"  PREFERRED: add_node('{node_class.__name__}', '{node_id}', {{...}})\n"
                f"String references work for all @register_node() decorated SDK nodes."
            )
        else:
            # Custom node using class reference - this is CORRECT
            return (
                f"✅ CUSTOM NODE USAGE CORRECT\n"
                f"\n"
                f"Pattern: add_node({node_class.__name__}, '{node_id}', {{...}})\n"
                f"Status: This is the CORRECT pattern for custom nodes\n"
                f"\n"
                f'⚠️  IGNORE "preferred pattern" suggestions for custom nodes\n'
                f"String references only work for @register_node() decorated SDK nodes.\n"
                f"Custom nodes MUST use class references as shown above.\n"
                f"\n"
                f"📚 Guide: sdk-users/7-gold-standards/GOLD-STANDARD-custom-node-development-guide.md"
            )

    def validate_parameter_declarations(
        self, warn_on_issues: bool = True
    ) -> list[ValidationIssue]:
        """Validate parameter declarations for all nodes in the workflow.

        This method detects common parameter declaration issues that lead to
        silent parameter dropping and debugging difficulties.

        Args:
            warn_on_issues: Whether to log warnings for detected issues

        Returns:
            List of ValidationIssue objects for any problems found
        """
        all_issues = []

        for node_id, node_info in self.nodes.items():
            try:
                # Create a temporary instance to validate parameter declarations
                if "instance" in node_info:
                    # Use existing instance
                    node_instance = node_info["instance"]
                    workflow_params = {}  # Instance already has config
                elif "class" in node_info:
                    # Create temporary instance of custom node
                    node_class = node_info["class"]
                    node_config = node_info.get("config", {})
                    # Create minimal instance just for parameter validation
                    try:
                        node_instance = node_class(**node_config)
                        workflow_params = node_config
                    except Exception as e:
                        # If we can't create instance, skip detailed validation
                        all_issues.append(
                            ValidationIssue(
                                severity=IssueSeverity.WARNING,
                                category="parameter_declaration",
                                code="PAR005",
                                message=f"Could not validate parameters for custom node '{node_id}': {e}",
                                suggestion="Ensure node constructor accepts provided configuration parameters",
                                node_id=node_id,
                            )
                        )
                        continue
                else:
                    # SDK node - validate if we can create it
                    node_type = node_info["type"]
                    node_config = node_info.get("config", {})
                    try:
                        # Try to get the class from registry
                        node_class = NodeRegistry.get(node_type)
                        node_instance = node_class(**node_config)
                        workflow_params = node_config
                    except Exception:
                        # Skip validation for nodes we can't instantiate
                        continue

                # Validate parameter declarations
                issues = self._param_validator.validate_node_parameters(
                    node_instance, workflow_params
                )

                # Add node_id to issues
                for issue in issues:
                    issue.node_id = node_id
                    all_issues.append(issue)

                    # Log warnings if requested
                    if warn_on_issues:
                        if issue.severity == IssueSeverity.ERROR:
                            logger.error(
                                f"Parameter validation error in node '{node_id}': {issue.message}"
                            )
                        elif issue.severity == IssueSeverity.WARNING:
                            # ADR-002: Changed from WARNING to DEBUG - extra params safely ignored
                            logger.debug(
                                f"Parameter validation info in node '{node_id}': {issue.message}"
                            )

            except Exception as e:
                # General validation error
                all_issues.append(
                    ValidationIssue(
                        severity=IssueSeverity.WARNING,
                        category="parameter_declaration",
                        code="PAR006",
                        message=f"Parameter validation failed for node '{node_id}': {e}",
                        suggestion="Check node configuration and parameter declarations",
                        node_id=node_id,
                    )
                )

        return all_issues

    def add_node(self, *args, **kwargs) -> str:
        """
        Unified add_node method supporting multiple API patterns.

        Supported patterns:
        1. add_node("NodeType", "node_id", {"param": value})     # Current/Preferred
        2. add_node("node_id", NodeClass, param=value)           # Legacy fluent
        3. add_node(NodeClass, "node_id", param=value)           # Alternative

        Args:
            *args: Positional arguments (pattern-dependent)
            **kwargs: Keyword arguments for configuration

        Returns:
            Node ID (useful for method chaining)

        Raises:
            WorkflowValidationError: If node_id is already used or invalid pattern
        """
        # Pattern detection and routing
        if len(args) == 0 and kwargs:
            # Keyword-only pattern: add_node(node_type="NodeType", node_id="id", config={})
            node_type = kwargs.pop("node_type", None)
            node_id = kwargs.pop("node_id", None)
            config = kwargs.pop("config", {})
            # Any remaining kwargs are treated as config
            config.update(kwargs)

            if node_type is None:
                raise WorkflowValidationError(
                    "node_type is required when using keyword arguments"
                )

            return self._add_node_current(node_type, node_id, config)

        elif len(args) == 1:
            # Single argument with possible keywords
            if isinstance(args[0], str) and kwargs:
                # Pattern: add_node("NodeType", node_id="id", config={})
                node_type = args[0]
                node_id = kwargs.pop("node_id", None)
                config = kwargs.pop("config", {})
                # Any remaining kwargs are treated as config
                config.update(kwargs)
                return self._add_node_current(node_type, node_id, config)
            elif isinstance(args[0], str):
                # Pattern: add_node("NodeType")
                return self._add_node_current(args[0], None, {})
            elif hasattr(args[0], "__name__"):
                # Pattern: add_node(NodeClass)
                return self._add_node_alternative(args[0], None, **kwargs)
            else:
                if isinstance(args[0], Node):
                    # Pattern: add_node(node_instance)
                    return self._add_node_instance(args[0], None)

        elif len(args) == 3 and isinstance(args[0], str) and isinstance(args[2], dict):
            # Pattern 1: Current API - add_node("NodeType", "node_id", {"param": value})
            return self._add_node_current(args[0], args[1], args[2])

        elif len(args) >= 2 and isinstance(args[0], str):
            # Pattern 2: Legacy fluent API - add_node("node_id", NodeClass, param=value)
            if hasattr(args[1], "__name__") or isinstance(args[1], type):
                return self._add_node_legacy_fluent(args[0], args[1], **kwargs)
            elif isinstance(args[1], str):
                # Two strings - assume current API: add_node("NodeType", "node_id")
                config = kwargs if kwargs else (args[2] if len(args) > 2 else {})
                return self._add_node_current(args[0], args[1], config)
            elif isinstance(args[1], dict):
                # Pattern: add_node("NodeType", {config}) - treat as add_node("NodeType", None, {config})
                return self._add_node_current(args[0], None, args[1])
            else:
                # Invalid second argument
                raise WorkflowValidationError(
                    f"Invalid node type: {type(args[1]).__name__}. "
                    "Expected: str (node type name), Node class, or Node instance"
                )

        elif len(args) >= 2 and hasattr(args[0], "__name__"):
            # Pattern 3: Alternative - add_node(NodeClass, "node_id", param=value)
            # Handle both dict config and keyword args
            if len(args) == 3 and isinstance(args[2], dict):
                # Config provided as dict
                return self._add_node_alternative(args[0], args[1], **args[2])
            else:
                # Config provided as kwargs
                return self._add_node_alternative(args[0], args[1], **kwargs)

        elif len(args) >= 2:
            # Check if first arg is a Node instance
            if isinstance(args[0], Node):
                # Pattern 4: Instance - add_node(node_instance, "node_id") or add_node(node_instance, "node_id", config)
                # Config is ignored for instances
                return self._add_node_instance(args[0], args[1])
            elif len(args) == 2:
                # Invalid arguments for 2-arg call
                raise WorkflowValidationError(
                    f"Invalid node type: {type(args[0]).__name__}. "
                    "Expected: str (node type name), Node class, or Node instance"
                )

            # For 3 or more args that don't match other patterns
            # Error with helpful message
            raise WorkflowValidationError(
                f"Invalid add_node signature. Received {len(args)} args: {[type(arg).__name__ for arg in args]}\n"
                f"Supported patterns:\n"
                f"  add_node('NodeType', 'node_id', {{'param': value}})  # Preferred\n"
                f"  add_node('node_id', NodeClass, param=value)          # Legacy\n"
                f"  add_node(NodeClass, 'node_id', param=value)          # Alternative\n"
                f"Examples:\n"
                f"  add_node('HTTPRequestNode', 'api_call', {{'url': 'https://api.com'}})\n"
                f"  add_node('csv_reader', CSVReaderNode, file_path='data.csv')"
            )

    def _add_node_current(
        self, node_type: str, node_id: str | None, config: dict[str, Any]
    ) -> str:
        """Handle current API pattern: add_node('NodeType', 'node_id', {'param': value})"""
        return self._add_node_unified(node_type, node_id, config)

    def _add_node_legacy_fluent(
        self, node_id: str, node_class_or_type: Any, **config
    ) -> "WorkflowBuilder":
        """Handle legacy fluent API pattern: add_node('node_id', NodeClass, param=value)"""
        import warnings

        # If it's a class, validate it's a Node subclass
        if isinstance(node_class_or_type, type) and not issubclass(
            node_class_or_type, Node
        ):
            raise WorkflowValidationError(
                f"Invalid node type: {node_class_or_type}. Expected a Node subclass or string."
            )

        warnings.warn(
            f"Legacy fluent API usage detected. "
            f"Migration guide:\n"
            f"  OLD: add_node('{node_id}', {getattr(node_class_or_type, '__name__', str(node_class_or_type))}, {list(config.keys())})\n"
            f"  NEW: add_node('{getattr(node_class_or_type, '__name__', str(node_class_or_type))}', '{node_id}', {config})\n"
            f"Legacy support will be removed in v0.8.0",
            DeprecationWarning,
            stacklevel=3,
        )

        if hasattr(node_class_or_type, "__name__"):
            node_type = node_class_or_type.__name__
        else:
            node_type = str(node_class_or_type)

        self._add_node_unified(node_type, node_id, config)
        return self  # Return self for fluent chaining

    def _add_node_alternative(
        self, node_class: type, node_id: str | None, **config
    ) -> str:
        """Handle alternative pattern: add_node(NodeClass, 'node_id', param=value)"""
        import warnings

        # Validate that node_class is actually a Node subclass
        if not isinstance(node_class, type) or not issubclass(node_class, Node):
            raise WorkflowValidationError(
                f"Invalid node type: {node_class}. Expected a Node subclass."
            )

        # Generate ID if not provided
        if node_id is None:
            node_id = f"node_{uuid.uuid4().hex[:8]}"

        # Generate context-aware warning based on node type
        warning_message = self._generate_intelligent_node_warning(node_class, node_id)
        warnings.warn(
            warning_message,
            UserWarning,
            stacklevel=3,
        )

        # Store the class reference along with the type name
        self.nodes[node_id] = {
            "type": node_class.__name__,
            "config": config,
            "class": node_class,
        }
        logger.info(f"Added node '{node_id}' of type '{node_class.__name__}'")
        return node_id

    def _add_node_instance(self, node_instance: "Node", node_id: str | None) -> str:
        """Handle instance pattern: add_node(node_instance, 'node_id')"""
        import warnings

        # Generate ID if not provided
        if node_id is None:
            node_id = f"node_{uuid.uuid4().hex[:8]}"

        warnings.warn(
            f"Instance-based API usage detected. Consider using preferred pattern:\n"
            f"  CURRENT: add_node(<instance>, '{node_id}')\n"
            f"  PREFERRED: add_node('{node_instance.__class__.__name__}', '{node_id}', {{'param': value}})",
            UserWarning,
            stacklevel=3,
        )

        # Store the instance
        self.nodes[node_id] = {
            "instance": node_instance,
            "type": node_instance.__class__.__name__,
        }
        logger.info(
            f"Added node '{node_id}' with instance of type '{node_instance.__class__.__name__}'"
        )
        return node_id

    def _add_node_unified(
        self,
        node_type: str,
        node_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        """
        Unified implementation for all add_node patterns.

        Args:
            node_type: Node type name (string)
            node_id: Unique identifier for this node (auto-generated if not provided)
            config: Configuration for the node

        Returns:
            Node ID

        Raises:
            WorkflowValidationError: If node_id is already used
        """
        # Generate ID if not provided
        if node_id is None:
            node_id = f"node_{uuid.uuid4().hex[:8]}"

        if node_id in self.nodes:
            raise WorkflowValidationError(
                f"Node ID '{node_id}' already exists in workflow"
            )

        # Handle different input types
        if isinstance(node_type, str):
            # String node type name
            self.nodes[node_id] = {"type": node_type, "config": config or {}}
            type_name = node_type
        elif isinstance(node_type, type) and issubclass(node_type, Node):
            # Node class
            self.nodes[node_id] = {
                "type": node_type.__name__,
                "config": config or {},
                "class": node_type,
            }
            type_name = node_type.__name__
        elif hasattr(node_type, "__class__") and issubclass(node_type.__class__, Node):
            # Node instance
            self.nodes[node_id] = {
                "instance": node_type,
                "type": node_type.__class__.__name__,
            }
            type_name = node_type.__class__.__name__
        else:
            raise WorkflowValidationError(
                f"Invalid node type: {type(node_type)}. "
                "Expected: str (node type name), Node class, or Node instance"
            )

        logger.info(f"Added node '{node_id}' of type '{type_name}'")

        # Detect edge nodes
        if self._is_edge_node(type_name):
            self._has_edge_nodes = True
            logger.debug(f"Detected edge node: {type_name}")

        return node_id

    def _is_edge_node(self, node_type: str) -> bool:
        """Check if a node type is an edge node.

        Args:
            node_type: The node type to check

        Returns:
            True if the node is an edge node
        """
        # Use the same logic as EdgeInfrastructure if available
        if self._edge_infrastructure:
            return self._edge_infrastructure.is_edge_node(node_type)

        # Otherwise use local logic
        # Check exact matches and subclasses
        edge_prefixes = ["Edge", "edge"]
        edge_suffixes = [
            "EdgeNode",
            "EdgeDataNode",
            "EdgeStateMachine",
            "EdgeCacheNode",
        ]

        # Exact match
        if node_type in edge_suffixes:
            return True

        # Check if it starts with Edge/edge
        for prefix in edge_prefixes:
            if node_type.startswith(prefix):
                return True

        # Check if it ends with EdgeNode (for custom edge nodes)
        if node_type.endswith("EdgeNode"):
            return True

        return False

    # Fluent API methods for backward compatibility
    def add_node_fluent(
        self, node_id: str, node_class_or_type: Any, **config
    ) -> "WorkflowBuilder":
        """
        DEPRECATED: Fluent API for backward compatibility.
        Use add_node(node_type, node_id, config) instead.

        Args:
            node_id: Node identifier
            node_class_or_type: Node class or type
            **config: Node configuration as keyword arguments

        Returns:
            Self for method chaining
        """
        import warnings

        warnings.warn(
            "Fluent API is deprecated. Use add_node(node_type, node_id, config) instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        if hasattr(node_class_or_type, "__name__"):
            # Node class
            self.add_node(node_class_or_type.__name__, node_id, config)
        else:
            # Assume string type
            self.add_node(str(node_class_or_type), node_id, config)

        return self

    def add_node_instance(self, node_instance: Any, node_id: str | None = None) -> str:
        """
        Add a node instance to the workflow.

        This is a convenience method for adding pre-configured node instances.

        Args:
            node_instance: Pre-configured node instance
            node_id: Unique identifier for this node (auto-generated if not provided)

        Returns:
            Node ID

        Raises:
            WorkflowValidationError: If node_id is already used or instance is invalid
        """
        return self._add_node_instance(node_instance, node_id)

    def add_node_type(
        self,
        node_type: str,
        node_id: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> str:
        """
        Add a node by type name to the workflow.

        This is the original string-based method, provided for clarity and backward compatibility.

        Args:
            node_type: Node type name as string
            node_id: Unique identifier for this node (auto-generated if not provided)
            config: Configuration for the node

        Returns:
            Node ID

        Raises:
            WorkflowValidationError: If node_id is already used
        """
        return self.add_node(node_type, node_id, config)

    def add_connection(
        self, from_node: str, from_output: str, to_node: str, to_input: str
    ) -> "WorkflowBuilder":
        """
        Connect two nodes in the workflow.

        Args:
            from_node: Source node ID
            from_output: Output field from source
            to_node: Target node ID
            to_input: Input field on target

        Raises:
            WorkflowValidationError: If nodes don't exist
            ConnectionError: If connection is invalid
        """
        # Enhanced error messages with helpful suggestions
        if from_node not in self.nodes:
            available_nodes = list(self.nodes.keys())
            similar_nodes = [
                n
                for n in available_nodes
                if from_node.lower() in n.lower() or n.lower() in from_node.lower()
            ]

            error_msg = f"Source node '{from_node}' not found in workflow."
            if available_nodes:
                error_msg += f"\nAvailable nodes: {available_nodes}"
            if similar_nodes:
                error_msg += f"\nDid you mean: {similar_nodes}?"
            error_msg += "\n\nTip: Use workflow.add_node() to create nodes before connecting them."
            error_msg += f"\nExample: workflow.add_node('CSVReaderNode', '{from_node}', {{'file_path': 'data.csv'}})"

            raise WorkflowValidationError(error_msg)

        if to_node not in self.nodes:
            available_nodes = list(self.nodes.keys())
            similar_nodes = [
                n
                for n in available_nodes
                if to_node.lower() in n.lower() or n.lower() in to_node.lower()
            ]

            error_msg = f"Target node '{to_node}' not found in workflow."
            if available_nodes:
                error_msg += f"\nAvailable nodes: {available_nodes}"
            if similar_nodes:
                error_msg += f"\nDid you mean: {similar_nodes}?"
            error_msg += "\n\nTip: Use workflow.add_node() to create nodes before connecting them."
            error_msg += f"\nExample: workflow.add_node('PythonCodeNode', '{to_node}', {{'code': 'result = data'}})"

            raise WorkflowValidationError(error_msg)

        # Self-connection check with helpful message
        if from_node == to_node:
            raise ConnectionError(
                f"Cannot connect node '{from_node}' to itself.\n"
                f"Tip: Consider using intermediate nodes or different port names.\n"
                f"Example: Create a separate processing node between input and output."
            )

        # REFINED: Enhanced duplicate connection detection
        for existing_conn in self.connections:
            if (
                existing_conn["from_node"] == from_node
                and existing_conn["from_output"] == from_output
                and existing_conn["to_node"] == to_node
                and existing_conn["to_input"] == to_input
            ):
                raise ConnectionError(
                    f"Duplicate connection detected: {from_node}.{from_output} -> {to_node}.{to_input}\n"
                    f"This connection already exists in the workflow.\n"
                    f"Tip: Remove the duplicate add_connection() call or use different port names.\n"
                    f"Current connections: {len(self.connections)} total"
                )

        # Enhanced port validation with suggestions
        common_output_ports = [
            "data",
            "result",
            "output",
            "response",
            "content",
            "value",
        ]
        common_input_ports = ["data", "input", "input_data", "content", "value"]

        # Log port usage patterns for debugging
        if from_output not in common_output_ports:
            logger.debug(
                f"Using non-standard output port '{from_output}' on node '{from_node}'"
            )
            logger.debug(f"Common output ports: {common_output_ports}")

        if to_input not in common_input_ports:
            logger.debug(
                f"Using non-standard input port '{to_input}' on node '{to_node}'"
            )
            logger.debug(f"Common input ports: {common_input_ports}")

        # Add connection to list
        connection = {
            "from_node": from_node,
            "from_output": from_output,
            "to_node": to_node,
            "to_input": to_input,
        }
        self.connections.append(connection)

        logger.info(f"Connected '{from_node}.{from_output}' -> '{to_node}.{to_input}'")

        # Provide helpful tips for common connection patterns
        if from_output == to_input == "data":
            logger.debug("Using standard data flow connection pattern")
        elif from_output in ["result", "output"] and to_input in ["data", "input"]:
            logger.debug("Using result-to-input connection pattern")
        else:
            logger.debug(f"Using custom port mapping: {from_output} -> {to_input}")
        return self

    def connect(
        self,
        from_node: str,
        to_node: str,
        mapping: dict = None,
        from_output: str = None,
        to_input: str = None,
    ) -> None:
        """
        Connect two nodes in the workflow with flexible parameter formats.

        This method provides a more intuitive API for connecting nodes and supports
        both simple connections and complex mapping-based connections.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            mapping: Dict mapping from_output to to_input (e.g., {"data": "input"})
            from_output: Single output field (alternative to mapping)
            to_input: Single input field (alternative to mapping)

        Examples:
            # Simple connection
            workflow.connect("node1", "node2", from_output="data", to_input="input")

            # Mapping-based connection
            workflow.connect("node1", "node2", mapping={"data": "input"})

            # Default data flow
            workflow.connect("node1", "node2")  # Uses "data" -> "data"
        """
        if mapping:
            # Handle mapping-based connections
            for from_out, to_in in mapping.items():
                self.add_connection(from_node, from_out, to_node, to_in)
        elif from_output and to_input:
            # Handle explicit parameter connections
            self.add_connection(from_node, from_output, to_node, to_input)
        else:
            # Default data flow
            self.add_connection(from_node, "data", to_node, "data")

    def set_metadata(self, **kwargs) -> "WorkflowBuilder":
        """
        Set workflow metadata.

        Args:
            **kwargs: Metadata key-value pairs

        Returns:
            Self for chaining
        """
        self._metadata.update(kwargs)
        return self

    def add_typed_connection(
        self,
        from_node: str,
        from_output: str,
        to_node: str,
        to_input: str,
        contract: Union[str, ConnectionContract],
        validate_immediately: bool = False,
    ) -> "WorkflowBuilder":
        """
        Add a typed connection with contract validation.

        This is the new contract-based connection method that enforces
        validation contracts on data flowing between nodes.

        Args:
            from_node: Source node ID
            from_output: Output field from source
            to_node: Target node ID
            to_input: Input field on target
            contract: Contract name (string) or ConnectionContract instance
            validate_immediately: Whether to validate contract definitions now

        Returns:
            Self for chaining

        Raises:
            WorkflowValidationError: If contract is invalid or nodes don't exist
            ConnectionError: If connection setup fails

        Example:
            # Using predefined contract
            workflow.add_typed_connection(
                "csv_reader", "data", "processor", "input_data",
                contract="string_data"
            )

            # Using custom contract
            custom_contract = ConnectionContract(
                name="user_data_flow",
                source_schema={"type": "object", "properties": {"id": {"type": "string"}}},
                target_schema={"type": "object", "properties": {"id": {"type": "string"}}},
                security_policies=[SecurityPolicy.NO_PII]
            )
            workflow.add_typed_connection(
                "user_source", "user", "user_processor", "user_data",
                contract=custom_contract
            )
        """
        # Resolve contract
        if isinstance(contract, str):
            contract_obj = self._contract_registry.get(contract)
            if not contract_obj:
                available_contracts = self._contract_registry.list_contracts()
                raise WorkflowValidationError(
                    f"Contract '{contract}' not found. Available contracts: {available_contracts}"
                )
            contract = contract_obj

        # Add the standard connection first
        self.add_connection(from_node, from_output, to_node, to_input)

        # Store the contract for this connection
        connection_id = f"{from_node}.{from_output} → {to_node}.{to_input}"
        self.connection_contracts[connection_id] = contract

        # Immediate validation if requested
        if validate_immediately:
            # Validate that contract schemas are valid
            try:
                if contract.source_schema:
                    from jsonschema import Draft7Validator

                    Draft7Validator.check_schema(contract.source_schema)
                if contract.target_schema:
                    Draft7Validator.check_schema(contract.target_schema)
            except Exception as e:
                raise WorkflowValidationError(
                    f"Invalid contract schema for connection {connection_id}: {e}"
                )

        logger.info(
            f"Added typed connection '{connection_id}' with contract '{contract.name}'"
        )

        return self

    def get_connection_contract(
        self, connection_id: str
    ) -> Optional[ConnectionContract]:
        """
        Get the contract for a specific connection.

        Args:
            connection_id: Connection identifier in format "from.output → to.input"

        Returns:
            ConnectionContract if found, None otherwise
        """
        return self.connection_contracts.get(connection_id)

    def list_connection_contracts(self) -> dict[str, str]:
        """
        List all connection contracts in this workflow.

        Returns:
            Dict mapping connection IDs to contract names
        """
        return {
            conn_id: contract.name
            for conn_id, contract in self.connection_contracts.items()
        }

    def validate_all_contracts(self) -> tuple[bool, list[str]]:
        """
        Validate all connection contracts in the workflow.

        Returns:
            Tuple of (all_valid, list_of_errors)
        """
        errors = []

        for connection_id, contract in self.connection_contracts.items():
            try:
                # Validate contract schemas
                if contract.source_schema:
                    from jsonschema import Draft7Validator

                    Draft7Validator.check_schema(contract.source_schema)
                if contract.target_schema:
                    Draft7Validator.check_schema(contract.target_schema)
            except Exception as e:
                errors.append(f"Contract '{contract.name}' for {connection_id}: {e}")

        return len(errors) == 0, errors

    def add_workflow_inputs(
        self, input_node_id: str, input_mappings: dict
    ) -> "WorkflowBuilder":
        """
        Map workflow-level inputs to a specific node's parameters.

        Args:
            input_node_id: The node that should receive workflow inputs
            input_mappings: Dict mapping workflow input names to node parameter names

        Returns:
            Self for chaining
        """
        if input_node_id not in self.nodes:
            raise WorkflowValidationError(f"Node '{input_node_id}' not found")

        # Store input mappings in metadata
        if "_workflow_inputs" not in self._metadata:
            self._metadata["_workflow_inputs"] = {}
        self._metadata["_workflow_inputs"][input_node_id] = input_mappings
        return self

    def update_node(
        self, node_id: str, config_updates: dict[str, Any]
    ) -> "WorkflowBuilder":
        """
        Update the configuration of an existing node.

        This is essential for enterprise scenarios like:
        - Dynamic environment-specific configuration
        - Runtime parameter injection
        - Security context updates
        - A/B testing and feature flags

        Args:
            node_id: ID of the node to update
            config_updates: Dictionary of configuration updates to apply

        Returns:
            Self for chaining

        Raises:
            WorkflowValidationError: If node doesn't exist
        """
        if node_id not in self.nodes:
            raise WorkflowValidationError(f"Node '{node_id}' not found in workflow")

        # Deep merge the configuration updates
        if "config" not in self.nodes[node_id]:
            self.nodes[node_id]["config"] = {}

        self.nodes[node_id]["config"].update(config_updates)
        return self

    def build(self, workflow_id: str | None = None, **kwargs) -> Workflow:
        """
        Build and return a Workflow instance.

        Args:
            workflow_id: Workflow identifier (auto-generated if not provided)
            **kwargs: Additional metadata (name, description, version, etc.)

        Returns:
            Configured Workflow instance

        Raises:
            WorkflowValidationError: If workflow building fails
        """
        # Generate ID if not provided
        if workflow_id is None:
            workflow_id = str(uuid.uuid4())

        # Prepare metadata
        metadata = self._metadata.copy()
        metadata.update(kwargs)
        if "name" not in metadata:
            metadata["name"] = f"Workflow-{workflow_id[:8]}"

        # Get basic workflow properties
        name = metadata.pop("name")
        description = metadata.pop("description", "")
        version = metadata.pop("version", "1.0.0")
        author = metadata.pop("author", "")

        # Initialize edge infrastructure if needed
        if self._has_edge_nodes and not self._edge_infrastructure:
            from kailash.workflow.edge_infrastructure import EdgeInfrastructure

            self._edge_infrastructure = EdgeInfrastructure(self.edge_config)
            logger.info("Initialized edge infrastructure for workflow")

        # Create workflow
        workflow = Workflow(
            workflow_id=workflow_id,
            name=name,
            description=description,
            version=version,
            author=author,
            metadata=metadata,
        )

        # Store edge infrastructure reference in workflow metadata if present
        if self._edge_infrastructure:
            workflow.metadata["_edge_infrastructure"] = self._edge_infrastructure

        # Validate parameter declarations before building workflow
        param_issues = self.validate_parameter_declarations(warn_on_issues=True)

        # Check for critical parameter errors that should block workflow creation
        critical_errors = [
            issue for issue in param_issues if issue.severity == IssueSeverity.ERROR
        ]
        if critical_errors:
            error_messages = [
                f"{issue.node_id}: {issue.message}" for issue in critical_errors
            ]
            raise WorkflowValidationError(
                "Cannot build workflow due to parameter declaration errors:\n"
                + "\n".join(f"  - {msg}" for msg in error_messages)
                + "\n\nSee: sdk-users/7-gold-standards/enterprise-parameter-passing-gold-standard.md"
            )

        # Add nodes to workflow
        for node_id, node_info in self.nodes.items():
            try:
                if "instance" in node_info:
                    # Node instance was provided
                    workflow.add_node(
                        node_id=node_id, node_or_type=node_info["instance"]
                    )
                elif "class" in node_info:
                    # Node class was provided
                    node_class = node_info["class"]
                    node_config = node_info.get("config", {})

                    # Inject edge infrastructure if this is an edge node
                    if self._edge_infrastructure and self._is_edge_node(
                        node_class.__name__
                    ):
                        node_config["_edge_infrastructure"] = self._edge_infrastructure
                        logger.debug(
                            f"Injected edge infrastructure into {node_class.__name__}"
                        )

                    workflow.add_node(
                        node_id=node_id, node_or_type=node_class, **node_config
                    )
                else:
                    # String node type
                    node_type = node_info["type"]
                    node_config = node_info.get("config", {})

                    # Inject edge infrastructure if this is an edge node
                    if self._edge_infrastructure and self._is_edge_node(node_type):
                        node_config["_edge_infrastructure"] = self._edge_infrastructure
                        logger.debug(f"Injected edge infrastructure into {node_type}")

                    workflow.add_node(
                        node_id=node_id, node_or_type=node_type, **node_config
                    )
            except Exception as e:
                raise WorkflowValidationError(
                    f"Failed to add node '{node_id}' to workflow: {e}"
                ) from e

        # Add connections to workflow
        for conn in self.connections:
            try:
                from_node = conn["from_node"]
                from_output = conn["from_output"]
                to_node = conn["to_node"]
                to_input = conn["to_input"]

                # Add the connection to workflow
                workflow._add_edge_internal(from_node, from_output, to_node, to_input)
            except Exception as e:
                raise WorkflowValidationError(
                    f"Failed to connect '{from_node}' to '{to_node}': {e}"
                ) from e

        # Parameter injection: Find nodes without incoming connections and inject parameters
        if self.workflow_parameters:
            nodes_with_inputs = set()
            for conn in self.connections:
                if not conn.get("is_workflow_input"):
                    nodes_with_inputs.add(conn["to_node"])

            nodes_without_inputs = set(self.nodes.keys()) - nodes_with_inputs

            # For each node without inputs, check if it needs workflow parameters
            for node_id in nodes_without_inputs:
                node_info = self.nodes[node_id]
                node_instance = workflow.get_node(node_id)

                if hasattr(node_instance, "get_parameters"):
                    params = node_instance.get_parameters()

                    # Check which required parameters are missing from config
                    for param_name, param_def in params.items():
                        if param_def.required and param_name not in node_info["config"]:
                            # Check if this parameter should come from workflow parameters
                            if param_name in self.workflow_parameters:
                                # Add to node config
                                node_info["config"][param_name] = (
                                    self.workflow_parameters[param_name]
                                )
                            elif node_id in self.parameter_mappings:
                                # Check parameter mappings
                                mapping = self.parameter_mappings[node_id]
                                if param_name in mapping:
                                    workflow_param = mapping[param_name]
                                    if workflow_param in self.workflow_parameters:
                                        node_info["config"][param_name] = (
                                            self.workflow_parameters[workflow_param]
                                        )

        # Store workflow parameters and contracts in metadata for runtime reference
        workflow.metadata["workflow_parameters"] = self.workflow_parameters
        workflow.metadata["parameter_mappings"] = self.parameter_mappings
        workflow.metadata["connection_contracts"] = {
            conn_id: contract.to_dict()
            for conn_id, contract in self.connection_contracts.items()
        }

        logger.info(
            f"Built workflow '{workflow_id}' with "
            f"{len(self.nodes)} nodes and {len(self.connections)} connections"
        )
        return workflow

    def set_workflow_parameters(self, **parameters) -> "WorkflowBuilder":
        """
        Set default parameters that will be passed to all nodes.

        Args:
            **parameters: Key-value pairs of workflow-level parameters

        Returns:
            Self for chaining
        """
        self.workflow_parameters.update(parameters)
        return self

    def add_parameter_mapping(
        self, node_id: str, mappings: dict[str, str]
    ) -> "WorkflowBuilder":
        """
        Add parameter mappings for a specific node.

        Args:
            node_id: Node to configure
            mappings: Dict mapping workflow param names to node param names

        Returns:
            Self for chaining
        """
        if node_id not in self.parameter_mappings:
            self.parameter_mappings[node_id] = {}
        self.parameter_mappings[node_id].update(mappings)
        return self

    def add_input_connection(
        self, to_node: str, to_input: str, from_workflow_param: str
    ) -> "WorkflowBuilder":
        """
        Connect a workflow parameter directly to a node input.

        Args:
            to_node: Target node ID
            to_input: Input parameter name on the node
            from_workflow_param: Workflow parameter name

        Returns:
            Self for chaining
        """
        # Add a special connection type for workflow inputs
        connection = {
            "from_node": "__workflow_input__",
            "from_output": from_workflow_param,
            "to_node": to_node,
            "to_input": to_input,
            "is_workflow_input": True,
        }
        self.connections.append(connection)
        return self

    def clear(self) -> "WorkflowBuilder":
        """
        Clear builder state.

        Returns:
            Self for chaining
        """
        self.nodes = {}
        self.connections = []
        self._metadata = {}
        self.workflow_parameters = {}
        self.parameter_mappings = {}
        self.connection_contracts = {}
        return self

    @classmethod
    def from_dict(cls, config: dict[str, Any]) -> "WorkflowBuilder":
        """
        Create builder from dictionary configuration.

        Args:
            config: Dictionary with workflow configuration

        Returns:
            Configured WorkflowBuilder instance

        Raises:
            WorkflowValidationError: If configuration is invalid
        """
        builder = cls()

        # Extract metadata
        for key, value in config.items():
            if key not in ["nodes", "connections"]:
                builder._metadata[key] = value

        # Add nodes - handle both dict and list formats
        nodes_config = config.get("nodes", [])

        if isinstance(nodes_config, dict):
            # Dict format: {node_id: {type: "...", parameters: {...}}}
            for node_id, node_config in nodes_config.items():
                node_type = node_config.get("type")

                # Handle parameter naming inconsistencies - prefer 'parameters' over 'config'
                if "parameters" in node_config:
                    node_params = node_config["parameters"]
                elif "config" in node_config:
                    node_params = node_config["config"]
                else:
                    node_params = {}

                # Ensure node_params is a dictionary
                if not isinstance(node_params, dict):
                    logger.warning(
                        f"Node '{node_id}' parameters must be a dict, got {type(node_params)}. Using empty dict."
                    )
                    node_params = {}

                if not node_type:
                    raise WorkflowValidationError(
                        f"Node type is required for node '{node_id}'"
                    )

                builder.add_node(node_type, node_id, node_params)
        else:
            # List format: [{id: "...", type: "...", config: {...}}]
            for node_config in nodes_config:
                node_id = node_config.get("id")
                node_type = node_config.get("type")

                # Handle parameter naming inconsistencies - prefer 'parameters' over 'config'
                if "parameters" in node_config:
                    node_params = node_config["parameters"]
                elif "config" in node_config:
                    node_params = node_config["config"]
                else:
                    node_params = {}

                # Ensure node_params is a dictionary
                if not isinstance(node_params, dict):
                    logger.warning(
                        f"Node '{node_id}' parameters must be a dict, got {type(node_params)}. Using empty dict."
                    )
                    node_params = {}

                if not node_id:
                    raise WorkflowValidationError("Node ID is required")
                if not node_type:
                    raise WorkflowValidationError(
                        f"Node type is required for node '{node_id}'"
                    )

                builder.add_node(node_type, node_id, node_params)

        # Add connections - handle both full and simple formats
        for conn in config.get("connections", []):
            # Try full format first: {from_node, from_output, to_node, to_input}
            from_node = conn.get("from_node")
            from_output = conn.get("from_output")
            to_node = conn.get("to_node")
            to_input = conn.get("to_input")

            # Handle simple format: {from, to} with default outputs/inputs
            if not from_node:
                from_node = conn.get("from")
                from_output = conn.get("from_output", "result")  # Default output
            if not to_node:
                to_node = conn.get("to")
                to_input = conn.get("to_input", "input")  # Default input

            if not all([from_node, to_node]):
                raise WorkflowValidationError(
                    f"Invalid connection: missing from_node and to_node. Connection data: {conn}"
                )

            # Use defaults if not specified
            from_output = from_output or "result"
            to_input = to_input or "input"

            builder.add_connection(from_node, from_output, to_node, to_input)

        return builder
