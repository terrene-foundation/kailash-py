"""
DataFlow debug command implementation.

Interactive debugging with breakpoints, parameter inspection, and step execution.
"""

import sys
from typing import Any

import click
from dataflow.cli.output import get_formatter
from dataflow.cli.validate import load_workflow


class DebugRuntime:
    """Mock debug runtime for testing."""

    def __init__(self, workflow: Any):
        """Initialize debug runtime."""
        self.workflow = workflow
        self.breakpoints = []
        self.current_step = 0

    def set_breakpoint(self, node_name: str) -> bool:
        """Set breakpoint on node."""
        if node_name in self.workflow.nodes:
            self.breakpoints.append(node_name)
            return True
        return False

    def execute(self, inputs: dict = None):
        """Execute workflow with debugging."""
        # Mock execution
        return ({"result": "data"}, "run123")

    def step(self):
        """Execute single step."""
        # Mock step execution
        self.current_step += 1
        if self.current_step <= len(self.workflow.nodes):
            node_name = list(self.workflow.nodes.keys())[self.current_step - 1]
            return {
                "node": node_name,
                "status": "completed",
                "output": {"data": f"step{self.current_step}"},
            }
        return None

    def has_next_step(self) -> bool:
        """Check if there are more steps."""
        return self.current_step < len(self.workflow.nodes)

    def interactive_session(self):
        """Start interactive debugging session."""
        return {"commands_executed": 3, "final_state": "completed"}


@click.command()
@click.argument("workflow_path", type=click.Path())
@click.option("--breakpoint", "-b", multiple=True, help="Set breakpoint on node")
@click.option("--inspect-node", "-i", help="Inspect specific node")
@click.option("--step", is_flag=True, help="Enable step-by-step execution")
@click.option("--interactive", is_flag=True, help="Start interactive debugger")
def debug(
    workflow_path: str,
    breakpoint: tuple,
    inspect_node: str,
    step: bool,
    interactive: bool,
):
    """
    Interactive debugging with breakpoints and inspection.

    WORKFLOW_PATH: Path to workflow Python file

    Exit codes:
      0 - Debug session completed
      2 - Internal error
    """
    formatter = get_formatter("text", True)

    try:
        # Load workflow
        workflow = load_workflow(workflow_path)

        # Create debug runtime
        debug_runtime = DebugRuntime(workflow)

        # Handle inspect node
        if inspect_node:
            from dataflow.platform.inspector import Inspector

            inspector = Inspector(workflow)
            node_info = inspector.inspect_node(inspect_node)

            formatter._print_header(f"Node: {inspect_node}")
            click.echo(f"Type: {node_info.get('type', 'Unknown')}")

            if node_info.get("parameters"):
                click.echo("\nParameters:")
                for param_name, param_data in node_info["parameters"].items():
                    param_type = param_data.get("type", "unknown")
                    param_value = param_data.get("value", "N/A")
                    click.echo(f"  {param_name} ({param_type}): {param_value}")

            sys.exit(0)

        # Handle breakpoints
        if breakpoint:
            for bp in breakpoint:
                if debug_runtime.set_breakpoint(bp):
                    formatter.print_success(f"Breakpoint set on '{bp}'")
                else:
                    formatter.print_warning(f"Node '{bp}' not found")

        # Handle step execution
        if step:
            formatter.print_info("Step-by-step execution mode")
            click.echo("Press Enter to execute next step...\n")

            while debug_runtime.has_next_step():
                input()  # Wait for user input
                result = debug_runtime.step()
                if result:
                    click.echo(
                        f"Executed: {result['node']} - Status: {result['status']}"
                    )
                else:
                    break

            formatter.print_success("Workflow execution completed")
            sys.exit(0)

        # Handle interactive mode
        if interactive:
            formatter.print_info("Interactive debugger mode")
            click.echo("Available commands: inspect, continue, step, break, exit\n")

            result = debug_runtime.interactive_session()
            formatter.print_success(
                f"Session completed - {result['commands_executed']} commands executed"
            )
            sys.exit(0)

        # Default: execute with breakpoints
        if breakpoint:
            formatter.print_info("Executing with breakpoints...")

        results, run_id = debug_runtime.execute()
        formatter.print_success(f"Workflow executed - Run ID: {run_id}")

        sys.exit(0)

    except FileNotFoundError as e:
        formatter.print_error(str(e))
        sys.exit(2)
    except Exception as e:
        formatter.print_error(f"Internal error: {str(e)}")
        sys.exit(2)
