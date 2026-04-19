# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 2 integration tests for ``km.doctor()``.

Exercises the real doctor function (no mocking) and, when the
``km-doctor`` console script is installed, the subprocess path.

Per ``specs/ml-backends.md`` §7:

- Exit 0 — all green (CPU present and any ``--require`` satisfied).
- Exit 1 — any warning.
- Exit 2 — ``--require=<backend>`` unreachable OR a probe raised.

These tests are Tier 2 per ``rules/testing.md``: the probes touch the
real PyTorch install, the real platform module, and (for the subprocess
test) a real subprocess invocation. No ``@patch`` / ``MagicMock``.
"""
from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys

import pytest

import kailash_ml as km
from kailash_ml.doctor import doctor, main


pytestmark = [pytest.mark.integration]


def _torch_has_cuda() -> bool:
    try:
        import torch
    except ImportError:
        return False
    try:
        return bool(torch.cuda.is_available())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core doctor() contract
# ---------------------------------------------------------------------------


def test_doctor_cpu_available() -> None:
    """CPU is always available -> doctor returns 0 and CPU probe is ok."""
    buf = io.StringIO()
    code = doctor(as_json=True, out=buf)
    assert code == 0
    payload = json.loads(buf.getvalue())
    cpu = next(p for p in payload["backends"] if p["backend"] == "cpu")
    assert cpu["status"] == "ok"
    assert cpu["devices"] >= 1


def test_doctor_json_output_shape() -> None:
    """``--json`` output exposes the 4 probed backends with required keys."""
    buf = io.StringIO()
    code = doctor(as_json=True, out=buf)
    payload = json.loads(buf.getvalue())
    assert payload["exit_code"] == code
    assert payload["require"] is None
    backends = {p["backend"] for p in payload["backends"]}
    assert backends == {"cpu", "cuda", "mps", "rocm"}
    for entry in payload["backends"]:
        # Mandatory structured fields per spec §7.2
        assert "status" in entry
        assert "version" in entry
        assert "devices" in entry
        assert "warnings" in entry
        assert "failures" in entry


def test_doctor_require_missing_backend() -> None:
    """``--require=cuda`` on a CPU-only host -> exit 2."""
    if _torch_has_cuda():
        pytest.skip("CUDA actually available on this host")
    buf = io.StringIO()
    code = doctor(require="cuda", as_json=True, out=buf)
    assert code == 2
    payload = json.loads(buf.getvalue())
    assert payload["require"] == "cuda"


def test_doctor_require_cpu_ok() -> None:
    """``--require=cpu`` on any host -> exit 0 (CPU always present)."""
    buf = io.StringIO()
    code = doctor(require="cpu", as_json=True, out=buf)
    assert code == 0


def test_doctor_main_cli_parses_flags() -> None:
    """``main([...])`` calls ``doctor`` with the parsed flags."""
    # --json --require=cpu should still exit 0 on any host
    code = main(["--json", "--require=cpu"])
    assert code == 0


def test_km_doctor_is_public_symbol() -> None:
    """``km.doctor`` resolves to the same callable as ``kailash_ml.doctor``."""
    # Eager import path — matches orphan-detection §6.
    assert km.doctor is doctor


# ---------------------------------------------------------------------------
# Console-script / subprocess path
# ---------------------------------------------------------------------------


def test_km_doctor_console_script_or_module_json() -> None:
    """Subprocess invocation prints parseable JSON and exits 0 on CPU.

    Prefers the ``km-doctor`` console script when available (installed
    by ``pip install kailash-ml`` with the matching ``[project.scripts]``
    entry). Falls back to ``python -m kailash_ml.doctor`` otherwise.
    Either way the test validates that an end-user invoking the binary
    from a shell can parse the JSON and rely on the exit code.
    """
    console = shutil.which("km-doctor")
    if console is not None:
        cmd = [console, "--json"]
    else:
        cmd = [
            sys.executable,
            "-W",
            "ignore::RuntimeWarning",
            "-m",
            "kailash_ml.doctor",
            "--json",
        ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=30.0,
    )
    assert (
        proc.returncode == 0
    ), f"km-doctor failed: exit={proc.returncode}, stdout={proc.stdout!r}, stderr={proc.stderr!r}"
    payload = json.loads(proc.stdout)
    assert payload["exit_code"] == 0
    assert any(
        p["backend"] == "cpu" and p["status"] == "ok" for p in payload["backends"]
    )
