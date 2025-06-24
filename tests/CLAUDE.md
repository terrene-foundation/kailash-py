# Test Suite Quick Reference

## 📚 Full Documentation
See **[# contrib (removed)/testing/](../# contrib (removed)/testing/)** for complete testing guidelines.

## 🚀 Quick Commands

```bash
# Run Tier 1 (Unit) - Fast, no dependencies
pytest tests/unit/ -m "not (slow or integration or e2e or requires_docker)"

# Run Tier 2 (Integration) - Component interactions
pytest tests/integration/ -m "not (slow or e2e or requires_docker)"

# Run Tier 3 (E2E) - Full scenarios with Docker
pytest tests/e2e/
```

## 📁 Structure
- `unit/` - Fast isolated tests (Tier 1)
- `integration/` - Component interaction tests (Tier 2)
- `e2e/` - End-to-end scenarios (Tier 3)

## ⚠️ Key Rules
1. **NO test files in root** - Use unit/, integration/, or e2e/
2. **Mirror source structure** - Easy navigation
3. **Use proper markers** - Enable tier execution
