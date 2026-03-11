# Server-Sent Events (SSE) Streaming

## Overview

Server-Sent Events (SSE) is a server push technology that enables real-time, unidirectional communication from server to client over HTTP. Unlike WebSockets, SSE uses standard HTTP and is simpler to implement, making it ideal for streaming workflow results, progress updates, and real-time notifications.

Nexus provides built-in SSE streaming support through the WorkflowAPI, allowing workflows to stream results incrementally as they execute.

**When to use SSE:**
- Real-time chat applications with AI agents
- Progress updates for long-running workflows
- Live notifications and alerts
- Streaming data processing results
- Dashboard metrics and monitoring

**SSE vs WebSockets:**
- SSE: Unidirectional (server to client), uses HTTP, automatic reconnection
- WebSockets: Bidirectional, custom protocol, manual reconnection
- **Use SSE when:** You only need server-to-client updates
- **Use WebSockets when:** You need bidirectional communication

## Quick Start

**Server (Nexus):**
```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(api_port=8000)

# Create workflow
workflow = WorkflowBuilder()
workflow.add_node("LLMAgentNode", "agent", {"model": "gpt-4"})

app.register("chat", workflow)
app.run()
```

**Client (JavaScript):**
```javascript
const eventSource = new EventSource('http://localhost:8000/workflows/chat/execute');

eventSource.addEventListener('start', (e) => {
    console.log('Workflow started:', JSON.parse(e.data));
});

eventSource.addEventListener('complete', (e) => {
    console.log('Workflow completed:', JSON.parse(e.data));
    eventSource.close();
});

eventSource.addEventListener('error', (e) => {
    console.error('Error:', JSON.parse(e.data));
});
```

## SSE Format Specification

SSE uses a simple text-based format with four field types:

```
id: <event-id>
event: <event-type>
data: <json-data>

```

**Field Types:**

1. **id**: Event identifier for reconnection support
   - Format: `id: 1`
   - Used by browser to resume connection after disconnect
   - Automatically increments with each event

2. **event**: Event type name
   - Format: `event: start`
   - Determines which event listener handles the message
   - Default: `message` (if not specified)

3. **data**: Event payload (JSON)
   - Format: `data: {"key": "value"}`
   - Must be valid JSON
   - Can span multiple lines (each prefixed with `data: `)

4. **comment**: Keepalive or comment (starts with `:`)
   - Format: `:keepalive`
   - Prevents connection timeout
   - Ignored by clients

**Example SSE Stream:**
```
id: 1
event: start
data: {"workflow_id": "chat", "timestamp": 1234567890}

id: 2
event: progress
data: {"step": "processing", "percent": 50}

id: 3
event: complete
data: {"result": {"response": "Hello!"}, "timestamp": 1234567891}

:keepalive

```

## Nexus SSE Event Types

Nexus WorkflowAPI emits the following event types:

### 1. `start` Event

Emitted when workflow execution begins.

```json
{
    "workflow_id": "chat",
    "version": "1.0.0",
    "timestamp": 1698765432.123
}
```

### 2. `complete` Event

Emitted when workflow execution finishes successfully.

```json
{
    "result": {
        "response": "AI-generated response",
        "metadata": {...}
    },
    "timestamp": 1698765435.456
}
```

### 3. `error` Event

Emitted when workflow execution fails.

```json
{
    "error": "Error message",
    "error_type": "ValidationError",
    "timestamp": 1698765433.789
}
```

### 4. `keepalive` Comment

Emitted periodically to prevent connection timeout.

```
:keepalive
```

## Browser EventSource API

The browser's built-in EventSource API provides automatic SSE handling:

### Basic Usage

```javascript
// Create connection
const eventSource = new EventSource('http://localhost:8000/workflows/chat/execute');

// Listen for specific event types
eventSource.addEventListener('start', (event) => {
    const data = JSON.parse(event.data);
    console.log('Started:', data.workflow_id);
});

eventSource.addEventListener('complete', (event) => {
    const data = JSON.parse(event.data);
    console.log('Completed:', data.result);
    eventSource.close(); // Close connection when done
});

eventSource.addEventListener('error', (event) => {
    const data = JSON.parse(event.data);
    console.error('Error:', data.error);
    eventSource.close();
});

// Handle connection errors
eventSource.onerror = (error) => {
    console.error('Connection error:', error);
    eventSource.close();
};
```

### With POST Request (Custom Endpoint)

EventSource only supports GET requests. For POST with SSE, use fetch with ReadableStream:

```javascript
async function connectSSE(url, requestBody) {
    const response = await fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream'
        },
        body: JSON.stringify(requestBody)
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    // Track current event
    let currentEvent = {};

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        // Decode chunk and add to buffer
        buffer += decoder.decode(value, { stream: true });

        // Process complete lines
        const lines = buffer.split('\n');
        buffer = lines.pop() || ''; // Keep incomplete line

        for (const line of lines) {
            if (line === '') {
                // Empty line = dispatch event
                if (currentEvent.data) {
                    const eventType = currentEvent.event || 'message';
                    const eventData = JSON.parse(currentEvent.data);
                    handleEvent(eventType, eventData, currentEvent.id);
                    currentEvent = {};
                }
            } else if (line.startsWith(':')) {
                // Comment (keepalive) - ignore
                console.log('Keepalive');
            } else if (line.includes(':')) {
                // Parse field
                const colonIndex = line.indexOf(':');
                const field = line.slice(0, colonIndex);
                let value = line.slice(colonIndex + 1);

                // Remove leading space (SSE spec)
                if (value.startsWith(' ')) {
                    value = value.slice(1);
                }

                currentEvent[field] = value;
            }
        }
    }
}

function handleEvent(type, data, id) {
    console.log(`Event[${id}] ${type}:`, data);

    switch (type) {
        case 'start':
            updateUI('Workflow started...');
            break;
        case 'complete':
            updateUI('Completed: ' + JSON.stringify(data.result));
            break;
        case 'error':
            updateUI('Error: ' + data.error);
            break;
    }
}
```

## Python Client Example

Use `httpx` for async SSE client or `requests` for sync:

### Async with httpx

```python
import httpx
import json
import asyncio

async def stream_workflow(url: str, inputs: dict):
    """Stream workflow results using SSE."""
    async with httpx.AsyncClient() as client:
        async with client.stream(
            'POST',
            url,
            json={'inputs': inputs},
            headers={'Accept': 'text/event-stream'},
            timeout=60.0
        ) as response:
            # Parse SSE stream
            current_event = {}
            buffer = ''

            async for chunk in response.aiter_text():
                buffer += chunk
                lines = buffer.split('\n')
                buffer = lines.pop() if lines else ''

                for line in lines:
                    if line == '':
                        # Dispatch event
                        if current_event.get('data'):
                            event_type = current_event.get('event', 'message')
                            event_data = json.loads(current_event['data'])
                            event_id = current_event.get('id')

                            handle_event(event_type, event_data, event_id)
                            current_event = {}

                    elif line.startswith(':'):
                        # Comment (keepalive)
                        print('Keepalive')

                    elif ':' in line:
                        # Parse field
                        field, _, value = line.partition(':')
                        value = value.lstrip()  # Remove leading space
                        current_event[field] = value

def handle_event(event_type: str, data: dict, event_id: str):
    """Handle SSE event."""
    print(f"[{event_id}] {event_type}: {data}")

    if event_type == 'start':
        print(f"Workflow {data['workflow_id']} started")
    elif event_type == 'complete':
        print(f"Result: {data['result']}")
    elif event_type == 'error':
        print(f"Error: {data['error']}")

# Usage
asyncio.run(stream_workflow(
    'http://localhost:8000/workflows/chat/execute',
    inputs={'message': 'Hello!'}
))
```

### Sync with requests

```python
import requests
import json

def stream_workflow(url: str, inputs: dict):
    """Stream workflow results using SSE (sync)."""
    response = requests.post(
        url,
        json={'inputs': inputs},
        headers={'Accept': 'text/event-stream'},
        stream=True
    )

    current_event = {}
    buffer = ''

    for chunk in response.iter_content(chunk_size=1, decode_unicode=True):
        if chunk:
            buffer += chunk

            if '\n' in buffer:
                lines = buffer.split('\n')
                buffer = lines.pop() if lines else ''

                for line in lines:
                    if line == '':
                        # Dispatch event
                        if current_event.get('data'):
                            event_type = current_event.get('event', 'message')
                            event_data = json.loads(current_event['data'])
                            event_id = current_event.get('id')

                            handle_event(event_type, event_data, event_id)
                            current_event = {}

                    elif line.startswith(':'):
                        print('Keepalive')

                    elif ':' in line:
                        field, _, value = line.partition(':')
                        value = value.lstrip()
                        current_event[field] = value

# Usage
stream_workflow(
    'http://localhost:8000/workflows/chat/execute',
    inputs={'message': 'Hello!'}
)
```

## Complete Working Example: Real-Time Chat

### Server (Nexus with SSE)

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder

app = Nexus(
    api_port=8000,
    enable_auth=False,
    cors_origins=["*"]  # Allow all origins for demo
)

# Create AI chat workflow
chat_workflow = WorkflowBuilder()
chat_workflow.add_node(
    "LLMAgentNode",
    "chat_agent",
    {
        "system_prompt": "You are a helpful AI assistant.",
        "model": "gpt-4",
        "temperature": 0.7,
        "max_tokens": 500
    }
)

# Register workflow - SSE enabled automatically
app.register("chat", chat_workflow)

if __name__ == "__main__":
    print("Starting Nexus server with SSE support...")
    print("Chat endpoint: http://localhost:8000/workflows/chat/execute")
    print("OpenAPI docs: http://localhost:8000/docs")
    app.run()
```

### Client (Browser HTML/JavaScript)

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Real-Time AI Chat with SSE</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            display: flex;
            justify-content: center;
            align-items: center;
            padding: 20px;
        }

        .chat-container {
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            max-width: 800px;
            width: 100%;
            height: 600px;
            display: flex;
            flex-direction: column;
        }

        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 12px 12px 0 0;
        }

        .chat-header h1 {
            font-size: 24px;
        }

        .chat-status {
            font-size: 12px;
            opacity: 0.9;
            margin-top: 5px;
        }

        .chat-messages {
            flex: 1;
            overflow-y: auto;
            padding: 20px;
            background: #f8f9fa;
        }

        .message {
            margin-bottom: 15px;
            animation: slideIn 0.3s ease-out;
        }

        @keyframes slideIn {
            from {
                opacity: 0;
                transform: translateY(10px);
            }
            to {
                opacity: 1;
                transform: translateY(0);
            }
        }

        .message.user {
            text-align: right;
        }

        .message.assistant {
            text-align: left;
        }

        .message-bubble {
            display: inline-block;
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 18px;
            word-wrap: break-word;
        }

        .message.user .message-bubble {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
        }

        .message.assistant .message-bubble {
            background: white;
            color: #333;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }

        .message-time {
            font-size: 11px;
            color: #999;
            margin-top: 4px;
        }

        .chat-input-container {
            padding: 20px;
            background: white;
            border-radius: 0 0 12px 12px;
            border-top: 1px solid #e0e0e0;
        }

        .chat-input-form {
            display: flex;
            gap: 10px;
        }

        .chat-input {
            flex: 1;
            padding: 12px 16px;
            border: 2px solid #e0e0e0;
            border-radius: 24px;
            font-size: 14px;
            transition: border-color 0.3s;
        }

        .chat-input:focus {
            outline: none;
            border-color: #667eea;
        }

        .chat-input:disabled {
            background: #f0f0f0;
            cursor: not-allowed;
        }

        .send-button {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 24px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }

        .send-button:hover:not(:disabled) {
            transform: translateY(-2px);
        }

        .send-button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
        }

        .typing-indicator {
            display: none;
            padding: 12px 16px;
            background: white;
            border-radius: 18px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            max-width: 70%;
        }

        .typing-indicator.active {
            display: inline-block;
        }

        .typing-dots {
            display: flex;
            gap: 4px;
        }

        .typing-dots span {
            width: 8px;
            height: 8px;
            background: #999;
            border-radius: 50%;
            animation: bounce 1.4s infinite ease-in-out both;
        }

        .typing-dots span:nth-child(1) {
            animation-delay: -0.32s;
        }

        .typing-dots span:nth-child(2) {
            animation-delay: -0.16s;
        }

        @keyframes bounce {
            0%, 80%, 100% {
                transform: scale(0);
            }
            40% {
                transform: scale(1);
            }
        }
    </style>
</head>
<body>
    <div class="chat-container">
        <div class="chat-header">
            <h1>🤖 AI Assistant</h1>
            <div class="chat-status" id="status">Ready to chat</div>
        </div>

        <div class="chat-messages" id="messages">
            <div class="message assistant">
                <div class="message-bubble">
                    Hello! I'm your AI assistant. How can I help you today?
                </div>
            </div>
        </div>

        <div class="chat-input-container">
            <form class="chat-input-form" id="chatForm">
                <input
                    type="text"
                    class="chat-input"
                    id="messageInput"
                    placeholder="Type your message..."
                    autocomplete="off"
                >
                <button type="submit" class="send-button" id="sendButton">
                    Send
                </button>
            </form>
        </div>
    </div>

    <script>
        const messagesContainer = document.getElementById('messages');
        const messageInput = document.getElementById('messageInput');
        const chatForm = document.getElementById('chatForm');
        const sendButton = document.getElementById('sendButton');
        const statusElement = document.getElementById('status');

        // Configuration
        const API_URL = 'http://localhost:8000/workflows/chat/execute';

        function addMessage(role, content) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `message ${role}`;

            const time = new Date().toLocaleTimeString();

            messageDiv.innerHTML = `
                <div class="message-bubble">${content}</div>
                <div class="message-time">${time}</div>
            `;

            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        function showTypingIndicator() {
            const indicator = document.createElement('div');
            indicator.className = 'message assistant';
            indicator.id = 'typingIndicator';
            indicator.innerHTML = `
                <div class="typing-indicator active">
                    <div class="typing-dots">
                        <span></span>
                        <span></span>
                        <span></span>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(indicator);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }

        function hideTypingIndicator() {
            const indicator = document.getElementById('typingIndicator');
            if (indicator) {
                indicator.remove();
            }
        }

        function updateStatus(text, isError = false) {
            statusElement.textContent = text;
            statusElement.style.color = isError ? '#ff4444' : 'white';
        }

        async function sendMessage(message) {
            // Add user message to UI
            addMessage('user', message);

            // Disable input
            messageInput.disabled = true;
            sendButton.disabled = true;
            showTypingIndicator();
            updateStatus('Sending message...');

            try {
                const response = await fetch(API_URL, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Accept': 'text/event-stream'
                    },
                    body: JSON.stringify({
                        inputs: {
                            user_message: message
                        }
                    })
                });

                if (!response.ok) {
                    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
                }

                updateStatus('Receiving response...');

                // Read SSE stream
                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                let currentEvent = {};

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (line === '') {
                            // Dispatch event
                            if (currentEvent.data) {
                                const eventType = currentEvent.event || 'message';
                                const eventData = JSON.parse(currentEvent.data);

                                handleSSEEvent(eventType, eventData);
                                currentEvent = {};
                            }
                        } else if (line.startsWith(':')) {
                            // Keepalive - ignore
                        } else if (line.includes(':')) {
                            const colonIndex = line.indexOf(':');
                            const field = line.slice(0, colonIndex);
                            let value = line.slice(colonIndex + 1);
                            if (value.startsWith(' ')) value = value.slice(1);
                            currentEvent[field] = value;
                        }
                    }
                }

            } catch (error) {
                console.error('Error:', error);
                hideTypingIndicator();
                addMessage('assistant', `Error: ${error.message}`);
                updateStatus('Error occurred', true);
            } finally {
                // Re-enable input
                messageInput.disabled = false;
                sendButton.disabled = false;
                messageInput.focus();
            }
        }

        function handleSSEEvent(eventType, data) {
            console.log(`SSE Event: ${eventType}`, data);

            switch (eventType) {
                case 'start':
                    updateStatus('Processing...');
                    break;

                case 'complete':
                    hideTypingIndicator();
                    const response = data.result?.response || 'No response';
                    addMessage('assistant', response);
                    updateStatus('Ready to chat');
                    break;

                case 'error':
                    hideTypingIndicator();
                    addMessage('assistant', `Error: ${data.error}`);
                    updateStatus('Error occurred', true);
                    setTimeout(() => updateStatus('Ready to chat'), 3000);
                    break;
            }
        }

        // Form submission
        chatForm.addEventListener('submit', (e) => {
            e.preventDefault();

            const message = messageInput.value.trim();
            if (message) {
                sendMessage(message);
                messageInput.value = '';
            }
        });

        // Focus input on load
        messageInput.focus();
    </script>
</body>
</html>
```

## Error Handling and Reconnection

### Automatic Reconnection

EventSource automatically reconnects on connection failure:

```javascript
const eventSource = new EventSource(url);

// Track reconnection attempts
let reconnectCount = 0;
const MAX_RECONNECTS = 5;

eventSource.addEventListener('open', () => {
    console.log('Connected');
    reconnectCount = 0; // Reset on successful connection
});

eventSource.onerror = (error) => {
    console.error('Connection error:', error);

    if (reconnectCount >= MAX_RECONNECTS) {
        console.error('Max reconnection attempts reached');
        eventSource.close();
        return;
    }

    reconnectCount++;
    console.log(`Reconnecting... (${reconnectCount}/${MAX_RECONNECTS})`);
};
```

### Custom Reconnection with Last Event ID

```javascript
let lastEventId = null;

function connect() {
    // Include last event ID for resumption
    const url = lastEventId
        ? `${baseUrl}?lastEventId=${lastEventId}`
        : baseUrl;

    const eventSource = new EventSource(url);

    eventSource.addEventListener('message', (event) => {
        lastEventId = event.lastEventId;
        // Process event...
    });

    eventSource.onerror = () => {
        eventSource.close();
        setTimeout(connect, 3000); // Reconnect after 3 seconds
    };

    return eventSource;
}

const eventSource = connect();
```

### Error Handling Best Practices

```javascript
const eventSource = new EventSource(url);

// Handle specific error event from server
eventSource.addEventListener('error', (event) => {
    const errorData = JSON.parse(event.data);

    switch (errorData.error_type) {
        case 'ValidationError':
            showUserError('Invalid input. Please check your request.');
            break;
        case 'AuthenticationError':
            redirectToLogin();
            break;
        case 'RateLimitError':
            showUserError('Too many requests. Please wait.');
            break;
        default:
            showUserError('An error occurred. Please try again.');
    }

    eventSource.close();
});

// Handle connection errors
eventSource.onerror = (error) => {
    console.error('Connection error:', error);

    if (eventSource.readyState === EventSource.CLOSED) {
        showUserError('Connection closed');
    } else {
        showUserError('Connection error. Retrying...');
    }
};

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    eventSource.close();
});
```

## Production Deployment

### 1. nginx Configuration

SSE requires special nginx configuration for proper streaming:

```nginx
server {
    listen 80;
    server_name api.example.com;

    location /workflows/ {
        proxy_pass http://127.0.0.1:8000;

        # Essential for SSE
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;

        # Disable buffering
        proxy_buffering off;
        proxy_cache off;

        # Timeouts
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;

        # Headers
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**Critical nginx settings for SSE:**
- `proxy_buffering off` - Disable response buffering
- `proxy_cache off` - Disable caching
- `chunked_transfer_encoding off` - Prevent chunk encoding
- `proxy_http_version 1.1` - Use HTTP/1.1
- `Connection ''` - Clear connection header
- Long timeouts - Prevent connection drops

### 2. CORS Configuration

```python
from nexus import Nexus

app = Nexus(
    api_port=8000,
    cors_origins=[
        "https://example.com",
        "https://app.example.com"
    ],
    cors_allow_methods=["GET", "POST"],
    cors_allow_headers=["*"]
)
```

### 3. Connection Timeout Handling

```python
# Server-side keepalive (built into WorkflowAPI)
# Sends :keepalive comment every few seconds

# Client-side timeout detection
const eventSource = new EventSource(url);
let timeoutId;

function resetTimeout() {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => {
        console.error('Connection timeout - no data received');
        eventSource.close();
        // Attempt reconnection
        connect();
    }, 30000); // 30 second timeout
}

eventSource.addEventListener('message', (event) => {
    resetTimeout();
    // Process event...
});

resetTimeout(); // Start timeout on connection
```

### 4. Load Balancer Configuration

**AWS Application Load Balancer:**
- Increase idle timeout to 3600 seconds
- Enable HTTP/2 (EventSource uses HTTP/1.1 but compatible)

**Google Cloud Load Balancer:**
- Set backend timeout to 3600 seconds
- Enable WebSocket/SSE support

### 5. Monitoring and Metrics

```python
import time
from kailash.workflow.builder import WorkflowBuilder

# Add timing metrics to workflow
workflow = WorkflowBuilder()

# Track execution time
start_time = time.time()

workflow.add_node("LLMAgentNode", "agent", {...})

# Log metrics after execution
execution_time = time.time() - start_time
logger.info(f"Workflow executed in {execution_time:.2f}s")
```

## Best Practices

### 1. Always Close Connections

```javascript
// Close when done
eventSource.addEventListener('complete', (event) => {
    // Process result
    eventSource.close();
});

// Close on error
eventSource.addEventListener('error', (event) => {
    eventSource.close();
});

// Close on page unload
window.addEventListener('beforeunload', () => {
    eventSource.close();
});
```

### 2. Use Keepalive for Long-Running Workflows

```python
# Nexus WorkflowAPI automatically sends keepalive
# Prevents proxy/browser timeout on idle connections
```

### 3. Implement Exponential Backoff for Reconnection

```javascript
let reconnectDelay = 1000; // Start with 1 second
const MAX_DELAY = 30000; // Max 30 seconds

function reconnect() {
    setTimeout(() => {
        connect();
        reconnectDelay = Math.min(reconnectDelay * 2, MAX_DELAY);
    }, reconnectDelay);
}

eventSource.onerror = () => {
    eventSource.close();
    reconnect();
};

// Reset delay on successful connection
eventSource.addEventListener('open', () => {
    reconnectDelay = 1000;
});
```

### 4. Validate Event Data

```javascript
eventSource.addEventListener('complete', (event) => {
    try {
        const data = JSON.parse(event.data);

        if (!data.result) {
            throw new Error('Invalid event data: missing result');
        }

        processResult(data.result);
    } catch (error) {
        console.error('Event data validation error:', error);
        handleError(error);
    }
});
```

### 5. Handle Browser Compatibility

```javascript
// Check EventSource support
if (typeof EventSource === 'undefined') {
    console.error('SSE not supported in this browser');
    // Fall back to polling or WebSockets
    useFallbackMethod();
} else {
    const eventSource = new EventSource(url);
}
```

### 6. Implement Client-Side Buffering

```javascript
const messageBuffer = [];
let isProcessing = false;

eventSource.addEventListener('message', (event) => {
    messageBuffer.push(JSON.parse(event.data));

    if (!isProcessing) {
        processBuffer();
    }
});

async function processBuffer() {
    isProcessing = true;

    while (messageBuffer.length > 0) {
        const message = messageBuffer.shift();
        await processMessage(message);
    }

    isProcessing = false;
}
```

## Troubleshooting

### Issue: Connection immediately closes

**Problem:** EventSource connects then immediately closes.

**Causes:**
- Server not sending proper SSE format
- CORS issue
- nginx buffering enabled

**Solution:**
```bash
# Check nginx configuration
proxy_buffering off;
proxy_cache off;

# Check CORS
app = Nexus(cors_origins=["*"])  # For testing only

# Verify SSE format (must end with \n\n)
data: {"test": "value"}\n\n
```

### Issue: Events not received in real-time

**Problem:** Events arrive in batches instead of streaming.

**Cause:** Proxy or browser buffering

**Solution:**
```nginx
# nginx
proxy_buffering off;
chunked_transfer_encoding off;

# Server - ensure flush after each event
yield f"data: {json.dumps(data)}\n\n"
```

### Issue: Connection timeout after 60 seconds

**Problem:** Connection closes after 60 seconds of inactivity.

**Cause:** Default proxy timeout

**Solution:**
```nginx
proxy_read_timeout 3600s;
```

```python
# Server sends keepalive (built into Nexus)
yield ":keepalive\n\n"
```

### Issue: High memory usage with many connections

**Problem:** Server memory grows with concurrent SSE connections.

**Cause:** Not properly closing connections or cleaning up resources.

**Solution:**
```python
# Use async generators to minimize memory
async def stream_results():
    try:
        for result in results:
            yield format_sse(result)
    finally:
        # Cleanup resources
        cleanup()
```

```javascript
// Client - always close when done
eventSource.addEventListener('complete', () => {
    eventSource.close();
});
```

## Next Steps

- **Custom Endpoints Guide**: Create custom SSE endpoints with `@app.endpoint()`
- **Query Parameters Guide**: Add filtering and pagination to SSE endpoints
- **Performance Guide**: Optimize SSE for high-concurrency scenarios
- **Authentication Guide**: Secure SSE endpoints with authentication

## Related Documentation

- [Custom Endpoints Guide](./custom_endpoints.md)
- [Query Parameters Guide](./query_parameters.md)
- [Performance Guide](./performance-guide.md)
- [MDN SSE Documentation](https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events)
