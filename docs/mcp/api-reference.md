# MCP API Reference

## Overview

This document provides a complete API reference for the Model Context Protocol (MCP) implementation in Kailash SDK. It covers server endpoints, client methods, transport protocols, and data models.

## Table of Contents

1. [Server API](#server-api)
2. [Client API](#client-api)
3. [Transport Protocols](#transport-protocols)
4. [Data Models](#data-models)
5. [Authentication](#authentication)
6. [Error Handling](#error-handling)
7. [WebSocket API](#websocket-api)
8. [SSE API](#sse-api)
9. [Tool API](#tool-api)
10. [Resource API](#resource-api)

## Server API

### Base URL

```
http://localhost:3000  # Development
https://mcp.example.com  # Production
```

### Health Endpoints

#### GET /health

Check server health status.

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2024-01-15T10:30:00Z",
  "checks": {
    "database": "healthy",
    "redis": "healthy",
    "tools": "healthy"
  }
}
```

**Status Codes:**
- `200`: Server is healthy
- `503`: Server is unhealthy

#### GET /ready

Check if server is ready to accept requests.

**Response:**
```json
{
  "ready": true,
  "initialized": true,
  "tools_loaded": 15
}
```

#### GET /metrics

Get Prometheus metrics.

**Response:**
```
# HELP mcp_requests_total Total number of requests
# TYPE mcp_requests_total counter
mcp_requests_total{method="GET",status="200"} 1234
```

### Authentication Endpoints

#### POST /auth/token

Obtain authentication token.

**Request:**
```json
{
  "username": "user@example.com",
  "password": "secure_password"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600,
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Status Codes:**
- `200`: Authentication successful
- `401`: Invalid credentials
- `429`: Too many attempts

#### POST /auth/refresh

Refresh access token.

**Request:**
```json
{
  "refresh_token": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type": "bearer",
  "expires_in": 3600
}
```

#### POST /auth/revoke

Revoke a token.

**Request:**
```json
{
  "token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
  "token_type_hint": "access_token"
}
```

**Response:**
```json
{
  "revoked": true
}
```

### Tool Management Endpoints

#### GET /tools

List all available tools.

**Headers:**
```
Authorization: Bearer <token>
```

**Query Parameters:**
- `category` (optional): Filter by tool category
- `search` (optional): Search tools by name or description
- `limit` (optional): Maximum number of results (default: 100)
- `offset` (optional): Pagination offset (default: 0)

**Response:**
```json
{
  "tools": [
    {
      "name": "search",
      "description": "Search the web for information",
      "category": "web",
      "version": "1.0.0",
      "parameters": {
        "type": "object",
        "properties": {
          "query": {
            "type": "string",
            "description": "Search query"
          },
          "max_results": {
            "type": "integer",
            "description": "Maximum number of results",
            "default": 10
          }
        },
        "required": ["query"]
      }
    }
  ],
  "total": 15,
  "limit": 100,
  "offset": 0
}
```

#### GET /tools/{tool_name}

Get details for a specific tool.

**Response:**
```json
{
  "name": "search",
  "description": "Search the web for information",
  "category": "web",
  "version": "1.0.0",
  "author": "MCP Team",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Search query",
        "minLength": 1,
        "maxLength": 500
      },
      "max_results": {
        "type": "integer",
        "description": "Maximum number of results",
        "minimum": 1,
        "maximum": 100,
        "default": 10
      },
      "safe_search": {
        "type": "boolean",
        "description": "Enable safe search",
        "default": true
      }
    },
    "required": ["query"]
  },
  "examples": [
    {
      "name": "Basic search",
      "parameters": {
        "query": "MCP protocol documentation"
      }
    }
  ],
  "rate_limit": "100/hour",
  "timeout": 30
}
```

#### POST /tools/{tool_name}/execute

Execute a specific tool.

**Request:**
```json
{
  "parameters": {
    "query": "MCP protocol documentation",
    "max_results": 5
  },
  "timeout": 30,
  "context": {
    "user_id": "user123",
    "session_id": "session456"
  }
}
```

**Response:**
```json
{
  "tool": "search",
  "status": "success",
  "result": {
    "results": [
      {
        "title": "MCP Documentation",
        "url": "https://example.com/mcp",
        "snippet": "Complete guide to Model Context Protocol..."
      }
    ],
    "total_results": 5,
    "search_time": 0.234
  },
  "execution_time": 1.234,
  "usage": {
    "requests_remaining": 99,
    "reset_time": "2024-01-15T11:00:00Z"
  }
}
```

**Error Response:**
```json
{
  "tool": "search",
  "status": "error",
  "error": {
    "type": "validation_error",
    "message": "Missing required parameter: query",
    "details": {
      "parameter": "query",
      "constraint": "required"
    }
  }
}
```

#### POST /tools/{tool_name}/validate

Validate tool parameters without execution.

**Request:**
```json
{
  "parameters": {
    "query": "test",
    "max_results": 150
  }
}
```

**Response:**
```json
{
  "valid": false,
  "errors": [
    {
      "parameter": "max_results",
      "message": "Value 150 exceeds maximum of 100",
      "constraint": "maximum"
    }
  ]
}
```

### Resource Management Endpoints

#### GET /resources

List available resources.

**Response:**
```json
{
  "resources": [
    {
      "id": "db_connection",
      "type": "database",
      "name": "Main Database",
      "status": "available",
      "metadata": {
        "engine": "postgresql",
        "version": "13.5"
      }
    }
  ]
}
```

#### GET /resources/{resource_id}

Get resource details.

**Response:**
```json
{
  "id": "db_connection",
  "type": "database",
  "name": "Main Database",
  "status": "available",
  "configuration": {
    "host": "localhost",
    "port": 5432,
    "database": "mcp_db"
  },
  "limits": {
    "max_connections": 100,
    "current_connections": 23
  }
}
```

### Prompt Management Endpoints

#### GET /prompts

List available prompts.

**Response:**
```json
{
  "prompts": [
    {
      "id": "code_review",
      "name": "Code Review Assistant",
      "description": "Reviews code for best practices",
      "parameters": [
        {
          "name": "language",
          "type": "string",
          "description": "Programming language"
        }
      ]
    }
  ]
}
```

#### POST /prompts/{prompt_id}/generate

Generate content using a prompt.

**Request:**
```json
{
  "parameters": {
    "language": "python",
    "code": "def hello(): print('world')"
  }
}
```

**Response:**
```json
{
  "prompt_id": "code_review",
  "generated": "## Code Review\n\n### Observations:\n1. Function lacks docstring...",
  "tokens_used": 150
}
```

## Client API

### Python Client

#### Installation

```bash
pip install kailash-sdk
```

#### Basic Usage

```python
from kailash.mcp import MCPClient

# Initialize client
client = MCPClient(
    server_url="http://localhost:3000",
    api_key="your-api-key"
)

# List tools
tools = await client.list_tools()

# Execute tool
result = await client.execute_tool(
    "search",
    {"query": "MCP documentation"}
)
```

#### Client Methods

##### MCPClient

```python
class MCPClient:
    """MCP client for interacting with MCP servers."""

    def __init__(
        self,
        server_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        max_retries: int = 3,
        transport: str = "http"
    ):
        """
        Initialize MCP client.

        Args:
            server_url: Base URL of MCP server
            api_key: Optional API key for authentication
            timeout: Request timeout in seconds
            max_retries: Maximum number of retry attempts
            transport: Transport protocol ("http", "sse", "websocket")
        """

    async def connect(self) -> None:
        """Establish connection to MCP server."""

    async def disconnect(self) -> None:
        """Close connection to MCP server."""

    async def list_tools(
        self,
        category: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Tool]:
        """
        List available tools.

        Args:
            category: Filter by category
            search: Search query

        Returns:
            List of Tool objects
        """

    async def get_tool(self, tool_name: str) -> Tool:
        """
        Get details for a specific tool.

        Args:
            tool_name: Name of the tool

        Returns:
            Tool object

        Raises:
            ToolNotFoundError: If tool doesn't exist
        """

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        timeout: Optional[int] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> ToolResult:
        """
        Execute a tool.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            timeout: Override default timeout
            context: Additional context

        Returns:
            ToolResult object

        Raises:
            ToolExecutionError: If execution fails
            ValidationError: If parameters are invalid
        """

    async def validate_parameters(
        self,
        tool_name: str,
        parameters: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate tool parameters.

        Args:
            tool_name: Name of the tool
            parameters: Parameters to validate

        Returns:
            ValidationResult object
        """

    async def list_resources(self) -> List[Resource]:
        """List available resources."""

    async def get_resource(self, resource_id: str) -> Resource:
        """Get resource details."""

    async def list_prompts(self) -> List[Prompt]:
        """List available prompts."""

    async def generate_from_prompt(
        self,
        prompt_id: str,
        parameters: Dict[str, Any]
    ) -> GeneratedContent:
        """Generate content using a prompt."""
```

##### Async Context Manager

```python
# Using as async context manager
async with MCPClient("http://localhost:3000") as client:
    result = await client.execute_tool("search", {"query": "test"})
```

##### Streaming Support

```python
# Stream results
async for chunk in client.stream_tool_execution("generate", {"prompt": "Write a story"}):
    print(chunk.content, end="")
```

### JavaScript/TypeScript Client

#### Installation

```bash
npm install @kailash/mcp-client
```

#### Basic Usage

```typescript
import { MCPClient } from '@kailash/mcp-client';

// Initialize client
const client = new MCPClient({
  serverUrl: 'http://localhost:3000',
  apiKey: 'your-api-key'
});

// List tools
const tools = await client.listTools();

// Execute tool
const result = await client.executeTool('search', {
  query: 'MCP documentation'
});
```

## Transport Protocols

### HTTP Transport

Standard request-response protocol.

**Example:**
```python
client = MCPClient(
    server_url="http://localhost:3000",
    transport="http"
)
```

### Server-Sent Events (SSE)

For server-to-client streaming.

**Endpoint:** `/events`

**Example:**
```python
client = MCPClient(
    server_url="http://localhost:3000",
    transport="sse"
)

async for event in client.stream_events():
    print(f"Event: {event.type}, Data: {event.data}")
```

**Event Format:**
```
event: tool_update
data: {"tool": "search", "status": "executing"}

event: tool_result
data: {"tool": "search", "result": {...}}

event: error
data: {"error": "Tool execution failed"}
```

### WebSocket Transport

For bidirectional real-time communication.

**Endpoint:** `/ws`

**Example:**
```python
client = MCPClient(
    server_url="ws://localhost:3000",
    transport="websocket"
)

# Send message
await client.send({
    "type": "execute_tool",
    "tool": "search",
    "parameters": {"query": "test"}
})

# Receive messages
async for message in client.messages():
    print(f"Received: {message}")
```

**Message Format:**

Client to Server:
```json
{
  "id": "msg-123",
  "type": "execute_tool",
  "tool": "search",
  "parameters": {
    "query": "test"
  }
}
```

Server to Client:
```json
{
  "id": "msg-123",
  "type": "tool_result",
  "tool": "search",
  "result": {
    "results": [...]
  }
}
```

## Data Models

### Tool

```typescript
interface Tool {
  name: string;
  description: string;
  category?: string;
  version: string;
  author?: string;
  parameters: JSONSchema;
  examples?: ToolExample[];
  rate_limit?: string;
  timeout?: number;
}

interface ToolExample {
  name: string;
  description?: string;
  parameters: Record<string, any>;
  expected_result?: any;
}
```

### ToolResult

```typescript
interface ToolResult {
  tool: string;
  status: 'success' | 'error';
  result?: any;
  error?: ToolError;
  execution_time: number;
  usage?: UsageInfo;
}

interface ToolError {
  type: string;
  message: string;
  details?: Record<string, any>;
}

interface UsageInfo {
  requests_remaining: number;
  reset_time: string;
  tokens_used?: number;
}
```

### Resource

```typescript
interface Resource {
  id: string;
  type: string;
  name: string;
  status: 'available' | 'busy' | 'offline';
  metadata?: Record<string, any>;
  configuration?: Record<string, any>;
  limits?: ResourceLimits;
}

interface ResourceLimits {
  max_connections?: number;
  current_connections?: number;
  rate_limit?: string;
}
```

### Prompt

```typescript
interface Prompt {
  id: string;
  name: string;
  description: string;
  parameters: PromptParameter[];
  template?: string;
  model?: string;
}

interface PromptParameter {
  name: string;
  type: 'string' | 'number' | 'boolean' | 'array' | 'object';
  description: string;
  required?: boolean;
  default?: any;
}
```

## Authentication

### API Key Authentication

Include API key in header:
```
X-API-Key: your-api-key
```

### Bearer Token Authentication

Include JWT token in header:
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGc...
```

### OAuth2 Flow

1. Redirect user to authorization URL:
```
https://mcp.example.com/oauth/authorize?client_id=YOUR_CLIENT_ID&redirect_uri=YOUR_REDIRECT_URI&response_type=code
```

2. Exchange authorization code for token:
```http
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code&code=AUTH_CODE&client_id=YOUR_CLIENT_ID&client_secret=YOUR_CLIENT_SECRET
```

## Error Handling

### Error Response Format

```json
{
  "error": {
    "type": "validation_error",
    "message": "Invalid parameter value",
    "code": "INVALID_PARAMETER",
    "details": {
      "parameter": "max_results",
      "value": 150,
      "constraint": "maximum",
      "maximum": 100
    },
    "request_id": "req-123",
    "timestamp": "2024-01-15T10:30:00Z"
  }
}
```

### Error Types

| Type | Description | HTTP Status |
|------|-------------|-------------|
| `validation_error` | Invalid input parameters | 400 |
| `authentication_error` | Authentication failed | 401 |
| `authorization_error` | Insufficient permissions | 403 |
| `not_found_error` | Resource not found | 404 |
| `rate_limit_error` | Rate limit exceeded | 429 |
| `timeout_error` | Request timeout | 408 |
| `internal_error` | Server error | 500 |
| `service_unavailable` | Service temporarily unavailable | 503 |

### Error Codes

| Code | Description |
|------|-------------|
| `INVALID_PARAMETER` | Parameter validation failed |
| `MISSING_PARAMETER` | Required parameter missing |
| `TOOL_NOT_FOUND` | Tool does not exist |
| `EXECUTION_FAILED` | Tool execution failed |
| `INVALID_TOKEN` | Invalid authentication token |
| `TOKEN_EXPIRED` | Authentication token expired |
| `INSUFFICIENT_PERMISSIONS` | User lacks required permissions |
| `RATE_LIMIT_EXCEEDED` | Too many requests |
| `RESOURCE_UNAVAILABLE` | Resource is not available |

## WebSocket API

### Connection

```javascript
const ws = new WebSocket('ws://localhost:3000/ws');

ws.onopen = () => {
  console.log('Connected to MCP server');

  // Authenticate
  ws.send(JSON.stringify({
    type: 'authenticate',
    token: 'your-jwt-token'
  }));
};
```

### Message Types

#### Client Messages

```typescript
// Authentication
{
  type: 'authenticate',
  token: string
}

// Execute tool
{
  id: string,
  type: 'execute_tool',
  tool: string,
  parameters: object,
  timeout?: number
}

// Cancel execution
{
  id: string,
  type: 'cancel_execution',
  execution_id: string
}

// Subscribe to events
{
  type: 'subscribe',
  events: string[]
}

// Ping
{
  type: 'ping'
}
```

#### Server Messages

```typescript
// Authentication result
{
  type: 'authenticated',
  user_id: string,
  permissions: string[]
}

// Tool result
{
  id: string,
  type: 'tool_result',
  tool: string,
  result: object,
  execution_time: number
}

// Tool progress
{
  id: string,
  type: 'tool_progress',
  tool: string,
  progress: number,
  message?: string
}

// Error
{
  id?: string,
  type: 'error',
  error: {
    type: string,
    message: string,
    code: string
  }
}

// Event
{
  type: 'event',
  event_type: string,
  data: object
}

// Pong
{
  type: 'pong'
}
```

### Reconnection

```javascript
class ReconnectingWebSocket {
  constructor(url, options = {}) {
    this.url = url;
    this.reconnectInterval = options.reconnectInterval || 1000;
    this.maxReconnectInterval = options.maxReconnectInterval || 30000;
    this.reconnectDecay = options.reconnectDecay || 1.5;
    this.reconnectAttempts = 0;
    this.connect();
  }

  connect() {
    this.ws = new WebSocket(this.url);

    this.ws.onopen = () => {
      console.log('Connected');
      this.reconnectAttempts = 0;
    };

    this.ws.onclose = () => {
      console.log('Disconnected');
      this.reconnect();
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  reconnect() {
    this.reconnectAttempts++;
    const timeout = Math.min(
      this.reconnectInterval * Math.pow(this.reconnectDecay, this.reconnectAttempts),
      this.maxReconnectInterval
    );

    console.log(`Reconnecting in ${timeout}ms...`);
    setTimeout(() => this.connect(), timeout);
  }
}
```

## SSE API

### Connection

```javascript
const eventSource = new EventSource('http://localhost:3000/events', {
  headers: {
    'Authorization': 'Bearer your-token'
  }
});

eventSource.onopen = () => {
  console.log('Connected to SSE stream');
};

eventSource.onerror = (error) => {
  console.error('SSE error:', error);
};
```

### Event Types

```javascript
// Tool updates
eventSource.addEventListener('tool_update', (event) => {
  const data = JSON.parse(event.data);
  console.log('Tool update:', data);
});

// System events
eventSource.addEventListener('system_event', (event) => {
  const data = JSON.parse(event.data);
  console.log('System event:', data);
});

// Custom events
eventSource.addEventListener('custom_event', (event) => {
  const data = JSON.parse(event.data);
  console.log('Custom event:', data);
});
```

## Tool API

### Creating Custom Tools

```python
from kailash.mcp import Tool, ToolParameter

class CustomTool(Tool):
    """Custom tool implementation."""

    def __init__(self):
        super().__init__(
            name="custom_tool",
            description="A custom tool",
            parameters={
                "input": ToolParameter(
                    type="string",
                    description="Input text",
                    required=True
                ),
                "options": ToolParameter(
                    type="object",
                    description="Additional options",
                    properties={
                        "format": {
                            "type": "string",
                            "enum": ["json", "text", "xml"]
                        }
                    }
                )
            }
        )

    async def execute(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the tool."""
        input_text = parameters["input"]
        options = parameters.get("options", {})

        # Tool logic here
        result = process_input(input_text, options)

        return {
            "output": result,
            "metadata": {
                "processed_at": datetime.utcnow().isoformat()
            }
        }
```

### Registering Tools

```python
from kailash.mcp import MCPServer

server = MCPServer()

# Register individual tool
server.register_tool(CustomTool())

# Register multiple tools
server.register_tools([
    SearchTool(),
    CalculatorTool(),
    CustomTool()
])

# Register with category
server.register_tool(CustomTool(), category="utilities")
```

## Resource API

### Resource Provider

```python
from kailash.mcp import ResourceProvider

class DatabaseResourceProvider(ResourceProvider):
    """Provide database resources."""

    async def list_resources(self) -> List[Resource]:
        """List available resources."""
        return [
            Resource(
                id="main_db",
                type="database",
                name="Main Database",
                status="available"
            )
        ]

    async def get_resource(self, resource_id: str) -> Resource:
        """Get specific resource."""
        if resource_id == "main_db":
            return Resource(
                id="main_db",
                type="database",
                name="Main Database",
                status="available",
                configuration={
                    "host": "localhost",
                    "port": 5432
                }
            )
        raise ResourceNotFoundError(f"Resource {resource_id} not found")
```

## Rate Limiting

### Rate Limit Headers

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 99
X-RateLimit-Reset: 1642252800
X-RateLimit-Reset-After: 3600
```

### Rate Limit Response

```json
{
  "error": {
    "type": "rate_limit_error",
    "message": "Rate limit exceeded",
    "code": "RATE_LIMIT_EXCEEDED",
    "details": {
      "limit": 100,
      "window": "1h",
      "reset_time": "2024-01-15T11:00:00Z"
    }
  }
}
```

## Pagination

### Request Parameters

- `limit`: Maximum number of items to return (default: 100, max: 1000)
- `offset`: Number of items to skip (default: 0)
- `cursor`: Cursor for cursor-based pagination

### Response Format

```json
{
  "data": [...],
  "pagination": {
    "total": 1234,
    "limit": 100,
    "offset": 200,
    "has_more": true,
    "next_cursor": "eyJpZCI6MTIzNH0="
  }
}
```

## Versioning

### API Version Header

```
X-API-Version: 1.0
```

### Version in URL

```
https://mcp.example.com/v1/tools
```

### Version Negotiation

```
Accept: application/vnd.mcp.v1+json
```

## CORS Configuration

### Allowed Origins

```
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, X-API-Key
Access-Control-Max-Age: 86400
```

## SDK Examples

### Python

```python
# Async example
import asyncio
from kailash.mcp import MCPClient

async def main():
    async with MCPClient("http://localhost:3000") as client:
        # List tools
        tools = await client.list_tools()
        print(f"Available tools: {[t.name for t in tools]}")

        # Execute tool
        result = await client.execute_tool(
            "search",
            {"query": "Python asyncio tutorial"}
        )
        print(f"Search results: {result.result}")

asyncio.run(main())
```

### JavaScript/TypeScript

```typescript
import { MCPClient } from '@kailash/mcp-client';

async function main() {
  const client = new MCPClient({
    serverUrl: 'http://localhost:3000',
    apiKey: process.env.MCP_API_KEY
  });

  try {
    // List tools
    const tools = await client.listTools();
    console.log('Available tools:', tools.map(t => t.name));

    // Execute tool
    const result = await client.executeTool('search', {
      query: 'TypeScript tutorials'
    });
    console.log('Search results:', result.result);
  } finally {
    await client.disconnect();
  }
}

main().catch(console.error);
```

### cURL Examples

```bash
# List tools
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:3000/tools

# Execute tool
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"parameters": {"query": "test"}}' \
  http://localhost:3000/tools/search/execute

# Stream events
curl -H "Authorization: Bearer $TOKEN" \
  -H "Accept: text/event-stream" \
  http://localhost:3000/events
```

## Best Practices

1. **Always use HTTPS in production**
2. **Implement proper error handling**
3. **Use exponential backoff for retries**
4. **Cache responses when appropriate**
5. **Monitor rate limits**
6. **Use connection pooling**
7. **Implement request timeouts**
8. **Log all API interactions**
9. **Validate inputs client-side**
10. **Use compression for large payloads**

## Conclusion

This API reference provides comprehensive documentation for integrating with MCP servers. For specific language SDKs and additional examples, refer to the respective SDK documentation.
