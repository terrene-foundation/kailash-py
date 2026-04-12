# Brief — DataFlow Perfection Mandate

**Owner**: Jack Hong (technical leader)
**Date**: 2026-04-08
**Scope**: The entire `packages/kailash-dataflow/` package in `terrene-foundation/kailash-py`
**Constraint**: None. No time budget, no cost ceiling. DataFlow MUST be perfect.
**Execution model**: Autonomous — 10x throughput, parallel agent specialization, zero human-days framing.

## Mandate

DataFlow is the database fabric the rest of the Kailash ecosystem depends on. Three recent issues exposed the tip of an iceberg:

- **#352** — `model_registry._create_model_registry_table()` calls sync `runtime.execute()` from async context; FastAPI startup fails
- **#353** — `PostgreSQLAdapter.get_connection_parameters()` ignores `sslmode` from URL; local dev broken
- **#354** — `PipelineExecutor(redis_url=...)` accepts and silently discards the URL; multi-replica fabric is per-process in-memory despite docstrings promising Redis; **eight stubs/lies in one file**, **two deeper wiring bugs** beyond the report, **latent multi-tenant data-leak primitive**

The user's directive: **"dataflow MUST be perfect"**. That is the scope of this workspace.

## Definition of "perfect"

A perfect DataFlow package satisfies ALL of the following:

1. **Zero stubs, placeholders, or silent fallbacks** — not one. Every config field, every docstring, every comment either reflects reality or is deleted. `.claude/rules/zero-tolerance.md` Rules 1-6 hold with no exceptions.
2. **Zero docstring lies** — every parameter documented is plumbed; every promise made is kept.
3. **Zero dead code** — every class instantiated somewhere, every field read somewhere, every fallback reachable or deleted.
4. **Zero sync-in-async-context bugs** — every DataFlow entry point works from both sync and async contexts without deadlock.
5. **Multi-tenant correctness at every layer** — tenant dimension on every cache key, every query filter, every log line, every metric label where `multi_tenant=True` is declared. Loud failure when tenant_id is missing and required.
6. **Multi-replica correctness** — shared state through Redis (or Postgres) where the docstring says "cross-worker"; no per-process pretending-to-be-shared. Race conditions documented and tested.
7. **Dialect portability where promised** — PostgreSQL / MySQL / SQLite parity for every feature not explicitly documented as dialect-specific. `sslmode`, `application_name`, pool sizing, connection timeout — all honored on every dialect.
8. **Observability at every boundary** — entry/exit/error logs per `.claude/rules/observability.md`, `mode=real|cached|fake` on every data call, structured fields not f-strings, correlation IDs propagated.
9. **Test coverage for every claim** — if a parameter's docstring mentions "production", "Redis", "cross-worker", "distributed", or "shared", there MUST be a Tier 2 integration test exercising it with real infrastructure.
10. **Security discipline** — no hardcoded secrets, no SQL string interpolation, no `except: pass`, no `eval` on user input, no PII in logs. Row-level security honored. Tenant isolation enforced.
11. **Cross-SDK parity** — kailash-rs `crates/kailash-dataflow` has matching semantics (not identical code) per EATP D6. Any Python feature missing in Rust is filed as a `cross-sdk` issue.
12. **Framework-first compliance** — no raw SQL where DataFlow nodes exist; no raw HTTP where Nexus exists. No two parallel cache implementations in the same package.
13. **Resource hygiene** — every async resource class has `__del__` with `ResourceWarning`; every connection pool has `close()` called on shutdown; no orphan runtimes; `asyncio.to_thread` not used in `__del__`.

## What this workspace produces

1. **01-analysis/02-subsystem-audits/** — one report per subsystem:
   - 01-core-and-config.md
   - 02-adapters.md
   - 03-fabric-deep-dive.md (builds on `workspaces/issue-354/` findings)
   - 04-cache.md
   - 05-tenancy-and-security.md
   - 06-nodes-query-migrations.md
   - 07-testing-and-observability.md
   - 08-platform-web-orphans.md (platform/, web/, semantic/, classification/, debug/, cli/, compatibility/, validators/, performance/, optimization/, features/, trust/, utils/, sql/, migration/)
2. **01-analysis/00-executive-summary.md** — consolidated findings with severity rollup
3. **02-plans/01-master-fix-plan.md** — atomic, sequenced fix plan for the entire package
4. **02-plans/02-followups-and-cross-sdk.md** — what goes into follow-up issues and parallel Rust work
5. **03-user-flows/** — flow diagrams for each changed subsystem behavior (cache, webhook, migration, tenant, etc.)
6. **04-validate/01-red-team-findings.md** — red team of the analysis
7. **journal/** — DISCOVERY, GAP, CONNECTION entries for institutional knowledge capture

## Severity taxonomy

- **CRITICAL** — production impact today, data loss risk, data leak risk, silent runtime failure, security vulnerability. MUST fix in this sprint.
- **HIGH** — silent degradation, stub parameters, docstring lies, framework-first violations. MUST fix in this sprint.
- **MEDIUM** — suboptimal patterns, missing observability, incomplete dialect support, test gaps. MUST fix in this sprint.
- **LOW** — code hygiene, dead comments, minor inconsistencies. SHOULD fix in this sprint; MAY be batched.

No MEDIUMs or LOWs should remain after implementation. The user said "perfect", not "acceptable".

## Constraints

- **No code changes in the analysis phase** — this is pure discovery and planning.
- **All claims cited `file:line`** — no speculation without a marker.
- **Cross-SDK check for every finding** — does kailash-rs have the same? File or note.
- **Framework-first check for every finding** — is there an existing abstraction being bypassed?
- **Respect `.claude/rules/`** — especially dataflow-pool.md, zero-tolerance.md, framework-first.md, observability.md, testing.md, schema-migration.md, dependencies.md, infrastructure-sql.md, cross-sdk-inspection.md.

## Existing issues in scope

- #352 — model_registry async bug
- #353 — PostgreSQL sslmode ignored
- #354 — fabric cache Redis ignored (analyzed separately in `workspaces/issue-354/`; integrate findings here)
- Any other open dataflow-tagged issue on GitHub — sweep at analysis time

## References

- Package root: `packages/kailash-dataflow/`
- Source: `packages/kailash-dataflow/src/dataflow/` (28 subsystems, ~280 .py files)
- Tests: `packages/kailash-dataflow/tests/` (~486 .py files)
- Issue #354 analysis: `workspaces/issue-354/` (830-line specialist report, blast radius, red team findings)
- Red-team verification protocol: `.claude/skills/spec-compliance/SKILL.md`
