# Kailash SDK - Development Workflow Guide

## 📁 Quick Directory Access by Role

| **SDK Users** (Building with SDK) | **SDK Contributors** (Developing SDK) | **Shared** (Both Groups) |
|-----------------------------------|--------------------------------------|-------------------------|
| [sdk-users/developer/](sdk-users/developer/) - Build from scratch | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) - ADR, design | [shared/mistakes/](shared/mistakes/) - Error lookup |
| [sdk-users/workflows/](sdk-users/workflows/) - Production workflows | [# contrib (removed)/training/](# contrib (removed)/training/) - LLM training data | [shared/frontend/](shared/frontend/) - UI development |
| [sdk-users/essentials/](sdk-users/essentials/) - Quick patterns | [# contrib (removed)/research/](# contrib (removed)/research/) - LLM research | [shared/prd/](shared/prd/) - Product vision |
| | [examples/feature-tests/](examples/feature-tests/) - Feature validation | |

## ⚡ Critical Validation Rules
1. **Node Names**: ALL end with "Node" (`CSVReaderNode` ✓)
2. **PythonCodeNode**: Input variables EXCLUDED from outputs!
   - `mapping={"result": "input_data"}` ✓
   - `mapping={"result": "result"}` ✗
3. **Parameter types**: ONLY `str`, `int`, `float`, `bool`, `list`, `dict`, `Any`
4. **Node Creation**: Can create without required params (validated at execution)
5. **Data Files**: Use centralized `/data/` structure with utilities from `examples/utils/data_paths.py`
6. **Output Files**: NEVER create `outputs/`, `cycle_analysis_output/` directories!
   - Use `get_output_data_path()` from `examples/utils/data_paths.py`
   - All outputs go to `/data/outputs/` with proper subdirectories
   - ❌ `os.makedirs("outputs")` → ✅ `ensure_output_dir_exists()`
   - ❌ `"outputs/report.json"` → ✅ `get_output_data_path("category/report.json")`
7. **PythonCodeNode Best Practice**: ALWAYS use `.from_function()` for code > 3 lines!
   - ❌ `PythonCodeNode(name="x", code="...100 lines...")` → Inline strings = NO IDE support
   - ✅ `PythonCodeNode.from_function(name="x", func=my_func)` → Full IDE support
   - String code ONLY for: one-liners, dynamic generation, user input
8. **Enhanced MCP Server**: Production-ready features enabled by default
   - ✅ `from kailash.mcp import MCPServer` → Gets caching, metrics, config management
   - ✅ `@server.tool(cache_key="name", cache_ttl=600)` → Automatic caching with TTL
   - ✅ `@server.tool(format_response="markdown")` → LLM-friendly formatting

## 📂 Directory Navigation Convention
**File Naming Standard**:
- **README.md** = Directory index/navigation (what's here, where to go)
- **QUICK_REFERENCE.md** = Hands-on implementation guide (code patterns, quick fixes)
- **Numbered guides** = Detailed topic-specific documentation

**Examples Organization**: All example folders end with `_examples` for easy test runner detection.

**Feature Tests** (`examples/feature_examples/`):
- **nodes/** - Test individual node features
- **workflows/** - Test workflow patterns
- **integrations/** - Test external integrations
- **runtime/** - Test runtime features

**Node Examples** (`examples/node_examples/`):
- Individual node demonstrations and usage patterns

**Integration Examples** (`examples/integration_examples/`):
- External system integration patterns

**Production Workflows** (`sdk-users/workflows/`):
- **by-enterprise/** - Business function workflows
- **by-industry/** - Industry-specific patterns
- **by-pattern/** - Technical implementation patterns

## 🔗 Quick Links by Need

| **I need to...** | **SDK User** | **SDK Contributor** |
|-------------------|--------------|---------------------|
| **Build a workflow** | [sdk-users/workflows/](sdk-users/workflows/) | - |
| **Fix an error** | [sdk-users/developer/07-troubleshooting.md](sdk-users/developer/07-troubleshooting.md) | [shared/mistakes/](shared/mistakes/) |
| **Find patterns** | [sdk-users/essentials/](sdk-users/essentials/) | - |
| **Organize data files** | [Data Consolidation Guide](docs/data-consolidation-guide.md) | - |
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
- **Create & start todos**: Add new tasks → mark "in_progress" in `# contrib (removed)/project/todos/` and write the details in `# contrib (removed)/project/todos/active/`

### **Phase 2: Implement → Validate → Test**
- **Implement**: Use `sdk-users/essentials/` for user patterns
- **Custom Nodes**: `sdk-users/developer/QUICK_REFERENCE.md` for usage patterns
- **Create Feature Test**: Create test in `examples/feature-tests/` appropriate subdirectory
- **Create Business Workflow**: If applicable, add to `sdk-users/workflows/` with business context
- **Validate**: Check `sdk-users/validation-guide.md` for user rules
- **Node Selection**: Use `sdk-users/nodes/comprehensive-node-catalog.md`
- **Track mistakes**: In `shared/mistakes/current-session-mistakes.md`
- **Test**: Run tests, debug, learn
- **Test Examples**: Run `python scripts/test-all-examples.py` to validate all examples

### **Phase 3: Document → Update → Release**
- **Update todos**: Mark completed in `# contrib (removed)/project/todos/` and move to `# contrib (removed)/project/todos/completed/`
- **Update mistakes**: From current-session → numbered files in `shared/mistakes/`
- **Update user patterns**: Add learnings to `sdk-users/essentials/`, `sdk-users/patterns/`
- **Update training data**: Add examples to `# contrib (removed)/training/workflow-examples/`
- **Update workflows**: Add end-to-end patterns to `sdk-users/workflows/`
- **Align docs**: Ensure CLAUDE.md ↔ README.md consistency
- **Release**: Commit → PR

## 🤝 Team Collaboration
Team uses Claude Code workflow system. When asked about team work, planning, or assignments, use patterns in `# contrib (removed)/operations/claude-code-workflows/`.

---

**Quick Start**:
- **Building solutions?** → [sdk-users/CLAUDE.md](sdk-users/CLAUDE.md)
- **Developing SDK?** → [# contrib (removed)/CLAUDE.md](# contrib (removed)/CLAUDE.md)
- **Need error help?** → [shared/mistakes/CLAUDE.md](shared/mistakes/CLAUDE.md)
- **New team member?** → [NEW_TEAM_MEMBER.md](NEW_TEAM_MEMBER.md)
