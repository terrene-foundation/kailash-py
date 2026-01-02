"""Unit tests for MCP advanced features."""

import asyncio
import base64
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from kailash.mcp_server.advanced_features import (
    BinaryResourceHandler,
    CancellationContext,
    Content,
    ContentType,
    ElicitationSystem,
    MultiModalContent,
    ProgressReporter,
    ResourceChange,
    ResourceTemplate,
    SchemaValidator,
    StreamingHandler,
    StructuredTool,
    ToolAnnotation,
    create_cancellation_context,
    create_progress_reporter,
    structured_tool,
)
from kailash.mcp_server.errors import MCPError, MCPErrorCode, ValidationError


class TestContent:
    """Test multi-modal content representation."""

    def test_text_content(self):
        """Test text content creation and serialization."""
        content = Content(
            type=ContentType.TEXT, data="Hello, world!", annotations={"language": "en"}
        )

        result = content.to_dict()

        assert result["type"] == "text"
        assert result["text"] == "Hello, world!"
        assert result["annotations"]["language"] == "en"

    def test_image_content(self):
        """Test image content creation and serialization."""
        content = Content(
            type=ContentType.IMAGE, data="base64encodeddata", mime_type="image/png"
        )

        result = content.to_dict()

        assert result["type"] == "image"
        assert result["data"] == "base64encodeddata"
        assert result["mimeType"] == "image/png"

    def test_resource_content(self):
        """Test resource content creation and serialization."""
        content = Content(
            type=ContentType.RESOURCE,
            data={"uri": "file://document.pdf", "text": "Document"},
        )

        result = content.to_dict()

        assert result["type"] == "resource"
        assert result["resource"]["uri"] == "file://document.pdf"
        assert result["resource"]["text"] == "Document"

    def test_annotation_content(self):
        """Test annotation content creation and serialization."""
        content = Content(
            type=ContentType.ANNOTATION,
            data={"type": "highlight", "data": {"start": 0, "end": 10}},
        )

        result = content.to_dict()

        assert result["type"] == "annotation"
        assert result["annotation"]["type"] == "highlight"


class TestResourceChange:
    """Test resource change notifications."""

    def test_resource_change_creation(self):
        """Test creating resource change notification."""
        from kailash.mcp_server.advanced_features import ChangeType

        change = ResourceChange(
            uri="file://document.pdf",
            change_type=ChangeType.UPDATED,
            content={"size": 1024},
            metadata={"user": "alice"},
        )

        assert change.uri == "file://document.pdf"
        assert change.change_type == ChangeType.UPDATED
        assert change.content["size"] == 1024
        assert change.metadata["user"] == "alice"

    def test_resource_change_to_dict(self):
        """Test converting resource change to dictionary."""
        from kailash.mcp_server.advanced_features import ChangeType

        change = ResourceChange(
            uri="file://document.pdf", change_type=ChangeType.CREATED
        )

        result = change.to_dict()

        assert result["uri"] == "file://document.pdf"
        assert result["type"] == "created"
        assert "timestamp" in result


class TestToolAnnotation:
    """Test tool annotation metadata."""

    def test_tool_annotation_defaults(self):
        """Test tool annotation with defaults."""
        annotation = ToolAnnotation()

        assert annotation.is_read_only is False
        assert annotation.is_destructive is False
        assert annotation.is_idempotent is True
        assert annotation.security_level == "normal"

    def test_tool_annotation_custom(self):
        """Test tool annotation with custom values."""
        annotation = ToolAnnotation(
            is_read_only=True,
            is_destructive=True,
            estimated_duration=30.0,
            security_level="admin",
            rate_limit={"requests": 10, "window": 60},
        )

        assert annotation.is_read_only is True
        assert annotation.is_destructive is True
        assert annotation.estimated_duration == 30.0
        assert annotation.security_level == "admin"
        assert annotation.rate_limit["requests"] == 10

    def test_tool_annotation_to_dict(self):
        """Test converting tool annotation to dictionary."""
        annotation = ToolAnnotation(is_read_only=True, estimated_duration=15.5)

        result = annotation.to_dict()

        assert result["is_read_only"] is True
        assert result["estimated_duration"] == 15.5
        assert result["is_destructive"] is False


class TestMultiModalContent:
    """Test multi-modal content container."""

    def setup_method(self):
        """Set up test environment."""
        self.content = MultiModalContent()

    def test_empty_content(self):
        """Test empty content container."""
        assert self.content.is_empty() is True
        assert self.content.to_list() == []

    def test_add_text(self):
        """Test adding text content."""
        self.content.add_text("Hello, world!", annotations={"language": "en"})

        result = self.content.to_list()

        assert len(result) == 1
        assert result[0]["type"] == "text"
        assert result[0]["text"] == "Hello, world!"
        assert result[0]["annotations"]["language"] == "en"

    def test_add_image_bytes(self):
        """Test adding image from bytes."""
        image_bytes = b"fake image data"

        self.content.add_image(image_bytes, "image/png")

        result = self.content.to_list()

        assert len(result) == 1
        assert result[0]["type"] == "image"
        assert result[0]["mimeType"] == "image/png"
        # Should be base64 encoded
        assert result[0]["data"] == base64.b64encode(image_bytes).decode()

    def test_add_image_base64(self):
        """Test adding image from base64 string."""
        base64_data = "dGVzdCBpbWFnZSBkYXRh"  # "test image data" in base64

        self.content.add_image(base64_data, "image/jpeg")

        result = self.content.to_list()

        assert len(result) == 1
        assert result[0]["data"] == base64_data

    def test_add_audio(self):
        """Test adding audio content."""
        audio_bytes = b"fake audio data"

        self.content.add_audio(audio_bytes, "audio/mp3")

        result = self.content.to_list()

        assert len(result) == 1
        assert result[0]["type"] == "audio"
        assert result[0]["mimeType"] == "audio/mp3"

    def test_add_resource(self):
        """Test adding resource reference."""
        self.content.add_resource(
            uri="file://document.pdf",
            text="Important document",
            mime_type="application/pdf",
        )

        result = self.content.to_list()

        assert len(result) == 1
        assert result[0]["type"] == "resource"
        assert result[0]["resource"]["uri"] == "file://document.pdf"
        assert result[0]["resource"]["text"] == "Important document"
        assert result[0]["resource"]["mimeType"] == "application/pdf"

    def test_add_annotation(self):
        """Test adding annotation content."""
        self.content.add_annotation(
            annotation_type="highlight", data={"start": 0, "end": 10, "color": "yellow"}
        )

        result = self.content.to_list()

        assert len(result) == 1
        assert result[0]["type"] == "annotation"
        assert result[0]["annotation"]["type"] == "highlight"
        assert result[0]["annotation"]["data"]["color"] == "yellow"

    def test_mixed_content(self):
        """Test adding multiple types of content."""
        self.content.add_text("Introduction")
        self.content.add_image(b"image data", "image/png")
        self.content.add_resource("file://data.csv")

        result = self.content.to_list()

        assert len(result) == 3
        assert result[0]["type"] == "text"
        assert result[1]["type"] == "image"
        assert result[2]["type"] == "resource"
        assert not self.content.is_empty()


class TestSchemaValidator:
    """Test JSON Schema validation."""

    def test_valid_schema_validation(self):
        """Test validation with valid data."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        }

        validator = SchemaValidator(schema)

        # Valid data should not raise
        validator.validate({"name": "Alice", "age": 30})

    def test_invalid_schema_validation(self):
        """Test validation with invalid data."""
        schema = {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "minimum": 0},
            },
            "required": ["name"],
        }

        validator = SchemaValidator(schema)

        # Missing required field
        with pytest.raises(ValidationError):
            validator.validate({"age": 30})

        # Wrong type
        with pytest.raises(ValidationError):
            validator.validate({"name": 123})

    def test_is_valid_method(self):
        """Test is_valid convenience method."""
        schema = {"type": "object", "properties": {"value": {"type": "number"}}}

        validator = SchemaValidator(schema)

        assert validator.is_valid({"value": 42}) is True
        assert validator.is_valid({"value": "not a number"}) is False

    def test_complex_schema_validation(self):
        """Test validation with complex nested schema."""
        schema = {
            "type": "object",
            "properties": {
                "user": {
                    "type": "object",
                    "properties": {
                        "profile": {
                            "type": "object",
                            "properties": {
                                "settings": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                }
                            },
                        }
                    },
                }
            },
        }

        validator = SchemaValidator(schema)

        valid_data = {"user": {"profile": {"settings": ["theme:dark", "lang:en"]}}}

        validator.validate(valid_data)  # Should not raise


class TestStructuredTool:
    """Test structured tool with validation."""

    def test_structured_tool_decorator(self):
        """Test using structured tool as decorator."""
        input_schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

        output_schema = {
            "type": "object",
            "properties": {"results": {"type": "array"}},
            "required": ["results"],
        }

        tool = StructuredTool(input_schema, output_schema)

        @tool
        def search_function(query: str):
            return {"results": [f"Result for {query}"]}

        # Valid input should work
        result = search_function(query="test")
        assert result["results"] == ["Result for test"]

    def test_structured_tool_input_validation_error(self):
        """Test input validation error."""
        input_schema = {
            "type": "object",
            "properties": {"number": {"type": "integer"}},
            "required": ["number"],
        }

        tool = StructuredTool(input_schema)

        @tool
        def calculate(number: int):
            return number * 2

        # Invalid input should raise MCPError
        with pytest.raises(MCPError) as exc_info:
            calculate(number="not a number")

        assert exc_info.value.error_code == MCPErrorCode.INVALID_PARAMS

    def test_structured_tool_output_validation_error(self):
        """Test output validation error."""
        output_schema = {
            "type": "object",
            "properties": {"result": {"type": "string"}},
            "required": ["result"],
        }

        tool = StructuredTool(output_schema=output_schema)

        @tool
        def bad_function():
            return {"result": 123}  # Should be string

        with pytest.raises(MCPError) as exc_info:
            bad_function()

        assert exc_info.value.error_code == MCPErrorCode.INTERNAL_ERROR

    @pytest.mark.asyncio
    async def test_structured_tool_async_function(self):
        """Test structured tool with async function."""
        input_schema = {"type": "object", "properties": {"delay": {"type": "number"}}}

        tool = StructuredTool(input_schema)

        @tool
        async def async_function(delay: float):
            await asyncio.sleep(delay)
            return {"completed": True}

        result = await async_function(delay=0.01)
        assert result["completed"] is True

    def test_structured_tool_with_annotations(self):
        """Test structured tool with annotations."""
        annotations = ToolAnnotation(
            is_read_only=True, estimated_duration=5.0, security_level="elevated"
        )

        tool = StructuredTool(annotations=annotations)

        assert tool.annotations.is_read_only is True
        assert tool.annotations.estimated_duration == 5.0
        assert tool.annotations.security_level == "elevated"

    @pytest.mark.asyncio
    async def test_structured_tool_with_progress(self):
        """Test structured tool with progress reporting."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_progress = MagicMock()
            mock_token = MagicMock()

            mock_manager.progress = mock_progress
            mock_progress.start_progress.return_value = mock_token
            mock_progress.complete_progress = AsyncMock()
            mock_protocol.return_value = mock_manager

            tool = StructuredTool(progress_reporting=True)

            @tool
            async def progress_function(progress_token=None):
                assert progress_token is mock_token
                return {"status": "completed"}

            result = await progress_function()

            assert result["status"] == "completed"
            mock_progress.start_progress.assert_called_once()
            mock_progress.complete_progress.assert_called_once()


class TestResourceTemplate:
    """Test resource template with URI patterns."""

    def setup_method(self):
        """Set up test environment."""
        self.template = ResourceTemplate(
            uri_template="files://{path}",
            name="File Access",
            description="Access files by path",
        )

    def test_template_initialization(self):
        """Test resource template initialization."""
        assert self.template.uri_template == "files://{path}"
        assert self.template.name == "File Access"
        assert self.template.description == "Access files by path"
        assert self.template.supports_subscription is True

    def test_matches_uri(self):
        """Test URI matching against template."""
        # Simple pattern matching (basic implementation)
        assert self.template.matches_uri("files://document.pdf") is True
        assert self.template.matches_uri("http://example.com") is False

    @pytest.mark.asyncio
    async def test_subscribe_to_resource(self):
        """Test subscribing to resource changes."""
        callback_called = False
        received_change = None

        def callback(change):
            nonlocal callback_called, received_change
            callback_called = True
            received_change = change

        subscription_id = await self.template.subscribe(
            "files://document.pdf", callback
        )

        assert subscription_id is not None
        assert len(subscription_id) > 0

    @pytest.mark.asyncio
    async def test_unsubscribe_from_resource(self):
        """Test unsubscribing from resource changes."""

        def callback(change):
            pass

        subscription_id = await self.template.subscribe(
            "files://document.pdf", callback
        )

        result = await self.template.unsubscribe(subscription_id)
        assert result is True

        # Try to unsubscribe again
        result = await self.template.unsubscribe(subscription_id)
        assert result is False

    @pytest.mark.asyncio
    async def test_notify_change(self):
        """Test notifying subscribers of changes."""
        from kailash.mcp_server.advanced_features import ChangeType

        callback_called = False
        received_change = None

        def callback(change):
            nonlocal callback_called, received_change
            callback_called = True
            received_change = change

        await self.template.subscribe("files://document.pdf", callback)

        change = ResourceChange(
            uri="files://document.pdf", change_type=ChangeType.UPDATED
        )

        await self.template.notify_change(change)

        assert callback_called is True
        assert received_change is change

    @pytest.mark.asyncio
    async def test_subscribe_unsupported_template(self):
        """Test subscribing to template that doesn't support subscriptions."""
        template = ResourceTemplate(
            uri_template="readonly://{path}", supports_subscription=False
        )

        with pytest.raises(MCPError) as exc_info:
            await template.subscribe("readonly://file.txt", lambda x: None)

        assert exc_info.value.error_code == MCPErrorCode.METHOD_NOT_FOUND

    def test_template_to_dict(self):
        """Test converting template to dictionary."""
        template = ResourceTemplate(
            uri_template="files://{path}",
            name="Files",
            description="File access",
            mime_type="application/octet-stream",
        )

        result = template.to_dict()

        assert result["uriTemplate"] == "files://{path}"
        assert result["name"] == "Files"
        assert result["description"] == "File access"
        assert result["mimeType"] == "application/octet-stream"


class TestBinaryResourceHandler:
    """Test binary resource handling."""

    def setup_method(self):
        """Set up test environment."""
        self.handler = BinaryResourceHandler(max_size=1024)

    def test_initialization(self):
        """Test binary resource handler initialization."""
        assert self.handler.max_size == 1024

    def test_decode_base64_content(self):
        """Test decoding base64 content."""
        test_data = b"Hello, world!"
        encoded = base64.b64encode(test_data).decode()

        decoded = self.handler.decode_base64_content(encoded)

        assert decoded == test_data

    def test_decode_invalid_base64(self):
        """Test decoding invalid base64 content."""
        with pytest.raises(MCPError) as exc_info:
            self.handler.decode_base64_content("invalid base64!")

        assert exc_info.value.error_code == MCPErrorCode.INVALID_PARAMS

    @pytest.mark.asyncio
    async def test_read_binary_file_not_found(self):
        """Test reading non-existent binary file."""
        with pytest.raises(MCPError) as exc_info:
            await self.handler.read_binary_file("/nonexistent/file.bin")

        assert exc_info.value.error_code == MCPErrorCode.RESOURCE_NOT_FOUND

    @pytest.mark.asyncio
    async def test_read_binary_file_too_large(self):
        """Test reading file that exceeds size limit."""
        # Mock a file that's too large
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.stat") as mock_stat:
                mock_stat.return_value.st_size = 2048  # Exceeds our 1024 limit

                with pytest.raises(MCPError) as exc_info:
                    await self.handler.read_binary_file("/fake/large/file.bin")

                assert exc_info.value.error_code == MCPErrorCode.INVALID_PARAMS


class TestStreamingHandler:
    """Test streaming response handler."""

    def setup_method(self):
        """Set up test environment."""
        self.handler = StreamingHandler(chunk_size=10)

    def test_initialization(self):
        """Test streaming handler initialization."""
        assert self.handler.chunk_size == 10

    @pytest.mark.asyncio
    async def test_stream_text(self):
        """Test streaming text content."""
        text = "Hello, world! This is a test."

        chunks = []
        async for chunk in self.handler.stream_text(text):
            chunks.append(chunk)

        # Should be split into chunks of 10 characters
        assert len(chunks) > 1
        assert "".join(chunks) == text

    @pytest.mark.asyncio
    async def test_stream_binary(self):
        """Test streaming binary content."""
        data = b"Hello, world! This is binary data."

        chunks = []
        async for chunk in self.handler.stream_binary(data):
            chunks.append(chunk)

        # Reconstruct the data
        reconstructed = b""
        for chunk in chunks:
            reconstructed += base64.b64decode(chunk)

        assert reconstructed == data


class TestElicitationSystem:
    """Test interactive user input system."""

    def setup_method(self):
        """Set up test environment."""
        self.elicitation = ElicitationSystem()

    @pytest.mark.asyncio
    async def test_request_input_with_test_prompt(self):
        """Test requesting input with test prompt (auto-response)."""
        # The implementation auto-responds to prompts starting with "test"
        result = await self.elicitation.request_input("test: What is your name?")

        assert result == "test response"

    @pytest.mark.asyncio
    async def test_request_input_timeout(self):
        """Test input request timeout."""
        with pytest.raises(MCPError) as exc_info:
            await self.elicitation.request_input(
                "Enter something:", timeout=0.1  # Very short timeout
            )

        assert exc_info.value.error_code == MCPErrorCode.REQUEST_TIMEOUT

    @pytest.mark.asyncio
    async def test_provide_input_manually(self):
        """Test providing input manually."""

        # Start a request in background
        async def background_request():
            return await self.elicitation.request_input(
                "Manual input test", timeout=1.0
            )

        task = asyncio.create_task(background_request())

        # Give it a moment to start
        await asyncio.sleep(0.1)

        # Find the pending request and provide input
        if self.elicitation._pending_requests:
            request_id = list(self.elicitation._pending_requests.keys())[0]
            success = await self.elicitation.provide_input(
                request_id, "manual response"
            )
            assert success is True

        result = await task
        assert result == "manual response"

    @pytest.mark.asyncio
    async def test_request_input_with_schema_validation(self):
        """Test input request with schema validation."""
        schema = {
            "type": "object",
            "properties": {"age": {"type": "integer", "minimum": 0}},
            "required": ["age"],
        }

        # Mock valid input
        with patch.object(self.elicitation, "_send_elicitation_request"):

            async def provide_valid_input():
                await asyncio.sleep(0.1)
                request_id = list(self.elicitation._pending_requests.keys())[0]
                await self.elicitation.provide_input(request_id, {"age": 25})

            task = asyncio.create_task(provide_valid_input())

            result = await self.elicitation.request_input(
                "Enter your age:", input_schema=schema, timeout=1.0
            )

            await task
            assert result["age"] == 25


class TestProgressReporter:
    """Test progress reporting system."""

    def test_progress_reporter_initialization(self):
        """Test progress reporter initialization."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_progress = MagicMock()
            mock_token = MagicMock()

            mock_manager.progress = mock_progress
            mock_progress.start_progress.return_value = mock_token
            mock_protocol.return_value = mock_manager

            reporter = ProgressReporter("test_operation", total=100)

            assert reporter.operation_name == "test_operation"
            assert reporter.total == 100
            assert reporter.current == 0.0
            assert reporter.progress_token is mock_token

    @pytest.mark.asyncio
    async def test_progress_reporter_update(self):
        """Test updating progress."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_progress = MagicMock()
            mock_progress.update_progress = AsyncMock()
            mock_token = MagicMock()

            mock_manager.progress = mock_progress
            mock_progress.start_progress.return_value = mock_token
            mock_protocol.return_value = mock_manager

            reporter = ProgressReporter("test_operation")

            await reporter.update(progress=50, status="halfway")

            assert reporter.current == 50
            assert reporter.status == "halfway"
            mock_progress.update_progress.assert_called_once()

    @pytest.mark.asyncio
    async def test_progress_reporter_increment(self):
        """Test incrementing progress."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_progress = MagicMock()
            mock_progress.update_progress = AsyncMock()
            mock_token = MagicMock()

            mock_manager.progress = mock_progress
            mock_progress.start_progress.return_value = mock_token
            mock_protocol.return_value = mock_manager

            reporter = ProgressReporter("test_operation")

            await reporter.update(increment=25)
            assert reporter.current == 25

            await reporter.update(increment=15)
            assert reporter.current == 40

    @pytest.mark.asyncio
    async def test_progress_reporter_context_manager(self):
        """Test progress reporter as context manager."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_progress = MagicMock()
            mock_progress.complete_progress = AsyncMock()
            mock_token = MagicMock()

            mock_manager.progress = mock_progress
            mock_progress.start_progress.return_value = mock_token
            mock_protocol.return_value = mock_manager

            async with ProgressReporter("test_operation") as reporter:
                assert reporter is not None

            mock_progress.complete_progress.assert_called_once_with(
                mock_token, "completed"
            )


class TestCancellationContext:
    """Test cancellation context management."""

    def test_cancellation_context_initialization(self):
        """Test cancellation context initialization."""
        context = CancellationContext("test_request_123")

        assert context.request_id == "test_request_123"
        assert len(context._cleanup_functions) == 0

    def test_is_cancelled(self):
        """Test checking cancellation status."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_cancellation = MagicMock()
            mock_cancellation.is_cancelled.return_value = False

            mock_manager.cancellation = mock_cancellation
            mock_protocol.return_value = mock_manager

            context = CancellationContext("test_request_123")

            assert context.is_cancelled() is False
            mock_cancellation.is_cancelled.assert_called_once_with("test_request_123")

    def test_check_cancellation_not_cancelled(self):
        """Test check_cancellation when not cancelled."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_cancellation = MagicMock()
            mock_cancellation.is_cancelled.return_value = False

            mock_manager.cancellation = mock_cancellation
            mock_protocol.return_value = mock_manager

            context = CancellationContext("test_request_123")

            # Should not raise
            context.check_cancellation()

    def test_check_cancellation_cancelled(self):
        """Test check_cancellation when cancelled."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_cancellation = MagicMock()
            mock_cancellation.is_cancelled.return_value = True

            mock_manager.cancellation = mock_cancellation
            mock_protocol.return_value = mock_manager

            context = CancellationContext("test_request_123")

            with pytest.raises(MCPError) as exc_info:
                context.check_cancellation()

            assert exc_info.value.error_code == MCPErrorCode.REQUEST_CANCELLED

    def test_add_cleanup_function(self):
        """Test adding cleanup function."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_cancellation = MagicMock()

            mock_manager.cancellation = mock_cancellation
            mock_protocol.return_value = mock_manager

            context = CancellationContext("test_request_123")

            def cleanup():
                pass

            context.add_cleanup(cleanup)

            assert cleanup in context._cleanup_functions
            mock_cancellation.add_cleanup_function.assert_called_once_with(
                "test_request_123", cleanup
            )


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_structured_tool_decorator(self):
        """Test structured_tool decorator convenience function."""
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}

        @structured_tool(input_schema=schema)
        def test_function(name: str):
            return f"Hello, {name}!"

        result = test_function(name="Alice")
        assert result == "Hello, Alice!"

    @pytest.mark.asyncio
    async def test_create_progress_reporter(self):
        """Test create_progress_reporter convenience function."""
        with patch(
            "kailash.mcp_server.advanced_features.get_protocol_manager"
        ) as mock_protocol:
            mock_manager = MagicMock()
            mock_progress = MagicMock()
            mock_token = MagicMock()

            mock_manager.progress = mock_progress
            mock_progress.start_progress.return_value = mock_token
            mock_protocol.return_value = mock_manager

            reporter = await create_progress_reporter("test_operation", total=100)

            assert isinstance(reporter, ProgressReporter)
            assert reporter.operation_name == "test_operation"
            assert reporter.total == 100

    def test_create_cancellation_context(self):
        """Test create_cancellation_context convenience function."""
        context = create_cancellation_context("test_request_123")

        assert isinstance(context, CancellationContext)
        assert context.request_id == "test_request_123"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
