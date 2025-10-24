# Components Team: Developer Instructions

**Team:** Marketplace Components Development
**Timeline:** Weeks 13-22 (after templates, Quick Mode, CLI complete)
**Estimated Effort:** 200 hours (40 hours × 5 components)
**Priority:** High (enables ecosystem)

---

## Your Responsibilities

Build the 5 initial official marketplace components:

1. ✅ kailash-sso (OAuth2, JWT, SAML authentication) - 40 hours
2. ✅ kailash-rbac (Role-based access control) - 40 hours
3. ✅ kailash-admin (Admin dashboard) - 40 hours
4. ✅ kailash-payments (Stripe, PayPal integration) - 40 hours
5. ✅ kailash-dataflow-utils (Field helpers) - 40 hours

**Note:** kailash-dataflow-utils built by DataFlow team (Weeks 3-4), you build the other 4

**Impact:** Set quality standard for entire marketplace ecosystem

---

## Required Reading

### MUST READ (3 hours):

**1. Strategic Context (30 min):**
- `../01-strategy/03-dual-market-thesis.md` - Why marketplace creates flywheel

**2. Marketplace Specification (2 hours):**
- `../02-implementation/02-new-components/04-marketplace-specification.md` - Complete spec (1,215 lines)
- `../02-implementation/02-new-components/05-official-components.md` - Your components (1,889 lines)

**3. Integration (30 min):**
- `../02-implementation/04-integration/00-integration-overview.md` - How components integrate

---

## Component Build Order

### Priority 1: kailash-sso (Weeks 13-15, 40 hours)

**Why first:** Most requested feature, used by 85% of applications

**Dependencies:** None (can start immediately)

**Specification:** `05-official-components.md` (Component 2, lines 350-700)

**What to build:**

**Public API:**
```python
from kailash_sso import SSOManager

sso = SSOManager(
    providers={
        "google": {"client_id": "...", "client_secret": "..."},
        "github": {...}
    },
    jwt_secret="secret"
)

# Pre-built workflows
login = sso.login_workflow()
register = sso.register_workflow()
logout = sso.logout_workflow()
```

**Features:**
- OAuth2 (Google, GitHub, Microsoft, custom)
- SAML (enterprise SSO)
- JWT token management
- Session management
- MFA support (basic)

**Testing:**
- Unit tests: Mock OAuth2 providers
- Integration tests: Real JWT, test OAuth2 flow patterns
- E2E tests: Manual (requires real OAuth2 credentials)

**Deliverable:** Package on PyPI, working in production

---

### Priority 2: kailash-rbac (Weeks 16-18, 40 hours)

**Why second:** Works with kailash-sso, needed by templates

**Dependencies:** kailash-sso (for integration testing)

**Specification:** `05-official-components.md` (Component 3, lines 700-1000)

**What to build:**

**Public API:**
```python
from kailash_rbac import RBACManager

rbac = RBACManager(
    db=db,
    roles={
        "admin": ["*"],
        "user": ["read:own", "write:own"]
    }
)

# Check permissions
authorized = rbac.has_permission(user_id, "delete:users")
```

**Features:**
- Role management (create, assign, revoke)
- Permission checking
- Resource-based permissions
- DataFlow models (Role, UserRole)
- Custom RBACCheckNode

**Testing:**
- Unit tests: Permission logic
- Integration tests: With DataFlow (real database)
- E2E tests: Complete auth + RBAC flow

---

### Priority 3: kailash-admin (Weeks 19-20, 40 hours)

**Why third:** Visual component, depends on RBAC

**Dependencies:** kailash-rbac (for permission-based UI)

**Specification:** `05-official-components.md` (Component 4, lines 1000-1300)

**What to build:**

**Public API:**
```python
from kailash_admin import AdminDashboard

admin = AdminDashboard(
    db=db,
    models=["User", "Organization", "Product"]
)

admin.register_with_nexus(nexus)
# Creates /admin routes
```

**Features:**
- Auto-generated CRUD UI for models
- React-based UI components
- Table, form, detail views
- Integration with RBAC (permission-based)

**Testing:**
- Unit tests: Workflow generation
- Integration tests: With DataFlow models
- E2E tests: UI interaction (Playwright/Selenium)

**Note:** Requires React knowledge

---

### Priority 4: kailash-payments (Weeks 21-22, 40 hours)

**Why fourth:** Specific use case (e-commerce, SaaS billing)

**Dependencies:** None (independent)

**Specification:** `05-official-components.md` (Component 5, lines 1300-1800)

**What to build:**

**Public API:**
```python
from kailash_payments import PaymentManager

payments = PaymentManager(
    db=db,
    providers={"stripe": {"api_key": "..."}}
)

charge = payments.charge_workflow()
refund = payments.refund_workflow()
```

**Features:**
- Stripe integration
- PayPal integration (optional)
- Payment workflows (charge, refund)
- Subscription workflows
- Webhook handling

**Testing:**
- Unit tests: Workflow structure
- Integration tests: With Stripe test mode
- E2E tests: Complete payment flow

---

## Component Development Standards

### Every Component MUST Have:

**1. Package Structure:**
```
packages/kailash-{component}/
├── src/kailash_{component}/
│   ├── __init__.py
│   ├── manager.py
│   └── workflows/
├── examples/
│   ├── basic_usage.py
│   └── advanced_usage.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── docs/
│   └── quickstart.md
├── README.md
├── CLAUDE.md
├── CHANGELOG.md
└── pyproject.toml
```

**2. Quality Standards:**
- 80%+ test coverage
- All public APIs documented
- CLAUDE.md with AI instructions
- 5-minute quick start in README
- Works with Quick Mode AND Full SDK

**3. Testing Requirements:**
- Tier 1 (unit): Mocked, fast
- Tier 2 (integration): Real infrastructure, NO MOCKING
- Tier 3 (E2E): Complete user flows

---

## Subagent Workflow for Components

### For EACH Component (Repeat 4 times)

**Week N: Planning**
```bash
# Day 1
> Use the sdk-navigator subagent to find similar components or patterns in existing SDK

> Use the requirements-analyst subagent to break down [component] into features, APIs, workflows, and testing requirements

> Use the ultrathink-analyst subagent to identify complexity and potential failure points in [component] design

# Day 2
> Use the todo-manager subagent to create detailed task breakdown for [component] development

> Use the framework-advisor subagent to determine if component should use Core SDK, DataFlow, Nexus, or Kaizen

> Use the intermediate-reviewer subagent to review component design before implementation
```

**Week N+1: Implementation**
```bash
# Day 3-5
> Use the tdd-implementer subagent to write comprehensive test suite for [component] before any implementation

# Day 6-8
> Use the pattern-expert subagent to implement [component] manager class and workflows following Kailash patterns

> Use the {framework}-specialist subagent to ensure proper integration with relevant frameworks (e.g., dataflow-specialist for RBAC)

# Day 9-10
> Use the testing-specialist subagent to run all tests and verify 80%+ coverage with real infrastructure in Tier 2-3

> Use the gold-standards-validator subagent to validate [component] follows all Kailash coding standards
```

**Week N+2: Polish and Publish**
```bash
# Day 11-12
> Use the documentation-validator subagent to test all code examples in README and CLAUDE.md

> Use the intermediate-reviewer subagent to review complete [component] before publishing

# Day 13-14
# Publish to PyPI
# Test installation and usage
# Update marketplace catalog

> Use the git-release-specialist subagent to create release with proper versioning and changelog
```

---

## Component-Specific Subagent Usage

### kailash-sso

```bash
# Additional specialists needed
> Use the security-specialist (if exists) or pattern-expert to review OAuth2 implementation for security vulnerabilities

# OAuth2 flow is complex
> Use the ultrathink-analyst subagent to review OAuth2 callback handling and token management for failure points
```

### kailash-rbac

```bash
# RBAC requires DataFlow integration
> Use the dataflow-specialist subagent to design Role and Permission models following DataFlow patterns

# Permission checking needs workflow integration
> Use the pattern-expert subagent to design RBACCheckNode for use in workflows
```

### kailash-admin

```bash
# Frontend component (React)
> Use the frontend-developer or react-specialist subagent to implement React UI components for admin dashboard

# DataFlow integration critical
> Use the dataflow-specialist subagent to ensure admin dashboard works with any DataFlow models

# Nexus integration
> Use the nexus-specialist subagent to ensure admin routes register correctly with Nexus
```

### kailash-payments

```bash
# External API integration
> Use the pattern-expert subagent to implement Stripe API workflows with proper error handling

# Financial operations require careful testing
> Use the testing-specialist subagent to ensure payment workflows are thoroughly tested with Stripe test mode
```

---

## Success Criteria (Per Component)

**Each component must achieve:**
- [ ] Published to PyPI
- [ ] Installation works: `pip install kailash-{component}`
- [ ] 5-minute quick start in README
- [ ] CLAUDE.md with AI instructions
- [ ] 80%+ test coverage
- [ ] All tests passing (Tier 1-3)
- [ ] Works with Quick Mode
- [ ] Works with Full SDK
- [ ] Integrates with other components (where applicable)

**Measure success by:**
- PyPI downloads (100+ in first month per component)
- User satisfaction (NPS 50+)
- Integration with templates (used by default)
- Production usage (50+ apps per component in 6 months)

---

## Integration Points

**With Templates Team:**
- Templates should recommend/use your components
- Update template CUSTOMIZE.md to reference components
- Test components in template context

**With DataFlow Team:**
- kailash-rbac needs DataFlow models
- Test integration with DataFlow validation

**With Nexus Team:**
- kailash-admin registers routes with Nexus
- Test multi-channel deployment

---

## Timeline Summary

**Weeks 13-15:** kailash-sso (40 hours)
**Weeks 16-18:** kailash-rbac (40 hours)
**Weeks 19-20:** kailash-admin (40 hours)
**Weeks 21-22:** kailash-payments (40 hours)

**Total: 160 hours over 10 weeks**

**Team size:** 2 developers at 16 hours/week each OR 1 developer at 16 hours/week for 20 weeks

---

**You are building the ecosystem. These components will be reused by hundreds of projects. Make them excellent.**
