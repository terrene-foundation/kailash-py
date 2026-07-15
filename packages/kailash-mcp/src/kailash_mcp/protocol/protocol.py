"""
Complete MCP Protocol Implementation.

This module implements the full Model Context Protocol (MCP) specification,
including all message types, progress reporting, cancellation, completion,
sampling, and other advanced protocol features that build on the official
MCP Python SDK.

Features:
- Complete protocol message type definitions
- Progress reporting with token-based tracking
- Request cancellation and cleanup
- Completion system for prompts and resources
- Sampling system for LLM interactions
- Roots system for file system access
- Meta field support for protocol metadata
- Proper error handling with standard codes

The implementation follows the official MCP specification while providing
enhanced functionality for production use cases.

Examples:
    Progress reporting:

    >>> from kailash_mcp.protocol.protocol import ProgressManager
    >>> progress = ProgressManager()
    >>>
    >>> # Start progress tracking
    >>> token = progress.start_progress("long_operation", total=100)
    >>> for i in range(100):
    ...     await progress.update_progress(token, progress=i, status=f"Step {i}")
    >>> await progress.complete_progress(token)

    Request cancellation:

    >>> from kailash_mcp.protocol.protocol import CancellationManager
    >>> cancellation = CancellationManager()
    >>>
    >>> # Check if request should be cancelled
    >>> if await cancellation.is_cancelled(request_id):
    ...     raise CancelledError("Operation was cancelled")

    Completion system:

    >>> from kailash_mcp.protocol.protocol import CompletionManager
    >>> completion = CompletionManager()
    >>>
    >>> # Get completions for a prompt argument
    >>> completions = await completion.get_completions(
    ...     "prompts/analyze", "data_source", "fil"
    ... )
"""

import asyncio
import inspect
import json
import logging
import posixpath
import time
import uuid
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Union
from urllib.parse import unquote, urlsplit

from kailash_mcp.errors import MCPError, MCPErrorCode

logger = logging.getLogger(__name__)


class MessageType(Enum):
    """MCP message types following the official specification."""

    # Core protocol
    INITIALIZE = "initialize"
    INITIALIZED = "initialized"

    # Tool operations
    TOOLS_LIST = "tools/list"
    TOOLS_CALL = "tools/call"

    # Resource operations
    RESOURCES_LIST = "resources/list"
    RESOURCES_READ = "resources/read"
    RESOURCES_SUBSCRIBE = "resources/subscribe"
    RESOURCES_UNSUBSCRIBE = "resources/unsubscribe"
    RESOURCES_UPDATED = "notifications/resources/updated"

    # Prompt operations
    PROMPTS_LIST = "prompts/list"
    PROMPTS_GET = "prompts/get"

    # Progress operations
    PROGRESS = "notifications/progress"

    # Cancellation
    CANCELLED = "notifications/cancelled"

    # Completion
    COMPLETION_COMPLETE = "completion/complete"

    # Sampling (Server to Client)
    SAMPLING_CREATE_MESSAGE = "sampling/createMessage"

    # Roots (File system)
    ROOTS_LIST = "roots/list"

    # Logging
    LOGGING_SET_LEVEL = "logging/setLevel"

    # Custom extensions
    PING = "ping"
    PONG = "pong"
    REQUEST = "request"  # Generic request type
    NOTIFICATION = "notification"  # Generic notification type


@dataclass
class ProgressToken:
    """Type-safe progress token with tracking information."""

    value: str
    operation_name: str
    total: Optional[float] = None
    progress: float = 0
    status: Optional[str] = None

    def __hash__(self):
        """Make hashable for use in dictionaries."""
        return hash(self.value)

    def __eq__(self, other):
        """Compare tokens by value."""
        if isinstance(other, ProgressToken):
            return self.value == other.value
        return False


@dataclass
class MetaData:
    """Meta fields for protocol messages."""

    progress_token: Optional[ProgressToken] = None
    request_id: Optional[str] = None
    timestamp: Optional[float] = None
    operation_id: Optional[str] = None
    user_id: Optional[str] = None
    additional_data: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        """Initialize timestamp if not provided."""
        if self.timestamp is None:
            self.timestamp = time.time()
        if self.additional_data is None:
            self.additional_data = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {}
        if self.progress_token:
            result["progressToken"] = self.progress_token
        if self.request_id:
            result["requestId"] = self.request_id
        if self.timestamp:
            result["timestamp"] = self.timestamp
        if self.operation_id:
            result["operation_id"] = self.operation_id
        if self.user_id:
            result["user_id"] = self.user_id
        if self.additional_data:
            result.update(self.additional_data)
        return result


@dataclass
class ProgressNotification:
    """Progress notification message."""

    method: str = "notifications/progress"
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure proper params structure."""
        if "progressToken" not in self.params:
            raise ValueError("Progress notification requires progressToken")

    @classmethod
    def create(
        cls,
        progress_token: ProgressToken,
        progress: Optional[float] = None,
        total: Optional[float] = None,
        status: Optional[str] = None,
    ) -> "ProgressNotification":
        """Create progress notification."""
        params: Dict[str, Any] = {"progressToken": progress_token}

        if progress is not None:
            params["progress"] = progress
        if total is not None:
            params["total"] = total
        if status is not None:
            params["status"] = status

        return cls(params=params)


@dataclass
class CancelledNotification:
    """Cancellation notification message."""

    method: str = "notifications/cancelled"
    params: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Ensure proper params structure."""
        if "requestId" not in self.params:
            raise ValueError("Cancellation notification requires requestId")

    @classmethod
    def create(
        cls, request_id: str, reason: Optional[str] = None
    ) -> "CancelledNotification":
        """Create cancellation notification."""
        params = {"requestId": request_id}
        if reason:
            params["reason"] = reason
        return cls(params=params)


@dataclass
class CompletionRequest:
    """Completion request for prompts and resources."""

    method: str = "completion/complete"
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls, ref: Dict[str, Any], argument: Optional[Dict[str, Any]] = None
    ) -> "CompletionRequest":
        """Create completion request."""
        params = {"ref": ref}
        if argument:
            params["argument"] = argument
        return cls(params=params)


@dataclass
class CompletionResult:
    """Completion result with completion values."""

    completion: Dict[str, Any]

    @classmethod
    def create(
        cls, values: List[str], total: Optional[int] = None
    ) -> "CompletionResult":
        """Create completion result."""
        completion: Dict[str, Any] = {"values": values}
        if total is not None:
            completion["total"] = total
        return cls(completion=completion)


@dataclass
class SamplingRequest:
    """Sampling request from server to client."""

    method: str = "sampling/createMessage"
    params: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        messages: List[Dict[str, Any]],
        model_preferences: Optional[Dict[str, Any]] = None,
        system_prompt: Optional[str] = None,
        include_context: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "SamplingRequest":
        """Create sampling request."""
        params: Dict[str, Any] = {"messages": messages}

        if model_preferences:
            params["modelPreferences"] = model_preferences
        if system_prompt:
            params["systemPrompt"] = system_prompt
        if include_context:
            params["includeContext"] = include_context
        if temperature is not None:
            params["temperature"] = temperature
        if max_tokens is not None:
            params["maxTokens"] = max_tokens
        if stop_sequences:
            params["stopSequences"] = stop_sequences
        if metadata:
            params["metadata"] = metadata

        return cls(params=params)


@dataclass
class ResourceTemplate:
    """Resource template with URI templates."""

    uri_template: str
    name: Optional[str] = None
    description: Optional[str] = None
    mime_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result = {"uriTemplate": self.uri_template}
        if self.name:
            result["name"] = self.name
        if self.description:
            result["description"] = self.description
        if self.mime_type:
            result["mimeType"] = self.mime_type
        return result


class ResourceChangeType(Enum):
    """Types of resource changes."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


@dataclass
class ResourceChange:
    """Represents a resource change event."""

    type: ResourceChangeType
    uri: str
    timestamp: datetime

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type.value,
            "uri": self.uri,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class ToolResult:
    """Enhanced tool result with structured content."""

    content: List[Dict[str, Any]]
    is_error: bool = False

    @classmethod
    def text(cls, text: str, is_error: bool = False) -> "ToolResult":
        """Create text result."""
        return cls(content=[{"type": "text", "text": text}], is_error=is_error)

    @classmethod
    def image(cls, data: str, mime_type: str) -> "ToolResult":
        """Create image result."""
        return cls(content=[{"type": "image", "data": data, "mimeType": mime_type}])

    @classmethod
    def resource(
        cls, uri: str, text: Optional[str] = None, mime_type: Optional[str] = None
    ) -> "ToolResult":
        """Create resource result."""
        content: Dict[str, Any] = {"type": "resource", "resource": {"uri": uri}}
        if text:
            content["resource"]["text"] = text
        if mime_type:
            content["resource"]["mimeType"] = mime_type
        return cls(content=[content])

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        result: Dict[str, Any] = {"content": self.content}
        if self.is_error:
            result["isError"] = self.is_error
        return result


class ProgressManager:
    """Manages progress reporting for long-running operations."""

    def __init__(self):
        """Initialize progress manager."""
        self._active_progress: Dict[ProgressToken, Dict[str, Any]] = {}
        self._progress_callbacks: Dict[ProgressToken, List[Callable]] = {}

    def start_progress(
        self,
        operation_name: str,
        total: Optional[float] = None,
        progress_token: Optional[ProgressToken] = None,
    ) -> ProgressToken:
        """Start progress tracking for an operation.

        Args:
            operation_name: Name of the operation
            total: Total progress units (if known)
            progress_token: Custom progress token (generates if None)

        Returns:
            Progress token for tracking
        """
        if progress_token is None:
            token_value = f"progress_{uuid.uuid4().hex[:8]}"
            progress_token = ProgressToken(
                value=token_value,
                operation_name=operation_name,
                total=total,
                progress=0,
                status="started",
            )

        self._active_progress[progress_token] = {
            "operation": operation_name,
            "started_at": time.time(),
            "total": total,
            "current": 0,
            "status": "started",
        }
        self._progress_callbacks[progress_token] = []

        logger.debug(
            f"Started progress tracking: {operation_name} ({progress_token.value})"
        )
        return progress_token

    async def update_progress(
        self,
        progress_token: ProgressToken,
        progress: Optional[float] = None,
        status: Optional[str] = None,
        increment: Optional[float] = None,
    ) -> None:
        """Update progress for an operation.

        Args:
            progress_token: Progress token
            progress: Current progress value
            status: Status message
            increment: Amount to increment current progress
        """
        if progress_token not in self._active_progress:
            logger.warning(f"Progress token not found: {progress_token}")
            return

        progress_info = self._active_progress[progress_token]

        # Update progress value
        if progress is not None:
            progress_info["current"] = progress
            progress_token.progress = progress
        elif increment is not None:
            new_progress = progress_info.get("current", 0) + increment
            progress_info["current"] = new_progress
            progress_token.progress = new_progress

        # Update status
        if status is not None:
            progress_info["status"] = status
            progress_token.status = status

        progress_info["updated_at"] = time.time()

        # Create notification
        notification = ProgressNotification.create(
            progress_token=progress_token.value,  # type: ignore[arg-type]
            progress=progress_info["current"],
            total=progress_info.get("total"),
            status=progress_info["status"],
        )

        # Call callbacks
        for callback in self._progress_callbacks.get(progress_token, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(notification)
                else:
                    callback(notification)
            except Exception as e:
                logger.error(f"Progress callback error: {e}")

    async def complete_progress(
        self, progress_token: ProgressToken, status: str = "completed"
    ) -> None:
        """Complete progress tracking.

        Args:
            progress_token: Progress token
            status: Final status message
        """
        if progress_token not in self._active_progress:
            return

        progress_info = self._active_progress[progress_token]
        progress_info["status"] = status
        progress_info["completed_at"] = time.time()

        # Update token status
        progress_token.status = status

        # Send final progress update
        await self.update_progress(progress_token, status=status)

        # Clean up
        del self._active_progress[progress_token]
        del self._progress_callbacks[progress_token]

        logger.debug(f"Completed progress tracking: {progress_token.value}")

    def add_progress_callback(
        self, progress_token: ProgressToken, callback: Callable
    ) -> None:
        """Add callback for progress updates.

        Args:
            progress_token: Progress token
            callback: Callback function
        """
        if progress_token in self._progress_callbacks:
            self._progress_callbacks[progress_token].append(callback)

    def get_progress_info(
        self, progress_token: ProgressToken
    ) -> Optional[Dict[str, Any]]:
        """Get current progress information.

        Args:
            progress_token: Progress token

        Returns:
            Progress information or None
        """
        return self._active_progress.get(progress_token)

    def list_active_progress(self) -> List[ProgressToken]:
        """List all active progress tokens."""
        return list(self._active_progress.keys())

    def get_active_progress(self) -> List[ProgressToken]:
        """Get all active progress tokens (alias for list_active_progress)."""
        return self.list_active_progress()


class CancellationManager:
    """Manages request cancellation and cleanup.

    The cancelled-request set is BOUNDED (``_MAX_CANCELLED_REQUESTS`` via FIFO
    eviction) so a client streaming unique request ids cannot grow it without
    limit (remote OOM/DoS), and stored reasons are length-capped
    (``_MAX_REASON_LEN``). Request ids are client-scoped by the server (the
    ``MCPServer`` keys by a ``client_id``-prefixed composite), so
    ``clear_cancelled_by_prefix`` lets the server drop one client's state on
    disconnect.
    """

    # Cap on the retained cancelled-request set. Mirrors the server-side
    # ``_MAX_SEEN_REQUEST_IDS`` bound; a cancelled id beyond the cap is
    # FIFO-evicted so client-controlled ids cannot grow the set without bound.
    _MAX_CANCELLED_REQUESTS = 4096
    # Cap on a stored cancellation reason string (client-supplied, untrusted).
    _MAX_REASON_LEN = 1024

    def __init__(self):
        """Initialize cancellation manager."""
        self._cancelled_requests: set[str] = set()
        self._cancelled_order: deque = deque()
        self._cancellation_callbacks: Dict[str, List[Callable]] = {}
        self._request_cleanup: Dict[str, List[Callable]] = {}
        self._cancellation_reasons: Dict[str, Optional[str]] = {}

    async def cancel_request(
        self, request_id: str, reason: Optional[str] = None
    ) -> None:
        """Cancel a request.

        Args:
            request_id: Request ID to cancel
            reason: Cancellation reason
        """
        if request_id in self._cancelled_requests:
            return  # Already cancelled

        # Cap the client-supplied reason before storing (untrusted length).
        if isinstance(reason, str) and len(reason) > self._MAX_REASON_LEN:
            reason = reason[: self._MAX_REASON_LEN]

        self._cancelled_requests.add(request_id)
        self._cancelled_order.append(request_id)
        self._cancellation_reasons[request_id] = reason

        # Bound the set: FIFO-evict the oldest cancelled ids beyond the cap so
        # a client streaming unique ids cannot grow it without bound.
        while len(self._cancelled_order) > self._MAX_CANCELLED_REQUESTS:
            evicted = self._cancelled_order.popleft()
            self._cancelled_requests.discard(evicted)
            self._cancellation_reasons.pop(evicted, None)

        # Create cancellation notification
        notification = CancelledNotification.create(request_id, reason)

        # Call cancellation callbacks
        for callback in self._cancellation_callbacks.get(request_id, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(notification)
                else:
                    callback(notification)
            except Exception as e:
                logger.error(f"Cancellation callback error: {e}")

        # Run cleanup functions
        for cleanup in self._request_cleanup.get(request_id, []):
            try:
                if asyncio.iscoroutinefunction(cleanup):
                    await cleanup()
                else:
                    cleanup()
            except Exception as e:
                logger.error(f"Cleanup error for {request_id}: {e}")

        # Clean up tracking
        self._cancellation_callbacks.pop(request_id, None)
        self._request_cleanup.pop(request_id, None)

        logger.info(f"Cancelled request: {request_id}")

    def is_cancelled(self, request_id: str) -> bool:
        """Check if a request is cancelled.

        Args:
            request_id: Request ID to check

        Returns:
            True if cancelled
        """
        return request_id in self._cancelled_requests

    def add_cancellation_callback(self, request_id: str, callback: Callable) -> None:
        """Add callback for request cancellation.

        Args:
            request_id: Request ID
            callback: Callback function
        """
        if request_id not in self._cancellation_callbacks:
            self._cancellation_callbacks[request_id] = []
        self._cancellation_callbacks[request_id].append(callback)

    def add_cleanup_function(self, request_id: str, cleanup: Callable) -> None:
        """Add cleanup function for request.

        Args:
            request_id: Request ID
            cleanup: Cleanup function
        """
        if request_id not in self._request_cleanup:
            self._request_cleanup[request_id] = []
        self._request_cleanup[request_id].append(cleanup)

    def clear_cancelled_request(self, request_id: str) -> None:
        """Clear cancelled request from tracking.

        Args:
            request_id: Request ID to clear
        """
        self._cancelled_requests.discard(request_id)
        self._cancellation_reasons.pop(request_id, None)
        try:
            self._cancelled_order.remove(request_id)
        except ValueError:
            pass

    def clear_cancelled_by_prefix(self, prefix: str) -> int:
        """Drop all cancelled-request state whose id starts with ``prefix``.

        The server keys cancellation by a ``client_id``-prefixed composite; on
        client disconnect it calls this with ``f"{client_id}\\x00"`` to evict
        that one client's cancellation state (bounded-state cleanup — the
        per-client eviction the disconnect handler needs). Returns the number
        of ids removed.
        """
        to_remove = [rid for rid in self._cancelled_requests if rid.startswith(prefix)]
        if not to_remove:
            return 0
        removed = set(to_remove)
        for rid in to_remove:
            self._cancelled_requests.discard(rid)
            self._cancellation_reasons.pop(rid, None)
            self._cancellation_callbacks.pop(rid, None)
            self._request_cleanup.pop(rid, None)
        remaining = [rid for rid in self._cancelled_order if rid not in removed]
        self._cancelled_order.clear()
        self._cancelled_order.extend(remaining)
        return len(to_remove)

    def get_cancellation_reason(self, request_id: str) -> Optional[str]:
        """Get cancellation reason for a request.

        Args:
            request_id: Request ID to check

        Returns:
            Cancellation reason if cancelled, None otherwise
        """
        return self._cancellation_reasons.get(request_id)


class CompletionManager:
    """Manages auto-completion for prompts and resources."""

    def __init__(self):
        """Initialize completion manager."""
        self._completion_providers: Dict[str, Callable] = {}
        self._available_tools = []
        self._available_resources = []

    def register_completion_provider(self, ref_type: str, provider: Callable) -> None:
        """Register completion provider for a reference type.

        Args:
            ref_type: Reference type (e.g., "prompts", "resources")
            provider: Completion provider function
        """
        self._completion_providers[ref_type] = provider

    async def get_completions(
        self,
        completion_type: Optional[str] = None,
        ref_type: Optional[str] = None,
        ref_name: Optional[str] = None,
        partial: Optional[str] = None,
        prefix: Optional[str] = None,
    ) -> List[Any]:
        """Get completions for a reference.

        Args:
            completion_type: Type of completion ("tools", "resources", etc)
            ref_type: Reference type (e.g., "tools", "resources", "prompts")
            ref_name: Reference name (optional)
            partial: Partial input to complete (optional)
            prefix: Prefix to filter completions (optional)

        Returns:
            List of completion items
        """
        # Handle different argument patterns
        type_to_use = completion_type or ref_type
        filter_text = prefix or partial

        if type_to_use == "tools":
            tools = self._get_available_tools()
            if filter_text:
                return [t for t in tools if t.get("name", "").startswith(filter_text)]
            return tools
        elif type_to_use == "resources":
            resources = self._get_available_resources()
            if filter_text:
                return [
                    r for r in resources if r.get("uri", "").startswith(filter_text)
                ]
            return resources

        # Use registered provider if available
        provider = self._completion_providers.get(type_to_use)  # type: ignore[reportArgumentType]
        if not provider:
            return []

        try:
            if asyncio.iscoroutinefunction(provider):
                completions = await provider(ref_name, filter_text)
            else:
                completions = provider(ref_name, filter_text)

            if isinstance(completions, list):
                return completions
            else:
                return []

        except Exception as e:
            logger.error(f"Completion provider error: {e}")
            return []

    def _get_available_tools(self) -> List[Dict[str, Any]]:
        """Get available tools for completion."""
        return self._available_tools

    def _get_available_resources(self) -> List[Dict[str, Any]]:
        """Get available resources for completion."""
        return self._available_resources


class SamplingManager:
    """Manages LLM sampling requests from server to client."""

    def __init__(self):
        """Initialize sampling manager."""
        self._sampling_callbacks: List[Callable] = []
        self._samples: List[Dict[str, Any]] = []

    def add_sampling_callback(self, callback: Callable) -> None:
        """Add callback for sampling requests.

        Args:
            callback: Sampling callback function
        """
        self._sampling_callbacks.append(callback)

    async def request_sampling(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> Dict[str, Any]:
        """Request LLM sampling from client.

        Args:
            messages: Messages for sampling
            **kwargs: Additional sampling parameters

        Returns:
            Sampling result
        """
        request = SamplingRequest.create(messages, **kwargs)

        # Try each callback until one handles the request
        for callback in self._sampling_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    result = await callback(request)
                else:
                    result = callback(request)

                if result is not None:
                    return result

            except Exception as e:
                logger.error(f"Sampling callback error: {e}")

        raise MCPError(
            "No sampling provider available", error_code=MCPErrorCode.METHOD_NOT_FOUND
        )

    async def create_message_sample(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> Dict[str, Any]:
        """Create a message sample.

        Args:
            messages: Messages for sampling
            **kwargs: Additional sampling parameters including model_preferences, metadata

        Returns:
            Sampling result with sample_id and timestamp
        """
        # Create sample with required fields
        sample = {
            "messages": messages,
            "sample_id": f"sample_{uuid.uuid4().hex[:8]}",
            "timestamp": time.time(),
        }

        # Add optional fields
        if "model_preferences" in kwargs:
            sample["model_preferences"] = kwargs["model_preferences"]
        if "metadata" in kwargs:
            sample["metadata"] = kwargs["metadata"]

        # Store in history
        self._samples.append(sample)

        return sample

    def get_sample_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get sampling history.

        Args:
            limit: Maximum number of samples to return

        Returns:
            List of sample history entries
        """
        if limit is None:
            return self._samples.copy()
        return self._samples[-limit:] if limit > 0 else []

    def clear_sample_history(self) -> None:
        """Clear sampling history."""
        self._samples.clear()


class RootsManager:
    """Manages file system roots access."""

    def __init__(self):
        """Initialize roots manager."""
        self._roots: List[Dict[str, Any]] = []
        self._access_validators: List[Callable] = []

    def add_root(
        self, uri: str, name: Optional[str] = None, description: Optional[str] = None
    ) -> None:
        """Add a file system root.

        Args:
            uri: Root URI
            name: Optional name for the root
            description: Optional description for the root
        """
        root = {"uri": uri}
        if name:
            root["name"] = name
        if description:
            root["description"] = description

        self._roots.append(root)
        logger.info(f"Added root: {uri}")

    def remove_root(self, uri: str) -> bool:
        """Remove a file system root.

        Args:
            uri: Root URI to remove

        Returns:
            True if removed
        """
        for i, root in enumerate(self._roots):
            if root["uri"] == uri:
                del self._roots[i]
                logger.info(f"Removed root: {uri}")
                return True
        return False

    def list_roots(self) -> List[Dict[str, Any]]:
        """List all file system roots.

        Returns:
            List of root objects
        """
        return self._roots.copy()

    @staticmethod
    def _normalize_uri(uri: str) -> "Optional[tuple[str, str, str]]":
        """Return ``(scheme, netloc, normalized_path)`` for ``uri`` or ``None``.

        The path component is percent-decoded ONCE (``urllib.parse.unquote``)
        then normalised (``posixpath.normpath``). ANY decoded path carrying a
        ``..`` traversal segment is REJECTED (returns ``None``) — a crafted
        ``file:///workspace/../../etc/passwd`` (or its ``%2e%2e`` percent-encoded
        form) MUST NOT be treated as within any root. The reject fires BEFORE
        ``normpath`` collapses the ``..`` and hides the escape (security.md —
        path normalization / root-URI consent).
        """
        try:
            parts = urlsplit(uri)
        except ValueError:
            return None
        decoded_path = unquote(parts.path)
        # Reject any traversal segment BEFORE normalisation collapses it.
        if any(seg == ".." for seg in decoded_path.split("/")):
            return None
        normalized = posixpath.normpath(decoded_path) if decoded_path else decoded_path
        return (parts.scheme.lower(), parts.netloc, normalized)

    @staticmethod
    def _uri_within_root(uri: str, root_uri: str) -> bool:
        """Return True only when ``uri`` is the root itself or a path-SEGMENT
        descendant of it, after normalisation.

        Two security boundaries compose here:

        * **Path-SEGMENT (not substring) matching** — a bare
          ``uri.startswith(root_uri)`` authorizes ``file:///workspace-evil``
          when ``file:///workspace`` is granted; the trailing-slash boundary
          rejects a sibling directory sharing a name prefix.
        * **Normalisation** — both URIs are percent-decoded once and
          ``posixpath.normpath``-ed, and any ``..`` traversal segment is
          rejected outright (``_normalize_uri`` returns ``None``), so
          ``file:///workspace/../../etc/passwd`` no longer lexically matches
          ``file:///workspace/`` (security.md — no fail-open).

        The scheme + authority (netloc) MUST also match; a URI on a different
        scheme/host is never within the root.
        """
        u = RootsManager._normalize_uri(uri)
        r = RootsManager._normalize_uri(root_uri)
        if u is None or r is None:
            return False
        u_scheme, u_netloc, u_path = u
        r_scheme, r_netloc, r_path = r
        if u_scheme != r_scheme or u_netloc != r_netloc:
            return False
        if u_path == r_path:
            return True
        boundary = r_path if r_path.endswith("/") else r_path + "/"
        return u_path.startswith(boundary)

    def find_root_for_uri(self, uri: str) -> Optional[Dict[str, Any]]:
        """Find the root that contains the given URI.

        Args:
            uri: URI to find root for

        Returns:
            Root object if found, None otherwise
        """
        for root in self._roots:
            if self._uri_within_root(uri, root["uri"]):
                return root
        return None

    def add_access_validator(self, validator: Callable) -> None:
        """Add access validator for roots.

        Args:
            validator: Validator function
        """
        self._access_validators.append(validator)

    async def validate_access(
        self,
        uri: str,
        operation: str = "read",
        user_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Validate access to a URI.

        Args:
            uri: URI to validate.
            operation: Operation type.
            user_context: Optional caller/session context (e.g. the client's
                declared capabilities + identity). Forwarded to any registered
                access validator whose signature accepts it, so the consent
                decision can be scoped per-caller. The server call site
                (``MCPServer._handle_roots_list``) passes the client's
                ``client_info`` entry here; a validator that never landed this
                parameter previously raised ``TypeError`` (the latent bug this
                fixes).

        Returns:
            True if access is allowed.
        """
        # Check if URI is under any root — path-SEGMENT matching (security.md),
        # NOT substring, so ``file:///workspace`` does not authorize
        # ``file:///workspace-evil``.
        is_under_root = False
        for root in self._roots:
            if self._uri_within_root(uri, root["uri"]):
                is_under_root = True
                break

        if not is_under_root:
            return False

        # Run access validators. A validator may opt into the per-caller
        # decision by declaring a third parameter; two-arg validators keep the
        # legacy (uri, operation) contract. This consumes ``user_context`` in
        # the consent decision (zero-tolerance Rule 3c) without breaking
        # pre-existing 2-arg validators.
        for validator in self._access_validators:
            try:
                accepts_context = len(inspect.signature(validator).parameters) >= 3
                if asyncio.iscoroutinefunction(validator):
                    if accepts_context:
                        allowed = await validator(uri, operation, user_context)
                    else:
                        allowed = await validator(uri, operation)
                else:
                    if accepts_context:
                        allowed = validator(uri, operation, user_context)
                    else:
                        allowed = validator(uri, operation)

                if not allowed:
                    return False

            except Exception as e:
                logger.error(f"Access validator error: {e}")
                return False

        return True


class ProtocolManager:
    """Central manager for all MCP protocol features."""

    def __init__(self):
        """Initialize protocol manager."""
        self.progress = ProgressManager()
        self.cancellation = CancellationManager()
        self.completion = CompletionManager()
        self.sampling = SamplingManager()
        self.roots = RootsManager()

        # Protocol state
        self._initialized = False
        self._client_capabilities: Dict[str, Any] = {}
        self._server_capabilities: Dict[str, Any] = {}
        self._handlers: Dict[str, Callable] = {}

    def set_initialized(self, client_capabilities: Dict[str, Any]) -> None:
        """Set protocol as initialized with client capabilities.

        Args:
            client_capabilities: Client capability advertisement
        """
        self._initialized = True
        self._client_capabilities = client_capabilities
        logger.info("MCP protocol initialized")

    def is_initialized(self) -> bool:
        """Check if protocol is initialized."""
        return self._initialized

    def get_client_capabilities(self) -> Dict[str, Any]:
        """Get client capabilities."""
        return self._client_capabilities.copy()

    def set_server_capabilities(self, capabilities: Dict[str, Any]) -> None:
        """Set server capabilities.

        Args:
            capabilities: Server capabilities
        """
        self._server_capabilities = capabilities

    def get_server_capabilities(self) -> Dict[str, Any]:
        """Get server capabilities."""
        return self._server_capabilities.copy()

    def supports_progress(self) -> bool:
        """Check if client supports progress reporting."""
        return self._client_capabilities.get("experimental", {}).get(
            "progressNotifications", False
        )

    def supports_cancellation(self) -> bool:
        """Check if client supports cancellation."""
        return True  # Basic support assumed

    def supports_completion(self) -> bool:
        """Check if client supports completion."""
        return self._client_capabilities.get("experimental", {}).get(
            "completion", False
        )

    def supports_sampling(self) -> bool:
        """Check if client supports sampling."""
        return self._client_capabilities.get("experimental", {}).get("sampling", False)

    def supports_roots(self) -> bool:
        """Check if client supports roots."""
        return self._client_capabilities.get("roots", {}).get("listChanged", False)

    def _get_handler(self, method: str) -> Optional[Callable]:
        """Get handler for a method.

        Args:
            method: Method name

        Returns:
            Handler function or None
        """
        return self._handlers.get(method)

    def register_handler(self, method: str, handler: Callable) -> None:
        """Register a handler for a method.

        Args:
            method: Method name
            handler: Handler function
        """
        self._handlers[method] = handler

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an incoming request.

        Args:
            request: Request message

        Returns:
            Response message
        """
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        handler = self._get_handler(method)  # type: ignore[arg-type]
        if not handler:
            raise MCPError(
                f"Method not found: {method}", error_code=MCPErrorCode.METHOD_NOT_FOUND
            )

        try:
            # Call handler
            if asyncio.iscoroutinefunction(handler):
                result = await handler(request)
            else:
                result = handler(request)

            # Build response
            response = {"jsonrpc": "2.0", "result": result, "id": request_id}
            return response

        except MCPError:
            raise
        except Exception as e:
            logger.error(f"Handler error for {method}: {e}")
            raise MCPError(str(e), error_code=MCPErrorCode.INTERNAL_ERROR)

    def validate_message_type(self, message: Dict[str, Any]) -> MessageType:
        """Validate and determine message type.

        Args:
            message: Message to validate

        Returns:
            Message type

        Raises:
            MCPError: If message is invalid
        """
        if "jsonrpc" not in message or message["jsonrpc"] != "2.0":
            raise MCPError(
                "Invalid JSON-RPC version", error_code=MCPErrorCode.INVALID_REQUEST
            )

        if "method" not in message:
            raise MCPError(
                "Missing method field", error_code=MCPErrorCode.INVALID_REQUEST
            )

        # Check if it's a request or notification
        if "id" in message:
            return MessageType.REQUEST
        else:
            return MessageType.NOTIFICATION


# Global protocol manager instance
_protocol_manager: Optional[ProtocolManager] = None


def get_protocol_manager() -> ProtocolManager:
    """Get global protocol manager instance."""
    global _protocol_manager
    if _protocol_manager is None:
        _protocol_manager = ProtocolManager()
    return _protocol_manager


# Convenience functions
def start_progress(operation_name: str, total: Optional[float] = None) -> ProgressToken:
    """Start progress tracking."""
    return get_protocol_manager().progress.start_progress(operation_name, total)


async def update_progress(
    token: ProgressToken, progress: Optional[float] = None, status: Optional[str] = None
) -> None:
    """Update progress."""
    await get_protocol_manager().progress.update_progress(token, progress, status)


async def complete_progress(token: ProgressToken, status: str = "completed") -> None:
    """Complete progress."""
    await get_protocol_manager().progress.complete_progress(token, status)


def is_cancelled(request_id: str) -> bool:
    """Check if request is cancelled."""
    return get_protocol_manager().cancellation.is_cancelled(request_id)


async def cancel_request(request_id: str, reason: Optional[str] = None) -> None:
    """Cancel a request."""
    await get_protocol_manager().cancellation.cancel_request(request_id, reason)
