# Kailash SDK - Development Workflow Guide

## 📁 Quick Directory Access by Role

| **SDK Users** (Building with SDK) | **SDK Contributors** (Developing SDK) | **Shared** (Both Groups) |
|-----------------------------------|--------------------------------------|-------------------------|
| [sdk-users/developer/](sdk-users/developer/) - Build from scratch | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) - ADR, design | [shared/mistakes/](shared/mistakes/) - Error lookup |
| [sdk-users/workflows/](sdk-users/workflows/) - Lift examples | [# contrib (removed)/training/](# contrib (removed)/training/) - LLM training data | [shared/frontend/](shared/frontend/) - UI development |
| [sdk-users/essentials/](sdk-users/essentials/) - Quick patterns | [# contrib (removed)/research/](# contrib (removed)/research/) - LLM research | [shared/prd/](shared/prd/) - Product vision |

## ⚡ Critical Validation Rules
1. **Node Names**: ALL end with "Node" (`CSVReaderNode` ✓)
2. **PythonCodeNode**: Input variables EXCLUDED from outputs!
   - `mapping={"result": "input_data"}` ✓
   - `mapping={"result": "result"}` ✗
3. **Parameter types**: ONLY `str`, `int`, `float`, `bool`, `list`, `dict`, `Any`

## 🚀 Quick Code Patterns
```python
# Basic workflow
workflow = Workflow("id", "name")
workflow.add_node("reader", CSVReaderNode(), file_path="data.csv")
workflow.connect("reader", "writer", mapping={"data": "data"})
runtime.execute(workflow, parameters={})

# PythonCodeNode (correct pattern)
workflow.connect("discovery", "processor", mapping={"result": "input_data"})
processor = PythonCodeNode(name="processor", code="result = {'count': len(input_data)}")
```

## 🔗 Quick Links by Need

| **I need to...** | **SDK User** | **SDK Contributor** |
|-------------------|--------------|---------------------|
| **Build a workflow** | [sdk-users/workflows/](sdk-users/workflows/) | - |
| **Fix an error** | [sdk-users/developer/07-troubleshooting.md](sdk-users/developer/07-troubleshooting.md) | [shared/mistakes/](shared/mistakes/) |
| **Find patterns** | [sdk-users/essentials/](sdk-users/essentials/) | - |
| **Train LLMs** | - | [# contrib (removed)/training/](# contrib (removed)/training/) |
| **Design architecture** | - | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) |
| **Version operations** | - | [# contrib (removed)/operations/](# contrib (removed)/operations/) |
| **Track progress** | - | [# contrib (removed)/project/todos/](# contrib (removed)/project/todos/) |

## 🎯 Primary Development Workflow

### **Every Session: Check Current Status**
1. **Current Session**: Check `# contrib (removed)/project/todos/000-master.md` - What's happening NOW
2. **Task Status**: Update todos from "pending" → "in_progress" → "completed"

### **Phase 1: Plan → Research**
- **Research**: `# contrib (removed)/architecture/adr/` (architecture decisions)
- **Reference**: `sdk-users/` (user patterns) + `# contrib (removed)/` (internal docs)
- **Development**: `sdk-users/developer/` (building with SDK) vs `# contrib (removed)/development/` (SDK development)
- **Plan**: Clear implementation approach
- **Create & start todos**: Add new tasks → mark "in_progress" in `# contrib (removed)/project/todos/`

### **Phase 2: Implement → Validate → Test**
- **Implement**: Use `sdk-users/essentials/` for user patterns
- **Custom Nodes**: `sdk-users/developer/CLAUDE.md` for usage patterns
- **Create Example**: MUST create working example in `examples/` directory
- **Validate**: Check `sdk-users/validation-guide.md` for user rules
- **Node Selection**: Use `sdk-users/nodes/comprehensive-node-catalog.md`
- **Track mistakes**: In `shared/mistakes/current-session-mistakes.md`
- **Test**: Run tests, debug, learn

### **Phase 3: Document → Update → Release**
- **Update todos**: Mark completed in `# contrib (removed)/project/todos/`
- **Update mistakes**: From current-session → numbered files in `shared/mistakes/`
- **Update user patterns**: Add learnings to `sdk-users/essentials/`, `sdk-users/patterns/`
- **Update training data**: Add examples to `# contrib (removed)/training/workflow-examples/`
- **Update workflows**: Add end-to-end patterns to `sdk-users/workflows/`
- **Align docs**: Ensure CLAUDE.md ↔ README.md consistency
- **Release**: Commit → PR

---

**Quick Start**: 
- **Building solutions?** → [sdk-users/CLAUDE.md](sdk-users/CLAUDE.md)
- **Developing SDK?** → [# contrib (removed)/CLAUDE.md](# contrib (removed)/CLAUDE.md)
- **Need error help?** → [shared/mistakes/CLAUDE.md](shared/mistakes/CLAUDE.md)