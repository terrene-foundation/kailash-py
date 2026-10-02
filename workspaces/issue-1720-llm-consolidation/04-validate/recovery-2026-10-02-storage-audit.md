# CSQ16 storage recovery audit — 2026-10-02

Ran: canonical `pwd -P` and `git rev-parse --show-toplevel` both resolved to `<worktree-root>/csq16-recovery-storage-audit`; initial tree clean. Compared actual files in source-integration, storage-ci, runtime-ci and promotion-verification against dev `cdcaeac6baf63911d1f43ed99542002bdcd361a1`. No original worktree edits. Scope: DataFlow/storage/cache classification, not approval to reap or behavioral convergence.

Read DataFlow skill, dataflow-core/cache specs and offloading guide. Inventory selected all changed/untracked DataFlow package files plus DataFlow specs: 66 paths. Full SHA-256 groups and dev equality are in adjacent `recovery-2026-10-02-storage-audit-variants.json`. Hash control discriminated equal/unequal bytes; 215 existing Python copies passed AST parse after invalid-syntax negative control raised SyntaxError. Syntax and byte identity do not prove runtime correctness. No suites run, therefore no runtime pass or security-clean claim. Long behavioral commands below must use `trestle run --`, after tracked-ignore preflight and environment provisioning.

## Variant selection

Use source-integration as the baseline for DataFlow recovery, subject to ordinary correctness/security review. Most DataFlow source bytes shared with storage/promotion; runtime has an older subset. Exceptions requiring deliberate composition:

1. **Storage-only temporary schema adapter ownership:** `core/schema_inspection.py` (87 lines) and regression `test_schema_inspection_cleanup_ownership.py` exist only in storage-ci. Its engine delta over source introduces `_release_schema_inspection_owner`, wraps PostgreSQL/MySQL/SQLite inspectors in `SchemaInspectionOwner`, preserves primary BaseException, parks failed owners in `_displaced_async_sql_nodes`, and calls `cleanup_sync` where available. Take storage engine variant plus schema owner/test and storage-only paragraph in specs/dataflow-models.md. Exact source→storage diff is only this owner lifecycle change; do not replace other files wholesale from storage.
2. **Source-only stronger trust policy behavior:** source/promotion query_wrapper bytes match; storage lacks the `_get_agent_constraints` shape validation and `if self._enforcement_mode == "enforcing": raise PermissionError("Constraint policy unavailable")`. Preserve source query_wrapper and source `test_trust_column_metadata.py` (contains unavailable/malformed policy cases). Storage's corresponding test is shorter. This is an open review requirement; static source is not proof all entry points are closed.
3. **Source-only resilience additions:** source resilience/test include post-call `if deadline is not None and monotonic() >= deadline: raise TimeoutError(...)`, plus safe_log_field for numeric configuration subclasses and three extra deadline/diagnostic regression cases. Storage/promotion match each other but lack those deltas. Preserve source resilience, source test_circuit_breaker_half_open_deadline and source specs/dataflow-core paragraph.
4. **Source+storage workflow utility repair:** protected_engine, workflow_binding, simple_test_utils and test_public_workflow_test_utilities absent from promotion/runtime. Preserve source versions. Protected workflow construction delegates to owned binder; utilities use LocalRuntime context manager and supported dialect quoting, and serial record creation stops connecting independent rows.
5. **Source-only memory schema expectations:** tests/unit/core/test_sqlite_basic.py and tests/unit/test_engine_migration_errors.py verify actual anchored in-memory discovery/read instead of expecting NotImplementedError. Preserve these alongside schema repair.
6. **Promotion has a unique weaker unit fixture:** test_base_adapter_hierarchy uses a real localhost connection and accepts either health outcome; source/runtime use AsyncMock connect with asserted awaited call and healthy result. Source version is the deterministic unit fixture; no production behavior is uniquely added by promotion's variant.
7. **Source includes runtime test corrections:** test_migration_bug_006_unit and test_migration_performance_tracker match runtime but are absent from storage/promotion. Source nodes.py adds nullable/JSON/ensure_table changes on top of runtime changes; source type_processor matches all four.
8. **Spec composition:** preserve source dataflow-cache paragraph on production SQLite retained connection (storage lacks it), and merge storage's schema-owner paragraph into source dataflow-models. dataflow-express is identical across source/storage/promotion. Refresh line citations after final composition.

## Bounded repair and validation shards

Each implementation owner must retain source manifests/hashes and use isolation. Shared engine.py composition must have one owner; cache, schema and nullability hunks cannot be copied independently into the same live file.

### S1. Physical schema and owner cleanup

Ownership: core/schema_inspection.py; engine inspector/discovery/Express-wrapper/cleanup hunks; platform/inspector.py; core/schema_comparator.py; matching tests/specs. Baseline source + storage owner delta. Approximately 400 load-bearing added lines after removing old fallback code; 8 invariants: real physical schema, no implicit DDL from inspector, errors propagate, retained memory address, physical custom names, primary error preserved, retries retain owner, close does not block owning loop. Split inspector/default comparison into a separate subshard if implementation expands beyond 500 logic LOC.

Tests (from project-provisioned interpreter): `trestle run -- python -m pytest packages/kailash-dataflow/tests/regression/test_inspector_physical_truth.py packages/kailash-dataflow/tests/regression/test_schema_inspection_cleanup_ownership.py packages/kailash-dataflow/tests/regression/test_displaced_sql_cleanup_retry.py packages/kailash-dataflow/tests/regression/test_sqlite_address_consumer_parity.py packages/kailash-dataflow/tests/regression/test_sqlite_schema_url_classification.py packages/kailash-dataflow/tests/unit/core/test_sqlite_basic.py packages/kailash-dataflow/tests/unit/test_engine_migration_errors.py packages/kailash-dataflow/tests/unit/test_inspector_model_introspection.py -q`.

Real backend catalog parity: `trestle run -- python -m pytest packages/kailash-dataflow/tests/integration/test_inspector_catalog_backends.py -q`. Depends on Core shared async_close/driver termination recovered by runtime owner. AST/grep sweep all `_inspect_*_schema_real`, `discover_schema*`, `_displaced_async_sql_nodes`, `model_instances_count`, Count `ensure_table` callers.

### S2. Resilience deadline/configuration snapshots

Ownership: platform/resilience.py; test_circuit_breaker_half_open_deadline.py; test_retry_config_snapshot.py; corresponding spec paragraph. Choose source. ~200 changed logic LOC, 7 invariants: config validation, immutable execution snapshot, one half-open deadline, stale generation isolation, cancellation identity, bounded backoff, safe diagnostics.

`trestle run -- python -m pytest packages/kailash-dataflow/tests/regression/test_circuit_breaker_half_open_deadline.py packages/kailash-dataflow/tests/regression/test_retry_config_snapshot.py -q`. Mechanical sweep every state transition and numeric diagnostic; adversarial review must include callback swallowing timeout and late old-generation results.

### S3. Trust constraints and metadata

Ownership: trust/query_wrapper.py, test_trust_column_metadata.py, tests/unit/trust/test_query_executor.py. Choose source. ~60 logic LOC, 5 invariants: enforcing denial on missing metadata, authoritative model columns, malformed configured policy denied, disabled/permissive compatibility, diagnostic privacy.

`trestle run -- python -m pytest packages/kailash-dataflow/tests/regression/test_trust_column_metadata.py packages/kailash-dataflow/tests/unit/trust/test_query_executor.py -q`. Sweep `_get_agent_constraints`, `_verify_table_access` and every read/table-access entry point; correctness AND adversarial security reviewers required. Coordinate specialist consultation for trust domain with root.

### S4. Redis connection and close ownership (existing dirty work)

Ownership: cache/auto_detection.py, redis_manager.py, async_redis_adapter.py connection/close/clear hunks; engine key_prefix forwarding single hunk via engine owner. Choose source/shared storage/promotion. ~240 logic LOC, 7 invariants: authenticated URL config parity, TLS verification, shared credential decoding, custom prefix literal clear, close drain order, shared manager ownership, safe diagnostics.

`trestle run -- python -m pytest packages/kailash-dataflow/tests/unit/cache/test_auto_detection.py packages/kailash-dataflow/tests/unit/cache/test_auto_detection_diagnostics.py packages/kailash-dataflow/tests/unit/cache/test_redis_diagnostic_privacy.py packages/kailash-dataflow/tests/unit/cache/test_redis_owned_close.py packages/kailash-dataflow/tests/unit/cache/test_redis_url_config.py -q`.

Real Redis: integration/test_cache_prefix_forwarding.py, test_redis_concurrent_close.py, test_redis_namespace_clear.py, test_redis_url_authentication.py through trestle. Coordinate sequential ownership of async_redis_adapter with S5.

### S5. Approved unambiguous cache identity — NOT IMPLEMENTED in any tree

Absolute-state sweep found key_generator.py still `EXPRESS_KEYSPACE_VERSION = "v3"` and `return ":".join(parts)`; Redis invalidator uses `f"dataflow:v*:{tenant_id}:{model_name}:*"`; memory invalidator uses substring `segment in k`. Source decision note still OPEN, though orchestrator states user subsequently approved new format. No changed key_generator.py or memory_cache.py exists among four trees. Do not mark approved design as delivered.

Proposed ownership: one shared fixed-position typed encoding/matching primitive, key_generator.py, memory_cache.py, async_redis_adapter.py invalidation, list_node_integration.py, Express caller plumbing, vectors/specs. Target <=450 load-bearing LOC, 9 invariants: injective identity, null-vs-empty distinction, namespace isolation, database isolation, tenant isolation, model isolation, same Redis/memory matching, no ambiguous legacy reads, explicit legacy expiry policy. If transaction publication/invalidation work is included, split that into S6 below.

Required cases: (`tenant=A, model=B:C`) differs from (`tenant=A:B, model=C`); `acme` invalidation retains `other:acme`; literal `acme*` retains `acme-other`; custom prefix with glob characters; None vs empty tenant; real Redis and in-memory parity; database identity scoped invalidation; query and Express paths; old entries cold-miss and expire. Existing note's reported probes are not re-run evidence here. Mechanical sweep producers `generate_key`, `generate_express_key`, `generate_key_from_builder` plus all invalidate_model callers, explicit clear_cache, and list-node writes. Update canonical vectors and keyspace tripwire to approved local contract without asserting unverified cross-repo parity. Two actual clean correctness/security rounds.

### S6. Generated-write cache publication/invalidation lifecycle

Decision note explicitly leaves generated-node write / Express cache interaction distinct from key identity. Sweep successful generated create/update/delete/upsert/bulk completions, transaction commit/rollback, and inflight read publication before asserting closure. Existing regression `tests/regression/test_issue_750_express_list_cache_invalidation.py` differs across trees and is root-owned scope; coordinate with runtime owner. No blanket copy or presumption that S5 fixes lifecycle behavior. Size only after call-graph inventory; <=8 invariants/500 logic LOC.

### S7. Type/nullability/JSON and public utility recovery

Split independent bounded tasks: (a) core/type_introspection.py/type_processor.py/nodes.py validation + engine nullability hunks and generated-model/nullability/JSON regressions (6 invariants, ~150 logic LOC), (b) protected_engine/workflow_binding/testing utilities plus public utility regression (~60 logic LOC, 4 invariants). Preserve source. S1 CountNode hunks in nodes.py must be composed by one owner.

### S8. MongoDB / MySQL adapters and CI fixture corrections

MongoDB/base_adapter dirty source adds failed-connect cleanup, synchronous resource close, health failure contract and diagnostic sanitation; tests are shared across source/storage/promotion. ~150 logic LOC, 5 invariants. MySQL source/promotion adds transaction rollback/close handling and safe diagnostics; storage/runtime lack it (~70 logic LOC, 4 invariants). Run named dirty unit/integration files with trestle, preserving real infrastructure in Tier 2. Source DataFlow pyproject pytest/dependency changes and fixture corrections must stay with corresponding CI change owner. No globally waived scanner findings.

## Landing/reaping gate

All dirty work is uncommitted versus dev, even when old branch tips are merged. SHA equality identifies duplicates, not landed behavior. Preserve every source-only/storage-only file above until its recovered committed blob is accounted for, tests/review evidence exists and the source inventory has no unexplained residuals. Do not reap on branch ancestry alone. Root owns integration ledger and burndown.
