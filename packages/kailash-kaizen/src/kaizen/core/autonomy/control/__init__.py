"""
Control Protocol Module

Bidirectional communication protocol for autonomous agent capabilities.

This module provides the core types and transport layer for control protocol
communication, enabling agents to ask questions, request approvals, and report
progress during execution.

Components:
    - ControlRequest: Agent-to-client messages
    - ControlResponse: Client-to-agent messages
    - Transport: Abstract base class for bidirectional communication
    - TransportProtocol: Runtime-checkable protocol for transports

Example:
    from kaizen.core.autonomy.control import ControlRequest, ControlResponse, Transport

    # Agent creates request
    request = ControlRequest.create(
        "question",
        {"question": "Proceed with deletion?", "options": ["yes", "no"]}
    )

    # Client creates response
    response = ControlResponse(
        request_id=request.request_id,
        data={"answer": "yes"}
    )

    # Use transport for communication
    transport = CLITransport()
    await transport.connect()
    await transport.write(request.to_json())

See Also:
    - docs/architecture/adr/011-control-protocol-architecture.md
    - todos/active/TODO-159-control-protocol-implementation.md
"""

from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transport import Transport, TransportProtocol
from kaizen.core.autonomy.control.transports import (
    CLITransport,
    HTTPTransport,
    StdioTransport,
)
from kaizen.core.autonomy.control.types import (
    MESSAGE_TYPES,
    ControlRequest,
    ControlResponse,
    MessageType,
)

__all__ = [
    "ControlRequest",
    "ControlResponse",
    "MessageType",
    "MESSAGE_TYPES",
    "Transport",
    "TransportProtocol",
    "ControlProtocol",
    "CLITransport",
    "HTTPTransport",
    "StdioTransport",
]
