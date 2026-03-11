"""
DataFlow generate command implementation.

Generates workflow reports, diagrams, and documentation.
"""

import json
import sys
from pathlib import Path
from typing import Any

import click
from dataflow.cli.output import get_formatter
from dataflow.cli.validate import load_workflow


@click.group()
def generate():
    """Generate workflow reports, diagrams, and documentation."""
    pass


@generate.command()
@click.argument("workflow_path", type=click.Path())
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option(
    "--format",
    "-f",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format",
)
def report(workflow_path: str, output: str, format: str):
    """
    Generate comprehensive workflow report.

    WORKFLOW_PATH: Path to workflow Python file
    """
    formatter = get_formatter(format, True)

    try:
        # Load workflow
        workflow = load_workflow(workflow_path)

        # Import Inspector from Phase 1A
        from dataflow.platform.inspector import Inspector

        # Create inspector
        inspector = Inspector(workflow)

        # Generate report
        report_data = inspector.generate_report()

        # Handle output
        if format == "json":
            report_json = json.dumps(report_data, indent=2)
            if output:
                Path(output).write_text(report_json)
                formatter.print_success(f"Report saved to {output}")
            else:
                click.echo(report_json)
        else:
            # Text report
            report_text = f"""
{report_data.get('title', 'Workflow Report')}
{'=' * 60}

{report_data.get('summary', 'No summary available')}

"""
            for section in report_data.get("sections", []):
                report_text += f"\n{section['title']}\n{'-' * 40}\n"
                report_text += f"{section['content']}\n"

            if output:
                Path(output).write_text(report_text)
                formatter.print_success(f"Report saved to {output}")
            else:
                click.echo(report_text)

        sys.exit(0)

    except Exception as e:
        formatter.print_error(f"Error generating report: {str(e)}")
        sys.exit(2)


@generate.command()
@click.argument("workflow_path", type=click.Path())
@click.option("--output", "-o", type=click.Path(), help="Output file path")
def diagram(workflow_path: str, output: str):
    """
    Generate text-based workflow diagram.

    WORKFLOW_PATH: Path to workflow Python file
    """
    formatter = get_formatter("text", True)

    try:
        # Load workflow
        workflow = load_workflow(workflow_path)

        # Import Inspector from Phase 1A
        from dataflow.platform.inspector import Inspector

        # Create inspector
        inspector = Inspector(workflow)

        # Generate diagram
        diagram_text = inspector.generate_diagram()

        if output:
            Path(output).write_text(diagram_text)
            formatter.print_success(f"Diagram saved to {output}")
        else:
            click.echo(diagram_text)

        sys.exit(0)

    except Exception as e:
        formatter.print_error(f"Error generating diagram: {str(e)}")
        sys.exit(2)


@generate.command()
@click.argument("workflow_path", type=click.Path())
@click.option(
    "--output-dir", "-d", type=click.Path(), default="./docs", help="Output directory"
)
def docs(workflow_path: str, output_dir: str):
    """
    Generate workflow documentation.

    WORKFLOW_PATH: Path to workflow Python file
    """
    formatter = get_formatter("text", True)

    try:
        # Load workflow
        workflow = load_workflow(workflow_path)

        # Import Inspector from Phase 1A
        from dataflow.platform.inspector import Inspector

        # Create inspector
        inspector = Inspector(workflow)

        # Generate documentation
        docs_content = inspector.generate_documentation()

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Write documentation
        doc_file = output_path / f"{workflow.name}.md"
        doc_file.write_text(docs_content)

        formatter.print_success(f"Documentation generated in {output_dir}/")
        click.echo(f"  - {doc_file.name}")

        sys.exit(0)

    except Exception as e:
        formatter.print_error(f"Error generating documentation: {str(e)}")
        sys.exit(2)
