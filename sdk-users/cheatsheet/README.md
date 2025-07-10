# Kailash SDK Cheatsheet Index

**Version**: 0.6.3 | **Last Updated**: 2025-07-03

Quick reference guides organized by topic. Each file contains focused, actionable code snippets and patterns.

## 📁 Cheatsheet Files

### 🎯 **Critical Guides for Claude Code**
| File | Topic | Description |
|------|-------|-------------|
| **[000-claude-code-guide](000-claude-code-guide.md)** | **Claude Code Mastery** | **Essential patterns for Claude Code success** |
| **[025-mcp-integration](025-mcp-integration.md)** | **🚀 MCP Integration** | **Model Context Protocol - Enable AI tool usage** |
| **[050-validation-testing-patterns](050-validation-testing-patterns.md)** | **🧪 Validation & Testing** | **NEW: Test-driven convergence & comprehensive validation** |
| **[038-integration-mastery](038-integration-mastery.md)** | **Integration Patterns** | **Complete guide for all integration types** |
| **[039-workflow-composition](039-workflow-composition.md)** | **Workflow Composition** | **Advanced workflow building and data flow** |

### 📋 **Core Fundamentals**
| File | Topic | Description |
|------|-------|-------------|
| [001-installation](001-installation.md) | Installation | Package installation instructions |
| [002-basic-imports](002-basic-imports.md) | Basic Imports | Essential imports for workflow development |
| [003-quick-workflow-creation](003-quick-workflow-creation.md) | Quick Workflow Creation | Fast workflow setup patterns |
| [004-common-node-patterns](004-common-node-patterns.md) | Common Node Patterns | Frequently used node configurations |
| [005-connection-patterns](005-connection-patterns.md) | Connection Patterns | Node connection and data flow patterns |
| [006-execution-options](006-execution-options.md) | Execution Options | Workflow execution and parameter handling |
| [007-error-handling](007-error-handling.md) | Error Handling | Error handling and validation patterns |
| [008-security-configuration](008-security-configuration.md) | Security Configuration | Security setup and safe operations |
| [009-export-workflows](009-export-workflows.md) | Export Workflows | Workflow export and serialization |
| [010-visualization](010-visualization.md) | Visualization | Workflow visualization and diagrams |
| [011-custom-node-creation](011-custom-node-creation.md) | Custom Node Creation | Creating custom nodes from scratch |
| [012-common-workflow-patterns](012-common-workflow-patterns.md) | Common Workflow Patterns | Complete workflow examples |
| [016-environment-variables](016-environment-variables.md) | Environment Variables | Configuration and secrets management |
| [017-quick-tips](017-quick-tips.md) | Quick Tips | Essential rules and best practices |
| [018-common-mistakes-to-avoid](018-common-mistakes-to-avoid.md) | Common Mistakes to Avoid | What not to do with examples |

### 🔌 **Integration & Enterprise**
| File | Topic | Description |
|------|-------|-------------|
| [013-sharepoint-integration](013-sharepoint-integration.md) | SharePoint Integration | SharePoint connectivity patterns |
| [014-access-control-multi-tenancy](014-access-control-multi-tenancy.md) | Access Control & Multi-Tenancy | Security and user management |
| [015-workflow-as-rest-api](015-workflow-as-rest-api.md) | Workflow as REST API | API exposure patterns |

### 🔄 **Cyclic Workflows**
| File | Topic | Description |
|------|-------|-------------|
| [019-cyclic-workflows-basics](019-cyclic-workflows-basics.md) | Cyclic Workflows Basics | Basic cycle setup, parameter mapping, convergence |
| [020-switchnode-conditional-routing](020-switchnode-conditional-routing.md) | SwitchNode Conditional Routing | SwitchNode patterns, field mapping for cycles ⚠️ |
| [021-cycle-aware-nodes](021-cycle-aware-nodes.md) | Cycle-Aware Nodes | CycleAwareNode, ConvergenceCheckerNode patterns |
| [022-cycle-debugging-troubleshooting](022-cycle-debugging-troubleshooting.md) | Cycle Debugging & Troubleshooting | Common issues, debugging, error handling |
| [027-cycle-aware-testing-patterns](027-cycle-aware-testing-patterns.md) | Cycle-Aware Testing Patterns | Testing patterns for cyclic workflows and nodes |
| [030-cycle-state-persistence-patterns](030-cycle-state-persistence-patterns.md) | Cycle State Persistence | Handling cycle state persistence and fallback patterns |
| [032-cycle-scenario-patterns](032-cycle-scenario-patterns.md) | Cycle Scenario Patterns | Real-world patterns: ETL retry, API polling, batch processing |
| [044-multi-path-conditional-cycle-patterns](044-multi-path-conditional-cycle-patterns.md) | Multi-Path Conditional Cycles | Complex workflows with multiple conditional routing paths |

### 🤖 **AI/Agent Coordination**
| File | Topic | Description |
|------|-------|-------------|
| **[025-mcp-integration](025-mcp-integration.md)** | **🚀 MCP Integration** | **Enable AI agents to use external tools via MCP** |
| [023-a2a-agent-coordination](023-a2a-agent-coordination.md) | A2A Agent Coordination | A2A coordination patterns and workflows |
| [024-self-organizing-agents](024-self-organizing-agents.md) | Self-Organizing Agents | Self-organizing agent pool patterns |
| **[045-ollama-integration-patterns](045-ollama-integration-patterns.md)** | **Ollama Local LLMs** | **Production-ready Ollama integration patterns** |

### ⚡ **Advanced Patterns**
| File | Topic | Description |
|------|-------|-------------|
| [026-performance-optimization](026-performance-optimization.md) | Performance Optimization | Memory management, cycle optimization, debugging |
| [028-developer-tools-advanced](028-developer-tools-advanced.md) | Advanced Developer Tools | CycleDebugger, CycleProfiler, CycleAnalyzer (Phase 5.2) |
| [029-pythoncode-data-science-patterns](029-pythoncode-data-science-patterns.md) | PythonCodeNode Data Science | DataFrame processing, NumPy arrays, ML workflows |
| [031-pythoncode-best-practices](031-pythoncode-best-practices.md) | PythonCodeNode Best Practices | Advanced patterns and optimization |
| [033-workflow-design-process](033-workflow-design-process.md) | Workflow Design Process | Systematic approach to workflow architecture |
| [034-data-integration-patterns](034-data-integration-patterns.md) | Data Integration Patterns | Multi-source data normalization and merging |
| [035-production-readiness](035-production-readiness.md) | Production Readiness | Deployment checklist and monitoring patterns |
| **[046-resilience-patterns](046-resilience-patterns.md)** | **🛡️ Resilience Patterns** | **Circuit breakers, bulkhead isolation, health monitoring** |

### 🔧 **Enhanced Features**
| File | Topic | Description |
|------|-------|-------------|
| [036-node-initialization-patterns](036-node-initialization-patterns.md) | Node Initialization Patterns | Proper node setup and configuration |
| [037-cyclic-workflow-patterns](037-cyclic-workflow-patterns.md) | Cyclic Workflow Patterns | Advanced cycle patterns and optimization |
| [038-integration-mastery](038-integration-mastery.md) | Integration Mastery | Complete guide for all integration types |
| [039-workflow-composition](039-workflow-composition.md) | Workflow Composition | Advanced workflow building and data flow |
| [040-enterprise-mcp-workflows](040-enterprise-mcp-workflows.md) | Enterprise MCP Workflows | Production-ready MCP patterns with compliance |
| [041-choosing-the-right-node](041-choosing-the-right-node.md) | Choosing the Right Node | Node selection and optimization strategies |
| [042-directoryreader-file-discovery](042-directoryreader-file-discovery.md) | DirectoryReaderNode File Discovery | Dynamic file discovery and metadata extraction |
| [043-datatransformer-bug-workarounds](043-datatransformer-bug-workarounds.md) | DataTransformer Bug Workarounds | Bug detection and mitigation patterns |
| [044-multi-path-conditional-cycle-patterns](044-multi-path-conditional-cycle-patterns.md) | Multi-Path Conditional Cycles | Complex workflows with multiple conditional routing paths |
| [045-ollama-integration-patterns](045-ollama-integration-patterns.md) | Ollama Local LLMs | Production-ready Ollama integration patterns |
| **[047-asyncsql-enterprise-patterns](047-asyncsql-enterprise-patterns.md)** | **🚀 AsyncSQL Enterprise** | **Production async SQL with transactions & optimistic locking** |
| **[048-transaction-monitoring](048-transaction-monitoring.md)** | **📊 Transaction Monitoring** | **Enterprise monitoring: performance metrics, deadlock detection, anomaly analysis** |
| **[050-validation-testing-patterns](050-validation-testing-patterns.md)** | **🧪 Validation & Testing** | **NEW: Comprehensive validation framework with test-driven convergence** |

## 🔗 Related Resources

- **[Pattern Library](../patterns/README.md)** - Complete workflow patterns and architectural guidance
- **[Validation Guide](../validation-guide.md)** - API rules and correct usage patterns
- **[API Registry](../api-registry.yaml)** - Full API specifications
- **[Node Catalog](../node-catalog.md)** - All 66 available nodes with parameters
- **[Templates](../templates/)** - Ready-to-use code templates

## 🚀 Quick Start

### For Claude Code Users (Recommended Path)
1. **START HERE** → [000-claude-code-guide](000-claude-code-guide.md) - Essential patterns for success
2. **AI + Tools?** → [025-mcp-integration](025-mcp-integration.md) - Enable AI to use external tools
3. **Integration work?** → [038-integration-mastery](038-integration-mastery.md) - All integration patterns
4. **Complex workflows?** → [039-workflow-composition](039-workflow-composition.md) - Advanced composition
5. **Debugging issues?** → [018-common-mistakes-to-avoid](018-common-mistakes-to-avoid.md) - What to avoid

### For MCP (Model Context Protocol) Users
1. **Quick Start** → [025-mcp-integration](025-mcp-integration.md) - Complete MCP reference
2. **Examples** → [../examples/mcp/](../examples/mcp/) - Ready-to-run MCP examples
3. **Patterns** → [../patterns/12-mcp-patterns.md](../patterns/12-mcp-patterns.md) - Production patterns
4. **Guide** → [../guides/mcp-quickstart.md](../guides/mcp-quickstart.md) - Beginner's guide

### For General Users
1. **New to Kailash?** Start with [001-installation](001-installation.md) and [002-basic-imports](002-basic-imports.md)
2. **Building workflows?** See [003-quick-workflow-creation](003-quick-workflow-creation.md) and [004-common-node-patterns](004-common-node-patterns.md)
3. **Need examples?** Check [012-common-workflow-patterns](012-common-workflow-patterns.md)

## 💡 Usage Tips

- Each file is self-contained with working code examples
- Copy-paste code snippets directly into your projects
- All examples follow current best practices and conventions
- Files are organized from basic to advanced topics

---
*For comprehensive documentation, see the main [docs/](../../docs/) directory*
