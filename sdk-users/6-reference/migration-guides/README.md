# Kailash SDK Migration Guides

**📍 Single Source of Truth**: All migration guides consolidated into organized categories for improved user experience.

This directory contains all migration guides for SDK users. These guides help you upgrade your code to use the latest SDK features and architectural improvements.

## 📁 Organized Migration Categories

### 📅 [version-specific/](version-specific/) - Version Upgrades
**What**: Version-to-version migration guides
**When to use**: Upgrading between SDK versions

- **[v2.1-sql-parameter-flexibility.md](version-specific/v2.1-sql-parameter-flexibility.md)** ⭐ **NEW**
  - SQLDatabaseNode parameter type flexibility (dict and list support)
  - Named parameter syntax recommendations (:param_name format)
  - AsyncSQLDatabaseNode parameter naming clarification (params vs parameters)
  - Improved error handling and validation patterns
  - Fully backward compatible with enhanced developer experience

- **[v0.6.0-to-v0.6.1-migration.md](version-specific/v0.6.0-to-v0.6.1-migration.md)**
  - Node construction vs runtime validation separation
  - Enhanced parameter flow architecture
  - Clear separation between configuration and runtime parameters
  - Improved error handling and validation

- **[v0.5.1-parameter-flow-updates.md](version-specific/v0.5.1-parameter-flow-updates.md)**
  - Parameter flow architecture improvements
  - Enhanced validation patterns

- **[v0.5.0-architecture-refactoring.md](version-specific/v0.5.0-architecture-refactoring.md)**
  - Sync/Async node separation (Node vs AsyncNode)
  - Execute/Run API standardization
  - WorkflowBuilder API unification
  - Resource management with connection pooling
  - Parameter resolution optimization with caching

### 🏗️ [architectural/](architectural/) - System Architecture Changes
**What**: Major architectural migrations and refactoring
**When to use**: Adopting new architectural patterns

- **[api-to-middleware-migration.md](architectural/api-to-middleware-migration.md)**
  - Migrate from legacy `kailash.api` and `kailash.mcp` to unified middleware
  - Dynamic workflow creation via REST API
  - Session-based execution with monitoring
  - Real-time communication (WebSocket/SSE)
  - AI chat integration

- **[auth-consolidation-migration.md](architectural/auth-consolidation-migration.md)**
  - JWT authentication consolidation
  - Resolve circular import issues
  - Support for both HS256 and RSA algorithms
  - Dependency injection patterns

- **[async-sql-to-workflowconnectionpool.md](architectural/async-sql-to-workflowconnectionpool.md)**
  - Migrate from AsyncSQLDatabaseNode to WorkflowConnectionPool
  - Production-grade connection pooling with fault tolerance
  - Health monitoring and automatic recycling
  - Performance improvements (10x+ throughput)
  - Step-by-step migration patterns

- **[sync-to-async-workflow-builder.md](architectural/sync-to-async-workflow-builder.md)** ⭐ **NEW**
  - Migrate from WorkflowBuilder to AsyncWorkflowBuilder
  - Automatic code indentation handling with textwrap.dedent()
  - Built-in async patterns (retry, rate limiting, circuit breaker)
  - Integrated resource management for databases, HTTP, and caches
  - 70%+ code reduction with production-grade reliability

### 🔧 [specialized/](specialized/) - Domain-Specific Migrations
**What**: Specialized migration patterns for specific use cases
**When to use**: Complex domain-specific migrations

- **[mcp-comprehensive-migration.md](specialized/mcp-comprehensive-migration.md)** ⭐ **COMPREHENSIVE** (1,884 lines)
  - Complete Model Context Protocol migration guide
  - Migration from REST APIs, Function Calling, Plugin Systems
  - Data migration, authentication, client migration patterns
  - Testing migration and rollback strategies
  - Step-by-step instructions for various scenarios

- **[middleware-optimization-patterns.md](specialized/middleware-optimization-patterns.md)**
  - Replace custom middleware code with SDK nodes
  - Use workflows for multi-step operations
  - Leverage enterprise nodes (BatchProcessorNode, DataLineageNode)
  - Performance optimization checklist

- **[phase2-intelligent-routing-migration.md](specialized/phase2-intelligent-routing-migration.md)**
  - Intelligent routing pattern migration
  - Advanced workflow routing strategies

- **[phase3-production-hardening-migration.md](specialized/phase3-production-hardening-migration.md)**
  - Production hardening migration patterns
  - Enterprise-grade reliability improvements
## 🚀 Quick Start

1. **Identify your current SDK version**:
   ```python
   import kailash
   print(kailash.__version__)
   ```

2. **Choose your migration category**:
   - **Version upgrade**: Check [version-specific/](version-specific/)
   - **Architecture change**: Check [architectural/](architectural/)
   - **Specialized migration**: Check [specialized/](specialized/)

3. **Read migration guides in order** from your current version to the latest

4. **Test thoroughly** after each migration step

5. **Use the validation tools** provided in each guide

## 📊 Migration Priority

Based on impact and benefits:

1. **High Priority** (Production Impact):
   - [v0.5.0 Architecture Refactoring](version-specific/v0.5.0-architecture-refactoring.md) (performance & reliability)
   - [Auth Consolidation](architectural/auth-consolidation-migration.md) (security & circular imports)
   - [Database Connection Migration](architectural/async-sql-to-workflowconnectionpool.md) (10x+ performance for production apps)
   - [Sync to Async Workflow Builder](architectural/sync-to-async-workflow-builder.md) (70%+ code reduction, production-grade)

2. **Medium Priority** (New Features):
   - [API to Middleware Migration](architectural/api-to-middleware-migration.md) (new features)
   - [v0.6.1 Parameter Flow](version-specific/v0.6.0-to-v0.6.1-migration.md) (cleaner code)

3. **Specialized** (Domain-Specific):
   - [MCP Comprehensive Migration](specialized/mcp-comprehensive-migration.md) (complete MCP transformation)
   - [Middleware Optimization Patterns](specialized/middleware-optimization-patterns.md) (performance)

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
| `kailash.api` module | v0.4.0 | v1.0.0 | [API to Middleware](architectural/api-to-middleware-migration.md) |
| Auto async detection | v0.5.0 | v1.0.0 | [v0.5.0 Architecture](version-specific/v0.5.0-architecture-refactoring.md) |
| `KailashJWTAuthManager` | v0.4.5 | v1.0.0 | [Auth Consolidation](architectural/auth-consolidation-migration.md) |
| Constructor validation | v0.6.1 | v1.1.0 | [v0.6.1 Parameter Flow](version-specific/v0.6.0-to-v0.6.1-migration.md) |

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
