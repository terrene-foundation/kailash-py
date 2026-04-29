# Cross-SDK Audit: kailash-rs vs kailash-py 1.5.1 Bugs (#699/#700/#701)

Audit target: `/Users/esperie/repos/loom/kailash-rs/crates/kailash-ml/`
Date: 2026-04-28
Scope: Read-only verification whether the three Python 1.5.1 bugs reproduce in the Rust SDK.

---

## Issue #699 — Schema fork on shared store

**VERDICT: ABSENT (structurally unreachable)**

**Evidence:**

1. Both engines exist:
   - `crates/kailash-ml/src/engine/registry.rs:147` — `pub struct ModelRegistry { backend: Box<dyn RegistryBackend> }`
   - `crates/kailash-ml/src/engine/tracker.rs:230` — `pub struct ExperimentTracker { backend: Box<dyn TrackerBackend> }`

2. Neither engine uses SQL/SQLite. `grep -rn 'sqlite\|rusqlite\|sqlx\|CREATE TABLE\|_kml_\|model_versions' crates/kailash-ml/` returns zero hits.

3. Backends are pluggable, in-process, and isolated by trait:
   - Registry: `InMemoryRegistry` (BTreeMap) and `FileSystemRegistry` (one directory tree per registry).
   - Tracker: `InMemoryTrackerBackend` (BTreeMap) and `LocalTrackerBackend` (one JSON file per run, `run_path = root.join("{run_id}.json")` — `tracker.rs:1001-1003`).

4. The two trait objects share no namespace. There is no SQL DDL surface, no shared keyspace, no possibility of CREATE-TABLE collision. Even if a user pointed both at the same filesystem directory, registry artifacts and tracker run JSON would coexist as distinct files.

**Recommendation:** No action. The Rust architecture (trait-object backends, no shared SQL store) makes #699 structurally unreachable. The lesson worth porting back to kailash-py is the trait-object boundary, not a fix.

---

## Issue #700 — InferenceServer hard break / multi-model loss

**VERDICT: ABSENT**

**Evidence:**

1. `inference.rs:223` — `pub struct InferenceServer { models: DashMap<String, LoadedModel>, config: InferenceConfig, cache: Option<InferenceCache>, metrics: InferenceMetrics }`. Multi-model by design — a `DashMap` keyed by name.

2. Constructor + load surface (`inference.rs:234, 261, 316`):

   ```rust
   pub fn new(config: InferenceConfig) -> Self
   pub fn load_model(&self, name: &str, pipeline: Box<dyn DynPredict>, version: Option<u64>) -> MlResult<()>
   pub fn load_from_registry(&self, name: &str, registry: &ModelRegistry, version: Option<u32>, deserialize_fn: ...) -> MlResult<()>
   ```

   The Python 1.5.x replacement `from_registry(name, registry=)` is structurally what the Rust API does, but the Rust API ALSO retains the multi-model `load_model(name, ...)` path that 1.5.x deleted on the Python side.

3. `InferenceConfig` (`inference.rs:47`) carries `max_models: usize` (default 10), `cache_ttl_secs`, `batch_size`. Caching is built-in (`cache: Option<InferenceCache>`) and per-model (`invalidate_model(name)`, `inference.rs:149`). Equivalent of `cache_size` + `warm_cache` is implicit in the cache + `max_models` cap.

4. Public surface stable: `git log --all --oneline crates/kailash-ml/src/engine/inference.rs` shows three commits since #242 introduction (`98fba26d`, `af1e723d` rustfmt, `b1351e40` merge). No breaking signature change.

**Recommendation:** No action. The Rust `InferenceServer` is the multi-model architecture the Python 1.1.x users want. Worth flagging in the cross-SDK parity spec that the Python deletion in 1.5.x diverged from the Rust contract — that divergence is the bug, not a Rust gap.

---

## Issue #701 — `diagnose()` silent-drop kwargs

**VERDICT: ABSENT (entry-point does not exist)**

**Evidence:**

1. No `diagnose()` dispatcher anywhere in the ML or diagnostics crates:
   - `grep -rn 'fn diagnose' crates/` returns hits ONLY in unrelated surfaces: `kaizen-agents/src/diagnoser.rs:137` (agent task method), `dataflow/src/debug_agent.rs:270` (DataFlow error diagnoser), `trust-plane/src/cli/commands/diagnose.rs:52` (test).
   - Nothing in `crates/kailash-ml/src/`, `crates/kailash-dl-diagnostics/src/`, or `crates/kailash-rag-diagnostics/src/`.

2. `kailash-dl-diagnostics/src/lib.rs:51` exports a typed struct, not a string-dispatched function:

   ```rust
   pub use diagnostics::{DlDiagnostics, DEFAULT_DEAD_NEURON_THRESHOLD, DEFAULT_WINDOW};
   pub use types::{BatchRecord, DlReport, EpochRecord, Finding, Severity};
   ```

   Usage (`lib.rs:32-41`): `DlDiagnostics::new("trainer-1", None)?; diag.record_batch(...); diag.record_epoch(...); diag.report();` — no `kind=`, no `data=`.

3. The Rust SDK is structurally immune to the silent-drop class: each diagnostic kind has its own typed constructor (`DlDiagnostics::new`, peer crate `RagDiagnostics`). There is no string-dispatch enum, so a misspelled `kind="classifier"` or an unrecognized kwarg cannot compile. Sum-type dispatch (if added later) would require explicit `match` arms — silent drops would surface as `unused_variables` warnings.

**Recommendation:** No action on the bug. RECOMMEND filing a forward-looking guardrail issue at `esperie/kailash-rs` only IF a top-level `diagnose(kind, ...)` dispatcher is ever added — at which point the spec MUST require an enum-typed `DiagnosticKind` rather than a stringly-typed kwarg.

---

## SUMMARY

**Zero of three** issues to file at `esperie/kailash-rs`. All three Python 1.5.1 bugs are absent from the Rust SDK by virtue of three structural choices:

1. **Trait-object backends per engine** (Issue #699) — registry and tracker share no namespace; no shared SQL store exists; CREATE-TABLE schema fork is unreachable.
2. **Stable multi-model API on `InferenceServer`** (Issue #700) — `DashMap`-backed `load_model(name, ...)` was never removed; the Python deletion is the divergence, not a Rust gap.
3. **Typed per-kind diagnostic constructors** (Issue #701) — no string-dispatched `diagnose()` exists; sum-type discipline forecloses the silent-drop class.

**Cross-cutting patterns the Rust SDK should defend against (preventive, not reactive):**

- **Dual-CREATE-TABLE on shared store**: the next time a SQL backend is added to either tracker or registry, the spec MUST mandate a single owning module for the schema (one CREATE TABLE per logical table, even across engines) and a Tier-2 test that initializes both engines against the same SQLite URL.
- **Deprecation cycle discipline**: any `pub fn` removal on a public engine surface MUST land with a `#[deprecated(since = "X.Y.Z", note = "...")]` shim for at least one minor cycle, enforced by the cross-SDK parity audit at `/release`.
- **Silent-drop kwargs**: if a top-level `diagnose()` dispatcher is ever introduced, the `kind` parameter MUST be `enum DiagnosticKind`, never `&str`, and unrecognized kwargs MUST be a compile error (use struct-typed config, not free-form maps).

These are spec/rule additions, not code fixes — the Rust SDK is currently clean on all three issues.
