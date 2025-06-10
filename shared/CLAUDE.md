# Shared Resources - Quick Reference

*Resources used by both SDK users and contributors*

## 📁 Shared Content

### **Learning from Mistakes**
- **[mistakes/](mistakes/)** - Comprehensive error documentation (75+ documented mistakes)
  - Common patterns and solutions
  - Error lookup by message
  - Historical learning for both users and contributors
  - Training data for LLM validation

### **Frontend Development**
- **[frontend/](frontend/)** - React/TypeScript frontend resources
  - Architecture and component patterns
  - API integration guides
  - Testing and debugging workflows
  - Styling and UI guidelines

### **Product Requirements**
- **[prd/](prd/)** - Product requirement documents
  - Project structure and vision
  - Feature specifications
  - Roadmap and planning

## 🔍 Quick Error Lookup
| Error Message | File | Quick Fix |
|---------------|------|-----------|
| `NameError: name 'NameError' is not defined` | [067](mistakes/067-phase-6-3-completion-pythoncode-execution-environment.md) | Use bare `except:` |
| `TypeError: PythonCodeNode.__init__() missing 1 required positional argument: 'name'` | [066](mistakes/066-phase-6-3-cycle-test-implementation-mistakes.md) | Add `name` parameter first |
| `TypeError: data is not a valid config parameter` | [053](mistakes/053-confusion-between-configuration-and-runtime-parameters.md) | Use runtime parameters |
| `TypeError: Object of type DataFrame is not JSON serializable` | [068](mistakes/068-pythoncode-dataframe-serialization.md) | Use `.to_dict('records')` |
| `AttributeError: 'Workflow' object has no attribute 'add'` | [056](mistakes/056-inconsistent-connection-apis-between-workflow-and-workflowbuilder.md) | Use `workflow.add_node()` |

## 🎯 Navigation by Role

### **For SDK Users**
- **Mistakes**: Learn from common errors to avoid them
- **Frontend**: If building UI components with Kailash
- **PRD**: Understand product vision and features

### **For SDK Contributors**
- **Mistakes**: Historical context for designing better APIs
- **Frontend**: Contribute to workflow studio and visualizations
- **PRD**: Align development with product requirements

## 🔗 Quick Links
- **Complete mistake index**: [mistakes/README.md](mistakes/README.md)
- **Frontend architecture**: [frontend/README.md](frontend/README.md)
- **Product vision**: [prd/0001-kailash_python_sdk_prd.md](prd/0001-kailash_python_sdk_prd.md)

---

**For SDK usage**: See [../sdk-users/CLAUDE.md](../sdk-users/CLAUDE.md)  
**For SDK development**: See [../# contrib (removed)/CLAUDE.md](../# contrib (removed)/CLAUDE.md)