# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""``pact-conformance-runner`` CLI entry point.

Drive a directory of N4/N5 conformance vectors through
:class:`~pact.conformance.runner.ConformanceRunner` and emit either a
machine-readable JSON report (``--json``, intended for CI matrix jobs) or
a human-readable summary on stdout. Per-vector progress lines and the
failure diff body go to stderr so the JSON payload remains parseable by
downstream tools without filtering.

Exit codes:

- ``0`` -- every vector landed as ``PASSED`` or ``UNSUPPORTED``.
  ``UNSUPPORTED`` is treated as a soft skip for exit-code purposes so a
  vector dir holding a future contract (N7, N8, ...) does not fail this
  runner before the runner is updated. The runner still surfaces the
  ``unsupported`` count in the JSON payload + stderr summary so CI can
  alert on persistent unsupported counts in a separate gate.
- ``1`` -- one or more vectors landed as ``FAILED`` (canonical-JSON
  mismatch OR an N4 invariant disagreement). Failure diffs are rendered
  to stderr via :meth:`RunnerReport.render_failure_report`.
- ``2`` -- argument / I/O / parse error before the runner could attempt
  any vector (missing dir, invalid vector JSON, etc.).

The CLI is the second public surface for the conformance runner (the
first is :func:`pact.conformance.run_vectors` from Python). It exists so
CI matrix jobs in this repo AND downstream consumers can run the cross-SDK
contract without writing a Python harness.

Usage::

    pact-conformance-runner /path/to/vectors --json
    pact-conformance-runner /path/to/vectors --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Sequence

from pact.conformance.runner import ConformanceRunner, RunnerReport, VectorStatus
from pact.conformance.vectors import (
    ConformanceVectorError,
    load_vectors_from_dir,
)

logger = logging.getLogger(__name__)

__all__ = ["build_parser", "main"]


# Exit codes -- pinned constants so callers can reason about CI behaviour.
EXIT_OK = 0
EXIT_FAILED_VECTORS = 1
EXIT_USAGE_ERROR = 2


def build_parser() -> argparse.ArgumentParser:
    """Construct the argparse parser for the CLI.

    Exposed as a public helper so tests + ``--help`` documentation can
    drive the parser without invoking :func:`main`.
    """
    parser = argparse.ArgumentParser(
        prog="pact-conformance-runner",
        description=(
            "Drive a directory of PACT N4/N5 conformance vectors through the "
            "Python runner and report PASSED / FAILED / UNSUPPORTED outcomes."
        ),
    )
    parser.add_argument(
        "vector_dir",
        type=Path,
        help="Directory containing *.json conformance vectors.",
    )
    parser.add_argument(
        "--json",
        dest="emit_json",
        action="store_true",
        help=(
            "Emit a machine-readable JSON report on stdout (CI mode). When "
            "absent, a human-readable summary is printed instead."
        ),
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Emit per-vector progress lines on stderr (status + reason).",
    )
    return parser


def _build_json_payload(report: RunnerReport) -> dict:
    """Render :class:`RunnerReport` as the canonical CI JSON payload.

    Shape pinned by README/specs and consumed by CI matrix jobs:

    .. code-block:: json

       {"total": N, "passed": N, "failed": N, "unsupported": N,
        "vectors": [
          {"vector_id": "...", "contract": "N4|N5",
           "outcome": "PASSED|FAILED|UNSUPPORTED",
           "reason": "...",
           "expected_sha256": "...",
           "actual_sha256": "..."}
        ]}
    """
    return {
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "unsupported": report.unsupported,
        "vectors": [
            {
                "vector_id": outcome.vector_id,
                "contract": outcome.contract,
                "outcome": outcome.status.value.upper(),
                "reason": outcome.reason,
                "expected_sha256": outcome.expected_sha256,
                "actual_sha256": outcome.actual_sha256,
            }
            for outcome in report.outcomes
        ],
    }


def _emit_progress_lines(report: RunnerReport, stderr) -> None:
    """Write per-vector progress lines to ``stderr`` (used with ``--verbose``)."""
    for outcome in report.outcomes:
        # One line per vector; status + id are the load-bearing fields, the
        # reason is included only when non-empty so PASSED rows stay quiet.
        if outcome.reason:
            stderr.write(
                f"[{outcome.status.value.upper()}] {outcome.vector_id} "
                f"({outcome.contract}): {outcome.reason}\n"
            )
        else:
            stderr.write(
                f"[{outcome.status.value.upper()}] {outcome.vector_id} "
                f"({outcome.contract})\n"
            )


def _emit_summary(report: RunnerReport, stderr) -> None:
    """Write the trailing summary line(s) to ``stderr``."""
    stderr.write(
        f"conformance: total={report.total} "
        f"passed={report.passed} failed={report.failed} "
        f"unsupported={report.unsupported}\n"
    )
    if report.failed > 0:
        stderr.write(report.render_failure_report())
        stderr.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point registered via ``[project.scripts]``.

    Returns an integer exit code; never raises. All errors are logged
    (logger, stderr) and converted to ``EXIT_USAGE_ERROR`` /
    ``EXIT_FAILED_VECTORS``.
    """
    parser = build_parser()
    # argparse exits with code 2 on usage error, which matches our intent.
    args = parser.parse_args(argv)
    stdout = sys.stdout
    stderr = sys.stderr

    logger.info(
        "conformance.cli.start",
        extra={
            "vector_dir": str(args.vector_dir),
            "emit_json": args.emit_json,
            "verbose": args.verbose,
        },
    )

    if not args.vector_dir.exists():
        stderr.write(
            f"pact-conformance-runner: vector directory does not exist: "
            f"{args.vector_dir}\n"
        )
        logger.error(
            "conformance.cli.error",
            extra={"reason": "vector_dir_missing", "path": str(args.vector_dir)},
        )
        return EXIT_USAGE_ERROR
    if not args.vector_dir.is_dir():
        stderr.write(
            f"pact-conformance-runner: vector_dir is not a directory: "
            f"{args.vector_dir}\n"
        )
        logger.error(
            "conformance.cli.error",
            extra={"reason": "vector_dir_not_dir", "path": str(args.vector_dir)},
        )
        return EXIT_USAGE_ERROR

    try:
        vectors = load_vectors_from_dir(args.vector_dir)
    except ConformanceVectorError as exc:
        stderr.write(f"pact-conformance-runner: failed to load vectors: {exc}\n")
        logger.exception(
            "conformance.cli.load_failed",
            extra={"path": str(args.vector_dir)},
        )
        return EXIT_USAGE_ERROR

    runner = ConformanceRunner()
    try:
        report = runner.run(vectors)
    except ConformanceVectorError as exc:
        # parse_vector enforced shape at load; this branch covers the
        # runner-side contract assertions (e.g. missing fixed_event_id on
        # an otherwise well-formed N4 vector).
        stderr.write(f"pact-conformance-runner: runner aborted: {exc}\n")
        logger.exception(
            "conformance.cli.run_failed",
            extra={"path": str(args.vector_dir)},
        )
        return EXIT_USAGE_ERROR

    if args.verbose:
        _emit_progress_lines(report, stderr)

    if args.emit_json:
        payload = _build_json_payload(report)
        # Machine-readable JSON on stdout; one final newline so consumers
        # using line-buffered IO see the payload terminate.
        stdout.write(json.dumps(payload, ensure_ascii=False))
        stdout.write("\n")
    else:
        # Human-readable summary on stdout when --json is absent.
        stdout.write(
            f"conformance: total={report.total} "
            f"passed={report.passed} failed={report.failed} "
            f"unsupported={report.unsupported}\n"
        )

    # Always emit the stderr summary so verbose + JSON modes share the
    # same trailing line shape.
    _emit_summary(report, stderr)

    logger.info(
        "conformance.cli.complete",
        extra={
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "unsupported": report.unsupported,
        },
    )

    if report.failed > 0:
        return EXIT_FAILED_VECTORS
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover -- exercised via console_script
    raise SystemExit(main())
