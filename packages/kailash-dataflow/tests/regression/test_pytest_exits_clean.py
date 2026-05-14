# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #1002 — pytest exits cleanly without setsid wrapper.

Asserts that a representative Tier-1 subset of
``packages/kailash-dataflow/tests/unit/`` completes within timeout via a
``subprocess.run`` invocation. If the post-summary ``_Py_Finalize`` hang
reproduces, the subprocess never returns and the regression fails with
``subprocess.TimeoutExpired`` (raised by ``run(..., timeout=OUTER_TIMEOUT)``).

Why subprocess instead of an in-process check: the hang manifests at process
finalization — when the test runner is itself the leaking process, it never
hands control back to assert on its own state. Running pytest as a subprocess
isolates the lifecycle; the parent observes exit code AND wall-clock from
outside the GC arena that would block the hang.

Subset chosen: ``tests/unit/cache/`` — covers the Redis + SQLite cleanup paths
exercised by 4 test files (``test_async_redis_adapter.py``,
``test_auto_detection.py``, ``test_memory_cache.py``,
``test_redis_invalidate_v2_keyspace.py``), the highest-risk leak class
surfaced in Shard 2. Small enough to run in <30 s under healthy conditions
(~4 s observed today); large enough to exercise the cache + lightweight-pool
+ runtime-cache cleanup paths Shards 1-3 closed.

Per ``rules/refactor-invariants.md`` MUST Rule 1 (invariant test in CI default
path, no special marker exclusion) + ``rules/testing.md`` § "Regression
Testing" (lives at ``tests/regression/``, marked ``@pytest.mark.regression``,
never deleted).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # packages/kailash-dataflow/
SUBSET = PACKAGE_ROOT / "tests" / "unit" / "cache"
INNER_TIMEOUT = 60  # per-test pytest --timeout (seconds)
OUTER_TIMEOUT = 300  # subprocess.run wait (5x inner; safety margin)
WALL_CLOCK_BUDGET_S = 90  # total wall-clock budget for the subset run

pytestmark = [pytest.mark.regression]


# `OUTER_TIMEOUT + 30s` gives `subprocess.TimeoutExpired` time to raise and
# the except-handler time to format the diagnostic message BEFORE pytest's
# outer per-test timeout fires. Defense in depth.
@pytest.mark.timeout(OUTER_TIMEOUT + 30)
def test_pytest_exits_clean_without_setsid_wrapper() -> None:
    """Run the Tier-1 cache subset as a subprocess; assert clean exit + budget.

    Guards against re-introducing the ``_Py_Finalize`` thread leak that issue
    #1002 closed. If the subprocess hangs past ``OUTER_TIMEOUT``,
    ``subprocess.run`` raises ``TimeoutExpired`` — the test fails loudly with
    the actual hang rather than a generic timeout.

    Two assertions:

    1. ``proc.returncode == 0`` — pytest's own exit code (test suite green).
    2. ``elapsed <= WALL_CLOCK_BUDGET_S`` — subprocess returned within budget.
       A subprocess that returns cleanly but slowly indicates a bounded leak
       worth investigating before it grows.
    """
    assert SUBSET.is_dir(), f"subset path missing: {SUBSET}"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(SUBSET),
        "-q",
        f"--timeout={INNER_TIMEOUT}",
        # `-p no:cacheprovider` keeps the subprocess from polluting
        # `.pytest_cache/` in the parent's cwd — clean isolation between the
        # outer pytest invocation and this regression's inner subprocess.
        "-p",
        "no:cacheprovider",
    ]
    started = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=OUTER_TIMEOUT,
        )
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - started
        # Truncate streams in case they are very large.
        stdout_tail = (exc.stdout or b"")[-2000:].decode("utf-8", errors="replace")
        stderr_tail = (exc.stderr or b"")[-1000:].decode("utf-8", errors="replace")
        pytest.fail(
            f"pytest subset did NOT return within {OUTER_TIMEOUT}s "
            f"(wall-clock {elapsed:.1f}s) — the _Py_Finalize hang from "
            f"issue #1002 may have regressed.\n"
            f"--- stdout (tail) ---\n{stdout_tail}\n"
            f"--- stderr (tail) ---\n{stderr_tail}"
        )

    elapsed = time.monotonic() - started

    assert proc.returncode == 0, (
        f"pytest subset failed: rc={proc.returncode}\n"
        f"--- stdout (tail) ---\n{proc.stdout[-2000:]}\n"
        f"--- stderr (tail) ---\n{proc.stderr[-1000:]}"
    )
    assert elapsed <= WALL_CLOCK_BUDGET_S, (
        f"pytest subset wall-clock {elapsed:.1f}s exceeded budget "
        f"{WALL_CLOCK_BUDGET_S}s — post-summary hang may have regressed "
        f"(issue #1002). subprocess returned cleanly, so the leak is bounded "
        f"but growing.\n"
        f"--- stdout (tail) ---\n{proc.stdout[-1500:]}"
    )
