---
skill: codegen-decision-tree
description: Structured decision logic for codegen agents to select the right Kailash pattern
priority: HIGH
tags: [nexus, codegen, decision-tree, anti-patterns, templates, scaffolding]
---

# Codegen Decision Tree

Structured decision logic for codegen agents to select the right Kailash pattern. Every scaffolding task MUST start by traversing this tree.

**Version**: 0.12.0

---

## Master Decision Tree

```
START: What are you building?
|
+-- API endpoint that reads/writes data?
|   |
|   +-- Simple CRUD (single model)?
|   |   --> Pattern 1 (Handler) + Pattern 2 (DataFlow Model)
|   |   --> Template: SaaS API Backend
|   |
|   +-- Multi-model with relationships?
|   |   --> Pattern 3 (Nexus+DataFlow) + Pattern 5 (Multi-DataFlow if separate DBs)
|   |   --> Template: Multi-Tenant Enterprise
|   |
|   +-- Complex validation/transformation?
|   |   --> Pattern 8 (WorkflowBuilder) + Pattern 6 (Custom Node)
|   |   --> Use: Multi-step pipelines, approval workflows
|   |
|   +-- Requires authentication?
|       --> Pattern 4 (Auth Stack) + above patterns
|       --> Always add NexusAuthPlugin
|
+-- AI-powered feature?
|   |
|   +-- Single LLM call (Q&A, summarization)?
|   |   --> Pattern 1 (Handler) with direct Kaizen call inside
|   |   --> Simple: just call agent.run() in handler
|   |
|   +-- Multi-step agent (ReAct, tool use)?
|   |   --> Pattern 7 (Kaizen Agent) + Pattern 1 (Handler to expose)
|   |   --> Use BaseAgent with tools="all" for MCP tools
|   |
|   +-- RAG/semantic search?
|   |   --> Pattern 7 (Kaizen Agent) + Pattern 10 (MCP) + DataFlow pgvector
|   |   --> Combine: vector search + agent reasoning
|   |
|   +-- AI agent integration (Claude, GPT)?
|       --> Pattern 10 (MCP Integration)
|       --> Expose handlers as MCP tools
|
+-- Background/batch processing?
|   |
|   +-- Event-driven (webhooks, queues)?
|   |   --> Pattern 8 (WorkflowBuilder) + Pattern 9 (AsyncLocalRuntime)
|   |   --> Use: WebhookNode, QueueNode triggers
|   |
|   +-- Scheduled jobs (cron)?
|   |   --> Pattern 8 (WorkflowBuilder) + external scheduler
|   |   --> Call workflow from APScheduler or Celery
|   |
|   +-- Bulk data import?
|       --> Pattern 2 (DataFlow) with BulkCreateNode/BulkUpsertNode
|       --> Use batch_size parameter for memory efficiency
|
+-- Infrastructure/auth only?
    |
    +-- Authentication system?
    |   --> Pattern 4 (Auth Stack)
    |   --> NexusAuthPlugin handles JWT, RBAC, tenant isolation
    |
    +-- Custom middleware?
        --> app.add_middleware() + Starlette-compatible middleware
        --> See: 01-nexus-native-middleware spec
```

---

## Quick Pattern Selection

| Building...       | Primary Pattern        | Supporting Patterns   | Template            |
| ----------------- | ---------------------- | --------------------- | ------------------- |
| REST API with DB  | Handler + DataFlow     | Auth Stack            | SaaS API            |
| Multi-tenant SaaS | Handler + DataFlow     | Auth + Multi-DataFlow | Multi-Tenant        |
| AI chatbot        | Kaizen Agent + Handler | MCP Integration       | AI Agent            |
| ETL pipeline      | WorkflowBuilder        | Custom Node           | None (manual)       |
| Background job    | WorkflowBuilder        | AsyncLocalRuntime     | None (manual)       |
| Public API        | Handler                | (no auth)             | SaaS API (modified) |

---

## Anti-Patterns (What NOT to Do)

### Anti-Pattern 1: PythonCodeNode for Business Logic

**WRONG**:

```python
# DON'T: PythonCodeNode sandbox blocks imports
workflow.add_node("PythonCodeNode", "process", {
    "code": """
import asyncio  # BLOCKED!
import httpx    # BLOCKED!
from myapp.db import get_user  # BLOCKED!

result = await httpx.get("https://api.example.com")
"""
})
app.register("process", workflow.build())
```

**RIGHT**:

```python
# DO: Use @app.handler() for full Python access
@app.handler("process")
async def process(data: dict) -> dict:
    import asyncio
    import httpx
    from myapp.db import get_user

    async with httpx.AsyncClient() as client:
        response = await client.get("https://api.example.com")
    return {"result": response.json()}
```

**Why**: PythonCodeNode runs in a sandboxed environment that blocks most imports. Handlers run with full Python access.

---

### Anti-Pattern 2: Raw FastAPI Alongside Nexus

**WRONG**:

```python
# DON'T: Access private _gateway.app
app = Nexus()
fastapi_app = app._gateway.app  # Private attribute!

@fastapi_app.get("/users")  # Bypasses Nexus features
async def get_users():
    return {"users": []}
```

**RIGHT**:

```python
# DO: Use Nexus public APIs
app = Nexus()

# Option 1: Use handler (recommended)
@app.handler("get_users")
async def get_users() -> dict:
    return {"users": []}

# Option 2: Include existing router
from myapp.legacy import legacy_router
app.include_router(legacy_router, prefix="/legacy")

# Option 3: Custom endpoint (API-only)
@app.endpoint("/health", methods=["GET"])
async def health():
    return {"status": "ok"}
```

**Why**: Using `_gateway.app` bypasses Nexus middleware, auth, and breaks in future versions.

---

### Anti-Pattern 3: Building Auth from Scratch

**WRONG**:

```python
# DON'T: 200+ lines of custom JWT handling
from jose import jwt
import os

SECRET_KEY = os.environ["JWT_SECRET"]

async def verify_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    token = auth_header.split(" ")[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        request.state.user = payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    # ... 150 more lines for refresh, RBAC, tenant isolation
```

**RIGHT**:

```python
# DO: Use NexusAuthPlugin (CORRECT WS02 imports)
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig
import os

app = Nexus()
auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],     # CORRECT: 'secret', NOT 'secret_key'
        algorithm="HS256",
        exempt_paths=["/health"],             # CORRECT: 'exempt_paths'
    ),
    rbac={                                    # Plain dict, NOT RBACConfig
        "admin": ["*"],
        "member": ["contacts:read", "contacts:create"],
    },
    tenant_isolation=TenantConfig(            # TenantConfig object, NOT True
        jwt_claim="tenant_id",
        admin_role="admin",                   # CORRECT: singular string
    ),
)
app.add_plugin(auth)
```

**Why**: Auth is complex (refresh tokens, RBAC, tenant isolation). NexusAuthPlugin handles edge cases.

---

### Anti-Pattern 4: DataFlow Instance Per Request

**WRONG**:

```python
# DON'T: Create DataFlow per request
@app.handler("get_user")
async def get_user(user_id: str) -> dict:
    db = DataFlow("postgresql://...")  # New instance every request!
    # Connection pool exhausted after ~20 requests
```

**RIGHT**:

```python
# DO: Create at module level, reuse across requests
db = DataFlow(
    "postgresql://...",
    pool_size=20
)

@db.model
class User:
    id: str
    name: str

@app.handler("get_user")
async def get_user(user_id: str) -> dict:
    # Reuse module-level db instance
    workflow = WorkflowBuilder()
    workflow.add_node("UserReadNode", "read", {"id": user_id})
    # ...
```

**Why**: DataFlow manages connection pools. Creating per request exhausts connections.

---

### Anti-Pattern 5: WorkflowBuilder for Simple CRUD

**WRONG**:

```python
# DON'T: Unnecessary complexity for simple operations
def create_user(name: str, email: str):
    workflow = WorkflowBuilder()
    workflow.add_node("ValidateInputNode", "validate", {"name": name, "email": email})
    workflow.add_node("UserCreateNode", "create", {})
    workflow.add_connection("validate", "validated", "create", "data")
    # 20 lines for what should be 5
```

**RIGHT**:

```python
# DO: Use handler for simple operations
@app.handler("create_user")
async def create_user(name: str, email: str) -> dict:
    if not email or "@" not in email:
        return {"error": "Invalid email"}

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": f"user-{uuid.uuid4()}",
        "name": name,
        "email": email
    })
    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]
```

**Why**: WorkflowBuilder shines for multi-step orchestration. For simple CRUD, handlers are cleaner.

---

### Anti-Pattern 6: Mocking in Integration Tests

**WRONG**:

```python
# DON'T: Mock database in integration tests
@pytest.fixture
def mock_db():
    with patch("myapp.db.DataFlow") as mock:
        mock.return_value.execute.return_value = {"id": "fake-123"}
        yield mock

def test_create_user(mock_db):
    result = create_user("John", "john@example.com")
    assert result["id"] == "fake-123"  # Tests nothing real!
```

**RIGHT**:

```python
# DO: Use real database in integration tests
@pytest.fixture
def real_db():
    db = DataFlow("sqlite:///:memory:")  # Real SQLite

    @db.model
    class User:
        id: str
        name: str
        email: str

    yield db
    db.close()

def test_create_user(real_db):
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": "test-123",
        "name": "John",
        "email": "john@example.com"
    })
    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())
    assert results["create"]["id"] == "test-123"
```

**Why**: Mocks hide real integration issues. Use `:memory:` SQLite for fast, real tests.

---

### Anti-Pattern 7: Accessing `app._gateway.app`

**WRONG**:

```python
# DON'T: Access private attributes
app = Nexus()
app._gateway.app.add_middleware(SomeMiddleware)  # Private!
```

**RIGHT**:

```python
# DO: Use public middleware API
app = Nexus()
app.add_middleware(SomeMiddleware, config={"key": "value"})
```

**Why**: `_gateway` is implementation detail. Public APIs are stable across versions.

---

## Scaffolding Templates

### Template 1: SaaS API Backend (Most Common)

Use for: Standard REST API with database, authentication, CRUD operations.

```python
"""
SaaS API Backend Template
-------------------------
Production-ready API with auth, database, and multi-channel support.

Provides:
- REST API at http://localhost:8000
- MCP tools at ws://localhost:3001
- CLI via `nexus execute <workflow>`
- JWT authentication with RBAC
- PostgreSQL with connection pooling
"""

import os
import uuid

from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.dependencies import RequireRole, RequirePermission, get_current_user
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime
from fastapi import Depends

# ============================================================================
# Configuration (from environment)
# ============================================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
JWT_SECRET = os.environ["JWT_SECRET"]  # REQUIRED
API_PORT = int(os.environ.get("API_PORT", "8000"))
MCP_PORT = int(os.environ.get("MCP_PORT", "3001"))

# ============================================================================
# Initialize Frameworks
# ============================================================================

app = Nexus(
    api_port=API_PORT,
    mcp_port=MCP_PORT,
    auto_discovery=False  # CRITICAL: Prevents blocking with DataFlow
)

db = DataFlow(
    database_url=DATABASE_URL,
    auto_migrate=True,  # v0.11.0: Works in Docker/FastAPI via SyncDDLExecutor
)

runtime = AsyncLocalRuntime()  # Initialize once at module level

# ============================================================================
# Authentication (CORRECT WS02 imports and parameters)
# ============================================================================

auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret=JWT_SECRET,                         # CORRECT: `secret`
        algorithm="HS256",
        exempt_paths=["/health", "/docs"],          # CORRECT: `exempt_paths`
    ),
    rbac={                                          # Plain dict, NOT RBACConfig
        "admin": ["*"],
        "member": ["users:read", "contacts:read", "contacts:create", "contacts:update"],
        "viewer": ["users:read", "contacts:read"],
    },
    tenant_isolation=TenantConfig(                  # TenantConfig object, NOT True
        jwt_claim="tenant_id",
        allow_admin_override=True,
        admin_role="admin",                         # CORRECT: singular string
    ),
)

app.add_plugin(auth)

# ============================================================================
# Models
# ============================================================================

@db.model
class User:
    id: str
    email: str
    name: str
    role: str = "member"
    org_id: str = None

@db.model
class Contact:
    id: str
    email: str
    name: str
    company: str = None
    org_id: str = None
    created_by: str = None

# ============================================================================
# Handlers (API Endpoints)
# ============================================================================

@app.handler("create_contact", description="Create a new contact")
async def create_contact(
    email: str,
    name: str,
    company: str = None,
    user=Depends(RequirePermission("contacts:create")),
) -> dict:
    """Create a contact in the authenticated user's organization."""
    workflow = WorkflowBuilder()
    workflow.add_node("ContactCreateNode", "create", {
        "id": f"contact-{uuid.uuid4()}",
        "email": email,
        "name": name,
        "company": company,
        "created_by": user.user_id,
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]


@app.handler("list_contacts", description="List contacts with filters")
async def list_contacts(
    company: str = None,
    limit: int = 20,
    offset: int = 0,
    user=Depends(RequirePermission("contacts:read")),
) -> dict:
    """List contacts in the authenticated user's organization."""
    filters = {}
    if company:
        filters["company"] = {"$regex": company}

    workflow = WorkflowBuilder()
    workflow.add_node("ContactListNode", "list", {
        "filter": filters,
        "limit": limit,
        "offset": offset,
        "order_by": ["-created_at"]
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {
        "contacts": results["list"]["items"],
        "total": results["list"]["total"]
    }


@app.handler("delete_contact", description="Delete a contact")
async def delete_contact(
    contact_id: str,
    user=Depends(RequirePermission("contacts:delete")),
) -> dict:
    """Soft-delete a contact."""
    workflow = WorkflowBuilder()
    workflow.add_node("ContactDeleteNode", "delete", {
        "filter": {"id": contact_id},
        "soft_delete": True
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {"deleted": True, "id": contact_id}

# ============================================================================
# Public Endpoints (No Auth)
# ============================================================================

@app.endpoint("/health", methods=["GET"])
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

# ============================================================================
# Startup
# ============================================================================

if __name__ == "__main__":
    import asyncio
    asyncio.run(db.create_tables_async())
    app.start()
```

---

### Template 2: AI Agent Backend

Use for: LLM-powered features, chatbots, document analysis, AI assistants.

```python
"""
AI Agent Backend Template
-------------------------
Production-ready AI agent with MCP tools and Nexus exposure.

Provides:
- REST API for chat/analysis
- MCP tools for AI-to-AI communication
- Structured outputs via Kaizen signatures
- Memory for multi-turn conversations
"""

import os
from dataclasses import dataclass

from nexus import Nexus
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from kailash.runtime import AsyncLocalRuntime

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class AgentConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000
    max_turns: int = 10

# ============================================================================
# Signatures (Type-Safe I/O)
# ============================================================================

class ChatSignature(Signature):
    """Chat completion with context."""
    message: str = InputField(description="User message")
    context: str = InputField(description="Additional context", default="")

    response: str = OutputField(description="Assistant response")
    confidence: float = OutputField(description="Confidence score 0.0-1.0")

class AnalysisSignature(Signature):
    """Document analysis with structured output."""
    document: str = InputField(description="Document text to analyze")
    question: str = InputField(description="Analysis question")

    answer: str = OutputField(description="Analysis answer")
    citations: list = OutputField(description="Supporting quotes")
    confidence: float = OutputField(description="Confidence score")

# ============================================================================
# Agents
# ============================================================================

class ChatAgent(BaseAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(config=config, signature=ChatSignature())

    async def chat(self, message: str, session_id: str, context: str = "") -> dict:
        return await self.run_async(message=message, context=context, session_id=session_id)

class AnalysisAgent(BaseAgent):
    def __init__(self, config: AgentConfig):
        super().__init__(config=config, signature=AnalysisSignature())

    async def analyze(self, document: str, question: str) -> dict:
        result = await self.run_async(document=document, question=question)
        if result.get("confidence", 0) < 0.5:
            result["warning"] = "Low confidence - consider manual review"
        return result

# ============================================================================
# Initialize
# ============================================================================

app = Nexus(api_port=8000, mcp_port=3001, auto_discovery=False)

config = AgentConfig(
    llm_provider=os.environ.get("LLM_PROVIDER", "openai"),
    model=os.environ.get("LLM_MODEL", "gpt-4")
)

chat_agent = ChatAgent(config)
analysis_agent = AnalysisAgent(config)

# ============================================================================
# Handlers
# ============================================================================

@app.handler("chat", description="Send a chat message")
async def chat(message: str, session_id: str = "default", context: str = "") -> dict:
    return await chat_agent.chat(message, session_id, context)

@app.handler("analyze", description="Analyze a document")
async def analyze(document: str, question: str) -> dict:
    return await analysis_agent.analyze(document, question)

@app.handler("summarize", description="Summarize a document")
async def summarize(document: str, max_length: int = 500) -> dict:
    result = await analysis_agent.analyze(
        document=document,
        question=f"Summarize this document in {max_length} words or less."
    )
    return {"summary": result["answer"], "key_points": result.get("citations", [])}

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    app.start()
```

---

### Template 3: Multi-Tenant Enterprise

Use for: Enterprise SaaS with multiple databases, tenant isolation, complex auth.

```python
"""
Multi-Tenant Enterprise Template
--------------------------------
Enterprise-grade multi-tenant application with:
- Separate databases per concern (primary, analytics, audit)
- Full tenant isolation
- RBAC with role hierarchy
- Audit logging
"""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime

from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.dependencies import RequirePermission
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime
from fastapi import Depends

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class DatabaseConfig:
    primary_url: str
    analytics_url: str
    audit_url: str
    pool_size: int = 20
    analytics_pool_size: int = 30
    audit_pool_size: int = 10

config = DatabaseConfig(
    primary_url=os.environ.get("PRIMARY_DATABASE_URL", "sqlite:///primary.db"),
    analytics_url=os.environ.get("ANALYTICS_DATABASE_URL", "sqlite:///analytics.db"),
    audit_url=os.environ.get("AUDIT_DATABASE_URL", "sqlite:///audit.db")
)

# ============================================================================
# Database Instances
# ============================================================================

primary_db = DataFlow(
    database_url=config.primary_url,
)

analytics_db = DataFlow(
    database_url=config.analytics_url,
)

audit_db = DataFlow(
    database_url=config.audit_url,
    echo=False
)

# ============================================================================
# Models
# ============================================================================

@primary_db.model
class Organization:
    id: str
    name: str
    plan: str = "free"

@primary_db.model
class User:
    id: str
    email: str
    name: str
    role: str = "member"
    org_id: str

@primary_db.model
class Project:
    id: str
    name: str
    description: str = None
    org_id: str
    created_by: str
    status: str = "active"

@analytics_db.model
class PageView:
    id: str
    user_id: str
    org_id: str
    page: str
    timestamp: datetime

@audit_db.model
class AuditLog:
    id: str
    org_id: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    changes: dict = None
    timestamp: datetime

# ============================================================================
# Nexus + Auth (CORRECT WS02 imports)
# ============================================================================

app = Nexus(
    api_port=int(os.environ.get("API_PORT", "8000")),
    mcp_port=int(os.environ.get("MCP_PORT", "3001")),
    auto_discovery=False
)

auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],           # CORRECT: `secret`
        algorithm="HS256",
        exempt_paths=["/health", "/docs"],          # CORRECT: `exempt_paths`
    ),
    rbac={                                          # Plain dict, NOT RBACConfig
        "owner": ["*"],
        "admin": ["users:*", "projects:*", "analytics:read"],
        "member": ["projects:read", "projects:create", "projects:update"],
        "viewer": ["projects:read", "analytics:read"],
    },
    tenant_isolation=TenantConfig(                  # TenantConfig object, NOT True
        jwt_claim="tenant_id",
        allow_admin_override=True,
        admin_role="owner",                         # CORRECT: singular string
    ),
)

app.add_plugin(auth)
runtime = AsyncLocalRuntime()

# ============================================================================
# Handlers
# ============================================================================

@app.handler("create_project", description="Create a new project")
async def create_project(
    name: str,
    description: str = None,
    user=Depends(RequirePermission("projects:create")),
) -> dict:
    project_id = f"proj-{uuid.uuid4()}"
    workflow = WorkflowBuilder()
    workflow.add_node("ProjectCreateNode", "create", {
        "id": project_id,
        "name": name,
        "description": description,
        "created_by": user.user_id,
        "status": "active"
    })
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]

@app.handler("list_projects", description="List organization projects")
async def list_projects(
    status: str = "active",
    limit: int = 50,
    user=Depends(RequirePermission("projects:read")),
) -> dict:
    workflow = WorkflowBuilder()
    workflow.add_node("ProjectListNode", "list", {
        "filter": {"status": status},
        "limit": limit,
        "order_by": ["-created_at"]
    })
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {"projects": results["list"]["items"], "total": results["list"]["total"]}

@app.handler("get_analytics", description="Get usage analytics")
async def get_analytics(
    user=Depends(RequirePermission("analytics:read")),
) -> dict:
    return {"page_views": 0, "api_calls": 0}

@app.handler("get_audit_log", description="Get audit log")
async def get_audit_log(
    limit: int = 100,
    user=Depends(RequirePermission("audit:read")),
) -> dict:
    return {"audit_logs": [], "total": 0}

@app.endpoint("/health", methods=["GET"])
async def health_check():
    return {"status": "healthy", "version": "1.0.0"}

# ============================================================================
# Startup
# ============================================================================

async def initialize_databases():
    await primary_db.create_tables_async()
    await analytics_db.create_tables_async()
    await audit_db.create_tables_async()

if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(initialize_databases())
    app.start()
```

---

## Pattern Selection Checklist

Before implementing, verify:

- [ ] **Data persistence needed?** --> Use DataFlow
- [ ] **Authentication required?** --> Add NexusAuthPlugin
- [ ] **Multiple databases?** --> Use Multi-DataFlow pattern
- [ ] **AI features?** --> Add Kaizen agent
- [ ] **Complex orchestration?** --> Use WorkflowBuilder
- [ ] **External integrations?** --> Create Custom Nodes
- [ ] **AI agent exposure?** --> Enable MCP

## Critical Settings Reminder

```python
# ALWAYS start with these settings

app = Nexus(
    auto_discovery=False,  # CRITICAL for DataFlow integration
)

db = DataFlow(
    auto_migrate=True,  # v0.11.0 default: Works in Docker/FastAPI via SyncDDLExecutor
)

runtime = AsyncLocalRuntime()  # CRITICAL for async contexts

# Use type annotations on handlers
@app.handler("my_handler")
async def my_handler(param: str, optional: int = 10) -> dict:
    return {"result": "..."}
```

### Auth Import Cheat Sheet

```python
# CORRECT imports (WS02 actual)
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, RateLimitConfig, AuditConfig
from nexus.auth.dependencies import RequireRole, RequirePermission, get_current_user

# CORRECT parameter names
JWTConfig(secret=..., exempt_paths=[...])       # NOT secret_key, NOT exclude_paths
TenantConfig(admin_role="admin")                 # NOT admin_roles (singular string)
rbac={"admin": ["*"]}                            # Plain dict, NOT RBACConfig(roles={...})
tenant_isolation=TenantConfig(jwt_claim="...")    # TenantConfig object, NOT True
```

## Validation Tests

All templates and anti-patterns validated with 19 passing tests in `tests/docs/templates/`:

- `test_saas_api_template.py`: 7 tests (health, CRUD permissions, admin, member, viewer, no-auth)
- `test_ai_agent_template.py`: 5 tests (chat handler, analysis, summarize, multiple handlers)
- `test_multi_tenant_template.py`: 7 tests (multiple DataFlow, models, owner/member/viewer roles, TenantConfig)
