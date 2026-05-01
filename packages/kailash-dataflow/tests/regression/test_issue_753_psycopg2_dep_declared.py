"""Regression test for issue #753 — psycopg2 must be a declared dependency.

`kailash-dataflow ≥2.4.0` imports `psycopg2` via the synchronous DDL /
migration path (`SyncDDLExecutor._get_postgresql_connection`,
`MigrationConnectionManager._connect_with_retry`,
`dataflow.core.pool_utils._is_postgresql_url`) when bootstrapping
registry tables and running ``auto_migrate=True`` against PostgreSQL.

Pre-fix: package declared `asyncpg` (covering runtime DML) but not
`psycopg2-binary`. Every fresh install pointed at a PostgreSQL
``DATABASE_URL`` failed at the first ``auto_migrate`` trigger with
``ModuleNotFoundError: No module named 'psycopg2'``, then crashed
downstream DML with ``relation "<table>" does not exist`` because the
registry/schema bootstrap silently failed.

Post-fix: `psycopg2-binary>=2.9` is declared as a baseline dependency
(matching the existing `asyncpg`, `aiosqlite`, `aiomysql` baseline
treatment). This regression locks the declaration AND verifies the
import chain so a future "dep cleanup" cannot silently re-open the
failure mode.

Per ``rules/cross-sdk-inspection.md`` MUST Rule 3a, this is a structural
declaration / import-chain test — there is no Tier 2 connection-binding
sibling because the bug is upstream of the connect call (the import
itself failed).
"""

from __future__ import annotations

from pathlib import Path


def test_pyproject_declares_psycopg2_binary() -> None:
    """`pyproject.toml::dependencies` MUST list `psycopg2-binary`.

    Catches future "dep cleanup" PRs that remove the declaration without
    test signal — without this guard, the failure surfaces only on a
    fresh-venv install against PostgreSQL.
    """
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject.read_text()

    # Find the [project] dependencies block (not [project.optional-dependencies])
    in_deps_block = False
    declared = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps_block = True
            continue
        if in_deps_block:
            if stripped == "]":
                break
            if "psycopg2-binary" in stripped or "psycopg2_binary" in stripped:
                declared = True
                break

    assert declared, (
        "psycopg2-binary missing from kailash-dataflow baseline dependencies. "
        "The synchronous DDL / migration path imports psycopg2; without the "
        "declaration, fresh-venv installs fail at auto_migrate=True against "
        "PostgreSQL with ModuleNotFoundError. See issue #753."
    )


def test_psycopg2_resolves_at_module_scope() -> None:
    """`import psycopg2` MUST succeed from the dataflow package context.

    Tightens the structural defense beyond the pyproject.toml declaration —
    proves the package the manifest resolves to is actually importable
    (catches a manifest entry that points at a non-existent / yanked
    distribution).
    """
    import psycopg2  # noqa: F401  — resolution is the test

    # Defense-in-depth: the version attribute exists, confirming we have a
    # real psycopg2 install (not a stub / shim).
    assert hasattr(psycopg2, "__version__")


def test_sync_ddl_executor_postgres_path_does_not_raise_importerror() -> None:
    """``SyncDDLExecutor._get_postgresql_connection`` MUST resolve psycopg2.

    The pre-fix failure mode was:
        ImportError: psycopg2 is required for PostgreSQL migrations.
                     Install with: pip install psycopg2-binary

    Raised at the ``import psycopg2`` line (sync_ddl_executor.py:102).
    This test invokes the method against an unreachable host so the
    psycopg2 *import* runs but the subsequent ``psycopg2.connect`` call
    fails with a connection-level exception (NOT ImportError).

    Asserts the FAILURE TYPE — ImportError means the dep declaration
    regressed; any other exception (OperationalError, ConnectionError,
    socket.gaierror, etc.) means the import succeeded and the test passed.
    """
    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    # Use an obviously-unreachable port so the connect attempt fails fast
    # and we never need a real Postgres instance to run this test.
    executor = SyncDDLExecutor(database_url="postgresql://x:x@127.0.0.1:1/x")

    try:
        executor._get_postgresql_connection()
    except ImportError as e:
        raise AssertionError(
            f"psycopg2 import regressed in sync DDL path: {e!r}. "
            f"Issue #753: psycopg2-binary MUST stay declared in "
            f"kailash-dataflow/pyproject.toml::dependencies."
        ) from e
    except Exception:
        # Connection-level exception is the success signal — the import
        # succeeded and we hit the network layer (or psycopg2's own error
        # taxonomy), which is exactly what we want to prove.
        pass
    else:
        # Unreachable port should never produce a real connection. If it
        # did, the test setup is wrong.
        raise AssertionError(
            "Unreachable Postgres URL produced a live connection — "
            "test environment is misconfigured."
        )
