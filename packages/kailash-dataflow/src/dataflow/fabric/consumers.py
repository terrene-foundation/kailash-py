# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Consumer adapter registry for DataFlow Fabric.

Consumers are pure functions that transform canonical product data into
consumer-specific views. A single product can support multiple consumers,
each producing a different shape from the same underlying data.

Example::

    def to_maturity_report(data: dict) -> dict:
        return {"maturity_score": data["score"], "date": data["date"]}

    db.fabric.register_consumer("maturity_report", to_maturity_report)

    @db.product("portfolio", depends_on=["User"], consumers=["maturity_report"])
    async def portfolio(ctx):
        ...

    # GET /fabric/portfolio?consumer=maturity_report
"""

from __future__ import annotations

import logging
from typing import Callable, Dict, List

logger = logging.getLogger(__name__)

__all__ = [
    "ConsumerFn",
    "ConsumerRegistry",
]

ConsumerFn = Callable[[dict], dict]
"""Pure function type: canonical product data -> consumer-specific view."""


class ConsumerRegistry:
    """Registry of consumer adapter functions for fabric products.

    Consumer functions are pure data transformations — they receive the
    canonical product data dict and return a consumer-specific view dict.
    They contain no side effects, no I/O, and no decision logic.

    Attributes:
        _consumers: Mapping of consumer name to transform function.
    """

    def __init__(self) -> None:
        self._consumers: Dict[str, ConsumerFn] = {}

    def register(self, name: str, fn: ConsumerFn) -> None:
        """Register a consumer adapter by name.

        Args:
            name: Unique consumer identifier.
            fn: Pure function that transforms canonical data to consumer view.

        Raises:
            ValueError: If *name* is empty or *fn* is not callable.
        """
        if not name or not name.strip():
            raise ValueError("Consumer name must be a non-empty string")
        if not callable(fn):
            raise ValueError(f"Consumer '{name}' function must be callable")
        self._consumers[name] = fn
        logger.debug("Registered consumer '%s'", name)

    def get(self, name: str) -> ConsumerFn | None:
        """Return the consumer function for *name*, or ``None`` if not found."""
        return self._consumers.get(name)

    def list_consumers(self) -> List[str]:
        """Return a list of all registered consumer names."""
        return list(self._consumers.keys())

    def transform(self, name: str, data: dict) -> dict:
        """Apply a registered consumer transform to product data.

        Args:
            name: Registered consumer name.
            data: Canonical product data dict.

        Returns:
            The consumer-specific view dict.

        Raises:
            ValueError: If *name* is not a registered consumer.
        """
        fn = self._consumers.get(name)
        if fn is None:
            raise ValueError(
                f"Unknown consumer: '{name}'. "
                f"Registered consumers: {self.list_consumers()}"
            )
        return fn(data)
