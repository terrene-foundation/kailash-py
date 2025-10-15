# Kailash SDK

## 🏗️ Architecture Overview

### Core SDK (`src/kailash/`)
**Foundational building blocks** for workflow automation:
- **Purpose**: Custom workflows, fine-grained control, integrations
- **Components**: WorkflowBuilder, LocalRuntime, 110+ nodes, MCP integration
- **Usage**: Direct workflow construction with full programmatic control
- **Install**: `pip install kailash`

### DataFlow (`sdk-users/apps/dataflow/`)
**Zero-config database framework** built on Core SDK:
- **Purpose**: Database operations with automatic model-to-node generation
- **Features**: @db.model decorator generates 9 nodes per model automatically. DataFlow IS NOT AN ORM!
- **Usage**: Database-first applications with enterprise features
- **Install**: `pip install kailash[dataflow]` or `pip install kailash-dataflow`

### Nexus (`sdk-users/apps/nexus/`)
**Multi-channel platform** built on Core SDK:
- **Purpose**: Deploy workflows as API + CLI + MCP simultaneously
- **Features**: Unified sessions, zero-config platform deployment
- **Usage**: Platform applications requiring multiple access methods
- **Install**: `pip install kailash[nexus]` or `pip install kailash-nexus`

### Critical Relationships
- **DataFlow and Nexus are built ON Core SDK** - they don't replace it
- **Framework choice affects development patterns** - different approaches for each
- **All use the same underlying workflow execution** - `runtime.execute(workflow.build())`

## 🎯 Specialized Subagents

### Analysis & Planning
- **ultrathink-analyst** → Deep failure analysis, complexity assessment
- **requirements-analyst** → Requirements breakdown, ADR creation
- **sdk-navigator** → Find patterns before coding, resolve errors during development
- **framework-advisor** → Choose Core SDK, DataFlow, or Nexus; coordinates with specialists

### Framework Implementation
- **nexus-specialist** → Multi-channel platform implementation (API/CLI/MCP)
- **dataflow-specialist** → Database operations with auto-generated nodes. String IDs preserved, multi-instance isolation, deferred schema ops (PostgreSQL + SQLite)

### Core Implementation
- **pattern-expert** → Workflow patterns, nodes, parameters
- **tdd-implementer** → Test-first development
- **intermediate-reviewer** → Review after todos and implementation
- **gold-standards-validator** → Compliance checking

### Testing & Validation
- **testing-specialist** → 3-tier strategy with real infrastructure
- **documentation-validator** → Test code examples, ensure accuracy

### Release & Operations
- **todo-manager** → Task management and project tracking
- **mcp-specialist** → MCP server implementation and integration
- **git-release-specialist** → Git workflows, CI validation, releases

### Success Factors
- **What Worked Well** ✅
  1. Systematic Task Completion - Finishing each task completely before moving on
  2. Test-First Development: Writing all tests before implementation prevented bugs
  3. Comprehensive Testing: Catching issues early with comprehensive tests
  4. Real Infrastructure Testing - NO MOCKING policy found real-world issues
  5. Evidence-Based Tracking: Clear audit trail with file:line references made progress clear
  6. Comprehensive Documentation: Guides provide clear path for users and prevent future support questions
  7. Subagent Specialization - Right agent for each task type
  8. Manual Verification: Running all examples caught integration issues

- **Lessons Learned** 🎓
  1. Documentation Early: Writing guides after implementation is easier
  2. Pattern Consistency: Following same structure across examples reduces errors
  3. Incremental Validation: Verifying tests pass immediately prevents compounding issues
  4. Comprehensive Coverage: Detailed documentation prevents future questions

## ⚡ Essential Pattern (All Frameworks)

### For Docker/FastAPI Deployment (RECOMMENDED)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import AsyncLocalRuntime  # Docker-optimized runtime

workflow = WorkflowBuilder()
workflow.add_node("NodeName", "id", {"param": "value"})  # String-based
runtime = AsyncLocalRuntime()  # Async-first, no threading
results = await runtime.execute_workflow_async(workflow.build(), inputs={})
```

### For CLI/Scripts (Sync Contexts)
```python
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime import LocalRuntime

workflow = WorkflowBuilder()
workflow.add_node("NodeName", "id", {"param": "value"})  # String-based
runtime = LocalRuntime()
results, run_id = runtime.execute(workflow.build())  # ALWAYS .build()
```

### Auto-Detection (Simplest)
```python
from kailash.runtime import get_runtime

# Automatically selects AsyncLocalRuntime for Docker/FastAPI,
# LocalRuntime for CLI/scripts
runtime = get_runtime()  # Defaults to "async" context
```

## 🚨 Emergency Fixes
- **"Missing required inputs"** → Use sdk-navigator for common-mistakes.md solutions
- **Parameter issues** → Use pattern-expert for 3-method parameter guide
- **Test failures** → Use testing-specialist for real infrastructure setup
- **DataFlow errors** → Use dataflow-specialist for database debugging (PostgreSQL + SQLite)
- **String ID issues** → DataFlow preserves string IDs - no forced int conversion
- **Multi-instance conflicts** → Each DataFlow instance maintains separate context
- **Nexus platform issues** → Use nexus-specialist for multi-channel troubleshooting
- **Framework selection** → Use framework-advisor to coordinate appropriate specialists
- **Mock provider issues** → ✅ FIXED (2025-10-03): All providers use registry consistently, no hardcoded paths
- **Docker workflows hang** → ✅ FIXED (2025-10-15 v0.9.24): WorkflowAPI now uses AsyncLocalRuntime by default, eliminating double-threading deadlock

## ⚠️ Critical Rules
- ALWAYS: `runtime.execute(workflow.build())`
- NEVER: `workflow.execute(runtime)`
- String-based nodes: `workflow.add_node("NodeName", "id", {})`
- Real infrastructure: NO MOCKING in Tiers 2-3 tests
- **Docker/FastAPI**: Use `AsyncLocalRuntime()` or `WorkflowAPI()` (defaults to async)
- **CLI/Scripts**: Use `LocalRuntime()` for synchronous execution

## 🐳 Docker Deployment (v0.9.24+)

### Critical Fix: Runtime Selection
**Problem**: Workflows hung indefinitely in Docker due to double-threading deadlock.
**Solution**: WorkflowAPI now defaults to AsyncLocalRuntime (async-first, no threads).

### WorkflowAPI (Recommended for Docker)
```python
from kailash.api.workflow_api import WorkflowAPI

# WorkflowAPI automatically uses AsyncLocalRuntime
api = WorkflowAPI(my_workflow)  # Docker-optimized by default
api.run(port=8000)  # No hanging, 10-100x faster
```

### Manual Runtime Selection
```python
from kailash.runtime import AsyncLocalRuntime, LocalRuntime

# For Docker/FastAPI (async contexts)
runtime = AsyncLocalRuntime()

# For CLI/scripts (sync contexts)
runtime = LocalRuntime()

# Or use helper
from kailash.runtime import get_runtime
runtime = get_runtime("async")  # or "sync"
```

### Why This Matters
- **Before (LocalRuntime in Docker)**: `asyncio.to_thread()` → Thread #1 → `_execute_sync()` → Thread #2 → **DEADLOCK**
- **After (AsyncLocalRuntime)**: Native async execution → No threads → **10-100x faster**

### Backward Compatibility
Existing code still works! Explicitly pass `LocalRuntime()` if needed:
```python
from kailash.runtime import LocalRuntime
api = WorkflowAPI(workflow, runtime=LocalRuntime())  # Explicit sync runtime
```
