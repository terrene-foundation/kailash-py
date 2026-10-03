# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""SQLite job-store mode, static-symlink refusal, and writer-mode regressions.

These behavioral checks inspect real POSIX modes and a pre-existing symlink.
They cover initial descriptor creation/tightening and live WAL/SHM modes after
bootstrap closure. They do not simulate concurrent path replacement or prove
a complete TOCTOU boundary; initialization assumes a trusted path lifetime.
"""

from __future__ import annotations

import asyncio
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
    assert mode == 0o600, f"main DB mode is 0o{mode:o}, expected 0o600"


@pytest.mark.regression
def test_secure_init_creates_wal_shm_sidecars_with_0o600(tmp_path: Path) -> None:
    """A subsequent real writer recreates private WAL and SHM sidecars."""
    from kailash.runtime.scheduler import _secure_init_sqlite_jobstore

    db = tmp_path / "schedules.db"
    _secure_init_sqlite_jobstore(str(db))

    # Closing the bootstrap connection can checkpoint and remove sidecars.
    # Verify the next real writer recreates them with the same private mode.
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(db)) as connection:
        connection.execute("INSERT INTO _kailash_secure_init VALUES (1)")
        connection.commit()
        wal = Path(f"{db}-wal")
        shm = Path(f"{db}-shm")
        assert wal.exists(), "Live WAL writer must have a sidecar"
        assert shm.exists(), "Live WAL writer must have shared memory"
        assert stat.S_IMODE(wal.stat().st_mode) == 0o600
        assert stat.S_IMODE(shm.stat().st_mode) == 0o600


@pytest.mark.regression
def test_secure_init_refuses_symlinked_path(tmp_path: Path) -> None:
    """``O_NOFOLLOW`` MUST refuse to follow a symlink at the job-store path.

    This tests an existing symlink, not a concurrent path replacement.
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
# Tier 2 — full WorkflowScheduler lifecycle: instantiate, start the job store,
# verify all three files (main DB + WAL + SHM) are 0o600.
# Requires APScheduler + asyncio loop.
# ---------------------------------------------------------------------------


apscheduler = pytest.importorskip(
    "apscheduler",
    reason="WorkflowScheduler regression requires APScheduler",
)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_workflow_scheduler_jobstore_files_have_0o600_after_start(
    tmp_path: Path,
) -> None:
    """The real scheduler writer inherits private modes after bootstrap closes.

    Starting APScheduler opens its SQLAlchemy job store and creates the job
    table. Its live WAL/SHM files must remain private before jobs are added.
    """
    from kailash.runtime.scheduler import WorkflowScheduler

    db_path = tmp_path / "schedules.db"

    scheduler = WorkflowScheduler(job_store_path=str(db_path))
    try:
        assert db_path.exists(), "main DB MUST exist after __init__"
        main_mode = stat.S_IMODE(db_path.stat().st_mode)
        assert main_mode == 0o600, f"main DB mode is 0o{main_mode:o}, expected 0o600"

        scheduler.start()
        for suffix in ("-wal", "-shm"):
            sidecar = Path(f"{db_path}{suffix}")
            assert (
                sidecar.exists()
            ), f"{sidecar.name} must exist for the live scheduler writer"
            mode = stat.S_IMODE(sidecar.stat().st_mode)
            assert mode == 0o600, (
                f"{sidecar.name} mode is 0o{mode:o}, expected 0o600 — "
                f"job-data bytes would be world-readable on multi-user hosts"
            )
    finally:
        scheduler.shutdown(wait=False)
        await asyncio.sleep(0)


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
