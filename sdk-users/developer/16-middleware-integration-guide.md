# Middleware Integration Guide
## Building Production Applications with Kailash Middleware

**Target Audience**: SDK Users building production applications
**Prerequisites**: Basic Kailash SDK knowledge, Python async/await
**Complexity**: Intermediate to Advanced

## Overview

The Kailash Middleware provides enterprise-grade components for building production applications with real-time agent-frontend communication, session management, and comprehensive security. This guide demonstrates practical patterns for integrating middleware into your applications.

## Quick Start

### Basic Middleware Stack

Create a minimal middleware stack for frontend communication:

```python
from kailash.middleware import AgentUIMiddleware, APIGateway, create_gateway
import asyncio

async def create_basic_middleware():
    """Create a basic middleware stack for development."""

    # Create agent-UI middleware with session management
    agent_ui = AgentUIMiddleware(
        enable_dynamic_workflows=True,
        max_sessions=100,
        session_timeout_minutes=30,
        enable_persistence=False  # For development
    )

    # Create API gateway with basic configuration
    gateway = create_gateway(
        title="My Kailash Application",
        version="1.0.0",
        cors_origins=["http://localhost:3000"],  # Your frontend URL
        enable_docs=True
    )

    # Connect components
    gateway.agent_ui = agent_ui

    return agent_ui, gateway

# Usage
async def main():
    agent_ui, gateway = await create_basic_middleware()

    # Start the API server
    import uvicorn
    uvicorn.run(gateway.app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    asyncio.run(main())
```

### Frontend Session Management

Establish sessions for frontend clients:

```python
async def handle_frontend_connection():
    """Handle new frontend client connection."""

    # Create session for frontend client
    session_id = await agent_ui.create_session(
        user_id="user123",
        metadata={
            "client": "web",
            "version": "1.0.0",
            "user_agent": "Mozilla/5.0...",
            "ip_address": "192.168.1.100"
        }
    )

    print(f"Created session: {session_id}")
    return session_id

# Frontend session cleanup
async def cleanup_frontend_session(session_id: str):
    """Clean up frontend session on disconnect."""
    await agent_ui.close_session(session_id)
    print(f"Cleaned up session: {session_id}")
```

## Dynamic Workflow Creation

### Configuration-Driven Workflows

Create workflows dynamically from frontend configurations:

```python
async def create_data_processing_workflow(session_id: str):
    """Create a data processing workflow from frontend configuration."""

    # Frontend sends workflow configuration
    workflow_config = {
        "name": "customer_data_pipeline",
        "description": "Process customer data and generate insights",
        "nodes": [
            {
                "id": "csv_reader",
                "type": "CSVReaderNode",
                "config": {
                    "name": "csv_reader",
                    "file_path": "/data/customers.csv",
                    "has_header": True
                }
            },
            {
                "id": "data_validator",
                "type": "PythonCodeNode",
                "config": {
                    "name": "data_validator",
                    "code": """
# Validate customer data
import pandas as pd

# Input validation
if not isinstance(data, pd.DataFrame):
    raise ValueError("Expected DataFrame input")

# Data quality checks
missing_data = data.isnull().sum()
duplicate_records = data.duplicated().sum()

# Clean data
cleaned_data = data.dropna().drop_duplicates()

result = {
    "cleaned_data": cleaned_data.to_dict('records'),
    "quality_metrics": {
        "original_rows": len(data),
        "cleaned_rows": len(cleaned_data),
        "missing_values": missing_data.to_dict(),
        "duplicates_removed": duplicate_records
    }
}
"""
                }
            },
            {
                "id": "insights_generator",
                "type": "PythonCodeNode",
                "config": {
                    "name": "insights_generator",
                    "code": """
# Generate customer insights
import pandas as pd

data_df = pd.DataFrame(cleaned_data)

# Calculate insights
insights = {
    "total_customers": len(data_df),
    "average_age": data_df['age'].mean() if 'age' in data_df.columns else None,
    "geographic_distribution": data_df['location'].value_counts().to_dict() if 'location' in data_df.columns else {},
    "quality_score": quality_metrics["cleaned_rows"] / quality_metrics["original_rows"] * 100
}

result = {
    "insights": insights,
    "summary": f"Processed {len(data_df)} customers with {insights['quality_score']:.1f}% data quality"
}
"""
                }
            }
        ],
        "connections": [
            {
                "from_node": "csv_reader",
                "from_output": "data",
                "to_node": "data_validator",
                "to_input": "data"
            },
            {
                "from_node": "data_validator",
                "from_output": "cleaned_data",
                "to_node": "insights_generator",
                "to_input": "cleaned_data"
            },
            {
                "from_node": "data_validator",
                "from_output": "quality_metrics",
                "to_node": "insights_generator",
                "to_input": "quality_metrics"
            }
        ]
    }

    # Create workflow using middleware
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=workflow_config
    )

    print(f"Created workflow: {workflow_id}")
    return workflow_id

# Usage example
async def process_customer_data():
    session_id = await agent_ui.create_session("data_analyst")
    workflow_id = await create_data_processing_workflow(session_id)

    # Execute workflow
    execution_id = await agent_ui.execute_workflow(
        session_id=session_id,
        workflow_id=workflow_id,
        inputs={}  # CSV file path is in configuration
    )

    # Monitor execution
    while True:
        status = await agent_ui.get_execution_status(execution_id, session_id)
        print(f"Status: {status['status']}, Progress: {status['progress']}%")

        if status['status'] in ['completed', 'failed']:
            break

        await asyncio.sleep(1)

    if status['status'] == 'completed':
        print("Results:", status['outputs'])
    else:
        print("Error:", status['error'])
```

### Template-Based Workflows

Create reusable workflow templates:

```python
class WorkflowTemplates:
    """Collection of reusable workflow templates."""

    @staticmethod
    def data_processing_template(input_file: str, output_format: str = "json"):
        """Template for data processing workflows."""
        return {
            "name": "data_processing_template",
            "description": "Generic data processing template",
            "nodes": [
                {
                    "id": "file_reader",
                    "type": "CSVReaderNode" if input_file.endswith('.csv') else "JSONReaderNode",
                    "config": {
                        "name": "file_reader",
                        "file_path": input_file
                    }
                },
                {
                    "id": "data_processor",
                    "type": "DataTransformer",
                    "config": {
                        "name": "data_processor",
                        "transformation_type": "normalize"
                    }
                },
                {
                    "id": "output_writer",
                    "type": "PythonCodeNode",
                    "config": {
                        "name": "output_writer",
                        "code": f"""
import json
import pandas as pd

# Write data in requested format
if "{output_format}" == "json":
    result = {{"data": data.to_dict('records') if hasattr(data, 'to_dict') else data}}
elif "{output_format}" == "csv":
    if hasattr(data, 'to_csv'):
        result = {{"csv_data": data.to_csv(index=False)}}
    else:
        result = {{"error": "Data cannot be converted to CSV"}}
else:
    result = {{"data": data}}
"""
                    }
                }
            ],
            "connections": [
                {
                    "from_node": "file_reader",
                    "from_output": "data",
                    "to_node": "data_processor",
                    "to_input": "data"
                },
                {
                    "from_node": "data_processor",
                    "from_output": "transformed_data",
                    "to_node": "output_writer",
                    "to_input": "data"
                }
            ]
        }

    @staticmethod
    def ai_chat_template(model_provider: str = "ollama", model_name: str = "llama3.2:3b"):
        """Template for AI chat workflows."""
        return {
            "name": "ai_chat_template",
            "description": "AI chat interaction template",
            "nodes": [
                {
                    "id": "message_processor",
                    "type": "PythonCodeNode",
                    "config": {
                        "name": "message_processor",
                        "code": """
# Process incoming chat message
processed_message = {
    "role": "user",
    "content": user_message,
    "timestamp": __import__('datetime').datetime.now().isoformat()
}

result = {"messages": [processed_message]}
"""
                    }
                },
                {
                    "id": "llm_agent",
                    "type": "LLMAgentNode",
                    "config": {
                        "name": "llm_agent",
                        "provider": model_provider,
                        "model": model_name,
                        "temperature": 0.7,
                        "max_tokens": 1000
                    }
                },
                {
                    "id": "response_formatter",
                    "type": "PythonCodeNode",
                    "config": {
                        "name": "response_formatter",
                        "code": """
# Format LLM response for frontend
formatted_response = {
    "message": response.get("content", "Sorry, I couldn't generate a response."),
    "model": response.get("model", "unknown"),
    "timestamp": __import__('datetime').datetime.now().isoformat(),
    "metadata": {
        "tokens_used": response.get("usage", {}),
        "model_info": response.get("model_info", {})
    }
}

result = {"chat_response": formatted_response}
"""
                    }
                }
            ],
            "connections": [
                {
                    "from_node": "message_processor",
                    "from_output": "messages",
                    "to_node": "llm_agent",
                    "to_input": "messages"
                },
                {
                    "from_node": "llm_agent",
                    "from_output": "response",
                    "to_node": "response_formatter",
                    "to_input": "response"
                }
            ]
        }

# Usage
async def create_template_workflow(session_id: str, template_name: str, **kwargs):
    """Create workflow from template."""

    templates = {
        "data_processing": WorkflowTemplates.data_processing_template,
        "ai_chat": WorkflowTemplates.ai_chat_template
    }

    if template_name not in templates:
        raise ValueError(f"Unknown template: {template_name}")

    # Generate workflow config from template
    workflow_config = templates[template_name](**kwargs)

    # Create workflow
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id=session_id,
        workflow_config=workflow_config
    )

    return workflow_id
```

## Real-time Communication

### WebSocket Integration

Set up real-time communication with frontend:

```python
from kailash.middleware import RealtimeMiddleware
from fastapi import WebSocket, WebSocketDisconnect
import json

# Create real-time middleware
realtime_middleware = RealtimeMiddleware(agent_ui)

async def websocket_endpoint(websocket: WebSocket):
    """Handle WebSocket connections for real-time communication."""
    await websocket.accept()

    # Create session for this WebSocket connection
    session_id = await agent_ui.create_session(
        user_id="websocket_user",
        metadata={"connection_type": "websocket"}
    )

    # Subscribe to events for this session
    events_received = []

    async def event_handler(event):
        # Send events to frontend via WebSocket
        event_data = {
            "type": event.type.value,
            "data": event.to_dict()
        }
        await websocket.send_text(json.dumps(event_data))

    subscriber_id = await agent_ui.subscribe_to_events(
        f"websocket_{session_id}",
        event_handler,
        session_id=session_id
    )

    try:
        while True:
            # Receive messages from frontend
            data = await websocket.receive_text()
            message = json.loads(data)

            if message["type"] == "execute_workflow":
                # Execute workflow based on frontend request
                workflow_config = message["workflow_config"]

                workflow_id = await agent_ui.create_dynamic_workflow(
                    session_id=session_id,
                    workflow_config=workflow_config
                )

                execution_id = await agent_ui.execute_workflow(
                    session_id=session_id,
                    workflow_id=workflow_id,
                    inputs=message.get("inputs", {})
                )

                # Send execution ID back to frontend
                await websocket.send_text(json.dumps({
                    "type": "execution_started",
                    "execution_id": execution_id
                }))

            elif message["type"] == "get_status":
                # Send current execution status
                execution_id = message["execution_id"]
                status = await agent_ui.get_execution_status(execution_id, session_id)

                await websocket.send_text(json.dumps({
                    "type": "status_update",
                    "status": status
                }))

    except WebSocketDisconnect:
        # Clean up on disconnect
        await agent_ui.unsubscribe_from_events(subscriber_id)
        await agent_ui.close_session(session_id)
```

### Server-Sent Events

Set up SSE for one-way real-time updates:

```python
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator

async def create_sse_stream(session_id: str) -> AsyncGenerator[str, None]:
    """Create SSE stream for real-time updates."""

    import asyncio
    import json
    from collections import deque

    # Event queue for this session
    event_queue = deque()

    async def event_handler(event):
        event_data = {
            "id": event.id,
            "type": event.type.value,
            "data": json.dumps(event.to_dict())
        }
        event_queue.append(event_data)

    # Subscribe to events
    subscriber_id = await agent_ui.subscribe_to_events(
        f"sse_{session_id}",
        event_handler,
        session_id=session_id
    )

    try:
        while True:
            if event_queue:
                event = event_queue.popleft()
                yield f"id: {event['id']}\\n"
                yield f"event: {event['type']}\\n"
                yield f"data: {event['data']}\\n\\n"
            else:
                # Send heartbeat
                yield f"event: heartbeat\\n"
                yield f"data: {json.dumps({'timestamp': time.time()})}\\n\\n"

            await asyncio.sleep(1)

    finally:
        await agent_ui.unsubscribe_from_events(subscriber_id)

# FastAPI endpoint for SSE
@app.get("/events/{session_id}")
async def stream_events(session_id: str):
    """Stream events via Server-Sent Events."""
    return StreamingResponse(
        create_sse_stream(session_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

## AI Chat Integration

### Conversational AI with Context

Integrate AI chat with context management:

```python
from kailash.middleware import AIChatMiddleware

# Create AI chat middleware with vector search
ai_chat = AIChatMiddleware(
    agent_ui,
    enable_vector_search=True,
    vector_database_url="postgresql://localhost/kailash_vectors",
    default_model_provider="ollama",
    default_model="llama3.2:3b"
)

async def handle_chat_message(session_id: str, user_message: str):
    """Handle incoming chat message with context."""

    # Start or continue chat session
    chat_session_id = await ai_chat.start_chat_session(session_id)

    # Send message with context
    response = await ai_chat.send_message(
        chat_session_id,
        user_message,
        context={
            "available_workflows": await get_available_workflows(session_id),
            "user_preferences": await get_user_preferences(session_id),
            "current_session_data": await get_session_context(session_id)
        }
    )

    # Check if AI suggests workflow creation
    if response.get("intent") == "create_workflow":
        workflow_config = response.get("workflow_config")
        if workflow_config:
            # Create suggested workflow
            workflow_id = await agent_ui.create_dynamic_workflow(
                session_id, workflow_config
            )

            # Add workflow info to response
            response["created_workflow"] = {
                "workflow_id": workflow_id,
                "message": f"I've created a workflow '{workflow_config['name']}' for you. Would you like to execute it?"
            }

    return response

async def get_available_workflows(session_id: str) -> list:
    """Get workflows available in session."""
    session = await agent_ui.get_session(session_id)
    if session:
        return list(session.workflows.keys())
    return []

async def get_user_preferences(session_id: str) -> dict:
    """Get user preferences for AI responses."""
    session = await agent_ui.get_session(session_id)
    if session and session.metadata:
        return session.metadata.get("user_preferences", {})
    return {}

async def get_session_context(session_id: str) -> dict:
    """Get current session context."""
    session = await agent_ui.get_session(session_id)
    if session:
        return {
            "active_workflows": len(session.workflows),
            "recent_executions": len(session.executions),
            "session_age_minutes": (datetime.utcnow() - session.created_at).total_seconds() / 60
        }
    return {}
```

### Natural Language to Workflow

Convert natural language descriptions to workflows:

```python
async def create_workflow_from_description(session_id: str, description: str):
    """Create workflow from natural language description."""

    # Use AI chat to analyze description
    chat_session_id = await ai_chat.start_chat_session(session_id)

    # Send structured prompt for workflow generation
    workflow_prompt = f"""
Based on this description, create a Kailash workflow configuration:

Description: {description}

Please analyze the requirements and create a workflow with:
1. Appropriate nodes for the task
2. Proper connections between nodes
3. Realistic configuration parameters

Available node types:
- CSVReaderNode: Read CSV files
- JSONReaderNode: Read JSON files
- PythonCodeNode: Custom Python processing
- DataTransformer: Data transformation operations
- LLMAgentNode: AI/LLM interactions
- HTTPRequestNode: API calls
- SQLDatabaseNode: Database operations

Return only a valid JSON workflow configuration.
"""

    response = await ai_chat.send_message(
        chat_session_id,
        workflow_prompt,
        context={
            "mode": "workflow_generation",
            "response_format": "json"
        }
    )

    # Parse workflow configuration from AI response
    try:
        import json
        import re

        # Extract JSON from response
        json_match = re.search(r'{.*}', response["message"], re.DOTALL)
        if json_match:
            workflow_config = json.loads(json_match.group())

            # Validate and create workflow
            workflow_id = await agent_ui.create_dynamic_workflow(
                session_id, workflow_config
            )

            return {
                "success": True,
                "workflow_id": workflow_id,
                "config": workflow_config,
                "message": f"Created workflow: {workflow_config.get('name', 'Untitled')}"
            }
        else:
            return {
                "success": False,
                "error": "Could not parse workflow configuration from AI response",
                "ai_response": response["message"]
            }

    except json.JSONDecodeError as e:
        return {
            "success": False,
            "error": f"Invalid JSON in AI response: {e}",
            "ai_response": response["message"]
        }

# Usage example
async def demo_nlp_workflow_creation():
    """Demo natural language workflow creation."""

    session_id = await agent_ui.create_session("nlp_demo_user")

    descriptions = [
        "Read a CSV file of sales data, calculate monthly totals, and generate a summary report",
        "Process customer feedback text, analyze sentiment, and store results in a database",
        "Call a weather API, process the data, and send notifications if temperature exceeds 30°C"
    ]

    for desc in descriptions:
        print(f"\\nProcessing: {desc}")

        result = await create_workflow_from_description(session_id, desc)

        if result["success"]:
            print(f"✅ Created workflow: {result['workflow_id']}")
            print(f"   Workflow name: {result['config']['name']}")
            print(f"   Nodes: {len(result['config']['nodes'])}")
        else:
            print(f"❌ Failed: {result['error']}")
```

## Database Integration

### Persistent Workflow Storage

Enable database persistence for workflows and executions:

```python
# Configure middleware with database persistence
middleware_with_db = AgentUIMiddleware(
    enable_dynamic_workflows=True,
    max_sessions=1000,
    session_timeout_minutes=60,
    enable_persistence=True,
    database_url="postgresql://user:password@localhost/kailash_app"
)

# Database configuration
DATABASE_CONFIG = {
    "host": "localhost",
    "port": 5432,
    "database": "kailash_app",
    "user": "kailash_user",
    "password": "secure_password"
}

async def setup_database_tables():
    """Set up database tables for middleware persistence."""

    from kailash.middleware.database import MiddlewareDatabaseManager

    db_manager = MiddlewareDatabaseManager(
        f"postgresql://{DATABASE_CONFIG['user']}:{DATABASE_CONFIG['password']}@"
        f"{DATABASE_CONFIG['host']}:{DATABASE_CONFIG['port']}/{DATABASE_CONFIG['database']}"
    )

    # Create tables
    await db_manager.create_tables()
    print("Database tables created successfully")

# Workflow persistence example
async def create_and_persist_workflow():
    """Create workflow with automatic persistence."""

    session_id = await middleware_with_db.create_session("persistent_user")

    workflow_config = {
        "name": "persistent_data_pipeline",
        "description": "A workflow that will be saved to database",
        "nodes": [
            {
                "id": "data_source",
                "type": "CSVReaderNode",
                "config": {
                    "name": "data_source",
                    "file_path": "/data/persistent_data.csv"
                }
            },
            {
                "id": "data_processor",
                "type": "PythonCodeNode",
                "config": {
                    "name": "data_processor",
                    "code": "result = {'processed': True, 'row_count': len(data)}"
                }
            }
        ],
        "connections": [
            {
                "from_node": "data_source",
                "from_output": "data",
                "to_node": "data_processor",
                "to_input": "data"
            }
        ]
    }

    # Create workflow (automatically persisted)
    workflow_id = await middleware_with_db.create_dynamic_workflow(
        session_id, workflow_config
    )

    # Execute workflow (execution history persisted)
    execution_id = await middleware_with_db.execute_workflow(
        session_id, workflow_id, inputs={}
    )

    print(f"Created persistent workflow: {workflow_id}")
    print(f"Started execution: {execution_id}")

    return workflow_id, execution_id

# Query execution history
async def get_execution_history(user_id: str, limit: int = 10):
    """Get execution history for a user."""

    # Access middleware repository directly
    if middleware_with_db.enable_persistence:
        execution_repo = middleware_with_db.execution_repo

        # Query executions for user
        executions = await execution_repo.get_user_executions(
            user_id=user_id,
            limit=limit
        )

        return [
            {
                "execution_id": exec["id"],
                "workflow_id": exec["workflow_id"],
                "status": exec["status"],
                "created_at": exec["created_at"],
                "outputs": exec.get("outputs", {})
            }
            for exec in executions
        ]

    return []
```

## Security Integration

### Authentication and Authorization

Integrate JWT authentication and access control:

```python
from kailash.middleware.auth import KailashJWTAuthManager, MiddlewareAccessControlManager
from kailash.nodes.security import AccessControlManager

# Set up authentication
jwt_auth = KailashJWTAuthManager(
    secret_key="your-super-secret-jwt-key",
    algorithm="HS256",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7
)

# Set up access control
access_control = MiddlewareAccessControlManager(
    strategy="hybrid",  # RBAC + ABAC
    default_permissions=["workflow:read"]
)

async def authenticate_user(username: str, password: str):
    """Authenticate user and create JWT token."""

    # Verify credentials (integrate with your user system)
    user_data = await verify_user_credentials(username, password)

    if user_data:
        # Create JWT token
        token_data = {
            "user_id": user_data["id"],
            "username": user_data["username"],
            "roles": user_data.get("roles", ["user"]),
            "permissions": user_data.get("permissions", [])
        }

        access_token = await jwt_auth.create_access_token(token_data)
        refresh_token = await jwt_auth.create_refresh_token(token_data)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user_data": user_data
        }

    return None

async def secure_session_creation(user_token: str):
    """Create session with authentication and authorization."""

    # Verify JWT token
    token_data = await jwt_auth.verify_token(user_token)

    if not token_data:
        raise ValueError("Invalid or expired token")

    # Check permission for session creation
    can_create_session = await access_control.check_permission(
        user_id=token_data["user_id"],
        resource="session:create",
        context={"roles": token_data.get("roles", [])}
    )

    if not can_create_session:
        raise ValueError("Insufficient permissions to create session")

    # Create authenticated session
    session_id = await agent_ui.create_session(
        user_id=token_data["user_id"],
        metadata={
            "username": token_data["username"],
            "roles": token_data.get("roles", []),
            "permissions": token_data.get("permissions", []),
            "authenticated": True,
            "auth_method": "jwt"
        }
    )

    return session_id

async def secure_workflow_execution(session_id: str, workflow_config: dict, user_token: str):
    """Execute workflow with security checks."""

    # Verify token
    token_data = await jwt_auth.verify_token(user_token)

    if not token_data:
        raise ValueError("Invalid or expired token")

    # Get session and verify ownership
    session = await agent_ui.get_session(session_id)

    if not session or session.user_id != token_data["user_id"]:
        raise ValueError("Session not found or access denied")

    # Check workflow execution permission
    can_execute = await access_control.check_permission(
        user_id=token_data["user_id"],
        resource="workflow:execute",
        context={
            "roles": token_data.get("roles", []),
            "workflow_type": workflow_config.get("name", "unknown")
        }
    )

    if not can_execute:
        raise ValueError("Insufficient permissions to execute workflows")

    # Create and execute workflow
    workflow_id = await agent_ui.create_dynamic_workflow(
        session_id, workflow_config
    )

    execution_id = await agent_ui.execute_workflow(
        session_id, workflow_id, inputs={}
    )

    # Log security event
    from kailash.nodes.security import SecurityEventNode

    security_event = SecurityEventNode(name="workflow_execution_audit")
    await security_event.run(
        event_type="workflow_executed",
        severity="info",
        user_id=token_data["user_id"],
        resource_id=workflow_id,
        metadata={
            "session_id": session_id,
            "execution_id": execution_id,
            "workflow_name": workflow_config.get("name", "unknown")
        }
    )

    return execution_id

async def verify_user_credentials(username: str, password: str):
    """Verify user credentials against your user system."""
    # Implement your user authentication logic here
    # This is a placeholder implementation

    # Example: database lookup, LDAP check, etc.
    if username == "demo" and password == "password":
        return {
            "id": "user_123",
            "username": "demo",
            "email": "demo@example.com",
            "roles": ["user", "developer"],
            "permissions": ["workflow:read", "workflow:execute", "session:create"]
        }

    return None
```

## Error Handling and Monitoring

### Comprehensive Error Handling

Implement robust error handling across the middleware stack:

```python
import logging
from typing import Optional, Dict, Any
from kailash.sdk_exceptions import (
    NodeConfigurationError,
    WorkflowValidationError,
    RuntimeExecutionError
)

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

class MiddlewareErrorHandler:
    """Centralized error handling for middleware operations."""

    @staticmethod
    async def handle_session_error(error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle session-related errors."""

        error_response = {
            "error_type": type(error).__name__,
            "message": str(error),
            "context": context,
            "timestamp": datetime.utcnow().isoformat()
        }

        if isinstance(error, ValueError):
            # Session not found or invalid parameters
            error_response["status_code"] = 404
            error_response["user_message"] = "Session not found or invalid"

        elif isinstance(error, PermissionError):
            # Access denied
            error_response["status_code"] = 403
            error_response["user_message"] = "Access denied"

        else:
            # Unexpected error
            error_response["status_code"] = 500
            error_response["user_message"] = "Internal server error"
            logger.error(f"Unexpected session error: {error}", exc_info=True)

        return error_response

    @staticmethod
    async def handle_workflow_error(error: Exception, context: Dict[str, Any]) -> Dict[str, Any]:
        """Handle workflow-related errors."""

        error_response = {
            "error_type": type(error).__name__,
            "message": str(error),
            "context": context,
            "timestamp": datetime.utcnow().isoformat()
        }

        if isinstance(error, NodeConfigurationError):
            # Invalid node configuration
            error_response["status_code"] = 400
            error_response["user_message"] = "Invalid workflow configuration"
            error_response["suggestions"] = [
                "Check node parameters and types",
                "Verify all required fields are provided",
                "Ensure node connections are valid"
            ]

        elif isinstance(error, WorkflowValidationError):
            # Workflow validation failed
            error_response["status_code"] = 400
            error_response["user_message"] = "Workflow validation failed"
            error_response["suggestions"] = [
                "Check workflow structure",
                "Verify node connections",
                "Ensure all required inputs are connected"
            ]

        elif isinstance(error, RuntimeExecutionError):
            # Runtime execution failed
            error_response["status_code"] = 500
            error_response["user_message"] = "Workflow execution failed"
            error_response["suggestions"] = [
                "Check workflow inputs",
                "Verify data formats",
                "Review node configurations"
            ]

        else:
            # Unexpected error
            error_response["status_code"] = 500
            error_response["user_message"] = "Workflow operation failed"
            logger.error(f"Unexpected workflow error: {error}", exc_info=True)

        return error_response

# Usage in middleware operations
async def safe_session_creation(user_id: str, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
    """Create session with comprehensive error handling."""

    try:
        session_id = await agent_ui.create_session(
            user_id=user_id,
            metadata=metadata
        )

        return {
            "success": True,
            "session_id": session_id,
            "message": "Session created successfully"
        }

    except Exception as error:
        error_response = await MiddlewareErrorHandler.handle_session_error(
            error,
            context={
                "operation": "create_session",
                "user_id": user_id,
                "metadata": metadata
            }
        )

        return {
            "success": False,
            **error_response
        }

async def safe_workflow_execution(
    session_id: str,
    workflow_config: Dict[str, Any],
    inputs: Dict[str, Any] = None
) -> Dict[str, Any]:
    """Execute workflow with comprehensive error handling."""

    execution_context = {
        "operation": "execute_workflow",
        "session_id": session_id,
        "workflow_name": workflow_config.get("name", "unknown"),
        "node_count": len(workflow_config.get("nodes", []))
    }

    try:
        # Create workflow
        workflow_id = await agent_ui.create_dynamic_workflow(
            session_id=session_id,
            workflow_config=workflow_config
        )

        execution_context["workflow_id"] = workflow_id

        # Execute workflow
        execution_id = await agent_ui.execute_workflow(
            session_id=session_id,
            workflow_id=workflow_id,
            inputs=inputs or {}
        )

        return {
            "success": True,
            "workflow_id": workflow_id,
            "execution_id": execution_id,
            "message": "Workflow execution started successfully"
        }

    except Exception as error:
        error_response = await MiddlewareErrorHandler.handle_workflow_error(
            error,
            context=execution_context
        )

        return {
            "success": False,
            **error_response
        }
```

### Health Monitoring

Implement health checks and monitoring:

```python
from dataclasses import dataclass
from typing import List
import psutil
import time

@dataclass
class HealthCheck:
    name: str
    status: str  # "healthy", "warning", "critical"
    message: str
    details: Dict[str, Any] = None

class MiddlewareHealthMonitor:
    """Health monitoring for middleware components."""

    def __init__(self, agent_ui: AgentUIMiddleware):
        self.agent_ui = agent_ui
        self.start_time = time.time()

    async def get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""

        checks = [
            await self._check_middleware_health(),
            await self._check_database_health(),
            await self._check_system_resources(),
            await self._check_session_health()
        ]

        # Determine overall status
        if any(check.status == "critical" for check in checks):
            overall_status = "critical"
        elif any(check.status == "warning" for check in checks):
            overall_status = "warning"
        else:
            overall_status = "healthy"

        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": time.time() - self.start_time,
            "checks": [
                {
                    "name": check.name,
                    "status": check.status,
                    "message": check.message,
                    "details": check.details
                }
                for check in checks
            ]
        }

    async def _check_middleware_health(self) -> HealthCheck:
        """Check middleware component health."""

        try:
            stats = self.agent_ui.get_stats()

            active_sessions = stats["active_sessions"]
            max_sessions = self.agent_ui.max_sessions
            session_usage = active_sessions / max_sessions

            if session_usage > 0.9:
                status = "critical"
                message = f"Session usage critical: {session_usage:.1%}"
            elif session_usage > 0.7:
                status = "warning"
                message = f"Session usage high: {session_usage:.1%}"
            else:
                status = "healthy"
                message = f"Middleware healthy: {active_sessions}/{max_sessions} sessions"

            return HealthCheck(
                name="middleware",
                status=status,
                message=message,
                details=stats
            )

        except Exception as e:
            return HealthCheck(
                name="middleware",
                status="critical",
                message=f"Middleware check failed: {e}"
            )

    async def _check_database_health(self) -> HealthCheck:
        """Check database connectivity and performance."""

        if not self.agent_ui.enable_persistence:
            return HealthCheck(
                name="database",
                status="healthy",
                message="Database persistence disabled"
            )

        try:
            # Test database connection
            start_time = time.time()

            # Simple connectivity test
            db_node = self.agent_ui.workflow_repo.db_node
            result = await db_node.execute_async(
                query="SELECT 1 as test",
                parameters={}
            )

            response_time = (time.time() - start_time) * 1000  # ms

            if response_time > 1000:  # 1 second
                status = "warning"
                message = f"Database slow: {response_time:.1f}ms"
            else:
                status = "healthy"
                message = f"Database healthy: {response_time:.1f}ms"

            return HealthCheck(
                name="database",
                status=status,
                message=message,
                details={"response_time_ms": response_time}
            )

        except Exception as e:
            return HealthCheck(
                name="database",
                status="critical",
                message=f"Database connection failed: {e}"
            )

    async def _check_system_resources(self) -> HealthCheck:
        """Check system resource usage."""

        try:
            # CPU usage
            cpu_percent = psutil.cpu_percent(interval=1)

            # Memory usage
            memory = psutil.virtual_memory()
            memory_percent = memory.percent

            # Disk usage
            disk = psutil.disk_usage('/')
            disk_percent = disk.percent

            # Determine status based on resource usage
            if cpu_percent > 90 or memory_percent > 90 or disk_percent > 90:
                status = "critical"
                message = "System resources critical"
            elif cpu_percent > 70 or memory_percent > 70 or disk_percent > 80:
                status = "warning"
                message = "System resources high"
            else:
                status = "healthy"
                message = "System resources normal"

            return HealthCheck(
                name="system_resources",
                status=status,
                message=message,
                details={
                    "cpu_percent": cpu_percent,
                    "memory_percent": memory_percent,
                    "disk_percent": disk_percent,
                    "memory_available_gb": memory.available / (1024**3)
                }
            )

        except Exception as e:
            return HealthCheck(
                name="system_resources",
                status="warning",
                message=f"Resource check failed: {e}"
            )

    async def _check_session_health(self) -> HealthCheck:
        """Check session health and cleanup status."""

        try:
            current_time = datetime.utcnow()
            timeout_minutes = self.agent_ui.session_timeout_minutes

            # Count sessions by age
            sessions_by_age = {
                "active": 0,
                "near_timeout": 0,
                "stale": 0
            }

            for session in self.agent_ui.sessions.values():
                age_minutes = (current_time - session.created_at).total_seconds() / 60

                if age_minutes > timeout_minutes:
                    sessions_by_age["stale"] += 1
                elif age_minutes > timeout_minutes * 0.8:
                    sessions_by_age["near_timeout"] += 1
                else:
                    sessions_by_age["active"] += 1

            # Determine status
            if sessions_by_age["stale"] > 0:
                status = "warning"
                message = f"{sessions_by_age['stale']} stale sessions need cleanup"
            else:
                status = "healthy"
                message = f"Session health good: {sessions_by_age['active']} active"

            return HealthCheck(
                name="sessions",
                status=status,
                message=message,
                details=sessions_by_age
            )

        except Exception as e:
            return HealthCheck(
                name="sessions",
                status="warning",
                message=f"Session check failed: {e}"
            )

# Usage
health_monitor = MiddlewareHealthMonitor(agent_ui)

# FastAPI health endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return await health_monitor.get_health_status()

# Detailed health endpoint
@app.get("/health/detailed")
async def detailed_health():
    """Detailed health information."""
    health_status = await health_monitor.get_health_status()

    # Add additional system information
    health_status["system_info"] = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "architecture": platform.architecture()[0],
        "processor": platform.processor()
    }

    return health_status
```

## Production Deployment

### Configuration Management

Set up environment-based configuration:

```python
# config.py
from pydantic import BaseSettings, Field
from typing import List, Optional

class MiddlewareConfig(BaseSettings):
    """Middleware configuration with environment variable support."""

    # Core settings
    debug: bool = Field(False, env="DEBUG")
    log_level: str = Field("INFO", env="LOG_LEVEL")

    # Database settings
    database_url: str = Field(..., env="DATABASE_URL")
    enable_persistence: bool = Field(True, env="ENABLE_PERSISTENCE")

    # Session settings
    max_sessions: int = Field(1000, env="MAX_SESSIONS")
    session_timeout_minutes: int = Field(60, env="SESSION_TIMEOUT_MINUTES")

    # Authentication settings
    jwt_secret_key: str = Field(..., env="JWT_SECRET_KEY")
    jwt_algorithm: str = Field("HS256", env="JWT_ALGORITHM")
    access_token_expire_minutes: int = Field(30, env="ACCESS_TOKEN_EXPIRE_MINUTES")

    # API settings
    api_title: str = Field("Kailash Middleware API", env="API_TITLE")
    api_version: str = Field("1.0.0", env="API_VERSION")
    cors_origins: List[str] = Field(["*"], env="CORS_ORIGINS")
    enable_docs: bool = Field(True, env="ENABLE_DOCS")

    # Real-time settings
    websocket_heartbeat_interval: int = Field(30, env="WEBSOCKET_HEARTBEAT_INTERVAL")
    sse_retry_timeout: int = Field(5000, env="SSE_RETRY_TIMEOUT")

    # AI Chat settings
    default_llm_provider: str = Field("ollama", env="DEFAULT_LLM_PROVIDER")
    default_llm_model: str = Field("llama3.2:3b", env="DEFAULT_LLM_MODEL")
    enable_vector_search: bool = Field(False, env="ENABLE_VECTOR_SEARCH")
    vector_database_url: Optional[str] = Field(None, env="VECTOR_DATABASE_URL")

    # Performance settings
    max_concurrent_executions: int = Field(50, env="MAX_CONCURRENT_EXECUTIONS")
    event_batch_size: int = Field(100, env="EVENT_BATCH_SIZE")
    event_batch_timeout: float = Field(1.0, env="EVENT_BATCH_TIMEOUT")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Production application factory
async def create_production_app(config: MiddlewareConfig = None):
    """Create production-ready middleware application."""

    if config is None:
        config = MiddlewareConfig()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create middleware with production settings
    agent_ui = AgentUIMiddleware(
        enable_dynamic_workflows=True,
        max_sessions=config.max_sessions,
        session_timeout_minutes=config.session_timeout_minutes,
        enable_workflow_sharing=True,
        enable_persistence=config.enable_persistence,
        database_url=config.database_url
    )

    # Create real-time middleware
    realtime = RealtimeMiddleware(
        agent_ui,
        websocket_heartbeat_interval=config.websocket_heartbeat_interval,
        sse_retry_timeout=config.sse_retry_timeout
    )

    # Create AI chat if enabled
    ai_chat = None
    if config.enable_vector_search and config.vector_database_url:
        ai_chat = AIChatMiddleware(
            agent_ui,
            enable_vector_search=True,
            vector_database_url=config.vector_database_url,
            default_model_provider=config.default_llm_provider,
            default_model=config.default_llm_model
        )

    # Create API gateway
    gateway = create_gateway(
        title=config.api_title,
        version=config.api_version,
        cors_origins=config.cors_origins,
        enable_docs=config.enable_docs
    )

    # Connect components
    gateway.agent_ui = agent_ui
    gateway.realtime = realtime
    if ai_chat:
        gateway.ai_chat = ai_chat

    # Set up authentication
    from kailash.middleware.auth import KailashJWTAuthManager

    jwt_auth = KailashJWTAuthManager(
        secret_key=config.jwt_secret_key,
        algorithm=config.jwt_algorithm,
        access_token_expire_minutes=config.access_token_expire_minutes
    )

    gateway.auth = jwt_auth

    return gateway, agent_ui, realtime, ai_chat

# Production startup
async def startup_production():
    """Production startup sequence."""

    config = MiddlewareConfig()

    # Create application
    gateway, agent_ui, realtime, ai_chat = await create_production_app(config)

    # Health monitoring
    health_monitor = MiddlewareHealthMonitor(agent_ui)

    # Log startup information
    logger.info(f"Starting {config.api_title} v{config.api_version}")
    logger.info(f"Max sessions: {config.max_sessions}")
    logger.info(f"Database persistence: {config.enable_persistence}")
    logger.info(f"Vector search: {config.enable_vector_search}")
    logger.info(f"Debug mode: {config.debug}")

    return gateway

# Run production server
if __name__ == "__main__":
    import uvicorn

    config = MiddlewareConfig()

    uvicorn.run(
        "main:startup_production",
        host="0.0.0.0",
        port=8000,
        workers=4 if not config.debug else 1,
        reload=config.debug,
        access_log=config.debug,
        log_level=config.log_level.lower()
    )
```

## MCP Server Integration

### Registering MCP Servers with Gateway

The gateway supports MCP (Model Context Protocol) server integration for external tool access:

```python
from kailash.api.mcp_integration import MCPIntegration

# Create MCP integration
mcp = MCPIntegration("tools_server", "External tools and utilities")

# Add async tools
async def web_search(query: str, max_results: int = 10):
    """Search the web for information."""
    results = await search_api.search(query, limit=max_results)
    return {"results": results}

async def analyze_text(text: str, analysis_type: str = "sentiment"):
    """Analyze text using AI."""
    result = await ai_service.analyze(text, type=analysis_type)
    return {"analysis": result}

# Register tools with schemas
mcp.add_tool("search", web_search, "Search the web", {
    "query": {"type": "string", "required": True},
    "max_results": {"type": "integer", "default": 10}
})

mcp.add_tool("analyze", analyze_text, "Analyze text", {
    "text": {"type": "string", "required": True},
    "analysis_type": {"type": "string", "default": "sentiment"}
})

# For WorkflowAPIGateway
gateway.register_mcp_server("tools", mcp)

# For create_gateway() - use middleware MCP
from kailash.middleware.mcp import MiddlewareMCPServer, MCPServerConfig

config = MCPServerConfig()
config.name = "tools"
config.enable_caching = True

mcp_server = MiddlewareMCPServer(
    config=config,
    agent_ui=gateway.agent_ui
)

# Register same tools
mcp_server.register_tool("search", web_search, "Search the web", {...})
```

### Using MCP Tools in Workflows

Once registered, use MCP tools in workflows via MCPToolNode:

```python
from kailash.api.mcp_integration import MCPToolNode
from kailash.workflow.builder import WorkflowBuilder

# Create workflow using MCP tools
builder = WorkflowBuilder("mcp_analysis_workflow")

# Add search node
search_node = MCPToolNode(
    mcp_server="tools",
    tool_name="search",
    parameter_mapping={
        "search_term": "query"  # Map workflow input to tool param
    }
)
builder.add_node("search", search_node)

# Add analysis node
analyze_node = MCPToolNode(
    mcp_server="tools",
    tool_name="analyze"
)
builder.add_node("analyze", analyze_node)

# Connect nodes - search results feed to analyzer
builder.add_connection("search", "results", "analyze", "text")

# Register workflow
await gateway.agent_ui.register_workflow(
    "mcp_analysis",
    builder.build(),
    make_shared=True
)

# Execute via API
execution_id = await gateway.agent_ui.execute_workflow(
    session_id=session_id,
    workflow_id="mcp_analysis",
    inputs={"search_term": "Kailash SDK middleware"}
)
```

### Complete MCP Integration Example

```python
async def create_mcp_enabled_gateway():
    """Create gateway with comprehensive MCP integration."""
    
    # 1. Create gateway
    gateway = create_gateway(
        title="MCP-Enabled Application",
        cors_origins=["http://localhost:3000"],
        enable_docs=True
    )
    
    # 2. Create MCP server with multiple tool categories
    mcp = MCPIntegration("enterprise_tools")
    
    # Data tools
    async def query_database(query: str, database: str = "main"):
        # Database query tool
        return {"results": await db.query(query, database)}
    
    # AI tools
    async def generate_content(prompt: str, style: str = "professional"):
        llm_node = LLMAgentNode("generator", model="gpt-4")
        result = await llm_node.async_run(
            prompt=f"Generate {style} content: {prompt}"
        )
        return {"content": result["response"]}
    
    # External API tools
    async def call_api(endpoint: str, method: str = "GET", data: dict = None):
        http_node = HTTPRequestNode(name="api_caller")
        result = await http_node.execute({
            "url": endpoint,
            "method": method,
            "json": data
        })
        return result
    
    # Register all tools
    mcp.add_tool("query_db", query_database, "Query database", {
        "query": {"type": "string", "required": True},
        "database": {"type": "string", "default": "main"}
    })
    
    mcp.add_tool("generate", generate_content, "Generate content", {
        "prompt": {"type": "string", "required": True},
        "style": {"type": "string", "default": "professional"}
    })
    
    mcp.add_tool("api_call", call_api, "Call external API", {
        "endpoint": {"type": "string", "required": True},
        "method": {"type": "string", "default": "GET"},
        "data": {"type": "object", "required": False}
    })
    
    # 3. Create workflow template using MCP tools
    template_config = {
        "name": "data_enrichment_pipeline",
        "description": "Query data, enrich with AI, and call APIs",
        "nodes": [
            {
                "id": "query",
                "type": "MCPToolNode",
                "config": {
                    "mcp_server": "enterprise_tools",
                    "tool_name": "query_db"
                }
            },
            {
                "id": "enrich",
                "type": "MCPToolNode",
                "config": {
                    "mcp_server": "enterprise_tools",
                    "tool_name": "generate"
                }
            },
            {
                "id": "notify",
                "type": "MCPToolNode",
                "config": {
                    "mcp_server": "enterprise_tools",
                    "tool_name": "api_call"
                }
            }
        ],
        "connections": [
            {"from_node": "query", "from_output": "results", 
             "to_node": "enrich", "to_input": "prompt"},
            {"from_node": "enrich", "from_output": "content", 
             "to_node": "notify", "to_input": "data"}
        ]
    }
    
    # Register as shared workflow
    workflow_id = await gateway.agent_ui.create_dynamic_workflow(
        session_id=None,  # Shared workflow
        workflow_config=template_config,
        workflow_id="data_enrichment_template"
    )
    
    return gateway

# Run the MCP-enabled gateway
if __name__ == "__main__":
    gateway = asyncio.run(create_mcp_enabled_gateway())
    gateway.run(port=8000)
```

For more detailed MCP integration patterns, see [19-mcp-gateway-integration.md](19-mcp-gateway-integration.md).

## Summary

This guide provides comprehensive patterns for integrating Kailash Middleware into production applications. Key takeaways:

### Core Benefits
- **Enterprise-Ready**: 17/17 integration tests passing for production reliability
- **Real-time Communication**: WebSocket, SSE, and webhook support
- **Dynamic Workflows**: Runtime workflow creation from frontend configurations
- **Comprehensive Security**: JWT authentication, RBAC/ABAC access control
- **Database Integration**: Persistent storage with audit trails
- **AI Integration**: Natural language workflow creation and chat interfaces
- **MCP Integration**: External tool access through unified interface

### Best Practices
1. **Use SDK Components**: Leverage authentic SDK nodes for all operations
2. **Error Handling**: Implement comprehensive error handling with user-friendly messages
3. **Security First**: Always validate permissions and authenticate requests
4. **Monitor Health**: Implement health checks and performance monitoring
5. **Configure for Environment**: Use environment-based configuration for deployment
6. **MCP Tools**: Register external tools as MCP servers for workflow integration

### Next Steps
- Review the [MCP Gateway Integration Guide](19-mcp-gateway-integration.md) for detailed MCP patterns
- Review the [Middleware Architecture Documentation](../../# contrib (removed)/architecture/middleware-architecture.md)
- Explore production deployment patterns in [Production Deployment Guide](../deployment/)
- Check out complete examples in [examples/feature_examples/middleware/](../../examples/feature_examples/middleware/)

The middleware provides a solid foundation for building production applications with the Kailash SDK. With proper configuration and monitoring, it can handle enterprise-scale workloads with confidence.
