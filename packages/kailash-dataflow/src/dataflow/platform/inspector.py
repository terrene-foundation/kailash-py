"""
Introspection API for debugging DataFlow without reading source code.

Provides detailed information about:
- Models and their schemas
- Generated nodes and parameters
- DataFlow instance configuration
- Workflows using DataFlow nodes
"""

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class ModelInfo:
    """Information about a DataFlow model."""

    name: str
    table_name: str
    schema: dict[str, Any]
    generated_nodes: list[str]
    parameters: dict[str, dict[str, Any]]  # node_type -> parameters
    primary_key: Optional[str] = None

    def show(self, color: bool = True) -> str:
        """Format model information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Model: {self.name}{RESET}")
        parts.append(f"Table: {self.table_name}")
        if self.primary_key:
            parts.append(f"Primary Key: {self.primary_key}")
        parts.append("")

        # Schema
        parts.append(f"{GREEN}Schema:{RESET}")
        for field_name, field_info in self.schema.items():
            parts.append(f"  {field_name}: {field_info}")
        parts.append("")

        # Generated nodes
        parts.append(f"{GREEN}Generated Nodes ({len(self.generated_nodes)}):{RESET}")
        for node_type in self.generated_nodes:
            parts.append(f"  - {node_type}")
        parts.append("")

        # Parameters per node
        parts.append(f"{GREEN}Parameters per Node:{RESET}")
        for node_type, params in self.parameters.items():
            parts.append(f"  {node_type}:")
            for param_name, param_info in params.items():
                parts.append(f"    - {param_name}: {param_info}")

        return "\n".join(parts)


@dataclass
class NodeInfo:
    """Information about a specific DataFlow node."""

    node_id: str
    node_type: str
    model_name: str
    expected_params: dict[str, Any]
    output_params: dict[str, Any]
    connections_in: list[dict[str, str]] = field(default_factory=list)
    connections_out: list[dict[str, str]] = field(default_factory=list)
    usage_example: str = ""

    def show(self, color: bool = True) -> str:
        """Format node information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Node: {self.node_id}{RESET}")
        parts.append(f"Type: {self.node_type}")
        parts.append(f"Model: {self.model_name}")
        parts.append("")

        # Expected parameters
        parts.append(f"{GREEN}Expected Input Parameters:{RESET}")
        if self.expected_params:
            for param_name, param_info in self.expected_params.items():
                required = param_info.get("required", False)
                param_type = param_info.get("type", "any")
                req_marker = f"{YELLOW}*{RESET}" if required else " "
                parts.append(f"  {req_marker} {param_name}: {param_type}")
                if "description" in param_info:
                    parts.append(f"      {param_info['description']}")
        else:
            parts.append("  (none)")
        parts.append("")

        # Output parameters
        parts.append(f"{GREEN}Output Parameters:{RESET}")
        if self.output_params:
            for param_name, param_info in self.output_params.items():
                parts.append(f"  - {param_name}: {param_info}")
        else:
            parts.append("  (none)")
        parts.append("")

        # Connections
        if self.connections_in:
            parts.append(f"{GREEN}Incoming Connections:{RESET}")
            for conn in self.connections_in:
                parts.append(
                    f"  {conn['source']}.{conn['source_param']} -> {conn['target_param']}"
                )
            parts.append("")

        if self.connections_out:
            parts.append(f"{GREEN}Outgoing Connections:{RESET}")
            for conn in self.connections_out:
                parts.append(
                    f"  {conn['source_param']} -> {conn['target']}.{conn['target_param']}"
                )
            parts.append("")

        # Usage example
        if self.usage_example:
            parts.append(f"{GREEN}Usage Example:{RESET}")
            parts.append(self.usage_example)

        return "\n".join(parts)

    def show_expected_params(self) -> str:
        """Show only expected parameters (compact format)."""
        parts = []
        parts.append(f"Expected parameters for '{self.node_id}':")
        for param_name, param_info in self.expected_params.items():
            required = " (required)" if param_info.get("required") else " (optional)"
            parts.append(f"  - {param_name}: {param_info.get('type', 'any')}{required}")
        return "\n".join(parts)


@dataclass
class InstanceInfo:
    """Information about a DataFlow instance."""

    name: str
    config: dict[str, Any]
    models: dict[str, Any]
    migrations: dict[str, Any]
    health: dict[str, Any]
    database_url: str

    def show(self, color: bool = True) -> str:
        """Format instance information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}DataFlow Instance: {self.name}{RESET}")
        parts.append(f"Database: {self.database_url}")
        parts.append("")

        # Health status
        health_status = self.health.get("status", "unknown")
        health_color = GREEN if health_status == "healthy" else RED
        parts.append(f"Health: {health_color}{health_status}{RESET}")
        if self.health.get("issues"):
            parts.append("Issues:")
            for issue in self.health["issues"]:
                parts.append(f"  - {issue}")
        parts.append("")

        # Models
        parts.append(f"{GREEN}Registered Models ({len(self.models)}):{RESET}")
        for model_name in self.models:
            parts.append(f"  - {model_name}")
        parts.append("")

        # Configuration
        parts.append(f"{GREEN}Configuration:{RESET}")
        for key, value in self.config.items():
            parts.append(f"  {key}: {value}")
        parts.append("")

        # Migrations
        parts.append(f"{GREEN}Migrations:{RESET}")
        for key, value in self.migrations.items():
            parts.append(f"  {key}: {value}")

        return "\n".join(parts)


@dataclass
class ConnectionInfo:
    """Information about a connection between two nodes."""

    source_node: str
    source_parameter: str
    target_node: str
    target_parameter: str
    source_type: Optional[str] = None
    target_type: Optional[str] = None
    is_valid: bool = True
    validation_message: Optional[str] = None

    def show(self, color: bool = True) -> str:
        """Format connection information for display."""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""

        # Format the connection arrow
        arrow = f"{self.source_node}.{self.source_parameter} -> {self.target_node}.{self.target_parameter}"

        # Add validation status
        if self.is_valid:
            status = f"{GREEN}✓{RESET}"
        else:
            status = f"{RED}✗{RESET}"

        parts = [f"{status} {arrow}"]

        # Add type information if available
        if self.source_type or self.target_type:
            type_info = []
            if self.source_type:
                type_info.append(f"source: {self.source_type}")
            if self.target_type:
                type_info.append(f"target: {self.target_type}")
            parts.append(f"  Types: {', '.join(type_info)}")

        # Add validation message if invalid
        if not self.is_valid and self.validation_message:
            parts.append(f"  {YELLOW}Issue:{RESET} {self.validation_message}")

        return "\n".join(parts)


@dataclass
class ConnectionGraph:
    """Information about a workflow's connection graph."""

    nodes: List[str]
    connections: List[ConnectionInfo]
    entry_points: List[str]  # Nodes with no inputs
    exit_points: List[str]  # Nodes with no outputs
    cycles: List[List[str]]  # Detected cycles

    def show(self, color: bool = True) -> str:
        """Format connection graph for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Connection Graph{RESET}")
        parts.append("")

        # Node summary
        parts.append(f"{GREEN}Nodes ({len(self.nodes)}):{RESET}")
        for node in sorted(self.nodes):
            parts.append(f"  - {node}")
        parts.append("")

        # Entry points
        parts.append(f"{GREEN}Entry Points ({len(self.entry_points)}):{RESET}")
        if self.entry_points:
            for node in sorted(self.entry_points):
                parts.append(f"  - {node}")
        else:
            parts.append("  (none - all nodes have inputs)")
        parts.append("")

        # Exit points
        parts.append(f"{GREEN}Exit Points ({len(self.exit_points)}):{RESET}")
        if self.exit_points:
            for node in sorted(self.exit_points):
                parts.append(f"  - {node}")
        else:
            parts.append("  (none - all nodes have outputs)")
        parts.append("")

        # Connections
        parts.append(f"{GREEN}Connections ({len(self.connections)}):{RESET}")
        if self.connections:
            for conn in self.connections:
                parts.append(f"  {conn.show(color=color)}")
        else:
            parts.append("  (none)")
        parts.append("")

        # Cycles
        if self.cycles:
            parts.append(f"{YELLOW}Cycles Detected ({len(self.cycles)}):{RESET}")
            for i, cycle in enumerate(self.cycles, 1):
                cycle_str = " -> ".join(cycle + [cycle[0]])
                parts.append(f"  {i}. {cycle_str}")
        else:
            parts.append(f"{GREEN}No Cycles Detected{RESET}")

        return "\n".join(parts)


@dataclass
class ParameterTrace:
    """Information about a parameter's trace through the workflow."""

    parameter_name: str
    source_node: Optional[str] = None
    source_parameter: Optional[str] = None
    transformations: List[Dict[str, Any]] = field(default_factory=list)
    consumers: List[str] = field(default_factory=list)
    parameter_type: Optional[str] = None
    is_complete: bool = True
    missing_sources: List[str] = field(default_factory=list)

    def show(self, color: bool = True) -> str:
        """Format parameter trace for display with flow visualization."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []

        # Header with completion status
        if self.is_complete:
            status = f"{GREEN}✓{RESET}"
        else:
            status = f"{RED}✗{RESET}"

        parts.append(
            f"{status} {BLUE}{BOLD}Parameter Trace: {self.parameter_name}{RESET}"
        )
        parts.append("")

        # Source information
        if self.source_node:
            parts.append(f"{GREEN}Source:{RESET}")
            parts.append(f"  Node: {self.source_node}")
            if self.source_parameter:
                parts.append(f"  Parameter: {self.source_parameter}")
            if self.parameter_type:
                parts.append(f"  Type: {self.parameter_type}")
        else:
            parts.append(
                f"{YELLOW}Source: Workflow input (no upstream connection){RESET}"
            )
        parts.append("")

        # Transformations
        if self.transformations:
            parts.append(
                f"{GREEN}Transformations ({len(self.transformations)}):{RESET}"
            )
            for i, transform in enumerate(self.transformations, 1):
                transform_type = transform.get("type", "unknown")
                details = transform.get("details", "")

                if transform_type == "dot_notation":
                    parts.append(f"  {i}. {YELLOW}Dot Notation:{RESET} {details}")
                elif transform_type == "mapping":
                    parts.append(f"  {i}. {YELLOW}Mapping:{RESET} {details}")
                elif transform_type == "type_change":
                    parts.append(f"  {i}. {YELLOW}Type Change:{RESET} {details}")
                else:
                    parts.append(f"  {i}. {transform_type}: {details}")
            parts.append("")

        # Consumers
        if self.consumers:
            parts.append(f"{GREEN}Consumed By ({len(self.consumers)}):{RESET}")
            for consumer in self.consumers:
                parts.append(f"  - {consumer}")
            parts.append("")

        # Missing sources (if incomplete)
        if not self.is_complete and self.missing_sources:
            parts.append(f"{RED}Missing Sources:{RESET}")
            for missing in self.missing_sources:
                parts.append(f"  - {missing}")
            parts.append("")

        # Flow visualization
        parts.append(f"{GREEN}Flow:{RESET}")
        if self.source_node:
            flow_parts = [self.source_node]
            if self.source_parameter:
                flow_parts.append(f"[{self.source_parameter}]")

            for transform in self.transformations:
                transform_type = transform.get("type", "unknown")
                if transform_type == "dot_notation":
                    flow_parts.append(f"→ {transform.get('details', '')}")
                elif transform_type == "mapping":
                    flow_parts.append(f"→ [{transform.get('details', '')}]")

            flow_parts.append(f"→ {self.parameter_name}")
            parts.append(f"  {' '.join(flow_parts)}")
        else:
            parts.append(f"  (workflow input) → {self.parameter_name}")

        return "\n".join(parts)


@dataclass
class NodeSchema:
    """Information about a node's input and output schema."""

    node_id: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    node_type: Optional[str] = None

    def show(self, color: bool = True) -> str:
        """Format node schema for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Node Schema: {self.node_id}{RESET}")
        if self.node_type:
            parts.append(f"Type: {self.node_type}")
        parts.append("")

        # Inputs
        parts.append(f"{GREEN}Inputs:{RESET}")
        if self.inputs:
            for name, info in self.inputs.items():
                parts.append(f"  - {name}: {info}")
        else:
            parts.append("  (none)")
        parts.append("")

        # Outputs
        parts.append(f"{GREEN}Outputs:{RESET}")
        if self.outputs:
            for name, info in self.outputs.items():
                parts.append(f"  - {name}: {info}")
        else:
            parts.append("  (none)")

        return "\n".join(parts)


@dataclass
class NodeComparison:
    """Comparison between two nodes."""

    node_id1: str
    node_id2: str
    differences: Dict[str, Any]
    similarities: Dict[str, Any]

    def show(self, color: bool = True) -> str:
        """Format node comparison for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(
            f"{BLUE}{BOLD}Comparison: {self.node_id1} ↔ {self.node_id2}{RESET}"
        )
        parts.append("")

        # Differences
        if self.differences:
            parts.append(f"{YELLOW}Differences:{RESET}")
            for key, value in self.differences.items():
                parts.append(f"  {key}: {value}")
            parts.append("")

        # Similarities
        if self.similarities:
            parts.append(f"{GREEN}Similarities:{RESET}")
            for key, value in self.similarities.items():
                parts.append(f"  {key}: {value}")

        return "\n".join(parts)


@dataclass
class WorkflowInfo:
    """Information about a workflow using DataFlow nodes."""

    workflow_id: str
    dataflow_nodes: list[str]
    parameter_flow: dict[str, list[str]]  # node_id -> [connected_nodes]
    validation_issues: list[str] = field(default_factory=list)

    def show(self, color: bool = True) -> str:
        """Format workflow information for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Workflow: {self.workflow_id}{RESET}")
        parts.append("")

        # DataFlow nodes
        parts.append(f"{GREEN}DataFlow Nodes ({len(self.dataflow_nodes)}):{RESET}")
        for node_id in self.dataflow_nodes:
            parts.append(f"  - {node_id}")
        parts.append("")

        # Parameter flow
        parts.append(f"{GREEN}Parameter Flow:{RESET}")
        for node_id, connected_nodes in self.parameter_flow.items():
            parts.append(f"  {node_id}:")
            for connected in connected_nodes:
                parts.append(f"    -> {connected}")
        parts.append("")

        # Validation issues
        if self.validation_issues:
            parts.append(f"{YELLOW}Validation Issues:{RESET}")
            for issue in self.validation_issues:
                parts.append(f"  - {issue}")

        return "\n".join(parts)


@dataclass
class ExecutionEvent:
    """Information about a workflow execution event."""

    event_type: str  # "node_start", "node_complete", "node_error", "param_set"
    node_id: str
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def show(self, color: bool = True) -> str:
        """Format execution event for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""

        # Event type indicator
        if self.event_type == "node_start":
            indicator = f"{BLUE}→{RESET}"
        elif self.event_type == "node_complete":
            indicator = f"{GREEN}✓{RESET}"
        elif self.event_type == "node_error":
            indicator = f"{RED}✗{RESET}"
        else:
            indicator = f"{YELLOW}•{RESET}"

        parts = [f"{indicator} [{self.event_type}] {self.node_id}"]

        if self.data:
            parts.append(f"  Data: {self.data}")
        if self.error:
            parts.append(f"  {RED}Error: {self.error}{RESET}")

        return "\n".join(parts)


@dataclass
class RuntimeState:
    """Information about workflow runtime state."""

    active_nodes: List[str]
    completed_nodes: List[str]
    pending_nodes: List[str]
    execution_order: List[str]
    current_node: Optional[str] = None
    parameter_values: Dict[str, Dict[str, Any]] = field(
        default_factory=dict
    )  # node_id -> {param: value}
    events: List[ExecutionEvent] = field(default_factory=list)

    def show(self, color: bool = True) -> str:
        """Format runtime state for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Runtime State{RESET}")
        parts.append("")

        # Current node
        if self.current_node:
            parts.append(f"{YELLOW}Current Node:{RESET} {self.current_node}")
            parts.append("")

        # Status counts
        parts.append(f"{GREEN}Completed:{RESET} {len(self.completed_nodes)}")
        parts.append(f"{YELLOW}Active:{RESET} {len(self.active_nodes)}")
        parts.append(f"{BLUE}Pending:{RESET} {len(self.pending_nodes)}")
        parts.append("")

        # Active nodes detail
        if self.active_nodes:
            parts.append(f"{YELLOW}Active Nodes:{RESET}")
            for node in self.active_nodes:
                parts.append(f"  - {node}")
            parts.append("")

        # Completed nodes
        if self.completed_nodes:
            parts.append(f"{GREEN}Completed Nodes:{RESET}")
            for node in self.completed_nodes:
                parts.append(f"  - {node}")
            parts.append("")

        # Recent events
        if self.events:
            parts.append(f"{BLUE}Recent Events (last 5):{RESET}")
            for event in self.events[-5:]:
                parts.append(f"  {event.show(color=color)}")

        return "\n".join(parts)


@dataclass
class BreakpointInfo:
    """Information about a breakpoint configuration."""

    node_id: str
    condition: Optional[str] = None  # Python expression to evaluate
    enabled: bool = True
    hit_count: int = 0

    def show(self, color: bool = True) -> str:
        """Format breakpoint info for display."""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""

        status = f"{GREEN}enabled{RESET}" if self.enabled else f"{RED}disabled{RESET}"
        parts = [f"Breakpoint at {self.node_id} ({status})"]

        if self.condition:
            parts.append(f"  Condition: {YELLOW}{self.condition}{RESET}")

        parts.append(f"  Hit count: {self.hit_count}")

        return "\n".join(parts)


@dataclass
class WorkflowSummary:
    """High-level workflow overview."""

    node_count: int
    connection_count: int
    entry_points: List[str]
    exit_points: List[str]
    has_cycles: bool
    max_depth: int
    complexity_score: float

    def show(self, color: bool = True) -> str:
        """Format workflow summary for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Workflow Summary{RESET}")
        parts.append("")

        # Basic metrics
        parts.append(f"{GREEN}Nodes:{RESET} {self.node_count}")
        parts.append(f"{GREEN}Connections:{RESET} {self.connection_count}")
        parts.append("")

        # Entry/Exit points
        parts.append(f"{YELLOW}Entry Points ({len(self.entry_points)}):{RESET}")
        for node in self.entry_points[:5]:
            parts.append(f"  - {node}")
        if len(self.entry_points) > 5:
            parts.append(f"  ... and {len(self.entry_points) - 5} more")
        parts.append("")

        parts.append(f"{YELLOW}Exit Points ({len(self.exit_points)}):{RESET}")
        for node in self.exit_points[:5]:
            parts.append(f"  - {node}")
        if len(self.exit_points) > 5:
            parts.append(f"  ... and {len(self.exit_points) - 5} more")
        parts.append("")

        # Complexity indicators
        cycle_status = f"{RED}Yes{RESET}" if self.has_cycles else f"{GREEN}No{RESET}"
        parts.append(f"Has Cycles: {cycle_status}")
        parts.append(f"Max Depth: {self.max_depth}")
        parts.append(f"Complexity Score: {self.complexity_score:.2f}")

        return "\n".join(parts)


@dataclass
class WorkflowMetrics:
    """Detailed workflow statistics."""

    total_nodes: int
    total_connections: int
    avg_connections_per_node: float
    max_fan_out: int
    max_fan_in: int
    isolated_nodes: List[str]
    bottleneck_nodes: List[str]
    critical_path_length: int

    def show(self, color: bool = True) -> str:
        """Format workflow metrics for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Workflow Metrics{RESET}")
        parts.append("")

        # Basic counts
        parts.append(f"{GREEN}Total Nodes:{RESET} {self.total_nodes}")
        parts.append(f"{GREEN}Total Connections:{RESET} {self.total_connections}")
        parts.append(f"Avg Connections/Node: {self.avg_connections_per_node:.2f}")
        parts.append("")

        # Fan-out/in
        parts.append(f"Max Fan-Out: {self.max_fan_out}")
        parts.append(f"Max Fan-In: {self.max_fan_in}")
        parts.append(f"Critical Path Length: {self.critical_path_length}")
        parts.append("")

        # Issues
        if self.isolated_nodes:
            parts.append(f"{RED}Isolated Nodes ({len(self.isolated_nodes)}):{RESET}")
            for node in self.isolated_nodes[:5]:
                parts.append(f"  - {node}")
            if len(self.isolated_nodes) > 5:
                parts.append(f"  ... and {len(self.isolated_nodes) - 5} more")
            parts.append("")

        if self.bottleneck_nodes:
            parts.append(
                f"{YELLOW}Bottleneck Nodes ({len(self.bottleneck_nodes)}):{RESET}"
            )
            for node in self.bottleneck_nodes[:5]:
                parts.append(f"  - {node}")
            if len(self.bottleneck_nodes) > 5:
                parts.append(f"  ... and {len(self.bottleneck_nodes) - 5} more")

        return "\n".join(parts)


@dataclass
class ValidationIssue:
    """Single validation issue."""

    severity: str  # "error", "warning", "info"
    category: str  # "connection", "parameter", "structure", "performance"
    node_id: Optional[str]
    message: str
    suggestion: Optional[str] = None


@dataclass
class WorkflowValidationReport:
    """Comprehensive workflow validation results."""

    is_valid: bool
    error_count: int
    warning_count: int
    info_count: int
    issues: List[ValidationIssue] = field(default_factory=list)

    def show(self, color: bool = True) -> str:
        """Format validation report for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        status = f"{GREEN}✓ VALID{RESET}" if self.is_valid else f"{RED}✗ INVALID{RESET}"
        parts.append(f"{BLUE}{BOLD}Validation Report{RESET} - {status}")
        parts.append("")

        # Summary counts
        parts.append(f"{RED}Errors:{RESET} {self.error_count}")
        parts.append(f"{YELLOW}Warnings:{RESET} {self.warning_count}")
        parts.append(f"{BLUE}Info:{RESET} {self.info_count}")
        parts.append("")

        # Issues by severity
        if self.issues:
            errors = [i for i in self.issues if i.severity == "error"]
            warnings = [i for i in self.issues if i.severity == "warning"]
            infos = [i for i in self.issues if i.severity == "info"]

            if errors:
                parts.append(f"{RED}{BOLD}Errors:{RESET}")
                for issue in errors[:5]:
                    node = f" [{issue.node_id}]" if issue.node_id else ""
                    parts.append(f"  {RED}•{RESET} {issue.message}{node}")
                    if issue.suggestion:
                        parts.append(f"    → {issue.suggestion}")
                if len(errors) > 5:
                    parts.append(f"  ... and {len(errors) - 5} more errors")
                parts.append("")

            if warnings:
                parts.append(f"{YELLOW}{BOLD}Warnings:{RESET}")
                for issue in warnings[:5]:
                    node = f" [{issue.node_id}]" if issue.node_id else ""
                    parts.append(f"  {YELLOW}•{RESET} {issue.message}{node}")
                    if issue.suggestion:
                        parts.append(f"    → {issue.suggestion}")
                if len(warnings) > 5:
                    parts.append(f"  ... and {len(warnings) - 5} more warnings")

        return "\n".join(parts)


@dataclass
class WorkflowVisualizationData:
    """Data for visualizing workflow as a graph."""

    nodes: List[Dict[str, Any]]
    edges: List[Dict[str, Any]]
    layout_hints: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "nodes": self.nodes,
            "edges": self.edges,
            "layout_hints": self.layout_hints,
        }

    def show(self, color: bool = True) -> str:
        """Format visualization data summary for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Visualization Data{RESET}")
        parts.append("")
        parts.append(f"{GREEN}Nodes:{RESET} {len(self.nodes)}")
        parts.append(f"{GREEN}Edges:{RESET} {len(self.edges)}")
        parts.append("")
        parts.append(
            f"Layout: {self.layout_hints.get('suggested_layout', 'hierarchical')}"
        )
        parts.append(
            f"Direction: {self.layout_hints.get('direction', 'top-to-bottom')}"
        )

        return "\n".join(parts)


@dataclass
class WorkflowPerformanceProfile:
    """Workflow performance characteristics."""

    estimated_execution_time_ms: float
    parallelization_potential: float
    sequential_bottlenecks: List[str]
    parallel_stages: List[List[str]]
    resource_requirements: Dict[str, Any]

    def show(self, color: bool = True) -> str:
        """Format performance profile for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Performance Profile{RESET}")
        parts.append("")

        # Timing
        parts.append(
            f"{GREEN}Estimated Execution Time:{RESET} {self.estimated_execution_time_ms:.2f}ms"
        )
        parts.append(f"Parallelization Potential: {self.parallelization_potential:.1%}")
        parts.append(f"Parallel Stages: {len(self.parallel_stages)}")
        parts.append("")

        # Bottlenecks
        if self.sequential_bottlenecks:
            parts.append(
                f"{YELLOW}Sequential Bottlenecks ({len(self.sequential_bottlenecks)}):{RESET}"
            )
            for node in self.sequential_bottlenecks[:5]:
                parts.append(f"  - {node}")
            if len(self.sequential_bottlenecks) > 5:
                parts.append(f"  ... and {len(self.sequential_bottlenecks) - 5} more")
            parts.append("")

        # Resource requirements
        if self.resource_requirements:
            parts.append(f"{BLUE}Resource Requirements:{RESET}")
            for resource, value in list(self.resource_requirements.items())[:5]:
                parts.append(f"  {resource}: {value}")

        return "\n".join(parts)


@dataclass
class ModelSchemaDiff:
    """Schema differences between two models."""

    model1_name: str
    model2_name: str
    added_fields: Dict[str, Any] = field(default_factory=dict)
    removed_fields: Dict[str, Any] = field(default_factory=dict)
    modified_fields: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    identical: bool = False

    def show(self, color: bool = True) -> str:
        """Format schema diff for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(
            f"{BLUE}{BOLD}Schema Diff: {self.model1_name} vs {self.model2_name}{RESET}"
        )
        parts.append("")

        if self.identical:
            parts.append(f"{GREEN}✓ Schemas are identical{RESET}")
        else:
            if self.added_fields:
                parts.append(f"{GREEN}Added Fields ({len(self.added_fields)}):{RESET}")
                for field_name, field_info in self.added_fields.items():
                    parts.append(f"  + {field_name}: {field_info}")

            if self.removed_fields:
                parts.append("")
                parts.append(
                    f"{RED}Removed Fields ({len(self.removed_fields)}):{RESET}"
                )
                for field_name, field_info in self.removed_fields.items():
                    parts.append(f"  - {field_name}: {field_info}")

            if self.modified_fields:
                parts.append("")
                parts.append(
                    f"{YELLOW}Modified Fields ({len(self.modified_fields)}):{RESET}"
                )
                for field_name, changes in self.modified_fields.items():
                    parts.append(f"  ~ {field_name}:")
                    parts.append(f"      Before: {changes['before']}")
                    parts.append(f"      After:  {changes['after']}")

        return "\n".join(parts)


@dataclass
class ModelMigrationStatus:
    """Migration status for a model."""

    model_name: str
    table_exists: bool
    schema_matches: bool
    pending_migrations: List[str] = field(default_factory=list)
    last_migration_date: Optional[str] = None
    migration_required: bool = False

    def show(self, color: bool = True) -> str:
        """Format migration status for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        RED = "\033[91m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Migration Status: {self.model_name}{RESET}")
        parts.append("")

        # Table existence
        if self.table_exists:
            parts.append(f"Table Exists: {GREEN}✓ Yes{RESET}")
        else:
            parts.append(f"Table Exists: {RED}✗ No{RESET}")

        # Schema match
        if self.schema_matches:
            parts.append(f"Schema Matches: {GREEN}✓ Yes{RESET}")
        else:
            parts.append(f"Schema Matches: {YELLOW}⚠ No{RESET}")

        # Migration requirement
        if self.migration_required:
            parts.append(f"Migration Required: {YELLOW}⚠ Yes{RESET}")
        else:
            parts.append(f"Migration Required: {GREEN}✓ No{RESET}")

        # Pending migrations
        if self.pending_migrations:
            parts.append("")
            parts.append(
                f"{YELLOW}Pending Migrations ({len(self.pending_migrations)}):{RESET}"
            )
            for migration in self.pending_migrations:
                parts.append(f"  - {migration}")

        # Last migration date
        if self.last_migration_date:
            parts.append("")
            parts.append(f"Last Migration: {self.last_migration_date}")

        return "\n".join(parts)


@dataclass
class ModelValidationRules:
    """Validation rules for a model."""

    model_name: str
    required_fields: List[str] = field(default_factory=list)
    nullable_fields: List[str] = field(default_factory=list)
    unique_constraints: List[str] = field(default_factory=list)
    foreign_keys: Dict[str, str] = field(default_factory=dict)
    field_types: Dict[str, str] = field(default_factory=dict)

    def show(self, color: bool = True) -> str:
        """Format validation rules for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{BLUE}{BOLD}Validation Rules: {self.model_name}{RESET}")
        parts.append("")

        # Required fields
        if self.required_fields:
            parts.append(
                f"{GREEN}Required Fields ({len(self.required_fields)}):{RESET}"
            )
            for field_name in self.required_fields:
                parts.append(f"  * {field_name}")
        else:
            parts.append(f"{GREEN}Required Fields: None{RESET}")

        # Nullable fields
        if self.nullable_fields:
            parts.append("")
            parts.append(
                f"{YELLOW}Nullable Fields ({len(self.nullable_fields)}):{RESET}"
            )
            for field_name in self.nullable_fields:
                parts.append(f"  - {field_name}")

        # Unique constraints
        if self.unique_constraints:
            parts.append("")
            parts.append(
                f"{GREEN}Unique Constraints ({len(self.unique_constraints)}):{RESET}"
            )
            for field_name in self.unique_constraints:
                parts.append(f"  ! {field_name}")

        # Foreign keys
        if self.foreign_keys:
            parts.append("")
            parts.append(f"{BLUE}Foreign Keys ({len(self.foreign_keys)}):{RESET}")
            for field_name, reference in self.foreign_keys.items():
                parts.append(f"  → {field_name} → {reference}")

        # Field types
        if self.field_types:
            parts.append("")
            parts.append(f"{GREEN}Field Types:{RESET}")
            for field_name, field_type in self.field_types.items():
                parts.append(f"  {field_name}: {field_type}")

        return "\n".join(parts)


@dataclass
class ErrorDiagnosis:
    """Diagnosis results for a DataFlow error."""

    error_code: str
    error_type: str
    affected_component: Optional[str]
    inspector_commands: List[str] = field(default_factory=list)
    context_hints: Dict[str, Any] = field(default_factory=dict)
    recommended_actions: List[str] = field(default_factory=list)

    def show(self, color: bool = True) -> str:
        """Format error diagnosis for display."""
        BLUE = "\033[94m" if color else ""
        GREEN = "\033[92m" if color else ""
        YELLOW = "\033[93m" if color else ""
        RED = "\033[91m" if color else ""
        RESET = "\033[0m" if color else ""
        BOLD = "\033[1m" if color else ""

        parts = []
        parts.append(f"{RED}{BOLD}Error Diagnosis: {self.error_code}{RESET}")
        parts.append(f"Type: {self.error_type}")
        if self.affected_component:
            parts.append(f"Affected Component: {self.affected_component}")
        parts.append("")

        # Inspector commands to investigate
        if self.inspector_commands:
            parts.append(f"{BLUE}Recommended Inspector Commands:{RESET}")
            for cmd in self.inspector_commands:
                parts.append(f"  $ {cmd}")
            parts.append("")

        # Context hints
        if self.context_hints:
            parts.append(f"{YELLOW}Context Hints:{RESET}")
            for key, value in self.context_hints.items():
                parts.append(f"  {key}: {value}")
            parts.append("")

        # Recommended actions
        if self.recommended_actions:
            parts.append(f"{GREEN}Recommended Actions:{RESET}")
            for i, action in enumerate(self.recommended_actions, 1):
                parts.append(f"  {i}. {action}")

        return "\n".join(parts)


class Inspector:
    """
    Introspection API for debugging DataFlow without reading source code.

    Provides detailed information about models, nodes, instance state,
    and workflows without requiring users to navigate large source files.
    """

    def __init__(self, studio: Any, workflow: Any = None):
        """
        Initialize inspector.

        Args:
            studio: DataFlowStudio instance or DataFlow instance
            workflow: Optional WorkflowBuilder instance for connection analysis
        """
        self.studio = studio
        # Handle both DataFlowStudio and raw DataFlow instances
        self.db = getattr(studio, "db", studio)
        self.workflow = workflow

        # Real-time debugging state
        self._runtime_state: Optional[RuntimeState] = None
        self._breakpoints: Dict[str, BreakpointInfo] = {}
        self._execution_events: List[ExecutionEvent] = []
        self._execution_callbacks: List[callable] = []

    def _get_workflow(self) -> Any:
        """Get workflow from either self.workflow or self.workflow_obj."""
        # Check for workflow attribute first
        if hasattr(self, "workflow") and self.workflow is not None:
            return self.workflow
        # Fall back to workflow_obj (used in tests)
        if hasattr(self, "workflow_obj") and self.workflow_obj is not None:
            return self.workflow_obj
        return None

    def model(self, model_name: str) -> ModelInfo:
        """
        Get detailed information about a model.

        Args:
            model_name: Name of the model

        Returns:
            ModelInfo instance with schema, nodes, and parameters

        Example:
            >>> info = inspector.model("User")
            >>> print(info.show())
            >>> print(info.schema)
            >>> print(info.generated_nodes)
        """
        # Get model from DataFlow
        models = getattr(self.db, "_models", {})
        model_class = models.get(model_name)

        if not model_class:
            raise ValueError(f"Model '{model_name}' not found")

        # Extract schema information
        schema = {}
        table_name = ""
        primary_key = None

        if hasattr(model_class, "__table__"):
            table = model_class.__table__
            table_name = table.name

            for column in table.columns:
                schema[column.name] = {
                    "type": str(column.type),
                    "nullable": column.nullable,
                    "primary_key": column.primary_key,
                }
                if column.primary_key:
                    primary_key = column.name

        # Generate list of nodes
        generated_nodes = [
            f"{model_name}CreateNode",
            f"{model_name}ReadNode",
            f"{model_name}ReadByIdNode",
            f"{model_name}UpdateNode",
            f"{model_name}DeleteNode",
            f"{model_name}ListNode",
            f"{model_name}CountNode",
            f"{model_name}UpsertNode",
            f"{model_name}BulkCreateNode",
        ]

        # Generate parameter information for each node type
        parameters = {
            "create": {
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Dictionary with model fields",
                }
            },
            "read": {
                "filters": {
                    "required": False,
                    "type": "dict",
                    "description": "Filter conditions",
                }
            },
            "read_by_id": {
                f"{primary_key}": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                }
            },
            "update": {
                f"{primary_key}": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                },
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Fields to update",
                },
            },
            "delete": {
                f"{primary_key}": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                }
            },
        }

        return ModelInfo(
            name=model_name,
            table_name=table_name,
            schema=schema,
            generated_nodes=generated_nodes,
            parameters=parameters,
            primary_key=primary_key,
        )

    def model_schema_diff(self, model_name1: str, model_name2: str) -> ModelSchemaDiff:
        """
        Compare schemas of two models.

        Args:
            model_name1: First model name
            model_name2: Second model name

        Returns:
            ModelSchemaDiff with added, removed, and modified fields

        Example:
            >>> diff = inspector.model_schema_diff("User", "UserV2")
            >>> print(diff.show())
            >>> print(diff.added_fields)
        """
        # Get both models
        model1 = self.model(model_name1)
        model2 = self.model(model_name2)

        # Compare schemas
        schema1 = model1.schema
        schema2 = model2.schema

        added_fields = {}
        removed_fields = {}
        modified_fields = {}

        # Find added and modified fields
        for field_name, field_info in schema2.items():
            if field_name not in schema1:
                added_fields[field_name] = field_info
            elif schema1[field_name] != field_info:
                modified_fields[field_name] = {
                    "before": schema1[field_name],
                    "after": field_info,
                }

        # Find removed fields
        for field_name, field_info in schema1.items():
            if field_name not in schema2:
                removed_fields[field_name] = field_info

        # Check if schemas are identical
        identical = not added_fields and not removed_fields and not modified_fields

        return ModelSchemaDiff(
            model1_name=model_name1,
            model2_name=model_name2,
            added_fields=added_fields,
            removed_fields=removed_fields,
            modified_fields=modified_fields,
            identical=identical,
        )

    def model_migration_status(self, model_name: str) -> ModelMigrationStatus:
        """
        Get migration status for a model.

        Args:
            model_name: Name of the model

        Returns:
            ModelMigrationStatus with table existence and schema match info

        Example:
            >>> status = inspector.model_migration_status("User")
            >>> print(status.show())
            >>> if status.migration_required:
            ...     print("Migration needed!")
        """
        # Get model information
        model_info = self.model(model_name)

        # Check table existence (simplified - would query actual database)
        table_exists = model_info.table_name != ""

        # Check schema match (simplified - would compare with database schema)
        schema_matches = table_exists

        # Determine if migration is required
        migration_required = not (table_exists and schema_matches)

        # Pending migrations (simplified - would query migration system)
        pending_migrations = []
        if migration_required:
            pending_migrations = [
                f"Create table {model_info.table_name}",
                "Add indexes",
                "Add constraints",
            ]

        # Last migration date (simplified - would query migration history)
        last_migration_date = None
        if table_exists:
            last_migration_date = "2025-01-15T10:30:00"

        return ModelMigrationStatus(
            model_name=model_name,
            table_exists=table_exists,
            schema_matches=schema_matches,
            pending_migrations=pending_migrations,
            last_migration_date=last_migration_date,
            migration_required=migration_required,
        )

    def model_instances_count(self, model_name: str) -> int:
        """
        Get count of records for a model.

        Args:
            model_name: Name of the model

        Returns:
            Number of records in the table

        Example:
            >>> count = inspector.model_instances_count("User")
            >>> print(f"Found {count} users")
        """
        # This is a simplified implementation
        # Real implementation would execute COUNT query on the database
        # For now, return 0 as we don't have access to the actual database connection
        return 0

    def model_validation_rules(self, model_name: str) -> ModelValidationRules:
        """
        Get validation rules for a model.

        Args:
            model_name: Name of the model

        Returns:
            ModelValidationRules with constraints and field types

        Example:
            >>> rules = inspector.model_validation_rules("User")
            >>> print(rules.show())
            >>> print(rules.required_fields)
        """
        # Get model information
        model_info = self.model(model_name)

        # Extract validation rules from schema
        required_fields = []
        nullable_fields = []
        unique_constraints = []
        foreign_keys = {}
        field_types = {}

        for field_name, field_info in model_info.schema.items():
            # Field types
            field_types[field_name] = field_info.get("type", "unknown")

            # Required vs nullable
            if field_info.get("nullable", True):
                nullable_fields.append(field_name)
            else:
                required_fields.append(field_name)

            # Primary key is unique
            if field_info.get("primary_key", False):
                unique_constraints.append(field_name)

            # Foreign keys (simplified detection)
            if field_name.endswith("_id") and field_name != "id":
                referenced_table = field_name[:-3]  # Remove "_id"
                foreign_keys[field_name] = f"{referenced_table}.id"

        return ModelValidationRules(
            model_name=model_name,
            required_fields=required_fields,
            nullable_fields=nullable_fields,
            unique_constraints=unique_constraints,
            foreign_keys=foreign_keys,
            field_types=field_types,
        )

    def diagnose_error(self, error: Exception) -> ErrorDiagnosis:
        """
        Diagnose a DataFlow error and suggest Inspector commands.

        Args:
            error: Exception (preferably EnhancedDataFlowError)

        Returns:
            ErrorDiagnosis with suggested commands and context

        Example:
            >>> try:
            ...     # DataFlow operation that fails
            ... except Exception as e:
            ...     diagnosis = inspector.diagnose_error(e)
            ...     print(diagnosis.show())
        """
        # Import EnhancedDataFlowError locally to avoid circular dependency
        try:
            from dataflow.exceptions import EnhancedDataFlowError
        except ImportError:
            EnhancedDataFlowError = None

        # Extract error information
        error_code = "UNKNOWN"
        error_type = type(error).__name__
        affected_component = None
        inspector_commands = []
        context_hints = {}
        recommended_actions = []

        # Check if it's an EnhancedDataFlowError
        if EnhancedDataFlowError and isinstance(error, EnhancedDataFlowError):
            error_code = error.error_code
            error_type = error.__class__.__name__
            context_hints = dict(error.context)

            # Extract affected component from context
            if "node_id" in context_hints:
                affected_component = context_hints["node_id"]
            elif "model_name" in context_hints:
                affected_component = context_hints["model_name"]
            elif "workflow_id" in context_hints:
                affected_component = context_hints["workflow_id"]

        # Generate Inspector command suggestions based on error type
        inspector_commands = self._suggest_inspector_commands(
            error_code, error_type, context_hints
        )

        # Generate recommended actions
        recommended_actions = self._suggest_error_actions(
            error_code, error_type, context_hints
        )

        return ErrorDiagnosis(
            error_code=error_code,
            error_type=error_type,
            affected_component=affected_component,
            inspector_commands=inspector_commands,
            context_hints=context_hints,
            recommended_actions=recommended_actions,
        )

    def _suggest_inspector_commands(
        self, error_code: str, error_type: str, context: Dict[str, Any]
    ) -> List[str]:
        """
        Suggest Inspector commands based on error type.

        Args:
            error_code: Error code (e.g., "DF-101")
            error_type: Error type name
            context: Error context dictionary

        Returns:
            List of suggested Inspector commands
        """
        commands = []

        # Parameter-related errors
        if "parameter" in error_code.lower() or "param" in error_type.lower():
            if "node_id" in context:
                commands.append(
                    f"inspector.node('{context['node_id']}')  # Check node parameters"
                )
                commands.append(
                    f"inspector.trace_parameter('{context['node_id']}', '<param>')  # Trace parameter source"
                )
            commands.append("inspector.validate_connections()  # Check all connections")

        # Connection-related errors
        if "connection" in error_code.lower() or "connection" in error_type.lower():
            if "node_id" in context:
                commands.append(
                    f"inspector.connections('{context['node_id']}')  # List node connections"
                )
            commands.append(
                "inspector.connection_graph()  # View full connection graph"
            )
            commands.append(
                "inspector.find_broken_connections()  # Find broken connections"
            )

        # Model-related errors
        if "model" in error_code.lower() or "model" in error_type.lower():
            if "model_name" in context:
                commands.append(
                    f"inspector.model('{context['model_name']}')  # Check model schema"
                )
                commands.append(
                    f"inspector.model_validation_rules('{context['model_name']}')  # Check validation"
                )
            commands.append("inspector.list_models()  # List all available models")

        # Migration-related errors
        if "migration" in error_code.lower() or "migration" in error_type.lower():
            if "model_name" in context:
                commands.append(
                    f"inspector.model_migration_status('{context['model_name']}')  # Check migration status"
                )

        # Workflow-related errors
        if "workflow" in error_code.lower() or "workflow" in error_type.lower():
            commands.append("inspector.workflow_summary()  # Get workflow overview")
            commands.append(
                "inspector.workflow_validation_report()  # Validate workflow structure"
            )
            commands.append("inspector.execution_order()  # Check execution order")

        # If no specific commands, suggest general debugging
        if not commands:
            commands.append(
                "inspector.workflow_summary()  # Start with workflow overview"
            )
            commands.append("inspector.validate_connections()  # Check connections")

        return commands

    def _suggest_error_actions(
        self, error_code: str, error_type: str, context: Dict[str, Any]
    ) -> List[str]:
        """
        Suggest actions to fix the error.

        Args:
            error_code: Error code (e.g., "DF-101")
            error_type: Error type name
            context: Error context dictionary

        Returns:
            List of recommended actions
        """
        actions = []

        # Parameter-related errors
        if "parameter" in error_code.lower():
            actions.append("Verify all required parameters are provided in the node")
            actions.append("Check parameter types match expected types")
            if "parameter_name" in context:
                actions.append(
                    f"Ensure '{context['parameter_name']}' is connected from a source node"
                )

        # Connection-related errors
        if "connection" in error_code.lower():
            actions.append("Verify connections use correct parameter names")
            actions.append("Check source and target nodes exist in the workflow")
            actions.append("Ensure parameter types are compatible")

        # Model-related errors
        if "model" in error_code.lower():
            actions.append("Verify model schema matches database table")
            actions.append("Check all required fields are defined")
            actions.append("Run migrations if schema has changed")

        # Default actions
        if not actions:
            actions.append("Review error message and context for specific details")
            actions.append("Use Inspector commands above to investigate the issue")
            actions.append("Check DataFlow documentation for error code details")

        return actions

    def node(self, node_id: str) -> NodeInfo:
        """
        Get detailed information about a specific node.

        Args:
            node_id: Node identifier

        Returns:
            NodeInfo instance with parameters and connections

        Example:
            >>> info = inspector.node("user_create")
            >>> print(info.show())
            >>> print(info.expected_params)
        """
        # Parse node ID to extract model and type
        # This is simplified - real implementation would query DataFlow
        parts = node_id.split("_")
        if len(parts) >= 2:
            model_name = parts[0].title()
            node_type = "_".join(parts[1:])
        else:
            model_name = "Unknown"
            node_type = "unknown"

        # Get expected parameters based on node type
        expected_params = {}
        if node_type == "create":
            expected_params = {
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Dictionary containing model fields",
                }
            }
        elif node_type == "read_by_id":
            expected_params = {
                "id": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                }
            }
        elif node_type == "update":
            expected_params = {
                "id": {
                    "required": True,
                    "type": "int/str",
                    "description": "Primary key value",
                },
                "data": {
                    "required": True,
                    "type": "dict",
                    "description": "Fields to update",
                },
            }

        # Output parameters
        output_params = {}
        if node_type in ["create", "read", "read_by_id", "update"]:
            output_params = {
                "result": {"type": "dict", "description": f"{model_name} instance"}
            }
        elif node_type == "delete":
            output_params = {
                "success": {"type": "bool", "description": "Whether deletion succeeded"}
            }

        # Usage example
        usage_example = f"""
# Add node to workflow
workflow.add_node("{model_name}{node_type.title().replace('_', '')}Node", "{node_id}", {{}})

# Connect parameter
workflow.add_connection("source_node", "output", "{node_id}", "data")

# Execute
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
"""

        return NodeInfo(
            node_id=node_id,
            node_type=node_type,
            model_name=model_name,
            expected_params=expected_params,
            output_params=output_params,
            usage_example=usage_example.strip(),
        )

    def instance(self) -> InstanceInfo:
        """
        Get information about the DataFlow instance.

        Returns:
            InstanceInfo with configuration and status

        Example:
            >>> info = inspector.instance()
            >>> print(info.show())
            >>> print(info.health)
        """
        # Get configuration
        config = {}
        config_attrs = [
            "enable_audit",
            "migration_strategy",
            "debug_mode",
            "pool_size",
            "max_overflow",
            "connection_validation",
        ]
        for attr in config_attrs:
            if hasattr(self.db, attr):
                config[attr] = getattr(self.db, attr)

        # Get models
        models = getattr(self.db, "_models", {})

        # Get migration info
        migrations = {
            "strategy": getattr(self.db, "migration_strategy", "unknown"),
            "pending": 0,  # This would query actual pending migrations
            "applied": 0,  # This would query applied migrations
        }

        # Get health status
        health = {"status": "healthy", "issues": []}

        # Get database URL
        database_url = getattr(self.db, "database_url", "unknown")

        # Get instance name
        name = getattr(self.studio, "name", "DataFlow")

        return InstanceInfo(
            name=name,
            config=config,
            models=models,
            migrations=migrations,
            health=health,
            database_url=database_url,
        )

    def workflow(self, workflow: Any) -> WorkflowInfo:
        """
        Get information about a workflow using DataFlow nodes.

        Args:
            workflow: WorkflowBuilder instance

        Returns:
            WorkflowInfo with nodes and parameter flow

        Example:
            >>> info = inspector.workflow(my_workflow)
            >>> print(info.show())
            >>> print(info.dataflow_nodes)
        """
        # This would analyze the workflow to find DataFlow nodes
        # and trace parameter flow
        workflow_id = getattr(workflow, "workflow_id", "unknown")

        # Extract DataFlow nodes (simplified)
        dataflow_nodes = []

        # Build parameter flow graph (simplified)
        parameter_flow = {}

        # Validation issues (simplified)
        validation_issues = []

        return WorkflowInfo(
            workflow_id=workflow_id,
            dataflow_nodes=dataflow_nodes,
            parameter_flow=parameter_flow,
            validation_issues=validation_issues,
        )

    def connections(self, node_id: Optional[str] = None) -> List[ConnectionInfo]:
        """
        List all connections or connections for a specific node.

        Args:
            node_id: Optional node ID to filter connections (shows incoming + outgoing)

        Returns:
            List of ConnectionInfo instances

        Example:
            >>> # List all connections
            >>> all_conns = inspector.connections()
            >>> for conn in all_conns:
            ...     print(conn.show())
            >>>
            >>> # List connections for specific node
            >>> user_conns = inspector.connections("create_user")
            >>> print(f"Found {len(user_conns)} connections for create_user")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return []

        connections = []
        workflow_connections = getattr(workflow, "connections", [])

        for conn in workflow_connections:
            # Extract connection details - handle both dict and Pydantic objects
            if hasattr(conn, "get"):
                # Dict-like object
                source_node = conn.get("source_node", "")
                source_param = conn.get("source_parameter", "")
                target_node = conn.get("target_node", "")
                target_param = conn.get("target_parameter", "")
            else:
                # Pydantic object - access fields directly
                if hasattr(conn, "__dict__"):
                    conn_dict = conn.__dict__
                elif hasattr(conn, "model_dump"):
                    conn_dict = conn.model_dump()
                else:
                    conn_dict = {}

                # Get from the dict - built workflows use source_output/target_input
                source_node = conn_dict.get("source_node", "")
                source_param = (
                    conn_dict.get("source_output")
                    or conn_dict.get("source_parameter")
                    or ""
                )
                target_node = conn_dict.get("target_node", "")
                target_param = (
                    conn_dict.get("target_input")
                    or conn_dict.get("target_parameter")
                    or ""
                )

            # Filter by node_id if provided
            if node_id and source_node != node_id and target_node != node_id:
                continue

            # Create ConnectionInfo
            conn_info = ConnectionInfo(
                source_node=source_node,
                source_parameter=source_param,
                target_node=target_node,
                target_parameter=target_param,
                is_valid=True,  # Will be updated by validation if needed
            )

            connections.append(conn_info)

        return connections

    def connection_chain(self, from_node: str, to_node: str) -> List[ConnectionInfo]:
        """
        Trace connection path between two nodes using BFS.

        Finds the shortest path of connections from from_node to to_node.

        Args:
            from_node: Source node ID
            to_node: Target node ID

        Returns:
            List of ConnectionInfo instances representing the path,
            empty list if no path exists

        Example:
            >>> # Find path from node A to node C
            >>> path = inspector.connection_chain("node_a", "node_c")
            >>> if path:
            ...     print(f"Found path with {len(path)} connections:")
            ...     for conn in path:
            ...         print(f"  {conn.show()}")
            ... else:
            ...     print("No path found")
        """
        if not hasattr(self, "workflow") or self.workflow is None:
            return []

        # Build adjacency list for BFS
        graph: Dict[str, List[tuple]] = {}
        all_connections = self.connections()

        for conn in all_connections:
            if conn.source_node not in graph:
                graph[conn.source_node] = []
            graph[conn.source_node].append((conn.target_node, conn))

        # BFS to find shortest path
        queue = deque([(from_node, [])])
        visited: Set[str] = {from_node}

        while queue:
            current_node, path = queue.popleft()

            # Found target
            if current_node == to_node:
                return path

            # Explore neighbors
            for next_node, conn in graph.get(current_node, []):
                if next_node not in visited:
                    visited.add(next_node)
                    queue.append((next_node, path + [conn]))

        # No path found
        return []

    def connection_graph(self) -> ConnectionGraph:
        """
        Get full workflow connection graph with topology analysis.

        Analyzes the complete connection structure including:
        - All nodes and connections
        - Entry points (nodes with no inputs)
        - Exit points (nodes with no outputs)
        - Detected cycles

        Returns:
            ConnectionGraph instance with complete topology information

        Example:
            >>> graph = inspector.connection_graph()
            >>> print(graph.show())
            >>>
            >>> # Check for cycles
            >>> if graph.cycles:
            ...     print(f"Warning: {len(graph.cycles)} cycles detected!")
            >>>
            >>> # Find entry points
            >>> print(f"Workflow starts at: {', '.join(graph.entry_points)}")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return ConnectionGraph(
                nodes=[],
                connections=[],
                entry_points=[],
                exit_points=[],
                cycles=[],
            )

        # Get all connections
        all_connections = self.connections()

        # Extract all nodes
        nodes: Set[str] = set()
        for conn in all_connections:
            nodes.add(conn.source_node)
            nodes.add(conn.target_node)

        # Build adjacency lists for incoming/outgoing connections
        incoming: Dict[str, List[str]] = {node: [] for node in nodes}
        outgoing: Dict[str, List[str]] = {node: [] for node in nodes}

        for conn in all_connections:
            incoming[conn.target_node].append(conn.source_node)
            outgoing[conn.source_node].append(conn.target_node)

        # Find entry and exit points
        entry_points = [node for node in nodes if not incoming[node]]
        exit_points = [node for node in nodes if not outgoing[node]]

        # Detect cycles using DFS
        cycles = self._detect_cycles(outgoing)

        return ConnectionGraph(
            nodes=sorted(list(nodes)),
            connections=all_connections,
            entry_points=sorted(entry_points),
            exit_points=sorted(exit_points),
            cycles=cycles,
        )

    def _detect_cycles(self, graph: Dict[str, List[str]]) -> List[List[str]]:
        """
        Detect cycles in a directed graph using DFS.

        Args:
            graph: Adjacency list representation {node: [neighbors]}

        Returns:
            List of cycles, where each cycle is a list of node IDs
        """
        cycles = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:]
                    if cycle not in cycles:
                        cycles.append(cycle[:])

            path.pop()
            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node)

        return cycles

    def validate_connections(self) -> List[ConnectionInfo]:
        """
        Check all connections are valid, return invalid ones.

        Validates:
        - Source parameter exists on source node
        - Target parameter exists on target node
        - Type compatibility (if type information available)

        Returns:
            List of invalid ConnectionInfo instances with validation messages

        Example:
            >>> invalid = inspector.validate_connections()
            >>> if invalid:
            ...     print(f"Found {len(invalid)} invalid connections:")
            ...     for conn in invalid:
            ...         print(conn.show())
            ... else:
            ...     print("All connections are valid!")
        """
        if not hasattr(self, "workflow") or self.workflow is None:
            return []

        invalid_connections = []
        all_connections = self.connections()

        # Get workflow nodes for validation
        workflow_nodes = getattr(self.workflow, "nodes", {})

        for conn in all_connections:
            is_valid = True
            issues = []

            # Check source node exists
            if conn.source_node not in workflow_nodes:
                is_valid = False
                issues.append(f"Source node '{conn.source_node}' not found in workflow")

            # Check target node exists
            if conn.target_node not in workflow_nodes:
                is_valid = False
                issues.append(f"Target node '{conn.target_node}' not found in workflow")

            # Check parameter existence if nodes exist
            if conn.source_node in workflow_nodes:
                source_node_config = workflow_nodes[conn.source_node]
                # Note: Parameter validation would require node type introspection
                # For now, we check if the parameter is in the node config
                if hasattr(source_node_config, "get_parameters"):
                    params = source_node_config.get_parameters()
                    if conn.source_parameter not in params:
                        is_valid = False
                        issues.append(
                            f"Source parameter '{conn.source_parameter}' not found in node '{conn.source_node}'"
                        )

            if conn.target_node in workflow_nodes:
                target_node_config = workflow_nodes[conn.target_node]
                if hasattr(target_node_config, "get_parameters"):
                    params = target_node_config.get_parameters()
                    if conn.target_parameter not in params:
                        is_valid = False
                        issues.append(
                            f"Target parameter '{conn.target_parameter}' not found in node '{conn.target_node}'"
                        )

            # Mark as invalid if issues found
            if not is_valid:
                conn.is_valid = False
                conn.validation_message = "; ".join(issues)
                invalid_connections.append(conn)

        return invalid_connections

    def find_broken_connections(self) -> List[ConnectionInfo]:
        """
        Identify missing/invalid connections with reasons.

        Checks for common connection errors:
        - Missing required connections
        - Invalid parameter types
        - Circular dependencies
        - Disconnected nodes

        Returns:
            List of ConnectionInfo instances with validation messages

        Example:
            >>> broken = inspector.find_broken_connections()
            >>> if broken:
            ...     print(f"Found {len(broken)} broken connections:")
            ...     for conn in broken:
            ...         print(f"  {conn.show()}")
            ...         print(f"  Issue: {conn.validation_message}")
            ... else:
            ...     print("No broken connections found!")
        """
        if not hasattr(self, "workflow") or self.workflow is None:
            return []

        broken_connections = []

        # Check for invalid connections (existing validation)
        invalid = self.validate_connections()
        broken_connections.extend(invalid)

        # Check for cycles (potential issues)
        graph = self.connection_graph()
        if graph.cycles:
            # Add cycle information to broken connections
            for cycle in graph.cycles:
                cycle_str = " -> ".join(cycle + [cycle[0]])
                conn_info = ConnectionInfo(
                    source_node=cycle[-1],
                    source_parameter="(cycle)",
                    target_node=cycle[0],
                    target_parameter="(cycle)",
                    is_valid=False,
                    validation_message=f"Circular dependency detected: {cycle_str}",
                )
                broken_connections.append(conn_info)

        # Check for disconnected nodes (nodes not in any connection)
        workflow_nodes = set(getattr(self.workflow, "nodes", {}).keys())
        connected_nodes = set()
        for conn in self.connections():
            connected_nodes.add(conn.source_node)
            connected_nodes.add(conn.target_node)

        disconnected = workflow_nodes - connected_nodes
        for node in disconnected:
            conn_info = ConnectionInfo(
                source_node=node,
                source_parameter="(none)",
                target_node="(none)",
                target_parameter="(none)",
                is_valid=False,
                validation_message=f"Node '{node}' has no connections (isolated node)",
            )
            broken_connections.append(conn_info)

        return broken_connections

    def trace_parameter(self, node_id: str, parameter_name: str) -> ParameterTrace:
        """
        Trace parameter back to its source using DFS.

        Follows connections backward from the node to find the parameter's origin,
        tracking all transformations (dot notation, mapping changes) along the way.

        Args:
            node_id: Node identifier
            parameter_name: Parameter name to trace

        Returns:
            ParameterTrace with complete trace information

        Example:
            >>> trace = inspector.trace_parameter("create_user", "email")
            >>> print(trace.show())
            >>> print(f"Source: {trace.source_node}")
            >>> print(f"Transformations: {len(trace.transformations)}")
        """
        if not hasattr(self, "workflow") or self.workflow is None:
            return ParameterTrace(
                parameter_name=parameter_name,
                is_complete=False,
                missing_sources=["No workflow attached to inspector"],
            )

        # Build reverse connection map (target -> source)
        reverse_connections: Dict[str, List[tuple]] = {}
        all_connections = self.connections()

        for conn in all_connections:
            key = (conn.target_node, conn.target_parameter)
            if key not in reverse_connections:
                reverse_connections[key] = []
            reverse_connections[key].append((conn.source_node, conn.source_parameter))

        # DFS to trace parameter back to source
        visited: Set[tuple] = set()
        transformations: List[Dict[str, Any]] = []
        source_node: Optional[str] = None
        source_parameter: Optional[str] = None
        is_complete = True
        missing_sources: List[str] = []

        def dfs(current_node: str, current_param: str, depth: int = 0) -> None:
            nonlocal source_node, source_parameter, is_complete

            # Prevent infinite loops
            key = (current_node, current_param)
            if key in visited:
                return
            visited.add(key)

            # Check for source connection
            if key not in reverse_connections:
                # No upstream connection - this is the source (or workflow input)
                if source_node is None:
                    # Only set as source if we've traced back at least one step
                    # Otherwise it's a workflow input (no source node)
                    if depth > 0:
                        source_node = current_node
                        source_parameter = current_param
                return

            # Follow connections backward (only take first connection for DFS)
            src_node, src_param = reverse_connections[key][0]

            # Track transformations
            if src_param != current_param:
                # Check for dot notation
                if "." in src_param:
                    transformations.insert(
                        0,
                        {
                            "type": "dot_notation",
                            "details": f"{src_param} → {current_param}",
                            "from": src_param,
                            "to": current_param,
                        },
                    )
                else:
                    # Parameter mapping/renaming
                    transformations.insert(
                        0,
                        {
                            "type": "mapping",
                            "details": f"{src_param} → {current_param}",
                            "from": src_param,
                            "to": current_param,
                        },
                    )

            # Continue tracing
            dfs(src_node, src_param, depth + 1)

        # Start DFS from target node/parameter
        dfs(node_id, parameter_name, depth=0)

        # Check if trace is complete
        if not source_node and (node_id, parameter_name) not in reverse_connections:
            # This is a workflow input (no upstream connection)
            is_complete = True  # It's complete, just has no source
            source_node = None
            source_parameter = None

        return ParameterTrace(
            parameter_name=parameter_name,
            source_node=source_node,
            source_parameter=source_parameter,
            transformations=transformations,
            is_complete=is_complete,
            missing_sources=missing_sources,
        )

    def parameter_flow(self, from_node: str, parameter: str) -> List[ParameterTrace]:
        """
        Show how parameter flows forward through workflow.

        Follows connections forward from the source node to track how the parameter
        flows to downstream nodes, including all transformations and name changes.

        Args:
            from_node: Source node ID
            parameter: Parameter name to trace forward

        Returns:
            List of ParameterTrace instances for all paths the parameter takes

        Example:
            >>> traces = inspector.parameter_flow("fetch_user", "user_data")
            >>> print(f"Parameter flows to {len(traces)} downstream nodes")
            >>> for trace in traces:
            ...     print(f"  → {trace.parameter_name}")
        """
        if not hasattr(self, "workflow") or self.workflow is None:
            return []

        # Build forward connection map (source -> targets)
        forward_connections: Dict[tuple, List[tuple]] = {}
        all_connections = self.connections()

        for conn in all_connections:
            key = (conn.source_node, conn.source_parameter)
            if key not in forward_connections:
                forward_connections[key] = []
            forward_connections[key].append((conn.target_node, conn.target_parameter))

        # BFS to trace parameter forward
        traces: List[ParameterTrace] = []
        queue: deque = deque([(from_node, parameter, [])])
        visited: Set[tuple] = set()

        while queue:
            current_node, current_param, transformations = queue.popleft()

            # Prevent infinite loops
            key = (current_node, current_param)
            if key in visited:
                continue
            visited.add(key)

            # Check for outgoing connections
            if key not in forward_connections:
                # No downstream connections - this is an endpoint
                if current_node != from_node or current_param != parameter:
                    traces.append(
                        ParameterTrace(
                            parameter_name=current_param,
                            source_node=from_node,
                            source_parameter=parameter,
                            transformations=transformations[:],
                            is_complete=True,
                        )
                    )
                continue

            # Follow connections forward
            for target_node, target_param in forward_connections[key]:
                new_transformations = transformations[:]

                # Track transformations
                if target_param != current_param:
                    # Check for dot notation
                    if "." in target_param:
                        new_transformations.append(
                            {
                                "type": "dot_notation",
                                "details": f"{current_param} → {target_param}",
                                "from": current_param,
                                "to": target_param,
                            }
                        )
                    else:
                        # Parameter mapping/renaming
                        new_transformations.append(
                            {
                                "type": "mapping",
                                "details": f"{current_param} → {target_param}",
                                "from": current_param,
                                "to": target_param,
                            }
                        )

                queue.append((target_node, target_param, new_transformations))

        return traces

    def find_parameter_source(self, node_id: str, parameter: str) -> Optional[str]:
        """
        Find original source node for a parameter.

        Simple version of trace_parameter that returns just the source node ID,
        useful for quick lookups without needing full trace information.

        Args:
            node_id: Node identifier
            parameter: Parameter name

        Returns:
            Source node ID, or None if parameter has no source (workflow input)

        Example:
            >>> source = inspector.find_parameter_source("create_user", "email")
            >>> if source:
            ...     print(f"Email comes from node: {source}")
            ... else:
            ...     print("Email is a workflow input")
        """
        trace = self.trace_parameter(node_id, parameter)
        return trace.source_node

    def parameter_dependencies(self, node_id: str) -> Dict[str, ParameterTrace]:
        """
        List all parameters this node depends on with their traces.

        Gets all required parameters for the node and traces each one back to
        its source, providing a complete dependency map.

        Args:
            node_id: Node identifier

        Returns:
            Dict mapping parameter name to ParameterTrace

        Example:
            >>> deps = inspector.parameter_dependencies("create_user")
            >>> print(f"Node has {len(deps)} parameter dependencies")
            >>> for param_name, trace in deps.items():
            ...     print(f"  {param_name} ← {trace.source_node}")
        """
        if not hasattr(self, "workflow") or self.workflow is None:
            return {}

        dependencies: Dict[str, ParameterTrace] = {}

        # Get all incoming connections for this node
        incoming_connections = [
            conn for conn in self.connections() if conn.target_node == node_id
        ]

        # Trace each parameter
        seen_params: Set[str] = set()
        for conn in incoming_connections:
            param_name = conn.target_parameter

            # Avoid duplicate traces
            if param_name in seen_params:
                continue
            seen_params.add(param_name)

            # Trace parameter back to source
            trace = self.trace_parameter(node_id, param_name)
            dependencies[param_name] = trace

        return dependencies

    def parameter_consumers(self, node_id: str, output_param: str) -> List[str]:
        """
        List all nodes that consume this output parameter.

        Follows connections forward from the node to find all consumers of a
        specific output parameter.

        Args:
            node_id: Node identifier
            output_param: Output parameter name

        Returns:
            List of consumer node IDs

        Example:
            >>> consumers = inspector.parameter_consumers("fetch_user", "user_data")
            >>> print(f"user_data is consumed by {len(consumers)} nodes:")
            >>> for consumer in consumers:
            ...     print(f"  - {consumer}")
        """
        if not hasattr(self, "workflow") or self.workflow is None:
            return []

        consumers: Set[str] = set()

        # Get all outgoing connections from this node/parameter
        for conn in self.connections():
            if conn.source_node == node_id and conn.source_parameter == output_param:
                consumers.add(conn.target_node)

        return sorted(list(consumers))

    def node_dependencies(self, node_id: str) -> List[str]:
        """
        List all nodes this node depends on (upstream dependencies).

        Follows incoming connections to find all direct dependencies.

        Args:
            node_id: Node identifier

        Returns:
            List of node IDs that this node depends on (sorted)

        Example:
            >>> deps = inspector.node_dependencies("merge_data")
            >>> print(f"{len(deps)} upstream dependencies")
            >>> for dep in deps:
            ...     print(f"  - {dep}")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return []

        dependencies: Set[str] = set()

        # Get all incoming connections to this node
        for conn in self.connections():
            if conn.target_node == node_id:
                dependencies.add(conn.source_node)

        return sorted(list(dependencies))

    def node_dependents(self, node_id: str) -> List[str]:
        """
        List all nodes that depend on this node (downstream dependents).

        Follows outgoing connections to find all direct dependents.

        Args:
            node_id: Node identifier

        Returns:
            List of node IDs that depend on this node (sorted)

        Example:
            >>> dependents = inspector.node_dependents("fetch_data")
            >>> print(f"{len(dependents)} downstream dependents")
            >>> for dep in dependents:
            ...     print(f"  - {dep}")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return []

        dependents: Set[str] = set()

        # Get all outgoing connections from this node
        for conn in self.connections():
            if conn.source_node == node_id:
                dependents.add(conn.target_node)

        return sorted(list(dependents))

    def execution_order(self) -> List[str]:
        """
        Get workflow execution order using topological sort.

        Uses Kahn's algorithm (BFS-based topological sort) to determine
        the correct execution order for workflow nodes.

        Returns:
            List of node IDs in execution order

        Example:
            >>> order = inspector.execution_order()
            >>> print("Execution order:")
            >>> for i, node in enumerate(order, 1):
            ...     print(f"  {i}. {node}")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return []

        # Build adjacency list and in-degree count
        graph = self.connection_graph()
        nodes = set(graph.nodes)

        if not nodes:
            return []

        # Build in-degree count
        in_degree: Dict[str, int] = {node: 0 for node in nodes}
        adjacency: Dict[str, List[str]] = {node: [] for node in nodes}

        for conn in graph.connections:
            adjacency[conn.source_node].append(conn.target_node)
            in_degree[conn.target_node] += 1

        # Kahn's algorithm: Start with nodes that have no dependencies
        queue: deque = deque([node for node in nodes if in_degree[node] == 0])
        execution_order: List[str] = []

        while queue:
            # Process node with no dependencies
            current = queue.popleft()
            execution_order.append(current)

            # Reduce in-degree for dependents
            for neighbor in adjacency[current]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # If execution order doesn't include all nodes, there's a cycle
        if len(execution_order) != len(nodes):
            # Return partial order + remaining nodes (cycle detected)
            remaining = sorted(list(nodes - set(execution_order)))
            execution_order.extend(remaining)

        return execution_order

    def node_schema(self, node_id: str) -> Dict[str, Any]:
        """
        Get input and output schema for a node.

        Analyzes the node's configuration and connections to determine
        its expected inputs and outputs.

        Args:
            node_id: Node identifier

        Returns:
            Dict with "inputs" and "outputs" keys containing parameter information

        Example:
            >>> schema = inspector.node_schema("process_data")
            >>> print(f"Inputs: {list(schema['inputs'].keys())}")
            >>> print(f"Outputs: {list(schema['outputs'].keys())}")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return {"node_id": node_id, "inputs": {}, "outputs": {}, "node_type": None}

        # Get node configuration from workflow
        workflow_nodes = getattr(workflow, "nodes", {})
        node_config = workflow_nodes.get(node_id)

        # Extract inputs from incoming connections
        inputs: Dict[str, Any] = {}
        for conn in self.connections():
            if conn.target_node == node_id:
                inputs[conn.target_parameter] = {
                    "source": conn.source_node,
                    "source_param": conn.source_parameter,
                    "type": conn.target_type or "any",
                }

        # Extract outputs from outgoing connections
        outputs: Dict[str, Any] = {}
        for conn in self.connections():
            if conn.source_node == node_id:
                if conn.source_parameter not in outputs:
                    outputs[conn.source_parameter] = {
                        "consumers": [],
                        "type": conn.source_type or "any",
                    }
                outputs[conn.source_parameter]["consumers"].append(conn.target_node)

        # Get node type if available
        node_type = None
        if node_config:
            node_type = getattr(node_config, "node_type", None)
            if not node_type and hasattr(node_config, "__class__"):
                node_type = node_config.__class__.__name__

        return {
            "node_id": node_id,
            "inputs": inputs,
            "outputs": outputs,
            "node_type": node_type,
        }

    def compare_nodes(self, node_id1: str, node_id2: str) -> Dict[str, Any]:
        """
        Compare two nodes in the workflow.

        Analyzes differences and similarities between two nodes including
        their schemas, connections, and configurations.

        Args:
            node_id1: First node identifier
            node_id2: Second node identifier

        Returns:
            Dict with "node1", "node2", "differences", and "similarities" keys

        Example:
            >>> comparison = inspector.compare_nodes("node_a", "node_b")
            >>> if comparison["differences"]:
            ...     print("Nodes differ in:", list(comparison["differences"].keys()))
        """
        workflow = self._get_workflow()
        if workflow is None:
            return {
                "node1": node_id1,
                "node2": node_id2,
                "differences": {},
                "similarities": {},
            }

        # Get schemas for both nodes
        schema1 = self.node_schema(node_id1)
        schema2 = self.node_schema(node_id2)

        differences: Dict[str, Any] = {}
        similarities: Dict[str, Any] = {}

        # Compare node types
        if schema1["node_type"] != schema2["node_type"]:
            differences["node_type"] = {
                node_id1: schema1["node_type"],
                node_id2: schema2["node_type"],
            }
        else:
            similarities["node_type"] = schema1["node_type"]

        # Compare inputs
        inputs1 = set(schema1["inputs"].keys())
        inputs2 = set(schema2["inputs"].keys())

        if inputs1 != inputs2:
            differences["inputs"] = {
                "unique_to_" + node_id1: sorted(list(inputs1 - inputs2)),
                "unique_to_" + node_id2: sorted(list(inputs2 - inputs1)),
                "common": sorted(list(inputs1 & inputs2)),
            }
        elif inputs1:
            similarities["inputs"] = sorted(list(inputs1))

        # Compare outputs
        outputs1 = set(schema1["outputs"].keys())
        outputs2 = set(schema2["outputs"].keys())

        if outputs1 != outputs2:
            differences["outputs"] = {
                "unique_to_" + node_id1: sorted(list(outputs1 - outputs2)),
                "unique_to_" + node_id2: sorted(list(outputs2 - outputs1)),
                "common": sorted(list(outputs1 & outputs2)),
            }
        elif outputs1:
            similarities["outputs"] = sorted(list(outputs1))

        # Compare dependencies
        deps1 = set(self.node_dependencies(node_id1))
        deps2 = set(self.node_dependencies(node_id2))

        if deps1 != deps2:
            differences["dependencies"] = {
                "unique_to_" + node_id1: sorted(list(deps1 - deps2)),
                "unique_to_" + node_id2: sorted(list(deps2 - deps1)),
                "common": sorted(list(deps1 & deps2)),
            }
        elif deps1:
            similarities["dependencies"] = sorted(list(deps1))

        # Compare dependents
        dependents1 = set(self.node_dependents(node_id1))
        dependents2 = set(self.node_dependents(node_id2))

        if dependents1 != dependents2:
            differences["dependents"] = {
                "unique_to_" + node_id1: sorted(list(dependents1 - dependents2)),
                "unique_to_" + node_id2: sorted(list(dependents2 - dependents1)),
                "common": sorted(list(dependents1 & dependents2)),
            }
        elif dependents1:
            similarities["dependents"] = sorted(list(dependents1))

        return {
            "node1": schema1,
            "node2": schema2,
            "differences": differences,
            "similarities": similarities,
        }

    def watch_execution(
        self, workflow: Any, callback: Optional[callable] = None
    ) -> RuntimeState:
        """
        Monitor workflow execution in real-time.

        Sets up execution monitoring with optional callback for events.
        Note: Current implementation provides post-execution analysis.
        Full runtime integration requires hooks in LocalRuntime/AsyncLocalRuntime.

        Args:
            workflow: WorkflowBuilder instance to monitor
            callback: Optional callback function called for each event
                     Signature: callback(event: ExecutionEvent) -> None

        Returns:
            RuntimeState with execution information

        Example:
            >>> def on_event(event):
            ...     print(f"Event: {event.event_type} at {event.node_id}")
            >>>
            >>> state = inspector.watch_execution(workflow, on_event)
            >>> print(state.show())
        """
        # Register callback if provided
        if callback:
            self._execution_callbacks.append(callback)

        # Initialize runtime state from workflow structure
        execution_order_list = self.execution_order()

        self._runtime_state = RuntimeState(
            active_nodes=[],
            completed_nodes=[],
            pending_nodes=execution_order_list.copy(),
            execution_order=execution_order_list,
            current_node=None,
            parameter_values={},
            events=[],
        )

        return self._runtime_state

    def breakpoint_at_node(
        self, node_id: str, condition: Optional[str] = None
    ) -> BreakpointInfo:
        """
        Set a breakpoint at a specific node.

        Breakpoints pause execution (when runtime integration is available)
        and allow state inspection.

        Args:
            node_id: Node ID to set breakpoint at
            condition: Optional Python expression for conditional breakpoint
                      Example: "parameters['count'] > 100"

        Returns:
            BreakpointInfo describing the breakpoint

        Example:
            >>> bp = inspector.breakpoint_at_node("process_data")
            >>> print(bp.show())
            >>>
            >>> # Conditional breakpoint
            >>> bp = inspector.breakpoint_at_node(
            ...     "validate",
            ...     condition="parameters['status'] == 'error'"
            ... )
        """
        breakpoint = BreakpointInfo(
            node_id=node_id, condition=condition, enabled=True, hit_count=0
        )

        self._breakpoints[node_id] = breakpoint
        return breakpoint

    def inspect_runtime_state(self) -> Optional[RuntimeState]:
        """
        Get current workflow execution state.

        Returns the current runtime state including active/completed nodes,
        parameter values, and recent events.

        Returns:
            RuntimeState if execution is being monitored, None otherwise

        Example:
            >>> state = inspector.inspect_runtime_state()
            >>> if state:
            ...     print(f"Active: {state.active_nodes}")
            ...     print(f"Completed: {state.completed_nodes}")
            ...     print(state.show())
        """
        return self._runtime_state

    def parameter_values_at_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get actual parameter values at a specific node during execution.

        Returns the parameter values that were passed to the node during
        the most recent execution (if execution monitoring was enabled).

        Args:
            node_id: Node ID to get parameter values for

        Returns:
            Dict mapping parameter names to values, or None if not available

        Example:
            >>> values = inspector.parameter_values_at_node("process_data")
            >>> if values:
            ...     print(f"Parameters: {values}")
            ...     for param, value in values.items():
            ...         print(f"  {param}: {value}")
        """
        if self._runtime_state and node_id in self._runtime_state.parameter_values:
            return self._runtime_state.parameter_values[node_id]
        return None

    def get_breakpoints(self) -> List[BreakpointInfo]:
        """
        Get all configured breakpoints.

        Returns:
            List of all breakpoints

        Example:
            >>> breakpoints = inspector.get_breakpoints()
            >>> for bp in breakpoints:
            ...     print(bp.show())
        """
        return list(self._breakpoints.values())

    def remove_breakpoint(self, node_id: str) -> bool:
        """
        Remove a breakpoint at a specific node.

        Args:
            node_id: Node ID to remove breakpoint from

        Returns:
            True if breakpoint was removed, False if no breakpoint existed

        Example:
            >>> inspector.breakpoint_at_node("process_data")
            >>> inspector.remove_breakpoint("process_data")
            True
        """
        if node_id in self._breakpoints:
            del self._breakpoints[node_id]
            return True
        return False

    def clear_breakpoints(self) -> None:
        """
        Remove all breakpoints.

        Example:
            >>> inspector.clear_breakpoints()
        """
        self._breakpoints.clear()

    def get_execution_events(self) -> List[ExecutionEvent]:
        """
        Get all execution events captured during monitoring.

        Returns:
            List of execution events in chronological order

        Example:
            >>> events = inspector.get_execution_events()
            >>> for event in events:
            ...     print(event.show())
        """
        return self._execution_events.copy()

    def workflow_summary(self) -> WorkflowSummary:
        """
        Get high-level workflow overview.

        Provides a concise summary of workflow structure including node count,
        connections, entry/exit points, and complexity indicators.

        Returns:
            WorkflowSummary with overview information

        Example:
            >>> summary = inspector.workflow_summary()
            >>> print(summary.show())
            >>> print(f"Workflow has {summary.node_count} nodes")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return WorkflowSummary(
                node_count=0,
                connection_count=0,
                entry_points=[],
                exit_points=[],
                has_cycles=False,
                max_depth=0,
                complexity_score=0.0,
            )

        graph = self.connection_graph()

        # Calculate max depth using BFS
        max_depth = 0
        if graph.entry_points:
            # Build adjacency list
            adjacency: Dict[str, List[str]] = {node: [] for node in graph.nodes}
            for conn in graph.connections:
                adjacency[conn.source_node].append(conn.target_node)

            # BFS from entry points
            visited: Set[str] = set()
            queue: deque = deque([(node, 0) for node in graph.entry_points])

            while queue:
                current, depth = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)
                max_depth = max(max_depth, depth)

                for neighbor in adjacency.get(current, []):
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))

        # Calculate complexity score (nodes * avg_connections + depth)
        avg_connections = (
            len(graph.connections) / len(graph.nodes) if graph.nodes else 0
        )
        complexity_score = len(graph.nodes) * avg_connections + max_depth

        return WorkflowSummary(
            node_count=len(graph.nodes),
            connection_count=len(graph.connections),
            entry_points=sorted(graph.entry_points),
            exit_points=sorted(graph.exit_points),
            has_cycles=len(graph.cycles) > 0,
            max_depth=max_depth,
            complexity_score=complexity_score,
        )

    def workflow_metrics(self) -> WorkflowMetrics:
        """
        Get detailed workflow statistics.

        Analyzes workflow structure to provide comprehensive metrics including
        fan-out/fan-in, isolated nodes, bottlenecks, and critical path.

        Returns:
            WorkflowMetrics with detailed statistics

        Example:
            >>> metrics = inspector.workflow_metrics()
            >>> print(metrics.show())
            >>> if metrics.isolated_nodes:
            ...     print(f"Warning: {len(metrics.isolated_nodes)} isolated nodes")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return WorkflowMetrics(
                total_nodes=0,
                total_connections=0,
                avg_connections_per_node=0.0,
                max_fan_out=0,
                max_fan_in=0,
                isolated_nodes=[],
                bottleneck_nodes=[],
                critical_path_length=0,
            )

        graph = self.connection_graph()

        # Calculate fan-out and fan-in
        fan_out: Dict[str, int] = {node: 0 for node in graph.nodes}
        fan_in: Dict[str, int] = {node: 0 for node in graph.nodes}

        for conn in graph.connections:
            fan_out[conn.source_node] += 1
            fan_in[conn.target_node] += 1

        max_fan_out = max(fan_out.values()) if fan_out else 0
        max_fan_in = max(fan_in.values()) if fan_in else 0

        # Find isolated nodes (no connections)
        isolated = [
            node for node in graph.nodes if fan_out[node] == 0 and fan_in[node] == 0
        ]

        # Find bottleneck nodes (high fan-in or fan-out)
        threshold = max(3, len(graph.nodes) // 10)  # At least 3, or 10% of nodes
        bottlenecks = [
            node
            for node in graph.nodes
            if fan_out[node] > threshold or fan_in[node] > threshold
        ]

        # Calculate critical path (longest path from entry to exit)
        critical_path_length = self.workflow_summary().max_depth

        # Calculate average connections per node
        avg_connections = (
            len(graph.connections) / len(graph.nodes) if graph.nodes else 0.0
        )

        return WorkflowMetrics(
            total_nodes=len(graph.nodes),
            total_connections=len(graph.connections),
            avg_connections_per_node=avg_connections,
            max_fan_out=max_fan_out,
            max_fan_in=max_fan_in,
            isolated_nodes=sorted(isolated),
            bottleneck_nodes=sorted(bottlenecks),
            critical_path_length=critical_path_length,
        )

    def workflow_validation_report(self) -> WorkflowValidationReport:
        """
        Get comprehensive workflow validation report.

        Validates workflow structure and identifies errors, warnings, and
        informational issues. Checks for common problems like broken connections,
        missing parameters, isolated nodes, and performance concerns.

        Returns:
            WorkflowValidationReport with validation results

        Example:
            >>> report = inspector.workflow_validation_report()
            >>> print(report.show())
            >>> if not report.is_valid:
            ...     print("Workflow has validation errors!")
            ...     for issue in report.issues:
            ...         if issue.severity == "error":
            ...             print(f"  - {issue.message}")
        """
        workflow = self._get_workflow()
        issues: List[ValidationIssue] = []

        if workflow is None:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="structure",
                    node_id=None,
                    message="No workflow attached to inspector",
                    suggestion="Pass workflow to Inspector(studio, workflow=...)",
                )
            )
            return WorkflowValidationReport(
                is_valid=False,
                error_count=1,
                warning_count=0,
                info_count=0,
                issues=issues,
            )

        graph = self.connection_graph()

        # Check for empty workflow
        if not graph.nodes:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="structure",
                    node_id=None,
                    message="Workflow has no nodes",
                    suggestion="Add nodes with workflow.add_node()",
                )
            )

        # Check for isolated nodes
        fan_out: Dict[str, int] = {node: 0 for node in graph.nodes}
        fan_in: Dict[str, int] = {node: 0 for node in graph.nodes}

        for conn in graph.connections:
            fan_out[conn.source_node] += 1
            fan_in[conn.target_node] += 1

        isolated = [
            node for node in graph.nodes if fan_out[node] == 0 and fan_in[node] == 0
        ]
        for node in isolated:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="structure",
                    node_id=node,
                    message=f"Node '{node}' is isolated (no connections)",
                    suggestion="Connect node to workflow or remove if unused",
                )
            )

        # Check for cycles
        if graph.cycles:
            for cycle in graph.cycles:
                cycle_str = " → ".join(cycle)
                issues.append(
                    ValidationIssue(
                        severity="info",
                        category="structure",
                        node_id=cycle[0],
                        message=f"Cycle detected: {cycle_str}",
                        suggestion="Ensure cyclic workflow is intended (enable_cycles=True)",
                    )
                )

        # Check for missing entry points
        if not graph.entry_points:
            issues.append(
                ValidationIssue(
                    severity="error",
                    category="structure",
                    node_id=None,
                    message="No entry points found (all nodes have dependencies)",
                    suggestion="Ensure at least one node has no incoming connections",
                )
            )

        # Check for missing exit points
        if not graph.exit_points:
            issues.append(
                ValidationIssue(
                    severity="warning",
                    category="structure",
                    node_id=None,
                    message="No exit points found (all nodes have outgoing connections)",
                    suggestion="Check if workflow structure is correct",
                )
            )

        # Check for bottlenecks
        threshold = max(5, len(graph.nodes) // 5)  # At least 5, or 20% of nodes
        for node in graph.nodes:
            if fan_out[node] > threshold:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        category="performance",
                        node_id=node,
                        message=f"Node '{node}' has high fan-out ({fan_out[node]} connections)",
                        suggestion="Consider splitting into multiple nodes for better parallelism",
                    )
                )
            if fan_in[node] > threshold:
                issues.append(
                    ValidationIssue(
                        severity="info",
                        category="performance",
                        node_id=node,
                        message=f"Node '{node}' has high fan-in ({fan_in[node]} connections)",
                        suggestion="Node may be a bottleneck - consider optimization",
                    )
                )

        # Count by severity
        error_count = sum(1 for i in issues if i.severity == "error")
        warning_count = sum(1 for i in issues if i.severity == "warning")
        info_count = sum(1 for i in issues if i.severity == "info")

        return WorkflowValidationReport(
            is_valid=error_count == 0,
            error_count=error_count,
            warning_count=warning_count,
            info_count=info_count,
            issues=issues,
        )

    def workflow_visualization_data(self) -> WorkflowVisualizationData:
        """
        Get data for visualizing workflow as a graph.

        Provides node and edge data compatible with graph visualization
        libraries like networkx, graphviz, or D3.js.

        Returns:
            WorkflowVisualizationData with nodes, edges, and layout hints

        Example:
            >>> viz_data = inspector.workflow_visualization_data()
            >>> print(viz_data.show())
            >>> # Export to JSON for visualization
            >>> import json
            >>> json.dumps(viz_data.to_dict(), indent=2)
        """
        workflow = self._get_workflow()
        if workflow is None:
            return WorkflowVisualizationData(
                nodes=[], edges=[], layout_hints={"suggested_layout": "empty"}
            )

        graph = self.connection_graph()

        # Build node data
        nodes = []
        for node_id in graph.nodes:
            node_data = {
                "id": node_id,
                "label": node_id,
                "type": "workflow_node",
                "is_entry": node_id in graph.entry_points,
                "is_exit": node_id in graph.exit_points,
            }
            nodes.append(node_data)

        # Build edge data
        edges = []
        for i, conn in enumerate(graph.connections):
            edge_data = {
                "id": f"edge_{i}",
                "source": conn.source_node,
                "target": conn.target_node,
                "source_param": conn.source_parameter,
                "target_param": conn.target_parameter,
            }
            edges.append(edge_data)

        # Determine layout hints
        has_cycles = len(graph.cycles) > 0
        node_count = len(nodes)

        # Choose layout: empty for no nodes, circular for cycles, hierarchical otherwise
        if node_count == 0:
            suggested_layout = "empty"
        elif has_cycles:
            suggested_layout = "circular"
        else:
            suggested_layout = "hierarchical"

        layout_hints = {
            "suggested_layout": suggested_layout,
            "direction": "top-to-bottom",
            "node_count": node_count,
            "has_cycles": has_cycles,
            "entry_count": len(graph.entry_points),
            "exit_count": len(graph.exit_points),
        }

        return WorkflowVisualizationData(
            nodes=nodes, edges=edges, layout_hints=layout_hints
        )

    def workflow_performance_profile(self) -> WorkflowPerformanceProfile:
        """
        Get workflow performance characteristics.

        Analyzes workflow structure to estimate execution time, identify
        parallelization opportunities, and detect sequential bottlenecks.

        Returns:
            WorkflowPerformanceProfile with performance estimates

        Example:
            >>> profile = inspector.workflow_performance_profile()
            >>> print(profile.show())
            >>> print(f"Estimated time: {profile.estimated_execution_time_ms}ms")
            >>> print(f"Parallel potential: {profile.parallelization_potential:.1%}")
        """
        workflow = self._get_workflow()
        if workflow is None:
            return WorkflowPerformanceProfile(
                estimated_execution_time_ms=0.0,
                parallelization_potential=0.0,
                sequential_bottlenecks=[],
                parallel_stages=[],
                resource_requirements={
                    "memory_mb": 0,
                    "cpu_cores": 0,
                    "estimated_duration_seconds": 0.0,
                },
            )

        graph = self.connection_graph()
        summary = self.workflow_summary()

        # Estimate execution time (assume 10ms per node)
        base_time_per_node = 10.0
        estimated_time = summary.max_depth * base_time_per_node

        # Calculate parallelization potential
        # Potential = (total_nodes - critical_path) / total_nodes
        total_nodes = len(graph.nodes)
        if total_nodes > 0:
            parallelization_potential = (total_nodes - summary.max_depth) / total_nodes
        else:
            parallelization_potential = 0.0

        # Find sequential bottlenecks (nodes with high fan-in and fan-out)
        fan_out: Dict[str, int] = {node: 0 for node in graph.nodes}
        fan_in: Dict[str, int] = {node: 0 for node in graph.nodes}

        for conn in graph.connections:
            fan_out[conn.source_node] += 1
            fan_in[conn.target_node] += 1

        bottlenecks = [
            node for node in graph.nodes if fan_in[node] > 1 and fan_out[node] > 1
        ]

        # Identify parallel stages (nodes at same depth)
        # Build adjacency and calculate levels
        adjacency: Dict[str, List[str]] = {node: [] for node in graph.nodes}
        in_degree: Dict[str, int] = {node: 0 for node in graph.nodes}

        for conn in graph.connections:
            adjacency[conn.source_node].append(conn.target_node)
            in_degree[conn.target_node] += 1

        # BFS to find levels
        queue: deque = deque([(node, 0) for node in graph.entry_points])
        node_levels: Dict[str, int] = {}

        while queue:
            current, level = queue.popleft()
            if current in node_levels:
                node_levels[current] = max(node_levels[current], level)
            else:
                node_levels[current] = level

            for neighbor in adjacency.get(current, []):
                queue.append((neighbor, level + 1))

        # Group nodes by level (parallel stages)
        levels: Dict[int, List[str]] = {}
        for node, level in node_levels.items():
            if level not in levels:
                levels[level] = []
            levels[level].append(node)

        parallel_stages = [levels[i] for i in sorted(levels.keys())]

        # Estimate resource requirements
        resource_requirements = {
            "memory_mb": total_nodes * 10,  # Estimate 10MB per node
            "cpu_cores": min(
                len(max(parallel_stages, key=len)) if parallel_stages else 1, 8
            ),  # Max parallel nodes, capped at 8
            "estimated_duration_seconds": estimated_time / 1000,
        }

        return WorkflowPerformanceProfile(
            estimated_execution_time_ms=estimated_time,
            parallelization_potential=parallelization_potential,
            sequential_bottlenecks=sorted(bottlenecks),
            parallel_stages=parallel_stages,
            resource_requirements=resource_requirements,
        )

    def interactive(self):
        """
        Launch interactive debugging session.

        This starts an interactive Python shell with the inspector
        and useful utilities pre-loaded.

        Example:
            >>> inspector.interactive()
            # Interactive shell opens with inspector available
        """
        import code
        import readline  # noqa: F401 - enables history

        banner = """
DataFlow Inspector - Interactive Mode
======================================

Available objects:
  inspector - Inspector instance
  studio    - DataFlowStudio instance
  db        - DataFlow instance

Commands:
  # Model & Node Inspection
  inspector.model('ModelName')        - Inspect a model
  inspector.node('node_id')           - Inspect a node
  inspector.instance()                - Inspect DataFlow instance

  # Connection Analysis
  inspector.connections()             - List all connections
  inspector.connections('node_id')    - List connections for node
  inspector.connection_chain('A', 'B') - Find path between nodes
  inspector.connection_graph()        - Get full connection graph
  inspector.validate_connections()    - Check connection validity
  inspector.find_broken_connections() - Find broken connections

  # Parameter Tracing
  inspector.trace_parameter('node_id', 'param_name')        - Trace parameter to source
  inspector.parameter_flow('node_id', 'param_name')         - Trace parameter forward
  inspector.find_parameter_source('node_id', 'param_name')  - Find source node
  inspector.parameter_dependencies('node_id')               - List all dependencies
  inspector.parameter_consumers('node_id', 'output_param')  - List consumers

  # Node Analysis
  inspector.node_dependencies('node_id')     - List upstream dependencies
  inspector.node_dependents('node_id')       - List downstream dependents
  inspector.execution_order()                - Get topological execution order
  inspector.node_schema('node_id')           - Get node input/output schema
  inspector.compare_nodes('node_id1', 'node_id2')  - Compare two nodes

Press Ctrl+D to exit.
"""

        local_vars = {"inspector": self, "studio": self.studio, "db": self.db}

        code.interact(banner=banner, local=local_vars)
