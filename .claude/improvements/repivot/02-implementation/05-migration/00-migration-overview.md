# Migration and Backward Compatibility

**Purpose:** Ensure 100% backward compatibility - existing users unaffected

---

## Core Principle

**ZERO BREAKING CHANGES**

Every existing Kailash project must continue to work without modification after the repivot.

---

## Compatibility Guarantee

### What Will Continue to Work

**1. All WorkflowBuilder Usage**
```python
# Existing code (2023-2025)
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("PythonCodeNode", "test", {...})
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())

# ✅ Works identically in v0.10.0
# ✅ No changes needed
# ✅ Same behavior, same performance
```

**2. All DataFlow Usage**
```python
# Existing code
from dataflow import DataFlow

db = DataFlow("postgresql://...")

@db.model
class User:
    name: str

workflow = WorkflowBuilder()
workflow.add_node("UserCreateNode", "create", {"name": "Alice"})

# ✅ Works identically
# ✅ No migration needed
```

**3. All Nexus Usage**
```python
# Existing code
from nexus import Nexus

nexus = Nexus(api_port=8000, enable_auth=True)
nexus.register("workflow", my_workflow)
nexus.start()

# ✅ Works identically
# ✅ No changes needed
```

**4. All Kaizen Usage**
```python
# Existing code
from kaizen.core.base_agent import BaseAgent

class MyAgent(BaseAgent):
    # ...

# ✅ Works identically
# ✅ Zero changes to Kaizen
```

### What's New (Opt-In)

**New features available but optional:**
- ✅ Templates (`kailash create --template`)
- ✅ Quick Mode (`from kailash.quick`)
- ✅ Marketplace components (`pip install kailash-sso`)
- ✅ Enhanced CLI (`kailash dev`, `kailash upgrade`)
- ✅ Better error messages (automatic, non-breaking)
- ✅ Telemetry (opt-in only)

**Users can:**
- Continue using Full SDK as before
- Gradually adopt new features
- Never adopt (still works perfectly)

---

## Version Compatibility Matrix

### Supported Python Versions

**Before:** Python 3.10+
**After:** Python 3.10+
**Change:** None

### Supported Databases

**Before:** PostgreSQL, MySQL, SQLite
**After:** PostgreSQL, MySQL, SQLite
**Change:** None

### Dependency Versions

**Core SDK:**
```
Before: kailash 0.9.27
After:  kailash 0.10.0

Breaking changes: NONE
New features: Templates, Quick Mode, CLI, telemetry
Migration: Not required
```

**DataFlow:**
```
Before: kailash-dataflow 0.6.5
After:  kailash-dataflow 0.7.0

Breaking changes: NONE
New features: Better errors, validation helpers, Quick Mode hooks
Migration: Not required
```

**Nexus:**
```
Before: kailash-nexus 1.0.0
After:  kailash-nexus 1.1.0

Breaking changes: NONE
New features: Configuration presets, enhanced errors
Migration: Not required
```

**Kaizen:**
```
Before: kailash-kaizen 0.4.0
After:  kailash-kaizen 0.4.0

Breaking changes: NONE
New features: NONE (no changes)
Migration: Not required
```

---

## Migration Scenarios

### Scenario 1: Existing User Upgrades SDK

**Current state:**
```bash
# User's project (using SDK 0.9.27)
pip list | grep kailash
# kailash==0.9.27
```

**Upgrade:**
```bash
pip install --upgrade kailash

# New version
pip list | grep kailash
# kailash==0.10.0
```

**Result:**
```python
# User's code (unchanged)
from kailash.workflow.builder import WorkflowBuilder
# ...

# ✅ Works identically
# ✅ No changes needed
# ✅ Can optionally use new features (kailash create, etc.)
```

**Migration effort:** 0 hours (automatic)

### Scenario 2: Existing User Wants Templates

**Current state:**
```
User has 3 projects, all use Full SDK
Want to start new project faster
```

**Adoption:**
```bash
# New project with template
kailash create new-saas --template=saas-starter

# Existing projects unchanged
cd existing-project-1
# Uses Full SDK (as before)

cd existing-project-2
# Uses Full SDK (as before)
```

**Result:**
- ✅ New project uses template (faster start)
- ✅ Existing projects unchanged
- ✅ Can mix template and Full SDK projects

**Migration effort:** 0 hours (opt-in for new projects only)

### Scenario 3: Existing User Wants Component

**Current state:**
```python
# User built custom auth from scratch (50 lines)
def login_workflow():
    # Custom implementation
    pass
```

**Adoption:**
```bash
# Install component
pip install kailash-sso
```

**Replace custom code:**
```python
# Replace 50 lines with 5 lines
from kailash_sso import SSOManager

sso = SSOManager(providers={"google": {...}}, jwt_secret="...")
login_workflow = sso.login_workflow()  # ← Replaces custom implementation
```

**Result:**
- ✅ Less code to maintain (50 → 5 lines)
- ✅ Battle-tested (used by 100+ projects)
- ✅ Security updates automatic
- ✅ More features (OAuth2, SAML, MFA)

**Migration effort:** 1-2 hours (replace custom auth)

**Value:** 4+ hours saved on next project (don't rebuild)

### Scenario 4: User Wants to Try Quick Mode

**Current state:**
```python
# User's existing Full SDK project
from kailash.workflow.builder import WorkflowBuilder
from nexus import Nexus

# ... 200 lines of workflow definitions
```

**Can't easily migrate existing project:**
- Too much Full SDK code
- Complex workflows
- Custom nodes

**Recommendation:**
- Keep existing project on Full SDK
- Use Quick Mode for NEW projects
- Gradually adopt marketplace components in existing project

**Result:**
- ✅ Existing project: Full SDK (unchanged)
- ✅ New projects: Quick Mode (faster)
- ✅ Both use marketplace components

**Migration effort:** 0 hours (don't migrate existing)

---

## Testing Backward Compatibility

### Comprehensive Regression Suite

**Test every existing pattern:**
```python
# tests/regression/test_v0_9_compatibility.py

class TestV09Compatibility:
    """Ensure all v0.9.27 patterns still work in v0.10.0."""

    def test_basic_workflow_builder(self):
        """Test basic WorkflowBuilder usage."""
        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {
            "code": "return {'result': 42}",
            "inputs": {}
        })

        runtime = LocalRuntime()
        results, run_id = runtime.execute(workflow.build())

        assert results["test"]["result"] == 42

    def test_dataflow_model_registration(self):
        """Test DataFlow model registration."""
        db = DataFlow(":memory:")

        @db.model
        class User:
            name: str

        # Should generate nodes as before
        assert "User" in db._models
        assert "UserCreateNode" in db._nodes

    def test_nexus_workflow_registration(self):
        """Test Nexus workflow registration."""
        nexus = Nexus(api_port=8000)

        workflow = WorkflowBuilder()
        workflow.add_node("PythonCodeNode", "test", {...})

        nexus.register("test", workflow.build())

        assert "test" in nexus._workflows

    def test_all_110_nodes_still_work(self):
        """Test that all 110+ nodes are still available."""
        from kailash.nodes import node_registry

        # All nodes should be registered
        assert len(node_registry) >= 110

        # Sample nodes should work
        workflow = WorkflowBuilder()
        workflow.add_node("LLMNode", "test", {...})
        workflow.add_node("HTTPRequestNode", "api", {...})
        workflow.add_node("DataValidationNode", "validate", {...})

        # Should build without errors
        workflow.build()

    # ... 100+ more tests covering all existing patterns
```

**Test coverage:**
- Core SDK: All public APIs
- DataFlow: All decorators, all node types
- Nexus: All registration patterns
- Kaizen: All agent types
- **Goal: 100% coverage of existing functionality**

---

## Deprecation Strategy

### No Deprecations in Repivot

**Nothing is deprecated:**
- Full SDK remains primary API
- All existing patterns supported
- No features removed

**Future deprecations (if ever needed):**
1. **Announcement** (CHANGELOG, blog post, email)
2. **Deprecation warnings** (6 months)
3. **Continued support** (12 months)
4. **Final removal** (18 months)
5. **Migration guide** (always provided)

**Example (hypothetical future):**
```python
# If we ever deprecate something (NOT in current repivot)

def old_method(self):
    """Old method (deprecated).

    Deprecated in v2.0.0, will be removed in v3.0.0.
    Use new_method() instead.
    """
    import warnings
    warnings.warn(
        "old_method() is deprecated. Use new_method() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    return self.new_method()
```

---

## Version Upgrade Path

### From 0.9.27 to 0.10.0

**Step 1: Upgrade SDK**
```bash
pip install --upgrade kailash
```

**Step 2: Run tests**
```bash
pytest

# All tests should pass
# If any fail, report as bug (backward compatibility broken)
```

**Step 3: Optionally adopt new features**
```bash
# Try templates for new projects
kailash create new-project --template=saas-starter

# Or install components
pip install kailash-sso

# Or try Quick Mode
# ... (in new projects)
```

**Required changes to existing code:** ZERO

### From 0.6.5 to 0.7.0 (DataFlow)

**Step 1: Upgrade**
```bash
pip install --upgrade kailash-dataflow
```

**Step 2: Test**
```bash
pytest

# Should pass without changes
```

**Step 3: Optionally use helpers**
```bash
# Install helpers (optional)
pip install kailash-dataflow-utils

# Update code to use helpers (optional)
from kailash_dataflow_utils import TimestampField

# ... (prevents future errors)
```

**Required changes:** ZERO (helpers are optional)

---

## Migration for Custom Code

### Users with Custom Nodes

**Current custom node:**
```python
# user_project/custom_nodes.py

from kailash.nodes.base import BaseNode

class MyCustomNode(BaseNode):
    def execute(self, params):
        # Custom logic
        return result
```

**After upgrade:**
```python
# SAME CODE (unchanged)
from kailash.nodes.base import BaseNode

class MyCustomNode(BaseNode):
    def execute(self, params):
        # Custom logic
        return result

# ✅ Still works
```

**Migration effort:** 0 hours

### Users with Custom Runtime

**Current custom runtime:**
```python
from kailash.runtime.local import LocalRuntime

class MyCustomRuntime(LocalRuntime):
    def execute(self, workflow, inputs):
        # Custom pre-processing
        result = super().execute(workflow, inputs)
        # Custom post-processing
        return result
```

**After upgrade:**
```python
# SAME CODE (unchanged)
from kailash.runtime.local import LocalRuntime

class MyCustomRuntime(LocalRuntime):
    def execute(self, workflow, inputs):
        # Custom pre-processing
        result = super().execute(workflow, inputs)
        # Custom post-processing
        return result

# ✅ Still works
```

**Migration effort:** 0 hours

---

## Communication Plan

### Pre-Release (2 weeks before)

**1. Announcement:**
```markdown
# Kailash 0.10.0 Beta: Templates, Quick Mode, Component Marketplace

We're excited to announce Kailash 0.10.0 beta!

## What's New

🎨 **AI-Optimized Templates** - Working apps in 5 minutes
⚡ **Quick Mode** - FastAPI-like simplicity
📦 **Component Marketplace** - Reusable components (SSO, RBAC, admin)
🛠️ **Enhanced CLI** - Better developer experience

## 100% Backward Compatible

All existing code continues to work without changes.

## Beta Testing

Help us test the beta:
1. `pip install kailash==0.10.0b1`
2. Try new features
3. Report issues: github.com/kailash-sdk/kailash/issues

## Timeline

- Beta: Jan 15 - Jan 31
- Release: Feb 1
```

**2. Email to existing users:**
```
Subject: Kailash 0.10.0 Beta - Try Templates and Quick Mode

Hi [User],

We've been working on making Kailash even easier to use, especially for IT teams using AI coding assistants.

The beta is now available with:
- Templates (working apps in 5 minutes)
- Quick Mode (FastAPI-like simplicity)
- Component marketplace (reusable SSO, RBAC, etc.)

**Important: 100% backward compatible**
Your existing code will continue to work without any changes.

Try it: pip install kailash==0.10.0b1

Feedback: [survey link]

Thanks,
Kailash Team
```

### Release Day

**1. CHANGELOG.md:**
```markdown
# v0.10.0 (2025-02-01)

## 🎉 Major Features

### AI-Optimized Templates
Create production-ready apps in 5 minutes:
- `kailash create my-saas --template=saas-starter`
- Pre-configured DataFlow + Nexus
- Working auth, models, workflows included

### Quick Mode
FastAPI-like simplicity for rapid development:
```python
from kailash.quick import app, db

@db.model
class User:
    name: str

@app.post("/users")
def create_user(name: str):
    return db.users.create(name=name)

app.run()
```

### Component Marketplace
Reusable components on PyPI:
- `pip install kailash-sso` - Authentication
- `pip install kailash-rbac` - RBAC
- `pip install kailash-admin` - Admin dashboard
- `pip install kailash-payments` - Payment processing
- `pip install kailash-dataflow-utils` - Field helpers

### Enhanced CLI
- `kailash create` - Create from template
- `kailash dev` - Dev server with auto-reload
- `kailash upgrade` - Upgrade Quick → Full SDK
- `kailash marketplace` - Component discovery

## 🔧 Improvements

- Better error messages (AI-friendly, actionable)
- Telemetry support (opt-in, anonymous)
- Nexus configuration presets
- DataFlow validation helpers

## ❌ Breaking Changes

**NONE** - 100% backward compatible

## 📈 Upgrade Guide

```bash
pip install --upgrade kailash kailash-dataflow kailash-nexus
```

No code changes required. All existing functionality unchanged.

To use new features, see: https://docs.kailash.dev/v0.10/whats-new
```

**2. Blog post:**
```markdown
# Kailash 0.10: Built for the AI Era

[Announcement blog post highlighting new features]

[Emphasize backward compatibility]

[Show before/after code examples]

[Video demos]
```

**3. Social media:**
```
🎉 Kailash 0.10 is here!

✨ Templates - Working apps in 5 minutes
⚡ Quick Mode - FastAPI-like simplicity
📦 Component Marketplace - Reusable SSO, RBAC, admin

100% backward compatible - upgrade with confidence

Try it: pip install --upgrade kailash

https://kailash.dev/v0.10
```

### Post-Release Support

**1. Migration support channel:**
- Dedicated Discord channel: #v0.10-upgrade
- Quick response to issues
- Hotfix releases if needed

**2. Documentation:**
- Migration FAQ
- Video tutorials
- Live office hours (optional)

**3. Monitoring:**
- Track error rates (should not increase)
- Monitor support tickets (categorize by version)
- Survey satisfaction

---

## Testing Migration

### Automated Compatibility Tests

```python
# tests/compatibility/test_v09_to_v10.py

def test_v09_project_works_with_v10():
    """Test that v0.9.27 project works with v0.10.0."""

    # Simulate v0.9.27 project structure
    project_dir = create_v09_project()

    # Install v0.10.0
    subprocess.run([
        sys.executable, '-m', 'pip', 'install',
        'kailash==0.10.0'
    ], check=True)

    # Run project
    process = subprocess.Popen(
        ['python', 'main.py'],
        cwd=project_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    # Should start without errors
    time.sleep(3)

    try:
        # Test API still works
        response = requests.post('http://localhost:8000/workflows/test/execute')
        assert response.status_code == 200

    finally:
        process.terminate()

    # ✅ v0.9.27 project works with v0.10.0
```

### Real-World Project Testing

**Beta testing with actual users:**
1. Identify 10 existing users with production deployments
2. Ask them to test beta in staging environment
3. Monitor for any breaking changes
4. Fix issues before public release

**Validation criteria:**
- All 10 projects work without code changes
- No performance regressions
- No new errors

---

## Rollback Plan

### If Something Goes Wrong

**Scenario:** Critical bug found after release

**Response:**
1. **Immediate:** Announce issue publicly
2. **Hotfix:** Release v0.10.1 within 24 hours
3. **Rollback option:** Users can downgrade
   ```bash
   pip install kailash==0.9.27
   ```

**Rollback guarantee:**
- v0.9.27 remains available on PyPI
- Users can downgrade anytime
- No data loss (schemas compatible)

---

## Long-Term Compatibility

### Commitment

**1-Year Guarantee:**
- v0.9.27 will be supported for 12 months after v0.10.0 release
- Security patches backported
- Critical bugs fixed

**After 1 year:**
- v0.9.x enters maintenance mode (security only)
- Users encouraged to upgrade to v0.10.x
- But still works (not removed from PyPI)

### Future Versions

**Planned:**
- v0.10.x: Minor features, bug fixes (backward compatible)
- v0.11.x: More components, improvements (backward compatible)
- v1.0.0: Production-ready declaration (when ecosystem mature)

**v1.0.0 criteria:**
- 1000+ GitHub stars
- 500+ production deployments
- 50+ marketplace components
- 6+ months of stability

**v2.0.0 (if ever):**
- Only after v1.0.0 is stable for 2+ years
- Breaking changes announced 12 months in advance
- Comprehensive migration guide
- Automated migration tooling

---

## Documentation Migration

### Old Docs (Keep for Reference)

**Location:** `sdk-users/legacy/` (moved, not deleted)

**Content:**
- All existing documentation (246,800 lines)
- Marked as "legacy reference"
- Links to new docs

**Purpose:**
- Historical reference
- For users who prefer old structure
- Search engine indexing preserved

### New Docs (Primary)

**Location:** `sdk-users/docs-it-teams/` and `sdk-users/docs-developers/`

**Content:**
- Rewritten for target audiences
- IT teams: 10 Golden Patterns focus
- Developers: Comprehensive technical docs

**Migration:**
- All links from old docs point to new docs
- 301 redirects on website
- Search engine reindexing

---

## Key Takeaways

**Backward compatibility is non-negotiable:**
- 100% of existing code must work
- Zero required migration effort
- Users opt-in to new features

**Testing is comprehensive:**
- Regression suite covers all existing patterns
- Real-world beta testing with production users
- Rollback plan if issues found

**Communication is clear:**
- Emphasize backward compatibility in all messaging
- Provide migration guides (even though not required)
- Support channel for questions

**Risk is minimized:**
- Changes are additive only
- Existing behavior preserved
- Gradual rollout with beta period

**Success metric:**
- Zero support tickets about "upgrade broke my code"
- High adoption of new features (opt-in)
- Positive feedback from existing users

---

**Next:** See additional documentation categories (go-to-market, risks, prototype plan)
