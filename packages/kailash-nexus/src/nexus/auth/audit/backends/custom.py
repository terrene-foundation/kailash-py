"""Custom backend wrapper for user-provided callable (TODO-310F)."""

import inspect
from typing import Awaitable, Callable, Union

from nexus.auth.audit.backends.base import AuditBackend
from nexus.auth.audit.record import AuditRecord

StoreCallable = Union[
    Callable[[AuditRecord], None],
    Callable[[AuditRecord], Awaitable[None]],
]


class CustomBackend(AuditBackend):
    """Custom backend wrapper for user-provided callable.

    Wraps a user-provided function as an audit backend.
    Supports both sync and async callables.
    """

    def __init__(self, store_func: StoreCallable):
        """Initialize custom backend.

        Args:
            store_func: Callable that accepts AuditRecord
        """
        self._store_func = store_func

    async def store(self, record: AuditRecord) -> None:
        """Store record using custom function."""
        # inspect.iscoroutinefunction — Python 3.14 deprecated asyncio's form;
        # inspect's form is the documented forward-compatible spelling.
        if inspect.iscoroutinefunction(self._store_func):
            await self._store_func(record)  # type: ignore[misc]
        else:
            self._store_func(record)
