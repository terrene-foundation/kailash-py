# Copyright 2026 Terrene Foundation
# Licensed under the Apache License, Version 2.0
"""PACT governance CLI -- validate YAML org definitions.

Usage:
    python -m pact.governance.cli validate org.yaml
    python -m pact.governance.cli validate --verbose org.yaml

The validate command loads a YAML org definition, compiles it, and
reports any structural issues. It does NOT start a server.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

logger = logging.getLogger(__name__)

__all__ = ["cli", "main"]


def _green(text: str) -> str:
    """Return text wrapped in ANSI green."""
    return f"\033[32m{text}\033[0m"


def _red(text: str) -> str:
    """Return text wrapped in ANSI red."""
    return f"\033[31m{text}\033[0m"


def _yellow(text: str) -> str:
    """Return text wrapped in ANSI yellow."""
    return f"\033[33m{text}\033[0m"


def _bold(text: str) -> str:
    """Return text wrapped in ANSI bold."""
    return f"\033[1m{text}\033[0m"


@click.group()
def cli() -> None:
    """PACT governance CLI."""
    pass


@cli.command()
@click.argument("yaml_path", type=click.Path(exists=True))
@click.option("--verbose", "-v", is_flag=True, help="Show compiled address tree")
def validate(yaml_path: str, verbose: bool) -> None:
    """Validate a YAML organization definition.

    Loads the YAML, validates all references, compiles the org structure,
    and reports any issues.
    """
    path = Path(yaml_path)
    click.echo(f"\nValidating {_bold(str(path))}...\n")

    # --- Load YAML ---
    try:
        from pact.governance.yaml_loader import ConfigurationError, load_org_yaml

        loaded = load_org_yaml(path)
    except ConfigurationError as e:
        click.echo(f"{_red('ERROR')}: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"{_red('ERROR')}: Failed to load YAML: {e}")
        sys.exit(1)

    org_def = loaded.org_definition
    click.echo(f"  Organization: {_bold(org_def.name)} ({org_def.org_id})")

    # --- Compile ---
    try:
        from pact.governance.compilation import CompilationError, compile_org

        compiled = compile_org(org_def)
    except CompilationError as e:
        click.echo(f"\n{_red('COMPILATION ERROR')}: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n{_red('ERROR')}: Compilation failed: {e}")
        sys.exit(1)

    # --- Count node types ---
    dept_count = 0
    team_count = 0
    role_count = 0
    for node in compiled.nodes.values():
        if node.node_type.value == "D":
            dept_count += 1
        elif node.node_type.value == "T":
            team_count += 1
        elif node.node_type.value == "R":
            role_count += 1

    click.echo(
        f"  Departments: {_bold(str(dept_count))}, "
        f"Teams: {_bold(str(team_count))}, "
        f"Roles: {_bold(str(role_count))}"
    )
    click.echo(
        f"  Clearances: {_bold(str(len(loaded.clearances)))}, "
        f"Envelopes: {_bold(str(len(loaded.envelopes)))}, "
        f"Bridges: {_bold(str(len(loaded.bridges)))}, "
        f"KSPs: {_bold(str(len(loaded.ksps)))}"
    )

    # --- Validate clearance references ---
    issues: list[str] = []
    role_ids = {r.role_id for r in org_def.roles}

    for spec in loaded.clearances:
        node = compiled.get_node_by_role_id(spec.role_id)
        if node is None:
            issues.append(
                f"Clearance for role '{spec.role_id}' could not be resolved to a compiled address"
            )

    for spec in loaded.envelopes:
        target_node = compiled.get_node_by_role_id(spec.target)
        definer_node = compiled.get_node_by_role_id(spec.defined_by)
        if target_node is None:
            issues.append(
                f"Envelope target '{spec.target}' could not be resolved to a compiled address"
            )
        if definer_node is None:
            issues.append(
                f"Envelope defined_by '{spec.defined_by}' could not be resolved to a compiled address"
            )

    for spec in loaded.bridges:
        a_node = compiled.get_node_by_role_id(spec.role_a)
        b_node = compiled.get_node_by_role_id(spec.role_b)
        if a_node is None:
            issues.append(f"Bridge '{spec.id}' role_a '{spec.role_a}' could not be resolved")
        if b_node is None:
            issues.append(f"Bridge '{spec.id}' role_b '{spec.role_b}' could not be resolved")

    # --- Show address tree if verbose ---
    if verbose:
        click.echo(f"\n  {_bold('Compiled Address Tree')}:")
        for addr in sorted(compiled.nodes.keys()):
            node = compiled.nodes[addr]
            depth = addr.count("-")
            indent = "    " + "  " * depth
            type_str = node.node_type.value
            click.echo(f"{indent}{type_str} {addr}: {node.name}")

    # --- Report results ---
    if issues:
        click.echo(f"\n{_yellow('WARNINGS')} ({len(issues)}):")
        for issue in issues:
            click.echo(f"  - {issue}")
        click.echo()

    if not issues:
        click.echo(f"\n{_green('All references valid.')} Organization is well-formed.\n")
    else:
        click.echo(
            f"\n{_yellow('Validation completed with warnings.')} "
            f"The organization compiled successfully but some governance "
            f"specs reference roles that could not be resolved.\n"
        )


def main() -> None:
    """Entry point for the ``kailash-pact`` console script."""
    logging.basicConfig(level=logging.WARNING)
    cli()


if __name__ == "__main__":
    main()
