# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""
A2A 1.0 core messaging data model.

Implements the message/task types defined by the A2A protocol specification
v1.0 (``a2aproject/A2A`` tag ``v1.0.1``, ``specification/a2a.proto``).

Three wire conventions are load-bearing here and are fixed by the spec, not by
local preference:

- **Field names are camelCase.** Spec § "JSON Serialization": *"All JSON
  serializations of the A2A protocol data model MUST use camelCase naming for
  field names, not the snake_case convention used in Protocol Buffer
  definitions."* So ``message_id`` on the wire is ``messageId``.
- **Enum values are ProtoJSON string names** — the SCREAMING_SNAKE_CASE symbol
  from the proto (``TASK_STATE_SUBMITTED``), not an ordinal and not a
  lowercased alias.
- **Unset optional fields are omitted**, matching proto3 JSON, so a
  round-tripped payload does not grow ``null`` keys.

``Part`` is a ``oneof`` in v1.0 — a single type carrying exactly one of
``text`` / ``raw`` / ``url`` / ``data``. This replaces the 0.2.x shape where
``TextPart``, ``FilePart`` and ``DataPart`` were separate types.
"""

from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

__all__ = [
    "Role",
    "TaskState",
    "Part",
    "Message",
    "Artifact",
    "TaskStatus",
    "Task",
    "SendMessageConfiguration",
    "SendMessageRequest",
    "SendMessageResponse",
    "GetTaskRequest",
]


class Role(str, Enum):
    """Originator of a :class:`Message` (proto ``Role``)."""

    UNSPECIFIED = "ROLE_UNSPECIFIED"
    USER = "ROLE_USER"
    AGENT = "ROLE_AGENT"


class TaskState(str, Enum):
    """Lifecycle state of a :class:`Task` (proto ``TaskState``)."""

    UNSPECIFIED = "TASK_STATE_UNSPECIFIED"
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    REJECTED = "TASK_STATE_REJECTED"
    AUTH_REQUIRED = "TASK_STATE_AUTH_REQUIRED"


#: States from which a task can no longer transition.
TERMINAL_TASK_STATES = frozenset(
    {TaskState.COMPLETED, TaskState.FAILED, TaskState.CANCELED, TaskState.REJECTED}
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_to_json(value: datetime) -> str:
    """Serialize a datetime as a ProtoJSON ``Timestamp`` (RFC 3339, UTC)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _timestamp_from_json(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _require_object(payload: Any, label: str) -> Dict[str, Any]:
    """Assert a decoded JSON value is an object before field access.

    Every ``from_dict`` below parses data that arrived over the wire, so the
    parameter is typed ``Any`` rather than ``Dict`` — annotating it ``Dict``
    would be a claim about untrusted input, and would make this guard read as
    dead code to a type checker. Without the guard a non-object payload fails
    later with an opaque ``AttributeError: 'list' object has no attribute
    'get'`` instead of naming the field that was wrong
    (``zero-tolerance.md`` Rule 3a).
    """
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object, got {type(payload).__name__}")
    return payload


@dataclass
class Part:
    """A single content part of a :class:`Message` or :class:`Artifact`.

    A ``oneof`` in the proto: exactly one of ``text``, ``raw``, ``url`` or
    ``data`` MUST be set. ``raw`` is bytes and serializes as base64, per
    ProtoJSON.
    """

    text: Optional[str] = None
    raw: Optional[bytes] = None
    url: Optional[str] = None
    data: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None
    filename: Optional[str] = None
    media_type: Optional[str] = None

    #: The ``oneof content`` members, in proto field order.
    _CONTENT_FIELDS = ("text", "raw", "url", "data")

    def __post_init__(self) -> None:
        set_fields = [f for f in self._CONTENT_FIELDS if getattr(self, f) is not None]
        if len(set_fields) != 1:
            raise ValueError(
                "Part requires exactly one of text/raw/url/data to be set "
                f"(got {len(set_fields)}: {set_fields or 'none'})"
            )

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.text is not None:
            out["text"] = self.text
        if self.raw is not None:
            out["raw"] = base64.b64encode(self.raw).decode("ascii")
        if self.url is not None:
            out["url"] = self.url
        if self.data is not None:
            out["data"] = self.data
        if self.metadata:
            out["metadata"] = self.metadata
        if self.filename is not None:
            out["filename"] = self.filename
        if self.media_type is not None:
            out["mediaType"] = self.media_type
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "Part":
        payload = _require_object(payload, "Part")
        raw = payload.get("raw")
        return cls(
            text=payload.get("text"),
            raw=base64.b64decode(raw) if raw is not None else None,
            url=payload.get("url"),
            data=payload.get("data"),
            metadata=payload.get("metadata"),
            filename=payload.get("filename"),
            media_type=payload.get("mediaType"),
        )


@dataclass
class Message:
    """A message exchanged between a client and an agent (proto ``Message``)."""

    message_id: str
    role: Role
    parts: List[Part]
    context_id: Optional[str] = None
    task_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    extensions: List[str] = field(default_factory=list)
    reference_task_ids: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.message_id:
            raise ValueError("Message.message_id is required")
        if not self.parts:
            raise ValueError("Message.parts is required and must be non-empty")
        if not isinstance(self.role, Role):
            self.role = Role(self.role)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "messageId": self.message_id,
            "role": self.role.value,
            "parts": [p.to_dict() for p in self.parts],
        }
        if self.context_id is not None:
            out["contextId"] = self.context_id
        if self.task_id is not None:
            out["taskId"] = self.task_id
        if self.metadata:
            out["metadata"] = self.metadata
        if self.extensions:
            out["extensions"] = list(self.extensions)
        if self.reference_task_ids:
            out["referenceTaskIds"] = list(self.reference_task_ids)
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "Message":
        payload = _require_object(payload, "Message")
        parts = payload.get("parts")
        if not isinstance(parts, list):
            raise ValueError("Message.parts must be an array")
        return cls(
            message_id=payload.get("messageId", ""),
            role=Role(payload.get("role", Role.UNSPECIFIED.value)),
            parts=[Part.from_dict(p) for p in parts],
            context_id=payload.get("contextId"),
            task_id=payload.get("taskId"),
            metadata=payload.get("metadata"),
            extensions=list(payload.get("extensions") or []),
            reference_task_ids=list(payload.get("referenceTaskIds") or []),
        )


@dataclass
class Artifact:
    """An output artifact produced by a task (proto ``Artifact``)."""

    artifact_id: str
    parts: List[Part]
    name: Optional[str] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    extensions: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.artifact_id:
            raise ValueError("Artifact.artifact_id is required")
        if not self.parts:
            raise ValueError("Artifact.parts is required and must be non-empty")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "artifactId": self.artifact_id,
            "parts": [p.to_dict() for p in self.parts],
        }
        if self.name is not None:
            out["name"] = self.name
        if self.description is not None:
            out["description"] = self.description
        if self.metadata:
            out["metadata"] = self.metadata
        if self.extensions:
            out["extensions"] = list(self.extensions)
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "Artifact":
        payload = _require_object(payload, "Artifact")
        return cls(
            artifact_id=payload.get("artifactId", ""),
            parts=[Part.from_dict(p) for p in payload.get("parts") or []],
            name=payload.get("name"),
            description=payload.get("description"),
            metadata=payload.get("metadata"),
            extensions=list(payload.get("extensions") or []),
        )


@dataclass
class TaskStatus:
    """Current status of a task (proto ``TaskStatus``)."""

    state: TaskState
    message: Optional[Message] = None
    timestamp: datetime = field(default_factory=_now)

    def __post_init__(self) -> None:
        if not isinstance(self.state, TaskState):
            self.state = TaskState(self.state)

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "state": self.state.value,
            "timestamp": _timestamp_to_json(self.timestamp),
        }
        if self.message is not None:
            out["message"] = self.message.to_dict()
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "TaskStatus":
        payload = _require_object(payload, "TaskStatus")
        message = payload.get("message")
        timestamp = payload.get("timestamp")
        return cls(
            state=TaskState(payload.get("state", TaskState.UNSPECIFIED.value)),
            message=Message.from_dict(message) if message else None,
            timestamp=_timestamp_from_json(timestamp) if timestamp else _now(),
        )


@dataclass
class Task:
    """A unit of work tracked by the agent (proto ``Task``)."""

    id: str
    status: TaskStatus
    context_id: Optional[str] = None
    artifacts: List[Artifact] = field(default_factory=list)
    history: List[Message] = field(default_factory=list)
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("Task.id is required")

    @property
    def is_terminal(self) -> bool:
        """True when the task can no longer transition."""
        return self.status.state in TERMINAL_TASK_STATES

    def to_dict(self, history_length: Optional[int] = None) -> Dict[str, Any]:
        """Serialize to ProtoJSON.

        Args:
            history_length: When set, return only the most recent N history
                entries. ``0`` omits history entirely. ``None`` returns all.
                Negative values are rejected — the spec has no meaning for
                them, and silently treating them as "all" would hide a caller
                bug.
        """
        history = self.history
        if history_length is not None:
            if history_length < 0:
                raise ValueError(f"history_length must be >= 0 (got {history_length})")
            history = history[len(history) - history_length :] if history_length else []

        out: Dict[str, Any] = {"id": self.id, "status": self.status.to_dict()}
        if self.context_id is not None:
            out["contextId"] = self.context_id
        if self.artifacts:
            out["artifacts"] = [a.to_dict() for a in self.artifacts]
        if history:
            out["history"] = [m.to_dict() for m in history]
        if self.metadata:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "Task":
        payload = _require_object(payload, "Task")
        return cls(
            id=payload.get("id", ""),
            status=TaskStatus.from_dict(payload.get("status") or {}),
            context_id=payload.get("contextId"),
            artifacts=[Artifact.from_dict(a) for a in payload.get("artifacts") or []],
            history=[Message.from_dict(m) for m in payload.get("history") or []],
            metadata=payload.get("metadata"),
        )


@dataclass
class SendMessageConfiguration:
    """Per-call configuration for ``SendMessage`` (proto
    ``SendMessageConfiguration``)."""

    accepted_output_modes: List[str] = field(default_factory=list)
    history_length: Optional[int] = None
    return_immediately: bool = False

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.accepted_output_modes:
            out["acceptedOutputModes"] = list(self.accepted_output_modes)
        if self.history_length is not None:
            out["historyLength"] = self.history_length
        if self.return_immediately:
            out["returnImmediately"] = True
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "SendMessageConfiguration":
        payload = _require_object(payload, "SendMessageConfiguration")
        return cls(
            accepted_output_modes=list(payload.get("acceptedOutputModes") or []),
            history_length=payload.get("historyLength"),
            return_immediately=bool(payload.get("returnImmediately", False)),
        )


@dataclass
class SendMessageRequest:
    """Params of the ``SendMessage`` JSON-RPC method."""

    message: Message
    tenant: Optional[str] = None
    configuration: Optional[SendMessageConfiguration] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"message": self.message.to_dict()}
        if self.tenant:
            out["tenant"] = self.tenant
        if self.configuration is not None:
            config = self.configuration.to_dict()
            if config:
                out["configuration"] = config
        if self.metadata:
            out["metadata"] = self.metadata
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "SendMessageRequest":
        payload = _require_object(payload, "SendMessageRequest")
        message = _require_object(payload.get("message"), "SendMessageRequest.message")
        configuration = payload.get("configuration")
        return cls(
            message=Message.from_dict(message),
            tenant=payload.get("tenant"),
            configuration=(
                SendMessageConfiguration.from_dict(configuration)
                if isinstance(configuration, dict)
                else None
            ),
            metadata=payload.get("metadata"),
        )


@dataclass
class SendMessageResponse:
    """Result of ``SendMessage`` — a ``oneof`` of ``task`` or ``message``."""

    task: Optional[Task] = None
    message: Optional[Message] = None

    def __post_init__(self) -> None:
        if (self.task is None) == (self.message is None):
            raise ValueError("SendMessageResponse requires exactly one of task/message")

    def to_dict(self) -> Dict[str, Any]:
        return self.to_dict_with_history(None)

    def to_dict_with_history(self, history_length: Optional[int]) -> Dict[str, Any]:
        """Serialize, applying the caller's ``historyLength`` to the task arm.

        ``historyLength`` comes from ``SendMessageConfiguration`` and only has
        meaning for the ``task`` arm of the oneof — a bare ``Message`` reply
        carries no history to trim.
        """
        if self.task is not None:
            return {"task": self.task.to_dict(history_length=history_length)}
        assert self.message is not None  # guaranteed by __post_init__
        return {"message": self.message.to_dict()}

    @classmethod
    def from_dict(cls, payload: Any) -> "SendMessageResponse":
        payload = _require_object(payload, "SendMessageResponse")
        task = payload.get("task")
        message = payload.get("message")
        return cls(
            task=Task.from_dict(task) if task else None,
            message=Message.from_dict(message) if message else None,
        )


@dataclass
class GetTaskRequest:
    """Params of the ``GetTask`` JSON-RPC method."""

    id: str
    tenant: Optional[str] = None
    history_length: Optional[int] = None

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("GetTaskRequest.id is required")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"id": self.id}
        if self.tenant:
            out["tenant"] = self.tenant
        if self.history_length is not None:
            out["historyLength"] = self.history_length
        return out

    @classmethod
    def from_dict(cls, payload: Any) -> "GetTaskRequest":
        payload = _require_object(payload, "GetTaskRequest")
        return cls(
            id=payload.get("id", ""),
            tenant=payload.get("tenant"),
            history_length=payload.get("historyLength"),
        )
