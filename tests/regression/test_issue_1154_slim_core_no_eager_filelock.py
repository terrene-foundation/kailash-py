# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: issue #1154 — slim-core delegate path must not eagerly import filelock.

2.24.1 (hotfix) promoted `filelock>=3.0` from the `[trust]` extra into slim-core
to make `pip install kailash` work — because `kailash.delegate.types` imports
`validate_id` from `kailash.trust._locking`, which had a module-scope
`from filelock import FileLock, Timeout`.

2.25.1 (#1154) lazy-imported filelock inside `_locking.file_lock()` so the
slim-core delegate path no longer touches filelock. This test pins the
invariant: the `_locking` module loads cleanly without filelock, AND a fresh
Python process importing `validate_id` does not load filelock.
"""

from __future__ import annotations

import subprocess
import sys


def test_validate_id_does_not_eager_import_filelock() -> None:
    """Subprocess: importing validate_id MUST NOT load filelock in sys.modules.

    A subprocess is required because pytest's process may have already imported
    filelock via other test paths. The clean subprocess proves the slim-core
    invariant: a fresh interpreter that only imports the delegate-reachable
    surface MUST see no `filelock` in `sys.modules`.
    """
    code = (
        "import sys\n"
        "from kailash.trust._locking import validate_id\n"
        "validate_id('test-id-123')\n"
        "assert 'filelock' not in sys.modules, (\n"
        "    'filelock leaked into sys.modules after importing validate_id; '\n"
        "    'lazy-import in trust/_locking.py::file_lock broke — see #1154'\n"
        ")\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"slim-core delegate path eagerly imports filelock\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


def test_delegate_types_does_not_eager_import_filelock() -> None:
    """End-to-end: importing kailash.delegate.types MUST NOT load filelock.

    This is the exact failure mode 2.24.1 hotfixed:
    `import kailash.delegate` → ModuleNotFoundError: filelock (on clean install
    without [trust] extra). Lazy-import #1154 restored slim-core installability.
    """
    code = (
        "import sys\n"
        "import kailash.delegate.types  # noqa: F401\n"
        "assert 'filelock' not in sys.modules, (\n"
        "    'kailash.delegate.types eagerly loads filelock; '\n"
        "    'slim-core install budget regressed — see #1154'\n"
        ")\n"
        "print('OK')\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"kailash.delegate.types eagerly imports filelock\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "OK" in result.stdout


def test_file_lock_still_works_when_filelock_available() -> None:
    """Sanity: file_lock() still works after the lazy-import refactor.

    Same-process test (filelock is installed in the dev env) — verifies the
    in-body import resolves and the context manager acquires/releases.
    """
    import tempfile
    from pathlib import Path

    from kailash.trust._locking import file_lock

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "test.lock"
        with file_lock(lock_path, timeout=5.0):
            pass  # context entered + exited cleanly
        # lock file was created
        assert lock_path.exists()
