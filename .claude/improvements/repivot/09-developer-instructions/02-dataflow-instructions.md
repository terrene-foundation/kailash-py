# DataFlow Team: Developer Instructions

**Team:** DataFlow Framework Development
**Timeline:** Weeks 3-8 (parallel with templates)
**Estimated Effort:** 60 hours
**Priority:** High (prevents 48-hour datetime errors)

---

## Your Responsibilities

You are responsible for preventing common DataFlow errors:

1. ✅ Build kailash-dataflow-utils package (TimestampField, UUIDField, JSONField)
2. ✅ Enhance error messages in DataFlow nodes
3. ✅ Add validation helper methods to DataFlow engine
4. ✅ Add Quick Mode detection and defaults
5. ✅ Integrate with ValidatingLocalRuntime (from Core SDK team)

**Impact:** Prevents the 48-hour datetime error that users currently experience

---

## Required Reading

### MUST READ (Before Starting):

**1. Strategic Context (45 min):**
- `../01-strategy/01-problem-analysis.md` - Root cause #1 and #5 (component reusability, datetime errors)

**2. Codebase Analysis (1 hour):**
- `../02-implementation/01-codebase-analysis/dataflow-structure.md` - Your domain (742 lines)

**3. Your Specifications (1.5 hours):**
- `../02-implementation/02-new-components/05-official-components.md` - kailash-dataflow-utils spec (section 1)
- `../02-implementation/03-modifications/02-dataflow-modifications.md` - DataFlow enhancements (773 lines)

**4. Integration Context (30 min):**
- `../02-implementation/04-integration/00-integration-overview.md` - How your work prevents errors

**5. Backward Compatibility (30 min):**
- `../02-implementation/05-migration/00-migration-overview.md` - Critical constraints

**Total reading:** 4 hours

### SHOULD READ (For Context):

- `../02-implementation/02-new-components/02-quick-mode-specification.md` - How Quick Mode uses your validation
- `../02-implementation/02-new-components/03-golden-patterns.md` - Pattern #1 (DataFlow model) uses your helpers

---

## Detailed Tasks

### Task 1: Build kailash-dataflow-utils Package

**Priority:** CRITICAL (prevents most common errors)

**New package to create:**
```
packages/kailash-dataflow-utils/
├── src/kailash_dataflow_utils/
│   ├── __init__.py
│   ├── fields.py         # TimestampField, UUIDField, JSONField
│   ├── validators.py     # EmailValidator, PhoneValidator
│   └── mixins.py         # TimestampMixin, SoftDeleteMixin
├── tests/
│   ├── unit/
│   └── integration/
├── README.md
├── CLAUDE.md
└── pyproject.toml
```

**Specification reference:** `02-new-components/05-official-components.md` (Component 1, lines 50-350)

**What to build:**

**1. TimestampField class:**
```python
class TimestampField:
    @staticmethod
    def now() -> datetime:
        """Return current UTC datetime (not string)."""
        return datetime.now(timezone.utc)

    @staticmethod
    def validate(value: Any) -> datetime:
        """Validate and convert to datetime."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            raise ValueError(
                "Expected datetime, got string. "
                "Did you use .isoformat()? Use TimestampField.now() instead."
            )
        raise ValueError(f"Expected datetime, got {type(value)}")
```

**This solves the 48-hour debugging problem!**

**2. UUIDField class:**
```python
class UUIDField:
    @staticmethod
    def generate() -> str:
        """Generate new UUID string."""
        return str(uuid.uuid4())

    @staticmethod
    def validate(value: Any) -> str:
        """Validate UUID format."""
        uuid.UUID(value)  # Validates format
        return value.lower()
```

**3. JSONField class:**
```python
class JSONField:
    @staticmethod
    def validate(value: Any) -> dict:
        """Validate and convert to dict."""
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            raise ValueError(
                "Expected dict, got string. "
                "Did you use json.dumps()? Pass dict directly."
            )
        raise ValueError(f"Expected dict, got {type(value)}")
```

**Testing:**
- Tier 1: Unit tests for each field helper
- Tier 2: Integration tests with real DataFlow models
- Tier 3: E2E test preventing actual datetime error

**Timeline:** Week 3-4 (2 weeks, 20 hours)

---

### Task 2: Enhanced Node Error Messages

**Files to modify:**
- `apps/kailash-dataflow/src/dataflow/core/nodes.py`

**New file to create:**
- `apps/kailash-dataflow/src/dataflow/core/exceptions.py`

**Specification reference:** `03-modifications/02-dataflow-modifications.md` (lines 10-220)

**What to build:**

**1. DataFlowExecutionError class:**
```python
class DataFlowExecutionError(Exception):
    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(message)
        self.context = context or {}

    def __str__(self):
        # Format with AI-friendly suggestions
        pass
```

**2. Enhanced error handling in generated nodes:**

Modify `NodeGenerator._generate_create_node_class()`:
```python
def execute(self, params: dict) -> dict:
    try:
        result = self._execute_create(params)
        return result
    except Exception as e:
        # BUILD ERROR CONTEXT
        context = self._build_error_context(e, params)
        raise DataFlowExecutionError(
            f"{self.model_name}CreateNode failed: {context['message']}",
            context=context
        ) from e

def _build_error_context(self, error, params):
    # Pattern match common errors
    # Provide AI-friendly suggestions
    pass
```

**3. Pattern matching for common errors:**
- "operator does not exist: text = integer" → datetime.isoformat() issue
- "violates not-null constraint" → missing required field
- "duplicate key" → unique constraint violation

**Timeline:** Week 5-6 (2 weeks, 20 hours)

---

### Task 3: Validation Helper Methods

**Files to modify:**
- `apps/kailash-dataflow/src/dataflow/core/engine.py`

**Specification reference:** `03-modifications/02-dataflow-modifications.md` (lines 222-380)

**What to build:**

**1. Validation methods in DataFlow class:**
```python
def validate_model_parameters(
    self,
    model_name: str,
    operation: str,
    params: dict
) -> List[str]:
    """Validate parameters before execution."""
    # Check for auto-managed fields
    # Check for required fields
    # Check types (datetime, dict, etc.)
    pass

def get_datetime_fields(self, model_name: str) -> List[str]:
    """Get list of datetime fields for a model."""
    pass

def get_json_fields(self, model_name: str) -> List[str]:
    """Get list of JSON fields for a model."""
    pass
```

**2. Used by Quick Mode for pre-execution validation:**
```python
# In Quick Mode (not your responsibility to build, but design interface for)
errors = db.validate_model_parameters("User", "create", params)
if errors:
    raise ValueError("Validation failed:\n" + "\n".join(errors))
```

**Timeline:** Week 7 (1 week, 10 hours)

---

### Task 4: Quick Mode Integration Hooks

**Files to modify:**
- `apps/kailash-dataflow/src/dataflow/core/engine.py`

**Specification reference:** `03-modifications/02-dataflow-modifications.md` (lines 382-500)

**What to build:**

**1. Quick Mode detection:**
```python
def __init__(
    self,
    database_url: Optional[str] = None,
    quick_mode: bool = False,  # ← ADD THIS
    **kwargs
):
    self._quick_mode = quick_mode or self._detect_quick_mode()

    if self._quick_mode:
        # Apply Quick Mode defaults
        kwargs['multi_tenant'] = False
        kwargs['audit_logging'] = False
        kwargs['debug'] = True

def _detect_quick_mode(self) -> bool:
    """Auto-detect Quick Mode from project structure."""
    return Path(".ai-mode").exists()
```

**2. Enhanced model registration feedback (debug mode):**
```python
def model(self, cls):
    # ... existing registration

    # ADD: Debug feedback
    if self.config.debug or self._quick_mode:
        print(f"✅ Model '{model_name}' registered")
        print(f"   Nodes generated: {model_name}CreateNode, ReadNode, ...")
```

**Timeline:** Week 8 (1 week, 10 hours)

---

## Subagent Workflow for DataFlow Team

### Week 3: Component Planning

**Day 1:**
```bash
# Understand DataFlow architecture
> Use the sdk-navigator subagent to locate DataFlow model registration, node generation, and error handling code

# Get DataFlow-specific guidance
> Use the dataflow-specialist subagent to understand current error handling patterns and validation approaches in DataFlow

# Analyze requirements
> Use the requirements-analyst subagent to break down kailash-dataflow-utils package requirements and DataFlow validation enhancements
```

**Day 2:**
```bash
# Create task breakdown
> Use the todo-manager subagent to create detailed task breakdown for dataflow-utils package and DataFlow engine modifications

# Complexity analysis
> Use the ultrathink-analyst subagent to identify potential failure points in field validation and error message enhancements

# Validate approach
> Use the intermediate-reviewer subagent to review task breakdown and ensure approach prevents common errors effectively
```

**Day 3-5:**
```bash
# Write tests first (TDD)
> Use the tdd-implementer subagent to create comprehensive test suite for TimestampField, UUIDField, JSONField, and validation methods

# Design validation
> Use the testing-specialist subagent to ensure test suite covers all common DataFlow error scenarios
```

---

### Week 4: Implement kailash-dataflow-utils

**Day 6-7:**
```bash
# Implement field helpers
> Use the dataflow-specialist subagent to implement TimestampField, UUIDField, and JSONField following DataFlow patterns

# Review implementation
> Use the gold-standards-validator subagent to validate field helpers follow security and type safety standards
```

**Day 8:**
```bash
# Implement validators and mixins
> Use the dataflow-specialist subagent to implement validators and mixins for common DataFlow patterns

# Test with real DataFlow models
> Use the testing-specialist subagent to run integration tests with actual DataFlow models and workflows
```

**Day 9-10:**
```bash
# Package and publish
> Use the dataflow-specialist subagent to review package structure and ensure proper DataFlow integration

# Documentation
> Use the documentation-validator subagent to test all examples in README and CLAUDE.md

# Publish to TestPyPI
# Validate installation and imports
```

---

### Week 5-6: Enhanced Error Messages

**Day 11-13:**
```bash
# Implement DataFlowExecutionError
> Use the dataflow-specialist subagent to implement enhanced error class with context and suggestions

# Add error context building
> Use the pattern-expert subagent to implement error pattern matching for common DataFlow errors

# Review error messages
> Use the intermediate-reviewer subagent to ensure error messages are AI-friendly and actionable
```

**Day 14-15:**
```bash
# Integrate into node generation
> Use the dataflow-specialist subagent to modify NodeGenerator to use enhanced error handling

# Test error messages
> Use the testing-specialist subagent to verify error messages provide helpful suggestions for all common error types
```

---

### Week 7: Validation Helpers

**Day 16-18:**
```bash
# Implement validation methods
> Use the dataflow-specialist subagent to implement validate_model_parameters, get_datetime_fields, and get_json_fields in DataFlow engine

# Test validation accuracy
> Use the testing-specialist subagent to verify validation catches 90%+ of common mistakes before execution

# Document validation API
> Use the documentation-validator subagent to ensure validation methods are properly documented for Quick Mode integration
```

---

### Week 8: Quick Mode Integration + Final Testing

**Day 19-20:**
```bash
# Implement Quick Mode hooks
> Use the dataflow-specialist subagent to add Quick Mode detection and defaults to DataFlow engine

# Coordinate with Core SDK team
# Test ValidatingLocalRuntime + DataFlow validation together

# Test enhanced feedback
> Use the testing-specialist subagent to verify model registration feedback appears correctly in debug mode
```

**Day 21-22:**
```bash
# Comprehensive integration testing
> Use the dataflow-specialist subagent to validate all DataFlow enhancements work together (utils, errors, validation, Quick Mode)

# Backward compatibility verification
> Use the gold-standards-validator subagent to run complete backward compatibility test suite for DataFlow

# Final review
> Use the intermediate-reviewer subagent to perform final review of all DataFlow enhancements before PR
```

**Day 23:**
```bash
# Documentation and PR
> Use the documentation-validator subagent to validate all DataFlow documentation updates

> Use the git-release-specialist subagent to create PR for DataFlow enhancements with comprehensive description and tests
```

---

## Success Criteria

### kailash-dataflow-utils Package

**Definition of Done:**
- [ ] TimestampField.now() returns datetime (not string)
- [ ] TimestampField.validate() catches .isoformat() mistake
- [ ] UUIDField.generate() creates valid UUID
- [ ] JSONField.validate() catches json.dumps() mistake
- [ ] Package published to PyPI
- [ ] Installation works: `pip install kailash-dataflow-utils`
- [ ] Tests: 80%+ coverage
- [ ] README with 5-minute quick start
- [ ] CLAUDE.md with AI instructions

**User impact:** Prevents datetime errors BEFORE they happen

### Enhanced Error Messages

**Definition of Done:**
- [ ] DataFlowExecutionError class created
- [ ] Error context built for all node types
- [ ] Pattern matching for 5+ common errors
- [ ] Suggestions are actionable and AI-friendly
- [ ] Tests verify error messages helpful
- [ ] Backward compatibility: old errors still work

**User impact:** 48-hour debugging → 5-minute fix

### Validation Helpers

**Definition of Done:**
- [ ] validate_model_parameters() method implemented
- [ ] get_datetime_fields() method implemented
- [ ] get_json_fields() method implemented
- [ ] Validation catches created_at/updated_at mistakes
- [ ] Validation catches type mismatches
- [ ] Tests verify 90%+ accuracy
- [ ] Interface ready for Quick Mode team

**User impact:** Pre-execution validation catches errors immediately

### Quick Mode Integration

**Definition of Done:**
- [ ] Quick Mode detection working
- [ ] Quick Mode defaults applied correctly
- [ ] Model registration feedback in debug mode
- [ ] Tests verify Quick Mode behavior
- [ ] Regular mode unchanged (backward compatible)

**User impact:** Better developer experience in Quick Mode

---

## Integration Points

### With Core SDK Team

**Dependency:** Need ValidatingLocalRuntime interface

**Coordination:**
- Week 8: Get ValidatingLocalRuntime API
- Test your validation methods with their runtime
- Ensure consistent error format

**Meeting:** Week 8, integration testing

### With Templates Team

**Dependency:** Templates will use kailash-dataflow-utils

**Coordination:**
- Week 4: Share kailash-dataflow-utils package
- Templates team integrates into SaaS template
- Verify error prevention works in template context

**Meeting:** Week 4, demo field helpers

### With Quick Mode Team (If Separate)

**Dependency:** Quick Mode uses your validation methods

**Coordination:**
- Week 7: Share validation API
- Quick Mode team builds QuickDB using your methods
- Test integration thoroughly

**Meeting:** Week 7, API review

---

## Code Examples

### Example 1: TimestampField Implementation

```python
# packages/kailash-dataflow-utils/src/kailash_dataflow_utils/fields.py

from datetime import datetime, timezone
from typing import Any

class TimestampField:
    """Prevent datetime.isoformat() errors."""

    @staticmethod
    def now() -> datetime:
        """Return current UTC datetime.

        Example:
            workflow.add_node("UserCreateNode", "create", {
                "created_at": TimestampField.now()  # ✅ Correct
            })

        Don't use:
            "created_at": datetime.now().isoformat()  # ❌ Wrong
        """
        return datetime.now(timezone.utc)

    @staticmethod
    def validate(value: Any) -> datetime:
        """Validate datetime value.

        Catches common mistake: passing string instead of datetime.

        Raises:
            ValueError with helpful message if string detected
        """
        if isinstance(value, datetime):
            return value

        if isinstance(value, str):
            raise ValueError(
                f"❌ Type Error: Expected datetime, got string\n\n"
                f"You provided: '{value}' (string)\n"
                f"Expected: datetime object\n\n"
                f"Did you use .isoformat()?\n"
                f"  ❌ WRONG: datetime.now().isoformat()\n"
                f"  ✅ CORRECT: TimestampField.now()\n\n"
                f"This prevents the 'operator does not exist: text = integer' error."
            )

        raise ValueError(f"Expected datetime or string, got {type(value).__name__}")
```

### Example 2: Enhanced DataFlow Error

```python
# apps/kailash-dataflow/src/dataflow/core/nodes.py

class GeneratedCreateNode(BaseNode):
    def execute(self, params: dict) -> dict:
        try:
            result = self._execute_create(params)
            return result
        except Exception as e:
            # BUILD ERROR CONTEXT
            context = self._build_error_context(e, params)

            # RAISE ENHANCED ERROR
            from dataflow.core.exceptions import DataFlowExecutionError
            raise DataFlowExecutionError(
                f"{self.model_name}CreateNode failed: {context['message']}",
                context=context
            ) from e

    def _build_error_context(self, error: Exception, params: dict) -> dict:
        """Build AI-friendly error context."""
        error_str = str(error).lower()

        context = {
            "model": self.model_name,
            "operation": "create",
            "error": str(error),
            "suggestions": []
        }

        # PATTERN MATCH COMMON ERRORS
        if "operator does not exist: text = integer" in error_str:
            datetime_fields = self._find_datetime_fields()
            likely_field = self._find_likely_culprit(params, datetime_fields)

            context["suggestions"].append(
                f"❌ Type mismatch in field '{likely_field}'\n\n"
                f"Field expects: datetime\n"
                f"You provided: string (probably from .isoformat())\n\n"
                f"Fix:\n"
                f"  ❌ WRONG: datetime.now().isoformat()\n"
                f"  ✅ CORRECT: datetime.now()\n\n"
                f"Or use kailash-dataflow-utils:\n"
                f"  pip install kailash-dataflow-utils\n"
                f"  from kailash_dataflow_utils import TimestampField\n"
                f"  '{likely_field}': TimestampField.now()"
            )

        return context
```

---

## Testing Protocol

### Tier 1: Unit Tests (Fast, Mocked)

```python
# packages/kailash-dataflow-utils/tests/unit/test_fields.py

def test_timestamp_field_now_returns_datetime():
    """TimestampField.now() returns datetime object."""
    result = TimestampField.now()
    assert isinstance(result, datetime)

def test_timestamp_field_validate_catches_string():
    """TimestampField.validate() catches isoformat() mistake."""
    with pytest.raises(ValueError, match="Did you use .isoformat()"):
        TimestampField.validate("2025-01-15T10:30:00")

def test_uuid_field_generates_valid_uuid():
    """UUIDField.generate() creates valid UUID."""
    uid = UUIDField.generate()
    uuid.UUID(uid)  # Should not raise
```

### Tier 2: Integration Tests (Real DataFlow)

```python
# packages/kailash-dataflow-utils/tests/integration/test_with_dataflow.py

def test_timestamp_field_prevents_actual_error():
    """Test that TimestampField actually prevents database error."""
    from dataflow import DataFlow
    from kailash.workflow.builder import WorkflowBuilder
    from kailash.runtime.local import LocalRuntime

    db = DataFlow(":memory:")

    @db.model
    class Session:
        user_id: str
        created_at: datetime

    # THIS SHOULD WORK (using TimestampField)
    workflow = WorkflowBuilder()
    workflow.add_node("SessionCreateNode", "create", {
        "user_id": "user-123",
        "created_at": TimestampField.now()  # ✅ Correct type
    })

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["create"]["created_at"] is not None

def test_error_message_enhancement_with_real_error():
    """Test enhanced error messages with actual database error."""
    db = DataFlow(":memory:")

    @db.model
    class User:
        name: str
        created_at: datetime

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "name": "Alice",
        "created_at": datetime.now().isoformat()  # ❌ String, will fail
    })

    runtime = LocalRuntime()

    with pytest.raises(DataFlowExecutionError) as exc:
        runtime.execute(workflow.build())

    # Verify enhanced error has helpful suggestions
    error_text = str(exc.value)
    assert "isoformat" in error_text
    assert "TimestampField.now()" in error_text
```

### Tier 3: E2E Tests (Complete User Flow)

```python
# tests/e2e/test_dataflow_error_prevention.py

def test_complete_error_prevention_flow():
    """Test that users avoid 48-hour datetime error entirely."""

    # Scenario: User creates model and workflow following template pattern

    # 1. Install kailash-dataflow-utils
    subprocess.run(["pip", "install", "kailash-dataflow-utils"], check=True)

    # 2. Create model using field helpers
    code = '''
from dataflow import DataFlow
from kailash_dataflow_utils import TimestampField, UUIDField

db = DataFlow(":memory:")

@db.model
class Session:
    id: str
    user_id: str
    created_at: datetime

workflow = WorkflowBuilder()
workflow.add_node("SessionCreateNode", "create", {
    "id": UUIDField.generate(),
    "user_id": "user-123",
    "created_at": TimestampField.now()
})
    '''

    # 3. Execute - should work without errors
    # ... (run code, verify success)

    # ✅ User NEVER hits datetime error (prevented by design)
```

---

## Common Pitfalls for DataFlow Team

### ❌ Breaking DataFlow Public API

**Wrong:**
```python
def model(self, cls, quick_mode=False):  # ❌ Changes signature
```

**Right:**
```python
def model(self, cls):  # ✅ Signature unchanged
    # Quick mode detected automatically via self._quick_mode
```

### ❌ Modifying Node Execution Logic

**Wrong:**
```python
def execute(self, params):
    # Rewrite entire create logic ❌
```

**Right:**
```python
def execute(self, params):
    try:
        # EXISTING logic (unchanged)
        result = self._execute_create(params)
        return result
    except Exception as e:
        # ADD error enhancement (wrapper only)
        context = self._build_error_context(e, params)
        raise DataFlowExecutionError(..., context=context) from e
```

### ❌ Forgetting to Test Backward Compatibility

**Must test:**
```python
def test_existing_dataflow_usage_unchanged():
    """ALL v0.6.5 code must work with v0.7.0."""

    # Test EVERY existing pattern:
    # - Model registration
    # - Node generation
    # - CRUD operations
    # - Bulk operations
    # - Multi-tenancy

    # If ANY fail → you broke backward compatibility
```

---

## Deliverables

### Week 4 (End):
- [ ] kailash-dataflow-utils package published to TestPyPI
- [ ] TimestampField, UUIDField, JSONField working
- [ ] Tests passing (80%+ coverage)
- [ ] README and CLAUDE.md complete

### Week 6 (End):
- [ ] Enhanced error messages in DataFlow nodes
- [ ] DataFlowExecutionError class created
- [ ] Pattern matching for 5+ common errors
- [ ] Tests verify errors are helpful
- [ ] Backward compatibility verified

### Week 7 (End):
- [ ] Validation helper methods in DataFlow engine
- [ ] validate_model_parameters() working
- [ ] get_datetime_fields() and get_json_fields() working
- [ ] Tests verify validation accuracy
- [ ] Interface documented for Quick Mode team

### Week 8 (End):
- [ ] Quick Mode integration complete
- [ ] Detection working (_detect_quick_mode)
- [ ] Defaults applied correctly
- [ ] Model registration feedback enhanced
- [ ] PR ready for review

---

## Coordination Meetings

**Week 3:** Kickoff with Templates team (understand patterns)
**Week 4:** Demo kailash-dataflow-utils to Templates team
**Week 6:** Review error messages with Core SDK team (consistency)
**Week 7:** API review with Quick Mode team (validation interface)
**Week 8:** Integration testing with Core SDK team

---

## Success Metrics for Your Work

**You succeed if:**
- ✅ Users install kailash-dataflow-utils (track downloads)
- ✅ Datetime errors reduced by 90%+ (track error telemetry)
- ✅ Error messages rated "helpful" (user surveys)
- ✅ Zero backward compatibility breaks (existing tests pass 100%)

**Track:**
- PyPI downloads of kailash-dataflow-utils
- Validation catch rate (how many errors prevented)
- User feedback on error messages
- Backward compatibility test pass rate

---

**You are preventing the single most frustrating error in DataFlow. Users will thank you every time they don't hit the 48-hour datetime debugging session.**
