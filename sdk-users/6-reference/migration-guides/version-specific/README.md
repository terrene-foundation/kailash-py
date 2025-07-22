# Version-Specific Migration Guides

**Purpose**: Step-by-step migration guides for upgrading between SDK versions.

## Available Migrations

### Latest Versions

- **[v0.6.6-infrastructure-enhancements.md](v0.6.6-infrastructure-enhancements.md)** ⭐ **NEW**
  - Enhanced transaction monitoring operations
  - Improved AsyncNode event loop handling
  - New operations: complete_transaction, acquire_resource, complete_operation
  - Success rate calculations and enhanced schemas

- **[v0.6.5-shared-workflow-fix.md](v0.6.5-shared-workflow-fix.md)**
  - AgentUIMiddleware shared workflow execution fix
  - execute_workflow() deprecated in favor of execute()

- **[v0.6.0-to-v0.6.1-migration.md](v0.6.0-to-v0.6.1-migration.md)**
  - Parameter flow architecture improvements
  - Runtime validation separation

- **[v0.5.1-parameter-flow-updates.md](v0.5.1-parameter-flow-updates.md)**
  - Enhanced parameter flow patterns

### Major Architecture Changes

- **[v0.5.0-architecture-refactoring.md](v0.5.0-architecture-refactoring.md)**
  - Sync/Async node separation
  - Major API standardization
  - Resource management overhaul

## Migration Path

1. **Identify current version**: `python -c "import kailash; print(kailash.__version__)"`
2. **Apply migrations in order**: Start from your current version and work up
3. **Test after each step**: Run your test suite between migrations
4. **Update dependencies**: Check for updated requirements

## Quick Reference

| From Version | To Version | Guide | Priority |
|--------------|------------|-------|----------|
| v0.4.x | v0.5.0 | [v0.5.0-architecture-refactoring.md](v0.5.0-architecture-refactoring.md) | HIGH |
| v0.5.0 | v0.5.1 | [v0.5.1-parameter-flow-updates.md](v0.5.1-parameter-flow-updates.md) | MEDIUM |
| v0.6.0 | v0.6.1 | [v0.6.0-to-v0.6.1-migration.md](v0.6.0-to-v0.6.1-migration.md) | MEDIUM |
| v0.6.x | v0.6.5+ | [v0.6.5-shared-workflow-fix.md](v0.6.5-shared-workflow-fix.md) | LOW |
| v0.6.5+ | v0.6.6+ | [v0.6.6-infrastructure-enhancements.md](v0.6.6-infrastructure-enhancements.md) | LOW |

---

**Back to**: [Migration Guides](../README.md)
