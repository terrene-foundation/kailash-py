# Architectural Migration Guides

**Purpose**: Major architectural pattern migrations and system refactoring guides.

## Available Migrations

### System Architecture Changes

- **[auth-consolidation-migration.md](auth-consolidation-migration.md)**
  - **Impact**: Consolidate JWT authentication components
  - **Benefits**: Resolve circular imports, support multiple algorithms
  - **Complexity**: MEDIUM - Authentication system update

### Performance & Infrastructure

- **[async-sql-to-workflowconnectionpool.md](async-sql-to-workflowconnectionpool.md)**
  - **Impact**: Upgrade to production-grade connection pooling
  - **Benefits**: 10x+ performance improvement, fault tolerance
  - **Complexity**: MEDIUM - Database layer migration

- **[sync-to-async-workflow-builder.md](sync-to-async-workflow-builder.md)** ⭐ **NEW**
  - **Impact**: Adopt async-first workflow patterns
  - **Benefits**: 70%+ code reduction, built-in reliability patterns
  - **Complexity**: HIGH - Workflow architecture overhaul

## Migration Planning

### Pre-Migration Assessment

```python
# Check current architecture
from kailash import __version__
print(f"Current SDK: {__version__}")

# Identify components to migrate
components = {
    "auth": "Using KailashJWTAuthManager?",
    "database": "Using AsyncSQLDatabaseNode?",
    "api": "Using kailash.api module?",
    "workflows": "Using WorkflowBuilder?"
}
```

### Migration Order Recommendations

1. **Start with**: [auth-consolidation-migration.md](auth-consolidation-migration.md) (fixes imports)
2. **Performance**: [async-sql-to-workflowconnectionpool.md](async-sql-to-workflowconnectionpool.md) (database optimization)
3. **Modern patterns**: [sync-to-async-workflow-builder.md](sync-to-async-workflow-builder.md) (workflow improvements)

## Impact Assessment

| Migration | Code Changes | Performance | Features | Risk |
|-----------|--------------|-------------|----------|------|
| **Auth Consolidation** | LOW | None | Security+ | LOW |
| **Database Pool** | MEDIUM | 10x+ | Monitoring+ | MEDIUM |
| **Async Workflows** | HIGH | 2-5x | Patterns+ | MEDIUM |

---

**Back to**: [Migration Guides](../README.md)
