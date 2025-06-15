# Architecture Decision Matrix - Quick Reference

## 🚀 Quick Decision Lookup

### Workflow Construction Pattern

| Situation | Pattern | Why | Reference |
|-----------|---------|-----|-----------|
| Simple CRUD app | **Inline** | Direct config access, rapid development | [ADR-0045](0045-workflow-construction-patterns.md) |
| Enterprise app with reusable patterns | **Class-based** | Inheritance, formal structure | [ADR-0045](0045-workflow-construction-patterns.md) |
| Mixed complexity (recommended) | **Hybrid** | Best of both approaches | [ADR-0045](0045-workflow-construction-patterns.md) |
| Prototyping/unsure | **Hybrid** | Safe default, can refactor later | [ADR-0045](0045-workflow-construction-patterns.md) |

### Interface Routing Strategy

| Situation | Strategy | Why | Reference |
|-----------|----------|-----|-----------|
| LLM agents will use this app | **MCP Routing** | Tool discovery, introspection | [ADR-0046](0046-interface-routing-strategies.md) |
| Need <5ms response time | **Direct Calls** | Minimal overhead | [ADR-0046](0046-interface-routing-strategies.md) |
| High volume (>1000 req/sec) | **Hybrid** | Direct for high-freq, MCP for features | [ADR-0046](0046-interface-routing-strategies.md) |
| Standard business app | **MCP Routing** | Automatic features, consistency | [ADR-0046](0046-interface-routing-strategies.md) |

### Performance Strategy

| Operation Time | Request Volume | Strategy | Reference |
|----------------|----------------|----------|-----------|
| <10ms | Any | Direct calls + selective optimization | [ADR-0047](0047-performance-guidelines.md) |
| 10-50ms | <1000/sec | MCP routing acceptable | [ADR-0047](0047-performance-guidelines.md) |
| 10-50ms | >1000/sec | Hybrid routing | [ADR-0047](0047-performance-guidelines.md) |
| >50ms | Any | Full MCP routing with caching | [ADR-0047](0047-performance-guidelines.md) |

## 📋 Decision Checklist for Claude Code

Before implementing any app/feature, answer:

### Performance Questions
- [ ] Expected latency requirement: ___ms
- [ ] Peak request volume: ___/second
- [ ] Real-time requirements: Y/N
- [ ] Batch processing needs: Y/N

### Integration Questions
- [ ] LLM agent integration needed: Y/N
- [ ] External API consistency required: Y/N
- [ ] Automatic caching/metrics needed: Y/N
- [ ] WebSocket/streaming required: Y/N

### Complexity Questions
- [ ] Workflow complexity: Simple (<5 nodes) / Medium (5-10) / Complex (>10)
- [ ] Reusable patterns needed: Y/N
- [ ] Multiple team members: Y/N
- [ ] Dynamic workflow modification: Y/N

## 🎯 Recommended Defaults

**For most applications:**
- **Workflow Pattern**: Hybrid (inline + templates)
- **Interface Routing**: MCP routing (unless <5ms required)
- **Performance Strategy**: Standard with caching

**Override defaults only when:**
- Specific performance requirements demand it
- Technical constraints require different approach
- User explicitly requests alternative

## 🔄 Common Decision Combinations

### Standard Business App
```yaml
Workflow Pattern: Hybrid
Interface Routing: MCP
Performance: Standard with caching
Rationale: Balanced approach with enterprise features
```

### High-Performance API
```yaml
Workflow Pattern: Inline
Interface Routing: Hybrid (direct for critical paths)
Performance: Selective optimization
Rationale: Performance critical with mixed requirements
```

### Enterprise Admin Tool
```yaml
Workflow Pattern: Class-based with templates
Interface Routing: MCP
Performance: Full feature stack
Rationale: Complex workflows, LLM integration, maintainability
```

### Real-time Processing
```yaml
Workflow Pattern: Inline
Interface Routing: Direct calls
Performance: Ultra-low latency optimization
Rationale: Performance is the primary constraint
```

## 🚨 Red Flags - When to Reconsider

**Workflow Pattern Red Flags:**
- Copying workflow code across services → Use templates
- Can't access service config in workflows → Consider inline
- Complex inheritance hierarchies → Simplify or use hybrid

**Interface Routing Red Flags:**
- Manual caching/metrics implementation → Use MCP
- Inconsistent API/CLI behavior → Use MCP
- Performance bottlenecks in MCP layer → Consider hybrid

**Performance Red Flags:**
- Optimizing prematurely → Profile first
- Sacrificing maintainability for marginal gains → Reconsider
- Not measuring actual performance → Benchmark first

## 📊 Migration Paths

### From Direct to MCP
1. Create MCP tools wrapping services
2. Update API/CLI to call MCP tools
3. Measure performance impact
4. Optimize if needed

### From Inline to Hybrid
1. Extract common patterns to templates
2. Keep service-specific logic inline
3. Test equivalent behavior

### From Simple to Enterprise
1. Add class-based templates for reuse
2. Implement MCP routing for consistency
3. Add monitoring and caching

## 🔗 Related Documentation

- **Complete App Guide**: [../apps/ARCHITECTURAL_GUIDE.md](../apps/ARCHITECTURAL_GUIDE.md)
- **Workflow Patterns**: [../# contrib (removed)/architecture/adr/0045-workflow-construction-patterns.md](../# contrib (removed)/architecture/adr/0045-workflow-construction-patterns.md)
- **Interface Routing**: [../# contrib (removed)/architecture/adr/0046-interface-routing-strategies.md](../# contrib (removed)/architecture/adr/0046-interface-routing-strategies.md)
- **Performance Guidelines**: [../# contrib (removed)/architecture/adr/0047-performance-guidelines.md](../# contrib (removed)/architecture/adr/0047-performance-guidelines.md)
