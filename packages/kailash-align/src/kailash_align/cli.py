# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""kailash-align-prepare CLI: model download, list, verify for air-gapped deployments."""
from __future__ import annotations

import sys

__all__ = ["main"]


def main() -> None:
    """CLI entry point for kailash-align-prepare.

    Commands:
        download MODEL_ID [--revision REV] -- Download model to local cache
        list                               -- List cached models
        verify MODEL_ID                    -- Verify cached model is loadable
    """
    try:
        import click
    except ImportError:
        print(
            "kailash-align-prepare requires click. " "Install with: pip install click",
            file=sys.stderr,
        )
        raise SystemExit(1)

    from kailash_align.onprem import OnPremModelCache

    @click.group()
    @click.option(
        "--cache-dir",
        default="~/.cache/kailash-align/models",
        help="Model cache directory",
    )
    @click.pass_context
    def cli(ctx: click.Context, cache_dir: str) -> None:
        """kailash-align model preparation CLI for air-gapped deployments."""
        ctx.ensure_object(dict)
        ctx.obj["cache"] = OnPremModelCache(cache_dir=cache_dir)

    @cli.command()
    @click.argument("model_id")
    @click.option("--revision", default=None, help="Model revision/branch")
    @click.pass_context
    def download(ctx: click.Context, model_id: str, revision: str | None) -> None:
        """Download a model from HuggingFace Hub to local cache."""
        cache: OnPremModelCache = ctx.obj["cache"]
        path = cache.download(model_id, revision=revision)
        click.echo(f"Downloaded: {model_id} -> {path}")

    @cli.command("list")
    @click.pass_context
    def list_models(ctx: click.Context) -> None:
        """List all cached models."""
        cache: OnPremModelCache = ctx.obj["cache"]
        models = cache.list()
        if not models:
            click.echo("No cached models found.")
            return
        for m in models:
            size_mb = m.size_bytes / (1024 * 1024)
            status = "complete" if m.is_complete else "INCOMPLETE"
            click.echo(f"  {m.model_id} ({size_mb:.0f} MB) [{status}] {m.cache_path}")

    @cli.command()
    @click.argument("model_id")
    @click.pass_context
    def verify(ctx: click.Context, model_id: str) -> None:
        """Verify a cached model is complete and loadable."""
        cache: OnPremModelCache = ctx.obj["cache"]
        if cache.verify(model_id):
            click.echo(f"PASS: {model_id} is verified and ready for offline use.")
        else:
            click.echo(f"FAIL: {model_id} is incomplete or corrupt.", err=True)
            raise SystemExit(1)

    cli()
