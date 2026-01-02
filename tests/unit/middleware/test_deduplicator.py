"""Unit tests for RequestDeduplicator."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from kailash.middleware.gateway.deduplicator import (
    CachedResponse,
    RequestDeduplicator,
    RequestFingerprinter,
)


class TestRequestFingerprinter:
    """Test RequestFingerprinter."""

    def test_basic_fingerprint(self):
        """Test basic request fingerprinting."""
        fp1 = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={"page": "1", "limit": "10"},
        )

        fp2 = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={"page": "1", "limit": "10"},
        )

        # Same request should have same fingerprint
        assert fp1 == fp2

    def test_fingerprint_different_methods(self):
        """Test fingerprints differ for different methods."""
        fp_get = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={},
        )

        fp_post = RequestFingerprinter.create_fingerprint(
            method="POST",
            path="/api/users",
            query_params={},
        )

        assert fp_get != fp_post

    def test_fingerprint_with_body(self):
        """Test fingerprinting with request body."""
        fp1 = RequestFingerprinter.create_fingerprint(
            method="POST",
            path="/api/users",
            query_params={},
            body={"name": "John", "age": 30},
        )

        fp2 = RequestFingerprinter.create_fingerprint(
            method="POST",
            path="/api/users",
            query_params={},
            body={"age": 30, "name": "John"},  # Different order
        )

        # Should be same despite different key order
        assert fp1 == fp2

    def test_fingerprint_body_normalization(self):
        """Test body normalization removes null values."""
        fp1 = RequestFingerprinter.create_fingerprint(
            method="POST",
            path="/api/users",
            query_params={},
            body={"name": "John", "age": None, "active": True},
        )

        fp2 = RequestFingerprinter.create_fingerprint(
            method="POST",
            path="/api/users",
            query_params={},
            body={"name": "John", "active": True},  # No age key
        )

        assert fp1 == fp2

    def test_fingerprint_query_param_normalization(self):
        """Test query parameter normalization."""
        fp1 = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={"page": "1", "limit": "", "filter": None},
        )

        fp2 = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={"page": "1"},  # Empty and None values removed
        )

        assert fp1 == fp2

    def test_fingerprint_with_headers(self):
        """Test fingerprinting with specific headers."""
        fp1 = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={},
            headers={"X-API-Key": "secret", "User-Agent": "test"},
            include_headers={"X-API-Key"},
        )

        fp2 = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={},
            headers={"X-API-Key": "secret", "User-Agent": "different"},
            include_headers={"X-API-Key"},
        )

        # Should be same (User-Agent not included)
        assert fp1 == fp2

        fp3 = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/api/users",
            query_params={},
            headers={"X-API-Key": "different", "User-Agent": "test"},
            include_headers={"X-API-Key"},
        )

        # Should be different (X-API-Key is different)
        assert fp1 != fp3


class TestCachedResponse:
    """Test CachedResponse dataclass."""

    def test_is_expired(self):
        """Test expiration check."""
        # Create response from 2 hours ago
        old_response = CachedResponse(
            request_fingerprint="fp123",
            idempotency_key=None,
            response_data={"status": "ok"},
            status_code=200,
            headers={},
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )

        assert old_response.is_expired(3600)  # 1 hour TTL
        assert not old_response.is_expired(10800)  # 3 hour TTL

    def test_to_response(self):
        """Test converting to response format."""
        cached = CachedResponse(
            request_fingerprint="fp123",
            idempotency_key="idem456",
            response_data={"result": "success"},
            status_code=201,
            headers={"X-Custom": "value"},
            created_at=datetime.now(UTC) - timedelta(seconds=30),
        )

        response = cached.to_response()

        assert response["data"] == {"result": "success"}
        assert response["status_code"] == 201
        assert response["headers"] == {"X-Custom": "value"}
        assert response["cached"] is True
        assert 29 <= response["cache_age_seconds"] <= 31


class TestRequestDeduplicator:
    """Test RequestDeduplicator."""

    @pytest.mark.asyncio
    async def test_no_duplicate_first_request(self):
        """Test first request is not duplicate."""
        dedup = RequestDeduplicator()

        result = await dedup.check_duplicate(
            method="GET",
            path="/api/users",
            query_params={},
        )

        assert result is None
        assert dedup.miss_count == 1
        assert dedup.hit_count == 0

    @pytest.mark.asyncio
    async def test_cache_and_detect_duplicate(self):
        """Test caching response and detecting duplicate."""
        dedup = RequestDeduplicator()

        # Cache a response
        await dedup.cache_response(
            method="GET",
            path="/api/users",
            query_params={"page": "1"},
            body=None,
            headers={},
            idempotency_key=None,
            response_data={"users": ["user1", "user2"]},
            status_code=200,
        )

        # Check for duplicate
        result = await dedup.check_duplicate(
            method="GET",
            path="/api/users",
            query_params={"page": "1"},
        )

        assert result is not None
        assert result["data"] == {"users": ["user1", "user2"]}
        assert result["status_code"] == 200
        assert result["cached"] is True
        assert dedup.hit_count == 1

    @pytest.mark.asyncio
    async def test_idempotency_key_same_request(self):
        """Test idempotency key with same request."""
        dedup = RequestDeduplicator()

        # Cache with idempotency key
        await dedup.cache_response(
            method="POST",
            path="/api/orders",
            query_params={},
            body={"item": "widget"},
            headers={},
            idempotency_key="order_123",
            response_data={"order_id": "12345"},
            status_code=201,
        )

        # Same request with same idempotency key
        result = await dedup.check_duplicate(
            method="POST",
            path="/api/orders",
            query_params={},
            body={"item": "widget"},
            headers={},
            idempotency_key="order_123",
        )

        assert result is not None
        assert result["data"] == {"order_id": "12345"}

    @pytest.mark.asyncio
    async def test_idempotency_key_different_request(self):
        """Test idempotency key with different request raises error."""
        dedup = RequestDeduplicator()

        # Cache with idempotency key
        await dedup.cache_response(
            method="POST",
            path="/api/orders",
            query_params={},
            body={"item": "widget"},
            headers={},
            idempotency_key="order_123",
            response_data={"order_id": "12345"},
            status_code=201,
        )

        # Different request with same idempotency key
        with pytest.raises(ValueError, match="different request"):
            await dedup.check_duplicate(
                method="POST",
                path="/api/orders",
                query_params={},
                body={"item": "gadget"},  # Different body
                headers={},
                idempotency_key="order_123",
            )

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        """Test TTL expiration of cached responses."""
        dedup = RequestDeduplicator(ttl_seconds=1)  # 1 second TTL

        # Generate the actual fingerprint that will be used
        from kailash.middleware.gateway.deduplicator import RequestFingerprinter

        fingerprint = RequestFingerprinter.create_fingerprint(
            method="GET",
            path="/test",
            query_params={},
            body=None,
            headers=None,
            include_headers=None,
        )

        # Create expired response
        expired = CachedResponse(
            request_fingerprint=fingerprint,
            idempotency_key=None,
            response_data={"status": "ok"},
            status_code=200,
            headers={},
            created_at=datetime.now(UTC) - timedelta(seconds=2),
        )

        # Add directly to cache
        dedup._cache[fingerprint] = expired

        # Check should return None (expired)
        result = await dedup.check_duplicate(
            method="GET",
            path="/test",
            query_params={},
        )

        assert result is None
        assert fingerprint not in dedup._cache  # Should be removed

        # Clean up
        await dedup.close()

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        """Test LRU eviction when cache is full."""
        dedup = RequestDeduplicator(max_cache_size=2)

        # Cache 3 responses (should evict first)
        for i in range(3):
            await dedup.cache_response(
                method="GET",
                path=f"/api/item{i}",
                query_params={},
                body=None,
                headers={},
                idempotency_key=None,
                response_data={"item": i},
                status_code=200,
            )

        assert len(dedup._cache) == 2
        assert dedup.eviction_count == 1

        # Clean up
        await dedup.close()

    @pytest.mark.asyncio
    async def test_no_cache_error_responses(self):
        """Test error responses are not cached."""
        dedup = RequestDeduplicator()

        # Try to cache error response
        await dedup.cache_response(
            method="GET",
            path="/api/error",
            query_params={},
            body=None,
            headers={},
            idempotency_key=None,
            response_data={"error": "Not found"},
            status_code=404,  # Error status
        )

        # Should not be in cache
        result = await dedup.check_duplicate(
            method="GET",
            path="/api/error",
            query_params={},
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_persistent_storage(self):
        """Test integration with persistent storage."""
        mock_storage = AsyncMock()
        mock_storage.get.return_value = {
            "request_fingerprint": "fp123",
            "idempotency_key": None,
            "response_data": {"persisted": True},
            "status_code": 200,
            "headers": {},
            "created_at": datetime.now(UTC),
            "request_count": 1,
            "last_accessed": datetime.now(UTC),
        }

        dedup = RequestDeduplicator(storage_backend=mock_storage)

        # Check duplicate (should hit storage)
        result = await dedup.check_duplicate(
            method="GET",
            path="/api/data",
            query_params={},
        )

        assert result is not None
        assert result["data"] == {"persisted": True}
        assert dedup.hit_count == 1

        # Should be promoted to cache
        assert len(dedup._cache) == 1

        # Clean up
        await dedup.close()

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self):
        """Test cleanup of expired entries."""
        dedup = RequestDeduplicator(ttl_seconds=1)

        # Add expired entries
        for i in range(3):
            expired = CachedResponse(
                request_fingerprint=f"fp{i}",
                idempotency_key=None,
                response_data={},
                status_code=200,
                headers={},
                created_at=datetime.now(UTC) - timedelta(seconds=2),
            )
            dedup._cache[f"fp{i}"] = expired

        # Add valid entry
        valid = CachedResponse(
            request_fingerprint="fp_valid",
            idempotency_key=None,
            response_data={},
            status_code=200,
            headers={},
            created_at=datetime.now(UTC),
        )
        dedup._cache["fp_valid"] = valid

        # Run cleanup
        await dedup._cleanup_expired()

        assert len(dedup._cache) == 1
        assert "fp_valid" in dedup._cache

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test getting deduplicator statistics."""
        dedup = RequestDeduplicator()
        dedup.hit_count = 10
        dedup.miss_count = 5
        dedup.eviction_count = 2
        dedup._cache = {"fp1": None, "fp2": None}
        dedup._idempotency_cache = {"idem1": "fp1"}

        stats = dedup.get_stats()

        assert stats["hit_count"] == 10
        assert stats["miss_count"] == 5
        assert stats["hit_rate"] == 10 / 15  # 10 hits / 15 total
        assert stats["cache_size"] == 2
        assert stats["eviction_count"] == 2
        assert stats["idempotency_keys"] == 1

        # Clean up
        await dedup.close()

    @pytest.mark.asyncio
    async def test_close(self):
        """Test closing deduplicator."""
        dedup = RequestDeduplicator()

        await dedup.close()

        assert dedup._cleanup_task.cancelled()
