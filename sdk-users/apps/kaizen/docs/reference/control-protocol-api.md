# Control Protocol API Reference

## Overview

The Control Protocol provides bidirectional communication between AI agents and their clients, enabling interactive agent execution with user input, approval workflows, and progress reporting.

**Key Features:**
- Bidirectional agent ↔ client messaging
- Request/response pairing with timeouts
- Multiple transport layers (CLI, HTTP/SSE, stdio, memory)
- Async-first design for non-blocking operation
- Real-time messaging with <20ms p95 latency

**Version:** Kaizen v0.2.0+
**Status:** Production-ready (114 integration tests passing)

---

## Core Components

### ControlProtocol

**Location:** `src/kaizen/core/autonomy/control/protocol.py`

The main protocol class that manages bidirectional communication between agents and clients.

#### Constructor

```python
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport

transport = CLITransport()
protocol = ControlProtocol(transport)
```

**Parameters:**
- `transport: Transport` - The transport layer implementation (CLI, HTTP/SSE, stdio, or memory)

**Attributes:**
- `_transport: Transport` - The configured transport instance
- `_pending_requests: dict[str, tuple[anyio.Event, list[ControlResponse | None]]]` - Request tracking with event-based synchronization
- `_running: bool` - Protocol running state

#### Methods

##### `async start(task_group: TaskGroup) -> None`

Starts the protocol and begins listening for incoming messages.

**Parameters:**
- `task_group: TaskGroup` - anyio TaskGroup for managing background tasks

**Raises:**
- `RuntimeError` - If protocol is already running

**Example:**
```python
import anyio
from kaizen.core.autonomy.control.protocol import ControlProtocol

async def main():
    protocol = ControlProtocol(transport)
    async with anyio.create_task_group() as tg:
        await protocol.start(tg)
        # Protocol now running
```

---

##### `async stop() -> None`

Stops the protocol and closes the transport connection.

**Example:**
```python
await protocol.stop()
```

---

##### `async send_request(request: ControlRequest, timeout: float = 30.0) -> ControlResponse`

Sends a control request and waits for the response.

**Parameters:**
- `request: ControlRequest` - The request to send
- `timeout: float` - Maximum wait time (default: 30.0 seconds)

**Returns:**
- `ControlResponse` - The response from the client

**Raises:**
- `TimeoutError` - If response not received within timeout
- `RuntimeError` - If protocol is not running

**Example:**
```python
from kaizen.core.autonomy.control.types import ControlRequest

request = ControlRequest.create(
    type="question",
    data={"question": "Choose option:", "options": ["A", "B", "C"]}
)

response = await protocol.send_request(request, timeout=60.0)
print(f"User selected: {response.data['answer']}")
```

---

## Message Types

### ControlRequest

**Location:** `src/kaizen/core/autonomy/control/types.py`

Represents a control request from agent to client.

**Attributes:**
```python
@dataclass(frozen=True)
class ControlRequest:
    request_id: str          # Auto-generated UUID
    type: MessageType        # "user_input", "approval", "progress_update", "question"
    data: dict[str, Any]     # Request payload
```

**Factory Method:**
```python
ControlRequest.create(type: str, data: dict[str, Any]) -> ControlRequest
```

**Serialization:**
- `to_json() -> str` - Convert to JSON
- `from_json(json_str: str) -> ControlRequest` - Parse from JSON

**Example:**
```python
# Question request
request = ControlRequest.create(
    type="question",
    data={"question": "Choose:", "options": ["Fast", "Slow"]}
)

# Approval request
approval = ControlRequest.create(
    type="approval",
    data={"action": "delete_file", "details": {"path": "/data.json"}}
)
```

---

### ControlResponse

Represents a response from client to agent.

**Attributes:**
```python
@dataclass(frozen=True)
class ControlResponse:
    request_id: str          # ID from corresponding request
    status: str              # "success" or "error"
    data: dict[str, Any]     # Response payload
    error: str | None        # Error message (if status == "error")
```

**Factory Methods:**
```python
# Success response
ControlResponse.success(request_id: str, data: dict[str, Any])

# Error response
ControlResponse.error(request_id: str, error: str)
```

---

## BaseAgent Integration

### `async ask_user_question(question: str, options: list[str], timeout: float = 30.0) -> str`

Asks a multiple-choice question and waits for answer.

**Parameters:**
- `question: str` - The question
- `options: list[str]` - Available choices
- `timeout: float` - Max wait time (default: 30.0)

**Returns:**
- `str` - Selected answer

**Example:**
```python
answer = await agent.ask_user_question(
    "Choose mode:",
    ["Fast", "Accurate", "Balanced"],
    timeout=60.0
)
```

---

### `async request_approval(action: str, details: dict[str, Any], timeout: float = 60.0) -> bool`

Requests user approval for potentially dangerous operations.

**Parameters:**
- `action: str` - Action description
- `details: dict[str, Any]` - Additional context
- `timeout: float` - Max wait time (default: 60.0)

**Returns:**
- `bool` - True if approved, False if denied

**Example:**
```python
approved = await agent.request_approval(
    action="delete_file",
    details={"path": "/important/data.json", "size": "10MB"},
    timeout=120.0
)

if approved:
    await delete_file(path)
```

---

### `async report_progress(message: str, percentage: float | None = None) -> None`

Reports progress to user (fire-and-forget).

**Parameters:**
- `message: str` - Progress message
- `percentage: float | None` - Completion % (0-100)

**Example:**
```python
for i in range(10):
    await agent.report_progress(
        f"Processing batch {i+1}/10",
        percentage=(i / 10) * 100
    )
```

---

## Transport Implementations

### CLITransport

Terminal-based transport with rich formatting.

**Example:**
```python
from kaizen.core.autonomy.control.transports import CLITransport

transport = CLITransport()
await transport.connect()
```

**Use Cases:** Development, CLI tools, debugging

---

### MemoryTransport

In-memory transport for testing.

**Example:**
```python
from kaizen.core.autonomy.control.transports import MemoryTransport

transport = MemoryTransport()
await transport.connect()

# Programmatic responses
def handler(request):
    return ControlResponse.success(request.request_id, {"answer": "A"})

transport.set_handler(handler)
```

**Use Cases:** Unit testing, automated workflows

---

### HTTPTransport

SSE-based transport for web applications.

**Configuration:**
```python
from kaizen.core.autonomy.control.transports import HTTPTransport

transport = HTTPTransport(host="0.0.0.0", port=8080, endpoint="/control")
await transport.connect()
```

**Client Example (JavaScript):**
```javascript
const eventSource = new EventSource('http://localhost:8080/control/stream');
eventSource.onmessage = (event) => {
  const request = JSON.parse(event.data);
  // Handle request and send response
};
```

**Use Cases:** Web apps, dashboards, remote control

---

### StdioTransport

JSONL-based transport for process communication.

**Example:**
```python
from kaizen.core.autonomy.control.transports import StdioTransport

transport = StdioTransport()
await transport.connect()
```

**Use Cases:** MCP integration, subprocess communication, language interop

---

## Error Handling

### TimeoutError

Raised when request doesn't receive response within timeout.

**Example:**
```python
try:
    answer = await agent.ask_user_question("Choose:", ["A", "B"], timeout=30.0)
except TimeoutError:
    answer = "A"  # Use default
```

---

### RuntimeError

Raised when control protocol not configured or not started.

**Fix:**
```python
# Provide control_protocol parameter
agent = BaseAgent(
    config=config,
    signature=signature,
    control_protocol=protocol  # ✅ Required
)
```

---

## Complete Example

```python
import anyio
from kaizen.core.base_agent import BaseAgent
from kaizen.core.autonomy.control.protocol import ControlProtocol
from kaizen.core.autonomy.control.transports import CLITransport
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

class ProcessorSignature(Signature):
    files: list[str] = InputField(desc="Available files")
    result: str = OutputField(desc="Processing result")

@dataclass
class ProcessorConfig:
    llm_provider: str = "mock"

class InteractiveProcessor(BaseAgent):
    def __init__(self, config, control_protocol):
        super().__init__(
            config=config,
            signature=ProcessorSignature(),
            control_protocol=control_protocol
        )

    async def process(self, available_files):
        # Ask user
        selected = await self.ask_user_question(
            "Which file?",
            available_files,
            timeout=60.0
        )

        # Request approval
        approved = await self.request_approval(
            f"Process: {selected}",
            {"file": selected, "will_modify": True},
            timeout=120.0
        )

        if not approved:
            return {"status": "cancelled"}

        # Report progress
        await self.report_progress("Processing...", 50.0)

        result = self.run(files=[selected])

        await self.report_progress("Complete", 100.0)

        return result

async def main():
    transport = CLITransport()
    await transport.connect()

    protocol = ControlProtocol(transport)

    async with anyio.create_task_group() as tg:
        await protocol.start(tg)

        agent = InteractiveProcessor(ProcessorConfig(), protocol)
        result = await agent.process(["file1.txt", "file2.txt"])

        await protocol.stop()

if __name__ == "__main__":
    anyio.run(main)
```

---

## Best Practices

### 1. Set Appropriate Timeouts

```python
# ✅ Short timeout for quick questions
answer = await agent.ask_user_question("Continue?", ["Yes", "No"], timeout=15.0)

# ✅ Long timeout for complex decisions
approved = await agent.request_approval("Deploy?", details, timeout=300.0)
```

---

### 2. Handle Timeouts Gracefully

```python
try:
    answer = await agent.ask_user_question("Choose:", ["A", "B"])
except TimeoutError:
    answer = "A"  # Safe default
```

---

### 3. Use Progress Updates

```python
async def process_items(items):
    for i, item in enumerate(items):
        await process_item(item)
        if i % 10 == 0:
            await self.report_progress(f"Processed {i}/{len(items)}", (i/len(items))*100)
```

---

### 4. Choose Right Transport

| Use Case | Transport | Why |
|----------|-----------|-----|
| CLI tools | CLITransport | Rich terminal UI |
| Web apps | HTTPTransport | Real-time browser |
| Testing | MemoryTransport | Fast, deterministic |
| MCP | StdioTransport | Standard protocol |

---

## Performance

| Metric | Value | Transport |
|--------|-------|-----------|
| Latency (p50) | <5ms | Memory |
| Latency (p95) | <20ms | CLI |
| Latency (p99) | <100ms | HTTP |
| Throughput | 1000+ msg/s | Memory |

---

**Last Updated:** 2025-10-22
**Version:** Kaizen v0.2.0
**Status:** Production-ready ✅
