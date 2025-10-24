# DataFlow Developer: Sprint 1 (Prototype) Instructions

**Sprint:** Phase 0 - Prototype Validation
**Duration:** 4 weeks (Week 0-4)
**Your Workload:** 62 hours (15.5 hours/week average)
**Your Role:** Lead template development (paired with Nexus dev), build kailash-dataflow-utils

---

## Your Objectives

**Primary (CRITICAL):**
1. Build minimal SaaS template foundation (paired with Nexus dev)
2. Implement kailash-dataflow-utils package (prevents datetime errors)
3. Validate that pairing works (team dynamics test)

**Success criteria:**
- SaaS template works in <30 min (tested with beta users)
- kailash-dataflow-utils installs successfully (100% rate)
- Pairing with Nexus dev is productive (self-report positive)

---

## Your Tasks (7 tasks, 62 hours)

| Task | Hours | Week | Priority | Status |
|------|-------|------|----------|--------|
| TODO-001: Template Structure | 8h | Week 1 | P0 | PENDING |
| TODO-002: Auth Models | 8h | Week 1 | P0 | PENDING |
| TODO-003: Auth Workflows | 12h | Week 1-2 | P0 | PENDING |
| TODO-008: TimestampField | 5h | Week 3 | P1 | PENDING |
| TODO-009: UUIDField | 5h | Week 3 | P1 | PENDING |
| TODO-010: JSONField | 5h | Week 3 | P1 | PENDING |
| TODO-011: Publish to PyPI | 5h | Week 3 | P1 | PENDING |
| TODO-013: Beta Testing | 8h | Week 4 | P0 | PENDING |
| Integration/Refinement | 6h | Week 2-4 | P1 | PENDING |

**Total: 62 hours over 4 weeks = 15.5 hours/week average**

---

## Week-by-Week Breakdown

### Week 1: Template Foundation (20 hours)

**Your focus:** Build SaaS template structure, models, and auth workflows

**Monday (4 hours):**

**AM (9am-11am): Kickoff + Planning**
- 1h: Team kickoff meeting (all 3 + PM)
- 1h: Read TODO-001 detailed file + GitHub issue #458

**PM (2pm-6pm): START TODO-001**

**Subagent workflow:**
```bash
# Step 1: Requirements Analysis (30 min)
> Use the requirements-analyst subagent to break down SaaS template directory structure into specific files, folders, and boilerplate content needed

# Step 2: Find Patterns (30 min)
> Use the sdk-navigator subagent to find existing template examples or starter projects in Kailash SDK documentation

# Step 3: Framework Guidance (30 min)
> Use the framework-advisor subagent to confirm SaaS template should use DataFlow + Nexus and understand integration requirements

> Use the dataflow-specialist subagent to review multi-tenant DataFlow configuration for SaaS applications
```

**Implementation (2h):**
- Create directory structure: `templates/saas-starter/`
- Create skeleton files (20 files)
- Add boilerplate (README.md, .env.example, requirements.txt)

**Coordination:**
- End of day: Sync with Nexus dev (15 min)
- Share structure for review
- Plan Tuesday pair session

---

**Tuesday (4 hours):**

**AM (9am-1pm): COMPLETE TODO-001**

**Subagent workflow:**
```bash
# Step 4: Test First (1h)
> Use the tdd-implementer subagent to write tests for template generation before finalizing structure

# Step 5: Implementation (2h)
> Use the pattern-expert subagent to guide directory structure refinement based on Python project best practices
```

**Implementation:**
- Finalize pyproject.toml
- Create test_template_generation.py
- Verify template generates correctly

**Validation (1h):**
```bash
> Use the testing-specialist subagent to verify template generation tests pass

> Use the gold-standards-validator subagent to ensure template structure follows gold standards

> Use the intermediate-reviewer subagent to review completed template structure
```

**Acceptance:**
- [ ] All subtasks (1-5) in TODO-001 complete
- [ ] Tests pass (template generates successfully)
- [ ] Nexus dev review approved
- [ ] GitHub issue #458 updated with completion evidence

**Mark TODO-001 COMPLETE**

---

**Wednesday (4 hours):**

**AM (9am-1pm): START TODO-002 - Auth Models**

**Subagent workflow:**
```bash
# Step 1-2: Analysis (30 min)
> Use the sdk-navigator subagent to find DataFlow multi-tenant model examples in existing SDK

> Use the dataflow-specialist subagent to review best practices for User, Organization, Session models with multi-tenancy

# Step 3: Plan (30 min)
> Use the ultrathink-analyst subagent to identify potential issues with auth model design (security, scalability, multi-tenancy)
```

**Implementation (3h):**
- Create `models/user.py` with AI instructions
- Create `models/organization.py`
- Create `models/session.py`
- Configure DataFlow multi-tenancy

**Coordination:**
- Pair session with Nexus dev (1h) - review models together
- Nexus dev provides feedback on Nexus integration needs

---

**Thursday (4 hours):**

**AM (9am-1pm): COMPLETE TODO-002**

**Implementation:**
- Refine models based on Nexus dev feedback
- Add comprehensive AI instructions as docstrings
- Embed Golden Pattern #1 (Add DataFlow Model)

**Testing:**
```bash
> Use the tdd-implementer subagent to write integration tests for all 3 models with DataFlow auto-generated nodes

> Use the testing-specialist subagent to verify model tests pass with real database (PostgreSQL or SQLite)
```

**Validation:**
```bash
> Use the gold-standards-validator subagent to ensure models follow DataFlow patterns and gold standards

> Use the intermediate-reviewer subagent to review completed auth models
```

**Acceptance:**
- [ ] All 3 models defined with type hints
- [ ] DataFlow generates 27 nodes (9 per model)
- [ ] Multi-tenancy enabled and tested
- [ ] AI instructions comprehensive
- [ ] Tests pass (85%+ coverage)

**Mark TODO-002 COMPLETE**

---

**Friday (4 hours):**

**AM (9am-1pm): START TODO-003 - Auth Workflows**

**Subagent workflow:**
```bash
> Use the sdk-navigator subagent to find authentication workflow examples in SDK documentation

> Use the pattern-expert subagent to review WorkflowBuilder patterns for multi-step authentication flows

> Use the dataflow-specialist subagent to understand how to use auto-generated nodes in authentication workflows
```

**Implementation (3h):**
- Create `workflows/auth.py`
- Implement register_workflow() (user + org creation)
- Start login_workflow() (email/password check)

**End of week:**
- Weekly retrospective (30 min, all 3)
- Daily update summarizing Week 1 progress

**Week 1 total: 20 hours** ✅

---

### Week 2: Complete Template + Refinement (10 hours)

**Monday (4 hours):**

**AM (9am-1pm): COMPLETE TODO-003**

**Implementation:**
- Complete login_workflow() (JWT generation)
- Implement logout_workflow() (session invalidation)
- Add error handling
- Embed Golden Pattern #5 (Authentication)

**Testing:**
```bash
> Use the tdd-implementer subagent to write E2E tests for complete auth flow (register → login → access protected endpoint → logout)

> Use the testing-specialist subagent to verify auth tests pass with real database and JWT validation
```

**Validation:**
```bash
> Use the gold-standards-validator subagent to ensure auth workflows follow security best practices

> Use the intermediate-reviewer subagent to review complete authentication implementation
```

**Acceptance:**
- [ ] All 3 auth workflows complete
- [ ] Tests pass (90%+ coverage for auth critical path)
- [ ] JWT tokens generated and validated correctly
- [ ] Error handling comprehensive

**Mark TODO-003 COMPLETE**

---

**Tuesday (2 hours):**

**AM (9am-11am): Integration Support**

**Tasks:**
- Review Nexus dev's TODO-004 (Nexus deployment integration)
- Test that workflows register correctly with Nexus
- Fix any integration issues

**Coordination:**
- Pair session with Nexus dev (2h)
- Test complete flow: Models → Workflows → Nexus → API endpoints

**Outcome:**
- Template runs end-to-end successfully
- All workflows accessible via API, CLI, MCP

---

**Wednesday (2 hours):**

**AM (10am-12pm): Template Testing**

**Tasks:**
- Run complete template manually (generate, configure, run)
- Time how long it takes (should be <5 min)
- Test with Claude Code (prompt: "Add Product model")
- Document any issues

**Testing:**
```bash
> Use the testing-specialist subagent to review template test coverage and ensure all critical paths tested
```

**Outcome:**
- Template works end-to-end
- Issues documented for Week 3 fixes

---

**Thursday-Friday (2 hours):**

**PM: Template Refinement**

**Tasks:**
- Fix issues from Wednesday testing
- Improve AI instructions based on Claude Code test
- Final polish before Week 3 package work

**Outcome:**
- Template ready for kailash-dataflow-utils integration

**Week 2 total: 10 hours**
**Running total: 30 hours** (on track)

---

### Week 3: Build kailash-dataflow-utils (20 hours)

**Your focus:** Build and publish first marketplace component

**Monday (5 hours):**

**AM (9am-2pm): TODO-008 - TimestampField**

**Subagent workflow:**
```bash
# Analysis (30 min)
> Use the requirements-analyst subagent to break down TimestampField requirements (methods, error handling, validation)

> Use the sdk-navigator subagent to find datetime handling patterns in existing SDK

# Design (30 min)
> Use the dataflow-specialist subagent to understand how DataFlow expects datetime parameters

> Use the ultrathink-analyst subagent to identify all datetime error scenarios to prevent
```

**Implementation (3h):**
- Create package structure: `packages/kailash-dataflow-utils/`
- Implement TimestampField class
  - `now()` method (returns datetime with UTC timezone)
  - `validate()` method (catches .isoformat() mistake)
  - Comprehensive error messages

**Testing (1h):**
```bash
> Use the tdd-implementer subagent to write unit and integration tests for TimestampField

> Use the testing-specialist subagent to verify tests cover the actual datetime error scenario (text = integer)
```

**Acceptance:**
- [ ] TimestampField.now() works correctly
- [ ] TimestampField.validate() catches string error
- [ ] Tests: Unit (mocked) + Integration (real DataFlow model)
- [ ] Error message helpful ("Did you use .isoformat()?")

**Mark TODO-008 COMPLETE**

---

**Tuesday (5 hours):**

**AM (9am-2pm): TODO-009 - UUIDField + TODO-010 - JSONField**

**Implementation (4h):**
- Implement UUIDField class
  - `generate()` method (creates valid UUID)
  - `validate()` method (validates format)
- Implement JSONField class
  - `validate()` method (catches json.dumps() mistake)
  - Error messages

**Testing (1h):**
```bash
> Use the tdd-implementer subagent to write tests for UUIDField and JSONField

> Use the testing-specialist subagent to ensure tests cover real error scenarios
```

**Acceptance:**
- [ ] UUIDField generates valid UUIDs
- [ ] JSONField catches dict-to-string errors
- [ ] Tests pass (90%+ coverage)

**Mark TODO-009 and TODO-010 COMPLETE**

---

**Wednesday-Thursday (8 hours):**

**TODO-011: Package and Publish to PyPI**

**Day 1 (Wed, 4h):**

**Package setup:**
- Create pyproject.toml (packaging metadata)
- Create README.md (5-minute quick start)
- Create CLAUDE.md (AI assistant instructions)
- Create tests/ directory (if not already)
- Create docs/ directory

**Testing:**
```bash
> Use the testing-specialist subagent to verify complete package test suite (unit + integration tests for all 3 fields)

> Use the gold-standards-validator subagent to ensure package follows Python packaging best practices
```

**Build locally:**
```bash
cd packages/kailash-dataflow-utils
python -m build
pip install dist/kailash_dataflow_utils-*.whl

# Test installation
python -c "from kailash_dataflow_utils import TimestampField; print(TimestampField.now())"
```

**Day 2 (Thu, 4h):**

**Publish to Test PyPI:**
```bash
python -m twine upload --repository testpypi dist/*
pip install --index-url https://test.pypi.org/simple/ kailash-dataflow-utils

# Test from Test PyPI
python -c "from kailash_dataflow_utils import TimestampField, UUIDField, JSONField"
```

**Fix any issues, then publish to PyPI:**
```bash
python -m twine upload dist/*

# Verify public installation
pip install kailash-dataflow-utils
python -c "from kailash_dataflow_utils import TimestampField; print('✅ Success')"
```

**Integration with template:**
- Update `templates/saas-starter/requirements.txt` (add kailash-dataflow-utils)
- Update `models/*.py` to import and use helpers
- Test that template uses package correctly

**Acceptance:**
- [ ] Package published to PyPI (public, installable)
- [ ] `pip install kailash-dataflow-utils` works
- [ ] All 3 field helpers importable
- [ ] Template uses package (datetime errors prevented)
- [ ] README.md and CLAUDE.md complete

**Mark TODO-011 COMPLETE**

---

**Friday (2 hours):**

**Integration testing:**
- Test template with kailash-dataflow-utils integrated
- Generate fresh template, verify package used
- Test that datetime error is actually prevented

**Weekly retrospective:**
- Participate in team retrospective (30 min)
- Document learnings from package creation

**Week 3 total: 20 hours**
**Running total: 50 hours**

---

### Week 4: Beta Testing & Decision (12 hours)

**Monday-Tuesday (4 hours):**

**Prepare for beta testing:**
- Review template one final time (1h)
- Prepare demo script (what to show testers) (1h)
- Create troubleshooting guide (common issues and fixes) (1h)
- Test template on fresh machine/environment (1h)

---

**Tuesday-Wednesday (8 hours):**

**TODO-013: Run Beta Testing Sessions**

**Your role:** Facilitator/Support

**Tuesday PM (3 hours):**
- **Beta Session 1:** Facilitate testing with 5 testers
- Watch for issues (where do people get stuck?)
- Provide help only when stuck >5 minutes
- Take notes on pain points

**Wednesday PM (3 hours):**
- **Beta Session 2:** Support role (Nexus dev facilitates)
- Observe DataFlow-specific issues
- Answer questions about models, workflows, DataFlow
- Take detailed notes

**Thursday (2 hours):**
- Compile DataFlow-specific feedback
- Identify issues to fix (if ITERATE decision)
- Input to Kaizen dev's analysis (TODO-014)

**Friday (0 hours - in decision meeting):**
- Participate in Go/No-Go decision meeting
- Provide technical input on feasibility of fixes (if ITERATE)
- Prepare for Phase 1 if GO

**Week 4 total: 12 hours**
**Sprint 1 total: 62 hours** ✅

---

## Your Detailed Task Guides

### TODO-001: SaaS Template Structure (8 hours, Week 1 Mon-Tue)

**GitHub Issue:** #458
**Local Todo:** `apps/kailash-nexus/todos/active/TODO-001-saas-template-structure.md`

**Read before starting (30 min):**
1. Specification: `.claude/improvements/repivot/02-implementation/02-new-components/01-templates-specification.md` (pages 1-20, template structure section)
2. GitHub issue #458 (acceptance criteria)
3. Detailed todo file (subtasks and verification)

**Subagent workflow (Day 1, 2 hours):**

**Morning (2h):**
```bash
# Understand requirements deeply
> Use the requirements-analyst subagent to create detailed breakdown of SaaS template structure requirements including all files, folders, and their purposes

# Find existing patterns
> Use the sdk-navigator subagent to locate any existing template or starter project patterns in Kailash SDK or apps

# Validate architecture
> Use the framework-advisor subagent to confirm SaaS template should use DataFlow for database and Nexus for multi-channel deployment
```

**Expected output:**
- Clear understanding of all 20 files needed
- Reference to existing patterns
- Confirmation of DataFlow + Nexus approach

**Afternoon (2h):**
```bash
# Design review
> Use the pattern-expert subagent to review Python project structure best practices and ensure template follows conventions

# Risk analysis
> Use the ultrathink-analyst subagent to identify potential failure points in template structure (e.g., wrong import paths, missing configs)

# Get approval before coding
> Use the intermediate-reviewer subagent to review planned directory structure and validate it matches specification
```

**Implementation (Day 2, 4 hours):**

**Morning (4h):**

Create directory structure:
```bash
mkdir -p templates/saas-starter/{models,workflows,tests,docs}
```

Create skeleton files:
```python
# templates/saas-starter/main.py
"""Main application entry point.

AI INSTRUCTIONS:
================
SEE: Golden Pattern #3 - Deploy with Nexus

To add a new workflow:
1. Create workflow in workflows/ directory
2. Import here
3. Register with nexus.register(name, workflow)
4. Automatically available on API, CLI, MCP
"""

from nexus import Nexus
from dataflow import DataFlow
import os

# Initialize DataFlow
db = DataFlow(
    database_url=os.getenv("DATABASE_URL", "postgresql://localhost/saas_dev"),
    multi_tenant=True,
    audit_logging=True
)

# Import models (triggers registration)
from models import user, organization, session

# Initialize Nexus
nexus = Nexus.for_development()  # Will change to .for_saas() later

# Import and register workflows (placeholder)
# from workflows import auth, users

if __name__ == "__main__":
    print("🚀 SaaS Starter Template")
    print("📡 Starting Nexus...")
    nexus.start()
```

Create other skeleton files:
- `requirements.txt`
- `.env.example`
- `README.md`
- `config.py`
- `models/__init__.py`
- `workflows/__init__.py`
- `tests/__init__.py`
- `docs/architecture.md`

**Validation (Day 2, 2 hours):**

```bash
# Test template generation
> Use the tdd-implementer subagent to write test that template directory can be created and all files present

# Ensure compliance
> Use the gold-standards-validator subagent to validate template structure follows gold standards for absolute imports and project organization

# Final review before completion
> Use the intermediate-reviewer subagent to review complete template structure before marking TODO-001 done
```

Run tests:
```python
# tests/test_template_generation.py
def test_saas_template_structure():
    """Verify template has all required files."""
    template_dir = Path("templates/saas-starter")

    required_files = [
        "main.py", "config.py", "requirements.txt",
        ".env.example", "README.md", "CUSTOMIZE.md",
        "models/__init__.py", "models/user.py",
        "workflows/__init__.py", "workflows/auth.py"
    ]

    for file in required_files:
        assert (template_dir / file).exists(), f"Missing: {file}"
```

**Evidence of completion:**
- Screenshot of directory structure
- Test output showing all files present
- GitHub comment on #458 with evidence

---

### TODO-002 & TODO-003: Continue This Pattern

**For each task:**
1. Read specification + issue + detailed todo (30 min)
2. Run subagent workflow (2-4 hours, following 7-phase process)
3. Implement with TDD (test first, then code)
4. Validate with gold-standards-validator
5. Get review from intermediate-reviewer
6. Document evidence and mark complete

**Never skip the subagent workflow. It's mandatory.**

---

## Pair Programming Guide

### How to Pair with Nexus Dev (Week 1-2)

**You are the DRIVER for TODO-001, 002, 003:**
- You write the code
- You make primary decisions
- Nexus dev is NAVIGATOR (reviews, suggests, questions)

**Nexus dev is DRIVER for TODO-004, 005:**
- They write the code
- They make primary decisions
- You are NAVIGATOR (review their Nexus integration)

**Pairing schedule:**
- Week 1: 3 pair sessions (2 hours each = 6h total)
  - Session 1 (Mon): Review TODO-001 structure together
  - Session 2 (Wed): Review TODO-002 models together
  - Session 3 (Fri): Review TODO-003 workflows together
- Week 2: 2 pair sessions (2 hours each = 4h total)
  - Session 4 (Mon): Nexus integration (you navigate)
  - Session 5 (Wed): Integration testing (equal partnership)

**Pairing tools:**
- Zoom with screen share OR VS Code Live Share OR in-person
- Shared GitHub repo (push frequently)
- Slack/Discord for quick questions between sessions

**Pairing best practices:**
- Switch roles every hour (prevents fatigue)
- Speak your thoughts out loud (navigator learns your reasoning)
- Ask questions (no stupid questions in pairing)
- Take breaks every 90 minutes
- Celebrate small wins together

---

## Common Pitfalls for DataFlow Developers

### Pitfall 1: Forgetting Multi-Tenancy

**Wrong:**
```python
@db.model
class User:
    name: str
    email: str
    # Missing tenant_id!
```

**Right:**
```python
db = DataFlow(multi_tenant=True)  # Enable first

@db.model
class User:
    name: str
    email: str
    # tenant_id added automatically by DataFlow
```

### Pitfall 2: Including Auto-Managed Fields

**Wrong:**
```python
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "created_at": datetime.now(),  # Auto-managed, don't include!
    "updated_at": datetime.now()   # Auto-managed!
})
```

**Right:**
```python
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # created_at, updated_at added automatically
})
```

### Pitfall 3: Wrong UpdateNode Pattern

**Wrong:**
```python
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "New Name"  # CreateNode pattern, not UpdateNode!
})
```

**Right:**
```python
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "New Name"}
})
```

**Refer to:** `sdk-users/apps/dataflow/CLAUDE.md` - Common Mistakes section

---

## Daily Checklist

**Every day, before ending work:**
- [ ] Push code to GitHub (don't keep work local)
- [ ] Update GitHub issue with progress comment
- [ ] Post daily update in #mvr-execution
- [ ] Update local todo status (PENDING → IN_PROGRESS → COMPLETED)
- [ ] If blocked: Escalate immediately (don't wait until next day)

**Every task completion:**
- [ ] All acceptance criteria met (100%)
- [ ] Tests pass (target coverage met)
- [ ] Code reviewed by secondary owner
- [ ] GitHub issue updated with evidence (file:line references)
- [ ] Local todo moved to completed/
- [ ] Notify next dependent task owner

---

## Success Metrics (Your Personal)

**Sprint 1 success for you means:**
- ✅ TODO-001, 002, 003 complete (SaaS template foundation)
- ✅ TODO-008, 009, 010, 011 complete (kailash-dataflow-utils published)
- ✅ Pairing with Nexus dev productive (you both report positive experience)
- ✅ Beta testers successfully use your DataFlow models (no errors)
- ✅ kailash-dataflow-utils installs successfully for all testers (100% rate)

**Measure by:**
- Task completion rate (7/7 tasks = 100%)
- Quality (test coverage ≥80%, no critical bugs)
- Team feedback (Nexus dev says pairing was valuable)
- User feedback (testers say DataFlow models are clear)

---

## Your Questions Answered

**Q: What if TODO-001 takes 12 hours instead of 8?**
**A:** That's OK. Estimate is guide, not limit. Update GitHub issue with actual time, adjust Week 2 plan if needed. Quality > speed.

**Q: What if pairing with Nexus dev isn't working well?**
**A:** Flag this in daily standup immediately. Options: Try different pairing style (driver/navigator switch more often), take a break and work solo, or escalate to PM for mediation. Prototype tests this - if pairing fails, we need to know Week 1, not Week 10.

**Q: What if kailash-dataflow-utils has bugs after publishing?**
**A:** Patch release. Fix bugs, bump version (0.1.0 → 0.1.1), re-publish. PyPI allows unlimited patches. Inform any users who already installed.

**Q: What if we don't hit 10 testers by Week 4?**
**A:** 6-8 is minimum viable. Proceed with smaller group, but note in decision that sample size is smaller (lower confidence). Alternatively, extend Week 4 by a few days to recruit more.

**Q: What if NPS is 28 (below 35 target)?**
**A:** This is ITERATE territory. Team discusses: Are issues fixable in 2-4 weeks? If yes, iterate. If issues are fundamental (testers hate templates), this is NO-GO signal. Be honest in assessment.

---

## Resources and Support

**Your developer instructions:**
- `.claude/improvements/repivot/09-developer-instructions/02-dataflow-instructions.md` (complete guide, 25K words)

**Component specifications:**
- Templates: `02-implementation/02-new-components/01-templates-specification.md`
- kailash-dataflow-utils: `02-implementation/02-new-components/05-official-components.md` (Component 1)

**DataFlow reference:**
- `sdk-users/apps/dataflow/CLAUDE.md` (common mistakes, patterns)
- `apps/kailash-dataflow/src/dataflow/core/engine.py` (DataFlow internals)

**If stuck:**
1. **Use subagents** (they're there to help)
2. **Ask Nexus dev** (especially for integration questions)
3. **Ask PM** (for scope/priority questions)
4. **Escalate early** (don't struggle alone for >2 hours)

---

## End of Sprint 1

**What you'll have accomplished:**
- Built foundation of SaaS template (models, workflows, structure)
- Published first marketplace component (prevents datetime errors!)
- Tested pairing approach (validated team can work together)
- Participated in beta testing (validated user value)

**What you'll know:**
- Does pairing with Nexus dev work? (team dynamics)
- Do users value templates? (market validation)
- Does kailash-dataflow-utils prevent errors? (component value)
- Should we proceed to full MVR? (strategic decision)

**Your impact:**
- If GO: Your work becomes foundation for 7-9 month MVR
- If NO-GO: Saved team from 1,320 hours of potentially wasted effort

**Either outcome is valuable. You win by executing well and providing data for good decision.**

---

**You are the DataFlow expert. Your role is critical. Build with quality, pair generously, validate thoroughly.**

**Let's build something amazing.** 🚀
