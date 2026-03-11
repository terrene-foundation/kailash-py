"""Structured JSON logging backend (TODO-310F).

Default audit backend that writes records as JSON to Python's logging system.
"""

import json
import logging

from nexus.auth.audit.backends.base import AuditBackend
from nexus.auth.audit.record import AuditRecord


class LoggingBackend(AuditBackend):
    """Structured JSON logging backend.

    Writes audit records as JSON to Python's logging system.
    Default backend - requires no additional infrastructure.
    """

    def __init__(
        self,
        logger_name: str = "nexus.audit",
        log_level: str = "INFO",
    ):
        """Initialize logging backend.

        Args:
            logger_name: Logger name (default: "nexus.audit")
            log_level: Log level (default: "INFO")
        """
        self._logger = logging.getLogger(logger_name)
        self._level = getattr(logging, log_level.upper(), logging.INFO)

    async def store(self, record: AuditRecord) -> None:
        """Store record by logging as JSON.

        Logs at ERROR for 5xx, WARNING for 4xx, configured level otherwise.
        """
        log_data = record.to_dict()
        log_message = json.dumps(log_data)

        if record.status_code >= 500:
            self._logger.error(log_message)
        elif record.status_code >= 400:
            self._logger.warning(log_message)
        else:
            self._logger.log(self._level, log_message)
