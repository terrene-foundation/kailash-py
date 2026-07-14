#!/usr/bin/env python3
"""Regression: error-path log/exception hygiene on the #1737 sibling asyncpg
pools (``LightweightPool`` + ``PostgreSQLEventStore``).

Offline boundary-injection tests (user-flow-validation.md MUST-7 class (b) —
exception mid-operation): ``asyncpg.create_pool`` is monkeypatched to RAISE so
the pool-creation failure path runs with NO real database. They pin two
security fixes surfaced by the #1737 /redteam:

  * HIGH — ``LightweightPool.initialize()`` MUST NOT log the pool-creation
    exception with ``exc_info=True``. A credential-provider error routed here
    carries token material in its message / ``__cause__`` chain; ``exc_info``
    would render that chain into DEBUG logs (security.md "No secrets in logs").
    Only the exception TYPE name is logged.

  * Important #2 — ``PostgreSQLEventStore.initialize()`` MUST wrap a
    ``create_pool`` failure in a ``ConnectionError`` routed through the shared
    ``sanitize_db_error()`` (mirroring ``adapters/postgresql.py``), never let
    the raw asyncpg exception (which can embed the credentialed DSN) propagate.

No mocking of the units under test — only the external ``asyncpg.create_pool``
boundary is injected. asyncpg must be importable (postgres extra).
"""

from __future__ import annotations

import logging

import pytest

asyncpg = pytest.importorskip("asyncpg")

from dataflow.core.event_stores.postgresql import PostgreSQLEventStore
from dataflow.core.pool_lightweight import LightweightPool

# A recognizable secret embedded in the injected exception message, used to
# prove the value-bearing DETAIL clause is redacted before it reaches the log
# line / raised error.
_SECRET = "s3cr3t-token-DO-NOT-LEAK"
_PG_URL = f"postgresql://appuser:{_SECRET}@db.internal:5432/appdb"


@pytest.mark.regression
class TestLightweightPoolInitErrorHygiene:
    @pytest.mark.asyncio
    async def test_create_pool_failure_logs_no_exc_info(self, monkeypatch, caplog):
        """HIGH: the pool-creation except path logs the TYPE name only and
        emits NO record carrying ``exc_info`` (the removed token-leak vector)."""

        async def _boom(*args, **kwargs):
            # A DETAIL-bearing message stands in for an asyncpg/provider error
            # whose __cause__ chain could carry credential material.
            raise RuntimeError(f"connect failed\nDETAIL: Key (password)=({_SECRET})")

        monkeypatch.setattr(asyncpg, "create_pool", _boom)

        pool = LightweightPool(_PG_URL, pool_size=2)
        with caplog.at_level(logging.DEBUG):
            # initialize() is best-effort: it catches, WARNs, and continues.
            await pool.initialize()

        assert not pool.is_initialized

        # The removed leak: NO log record may carry an exception traceback.
        offenders = [r for r in caplog.records if r.exc_info is not None]
        assert offenders == [], (
            "exc_info leaked on the lightweight-pool create_pool failure path: "
            f"{[r.getMessage() for r in offenders]}"
        )

        # A WARN was emitted, and it names only the exception TYPE — the raw
        # message (and the embedded secret) never reach the log line.
        warns = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert warns, "expected a WARN on pool-creation failure"
        combined = " ".join(r.getMessage() for r in caplog.records)
        assert _SECRET not in combined
        assert "RuntimeError" in " ".join(r.getMessage() for r in warns)


@pytest.mark.regression
class TestEventStoreInitErrorHygiene:
    @pytest.mark.asyncio
    async def test_create_pool_failure_wraps_and_sanitizes(self, monkeypatch, caplog):
        """Important #2: a create_pool failure surfaces as a sanitized
        ``ConnectionError`` (raw asyncpg exception NOT propagated), and the
        value-bearing DETAIL clause is redacted before the message is used."""

        async def _boom(*args, **kwargs):
            raise RuntimeError(f"connect failed\nDETAIL: Key (password)=({_SECRET})")

        monkeypatch.setattr(asyncpg, "create_pool", _boom)

        store = PostgreSQLEventStore(
            database_url=_PG_URL, pool_min_size=1, pool_max_size=1
        )
        with caplog.at_level(logging.ERROR):
            with pytest.raises(ConnectionError) as excinfo:
                await store.initialize()

        # Structural contract: the raw RuntimeError is wrapped, not propagated,
        # by the sanitize barrier (mirrors adapters/postgresql.py).
        msg = str(excinfo.value)
        assert msg.startswith("PostgreSQL event store connection failed:")
        # sanitize_db_error actually ran: the DETAIL value is redacted, so the
        # embedded secret reaches neither the raised error nor the ERROR log.
        assert _SECRET not in msg
        assert "[REDACTED]" in msg
        combined = " ".join(r.getMessage() for r in caplog.records)
        assert _SECRET not in combined
