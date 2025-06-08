# Kailash SDK - LLM Workflow Guide

## 🚨 FIRST: Always Check These
1. **CURRENT SESSION**: `guide/todos/000-master.md` - What's happening NOW & immediate priorities
2. **TODO SYSTEM**: `guide/todos/README.md` - How to use the todos system & file navigation
3. **API Reference**: `guide/reference/api/` - Modular API docs by module (workflow, nodes, security)
4. **VALIDATION**: `guide/reference/validation/validation-guide.md` - Critical rules to prevent mistakes
5. **WORKFLOW GUIDE**: `guide/workflows/phases.md` - Full 5-phase process details
6. **MISTAKES GUIDE**: `guide/mistakes/README.md` - Quick reference for documented mistakes and solutions
7. **CHEATSHEET**: `guide/reference/cheatsheet/README.md` - Quick reference organized by topic with focused examples

## 🚀 Development Workflow Phases

### Phase 1: Discovery & Planning
```
PLAN MODE:
1. Check: guide/todos/000-master.md (current session status & immediate priorities)
2. Review: guide/todos/active/ (existing plans & implementation details)
3. Research: guide/adr/, guide/features/, guide/reference/
4. Review: guide/mistakes/README.md for known issues & patterns
5. Output: Architecture plan with deliverables
```

### Phase 2: Implementation & Learning
```
EDIT MODE:
5. Update TODOs → In Progress (in guide/todos/000-master.md)
6. Check implementation details (in guide/todos/active/)
7. Write examples → Debug → Learn
8. If examples fail, do not resort to simplifying it with mock data and new scripts.
9. Reference cheatsheet: guide/reference/cheatsheet/README.md for quick examples
10. Reference mistakes from guide/mistakes/README.md when resolving issues with the examples
11. Implement → Test → Learn more
12. Track all mistakes in: guide/mistakes/current-session-mistakes.md
```

### Phase 3: Mistake Analysis ⚠️ CRITICAL
```
PLAN MODE:
12. List all mistakes from current-session-mistakes.md
13. Identify patterns and root causes
14. Plan which docs need updates
15. Output: Documentation update plan
```

### Phase 4: Documentation Updates
```
EDIT MODE:
16. Update all docstrings to the standard outlined in `guide/instructions/documentation-requirements.md`
17. Update mistakes in guide/mistakes as outlined in `guide/workflows/mistake-tracking.md`
   - /XXX-mistake-name.md (detailed mistake file)
   - README.md (add link to browse by category and index)
   - Then remove the updated mistakes from current-session-mistakes.md
18. Update relevant reference docs in guide/reference/
   - api-registry.yaml
   - node-catalog.md
   - cheatsheet/
   - pattern-library/
   - validation-guide.md
19. Update feature guides with learnings
```

### Phase 5: Final Release
```
EDIT MODE:
20. Run full validation suite
21. Update TODOs → Complete (in guide/todos/000-master.md)
22. Release prep → Commit → PR
```

## 📋 Todo Management System

### Todo Files & Their Purpose:
- **`guide/todos/000-master.md`** - Current session status, immediate priorities, in-progress work
- **`guide/todos/active/`** - Detailed implementation plans for active features
  - `core-features.md` - Core feature implementation details
  - `quality-infrastructure.md` - Infrastructure and quality tasks
- **`guide/todos/completed/`** - Historical session records (001-053.md files)
- **`guide/todos/README.md`** - Instructions on how to use the todo system

### How to Update Todos:
1. **Starting work**: Update status from "pending" → "in_progress" in 000-master.md
2. **During work**: Add implementation notes to relevant active/ files
3. **Completing work**: Update status from "in_progress" → "completed" in 000-master.md
4. **Session end**: Move completed items to session achievements in 000-master.md

### When to Update:
- **ALWAYS** update 000-master.md when changing task status
- **NEVER** edit completed/ files (they're historical records)
- **ADD** details to active/ files as you discover implementation requirements

## Core Rules (MEMORIZE)
1. **ALL node classes end with "Node"**: `CSVReaderNode` ✓, `CSVReader` ✗
2. **ALL methods use snake_case**: `add_node()` ✓, `addNode()` ✗
3. **ALL config keys use underscores**: `file_path` ✓, `filePath` ✗
4. **Workflow execution pattern**: Always use `runtime.execute(workflow, parameters={...})` ✓
5. **Parameter order is STRICT**: Check exact signatures in api-registry.yaml
6. **Docstring examples use doctest format**: `>>> code` ✓, `:: code` ✗
7. **get_parameters() defines ALL node parameters**: Both config AND runtime
8. **Config vs Runtime**: Config=HOW (static), Runtime=WHAT (dynamic data)
9. **Execution inputs**: Use `runtime.execute(workflow, parameters={...})` only
10. **Initial workflow data**: Can use source nodes OR pass via parameters to ANY node
11. **Use Workflow.connect()**: NOT WorkflowBuilder (different API, causes confusion). Be careful not to create accidental cycles!
12. **ASYNC is DEFAULT**: Use async/await patterns wherever possible, especially for I/O operations
13. **Conditional routing**: Use SwitchNode for A→B→C→D→Switch→(B if retry|E if finish) patterns
14. **PythonCodeNode Constructor**: Always include `name` parameter: `PythonCodeNode(name="node_id", code=code)` ✓
15. **PythonCodeNode Code Format**: Use raw statements `value = 10; result = {"value": value}`, not functions ✓
16. **Cycle Connection Mapping**: Always include `mapping={"output": "input"}` for data flow ✓
17. **Convergence Check Format**: Use direct field names `"converged == True"`, not nested paths ✓
18. **PythonCodeNode Exception Handling**: Use bare `except:` clauses, not specific exception types ✓
19. **PythonCodeNode input_types**: When using `input_types`, ALL parameters must be mapped through cycles ✓
20. **Initial Cycle Parameters**: Cycle first iteration uses try/except defaults, not workflow parameters ✓
21. **PythonCodeNode DataFrame Output**: Convert DataFrames with `.to_dict('records')` for JSON serialization ✓
22. **NumPy Type Compatibility**: Check availability with `hasattr(np, 'float128')` for platform-specific types ✓
23. **NumPy Array Serialization**: Convert arrays to lists with `.tolist()` before returning from PythonCodeNode ✓

## Common Pitfalls (Avoid These!)
1. **Config vs Runtime** (#1 issue!): Config=HOW (code, paths), Runtime=WHAT (data)
2. **Cyclic Parameter Mapping**: Use `{"result.count": "count"}` not `{"count": "count"}`
3. **Cyclic Parameter Access**: Always use try/except in PythonCodeNode cycle parameters
4. **Multi-Node Cycles**: Only mark CLOSING edge as `cycle=True`
5. **Safe state access**: `prev_state = cycle_info.get("node_state") or {}`
6. **PythonCodeNode Scope**: Variables injected directly into namespace, no `kwargs.get()` access
7. **Cycle Test Assertions**: Use `>= 1` not `== 3` for iteration counts (cycles may converge early)
8. **Missing Cycle Mapping**: Cycles need explicit `mapping={}` or data won't flow between iterations
9. **PythonCodeNode Execution Environment**: Limited builtins available; use bare except, not `NameError`
10. **Complete Parameter Mapping**: With `input_types`, include ALL parameters (constants + variables) in mappings
11. **DataFrame Index Lost**: Serialization with `.to_dict('records')` loses index - use `.reset_index()` to preserve
12. **NumPy 2.0 Breaking Changes**: `np.string_` → `np.bytes_`, `np.unicode_` → `np.str_`, `np.matrix` deprecated
13. **Platform-Specific NumPy Types**: float128/complex256 not available everywhere - always check with `hasattr()`

📋 **Quick reference guide**:
- **Snippets?** → `guide/reference/cheatsheet/`
- **Patterns?** → `guide/reference/pattern-library/README.md`
- **Validation?** → `guide/reference/validation-guide.md`

## 📁 Context-Optimized Navigation

### For Planning (Phases 1 & 3):
- `guide/todos/000-master.md` - Current state
- `guide/reference/api-registry.yaml` - API specs
- `guide/mistakes/README.md` - Mistakes index & critical patterns
- `guide/features/` - Implementation patterns
- `guide/adr/` - Architecture decisions

### For Implementation (Phase 2):
- `guide/todos/000-master.md` - Update task status
- `guide/todos/active/` - Implementation details
- `guide/reference/cheatsheet/` - Quick code patterns and examples
- `examples/` - Write examples first
- `src/kailash/` - Implementation
- `tests/` - Test coverage
- `guide/sessions/current-mistakes.md` - Track issues
- `guide/workflows/validation-checklist.md` - Validation steps

### For Documentation (Phase 4):
- `guide/mistakes/` - Update mistake logs
- `guide/reference/api/` - Update API reference docs
- `guide/reference/nodes/` - Update node catalog
- `guide/reference/validation/` - Update validation rules
- `guide/features/` - Update feature guides
- `CHANGELOG.md` - Track changes

### For Release (Phase 5):
- `guide/workflows/release-checklist.md` - Release steps
- `releases/` - Release notes
- `docs/` - Sphinx documentation

## 🔄 Learning Loop
Implementation → Mistakes → Analysis → Documentation → Better Implementation

## 📚 Workflow Documentation
- **Complete Process**: `guide/workflows/phases.md` - Detailed 5-phase workflow
- **Mistake Tracking**: `guide/workflows/mistake-tracking.md` - How to capture learnings
- **Validation Steps**: `guide/workflows/validation-checklist.md` - All validation commands
- **Release Process**: `guide/workflows/release-checklist.md` - Release checklist

## Project Context
Kailash Python SDK enables AI Business Coaches to create workflows using a node-based architecture with Python-friendly interfaces.

## Key Reminders
- Track mistakes as they happen
- Clear context between phases
- Do only what's asked
- Validate continuously
