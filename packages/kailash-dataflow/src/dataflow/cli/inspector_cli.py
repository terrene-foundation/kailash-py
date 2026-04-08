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
import logging
import sys
from typing import Any, Optional

from dataflow import DataFlow
from dataflow.platform.inspector import Inspector

logger = logging.getLogger(__name__)


def _cli_output(message: str, file=None) -> None:
    """Write CLI output to stdout or specified file handle."""
    target = file or sys.stdout
    target.write(message + "\n")


def load_workflow(workflow_path: str) -> Any:
    """Load workflow from JSON file."""
    try:
        with open(workflow_path, "r") as f:
            workflow_data = json.load(f)
        # TODO: Reconstruct workflow from JSON
        # For now, this is a placeholder
        return workflow_data
    except FileNotFoundError:
        logger.error("inspector.workflow_file_not_found", extra={"path": workflow_path})
        sys.exit(1)
    except json.JSONDecodeError as e:
        logger.error(
            "inspector.invalid_json", extra={"path": workflow_path, "error": str(e)}
        )
        sys.exit(1)


def cmd_model(inspector: Inspector, args: argparse.Namespace) -> None:
    """Inspect a model."""
    try:
        model_info = inspector.model(args.model_name)
        _cli_output(model_info.show(color=args.color))
    except ValueError as e:
        logger.error("inspector.model_error", extra={"error": str(e)})
        sys.exit(1)


def cmd_node(inspector: Inspector, args: argparse.Namespace) -> None:
    """Inspect a node."""
    node_info = inspector.node(args.node_id)
    _cli_output(node_info.show(color=args.color))


def cmd_instance(inspector: Inspector, args: argparse.Namespace) -> None:
    """Get DataFlow instance information."""
    instance_info = inspector.instance()
    _cli_output(instance_info.show(color=args.color))


def cmd_workflow(inspector: Inspector, args: argparse.Namespace) -> None:
    """Get workflow information."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    workflow_info = inspector.workflow(workflow)
    _cli_output(workflow_info.show(color=args.color))


def cmd_connections(inspector: Inspector, args: argparse.Namespace) -> None:
    """List workflow connections."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    connections = inspector.connections(args.node_id)
    if not connections:
        _cli_output("No connections found.")
        return

    _cli_output("Found %d connection(s):" % len(connections))
    for conn in connections:
        status = "+" if conn.is_valid else "x"
        _cli_output(
            "  %s %s.%s -> %s.%s"
            % (
                status,
                conn.source_node,
                conn.source_parameter,
                conn.target_node,
                conn.target_parameter,
            )
        )
        if conn.validation_message:
            _cli_output("      Issue: %s" % conn.validation_message)


def cmd_connection_chain(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show connection chain between two nodes."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    chain = inspector.connection_chain(args.from_node, args.to_node)
    if not chain:
        _cli_output(
            "No connection path found from '%s' to '%s'"
            % (args.from_node, args.to_node)
        )
        return

    _cli_output("Connection chain (%d steps):" % len(chain))
    for i, conn in enumerate(chain, 1):
        _cli_output(
            "  %d. %s.%s -> %s.%s"
            % (
                i,
                conn.source_node,
                conn.source_parameter,
                conn.target_node,
                conn.target_parameter,
            )
        )


def cmd_connection_graph(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow connection graph."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    graph = inspector.connection_graph()
    if not graph:
        _cli_output("No connections found.")
        return

    _cli_output("Connection Graph:")
    for node, targets in sorted(graph.items()):
        if targets:
            _cli_output("  %s -> %s" % (node, ", ".join(targets)))
        else:
            _cli_output("  %s (no outgoing connections)" % node)


def cmd_validate_connections(inspector: Inspector, args: argparse.Namespace) -> None:
    """Validate all workflow connections."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    is_valid, issues = inspector.validate_connections()
    if is_valid:
        _cli_output("All connections are valid.")
    else:
        _cli_output("Found %d validation issue(s):" % len(issues))
        for issue in issues:
            _cli_output("  - %s" % issue)
        sys.exit(1)


def cmd_trace_parameter(inspector: Inspector, args: argparse.Namespace) -> None:
    """Trace parameter back to source."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    try:
        trace = inspector.trace_parameter(args.node_id, args.parameter)
        _cli_output(
            "Parameter Trace for '%s' in '%s':" % (args.parameter, args.node_id)
        )
        _cli_output("  Source: %s.%s" % (trace.source_node, trace.source_parameter))
        _cli_output(
            "  Destination: %s.%s" % (trace.destination_node, trace.destination_param)
        )
        if trace.transformations:
            _cli_output("  Transformations (%d):" % len(trace.transformations))
            for i, transform in enumerate(trace.transformations, 1):
                _cli_output(
                    "    %d. %s: %s"
                    % (i, transform["node"], transform.get("transformation", "unknown"))
                )
    except ValueError as e:
        logger.error("inspector.trace_parameter_error", extra={"error": str(e)})
        sys.exit(1)


def cmd_parameter_flow(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show how parameter flows through workflow."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    flows = inspector.parameter_flow(args.node_id, args.parameter)
    if not flows:
        _cli_output(
            "No flows found for parameter '%s' from '%s'"
            % (args.parameter, args.node_id)
        )
        return

    _cli_output("Parameter Flow (%d path(s)):" % len(flows))
    for i, flow in enumerate(flows, 1):
        _cli_output(
            "  %d. %s.%s -> %s.%s"
            % (
                i,
                flow.source_node,
                flow.source_parameter,
                flow.destination_node,
                flow.destination_param,
            )
        )


def cmd_parameter_dependencies(inspector: Inspector, args: argparse.Namespace) -> None:
    """List parameter dependencies for a node."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    deps = inspector.parameter_dependencies(args.node_id)
    if not deps:
        _cli_output("Node '%s' has no parameter dependencies." % args.node_id)
        return

    _cli_output("Parameter Dependencies for '%s':" % args.node_id)
    for param, source in deps.items():
        _cli_output("  %s <- %s" % (param, source))


def cmd_node_dependencies(inspector: Inspector, args: argparse.Namespace) -> None:
    """List node dependencies (upstream)."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    deps = inspector.node_dependencies(args.node_id)
    if not deps:
        _cli_output("Node '%s' has no dependencies." % args.node_id)
        return

    _cli_output("Node Dependencies (upstream) for '%s':" % args.node_id)
    for dep in deps:
        _cli_output("  <- %s" % dep)


def cmd_node_dependents(inspector: Inspector, args: argparse.Namespace) -> None:
    """List node dependents (downstream)."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    dependents = inspector.node_dependents(args.node_id)
    if not dependents:
        _cli_output("Node '%s' has no dependents." % args.node_id)
        return

    _cli_output("Node Dependents (downstream) for '%s':" % args.node_id)
    for dependent in dependents:
        _cli_output("  -> %s" % dependent)


def cmd_execution_order(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow execution order."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    order = inspector.execution_order()
    _cli_output("Execution Order (%d nodes):" % len(order))
    for i, node in enumerate(order, 1):
        _cli_output("  %d. %s" % (i, node))


def cmd_workflow_summary(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow summary."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    summary = inspector.workflow_summary()
    _cli_output("Workflow Summary:")
    _cli_output("  Nodes: %s" % summary["node_count"])
    _cli_output("  Connections: %s" % summary["connection_count"])
    _cli_output(
        "  Entry Points: %s"
        % (", ".join(summary["entry_points"]) if summary["entry_points"] else "None")
    )
    _cli_output(
        "  Exit Points: %s"
        % (", ".join(summary["exit_points"]) if summary["exit_points"] else "None")
    )


def cmd_workflow_metrics(inspector: Inspector, args: argparse.Namespace) -> None:
    """Show workflow metrics."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    metrics = inspector.workflow_metrics()
    _cli_output("Workflow Metrics:")
    _cli_output("  Nodes: %s" % metrics["node_count"])
    _cli_output("  Connections: %s" % metrics["connection_count"])
    _cli_output("  Depth: %s" % metrics["depth"])
    _cli_output("  Complexity: %s" % metrics["complexity"])


def cmd_workflow_validation(inspector: Inspector, args: argparse.Namespace) -> None:
    """Comprehensive workflow validation."""
    if not args.workflow_file:
        logger.error("inspector.workflow_file_required")
        sys.exit(1)

    workflow = load_workflow(args.workflow_file)
    inspector.workflow_obj = workflow

    report = inspector.workflow_validation_report()
    _cli_output("Workflow Validation Report:")
    _cli_output("  Valid: %s" % ("Yes" if report["is_valid"] else "No"))

    if report["errors"]:
        _cli_output("\nErrors (%d):" % len(report["errors"]))
        for error in report["errors"]:
            _cli_output("  x %s" % error)

    if report["warnings"]:
        _cli_output("\nWarnings (%d):" % len(report["warnings"]))
        for warning in report["warnings"]:
            _cli_output("  ! %s" % warning)

    if report["suggestions"]:
        _cli_output("\nSuggestions (%d):" % len(report["suggestions"]))
        for suggestion in report["suggestions"]:
            _cli_output("  * %s" % suggestion)

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
        logger.error("inspector.init_failed", extra={"error": str(e)})
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
        logger.error("inspector.unknown_command", extra={"command": args.command})
        sys.exit(1)


if __name__ == "__main__":
    main()
