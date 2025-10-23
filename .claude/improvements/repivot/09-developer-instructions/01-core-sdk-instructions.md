# Core SDK Team: Developer Instructions

**Team:** Core SDK Development
**Timeline:** Weeks 9-12 (after templates are designed)
**Estimated Effort:** 80 hours
**Priority:** Medium (enables Quick Mode and telemetry)

---

## Your Responsibilities

You are responsible for enhancing the Core SDK runtime and adding telemetry:

1. ✅ Add telemetry hooks to LocalRuntime and AsyncLocalRuntime
2. ✅ Enhance error context in WorkflowExecutionError
3. ✅ Create ValidatingLocalRuntime for Quick Mode
4. ✅ Add performance tracking
5. ✅ Ensure 100% backward compatibility

**Impact:** Enables better error messages (prevents 48-hour debugging) and usage tracking

---

## Required Reading

### MUST READ (Before Starting):

**1. Strategic Context (1 hour):**
- `../01-strategy/00-overview.md` - Understand the repivot vision
- `../01-strategy/01-problem-analysis.md` - Understand root cause #2 and #3

**2. Codebase Analysis (30 min):**
- `../02-implementation/01-codebase-analysis/core-sdk-structure.md` - Your domain

**3. Your Specifications (1 hour):**
- `../02-implementation/03-modifications/01-runtime-modifications.md` - What to build

**4. Integration Context (30 min):**
- `../02-implementation/04-integration/00-integration-overview.md` - How your work fits

**5. Backward Compatibility (30 min):**
- `../02-implementation/05-migration/00-migration-overview.md` - Critical constraints

**Total reading:** 3.5 hours

### SHOULD READ (For Context):

- `../02-implementation/02-new-components/02-quick-mode-specification.md` - How Quick Mode uses ValidatingLocalRuntime
- `../06-success-validation/00-measurement-framework.md` - What telemetry should track

---

## Detailed Tasks

### Task 1: Add Telemetry Hooks

**Files to modify:**
- `src/kailash/runtime/local.py`
- `src/kailash/runtime/async_local.py`

**New file to create:**
- `src/kailash/runtime/telemetry.py`

**Specification reference:** `03-modifications/01-runtime-modifications.md` (lines 10-180)

**What to build:**

1. **TelemetryCollector class** (`runtime/telemetry.py`):
   ```python
   class TelemetryCollector:
       def track_execution_start(workflow_id, node_count, timestamp)
       def track_execution_success(workflow_id, run_id, duration, node_count)
       def track_execution_error(workflow_id, error_type, error_category)
   ```

2. **Add telemetry to LocalRuntime**:
   - Add `enable_telemetry` parameter (default: False)
   - Initialize TelemetryCollector if enabled
   - Track events in execute() method

3. **Privacy-first design:**
   - Opt-in only (disabled by default)
   - Anonymous (no user IDs, no code contents)
   - Local storage only (no automatic upload)

**Backward compatibility:**
- Default behavior unchanged (telemetry=False)
- Existing code works identically

**Testing:**
- Write tests that verify telemetry OFF by default
- Write tests that verify telemetry works when enabled
- Write tests that verify no data leaks (privacy)

---

### Task 2: Enhanced Error Context

**Files to modify:**
- `src/kailash/runtime/local.py` (execute method)
- `src/kailash/runtime/async_local.py` (execute method)
- `src/kailash/sdk_exceptions.py` (WorkflowExecutionError)

**Specification reference:** `03-modifications/01-runtime-modifications.md` (lines 182-350)

**What to build:**

1. **Enhanced WorkflowExecutionError**:
   ```python
   class WorkflowExecutionError(Exception):
       def __init__(self, message: str, context: Optional[dict] = None)
       def __str__(self) → format with suggestions
   ```

2. **Error context builder** in LocalRuntime:
   ```python
   def _build_error_context(self, node, params, error) → dict
   def _sanitize_params(self, params) → dict (remove secrets)
   ```

3. **Pattern matching for common errors:**
   - "operator does not exist: text = integer" → suggest datetime fix
   - "required parameter missing" → list required parameters
   - "created_at" errors → explain auto-managed fields

**AI-friendly error format:**
```
WorkflowExecutionError: Node 'create_user' failed: Type mismatch

Category: type_mismatch

Suggestions:
  - datetime.now().isoformat() → use datetime.now() instead
  - Check DataFlow common errors guide

Documentation:
  https://docs.kailash.dev/errors/type-mismatch
```

**Backward compatibility:**
- `WorkflowExecutionError("message")` still works (existing usage)
- `WorkflowExecutionError("message", context={...})` adds features

**Testing:**
- Test that old error format still works
- Test that new error format provides suggestions
- Test that sensitive data is sanitized

---

### Task 3: ValidatingLocalRuntime

**New file to create:**
- `src/kailash/runtime/validation.py`

**Specification reference:** `03-modifications/01-runtime-modifications.md` (lines 352-480)

**What to build:**

1. **ValidatingLocalRuntime class**:
   ```python
   class ValidatingLocalRuntime(LocalRuntime):
       def __init__(self, config, strict_mode=True)
       def execute(self, workflow, inputs) → validate then execute
   ```

2. **WorkflowValidator class**:
   ```python
   class WorkflowValidator:
       def validate_workflow(self, workflow, inputs) → List[errors]
       def _validate_node(self, node, inputs) → List[errors]
       def _validate_connections(self, workflow) → List[errors]
   ```

3. **Validation rules:**
   - Check for created_at/updated_at in CreateNode parameters
   - Check for filter/fields in UpdateNode parameters
   - Check for disconnected nodes
   - Check for missing required inputs

**Usage by Quick Mode:**
```python
# Quick Mode uses ValidatingLocalRuntime
from kailash.runtime.validation import ValidatingLocalRuntime

runtime = ValidatingLocalRuntime(strict_mode=True)
results, run_id = runtime.execute(workflow, inputs)
# Raises ValidationError before executing if issues found
```

**Backward compatibility:**
- NEW class (doesn't affect existing LocalRuntime)
- Opt-in only (Quick Mode uses it)
- Full SDK users can choose to use or not

**Testing:**
- Test that validation catches common mistakes
- Test that strict_mode=True raises, False warns
- Test that validated workflows execute normally

---

### Task 4: Performance Tracking

**Files to modify:**
- `src/kailash/runtime/local.py` (execute method)
- `src/kailash/runtime/async_local.py` (execute method)

**Specification reference:** `03-modifications/01-runtime-modifications.md` (lines 482-550)

**What to build:**

1. **Per-node timing** in execute():
   ```python
   node_timings = {}
   for node in workflow.nodes:
       start = time.time()
       result = self._execute_node(node, context)
       node_timings[node.id] = time.time() - start
   ```

2. **Slow execution warnings** (debug mode):
   ```
   ⚠️  Slow workflow execution (12.5s)
      Slowest nodes:
        - external_api: 10.2s
        - data_transform: 1.8s
   ```

3. **Execution history tracking**:
   ```python
   self._execution_history.append({
       "run_id": run_id,
       "total_time": total_time,
       "node_timings": node_timings
   })
   ```

**Backward compatibility:**
- Only affects debug logging (non-breaking)
- Performance impact minimal (<1% overhead)

**Testing:**
- Test that timings are tracked when debug=True
- Test that no overhead when debug=False
- Test that slow execution warnings appear correctly

---

## Subagent Workflow for Core SDK Team

### Before Starting Any Task

**Run this sequence:**

```bash
# 1. Understand requirements
> Use the requirements-analyst subagent to break down Core SDK runtime enhancements into detailed subtasks

# 2. Navigate existing code
> Use the sdk-navigator subagent to find existing error handling patterns and runtime execution code in Core SDK

# 3. Get Core SDK-specific guidance
> Use the pattern-expert subagent to review best practices for runtime modifications and error handling

# 4. Create task breakdown
> Use the todo-manager subagent to create detailed task breakdown for telemetry, validation, and error enhancements

# 5. Validate approach
> Use the intermediate-reviewer subagent to review task breakdown and validate approach before coding
```

### During Implementation (Per Component)

**For each component (telemetry, validation, errors):**

```bash
# 1. Write tests first
> Use the tdd-implementer subagent to create comprehensive tests for [telemetry/validation/errors] before implementation

# 2. Implement feature
> Use the pattern-expert subagent to guide implementation of [feature] following Kailash SDK patterns

# 3. Validate compliance
> Use the gold-standards-validator subagent to ensure [feature] follows absolute imports, error handling, and testing standards

# 4. Review implementation
> Use the intermediate-reviewer subagent to review completed [feature] implementation before moving to next component
```

### Before Submitting PR

```bash
# 1. Validate testing
> Use the testing-specialist subagent to verify 3-tier test coverage for all runtime enhancements

# 2. Test documentation
> Use the documentation-validator subagent to validate that all code examples in runtime docs are accurate

# 3. Pre-commit validation
> Use the git-release-specialist subagent to run pre-commit validation before creating PR

# 4. Final review
> Use the intermediate-reviewer subagent to perform final review of complete runtime enhancements implementation
```

---

## Success Criteria

### Definition of Done

**For each task, ALL must be true:**

1. ✅ **Code complete and tested**
   - Implementation matches specification
   - All edge cases handled
   - No TODOs or FIXMEs remaining

2. ✅ **Tests comprehensive (80%+ coverage)**
   - Tier 1 (unit): Mocked, fast
   - Tier 2 (integration): Real runtime, NO MOCKING
   - Tier 3 (E2E): Complete workflows

3. ✅ **Backward compatibility verified**
   - All existing tests pass
   - Regression suite passes
   - No breaking changes

4. ✅ **Documentation updated**
   - API reference updated
   - CLAUDE.md updated (if applicable)
   - Examples added

5. ✅ **Code review approved**
   - Manual review by tech lead
   - gold-standards-validator passed
   - All PR comments addressed

### Acceptance Criteria

**Telemetry:**
- [ ] TelemetryCollector class implemented
- [ ] LocalRuntime has enable_telemetry parameter
- [ ] AsyncLocalRuntime has enable_telemetry parameter
- [ ] Privacy-first design (opt-in, anonymous)
- [ ] Tests verify telemetry OFF by default
- [ ] Tests verify telemetry works when enabled

**Error Context:**
- [ ] WorkflowExecutionError accepts context parameter
- [ ] _build_error_context() method implemented
- [ ] Pattern matching for 5+ common errors
- [ ] AI-friendly error messages formatted correctly
- [ ] Sensitive data sanitized from errors
- [ ] Tests verify backward compatibility

**ValidatingLocalRuntime:**
- [ ] ValidatingLocalRuntime class created
- [ ] WorkflowValidator class created
- [ ] Validates DataFlow node parameters
- [ ] Catches created_at/updated_at mistakes
- [ ] Catches UpdateNode pattern mistakes
- [ ] strict_mode works (raises vs warns)
- [ ] Tests comprehensive (10+ test cases)

**Performance Tracking:**
- [ ] Per-node timing tracked
- [ ] Slow execution warnings in debug mode
- [ ] Execution history stored
- [ ] Minimal overhead (<1%)
- [ ] Tests verify timing accuracy

---

## Integration Points

### With DataFlow Team

**Dependency:** DataFlow team needs your ValidatingLocalRuntime

**Coordination:**
- Share ValidatingLocalRuntime interface early (Week 9)
- DataFlow team can start testing validation hooks
- Ensure error messages are consistent (same format)

**Meeting:** Week 9, sync on validation interface

### With Templates Team

**Dependency:** Templates will use enhanced error messages

**Coordination:**
- Share error message format (Week 10)
- Templates team documents common errors
- Ensure error messages reference Golden Patterns

**Meeting:** Week 10, review error messages together

### With CLI Team

**Dependency:** CLI needs telemetry for usage tracking

**Coordination:**
- Share telemetry API (Week 11)
- CLI team adds telemetry to kailash create, kailash dev
- Consistent telemetry format

**Meeting:** Week 11, align on telemetry events

---

## Code Examples

### Example 1: Adding Telemetry

```python
# src/kailash/runtime/local.py

class LocalRuntime:
    def __init__(
        self,
        config: Optional[RuntimeConfig] = None,
        enable_telemetry: bool = False  # ← ADD THIS
    ):
        self.config = config or RuntimeConfig()
        self._execution_history = []

        # ADD THIS:
        self._telemetry_enabled = enable_telemetry or os.getenv("KAILASH_TELEMETRY", "false").lower() == "true"
        self._telemetry = TelemetryCollector() if self._telemetry_enabled else None

    def execute(self, workflow: Workflow, inputs: dict = None):
        # ADD THIS (before execution):
        if self._telemetry:
            self._telemetry.track_execution_start(
                workflow_id=workflow.id,
                node_count=len(workflow.nodes),
                timestamp=datetime.now()
            )

        try:
            # ... existing execution logic (UNCHANGED)

            results, run_id = self._execute_workflow(workflow, inputs)

            # ADD THIS (after success):
            if self._telemetry:
                self._telemetry.track_execution_success(
                    workflow_id=workflow.id,
                    run_id=run_id,
                    duration=time.time() - start_time,
                    node_count=len(workflow.nodes)
                )

            return results, run_id

        except Exception as e:
            # ADD THIS (on error):
            if self._telemetry:
                self._telemetry.track_execution_error(
                    workflow_id=workflow.id,
                    error_type=type(e).__name__,
                    error_category=self._categorize_error(e)
                )

            raise  # Re-raise (UNCHANGED)
```

**Note:** Changes are ADDITIVE only. Existing code untouched.

### Example 2: Enhanced Error

```python
# src/kailash/sdk_exceptions.py

class WorkflowExecutionError(Exception):
    def __init__(self, message: str, context: Optional[dict] = None):  # ← ADD context
        super().__init__(message)
        self.context = context or {}  # ← ADD THIS

    def __str__(self):  # ← MODIFY THIS
        if not self.context:
            # Backward compatible: No context, return simple message
            return super().__str__()

        # NEW: Format with context
        parts = [super().__str__()]

        if self.context.get("suggestions"):
            parts.append("\nSuggestions:")
            for suggestion in self.context["suggestions"]:
                parts.append(f"  {suggestion}")

        return "\n".join(parts)
```

---

## Testing Protocol

### Test-First Development (TDD)

**For EVERY change:**

1. **Write test first** (before implementation)
2. **Verify test fails** (red)
3. **Implement feature** (minimum to pass)
4. **Verify test passes** (green)
5. **Refactor** (improve code quality)
6. **Verify test still passes**

### Test Coverage Requirements

**Tier 1 (Unit) - 70%:**
```python
# tests/runtime/test_telemetry.py

def test_telemetry_disabled_by_default():
    """Backward compatibility: telemetry OFF by default."""
    runtime = LocalRuntime()
    assert runtime._telemetry is None

def test_telemetry_enabled_when_requested():
    """Can enable telemetry explicitly."""
    runtime = LocalRuntime(enable_telemetry=True)
    assert runtime._telemetry is not None

def test_telemetry_tracks_execution():
    """Telemetry tracks workflow execution."""
    runtime = LocalRuntime(enable_telemetry=True)
    # ... execute workflow
    # ... verify telemetry file created
```

**Tier 2 (Integration) - 20%:**
```python
# tests/integration/test_runtime_integration.py

def test_enhanced_errors_in_real_execution():
    """Test enhanced errors with real workflow execution."""
    runtime = LocalRuntime()

    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {
        "name": "Alice",
        "created_at": datetime.now().isoformat()  # ← Type error
    })

    with pytest.raises(WorkflowExecutionError) as exc:
        runtime.execute(workflow.build())

    # Verify enhanced error has suggestions
    assert "suggestions" in exc.value.context
    assert "isoformat" in str(exc.value)
```

**Tier 3 (E2E) - 10%:**
```python
# tests/e2e/test_complete_error_flow.py

def test_user_sees_helpful_error_end_to_end():
    """Test complete user experience with error."""
    # Simulate user creating workflow with common mistake
    # Verify they get actionable error message
    # Verify they can fix based on suggestion
```

**NO MOCKING in Tier 2-3 tests!**

---

## Subagent Workflow (Step-by-Step)

### Week 9: Planning and Test Design

**Day 1 (Monday):**
```bash
# Morning: Requirements analysis
> Use the requirements-analyst subagent to break down runtime enhancements into detailed technical requirements with acceptance criteria

# Afternoon: Code navigation
> Use the sdk-navigator subagent to locate all error handling code and telemetry integration points in Core SDK runtime
```

**Day 2 (Tuesday):**
```bash
# Morning: Pattern review
> Use the pattern-expert subagent to identify best practices for adding optional features to existing classes while maintaining backward compatibility

# Afternoon: Task breakdown
> Use the todo-manager subagent to create detailed task breakdown for runtime enhancements with time estimates and dependencies
```

**Day 3 (Wednesday):**
```bash
# Morning: Complexity analysis
> Use the ultrathink-analyst subagent to analyze potential failure points in runtime modifications and telemetry implementation

# Afternoon: Approach validation
> Use the intermediate-reviewer subagent to review task breakdown and validate that approach maintains 100% backward compatibility
```

**Day 4-5 (Thursday-Friday):**
```bash
# Write tests first (entire 2 days)
> Use the tdd-implementer subagent to create comprehensive test suite for telemetry, validation, and error enhancements before any implementation
```

**Week 9 Deliverable:** Complete test suite (failing tests), validated approach

---

### Week 10: Implementation (Telemetry + Errors)

**Day 6 (Monday):**
```bash
# Implement TelemetryCollector
> Use the pattern-expert subagent to guide implementation of TelemetryCollector class following Kailash privacy and security patterns

# Review
> Use the gold-standards-validator subagent to validate TelemetryCollector implementation against security and privacy standards
```

**Day 7 (Tuesday):**
```bash
# Integrate telemetry into LocalRuntime
> Use the pattern-expert subagent to guide integration of telemetry hooks into LocalRuntime.execute() method

# Review
> Use the intermediate-reviewer subagent to review telemetry integration ensuring no performance regression
```

**Day 8 (Wednesday):**
```bash
# Enhance WorkflowExecutionError
> Use the pattern-expert subagent to guide enhancement of WorkflowExecutionError class with context parameter

# Build error context
> Use the pattern-expert subagent to implement _build_error_context() method with pattern matching for common errors
```

**Day 9 (Thursday):**
```bash
# Integrate into AsyncLocalRuntime
> Use the pattern-expert subagent to apply same enhancements to AsyncLocalRuntime ensuring consistency with LocalRuntime

# Review both runtimes
> Use the intermediate-reviewer subagent to review both runtime implementations for consistency and completeness
```

**Day 10 (Friday):**
```bash
# Comprehensive testing
> Use the testing-specialist subagent to verify all Tier 1-3 tests pass and meet coverage requirements

# Validate compliance
> Use the gold-standards-validator subagent to ensure all runtime modifications follow gold standards for error handling and testing
```

**Week 10 Deliverable:** Telemetry and enhanced errors complete, tested

---

### Week 11: Implementation (ValidatingLocalRuntime + Performance)

**Day 11 (Monday):**
```bash
# Implement WorkflowValidator
> Use the pattern-expert subagent to implement WorkflowValidator class with comprehensive validation rules

# Test validation rules
> Use the tdd-implementer subagent to verify all validation tests pass
```

**Day 12 (Tuesday):**
```bash
# Implement ValidatingLocalRuntime
> Use the pattern-expert subagent to implement ValidatingLocalRuntime as subclass of LocalRuntime

# Review inheritance
> Use the intermediate-reviewer subagent to review class hierarchy and ensure proper inheritance patterns
```

**Day 13 (Wednesday):**
```bash
# Add performance tracking
> Use the pattern-expert subagent to implement per-node timing and slow execution warnings

# Test performance impact
> Use the testing-specialist subagent to verify performance tracking has <1% overhead
```

**Day 14 (Thursday):**
```bash
# Integration testing
> Use the testing-specialist subagent to run full integration test suite with real workflows and verify all enhancements work together

# Backward compatibility verification
> Use the gold-standards-validator subagent to run complete backward compatibility test suite
```

**Day 15 (Friday):**
```bash
# Documentation
> Use the documentation-validator subagent to test all code examples in runtime documentation

# Final review
> Use the intermediate-reviewer subagent to perform final review of all runtime enhancements before creating PR
```

**Week 11 Deliverable:** ValidatingLocalRuntime and performance tracking complete

---

### Week 12: Integration and PR

**Day 16-17:**
```bash
# Integration with Quick Mode (coordinate with Templates team)
> Use the pattern-expert subagent to validate that ValidatingLocalRuntime integrates correctly with Quick Mode design

# Cross-team testing
# Work with DataFlow team to test validation with DataFlow nodes
```

**Day 18-19:**
```bash
# Documentation updates
> Use the documentation-validator subagent to update all runtime documentation with new features

# CLAUDE.md updates
# Update sdk-users/docs-developers/reference/ with new runtime features
```

**Day 20:**
```bash
# Create PR
> Use the git-release-specialist subagent to create PR with proper description, tests, and documentation

# Final validation
> Use the intermediate-reviewer subagent to ensure PR is complete and ready for merge
```

**Week 12 Deliverable:** PR ready for review and merge

---

## Code Review Checklist

**Before creating PR, verify:**

### Backward Compatibility
- [ ] All existing tests pass (100%)
- [ ] New parameters have defaults (opt-in)
- [ ] No changes to existing method signatures
- [ ] Deprecation warnings if removing anything (not applicable)

### Code Quality
- [ ] Black formatted
- [ ] Ruff linting passes
- [ ] Type hints on all new code
- [ ] Docstrings on all public methods

### Testing
- [ ] Test coverage ≥80%
- [ ] Tier 1 tests (unit, mocked)
- [ ] Tier 2 tests (integration, real runtime)
- [ ] Tier 3 tests (E2E, complete flows)
- [ ] NO MOCKING in Tier 2-3

### Documentation
- [ ] README updated (if user-facing changes)
- [ ] API reference updated
- [ ] CLAUDE.md updated (if patterns changed)
- [ ] Code examples tested

### Integration
- [ ] ValidatingLocalRuntime interface shared with DataFlow team
- [ ] Telemetry format shared with CLI team
- [ ] Error format shared with Templates team

---

## Common Pitfalls to Avoid

### ❌ Breaking Backward Compatibility

**Wrong:**
```python
def __init__(self, config, enable_telemetry=True):  # ❌ Changes default
```

**Right:**
```python
def __init__(self, config, enable_telemetry=False):  # ✅ Backward compatible
```

### ❌ Modifying Existing Methods

**Wrong:**
```python
def execute(self, workflow, inputs):
    # Rewrite entire method ❌
```

**Right:**
```python
def execute(self, workflow, inputs):
    # ADD hooks to existing code ✅
    if self._telemetry:  # NEW
        self._telemetry.track_start()

    # ... existing code (UNCHANGED) ...
```

### ❌ Exposing Sensitive Data

**Wrong:**
```python
context["parameters"] = params  # ❌ May include passwords, API keys
```

**Right:**
```python
context["parameters"] = self._sanitize_params(params)  # ✅ Remove secrets
```

---

## Questions and Support

### If Blocked or Unsure

**Use subagents for guidance:**
```bash
> Use the sdk-navigator subagent to find similar patterns in existing code

> Use the pattern-expert subagent to recommend best approach for [specific problem]

> Use the gold-standards-validator subagent to validate if approach follows standards
```

**Escalate if:**
- Subagents don't resolve (ask tech lead)
- Backward compatibility concern (discuss with team)
- Cross-team dependency blocked (coordinate meeting)

---

## Success Metrics for Your Work

**Your work is successful if:**
- ✅ 48-hour debugging reduced to 5 minutes (via enhanced errors)
- ✅ Token consumption tracked (enables measurement of Golden Patterns success)
- ✅ Quick Mode validation prevents common errors (user feedback positive)
- ✅ Zero backward compatibility breaks (existing users unaffected)

**Measure by:**
- User feedback: "Error messages helped me fix immediately"
- Telemetry data: Validation catching 80%+ of common errors before execution
- Support tickets: Reduction in "I don't understand this error" tickets

---

## Timeline Summary

**Week 9:** Planning, test design (40 hours)
**Week 10:** Telemetry + Errors implementation (40 hours)
**Week 11:** Validation + Performance implementation (40 hours)
**Week 12:** Integration, documentation, PR (40 hours)

**Total: 160 hours over 4 weeks** (2 developers at 20 hours/week each)

OR **80 hours over 4 weeks** (1 developer full-time)

---

**You are building the foundation for better developer experience. Your work will save users hundreds of hours of debugging. Make it excellent.**
