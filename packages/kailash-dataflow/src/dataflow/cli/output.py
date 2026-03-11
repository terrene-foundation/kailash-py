"""
Output formatting utilities for DataFlow CLI.

Provides Rich-based formatting for tables, trees, and JSON output.
"""

import json
import sys
from typing import Any, Dict, List, Optional

import click


class OutputFormatter:
    """Handles formatted output for CLI commands."""

    def __init__(self, format: str = "text", color: bool = True):
        """
        Initialize output formatter.

        Args:
            format: Output format (text, json, yaml)
            color: Enable colored output
        """
        self.format = format
        self.color = color and sys.stdout.isatty()

    def print_dict(self, data: Dict[str, Any], title: Optional[str] = None):
        """Print dictionary data in specified format."""
        if self.format == "json":
            click.echo(json.dumps(data, indent=2))
        else:
            if title:
                self._print_header(title)
            for key, value in data.items():
                click.echo(f"{key}: {value}")

    def print_list(self, items: List[Any], title: Optional[str] = None):
        """Print list items in specified format."""
        if self.format == "json":
            click.echo(json.dumps(items, indent=2))
        else:
            if title:
                self._print_header(title)
            for item in items:
                if isinstance(item, dict):
                    self.print_dict(item)
                else:
                    click.echo(f"  - {item}")

    def print_table(self, headers: List[str], rows: List[List[Any]]):
        """Print tabular data."""
        if self.format == "json":
            table_data = [dict(zip(headers, row)) for row in rows]
            click.echo(json.dumps(table_data, indent=2))
        else:
            # Simple text table
            col_widths = [
                max(len(str(h)), max(len(str(row[i])) for row in rows))
                for i, h in enumerate(headers)
            ]

            # Header
            header_row = " | ".join(
                str(h).ljust(w) for h, w in zip(headers, col_widths)
            )
            click.echo(header_row)
            click.echo("-" * len(header_row))

            # Rows
            for row in rows:
                row_str = " | ".join(
                    str(cell).ljust(w) for cell, w in zip(row, col_widths)
                )
                click.echo(row_str)

    def print_success(self, message: str):
        """Print success message."""
        if self.color:
            click.secho(f"✓ {message}", fg="green")
        else:
            click.echo(f"[SUCCESS] {message}")

    def print_error(self, message: str):
        """Print error message."""
        if self.color:
            click.secho(f"✗ {message}", fg="red", err=True)
        else:
            click.echo(f"[ERROR] {message}", err=True)

    def print_warning(self, message: str):
        """Print warning message."""
        if self.color:
            click.secho(f"⚠ {message}", fg="yellow")
        else:
            click.echo(f"[WARNING] {message}")

    def print_info(self, message: str):
        """Print info message."""
        if self.color:
            click.secho(message, fg="blue")
        else:
            click.echo(f"[INFO] {message}")

    def _print_header(self, title: str):
        """Print section header."""
        if self.color:
            click.secho(f"\n{title}", fg="cyan", bold=True)
            click.secho("-" * len(title), fg="cyan")
        else:
            click.echo(f"\n{title}")
            click.echo("-" * len(title))


def get_formatter(output: str = "text", color: bool = True) -> OutputFormatter:
    """Get output formatter instance."""
    return OutputFormatter(format=output, color=color)
