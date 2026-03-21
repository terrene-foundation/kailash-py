# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Tests for lightweight health check pool (M10 / RS-6 alignment)."""

from __future__ import annotations

import pytest

from dataflow.core.pool_lightweight import LightweightPool


class TestLightweightPoolInit:
    """Test lightweight pool initialization."""

    def test_default_pool_size_is_2(self):
        pool = LightweightPool("sqlite:///:memory:")
        assert pool._pool_size == 2

    def test_not_initialized_by_default(self):
        pool = LightweightPool("sqlite:///:memory:")
        assert pool._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_sqlite(self):
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        assert pool._initialized is True
        await pool.close()

    @pytest.mark.asyncio
    async def test_double_initialize_is_safe(self):
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        await pool.initialize()  # Should not raise
        assert pool._initialized is True
        await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_sqlite(self):
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        result = await pool.execute_raw("SELECT 1")
        assert len(result) == 1
        assert result[0][0] == 1
        await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_before_init_raises(self):
        pool = LightweightPool("sqlite:///:memory:")
        with pytest.raises(RuntimeError, match="not initialized"):
            await pool.execute_raw("SELECT 1")

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self):
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        await pool.close()
        await pool.close()  # Should not raise
        assert pool._initialized is False

    @pytest.mark.asyncio
    async def test_close_without_init_is_safe(self):
        pool = LightweightPool("sqlite:///:memory:")
        await pool.close()  # Should not raise


class TestLightweightPoolAllowlist:
    """Test the allowlist enforcement for execute_raw (Gap 4)."""

    @pytest.mark.asyncio
    async def test_execute_raw_rejects_disallowed_query(self):
        """DROP TABLE is not in the allowlist and must be rejected with
        a ValueError."""
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        try:
            with pytest.raises(ValueError, match="not allowed on lightweight pool"):
                await pool.execute_raw("DROP TABLE users")
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_rejects_broad_show(self):
        """SHOW GRANTS is not in the narrowed allowlist and must be
        rejected.  Only SHOW MAX_CONNECTIONS and SHOW SERVER_VERSION
        are permitted."""
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        try:
            with pytest.raises(ValueError, match="not allowed on lightweight pool"):
                await pool.execute_raw("SHOW GRANTS")
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_rejects_insert(self):
        """INSERT statements must be rejected by the allowlist."""
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        try:
            with pytest.raises(ValueError, match="not allowed on lightweight pool"):
                await pool.execute_raw("INSERT INTO users VALUES (1, 'admin')")
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_rejects_update(self):
        """UPDATE statements must be rejected by the allowlist."""
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        try:
            with pytest.raises(ValueError, match="not allowed on lightweight pool"):
                await pool.execute_raw("UPDATE users SET admin=1")
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_rejects_delete(self):
        """DELETE statements must be rejected by the allowlist."""
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        try:
            with pytest.raises(ValueError, match="not allowed on lightweight pool"):
                await pool.execute_raw("DELETE FROM users")
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_allows_select_1(self):
        """SELECT 1 is explicitly allowlisted and should succeed."""
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        try:
            result = await pool.execute_raw("SELECT 1")
            assert len(result) == 1
            assert result[0][0] == 1
        finally:
            await pool.close()

    @pytest.mark.asyncio
    async def test_execute_raw_allowlist_is_case_insensitive(self):
        """The allowlist check should be case-insensitive."""
        pool = LightweightPool("sqlite:///:memory:")
        await pool.initialize()
        try:
            result = await pool.execute_raw("select 1")
            assert len(result) == 1
            assert result[0][0] == 1
        finally:
            await pool.close()
