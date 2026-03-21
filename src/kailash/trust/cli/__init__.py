# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
EATP CLI -- trust management commands.

Provides the ``eatp`` command-line interface for managing trust chains,
authorities, agents, delegations, and verification.

Entry point: ``main()`` which is registered as ``eatp`` in pyproject.toml.
"""

import logging
import os

import click

from kailash.trust.cli.commands import (
    audit_cmd,
    delegate_cmd,
    establish_cmd,
    export_cmd,
    init_cmd,
    revoke_cmd,
    scan_cmd,
    status_cmd,
    verify_chain_cmd,
    verify_cmd,
    version_cmd,
)


@click.group()
@click.option(
    "--store-dir",
    default=None,
    envvar="EATP_STORE_DIR",
    help="EATP data directory (default: ~/.eatp/).",
)
@click.option(
    "--verbose",
    is_flag=True,
    help="Enable debug logging.",
)
@click.pass_context
def main(ctx: click.Context, store_dir: str | None, verbose: bool) -> None:
    """EATP -- Enterprise Agent Trust Protocol CLI.

    Manage trust chains, authorities, agents, delegations, and verification
    from the command line.
    """
    ctx.ensure_object(dict)

    if store_dir is None:
        store_dir = os.path.join(os.path.expanduser("~"), ".eatp")
    ctx.obj["store_dir"] = store_dir

    if verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(name)s %(levelname)s: %(message)s")


# Register commands
main.add_command(init_cmd)
main.add_command(establish_cmd)
main.add_command(delegate_cmd)
main.add_command(verify_cmd)
main.add_command(revoke_cmd)
main.add_command(status_cmd)
main.add_command(version_cmd)
main.add_command(audit_cmd)
main.add_command(export_cmd)
main.add_command(scan_cmd)
main.add_command(verify_chain_cmd)
