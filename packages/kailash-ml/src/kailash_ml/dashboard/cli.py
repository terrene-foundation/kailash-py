# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``kailash-ml-dashboard`` command-line entry point (argparse-based).

Per ``specs/ml-dashboard.md`` §8: the CLI is the blocking / foreground
launch path for operators and CI deployments. The sibling
``kailash_ml.dashboard.launcher.launch`` (a.k.a. ``km.dashboard``) is the
non-blocking / notebook path. Both construct the same ``MLDashboard``
class with the same default store path (``~/.kailash_ml/ml.db``).

Exit codes (spec §8.4):
  0  Clean shutdown (SIGTERM / SIGINT).
  1  Unexpected runtime error.
  2  Invalid CLI arguments (incompatible flags, missing required value).
  3  Tracker store unreachable at startup.
  4  Port already in use.

Security defaults (spec §8.3 + rules/security.md):
  --host 0.0.0.0 MUST be paired with --auth. Launching without auth and
  with a non-loopback bind exits 2 with a clear refusal message.
"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger(__name__)

__all__ = ["main", "build_parser", "run"]


# ---------------------------------------------------------------------------
# Exit codes (spec §8.4)
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_RUNTIME_ERROR = 1
EXIT_INVALID_ARGS = 2
EXIT_STORE_UNREACHABLE = 3
EXIT_PORT_IN_USE = 4


# ---------------------------------------------------------------------------
# Store URL resolution (spec §3.2)
# ---------------------------------------------------------------------------


_LEGACY_ENV_VAR = "KAILASH_ML_TRACKER_DB"
_CURRENT_ENV_VAR = "KAILASH_ML_STORE_URL"
_LEGACY_ENV_WARNED = False  # process-lifetime sentinel per spec §3.2.1


def resolve_store_url(explicit: str | None = None) -> str:
    """Resolve tracker store URL per spec §3.2 authority chain.

    Priority: explicit kwarg -> ``$KAILASH_ML_STORE_URL`` ->
    ``$KAILASH_ML_TRACKER_DB`` (legacy, 1.x only) -> ``~/.kailash_ml/ml.db``.
    """
    global _LEGACY_ENV_WARNED

    if explicit:
        return explicit

    current = os.environ.get(_CURRENT_ENV_VAR)
    legacy = os.environ.get(_LEGACY_ENV_VAR)

    if current and legacy:
        if not _LEGACY_ENV_WARNED:
            logger.warning(
                "kml.env.legacy_precedence_ignored",
                extra={
                    "current_var": _CURRENT_ENV_VAR,
                    "legacy_var": _LEGACY_ENV_VAR,
                    "note": "both env vars set; KAILASH_ML_STORE_URL wins",
                },
            )
            _LEGACY_ENV_WARNED = True
        return current

    if current:
        return current

    if legacy:
        if not _LEGACY_ENV_WARNED:
            logger.debug(
                "kailash_ml.dashboard.legacy_env_resolved",
                extra={
                    "legacy_var": _LEGACY_ENV_VAR,
                    "rename_to": _CURRENT_ENV_VAR,
                    "removal_at": "kailash-ml 2.0",
                },
            )
            _LEGACY_ENV_WARNED = True
        return legacy

    # Canonical default: ~/.kailash_ml/ml.db per spec §3.2 + ml-tracking.md §2.2
    default_path = Path.home() / ".kailash_ml" / "ml.db"
    return f"sqlite:///{default_path}"


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser per spec §8.2 / §8.5."""
    # Resolve the default store URL at parser-build time so --help text
    # includes the canonical default path visibly per spec §8.5.
    default_store_url = resolve_store_url(None)

    parser = argparse.ArgumentParser(
        prog="kailash-ml-dashboard",
        description=(
            "Launch the kailash-ml experiment dashboard — Terrene Foundation's "
            "canonical tracker-store web UI. Default store path: "
            f"{default_store_url}."
        ),
        epilog=(
            "Examples:\n"
            "  kailash-ml-dashboard --db sqlite:///~/.kailash_ml/ml.db --port 5000\n"
            "  kailash-ml-dashboard --tenant-id acme --db postgresql://...\n"
            "  # Nexus automatically mounts; do not launch standalone.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--db",
        default=None,
        help=(
            f"Tracker store URL. Defaults to ${_CURRENT_ENV_VAR} or "
            f"~/.kailash_ml/ml.db."
        ),
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Bind host. 0.0.0.0 requires --auth. Default: 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Bind port. Default: 5000.",
    )
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Scope every view to this tenant_id.",
    )
    parser.add_argument(
        "--title",
        default="Kailash ML",
        help="Dashboard page title.",
    )
    parser.add_argument(
        "--artifact-root",
        default="./mlartifacts",
        help="Root directory for artifact storage. Default: ./mlartifacts.",
    )
    parser.add_argument(
        "--enable-control",
        action="store_true",
        help="Mount the WebSocket control routes (write operations).",
    )
    parser.add_argument(
        "--auth",
        default=None,
        help="Auth policy URL (e.g. nexus://URL). Required for non-loopback bind.",
    )
    parser.add_argument(
        "--cors-origins",
        default="",
        help="Comma-separated list of permitted CORS origins.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Logging level: DEBUG, INFO, WARNING, ERROR. Default: INFO.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )
    return parser


# ---------------------------------------------------------------------------
# Runtime entry
# ---------------------------------------------------------------------------


def _configure_logging(level_name: str) -> None:
    level = getattr(logging, level_name.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _validate_bind(host: str, auth: str | None) -> tuple[bool, str]:
    """Validate host/auth pairing per spec §8.3.

    Returns ``(ok, error_message)``. When ``ok=False``, the caller exits
    ``EXIT_INVALID_ARGS``.
    """
    loopback_hosts = {"127.0.0.1", "localhost", "::1"}
    if host in loopback_hosts:
        return True, ""
    if auth is None:
        return False, (
            f"refused: --host {host} requires --auth; "
            "use --host 127.0.0.1 for local-only."
        )
    return True, ""


def run(argv: Sequence[str] | None = None) -> int:
    """CLI entry implementation (separated from ``main`` for testability).

    Returns the exit code. Callers in ``main()`` pass the return value to
    ``sys.exit()``.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        # Late import keeps --version fast (no dashboard stack init)
        from kailash_ml._version import __version__

        print(f"kailash-ml-dashboard {__version__}")
        return EXIT_OK

    _configure_logging(args.log_level)

    # §8.3 security defaults
    ok, err = _validate_bind(args.host, args.auth)
    if not ok:
        print(err, file=sys.stderr)
        return EXIT_INVALID_ARGS

    if (
        args.enable_control
        and args.auth is None
        and args.host
        in {
            "127.0.0.1",
            "localhost",
            "::1",
        }
    ):
        logger.warning(
            "mldashboard.control.unauthed",
            extra={
                "note": "--enable-control without --auth; writes permitted on loopback only",
            },
        )

    # Resolve store url (may emit legacy-env DEBUG log per spec §3.2.1)
    db_url = resolve_store_url(args.db)

    cors_origins: tuple[str, ...] = tuple(
        origin.strip() for origin in args.cors_origins.split(",") if origin.strip()
    )

    logger.info(
        "mldashboard.cli.start",
        extra={
            "bind": args.host,
            "port": args.port,
            "tenant_id": args.tenant_id,
            "enable_control": args.enable_control,
            "auth_configured": args.auth is not None,
            "db_url": _mask_db_url(db_url),
        },
    )

    # Late import — keep --help / --version fast and independent of the
    # [dashboard] extra (the starlette import is behind __init__'s import
    # and raises a descriptive ImportError naming [dashboard] if missing).
    try:
        from kailash_ml.dashboard import MLDashboard
    except ImportError as exc:
        print(
            "kailash-ml-dashboard requires the [dashboard] extra: "
            "pip install 'kailash-ml[dashboard]'",
            file=sys.stderr,
        )
        logger.error("mldashboard.cli.extra_missing", extra={"error": str(exc)})
        return EXIT_RUNTIME_ERROR

    dashboard = MLDashboard(
        db_url=db_url,
        artifact_root=args.artifact_root,
        host=args.host,
        port=args.port,
        tenant_id=args.tenant_id,
        title=args.title,
        enable_control=args.enable_control,
        auth=args.auth,
        cors_origins=cors_origins,
    )

    # Graceful shutdown on SIGTERM/SIGINT (CLI runs in foreground)
    def _sigterm(signum: int, _frame: Any) -> None:
        logger.info("mldashboard.cli.signal_received", extra={"signum": signum})
        # uvicorn.run installs its own signal handlers; we just log and let
        # uvicorn complete its shutdown sequence cleanly.

    try:
        signal.signal(signal.SIGTERM, _sigterm)
        signal.signal(signal.SIGINT, _sigterm)
    except (ValueError, AttributeError):
        # signal.signal raises ValueError off main thread — CLI always runs
        # on main thread, but guard anyway for test-harness invocations.
        pass

    try:
        dashboard.serve()
    except OSError as exc:
        # EADDRINUSE (48) on macOS / (98) on Linux when port is in use.
        if getattr(exc, "errno", None) in (48, 98):
            print(
                f"kailash-ml-dashboard: port {args.port} already in use",
                file=sys.stderr,
            )
            logger.error(
                "mldashboard.cli.port_in_use",
                extra={"port": args.port, "error": str(exc)},
            )
            return EXIT_PORT_IN_USE
        # Store connection errors surface here on startup — exit 3
        print(
            f"kailash-ml-dashboard: tracker store unreachable: {exc}",
            file=sys.stderr,
        )
        logger.error(
            "mldashboard.cli.store_unreachable",
            extra={"error": str(exc)},
        )
        return EXIT_STORE_UNREACHABLE
    except KeyboardInterrupt:
        logger.info("mldashboard.cli.shutdown", extra={"reason": "keyboard_interrupt"})
        return EXIT_OK
    except Exception as exc:  # pragma: no cover — last-resort error
        logger.exception("mldashboard.cli.error", extra={"error": str(exc)})
        return EXIT_RUNTIME_ERROR

    logger.info("mldashboard.cli.shutdown", extra={"reason": "clean"})
    return EXIT_OK


def main() -> None:
    """Console-script entry: exits with the return code from ``run``."""
    sys.exit(run())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mask_db_url(db_url: str) -> str:
    """Mask credentials in DB URL for log lines per rules/observability.md §6."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(db_url)
    except Exception:
        return "<unparseable db url>"

    if not parsed.scheme:
        return "<unparseable db url>"

    if parsed.hostname is None and not parsed.path:
        return "<unparseable db url>"

    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    path = parsed.path or ""
    # SQLite URLs have no userinfo — return verbatim path for them
    if parsed.scheme.startswith("sqlite"):
        return db_url
    # Mask userinfo uniformly (***@host) so credentials never land in logs
    if parsed.username or parsed.password:
        return f"{parsed.scheme}://***@{host}{port}{path}"
    return f"{parsed.scheme}://{host}{port}{path}"
