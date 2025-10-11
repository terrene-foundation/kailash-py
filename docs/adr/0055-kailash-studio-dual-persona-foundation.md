# ADR-0055: Kailash Studio Dual-Persona Shared Foundation

## Status
Proposed

## Context

### Problem Statement

Kailash Studio is being designed to serve TWO distinct user personas with fundamentally different workflow preferences:

**Sarah - Marketing Manager (No-Code Persona)**:
- Primary interface: Visual canvas (drag-drop)
- Workflow source of truth: Canvas JSON (Studio-managed, database-stored)
- Interaction model: UI-driven (forms, buttons, visual feedback)
- Success metric: Build workflow in < 15 minutes without code

**Alex - Software Engineer (Code-First Persona)**:
- Primary interface: Python code editor
- Workflow source of truth: Python files (Git-managed, version controlled)
- Interaction model: Code-driven (type, compile, debug)
- Success metric: Write workflow in < 10 minutes with full SDK power

### Current Architecture Challenge

The initial web app implementation (canvas-first) optimizes perfectly for Sarah but EXCLUDES Alex entirely:

```
Canvas JSON Only Approach (Current):
┌──────────────────────────────────────────────────┐
│ Sarah's Workflow Flow:                           │
│ 1. Drag nodes in canvas (React Flow)             │
│ 2. Configure via forms (auto-generated)          │
│ 3. Save → JSON stored in database                │
│ 4. Execute → Backend reads JSON                  │
│ 5. Deploy → Nexus reads JSON                     │
│ ✅ Works perfectly for Sarah                     │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│ Alex's Workflow Flow (NOT SUPPORTED):            │
│ 1. Write Python file                             │
│ 2. ??? How to visualize in Studio? ❌            │
│ 3. ??? How to debug visually? ❌                 │
│ 4. ??? How to deploy via UI? ❌                  │
│ 5. Fallback: Pure SDK (no Studio benefits)      │
│ ❌ No Studio integration for developers          │
└──────────────────────────────────────────────────┘
```

**Problem**: Canvas JSON is the ONLY workflow representation, forcing developers into a no-code workflow that is unnatural for their skillset.

**Evidence**:
- `apps/kailash-studio/DUAL_PERSONA_ARCHITECTURE_ANALYSIS.md:59-78` - Canvas-first excludes developers
- `apps/kailash-studio/user-scenarios/02-customer-feedback-analysis-developer-vscode.md:1-698` - Developer workflow analysis

### Business Requirements

1. **Equal First-Class Support**: Both Sarah (no-code) and Alex (code-first) must have optimal experiences
2. **Component Reusability**: Maximize shared code between web app and VS Code extension
3. **Bidirectional Workflows**: Support Canvas JSON → Python and Python → Canvas JSON conversions
4. **Version Control**: Enable Git-friendly workflows for developers
5. **60-65% Code Sharing**: Achieve significant reusability to reduce maintenance burden

### Technical Constraints

1. **Existing SDK Patterns**: Must not recreate WorkflowBuilder patterns from `src/kailash/workflow/builder.py`
2. **React Flow Integration**: Web app uses React Flow for canvas visualization
3. **VS Code Extension**: Must support TypeScript webviews with shared backend
4. **Backend Services**: Execution, discovery, and deployment services must remain source-agnostic

---

## Decision

### Workflow-as-Data Abstraction Layer

We will implement a **universal WorkflowDefinition format** that serves as an intermediate representation between Canvas JSON (Sarah) and Python files (Alex).

```
Abstraction Layer Architecture:
┌─────────────────────────────────────────────────────────┐
│ WorkflowDefinition (Intermediate Representation)        │
│ • Nodes: [{ id, type, parameters, position }]          │
│ • Edges: [{ source, target, handles }]                 │
│ • Metadata: { version, author, tags }                  │
└─────────────────────────────────────────────────────────┘
          ▲                                    ▲
          │                                    │
    ┌─────┴────────┐                  ┌───────┴──────┐
    │              │                  │              │
┌───▼────┐    ┌───▼────┐        ┌───▼────┐    ┌───▼────┐
│ Canvas │◄──►│ JSON   │        │ Python │◄──►│ AST    │
│  UI    │    │ File   │        │  File  │    │ Parser │
└────────┘    └────────┘        └────────┘    └────────┘
   Sarah's        │                Alex's         │
   Source         │                Source         │
                  │                               │
                  └───────────┬───────────────────┘
                              ▼
                    Backend Services (Shared)
                    • Execution
                    • Discovery
                    • Deployment
```

**Key Principle**: WorkflowDefinition is **source-agnostic**:
- Sarah creates via canvas → Converts to WorkflowDefinition → Can export as Python
- Alex writes Python → Parses to WorkflowDefinition → Can visualize in canvas
- Both representations are **equal first-class citizens**

---

## Phase 0 Implementation Components

### Component 1: WorkflowDefinition Type System

**TypeScript Types** (`packages/studio-core/src/types/WorkflowDefinition.ts`):
```typescript
export interface WorkflowNode {
  id: string;
  type: string;
  parameters: Record<string, any>;
  position?: { x: number; y: number };
}

export interface WorkflowEdge {
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
}

export interface WorkflowMetadata {
  version: string;
  author?: string;
  description?: string;
  tags?: string[];
  source: "canvas" | "python";
  created_at?: string;
  updated_at?: string;
}

export interface WorkflowDefinition {
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  metadata: WorkflowMetadata;
}
```

**Python Dataclasses** (`backend/src/kailash_studio/types/workflow_definition.py`):
```python
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Literal

@dataclass
class WorkflowNode:
    id: str
    type: str
    parameters: Dict[str, Any]
    position: Optional[Dict[str, float]] = None

@dataclass
class WorkflowEdge:
    source: str
    target: str
    source_handle: Optional[str] = None
    target_handle: Optional[str] = None

@dataclass
class WorkflowMetadata:
    version: str
    author: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    source: Literal["canvas", "python"] = "canvas"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class WorkflowDefinition:
    nodes: List[WorkflowNode]
    edges: List[WorkflowEdge]
    metadata: WorkflowMetadata
```

**Effort**: 4 hours

---

### Component 2: Python Workflow Parser (AST-Based)

**Strategy**: Extract `WorkflowBuilder` patterns from Python files without executing code.

**Parser Class** (`backend/src/kailash_studio/sdk/workflow_parser.py`):
```python
import ast
from typing import Dict, Any
from kailash_studio.types.workflow_definition import (
    WorkflowDefinition, WorkflowNode, WorkflowEdge, WorkflowMetadata
)

class PythonWorkflowParser:
    """Parse Python workflow files using AST to extract WorkflowDefinition."""

    def parse_file(self, file_path: str) -> WorkflowDefinition:
        """Parse Python file and return WorkflowDefinition."""
        with open(file_path, 'r') as f:
            code = f.read()
        return self.parse_string(code)

    def parse_string(self, code: str) -> WorkflowDefinition:
        """Parse Python code string and extract workflow structure."""
        tree = ast.parse(code)

        nodes = []
        edges = []
        metadata = WorkflowMetadata(version="1.0.0", source="python")

        # Walk AST to find WorkflowBuilder patterns
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Detect: workflow.add_node("NodeType", "id", {...})
                if self._is_add_node_call(node):
                    workflow_node = self._extract_node(node)
                    nodes.append(workflow_node)

                # Detect: workflow.add_connection("source", "target", ...)
                elif self._is_add_connection_call(node):
                    edge = self._extract_edge(node)
                    edges.append(edge)

        # Extract docstrings for description
        metadata.description = self._extract_docstring(tree)

        return WorkflowDefinition(nodes=nodes, edges=edges, metadata=metadata)

    def _is_add_node_call(self, node: ast.Call) -> bool:
        """Check if AST node is workflow.add_node() call."""
        return (
            isinstance(node.func, ast.Attribute) and
            node.func.attr == "add_node"
        )

    def _extract_node(self, call: ast.Call) -> WorkflowNode:
        """Extract WorkflowNode from add_node() AST call."""
        # Extract: add_node(type, id, parameters)
        args = call.args
        node_type = ast.literal_eval(args[0])  # String literal
        node_id = ast.literal_eval(args[1])     # String literal
        parameters = ast.literal_eval(args[2]) if len(args) > 2 else {}

        return WorkflowNode(
            id=node_id,
            type=node_type,
            parameters=parameters
        )

    def _is_add_connection_call(self, node: ast.Call) -> bool:
        """Check if AST node is workflow.add_connection() call."""
        return (
            isinstance(node.func, ast.Attribute) and
            node.func.attr == "add_connection"
        )

    def _extract_edge(self, call: ast.Call) -> WorkflowEdge:
        """Extract WorkflowEdge from add_connection() AST call."""
        args = call.args
        source = ast.literal_eval(args[0])
        target = ast.literal_eval(args[1])

        return WorkflowEdge(source=source, target=target)

    def _extract_docstring(self, tree: ast.AST) -> Optional[str]:
        """Extract module docstring as workflow description."""
        return ast.get_docstring(tree)
```

**API Endpoint** (`backend/src/kailash_studio/api_routes.py`):
```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()
parser = PythonWorkflowParser()

class ParseRequest(BaseModel):
    code: str

@router.post("/api/workflows/parse")
async def parse_python_workflow(request: ParseRequest):
    """Parse Python code and return WorkflowDefinition JSON."""
    try:
        workflow_def = parser.parse_string(request.code)
        return workflow_def
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Parse error: {str(e)}")
```

**Effort**: 12 hours

**Evidence**:
- `src/kailash/workflow/builder.py:1-350` - WorkflowBuilder patterns to extract
- `apps/kailash-studio/IMPLEMENTATION_ROADMAP_DETAILED_TODOS.md:70-122` - Parser implementation tasks

---

### Component 3: Python Code Generator

**Strategy**: Convert WorkflowDefinition to executable Python code using Jinja2 templates.

**Generator Class** (`backend/src/kailash_studio/sdk/code_generator.py`):
```python
from jinja2 import Template
from kailash_studio.types.workflow_definition import WorkflowDefinition

class PythonCodeGenerator:
    """Generate Python code from WorkflowDefinition."""

    TEMPLATE = """
\"\"\"{{ metadata.description or 'Generated workflow' }}\"\"\"
from kailash.workflow.builder import WorkflowBuilder
from kailash.runtime.local import LocalRuntime

def build_workflow():
    workflow = WorkflowBuilder()

    # Add nodes
    {% for node in nodes %}
    workflow.add_node("{{ node.type }}", "{{ node.id }}", {{ node.parameters | tojson }})
    {% endfor %}

    # Add connections
    {% for edge in edges %}
    workflow.add_connection("{{ edge.source }}", "{{ edge.target }}")
    {% endfor %}

    return workflow

if __name__ == "__main__":
    workflow = build_workflow()
    runtime = LocalRuntime()
    results, run_id = runtime.execute(workflow.build())
    print(f"Execution completed: {run_id}")
    print(results)
"""

    def generate(self, workflow_def: WorkflowDefinition) -> str:
        """Generate Python code from WorkflowDefinition."""
        template = Template(self.TEMPLATE)
        code = template.render(
            nodes=workflow_def.nodes,
            edges=workflow_def.edges,
            metadata=workflow_def.metadata
        )

        # Format with black
        try:
            import black
            code = black.format_str(code, mode=black.Mode())
        except ImportError:
            pass  # black is optional

        return code
```

**API Endpoint**:
```python
@router.post("/api/workflows/generate")
async def generate_python_code(workflow_def: WorkflowDefinition):
    """Generate Python code from WorkflowDefinition."""
    try:
        generator = PythonCodeGenerator()
        code = generator.generate(workflow_def)
        return {"code": code}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Generation error: {str(e)}")
```

**Effort**: 4 hours

---

## Consequences

### Positive

1. **60-65% Component Reusability Achieved**:
   - Backend services: 100% shared (execution, discovery, DataFlow)
   - Canvas package: 90% shared (mode-aware design)
   - Properties panel: 60% shared (different modes for Sarah vs Alex)
   - Overall code sharing: 60-65%

2. **Both Personas Equal First-Class Citizens**:
   - Sarah: Canvas JSON → WorkflowDefinition → Python export
   - Alex: Python file → WorkflowDefinition → Canvas visualization
   - Neither persona is forced into unnatural workflow

3. **Git-Friendly Developer Workflows**:
   - Python files as source of truth (not JSON diffs)
   - Native Git branches, PRs, code review
   - Merge conflicts resolved in code (not JSON)

4. **Bidirectional Sync Enabled**:
   - Canvas edits → Code updates (VS Code extension)
   - Code edits → Canvas updates (visual debugging)
   - Both directions preserve semantics

5. **22% Time Savings**:
   - Without dual-persona: ~200 hours (separate implementations)
   - With shared foundation: ~156 hours (22% savings)
   - Maintenance burden reduced by 40%

### Negative

1. **Additional Complexity (20 hours)**:
   - WorkflowDefinition types (4h)
   - Python parser (12h)
   - Code generator (4h)
   - Trade-off accepted for long-term maintainability

2. **Parser Limitations**:
   - AST parsing supports ~80% of common patterns
   - Dynamic parameters may not parse correctly
   - Complex decorators may be missed
   - Mitigation: Show warning "Edit in code" for complex workflows

3. **Sync Challenges**:
   - Concurrent edits (code and canvas) may conflict
   - Mitigation: Last-write-wins with undo support
   - Source of truth per persona (Sarah: canvas, Alex: code)

4. **Bundle Size Consideration**:
   - React Flow may be heavy for VS Code webviews
   - Mitigation: Lazy-load canvas, fallback to ASCII visualization
   - Target: < 1MB gzipped for webview bundle

---

## Alternatives Considered

### Alternative 1: Canvas JSON Only (Single-Source)

**Approach**: Keep current canvas-first architecture, no Python file support.

**Pros**:
- Simple: One source of truth
- Works perfectly for Sarah
- Zero additional implementation time

**Cons**:
- ❌ Excludes Alex entirely (developers forced into no-code)
- ❌ Not Git-friendly (JSON diffs hard to review)
- ❌ Limits Studio adoption to non-technical users only
- ❌ Developers bypass Studio, use pure SDK (Studio irrelevant)

**Why Rejected**: Fails to serve 50% of target audience (developers).

**Evidence**:
- `apps/kailash-studio/DUAL_PERSONA_ARCHITECTURE_ANALYSIS.md:176-183` - Canvas-only analysis

---

### Alternative 2: Python Code Only (Code-First)

**Approach**: Python files as ONLY workflow representation, no visual canvas.

**Pros**:
- Works perfectly for Alex
- Git-friendly (code review, version control)
- Simple: One source of truth

**Cons**:
- ❌ Excludes Sarah entirely (requires coding skills)
- ❌ No visual workflow builder
- ❌ Limits Studio to developers only
- ❌ Kaizen's no-code vision not achieved

**Why Rejected**: Fails to serve no-code persona, contradicts Studio's mission.

**Evidence**:
- `apps/kailash-studio/DUAL_PERSONA_ARCHITECTURE_ANALYSIS.md:184-189` - Python-only analysis

---

### Alternative 3: Separate Implementations (No Sharing)

**Approach**: Build web app and VS Code extension independently.

**Pros**:
- Optimized for each platform
- No abstraction layer complexity
- Independent release cycles

**Cons**:
- ❌ Duplicate code (~60% overlap wasted)
- ❌ Double maintenance burden
- ❌ Bug fixes must be applied twice
- ❌ 200 hours effort (vs 156 hours with sharing)

**Why Rejected**:
- 28% more implementation time (200h vs 156h)
- 40% more maintenance code
- Violates DRY principle

**Evidence**:
- `apps/kailash-studio/DUAL_PERSONA_ARCHITECTURE_ANALYSIS.md:456-536` - Effort comparison

---

## Implementation Plan

### Phase 0: Shared Foundation (20 hours) - BLOCKING

**Goal**: Build abstraction layer before persona-specific features.

**Tasks**:
1. **WorkflowDefinition Types** (4h):
   - TypeScript: `packages/studio-core/src/types/WorkflowDefinition.ts`
   - Python: `backend/src/kailash_studio/types/workflow_definition.py`
   - JSON Schema: `schemas/workflow-definition.schema.json`
   - Validation: Zod (TypeScript) + Pydantic (Python)

2. **Python Workflow Parser** (12h):
   - AST parser class: `backend/src/kailash_studio/sdk/workflow_parser.py`
   - API endpoint: `POST /api/workflows/parse`
   - Tests: 20 test cases (common + edge cases)
   - Support: 80% of WorkflowBuilder patterns

3. **Python Code Generator** (4h):
   - Generator class: `backend/src/kailash_studio/sdk/code_generator.py`
   - Jinja2 template: `templates/workflow_template.py.j2`
   - API endpoint: `POST /api/workflows/generate`
   - Formatting: Black integration
   - Round-trip test: JSON → Python → JSON (verify identical)

**Deliverable**: Universal workflow representation supporting both personas.

**Evidence**:
- `apps/kailash-studio/IMPLEMENTATION_ROADMAP_DETAILED_TODOS.md:28-164` - Phase 0 detailed todos

---

### Phase 1A: No-Code MVP - Sarah (44 hours)

**Depends On**: Phase 0 complete

**Tasks**:
1. Kaizen Agent Integration (10h)
2. Shared Canvas Package (8h)
3. Auto-Form Properties Panel (14h)
4. Execution UI - Web App (9h)
5. Template Integration (3h)

**Outcome**: Sarah can execute customer feedback scenario end-to-end (90% complete).

**Evidence**:
- `apps/kailash-studio/IMPLEMENTATION_ROADMAP_DETAILED_TODOS.md:166-413` - Phase 1A todos
- `apps/kailash-studio/user-scenarios/01-customer-feedback-analysis-no-code.md` - Sarah's scenario

---

### Phase 1B: Developer MVP - Alex (52 hours)

**Depends On**: Phase 0 + Shared Canvas Package (Phase 1A.2)

**Tasks**:
1. Python Parser Integration (4h)
2. Canvas Webview - Readonly Mode (8h)
3. Bidirectional Sync Engine (16h)
4. Code Lens Provider (8h)
5. Quick-Edit Properties Panel (6h)
6. Inline Results Decorator (6h)
7. Debug Console Integration (4h)

**Outcome**: Alex can write code, visualize, and debug workflows (90% complete).

**Evidence**:
- `apps/kailash-studio/IMPLEMENTATION_ROADMAP_DETAILED_TODOS.md:415-690` - Phase 1B todos
- `apps/kailash-studio/user-scenarios/02-customer-feedback-analysis-developer-vscode.md` - Alex's scenario

---

### Phase 2: Shared Enhancements (40 hours)

**Depends On**: Phase 1A + Phase 1B

**Tasks**:
1. Real-Time Progress Monitoring (8h)
2. Nexus Deployment UI (16h)
3. Advanced Parameter Validation (6h)
4. Template Export/Import (6h)
5. Error Handling Improvements (4h)

**Outcome**: Production-ready for both personas (100% scenario completion).

**Evidence**:
- `apps/kailash-studio/IMPLEMENTATION_ROADMAP_DETAILED_TODOS.md:692-897` - Phase 2 todos

---

## Integration Points

### Kailash SDK Integration

**DO NOT Recreate**:
- WorkflowBuilder patterns: `src/kailash/workflow/builder.py:1-350`
- LocalRuntime execution: `src/kailash/runtime/local.py:1-400`
- Node signatures: `src/kailash/nodes/` (110+ nodes)

**Parser Must Extract**:
- `workflow.add_node()` calls → WorkflowNode objects
- `workflow.add_connection()` calls → WorkflowEdge objects
- Node parameters → Preserve SDK 3-method parameter pattern

**Generator Must Produce**:
- Valid WorkflowBuilder code
- Executable with `runtime.execute(workflow.build())`
- PEP-8 compliant (Black formatted)

---

### React Flow Integration

**Canvas Package** (`packages/studio-canvas/`):
```typescript
export interface WorkflowCanvasProps {
  mode: "interactive" | "readonly";  // Interactive: Sarah, Readonly: Alex
  workflow: WorkflowDefinition;
  onNodeClick?: (nodeId: string) => void;
  onConnect?: (edge: WorkflowEdge) => void;
}

export const WorkflowCanvas: React.FC<WorkflowCanvasProps> = ({
  mode, workflow, onNodeClick, onConnect
}) => {
  const editable = mode === "interactive";

  return (
    <ReactFlow
      nodes={convertToReactFlowNodes(workflow.nodes)}
      edges={convertToReactFlowEdges(workflow.edges)}
      nodesDraggable={editable}
      nodesConnectable={editable}
      onNodeClick={handleNodeClick}
      onConnect={editable ? onConnect : undefined}
    />
  );
};
```

**Reusability**:
- Web App: `mode="interactive"` (full editing)
- VS Code: `mode="readonly"` (visualization only)
- 90% code sharing achieved

---

### FastAPI Backend Integration

**Parser/Generator Endpoints**:
```python
# backend/src/kailash_studio/api_routes.py

@app.post("/api/workflows/parse")
async def parse_python_workflow(request: ParseRequest):
    """Parse Python code → WorkflowDefinition."""
    workflow_def = parser.parse_string(request.code)
    return workflow_def

@app.post("/api/workflows/generate")
async def generate_python_code(workflow_def: WorkflowDefinition):
    """Generate Python code from WorkflowDefinition."""
    code = generator.generate(workflow_def)
    return {"code": code}
```

**Shared with**:
- Execution service: `POST /api/workflows/execute` (accepts WorkflowDefinition)
- Discovery service: `GET /api/nodes` (parameter schemas for forms)
- Deployment service: `POST /api/deployments` (Nexus configuration)

---

## Success Criteria

### Phase 0 Completion Checklist

- [ ] WorkflowDefinition types implemented (TypeScript + Python)
- [ ] JSON Schema validation working
- [ ] Python parser extracts nodes + edges from `.py` files
- [ ] Parser handles 80%+ of WorkflowBuilder patterns
- [ ] Code generator produces executable Python code
- [ ] Round-trip test passes: JSON → Python → JSON (identical)
- [ ] API endpoints functional: `/api/workflows/parse`, `/api/workflows/generate`
- [ ] Unit tests: 20+ test cases covering common + edge cases

### Component Reusability Metrics

**Target**: 60-65% code sharing

**Measurement**:
- Backend services: 100% shared (execution, discovery, DataFlow, Kaizen)
- Canvas package: 90% shared (mode-aware design)
- Properties panel: 60% shared (dual-mode: forms vs quick-edit)
- Execution UI: 50% shared (different rendering, shared logic)

**Evidence**:
- `apps/kailash-studio/DUAL_PERSONA_ARCHITECTURE_ANALYSIS.md:123-169` - Component reusability matrix

### Scenario Completion Rates

**Target**: 90% after Phase 0 + Phase 1A/1B

**Sarah's Scenario** (No-Code):
- Load customer feedback template ✅
- Configure 5 nodes via auto-generated forms ✅
- Execute workflow with visual progress ✅
- View results in ResultsPanel ✅
- Deploy to Nexus API (Phase 2) ⏳

**Alex's Scenario** (Code-First):
- Write Python workflow file ✅
- Visualize in canvas (VS Code webview) ✅
- Edit code → Canvas auto-updates ✅
- Execute with inline results ✅
- Deploy via generated Dockerfile (Phase 2) ⏳

**Evidence**:
- `apps/kailash-studio/PHASE_5_SCENARIO_VALIDATION_SUMMARY.md:461-500` - Scenario completion analysis

---

## References

### Planning Documents

1. **DUAL_PERSONA_ARCHITECTURE_ANALYSIS.md** (`apps/kailash-studio/`)
   - Lines 1-668: Dual-persona comparison, architectural decisions
   - Lines 89-121: Workflow-as-Data abstraction layer diagram
   - Lines 123-169: Component reusability matrix (60-65% sharing)
   - Lines 359-383: Phase 0 implementation roadmap

2. **IMPLEMENTATION_ROADMAP_DETAILED_TODOS.md** (`apps/kailash-studio/`)
   - Lines 28-164: Phase 0 detailed tasks (20 hours)
   - Lines 166-413: Phase 1A tasks (Sarah - 44 hours)
   - Lines 415-690: Phase 1B tasks (Alex - 52 hours)
   - Lines 692-897: Phase 2 shared enhancements (40 hours)

3. **PHASE_5_SCENARIO_VALIDATION_SUMMARY.md** (`apps/kailash-studio/`)
   - Lines 1-1153: Executive summary, all findings
   - Lines 461-500: Scenario completion readiness analysis
   - Lines 728-756: Component reusability impact (156h vs 200h)

### User Scenarios

4. **user-scenarios/01-customer-feedback-analysis-no-code.md**
   - Lines 1-698: Sarah's step-by-step journey (no-code persona)
   - Lines 52-74: Template loading (requires WorkflowDefinition)
   - Lines 174-222: Node configuration (requires parameter schemas)

5. **user-scenarios/02-customer-feedback-analysis-developer-vscode.md**
   - Lines 1-698: Alex's code-first workflow (developer persona)
   - Lines 82-142: Python workflow visualization (requires parser)
   - Lines 197-254: Bidirectional sync (requires generator)

### Existing SDK Code

6. **src/kailash/workflow/builder.py**
   - Lines 1-350: WorkflowBuilder patterns to extract
   - Lines 50-120: `add_node()` method signatures
   - Lines 150-200: `add_connection()` method signatures

7. **src/kailash/runtime/local.py**
   - Lines 1-400: LocalRuntime execution patterns
   - Lines 100-150: `runtime.execute(workflow.build())` pattern

---

## Conclusion

Building a shared WorkflowDefinition abstraction layer (Phase 0) BEFORE implementing persona-specific features enables:

1. **60-65% component reusability** (saves 44 hours = 22% time)
2. **Equal first-class support** for both Sarah (no-code) and Alex (code-first)
3. **Bidirectional workflows** (Canvas JSON ↔ Python files)
4. **Git-friendly developer workflows** (Python as source of truth)
5. **Long-term maintainability** (40% less code to maintain)

This architectural decision is **critical** because it determines whether Kailash Studio can successfully serve both personas or must choose one at the expense of the other.

**Recommendation**: Accept this proposal and implement Phase 0 (20 hours) as the foundation for all subsequent development.

---

**Author**: Kailash Architecture Team
**Date**: 2025-10-06
**Last Updated**: 2025-10-06
**Related ADRs**:
- ADR-0050: Kailash Studio Visual Workflow Platform
- Future ADR: Bidirectional Sync Engine Architecture (Phase 1B)
