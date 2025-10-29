# DataFlow v0.7.4 Global State Persistence Bug

**Date**: 2025-10-27
**Severity**: CRITICAL
**Component**: DataFlow Core SDK
**Impact**: Test isolation failures, data leakage between separate database instances

---

## Executive Summary

DataFlow v0.7.4 has a **critical design flaw** where node classes generated via `@db.model` are registered **GLOBALLY** in the Core SDK's `NodeRegistry`, causing complete test isolation failure. When multiple DataFlow instances use the same model name (e.g., `ConversationMessage`), the second registration **overwrites** the first, causing all subsequent operations to use the wrong database connection.

**Result**: Data from one test appears in unrelated tests, making DataFlow **unsuitable for testing** in its current form.

---

## Root Cause Analysis

### 1. Global NodeRegistry Singleton

**Location**: `./src/kailash/nodes/base.py:1952-1996`

```python
class NodeRegistry:
    """Registry for discovering and managing available nodes."""

    _instance = None
    _nodes: dict[str, type[Node]] = {}  # ← GLOBAL CLASS VARIABLE

    @classmethod
    def register(cls, node_class: type[Node], alias: str | None = None):
        """Register a node class."""
        # ... validation ...
        cls._nodes[node_name] = node_class  # ← GLOBAL REGISTRATION
```

**Problem**: `_nodes` is a **class variable** shared across ALL NodeRegistry instances in the process.

### 2. DataFlow Node Generation

**Location**: `./apps/kailash-dataflow/src/dataflow/core/nodes.py:168-173`

```python
def generate_crud_nodes(self, model_name: str, fields: Dict[str, Any]):
    """Generate CRUD nodes for a model."""
    nodes = {
        f"{model_name}CreateNode": self._create_node_class(...),
        # ... other nodes ...
    }

    # Register nodes with Kailash's NodeRegistry system
    for node_name, node_class in nodes.items():
        NodeRegistry.register(node_class, alias=node_name)  # ← GLOBAL REGISTRATION
        globals()[node_name] = node_class                    # ← GLOBAL NAMESPACE
        self.dataflow_instance._nodes[node_name] = node_class  # ← Instance copy
```

**Problems**:
1. **NodeRegistry.register()** stores node in **global `_nodes` dict**
2. **globals()[node_name]** pollutes **global Python namespace**
3. **Second registration overwrites first** with same model name

### 3. Node Execution Path

When `ConversationMessageCreateNode` is instantiated:

```python
# Inside generated node class (closure)
dataflow_instance = self.dataflow_instance  # ← References WHICH DataFlow?
test_context = self._test_context           # ← References WHICH test context?
```

**Critical Question**: When the node class is overwritten in NodeRegistry, which DataFlow instance does the closure reference?

**Answer**: The **LAST** registered DataFlow instance, because:
- Node class is recreated with new closure
- Old closure is garbage collected
- New node class replaces old in NodeRegistry
- All future uses get the **new** closure pointing to **new** DataFlow instance

---

## Reproduction

### Test Case: 26 Integration Tests

**File**: `./repos/dev/kailash_kaizen/apps/kailash-kaizen/tests/integration/memory/test_persistent_buffer_dataflow.py`

**Setup**:
```python
@pytest.fixture
def temp_db():
    """Create temporary SQLite database (function-scoped)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield f"sqlite:///{db_path}"

@pytest.fixture
def dataflow_db(temp_db):
    """Create DataFlow instance with ConversationMessage model."""
    db = DataFlow(db_url=temp_db, auto_migrate=True)

    @db.model
    class ConversationMessage:  # ← Same model name in all tests!
        id: str
        conversation_id: str
        sender: str
        content: str
```

**Expected Behavior**:
- Each test gets fresh SQLite database in temp directory
- Function-scoped fixtures ensure complete isolation
- Test 1 data stays in test 1's database
- Test 2 gets empty database

**Actual Behavior**:
- Test 1 saves: `"Hello, how are you?"` to `session_1`
- Test 3 (`test_empty_conversation`) expects 0 messages from `empty_session`
- Test 3 **FAILS**: Finds 1 message containing `"Hello, how are you?"`
- 10 tests fail, all showing data from first test

**Evidence**:
```bash
$ python test_dataflow_isolation.py

WARNING:root:Overwriting existing node registration for 'ConversationMessageCreateNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageReadNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageUpdateNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageDeleteNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageListNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageUpsertNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageBulkCreateNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageBulkUpdateNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageBulkDeleteNode'
WARNING:root:Overwriting existing node registration for 'ConversationMessageBulkUpsertNode'

--- Creating DataFlow instance 2 ---
New nodes registered: 0  ← NO NEW NODES! Overwrote existing!
```

---

## Impact Assessment

### 1. Test Isolation Failure
- **ALL** DataFlow integration tests unreliable
- Data leaks between unrelated tests
- Non-deterministic failures based on test execution order
- **Cannot trust test results**

### 2. Multi-Tenant Risk
- If two DataFlow instances exist in same process with same model names
- Second instance **overwrites** first in NodeRegistry
- Operations on first instance may use second instance's database
- **CRITICAL SECURITY RISK** for multi-tenant applications

### 3. Production Impact
- **LOW IMMEDIATE RISK**: Most production apps use single DataFlow instance
- **HIGH RISK**: Applications with multiple DataFlow instances (e.g., multi-database scenarios)
- **HIGH RISK**: Long-running processes that recreate DataFlow instances

---

## Why Tests "Pass" Initially

Tests may pass when:
1. **Single process execution**: First DataFlow instance persists
2. **No model name collisions**: Different model names don't overwrite
3. **Lucky execution order**: Test using "wrong" database happens to get "right" data

Tests fail when:
1. **Multiple instances with same model name** (our case)
2. **Parallel test execution**: Process-level isolation prevents issue
3. **Test execution order** changes (pytest randomization)

---

## Solutions

### Option 1: Namespaced Node Registration (RECOMMENDED)

**Change**: Include DataFlow instance ID in node names

```python
# In DataFlow.core.nodes.py
def generate_crud_nodes(self, model_name: str, fields: Dict[str, Any]):
    # Generate unique node names per DataFlow instance
    instance_id = id(self.dataflow_instance)
    nodes = {
        f"{model_name}CreateNode_{instance_id}": self._create_node_class(...),
        f"{model_name}ReadNode_{instance_id}": self._create_node_class(...),
        # ...
    }
```

**Pros**:
- ✅ Complete isolation between DataFlow instances
- ✅ No global state pollution
- ✅ Minimal code changes

**Cons**:
- ❌ Node names less predictable
- ❌ Breaks existing code that hardcodes node names
- ❌ Complicates debugging (longer names)

### Option 2: Instance-Scoped NodeRegistry

**Change**: Make NodeRegistry instance-scoped, not global

```python
# In DataFlow.__init__
self._node_registry = NodeRegistry()  # Instance-specific

# In DataFlow.core.nodes.py
self.dataflow_instance._node_registry.register(node_class, alias=node_name)
```

**Pros**:
- ✅ True isolation per DataFlow instance
- ✅ No naming collisions
- ✅ Clean architecture

**Cons**:
- ❌ **BREAKS Core SDK architecture** (NodeRegistry designed as singleton)
- ❌ Requires Core SDK changes (high risk)
- ❌ Workflow deserialization breaks (expects global registry)

### Option 3: pytest Fixture Cleanup

**Change**: Clear NodeRegistry between tests

```python
@pytest.fixture
def dataflow_db(temp_db):
    db = DataFlow(db_url=temp_db, auto_migrate=True)

    @db.model
    class ConversationMessage:
        # ...

    yield db

    # Cleanup: Unregister all nodes from this DataFlow instance
    for node_name in db._nodes.keys():
        NodeRegistry.unregister(node_name)
```

**Pros**:
- ✅ Minimal SDK changes
- ✅ Works for testing
- ✅ No production impact

**Cons**:
- ❌ Only fixes tests, not production multi-instance scenarios
- ❌ Requires manual cleanup in all test fixtures
- ❌ Doesn't address root cause

### Option 4: Database Connection Isolation (CURRENT WORKAROUND)

**Change**: Store database URL in node class, resolve at execution time

```python
# In _create_node_class
class DynamicNode(Node):
    def execute(self, **kwargs):
        # Resolve DataFlow instance at execution time
        dataflow = kwargs.get('db_instance')
        if not dataflow:
            dataflow = self._find_dataflow_by_model(model_name)

        # Use resolved DataFlow's connection
        return super().execute(db_instance=dataflow, **kwargs)
```

**Pros**:
- ✅ Fixes data leakage issue
- ✅ Maintains global node registration
- ✅ Backward compatible

**Cons**:
- ❌ Requires `db_instance` parameter in all node calls
- ❌ Adds runtime overhead
- ❌ Complex resolution logic

---

## Recommended Solution

**Combination of Option 1 + Option 3**:

1. **Short-term (pytest fix)**: Add `NodeRegistry.clear()` to test fixtures
2. **Long-term (SDK fix)**: Implement namespaced node registration in DataFlow v0.7.5

### Short-Term Fix (pytest)

```python
@pytest.fixture
def dataflow_db(temp_db):
    """Create DataFlow instance with ConversationMessage model."""
    # Record nodes before
    nodes_before = set(NodeRegistry.list_nodes().keys())

    db = DataFlow(db_url=temp_db, auto_migrate=True)

    @db.model
    class ConversationMessage:
        id: str
        conversation_id: str
        sender: str
        content: str

    yield db

    # Cleanup: Remove only nodes added by this fixture
    nodes_after = set(NodeRegistry.list_nodes().keys())
    new_nodes = nodes_after - nodes_before
    for node_name in new_nodes:
        NodeRegistry._nodes.pop(node_name, None)
```

### Long-Term Fix (DataFlow v0.7.5)

```python
# In DataFlow.__init__
self._instance_namespace = f"df_{id(self)}"

# In generate_crud_nodes
def generate_crud_nodes(self, model_name: str, fields: Dict[str, Any]):
    namespace = self.dataflow_instance._instance_namespace
    nodes = {
        f"{namespace}_{model_name}CreateNode": self._create_node_class(...),
        # ...
    }
```

---

## Testing the Fix

### Test 1: Isolation Verification

```python
def test_dataflow_isolation():
    """Verify two DataFlow instances don't interfere."""
    db1 = DataFlow("sqlite:///test1.db", auto_migrate=True)

    @db1.model
    class User:
        id: str
        name: str

    db2 = DataFlow("sqlite:///test2.db", auto_migrate=True)

    @db2.model
    class User:
        id: str
        name: str

    # Save to db1
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

    assert len(results["list"]) == 0, "db2 should not contain db1's data!"
```

### Test 2: Node Registry State

```python
def test_node_registry_cleanup():
    """Verify NodeRegistry cleanup between fixtures."""
    nodes_before = set(NodeRegistry.list_nodes().keys())

    # Create DataFlow with cleanup
    with pytest_fixture_with_cleanup():
        db = DataFlow("sqlite:///test.db", auto_migrate=True)

        @db.model
        class TempModel:
            id: str

    nodes_after = set(NodeRegistry.list_nodes().keys())

    assert nodes_before == nodes_after, "NodeRegistry not cleaned up!"
```

---

## Questions Answered

### 1. Does DataFlow v0.7.4 cache DATA at process/global level?

**Answer**: **NO**, but it caches **NODE CLASSES** at process/global level, and those node classes hold **DATABASE CONNECTION REFERENCES** via closures.

### 2. Does the `@db.model` decorator create global state?

**Answer**: **YES**. The `@db.model` decorator triggers node generation, which registers nodes in the **GLOBAL** `NodeRegistry._nodes` dict.

### 3. Is `auto_migrate=True` causing schema/data to be shared?

**Answer**: **NO**. Schema migrations are per-database. The issue is **node registration**, not migrations.

### 4. What is the correct way to ensure complete isolation?

**Answer**:
- **Current**: Use `NodeRegistry` cleanup in pytest fixtures (workaround)
- **Proper**: DataFlow v0.7.5 should implement namespaced node registration

### 5. Is this a DataFlow SDK bug or test design issue?

**Answer**: **DataFlow SDK BUG**. The architecture violates test isolation principles:
- Global state (NodeRegistry) shared across test boundaries
- No cleanup mechanism for node registrations
- Closure-captured references to DataFlow instances persist after fixture teardown

---

## Impact Timeline

- **v0.7.4 (Current)**: Bug present, test isolation broken
- **v0.7.5 (Target)**: Fix with namespaced node registration
- **v0.8.0 (Alternative)**: Consider instance-scoped NodeRegistry (breaking change)

---

## Related Issues

- **Core SDK NodeRegistry**: Designed as singleton for workflow deserialization
- **DataFlow TDD Mode**: Uses global test context (similar issue, but has cleanup)
- **Multi-Instance Support**: Not architected for multiple DataFlow instances per process

---

## Recommendations

1. **Immediate**: Fix Kaizen tests with NodeRegistry cleanup
2. **DataFlow v0.7.5**: Implement namespaced node registration
3. **Documentation**: Warn against multiple DataFlow instances with same model names
4. **Core SDK v0.11.0**: Consider instance-scoped NodeRegistry as opt-in feature

---

**End of Report**
