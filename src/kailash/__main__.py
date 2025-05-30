"""
Kailash SDK CLI entry point.

This module enables running the Kailash SDK as a module with:
    python -m kailash
"""

from kailash.cli.commands import cli

if __name__ == "__main__":
    cli()
