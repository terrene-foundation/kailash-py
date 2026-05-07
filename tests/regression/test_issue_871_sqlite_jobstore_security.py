# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #871 — SQLite job-store TOCTOU + WAL/SHM mode.

Two HIGH findings closed by this set:

1. **TOCTOU on chmod.** Prior code used ``open(path, "a").close()`` followed
   by ``os.chmod(path, 0o600)``. A parent-directory-controlling attacker
   could swap the target between the two calls.
   Fix: ``os.open(path, O_RDWR|O_CREAT|O_NOFOLLOW, 0o600)`` — atomic + symlink
   refusal in one syscall.

2. **WAL/SHM sidecars world-readable.** SQLAlchemy + SQLite in WAL mode
   creates ``<db>-wal`` and ``<db>-shm`` at first write under default umask
   (commonly ``0o644``). The sidecars carry the same job-data bytes the
   main DB protects via ``0o600``.
   Fix: pre-init WAL mode + chmod sidecars before APScheduler ever opens
   the file.

Per ``rules/testing.md`` § "Regression Testing" + § "Behavioral Regression
Tests Over Source-Grep", these tests CALL the function and assert
raise/return + actual filesystem mode bits — not grep source for literal
substrings.
"""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

import pytest

# Skip the entire module on non-POSIX platforms — POSIX-specific behavior
# (O_NOFOLLOW, fchmod, mode bits in stat result).
pytestmark = pytest.mark.skipif(
    os.name != "posix",
    reason="Issue #871 hardening is POSIX-only (O_NOFOLLOW, mode bits, fchmod)",
)


# ---------------------------------------------------------------------------
# Tier 1 — direct unit tests on _secure_init_sqlite_jobstore
# (no APScheduler dependency; tests the helper in isolation)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_secure_init_creates_main_db_with_0o600(tmp_path: Path) -> None:
    """``_secure_init_sqlite_jobstore`` creates the main DB at mode 0o600
    atomically — no open-then-chmod race window.
    """
    from kailash.runtime.scheduler import _secure_init_sqlite_jobstore

    db = tmp_path / "schedules.db"
    _secure_init_sqlite_jobstore(str(db))

    assert db.exists(), "main DB file MUST exist after secure init"
    mode = stat.S_IMODE(db.stat().st_mode)
    assert (
        mode == 0o600
    ), f"main DB mode is 0o{mode:o}, expected 0o600 — TOCTOU window is open"


@pytest.mark.regression
def test_secure_init_creates_wal_shm_sidecars_with_0o600(tmp_path: Path) -> None:
    """WAL + SHM sidecars are created and chmod'd to 0o600 before APScheduler
    opens the file. Closes the world-readable-job-data leak on multi-user hosts.
    """
    from kailash.runtime.scheduler import _secure_init_sqlite_jobstore

    db = tmp_path / "schedules.db"
    _secure_init_sqlite_jobstore(str(db))

    # WAL pre-init forces -wal + -shm into existence; both MUST be 0o600.
    wal = Path(f"{db}-wal")
    shm = Path(f"{db}-shm")
    assert wal.exists(), "WAL sidecar MUST exist after WAL pre-init"
    assert shm.exists(), "SHM sidecar MUST exist after WAL pre-init"

    wal_mode = stat.S_IMODE(wal.stat().st_mode)
    shm_mode = stat.S_IMODE(shm.stat().st_mode)
    assert wal_mode == 0o600, (
        f"WAL sidecar mode is 0o{wal_mode:o}, expected 0o600 — job-data bytes "
        f"are world-readable on multi-user hosts"
    )
    assert shm_mode == 0o600, (
        f"SHM sidecar mode is 0o{shm_mode:o}, expected 0o600 — job-data bytes "
        f"are world-readable on multi-user hosts"
    )


@pytest.mark.regression
def test_secure_init_refuses_symlinked_path(tmp_path: Path) -> None:
    """``O_NOFOLLOW`` MUST refuse to follow a symlink at the job-store path.

    Verifies that a parent-directory-controlling attacker cannot swap the
    target file between create and chmod — the very TOCTOU surface the
    fix closes.
    """
    from kailash.runtime.scheduler import _secure_init_sqlite_jobstore

    real_target = tmp_path / "real_target.db"
    real_target.write_bytes(b"")  # exists so the symlink isn't dangling

    symlink = tmp_path / "schedules.db"
    symlink.symlink_to(real_target)

    with pytest.raises(OSError) as exc_info:
        _secure_init_sqlite_jobstore(str(symlink))

    # ``O_NOFOLLOW`` raises ELOOP on Linux/macOS when the target is a symlink.
    # Some platforms return ENOTDIR or EMLINK; accept any of the symlink-refusal
    # errnos. Test FAILS if the call succeeded — that would mean the symlink
    # was followed, defeating the security guarantee.
    assert exc_info.value.errno in (errno.ELOOP, errno.EMLINK, errno.ENOTDIR), (
        f"Expected symlink-refusal errno, got {exc_info.value.errno} "
        f"({errno.errorcode.get(exc_info.value.errno, 'unknown')})"
    )


@pytest.mark.regression
def test_secure_init_tightens_existing_loose_permissions(tmp_path: Path) -> None:
    """If the job-store file pre-exists at a looser mode (e.g. 0o644 from a
    pre-fix deployment), secure init MUST tighten it to 0o600.

    Validates the ``os.fchmod`` call inside the helper — without it, upgrading
    from a pre-fix kailash version leaves existing job-store files at their
    insecure default.
    """
    from kailash.runtime.scheduler import _secure_init_sqlite_jobstore

    db = tmp_path / "schedules.db"
    db.write_bytes(b"")
    os.chmod(db, 0o644)  # simulate pre-fix loose permissions

    _secure_init_sqlite_jobstore(str(db))

    mode = stat.S_IMODE(db.stat().st_mode)
    assert mode == 0o600, (
        f"existing file mode is 0o{mode:o}, expected 0o600 — fchmod tightening "
        f"failed; users upgrading from a pre-fix release still leak job data"
    )


# ---------------------------------------------------------------------------
# Tier 2 — full WorkflowScheduler lifecycle: instantiate, fire one job,
# verify all three files (main DB + WAL + SHM) are 0o600.
# Requires APScheduler + asyncio loop.
# ---------------------------------------------------------------------------


apscheduler = pytest.importorskip(
    "apscheduler",
    reason="WorkflowScheduler regression requires APScheduler",
)


@pytest.mark.regression
def test_workflow_scheduler_jobstore_files_have_0o600_after_init(
    tmp_path: Path,
) -> None:
    """End-to-end through the public ``WorkflowScheduler`` constructor:
    verify all three job-store files (main DB, WAL, SHM) ship at mode 0o600
    BEFORE any job is added.

    This is the canonical user-flow regression — a deployment scheduling
    real workflows on a multi-user host MUST NOT leak job-data bytes via
    world-readable WAL/SHM sidecars. The pre-init runs at ``__init__``
    time, so any file APScheduler subsequently writes inherits 0o600 from
    the file already present on disk.
    """
    from kailash.runtime.scheduler import WorkflowScheduler

    db_path = tmp_path / "schedules.db"

    scheduler = WorkflowScheduler(job_store_path=str(db_path))
    try:
        assert db_path.exists(), "main DB MUST exist after __init__"
        main_mode = stat.S_IMODE(db_path.stat().st_mode)
        assert main_mode == 0o600, f"main DB mode is 0o{main_mode:o}, expected 0o600"

        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            assert sidecar.exists(), (
                f"{sidecar.name} MUST be pre-created by secure init so its "
                f"permissions are tightened BEFORE APScheduler writes job data"
            )
            mode = stat.S_IMODE(sidecar.stat().st_mode)
            assert mode == 0o600, (
                f"{sidecar.name} mode is 0o{mode:o}, expected 0o600 — "
                f"job-data bytes would be world-readable on multi-user hosts"
            )
    finally:
        scheduler.shutdown(wait=False)


@pytest.mark.regression
def test_workflow_scheduler_refuses_symlinked_jobstore_path(tmp_path: Path) -> None:
    """``WorkflowScheduler.__init__`` MUST refuse to construct when the
    job-store path is a symlink — propagating the OSError from O_NOFOLLOW.

    Lifts the unit-level symlink test (``test_secure_init_refuses_symlinked_path``)
    to the public API surface a user actually constructs.
    """
    from kailash.runtime.scheduler import WorkflowScheduler

    real_target = tmp_path / "real_target.db"
    real_target.write_bytes(b"")

    symlink = tmp_path / "schedules.db"
    symlink.symlink_to(real_target)

    with pytest.raises(OSError) as exc_info:
        WorkflowScheduler(job_store_path=str(symlink))

    assert exc_info.value.errno in (errno.ELOOP, errno.EMLINK, errno.ENOTDIR), (
        f"Expected symlink-refusal errno, got {exc_info.value.errno} "
        f"({errno.errorcode.get(exc_info.value.errno, 'unknown')})"
    )
