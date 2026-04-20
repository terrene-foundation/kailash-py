# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Advanced MCP Features Implementation.

This module implements advanced MCP features including structured outputs,
resource templates, streaming support, progress reporting, and other
sophisticated protocol features that extend the basic MCP functionality.

Features:
- Structured tool outputs with JSON Schema validation
- Resource templates with URI template patterns
- Resource subscriptions and change notifications
- Multi-modal content support (text, images, audio)
- Binary resource handling with Base64 encoding
- Progress reporting for long-running operations
- Request cancellation and cleanup
- Tool annotations and metadata
- Content streaming for large responses
- Elicitation system for interactive user input

Examples:
    Structured tool with validation:

    >>> from kailash_mcp.advanced.features import StructuredTool
    >>>
    >>> @StructuredTool(
    ...     output_schema={
    ...         "type": "object",
    ...         "properties": {
    ...             "results": {"type": "array"},
    ...             "count": {"type": "integer"}
    ...         },
    ...         "required": ["results", "count"]
    ...     }
    ... )
    ... def search_tool(query: str) -> dict:
    ...     return {"results": ["item1", "item2"], "count": 2}

    Resource template with dynamic URIs:

    >>> from kailash_mcp.advanced.features import ResourceTemplate
    >>>
    >>> template = ResourceTemplate(
    ...     uri_template="files://{path}",
    ...     name="File Access",
    ...     description="Access files by path"
    ... )
    >>>
    >>> # Subscribe to resource changes
    >>> subscription = await template.subscribe(
    ...     uri="files://documents/report.pdf",
    ...     callback=lambda change: print(f"File changed: {change}")
    ... )

    Multi-modal content:

    >>> from kailash_mcp.advanced.features import MultiModalContent
    >>>
    >>> content = MultiModalContent()
    >>> content.add_text("Here is the analysis:")
    >>> content.add_image(image_data, "image/png")
    >>> content.add_resource("files://data.csv", "text/csv")
"""

import asyncio
import base64
import json
import logging
import mimetypes
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, AsyncGenerator, Awaitable, Callable, Dict, List, Optional, Union
from urllib.parse import urlparse

import jsonschema
from kailash_mcp.errors import MCPError, MCPErrorCode, ValidationError
from kailash_mcp.protocol.protocol import ProgressToken, get_protocol_manager

logger = logging.getLogger(__name__)

# Type alias for the send-callable injected into ElicitationSystem.
# A SendFn takes a JSON-RPC message dict and returns an awaitable that completes
# once the message has been pushed through the underlying transport.
SendFn = Callable[[Dict[str, Any]], Awaitable[None]]


class ContentType(Enum):
    """Content types for multi-modal content."""

    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"
    RESOURCE = "resource"
    ANNOTATION = "annotation"


class ChangeType(Enum):
    """Resource change types."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass
class Content:
    """Multi-modal content item."""

    type: ContentType
    data: Any
    mime_type: Optional[str] = None
    annotations: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result: Dict[str, Any] = {
            "type": self.type.value,
        }

        if self.type == ContentType.TEXT:
            result["text"] = self.data
        elif self.type == ContentType.IMAGE:
            result["data"] = self.data
            if self.mime_type:
                result["mimeType"] = self.mime_type
        elif self.type == ContentType.AUDIO:
            result["data"] = self.data
            if self.mime_type:
                result["mimeType"] = self.mime_type
        elif self.type == ContentType.RESOURCE:
            result["resource"] = self.data
        elif self.type == ContentType.ANNOTATION:
            result["annotation"] = self.data

        if self.annotations:
            result["annotations"] = self.annotations

        return result


@dataclass
class ResourceChange:
    """Resource change notification."""

    uri: str
    change_type: ChangeType
    content: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return {
            "uri": self.uri,
            "type": self.change_type.value,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class ToolAnnotation:
    """Tool annotation for metadata."""

    is_read_only: bool = False
    is_destructive: bool = False
    is_idempotent: bool = True
    estimated_duration: Optional[float] = None
    requires_confirmation: bool = False
    security_level: str = "normal"  # normal, elevated, admin
    rate_limit: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return asdict(self)


class MultiModalContent:
    """Multi-modal content container."""

    def __init__(self):
        """Initialize multi-modal content."""
        self.content_items: List[Content] = []

    def add_text(self, text: str, annotations: Optional[Dict[str, Any]] = None) -> None:
        """Add text content.

        Args:
            text: Text content
            annotations: Optional annotations
        """
        self.content_items.append(
            Content(type=ContentType.TEXT, data=text, annotations=annotations or {})
        )

    def add_image(
        self,
        image_data: Union[str, bytes],
        mime_type: str,
        annotations: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add image content.

        Args:
            image_data: Image data (base64 string or bytes)
            mime_type: Image MIME type
            annotations: Optional annotations
        """
        if isinstance(image_data, bytes):
            image_data = base64.b64encode(image_data).decode()

        self.content_items.append(
            Content(
                type=ContentType.IMAGE,
                data=image_data,
                mime_type=mime_type,
                annotations=annotations or {},
            )
        )

    def add_audio(
        self,
        audio_data: Union[str, bytes],
        mime_type: str,
        annotations: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add audio content.

        Args:
            audio_data: Audio data (base64 string or bytes)
            mime_type: Audio MIME type
            annotations: Optional annotations
        """
        if isinstance(audio_data, bytes):
            audio_data = base64.b64encode(audio_data).decode()

        self.content_items.append(
            Content(
                type=ContentType.AUDIO,
                data=audio_data,
                mime_type=mime_type,
                annotations=annotations or {},
            )
        )

    def add_resource(
        self,
        uri: str,
        text: Optional[str] = None,
        mime_type: Optional[str] = None,
        annotations: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add resource reference.

        Args:
            uri: Resource URI
            text: Optional text content
            mime_type: Optional MIME type
            annotations: Optional annotations
        """
        resource_data = {"uri": uri}
        if text:
            resource_data["text"] = text
        if mime_type:
            resource_data["mimeType"] = mime_type

        self.content_items.append(
            Content(
                type=ContentType.RESOURCE,
                data=resource_data,
                annotations=annotations or {},
            )
        )

    def add_annotation(
        self,
        annotation_type: str,
        data: Dict[str, Any],
        annotations: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Add annotation content.

        Args:
            annotation_type: Type of annotation
            data: Annotation data
            annotations: Optional meta-annotations
        """
        annotation_data = {"type": annotation_type, "data": data}

        self.content_items.append(
            Content(
                type=ContentType.ANNOTATION,
                data=annotation_data,
                annotations=annotations or {},
            )
        )

    def to_list(self) -> List[Dict[str, Any]]:
        """Convert to list format for MCP protocol.

        Returns:
            List of content dictionaries
        """
        return [item.to_dict() for item in self.content_items]

    def is_empty(self) -> bool:
        """Check if content is empty."""
        return len(self.content_items) == 0


class SchemaValidator:
    """JSON Schema validator for tool outputs and inputs."""

    def __init__(self, schema: Dict[str, Any]):
        """Initialize schema validator.

        Args:
            schema: JSON Schema definition
        """
        self.schema = schema
        self._validator = jsonschema.Draft7Validator(schema)

    def validate(self, data: Any) -> None:
        """Validate data against schema.

        Args:
            data: Data to validate

        Raises:
            ValidationError: If validation fails
        """
        errors = list(self._validator.iter_errors(data))
        if errors:
            error_messages = [
                f"{'.'.join(str(p) for p in error.absolute_path)}: {error.message}"
                for error in errors
            ]
            raise ValidationError(
                f"Schema validation failed: {'; '.join(error_messages)}"
            )

    def is_valid(self, data: Any) -> bool:
        """Check if data is valid.

        Args:
            data: Data to check

        Returns:
            True if valid
        """
        try:
            self.validate(data)
            return True
        except ValidationError:
            return False


class StructuredTool:
    """Tool with structured input/output validation."""

    def __init__(
        self,
        input_schema: Optional[Dict[str, Any]] = None,
        output_schema: Optional[Dict[str, Any]] = None,
        annotations: Optional[ToolAnnotation] = None,
        progress_reporting: bool = False,
    ):
        """Initialize structured tool.

        Args:
            input_schema: JSON Schema for input validation
            output_schema: JSON Schema for output validation
            annotations: Tool annotations
            progress_reporting: Enable progress reporting
        """
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.annotations = annotations or ToolAnnotation()
        self.progress_reporting = progress_reporting

        # Create validators
        self.input_validator = SchemaValidator(input_schema) if input_schema else None
        self.output_validator = (
            SchemaValidator(output_schema) if output_schema else None
        )

    def __call__(self, func: Callable) -> Callable:
        """Decorator to wrap function with validation."""

        async def async_wrapper(*args, **kwargs):
            # Input validation
            if self.input_validator and kwargs:
                try:
                    self.input_validator.validate(kwargs)
                except ValidationError as e:
                    raise MCPError(
                        f"Input validation failed: {e}",
                        error_code=MCPErrorCode.INVALID_PARAMS,
                    )

            # Progress reporting setup
            progress_token = None
            protocol = None
            if self.progress_reporting:
                protocol = get_protocol_manager()
                progress_token = protocol.progress.start_progress(func.__name__)
                kwargs["progress_token"] = progress_token

            try:
                # Execute function
                result = await func(*args, **kwargs)

                # Output validation
                if self.output_validator:
                    try:
                        self.output_validator.validate(result)
                    except ValidationError as e:
                        raise MCPError(
                            f"Output validation failed: {e}",
                            error_code=MCPErrorCode.INTERNAL_ERROR,
                        )

                # Complete progress
                if progress_token and protocol is not None:
                    await protocol.progress.complete_progress(
                        progress_token, "completed"
                    )

                return result

            except Exception as e:
                # Error handling
                if progress_token and protocol is not None:
                    await protocol.progress.complete_progress(
                        progress_token, f"failed: {str(e)}"
                    )
                raise

        def sync_wrapper(*args, **kwargs):
            # Input validation
            if self.input_validator and kwargs:
                try:
                    self.input_validator.validate(kwargs)
                except ValidationError as e:
                    raise MCPError(
                        f"Input validation failed: {e}",
                        error_code=MCPErrorCode.INVALID_PARAMS,
                    )

            # Execute function
            result = func(*args, **kwargs)

            # Output validation
            if self.output_validator:
                try:
                    self.output_validator.validate(result)
                except ValidationError as e:
                    raise MCPError(
                        f"Output validation failed: {e}",
                        error_code=MCPErrorCode.INTERNAL_ERROR,
                    )

            return result

        # Return appropriate wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper


class ResourceTemplate:
    """Resource template with URI patterns and subscriptions."""

    def __init__(
        self,
        uri_template: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None,
        supports_subscription: bool = True,
    ):
        """Initialize resource template.

        Args:
            uri_template: URI template pattern
            name: Template name
            description: Template description
            mime_type: Default MIME type
            supports_subscription: Support change subscriptions
        """
        self.uri_template = uri_template
        self.name = name
        self.description = description
        self.mime_type = mime_type
        self.supports_subscription = supports_subscription

        # Subscription management
        self._subscriptions: Dict[str, List[Callable]] = {}
        self._subscription_ids: Dict[str, str] = {}

    def matches_uri(self, uri: str) -> bool:
        """Check if URI matches this template.

        Args:
            uri: URI to check

        Returns:
            True if matches template
        """
        # Simple pattern matching - check scheme first
        if "://" in self.uri_template and "://" in uri:
            template_scheme = self.uri_template.split("://")[0]
            uri_scheme = uri.split("://")[0]

            if template_scheme != uri_scheme:
                return False

        # For basic matching, just check if URI starts with the template prefix
        # (without the variable parts)
        template_prefix = self.uri_template.split("{")[0]
        return uri.startswith(template_prefix)

    async def subscribe(
        self, uri: str, callback: Callable[[ResourceChange], None]
    ) -> str:
        """Subscribe to resource changes.

        Args:
            uri: Resource URI to monitor
            callback: Change notification callback

        Returns:
            Subscription ID
        """
        if not self.supports_subscription:
            raise MCPError(
                "Resource does not support subscriptions",
                error_code=MCPErrorCode.METHOD_NOT_FOUND,
            )

        if not self.matches_uri(uri):
            raise MCPError(
                "URI does not match template", error_code=MCPErrorCode.INVALID_PARAMS
            )

        subscription_id = str(uuid.uuid4())

        if uri not in self._subscriptions:
            self._subscriptions[uri] = []

        self._subscriptions[uri].append(callback)
        self._subscription_ids[subscription_id] = uri

        logger.info(f"Created subscription {subscription_id} for {uri}")
        return subscription_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe from resource changes.

        Args:
            subscription_id: Subscription ID to remove

        Returns:
            True if subscription was removed
        """
        if subscription_id not in self._subscription_ids:
            return False

        uri = self._subscription_ids[subscription_id]

        # Find and remove callback (simplified - in production, track callback references)
        if uri in self._subscriptions and self._subscriptions[uri]:
            self._subscriptions[uri].pop()  # Remove last callback (simplified)

            if not self._subscriptions[uri]:
                del self._subscriptions[uri]

        del self._subscription_ids[subscription_id]

        logger.info(f"Removed subscription {subscription_id} for {uri}")
        return True

    async def notify_change(self, change: ResourceChange) -> None:
        """Notify subscribers of resource change.

        Args:
            change: Resource change details
        """
        uri = change.uri
        if uri not in self._subscriptions:
            return

        # Notify all subscribers
        for callback in self._subscriptions[uri]:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(change)
                else:
                    callback(change)
            except Exception as e:
                logger.error(f"Subscription callback error: {e}")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        result = {"uriTemplate": self.uri_template}

        if self.name:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.mime_type:
            result["mimeType"] = self.mime_type

        return result


class BinaryResourceHandler:
    """Handler for binary resources with Base64 encoding."""

    def __init__(self, max_size: int = 10_000_000):  # 10MB default
        """Initialize binary resource handler.

        Args:
            max_size: Maximum file size in bytes
        """
        self.max_size = max_size

    async def read_binary_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        """Read binary file and encode as Base64.

        Args:
            file_path: Path to binary file

        Returns:
            Resource content with Base64 data
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise MCPError(
                f"File not found: {file_path}",
                error_code=MCPErrorCode.RESOURCE_NOT_FOUND,
            )

        file_size = file_path.stat().st_size
        if file_size > self.max_size:
            raise MCPError(
                f"File too large: {file_size} bytes",
                error_code=MCPErrorCode.INVALID_PARAMS,
            )

        # Read file and encode
        with open(file_path, "rb") as f:
            binary_data = f.read()

        encoded_data = base64.b64encode(binary_data).decode()

        # Detect MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = "application/octet-stream"

        return {
            "uri": f"file://{file_path.absolute()}",
            "mimeType": mime_type,
            "blob": encoded_data,
        }

    def decode_base64_content(self, encoded_data: str) -> bytes:
        """Decode Base64 content to bytes.

        Args:
            encoded_data: Base64 encoded data

        Returns:
            Binary data
        """
        try:
            return base64.b64decode(encoded_data)
        except Exception as e:
            raise MCPError(
                f"Invalid Base64 data: {e}", error_code=MCPErrorCode.INVALID_PARAMS
            )


class StreamingHandler:
    """Handler for streaming large responses."""

    def __init__(self, chunk_size: int = 8192):
        """Initialize streaming handler.

        Args:
            chunk_size: Size of each chunk in bytes
        """
        self.chunk_size = chunk_size

    async def stream_text(self, text: str) -> AsyncGenerator[str, None]:
        """Stream text content in chunks.

        Args:
            text: Text to stream

        Yields:
            Text chunks
        """
        for i in range(0, len(text), self.chunk_size):
            chunk = text[i : i + self.chunk_size]
            yield chunk
            await asyncio.sleep(0)  # Allow other tasks to run

    async def stream_binary(self, data: bytes) -> AsyncGenerator[str, None]:
        """Stream binary content as Base64 chunks.

        Args:
            data: Binary data to stream

        Yields:
            Base64 encoded chunks
        """
        for i in range(0, len(data), self.chunk_size):
            chunk = data[i : i + self.chunk_size]
            encoded_chunk = base64.b64encode(chunk).decode()
            yield encoded_chunk
            await asyncio.sleep(0)  # Allow other tasks to run

    async def stream_file(
        self, file_path: Union[str, Path]
    ) -> AsyncGenerator[str, None]:
        """Stream file content as Base64 chunks.

        Args:
            file_path: Path to file

        Yields:
            Base64 encoded chunks
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise MCPError(
                f"File not found: {file_path}",
                error_code=MCPErrorCode.RESOURCE_NOT_FOUND,
            )

        with open(file_path, "rb") as f:
            while True:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break

                encoded_chunk = base64.b64encode(chunk).decode()
                yield encoded_chunk
                await asyncio.sleep(0)  # Allow other tasks to run


class ElicitationSystem:
    """Interactive user input collection system (MCP elicitation/create).

    Implements the MCP 2025-06-18 `elicitation/create` server-to-client request.
    The system is split into two halves, both wired into the framework's hot
    path per rules/orphan-detection.md §1:

    - **Send half** (`_send_elicitation_request`): serializes an
      `elicitation/create` JSON-RPC request and pushes it through an injected
      send-callable bound to the active client transport.
    - **Receive half** (`provide_input` / `cancel_request`): invoked by the
      MCPServer's dispatch loop when an inbound `elicitation/response` with a
      matching request_id arrives from the client.

    Construction:

        >>> from typing import Awaitable, Callable
        >>> # Option A: pass send-callable at construction time
        >>> system = ElicitationSystem(send=transport.send_message)
        >>> # Option B: bind after construction (transport attaches later)
        >>> system = ElicitationSystem()
        >>> system.bind_transport(transport.send_message)

    When `send is None`, the system is receive-only: `provide_input()` still
    works (useful for in-process tests), but `request_input()` raises
    `MCPError(INVALID_REQUEST)` with actionable guidance naming
    `bind_transport`.

    See specs/mcp-server.md §4.9 for the full contract.
    """

    def __init__(self, send: Optional[SendFn] = None):
        """Initialize elicitation system.

        Args:
            send: Optional transport send-callable. When provided, the system
                can issue `elicitation/create` requests. When None, the system
                is receive-only — `request_input()` raises MCPError until
                `bind_transport()` is called.
        """
        self._send: Optional[SendFn] = send
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._response_callbacks: Dict[str, Callable] = {}
        self._cancel_callbacks: Dict[str, Callable] = {}

    def bind_transport(self, send: SendFn) -> None:
        """Bind a transport send-callable after construction.

        Idempotent: a second call replaces the prior send-fn (used when a
        transport reconnects). Does not affect pending requests.

        Args:
            send: Awaitable callable that accepts a JSON-RPC message dict and
                pushes it through the underlying transport.
        """
        self._send = send
        logger.debug(
            "elicitation.transport.bound",
            extra={"has_send": True},
        )

    def has_transport(self) -> bool:
        """Return True when a send-callable has been bound."""
        return self._send is not None

    async def request_input(
        self,
        prompt: str,
        input_schema: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = 300.0,
    ) -> Any:
        """Request input from the connected client.

        Emits an MCP `elicitation/create` JSON-RPC request, awaits the
        matching `elicitation/response`, validates against `input_schema`,
        and returns the validated payload.

        Args:
            prompt: Prompt shown to the user by the client.
            input_schema: Optional JSON Schema (Draft 7) for response
                validation. When None, defaults to `{"type": "string"}` on the
                wire (per MCP spec: `requestedSchema` is required in the
                outbound message).
            timeout: Seconds to wait for the response. When None, waits
                indefinitely.

        Returns:
            The validated response payload from the client.

        Raises:
            MCPError(INVALID_REQUEST): No send-transport is bound.
            MCPError(REQUEST_TIMEOUT): Client did not respond within `timeout`.
            MCPError(REQUEST_CANCELLED): Client returned a `decline` or
                `cancel` action.
            ValidationError: Response failed `input_schema` validation.
        """
        if self._send is None:
            raise MCPError(
                "ElicitationSystem has no send transport bound. Construct via "
                "ElicitationSystem(send=transport.send_message) or call "
                "system.bind_transport(transport.send_message) before "
                "request_input(). See specs/mcp-server.md §4.9.",
                error_code=MCPErrorCode.INVALID_REQUEST,
            )

        request_id = str(uuid.uuid4())
        start_ts = time.monotonic()
        logger.info(
            "elicitation.request.start",
            extra={
                "elicitation_request_id": request_id,
                "has_schema": input_schema is not None,
                "timeout": timeout,
            },
        )

        # Store request metadata
        self._pending_requests[request_id] = {
            "prompt": prompt,
            "schema": input_schema,
            "timestamp": time.time(),
        }

        # Create futures for response / cancellation
        response_future: "asyncio.Future[Any]" = asyncio.Future()
        self._response_callbacks[request_id] = lambda data: (
            response_future.set_result(data) if not response_future.done() else None
        )
        self._cancel_callbacks[request_id] = lambda reason: (
            response_future.set_exception(
                MCPError(
                    f"Client cancelled elicitation request: {reason}",
                    error_code=MCPErrorCode.REQUEST_CANCELLED,
                )
            )
            if not response_future.done()
            else None
        )

        try:
            # Dispatch the elicitation/create request through the bound transport
            await self._send_elicitation_request(request_id, prompt, input_schema)

            # Wait for the matching response (or cancel / timeout)
            if timeout:
                response = await asyncio.wait_for(response_future, timeout=timeout)
            else:
                response = await response_future

            # Validate the response against the declared schema. MUST happen
            # BEFORE returning to the calling tool — skipping validation lets
            # client-supplied payloads reach downstream tools as trusted input.
            if input_schema:
                validator = SchemaValidator(input_schema)
                validator.validate(response)

            elapsed_ms = (time.monotonic() - start_ts) * 1000
            logger.info(
                "elicitation.request.ok",
                extra={
                    "elicitation_request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                },
            )
            return response

        except asyncio.TimeoutError:
            elapsed_ms = (time.monotonic() - start_ts) * 1000
            logger.warning(
                "elicitation.request.timeout",
                extra={
                    "elicitation_request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                    "timeout": timeout,
                },
            )
            raise MCPError(
                f"Elicitation request {request_id} timed out after {timeout}s",
                error_code=MCPErrorCode.REQUEST_TIMEOUT,
            )
        except MCPError:
            elapsed_ms = (time.monotonic() - start_ts) * 1000
            logger.warning(
                "elicitation.request.error",
                extra={
                    "elicitation_request_id": request_id,
                    "elapsed_ms": elapsed_ms,
                },
            )
            raise
        finally:
            self._pending_requests.pop(request_id, None)
            self._response_callbacks.pop(request_id, None)
            self._cancel_callbacks.pop(request_id, None)

    async def provide_input(self, request_id: str, input_data: Any) -> bool:
        """Deliver an `accept`-action response to a pending elicitation.

        Invoked by the MCPServer dispatch loop when an inbound
        `elicitation/response` (action == "accept") with matching request_id
        arrives from the client. Schema validation is intentionally NOT done
        here — it happens in `request_input()` after the response future
        resolves, so validation is a single-point concern.

        Args:
            request_id: Request ID from the client's response (matches the
                `id` field of the original elicitation/create request).
            input_data: The `content` payload from the client's ElicitResult.

        Returns:
            True if a matching pending request existed and the callback was
            invoked. False when the request_id is unknown (e.g., late
            response arriving after timeout cleanup).
        """
        if request_id not in self._pending_requests:
            logger.debug(
                "elicitation.response.unknown",
                extra={"elicitation_request_id": request_id},
            )
            return False

        callback = self._response_callbacks.get(request_id)
        if callback:
            callback(input_data)
            logger.debug(
                "elicitation.response.delivered",
                extra={"elicitation_request_id": request_id},
            )
            return True

        return False

    async def cancel_request(
        self, request_id: str, reason: str = "client cancelled"
    ) -> bool:
        """Cancel a pending elicitation.

        Invoked by the MCPServer dispatch loop when the client's
        `elicitation/response` carries action "decline" or "cancel", OR when
        the transport disconnects with pending elicitations. The calling
        `request_input()` coroutine will raise
        `MCPError(REQUEST_CANCELLED)`.

        Args:
            request_id: Request ID to cancel.
            reason: Short reason string propagated into the raised MCPError.

        Returns:
            True if a matching pending request existed and was cancelled.
            False when the request_id is unknown.
        """
        if request_id not in self._pending_requests:
            return False

        callback = self._cancel_callbacks.get(request_id)
        if callback:
            callback(reason)
            logger.info(
                "elicitation.response.cancelled",
                extra={
                    "elicitation_request_id": request_id,
                    "reason": reason,
                },
            )
            return True

        return False

    async def _send_elicitation_request(
        self,
        request_id: str,
        prompt: str,
        schema: Optional[Dict[str, Any]],
    ) -> None:
        """Serialize and dispatch an MCP elicitation/create request.

        Builds a JSON-RPC 2.0 message per MCP 2025-06-18 and pushes it
        through the bound send-callable. The client responds asynchronously
        via the MCP transport's normal receive loop; the server's dispatch
        layer routes the inbound `elicitation/response` back into
        `provide_input()` or `cancel_request()`.

        Args:
            request_id: Unique request ID (also used as the JSON-RPC `id`).
            prompt: Prompt string shown to the user.
            schema: Optional JSON Schema for the response. When None, the
                outbound `requestedSchema` defaults to
                `{"type": "string"}` per MCP spec requirement.

        Raises:
            MCPError(INVALID_REQUEST): No send-callable is bound. Callers
                should normally hit this via `request_input()` which checks
                the transport first; the check is duplicated here as
                defense-in-depth against callers that invoke the private
                method directly.
        """
        if self._send is None:
            raise MCPError(
                "ElicitationSystem has no send transport bound. Call "
                "system.bind_transport(transport.send_message) before "
                "invoking _send_elicitation_request(). See "
                "specs/mcp-server.md §4.9.",
                error_code=MCPErrorCode.INVALID_REQUEST,
            )

        requested_schema = schema if schema is not None else {"type": "string"}
        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "elicitation/create",
            "params": {
                "requestId": request_id,
                "message": prompt,
                "requestedSchema": requested_schema,
            },
        }

        logger.info(
            "elicitation.send",
            extra={
                "elicitation_request_id": request_id,
                "has_schema": schema is not None,
                "mode": "real",
            },
        )
        await self._send(message)


class ProgressReporter:
    """Enhanced progress reporting for long-running operations."""

    def __init__(self, operation_name: str, total: Optional[float] = None):
        """Initialize progress reporter.

        Args:
            operation_name: Name of the operation
            total: Total progress units (if known)
        """
        self.operation_name = operation_name
        self.total = total
        self.current = 0.0
        self.status = "started"

        # Get progress token from protocol manager
        protocol = get_protocol_manager()
        self.progress_token = protocol.progress.start_progress(operation_name, total)

    async def update(
        self,
        progress: Optional[float] = None,
        status: Optional[str] = None,
        increment: Optional[float] = None,
    ) -> None:
        """Update progress.

        Args:
            progress: Current progress value
            status: Status message
            increment: Amount to increment progress
        """
        protocol = get_protocol_manager()

        if progress is not None:
            self.current = progress
        elif increment is not None:
            self.current += increment

        if status is not None:
            self.status = status

        await protocol.progress.update_progress(
            self.progress_token,
            progress=self.current,
            status=self.status,
            increment=increment,
        )

    async def complete(self, status: str = "completed") -> None:
        """Complete progress reporting.

        Args:
            status: Final status
        """
        protocol = get_protocol_manager()
        await protocol.progress.complete_progress(self.progress_token, status)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if exc_type:
            await self.complete(f"failed: {exc_val}")
        else:
            await self.complete()


class CancellationContext:
    """Context for handling request cancellation."""

    def __init__(self, request_id: str):
        """Initialize cancellation context.

        Args:
            request_id: Request ID to monitor for cancellation
        """
        self.request_id = request_id
        self._cleanup_functions: List[Callable] = []

    def is_cancelled(self) -> bool:
        """Check if request is cancelled."""
        protocol = get_protocol_manager()
        return protocol.cancellation.is_cancelled(self.request_id)

    def check_cancellation(self) -> None:
        """Check for cancellation and raise exception if cancelled."""
        if self.is_cancelled():
            raise MCPError(
                "Operation was cancelled", error_code=MCPErrorCode.REQUEST_CANCELLED
            )

    def add_cleanup(self, cleanup_func: Callable) -> None:
        """Add cleanup function.

        Args:
            cleanup_func: Function to call on cancellation
        """
        self._cleanup_functions.append(cleanup_func)

        # Register with protocol manager
        protocol = get_protocol_manager()
        protocol.cancellation.add_cleanup_function(self.request_id, cleanup_func)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        # Cleanup is handled by protocol manager
        pass


# Convenience functions
def structured_tool(
    input_schema: Optional[Dict[str, Any]] = None,
    output_schema: Optional[Dict[str, Any]] = None,
    annotations: Optional[ToolAnnotation] = None,
    progress_reporting: bool = False,
):
    """Decorator for creating structured tools.

    Args:
        input_schema: JSON Schema for input validation
        output_schema: JSON Schema for output validation
        annotations: Tool annotations
        progress_reporting: Enable progress reporting

    Returns:
        Tool decorator
    """
    return StructuredTool(input_schema, output_schema, annotations, progress_reporting)


async def create_progress_reporter(
    operation_name: str, total: Optional[float] = None
) -> ProgressReporter:
    """Create progress reporter.

    Args:
        operation_name: Operation name
        total: Total progress units

    Returns:
        Progress reporter
    """
    return ProgressReporter(operation_name, total)


def create_cancellation_context(request_id: str) -> CancellationContext:
    """Create cancellation context.

    Args:
        request_id: Request ID

    Returns:
        Cancellation context
    """
    return CancellationContext(request_id)
