"""Unit tests for MCP protocol implementation."""

import asyncio
import json
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.mcp_server.errors import MCPError, MCPErrorCode
from kailash.mcp_server.protocol import (
    CancellationManager,
    CompletionManager,
    MessageType,
    MetaData,
    ProgressManager,
    ProgressToken,
    ProtocolManager,
    RootsManager,
    SamplingManager,
    get_protocol_manager,
)


class TestProgressManager:
    """Test progress notification management."""

    def setup_method(self):
        """Set up test environment."""
        self.progress_manager = ProgressManager()

    def test_start_progress(self):
        """Test starting progress tracking."""
        token = self.progress_manager.start_progress("test_operation")

        assert isinstance(token, ProgressToken)
        assert token.value.startswith("progress_")
        assert token.operation_name == "test_operation"
        assert token in self.progress_manager._active_progress

    def test_start_progress_with_total(self):
        """Test starting progress with total value."""
        token = self.progress_manager.start_progress("test_operation", total=100)

        assert token.total == 100
        assert token.progress == 0

    @pytest.mark.asyncio
    async def test_update_progress(self):
        """Test updating progress."""
        token = self.progress_manager.start_progress("test_operation", total=100)

        await self.progress_manager.update_progress(token, progress=50)

        assert token.progress == 50

    @pytest.mark.asyncio
    async def test_update_progress_with_increment(self):
        """Test updating progress with increment."""
        token = self.progress_manager.start_progress("test_operation", total=100)

        await self.progress_manager.update_progress(token, increment=25)
        assert token.progress == 25

        await self.progress_manager.update_progress(token, increment=25)
        assert token.progress == 50

    @pytest.mark.asyncio
    async def test_complete_progress(self):
        """Test completing progress."""
        token = self.progress_manager.start_progress("test_operation")

        await self.progress_manager.complete_progress(token, "completed successfully")

        assert token not in self.progress_manager._active_progress
        assert token.status == "completed successfully"

    def test_invalid_token_operations(self):
        """Test operations with invalid tokens."""
        fake_token = ProgressToken("fake_token", "fake_operation")

        # Should not raise but should handle gracefully
        assert (
            asyncio.run(self.progress_manager.update_progress(fake_token, progress=50))
            is None
        )

    def test_get_active_progress(self):
        """Test getting active progress tokens."""
        token1 = self.progress_manager.start_progress("op1")
        token2 = self.progress_manager.start_progress("op2")

        active = self.progress_manager.get_active_progress()
        assert len(active) == 2
        assert token1 in active
        assert token2 in active


class TestCancellationManager:
    """Test request cancellation management."""

    def setup_method(self):
        """Set up test environment."""
        self.cancellation_manager = CancellationManager()

    @pytest.mark.asyncio
    async def test_cancel_request(self):
        """Test cancelling a request."""
        request_id = "test_request_123"

        await self.cancellation_manager.cancel_request(request_id, "User cancelled")

        assert self.cancellation_manager.is_cancelled(request_id)
        assert (
            self.cancellation_manager.get_cancellation_reason(request_id)
            == "User cancelled"
        )

    def test_is_cancelled_false_for_active_request(self):
        """Test that active requests are not cancelled."""
        request_id = "active_request_123"

        assert not self.cancellation_manager.is_cancelled(request_id)

    @pytest.mark.asyncio
    async def test_add_cleanup_function(self):
        """Test adding cleanup functions."""
        request_id = "test_request_123"
        cleanup_called = False

        def cleanup():
            nonlocal cleanup_called
            cleanup_called = True

        self.cancellation_manager.add_cleanup_function(request_id, cleanup)
        await self.cancellation_manager.cancel_request(request_id, "Test cancellation")

        # Cleanup should be called when request is cancelled
        assert cleanup_called

    @pytest.mark.asyncio
    async def test_async_cleanup_function(self):
        """Test async cleanup functions."""
        request_id = "test_request_123"
        cleanup_called = False

        async def async_cleanup():
            nonlocal cleanup_called
            await asyncio.sleep(0.01)  # Simulate async work
            cleanup_called = True

        self.cancellation_manager.add_cleanup_function(request_id, async_cleanup)
        await self.cancellation_manager.cancel_request(request_id, "Test cancellation")

        # Async cleanup should be called directly
        assert cleanup_called

    @pytest.mark.asyncio
    async def test_multiple_cleanup_functions(self):
        """Test multiple cleanup functions for one request."""
        request_id = "test_request_123"
        cleanup_count = 0

        def cleanup1():
            nonlocal cleanup_count
            cleanup_count += 1

        def cleanup2():
            nonlocal cleanup_count
            cleanup_count += 1

        self.cancellation_manager.add_cleanup_function(request_id, cleanup1)
        self.cancellation_manager.add_cleanup_function(request_id, cleanup2)
        await self.cancellation_manager.cancel_request(request_id, "Test cancellation")

        assert cleanup_count == 2


class TestCompletionManager:
    """Test completion system management."""

    def setup_method(self):
        """Set up test environment."""
        self.completion_manager = CompletionManager()

    @pytest.mark.asyncio
    async def test_get_completions_tools(self):
        """Test getting tool completions."""
        # Mock available tools
        tools = [
            {"name": "search", "description": "Search for information"},
            {"name": "calculate", "description": "Perform calculations"},
        ]

        with patch.object(
            self.completion_manager, "_get_available_tools", return_value=tools
        ):
            completions = await self.completion_manager.get_completions(
                completion_type="tools", prefix="sea"
            )

            assert len(completions) == 1
            assert completions[0]["name"] == "search"

    @pytest.mark.asyncio
    async def test_get_completions_resources(self):
        """Test getting resource completions."""
        # Mock available resources
        resources = [
            {"uri": "file://documents/report.pdf", "name": "Report"},
            {"uri": "file://data/dataset.csv", "name": "Dataset"},
        ]

        with patch.object(
            self.completion_manager, "_get_available_resources", return_value=resources
        ):
            completions = await self.completion_manager.get_completions(
                completion_type="resources", prefix="file://data"
            )

            assert len(completions) == 1
            assert completions[0]["uri"] == "file://data/dataset.csv"

    @pytest.mark.asyncio
    async def test_get_completions_invalid_type(self):
        """Test getting completions for invalid type."""
        completions = await self.completion_manager.get_completions(
            completion_type="invalid", prefix="test"
        )

        assert completions == []


class TestSamplingManager:
    """Test sampling system management."""

    def setup_method(self):
        """Set up test environment."""
        self.sampling_manager = SamplingManager()

    @pytest.mark.asyncio
    async def test_create_message_sample(self):
        """Test creating a message sample."""
        messages = [
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
        ]

        sample = await self.sampling_manager.create_message_sample(
            messages=messages, model_preferences={"temperature": 0.7, "max_tokens": 100}
        )

        assert sample["messages"] == messages
        assert sample["model_preferences"]["temperature"] == 0.7
        assert "sample_id" in sample
        assert "timestamp" in sample

    @pytest.mark.asyncio
    async def test_create_message_sample_with_metadata(self):
        """Test creating a message sample with metadata."""
        messages = [{"role": "user", "content": "Test message"}]
        metadata = {"session_id": "test_session", "user_id": "test_user"}

        sample = await self.sampling_manager.create_message_sample(
            messages=messages, metadata=metadata
        )

        assert sample["metadata"] == metadata

    def test_get_sample_history(self):
        """Test getting sample history."""
        # Create some samples first
        for i in range(3):
            asyncio.run(
                self.sampling_manager.create_message_sample(
                    messages=[{"role": "user", "content": f"Message {i}"}]
                )
            )

        history = self.sampling_manager.get_sample_history(limit=2)
        assert len(history) == 2

    def test_clear_sample_history(self):
        """Test clearing sample history."""
        # Create a sample
        asyncio.run(
            self.sampling_manager.create_message_sample(
                messages=[{"role": "user", "content": "Test message"}]
            )
        )

        assert len(self.sampling_manager._samples) == 1

        self.sampling_manager.clear_sample_history()
        assert len(self.sampling_manager._samples) == 0


class TestRootsManager:
    """Test roots system management."""

    def setup_method(self):
        """Set up test environment."""
        self.roots_manager = RootsManager()

    def test_add_root(self):
        """Test adding a root."""
        root_info = {
            "uri": "file:///workspace",
            "name": "Workspace",
            "description": "Main workspace directory",
        }

        self.roots_manager.add_root(**root_info)

        roots = self.roots_manager.list_roots()
        assert len(roots) == 1
        assert roots[0]["uri"] == "file:///workspace"
        assert roots[0]["name"] == "Workspace"

    def test_remove_root(self):
        """Test removing a root."""
        self.roots_manager.add_root("file:///workspace", "Workspace")
        self.roots_manager.add_root("file:///temp", "Temp")

        assert len(self.roots_manager.list_roots()) == 2

        removed = self.roots_manager.remove_root("file:///workspace")
        assert removed is True
        assert len(self.roots_manager.list_roots()) == 1

    def test_remove_nonexistent_root(self):
        """Test removing a root that doesn't exist."""
        removed = self.roots_manager.remove_root("file:///nonexistent")
        assert removed is False

    def test_find_root_for_uri(self):
        """Test finding the appropriate root for a URI."""
        self.roots_manager.add_root("file:///workspace", "Workspace")
        self.roots_manager.add_root("file:///temp", "Temp")

        root = self.roots_manager.find_root_for_uri(
            "file:///workspace/project/file.txt"
        )
        assert root is not None
        assert root["uri"] == "file:///workspace"

        root = self.roots_manager.find_root_for_uri("file:///other/file.txt")
        assert root is None


class TestProtocolManager:
    """Test overall protocol management."""

    def setup_method(self):
        """Set up test environment."""
        self.protocol_manager = ProtocolManager()

    def test_initialization(self):
        """Test protocol manager initialization."""
        assert self.protocol_manager.progress is not None
        assert self.protocol_manager.cancellation is not None
        assert self.protocol_manager.completion is not None
        assert self.protocol_manager.sampling is not None
        assert self.protocol_manager.roots is not None

    @pytest.mark.asyncio
    async def test_handle_request_with_progress(self):
        """Test handling a request with progress tracking."""

        async def mock_handler(request):
            # Simulate progress updates
            token = self.protocol_manager.progress.start_progress(
                "test_operation", total=100
            )
            await self.protocol_manager.progress.update_progress(token, progress=50)
            await self.protocol_manager.progress.complete_progress(token, "completed")
            return {"result": "success"}

        request = {"method": "test", "params": {}, "id": "123"}

        with patch.object(
            self.protocol_manager, "_get_handler", return_value=mock_handler
        ):
            response = await self.protocol_manager.handle_request(request)

            assert response["result"]["result"] == "success"

    @pytest.mark.asyncio
    async def test_handle_request_with_cancellation(self):
        """Test handling a request that gets cancelled."""
        request_id = "test_request_123"

        async def mock_handler(request):
            # Simulate long operation that checks for cancellation
            for i in range(10):
                if self.protocol_manager.cancellation.is_cancelled(request_id):
                    raise MCPError(
                        "Operation cancelled", error_code=MCPErrorCode.REQUEST_CANCELLED
                    )
                await asyncio.sleep(0.01)
            return {"result": "completed"}

        request = {"method": "test", "params": {}, "id": request_id}

        # Cancel the request partway through
        async def cancel_after_delay():
            await asyncio.sleep(0.05)
            await self.protocol_manager.cancellation.cancel_request(
                request_id, "User cancelled"
            )

        with patch.object(
            self.protocol_manager, "_get_handler", return_value=mock_handler
        ):
            # Start both the request and the cancellation
            request_task = asyncio.create_task(
                self.protocol_manager.handle_request(request)
            )
            cancel_task = asyncio.create_task(cancel_after_delay())

            # Wait for both to complete
            await cancel_task

            with pytest.raises(MCPError) as exc_info:
                await request_task

            assert exc_info.value.error_code == MCPErrorCode.REQUEST_CANCELLED

    def test_validate_message_type(self):
        """Test message type validation."""
        valid_message = {"jsonrpc": "2.0", "method": "test", "params": {}, "id": "123"}

        msg_type = self.protocol_manager.validate_message_type(valid_message)
        assert msg_type == MessageType.REQUEST

        # Test notification (no id)
        notification = {"jsonrpc": "2.0", "method": "test", "params": {}}

        msg_type = self.protocol_manager.validate_message_type(notification)
        assert msg_type == MessageType.NOTIFICATION

    def test_validate_message_type_invalid(self):
        """Test message type validation with invalid message."""
        invalid_message = {"invalid": "message"}

        with pytest.raises(MCPError) as exc_info:
            self.protocol_manager.validate_message_type(invalid_message)

        assert exc_info.value.error_code == MCPErrorCode.INVALID_REQUEST


class TestConvenienceFunctions:
    """Test convenience functions for protocol operations."""

    def test_get_protocol_manager_singleton(self):
        """Test that get_protocol_manager returns singleton."""
        manager1 = get_protocol_manager()
        manager2 = get_protocol_manager()

        assert manager1 is manager2
        assert isinstance(manager1, ProtocolManager)

    def test_start_progress_convenience(self):
        """Test start_progress convenience function."""
        from kailash.mcp_server.protocol import start_progress

        token = start_progress("test_operation", total=100)
        assert isinstance(token, ProgressToken)
        assert token.operation_name == "test_operation"
        assert token.total == 100

    @pytest.mark.asyncio
    async def test_update_progress_convenience(self):
        """Test update_progress convenience function."""
        from kailash.mcp_server.protocol import start_progress, update_progress

        token = start_progress("test_operation", total=100)
        await update_progress(token, progress=50)
        assert token.progress == 50

    @pytest.mark.asyncio
    async def test_is_cancelled_convenience(self):
        """Test is_cancelled convenience function."""
        from kailash.mcp_server.protocol import cancel_request, is_cancelled

        request_id = "test_request_123"
        assert not is_cancelled(request_id)

        await cancel_request(request_id, "Test cancellation")
        assert is_cancelled(request_id)


class TestMetaData:
    """Test MetaData dataclass."""

    def test_metadata_creation(self):
        """Test creating metadata."""
        metadata = MetaData(
            operation_id="op_123",
            timestamp=time.time(),
            user_id="user_123",
            additional_data={"key": "value"},
        )

        assert metadata.operation_id == "op_123"
        assert metadata.user_id == "user_123"
        assert metadata.additional_data["key"] == "value"

    def test_metadata_to_dict(self):
        """Test converting metadata to dict."""
        metadata = MetaData(operation_id="op_123", user_id="user_123")

        data = metadata.to_dict()
        assert data["operation_id"] == "op_123"
        assert data["user_id"] == "user_123"
        assert "timestamp" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
