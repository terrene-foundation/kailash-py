# SSE Streaming Guide

*Server-Sent Events (SSE) for Real-Time Workflow Streaming*

## ✅ Native SSE Support in Nexus v1.0.9

**Nexus v1.0.9** includes **native SSE streaming** via the `mode="stream"` parameter in workflow execution. This guide demonstrates how to use built-in SSE capabilities for real-time token streaming, progress updates, and event-driven workflows.

---

## Quick Start

### 1. Basic SSE Streaming with Custom Endpoint

```python
from nexus import Nexus
from fastapi import Request

app = Nexus(api_port=8000)

# Register your streaming workflow
app.register("chat_stream", chat_stream_workflow().build())

# Create custom SSE endpoint
@app.endpoint("/api/chat/stream", methods=["POST"])
async def stream_chat(request: Request):
    """Stream chat response using SSE."""
    data = await request.json()

    # Execute workflow with streaming mode
    result = await app.execute_workflow_async(
        "chat_stream",
        inputs=data,
        mode="stream"  # ✅ Enables native SSE streaming
    )

    return result  # Returns StreamingResponse automatically

app.start()
```

**How it works**:
- `mode="stream"` tells Nexus to return a `StreamingResponse`
- Workflow nodes can yield SSE events via async generators
- Nexus handles SSE formatting, headers, and connection management

### 2. SSE Event Format

Nexus streams SSE events in this format:

```
event: workflow_start
data: {"workflow_id": "chat_stream", "run_id": "run_abc123"}

event: node_start
data: {"node_id": "search_knowledge_base"}

event: token
data: {"text": "The MEP Coach program..."}

event: citation
data: {"number": 1, "title": "Employee Handbook", "page": 15}

event: workflow_complete
data: {"status": "success", "tokens_used": 1234, "execution_time": 3.2}
```

### 3. Client-Side Consumption

#### JavaScript/TypeScript

```typescript
const response = await fetch('http://localhost:8000/api/chat/stream', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-Session-ID': sessionToken
    },
    body: JSON.stringify({
        conversation_id: 'conv_123',
        message: 'What is MEP Coach?'
    })
});

const reader = response.body!.getReader();
const decoder = new TextDecoder();

let buffer = '';

while (true) {
    const { done, value } = await reader.read();

    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Parse SSE events (event: <type>\ndata: <json>\n\n)
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
        if (!line.trim()) continue;

        const eventMatch = line.match(/^event: (.+)$/m);
        const dataMatch = line.match(/^data: (.+)$/m);

        if (eventMatch && dataMatch) {
            const eventType = eventMatch[1];
            const data = JSON.parse(dataMatch[1]);

            switch (eventType) {
                case 'workflow_start':
                    console.log('Workflow started:', data.workflow_id);
                    break;
                case 'token':
                    process.stdout.write(data.text);
                    break;
                case 'citation':
                    console.log(`\n[${data.number}] ${data.title}`);
                    break;
                case 'workflow_complete':
                    console.log(`\nDone! Tokens: ${data.tokens_used}`);
                    break;
            }
        }
    }
}
```

---

## Streaming Workflow Implementation

### Creating a Streaming Workflow

To enable streaming, your workflow must yield SSE events using `PythonCodeNode` with async generators:

```python
from kailash.workflow.builder import WorkflowBuilder

def chat_stream_workflow() -> WorkflowBuilder:
    """
    Streaming chat workflow that yields SSE events.

    Inputs:
        - conversation_id: str
        - message: str
        - user_context: dict

    Yields:
        SSE events (workflow_start, token, citation, workflow_complete)
    """
    workflow = WorkflowBuilder()

    # Step 1: Send workflow start event
    workflow.add_node("PythonCodeNode", "stream_start", {
        "code": """
import json

# Yield SSE event
def generate_event():
    yield {
        "event": "workflow_start",
        "data": {"workflow_id": "chat_stream", "run_id": "run_123"}
    }

result = {"events": list(generate_event())}
"""
    })

    # Step 2: Execute RAG search
    workflow.add_node("RAGSearchNode", "search", {
        "query": "",  # From connection
        "user_role": "admin",
        "top_k": 5
    })

    # Step 3: Stream LLM tokens
    workflow.add_node("PythonCodeNode", "stream_tokens", {
        "code": """
import json

# Simulate streaming tokens
def stream_llm_tokens(text):
    tokens = text.split()
    for token in tokens:
        yield {
            "event": "token",
            "data": {"text": token + " "}
        }

response_text = "The MEP Coach program helps employees develop leadership skills."
result = {"events": list(stream_llm_tokens(response_text))}
"""
    })

    # Step 4: Send completion event
    workflow.add_node("PythonCodeNode", "stream_complete", {
        "code": """
import json

result = {
    "events": [{
        "event": "workflow_complete",
        "data": {"status": "success", "tokens_used": 50}
    }]
}
"""
    })

    # Connect nodes
    workflow.add_connection("stream_start", "events", "search", "query")
    workflow.add_connection("search", "search_results", "stream_tokens", "text")
    workflow.add_connection("stream_tokens", "events", "stream_complete", "input")

    return workflow
```

### Advanced: Real-Time LLM Streaming

For real LLM streaming (OpenAI GPT-4), use async generators:

```python
workflow.add_node("PythonCodeNode", "stream_gpt4", {
    "code": """
import json
import openai
import os

# Initialize OpenAI client
client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def stream_gpt4_response(prompt):
    '''Stream tokens from GPT-4.'''
    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        stream=True  # Enable streaming
    )

    async for chunk in response:
        if chunk.choices[0].delta.content:
            yield {
                "event": "token",
                "data": {"text": chunk.choices[0].delta.content}
            }

# Execute streaming
import asyncio
prompt = "What is MEP Coach?"
events = []
async for event in stream_gpt4_response(prompt):
    events.append(event)

result = {"events": events}
"""
})
```

---

## Custom Endpoint Patterns

### Pattern 1: Direct Workflow Execution

Execute workflow with streaming mode:

```python
@app.endpoint("/api/chat/stream", methods=["POST"])
async def stream_endpoint(request: Request):
    data = await request.json()

    # Nexus handles SSE formatting automatically
    return await app.execute_workflow_async(
        "chat_stream",
        inputs=data,
        mode="stream"
    )
```

### Pattern 2: Custom SSE Generator

For more control, use a custom generator:

```python
from fastapi.responses import StreamingResponse
import json
import asyncio

@app.endpoint("/api/chat/stream", methods=["POST"])
async def stream_endpoint(request: Request):
    data = await request.json()

    async def generate_sse():
        # Start event
        yield f"event: start\ndata: {json.dumps({'message': 'Starting'})}\n\n"

        # Execute workflow
        result = await app.execute_workflow_async(
            "chat_stream",
            inputs=data
        )

        # Stream workflow events
        for event in result.get("events", []):
            yield f"event: {event['event']}\ndata: {json.dumps(event['data'])}\n\n"
            await asyncio.sleep(0.01)  # Smooth streaming

        # Done event
        yield f"event: done\ndata: {json.dumps({'status': 'complete'})}\n\n"

    return StreamingResponse(
        generate_sse(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive"
        }
    )
```

### Pattern 3: Hybrid Workflow + Manual Streaming

Combine workflow execution with custom streaming logic:

```python
@app.endpoint("/api/chat/stream", methods=["POST"])
async def stream_endpoint(request: Request):
    data = await request.json()

    async def hybrid_stream():
        # 1. Send typing indicator
        yield f"event: typing\ndata: {json.dumps({'status': 'searching'})}\n\n"

        # 2. Execute search workflow (non-streaming)
        search_result = await app.execute_workflow_async(
            "search_workflow",
            inputs={"query": data["message"]}
        )

        # 3. Stream LLM response
        yield f"event: typing\ndata: {json.dumps({'status': 'generating'})}\n\n"

        # 4. Execute streaming LLM workflow
        stream_result = await app.execute_workflow_async(
            "llm_stream_workflow",
            inputs={"context": search_result["results"]},
            mode="stream"
        )

        # 5. Yield stream events
        async for event in stream_result:
            yield event

    return StreamingResponse(
        hybrid_stream(),
        media_type="text/event-stream"
    )
```

---

## Event Types Reference

### Standard Nexus Events

| Event | Data Fields | Purpose |
|-------|-------------|---------|
| `workflow_start` | `workflow_id`, `run_id`, `timestamp` | Workflow execution started |
| `node_start` | `node_id`, `node_type` | Node execution started |
| `node_complete` | `node_id`, `output` | Node execution completed |
| `workflow_complete` | `status`, `result`, `execution_time` | Workflow finished |
| `error` | `error_type`, `message`, `traceback` | Error occurred |

### Custom Chat Events

| Event | Data Fields | Purpose |
|-------|-------------|---------|
| `typing` | `status`, `message` | Typing indicator (searching, generating) |
| `token` | `text`, `index` | LLM token streaming |
| `citation` | `number`, `title`, `doc_id`, `page` | Source citation |
| `metadata` | `tokens_used`, `model`, `temperature` | Metadata about response |

---

## Production Considerations

### 1. Connection Timeouts

Send keepalive events to prevent proxy/load balancer timeouts:

```python
async def stream_with_keepalive():
    last_event_time = asyncio.get_event_loop().time()

    while streaming:
        current_time = asyncio.get_event_loop().time()

        # Send keepalive every 15 seconds
        if current_time - last_event_time > 15:
            yield ":keepalive\n\n"
            last_event_time = current_time

        # Your streaming logic
        yield from workflow_events()

        await asyncio.sleep(0.1)
```

### 2. Error Handling

Always send error events before closing stream:

```python
async def safe_stream():
    try:
        # Your streaming logic
        yield f"event: start\ndata: {json.dumps({'status': 'ok'})}\n\n"

        result = await execute_workflow()

        yield from result.events

    except Exception as e:
        # Send error event
        yield f"event: error\ndata: {json.dumps({'message': str(e)})}\n\n"
    finally:
        # Always send done event
        yield f"event: done\ndata: {json.dumps({})}\n\n"
```

### 3. Resource Cleanup

Clean up resources when client disconnects:

```python
from fastapi import BackgroundTasks

async def stream_with_cleanup(background_tasks: BackgroundTasks):
    workflow_id = None

    try:
        workflow_id = await start_workflow()

        async for event in stream_events(workflow_id):
            yield event

    except asyncio.CancelledError:
        # Client disconnected
        if workflow_id:
            background_tasks.add_task(cancel_workflow, workflow_id)
        raise
    finally:
        if workflow_id:
            background_tasks.add_task(cleanup_resources, workflow_id)
```

### 4. Nginx Configuration

Configure Nginx to support SSE:

```nginx
location /api/chat/stream {
    proxy_pass http://localhost:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
    proxy_read_timeout 86400;  # 24 hours

    # Disable buffering for SSE
    proxy_set_header X-Accel-Buffering no;
}
```

---

## Performance Optimization

### 1. Token Buffering

Buffer tokens for smoother streaming:

```python
async def buffered_stream(tokens, buffer_size=5):
    """Stream tokens in small batches for smoothness."""
    buffer = []

    for token in tokens:
        buffer.append(token)

        if len(buffer) >= buffer_size:
            # Flush buffer
            text = "".join(buffer)
            yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
            buffer = []
            await asyncio.sleep(0.05)  # Smooth animation

    # Flush remaining
    if buffer:
        text = "".join(buffer)
        yield f"event: token\ndata: {json.dumps({'text': text})}\n\n"
```

### 2. Compression

Enable compression for large SSE streams:

```python
from fastapi.responses import StreamingResponse

return StreamingResponse(
    stream_generator(),
    media_type="text/event-stream",
    headers={
        "Content-Encoding": "gzip",  # Enable compression
        "Cache-Control": "no-cache",
        "Connection": "keep-alive"
    }
)
```

### 3. Connection Pooling

Limit concurrent SSE connections per user:

```python
from collections import defaultdict
import asyncio

# Track active connections per user
active_streams = defaultdict(int)
MAX_STREAMS_PER_USER = 3

@app.endpoint("/api/chat/stream", methods=["POST"])
async def stream_endpoint(request: Request):
    user_id = request.user.id

    # Check connection limit
    if active_streams[user_id] >= MAX_STREAMS_PER_USER:
        return {"error": "Too many active streams"}, 429

    # Increment counter
    active_streams[user_id] += 1

    try:
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream"
        )
    finally:
        # Decrement counter
        active_streams[user_id] -= 1
```

---

## Testing

### Unit Test Example

```python
import pytest
from fastapi.testclient import TestClient

@pytest.mark.asyncio
async def test_sse_streaming():
    """Test SSE streaming endpoint."""
    async with AsyncClient(app=app.app, base_url="http://test") as client:
        events = []

        async with client.stream(
            "POST",
            "/api/chat/stream",
            json={"conversation_id": "conv_123", "message": "Test"}
        ) as response:
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream"

            async for line in response.aiter_lines():
                if line.startswith("event: ") or line.startswith("data: "):
                    events.append(line)

        # Validate events
        assert any("workflow_start" in e for e in events)
        assert any("token" in e for e in events)
        assert any("workflow_complete" in e for e in events)
```

---

## Related Documentation

- [Custom Endpoints Guide](custom_endpoints.md) - REST endpoints with path parameters
- [Query Parameters Guide](query_parameters.md) - Advanced query parameter patterns
- [Nexus Developer Guide](../DEVELOPER_GUIDE.md) - Comprehensive Nexus development guide
- [Migration Guide](../../README.md) - Migrating from FastAPI to Nexus

---

## Summary

✅ **Nexus v1.0.9 has native SSE streaming** via `mode="stream"`
- Use `app.execute_workflow_async(workflow_id, inputs, mode="stream")` for automatic SSE
- Workflows yield events via `PythonCodeNode` with async generators
- Nexus handles SSE formatting, headers, and connection management
- Custom endpoints provide full control over streaming behavior

🚀 **Ready for Production**:
- Keepalive support for long-running connections
- Error handling and resource cleanup
- Nginx configuration for reverse proxy
- Connection pooling and rate limiting
