# Middleware Directory Structure

The middleware has been reorganized for better clarity and maintainability.

## Directory Organization

```
middleware/
├── __init__.py              # Main exports
├── auth/                    # Authentication & Authorization
│   ├── __init__.py
│   ├── auth_manager.py      # MiddlewareAuthManager (was SDKAuthManager)
│   ├── access_control.py    # MiddlewareAccessControlManager
│   ├── jwt_auth.py          # Legacy JWT implementation
│   └── kailash_jwt_auth.py  # KailashJWTAuthManager
│
├── core/                    # Core middleware components
│   ├── __init__.py
│   ├── agent_ui.py          # AgentUIMiddleware
│   ├── workflows.py         # MiddlewareWorkflows, WorkflowBasedMiddleware
│   └── schema.py            # NodeSchemaGenerator, DynamicSchemaRegistry
│
├── communication/           # External communication layer
│   ├── __init__.py
│   ├── events.py           # EventStream and event types
│   ├── realtime.py         # RealtimeMiddleware (WebSocket, SSE)
│   ├── api_gateway.py      # APIGateway for REST APIs
│   └── ai_chat.py          # AIChatMiddleware
│
├── database/               # Database persistence layer
│   ├── __init__.py
│   ├── models.py          # SQLAlchemy models
│   ├── repositories.py    # Repository pattern implementations
│   └── session_manager.py # Database session management
│
├── mcp/                   # Model Context Protocol integration
│   ├── __init__.py
│   ├── enhanced_server.py # MiddlewareMCPServer
│   └── client_integration.py # MiddlewareMCPClient
│
└── integrations/          # Future third-party integrations
    └── __init__.py
```

## Key Changes Made

1. **Removed Confusion**:
   - Deleted standalone `auth.py` file
   - Moved `SDKAuthManager` to `auth/auth_manager.py` as `MiddlewareAuthManager`
   - All auth-related code now in `auth/` directory

2. **Better Organization**:
   - `core/` - Central orchestration components
   - `communication/` - All external communication (REST, WebSocket, events)
   - Clear separation of concerns

3. **Consistent Naming**:
   - `SDKAuthManager` → `MiddlewareAuthManager`
   - All middleware classes now prefixed with "Middleware"
   - Consistent with existing patterns

4. **Fixed Imports**:
   - Updated relative imports throughout
   - Main `__init__.py` imports from subdirectories
   - No more circular dependencies

## Import Examples

```python
# From outside middleware
from kailash.middleware import (
    # Core
    AgentUIMiddleware,
    MiddlewareWorkflows,

    # Communication
    EventStream,
    APIGateway,
    RealtimeMiddleware,

    # Auth
    MiddlewareAuthManager,
    KailashJWTAuthManager,

    # Database
    MiddlewareWorkflowRepository
)

# From within middleware submodules
from ..core.agent_ui import AgentUIMiddleware
from ..auth import MiddlewareAuthManager
from ...nodes.enterprise import BatchProcessorNode
```

This structure provides:
- Clear organization
- No naming conflicts
- Easy navigation
- Consistent patterns
- Room for growth
