# DataFlow v0.7.4 Global State Bug - Investigation Summary

**Date**: 2025-10-27
**Investigation**: COMPLETE
**Status**: Bug confirmed, short-term fix applied, SDK patch required

---

## Quick Summary

DataFlow v0.7.4 registers generated nodes in a **GLOBAL** NodeRegistry singleton from Core SDK. When multiple DataFlow instances use the same model name (e.g., `ConversationMessage`), the second instance **overwrites** the first's node registrations, causing all operations to use the wrong database connection.

**Impact**: Complete test isolation failure - data from test 1 appears in test 3, making 10/26 tests fail.

---

## Root Cause (Confirmed)

### 1. Global NodeRegistry

**File**: `kailash_python_sdk/src/kailash/nodes/base.py:1952-1996`

```python
class NodeRegistry:
    _instance = None
    _nodes: dict[str, type[Node]] = {}  # ← GLOBAL CLASS VARIABLE (process-wide)
```

### 2. DataFlow Node Registration

**File**: `kailash_python_sdk/apps/kailash-dataflow/src/dataflow/core/nodes.py:168-173`

```python
for node_name, node_class in nodes.items():
    NodeRegistry.register(node_class, alias=node_name)  # ← Registers GLOBALLY
    globals()[node_name] = node_class                    # ← Pollutes global namespace
    self.dataflow_instance._nodes[node_name] = node_class  # ← Instance copy (unused)
```

### 3. Evidence from Test Script

```bash
$ python test_dataflow_isolation.py

WARNING:root:Overwriting existing node registration for 'ConversationMessageCreateNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageReadNode'
...10 more warnings...

--- Creating DataFlow instance 2 ---
New nodes registered: 0  ← CRITICAL: No new nodes! Overwrote existing!
```

**Explanation**:
1. First DataFlow instance creates `ConversationMessageCreateNode` → registers in NodeRegistry
2. Second DataFlow instance creates `ConversationMessageCreateNode` → **OVERWRITES** in NodeRegistry
3. Node class closure holds reference to **second** DataFlow instance
4. All future operations use **second** instance's database
5. First instance's database appears "empty" even after writes

---

## Answers to Original Questions

### 1. Does DataFlow v0.7.4 cache DATA at process/global level?

**Answer**: NO. It caches **NODE CLASSES** at process/global level.

Those node classes contain **closures** that capture references to the DataFlow instance that created them. When overwritten, the closure changes.

### 2. Does the `@db.model` decorator create global state?

**Answer**: YES, indirectly.

The `@db.model` decorator triggers:
1. Node generation via `DynamicNodeGenerator`
2. Node registration in **GLOBAL** `NodeRegistry._nodes`
3. Node insertion into **GLOBAL** `globals()` Python namespace

### 3. Is `auto_migrate=True` causing schema/data to be shared?

**Answer**: NO.

Migrations are per-database. The issue is node registration, not migrations.

### 4. What is the correct way to ensure complete isolation?

**Current (workaround)**:
```python
@pytest.fixture
def dataflow_db(temp_db):
    from kailash.nodes.base import NodeRegistry

    nodes_before = set(NodeRegistry.list_nodes().keys())

    db = DataFlow(db_url=temp_db, auto_migrate=True)

    @db.model
    class ConversationMessage:
        # ...

    yield db

    # Cleanup
    nodes_after = set(NodeRegistry.list_nodes().keys())
    new_nodes = nodes_after - nodes_before
    for node_name in new_nodes:
        NodeRegistry._nodes.pop(node_name, None)
        if node_name in globals():
            del globals()[node_name]
```

**Proper (SDK fix needed)**: DataFlow v0.7.5 should implement namespaced node registration.

### 5. Is this a DataFlow SDK bug or test design issue?

**Answer**: **DataFlow SDK BUG** (architectural flaw).

The SDK violates fundamental isolation principles:
- ❌ Global state shared across boundaries
- ❌ No cleanup mechanism
- ❌ Closure references persist after fixture teardown
- ❌ No documented multi-instance limitations

---

## Files Modified

### 1. Test Fix (Kaizen)

**File**: `apps/kailash-kaizen/tests/integration/memory/test_persistent_buffer_dataflow.py`

**Changes**:
- Added `NodeRegistry` import
- Record nodes before DataFlow creation
- Added `yield` to make fixture generator-based
- Added cleanup in teardown to remove registered nodes

**Status**: ✅ Implemented (not yet verified)

### 2. Investigation Script

**File**: `apps/kailash-kaizen/test_dataflow_isolation.py`

**Purpose**: Demonstrates the bug with minimal reproduction

**Status**: ✅ Created, confirmed bug

### 3. Bug Report

**File**: `apps/kailash-kaizen/DATAFLOW_GLOBAL_STATE_BUG_REPORT.md`

**Contents**:
- Executive summary
- Root cause analysis
- Reproduction steps
- Impact assessment
- Solution options (4 approaches)
- Recommendations

**Status**: ✅ Created

---

## Recommended Actions

### Immediate (Kaizen Team)

1. ✅ **DONE**: Fix test fixture with NodeRegistry cleanup
2. ⏳ **TODO**: Verify tests pass with fix
3. ⏳ **TODO**: Add test case to prevent regression

### Short-Term (DataFlow Team)

1. ⚠️ **URGENT**: Review and confirm root cause analysis
2. ⚠️ **URGENT**: Add warning to documentation about multi-instance limitations
3. 📋 **PLAN**: Design namespaced node registration for v0.7.5

### Long-Term (Core SDK + DataFlow)

1. 🔬 **RESEARCH**: Evaluate instance-scoped NodeRegistry for Core SDK v0.11.0
2. 🏗️ **ARCHITECT**: Design proper multi-instance support in DataFlow v0.8.0
3. 📚 **DOCUMENT**: Update architecture guides with multi-instance patterns

---

## Solution Design (DataFlow v0.7.5)

### Option A: Namespaced Nodes (Recommended)

```python
# In DataFlow.__init__
self._instance_namespace = f"df_{id(self)}"

# In DynamicNodeGenerator.generate_crud_nodes
def generate_crud_nodes(self, model_name: str, fields: Dict[str, Any]):
    namespace = self.dataflow_instance._instance_namespace
    nodes = {
        f"{namespace}_{model_name}CreateNode": self._create_node_class(...),
        f"{namespace}_{model_name}ReadNode": self._create_node_class(...),
        # ...
    }
```

**Pros**:
- ✅ Complete isolation
- ✅ Minimal code changes
- ✅ Backward compatible (nodes still work)

**Cons**:
- ⚠️ Node names less predictable
- ⚠️ Breaks hardcoded node name usage (rare)

### Option B: Cleanup API

```python
# In DataFlow class
def cleanup_node_registrations(self):
    """Remove this instance's nodes from global NodeRegistry."""
    for node_name in self._nodes.keys():
        NodeRegistry._nodes.pop(node_name, None)
        if node_name in globals():
            del globals()[node_name]

# In pytest fixture
@pytest.fixture
def dataflow_db(temp_db):
    db = DataFlow(db_url=temp_db, auto_migrate=True)
    # ...
    yield db
    db.cleanup_node_registrations()  # Explicit cleanup
```

**Pros**:
- ✅ Explicit control
- ✅ No naming changes

**Cons**:
- ⚠️ Requires manual cleanup (error-prone)
- ⚠️ Doesn't fix production multi-instance scenarios

---

## Testing Strategy

### Verification Tests (Kaizen)

1. **Test isolation**: Verify data doesn't leak between tests
2. **Node cleanup**: Verify NodeRegistry size before/after fixtures
3. **Multi-instance**: Verify two DataFlow instances work correctly

```python
def test_dataflow_multi_instance_isolation():
    """Verify two DataFlow instances with same model name are isolated."""
    db1 = DataFlow("sqlite:///test1.db", auto_migrate=True)

    @db1.model
    class User:
        id: str
        name: str

    db2 = DataFlow("sqlite:///test2.db", auto_migrate=True)

    @db2.model
    class User:  # Same model name
        id: str
        name: str

    # Write to db1
    workflow1 = WorkflowBuilder()
    workflow1.add_node("UserCreateNode", "create", {
        "db_instance": db1,
        "id": "1",
        "name": "Alice"
    })
    LocalRuntime().execute(workflow1.build())

    # Query db2 - should be empty
    workflow2 = WorkflowBuilder()
    workflow2.add_node("UserListNode", "list", {
        "db_instance": db2,
        "filters": {}
    })
    results, _ = LocalRuntime().execute(workflow2.build())

    assert len(results["list"]) == 0, "db2 contaminated with db1 data!"
```

---

## Open Questions

1. **Node Closure Behavior**: Do closures update when NodeRegistry entry is overwritten?
   - **Hypothesis**: Yes, new node class replaces old, new closure takes effect
   - **Verification**: Needs debugger session to trace closure references

2. **Production Impact**: How many production apps use multiple DataFlow instances?
   - **Low risk**: Most apps use single DataFlow instance
   - **High risk**: Multi-database scenarios (sharding, multi-tenant)

3. **Core SDK Breaking Change**: Can NodeRegistry be made instance-scoped?
   - **Challenge**: Workflow deserialization expects global registry
   - **Solution**: Registry federation (global + per-instance)

---

## Timeline

- **2025-10-27 06:00**: Investigation started
- **2025-10-27 06:45**: Root cause confirmed with test script
- **2025-10-27 07:00**: Fix applied to Kaizen tests
- **2025-10-27 07:15**: Bug report and summary created
- **Next**: Verify tests pass, escalate to DataFlow team

---

## Escalation

**To**: DataFlow SDK Team
**Priority**: HIGH (affects all multi-instance scenarios)
**Blocking**: Kaizen integration tests (workaround applied)

**Deliverables**:
1. ✅ Comprehensive bug report (DATAFLOW_GLOBAL_STATE_BUG_REPORT.md)
2. ✅ Reproduction script (test_dataflow_isolation.py)
3. ✅ Test fix (test_persistent_buffer_dataflow.py)
4. ⏳ Verified test results (pending)

---

**End of Investigation Summary**
