"""
DataFlow CLI commands module.

Exports all CLI commands for validation, analysis, generation, debugging, and performance profiling.
"""

import click
from dataflow.cli.analyze import analyze
from dataflow.cli.debug import debug
from dataflow.cli.generate import generate
from dataflow.cli.main import main
from dataflow.cli.perf import perf
from dataflow.cli.validate import validate

# Register new commands with main CLI group
main.add_command(validate)
main.add_command(analyze)
main.add_command(generate)
main.add_command(debug)
main.add_command(perf)

# Export the CLI group
cli = main

__all__ = ["cli", "validate", "analyze", "generate", "debug", "perf"]
