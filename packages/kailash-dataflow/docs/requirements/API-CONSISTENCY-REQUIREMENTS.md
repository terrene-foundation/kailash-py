# DataFlow API Consistency Requirements

**Document Version**: 1.0
**Date**: 2025-10-21
**Status**: Proposed
**Related ADR**: [ADR-002: DataFlow API Consistency Redesign](../../adr/ADR-002-dataflow-api-consistency-redesign.md)

---

## Executive Summary

### Problem
DataFlow's auto-generated CRUD nodes have severe API inconsistencies causing 4+ hours of debugging time, poor developer experience, and high support burden.

### Solution
Phased migration strategy:
- **Phase 1** (Week 1): Enhanced validation and documentation
- **Phase 2** (Weeks 2-3): Builder pattern API
- **Phase 3** (Months 2-3): Unified API v2.0

### Success Criteria
- Time to first CRUD success: <30 minutes (Phase 1), <15 minutes (Phase 2), <5 minutes (Phase 3)
- Developer satisfaction: >8/10
- Support tickets: -70% reduction
- API pattern confusion: <10% of developers

---

## 1. Functional Requirements

### FR1: API Consistency

**Priority**: CRITICAL
**Complexity**: HIGH
**Risk Level**: MEDIUM

#### FR1.1: Consistent Parameter Patterns Across CRUD Operations

**Description**: All CRUD operations (Create, Read, Update, Delete, List, Bulk) must follow a unified parameter structure that is predictable and discoverable.

**Current State**:
```python
# CreateNode - Flat structure (17+ parameters)
workflow.add_node("UserCreateNode", "create", {
    "name": "Alice",           # Direct field
    "email": "alice@example.com",
    "age": 30,
    "tenant_id": "tenant_123",
    "return_ids": True
})

# UpdateNode - Nested structure (2 parameters)
workflow.add_node("UserUpdateNode", "update", {
    "conditions": {"id": 1},    # Nested filter
    "updates": {                # Nested updates
        "name": "Alice Updated",
        "age": 31
    }
})

# BulkUpdateNode - Hybrid structure (different naming)
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "filter": {"active": True},      # Different from "conditions"
    "update_fields": {               # Different from "updates"
        "status": "verified"
    }
})
```

**Required Behavior** (Phase 3):
```python
# ALL operations follow consistent structure
workflow.add_node("UserCreateNode", "create", {
    "fields": {"name": "Alice", "email": "alice@example.com"},
    "options": {"return_fields": ["id", "created_at"]}
})

workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},           # Consistent naming
    "fields": {"name": "Updated"},  # Consistent naming
    "options": {"return_fields": ["id", "updated_at"]}
})

workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "filter": {"active": True},    # Same as UpdateNode
    "fields": {"status": "verified"},  # Same as UpdateNode
    "options": {"batch_size": 1000}
})
```

**Acceptance Criteria**:
- [ ] All 9 generated nodes use same top-level parameter names
- [ ] Filter/where conditions use identical syntax across all nodes
- [ ] Field updates use identical syntax across all nodes
- [ ] Options/metadata separated from data parameters
- [ ] Backward compatibility maintained via adapter layer
- [ ] Performance within 5% of current implementation

**User Journey**:
1. Developer learns CreateNode parameter pattern
2. Applies same pattern to UpdateNode → succeeds immediately
3. Scales to BulkUpdateNode → same pattern works
4. Time to success: <5 minutes instead of 4+ hours

#### FR1.2: Consistent Filter Syntax

**Description**: MongoDB-style filter operators must work identically across List, Update, BulkUpdate, Delete, and BulkDelete operations.

**Current State**:
```python
# ListNode - Full operator support
{"age": {"$gte": 18, "$lte": 65}}

# UpdateNode - Limited operator support, undocumented
{"conditions": {"age": {"$gte": 18}}}  # May or may not work

# BulkUpdateNode - Different implementation
{"filter": {"age": {"$gte": 18}}}  # Different parameter name
```

**Required Behavior**:
```python
# ALL operations support identical filter syntax
FILTER_OPERATORS = [
    "$eq", "$ne",           # Equality
    "$gt", "$gte", "$lt", "$lte",  # Comparison
    "$in", "$nin",          # Membership
    "$regex", "$like",      # Pattern matching
    "$exists", "$null",     # Existence
    "$and", "$or", "$not"   # Logical
]

# Example: Same filter works everywhere
age_filter = {"age": {"$gte": 18, "$lte": 65}}

workflow.add_node("UserListNode", "list", {"filter": age_filter})
workflow.add_node("UserUpdateNode", "update", {"filter": age_filter, ...})
workflow.add_node("UserBulkUpdateNode", "bulk_update", {"filter": age_filter, ...})
workflow.add_node("UserDeleteNode", "delete", {"filter": age_filter})
```

**Acceptance Criteria**:
- [ ] All 15 operators work identically across all operations
- [ ] Validation errors are consistent across operations
- [ ] Performance within 10% across operations
- [ ] Documentation shows operator support matrix
- [ ] Examples demonstrate cross-operation filter reuse

**Edge Cases**:
- Empty filters: `{}` (should update ALL records with confirmation)
- Invalid operators: `{"age": {"$invalid": 10}}` (clear error message)
- Type mismatches: `{"age": {"$gte": "eighteen"}}` (type coercion or error)

#### FR1.3: Consistent Update Operator Syntax

**Description**: MongoDB-style update operators (`$set`, `$inc`, `$mul`, etc.) must work identically across Update and BulkUpdate operations.

**Current State**:
```python
# UpdateNode - Operators work but undocumented
workflow.add_node("UserUpdateNode", "update", {
    "conditions": {"id": 1},
    "updates": {
        "age": {"$inc": 1},  # Works but not in docs
        "name": {"$set": "Alice"}
    }
})

# BulkUpdateNode - Different parameter structure
workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "filter": {"active": True},
    "update_fields": {  # Different from "updates"
        "age": {"$inc": 1}
    }
})
```

**Required Behavior**:
```python
UPDATE_OPERATORS = [
    "$set",         # Set field value
    "$inc",         # Increment numeric field
    "$dec",         # Decrement numeric field
    "$mul",         # Multiply numeric field
    "$append",      # Append to array
    "$remove",      # Remove from array
    "$concat"       # String concatenation
]

# Example: Same operators work everywhere
update_ops = {
    "login_count": {"$inc": 1},
    "last_login": {"$set": datetime.now()},
    "reputation": {"$mul": 1.1}
}

workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},
    "fields": update_ops  # Consistent naming
})

workflow.add_node("UserBulkUpdateNode", "bulk_update", {
    "filter": {"active": True},
    "fields": update_ops  # Identical structure
})
```

**Acceptance Criteria**:
- [ ] All 7 update operators supported in both Update and BulkUpdate
- [ ] Operator validation messages are identical
- [ ] Type checking works for all operators
- [ ] Documentation includes complete operator reference
- [ ] Examples show operator composition

**Validation Rules**:
- `$inc`, `$dec`, `$mul`: Only numeric fields
- `$append`, `$remove`: Only array fields (or JSON arrays)
- `$concat`: Only string fields
- `$set`: Any field type

---

### FR2: Validation & Error Handling

**Priority**: CRITICAL
**Complexity**: MEDIUM
**Risk Level**: LOW

#### FR2.1: Detect and Prevent Common Mistakes

**Description**: The system must detect common parameter structure mistakes and provide actionable error messages with suggested fixes.

**Common Mistakes**:

1. **Flat parameters in UpdateNode**:
   ```python
   # MISTAKE: Flat structure like CreateNode
   workflow.add_node("UserUpdateNode", "update", {
       "id": 1,
       "name": "Alice Updated",
       "age": 31
   })

   # REQUIRED ERROR MESSAGE:
   """
   NodeValidationError: UpdateNode requires 'filter' and 'fields' parameters.

   You provided flat field parameters: id, name, age

   Did you mean this?
       {
           "filter": {"id": 1},
           "fields": {"name": "Alice Updated", "age": 31}
       }

   See: https://docs.kailash.ai/dataflow/update-patterns#nested-structure
   """
   ```

2. **Missing filter/conditions**:
   ```python
   # MISTAKE: Only updates, no filter
   workflow.add_node("UserUpdateNode", "update", {
       "fields": {"name": "Alice"}
   })

   # REQUIRED ERROR MESSAGE:
   """
   NodeValidationError: UpdateNode requires 'filter' parameter to specify which records to update.

   Safety check: Updates without filters affect ALL records in the table.

   Add a filter:
       {"filter": {"id": 1}, "fields": {"name": "Alice"}}

   Or explicitly update all records:
       {"filter": {}, "fields": {"name": "Alice"}, "confirm_all": True}

   See: https://docs.kailash.ai/dataflow/update-patterns#safety
   """
   ```

3. **Wrong parameter names**:
   ```python
   # MISTAKE: Using CreateNode syntax
   workflow.add_node("UserUpdateNode", "update", {
       "conditions": {"id": 1},  # Old v0.5 parameter
       "updates": {"name": "Alice"}
   })

   # REQUIRED WARNING MESSAGE:
   """
   DeprecationWarning: Parameter 'conditions' is deprecated in v0.6+.

   Use 'filter' instead:
       {"filter": {"id": 1}, ...}

   The old 'conditions' parameter still works but will be removed in v2.0.

   Migration guide: https://docs.kailash.ai/dataflow/migration/v0.6
   """
   ```

**Acceptance Criteria**:
- [ ] 100% of common mistakes detected with <1ms validation overhead
- [ ] Error messages include example corrected code
- [ ] Error messages link to relevant documentation
- [ ] Validation suggests most likely intended pattern
- [ ] Deprecation warnings don't break code execution

**Success Metrics**:
- Time from error to fix: <1 minute
- Error message satisfaction: >9/10
- Repeat mistakes: <5%

#### FR2.2: Progressive Disclosure of Advanced Features

**Description**: Basic operations should be simple, with advanced features discoverable through documentation and error messages.

**Simple Use Case** (80% of usage):
```python
# Basic update - simple and obvious
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},
    "fields": {"name": "Alice Updated"}
})
```

**Advanced Use Case** (15% of usage):
```python
# Advanced update with operators - discovered through docs
workflow.add_node("UserUpdateNode", "update", {
    "filter": {"id": 1},
    "fields": {
        "login_count": {"$inc": 1},  # Operator discovered in docs
        "last_login": {"$set": datetime.now()}
    },
    "options": {
        "return_fields": ["id", "login_count", "last_login"]
    }
})
```

**Expert Use Case** (5% of usage):
```python
# Expert update with version control and multi-tenant
workflow.add_node("UserUpdateNode", "update", {
    "filter": {
        "id": 1,
        "tenant_id": "tenant_123",
        "version": 5  # Optimistic locking
    },
    "fields": {
        "status": "verified",
        "version": {"$inc": 1}
    },
    "options": {
        "return_fields": ["id", "version", "updated_at"],
        "validate_version": True,
        "rollback_on_conflict": True
    }
})
```

**Acceptance Criteria**:
- [ ] Simple case requires <3 parameters
- [ ] Advanced features documented with examples
- [ ] Error messages suggest simpler alternatives when over-complex
- [ ] Documentation shows progression from simple → advanced
- [ ] Each complexity level has 3+ examples

**Validation Messages**:
```python
# Over-complex for simple use case
if using_operators and all_fields_use_$set:
    warning("""
        You're using $set operators for all fields.
        Consider simplifying:
            {"fields": {"name": "Alice", "age": 31}}
        instead of:
            {"fields": {"name": {"$set": "Alice"}, "age": {"$set": 31}}}
    """)
```

#### FR2.3: Type-Safe Parameter Validation

**Description**: All parameters must be type-checked with clear error messages for type mismatches.

**Type Validation Examples**:

```python
# MISTAKE: Wrong parameter type
workflow.add_node("UserUpdateNode", "update", {
    "filter": "id=1",  # String instead of dict
    "fields": {"name": "Alice"}
})

# REQUIRED ERROR MESSAGE:
"""
NodeValidationError: Parameter 'filter' must be a dictionary, got string.

You provided: "id=1"

Did you mean:
    {"filter": {"id": 1}}

Valid filter syntax:
    - Simple: {"id": 1, "active": True}
    - Operators: {"age": {"$gte": 18}}
    - Logical: {"$and": [{"active": True}, {"age": {"$gte": 18}}]}

See: https://docs.kailash.ai/dataflow/filters
"""
```

**Type Coercion Policy**:

| Parameter | Expected Type | Coercion Rules | Example |
|-----------|--------------|----------------|---------|
| `filter` | `dict` | No coercion, strict validation | `{"id": 1}` |
| `fields` | `dict` | No coercion, strict validation | `{"name": "Alice"}` |
| `options` | `dict` | Optional, defaults to `{}` | `{"return_fields": [...]}` |
| Field values | Model type | Coerce if unambiguous | `"123"` → `123` for int field |
| `return_fields` | `list[str]` | Coerce from string | `"id,name"` → `["id", "name"]` |

**Acceptance Criteria**:
- [ ] All parameters have explicit type requirements
- [ ] Type errors include example of correct type
- [ ] Coercion policy documented for each parameter
- [ ] Type hints enable IDE autocomplete
- [ ] Runtime type validation <1ms overhead

---

### FR3: Error Messages & Guidance

**Priority**: HIGH
**Complexity**: LOW
**Risk Level**: LOW

#### FR3.1: Actionable Error Messages

**Description**: Every error message must provide the next action the developer should take.

**Error Message Template**:
```
{ErrorType}: {What went wrong}

{What was provided}

{Suggested fix with code example}

{Link to documentation}
```

**Examples**:

1. **Missing Required Parameter**:
   ```
   NodeValidationError: Required parameter 'filter' missing in UpdateNode.

   You provided: {"fields": {"name": "Alice"}}

   Add a filter to specify which records to update:
       {
           "filter": {"id": 1},
           "fields": {"name": "Alice"}
       }

   For bulk updates, use BulkUpdateNode instead:
       https://docs.kailash.ai/dataflow/bulk-operations
   ```

2. **Invalid Operator**:
   ```
   NodeValidationError: Invalid update operator '$invalid' in field 'age'.

   Valid operators: $set, $inc, $dec, $mul, $append, $remove, $concat

   Did you mean one of these?
       - $inc (increment): {"age": {"$inc": 1}}
       - $set (set value): {"age": {"$set": 31}}

   See operator reference: https://docs.kailash.ai/dataflow/operators
   ```

3. **Type Mismatch**:
   ```
   NodeValidationError: Type mismatch for field 'age'.

   Expected: int
   Received: "thirty-one" (str)

   Fix the type:
       {"age": 31}  # Use integer, not string

   See field types: https://docs.kailash.ai/dataflow/models#user-fields
   ```

**Acceptance Criteria**:
- [ ] 100% of errors include suggested fix
- [ ] 90%+ of errors include code example
- [ ] All errors link to relevant documentation
- [ ] Error messages tested with real users (>8/10 clarity)
- [ ] Errors suggest most likely intended action

#### FR3.2: Warning Messages for Suboptimal Patterns

**Description**: System should warn (not error) for suboptimal but valid patterns.

**Warning Scenarios**:

1. **Updating all records without confirmation**:
   ```python
   workflow.add_node("UserUpdateNode", "update", {
       "filter": {},  # Empty filter = ALL records
       "fields": {"status": "verified"}
   })

   # WARNING MESSAGE:
   """
   SafetyWarning: Empty filter will update ALL records in 'users' table.

   If this is intentional, add confirmation:
       {"filter": {}, "fields": {...}, "confirm_all": True}

   To update specific records, add filter conditions:
       {"filter": {"active": True}, "fields": {...}}
   """
   ```

2. **Using Update instead of BulkUpdate**:
   ```python
   # User calls UpdateNode in a loop for 1000 records
   for record in records:  # 1000 iterations
       workflow.add_node("UserUpdateNode", f"update_{record.id}", {
           "filter": {"id": record.id},
           "fields": {"status": "processed"}
       })

   # WARNING MESSAGE:
   """
   PerformanceWarning: Detected 1000+ UpdateNode operations in single workflow.

   Use BulkUpdateNode for better performance:
       {
           "filter": {"id": {"$in": [record_ids]}},
           "fields": {"status": "processed"}
       }

   Expected improvement: ~100x faster (1000ms → 10ms)

   See: https://docs.kailash.ai/dataflow/performance#bulk-operations
   """
   ```

3. **Deprecated parameter usage**:
   ```python
   workflow.add_node("UserUpdateNode", "update", {
       "conditions": {"id": 1},  # Deprecated in v0.6
       "updates": {"name": "Alice"}
   })

   # WARNING MESSAGE:
   """
   DeprecationWarning: Parameters 'conditions' and 'updates' deprecated in v0.6.

   Use 'filter' and 'fields' instead:
       {
           "filter": {"id": 1},
           "fields": {"name": "Alice"}
       }

   Deprecated parameters will be removed in v2.0 (estimated Q2 2026).

   Migration guide: https://docs.kailash.ai/dataflow/migration/v0.6-v2.0
   """
   ```

**Acceptance Criteria**:
- [ ] Warnings don't prevent execution
- [ ] Warnings logged but not raised as exceptions
- [ ] Warnings can be suppressed with configuration
- [ ] Warning messages suggest better approach
- [ ] Performance warnings include estimated improvement

#### FR3.3: Documentation Linkage

**Description**: Every error and warning must link to relevant, specific documentation.

**Documentation Structure**:
```
/docs/dataflow/
├── api-reference/
│   ├── create-node.md
│   ├── update-node.md
│   ├── bulk-update-node.md
│   └── ...
├── guides/
│   ├── update-patterns.md
│   ├── filter-syntax.md
│   ├── operator-reference.md
│   └── ...
├── troubleshooting/
│   ├── common-errors.md
│   ├── validation-errors.md
│   └── ...
└── migration/
    ├── v0.6-changes.md
    ├── v0.6-v2.0.md
    └── ...
```

**Link Requirements**:
- [ ] Every error links to troubleshooting guide
- [ ] Every deprecation links to migration guide
- [ ] Every operator links to operator reference
- [ ] Links include anchor to specific section
- [ ] Documentation tested for correctness

**Example Error with Links**:
```
NodeValidationError: Invalid filter operator '$invalid'.

Valid operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $regex, $exists, $and, $or, $not

See operator reference: https://docs.kailash.ai/dataflow/guides/filter-syntax#operators

Common mistakes: https://docs.kailash.ai/dataflow/troubleshooting/common-errors#invalid-operator

Did you mean '$inc' for incrementing? https://docs.kailash.ai/dataflow/guides/operator-reference#inc
```

---

### FR4: Documentation Quality

**Priority**: HIGH
**Complexity**: MEDIUM
**Risk Level**: LOW

#### FR4.1: Eliminate Documentation Contradictions

**Description**: All documentation must present consistent, non-contradictory information about API usage.

**Current Contradictions**:

1. **Parameter naming conflict**:
   - `/docs/api/nodes.md`: Says use `"id"` for UpdateNode
   - `/docs/development/crud.md`: Says use `"record_id"` for UpdateNode
   - **Required**: Single consistent parameter name across ALL docs

2. **Filter structure conflict**:
   - `/docs/api/nodes.md`: Shows `"filter": {...}` for BulkUpdateNode
   - `/docs/development/crud.md`: Shows `"conditions": {...}` for UpdateNode
   - **Required**: Unified `"filter"` terminology across operations

3. **Update operator visibility**:
   - `/docs/api/nodes.md`: No mention of `$inc`, `$mul` operators
   - `/docs/development/crud.md`: Shows `atomic_operations` with operators
   - **Required**: Full operator reference in API docs

**Validation Process**:
```bash
# Automated documentation validation
npm run docs:validate

# Checks:
# 1. All code examples are valid and tested
# 2. Parameter names consistent across all docs
# 3. No contradictory statements about same feature
# 4. All links resolve correctly
# 5. All examples follow current best practices
```

**Acceptance Criteria**:
- [ ] Zero contradictions across all documentation
- [ ] All code examples tested in CI pipeline
- [ ] Single source of truth for each API pattern
- [ ] Automated validation in CI/CD
- [ ] Documentation review checklist for all changes

#### FR4.2: Clear Pattern Documentation

**Description**: Documentation must clearly explain when to use each pattern and why.

**Required Sections**:

1. **Decision Trees**:
   ```markdown
   ## When to Use UpdateNode vs BulkUpdateNode

   Start here: How many records do you need to update?

   ONE record:
       → Use UpdateNode
       → Example: Update user profile after form submission
       → Performance: <1ms

   MULTIPLE records (same fields):
       → Use BulkUpdateNode
       → Example: Mark all pending orders as "processed"
       → Performance: ~5000 updates/sec

   MULTIPLE records (different fields per record):
       → Use BulkUpdateNode with data list
       → Example: Import updated product prices from CSV
       → Performance: ~3000 updates/sec

   See detailed comparison: [Bulk Operations Guide](../development/bulk-operations.md)
   ```

2. **Side-by-Side Comparisons**:
   ```markdown
   ## CreateNode vs UpdateNode Parameter Patterns

   | Aspect | CreateNode | UpdateNode |
   |--------|-----------|------------|
   | **Structure** | Flat fields | Nested filter + fields |
   | **Required params** | Model fields | filter, fields |
   | **Optional params** | options | options |
   | **Example** | `{"name": "Alice"}` | `{"filter": {"id": 1}, "fields": {"name": "Alice"}}` |
   | **Use case** | New record | Modify existing |
   | **Performance** | <1ms | <1ms |
   ```

3. **Common Mistakes Section**:
   ```markdown
   ## Common UpdateNode Mistakes

   ### ❌ WRONG: Using CreateNode syntax
   ```python
   workflow.add_node("UserUpdateNode", "update", {
       "id": 1,
       "name": "Alice Updated"
   })
   ```
   Error: "UpdateNode requires 'filter' and 'fields' parameters"

   ### ✅ CORRECT: Using nested structure
   ```python
   workflow.add_node("UserUpdateNode", "update", {
       "filter": {"id": 1},
       "fields": {"name": "Alice Updated"}
   })
   ```
   ```

**Acceptance Criteria**:
- [ ] Decision tree for every operation choice
- [ ] Side-by-side comparison for similar operations
- [ ] Common mistakes section with fixes
- [ ] Real-world use case examples
- [ ] Performance characteristics documented

#### FR4.3: Warning Annotations in Documentation

**Description**: Documentation must include prominent warnings for common pitfalls.

**Warning Types**:

1. **Critical Safety Warnings**:
   ```markdown
   ## ⚠️ CRITICAL: UpdateNode Safety

   UpdateNode with empty filter updates ALL records in the table.

   ```python
   # ❌ DANGEROUS: Updates every user in database
   workflow.add_node("UserUpdateNode", "update", {
       "filter": {},  # Empty = ALL records
       "fields": {"status": "deleted"}
   })

   # ✅ SAFE: Filter specific records
   workflow.add_node("UserUpdateNode", "update", {
       "filter": {"id": 1},
       "fields": {"status": "deleted"}
   })
   ```

   Always specify filter conditions unless you explicitly want to update all records.
   ```

2. **Performance Warnings**:
   ```markdown
   ## ⚡ PERFORMANCE: Use BulkUpdateNode for Multiple Records

   Calling UpdateNode in a loop is 100x slower than BulkUpdateNode.

   ```python
   # ❌ SLOW: 1000ms for 1000 records
   for user_id in user_ids:  # 1000 iterations
       workflow.add_node("UserUpdateNode", f"update_{user_id}", {
           "filter": {"id": user_id},
           "fields": {"status": "verified"}
       })

   # ✅ FAST: 10ms for 1000 records
   workflow.add_node("UserBulkUpdateNode", "bulk_update", {
       "filter": {"id": {"$in": user_ids}},
       "fields": {"status": "verified"}
   })
   ```

   Use BulkUpdateNode for 10+ records for significant performance improvement.
   ```

3. **Deprecation Warnings**:
   ```markdown
   ## 🔄 DEPRECATED: Old Parameter Names

   The following parameters are deprecated in v0.6+ and will be removed in v2.0:

   | Deprecated | Replacement | Migration Guide |
   |------------|------------|-----------------|
   | `conditions` | `filter` | [Link](migration/v0.6-v2.0.md#conditions-to-filter) |
   | `updates` | `fields` | [Link](migration/v0.6-v2.0.md#updates-to-fields) |
   | `record_id` | `filter: {"id": ...}` | [Link](migration/v0.6-v2.0.md#record-id-to-filter) |

   See full migration guide: [v0.6 → v2.0 Migration](migration/v0.6-v2.0.md)
   ```

**Acceptance Criteria**:
- [ ] Critical warnings use ⚠️ emoji and "CRITICAL" label
- [ ] Performance warnings use ⚡ emoji and show measurements
- [ ] Deprecation warnings use 🔄 emoji and link to migration guide
- [ ] Warnings appear at top of relevant sections
- [ ] Code examples show both wrong ❌ and correct ✅ approaches

---

### FR5: Developer Experience

**Priority**: HIGH
**Complexity**: MEDIUM
**Risk Level**: MEDIUM

#### FR5.1: Time to First Success

**Description**: New developers should successfully execute CRUD operations within defined time limits.

**Baseline Measurement** (Current State):
- Read documentation: 30 minutes
- Write first CreateNode: 5 minutes → ✅ **Success**
- Write first UpdateNode: 4+ hours → ❌ **Failure** (root cause of this ADR)
- Debug parameter structure: 2-4 hours
- Find correct documentation: 30-60 minutes

**Phase 1 Targets** (Enhanced Validation + Documentation):
- Read documentation: 20 minutes (improved clarity)
- Write first UpdateNode: 30 minutes (better errors)
- Debug parameter structure: 5 minutes (actionable errors)
- Find correct documentation: <2 minutes (better linkage)
- **Total**: <1 hour to CRUD success

**Phase 2 Targets** (Builder API):
- Read documentation: 10 minutes (simpler API)
- Write first UpdateNode with builder: 5 minutes (obvious API)
- Debug parameter structure: <1 minute (type hints)
- Find correct documentation: <1 minute (inline docs)
- **Total**: <15 minutes to CRUD success

**Phase 3 Targets** (Unified API):
- Read documentation: 5 minutes (consistent patterns)
- Write first UpdateNode: 2 minutes (same as CreateNode)
- Debug parameter structure: 0 minutes (pattern known from CreateNode)
- Find correct documentation: <30 seconds (same docs as CreateNode)
- **Total**: <5 minutes to CRUD success

**Measurement Method**:
```python
# User journey telemetry (opt-in)
class DeveloperJourneyTracker:
    def track_event(self, event_type, metadata):
        """Track developer journey events."""
        events = [
            "docs_page_view",
            "code_example_copy",
            "workflow_execute",
            "error_encountered",
            "error_resolved",
            "first_success"
        ]
        # Anonymous telemetry to measure time-to-success
```

**Acceptance Criteria**:
- [ ] 90th percentile time-to-success meets phase targets
- [ ] <10% of developers abandon after first error
- [ ] >80% success rate on first attempt (Phase 3)
- [ ] Telemetry collected from opt-in beta users

#### FR5.2: Reduced Support Burden

**Description**: API improvements should measurably reduce support ticket volume for API-related issues.

**Current Support Metrics** (Baseline):
```
Total monthly tickets: ~200
API-related tickets: ~80 (40%)
Top issues:
  1. UpdateNode parameter confusion: 30 tickets (37.5%)
  2. Filter syntax errors: 20 tickets (25%)
  3. Documentation contradictions: 15 tickets (18.75%)
  4. Parameter naming confusion: 10 tickets (12.5%)
  5. Other: 5 tickets (6.25%)

Average resolution time: 45 minutes
```

**Phase 1 Targets**:
```
API-related tickets: ~40 (-50%)
Top issues:
  1. UpdateNode parameter confusion: 10 tickets (-66%)
  2. Filter syntax errors: 15 tickets (-25%)
  3. Documentation contradictions: 0 tickets (-100%)
  4. Parameter naming confusion: 10 tickets (0%)
  5. Other: 5 tickets (0%)

Average resolution time: 20 minutes (-55%)
```

**Phase 2 Targets**:
```
API-related tickets: ~25 (-70%)
Top issues:
  1. UpdateNode parameter confusion: 3 tickets (-90%)
  2. Filter syntax errors: 10 tickets (-50%)
  3. Builder API questions: 7 tickets (new)
  4. Migration questions: 5 tickets (new)

Average resolution time: 10 minutes (-78%)
```

**Phase 3 Targets**:
```
API-related tickets: ~8 (-90%)
Top issues:
  1. API v2.0 migration: 5 tickets (new)
  2. Advanced features: 3 tickets (new)

Average resolution time: 5 minutes (-89%)
```

**Tracking Mechanism**:
- Tag all support tickets with category
- Monthly report generation
- Quarterly review of trends
- Correlation analysis with releases

**Acceptance Criteria**:
- [ ] 50% reduction in API tickets by Phase 1
- [ ] 70% reduction in API tickets by Phase 2
- [ ] 90% reduction in API tickets by Phase 3
- [ ] Average resolution time <10 minutes by Phase 2

#### FR5.3: Satisfaction Metrics

**Description**: Track developer satisfaction through surveys and Net Promoter Score (NPS).

**Measurement Approach**:

1. **In-Product Survey** (Quarterly):
   ```
   Question 1: How satisfied are you with DataFlow's API design?
   Scale: 1-10 (Very Dissatisfied → Very Satisfied)

   Question 2: How easy is it to learn DataFlow's CRUD operations?
   Scale: 1-10 (Very Difficult → Very Easy)

   Question 3: How clear are error messages when something goes wrong?
   Scale: 1-10 (Very Confusing → Very Clear)

   Question 4: How would you rate the documentation quality?
   Scale: 1-10 (Very Poor → Excellent)

   Question 5: Would you recommend DataFlow to a colleague?
   Scale: 0-10 (Not at all likely → Extremely likely) [NPS]
   ```

2. **NPS Calculation**:
   ```
   Promoters (9-10): % who would strongly recommend
   Passives (7-8): % who are neutral
   Detractors (0-6): % who would not recommend

   NPS = % Promoters - % Detractors
   ```

**Baseline Metrics** (Current State):
- API Design Satisfaction: Unknown (assumed ~5/10 based on complaints)
- Learning Ease: Unknown (assumed ~4/10 based on 4-hour debug time)
- Error Message Clarity: Unknown (assumed ~3/10 based on confusion)
- Documentation Quality: Unknown (assumed ~5/10 based on contradictions)
- NPS: Unknown (assumed ~0 to -10 for API)

**Phase 1 Targets**:
- API Design Satisfaction: >6/10
- Learning Ease: >6/10
- Error Message Clarity: >8/10 (major focus area)
- Documentation Quality: >7/10
- NPS: >10

**Phase 2 Targets**:
- API Design Satisfaction: >8/10
- Learning Ease: >8/10
- Error Message Clarity: >9/10
- Documentation Quality: >8/10
- NPS: >30

**Phase 3 Targets**:
- API Design Satisfaction: >9/10
- Learning Ease: >9/10
- Error Message Clarity: >9/10
- Documentation Quality: >9/10
- NPS: >50

**Acceptance Criteria**:
- [ ] Survey completion rate >30%
- [ ] Trend improvement each phase
- [ ] NPS >50 by Phase 3 (world-class)
- [ ] All metrics >8/10 by Phase 3

---

## 2. Non-Functional Requirements

### NFR1: Backward Compatibility

**Priority**: CRITICAL
**Complexity**: HIGH
**Risk Level**: HIGH

#### NFR1.1: Zero Breaking Changes in Phase 1-2

**Description**: All Phase 1 and Phase 2 changes must maintain 100% backward compatibility with existing code.

**Compatibility Requirements**:

1. **Old API continues working**:
   ```python
   # v0.5 API (old) - must still work in v0.6+
   workflow.add_node("UserUpdateNode", "update", {
       "conditions": {"id": 1},  # Deprecated but functional
       "updates": {"name": "Alice"}
   })
   # Result: Works with deprecation warning
   ```

2. **Adapter layer translates old → new**:
   ```python
   class UpdateNodeV1Adapter:
       """Transparent adapter for v0.5 → v0.6+ API."""

       def translate_params(self, params):
           """Translate old API to new API format."""
           if "conditions" in params:
               # Old format detected
               return {
                   "filter": params.pop("conditions"),
                   "fields": params.pop("updates", {}),
                   "options": params  # Remaining params
               }
           # Already new format
           return params
   ```

3. **Dual testing in CI**:
   ```python
   # Test both APIs in parallel
   @pytest.mark.parametrize("api_version", ["v0.5", "v0.6"])
   def test_update_operation(api_version):
       if api_version == "v0.5":
           params = {"conditions": {"id": 1}, "updates": {"name": "Alice"}}
       else:
           params = {"filter": {"id": 1}, "fields": {"name": "Alice"}}

       result = execute_update(params)
       assert result["success"] == True
   ```

**Acceptance Criteria**:
- [ ] 100% of v0.5 code works in v0.6+ without modification
- [ ] Adapter layer tested with 1000+ real-world examples
- [ ] Performance within 5% of direct implementation
- [ ] Deprecation warnings logged but don't break execution
- [ ] CI tests both APIs in parallel

**Risk Mitigation**:
- Extensive backward compatibility test suite
- Canary deployments for early detection
- Rollback plan if issues discovered
- User communication about deprecation timeline

#### NFR1.2: Migration Path to v2.0

**Description**: Provide clear, automated migration path from v0.5 → v2.0 with tools and documentation.

**Migration Tools**:

1. **Automated Codemod**:
   ```bash
   # AST-based code transformation
   npx dataflow-migrate upgrade --from v0.5 --to v2.0 --path ./src

   # Transforms:
   # Before (v0.5):
   workflow.add_node("UserUpdateNode", "update", {
       "conditions": {"id": 1},
       "updates": {"name": "Alice"}
   })

   # After (v2.0):
   workflow.add_node("UserUpdateNode", "update", {
       "filter": {"id": 1},
       "fields": {"name": "Alice"}
   })
   ```

2. **Migration Report**:
   ```bash
   $ npx dataflow-migrate analyze --path ./src

   Migration Analysis Report
   =========================
   Total files scanned: 47
   DataFlow nodes found: 312

   v0.5 API usage:
     - UpdateNode with "conditions": 89 occurrences
     - UpdateNode with "updates": 89 occurrences
     - BulkUpdateNode with "update_fields": 23 occurrences

   Estimated migration effort: 2-3 hours (mostly automated)
   Estimated test updates: 15-20 test files

   Run migration: npx dataflow-migrate upgrade --from v0.5 --to v2.0
   ```

3. **Deprecation Timeline**:
   ```
   v0.6.0 (2025-10-28): Deprecated API marked, warnings issued
   v0.7.0 (2025-11-28): Deprecation warnings become errors (opt-in)
   v1.0.0 (2026-01-28): Deprecation warnings mandatory
   v2.0.0 (2026-04-28): Old API removed

   Total deprecation period: 6 months
   ```

**Migration Guide Structure**:
```markdown
# DataFlow v0.5 → v2.0 Migration Guide

## Overview
- Estimated time: 2-4 hours for typical project
- Automated migration: 90%+ of changes
- Breaking changes: Parameter naming only

## Quick Start
```bash
# 1. Analyze your codebase
npx dataflow-migrate analyze

# 2. Run automated migration
npx dataflow-migrate upgrade --from v0.5 --to v2.0

# 3. Review changes
git diff

# 4. Update tests
npm test
```

## Change Details
### UpdateNode Parameter Changes
[Table of all parameter changes]

### Common Patterns
[Side-by-side examples]

## Troubleshooting
[Common issues and fixes]
```

**Acceptance Criteria**:
- [ ] 90%+ of migrations fully automated
- [ ] Migration tool tested on 50+ real projects
- [ ] Migration guide covers 100% of breaking changes
- [ ] Deprecation timeline clearly communicated
- [ ] Rollback process documented

---

### NFR2: Performance

**Priority**: HIGH
**Complexity**: MEDIUM
**Risk Level**: MEDIUM

#### NFR2.1: No Performance Degradation

**Description**: All API changes must maintain or improve performance compared to current implementation.

**Performance Benchmarks**:

| Operation | Current (v0.5) | Phase 1 Target | Phase 2 Target | Phase 3 Target |
|-----------|----------------|----------------|----------------|----------------|
| **Single Update** | <1ms | <1ms (±5%) | <1ms (±5%) | <1ms (±5%) |
| **Bulk Update (1K)** | 200ms | 200ms (±5%) | 200ms (±5%) | 200ms (±5%) |
| **Bulk Update (10K)** | 2000ms | 2000ms (±5%) | 2000ms (±5%) | 2000ms (±5%) |
| **Parameter Validation** | <0.1ms | <0.5ms | <0.5ms | <0.5ms |
| **Error Generation** | <0.1ms | <1ms | <1ms | <1ms |
| **Builder API** | N/A | N/A | <2ms | <2ms |

**Benchmark Suite**:
```python
# Performance regression tests
@pytest.mark.benchmark
def test_update_node_performance(benchmark):
    """Benchmark UpdateNode execution time."""
    params = {"filter": {"id": 1}, "fields": {"name": "Alice"}}

    def execute():
        node = UpdateNode(**params)
        return node.execute()

    result = benchmark(execute)
    assert result.stats.mean < 0.001  # <1ms average
    assert result.stats.stddev < 0.0002  # Low variance

@pytest.mark.benchmark
def test_bulk_update_performance(benchmark):
    """Benchmark BulkUpdateNode with 10K records."""
    params = {
        "filter": {"active": True},
        "fields": {"status": "verified"}
    }

    def execute():
        node = BulkUpdateNode(**params)
        return node.execute()

    result = benchmark(execute)
    assert result.stats.mean < 2.0  # <2s for 10K records
    assert result.stats.stddev < 0.5  # Consistent
```

**Acceptance Criteria**:
- [ ] All operations within 5% of baseline
- [ ] No operation >10% slower than baseline
- [ ] Benchmark suite runs in CI on every commit
- [ ] Performance regression alerts in Slack
- [ ] Quarterly performance review

#### NFR2.2: Validation Overhead Limits

**Description**: Enhanced validation must add <1ms overhead per operation.

**Validation Performance Budget**:
```
Total validation overhead: <1ms
Breakdown:
  - Parameter type checking: <0.2ms
  - Structure validation: <0.3ms
  - Error message generation: <0.3ms
  - Documentation link lookup: <0.1ms
  - Deprecation warnings: <0.1ms
```

**Optimization Strategies**:
1. **Lazy error message generation**:
   ```python
   # Only generate detailed message if error occurs
   if validation_fails:
       error_message = generate_detailed_error()  # <1ms
   else:
       pass  # <0.1ms for success path
   ```

2. **Cached validation rules**:
   ```python
   # Cache compiled validation rules
   @lru_cache(maxsize=1000)
   def get_validation_rules(model_name):
       return compile_validation_rules(model_name)
   ```

3. **Incremental validation**:
   ```python
   # Validate only changed parameters
   def validate_update_params(new_params, cached_schema):
       changed = diff(new_params, cached_schema)
       return validate_fields(changed)  # Only validate changes
   ```

**Acceptance Criteria**:
- [ ] Validation overhead <1ms (p99)
- [ ] Success path <0.5ms (p99)
- [ ] Error path <1.5ms (p99)
- [ ] Memory overhead <1MB per validation
- [ ] Benchmarked on every commit

---

### NFR3: Type Safety

**Priority**: MEDIUM
**Complexity**: MEDIUM
**Risk Level**: LOW

#### NFR3.1: IDE Autocomplete Support

**Description**: All APIs must provide full type hints for IDE autocomplete and type checking.

**Type Hint Coverage**:

```python
from typing import Dict, List, Optional, Any, TypedDict

class UpdateNodeParams(TypedDict, total=False):
    """Type-safe UpdateNode parameters."""
    filter: Dict[str, Any]  # Required
    fields: Dict[str, Any]  # Required
    options: Optional[Dict[str, Any]]  # Optional

class UserUpdateNodeParams(UpdateNodeParams):
    """Type-safe User-specific UpdateNode parameters."""
    filter: Dict[str, Any]
    fields: Dict[str, Any]  # Auto-generated from User model
    options: Optional[Dict[str, Any]]

# Usage with full autocomplete
params: UserUpdateNodeParams = {
    "filter": {"id": 1},
    "fields": {
        "name": "Alice",  # IDE shows valid User fields
        "email": "alice@example.com",
        "age": 31
    }
}
```

**Builder API Type Hints**:
```python
from typing import Generic, TypeVar

T = TypeVar('T')

class QueryBuilder(Generic[T]):
    """Type-safe query builder."""

    def where(self, **conditions) -> 'QueryBuilder[T]':
        """Add filter conditions."""
        ...

    def update(self, **fields) -> 'QueryBuilder[T]':
        """Add fields to update."""
        ...

    def build(self) -> Dict[str, Any]:
        """Build parameter dictionary."""
        ...

# Usage with IDE autocomplete
update = (QueryBuilder(User)
    .where(id=1)  # IDE knows User has 'id'
    .update(name="Alice")  # IDE knows User has 'name'
    .build())
```

**Acceptance Criteria**:
- [ ] 100% of public APIs have type hints
- [ ] Type hints pass mypy strict mode
- [ ] IDE autocomplete works in VSCode, PyCharm, Vim
- [ ] Type errors caught at development time
- [ ] Auto-generated type stubs for models

#### NFR3.2: Runtime Type Validation

**Description**: Validate parameter types at runtime with clear error messages.

**Validation Examples**:

```python
def validate_update_params(params: Dict[str, Any]) -> None:
    """Validate UpdateNode parameters with type checking."""

    # Check filter type
    if "filter" in params and not isinstance(params["filter"], dict):
        raise TypeError(
            f"Parameter 'filter' must be dict, got {type(params['filter']).__name__}.\n"
            f"Example: {{'filter': {{'id': 1}}}}"
        )

    # Check fields type
    if "fields" in params and not isinstance(params["fields"], dict):
        raise TypeError(
            f"Parameter 'fields' must be dict, got {type(params['fields']).__name__}.\n"
            f"Example: {{'fields': {{'name': 'Alice', 'age': 31}}}}"
        )

    # Check field value types against model
    if "fields" in params:
        for field, value in params["fields"].items():
            expected_type = get_field_type(field)
            if not isinstance(value, expected_type):
                raise TypeError(
                    f"Field '{field}' expects {expected_type.__name__}, "
                    f"got {type(value).__name__}.\n"
                    f"Example: {{'{field}': <{expected_type.__name__} value>}}"
                )
```

**Acceptance Criteria**:
- [ ] All parameter types validated at runtime
- [ ] Type errors include expected vs actual type
- [ ] Type errors include example of correct type
- [ ] Validation overhead <0.5ms
- [ ] 100% test coverage for type validation

---

### NFR4: Maintainability

**Priority**: MEDIUM
**Complexity**: MEDIUM
**Risk Level**: LOW

#### NFR4.1: Clear Design Principles

**Description**: Document and enforce design principles for all future API additions.

**Design Principles**:

1. **Consistency First**:
   - New operations follow existing patterns
   - Similar operations use similar parameter structures
   - Parameter naming conventions strictly enforced

2. **Progressive Disclosure**:
   - Simple cases require minimal parameters
   - Advanced features opt-in through explicit parameters
   - Complexity scales with use case complexity

3. **Fail-Fast with Guidance**:
   - Invalid parameters detected immediately
   - Error messages suggest correct alternatives
   - Documentation links provided for all errors

4. **Type Safety**:
   - All APIs fully type-hinted
   - Runtime validation matches type hints
   - IDE autocomplete for all parameters

5. **Performance Budget**:
   - New features must meet performance benchmarks
   - No >10% performance regression
   - Validation overhead <1ms

**Enforcement**:
```python
# Design principle checklist for new operations
class OperationDesignChecklist:
    """Enforce design principles for new operations."""

    @staticmethod
    def validate_new_operation(operation_spec):
        """Validate new operation against design principles."""
        checks = [
            check_consistency_with_existing(),
            check_progressive_disclosure(),
            check_error_messages_quality(),
            check_type_safety(),
            check_performance_budget()
        ]
        return all(checks)
```

**Acceptance Criteria**:
- [ ] Design principles documented in CONTRIBUTING.md
- [ ] Automated checks enforce principles in CI
- [ ] Code review checklist includes principles
- [ ] New operations require design review
- [ ] Quarterly review of adherence to principles

---

## 3. Success Metrics

### Quantitative Metrics

| Metric | Baseline | Phase 1 | Phase 2 | Phase 3 |
|--------|----------|---------|---------|---------|
| **Time to First Success** | 4+ hours | <30 min | <15 min | <5 min |
| **API Pattern Confusion** | Unknown | <20% | <10% | <5% |
| **Support Tickets (API)** | 80/month | 40/month | 25/month | 8/month |
| **Documentation Satisfaction** | ~5/10 | >7/10 | >8/10 | >9/10 |
| **Error Message Clarity** | ~3/10 | >8/10 | >9/10 | >9/10 |
| **NPS (API Experience)** | ~0 | >10 | >30 | >50 |

### Qualitative Metrics

1. **Developer Sentiment**:
   - Community forum discussions about API
   - GitHub issue tone and frequency
   - Blog post sentiment analysis

2. **Documentation Usage**:
   - Page views for troubleshooting guides
   - Search queries for API help
   - Video tutorial completion rates

3. **Code Quality**:
   - Adoption rate of builder API
   - Deprecation warning suppression rate
   - Test coverage of API usage

---

## 4. Risk Assessment

### High-Impact Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Backward Compatibility Break** | Low | CRITICAL | Extensive testing, adapter layer, staged rollout |
| **Performance Regression** | Medium | HIGH | Benchmark suite, performance budgets, profiling |
| **Incomplete Migration** | Medium | MEDIUM | Automated tools, clear timeline, support program |
| **User Confusion During Transition** | High | MEDIUM | Clear communication, deprecation warnings, docs |

### Medium-Impact Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Documentation Errors** | Medium | MEDIUM | Automated validation, code example testing |
| **Builder API Complexity** | Low | MEDIUM | User testing, iterative refinement |
| **Support Burden Spike** | Low | MEDIUM | Phased rollout, office hours, FAQ |

### Low-Impact Risks

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| **Type Hint Errors** | Low | LOW | Mypy strict mode, CI validation |
| **Validation Overhead** | Low | LOW | Performance benchmarks, optimization |

---

## 5. Dependencies

### External Dependencies

- **Kailash SDK**: Node registration, parameter validation system
- **Python Type System**: TypedDict, Generic, type hints
- **Testing Infrastructure**: Pytest, benchmark tools
- **Documentation System**: MkDocs, automated example validation
- **CI/CD Pipeline**: GitHub Actions, performance monitoring

### Internal Dependencies

- **DataFlow Core**: Model registration, node generation
- **Migration System**: Schema evolution, existing migration tools
- **Connection Pooling**: Database connection management
- **Validation Framework**: Existing validation infrastructure

---

## 6. Implementation Phases

### Phase 1: Immediate Fixes (v0.6.1 - Week 1)
**Priority**: CRITICAL
**Dependencies**: None

**Tasks**:
1. Enhanced validation logic (2 days)
2. Error message improvements (1 day)
3. Documentation overhaul (2 days)
4. Parameter naming deprecations (1 day)

**Deliverables**:
- 50% reduction in debugging time
- Zero documentation contradictions
- Actionable error messages
- Deprecation warnings

### Phase 2: Builder Pattern API (v0.6.5 - Weeks 2-3)
**Priority**: HIGH
**Dependencies**: Phase 1 complete

**Tasks**:
1. QueryBuilder class implementation (5 days)
2. Helper functions (2 days)
3. Type-safe API (2 days)
4. Migration guide (2 days)

**Deliverables**:
- Builder API for all CRUD operations
- 60% code reduction for CRUD
- Type-safe interface
- Migration guide and tools

### Phase 3: API v2.0 Design (v0.7.0 - Months 2-3)
**Priority**: MEDIUM
**Dependencies**: Phase 2 adoption >30%

**Tasks**:
1. Unified node API (3 weeks)
2. Backward compatibility layer (1 week)
3. Deprecation strategy (1 week)
4. Comprehensive testing (2 weeks)

**Deliverables**:
- Unified consistent API
- Automated migration tools
- Complete test coverage
- Production-ready v2.0

---

## 7. Monitoring and Validation

### Telemetry (Opt-In)

```python
# Anonymous usage telemetry
class APIUsageTelemetry:
    """Track API usage patterns (opt-in only)."""

    def track_operation(self, operation_type, api_version, success):
        """Track operation execution."""
        # operation_type: "create", "update", "bulk_update", etc.
        # api_version: "v0.5", "v0.6", "v2.0"
        # success: True/False
        ...

    def track_error(self, error_type, error_message):
        """Track error occurrences."""
        ...

    def track_migration(self, from_version, to_version, success):
        """Track migration attempts."""
        ...
```

### Quality Gates

**Phase 1 Gates**:
- [ ] Zero regressions in test suite
- [ ] Documentation contradictions = 0
- [ ] Error message clarity >8/10 (user testing)
- [ ] Performance within 5% baseline

**Phase 2 Gates**:
- [ ] Builder API test coverage >95%
- [ ] Type hints pass mypy strict
- [ ] Migration guide validated by 10+ users
- [ ] Performance within 5% baseline

**Phase 3 Gates**:
- [ ] Automated migration success >95%
- [ ] Backward compatibility 100%
- [ ] All metrics >8/10
- [ ] Performance within 5% baseline

---

## Appendix A: Complete Parameter Mapping

### Current State (v0.5)

```python
# CreateNode
{
    "field1": value1,
    "field2": value2,
    ...
    "tenant_id": "...",
    "return_ids": True
}

# UpdateNode
{
    "conditions": {...},  # Filter
    "updates": {...},     # Fields to update
    "tenant_id": "...",
    "return_updated": True
}

# BulkUpdateNode
{
    "filter": {...},         # Different from "conditions"
    "update_fields": {...},  # Different from "updates"
    "batch_size": 1000
}
```

### Target State (v2.0)

```python
# ALL nodes follow same structure
{
    "filter": {...},     # Consistent across all operations
    "fields": {...},     # Consistent across all operations
    "options": {         # Consistent metadata location
        "return_fields": [...],
        "batch_size": 1000,
        "tenant_id": "..."
    }
}
```

---

## Appendix B: Error Message Templates

### Template Structure
```
{ErrorType}: {Problem Summary}

Current value: {what_user_provided}

Expected format:
{code_example_of_correct_usage}

{Additional_context_or_suggestions}

Documentation: {specific_doc_link}
```

### Example Error Messages

See FR3.1 for complete examples.

---

## Appendix C: Migration Script Examples

### Automated Migration

```bash
# Analyze codebase
npx dataflow-migrate analyze --path ./src

# Preview changes
npx dataflow-migrate upgrade --from v0.5 --to v2.0 --dry-run

# Execute migration
npx dataflow-migrate upgrade --from v0.5 --to v2.0

# Validate migration
npm test
```

### Manual Migration Patterns

See Phase 2 migration guide for complete manual migration patterns.

---

**Document End**

---

**Next Steps**:
1. Review and approve requirements
2. Begin Phase 1 implementation
3. Set up telemetry infrastructure
4. Create detailed implementation tasks

**Questions for Stakeholders**:
1. Agreement on phased timeline (1 week + 2-3 weeks + 2-3 months)?
2. Acceptable performance budget (5% overhead)?
3. Deprecation timeline acceptable (6 months)?
4. Resource allocation for implementation?
