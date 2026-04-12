# Arbor Upstream Issues — Disposition

Source: Arbor HR Advisory Platform report, 2026-04-09, by Jared Teo.

| #   | Issue                                                                                                                                                                | Priority | Status (as of 2026-04-11)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| --- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Kaizen `get_openai_config` / `get_ollama_config` / `get_anthropic_config` no `api_key` override parameter (blocks multi-tenant BYOK)                                 | P0       | **Already resolved** in `kailash-py#12` (closed 2026-03-19). All provider config functions now accept optional `api_key` and `base_url`. `BaseAgentConfig` has both fields. 503-line regression test suite covers per-request override, SSRF protection, credential storage redaction.                                                                                                                                                                                                                                                                                       |
| 2   | DataFlow `express_sync.list()` caches by default with no auto-invalidation after writes (147 `enable_cache=False` workarounds in Arbor)                              | P1       | **Already resolved**. All `express` write operations (`create`, `update`, `delete`, bulk variants) now call `_invalidate_model_cache(model)` immediately after the write (tagged TSG-104). Public `clear_cache(model=None)` API for manual invalidation. Model-scoped, tenant-aware.                                                                                                                                                                                                                                                                                         |
| 3   | Nexus no `metadata` parameter on `register()` for attaching version / author / tags / description to registered workflows                                            | P2       | **FIXED this session.** See `../.session-notes` → "Fix 1 — Nexus workflow metadata". Filed cross-SDK issue `esperie-enterprise/kailash-rs#323` for Rust Nexus parity.                                                                                                                                                                                                                                                                                                                                                                                                        |
| 4   | SDK transitive dependencies not fully declared (Docker builds fail until `psutil`, `requests`, `pandas`, `numpy`, `jinja2`, `aiohttp`, `websockets` manually pinned) | P2       | **FIXED this session.** The specific deps Arbor reported were mostly already declared in core `pyproject.toml`. Remaining gaps discovered in audit: `kailash-kaizen` imported `requests` without declaring it (3 files); `kailash-dataflow` over-declared `numpy` and `aiohttp` (not imported in src/); `kailash` core over-declared `websockets` in main deps (not imported, lives in dev extras now). `jinja2` is nowhere imported — false positive in the Arbor report. `uv pip check` clean after fix.                                                                   |
| 5   | `DATABASE_URL` validation rejects passwords with `@`, `#`, `%`, `:` — must be URL-encoded manually, not documented                                                   | P3       | **FIXED this session** (expanded scope). The narrow fix was making `DatabaseConfigBuilder.{postgresql,mysql}` URL-encode credentials. Red team surfaced the same root cause (raw `parsed.password` / missing `quote_plus` / missing `unquote`) at 9 downstream sites plus a divergent hand-rolled regex MySQL parser in `trust/esa/database.py`. All sites consolidated on `urlparse + quote_plus/unquote`, null-byte defense added for MySQL, masking helpers consolidated on a single 6-key sensitive-query set, `mask_url()` extended to handle MongoDB replica-set URLs. |
| 6   | DataFlow `auto_migrate` event loop conflict in async environments                                                                                                    | —        | **Already resolved** in `kailash-dataflow v0.10.15` — `SyncDDLExecutor` bypasses the event loop. Listed for completeness.                                                                                                                                                                                                                                                                                                                                                                                                                                                    |

## Out-of-scope cleanups done this session

- **47 JWT test failures** in `nexus.auth` (deprecated per SPEC-06). Root
  cause: test helpers used `__new__` to bypass `JWTMiddleware.__init__`
  but never assigned `mw._validator` — SPEC-06 extracted the crypto path
  to `JWTValidator`. Fixed by adding four thin-delegate methods to the
  middleware (backward-compat for the deprecation window) and updating
  all 8 `_make_middleware` test helpers + 1 inline case. Result:
  475/475 auth unit tests pass (was 428/475).

- **MongoDB motor import** made lazy. `packages/kailash-dataflow/src/
dataflow/adapters/mongodb.py` imported `motor.motor_asyncio` at
  module top-level, breaking `from dataflow import DataFlow` for
  projects that don't use MongoDB. Moved import inside
  `MongoDBAdapter.connect()` with a descriptive `ImportError`.

- **LocalRuntime deprecation warning in `ModelRegistry`**. The registry
  owns a long-lived LocalRuntime and releases it via
  `close()` → `runtime.release()`, but the runtime emitted a
  DeprecationWarning on first execute() because neither
  `_is_context_managed` nor `_cleanup_registered` was set. Fixed by
  setting `self.runtime._cleanup_registered = True` in the registry's
  `__init__` for the own-runtime sync path. (Earlier attempts using
  `__enter__()` / `__exit__()` caused a new `coroutine 'wait_for' was
never awaited` RuntimeWarning — reverted in favor of flag assignment.)

## Cross-SDK disposition

Per `rules/cross-sdk-inspection.md`, each issue was checked against
`esperie-enterprise/kailash-rs`:

- **Issue 3 (Nexus metadata)**: Rust `WorkflowRegistry` has
  `register()` + `register_with_description()` but `RegisteredWorkflow`
  only carries a plain `description: Option<String>`, no structured
  metadata. Filed `esperie-enterprise/kailash-rs#323` with the Python
  PR as cross-reference.
- **Issue 4 (deps)**: Rust Cargo workspace is cleanly managed — all
  dependencies declared at workspace root + per-crate, no gaps. No
  action needed.
- **Issue 5 (DATABASE_URL)**: Rust SDK delegates URL parsing to
  `sqlx::AnyPool::connect()` which uses the `url` crate to properly
  handle percent-encoding. Password masking uses a scheme-aware helper
  at `kailash-dataflow/src/connection.rs:878-900`. No action needed.
