# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
MockSource — test adapter for product functions without real connections.

Provides a fully controllable ``BaseSourceAdapter`` implementation for
unit and integration tests. Supports configurable data, change detection
triggers, and path-based routing.

Usage::

    from dataflow.fabric.testing import MockSource

    source = MockSource("crm", data={"deals": [{"id": 1}]})
    await source.connect()

    result = await source.fetch("deals")
    assert result == [{"id": 1}]

    source.trigger_change()
    assert await source.detect_change() is True

Design reference: TODO-27 in M5-M6 milestones.
"""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.adapters.source_adapter import BaseSourceAdapter, SourceState

logger = logging.getLogger(__name__)

__all__ = [
    "MockSource",
]


class MockSource(BaseSourceAdapter):
    """Mock source adapter for testing product functions without real connections.

    All data is stored in-memory. Change detection is configurable via
    ``trigger_change()`` and ``reset_change()``. Data can be pre-loaded
    at construction or updated at any time via ``set_data()``.

    Args:
        name: Source identifier (used in ``ctx.source(name)``).
        data: Optional mapping of path strings to response data.
            A key of ``""`` serves as the default path. For example,
            ``{"deals": [{"id": 1}], "": {"status": "ok"}}`` makes
            ``fetch("deals")`` return the list and ``fetch()`` return
            the status dict.
        change_detected: Initial change-detection state. When ``True``,
            the first call to ``detect_change()`` returns ``True`` and
            resets the flag (one-shot). Use ``trigger_change()`` to fire
            again.
    """

    def __init__(
        self,
        name: str,
        data: Optional[Dict[str, Any]] = None,
        change_detected: bool = False,
    ) -> None:
        super().__init__(name=name)
        self._mock_data: Dict[str, Any] = data if data is not None else {}
        self._change_detected = change_detected

    # ------------------------------------------------------------------
    # BaseAdapter abstract properties
    # ------------------------------------------------------------------

    @property
    def source_type(self) -> str:
        """Identifier for this adapter type."""
        return "mock"

    # ------------------------------------------------------------------
    # Connection lifecycle (no-ops for mock)
    # ------------------------------------------------------------------

    async def _connect(self) -> None:
        """No-op: mock adapter has no external connection to establish."""
        logger.debug("MockSource '%s': connect (no-op)", self.name)

    async def _disconnect(self) -> None:
        """No-op: mock adapter has no resources to release."""
        logger.debug("MockSource '%s': disconnect (no-op)", self.name)

    # ------------------------------------------------------------------
    # Change detection
    # ------------------------------------------------------------------

    async def detect_change(self) -> bool:
        """Return the current change-detection flag.

        The flag is consumed on read (one-shot): after returning ``True``
        the flag resets to ``False`` until ``trigger_change()`` is called
        again. This mirrors real adapters where a change is detected once
        per polling cycle.

        Returns:
            ``True`` if a change has been triggered since the last check.
        """
        if self._change_detected:
            self._change_detected = False
            return True
        return False

    # ------------------------------------------------------------------
    # Data retrieval
    # ------------------------------------------------------------------

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Fetch mock data for the given path.

        Path resolution order:

        1. Exact match on *path* in the mock data dict.
        2. Fallback to the default path ``""``.
        3. Raise ``KeyError`` if neither exists.

        Args:
            path: Resource path (e.g. ``"deals"``).
            params: Ignored for mock; accepted for interface compatibility.

        Returns:
            The pre-loaded data for *path*.

        Raises:
            KeyError: If no data is available for *path* or the default.
        """
        if path in self._mock_data:
            data = self._mock_data[path]
            self._record_successful_data(path, data)
            return data
        if "" in self._mock_data:
            data = self._mock_data[""]
            self._record_successful_data(path, data)
            return data
        raise KeyError(
            f"MockSource '{self.name}' has no data for path '{path}'. "
            f"Available paths: {sorted(self._mock_data.keys())}"
        )

    async def fetch_pages(  # type: ignore[override]
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        """Yield mock data as a single page.

        If the data at *path* is a list, it is chunked into pages of
        *page_size*. Otherwise, the data is wrapped in a single-element
        list and yielded as one page.

        Args:
            path: Resource path.
            page_size: Maximum records per page.

        Yields:
            Lists of records.
        """
        data = await self.fetch(path)
        if isinstance(data, list):
            for i in range(0, len(data), page_size):
                yield data[i : i + page_size]
        else:
            yield [data]

    # ------------------------------------------------------------------
    # Write support
    # ------------------------------------------------------------------

    async def write(self, path: str, data: Any) -> Any:
        """Store data in the mock data dict under *path*.

        Args:
            path: Resource path to write to.
            data: Data to store.

        Returns:
            The stored data.
        """
        self._mock_data[path] = data
        logger.debug("MockSource '%s': wrote data at path '%s'", self.name, path)
        return data

    # ------------------------------------------------------------------
    # Test helpers
    # ------------------------------------------------------------------

    def set_data(self, path: str, data: Any) -> None:
        """Update mock data for a specific path.

        This is a synchronous helper for test setup. It replaces any
        existing data at *path*.

        Args:
            path: Resource path to set.
            data: Data to store.
        """
        self._mock_data[path] = data

    def trigger_change(self) -> None:
        """Set the change-detection flag to ``True``.

        The next call to ``detect_change()`` (or ``safe_detect_change()``)
        will return ``True`` and reset the flag.
        """
        self._change_detected = True

    def reset_change(self) -> None:
        """Reset the change-detection flag to ``False`` without consuming it."""
        self._change_detected = False

    @property
    def mock_data(self) -> Dict[str, Any]:
        """Read-only access to the internal mock data dict.

        Useful for assertions in tests.
        """
        return dict(self._mock_data)
