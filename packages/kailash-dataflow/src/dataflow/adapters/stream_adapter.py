# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Stream Source Adapter — Kafka and WebSocket streaming sources.

Streams are continuous data sources where `detect_change()` always returns True.
Consumer group management and offset tracking are handled by the underlying
client library (aiokafka for Kafka, websockets for WebSocket).
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

from dataflow.adapters.source_adapter import BaseSourceAdapter
from dataflow.fabric.config import StreamSourceConfig

logger = logging.getLogger(__name__)

__all__ = ["StreamSourceAdapter"]


class StreamSourceAdapter(BaseSourceAdapter):
    """Source adapter for streaming data (Kafka, WebSocket)."""

    def __init__(self, name: str, config: StreamSourceConfig) -> None:
        super().__init__(name, circuit_breaker=config.circuit_breaker)
        self.config = config
        self._consumer: Any = None
        self._producer: Any = None
        self._ws: Any = None

    @property
    def source_type(self) -> str:
        broker = self.config.broker
        if broker.startswith("ws://") or broker.startswith("wss://"):
            return "websocket"
        return "kafka"

    async def _connect(self) -> None:
        if self.source_type == "kafka":
            try:
                from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
            except ImportError as exc:
                raise ImportError(
                    "aiokafka is required for Kafka sources. "
                    "Install with: pip install kailash-dataflow[streaming]"
                ) from exc

            consumer_kwargs: Dict[str, Any] = {
                "bootstrap_servers": self.config.broker,
                "value_deserializer": lambda v: json.loads(v.decode("utf-8")),
            }
            if self.config.group_id:
                consumer_kwargs["group_id"] = self.config.group_id

            self._consumer = AIOKafkaConsumer(self.config.topic, **consumer_kwargs)
            await self._consumer.start()

            self._producer = AIOKafkaProducer(
                bootstrap_servers=self.config.broker,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            )
            await self._producer.start()

        elif self.source_type == "websocket":
            try:
                import websockets
            except ImportError as exc:
                raise ImportError(
                    "websockets is required for WebSocket sources. "
                    "Install with: pip install kailash-dataflow[streaming]"
                ) from exc

            self._ws = await websockets.connect(self.config.broker)

        else:
            raise ValueError(f"Unknown stream broker type: {self.config.broker}")

        logger.debug(
            "Stream adapter '%s' connected to %s", self.name, self.config.broker
        )

    async def _disconnect(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def detect_change(self) -> bool:
        """Streams are continuous — always report as changed."""
        return True

    async def fetch(
        self, path: str = "", params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Consume a batch of messages from the stream."""
        if self.source_type == "kafka":
            if self._consumer is None:
                raise ConnectionError(f"Stream adapter '{self.name}' not connected")

            batch = await self._consumer.getmany(timeout_ms=1000, max_records=100)
            messages: List[Any] = []
            for tp, records in batch.items():
                for record in records:
                    messages.append(record.value)

            self._record_successful_data(path, messages)
            return messages

        elif self.source_type == "websocket":
            if self._ws is None:
                raise ConnectionError(f"Stream adapter '{self.name}' not connected")

            try:
                raw = await self._ws.recv()
                try:
                    data = json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    data = raw
                self._record_successful_data(path, data)
                return data
            except Exception as e:
                logger.error("WebSocket receive failed for '%s': %s", self.name, e)
                raise

        else:
            raise ConnectionError(f"Stream adapter '{self.name}' not connected")

    async def fetch_pages(
        self, path: str = "", page_size: int = 100
    ) -> AsyncIterator[List[Any]]:
        """Consume messages in batches."""
        if self.source_type == "kafka":
            if self._consumer is None:
                raise ConnectionError(f"Stream adapter '{self.name}' not connected")

            batch = await self._consumer.getmany(timeout_ms=2000, max_records=page_size)
            page: List[Any] = []
            for tp, records in batch.items():
                for record in records:
                    page.append(record.value)
                    if len(page) >= page_size:
                        yield page
                        page = []
            if page:
                yield page

        elif self.source_type == "websocket":
            # WebSocket doesn't support batching natively — yield single messages
            data = await self.fetch(path)
            yield [data] if not isinstance(data, list) else data

    async def write(self, path: str, data: Any) -> Any:
        """Produce messages to the stream."""
        if self.source_type == "kafka":
            if self._producer is None:
                raise ConnectionError(f"Stream adapter '{self.name}' not connected")

            topic = path or self.config.topic
            if isinstance(data, list):
                for item in data:
                    await self._producer.send_and_wait(topic, item)
                return {"topic": topic, "count": len(data)}
            else:
                await self._producer.send_and_wait(topic, data)
                return {"topic": topic, "count": 1}

        elif self.source_type == "websocket":
            if self._ws is None:
                raise ConnectionError(f"Stream adapter '{self.name}' not connected")

            payload = json.dumps(data) if isinstance(data, (dict, list)) else str(data)
            await self._ws.send(payload)
            return {"sent": True}

        else:
            raise ConnectionError(f"Stream adapter '{self.name}' not connected")

    def supports_feature(self, feature: str) -> bool:
        return feature in {"detect_change", "fetch", "fetch_pages", "write"}
