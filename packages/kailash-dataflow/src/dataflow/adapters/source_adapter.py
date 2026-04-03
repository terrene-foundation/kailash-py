# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Base Source Adapter — abstract contract for all external data sources.

Parallel to DatabaseAdapter (which handles SQL databases), BaseSourceAdapter
handles external data sources: REST APIs, files, cloud storage, databases,
and streams. Source adapters manage their own connection lifecycle because
non-database connections do not share the same pooling constraints as
database connections (F1 resolution).

State machine: registered → connecting → active → paused → error
Circuit breaker: configurable failure threshold with automatic probe.
"""

from __future__ import annotations

import asyncio
import collections
import enum
import logging
import time
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.adapters.base_adapter import BaseAdapter

logger = logging.getLogger(__name__)

__all__ = [
    "BaseSourceAdapter",
    "SourceState",
    "CircuitBreakerConfig",
    "CircuitBreakerState",
]


class SourceState(enum.Enum):
    """Source adapter lifecycle states."""

    REGISTERED = "registered"
    CONNECTING = "connecting"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    DISCONNECTED = "disconnected"


class CircuitBreakerState(enum.Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting calls
    HALF_OPEN = "half_open"  # Probing after cooldown


@dataclass
class CircuitBreakerConfig:
    """Configuration for adapter circuit breaker."""

    failure_threshold: int = 3
    probe_interval: float = 30.0  # seconds before probing after open
    success_threshold: int = 1  # successes needed to close from half_open


@dataclass
class CircuitBreaker:
    """Circuit breaker implementation for source adapters."""

    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0.0
    last_error: Optional[str] = None

    def record_success(self) -> None:
        """Record a successful operation."""
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.last_error = None
                logger.debug("Circuit breaker closed after successful probe")
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def record_failure(self, error: str) -> None:
        """Record a failed operation."""
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        self.last_error = error

        if self.state == CircuitBreakerState.HALF_OPEN:
            self.state = CircuitBreakerState.OPEN
            self.success_count = 0
            logger.warning("Circuit breaker re-opened after probe failure: %s", error)
        elif (
            self.state == CircuitBreakerState.CLOSED
            and self.failure_count >= self.config.failure_threshold
        ):
            self.state = CircuitBreakerState.OPEN
            logger.warning(
                "Circuit breaker opened after %d failures: %s",
                self.failure_count,
                error,
            )

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.config.probe_interval:
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                logger.debug("Circuit breaker entering half-open state for probe")
                return True
            return False

        # HALF_OPEN — allow probe requests
        return True


class BaseSourceAdapter(BaseAdapter):
    """
    Abstract base for all external data source adapters.

    Extends BaseAdapter with source-specific methods: detect_change, fetch,
    fetch_all, fetch_pages, write, and last_successful_data.

    Concrete implementations:
    - RestSourceAdapter (HTTP APIs)
    - FileSourceAdapter (local files)
    - CloudSourceAdapter (S3, GCS, Azure Blob)
    - DatabaseSourceAdapter (external databases)
    - StreamSourceAdapter (Kafka, WebSocket)
    """

    def __init__(self, name: str, **kwargs: Any) -> None:
        super().__init__(connection_string=name, **kwargs)
        self.name = name
        self._state = SourceState.REGISTERED
        self._circuit_breaker = CircuitBreaker(
            config=kwargs.get("circuit_breaker", CircuitBreakerConfig())
        )
        self._last_successful_data: collections.OrderedDict[str, Any] = (
            collections.OrderedDict()
        )
        self._last_change_detected: Optional[datetime] = None
        self._connect_lock = asyncio.Lock()

    @property
    def adapter_type(self) -> str:
        return "source"

    @property
    def state(self) -> SourceState:
        return self._state

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    @property
    def last_change_detected(self) -> Optional[datetime]:
        return self._last_change_detected

    @property
    def healthy(self) -> bool:
        return (
            self._state == SourceState.ACTIVE
            and self._circuit_breaker.state != CircuitBreakerState.OPEN
        )

    async def connect(self) -> None:
        """Connect to the source. Thread-safe via lock."""
        async with self._connect_lock:
            if self._state == SourceState.ACTIVE:
                return
            self._state = SourceState.CONNECTING
            try:
                await self._connect()
                self._state = SourceState.ACTIVE
                self.is_connected = True
                logger.debug("Source '%s' connected", self.name)
            except Exception as e:
                self._state = SourceState.ERROR
                self.is_connected = False
                logger.error("Source '%s' connection failed: %s", self.name, e)
                raise

    async def disconnect(self) -> None:
        """Disconnect from the source."""
        try:
            await self._disconnect()
        finally:
            self._state = SourceState.DISCONNECTED
            self.is_connected = False
            logger.debug("Source '%s' disconnected", self.name)

    @abstractmethod
    async def _connect(self) -> None:
        """Implementation-specific connection logic."""

    @abstractmethod
    async def _disconnect(self) -> None:
        """Implementation-specific disconnection logic."""

    @abstractmethod
    async def detect_change(self) -> bool:
        """
        Cheap change detection.

        Returns True if the source data has changed since last check.
        Implementations should use lightweight mechanisms:
        - REST: ETag / If-Modified-Since / content hash
        - File: mtime comparison
        - Database: MAX(updated_at) or change counter
        - Stream: always True
        """

    @abstractmethod
    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """
        Fetch data from a single endpoint/path.

        Args:
            path: Resource path (e.g., "deals" for REST, table name for DB)
            params: Optional query parameters

        Returns:
            Parsed response data
        """

    async def fetch_all(
        self,
        path: str = "",
        page_size: int = 100,
        max_records: int = 100_000,
    ) -> List[Any]:
        """
        Auto-paginate and fetch all records with memory guard.

        Args:
            path: Resource path
            page_size: Records per page
            max_records: Maximum total records (memory guard)

        Returns:
            List of all records

        Raises:
            MemoryError: If max_records exceeded
        """
        all_records: List[Any] = []
        async for page in self.fetch_pages(path, page_size):
            if isinstance(page, list):
                all_records.extend(page)
            else:
                all_records.append(page)
            if len(all_records) > max_records:
                raise MemoryError(
                    f"Source '{self.name}' fetch_all exceeded max_records "
                    f"({max_records}). Use fetch_pages() for streaming."
                )
        return all_records

    @abstractmethod
    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        """
        Stream pages of data as an async iterator.

        Args:
            path: Resource path
            page_size: Records per page

        Yields:
            Pages of records
        """
        yield []  # pragma: no cover — abstract, overridden by subclasses

    async def read(self) -> Any:
        """Alias for fetch("") — read the default resource."""
        return await self.fetch("")

    async def list(self, prefix: str = "", limit: int = 1000) -> List[Any]:
        """
        List available items/resources.

        Args:
            prefix: Filter prefix
            limit: Maximum items to return
        """
        return await self.fetch_all(prefix, page_size=limit, max_records=limit)

    async def write(self, path: str, data: Any) -> Any:
        """
        Write data to the source.

        Args:
            path: Resource path
            data: Data to write

        Raises:
            NotImplementedError: If source is read-only
        """
        raise NotImplementedError(
            f"Source '{self.name}' does not support writes. "
            f"Override write() in {self.__class__.__name__} to enable."
        )

    def last_successful_data(self, path: str = "") -> Optional[Any]:
        """
        Return the last known good data for graceful degradation.

        When a source is unhealthy, products can fall back to the last
        successful fetch result instead of failing entirely.
        """
        return self._last_successful_data.get(path)

    _MAX_CACHED_PATHS = 1000

    def _record_successful_data(self, path: str, data: Any) -> None:
        """Store data as last known good for graceful degradation.

        Bounded to _MAX_CACHED_PATHS entries with LRU eviction.
        """
        if path in self._last_successful_data:
            self._last_successful_data.move_to_end(path)
        self._last_successful_data[path] = data
        while len(self._last_successful_data) > self._MAX_CACHED_PATHS:
            self._last_successful_data.popitem(last=False)

    def _record_change_detected(self) -> None:
        """Mark that a change was detected now."""
        self._last_change_detected = datetime.now(timezone.utc)

    async def safe_detect_change(self) -> bool:
        """Detect change with circuit breaker protection."""
        if not self._circuit_breaker.allow_request():
            return False

        try:
            changed = await self.detect_change()
            self._circuit_breaker.record_success()
            if changed:
                self._record_change_detected()
            return changed
        except Exception as e:
            self._circuit_breaker.record_failure(str(e))
            if self._circuit_breaker.state == CircuitBreakerState.OPEN:
                self._state = SourceState.PAUSED
            raise

    async def safe_fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Fetch with circuit breaker protection and last-good caching."""
        if not self._circuit_breaker.allow_request():
            last = self.last_successful_data(path)
            if last is not None:
                logger.warning(
                    "Source '%s' circuit open, serving last good data for '%s'",
                    self.name,
                    path,
                )
                return last
            raise ConnectionError(
                f"Source '{self.name}' circuit breaker open and no cached data for '{path}'"
            )

        try:
            data = await self.fetch(path, params)
            self._circuit_breaker.record_success()
            self._record_successful_data(path, data)
            return data
        except Exception as e:
            self._circuit_breaker.record_failure(str(e))
            if self._circuit_breaker.state == CircuitBreakerState.OPEN:
                self._state = SourceState.PAUSED
            last = self.last_successful_data(path)
            if last is not None:
                logger.warning(
                    "Source '%s' fetch failed, serving last good data for '%s': %s",
                    self.name,
                    path,
                    e,
                )
                return last
            raise

    def supports_feature(self, feature: str) -> bool:
        """Check feature support. Override in subclasses."""
        return feature in {"detect_change", "fetch", "fetch_pages"}

    async def health_check(self) -> Dict[str, Any]:
        """Source-specific health check."""
        return {
            "healthy": self.healthy,
            "source_name": self.name,
            "source_type": self.database_type,
            "state": self._state.value,
            "circuit_breaker": self._circuit_breaker.state.value,
            "consecutive_failures": self._circuit_breaker.failure_count,
            "last_change_detected": (
                self._last_change_detected.isoformat()
                if self._last_change_detected
                else None
            ),
            "last_error": self._circuit_breaker.last_error,
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"state={self._state.value}, "
            f"circuit={self._circuit_breaker.state.value})"
        )
