"""Abstract audit backend interface (TODO-310F)."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

from nexus.auth.audit.record import AuditRecord


class AuditBackend(ABC):
    """Abstract interface for audit storage backends.

    All backends must implement store() for writing records.
    Query methods are optional (raise NotImplementedError if not supported).
    """

    @abstractmethod
    async def store(self, record: AuditRecord) -> None:
        """Store an audit record.

        Args:
            record: AuditRecord to store
        """
        pass

    async def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        path_pattern: Optional[str] = None,
        status_code: Optional[int] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditRecord]:
        """Query audit records (optional).

        Raises:
            NotImplementedError: If query not supported
        """
        raise NotImplementedError("Query not supported by this backend")

    async def close(self) -> None:
        """Clean up resources."""
        pass
