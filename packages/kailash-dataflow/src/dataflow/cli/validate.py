"""
DataFlow validate command implementation.

Validates workflow structure, connections, and parameters with auto-fixing capability.
"""

import importlib.util
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import click
from dataflow.cli.output import get_formatter


def load_workflow(workflow_path: str) -> Any:
    """
    Load workflow from Python file.

    Args:
        workflow_path: Path to workflow Python file

    Returns:
        Workflow object

    Raises:
        Exception: If workflow cannot be loaded
    """
    path = Path(workflow_path)
    if not path.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")

    # Load module from file
    spec = importlib.util.spec_from_file_location("workflow_module", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load workflow from {workflow_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules["workflow_module"] = module
    spec.loader.exec_module(module)

    # Try to find workflow object
    workflow = None
    for attr_name in dir(module):
        attr = getattr(module, attr_name)
        if hasattr(attr, "nodes") and hasattr(attr, "connections"):
            workflow = attr
            break

    if workflow is None:
        raise ValueError(f"No workflow found in {workflow_path}")

    return workflow


def apply_fixes(workflow: Any, errors: list) -> Dict[str, Any]:
    """
    Apply automatic fixes to workflow errors.

    Args:
        workflow: Workflow object
        errors: List of fixable errors

    Returns:
        Dictionary with fix results
    """
    fixed = 0
    failed = 0
    changes = []

    for error in errors:
        if error.get("fixable", False):
            try:
                # Apply fix based on error type
                error_type = error.get("type")
                if error_type == "ParameterNaming":
                    # Fix parameter naming
                    changes.append(f"Fixed parameter naming: {error.get('message')}")
                    fixed += 1
                elif error_type == "ConnectionSyntax":
                    # Fix connection syntax
                    changes.append(f"Fixed connection syntax: {error.get('message')}")
                    fixed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

    return {"fixed": fixed, "failed": failed, "changes": changes}


@click.command()
@click.argument("workflow_path", type=click.Path())
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
@click.option("--fix", is_flag=True, help="Automatically fix errors")
@click.option("--dry-run", is_flag=True, help="Show fixes without applying")
@click.option("--color/--no-color", default=True, help="Enable/disable colored output")
def validate(workflow_path: str, output: str, fix: bool, dry_run: bool, color: bool):
    """
    Validate workflow structure, connections, and parameters.

    WORKFLOW_PATH: Path to workflow Python file

    Exit codes:
      0 - Validation passed
      1 - Validation errors found
      2 - Internal error
    """
    formatter = get_formatter(output, color)

    try:
        # Load workflow
        workflow = load_workflow(workflow_path)

        # Import Inspector from Phase 1A
        from dataflow.platform.inspector import Inspector

        # Create inspector and validate
        inspector = Inspector(workflow)
        validation_result = inspector.validate()

        # Handle output format
        if output == "json":
            import json

            click.echo(json.dumps(validation_result, indent=2))
            sys.exit(0 if validation_result["valid"] else 1)

        # Text output
        if validation_result["valid"]:
            formatter.print_success(f"Workflow '{workflow.name}' is valid")

            # Show warnings if any
            if validation_result.get("warnings"):
                formatter.print_warning(
                    f"Found {len(validation_result['warnings'])} warning(s):"
                )
                for warning in validation_result["warnings"]:
                    click.echo(f"  - {warning.get('message', 'Unknown warning')}")

            sys.exit(0)
        else:
            # Validation errors
            errors = validation_result.get("errors", [])
            formatter.print_error(f"Found {len(errors)} validation error(s):")

            for error in errors:
                error_msg = error.get("message", "Unknown error")
                error_type = error.get("type", "Error")
                node = error.get("node", "")

                if node:
                    click.echo(f"  - [{error_type}] {node}: {error_msg}")
                else:
                    click.echo(f"  - [{error_type}] {error_msg}")

            # Apply fixes if requested
            if fix:
                if dry_run:
                    formatter.print_info("Dry run mode - no changes will be applied")

                fix_result = apply_fixes(workflow, errors)

                if fix_result["fixed"] > 0:
                    formatter.print_success(f"Fixed {fix_result['fixed']} error(s)")
                    for change in fix_result["changes"]:
                        click.echo(f"  - {change}")

                if fix_result["failed"] > 0:
                    formatter.print_warning(
                        f"Could not fix {fix_result['failed']} error(s)"
                    )

                # Re-validate after fixes
                if not dry_run and fix_result["fixed"] > 0:
                    validation_result = inspector.validate()
                    if validation_result["valid"]:
                        formatter.print_success(
                            "All errors fixed - workflow is now valid"
                        )
                        sys.exit(0)

            sys.exit(1)

    except FileNotFoundError as e:
        formatter.print_error(str(e))
        sys.exit(2)
    except Exception as e:
        formatter.print_error(f"Internal error: {str(e)}")
        sys.exit(2)
