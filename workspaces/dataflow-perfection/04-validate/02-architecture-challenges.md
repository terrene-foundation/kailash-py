# Architecture + Strategy Red Team

## Verdict: PASS WITH AMENDMENTS — blocking deletions, wrong severity framing, wrong version strategy

The plan's technical decomposition is mostly sound. The analysis is extraordinary in depth. But the strategy layer has **three blocking errors** (deletion safety, severity miscalibration on Express, version bump timing) and several MAJOR architectural decisions that need inversion before `/implement` is cleared.

---

## Top architectural challenges

### C1. Express cache "active data leak" severity is inflated for the real consumer [BLOCKING]

**Challenge.** Executive summary §9 and the fix plan treat Express cache cross-tenant leakage as a CRITICAL-ACTIVE production vulnerability that "justifies pulling forward the entire sprint". But it is active only when `DataFlow(multi_tenant=True, redis_url=...)`. Both flags are required; both default off.

**Evidence.**

- `packages/kailash-dataflow/src/dataflow/core/engine.py:84` and `:1923` — `multi_tenant: bool = False` default
- impact-verse audit: `grep -rn 'multi_tenant=True' /Users/esperie/repos/tpc/impact-verse/src` returns ZERO matches in production source (one skill doc reference). Every `DataFlow(...)` call site in impact-verse (`database.py:64/67/77`, `fabric/__init__.py:114`, `auth_fastapi_app.py:311`, `enhanced_agent_base.py:214`, `cache_service.py:83`) constructs DataFlow without `multi_tenant`.
- impact-verse DOES pass `redis_url` — so the Redis path is wired, but without `multi_tenant=True` the tenant-partitioning bug does not trigger cross-tenant reads because there is only one tenant namespace.

**What this means.** The bug is REAL and CRITICAL as a latent security defect. But the "bigger than #354 because Redis is wired today" framing in the executive summary is factually wrong for the named downstream consumer. No live cross-tenant leak is occurring at impact-verse today. The urgency collapse means PR-5 does not need to pre-empt PR-6 for "production exposure" reasons — it can parallelize.

**Recommendation.** Downgrade the Express bug from "actively leaking today at impact-verse" to "latent CRITICAL — will leak the moment any consumer enables `multi_tenant=True` with Redis". Rewrite executive summary §9 to say so. This is still CRITICAL and still blocks release, but the plan's sequencing does not need to be distorted around a phantom production fire.

**Severity if unaddressed: BLOCKING** — misframing severity leads to wrong sequencing and misleads the human approval gate.

---

### C2. Deletion candidates with non-zero external importers [BLOCKING]

**Challenge.** PR-3 commits to deleting `dataflow/trust/`, `dataflow/classification/`, `dataflow/performance/`, `dataflow/compatibility/`. Ripgrep across the entire monorepo and downstream ecosystem shows these are NOT orphans.

**Evidence.**

| Candidate                                             | External importers                                                                                                                                                                                                                                                                                                                                                                                                    | Source              |
| ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------- |
| `dataflow/classification/`                            | **engine.py:13 and engine.py:458** import `FieldClassification`, `ClassificationPolicy`, `classify`, `DataClassification`, `RetentionPolicy`, `MaskingStrategy` from live production code path                                                                                                                                                                                                                        | in-package          |
| `dataflow/trust/`                                     | **`docs/trust/trust-dataflow-integration.md`** lines 30/51/71/416 document public API; **4 separate workspaces** in `rr/agentic-os`, `rr/rr-agentic-os`, `rr/rr-aegis`, `dev/aegis` have `care-implementation/02-plans/01-sdk-implementation/03-dataflow-nexus-integration.md` that prescribes `dataflow.trust.query_wrapper`, `dataflow.trust.audit`, `dataflow.trust.multi_tenant` as the CARE integration contract | downstream planning |
| `dataflow/performance/`                               | **official doc** `packages/kailash-dataflow/docs/advanced/sqlite-enterprise-features.md` (lines 146/269/689) imports `SQLitePerformanceMonitor`; live tests in `tests/integration/test_sqlite_enterprise_features.py` and `tests/integration/schema/test_streaming_schema_comparator_integration.py`                                                                                                                  | in-package docs     |
| `dataflow/compatibility/`                             | `compatibility/migration_path.py` actively imports from `compatibility/legacy_support.py` — internal cohesion, not orphan                                                                                                                                                                                                                                                                                             | in-package          |
| `dataflow/platform/` (except Inspector/ErrorEnhancer) | `dataflow.platform.inspector` consumed by `debug/`, `cli/analyze.py`, `cli/debug.py`, `cli/validate.py`, `cli/generate.py`, official skill doc `dataflow-troubleshooting.md`, every debug_agent example                                                                                                                                                                                                               | in-package + skills |

**What this means.** The plan's "orphan" classification was based on a narrow grep limited to `packages/kailash-dataflow/src/`. Four out of five major deletion targets have active importers OR are the backing for documented public APIs OR are the declared integration point for CARE. Any one of these deletions as currently scoped will break published documentation and downstream planning.

**Recommendation.**

1. `dataflow/classification/` — RECLASSIFY from "delete or wire" to **wire**. It is already imported by `core/engine.py`. Decision is already made implicitly by the code. PR-8's "either-or" framing is wrong; pick "wire" now.
2. `dataflow/trust/` — RECLASSIFY from "delete or wire" to **wire**. The downstream CARE implementation has four independent workspaces calling it out as the integration surface. Deleting it would violate `rules/cross-sdk-inspection.md` (cross-SDK contract break) and destroy published rollout plans. Wire it into `core/audit_integration.py` + `core/nodes.py` query interception per the audit recommendation. This is the seed of the Terrene Foundation's trust-plane integration — the very thing `rules/independence.md` exists to protect.
3. `dataflow/performance/` — RECLASSIFY. `SQLitePerformanceMonitor` has documented public examples. Audit which classes are genuinely orphan and delete only those. Keep `SQLitePerformanceMonitor` and whatever is consumed by the official doc.
4. `dataflow/platform/` — the plan already carves out Inspector + ErrorEnhancer; confirm the carve-out covers every importer above before deletion.

**Severity if unaddressed: BLOCKING** — a bulk `rm -rf` on these directories breaks published documentation, violates the cross-SDK inspection rule, and orphans four downstream CARE implementation plans mid-flight.

---

### C3. Version strategy: security should ship as 1.8.1 independently [MAJOR]

**Challenge.** The plan cascades all 14 PRs through a 2.0.0 major bump. The security fixes (PR-1) have no API surface change — they are parameterization, validation, deletion of an RCE node. They can ship as a patch bump TODAY.

**Evidence.**

- PR-1 deliverables are all internal: SQL parameterization, identifier quoting, deletion of `DynamicUpdateNode` (zero external consumers confirmed by plan §PR-3), replacement of fake encryption with Fernet (the public `encrypt_tenant_data` signature can be preserved).
- PR-2 onwards introduces real API shape changes: `TransactionManager` becomes real (behavior change), `ConnectionManager.health_check()` returns real state (behavior change), `FabricRuntime.product_info` becomes async (signature change), fabric endpoints require `nexus` parameter (signature change). THESE are the breaking changes that justify 2.0.0.
- The user explicitly said the current plan constrains the sprint to "~21 cycles". Even on the 10x autonomous multiplier, 21 cycles is multi-week calendar time. Meanwhile eight CRITICAL security findings sit unpatched. The plan's own release gate §Release requires "every PR merged" before a single security fix ships.

**Recommendation.**

- **Ship PR-1 as 1.8.1** on a dedicated branch `fix/dataflow-security-1.8.1` within 1-2 cycles. Cherry-pick from `fix/dataflow-perfection` or develop in isolation.
- Coordinate with impact-verse so they can bump their pin to 1.8.1 immediately.
- PR-0 and PR-2 onwards land on `fix/dataflow-perfection` → 2.0.0 as currently planned.
- The "nine critical security findings in production unpatched for 3 weeks while we do the perfection work" is a risk the plan does not acknowledge. `rules/zero-tolerance.md` Rule 1 ("if you found it, you own it — fix in THIS run") implicitly requires the fastest possible delivery of security fixes.

**Severity if unaddressed: MAJOR** — delaying security fixes behind a 21-cycle refactor is the exact pattern `zero-tolerance.md` exists to prevent.

---

### C4. PR-1 merge-conflict risk is understated [MAJOR]

**Challenge.** The sequencing table says PR-1 blocks PR-2/PR-3/PR-5/PR-6/PR-11 but the plan still allows PR-2, PR-3, PR-4 to run in parallel. All four touch `core/multi_tenancy.py`, `adapters/*.py`, `core/nodes.py`.

**Evidence of shared-file collisions.**

- PR-1 item 1 edits `core/multi_tenancy.py` at 13 sites. PR-2 item 4 deletes `TenantSecurityManager` in the same file at `:903`. PR-3 orphan-deletion list includes `core/multi_tenancy.py::TenantSecurityManager`. Three-way conflict.
- PR-1 item 5 edits `adapters/postgresql.py`, `mysql.py`, `sqlite.py`, `sqlite_enterprise.py` for identifier quoting. PR-3 deletes `sqlite_enterprise.py` entirely. PR-4 rewrites `postgresql.py::execute_transaction` and `adapters/dialect.py`. Three-way on every adapter file.
- PR-1 item 6 edits `core/nodes.py` field whitelist. PR-8 also edits `core/nodes.py` for query filter whitelist, LIKE escaping, pagination cap, classification wiring. Two-way.
- PR-5 and PR-6 both edit the cache key layer. PR-5 rewrites `cache/key_generator.py`; PR-6 adds fabric-specific wrapping.

**Recommendation.** Serialize PRs that touch the same files. Updated dependency graph:

```
PR-0 → PR-1 → (PR-2, PR-3) serial on multi_tenancy.py
         ↓
        PR-3 → PR-4 → (PR-5 ‖ PR-6) serial on cache/
         ↓                  ↓
        PR-8 → PR-11     PR-10
```

PR-2 and PR-3 cannot parallelize where they share `multi_tenancy.py`. PR-3 and PR-4 cannot parallelize where they share adapter files. Update the parallelizability column in §Gating.

**Severity if unaddressed: MAJOR** — merge conflicts will burn cycles and the autonomous multiplier evaporates when agents block on rebases.

---

### C5. PR-6 is overloaded — fabric scope creep [MAJOR]

**Challenge.** PR-6 as written contains: the issue-354 fix plan (Redis cache, amendments A/B/C/D/E), endpoint wiring into Nexus (6 endpoints × 4 webhook providers), `FabricScheduler` wiring, `tenant_extractor` invocation, `FabricMetrics` wiring, and webhook source adapters for GitHub/GitLab/Stripe/Slack. That is 4 distinct features bundled into a bug-fix PR.

**Evidence.** Plan §PR-6 deliverables 1-15. Item 10 is net-new endpoint registration (architectural wiring). Item 11 is net-new webhook providers. Item 12 is a scheduler, which is arguably an entirely new runtime subsystem. Item 14 is metrics wiring dependent on PR-10 which has not landed yet.

**Recommendation.** Split PR-6 into:

- **PR-6a**: issue-354 fix — `fabric/cache.py` Redis backend, amendments, `_redis_url` plumbing, `_queue` deletion, `_get_or_create_redis_client`. Matches `workspaces/issue-354/02-plans/01-fix-plan.md` exactly.
- **PR-6b**: endpoint wiring into Nexus — accept `nexus: Nexus` parameter, register all 6 endpoint handlers, `tenant_extractor` invocation, health endpoint.
- **PR-6c**: multi-source webhook adapters (GitHub/GitLab/Stripe/Slack) with HMAC verification regression tests per provider.
- **PR-6d**: `FabricScheduler` wiring + leader-side execution. This is a real feature addition; it should have its own acceptance review. If it feels too big to include in this sprint, it becomes PR-6d deferred or a follow-up — the plan currently bolts it onto a bug fix without that deliberation.

**Severity if unaddressed: MAJOR** — an overloaded PR is unreviewable, un-rollback-able, and a single conflict forces the whole bundle to re-land.

---

### C6. PR-3 is feasible as one PR but must be split for safety by category [MAJOR]

**Challenge.** 18,400 LOC in one PR is technically mergeable but unreviewable. The plan's own §PR-3 process acknowledges this by requiring batch-of-10 checkpoints.

**Recommendation.** Carve PR-3 into:

- **PR-3a** (confirmed orphan, zero importers): `dynamic_update.py` (already covered by PR-1 deletion), `web/`, `migration/` (singular, dead), `validators/` (plural, dead), dead parallel init path in `cache/`, dead pair in fabric pipeline.
- **PR-3b** (duplicate consolidation): SQLite adapter merge, three-dialect → one-dialect, three CircuitBreaker → one, two DataFlowError → one, two HealthStatus → one, two RetentionPolicy → one.
- **PR-3c** (contentious deletions deferred OR wired): `trust/`, `classification/`, `performance/` (partial), `compatibility/`, `optimization/` — these go through a WIRE decision first (see C2), and whatever truly is dead gets deleted in a smaller, clearly scoped PR.

Each PR-3x is <5k LOC and independently reviewable. `wc -l` target for the whole bundle stays ~18,400.

**Severity if unaddressed: MAJOR** — 18,400 LOC in one diff cannot be red-teamed.

---

### C7. "Library that raises" vs "library that degrades" [MAJOR]

**Challenge.** Plan PR-1 item 1 says missing `tenant_id` raises `InvalidTenantIdError`. PR-5 item 1 says missing `tenant_id` raises `FabricTenantRequiredError`. PR-2 item 1 says `TransactionManager` exceptions propagate. PR-8 item 2 says auto-migrate failures raise. DataFlow is a library consumed by Nexus, Kaizen, user FastAPI apps — aggressive raising cascades to user-visible 500s.

**Evidence.** `rules/communication.md` § "Report in Outcomes" implies library-level errors must surface to users as actionable impact, not stack traces. Nexus and Kaizen wrap DataFlow calls — they need error objects they can route, not uncaught raises.

**Recommendation.**

- Security failures (SQL injection attempt, invalid tenant_id format) → RAISE loudly. These are attacks; callers must not swallow them.
- Infrastructure failures (Redis down, Postgres reachability, migration SQL error) → surface through a structured `HealthStatus` + `DataFlowError` subtype AND emit a Prometheus `*_errors_total` increment AND raise. Callers can catch the specific subtype to degrade gracefully (read-only mode, cache-only mode) rather than 500ing.
- Configuration failures (fabric has product with `multi_tenant=True` but no `tenant_extractor`) → FAIL AT CONSTRUCTION, not at request time. Prevents the "the 10000th request is the first to discover your config is wrong" failure mode.

Add to PR-2 and PR-5 deliverables: define the `DataFlowError` taxonomy (`SecurityError`, `ConfigError`, `InfrastructureError`, `IntegrityError`) and document catch semantics.

**Severity if unaddressed: MAJOR** — inadequate error taxonomy means fixing one silent-failure bug creates a new noisy-failure bug at every consumer.

---

### C8. Cross-SDK timing: Rust work should parallelize, not defer to PR-14 [MAJOR]

**Challenge.** Plan PR-14 is "file cross-SDK Rust issues after everything else". That sequentializes what `rules/autonomous-execution.md` says should parallelize: independent agent specializations running concurrently.

**Evidence.** `rules/cross-sdk-inspection.md` and `rules/autonomous-execution.md` both mandate parallel execution across specializations. Every CRITICAL finding with a Rust parallel (query cache tenant isolation, fabric Redis cache, adapter sslmode forwarding, transaction wrapper, DDL parameterization) could be being fixed in kailash-rs RIGHT NOW by a parallel agent team while Python lands.

**Recommendation.** PR-14 splits into:

- **PR-14 (now)**: file all Rust cross-SDK issues at sprint kickoff, NOT at sprint end. Issues become the brief for a parallel Rust agent team.
- **Spawn parallel kailash-rs sprint** with identical 14-PR structure (minus things that don't apply) running concurrently in a worktree on the kailash-rs repo.
- Merge order is independent: Python and Rust each ship when their own red team converges. Cross-SDK issue closure requires both.

**Severity if unaddressed: MAJOR** — deferring Rust work 21 cycles means every Python security fix has a matching Rust-side attack surface open for 21 cycles.

---

### C9. Downstream migration partnership is too thin [MAJOR]

**Challenge.** Plan §Impact on downstream consumers says "impact-verse will need to explicitly set tenant_id on every Express operation. Breaking change documented in CHANGELOG." That is not a migration partnership — it is a release note.

**Recommendation.**

- Add **PR-15** (new): impact-verse lockstep migration. impact-verse runs on a `feat/dataflow-2.0-migration` branch in parallel with `fix/dataflow-perfection`. Each breaking change in DataFlow lands an impact-verse patch in the same cycle. By the time DataFlow 2.0.0 releases, impact-verse main branch has already proved the migration works.
- Add a dedicated cycle for impact-verse's `auth_fastapi_app.py`, `database.py`, `workflows/*.py` migration — every `db.express.*` call site must pass `tenant_id` if the consumer opts into `multi_tenant=True`, or explicitly remain on `multi_tenant=False`.
- Provide a compat shim: DataFlow 2.0.0 accepts `tenant_id=None` with a `DeprecationWarning` for one minor release (2.0.x) before 2.1.0 hard-raises. This is the standard library-compatibility path and it's missing from the plan entirely.

**Severity if unaddressed: MAJOR** — shipping a 2.0.0 with zero deprecation path breaks every downstream on release day. `rules/git.md` PR discipline and `rules/testing.md` state-persistence verification assume continuous integration with downstream; a hard break violates both.

---

### C10. Classification and encryption should unify, not split [MINOR → MAJOR]

**Challenge.** PR-1 replaces fake `encrypt_tenant_data` with Fernet. PR-8 decides whether to wire `@classify("email", PII, ..., REDACT)`. These are the same feature — field-level data protection. They should be one subsystem with a single decision point.

**Recommendation.** Merge into a single PR (absorbed into PR-2 or new PR-2b) that defines:

- A `FieldProtectionPolicy` subsystem: `classification` metadata on fields + `EncryptionKeyProvider` interface + `RedactionPolicy` + enforcement at read/write interception points in `core/nodes.py`.
- Fernet becomes the default `EncryptionKeyProvider`; `@classify` becomes the declarative metadata API.
- PR-1 keeps the RAW security fix (delete fake encryption, replace with a real primitive). The full field-protection wiring is a dedicated PR built on top.

**Severity if unaddressed: MAJOR** — splitting related work across PRs that don't know about each other produces two half-implementations that never reconcile. This is exactly the pattern that created the façade-manager mess in the first place.

---

### C11. "Façade-manager" framing misses the root cause [MAJOR]

**Challenge.** Pattern A in the executive summary names the problem "façade-manager anti-pattern". The deeper problem is **premature public-API commitment without implementation**. The managers are symptoms; the root cause is that DataFlow's public surface (`db.transactions`, `db.connection`, `db.tenants`) was designed and exposed as a docstring contract before any backing was built.

**Why the distinction matters.**

- "Façade-manager" framing → solution is "implement the managers". Plan does this in PR-2.
- "Premature public API" framing → solution is ALSO to ask: was the public API right? Does `db.transactions.transaction()` belong on the DataFlow object at all, or does a transaction belong to a connection/session scope? Does `db.connection` as a public attribute make sense, or should users interact through explicit session objects the adapter returns?

**Recommendation.** Before PR-2 lands, convene a 1-cycle API design review: for each of the 7 façade managers, ask "is the public surface the right shape?" before implementing it. Cheap opportunity to fix shape now, impossible after 2.0.0 ships.

Add to PR-2 as deliverable #0: "API review memo — for each manager, document whether the current shape is the target or a backward-compat wrapper. If backward-compat, define the target shape and schedule 2.1.0 migration."

**Severity if unaddressed: MAJOR** — implementing a bad API shape perfectly is still a bad API shape. 2.0.0 locks it in.

---

### C12. "~21 cycles" estimate is wrong [MINOR]

**Challenge.** 21-cycle estimate depends on PR parallelization that C4 shows cannot happen cleanly. Upward pressure: serialization from file collisions, security 1.8.1 branch cherry-pick work, impact-verse lockstep PR, API review memo, trust/classification wire-in.

Downward pressure: if PR-14 Rust work genuinely parallelizes in a separate worktree with a separate agent team, it doesn't count against Python critical path.

**Evidence.** Plan §Gating shows critical path "PR-0 → PR-1 → PR-3 → PR-4 → PR-6 → PR-10 → PR-11 → release" = 7 serial steps. With C5's PR-6 split and C6's PR-3 split, critical path grows to ~10 serial steps. Each step is 1-2 cycles = 10-20 cycles critical path alone, plus parallel work = **25-30 cycles total** for Python.

**Recommendation.** Update estimate to 25-30 autonomous cycles. Make the user-facing framing "3-4 weeks of continuous autonomous execution" and set expectations accordingly. The user said "regardless of cost" — fine, but the estimate should be honest about what that buys.

**Severity if unaddressed: MINOR** — wrong estimate doesn't block work but misleads the human at the approval gate.

---

### C13. Guardrail against "don't unfix" regression [MAJOR]

**Challenge.** The plan has no mechanism to prevent a future PR (inside this sprint or after) from re-introducing a stub, fake encryption string, f-string logger, or dict-backed manager. PR-13 adds new rules but rules without enforcement are exactly how we got here.

**Recommendation.** Add to PR-0:

1. Pre-commit hook: `grep -rn "encrypted_" src/dataflow/` MUST return zero.
2. Pre-commit hook: `grep -rn "logger\\.\\(info\\|error\\|warning\\|debug\\)(f\"" src/dataflow/` MUST return zero.
3. Pre-commit hook: `grep -rn "^\\s*print(" src/dataflow/` MUST return zero.
4. CI gate: AST walker that fails if any class named `*Manager` exposed on `DataFlow` has no integration test that touches real infrastructure (implements `rules/facade-manager-detection.md`).
5. CI gate: `rules/orphan-detection.md` automation — any class added in a PR with zero non-test importers fails the build.

Guardrails land in PR-0 so every subsequent PR lands under the new regime. PR-13's "rule extensions" becomes documentation of guardrails already enforced.

**Severity if unaddressed: MAJOR** — the whole sprint is worth only as much as the guardrail that prevents regression.

---

### C14. Test cycle budget in PR-11 is unrealistic [MAJOR]

**Challenge.** PR-11 bundles: 118 mock removals (30 files, average 4 mocks each), new regression tests for every CRITICAL finding (46 CRITICALs), state-persistence verification added to every Tier 2/3 write, enabling `pytest -W error` (which surfaces all the deferred warnings from PR-0), and coverage gate enforcement. Plan allocates ~2 cycles. Optimistic by 3-4x.

**Evidence.** Each mock removal requires: identifying what the mock was standing in for, provisioning a real-infra fixture for that dependency, verifying the test still captures the same intent, adding clean teardown. 118 × ~30 min per rewrite = realistic 60 hours agent wall-time, which at 10x ≈ 6 cycles just for mock removal. Plus 46 new regression tests for CRITICAL findings ≈ 2-3 cycles. Plus state-persistence augmentation ≈ 1 cycle.

**Recommendation.**

- Budget PR-11 at 6-8 cycles, not 2.
- Split into **PR-11a** (regression tests for CRITICAL — paired with the PR that fixes each finding, NOT deferred to PR-11) and **PR-11b** (mock removal + state-persistence + coverage gate).
- Testing-specialist agent runs in a dedicated worktree in parallel with fix PRs, writing regression tests the moment each fix lands.

**Severity if unaddressed: MAJOR** — the plan understates the testing-specialist's critical-path contribution, which is the main source of convergence confidence.

---

## PR structure amendments

| Original                 | Amended                                                                                                            | Rationale                                        |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------ |
| PR-1 (9 security fixes)  | PR-1a (SQL injection + identifier quoting), PR-1b (eval/exec deletion), PR-1c (fake encryption → Fernet primitive) | Reviewability; three distinct review specialties |
| PR-3 (18,400 LOC one PR) | PR-3a orphans, PR-3b duplicate consolidation, PR-3c contentious (after C2 wire decisions)                          | Reviewability; safety                            |
| PR-6 (fabric everything) | PR-6a issue-354 fix, PR-6b endpoint wiring, PR-6c webhook adapters, PR-6d scheduler                                | C5 reasoning                                     |
| PR-11 (all tests)        | PR-11a regression paired with each fix PR, PR-11b mock removal / coverage / state persistence                      | C14 reasoning                                    |
| (new) PR-15              | impact-verse lockstep migration branch                                                                             | C9 reasoning                                     |

Result: 14 PRs → ~19 PRs. Longer PR list, each <5k LOC, each reviewable, each rollback-able.

## Dependency graph corrections

- `PR-2` and `PR-3` cannot parallelize on `core/multi_tenancy.py` deletions — serialize.
- `PR-3` and `PR-4` cannot parallelize on `adapters/*.py` edits — serialize.
- `PR-5` and `PR-6a` can parallelize (different cache layers) but PR-6b depends on PR-5's tenant key format.
- `PR-14` (Rust issue filing) moves to sprint kickoff, not end. Rust fix work becomes a parallel sprint in kailash-rs worktree.
- `PR-13` (guardrails) moves to PR-0 so every subsequent PR lands under enforcement.

## Version strategy recommendation

Ship **DataFlow 1.8.1** immediately with PR-1 cherry-picked. This is a pure security patch, no behavior changes for consumers who weren't exploiting the holes. impact-verse bumps pin to 1.8.1 same day.

**DataFlow 2.0.0** ships when the rest of the sprint converges. Include **1 deprecation release 2.0.x** that accepts `tenant_id=None` with `DeprecationWarning` before 2.1.0 enforces.

## Cross-SDK timing recommendation

- File Rust issues at sprint kickoff (not sprint end). Use them as the Rust sprint brief.
- Run kailash-rs fix sprint in parallel worktree with its own agent team and 14-PR structure. Python and Rust have independent release gates; cross-SDK inspection rule closure blocks both.

## Downstream migration recommendation

- Add **PR-15**: impact-verse `feat/dataflow-2.0-migration` branch runs in lockstep with `fix/dataflow-perfection`. Every DataFlow breaking change lands a same-cycle impact-verse patch.
- Provide **2.0.x deprecation shim** for `multi_tenant` + `tenant_id` path — one minor release of `DeprecationWarning`, then 2.1.0 enforces.
- Coordinate with impact-verse deployment owner BEFORE sprint start so their migration cycles are allocated.

## Open questions for the human approval gate

1. **Security independence**: Do we ship PR-1 as 1.8.1 this week, or wait for 2.0.0 (3-4 weeks)? Given impact-verse exposure, strongly recommend 1.8.1.
2. **Trust/classification decision**: Wire or delete? Evidence says wire (downstream CARE plans exist). Does the human agree?
3. **impact-verse lockstep**: Will the impact-verse deployment owner commit to a `feat/dataflow-2.0-migration` branch running in parallel? If no, the 2.0.0 release stalls at the downstream migration gate.
4. **Breaking change via deprecation shim**: 2.0.0 hard-break or 2.0.x soft-break via DeprecationWarning? Strong recommendation: soft-break.
5. **API design review**: Spend 1 cycle reviewing the shape of 7 façade managers before implementing them? Strong recommendation: yes.
6. **Scheduler scope**: Is `FabricScheduler` in-scope for this sprint (PR-6d) or follow-up? The plan currently bolts it onto a bug-fix PR with no explicit deliberation.

## Final plan amendment list (what must change before /implement)

1. **Executive summary §9** — rewrite to say Express leak is CRITICAL LATENT, not CRITICAL ACTIVE, since impact-verse does not set `multi_tenant=True`. Severity unchanged; urgency framing corrected.
2. **PR-1** — split into 1a/1b/1c OR keep as one but add explicit commit sequencing within the PR.
3. **PR-1** — add deliverable: ship as **1.8.1** on a dedicated branch within 1-2 cycles, independent of 2.0.0 sprint. Coordinate with impact-verse pin bump.
4. **PR-2** — add deliverable #0: API review memo for all 7 façade managers before implementation.
5. **PR-2** — add deliverable: `DataFlowError` taxonomy (SecurityError / ConfigError / InfrastructureError / IntegrityError) with documented catch semantics.
6. **PR-3** — split into 3a/3b/3c. Reclassify `trust/`, `classification/`, `performance/`, `platform/`, `compatibility/` from "delete or wire" to explicit decisions: trust WIRE, classification WIRE, performance PARTIAL-DELETE (keep SQLitePerformanceMonitor), platform KEEP Inspector+ErrorEnhancer+cli dependencies, compatibility AUDIT.
7. **PR-3** — add deletion safety log: before any `rm`, run full-repo ripgrep including `docs/`, `examples/`, downstream workspaces (`rr/`, `dev/aegis/`, `tpc/impact-verse/`). Block deletion if any external importer found.
8. **PR-5 and PR-6** — update cache layer edits to serialize, not parallelize.
9. **PR-6** — split into 6a (issue-354), 6b (endpoint wiring), 6c (webhook adapters), 6d (scheduler). Re-evaluate 6d scope.
10. **PR-8 "classification decision"** — resolve NOW as WIRE. Delete the either-or framing.
11. **PR-11** — split. Regression tests paired with each fix PR. Mock removal, coverage gate, state-persistence stay in PR-11b. Budget 6-8 cycles, not 2.
12. **PR-13 / PR-0** — move guardrails (pre-commit hooks, facade-manager AST check, orphan-detection CI) to PR-0 so every PR lands under enforcement.
13. **PR-14** — move cross-SDK Rust issue filing to sprint kickoff. Spawn parallel Rust sprint in worktree.
14. **NEW PR-15** — impact-verse lockstep migration branch `feat/dataflow-2.0-migration` with same-cycle patches for every DataFlow breaking change.
15. **Deprecation shim** — DataFlow 2.0.x accepts `tenant_id=None` with DeprecationWarning; 2.1.0 enforces. Add to PR-5 deliverable.
16. **Cycle estimate** — update from "~21" to "25-30 autonomous cycles, critical path 10-12 sequential".
17. **Impact on downstream** section — expand from 5 lines to a full migration playbook per downstream consumer (impact-verse, aegis CARE, any `rr/` project).
18. **Deletion rule** — add to `rules/zero-tolerance.md` or new `rules/deletion-safety.md`: no directory deletion without proof of zero external importers via monorepo-wide grep AND sweep of `docs/` AND sweep of downstream workspaces. This is the safeguard that would have prevented the `trust/`/`classification/` mistakes in this very plan.
