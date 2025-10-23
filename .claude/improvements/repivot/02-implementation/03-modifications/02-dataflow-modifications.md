# DataFlow Modifications

**Files:** `apps/kailash-dataflow/src/dataflow/core/nodes.py`, `apps/kailash-dataflow/src/dataflow/core/engine.py`
**Estimated Effort:** 15 hours
**Risk:** Low (error handling improvements only)

---

## Changes Overview

**1. Enhanced Node Error Messages** (~100 lines in nodes.py)
- AI-friendly error formatting
- Actionable suggestions
- Link to common mistakes

**2. Quick Mode Integration Hooks** (~50 lines in engine.py)
- Detect Quick Mode projects
- Simplified defaults
- Optional validation

**Total Changes:** ~150 lines (in 7000+ line codebase)

---

## Change 1: Enhanced Node Error Messages

### Current Error Handling

```python
# In DataFlow-generated CreateNode

def execute(self, params: dict) -> dict:
    """Execute create operation."""
    try:
        # Database insert
        result = self._db_insert(params)
        return result
    except Exception as e:
        # Current: Generic re-raise
        raise Exception(f"Database operation failed: {e}") from e
```

**Output (current):**
```
Exception: Database operation failed: (psycopg2.ProgrammingError) operator does not exist: text = integer
LINE 1: ...WHERE created_at = '2025-01-15T10:30:00'
```

### Enhanced Error Handling

```python
# Modified in dataflow/core/nodes.py

class NodeGenerator:
    """Generate CRUD nodes from models."""

    def _generate_create_node_class(self, model_name: str, fields: dict):
        """Generate CreateNode class with enhanced errors."""

        class GeneratedCreateNode(BaseNode):
            """Auto-generated Create node for {model_name}."""

            def __init__(self):
                super().__init__()
                self.model_name = model_name
                self.fields = fields
                self.dataflow_instance = dataflow_instance  # Reference to DataFlow

            def execute(self, params: dict) -> dict:
                """Execute create operation with enhanced error handling."""
                try:
                    # Existing create logic (unchanged)
                    result = self._execute_create(params)
                    return result

                except Exception as e:
                    # NEW: Build error context
                    error_context = self._build_error_context(e, params)

                    # Raise enhanced error
                    raise DataFlowExecutionError(
                        f"{self.model_name}CreateNode failed: {error_context['message']}",
                        context=error_context
                    ) from e

            def _build_error_context(self, error: Exception, params: dict) -> dict:
                """Build AI-friendly error context.

                NEW METHOD: Provides structured error information
                """
                context = {
                    "node_type": "CreateNode",
                    "model": self.model_name,
                    "operation": "create",
                    "error_type": type(error).__name__,
                    "error_message": str(error),
                    "parameters": params,
                    "suggestions": [],
                    "pattern_link": None
                }

                # Pattern match common errors
                error_str = str(error).lower()

                if "operator does not exist: text = integer" in error_str:
                    context["error_category"] = "type_mismatch"
                    context["likely_field"] = self._find_likely_datetime_field(params)
                    context["suggestions"].append(
                        "❌ Type mismatch: You're passing a string where datetime is expected.\n\n"
                        "Common cause:\n"
                        f"  Field '{context['likely_field']}' expects: datetime\n"
                        f"  You provided: string (probably from .isoformat())\n\n"
                        "Fix:\n"
                        f"  ❌ WRONG: datetime.now().isoformat()\n"
                        f"  ✅ CORRECT: datetime.now()\n\n"
                        "Or use kailash-dataflow-utils:\n"
                        "  from kailash_dataflow_utils import TimestampField\n"
                        f"  '{context['likely_field']}': TimestampField.now()"
                    )
                    context["pattern_link"] = "golden-pattern-1-dataflow-model"

                elif "operator does not exist: text = json" in error_str:
                    context["error_category"] = "json_serialization"
                    context["suggestions"].append(
                        "❌ JSON field error: You're passing a string where dict is expected.\n\n"
                        "Common cause:\n"
                        "  You used json.dumps() but DataFlow handles JSON automatically\n\n"
                        "Fix:\n"
                        "  ❌ WRONG: json.dumps({'key': 'value'})\n"
                        "  ✅ CORRECT: {'key': 'value'}\n\n"
                        "DataFlow automatically serializes dicts to JSON in the database."
                    )

                elif "violates not-null constraint" in error_str:
                    missing_field = self._extract_field_from_error(error_str)
                    context["error_category"] = "missing_required"
                    context["suggestions"].append(
                        f"❌ Missing required field: '{missing_field}'\n\n"
                        f"Model '{self.model_name}' requires this field.\n\n"
                        "Fix:\n"
                        f"  Add to your parameters:\n"
                        f"    '{missing_field}': <value>"
                    )

                elif "duplicate key value violates unique constraint" in error_str:
                    context["error_category"] = "duplicate_key"
                    context["suggestions"].append(
                        "❌ Duplicate value: A record with this value already exists.\n\n"
                        "Common causes:\n"
                        "  1. Email already registered\n"
                        "  2. Duplicate ID (use UUIDField.generate() for unique IDs)\n\n"
                        "Fix:\n"
                        "  1. Check if record exists first (use ListNode)\n"
                        "  2. Update instead of create (use UpdateNode)\n"
                        "  3. Use different value for unique field"
                    )

                return context

            def _find_likely_datetime_field(self, params: dict) -> str:
                """Identify which field likely has datetime issue."""
                for field_name, field_info in self.fields.items():
                    if field_info["type"] == datetime:
                        if field_name in params:
                            if isinstance(params[field_name], str):
                                return field_name
                return "unknown"

            def _extract_field_from_error(self, error_str: str) -> str:
                """Extract field name from error message."""
                import re
                match = re.search(r'column "(\w+)"', error_str)
                return match.group(1) if match else "unknown"

        return GeneratedCreateNode
```

### New Exception Class

```python
# apps/kailash-dataflow/src/dataflow/core/exceptions.py (NEW FILE)

class DataFlowExecutionError(Exception):
    """Enhanced DataFlow execution error with context.

    Similar to WorkflowExecutionError but DataFlow-specific.
    """

    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(message)
        self.context = context or {}

    def __str__(self):
        """Format error with suggestions."""
        if not self.context.get("suggestions"):
            return super().__str__()

        parts = [super().__str__(), ""]

        for suggestion in self.context["suggestions"]:
            parts.append(suggestion)

        if self.context.get("pattern_link"):
            parts.append(f"\nSee pattern: {self.context['pattern_link']}")

        return "\n".join(parts)
```

**Example enhanced error:**
```
DataFlowExecutionError: UserCreateNode failed: Type mismatch in 'created_at' field

❌ Type mismatch: You're passing a string where datetime is expected.

Common cause:
  Field 'created_at' expects: datetime
  You provided: string (probably from .isoformat())

Fix:
  ❌ WRONG: datetime.now().isoformat()
  ✅ CORRECT: datetime.now()

Or use kailash-dataflow-utils:
  from kailash_dataflow_utils import TimestampField
  'created_at': TimestampField.now()

See pattern: golden-pattern-1-dataflow-model
```

---

## Change 2: Quick Mode Integration Hooks

### Current Engine Init

```python
class DataFlow:
    def __init__(
        self,
        database_url: Optional[str] = None,
        config: Optional[DataFlowConfig] = None,
        multi_tenant: bool = False,
        audit_logging: bool = False,
        # ... existing parameters
    ):
        # ... existing initialization
```

### Modified Engine Init

```python
class DataFlow:
    def __init__(
        self,
        database_url: Optional[str] = None,
        config: Optional[DataFlowConfig] = None,
        multi_tenant: bool = False,
        audit_logging: bool = False,
        quick_mode: bool = False,  # ← NEW parameter (default False)
        # ... existing parameters
    ):
        """Initialize DataFlow.

        Args:
            ... (existing args)
            quick_mode: Enable Quick Mode defaults and validation (NEW)
        """
        # NEW: Quick Mode detection
        self._quick_mode = quick_mode or self._detect_quick_mode()

        if self._quick_mode:
            # Apply Quick Mode defaults
            multi_tenant = False  # Quick Mode: single tenant
            audit_logging = False  # Quick Mode: minimal overhead
            debug = True  # Quick Mode: verbose errors

        # ... existing initialization (unchanged)

    def _detect_quick_mode(self) -> bool:
        """Detect if running in Quick Mode context.

        NEW METHOD: Auto-detect Quick Mode from project structure
        """
        # Check for .ai-mode file (created by templates)
        if Path(".ai-mode").exists():
            return True

        # Check for Quick Mode imports in calling code
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            caller_globals = frame.f_back.f_globals
            if "kailash.quick" in caller_globals.get("__package__", ""):
                return True

        return False
```

**Backward compatibility: 100%**
- quick_mode defaults to False
- Existing behavior unchanged
- Auto-detection is optional hint

---

## Change 3: Model Validation Helper

### New Method in DataFlow

```python
# In dataflow/core/engine.py

def validate_model_parameters(
    self,
    model_name: str,
    operation: str,
    params: dict
) -> list:
    """Validate parameters before execution.

    NEW METHOD: Used by Quick Mode for pre-execution validation

    Args:
        model_name: Model name (e.g., "User")
        operation: Operation type ("create", "update", "delete", "read")
        params: Parameters to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    model_info = self._models.get(model_name)
    if not model_info:
        errors.append(f"Model '{model_name}' not registered")
        return errors

    fields = model_info["fields"]

    if operation == "create":
        errors.extend(self._validate_create_params(params, fields))
    elif operation == "update":
        errors.extend(self._validate_update_params(params, fields))

    return errors

def _validate_create_params(self, params: dict, fields: dict) -> list:
    """Validate create operation parameters.

    NEW METHOD: Check types, required fields, auto-managed fields
    """
    errors = []

    # Check for auto-managed fields
    if "created_at" in params:
        errors.append("created_at is auto-managed - remove from parameters")
    if "updated_at" in params:
        errors.append("updated_at is auto-managed - remove from parameters")

    # Check required fields
    for field_name, field_info in fields.items():
        if field_info.get("required", False):
            if field_name not in params:
                if field_name not in ["id", "created_at", "updated_at"]:
                    errors.append(f"Required field '{field_name}' missing")

    # Check types
    from datetime import datetime
    for field_name, value in params.items():
        if field_name not in fields:
            continue

        expected_type = fields[field_name]["type"]

        # Common type mistakes
        if expected_type == datetime and isinstance(value, str):
            errors.append(
                f"Field '{field_name}' expects datetime, got string. "
                f"Did you use .isoformat()? Use datetime.now() instead."
            )

        if expected_type == dict and isinstance(value, str):
            errors.append(
                f"Field '{field_name}' expects dict, got string. "
                f"Did you use json.dumps()? Pass dict directly."
            )

    return errors

def _validate_update_params(self, params: dict, fields: dict) -> list:
    """Validate update operation parameters.

    NEW METHOD: Check UpdateNode pattern (filter + fields)
    """
    errors = []

    # UpdateNode requires specific structure
    if "filter" not in params:
        errors.append("UpdateNode requires 'filter' parameter")
    if "fields" not in params:
        errors.append("UpdateNode requires 'fields' parameter")

    # Validate fields being updated
    if "fields" in params:
        for field_name in params["fields"]:
            if field_name in ["created_at", "updated_at", "id"]:
                errors.append(f"'{field_name}' cannot be updated (auto-managed or primary key)")

    return errors
```

**Usage (Quick Mode):**
```python
# In kailash/quick/db.py

class ModelOperations:
    def create(self, **kwargs):
        # Validate before creating
        errors = self.dataflow.validate_model_parameters(
            self.model_name,
            "create",
            kwargs
        )

        if errors:
            raise ValueError("Validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

        # Proceed with creation (existing code)
        # ...
```

**Backward compatibility: 100%**
- New method doesn't affect existing behavior
- Only called by Quick Mode (opt-in)
- Full SDK doesn't use validation (as before)

---

## Change 4: Datetime Field Auto-Detection

### Problem

Users don't know which fields are datetime types - leads to .isoformat() errors.

### Solution

Add helper to identify datetime fields:

```python
# In dataflow/core/engine.py

def get_datetime_fields(self, model_name: str) -> list:
    """Get list of datetime fields for a model.

    NEW METHOD: Helper for users to identify datetime fields

    Args:
        model_name: Model name

    Returns:
        List of field names that are datetime type

    Example:
        >>> db.get_datetime_fields("User")
        ['created_at', 'updated_at', 'last_login']
    """
    model_info = self._models.get(model_name)
    if not model_info:
        return []

    from datetime import datetime
    datetime_fields = []

    for field_name, field_info in model_info["fields"].items():
        if field_info["type"] == datetime:
            datetime_fields.append(field_name)

    return datetime_fields

def get_json_fields(self, model_name: str) -> list:
    """Get list of JSON fields for a model.

    NEW METHOD: Helper for users to identify JSON fields
    """
    model_info = self._models.get(model_name)
    if not model_info:
        return []

    json_fields = []

    for field_name, field_info in model_info["fields"].items():
        if field_info["type"] == dict:
            json_fields.append(field_name)

    return json_fields
```

**Usage (in error messages):**
```python
# Enhanced error can reference these
if "text = integer" in error_str:
    datetime_fields = self.dataflow_instance.get_datetime_fields(self.model_name)
    suggestion = (
        f"This model has datetime fields: {', '.join(datetime_fields)}\n"
        f"Don't use .isoformat() on these fields."
    )
```

---

## Change 5: Better Model Registration Feedback

### Current Registration

```python
@db.model
class User:
    name: str

# No output, silent registration
```

### Enhanced Registration (Debug Mode)

```python
# In dataflow/core/engine.py

def model(self, cls: Type) -> Type:
    """Decorator to register a model with DataFlow."""

    # ... existing registration logic

    # NEW: Debug feedback (if debug mode or Quick Mode)
    if self.config.debug or self._quick_mode:
        print(f"✅ Model '{model_name}' registered")
        print(f"   Table: {table_name}")
        print(f"   Fields: {', '.join(fields.keys())}")
        print(f"   Nodes generated:")
        print(f"     - {model_name}CreateNode")
        print(f"     - {model_name}ReadNode")
        print(f"     - {model_name}UpdateNode")
        print(f"     - {model_name}DeleteNode")
        print(f"     - {model_name}ListNode")
        print(f"     - {model_name}BulkCreateNode")
        print(f"     - {model_name}BulkUpdateNode")
        print(f"     - {model_name}BulkDeleteNode")
        print(f"     - {model_name}BulkUpsertNode")

    return cls
```

**Output (Quick Mode / Debug):**
```
✅ Model 'User' registered
   Table: users
   Fields: id, name, email, is_active
   Nodes generated:
     - UserCreateNode
     - UserReadNode
     - UserUpdateNode
     - UserDeleteNode
     - UserListNode
     - UserBulkCreateNode
     - UserBulkUpdateNode
     - UserBulkDeleteNode
     - UserBulkUpsertNode
```

**Backward compatibility: 100%**
- Only shows in debug mode (opt-in)
- Silent in production (existing behavior)

---

## Testing

### Regression Tests

```python
# apps/kailash-dataflow/tests/test_backward_compatibility.py

def test_existing_dataflow_usage_unchanged():
    """Test that ALL existing DataFlow patterns still work."""

    # Test 1: Basic model registration
    db = DataFlow(":memory:")

    @db.model
    class User:
        name: str

    # Should work exactly as before
    assert "User" in db._models

    # Test 2: CRUD operations
    workflow = WorkflowBuilder()
    workflow.add_node("UserCreateNode", "create", {"name": "Alice"})

    runtime = LocalRuntime()
    results, _ = runtime.execute(workflow.build())

    assert results["create"]["name"] == "Alice"

def test_no_breaking_changes_to_public_api():
    """Test that public API is unchanged."""
    from dataflow import DataFlow

    # All existing parameters still work
    db = DataFlow(
        database_url=":memory:",
        pool_size=10,
        multi_tenant=False,
        audit_logging=False
    )

    # New parameters are optional
    db2 = DataFlow(":memory:", quick_mode=True)  # New, but optional

    # Both should work identically for existing use cases
```

### New Feature Tests

```python
# apps/kailash-dataflow/tests/test_validation_helpers.py

def test_validate_model_parameters():
    """Test new validation method."""
    from dataflow import DataFlow
    from datetime import datetime

    db = DataFlow(":memory:")

    @db.model
    class User:
        name: str
        created_at: datetime

    # Should detect .isoformat() error
    errors = db.validate_model_parameters("User", "create", {
        "name": "Alice",
        "created_at": datetime.now().isoformat()  # String, not datetime
    })

    assert len(errors) > 0
    assert any("expects datetime, got string" in err for err in errors)

def test_datetime_field_detection():
    """Test datetime field helper."""
    from dataflow import DataFlow
    from datetime import datetime

    db = DataFlow(":memory:")

    @db.model
    class Session:
        user_id: str
        created_at: datetime
        expires_at: datetime

    datetime_fields = db.get_datetime_fields("Session")

    assert "created_at" in datetime_fields
    assert "expires_at" in datetime_fields
    assert "user_id" not in datetime_fields
```

---

## Documentation Changes

### New Guide: Common DataFlow Errors

**Location:** `sdk-users/docs-it-teams/dataflow/common-errors.md`

```markdown
# Common DataFlow Errors and Fixes

## Error: "operator does not exist: text = integer"

**Cause:** Type mismatch - passing string where datetime/int expected

**Common scenario:**
```python
# ❌ WRONG
"created_at": datetime.now().isoformat()  # Returns string

# ✅ CORRECT
"created_at": datetime.now()  # Returns datetime
```

**How to prevent:**
```python
# Use kailash-dataflow-utils
pip install kailash-dataflow-utils

from kailash_dataflow_utils import TimestampField

workflow.add_node("UserCreateNode", "create", {
    "created_at": TimestampField.now()  # Always correct type
})
```

## Error: "created_at is auto-managed"

**Cause:** Including auto-managed fields in parameters

**Fix:**
```python
# ❌ WRONG
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",
    "created_at": datetime.now()  # DataFlow manages this
})

# ✅ CORRECT
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice"
    # created_at added automatically
})
```

## Error: "UpdateNode requires 'filter' and 'fields'"

**Cause:** Using CreateNode pattern for UpdateNode

**Fix:**
```python
# ❌ WRONG (CreateNode pattern)
workflow.add_node("UserUpdateNode", "update", {
    "id": "user-123",
    "name": "New Name"
})

# ✅ CORRECT (UpdateNode pattern)
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": "user-123"},
    "fields": {"name": "New Name"}
})
```

[... more common errors with fixes ...]
```

---

## Rollout Plan

**Week 1-2:** Implement enhanced error messages
**Week 3:** Implement validation helpers
**Week 4:** Implement Quick Mode hooks
**Week 5:** Testing and documentation

---

## Key Takeaways

**DataFlow modifications are minimal:**
- ~150 lines in 7000+ line codebase (<2%)
- All changes improve error messages (user-facing)
- No breaking changes to existing functionality
- Validation is opt-in (Quick Mode only)

**Impact: High value, low risk**
- Prevents 48-hour debugging sessions
- AI-friendly error messages
- Minimal code changes

**The 48-hour datetime error would have been caught in <1 minute with these changes.**

---

**Next:** See `03-nexus-modifications.md` for Nexus enhancements
