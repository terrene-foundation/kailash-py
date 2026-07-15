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


# A CapabilityFn returns True when at least one connected client has advertised
# the ``elicitation`` capability, so the send-half can fail closed instead of
# dispatching an ``elicitation/create`` a client cannot handle (spec 2025-11-25
# § Elicitation — capability-gated). See MCPServer._bind_elicitation_transport.
CapabilityFn = Callable[[], bool]

# The two elicitation modes defined by MCP 2025-11-25. ``form`` collects a set
# of flat primitives inline via ``requestedSchema``; ``url`` hands the user off
# to a server-issued URL so sensitive data is provided OUT-OF-BAND (never inline
# in the JSON-RPC params). Any other requested mode is rejected with -32602.
ELICITATION_MODE_FORM = "form"
ELICITATION_MODE_URL = "url"
ELICITATION_MODES = frozenset({ELICITATION_MODE_FORM, ELICITATION_MODE_URL})

# Primitive JSON-Schema types permitted for a form-mode ``requestedSchema``
# property. The 2025-11-25 form shape is a FLAT object of primitives — no
# nested objects, no arrays — so a client can always render a simple form and
# no structured payload smuggles through the collection surface.
_FLAT_PRIMITIVE_TYPES = frozenset({"string", "number", "integer", "boolean"})

# JSON-Schema structural keywords that reintroduce nesting or indirection and
# therefore have NO place in a flat-primitive form schema. Present at the top
# level OR on any property, each is a fail-closed rejection — a form schema that
# smuggles one of these back in is not renderable as a flat form and could carry
# a structured payload through the collection surface.
_SCHEMA_COMBINATOR_KEYS = frozenset({"allOf", "anyOf", "oneOf", "not", "$ref", "$defs"})

# JSON primitive scalar types permitted as ``enum`` members (``None`` — JSON
# ``null`` — is handled separately since it is not a type instance). ``bool`` is
# a subclass of ``int``; both are covered by the tuple.
_ENUM_PRIMITIVE_TYPES = (bool, int, float, str)


def _validate_flat_primitive_schema(schema: Dict[str, Any]) -> None:
    """Validate a form-mode ``requestedSchema`` is a flat object of primitives.

    The MCP 2025-11-25 form-elicitation shape restricts ``requestedSchema`` to
    an object whose properties are each a primitive (``string`` / ``number`` /
    ``integer`` / ``boolean``) or an ``enum`` of primitives — NO nested objects
    and NO arrays. This keeps the collection surface renderable as a flat form
    and prevents a structured payload from smuggling through it.

    Args:
        schema: The candidate ``requestedSchema`` dict.

    The guard is EXHAUSTIVE and fail-closed: beyond the obvious nested-object /
    array cases it rejects every structural JSON-Schema vector that could
    reintroduce nesting or indirection — top-level ``additionalProperties`` (any
    value other than ``false`` or a flat-primitive schema), ``patternProperties``,
    the combinators / refs in :data:`_SCHEMA_COMBINATOR_KEYS` (top-level AND
    per-property), a property whose ``type`` is not a single primitive string
    (this closes the previously-uncaught ``TypeError`` on a LIST/union ``type``),
    a property carrying ``$ref`` (even alongside a primitive ``type`` sibling),
    and an ``enum`` whose members are not JSON primitive scalars.

    Raises:
        MCPError(INVALID_PARAMS, -32602): The schema is not a flat-primitive
            object.
    """
    if not isinstance(schema, dict):
        raise MCPError(
            "form-mode requestedSchema must be a JSON Schema object, got "
            f"{type(schema).__name__}",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )

    declared_type = schema.get("type", "object")
    if declared_type != "object":
        raise MCPError(
            "form-mode requestedSchema must declare type 'object' with flat "
            f"primitive properties, got type '{declared_type}'",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )

    # Top-level combinators / refs reintroduce nesting or indirection.
    _reject_flat_schema_combinators(schema, "form-mode requestedSchema")

    # ``patternProperties`` describes arbitrarily-keyed nested subschemas — a
    # structured smuggling surface a flat form cannot render.
    if "patternProperties" in schema:
        raise MCPError(
            "form-mode requestedSchema must not use 'patternProperties'; form "
            "mode requires an explicit flat set of primitive properties "
            "(use url mode for open-ended / structured schemas)",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )

    # ``additionalProperties`` may only be ``false`` (a closed object) or itself
    # a flat-primitive schema; a ``true`` / non-``false`` scalar / nested-object
    # value reopens the smuggling surface this guard exists to close.
    if "additionalProperties" in schema:
        addl = schema["additionalProperties"]
        if addl is not False:
            if not isinstance(addl, dict):
                raise MCPError(
                    "form-mode requestedSchema 'additionalProperties' must be "
                    "false or a flat-primitive schema, got "
                    f"{type(addl).__name__}",
                    error_code=MCPErrorCode.INVALID_PARAMS,
                )
            _validate_flat_primitive_property("<additionalProperties>", addl)

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise MCPError(
            "form-mode requestedSchema 'properties' must be an object",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )

    for field_name, prop in properties.items():
        _validate_flat_primitive_property(field_name, prop)


def _reject_flat_schema_combinators(schema: Dict[str, Any], context: str) -> None:
    """Reject any :data:`_SCHEMA_COMBINATOR_KEYS` keyword on ``schema``.

    Fail-closed with MCPError(INVALID_PARAMS) naming the offending keyword.
    Applied at the top level AND per-property so a combinator / ``$ref`` cannot
    reintroduce nesting or indirection at either level.
    """
    for key in _SCHEMA_COMBINATOR_KEYS:
        if key in schema:
            raise MCPError(
                f"{context} must not use the '{key}' JSON-Schema keyword; form "
                "mode requires a flat object of primitive properties "
                "(use url mode for structured / combinator schemas)",
                error_code=MCPErrorCode.INVALID_PARAMS,
            )


def _validate_enum_primitive_members(field_name: str, enum: Any) -> None:
    """Assert every ``enum`` member is a JSON primitive scalar.

    Members must be ``string`` / ``number`` / ``integer`` / ``boolean`` / ``null``
    (Python ``str`` / ``int`` / ``float`` / ``bool`` / ``None``). An object- or
    array-valued member reintroduces nesting through the enum and is rejected
    with a clean -32602.
    """
    if not isinstance(enum, list):
        raise MCPError(
            f"form-mode property '{field_name}' 'enum' must be a list, got "
            f"{type(enum).__name__}",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )
    for member in enum:
        if member is not None and not isinstance(member, _ENUM_PRIMITIVE_TYPES):
            raise MCPError(
                f"form-mode property '{field_name}' enum members must be JSON "
                "primitive scalars (string/number/integer/boolean/null), got "
                f"{type(member).__name__}",
                error_code=MCPErrorCode.INVALID_PARAMS,
            )


def _validate_flat_primitive_property(field_name: str, prop: Any) -> None:
    """Validate one form-mode property is a flat primitive. Raises MCPError.

    Shared by the top-level ``properties`` loop and the ``additionalProperties``
    (schema form) check so both surfaces enforce the identical flat-primitive
    contract.
    """
    if not isinstance(prop, dict):
        raise MCPError(
            f"form-mode property '{field_name}' must be a schema object",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )
    # A property may not reintroduce nesting via structural markers ``properties``
    # (object) / ``items`` (array) / ``patternProperties``.
    if "properties" in prop or "items" in prop or "patternProperties" in prop:
        raise MCPError(
            f"form-mode property '{field_name}' must be a flat primitive; "
            "nested objects and arrays are not permitted in form mode "
            "(use url mode for structured data)",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )
    # A combinator or ``$ref`` on the property is rejected BEFORE the ``type``
    # check, so a property carrying ``$ref`` alongside a primitive ``type``
    # sibling is still rejected.
    _reject_flat_schema_combinators(prop, f"form-mode property '{field_name}'")

    prop_type = prop.get("type")
    # An ``enum`` of primitive scalars is a valid flat primitive even without an
    # explicit ``type``.
    if prop_type is None and "enum" in prop:
        _validate_enum_primitive_members(field_name, prop["enum"])
        return
    # ``type`` MUST be a SINGLE primitive string. A LIST type (union) or a
    # non-primitive type reintroduces nesting / ambiguity and is rejected — this
    # also converts the previously-uncaught ``TypeError`` on ``type: [..]`` into
    # a clean -32602.
    if not isinstance(prop_type, str) or prop_type not in _FLAT_PRIMITIVE_TYPES:
        raise MCPError(
            f"form-mode property '{field_name}' has non-primitive type "
            f"{prop_type!r}; form mode allows only a single primitive type in "
            f"{sorted(_FLAT_PRIMITIVE_TYPES)} or an enum of primitive scalars "
            "(use url mode for nested objects / arrays / unions)",
            error_code=MCPErrorCode.INVALID_PARAMS,
        )
    # A primitive ``type`` MAY still carry an ``enum`` constraint whose members
    # MUST be primitive scalars.
    if "enum" in prop:
        _validate_enum_primitive_members(field_name, prop["enum"])


def _form_response_schema(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Return a form schema hardened with ``additionalProperties: false``.

    A form-mode response MUST NOT carry undeclared (nested) keys past
    validation. Injecting ``additionalProperties: false`` at the top level when
    absent rejects any key the form schema did not declare. If the author
    already set ``additionalProperties`` (constrained by
    :func:`_validate_flat_primitive_schema` to ``false`` or a flat-primitive
    schema), their value is respected. url-mode schemas never reach this path.
    """
    if not isinstance(schema, dict) or "additionalProperties" in schema:
        return schema
    hardened = dict(schema)
    hardened["additionalProperties"] = False
    return hardened


class ElicitationSystem:
    """Interactive user input collection system (MCP elicitation/create).

    Implements the MCP 2025-11-25 `elicitation/create` server-to-client request.
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

    def __init__(
        self,
        send: Optional[SendFn] = None,
        *,
        server_identity: Optional[Dict[str, Any]] = None,
        capability_provider: Optional[CapabilityFn] = None,
    ):
        """Initialize elicitation system.

        Args:
            send: Optional transport send-callable. When provided, the system
                can issue `elicitation/create` requests. When None, the system
                is receive-only — `request_input()` raises MCPError until
                `bind_transport()` is called.
            server_identity: Optional server-identity descriptor bound into
                every ``url``-mode elicitation so the client can verify which
                server issued the hand-off (spec 2025-11-25). ``url`` mode
                requires this — see `request_input`.
            capability_provider: Optional zero-arg callable returning True when
                a connected client has advertised the ``elicitation``
                capability. When bound, `request_input` fails closed if it
                returns False (a client that cannot handle elicitation is never
                sent one blindly). When None, the capability gate is skipped
                (in-process / receive-only construction).
        """
        self._send: Optional[SendFn] = send
        self._server_identity: Optional[Dict[str, Any]] = server_identity
        self._capability_provider: Optional[CapabilityFn] = capability_provider
        self._pending_requests: Dict[str, Dict[str, Any]] = {}
        self._response_callbacks: Dict[str, Callable] = {}
        self._cancel_callbacks: Dict[str, Callable] = {}

    def bind_capability_provider(self, provider: CapabilityFn) -> None:
        """Bind the client-elicitation-capability provider.

        Idempotent: a later call replaces the prior provider. When bound,
        `request_input` consults it BEFORE dispatching and fails closed if the
        provider reports no client advertises the ``elicitation`` capability.

        Args:
            provider: Zero-arg callable returning True when ≥1 connected client
                advertises the ``elicitation`` capability.
        """
        self._capability_provider = provider

    def bind_server_identity(self, server_identity: Dict[str, Any]) -> None:
        """Bind the server-identity descriptor used for ``url``-mode elicitation.

        Idempotent: a later call replaces the prior identity.

        Args:
            server_identity: Descriptor (e.g. ``{"name": server.name}``) bound
                into every ``url``-mode outbound request so the client can
                verify the issuing server.
        """
        self._server_identity = server_identity

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
        *,
        mode: str = ELICITATION_MODE_FORM,
        url: Optional[str] = None,
        client_id: Optional[str] = None,
    ) -> Any:
        """Request input from the connected client.

        Emits an MCP 2025-11-25 `elicitation/create` JSON-RPC request with the
        ``{mode, message, requestedSchema}`` shape, awaits the matching
        `elicitation/response`, validates against `input_schema`, and returns
        the validated payload.

        Two modes (spec 2025-11-25):

        - **form** (default): collect a set of FLAT PRIMITIVES inline via
          `input_schema` (→ ``requestedSchema``). The schema MUST be a flat
          object of primitives (string / number / integer / boolean / enum) —
          nested objects and arrays are rejected at request time.
        - **url**: hand the user off to a server-issued `url`. Sensitive data is
          provided OUT-OF-BAND at that URL — it is NEVER inlined in the JSON-RPC
          params. The outbound request carries an ``elicitationId`` and the
          bound server-identity descriptor so the client can verify the issuing
          server. An `input_schema` is REJECTED in url mode (it would inline the
          collection surface url mode exists to keep out-of-band).

        Args:
            prompt: Prompt shown to the user by the client.
            input_schema: Optional JSON Schema for response validation. In form
                mode, MUST be a flat-primitive object; when None, defaults to
                `{"type": "string"}` on the wire. MUST be None in url mode.
            timeout: Seconds to wait for the response. When None, waits
                indefinitely.
            mode: ``"form"`` (default) or ``"url"``. Any other value is rejected
                with ``INVALID_PARAMS`` (-32602).
            url: Required in url mode — the server-issued URL the client opens to
                collect input out-of-band. Ignored in form mode.
            client_id: Optional id of the client this elicitation targets. When
                provided it is recorded on the pending request so (a) only that
                client may resolve it — a response from another client is
                rejected by the server's response router (cross-client
                isolation) — and (b) that client's disconnect cancels+evicts the
                pending request (``cancel_requests_for_client``). When None the
                request is UNSCOPED: any responder may resolve it and a
                disconnect does not evict it (backward-compatible default).

        Returns:
            The validated response payload from the client.

        Raises:
            MCPError(INVALID_PARAMS, code=-32602): `mode` is not in
                {form, url}, a form-mode schema is not flat-primitive, or a
                url-mode call is missing `url` / passes an inline schema.
            MCPError(INVALID_REQUEST): No send-transport is bound, the client
                has not advertised the ``elicitation`` capability, or url mode
                is requested with no server identity bound.
            MCPError(MCP_ELICITATION_TIMEOUT, code=-32001): Client did not respond within `timeout`.
            MCPError(MCP_REQUEST_CANCELLED, code=-32800): Client returned a `decline` or
                `cancel` action.
            ValidationError: Response failed `input_schema` validation.
        """
        # (1) Mode validation FIRST — an undeclared/unknown mode is a client
        # contract error rejected with INVALID_PARAMS (-32602) before any
        # transport work (security.md § Input Validation).
        if mode not in ELICITATION_MODES:
            raise MCPError(
                f"Unknown elicitation mode {mode!r}; supported modes are "
                f"{sorted(ELICITATION_MODES)}",
                error_code=MCPErrorCode.INVALID_PARAMS,
            )

        if self._send is None:
            raise MCPError(
                "ElicitationSystem has no send transport bound. Construct via "
                "ElicitationSystem(send=transport.send_message) or call "
                "system.bind_transport(transport.send_message) before "
                "request_input(). See specs/mcp-server.md §4.9.",
                error_code=MCPErrorCode.INVALID_REQUEST,
            )

        # (2) Capability gate — never dispatch an elicitation/create to a
        # client that has not advertised the ``elicitation`` capability. When a
        # provider is bound and reports no capable client, fail closed instead
        # of sending blindly (spec 2025-11-25 § capability-gated).
        if self._capability_provider is not None and not self._capability_provider():
            raise MCPError(
                "No connected client has advertised the 'elicitation' "
                "capability; refusing to send elicitation/create. The client "
                "MUST declare `capabilities.elicitation` in initialize.",
                error_code=MCPErrorCode.INVALID_REQUEST,
            )

        # (3) Per-mode request-shape validation.
        if mode == ELICITATION_MODE_FORM:
            # A form schema, when supplied, MUST be a flat object of primitives.
            if input_schema is not None:
                _validate_flat_primitive_schema(input_schema)
        else:  # ELICITATION_MODE_URL
            if not url:
                raise MCPError(
                    "url-mode elicitation requires a non-empty 'url' the client "
                    "opens to collect input out-of-band.",
                    error_code=MCPErrorCode.INVALID_PARAMS,
                )
            if input_schema is not None:
                # An inline schema in url mode would inline the collection
                # surface url mode exists to keep OUT-OF-BAND — reject it so no
                # sensitive field is described (or later carried) inline.
                raise MCPError(
                    "url-mode elicitation MUST NOT carry an inline "
                    "requestedSchema; sensitive data is collected out-of-band "
                    "at the url. Use form mode for inline collection.",
                    error_code=MCPErrorCode.INVALID_PARAMS,
                )
            if not self._server_identity:
                # url mode binds a server identity so the client can verify the
                # issuer; without it the hand-off is unverifiable.
                raise MCPError(
                    "url-mode elicitation requires a bound server identity. "
                    "Construct ElicitationSystem(server_identity=...) or call "
                    "bind_server_identity(...) before request_input(mode='url').",
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

        # Store request metadata. ``client_id`` (may be None) scopes the request
        # to a single client for response-routing + disconnect eviction.
        self._pending_requests[request_id] = {
            "prompt": prompt,
            "schema": input_schema,
            "mode": mode,
            "url": url,
            "client_id": client_id,
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
                    error_code=MCPErrorCode.MCP_REQUEST_CANCELLED,
                )
            )
            if not response_future.done()
            else None
        )

        try:
            # Dispatch the elicitation/create request through the bound transport
            await self._send_elicitation_request(
                request_id, prompt, input_schema, mode=mode, url=url
            )

            # Wait for the matching response (or cancel / timeout)
            if timeout:
                response = await asyncio.wait_for(response_future, timeout=timeout)
            else:
                response = await response_future

            # Validate the response against the declared schema. MUST happen
            # BEFORE returning to the calling tool — skipping validation lets
            # client-supplied payloads reach downstream tools as trusted input.
            if input_schema:
                # Harden the form schema with ``additionalProperties: false`` so
                # a response carrying undeclared (nested) keys is rejected rather
                # than passing validation. url-mode never reaches here (its
                # input_schema is rejected earlier), so this is form-only.
                validator = SchemaValidator(_form_response_schema(input_schema))
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
                error_code=MCPErrorCode.MCP_ELICITATION_TIMEOUT,
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

    def cancel_requests_for_client(
        self, client_id: Optional[str], reason: str = "client disconnected"
    ) -> int:
        """Cancel + evict every pending request SCOPED to ``client_id``.

        Called from the MCPServer transport-disconnect handler (a SYNC context)
        so a disconnecting client's awaiting ``request_input()`` callers get a
        clean ``MCP_REQUEST_CANCELLED`` immediately instead of hanging until
        their timeout. Synchronous by design — it only invokes the already-
        registered cancel callbacks (each sets an exception on the awaiting
        Future) and evicts the pending entry; it never awaits.

        Requests with no bound ``client_id`` (UNSCOPED) are left intact — a
        disconnect cannot know they targeted the departing client, so evicting
        them would wrongly cancel unrelated in-flight elicitations. A ``None``
        ``client_id`` argument therefore matches nothing.

        Args:
            client_id: The disconnecting client. ``None`` matches no request.
            reason: Reason string propagated into the raised MCPError.

        Returns:
            The number of pending requests cancelled + evicted.
        """
        if client_id is None:
            return 0
        stale = [
            rid
            for rid, meta in self._pending_requests.items()
            if meta.get("client_id") == client_id
        ]
        for rid in stale:
            callback = self._cancel_callbacks.get(rid)
            if callback is not None:
                # Sets MCP_REQUEST_CANCELLED on the awaiting Future; the
                # request_input() finally-block pops the callbacks as it unwinds.
                callback(reason)
            # Evict the metadata now so a duplicate disconnect is idempotent and
            # a receive-only pending request (no awaiter) does not leak.
            self._pending_requests.pop(rid, None)
        if stale:
            logger.info(
                "elicitation.client_disconnect.cancelled",
                extra={"client_id": client_id, "count": len(stale)},
            )
        return len(stale)

    async def _send_elicitation_request(
        self,
        request_id: str,
        prompt: str,
        schema: Optional[Dict[str, Any]],
        *,
        mode: str = ELICITATION_MODE_FORM,
        url: Optional[str] = None,
    ) -> None:
        """Serialize and dispatch an MCP elicitation/create request.

        Builds a JSON-RPC 2.0 message per MCP 2025-11-25 (the
        ``{mode, message, requestedSchema}`` shape) and pushes it through the
        bound send-callable. The client responds asynchronously via the MCP
        transport's normal receive loop; the server's dispatch layer routes the
        inbound `elicitation/response` back into `provide_input()` or
        `cancel_request()`.

        In **form** mode the outbound params carry ``requestedSchema`` (the
        flat-primitive collection schema). In **url** mode the params carry an
        ``elicitationId`` + ``url`` + the bound ``server`` identity and carry NO
        ``requestedSchema`` and NO inline field values — sensitive data is
        collected OUT-OF-BAND at the url, so nothing sensitive is ever placed in
        the JSON-RPC params (security invariant).

        Args:
            request_id: Unique request ID (also used as the JSON-RPC `id`).
            prompt: Prompt string shown to the user.
            schema: Optional form-mode JSON Schema for the response. When None
                in form mode, the outbound `requestedSchema` defaults to
                `{"type": "string"}`. Unused in url mode.
            mode: ``"form"`` or ``"url"`` (already validated by `request_input`).
            url: The out-of-band collection URL (url mode only).

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

        if mode == ELICITATION_MODE_URL:
            # url mode: OUT-OF-BAND collection. The params reference the data
            # via ``url`` + ``elicitationId`` and bind the server identity so
            # the client can verify the issuer; NO requestedSchema and NO inline
            # field values are carried (sensitive data never touches the wire).
            params: Dict[str, Any] = {
                "requestId": request_id,
                "mode": ELICITATION_MODE_URL,
                "message": prompt,
                "elicitationId": request_id,
                "url": url,
                "server": self._server_identity,
            }
        else:
            requested_schema = schema if schema is not None else {"type": "string"}
            params = {
                "requestId": request_id,
                "mode": ELICITATION_MODE_FORM,
                "message": prompt,
                "requestedSchema": requested_schema,
            }

        message: Dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "elicitation/create",
            "params": params,
        }

        logger.info(
            "elicitation.send",
            extra={
                "elicitation_request_id": request_id,
                "elicitation_mode": mode,
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
