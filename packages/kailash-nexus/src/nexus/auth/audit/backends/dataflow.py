"""DataFlow database backend for audit records (TODO-310F).

Stores audit records in a database table via DataFlow.
Supports querying for compliance and debugging.
"""

import logging
from datetime import datetime
from typing import Any, List, Optional

from nexus.auth.audit.backends.base import AuditBackend
from nexus.auth.audit.record import AuditRecord

logger = logging.getLogger(__name__)


class DataFlowBackend(AuditBackend):
    """DataFlow database backend for audit records.

    Stores audit records in a database table via DataFlow.
    Supports querying for compliance and debugging.
    """

    def __init__(
        self,
        dataflow: Any,
        model_name: str = "AuditRecord",
    ):
        """Initialize DataFlow backend.

        Args:
            dataflow: DataFlow instance
            model_name: Name of the audit model (default: "AuditRecord")
        """
        self._db = dataflow
        self._model_name = model_name
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize the audit model in DataFlow."""
        if self._initialized:
            return

        try:
            self._db.get_model(self._model_name)
        except Exception:
            logger.warning(
                f"Audit model '{self._model_name}' not found. "
                "Please define the model in your DataFlow instance."
            )

        self._initialized = True

    async def store(self, record: AuditRecord) -> None:
        """Store audit record in database."""
        if not self._initialized:
            await self.initialize()

        try:
            await self._db.create(
                self._model_name,
                record.to_dict(),
            )
        except Exception as e:
            # Never let audit storage failures break the application
            logger.error(f"Failed to store audit record: {e}")

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
        """Query audit records from database."""
        if not self._initialized:
            await self.initialize()

        filters = {}
        if user_id:
            filters["user_id"] = user_id
        if tenant_id:
            filters["tenant_id"] = tenant_id
        if status_code:
            filters["status_code"] = status_code

        try:
            records = await self._db.list(
                self._model_name,
                filter=filters,
                limit=limit,
                offset=offset,
                order_by=["-timestamp"],
            )

            result = []
            for record_data in records:
                record = AuditRecord.from_dict(record_data)

                if start_time and record.timestamp < start_time:
                    continue
                if end_time and record.timestamp > end_time:
                    continue

                if path_pattern:
                    import fnmatch

                    if not fnmatch.fnmatch(record.path, path_pattern):
                        continue

                result.append(record)

            return result

        except Exception as e:
            logger.error(f"Failed to query audit records: {e}")
            return []

    async def close(self) -> None:
        """Close database connection."""
        pass
