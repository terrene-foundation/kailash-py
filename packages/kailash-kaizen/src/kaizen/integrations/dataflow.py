# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Optional DataFlow integration for Kaizen agents.

Provides DataFlow-aware agent capabilities when kailash-dataflow is installed.
Degrades gracefully (DATAFLOW_AVAILABLE=False) when DataFlow is not present.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

__version__ = "0.1.0"

try:
    from dataflow.core.engine import DataFlow  # noqa: F401

    DATAFLOW_AVAILABLE = True
except ImportError:
    DATAFLOW_AVAILABLE = False


class DataFlowConnection:
    """Manages a connection between a Kaizen agent and a DataFlow instance.

    Provides convenience methods for agents to query and mutate data
    through the DataFlow Express API.
    """

    def __init__(self, dataflow: Any) -> None:
        if not DATAFLOW_AVAILABLE:
            raise RuntimeError(
                "kailash-dataflow is not installed. "
                "Install with: pip install kailash-dataflow"
            )
        self._dataflow = dataflow

    @property
    def express(self) -> Any:
        """Access the DataFlow Express API."""
        return getattr(self._dataflow, "_express_dataflow", None)

    async def query(
        self, model_name: str, filters: dict | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Query records from a DataFlow model."""
        express = self.express
        if express is None:
            raise RuntimeError("DataFlow Express API not available")
        return await express.list(model_name, filters or {}, limit=limit)


class DataFlowAwareAgent:
    """Mixin that adds DataFlow awareness to a Kaizen agent.

    Agents inheriting this mixin gain access to DataFlow operations
    through a managed connection.
    """

    _dataflow_connection: DataFlowConnection | None = None

    def set_dataflow(self, dataflow: Any) -> None:
        """Attach a DataFlow instance to this agent."""
        self._dataflow_connection = DataFlowConnection(dataflow)

    @property
    def dataflow(self) -> DataFlowConnection | None:
        """The DataFlow connection, or None if not attached."""
        return self._dataflow_connection


class DataFlowOperationsMixin:
    """Provides DataFlow CRUD operations as agent tool methods.

    When mixed into a BaseAgent subclass, exposes create/read/update/delete
    operations that the agent's LLM can invoke via tool calls.
    """

    _dataflow_connection: DataFlowConnection | None = None

    async def df_create(self, model_name: str, data: dict[str, Any]) -> dict[str, Any]:
        """Create a record in DataFlow."""
        if self._dataflow_connection is None:
            raise RuntimeError("DataFlow not connected")
        express = self._dataflow_connection.express
        if express is None:
            raise RuntimeError("DataFlow Express API not available")
        return await express.create(model_name, data)

    async def df_read(self, model_name: str, record_id: str) -> dict[str, Any]:
        """Read a record from DataFlow."""
        if self._dataflow_connection is None:
            raise RuntimeError("DataFlow not connected")
        express = self._dataflow_connection.express
        if express is None:
            raise RuntimeError("DataFlow Express API not available")
        return await express.read(model_name, record_id)


__all__ = [
    "DATAFLOW_AVAILABLE",
    "DataFlowConnection",
    "DataFlowAwareAgent",
    "DataFlowOperationsMixin",
]
