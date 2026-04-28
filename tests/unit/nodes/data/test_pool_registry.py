"""Unit tests for the process-wide pool registry (DPI-B2 / issue #697 + #698).

Covers:
    - ``set_pool_defaults`` validation + override behavior
    - ``AsyncSQLDatabaseNode.pool_count()`` round-trip
    - ``AsyncSQLDatabaseNode.pool_keys()`` round-trip
    - Per-test cleanup fixture isolation (no leak across tests)

The Tier 2 regression that exercises the registry against real PG lives
in ``tests/regression/test_issue_697_pool_leak.py`` (DPI-B5).
"""

from __future__ import annotations

import pytest

from kailash.nodes.data.async_sql import (
    _POOL_DEFAULTS,
    _PROCESS_POOL_REGISTRY,
    AsyncSQLDatabaseNode,
    set_pool_defaults,
)


class _FakePool:
    """Stand-in object for an EnterpriseConnectionPool, used only to
    populate ``_PROCESS_POOL_REGISTRY`` (a WeakValueDictionary). MUST be
    a class instance — Python forbids weak references to bare ``object``
    instances of some built-in types.
    """

    def __init__(self, name: str) -> None:
        self.name = name


def test_set_pool_defaults_idle_timeout_override():
    """idle_timeout override mutates _POOL_DEFAULTS in place."""
    assert _POOL_DEFAULTS["idle_timeout"] == 300  # factory default
    set_pool_defaults(idle_timeout=42)
    assert _POOL_DEFAULTS["idle_timeout"] == 42


def test_set_pool_defaults_max_pool_count_override():
    """max_pool_count_per_process override mutates _POOL_DEFAULTS."""
    assert _POOL_DEFAULTS["max_pool_count_per_process"] == 100
    set_pool_defaults(max_pool_count_per_process=10)
    assert _POOL_DEFAULTS["max_pool_count_per_process"] == 10


def test_set_pool_defaults_partial_override_leaves_other_keys_unchanged():
    """Setting only one parameter does not clobber the other key."""
    set_pool_defaults(idle_timeout=15)
    assert _POOL_DEFAULTS["idle_timeout"] == 15
    assert _POOL_DEFAULTS["max_pool_count_per_process"] == 100  # factory


def test_set_pool_defaults_rejects_unknown_kwargs():
    """Unknown kwargs raise TypeError (no silent typos)."""
    with pytest.raises(TypeError):
        set_pool_defaults(foo=42)  # type: ignore[call-arg]


def test_set_pool_defaults_rejects_positional_args():
    """The signature is keyword-only — positional args raise TypeError."""
    with pytest.raises(TypeError):
        set_pool_defaults(300)  # type: ignore[misc]


@pytest.mark.parametrize("bad_idle", [0, -1, -100])
def test_set_pool_defaults_rejects_non_positive_idle_timeout(bad_idle):
    """idle_timeout must be a positive int."""
    with pytest.raises(ValueError, match="idle_timeout"):
        set_pool_defaults(idle_timeout=bad_idle)


def test_set_pool_defaults_rejects_non_int_idle_timeout():
    """idle_timeout must be int — strings rejected."""
    with pytest.raises(ValueError, match="idle_timeout"):
        set_pool_defaults(idle_timeout="300")  # type: ignore[arg-type]


@pytest.mark.parametrize("bad_cap", [0, -1, -100])
def test_set_pool_defaults_rejects_non_positive_max_pool_count(bad_cap):
    """max_pool_count_per_process must be a positive int."""
    with pytest.raises(ValueError, match="max_pool_count_per_process"):
        set_pool_defaults(max_pool_count_per_process=bad_cap)


def test_set_pool_defaults_none_leaves_value_unchanged():
    """Passing None for a parameter leaves the existing default in place."""
    set_pool_defaults(idle_timeout=42)
    set_pool_defaults(max_pool_count_per_process=10)
    set_pool_defaults(idle_timeout=None, max_pool_count_per_process=None)
    assert _POOL_DEFAULTS["idle_timeout"] == 42
    assert _POOL_DEFAULTS["max_pool_count_per_process"] == 10


def test_pool_count_zero_on_empty_registry():
    """Empty registry → pool_count() returns 0."""
    # The autouse reset_pool_registry fixture clears between tests.
    assert AsyncSQLDatabaseNode.pool_count() == 0


def test_pool_count_reflects_registry_size():
    """pool_count() reads len(_PROCESS_POOL_REGISTRY)."""
    pools = [_FakePool(f"k{i}") for i in range(3)]
    for pool in pools:
        _PROCESS_POOL_REGISTRY[pool.name] = pool
    assert AsyncSQLDatabaseNode.pool_count() == 3
    # Pinning the pools list to keep strong refs alive for the assertion
    assert len(pools) == 3


def test_pool_keys_returns_sorted_snapshot():
    """pool_keys() is sorted, deterministic for assertions."""
    pools = [_FakePool(f"key_{name}") for name in ("c", "a", "b")]
    for pool in pools:
        _PROCESS_POOL_REGISTRY[pool.name] = pool
    keys = AsyncSQLDatabaseNode.pool_keys()
    assert keys == ["key_a", "key_b", "key_c"]
    assert pools  # pin


def test_pool_count_drops_on_gc():
    """WeakValueDictionary semantics: dropping refs reaps entries."""
    import gc

    pool = _FakePool("ephemeral")
    _PROCESS_POOL_REGISTRY["ephemeral"] = pool
    assert AsyncSQLDatabaseNode.pool_count() == 1

    del pool
    gc.collect()
    # GC may be lazy on PyPy; CPython reaps immediately for this case.
    assert AsyncSQLDatabaseNode.pool_count() == 0


# ----------------------------------------------------------------------------
# Per-test cleanup verification — sequential test pair
# ----------------------------------------------------------------------------


def test_reset_fixture_clears_registry_seed():
    """Seed the registry; the autouse fixture clears it before next test."""
    pool = _FakePool("seed")
    _PROCESS_POOL_REGISTRY["seed"] = pool
    assert AsyncSQLDatabaseNode.pool_count() == 1
    assert pool  # pin


def test_reset_fixture_starts_with_empty_registry():
    """Sibling test of the previous; verifies the fixture cleared the seed."""
    assert AsyncSQLDatabaseNode.pool_count() == 0


def test_reset_fixture_restores_defaults_to_factory():
    """After a test mutates defaults, next test sees factory values."""
    # The previous test (or any prior test) may have called
    # set_pool_defaults(); the fixture resets between tests.
    assert _POOL_DEFAULTS["idle_timeout"] == 300
    assert _POOL_DEFAULTS["max_pool_count_per_process"] == 100
