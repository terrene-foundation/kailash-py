"""Protocol definition for EventStore storage backends.

Defines the interface contract that storage backends must satisfy
for use with EventStore. Backends must implement async append() and get()
methods matching the implicit interface used by EventStore._store_events
and EventStore._load_from_storage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

__all__ = ["EventStoreBackend"]


@runtime_checkable
class EventStoreBackend(Protocol):
    """Protocol for EventStore storage backends.

    Any class implementing these async methods can serve as a storage_backend
    for EventStore. The EventStore groups events by request_id and calls:

    - append(key, events) where key is "events:{request_id}" and events
      is a list of event dicts (from RequestEvent.to_dict())
    - get(key) to retrieve all stored event dicts for a given key

    Existing implementations: RedisEventStorage, PostgreSQLEventStorage.
    """

    async def append(self, key: str, events: List[Dict[str, Any]]) -> None:
        """Append events to a stream identified by key.

        Args:
            key: Stream key in the format "events:{request_id}".
            events: List of serialized event dicts (from RequestEvent.to_dict()).
        """
        ...

    async def get(self, key: str) -> List[Dict[str, Any]]:
        """Retrieve all events for a stream identified by key.

        Args:
            key: Stream key in the format "events:{request_id}".

        Returns:
            List of event dicts, ordered by sequence number.
        """
        ...

    async def close(self) -> None:
        """Release any resources held by the backend."""
        ...
