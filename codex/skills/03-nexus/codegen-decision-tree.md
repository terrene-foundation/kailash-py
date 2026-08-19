# Codegen Decision Tree

Pattern selection logic for Nexus scaffolding. Traverse before every codegen task.

## Decision Tree

```
START: What are you building?
├── API endpoint (reads/writes data)?
│   ├── Simple CRUD (single model) → Handler + DataFlow Model [SaaS Template]
│   ├── Multi-model with relationships → Nexus+DataFlow + Multi-DataFlow [Multi-Tenant Template]
│   ├── Complex validation/transformation → WorkflowBuilder + Custom Node
│   └── Requires auth → NexusAuthPlugin + above patterns
├── AI-powered feature?
│   ├── Single LLM call → Handler with agent.run() inside
│   ├── Multi-step agent (ReAct, tools) → Kaizen BaseAgent + Handler [AI Agent Template]
│   ├── RAG/semantic search → Kaizen Agent + MCP + DataFlow pgvector
│   └── AI agent integration → MCP Integration (expose handlers as tools)
├── Background/batch processing?
│   ├── Event-driven (webhooks) → WorkflowBuilder + AsyncLocalRuntime
│   ├── Scheduled jobs → WorkflowBuilder + external scheduler (APScheduler/Celery)
│   └── Bulk data import → DataFlow BulkCreateNode/BulkUpsertNode
└── Infrastructure only?
    ├── Authentication → NexusAuthPlugin (JWT, RBAC, tenant isolation)
    └── Custom middleware → app.add_middleware()
```

| Building...       | Primary Pattern        | Supporting Patterns   | Template     |
| ----------------- | ---------------------- | --------------------- | ------------ |
| REST API with DB  | Handler + DataFlow     | Auth Stack            | SaaS API     |
| Multi-tenant SaaS | Handler + DataFlow     | Auth + Multi-DataFlow | Multi-Tenant |
| AI chatbot        | Kaizen Agent + Handler | MCP Integration       | AI Agent     |
| ETL pipeline      | WorkflowBuilder        | Custom Node           | Manual       |
| Background job    | WorkflowBuilder        | AsyncLocalRuntime     | Manual       |
| Public API        | Handler                | (no auth)             | SaaS (mod)   |

**Pre-implementation checklist:** Data persistence? -> DataFlow. Auth? -> NexusAuthPlugin. Multiple DBs? -> Multi-DataFlow. AI? -> Kaizen. Complex orchestration? -> WorkflowBuilder. External integrations? -> Custom Nodes. AI agent exposure? -> MCP.

---

## Anti-Patterns

### AP1: PythonCodeNode for Business Logic

PythonCodeNode sandbox blocks imports. Use `@app.handler()` for full Python access.

```python
# WRONG: sandbox blocks asyncio, httpx, app imports
workflow.add_node("PythonCodeNode", "process", {"code": "import httpx  # BLOCKED!"})

# RIGHT:
@app.handler("process")
async def process(data: dict) -> dict:
    async with httpx.AsyncClient() as client:
        return {"result": (await client.get("https://api.example.com")).json()}
```

### AP2: Accessing Private `_gateway.app`

Never use `app._gateway.app` — bypasses middleware, auth, breaks across versions.

```python
# WRONG:
app._gateway.app.add_middleware(SomeMiddleware)   # Private!
@app._gateway.app.get("/users")                   # Bypasses Nexus!

# RIGHT:
app.add_middleware(SomeMiddleware, config={...})   # Public middleware API
@app.handler("get_users")                         # Handler (recommended)
async def get_users() -> dict: ...
app.include_router(legacy_router, prefix="/legacy")  # Existing routers
@app.endpoint("/health", methods=["GET"])            # Custom endpoint (API-only)
async def health(): ...
```

### AP3: Building Auth from Scratch

NexusAuthPlugin handles JWT, refresh, RBAC, tenant isolation. See Auth Cheat Sheet below.

```python
# WRONG: 200+ lines of custom JWT/RBAC/tenant handling
from jose import jwt
payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])  # + 150 more lines

# RIGHT: See NexusAuthPlugin setup in SaaS Template
```

### AP4: DataFlow Instance Per Request

DataFlow manages connection pools. Create at module level, reuse across requests.

```python
# WRONG:
@app.handler("get_user")
async def get_user(user_id: str) -> dict:
    db = DataFlow("postgresql://...")  # New instance every request — pool exhausted!

# RIGHT:
db = DataFlow("postgresql://...", pool_size=20)  # Module level, reuse everywhere
```

### AP5: WorkflowBuilder for Simple CRUD

WorkflowBuilder is for multi-step orchestration. Simple CRUD belongs in handlers.

```python
# WRONG: 20 lines of workflow setup for a single create
workflow.add_node("ValidateInputNode", "validate", {...})
workflow.add_node("UserCreateNode", "create", {})
workflow.add_connection("validate", "validated", "create", "data")

# RIGHT:
@app.handler("create_user")
async def create_user(name: str, email: str) -> dict:
    if not email or "@" not in email:
        return {"error": "Invalid email"}
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"id": f"user-{uuid.uuid4()}", "name": name, "email": email})
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]
```

### AP6: Mocking in Integration Tests

Use real database (`:memory:` SQLite) in integration tests, not mocks.

```python
# WRONG:
with patch("myapp.db.DataFlow") as mock:
    mock.return_value.execute.return_value = {"id": "fake-123"}  # Tests nothing real

# RIGHT:
db = DataFlow("sqlite:///:memory:")
@db.model
class User:
    id: str; name: str; email: str
# Run real workflow against real SQLite
```

---

## Scaffolding Templates

### Template 1: SaaS API Backend

Standard REST API with auth, database, CRUD. Most common starting point.

```python
import os, uuid
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig
from nexus.auth.dependencies import RequirePermission
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime
from nexus.http import Depends

app = Nexus(api_port=8000, mcp_port=3001, auto_discovery=False)  # auto_discovery=False CRITICAL with DataFlow
db = DataFlow(database_url=os.environ.get("DATABASE_URL", "sqlite:///app.db"), auto_migrate=True)
runtime = AsyncLocalRuntime()

auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"], algorithm="HS256", exempt_paths=["/health", "/docs"]),
    rbac={"admin": ["*"], "member": ["contacts:read", "contacts:create", "contacts:update"], "viewer": ["contacts:read"]},
    tenant_isolation=TenantConfig(jwt_claim="tenant_id", allow_admin_override=True, admin_role="admin"),
)
app.add_plugin(auth)

@db.model
class Contact:
    id: str; email: str; name: str; company: str = None; org_id: str = None; created_by: str = None

@app.handler("create_contact")
async def create_contact(email: str, name: str, company: str = None, user=Depends(RequirePermission("contacts:create"))) -> dict:
    workflow = WorkflowBuilder()
    workflow.add_node("ContactCreateNode", "create", {"id": f"contact-{uuid.uuid4()}", "email": email, "name": name, "company": company, "created_by": user.user_id})
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]

@app.handler("list_contacts")
async def list_contacts(company: str = None, limit: int = 20, user=Depends(RequirePermission("contacts:read"))) -> dict:
    filters = {"company": {"$regex": company}} if company else {}
    workflow = WorkflowBuilder()
    workflow.add_node("ContactListNode", "list", {"filter": filters, "limit": limit, "order_by": ["-created_at"]})
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {"contacts": results["list"]["items"], "total": results["list"]["total"]}

@app.endpoint("/health", methods=["GET"])
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import asyncio
    asyncio.run(db.create_tables_async())
    app.start()
```

### Template 2: AI Agent Backend

LLM-powered features with Kaizen agents and Nexus exposure.

```python
import os
from nexus import Nexus
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField

class ChatSignature(Signature):
    message: str = InputField(description="User message")
    context: str = InputField(description="Additional context", default="")
    response: str = OutputField(description="Assistant response")
    confidence: float = OutputField(description="Confidence score 0.0-1.0")

class AnalysisSignature(Signature):
    document: str = InputField(description="Document text")
    question: str = InputField(description="Analysis question")
    answer: str = OutputField(description="Analysis answer")
    citations: list = OutputField(description="Supporting quotes")
    confidence: float = OutputField(description="Confidence score")

class ChatAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=ChatSignature())
    async def chat(self, message: str, session_id: str, context: str = "") -> dict:
        return await self.run_async(message=message, context=context, session_id=session_id)

class AnalysisAgent(BaseAgent):
    def __init__(self, config):
        super().__init__(config=config, signature=AnalysisSignature())
    async def analyze(self, document: str, question: str) -> dict:
        result = await self.run_async(document=document, question=question)
        if result.get("confidence", 0) < 0.5:
            result["warning"] = "Low confidence - consider manual review"
        return result

app = Nexus(api_port=8000, mcp_port=3001, auto_discovery=False)
chat_agent = ChatAgent(config={"llm_provider": os.environ.get("LLM_PROVIDER", "openai"), "model": os.environ.get("LLM_MODEL", "")})
analysis_agent = AnalysisAgent(config={"llm_provider": os.environ.get("LLM_PROVIDER", "openai"), "model": os.environ.get("LLM_MODEL", "")})

@app.handler("chat")
async def chat(message: str, session_id: str = "default", context: str = "") -> dict:
    return await chat_agent.chat(message, session_id, context)

@app.handler("analyze")
async def analyze(document: str, question: str) -> dict:
    return await analysis_agent.analyze(document, question)

@app.handler("summarize")
async def summarize(document: str, max_length: int = 500) -> dict:
    result = await analysis_agent.analyze(document, f"Summarize in {max_length} words or less.")
    return {"summary": result["answer"], "key_points": result.get("citations", [])}

if __name__ == "__main__":
    from dotenv import load_dotenv; load_dotenv()
    app.start()
```

### Template 3: Multi-Tenant Enterprise

Extends SaaS template with: separate databases per concern, role hierarchy, audit logging. Handlers follow same pattern as Template 1.

```python
from dataflow import DataFlow
from datetime import datetime

# Key difference: multiple DataFlow instances, one per concern
primary_db = DataFlow(database_url=os.environ.get("PRIMARY_DATABASE_URL", "sqlite:///primary.db"))
analytics_db = DataFlow(database_url=os.environ.get("ANALYTICS_DATABASE_URL", "sqlite:///analytics.db"))
audit_db = DataFlow(database_url=os.environ.get("AUDIT_DATABASE_URL", "sqlite:///audit.db"), echo=False)

@primary_db.model
class Organization:
    id: str; name: str; plan: str = "free"

@primary_db.model
class Project:
    id: str; name: str; description: str = None; org_id: str; created_by: str; status: str = "active"

@analytics_db.model
class PageView:
    id: str; user_id: str; org_id: str; page: str; timestamp: datetime

@audit_db.model
class AuditLog:
    id: str; org_id: str; actor_id: str; action: str; resource_type: str; resource_id: str; changes: dict = None; timestamp: datetime

# Auth: role hierarchy with owner > admin > member > viewer
auth = NexusAuthPlugin(
    jwt=JWTConfig(secret=os.environ["JWT_SECRET"], algorithm="HS256", exempt_paths=["/health"]),
    rbac={"owner": ["*"], "admin": ["users:*", "projects:*", "analytics:read"], "member": ["projects:read", "projects:create", "projects:update"], "viewer": ["projects:read", "analytics:read"]},
    tenant_isolation=TenantConfig(jwt_claim="tenant_id", allow_admin_override=True, admin_role="owner"),
)

# Initialize all databases on startup
async def initialize_databases():
    await primary_db.create_tables_async()
    await analytics_db.create_tables_async()
    await audit_db.create_tables_async()
```

---

## Critical Settings & Auth Cheat Sheet

```python
# ALWAYS start with these
app = Nexus(auto_discovery=False)     # CRITICAL for DataFlow integration
db = DataFlow(auto_migrate=True)      # Default: works in Docker/async
runtime = AsyncLocalRuntime()         # CRITICAL for async contexts

@app.handler("my_handler")
async def my_handler(param: str, optional: int = 10) -> dict:  # Type annotations required
    return {"result": "..."}
```

```python
# CORRECT auth imports (WS02 actual)
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, RateLimitConfig, AuditConfig
from nexus.auth.dependencies import RequireRole, RequirePermission, get_current_user

# CORRECT parameter names — common mistakes noted
JWTConfig(secret=..., exempt_paths=[...])       # NOT secret_key, NOT exclude_paths
TenantConfig(admin_role="admin")                 # NOT admin_roles (singular string)
rbac={"admin": ["*"]}                            # Plain dict, NOT RBACConfig(roles={...})
tenant_isolation=TenantConfig(jwt_claim="...")    # TenantConfig object, NOT True
```
