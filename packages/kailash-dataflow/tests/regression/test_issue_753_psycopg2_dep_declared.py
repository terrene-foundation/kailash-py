"""Regression test for issue #753 — psycopg2 declared in the `postgres-sync` extra.

`kailash-dataflow` imports `psycopg2` only on the SYNCHRONOUS PostgreSQL DDL /
migration path (`SyncDDLExecutor._get_postgresql_connection`, reached from the
sync `DataFlow.create_tables()` / sync-context auto-migrate). The async-first
default path — `create_tables_async()` / `await db.auto_migrate()` / all runtime
DML — uses **asyncpg** (a baseline dependency), never psycopg2.

Architecture note (post-#890 dependency-slimming audit): DataFlow is async-first.
`psycopg2-binary` is therefore an **opt-in** dependency declared in the
`postgres-sync` optional-dependencies extra, NOT a baseline dependency — an
async-first user on asyncpg never needs it. The sync DDL path is a documented
opt-in (`create_tables()` is explicitly "use only outside an async context").

This regression locks the declaration so a future "dep cleanup" cannot silently
DROP `psycopg2-binary` from the `postgres-sync` extra entirely (which would break
the sync PostgreSQL DDL path with `ModuleNotFoundError`). It guards the EXTRA, not
baseline — asserting baseline was the pre-#890 expectation and is now stale.

Per ``rules/cross-sdk-inspection.md`` MUST Rule 3a, this is a structural
declaration / import-chain test — there is no Tier 2 connection-binding sibling
because the failure mode is upstream of the connect call (the import itself).
"""

from __future__ import annotations

from pathlib import Path


def test_pyproject_declares_psycopg2_binary_in_postgres_sync_extra() -> None:
    """`pyproject.toml` MUST list `psycopg2-binary` in the `postgres-sync` extra.

    DataFlow is async-first (asyncpg is baseline); psycopg2 is opt-in for the
    sync PostgreSQL DDL path. This guards the `postgres-sync` extra declaration
    so a future "dep cleanup" cannot drop psycopg2-binary entirely without test
    signal — the sync DDL path would then fail with ModuleNotFoundError on a
    fresh `pip install "kailash-dataflow[postgres-sync]"`.
    """
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject.read_text()

    # Find the `postgres-sync = [` extra block within
    # [project.optional-dependencies] and assert psycopg2-binary is declared.
    in_extra_block = False
    declared = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("postgres-sync = ["):
            in_extra_block = True
            continue
        if in_extra_block:
            if stripped == "]":
                break
            if "psycopg2-binary" in stripped or "psycopg2_binary" in stripped:
                declared = True
                break

    assert declared, (
        "psycopg2-binary missing from the kailash-dataflow `postgres-sync` extra. "
        "DataFlow is async-first (asyncpg is baseline); psycopg2 is opt-in for the "
        "sync PostgreSQL DDL path. Without the extra declaration, "
        '`pip install "kailash-dataflow[postgres-sync]"` fails to provide psycopg2 '
        "and the sync DDL path raises ModuleNotFoundError. See issue #753."
    )


def test_psycopg2_binary_not_in_baseline_dependencies() -> None:
    """`psycopg2-binary` MUST NOT be in baseline `[project].dependencies`.

    Async-first invariant (#890): the baseline install resolves asyncpg only;
    psycopg2 is opt-in via `postgres-sync`. This is the inverse guard of the
    extra-declaration test — it locks the async-first architecture so a future
    PR cannot silently re-promote psycopg2 to baseline (re-bloating every
    async-only install with a sync driver they never use).
    """
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    text = pyproject.read_text()

    in_deps_block = False
    in_baseline = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "dependencies = [":
            in_deps_block = True
            continue
        if in_deps_block:
            if stripped == "]":
                break
            if "psycopg2-binary" in stripped or "psycopg2_binary" in stripped:
                in_baseline = True
                break

    assert not in_baseline, (
        "psycopg2-binary found in baseline dependencies. DataFlow is async-first "
        "(asyncpg baseline); psycopg2 belongs in the `postgres-sync` opt-in extra "
        "per the #890 dependency-slimming audit. See issue #753 / #1228 disposition."
    )


def test_psycopg2_resolves_when_postgres_sync_installed() -> None:
    """`import psycopg2` resolves in an env with the `postgres-sync` extra.

    Tightens the structural defense beyond the pyproject declaration — proves the
    package the extra resolves to is actually importable (catches a manifest entry
    pointing at a non-existent / yanked distribution). Skips cleanly when the
    `postgres-sync` extra is not installed (async-first `[dev]`-only environments).
    """
    import importlib.util

    if importlib.util.find_spec("psycopg2") is None:
        import pytest

        pytest.skip("postgres-sync extra not installed (async-first baseline env)")

    import psycopg2  # noqa: F401  — resolution is the test

    assert hasattr(psycopg2, "__version__")


def test_sync_ddl_executor_postgres_path_does_not_raise_importerror() -> None:
    """``SyncDDLExecutor._get_postgresql_connection`` resolves psycopg2 when present.

    The sync DDL path requires the `postgres-sync` extra. With it installed, the
    method's ``import psycopg2`` (sync_ddl_executor.py) MUST succeed and any failure
    is connection-level (NOT ImportError). Skips when the extra is absent.

    Asserts the FAILURE TYPE — ImportError means psycopg2-binary regressed out of
    the `postgres-sync` extra; any other exception (OperationalError,
    ConnectionError, socket.gaierror) means the import succeeded.
    """
    import importlib.util

    if importlib.util.find_spec("psycopg2") is None:
        import pytest

        pytest.skip("postgres-sync extra not installed (async-first baseline env)")

    from dataflow.migrations.sync_ddl_executor import SyncDDLExecutor

    # Use an obviously-unreachable port so the connect attempt fails fast
    # and we never need a real Postgres instance to run this test.
    executor = SyncDDLExecutor(database_url="postgresql://x:x@127.0.0.1:1/x")

    try:
        executor._get_postgresql_connection()
    except ImportError as e:
        raise AssertionError(
            f"psycopg2 import regressed in sync DDL path: {e!r}. "
            f"Issue #753: psycopg2-binary MUST stay declared in the "
            f"kailash-dataflow `postgres-sync` optional-dependencies extra."
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
