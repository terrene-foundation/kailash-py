"""CLI commands for Kailash SDK."""
import os
import sys
import json
import click
import yaml
from pathlib import Path
from typing import Optional

from kailash.workflow import Workflow
from kailash.runtime.local import LocalRuntime
from kailash.tracking import TaskManager, TaskStatus
from kailash.tracking.storage.filesystem import FileSystemStorage
from kailash.nodes import NodeRegistry
from kailash.utils.templates import TemplateManager


@click.group()
@click.version_option()
def cli():
    """Kailash SDK - Python SDK for container-node architecture."""
    pass


@cli.command()
@click.argument('name')
@click.option('--template', default='basic', help='Project template to use')
def init(name: str, template: str):
    """Initialize a new Kailash project."""
    template_manager = TemplateManager()
    
    try:
        template_manager.create_project(name, template)
        click.echo(f"Created new Kailash project: {name}")
        click.echo(f"To get started:\n  cd {name}\n  kailash run example_workflow.py")
    except Exception as e:
        click.echo(f"Error creating project: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('workflow_file')
@click.option('--params', '-p', help='JSON file with parameter overrides')
@click.option('--debug', is_flag=True, help='Enable debug mode')
@click.option('--no-tracking', is_flag=True, help='Disable task tracking')
def run(workflow_file: str, params: Optional[str], debug: bool, no_tracking: bool):
    """Run a workflow locally."""
    # Load workflow
    if workflow_file.endswith('.py'):
        # Execute Python file to load workflow
        global_scope = {}
        with open(workflow_file, 'r') as f:
            exec(f.read(), global_scope)
        
        # Find workflow instance
        workflow = None
        for obj in global_scope.values():
            if isinstance(obj, Workflow):
                workflow = obj
                break
        
        if not workflow:
            click.echo("No Workflow instance found in file", err=True)
            sys.exit(1)
    else:
        click.echo("Only Python workflow files are supported", err=True)
        sys.exit(1)
    
    # Load parameter overrides
    parameters = {}
    if params:
        with open(params, 'r') as f:
            parameters = json.load(f)
    
    # Create runtime and task manager
    runtime = LocalRuntime(debug=debug)
    task_manager = None if no_tracking else TaskManager()
    
    try:
        click.echo(f"Running workflow: {workflow.metadata.name}")
        results, run_id = runtime.execute(workflow, task_manager, parameters)
        
        click.echo("Workflow completed successfully!")
        
        if run_id:
            click.echo(f"Run ID: {run_id}")
            click.echo(f"To view task details: kailash tasks show {run_id}")
        
        # Show summary of results
        for node_id, node_results in results.items():
            click.echo(f"\n{node_id}:")
            for key, value in node_results.items():
                if isinstance(value, (list, dict)) and len(str(value)) > 100:
                    click.echo(f"  {key}: <{type(value).__name__} with {len(value)} items>")
                else:
                    click.echo(f"  {key}: {value}")
    
    except Exception as e:
        click.echo(f"Workflow failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('workflow_file')
def validate(workflow_file: str):
    """Validate a workflow definition."""
    # Load workflow
    try:
        if workflow_file.endswith('.py'):
            global_scope = {}
            with open(workflow_file, 'r') as f:
                exec(f.read(), global_scope)
            
            workflow = None
            for obj in global_scope.values():
                if isinstance(obj, Workflow):
                    workflow = obj
                    break
            
            if not workflow:
                click.echo("No Workflow instance found in file", err=True)
                sys.exit(1)
        else:
            click.echo("Only Python workflow files are supported", err=True)
            sys.exit(1)
        
        # Validate workflow
        runtime = LocalRuntime()
        warnings = runtime.validate_workflow(workflow)
        
        if warnings:
            click.echo("Workflow validation warnings:")
            for warning in warnings:
                click.echo(f"  - {warning}")
        else:
            click.echo("Workflow is valid!")
    
    except Exception as e:
        click.echo(f"Validation failed: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('workflow_file')
@click.argument('output_file')
@click.option('--format', default='yaml', type=click.Choice(['yaml', 'json']))
def export(workflow_file: str, output_file: str, format: str):
    """Export workflow to Kailash format."""
    # Load workflow
    try:
        if workflow_file.endswith('.py'):
            global_scope = {}
            with open(workflow_file, 'r') as f:
                exec(f.read(), global_scope)
            
            workflow = None
            for obj in global_scope.values():
                if isinstance(obj, Workflow):
                    workflow = obj
                    break
            
            if not workflow:
                click.echo("No Workflow instance found in file", err=True)
                sys.exit(1)
        else:
            click.echo("Only Python workflow files are supported", err=True)
            sys.exit(1)
        
        # Export workflow
        if format == 'yaml':
            workflow.export_to_kailash(output_file)
        else:
            # Export to JSON
            data = workflow.to_dict()
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=2)
        
        click.echo(f"Exported workflow to: {output_file}")
    
    except Exception as e:
        click.echo(f"Export failed: {e}", err=True)
        sys.exit(1)


# Task management commands
@cli.group()
def tasks():
    """Task tracking commands."""
    pass


@tasks.command('list')
@click.option('--workflow', help='Filter by workflow name')
@click.option('--status', help='Filter by status')
@click.option('--limit', default=10, help='Number of runs to show')
def list_tasks(workflow: Optional[str], status: Optional[str], limit: int):
    """List workflow runs."""
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
            "failed": "red"
        }.get(run.status, "white")
        
        click.echo(
            f"{run.run_id[:8]}  "
            f"{click.style(run.status.upper(), fg=status_color):12}  "
            f"{run.workflow_name:20}  "
            f"{run.started_at}"
        )
        
        if run.error:
            click.echo(f"  Error: {run.error}")


@tasks.command('show')
@click.argument('run_id')
@click.option('--verbose', '-v', is_flag=True, help='Show detailed task information')
def show_tasks(run_id: str, verbose: bool):
    """Show details of a workflow run."""
    task_manager = TaskManager()
    
    # Get run details
    run = task_manager.get_run_summary(run_id)
    if not run:
        click.echo(f"Run {run_id} not found", err=True)
        sys.exit(1)
    
    # Show run header
    click.echo(f"Workflow: {run.workflow_name}")
    click.echo(f"Run ID: {run.run_id}")
    click.echo(f"Status: {click.style(run.status.upper(), fg='green' if run.status == 'completed' else 'red')}")
    click.echo(f"Started: {run.started_at}")
    
    if run.ended_at:
        click.echo(f"Ended: {run.ended_at}")
        click.echo(f"Duration: {run.duration:.2f}s")
    
    if run.error:
        click.echo(f"Error: {run.error}")
    
    # Show task summary
    click.echo(f"\nTasks: {run.task_count} total, "
               f"{run.completed_tasks} completed, "
               f"{run.failed_tasks} failed")
    
    # Show individual tasks
    tasks = task_manager.list_tasks(run_id)
    
    if verbose and tasks:
        click.echo("\nTask Details:")
        click.echo("-" * 60)
        
        for task in tasks:
            status_color = {
                TaskStatus.PENDING: "white",
                TaskStatus.RUNNING: "yellow",
                TaskStatus.COMPLETED: "green",
                TaskStatus.FAILED: "red",
                TaskStatus.SKIPPED: "cyan"
            }.get(task.status, "white")
            
            click.echo(
                f"{task.node_id:20}  "
                f"{click.style(task.status.upper(), fg=status_color):12}  "
                f"{task.duration:.3f}s" if task.duration else "N/A"
            )
            
            if task.error:
                click.echo(f"  Error: {task.error}")


@tasks.command('clear')
@click.confirmation_option(prompt='Clear all task history?')
def clear_tasks():
    """Clear all task history."""
    task_manager = TaskManager()
    task_manager.storage.clear()
    click.echo("Task history cleared")


# Node management commands
@cli.group()
def nodes():
    """Node management commands."""
    pass


@nodes.command('list')
def list_nodes():
    """List available nodes."""
    registry = NodeRegistry()
    nodes = registry.list_nodes()
    
    if not nodes:
        click.echo("No nodes registered")
        return
    
    click.echo("Available nodes:")
    click.echo("-" * 40)
    
    for name, node_class in sorted(nodes.items()):
        click.echo(f"{name:20}  {node_class.__module__}")


@nodes.command('info')
@click.argument('node_name')
def node_info(node_name: str):
    """Show information about a node."""
    registry = NodeRegistry()
    
    try:
        node_class = registry.get(node_name)
        
        # Create instance to get metadata
        node = node_class()
        
        click.echo(f"Node: {node_name}")
        click.echo(f"Class: {node_class.__name__}")
        click.echo(f"Module: {node_class.__module__}")
        
        if node.metadata.description:
            click.echo(f"Description: {node.metadata.description}")
        
        # Show parameters
        params = node.get_parameters()
        if params:
            click.echo("\nParameters:")
            for name, param in params.items():
                required = "required" if param.required else "optional"
                click.echo(f"  {name}: {param.type.__name__} ({required})")
                if param.description:
                    click.echo(f"    {param.description}")
    
    except KeyError:
        click.echo(f"Node '{node_name}' not found", err=True)
        sys.exit(1)


if __name__ == '__main__':
    cli()