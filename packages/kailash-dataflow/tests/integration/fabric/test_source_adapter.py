# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Tier 1 unit tests for BaseSourceAdapter — abstract contract, state machine,
circuit breaker logic.
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional

import pytest

from dataflow.adapters.source_adapter import (
    BaseSourceAdapter,
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerState,
    SourceState,
)


class StubSourceAdapter(BaseSourceAdapter):
    """Minimal concrete adapter for testing the abstract contract."""

    def __init__(
        self,
        name: str = "test",
        fail_connect: bool = False,
        fail_fetch: bool = False,
        change_detected: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(name, **kwargs)
        self._fail_connect = fail_connect
        self._fail_fetch = fail_fetch
        self._change_detected = change_detected
        self._fetch_count = 0

    @property
    def source_type(self) -> str:
        return "stub"

    async def _connect(self) -> None:
        if self._fail_connect:
            raise ConnectionError("Stub connect failure")

    async def _disconnect(self) -> None:
        pass

    async def detect_change(self) -> bool:
        if self._fail_fetch:
            raise ConnectionError("Stub detect_change failure")
        return self._change_detected

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        self._fetch_count += 1
        if self._fail_fetch:
            raise ConnectionError("Stub fetch failure")
        return {"path": path, "data": "test_data"}

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        data = await self.fetch(path)
        yield [data]


# ---------- State machine tests ----------


class TestSourceState:
    @pytest.mark.asyncio
    async def test_initial_state_is_registered(self):
        adapter = StubSourceAdapter()
        assert adapter.state == SourceState.REGISTERED
        assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_connect_transitions_to_active(self):
        adapter = StubSourceAdapter()
        await adapter.connect()
        assert adapter.state == SourceState.ACTIVE
        assert adapter.is_connected
        assert adapter.healthy

    @pytest.mark.asyncio
    async def test_failed_connect_transitions_to_error(self):
        adapter = StubSourceAdapter(fail_connect=True)
        with pytest.raises(ConnectionError):
            await adapter.connect()
        assert adapter.state == SourceState.ERROR
        assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_disconnect_transitions_to_disconnected(self):
        adapter = StubSourceAdapter()
        await adapter.connect()
        await adapter.disconnect()
        assert adapter.state == SourceState.DISCONNECTED
        assert not adapter.is_connected

    @pytest.mark.asyncio
    async def test_double_connect_is_idempotent(self):
        adapter = StubSourceAdapter()
        await adapter.connect()
        await adapter.connect()  # Should not raise
        assert adapter.state == SourceState.ACTIVE

    @pytest.mark.asyncio
    async def test_health_check_returns_state(self):
        adapter = StubSourceAdapter(name="my_source")
        await adapter.connect()
        health = await adapter.health_check()
        assert health["healthy"] is True
        assert health["source_name"] == "my_source"
        assert health["state"] == "active"
        assert health["circuit_breaker"] == "closed"


# ---------- Circuit breaker tests ----------


class TestCircuitBreaker:
    def test_initial_state_is_closed(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.allow_request()

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure("err1")
        cb.record_failure("err2")
        assert cb.state == CircuitBreakerState.CLOSED
        cb.record_failure("err3")
        assert cb.state == CircuitBreakerState.OPEN
        assert not cb.allow_request()

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))
        cb.record_failure("err1")
        cb.record_failure("err2")
        cb.record_success()
        assert cb.failure_count == 0
        cb.record_failure("err1")
        cb.record_failure("err2")
        assert cb.state == CircuitBreakerState.CLOSED

    def test_half_open_after_probe_interval(self):
        import time

        cb = CircuitBreaker(
            config=CircuitBreakerConfig(failure_threshold=1, probe_interval=0.01)
        )
        cb.record_failure("err")
        assert cb.state == CircuitBreakerState.OPEN
        assert not cb.allow_request()

        time.sleep(0.02)
        assert cb.allow_request()
        assert cb.state == CircuitBreakerState.HALF_OPEN

    def test_half_open_closes_on_success(self):
        import time

        cb = CircuitBreaker(
            config=CircuitBreakerConfig(
                failure_threshold=1, probe_interval=0.01, success_threshold=1
            )
        )
        cb.record_failure("err")
        time.sleep(0.02)
        cb.allow_request()  # Transition to HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

    def test_half_open_reopens_on_failure(self):
        import time

        cb = CircuitBreaker(
            config=CircuitBreakerConfig(failure_threshold=1, probe_interval=0.01)
        )
        cb.record_failure("err1")
        time.sleep(0.02)
        cb.allow_request()  # Transition to HALF_OPEN
        cb.record_failure("err2")
        assert cb.state == CircuitBreakerState.OPEN


# ---------- Safe fetch / detect_change with circuit breaker ----------


class TestSafeFetchAndDetect:
    @pytest.mark.asyncio
    async def test_safe_fetch_records_success(self):
        adapter = StubSourceAdapter()
        await adapter.connect()
        result = await adapter.safe_fetch("test_path")
        assert result == {"path": "test_path", "data": "test_data"}
        assert adapter.last_successful_data("test_path") is not None

    @pytest.mark.asyncio
    async def test_safe_fetch_serves_last_good_on_failure(self):
        adapter = StubSourceAdapter()
        await adapter.connect()

        # First fetch succeeds and caches
        await adapter.safe_fetch("path")

        # Now make it fail
        adapter._fail_fetch = True
        result = await adapter.safe_fetch("path")
        assert result == {"path": "path", "data": "test_data"}  # Cached data

    @pytest.mark.asyncio
    async def test_safe_fetch_raises_when_circuit_open_no_cache(self):
        adapter = StubSourceAdapter(
            fail_fetch=True,
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1),
        )
        await adapter.connect()

        with pytest.raises(ConnectionError):
            await adapter.safe_fetch("new_path")

        # Circuit is now open
        with pytest.raises(ConnectionError, match="circuit breaker open"):
            await adapter.safe_fetch("new_path")

    @pytest.mark.asyncio
    async def test_safe_detect_change_records_timestamp(self):
        adapter = StubSourceAdapter(change_detected=True)
        await adapter.connect()
        changed = await adapter.safe_detect_change()
        assert changed is True
        assert adapter.last_change_detected is not None

    @pytest.mark.asyncio
    async def test_safe_detect_change_pauses_on_circuit_open(self):
        adapter = StubSourceAdapter(
            fail_fetch=True,
            circuit_breaker=CircuitBreakerConfig(failure_threshold=1),
        )
        await adapter.connect()

        with pytest.raises(ConnectionError):
            await adapter.safe_detect_change()

        assert adapter.state == SourceState.PAUSED


# ---------- fetch_all memory guard ----------


class TestFetchAllMemoryGuard:
    @pytest.mark.asyncio
    async def test_fetch_all_returns_all_records(self):
        adapter = StubSourceAdapter()
        await adapter.connect()
        results = await adapter.fetch_all("path", max_records=10)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_fetch_all_raises_on_max_records_exceeded(self):
        class LargeAdapter(StubSourceAdapter):
            async def fetch_pages(
                self, path: str = "", page_size: int = 100
            ) -> AsyncIterator[List[Any]]:
                for _ in range(10):
                    yield list(range(page_size))

        adapter = LargeAdapter()
        await adapter.connect()
        with pytest.raises(MemoryError, match="max_records"):
            await adapter.fetch_all("path", page_size=100, max_records=500)


# ---------- Misc ----------


class TestAdapterMisc:
    @pytest.mark.asyncio
    async def test_write_raises_not_implemented_by_default(self):
        adapter = StubSourceAdapter()
        with pytest.raises(NotImplementedError, match="does not support writes"):
            await adapter.write("path", {"data": 1})

    @pytest.mark.asyncio
    async def test_read_aliases_fetch_empty(self):
        adapter = StubSourceAdapter()
        await adapter.connect()
        result = await adapter.read()
        assert result["path"] == ""

    def test_repr(self):
        adapter = StubSourceAdapter(name="my_src")
        r = repr(adapter)
        assert "my_src" in r
        assert "registered" in r

    def test_supports_feature(self):
        adapter = StubSourceAdapter()
        assert adapter.supports_feature("detect_change")
        assert adapter.supports_feature("fetch")
        assert not adapter.supports_feature("vector_search")
