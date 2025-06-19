# Kailash SDK Migration Guides

This directory contains all migration guides for SDK users. These guides help you upgrade your code to use the latest SDK features and architectural improvements.

## 📋 Migration Guides by Version

### v0.6.1 - Parameter Flow Updates
**File**: [v0.6.1-parameter-flow-updates.md](v0.5.1-parameter-flow-updates.md)
- Node construction vs runtime validation separation
- Enhanced parameter flow architecture
- Clear separation between configuration and runtime parameters
- Improved error handling and validation

### v0.5.0 - Architecture Refactoring
**File**: [v0.5.0-architecture-refactoring.md](v0.5.0-architecture-refactoring.md)
- Sync/Async node separation (Node vs AsyncNode)
- Execute/Run API standardization
- WorkflowBuilder API unification
- Resource management with connection pooling
- Parameter resolution optimization with caching

### API to Middleware Migration
**File**: [api-to-middleware-migration.md](api-to-middleware-migration.md)
- Migrate from legacy `kailash.api` and `kailash.mcp` to unified middleware
- Dynamic workflow creation via REST API
- Session-based execution with monitoring
- Real-time communication (WebSocket/SSE)
- AI chat integration

### Auth Consolidation Migration
**File**: [auth-consolidation-migration.md](auth-consolidation-migration.md)
- JWT authentication consolidation
- Resolve circular import issues
- Support for both HS256 and RSA algorithms
- Dependency injection patterns

### Middleware Optimization Patterns
**File**: [middleware-optimization-patterns.md](middleware-optimization-patterns.md)
- Replace custom middleware code with SDK nodes
- Use workflows for multi-step operations
- Leverage enterprise nodes (BatchProcessorNode, DataLineageNode)
- Performance optimization checklist

## 🚀 Quick Start

1. **Identify your current SDK version**:
   ```python
   import kailash
   print(kailash.__version__)
   ```

2. **Read migration guides in order** from your current version to the latest

3. **Test thoroughly** after each migration step

4. **Use the validation tools** provided in each guide

## 📊 Migration Priority

Based on impact and benefits:

1. **High Priority**:
   - v0.5.0 Architecture Refactoring (performance & reliability)
   - Auth Consolidation (security & circular imports)

2. **Medium Priority**:
   - API to Middleware Migration (new features)
   - v0.6.1 Parameter Flow (cleaner code)

3. **Optimization**:
   - Middleware Optimization Patterns (performance)

## 🔧 Common Migration Patterns

### Before Starting Any Migration

```python
# 1. Create a backup branch
git checkout -b migration-backup

# 2. Run existing tests
pytest tests/

# 3. Document current behavior
python -m your_app --version
```

### After Completing Migration

```python
# 1. Run updated tests
pytest tests/

# 2. Verify performance
python -m kailash.tools.benchmark your_workflow

# 3. Update documentation
```

## ❓ Getting Help

- Check the [Troubleshooting Guide](../developer/05-troubleshooting.md)
- Review [Common Mistakes](../validation/common-mistakes.md)
- Open an issue with the `migration` label

## 📅 Deprecation Timeline

| Feature | Deprecated | Removed | Migration Guide |
|---------|------------|---------|-----------------|
| `kailash.api` module | v0.4.0 | v1.0.0 | [API to Middleware](api-to-middleware-migration.md) |
| Auto async detection | v0.5.0 | v1.0.0 | [v0.5.0 Architecture](v0.5.0-architecture-refactoring.md) |
| `KailashJWTAuthManager` | v0.4.5 | v1.0.0 | [Auth Consolidation](auth-consolidation-migration.md) |
| Constructor validation | v0.6.1 | v1.1.0 | [v0.6.1 Parameter Flow](v0.5.1-parameter-flow-updates.md) |

## 🎯 Migration Checklist Template

```markdown
## Migration Checklist for [Your Project]

### Pre-Migration
- [ ] Current SDK version: ____
- [ ] Target SDK version: ____
- [ ] Tests passing: Yes/No
- [ ] Backup created: Yes/No

### Migration Steps
- [ ] Read relevant migration guides
- [ ] Update imports
- [ ] Update node creation patterns
- [ ] Update parameter handling
- [ ] Update error handling
- [ ] Run tests after each major change

### Post-Migration
- [ ] All tests passing
- [ ] Performance verified
- [ ] Documentation updated
- [ ] Team notified
```

---

**Remember**: Migrations can be done incrementally. You don't need to apply all changes at once.
