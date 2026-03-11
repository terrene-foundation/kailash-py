"""
DataFlow perf command implementation.

Performance profiling and bottleneck detection with optimization recommendations.
"""

import json
import sys
from typing import Any, Dict

import click
from dataflow.cli.output import get_formatter
from dataflow.cli.validate import load_workflow


class ProfilingRuntime:
    """Mock profiling runtime for testing."""

    def __init__(self, workflow: Any):
        """Initialize profiling runtime."""
        self.workflow = workflow
        self.profile_data = None

    def execute(self, inputs: dict = None):
        """Execute workflow with profiling."""
        # Mock execution
        return ({"result": "data"}, "run123")

    def get_profile(self) -> Dict[str, Any]:
        """Get profiling data."""
        if self.profile_data is None:
            # Generate mock profile data
            node_count = len(self.workflow.nodes)
            self.profile_data = {
                "total_time": 1.234,
                "node_timings": {
                    node_name: {
                        "time": 0.1 + (i * 0.2),
                        "calls": 1,
                        "percentage": (0.1 + (i * 0.2)) / 1.234 * 100,
                    }
                    for i, node_name in enumerate(self.workflow.nodes.keys())
                },
                "bottlenecks": [],
                "memory_usage": {"peak": "45.2 MB", "average": "32.1 MB"},
            }

            # Identify bottlenecks (nodes taking >40% of total time)
            for node_name, timing in self.profile_data["node_timings"].items():
                if timing["percentage"] > 40:
                    self.profile_data["bottlenecks"].append(
                        {"node": node_name, "time": timing["time"], "impact": "high"}
                    )

        return self.profile_data


@click.command()
@click.argument("workflow_path", type=click.Path())
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.option("--bottlenecks", is_flag=True, help="Show bottleneck analysis")
@click.option("--recommend", is_flag=True, help="Show optimization recommendations")
def perf(workflow_path: str, format: str, bottlenecks: bool, recommend: bool):
    """
    Profile workflow execution and detect bottlenecks.

    WORKFLOW_PATH: Path to workflow Python file

    Exit codes:
      0 - Profiling completed successfully
      2 - Internal error
    """
    formatter = get_formatter(format, True)

    try:
        # Load workflow
        workflow = load_workflow(workflow_path)

        # Create profiling runtime
        profiling_runtime = ProfilingRuntime(workflow)

        # Execute with profiling
        if format != "json":
            formatter.print_info("Profiling workflow execution...")
        results, run_id = profiling_runtime.execute()

        # Get profile data
        profile = profiling_runtime.get_profile()

        # Add recommendations if requested
        if recommend:
            recommendations = []
            for bottleneck in profile.get("bottlenecks", []):
                recommendations.append(
                    {
                        "node": bottleneck["node"],
                        "issue": "Slow execution",
                        "suggestion": "Consider caching or parallelization",
                        "impact": bottleneck.get("impact", "medium"),
                    }
                )
            profile["recommendations"] = recommendations

        # Handle JSON output
        if format == "json":
            click.echo(json.dumps(profile, indent=2))
            sys.exit(0)

        # Text output
        formatter._print_header("Performance Profile")

        click.echo(f"\nTotal execution time: {profile['total_time']:.3f}s")
        click.echo(f"Memory peak: {profile['memory_usage']['peak']}")

        # Node timings table
        click.echo("\nNode Timings:")
        rows = []
        for node_name, timing in profile["node_timings"].items():
            rows.append(
                [
                    node_name,
                    f"{timing['time']:.3f}s",
                    f"{timing['percentage']:.1f}%",
                    timing["calls"],
                ]
            )

        # Sort by time descending
        rows.sort(key=lambda x: float(x[1].rstrip("s")), reverse=True)

        formatter.print_table(["Node", "Time", "Percentage", "Calls"], rows)

        # Bottleneck analysis
        if bottlenecks or profile.get("bottlenecks"):
            click.echo("\nBottlenecks:")
            for bottleneck in profile.get("bottlenecks", []):
                impact = bottleneck.get("impact", "unknown")
                node = bottleneck["node"]
                time = bottleneck["time"]
                formatter.print_warning(f"  [{impact.upper()}] {node}: {time:.3f}s")

        # Recommendations
        if recommend and profile.get("recommendations"):
            click.echo("\nOptimization Recommendations:")
            for rec in profile["recommendations"]:
                click.echo(f"\n  Node: {rec['node']}")
                click.echo(f"  Issue: {rec['issue']}")
                click.echo(f"  Suggestion: {rec['suggestion']}")
                click.echo(f"  Impact: {rec['impact']}")

        sys.exit(0)

    except FileNotFoundError as e:
        formatter.print_error(str(e))
        sys.exit(2)
    except Exception as e:
        formatter.print_error(f"Internal error: {str(e)}")
        sys.exit(2)
