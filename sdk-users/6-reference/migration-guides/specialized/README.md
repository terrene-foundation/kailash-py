# Specialized Migration Guides

**Purpose**: Domain-specific and complex migration patterns for specialized use cases.

## Available Specialized Migrations

### Protocol & Integration Migrations

- **[mcp-comprehensive-migration.md](mcp-comprehensive-migration.md)** ⭐ **COMPREHENSIVE** (1,884 lines)
  - **Scope**: Complete Model Context Protocol migration
  - **Coverage**: REST APIs → MCP, Function Calling → MCP, Plugin Systems → MCP
  - **Includes**: Data migration, authentication, client patterns, testing, rollback
  - **Complexity**: VERY HIGH - Complete system transformation

### Performance & Optimization

- **[middleware-optimization-patterns.md](middleware-optimization-patterns.md)**
  - **Scope**: Replace custom middleware with SDK nodes
  - **Benefits**: Standardized patterns, better performance, reduced complexity
  - **Complexity**: MEDIUM - Code refactoring and optimization

### Phased Migration Patterns

- **[phase2-intelligent-routing-migration.md](phase2-intelligent-routing-migration.md)**
  - **Scope**: Intelligent routing pattern adoption
  - **Benefits**: Advanced workflow routing strategies
  - **Complexity**: HIGH - Routing architecture changes

- **[phase3-production-hardening-migration.md](phase3-production-hardening-migration.md)**
  - **Scope**: Production hardening and reliability patterns
  - **Benefits**: Enterprise-grade reliability improvements
  - **Complexity**: HIGH - Production infrastructure changes

## When to Use Specialized Migrations

### MCP Comprehensive Migration
**Use when**:
- Migrating from REST API architectures
- Adopting Model Context Protocol
- Need complete transformation guidance
- Require testing and rollback strategies

### Middleware Optimization
**Use when**:
- Custom middleware performance issues
- Want to adopt SDK standard patterns
- Need to leverage enterprise nodes
- Refactoring existing middleware

### Phased Migrations
**Use when**:
- Large-scale system transformations
- Need staged rollout approaches
- Production system can't be migrated at once
- Risk mitigation is critical

## Planning Your Specialized Migration

### Assessment Questions

1. **Scope**: How much of your system needs to change?
2. **Timeline**: Can you afford a complete transformation?
3. **Risk tolerance**: How critical is your current system?
4. **Resources**: Do you have dedicated migration time?

### Recommended Approach

```markdown
## Specialized Migration Planning Template

### Current Assessment
- [ ] System architecture documented
- [ ] Migration scope defined
- [ ] Risk assessment completed
- [ ] Rollback plan prepared

### Migration Strategy
- [ ] Phased approach vs complete migration
- [ ] Testing strategy defined
- [ ] Performance benchmarks established
- [ ] Stakeholder communication plan

### Execution Plan
- [ ] Migration guide selected
- [ ] Timeline and milestones defined
- [ ] Monitoring and validation approach
- [ ] Success criteria established
```

## Support & Resources

- **Complex migrations**: Consider consulting support
- **Testing strategies**: See individual guide testing sections
- **Performance validation**: Use built-in benchmarking tools
- **Rollback procedures**: Follow guide-specific rollback instructions

---

**Back to**: [Migration Guides](../README.md)
