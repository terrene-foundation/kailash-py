# 0007 — DECISION — S-EV: test_dataflow_events.py diagnosed + fixed

**Date:** 2026-05-14
**Shard:** S-EV (Workstream-A, briefs/00-brief.md:41-42 AC#2)
**Branch:** `feat/issue-979-s-ev-dataflow-events`
**Disposition:** Branch A (real bug, fix shipped). Layer-2 OOM hypothesis from journal/0001 was wrong.

## Verdict

The brief's "4+ test failures from PR #976 investigation" claim was **TRUE** — 5 of 11 tests in `packages/kailash-dataflow/tests/unit/features/test_dataflow_events.py` failed in clean-venv reproduction. The journal/0001 hypothesis "Branch B (no reproduction) most likely" was incorrect.

Failure receipt (clean venv `/tmp/s-ev-verify`, pre-fix):

```
$ /tmp/s-ev-verify/bin/pytest packages/kailash-dataflow/tests/unit/features/test_dataflow_events.py -v
...
FAILED test_init_events_creates_bus              — assert None is not None
FAILED test_emit_publishes_domain_event_with_payload — AttributeError: 'NoneType' object has no attribute 'subscribe'
FAILED test_emit_correct_field_name_is_payload   — AttributeError: 'NoneType' object has no attribute 'subscribe'
FAILED test_subscribes_all_8_write_operations    — AttributeError: 'NoneType' object has no attribute 'subscribe'
FAILED test_on_model_change_receives_events      — AttributeError: 'NoneType' object has no attribute 'subscribe'
=========================== 5 failed, 6 passed ==========================
```

## Root Cause

`DataFlowEventMixin._init_events` (`packages/kailash-dataflow/src/dataflow/core/events.py:56`) imports `kailash.middleware.communication.backends.memory.InMemoryEventBus`. Python's import machinery runs `kailash.middleware/__init__.py` which eagerly imports:

- `kailash.nodes.admin.user_management` → requires `bcrypt` (from `kailash[server]`)
- `kailash.middleware.communication.api_gateway` → requires `fastapi` + `uvicorn` (from `kailash[server]`)

`kailash-dataflow[dev]` did NOT declare `kailash[server]`. Clean-venv install → `ImportError` → `_init_events` silently sets `_event_bus = None` → downstream `subscribe(...)` calls produce opaque `AttributeError: NoneType.subscribe`.

This is a zero-tolerance Rule 3a violation — "Typed Delegate Guards For None Backing Objects."

## Fix (two layers)

**Layer 1 — Code (`packages/kailash-dataflow/src/dataflow/core/events.py`):**
- `_init_events` now records the `ImportError` into `_event_bus_import_error` (class-level default `None`).
- `on_model_change` raises typed `DataFlowError` citing the `kailash[server]` extra when `_event_bus is None` — replaces opaque `AttributeError`.
- `_emit_write_event`'s existing `_event_bus is None` early-return is preserved (documented no-op contract; see `test_emit_when_bus_is_none`).

**Layer 2 — Dep declaration (`packages/kailash-dataflow/pyproject.toml`):**
- Added `kailash[server]` to `[dev]` extras alongside `aiosqlite` and `pytest-timeout` — same "tier-1 collection requires extra not installed" pattern PR #976 established.

**Regression test (`packages/kailash-dataflow/tests/regression/test_issue_979_s_ev_dataflow_events.py`):**
- 3 tests covering: (a) `[dev]` pin presence via `tomllib` parse, (b) `_event_bus_import_error` class attribute exists, (c) `on_model_change` raises `DataFlowError` citing `kailash[server]` when `_event_bus is None`.

## Verification

```
$ /tmp/s-ev-cleanverify/bin/pytest \
    packages/kailash-dataflow/tests/unit/features/test_dataflow_events.py \
    packages/kailash-dataflow/tests/regression/test_issue_979_s_ev_dataflow_events.py -v
...
============================== 14 passed in 1.70s ==============================
```

Fresh `/tmp/s-ev-cleanverify` venv with ONLY `pip install -e packages/kailash-dataflow[dev]` (no manual bcrypt/fastapi). All 11 original tests + 3 new regression tests green.

## Capacity Budget

- LOC: ~80 (events.py ~40, pyproject.toml ~14, regression test ~120 — well under 200 budget)
- Invariants: 3 (Rule 3a typed guard, dep declared = imported, regression coverage)
- Call-graph hops: 2 (`_init_events` ↔ `on_model_change` ↔ user-facing surface)

Within shard budget. No decomposition needed.

## Files Changed

```
packages/kailash-dataflow/src/dataflow/core/events.py            (+40, -3)
packages/kailash-dataflow/pyproject.toml                          (+14)
packages/kailash-dataflow/tests/regression/test_issue_979_s_ev_dataflow_events.py  (+120, new)
workspaces/issue-979-dataflow-unit-triage/journal/0007-DECISION-s-ev-resolution.md  (this file)
```

## Cross-References

- Brief AC#2: `briefs/00-brief.md:41-42`
- Plan source: `workspaces/issue-979-dataflow-unit-triage/02-plans/02-amendments-v2-post-redteam-r1r2.md` § S-EV
- Prior assumption (corrected): `journal/0001-DISCOVERY-brief-verification.md:96-126` Layer 5
- Pattern reference: `rules/zero-tolerance.md` Rule 3a (Typed Delegate Guards)
- Pattern reference: `rules/dependencies.md` § Declared = Imported
- Sibling pattern: existing `[dev]` pins for `pytest-timeout` + `aiosqlite` (S1 / PR #976)
