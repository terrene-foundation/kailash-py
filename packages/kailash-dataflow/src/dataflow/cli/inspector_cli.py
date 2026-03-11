"""
Command-line interface for DataFlow Inspector.

Usage:
    python -m dataflow.cli.inspector_cli <database_url> <command> [options]

Examples:
    # Inspect a model
    python -m dataflow.cli.inspector_cli :memory: model User

    # Get DataFlow instance info
    python -m dataflow.cli.inspector_cli postgresql://localhost/db instance

    # Validate workflow connections
    python -m dataflow.cli.inspector_cli :memory: validate-connections workflow.json

    # Trace parameter source
    python -m dataflow.cli.inspector_cli :memory: trace-parameter read_user id workflow.json

    # Interactive mode
    python -m dataflow.cli.inspector_cli :memory: interactive
"""

import argparse
import json
import sys
from typing import Any, Optional

from dataflow import DataFlow
from dataflow.platform.inspector import Inspector


def load_workflow(workflow_path: str) -> Any:
    """Load workflow from JSON file."""
    try:
        with open(workflow_path, "r") as f:
            workflow_data = json.load(f)
        # TODO: Reconstruct workflow from JSON
        # For now, this is a placeholder
        return workflow_data
    except FileNotFoundError:
        print(f"Error: Workflow file '{workflow_path}' not found", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in workflow file: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_model(inspector: Inspector, args: argparse.Namespace) -> None:
    """Inspect a model."""
    try:
        model_info = inspector.model(args.model_name)
        print(model_info.show(color=args.color))
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_node(inspector: Inspector, args: argparse.Namespace) -> None:
    """Inspect a node."""
    node_info = inspector.node(args.node_id)
    print(node_info.show(color=args.color))


def cmd_instance(inspector: Inspector, args: argparse.Namespace) -> None:
    """Get DataFlow instance information."""
    instance_info = inspector.instance()
    print(instance_info.show(color=args.color))


def cmd_workflow(inspector: Inspector, args: argparse.Namespace) -> None:
    """Get workflow information."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    workflow_info = inspector.workflow(workflow)
    print(workflow_info.show(color=args.color))


def cmd_connections(inspector: Inspector, args: argparse.Namespace) -> None:
    """List workflow connections."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    connections = inspector.connections(args.node_id)
    if not connections:
        print("No connections found.")
        return

    print(f"Found {len(connections)} connection(s):")
    for conn in connections:
        status = "✓" if conn.is_valid else "✗"
        print(
            f"  {status} {conn.source_node}.{conn.source_parameter} → {conn.target_node}.{conn.target_parameter}"
        )
        if conn.validation_message:
            print(f"      Issue: {conn.validation_message}")


def cmd_connection_chain(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show connection chain between two nodes."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    chain = inspector.connection_chain(args.from_node, args.to_node)
    if not chain:
        print(f"No connection path found from '{args.from_node}' to '{args.to_node}'")
        return

    print(f"Connection chain ({len(chain)} steps):")
    for i, conn in enumerate(chain, 1):
        print(
            f"  {i}. {conn.source_node}.{conn.source_parameter} → {conn.target_node}.{conn.target_parameter}"
        )


def cmd_connection_graph(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow connection graph."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    graph = inspector.connection_graph()
    if not graph:
        print("No connections found.")
        return

    print("Connection Graph:")
    for node, targets in sorted(graph.items()):
        if targets:
            print(f"  {node} → {', '.join(targets)}")
        else:
            print(f"  {node} (no outgoing connections)")


def cmd_validate_connections(inspector: Inspector, args: argparse.Namespace) -> None:
    """Validate all workflow connections."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    is_valid, issues = inspector.validate_connections()
    if is_valid:
        print("✓ All connections are valid.")
    else:
        print(f"✗ Found {len(issues)} validation issue(s):")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)


def cmd_trace_parameter(inspector: Inspector, args: argparse.Namespace) -> None:
    """Trace parameter back to source."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    try:
        trace = inspector.trace_parameter(args.node_id, args.parameter)
        print(f"Parameter Trace for '{args.parameter}' in '{args.node_id}':")
        print(f"  Source: {trace.source_node}.{trace.source_parameter}")
        print(f"  Destination: {trace.destination_node}.{trace.destination_param}")
        if trace.transformations:
            print(f"  Transformations ({len(trace.transformations)}):")
            for i, transform in enumerate(trace.transformations, 1):
                print(
                    f"    {i}. {transform['node']}: {transform.get('transformation', 'unknown')}"
                )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


def cmd_parameter_flow(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show how parameter flows through workflow."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    flows = inspector.parameter_flow(args.node_id, args.parameter)
    if not flows:
        print(f"No flows found for parameter '{args.parameter}' from '{args.node_id}'")
        return

    print(f"Parameter Flow ({len(flows)} path(s)):")
    for i, flow in enumerate(flows, 1):
        print(
            f"  {i}. {flow.source_node}.{flow.source_parameter} → {flow.destination_node}.{flow.destination_param}"
        )


def cmd_parameter_dependencies(inspector: Inspector, args: argparse.Namespace) -> None:
    """List parameter dependencies for a node."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    deps = inspector.parameter_dependencies(args.node_id)
    if not deps:
        print(f"Node '{args.node_id}' has no parameter dependencies.")
        return

    print(f"Parameter Dependencies for '{args.node_id}':")
    for param, source in deps.items():
        print(f"  {param} ← {source}")


def cmd_node_dependencies(inspector: Inspector, args: argparse.Namespace) -> None:
    """List node dependencies (upstream)."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    deps = inspector.node_dependencies(args.node_id)
    if not deps:
        print(f"Node '{args.node_id}' has no dependencies.")
        return

    print(f"Node Dependencies (upstream) for '{args.node_id}':")
    for dep in deps:
        print(f"  ← {dep}")


def cmd_node_dependents(inspector: Inspector, args: argparse.Namespace) -> None:
    """List node dependents (downstream)."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    dependents = inspector.node_dependents(args.node_id)
    if not dependents:
        print(f"Node '{args.node_id}' has no dependents.")
        return

    print(f"Node Dependents (downstream) for '{args.node_id}':")
    for dependent in dependents:
        print(f"  → {dependent}")


def cmd_execution_order(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow execution order."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    order = inspector.execution_order()
    print(f"Execution Order ({len(order)} nodes):")
    for i, node in enumerate(order, 1):
        print(f"  {i}. {node}")


def cmd_workflow_summary(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow summary."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    summary = inspector.workflow_summary()
    print("Workflow Summary:")
    print(f"  Nodes: {summary['node_count']}")
    print(f"  Connections: {summary['connection_count']}")
    print(
        f"  Entry Points: {', '.join(summary['entry_points']) if summary['entry_points'] else 'None'}"
    )
    print(
        f"  Exit Points: {', '.join(summary['exit_points']) if summary['exit_points'] else 'None'}"
    )


def cmd_workflow_metrics(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow metrics."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    metrics = inspector.workflow_metrics()
    print("Workflow Metrics:")
    print(f"  Nodes: {metrics['node_count']}")
    print(f"  Connections: {metrics['connection_count']}")
    print(f"  Depth: {metrics['depth']}")
    print(f"  Complexity: {metrics['complexity']}")


def cmd_workflow_validation(inspector: Inspector, args: argparse.Namespace) -> None:
    """Comprehensive workflow validation."""
    if not args.workflow_file:
        print("Error: --workflow-file is required", file=sys.stderr)
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    report = inspector.workflow_validation_report()
    print("Workflow Validation Report:")
    print(f"  Valid: {'Yes' if report['is_valid'] else 'No'}")

    if report["errors"]:
        print(f"\nErrors ({len(report['errors'])}):")
        for error in report["errors"]:
            print(f"  ✗ {error}")

    if report["warnings"]:
        print(f"\nWarnings ({len(report['warnings'])}):")
        for warning in report["warnings"]:
            print(f"  ! {warning}")

    if report["suggestions"]:
        print(f"\nSuggestions ({len(report['suggestions'])}):")
        for suggestion in report["suggestions"]:
            print(f"  💡 {suggestion}")

    if not report["is_valid"]:
        sys.exit(1)


def cmd_interactive(inspector: Inspector, args: argparse.Namespace) -> None:
    """Launch interactive Inspector session."""
    inspector.interactive()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="DataFlow Inspector CLI - Inspect models, nodes, and workflows",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "database_url", help="Database URL (e.g., :memory:, postgresql://...)"
    )
    parser.add_argument(
        "--no-color",
        dest="color",
        action="store_false",
        default=True,
        help="Disable colored output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Model inspection
    model_parser = subparsers.add_parser("model", help="Inspect a model")
    model_parser.add_argument("model_name", help="Model name")

    # Node inspection
    node_parser = subparsers.add_parser("node", help="Inspect a node")
    node_parser.add_argument("node_id", help="Node ID")

    # Instance inspection
    subparsers.add_parser("instance", help="Get DataFlow instance information")

    # Workflow inspection
    workflow_parser = subparsers.add_parser("workflow", help="Get workflow information")
    workflow_parser.add_argument("workflow_file", help="Path to workflow JSON file")

    # Connection analysis
    connections_parser = subparsers.add_parser(
        "connections", help="List workflow connections"
    )
    connections_parser.add_argument("workflow_file", help="Path to workflow JSON file")
    connections_parser.add_argument("--node-id", help="Filter by node ID")

    chain_parser = subparsers.add_parser(
        "connection-chain", help="Show connection chain"
    )
    chain_parser.add_argument("workflow_file", help="Path to workflow JSON file")
    chain_parser.add_argument("from_node", help="Source node ID")
    chain_parser.add_argument("to_node", help="Target node ID")

    graph_parser = subparsers.add_parser(
        "connection-graph", help="Show connection graph"
    )
    graph_parser.add_argument("workflow_file", help="Path to workflow JSON file")

    validate_parser = subparsers.add_parser(
        "validate-connections", help="Validate connections"
    )
    validate_parser.add_argument("workflow_file", help="Path to workflow JSON file")

    # Parameter tracing
    trace_parser = subparsers.add_parser(
        "trace-parameter", help="Trace parameter to source"
    )
    trace_parser.add_argument("workflow_file", help="Path to workflow JSON file")
    trace_parser.add_argument("node_id", help="Node ID")
    trace_parser.add_argument("parameter", help="Parameter name")

    flow_parser = subparsers.add_parser("parameter-flow", help="Show parameter flow")
    flow_parser.add_argument("workflow_file", help="Path to workflow JSON file")
    flow_parser.add_argument("node_id", help="Source node ID")
    flow_parser.add_argument("parameter", help="Parameter name")

    param_deps_parser = subparsers.add_parser(
        "parameter-dependencies", help="List parameter dependencies"
    )
    param_deps_parser.add_argument("workflow_file", help="Path to workflow JSON file")
    param_deps_parser.add_argument("node_id", help="Node ID")

    # Node analysis
    node_deps_parser = subparsers.add_parser(
        "node-dependencies", help="List node dependencies"
    )
    node_deps_parser.add_argument("workflow_file", help="Path to workflow JSON file")
    node_deps_parser.add_argument("node_id", help="Node ID")

    node_dependents_parser = subparsers.add_parser(
        "node-dependents", help="List node dependents"
    )
    node_dependents_parser.add_argument(
        "workflow_file", help="Path to workflow JSON file"
    )
    node_dependents_parser.add_argument("node_id", help="Node ID")

    order_parser = subparsers.add_parser("execution-order", help="Show execution order")
    order_parser.add_argument("workflow_file", help="Path to workflow JSON file")

    # Workflow analysis
    summary_parser = subparsers.add_parser(
        "workflow-summary", help="Show workflow summary"
    )
    summary_parser.add_argument("workflow_file", help="Path to workflow JSON file")

    metrics_parser = subparsers.add_parser(
        "workflow-metrics", help="Show workflow metrics"
    )
    metrics_parser.add_argument("workflow_file", help="Path to workflow JSON file")

    validation_parser = subparsers.add_parser(
        "workflow-validation", help="Comprehensive validation"
    )
    validation_parser.add_argument("workflow_file", help="Path to workflow JSON file")

    # Interactive mode
    subparsers.add_parser("interactive", help="Launch interactive Inspector session")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Initialize DataFlow and Inspector
    try:
        db = DataFlow(args.database_url)
        inspector = Inspector(db)
    except Exception as e:
        print(f"Error: Failed to initialize DataFlow: {e}", file=sys.stderr)
        sys.exit(1)

    # Dispatch to command handler
    command_handlers = {
        "model": cmd_model,
        "node": cmd_node,
        "instance": cmd_instance,
        "workflow": cmd_workflow,
        "connections": cmd_connections,
        "connection-chain": cmd_connection_chain,
        "connection-graph": cmd_connection_graph,
        "validate-connections": cmd_validate_connections,
        "trace-parameter": cmd_trace_parameter,
        "parameter-flow": cmd_parameter_flow,
        "parameter-dependencies": cmd_parameter_dependencies,
        "node-dependencies": cmd_node_dependencies,
        "node-dependents": cmd_node_dependents,
        "execution-order": cmd_execution_order,
        "workflow-summary": cmd_workflow_summary,
        "workflow-metrics": cmd_workflow_metrics,
        "workflow-validation": cmd_workflow_validation,
        "interactive": cmd_interactive,
    }

    handler = command_handlers.get(args.command)
    if handler:
        handler(inspector, args)
    else:
        print(f"Error: Unknown command '{args.command}'", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
