"""
Connection Validation Layer (Layer 3)

This module implements comprehensive connection validation for DataFlow's strict mode.
Validates workflow connections at workflow.add_connection() time to catch configuration
errors early before workflow execution.

Validation Rules:
- Node Existence: Both source and destination nodes must exist in workflow
- Connection Structure: Valid source_output and destination_input parameters
- Dot Notation: Validate dot notation for nested field access
- Parameter Contracts: Source output should match destination input expectations

Integration: Called during workflow.add_connection() when strict_mode enabled
"""

from typing import Any, Dict, List, Optional, Set

from dataflow.validation.strict_mode import StrictModeConfig
from dataflow.validation.validators import ValidationError

# ============================================================================
# Constants
# ============================================================================

# Valid connection parameter types
VALID_CONNECTION_PARAMS = {
    "source_node",
    "source_output",
    "destination_node",
    "destination_input",
}

# Reserved output names that should not be used in dot notation
RESERVED_OUTPUTS = {"error", "success", "metadata", "_internal"}


# ============================================================================
# Validation Result Helper
# ============================================================================


class ConnectionValidationResult:
    """
    Connection validation result wrapper for individual validation checks.

    Can represent either success or failure with error details.
    """

    def __init__(
        self,
        success: bool = False,
        error_code: Optional[str] = None,
        message: Optional[str] = None,
        solution: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        self.success = success
        self.error_code = error_code
        self.message = message
        self.solution = solution or {}
        self.context = context or {}


# ============================================================================
# Node Existence Validation (STRICT_CONN_201)
# ============================================================================


def validate_node_existence(
    source_node: str, destination_node: str, existing_nodes: Set[str]
) -> List[ConnectionValidationResult]:
    """
    Validate that both source and destination nodes exist in workflow.

    Validation Rules:
    1. Source node must exist in workflow
    2. Destination node must exist in workflow

    Args:
        source_node: Source node ID
        destination_node: Destination node ID
        existing_nodes: Set of node IDs currently in workflow

    Returns:
        List of ConnectionValidationResult instances

    Error Codes:
        STRICT_CONN_201: Node not found in workflow
    """
    results = []

    # Check source node existence
    if source_node not in existing_nodes:
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_201",
                message=f"Source node '{source_node}' not found in workflow",
                solution={
                    "description": f"Add node '{source_node}' before creating connection",
                    "code_example": (
                        f"# Add source node first\n"
                        f'workflow.add_node("NodeType", "{source_node}", {{...}})\n'
                        f"\n"
                        f"# Then create connection\n"
                        f'workflow.add_connection("{source_node}", "output", "{destination_node}", "input")'
                    ),
                },
                context={
                    "source_node": source_node,
                    "destination_node": destination_node,
                    "existing_nodes": list(existing_nodes),
                },
            )
        )

    # Check destination node existence
    if destination_node not in existing_nodes:
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_201",
                message=f"Destination node '{destination_node}' not found in workflow",
                solution={
                    "description": f"Add node '{destination_node}' before creating connection",
                    "code_example": (
                        f"# Add destination node first\n"
                        f'workflow.add_node("NodeType", "{destination_node}", {{...}})\n'
                        f"\n"
                        f"# Then create connection\n"
                        f'workflow.add_connection("{source_node}", "output", "{destination_node}", "input")'
                    ),
                },
                context={
                    "source_node": source_node,
                    "destination_node": destination_node,
                    "existing_nodes": list(existing_nodes),
                },
            )
        )

    # If no errors, return success
    if not results:
        results.append(ConnectionValidationResult(success=True))

    return results


# ============================================================================
# Connection Parameter Validation (STRICT_CONN_202-204)
# ============================================================================


def validate_connection_parameters(
    source_output: str, destination_input: str
) -> List[ConnectionValidationResult]:
    """
    Validate connection parameter structure.

    Validation Rules:
    1. source_output must be non-empty string
    2. destination_input must be non-empty string
    3. Parameters should not contain reserved keywords

    Args:
        source_output: Source node output parameter
        destination_input: Destination node input parameter

    Returns:
        List of ConnectionValidationResult instances

    Error Codes:
        STRICT_CONN_202: Empty connection parameter
        STRICT_CONN_203: Invalid parameter name
    """
    results = []

    # Rule 1: Check source_output is non-empty
    if not source_output or not isinstance(source_output, str):
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_202",
                message="Source output parameter cannot be empty",
                solution={
                    "description": "Provide valid source output parameter",
                    "code_example": (
                        "workflow.add_connection(\n"
                        '    "source_node",\n'
                        '    "output_field",  # Valid output parameter\n'
                        '    "dest_node",\n'
                        '    "input_field"\n'
                        ")"
                    ),
                },
                context={
                    "source_output": source_output,
                    "destination_input": destination_input,
                },
            )
        )

    # Rule 2: Check destination_input is non-empty
    if not destination_input or not isinstance(destination_input, str):
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_202",
                message="Destination input parameter cannot be empty",
                solution={
                    "description": "Provide valid destination input parameter",
                    "code_example": (
                        "workflow.add_connection(\n"
                        '    "source_node",\n'
                        '    "output_field",\n'
                        '    "dest_node",\n'
                        '    "input_field"  # Valid input parameter\n'
                        ")"
                    ),
                },
                context={
                    "source_output": source_output,
                    "destination_input": destination_input,
                },
            )
        )

    # If no errors, return success
    if not results:
        results.append(ConnectionValidationResult(success=True))

    return results


# ============================================================================
# Dot Notation Validation (STRICT_CONN_204)
# ============================================================================


def validate_dot_notation(
    parameter: str, parameter_type: str  # "source_output" or "destination_input"
) -> List[ConnectionValidationResult]:
    """
    Validate dot notation for nested field access.

    Validation Rules:
    1. Dot notation should have valid structure (field.subfield)
    2. No leading/trailing dots
    3. No consecutive dots
    4. No reserved field names in dot notation

    Args:
        parameter: Parameter with potential dot notation
        parameter_type: Type of parameter ("source_output" or "destination_input")

    Returns:
        List of ConnectionValidationResult instances

    Error Codes:
        STRICT_CONN_204: Invalid dot notation structure
        STRICT_CONN_205: Reserved field in dot notation
    """
    results = []

    # Check if parameter contains dot notation
    if "." not in parameter:
        # No dot notation, no validation needed
        results.append(ConnectionValidationResult(success=True))
        return results

    # Rule 1: Check for leading/trailing dots
    if parameter.startswith(".") or parameter.endswith("."):
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_204",
                message=f"Invalid dot notation in {parameter_type}: '{parameter}' has leading/trailing dot",
                solution={
                    "description": "Remove leading/trailing dots from parameter",
                    "code_example": (
                        f"# ❌ WRONG\n"
                        f'workflow.add_connection("node1", "{parameter}", "node2", "input")\n'
                        f"\n"
                        f"# ✅ CORRECT\n"
                        f'workflow.add_connection("node1", "{parameter.strip(".")}", "node2", "input")'
                    ),
                },
                context={"parameter": parameter, "parameter_type": parameter_type},
            )
        )

    # Rule 2: Check for consecutive dots
    if ".." in parameter:
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_204",
                message=f"Invalid dot notation in {parameter_type}: '{parameter}' has consecutive dots",
                solution={
                    "description": "Remove consecutive dots from parameter",
                    "code_example": (
                        f"# ❌ WRONG\n"
                        f'workflow.add_connection("node1", "{parameter}", "node2", "input")\n'
                        f"\n"
                        f"# ✅ CORRECT\n"
                        f'workflow.add_connection("node1", "{parameter.replace("..", ".")}", "node2", "input")'
                    ),
                },
                context={"parameter": parameter, "parameter_type": parameter_type},
            )
        )

    # Rule 3: Check for reserved field names
    parts = parameter.split(".")
    for part in parts:
        if part in RESERVED_OUTPUTS:
            results.append(
                ConnectionValidationResult(
                    success=False,
                    error_code="STRICT_CONN_205",
                    message=f"Reserved field '{part}' in {parameter_type} dot notation: '{parameter}'",
                    solution={
                        "description": f"Avoid using reserved field name '{part}'",
                        "code_example": (
                            f"# ❌ WRONG - Reserved field\n"
                            f'workflow.add_connection("node1", "{parameter}", "node2", "input")\n'
                            f"\n"
                            f"# ✅ CORRECT - Use non-reserved field\n"
                            f'workflow.add_connection("node1", "data.value", "node2", "input")'
                        ),
                    },
                    context={
                        "parameter": parameter,
                        "parameter_type": parameter_type,
                        "reserved_field": part,
                        "reserved_fields": list(RESERVED_OUTPUTS),
                    },
                )
            )

    # If no errors, return success
    if not results:
        results.append(ConnectionValidationResult(success=True))

    return results


# ============================================================================
# Self-Connection Validation (STRICT_CONN_206)
# ============================================================================


def validate_no_self_connection(
    source_node: str, destination_node: str
) -> List[ConnectionValidationResult]:
    """
    Validate that a node does not connect to itself (self-connection).

    Validation Rules:
    1. Source node must be different from destination node

    Args:
        source_node: Source node ID
        destination_node: Destination node ID

    Returns:
        List of ConnectionValidationResult instances

    Error Codes:
        STRICT_CONN_206: Self-connection detected
    """
    results = []

    # Check for self-connection
    if source_node == destination_node:
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_206",
                message=f"Self-connection detected: node '{source_node}' connects to itself",
                solution={
                    "description": "Connect to a different node",
                    "code_example": (
                        f"# ❌ WRONG - Self-connection\n"
                        f'workflow.add_connection("{source_node}", "output", "{source_node}", "input")\n'
                        f"\n"
                        f"# ✅ CORRECT - Connect to different node\n"
                        f'workflow.add_connection("{source_node}", "output", "other_node", "input")'
                    ),
                },
                context={
                    "source_node": source_node,
                    "destination_node": destination_node,
                },
            )
        )
    else:
        # No self-connection, return success
        results.append(ConnectionValidationResult(success=True))

    return results


# ============================================================================
# Circular Dependency Detection (STRICT_CONN_207)
# ============================================================================


def detect_circular_dependency(
    source_node: str, destination_node: str, existing_connections: List[tuple]
) -> List[ConnectionValidationResult]:
    """
    Detect circular dependencies in workflow connections.

    Validation Rules:
    1. Adding connection should not create circular dependency

    Args:
        source_node: Source node ID
        destination_node: Destination node ID
        existing_connections: List of existing connections as (source, dest) tuples

    Returns:
        List of ConnectionValidationResult instances

    Error Codes:
        STRICT_CONN_207: Circular dependency detected
    """
    results = []

    # Build adjacency list from existing connections
    adjacency = {}
    for src, dst in existing_connections:
        if src not in adjacency:
            adjacency[src] = []
        adjacency[src].append(dst)

    # Check if adding new connection would create cycle
    # Use DFS to detect if destination_node can reach source_node
    def has_path(start: str, target: str, visited: Set[str]) -> bool:
        if start == target:
            return True
        if start in visited:
            return False

        visited.add(start)

        if start in adjacency:
            for neighbor in adjacency[start]:
                if has_path(neighbor, target, visited):
                    return True

        return False

    # Check if destination can reach source (would create cycle)
    if has_path(destination_node, source_node, set()):
        results.append(
            ConnectionValidationResult(
                success=False,
                error_code="STRICT_CONN_207",
                message=f"Circular dependency detected: adding connection from '{source_node}' to '{destination_node}' would create cycle",
                solution={
                    "description": "Remove connections that create circular dependency",
                    "code_example": (
                        f"# ❌ WRONG - Creates cycle\n"
                        f'workflow.add_connection("{destination_node}", "output", "{source_node}", "input")\n'
                        f'workflow.add_connection("{source_node}", "output", "{destination_node}", "input")  # Cycle!\n'
                        f"\n"
                        f"# ✅ CORRECT - Linear flow\n"
                        f'workflow.add_connection("node1", "output", "node2", "input")\n'
                        f'workflow.add_connection("node2", "output", "node3", "input")'
                    ),
                },
                context={
                    "source_node": source_node,
                    "destination_node": destination_node,
                    "existing_connections": existing_connections,
                },
            )
        )
    else:
        # No circular dependency, return success
        results.append(ConnectionValidationResult(success=True))

    return results


# ============================================================================
# Complete Connection Validation
# ============================================================================


def validate_connection(
    source_node: str,
    source_output: str,
    destination_node: str,
    destination_input: str,
    existing_nodes: Set[str],
    existing_connections: Optional[List[tuple]] = None,
) -> List[ConnectionValidationResult]:
    """
    Validate a complete connection with all validation rules.

    Combines all connection validation rules:
    1. Node existence validation
    2. Connection parameter validation
    3. Dot notation validation
    4. Self-connection validation
    5. Circular dependency detection (if existing_connections provided)

    Args:
        source_node: Source node ID
        source_output: Source node output parameter
        destination_node: Destination node ID
        destination_input: Destination node input parameter
        existing_nodes: Set of node IDs currently in workflow
        existing_connections: Optional list of existing connections as (source, dest) tuples

    Returns:
        List of ConnectionValidationResult instances
    """
    results = []

    # 1. Validate node existence
    node_results = validate_node_existence(
        source_node, destination_node, existing_nodes
    )
    results.extend([r for r in node_results if not r.success])

    # 2. Validate connection parameters
    param_results = validate_connection_parameters(source_output, destination_input)
    results.extend([r for r in param_results if not r.success])

    # 3. Validate dot notation in source_output
    source_dot_results = validate_dot_notation(source_output, "source_output")
    results.extend([r for r in source_dot_results if not r.success])

    # 4. Validate dot notation in destination_input
    dest_dot_results = validate_dot_notation(destination_input, "destination_input")
    results.extend([r for r in dest_dot_results if not r.success])

    # 5. Validate no self-connection
    self_conn_results = validate_no_self_connection(source_node, destination_node)
    results.extend([r for r in self_conn_results if not r.success])

    # 6. Detect circular dependencies (if existing_connections provided)
    if existing_connections is not None:
        circular_results = detect_circular_dependency(
            source_node, destination_node, existing_connections
        )
        results.extend([r for r in circular_results if not r.success])

    # If no errors, return success
    if not results:
        results.append(ConnectionValidationResult(success=True))

    return results


# ============================================================================
# Helper Functions
# ============================================================================


def get_connection_summary(results: List[ConnectionValidationResult]) -> Dict[str, Any]:
    """
    Get summary of connection validation results.

    Args:
        results: List of ConnectionValidationResult instances

    Returns:
        Dictionary with validation summary
    """
    return {
        "valid": all(r.success for r in results),
        "error_count": len([r for r in results if not r.success]),
        "errors": [
            {
                "code": r.error_code,
                "message": r.message,
                "solution": r.solution.get("description", ""),
            }
            for r in results
            if not r.success
        ],
    }
