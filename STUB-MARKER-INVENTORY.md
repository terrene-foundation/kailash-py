# Stub-Marker Inventory — `kailash` core (`src/kailash`)

Resolves GitHub issue **#1406** — _"Package is classified Production/Stable yet
carries stub markers in `src/` with no documented inventory of which surfaces are
incomplete."_

The `kailash` distribution is published `Development Status :: 5 - Production/Stable`
(`pyproject.toml:16`). That classifier is a promise that the public surface is
complete and supported. This file is the auditable inventory that backs the promise:
every stub marker in `src/kailash` is enumerated and categorised so a consumer can
tell a **contractual sentinel** (intentional, e.g. an abstract method) from a
**genuine gap** (a capability not yet implemented).

A CI guard (`tests/unit/test_stub_marker_inventory.py`) pins the per-file marker
counts to the machine-readable baseline at the bottom of this file, so the marker
population **cannot grow (or shrink) silently** without this inventory being updated
in the same change.

---

## Scope & canonical marker definition

- **Scope:** `src/kailash/**/*.py` only — the `kailash` core distribution that
  `pyproject.toml:16` classifies Production/Stable. Sub-packages under
  `packages/*/src` (DataFlow, Nexus, Kaizen, PACT, ML, Align) have their **own**
  `pyproject.toml` classifiers and are out of scope for this inventory.
- **Canonical regex** (lines-with-a-match, identical under `grep -E` and Python `re`):

  ```
  \b(TODO|FIXME|HACK|STUB|XXX)\b|NotImplementedError
  ```

  This is the marker set named in issue #1406 (`TODO`/`FIXME`/`HACK`/`XXX`/
  `NotImplementedError`), plus `STUB` from `zero-tolerance.md` Rule 2. `FIXME`,
  `HACK`, and `STUB` currently have **zero** hits.

### Reconciliation with the "~213" figure

Issue #1406 cites _"213 stub-markers in src"_ from `SWEEP-2026-06-15-post-2.34.2.md`
(Sweep row 7). That figure counted the **entire `src` + `packages/*/src` tree**
(206 today) — the whole monorepo, not the `kailash` core — **and is inflated by
false positives** the naive grep cannot distinguish (`ADR-XXX` doc placeholders,
`KS-XXX`/`DF-XXX` error-code format strings, an `XXX-XX-6789` SSN-mask literal).
That undifferentiated count is exactly the "unauditable" problem #1406 raises.

Scoped to the `kailash` core and categorised, the real picture is:

| Metric                                                  | Count |
| ------------------------------------------------------- | ----- |
| Files with ≥1 marker (`src/kailash`)                    | 38    |
| Total marker lines                                      | 66    |
| — false-positive (not a real marker)                    | 31    |
| — sentinel (intentional contract)                       | 24    |
| — gap (genuine deferred work)                           | 11    |
| — tracked (deferred + issue-linked)                     | 0     |
| **Genuine gaps reachable from a documented public API** | **4** |

---

## Category definitions

- **false_positive** — the matched token is **not** an incompleteness marker:
  docstring prose describing behaviour (`Raises: NotImplementedError`,
  `:class:\`NotImplementedError\``), exception **handling** (`except NotImplementedError:`),
the exception **registry** entry (`"NotImplementedError": NotImplementedError`),
ID/format placeholders (`ADR-XXX`, `KS-XXX`, `DF-XXX`), a data-mask literal
(`XXX-XX-6789`), or **template-generator output** — a string the SDK *emits into
generated user code* (`utils/templates.py`, `utils/migrations/generator.py`). The
SDK itself is complete; the `TODO`/`NotImplementedError` lives in the scaffold
  produced _for the user_ to fill in.
- **sentinel** — an **intentional** contractual marker in real SDK code: an abstract
  / base method, typed-node guard, or transport base that raises `NotImplementedError`
  **by design** to force a subclass / async variant / concrete runtime to implement
  it. The contract is complete; the raise _is_ the contract.
- **gap** — a genuine unimplemented feature / deferred work with no tracking link,
  where the marker means the SDK does not (yet) do something a consumer might
  reasonably expect.
- **tracked** — a real deferred item already linked to a tracking issue / ADR.

---

## Genuine gaps (category `gap`) — the load-bearing findings

`public` = reachable from a documented public API (a stub a consumer can hit matters
more than an internal one).

| #   | Location                                         | Marker                                                                                         | public  | Disposition        | Note                                                                                                                                                                      |
| --- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------- | :-----: | ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `nodes/edge/edge_monitoring_node.py:359`         | `# TODO: proper active check`                                                                  | **yes** | implement          | `[a for a in alerts if active_only or True]` — the `or True` makes the filter a no-op, so `active_count` **always equals the total alert count**. Latent correctness bug. |
| 2   | `nodes/api/rest.py:433`                          | `# max_pages = ... # TODO: Implement max pages limit`                                          | **yes** | implement / remove | `max_pages` pagination cap is commented out, so the param is silently ignored — a caller passing `max_pages` gets no effect (over-fetch risk).                            |
| 3   | `nodes/monitoring/performance_benchmark.py:2155` | `raise NotImplementedError("Anomaly detector training requires a machine learning library …")` | **yes** | track              | The anomaly-detection benchmark path raises; needs an ML dependency to implement.                                                                                         |
| 4   | `cli/validate_imports.py:118`                    | `# TODO: Add support for include_tests flag in validator`                                      | **yes** | track              | The `--include-tests` CLI flag is parsed and printed but never passed to `validate_directory()` (`zero-tolerance` Rule 3c).                                               |
| 5   | `nodes/monitoring/deadlock_detector.py:919`      | `# TODO: Send alerts or take automatic resolution actions`                                     |   no    | track              | Deadlocks are detected and recorded; alerting / auto-resolution is deferred (enhancement, not a broken contract).                                                         |
| 6   | `middleware/communication/events.py:210`         | `# TODO: Replace with BatchProcessorNode for production use`                                   |   no    | track              | `EventBatch` is deprecated (emits a `DeprecationWarning`); replacement deferred.                                                                                          |
| 7   | `middleware/communication/events.py:279`         | `# TODO: Add CacheNode when available for event history`                                       |   no    | track              | Depends on a node that does not yet exist.                                                                                                                                |
| 8   | `middleware/communication/events.py:280`         | `# TODO: Add AsyncQueueNode when available for event buffering`                                |   no    | track              | Depends on a node that does not yet exist.                                                                                                                                |
| 9   | `middleware/communication/events.py:281`         | `# TODO: Add MetricsCollectorNode when available for performance tracking`                     |   no    | track              | Depends on a node that does not yet exist.                                                                                                                                |
| 10  | `nodes/data/bulk_operations.py:269`              | `# TODO: Implement COPY FROM for maximum performance`                                          |   no    | track              | Performance optimisation only — functionally complete via the multi-row-`INSERT` fallback directly below it.                                                              |
| 11  | `runtime/parallel_cyclic.py:224`                 | `# TODO: Add cycle-aware parallel execution optimizations`                                     |   no    | track              | Performance optimisation; the path executes correctly without it.                                                                                                         |

**Resolved:** the two former gaps #1/#2 (`nodes/data/async_sql.py:1268,1319` —
`FetchMode.ITERATOR`) are closed. `FetchMode.ITERATOR` was a category error (a lazy
async stream cannot be a materializing fetch _return value_); it never produced a
working result (raised on PostgreSQL, returned `None`/`[]` on MySQL/SQLite). The enum
member is removed, the silent MySQL/SQLite fallbacks now raise a typed `ValueError`,
and a dedicated memory-bounded `stream()` API replaces the streaming use case
(follow-up workstream). This drops the gap count 13 → 11 and the public-reachable
gap count 6 → 4.

**Recommended follow-ups (highest value first):** #1 (`edge_monitoring`
active-count bug) is the only remaining entry that alters or blocks observable
behaviour on a public surface; #2 and #4 are silently-ignored public params; the
remainder are enhancements/perf with a working code path.

---

## Sentinels (category `sentinel`) — intentional, no action

These raise `NotImplementedError` **by contract** (abstract method / typed-node guard
/ transport base). They are correct as-is; a consumer reaches them only by subclassing
a base without implementing the required method, or by calling a deliberately
unsupported operation, and the error message names the fix.

| Location                                   | Contract                                                                               |
| ------------------------------------------ | -------------------------------------------------------------------------------------- |
| `nodes/base_async.py:190`, `:210`          | `AsyncNode.run()` guard — async nodes must implement `async_run()`.                    |
| `nodes/base.py:2056`                       | `AsyncTypedNode.run()` guard — must implement `async_run()`.                           |
| `nodes/base_with_acl.py:147`, `:258`       | Access-controlled node must implement `_execute()`.                                    |
| `runtime/base.py:940`                      | `BaseRuntime.execute()` — implemented by `LocalRuntime` / `AsyncLocalRuntime`.         |
| `delegate/dispatch.py:643`                 | Abstract connector primitive (`# pragma: no cover (abstract)`).                        |
| `delegate/dispatch.py:769`                 | Guard for legacy `invoke()`-only connectors — directs to `connector.invoke(...)`.      |
| `utils/migrations/models.py:196`           | Abstract template method — "Override in subclasses".                                   |
| `nodes/edge/edge_data.py:564`, `:574`      | Strong-consistency / primary-refresh need an inter-edge transport (subclass supplies). |
| `nodes/edge/edge_warming_node.py:348`      | Edge warming needs infrastructure integration (subclass supplies).                     |
| `nodes/edge/edge_state.py:622`             | State replication needs an edge transport (subclass supplies).                         |
| `edge/consistency.py:214`, `:241`          | 2PC prepare / abort need a replica transport (subclass supplies).                      |
| `edge/prediction/predictive_warmer.py:524` | Edge warming needs infrastructure integration (subclass supplies).                     |
| `workflow/convergence.py:28`               | Abstract `ConvergenceCondition.should_terminate()`.                                    |
| `trust/audit_service.py:488`               | Guard — `get_unattested_reasoning()` requires a store with `list_records()`.           |
| `trust/plane/conformance/__init__.py:602`  | Dispatch guard for a conformance test name with no `_test_<name>` method.              |
| `trust/pact/stores/sqlite.py:176`          | Abstract `_create_tables()` — "Override in subclasses".                                |
| `channels/mcp/http.py:130`                 | `HttpTransport.receive()` — HTTP is request/response only (documented design).         |
| `channels/mcp/base.py:80`, `:99`, `:108`   | Abstract `Transport` base — `send` / `receive` / `close`.                              |

---

## False positives (category `false_positive`) — not markers

Documented so the count is complete and the guard's raw hits are explained.

| Location(s)                                                                                                                                                                                                   | Why it is not a marker                                                                                                                                                                                       |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `nodes/base_async.py:188`, `:198`; `nodes/base.py:2054`; `runtime/base.py:912`; `runtime/mixins/conditional_execution.py:1081`, `:1104`, `:1134`; `channels/mcp/http.py:20`; `channels/mcp/base.py:89`, `:96` | Docstring prose (`Raises: NotImplementedError`, `:class:\`NotImplementedError\``) describing a sentinel that lives elsewhere. (`conditional_execution`bodies are`pass` — mixin hooks the runtime overrides.) |
| `runtime/shutdown.py:206`; `trust/envelope.py:1505`; `trust/signing/rotation.py:592`                                                                                                                          | `except NotImplementedError:` — handling a raise, not making one (e.g. Windows `add_signal_handler` fallback).                                                                                               |
| `runtime/local.py:143`                                                                                                                                                                                        | `"NotImplementedError": NotImplementedError` — entry in the exception-name registry.                                                                                                                         |
| `delegate/trust.py:140`                                                                                                                                                                                       | A `#` comment describing CPython's `secrets.token_bytes` fallback chain.                                                                                                                                     |
| `runtime/base.py:6`, `:57`, `:141`; `runtime/mixins/parameters.py:82`; `runtime/mixins/validation.py:73`                                                                                                      | `ADR-XXX` — placeholder ADR reference in module docstrings.                                                                                                                                                  |
| `runtime/validation/core_error_enhancer.py:4`, `:42`; `runtime/validation/base_error_enhancer.py:12`, `:13`                                                                                                   | `KS-XXX` / `DF-XXX` — error-code **format** strings in docstrings.                                                                                                                                           |
| `nodes/compliance/gdpr.py:1748`                                                                                                                                                                               | `"XXX-XX-6789"` — an anonymised-SSN **mask literal**.                                                                                                                                                        |
| `utils/templates.py:145`, `:153`                                                                                                                                                                              | The node-template generator **emits** `# TODO: Implement node logic` / `# TODO: Set <param>` **into the user's generated node** — scaffold output, not an SDK stub.                                          |
| `utils/migrations/generator.py:121`, `:122`, `:126`, `:127`                                                                                                                                                   | The migration generator **emits** a `forward`/`backward` template that raises `NotImplementedError` **into the user's generated migration** — scaffold output, not an SDK stub.                              |

---

## How to keep this inventory honest

1. The CI guard `tests/unit/test_stub_marker_inventory.py` runs in the default unit
   lane and asserts the **per-file** marker counts equal the baseline below.
2. When you add or remove a marker in `src/kailash`, the guard fails. Resolve it by:
   - adding/removing the marker's row in the tables above (with its category +
     public-reachability + disposition), **and**
   - updating the per-file count + tally in the baseline block below.
3. Regenerate the per-file map mechanically:
   ```bash
   grep -rIlE '\b(TODO|FIXME|HACK|STUB|XXX)\b|NotImplementedError' src/kailash --include='*.py' \
     | sort | while read -r f; do printf '%s %s\n' "$(grep -cE '\b(TODO|FIXME|HACK|STUB|XXX)\b|NotImplementedError' "$f")" "$f"; done
   ```

<!-- STUB-MARKER-BASELINE-JSON
{
  "scope": "src/kailash",
  "regex": "\\b(TODO|FIXME|HACK|STUB|XXX)\\b|NotImplementedError",
  "total": 66,
  "category_tally": {
    "false_positive": 31,
    "sentinel": 24,
    "gap": 11,
    "tracked": 0
  },
  "public_reachable_gaps": 4,
  "per_file": {
    "src/kailash/channels/mcp/base.py": 5,
    "src/kailash/channels/mcp/http.py": 2,
    "src/kailash/cli/validate_imports.py": 1,
    "src/kailash/delegate/dispatch.py": 2,
    "src/kailash/delegate/trust.py": 1,
    "src/kailash/edge/consistency.py": 2,
    "src/kailash/edge/prediction/predictive_warmer.py": 1,
    "src/kailash/middleware/communication/events.py": 4,
    "src/kailash/nodes/api/rest.py": 1,
    "src/kailash/nodes/base.py": 2,
    "src/kailash/nodes/base_async.py": 4,
    "src/kailash/nodes/base_with_acl.py": 2,
    "src/kailash/nodes/compliance/gdpr.py": 1,
    "src/kailash/nodes/data/bulk_operations.py": 1,
    "src/kailash/nodes/edge/edge_data.py": 2,
    "src/kailash/nodes/edge/edge_monitoring_node.py": 1,
    "src/kailash/nodes/edge/edge_state.py": 1,
    "src/kailash/nodes/edge/edge_warming_node.py": 1,
    "src/kailash/nodes/monitoring/deadlock_detector.py": 1,
    "src/kailash/nodes/monitoring/performance_benchmark.py": 1,
    "src/kailash/runtime/base.py": 5,
    "src/kailash/runtime/local.py": 1,
    "src/kailash/runtime/mixins/conditional_execution.py": 3,
    "src/kailash/runtime/mixins/parameters.py": 1,
    "src/kailash/runtime/mixins/validation.py": 1,
    "src/kailash/runtime/parallel_cyclic.py": 1,
    "src/kailash/runtime/shutdown.py": 1,
    "src/kailash/runtime/validation/base_error_enhancer.py": 2,
    "src/kailash/runtime/validation/core_error_enhancer.py": 2,
    "src/kailash/trust/audit_service.py": 1,
    "src/kailash/trust/envelope.py": 1,
    "src/kailash/trust/pact/stores/sqlite.py": 1,
    "src/kailash/trust/plane/conformance/__init__.py": 1,
    "src/kailash/trust/signing/rotation.py": 1,
    "src/kailash/utils/migrations/generator.py": 4,
    "src/kailash/utils/migrations/models.py": 1,
    "src/kailash/utils/templates.py": 2,
    "src/kailash/workflow/convergence.py": 1
  }
}
STUB-MARKER-BASELINE-JSON -->
