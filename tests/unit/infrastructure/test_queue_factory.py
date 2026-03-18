# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for queue_factory.create_task_queue().

Tests cover auto-detection from KAILASH_QUEUE_URL, explicit URL handling,
and error cases for unsupported schemes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from kailash.infrastructure.queue_factory import create_task_queue


@pytest.mark.asyncio
class TestNoUrlConfigured:
    async def test_no_url_returns_none(self):
        """When no URL is passed and env var is unset, returns None."""
        with patch(
            "kailash.infrastructure.queue_factory.resolve_queue_url", return_value=None
        ):
            result = await create_task_queue()
            assert result is None

    async def test_empty_string_url_returns_none(self):
        """When an empty string is explicitly passed, resolve_queue_url returns None."""
        with patch(
            "kailash.infrastructure.queue_factory.resolve_queue_url", return_value=None
        ):
            result = await create_task_queue(queue_url=None)
            assert result is None


@pytest.mark.asyncio
class TestSqliteUrl:
    async def test_sqlite_memory_returns_sql_task_queue(self):
        """sqlite:///:memory: URL creates a real SQLTaskQueue."""
        from kailash.infrastructure.task_queue import SQLTaskQueue

        queue = await create_task_queue("sqlite:///:memory:")
        assert queue is not None
        assert isinstance(queue, SQLTaskQueue)

    async def test_sqlite_memory_queue_is_functional(self):
        """The returned SQLTaskQueue from sqlite:///:memory: can enqueue and dequeue."""
        queue = await create_task_queue("sqlite:///:memory:")

        tid = await queue.enqueue({"job": "test"}, task_id="factory-task-1")
        assert tid == "factory-task-1"

        msg = await queue.dequeue(worker_id="w1")
        assert msg is not None
        assert msg.task_id == "factory-task-1"
        assert msg.payload == {"job": "test"}

    async def test_sqlite_file_url_returns_sql_task_queue(self, tmp_path):
        """sqlite:///path/to/file.db URL creates a SQLTaskQueue."""
        from kailash.infrastructure.task_queue import SQLTaskQueue

        db_path = tmp_path / "test_queue.db"
        url = f"sqlite:///{db_path}"
        queue = await create_task_queue(url)
        assert queue is not None
        assert isinstance(queue, SQLTaskQueue)


@pytest.mark.asyncio
class TestRedisUrl:
    async def test_redis_url_creates_redis_task_queue(self):
        """redis://localhost:6379 URL attempts to create a Redis TaskQueue.

        We mock the import of kailash.runtime.distributed.TaskQueue since
        Redis may not be installed in the test environment.
        """
        mock_task_queue_cls = MagicMock()
        mock_task_queue_instance = MagicMock()
        mock_task_queue_cls.return_value = mock_task_queue_instance

        with patch.dict(
            "sys.modules",
            {"kailash.runtime.distributed": MagicMock(TaskQueue=mock_task_queue_cls)},
        ):
            # Re-import to pick up the mocked module
            import importlib

            import kailash.infrastructure.queue_factory as qf_mod

            importlib.reload(qf_mod)

            result = await qf_mod.create_task_queue("redis://localhost:6379/0")

            assert result is mock_task_queue_instance
            mock_task_queue_cls.assert_called_once_with(
                redis_url="redis://localhost:6379/0"
            )

            # Restore the original module
            importlib.reload(qf_mod)

    async def test_rediss_url_creates_redis_task_queue(self):
        """rediss:// (TLS) URL also routes to Redis TaskQueue."""
        mock_task_queue_cls = MagicMock()
        mock_task_queue_instance = MagicMock()
        mock_task_queue_cls.return_value = mock_task_queue_instance

        with patch.dict(
            "sys.modules",
            {"kailash.runtime.distributed": MagicMock(TaskQueue=mock_task_queue_cls)},
        ):
            import importlib

            import kailash.infrastructure.queue_factory as qf_mod

            importlib.reload(qf_mod)

            result = await qf_mod.create_task_queue("rediss://redis.example.com:6380/0")

            assert result is mock_task_queue_instance
            mock_task_queue_cls.assert_called_once_with(
                redis_url="rediss://redis.example.com:6380/0"
            )

            importlib.reload(qf_mod)


@pytest.mark.asyncio
class TestUnknownScheme:
    async def test_unknown_scheme_raises_value_error(self):
        """An unrecognized URL scheme raises ValueError with a descriptive message."""
        with pytest.raises(ValueError, match="Unsupported queue URL scheme 'ftp'"):
            await create_task_queue("ftp://some-server/queue")

    async def test_unknown_scheme_amqp_raises_value_error(self):
        """AMQP is not a supported scheme."""
        with pytest.raises(ValueError, match="Unsupported queue URL scheme 'amqp'"):
            await create_task_queue("amqp://rabbitmq:5672")


@pytest.mark.asyncio
class TestPlainFilePath:
    async def test_absolute_file_path_returns_sql_task_queue(self, tmp_path):
        """A plain absolute file path (no scheme) is treated as SQLite."""
        from kailash.infrastructure.task_queue import SQLTaskQueue

        db_path = str(tmp_path / "queue_from_path.db")
        queue = await create_task_queue(db_path)
        assert queue is not None
        assert isinstance(queue, SQLTaskQueue)

    async def test_relative_file_path_returns_sql_task_queue(
        self, tmp_path, monkeypatch
    ):
        """A relative file path like ./queue.db is treated as SQLite."""
        from kailash.infrastructure.task_queue import SQLTaskQueue

        monkeypatch.chdir(tmp_path)
        queue = await create_task_queue("./queue_relative.db")
        assert queue is not None
        assert isinstance(queue, SQLTaskQueue)


@pytest.mark.asyncio
class TestEnvVarAutoDetection:
    async def test_env_var_sqlite_auto_detection(self, monkeypatch):
        """KAILASH_QUEUE_URL env var is used when no explicit URL is given."""
        from kailash.infrastructure.task_queue import SQLTaskQueue

        monkeypatch.setenv("KAILASH_QUEUE_URL", "sqlite:///:memory:")
        queue = await create_task_queue()
        assert queue is not None
        assert isinstance(queue, SQLTaskQueue)

    async def test_env_var_unset_returns_none(self, monkeypatch):
        """When KAILASH_QUEUE_URL is not set, factory returns None."""
        monkeypatch.delenv("KAILASH_QUEUE_URL", raising=False)
        result = await create_task_queue()
        assert result is None

    async def test_env_var_empty_string_returns_none(self, monkeypatch):
        """When KAILASH_QUEUE_URL is set to empty string, factory returns None."""
        monkeypatch.setenv("KAILASH_QUEUE_URL", "")
        result = await create_task_queue()
        assert result is None

    async def test_explicit_url_overrides_env_var(self, monkeypatch):
        """An explicit URL parameter takes precedence over the env var."""
        from kailash.infrastructure.task_queue import SQLTaskQueue

        monkeypatch.setenv("KAILASH_QUEUE_URL", "ftp://should-not-be-used")
        queue = await create_task_queue("sqlite:///:memory:")
        assert queue is not None
        assert isinstance(queue, SQLTaskQueue)
