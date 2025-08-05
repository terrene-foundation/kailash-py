# Kailash Core SDK v0.9.13 Release Notes

## 🐛 Bug Fixes

### WorkflowBuilder Parameter Validation (Bug 010)
- **Fixed**: Parameter validation now correctly recognizes `auto_map_from` parameters
- **Impact**: Eliminates false positive warnings when using valid parameter mappings
- **File**: `src/kailash/workflow/validation.py`

## 📈 Improvements

### Enhanced Parameter Validation Logic
The WorkflowBuilder now properly validates parameters that use the `auto_map_from` feature:

```python
# Before: Would generate false warnings
workflow.add_node("AsyncSQLDatabaseNode", "query", {
    "connection_string": "postgresql://...",  # Would warn incorrectly
    "query": "SELECT * FROM users"
})

# After: Correctly recognizes auto_map_from alternatives
# No more spurious warnings for valid parameter mappings
```

## 🔧 Technical Details

- Enhanced validation logic to build a complete set of valid parameter names including all `auto_map_from` alternatives
- No breaking changes - fully backward compatible
- Improves developer experience by reducing noise in validation output

## 📦 Installation

```bash
pip install kailash==0.9.13
```

## 🤝 Contributors

- Fixed parameter validation logic for better developer experience
- Maintained 100% backward compatibility

---

*This release focuses on improving the developer experience by eliminating false positive parameter validation warnings.*