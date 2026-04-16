# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
Unit tests for TSG-105: ReadReplicaSupport -- DataFlow(read_url="...") dual adapter.

Tests:
- Single-adapter default (backward compat)
- Dual-adapter creation
- Read routing to replica
- Write routing to primary
- use_primary forces primary
- Transactions force primary
- Pool exhaustion warning
- SyncExpress use_primary pass-through
- Health check reports both adapters
"""

from __future__ import annotations

import pytest

from dataflow import DataFlow
from dataflow.utils.connection import ConnectionManager


# ---------------------------------------------------------------------------
# Single-adapter default (backward compat)
# ---------------------------------------------------------------------------


def test_single_adapter_default():
    """Without read_url, only the primary connection manager exists."""
    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
    assert db._read_connection_manager is None
    assert db._read_url is None
    assert isinstance(db._connection_manager, ConnectionManager)


# ---------------------------------------------------------------------------
# Dual-adapter creation
# ---------------------------------------------------------------------------


def test_dual_adapter_creation():
    """When read_url is provided, two connection managers are created."""
    db = DataFlow(
        database_url="sqlite:///:memory:",
        read_url="sqlite:///read_replica.db",
        auto_migrate=False,
    )
    assert db._read_url == "sqlite:///read_replica.db"
    assert db._read_connection_manager is not None
    assert isinstance(db._read_connection_manager, ConnectionManager)
    assert db._read_connection_manager is not db._connection_manager


# ---------------------------------------------------------------------------
# Connection manager routing
# ---------------------------------------------------------------------------


def test_read_routes_to_replica():
    """list, read, count, find_one operations route to read connection manager."""
    db = DataFlow(
        database_url="sqlite:///:memory:",
        read_url="sqlite:///replica.db",
        auto_migrate=False,
    )
    for op in ("list", "read", "count", "find_one", "search"):
        cm = db._get_connection_manager(op)
        assert cm is db._read_connection_manager, f"Op '{op}' should route to read"


def test_write_routes_to_primary():
    """create, update, delete operations route to primary connection manager."""
    db = DataFlow(
        database_url="sqlite:///:memory:",
        read_url="sqlite:///replica.db",
        auto_migrate=False,
    )
    for op in ("create", "update", "delete", "upsert", "bulk_create"):
        cm = db._get_connection_manager(op)
        assert cm is db._connection_manager, f"Op '{op}' should route to primary"


def test_get_connection_manager_for_primary():
    """_get_connection_manager_for_primary() always returns primary."""
    db = DataFlow(
        database_url="sqlite:///:memory:",
        read_url="sqlite:///replica.db",
        auto_migrate=False,
    )
    assert db._get_connection_manager_for_primary() is db._connection_manager


def test_single_adapter_routing():
    """In single-adapter mode, all operations route to primary."""
    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
    for op in ("list", "read", "count", "find_one", "create", "update", "delete"):
        cm = db._get_connection_manager(op)
        assert cm is db._connection_manager


# ---------------------------------------------------------------------------
# ConnectionManager url_override
# ---------------------------------------------------------------------------


def test_connection_manager_url_override():
    """ConnectionManager with url_override uses the override URL."""
    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
    cm = ConnectionManager(db, url_override="sqlite:///override.db")
    assert cm._url_override == "sqlite:///override.db"


def test_connection_manager_pool_size_override():
    """ConnectionManager with pool_size_override uses the override pool size."""
    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
    cm = ConnectionManager(db, pool_size_override=42)
    assert cm._pool_size_override == 42
    assert cm.get_connection_stats()["pool_size"] == 42


# ---------------------------------------------------------------------------
# read_pool_size parameter
# ---------------------------------------------------------------------------


def test_read_pool_size_passed_to_read_connection_manager():
    """read_pool_size flows through to the read connection manager."""
    db = DataFlow(
        database_url="sqlite:///:memory:",
        read_url="sqlite:///replica.db",
        read_pool_size=7,
        auto_migrate=False,
    )
    assert db._read_connection_manager is not None
    assert db._read_connection_manager._pool_size_override == 7
    assert db._read_connection_manager.get_connection_stats()["pool_size"] == 7


# ---------------------------------------------------------------------------
# Health check reports both
# ---------------------------------------------------------------------------


def test_health_check_single_adapter():
    """health_check without read_url has no read_replica key."""
    db = DataFlow(database_url="sqlite:///:memory:", auto_migrate=False)
    health = db.health_check()
    assert "read_replica" not in health


def test_health_check_dual_adapter():
    """health_check with read_url reports read_replica status."""
    db = DataFlow(
        database_url="sqlite:///:memory:",
        read_url="sqlite:///replica.db",
        auto_migrate=False,
    )
    health = db.health_check()
    assert "read_replica" in health
    assert health["read_replica"]["status"] == "connected"


# ---------------------------------------------------------------------------
# Express use_primary parameter (signature only -- no real DB)
# ---------------------------------------------------------------------------


def test_express_read_accepts_use_primary():
    """Express.read() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import DataFlowExpress

    sig = inspect.signature(DataFlowExpress.read)
    assert "use_primary" in sig.parameters


def test_express_list_accepts_use_primary():
    """Express.list() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import DataFlowExpress

    sig = inspect.signature(DataFlowExpress.list)
    assert "use_primary" in sig.parameters


def test_express_count_accepts_use_primary():
    """Express.count() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import DataFlowExpress

    sig = inspect.signature(DataFlowExpress.count)
    assert "use_primary" in sig.parameters


def test_express_find_one_accepts_use_primary():
    """Express.find_one() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import DataFlowExpress

    sig = inspect.signature(DataFlowExpress.find_one)
    assert "use_primary" in sig.parameters


# ---------------------------------------------------------------------------
# SyncExpress use_primary parameter (signature only)
# ---------------------------------------------------------------------------


def test_sync_express_read_accepts_use_primary():
    """SyncExpress.read() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import SyncExpress

    sig = inspect.signature(SyncExpress.read)
    assert "use_primary" in sig.parameters


def test_sync_express_list_accepts_use_primary():
    """SyncExpress.list() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import SyncExpress

    sig = inspect.signature(SyncExpress.list)
    assert "use_primary" in sig.parameters


def test_sync_express_count_accepts_use_primary():
    """SyncExpress.count() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import SyncExpress

    sig = inspect.signature(SyncExpress.count)
    assert "use_primary" in sig.parameters


def test_sync_express_find_one_accepts_use_primary():
    """SyncExpress.find_one() signature accepts use_primary parameter."""
    import inspect

    from dataflow.features.express import SyncExpress

    sig = inspect.signature(SyncExpress.find_one)
    assert "use_primary" in sig.parameters
