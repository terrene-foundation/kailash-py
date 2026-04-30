# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression: ``DataFlow.runtime`` is lazily resolved per access (issue #713).

Pre-fix, ``DataFlow.__init__`` called ``asyncio.get_running_loop()`` once and
bound either ``LocalRuntime`` or ``AsyncLocalRuntime`` for the lifetime of the
instance. The natural FastAPI deployment pattern — constructing
``db = DataFlow(POSTGRES_URL)`` at module scope — bound ``LocalRuntime``
permanently. Any later ``await db.create_tables_async()`` call inside
uvicorn's running event loop hit::

    AttributeError: 'LocalRuntime' object has no attribute
                    'execute_workflow_async'

Post-fix (S4), ``self.runtime`` is a ``@property`` that detects the async
context per access via ``asyncio.get_running_loop()``, caches an
``AsyncLocalRuntime`` per event-loop id, and falls back to a
``LocalRuntime`` singleton in sync contexts. The test exercises FOUR
construction modes:

1. ``DataFlow(POSTGRES_URL)`` at module scope (sync), then
   ``await db.create_tables_async()`` inside ``asyncio.run(...)``.
2. ``DataFlow(POSTGRES_URL, runtime=AsyncLocalRuntime())`` — explicit
   kwarg escape hatch.
3. Post-init ``db.runtime = AsyncLocalRuntime()`` setter override.
4. ``db.runtime = None`` clears the override and resumes lazy detection.

Plus a Tier-1 sub-test verifying ``pickle`` / ``deepcopy`` round-trip.

Tracking: GitHub issue #713 (kailash-py).
"""

from __future__ import annotations

import asyncio
import copy
import inspect
import os
import pickle
import threading

import pytest
from kailash.runtime import AsyncLocalRuntime, LocalRuntime

from dataflow import DataFlow

# ---------------------------------------------------------------------------
# Postgres test container at port 5434 (per
# packages/kailash-dataflow/tests/CLAUDE.md "Standard SDK Docker
# Infrastructure"). Each test creates a uniquely-named model so the schema
# is fresh and parallel runs do not collide.
# ---------------------------------------------------------------------------

_POSTGRES_HOST = os.getenv("DB_HOST", "localhost")
_POSTGRES_PORT = os.getenv("DB_PORT", "5434")
_POSTGRES_USER = os.getenv("DB_USER", "test_user")
_POSTGRES_PASSWORD = os.getenv("DB_PASSWORD", "test_password")
_POSTGRES_DB = os.getenv("DB_NAME", "kailash_test")

POSTGRES_URL = os.getenv(
    "TEST_DATABASE_URL",
    f"postgresql://{_POSTGRES_USER}:{_POSTGRES_PASSWORD}"
    f"@{_POSTGRES_HOST}:{_POSTGRES_PORT}/{_POSTGRES_DB}",
)


# ---------------------------------------------------------------------------
# Tier-3 regression: module-import construction + async DDL via PostgreSQL.
# Mirrors the downstream consumer deployment pattern: DataFlow constructed at module
# scope (uvicorn imports the FastAPI app first, runs the lifespan in the
# event loop second).
# ---------------------------------------------------------------------------


_MODULE_DB_LOCK = threading.Lock()


def _make_unique_model(db: DataFlow, suffix: str) -> type:
    """Register a unique model per test so schemas do not collide.

    Returns the model class so the caller can issue model-specific DDL.
    """
    model_name = f"Issue713Doc{suffix}"

    @db.model
    class _Doc:  # noqa: D401 — anonymous regression model
        title: str

    _Doc.__name__ = model_name
    _Doc.__qualname__ = model_name
    return _Doc


@pytest.mark.regression
@pytest.mark.integration
def test_module_import_then_async_ddl_succeeds() -> None:
    """Module-scope DataFlow + async DDL inside ``asyncio.run`` succeeds.

    Pre-fix: ``AttributeError: 'LocalRuntime' object has no attribute
    'execute_workflow_async'`` because ``runtime`` was bound to
    ``LocalRuntime`` at module-import construction.
    Post-fix: ``runtime`` is a ``@property`` that detects the running
    event loop per access and returns ``AsyncLocalRuntime`` keyed by
    ``id(loop)``.
    """
    with _MODULE_DB_LOCK:
        # Construction in SYNC context (no running event loop).
        db = DataFlow(POSTGRES_URL, auto_migrate=False)
        # Sanity: in this sync context the runtime resolves to LocalRuntime.
        assert isinstance(
            db.runtime, LocalRuntime
        ), f"sync construction expected LocalRuntime, got {type(db.runtime)}"
        assert db._is_async is False

        _make_unique_model(db, "ModuleImport")

        async def run_async_ddl() -> None:
            # Inside the running loop the SAME ``db`` instance MUST resolve
            # ``runtime`` to ``AsyncLocalRuntime`` per access.
            assert isinstance(
                db.runtime, AsyncLocalRuntime
            ), f"async ctx expected AsyncLocalRuntime, got {type(db.runtime)}"
            assert db._is_async is True

            # The actual #713 repro: the call below raised AttributeError
            # pre-fix because runtime was the SYNC-bound LocalRuntime even
            # inside this loop.
            await db.create_tables_async()

        try:
            asyncio.run(run_async_ddl())
        finally:
            # Lazy cleanup — close() is safe even if connection was never
            # actually opened.
            try:
                db.close()
            except Exception:
                pass


@pytest.mark.regression
@pytest.mark.integration
def test_explicit_runtime_kwarg_succeeds() -> None:
    """``DataFlow(..., runtime=AsyncLocalRuntime())`` is an explicit override.

    Verifies the new ``runtime=`` kwarg in ``__init__`` is honored and
    survives through to async-DDL execution. The override is fixed for
    the instance lifetime — even outside an event loop ``runtime``
    returns ``AsyncLocalRuntime``.
    """
    with _MODULE_DB_LOCK:
        async_runtime = AsyncLocalRuntime()
        db = DataFlow(POSTGRES_URL, auto_migrate=False, runtime=async_runtime)

        # Override is active even in sync context.
        assert db.runtime is async_runtime
        assert db._is_async is True

        _make_unique_model(db, "RuntimeKwarg")

        async def run_async_ddl() -> None:
            # Override remains active inside the loop (override > lazy).
            assert db.runtime is async_runtime
            await db.create_tables_async()

        try:
            asyncio.run(run_async_ddl())
        finally:
            try:
                db.close()
            except Exception:
                pass


@pytest.mark.regression
@pytest.mark.integration
def test_post_init_setter_override_succeeds() -> None:
    """``db.runtime = AsyncLocalRuntime()`` setter override is honored.

    Mirrors the downstream consumer's workaround pattern. Verifies the setter is
    reachable via direct ``db.runtime = X`` assignment AND that the
    override is returned by every subsequent ``self.runtime`` access.
    """
    with _MODULE_DB_LOCK:
        db = DataFlow(POSTGRES_URL, auto_migrate=False)
        async_runtime = AsyncLocalRuntime()
        db.runtime = async_runtime  # setter

        assert db.runtime is async_runtime
        assert db._is_async is True

        _make_unique_model(db, "SetterOverride")

        async def run_async_ddl() -> None:
            assert db.runtime is async_runtime
            await db.create_tables_async()

        try:
            asyncio.run(run_async_ddl())
        finally:
            try:
                db.close()
            except Exception:
                pass


@pytest.mark.regression
@pytest.mark.integration
def test_clear_override_resumes_lazy_detection() -> None:
    """``db.runtime = None`` clears the override and resumes lazy detection.

    Sets an override, clears it via ``= None``, and verifies the next
    ``self.runtime`` access falls back to the lazy per-event-loop
    resolution.
    """
    with _MODULE_DB_LOCK:
        db = DataFlow(POSTGRES_URL, auto_migrate=False)
        # Set, then clear.
        db.runtime = LocalRuntime()
        db.runtime = None  # clear override
        assert db._runtime_override is None  # internal state matches contract

        # Sync context: lazy returns LocalRuntime singleton.
        runtime_sync = db.runtime
        assert isinstance(runtime_sync, LocalRuntime)
        assert db._is_async is False

        _make_unique_model(db, "ClearOverride")

        async def run_async_ddl() -> None:
            # Async context: lazy now returns AsyncLocalRuntime
            # (different instance from the sync one above).
            assert isinstance(db.runtime, AsyncLocalRuntime)
            assert db._is_async is True
            await db.create_tables_async()

        try:
            asyncio.run(run_async_ddl())
        finally:
            try:
                db.close()
            except Exception:
                pass


@pytest.mark.regression
@pytest.mark.integration
def test_descriptor_protocol_via_setattr() -> None:
    """``setattr(db, "runtime", X)`` reaches the property setter.

    Equivalent to ``monkeypatch.setattr(db, "runtime", X)``. Verifies
    the descriptor protocol is honored — i.e. ``runtime`` is a real
    ``@property`` on the class, not a plain instance attribute.
    """
    with _MODULE_DB_LOCK:
        db = DataFlow(POSTGRES_URL, auto_migrate=False)
        async_runtime = AsyncLocalRuntime()

        # ``setattr`` on an instance with a class-level property routes
        # through the descriptor's ``__set__``. This is the path used
        # by ``monkeypatch.setattr``.
        setattr(db, "runtime", async_runtime)
        assert db.runtime is async_runtime
        assert db._runtime_override is async_runtime

        # Confirm runtime is indeed a property on the class (descriptor).
        assert isinstance(
            inspect.getattr_static(type(db), "runtime"), property
        ), "DataFlow.runtime MUST be a property descriptor (not a plain attr)"


# ---------------------------------------------------------------------------
# Tier-1 sub-tests: pickle + deepcopy round-trip. Verifies that
# ``__getstate__`` / ``__setstate__`` strip per-loop caches + lock-holding
# subsystems so the unpickled instance is "re-initialization-ready" per
# specs/dataflow-core.md §1.4.
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_pickle_round_trip_strips_per_loop_state() -> None:
    """``pickle.loads(pickle.dumps(db))`` round-trips and resumes lazy.

    The unpickled instance has no override and no per-loop cache; the
    next ``self.runtime`` read repopulates lazily. This is the
    canonical post-#713 behaviour.
    """
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    pickled = pickle.dumps(db)
    db_restored = pickle.loads(pickled)
    # Override stripped on pickle.
    assert db_restored._runtime_override is None
    # Lazy resumes; sync context returns LocalRuntime singleton.
    assert isinstance(db_restored.runtime, LocalRuntime)


@pytest.mark.regression
def test_pickle_with_setter_override_strips_override() -> None:
    """Pickle of a DataFlow with active override strips the override.

    ``LocalRuntime`` and ``AsyncLocalRuntime`` themselves hold thread
    locks and are not picklable. Pre-pickle the override is stripped;
    the unpickled instance resumes lazy detection.
    """
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    db.runtime = LocalRuntime()  # explicit override
    db_restored = pickle.loads(pickle.dumps(db))
    assert db_restored._runtime_override is None  # stripped
    # Lazy resumes — sync context returns a fresh LocalRuntime singleton.
    assert isinstance(db_restored.runtime, LocalRuntime)


@pytest.mark.regression
def test_deepcopy_round_trip() -> None:
    """``copy.deepcopy(db)`` survives, symmetric with pickle."""
    db = DataFlow("sqlite:///:memory:", auto_migrate=False)
    db_copy = copy.deepcopy(db)
    assert isinstance(db_copy.runtime, LocalRuntime)
    assert db_copy._runtime_override is None
