# Top 10 Kailash Patterns

**Purpose**: Definitive reference for codegen agents selecting implementation patterns. Ranked by usage frequency across three production projects: enterprise-app (218K LOC), example-project (89K LOC), example-backend (75K LOC).

**Version**: 0.12.0
**Last Updated**: 2026-02-09

---

## Pattern 1: Nexus Handler Pattern

**One-line**: Register async functions as multi-channel endpoints (API + CLI + MCP) with a single decorator.

### When to Use

- Building REST API endpoints that need database access
- Service orchestration requiring async I/O (HTTP clients, databases)
- Full Python access needed (sandbox-blocked imports like `asyncio`, `httpx`)

### When NOT to Use

- Complex multi-step orchestration with branching (use WorkflowBuilder)
- Data transformation pipelines without side effects (use Core SDK workflow)

### Canonical Example

```python
from nexus import Nexus
from dataflow import DataFlow

app = Nexus(auto_discovery=False)
db = DataFlow(os.environ["DATABASE_URL"], enable_model_persistence=False)

@db.model
class User:
    id: str
    email: str
    name: str

@app.handler("create_user", description="Create a new user")
async def create_user(email: str, name: str) -> dict:
    """Handler for user creation - full Python access, no sandbox."""
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime import AsyncLocalRuntime
    import uuid

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "id": f"user-{uuid.uuid4()}",
        "email": email,
        "name": name
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]

app.start()
```

### Common Mistakes

- **Using PythonCodeNode for business logic**: Sandbox blocks `asyncio`, `httpx`, database drivers. Use `@app.handler()` instead.
- **Forgetting type annotations**: Handler parameters without types default to `str`, losing validation.
- **Returning non-dict**: Returns like `"success"` get wrapped as `{"result": "success"}`. Return explicit dicts.

### Real Project Evidence

- **enterprise-app**: 97 service handlers across `backend/app/services/` use this pattern
- **example-project**: 21 Nexus handlers in `backend/gateways/`
- **example-backend**: Migrated from FastAPI routes to handlers in `app/api/v2/`

---

## Pattern 2: DataFlow Model Pattern

**One-line**: Define Python classes with `@db.model` to auto-generate 9 CRUD workflow nodes.

### When to Use

- Any database table/entity definition
- Need Create, Read, Update, Delete, List, Bulk operations
- Want MongoDB-style query syntax across PostgreSQL/MySQL/SQLite

### When NOT to Use

- Document databases without fixed schema (use raw MongoDB client)
- Read-only data sources (no CRUD needed)

### Canonical Example

```python
from dataflow import DataFlow
from typing import Optional
from datetime import datetime

db = DataFlow(os.environ["DATABASE_URL"])

@db.model
class User:
    id: str                           # Primary key (MUST be named 'id')
    email: str                        # Required field
    name: str                         # Required field
    role: str = "member"              # Default value
    active: bool = True               # Default boolean
    created_at: datetime = None       # Auto-managed by DataFlow
    org_id: Optional[str] = None      # Optional foreign key

# Auto-generates 9 nodes:
# - UserCreateNode, UserReadNode, UserUpdateNode, UserDeleteNode
# - UserListNode
# - UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode
```

### Common Mistakes

- **Primary key not named `id`**: DataFlow requires `id` as the primary key name.
- **Manually setting `created_at`/`updated_at`**: These are auto-managed. Never set them.
- **Using `user.save()` ORM pattern**: DataFlow is NOT an ORM. Use workflow nodes.

### Real Project Evidence

- **enterprise-app**: 96 models in `backend/app/models/`
- **example-project**: 34 models across domain modules
- **example-backend**: 7 DataFlow instances with 45 total models

---

## Pattern 3: Nexus + DataFlow Integration

**One-line**: Wire DataFlow operations to Nexus endpoints with CRITICAL configuration to prevent blocking.

### When to Use

- Any API that reads/writes database
- SaaS backends with CRUD operations
- Multi-tenant applications

### When NOT to Use

- Standalone CLI tools (use DataFlow directly)
- Batch processing jobs (use Core SDK runtime)

### Canonical Example

```python
from nexus import Nexus
from dataflow import DataFlow
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime
import uuid

# CRITICAL: These settings prevent blocking and slow startup
app = Nexus(
    api_port=8000,
    auto_discovery=False  # CRITICAL: Prevents filesystem scanning
)

db = DataFlow(
    database_url=os.environ["DATABASE_URL"],
    enable_model_persistence=False,  # CRITICAL: Prevents 5-10s delay per model
    auto_migrate=False                # CRITICAL: Prevents async deadlock in Docker
)

@db.model
class Contact:
    id: str
    email: str
    name: str
    company_id: str

@app.handler("create_contact")
async def create_contact(email: str, name: str, company_id: str) -> dict:
    workflow = WorkflowBuilder()
    workflow.add_node("ContactCreateNode", "create", {
        "id": f"contact-{uuid.uuid4()}",
        "email": email,
        "name": name,
        "company_id": company_id
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return results["create"]

@app.handler("list_contacts")
async def list_contacts(company_id: str, limit: int = 20) -> dict:
    workflow = WorkflowBuilder()
    workflow.add_node("ContactListNode", "list", {
        "filter": {"company_id": company_id},
        "limit": limit,
        "order_by": ["-created_at"]
    })

    runtime = AsyncLocalRuntime()
    results, _ = await runtime.execute_workflow_async(workflow.build(), inputs={})
    return {"contacts": results["list"]["items"]}

app.start()
```

### Common Mistakes

- **Missing `auto_discovery=False`**: Causes infinite blocking on startup with DataFlow.
- **Missing `enable_model_persistence=False`**: Adds 5-10 seconds per model registration.
- **Using `auto_migrate=True` in Docker/FastAPI**: Causes async event loop deadlock.

### Real Project Evidence

- **enterprise-app**: Uses this exact pattern in `backend/main.py`
- **example-project**: 21 gateways each follow this configuration
- **example-backend**: Critical fix applied in `app/core/database.py`

---

## Pattern 4: Auth Middleware Stack

**One-line**: JWT verification + RBAC permissions + tenant isolation via NexusAuthPlugin.

### When to Use

- Production APIs requiring authentication
- Multi-tenant SaaS platforms
- Role-based access control requirements

### When NOT to Use

- Public APIs with no auth
- Internal microservices with network-level security only

### Canonical Example

```python
from nexus import Nexus
from nexus.plugins.auth import NexusAuthPlugin, JWTConfig, RBACConfig

app = Nexus(auto_discovery=False)

# Configure auth plugin
auth = NexusAuthPlugin(
    jwt=JWTConfig(
        secret_key=os.environ["JWT_SECRET"],
        algorithm="HS256",
        access_token_expire_minutes=30,
        refresh_token_expire_days=7
    ),
    rbac=RBACConfig(
        roles={
            "admin": ["users:*", "contacts:*", "billing:*"],
            "member": ["contacts:read", "contacts:create"],
            "viewer": ["contacts:read"]
        }
    ),
    tenant_isolation=True  # Auto-scope all queries by org_id
)

app.add_plugin(auth)

@app.handler("create_contact")
@auth.require_permission("contacts:create")
async def create_contact(email: str, name: str, request: Request) -> dict:
    # request.state.user contains verified JWT claims
    # request.state.org_id contains tenant ID (auto-scoped)
    user_id = request.state.user["sub"]
    org_id = request.state.org_id

    # DataFlow queries auto-filtered by org_id when tenant_isolation=True
    return await create_contact_in_db(email, name, org_id, created_by=user_id)

app.start()
```

### Common Mistakes

- **Hardcoding JWT secret**: Always use environment variables (`os.environ["JWT_SECRET"]`).
- **Missing tenant isolation in queries**: Without plugin, must manually filter by `org_id`.
- **Checking roles instead of permissions**: Use fine-grained `contacts:create` not `role == "admin"`.

### Real Project Evidence

- **enterprise-app**: 150+ lines JWT middleware in `backend/app/middleware/auth.py`
- **example-project**: 250+ lines RBAC in `backend/middleware/rbac.py`
- **example-backend**: 294 lines tenant isolation in `app/middleware/tenant.py`

---

## Pattern 5: Multi-DataFlow Instance Pattern

**One-line**: Separate DataFlow instances per database/domain for isolation and scalability.

### When to Use

- Multiple databases (users DB, analytics DB, logs DB)
- Microservice boundaries within a monolith
- Read replicas vs write primary separation

### When NOT to Use

- Single database applications
- Tightly coupled domains sharing transactions

### Canonical Example

```python
from dataflow import DataFlow
import os

# Primary database for transactional data
users_db = DataFlow(
    database_url=os.environ["PRIMARY_DATABASE_URL"],
    enable_model_persistence=False,
    auto_migrate=False
)

# Analytics database (read-heavy, different optimization)
analytics_db = DataFlow(
    database_url=os.environ["ANALYTICS_DATABASE_URL"],
    enable_model_persistence=False,
    auto_migrate=False,
    pool_size=30  # Higher pool for read-heavy workload
)

# Logs database (append-only, high throughput)
logs_db = DataFlow(
    database_url=os.environ["LOGS_DATABASE_URL"],
    enable_model_persistence=False,
    auto_migrate=False,
    echo=False  # Disable SQL logging for performance
)

# Models are scoped to their database instance
@users_db.model
class User:
    id: str
    email: str
    name: str

@analytics_db.model
class PageView:
    id: str
    user_id: str
    page: str
    timestamp: datetime

@logs_db.model
class AuditLog:
    id: str
    action: str
    actor_id: str
    resource: str
    timestamp: datetime

# Initialize all databases at startup
async def initialize_databases():
    await users_db.create_tables_async()
    await analytics_db.create_tables_async()
    await logs_db.create_tables_async()
```

### Common Mistakes

- **One DataFlow for all databases**: Loses connection pool optimization per workload.
- **Sharing models across instances**: Models are bound to their `@db.model` decorator's instance.
- **Forgetting initialization order**: Initialize in dependency order (users before logs).

### Real Project Evidence

- **example-backend**: 7 DataFlow instances in `app/core/database.py` (users, itineraries, bookings, reviews, notifications, analytics, audit)
- **enterprise-app**: 3 instances (primary, analytics, cache)
- **example-project**: 2 instances (main, reporting)

---

## Pattern 6: Custom Node Pattern

**One-line**: Extend SDK with project-specific logic as reusable workflow nodes.

### When to Use

- Repeated logic across multiple workflows (API calls, transformations)
- Third-party integrations (payment gateways, notification services)
- Domain-specific calculations (pricing, scoring algorithms)

### When NOT to Use

- One-off logic (use `@app.handler()` instead)
- Simple transformations (use built-in TransformNode)

### Canonical Example

```python
from kailash.nodes.base import Node, NodeParameter, register_node

@register_node("SendgridEmailNode")
class SendgridEmailNode(Node):
    """Custom node for sending emails via Sendgrid API."""

    @classmethod
    def get_parameters(cls) -> list[NodeParameter]:
        return [
            NodeParameter(name="to_email", type=str, required=True),
            NodeParameter(name="subject", type=str, required=True),
            NodeParameter(name="template_id", type=str, required=True),
            NodeParameter(name="template_data", type=dict, required=False, default={}),
        ]

    async def execute(self, **kwargs) -> dict:
        import httpx
        import os

        api_key = os.environ["SENDGRID_API_KEY"]

        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.sendgrid.com/v3/mail/send",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "personalizations": [{
                        "to": [{"email": kwargs["to_email"]}],
                        "dynamic_template_data": kwargs.get("template_data", {})
                    }],
                    "from": {"email": "noreply@example.com"},
                    "subject": kwargs["subject"],
                    "template_id": kwargs["template_id"]
                }
            )

        return {
            "success": response.status_code == 202,
            "status_code": response.status_code
        }

# Usage in workflow
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("SendgridEmailNode", "send_welcome", {
    "to_email": "user@example.com",
    "subject": "Welcome!",
    "template_id": "d-abc123",
    "template_data": {"name": "Alice"}
})
```

### Common Mistakes

- **Not using `@register_node()`**: Required for string-based node references in workflows.
- **Blocking I/O in execute()**: Always use `async with httpx.AsyncClient()` not `requests`.
- **Missing required parameters**: Define all parameters with proper `required` flag.

### Real Project Evidence

- **example-project**: 13 custom nodes in `backend/nodes/` (payment, notification, analytics)
- **enterprise-app**: 8 custom nodes for integrations (Slack, Stripe, Twilio)
- **example-backend**: 17 custom nodes in `app/nodes/` (booking, maps, weather)

---

## Pattern 7: Kaizen Agent Pattern

**One-line**: AI agent with MCP tools, structured outputs, and automatic execution strategies.

### When to Use

- LLM-powered features (chat, analysis, summarization)
- Tool-using agents (file operations, API calls)
- Multi-step reasoning tasks

### When NOT to Use

- Simple string templating (use format strings)
- Deterministic data processing (use workflows)

### Canonical Example

```python
from kaizen.core.base_agent import BaseAgent
from kaizen.signatures import Signature, InputField, OutputField
from dataclasses import dataclass

@dataclass
class AnalysisConfig:
    llm_provider: str = "openai"
    model: str = "gpt-4"
    temperature: float = 0.1
    max_tokens: int = 2000

class AnalysisSignature(Signature):
    """Signature defines type-safe inputs and outputs."""
    document: str = InputField(description="Document text to analyze")
    question: str = InputField(description="Analysis question")

    answer: str = OutputField(description="Analysis answer")
    confidence: float = OutputField(description="Confidence score 0.0-1.0")
    citations: list = OutputField(description="Supporting quotes from document")

class DocumentAnalyzer(BaseAgent):
    """Agent for document analysis with structured outputs."""

    def __init__(self, config: AnalysisConfig):
        super().__init__(config=config, signature=AnalysisSignature())

    async def analyze(self, document: str, question: str) -> dict:
        """Analyze document and return structured result."""
        result = await self.run_async(document=document, question=question)

        # Validate confidence
        if result.get("confidence", 0) < 0.5:
            result["warning"] = "Low confidence - consider manual review"

        return result

# Usage
async def main():
    config = AnalysisConfig()
    analyzer = DocumentAnalyzer(config)

    result = await analyzer.analyze(
        document="Quarterly revenue increased 15% YoY...",
        question="What was the revenue growth?"
    )
    print(f"Answer: {result['answer']}")
    print(f"Confidence: {result['confidence']}")
```

### Common Mistakes

- **Creating BaseAgentConfig manually**: Let BaseAgent auto-convert domain configs.
- **Calling strategy.execute() directly**: Always use `self.run()` or `self.run_async()`.
- **Missing `.env` file**: Must load `load_dotenv()` before creating agents.

### Real Project Evidence

- **enterprise-app**: 23 Kaizen agents for various analysis tasks
- **example-project**: Research agent, summarization agent, Q&A agent
- **example-backend**: Trip planning agent, recommendation agent

---

## Pattern 8: Workflow Builder Pattern

**One-line**: Multi-step orchestrated workflows with branching, cycles, and complex data flows.

### When to Use

- Multi-step pipelines (ETL, approval flows)
- Conditional branching (SwitchNode for business rules)
- Cyclic workflows (retry loops, iterative refinement)
- Connecting multiple nodes with data dependencies

### When NOT to Use

- Single-step operations (use `@app.handler()`)
- Simple CRUD without orchestration (use DataFlow directly)

### Canonical Example

```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime

def build_order_processing_workflow():
    """Multi-step order processing with validation and notification."""
    workflow = WorkflowBuilder()

    # Step 1: Validate order
    workflow.add_node("PythonCodeNode", "validate", {
        "code": """
result = {
    "valid": order["quantity"] > 0 and order["price"] > 0,
    "order": order
}
"""
    })

    # Step 2: Check inventory (only if valid)
    workflow.add_node("InventoryCheckNode", "check_inventory", {
        "product_id": None  # Connected from validate
    })

    # Step 3: Create order in database
    workflow.add_node("OrderCreateNode", "create_order", {
        "product_id": None,
        "quantity": None,
        "price": None,
        "status": "confirmed"
    })

    # Step 4: Send confirmation email
    workflow.add_node("SendgridEmailNode", "send_confirmation", {
        "to_email": None,
        "subject": "Order Confirmed",
        "template_id": "d-order-confirmed"
    })

    # Wire connections (explicit data flow)
    workflow.add_connection("validate", "order.product_id", "check_inventory", "product_id")
    workflow.add_connection("validate", "order.product_id", "create_order", "product_id")
    workflow.add_connection("validate", "order.quantity", "create_order", "quantity")
    workflow.add_connection("validate", "order.price", "create_order", "price")
    workflow.add_connection("validate", "order.customer_email", "send_confirmation", "to_email")

    return workflow

# Execute
async def process_order(order: dict):
    workflow = build_order_processing_workflow()
    runtime = AsyncLocalRuntime()
    results, run_id = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={"order": order}
    )
    return results
```

### Common Mistakes

- **Forgetting `.build()`**: Must call `workflow.build()` before `runtime.execute()`.
- **Using template syntax `${...}`**: Use `add_connection()` for data flow, not string interpolation.
- **Missing runtime**: Always create runtime before execution.

### Real Project Evidence

- **enterprise-app**: 47 complex workflows in `backend/workflows/`
- **example-project**: ETL pipelines, approval workflows
- **example-backend**: Booking flow with 7 steps

---

## Pattern 9: AsyncLocalRuntime Pattern

**One-line**: Async-first execution for Docker/FastAPI with proper event loop handling.

### When to Use

- FastAPI endpoints
- Docker deployments
- Concurrent request handling
- Any async context (`async def`)

### When NOT to Use

- CLI scripts (use `LocalRuntime`)
- Jupyter notebooks (use `LocalRuntime`)
- Sync-only code

### Canonical Example

```python
from kailash.runtime import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder
from fastapi import FastAPI
from contextlib import asynccontextmanager

# Initialize runtime once (not per request!)
runtime = AsyncLocalRuntime()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: nothing needed for AsyncLocalRuntime
    yield
    # Shutdown: cleanup if needed
    pass

app = FastAPI(lifespan=lifespan)

@app.post("/process")
async def process_data(data: dict):
    workflow = WorkflowBuilder()
    workflow.add_node("TransformNode", "transform", {
        "data": data,
        "operation": "normalize"
    })

    # AsyncLocalRuntime handles event loop correctly
    results, run_id = await runtime.execute_workflow_async(
        workflow.build(),
        inputs={}
    )

    return {"result": results["transform"], "run_id": run_id}
```

### Common Mistakes

- **Creating runtime per request**: Creates overhead. Initialize once at module level.
- **Using LocalRuntime in async context**: Blocks event loop. Use AsyncLocalRuntime.
- **Mixing sync and async**: Use `await runtime.execute_workflow_async()` not `.execute()`.

### Real Project Evidence

- **enterprise-app**: All 97 services use AsyncLocalRuntime
- **example-project**: Migrated from LocalRuntime after performance issues
- **example-backend**: Standard pattern in `app/core/runtime.py`

---

## Pattern 10: MCP Integration Pattern

**One-line**: Expose workflows as MCP tools for AI agent consumption.

### When to Use

- AI agent integrations (Claude, GPT agents)
- Tool-using scenarios
- Automated workflows triggered by AI

### When NOT to Use

- Human-only APIs
- Simple REST endpoints without AI integration

### Canonical Example

```python
from nexus import Nexus

app = Nexus(
    api_port=8000,
    mcp_port=3001,  # MCP server on separate port
    auto_discovery=False
)

# Every registered handler automatically becomes an MCP tool
@app.handler("search_contacts", description="Search contacts by company or email")
async def search_contacts(
    company: str = None,
    email_pattern: str = None,
    limit: int = 10
) -> dict:
    """
    Search contacts in the database.

    Args:
        company: Filter by company name (partial match)
        email_pattern: Filter by email pattern
        limit: Maximum results to return

    Returns:
        List of matching contacts
    """
    filters = {}
    if company:
        filters["company"] = {"$regex": company}
    if email_pattern:
        filters["email"] = {"$regex": email_pattern}

    # Query database
    results = await query_contacts(filters, limit)
    return {"contacts": results, "count": len(results)}

# MCP tool automatically available as:
# - Tool name: workflow_search_contacts
# - Parameters derived from function signature
# - Description from docstring

# For custom MCP tools (not backed by handler):
@app.mcp_tool("calculate_metrics", description="Calculate business metrics")
async def calculate_metrics(metric_type: str, date_range: dict) -> dict:
    """Custom MCP tool for AI agents."""
    return await compute_metrics(metric_type, date_range)

app.start()
# MCP tools available at ws://localhost:3001
```

### Common Mistakes

- **No descriptions**: AI agents need descriptions to understand tool purpose.
- **Complex return types**: Keep returns as simple dicts for AI parsing.
- **Missing parameter defaults**: Optional params should have defaults for AI flexibility.

### Real Project Evidence

- **enterprise-app**: 45 MCP tools exposed for internal AI agents
- **example-project**: Research tools for document analysis agents
- **example-backend**: Trip planning tools for recommendation agent

---

## Quick Reference Table

| Pattern              | Primary Use Case  | Key Import                                             | File Location          |
| -------------------- | ----------------- | ------------------------------------------------------ | ---------------------- |
| 1. Handler           | API endpoints     | `from nexus import Nexus`                              | `app/handlers/`        |
| 2. DataFlow Model    | Database entities | `from dataflow import DataFlow`                        | `app/models/`          |
| 3. Nexus+DataFlow    | API+Database      | Both above                                             | `app/main.py`          |
| 4. Auth Stack        | Authentication    | `from nexus.plugins.auth import NexusAuthPlugin`       | `app/auth/`            |
| 5. Multi-DataFlow    | Multiple DBs      | `from dataflow import DataFlow`                        | `app/core/database.py` |
| 6. Custom Node       | Reusable logic    | `from kailash.nodes.base import Node`                  | `app/nodes/`           |
| 7. Kaizen Agent      | AI features       | `from kaizen.core.base_agent import BaseAgent`         | `app/agents/`          |
| 8. Workflow Builder  | Orchestration     | `from kailash.workflow.builder import WorkflowBuilder` | `app/workflows/`       |
| 9. AsyncLocalRuntime | Async execution   | `from kailash.runtime import AsyncLocalRuntime`        | `app/core/runtime.py`  |
| 10. MCP Integration  | AI tools          | `from nexus import Nexus`                              | `app/mcp/`             |

---

## Critical Configuration Summary

```python
# ALWAYS use these settings for Nexus + DataFlow

app = Nexus(
    auto_discovery=False,  # CRITICAL: Prevents blocking
)

db = DataFlow(
    database_url="...",
    enable_model_persistence=False,  # CRITICAL: Fast startup
    auto_migrate=False,              # CRITICAL: Docker-safe
)

# ALWAYS use AsyncLocalRuntime in FastAPI/async contexts
runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(workflow.build(), inputs={})

# ALWAYS use type annotations in handlers
@app.handler("my_handler")
async def my_handler(required_param: str, optional_param: int = 10) -> dict:
    return {"result": "..."}
```
