# Shared Resources

*Resources used by both SDK users and contributors*

## 🚨 Start Here: [CLAUDE.md](CLAUDE.md)
Quick reference for shared resources and error lookup.

## 📁 Contents

### **Learning from Mistakes**
- **[mistakes/](mistakes/)** - Comprehensive error documentation
  - **75+ documented mistakes** with solutions
  - **Error lookup by message** for quick resolution
  - **Historical learning** patterns for both users and contributors
  - **Training data** for LLM validation and improvement
  - **Common patterns** that apply across all SDK usage

### **Frontend Development**
- **[frontend/](frontend/)** - React/TypeScript resources for UI development
  - **Architecture guides** for component organization
  - **API integration** patterns for connecting frontend to workflows
  - **Testing strategies** for UI components
  - **Debugging workflows** for frontend issues
  - **Styling guidelines** and component patterns

### **Product Requirements**
- **[prd/](prd/)** - Product requirement documents and vision
  - **Project structure** and architectural vision
  - **Feature specifications** and roadmap planning
  - **Strategic direction** for SDK development

## 🎯 Usage by Role

### **For SDK Users**
The shared resources help SDK users by providing:

- **Error Resolution**: Quick lookup for common issues in `mistakes/`
- **UI Development**: Frontend patterns if building applications with Kailash
- **Product Understanding**: Context about SDK capabilities and vision

**Most Useful for Users**:
- [mistakes/CLAUDE.md](mistakes/CLAUDE.md) - Quick error lookup
- [frontend/README.md](frontend/README.md) - UI integration patterns

### **For SDK Contributors**
The shared resources help SDK contributors by providing:

- **Historical Context**: Understanding past mistakes to design better APIs
- **Frontend Architecture**: Contributing to workflow studio and visualizations
- **Product Alignment**: Ensuring development matches product vision

**Most Useful for Contributors**:
- [mistakes/README.md](mistakes/README.md) - Complete mistake analysis
- [frontend/architecture.md](frontend/architecture.md) - System architecture
- [prd/0001-kailash_python_sdk_prd.md](prd/0001-kailash_python_sdk_prd.md) - Product vision

## 🔍 Quick Error Lookup

| Error Message | Mistake File | Quick Fix |
|---------------|--------------|-----------|
| `Required output 'result' not provided` | [075](mistakes/075-pythoncode-input-variable-exclusion.md) | Map to different variable name |
| `TypeError: PythonCodeNode.__init__() missing 1 required positional argument: 'name'` | [066](mistakes/066-phase-6-3-cycle-test-implementation-mistakes.md) | Add `name` parameter first |
| `Object of type DataFrame is not JSON serializable` | [068](mistakes/068-pythoncode-dataframe-serialization.md) | Use `.to_dict('records')` |
| `'list' object has no attribute 'get'` | [071](mistakes/071-base-node-comprehensive-fixes.md) | DataTransformer dict bug |
| `NameError: name 'data' is not defined` | [Multiple](mistakes/) | Check node output mappings |

## 📊 Mistake Categories

The mistake database is organized by patterns:

- **001-020**: Configuration and runtime parameter confusion
- **021-040**: Test and validation issues
- **041-060**: Async and performance problems
- **061-075**: Advanced patterns (cycles, nodes, serialization)

## 🔗 Navigation Links

- **Complete error index**: [mistakes/README.md](mistakes/README.md)
- **Error lookup hub**: [mistakes/CLAUDE.md](mistakes/CLAUDE.md)
- **Frontend guide**: [frontend/README.md](frontend/README.md)
- **Product vision**: [prd/0001-kailash_python_sdk_prd.md](prd/0001-kailash_python_sdk_prd.md)

## 🤝 Contributing to Shared Resources

### **Adding New Mistakes**
1. Use the [template](mistakes/template.md)
2. Follow numbering convention
3. Include both problem and solution
4. Add to the error lookup table

### **Frontend Improvements**
1. Follow architecture in [frontend/architecture.md](frontend/architecture.md)
2. Update component documentation
3. Test integration patterns

### **Product Feedback**
1. Reference current PRD
2. Propose changes with clear rationale
3. Consider impact on both users and contributors

---

**For SDK usage**: [../sdk-users/README.md](../sdk-users/README.md)
**For SDK development**: [../# contrib (removed)/README.md](../# contrib (removed)/README.md)
