# AI-Optimized Templates Specification

**Purpose:** Detailed specification for the 3 starter templates that enable IT teams to build with Kailash using AI assistants

**Priority:** 1 (Critical - Must build first)
**Estimated Effort:** 120 hours
**Timeline:** Weeks 1-8

---

## Executive Summary

**What:** Pre-built, working applications that IT teams can customize with AI assistance

**Why:** Solve the "blank canvas problem" - starting from scratch is intimidating and token-intensive

**How:** Templates generate working code with embedded AI instructions, allowing Claude Code to help users customize

**Success Criteria:** 80% of new projects use templates, time-to-first-screen <5 minutes

---

## The Three Templates

### Template 1: SaaS Starter

**Target Use Case:** Multi-tenant SaaS applications

**What It Includes:**
- User authentication (OAuth2 + JWT)
- Multi-tenant data isolation
- Admin dashboard
- API + CLI + MCP deployment (via Nexus)
- Payment integration hooks (Stripe ready)
- Email notifications
- Audit logging

**Tech Stack:**
- DataFlow: User, Organization, Subscription models
- Nexus: Multi-channel deployment
- PostgreSQL: Production database
- Pre-configured middleware: Auth, RBAC, audit

**Working in 5 minutes:**
```bash
kailash create my-saas --template=saas-starter
cd my-saas
cp .env.example .env  # Add DATABASE_URL, OPENAI_API_KEY
kailash dev

# Output:
# ✅ API: http://localhost:8000
# ✅ Admin: http://localhost:8000/admin
# ✅ MCP: stdio://localhost:3001
# ✅ Database: 5 tables created
# ✅ Sample data: 2 users, 1 org
```

### Template 2: Internal Tools

**Target Use Case:** Internal business tools and automation

**What It Includes:**
- Employee authentication (SSO ready)
- Dashboard with metrics
- Data import/export workflows
- Scheduled jobs
- Notification system
- Simple RBAC

**Tech Stack:**
- DataFlow: Employee, Task, Report models
- Nexus: API + CLI focus (MCP optional)
- SQLite: Fast local development
- Background jobs: Celery integration hooks

**Working in 5 minutes:**
```bash
kailash create my-tool --template=internal-tools
cd my-tool
kailash dev

# Output:
# ✅ API: http://localhost:8000
# ✅ CLI: kailash run import-data
# ✅ Dashboard: http://localhost:8000/dashboard
# ✅ Database: SQLite (data.db)
# ✅ Scheduled job: Daily report at 9 AM
```

### Template 3: API Gateway

**Target Use Case:** API orchestration and microservices gateway

**What It Includes:**
- API routing and composition
- Request/response transformation
- Rate limiting
- API key management
- Request logging
- Health checks

**Tech Stack:**
- Core SDK: Workflow orchestration
- Nexus: API gateway mode
- No database (stateless by default)
- Redis: Optional for rate limiting cache

**Working in 5 minutes:**
```bash
kailash create my-gateway --template=api-gateway
cd my-gateway
kailash dev

# Output:
# ✅ Gateway: http://localhost:8000
# ✅ Routes: 3 configured
# ✅ Rate limiting: 1000 req/min
# ✅ Health: http://localhost:8000/health
# ✅ Docs: http://localhost:8000/docs
```

---

## Template Structure (Detailed)

### SaaS Starter Template Structure

```
templates/saas-starter/
├── README.md                    # Human-readable overview
├── CUSTOMIZE.md                # How to customize for YOUR SaaS
├── .env.example                # Environment variables template
├── requirements.txt            # Python dependencies
├── pyproject.toml              # Project metadata
│
├── main.py                     # Application entry point
│   # AI INSTRUCTION: This is the main entry point
│   # To add new workflows, register them with nexus.register(name, workflow)
│
├── config.py                   # Configuration management
│   # AI INSTRUCTION: Add your config variables here
│   # All configs loaded from environment or .env file
│
├── models/                     # DataFlow models
│   ├── __init__.py
│   ├── user.py                # User model with auth
│   │   # AI INSTRUCTION: User model is pre-configured with:
│   │   # - id (UUID), email, hashed_password, is_active
│   │   # - created_at, updated_at (auto-managed)
│   │   # - tenant_id (multi-tenancy enabled)
│   │   #
│   │   # To add custom fields:
│   │   # 1. Add field to User class with type hint
│   │   # 2. Run: kailash db migrate
│   │   # 3. Use in workflows: UserCreateNode, UserUpdateNode, etc.
│   │
│   ├── organization.py        # Organization (tenant) model
│   └── subscription.py        # Subscription/billing model
│
├── workflows/                  # Business logic workflows
│   ├── __init__.py
│   ├── auth_workflows.py      # Login, register, logout
│   │   # AI INSTRUCTION: Auth workflows are pre-configured
│   │   # - login: Takes email/password, returns JWT token
│   │   # - register: Creates user + organization
│   │   # - logout: Invalidates session
│   │   #
│   │   # To customize:
│   │   # - Add fields to registration (edit register workflow)
│   │   # - Change token expiration (edit config.py JWT_EXPIRY)
│   │
│   ├── user_workflows.py      # User CRUD operations
│   └── admin_workflows.py     # Admin operations
│
├── middleware/                 # Custom middleware (if needed)
│   └── __init__.py
│
├── tests/                      # Test suite
│   ├── test_auth.py
│   ├── test_users.py
│   └── test_workflows.py
│
└── docs/                       # Documentation
    ├── architecture.md        # System architecture
    ├── api-reference.md       # API endpoints
    └── deployment.md          # How to deploy
```

### AI Instruction Embedding Pattern

**Every Python file has AI instructions as comments:**

```python
# models/user.py

"""User model for authentication and profile management.

AI INSTRUCTIONS:
================
This model uses DataFlow's @db.model decorator to auto-generate 9 workflow nodes:
- UserCreateNode: Create new user
- UserReadNode: Get user by ID
- UserUpdateNode: Update user fields
- UserDeleteNode: Delete user
- UserListNode: Query users with filters
- UserBulkCreateNode, UserBulkUpdateNode, UserBulkDeleteNode, UserBulkUpsertNode

Common Customizations:
1. ADD A FIELD
   class User:
       phone: str  # ← Just add this line
       # DataFlow automatically:
       # - Creates database column
       # - Updates all 9 nodes
       # - Validates type on operations

2. MAKE FIELD OPTIONAL
   class User:
       phone: Optional[str] = None  # ← Add default value

3. ADD VALIDATION
   class User:
       phone: str
       __dataflow__ = {
           'validators': {
               'phone': r'^\+?[0-9]{10,15}$'  # Regex pattern
           }
       }

4. ENABLE ENCRYPTION
   class User:
       ssn: str
       __dataflow__ = {
           'encrypted_fields': ['ssn']
       }

COMMON MISTAKES TO AVOID:
- ❌ Don't use .isoformat() for datetime fields
     created_at: datetime.now().isoformat()  # WRONG
     created_at: datetime.now()  # CORRECT

- ❌ Don't include created_at/updated_at manually
     # These are auto-managed by DataFlow

- ❌ Don't use user_id as primary key
     id: str  # MUST be named 'id', not 'user_id'

USAGE IN WORKFLOWS:
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create_user", {
    "id": "uuid-here",  # Use UUIDField.generate() from kailash-dataflow-utils
    "email": "user@example.com",
    "name": "Alice"
})
"""

from dataflow import DataFlow
from datetime import datetime
from typing import Optional

db = DataFlow("postgresql://...")  # From env: DATABASE_URL

@db.model
class User:
    """User model with multi-tenancy and authentication."""
    id: str                    # Primary key (UUID)
    email: str                 # Email (unique per tenant)
    name: str                  # Display name
    hashed_password: str       # Password (hashed, never plain text)
    is_active: bool = True     # Account active status
    is_admin: bool = False     # Admin flag
    created_at: datetime       # Auto-managed
    updated_at: datetime       # Auto-managed
    # tenant_id: str  # Added automatically in multi-tenant mode
```

### CUSTOMIZE.md Structure

```markdown
# Customizing Your SaaS

This template provides a working multi-tenant SaaS application. Follow these steps to make it yours.

## Step 1: Configure Your Database (5 minutes)

1. Copy `.env.example` to `.env`
2. Set `DATABASE_URL` to your PostgreSQL connection string
3. Set `OPENAI_API_KEY` if using AI features

```bash
cp .env.example .env
# Edit .env and add your values
```

## Step 2: Add Your Business Models (15 minutes)

Example: Adding a "Product" model

1. Create `models/product.py`:

```python
from dataflow import DataFlow

db = DataFlow("postgresql://...")  # Uses DATABASE_URL from .env

@db.model
class Product:
    """Product model for your catalog."""
    id: str
    name: str
    description: str
    price: float
    is_available: bool = True
```

2. DataFlow automatically creates 9 workflow nodes:
   - ProductCreateNode, ProductReadNode, ProductUpdateNode, etc.

3. Use in workflows:

```python
# workflows/product_workflows.py

from kailash.workflow.builder import WorkflowBuilder

def create_product_workflow():
    workflow = WorkflowBuilder()
    workflow.add_node("ProductCreateNode", "create", {
        "id": "{{ product_id }}",
        "name": "{{ product_name }}",
        "description": "{{ description }}",
        "price": "{{ price }}"
    })
    return workflow.build()
```

4. Register with Nexus:

```python
# main.py

from workflows.product_workflows import create_product_workflow

nexus.register("create_product", create_product_workflow())
```

Now available on all channels:
- API: POST /workflows/create_product
- CLI: nexus run create_product --product_name "Widget"
- MCP: create_product(product_name="Widget")

## Step 3: Customize Authentication (10 minutes)

Add custom fields to registration:

```python
# models/user.py

@db.model
class User:
    # ... existing fields ...
    company: Optional[str] = None      # ← Add company field
    phone: Optional[str] = None         # ← Add phone field
```

Update registration workflow:

```python
# workflows/auth_workflows.py

workflow.add_node("UserCreateNode", "create_user", {
    "id": "{{ user_id }}",
    "email": "{{ email }}",
    "name": "{{ name }}",
    "company": "{{ company }}",  # ← Now included
    "phone": "{{ phone }}",      # ← Now included
    "hashed_password": "{{ hashed_password }}"
})
```

## Step 4: Add Business Workflows (30 minutes)

Example: Add a "Process Order" workflow

1. Create `workflows/order_workflows.py`
2. Define workflow using WorkflowBuilder
3. Register with Nexus in `main.py`
4. Test via API or CLI

## Step 5: Deploy (15 minutes)

See `docs/deployment.md` for:
- Docker deployment
- Kubernetes deployment
- Environment variables
- Database migrations
- Monitoring setup

---

## Common Customizations

### Add Payment Processing
- Install: `pip install kailash-payments`
- Configure Stripe keys in `.env`
- See: `docs/integrations/payments.md`

### Add Admin Dashboard
- Install: `pip install kailash-admin`
- Configure in `main.py`
- See: `docs/admin-dashboard.md`

### Add Email Notifications
- Install: `pip install kailash-notifications`
- Configure email provider in `.env`
- See: `docs/notifications.md`

---

## Getting Help

- Documentation: `docs/`
- Examples: `examples/`
- Community: Discord, GitHub Discussions
- Support: support@kailash.dev

## Using Claude Code

This template is optimized for Claude Code. When making changes:

1. Describe what you want in plain English
2. Claude Code will modify the appropriate files
3. Test with `kailash dev`
4. Iterate until it works

Example prompt:
> "Add a 'status' field to the User model that can be 'active', 'suspended', or 'deleted'. Update the admin workflow to allow changing user status."

Claude Code will:
- Add `status` field to `models/user.py`
- Generate migration (if needed)
- Update admin workflow to include status changes
- Test the changes

---

**Ready to build your SaaS? Start with Step 1 above!**
```

---

## Implementation Details

### Template Generation System

**Location:** `templates/` directory in SDK root

**Structure:**
```
templates/
├── saas-starter/
├── internal-tools/
├── api-gateway/
└── template.json       # Template metadata
```

**template.json format:**
```json
{
  "name": "saas-starter",
  "version": "1.0.0",
  "description": "Multi-tenant SaaS application template",
  "author": "Kailash Team",
  "keywords": ["saas", "multi-tenant", "auth", "payments"],
  "variables": {
    "project_name": {
      "prompt": "Project name (lowercase, hyphens only)",
      "default": "my-saas",
      "pattern": "^[a-z][a-z0-9-]*$"
    },
    "database_type": {
      "prompt": "Database type",
      "choices": ["postgresql", "mysql", "sqlite"],
      "default": "postgresql"
    },
    "enable_payments": {
      "prompt": "Enable payment integration?",
      "type": "boolean",
      "default": false
    }
  },
  "files": [
    "**/*.py",
    "**/*.md",
    ".env.example",
    "requirements.txt"
  ],
  "exclude": [
    "**/__pycache__",
    "**/*.pyc",
    ".env"
  ]
}
```

### CLI Command: kailash create

**Implementation:** `src/kailash/cli/create.py` (new file)

```python
# src/kailash/cli/create.py

import click
import os
import shutil
import json
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

@click.command()
@click.argument('project_name')
@click.option('--template', default='saas-starter', help='Template to use')
@click.option('--ai-mode', is_flag=True, help='Enable AI-optimized mode')
def create(project_name, template, ai_mode):
    """Create a new Kailash project from a template."""

    # Get template directory
    templates_dir = Path(__file__).parent.parent.parent / 'templates'
    template_dir = templates_dir / template

    if not template_dir.exists():
        click.echo(f"❌ Template '{template}' not found")
        click.echo(f"Available templates: {', '.join(list_templates())}")
        return

    # Load template metadata
    metadata = load_template_metadata(template_dir)

    # Prompt for template variables
    variables = prompt_for_variables(metadata['variables'], project_name)

    # Create project directory
    project_dir = Path(project_name)
    if project_dir.exists():
        click.echo(f"❌ Directory '{project_name}' already exists")
        return

    # Copy template files with variable substitution
    copy_template(template_dir, project_dir, variables, ai_mode)

    # Post-creation setup
    setup_project(project_dir, variables)

    # Success message
    click.echo(f"✅ Project '{project_name}' created successfully!")
    click.echo(f"\nNext steps:")
    click.echo(f"  cd {project_name}")
    click.echo(f"  cp .env.example .env  # Add your config")
    click.echo(f"  kailash dev           # Start development server")
    click.echo(f"\nSee CUSTOMIZE.md for customization guide.")

def copy_template(template_dir, project_dir, variables, ai_mode):
    """Copy template files with Jinja2 variable substitution."""

    env = Environment(loader=FileSystemLoader(template_dir))

    for file_path in template_dir.rglob('*'):
        if file_path.is_file():
            relative_path = file_path.relative_to(template_dir)

            # Skip excluded files
            if should_exclude(relative_path):
                continue

            # Render file with variables
            if file_path.suffix in ['.py', '.md', '.txt', '.json']:
                content = env.get_template(str(relative_path)).render(**variables)
            else:
                content = file_path.read_bytes()

            # Write to project directory
            dest_path = project_dir / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(content, str):
                dest_path.write_text(content)
            else:
                dest_path.write_bytes(content)

def setup_project(project_dir, variables):
    """Post-creation setup."""

    # Initialize git repo
    os.system(f"cd {project_dir} && git init")

    # Create virtual environment
    os.system(f"cd {project_dir} && python -m venv .venv")

    # Install dependencies
    click.echo("Installing dependencies...")
    os.system(f"cd {project_dir} && .venv/bin/pip install -r requirements.txt")

    click.echo("✅ Setup complete!")
```

---

## Testing Strategy

### Unit Tests

**Test template generation:**
```python
# tests/test_template_generation.py

def test_saas_template_generates_correctly():
    """Test that SaaS template generates with correct structure."""
    result = runner.invoke(create, ['test-saas', '--template=saas-starter'])

    assert result.exit_code == 0
    assert Path('test-saas').exists()
    assert Path('test-saas/main.py').exists()
    assert Path('test-saas/models/user.py').exists()
    assert Path('test-saas/CUSTOMIZE.md').exists()

def test_variable_substitution():
    """Test that template variables are substituted correctly."""
    result = runner.invoke(create, [
        'my-app',
        '--template=saas-starter',
        '--project-name=my-app',
        '--database-type=postgresql'
    ])

    main_py = Path('my-app/main.py').read_text()
    assert 'my-app' in main_py
    assert 'postgresql' in main_py
```

### Integration Tests

**Test generated project works:**
```python
# tests/integration/test_template_integration.py

def test_saas_template_runs_successfully():
    """Test that generated SaaS template runs without errors."""

    # Generate project
    runner.invoke(create, ['test-saas', '--template=saas-starter'])

    # Set up test environment
    env_file = Path('test-saas/.env')
    env_file.write_text("""
    DATABASE_URL=sqlite:///test.db
    JWT_SECRET=test-secret
    """)

    # Run project
    result = subprocess.run(
        ['python', 'main.py'],
        cwd='test-saas',
        capture_output=True,
        timeout=10
    )

    # Verify it starts correctly
    assert result.returncode == 0
    assert b'Nexus initialized' in result.stdout

def test_template_workflows_execute():
    """Test that template workflows execute correctly."""

    # ... (similar setup)

    # Test auth workflow
    response = requests.post('http://localhost:8000/workflows/register', json={
        "email": "test@example.com",
        "password": "testpass123",
        "name": "Test User"
    })

    assert response.status_code == 200
    assert 'user_id' in response.json()
```

### E2E Tests

**Test with real AI assistant:**
```python
# tests/e2e/test_ai_customization.py

def test_claude_code_can_customize_template(claude_code_api):
    """Test that Claude Code can successfully customize a template."""

    # Generate project
    runner.invoke(create, ['test-saas', '--template=saas-starter', '--ai-mode'])

    # Send prompt to Claude Code
    prompt = """
    Add a 'Product' model with fields: name, description, price, is_available.
    Create a workflow to create products.
    Register the workflow with Nexus.
    """

    result = claude_code_api.execute(prompt, project_dir='test-saas')

    # Verify changes
    assert Path('test-saas/models/product.py').exists()
    assert Path('test-saas/workflows/product_workflows.py').exists()

    # Verify product workflow registered
    main_py = Path('test-saas/main.py').read_text()
    assert 'create_product' in main_py

    # Test the workflow works
    # ... (similar to integration test)
```

---

## Success Metrics

### Template Quality Metrics

**1. Time-to-First-Screen**
- Target: <5 minutes (90th percentile)
- Measure: Time from `kailash create` to seeing working app
- How: Telemetry + user surveys

**2. Customization Success Rate**
- Target: 80% of users successfully customize
- Measure: % who add at least 1 custom model or workflow
- How: Opt-in telemetry tracking model registration

**3. Template Adoption Rate**
- Target: 80% of new projects use templates
- Measure: `kailash create --template` vs `kailash create` (blank)
- How: CLI telemetry

**4. Template Satisfaction (NPS)**
- Target: NPS 40+ (considered "good")
- Measure: "How likely are you to recommend Kailash templates?"
- How: In-app survey after 7 days

### AI Assistant Effectiveness

**5. Successful AI-Assisted Customizations**
- Target: 70% of AI-assisted changes work first try
- Measure: Changes that don't require debugging
- How: User feedback + error tracking

**6. Token Efficiency**
- Target: <10K tokens for typical customization
- Measure: Token consumption for common tasks
- How: Compare with blank project (expected 50K+ tokens)

---

## Rollout Plan

### Week 1-2: SaaS Template Alpha
- Build basic SaaS template
- Test internally
- Validate structure and AI instructions

### Week 3-4: SaaS Template Beta
- Add CUSTOMIZE.md
- Test with 5 external beta testers (IT teams)
- Gather feedback, iterate

### Week 5-6: Internal Tools Template
- Build based on learnings from SaaS template
- Reuse patterns that worked
- Beta test with 5 different users

### Week 7-8: API Gateway Template
- Build third template
- Finalize CLI command
- Documentation complete
- Public beta launch

---

## Maintenance Plan

### Template Updates

**Monthly:** Security updates, dependency bumps

**Quarterly:** Feature additions based on user feedback

**Annually:** Major template redesigns if needed

**Process:**
1. Make changes to template
2. Test with fresh generation
3. Update version in template.json
4. Document changes in CHANGELOG.md
5. Announce to users (upgrade guide if breaking)

### Community Templates

**Phase 2 (Month 6+):** Allow community-contributed templates

**Requirements:**
- Must follow template.json format
- Must include CUSTOMIZE.md
- Must have tests
- Must be reviewed by Kailash team

**Discovery:** `kailash create my-app --template=community/awesome-template`

---

## Key Takeaways

**Templates are the foundation of the entire repivot strategy.**

**Success criteria:**
- Working in 5 minutes
- AI-friendly (embedded instructions)
- Highly customizable
- Production-ready (not toy examples)

**Implementation priorities:**
1. SaaS template first (most common use case)
2. Perfect the AI instruction embedding
3. Validate with beta testers before building others
4. Iterate based on real feedback

**If templates succeed, the entire repivot succeeds. If templates fail, reconsider the strategy.**

---

**Next:** See `02-quick-mode-specification.md` for Quick Mode details (builds on templates)
