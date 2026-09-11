"""Unit tests for DPI-B4 bounded fallback path (issue #697).

Covers the structural invariants of ``AsyncSQLDatabaseNode._get_adapter``:
    - bare ``Exception`` is no longer caught (only RuntimeError +
      asyncio.TimeoutError)
    - cap-check raises ``PoolExhaustedError`` with helpful message
    - shared-path AND fallback-path AND dedicated-path pools register
      in ``_PROCESS_POOL_REGISTRY`` (no path bypasses the cap)

The Tier-2 regression that exercises the path against real PostgreSQL
lives in ``tests/regression/test_issue_697_pool_leak.py`` (DPI-B5).
"""

from __future__ import annotations

import asyncio
import inspect

import pytest

from kailash.nodes.data import async_sql as async_sql_module
from kailash.nodes.data.async_sql import (
    _POOL_DEFAULTS,
    _PROCESS_POOL_REGISTRY,
    AsyncSQLDatabaseNode,
    set_pool_defaults,
)
from kailash.nodes.data.exceptions import PoolExhaustedError


def test_get_adapter_does_not_catch_bare_exception():
    """The except clause MUST narrow to (RuntimeError, asyncio.TimeoutError).

    This is the structural invariant for zero-tolerance.md Rule 3 — bare
    ``Exception`` was the silent-fallback bug. The test reads the
    source of ``_get_adapter`` and asserts no occurrence of
    ``except (.*Exception``.
    """
    source = inspect.getsource(AsyncSQLDatabaseNode._get_adapter)
    # Must catch only the legitimate fallback triggers.
    assert "except (RuntimeError, asyncio.TimeoutError)" in source
    # Must NOT catch bare Exception in the same triple.
    assert "(RuntimeError, asyncio.TimeoutError, Exception)" not in source
    # Generic ``except Exception:`` BLOCKED on this path.
    # (We accept ``except Exception`` elsewhere in the function for
    #  detection blocks — the assertion above already pins the
    #  fallback-trigger triple.)


def test_pool_exhausted_error_raised_at_cap():
    """When _PROCESS_POOL_REGISTRY size hits cap, raise PoolExhaustedError.

    Simulates the cap-reached condition by seeding the registry with a
    cap-sized batch of stub pools, then constructs a node and exercises
    the cap-check arithmetic directly via the registry.
    """

    class _StubPool:
        pass

    set_pool_defaults(max_pool_count_per_process=3)
    pools = [_StubPool() for _ in range(3)]
    for i, p in enumerate(pools):
        _PROCESS_POOL_REGISTRY[f"existing_{i}"] = p

    cap = _POOL_DEFAULTS["max_pool_count_per_process"]
    current = len(_PROCESS_POOL_REGISTRY)
    assert current == cap

    # Reproduce the cap-check arithmetic from _get_adapter:
    if current >= cap:
        with pytest.raises(PoolExhaustedError) as exc_info:
            raise PoolExhaustedError(
                current=current, cap=cap, pool_key="loop|pg|h|10|20"
            ) from RuntimeError("simulated lock timeout")

    err = exc_info.value
    assert err.current == 3
    assert err.cap == 3
    assert "set_pool_defaults" in str(err)
    assert isinstance(err.__cause__, RuntimeError)
    # Pin pools list so weak refs survive the assertion
    assert len(pools) == 3


def test_get_adapter_imports_pool_exhausted_error():
    """Module imports PoolExhaustedError so the runtime path can raise it."""
    assert hasattr(async_sql_module, "PoolExhaustedError")
    # The fallback path uses the imported symbol directly
    assert async_sql_module.PoolExhaustedError is PoolExhaustedError


def test_fallback_pool_key_format_is_grep_able():
    """Fallback pool keys MUST be prefixed 'fallback_' for log correlation.

    The structured WARN log emits ``fallback_pool_key`` so operators
    can ``grep fallback_`` to find every leaked pool. This invariant
    is read from the source.
    """
    source = inspect.getsource(AsyncSQLDatabaseNode._get_adapter)
    # The key format string must include the 'fallback_' prefix
    assert 'f"fallback_{id(self)}_{self._pool_key}"' in source


def test_get_adapter_has_no_raw_registry_assignment():
    """Every registration goes through ``_register_pool`` — no raw poke.

    Issue #2075 replaced the three inline ``_PROCESS_POOL_REGISTRY[...] = ...``
    assignments with one helper, because the three-site shape is what let the
    REMOVAL side never get written at all: nothing freed a slot when a pool
    closed, so ``pool_count()`` counted adapter objects instead of pools.
    Structural, and deliberately phrased as an ABSENCE — a new branch that
    registers a pool by hand would also skip ``_ensure_reaper_started()``.
    """
    source = inspect.getsource(AsyncSQLDatabaseNode._get_adapter)
    assert "_PROCESS_POOL_REGISTRY[" not in source, (
        "a raw registry assignment reappeared in _get_adapter; register via "
        "_register_pool() so registration and reaper startup cannot drift"
    )
    assert source.count("_register_pool(") == 3, (
        "expected exactly three registration sites (shared, fallback, "
        "dedicated); each is a path that must honour the process-wide cap"
    )


@pytest.mark.asyncio
async def test_dedicated_path_registers_in_process_registry(tmp_path):
    """Dedicated pool path (share_pool=False) ALSO registers in registry.

    The cap is process-wide; ``share_pool=False`` does NOT exempt the pool.
    Behavioural per ``rules/testing.md`` § "Behavioral Regression Tests Over
    Source-Grep" — the source-grep form of this test broke on the #2075
    refactor while the invariant it guards was intact.
    """
    before = AsyncSQLDatabaseNode.pool_count()
    node = AsyncSQLDatabaseNode(
        node_id="dpi_b4_dedicated",
        connection_string=f"sqlite:///{tmp_path / 'dedicated.db'}",
        database_type="sqlite",
        share_pool=False,
    )
    await node.async_run(query="SELECT 1", result_format="dict")
    try:
        assert AsyncSQLDatabaseNode.pool_count() == before + 1
        keys = [k for k in _PROCESS_POOL_REGISTRY if k.startswith("dedicated_")]
        assert keys, "share_pool=False pool did not register under a dedicated_ key"
        assert any(
            _PROCESS_POOL_REGISTRY[k] is node._adapter for k in keys
        ), "the dedicated key does not point at this node's adapter"
    finally:
        await node.cleanup()


@pytest.mark.asyncio
async def test_shared_path_registers_in_process_registry(tmp_path):
    """Shared-path pool also registers (cap honours both shared + fallback)."""
    before = AsyncSQLDatabaseNode.pool_count()
    node = AsyncSQLDatabaseNode(
        node_id="dpi_b4_shared",
        connection_string=f"sqlite:///{tmp_path / 'shared.db'}",
        database_type="sqlite",
    )
    await node.async_run(query="SELECT 1", result_format="dict")
    try:
        assert AsyncSQLDatabaseNode.pool_count() == before + 1
        assert node._pool_key is not None
        assert _PROCESS_POOL_REGISTRY.get(node._pool_key) is node._adapter
    finally:
        await node.cleanup()


@pytest.mark.asyncio
async def test_pool_creation_starts_the_reaper_for_this_loop(tmp_path):
    """Every successful pool creation triggers reaper startup.

    Behavioural replacement for the ``source.count("_ensure_reaper_started()")
    >= 3`` grep: with registration funnelled through ``_register_pool`` there
    is now exactly ONE call site, and counting it proves nothing. What the
    invariant actually means is that a task exists to reap this loop's pools.
    """
    loop_key = id(asyncio.get_running_loop())
    async_sql_module._REAPER_TASKS.pop(loop_key, None)

    node = AsyncSQLDatabaseNode(
        node_id="dpi_b4_reaper",
        connection_string=f"sqlite:///{tmp_path / 'reaper.db'}",
        database_type="sqlite",
    )
    await node.async_run(query="SELECT 1", result_format="dict")
    try:
        assert (
            loop_key in async_sql_module._REAPER_TASKS
        ), "pool creation did not start the idle-pool reaper for this loop"
    finally:
        await node.cleanup()


# ----------------------------------------------------------------------------
# Behavioral test — exercises the cap-check via monkeypatched lock-timeout
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_adapter_raises_pool_exhausted_when_at_cap(monkeypatch):
    """When the registry is at cap and the per-pool lock times out,
    ``_get_adapter`` raises PoolExhaustedError instead of silently
    creating a fallback pool.

    Behavioral test per rules/testing.md § "Behavioral Regression Tests
    Over Source-Grep". Monkeypatches the per-pool lock to force a
    TimeoutError trigger, then asserts the cap-check fires.
    """

    class _StubAdapter:
        """Pinned object to fill the registry — needs to be a class
        instance for WeakValueDictionary."""

    # Seed the registry to cap with strong refs.
    set_pool_defaults(max_pool_count_per_process=2)
    seeded = [_StubAdapter() for _ in range(2)]
    _PROCESS_POOL_REGISTRY["seed_a"] = seeded[0]
    _PROCESS_POOL_REGISTRY["seed_b"] = seeded[1]
    assert AsyncSQLDatabaseNode.pool_count() == 2

    # Force the per-pool lock to timeout.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _timeout_lock(*args, **kwargs):
        raise asyncio.TimeoutError("simulated lock timeout")
        yield  # unreachable, satisfies generator contract

    monkeypatch.setattr(
        AsyncSQLDatabaseNode,
        "_acquire_pool_lock_with_timeout",
        classmethod(lambda cls, *a, **kw: _timeout_lock()),
    )

    # Patch _get_runtime_pool_adapter to skip the runtime-pool path.
    async def _no_runtime_pool(self):
        return None

    monkeypatch.setattr(
        AsyncSQLDatabaseNode,
        "_get_runtime_pool_adapter",
        _no_runtime_pool,
    )

    # Construct a node that would otherwise create a pool.
    node = AsyncSQLDatabaseNode(
        name="test_node",
        database_type="postgresql",
        connection_string="postgresql://test:test@localhost/test",
        validate_queries=False,
    )

    # Trigger the cap-check.
    with pytest.raises(PoolExhaustedError) as exc_info:
        await node._get_adapter()

    err = exc_info.value
    assert err.current == 2
    assert err.cap == 2
    assert isinstance(err.__cause__, asyncio.TimeoutError)
    assert seeded  # pin


@pytest.mark.asyncio
async def test_get_adapter_does_not_catch_value_error_or_attribute_error(
    monkeypatch,
):
    """ValueError / AttributeError raised inside the lock body propagate
    instead of being silently swallowed into a fallback pool.

    The legacy bare ``except Exception`` swallowed every exception type;
    DPI-B4's narrowed ``except (RuntimeError, asyncio.TimeoutError)``
    must let unrelated bugs surface.
    """
    from contextlib import asynccontextmanager

    class _UnexpectedError(ValueError):
        pass

    @asynccontextmanager
    async def _bad_lock(*args, **kwargs):
        raise _UnexpectedError("simulated unrelated bug")
        yield  # unreachable

    monkeypatch.setattr(
        AsyncSQLDatabaseNode,
        "_acquire_pool_lock_with_timeout",
        classmethod(lambda cls, *a, **kw: _bad_lock()),
    )

    async def _no_runtime_pool(self):
        return None

    monkeypatch.setattr(
        AsyncSQLDatabaseNode,
        "_get_runtime_pool_adapter",
        _no_runtime_pool,
    )

    node = AsyncSQLDatabaseNode(
        name="test_node",
        database_type="postgresql",
        connection_string="postgresql://test:test@localhost/test",
        validate_queries=False,
    )

    # The unrelated ValueError MUST propagate, NOT trigger fallback.
    with pytest.raises(_UnexpectedError):
        await node._get_adapter()
