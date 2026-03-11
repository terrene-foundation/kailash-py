"""
DataFlow Debug Agent CLI - Interactive error diagnosis and solution ranking.

Provides command-line interface for AI-powered error diagnosis using DebugAgent.

Commands:
- dataflow diagnose --error-input "error message"  # Diagnose error from input
- dataflow diagnose --workflow workflow.py         # Diagnose workflow file
- dataflow diagnose --format json                  # JSON output format
- dataflow diagnose --verbose                      # Detailed diagnosis
- dataflow diagnose --top-n 5                      # Show top 5 solutions

Architecture:
- Uses DebugAgent for AI-powered diagnosis
- Leverages ErrorEnhancer for 60+ error types
- Outputs formatted diagnosis with ranked solutions
- Supports plain text and JSON formats
"""

import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from dataflow.cli.output import get_formatter
from dataflow.core.error_enhancer import ErrorEnhancer
from dataflow.debug.agent import DebugAgent
from dataflow.debug.data_structures import Diagnosis, KnowledgeBase, RankedSolution
from dataflow.exceptions import EnhancedDataFlowError


def load_workflow(workflow_path: str):
    """
    Load workflow from Python file.

    Args:
        workflow_path: Path to workflow file

    Returns:
        Workflow instance

    Raises:
        FileNotFoundError: If workflow file doesn't exist
        ImportError: If workflow cannot be imported
    """
    workflow_file = Path(workflow_path)

    if not workflow_file.exists():
        raise FileNotFoundError(f"Workflow file not found: {workflow_path}")

    # Import workflow from file
    import importlib.util

    spec = importlib.util.spec_from_file_location("workflow_module", workflow_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load workflow from {workflow_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # Look for workflow variable
    if not hasattr(module, "workflow"):
        raise ValueError(
            f"No 'workflow' variable found in {workflow_path}. "
            "Expected: workflow = WorkflowBuilder() ..."
        )

    return module.workflow


def ranked_solution_to_dict(ranked_solution: RankedSolution) -> Dict[str, Any]:
    """
    Convert RankedSolution to dictionary.

    Args:
        ranked_solution: RankedSolution instance

    Returns:
        Dictionary representation
    """
    return {
        "description": ranked_solution.solution.description,
        "code_template": ranked_solution.solution.code_template,
        "auto_fixable": ranked_solution.solution.auto_fixable,
        "priority": ranked_solution.solution.priority,
        "relevance_score": ranked_solution.relevance_score,
        "reasoning": ranked_solution.reasoning,
        "confidence": ranked_solution.confidence,
        "effectiveness_score": ranked_solution.effectiveness_score,
        "combined_score": ranked_solution.combined_score,
    }


def diagnosis_to_dict(diagnosis: Diagnosis) -> Dict[str, Any]:
    """
    Convert Diagnosis to dictionary.

    Args:
        diagnosis: Diagnosis instance

    Returns:
        Dictionary representation
    """
    return {
        "diagnosis": diagnosis.diagnosis,
        "ranked_solutions": [
            ranked_solution_to_dict(sol) for sol in diagnosis.ranked_solutions
        ],
        "confidence": diagnosis.confidence,
        "next_steps": diagnosis.next_steps,
        "inspector_hints": diagnosis.inspector_hints,
    }


def format_diagnosis(
    diagnosis: Diagnosis,
    format: str = "text",
    verbose: bool = False,
    top_n: int = 3,
) -> str:
    """
    Format diagnosis for output.

    Args:
        diagnosis: Diagnosis instance
        format: Output format ("text" or "json")
        verbose: Include detailed information
        top_n: Number of top solutions to show

    Returns:
        Formatted diagnosis string
    """
    if format == "json":
        # JSON format
        data = diagnosis_to_dict(diagnosis)
        # Limit to top-n solutions
        data["ranked_solutions"] = data["ranked_solutions"][:top_n]
        return json.dumps(data, indent=2)

    # Plain text format
    lines = []

    # Header
    lines.append("\n" + "=" * 80)
    lines.append("DataFlow AI Debug Agent - Diagnosis")
    lines.append("=" * 80)
    lines.append("")

    # Diagnosis
    lines.append(diagnosis.diagnosis)
    lines.append("")

    # Confidence
    lines.append(f"Overall Confidence: {diagnosis.confidence:.2f}")
    lines.append("")

    # Solutions
    ranked_solutions = diagnosis.ranked_solutions[:top_n]

    if ranked_solutions:
        lines.append("-" * 80)
        lines.append(f"Top {len(ranked_solutions)} Solutions (Ranked by Relevance)")
        lines.append("-" * 80)
        lines.append("")

        for i, ranked_solution in enumerate(ranked_solutions, 1):
            lines.append(f"{i}. {ranked_solution.solution.description}")
            lines.append(f"   Relevance: {ranked_solution.relevance_score:.2f}")

            if verbose:
                lines.append(f"   Reasoning: {ranked_solution.reasoning}")
                lines.append(f"   Confidence: {ranked_solution.confidence:.2f}")
                lines.append(
                    f"   Effectiveness: {ranked_solution.effectiveness_score:.2f}"
                )
                lines.append(f"   Combined Score: {ranked_solution.combined_score:.2f}")

            lines.append("")

            # Code template
            if ranked_solution.solution.code_template:
                lines.append("   Code:")
                code_lines = ranked_solution.solution.code_template.strip().split("\n")

                if verbose:
                    # Show full code in verbose mode
                    for code_line in code_lines:
                        lines.append(f"   {code_line}")
                else:
                    # Show first 5 lines in normal mode
                    for code_line in code_lines[:5]:
                        lines.append(f"   {code_line}")
                    if len(code_lines) > 5:
                        lines.append("   ...")

                lines.append("")
    else:
        lines.append("No solutions available for this error.")
        lines.append("")

    # Next steps
    if diagnosis.next_steps:
        lines.append("-" * 80)
        lines.append("Next Steps")
        lines.append("-" * 80)
        lines.append("")
        for step in diagnosis.next_steps:
            lines.append(step)
        lines.append("")

    # Inspector hints (if available)
    if verbose and diagnosis.inspector_hints:
        lines.append("-" * 80)
        lines.append("Inspector Hints")
        lines.append("-" * 80)
        lines.append("")
        for hint in diagnosis.inspector_hints:
            lines.append(f"  - {hint}")
        lines.append("")

    lines.append("=" * 80)

    return "\n".join(lines)


@click.command()
@click.option(
    "--error-input",
    "-e",
    help="Error message or exception text to diagnose",
    default=None,
)
@click.option(
    "--workflow",
    "-w",
    type=click.Path(exists=True),
    help="Path to workflow file for inspection",
    default=None,
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"], case_sensitive=False),
    default="text",
    help="Output format (text or json)",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed diagnosis with all information",
)
@click.option(
    "--top-n",
    "-n",
    type=int,
    default=3,
    help="Number of top solutions to display (default: 3)",
)
def diagnose(
    error_input: Optional[str],
    workflow: Optional[str],
    format: str,
    verbose: bool,
    top_n: int,
):
    """
    Diagnose DataFlow errors with AI-powered analysis.

    Provides intelligent error diagnosis with ranked solutions using the DebugAgent.

    Examples:

        # Diagnose error from input
        $ dataflow diagnose --error-input "Field 'id' is required"

        # Diagnose workflow file
        $ dataflow diagnose --workflow workflow.py

        # JSON output
        $ dataflow diagnose --error-input "error" --format json

        # Verbose mode with top 5 solutions
        $ dataflow diagnose --error-input "error" --verbose --top-n 5

    Exit codes:
      0 - Diagnosis completed successfully
      1 - Invalid input or arguments
      2 - Internal error
    """
    formatter = get_formatter("text", color=True)

    try:
        # Validation: require either error_input or workflow
        if not error_input and not workflow:
            formatter.print_error(
                "Either --error-input or --workflow is required for diagnosis."
            )
            click.echo("\nUsage examples:")
            click.echo("  dataflow diagnose --error-input 'Field id is required'")
            click.echo("  dataflow diagnose --workflow workflow.py")
            sys.exit(1)

        # Validation: top-n must be positive
        if top_n < 1:
            formatter.print_error("--top-n must be a positive integer (>= 1)")
            sys.exit(1)

        # Initialize ErrorEnhancer and DebugAgent
        error_enhancer = ErrorEnhancer()
        knowledge_base = KnowledgeBase(storage_type="memory")
        debug_agent = DebugAgent(
            error_enhancer=error_enhancer,
            knowledge_base=knowledge_base,
            model="gpt-4o-mini",
        )

        # Workflow-based diagnosis
        if workflow:
            try:
                workflow_instance = load_workflow(workflow)

                # For workflow files, we need an actual error to diagnose
                # This is a simplified version - in practice, you'd need to
                # execute the workflow or provide an error
                formatter.print_info(
                    f"Loaded workflow from: {workflow}\n"
                    f"Note: Workflow inspection without errors is limited.\n"
                    f"Please provide --error-input for full diagnosis."
                )

                # If no error provided with workflow, show usage
                if not error_input:
                    formatter.print_warning(
                        "No error input provided. "
                        "Use --error-input with --workflow for full diagnosis."
                    )
                    sys.exit(0)

            except (FileNotFoundError, ImportError, ValueError) as e:
                formatter.print_error(f"Failed to load workflow: {e}")
                sys.exit(1)

        # Create enhanced error from error_input
        if error_input:
            # Try to parse as existing EnhancedDataFlowError or create new one
            try:
                # Attempt to create a generic error
                original_error = ValueError(error_input)

                # Enhance the error using generic error enhancement
                enhanced_error = error_enhancer.enhance_generic_error(
                    exception=original_error, source="cli_input"
                )

            except Exception as e:
                formatter.print_error(f"Failed to parse error input: {e}")
                sys.exit(1)

            # Diagnose the error
            try:
                # Create a mock workflow if not provided
                if not workflow:
                    from kailash.workflow.builder import WorkflowBuilder

                    workflow_instance = WorkflowBuilder()

                diagnosis = debug_agent.diagnose_error(
                    enhanced_error, workflow_instance
                )

                # Format and display diagnosis
                output = format_diagnosis(
                    diagnosis, format=format, verbose=verbose, top_n=top_n
                )

                # Print output
                if format == "json":
                    click.echo(output)
                else:
                    click.echo(output)

                sys.exit(0)

            except Exception as e:
                formatter.print_error(f"Diagnosis failed: {e}")
                if verbose:
                    click.echo("\nFull traceback:")
                    traceback.print_exc()
                sys.exit(2)

    except Exception as e:
        formatter.print_error(f"Internal error: {e}")
        if verbose:
            click.echo("\nFull traceback:")
            traceback.print_exc()
        sys.exit(2)


if __name__ == "__main__":
    diagnose()
