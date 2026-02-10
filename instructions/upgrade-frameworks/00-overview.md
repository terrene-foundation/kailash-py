# Framework Upgrade Plan: Kailash SDK v0.12.0

## Purpose

This document set is the **authoritative implementation specification** for upgrading the Kailash SDK frameworks. Every codegen agent MUST read these documents before starting any implementation work under this upgrade.

## Problem Statement

Analysis of 3 production projects (enterprise-app: 218K LOC, example-project: 89K LOC, example-backend: 75K LOC) reveals that **every project independently builds the same infrastructure**:

- JWT auth middleware: 150-350 lines per project
- RBAC middleware: 250-435 lines per project
- Rate limiting: 236-434 lines per project
- Audit middleware: 243-272 lines per project
- Tenant isolation: 137-294 lines per project
- SSO/OAuth integration: 276-425 lines per project
- Total duplicated auth/middleware: **~10,470 lines across 3 projects**

Additionally, all projects access `app._gateway.app` (a private attribute) to add FastAPI middleware and routers, because Nexus has no public API for this.

## Scope

Four workstreams, executed in dependency order:

| #   | Workstream                  | Package                | Priority | Estimated Effort |
| --- | --------------------------- | ---------------------- | -------- | ---------------- |
| 01  | Nexus Native Middleware API | kailash-nexus          | P0       | 15-20h           |
| 02  | Auth/RBAC/SSO Package       | kailash-nexus (plugin) | P0       | 35-45h           |
| 03  | Handler Migration Guide     | kailash-nexus + docs   | P1       | 8-12h            |
| 04  | Golden Patterns for Codegen | .claude/skills + docs  | P1       | 10-15h           |

## Dependency Graph

```
01-nexus-native-middleware
    ↓
02-auth-package (depends on 01 for add_middleware/include_router)
    ↓
03-handler-migration (depends on 01+02 for complete examples)
    ↓
04-golden-patterns (incorporates patterns from 01+02+03)
```

## Architecture Principle

All new functionality MUST be implemented as **Nexus plugins** or **Nexus-native APIs**, not as standalone packages. This ensures:

1. Single integration point (`app.add_plugin(AuthPlugin(...))`)
2. Consistent lifecycle (startup/shutdown hooks)
3. Codegen can scaffold with one line instead of wiring middleware manually
4. Cross-cutting concerns (auth, audit, rate limit) compose naturally

## Version Targets

- kailash (core): 0.12.0 (add HandlerNode exports, any needed base classes)
- kailash-nexus: 1.3.0 (middleware API, auth plugin, presets)
- kailash-dataflow: 0.11.0 (no changes needed)
- kailash-kaizen: 1.1.0 (no changes needed)

## Evidence Base

All design decisions are grounded in real usage patterns observed in:

- `./repos/dev/enterprise-app/` - 97 services, 96 models, RBAC+ABAC+SSO+audit+feature gates
- `./repos/projects/example-project/` - 21 Nexus gateways, 13 custom auth nodes, RBAC+JWT+rate limiting
- `./repos/projects/example-backend/` - 15 FastAPI routers, 7 DataFlow instances, Azure AD+Apple JWT+tenant isolation

## Document Index

- `01-nexus-native-middleware/` - Public middleware and router API for Nexus
  - `01-public-middleware-api.md` - `app.add_middleware()`, `app.include_router()` methods
  - `02-preset-system.md` - Pre-configured middleware stacks (SaaS, Enterprise, Lightweight)
  - `03-cors-configuration.md` - Native CORS support without `_gateway.app`
- `02-auth-package/` - Authentication, authorization, and identity
  - `01-architecture.md` - Plugin architecture, component overview
  - `02-jwt-middleware.md` - JWT extraction, verification, refresh token support
  - `03-rbac-system.md` - Role-based and permission-based access control
  - `04-sso-providers.md` - OAuth2 (Google, GitHub, Azure AD), SAML, Apple Sign-In
  - `05-rate-limiting.md` - Redis-backed distributed rate limiting
  - `06-tenant-isolation.md` - Multi-tenant query scoping and org boundaries
  - `07-audit-logging.md` - Request audit trail with structured logging
- `03-handler-migration/` - Migrating from workflow boilerplate to `@app.handler()`
  - `01-migration-guide.md` - Step-by-step migration patterns
  - `02-real-project-patterns.md` - Patterns extracted from production projects
- `04-golden-patterns/` - Codegen-optimized pattern catalog
  - `01-top-10-patterns.md` - Curated pattern catalog for AI scaffolding
  - `02-codegen-decision-tree.md` - Pattern selection logic for codegen agents

## Implementation Protocol

1. **Read this overview** and all relevant workstream docs before writing code
2. **Follow dependency order** - complete 01 before 02, etc.
3. **Test comprehensively** - no stubs, no mocks in Tier 2-3, 100% pass rate
4. **Update todos** - use todo-manager to track every task
5. **Document as you go** - update docs/ in the respective package directory
6. **Red-team review** - security-reviewer before any commit
