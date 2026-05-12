# Golden Patterns Catalog

Canonical patterns for Nexus, DataFlow, Kaizen, and Core SDK ranked by production usage.

## Pattern 1: Nexus Handler

Register async functions as multi-channel endpoints (API + CLI + MCP) with a single decorator.

**Use when**: REST endpoints, service orchestration, full Python access (no sandbox).
**Not for**: Multi-step orchestration (use WorkflowBuilder), pure data transforms (use Core SDK).

```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime
import os, uuid

app = Nexus(auto_discovery=False)
db = DataFlow(os.environ["DATABASE_URL"])

@db.model
class User:
    id: str
    email: str
    name: str

@app.handler("create_user", description="Create a new user")
async def create_user(email: str, name: str) -> dict:
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": f"user-{uuid.uuid4()}", "email": email, "name": name
    })
    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]

app.start()
```

**Mistakes**: Using PythonCodeNode for business logic (sandbox blocks asyncio/httpx) | Missing type annotations (defaults to str) | Returning non-dict (gets wrapped) | `List[dict]` annotation (mapped to str, use plain `list`)

## Pattern 2: DataFlow Model

`@db.model` auto-generates 11 CRUD workflow nodes per entity.

**Use when**: Any database entity needing CRUD + Bulk operations.

```python
from dataflow import DataFlow
from typing import Optional
from datetime import datetime

db = DataFlow(os.environ["DATABASE_URL"])

@db.model
class User:
    id: str                           # MUST be named 'id'
    email: str
    name: str
    role: str = "member"
    active: bool = True
    created_at: datetime = None       # Auto-managed by DataFlow
    org_id: Optional[str] = None

# Auto-generates: User{Create,Read,Update,Delete,List,Upsert,Count}Node
# + UserBulk{Create,Update,Delete,Upsert}Node
```

**Mistakes**: PK not named `id` | Manually setting `created_at`/`updated_at` (auto-managed) | Using `user.save()` (not an ORM, use workflow nodes)

## Pattern 3: Nexus + DataFlow Integration

Combines Patterns 1+2. Critical config additions to prevent blocking.

**Use when**: Any API with database reads/writes, SaaS backends.

```python
app = Nexus(api_port=8000, auto_discovery=False)  # CRITICAL: prevents filesystem scanning
db = DataFlow(database_url=os.environ["DATABASE_URL"], auto_migrate=True)

@app.handler("list_contacts")  # See Pattern 1 for create pattern
async def list_contacts(company_id: str, limit: int = 20) -> dict:
    wf = WorkflowBuilder()
    wf.add_node("ContactListNode", "list", {
        "filter": {"company_id": company_id}, "limit": limit, "order_by": ["-created_at"]})
    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(wf.build(), inputs={})
    return {"contacts": results["list"]["items"]}
```

**Mistakes**: Missing `auto_discovery=False` (infinite blocking) | Using removed params `enable_model_persistence`/`skip_migration` (use `auto_migrate=True`)

## Pattern 4: Auth Middleware Stack

JWT + RBAC + tenant isolation via NexusAuthPlugin.

**Use when**: Production APIs, multi-tenant SaaS, role-based access control.

```python
from nexus import Nexus
from nexus.auth.plugin import NexusAuthPlugin
from nexus.auth import JWTConfig, TenantConfig, AuditConfig
from nexus.auth.dependencies import RequireRole, RequirePermission, get_current_user
from nexus.http import Depends
import os

app = Nexus(auto_discovery=False)
auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret=os.environ["JWT_SECRET"],       # NOT 'secret_key'
        algorithm="HS256",
        exempt_paths=["/health", "/docs"],      # NOT 'exclude_paths'
    ),
    rbac={                                      # Plain dict, NOT RBACConfig
        "admin": ["*"],
        "member": ["contacts:read", "contacts:create"],
        "viewer": ["contacts:read"],
    },
    tenant_isolation=TenantConfig(              # NOT True/False
        jwt_claim="tenant_id",
        admin_role="super_admin",               # Singular, NOT 'admin_roles'
    ),
    audit=AuditConfig(backend="logging"),
)
app.add_plugin(auth)

@app.handler("admin_dashboard")
async def admin_dashboard(user=Depends(RequireRole("admin"))) -> dict:
    return {"user_id": user.user_id, "roles": user.roles}

@app.handler("create_contact")
async def create_contact(email: str, name: str,
    user=Depends(RequirePermission("contacts:create"))) -> dict:
    return {"created_by": user.user_id, "email": email, "name": name}
# get_current_user dependency also available for basic auth check without role/perm
```

**Factory methods**: `NexusAuthPlugin.basic_auth(jwt=...)`, `.saas_app(jwt=..., rbac=..., tenant_isolation=TenantConfig())`, `.enterprise(jwt=..., rbac=..., rate_limit=RateLimitConfig(...), tenant_isolation=..., audit=...)`

**Middleware order** (automatic): `Request -> Audit -> RateLimit -> JWT -> Tenant -> RBAC -> Handler`

**Auth parameter gotchas**:

| Wrong                                | Correct                           | Why                         |
| ------------------------------------ | --------------------------------- | --------------------------- |
| `secret_key`                         | `secret`                          | JWTConfig param name        |
| `exclude_paths`                      | `exempt_paths`                    | JWTConfig param name        |
| `admin_roles` (list)                 | `admin_role` (string)             | TenantConfig: singular      |
| `RBACConfig(roles={})`               | `rbac={...}` dict                 | No RBACConfig class         |
| `tenant_isolation=True`              | `tenant_isolation=TenantConfig()` | Config object required      |
| `from nexus.plugins.auth`            | `from nexus.auth.plugin`          | Correct import path         |
| `from __future__ import annotations` | Remove it                         | Breaks dependency injection |

## Pattern 5: Multi-DataFlow Instance

Separate DataFlow instances per database/domain for isolation.

**Use when**: Multiple databases, microservice boundaries, read replica separation.

```python
from dataflow import DataFlow
import os

users_db = DataFlow(database_url=os.environ["PRIMARY_DATABASE_URL"])
analytics_db = DataFlow(database_url=os.environ["ANALYTICS_DATABASE_URL"], pool_size=30)
logs_db = DataFlow(database_url=os.environ["LOGS_DATABASE_URL"], echo=False)

@users_db.model
class User:
    id: str
    email: str
    name: str
# Models scoped to their DataFlow instance — cannot share across instances
# Initialize in dependency order: await users_db.create_tables_async() etc.
```

## Pattern 6: Custom Node

Extend SDK with project-specific reusable workflow nodes.

**Use when**: Repeated logic across workflows, third-party integrations, domain calculations.
**Not for**: One-off logic (use handler), simple transforms (use TransformNode).

```python
from kailash.nodes.base import Node, NodeParameter, register_node

@register_node("SendgridEmailNode")
class SendgridEmailNode(Node):
    def get_parameters(self) -> dict[str, NodeParameter]:
        return {
            "to_email": NodeParameter(name="to_email", type=str, required=True),
            "subject": NodeParameter(name="subject", type=str, required=True),
            "template_id": NodeParameter(name="template_id", type=str, required=True),
            "template_data": NodeParameter(name="template_data", type=dict, required=False, default={}),
        }

    async def execute(self, **kwargs) -> dict:
        import httpx, os
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {os.environ['SENDGRID_API_KEY']}"},
                json={"personalizations": [{"to": [{"email": kwargs["to_email"]}],
                    "dynamic_template_data": kwargs.get("template_data", {})}],
                    "from": {"email": "noreply@example.com"},
                    "subject": kwargs["subject"], "template_id": kwargs["template_id"]})
        return {"success": response.status_code == 202, "status_code": response.status_code}

# Usage in workflow
workflow.add_node("SendgridEmailNode", "send_welcome", {
    "to_email": "user@example.com", "subject": "Welcome!",
    "template_id": "d-abc123", "template_data": {"name": "Alice"}
})
```

**Mistakes**: Missing `@register_node()` (required for string refs) | Blocking I/O in execute (use httpx, not requests) | Missing required param flags

## Pattern 7: Kaizen Agent

AI agent with structured outputs via Signature.

**Use when**: LLM-powered features, tool-using agents, multi-step reasoning.
**Not for**: String templating, deterministic processing (use workflows).

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass
import os

@dataclass
class AnalysisConfig:
    llm_provider: str = os.environ.get("LLM_PROVIDER", "openai")
    model: str = os.environ.get("LLM_MODEL", "")
    temperature: float = 0.1
    max_tokens: int = 2000

class AnalysisSignature(Signature):
    document: str = InputField(description="Document to analyze")
    question: str = InputField(description="Analysis question")
    answer: str = OutputField(description="Answer")
    confidence: float = OutputField(description="Score 0.0-1.0")
    citations: list = OutputField(description="Supporting quotes")

class DocumentAnalyzer(BaseAgent):
    def __init__(self, config: AnalysisConfig):
        super().__init__(config=config, signature=AnalysisSignature())

    async def analyze(self, document: str, question: str) -> dict:
        result = await self.run_async(document=document, question=question)
        if result.get("confidence", 0) < 0.5:
            result["warning"] = "Low confidence - consider manual review"
        return result
```

**Mistakes**: Creating BaseAgentConfig manually (let BaseAgent auto-convert) | Calling strategy.execute() directly (use `self.run()`/`self.run_async()`) | Missing `.env` (must `load_dotenv()` before creating agents)

## Pattern 8: Workflow Builder

Multi-step orchestration with branching, cycles, and data flow connections.

**Use when**: Multi-step pipelines, conditional branching (SwitchNode), cyclic workflows.
**Not for**: Single-step ops (use handler), simple CRUD (use DataFlow directly).

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

def build_order_workflow():
    wf = WorkflowBuilder()
    wf.add_node("PythonCodeNode", "validate", {"code": """
result = {"valid": order["quantity"] > 0 and order["price"] > 0, "order": order}
"""})
    wf.add_node("InventoryCheckNode", "check_inv", {"product_id": None})
    wf.add_node("OrderCreateNode", "create", {
        "product_id": None, "quantity": None, "price": None, "status": "confirmed"
    })
    # Wire connections (explicit data flow, NOT template ${...} syntax)
    wf.add_connection("validate", "order.product_id", "check_inv", "product_id")
    wf.add_connection("validate", "order.quantity", "create", "quantity")
    return wf  # additional connections follow same pattern

async def process_order(order: dict):
    wf = build_order_workflow()
    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(
        wf.build(), inputs={"order": order}  # ALWAYS call .build()
    )
    return results
```

**Mistakes**: Forgetting `.build()` | Using template syntax `${...}` (use `add_connection()`) | Using `inputs.get()` in PythonCodeNode (use try/except)

## Pattern 9: AsyncLocalRuntime

Async-first execution for Nexus/Docker contexts. Used throughout Patterns 1, 3, 8.

**Use when**: Nexus endpoints, Docker, concurrent requests, any `async def`.
**Not for**: CLI scripts or Jupyter (use `LocalRuntime`).

```python
from kailash.runtime import AsyncLocalRuntime, LocalRuntime, get_runtime

runtime = AsyncLocalRuntime()          # Initialize ONCE at module level
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})

sync_runtime = LocalRuntime()          # Sync context (CLI/scripts)
results, run_id = sync_runtime.execute(workflow.build())

runtime = get_runtime()               # Auto-detect: Async for Docker, Local for CLI
```

**Mistakes**: Creating runtime per request (overhead) | LocalRuntime in async (blocks event loop) | Mixing sync `.execute()` in async context

## Pattern 10: MCP Integration

Every `@app.handler()` automatically becomes an MCP tool.

**Use when**: AI agent integrations (Claude, GPT), tool-using scenarios.

```python
app = Nexus(api_port=8000, mcp_port=3001, auto_discovery=False)

@app.handler("search_contacts", description="Search contacts by company or email")
async def search_contacts(company: str = None, email_pattern: str = None, limit: int = 10) -> dict:
    filters = {}
    if company: filters["company"] = {"$regex": company}
    if email_pattern: filters["email"] = {"$regex": email_pattern}
    return {"contacts": await query_contacts(filters, limit)}

app.start()  # API at :8000, MCP at ws://:3001
```

**Mistakes**: No descriptions (AI agents need them) | Complex return types (keep simple dicts) | Missing parameter defaults (optional params need defaults)

## Quick Reference

| Pattern              | Use Case        | Key Import                                             | Location               |
| -------------------- | --------------- | ------------------------------------------------------ | ---------------------- |
| 1. Handler           | API endpoints   | `from nexus import Nexus`                              | `app/handlers/`        |
| 2. DataFlow Model    | DB entities     | `from dataflow import DataFlow`                        | `app/models/`          |
| 3. Nexus+DataFlow    | API+DB          | Both above                                             | `app/main.py`          |
| 4. Auth Stack        | Authentication  | `from nexus.auth.plugin import NexusAuthPlugin`        | `app/auth/`            |
| 5. Multi-DataFlow    | Multiple DBs    | `from dataflow import DataFlow`                        | `app/core/database.py` |
| 6. Custom Node       | Reusable logic  | `from kailash.nodes.base import Node`                  | `app/nodes/`           |
| 7. Kaizen Agent      | AI features     | `from kaizen.core.base_agent import BaseAgent`         | `app/agents/`          |
| 8. Workflow Builder  | Orchestration   | `from kailash.workflow.builder import WorkflowBuilder` | `app/workflows/`       |
| 9. AsyncLocalRuntime | Async execution | `from kailash.runtime import AsyncLocalRuntime`        | `app/core/runtime.py`  |
| 10. MCP Integration  | AI tools        | `from nexus import Nexus`                              | `app/mcp/`             |
