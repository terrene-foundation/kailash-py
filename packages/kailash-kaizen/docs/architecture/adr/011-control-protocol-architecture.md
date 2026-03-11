# 015: Control Protocol Architecture

## Status
**Implemented** - Fully implemented and deployed (2025-10-20)

**Implementation Date**: 2025-10-20
**Implementation Evidence**:
- Source code: src/kaizen/core/autonomy/control/ (4 files, 31,828 bytes)
- Transports: cli.py, http.py, stdio.py, memory.py (4 implementations)
- Tests: 114 integration tests passing (100% pass rate, 74.60s)
- Examples: 3 working applications (CLI, web, subprocess)
- See: TODO-159 for complete implementation details

## Context

Kaizen agents currently execute in a unidirectional manner: user provides inputs, agent processes, agent returns results. This limits autonomy because agents cannot:
- Ask clarifying questions during execution
- Request user approval for risky actions
- Report progress updates in real-time
- Be interrupted or controlled mid-execution

**Problem**: To achieve autonomous agent capabilities (matching Claude Agent SDK), Kaizen needs **bidirectional communication** between agent and client during execution, not just request/response at boundaries.

**Requirements** (from Gap Analysis):
1. **P0 - Critical**: Bidirectional control protocol for agent ↔ client communication
2. Real-time messaging with <20ms latency (p95)
3. Support for multiple transport types (CLI, HTTP/SSE, stdio)
4. Request/response pairing with timeouts
5. Async-first design for non-blocking operation
6. Integration with BaseAgent without breaking existing API

## Decision

We will implement a **Control Protocol** system in `kaizen/core/autonomy/control/` with the following design:

### Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│ BaseAgent (User-Facing API)                              │
│ - agent.ask_user_question(question, options)             │
│ - agent.request_approval(action, details)                │
│ - agent.report_progress(message, percentage)             │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ High-level API
                        ▼
┌──────────────────────────────────────────────────────────┐
│ ControlProtocol (Core Implementation)                    │
│ - send_request(request) → response                       │
│ - receive_responses() → async iterator                   │
│ - Handles request/response pairing                       │
│ - Manages timeouts and errors                            │
└──────────────────────────────────────────────────────────┘
                        ▲
                        │ Abstract transport
                        ▼
┌──────────────────────────────────────────────────────────┐
│ Transport Layer (Pluggable)                              │
│ - CLITransport (terminal apps)                           │
│ - HTTPTransport (web apps via SSE)                       │
│ - StdioTransport (subprocess communication)              │
└──────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. Message Types (`kaizen/core/autonomy/control/types.py`)

```python
from dataclasses import dataclass
from typing import Literal, Any
import uuid

@dataclass
class ControlRequest:
    """Request from agent to client"""
    request_id: str
    type: Literal["user_input", "approval", "progress_update", "question"]
    data: dict[str, Any]

    @classmethod
    def create(cls, type: str, data: dict[str, Any]) -> "ControlRequest":
        return cls(request_id=f"req_{uuid.uuid4().hex[:8]}", type=type, data=data)

@dataclass
class ControlResponse:
    """Response from client to agent"""
    request_id: str
    data: dict[str, Any] | None = None
    error: str | None = None

    @property
    def is_error(self) -> bool:
        return self.error is not None
```

#### 2. Transport Abstract Base Class (`kaizen/core/autonomy/control/transport.py`)

```python
from abc import ABC, abstractmethod
from typing import AsyncIterator
import anyio

class Transport(ABC):
    """Abstract transport for bidirectional communication"""

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection"""
        pass

    @abstractmethod
    async def write(self, data: str) -> None:
        """Send data to client"""
        pass

    @abstractmethod
    def read_messages(self) -> AsyncIterator[str]:
        """Receive messages from client"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close connection"""
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """Check if transport is ready"""
        pass
```

#### 3. Control Protocol (`kaizen/core/autonomy/control/protocol.py`)

```python
from typing import AsyncIterator
import anyio
import json

class ControlProtocol:
    """Manages bidirectional control communication"""

    def __init__(self, transport: Transport):
        self.transport = transport
        self.pending_requests: dict[str, anyio.Event] = {}
        self.pending_responses: dict[str, ControlResponse] = {}
        self._message_send, self._message_receive = \
            anyio.create_memory_object_stream[ControlResponse](max_buffer_size=100)
        self._tg: anyio.abc.TaskGroup | None = None

    async def start(self) -> None:
        """Start protocol (background message reader)"""
        if self._tg is None:
            self._tg = anyio.create_task_group()
            await self._tg.__aenter__()
            self._tg.start_soon(self._read_messages)

    async def stop(self) -> None:
        """Stop protocol"""
        if self._tg:
            await self._tg.__aexit__(None, None, None)
            self._tg = None

    async def send_request(self, request: ControlRequest, timeout: float = 60.0) -> ControlResponse:
        """Send request and wait for response"""
        event = anyio.Event()
        self.pending_requests[request.request_id] = event

        # Send request
        await self.transport.write(json.dumps(request.__dict__))

        # Wait for response
        try:
            with anyio.fail_after(timeout):
                await event.wait()
        except TimeoutError:
            self.pending_requests.pop(request.request_id, None)
            raise TimeoutError(f"Control request timeout: {request.type}")

        # Retrieve response
        response = self.pending_responses.pop(request.request_id)
        if response.is_error:
            raise RuntimeError(f"Control request error: {response.error}")
        return response

    async def _read_messages(self) -> None:
        """Background task: read messages from transport"""
        async for message in self.transport.read_messages():
            try:
                data = json.loads(message)
                response = ControlResponse(**data)

                # Pair with pending request
                if response.request_id in self.pending_requests:
                    self.pending_responses[response.request_id] = response
                    self.pending_requests[response.request_id].set()
                else:
                    # Unsolicited message (push notification)
                    await self._message_send.send(response)
            except Exception as e:
                logger.error(f"Failed to parse control message: {e}")

    def receive_messages(self) -> AsyncIterator[ControlResponse]:
        """Receive unsolicited messages (async iterator)"""
        return self._message_receive
```

#### 4. CLI Transport (`kaizen/core/autonomy/control/transports/cli.py`)

```python
from typing import AsyncIterator
import anyio
import sys

class CLITransport(Transport):
    """Terminal-based transport (interactive CLI)"""

    async def connect(self) -> None:
        """No connection needed for CLI"""
        pass

    async def write(self, data: str) -> None:
        """Write to stdout"""
        print(f"[AGENT REQUEST] {data}", file=sys.stderr)

    async def read_messages(self) -> AsyncIterator[str]:
        """Read from stdin"""
        async with anyio.wrap_file(sys.stdin) as stdin:
            async for line in stdin:
                yield line.strip()

    async def close(self) -> None:
        """No cleanup needed"""
        pass

    def is_ready(self) -> bool:
        return True
```

#### 5. HTTP/SSE Transport (`kaizen/core/autonomy/control/transports/http.py`)

```python
import aiohttp
from typing import AsyncIterator

class HTTPTransport(Transport):
    """HTTP-based transport using Server-Sent Events"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session: aiohttp.ClientSession | None = None

    async def connect(self) -> None:
        self.session = aiohttp.ClientSession()

    async def write(self, data: str) -> None:
        """Send via HTTP POST"""
        async with self.session.post(f"{self.base_url}/control", json=json.loads(data)) as resp:
            resp.raise_for_status()

    async def read_messages(self) -> AsyncIterator[str]:
        """Receive via Server-Sent Events"""
        async with self.session.get(f"{self.base_url}/stream") as resp:
            async for line in resp.content:
                decoded = line.decode().strip()
                if decoded.startswith("data: "):
                    yield decoded[6:]  # Strip "data: " prefix

    async def close(self) -> None:
        if self.session:
            await self.session.close()

    def is_ready(self) -> bool:
        return self.session is not None and not self.session.closed
```

### Integration with BaseAgent

```python
# kaizen/core/base_agent.py

class BaseAgent(Node):
    def __init__(self, config: BaseAgentConfig):
        super().__init__(config)
        self.control_protocol: ControlProtocol | None = None

    def enable_control_protocol(self, transport: Transport) -> None:
        """Enable bidirectional control (opt-in)"""
        self.control_protocol = ControlProtocol(transport)

    async def ask_user_question(self, question: str, options: list[str]) -> str:
        """Ask user for input mid-execution"""
        if not self.control_protocol:
            raise RuntimeError("Control protocol not enabled")

        request = ControlRequest.create(
            type="question",
            data={"question": question, "options": options}
        )

        response = await self.control_protocol.send_request(request)
        return response.data["answer"]

    async def request_approval(self, action: str, details: dict[str, Any]) -> bool:
        """Request user approval for action"""
        if not self.control_protocol:
            return True  # Default: auto-approve if protocol disabled

        request = ControlRequest.create(
            type="approval",
            data={"action": action, "details": details}
        )

        response = await self.control_protocol.send_request(request)
        return response.data.get("approved", False)

    async def report_progress(self, message: str, percentage: float) -> None:
        """Report progress update"""
        if not self.control_protocol:
            return  # Silently ignore if protocol disabled

        request = ControlRequest.create(
            type="progress_update",
            data={"message": message, "percentage": percentage}
        )

        # Fire-and-forget (no response expected)
        await self.control_protocol.transport.write(json.dumps(request.__dict__))
```

## Consequences

### Positive

1. **✅ Enables Autonomous Agents**: Agents can now ask questions, request approvals, and report progress—core capabilities for autonomy
2. **✅ Non-Breaking**: Opt-in via `enable_control_protocol()`, existing agents work unchanged
3. **✅ Transport Agnostic**: Same protocol works for CLI, web, subprocess via pluggable transports
4. **✅ Async-First**: Uses `anyio` for runtime-agnostic async (asyncio/trio)
5. **✅ Performance**: Target <20ms latency achievable with in-memory channels + async I/O
6. **✅ Testable**: Mock transports for unit testing, real transports for integration testing

### Negative

1. **⚠️ Complexity**: Adds ~1000 lines of code for control protocol infrastructure
2. **⚠️ New Dependency**: Requires `anyio` (already used in async strategies)
3. **⚠️ Learning Curve**: Developers must understand async patterns and transport abstraction
4. **⚠️ Debugging**: Distributed communication harder to debug than local execution

### Mitigations

1. **Complexity**: Provide clear examples and comprehensive docs
2. **Dependency**: `anyio` is lightweight and well-maintained
3. **Learning Curve**: Create tutorial showing CLI → HTTP migration path
4. **Debugging**: Add verbose logging mode + message tracing

## Performance Targets

| Metric | Target | Validation |
|--------|--------|------------|
| Request/response latency (p95) | <20ms | Benchmark with 1000 requests |
| Message throughput | >500 msg/sec | Sustained 1-minute load test |
| Concurrent requests | >100 concurrent | 100 clients, measure degradation |
| Memory per connection | <5MB | 100 connections, measure delta |
| Initialization overhead | <10ms | Measure ControlProtocol creation |

See `PERFORMANCE_PARITY_PLAN.md` for full benchmarking strategy.

## Alternatives Considered

### Alternative 1: Callback-Based API
```python
agent.on_question(lambda q: input(f"{q}: "))
```
**Rejected**: Callbacks don't work well with async execution, harder to test

### Alternative 2: Polling-Based Status
```python
while agent.is_running():
    status = agent.get_status()
```
**Rejected**: High latency, inefficient resource usage

### Alternative 3: Use External Message Broker (Redis, RabbitMQ)
**Rejected**: Too heavyweight for core functionality, adds external dependency

## Implementation Plan

**Phase 1 Timeline**: 8 weeks (Weeks 5-12)

| Week | Tasks |
|------|-------|
| 5-6 | Implement core types + Transport ABC + ControlProtocol |
| 7 | Implement CLITransport + integration tests |
| 8 | Implement HTTPTransport + web example |
| 9 | Implement StdioTransport + subprocess example |
| 10 | BaseAgent integration + agent examples |
| 11 | Performance benchmarks + optimization |
| 12 | Documentation + tutorial |

**Deliverables**:
- [ ] `kaizen/core/autonomy/control/` module (~1000 lines)
- [ ] 3 transport implementations (CLI, HTTP/SSE, stdio)
- [ ] BaseAgent integration
- [ ] 50+ unit/integration tests
- [ ] 3 example applications
- [ ] Performance benchmark suite
- [ ] Comprehensive documentation

## Testing Strategy

### Tier 1: Unit Tests (Mock Transports)
```python
def test_control_protocol_send_request():
    mock_transport = MockTransport()
    protocol = ControlProtocol(mock_transport)

    request = ControlRequest.create("question", {"question": "Yes or no?"})
    mock_transport.queue_response(ControlResponse(request_id=request.request_id, data={"answer": "yes"}))

    response = await protocol.send_request(request)
    assert response.data["answer"] == "yes"
```

### Tier 2: Integration Tests (Real Local Transports)
```python
@pytest.mark.tier2
def test_cli_transport_bidirectional():
    transport = CLITransport()
    protocol = ControlProtocol(transport)

    # Simulate user input
    with mock_stdin("yes\n"):
        request = ControlRequest.create("question", {"question": "Proceed?"})
        response = await protocol.send_request(request)
        assert response.data["answer"] == "yes"
```

### Tier 3: E2E Tests (Real HTTP Server)
```python
@pytest.mark.tier3
async def test_http_transport_with_server():
    # Start test HTTP server
    server = await start_test_server(port=8080)

    transport = HTTPTransport("http://localhost:8080")
    protocol = ControlProtocol(transport)

    request = ControlRequest.create("question", {"question": "Test?"})
    response = await protocol.send_request(request, timeout=5.0)

    assert response.data["answer"] is not None
```

## Documentation Requirements

- [ ] **ADR** (this document)
- [ ] **API Reference**: `docs/reference/control-protocol-api.md`
- [ ] **Tutorial**: `docs/guides/control-protocol-tutorial.md`
- [ ] **Transport Guide**: `docs/guides/custom-transports.md`
- [ ] **Migration Guide**: `docs/guides/migrating-to-control-protocol.md`
- [ ] **Troubleshooting**: `docs/reference/control-protocol-troubleshooting.md`

## References

1. **Gap Analysis**: `.claude/improvements/CLAUDE_AGENT_SDK_KAIZEN_GAP_ANALYSIS.md`
2. **Implementation Proposal**: `.claude/improvements/KAIZEN_AUTONOMOUS_AGENT_ENHANCEMENT_PROPOSAL.md` (Section 3.3.1)
3. **Architectural Patterns**: `.claude/improvements/ARCHITECTURAL_PATTERNS_ANALYSIS.md` (Section 1)
4. **Performance Plan**: `.claude/improvements/PERFORMANCE_PARITY_PLAN.md` (Phase 1)
5. **Claude Agent SDK Analysis**: How bidirectional control enables Claude Code's autonomy

## Approval

**Proposed By**: Kaizen Architecture Team
**Date**: 2025-10-18
**Reviewers**: TBD
**Status**: Proposed (awaiting team review)

---

**Next ADR**: 012: Permission System Design
