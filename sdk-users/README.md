# SDK Users Guide

*Everything you need to build solutions with the Kailash SDK*

## 🚨 Start Here: [CLAUDE.md](CLAUDE.md)
Quick reference with critical rules, common patterns, and navigation guide.

## 🎯 **Critical for Claude Code Users**
- **[cheatsheet/000-claude-code-guide.md](cheatsheet/000-claude-code-guide.md)** - **START HERE** Essential success patterns
- **[cheatsheet/038-integration-mastery.md](cheatsheet/038-integration-mastery.md)** - Complete integration guide
- **[cheatsheet/039-workflow-composition.md](cheatsheet/039-workflow-composition.md)** - Advanced workflow patterns

## 📁 Contents

### **Enterprise & Production**
- **[enterprise/](enterprise/)** - Enterprise-grade patterns and architecture
  - Advanced middleware patterns
  - Multi-tenant session management
  - Production security and monitoring
  - High-scale deployment patterns

- **[production-patterns/](production-patterns/)** - Real app implementations & deployment
  - Proven patterns from actual production apps
  - 15.9x performance optimizations
  - Production deployment configurations
  - Real-world security and monitoring

### **Build from Scratch or Modify**
- **[developer/](developer/)** - Node creation, patterns, troubleshooting
  - Critical PythonCodeNode input exclusion patterns
  - DirectoryReaderNode file discovery
  - Document processing workflows
  - Custom node development guide
  - Advanced troubleshooting

### **Lift Working Examples**
- **[workflows/](workflows/)** - End-to-end use cases ready to copy
  - Quick-start patterns for immediate use
  - Common patterns (data processing, API integration, AI)
  - Industry solutions (healthcare, finance, manufacturing)
  - Production-ready scripts with real data

### **Quick Reference**
- **[essentials/](essentials/)** - Essential patterns and guides
- **[cheatsheet/](cheatsheet/)** - Copy-paste code snippets
  - **NEW: Claude Code specific guides**
  - Installation and basic setup
  - Common node patterns
  - Connection patterns
  - Error handling
- **[migration-guides/](migration-guides/)** - Version upgrade guides
  - Architecture improvements by version
  - Step-by-step migration instructions
  - Breaking changes documentation
  - Security configuration

- **[api/](api/)** - Complete API documentation
  - Method signatures and parameters
  - YAML specifications
  - Usage examples

- **[nodes/](nodes/)** - Comprehensive node catalog
  - 66+ nodes with examples
  - Node selection guide
  - Use case recommendations

- **[patterns/](patterns/)** - Architectural workflow patterns
  - Core workflow patterns
  - Control flow and data processing
  - Integration and deployment patterns
  - Performance and security patterns

- **[templates/](templates/)** - Ready-to-use boilerplate code
  - Basic workflows
  - Custom node templates
  - Integration examples

### **User Features**
- **[features/](features/)** - Feature guides and implementation examples
  - When and how to use each feature
  - Decision guides and best practices
  - Real-world implementation patterns

- **[validation-guide.md](validation-guide.md)** - Critical rules to prevent common errors

## 🎯 Quick Start Paths

### **New to Kailash?**
1. Read [CLAUDE.md](CLAUDE.md) for critical rules
2. Try [workflows/quick-start/](workflows/quick-start/) examples
3. Use [essentials/getting-started/](essentials/getting-started/) patterns
4. Reference [nodes/](nodes/) for available components

### **Building Complex Workflows?**
1. Start with [workflows/common-patterns/](workflows/common-patterns/)
2. Check [patterns/](patterns/) for architectural guidance
3. Use [developer/](developer/) for custom components
4. Reference [api/](api/) for detailed specifications

### **Industry-Specific Solutions?**
1. Browse [workflows/industry-solutions/](workflows/industry-solutions/)
2. Check [features/](features/) for relevant capabilities
3. Use [templates/](templates/) for boilerplate code
4. Customize with [developer/](developer/) patterns

### **Debugging Issues?**
1. Check [developer/07-troubleshooting.md](developer/07-troubleshooting.md)
2. Review [CLAUDE.md](CLAUDE.md) common mistakes
3. Look up errors in [../shared/mistakes/](../shared/mistakes/)
4. Validate with [validation-guide.md](validation-guide.md)

## ⚠️ Critical Knowledge

### **PythonCodeNode Input Exclusion**
Variables passed as inputs are EXCLUDED from outputs!
```python
# SDK Setup for example
from kailash import Workflow
from kailash.runtime import LocalRuntime
from kailash.nodes.data import CSVReaderNode
from kailash.nodes.ai import LLMAgentNode
from kailash.nodes.api import HTTPRequestNode
from kailash.nodes.logic import SwitchNode, MergeNode
from kailash.nodes.code import PythonCodeNode
from kailash.nodes.base import Node, NodeParameter

# Example setup
workflow = Workflow("example", name="Example")
workflow.runtime = LocalRuntime()

# WRONG
workflow = Workflow("example", name="Example")
workflow.  # Method signature

# CORRECT
workflow = Workflow("example", name="Example")
workflow.  # Method signature

```

### **Node Naming Convention**
ALL nodes must end with "Node":
- ✅ `CSVReaderNode`
- ❌ `CSVReader`

### **Parameter Types**
Only use basic types: `str`, `int`, `float`, `bool`, `list`, `dict`, `Any`
- ❌ `List[str]`, `Optional[int]`, `Union[str, int]`

## 📖 Related Resources

- **SDK Development**: [../# contrib (removed)/](../# contrib (removed)/)
- **Shared Resources**: [../shared/](../shared/)
- **Error Lookup**: [../shared/mistakes/CLAUDE.md](../shared/mistakes/CLAUDE.md)

---

*This guide focuses on using the SDK to build solutions. For extending the SDK itself, see [../# contrib (removed)/README.md](../# contrib (removed)/README.md)*
