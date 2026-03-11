"""
Transport Implementations for Control Protocol

Available Transports:
- CLITransport: Terminal-based stdin/stdout communication
- HTTPTransport: Web-based Server-Sent Events communication
- StdioTransport: Subprocess communication

Example:
    from kaizen.core.autonomy.control.transports import CLITransport, HTTPTransport, StdioTransport

    # CLI Transport
    transport = CLITransport()
    await transport.connect()
    await transport.write('{"type": "question"}')

    async for message in transport.read_messages():
        print(f"Received: {message}")
        break

    await transport.close()

    # HTTP Transport
    transport = HTTPTransport(base_url="http://localhost:8000")
    await transport.connect()
    await transport.write('{"type": "question"}')

    async for message in transport.read_messages():
        print(f"Received: {message}")
        break

    await transport.close()

    # Stdio Transport
    transport = StdioTransport()
    await transport.connect()
    await transport.write('{"type": "question"}')

    async for message in transport.read_messages():
        print(f"Received: {message}")
        break

    await transport.close()
"""

from kaizen.core.autonomy.control.transports.cli import CLITransport
from kaizen.core.autonomy.control.transports.http import HTTPTransport
from kaizen.core.autonomy.control.transports.memory import InMemoryTransport
from kaizen.core.autonomy.control.transports.stdio import StdioTransport

__all__ = [
    "CLITransport",
    "HTTPTransport",
    "StdioTransport",
    "InMemoryTransport",
]
