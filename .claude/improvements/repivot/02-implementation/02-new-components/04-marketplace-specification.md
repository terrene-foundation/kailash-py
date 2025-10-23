# Component Marketplace Specification

**Purpose:** Enable component reuse through a package marketplace - solve "rebuilding same components" problem

**Priority:** 1 (Critical - Enables ecosystem)
**Estimated Effort:** 80 hours (infrastructure) + 200 hours (initial components)
**Timeline:** Weeks 13-24

---

## Executive Summary

**What:** PyPI-based package registry for reusable Kailash components

**Why:** Users waste hours rebuilding SSO, RBAC, payments for each project - need installable artifacts

**How:** Publish official + community components as pip packages with discovery system

**Success Criteria:** 80% of projects use ≥1 marketplace component, 50+ components within 6 months

---

## The Problem

### Current State: Documentation Without Artifacts

**User wants SSO:**
```
Current approach:
1. Read authentication documentation (30 min)
2. Generate OAuth2 code from docs (1 hour)
3. Debug integration (2 hours)
4. Test with Google/GitHub (30 min)
Total: 4 hours

Repeat for EVERY project using SSO.
```

**Should be:**
```
Marketplace approach:
1. pip install kailash-sso (30 seconds)
2. Configure provider (5 minutes)
3. Register workflow (1 line)
Total: 10 minutes

Reuse across ALL projects.
```

### Component Reusability Gap

**User complaint:** "Too much time rebuilding same enterprise components for different apps"

**Examples of repeated work:**
- SSO (OAuth2, SAML, JWT) - rebuilt for every SaaS
- RBAC (roles, permissions) - rebuilt for every multi-user app
- Admin dashboard - rebuilt for every internal tool
- Payment integration - rebuilt for every e-commerce
- Audit logging - rebuilt for every enterprise app
- Email notifications - rebuilt for every app

**Cost:**
- 4-8 hours per component per project
- Slight variations (maintenance nightmare)
- No shared improvements (bug fixes don't propagate)
- No versioning (can't upgrade)

---

## Marketplace Architecture

### Three-Tier System

```
┌─────────────────────────────────────────────────┐
│  Tier 1: Official Components (Kailash Team)    │
│  - Verified, production-tested                  │
│  - Security audited                             │
│  - Maintained by core team                      │
│  - Examples: kailash-sso, kailash-rbac          │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  Tier 2: Verified Community (Reviewed)         │
│  - Submitted by community                       │
│  - Reviewed by Kailash team                     │
│  - Quality standards met                        │
│  - Examples: kailash-discord, kailash-analytics │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  Tier 3: Community (Unreviewed)                │
│  - Published by anyone                          │
│  - No verification                              │
│  - Use at own risk                              │
│  - Examples: experimental integrations          │
└─────────────────────────────────────────────────┘
```

### Distribution Model

**Primary:** PyPI (Python Package Index)
- Standard Python package distribution
- Familiar to all Python developers
- `pip install kailash-{component}`
- Semantic versioning

**Future:** Component catalog website
- Browse components
- Search by category/tag
- Usage statistics
- Reviews and ratings

---

## Official Components (Initial 5)

### Component 1: kailash-sso

**Purpose:** Authentication and Single Sign-On

**Features:**
- OAuth2 providers (Google, GitHub, Microsoft, etc.)
- SAML support (enterprise SSO)
- JWT token management
- Session management
- MFA support

**Package structure:**
```
packages/kailash-sso/
├── src/kailash_sso/
│   ├── __init__.py          # Public API
│   ├── manager.py           # SSOManager class
│   ├── providers/
│   │   ├── oauth2.py        # OAuth2 implementation
│   │   ├── saml.py          # SAML implementation
│   │   └── jwt.py           # JWT implementation
│   ├── workflows/
│   │   ├── login.py         # Pre-built login workflow
│   │   ├── register.py      # Pre-built registration
│   │   └── logout.py        # Pre-built logout
│   └── models/
│       ├── user.py          # User model (optional, use your own)
│       └── session.py       # Session model
│
├── examples/
│   ├── oauth2_basic.py      # Simple OAuth2 setup
│   ├── saml_enterprise.py   # Enterprise SAML
│   └── mfa_enabled.py       # Multi-factor auth
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   ├── quickstart.md
│   ├── oauth2-guide.md
│   ├── saml-guide.md
│   └── api-reference.md
│
├── README.md
├── CHANGELOG.md
├── pyproject.toml
└── setup.py
```

**API design:**
```python
# Installation
pip install kailash-sso

# Usage
from kailash_sso import SSOManager

sso = SSOManager(
    providers={
        "google": {
            "client_id": "{{ GOOGLE_CLIENT_ID }}",
            "client_secret": "{{ GOOGLE_CLIENT_SECRET }}",
            "redirect_uri": "https://myapp.com/auth/callback"
        },
        "github": {
            "client_id": "{{ GITHUB_CLIENT_ID }}",
            "client_secret": "{{ GITHUB_CLIENT_SECRET }}"
        }
    },
    jwt_secret="{{ JWT_SECRET }}",
    token_expiry=86400  # 24 hours
)

# Get pre-built workflows
login_workflow = sso.login_workflow()
register_workflow = sso.register_workflow()
callback_workflow = sso.callback_workflow()  # OAuth2 callback handler

# Register with Nexus
from nexus import Nexus

nexus = Nexus()
nexus.register("login", login_workflow)
nexus.register("register", register_workflow)
nexus.register("oauth_callback", callback_workflow)

# Start
nexus.start()

# Now available:
# - POST /workflows/login (email/password or OAuth2)
# - POST /workflows/register
# - GET /workflows/oauth_callback?code=...
```

**Value proposition:**
- 4 hours of development → 10 minutes of configuration
- Battle-tested (used in 100+ production apps)
- Security updates automatic
- Multiple providers supported
- Customizable

**Maintenance:**
- Monthly security updates
- Quarterly feature additions
- Annual major versions

### Component 2: kailash-rbac

**Purpose:** Role-Based Access Control

**Features:**
- Role management (create, assign, revoke roles)
- Permission system (resource-based)
- Middleware integration
- Audit logging
- UI components (admin dashboard)

**API design:**
```python
# Installation
pip install kailash-rbac

# Usage
from kailash_rbac import RBACManager
from dataflow import DataFlow

db = DataFlow("postgresql://...")

rbac = RBACManager(
    db=db,
    roles={
        "admin": ["*"],  # All permissions
        "user": ["read:own", "update:own"],
        "viewer": ["read:*"]
    }
)

# Check permissions in workflows
workflow.add_node("PythonCodeNode", "check_permission", {
    "code": """
if not rbac.has_permission(inputs['user_id'], 'delete:users'):
    raise PermissionError("Not authorized")
return {'authorized': True}
    """,
    "inputs": {"user_id": "{{ user_id }}"}
})

# Or use built-in node
workflow.add_node("RBACCheckNode", "authorize", {
    "user_id": "{{ user_id }}",
    "permission": "delete:users",
    "resource_id": "{{ target_user_id }}"
})
```

**DataFlow models:**
```python
# Auto-generated when you initialize RBACManager

@db.model
class Role:
    id: str
    name: str
    permissions: list  # JSON field

@db.model
class UserRole:
    id: str
    user_id: str
    role_id: str

# Usage in your code
rbac.assign_role(user_id="user-123", role="admin")
rbac.check_permission(user_id="user-123", permission="delete:users")
```

### Component 3: kailash-admin

**Purpose:** Admin dashboard and management UI

**Features:**
- Auto-generated CRUD UI for DataFlow models
- User management interface
- Role assignment UI
- Audit log viewer
- System health dashboard

**API design:**
```python
# Installation
pip install kailash-admin

# Usage
from kailash_admin import AdminDashboard
from dataflow import DataFlow

db = DataFlow("postgresql://...")

admin = AdminDashboard(
    db=db,
    models=["User", "Organization", "Subscription"],  # Models to manage
    auth_required=True
)

# Register with Nexus
from nexus import Nexus

nexus = Nexus()
admin.register_with_nexus(nexus)

# Now available:
# - /admin - Main dashboard
# - /admin/users - User management
# - /admin/organizations - Org management
# - /admin/audit - Audit logs
```

**Value:**
- Hours of React/Vue development → 5 minutes of configuration
- Responsive UI (works on mobile)
- Customizable (override templates)

### Component 4: kailash-payments

**Purpose:** Payment processing integration

**Features:**
- Stripe integration
- PayPal integration
- Subscription management
- Webhook handling
- Refund workflows

**API design:**
```python
# Installation
pip install kailash-payments

# Usage
from kailash_payments import PaymentManager

payments = PaymentManager(
    providers={
        "stripe": {
            "api_key": "{{ STRIPE_API_KEY }}",
            "webhook_secret": "{{ STRIPE_WEBHOOK_SECRET }}"
        }
    }
)

# Get workflows
charge_workflow = payments.charge_workflow()
refund_workflow = payments.refund_workflow()
subscription_workflow = payments.create_subscription_workflow()

# Register
nexus.register("charge_payment", charge_workflow)
nexus.register("process_refund", refund_workflow)
nexus.register("create_subscription", subscription_workflow)
```

### Component 5: kailash-dataflow-utils

**Purpose:** Prevent common DataFlow errors (datetime, JSON, UUID)

**Features:**
- TimestampField (prevents .isoformat() errors)
- JSONField (handles serialization)
- UUIDField (generates valid UUIDs)
- Validators (email, phone, URL)
- Common field mixins

**API design:**
```python
# Installation
pip install kailash-dataflow-utils

# Usage
from kailash_dataflow_utils import (
    TimestampField,
    JSONField,
    UUIDField,
    EmailValidator,
    PhoneValidator
)
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User:
    id: str
    email: str
    profile: dict  # JSON field
    created_at: datetime

# In workflow
workflow.add_node("UserCreateNode", "create", {
    "id": UUIDField.generate(),  # ✅ Correct UUID format
    "email": EmailValidator.validate("user@example.com"),  # ✅ Valid email
    "profile": {"age": 30, "city": "NYC"},  # ✅ Dict, not json.dumps()
    "created_at": TimestampField.now()  # ✅ datetime, not .isoformat()
})
```

**This component prevents the 48-hour datetime error!**

---

## Marketplace Infrastructure

### Component Discovery

**CLI commands:**
```bash
# Search marketplace
kailash marketplace search "authentication"

# Output:
# 📦 kailash-sso (v2.1.3) ⭐️ 1.2K installs
#    OAuth2, SAML, JWT authentication
#    Author: Kailash Team
#    License: MIT
#    Tags: auth, oauth2, saml, jwt
#
# 📦 kailash-auth0 (v1.0.5) ⭐️ 450 installs
#    Auth0 integration
#    Author: @community-member
#    License: MIT
#    Tags: auth, auth0

# Install component
kailash marketplace install kailash-sso

# Or use pip directly
pip install kailash-sso

# List installed components
kailash marketplace list

# Update component
kailash marketplace update kailash-sso

# Uninstall
kailash marketplace remove kailash-sso
```

**Backend:**
- Uses PyPI as package registry (no custom infrastructure)
- Metadata stored in each package's pyproject.toml
- Discovery via PyPI API + optional kailash.dev catalog

### Package Standard

**All marketplace components must:**
1. ✅ Follow naming: `kailash-{component}` (kebab-case)
2. ✅ Semantic versioning: `MAJOR.MINOR.PATCH`
3. ✅ Include README.md with quick start
4. ✅ Include CLAUDE.md with AI instructions
5. ✅ Include examples/ directory
6. ✅ Include tests/ with ≥80% coverage
7. ✅ Include CHANGELOG.md
8. ✅ Declare kailash dependency version range

**pyproject.toml format:**
```toml
[project]
name = "kailash-sso"
version = "2.1.3"
description = "Authentication and SSO for Kailash applications"
authors = [{name = "Kailash Team", email = "team@kailash.dev"}]
license = {text = "MIT"}
readme = "README.md"
requires-python = ">=3.10"

dependencies = [
    "kailash>=0.9.27,<1.0.0",  # SDK version range
    "pyjwt>=2.8.0",
    "requests>=2.31.0"
]

[project.optional-dependencies]
dev = ["pytest>=7.4.0", "black>=23.0.0"]

[project.urls]
Homepage = "https://github.com/kailash-sdk/kailash-sso"
Documentation = "https://docs.kailash.dev/components/sso"
Repository = "https://github.com/kailash-sdk/kailash-sso"

[tool.kailash]  # ← Marketplace metadata
category = "authentication"
tags = ["oauth2", "saml", "jwt", "sso"]
tier = "official"  # official | verified | community
verified = true
featured = true
production_ready = true
```

### Component Template

**cookiecutter template for creating components:**

```bash
# Create new component
kailash component create kailash-mycomponent

# Generates:
kailash-mycomponent/
├── src/kailash_mycomponent/
│   ├── __init__.py
│   ├── manager.py       # Main class
│   └── workflows/       # Pre-built workflows
│
├── examples/
│   └── basic_usage.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
│
├── docs/
│   └── quickstart.md
│
├── README.md           # Auto-generated template
├── CLAUDE.md          # AI instructions template
├── CHANGELOG.md
├── pyproject.toml     # Pre-configured
├── .gitignore
└── LICENSE
```

---

## Component Development Workflow

### 1. Create Component

```bash
kailash component create kailash-notifications
cd kailash-notifications
```

### 2. Implement Component

```python
# src/kailash_notifications/manager.py

from kailash.workflow.builder import WorkflowBuilder
from typing import Optional, Dict, List

class NotificationManager:
    """Manage email, SMS, and push notifications."""

    def __init__(
        self,
        email_provider: str = "sendgrid",
        sms_provider: str = "twilio",
        email_config: Optional[Dict] = None,
        sms_config: Optional[Dict] = None
    ):
        self.email_provider = email_provider
        self.sms_provider = sms_provider
        self.email_config = email_config or {}
        self.sms_config = sms_config or {}

    def send_email_workflow(self):
        """Pre-built workflow for sending email."""
        workflow = WorkflowBuilder()

        if self.email_provider == "sendgrid":
            workflow.add_node("HTTPRequestNode", "send_email", {
                "url": "https://api.sendgrid.com/v3/mail/send",
                "method": "POST",
                "headers": {
                    "Authorization": f"Bearer {self.email_config['api_key']}",
                    "Content-Type": "application/json"
                },
                "body": {
                    "personalizations": [{
                        "to": [{"email": "{{ to }}"}],
                        "subject": "{{ subject }}"
                    }],
                    "from": {"email": self.email_config['from_email']},
                    "content": [{"type": "text/html", "value": "{{ body }}"}]
                }
            })

        return workflow.build()

    def send_sms_workflow(self):
        """Pre-built workflow for sending SMS."""
        # Similar implementation for Twilio
        pass

    def send_push_workflow(self):
        """Pre-built workflow for push notifications."""
        # Implementation for push notifications
        pass
```

### 3. Write Tests

```python
# tests/integration/test_email_integration.py

def test_send_email_via_sendgrid():
    """Test that email workflow works with real SendGrid API."""
    from kailash_notifications import NotificationManager
    from kailash.runtime.local import LocalRuntime

    manager = NotificationManager(
        email_provider="sendgrid",
        email_config={
            "api_key": os.getenv("SENDGRID_API_KEY"),
            "from_email": "test@kailash.dev"
        }
    )

    workflow = manager.send_email_workflow()

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow, inputs={
        "to": "recipient@example.com",
        "subject": "Test Email",
        "body": "This is a test"
    })

    assert results["send_email"]["status"] == "success"
```

### 4. Document

```markdown
# kailash-notifications

Email, SMS, and push notification workflows for Kailash applications.

## Quick Start

```python
pip install kailash-notifications

from kailash_notifications import NotificationManager

notifications = NotificationManager(
    email_provider="sendgrid",
    email_config={"api_key": "...", "from_email": "noreply@myapp.com"}
)

# Get workflow
email_workflow = notifications.send_email_workflow()

# Register with Nexus
nexus.register("send_email", email_workflow)
```

## Supported Providers

**Email:**
- SendGrid (recommended)
- AWS SES
- Mailgun
- SMTP (generic)

**SMS:**
- Twilio (recommended)
- AWS SNS

**Push:**
- Firebase Cloud Messaging
- Apple Push Notification Service
```

### 5. Publish to PyPI

```bash
# Build package
python -m build

# Upload to PyPI
python -m twine upload dist/*

# Now installable:
pip install kailash-notifications
```

### 6. Submit to Marketplace Catalog

```bash
# Submit for verification (optional)
kailash marketplace submit kailash-notifications

# Or just publish to PyPI (community tier)
# Users can find via: pip search kailash-notifications
```

---

## Component Discovery System

### PyPI-Based Discovery

**Automatic discovery via naming convention:**
- All packages starting with `kailash-` are components
- PyPI provides: name, version, description, downloads
- No custom infrastructure needed

**Search implementation:**
```python
# src/kailash/cli/marketplace.py

import requests

def search_components(query: str) -> list:
    """Search for Kailash components on PyPI."""

    # Search PyPI for packages matching kailash-{query}
    response = requests.get(
        "https://pypi.org/pypi/kailash-{query}/json"
    )

    if response.status_code == 200:
        data = response.json()
        return [{
            "name": data["info"]["name"],
            "version": data["info"]["version"],
            "description": data["info"]["summary"],
            "author": data["info"]["author"],
            "downloads": data["info"]["downloads"]["last_month"],
            "url": data["info"]["home_page"]
        }]

    # Fallback: Search all packages containing "kailash"
    response = requests.get(
        f"https://pypi.org/search/?q=kailash+{query}",
        headers={"Accept": "application/json"}
    )

    # Parse search results
    # ... (implementation)

    return results
```

### Optional: Component Catalog Website (Future)

**kailash.dev/marketplace:**
- Browse by category (auth, database, integrations, AI)
- Filter by tier (official, verified, community)
- Sort by popularity, newest, trending
- Reviews and ratings (future)
- Usage examples embedded

**Benefits:**
- Better UX than PyPI search
- Showcase featured components
- Community engagement (reviews, comments)

**Implementation:**
- Static site (Next.js) hosted on Vercel
- Data from PyPI API + metadata file
- Optional (Phase 2)

---

## Component Categories

### 1. Authentication & Security
- kailash-sso (OAuth2, SAML, JWT)
- kailash-rbac (role-based access control)
- kailash-mfa (multi-factor authentication)
- kailash-audit (audit logging)

### 2. Database & Data
- kailash-dataflow-utils (field helpers, validators)
- kailash-migrations (advanced migration tools)
- kailash-elasticsearch (Elasticsearch integration)
- kailash-redis (Redis cache integration)

### 3. Integrations
- kailash-payments (Stripe, PayPal)
- kailash-notifications (email, SMS, push)
- kailash-storage (S3, GCS, Azure Blob)
- kailash-analytics (Google Analytics, Mixpanel)

### 4. UI & Admin
- kailash-admin (admin dashboard)
- kailash-forms (form builder)
- kailash-reports (report generator)

### 5. AI & ML
- kailash-ai-support (customer support agent)
- kailash-document-processor (document extraction)
- kailash-vision-analyzer (image analysis)
- kailash-embeddings (vector embeddings)

### 6. Utilities
- kailash-schedulers (background jobs, cron)
- kailash-webhooks (webhook handlers)
- kailash-monitoring (Prometheus, Grafana)
- kailash-logging (structured logging)

---

## Quality Standards

### Official Component Requirements

**Code Quality:**
- ✅ Type hints on all public APIs
- ✅ Docstrings on all classes and methods
- ✅ Black-formatted code
- ✅ Ruff linting passing
- ✅ No security vulnerabilities

**Testing:**
- ✅ 80%+ code coverage
- ✅ Unit tests (Tier 1 - mocked)
- ✅ Integration tests (Tier 2 - real infrastructure)
- ✅ E2E tests (Tier 3 - complete user flow)
- ✅ All tests passing on CI

**Documentation:**
- ✅ README.md with quick start (5 min to working code)
- ✅ CLAUDE.md with AI instructions
- ✅ API reference
- ✅ At least 3 examples
- ✅ CHANGELOG.md

**Compatibility:**
- ✅ Supports Python 3.10+
- ✅ Declares Kailash version range
- ✅ Works with PostgreSQL, MySQL, SQLite
- ✅ No undeclared dependencies

### Verified Component Requirements (Community)

**Reduced standards:**
- ✅ 60%+ code coverage (vs 80% official)
- ✅ Basic tests (unit + integration)
- ✅ README with quick start
- ✅ Reviewed by Kailash team (security, quality)

**Review process:**
1. Component submitted to GitHub
2. Automated checks (tests, coverage, linting)
3. Manual review (code quality, security)
4. Approved → marked as "verified"

### Community Components (Unreviewed)

**Minimal requirements:**
- ✅ Published to PyPI
- ✅ Named `kailash-{component}`
- ✅ Basic README

**No review process:**
- Users install at own risk
- Marked clearly as "community" (not verified)

---

## Monetization (Future)

### Free Tier
- All official components (free and open source)
- Community components (free)
- No restrictions

### Premium Components (Future)
- Enterprise-only features (SSO, advanced RBAC)
- Proprietary integrations (Salesforce, Oracle)
- Pricing: $50-500/month per component
- Revenue share: 70% developer, 30% Kailash

### Marketplace Revenue (Future - Phase 3)
- Transaction fee: 20% of premium component sales
- Featured placement: $100/month
- Verified badge: Free (quality incentive)

---

## Component Versioning

### Semantic Versioning

**Strictly enforced:**
- MAJOR.MINOR.PATCH (e.g., 2.1.3)
- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

**Example:**
```
kailash-sso:
  1.0.0 - Initial release (OAuth2 only)
  1.1.0 - Added SAML support (backward compatible)
  1.2.0 - Added MFA support (backward compatible)
  1.2.1 - Fixed security vulnerability (patch)
  2.0.0 - Changed API signature (breaking change)
```

### Compatibility Matrix

**Components declare SDK version range:**
```toml
[project]
dependencies = [
    "kailash>=0.9.27,<1.0.0"  # Works with 0.9.x, not 1.x
]
```

**Installation checks compatibility:**
```bash
pip install kailash-sso

# Checks:
# ✅ kailash 0.9.27 installed
# ✅ kailash-sso 2.1.3 requires kailash>=0.9.27,<1.0.0
# ✅ Compatible - installing

# Or if incompatible:
# ❌ kailash-sso 2.1.3 requires kailash>=0.9.27
# ❌ You have kailash 0.8.0
# ❌ Upgrade kailash: pip install --upgrade kailash
```

### Upgrade Strategy

**Automatic security updates:**
```bash
# Check for updates
kailash marketplace outdated

# Output:
# 📦 kailash-sso
#    Installed: 2.1.2
#    Available: 2.1.3 (security update)
#    Changelog: Fixed CVE-2025-1234
#
# 📦 kailash-rbac
#    Installed: 1.5.0
#    Available: 2.0.0 (major update - breaking changes)
#    Changelog: See CHANGELOG.md

# Update all (patch/minor only)
kailash marketplace update-all

# Update specific component (including major)
kailash marketplace update kailash-rbac --major
```

---

## Success Metrics

### Adoption Metrics

**1. Component Install Rate**
- Target: 100 installs/month (Month 1)
- Growth: 50% month-over-month
- Measure: PyPI download stats

**2. Component Usage**
- Target: 80% of projects use ≥1 component
- Measure: Detect imports in user projects (telemetry)
- Baseline: 0% (currently rebuild everything)

**3. Average Components Per Project**
- Target: 3 components per project
- Measure: Telemetry + surveys
- Indicates: Ecosystem value

### Ecosystem Metrics

**4. Community Components**
- Target: 5 community components (Month 6)
- Target: 50 community components (Month 12)
- Measure: PyPI packages with `kailash-` prefix

**5. Component Contributors**
- Target: 20 developers publishing components (Month 12)
- Measure: Unique authors on PyPI
- Indicates: Ecosystem health

**6. Verified Components**
- Target: 15 verified components (Month 12)
- Process: Community submits → review → verify
- Indicates: Quality standards maintained

### Quality Metrics

**7. Component Satisfaction (NPS)**
- Target: NPS 50+ for official components
- Target: NPS 35+ for verified components
- Measure: Quarterly survey

**8. Security Issues**
- Target: <1 security issue per quarter (official)
- Process: Automated CVE scanning + manual audits
- Indicates: Component quality

---

## Testing Strategy

### Unit Tests (Tier 1)

```python
# Test component installation
def test_component_imports_correctly():
    """Test that component can be imported after installation."""
    import kailash_sso
    assert hasattr(kailash_sso, 'SSOManager')

def test_component_workflow_generation():
    """Test that component generates workflows correctly."""
    from kailash_sso import SSOManager

    sso = SSOManager(providers={"google": {...}})
    workflow = sso.login_workflow()

    assert workflow is not None
    assert len(workflow.nodes) > 0
```

### Integration Tests (Tier 2)

```python
# Test component with real infrastructure
def test_sso_oauth2_flow():
    """Test OAuth2 flow with real provider (requires credentials)."""
    from kailash_sso import SSOManager
    from kailash.runtime.local import LocalRuntime

    sso = SSOManager(
        providers={
            "google": {
                "client_id": os.getenv("GOOGLE_CLIENT_ID"),
                "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
                "redirect_uri": "http://localhost:8000/callback"
            }
        },
        jwt_secret="test-secret"
    )

    # Test login workflow
    workflow = sso.login_workflow()
    runtime = LocalRuntime()

    # Note: This test requires mocking OAuth2 callback
    # Or manual testing with real OAuth2 flow
    # (E2E test)
```

### E2E Tests (Tier 3)

```python
# Test complete user journey
def test_complete_sso_integration():
    """Test complete SSO flow in real application."""

    # Setup: Create test application using template
    # ... (template generation)

    # Install component
    subprocess.run(["pip", "install", "kailash-sso"], check=True)

    # Configure in app
    # ... (modify app code)

    # Run app
    # ... (start server)

    # Test OAuth2 flow
    # 1. Initiate login
    # 2. Follow OAuth2 redirect
    # 3. Verify callback success
    # 4. Verify JWT token generated
    # 5. Verify user session created

    # Complete user journey validation
```

---

## Component Maintenance

### Official Components (Kailash Team Responsibility)

**Monthly:**
- Dependency updates
- Security scanning
- Bug fixes from community

**Quarterly:**
- Feature additions (based on user feedback)
- Performance optimization
- Documentation updates

**Annually:**
- Major version releases (if needed)
- Architecture reviews
- Deprecation notices (6 months advance)

### Community Components (Author Responsibility)

**Kailash team provides:**
- CI/CD templates
- Testing infrastructure
- Documentation templates
- Security scanning tools

**Authors maintain:**
- Bug fixes
- Feature development
- User support

**If unmaintained:**
- Mark as "unmaintained" after 6 months of inactivity
- Consider forking to official (if popular)

### Deprecation Policy

**Official components:**
1. Deprecation notice (6 months advance)
2. Migration guide published
3. Backward compatibility maintained for 12 months
4. Final sunset (with clear alternatives)

**Community components:**
- Authors can deprecate anytime
- Kailash team may fork popular components

---

## Implementation Timeline

**Weeks 13-14: Infrastructure**
- Component template (cookiecutter)
- CLI commands (search, install, update)
- Quality standards documentation

**Weeks 15-16: First Component (kailash-dataflow-utils)**
- Implement TimestampField, JSONField, UUIDField
- Write tests (Tier 1, 2, 3)
- Publish to PyPI
- Validate installation flow

**Weeks 17-18: kailash-sso**
- OAuth2 implementation
- JWT token management
- Tests with real providers
- Documentation

**Weeks 19-20: kailash-rbac**
- Role management
- Permission checking
- Middleware integration
- Tests

**Weeks 21-22: kailash-admin + kailash-payments**
- Admin dashboard (React UI + Kailash backend)
- Payment workflows (Stripe)
- Integration examples
- Templates updated to use components

**Weeks 23-24: Launch + Community**
- Public announcement
- Component submission guidelines
- First community component verified
- Marketplace catalog v1

---

## Key Takeaways

**Component marketplace solves the reusability problem directly:**
- Install vs rebuild (4 hours → 10 minutes)
- Versioned and upgradeable (vs forked code)
- Battle-tested (vs generated from docs)
- Ecosystem growth (developers contribute)

**Success depends on:**
- **Quality of official components** (must be excellent)
- **Ease of discovery** (PyPI + optional catalog)
- **Community engagement** (contribution guidelines, incentives)
- **Maintenance commitment** (official components always updated)

**If developers build components and IT teams consume them, the flywheel starts.**

---

**Next:** See `05-official-components.md` for detailed specifications of the 5 initial official components
