# SDK Release Configuration

## Build System

- **Tool**: setuptools (pyproject.toml)
- **Python**: >=3.11

## Publishing

- **Registry**: PyPI (production), TestPyPI (validation)
- **Method**: Trusted Publisher (OIDC) via GitHub Actions
- **Trigger**: Git tags (`v*` for core, `kaizen-v*` for Kaizen, etc.)
- **Workflow**: `.github/workflows/publish-pypi.yml`
- **Strategy**: Tag-triggered automated publishing. No manual twine uploads.

## Packages

| Package          | Tag Pattern        | Current Version |
| ---------------- | ------------------ | --------------- |
| kailash (core)   | `v*`               | 2.17.0          |
| kailash-dataflow | `dataflow-v*`      | 2.8.1           |
| kailash-kaizen   | `kaizen-v*`        | 2.20.0          |
| kailash-nexus    | `nexus-v*`         | 2.8.0           |
| kailash-pact     | `pact-v*`          | 0.11.0          |
| kailash-ml       | `ml-v*`            | 1.7.2           |
| kailash-align    | `align-v*`         | 0.7.0           |
| kailash-mcp      | `mcp-v*`           | 0.2.12          |
| kaizen-agents    | `kaizen-agents-v*` | 0.9.5           |

Last updated: 2026-05-31 — single-package minor release closing issue #1174 (PR #1214, Shard 5): `kailash-nexus 2.7.0 → 2.8.0` — Nexus FastAPI parity, final AC (migration guide + version owner). Shards 1–4 (PRs #1210/#1211/#1212/#1213) shipped the `nexus.extractors` sub-module (`Depends`/`Request`/`UploadFile`/`Multipart`/`Bytes`/`Headers`/`NexusHandlerError` + `DependencyOverrideMap`), `Nexus.handler_extract` resolver chain, `Nexus.dependency_overrides` test-injection map, `Nexus.register_sse` primitive (`register_sse_endpoint` now a shim), and the `register_websocket` callback overload — all backwards-compatible, no new top-level `fastapi` dep (Starlette re-exports). Shard 5 adds `docs/migration-fastapi.md` (474 lines, 9 sections). Stale-plan correction caught at implement: the outline documented a `Body[T]` typed-body extractor + `register_decoder` that were DEFERRED at the Q3 gate (absent from shipped `__all__`); guide §2 documents the shipped flat-input + `Bytes` story and §9 lists `Body[T]`/`Query` as not-yet-ported (no phantom imports per `spec-accuracy.md` MUST-1). reviewer APPROVE (6/6 mechanical sweeps) + security-reviewer APPROVE (zero findings; bounded file reads, fail-closed auth samples, `Body[T]`-deferred claim verified against source). Full Python 3.11–3.14 matrix + DataFlow/PACT/infrastructure CI green on PR #1214. Admin-merge → `main` `37f543643` (issue #1174 auto-closed) → lightweight tag `nexus-v2.8.0` → publish-pypi.yml run `26711302363` succeeded (TestPyPI skipped per minor-release exception with explicit human approval — matrix CI + both gates clean). Clean-venv install verified live: `nexus.__version__ == "2.8.0"` + extractors + `handler_extract`/`register_sse`/`register_websocket` all importable. SDK pin `kailash>=2.28.1` already PyPI-resolvable; no framework pin sweep needed. Deployment record: `deploy/deployments/2026-05-31-nexus-v2.8.0.md`. No sibling drift — all 7 other framework packages AT-PARITY with PyPI at release-time enumeration.

Prior 2026-05-08 — single-package minor release closing issue #881 (PR #888): `kailash 2.16.1 → 2.17.0` — `DurableExecutionEngine.workflow_blob` JSON serialization contract. `_enqueue_for_run` previously enqueued `Task(workflow_blob=b"", ...)` because the engine had no built-in serializer; cross-process workers couldn't reconstruct without out-of-band registry access. Both producer surfaces (`WorkflowScheduler` + `DurableExecutionEngine`) now route through new shared helper `runtime/_workflow_blob.py::serialize_workflow_to_blob` so they emit byte-identical JSON for the same workflow. Workers reconstruct via `Workflow.from_dict(json.loads(blob.decode("utf-8")))`. Producer-boundary 8 MiB cap prevents worker OOM. Additive contract (workers ignoring `workflow_blob` keep working). Side-benefit: W6 redaction consumer's `_redact_workflow_blob` now actually fires for engine-dispatched paths (pre-fix `json.loads("")` raised non-fatally and redaction never ran). 6 Tier-1 + 3 regression tests. Both gates approved on PR #888 (reviewer + security-reviewer, no findings; one LOW addressed in CHANGELOG addendum). Release-prep PR #889 auto-skipped PR-gate matrix per `release/v*` convention; admin-merge → tag `v2.17.0` → publish-pypi.yml run `25537573033` succeeded (TestPyPI skipped per minor-release exception with explicit human approval — Python 3.11–3.14 matrix CI on PR #888 pass + reviewer/security gates clean). Clean-venv install verified live: `kailash.__version__ == "2.17.0"` + `serialize_workflow_to_blob` importable + `MAX_WORKFLOW_BLOB_BYTES == 8388608` from both helper and scheduler back-compat alias + `DurableExecutionEngine` importable. Deployment record: `deploy/deployments/2026-05-08-v2.17.0.md`. No sibling drift — all 8 framework packages AT-PARITY with PyPI at release-time enumeration; framework `kailash>=2.16.0` pins admit 2.17.0 (minor backward-compat) so no framework-package release required. Follow-up surfaced (not blocking): #891 — `HybridSearchNode` name collision between `kailash-dataflow` and `kailash-kaizen` (both register the same string name into the global node registry; pre-existing since 2026-03-11 monorepo refactor `b553104c`).

Prior 2026-05-06 — single-package patch release closing issue #835 (PR #842): `kailash-dataflow 2.7.8 → 2.7.9` — `db.transactions.transaction()` no longer raises `RuntimeError: Event loop is closed` when invoked from an event loop different from the one that constructed the DataFlow instance. `TransactionManager._get_adapter` now resolves the asyncpg pool via the same per-loop `_get_or_create_async_sql_node(db_type)._get_adapter()` priority chain used by `db.express.*` (priority chain `_shared_pools` → runtime pool → `_PROCESS_POOL_REGISTRY` → fallback under per-key creation locks; WeakValueDictionary-based reaping on loop close). `_get_adapter_from_context` (used by `TransactionScopeNode` / `TransactionSavepointNode`) converted to `async`; every caller awaits it. `ConnectionManager.initialize_pool` converted to transient reachability check (no long-lived `_connection_manager._adapter` retention); the init-time fail-fast contract from `dataflow-pool.md` Rule 2 preserved exactly. `_PoolWrapper` (internal, dead branch) deleted. Internal API removal carries no deprecation shim per `rules/zero-tolerance.md` Rule 6a internal-only carve-out. 9 Tier-2 regression tests at `tests/regression/test_issue_835_transaction_cross_loop.py` against real PostgreSQL (cross-loop `begin()`, nested savepoint/rollback, `TransactionScope` async-cm, concurrent two-loop `begin()`, WeakValueDictionary reaping, pool-cap stress 50 sequential loops). Spec: `specs/dataflow-cache.md` §12.1 (loop-affinity contract) + §13.4 (async transaction participation) updated. Admin-merge → tag `dataflow-v2.7.9` → publish-pypi.yml run `25420043122` succeeded (TestPyPI skipped per patch-release exception with human authorization — Python 3.11–3.14 matrix CI on PR #842 all pass + CodeQL + spec drift + infrastructure tests). Clean-venv install verified live: `dataflow.__version__ == "2.7.9"` + `TransactionManager._get_adapter` source contains `_get_or_create_async_sql_node` AND no `_PoolWrapper` reference + `ConnectionManager._adapter` field absent (no `self._adapter:` annotation). Deployment record: `deploy/deployments/2026-05-06-dataflow-v2.7.9.md`. No sibling drift — all 7 other framework packages AT-PARITY with PyPI at release-time enumeration.

Prior 2026-05-06 — single-package minor release closing issue #829 (PR #836): `kailash-kaizen 2.19.0 → 2.20.0` — replaces `Kaizen._generate_role_based_traits` keyword classifier with LLM-first `Signature`-driven derivation per `rules/agent-reasoning.md` Rule 1. New private `RoleToTraitsSignature` (`role: str → traits_csv: str`) constructed in a per-call `BaseAgent` with `temperature=0`. Per-Kaizen-instance bounded LRU cache (`OrderedDict`, max 256 entries, `popitem(last=False)` eviction) keyed by `role.strip().lower()`. Security hardening landed same-shard per security-reviewer: output sanitization regex `^[a-z0-9_ ]{1,32}$` (prompt-injection defense — protects downstream `_generate_role_based_prompt` system-prompt rendering); hashed `role_hash=<sha256[:8]>` + `raw_len=<int>` in WARN logs (PII-leakage defense per `rules/observability.md` Rule 8 spirit); bounded LRU (DoS defense). Failure mode change: `KAIZEN_DEFAULT_MODEL` unset OR LLM call failure → `RuntimeError` naming both escape hatches (`behavior_traits=...` config arg OR `.env` provider key). Test sweep per `rules/orphan-detection.md` Rule 4: rewrote `tests/regression/test_issue_822_behavior_traits_render.py::test_behavior_traits_default_from_role` to shape-only Tier-2 + `tests/unit/test_kaizen_multi_agent_coordination.py::test_specialized_agent_role_based_behavior_traits` to shape-only; new `tests/unit/conftest.py` autouse fixture stubs `Kaizen._generate_role_based_traits` for Tier-1 (replaces 36 individual call-site edits with one fixture); 6 new Tier-2 tests across `test_role_to_traits_llm_derivation.py` (4) + `test_role_traits_cache_wiring.py` (2). Spec: `specs/kaizen-core.md` §7.5 (Trait Derivation) added with full contract. Admin-merge → tag `kaizen-v2.20.0` → publish-pypi.yml run `25393777596` succeeded (TestPyPI skipped per minor-release exception with explicit human approval — Python 3.11–3.14 matrix CI on PR #836 all pass + CodeQL Python pass). Clean-venv install verified live: `kaizen.__version__ == "2.20.0"` + `RoleToTraitsSignature` importable + `Kaizen._TRAIT_CACHE_MAX == 256` + keyword classifier residue absent in `inspect.getsource` of `_generate_role_based_traits`. Deployment record: `deploy/deployments/2026-05-06-kaizen-v2.20.0.md`. No sibling drift — all 8 other framework packages AT-PARITY with PyPI at release-time enumeration.

Prior 2026-05-05 — single-package minor release closing issue #822 (PRs #825 + #826): `kailash-kaizen 2.18.2 → 2.19.0` (Shard 1 — Optional/None pyright cascade fix + `signature_programming` silent no-op gate, restoring the LLM-first signature-programming behavior; Shard 2 — dead MCP integration surface deletion, ~1155 LOC removed, 12 methods + 1 property on `kaizen.core.agents.Agent` and `kaizen.core.framework.Kaizen` that imported `..mcp.registry::get_global_registry` / `..mcp::AutoDiscovery` / `..mcp::MCPConnection` — modules that never existed in the kaizen source tree at any commit since the original `apps/`→`packages/` move `b553104c`; per `rules/zero-tolerance.md` Rule 2 + `rules/orphan-detection.md` Rule 3, deletion is the only valid disposition; LOC invariant regression test at `tests/regression/test_issue_822_loc_invariant.py`). Release-prep PR #827 auto-skipped PR-gate matrix per `release/v*` convention; admin-merge → tag `kaizen-v2.19.0` → publish-pypi.yml run `25382388831` succeeded (TestPyPI skipped per minor-release exception with human approval — structural deletion + type-only fixes covered by Python 3.11–3.14 matrix CI on Shards). Clean-venv install verified live: `kaizen.__version__ == "2.19.0"` + all 12 deleted surfaces absent (`hasattr` returns False on `expose_as_mcp_server` / `connect_to_mcp_servers` / `mcp_registry` / etc.) + canonical Agent/CoreAgent/Kaizen surfaces live. Deployment record: `deploy/deployments/2026-05-05-kaizen-v2.19.0.md`. No sibling drift — only kailash-kaizen needed release; the other 7 of 8 packages were AT-PARITY with PyPI.

Prior 2026-05-04 — single-package patch release closing issue #814 (PRs #818 + #820): `kailash-kaizen 2.18.1 → 2.18.2` (Shard 1 — 22 BaseTool override conformance + 12 Optional/None safety + Cluster D `ResearchAdapter` runtime bug; Shard 2 — vestigial research-integration subsystem deleted, ~5,019 LOC removed across 14 files including 5 src + 8 tests + 1 examples dir, `[research]` + `[web-search]` optional extras declared, `WebFetchTool._extract_text` bs4 silent-degradation converted to loud `ImportError`). publish-pypi.yml run `25323887979` succeeded (TestPyPI skipped per patch-release exception). Clean-venv install verified live: `kaizen.__version__ == "2.18.2"` + new `kaizen.research` 8-symbol surface imports + deleted orphan symbols (`FeatureManager`, `IntegrationWorkflow`) raise `ImportError`. Two follow-up issues filed: #821 (kaizen-agents test parity for `research_patterns/*`) + #822 (kaizen Optional/None typing in `core/`). Deployment record: `deploy/deployments/2026-05-04-kaizen-v2.18.2.md`. No sibling drift — only kailash-kaizen needed release.

Prior 2026-05-03 — six-package release closing the issue #781 cleanup workstream (T1-T5 merged via PRs #804/#805/#806/#807/#808): `kailash 2.13.3 → 2.13.4` (T4 core/runtime TODO-NNN comment-strip + T5 CI gate `.pre-commit-config.yaml::no-untracked-todo-nnn` + `tests/regression/test_no_untracked_todo_nnn.py` + `scripts/check_no_untracked_todo_nnn.sh`), `kailash-dataflow 2.7.5 → 2.7.6` (T1, 89 markers stripped), `kailash-kaizen 2.18.0 → 2.18.1` (T2, 80 markers stripped + #801 test fix), `kailash-nexus 2.6.0 → 2.6.1` (T4, 16 markers stripped), `kaizen-agents 0.9.4 → 0.9.5` (T3, 69 markers stripped), `kailash-mcp 0.2.10 → 0.2.11` (sibling sweep per `build-repo-release-discipline.md` Rule 1: W6-002 type fix + 10 ElicitationSystem Tier-2 tests + LOW-6 triage). All six PRs through admin-merge → 6 tags pushed sequentially → publish-pypi.yml (OIDC) workflow runs all `success`. Clean-venv install + import verification documented in `deploy/deployments/2026-05-03-v2.13.4-six-package-issue-781-release.md`. SDK dep pin sweep `kailash>=2.13.4` across all 8 framework packages (released 5 + align/pact/ml unreleased-this-cycle for consistency). Issue #781 closed.

Prior 2026-05-02 — paired release closing #761 + #762 + #763 + #764 + #779: `kailash 2.13.2 → 2.13.3` (catch-up release for #779's auth Rule 2 cleanup that landed without a same-PR version bump per `build-repo-release-discipline.md` Rule 5 — 7 NotImplementedError stubs eliminated across `src/kailash/{nodes,middleware}/auth/` per `zero-tolerance.md` Rule 2 § "Fake dispatch"), `kailash-kaizen 2.14.0 → 2.16.0` (two-minor jump combining PR #780's #761/#762 LlmDeployment.openai_compatible + anthropic_compatible escape-hatch presets + preset_name field, AND PR #783's #763 LlmDeployment.supports() capability matrix + #764 register_bedrock_region runtime override). Cross-SDK parity with kailash-rs PR #722/#724/#725/#726. Both via admin-merge → tag → publish-pypi.yml (OIDC) → workflow runs `25237480388` + `25237487960` succeeded. TestPyPI gate skipped on both with explicit human approval (kailash 2.13.3 is recap-only; kailash-kaizen 2.16.0 surfaces unit-tested with parametrized cross-SDK byte-match coverage and dual-reviewer APPROVED). Clean-venv install + import verification documented in `deploy/deployments/2026-05-02-v2.13.3-kaizen-v2.16.0.md`.

Prior 2026-05-01 — paired patch cut closing #767 + #768: `kailash 2.13.1 → 2.13.2` (durability_middleware short-circuits before draining `StreamingResponse` / `text/event-stream`, restoring SSE + cache-replay semantics for `EventSource` clients on `EnterpriseWorkflowServer`/`Nexus()` for #767), `kailash-dataflow 2.7.1 → 2.7.3` (skipping 2.7.2 — never tagged; `ListNodeCacheIntegration` invalidation patterns aligned with producer key shape for #750, plus `FieldTypeProcessor._resolve_type` now strips parameterized generics + handles PEP 604 `T | None` so `@db.model` accepts `list[str]` / `dict[str, Any]` on Python 3.11+ for #768). Both PRs through admin-merge → tag → publish-pypi.yml (OIDC) → clean-venv install verified live (`kailash==2.13.2` + `kailash-dataflow==2.7.3` import; `_resolve_type(list[str]) is list` + `durability_middleware` source contains `StreamingResponse`). Cross-SDK loop closure for #759/#767/#768 still pending explicit human approval per `upstream-issue-hygiene.md` Rule 1.

Prior 2026-04-30 — the v2.13.0 cluster cut: `kailash 2.12.0 → 2.13.0` (adds `kailash.utils.lifespan` shared FastAPI helpers + patches 3 sibling FastAPI lifespan sites for #712), `kailash-nexus 2.4.1 → 2.5.0` (adds `Nexus.add_startup_handler` / `add_shutdown_handler` public API for #712), `kailash-dataflow 2.5.0 → 2.6.0` (lazy `runtime` `@property` + setter + `runtime=` kwarg for #713 + 6 subsystem captures → lazy lookups + DDL connection-reuse via `SyncDDLExecutor.execute_ddl_batch_per_statement` for #714). Three tags pushed individually (per multi-tag discipline), three `publish-pypi.yml` runs triggered. Specs landed in PR #728 (`specs/dataflow-core.md` §1.4/1.5/1.6.5 + `specs/nexus-core.md` §10.2/10.3 + `specs/nexus-services.md` §29). Cross-SDK: kailash-rs uses axum + Tokio (no equivalent custom-lifespan footgun for #712, no module-import event-loop binding for #713); analogous DDL connection thrash for #714 may exist — companion issue to be filed.

Prior 2026-04-28 (kailash-dataflow 2.3.3 patch — closes merged-but-unreleased gap from PRs #684 / #689 / #690: `not_null_handler.py` pyright cleanup + 8 migration unit-test mock-method-drift repairs. No production behavior change beyond type-checking cleanup; 13 pre-existing pytest warnings in the migrations suite remain on separate workstreams). kailash-ml 1.5.1 (PR #679) routes the `engines/model_registry.py` `ModelNotFoundError` through the canonical `kailash.ml.errors.ModelNotFoundError` (subclass of `ModelRegistryError → MLError`), removing the divergent local `class ModelNotFoundError(Exception)` that surfaced when the W7-001 LineageGraph walker raised canonical while `ModelRegistry.get_model` raised local. 6 raise sites converted to canonical kwargs; 3 regression tests pin class-identity + AST invariant. PR #679 also adds `scripts/development/find-venv-python.sh` — wrapper that resolves `.venv/bin/python` via `git rev-parse --git-common-dir` so pre-commit hooks run from inside `.claude/worktrees/<X>/` without the `core.hooksPath=/dev/null` bypass; 3 regression tests pin the worktree-safe invariants. Clean-venv install verified live: `kailash-ml==1.5.1` + `ModelNotFoundError canonical identity: OK` + `__all__ count: 50 (AST-derived)`. No sibling drift.

Prior 2026-04-27 — W7 portfolio remediation: kailash-ml 1.5.0 (PR #677 closes #657) ships the cross-engine `LineageGraph` engine module; kailash-dataflow 2.3.2 (PR #678) wires `format_error_for_event` through `emit_train_end` at the emitter.

## Release Runbook

1. Version bump in `pyproject.toml` + `__init__.py`
2. Update CHANGELOG.md
3. Run full test suite
4. Security review
5. Create release branch + PR
6. Merge PR (admin bypass)
7. Tag on main → triggers publish-pypi.yml
8. Verify PyPI install
9. Update COC template dependency pins
10. Document in `deploy/deployments/`

## Documentation

- **Build**: `cd docs && python build_docs.py`
- **Deploy**: Auto via `docs-deploy.yml` on push to main
- **Hosting**: GitHub Pages

## Versioning

- Lockstep: core SDK version bumps require framework dependency pin updates
- SemVer: major (breaking), minor (features), patch (fixes)

## Tag Convention

**IMPORTANT**: Use lightweight tags (NOT annotated) for release triggers.

```bash
# CORRECT — lightweight tag triggers GitHub Actions reliably
git tag v2.5.0
git push origin v2.5.0

# WRONG — annotated tag may NOT trigger publish-pypi.yml
git tag v2.5.0 -m "Release message"
```

GitHub Actions `push.tags` webhook processing handles lightweight tags
more reliably than annotated tags pushed after creation.

## Multi-Tag Release — Push Individually

When releasing multiple packages at once (coordinated patch release), tags
MUST be pushed individually, NOT in a single batch. Batch pushes of 3+ tags
fail to trigger the publish workflow reliably.

```bash
# CORRECT — push tags one at a time
git push origin v2.8.6
git push origin dataflow-v2.0.8
git push origin kaizen-v2.7.4
git push origin nexus-v2.0.2
git push origin mcp-v0.2.4

# WRONG — batch push silently skips workflow triggers
git push origin v2.8.6 dataflow-v2.0.8 kaizen-v2.7.4 nexus-v2.0.2 mcp-v0.2.4
# ↑ observed on 2026-04-14: ZERO of 5 tags triggered publish-pypi.yml.
# Required manual workflow_dispatch for each package.
```

**Why:** GitHub Actions' `push.tags` webhook delivery has undocumented
rate-limiting/batching behavior when multiple tags arrive in a single push
event. The first observed failure mode (2026-04-14): 5 tags pushed at once
triggered zero workflow runs. Individual pushes with a brief pause (≥1s)
between them trigger reliably.

**Recovery if a batch push was already done**: use `workflow_dispatch` to
manually trigger publishing for each affected package. The tags themselves
are still valid — only the auto-trigger was missed.
