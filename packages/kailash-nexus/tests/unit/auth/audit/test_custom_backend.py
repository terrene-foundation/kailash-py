"""Unit tests for CustomBackend (TODO-310F).

Tier 1 tests - mocking allowed.
"""

import pytest
from nexus.auth.audit.backends.custom import CustomBackend
from nexus.auth.audit.record import AuditRecord

# =============================================================================
# Tests: CustomBackend
# =============================================================================


class TestCustomBackend:
    """Test CustomBackend with user-provided callables."""

    @pytest.mark.asyncio
    async def test_sync_callable(self):
        """Sync callable is invoked."""
        stored = []

        def sync_store(record):
            stored.append(record)

        backend = CustomBackend(store_func=sync_store)

        record = AuditRecord.create(
            method="GET",
            path="/test",
            status_code=200,
            duration_ms=1.0,
            ip_address="127.0.0.1",
        )

        await backend.store(record)
        assert len(stored) == 1
        assert stored[0].path == "/test"

    @pytest.mark.asyncio
    async def test_async_callable(self):
        """Async callable is awaited."""
        stored = []

        async def async_store(record):
            stored.append(record)

        backend = CustomBackend(store_func=async_store)

        record = AuditRecord.create(
            method="POST",
            path="/api/data",
            status_code=201,
            duration_ms=10.0,
            ip_address="10.0.0.1",
        )

        await backend.store(record)
        assert len(stored) == 1
        assert stored[0].method == "POST"

    @pytest.mark.asyncio
    async def test_multiple_stores(self):
        """Multiple records stored correctly."""
        stored = []

        async def my_store(record):
            stored.append(record)

        backend = CustomBackend(store_func=my_store)

        for i in range(5):
            record = AuditRecord.create(
                method="GET",
                path=f"/api/item/{i}",
                status_code=200,
                duration_ms=1.0,
                ip_address="127.0.0.1",
            )
            await backend.store(record)

        assert len(stored) == 5

    @pytest.mark.asyncio
    async def test_query_not_supported(self):
        """Query raises NotImplementedError."""
        backend = CustomBackend(store_func=lambda r: None)
        with pytest.raises(NotImplementedError):
            await backend.query()
