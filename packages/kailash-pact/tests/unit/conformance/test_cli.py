# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 tests for the ``pact-conformance-runner`` CLI entry point.

These tests pin the CLI contract:

- Args / parser: positional ``vector_dir``, optional ``--json`` and
  ``--verbose``.
- Exit codes: ``0`` = all passed (or unsupported-only), ``1`` = any
  failed, ``2`` = usage / I/O / parse error.
- Stdout shape: machine-readable JSON when ``--json`` is set; otherwise
  a single human-readable summary line.
- Stderr shape: per-vector progress under ``--verbose``, plus a
  trailing summary that mirrors stdout.
- Logger discipline: the CLI uses ``logging.getLogger(__name__)`` for
  diagnostic events; never ``print()`` for non-output (rule
  observability.md §1).

Fixtures synthesise vector JSON files matching the real N4/N5 schema so
the load + run path exercises the same code as production. We do NOT
mock the runner -- the CLI is thin enough that its behaviour reduces to
the runner's behaviour, and a pure-CLI Tier 1 test that mocks the runner
proves nothing.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest

from pact.conformance import cli
from pact.conformance.cli import (
    EXIT_FAILED_VECTORS,
    EXIT_OK,
    EXIT_USAGE_ERROR,
    main,
)


# ---------------------------------------------------------------------------
# Vector JSON helpers
# ---------------------------------------------------------------------------


# Canonical JSON strings for the synthetic N4 / N5 vectors. These match the
# byte-for-byte forms that the runner emits given the `input` block.
_N4_ZONE1_CANONICAL = (
    '{"event_id":"00000000-0000-4000-8000-000000000001",'
    '"timestamp":"2026-01-01T00:00:00+00:00",'
    '"role_address":"D1-R1","posture":"pseudo_agent",'
    '"action":"ping","zone":"AutoApproved","reason":"ok",'
    '"tier":"zone1_pseudo","tenant_id":null,"signature":null}'
)


_N5_BLOCKED_CANONICAL = (
    '{"schema":"pact.governance.verdict.v1","source":"D1-R1-T1-R1",'
    '"timestamp":"2026-01-01T00:00:00+00:00","gradient":"Blocked",'
    '"action":"wire_transfer","payload":{"details":{},'
    '"reason":"exceeded financial limit",'
    '"role_address":"D1-R1-T1-R1"}}'
)


def _write_n4_passing_vector(directory: Path, vector_id: str = "stub_n4_pass") -> Path:
    """Write an N4 vector that the runner will mark PASSED."""
    payload = {
        "id": vector_id,
        "contract": "N4",
        "description": "stub n4 pass vector",
        "input": {
            "verdict": {
                "zone": "AutoApproved",
                "reason": "ok",
                "action": "ping",
                "role_address": "D1-R1",
                "details": {},
            },
            "posture": "PseudoAgent",
            "fixed_event_id": "00000000-0000-4000-8000-000000000001",
            "fixed_timestamp": "2026-01-01T00:00:00+00:00",
        },
        "expected": {
            "tier": "zone1_pseudo",
            "durable": False,
            "requires_signature": False,
            "requires_replication": False,
            "canonical_json": _N4_ZONE1_CANONICAL,
        },
        "hash_algo": "sha256",
    }
    path = directory / f"{vector_id}.json"
    path.write_text(json.dumps(payload))
    return path


def _write_n4_failing_vector(directory: Path, vector_id: str = "stub_n4_fail") -> Path:
    """Write an N4 vector whose canonical_json drifts by one byte."""
    drifted = _N4_ZONE1_CANONICAL.replace(
        '"tier":"zone1_pseudo"', '"tier":"zone1_PSEUDO"'
    )
    assert drifted != _N4_ZONE1_CANONICAL
    payload = {
        "id": vector_id,
        "contract": "N4",
        "description": "stub n4 fail vector",
        "input": {
            "verdict": {
                "zone": "AutoApproved",
                "reason": "ok",
                "action": "ping",
                "role_address": "D1-R1",
                "details": {},
            },
            "posture": "PseudoAgent",
            "fixed_event_id": "00000000-0000-4000-8000-000000000001",
            "fixed_timestamp": "2026-01-01T00:00:00+00:00",
        },
        "expected": {
            "canonical_json": drifted,
        },
        "hash_algo": "sha256",
    }
    path = directory / f"{vector_id}.json"
    path.write_text(json.dumps(payload))
    return path


def _write_n5_passing_vector(directory: Path, vector_id: str = "stub_n5_pass") -> Path:
    """Write an N5 vector that the runner will mark PASSED."""
    payload = {
        "id": vector_id,
        "contract": "N5",
        "description": "stub n5 pass vector",
        "input": {
            "verdict": {
                "zone": "Blocked",
                "reason": "exceeded financial limit",
                "action": "wire_transfer",
                "role_address": "D1-R1-T1-R1",
                "details": {},
            },
            "fixed_timestamp": "2026-01-01T00:00:00+00:00",
            "evidence_source": "D1-R1-T1-R1",
        },
        "expected": {
            "canonical_json": _N5_BLOCKED_CANONICAL,
        },
        "hash_algo": "sha256",
    }
    path = directory / f"{vector_id}.json"
    path.write_text(json.dumps(payload))
    return path


def _write_unparseable_contract_vector(
    directory: Path, vector_id: str = "stub_n7_future"
) -> Path:
    """Write a vector with a contract field outside {N4, N5}.

    The loader (``parse_vector``) rejects this at parse-time, so the runner
    never sees it as ``UNSUPPORTED``. The CLI surfaces the load error as
    ``EXIT_USAGE_ERROR`` (2). The runner's UNSUPPORTED branch is reachable
    only via direct in-process construction of a ``ConformanceVector`` and
    is exercised in ``test_runner.py``.
    """
    payload = {
        "id": vector_id,
        "contract": "N7",
        "description": "stub future-contract vector",
        "input": {
            "verdict": {
                "zone": "AutoApproved",
                "reason": "ok",
                "action": "ping",
                "role_address": "D1-R1",
                "details": {},
            },
            "fixed_timestamp": "2026-01-01T00:00:00+00:00",
        },
        "expected": {
            "canonical_json": "{}",
        },
        "hash_algo": "sha256",
    }
    path = directory / f"{vector_id}.json"
    path.write_text(json.dumps(payload))
    return path


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def test_build_parser_accepts_vector_dir_only(tmp_path: Path) -> None:
    parser = cli.build_parser()
    args = parser.parse_args([str(tmp_path)])
    assert args.vector_dir == tmp_path
    assert args.emit_json is False
    assert args.verbose is False


def test_build_parser_accepts_json_and_verbose(tmp_path: Path) -> None:
    parser = cli.build_parser()
    args = parser.parse_args([str(tmp_path), "--json", "--verbose"])
    assert args.emit_json is True
    assert args.verbose is True


def test_build_parser_short_verbose_flag(tmp_path: Path) -> None:
    parser = cli.build_parser()
    args = parser.parse_args([str(tmp_path), "-v"])
    assert args.verbose is True


def test_build_parser_missing_vector_dir_exits(capsys: pytest.CaptureFixture) -> None:
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as excinfo:
        parser.parse_args([])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


def test_main_returns_zero_when_all_passed(tmp_path: Path) -> None:
    _write_n4_passing_vector(tmp_path, "v1_pass")
    _write_n5_passing_vector(tmp_path, "v2_pass")
    rc = main([str(tmp_path)])
    assert rc == EXIT_OK


def test_main_returns_one_when_any_failed(tmp_path: Path) -> None:
    _write_n4_passing_vector(tmp_path, "v1_pass")
    _write_n4_failing_vector(tmp_path, "v2_fail")
    rc = main([str(tmp_path)])
    assert rc == EXIT_FAILED_VECTORS


def test_main_returns_two_for_unparseable_contract(tmp_path: Path) -> None:
    """A future / unrecognised contract is rejected by the loader.

    The runner's UNSUPPORTED branch covers in-process constructions only;
    the file loader treats unrecognised contracts as a usage error so CI
    matrix jobs surface a stale runner immediately rather than silently
    skipping vectors.
    """
    _write_n4_passing_vector(tmp_path, "v1_pass")
    _write_unparseable_contract_vector(tmp_path, "v2_n7")
    rc = main([str(tmp_path)])
    assert rc == EXIT_USAGE_ERROR


def test_main_returns_two_for_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    rc = main([str(missing)])
    assert rc == EXIT_USAGE_ERROR


def test_main_returns_two_for_file_not_dir(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir.json"
    file_path.write_text("{}")
    rc = main([str(file_path)])
    assert rc == EXIT_USAGE_ERROR


def test_main_returns_two_for_invalid_vector(tmp_path: Path) -> None:
    """An unparseable vector blocks the runner before any vector runs."""
    (tmp_path / "broken.json").write_text("{ this is not valid json")
    rc = main([str(tmp_path)])
    assert rc == EXIT_USAGE_ERROR


# ---------------------------------------------------------------------------
# Stdout / stderr shape
# ---------------------------------------------------------------------------


def test_main_json_output_has_canonical_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _write_n4_passing_vector(tmp_path, "v1_pass")
    _write_n4_failing_vector(tmp_path, "v2_fail")
    rc = main([str(tmp_path), "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["total"] == 2
    assert payload["passed"] == 1
    assert payload["failed"] == 1
    assert payload["unsupported"] == 0
    assert len(payload["vectors"]) == 2
    # Each vector entry has the documented keys.
    for entry in payload["vectors"]:
        assert set(entry.keys()) == {
            "vector_id",
            "contract",
            "outcome",
            "reason",
            "expected_sha256",
            "actual_sha256",
        }
        assert entry["outcome"] in {"PASSED", "FAILED", "UNSUPPORTED"}
    # Exit code reflects FAILED count.
    assert rc == EXIT_FAILED_VECTORS


def test_main_default_summary_on_stdout(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _write_n4_passing_vector(tmp_path, "v1_pass")
    rc = main([str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == EXIT_OK
    # Default mode emits a single summary line on stdout.
    assert captured.out.startswith("conformance: total=1")
    assert "passed=1" in captured.out
    # Stderr also has the summary so verbose + non-verbose share that surface.
    assert "conformance:" in captured.err


def test_main_verbose_writes_progress_to_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    _write_n4_passing_vector(tmp_path, "v_pass")
    _write_n4_failing_vector(tmp_path, "v_fail")
    rc = main([str(tmp_path), "--verbose"])
    captured = capsys.readouterr()
    assert rc == EXIT_FAILED_VECTORS
    # Verbose progress lives on stderr.
    assert "[PASSED] v_pass" in captured.err
    assert "[FAILED] v_fail" in captured.err
    # Failure body included when failed > 0.
    assert "canonical_json mismatch" in captured.err


def test_main_failure_renders_diff_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """When any vector FAILS, stderr carries the rendered failure diff."""
    _write_n4_failing_vector(tmp_path, "drift")
    rc = main([str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == EXIT_FAILED_VECTORS
    assert "[drift]" in captured.err
    assert "expected_sha256" in captured.err
    assert "actual_sha256" in captured.err


def test_main_json_payload_does_not_pollute_stdout_with_progress(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """``--json`` mode reserves stdout for JSON; progress stays on stderr."""
    _write_n4_passing_vector(tmp_path, "v_pass")
    main([str(tmp_path), "--json", "--verbose"])
    captured = capsys.readouterr()
    # stdout MUST be a single JSON document.
    payload = json.loads(captured.out)
    assert payload["total"] == 1
    # Progress lines and trailing summary live on stderr only.
    assert "[PASSED] v_pass" in captured.err
    assert "conformance: total=1" in captured.err


# ---------------------------------------------------------------------------
# Observability discipline
# ---------------------------------------------------------------------------


def test_main_uses_module_logger_not_print(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture
) -> None:
    """Diagnostic events go through the module logger, not ``print``."""
    _write_n4_passing_vector(tmp_path, "v_pass")
    with caplog.at_level(logging.INFO, logger="pact.conformance.cli"):
        main([str(tmp_path)])
    # At least the start + complete events recorded via the logger.
    event_messages = {record.message for record in caplog.records}
    assert any("conformance.cli.start" in msg for msg in event_messages)
    assert any("conformance.cli.complete" in msg for msg in event_messages)
