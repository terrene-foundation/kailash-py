# Templates Team: Developer Instructions

**Team:** Templates Development (MOST CRITICAL TEAM)
**Timeline:** Weeks 1-8 (FIRST PRIORITY)
**Estimated Effort:** 120 hours
**Priority:** CRITICAL (foundation of entire repivot)

---

## Your Responsibilities

You are building the foundation of the repivot:

1. ✅ Build SaaS Starter template (Weeks 1-4)
2. ✅ Build Internal Tools template (Weeks 5-6)
3. ✅ Build API Gateway template (Weeks 7-8)
4. ✅ Create 10 Golden Patterns documentation
5. ✅ Test templates with Claude Code
6. ✅ Create CUSTOMIZE.md guides

**Impact:** This is the FIRST thing IT teams will see. If templates succeed, repivot succeeds.

---

## Required Reading

### MUST READ (4 hours):

**1. Strategic Context (1 hour):**
- `../01-strategy/00-overview.md` - Understand the vision
- `../01-strategy/01-problem-analysis.md` - Understand root cause #1 (documentation vs artifacts)
- `../01-strategy/02-market-opportunity.md` - Understand IT teams persona

**2. Your Specifications (2 hours):**
- `../02-implementation/02-new-components/01-templates-specification.md` - Complete spec (839 lines)
- `../02-implementation/02-new-components/03-golden-patterns.md` - 10 patterns to embed (1,300 lines)

**3. Integration Context (1 hour):**
- `../02-implementation/04-integration/00-integration-overview.md` - How templates integrate with everything
- `../04-prototype-plan/00-validation-prototype.md` - Validation criteria

**Total reading:** 4 hours (DO NOT SKIP - critical for success)

### SHOULD READ:

- `../02-implementation/02-new-components/02-quick-mode-specification.md` - Templates may use Quick Mode
- All codebase analysis docs - Understand what you're configuring

---

## Detailed Tasks

### Task 1: SaaS Starter Template (Weeks 1-4, 60 hours) - HIGHEST PRIORITY

**This is the most important task in the entire repivot.**

**Directory to create:**
```
templates/saas-starter/
├── README.md
├── CUSTOMIZE.md           # ← Most important file for users
├── main.py
├── config.py
├── .env.example
├── requirements.txt
├── pyproject.toml
├── models/
│   ├── __init__.py
│   ├── user.py            # ← Embed Pattern #1
│   ├── organization.py    # ← Embed Pattern #6
│   └── session.py
├── workflows/
│   ├── __init__.py
│   ├── auth.py            # ← Embed Pattern #5
│   ├── users.py           # ← Embed Pattern #2
│   └── admin.py           # ← Embed Pattern #10
├── tests/
│   ├── test_auth.py
│   └── test_workflows.py
└── docs/
    ├── architecture.md
    ├── api-reference.md
    └── deployment.md
```

**Specification reference:** `02-new-components/01-templates-specification.md` (complete file)

---

#### Week 1: Template Structure + Core Models

**Day 1-2: Project Structure**

```bash
> Use the requirements-analyst subagent to break down SaaS template requirements into file structure, models, workflows, and documentation components

> Use the ultrathink-analyst subagent to analyze what makes an excellent SaaS template and identify potential failure points in template design

> Use the todo-manager subagent to create detailed day-by-day breakdown for building SaaS template
```

Create:
- Directory structure
- README.md (overview, quick start)
- .env.example (all config variables documented)
- requirements.txt (kailash, dataflow, nexus, components)

**Day 3: User Model with AI Instructions**

```bash
> Use the sdk-navigator subagent to find best examples of DataFlow models in existing SDK

> Use the dataflow-specialist subagent to design User model with authentication fields following DataFlow best practices
```

Create `models/user.py`:
```python
"""User model for authentication and profile management.

AI INSTRUCTIONS:
================
This model uses DataFlow's @db.model decorator to auto-generate 9 workflow nodes.

COMMON CUSTOMIZATIONS:
1. ADD A FIELD:
   phone: Optional[str] = None  # ← Just add this line

2. MAKE FIELD REQUIRED:
   phone: str  # ← Remove Optional and default

3. ADD VALIDATION:
   __dataflow__ = {'validators': {'phone': r'^\+?[0-9]{10,15}$'}}

COMMON MISTAKES TO AVOID:
❌ datetime.now().isoformat() → Use TimestampField.now()
❌ Don't include created_at/updated_at → Auto-managed
❌ Don't use user_id as primary key → Must be 'id'

USAGE IN WORKFLOWS:
workflow.add_node("UserCreateNode", "create_user", {
    "id": UUIDField.generate(),
    "email": "user@example.com",
    "name": "Alice"
})

SEE: Golden Pattern #1 - Add DataFlow Model
"""

from dataflow import DataFlow
from kailash_dataflow_utils import UUIDField, TimestampField
from datetime import datetime
from typing import Optional

db = DataFlow("postgresql://...")  # From env: DATABASE_URL

@db.model
class User:
    """User model with multi-tenancy and authentication."""
    id: str
    email: str
    name: str
    hashed_password: str
    is_active: bool = True
    is_admin: bool = False
    # created_at, updated_at added automatically
    # tenant_id added automatically if multi_tenant=True
```

**Critical:** Every file MUST have AI instructions as comments

**Day 4-5: Organization and Session Models**

```bash
> Use the dataflow-specialist subagent to design Organization model for multi-tenancy following DataFlow multi-tenant patterns

> Use the intermediate-reviewer subagent to review all 3 models ensuring they follow best practices and have comprehensive AI instructions
```

**Week 1 Deliverable:** Models complete with AI instructions

---

#### Week 2: Auth Workflows

**Day 6-7: Login Workflow**

```bash
> Use the sdk-navigator subagent to find authentication workflow examples in existing SDK documentation

> Use the pattern-expert subagent to implement login workflow following Kailash workflow patterns and incorporating error handling
```

Create `workflows/auth.py`:
```python
"""Authentication workflows.

AI INSTRUCTIONS:
================
SEE: Golden Pattern #5 - Authentication Workflow

These workflows handle user authentication:
- register: Create new user account
- login: Authenticate existing user
- logout: Invalidate session

TO CUSTOMIZE:
1. Add fields to registration (edit register_workflow)
2. Change token expiration (edit config.py JWT_EXPIRY)
3. Add OAuth providers (pip install kailash-sso recommended)

COMMON MISTAKES:
❌ Storing plain text passwords → Always hash
❌ Weak JWT secret → Use strong random string
❌ No password validation → Add min length, complexity
"""

from kailash.workflow.builder import WorkflowBuilder
from kailash_dataflow_utils import UUIDField
import hashlib

def register_workflow():
    """User registration workflow.

    Inputs:
        - email: str
        - name: str
        - password: str (plain text, will be hashed)

    Returns:
        - user: dict (created user, no password)
        - token: str (JWT for immediate login)
    """
    workflow = WorkflowBuilder()

    # Step 1: Check if email exists
    workflow.add_node("UserListNode", "check_existing", {
        "filters": {"email": "{{ email }}"},
        "limit": 1
    })

    # Step 2: Hash password
    workflow.add_node("PythonCodeNode", "hash_password", {
        "code": """
import hashlib
hashed = hashlib.sha256(inputs['password'].encode()).hexdigest()
return {'hashed_password': hashed}
        """,
        "inputs": {"password": "{{ password }}"}
    })

    # ... (complete implementation following spec)

    return workflow.build()

# SEE: Golden Pattern #5 for complete authentication pattern
# OR: Use kailash-sso for production-ready auth (pip install kailash-sso)
```

**Day 8-10: Test Auth Workflows**

```bash
> Use the tdd-implementer subagent to create comprehensive tests for registration and login workflows

> Use the testing-specialist subagent to verify auth workflows work with real database and proper security
```

**Week 2 Deliverable:** Auth workflows complete and tested

---

#### Week 3: CRUD Workflows + Main Entry Point

**Day 11-12: User CRUD Workflows**

```bash
> Use the pattern-expert subagent to implement user management workflows (create, read, update, list)

> Use the dataflow-specialist subagent to ensure workflows correctly use DataFlow-generated nodes
```

**Day 13-14: Main.py + Nexus Setup**

```bash
> Use the nexus-specialist subagent to implement main.py with Nexus initialization and workflow registration

> Use the intermediate-reviewer subagent to review complete template ensuring all pieces integrate correctly
```

Create `main.py`:
```python
"""Main application entry point.

AI INSTRUCTIONS:
================
SEE: Golden Pattern #3 - Deploy with Nexus

To add a new workflow:
1. Create workflow in workflows/ directory
2. Import here: from workflows.myworkflows import my_workflow
3. Register: nexus.register("my_workflow", my_workflow())
4. Automatically available on API, CLI, and MCP
"""

from nexus import Nexus
from dataflow import DataFlow
import os

# Initialize DataFlow
db = DataFlow(
    database_url=os.getenv("DATABASE_URL"),
    multi_tenant=True,
    audit_logging=True
)

# Import models (triggers registration)
from models import user, organization, session

# Import workflows
from workflows import auth, users, admin

# Initialize Nexus with SaaS preset
nexus = Nexus.for_saas()  # ← Configuration preset

# Register workflows
nexus.register("register", auth.register_workflow())
nexus.register("login", auth.login_workflow())
nexus.register("get_profile", users.get_profile_workflow())
# ... (all workflows)

if __name__ == "__main__":
    nexus.start()
```

**Day 15: Integration Testing**

```bash
> Use the testing-specialist subagent to run end-to-end tests of complete SaaS template from creation to deployment
```

**Week 3 Deliverable:** Complete working SaaS template

---

#### Week 4: CUSTOMIZE.md + Documentation + Beta Testing

**Day 16-17: CUSTOMIZE.md (CRITICAL DOCUMENT)**

This is what users read to customize the template.

```bash
> Use the documentation-validator subagent to create comprehensive CUSTOMIZE.md with step-by-step instructions and code examples
```

Create `CUSTOMIZE.md`:
```markdown
# Customizing Your SaaS

This template provides a working multi-tenant SaaS. Make it yours in 5 steps.

## Step 1: Configure Database (5 minutes)

```bash
cp .env.example .env
# Edit .env, set DATABASE_URL
```

## Step 2: Add Your Business Models (15 minutes)

Example: Adding a "Product" model

[... complete step-by-step with code examples ...]

## Step 3: Customize Authentication (10 minutes)

[... steps to add fields to registration ...]

## Step 4: Add Business Workflows (30 minutes)

[... how to create custom workflows ...]

## Step 5: Deploy (15 minutes)

[... deployment steps ...]

## Using Claude Code

This template is optimized for Claude Code:

Prompt: "Add a Product model with name, price, and description"

Claude Code will:
1. Create models/product.py
2. Generate workflows (optional)
3. Update main.py to register

[... more AI assistance examples ...]
```

**THIS DOCUMENT DETERMINES SUCCESS.** If users can customize easily, template succeeds.

**Day 18-19: Template Testing**

```bash
# Test template generation
> Use the testing-specialist subagent to test template generation process and verify generated project works correctly

# Test with Claude Code (CRITICAL)
# Prompt Claude Code: "Add Product model"
# Verify it successfully customizes template
```

Test scenarios:
1. Generate template → should work in <5 min
2. Run `kailash dev` → should start successfully
3. Add model with Claude Code → should work first try
4. Deploy to staging → should work without errors

**Day 20: Beta Testing Prep**

```bash
> Use the intermediate-reviewer subagent to review complete SaaS template and validate it meets all requirements before beta testing
```

Prepare:
- Beta testing script
- Feedback survey
- Known issues list

**Week 4 Deliverable:** SaaS template ready for beta testing

---

### Task 2: Internal Tools Template (Weeks 5-6, 30 hours)

**Based on learnings from SaaS template.**

**Key differences:**
- SQLite database (not PostgreSQL) - faster for internal tools
- No multi-tenancy (single organization)
- API + CLI focus (MCP optional)
- Scheduled jobs (cron patterns)

**Reuse from SaaS:**
- Auth pattern (simpler - no OAuth2)
- Model pattern (same DataFlow approach)
- Workflow pattern (same structure)

**Timeline:**
- Week 5: Structure + models + workflows (20 hours)
- Week 6: CUSTOMIZE.md + testing (10 hours)

---

### Task 3: API Gateway Template (Weeks 7-8, 30 hours)

**Key differences:**
- No database (stateless by default)
- Focus on orchestration and transformation
- Rate limiting and caching
- Request/response transformation

**Timeline:**
- Week 7: Structure + workflows (20 hours)
- Week 8: CUSTOMIZE.md + testing (10 hours)

---

## Golden Patterns Documentation

**Integrate throughout all templates:**

Create `templates/saas-starter/PATTERNS.md`:
```markdown
# Golden Patterns Reference

This template demonstrates all 10 Golden Patterns.

## Pattern 1: Add DataFlow Model
Location: models/user.py (lines 20-50)
[... pattern documentation ...]

## Pattern 2: Create Workflow
Location: workflows/users.py (lines 10-40)
[... pattern documentation ...]

[... all 10 patterns ...]

These patterns solve 80% of use cases. For advanced scenarios, see Full SDK documentation.
```

**Also create:**
- `.claude/context/golden-patterns.md` (auto-used by Claude Code)
- Each pattern embedded in relevant files as comments

---

## Subagent Workflow for Templates Team

### Week 1: SaaS Template Planning

**Day 1:**
```bash
# Strategic understanding
> Use the ultrathink-analyst subagent to deeply analyze what makes an excellent SaaS template for IT teams using AI assistants

# Requirements breakdown
> Use the requirements-analyst subagent to break down SaaS template into models, workflows, configuration, documentation, and testing requirements

# Create ADR
> Document architectural decisions for template structure
```

**Day 2:**
```bash
# Review existing patterns
> Use the sdk-navigator subagent to find best examples of DataFlow models, Nexus deployment, and workflow patterns across SDK documentation

# Get framework guidance
> Use the framework-advisor subagent to validate using DataFlow + Nexus for SaaS template and get integration guidance

> Use the dataflow-specialist subagent to review multi-tenant model design and auto-generated node usage patterns

> Use the nexus-specialist subagent to review multi-channel deployment and session management patterns for SaaS
```

**Day 3:**
```bash
# Task breakdown
> Use the todo-manager subagent to create detailed task breakdown for SaaS template with daily milestones

# Validate approach
> Use the intermediate-reviewer subagent to review template design and validate it meets IT team needs before implementation
```

**Day 4-5:**
```bash
# Create project structure
# Write initial README and .env.example
```

---

### Week 2: Models and Workflows

**Day 6-8:**
```bash
# Implement models
> Use the dataflow-specialist subagent to implement User, Organization, and Session models with comprehensive AI instructions embedded

# For each model, ensure:
# - Proper type hints
# - AI instructions as docstrings
# - Common mistakes documented
# - Golden Pattern references
```

**Day 9-10:**
```bash
# Implement workflows
> Use the pattern-expert subagent to implement authentication and user management workflows following established patterns

> Use the intermediate-reviewer subagent to review workflows ensuring they're simple enough for IT teams but complete enough for production
```

---

### Week 3: Main.py and Integration

**Day 11-12:**
```bash
# Implement main.py
> Use the nexus-specialist subagent to implement Nexus initialization and workflow registration for multi-tenant SaaS

# Test complete integration
> Use the testing-specialist subagent to verify all models, workflows, and Nexus deployment work together correctly
```

**Day 13-15:**
```bash
# Test template generation
# Create CLI command to generate template (or coordinate with CLI team)

> Use the testing-specialist subagent to test complete template generation and startup process

# Verify:
# - Template generates correctly
# - All files present
# - No syntax errors
# - Project runs with kailash dev
```

---

### Week 4: CUSTOMIZE.md and Beta Testing

**Day 16-18: Write CUSTOMIZE.md (CRITICAL)**

```bash
> Use the documentation-validator subagent to create comprehensive CUSTOMIZE.md with tested, working examples for all common customizations

# This document determines if IT teams can successfully customize
# Spend quality time here - test every example
```

**CUSTOMIZE.md must include:**
1. Configure database (copy-paste commands)
2. Add business models (complete code example)
3. Customize authentication (step-by-step)
4. Add workflows (template to copy)
5. Deploy to production (deployment guide)
6. Using Claude Code (AI assistance examples)

**Each section:**
- Time estimate (5 min, 15 min, 30 min)
- Complete code example (tested, working)
- Expected outcome (what you'll see)
- Troubleshooting (common issues)

**Day 19: Test with Claude Code**

```bash
# CRITICAL TEST: Use Claude Code to customize template

# Prompts to test:
> "Add a Product model with name, price, description"
> "Add an endpoint to list products"
> "Add multi-tenancy to products"

# Claude Code should:
# - Find Golden Patterns in code
# - Generate correct code
# - Make it work first try (70%+ success rate goal)

# If Claude Code fails:
# - Improve AI instructions
# - Add more examples
# - Clarify patterns
```

**Day 20: Beta Test Prep**

```bash
> Use the intermediate-reviewer subagent to perform final review of SaaS template ensuring it's ready for beta testers

# Prepare beta test package:
# - Testing script
# - Feedback survey
# - Known issues list
# - Support channel info
```

**Week 4 Deliverable:** SaaS template ready for beta testing

---

### Week 5-6: Internal Tools Template (30 hours)

**Faster than SaaS (reuse patterns):**

```bash
# Week 5: Build template
> Use the pattern-expert subagent to adapt SaaS template patterns for internal tools use case

> Use the dataflow-specialist subagent to configure for SQLite and single-tenant mode

# Week 6: Test and document
> Use the testing-specialist subagent to verify internal tools template works for common internal tool scenarios

> Use the documentation-validator subagent to create CUSTOMIZE.md for internal tools template
```

**Key differences from SaaS:**
- SQLite database (not PostgreSQL)
- Single-tenant (simpler)
- Basic auth (no OAuth2 needed)
- CLI-focused (not API-first)

---

### Week 7-8: API Gateway Template (30 hours)

```bash
# Week 7: Build template
> Use the nexus-specialist subagent to design API gateway template focused on orchestration and transformation

> Use the pattern-expert subagent to implement request routing, transformation, and rate limiting workflows

# Week 8: Test and document
> Use the testing-specialist subagent to verify API gateway template handles common gateway scenarios

> Use the documentation-validator subagent to ensure API gateway CUSTOMIZE.md is clear for DevOps engineers
```

**Key differences:**
- No database (stateless)
- Orchestration-focused
- Rate limiting and caching
- Multiple upstream APIs

---

## Testing Protocol

### Template Generation Tests

```python
# tests/templates/test_template_generation.py

def test_saas_template_generates_correctly():
    """Test SaaS template generates all required files."""
    # Generate template
    result = generate_template("saas-starter", "test-saas")

    # Verify structure
    assert Path("test-saas/main.py").exists()
    assert Path("test-saas/models/user.py").exists()
    assert Path("test-saas/CUSTOMIZE.md").exists()
    # ... verify all files

def test_generated_project_runs():
    """Test that generated project starts successfully."""
    generate_template("saas-starter", "test-saas")

    # Set up environment
    env_file = Path("test-saas/.env")
    env_file.write_text("DATABASE_URL=sqlite:///test.db")

    # Run project
    process = subprocess.Popen(["python", "main.py"], cwd="test-saas")
    time.sleep(3)  # Wait for startup

    try:
        # Verify server started
        response = requests.get("http://localhost:8000/health")
        assert response.status_code == 200
    finally:
        process.terminate()
```

### AI Customization Tests

```python
# tests/templates/test_ai_customization.py

def test_claude_code_can_add_model():
    """Test that Claude Code successfully adds model to template."""

    generate_template("saas-starter", "test-saas")

    # Simulate Claude Code prompt
    prompt = "Add a Product model with name: str, price: float, description: str"

    # Claude Code should:
    # 1. Find Golden Pattern #1 in models/user.py
    # 2. Create models/product.py following pattern
    # 3. Update main.py to import product (if needed)

    # Verify:
    # - File created correctly
    # - Syntax valid
    # - DataFlow generates nodes
    # - Workflow can use ProductCreateNode

    # This tests the AI instructions are effective
```

---

## Success Criteria (Critical)

### SaaS Template

**Must achieve (beta testing):**
- [ ] 80% of testers get working app in <30 minutes
- [ ] 70% of Claude Code customizations work first try
- [ ] 90% would use for real project
- [ ] NPS 40+ from IT teams
- [ ] CUSTOMIZE.md rated "clear and helpful" (80%+)

**If not achieved:**
- Iterate template
- Improve AI instructions
- Simplify setup
- Add more examples

**This is the validation gate - don't proceed to templates 2-3 until template 1 succeeds**

### All Templates

**Must have:**
- [ ] Working in <5 minutes from generation
- [ ] AI instructions embedded in every file
- [ ] CUSTOMIZE.md comprehensive and tested
- [ ] Golden Patterns demonstrated
- [ ] Tests covering common customizations
- [ ] Production deployment guide

---

## Beta Testing Responsibilities

**Your role in beta testing:**

1. **Prepare beta test package** (Day 20, Week 4)
2. **Support beta testers** (Week 5 for SaaS template)
3. **Collect feedback** (surveys, interviews)
4. **Iterate based on feedback** (Week 5-6)
5. **Validate success criteria** (end of Week 6)

**Beta testing script example:**
```markdown
# SaaS Template Beta Test

## Task 1: Generate and Run (Target: <10 minutes)
1. kailash create my-saas --template=saas-starter
2. cd my-saas
3. cp .env.example .env
4. kailash dev

Time: ______ minutes
Issues: _____________

## Task 2: Customize with Claude Code (Target: <20 minutes)
Prompt: "Add a Product model with name, price, description"

Success? Y/N
Time: ______ minutes
Claude Code tokens: ______
Issues: _____________

## Task 3: Deploy to Staging (Target: <30 minutes)
Follow deployment guide

Success? Y/N
Time: ______ minutes
Issues: _____________

## Feedback
[... survey questions ...]
```

---

## Common Pitfalls for Templates Team

### ❌ Making Templates Too Complex

**Wrong:** 20+ files, 10+ models, advanced features
**Right:** 8-12 files, 3-5 models, essential features only

**Principle:** Minimal but complete (can add, not remove)

### ❌ Weak AI Instructions

**Wrong:**
```python
# Add models here
```

**Right:**
```python
"""
AI INSTRUCTION: To add a new model, copy this pattern:
[complete example with annotations]

COMMON MISTAKES:
[list of mistakes to avoid]

USAGE:
[how to use generated nodes]
"""
```

### ❌ Not Testing with Claude Code

**Must test:**
- Generate template
- Prompt Claude Code with common customizations
- Verify it works first try (70%+ success rate)
- If fails, improve AI instructions

### ❌ Forgetting CUSTOMIZE.md

**Templates without good CUSTOMIZE.md = failure**
- Users won't know how to customize
- Will abandon or ask for support
- NPS will be low

**CUSTOMIZE.md is as important as the code.**

---

## Coordination with Other Teams

**Week 4: DataFlow Team**
- Get kailash-dataflow-utils package
- Integrate into templates
- Test error prevention

**Week 6: Nexus Team**
- Get configuration presets
- Update main.py to use presets
- Test integration

**Week 8: CLI Team**
- Finalize template.json format
- Test template generation command
- Verify variable substitution

**Week 8: Quick Mode Team (if separate)**
- Discuss if templates should use Quick Mode
- Decide on Level 1 (Quick Mode) vs Level 2 (Full SDK)
- Current plan: Full SDK with optional Quick Mode upgrade

---

## Your Success Metrics

**Templates succeed if:**
- ✅ 80% of new projects use templates (not blank)
- ✅ Time-to-first-screen <30 minutes (90th percentile)
- ✅ 70% of Claude Code customizations work first try
- ✅ NPS 40+ from IT teams
- ✅ Template satisfaction: 8+/10

**Templates fail if:**
- ❌ <40% use templates (users prefer blank)
- ❌ Time-to-first-screen >1 hour
- ❌ <50% Claude Code success rate
- ❌ NPS <25
- ❌ Negative feedback dominant

**If templates fail, entire repivot needs reconsideration.**

**This is THE most critical team. Everything depends on template quality.**

---

## Timeline Summary

**Week 1:** SaaS structure + models (40 hours)
**Week 2:** SaaS workflows (40 hours)
**Week 3:** SaaS main.py + integration (40 hours)
**Week 4:** SaaS CUSTOMIZE.md + beta prep (40 hours)
**Week 5-6:** Internal Tools template (30 hours)
**Week 7-8:** API Gateway template (30 hours)

**Total: 220 hours over 8 weeks** (2 developers at 20 hours/week = 160 hours total, OR 1 developer at 27.5 hours/week)

Wait, math doesn't add up. Let me recalculate:
- Week 1-4: 60 hours (SaaS)
- Week 5-6: 30 hours (Internal Tools)
- Week 7-8: 30 hours (API Gateway)
- Total: 120 hours ✓ (matches original estimate)

**Can be done by:**
- 1 developer full-time (3 weeks)
- OR 1 developer part-time (8 weeks at 15 hours/week)
- OR 2 developers part-time (4 weeks at 15 hours/week each)

---

**You are building the first impression of the repivot. Make it amazing. IT teams will judge Kailash by template quality. No pressure. 😊**

**But seriously: This is the most important work in the entire repivot. Invest the time to make templates excellent.**
