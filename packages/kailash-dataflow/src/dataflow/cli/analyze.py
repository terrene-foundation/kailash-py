"""
DataFlow analyze command implementation.

Analyzes workflow metrics, complexity, and performance characteristics.
"""

import json
import sys
from typing import Any, Dict

import click
from dataflow.cli.output import get_formatter
from dataflow.cli.validate import load_workflow


@click.command()
@click.argument("workflow_path", type=click.Path())
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.option("--complexity", is_flag=True, help="Include complexity analysis")
@click.option("-q", "--quiet", is_flag=True, help="Quiet mode (minimal output)")
@click.option("-v", "--verbose", count=True, help="Verbose output (-v, -vv)")
@click.option("--color/--no-color", default=True, help="Enable/disable colored output")
def analyze(
    workflow_path: str,
    format: str,
    complexity: bool,
    quiet: bool,
    verbose: int,
    color: bool,
):
    """
    Analyze workflow metrics, complexity, and performance.

    WORKFLOW_PATH: Path to workflow Python file

    Exit codes:
      0 - Analysis completed successfully
      2 - Internal error
    """
    formatter = get_formatter(format, color)

    try:
        # Load workflow
        workflow = load_workflow(workflow_path)

        # Import Inspector from Phase 1A
        from dataflow.platform.inspector import Inspector

        # Create inspector
        inspector = Inspector(workflow)

        # Get metrics
        metrics = inspector.get_metrics()

        # Handle JSON output
        if format == "json":
            output_data = metrics.copy()

            # Add complexity analysis if requested
            if complexity:
                complexity_data = inspector.analyze_complexity()
                output_data["complexity"] = complexity_data

            click.echo(json.dumps(output_data, indent=2))
            sys.exit(0)

        # Text output based on verbosity
        if quiet:
            # Quiet mode: just key metrics
            click.echo(f"Nodes: {metrics.get('node_count', 0)}")
            click.echo(f"Connections: {metrics.get('connection_count', 0)}")
        elif verbose >= 2:
            # Very verbose: all details
            formatter._print_header(f"Workflow Analysis: {workflow.name}")

            # Basic metrics
            click.echo("\nBasic Metrics:")
            for key, value in metrics.items():
                click.echo(f"  {key}: {value}")

            # Complexity analysis if requested
            if complexity:
                complexity_data = inspector.analyze_complexity()
                click.echo("\nComplexity Analysis:")
                for key, value in complexity_data.items():
                    if isinstance(value, list):
                        click.echo(f"  {key}:")
                        for item in value:
                            if isinstance(item, dict):
                                click.echo(f"    - {item}")
                            else:
                                click.echo(f"    - {item}")
                    else:
                        click.echo(f"  {key}: {value}")
        elif verbose == 1:
            # Verbose: standard details
            formatter._print_header(f"Workflow Analysis: {workflow.name}")

            click.echo(f"\nNode count: {metrics.get('node_count', 0)}")
            click.echo(f"Connection count: {metrics.get('connection_count', 0)}")
            click.echo(f"Max depth: {metrics.get('max_depth', 0)}")
            click.echo(f"Branches: {metrics.get('branches', 0)}")
            click.echo(f"Cycles: {metrics.get('cycles', 0)}")

            if complexity:
                complexity_data = inspector.analyze_complexity()
                click.echo(
                    f"\nCyclomatic complexity: {complexity_data.get('cyclomatic_complexity', 0)}"
                )
                click.echo(
                    f"Complexity score: {complexity_data.get('complexity_score', 'unknown')}"
                )
        else:
            # Default: standard output
            formatter._print_header(f"Workflow Analysis: {workflow.name}")

            # Create metrics table
            rows = [
                ["Node count", metrics.get("node_count", 0)],
                ["Connection count", metrics.get("connection_count", 0)],
                ["Average params/node", f"{metrics.get('avg_params_per_node', 0):.1f}"],
                ["Max depth", metrics.get("max_depth", 0)],
                ["Branches", metrics.get("branches", 0)],
                ["Cycles", metrics.get("cycles", 0)],
            ]

            formatter.print_table(["Metric", "Value"], rows)

            if complexity:
                complexity_data = inspector.analyze_complexity()
                click.echo("\nComplexity:")
                click.echo(
                    f"  Cyclomatic: {complexity_data.get('cyclomatic_complexity', 0)}"
                )
                click.echo(
                    f"  Score: {complexity_data.get('complexity_score', 'unknown')}"
                )

        sys.exit(0)

    except FileNotFoundError as e:
        formatter.print_error(str(e))
        sys.exit(2)
    except Exception as e:
        formatter.print_error(f"Internal error: {str(e)}")
        sys.exit(2)
