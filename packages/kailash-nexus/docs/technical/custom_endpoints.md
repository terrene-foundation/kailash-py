# Custom REST Endpoints

## Overview

Nexus allows you to register custom REST endpoints using the `@app.endpoint()` decorator. These endpoints are API-channel only (not available in CLI or MCP) and provide full FastAPI functionality including path parameters, query parameters, request validation, and automatic OpenAPI documentation.

Custom endpoints enable you to:
- Create specialized API routes beyond standard workflow execution
- Integrate with external systems using familiar REST patterns
- Build CRUD operations for resources
- Implement custom business logic with workflow integration

**When to use custom endpoints:**
- Resource-specific operations (e.g., `/api/conversations/{id}`)
- Complex query patterns not suited for standard workflow input
- Integration with existing REST APIs
- Custom authentication or authorization flows

## Quick Start

```python
from nexus import Nexus

app = Nexus(api_port=8000)

@app.endpoint("/api/health", methods=["GET"])
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

app.run()
```

Access: `GET http://localhost:8000/api/health`

## Basic Example

Create a simple endpoint with path parameter:

```python
from nexus import Nexus

app = Nexus(api_port=8000)

@app.endpoint("/api/users/{user_id}", methods=["GET"])
async def get_user(user_id: str):
    """Retrieve user information by ID."""
    return {
        "user_id": user_id,
        "name": "John Doe",
        "email": f"{user_id}@example.com"
    }

app.run()
```

**Usage:**
```bash
curl http://localhost:8000/api/users/u123
# Response: {"user_id": "u123", "name": "John Doe", "email": "u123@example.com"}
```

## Advanced Examples

### Example 1: Multiple HTTP Methods

```python
from nexus import Nexus
from pydantic import BaseModel
from typing import Dict

app = Nexus(api_port=8000)

# In-memory storage (for demonstration)
conversations: Dict[str, dict] = {}

class ConversationCreate(BaseModel):
    title: str
    description: str = ""

@app.endpoint("/api/conversations", methods=["POST"])
async def create_conversation(request: ConversationCreate):
    """Create a new conversation."""
    import uuid

    conversation_id = str(uuid.uuid4())
    conversation = {
        "id": conversation_id,
        "title": request.title,
        "description": request.description,
        "messages": []
    }
    conversations[conversation_id] = conversation

    return conversation

@app.endpoint("/api/conversations/{conversation_id}", methods=["GET"])
async def get_conversation(conversation_id: str):
    """Retrieve a specific conversation."""
    from fastapi import HTTPException

    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conversations[conversation_id]

@app.endpoint("/api/conversations/{conversation_id}", methods=["DELETE"])
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    from fastapi import HTTPException

    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    deleted = conversations.pop(conversation_id)
    return {"deleted": True, "conversation_id": deleted["id"]}

app.run()
```

**Usage:**
```bash
# Create conversation
curl -X POST http://localhost:8000/api/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "My Chat", "description": "Test conversation"}'

# Get conversation
curl http://localhost:8000/api/conversations/{conversation_id}

# Delete conversation
curl -X DELETE http://localhost:8000/api/conversations/{conversation_id}
```

### Example 2: Path Parameters with Type Validation

```python
from nexus import Nexus
from fastapi import HTTPException, Path
from typing import List

app = Nexus(api_port=8000)

@app.endpoint("/api/items/{item_id}/versions/{version}", methods=["GET"])
async def get_item_version(
    item_id: str = Path(..., min_length=3, max_length=50),
    version: int = Path(..., ge=1, le=100)
):
    """Get specific version of an item.

    Args:
        item_id: Item identifier (3-50 chars)
        version: Version number (1-100)
    """
    return {
        "item_id": item_id,
        "version": version,
        "data": f"Content for {item_id} v{version}"
    }

app.run()
```

**Usage:**
```bash
# Valid request
curl http://localhost:8000/api/items/abc123/versions/5

# Invalid - version out of range (422 error)
curl http://localhost:8000/api/items/abc123/versions/150

# Invalid - item_id too short (422 error)
curl http://localhost:8000/api/items/ab/versions/5
```

### Example 3: Integration with Workflows

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from pydantic import BaseModel
from typing import Optional

app = Nexus(api_port=8000)

# Register a workflow
chat_workflow = WorkflowBuilder()
chat_workflow.add_node(
    "LLMAgentNode",
    "chat_agent",
    {
        "system_prompt": "You are a helpful assistant.",
        "model": "gpt-4",
        "temperature": 0.7
    }
)
app.register("chat", chat_workflow)

# Create custom endpoint that executes workflow
class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None

@app.endpoint("/api/chat/{conversation_id}/message", methods=["POST"])
async def send_message(conversation_id: str, request: ChatRequest):
    """Send a message in a conversation using the chat workflow.

    This endpoint demonstrates how to execute registered workflows
    from custom endpoints.
    """
    # Execute the registered workflow
    result = await app._execute_workflow(
        workflow_name="chat",
        inputs={
            "user_message": request.message,
            "conversation_id": conversation_id
        }
    )

    return {
        "conversation_id": conversation_id,
        "user_message": request.message,
        "assistant_response": result.get("response", ""),
        "workflow_result": result
    }

app.run()
```

**Usage:**
```bash
curl -X POST http://localhost:8000/api/chat/conv123/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello, how are you?"}'
```

### Example 4: Rate Limiting Configuration

```python
from nexus import Nexus

app = Nexus(api_port=8000)

# Endpoint with custom rate limit
@app.endpoint("/api/public/search", methods=["GET"], rate_limit=10)
async def public_search(query: str):
    """Public search endpoint - limited to 10 requests per minute."""
    return {"query": query, "results": []}

# Endpoint with higher rate limit for authenticated users
@app.endpoint("/api/search", methods=["GET"], rate_limit=100)
async def authenticated_search(query: str):
    """Authenticated search - 100 requests per minute."""
    return {"query": query, "results": []}

# Endpoint with no rate limiting
@app.endpoint("/api/health", methods=["GET"], rate_limit=None)
async def health_check():
    """Health check - no rate limiting."""
    return {"status": "healthy"}

app.run()
```

**Rate limit behavior:**
- Rate limits are per-client IP address
- Uses 1-minute rolling window
- Returns 429 status code when exceeded
- Automatically cleans up old entries to prevent memory leaks

### Example 5: FastAPI Advanced Features

```python
from nexus import Nexus
from fastapi import Header, Cookie, Response, status
from pydantic import BaseModel
from typing import Optional

app = Nexus(api_port=8000)

class UserPreferences(BaseModel):
    theme: str = "light"
    language: str = "en"

@app.endpoint(
    "/api/preferences",
    methods=["POST"],
    status_code=status.HTTP_201_CREATED,
    tags=["user"],
    summary="Update user preferences",
    description="Store user preferences and set cookie"
)
async def update_preferences(
    preferences: UserPreferences,
    response: Response,
    user_agent: Optional[str] = Header(None)
):
    """Update user preferences with cookie storage."""

    # Set cookie with preferences
    response.set_cookie(
        key="preferences",
        value=f"{preferences.theme}:{preferences.language}",
        max_age=86400  # 1 day
    )

    return {
        "preferences": preferences.dict(),
        "user_agent": user_agent,
        "message": "Preferences saved"
    }

@app.endpoint("/api/preferences", methods=["GET"])
async def get_preferences(
    preferences: Optional[str] = Cookie(None)
):
    """Retrieve user preferences from cookie."""
    if preferences:
        theme, language = preferences.split(":")
        return {"theme": theme, "language": language}

    return {"theme": "light", "language": "en"}

app.run()
```

**Usage:**
```bash
# Set preferences
curl -X POST http://localhost:8000/api/preferences \
  -H "Content-Type: application/json" \
  -d '{"theme": "dark", "language": "es"}' \
  -c cookies.txt

# Get preferences (using cookie)
curl http://localhost:8000/api/preferences -b cookies.txt
```

## Complete Working Example: Chat Conversation API

```python
from nexus import Nexus
from kailash.workflow.builder import WorkflowBuilder
from pydantic import BaseModel, Field
from fastapi import HTTPException, Query, Path
from typing import List, Optional, Dict
import uuid
from datetime import datetime

app = Nexus(
    api_port=8000,
    enable_auth=False,
    enable_monitoring=False
)

# In-memory storage (use database in production)
conversations: Dict[str, dict] = {}
messages: Dict[str, List[dict]] = {}

# Pydantic models for request validation
class ConversationCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=100)
    system_prompt: str = Field(default="You are a helpful assistant.", max_length=500)

class MessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)

# Register AI chat workflow
chat_workflow = WorkflowBuilder()
chat_workflow.add_node(
    "LLMAgentNode",
    "chat_agent",
    {
        "model": "gpt-4",
        "temperature": 0.7
    }
)
app.register("chat", chat_workflow)

# === CONVERSATION ENDPOINTS ===

@app.endpoint("/api/conversations", methods=["POST"], rate_limit=20)
async def create_conversation(request: ConversationCreate):
    """Create a new conversation."""
    conversation_id = str(uuid.uuid4())

    conversation = {
        "id": conversation_id,
        "title": request.title,
        "system_prompt": request.system_prompt,
        "created_at": datetime.utcnow().isoformat(),
        "message_count": 0
    }

    conversations[conversation_id] = conversation
    messages[conversation_id] = []

    return conversation

@app.endpoint("/api/conversations", methods=["GET"], rate_limit=50)
async def list_conversations(
    limit: int = Query(20, gt=0, le=100),
    offset: int = Query(0, ge=0)
):
    """List all conversations with pagination."""
    all_conversations = list(conversations.values())
    total = len(all_conversations)

    paginated = all_conversations[offset:offset + limit]

    return {
        "conversations": paginated,
        "total": total,
        "limit": limit,
        "offset": offset
    }

@app.endpoint("/api/conversations/{conversation_id}", methods=["GET"], rate_limit=100)
async def get_conversation(
    conversation_id: str = Path(..., min_length=1)
):
    """Get a specific conversation."""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = conversations[conversation_id]
    conversation_messages = messages.get(conversation_id, [])

    return {
        **conversation,
        "messages": conversation_messages
    }

@app.endpoint("/api/conversations/{conversation_id}", methods=["DELETE"])
async def delete_conversation(conversation_id: str):
    """Delete a conversation."""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Remove conversation and messages
    deleted_conv = conversations.pop(conversation_id)
    messages.pop(conversation_id, None)

    return {"deleted": True, "conversation_id": deleted_conv["id"]}

# === MESSAGE ENDPOINTS ===

@app.endpoint("/api/conversations/{conversation_id}/messages", methods=["POST"], rate_limit=30)
async def send_message(
    conversation_id: str,
    request: MessageCreate
):
    """Send a message and get AI response using workflow."""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    conversation = conversations[conversation_id]

    # Add user message
    user_message = {
        "id": str(uuid.uuid4()),
        "role": "user",
        "content": request.content,
        "timestamp": datetime.utcnow().isoformat()
    }
    messages[conversation_id].append(user_message)

    # Execute chat workflow
    try:
        result = await app._execute_workflow(
            workflow_name="chat",
            inputs={
                "user_message": request.content,
                "system_prompt": conversation["system_prompt"]
            }
        )

        assistant_response = result.get("response", "I apologize, but I couldn't process that.")

    except Exception as e:
        # Fallback response on error
        assistant_response = f"Error processing message: {str(e)}"

    # Add assistant message
    assistant_message = {
        "id": str(uuid.uuid4()),
        "role": "assistant",
        "content": assistant_response,
        "timestamp": datetime.utcnow().isoformat()
    }
    messages[conversation_id].append(assistant_message)

    # Update conversation stats
    conversation["message_count"] = len(messages[conversation_id])

    return {
        "user_message": user_message,
        "assistant_message": assistant_message,
        "conversation_id": conversation_id
    }

@app.endpoint("/api/conversations/{conversation_id}/messages", methods=["GET"], rate_limit=100)
async def get_messages(
    conversation_id: str,
    limit: int = Query(50, gt=0, le=100),
    offset: int = Query(0, ge=0)
):
    """Get messages from a conversation with pagination."""
    if conversation_id not in conversations:
        raise HTTPException(status_code=404, detail="Conversation not found")

    all_messages = messages.get(conversation_id, [])
    total = len(all_messages)

    paginated = all_messages[offset:offset + limit]

    return {
        "messages": paginated,
        "total": total,
        "limit": limit,
        "offset": offset,
        "conversation_id": conversation_id
    }

if __name__ == "__main__":
    app.run()
```

**Complete API Usage:**

```bash
# 1. Create a conversation
CONV_ID=$(curl -X POST http://localhost:8000/api/conversations \
  -H "Content-Type: application/json" \
  -d '{"title": "AI Assistant Chat", "system_prompt": "You are a helpful AI assistant."}' \
  | jq -r '.id')

# 2. Send a message
curl -X POST http://localhost:8000/api/conversations/$CONV_ID/messages \
  -H "Content-Type: application/json" \
  -d '{"content": "Hello! What can you help me with?"}'

# 3. Get conversation with messages
curl http://localhost:8000/api/conversations/$CONV_ID

# 4. List all messages with pagination
curl "http://localhost:8000/api/conversations/$CONV_ID/messages?limit=10&offset=0"

# 5. List all conversations
curl "http://localhost:8000/api/conversations?limit=20&offset=0"

# 6. Delete conversation
curl -X DELETE http://localhost:8000/api/conversations/$CONV_ID
```

## API Reference

### `@app.endpoint()` Decorator

```python
def endpoint(
    path: str,
    methods: Optional[List[str]] = None,
    rate_limit: Optional[int] = None,
    **fastapi_kwargs
)
```

**Parameters:**

- **path** (str): URL path pattern. Supports FastAPI path parameters using `{param_name}` syntax.
  - Example: `/api/users/{user_id}/items/{item_id}`

- **methods** (List[str], optional): HTTP methods to support. Default: `["GET"]`
  - Valid: `["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]`

- **rate_limit** (int, optional): Requests per minute per client IP. Default: 100
  - Set to `None` for unlimited
  - Set to `0` for unlimited (same as `None`)
  - Enforced per client IP address with 1-minute rolling window

- **fastapi_kwargs**: Additional FastAPI route parameters
  - `status_code` (int): HTTP status code for successful response
  - `response_model` (Type): Pydantic model for response validation
  - `tags` (List[str]): OpenAPI tags for grouping
  - `summary` (str): Short description for OpenAPI docs
  - `description` (str): Long description for OpenAPI docs
  - `response_description` (str): Description of response
  - `deprecated` (bool): Mark endpoint as deprecated

**Returns:**
- Decorator function that registers the endpoint with FastAPI

**Raises:**
- `RuntimeError`: If gateway not initialized (called before `app.run()`)
- `ValueError`: If invalid HTTP method provided

### `app._execute_workflow()` Helper

```python
async def _execute_workflow(
    workflow_name: str,
    inputs: Dict[str, Any]
) -> Dict[str, Any]
```

**Parameters:**
- **workflow_name** (str): Name of registered workflow
- **inputs** (Dict[str, Any]): Input data for workflow execution

**Returns:**
- Dict[str, Any]: Workflow execution results

**Raises:**
- `HTTPException(404)`: If workflow not found
- `HTTPException(413)`: If input data exceeds 10MB
- `HTTPException(400)`: If input contains dangerous keys
- `HTTPException(500)`: If workflow execution fails

**Security Features:**
- Input size validation (max 10MB)
- Dangerous key filtering (prevents code injection)
- Key length validation (max 256 chars)
- Automatic error handling and conversion to HTTP exceptions

## Security Considerations

### 1. Rate Limiting

**Built-in rate limiting protects against abuse:**

```python
# Conservative limit for public endpoints
@app.endpoint("/api/public/data", methods=["GET"], rate_limit=10)
async def public_endpoint():
    return {"data": "public"}

# Higher limit for authenticated endpoints
@app.endpoint("/api/data", methods=["GET"], rate_limit=100)
async def authenticated_endpoint():
    return {"data": "protected"}
```

**Rate limiting features:**
- Per-client IP address tracking
- 1-minute rolling window
- Automatic cleanup (prevents memory leaks)
- Returns HTTP 429 when exceeded
- Configurable per-endpoint or globally

### 2. Input Validation

**Always use Pydantic models for request validation:**

```python
from pydantic import BaseModel, Field, validator

class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, pattern="^[a-zA-Z0-9_]+$")
    email: str = Field(..., pattern=r"^[\w\.-]+@[\w\.-]+\.\w+$")
    age: int = Field(..., ge=0, le=150)

    @validator('email')
    def validate_email_domain(cls, v):
        allowed_domains = ['example.com', 'company.com']
        domain = v.split('@')[1]
        if domain not in allowed_domains:
            raise ValueError(f'Email domain must be one of {allowed_domains}')
        return v

@app.endpoint("/api/users", methods=["POST"])
async def create_user(request: UserCreate):
    return {"user": request.dict()}
```

### 3. Path Parameter Validation

```python
from fastapi import Path

@app.endpoint("/api/items/{item_id}", methods=["GET"])
async def get_item(
    item_id: str = Path(..., pattern="^[a-zA-Z0-9-_]{3,50}$")
):
    """Only allow alphanumeric, dash, underscore (3-50 chars)."""
    return {"item_id": item_id}
```

### 4. Workflow Execution Security

**The `_execute_workflow()` helper includes built-in protections:**

- Maximum input size: 10MB
- Dangerous key filtering: Blocks `__class__`, `__builtins__`, `eval`, `exec`, etc.
- Key length validation: Maximum 256 characters
- Automatic error sanitization

```python
# Safe workflow execution
result = await app._execute_workflow(
    workflow_name="process_data",
    inputs={
        "user_input": user_data,  # Automatically validated
        "config": config_params
    }
)
```

### 5. Error Handling

**Never expose internal errors to clients:**

```python
from fastapi import HTTPException

@app.endpoint("/api/process", methods=["POST"])
async def process_data(request: DataRequest):
    try:
        result = await app._execute_workflow("process", request.dict())
        return result
    except HTTPException:
        # Re-raise HTTP exceptions (already safe)
        raise
    except Exception as e:
        # Log internal error, return safe message
        logger.error(f"Processing error: {e}")
        raise HTTPException(
            status_code=500,
            detail="An error occurred processing your request"
        )
```

## Production Deployment

### 1. CORS Configuration

```python
from nexus import Nexus

app = Nexus(
    api_port=8000,
    cors_origins=["https://example.com", "https://app.example.com"]
)
```

### 2. Behind Reverse Proxy (nginx)

**nginx configuration:**

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Rate limiting (nginx level)
        limit_req zone=api_limit burst=20 nodelay;
    }
}
```

### 3. Environment-Based Configuration

```python
import os
from nexus import Nexus

app = Nexus(
    api_port=int(os.getenv("API_PORT", "8000")),
    enable_auth=os.getenv("ENABLE_AUTH", "false").lower() == "true",
    enable_monitoring=os.getenv("ENABLE_MONITORING", "false").lower() == "true",
    cors_origins=os.getenv("CORS_ORIGINS", "*").split(",")
)
```

### 4. Health Check Endpoint

```python
@app.endpoint("/health", methods=["GET"], rate_limit=None)
async def health_check():
    """Health check for load balancers."""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }
```

### 5. Monitoring and Metrics

```python
from fastapi import Request
import time

@app.endpoint("/api/data", methods=["GET"])
async def get_data(request: Request):
    """Endpoint with timing metrics."""
    start_time = time.time()

    # Process request
    result = {"data": "example"}

    # Log metrics
    duration = time.time() - start_time
    logger.info(f"Request to /api/data completed in {duration:.3f}s")

    return result
```

## Best Practices

### 1. Use Descriptive Path Parameters

```python
# Good - clear and descriptive
@app.endpoint("/api/users/{user_id}/orders/{order_id}")

# Bad - vague parameter names
@app.endpoint("/api/users/{id}/orders/{id2}")
```

### 2. Version Your API

```python
@app.endpoint("/api/v1/users", methods=["GET"])
async def get_users_v1():
    return {"version": "1.0", "users": []}

@app.endpoint("/api/v2/users", methods=["GET"])
async def get_users_v2():
    return {"version": "2.0", "users": [], "metadata": {}}
```

### 3. Consistent Response Structure

```python
# Success response
{
    "success": true,
    "data": {...},
    "metadata": {...}
}

# Error response
{
    "success": false,
    "error": "Error message",
    "error_code": "VALIDATION_ERROR"
}
```

### 4. Use Appropriate HTTP Methods

- **GET**: Retrieve data (idempotent, cacheable)
- **POST**: Create new resource
- **PUT**: Update/replace entire resource
- **PATCH**: Partial update of resource
- **DELETE**: Remove resource

### 5. Leverage FastAPI Dependency Injection

```python
from fastapi import Depends, Header, HTTPException

async def verify_api_key(x_api_key: str = Header(...)):
    """Dependency to verify API key."""
    if x_api_key != "secret-key":
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

@app.endpoint("/api/protected", methods=["GET"])
async def protected_endpoint(api_key: str = Depends(verify_api_key)):
    """Endpoint protected by API key."""
    return {"message": "Access granted"}
```

### 6. Document with OpenAPI Tags

```python
@app.endpoint(
    "/api/users",
    methods=["GET"],
    tags=["users"],
    summary="List all users",
    description="Retrieve a paginated list of all users in the system"
)
async def list_users():
    return {"users": []}
```

### 7. Async All The Way

```python
# Good - fully async
@app.endpoint("/api/data", methods=["GET"])
async def get_data():
    result = await async_database_call()
    return result

# Avoid - mixing sync/async
@app.endpoint("/api/data", methods=["GET"])
async def get_data():
    result = sync_blocking_call()  # Blocks event loop!
    return result
```

## Troubleshooting

### Error: "Gateway not initialized"

**Problem:** Calling `@app.endpoint()` before gateway is ready.

**Solution:** Ensure decorators are defined before `app.run()`:

```python
app = Nexus()

@app.endpoint("/api/test", methods=["GET"])  # Define first
async def test(): return {}

app.run()  # Then run
```

### Error: "Rate limit exceeded (429)"

**Problem:** Too many requests from the same IP address.

**Solution:** Adjust rate limit or implement authentication:

```python
# Increase limit for authenticated users
@app.endpoint("/api/data", methods=["GET"], rate_limit=500)
async def get_data(api_key: str = Depends(verify_api_key)):
    return {"data": "example"}
```

### Error: "Validation error (422)"

**Problem:** Request data doesn't match Pydantic model.

**Solution:** Check request format and model validators:

```python
# Request
{
    "name": "ab"  # Too short
}

# Model
class User(BaseModel):
    name: str = Field(..., min_length=3)  # Minimum 3 chars
```

### Error: "Workflow not found (404)"

**Problem:** Calling `_execute_workflow()` with unregistered workflow.

**Solution:** Ensure workflow is registered before use:

```python
# Register workflow
app.register("my_workflow", workflow_builder)

# Then use in endpoint
result = await app._execute_workflow("my_workflow", inputs)
```

## Next Steps

- **Query Parameters Guide**: Learn how to use query parameters for filtering and pagination
- **SSE Streaming Guide**: Implement real-time updates with Server-Sent Events
- **Authentication Guide**: Add authentication and authorization to custom endpoints
- **OpenAPI Documentation**: Auto-generate API documentation with FastAPI

## Related Documentation

- [Nexus Architecture Overview](./architecture-overview.md)
- [Security Guide](./security-guide.md)
- [Integration Guide](./integration-guide.md)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
