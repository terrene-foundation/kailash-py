# Nexus Skills

Complete set of 21 Nexus skills covering all aspects from quickstart to advanced topics.

## Skills Overview

### Core Nexus (5 Skills - CRITICAL/HIGH)

1. **nexus-quickstart** - Zero-config Nexus() setup, basic registration
   - Priority: CRITICAL
   - Zero configuration, .build() pattern, multi-channel basics

2. **nexus-multi-channel** - API/CLI/MCP channels, unified access
   - Priority: HIGH
   - Revolutionary architecture, cross-channel consistency

3. **nexus-workflow-registration** - Registration patterns, auto-discovery, versioning
   - Priority: HIGH
   - Manual registration, dynamic discovery, lifecycle management

4. **nexus-sessions** - Session management across channels
   - Priority: HIGH
   - Cross-channel sessions, state persistence

5. **nexus-dataflow-integration** - CRITICAL blocking fix configuration
   - Priority: CRITICAL
   - auto_discovery=False, auto_migrate=True (v0.11.0 default), performance optimization

### Channel-Specific (6 Skills - HIGH)

6. **nexus-api-patterns** - REST API usage, endpoints, requests
   - Priority: HIGH
   - HTTP endpoints, request/response formats, Python clients

7. **nexus-cli-patterns** - CLI commands, arguments, execution
   - Priority: HIGH
   - Command-line interface, scripting, automation

8. **nexus-mcp-channel** - MCP tool exposure, AI agent integration
   - Priority: HIGH
   - Model Context Protocol, tool discovery, AI agents

9. **nexus-api-input-mapping** - How API inputs map to workflow parameters
   - Priority: CRITICAL
   - try/except pattern, parameter broadcasting, connections

10. **nexus-health-monitoring** - Health checks, monitoring, metrics
    - Priority: HIGH
    - Health endpoints, Prometheus, custom checks

11. **nexus-troubleshooting** - Common issues, debugging, solutions
    - Priority: HIGH
    - Error messages, debugging strategies, fixes

### Configuration (3 Skills - MEDIUM)

12. **nexus-config-options** - Configuration reference
    - Priority: MEDIUM
    - Constructor options, progressive config, environment variables

13. **nexus-enterprise-features** - Authentication, monitoring, rate limiting
    - Priority: MEDIUM
    - OAuth2, RBAC, circuit breakers, caching

14. **nexus-production-deployment** - Docker, Kubernetes, scaling
    - Priority: MEDIUM
    - Production patterns, containerization, orchestration

### Advanced (3 Skills - MEDIUM/LOW)

15. **nexus-architecture** - Internal architecture, design principles
    - Priority: MEDIUM
    - Multi-layer architecture, component overview, design patterns

16. **nexus-event-system** - Event routing, handlers, lifecycle
    - Priority: LOW
    - Workflow events, cross-channel broadcasting, custom events

17. **nexus-plugins** - Plugin development, extending Nexus
    - Priority: LOW
    - Custom plugins, plugin system, extensibility

### v1.3.0 Additions (4 Skills - HIGH)

18. **nexus-handler-support** - Register Python functions as multi-channel workflows
    - Priority: HIGH
    - `@app.handler()` decorator, `register_handler()`, parameter derivation, sandbox bypass

19. **nexus-auth-plugin** - NexusAuthPlugin unified authentication
    - Priority: HIGH
    - JWT, RBAC, SSO (GitHub/Google/Azure), rate limiting, tenant isolation, audit logging

20. **golden-patterns-catalog** - Top 7 production-validated codegen patterns
    - Priority: HIGH
    - Ranked by usage across 382K LOC, with correct imports and security defaults

21. **codegen-decision-tree** - Structured decision logic for pattern selection
    - Priority: HIGH
    - Decision tree, 7 anti-patterns, 3 scaffolding templates

## Critical Patterns Included

### 1. API Input Mapping (Lines 139-241 from nexus-specialist)

- Complete flow from API request to node parameters
- try/except pattern for parameter access
- Broadcasting behavior explained
- Common pitfalls with solutions

### 2. DataFlow Blocking Fix (Lines 320-386 from nexus-specialist)

- auto_discovery=False configuration
- auto_migrate=True (v0.11.0 default, works in Docker/FastAPI)
- Performance comparison (30s → <2s)
- Trade-off analysis

### 3. Zero-Config Pattern

- Nexus() with no parameters
- .build() before register
- Correct parameter order

### 4. Multi-Channel Architecture

- Single registration, three interfaces
- Cross-channel sessions
- Unified parameter handling

## Source Documentation

All skills created from verified sources:

- sdk-users/apps/nexus/README.md
- sdk-users/apps/nexus/docs/\* (getting-started, user-guides, technical, reference, advanced)
- .claude/agents/frameworks/nexus-specialist.md
- sdk-users/apps/nexus/CLAUDE.md

## Skill Dependencies

```
nexus-quickstart (START HERE)
    ├── nexus-multi-channel
    │   ├── nexus-api-patterns
    │   │   └── nexus-api-input-mapping
    │   ├── nexus-cli-patterns
    │   └── nexus-mcp-channel
    ├── nexus-workflow-registration
    │   └── nexus-dataflow-integration
    └── nexus-sessions

nexus-config-options
    ├── nexus-enterprise-features
    └── nexus-production-deployment

nexus-health-monitoring
    └── nexus-troubleshooting

nexus-architecture
    ├── nexus-event-system
    └── nexus-plugins
```

## Quick Reference

### Start Here

1. Read **nexus-quickstart** for basic setup
2. Read **nexus-multi-channel** to understand architecture
3. Read **nexus-api-input-mapping** for critical parameter handling

### Common Tasks

- **Setup Nexus**: nexus-quickstart
- **Fix blocking with DataFlow**: nexus-dataflow-integration
- **Use REST API**: nexus-api-patterns, nexus-api-input-mapping
- **Deploy to production**: nexus-production-deployment
- **Fix issues**: nexus-troubleshooting

### By Priority

- **CRITICAL**: nexus-quickstart, nexus-dataflow-integration, nexus-api-input-mapping
- **HIGH**: nexus-multi-channel, nexus-workflow-registration, nexus-sessions, channels, monitoring
- **MEDIUM**: config, enterprise, production, architecture
- **LOW**: events, plugins

## Coverage

### What's Covered

- ✅ Zero-configuration setup
- ✅ Multi-channel architecture (API/CLI/MCP)
- ✅ Workflow registration patterns
- ✅ DataFlow integration with blocking fix
- ✅ API input mapping (critical pattern)
- ✅ Session management
- ✅ Health monitoring
- ✅ Troubleshooting guide
- ✅ Configuration options
- ✅ Enterprise features
- ✅ Production deployment
- ✅ Architecture overview
- ✅ Event system
- ✅ Plugin development
- ✅ Handler support (`@app.handler()` decorator)
- ✅ Authentication plugin (JWT, RBAC, SSO, rate limiting, tenant, audit)
- ✅ Golden patterns catalog (7 patterns)
- ✅ Codegen decision tree (anti-patterns, scaffolding)

### What's NOT Covered

- Implementation details (covered in docs)
- Code deep-dives (use source code)

## Usage Notes

1. **Skills are self-contained** - Each can be read independently
2. **Start with quickstart** - Best entry point for all users
3. **Use input-mapping for API issues** - Critical for parameter problems
4. **Check troubleshooting first** - Common issues with solutions
5. **Reference config-options** - Complete configuration reference

## Verification

21 skills created and verified:

- Location: .claude/skills/03-nexus/
- Total files: 21 skills + SKILL.md + README.md
- Priority: CRITICAL (3), HIGH (12), MEDIUM (4), LOW (2)

## Related Skill Sets

- **Core SDK Skills**: .claude/skills/1-core-sdk/
- **DataFlow Skills**: .claude/skills/2-frameworks/dataflow/
- **Kaizen Skills**: .claude/skills/2-frameworks/kaizen/

---

**Phase 2 Complete**: 17 Nexus skills ready for use.
