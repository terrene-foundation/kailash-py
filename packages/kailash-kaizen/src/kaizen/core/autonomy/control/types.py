"""
Control Protocol Core Types

Defines the core message types for bidirectional agent-client communication:
- ControlRequest: Messages from agent to client (questions, approvals, progress)
- ControlResponse: Messages from client to agent (answers, confirmations, errors)

All types support JSON serialization for transport-agnostic communication.

Design Principles:
- Type safety with dataclasses and Literal types
- Immutable structures (frozen dataclasses)
- Clear error handling with explicit error field
- UUID-based request IDs for reliable pairing
- Explicit is better than implicit (no defaults for fallbacks)

Example Usage:
    # Create request
    request = ControlRequest.create(
        type="question",
        data={"question": "Proceed with deletion?", "options": ["yes", "no"]}
    )

    # Serialize for transport
    json_str = request.to_json()

    # Deserialize response
    response = ControlResponse.from_json(json_str)
    if response.is_error:
        raise RuntimeError(f"Control error: {response.error}")

    answer = response.data["answer"]
"""

import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any, Literal

# Message type constants
MESSAGE_TYPES = {"user_input", "approval", "progress_update", "question"}
MessageType = Literal["user_input", "approval", "progress_update", "question"]


@dataclass(frozen=True)
class ControlRequest:
    """
    Request message from agent to client.

    Represents a bidirectional control request where the agent asks the client
    for input, approval, or sends progress updates.

    Attributes:
        request_id: Unique identifier for request/response pairing (e.g., "req_a1b2c3d4")
        type: Type of request (user_input, approval, progress_update, question)
        data: Request-specific data as key-value pairs

    Thread Safety: Immutable (frozen dataclass)
    Serialization: JSON via to_json()/from_json()

    Example:
        request = ControlRequest.create(
            "approval",
            {"action": "delete_files", "count": 100}
        )
    """

    request_id: str
    type: MessageType
    data: dict[str, Any]

    @classmethod
    def create(cls, type: str, data: dict[str, Any]) -> "ControlRequest":
        """
        Create a new ControlRequest with auto-generated request ID.

        Args:
            type: Message type (must be one of: user_input, approval, progress_update, question)
            data: Request data as dictionary

        Returns:
            New ControlRequest instance

        Raises:
            ValueError: If type is not a valid message type
            TypeError: If data is not a dictionary

        Example:
            request = ControlRequest.create(
                "question",
                {"question": "Which format?", "options": ["json", "xml"]}
            )
        """
        # Validate message type
        if type not in MESSAGE_TYPES:
            raise ValueError(
                f"Invalid message type: '{type}'. "
                f"Must be one of: {', '.join(sorted(MESSAGE_TYPES))}"
            )

        # Validate data type
        if not isinstance(data, dict):
            raise TypeError(
                f"Request data must be a dict, got {type(data).__name__}. "
                f"Provide data as key-value pairs: {{'key': 'value'}}"
            )

        # Generate request ID
        request_id = f"req_{uuid.uuid4().hex[:8]}"

        return cls(request_id=request_id, type=type, data=data)

    def to_json(self) -> str:
        """
        Serialize request to JSON string.

        Returns:
            JSON string representation

        Example:
            json_str = request.to_json()
            # '{"request_id": "req_a1b2c3d4", "type": "question", "data": {...}}'
        """
        return json.dumps(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """
        Convert request to dictionary.

        Returns:
            Dictionary with request_id, type, and data fields

        Example:
            data = request.to_dict()
            # {"request_id": "req_...", "type": "question", "data": {...}}
        """
        return asdict(self)

    @classmethod
    def from_json(cls, json_str: str) -> "ControlRequest":
        """
        Deserialize request from JSON string.

        Args:
            json_str: JSON string to deserialize

        Returns:
            ControlRequest instance

        Raises:
            json.JSONDecodeError: If JSON is invalid
            KeyError: If required fields are missing
            ValueError: If type is invalid

        Example:
            request = ControlRequest.from_json(json_string)
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlRequest":
        """
        Create request from dictionary.

        Args:
            data: Dictionary with request_id, type, and data fields

        Returns:
            ControlRequest instance

        Raises:
            KeyError: If required fields are missing (request_id, type, data)
            ValueError: If type is invalid

        Example:
            request = ControlRequest.from_dict({
                "request_id": "req_test",
                "type": "question",
                "data": {"question": "Proceed?"}
            })
        """
        # Validate required fields
        required_fields = {"request_id", "type", "data"}
        missing_fields = required_fields - set(data.keys())
        if missing_fields:
            raise KeyError(
                f"Missing required fields: {', '.join(sorted(missing_fields))}. "
                f"Required: {', '.join(sorted(required_fields))}"
            )

        # Validate message type
        msg_type = data["type"]
        if msg_type not in MESSAGE_TYPES:
            raise ValueError(
                f"Invalid message type: '{msg_type}'. "
                f"Must be one of: {', '.join(sorted(MESSAGE_TYPES))}"
            )

        return cls(request_id=data["request_id"], type=data["type"], data=data["data"])


@dataclass(frozen=True)
class ControlResponse:
    """
    Response message from client to agent.

    Represents a response to a ControlRequest, containing either successful data
    or an error message.

    Attributes:
        request_id: ID of the request this responds to (must match ControlRequest.request_id)
        data: Response data as key-value pairs (None if error occurred)
        error: Error message if request failed (None if successful)

    Thread Safety: Immutable (frozen dataclass)
    Serialization: JSON via to_json()/from_json()

    Error Handling:
        - If error is not None, response.is_error returns True
        - Both data and error can be set (error takes precedence in is_error)
        - Neither data nor error being set is valid (represents acknowledgment)

    Example:
        # Success response
        response = ControlResponse(
            request_id="req_a1b2c3d4",
            data={"answer": "yes", "confidence": 0.95}
        )

        # Error response
        response = ControlResponse(
            request_id="req_a1b2c3d4",
            error="User cancelled operation"
        )
    """

    request_id: str
    data: dict[str, Any] | None = None
    error: str | None = None

    @property
    def is_error(self) -> bool:
        """
        Check if response represents an error.

        Returns:
            True if error field is not None, False otherwise

        Example:
            if response.is_error:
                print(f"Error: {response.error}")
            else:
                print(f"Success: {response.data}")
        """
        return self.error is not None

    def to_json(self) -> str:
        """
        Serialize response to JSON string.

        Returns:
            JSON string representation

        Example:
            json_str = response.to_json()
            # '{"request_id": "req_...", "data": {...}, "error": null}'
        """
        return json.dumps(self.to_dict())

    def to_dict(self) -> dict[str, Any]:
        """
        Convert response to dictionary.

        Returns:
            Dictionary with request_id, data, and error fields

        Example:
            data = response.to_dict()
            # {"request_id": "req_...", "data": {...}, "error": null}
        """
        return asdict(self)

    @classmethod
    def from_json(cls, json_str: str) -> "ControlResponse":
        """
        Deserialize response from JSON string.

        Args:
            json_str: JSON string to deserialize

        Returns:
            ControlResponse instance

        Raises:
            json.JSONDecodeError: If JSON is invalid
            KeyError: If request_id field is missing

        Example:
            response = ControlResponse.from_json(json_string)
        """
        data = json.loads(json_str)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlResponse":
        """
        Create response from dictionary.

        Args:
            data: Dictionary with at minimum request_id field

        Returns:
            ControlResponse instance

        Raises:
            KeyError: If request_id field is missing

        Example:
            response = ControlResponse.from_dict({
                "request_id": "req_test",
                "data": {"result": "ok"},
                "error": None
            })
        """
        # Validate required field
        if "request_id" not in data:
            raise KeyError(
                "Missing required field: 'request_id'. "
                "Response must reference the original request ID."
            )

        return cls(
            request_id=data["request_id"],
            data=data.get("data"),
            error=data.get("error"),
        )


# Public API exports
__all__ = [
    "ControlRequest",
    "ControlResponse",
    "MessageType",
    "MESSAGE_TYPES",
]
