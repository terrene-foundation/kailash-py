"""CLI commands for Kailash SDK."""

import json
import logging
import sys
from pathlib import Path
from typing import Optional

import click

from kailash.nodes import NodeRegistry
from kailash.runtime.local import LocalRuntime
from kailash.sdk_exceptions import (
    CLIException,
    ExportException,
    KailashException,
    NodeConfigurationError,
    RuntimeExecutionError,
    TaskException,
    TemplateError,
    WorkflowValidationError,
)
from kailash.tracking import TaskManager, TaskStatus
from kailash.utils.templates import TemplateManager
from kailash.workflow import Workflow

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def get_error_message(error: Exception) -> str:
    """Extract a helpful error message from an exception."""
    if isinstance(error, KailashException):
        return str(error)
    return f"{type(error).__name__}: {error}"


@click.group()
@click.version_option()
@click.option("--debug", is_flag=True, help="Enable debug mode")
def cli(debug: bool):
    """Kailash SDK - Python SDK for container-node architecture."""
    if debug:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.command()
@click.argument("name")
@click.option("--template", default="basic", help="Project template to use")
def init(name: str, template: str):
    """Initialize a new Kailash project."""
    if not name:
        click.echo("Error: Project name is required", err=True)
        sys.exit(1)

    try:
        template_manager = TemplateManager()
        template_manager.create_project(name, template)

        click.echo(f"Created new Kailash project: {name}")
        click.echo(f"To get started:\n  cd {name}\n  kailash run example_workflow.py")

    except TemplateError as e:
        click.echo(f"Template error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error creating project: {get_error_message(e)}", err=True)
        logger.error(f"Failed to create project: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument("workflow_file")
@click.option("--params", "-p", help="JSON file with parameter overrides")
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.option("--no-tracking", is_flag=True, help="Disable task tracking")
def run(workflow_file: str, params: Optional[str], debug: bool, no_tracking: bool):
    """Run a workflow locally."""
    try:
        # Validate workflow file exists
        if not Path(workflow_file).exists():
            raise CLIException(f"Workflow file not found: {workflow_file}")

        # Load workflow
        if workflow_file.endswith(".py"):
            workflow = _load_python_workflow(workflow_file)
        else:
            raise CLIException(
                "Only Python workflow files are supported. "
                "File must have .py extension"
            )

        # Load parameter overrides
        parameters = {}
        if params:
            try:
                with open(params, "r") as f:
                    parameters = json.load(f)
            except FileNotFoundError:
                raise CLIException(f"Parameters file not found: {params}")
            except json.JSONDecodeError as e:
                raise CLIException(f"Invalid JSON in parameters file: {e}")

        # Create runtime and task manager
        runtime = LocalRuntime(debug=debug)
        task_manager = None

        if not no_tracking:
            try:
                task_manager = TaskManager()
            except Exception as e:
                logger.warning(f"Failed to create task manager: {e}")
                click.echo("Warning: Task tracking disabled due to error", err=True)

        click.echo(f"Running workflow: {workflow.name}")

        # Execute workflow
        results, run_id = runtime.execute(workflow, task_manager, parameters)

        click.echo("Workflow completed successfully!")

        if run_id:
            click.echo(f"Run ID: {run_id}")
            click.echo(f"To view task details: kailash tasks show {run_id}")

        # Show summary of results
        _display_results(results)

    except RuntimeExecutionError as e:
        click.echo(f"Workflow execution failed: {e}", err=True)
        sys.exit(1)
    except CLIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Unexpected error: {get_error_message(e)}", err=True)
        logger.error(f"Failed to run workflow: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument("workflow_file")
def validate(workflow_file: str):
    """Validate a workflow definition."""
    try:
        # Validate workflow file exists
        if not Path(workflow_file).exists():
            raise CLIException(f"Workflow file not found: {workflow_file}")

        # Load workflow
        if workflow_file.endswith(".py"):
            workflow = _load_python_workflow(workflow_file)
        else:
            raise CLIException(
                "Only Python workflow files are supported. "
                "File must have .py extension"
            )

        # Validate workflow
        runtime = LocalRuntime()
        warnings = runtime.validate_workflow(workflow)

        if warnings:
            click.echo("Workflow validation warnings:")
            for warning in warnings:
                click.echo(f"  - {warning}")
            click.echo("\nWorkflow is valid with warnings")
        else:
            click.echo("Workflow is valid!")

    except WorkflowValidationError as e:
        click.echo(f"Validation failed: {e}", err=True)
        sys.exit(1)
    except CLIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Validation failed: {get_error_message(e)}", err=True)
        logger.error(f"Failed to validate workflow: {e}", exc_info=True)
        sys.exit(1)


@cli.command()
@click.argument("workflow_file")
@click.argument("output_file")
@click.option(
    "--format", default="yaml", type=click.Choice(["yaml", "json", "manifest"])
)
@click.option("--registry", help="Container registry URL")
def export(workflow_file: str, output_file: str, format: str, registry: Optional[str]):
    """Export workflow to Kailash format."""
    try:
        # Validate workflow file exists
        if not Path(workflow_file).exists():
            raise CLIException(f"Workflow file not found: {workflow_file}")

        # Load workflow
        if workflow_file.endswith(".py"):
            workflow = _load_python_workflow(workflow_file)
        else:
            raise CLIException(
                "Only Python workflow files are supported. "
                "File must have .py extension"
            )

        # Export workflow
        export_config = {}
        if registry:
            export_config["container_registry"] = registry

        workflow.export_to_kailash(
            output_path=output_file, format=format, **export_config
        )

        click.echo(f"Exported workflow to: {output_file}")

    except ExportException as e:
        click.echo(f"Export failed: {e}", err=True)
        sys.exit(1)
    except CLIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Export failed: {get_error_message(e)}", err=True)
        logger.error(f"Failed to export workflow: {e}", exc_info=True)
        sys.exit(1)


# Task management commands
@cli.group()
def tasks():
    """Task tracking commands."""
    pass


@tasks.command("list")
@click.option("--workflow", help="Filter by workflow name")
@click.option("--status", help="Filter by status")
@click.option("--limit", default=10, help="Number of runs to show")
def list_tasks(workflow: Optional[str], status: Optional[str], limit: int):
    """List workflow runs."""
    try:
        task_manager = TaskManager()
        runs = task_manager.list_runs(workflow_name=workflow, status=status)

        if not runs:
            click.echo("No runs found")
            return

        # Show recent runs
        click.echo("Recent workflow runs:")
        click.echo("-" * 60)

        for i, run in enumerate(runs[:limit]):
            status_color = {
                "running": "yellow",
                "completed": "green",
                "failed": "red",
            }.get(run.status, "white")

            click.echo(
                f"{run.run_id[:8]}  "
                f"{click.style(run.status.upper(), fg=status_color):12}  "
                f"{run.workflow_name:20}  "
                f"{run.started_at}"
            )

            if run.error:
                click.echo(f"  Error: {run.error}")

    except TaskException as e:
        click.echo(f"Task error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error listing tasks: {get_error_message(e)}", err=True)
        logger.error(f"Failed to list tasks: {e}", exc_info=True)
        sys.exit(1)


@tasks.command("show")
@click.argument("run_id")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed task information")
def show_tasks(run_id: str, verbose: bool):
    """Show details of a workflow run."""
    try:
        if not run_id:
            raise CLIException("Run ID is required")

        task_manager = TaskManager()

        # Get run details
        run = task_manager.get_run_summary(run_id)
        if not run:
            raise TaskException(
                f"Run '{run_id}' not found. "
                "Use 'kailash tasks list' to see available runs."
            )

        # Show run header
        click.echo(f"Workflow: {run.workflow_name}")
        click.echo(f"Run ID: {run.run_id}")
        click.echo(
            f"Status: {click.style(run.status.upper(), fg='green' if run.status == 'completed' else 'red')}"
        )
        click.echo(f"Started: {run.started_at}")

        if run.ended_at:
            click.echo(f"Ended: {run.ended_at}")
            click.echo(f"Duration: {run.duration:.2f}s")

        if run.error:
            click.echo(f"Error: {run.error}")

        # Show task summary
        click.echo(
            f"\nTasks: {run.task_count} total, "
            f"{run.completed_tasks} completed, "
            f"{run.failed_tasks} failed"
        )

        # Show individual tasks
        if verbose:
            tasks = task_manager.list_tasks(run_id)

            if tasks:
                click.echo("\nTask Details:")
                click.echo("-" * 60)

                for task in tasks:
                    status_color = {
                        TaskStatus.PENDING: "white",
                        TaskStatus.RUNNING: "yellow",
                        TaskStatus.COMPLETED: "green",
                        TaskStatus.FAILED: "red",
                        TaskStatus.SKIPPED: "cyan",
                    }.get(task.status, "white")

                    duration_str = f"{task.duration:.3f}s" if task.duration else "N/A"

                    click.echo(
                        f"{task.node_id:20}  "
                        f"{click.style(task.status.value.upper(), fg=status_color):12}  "
                        f"{duration_str:10}"
                    )

                    if task.error:
                        click.echo(f"  Error: {task.error}")

    except TaskException as e:
        click.echo(f"Task error: {e}", err=True)
        sys.exit(1)
    except CLIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error showing tasks: {get_error_message(e)}", err=True)
        logger.error(f"Failed to show tasks: {e}", exc_info=True)
        sys.exit(1)


@tasks.command("clear")
@click.confirmation_option(prompt="Clear all task history?")
def clear_tasks():
    """Clear all task history."""
    try:
        task_manager = TaskManager()
        task_manager.storage.clear()
        click.echo("Task history cleared")

    except Exception as e:
        click.echo(f"Error clearing tasks: {get_error_message(e)}", err=True)
        logger.error(f"Failed to clear tasks: {e}", exc_info=True)
        sys.exit(1)


# Node management commands
@cli.group()
def nodes():
    """Node management commands."""
    pass


@nodes.command("list")
def list_nodes():
    """List available nodes."""
    try:
        registry = NodeRegistry()
        nodes = registry.list_nodes()

        if not nodes:
            click.echo("No nodes registered")
            return

        click.echo("Available nodes:")
        click.echo("-" * 40)

        for name, node_class in sorted(nodes.items()):
            module_name = node_class.__module__
            click.echo(f"{name:20}  {module_name}")

    except Exception as e:
        click.echo(f"Error listing nodes: {get_error_message(e)}", err=True)
        logger.error(f"Failed to list nodes: {e}", exc_info=True)
        sys.exit(1)


@nodes.command("info")
@click.argument("node_name")
def node_info(node_name: str):
    """Show information about a node."""
    try:
        if not node_name:
            raise CLIException("Node name is required")

        registry = NodeRegistry()

        try:
            node_class = registry.get(node_name)
        except NodeConfigurationError:
            available_nodes = list(registry.list_nodes().keys())
            raise CLIException(
                f"Node '{node_name}' not found. "
                f"Available nodes: {', '.join(available_nodes)}"
            )

        # Try to create instance with empty config to get metadata
        # Some nodes require parameters, so provide empty dict
        try:
            node = node_class()
        except NodeConfigurationError:
            # If node requires config, create with minimal config
            # This is just for getting metadata
            node = None

        click.echo(f"Node: {node_name}")
        click.echo(f"Class: {node_class.__name__}")
        click.echo(f"Module: {node_class.__module__}")

        # Try to get description from docstring if node instance not available
        if node and hasattr(node, "metadata") and node.metadata.description:
            click.echo(f"Description: {node.metadata.description}")
        elif node_class.__doc__:
            # Use first line of docstring as description
            description = node_class.__doc__.strip().split("\n")[0]
            click.echo(f"Description: {description}")

        # Show parameters - get from class method if instance not available
        if node:
            params = node.get_parameters()
        else:
            # Try to get parameters from class without instance
            try:
                temp_node = object.__new__(node_class)
                params = temp_node.get_parameters()
            except Exception:
                params = {}

        if params:
            click.echo("\nParameters:")
            for name, param in params.items():
                required = "required" if param.required else "optional"
                default = (
                    f", default={param.default}" if param.default is not None else ""
                )

                click.echo(f"  {name}: {param.type.__name__} ({required}{default})")
                if param.description:
                    click.echo(f"    {param.description}")
        else:
            click.echo("\nNo parameters")

    except CLIException as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error getting node info: {get_error_message(e)}", err=True)
        logger.error(f"Failed to get node info: {e}", exc_info=True)
        sys.exit(1)


# Helper functions
def _load_python_workflow(workflow_file: str) -> Workflow:
    """Load a workflow from a Python file.

    Args:
        workflow_file: Path to Python file containing workflow

    Returns:
        Workflow instance

    Raises:
        CLIException: If workflow cannot be loaded
    """
    try:
        # Read and execute Python file
        global_scope = {}
        with open(workflow_file, "r") as f:
            code = f.read()

        exec(code, global_scope)

        # Find workflow instance
        workflow = None
        workflow_count = 0

        for name, obj in global_scope.items():
            if isinstance(obj, Workflow):
                workflow = obj
                workflow_count += 1

        if workflow_count == 0:
            raise CLIException(
                "No Workflow instance found in file. "
                "Make sure your file creates a Workflow object."
            )
        elif workflow_count > 1:
            raise CLIException(
                f"Multiple Workflow instances found ({workflow_count}). "
                "Only one Workflow per file is supported."
            )

        return workflow

    except FileNotFoundError:
        raise CLIException(f"Workflow file not found: {workflow_file}")
    except SyntaxError as e:
        raise CLIException(f"Syntax error in workflow file: {e}")
    except ImportError as e:
        raise CLIException(f"Import error in workflow file: {e}")
    except Exception as e:
        if isinstance(e, CLIException):
            raise
        raise CLIException(f"Failed to load workflow: {get_error_message(e)}")


def _display_results(results: dict):
    """Display workflow results in a readable format.

    Args:
        results: Dictionary of node results
    """
    for node_id, node_results in results.items():
        click.echo(f"\n{node_id}:")

        # Handle error results
        if isinstance(node_results, dict) and node_results.get("failed"):
            click.echo("  Status: FAILED")
            click.echo(f"  Error: {node_results.get('error', 'Unknown error')}")
            continue

        # Display normal results
        for key, value in node_results.items():
            if isinstance(value, (list, dict)) and len(str(value)) > 100:
                click.echo(f"  {key}: <{type(value).__name__} with {len(value)} items>")
            else:
                click.echo(f"  {key}: {value}")


if __name__ == "__main__":
    cli()
