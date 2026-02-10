# Codegen Decision Tree

**Purpose**: Structured decision logic for codegen agents to select the right Kailash pattern. Every scaffolding task MUST start by traversing this tree.

**Version**: 0.12.0
**Last Updated**: 2026-02-09

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
# DO: Use NexusAuthPlugin
from nexus.plugins.auth import NexusAuthPlugin, JWTConfig

app = Nexus()
auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret_key=os.environ["JWT_SECRET"],
        algorithm="HS256"
    ),
    tenant_isolation=True
)
app.add_plugin(auth)

@app.handler("protected_endpoint")
@auth.require_permission("resource:read")
async def protected(request: Request) -> dict:
    user = request.state.user  # Already verified
    return {"user_id": user["sub"]}
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
    enable_model_persistence=False,
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
    # Validation can be inline
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

    # Verify actually created
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
from contextlib import asynccontextmanager

from nexus import Nexus
from nexus.plugins.auth import NexusAuthPlugin, JWTConfig, RBACConfig
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# ============================================================================
# Configuration (from environment)
# ============================================================================

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///app.db")
JWT_SECRET = os.environ["JWT_SECRET"]  # REQUIRED: Set JWT_SECRET env var
API_PORT = int(os.environ.get("API_PORT", "8000"))
MCP_PORT = int(os.environ.get("MCP_PORT", "3001"))

# ============================================================================
# Initialize Frameworks
# ============================================================================

# CRITICAL: auto_discovery=False prevents blocking with DataFlow
app = Nexus(
    api_port=API_PORT,
    mcp_port=MCP_PORT,
    auto_discovery=False
)

# CRITICAL: These settings prevent slow startup and async deadlock
db = DataFlow(
    database_url=DATABASE_URL,
    enable_model_persistence=False,  # Fast startup
    auto_migrate=False                # Docker-safe
)

# Initialize runtime once at module level
runtime = AsyncLocalRuntime()

# ============================================================================
# Authentication
# ============================================================================

auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret_key=JWT_SECRET,
        algorithm="HS256",
        access_token_expire_minutes=30
    ),
    rbac=RBACConfig(
        roles={
            "admin": ["*"],
            "member": ["users:read", "contacts:*"],
            "viewer": ["users:read", "contacts:read"]
        }
    ),
    tenant_isolation=True
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
    org_id: str = None  # Tenant ID for isolation

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
@auth.require_permission("contacts:create")
async def create_contact(
    email: str,
    name: str,
    company: str = None,
    request: "Request" = None
) -> dict:
    """Create a contact in the authenticated user's organization."""
    org_id = request.state.org_id
    user_id = request.state.user["sub"]

    workflow = WorkflowBuilder()
    workflow.add_node("ContactCreateNode", "create", {
        "id": f"contact-{uuid.uuid4()}",
        "email": email,
        "name": name,
        "company": company,
        "org_id": org_id,
        "created_by": user_id
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]


@app.handler("list_contacts", description="List contacts with filters")
@auth.require_permission("contacts:read")
async def list_contacts(
    company: str = None,
    limit: int = 20,
    offset: int = 0,
    request: "Request" = None
) -> dict:
    """List contacts in the authenticated user's organization."""
    org_id = request.state.org_id

    filters = {"org_id": org_id}
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


@app.handler("get_contact", description="Get a single contact by ID")
@auth.require_permission("contacts:read")
async def get_contact(contact_id: str, request: "Request" = None) -> dict:
    """Get a specific contact (tenant-isolated)."""
    org_id = request.state.org_id

    workflow = WorkflowBuilder()
    workflow.add_node("ContactReadNode", "read", {
        "filter": {"id": contact_id, "org_id": org_id}
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    contact = results["read"]

    if not contact:
        return {"error": "Contact not found", "status": 404}
    return contact


@app.handler("delete_contact", description="Delete a contact")
@auth.require_permission("contacts:delete")
async def delete_contact(contact_id: str, request: "Request" = None) -> dict:
    """Soft-delete a contact (tenant-isolated)."""
    org_id = request.state.org_id

    workflow = WorkflowBuilder()
    workflow.add_node("ContactDeleteNode", "delete", {
        "filter": {"id": contact_id, "org_id": org_id},
        "soft_delete": True
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {"deleted": True, "id": contact_id}

# ============================================================================
# Public Endpoints (No Auth)
# ============================================================================

@app.endpoint("/health", methods=["GET"])
async def health_check():
    """Health check endpoint for load balancers."""
    return {"status": "healthy", "version": "1.0.0"}

# ============================================================================
# Startup
# ============================================================================

if __name__ == "__main__":
    # Create tables if needed
    import asyncio
    asyncio.run(db.create_tables_async())

    # Start the server
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
from typing import Optional

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
    max_turns: int = 10  # Enable conversation memory

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
    """Conversational agent with memory."""

    def __init__(self, config: AgentConfig):
        super().__init__(config=config, signature=ChatSignature())

    async def chat(self, message: str, session_id: str, context: str = "") -> dict:
        """Process chat message with session memory."""
        result = await self.run_async(
            message=message,
            context=context,
            session_id=session_id  # Memory continuity
        )
        return result


class AnalysisAgent(BaseAgent):
    """Document analysis agent with structured outputs."""

    def __init__(self, config: AgentConfig):
        super().__init__(config=config, signature=AnalysisSignature())

    async def analyze(self, document: str, question: str) -> dict:
        """Analyze document and return structured result."""
        result = await self.run_async(document=document, question=question)

        if result.get("confidence", 0) < 0.5:
            result["warning"] = "Low confidence - consider manual review"

        return result

# ============================================================================
# Initialize
# ============================================================================

app = Nexus(
    api_port=8000,
    mcp_port=3001,
    auto_discovery=False
)

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
async def chat(
    message: str,
    session_id: str = "default",
    context: str = ""
) -> dict:
    """
    Process a chat message with conversation memory.

    Args:
        message: User message
        session_id: Session ID for memory continuity
        context: Additional context for the conversation

    Returns:
        response: Assistant's response
        confidence: Confidence score
    """
    return await chat_agent.chat(message, session_id, context)


@app.handler("analyze", description="Analyze a document")
async def analyze(document: str, question: str) -> dict:
    """
    Analyze a document and answer a question about it.

    Args:
        document: Document text (up to 100K tokens)
        question: Question to answer about the document

    Returns:
        answer: Analysis answer
        citations: Supporting quotes from document
        confidence: Confidence score
    """
    return await analysis_agent.analyze(document, question)


@app.handler("summarize", description="Summarize a document")
async def summarize(document: str, max_length: int = 500) -> dict:
    """
    Generate a summary of the document.

    Args:
        document: Document text to summarize
        max_length: Maximum summary length in words

    Returns:
        summary: Document summary
        key_points: List of key points
    """
    result = await analysis_agent.analyze(
        document=document,
        question=f"Summarize this document in {max_length} words or less. Include key points."
    )
    return {
        "summary": result["answer"],
        "key_points": result.get("citations", [])
    }

# ============================================================================
# Startup
# ============================================================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()  # Load API keys from .env

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
- RBAC + feature flags
- Audit logging
"""

import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from nexus import Nexus
from nexus.plugins.auth import NexusAuthPlugin, JWTConfig, RBACConfig
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

# ============================================================================
# Configuration
# ============================================================================

@dataclass
class DatabaseConfig:
    primary_url: str
    analytics_url: str
    audit_url: str
    pool_size: int = 20
    analytics_pool_size: int = 30  # Higher for read-heavy
    audit_pool_size: int = 10

config = DatabaseConfig(
    primary_url=os.environ.get("PRIMARY_DATABASE_URL", "sqlite:///primary.db"),
    analytics_url=os.environ.get("ANALYTICS_DATABASE_URL", "sqlite:///analytics.db"),
    audit_url=os.environ.get("AUDIT_DATABASE_URL", "sqlite:///audit.db")
)

# ============================================================================
# Database Instances
# ============================================================================

# Primary database for transactional data
primary_db = DataFlow(
    database_url=config.primary_url,
    enable_model_persistence=False,
    auto_migrate=False,
    pool_size=config.pool_size
)

# Analytics database (read-heavy, different optimization)
analytics_db = DataFlow(
    database_url=config.analytics_url,
    enable_model_persistence=False,
    auto_migrate=False,
    pool_size=config.analytics_pool_size
)

# Audit database (append-only, compliance)
audit_db = DataFlow(
    database_url=config.audit_url,
    enable_model_persistence=False,
    auto_migrate=False,
    pool_size=config.audit_pool_size,
    echo=False  # No SQL logging for audit
)

# ============================================================================
# Primary Database Models
# ============================================================================

@primary_db.model
class Organization:
    id: str
    name: str
    plan: str = "free"  # free, pro, enterprise
    features: dict = None  # Feature flags

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

# ============================================================================
# Analytics Database Models
# ============================================================================

@analytics_db.model
class PageView:
    id: str
    user_id: str
    org_id: str
    page: str
    timestamp: datetime

@analytics_db.model
class ApiCall:
    id: str
    org_id: str
    endpoint: str
    method: str
    latency_ms: int
    timestamp: datetime

# ============================================================================
# Audit Database Models
# ============================================================================

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
    ip_address: str = None

# ============================================================================
# Initialize Nexus with Auth
# ============================================================================

app = Nexus(
    api_port=int(os.environ.get("API_PORT", "8000")),
    mcp_port=int(os.environ.get("MCP_PORT", "3001")),
    auto_discovery=False
)

auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret_key=os.environ["JWT_SECRET"],  # REQUIRED: Set JWT_SECRET env var
        algorithm="HS256",
        access_token_expire_minutes=30
    ),
    rbac=RBACConfig(
        roles={
            "owner": ["*"],
            "admin": ["users:*", "projects:*", "analytics:read"],
            "member": ["projects:read", "projects:create", "projects:update"],
            "viewer": ["projects:read", "analytics:read"]
        }
    ),
    tenant_isolation=True
)

app.add_plugin(auth)

runtime = AsyncLocalRuntime()

# ============================================================================
# Audit Logging Helper
# ============================================================================

async def log_audit(
    org_id: str,
    actor_id: str,
    action: str,
    resource_type: str,
    resource_id: str,
    changes: dict = None,
    ip_address: str = None
):
    """Log an audit event (fire-and-forget)."""
    workflow = WorkflowBuilder()
    workflow.add_node("AuditLogCreateNode", "log", {
        "id": f"audit-{uuid.uuid4()}",
        "org_id": org_id,
        "actor_id": actor_id,
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "changes": changes,
        "timestamp": datetime.utcnow(),
        "ip_address": ip_address
    })
    # Fire and forget - don't await
    await runtime.execute_workflow_async(workflow.build(), inputs={})

# ============================================================================
# Project Handlers
# ============================================================================

@app.handler("create_project", description="Create a new project")
@auth.require_permission("projects:create")
async def create_project(
    name: str,
    description: str = None,
    request: "Request" = None
) -> dict:
    """Create a project in the organization."""
    org_id = request.state.org_id
    user_id = request.state.user["sub"]
    project_id = f"proj-{uuid.uuid4()}"

    workflow = WorkflowBuilder()
    workflow.add_node("ProjectCreateNode", "create", {
        "id": project_id,
        "name": name,
        "description": description,
        "org_id": org_id,
        "created_by": user_id,
        "status": "active"
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})

    # Log audit event
    await log_audit(
        org_id=org_id,
        actor_id=user_id,
        action="create",
        resource_type="project",
        resource_id=project_id,
        changes={"name": name},
        ip_address=request.client.host if request.client else None
    )

    return results["create"]


@app.handler("list_projects", description="List organization projects")
@auth.require_permission("projects:read")
async def list_projects(
    status: str = "active",
    limit: int = 50,
    request: "Request" = None
) -> dict:
    """List projects in the organization."""
    org_id = request.state.org_id

    workflow = WorkflowBuilder()
    workflow.add_node("ProjectListNode", "list", {
        "filter": {"org_id": org_id, "status": status},
        "limit": limit,
        "order_by": ["-created_at"]
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {
        "projects": results["list"]["items"],
        "total": results["list"]["total"]
    }

# ============================================================================
# Analytics Handlers
# ============================================================================

@app.handler("get_analytics", description="Get usage analytics")
@auth.require_permission("analytics:read")
async def get_analytics(
    start_date: str,
    end_date: str,
    request: "Request" = None
) -> dict:
    """Get analytics for date range."""
    org_id = request.state.org_id

    # Query page views
    pv_workflow = WorkflowBuilder()
    pv_workflow.add_node("PageViewListNode", "views", {
        "filter": {
            "org_id": org_id,
            "timestamp": {"$gte": start_date, "$lte": end_date}
        },
        "limit": 10000
    })

    # Query API calls
    api_workflow = WorkflowBuilder()
    api_workflow.add_node("ApiCallListNode", "calls", {
        "filter": {
            "org_id": org_id,
            "timestamp": {"$gte": start_date, "$lte": end_date}
        },
        "limit": 10000
    })

    pv_results, _ = await runtime.execute_workflow_async(pv_workflow.build(), inputs={})
    api_results, _ = await runtime.execute_workflow_async(api_workflow.build(), inputs={})

    return {
        "page_views": len(pv_results["views"]["items"]),
        "api_calls": len(api_results["calls"]["items"]),
        "period": {"start": start_date, "end": end_date}
    }

# ============================================================================
# Audit Handlers
# ============================================================================

@app.handler("get_audit_log", description="Get audit log")
@auth.require_permission("audit:read")  # Only admins/owners
async def get_audit_log(
    resource_type: str = None,
    actor_id: str = None,
    limit: int = 100,
    request: "Request" = None
) -> dict:
    """Get audit log for the organization."""
    org_id = request.state.org_id

    filters = {"org_id": org_id}
    if resource_type:
        filters["resource_type"] = resource_type
    if actor_id:
        filters["actor_id"] = actor_id

    workflow = WorkflowBuilder()
    workflow.add_node("AuditLogListNode", "logs", {
        "filter": filters,
        "limit": limit,
        "order_by": ["-timestamp"]
    })

    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {
        "audit_logs": results["logs"]["items"],
        "total": results["logs"]["total"]
    }

# ============================================================================
# Startup
# ============================================================================

async def initialize_databases():
    """Initialize all database tables."""
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

- [ ] **Data persistence needed?** -> Use DataFlow
- [ ] **Authentication required?** -> Add NexusAuthPlugin
- [ ] **Multiple databases?** -> Use Multi-DataFlow pattern
- [ ] **AI features?** -> Add Kaizen agent
- [ ] **Complex orchestration?** -> Use WorkflowBuilder
- [ ] **External integrations?** -> Create Custom Nodes
- [ ] **AI agent exposure?** -> Enable MCP

## Critical Settings Reminder

```python
# ALWAYS start with these settings

app = Nexus(
    auto_discovery=False,  # CRITICAL for DataFlow integration
)

db = DataFlow(
    enable_model_persistence=False,  # CRITICAL for fast startup
    auto_migrate=False,              # CRITICAL for Docker/FastAPI
)

runtime = AsyncLocalRuntime()  # CRITICAL for async contexts

# Use type annotations on handlers
@app.handler("my_handler")
async def my_handler(param: str, optional: int = 10) -> dict:
    # Handler body
    return {"result": "..."}
```
