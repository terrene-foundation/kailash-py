# Control Protocol API Reference

Complete API reference for Kaizen Control Protocol bidirectional agent ↔ client communication.

**Version:** Kaizen v0.3.0+
**Status:** Production-ready ✅

---

## Table of Contents

1. [Overview](#overview)
2. [Core Types](#core-types)
   - [ControlRequest](#controlrequest)
   - [ControlResponse](#controlresponse)
3. [Protocol](#protocol)
   - [ControlProtocol](#controlprotocol)
4. [Transport Interface](#transport-interface)
   - [Transport ABC](#transport-abc)
5. [Transport Implementations](#transport-implementations)
   - [CLITransport](#clitransport)
   - [HTTPTransport](#httptransport)
   - [StdioTransport](#stdiotransport)
   - [InMemoryTransport](#inmemorytransport)
6. [BaseAgent Integration](#baseagent-integration)
   - [ask_user_question()](#ask_user_question)
   - [request_approval()](#request_approval)
   - [report_progress()](#report_progress)
7. [Error Handling](#error-handling)
8. [Performance](#performance)

---

## Overview

The Control Protocol provides bidirectional communication between AI agents and clients (users, web interfaces, parent processes). It enables:

- **Interactive agents** - Ask questions during execution
- **Safe operations** - Request approval for dangerous actions
- **User experience** - Report progress for long-running tasks

**Architecture:**

```
┌─────────────┐                    ┌─────────────┐
│   Agent     │◄───ControlRequest──┤   Client    │
│  (BaseAgent)│                    │  (User/UI)  │
│             │──ControlResponse──►│             │
└─────────────┘                    └─────────────┘
       ▲                                  ▲
       │                                  │
       └────────Transport Layer───────────┘
          (CLI, HTTP, stdio, memory)
```

**Key Components:**

1. **Message Types** - ControlRequest, ControlResponse (type-safe messages)
2. **Protocol** - ControlProtocol (request/response lifecycle management)
3. **Transport** - Transport ABC + implementations (communication channels)
4. **Agent Integration** - BaseAgent helper methods (convenience API)

---

## Core Types

### ControlRequest

Immutable request message sent from agent to client.

**Module:** `kaizen.core.autonomy.control.types`

```python
@dataclass(frozen=True)
class ControlRequest:
    """Request message from agent to client."""

    request_id: str
    type: str  # "question", "approval", "progress_update"
    data: dict[str, Any]
```

#### Methods

##### `create()`

Create request with auto-generated request ID.

```python
@classmethod
def create(cls, type: str, data: dict[str, Any]) -> "ControlRequest"
```

**Parameters:**
- `type` (str) - Request type: "question", "approval", "progress_update"
- `data` (dict) - Request payload (type-specific fields)

**Returns:**
- `ControlRequest` - New request with auto-generated request_id (format: `req_{8_hex_chars}`)

**Example:**

```python
from kaizen.core.autonomy.control.types import ControlRequest

# Question request
request = ControlRequest.create(
    "question",
    {
        "question": "Which file should I process?",
        "options": ["file1.txt", "file2.txt", "all"]
    }
)
# request.request_id = "req_a1b2c3d4"

# Approval request
request = ControlRequest.create(
    "approval",
    {
        "action": "Delete 100 files",
        "details": {"count": 100, "total_size_mb": 250}
    }
)

# Progress update request
request = ControlRequest.create(
    "progress_update",
    {
        "message": "Processing file 5 of 10",
        "percentage": 50.0,
        "details": {"current": 5, "total": 10}
    }
)
```

##### `to_json()`

Serialize request to JSON string.

```python
def to_json(self) -> str
```

**Returns:**
- `str` - JSON-serialized request

**Example:**

```python
request = ControlRequest.create("question", {"question": "Continue?"})
json_str = request.to_json()
# '{"request_id": "req_a1b2c3d4", "type": "question", "data": {"question": "Continue?"}}'
```

##### `from_dict()`

Deserialize request from dictionary.

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "ControlRequest"
```

**Parameters:**
- `data` (dict) - Dictionary with request_id, type, data fields

**Returns:**
- `ControlRequest` - Deserialized request

**Raises:**
- `KeyError` - If required fields missing
- `ValueError` - If fields have invalid types

**Example:**

```python
data = {
    "request_id": "req_abc123",
    "type": "question",
    "data": {"question": "Continue?"}
}
request = ControlRequest.from_dict(data)
```

---

### ControlResponse

Immutable response message sent from client to agent.

**Module:** `kaizen.core.autonomy.control.types`

```python
@dataclass(frozen=True)
class ControlResponse:
    """Response message from client to agent."""

    request_id: str
    data: dict[str, Any] | None = None
    error: str | None = None
```

#### Properties

##### `is_error`

Check if response represents an error.

```python
@property
def is_error(self) -> bool
```

**Returns:**
- `bool` - True if error field is not None, False otherwise

**Example:**

```python
response = ControlResponse(request_id="req_123", error="User cancelled")
if response.is_error:
    print(f"Error: {response.error}")
```

#### Methods

##### `to_json()`

Serialize response to JSON string.

```python
def to_json(self) -> str
```

**Returns:**
- `str` - JSON-serialized response

**Example:**

```python
response = ControlResponse(
    request_id="req_123",
    data={"answer": "file1.txt"}
)
json_str = response.to_json()
```

##### `from_dict()`

Deserialize response from dictionary.

```python
@classmethod
def from_dict(cls, data: dict[str, Any]) -> "ControlResponse"
```

**Parameters:**
- `data` (dict) - Dictionary with request_id, data (optional), error (optional)

**Returns:**
- `ControlResponse` - Deserialized response

**Raises:**
- `KeyError` - If request_id field missing
- `ValueError` - If both data and error are None

**Example:**

```python
# Success response
data = {"request_id": "req_123", "data": {"answer": "yes"}}
response = ControlResponse.from_dict(data)

# Error response
data = {"request_id": "req_123", "error": "Timeout"}
response = ControlResponse.from_dict(data)
```

---

## Protocol

### ControlProtocol

Manages request/response pairing, background message reading, and protocol lifecycle.

**Module:** `kaizen.core.autonomy.control.protocol`

```python
class ControlProtocol:
    """Control protocol for bidirectional agent-client communication."""

    def __init__(self, transport: Transport):
        """Initialize with transport."""
```

#### Constructor

```python
def __init__(self, transport: Transport)
```

**Parameters:**
- `transport` (Transport) - Transport implementation for communication

**Raises:**
- `TypeError` - If transport is not a Transport instance

**Example:**

```python
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

transport = CLITransport()
protocol = ControlProtocol(transport=transport)
```

#### Methods

##### `start()`

Start the control protocol.

```python
async def start(self, task_group: TaskGroup) -> None
```

**Description:**

Connects transport and launches background message reader in the provided task group. Must be called before send_request().

**Parameters:**
- `task_group` (anyio.TaskGroup) - Task group to run background reader in

**Raises:**
- `RuntimeError` - If already started
- `ConnectionError` - If transport connection fails

**Example:**

```python
import anyio
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

transport = CLITransport()
protocol = ControlProtocol(transport=transport)

async with anyio.create_task_group() as tg:
    await protocol.start(tg)

    # ... send requests ...

    await protocol.stop()
```

##### `stop()`

Stop the control protocol gracefully.

```python
async def stop() -> None
```

**Description:**

Closes transport, cancels pending requests, and cleans up resources. Idempotent - safe to call multiple times.

**Example:**

```python
await protocol.stop()
await protocol.stop()  # Safe to call again
```

##### `send_request()`

Send request and wait for response with timeout.

```python
async def send_request(
    self,
    request: ControlRequest,
    timeout: float = 60.0
) -> ControlResponse
```

**Description:**

Writes request to transport, waits for matching response by request_id, and returns the response. Uses anyio.fail_after for timeout handling.

**Parameters:**
- `request` (ControlRequest) - Request to send
- `timeout` (float) - Maximum seconds to wait for response (default: 60.0)

**Returns:**
- `ControlResponse` - Response from client

**Raises:**
- `RuntimeError` - If protocol not started
- `TimeoutError` - If no response received within timeout
- `ConnectionError` - If transport write fails

**Example:**

```python
from kaizen.core.autonomy.control.types import ControlRequest

# Create and send request
request = ControlRequest.create("approval", {"action": "delete files"})
response = await protocol.send_request(request, timeout=30.0)

if response.is_error:
    raise RuntimeError(f"Request failed: {response.error}")

approved = response.data.get("approved", False)
print(f"Approved: {approved}")
```

---

## Transport Interface

### Transport ABC

Abstract base class defining the interface for all transport implementations.

**Module:** `kaizen.core.autonomy.control.transport`

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator

class Transport(ABC):
    """Abstract base class for bidirectional communication transports."""
```

#### Abstract Methods

##### `connect()`

Establish connection to client.

```python
@abstractmethod
async def connect(self) -> None
```

**Description:**

Called once before any read/write operations. Implementations should initialize connection resources, set up communication channels, and update ready state.

**Raises:**
- `RuntimeError` - If already connected
- `ConnectionError` - If connection fails

**Example:**

```python
await transport.connect()
```

##### `write()`

Send data to client.

```python
@abstractmethod
async def write(self, data: str) -> None
```

**Description:**

Writes a message string to the transport. Messages are typically JSON-serialized control requests or responses.

**Parameters:**
- `data` (str) - Message string to send (typically JSON)

**Raises:**
- `RuntimeError` - If not connected
- `ConnectionError` - If connection is closed or write fails

**Example:**

```python
await transport.write('{"request_id": "req_123", "type": "question"}')
```

##### `read_messages()`

Receive messages from client.

```python
@abstractmethod
def read_messages(self) -> AsyncIterator[str]
```

**Description:**

Returns an async iterator that yields messages as they arrive. Messages are streamed incrementally, not batched.

**Returns:**
- `AsyncIterator[str]` - Async iterator yielding message strings

**Raises:**
- `RuntimeError` - If not connected

**Example:**

```python
async for message in transport.read_messages():
    response = json.loads(message)
    print(f"Got response: {response}")
    if done:
        break
```

##### `close()`

Close connection and clean up resources.

```python
@abstractmethod
async def close(self) -> None
```

**Description:**

Should be idempotent - safe to call multiple times. Implementations should close all open connections/streams, release resources, and update ready state to False.

**Example:**

```python
await transport.close()
await transport.close()  # Safe to call again
```

##### `is_ready()`

Check if transport is ready for communication.

```python
@abstractmethod
def is_ready(self) -> bool
```

**Description:**

Synchronous method for quick status checks without async overhead.

**Returns:**
- `bool` - True if connected and ready, False otherwise

**Example:**

```python
if transport.is_ready():
    await transport.write(message)
else:
    await transport.connect()
```

---

## Transport Implementations

### CLITransport

Terminal-based transport using stdin/stdout for CLI applications.

**Module:** `kaizen.core.autonomy.control.transports`

```python
from kaizen.core.autonomy.control.transports import CLITransport

class CLITransport(Transport):
    """Terminal-based transport using stdin/stdout."""
```

#### Overview

- **Use Case:** Command-line applications, local development
- **Communication:** stdin (read), stdout (write)
- **Protocol:** Line-based (one JSON message per line)
- **Performance:** Low latency (<10ms), high throughput (>1000 msg/s)

#### Constructor

```python
def __init__(self)
```

**Example:**

```python
transport = CLITransport()
```

#### Usage

```python
import anyio
from kaizen.core.autonomy.control.transports import CLITransport

transport = CLITransport()
await transport.connect()

# Write request (agent -> client via stdout)
await transport.write('{"request_id": "req_1", "type": "question"}')

# Read response (client -> agent via stdin)
async for message in transport.read_messages():
    print(f"Received: {message}")
    break

await transport.close()
```

---

### HTTPTransport

HTTP-based transport using Server-Sent Events (SSE) for web applications.

**Module:** `kaizen.core.autonomy.control.transports`

```python
from kaizen.core.autonomy.control.transports import HTTPTransport

class HTTPTransport(Transport):
    """HTTP-based transport using Server-Sent Events (SSE)."""
```

#### Overview

- **Use Case:** Web applications, real-time dashboards
- **Communication:** POST /control (write), GET /stream SSE (read)
- **Protocol:** SSE format (lines prefixed with `data: `)
- **Performance:** Network-dependent (local: <50ms, remote: varies)

#### Constructor

```python
def __init__(self, base_url: str)
```

**Parameters:**
- `base_url` (str) - Base URL for HTTP endpoints (e.g., "http://localhost:8000")

**Example:**

```python
transport = HTTPTransport(base_url="http://localhost:8000")
```

#### Usage

```python
import anyio
from kaizen.core.autonomy.control.transports import HTTPTransport

transport = HTTPTransport(base_url="http://localhost:8000")
await transport.connect()

# Write request (agent -> server via POST /control)
await transport.write('{"request_id": "req_1", "type": "question"}')

# Read response (server -> agent via GET /stream SSE)
async for message in transport.read_messages():
    print(f"Received: {message}")
    break

await transport.close()
```

#### SSE Format

Messages from `/stream` endpoint follow SSE format:

```
data: {"request_id": "req_1", "type": "question"}

: this is a comment (lines starting with : are ignored)

data: {"request_id": "req_2", "type": "approval"}

```

---

### StdioTransport

Subprocess-based transport using stdin/stdout for parent-child process communication.

**Module:** `kaizen.core.autonomy.control.transports`

```python
from kaizen.core.autonomy.control.transports import StdioTransport

class StdioTransport(Transport):
    """Subprocess-based transport using stdin/stdout."""
```

#### Overview

- **Use Case:** MCP servers, subprocess communication, piped processes
- **Communication:** stdin (read), stdout (write)
- **Protocol:** Line-based (one JSON message per line)
- **Performance:** Low latency (<10ms), high throughput (>1000 msg/s)
- **Always Ready:** No connection state (stdin/stdout always available)

#### Constructor

```python
def __init__(self)
```

**Example:**

```python
transport = StdioTransport()
```

#### Usage

```python
import anyio
from kaizen.core.autonomy.control.transports import StdioTransport

transport = StdioTransport()
# Already ready - no connect needed
assert transport.is_ready()

# Write request (child -> parent via stdout)
await transport.write('{"request_id": "req_1", "type": "question"}')

# Read response (parent -> child via stdin)
async for message in transport.read_messages():
    # Use stderr for logging (don't pollute stdout protocol)
    print(f"Received: {message}", file=sys.stderr)
    break

await transport.close()
```

#### Difference from CLITransport

| Aspect | CLITransport | StdioTransport |
|--------|--------------|----------------|
| **Use Case** | Interactive terminal (user-facing) | Programmatic subprocess (process-to-process) |
| **Connection State** | Tracks connection state | Always ready (no state tracking) |
| **Semantic Use** | User interaction | Process communication |

---

### InMemoryTransport

In-memory transport using anyio memory streams for performance testing.

**Module:** `kaizen.core.autonomy.control.transports`

```python
from kaizen.core.autonomy.control.transports import InMemoryTransport

class InMemoryTransport(Transport):
    """In-memory transport using anyio memory streams."""
```

#### Overview

- **Use Case:** Performance benchmarking, unit/integration testing
- **Communication:** anyio memory streams (zero I/O overhead)
- **Protocol:** Direct message passing (no serialization overhead)
- **Performance:** Ultra-low latency (<1ms), maximum throughput

#### Constructor

```python
def __init__(self, buffer_size: int = 100)
```

**Parameters:**
- `buffer_size` (int) - Size of memory stream buffers (default: 100)

**Example:**

```python
transport = InMemoryTransport(buffer_size=100)
```

#### Usage

```python
import anyio
from kaizen.core.autonomy.control.transports import InMemoryTransport

transport = InMemoryTransport()
await transport.connect()

# Write message
await transport.write('{"type": "question"}')

# Read messages
async for message in transport.read_messages():
    print(f"Received: {message}")
    break

await transport.close()
```

#### Architecture

The transport has two pairs of memory streams:

1. **write_send/write_receive** - For outgoing messages (agent writes → responder reads)
2. **read_send/read_receive** - For incoming messages (responder writes → agent reads)

#### Testing Methods

##### `get_write_receiver()`

Get the receive end of the write stream for responder to read agent's messages.

```python
def get_write_receiver(self) -> MemoryObjectReceiveStream
```

**Returns:**
- `MemoryObjectReceiveStream` - Receive stream for reading written messages

**Raises:**
- `RuntimeError` - If not connected

**Example:**

```python
transport = InMemoryTransport()
await transport.connect()

# Responder reads agent's messages
write_receiver = transport.get_write_receiver()
async for message in write_receiver:
    print(f"Agent wrote: {message}")
    break
```

##### `get_read_sender()`

Get the send end of the read stream for responder to send messages to agent.

```python
def get_read_sender(self) -> MemoryObjectSendStream
```

**Returns:**
- `MemoryObjectSendStream` - Send stream for writing responses

**Raises:**
- `RuntimeError` - If not connected

**Example:**

```python
transport = InMemoryTransport()
await transport.connect()

# Responder sends response to agent
read_sender = transport.get_read_sender()
await read_sender.send('{"request_id": "req_1", "data": {"answer": "yes"}}')
```

---

## BaseAgent Integration

The BaseAgent class provides high-level convenience methods for using the Control Protocol.

**Module:** `kaizen.core.base_agent`

### ask_user_question()

Ask user a question during agent execution.

```python
async def ask_user_question(
    self,
    question: str,
    options: Optional[List[str]] = None,
    timeout: float = 60.0
) -> str
```

**Description:**

Uses the Control Protocol to send a question to the user and wait for their response. This enables interactive agent workflows where the agent can request input mid-execution.

**Parameters:**
- `question` (str) - Question to ask the user
- `options` (Optional[List[str]]) - Optional list of answer choices (for multiple choice)
- `timeout` (float) - Maximum time to wait for response in seconds (default: 60.0)

**Returns:**
- `str` - User's answer as a string

**Raises:**
- `RuntimeError` - If control_protocol is not configured
- `TimeoutError` - If user doesn't respond within timeout

**Example:**

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Configure agent with control protocol
transport = CLITransport()
protocol = ControlProtocol(transport=transport)

agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol
)

# Ask user a question during execution
answer = await agent.ask_user_question(
    "Which file should I process?",
    options=["file1.txt", "file2.txt", "all"]
)
print(f"User selected: {answer}")

# Open-ended question (no options)
name = await agent.ask_user_question("What is your name?")
```

---

### request_approval()

Request user approval for an action during agent execution.

```python
async def request_approval(
    self,
    action: str,
    details: Optional[Dict[str, Any]] = None,
    timeout: float = 60.0
) -> bool
```

**Description:**

Uses the Control Protocol to ask the user to approve or deny a proposed action. This enables safe interactive workflows where critical operations require human confirmation.

**Parameters:**
- `action` (str) - Description of the action needing approval
- `details` (Optional[Dict[str, Any]]) - Optional additional context/details about the action
- `timeout` (float) - Maximum time to wait for response in seconds (default: 60.0)

**Returns:**
- `bool` - True if approved, False if denied

**Raises:**
- `RuntimeError` - If control_protocol is not configured
- `TimeoutError` - If user doesn't respond within timeout

**Example:**

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Configure agent with control protocol
transport = CLITransport()
protocol = ControlProtocol(transport=transport)

agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol
)

# Request approval with details
approved = await agent.request_approval(
    "Delete 100 files",
    details={
        "files": file_list,
        "total_size_mb": 250,
        "oldest_date": "2020-01-01"
    }
)

if approved:
    # Proceed with deletion
    delete_files(file_list)
else:
    # Cancel operation
    print("Operation cancelled by user")
```

---

### report_progress()

Report progress update to user during agent execution.

```python
async def report_progress(
    self,
    message: str,
    percentage: Optional[float] = None,
    details: Optional[Dict[str, Any]] = None
) -> None
```

**Description:**

This is a fire-and-forget method - it sends progress updates but doesn't wait for acknowledgment. Use this to keep users informed during long-running operations.

**Parameters:**
- `message` (str) - Progress message to display (e.g., "Processing file 5 of 10")
- `percentage` (Optional[float]) - Optional progress percentage (0.0-100.0)
- `details` (Optional[Dict[str, Any]]) - Optional additional progress details

**Raises:**
- `RuntimeError` - If control_protocol is not configured
- `ValueError` - If percentage not between 0.0 and 100.0

**Example:**

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.control import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

# Configure agent with control protocol
transport = CLITransport()
protocol = ControlProtocol(transport=transport)

agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol
)

# Report progress during long operation
files = ["file1.txt", "file2.txt", "file3.txt"]
for i, file in enumerate(files):
    await agent.report_progress(
        f"Processing {file}",
        percentage=(i / len(files)) * 100,
        details={"current": i + 1, "total": len(files)}
    )
    # ... process file ...

# Final progress update
await agent.report_progress(
    "Processing complete",
    percentage=100.0
)
```

---

## Error Handling

### Common Exceptions

#### RuntimeError

**When:** Protocol not started or control_protocol not configured

**Fix:**

```python
# For ControlProtocol
async with anyio.create_task_group() as tg:
    await protocol.start(tg)  # Start before send_request

# For BaseAgent methods
agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol  # Must pass control_protocol
)
```

#### TimeoutError

**When:** No response received within timeout

**Fix:**

```python
# Increase timeout
response = await protocol.send_request(request, timeout=120.0)

# Or handle timeout gracefully
try:
    response = await protocol.send_request(request, timeout=30.0)
except TimeoutError:
    # Use default or cancel
    response = ControlResponse(request_id=request.request_id, data={"answer": "default"})
```

#### ConnectionError

**When:** Transport write fails or connection closed

**Fix:**

```python
# Ensure transport is connected
await transport.connect()

# Check ready state
if not transport.is_ready():
    await transport.connect()

# Reconnect on error
try:
    await transport.write(message)
except ConnectionError:
    await transport.close()
    await transport.connect()
    await transport.write(message)
```

### Error Response Pattern

```python
from kaizen.core.autonomy.control.types import ControlRequest

request = ControlRequest.create("approval", {"action": "delete"})
response = await protocol.send_request(request)

if response.is_error:
    # Handle error response
    print(f"Error: {response.error}")
    # Fall back to default behavior
else:
    # Handle success response
    approved = response.data.get("approved", False)
```

---

## Performance

### Transport Comparison

| Transport | Latency (p50) | Latency (p95) | Throughput | Use Case |
|-----------|---------------|---------------|------------|----------|
| **InMemoryTransport** | <1ms | <1ms | Unlimited | Testing, benchmarking |
| **CLITransport** | ~10ms | ~20ms | >1000 msg/s | CLI apps, local dev |
| **StdioTransport** | ~10ms | ~20ms | >1000 msg/s | Subprocesses, MCP |
| **HTTPTransport** | ~50ms (local) | ~100ms (local) | >100 msg/s | Web apps, remote |

### Protocol Overhead

| Operation | Latency | Notes |
|-----------|---------|-------|
| Request serialization | <0.1ms | JSON encoding |
| Request ID generation | <0.01ms | UUID-based |
| Response deserialization | <0.1ms | JSON decoding |
| Background reader | ~1ms | Message pairing |

### Optimization Tips

1. **Use InMemoryTransport for testing** - Zero I/O overhead for pure protocol benchmarking
2. **Batch operations** - Group multiple small operations instead of many individual requests
3. **Adjust timeouts** - Use appropriate timeouts based on operation complexity
4. **Connection pooling** - HTTPTransport reuses connections automatically

### Memory Usage

| Component | Memory | Notes |
|-----------|--------|-------|
| ControlProtocol | ~1KB | Base overhead |
| ControlRequest | ~200 bytes | Per request |
| ControlResponse | ~200 bytes | Per response |
| CLITransport | ~500 bytes | Minimal |
| HTTPTransport | ~50KB | aiohttp session |
| InMemoryTransport | ~10KB | Memory streams |

---

## See Also

- **[Control Protocol Tutorial](../guides/control-protocol-tutorial.md)** - Step-by-step guide
- **[Custom Transports Guide](../guides/custom-transports.md)** - Develop custom transports
- **[Migration Guide](../guides/migrating-to-control-protocol.md)** - Migrate existing agents
- **[Troubleshooting](./control-protocol-troubleshooting.md)** - Common issues and solutions
- **[ADR-011](../architecture/adr/ADR-011-control-protocol-architecture.md)** - Architecture decisions

---

**Version:** Kaizen v0.3.0+
**Status:** Production-ready ✅
**Last Updated:** 2025-01-22
