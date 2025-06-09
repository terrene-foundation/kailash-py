# Error Lookup Hub

## 🔍 Quick Error Lookup
| Error Message | File | Quick Fix |
|---------------|------|-----------|
| `NameError: name 'NameError' is not defined` | [067](067-phase-6-3-completion-pythoncode-execution-environment.md) | Use bare `except:` |
| `TypeError: PythonCodeNode.__init__() missing 1 required positional argument: 'name'` | [066](066-phase-6-3-cycle-test-implementation-mistakes.md) | Add `name` parameter first |
| `TypeError: data is not a valid config parameter` | [053](053-confusion-between-configuration-and-runtime-parameters.md) | Use runtime parameters |
| `TypeError: Object of type DataFrame is not JSON serializable` | [068](068-pythoncode-dataframe-serialization.md) | Use `.to_dict('records')` |
| `AttributeError: 'Workflow' object has no attribute 'add'` | [056](056-inconsistent-connection-apis-between-workflow-and-workflowbuilder.md) | Use `workflow.add_node()` |

## ⚡ Browse All Mistakes
- **Complete Index**: [README.md](README.md) - 73+ documented mistakes
- **Search**: Use Ctrl+F with error message above

## 📝 Add New Mistake
Use [template.md](template.md) with next sequential number
