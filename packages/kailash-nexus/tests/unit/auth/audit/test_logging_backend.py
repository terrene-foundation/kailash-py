"""Unit tests for LoggingBackend (TODO-310F).

Tier 1 tests - mocking allowed.
"""

import json
import logging

import pytest
from nexus.auth.audit.backends.logging import LoggingBackend
from nexus.auth.audit.record import AuditRecord

# =============================================================================
# Tests: LoggingBackend Store
# =============================================================================


class TestLoggingBackendStore:
    """Test LoggingBackend storage."""

    @pytest.mark.asyncio
    async def test_store_record(self, caplog):
        """Store record writes to logger."""
        backend = LoggingBackend(logger_name="test.audit", log_level="INFO")

        record = AuditRecord.create(
            method="GET",
            path="/api/test",
            status_code=200,
            duration_ms=10.0,
            ip_address="127.0.0.1",
        )

        with caplog.at_level(logging.INFO, logger="test.audit"):
            await backend.store(record)

        assert len(caplog.records) == 1
        assert "/api/test" in caplog.records[0].message

    @pytest.mark.asyncio
    async def test_store_as_json(self, caplog):
        """Record stored as JSON string."""
        backend = LoggingBackend(logger_name="test.audit", log_level="INFO")

        record = AuditRecord.create(
            method="POST",
            path="/api/users",
            status_code=201,
            duration_ms=45.0,
            ip_address="192.168.1.1",
        )

        with caplog.at_level(logging.INFO, logger="test.audit"):
            await backend.store(record)

        # Verify message is valid JSON
        log_message = caplog.records[0].message
        parsed = json.loads(log_message)
        assert parsed["method"] == "POST"
        assert parsed["path"] == "/api/users"

    @pytest.mark.asyncio
    async def test_5xx_logged_at_error(self, caplog):
        """5xx responses logged at ERROR level."""
        backend = LoggingBackend(logger_name="test.audit")

        record = AuditRecord.create(
            method="GET",
            path="/api/error",
            status_code=500,
            duration_ms=100.0,
            ip_address="127.0.0.1",
        )

        with caplog.at_level(logging.ERROR, logger="test.audit"):
            await backend.store(record)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.ERROR

    @pytest.mark.asyncio
    async def test_4xx_logged_at_warning(self, caplog):
        """4xx responses logged at WARNING level."""
        backend = LoggingBackend(logger_name="test.audit")

        record = AuditRecord.create(
            method="GET",
            path="/api/notfound",
            status_code=404,
            duration_ms=5.0,
            ip_address="127.0.0.1",
        )

        with caplog.at_level(logging.WARNING, logger="test.audit"):
            await backend.store(record)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.WARNING

    @pytest.mark.asyncio
    async def test_2xx_logged_at_configured_level(self, caplog):
        """2xx responses logged at configured level."""
        backend = LoggingBackend(logger_name="test.audit", log_level="DEBUG")

        record = AuditRecord.create(
            method="GET",
            path="/api/ok",
            status_code=200,
            duration_ms=5.0,
            ip_address="127.0.0.1",
        )

        with caplog.at_level(logging.DEBUG, logger="test.audit"):
            await backend.store(record)

        assert len(caplog.records) == 1
        assert caplog.records[0].levelno == logging.DEBUG


# =============================================================================
# Tests: LoggingBackend Init
# =============================================================================


class TestLoggingBackendInit:
    """Test LoggingBackend initialization."""

    def test_default_logger_name(self):
        """Default logger name is nexus.audit."""
        backend = LoggingBackend()
        assert backend._logger.name == "nexus.audit"

    def test_custom_logger_name(self):
        """Custom logger name used."""
        backend = LoggingBackend(logger_name="custom.audit")
        assert backend._logger.name == "custom.audit"

    def test_default_log_level(self):
        """Default log level is INFO."""
        backend = LoggingBackend()
        assert backend._level == logging.INFO

    def test_custom_log_level(self):
        """Custom log level parsed correctly."""
        backend = LoggingBackend(log_level="DEBUG")
        assert backend._level == logging.DEBUG


# =============================================================================
# Tests: Query Not Supported
# =============================================================================


class TestLoggingBackendQuery:
    """Test query raises NotImplementedError."""

    @pytest.mark.asyncio
    async def test_query_not_supported(self):
        """Query raises NotImplementedError."""
        backend = LoggingBackend()
        with pytest.raises(NotImplementedError, match="Query not supported"):
            await backend.query()

    @pytest.mark.asyncio
    async def test_close_is_noop(self):
        """Close is a no-op."""
        backend = LoggingBackend()
        await backend.close()  # Should not raise
