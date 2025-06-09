# Kailash SDK - Development Workflow Guide

## 🎯 Primary Development Workflow

### **Every Session: Check Current Status**
1. **Current Session**: Check `guide/todos/000-master.md` - What's happening NOW
2. **Task Status**: Update todos from "pending" → "in_progress" → "completed"

### **Phase 1: Plan → Research**
- **Research**: `guide/adr/` (architecture), `guide/features/` (patterns)
- **Reference**: `guide/reference/CLAUDE.md` → cheatsheet, validation, patterns
- **Plan**: Clear implementation approach
- **Create & start todos**: Add new tasks from plan → mark "in_progress" in `guide/todos/000-master.md`

### **Phase 2: Implement → Validate → Test**
- **Implement**: Use `guide/reference/cheatsheet/` for copy-paste patterns
- **Validate**: Check `guide/reference/validation/validation-guide.md` for LLM rules
- **Node Selection**: Use `guide/reference/nodes/comprehensive-node-catalog.md`
- **Track mistakes**: In `guide/mistakes/current-session-mistakes.md`
- **Test**: Run tests, debug, learn

### **Phase 3: Document → Update → Release**
- **Update todos**: Mark completed in `guide/todos/000-master.md`
- **Update mistakes**: From current-session → numbered files in `guide/mistakes/`
- **Update patterns**: Add learnings to `guide/reference/cheatsheet/`, `guide/reference/pattern-library/`
- **Update workflows**: Add end-to-end patterns to `guide/reference/workflow-library/`
- **Align docs**: Ensure CLAUDE.md ↔ README.md consistency
- **Release**: Commit → PR

## ⚡ Critical Validation Rules
1. **Node Names**: ALL end with "Node" (`CSVReaderNode` ✓)
2. **Methods**: ALL use snake_case (`add_node()` ✓)
3. **Config vs Runtime**: Config=HOW (static), Runtime=WHAT (data flow)
4. **PythonCodeNode**: Always include `name` parameter first
5. **Cycle Mapping**: Use `mapping={"output": "input"}` for data flow

## 🚀 Quick Code Patterns
```python
# Basic workflow
workflow = Workflow("id", "name")
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
workflow.connect("reader", "writer", mapping={"data": "data"})
runtime.execute(workflow, parameters={})

# PythonCodeNode with cycles
code = "try:\n    count = input_count + 1\nexcept:\n    count = 1\nresult = {'count': count}"
node = PythonCodeNode(name="counter", code=code)
```

## 📁 Quick Directory Access
| I need to... | Go to | Check |
|--------------|-------|-------|
| **Fix an error** | [guide/mistakes/CLAUDE.md](guide/mistakes/CLAUDE.md) | Error lookup table |
| **Find patterns/validation** | [guide/reference/CLAUDE.md](guide/reference/CLAUDE.md) | Cheatsheet, validation, nodes, workflows |
| **Run examples** | `examples/README.md` | Security restrictions & example list |
| **Run tests** | `tests/integration/README.md` | Test commands & troubleshooting |  
| **Frontend work** | `studio/README.md` | React setup & development guide |
| **Architecture decisions** | `guide/adr/README.md` | ADR index & process |

---

**Kailash Python SDK**: AI workflow automation with node-based architecture.