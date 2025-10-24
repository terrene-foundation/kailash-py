# Nexus Developer: Sprint 1 (Prototype) Instructions

**Sprint:** Phase 0 - Prototype Validation
**Duration:** 4 weeks (Week 0-4)
**Your Workload:** 38 hours (9.5 hours/week average)
**Your Role:** Pair on template development, integrate Nexus deployment, write CUSTOMIZE.md

---

## Your Objectives

**Primary:**
1. Pair with DataFlow dev on SaaS template (learn DataFlow, teach Nexus)
2. Integrate Nexus multi-channel deployment
3. Write CUSTOMIZE.md guide (user-facing documentation)

**Success criteria:**
- Template deploys successfully via Nexus (API + CLI + MCP working)
- CUSTOMIZE.md rated "clear and helpful" by beta testers (80%+)
- Pairing productive (positive feedback from both you and DataFlow dev)

---

## Your Tasks (5 tasks, 38 hours)

| Task | Hours | Week | Role | Status |
|------|-------|------|------|--------|
| TODO-001: Template Structure | 4h | Week 1 | NAVIGATOR (review) | PENDING |
| TODO-002: Auth Models | 4h | Week 1 | NAVIGATOR (review) | PENDING |
| TODO-003: Auth Workflows | 4h | Week 1-2 | NAVIGATOR (review) | PENDING |
| TODO-004: Nexus Deployment | 6h | Week 2 | DRIVER (implement) | PENDING |
| TODO-005: CUSTOMIZE.md | 6h | Week 2 | DRIVER (write) | PENDING |
| TODO-013: Beta Testing | 8h | Week 4 | CO-FACILITATOR | PENDING |
| Reviews/Integration | 6h | Week 2-4 | SUPPORT | PENDING |

**Total: 38 hours over 4 weeks = 9.5 hours/week average**

---

## Week-by-Week Breakdown

### Week 1: Pair on Template Foundation (12 hours)

**Your role this week:** NAVIGATOR (review DataFlow dev's work, learn DataFlow, prepare for TODO-004)

**Monday (3 hours):**

**AM (9am-10am):**
- Kickoff meeting (1h, all 3 + PM)

**AM (10am-1pm):**
- Read TODO-001 + GitHub issue #458 (30 min)
- Read `.claude/improvements/repivot/09-developer-instructions/03-nexus-instructions.md` (your guide, 1h)
- Read DataFlow basics in `sdk-users/apps/dataflow/CLAUDE.md` (30 min)
- Read TODO-004, TODO-005 (your upcoming tasks, 30 min)

**PM (2pm-4pm): Pair Session 1 - Review TODO-001 Structure**
- DataFlow dev drives (creates structure)
- You navigate (ask questions, review, suggest)
- Focus: Learn how DataFlow models will be organized
- Note: Where Nexus will integrate (main.py, workflows)

**Takeaway:** Understand template structure before implementing Nexus integration

---

**Tuesday (3 hours):**

**AM (10am-1pm): Review TODO-001 Completion**

**Your responsibility as reviewer:**
```bash
# Review the structure
> Use the nexus-specialist subagent to validate that template structure accommodates Nexus multi-channel deployment properly

# Check integration points
- Is main.py ready for Nexus initialization?
- Are workflows structured for Nexus registration?
- Are there any Nexus-specific configs needed?
```

**Approval checklist:**
- [ ] Structure has main.py for Nexus entry point
- [ ] Workflows directory ready for workflow registration
- [ ] .env.example includes Nexus configs (API_PORT, MCP_PORT)
- [ ] No Nexus integration issues foreseen

**Provide feedback to DataFlow dev (GitHub comment or Slack)**

---

**Wednesday (3 hours):**

**AM (10am-1pm): Pair Session 2 - Review TODO-002 Models**

**Focus:**
- How will Nexus access these DataFlow models in API endpoints?
- What parameters will Nexus workflows need?
- Any multi-tenancy implications for Nexus session management?

**Start TODO-004 preparation:**
```bash
# Understand Nexus requirements
> Use the sdk-navigator subagent to find Nexus integration examples with DataFlow in existing SDK

> Use the nexus-specialist subagent to review best practices for integrating Nexus with DataFlow models

# Plan integration
> Use the requirements-analyst subagent to break down TODO-004 Nexus deployment task into specific integration steps
```

**Outcome:** Understand how you'll integrate Nexus in Week 2

---

**Thursday (3 hours):**

**AM (10am-1pm): Pair Session 3 - Review TODO-003 Workflows**

**Focus:**
- These workflows will be registered with Nexus
- Validate workflow structure is Nexus-compatible
- Plan how workflows will be exposed (API endpoints, CLI commands, MCP tools)

**Questions to ask DataFlow dev:**
- What parameters do these workflows expect?
- Are parameters Nexus-template-variable compatible? ({{ variable }})
- Any workflow-specific error handling needed?

**Outcome:** Deep understanding of workflows before registering with Nexus

---

**Friday (0 hours - unless issues found):**

**Tasks:**
- Participate in weekly retrospective (30 min)
- Plan Week 2 work (TODO-004 detailed plan)

**Week 1 total: 12 hours** (all pair/review work)

---

### Week 2: Nexus Integration & Documentation (12 hours)

**Monday-Tuesday (6 hours):**

**TODO-004: Nexus Deployment Integration** [#470]

**Monday AM (9am-1pm, 4h): IMPLEMENT**

**Subagent workflow:**
```bash
# Deep dive into Nexus configuration
> Use the nexus-specialist subagent to design Nexus initialization with .for_development() preset for SaaS template

> Use the pattern-expert subagent to review workflow registration patterns and multi-channel deployment best practices

# Integration planning
> Use the framework-advisor subagent to validate DataFlow + Nexus integration approach and identify potential issues
```

**Implementation:**

Update `main.py`:
```python
from nexus import Nexus
from dataflow import DataFlow
from workflows.auth import register_workflow, login_workflow, logout_workflow

# Initialize Nexus with development preset
nexus = Nexus.for_development()
# Future: Use .for_saas() in production

# Register auth workflows
nexus.register("register", register_workflow())
nexus.register("login", login_workflow())
nexus.register("logout", logout_workflow())

if __name__ == "__main__":
    print("🚀 SaaS Starter - Multi-Channel Deployment")
    print("   📡 API: http://localhost:8000")
    print("   💻 CLI: nexus run [workflow-name]")
    print("   🤖 MCP: stdio://localhost:3001")
    nexus.start()
```

**Tuesday AM (9am-11am, 2h): TEST & VALIDATE**

**Testing:**
```bash
# Integration tests
> Use the testing-specialist subagent to create integration tests for Nexus deployment with all 3 auth workflows

# Verify multi-channel works
# Test: python main.py (server starts)
# Test: curl http://localhost:8000/workflows/login/execute (API works)
# Test: nexus run login (CLI works) - if CLI available
# Test: MCP connection (basic validation)

# Ensure quality
> Use the gold-standards-validator subagent to validate Nexus integration follows best practices

> Use the intermediate-reviewer subagent to review complete Nexus deployment integration
```

**Acceptance:**
- [ ] Nexus initializes with .for_development()
- [ ] All 3 workflows registered successfully
- [ ] API endpoints accessible (POST /workflows/*/execute)
- [ ] No startup errors or warnings
- [ ] Tests pass (integration tests with real Nexus server)

**Mark TODO-004 COMPLETE**

---

**Wednesday-Friday (6 hours):**

**TODO-005: Write CUSTOMIZE.md** [#471]

**This is the most important user-facing document. Users judge template quality by this guide.**

**Wednesday AM (9am-1pm, 4h): WRITE**

**Subagent workflow:**
```bash
# Understand what users need
> Use the requirements-analyst subagent to break down what information IT teams need to customize the SaaS template successfully

# Find examples
> Use the sdk-navigator subagent to find existing customization guides or getting-started docs in SDK

# Validate content
> Use the documentation-validator subagent to ensure all code examples in CUSTOMIZE.md are tested and working
```

**Content to write:**

```markdown
# Customizing Your SaaS

This template provides a working multi-tenant SaaS. Make it yours in 5 steps.

## Step 1: Configure Database (5 minutes)

```bash
cp .env.example .env
# Edit .env:
# DATABASE_URL=postgresql://localhost/mydb
```

[... detailed steps with copy-paste commands ...]

## Step 2: Add Your Business Models (15 minutes)

Example: Adding a "Product" model

```python
# models/product.py

"""
AI INSTRUCTION: Copy this pattern to add any model
SEE: Golden Pattern #1 - Add DataFlow Model
"""

from dataflow import DataFlow

db = DataFlow()  # Configured in main.py

@db.model
class Product:
    id: str
    name: str
    price: float
    description: str = ""
    is_available: bool = True

# DataFlow auto-generates 9 nodes:
# - ProductCreateNode, ProductReadNode, ProductUpdateNode, etc.
```

[... complete step with register workflow, test, deploy ...]

## Step 3: Using Claude Code (10 minutes)

This template is optimized for Claude Code. To add a feature:

**Prompt:** "Add a Product model with name, price, description. Create workflows to create and list products."

**Claude Code will:**
1. Create models/product.py (following Pattern #1)
2. Create workflows/product_workflows.py (following Pattern #2)
3. Update main.py to import and register

**Test:** Run `python main.py` - new endpoints available

[... more steps: deploy, customize auth, add workflows ...]
```

**Thursday PM (2pm-4pm, 2h): TEST & REFINE**

- Test every code example (run them manually)
- Have Kaizen dev review for clarity
- Get feedback from DataFlow dev (technical accuracy)
- Refine based on feedback

**Acceptance:**
- [ ] All 5 steps documented with tested examples
- [ ] "Using Claude Code" section with specific prompts
- [ ] Common troubleshooting section
- [ ] Estimated time for each step (<30 min total)
- [ ] Kaizen dev approves (clarity)
- [ ] DataFlow dev approves (technical accuracy)

**Mark TODO-005 COMPLETE**

---

**Week 2 total: 12 hours**
**Running total: 24 hours**

---

### Week 3: Testing Support (4 hours)

**Your focus:** Help DataFlow dev test kailash-dataflow-utils integration

**Wednesday (2 hours):**

**PM (2pm-4pm): Test dataflow-utils in Template**

**Tasks:**
- Install kailash-dataflow-utils from Test PyPI
- Update template to use package
- Test that datetime errors are prevented
- Test workflow execution with field helpers

**Testing:**
```python
# Test in template context
from kailash_dataflow_utils import TimestampField, UUIDField

# In workflow
workflow.add_node("UserCreateNode", "create", {
    "id": UUIDField.generate(),  # Should work
    "name": "Test",
    "created_at": TimestampField.now()  # Should work
})

# Verify no "text = integer" error
```

**Provide feedback to DataFlow dev:**
- Does package integrate smoothly?
- Are imports working?
- Any Nexus-specific issues?

---

**Friday (2 hours):**

**AM (10am-12pm): End-to-End Integration Test**

**Tasks:**
- Generate template fresh
- Install kailash-dataflow-utils
- Run complete flow: Register → Login → Create org
- Test all Nexus channels (API, CLI if available, MCP basic)
- Document any issues

**Weekly retrospective:**
- Participate (30 min)
- Share feedback on pairing experience (honest assessment)

**Week 3 total: 4 hours**
**Running total: 28 hours**

---

### Week 4: Beta Testing (10 hours)

**Monday (1 hour):**

**PM (2pm-3pm): Beta Testing Preparation**

**Tasks:**
- Review testing script with Kaizen dev
- Prepare demo talking points (what to show testers)
- Test template one final time (fresh installation)

---

**Tuesday (3 hours):**

**PM (2pm-5pm): TODO-013 - Beta Session 1 (Support Role)**

**Your role:** Support (DataFlow dev facilitates)

**Tasks:**
- Answer Nexus-specific questions (multi-channel deployment, CLI, MCP)
- Observe where users struggle with Nexus integration
- Take notes on CUSTOMIZE.md clarity (did your docs help?)

**Notes to capture:**
- Do users understand multi-channel deployment?
- Is CUSTOMIZE.md clear enough?
- Any Nexus errors or confusion?

---

**Wednesday (3 hours):**

**PM (2pm-5pm): Beta Session 2 (Facilitator Role)**

**Your role:** Facilitator (you lead this session)

**Tasks:**
- Guide 5 new testers through template
- Let them struggle a bit (don't jump in immediately)
- Observe timing (are they <30 min?)
- Note pain points for CUSTOMIZE.md improvements

**Focus:**
- Nexus deployment: Is it clear what's happening?
- Multi-channel: Do users appreciate API + CLI + MCP?
- Customization: Can they add workflows and see them in Nexus?

---

**Thursday (1 hour):**

**AM (10am-11am): Feedback Compilation**

**Tasks:**
- Compile Nexus-specific feedback
- Identify CUSTOMIZE.md improvements
- Input to Kaizen dev's analysis (TODO-014)

---

**Friday (2 hours):**

**AM (10am-12pm): Go/No-Go Decision Meeting**

**Your input:**
- Nexus integration feedback (did it work well?)
- CUSTOMIZE.md effectiveness (did users find it helpful?)
- Pairing assessment (was pairing with DataFlow dev valuable?)
- Recommendation (GO/ITERATE/NO-GO from Nexus perspective)

**Week 4 total: 10 hours**
**Sprint 1 total: 38 hours** ✅

---

## Your Detailed Task Guides

### TODO-001, 002, 003: NAVIGATOR Role (12 hours, Week 1)

**As NAVIGATOR, your job is to:**
1. **Review DataFlow dev's code** (models, workflows, structure)
2. **Ask questions** (How does this work? Why this approach? What about X?)
3. **Provide Nexus perspective** (This won't work with Nexus because...)
4. **Learn DataFlow** (understand models, auto-generated nodes, patterns)
5. **Prepare for TODO-004** (understand what you'll integrate with)

**NOT your job:**
- Write the code (DataFlow dev drives)
- Make DataFlow decisions (defer to DataFlow dev's expertise)
- Slow down progress (ask questions but don't block)

**Pairing sessions (3 sessions, 2h each = 6h):**
- **Session 1 (Mon PM):** Review structure together, ask questions
- **Session 2 (Wed PM):** Review models together, understand multi-tenancy
- **Session 3 (Fri PM):** Review workflows together, understand WorkflowBuilder

**Individual review time (6h):**
- Review code async (GitHub PRs or direct code review)
- Test locally (run DataFlow dev's code)
- Provide written feedback (GitHub comments)

**What you're learning:**
- How DataFlow @db.model works
- How to define models with type hints
- How DataFlow generates nodes automatically
- How to use auto-generated nodes in workflows
- How multi-tenancy works

**Why this matters:**
- You need to understand DataFlow to integrate Nexus properly (TODO-004)
- You need to understand models to write CUSTOMIZE.md (TODO-005)
- You're building cross-functional skills (valuable for full MVR)

---

### TODO-004: Nexus Deployment (6 hours, Week 2 Mon-Tue)

**GitHub Issue:** #470
**Local Todo:** `apps/kailash-nexus/todos/active/TODO-004-saas-nexus-deployment.md` (will be created)

**Read before starting (30 min):**
1. Your developer instructions: `09-developer-instructions/03-nexus-instructions.md`
2. Nexus modifications spec: `02-implementation/03-modifications/03-nexus-modifications.md`
3. GitHub issue #470

**Monday AM (9am-1pm, 4 hours): IMPLEMENT**

**Subagent workflow:**
```bash
# Step 1: Deep dive into Nexus configuration for SaaS
> Use the nexus-specialist subagent to design Nexus initialization with .for_development() preset for SaaS template (will use .for_saas() in production)

# Step 2: Workflow registration patterns
> Use the pattern-expert subagent to review multi-channel workflow registration best practices

# Step 3: Integration validation
> Use the framework-advisor subagent to validate DataFlow + Nexus integration approach and check for known issues (e.g., startup time)
```

**Implementation:**

1. **Update main.py with Nexus initialization:**
```python
from nexus import Nexus

# Initialize with development preset (fast iteration)
# AI INSTRUCTION: For production, use Nexus.for_saas()
nexus = Nexus.for_development()

# Register workflows
from workflows.auth import register_workflow, login_workflow, logout_workflow

nexus.register("register", register_workflow())
nexus.register("login", login_workflow())
nexus.register("logout", logout_workflow())

# AI INSTRUCTION: To add new workflow:
# 1. Import workflow function
# 2. Register: nexus.register("name", workflow())
# 3. Automatically available on API, CLI, MCP
```

2. **Add AI instructions:**
- Document what Nexus does
- Explain multi-channel deployment
- Show how to add workflows

3. **Test multi-channel:**
```bash
python main.py

# Verify:
# - Server starts successfully
# - API endpoints created: POST /workflows/register/execute
# - CLI commands available (if CLI implemented)
# - MCP tools registered
```

---

**Tuesday AM (9am-11am, 2 hours): TEST & VALIDATE**

**Testing:**
```bash
# Write integration tests
> Use the tdd-implementer subagent to create integration tests for Nexus multi-channel deployment

# Verify tests pass
> Use the testing-specialist subagent to ensure Nexus integration tests cover all 3 channels (API, CLI, MCP)
```

**Integration test example:**
```python
def test_nexus_registers_all_workflows():
    """Test that Nexus registers all auth workflows correctly."""
    # Import main.py module
    # Verify nexus._workflows contains register, login, logout
    assert "register" in nexus._workflows
    assert "login" in nexus._workflows
    assert "logout" in nexus._workflows

def test_nexus_api_endpoints_accessible():
    """Test that API endpoints are created."""
    # Start Nexus
    # Make HTTP request to each endpoint
    response = requests.get("http://localhost:8000/workflows/login/info")
    assert response.status_code == 200
```

**Validation:**
```bash
> Use the gold-standards-validator subagent to ensure Nexus integration follows best practices

> Use the intermediate-reviewer subagent to review Nexus deployment integration for completeness
```

**Acceptance:**
- [ ] Nexus initialized correctly
- [ ] All workflows registered
- [ ] Multi-channel working (API confirmed, CLI/MCP basic check)
- [ ] Tests pass (80%+ coverage)
- [ ] No startup errors

**Mark TODO-004 COMPLETE**

---

**Wednesday-Friday (6 hours):**

**TODO-005: Write CUSTOMIZE.md** [#471]

**This is YOUR signature deliverable for Sprint 1.**

**Wednesday AM (9am-1pm, 4 hours): WRITE**

**Subagent workflow:**
```bash
# Understand user needs
> Use the requirements-analyst subagent to identify what IT teams need to know to successfully customize the SaaS template

# Content strategy
> Use the documentation-validator subagent to plan CUSTOMIZE.md structure with tested, working examples for each customization scenario
```

**Structure:**
```markdown
# Customizing Your SaaS

## Overview (2 min read)
- What this template provides
- What you'll customize
- Prerequisites

## Step 1: Configure Database (5 minutes)
[Copy-paste commands, screenshots]

## Step 2: Add Business Models (15 minutes)
[Complete example: Product model]
[Shows: DataFlow @db.model, auto-generated nodes]

## Step 3: Customize Authentication (10 minutes)
[Example: Add company field to User]
[Shows: Update model, update workflow, test]

## Step 4: Add Business Workflows (20 minutes)
[Example: Create product workflow]
[Shows: WorkflowBuilder, register with Nexus, test API]

## Step 5: Deploy (15 minutes)
[Deployment guide: Docker, local, cloud]

## Using Claude Code (IMPORTANT)
[Specific prompts that work]
[What Claude Code will do]
[How to verify success]

## Troubleshooting
[Common issues and fixes]
[Where to get help]
```

**Thursday AM (10am-12pm, 2 hours): TEST & REFINE**

**Test EVERY example:**
```bash
# Run each example in CUSTOMIZE.md manually
# Time yourself (should match time estimates)
# Note any confusing parts
# Fix issues

# Validate with subagent
> Use the documentation-validator subagent to test all code examples in CUSTOMIZE.md and ensure they work

# Get review
# Ask Kaizen dev to review for clarity (non-technical perspective)
# Ask DataFlow dev to review for technical accuracy
```

**Refinement:**
- Simplify confusing sections
- Add screenshots where helpful
- Improve "Using Claude Code" section (this is key for IT teams)

**Acceptance:**
- [ ] All 5 steps documented with tested examples
- [ ] Time estimates realistic (tested)
- [ ] "Using Claude Code" section comprehensive
- [ ] Troubleshooting covers common issues
- [ ] Kaizen dev approves (clarity ✅)
- [ ] DataFlow dev approves (technical accuracy ✅)

**Mark TODO-005 COMPLETE**

**Week 2 total: 12 hours**
**Running total: 36 hours**

---

### Week 3: Light Support (4 hours)

**Your role:** Support DataFlow dev's component work, test integration

**Monday-Tuesday (2 hours):**

**Tasks:**
- Answer questions from DataFlow dev (about Nexus integration with dataflow-utils)
- Review code if requested

**Wednesday PM (2pm-4pm, 2 hours):**

**Integration testing:**
- Test kailash-dataflow-utils in template
- Verify Nexus still works after template updated
- Test end-to-end flow

**End of week:**
- Participate in retrospective (30 min)
- Prepare for Week 4 beta testing

**Week 3 total: 4 hours**
**Running total: 40 hours**

---

### Week 4: Beta Testing (10 hours)

**Already covered in week-by-week breakdown above**

**Your deliverables:**
- Facilitated beta testing session (Session 2)
- Nexus-specific feedback compiled
- CUSTOMIZE.md effectiveness assessment
- Pairing experience documented

**Final total: 38 hours** (slightly under estimate of 40h, good!)

---

## Subagent Workflow Reminders

**For EVERY task, follow 7-phase process:**

1. **Analysis:** requirements-analyst, sdk-navigator, framework-advisor
2. **Planning:** todo-manager (already done), intermediate-reviewer
3. **Implementation:** tdd-implementer (tests first), nexus-specialist
4. **Testing:** testing-specialist
5. **Validation:** gold-standards-validator
6. **Review:** intermediate-reviewer
7. **Release:** git-release-specialist (if creating PR)

**Example for TODO-004:**
- Analysis: nexus-specialist, framework-advisor (30 min)
- Implementation: tdd-implementer → tests, nexus-specialist → code (3h)
- Testing: testing-specialist (30 min)
- Validation: gold-standards-validator, intermediate-reviewer (30 min)

**Don't skip any step. Each step prevents errors and ensures quality.**

---

## Your Success Criteria

**Sprint 1 success for you:**
- ✅ TODO-004, 005 complete (Nexus integration + CUSTOMIZE.md)
- ✅ Reviewed TODO-001, 002, 003 thoroughly (learned DataFlow basics)
- ✅ Pairing productive (you gained value from working with DataFlow dev)
- ✅ CUSTOMIZE.md rated "clear" by beta testers (80%+)
- ✅ Nexus multi-channel deployment works for all testers (100%)

**Personal growth:**
- Learned DataFlow @db.model and auto-generated nodes
- Practiced pair programming (driver/navigator)
- Wrote user-facing documentation (new skill?)
- Contributed to strategic decision (Go/No-Go)

---

## Common Questions

**Q: What if I don't understand DataFlow well enough to review?**
**A:** That's OK and expected. Use this formula:
1. "I don't understand X, can you explain?" (learn)
2. "From Nexus perspective, Y might be an issue" (provide your expertise)
3. Use dataflow-specialist subagent to learn DataFlow patterns

**Q: What if my CUSTOMIZE.md is too technical?**
**A:** Get Kaizen dev to review from "non-expert" perspective. They'll flag confusing parts. Simplify iteratively.

**Q: What if Nexus integration has bugs in beta testing?**
**A:** Fix immediately if critical (blocks usage). Document if minor (fix in Phase 1). Your job is to ensure Nexus works well enough for validation, not perfectly.

---

## Resources

**Your instructions:** `09-developer-instructions/03-nexus-instructions.md`
**Nexus spec:** `02-implementation/03-modifications/03-nexus-modifications.md`
**Nexus reference:** `apps/kailash-nexus/src/nexus/core.py`

**If stuck:**
1. Use nexus-specialist subagent
2. Ask DataFlow dev (they're your pair partner)
3. Ask PM

---

**You are the Nexus expert. Your job is to make multi-channel deployment seamless and to write docs that make customization obvious.**

**Make it easy. Make it clear. Make it work.** 🚀
