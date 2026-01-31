# Kailash Pattern Rules

## Scope
These rules apply to all Kailash SDK code.

## MUST Rules

### 1. Runtime Execution Pattern
MUST use `runtime.execute(workflow.build())`.

**Correct**:
```python
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

**Incorrect**:
```python
❌ workflow.execute(runtime)  # WRONG
❌ runtime.execute(workflow)  # Missing .build()
❌ runtime.run(workflow)  # Wrong method
```

**Enforced by**: validate-workflow hook
**Violation**: Code review flag

### 2. String-Based Node IDs
Node IDs MUST be string literals.

**Correct**:
```python
workflow.add_node("NodeType", "my_node_id", {...})
```

**Incorrect**:
```python
❌ workflow.add_node("NodeType", node_id_var, {...})
❌ workflow.add_node("NodeType", f"node_{i}", {...})
```

**Enforced by**: Code review
**Violation**: Potential runtime issues

### 3. Absolute Imports
MUST use absolute imports for Kailash code.

**Correct**:
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime
from dataflow import DataFlow
```

**Incorrect**:
```python
❌ from .workflow.builder import WorkflowBuilder
❌ from ..runtime import LocalRuntime
```

**Enforced by**: validate-workflow hook
**Violation**: Code review flag

### 4. Environment Variable Loading
MUST load .env before any operation.

**Correct**:
```python
from dotenv import load_dotenv
load_dotenv()  # First line after imports

# Then use environment variables
api_key = os.environ.get("API_KEY")
```

**Enforced by**: session-start hook warning
**Violation**: Runtime errors

### 5. 4-Parameter Node Pattern
MUST use correct parameter order for add_node.

**Correct**:
```python
workflow.add_node(
    "NodeType",      # 1. Type (string)
    "node_id",       # 2. ID (string)
    {"param": "v"},  # 3. Config (dict)
    connections      # 4. Connections (optional)
)
```

## Framework-Specific Rules

### DataFlow
```python
# Primary key MUST be named 'id'
@db.model
class User:
    id: int = field(primary_key=True)  # ✅ Named 'id'

# NEVER manually set timestamps
user = CreateUser(
    name="test"
    # ❌ created_at=datetime.now()  # Auto-managed
)

# Use FLAT params for CreateNode
workflow.add_node("CreateUser", "create", {
    "name": "test",  # ✅ Flat
    # ❌ "data": {"name": "test"}  # Not nested
})

# Use filter + fields for UpdateNode
workflow.add_node("UpdateUser", "update", {
    "filter": {"id": 1},
    "fields": {"name": "new_name"}
})
```

### Nexus
```python
# Register workflows before starting
app = Nexus()
app.register(my_workflow)  # ✅ Register first
app.start()  # Then start

# Use unified sessions for state
session = app.create_session()
# Session maintains state across channels
```

### Kaizen
```python
# Use signature-based patterns
from kaizen.api import Agent

agent = Agent(
    model="gpt-4",
    execution_mode="autonomous"
)

# Register agents in AgentRegistry for scale
from kaizen.core.registry import AgentRegistry
registry = AgentRegistry()
registry.register(agent)
```

## Async vs Sync Runtime

### Use AsyncLocalRuntime for Docker/FastAPI
```python
from kailash.runtime import AsyncLocalRuntime

runtime = AsyncLocalRuntime()
results, run_id = await runtime.execute_workflow_async(
    workflow.build(),
    inputs={}
)
```

### Use LocalRuntime for CLI/Scripts
```python
from kailash.runtime import LocalRuntime

runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())
```

## Exceptions
Pattern exceptions require:
1. Written justification
2. Approval from pattern-expert
3. Documentation in code comments
