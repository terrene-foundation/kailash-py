# DataFlow + Gateway Integration

Create production-ready REST APIs from DataFlow models using the Kailash Gateway.

## Overview

The DataFlow + Gateway integration provides:
- **Automatic REST API Generation**: CRUD endpoints for all models
- **OpenAPI Documentation**: Auto-generated API specs
- **Authentication & Authorization**: Built-in security
- **Rate Limiting**: Protect your APIs
- **Request Validation**: Automatic input validation
- **Response Transformation**: Consistent API responses

## Quick Start

### Basic Gateway Setup

```python
from kailash.workflow.builder import WorkflowBuilder
from dataflow import DataFlow
from kailash.servers.gateway import create_gateway

# Initialize DataFlow
db = DataFlow()

@db.model
class User:
    name: str
    email: str
    role: str = "user"
    active: bool = True

@db.model
class Post:
    title: str
    content: str
    author_id: int
    published: bool = False

# Create Gateway with DataFlow
gateway = create_gateway(
    title="Blog API",
    server_type="enterprise",
    dataflow_integration=db,
    auto_generate_endpoints=True  # Creates CRUD endpoints
)

# Start the API server
# uvicorn main:gateway --reload
```

This automatically creates:
```
GET    /api/users          # List users
POST   /api/users          # Create user
GET    /api/users/{id}     # Get user
PUT    /api/users/{id}     # Update user
DELETE /api/users/{id}     # Delete user

GET    /api/posts          # List posts
POST   /api/posts          # Create post
GET    /api/posts/{id}     # Get post
PUT    /api/posts/{id}     # Update post
DELETE /api/posts/{id}     # Delete post
```

## Advanced Configuration

### Customizing Generated Endpoints

```python
gateway = create_gateway(
    title="Advanced Blog API",
    server_type="enterprise",
    dataflow_integration=db,

    # Endpoint configuration
    endpoint_config={
        "prefix": "/api/v1",
        "plural_names": True,  # /users instead of /user
        "include_bulk": True,  # Bulk operations
        "include_aggregate": True,  # Aggregation endpoints

        # Model-specific settings
        "models": {
            "User": {
                "exclude_endpoints": ["delete"],  # No user deletion
                "read_only_fields": ["created_at", "updated_at"],
                "required_fields": ["name", "email"],
                "searchable_fields": ["name", "email"],
                "sortable_fields": ["name", "created_at"],
                "default_limit": 20,
                "max_limit": 100
            },
            "Post": {
                "auth_required": {
                    "create": True,
                    "update": True,
                    "delete": True
                },
                "owner_field": "author_id",  # For ownership checks
                "filterable_fields": ["published", "author_id"],
                "expand_fields": ["author"]  # Join with User
            }
        }
    }
)
```

### Authentication Integration

```python
from kailash.servers.auth import JWTAuth, APIKeyAuth

# JWT Authentication
jwt_auth = JWTAuth(
    secret_key="your-secret-key",
    algorithm="HS256",
    expire_minutes=60
)

# API Key Authentication
api_key_auth = APIKeyAuth(
    header_name="X-API-Key",
    query_param="api_key"
)

gateway = create_gateway(
    title="Secure Blog API",
    dataflow_integration=db,

    # Authentication configuration
    auth_config={
        "providers": [jwt_auth, api_key_auth],
        "default_provider": "jwt",

        # Endpoint-specific auth
        "public_endpoints": [
            "GET /api/posts",  # Public post listing
            "GET /api/posts/*"  # Public post reading
        ],

        # Role-based access
        "rbac": {
            "enabled": True,
            "roles": {
                "admin": ["*"],  # All permissions
                "editor": ["posts:*", "users:read"],
                "viewer": ["*:read"]
            }
        }
    }
)
```

## Request Handling

### Input Validation

```python
from pydantic import BaseModel, EmailStr, conint

# Define request schemas
class CreateUserRequest(BaseModel):
    name: str
    email: EmailStr
    age: conint(ge=18, le=120)
    role: str = "user"

class UpdatePostRequest(BaseModel):
    title: str = None
    content: str = None
    published: bool = None

# Apply schemas to endpoints
gateway = create_gateway(
    title="Validated API",
    dataflow_integration=db,

    validation_config={
        "models": {
            "User": {
                "create_schema": CreateUserRequest,
                "update_schema": "partial",  # Allow partial updates
                "validate_query_params": True
            },
            "Post": {
                "create_schema": {
                    "title": {"type": "string", "min_length": 5},
                    "content": {"type": "string", "min_length": 10}
                },
                "update_schema": UpdatePostRequest
            }
        },

        # Global validation settings
        "strict_mode": True,
        "coerce_types": True,
        "strip_unknown_fields": True
    }
)
```

### Query Parameter Handling

```python
# Advanced query parameters
GET /api/posts?published=true&author_id=123&sort=-created_at&limit=10&offset=20

# Search functionality
GET /api/posts?search=python&fields=title,content

# Date filtering
GET /api/posts?created_at__gte=2025-01-01&created_at__lt=2025-02-01

# Complex filters
GET /api/posts?filter={"$or":[{"published":true},{"author_id":123}]}
```

Configure query handling:

```python
gateway = create_gateway(
    title="Query-Enabled API",
    dataflow_integration=db,

    query_config={
        "enable_search": True,
        "search_fields": ["title", "content", "tags"],
        "search_mode": "fulltext",  # or "like", "regex"

        "enable_filtering": True,
        "filter_operators": ["eq", "ne", "gt", "gte", "lt", "lte", "in", "contains"],

        "enable_sorting": True,
        "default_sort": "-created_at",

        "enable_pagination": True,
        "default_page_size": 20,
        "max_page_size": 100,

        "enable_field_selection": True,
        "always_include_fields": ["id", "created_at"]
    }
)
```

## Response Transformation

### Consistent Response Format

```python
gateway = create_gateway(
    title="Consistent API",
    dataflow_integration=db,

    response_config={
        "envelope": True,  # Wrap responses
        "envelope_format": {
            "success": True,
            "data": None,
            "error": None,
            "meta": {}
        },

        # Pagination metadata
        "pagination_format": {
            "page": 1,
            "page_size": 20,
            "total_pages": 0,
            "total_items": 0,
            "has_next": False,
            "has_prev": False
        },

        # Field transformation
        "field_naming": "camelCase",  # or "snake_case"
        "exclude_null": True,
        "date_format": "iso8601",

        # Expansion
        "enable_expansion": True,
        "max_expansion_depth": 2
    }
)
```

### Custom Response Transformers

```python
from typing import Any, Dict

def transform_user_response(user: Dict[str, Any]) -> Dict[str, Any]:
    """Custom user response transformation."""
    return {
        "id": user["id"],
        "displayName": user["name"],
        "email": user["email"],
        "isActive": user["active"],
        "memberSince": user["created_at"],
        "role": user["role"].upper()
    }

gateway = create_gateway(
    title="Transformed API",
    dataflow_integration=db,

    transformers={
        "User": {
            "response": transform_user_response,
            "list_response": lambda users: {
                "users": [transform_user_response(u) for u in users],
                "count": len(users)
            }
        }
    }
)
```

## Rate Limiting

### Configure Rate Limits

```python
from kailash.servers.middleware import RateLimiter

gateway = create_gateway(
    title="Rate-Limited API",
    dataflow_integration=db,

    rate_limiting={
        "enabled": True,
        "backend": "redis",  # or "memory"

        # Global limits
        "default_limits": {
            "per_minute": 60,
            "per_hour": 1000,
            "per_day": 10000
        },

        # Endpoint-specific limits
        "endpoint_limits": {
            "POST /api/users": {
                "per_minute": 5,
                "per_hour": 20
            },
            "GET /api/posts": {
                "per_minute": 100,
                "per_hour": 5000
            }
        },

        # User tier limits
        "tier_limits": {
            "free": {"per_hour": 100},
            "basic": {"per_hour": 1000},
            "pro": {"per_hour": 10000},
            "enterprise": None  # Unlimited
        },

        # Headers
        "headers": {
            "limit": "X-RateLimit-Limit",
            "remaining": "X-RateLimit-Remaining",
            "reset": "X-RateLimit-Reset"
        }
    }
)
```

## Error Handling

### Consistent Error Responses

```python
gateway = create_gateway(
    title="Error-Handled API",
    dataflow_integration=db,

    error_config={
        "include_stack_trace": False,  # Production setting
        "include_error_code": True,
        "include_request_id": True,

        # Error format
        "error_format": {
            "error": {
                "code": None,
                "message": None,
                "details": {},
                "request_id": None,
                "timestamp": None
            }
        },

        # Custom error mappings
        "error_mappings": {
            "RecordNotFound": {"status": 404, "code": "NOT_FOUND"},
            "ValidationError": {"status": 400, "code": "VALIDATION_FAILED"},
            "UnauthorizedError": {"status": 401, "code": "UNAUTHORIZED"},
            "ForbiddenError": {"status": 403, "code": "FORBIDDEN"},
            "RateLimitError": {"status": 429, "code": "RATE_LIMITED"}
        }
    }
)
```

## Middleware Integration

### Custom Middleware

```python
from fastapi import Request
import time

async def timing_middleware(request: Request, call_next):
    """Add response time header."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

async def tenant_middleware(request: Request, call_next):
    """Extract tenant from subdomain."""
    host = request.headers.get("host", "")
    tenant = host.split(".")[0] if "." in host else "default"
    request.state.tenant_id = tenant
    return await call_next(request)

gateway = create_gateway(
    title="Middleware-Enhanced API",
    dataflow_integration=db,

    middleware=[
        timing_middleware,
        tenant_middleware
    ],

    # Built-in middleware configuration
    middleware_config={
        "cors": {
            "enabled": True,
            "origins": ["https://app.example.com"],
            "methods": ["GET", "POST", "PUT", "DELETE"],
            "headers": ["Content-Type", "Authorization"]
        },

        "compression": {
            "enabled": True,
            "minimum_size": 1000  # bytes
        },

        "request_id": {
            "enabled": True,
            "header_name": "X-Request-ID"
        }
    }
)
```

## API Documentation

### OpenAPI/Swagger Integration

```python
gateway = create_gateway(
    title="Well-Documented API",
    description="Complete API documentation with examples",
    version="1.0.0",
    dataflow_integration=db,

    docs_config={
        "enable_swagger": True,
        "swagger_url": "/docs",
        "enable_redoc": True,
        "redoc_url": "/redoc",

        # Schema customization
        "schema_config": {
            "include_examples": True,
            "include_schemas": True,
            "group_by_tags": True
        },

        # Custom documentation
        "custom_docs": {
            "authentication": """
            ## Authentication

            This API uses JWT tokens for authentication.

            ### Getting a Token
            ```
            POST /auth/token
            {
                "username": "user@example.com",
                "password": "secure_password"
            }
            ```

            ### Using the Token
            Include the token in the Authorization header:
            ```
            Authorization: Bearer <your-token>
            ```
            """,

            "rate_limiting": """
            ## Rate Limiting

            - Free tier: 100 requests/hour
            - Pro tier: 10,000 requests/hour

            Check headers for current limits.
            """
        }
    }
)
```

## WebSocket Support

### Real-time Updates via Gateway

```python
gateway = create_gateway(
    title="Real-time API",
    dataflow_integration=db,

    websocket_config={
        "enabled": True,
        "endpoint": "/ws",

        # Subscribe to model changes
        "subscriptions": {
            "enabled": True,
            "models": ["Post", "Comment"],
            "events": ["create", "update", "delete"]
        },

        # Authentication for WebSocket
        "auth_required": True,
        "auth_method": "query_param",  # ?token=xxx

        # Connection limits
        "max_connections": 1000,
        "max_subscriptions_per_connection": 10
    }
)

# WebSocket endpoint handler
@gateway.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    # Verify token
    user = await verify_token(token)
    if not user:
        await websocket.close(code=4001)
        return

    await websocket.accept()

    # Subscribe to changes
    async for message in websocket.iter_json():
        if message["action"] == "subscribe":
            await subscribe_to_model(
                websocket,
                model=message["model"],
                filters=message.get("filters")
            )
```

## Performance Optimization

### Caching Strategy

```python
from kailash.servers.cache import RedisCache

cache = RedisCache(url="redis://localhost")

gateway = create_gateway(
    title="Cached API",
    dataflow_integration=db,

    cache_config={
        "backend": cache,
        "enabled": True,

        # Cache strategies
        "strategies": {
            "User": {
                "get": {"ttl": 3600},  # 1 hour
                "list": {"ttl": 300}   # 5 minutes
            },
            "Post": {
                "get": {"ttl": 600},   # 10 minutes
                "list": {
                    "ttl": 60,
                    "vary_by": ["published", "author_id"]
                }
            }
        },

        # Cache headers
        "headers": {
            "cache_control": True,
            "etag": True,
            "last_modified": True
        },

        # Invalidation
        "invalidation": {
            "on_create": ["list"],
            "on_update": ["get", "list"],
            "on_delete": ["get", "list"]
        }
    }
)
```

## Monitoring & Metrics

### API Metrics Collection

```python
gateway = create_gateway(
    title="Monitored API",
    dataflow_integration=db,

    monitoring_config={
        "enabled": True,
        "backend": "prometheus",  # or "datadog", "newrelic"

        # Metrics to collect
        "metrics": {
            "request_count": True,
            "request_duration": True,
            "response_size": True,
            "error_rate": True,
            "database_queries": True
        },

        # Custom metrics
        "custom_metrics": {
            "active_users": "gauge",
            "posts_created": "counter",
            "api_revenue": "histogram"
        },

        # Endpoints
        "metrics_endpoint": "/metrics",
        "health_endpoint": "/health",
        "ready_endpoint": "/ready"
    }
)
```

## Testing Support

### Built-in Test Client

```python
from fastapi.testclient import TestClient

# Create test client
client = TestClient(gateway)

# Test user creation
response = client.post("/api/users", json={
    "name": "Test User",
    "email": "test@example.com"
})
assert response.status_code == 201
user = response.json()["data"]

# Test user listing
response = client.get("/api/users")
assert response.status_code == 200
users = response.json()["data"]
assert len(users) > 0

# Test with authentication
token = get_test_token()
response = client.get(
    "/api/posts",
    headers={"Authorization": f"Bearer {token}"}
)
assert response.status_code == 200
```

## Complete Example

### Production-Ready Blog API

```python
from dataflow import DataFlow
from kailash.servers.gateway import create_gateway
from kailash.servers.auth import JWTAuth
from kailash.servers.cache import RedisCache

# Initialize DataFlow with models
db = DataFlow("postgresql://localhost/blog")

@db.model
class User:
    username: str
    email: str
    password_hash: str
    role: str = "user"
    active: bool = True

    __dataflow__ = {
        'indexes': [
            {'fields': ['email'], 'unique': True},
            {'fields': ['username'], 'unique': True}
        ],
        'audit_log': True
    }

@db.model
class Post:
    title: str
    slug: str
    content: str
    author_id: int
    published: bool = False
    tags: list = []
    view_count: int = 0

    __dataflow__ = {
        'indexes': [
            {'fields': ['slug'], 'unique': True},
            {'fields': ['author_id', 'published']},
            {'fields': ['tags'], 'type': 'gin'}  # PostgreSQL
        ],
        'soft_delete': True,
        'versioned': True
    }

@db.model
class Comment:
    post_id: int
    author_id: int
    content: str
    approved: bool = False

    __dataflow__ = {
        'indexes': [
            {'fields': ['post_id', 'approved']},
            {'fields': ['author_id']}
        ],
        'audit_log': True
    }

# Create production gateway
gateway = create_gateway(
    title="Blog API",
    description="Production-ready blog API with authentication",
    version="2.0.0",
    server_type="enterprise",

    # DataFlow integration
    dataflow_integration=db,
    auto_generate_endpoints=True,

    # Endpoint customization
    endpoint_config={
        "prefix": "/api/v2",
        "models": {
            "User": {
                "exclude_fields": ["password_hash"],
                "auth_required": {
                    "list": ["admin"],
                    "create": ["admin"],
                    "update": ["admin", "self"],
                    "delete": ["admin"]
                }
            },
            "Post": {
                "searchable_fields": ["title", "content", "tags"],
                "owner_field": "author_id",
                "auth_required": {
                    "create": True,
                    "update": ["owner", "admin"],
                    "delete": ["owner", "admin"]
                },
                "custom_endpoints": {
                    "publish": {
                        "method": "POST",
                        "path": "/{id}/publish",
                        "auth": ["owner", "admin"]
                    },
                    "view": {
                        "method": "POST",
                        "path": "/{id}/view",
                        "auth": False
                    }
                }
            },
            "Comment": {
                "auth_required": {
                    "create": True,
                    "approve": ["admin", "moderator"]
                }
            }
        }
    },

    # Authentication
    auth_config={
        "provider": JWTAuth(
            secret_key="your-secret-key",
            expire_minutes=60
        ),
        "login_endpoint": "/auth/login",
        "refresh_endpoint": "/auth/refresh",
        "rbac": {
            "enabled": True,
            "roles": {
                "admin": ["*"],
                "moderator": ["posts:read", "posts:update", "comments:*"],
                "author": ["posts:*", "comments:create"],
                "user": ["posts:read", "comments:create"]
            }
        }
    },

    # Rate limiting
    rate_limiting={
        "enabled": True,
        "backend": "redis",
        "default_limits": {
            "per_minute": 60,
            "per_hour": 1000
        },
        "tier_limits": {
            "anonymous": {"per_hour": 100},
            "authenticated": {"per_hour": 1000},
            "pro": {"per_hour": 10000}
        }
    },

    # Caching
    cache_config={
        "backend": RedisCache(),
        "enabled": True,
        "strategies": {
            "Post": {
                "get": {"ttl": 600},
                "list": {"ttl": 60, "vary_by": ["published"]}
            }
        }
    },

    # Response handling
    response_config={
        "envelope": True,
        "pagination_format": "cursor",  # Better for large datasets
        "field_naming": "camelCase",
        "include_timestamps": True
    },

    # Monitoring
    monitoring_config={
        "enabled": True,
        "backend": "prometheus",
        "custom_metrics": {
            "post_views": "counter",
            "comment_approval_time": "histogram"
        }
    },

    # Documentation
    docs_config={
        "enable_swagger": True,
        "enable_redoc": True,
        "include_examples": True
    }
)

# Custom endpoints
@gateway.post("/api/v2/posts/{post_id}/publish")
async def publish_post(post_id: int, user=Depends(get_current_user)):
    """Publish a post (owner or admin only)."""
    workflow = WorkflowBuilder()

    # Check ownership
    workflow.add_node("PostReadNode", "post", {"id": post_id})
    workflow.add_node("AuthorizationNode", "auth", {
        "user_id": user.id,
        "resource": "$post",
        "action": "publish"
    })

    # Update post
    workflow.add_node("PostUpdateNode", "publish", {
        "id": post_id,
        "published": True,
        "published_at": datetime.now()
    })

    # Send notifications
    workflow.add_node("NotificationNode", "notify", {
        "event": "post_published",
        "post_id": post_id
    })

    return gateway.execute_workflow(workflow)

@gateway.post("/api/v2/posts/{post_id}/view")
async def record_view(post_id: int):
    """Record a post view."""
    workflow = WorkflowBuilder()

    workflow.add_node("PostUpdateNode", "increment", {
        "id": post_id,
        "view_count": {"$inc": 1}
    })

    # Analytics
    workflow.add_node("AnalyticsNode", "track", {
        "event": "post_view",
        "post_id": post_id,
        "timestamp": datetime.now()
    })

    return gateway.execute_workflow(workflow)

# Run with: uvicorn main:gateway --reload
```

## Deployment

### Production Configuration

```python
# config.py
import os

gateway = create_gateway(
    title="Production API",
    dataflow_integration=db,

    # Production settings
    production_config={
        "debug": False,
        "testing": False,

        # Performance
        "workers": os.cpu_count() * 2,
        "threads": 4,
        "connection_pool_size": 100,

        # Security
        "https_only": True,
        "hsts_enabled": True,
        "csp_enabled": True,

        # Logging
        "log_level": "INFO",
        "log_format": "json",
        "log_file": "/var/log/api/gateway.log",

        # Monitoring
        "apm_enabled": True,
        "apm_service_name": "blog-api",

        # Deployment
        "behind_proxy": True,
        "trusted_hosts": ["api.example.com"],
        "allowed_hosts": ["api.example.com", "www.example.com"]
    }
)
```

---

**Next**: See [Event-Driven Architecture](events.md) for event-based integration patterns.
