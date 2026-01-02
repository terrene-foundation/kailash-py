"""Workflow DAG implementation for the Kailash SDK."""

import inspect
import json
import logging
import uuid
import warnings
from datetime import UTC, datetime
from typing import Any

import networkx as nx
import yaml
from kailash.nodes.base import Node
from pydantic import BaseModel, Field, ValidationError

try:
    # For normal runtime, use the actual registry
    from kailash.nodes.base import NodeRegistry
except ImportError:
    # For tests, use the mock registry
    from kailash.workflow.mock_registry import MockRegistry as NodeRegistry

from kailash.sdk_exceptions import (
    ConnectionError,
    ExportException,
    NodeConfigurationError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.workflow.state import WorkflowStateWrapper

logger = logging.getLogger(__name__)


class NodeInstance(BaseModel):
    """Instance of a node in a workflow."""

    node_id: str = Field(..., description="Unique identifier for this instance")
    node_type: str = Field(..., description="Type of node")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Node configuration"
    )
    position: tuple[float, float] = Field(default=(0, 0), description="Visual position")


class Connection(BaseModel):
    """Connection between two nodes in a workflow."""

    source_node: str = Field(..., description="Source node ID")
    source_output: str = Field(..., description="Output field from source")
    target_node: str = Field(..., description="Target node ID")
    target_input: str = Field(..., description="Input field on target")


class CyclicConnection(Connection):
    """Extended connection supporting cycle metadata."""

    cycle: bool = Field(
        default=False, description="Whether this connection creates a cycle"
    )
    max_iterations: int | None = Field(
        default=None, description="Maximum cycle iterations"
    )
    convergence_check: str | None = Field(
        default=None, description="Convergence condition expression"
    )
    cycle_id: str | None = Field(
        default=None, description="Logical cycle group identifier"
    )
    timeout: float | None = Field(default=None, description="Cycle timeout in seconds")
    memory_limit: int | None = Field(default=None, description="Memory limit in MB")
    condition: str | None = Field(
        default=None, description="Conditional cycle routing expression"
    )
    parent_cycle: str | None = Field(
        default=None, description="Parent cycle for nested cycles"
    )


class Workflow:
    """Represents a workflow DAG of nodes."""

    def __init__(
        self,
        workflow_id: str,
        name: str,
        description: str = "",
        version: str = "1.0.0",
        author: str = "",
        metadata: dict[str, Any] | None = None,
    ):
        """Initialize a workflow.

        Args:
            workflow_id: Unique workflow identifier
            name: Workflow name
            description: Workflow description
            version: Workflow version
            author: Workflow author
            metadata: Additional metadata

        Raises:
            WorkflowValidationError: If workflow initialization fails
        """
        self.workflow_id = workflow_id
        self.name = name
        self.description = description
        self.version = version
        self.author = author
        self.metadata = metadata or {}

        # Add standard metadata
        if "author" not in self.metadata and author:
            self.metadata["author"] = author
        if "version" not in self.metadata and version:
            self.metadata["version"] = version
        if "created_at" not in self.metadata:
            self.metadata["created_at"] = datetime.now(UTC).isoformat()

        # Create directed graph for the workflow
        self.graph = nx.DiGraph()

        # Storage for node instances and node metadata
        self._node_instances = {}  # Maps node_id to Node instances
        self.nodes = {}  # Maps node_id to NodeInstance metadata objects
        self.connections = []  # List of Connection objects

        logger.info(f"Created workflow '{name}' (ID: {workflow_id})")

    def _create_node_instance(
        self, node_class: type, node_id: str, config: dict
    ) -> Node:
        """Create a node instance with proper parameter mapping.

        Handles the inconsistency between nodes that expect 'name' vs 'id' parameters.
        This is a core SDK improvement to standardize node constructor patterns.

        Args:
            node_class: The node class to instantiate
            node_id: The node identifier from workflow config
            config: Node configuration parameters

        Returns:
            Instantiated node instance

        Raises:
            NodeConfigurationError: If node creation fails with detailed diagnostics
        """
        # Inspect the node constructor signature
        sig = inspect.signature(node_class.__init__)
        params = list(sig.parameters.keys())

        try:
            # Handle different constructor patterns
            if "name" in params and "_node_id" not in params:
                # Node expects 'name' parameter (like PythonCodeNode)
                if "name" not in config:
                    config = config.copy()  # Don't modify original
                    config["name"] = node_id
                return node_class(**config)
            elif "_node_id" in params:
                # Node expects '_node_id' parameter (namespace-separated metadata)
                return node_class(_node_id=node_id, **config)
            else:
                # Fallback: try both patterns
                try:
                    return node_class(_node_id=node_id, **config)
                except TypeError:
                    # Try with name parameter
                    config = config.copy()
                    config["name"] = node_id
                    return node_class(**config)

        except TypeError as e:
            error_msg = str(e)
            if "missing 1 required positional argument: 'name'" in error_msg:
                raise NodeConfigurationError(
                    f"Node '{node_class.__name__}' requires 'name' parameter. "
                    f"Expected constructor signature includes 'name'. "
                    f"Config provided: {list(config.keys())}. "
                    f"Add 'name': '{node_id}' to node config."
                ) from e
            elif "unexpected keyword argument" in error_msg:
                raise NodeConfigurationError(
                    f"Node '{node_class.__name__}' received unexpected parameters. "
                    f"Constructor signature: {sig}. "
                    f"Config provided: {list(config.keys())}."
                ) from e
            else:
                raise NodeConfigurationError(
                    f"Failed to create node '{node_id}' of type '{node_class.__name__}': {e}. "
                    f"Constructor signature: {sig}. Config: {config}"
                ) from e

    def add_node(self, node_id: str, node_or_type: Any, **config) -> None:
        """Add a node to the workflow.

        Args:
            node_id: Unique identifier for this node instance
            node_or_type: Either a Node instance, Node class, or node type name
            **config: Configuration for the node

        Raises:
            WorkflowValidationError: If node is invalid
            NodeConfigurationError: If node configuration fails
        """
        if node_id in self.nodes:
            raise WorkflowValidationError(
                f"Node '{node_id}' already exists in workflow. "
                f"Existing nodes: {list(self.nodes.keys())}"
            )

        try:
            # Handle different input types
            if isinstance(node_or_type, str):
                # Node type name provided
                node_class = NodeRegistry.get(node_or_type)
                node_instance = self._create_node_instance(node_class, node_id, config)
                node_type = node_or_type
            elif isinstance(node_or_type, type) and issubclass(node_or_type, Node):
                # Node class provided
                node_instance = self._create_node_instance(
                    node_or_type, node_id, config
                )
                node_type = node_or_type.__name__
            elif isinstance(node_or_type, Node):
                # Node instance provided
                node_instance = node_or_type
                node_instance.id = node_id
                node_type = node_instance.__class__.__name__
                # Update config - handle nested config case
                if "config" in node_instance.config and isinstance(
                    node_instance.config["config"], dict
                ):
                    # If config is nested, extract it
                    actual_config = node_instance.config["config"]
                    node_instance.config.update(actual_config)
                    # Remove the nested config key
                    del node_instance.config["config"]
                # Now update with provided config
                node_instance.config.update(config)
                node_instance._validate_config()
            else:
                raise WorkflowValidationError(
                    f"Invalid node type: {type(node_or_type)}. "
                    "Expected: str (node type name), Node class, or Node instance"
                )
        except NodeConfigurationError:
            # Re-raise configuration errors with additional context
            raise
        except Exception as e:
            raise NodeConfigurationError(
                f"Failed to create node '{node_id}' of type '{node_or_type}': {e}"
            ) from e

        # Store node instance and metadata
        try:
            # Use the node instance's actual config, which includes both original config and any updates
            actual_config = node_instance.config.copy()
            node_instance_data = NodeInstance(
                node_id=node_id,
                node_type=node_type,
                config=actual_config,
                position=(len(self.nodes) * 150, 100),
            )
            self.nodes[node_id] = node_instance_data
        except ValidationError as e:
            raise WorkflowValidationError(f"Invalid node instance data: {e}") from e

        self._node_instances[node_id] = node_instance

        # Add to graph with actual config
        self.graph.add_node(
            node_id, node=node_instance, type=node_type, config=actual_config
        )
        logger.info(f"Added node '{node_id}' of type '{node_type}'")

    def _add_node_internal(
        self, node_id: str, node_type: str, config: dict[str, Any] | None = None
    ) -> None:
        """Add a node to the workflow (internal method).

        Args:
            node_id: Node identifier
            node_type: Node type name
            config: Node configuration
        """
        # This method is used by WorkflowBuilder and from_dict
        config = config or {}
        self.add_node(node_id=node_id, node_or_type=node_type, **config)

    def connect(
        self,
        source_node: str,
        target_node: str,
        mapping: dict[str, str] | None = None,
        cycle: bool = False,
        max_iterations: int | None = None,
        convergence_check: str | None = None,
        cycle_id: str | None = None,
        timeout: float | None = None,
        memory_limit: int | None = None,
        condition: str | None = None,
        parent_cycle: str | None = None,
    ) -> None:
        """Connect two nodes in the workflow.

        Args:
            source_node: Source node ID
            target_node: Target node ID
            mapping: Dict mapping source outputs to target inputs
            cycle: Whether this connection creates a cycle
            max_iterations: Maximum cycle iterations (required if cycle=True)
            convergence_check: Convergence condition expression
            cycle_id: Logical cycle group identifier
            timeout: Cycle timeout in seconds
            memory_limit: Memory limit in MB
            condition: Conditional cycle routing expression
            parent_cycle: Parent cycle for nested cycles

        Raises:
            ConnectionError: If connection is invalid
            WorkflowValidationError: If nodes don't exist or cycle parameters invalid
        """
        if source_node not in self.nodes:
            available_nodes = ", ".join(self.nodes.keys())
            raise WorkflowValidationError(
                f"Source node '{source_node}' not found in workflow. "
                f"Available nodes: {available_nodes}"
            )
        if target_node not in self.nodes:
            available_nodes = ", ".join(self.nodes.keys())
            raise WorkflowValidationError(
                f"Target node '{target_node}' not found in workflow. "
                f"Available nodes: {available_nodes}"
            )

        # Self-connection check (allow for cycles)
        if source_node == target_node and not cycle:
            raise ConnectionError(
                f"Cannot connect node '{source_node}' to itself unless it's a cycle"
            )

        # Validate cycle parameters and issue deprecation warning
        if cycle:
            # Issue deprecation warning for cycle usage via connect()
            # Skip warning if called from CycleBuilder (check stack)
            import inspect

            frame = inspect.currentframe()
            caller_frame = frame.f_back if frame else None
            caller_filename = caller_frame.f_code.co_filename if caller_frame else ""

            # Only warn if NOT called from CycleBuilder
            if "cycle_builder.py" not in caller_filename:
                warnings.warn(
                    "Using workflow.connect() with cycle=True is deprecated and will be removed in v0.2.0. "
                    "Use the new CycleBuilder API instead:\n"
                    "  workflow.create_cycle('cycle_name')\\\n"
                    "    .connect(source_node, target_node)\\\n"
                    "    .max_iterations(N)\\\n"
                    "    .converge_when('condition')\\\n"
                    "    .build()\n"
                    "See Phase 5 API documentation for details.",
                    DeprecationWarning,
                    stacklevel=2,
                )

            # Import enhanced exceptions for better error messaging
            try:
                from kailash.workflow.cycle_exceptions import CycleConfigurationError

                if max_iterations is None and convergence_check is None:
                    raise CycleConfigurationError(
                        "Cycle connections must specify either max_iterations or convergence_check",
                        error_code="CYCLE_CONFIG_001",
                        suggestions=[
                            "Add max_iterations parameter (recommended: 10-100)",
                            "Add convergence_check expression (e.g., 'error < 0.01')",
                            "Consider using the new CycleBuilder API for better validation",
                        ],
                    )
                if max_iterations is not None and max_iterations <= 0:
                    raise CycleConfigurationError(
                        f"max_iterations must be positive, got {max_iterations}",
                        error_code="CYCLE_CONFIG_002",
                        invalid_params={"max_iterations": max_iterations},
                        suggestions=[
                            "Use 10-100 iterations for quick convergence",
                            "Use 100-1000 iterations for complex optimization",
                        ],
                    )
                if timeout is not None and timeout <= 0:
                    raise CycleConfigurationError(
                        f"timeout must be positive, got {timeout}",
                        error_code="CYCLE_CONFIG_003",
                        invalid_params={"timeout": timeout},
                        suggestions=[
                            "Use 30-300 seconds for most cycles",
                            "Use longer timeouts for complex processing",
                        ],
                    )
                if memory_limit is not None and memory_limit <= 0:
                    raise CycleConfigurationError(
                        f"memory_limit must be positive, got {memory_limit}",
                        error_code="CYCLE_CONFIG_004",
                        invalid_params={"memory_limit": memory_limit},
                        suggestions=[
                            "Use 100-1000 MB for most cycles",
                            "Increase limit for data-intensive processing",
                        ],
                    )
            except ImportError:
                # Fallback to old exceptions if enhanced ones aren't available
                if max_iterations is None and convergence_check is None:
                    raise WorkflowValidationError(
                        "Cycle connections must specify either max_iterations or convergence_check"
                    )
                if max_iterations is not None and max_iterations <= 0:
                    raise WorkflowValidationError("max_iterations must be positive")
                if timeout is not None and timeout <= 0:
                    raise WorkflowValidationError("timeout must be positive")
                if memory_limit is not None and memory_limit <= 0:
                    raise WorkflowValidationError("memory_limit must be positive")

        # Default mapping if not provided
        if mapping is None:
            mapping = {"output": "input"}

        # Check for existing connections (allow multiple cycles with different IDs)
        existing_connections = [
            c
            for c in self.connections
            if c.source_node == source_node and c.target_node == target_node
        ]
        # Allow multiple connections between same nodes for different mappings
        # Only reject if it's a duplicate mapping, not just any existing connection
        if existing_connections and not cycle:
            # Check if any of the new mappings already exist
            existing_mappings = set()
            for conn in existing_connections:
                existing_mappings.add((conn.source_output, conn.target_input))

            for source_output, target_input in mapping.items():
                if (source_output, target_input) in existing_mappings:
                    raise ConnectionError(
                        f"Duplicate connection already exists: '{source_node}.{source_output}' -> '{target_node}.{target_input}'. "
                        f"Existing mappings: {[c.model_dump() for c in existing_connections]}"
                    )

        # Create connections (store in self.connections list)
        for source_output, target_input in mapping.items():
            try:
                if cycle:
                    # Create cyclic connection with all metadata
                    connection = CyclicConnection(
                        source_node=source_node,
                        source_output=source_output,
                        target_node=target_node,
                        target_input=target_input,
                        cycle=cycle,
                        max_iterations=max_iterations,
                        convergence_check=convergence_check,
                        cycle_id=cycle_id,
                        timeout=timeout,
                        memory_limit=memory_limit,
                        condition=condition,
                        parent_cycle=parent_cycle,
                    )
                else:
                    # Create regular connection
                    connection = Connection(
                        source_node=source_node,
                        source_output=source_output,
                        target_node=target_node,
                        target_input=target_input,
                    )
            except ValidationError as e:
                raise ConnectionError(f"Invalid connection data: {e}") from e

            self.connections.append(connection)

        # FIXED: Add edge to graph ONCE with the complete mapping
        edge_data = {
            "mapping": mapping,  # Complete mapping dictionary
        }

        # For backward compatibility, store single mappings as strings
        # and multi-mappings as lists
        if len(mapping) == 1:
            # Single mapping - store as strings for backward compatibility
            edge_data["from_output"] = list(mapping.keys())[0]
            edge_data["to_input"] = list(mapping.values())[0]
        else:
            # Multiple mappings - store as lists
            edge_data["from_output"] = list(mapping.keys())
            edge_data["to_input"] = list(mapping.values())

        # Add cycle metadata to edge
        if cycle:
            edge_data.update(
                {
                    "cycle": cycle,
                    "max_iterations": max_iterations,
                    "convergence_check": convergence_check,
                    "cycle_id": cycle_id,
                    "timeout": timeout,
                    "memory_limit": memory_limit,
                    "condition": condition,
                    "parent_cycle": parent_cycle,
                }
            )

        # CRITICAL FIX: Merge edge data for multiple connections between same nodes
        # Check if edge already exists and merge mappings
        existing_edge_data = None
        if self.graph.has_edge(source_node, target_node):
            existing_edge_data = self.graph.get_edge_data(source_node, target_node)

        if existing_edge_data and "mapping" in existing_edge_data:
            # Merge with existing mapping
            merged_mapping = existing_edge_data["mapping"].copy()
            merged_mapping.update(mapping)
            edge_data = {
                "mapping": merged_mapping,  # Merged mapping dictionary
            }

            # Update backward compatibility fields
            if len(merged_mapping) == 1:
                edge_data["from_output"] = list(merged_mapping.keys())[0]
                edge_data["to_input"] = list(merged_mapping.values())[0]
            else:
                edge_data["from_output"] = list(merged_mapping.keys())
                edge_data["to_input"] = list(merged_mapping.values())

            # Preserve any existing cycle metadata
            if existing_edge_data.get("cycle"):
                edge_data.update(
                    {
                        k: v
                        for k, v in existing_edge_data.items()
                        if k not in ["mapping", "from_output", "to_input"]
                    }
                )
        else:
            # No existing edge or no mapping, use new mapping as-is
            # (edge_data was already set above)
            pass

        # Add cycle metadata to edge if this is a cycle connection
        if cycle:
            edge_data.update(
                {
                    "cycle": cycle,
                    "max_iterations": max_iterations,
                    "convergence_check": convergence_check,
                    "cycle_id": cycle_id,
                    "timeout": timeout,
                    "memory_limit": memory_limit,
                    "condition": condition,
                    "parent_cycle": parent_cycle,
                }
            )

        # Add or update the edge with merged data
        self.graph.add_edge(source_node, target_node, **edge_data)

        # Enhanced logging for cycles
        if cycle:
            cycle_info = f" (CYCLE: id={cycle_id}, max_iter={max_iterations}, conv={convergence_check})"
            logger.info(
                f"Connected '{source_node}' to '{target_node}' with mapping: {mapping}{cycle_info}"
            )
        else:
            logger.info(
                f"Connected '{source_node}' to '{target_node}' with mapping: {mapping}"
            )

    def create_cycle(self, cycle_id: str | None = None):
        """
        Create a new CycleBuilder for intuitive cycle configuration.

        This method provides the entry point to the enhanced CycleBuilder API,
        which offers a fluent, chainable interface for creating cyclic workflow
        connections with better developer experience than the raw connect() method.

        Design Philosophy:
            Replaces verbose parameter-heavy cycle creation with an intuitive
            builder pattern that guides developers through cycle configuration
            with IDE auto-completion and method chaining.

        Upstream Dependencies:
            - Requires source and target nodes to exist in workflow
            - Uses existing connection validation and cycle infrastructure

        Downstream Consumers:
            - CycleBuilder.build() calls back to workflow.connect() internally
            - CyclicWorkflowExecutor for execution of configured cycles
            - Cycle debugging and visualization tools

        Usage Patterns:
            1. Simple cycles: create_cycle().connect().max_iterations().build()
            2. Convergence-based: create_cycle().connect().converge_when().build()
            3. Complex cycles: Full builder chain with timeouts and conditions

        Implementation Details:
            Creates a CycleBuilder instance that accumulates configuration
            through method chaining, then applies it via workflow.connect()
            when build() is called. Maintains full backward compatibility.

        Error Handling:
            - WorkflowValidationError: If cycle_id conflicts with existing cycles
            - CycleConfigurationError: Raised by CycleBuilder for invalid config

        Side Effects:
            Creates CycleBuilder instance but does not modify workflow until
            build() is called. No validation occurs until build() time.

        Args:
            cycle_id (Optional[str]): Optional identifier for the cycle group.
                If None, cycles are grouped by connection pattern.
                Used for nested cycles and debugging identification.

        Returns:
            CycleBuilder: Fluent builder instance for configuring the cycle

        Raises:
            ImportError: If CycleBuilder module cannot be imported

        Example:
            >>> # Basic cycle with iteration limit
            >>> workflow.create_cycle("optimization") \\
            ...     .connect("processor", "evaluator") \\
            ...     .max_iterations(50) \\
            ...     .build()

            >>> # Convergence-based cycle with timeout
            >>> workflow.create_cycle("quality_improvement") \\
            ...     .connect("cleaner", "validator", {"result": "data"}) \\
            ...     .converge_when("quality > 0.95") \\
            ...     .timeout(300) \\
            ...     .build()

            >>> # Nested cycle with memory limit
            >>> workflow.create_cycle("inner_optimization") \\
            ...     .connect("fine_tuner", "evaluator") \\
            ...     .max_iterations(10) \\
            ...     .nested_in("outer_optimization") \\
            ...     .memory_limit(1024) \\
            ...     .build()
        """
        try:
            from kailash.workflow.cycle_builder import CycleBuilder
        except ImportError as e:
            raise ImportError(
                "CycleBuilder not available. Ensure kailash.workflow.cycle_builder is installed."
            ) from e

        return CycleBuilder(workflow=self, cycle_id=cycle_id)

    def _add_edge_internal(
        self, from_node: str, from_output: str, to_node: str, to_input: str
    ) -> None:
        """Add an edge between nodes (internal method).

        Args:
            from_node: Source node ID
            from_output: Output field from source
            to_node: Target node ID
            to_input: Input field on target
        """
        # This method is used by WorkflowBuilder and from_dict
        self.connect(
            source_node=from_node, target_node=to_node, mapping={from_output: to_input}
        )

    def get_node(self, node_id: str) -> Node | None:
        """Get node instance by ID.

        Args:
            node_id: Node identifier

        Returns:
            Node instance or None if not found
        """
        if node_id not in self.graph.nodes:
            return None

        # First try to get from graph (for test compatibility)
        graph_node = self.graph.nodes[node_id].get("node")
        if graph_node:
            return graph_node

        # Fallback to _node_instances
        return self._node_instances.get(node_id)

    def separate_dag_and_cycle_edges(self) -> tuple[list[tuple], list[tuple]]:
        """Separate DAG edges from cycle edges.

        Returns:
            Tuple of (dag_edges, cycle_edges) where each edge is (source, target, data)
        """
        dag_edges = []
        cycle_edges = []

        for source, target, data in self.graph.edges(data=True):
            if data.get("cycle", False):
                cycle_edges.append((source, target, data))
            else:
                dag_edges.append((source, target, data))

        return dag_edges, cycle_edges

    def get_cycle_groups(self) -> dict[str, list[tuple]]:
        """Get cycle edges grouped by cycle_id with enhanced multi-node cycle detection.

        For multi-node cycles like A → B → C → A where only C → A is marked as cycle,
        this method identifies all nodes (A, B, C) that are part of the same strongly
        connected component and groups them together.

        Returns:
            Dict mapping cycle_id to list of cycle edges
        """
        cycle_groups = {}
        _, cycle_edges = self.separate_dag_and_cycle_edges()

        # First pass: group by cycle_id, using edge-based IDs when not specified
        for source, target, data in cycle_edges:
            # Generate unique cycle_id based on edge if not provided
            cycle_id = data.get("cycle_id")
            if cycle_id is None:
                # Create unique ID based on the cycle edge
                cycle_id = f"cycle_{source}_{target}"

            if cycle_id not in cycle_groups:
                cycle_groups[cycle_id] = []
            cycle_groups[cycle_id].append((source, target, data))

        # Second pass: enhance cycle groups with strongly connected components
        enhanced_groups = {}
        for cycle_id, edges in cycle_groups.items():
            # Find all nodes that are part of strongly connected components
            # containing any cycle edge nodes
            cycle_nodes = set()
            for source, target, data in edges:
                cycle_nodes.add(source)
                cycle_nodes.add(target)

            # Find strongly connected components in the full graph
            try:
                # Get all strongly connected components
                sccs = list(nx.strongly_connected_components(self.graph))

                # Find which SCC contains our cycle nodes
                target_scc = None
                for scc in sccs:
                    if any(node in scc for node in cycle_nodes):
                        target_scc = scc
                        break

                if target_scc and len(target_scc) > 1:
                    # Multi-node cycle detected - include all SCC nodes
                    logger.debug(
                        f"Enhanced cycle detection for {cycle_id}: {cycle_nodes} → {target_scc}"
                    )

                    # Add edges for all nodes in the SCC that are connected
                    enhanced_edges = list(edges)  # Start with original cycle edges
                    for node in target_scc:
                        for successor in self.graph.successors(node):
                            if successor in target_scc:
                                # This is an edge within the SCC
                                edge_data = self.graph.get_edge_data(node, successor)
                                if not edge_data.get("cycle", False):
                                    # Add as a synthetic cycle edge for execution planning
                                    synthetic_edge_data = edge_data.copy()
                                    synthetic_edge_data.update(
                                        {
                                            "cycle": True,
                                            "cycle_id": cycle_id,
                                            "synthetic": True,  # Mark as synthetic for reference
                                            "max_iterations": edges[0][2].get(
                                                "max_iterations"
                                            ),
                                            "convergence_check": edges[0][2].get(
                                                "convergence_check"
                                            ),
                                            "timeout": edges[0][2].get("timeout"),
                                            "memory_limit": edges[0][2].get(
                                                "memory_limit"
                                            ),
                                        }
                                    )
                                    enhanced_edges.append(
                                        (node, successor, synthetic_edge_data)
                                    )

                    enhanced_groups[cycle_id] = enhanced_edges
                else:
                    # Single-node cycle or no SCC found
                    enhanced_groups[cycle_id] = edges

            except Exception as e:
                logger.warning(f"Could not enhance cycle detection for {cycle_id}: {e}")
                # Fall back to original behavior
                enhanced_groups[cycle_id] = edges

        return enhanced_groups

    def has_cycles(self) -> bool:
        """Check if the workflow contains any cycle connections.

        Returns:
            True if workflow has cycle connections, False otherwise
        """
        _, cycle_edges = self.separate_dag_and_cycle_edges()
        return len(cycle_edges) > 0

    def get_execution_order(self) -> list[str]:
        """Get topological execution order for nodes, handling cycles gracefully.

        Returns:
            List of node IDs in execution order

        Raises:
            WorkflowValidationError: If workflow contains unmarked cycles
        """
        # Create a copy of the graph without cycle edges for topological sort
        dag_edges, cycle_edges = self.separate_dag_and_cycle_edges()

        # Create DAG-only graph
        dag_graph = nx.DiGraph()
        dag_graph.add_nodes_from(self.graph.nodes(data=True))
        for source, target, data in dag_edges:
            dag_graph.add_edge(source, target, **data)

        try:
            # Get topological order for DAG portion
            return list(nx.topological_sort(dag_graph))
        except nx.NetworkXUnfeasible:
            # Check if there are unmarked cycles
            cycles = list(nx.simple_cycles(dag_graph))
            if cycles:
                raise WorkflowValidationError(
                    f"Workflow contains unmarked cycles: {cycles}. "
                    "Mark cycle connections with cycle=True or remove circular dependencies."
                )
            else:
                # This shouldn't happen, but handle gracefully
                raise WorkflowValidationError("Unable to determine execution order")

    def validate(self, runtime_parameters: dict[str, Any] | None = None) -> None:
        """Validate the workflow structure.

        Args:
            runtime_parameters: Parameters that will be provided at runtime (Session 061)

        Raises:
            WorkflowValidationError: If workflow is invalid
        """
        # Check for unmarked cycles and validate execution order
        try:
            self.get_execution_order()
        except WorkflowValidationError:
            raise

        # Validate cycle configurations
        self._validate_cycles()

        # Check all nodes have required inputs
        for node_id, node_instance in self._node_instances.items():
            try:
                params = node_instance.get_parameters()
            except Exception as e:
                raise WorkflowValidationError(
                    f"Failed to get parameters for node '{node_id}': {e}"
                ) from e

            # Get inputs from connections
            incoming_edges = self.graph.in_edges(node_id, data=True)
            connected_inputs = set()

            for _, _, data in incoming_edges:
                to_input = data.get("to_input")
                if to_input:
                    # Handle both string and list formats
                    if isinstance(to_input, list):
                        connected_inputs.update(to_input)
                    else:
                        connected_inputs.add(to_input)
                # For backward compatibility and complete mapping
                mapping = data.get("mapping", {})
                connected_inputs.update(mapping.values())

            # Check required parameters
            missing_inputs = []
            for param_name, param_def in params.items():
                if param_def.required and param_name not in connected_inputs:
                    # Check if it's provided in config
                    # Handle nested config case (for PythonCodeNode and similar)
                    found_in_config = param_name in node_instance.config
                    if not found_in_config and "config" in node_instance.config:
                        # Check nested config
                        found_in_config = param_name in node_instance.config["config"]

                    # Session 061: Check if parameter will be provided at runtime
                    found_in_runtime = False
                    if runtime_parameters and node_id in runtime_parameters:
                        found_in_runtime = param_name in runtime_parameters[node_id]

                    if not found_in_config and not found_in_runtime:
                        if param_def.default is None:
                            missing_inputs.append(param_name)

            if missing_inputs:
                raise WorkflowValidationError(
                    f"Node '{node_id}' missing required inputs: {missing_inputs}. "
                    f"Provide these inputs via connections, node configuration, or runtime parameters"
                )

        logger.info(f"Workflow '{self.name}' validated successfully")

    def _validate_cycles(self) -> None:
        """Validate cycle configurations and detect potential issues.

        Raises:
            WorkflowValidationError: If cycle configuration is invalid
        """
        cycle_groups = self.get_cycle_groups()

        for cycle_id, cycle_edges in cycle_groups.items():
            # Check for conflicting cycle parameters within the same group
            max_iterations_set = set()
            convergence_checks = set()
            timeouts = set()

            for source, target, data in cycle_edges:
                if data.get("max_iterations") is not None:
                    max_iterations_set.add(data["max_iterations"])
                if data.get("convergence_check") is not None:
                    convergence_checks.add(data["convergence_check"])
                if data.get("timeout") is not None:
                    timeouts.add(data["timeout"])

            # Warn about conflicting parameters (but don't fail)
            if len(max_iterations_set) > 1:
                logger.warning(
                    f"Cycle group '{cycle_id}' has conflicting max_iterations: {max_iterations_set}"
                )
            if len(convergence_checks) > 1:
                logger.warning(
                    f"Cycle group '{cycle_id}' has conflicting convergence_check: {convergence_checks}"
                )
            if len(timeouts) > 1:
                logger.warning(
                    f"Cycle group '{cycle_id}' has conflicting timeouts: {timeouts}"
                )

        # Check for nested cycle validity
        parent_cycles = set()
        child_cycles = set()

        for cycle_id, cycle_edges in cycle_groups.items():
            for source, target, data in cycle_edges:
                if data.get("parent_cycle"):
                    parent_cycles.add(data["parent_cycle"])
                    child_cycles.add(cycle_id)

        # Ensure parent cycles exist
        for parent_cycle in parent_cycles:
            if parent_cycle not in cycle_groups:
                raise WorkflowValidationError(
                    f"Parent cycle '{parent_cycle}' not found in workflow"
                )

        # Check for circular parent relationships
        for child_cycle in child_cycles:
            if child_cycle in parent_cycles:
                raise WorkflowValidationError(
                    f"Cycle '{child_cycle}' cannot be both parent and child"
                )

    def run(
        self, task_manager: TaskManager | None = None, **overrides
    ) -> tuple[dict[str, Any], str | None]:
        """Execute the workflow.

        Args:
            task_manager: Optional task manager for tracking
            **overrides: Parameter overrides

        Returns:
            Tuple of (results dict, run_id)

        Raises:
            WorkflowExecutionError: If workflow execution fails
            WorkflowValidationError: If workflow is invalid
        """
        # For backward compatibility with original graph.py's run method
        return self.execute(inputs=overrides, task_manager=task_manager), None

    def execute(
        self,
        inputs: dict[str, Any] | None = None,
        task_manager: TaskManager | None = None,
    ) -> dict[str, Any]:
        """Execute the workflow.

        Args:
            inputs: Input data for the workflow (can include node overrides)
            task_manager: Optional task manager for tracking

        Returns:
            Execution results by node

        Raises:
            WorkflowExecutionError: If execution fails
        """
        try:
            self.validate()
        except Exception as e:
            raise WorkflowValidationError(f"Workflow validation failed: {e}") from e

        # Initialize task tracking
        run_id = None
        if task_manager:
            try:
                run_id = task_manager.create_run(
                    workflow_name=self.name, metadata={"inputs": inputs}
                )
            except Exception as e:
                logger.warning(f"Failed to create task run: {e}")
                # Continue without task tracking

        # Get execution order
        try:
            execution_order = self.get_execution_order()
        except Exception as e:
            raise WorkflowExecutionError(
                f"Failed to determine execution order: {e}"
            ) from e

        # Execute nodes in order
        results = {}
        inputs = inputs or {}
        failed_nodes = []

        for node_id in execution_order:
            node_instance = self._node_instances[node_id]

            # Start task tracking
            task = None
            if task_manager and run_id:
                try:
                    task = task_manager.create_task(
                        run_id=run_id,
                        node_id=node_id,
                        node_type=node_instance.__class__.__name__,
                    )
                    task.update_status(TaskStatus.RUNNING)
                except Exception as e:
                    logger.warning(f"Failed to create task for node '{node_id}': {e}")

            try:
                # Gather inputs from previous nodes
                node_inputs = {}

                # Add config values
                node_inputs.update(node_instance.config)

                # Get inputs from connected nodes
                for edge in self.graph.in_edges(node_id, data=True):
                    source_node_id = edge[0]
                    edge_data = self.graph[source_node_id][node_id]

                    # Try both connection formats for backward compatibility
                    from_output = edge_data.get("from_output")
                    to_input = edge_data.get("to_input")
                    mapping = edge_data.get("mapping", {})

                    print(f"CONNECTION DEBUG: {source_node_id} -> {node_id}")
                    print(f"  Edge data: {edge_data}")
                    print(f"  from_output: {from_output}, to_input: {to_input}")
                    print(f"  mapping: {mapping}")
                    print(
                        f"  source_results keys: {list(results.get(source_node_id, {}).keys())}"
                    )

                    source_results = results.get(source_node_id, {})

                    # Handle backward compatibility - from_output/to_input can be string or list
                    if from_output and to_input:
                        # Convert to lists if they're strings (backward compatibility)
                        from_outputs = (
                            [from_output]
                            if isinstance(from_output, str)
                            else from_output
                        )
                        to_inputs = (
                            [to_input] if isinstance(to_input, str) else to_input
                        )

                        # Process each mapping pair
                        for i, (src, dst) in enumerate(
                            zip(from_outputs, to_inputs, strict=False)
                        ):
                            if src in source_results:
                                node_inputs[dst] = source_results[src]

                    # Also add connections using mapping format for backward compatibility
                    for source_key, target_key in mapping.items():
                        if source_key in source_results:
                            node_inputs[target_key] = source_results[source_key]
                            print(
                                f"MAPPING DEBUG: {source_key} -> {target_key}, value type: {type(source_results[source_key])}"
                            )
                        else:
                            print(
                                f"MAPPING DEBUG: Source key '{source_key}' not found in source results: {list(source_results.keys())}"
                            )

                # Apply overrides
                node_overrides = inputs.get(node_id, {})
                node_inputs.update(node_overrides)

                # Execute node
                logger.info(
                    f"Executing node '{node_id}' with inputs: {list(node_inputs.keys())}"
                )

                # Support both process() and execute() methods
                if hasattr(node_instance, "process") and callable(
                    node_instance.process
                ):
                    node_results = node_instance.process(node_inputs)
                else:
                    node_results = node_instance.execute(**node_inputs)

                results[node_id] = node_results

                if task:
                    task.update_status(TaskStatus.COMPLETED, result=node_results)

                logger.info(f"Node '{node_id}' completed successfully")

            except Exception as e:
                failed_nodes.append(node_id)
                if task:
                    task.update_status(TaskStatus.FAILED, error=str(e))

                # Include previous failures in error message
                error_msg = f"Node '{node_id}' failed: {e}"
                if len(failed_nodes) > 1:
                    error_msg += f" (Previously failed nodes: {failed_nodes[:-1]})"

                raise WorkflowExecutionError(error_msg) from e

        logger.info(
            f"Workflow '{self.name}' completed successfully. "
            f"Executed {len(execution_order)} nodes"
        )
        return results

    def export_to_kailash(
        self, output_path: str, format: str = "yaml", **config
    ) -> None:
        """Export workflow to Kailash-compatible format.

        Args:
            output_path: Path to write file
            format: Export format (yaml, json, manifest)
            **config: Additional export configuration

        Raises:
            ExportException: If export fails
        """
        try:
            from kailash.utils.export import export_workflow

            export_workflow(self, format=format, output_path=output_path, **config)
        except ImportError as e:
            raise ExportException(f"Failed to import export utilities: {e}") from e
        except Exception as e:
            raise ExportException(
                f"Failed to export workflow to '{output_path}': {e}"
            ) from e

    def to_dict(self) -> dict[str, Any]:
        """Convert workflow to dictionary.

        Returns:
            Dictionary representation
        """
        # Build nodes dictionary
        nodes_dict = {}
        for node_id, node_data in self.nodes.items():
            nodes_dict[node_id] = node_data.model_dump()

        # Build connections list
        connections_list = [conn.model_dump() for conn in self.connections]

        # Build workflow dictionary
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "author": self.author,
            "metadata": self.metadata,
            "nodes": nodes_dict,
            "connections": connections_list,
        }

    def to_json(self) -> str:
        """Convert workflow to JSON string.

        Returns:
            JSON representation
        """
        return json.dumps(self.to_dict(), indent=2)

    def to_yaml(self) -> str:
        """Convert workflow to YAML string.

        Returns:
            YAML representation
        """
        return yaml.dump(self.to_dict(), default_flow_style=False)

    def save(self, path: str, format: str = "json") -> None:
        """Save workflow to file.

        Args:
            path: Output file path
            format: Output format (json or yaml)

        Raises:
            ValueError: If format is invalid
        """
        if format == "json":
            with open(path, "w") as f:
                f.write(self.to_json())
        elif format == "yaml":
            with open(path, "w") as f:
                f.write(self.to_yaml())
        else:
            raise ValueError(f"Unsupported format: {format}")

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        """Create workflow from dictionary.

        Args:
            data: Dictionary representation

        Returns:
            Workflow instance

        Raises:
            WorkflowValidationError: If data is invalid
        """
        try:
            # Extract basic data
            workflow_id = data.get("workflow_id", str(uuid.uuid4()))
            name = data.get("name", "Unnamed Workflow")
            description = data.get("description", "")
            version = data.get("version", "1.0.0")
            author = data.get("author", "")
            metadata = data.get("metadata", {})

            # Create workflow
            workflow = cls(
                workflow_id=workflow_id,
                name=name,
                description=description,
                version=version,
                author=author,
                metadata=metadata,
            )

            # Add nodes
            nodes_data = data.get("nodes", {})
            for node_id, node_data in nodes_data.items():
                # Handle both formats of node data
                if isinstance(node_data, dict):
                    # Get node type
                    node_type = node_data.get("node_type") or node_data.get("type")
                    if not node_type:
                        raise WorkflowValidationError(
                            f"Node type not specified for node '{node_id}'"
                        )

                    # Get node config
                    config = node_data.get("config", {})

                    # Add the node
                    workflow._add_node_internal(node_id, node_type, config)
                else:
                    raise WorkflowValidationError(
                        f"Invalid node data format for node '{node_id}': {type(node_data)}"
                    )

            # Add connections
            connections = data.get("connections", [])
            for conn_data in connections:
                # Handle both connection formats
                if "source_node" in conn_data and "target_node" in conn_data:
                    # Original format
                    source_node = conn_data.get("source_node")
                    source_output = conn_data.get("source_output")
                    target_node = conn_data.get("target_node")
                    target_input = conn_data.get("target_input")
                    workflow._add_edge_internal(
                        source_node, source_output, target_node, target_input
                    )
                elif "from_node" in conn_data and "to_node" in conn_data:
                    # Updated format
                    from_node = conn_data.get("from_node")
                    from_output = conn_data.get("from_output", "output")
                    to_node = conn_data.get("to_node")
                    to_input = conn_data.get("to_input", "input")
                    workflow._add_edge_internal(
                        from_node, from_output, to_node, to_input
                    )
                else:
                    raise WorkflowValidationError(
                        f"Invalid connection data: {conn_data}"
                    )

            return workflow

        except Exception as e:
            if isinstance(e, WorkflowValidationError):
                raise
            raise WorkflowValidationError(
                f"Failed to create workflow from dict: {e}"
            ) from e

    def __repr__(self) -> str:
        """Get string representation."""
        return f"Workflow(id='{self.workflow_id}', name='{self.name}', nodes={len(self.graph.nodes)}, connections={len(self.graph.edges)})"

    def __str__(self) -> str:
        """Get readable string."""
        return f"Workflow '{self.name}' (ID: {self.workflow_id}) with {len(self.graph.nodes)} nodes and {len(self.graph.edges)} connections"

    def create_state_wrapper(self, state_model: BaseModel) -> WorkflowStateWrapper:
        """Create a state manager wrapper for a workflow.

        This wrapper provides convenient methods for updating state immutably,
        making it easier to manage state in workflow nodes.

        Args:
            state_model: The Pydantic model state object to wrap

        Returns:
            A WorkflowStateWrapper instance

        Raises:
            TypeError: If state_model is not a Pydantic BaseModel
        """
        if not isinstance(state_model, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_model)}")

        return WorkflowStateWrapper(state_model)

    def execute_with_state(
        self,
        state_model: BaseModel,
        wrap_state: bool = True,
        task_manager: TaskManager | None = None,
        **overrides,
    ) -> tuple[BaseModel, dict[str, Any]]:
        """Execute the workflow with state management.

        This method provides a simplified interface for executing workflows
        with automatic state management, making it easier to manage state
        transitions.

        Args:
            state_model: The initial state for workflow execution
            wrap_state: Whether to wrap state in WorkflowStateWrapper
            task_manager: Optional task manager for tracking
            **overrides: Additional parameter overrides

        Returns:
            Tuple of (final state, all results)

        Raises:
            WorkflowExecutionError: If execution fails
            WorkflowValidationError: If workflow is invalid
        """
        # Validate input
        if not isinstance(state_model, BaseModel):
            raise TypeError(f"Expected BaseModel, got {type(state_model)}")

        # Prepare inputs
        inputs = {}

        # Wrap the state if needed
        if wrap_state:
            state_wrapper = self.create_state_wrapper(state_model)
            # Find entry nodes (nodes with no incoming edges) and provide state_wrapper to them
            for node_id in self.nodes:
                if self.graph.in_degree(node_id) == 0:  # Entry node
                    inputs[node_id] = {"state_wrapper": state_wrapper}
        else:
            # Find entry nodes and provide unwrapped state to them
            for node_id in self.nodes:
                if self.graph.in_degree(node_id) == 0:  # Entry node
                    inputs[node_id] = {"state": state_model}

        # Add any additional overrides
        for key, value in overrides.items():
            if key in self.nodes:
                inputs.setdefault(key, {}).update(value)

        # Execute the workflow
        results = self.execute(inputs=inputs, task_manager=task_manager)

        # Find the final state
        # First try to find state_wrapper in the last node's outputs
        execution_order = self.get_execution_order()
        if execution_order:
            last_node_id = execution_order[-1]
            last_node_results = results.get(last_node_id, {})

            if wrap_state:
                final_state_wrapper = last_node_results.get("state_wrapper")
                if final_state_wrapper and isinstance(
                    final_state_wrapper, WorkflowStateWrapper
                ):
                    return final_state_wrapper.get_state(), results

                # Try to find another key with a WorkflowStateWrapper
                for key, value in last_node_results.items():
                    if isinstance(value, WorkflowStateWrapper):
                        return value.get_state(), results
            else:
                final_state = last_node_results.get("state")
                if final_state and isinstance(final_state, BaseModel):
                    return final_state, results

                # Try to find another key with a BaseModel
                for key, value in last_node_results.items():
                    if isinstance(value, BaseModel) and isinstance(
                        value, type(state_model)
                    ):
                        return value, results

        # Fallback to original state
        logger.warning(
            "Failed to find final state in workflow results, returning original state"
        )
        return state_model, results
