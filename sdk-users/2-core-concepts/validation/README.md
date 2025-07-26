# Validation Guide - API Usage Patterns

*Critical rules and patterns for successful Kailash SDK usage*

## 🎯 **Quick Start**
- **[Critical Rules](critical-rules.md)** - Must-follow patterns for success
- **[Common Mistakes](common-mistakes.md)** - What to avoid and how to fix
- **[API Reference](api-reference.md)** - Method signatures and patterns
- **[Migration Guides](../migration-guides/)** - Version upgrades and breaking changes

## 📁 **Validation Sections**

### **For Immediate Success**
1. **[Critical Rules](critical-rules.md)** - 5 essential rules for using Kailash SDK
   - Method names and signatures
   - Node class naming conventions
   - Parameter order and types
   - Import paths
   - Configuration patterns

2. **[Common Mistakes](common-mistakes.md)** - Error prevention and solutions
   - Validation checklist
   - Real examples with fixes
   - Error patterns to avoid
   - Debugging techniques

### **For API Mastery**
3. **[API Reference](api-reference.md)** - Complete method reference
   - Workflow methods
   - Node configuration patterns
   - Parameter structures
   - Execution patterns

4. **[Advanced Patterns](advanced-patterns.md)** - Complex usage scenarios
   - Cyclic workflows
   - Parameter flow patterns
   - Runtime vs configuration
   - WorkflowBuilder patterns

### **For Migration & Updates**
5. **[Migration Guides](../migration-guides/)** - Version-specific migration guides
   - Architecture improvements by version
   - Step-by-step migration instructions
   - Breaking changes documentation
   - Compatibility information

## 🏆 **Production Quality Standards (v0.5.0)**

**Kailash SDK has achieved "best production quality" testing standards**:
- ✅ **100% Core Test Pass Rate**: 4/4 durable gateway tests PASSING
- ✅ **Docker Infrastructure**: Real PostgreSQL, Ollama AI, Redis, MongoDB
- ✅ **AI/LLM Integration**: Ollama llama3.2:3b model with business workflows
- ✅ **Real-World E2E**: Complete business journey validation
- ✅ **Production Readiness**: Comprehensive error handling and recovery

**Testing Infrastructure**: See [developer/06-testing-production-quality.md](../developer/06-testing-production-quality.md)

## 🚀 **Quick Validation**
```python
# Use this to validate your patterns
from kailash.validation import validate_workflow_pattern

# Check if your code follows best practices
is_valid = validate_workflow_pattern(your_workflow_code)
if not is_valid:
    print("Check the critical rules and common mistakes guides")

# For production testing validation
pytest tests/integration/test_durable_gateway_simple.py -v
```

## 🔗 **Related Resources**
- **[Cheatsheet](../cheatsheet/)** - Quick code snippets
- **[Developer Guide](../developer/)** - Comprehensive development patterns
- **[Claude Code Guide](../cheatsheet/000-claude-code-guide.md)** - Special guide for Claude Code

## 📋 **Quick Reference Card**

### ✅ **Always Do**
- Use exact method names: `workflow.add_node()`, `workflow.add_connection("source", "result", "target", "input")`
- Include "Node" suffix: `CSVReaderNode`, `HTTPRequestNode`
- Use keyword arguments: `# mapping removed)`
- Use runtime for execution: `runtime.execute(workflow.build())`

### ❌ **Never Do**
- Use camelCase: `addNode()`, `connectNodes()`
- Missing "Node" suffix: `CSVReader`, `HTTPRequest`
- Wrong parameter order: `workflow.add_connection("source", "result", "target", "input")  # Fixed complex pattern`
- Skip validation
- Wrong execution pattern: `runtime.execute(workflow.build(), runtime)`

---

**Start with [Critical Rules](critical-rules.md) for immediate success!**
