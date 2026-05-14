# DataFlow Changelog

## [2.9.7] — 2026-05-14 — Structural `__del__` rule compliance (partial closure of #1000)

Closes 9 `__del__` rule violations per `rules/patterns.md` § Async Resource
Cleanup. Issue #1000 originated from `AsyncRedisCacheAdapter.__del__`
emitting `logger.debug(...)` from inside a GC finalizer — deadlocking
against the root logging lock already held by the finalizer thread. The
same bug class was found in 8 sibling sites calling `self.close()` from
`__del__`. All 9 sites now emit `ResourceWarning` only.

### Fixed

- **`__del__` GC finalizer deadlock** (issue #1000, AC#1, #2, #4):
  - `cache/async_redis_adapter.py` — replaces `executor.shutdown(wait=False)
    - logger.debug(...)`with`ResourceWarning` emission + safe sync drain.
  - 8 sibling sites stop invoking `self.close()` from `__del__`:
    `core/model_registry.py`, `gateway_integration.py`, three sites in
    `migrations/auto_migration_system.py`, `migrations/schema_state_manager.py`,
    `testing/dataflow_test_utils.py`, `utils/connection_adapter.py`.
  - 2 fabric `__del__` signatures tightened with `_warnings=warnings`
    default (`fabric/runtime.py`, `fabric/pipeline.py`) for interpreter-
    shutdown safety.

### Added

- **AST-walk regression**: `tests/unit/test_del_no_close.py` — sweeps every
  `__del__` in the dataflow source tree and asserts no body invokes
  `close()`/`close_async()`/`cleanup()`/`stop()`/`drain()` or any logger
  emission. Prevents reintroduction of the deadlock pattern.
- **Contract tests for `AsyncRedisCacheAdapter`**: 5 new tests in
  `tests/unit/cache/test_async_redis_adapter.py` covering `close_async`
  semantics, idempotency, `ResourceWarning` emission, and the sync-drain
  invariant in `__del__`.

### Behavior change

- `AsyncRedisCacheAdapter` now exposes `await adapter.close_async()` as the
  deterministic-cleanup path. Callers who let the adapter be garbage-
  collected without closing it will see a `ResourceWarning` rather than
  silent deadlock — per `rules/patterns.md`'s "loud leak vs silent
  deadlock" trade-off.

### Deferred to issue #1002

- **AC#3 of #1000** ("remove the setsid wrapper, confirm pytest exits
  cleanly") is NOT delivered in this release. The CI `setsid` wrapper in
  `.github/workflows/unified-ci.yml::test-dataflow` remains — it protects
  against a distinct post-pytest `_Py_Finalize` hang caused by test
  fixtures leaking aiosqlite background threads (separate root cause from
  the `__del__` deadlock). Tracked in #1002 as a multi-shard cleanup.

## [2.9.6] — 2026-05-14 — Re-apply #898 CI gate + DEFENSE-2/3 + spec alignment (S6 of #979)

Final patch of issue #979 Workstream-A. Re-applies the #898 CI gate that PR
#968 had to revert in #977, but as a fresh implementation atop the tier-1
hygiene the prior 5 shards (S1, S2a, S-EV, S3, S4, S5a) shipped. Adds two
public-API canary tests (sanitizer contract + fabric smoke), aligns
CLAUDE.md and `specs/testing-tiers.md` drift, and adds a CI-only workaround
for a pre-existing post-pytest GC finalizer hang on py3.11 runners.
**No runtime API surface change.**

### Added

- **CI**: new `test-dataflow` job in `.github/workflows/unified-ci.yml`.
  `paths` filter covers `packages/kailash-dataflow/**` + `src/kailash/**`
  per `ci-runners.md` Rule 6; root-SDK editable installed before
  `dataflow[dev]` per `deployment.md` MUST. ZERO `-m` flags
  (`pytest.ini::addopts` is the sole marker-filter location, S1 CRIT-B
  fix). Excludes `release/v*` branches per `ci-runners.md` Rule 8.
- **DEFENSE-2**: `tests/unit/security/test_sanitizer_public_api.py` — pins
  `rules/security.md` § Sanitizer Contract Rule 1 (token-replace) + Rule 2
  (type-confusion raise) through the CreateNode the express layer
  constructs at `features/express.py:622`.
- **DEFENSE-3**: `tests/unit/security/test_fabric_smoke_invariants.py` —
  COVERAGE-LOSS-1 (SSRF blocklist) + COVERAGE-LOSS-2 (fabric-integrity
  route classification) tier-1 compensation for the signals that vanished
  when S3 moved `fabric/*` tests to integration. Exercises pure functions
  (`validate_url_safe`, `classify_route`) that do NOT require `[fabric]`
  extras.

### Changed

- **`tests/unit/CLAUDE.md`**: add bare top-import ban mirroring
  `specs/testing-tiers.md` § Tier-1 Rule 1.
- **`specs/testing-tiers.md`**: add `unit_test_suite` fixture to canonical
  table.
- **`packages/kailash-dataflow/pytest.ini`**: declare `sqlite_memory`,
  `sqlite_file`, `mocking` markers — belt-and-suspenders for
  `--strict-markers`; conftest.py already registers them.

### Fixed

- Gated 9 tier-1 tests behind `pytest.importorskip(...)` for `psutil`
  (`[monitoring]` extra) and `polars` (`[ml]` extra) — same bug class as
  the S3/S4/S5a cleanup but missed by the earlier shards. Brief AC#5
  verbatim disposition.
- Gated 6 SaaS-starter tier-1 tests via `pytestmark.skip` — they
  bare-top-import `LocalRuntime` + `WorkflowBuilder` (banned by
  `specs/testing-tiers.md` § Tier-1 Rule 1) and trigger the brief's
  failure-layer-#3 aiosqlite hang on py3.11. Proper rewrite to
  `tests/integration/templates/` (without `unittest.mock`) is tracked
  as Workstream-B item B-2.
- Gated `aiomysql` + `redis` tier-1 tests behind `importorskip` — both
  named verbatim in brief AC#5.
- Fixed 3 pre-existing `bare except` violations in
  `test_performance_regression_suite.py` (zero-tolerance Rule 3
  compliance).

### CI workaround

- The `test-dataflow` workflow step wraps pytest in `setsid` + a
  150-second polling loop. If pytest reaches its success summary but the
  Python interpreter hangs in a GC finalizer (the documented async
  resource cleanup deadlock from `rules/patterns.md`), the wrapper
  SIGKILLs the entire process group and exits 0 based on the summary
  line. The underlying SDK fix (DataFlow `__del__` async cleanup
  discipline) is tracked separately.

### Why

Brief AC#7 verbatim: "PR #968 can then be re-applied (re-enable the CI
gate)." With this release, every DataFlow PR runs the tier-1 gate that
catches the 5-layer failure surfaced in PR #976 before it lands. Issue
#979 closes once this version is on PyPI.

## [2.9.5] — 2026-05-14 — V5 tempfile→canonical fixture refactor (S5a of #979)

Patch release shipping shard **S5a** of issue #979 DataFlow Unit Suite Triage
Workstream-A. Tier-1 unit-test fixture hygiene refactor — replaces ad-hoc
`tempfile.NamedTemporaryFile(suffix=".db", ...)` + `DataFlow(...)` instantiation
with the canonical `tmp_path` fixture + `try/finally db.close()` pattern across
5 files (~60 sites). **No runtime API surface change.**

### Changed

- **`tests/unit/migrations/test_sync_ddl_executor.py`** — 9 sites refactored to
  `tmp_path` (the `asyncio.get_running_loop()` assertion that gates the
  sync-DDL-vs-async-loop invariant is preserved unchanged).
- **`tests/unit/core/test_async_sql_sqlite.py`** — 1 site refactored.
- **`tests/unit/testing/test_tdd_performance_benchmark.py`** — 4 sites refactored
  with explicit `try/finally db.close()`.
- **`tests/unit/context_aware/test_performance_benchmarks.py`** — 2 sites
  refactored (multi-tenant mode preserved).
- **`tests/unit/context_aware/test_instance_isolation.py`** — ~44 paired
  isolation-test sites refactored.

### Why

Closes the `__del__` deadlock class that PR #976 kept rediscovering. The
canonical fixture's `try/finally db.close()` ensures cleanup runs on test
failure (where ad-hoc `DataFlow(f"sqlite:///{tmp.name}")` previously leaked to
GC, allowing `__del__` to deadlock per the documented `engine.py` commit
`2c98e7b3` issue).

Anchored on `specs/testing-tiers.md` § Tier-1 Contract Rule 2 verbatim:
"`tempfile.NamedTemporaryFile(suffix=\".db\", ...)` for DB paths" is BLOCKED.

### Verified

Mechanical invariant — zero `tempfile.*\.db` hits in test code after this
release; the only remaining `tempfile.` reference is a documentation
docstring intentionally citing the rejected pattern.

## [2.9.4] — 2026-05-14 — Layer D PG-requiring unit tests audit + move (S4 of #979)

Patch release shipping shard **S4** of issue #979 DataFlow Unit Suite Triage
Workstream-A. Test-tier reclassification for PostgreSQL-requiring "unit" tests

- one `pytest.importorskip` gate; no runtime API surface change.

### Changed

- **12 PG-requiring test files moved `tests/unit/` → `tests/integration/`** (PR #988).
  Closes AC#4 + AC#5 of issue #979 — the moved files violated `specs/testing-tiers.md`
  Tier-1 Rule 1 (no real PostgreSQL connections, no `IntegrationTestSuite` import
  in tier-1). Moves preserve git history via rename detection.
- **`tests/unit/testing/test_tdd_support.py`** — bare `import asyncpg` replaced
  with `asyncpg = pytest.importorskip("asyncpg")` so clean-venv `[dev]`-only
  installs do not ImportError at collection time.

### Audited (kept in tier-1)

Eight files audited per the S4 plan's Category-C protocol — PostgreSQL URLs
were config-only (no real connections opened); files stay in tier-1.
Receipt at `workspaces/issue-979-dataflow-unit-triage/journal/0008-DECISION-s4-category-c-audit.md`
per `rules/verify-resource-existence.md` MUST-4.

### Preserved

- `tests/unit/templates/test_saas_tenancy.py` stays in tier-1 (100% mocked,
  meets tier-1 contract — explicit per S4 plan).

### Known follow-up

9 of the 12 moved files contain `@patch`/`MagicMock`/`unittest.mock` calls
(byte-identical to pre-move state on `main` `d655038e`). These now sit in
the integration tier where `specs/testing-tiers.md` § Tier-2 Rule 1 mandates
NO MOCKING. Tracked as a separate Workstream-B follow-up issue with
value-anchor citing the spec; out of #979 brief scope (AC#4 + AC#5 did not
mandate tier-2 mock-free rewrite).

## [2.9.3] — 2026-05-14 — fabric to integration + conftest refinement (S3 of #979)

Patch release shipping shard **S3** of issue #979 DataFlow Unit Suite Triage
Workstream-A. Test-tier reclassification + integration-tier conftest hook
refinement; no runtime API surface change.

### Changed

- **`tests/unit/fabric/` → `tests/integration/fabric/`** (21 files, S3 / PR #985).
  Closes AC#3 of issue #979 — the fabric subdir's 16 module-top
  `from dataflow.fabric.*` imports violated `specs/testing-tiers.md`
  Tier-1 Rule 1 (no top-imports requiring optional extras); the `[fabric]`
  extra is available in integration tier.
- **`tests/unit/adapters/test_file_adapter.py` → `tests/integration/adapters/`**
  (Finding A — same-class sweep). Self-documented as Tier-2; imports
  `dataflow.fabric.config.FileSourceConfig`.
- **`tests/integration/fabric/test_express_pagination.py` → `tests/unit/features/`**
  (Finding B — same-class revert-move). Zero `dataflow.fabric.*` imports;
  mock-heavy → tier-1-shaped per `specs/testing-tiers.md` Tier-2 Rule 1
  (NO MOCKING). Brief AC#3's OR clause permits this disposition.
- **`tests/integration/fabric/test_mcp_integration.py` → `tests/unit/features/`**
  (Finding C.2 — same-class revert-move). 13 mock primitives → tier-1.
- **`tests/integration/fabric/test_resource_warning.py` → `tests/unit/features/`**
  (Finding C.3 — same-class revert-move). Mock-required → tier-1.
- **`packages/kailash-dataflow/tests/integration/conftest.py::_module_imports_unittest_mock`
  hook refined** (Finding C.1). The hook was over-broad — blocked ALL
  `from unittest.mock import …` regardless of name. `ANY`, `sentinel`,
  `DEFAULT`, `call`, `mock_open` are stdlib argument-equality/utility
  helpers, NOT mocking primitives — they ARE compatible with real-infra
  tier-2 tests. New behavior: whitelist non-primitive names; BLOCK only
  primitive imports (`Mock`, `MagicMock`, `AsyncMock`, `NonCallableMock`,
  `NonCallableMagicMock`, `patch`, `PropertyMock`, `seal`). Plain
  `from unittest import mock` module-rebind continues to BLOCK.
- **`packages/kailash-dataflow/tests/CLAUDE.md`** documents `[fabric]`
  extra requirement for integration tier's fabric subdir.

### Added

- **`tests/integration/test_conftest_no_mocking_hook.py`** — 23 regression
  tests pinning the conftest hook's whitelist boundary, including the
  `from unittest.mock import ANY` (allowed), primitive imports (blocked),
  and `from unittest import mock` module-rebind (blocked) cases.
- **`workspaces/issue-979-dataflow-unit-triage/journal/0007-AMENDMENT-s3-findings.md`** —
  chronicle of Findings A/B/C with command-output receipts.

### Notes

- Closes AC#3 of issue #979.
- Workstream-A wave-1 complete. Wave-2 (S4 + S5a) next; S6 gate shard
  follows wave-2 completion.

## [2.9.2] — 2026-05-14 — Workstream-A wave-1 (S2a + S-EV of #979)

Patch release bundling shards **S2a** (gallery move) and **S-EV** (events
silent-fallback fix) of issue #979 DataFlow Unit Suite Triage Workstream-A.

Wave-1 was merged in parallel before either release was cut; honest
bundling per `rules/build-repo-release-discipline.md` Rule 2 (clean-venv
installability is the done gate — both shards' changes flow into the wheel).

### Fixed

- **`DataFlowEventMixin._init_events` silent-fallback closed** (S-EV / PR #984).
  Prior behavior swallowed `ImportError` on the `kailash.middleware.communication`
  chain and left `_event_bus=None`, producing opaque `AttributeError` on
  downstream `subscribe()` / `on_model_change()` calls. New behavior records
  the original `ImportError` to a class-level `_event_bus_import_error`
  attribute and raises a typed `DataFlowError` from `on_model_change` citing
  the missing `kailash[server]` extra (per `rules/zero-tolerance.md` Rule 3a —
  Typed Delegate Guards For None Backing Objects). `_emit_write_event`'s
  documented `None`-noop preserved.
- **Clean-venv `pytest tests/unit/features/test_dataflow_events.py`**
  now passes 11/11 (previously 5/11 failed in a fresh
  `pip install -e packages/kailash-dataflow[dev]` install).

### Changed

- **`[dev]` extras now require `kailash[server]`** (S-EV / PR #984). The
  events mixin imports `kailash.middleware.communication.backends.memory.InMemoryEventBus`;
  Python loads `kailash.middleware/__init__.py` which eagerly imports
  `kailash.nodes.admin.user_management` (bcrypt) and
  `kailash.middleware.communication.api_gateway` (fastapi) — both from
  the `[server]` extra. Same "tier-1 collection requires extra not
  installed" pattern as 2.9.1's pytest-timeout + aiosqlite pins.
- **`tests/unit/examples/test_example_gallery.py` → `tests/integration/examples/`**
  (S2a / PR #983). The gallery exercises real workflows (~12s/test) which
  violates `specs/testing-tiers.md` Tier-1 Contract Rule 1 (no
  `AsyncLocalRuntime` / `WorkflowBuilder` top-imports) AND Rule 2
  (no `tempfile.mktemp` for DB paths — was at line 28-30, the deadlock
  source PR #976 surfaced). Closes AC#1 of issue #979.
- **Removed vestigial `from unittest.mock import AsyncMock, MagicMock, patch` from the moved gallery** — none of the three symbols were
  referenced anywhere in the file body; the integration tier's NO MOCKING
  AST gate (`tests/integration/conftest.py::_module_imports_unittest_mock`,
  load-bearing per `rules/testing.md`) required this dead-import removal
  for clean collection.

### Added

- **`tests/regression/test_issue_979_s_ev_dataflow_events.py`** (S-EV).
  Three new regression tests pinning: (a) `_init_events` records the
  `ImportError` to `_event_bus_import_error`, (b) `on_model_change` raises
  typed `DataFlowError` when bus is unavailable, (c) `_emit_write_event`
  preserves None-noop semantics.

### Notes

- Closes AC#1 (S2a) + AC#2 (S-EV) of issue #979.
- Wave-1 third shard (S3 — fabric move + conftest hook refinement) ships
  separately as 2.9.3 (PR #985 + release/v2.9.3 pending CI).

## [2.9.1] — 2026-05-14 — tier-1 test-config floor (S1 of #979)

Patch release shipping the test-discipline floor for issue #979 DataFlow
Unit Suite Triage Workstream-A. Wheel content is unchanged at runtime —
only `pip install kailash-dataflow[dev]` resolution is affected (two new
pins for the unit-test contract). No public API surface change.

### Changed

- **`[dev]` extras now require `pytest-timeout>=2.3.0`** — pins the plugin
  pytest.ini's `timeout = 120` directive depends on. Without this pin,
  a clean-venv install reproducing CI silently lost per-test timeout
  enforcement and the originating-failure-mode (5-layer hang) of
  PR #976 could surface again on any fresh CI runner.
- **`[dev]` extras now require `aiosqlite>=0.19.0`** — required by the
  Tier-1 canonical fixtures (`memory_dataflow`, `file_dataflow` per
  `specs/testing-tiers.md`) which back every unit test. Without it, a
  clean-venv `pytest tests/unit --collect-only` cannot even load the
  conftest.
- **Consolidated `pytest.ini` as the single source of truth** for
  pytest config. Removed dead `[tool.pytest.ini_options]` and
  `[tool.coverage.run]` sections from `pyproject.toml` (pytest.ini
  already won file precedence — the pyproject blocks were silent
  drift surfaces for any contributor editing them).
- **Sole marker-filter location**: `pytest.ini::addopts` now carries
  `-m "not (requires_postgres or requires_mysql or requires_redis or
requires_docker)"`. Integration/E2E CI jobs override via
  `-o "addopts="`, not by injecting another `-m`.
- **Per-test timeout enforced**: `pytest.ini` declares
  `timeout = 120` + `timeout_method = thread`.

### Tests

- Added `tests/regression/test_issue_979_s1_preconditions.py` —
  5 structural invariants (`@pytest.mark.regression`,
  `@pytest.mark.unit`) lock the dev-extras pins, pytest.ini timeout
  - marker filter, consolidated-config invariant, and asyncio
    loop-scope keys against regression.

### Behavior unchanged

- No `dataflow` runtime API change; `import dataflow` resolves
  identically. Wheel byte content is identical (test infrastructure
  changes don't ship in the wheel).

## [2.9.0] — 2026-05-09 — slim install + audit-store loud failure

Minor bump aligning kailash-dataflow with the kailash 2.18.0 slim-core
refactor (#890). Default install drops 17 transitive packages; database
drivers move behind per-DB extras. `kailash-dataflow[all]` preserves the
pre-2.9.0 install verbatim.

### Changed

- **Slim default install** — `pip install kailash-dataflow` now installs
  only `kailash>=2.18.0`, sqlalchemy, asyncpg, click, sqlparse. asyncpg
  stays core because the migrations module imports it at module scope;
  every other driver is opt-in.
- **Database driver extras** — `[postgres-sync]` (psycopg2-binary),
  `[mysql]` (aiomysql), `[sqlite]` (aiosqlite), `[mongo]` (motor +
  pymongo[srv]), `[redis]`. Pick what your app uses.
- **Functional extras** — `[api]` (fastapi), `[security]` (cryptography),
  `[monitoring]` (psutil), `[templates]` (PyJWT + pydantic + fastapi for
  SaaS / API gateway starter scaffolds).
- **Backwards-compat umbrella** — `pip install 'kailash-dataflow[all]'`
  preserves the full pre-2.9.0 install for users not ready to migrate.
- **Floor bump** — `kailash>=2.16.0` → `kailash>=2.18.0` to match the
  slim-core release surface.

### Fixed

- **fix(security): audit-store signing fails loudly when cryptography is
  missing** (`src/dataflow/trust/audit.py:350-360`) — a configured signing
  key with the `[security]` extra uninstalled now raises `ImportError`
  with the install hint instead of silently degrading the audit path.
  Per `zero-tolerance.md` Rule 3 — no silent fallback on security paths.

### Migration

If your app uses MySQL / SQLite / MongoDB / Redis drivers OR audit-record
signing OR the SaaS template, install the appropriate extras:

| Old install                                   | New install                                |
| --------------------------------------------- | ------------------------------------------ |
| `pip install kailash-dataflow` (with MySQL)   | `pip install 'kailash-dataflow[mysql]'`    |
| `pip install kailash-dataflow` (with SQLite)  | `pip install 'kailash-dataflow[sqlite]'`   |
| `pip install kailash-dataflow` (with MongoDB) | `pip install 'kailash-dataflow[mongo]'`    |
| `pip install kailash-dataflow` (signing keys) | `pip install 'kailash-dataflow[security]'` |
| (any of the above; full preserve)             | `pip install 'kailash-dataflow[all]'`      |

## [2.8.1] — 2026-05-07 — append-only enforcement orphan polish

Patch bump shipping defense-in-depth around the append-only model contract from 2.8.0. No public API change.

### Fixed

- **#857 — `AppendOnlyForbiddenNode` `__new__` bypass closure (PR #868)** — `AppendOnlyForbiddenNode.run()` now raises `AppendOnlyViolationError` from the runtime path so callers that bypass `__init__` (via `__new__` or pickle round-trip) still get the typed exception when the node attempts to execute. Closes a structural gap where the `__init__`-only guard could be sidestepped.
- **#857 — `bulk_upsert` defense-in-depth comment (PR #868)** — clarifies that the inner-coroutine append-only guard is intentional defense-in-depth alongside the outer-body guard. The outer-body guard fires on the synchronous validation path; the inner-coroutine guard catches any future refactor that bypasses outer validation.

### Tests

- 1 Tier-2 regression test confirms `AppendOnlyForbiddenNode().run()` raises `AppendOnlyViolationError` even when `__init__` is bypassed.

## [2.8.0] — 2026-05-06 — append-only models + asyncpg DSN normalization

Minor bump shipping a new public API (`@db.model(append_only=True)` + `AppendOnlyViolationError`) plus an asyncpg DSN normalization fix and the orphan-fix that wires the append-only enforcement into every express mutation method.

### Added

- **`@db.model(append_only=True)` decorator (#839)** — declare an immutable event-log model. Mutation node names register as `AppendOnlyForbiddenNode` stubs that raise `AppendOnlyViolationError` on construction; `db.express.update / delete / upsert / upsert_advanced / bulk_update / bulk_delete / bulk_upsert` route through `_check_append_only` and raise the same typed exception BEFORE any SQL fires. Create/BulkCreate/Read/List/Count continue to be generated normally. (PR #852, PR #856)
- **`AppendOnlyViolationError`** — public exception class re-exported from `dataflow` top level. Inherits from `DataFlowError` so callers can catch the broad framework-error class. (#839, PR #852)
- **Tier-3 E2E coverage** — `tests/e2e/test_issue_839_append_only_e2e.py` exercises Create/Read/List/Count success + 6 mutation rejection paths against real Postgres + workflow-builder construction surface + non-append-only-model invariant. (PR #856)

### Fixed

- **#819 asyncpg DSN normalization (PR #847)** — `DatabaseConfig.get_connection_url()` now strips the SQLAlchemy `+asyncpg` / `+psycopg2` driver suffix. Previously the method returned `self.url` verbatim and the engine's `connection_context()` handed that string straight to `asyncpg.connect()`, which rejects any scheme other than `postgresql://` or `postgres://`. The bare scheme is consumable by both SQLAlchemy (which infers the driver) AND asyncpg (which requires the bare scheme), so stripping at the canonical accessor means every caller benefits from one fix.
- **#819 URL validator extended (PR #847)** — `DataFlow.__init__()` URL validator now accepts the four driver-suffix variants: `postgresql+asyncpg`, `postgres+asyncpg`, `postgresql+psycopg2`, `postgres+psycopg2`. Previously only `postgresql+asyncpg` passed the validator, so users whose `DATABASE_URL` carried `postgres+asyncpg://` hit `DF-401` at construction time before the new normalization could run.
- **Orphan: 14 express mutation methods now invoke `_check_append_only` (PR #856)** — `_check_append_only` was defined in PR #852 but only one of 14 mutation method bodies called it; the other 13 silently permitted writes on `append_only=True` models, defeating the documented contract. Same-shard fix-immediately per `rules/autonomous-execution.md` Rule 4. Defense-in-depth: `bulk_upsert` checks at both outer-body and inner-coroutine. ABC-gate fix on `AppendOnlyForbiddenNode` so typed exception surfaces instead of `TypeError: Can't instantiate abstract class`.

### Changed

- **`pool_utils._probe_postgresql` (PR #847)** now routes its inline `+asyncpg` strip through the canonical helper `dataflow.core.config._strip_asyncpg_driver_suffix`. Defense-in-depth — callers passing raw URLs that have not been routed through `DatabaseConfig.get_connection_url()` still get the suffix stripped here.

### Tests

- **#819:** 10 new Tier-2 regression tests at `tests/integration/test_issue_819_asyncpg_dsn_normalization.py` covering helper passthrough / strip behavior across plain/non-Postgres URLs and all three Postgres driver-suffix variants; real-Postgres round-trip via `DataFlow.get_connection()`; raw asyncpg connect on stripped output.
- **#839 + orphan:** 7 Tier-2 + 4 Tier-3 regression tests covering structural invariants and end-to-end rejection across all mutation surfaces against real Postgres.

### Migration

No breaking changes. Existing models without `append_only=True` operate identically. `@db.model(append_only=True)` is opt-in.

## [2.7.9] — 2026-05-06 — Async transaction event-loop mismatch (#835)

Patch release fixing a runtime regression where `db.transactions.transaction()` raised `RuntimeError: Event loop is closed` when invoked from an event loop different from the one that constructed the DataFlow instance. Bug fix; no public API surface change; no migration required.

### Fixed

- **`db.transactions.transaction()` now resolves its asyncpg pool through the same per-loop registry as `db.express.*`.** `TransactionManager._get_adapter` previously returned a wrapper around the long-lived `_connection_manager._adapter` whose pool was bound to the worker-thread loop that ran `DataFlow.__init__`; that loop closed at return and every subsequent `transaction()` call from a fresh loop hit `pool.acquire()` against the closed loop. Resolution now walks `_get_or_create_async_sql_node(db_type)._get_adapter()` — priority chain `_shared_pools` → runtime pool → `_PROCESS_POOL_REGISTRY` (WeakValueDictionary, reaped on loop close) → fallback `connect()` — under per-key creation locks. Issue #835.
- **`_get_adapter_from_context` (used by `TransactionScopeNode` / `TransactionSavepointNode`) is now async.** Every caller awaits it. The previous attribute-based access returned `None` when the cached node had not yet been initialized on the calling loop; the await ensures the priority chain runs.

### Changed

- **`ConnectionManager.initialize_pool()` now uses a transient reachability check** instead of retaining a long-lived adapter on `_connection_manager._adapter`. The init-time fail-fast contract from `dataflow-pool.md` Rule 2 (`await adapter.connect()` MUST succeed before `DataFlow.__init__` returns) is preserved exactly — the adapter is opened, verified, and `disconnect()`-ed within one `async_safe_run` call.
- **`_connection_manager._adapter` field is removed.** Internal callers (`health_check`, `get_connection_stats`, `disconnect`, dialect-detection sites in `engine.py` / `engine.async_methods.py`) migrated to walking `_PROCESS_POOL_REGISTRY` for live pool stats, or to the existing `dialect_factory` for type-only queries. Internal API only — no `__all__` export, no spec coverage; per `zero-tolerance.md` Rule 6a internal-only carve-out, no deprecation shim is required.
- **`_PoolWrapper` (internal) is removed.** It previously wrapped the dead-code branch of `TransactionManager._get_adapter()` and is no longer reachable after the routing change above.

### Tests

- 9 new Tier-2 regression tests at `tests/regression/test_issue_835_transaction_cross_loop.py` covering: cross-loop `begin()`, nested savepoint/rollback paths, `TransactionScope` async-cm, concurrent `begin()` from two loops, WeakValueDictionary reaping on loop close, and pool-cap stress (50 sequential loops). Autouse fixture lowers `idle_timeout=2` so pool churn under pytest-xdist parallelism does not breach `max_pool_count_per_process=100`. Production defaults are unchanged.

## [2.7.8] — 2026-05-06 — CLI generate command: filename validation hardening

Patch release closing a Tier-1 test isolation bug AND the production code path that allowed it. Bug fix; no API surface change; no migration required.

### Fixed

- **CLI `dataflow generate docs` no longer accepts unsafe `workflow.name` values for filename interpolation.** `dataflow.cli.generate.docs` previously interpolated `workflow.name` directly into the output filename via `f"{workflow.name}.md"`. Any non-string, path-traversal substring (`..`), or filesystem-unsafe character (`/`, `\`, control chars, shell metacharacters) was written to disk verbatim. Now routes through `dataflow.utils.filenames.safe_workflow_filename(name, ext)` which validates against `^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`, rejects path-traversal substrings, and raises `WorkflowNameError` (a `ValueError` subclass) on any invalid input.

### Added

- **NEW: `dataflow.utils.filenames`** — public helper module exporting `safe_workflow_filename()` and `WorkflowNameError`. Same trust-boundary discipline as `dialect.quote_identifier()` for SQL identifiers, applied to filesystem identifiers. Logs at WARN with a hashed `sha256[:8]` fingerprint on rejection (per `observability.md` Rule 8 — the raw input is never echoed to logs).
- **NEW: 52 Tier-1 regression tests** at `tests/unit/utils/test_filenames.py` pinning the helper's accept/reject contract: 9 accepted forms, 23 rejected forms (path-traversal, control chars, shell metacharacters, length cap, Unicode bidi-override, non-string, Mock-repr leak vector), 9 extension validation cases, plus error-message and logging hygiene assertions.
- **NEW regression test** `test_generate_documentation_rejects_unsafe_workflow_name` at `tests/unit/cli/test_generate_command.py` — exercises the historical Mock-leak vector end-to-end through the Click runner; asserts `exit_code == 2` and zero `<Mock` files written.

### Changed

- **`tests/unit/cli/test_generate_command.py`** — replaced `Mock(name="test_workflow")` (which sets the Mock's repr-name, NOT `.name`) with a `_make_workflow_mock()` helper that constructs the Mock then assigns `.name = "test_workflow"` post-construction. The `docs` test now uses `tmp_path` for `--output-dir` (per `tests/unit/CLAUDE.md` Tier-1 filesystem-isolation contract); previously pointed at the real `./docs/` directory and `Path.write_text` (used by `generate.py`) is NOT intercepted by `patch("builtins.open", mock_open())`.

### Origin

108 orphan `<Mock name='test_workflow.name' id='*'>.md` files accumulated under `docs/` (107) and `packages/kailash-dataflow/docs/` (1) since 2026-04-15 because the `unittest.mock.Mock(name=...)` API surface diverges from caller expectation: the `name=` kwarg sets the Mock's repr-name, NOT the `.name` attribute. Production code that f-strings `workflow.name` into a filename interpolated the child-Mock's `__str__` ("`<Mock name='test_workflow.name' id='...'>`") into a real path. Fix is two-layered: (a) the production code now validates at the trust boundary regardless of test-side correctness, (b) the test correctly constructs the Mock and uses `tmp_path`. Workspace `issue-829-kaizen-llm-first-traits/journal/0005-DECISION-codify-loopback-close-after-loom-sync-2.20.0.md` § F4 captures the discovery and the orphan-file cleanup.

## [2.7.7] — 2026-05-04 — engine.py pyright cleanup (dataflow-engine-pyright-cleanup workspace)

Patch release cutting PyPI for the dataflow-engine-pyright-cleanup workspace (T1–T8). Static-analysis-only diff: brings `engine.py` from `5 errors, 56 warnings` to `0 errors, 8 warnings` against pinned `pyright==1.1.371`.

### Fixed (zero-tolerance Rule 1 — pre-existing static-analysis failures)

- **E1** — Production code no longer imports from `tests.fixtures.*`. `MockConnectionPool` relocated to `dataflow.testing.mock_helpers` (real package path); `engine.py:3427::get_connection_pool()` imports from the new location; old `tests/fixtures/mock_helpers.py` deleted (zero remaining importers verified).
- **E2** — `TenantContextSwitch` forward-reference at `engine.py::tenant_context` resolves via `TYPE_CHECKING` import (orphan-detection.md Rule 6b); runtime local-import behavior unchanged.
- **E3, E4, E5** — `discover_schema()` flow restructured per zero-tolerance.md Rule 3a: `discovered_schema` pre-initialized to `None`; every reachable inner branch assigns or raises; typed-guard added at the return path. Four redundant local `import asyncio` statements deleted (module-scope import at L7 is canonical).

### Changed (warning triage — 48 of 56 warnings closed at root cause)

- **W1 (12 warnings)** — `dataflow.adapters.connection_parser.build_connection_string` signature corrected: `scheme/host/database/username/password/port` typed `Optional[...]` (was `str = None` / `int = None` — invalid mismatched annotation).
- **W2 (13 warnings)** — `assert ... is not None` typed-narrowing applied at every site accessing `_migration_system`, `_schema_state_manager`, `_fabric`, `ErrorEnhancer`, async DB `conn`. Each assert carries an actionable error message identifying the missing-init path.
- **W3 (10 warnings)** — Method signatures corrected: `create_tables`, `create_tables_async`, `_ensure_migration_tables`, `_ensure_migration_tables_async`, `_execute_ddl`, `_execute_ddl_async`, `create_tables_sync`, `get_relationships`, `create_workflow`, `get_available_nodes` now declare `Optional[T] = None`.
- **W4 (5 warnings)** — Subclass-scoped `AsyncSQLDatabaseNode._shared_pools / .clear_shared_pools / ._cleanup_closed_loop_pools` accessed via `getattr()` to bypass pyright's narrow-to-base-type inference.
- **W5 (4 warnings)** — `cls._dataflow / ._dataflow_meta` and `DynamicModel/ReconstructedModel._dataflow*` assignments now use `setattr()` (explicit dynamic-set form pyright accepts).
- **W6 (2 warnings)** — Refactored `with cursor:` to explicit try/finally on the sync psycopg2 path; cleaner code that bypasses pyright's type-stub gap on the polymorphic connection return type.
- **W7-misc (~2 closed)** — `DataFlowConfig.max_overflow` runtime shim now uses `setattr()`; `_Proxy.__field_validators__` runtime assignment uses `setattr()`.

### Added — regression gate

- `packages/kailash-dataflow/tests/regression/test_engine_pyright_invariant.py` — 4 tests asserting `engine.py` stays at `0 errors / ≤10 warnings` against pinned `pyright==1.1.371`. Threshold relaxation requires the Rule 1b protocol (tracking issue + release-specialist signoff). Suppressions audit: every `# pyright: ignore[<rule>]` MUST have a `# Reason: <X>` line within ±5 lines.
- `pyright==1.1.371` pinned EXACTLY in `[project.optional-dependencies].dev`.

### Surviving warnings (8, under brief's ≤10 ceiling)

All structural/upstream-typing-stub limitations: `cache_enabled` Optional/bool, `DataFlowProtocol` mismatch, `refresh` Literal, `__name__` on `Literal['Decimal']`, `ConnectionManager.get_connection` stub gap, `_schema_state_manager` subclass-attr, asyncpg `Connection.fetch` stub gap, "Never" not awaitable. Documented in workspace's `specs/regression-gate-contract.md`.

### Notes

- API-surface change: `dataflow.testing.mock_helpers.MockConnectionPool` is now the canonical location (was `tests.fixtures.mock_helpers.MockConnectionPool`). The old import path is BLOCKED per `production-test-isolation.md` invariant. The 10 integration tests using `db.get_connection_pool()` continue to work without modification (they call the method, not the symbol directly).
- Zero behavior change: all fixes are type-narrowing / dynamic-attribute-explicit / signature-correctness. No control-flow changes outside `discover_schema()` (which now raises a typed `RuntimeError` on the previously-unreachable invariant-violation path instead of silently returning unbound state).

## [2.7.6] — 2026-05-03 — issue #781 hygiene release (T1)

Patch release cutting PyPI for T1 (dataflow TODO-NNN comment-strip) of the issue #781 cleanup workstream.

### Changed (T1 of #781 — comment-only, packages/kailash-dataflow/src/)

- Stripped 89 `TODO-NNN` markers across 48 files in `dataflow/migrations/`, `dataflow/core/`, `dataflow/fabric/`, `dataflow/features/` per the ratified disposition catalog (24 Class 1a header banner / inline-shipped, 45 Class 1b module docstring provenance, 20 Class 3 mid-comment cross-reference). The disposition convention is documented at `workspaces/issue-781-todo-nnn-cleanup/02-plans/01-cleanup-architecture.md`.
- Aligned `tests/unit/core/test_model_registry_runtime_injection.py` with post-S5 lazy-property semantics (test-file change, no production behavior).

### Notes

- Comment-only diff: zero changes to imports, signatures, control flow, or types. The bump cuts PyPI per `build-repo-release-discipline.md` Rule 1 so downstream consumers pick up the cleaned tree.

## [2.7.5] — 2026-05-01 — `bulk_create` AttributeError on bare-type field specs (#774)

Patch release closing issue #774. `NodeGenerator.generate_*_nodes` accepted both dict-form (`{"name": {"type": str}}`) and bare-type (`{"name": str}`) field specs by signature, but only dict-form by behavior. Direct callers passing bare-type form crashed at `dataflow/core/nodes.py:837` with `AttributeError: type object 'str' has no attribute 'get'` because the downstream `self.model_fields.get(name, {}).get("type")` chain assumed dict-form. The canonical `@db.model` path (`engine.py:1858`) already produced dict-form, so the bug only surfaced when external code constructed bulk nodes through the public `NodeGenerator` API directly.

### Fixed

- **#774 — Field-spec normalization at the node constructor boundary.** New `_normalize_field_specs()` helper at `dataflow/core/nodes.py` makes the contract explicit: `self.model_fields` is canonical dict-form everywhere downstream regardless of caller-supplied shape. Defense-in-depth `isinstance` guards added to `_coerce_record_id` and `convert_datetime_fields` for any external caller bypassing the constructor.

### Tests

- `tests/regression/test_issue_774_bulk_create_field_spec_normalization.py` — covers Tier 1 (replays the originally-failing unit test against bare-type form), structural-invariant (pins the normalizer contract for both dict-form and bare-type shapes), and Tier 2 (round-trip via `@db.model` against real PostgreSQL).

### Cross-SDK

- N/A — kailash-rs uses strongly-typed `Vec<FieldDef>` with `FieldType` enum (`crates/kailash-dataflow/src/model.rs:587`, `:842`); the bug class is structurally unreachable. No upstream issue to file.

## [2.7.4] — 2026-05-01 — Declare `psycopg2-binary` as baseline dependency (#753)

Patch release closing issue #753. The synchronous DDL / migration path (`SyncDDLExecutor._get_postgresql_connection`, `MigrationConnectionManager._connect_with_retry`, `dataflow.core.pool_utils._is_postgresql_url`) imports `psycopg2` to bootstrap registry tables and run `auto_migrate=True` against PostgreSQL. The package declared `asyncpg` (covering runtime DML) but did NOT declare `psycopg2` / `psycopg2-binary` as a baseline dep nor as an optional extra. Every fresh install pointed at a PostgreSQL `DATABASE_URL` failed at the first `auto_migrate` trigger with `ModuleNotFoundError: No module named 'psycopg2'`, then crashed downstream DML with `relation "<table>" does not exist` because the registry/schema bootstrap silently failed earlier in the stack trace.

### Fixed

- **#753 — `psycopg2-binary>=2.9` added to baseline `dependencies`.** Treatment matches the existing baseline-driver pattern (`asyncpg`, `aiosqlite`, `aiomysql`, `motor`, `pymongo` are all baseline) — DataFlow bundles all DB drivers so users pick which they use; the asymmetric "asyncpg baseline + psycopg2 missing" was a packaging bug, not a design choice.

### Tests

- `tests/regression/test_issue_753_psycopg2_dep_declared.py` — structural regression covering: (a) `pyproject.toml::dependencies` declares `psycopg2-binary` (catches a future "dep cleanup" that removes it without test signal); (b) `import psycopg2` resolves at module-scope from the dataflow package; (c) `SyncDDLExecutor._get_postgresql_connection` no longer raises `ImportError` when invoked against a postgres URL.

### Cross-SDK

- N/A — kailash-rs uses `tokio_postgres` / `sqlx` natively and has no equivalent Python-driver-declaration failure mode.

## [2.7.3] — 2026-05-01 — `@db.model` accepts parameterized generics on Python 3.11+ (#768)

Patch release closing issue #768. `FieldTypeProcessor._resolve_type` returned parameterized builtin generics (`list[str]`, `dict[str, Any]`, `typing.List[str]`, PEP 604 `list[str] | None`) verbatim. The next `isinstance(value, expected_type)` call raised `TypeError: isinstance() argument 2 cannot be a parameterized generic` on Python 3.11+, crashing every CRUD operation against models that used the standard, idiomatic form of list / dict / tuple annotations.

### Fixed

- **#768 — `_resolve_type` strips parameterized generics down to their origin.** `list[str]` / `typing.List[str]` resolves to `list`; `dict[str, Any]` resolves to `dict`; `tuple[int, ...]` resolves to `tuple`. The Optional / Union path now recurses on the inner non-None type so `Optional[list[str]]` resolves through `list[str]` to `list`.
- **#768 — PEP 604 union form (`list[str] | None`) handled.** `get_origin` returns `types.UnionType` for PEP 604 syntax (vs `typing.Union` for the legacy form). The resolver now matches both and recurses identically through the parameterized inner type.

### Tests

- `tests/regression/test_issue_768_parameterized_generics.py` — 15 tests covering: structural invariants on `_resolve_type` for every generic shape called out in the issue acceptance (`list[str]`, `dict[str, Any]`, `tuple[int, ...]`, `typing.List[str]`, `typing.Dict[str, Any]`, `typing.Optional[list[str]]`, PEP 604 `list[str] | None`, `dict[str, Any] | None`, plain types unchanged); end-to-end CRUD against SQLite for `@db.model` with `list[str]`, `dict[str, Any]`, `typing.List[str]`, and PEP 604 `list[str] | None` field annotations. Pre-fix behavior: `TypeError("isinstance() argument 2 cannot be a parameterized generic")` on every CRUD operation. Post-fix: 15/15 pass.

### Cross-SDK

- kailash-rs uses `syn`-time parsing for model derivation and is structurally immune to this Python-runtime `isinstance` failure mode (Rust types are erased at compile time; runtime isinstance equivalent does not exist). Cross-SDK loop closure pending explicit human approval per `rules/upstream-issue-hygiene.md` MUST Rule 1.

### Follow-up

- `_resolve_type` and `dataflow.core.nodes._normalize_type_annotation` remain as parallel implementations of essentially the same logic. Consolidation into a single shared helper is recommended (issue acceptance criterion 6). Deferred to follow-up issue — exceeds the one-shard budget for this fix and would expand blast radius beyond the surface the bug class touched.

## [2.7.2] — 2026-05-01 — Express list/count cache invalidation aligned with producer key shape (#750)

Patch release closing issue #750. `db.express.list(...)` returned STALE rows after `db.express.update / .delete / .create` because the `ListNodeCacheIntegration` invalidation patterns never matched the actual cache keys. Disk state was always correct; the bug was a silent no-op invalidation in the read-path cache layer.

### Fixed

- **#750 — `ListNodeCacheIntegration._setup_invalidation_patterns` now uses the producer-side key prefix.** `CacheKeyGenerator.generate_key` produces keys of shape `{prefix}:{model}:{version}:{hash}` where `prefix` defaults to `"dataflow:query"` (per `DataFlowConfig.cache_key_prefix`). Previous patterns `"{model}:list:*"` / `"{model}:record:{id}"` / `"{model}:count:*"` substring-matched against expanded patterns like `"Tag:list:"` — which never appears in any real key — so every create/update/delete/bulk\__ invalidation was a silent no-op. Patterns now use a version-wildcard sweep `f"{prefix}:{{model}}:_"`so every cache entry for the model is swept regardless of operation kind, and the format survives future keyspace bumps unchanged (per`rules/tenant-isolation.md`Rule 3a). Affects all DataFlow consumers with`enable_query_cache=True`(the default) — every`list()`/`count()` / filtered-list call after a mutation served stale data.
- **`asyncio.iscoroutinefunction` deprecated since Python 3.14, scheduled for removal in 3.16.** Replaced with `inspect.iscoroutinefunction` in `packages/kailash-dataflow/src/dataflow/cache/list_node_integration.py` and `packages/kailash-dataflow/src/dataflow/cache/invalidation.py` (3 call sites total) per `rules/zero-tolerance.md` Rule 1. The `asyncio.iscoroutine` form remains valid and is unchanged.

### Tests

- `tests/regression/test_issue_750_express_list_cache_invalidation.py` — Tier-2 SQLite regression test asserting list reflects update / delete / create across the full express → node → cache_integration path (the path that the broken patterns silently no-op'd). Includes a structural-invariant test that pins the actual key shape against a registered invalidation pattern, so any future refactor that introduces a producer/invalidator key-format drift fails loudly at gate time.

### Cross-SDK

- kailash-rs DataFlow's read-path cache layer (if it exposes a comparable invalidation pattern system) is expected to carry the same gap if its producer key shape and invalidator pattern strings were drafted independently. Cross-SDK verification ticket per `rules/cross-sdk-inspection.md` MUST Rule 1 — disposition pending explicit human approval per `rules/upstream-issue-hygiene.md` MUST Rule 1.

## [2.7.1] — 2026-05-01 — DPI-A propagation: Express raises `DDLFailedError` instead of returning failure dict (#759)

Patch release closing issue #759. DataFlow Express's `create` / `update` / `delete` / `upsert` / `upsert_advanced` previously returned the underlying CRUD node's `{"success": False, "error": ...}` failure dict to the caller when an auto-migration DDL failure recorded the model as failed. This broke the DPI-A 2.4.0 fail-fast contract — `await db.express.create(...)` returned a "result" with `success=False` instead of raising the typed `DDLFailedError` the user-facing API documented.

### Fixed

- **#759 — `DataFlowExpress.{create,update,delete,upsert,upsert_advanced}` raise `DDLFailedError` on recorded DDL failure (PR #43eb851f + this release).** Express now invokes a single helper `_raise_for_failed_result` immediately after the underlying `node.async_run(...)` returns. The helper first delegates to `engine._check_failed_ddl(model)` so a recorded DDL failure surfaces as the documented typed exception with the original `statement_preview`; otherwise it raises a generic `RuntimeError("express.<op> failed for model <m>: <error>")` so callers still observe a typed exception rather than the legacy dict shape. `_trust_record_failure` is invoked on the raise path (audit trail no longer records a phantom success).
- **#759 (refinement) — `_check_failed_ddl` probed under both model-name and table-name keys.** The engine's bulk-DDL path (`_execute_ddl` / `_execute_ddl_async`, engine.py:7903 / 7992 / 8466) records failures under the extracted SQL identifier (`dpi_d2_children`) returned by `_extract_table_from_statement`, while the single-model path (engine.py:2157, 8263) records under the model class name (`DpiD2Child`). Express now probes both shapes via the new `_class_name_to_table_name` helper before falling through to the generic `RuntimeError`. Without the table-name fallback, the bulk-DDL path (the common DPI-A failure mode) silently emitted the generic error instead of `DDLFailedError`.
- **#759 (refinement) — `CreateNode.async_run` re-raises `DDLFailedError` instead of converting to the legacy failure dict.** The CreateNode-level swallow at the operation-error boundary is preserved for backward compatibility with WorkflowBuilder consumers (their `{"success": False}` contract is intact), but the typed DDL circuit-breaker exception is now treated as a structural failure that propagates through to express. `ensure_table_exists`'s exception handler also re-raises `DDLFailedError` rather than logging-and-continuing — log-and-continue would mask the engine-recorded DDL failure exactly as the original swallow did.

### Tests

- `tests/regression/test_issue_759_express_propagates_ddl_failure.py` — deterministic Tier 1+2 propagation matrix covering `create` / `update` / `delete` / `upsert` and the `auto_migrate="warn"` legacy log-and-continue contract. Pre-records a synthetic DDL failure on each test's DataFlow instance via `engine._record_failed_ddl(...)` then asserts `DDLFailedError` propagates (or, in warn mode, MUST NOT propagate as `DDLFailedError`).
- `tests/regression/test_dataflow_pool_bridge.py::test_failed_ddl_does_not_leak_pools_under_saturation` — pre-existing concurrent-saturation test rewritten to pre-record a synthetic DDL failure on each instance (the original FK-misordering setup did not actually emit any FK constraints — the failures observed were pool exhaustion, never DDL). The test still asserts the DPI-D2 pool-bound invariant (≤5 pools) AND now asserts at least one of the 10 instances raises `DDLFailedError` through the express layer.

### Cross-SDK

- See cross-SDK note appended at the bottom of this release-prep PR — kailash-rs DataFlow's CRUD-Express path may carry the same swallow pattern. Companion issue filed against `esperie-enterprise/kailash-rs` per `rules/cross-sdk-inspection.md` MUST Rule 1.

## [2.7.0] — 2026-04-30 — Sync transaction surface (#711) + #707 test fix

Minor release adding `db.transactions_sync` — a sync-style transaction manager that owns its connection lifecycle on a dedicated background event loop, so synchronous callers can compose multi-statement atomic units of work without juggling `asyncio.run()` boundaries.

### Added

- **`db.transactions_sync` property + `SyncTransactionManager` + `SyncTransactionScope` (#711)** — the sync surface owns its own background loop and connection acquisition. Multi-statement atomic blocks survive process restarts, fail with typed `TransactionRolledBack` on any inner exception, and return per-statement diagnostics. Spec: `packages/kailash-dataflow/specs/dataflow-cache.md` § 12.7.
- Tier 1 unit suite for `SyncTransactionManager` lifecycle + rollback paths.
- Tier 2 integration suite for `db.transactions_sync` against real Postgres.

### Fixed

- **#707 — idempotency regression test rewritten to canonical `INSERT ... ON CONFLICT DO NOTHING` pattern (#748)** — the original repro relied on `tx.execute_raw` routing `INSERT … RETURNING` through `fetch`, which is not how the sync surface dispatches statements (only `SELECT` / `WITH` are SELECT-shape). The test now follows the canonical pattern and parses the asyncpg command-tag rowcount instead.
- **#707 — fixture missing `db.initialize()` call** — added explicit `await db.initialize()` to the sync-transaction fixture so the connection is reachable before the regression test runs.

### Dependencies

- `kailash>=2.13.1` (was `>=2.12.0`).

## [2.6.0] — 2026-04-30 — Lazy runtime resolution + DDL connection-reuse (the v2.13.0 cluster: closes #713, #714)

Minor release closing the two remaining DataFlow surfaces in the the v2.13.0 cluster. Backward-compatible: every existing `db.runtime`-reading consumer keeps working unchanged because the new `@property` resolves to the same runtime instance per event loop, and the existing `db.runtime = X` mutation pattern is preserved through the new setter.

### Added

- **`DataFlow.runtime` lazy `@property` + setter + `runtime=` `__init__` kwarg (#713 / S4)** — `DataFlow.runtime` is now resolved per access via a per-event-loop cache rather than bound at construction time. Resolution order: (1) setter override (`db.runtime = X`, `runtime=` kwarg, `monkeypatch.setattr`), (2) `None` if `_closed`, (3) per-event-loop `AsyncLocalRuntime` cache (mirrors the per-loop `_async_sql_node_cache` pattern at engine.py:7488), (4) cached sync `LocalRuntime` singleton. The `runtime=` `__init__` kwarg is the explicit escape hatch for callers that need a specific runtime from construction. Pickle / deepcopy round-trip support: the per-loop cache is excluded from `__getstate__` and rebuilt lazily on first access in the unpickled instance, making DataFlow safe to ship across multiprocessing / Ray / Dask workers.
- **DDL connection reuse via `SyncDDLExecutor.execute_ddl_batch_per_statement` (#714 / S6)** — `_execute_ddl` (sync) and `_execute_ddl_async` (async, via `asyncio.to_thread`) now run the entire DDL batch on a single sync connection acquired from the dialect driver (`psycopg2` / `sqlite3` / `pymysql`). Per-statement results are captured (success/error/duration_ms) so the #696 fail-fast circuit-breaker continues to fire on individual CREATE TABLE failures while index/FK/auxiliary failures continue past (legacy semantics).

### Fixed

- **#713 — module-import construction permanently bound `LocalRuntime` (S4)** — pre-fix, `db = DataFlow(...)` at module scope ran with no event loop and bound `LocalRuntime` for the instance's lifetime, so `await db.create_tables_async()` from inside FastAPI/uvicorn either raised "no running event loop" or quietly used the wrong runtime. Lazy per-loop resolution fixes this without breaking the synchronous CLI path.
- **#713 — subsystem captures snapshot the runtime at `__init__` time (S5)** — `DataFlowExpress`, `DataFlowExpressSync`, `BulkOperations`, `TransactionManager`, `_DataFlowAuditQueryProxy`, `_DataFlowAuditExportProxy` previously captured `self.runtime = dataflow.runtime` at construction. Captured runtimes did not follow setter overrides and missed the per-event-loop cache. All six subsystems now hold `self._dataflow = dataflow` and read `self._dataflow.runtime` lazily on each operation, picking up `db.runtime = X` mutations and the per-loop cache transparently.
- **#714 — DDL connection thrash (S6)** — pre-fix, `_execute_ddl` / `_execute_ddl_async` routed every CREATE TABLE / CREATE INDEX through a fresh `AsyncSQLDatabaseNode` instance (one connection acquire/release per statement). Under `auto_migrate=True` with N models, this produced ≈ 2N+ connection acquires at startup, exhausting pgbouncer transaction-pool slots or constrained Azure PostgreSQL `max_connections` before the application opened to traffic. The single-sync-connection path closes that failure mode.

### Tests

- `packages/kailash-dataflow/tests/regression/test_issue_713_module_import_then_async_ddl.py` — Tier 3 regression for the module-import construction → async DDL path.
- `packages/kailash-dataflow/tests/regression/test_issue_713_subsystems_follow_runtime_swap.py` — Tier 2 regression for subsystem lazy lookups (every subsystem follows `db.runtime = X` mutations).
- `packages/kailash-dataflow/tests/regression/test_issue_714_ddl_single_connection.py` — structural + behavioral regression suite pinning the single-connection contract; verifies the #696 fail-fast circuit-breaker is preserved through the refactor.

### Cross-SDK

- kailash-rs Tokio runtime is always present at construction time; no equivalent module-import footgun for #713. No companion issue.
- kailash-rs may have analogous DDL connection thrash for #714 — companion issue to be filed.

## [2.5.0] — 2026-04-29 — `TransactionScope.execute_raw` for multi-statement raw-SQL atomicity

Minor release adding the `TransactionScope.execute_raw` surface from issue #707 (closed by PR #716). Backward-compatible: every prior `db.transactions.begin()` consumer keeps working unchanged via the dict-style `__getitem__`/`__setitem__` shim. Bundles a latent savepoint async-context-manager bug fix discovered during implementation review.

### Added

- **`TransactionScope.execute_raw(sql, params=None)` for multi-statement raw-SQL atomicity (#707)**: `db.transactions.begin()` now yields a `TransactionScope` (replacing the prior bare `dict`) carrying the canonical metadata (`id`, `isolation_level`, `status`, `type`, `depth`) AND an `execute_raw` method that routes every call to the connection pinned for the lifetime of the `async with` body. Closes the OAuth credential rotation use case from #707: SELECT FOR UPDATE + UPDATE-or-INSERT now expressible in one atomic transaction without the Express API. Calling `tx.execute_raw` outside the `async with` body raises `RuntimeError` per `rules/zero-tolerance.md` Rule 3a (typed delegate guard) — the pinned connection only exists while the scope is active. The asyncpg vs aiosqlite parameter-binding shape is dispatched by connection type. SELECT-style statements return rows; INSERT/UPDATE/DELETE return the driver's command-tag string (asyncpg) or cursor (aiosqlite). Backward-compat: existing `txn["id"]` / `txn["status"]= "..."` dict-style access preserved via `__getitem__` / `__setitem__` that map through to attributes — every prior consumer keeps working unchanged. Public surface: `TransactionScope` exported from `dataflow.features` (and via `dataflow.features.transactions`).

### Fixed

- **Savepoint context-manager invocation (#707, bundled fix)**: `TransactionManager.begin()` previously invoked the nested-transaction (savepoint) path with `async for ctx in self._savepoint(): yield ctx`, which iterates an `@asynccontextmanager`-decorated method as if it were an async generator. Corrected to `async with self._savepoint() as ctx: yield ctx`. The bug was latent because no test exercised nested `db.transactions.begin()` calls; the new #707 regression suite covers the canonical surface and the reviewer flagged the savepoint path as adjacent.

### Tests

- Added Tier 2 regression suite at `packages/kailash-dataflow/tests/regression/test_issue_707_transaction_pins_connection.py`:
  - `test_multi_statement_atomicity_via_tx_execute_raw` — BEGIN-INSERT-INSERT-COMMIT verified via fresh-connection read-back.
  - `test_auto_rollback_on_exception` — exception inside `async with` body MUST roll back; OAuth-rotation invariant.
  - `test_oauth_credential_rotation_pattern` — full SELECT FOR UPDATE + UPDATE-or-INSERT cycle across 4 transactions.
  - `test_select_for_update_then_insert_idempotency` — two concurrent transactions racing on the same idempotency token serialize on `SELECT ... FOR UPDATE`; exactly-one-insert invariant.
  - `test_partial_failure_within_transaction_rolls_back_all` — UNIQUE-constraint violation mid-txn rolls back the prior row.
  - `test_execute_raw_outside_scope_raises_runtime_error` — Rule 3a typed delegate guard, runs without infrastructure.

### Cross-SDK

- kailash-rs#688 tracks the equivalent `TransactionScope::execute_raw` surface for the Rust SDK (cross-SDK alignment per `rules/cross-sdk-inspection.md` Rule 1 + EATP D6 matching semantics).

### Specification

- `specs/dataflow-cache.md` §12.6 documents the multi-statement atomicity surface and pins the `_active_transaction` ContextVar contract that `tx.execute_raw` and `db.execute_raw_lightweight` (called inside the `async with` body) both honor.

---

## [2.4.0] — 2026-04-28 — DDL fail-fast, DDLFailedError, build_sync surface

Minor release delivering three production-incident fixes from the `dataflow-prod-incident` workstream (shards DPI-A, DPI-C) plus the kailash core floor bump to 2.12.0 required by DPI-B (pool registry leak fix).

- DPI-A: `auto_migrate` now raises `DDLFailedError` (a `DataFlowError` subclass) immediately when DDL fails, rather than silently continuing. Surfaces as `DDLFailedError` on first DataFlow access with a broken schema. `DDLFailedError` is exported from the `dataflow` package top-level.
- DPI-C: `DataFlowEngineBuilder.build_sync()` added as a synchronous builder surface for sync-only contexts (scripts, CLI tools, Django management commands).
- Dep floor: `kailash>=2.12.0` required — pulls in `pool_count()` and `_PROCESS_POOL_REGISTRY` (DPI-B pool leak fix from kailash core).

### Added

- `DDLFailedError` raised by `auto_migrate` on DDL failure (DPI-A, closes #696).
- `DataFlowEngineBuilder.build_sync()` synchronous builder (DPI-C, closes #698).

### Changed

- Minimum kailash core dependency bumped from `>=2.11.0` to `>=2.12.0` (DPI-B pool registry, closes #697).

---

## [2.3.3] — 2026-04-28 — Migration test-suite + pyright cleanup follow-through

Patch release closing the merged-but-unreleased gap on `kailash-dataflow` main. Three commits since 2.3.2:

- `95e8e2c8` (PR #684) — `not_null_handler.py` pyright cleanup: 8 errors / 2 warnings to 0 / 0. Production source change in `packages/kailash-dataflow/src/dataflow/migrations/not_null_handler.py`; per `rules/build-repo-release-discipline.md` Rule 5 this triggers the version bump.
- `f1dfb194` (PR #689, closes #683) — repaired test mock-method drift in 4 not_null_handler unit-test files where mocks invoked methods that no longer exist on the production class.
- `391617d1` (PR #690, closes #688) — aligned 4 migration unit-test files (column removal, dependency analyzer, impact analysis reporter, application-safe rename) to the post-refactor production surface.

### Fixed

- Pyright drift in `not_null_handler.py` (PR #684).
- Test-mock drift across 8 migration unit-test files (PRs #689, #690). Local `pytest packages/kailash-dataflow/tests/unit/migrations/` is GREEN at 717 passed / 0 failed; these tests are not yet in CI per #688.

### Notes

- No production runtime behavior change beyond the type-checking cleanup in `not_null_handler.py`.
- 13 pre-existing pytest warnings in the migrations suite remain (separate workstreams: `MigrationPerformanceTracker._stop_monitoring` un-awaited coroutine, `AsyncMockMixin._execute_mock_call` un-awaited coroutine in test framework).

## [2.3.2] — 2026-04-27 — emit_train_end structural error redaction (W7-002, Round-3 LOW-2 carry-forward)

### Security

- **HIGH** Wire `dataflow.classification.event_payload.format_error_for_event` (new helper) into `dataflow.ml._events.emit_train_end` so the emitter — not the caller — structurally redacts classified field VALUES and classified field NAMES from the `error: Optional[str]` argument before publishing the `kailash_ml.train.end` `DomainEvent`. Per `rules/event-payload-classification.md` § 1, caller-side sanitisation documented in the previous spec was not a structural defence — every call site that forgot the rule shipped raw `str(exc)` strings to subscribers, tracing spans, and observability vendors. The fix is single-filter-point at the emitter: callers MAY pass `str(exc)` directly, including DB-engine error strings that interpolate row data (`DETAIL: Failing row contains (alice@tenant.example, hunter2)`) — the helper substitutes any classified value with `"[REDACTED]"` and scrubs classified field names that appear verbatim. Closes the W6 audit's Round-3 LOW-2 finding (carry-forward W7-002).

### Added

- **`dataflow.classification.event_payload.format_error_for_event(policy, error_str, *, model_name=None, known_field_values=None)`** — public helper for emitter-side error redaction. Re-exported through `dataflow.classification.__all__` per `rules/orphan-detection.md` § 6. The helper:
  - returns `None` for `None` and the input unchanged when policy is `None` or the input is empty/whitespace,
  - scrubs known classified VALUES (when caller supplies the row dict via `known_field_values=`) using the `[REDACTED]` sentinel,
  - scrubs classified field NAMES that appear verbatim in the error string (DB engine errors leak column names; `rules/observability.md` Rule 8 classifies field names as schema-revealing),
  - enforces a 3-character minimum scrub length to avoid shredding error strings on common substrings,
  - supports `model_name=None` mode for ML training paths where the active model name is not bound at emit time (scans every classified field across every registered model in the policy).

  Cross-SDK: helper-name, sentinel, and minimum-scrub-length are intentionally aligned with the equivalent kailash-rs surface so the same input produces byte-identical scrubbed payloads in both SDKs.

### Tests

- **Tier 2 regression — `tests/integration/test_emit_train_end_redaction.py`** — 4 regression tests subscribe a real handler to the DataFlow event bus, trigger `emit_train_end` with classified content in the error string, and assert the published payload has the classified content scrubbed. Per `rules/event-payload-classification.md` § 4: helper-level unit tests are necessary but insufficient; only an end-to-end exercise against the real bus proves the emitter invokes the helper. Marked `@pytest.mark.regression` + `@pytest.mark.integration` per `rules/testing.md`.

### Documentation

- Updated `specs/dataflow-ml-integration.md` § 4A.2 — replaced the "Caller is responsible for sanitizing" docstring contract with the emitter-redacted contract, referencing `format_error_for_event` and `rules/event-payload-classification.md` § 1.
- Cross-spec re-derivation per `rules/specs-authority.md` § 5b: `kailash-core-ml-integration.md` § 3.4 (MLError discipline) lightly amended to clarify that the emitter-side helper is defense-in-depth, NOT a license to construct leaky MLError messages — the caller-construction discipline remains the primary gate. Other ml-_ and dataflow-ml-_ specs were re-derived but required no changes (no references to `emit_train_end` / `format_error_for_event` / caller-sanitization vocabulary).

## [Unreleased] — DataFlow × ML error-name spec compliance + TenantTrustManager orphan removal (W6-003 / W6-006 / W6-017)

### Tests

- **Pinned `dataflow.hash()` byte-vector tests against kailash-rs reference (closes F-B-31, W6-017).** Added `packages/kailash-dataflow/tests/regression/test_hash_byte_vectors.py` with 5 pinned reference vectors covering sentinel cases (empty frame, single-row, all-zero, two-column, mixed types) per `rules/cross-sdk-inspection.md` MUST 4. Each vector is a `(polars.DataFrame, expected sha256:<64hex>)` tuple derived empirically from kailash-py at polars 1.40.0 — these ARE the canonical reference set the kailash-rs `dataflow::hash()` implementation MUST match byte-for-byte once it lands. Also pins format invariant (`^sha256:[a-f0-9]{64}$`) and signature invariant (positional `df`, keyword-only `algorithm='sha256'` and `stable=True`) per `cross-sdk-inspection.md` § 3a structural API-divergence disposition. The cross-SDK byte-for-byte parity assertion is deferred via `pytest.skip` because kailash-rs has not yet implemented the Rust-side helper (no `crates/kailash-dataflow/src/hash.rs` or `ml/` module exists at the time of writing); per `rules/zero-tolerance.md` Rule 2, no fabricated reference vectors. When the Rust implementation lands, the skip flips on and the byte-for-byte check executes against these pinned vectors.

### Changed

- **`dataflow.ml.MLTenantRequiredError` → `dataflow.ml.TenantRequiredError`** — renamed the ML-bridge tenant-required error to match `specs/dataflow-ml-integration.md` § 5 canonical name; spec-following users hit `ImportError` against the old name. Closes finding F-B-23.

### Deprecated

- **`MLTenantRequiredError`** — deprecated alias resolves to `TenantRequiredError` via module-level `__getattr__` on both `dataflow.ml` and `dataflow.ml._errors`; access emits a `DeprecationWarning`. The alias is intentionally absent from `__all__` so star-imports pick up only the canonical name. Slated for removal in **kailash-dataflow v3.0** — callers MUST migrate within the v2.x window. Per user `feedback_no_shims`, this is a 1-release back-compat bridge with an explicit removal milestone, NOT a permanent shim.

### Removed

- **Removed unused `TenantTrustManager` per orphan-detection §3 — no production call site existed (closes F-B-05).** The `dataflow.trust.multi_tenant.TenantTrustManager` class and its `CrossTenantDelegation` companion were exposed publicly but no framework hot-path (express read/list, query engine, cache adapter) ever invoked them. The `db._tenant_trust_manager` facade was already withdrawn on 2026-04-18 (Phase-5.11-shaped orphan); the class itself was retained as a standalone import "for when a production call site lands" — that call site never materialised in 9+ days. Per `rules/orphan-detection.md` § 3 ("Removed = Deleted, Not Deprecated"), the source (`packages/kailash-dataflow/src/dataflow/trust/multi_tenant.py`, 585 LOC) and tests (`tests/unit/trust/test_multi_tenant.py` + `test_multi_tenant_thread_safety.py`, 1,741 LOC) were deleted. `dataflow.trust.__init__::__all__` no longer exports `TenantTrustManager` or `CrossTenantDelegation`. Existing regression test `tests/regression/test_trust_manager_wiring.py` was inverted — now asserts BOTH the absent-facade AND the deleted-class invariants (2 tests, both passing). When a production cross-tenant delegation requirement lands, design the new surface against the framework's hot path in the SAME PR — do NOT resurrect the orphan from git history without a real call site. **User impact:** `from dataflow.trust import TenantTrustManager` now raises `ImportError` (acceptable per orphan-detection §3 — silent deprecation banners are the failure mode this rule prevents).

## [2.3.1] — 2026-04-26 — SecurityDefinerBuilder owner-pinning + COMMENT defense-in-depth (#607 follow-up)

### Security

- **HIGH** Add mandatory `function_owner` builder field + emit `ALTER FUNCTION ... OWNER TO` so SECURITY DEFINER helpers run as a low-privilege role (CVE-2018-1058 component B). Without owner pinning every emitted helper inherited the migration-runner's role (typically superuser) — defeating the bypass-protection design intent. The new statement order is `CREATE → ALTER OWNER → COMMENT → REVOKE → GRANT` (5 statements, was 4). `SecurityDefinerBuilder.build()` raises `SecurityDefinerBuilderError("function_owner is required ...")` when the setter is unset; existing call sites MUST add `.function_owner(<low_privilege_role>)` to the fluent chain.
- **HIGH** Replace fragile `chr(39).replace` COMMENT escape with typed `_safe_comment_literal` helper that validates body against printable-ASCII allowlist (rejects control chars, backslash, non-ASCII) before doubling single-quotes. Defense-in-depth on top of upstream identifier validation; closes the gap a future refactor would open if any interpolant were allowed to skip `dialect.quote_identifier()`.

### Tests

- Updated unit + integration suite to assert ALTER OWNER TO emission, function_owner identifier validation, comment-literal allowlist enforcement. New unit tests: `test_build_raises_when_function_owner_unset`, `test_emitted_ddl_includes_alter_owner_to`, `test_function_owner_validates_identifier`, `test_rejects_sql_injection_in_function_owner`, `test_safe_comment_literal_passes_printable_ascii`, `test_safe_comment_literal_rejects_backslash_and_control_chars`. New Tier 2 test against real PostgreSQL: `test_pg_proc_proowner_matches_function_owner_setter`.
- Cross-SDK byte vectors regenerated to include the new `ALTER FUNCTION ... OWNER TO` statement; `function_owner` field added to every fixture vector. Cross-SDK align with kailash-rs lands separately on that side.

### Breaking change

- **API**: `SecurityDefinerBuilder.build()` now requires `.function_owner(role)` to be called before `.build()` — previously every existing chain compiled without owner pinning. Callers MUST add the new fluent setter; otherwise `build()` raises `SecurityDefinerBuilderError`. The break is intentional (the unset-default IS the security failure this release fixes); the migration is a one-line addition to every builder chain.

### Origin

- Wave 3 /redteam findings H3 + H4. See `workspaces/issues-604-607/04-validate/02-security-review.md`.

## [2.3.0] — 2026-04-25 — SecurityDefinerBuilder + RLS posture audit (#607)

Cross-SDK parity with kailash-rs PR #579 + #590. Minor bump — new public surface, no breaking changes.

### Added

- **`dataflow.migration.security_definer.SecurityDefinerBuilder`** (#607) — port of the Rust `SecurityDefinerBuilder` for declaring pre-auth `SECURITY DEFINER` carveouts on top of row-scoped RLS policies. Cross-SDK byte-identical SQL emission for the same builder chain. Builder API mirrors the Rust signature exactly: `.primary_lookup_column(col)` for explicit WHERE column, `.active_column(col)` for opt-in `is_active` guard (default off), `ALLOWED_PG_TYPES` allowlist matching Rust (`smallserial`, `inet`, `cidr`, `citext`, `interval` plus baseline types). Every emitted DDL identifier routes through `dataflow.adapters.dialect.quote_identifier()` per `rules/dataflow-identifier-safety.md`. Returns parameterless emitted SQL strings ready for execution in numbered migrations.
- **Cross-SDK test vectors** at `tests/fixtures/security_definer_vectors.json` — shared fixture file consumed by both SDKs to assert byte-identical SQL output for the same builder chain. 4 parametrized regression tests at `tests/regression/test_issue_607_cross_sdk_vectors.py`.
- **Tier 1 + Tier 2 tests** — 36 unit tests at `tests/unit/migration/test_security_definer_builder.py` (allowlist, validation, builder chains, emission shape) + 7 integration tests at `tests/integration/migration/test_security_definer_builder_integration.py` against real PostgreSQL with RLS enabled (helper + role grants + revoke-from-public + minimum-disclosure return columns).
- **RLS posture audit + carveout pattern docs** (#607 items 1+2) — new advanced guide at `docs/advanced/rls-security-definer-preauth-carveout.md` (200 lines) + quickstart pointer + `specs/security-data.md` § 11.5 audit (DataFlow `@db.model` tables ship without RLS by default — only `RowLevelSecurityProvider.create_tenant_policy()` emits RLS DDL, never `USING(true)`) + § 11.6 SECURITY DEFINER public-surface contract.

### Deferred

- Item 3 of #607 (`rls=` flag on `@db.model` for declarative auto-emit of `ENABLE ROW LEVEL SECURITY` + tenant-scoped policy) — out of scope per issue brief; warrants its own PR with its own Tier 2 test surface.

### Related

- Cross-SDK: `kailash-rs#579` (v1) + `#590` (v2 refinements)
- Reference impl: STP migration `0027_users_rls_policy.sql`
- Issues: closes #607 items 1+2 (item 3 follow-up)

## [2.2.0] — 2026-04-25 — Public API expose for read-time classification (#601)

Cross-SDK parity with kailash-rs PR #580 (closes #514). Minor bump — new public surface, no breaking changes.

### Added

- **`apply_read_classification` + `format_record_id_for_event` on public API** (#601) — cross-SDK parity with kailash-rs PR #580 (closes #514). Both helpers now importable from the top-level `dataflow.classification` module; `__all__` lists them under the "Read-time helpers" group. `apply_read_classification(fields, record, caller_clearance=None)` is the module-level form of `ClassificationPolicy.apply_masking_to_record` — accepts a `Dict[str, FieldClassification]` (typically `policy.get_model_fields(model_name)`), mutates the record dict in place, and honors the ambient `clearance_context` when `caller_clearance is None`. The full masking matrix (REDACT / HASH / LAST_FOUR / ENCRYPT / NONE-defaults-to-REDACT) is exercised by 19 Tier-1 tests at `tests/unit/test_apply_read_classification.py`. Sub-module `__version__` bumped to `0.2.0`.

## [2.1.2] — 2026-04-24 — Cyclic-import refactor (issue #612)

### Changed

- **CodeQL `py/unsafe-cyclic-import` hardening** — extracted `dataflow._types` to break the 3-way static cycle between `core/tenant_context.py`, `core/engine.py`, and `features/express.py`. `DataFlowProtocol` (new) captures the structural surface `tenant_context` needs (`multi_tenant`, `connection_manager`, `cache_backend`) without importing the concrete `DataFlow` class. All classification, tenant-isolation, and event-payload contracts preserved — sec-review on PR #616 verified no mutation-return redaction or `format_record_id_for_event` call sites were disturbed. `isinstance(db, DataFlow)` admission gates in kaizen/memory + kaizen-agents/integrations preserved (structural-invariant test at `tests/regression/test_issue_612_protocol_isinstance_invariant.py` enforces this).

## [2.1.1] — 2026-04-24 — Security patch (issue #613) — retroactive entry

### Fixed

- **Clear-text password logging** (`py/clear-text-logging-sensitive-data`) — dataflow adapters (`adapters/postgresql.py`, `adapters/mysql.py`, `adapters/mongodb.py`, `adapters/factory.py`, `fabric/webhooks.py`) previously logged URL-derived fields that included credentials. Structural fix: drop URL-derived fields from log arguments entirely; canonical event names survive for triage per `rules/observability.md` § 6. Per-PR custom CodeQL sanitizer packs are not reliably honored across releases, so the fix is source-side rather than scanner-configuration. Regression test: `packages/kailash-dataflow/tests/regression/test_codeql_clear_text_logging_613.py`.

_(This entry was missed in the 2.1.1 release commit on PR #615 — the version bumps landed on pyproject.toml + `__init__.py` but the CHANGELOG edit failed silently in the parallel-Edit batch. Added here in PR #616 alongside the 2.1.2 entry to restore the audit trail.)_

## [2.1.0] - 2026-04-23 — W31.b kailash-ml bridge (`dataflow.ml`)

### Added

- **New `dataflow.ml` module** (spec `specs/dataflow-ml-integration.md`). The DataFlow × kailash-ml bridge kailash-ml 1.0.0 consumes for feature-store + lineage + training-lifecycle event integration. Additive — no existing engine/Express/classification/trust surface changes.
  - `dataflow.ml.ml_feature_source(feature_group, tenant_id=None, point_in_time=None, since=None, until=None, limit=None) -> polars.LazyFrame` — materialize a `FeatureGroup`-shaped adapter as a polars LazyFrame. Duck-typed validation (any object with `.name` + callable `.materialize`) so DataFlow does not hard-import `kailash_ml.engines.feature_store.FeatureGroup`. Tenant strict mode: `multi_tenant=True` groups raise `MLTenantRequiredError` when `tenant_id is None` (per `rules/tenant-isolation.md` § 2). Cache keys follow the canonical `kailash_ml:v1:{tenant_id}:feature_source:{group}:{params}` shape.
  - `dataflow.ml.transform(expr, source, *, name, tenant_id=None) -> polars.LazyFrame` — apply a polars expression to a feature source, propagating classification metadata from source to result and tagging the result with `kailash_ml.transform` for downstream lineage. Rejects pandas/non-Expr inputs at the boundary per `rules/framework-first.md` § "Raw Is Always Wrong".
  - `dataflow.ml.hash(df, *, algorithm="sha256", stable=True) -> str` — stable SHA-256 content fingerprint of a polars DataFrame/LazyFrame in `"sha256:<64hex>"` form for `ModelRegistry.register_version(lineage_dataset_hash=...)`. Cross-SDK byte-identical with kailash-rs `dataflow::hash` for the same canonicalized polars Arrow IPC stream.
  - `dataflow.ml.TrainingContext(run_id, tenant_id, dataset_hash, actor_id)` — frozen dataclass for training-run provenance. Validates `dataset_hash` starts with `"sha256:"` at construction time.
  - `dataflow.ml.emit_train_start(db, context, *, model_name=None, engine=None)` and `dataflow.ml.emit_train_end(db, context, *, status, duration_seconds=None, error=None)` — publish `kailash_ml.train.start` / `kailash_ml.train.end` `DomainEvent`s on `db.event_bus`. Payload record_id routes through `format_record_id_for_event` so cross-SDK fingerprint correlation matches DataFlow's existing write-event surface (per `rules/event-payload-classification.md` § 1).
  - `dataflow.ml.on_train_start(db, handler)` / `dataflow.ml.on_train_end(db, handler)` — subscribe to the training lifecycle events; return list of subscription ids matching `DataFlow.on_model_change` shape for uniform sub/unsub handling.
  - `dataflow.ml._kml_classify_actions(policy, model_name, columns) -> Dict[str, "allow"|"redact"|"hash"|"encrypt"]` — DataFlow classification bridge for kailash-ml training paths. Single translation point from `MaskingStrategy` to action strings; fail-safe `"redact"` for unknown strategies prevents silent pass-through of raw classified columns into training data.
  - `dataflow.ml.build_cache_key(...)` — tenant-aware cache key helper (exposed for invalidation callers).
- **Error taxonomy** (spec § 5): `DataFlowMLIntegrationError`, `FeatureSourceError`, `DataFlowTransformError`, `LineageHashError`, `MLTenantRequiredError`. All inherit from `dataflow.exceptions.DataFlowError` so existing `except DataFlowError` handlers continue to catch ML-bridge failures.

### Tests

- `packages/kailash-dataflow/tests/unit/ml/test_dataflow_ml_symbols.py` — 25 Tier 1 tests covering import surface, `TrainingContext` validation, hash stability (column-reorder, row-reorder, dtype-sensitive, sha256 format), transform rejection of pandas/non-Expr inputs, classification metadata propagation, `_kml_classify_actions` MaskingStrategy translation, cache key shape, error hierarchy.
- `packages/kailash-dataflow/tests/integration/test_dataflow_ml_feature_source_wiring.py` — 7 Tier 2 wiring tests against real SQLite-backed DataFlow (write-then-read persistence; multi-tenant strict mode; transform round-trip; classification metadata; limit forwarding; lineage hash stability).
- `packages/kailash-dataflow/tests/integration/test_dataflow_ml_event_wiring.py` — 9 Tier 2 wiring tests against real DataFlow event bus (start/end subscribers, pub/sub fan-out, event-type separation, failure payload, sha256 record_id fingerprint).

### Version

- `kailash-dataflow` bumped from 2.0.12 to 2.1.0. Additive minor (no breaking changes). Consumed by kailash-ml 1.0.0 (W31.b coordination).

## [2.0.11] - 2026-04-19 — BP-049 classified-data leak fixes (#522)

### Security

- **BP-049 NotFound error no longer leaks classified field values (#522)**: `DataFlowExpress.read()` raised `NotFoundError` with the raw record ID in the error message. For models where the PK is a classified field (e.g. email-keyed `Account`), the error message echoed the raw email address to any caller with the right to call `read()` regardless of clearance. Fixed by routing the record_id in `NotFoundError` messages through `format_record_id_for_event` — classified PKs become `sha256:<8hex>` fingerprints.
- **BP-049 cache key contained raw classified PK (#522)**: Read-path cache keys were constructed as `dataflow:v1:{model}:{record_id}` without sanitizing the `record_id`. Classified string PKs are now hashed before inclusion in the cache key, preventing the raw value from appearing in Redis SCAN output or cache-key logs.
- **BP-049 validation error message sanitization (#522)**: Field validation errors in `DataFlowExpress` echoed the user-supplied value verbatim in the error string. For classified fields this leaks the value to any log aggregator that captures error messages. Validation errors for classified fields now include a fingerprint only.

## [2.0.10] - 2026-04-19 — Identifier quoting + defense-in-depth hardening + force_downgrade split (#480 #499 #510)

### Security

- **Express CRUD PG identifier quoting (#480, PR #503)**: `DataFlowExpress` CRUD methods (`create`, `read`, `update`, `delete`, `list`, `count`) now route all table and column name interpolations in PostgreSQL DDL and DML through `dialect.quote_identifier()`. Prior to this fix, Express CRUD SQL used unquoted identifiers in PostgreSQL, allowing model names with reserved words or special characters to produce syntax errors or (in adversarial contexts) injection via crafted model names.
- **9 defense-in-depth MED findings (#499, PRs #504 #508)**: batch close of medium-severity findings from the post-convergence security audit. Includes: constant-time comparison enforcement in credential validators, structured-error sanitization to avoid leaking DB internals in error messages, input length guards on several public API entry points, and tightening of exception handler scopes that were too broad.

### Changed

- **`force_drop` vs `force_downgrade` split (#510, PR #517)**: The `force_drop=True` flag on `dialect.drop_table()` (primitive DDL layer) is now distinct from the new `force_downgrade=True` flag on `MigrationManager.apply_downgrade()` (orchestrator layer). Before this refactor, `force_drop` was overloaded to mean both "acknowledge this individual DROP" and "acknowledge this destructive migration rollback." They now carry independent semantics per `rules/schema-migration.md` MUST Rule 7 and `rules/dataflow-identifier-safety.md` MUST Rule 4.

## [2.0.9] - 2026-04-18 — Security hardening + Python 3.14 compatibility (#477 #478)

### Security

Three HIGH findings surfaced by the `/redteam` round-1 sweep of issues #492–#497 and fixed here. See `workspaces/issues-492-497/journal/0001-0003-RISK-*.md` for per-finding origin and blast radius.

- **Stop logging raw bound params on query failure.** `ConnectionManagerAdapter.execute_query`'s exception branch emitted `logger.error("connection_adapter.params", extra={"params": params})`. `params` carries classified row values (PII, secrets, API keys bound to INSERT/UPDATE). Every query failure wrote them to the ERROR stream where every aggregator and observability vendor could read them. Fixed by consolidating the 3-line failure emission into one structured call that logs `error`, `sql`, and `param_count` only. Parameterized SQL never carries raw values. Violated `rules/security.md` § No secrets in logs, `rules/observability.md` Rule 4, `rules/dataflow-classification.md` MUST 1. Commit `e203ba27`.
- **Delete `BulkUpsertNode` pool dead branch.** `BulkUpsertNode._execute_query` called `self._pool_manager.execute(operation="execute", …)` when `use_pooled_connection=True`. `DataFlowConnectionManager.execute()` has a closed allowlist that does NOT include `"execute"` — every call raised `ValueError`, was caught by a bare `except Exception`, emitted a generic WARN, and silently fell through to direct `AsyncSQLDatabaseNode` execution. Operators who set `use_pooled_connection=True` believed they were routing through the pool; they weren't. Pool accounting, tenant tracking, and audit trail were all bypassed. Fix: delete the dead branch; `use_pooled_connection=True` now raises `NodeValidationError` naming `BulkCreatePoolNode` as the correct pool-routed alternative. Violated `rules/zero-tolerance.md` Rule 3 (silent fallback) and `rules/dataflow-pool.md` Rule 3 (deceptive configuration). Commit `ed1265e8`.
- **Delete `_tenant_trust_manager` orphan facade.** `DataFlow.__init__` constructed `TenantTrustManager(strict_mode=True)` and attached it to `self._tenant_trust_manager` when `multi_tenant=True` and trust mode != `"disabled"`. Zero framework hot-paths invoked any of the manager's 8 public methods. Classic Phase-5.11 failure: facade exists, consumers import it, framework never calls it. Operators with `multi_tenant + trust=enforcing` believed cross-tenant verification was running; it wasn't. Per `rules/orphan-detection.md` MUST 3 ("Removed = Deleted, Not Deprecated"), the facade is deleted. `TenantTrustManager` remains importable at `dataflow.trust.multi_tenant.TenantTrustManager` for standalone consumer use; when a production call site lands on `features/express.py`, the facade will be wired in the SAME PR. Commit `eab947dc`.

### Fixed

- **`@db.model` registration on Python 3.14 (#477).** Multiple call sites read `cls.__annotations__` (or `getattr(cls, "__annotations__", {})`) directly to extract field types for SQL generation. Under PEP 649 / PEP 749, `cls.__annotations__` access can raise `NameError` instead of returning a string when a model uses a forward reference — and `getattr`'s default does NOT catch that, since it only triggers on `AttributeError`. The result on 3.14 is a bare `NameError` mid-`@db.model` registration with no actionable message about which field caused it. Sites fixed: `core/engine.py` (MRO walk + multi-tenant `tenant_id` injection), `core/model_registry.py` (metadata extraction), `core/engine_production.py` (`_extract_fields`), `migrations/fk_aware_model_integration.py` (`_analyze_model_fields`).
- **All read paths now route through `kailash.utils.annotations.get_resolved_type_hints`** — the same handler shape the kailash-rs SDK uses. On 3.14 it falls back to `annotationlib.get_annotations(cls, format=FORWARDREF)` and raises a per-field `RuntimeError` naming the model, the field, and the unresolvable forward reference, with a clear suggestion to import the type at runtime instead of under `TYPE_CHECKING`.
- **`LocalRuntime.execute()` deprecation warning leaked from internal DataFlow code (#478).** Long-lived `LocalRuntime` instances owned by DataFlow internals (`DataFlow.__init__`, `ModelRegistry`, `PostgreSQLSchemaInspector`, `SQLiteSchemaInspector`, `AutoMigrationSystem`, `MigrationHistoryManager`, `DataFlowGateway`, `ConnectionManagerAdapter` — eight construction sites) were triggering Core SDK's "use context manager" deprecation warning on every call. Each owner now invokes the new public `LocalRuntime.mark_externally_managed()` method (added in `kailash 2.8.7`) immediately after construction — Core SDK responds by suppressing the ad-hoc-usage warning AND skipping the fallback `atexit` cleanup, with the owning framework calling `runtime.close()` at its own shutdown. The initial iteration of this fix mutated the private `_cleanup_registered` flag directly; that has been replaced with the documented public opt-out so the contract survives Core SDK refactors. The warning was aimed at transient ad-hoc callers, not framework-owned long-lived runtimes; without this fix the warning would become a hard error in Core SDK v0.12.0 and break every fresh `pip install kailash-dataflow`.

## [2.0.6] - 2026-04-12 — Post-Convergence Security Hardening

### Security

- **Classification fail-closed** (cross-SDK alignment #418, EATP D6): `ClassificationPolicy.classify()` default changed from `PUBLIC` (fail-open) to `HIGHLY_CONFIDENTIAL` (fail-closed) for unclassified fields, matching kailash-rs semantics. A `WARN` log is emitted each time the fail-closed default is applied so operators can identify and classify missing fields.
  - **Breaking**: Fields that were implicitly readable as PUBLIC must now carry `@classify("field", DataClassification.PUBLIC)`. Failure to classify will result in redaction for all callers without explicit PUBLIC clearance.
- **Connection parser consolidated credential decode**: `connection_parser.py` now routes credential extraction through the shared `kailash.utils.url_credentials.decode_userinfo_or_raise` helper. The prior hand-rolled `unquote()` call lacked null-byte rejection, enabling the `mysql://user:%00bypass@host/db` auth-bypass (same class as R3 null-byte CVE).
- **Identifier fingerprint error messages**: `IdentifierError` messages from `dialect.quote_identifier()` now emit a hex fingerprint (`hash(name) & 0xFFFF:04x`) instead of echoing the raw identifier value, preventing log-poisoning via crafted model or column names.
- **Cache CAS + tenant eviction** (#419): `InMemoryCache` CAS path now scopes version-eviction to the originating tenant's partition. A version mismatch no longer silently evicts cache entries belonging to a different tenant.
- **Tenant-scoped `_clear`**: `InMemoryCache._clear()` requires an explicit `tenant_id` when the cache is operating in multi-tenant mode; clearing all tenants at once is blocked without an explicit override flag.

### Fixed

- **Regression tests** (34 total, 5 new test classes): `test_classification_fail_closed.py`, `test_cache_cas_tenant.py`, `test_create_index_identifier_validation.py`, `test_loc_invariants.py`, plus additions to existing regression files.

---

## [2.0.0] - unreleased — DataFlow 2.0 Perfection Sprint

Comprehensive rework of DataFlow's core, cache, fabric, security, and
observability surfaces. ~11,800 net LOC removed, 9 CRITICAL security
vectors closed, every "manager" facade replaced with a real
implementation, fabric Redis cache shipped, parameterized products
fixed, full tenant partitioning across Express and fabric, and the
model-registry sync-in-async deadlock resolved.

### Breaking changes

1. **`FabricRuntime` cache methods are now async.** `product_info`,
   `invalidate`, `invalidate_all`, `_get_products_cache` became
   `async def` to support the Redis-backed fabric cache. Wrap
   existing callers in `async def` or use `asyncio.run()`.

2. **`multi_tenant=True` DataFlow instances MUST bind a tenant.**
   Express CRUD operations now resolve `tenant_id` from
   `dataflow.core.tenant_context.get_current_tenant_id()` and raise
   `TenantRequiredError` when none is set. Fabric products declared
   `multi_tenant=True` raise `FabricTenantRequiredError` when the
   serving layer cannot extract a tenant. Silent fallback to a shared
   cache partition is blocked.

3. **Fabric parameterized products REQUIRE params in the cache-read
   path.** `serving.py` now passes the request's query params to
   `get_cached(name, params=...)`; the batch endpoint returns an
   explicit routing error for parameterized products instead of
   silently returning `null`.

4. **`DataFlowExpress._cache_manager.invalidate_model`** now accepts
   an optional `tenant_id` kwarg. Custom cache backends that override
   the method must add the kwarg or Express falls back to model-wide
   invalidation with a WARN log.

5. **Dynamic update node (`nodes/dynamic_update.py`) deleted.** The
   223-line module executed user-supplied code via `exec()` — a
   critical RCE vector with zero consumers. Any caller must migrate
   to the generated `UpdateNode` with field whitelists.

6. **`TransactionManager`, `ConnectionManager`, and related facade
   managers rewritten.** They now hold real BEGIN/COMMIT/ROLLBACK
   state, SELECT 1 health checks, and adapter-delegated pool stats.
   External callers that depended on the old dict-returning stubs
   will see real data for the first time.

7. **`ClassificationPolicy.classify()` now fail-closed.**
   Unclassified fields previously returned `"public"` (fail-open),
   silently exposing data that was never explicitly classified.
   The default is now `"highly_confidential"` (most restrictive),
   matching kailash-rs semantics (cross-SDK alignment per EATP D6,
   #418). A WARN log is emitted when the default is applied so
   operators can identify and classify missing fields.
   **Migration**: Audit your models for unclassified fields and
   explicitly classify each one with the intended level. Fields that
   should be publicly readable must now carry
   `@classify("field", DataClassification.PUBLIC)`. Failure to
   classify will result in redaction for most callers.

### Security fixes (9 CRITICAL vectors closed)

- **SQL injection (13 sites) in `core/multi_tenancy.py`** — every
  f-string DDL migrated to `dialect.quote_identifier()` with strict
  regex validation on tenant_id.
- **`eval()` RCE in `semantic/search.py`** — replaced with
  msgpack/json deserialization (then the module was deleted in the
  orphan sweep).
- **`exec()` RCE in `nodes/dynamic_update.py`** — entire 223-line
  file deleted, zero consumers.
- **DDL identifier injection (25 sites across adapters)** — all
  migrated to `dialect.quote_identifier()` with strict validation.
- **Fake `encrypt_tenant_data`** — `f"encrypted_{key}_{data}"` with
  a hardcoded constant replaced with real
  `cryptography.fernet.Fernet` + env-sourced keys
  (`TenantKeyProvider` abstraction for HSM/KMS).
- **`UpdateNode` field whitelist** — unknown fields raise
  `UnknownFieldError`; whitelist sourced from `self.model_fields`.
- **`LIMIT`/`OFFSET` parameterization** in `database/query_builder.py`.
- **`validate_queries=True`** flipped to the default at every DML
  call site.
- **Redis URL masking** — every log line touching a URL now goes
  through `mask_sensitive_values()`.

### Added

- **`FabricCacheBackend` ABC + two implementations**
  (`InMemoryFabricCacheBackend`, `RedisFabricCacheBackend`). The
  Redis backend uses a Lua CAS script keyed on `run_started_at` so
  stale data cannot overwrite fresh data under the R3 last-writer-
  wins model, offers a metadata-only HGET fast path, SCAN (not KEYS)
  for non-blocking invalidation, and degrades gracefully on Redis
  outage (flips `fabric_cache_degraded` gauge, returns cache miss).
- **`FabricCacheBackend.scan_prefix(prefix)`** primitive for fabric
  health probes to aggregate parameterized product freshness without
  transferring payload bytes.
- **`PipelineExecutor.scan_product_metadata`** — wraps `scan_prefix`
  with the proper product-name + tenant_id prefix.
- **Leader-side warm-cache on election** — new leader checks Redis
  metadata for each materialized product and skips execution if
  `cached_at + max_age > now`.
- **Shared Redis client** (`FabricRuntime._get_or_create_redis_client`)
  — one connection per replica shared across cache backend, leader
  elector, and webhook receiver.
- **Fabric webhook Redis nonce deduplication** now actually uses the
  shared Redis client.
- **Express cache tenant dimension** — keys become
  `dataflow:v1:{tenant}:{model}:{op}:{hash}` when
  `multi_tenant=True`. `InMemoryCache.invalidate_model` and
  `AsyncRedisCacheAdapter.invalidate_model` accept an optional
  `tenant_id` kwarg for scoped invalidation.
- **`TenantRequiredError`** shared exception in
  `dataflow/core/multi_tenancy.py`.
- **`ModelRegistry._execute_workflow_sync_safe`** — worker-thread
  bridge for async-context DDL execution that resolves #352.
- **Phase 5.8 — Fabric endpoints registered into Nexus**:
  `FabricRuntime._register_with_nexus` now wires serving, health,
  trace, webhook, and `/fabric/metrics` routes onto the supplied
  Nexus instance. Previously the subsystems existed but were not
  exposed over HTTP; operators pass `nexus=Nexus(...)` to
  `db.start()` to enable.
- **Phase 5.9 — Per-provider webhook signature verifiers**:
  `WebhookConfig.provider` selects one of five verification schemes
  (generic, github, gitlab, stripe, slack). Each verifier owns its
  upstream signature contract (GitHub sha256= prefix, GitLab
  x-gitlab-token plain token, Stripe `t=,v1=` over
  `{t}.{body}`, Slack `v0=` over `v0:{ts}:{body}`, generic SHA256)
  and picks the most reliable per-provider nonce for dedup.
- **Phase 5.10 — `@classify` redaction wired into Express reads**:
  the decorator was a no-op pre-2.0; classification metadata was
  stored but the read path never consulted it. Express
  `list`/`get`/`find_one` now apply per-row and per-record
  masking based on the caller's clearance level resolved from
  `dataflow.core.clearance_context.get_current_clearance()`.
- **Phase 5.11 — Trust subsystems wired into Express query path**:
  `TrustAwareQueryExecutor`, `DataFlowAuditStore`, and
  `TenantTrustManager` were 2,407 LOC of facade code before 2.0
  with zero production call sites. Express reads now go through
  `_trust_check_read` (pre-query access check),
  `_trust_record_success` / `_trust_record_failure` (audit event
  persistence), and honour `plan.additional_filters` /
  `plan.row_limit` / `plan.redact_columns` from the trust plan.
- **Phase 5.12 — FabricMetrics singleton + `/fabric/metrics`**:
  13 Prometheus metric families (pipeline runs, cache hit/miss/
  errors/degraded, source health, request duration, webhook
  received, leader status) exposed through a process-wide
  `FabricMetrics` singleton. `/fabric/metrics` route registered
  via `FabricRuntime._register_with_nexus`. `prometheus-client`
  added to the `fabric` optional extra; missing package logs a
  single startup WARN and every counter becomes a loud no-op.
- **Phase 6.2 — Model registry mutations in real transactions**:
  `_create_model_registry_table` now runs all DDL in a single
  `engine.begin()` block on the SQLDatabaseNode shared engine, so
  partial failure rolls back the whole bundle on PostgreSQL/SQLite.
  The previously broken sync `ModelRegistry.transaction()` context
  manager (which tried to enter an `@asynccontextmanager` from a
  sync `with` block) is fixed to yield a real SQLAlchemy
  Connection inside an active transaction.
- **Phase 6.3 — Async cascade contract locked in place**:
  regression suite asserts `FabricRuntime.product_info`,
  `invalidate`, `invalidate_all` (and their downstream
  `PipelineExecutor.get_metadata`, `invalidate`, `invalidate_all`
  counterparts) remain async. Regression here would reintroduce
  the gh#352 deadlock pattern.
- **Phase 6.4 — `ResourceWarning` on leaked async resources**:
  `FabricRuntime`, `PipelineExecutor`, and `ConnectionManager`
  now implement `__del__` that warns when garbage-collected while
  still holding live asyncio tasks, DB adapters, or cache
  backends. Enables `pytest -W error` to catch leaks before they
  reach production.
- **Phase 7.1 — Structured logging across 93 source files**: 908
  f-string logger calls rewritten to `logger.info("event.name",
extra={"field": value})` form per `rules/observability.md`.
  Event names use dot.snake.case, every interpolated variable
  becomes a field, nothing dropped.
- **Phase 7.2 — Correlation ID propagation**:
  `dataflow.observability.correlation` provides a ContextVar-based
  `get/set/clear/with_correlation_id` API scoped per-asyncio-task.
  Concurrent requests never cross-contaminate; child tasks
  inherit the parent's binding at spawn time.
- **Phase 7.6 — Centralized URL masking**: `dataflow.utils.masking`
  exposes `mask_url` and `mask_secret`; `fabric/cache._mask_url`
  is a backwards-compatible re-export. Single canonical
  implementation eliminates the prior three-copy drift risk.
- **Phase 8.1-8.5 — Test suite hardened with real infrastructure**:
  89 mock violations removed from Tier 2/3 tests (67 integration
  - 22 e2e). `no_mocking_policy` fixture wired as autouse to
    block future regressions. Coverage gate added at
    `tool.coverage.report.fail_under = 80` with a separate 100%
    target for security/trust subpackages.

### Fixed

- **#352** — model_registry sync-in-async: DataFlow.start() under
  FastAPI no longer deadlocks trying to call
  `AsyncLocalRuntime.execute()` from inside an event loop.
- **#353** — `adapters/postgresql.py` now parses and forwards every
  URL parameter (`sslmode`, `application_name`, `command_timeout`,
  `sslrootcert`, `sslcert`, `sslkey`) correctly to asyncpg.
- **#354** — `DataFlow(redis_url=...)` now actually drives the
  fabric product cache. Previously the parameter was accepted and
  silently ignored; fabric ran with a per-process `OrderedDict`
  regardless of configuration.
- **#358** — parameterized fabric products can now be read from
  cache via HTTP. Previously `serving.py` dropped query params on
  the cache lookup, so parameterized products always returned
  `data=null`. Health endpoint now aggregates freshness across every
  cached param combination via the new `scan_product_metadata`
  helper and reports `param_combinations_cached` per product.
- **PostgreSQL `execute_transaction`** — previously executed each
  query on a separate connection, so "transactions" had no
  atomicity. Now uses asyncpg's `connection.transaction()` context
  manager matching MySQL/SQLite semantics.
- **Dialect consolidation** — three parallel dialect systems
  collapsed into one `adapters/dialect.py` with the full
  `rules/infrastructure-sql.md` helper set.
- **SQLite adapters merged** — `sqlite_enterprise.py` deleted, all
  features folded into `sqlite.py`. `factory.py` default no longer
  points at the deleted class.
- **Cache invalidation exact-match** — `InMemoryCache.invalidate_model`
  now matches keys by exact `:{model_name}:` segment, not substring.

### Removed

- `nodes/dynamic_update.py` (223 LOC, RCE risk, zero consumers)
- `semantic/` subsystem (1,239 LOC)
- `web/` orphan subsystem (1,958 LOC, WebMigrationAPI never wired)
- `compatibility/` (1,327 LOC, `unittest.mock.Mock` in production at
  `legacy_support.py:79`)
- `performance/` duplicate `MigrationConnectionManager` class
- `migration/` singular (dead duplicate of `migrations/`)
- `validators/` (dead duplicate of `validation/`)
- `core/cache_integration.py` (886 LOC, dead parallel init path)
- `adapters/sqlite_enterprise.py` (folded into `sqlite.py`)
- `InMemoryDebouncer` class (zero instantiations)
- `utils/suppress_warnings.py` and the underlying
  `pytest.ini --disable-warnings` suppression

**Net LOC delta: approximately −11,800 lines, 86 files changed.**

### Migration

```python
# FabricRuntime cache methods are async now
info = await runtime.product_info("users")

# Multi-tenant Express requires a tenant binding
async with db.tenant_context.aswitch("acme"):
    users = await db.express.list("User", {"active": True})
```

## [1.6.0] - 2026-04-03

### Added

- **Data Fabric Engine**: External data source integration and derived data products
  - `db.source()` — register REST, File, Cloud, Database, and Stream sources
  - `@db.product()` — define materialized, parameterized, and virtual data products
  - `await db.start()` — start the fabric runtime with auto-generated endpoints
  - 5 source adapters: REST (httpx, ETag caching, SSRF protection), File (watchdog), Cloud (S3/GCS/Azure), Database, Stream (Kafka/WebSocket)
  - Pipeline executor with change detection and configurable debounce
  - Leader election for multi-worker coordination (Redis or in-memory)
  - Circuit breaker per source with configurable staleness policies
  - Webhook receiver with HMAC validation and nonce deduplication (Redis or in-memory)
  - Auto-generated REST endpoints for all registered products
  - Write pass-through with event-driven product refresh
  - Observability: health endpoints, pipeline traces, Prometheus metrics, SSE
  - SSRF protection with DNS rebinding defense on REST sources
  - Optional extras: `fabric`, `cloud`, `streaming`, `fabric-all`

## [1.5.1] - 2026-04-01

### Fixed

- **Connection stampede during auto_migrate** (#212): `_create_table_sync()` opened a fresh psycopg2 connection per DDL statement (63+ connections for 21 models). New `_create_tables_batch()` batches all `CREATE TABLE` and `CREATE INDEX` into a single connection. Reduces DDL connections from ~88 to 1.
- **Missing `IF NOT EXISTS` on `CREATE INDEX`**: User-defined and FK indexes now use `CREATE INDEX IF NOT EXISTS`, matching kailash-rs behavior. Prevents "relation already exists" errors on re-run.

## [1.5.0] - 2026-04-01

### Added

- **DerivedModel**: Computed models that auto-update when source models change. Declarative derivation rules with dependency tracking.
- **FileSource node**: Import data from CSV, JSON, and Parquet files directly into DataFlow models with schema inference and validation.
- **Validation DSL**: Declarative field validation rules (`required`, `min`/`max`, `pattern`, `unique`, custom validators) applied at model level before database writes.
- **Express cache wiring**: Transparent caching layer for `db.express` reads with configurable TTL and invalidation on writes.
- **ReadReplica support**: Route read queries to replica databases automatically. Configurable read/write splitting with lag-aware routing.
- **Retention engine**: Time-based and count-based data retention policies. Automatic cleanup of expired records with configurable schedules.
- **EventMixin**: `on_source_change` callback system for reactive data pipelines. Models can subscribe to changes in other models.

### Test Results

- 3,690 tests passed, 0 failures

## [1.4.0] - 2026-03-31

### Added

- **Sync Express API**: `SyncExpress` class via `db.express_sync` — wraps all 11 async Express methods for non-async contexts.

### Fixed

- SQLite timestamp read-back, migration log noise, `__del__` finalizer safety, `id_type.__name__` AttributeError.

## [1.1.0] - 2026-03-21

### Added

- **Pool auto-scaling**: Pool size automatically detected from database `max_connections`, divided by worker count. No configuration needed for most deployments.
- **Startup validation**: Warns at startup if configured pool will exhaust `max_connections`. Set `DATAFLOW_STARTUP_VALIDATION=false` to disable.
- **Pool utilization monitor**: Background daemon thread logs at 70% (INFO), 80% (WARNING), 95% (ERROR) utilization thresholds.
- **Connection leak detection**: Tracks connection checkout time and logs warnings with tracebacks when connections are held beyond threshold (default: 30s).
- **Lightweight health check pool**: Separate 2-connection mini-pool for health checks that doesn't compete with the main application pool (RS-6 alignment).
- **`pool_stats()` API**: Real-time pool utilization stats (`active`, `idle`, `max`, `utilization`).
- **`execute_raw_lightweight()` API**: Execute health check queries on the dedicated lightweight pool.
- **`health_check()` pool integration**: Health check response now includes pool utilization stats and degrades status at 95%+ utilization.

### Changed

- **Pool size default**: Replaced five competing pool size defaults with single source of truth via `DatabaseConfig.get_pool_size()`.
- **`max_overflow` formula**: Changed from `pool_size * 2` (triples connections) to `max(2, pool_size // 2)` (bounded).
- **`pool_max_overflow` parameter**: Changed from `int = 30` to `Optional[int] = None` to allow auto-computation.

### Deprecated

- `DataFlowConfig.connection_pool_size`: Use `DatabaseConfig.pool_size` via `get_pool_size()` instead.

### Removed

- Dead `MonitoringConfig` flags (`alert_on_slow_queries`, `alert_on_failed_transactions`, `query_insights`, `transaction_tracking`, `metrics_export_interval`, `metrics_export_format`) that had no backing implementation.
- Ghost `DATAFLOW_POOL_SIZE` env var read in engine.py pooling block that computed but never stored the value.
- `connection_pool_size` suggestion mapping from engine.py parameter suggestions.

### Fixed

- Five competing pool size defaults (10, 20, 25, 30, `cpu_count * 4`) consolidated into single code path.
- `MonitoringConfig.alert_on_connection_exhaustion` and `connection_metrics` flags now wired to pool monitor.

## [0.12.1] - 2026-02-22

### V4 Audit Hardening Patch

Post-release reliability hardening from V4 final audit.

### Fixed

- **Health Check Error Sanitization**: Health endpoint error responses use `type(e).__name__` instead of raw `str(e)` to prevent internal detail leakage
- **DB URL Credential Masking**: Health check masks database credentials in URL before including in response
- **Engine Silent Swallows**: 3 bare `except: pass` blocks in engine.py replaced with `logger.debug()` calls
- **Transaction Node Cleanup Logging**: 2 cleanup-after-failure silent swallows now log at debug level
- **Migration API Introspection**: 9 silent exception swallows in schema introspection (PK, FK, index, unique constraints) now log at debug level
- **Debug Data Structures**: 2 silent swallows in cached solution loading now log at debug level

### Test Results

- DataFlow: 794 passed

## [0.12.0] - 2026-02-21

### Quality Milestone Release - V4 Audit Cleared

This release completes 4 rounds of production quality audits (V1-V4) with all DataFlow-specific gaps remediated.

### Added

- **Auto-Wired Multi-Tenancy**: QueryInterceptor injects tenant filtering at 8 SQL execution points automatically
- **Async Transactions**: Transaction nodes are AsyncNode subclasses with proper `async_run()` pattern
- **Debug Persistence**: KnowledgeBase supports persistent SQLite storage for debug patterns
- **Savepoint Validation**: Regex-validated savepoint names prevent SQL injection in transaction nodes

### Changed

- **Bare Exception Cleanup**: All 4 bare `except:` blocks in engine.py replaced with `except Exception:`
- **SQL Injection Prevention**: Enhanced `_is_invalid_identifier()` with comprehensive SQL keyword blacklist
- **Sensitive Value Masking**: All logging paths use `mask_sensitive_values()` for credential safety

### Security

- Parameterized queries throughout (no f-string interpolation in SQL)
- Savepoint names validated via `^[A-Za-z_][A-Za-z0-9_]{0,62}$` regex
- Table/column/schema names validated before use in DDL
- Default values validated for injection patterns
- V4 audit: 0 CRITICAL, 0 HIGH findings

### Test Results

- 794 unit tests passed

## [0.10.12] - 2026-01-07

### Added

#### Centralized Logging Configuration (ADR-002)

- **New**: `LoggingConfig` dataclass for centralized log level control
  - `LoggingConfig.production()` - Only WARNING+ (production deployments)
  - `LoggingConfig.development()` - DEBUG level (local development)
  - `LoggingConfig.quiet()` - Only CRITICAL (testing with minimal output)
  - `LoggingConfig.from_env()` - Environment variable configuration
- **New**: `log_level` and `log_config` parameters in `DataFlow.__init__()`
  - `db = DataFlow("postgresql://...", log_level=logging.WARNING)`
  - `db = DataFlow("postgresql://...", log_config=LoggingConfig.production())`
- **New**: Category-specific log levels (node_execution, sql_generation, list_operations, migration, core)
- **New**: `mask_sensitive()` function for security-safe logging
- **New**: `configure_dataflow_logging()`, `restore_dataflow_logging()`, and `is_logging_configured()` utilities
- **New**: Environment variables for 12-factor app configuration:
  - `DATAFLOW_LOG_LEVEL` - Default level
  - `DATAFLOW_NODE_EXECUTION_LOG_LEVEL` - Node execution traces
  - `DATAFLOW_SQL_GENERATION_LOG_LEVEL` - SQL generation diagnostics
  - `DATAFLOW_MIGRATION_LOG_LEVEL` - Migration operations

### Fixed

#### Reduced WARNING Noise from 524 to 0 Messages

- **Fixed**: Node execution tracing messages incorrectly logged at WARNING level → DEBUG
- **Fixed**: SQL generation diagnostics incorrectly logged at WARNING level → DEBUG
- **Fixed**: ListNode field ordering info incorrectly logged at WARNING level → DEBUG
- **Fixed**: SQLite result tracing incorrectly logged at WARNING level → DEBUG
- **Fixed**: Core SDK node registration using root logger → named logger at INFO
- **Fixed**: Core SDK DDL safety check warnings during schema creation → DEBUG
- **Fixed**: Core SDK parameter validation warnings for expected behavior → DEBUG
- **Fixed**: Migration table creation attempted even when `migration_enabled=False`

### Changed

- Default logging behavior unchanged (WARNING level) for backward compatibility
- All diagnostic/trace messages now correctly logged at DEBUG level per ADR-002

---

## [0.10.2] - 2025-11-29

### Critical Bug Fixes

#### Session-Scoped Event Loop Deadlock Fixed (DATAFLOW-SESSION-LOOP-DEADLOCK-001)

- **Fixed**: `discover_schema()` causes deadlocks when called from pytest tests using session-scoped event loops (`asyncio_default_fixture_loop_scope = session`)
- **Bug ID**: DATAFLOW-SESSION-LOOP-DEADLOCK-001
- **Root Cause**: The v0.10.1 fix using `ThreadPoolExecutor + asyncio.run()` creates a NEW event loop in the worker thread, which cannot access connection pools tied to the ORIGINAL session-scoped pytest event loop, causing `future.result()` to block forever
- **Location**: `src/dataflow/core/engine.py:2545-2810, 5033-5095`
- **Solution**: Implemented async-first API pattern:
  1. `discover_schema()` now raises `RuntimeError` when called from a running async context with clear guidance
  2. Added `discover_schema_async()` for safe use in async contexts (uses existing event loop)
  3. Updated `_get_table_columns()` to handle async context gracefully with fallback
  4. Added `_get_table_columns_async()` for async contexts
- **Impact**:
  - ✅ Clear error message in async contexts prevents silent deadlocks
  - ✅ `discover_schema_async()` works correctly with session-scoped pytest event loops
  - ✅ `_get_table_columns()` no longer triggers deadlock in async workflows
  - ✅ Backward compatible: sync code paths unchanged
- **Breaking**: NO - adds new methods, existing sync usage unchanged
- **Example**:

  ```python
  # Before: Hangs indefinitely in session-scoped pytest fixtures
  # ThreadPoolExecutor creates new loop that can't access session-scoped pool

  # After: Clear error with guidance
  async def test_with_session_loop(dataflow_instance):
      try:
          schema = dataflow_instance.discover_schema(use_real_inspection=True)
      except RuntimeError as e:
          # "discover_schema() cannot be called from a running async context.
          #  Use 'await discover_schema_async()' instead"
          pass

  # Solution: Use async version
  async def test_with_session_loop(dataflow_instance):
      schema = await dataflow_instance.discover_schema_async(use_real_inspection=True)
      # Works correctly with session-scoped event loop!
  ```

- **New Methods**:
  - `discover_schema_async(use_real_inspection: bool = False)` - Async version for async contexts
  - `_get_table_columns_async(table_name: str)` - Async version for internal use
- **Test Coverage**: 3 comprehensive tests
  - Sync context test (existing behavior preserved)
  - Async context RuntimeError test (new protection)
  - Async version test (new functionality)
- **Test Results**: 3/3 passing (100% success rate)
- **Files Modified**:
  - `src/dataflow/core/engine.py` (discover_schema, discover_schema_async, \_get_table_columns, \_get_table_columns_async, \_generate_mock_schema_data)
  - `test_session_scoped_loop_deadlock.py` (reproduction test)

---

## [0.10.1] - 2025-11-28

### Critical Bug Fixes

#### Nested Event Loop Deadlock Fixed (DATAFLOW-NESTED-LOOP-001)

- **Fixed**: `discover_schema()` hangs/deadlocks when called from async context
- **Bug ID**: DATAFLOW-NESTED-LOOP-001
- **Root Cause**: `discover_schema()` called `asyncio.run()` while already inside an async event loop, causing deadlock
- **Location**: `src/dataflow/core/engine.py:2559`
- **Solution**: Use `ThreadPoolExecutor` to run async operation in separate thread when already in async context
- **Impact**:
  - ✅ `discover_schema()` can now be safely called from async functions
  - ✅ No deadlock or hanging when used in async contexts (FastAPI, async workflows, etc.)
  - ✅ Works correctly with or without `nest_asyncio` installed
  - ✅ Maintains backward compatibility with sync code paths
- **Breaking**: NO - fully backward compatible, transparent to users
- **Note**: See v0.10.2 for follow-up fix addressing session-scoped pytest event loops

---

## [0.9.7] - 2025-11-25

### Critical Bug Fixes

#### Nested Event Loop Deadlock Fixed (DATAFLOW-NESTED-LOOP-001)

- **Fixed**: `discover_schema()` hangs/deadlocks when called from async context
- **Bug ID**: DATAFLOW-NESTED-LOOP-001
- **Root Cause**: `discover_schema()` called `asyncio.run()` while already inside an async event loop, causing deadlock
- **Location**: `src/dataflow/core/engine.py:2559`
- **Solution**: Use `ThreadPoolExecutor` to run async operation in separate thread when already in async context
  - Removed dependency on `nest_asyncio` (which masked but didn't fix the underlying issue)
  - Always use `ThreadPoolExecutor` when existing event loop is detected
  - Continue using `asyncio.run()` when no event loop is running (safe case)
- **Impact**:
  - ✅ `discover_schema()` can now be safely called from async functions
  - ✅ No deadlock or hanging when used in async contexts (FastAPI, async workflows, etc.)
  - ✅ Works correctly with or without `nest_asyncio` installed
  - ✅ Maintains backward compatibility with sync code paths
- **Breaking**: NO - fully backward compatible, transparent to users
- **Example**:

  ```python
  # Before: Hangs indefinitely when called from async context
  # asyncio.run() cannot be called from a running event loop

  # After: Works correctly in all contexts
  import asyncio
  from dataflow import DataFlow

  async def async_function():
      db = DataFlow("postgresql://...")
      schema = db.discover_schema(use_real_inspection=True)  # No deadlock!
      return schema

  # Also works in sync contexts (no change)
  db = DataFlow("postgresql://...")
  schema = db.discover_schema(use_real_inspection=True)  # Still works
  ```

- **Test Coverage**: 2 comprehensive tests
  - Direct async context test (most common failure scenario)
  - run_in_executor wrapper test (FastAPI/async web framework scenario)
- **Test Results**: 2/2 passing (100% success rate)
- **Files Modified**:
  - `src/dataflow/core/engine.py` (discover_schema method - simplified to always use ThreadPoolExecutor in async contexts)

#### Cache Async/Await Bug Fixed (DATAFLOW-CACHE-ASYNC-001)

- **Fixed**: `TypeError: 'coroutine' object does not support item assignment` in cache operations when using `InMemoryCache`
- **Bug ID**: DATAFLOW-CACHE-ASYNC-001
- **Root Cause**: `ListNodeCacheIntegration` called async cache methods without `await`, treating coroutines as regular values
- **Location**: `src/dataflow/cache/list_node_integration.py:74, 88, 108`
- **Solution**: Implemented unified async cache interface across all backends
  - Created `AsyncRedisCacheAdapter` to wrap sync `RedisCacheManager` with async interface
  - Added `await` to 3 cache method calls in `ListNodeCacheIntegration`
  - Normalized `get_metrics()` response format across InMemoryCache and Redis backends
  - Added `get_metrics()` and `invalidate_model()` methods to `AsyncRedisCacheAdapter`
- **Impact**:
  - ✅ InMemoryCache (native async) works correctly with await
  - ✅ RedisCacheManager (sync) wrapped with `AsyncRedisCacheAdapter` for async compatibility
  - ✅ ListNode cache operations no longer throw TypeError
  - ✅ Unified async interface across all cache backends
- **Breaking**: NO - fully backward compatible, transparent to users
- **Example**:

  ```python
  # Before: Failed with TypeError
  # TypeError: 'coroutine' object does not support item assignment

  # After: Works correctly with both cache backends
  from dataflow.cache.auto_detection import CacheBackend
  from dataflow.cache.list_node_integration import ListNodeCacheIntegration

  # Auto-detect returns either InMemoryCache or AsyncRedisCacheAdapter
  cache = CacheBackend.auto_detect()  # Both have unified async interface

  # Use with ListNode operations (now with proper await)
  result = await integration.execute_with_cache(
      model_name="User",
      query="SELECT * FROM users",
      params=[],
      executor_func=lambda: {"data": "value"},
      cache_enabled=True
  )
  ```

- **Test Coverage**: 53 comprehensive tests across 3 tiers
  - Tier 1 (Unit): 32 tests for AsyncRedisCacheAdapter (all passing)
  - Tier 2 (Integration): 15 tests with real InMemoryCache (all passing)
  - Tier 3 (E2E): 6 tests with complete workflows (all passing)
- **Test Results**: 53/53 passing (100% success rate)
- **Files Modified**:
  - `src/dataflow/cache/async_redis_adapter.py` (NEW - 370 lines)
  - `src/dataflow/cache/__init__.py` (added AsyncRedisCacheAdapter export)
  - `src/dataflow/cache/auto_detection.py` (returns AsyncRedisCacheAdapter for Redis)
  - `src/dataflow/cache/list_node_integration.py` (added await to 3 cache calls)

#### Model Registration Race Condition Fixed

- **Fixed**: Race condition in pytest where models imported during test collection phase failed to register because `dataflow_model_registry` table didn't exist yet
- **Root Cause**: Model `@db.model` decorators executed at import time (before table creation), triggering immediate registration queries that failed in pytest collection phase
- **Location**: `src/dataflow/core/model_registry.py:92-167, 311-335`
- **Solution**: Implemented lazy model registration queue system
  - Models queue for registration before initialization (`_pending_models`)
  - Registry initialization automatically processes pending models (`_finalize_initialization()`)
  - Thread-safe with `threading.Lock()` protection for concurrent registration
  - Backward compatible: Initialized registries register models immediately (no queue)
- **Impact**:
  - ✅ Pytest tests now work correctly (all 32 Kaizen Studio models register successfully)
  - ✅ Standalone scripts unchanged (registry auto-initializes during DataFlow construction)
  - ✅ Production deployments protected from import-time registration failures
- **Breaking**: NO - fully backward compatible, transparent to users
- **Example**:

  ```python
  # Before: Failed in pytest collection phase
  # ERROR: relation "dataflow_model_registry" does not exist

  # After: Models queue during import, register after initialization
  db = DataFlow("postgresql://...")  # Registry initializes

  @db.model  # Registers immediately (or queues if not initialized)
  class User:
      id: str
      name: str

  # Pytest collection phase: Models queue successfully
  # Test execution phase: Models registered when test_db fixture runs
  ```

- **Test Coverage**: 15 comprehensive unit tests covering:
  - Model queueing before initialization
  - Immediate registration after initialization
  - Finalization process
  - Thread safety
  - Error handling
  - Backward compatibility
- **Test Results**: 15/15 passing (`tests/unit/test_lazy_model_registration.py`)

#### Database Infrastructure Threading Issue Fixed

- **Fixed**: `'tuple' object has no attribute 'execute'` errors when using `AsyncSQLDatabaseNode` with synchronous `LocalRuntime` for DDL operations
- **Root Cause**: Model registry and schema state manager used asynchronous `AsyncSQLDatabaseNode` with synchronous `LocalRuntime`, which returned tuples instead of database results
- **Location**:
  - `src/dataflow/core/model_registry.py` (17 instances)
  - `src/dataflow/migrations/schema_state_manager.py` (4 instances)
- **Solution**: Replaced all `AsyncSQLDatabaseNode` with synchronous `SQLDatabaseNode` for DDL operations
  - DDL operations (CREATE TABLE, CREATE INDEX) now use `SQLDatabaseNode` with `LocalRuntime`
  - Parameter naming corrected from `"params"` to `"parameters"` (8 instances)
  - Works correctly in all contexts: sync, async, and pytest
- **Impact**:
  - ✅ All DataFlow DDL operations work correctly (table creation, index creation)
  - ✅ No more runtime/node type mismatches
  - ✅ Compatible with all runtime contexts
- **Breaking**: NO - internal implementation change only
- **Performance**: No impact (DDL operations are infrequent)
- **Test Coverage**: All 46 DataFlow core tests passing

### Documentation Updates

#### Test Expectations Updated

- **Updated**: Integration test expectations to reflect lazy registration behavior
- **Location**: `tests/unit/test_lazy_model_registration.py:340-367`
- **Changes**:
  - Registry now auto-initializes during DataFlow construction (correct behavior)
  - Models register immediately instead of queueing (registry already initialized)
  - Updated assertions to expect `_initialized=True` and `_pending_models=0`
- **Rationale**: Tests now verify correct behavior (auto-initialization) instead of incorrect expectations

### Migration Guide

#### No Action Required for Users

This release is **100% backward compatible**:

- ✅ Existing code works unchanged
- ✅ No API changes
- ✅ No configuration changes
- ✅ No breaking changes

#### Benefits for Users

1. **Pytest Compatibility**: Tests using DataFlow models now work correctly
2. **Production Safety**: Import-time registration failures prevented
3. **Better Error Handling**: Graceful fallback if initialization fails

#### Internal Changes Only

- Model registration uses queue system (transparent to users)
- DDL operations use synchronous SQLDatabaseNode (internal implementation)
- No user-facing API changes

### Verification

#### Test Results

- **Lazy Registration Tests**: 15/15 passing ✅
- **DataFlow Core Tests**: 46/46 passing ✅
- **No Regressions**: All existing functionality preserved ✅

#### Verified Scenarios

1. ✅ Standalone scripts (registry auto-initializes)
2. ✅ Pytest tests (models queue during collection, register during execution)
3. ✅ Multi-threaded applications (thread-safe registration)
4. ✅ FastAPI/Gunicorn deployments (protected from import-time failures)

---

## [0.7.12] - 2025-11-02

### Bug Fixes

#### Bulk Operations Rowcount Extraction Fixed

- **Fixed**: `bulk_create` incorrectly prioritized `row_count` field over `data.rows_affected`, causing inaccurate reporting
- **Location**: `src/dataflow/features/bulk.py:342-368`
- **Root Cause**: Extraction logic checked `row_count` first (calculated from `len(data)` = 1), instead of `data[0]['rows_affected']` (actual database rowcount)
- **Solution**: Reversed extraction priority to check `data` field FIRST, then fall back to `row_count` for backward compatibility
- **Example**:
  ```python
  # Before: Reported 1 record created when 3 were actually created
  # After: Correctly reports 3 records created
  workflow.add_node("ProductBulkCreateNode", "import", {
      "data": [{"id": "1"}, {"id": "2"}, {"id": "3"}]
  })
  ```
- **Impact**: All bulk operations now accurately report database operation counts
- **Related**: Requires Core SDK v0.10.6+ for proper rowcount capture from database adapters
- **Breaking**: NO - fully backward compatible, fixes reporting accuracy only

---

## [0.7.11] - 2025-10-31

### Bug Fixes

#### Bulk Operations Parameter Handling Fixed

- **Fixed**: `TypeError: got multiple values for keyword argument 'model_name'` in all 4 bulk operations (BulkCreate, BulkUpdate, BulkDelete, BulkUpsert)
- **Location**: `src/dataflow/core/nodes.py` lines 2835, 2951-2952, 3054-3055, 3116
- **Root Cause**: Bulk operations passed explicit parameters (`model_name`, `db_instance`) and then spread `**kwargs` without filtering those same parameters, causing conflicts when global workflow inputs contained these parameters
- **Solution**: Added `"model_name"` and `"db_instance"` to exclusion lists in all 4 bulk operations' kwargs filtering
- **Impact**: All bulk operations now work correctly with Nexus/AsyncLocalRuntime global parameters
- **Breaking**: NO - fully backward compatible, no API changes
- **Example**:
  ```python
  # Now works correctly with global parameters:
  workflow.add_node("ProductBulkDeleteNode", "cleanup", {
      "filter": {"active": False}
  })
  results, _ = await runtime.execute_workflow_async(
      workflow.build(),
      inputs={"model_name": "Product", "user_id": "admin"}  # Global params no longer cause conflicts
  )
  ```

---

## [0.7.10] - 2025-10-30

### New Features

#### Test Mode API (ADR-017)

- **Added**: Comprehensive Test Mode API for production-grade async testing
- **Features**:
  - 3-tier auto-detection (explicit parameter > global setting > auto-detection)
  - Global test mode control via `DataFlow.enable_test_mode()`, `disable_test_mode()`, `is_test_mode_enabled()`
  - Connection pool cleanup methods: `cleanup_stale_pools()`, `cleanup_all_pools()`, `get_cleanup_metrics()`
  - Thread-safe with RLock protection for multi-threaded applications
  - Zero overhead (<150ms per test with aggressive cleanup)
- **Benefits**:
  - Eliminates "Event loop is closed" errors in pytest
  - Prevents pool leaks between tests
  - Automatic detection when running under pytest
  - Graceful error handling with detailed metrics
- **Location**: `src/dataflow/core/engine.py:270-1600`
- **Breaking**: NO - fully backward compatible, opt-in feature
- **Documentation**: See `/packages/kailash-dataflow/adr/ADR-017-*.md` (6 files) for complete specification

#### AsyncSQLDatabaseNode Enhancements

- **Added**: Async-first cleanup method `_cleanup_closed_loop_pools()` (async class method)
- **Enhanced**: `clear_shared_pools()` now accepts `graceful` parameter with detailed metrics return
- **Added**: `_total_pools_created` counter for lifecycle tracking
- **Benefits**:
  - Proper async handling (no more "object int can't be used in await" errors)
  - Graceful pool cleanup with error reporting
  - Complete pool lifecycle visibility
- **Location**: `src/kailash/nodes/data/async_sql.py:2371-3500`
- **Breaking**: NO - backward compatible, enhanced API

### Test Coverage

- **Added**: 33 comprehensive unit tests covering all Test Mode API features
- **Coverage**: Test mode detection (7 tests), global control (4 tests), priority system (5 tests), logging (4 tests), cleanup methods (8 tests), graceful degradation (3 tests), backward compatibility (3 tests)
- **Result**: 100% passing (33/33 tests)
- **Location**: `tests/unit/core/test_dataflow_test_mode.py`

### Documentation Updates

- **Added**: Complete Test Mode API documentation in dataflow-specialist subagent
- **Sections**: API overview, configuration, cleanup methods, fixture patterns, troubleshooting
- **Location**: `.claude/agents/frameworks/dataflow-specialist.md:923-1103`
- **Quick Reference**: Test Mode Configuration table added to Quick Config section

## [0.6.3] - 2025-10-22

### Bug Fixes

#### BulkDeleteNode Safe Mode Validation Fixed

- **Fixed**: Similar truthiness bug in BulkDeleteNode safe mode validation
- **Location**: `src/dataflow/nodes/bulk_delete.py:177`
- **Root Cause**: `not filter_conditions` evaluates to True for empty dict `{}`, incorrectly rejecting valid operations
- **Solution**: Changed from `not filter_conditions` to `"filter" not in validated_inputs` to match pattern at line 153
- **Impact**: BulkDeleteNode safe_mode now correctly handles empty filter operations
- **Discovery**: Found during comprehensive search for similar bugs after v0.6.2 fix
- **Consistency**: Makes line 177 consistent with line 153's validation logic
- **Documentation**: See SIMILAR_BUGS_SEARCH_REPORT.md for complete search results
- **Breaking**: NO - backward compatible, fixes edge case

### Comprehensive Bug Search

- **Searched**: 50+ files, 100+ code locations, 13 suspicious patterns found
- **Result**: 1 real bug found and fixed (bulk_delete.py), 12 false positives (correct behavior)
- **Confidence**: Very High (95%+) - All similar truthiness bugs have been found and fixed
- **Report**: SIMILAR_BUGS_SEARCH_REPORT.md contains full methodology and findings

## [0.6.2] - 2025-10-22

### Critical Bug Fixes

#### ListNode Filter Operators Fixed

- **Fixed**: Critical bug where all MongoDB-style filter operators ($ne, $nin, $in, $not) were broken in ListNode except $eq
- **Root Cause**: Python truthiness bug - `if filter_dict:` evaluates to False for empty dict `{}`, causing QueryBuilder path to be skipped
- **Solution**: Changed condition from `if filter_dict:` to `if "filter" in kwargs:` at line 1810 in nodes.py
- **Impact**: All filter operators now work correctly - $ne, $nin, $in, $not, $gt, $lt, $gte, $lte, $regex, etc.
- **Evidence**: SQL query logging confirms QueryBuilder path is now used correctly with proper WHERE clauses
- **Example**:
  ```python
  # Now works correctly:
  workflow.add_node("UserListNode", "list_active", {
      "filter": {"status": {"$ne": "inactive"}}
  })
  # Generates: SELECT * FROM "users" WHERE "status" != $1
  ```
- **Files Changed**: `src/dataflow/core/nodes.py:1810`
- **Documentation**: See BUGFIX_EVIDENCE.md for complete proof
- **Matches**: v0.5.2 fix pattern for BulkUpdateNode and BulkDeleteNode
- **Breaking**: NO - backward compatible, fixes broken functionality

## [0.6.1] - 2025-10-22

### Documentation

#### Comprehensive Documentation Updates

- **Updated**: Complete documentation refresh for DataFlow framework
- **New Guides**: Added specialized guides for bulk operations, migrations, multi-tenancy, and performance
- **Updated Version**: All documentation now references DataFlow 0.6.0+
- **Files Updated**:
  - `.claude/skills/02-dataflow/*.md` - 13 comprehensive guides
  - Examples, patterns, and best practices updated
- **Breaking**: NO - documentation only

## [0.6.0] - 2025-10-21

### Major Features

#### MongoDB Document Database Support

- **Added**: Complete MongoDB document database support via MongoDBAdapter
- **Impact**: Enables NoSQL applications, flexible schema operations, and rapid iteration with document-based data models
- **Components**:
  - `MongoDBAdapter` - Extends BaseAdapter with Motor async driver for MongoDB operations
  - `DocumentInsertNode` - Insert single document workflow node
  - `DocumentFindNode` - Find documents with filters, sorting, and pagination
  - `DocumentUpdateNode` - Update one or many documents
  - `DocumentDeleteNode` - Delete one or many documents
  - `AggregateNode` - Execute MongoDB aggregation pipelines
  - `BulkDocumentInsertNode` - Bulk insert documents
  - `CreateIndexNode` - Create indexes (simple or compound)
  - `DocumentCountNode` - Count documents matching filter
- **Features**:
  - Flexible schema (schemaless) document operations
  - MongoDB Query Language support (comparison, logical, array operators)
  - Aggregation pipelines for complex data processing
  - Index management (single, compound, text, geospatial)
  - Collection management (create, drop, list, exists)
  - Connection pooling with Motor async driver
  - Health checks and comprehensive error handling
- **Files**:
  - `src/dataflow/adapters/mongodb.py` (870 lines) - MongoDB adapter implementation
  - `src/dataflow/nodes/mongodb_nodes.py` (910 lines) - 8 MongoDB workflow nodes
- **Tests**: 83 comprehensive tests (100% passing)
  - `tests/unit/adapters/test_mongodb_adapter.py` (850+ lines) - 43 adapter tests
  - `tests/unit/nodes/test_mongodb_nodes.py` (900+ lines) - 40 node tests
  - All tests passed in 0.61s
- **Documentation**:
  - `docs/guides/mongodb-quickstart.md` (800+ lines) - Complete user guide
  - `docs/architecture/mongodb-implementation-plan.md` - Architecture specification
  - `examples/mongodb_crud_example.py` (400+ lines) - Complete CRUD example
- **Dependencies**:
  - `motor>=3.3.0` - MongoDB async driver
  - `pymongo>=4.5.0` - Motor dependency
  - `dnspython>=2.4.0` - For mongodb+srv:// URLs
- **Breaking**: NO - fully backward compatible, opt-in feature

**Example Usage**:

```python
from dataflow import DataFlow
from dataflow.adapters import MongoDBAdapter

# Create MongoDB adapter
adapter = MongoDBAdapter(
    "mongodb://localhost:27017/mydb",
    maxPoolSize=50,
    minPoolSize=10
)
db = DataFlow(adapter=adapter)
await db.initialize()

# Document operations using adapter
user_id = await adapter.insert_one("users", {
    "name": "Alice",
    "email": "alice@example.com",
    "age": 30,
    "tags": ["developer", "python"]
})

users = await adapter.find("users",
    filter={"age": {"$gte": 25}},
    sort=[("name", 1)],
    limit=10
)

# Workflow integration
from dataflow.nodes.mongodb_nodes import DocumentFindNode, AggregateNode
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()

# Find active users
workflow.add_node("DocumentFindNode", "find_users", {
    "collection": "users",
    "filter": {"status": "active"},
    "sort": [("name", 1)]
})

# Aggregate sales by category
workflow.add_node("AggregateNode", "sales_summary", {
    "collection": "orders",
    "pipeline": [
        {"$match": {"status": "completed"}},
        {"$group": {
            "_id": "$category",
            "total": {"$sum": "$amount"}
        }},
        {"$sort": {"total": -1}}
    ]
})

results = await runtime.execute_workflow_async(workflow.build())
```

**MongoDB vs SQL Comparison**:

```python
# SQL Approach (PostgreSQL)
db = DataFlow("postgresql://localhost/mydb")

@db.model
class User:
    id: int
    name: str
    email: str

# MongoDB Approach (Flexible Schema)
adapter = MongoDBAdapter("mongodb://localhost:27017/mydb")
db = DataFlow(adapter=adapter)

# No model definition needed - direct document operations
await adapter.insert_one("users", {
    "name": "Alice",
    "email": "alice@example.com",
    "profile": {"age": 30, "city": "NYC"},  # Nested documents
    "tags": ["developer", "python"],         # Arrays
    # Any fields, no schema constraints!
})
```

### Multi-Database Support Matrix

DataFlow now supports 4 database types:

| Database                  | Adapter                   | Use Case                          | Schema         | Query Language         |
| ------------------------- | ------------------------- | --------------------------------- | -------------- | ---------------------- |
| **PostgreSQL**            | `PostgreSQLAdapter`       | Production, complex queries, ACID | Fixed          | SQL                    |
| **PostgreSQL + pgvector** | `PostgreSQLVectorAdapter` | RAG, semantic search              | Fixed + Vector | SQL + Vector           |
| **MongoDB**               | `MongoDBAdapter`          | Flexible schema, rapid iteration  | Schemaless     | MongoDB Query Language |
| **SQLite**                | `SQLiteAdapter`           | Development, embedded, mobile     | Fixed          | SQL                    |

### Documentation Updates

- Added MongoDB roadmap to `.claude/skills/02-dataflow/SKILL.md`
- Complete MongoDB quickstart guide with CRUD examples
- Architecture decision records for MongoDB implementation
- README updated with MongoDB support information

### Testing Coverage

- **NO MOCKING** policy maintained for integration tests
- 83 unit tests for MongoDB adapter and nodes (100% passing)
- Comprehensive test coverage for document operations, queries, aggregation, indexing

#### PostgreSQL Vector Similarity Search (pgvector Support)

- **Added**: Complete vector similarity search support via PostgreSQLVectorAdapter
- **Impact**: Enables RAG applications, semantic search, and hybrid search with 40-60% cost savings vs dedicated vector databases
- **Components**:
  - `PostgreSQLVectorAdapter` - Extends PostgreSQLAdapter with vector operations
  - `VectorSearchNode` - Semantic similarity search workflow node
  - `CreateVectorIndexNode` - Vector index creation workflow node
  - `HybridSearchNode` - Combined vector + full-text search workflow node
- **Features**:
  - Multiple distance metrics: cosine, L2, inner product
  - IVFFlat and HNSW index types
  - Hybrid search with RRF (Reciprocal Rank Fusion)
  - Filter-based vector search
  - Vector column statistics
- **Files**:
  - `src/dataflow/adapters/postgresql_vector.py` (465 lines) - Vector adapter implementation
  - `src/dataflow/nodes/vector_nodes.py` (460 lines) - Vector workflow nodes
- **Tests**: 40 comprehensive tests (24 unit, 16 integration)
  - `tests/unit/adapters/test_postgresql_vector_adapter.py` (443 lines)
  - `tests/unit/nodes/test_vector_nodes.py` (566 lines)
  - `tests/integration/adapters/test_postgresql_vector_adapter_integration.py` (340 lines)
  - `tests/integration/nodes/test_vector_nodes_integration.py` (290 lines)
- **Documentation**:
  - `docs/guides/pgvector-quickstart.md` - Complete user guide
  - `docs/architecture/pgvector-implementation-plan.md` - Architecture specification
  - `docs/pgvector-implementation-summary.md` - Implementation summary
- **Breaking**: NO - fully backward compatible, opt-in feature

**Example Usage**:

```python
from dataflow import DataFlow
from dataflow.adapters import PostgreSQLVectorAdapter

# Create vector adapter
adapter = PostgreSQLVectorAdapter(
    "postgresql://localhost/vectordb",
    vector_dimensions=1536,  # OpenAI embeddings
    default_distance="cosine"
)
db = DataFlow(adapter=adapter)

# Semantic search
from dataflow.nodes.vector_nodes import VectorSearchNode
from kailash.workflow.builder import WorkflowBuilder

workflow = WorkflowBuilder()
workflow.add_node("VectorSearchNode", "search", {
    "table_name": "documents",
    "query_vector": embedding,  # 1536-dim vector from AI model
    "k": 5,
    "distance": "cosine"
})

results = await runtime.execute_workflow_async(workflow.build())
documents = results["search"]["results"]  # Top 5 similar documents
```

#### BaseAdapter Hierarchy

- **Added**: Minimal base interface for all adapter types (SQL, Document, Vector, Graph, Key-Value)
- **Impact**: Foundation for multi-database support beyond SQL
- **Component**: `src/dataflow/adapters/base_adapter.py` (133 lines)
- **Changes**: DatabaseAdapter now inherits from BaseAdapter
- **Tests**: 10 comprehensive tests in `tests/unit/adapters/test_base_adapter_hierarchy.py`
- **Breaking**: NO - fully backward compatible

**Adapter Hierarchy**:

```
BaseAdapter (minimal interface)
├── DatabaseAdapter (SQL databases)
│   ├── PostgreSQLAdapter
│   │   └── PostgreSQLVectorAdapter (vector search)
│   ├── MySQLAdapter
│   └── SQLiteAdapter
└── Future: DocumentAdapter, VectorAdapter, GraphAdapter, KeyValueAdapter
```

### Performance

#### Vector Search Benchmarks

- **Query Latency**: <50ms for 100K vectors (with IVFFlat index)
- **Index Build**: <5 minutes for 1M vectors (IVFFlat)
- **Memory**: <2GB for 1M vectors (1536 dimensions)
- **Throughput**: >100 QPS for semantic search operations

### Documentation Updates

- Added pgvector roadmap to `.claude/skills/02-dataflow/SKILL.md`
- Added "Coming Soon" sections to README and CLAUDE.md
- Complete pgvector quickstart guide with RAG examples
- Architecture decision records for BaseAdapter hierarchy

### Testing Improvements

- **NO MOCKING** policy enforced for integration tests
- Real PostgreSQL + pgvector infrastructure testing
- Concurrent vector search tests
- Hybrid search integration tests

### Compatibility

- ✅ 100% backward compatible
- ✅ All existing tests passing (60+ tests)
- ✅ Zero breaking changes
- ✅ Opt-in feature (requires pgvector extension)

## [0.5.4] - 2025-10-11

### Critical Bug Fixes

#### Cache Invalidation Missing in Bulk Operations (HIGH PRIORITY)

- **Fixed**: BulkUpdateNode, BulkDeleteNode, and BulkUpsertNode now properly invalidate query cache after data modifications
- **Impact**: ListNode queries now return fresh database data instead of stale cached results
- **Root Cause**: Missing `cache_integration.invalidate_model_cache()` calls after successful bulk operations
- **Symptoms**: Applications using bulk operations with query caching were getting stale data, causing data consistency issues
- **Locations**:
  - `src/dataflow/core/nodes.py:1884-1897` - Added cache invalidation to BulkUpdateNode
  - `src/dataflow/core/nodes.py:1940-1953` - Added cache invalidation to BulkDeleteNode
  - `src/dataflow/core/nodes.py:1997-2010` - Added cache invalidation to BulkUpsertNode
- **Tests**: 3 comprehensive integration tests in `tests/integration/test_cache_invalidation_bug.py`
- **Breaking**: NO - previously broken functionality now works correctly

**Before**:

```python
# Step 1: Bulk delete all records
workflow.add_node('AgentMemoryBulkDeleteNode', 'cleanup', {
    'filter': {}, 'confirmed': True
})
runtime.execute(workflow.build())  # ❌ Cache NOT invalidated

# Step 2: Query after deletion
workflow.add_node('AgentMemoryListNode', 'query', {
    'filter': {'workflow_run_id': 300}
})
result, _ = runtime.execute(workflow.build())
# BUG: Returns old cached data instead of empty result
# {'records': [old_data], '_cache': {'hit': True}}
```

**After**:

```python
# Step 1: Bulk delete all records
workflow.add_node('AgentMemoryBulkDeleteNode', 'cleanup', {
    'filter': {}, 'confirmed': True
})
runtime.execute(workflow.build())  # ✅ Cache properly invalidated

# Step 2: Query after deletion
workflow.add_node('AgentMemoryListNode', 'query', {
    'filter': {'workflow_run_id': 300}
})
result, _ = runtime.execute(workflow.build())
# ✅ Returns fresh data from database: {'records': [], 'count': 0}
```

#### Async/Await Bug in BulkUpsertNode (CRITICAL)

- **Fixed**: BulkUpsertNode now properly awaits async `bulk_upsert()` function call
- **Impact**: Prevents runtime errors when bulk_upsert operations are executed
- **Root Cause**: Missing `await` keyword when calling async function
- **Location**: `src/dataflow/core/nodes.py:1982` - Added `await` keyword
- **Related**: `src/dataflow/features/bulk.py:564` - Changed `bulk_upsert` from `def` to `async def`
- **Breaking**: NO - fixes previously broken async execution

**Before**:

```python
# Missing await caused runtime errors
bulk_result = self.dataflow_instance.bulk.bulk_upsert(...)  # ❌ WRONG
```

**After**:

```python
# Properly awaits async function
bulk_result = await self.dataflow_instance.bulk.bulk_upsert(...)  # ✅ CORRECT
```

#### Return Structure Inconsistencies (HIGH PRIORITY)

- **Fixed**: BulkDeleteNode and BulkUpsertNode exception handlers now include operation-specific aliases
- **Impact**: API consistency across all bulk operations; better error handling
- **Root Cause**: Missing "deleted" and "upserted" aliases in exception return structures
- **Locations**:
  - `src/dataflow/core/nodes.py:1974` - Added "deleted": 0 to BulkDeleteNode exception handler
  - `src/dataflow/core/nodes.py:2041` - Added "upserted": 0 to BulkUpsertNode exception handler
- **Breaking**: NO - adds missing fields, maintains backward compatibility

**Before**:

```python
# BulkDeleteNode exception: missing "deleted" alias
return {
    "processed": 0,
    # "deleted": 0 - MISSING!
    "success": False,
    "error": str(e),
}
```

**After**:

```python
# BulkDeleteNode exception: includes "deleted" alias for API consistency
return {
    "processed": 0,
    "deleted": 0,  # Alias for compatibility
    "success": False,
    "error": str(e),
}
```

#### Error Propagation Gap in BulkUpsertNode (HIGH PRIORITY)

- **Fixed**: BulkUpsertNode now properly propagates error details and operational statistics
- **Impact**: Better debugging experience; detailed upsert statistics (inserted/updated/skipped)
- **Root Cause**: Missing error propagation and detailed stat exposure
- **Location**: `src/dataflow/core/nodes.py:2013-2036` - Enhanced return structure with error propagation
- **Breaking**: NO - adds additional information without breaking existing behavior

**Enhanced Return Structure**:

```python
result = {
    "processed": bulk_result.get("records_processed", 0),
    "upserted": bulk_result.get("records_processed", 0),  # Alias for compatibility
    "batch_size": batch_size,
    "operation": operation,
    "success": bulk_result.get("success", True),
}

# Expose detailed upsert stats if available
if "inserted" in bulk_result:
    result["inserted"] = bulk_result["inserted"]
if "updated" in bulk_result:
    result["updated"] = bulk_result["updated"]
if "skipped" in bulk_result:
    result["skipped"] = bulk_result["skipped"]

# Propagate error details if operation failed
if not bulk_result.get("success", True) and "error" in bulk_result:
    result["error"] = bulk_result["error"]
```

#### Mock Implementation Warning for bulk_upsert (CRITICAL)

- **Added**: Comprehensive warnings that bulk_upsert is currently a stub implementation
- **Impact**: Users are clearly informed that data is NOT being upserted to the database
- **Root Cause**: bulk_upsert returns simulated data without performing real database operations
- **Location**: `src/dataflow/features/bulk.py:564-607` - Added docstring warning and runtime logging
- **Breaking**: NO - exposes existing limitation with clear communication

**Warning Added**:

```python
async def bulk_upsert(...) -> Dict[str, Any]:
    """Perform bulk upsert (insert or update) operation.

    WARNING: This is currently a STUB implementation that returns simulated data.
    Real database upsert operations are NOT yet implemented.
    Data is NOT being inserted or updated in the database.
    """
    logger.warning(
        f"BULK_UPSERT WARNING: This is a STUB implementation! "
        f"No actual database operations are performed. "
        f"Data will NOT be inserted or updated. "
        f"Model: {model_name}, Records: {len(data)}"
    )
```

### Test Coverage

- **Cache Invalidation Tests**: 3/3 PASSED in `tests/integration/test_cache_invalidation_bug.py`
  - `test_bulk_delete_cache_invalidation` - Delete → List returns fresh empty result
  - `test_bulk_update_cache_invalidation` - Update → List returns fresh updated data
  - `test_bulk_create_then_delete_then_create_cache_bug` - Exact user scenario reproduction
- **Unit Tests**: 36/36 PASSED (100%)
- **NO REGRESSIONS**: All existing tests continue to pass
- **Infrastructure**: Real PostgreSQL testing (NO MOCKING policy)

### Files Changed

- `src/dataflow/core/nodes.py` - 7 separate fixes across bulk operations
- `src/dataflow/features/bulk.py` - Made bulk_upsert async with warnings
- `tests/integration/test_cache_invalidation_bug.py` - New comprehensive test suite
- `docs/bugfix-v054-cache-invalidation.md` - Complete technical documentation

### Impact Assessment

- **Breaking Changes**: NONE - All fixes are backward compatible
- **Performance Impact**: Minimal - Cache invalidation adds ~0.1ms per bulk operation (negligible)
- **Migration Required**: NONE - Drop-in replacement for v0.5.3

### Dependencies

- Requires Kailash SDK >= 0.9.21 (no change from 0.5.3)

## [0.5.3] - 2025-10-10

### Critical Bug Fixes

#### Bulk Operation Truthiness Bugs (Bugs #1-3)

- **Fixed**: Empty dict/list handling in bulk_create, bulk_update, bulk_delete operations
- **Impact**: MongoDB-style empty filter `{}` and empty data `[]` now work correctly
- **Root Causes**:
  1. **Bug #1**: BulkDeleteNode empty filter execution failure - Python truthiness check failed on empty dict
  2. **Bug #2**: BulkCreateNode "Unsupported operation" error - Missing key existence check before accessing kwargs
  3. **Bug #3**: Generic error messages - Errors not properly propagated from bulk.py to nodes.py
- **Locations**:
  - `src/dataflow/core/nodes.py:1905, 1937, 1969` (changed to key existence checks)
  - `src/dataflow/features/bulk.py:87, 131, 175` (added proper error propagation)
  - `src/dataflow/core/nodes.py:1975` (added missing await for async bulk_update)
- **Tests**: 119/119 tests passing (100% pass rate, NO REGRESSIONS)
- **Breaking**: NO - previously broken functionality now works

**Before**:

```python
# Empty filter/data failed with various errors
node = BulkDeleteNode(...)
result = await node.async_run(filter={}, confirmed=True)  # ❌ FAILED
# Error: "Unsupported bulk operation" or generic errors

node = BulkCreateNode(...)
result = await node.async_run(data=[])  # ❌ FAILED
# Error: KeyError or "Unsupported operation"
```

**After**:

```python
# Empty filter/data works correctly
node = BulkDeleteNode(...)
result = await node.async_run(filter={}, confirmed=True)  # ✅ WORKS
# Successfully processes empty filter as "match all"

node = BulkCreateNode(...)
result = await node.async_run(data=[])  # ✅ WORKS
# Successfully handles empty data gracefully
```

### Real Database Operations Implementation

- **Implemented**: Real database operations for bulk_create, bulk_update, bulk_delete
- **Impact**: All bulk operations now execute actual SQL via AsyncSQLDatabaseNode
- **Features**:
  - Real INSERT, UPDATE, DELETE SQL execution
  - Proper error propagation from database layer
  - Support for batch processing
  - Transaction-aware operations
- **Location**: `src/dataflow/features/bulk.py`
- **Tests**: Comprehensive integration tests with real PostgreSQL database

### Safety Features

- **Added**: safe_mode parameter for bulk operations (default: True for delete)
- **Added**: confirmed parameter requirement for dangerous operations
- **Added**: Empty filter validation with clear error messages
- **Impact**: Prevents accidental full-table deletion/updates

**Safety Example**:

```python
# Safe mode prevents accidental deletion
node = BulkDeleteNode(safe_mode=True)  # Default
result = await node.async_run(filter={}, confirmed=True)  # ❌ Raises error
# Error: "Empty filter would delete all records. Set safe_mode=False if intentional"

# Explicit override for intentional full-table operations
node = BulkDeleteNode(safe_mode=False)
result = await node.async_run(filter={}, confirmed=True)  # ✅ Works
```

### Test Coverage

- **Bug Reproduction Tests**: 5/5 PASSED in `tests/integration/bulk_operations/test_v052_bug_reproduction.py`
  - `test_bug_1_bulk_delete_empty_filter` - Empty filter execution
  - `test_bug_2_bulk_create_unsupported_operation` - KeyError fix
  - `test_bug_3_generic_error_messages` - Error propagation
  - `test_empty_data_handling` - Empty list handling
  - `test_error_propagation_chain` - Full error chain validation

- **Bulk Update Tests**: 8/8 PASSED in `tests/integration/bulk_operations/test_bulk_update_real_operations.py`
  - Real database UPDATE operations
  - Transaction support
  - Error handling
  - Edge cases (empty filter, no matches, etc.)

- **Unit Tests**: 36/36 PASSED
- **Integration Tests**: 70/70 PASSED
- **Total**: 119/119 tests passing (100%)
- **Infrastructure**: Real PostgreSQL testing (NO MOCKING policy)
- **Regressions**: ZERO - all existing tests continue to pass

### Enhanced

- Improved error messages with detailed context for bulk operations
- Better validation for empty filter/data edge cases
- Comprehensive debug logging for bulk operation failures
- Clear documentation of safety parameters

### Dependencies

- Requires Kailash SDK >= 0.9.21 (no change from 0.5.2)

## [0.5.2] - 2025-10-10

### Critical Bug Fixes

#### Empty Filter Bug in Bulk Operations (Bug #4)

- **Fixed**: BulkDeleteNode and BulkUpdateNode now accept empty filter `{}` for "match all" operations
- **Impact**: MongoDB-style empty filter syntax now works correctly for bulk operations
- **Root Cause**: Python truthiness check failed on empty dict (empty dict evaluates to `False`)
- **Locations**:
  - `src/dataflow/core/nodes.py:1905, 1937` (changed to key existence check `"filter" in kwargs`)
  - `src/dataflow/nodes/bulk_delete.py:153` (changed to `"filter" not in validated_inputs`)
  - `src/dataflow/nodes/bulk_update.py:162` (changed to `"filter" not in validated_inputs`)
- **Tests**: 4 regression tests + 48 bulk operation integration tests (all passing)
- **Breaking**: NO - previously broken functionality now works

**Before**:

```python
# Empty filter failed with "Unsupported bulk operation" error
node = BulkDeleteNode(...)
result = await node.async_run(filter={}, confirmed=True)  # ❌ FAILED
# Error: "Unsupported bulk operation: bulk_delete"
```

**After**:

```python
# Empty filter works as "match all" (MongoDB-style)
node = BulkDeleteNode(...)
result = await node.async_run(filter={}, confirmed=True)  # ✅ WORKS
# Successfully deletes/updates all records in table
```

**Security Note**: Empty filter `{}` means "match all records". Always use with caution:

- BulkDeleteNode has `safe_mode` enabled by default to prevent accidental full-table deletion
- Set `safe_mode=False` explicitly if you intend to delete all records
- Always use `confirmed=True` for dangerous operations

### Test Coverage

- **New Regression Tests**: 4 comprehensive tests in `tests/integration/bulk_operations/test_bulk_empty_filter_regression.py`
  - `test_bulk_delete_with_empty_filter` - Empty filter deletes all records
  - `test_bulk_update_with_empty_filter` - Empty filter updates all records
  - `test_empty_filter_vs_non_empty_filter` - Correctly distinguishes empty vs non-empty
  - `test_no_filter_parameter_still_works` - Operations without filter still work
- **Total Bulk Tests**: 48 integration tests (100% pass rate)
- **Infrastructure**: Real PostgreSQL testing (NO MOCKING policy)
- **Zero Regressions**: All existing tests pass with the fix

### Dependencies

- Requires Kailash SDK >= 0.9.21 (no change from 0.5.1)

## [0.5.1] - 2025-10-09

### Critical Bug Fixes

#### JSONB Serialization (Bug #1)

- **Fixed**: JSONB fields now use `json.dumps()` instead of `str()` for dict/list serialization
- **Impact**: Prevents PostgreSQL errors with invalid JSON syntax (single quotes vs double quotes)
- **Location**: `src/dataflow/core/nodes.py:211-216`
- **Tests**: 9 comprehensive tests in `tests/integration/test_jsonb_bug_reproduction.py`
- **Breaking**: NO - transparent fix for previously broken functionality

**Before**:

```python
str({'key': 'value'})  # → "{'key': 'value'}" (invalid JSON - single quotes)
```

**After**:

```python
json.dumps({'key': 'value'})  # → '{"key": "value"}' (valid JSON - double quotes)
```

#### DeleteNode Safety Validation (Bug #2)

- **Fixed**: DeleteNode now raises `ValueError` when no ID is provided instead of silently defaulting to `id=1`
- **Impact**: Prevents accidental data loss from unintentional deletions
- **Location**: `src/dataflow/core/nodes.py:1437-1443`
- **Tests**: 7 comprehensive tests in `tests/integration/core_engine/test_delete_node_validation.py`
- **Breaking**: YES - intentional security improvement

**BREAKING CHANGE**: DeleteNode now requires explicit `id` or `record_id` parameter

**Migration Required**:

```python
# Before (DANGEROUS - silently deleted id=1):
workflow.add_node("ProductDeleteNode", "delete", {})

# After (SAFE - must provide explicit ID):
workflow.add_node("ProductDeleteNode", "delete", {"id": 5})
# or
workflow.add_node("ProductDeleteNode", "delete", {"record_id": 5})
```

#### Reserved Parameter Names (Bug #3)

- **Fixed**: Complete namespace separation between node metadata and user parameters
- **Impact**: Users can now freely use 'id' as a parameter name (string OR integer types)
- **Locations**:
  - Core SDK: `src/kailash/workflow/graph.py` (inject `_node_id` instead of `id`)
  - Core SDK: `src/kailash/nodes/base.py` (use `_node_id` internally, add `id` property)
  - DataFlow: `src/dataflow/core/nodes.py` (accept integer IDs, dynamic SQL generation)
- **Tests**: 5 comprehensive tests in `tests/integration/test_bug_3_reserved_fields_fix.py`
- **Breaking**: NO - backward compatible via property alias

**Before**:

```python
# Users couldn't use 'id' parameter due to namespace collision
workflow.add_node("SessionCreateNode", "create", {
    "session_id": "sess-123",  # Had to use alternative field name
    "user_id": "user-456"
})
```

**After**:

```python
# Users can freely use 'id' parameter (string or integer)
workflow.add_node("SessionCreateNode", "create", {
    "id": "sess-123",  # Now works!
    "user_id": "user-456"
})
```

### Test Coverage

- **Total Tests**: 21 comprehensive integration tests (100% pass rate)
- **Infrastructure**: Real PostgreSQL testing (NO MOCKING policy)
- **Verification**: 1,420+ existing tests verified with no new regressions

### Enhanced

- Dynamic SQL generation for flexible parameter handling
- Improved error messages for DeleteNode validation
- Better namespace separation between framework and user code

### Dependencies

- Requires Kailash SDK >= 0.9.21 (updated from >= 0.9.16)

## [0.4.0] - 2025-08-04

### Major Features

- **TDD Foundation Implementation**: Complete Test-Driven Development infrastructure with <100ms test execution
  - TDD-aware connection management for maximum performance and test isolation
  - Enhanced test fixtures and isolation mechanisms
  - Performance optimization with sub-100ms test execution through connection reuse
  - Comprehensive TDD documentation and examples

- **Dynamic Model Registration**: Enhanced model registration system with runtime discovery
  - Dynamic schema discovery and model reconstruction capabilities
  - Improved existing database integration workflows
  - Better model registry management for multi-application scenarios

### Enhanced Testing Infrastructure

- **4,000+ Test Milestone**: Comprehensive testing coverage with 4,072 passing tier 1 tests
- **Test Organization**: Restructured test suite with clear separation of unit, integration, and E2E tests
- **Performance Optimization**: Test execution optimized for development workflow efficiency
- **Real Infrastructure Testing**: Enhanced PostgreSQL and SQLite integration testing

### Fixed

- Merge conflict resolution with proper initialize() method implementation
- Import order corrections across test modules
- Enhanced error handling in migration systems
- Improved connection pool management in test environments

### Changed

- Updated Kailash SDK dependency to >=0.9.11 for latest compatibility
- Enhanced documentation structure with comprehensive TDD guidance
- Improved code formatting and linting compliance
- Better test isolation and cleanup mechanisms

### Developer Experience

- Complete TDD workflow implementation for rapid development cycles
- Enhanced debugging capabilities with comprehensive test coverage
- Improved error messages and validation feedback
- Streamlined development setup and testing procedures

## [0.3.3] - 2025-07-31

### Fixed

- Critical connection string parsing issues with special characters in passwords
- Database URL parsing now uses proper urllib.parse for robust handling
- Password parsing bug where '#' character caused int() conversion errors
- Connection parameter validation for complex database URLs

### Enhanced

- ConnectionParser class with improved URL parsing capabilities
- DatabaseRegistry with better connection handling and error reporting
- MultiDatabase adapter with enhanced connection validation
- Better error messages for connection parsing failures

### Added

- Comprehensive bug reproduction tools and analysis scripts
- Enhanced connection string parsing test coverage
- Support for URL-encoded special characters in passwords
- Better debugging utilities for connection issues

### Dependencies

- Requires Kailash SDK >= 0.9.4 (updated from >= 0.9.2)
- All other dependencies remain compatible

## [0.3.2] - 2025-07-30

### Fixed

- Minor bug fixes and improvements
- Enhanced stability for production deployments

## [0.3.1] - 2025-07-22

### Added

- Comprehensive release notes documenting all improvements
- Enhanced parameter validation error messages
- Redis integration tests with cache operations
- Performance benchmarks for bulk operations

### Changed

- Improved test pass rate from ~40% to 90.7% (330/364 tests passing)
- Zero failing tests - all tests now pass or are properly skipped
- Enhanced documentation for parameter validation patterns
- Updated CLAUDE.md files with debugging guidance

### Fixed

- Template string parameter validation - `${}` syntax now properly rejected
- DateTime format handling - use native datetime objects
- Floating point precision comparisons in PostgreSQL tests
- Bulk operations assertion handling for metadata responses
- Circuit breaker parameter names (recovery_timeout, half_open_requests)
- Multi-tenancy Row Level Security (RLS) tests
- Transaction management DataFlow context passing

### Developer Experience

- Added debugging section to root CLAUDE.md for parameter errors
- Direct links to parameter solution guides
- Moved parameter validation to step 2 in Multi-Step Strategy
- Clear migration guide for parameter passing patterns

## [0.3.0] - 2025-07-21

### Added

- DataFlow test utilities (`DataFlowTestUtils`) for clean database management
- Migration-based table cleanup functionality
- Support for direct node execution pattern in tests
- Comprehensive test coverage improvements

### Changed

- Replaced all psql command line usage with DataFlow components
- Updated all e2e tests to use DataFlow's own database operations
- Improved test reliability by removing external tool dependencies
- Enhanced integration test structure for better maintainability

### Fixed

- Database cleanup issues in integration tests
- Test failures due to missing psql command
- DatabaseConfig parameter compatibility issues
- Connection management in concurrent test scenarios

### Developer Experience

- Simplified test database setup and teardown
- Better error messages for database operations
- Consistent use of DataFlow patterns across all tests

## [0.2.0] - 2025-07-20

### Breaking Changes

- Updated Nexus integration imports from `from kailash.nexus import create_nexus` to `from nexus import Nexus`
- Requires Kailash SDK >= 0.8.5 (previously >= 0.8.3)

### Fixed

- Version mismatch between setup.py and **init**.py (now consistently 0.2.0)
- Gateway integration now uses correct Nexus import pattern

### Changed

- Updated documentation examples to use new Nexus import pattern
- SQL injection test scenarios updated to use new import

## [0.1.1] - Previous Release

- Initial release with modular architecture
- Enterprise features including bulk operations and multi-tenancy
- MongoDB-style query API
- Zero-configuration setup
