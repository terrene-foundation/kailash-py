# 10 Golden Patterns Specification

**Purpose:** Reduce 246 skills to 10 essential patterns that solve 80% of use cases

**Priority:** 1 (Critical - Must define before templates)
**Estimated Effort:** 40 hours
**Timeline:** Weeks 1-2

---

## Executive Summary

**What:** 10 copy-paste ready patterns covering the most common Kailash use cases

**Why:** 246 skills overwhelming for AI assistants - leads to token waste and slow navigation

**How:** Curate the 20% of patterns that solve 80% of problems, embed in template code

**Success Criteria:** 80% of AI-assisted customizations use Golden Patterns, not full 246 skills

---

## The Problem

### Current State: 246 Skills

**Skill Categories (17 categories):**
```
01-core-sdk/           (14 skills)
02-dataflow/           (12 skills)
03-nexus/              (8 skills)
04-kaizen/             (15 skills)
05-mcp/                (10 skills)
06-cheatsheets/        (20 skills)
07-development-guides/ (45 skills)
08-nodes-reference/    (30 skills)
09-workflow-patterns/  (25 skills)
10-deployment-git/     (8 skills)
11-frontend-integration/ (6 skills)
12-testing-strategies/ (12 skills)
13-architecture-decisions/ (8 skills)
14-code-templates/     (7 skills)
15-error-troubleshooting/ (10 skills)
16-validation-patterns/ (8 skills)
17-gold-standards/     (8 skills)

Total: 246 skills
```

**Problem for AI Assistants:**
- Must navigate all 246 to find relevant pattern
- Token consumption: 5K-20K before finding answer
- Often picks wrong pattern (too many choices)
- Slow response time (30+ seconds to navigate)

**User Impact:**
- 48-hour debugging sessions
- Overcomplicated solutions (agent found advanced pattern when simple would work)
- Token waste

---

## The Solution: 10 Golden Patterns

### Pattern Selection Criteria

**Included IF:**
1. ✅ Used in 80%+ of projects
2. ✅ Solves complete use case (not partial)
3. ✅ Copy-paste ready (minimal customization)
4. ✅ Works across databases (PostgreSQL, MySQL, SQLite)
5. ✅ Addresses common mistakes (prevents errors)

**Excluded IF:**
1. ❌ Niche use case (<20% of projects)
2. ❌ Requires deep SDK knowledge
3. ❌ Advanced optimization (not needed for MVP)
4. ❌ Database-specific (PostgreSQL-only features)

### Usage Analysis (from Current 246 Skills)

**Top 20 Most-Referenced Skills:**
1. DataFlow CRUD operations (used in 95% of projects)
2. Workflow creation basics (used in 100% of projects)
3. Nexus registration (used in 80% of projects)
4. Error handling (used in 70% of projects)
5. Parameter passing (used in 90% of projects)
6. Multi-tenancy setup (used in 60% of SaaS projects)
7. External API integration (used in 65% of projects)
8. Authentication patterns (used in 85% of projects)
9. Background jobs (used in 50% of projects)
10. File operations (used in 55% of projects)

**Bottom 20 (Rarely Used):**
- Edge computing patterns (<5%)
- Distributed transactions (<10%)
- Custom runtime development (<2%)
- Advanced cyclic workflows (<15%)
- Circuit breaker patterns (<20%)

**Decision:** Focus on top 10, keep full docs for rare cases

---

## The 10 Golden Patterns

### Pattern 1: Add a DataFlow Model (95% usage)

**File:** Embedded in template `models/example.py`

```python
"""
GOLDEN PATTERN #1: Add a DataFlow Model
========================================

Use this when you need to store data in the database.

DataFlow auto-generates 9 workflow nodes per model:
  1. {Model}CreateNode - Create single record
  2. {Model}ReadNode - Read by ID
  3. {Model}UpdateNode - Update record
  4. {Model}DeleteNode - Delete record
  5. {Model}ListNode - Query multiple records
  6. {Model}BulkCreateNode - Batch create
  7. {Model}BulkUpdateNode - Batch update
  8. {Model}BulkDeleteNode - Batch delete
  9. {Model}BulkUpsertNode - Batch upsert

COPY THIS PATTERN:
"""

from dataflow import DataFlow
from datetime import datetime
from typing import Optional

db = DataFlow("postgresql://...")  # From env: DATABASE_URL

@db.model
class Product:  # ← Change model name
    """Product catalog model.

    Fields are defined with type hints:
    - str, int, float, bool: Basic types
    - Optional[str]: Optional field (can be None)
    - datetime: Auto-managed if not provided
    """
    # Required fields (no default value)
    id: str                    # Primary key (MUST be named 'id')
    name: str                  # Product name
    price: float               # Product price

    # Optional fields (have default values)
    description: Optional[str] = None  # Optional description
    is_available: bool = True          # Default to available
    stock: int = 0                     # Default to 0 stock

    # Auto-managed fields (DON'T include in create/update)
    # created_at: datetime  # Added automatically
    # updated_at: datetime  # Added automatically

    # Multi-tenant field (added automatically if multi_tenant=True)
    # tenant_id: str  # Added by DataFlow

"""
USAGE IN WORKFLOW:

from kailash.workflow.builder import WorkflowBuilder
from kailash_dataflow_utils import UUIDField  # Prevents ID errors

workflow = WorkflowBuilder()

# Create product
workflow.add_node("ProductCreateNode", "create", {
    "id": UUIDField.generate(),  # Generate UUID
    "name": "Widget",
    "price": 9.99,
    "description": "A useful widget",
    "is_available": True
})

# Read product
workflow.add_node("ProductReadNode", "read", {
    "id": "product-uuid-here"
})

# Update product
workflow.add_node("ProductUpdateNode", "update", {
    "filter": {"id": "product-uuid-here"},  # ← Note: UpdateNode uses filter
    "fields": {"price": 12.99}              # ← and fields (not flat)
})

# List products
workflow.add_node("ProductListNode", "list", {
    "filters": {"is_available": True},
    "limit": 10
})
"""

"""
COMMON MISTAKES (AVOID):

❌ Using user_id instead of id:
   class User:
       user_id: str  # WRONG - must be 'id'

❌ Including created_at/updated_at:
   workflow.add_node("UserCreateNode", "create", {
       "name": "Alice",
       "created_at": datetime.now()  # WRONG - auto-managed
   })

❌ Using .isoformat() for datetime:
   "updated_at": datetime.now().isoformat()  # WRONG - returns string
   "updated_at": datetime.now()  # CORRECT - datetime object

❌ Wrong UpdateNode pattern:
   workflow.add_node("UserUpdateNode", "update", {
       "id": "user-123",  # WRONG - UpdateNode uses filter/fields
       "name": "New Name"
   })

   workflow.add_node("UserUpdateNode", "update", {
       "filter": {"id": "user-123"},  # CORRECT
       "fields": {"name": "New Name"}
   })
"""
```

### Pattern 2: Create a Workflow (100% usage)

**File:** Embedded in template `workflows/example_workflow.py`

```python
"""
GOLDEN PATTERN #2: Create a Workflow
====================================

Use this to define multi-step business logic.

Workflows connect nodes to create data pipelines.

COPY THIS PATTERN:
"""

from kailash.workflow.builder import WorkflowBuilder

def create_user_workflow():
    """Example: Create user and send welcome email."""

    workflow = WorkflowBuilder()

    # Step 1: Create user in database
    workflow.add_node("UserCreateNode", "create_user", {
        "id": "{{ user_id }}",  # Template variable (filled at runtime)
        "name": "{{ name }}",
        "email": "{{ email }}"
    })

    # Step 2: Send welcome email
    workflow.add_node("EmailSendNode", "send_welcome", {
        "to": "{{ email }}",
        "subject": "Welcome to our platform!",
        "body": "Hi {{ name }}, welcome aboard!"
    })

    # Step 3: Log event
    workflow.add_node("LogNode", "log_registration", {
        "message": "User {{ name }} registered successfully",
        "level": "info"
    })

    # Connect nodes (defines execution order)
    workflow.add_connection("create_user", "send_welcome", "output", "input")
    workflow.add_connection("send_welcome", "log_registration", "output", "input")

    # CRITICAL: Always call .build()
    return workflow.build()

"""
USAGE:

# In main.py
from nexus import Nexus
from workflows.example_workflow import create_user_workflow

nexus = Nexus()
nexus.register("create_user", create_user_workflow())

# Now available on all channels:
# - API: POST /workflows/create_user
# - CLI: nexus run create_user --user_id=... --name=... --email=...
# - MCP: create_user(user_id="...", name="...", email="...")
"""

"""
COMMON MISTAKES (AVOID):

❌ Forgetting .build():
   return workflow  # WRONG
   return workflow.build()  # CORRECT

❌ Wrong connection syntax:
   workflow.connect("node1", "node2")  # WRONG - no such method

   workflow.add_connection(
       "node1", "node2",
       "output", "input"  # CORRECT - specify ports
   )

❌ Creating workflow inside function call:
   nexus.register("name", WorkflowBuilder().add_node(...))  # WRONG - incomplete

   workflow = WorkflowBuilder()
   workflow.add_node(...)
   nexus.register("name", workflow.build())  # CORRECT
"""
```

### Pattern 3: Deploy with Nexus (80% usage)

**File:** Embedded in template `main.py`

```python
"""
GOLDEN PATTERN #3: Deploy with Nexus
====================================

Use this to deploy workflows as API + CLI + MCP simultaneously.

Nexus is zero-config multi-channel deployment.

COPY THIS PATTERN:
"""

from nexus import Nexus
from workflows import user_workflows, admin_workflows

# AI INSTRUCTION: Nexus deployment is simple:
# 1. Initialize Nexus
# 2. Register workflows
# 3. Call nexus.start()

# Initialize (zero-config for development)
nexus = Nexus(
    api_port=8000,      # API server port
    mcp_port=3001,      # MCP server port (for AI agents)
    enable_auth=False,  # Set True for production
    enable_monitoring=False  # Set True for production
)

# Or use presets:
# nexus = Nexus.for_development()  # Quick defaults
# nexus = Nexus.for_production()   # Enterprise features
# nexus = Nexus.for_saas()         # SaaS-optimized

# Register workflows (each becomes available on all channels)
nexus.register("create_user", user_workflows.create_user)
nexus.register("get_user", user_workflows.get_user)
nexus.register("list_users", admin_workflows.list_users)

# AI INSTRUCTION: To add a new endpoint:
# 1. Create workflow in workflows/ directory
# 2. Register with nexus.register(name, workflow)
# 3. Automatically available on API, CLI, MCP

# Start all channels
if __name__ == "__main__":
    nexus.start()

    # Output:
    # ✅ API: http://localhost:8000
    # ✅ MCP: stdio://localhost:3001
    # ✅ 3 workflows registered

"""
CONFIGURATION PRESETS:

# Development (fast iteration)
nexus = Nexus.for_development()
# - No auth
# - No monitoring
# - No durability (faster)
# - Debug mode ON

# Production (enterprise features)
nexus = Nexus.for_production()
# - Auth required
# - Monitoring enabled
# - Durability enabled
# - Rate limiting

# SaaS (multi-tenant)
nexus = Nexus.for_saas()
# - All production features
# - Rate limiting: 1000 req/min
# - Multi-tenant ready
"""

"""
COMMON MISTAKES (AVOID):

❌ Not calling .start():
   nexus.register("workflow", wf)
   # Missing: nexus.start()

❌ Calling .build() on already-built workflow:
   workflow = create_workflow()  # Already returns workflow.build()
   nexus.register("name", workflow.build())  # WRONG - double build

   nexus.register("name", create_workflow())  # CORRECT

❌ Starting multiple Nexus instances:
   nexus1 = Nexus(api_port=8000)
   nexus2 = Nexus(api_port=8000)  # WRONG - port conflict

   # Use one Nexus instance for all workflows
"""
```

### Pattern 4: External API Integration (65% usage)

```python
"""
GOLDEN PATTERN #4: External API Integration
===========================================

Use this to call external APIs (Stripe, SendGrid, Slack, etc.).

COPY THIS PATTERN:
"""

from kailash.workflow.builder import WorkflowBuilder

def call_stripe_api_workflow():
    """Example: Create Stripe customer."""

    workflow = WorkflowBuilder()

    # Step 1: Call Stripe API
    workflow.add_node("HTTPRequestNode", "create_customer", {
        "url": "https://api.stripe.com/v1/customers",
        "method": "POST",
        "headers": {
            "Authorization": "Bearer {{ stripe_api_key }}",  # From env or input
            "Content-Type": "application/x-www-form-urlencoded"
        },
        "body": {
            "email": "{{ customer_email }}",
            "name": "{{ customer_name }}",
            "metadata[user_id]": "{{ user_id }}"
        }
    })

    # Step 2: Save Stripe customer ID to database
    workflow.add_node("SubscriptionCreateNode", "save_subscription", {
        "user_id": "{{ user_id }}",
        "stripe_customer_id": "{{ create_customer.id }}",  # Reference previous node
        "status": "active"
    })

    # Connect steps
    workflow.add_connection("create_customer", "save_subscription", "output", "input")

    return workflow.build()

"""
NODE REFERENCE FOR APIs:

HTTPRequestNode - General HTTP requests
  - method: GET, POST, PUT, DELETE, PATCH
  - url: Full URL
  - headers: Dict of headers
  - body: Request body (dict or string)
  - auth: Optional authentication

WebhookNode - Handle incoming webhooks
  - path: Webhook path
  - validation: Signature validation

GraphQLNode - GraphQL queries
  - endpoint: GraphQL endpoint
  - query: GraphQL query string
  - variables: Query variables
"""

"""
COMMON INTEGRATIONS:

# Stripe (payments)
HTTPRequestNode → https://api.stripe.com/v1/

# SendGrid (email)
HTTPRequestNode → https://api.sendgrid.com/v3/

# Slack (notifications)
HTTPRequestNode → https://slack.com/api/

# Twilio (SMS)
HTTPRequestNode → https://api.twilio.com/

# For pre-built integrations:
pip install kailash-payments  # Stripe, PayPal
pip install kailash-notifications  # Email, SMS, Push
"""
```

### Pattern 5: Authentication Workflow (85% usage)

```python
"""
GOLDEN PATTERN #5: Authentication Workflow
==========================================

Use this for user login/registration.

COPY THIS PATTERN:
"""

from kailash.workflow.builder import WorkflowBuilder
from kailash_dataflow_utils import UUIDField
import hashlib

def login_workflow():
    """User login - email/password authentication."""

    workflow = WorkflowBuilder()

    # Step 1: Find user by email
    workflow.add_node("UserListNode", "find_user", {
        "filters": {"email": "{{ email }}"},
        "limit": 1
    })

    # Step 2: Validate password (PythonCodeNode for custom logic)
    workflow.add_node("PythonCodeNode", "validate_password", {
        "code": """
import hashlib

user = inputs['find_user'][0] if inputs['find_user'] else None

if not user:
    return {'valid': False, 'error': 'User not found'}

# Hash provided password
provided_hash = hashlib.sha256(inputs['password'].encode()).hexdigest()

# Compare with stored hash
if provided_hash == user['hashed_password']:
    return {'valid': True, 'user': user}
else:
    return {'valid': False, 'error': 'Invalid password'}
        """,
        "inputs": {
            "find_user": "{{ find_user }}",
            "password": "{{ password }}"
        }
    })

    # Step 3: Generate JWT token
    workflow.add_node("JWTGenerateNode", "generate_token", {
        "payload": {
            "user_id": "{{ validate_password.user.id }}",
            "email": "{{ validate_password.user.email }}"
        },
        "secret": "{{ jwt_secret }}",  # From env
        "expires_in": 86400  # 24 hours
    })

    # Connect
    workflow.add_connection("find_user", "validate_password", "output", "input")
    workflow.add_connection("validate_password", "generate_token", "output", "input")

    return workflow.build()

def register_workflow():
    """User registration."""

    workflow = WorkflowBuilder()

    # Step 1: Check if email already exists
    workflow.add_node("UserListNode", "check_existing", {
        "filters": {"email": "{{ email }}"},
        "limit": 1
    })

    # Step 2: Create user (only if email doesn't exist)
    workflow.add_node("SwitchNode", "check_duplicate", {
        "condition": "len(inputs['check_existing']) == 0",
        "true_branch": "create_user",
        "false_branch": "error"
    })

    # Step 3a: Create user
    workflow.add_node("UserCreateNode", "create_user", {
        "id": UUIDField.generate(),
        "email": "{{ email }}",
        "name": "{{ name }}",
        "hashed_password": "{{ hashed_password }}"  # Pre-hashed by caller
    })

    # Step 3b: Return error
    workflow.add_node("PythonCodeNode", "error", {
        "code": "return {'error': 'Email already registered'}",
        "inputs": {}
    })

    # Connect
    workflow.add_connection("check_existing", "check_duplicate", "output", "input")

    return workflow.build()

"""
OR USE PRE-BUILT COMPONENT:

pip install kailash-sso

from kailash_sso import SSOManager

sso = SSOManager(
    providers=["google", "github"],  # OAuth2 providers
    jwt_secret="your-secret"
)

# Login workflow (pre-built)
nexus.register("login", sso.login_workflow())
nexus.register("register", sso.register_workflow())
nexus.register("logout", sso.logout_workflow())
"""
```

### Pattern 6: Multi-Tenancy Setup (60% usage in SaaS)

```python
"""
GOLDEN PATTERN #6: Multi-Tenancy Setup
======================================

Use this for SaaS applications with multiple customers (tenants).

Multi-tenancy isolates data between customers.

COPY THIS PATTERN:
"""

from dataflow import DataFlow

# Enable multi-tenancy
db = DataFlow(
    "postgresql://...",
    multi_tenant=True,  # ← Key setting
    audit_logging=True  # Recommended for SaaS
)

@db.model
class Organization:
    """Organization (tenant) model."""
    id: str
    name: str
    plan: str = "free"  # free, pro, enterprise

@db.model
class User:
    """User model with tenant association."""
    id: str
    name: str
    email: str
    organization_id: str  # Foreign key to Organization
    # tenant_id: str  # Added automatically by DataFlow

@db.model
class Product:
    """Product model - automatically isolated by tenant."""
    id: str
    name: str
    price: float
    # tenant_id: str  # Added automatically

"""
HOW MULTI-TENANCY WORKS:

1. DataFlow automatically adds 'tenant_id' to all models
2. All queries automatically filter by tenant_id
3. You don't need to add tenant_id to parameters

WORKFLOW USAGE:

# Set tenant context (usually from JWT token)
workflow = WorkflowBuilder()

# Read user (automatically scoped to tenant)
workflow.add_node("UserReadNode", "get_user", {
    "id": "{{ user_id }}",
    # tenant_id automatically injected from context
})

# List products (automatically filtered by tenant)
workflow.add_node("ProductListNode", "list_products", {
    "filters": {"is_available": True},
    # Only returns products for current tenant
})
"""

"""
TENANT CONTEXT MANAGEMENT:

# In API request handler (via middleware)
def get_current_tenant_id(jwt_token):
    # Extract from JWT
    payload = jwt.decode(jwt_token, secret)
    return payload['tenant_id']

# DataFlow uses tenant context from:
# 1. Explicit tenant_id parameter (rare)
# 2. Runtime context (set by middleware)
# 3. Environment variable: DATAFLOW_TENANT_ID

# In templates, tenant context is managed automatically
"""

"""
COMMON MISTAKES (AVOID):

❌ Manually filtering by tenant_id:
   workflow.add_node("UserListNode", "list", {
       "filters": {"tenant_id": "{{ tenant_id }}"}  # WRONG - redundant
   })

   workflow.add_node("UserListNode", "list", {
       "filters": {"is_active": True}  # CORRECT - tenant_id auto-added
   })

❌ Forgetting organization model:
   # Multi-tenancy needs an Organization/Tenant model
   # Users belong to organizations
   # Data belongs to organizations

❌ Cross-tenant data access:
   # DataFlow prevents this by default
   # To explicitly allow (rare): use existing_schema_mode=True
"""
```

### Pattern 7: Background Jobs (50% usage)

```python
"""
GOLDEN PATTERN #7: Background Jobs
==================================

Use this for async tasks (email, reports, cleanup).

COPY THIS PATTERN:
"""

from kailash.workflow.builder import WorkflowBuilder

def send_daily_report_workflow():
    """Background job: Send daily report."""

    workflow = WorkflowBuilder()

    # Step 1: Query data
    workflow.add_node("UserListNode", "get_active_users", {
        "filters": {"is_active": True}
    })

    # Step 2: Generate report
    workflow.add_node("PythonCodeNode", "generate_report", {
        "code": """
users = inputs['get_active_users']

report = f"Daily Report: {len(users)} active users"
# ... generate detailed report

return {'report': report}
        """,
        "inputs": {"get_active_users": "{{ get_active_users }}"}
    })

    # Step 3: Send email
    workflow.add_node("EmailSendNode", "send_report", {
        "to": "admin@company.com",
        "subject": "Daily Report",
        "body": "{{ generate_report.report }}"
    })

    # Connect
    workflow.add_connection("get_active_users", "generate_report", "output", "input")
    workflow.add_connection("generate_report", "send_report", "output", "input")

    return workflow.build()

"""
SCHEDULING:

Option 1: Use cron (simple)
# crontab -e
0 9 * * * cd /path/to/app && nexus run send_daily_report

Option 2: Use Nexus scheduling (future feature)
nexus.schedule("send_daily_report", cron="0 9 * * *")

Option 3: Use external scheduler
# APScheduler, Celery, etc.
"""

"""
LONG-RUNNING JOBS:

For jobs that take >5 minutes, use AsyncLocalRuntime:

from kailash.runtime.async_local import AsyncLocalRuntime

async def run_job():
    runtime = AsyncLocalRuntime()
    results = await runtime.execute_workflow_async(workflow)
    return results

# Or use background queue (Celery, Redis Queue)
"""
```

### Pattern 8: File Processing (55% usage)

```python
"""
GOLDEN PATTERN #8: File Processing
==================================

Use this to process uploaded files (CSV, PDF, images).

COPY THIS PATTERN:
"""

from kailash.workflow.builder import WorkflowBuilder

def process_csv_upload_workflow():
    """Process uploaded CSV file."""

    workflow = WorkflowBuilder()

    # Step 1: Read file
    workflow.add_node("FileReadNode", "read_csv", {
        "file_path": "{{ file_path }}",
        "encoding": "utf-8"
    })

    # Step 2: Parse CSV
    workflow.add_node("PythonCodeNode", "parse_csv", {
        "code": """
import csv
import io

content = inputs['read_csv']
reader = csv.DictReader(io.StringIO(content))
rows = list(reader)

return {'rows': rows, 'count': len(rows)}
        """,
        "inputs": {"read_csv": "{{ read_csv }}"}
    })

    # Step 3: Bulk insert to database
    workflow.add_node("ProductBulkCreateNode", "import_products", {
        "records": "{{ parse_csv.rows }}"
    })

    # Connect
    workflow.add_connection("read_csv", "parse_csv", "output", "input")
    workflow.add_connection("parse_csv", "import_products", "output", "input")

    return workflow.build()

"""
FILE NODES AVAILABLE:

FileReadNode - Read file content
  - file_path: Path to file
  - encoding: File encoding (default: utf-8)

FileWriteNode - Write file
  - file_path: Destination path
  - content: Content to write

FileDeleteNode - Delete file
  - file_path: File to delete

DirectoryReaderNode - Read directory
  - directory_path: Directory to scan
  - pattern: File pattern (*.csv, *.pdf)
"""

"""
COMMON FILE OPERATIONS:

# CSV processing
workflow.add_node("CSVParserNode", "parse", {"file": "data.csv"})

# PDF extraction
workflow.add_node("PDFExtractorNode", "extract", {"file": "document.pdf"})

# Image processing (requires kailash-vision-analyzer)
from kailash_vision_analyzer import VisionAnalyzer

analyzer = VisionAnalyzer()
result = analyzer.analyze(image="receipt.jpg", question="What's the total?")

# Bulk file processing
workflow.add_node("DirectoryReaderNode", "scan", {"path": "uploads/", "pattern": "*.csv"})
workflow.add_node("PythonCodeNode", "process_each", {
    "code": "return {'files': [process(f) for f in inputs['scan']]}"
})
```

### Pattern 9: Error Handling (70% usage)

```python
"""
GOLDEN PATTERN #9: Error Handling
=================================

Use this to handle errors gracefully in workflows.

COPY THIS PATTERN:
"""

from kailash.workflow.builder import WorkflowBuilder

def process_payment_with_error_handling():
    """Example: Process payment with error handling."""

    workflow = WorkflowBuilder()

    # Step 1: Validate payment details
    workflow.add_node("PythonCodeNode", "validate_payment", {
        "code": """
if inputs['amount'] <= 0:
    raise ValueError("Amount must be positive")
if not inputs['payment_method']:
    raise ValueError("Payment method required")

return {'valid': True}
        """,
        "inputs": {
            "amount": "{{ amount }}",
            "payment_method": "{{ payment_method }}"
        }
    })

    # Step 2: Process payment
    workflow.add_node("HTTPRequestNode", "charge_stripe", {
        "url": "https://api.stripe.com/v1/charges",
        "method": "POST",
        # ... Stripe API config
    })

    # Step 3: Update order status on success
    workflow.add_node("OrderUpdateNode", "mark_paid", {
        "filter": {"id": "{{ order_id }}"},
        "fields": {"status": "paid", "payment_id": "{{ charge_stripe.id }}"}
    })

    # ERROR HANDLERS:

    # If validation fails → log error
    workflow.add_error_handler("validate_payment", "log_validation_error")

    workflow.add_node("LogNode", "log_validation_error", {
        "message": "Payment validation failed: {{ error }}",
        "level": "error"
    })

    # If Stripe API fails → create refund request
    workflow.add_error_handler("charge_stripe", "handle_payment_failure")

    workflow.add_node("PythonCodeNode", "handle_payment_failure", {
        "code": """
# Log the error
logger.error(f"Payment failed: {inputs['error']}")

# Update order status
return {'status': 'payment_failed', 'error': str(inputs['error'])}
        """,
        "inputs": {"error": "{{ error }}"}
    })

    # Connect
    workflow.add_connection("validate_payment", "charge_stripe", "output", "input")
    workflow.add_connection("charge_stripe", "mark_paid", "output", "input")

    return workflow.build()

"""
ERROR HANDLER SYNTAX:

workflow.add_error_handler(
    source_node="node_that_might_fail",
    error_handler_node="node_to_handle_error"
)

When source_node raises exception:
- Normal flow stops
- Error handler node executes
- Error message available as {{ error }}

ERROR HANDLING STRATEGIES:

1. Log and continue
   workflow.add_error_handler("api_call", "log_error")

2. Retry with backoff
   workflow.add_error_handler("api_call", "retry_node")
   # Use RetryNode or custom retry logic

3. Compensating transaction
   workflow.add_error_handler("charge_payment", "refund_payment")

4. Notify admin
   workflow.add_error_handler("critical_operation", "send_alert")
"""
```

### Pattern 10: Conditional Logic (90% usage)

```python
"""
GOLDEN PATTERN #10: Conditional Logic
=====================================

Use this for if/else logic in workflows.

COPY THIS PATTERN:
"""

from kailash.workflow.builder import WorkflowBuilder

def user_approval_workflow():
    """Example: Approve or reject user based on conditions."""

    workflow = WorkflowBuilder()

    # Step 1: Get user details
    workflow.add_node("UserReadNode", "get_user", {
        "id": "{{ user_id }}"
    })

    # Step 2: Check if user should be auto-approved
    workflow.add_node("SwitchNode", "check_auto_approve", {
        "condition": "inputs['get_user']['email'].endswith('@company.com')",
        "true_branch": "auto_approve",
        "false_branch": "manual_review"
    })

    # Path A: Auto-approve
    workflow.add_node("UserUpdateNode", "auto_approve", {
        "filter": {"id": "{{ user_id }}"},
        "fields": {"status": "approved", "approved_by": "system"}
    })

    # Path B: Manual review
    workflow.add_node("PythonCodeNode", "manual_review", {
        "code": """
# Send to admin for review
return {
    'status': 'pending_review',
    'message': 'User requires manual approval'
}
        """,
        "inputs": {}
    })

    # Connect
    workflow.add_connection("get_user", "check_auto_approve", "output", "input")

    return workflow.build()

"""
CONDITIONAL NODES:

SwitchNode - If/else logic
  - condition: Python expression (evaluated)
  - true_branch: Node ID to execute if true
  - false_branch: Node ID to execute if false

ConditionsNode - Multiple conditions
  - conditions: List of (condition, node_id) pairs
  - default: Default node if none match

FilterNode - Filter data
  - data: Input data
  - filter_expression: Filter criteria
"""

"""
COMPLEX CONDITIONS:

# Multiple conditions
workflow.add_node("SwitchNode", "check_tier", {
    "condition": "inputs['user']['plan'] == 'enterprise'",
    "true_branch": "enterprise_features",
    "false_branch": "check_pro"
})

workflow.add_node("SwitchNode", "check_pro", {
    "condition": "inputs['user']['plan'] == 'pro'",
    "true_branch": "pro_features",
    "false_branch": "free_features"
})

# Or use ConditionsNode for multiple branches
workflow.add_node("ConditionsNode", "route_by_plan", {
    "conditions": [
        ("inputs['user']['plan'] == 'enterprise'", "enterprise_features"),
        ("inputs['user']['plan'] == 'pro'", "pro_features"),
        ("inputs['user']['plan'] == 'free'", "free_features")
    ],
    "default": "free_features"
})
"""
```

---

## Remaining 4 Golden Patterns (Summary)

### Pattern 7: Custom Business Logic (PythonCodeNode)

**Use case:** When no built-in node fits your needs

**Pattern:** Use PythonCodeNode to write custom Python code

**Example:** Complex calculations, data transformations, third-party SDK calls

### Pattern 8: Data Transformation (TransformNode)

**Use case:** Transform data between nodes

**Pattern:** Map, filter, reduce operations

**Example:** Format API responses, aggregate data, join datasets

### Pattern 9: Monitoring & Logging (75% usage)

**Use case:** Track application health and events

**Pattern:** Add LogNode, MetricsNode to workflows

**Example:** Performance tracking, audit logs, error monitoring

### Pattern 10: Testing Workflows (60% usage)

**Use case:** Test workflows in isolation

**Pattern:** Use TestingRuntime with mock nodes

**Example:** Unit tests for workflows, integration tests with real data

---

## Pattern Organization

### Embedded in Templates

**Every template includes all 10 patterns:**

```
templates/saas-starter/
├── models/
│   ├── user.py          # Pattern 1: DataFlow Model
│   └── organization.py  # Pattern 6: Multi-Tenancy
│
├── workflows/
│   ├── auth.py          # Pattern 5: Authentication
│   ├── crud.py          # Pattern 2: Create Workflow
│   ├── background.py    # Pattern 7: Background Jobs
│   ├── integrations.py  # Pattern 4: External API
│   └── admin.py         # Pattern 9: Conditional Logic
│
├── main.py              # Pattern 3: Deploy with Nexus
│
└── PATTERNS.md          # All 10 patterns documented
```

### AI Context Engineering

**For AI-assisted projects (detected by .ai-mode file):**

**.claude/context/golden-patterns.md** (auto-generated in project):
```markdown
# Golden Patterns for This Project

This project uses Kailash SDK with AI assistance.

Only use these 10 patterns:
1. Add DataFlow Model → See models/user.py
2. Create Workflow → See workflows/crud.py
3. Deploy with Nexus → See main.py
4. External API → See workflows/integrations.py
5. Authentication → See workflows/auth.py
6. Multi-Tenancy → See models/organization.py
7. Background Jobs → See workflows/background.py
8. File Processing → (add if needed, see Pattern 8)
9. Error Handling → See workflows/error_handling.py
10. Conditional Logic → See workflows/admin.py

DO NOT search full SDK documentation unless pattern doesn't fit.

For advanced use cases not covered, use Full SDK documentation.
```

**Claude Code behavior:**
- Detects `.ai-mode` file → Uses golden-patterns.md
- Doesn't detect → Uses full 246 skills

**Token savings:** 90% reduction (from 20K to 2K tokens)

---

## Pattern Distribution

### In Templates (Primary)
- All 10 patterns embedded in code
- Comments explain each pattern
- PATTERNS.md references all patterns

### In Quick Mode Docs (Secondary)
- `/docs/it-teams/patterns/` directory
- One file per pattern
- Copy-paste ready code

### In AI Context (Automatic)
- `.claude/context/golden-patterns.md` auto-generated
- References template files
- Minimal token overhead

---

## Success Metrics

**1. Pattern Coverage**
- Target: 80% of use cases solved by 10 patterns
- Measure: % of AI prompts that use Golden Patterns (vs full docs)
- Validation: A/B test with beta users

**2. Token Reduction**
- Target: 90% reduction in navigation tokens
- Current: 20K tokens to find pattern
- Goal: 2K tokens with Golden Patterns

**3. AI Success Rate**
- Target: 90% of code generations work first try
- With 246 skills: ~60% success rate (too many choices)
- With 10 patterns: Expected 90% (clear choices)

**4. Time-to-Solution**
- Target: <5 seconds to find relevant pattern
- Current: 30+ seconds navigating 246 skills
- With 10 patterns: <5 seconds

---

## Implementation Timeline

**Week 1: Pattern Selection**
- Analyze current skill usage
- Identify top 10 patterns
- Validate with user interviews

**Week 2: Pattern Documentation**
- Write detailed pattern docs
- Create code examples
- Test with AI assistants (Claude Code)

**Week 3: Template Integration**
- Embed patterns in SaaS template
- Add PATTERNS.md reference
- Test discoverability

**Week 4: AI Context Engineering**
- Create auto-detection system
- Generate .claude/context/golden-patterns.md
- A/B test vs full skills

---

## Key Takeaways

**10 Golden Patterns are the foundation of AI-assisted development with Kailash.**

**Success depends on:**
- Choosing the RIGHT 10 patterns (80/20 rule)
- Clear documentation (copy-paste ready)
- Seamless integration with templates
- AI context detection (auto-use golden patterns)

**If Golden Patterns reduce token consumption by 90% and improve success rate to 90%, the repivot succeeds.**

---

**Next:** See `04-marketplace-specification.md` for component marketplace details
