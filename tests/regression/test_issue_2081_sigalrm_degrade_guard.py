# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #2081 — the root conftest SIGALRM degrade guard.

The two restored root-regression CI steps pass ``--timeout-method=signal``
explicitly. A thread-method timeout CANNOT kill a test blocked in a C call, so
signal is the only method that makes a hang fail and name itself — that is what
made two of the three #2081 CI runs unreadable.

SIGALRM is POSIX-only, and **pytest-timeout has NO fallback of its own for a
missing SIGALRM**. Its only coercion is signal -> thread when off the main
thread; with ``method="signal"`` and any active timeout on a platform without
SIGALRM, ``pytest_timeout_set_timer`` reaches
``signal.signal(signal.SIGALRM, handler)`` and the run dies before a single
test executes:

    INTERNALERROR> AttributeError: module 'signal' has no attribute 'SIGALRM'
    ============================ no tests ran in 0.02s =============================

Root ``conftest.py::pytest_configure`` therefore degrades a requested
``signal`` back to ``thread`` with a ``RuntimeWarning`` where SIGALRM is
absent. These tests execute that branch directly rather than asserting it reads
correctly.

WHY A SUBPROCESS, NOT AN IN-PROCESS IMPORT: root ``conftest.py`` is already
loaded as a plugin in THIS session, and its ``pytest_configure`` calls
``install_cost_guard``, which monkeypatches ``dotenv.load_dotenv`` and scrubs
provider secrets from ``os.environ`` process-wide. Re-driving it in-process
would mutate the running session. The subprocess also lets us delete
``signal.SIGALRM`` without affecting this interpreter.

NOTE ON WHY NO WINDOWS JOB COVERS THIS: no workflow this PR touches runs a
Windows matrix (`trust-plane.yml` is the repo's only `windows-latest` job and
its `paths:` filter is `src/kailash/trust/**`). These tests are the coverage —
they simulate the platform condition rather than requiring the platform, which
is why they run on every Linux CI job instead of none.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.regression]

REPO_ROOT = Path(__file__).resolve().parents[2]
ROOT_CONFTEST = REPO_ROOT / "conftest.py"


def _drive_pytest_configure(*, delete_sigalrm: bool, requested: str) -> dict:
    """Drive root conftest's pytest_configure in a clean subprocess.

    Returns the parsed result dict: the resolved ``timeout_method`` and whether
    a RuntimeWarning naming SIGALRM was emitted.
    """
    script = textwrap.dedent(
        f"""
        import importlib.util, json, signal, warnings

        delete_sigalrm = {delete_sigalrm!r}
        if delete_sigalrm:
            # Simulate a platform without SIGALRM (Windows).
            assert hasattr(signal, "SIGALRM"), "precondition: host HAS SIGALRM"
            del signal.SIGALRM
        assert hasattr(signal, "SIGALRM") is (not delete_sigalrm)

        spec = importlib.util.spec_from_file_location(
            "root_conftest_under_test", {str(ROOT_CONFTEST)!r}
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        class _Opt:
            timeout_method = {requested!r}

        class _Cfg:
            option = _Opt()

        cfg = _Cfg()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            mod.pytest_configure(cfg)

        sigalrm_warnings = [
            str(w.message)
            for w in caught
            if issubclass(w.category, RuntimeWarning) and "SIGALRM" in str(w.message)
        ]
        print(
            "RESULT_JSON:"
            + json.dumps(
                {{
                    "timeout_method": cfg.option.timeout_method,
                    "sigalrm_warnings": sigalrm_warnings,
                }}
            )
        )
        """
    )
    env = dict(os.environ)
    # The repo `src` FIRST — a stale installed wheel otherwise shadows the repo
    # source and the conftest's own imports fail with an unrelated ImportError.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(REPO_ROOT / "src"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    proc = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(REPO_ROOT),
        env=env,
    )
    assert proc.returncode == 0, (
        f"subprocess failed (rc={proc.returncode})\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
    )
    marker = "RESULT_JSON:"
    line = next((ln for ln in proc.stdout.splitlines() if ln.startswith(marker)), None)
    assert line is not None, f"no RESULT_JSON in stdout:\n{proc.stdout}"

    import json as _json

    return _json.loads(line[len(marker) :])


@pytest.mark.timeout(180)
def test_signal_degrades_to_thread_where_sigalrm_is_absent():
    """The degrade branch EXECUTES — this is the Windows path, simulated.

    Without this guard, ``--timeout-method=signal`` on a no-SIGALRM platform
    kills the run at the first timed test with
    ``AttributeError: module 'signal' has no attribute 'SIGALRM'`` and zero
    tests execute.
    """
    result = _drive_pytest_configure(delete_sigalrm=True, requested="signal")

    assert result["timeout_method"] == "thread", (
        "the SIGALRM degrade branch did NOT fire — a --timeout-method=signal "
        "invocation on a platform without SIGALRM would die at collection with "
        "AttributeError before any test ran"
    )
    assert result["sigalrm_warnings"], (
        "the degrade happened SILENTLY — it MUST emit a RuntimeWarning naming "
        "SIGALRM so the operator knows a thread-method timeout can report a "
        "hung test but cannot kill one blocked in a C call"
    )
    assert "thread" in result["sigalrm_warnings"][0]


@pytest.mark.timeout(180)
def test_signal_is_left_intact_where_sigalrm_exists():
    """The negative control — the guard MUST NOT degrade on POSIX.

    Without this, a guard that unconditionally returned ``thread`` would pass
    the test above while silently disabling signal-method timeouts on the very
    Linux CI runners the #2081 fix depends on.
    """
    result = _drive_pytest_configure(delete_sigalrm=False, requested="signal")

    assert result["timeout_method"] == "signal", (
        "the guard degraded signal -> thread on a platform that HAS SIGALRM; "
        "that silently removes the only timeout method able to kill a test "
        "blocked in a C call (#2081)"
    )
    assert not result[
        "sigalrm_warnings"
    ], "the guard warned on a platform where SIGALRM is available"


@pytest.mark.timeout(180)
def test_an_explicitly_requested_thread_method_is_untouched():
    """``--timeout-method=thread`` is honored as-is on both platforms."""
    for delete in (True, False):
        result = _drive_pytest_configure(delete_sigalrm=delete, requested="thread")
        assert result["timeout_method"] == "thread"
        assert not result["sigalrm_warnings"], (
            "the guard warned about SIGALRM for a request that never asked for "
            f"the signal method (delete_sigalrm={delete})"
        )
