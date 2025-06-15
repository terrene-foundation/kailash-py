# Kailash SDK - Development Guide

## 📁 Quick Access
| **SDK Users** | **SDK Contributors** | **Shared** |
|---------------|---------------------|-----------|
| [sdk-users/developer/](sdk-users/developer/) | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) | [shared/mistakes/](shared/mistakes/) |
| [sdk-users/workflows/](sdk-users/workflows/) | [# contrib (removed)/training/](# contrib (removed)/training/) | [tests/](tests/) |
| [examples/](examples/) | [# contrib (removed)/research/](# contrib (removed)/research/) | |

## ⚠️ MUST FOLLOW
1. **SDK-First Development**: Use SDK components, NO custom orchestration
    - ✅ Check [node catalog](sdk-users/nodes/comprehensive-node-catalog.md) before PythonCodeNode
    - ✅ Use `LocalRuntime` (includes async + enterprise features)
    - ✅ Use `WorkflowBuilder.from_dict()` for dynamic workflows
    - 🚨 **NEVER** manual database/FastAPI - use `create_gateway()` from middleware

2. **Real Solutions Only**: Never simplify examples or use mock data
    - ✅ Fix complex examples, delete simple test versions
    - ❌ Mock data to make failing examples pass
    - ✅ Use built-in infrastructure: docker and ollama

3. **Node Development Rules**:
    - ✅ Names end with "Node" (`CSVReaderNode` ✓)
    - ✅ Set attributes BEFORE `super().__init__()`
    - ✅ `get_parameters()` returns `Dict[str, NodeParameter]`

4. **PythonCodeNode Patterns**:
    - ✅ Wrap outputs: `{"result": data}`
    - ✅ Use dot notation: `"result.data"` in connections
    - ✅ Use `.from_function()` for multi-line code

5. **Middleware**: Use `create_gateway()` for production apps
    - ✅ Real-time communication, AI chat, session management included

## ⚡ Critical Patterns
1. **Data Paths**: `get_input_data_path()`, `get_output_data_path()`
2. **Access Control**: `AccessControlManager(strategy="rbac"|"abac"|"hybrid")`
3. **Execution**: Use `.execute()` not `.process()` or `.call()`
4. **Ollama Embeddings**: Extract with `[emb["embedding"] for emb in result["embeddings"]]`
5. **Cyclic Workflows**: Preserve state with `set_cycle_state()`, explicit parameter mapping
6. **WorkflowBuilder**: String-based `add_node("CSVReaderNode", ...)`, 4-param `add_connection()`

## 🔧 Core Nodes (110+ available)
**AI**: LLMAgentNode, MonitoredLLMAgentNode, EmbeddingGeneratorNode, A2AAgentNode, SelfOrganizingAgentNode
**Data**: CSVReaderNode, JSONReaderNode, SQLDatabaseNode, AsyncSQLDatabaseNode, DirectoryReaderNode
**RAG**: 47+ specialized nodes - see [comprehensive guide](sdk-users/developer/20-comprehensive-rag-guide.md)
**API**: HTTPRequestNode, RESTClientNode, OAuth2Node, GraphQLClientNode
**Logic**: SwitchNode, MergeNode, WorkflowNode, ConvergenceCheckerNode
**Auth/Security**: MultiFactorAuthNode, ThreatDetectionNode, AccessControlManager, GDPRComplianceNode
**Middleware**: AgentUIMiddleware, RealtimeMiddleware, APIGateway, AIChatMiddleware
**Full catalog**: [sdk-users/nodes/comprehensive-node-catalog.md](sdk-users/nodes/comprehensive-node-catalog.md)

## 📂 Directory Navigation Convention
**File Naming Standard**:
- **README.md** = Directory index/navigation (what's here, where to go)
- **QUICK_REFERENCE.md** = Hands-on implementation guide (code patterns, quick fixes)
- **Numbered guides** = Detailed topic-specific documentation

## 🏗️ Architecture Decisions

**For app building guidance:** → [sdk-users/decision-matrix.md](sdk-users/decision-matrix.md)

**Before any app implementation:**
1. Enter `sdk-users/` directory to load full architectural guidance
2. Check decision matrix for patterns and trade-offs
3. Reference complete app guide as needed

## 🔗 Quick Links by Need

| **I need to...** | **SDK User** | **SDK Contributor** |
|-------------------|--------------|---------------------|
| **Build a workflow** | [sdk-users/workflows/](sdk-users/workflows/) | - |
| **Build an app** | [apps/APP_DEVELOPMENT_GUIDE.md](apps/APP_DEVELOPMENT_GUIDE.md) | - |
| **Make arch decisions** | [Architecture ADRs](# contrib (removed)/architecture/adr/) | [Architecture ADRs](# contrib (removed)/architecture/adr/) |
| **Fix an error** | [sdk-users/developer/07-troubleshooting.md](sdk-users/developer/07-troubleshooting.md) | [shared/mistakes/](shared/mistakes/) |
| **Find patterns** | [sdk-users/essentials/](sdk-users/essentials/) | - |
| **Learn from workflows** | [sdk-users/workflows/](sdk-users/workflows/) - Production workflows | - |
| **Run tests** | [tests/README.md](tests/README.md) - Test guide | [tests/](tests/) - Full test suite |
| **SDK development** | [examples/](examples/) - Feature validation | - |
| **Train LLMs** | - | [# contrib (removed)/training/](# contrib (removed)/training/) |
| **Design architecture** | - | [# contrib (removed)/architecture/](# contrib (removed)/architecture/) |
| **Version operations** | - | [# contrib (removed)/operations/](# contrib (removed)/operations/) |
| **Track progress** | - | [# contrib (removed)/project/todos/](# contrib (removed)/project/todos/) |

## 📁 Organization Principles
- **Production workflows** → `sdk-users/workflows/` (business value)
- **SDK development** → `examples/` (feature validation)
- **Quality validation** → `tests/` (unit/integration/e2e)
- **Training data** → `# contrib (removed)/training/` (LLM patterns)

## 🎯 Development Workflow
1. **Check todos**: `# contrib (removed)/project/todos/000-master.md`
2. **Plan**: Check ADRs, use `sdk-users/essentials/` for patterns
3. **Implement**: Use node catalog, create tests in `examples/`
4. **Document**: Update todos, add to workflows, align docs

---

**Quick Start**:
- **Building solutions?** → [sdk-users/CLAUDE.md](sdk-users/CLAUDE.md)
- **Developing SDK?** → [# contrib (removed)/CLAUDE.md](# contrib (removed)/CLAUDE.md)
- **Need error help?** → [shared/mistakes/CLAUDE.md](shared/mistakes/CLAUDE.md)
- **New team member?** → [NEW_TEAM_MEMBER.md](NEW_TEAM_MEMBER.md)
