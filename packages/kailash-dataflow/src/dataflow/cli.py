"""
DataFlow CLI Interface

Command-line interface for DataFlow operations including schema management,
migrations, and database operations.
"""

import os
import sys
from typing import Optional

import click

# Add the parent directory to the path so we can import dataflow
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dataflow import DataFlow


@click.group()
@click.version_option(version="0.1.0")
def main():
    """DataFlow - Workflow-native database framework for Kailash SDK"""
    pass


@main.command()
@click.option("--database-url", help="Database connection URL")
@click.option("--model", help="Model name to generate schema for")
def schema(database_url: Optional[str], model: Optional[str]):
    """Generate and display database schema"""
    try:
        db = DataFlow(database_url=database_url)
        click.echo("DataFlow schema generation")
        click.echo(f"Database URL: {database_url or 'Using default/environment'}")
        if model:
            click.echo(f"Model: {model}")
        else:
            click.echo("All models")

        # TODO: Implement actual schema generation display
        click.echo("Schema generation functionality coming soon...")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
@click.option("--database-url", help="Database connection URL")
def init(database_url: Optional[str]):
    """Initialize DataFlow database"""
    try:
        db = DataFlow(database_url=database_url)
        click.echo("Initializing DataFlow database...")
        click.echo(f"Database URL: {database_url or 'Using default/environment'}")

        # TODO: Implement actual database initialization
        click.echo("Database initialization functionality coming soon...")

    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


@main.command()
def version():
    """Show DataFlow version"""
    click.echo("DataFlow version 0.1.0")


if __name__ == "__main__":
    main()
