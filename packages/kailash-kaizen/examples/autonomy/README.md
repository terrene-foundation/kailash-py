# Autonomous Agent Examples

Examples demonstrating Control Protocol for bidirectional agent ↔ user communication.

## Overview

The Control Protocol (ADR-011) enables autonomous agents to:
- Ask questions during execution
- Request approval for actions
- Send real-time progress updates
- Interact with users through multiple interfaces (CLI, web, subprocess)

## Examples

### 1. CLI Interactive Agent

**File**: `cli_interactive_agent.py`

Terminal-based interactive agent using stdin/stdout for communication.

**Usage**:
```bash
# Agent mode: Agent asks questions to user
python examples/autonomy/cli_interactive_agent.py agent

# Client mode: User provides responses to agent
python examples/autonomy/cli_interactive_agent.py client
```

**Features**:
- ✅ Real-time question/answer via terminal
- ✅ Approval workflow for actions
- ✅ Progress updates
- ✅ Uses CLITransport (stdin/stdout)

**Architecture**:
```
User Terminal (stdin/stdout)
         ↕
    CLITransport
         ↕
  ControlProtocol
         ↕
   Agent Workflow
```

---

### 2. Web Interactive Agent

**File**: `web_interactive_agent.py` + `web_ui.html`

Web-based interactive agent using Server-Sent Events (SSE) for real-time communication.

**Usage**:
```bash
# Terminal 1: Start agent server
python examples/autonomy/web_interactive_agent.py

# Terminal 2: Open web UI in browser
open examples/autonomy/web_ui.html
# Or visit: http://127.0.0.1:8765/ui
```

**Features**:
- ✅ Real-time bidirectional communication via HTTP + SSE
- ✅ Modern web UI with progress bar
- ✅ Question/answer with multiple choice options
- ✅ Approval workflow with details
- ✅ Event log for debugging
- ✅ Uses HTTPTransport (HTTP POST + SSE GET)

**Architecture**:
```
Web Browser (HTML/JS)
    ↕ POST /control
    ↕ GET /stream (SSE)
Web Agent HTTP Server
    ↕
ControlProtocol
    ↕
Agent Workflow
```

**Endpoints**:
- `GET /ui` - Serve web interface
- `POST /control` - Receive user responses
- `GET /stream` - Send agent requests via SSE
- `GET /health` - Health check

---

### 3. BaseAgent with Real Ollama

**File**: `baseagent_with_ollama.py`

Demonstrates BaseAgent using REAL Ollama LLM inference combined with Control Protocol.

**Usage**:
```bash
# Prerequisites
ollama serve  # Start Ollama
ollama pull llama3.1:8b-instruct-q8_0  # Download model

# Run example
python examples/autonomy/baseagent_with_ollama.py
```

**Features**:
- ✅ Real Ollama LLM inference (NOT mocked)
- ✅ Interactive questions during AI execution
- ✅ Approval requests before LLM calls
- ✅ Complete AI-powered decision workflow
- ✅ Uses CLITransport for terminal interaction

**Workflow**:
```
1. Agent asks user: "What aspect should I focus on?"
2. User selects: "overview" / "technical details" / "practical applications"
3. Agent requests approval: "Conduct research on [topic]?"
4. User approves: yes/no
5. If approved: Real Ollama inference (llama3.1:8b-instruct-q8_0)
6. Agent returns research summary
```

**Why This Example**:
This demonstrates the **killer feature** of Control Protocol + BaseAgent:
- AI agents can **ask clarifying questions** during execution
- Users **approve expensive operations** before they run
- Real LLM inference **integrated with interactive workflows**
- Production-ready pattern for **autonomous AI with human oversight**

---

### 4. Subprocess Coordination

**File**: `subprocess_coordination.py`

Parent-child agent communication using subprocess stdin/stdout pipes.

**Usage**:
```bash
# Run parent agent (spawns child automatically)
python examples/autonomy/subprocess_coordination.py parent

# Run as child agent (usually spawned by parent)
python examples/autonomy/subprocess_coordination.py child
```

**Features**:
- ✅ Parent agent spawns child as subprocess
- ✅ Bidirectional agent-to-agent communication
- ✅ Question/answer across process boundaries
- ✅ Approval requests between agents
- ✅ Process coordination and lifecycle management
- ✅ Graceful shutdown handling

**Architecture**:
```
Parent Agent (main process)
    ↕ SubprocessTransport
    ↕ ControlProtocol
    ↕ stdin/stdout pipes
Child Agent (subprocess)
    ↕ Direct JSON I/O
    ↕ Agent Workflow
```

**Workflow**:
1. Parent spawns child as subprocess
2. Parent asks: "Are you ready?"
3. Child responds: "yes"
4. Parent asks for child's name
5. Parent asks for child's status
6. Parent asks child to compute 10 + 32
7. Parent requests approval from child
8. Child auto-approves
9. Workflow completes

---

## Control Protocol Flow

### Question Flow
```
1. Agent: Needs user input
   ↓
2. Agent: Creates ControlRequest (type=question)
   ↓
3. Transport: Sends request to user interface
   ↓
4. User: Sees question in UI
   ↓
5. User: Provides answer
   ↓
6. Transport: Sends ControlResponse to agent
   ↓
7. Agent: Receives answer, continues execution
```

### Approval Flow
```
1. Agent: Needs permission for action
   ↓
2. Agent: Creates ControlRequest (type=approval)
   ↓
3. Transport: Sends request with action details
   ↓
4. User: Reviews details
   ↓
5. User: Approves or denies
   ↓
6. Transport: Sends ControlResponse (approved=true/false)
   ↓
7. Agent: Proceeds or cancels based on response
```

### Progress Flow
```
1. Agent: Long-running operation
   ↓
2. Agent: Creates ControlRequest (type=progress)
   ↓
3. Transport: Sends progress update
   ↓
4. User: Sees real-time progress (0-100%)
   ↓
5. Agent: Continues sending updates
```

---

## Message Types

### Question
```json
{
  "request_id": "req_abc123",
  "type": "question",
  "data": {
    "question": "What is your name?",
    "options": ["Alice", "Bob", "Charlie"]  // Optional
  }
}
```

### Approval
```json
{
  "request_id": "req_def456",
  "type": "approval",
  "data": {
    "action": "Delete 100 files",
    "details": {
      "files": ["file1.txt", "file2.txt", "..."],
      "size_mb": 250
    }
  }
}
```

### Progress
```json
{
  "request_id": "req_ghi789",
  "type": "progress",
  "data": {
    "message": "Processing files...",
    "percent": 45.5
  }
}
```

### Response
```json
{
  "request_id": "req_abc123",
  "data": {
    "answer": "Alice"
    // or
    "approved": true
  },
  "error": null
}
```

---

## Transport Implementations

| Transport | Interface | Use Case | Example |
|-----------|-----------|----------|---------|
| **CLITransport** | stdin/stdout | Terminal applications | cli_interactive_agent.py |
| **HTTPTransport** | HTTP + SSE | Web applications | web_interactive_agent.py |
| **StdioTransport** | stdin/stdout | Subprocess communication | subprocess_coordination.py |

---

## Technical Details

### Server-Sent Events (SSE)

SSE format used by HTTPTransport:
```
data: {"request_id": "req_123", "type": "question", ...}

data: {"request_id": "req_124", "type": "progress", ...}

: keepalive

```

**Key Features**:
- One-way server → client streaming
- Automatic reconnection
- Text-based protocol
- Compatible with EventSource API

### Error Handling

Both examples demonstrate:
- ✅ Timeout handling (default 60s per request)
- ✅ Connection errors (reconnection logic)
- ✅ User cancellation (Ctrl+C handling)
- ✅ Malformed input validation

### Async/Await Patterns

All examples use async/await for:
- Non-blocking I/O
- Concurrent request handling
- Efficient resource usage

```python
async def ask_question(question: str) -> str:
    request = ControlRequest.create("question", {"question": question})
    response = await protocol.send_request(request, timeout=60.0)
    return response.data.get("answer")
```

---

## Testing

### Manual Testing: CLI Agent
```bash
# Terminal 1: Agent mode
python examples/autonomy/cli_interactive_agent.py agent

# Terminal 2: Client mode (answer questions)
python examples/autonomy/cli_interactive_agent.py client
```

### Manual Testing: Web Agent
```bash
# Start agent
python examples/autonomy/web_interactive_agent.py

# Open browser to http://127.0.0.1:8765/ui
# Answer questions in web UI
```

### Automated Testing
```bash
# Unit tests for Transport implementations
pytest tests/unit/core/autonomy/control/transports/

# Integration tests with real I/O
pytest tests/integration/autonomy/control/
```

---

## Next Steps

### Extend Examples
1. Add database persistence for conversation history
2. Implement retry logic for failed requests
3. Add file upload/download capabilities
4. Create multi-user collaboration example

### Create New Transports
1. **WebSocketTransport** - Bidirectional WebSocket
2. **gRPCTransport** - High-performance RPC
3. **RedisTransport** - Message queue based
4. **MCPTransport** - Model Context Protocol integration

### Production Deployment
1. Add authentication/authorization
2. Implement rate limiting
3. Add request logging and metrics
4. Deploy with load balancing

---

## Troubleshooting

### Web UI not connecting
```bash
# Check if agent is running
curl http://127.0.0.1:8765/health

# Check browser console for errors
# Open DevTools → Console
```

### Port already in use
```python
# Change port in web_interactive_agent.py
agent = WebInteractiveAgent(host="127.0.0.1", port=8766)  # Different port
```

### SSE connection timeout
```javascript
// Increase timeout in web_ui.html
const eventSource = new EventSource(SSE_URL, {
    heartbeatTimeout: 120000  // 2 minutes
});
```

---

## References

- **ADR-011**: Control Protocol Architecture
- **CLITransport**: `src/kaizen/core/autonomy/control/transports/cli.py`
- **HTTPTransport**: `src/kaizen/core/autonomy/control/transports/http.py`
- **ControlProtocol**: `src/kaizen/core/autonomy/control/protocol.py`
- **Integration Tests**: `tests/integration/autonomy/control/`

---

**Version**: 1.0.0
**Last Updated**: 2025-10-19
**Maintainer**: Kaizen AI Team
