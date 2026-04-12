# DataFlow Perfection — Amendments Applied

**Date**: 2026-04-08
**Source**: red team findings at `04-validate/01-red-team-findings.md` and `04-validate/02-architecture-challenges.md`
**Status**: Applied in this commit. The executive summary and master fix plan were corrected inline where the scope of change was small; the larger structural amendments are captured here and should be read AS THE ADDENDUM TO `02-plans/01-master-fix-plan.md` before `/todos`.

## Factual corrections to executive summary

| #   | Claim                                       | Was                      | Actual                                                                                                                                                                   | Source                              |
| --- | ------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------- |
| 1   | `migration_history.jsonl` success rate      | "44/44 all failed"       | **16/44 failed, 28 succeeded**                                                                                                                                           | Re-counted                          |
| 2   | `print()` calls in production               | 301 in 37 files          | **294 in 36 files**                                                                                                                                                      | Re-grepped                          |
| 3   | Mock violations in Tier 2/3                 | 118 in 30 files          | **89 in 34 files (67 integration + 22 e2e)**                                                                                                                             | Re-grepped                          |
| 4   | `compatibility/legacy_support.py` Mock line | line 75                  | **line 79**                                                                                                                                                              | Read                                |
| 5   | Current package version                     | 1.8.0                    | **1.7.1** per `dataflow/__init__.py:95` — also a Rule 5 violation (version drift with `pyproject.toml`)                                                                  | Read                                |
| 6   | Express cache leak characterization         | "ACTIVE data leak today" | **LATENT** — impact-verse does not set `multi_tenant=True` (default False). Still CRITICAL because any user who DOES set `multi_tenant=True` with `redis_url` is leaking | Verified in tpc/impact-verse source |

Severity of the overall audit is unchanged — the architectural verdict holds. Every other CRITICAL/HIGH finding (SQL injection 13 sites, eval RCE, exec RCE, fake encryption, fake managers, orphan stacks, façade pattern, fabric endpoint stack, webhook dedup, sslmode, execute_transaction non-transaction, `_cache_key` tenant dimension, observability collapse) was verified at source.

## Structural amendments to the master plan

### Amendment 1: Three-release strategy instead of one 2.0.0 bump

**Problem**: a single 2.0.0 release bundles urgent security patches behind 21+ cycles of architectural rework. impact-verse needs the security fixes now. The plan also conflicts with `workspaces/issue-354/` which targets 1.9.0 on its own branch with overlapping files.

**Amendment**: three releases, three branches, three merges.

| Release   | Branch                                                                              | Scope                                                                                                                                                                                                                                                                  | Target cycle |
| --------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------ |
| **1.8.1** | `fix/dataflow-security-urgent`                                                      | PR-1 only — 9 CRITICAL security fixes (SQL injection 13 sites, eval, exec, fake encryption, DDL identifier quoting, `LIMIT/OFFSET` parameterization, `validate_queries=True` flip, Redis URL masking). Minimal-diff patch release. No API shape changes. No deletions. | 1-2          |
| **1.9.0** | `fix/354-fabric-redis-cache` (EXISTING, already planned in `workspaces/issue-354/`) | Integrated issue-354 fabric cache fix + all red-team amendments from that workspace. Merges AFTER 1.8.1.                                                                                                                                                               | 3-4          |
| **2.0.0** | `fix/dataflow-perfection` (branched from 1.9.0 merge commit)                        | Remaining 12 PRs: façade managers, orphan wiring/deletion, adapter consolidation, model registry async, nodes, auto-migrate safety, observability overhaul, test rewrite, docs, rule extensions, cross-SDK parallels.                                                  | 5-25         |

**Why**: urgent security should never wait on refactor scope. impact-verse can roll forward on 1.8.1 immediately and upgrade to 2.0.0 on a longer timeline. The fabric cache fix is already designed and red-teamed in `workspaces/issue-354/` — don't re-do that work, merge it into 1.9.0 as planned.

### Amendment 2: Reclassify four "delete" candidates as "wire"

**Problem**: four subsystems marked for deletion in PR-3 have non-zero production importers OR downstream workspace usage OR published documentation. Deletion would break the build AND break downstream users.

**Amendment**: reclassify from DELETE to WIRE or KEEP.

| Subsystem                  | Original verdict    | Evidence against deletion                                                                                                                                                                                                                                | New verdict                                                                                                                 |
| -------------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `dataflow/classification/` | DELETE (1,200+ LOC) | Imported by `core/engine.py:13, 458`. LIVE code path. The `@classify("email", PII, ..., REDACT)` decorator promises redaction — wire it into the read/write interceptor per PR-8.                                                                        | **WIRE in PR-8**                                                                                                            |
| `dataflow/trust/`          | DELETE (2,407 LOC)  | Referenced by four downstream workspaces (`rr/agentic-os`, `rr/rr-agentic-os`, `rr/rr-aegis`, `dev/aegis`) AND published in `docs/trust/trust-dataflow-integration.md`. This is the seed of Terrene Foundation's trust-plane integration, not dead code. | **WIRE in PR-6b (new sub-PR)** — complete the CARE/EATP integration into the query path, audit store, and tenant isolation. |
| `dataflow/performance/`    | DELETE (1,700 LOC)  | Published in `docs/advanced/sqlite-enterprise-features.md`. Duplicate `MigrationConnectionManager` class collision must still be resolved, but the directory stays.                                                                                      | **KEEP + rename collision**                                                                                                 |
| `dataflow/platform/`       | DELETE (most of it) | Consumed by every `debug/` and `cli/` module. `platform/errors::ErrorEnhancer` imported at `core/nodes.py:52`.                                                                                                                                           | **KEEP + audit each file individually** — only delete leaf modules with zero importers                                      |

**Revised PR-3 deletion scope**: ~13,000 LOC (down from ~18,400) — still substantial but doesn't break the build. The full deletion manifest becomes a per-file audit in `02-plans/04-deletion-manifest.md` (to be written in PR-3 preamble).

### Amendment 3: Break the PR-1 → PR-3 → PR-4 dependency cycle

**Problem**: PR-1 (security) says "use `quote_identifier()` from PR-4". PR-4 depends on PR-3 (delete dead dialect systems). PR-3 depends on PR-1 (security patches land first). Three-way cycle.

**Amendment**: PR-1 introduces a stopgap `_safe_identifier(name: str) -> str` helper inside `adapters/base.py` that does strict regex validation (`^[a-zA-Z_][a-zA-Z0-9_]*$`) and double-quotes the result. Every security fix in PR-1 uses this helper. PR-4 later promotes the stopgap into the canonical `dialect.quote_identifier()` and migrates call sites. No cycle.

```
PR-1: adds _safe_identifier() stopgap + uses it at every DDL site
PR-3: deletes dead dialect systems (no _safe_identifier conflict because PR-1's stopgap lives in adapters/base.py, not the dialect modules)
PR-4: promotes _safe_identifier() into dialect.quote_identifier() + migrates the PR-1 call sites + deletes the stopgap
```

### Amendment 4: PR-3 dependent-file manifest before any deletion

**Problem**: several deletion candidates have in-package importers the audit missed:

- `nodes/semantic_memory.py:17-19` imports `from ..semantic.embeddings/memory/search` — deleting `semantic/` crashes on next import
- `compatibility/migration_path.py:107,171` imports `legacy_support.py` — deleting `compatibility/` cascades
- `core/nodes.py:52` imports `platform/errors::ErrorEnhancer` — `platform/` has live consumers

**Amendment**: PR-3 begins with a mandatory manifest write.

1. For every deletion candidate, run `git grep -l '<module_name>\|<class_name>' packages/ src/ docs/ workspaces/`
2. Record each importer in `workspaces/dataflow-perfection/02-plans/04-deletion-manifest.md` with one of three dispositions:
   - **Update importer**: the importer also gets updated in the same commit (e.g., `nodes/semantic_memory.py` gets rewritten or deleted)
   - **Downstream workspace**: the importer is a non-kailash-py repo; file a cross-repo issue and defer deletion until those repos migrate
   - **Safe**: zero importers in any repo
3. Delete only files with all importers resolved or marked safe.

### Amendment 5: PR-6 split into four sub-PRs

**Problem**: PR-6 as written combined issue-354 fabric cache + 6 Nexus endpoint registrations + 4 webhook provider adapters + FabricScheduler cron runtime. That's four distinct features on one diff — unreviewable and un-rollback-able.

**Amendment**:

| Sub-PR    | Scope                                                                                                                                                               | Depends on                                                                       |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| **PR-6a** | Issue-354 fabric cache fix (integrates `workspaces/issue-354/` plan with all red-team amendments). Ships in **1.9.0**.                                              | PR-1 (1.8.1 merged), PR-5 tenant partitioning (post-1.8.1 patch to 1.9.0 branch) |
| **PR-6b** | Fabric endpoint wiring into Nexus (6 endpoint classes, 1,555 LOC of orphan code). Ships in **2.0.0**.                                                               | PR-6a, nexus-specialist                                                          |
| **PR-6c** | Multi-webhook-source adapters (GitHub, GitLab, Stripe, Slack, generic). Ships in **2.0.0**.                                                                         | PR-6b                                                                            |
| **PR-6d** | FabricScheduler cron runtime wiring. **Re-evaluate scope**: this is a net-new feature, not a bug fix. Push to a dedicated follow-up PR after the perfection sprint. | —                                                                                |

PR-6d is removed from the perfection sprint and filed as a follow-up issue (`feat(fabric): wire FabricScheduler cron runtime`). The sprint's scope is "fix every broken thing", not "add every missing feature".

### Amendment 6: Parallel execution corrections

**Problem**: the plan claimed PR-1, PR-2, PR-3, PR-5 could parallelize. Three-way merge conflicts identified:

- **`core/multi_tenancy.py`**: PR-1 (security) + PR-2 (`TenantSecurityManager` delete) + PR-3 (orphan sweep) all touch this file
- **`adapters/*.py`**: PR-1 (quote_identifier) + PR-3 (delete `sqlite_enterprise.py`) + PR-4 (dialect rewrite) all touch the adapter layer
- **`cache/key_generator.py` + `features/express.py`**: PR-5 (cache tenancy) + PR-6a (fabric cache) both touch cache key construction

**Amendment**: enforce strict sequential ordering on shared files.

1. PR-1 lands first and touches `core/multi_tenancy.py` + adapters + `database/query_builder.py` + `cache/auto_detection.py`
2. After PR-1 merges, PR-2 rebases on top and touches `core/multi_tenancy.py` again (for `TenantSecurityManager` delete)
3. After PR-2, PR-3 rebases and deletes orphans
4. After PR-3, PR-4 rebases and does dialect consolidation on adapters
5. PR-5 and PR-6a serialize on cache keys — PR-5 lands first in a 1.8.2 or 1.9.0 baseline, PR-6a rebases

True parallelizable pairs: (PR-7, PR-8), (PR-10, PR-12), (PR-13, PR-14). Everything else serializes by shared file.

### Amendment 7: Pre-commit guardrails move to PR-0

**Problem**: PR-13 was going to add rule extensions and CI guards. But the guards are what PROTECT PR-1 through PR-12 from re-introducing the bugs they're fixing. Putting them at the end of the sprint defeats their purpose.

**Amendment**: PR-0 adds the following pre-commit guards BEFORE any fix lands:

- `grep -rn 'f"[^"]*{[a-zA-Z_]*}.*"' src/dataflow/ --include='*.py' | grep -i 'sql\|query\|execute\|insert\|update\|delete\|drop\|create\|alter'` → zero matches required
- `grep -rn '^\s*print(' packages/kailash-dataflow/src/dataflow/` → zero
- `grep -rn 'logger\.\(info\|error\|warning\|debug\)(f"' packages/kailash-dataflow/src/dataflow/` → zero (after PR-10)
- `grep -rn 'eval(\|exec(' packages/kailash-dataflow/src/dataflow/` → zero (after PR-1, enforced forever)
- `grep -rn 'except:\s*pass' packages/kailash-dataflow/src/dataflow/` → zero
- `grep -rn 'unittest.mock\|from mock\|MagicMock\|@patch' packages/kailash-dataflow/tests/integration/ packages/kailash-dataflow/tests/e2e/ packages/kailash-dataflow/tests/fabric/` → zero (after PR-11)
- `grep -rn 'aiosqlite.connect(' packages/kailash-dataflow/src/` → zero outside the canonical pool module
- `grep -rn 'print[^_(]*(' packages/kailash-dataflow/src/` → zero (extends PR-0's 294 deletion)

Each guard fails pre-commit if violated. Guards are ratcheted — they start at "reduce by N this commit" and tighten to "zero" as PRs land.

### Amendment 8: Cross-SDK Rust work runs in parallel from PR-0, not at PR-14

**Problem**: the plan deferred kailash-rs issue filing to PR-14 (after everything). But autonomous execution is 10x parallel — the Rust work can start at sprint kickoff.

**Amendment**: PR-0 files all 8 kailash-rs issues as placeholders. Rust specialists claim them and work in parallel with Python PRs. Rust work does NOT block Python merges, but every Python PR that lands triggers a re-sync on the corresponding Rust issue.

### Amendment 9: impact-verse lockstep migration PR-15

**Problem**: the plan said "breaking changes documented in CHANGELOG". For impact-verse — a production user — that is insufficient. A broken upgrade path is the same as no fix.

**Amendment**: add PR-15 "impact-verse lockstep migration". Scope:

1. Clone `tpc/impact-verse` to a feature branch
2. Upgrade the `kailash-dataflow` dependency from 1.7.1 → 1.8.1 (after 1.8.1 merges to main) and verify
3. Upgrade to 1.9.0 after 1.9.0 lands — coordinate with the fabric cache migration
4. Upgrade to 2.0.0 after 2.0.0 lands — full async migration + tenant_id extraction + `multi_tenant=True` opt-in if desired
5. Open an impact-verse PR for each upgrade step
6. Run impact-verse's full integration test suite at each step

This is not extra work — it is the validation that the perfection sprint actually achieved perfection, using the primary production consumer as the canary.

### Amendment 10: Classification — decide WIRE now, not in PR-8

**Problem**: PR-8 said "either wire or delete". A decision must be made before implementation.

**Amendment**: **WIRE it.** The `@classify("email", PII, ..., REDACT)` decorator is the natural user API for field-level security. Wire it into the Express query path (write-time classification + read-time redaction based on tenant context) in PR-8. Deletion would throw away a good API surface.

### Amendment 11: `raise` vs graceful degradation on library boundaries

**Problem**: the plan defaults to `raise` on every failure path. DataFlow is a library — aggressive raises break its consumers.

**Amendment**: distinguish invariant violations (raise) from operational failures (log + surface):

| Failure                                                | Action                                                                                |
| ------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| `multi_tenant=True` model without `tenant_id`          | **Raise** `FabricTenantRequiredError` (invariant violation)                           |
| Unknown field name in UpdateNode `fields` dict         | **Raise** `UnknownFieldError` (invariant violation)                                   |
| SQL injection attempt via unquoted identifier          | **Raise** `InvalidIdentifierError` (invariant violation)                              |
| Redis unreachable mid-operation                        | **Log WARN, emit `fabric_cache_degraded=1`, return cache miss** (operational failure) |
| Redis URL malformed at startup                         | **Raise** `InvalidConfigError` at startup (invariant violation)                       |
| Database connection failed at startup                  | **Raise** `ConnectionError` per `rules/dataflow-pool.md` Rule 2 (invariant violation) |
| Auto-migrate failed on model registration              | **Raise** (new behavior — was swallowed, will now fail loudly)                        |
| Migration run failed                                   | **Raise**                                                                             |
| Cache backend selection warning (dev_mode + redis_url) | **Log WARN, use in-memory** (operational)                                             |
| Webhook signature mismatch                             | **Log WARN, return 401** (operational)                                                |
| Change detector source error                           | **Log ERROR, skip this cycle** (operational per source)                               |

### Amendment 12: PR-11 test cycle budget increased to 6-8

**Problem**: PR-11 was budgeted at 2 cycles for "118 mock removals + regression tests + coverage". Actual scope: 89 mock removals (corrected) + ~50 new regression tests across 9 CRITICAL findings + ~25 new tests for manager real implementations + coverage gate work. 2 cycles is unrealistic.

**Amendment**: PR-11 cycles = 6-8. Total sprint cycles: **25-30** (was 21).

### Amendment 13: Explicit deprecation shim for `tenant_id=None`

**Problem**: downstream users who upgrade will face hard failures when they call `db.express.list("User")` without a `tenant_id` on a `multi_tenant=True` model. Even with the CHANGELOG note, that's a deployment cliff.

**Amendment**: add a `DEPRECATION_GRACE` mode to DataFlow:

- When `DataFlow(deprecation_grace="1.x-to-2.x")` is set, missing `tenant_id` on `multi_tenant=True` models logs `ERROR dataflow.deprecation.tenant_required {...}` AND falls back to a system tenant (with loud warning)
- After one minor release, the grace mode is removed and the hard raise takes over
- This gives users a deploy-window to migrate without a production outage

### Amendment 14: PR-6a must ship with issue-354's existing plan, not re-derive

**Problem**: the perfection plan was about to re-derive the fabric fix. The issue-354 workspace already has a red-teamed plan with 6 amendments.

**Amendment**: PR-6a = exactly what `workspaces/issue-354/02-plans/01-fix-plan.md` says, with the red-team amendments from `workspaces/issue-354/04-validate/01-red-team-findings.md` applied. Do not rewrite. Do not duplicate work.

## New findings from red team that were not in the audit

### Finding A: Version mismatch between `pyproject.toml` and `dataflow/__init__.py`

Current state: `dataflow/__init__.py:95 __version__ = "1.7.1"` vs the `1.8.0` claim in the audit. This is a `rules/zero-tolerance.md` Rule 5 violation (split version state). Add to PR-0: verify the version string matches pyproject.toml on branch creation.

### Finding B: `dataflow/trust/` is the seed of Terrene Foundation's trust-plane integration

Not dead code — a deliberate integration surface awaiting wiring. Four downstream workspaces already reference it, and `docs/trust/trust-dataflow-integration.md` publishes the integration contract. Reclassified as WIRE (PR-6b sibling) — complete the integration per `rules/eatp.md` and `rules/trust-plane.md`, don't delete.

### Finding C: Impact-verse doesn't use `multi_tenant=True`

Verified in `tpc/impact-verse/src/` — `database.py`, `fabric/__init__.py`, `auth_fastapi_app.py`, `enhanced_agent_base.py`, `cache_service.py` all construct `DataFlow(...)` without `multi_tenant=True`. The default is `False` (`engine.py:84, 1923`). Reframing: Express cache leak is **CRITICAL LATENT**, not **CRITICAL ACTIVE**. Severity unchanged; immediacy reduced.

## Sequencing diagram (post-amendment)

```
Branch 1: fix/dataflow-security-urgent (ships as 1.8.1)
  └── PR-1 (security fixes + _safe_identifier stopgap)
       └── merge to main
            └── release 1.8.1

Branch 2: fix/354-fabric-redis-cache (ships as 1.9.0, existing workspaces/issue-354 plan)
  └── PR-6a (integrates issue-354 plan + red-team amendments)
       └── rebase on 1.8.1
            └── merge to main
                 └── release 1.9.0

Branch 3: fix/dataflow-perfection (ships as 2.0.0)
  └── branched from 1.9.0
  ├── PR-0 (foundation + CI guards + version bump to 2.0.0-dev.1 + Rust issues filed)
  ├── PR-2 (façade managers real implementations) — serialize on multi_tenancy.py
  ├── PR-3 (orphan sweep with dependent manifest) — serialize on shared files
  ├── PR-4 (adapters + dialect consolidation) — serialize on adapters
  ├── PR-5 (Express cache tenancy)
  ├── PR-6b (fabric endpoint Nexus wiring)
  ├── PR-6c (multi-webhook-source adapters)
  ├── PR-7 (model registry async + 13 sites)
  ├── PR-8 (nodes + query + auto-migrate + classification wire)
  ├── PR-10 (observability overhaul)
  ├── PR-11 (test rewrite — 6-8 cycles)
  ├── PR-12 (docs + CHANGELOG)
  ├── PR-13 (rule extensions — now a PR-0 prerequisite, not a PR-13 finalization)
  ├── PR-14 (cross-SDK Rust — parallel from PR-0, merged here)
  ├── PR-15 (impact-verse lockstep migration)
  └── release 2.0.0

Parallel track: kailash-rs mirror work runs from PR-0 onwards.
```

## Final verdict

**Plan is PASS WITH AMENDMENTS APPLIED.** With these 14 amendments, the plan is executable. Total sprint cycles: **25-30** (was 21). Three releases: 1.8.1 (security, 1-2 cycles), 1.9.0 (fabric, 3-4 cycles), 2.0.0 (remaining, 20-24 cycles).

Ready for `/todos` human approval gate.
