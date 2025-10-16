# Important Directives 📜
1. Always use kailash SDK with its frameworks to implement.
2. Always use the specialist subagents (nexus-specialist, dataflow-specialist, mcp-specialist, kaizen-specialist) when working with the frameworks.
3. Never attempt to write codes from scratch before checking the frameworks with the specialist subagents.
   - Instead of using direct SQL, SQLAlchemy, Django ORM, always check with the dataflow-specialist on how to do it with the dataflow framework
   - Instead of building your own API gateway or use FastAPI, always check with the nexus-specialist on how to do it with the nexus framework
   - Instead of building your own MCP server/client, always check with the mcp-specialist on how to do it with the mcp_server module inside the core SDK
   - Instead of building your own agentic platform, always check with the kaizen-specialist on how to do it with the kaizen framework

## 🏗️ Documentation

### Core SDK (`sdk-users/`)
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
- **Install**: `pip install kailash-dataflow`
- **Import**: `from dataflow import DataFlow`

### Nexus (`sdk-users/apps/nexus/`)
**Multi-channel platform** built on Core SDK:
- **Purpose**: Deploy workflows as API + CLI + MCP simultaneously
- **Features**: Unified sessions, zero-config platform deployment
- **Usage**: Platform applications requiring multiple access methods
- **Install**: `pip install kailash-nexus`
- **Import**: `from nexus import Nexus`

### Kaizen ('sdk-users/apps/kaizen/')
**AI agent framework** built on Core SDK:
- **Purpose**: Production-ready AI agents with multi-modal processing, multi-agent coordination, and enterprise features built on Kailash SDK
- **Features**: Signature-based programming, BaseAgent architecture, automatic optimization, error handling, audit trails
- **Usage**: Agentic applications requiring robust AI capabilities
- **Install**: `pip install kailash-kaizen`
- **Import**: `from kaizen.* import ...`

### Critical Relationships
- **DataFlow, Nexus, and Kaizen are built ON Core SDK** - they don't replace it
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
  9. Design System Foundation: Creating comprehensive design system FIRST prevented inconsistencies
  10. Institutional Directives: Documented design patterns as mandatory guides for future work
  11. Component Reusability: Building 16 reusable components eliminated redundant work
  12. Responsive-First Design: Building responsive patterns from the start prevented mobile/desktop divergence
  13. Dark Mode Built-In: Supporting dark mode in all components from day 1 avoided retrofitting
  14. Design Token System: Using centralized tokens (colors, spacing, typography) enabled easy theme changes

- **Lessons Learned** 🎓
  1. Documentation Early: Writing guides after implementation is easier
  2. Pattern Consistency: Following same structure across examples reduces errors
  3. Incremental Validation: Verifying tests pass immediately prevents compounding issues
  4. Comprehensive Coverage: Detailed documentation prevents future questions
  5. Design System as Foundation: Create design system BEFORE features to enforce consistency
  6. Mandatory Guides: Institutionalizing design patterns as "must follow" directives prevents drift
  7. Single Import Pattern: Consolidating all design system exports into one file (design_system.dart) simplifies usage
  8. Component Showcase: Building live demo app while developing components catches UX issues early
  9. Deprecation Fixes: Address all deprecations immediately to prevent tech debt accumulation
  10. Real Device Testing: Testing on actual trackpad/touch reveals issues that simulators miss
  11. Pointer Events for Touch: Low-level pointer events (PointerDownEvent, PointerMoveEvent) handle trackpad/touch better than high-level gestures alone
  12. Responsive Testing: Test at all three breakpoints (mobile/tablet/desktop) for every feature

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

## ⚠️ Critical Rules
- ALWAYS: `runtime.execute(workflow.build())`
- NEVER: `workflow.execute(runtime)`
- String-based nodes: `workflow.add_node("NodeName", "id", {})`
- Real infrastructure: NO MOCKING in Tiers 2-3 tests
- **Docker/FastAPI**: Use `AsyncLocalRuntime()` or `WorkflowAPI()` (defaults to async)
- **CLI/Scripts**: Use `LocalRuntime()` for synchronous execution

## 🐳 Docker Deployment
- WorkflowAPI now defaults to AsyncLocalRuntime (async-first, no threads).

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
