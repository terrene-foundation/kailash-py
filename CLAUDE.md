# Kailash SDK - Development Workflow Guide

## 📁 Quick Directory Access by Role

| **SDK Users** (Building with SDK) | **SDK Contributors** (Developing SDK) | **Shared** (Both Groups) |
|-----------------------------------|--------------------------------------|-------------------------|
| [sdk-users/developer/](sdk-users/developer/) - Build from scratch | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) - ADR, design | [shared/mistakes/](shared/mistakes/) - Error lookup |
| [sdk-users/workflows/](sdk-users/workflows/) - Production workflows | [# contrib (removed)/training/](# contrib (removed)/training/) - LLM training data | [shared/frontend/](shared/frontend/) - UI development |
| [sdk-users/essentials/](sdk-users/essentials/) - Quick patterns | [# contrib (removed)/research/](# contrib (removed)/research/) - LLM research | [shared/prd/](shared/prd/) - Product vision |
| | [examples/feature-tests/](examples/feature-tests/) - Feature validation | |

## ⚡ Critical Validation Rules
1. **Node Names**: ALL end with "Node" (`CSVReaderNode` ✓, `CSVReader` ✗)
2. **PythonCodeNode Outputs**: ALWAYS wrapped in `"result"` key
   - ✅ `{"result": {"data": processed}}` or `{"result": 42}`
   - ❌ Direct returns without "result" wrapper
   - ✅ Connect using: `mapping={"result": "next_param"}`
3. **Data Files**: Use `/data/` structure with path utilities
   - ✅ `get_output_data_path("reports/analysis.json")` → `/data/outputs/reports/analysis.json`
   - ❌ `os.makedirs("outputs")` or hardcoded paths
   - ✅ Import: `from examples.utils.data_paths import get_output_data_path`
4. **PythonCodeNode**: Use `.from_function()` for multi-line code
   - ✅ `PythonCodeNode.from_function(name="processor", func=my_func)`
   - ❌ Inline strings for complex logic (no IDE support)
5. **Import Structure**: Use specific module imports
   - ✅ `from kailash.nodes.data import SQLDatabaseNode`
   - ✅ `from kailash.nodes.api import HTTPRequestNode`
   - ❌ `from kailash.core` (doesn't exist!)
6. **Node Parameters**: Must implement `get_parameters()` returning dict
   - ✅ Returns `Dict[str, NodeParameter]` mapping name→parameter
   - ❌ Never return a list
7. **Database Types**: Auto-convert for JSON serialization
   - ✅ Decimal→float, datetime→ISO string, UUID→string
   - ✅ SQLDatabaseNode now handles this automatically
8. **Access Control**: Single unified interface
   - ✅ `AccessControlManager(strategy="rbac"|"abac"|"hybrid")`
   - ❌ Don't use old EnhancedAccessControlManager
9. **Workflow Resilience**: Built into standard Workflow
   - ✅ `workflow.configure_retry("node_id", max_retries=3)`
   - ✅ `workflow.add_fallback("primary_node", "backup_node")`
   - ❌ No separate ResilientWorkflow class needed
10. **Specialized Nodes First**: Check catalog before using PythonCodeNode
    - ✅ `CSVReaderNode` for CSV files (not pandas in PythonCodeNode)
    - ✅ `HTTPRequestNode` for APIs (not requests library)
    - ✅ `CredentialManagerNode` for secrets (not env vars directly)

## 🔧 Core Node Quick Reference (89+ total)
**AI**: LLMAgentNode, MonitoredLLMAgentNode, EmbeddingGeneratorNode, A2AAgentNode, MCPAgentNode, SelfOrganizingAgentNode
**Data**: CSVReaderNode, JSONReaderNode, SQLDatabaseNode, AsyncSQLDatabaseNode, SharePointGraphReader, SharePointGraphReaderEnhanced, DirectoryReaderNode
**Vector**: AsyncPostgreSQLVectorNode (pgvector similarity search)
**API**: HTTPRequestNode, RESTClientNode, OAuth2Node, GraphQLClientNode
**Logic**: SwitchNode, MergeNode, WorkflowNode, ConvergenceCheckerNode
**Transform**: FilterNode, Map, DataTransformer, HierarchicalChunkerNode
**Admin**: UserManagementNode, RoleManagementNode, PermissionCheckNode, AuditLogNode, SecurityEventNode
**Security**: CredentialManagerNode, AccessControlManager (Unified RBAC/ABAC/Hybrid)
**Code**: PythonCodeNode (use only when no specialized node exists)
**Full catalog**: sdk-users/nodes/comprehensive-node-catalog.md

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
- **Update catalog**: `sdk-users/nodes/comprehensive-node-catalog.md` and compressed list in CLAUDE.md
- **Release**: Commit → PR

## 🤝 Team Collaboration
Team uses Claude Code workflow system. When asked about team work, planning, or assignments, use patterns in `# contrib (removed)/operations/claude-code-workflows/`.

---

**Quick Start**:
- **Building solutions?** → [sdk-users/CLAUDE.md](sdk-users/CLAUDE.md)
- **Developing SDK?** → [# contrib (removed)/CLAUDE.md](# contrib (removed)/CLAUDE.md)
- **Need error help?** → [shared/mistakes/CLAUDE.md](shared/mistakes/CLAUDE.md)
- **New team member?** → [NEW_TEAM_MEMBER.md](NEW_TEAM_MEMBER.md)
