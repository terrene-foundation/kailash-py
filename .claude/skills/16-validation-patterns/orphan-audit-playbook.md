# Orphan Audit Playbook

Detailed audit protocols and extended evidence backing `rules/orphan-detection.md`. The rule holds the load-bearing MUST clauses; this file holds the step-by-step playbooks agents can execute during `/redteam` and `/codify` cycles.

Cf. the spec-drift-gate at `specs/spec-drift-gate.md` for the executable form of FR-6 (`__getattr__` resolution) + FR-7 (test-path existence) sweeps; the gate productionizes the manual checks below at PR time via `scripts/spec_drift_gate.py`.

## Detection Protocol

Run this 5-step protocol during `/redteam` against every class exposed on the public surface:

1. **Surface scan** — list every property, method, and attribute on the framework's top-level class that returns a `*Manager` / `*Executor` / `*Store` / `*Registry` / `*Engine` / `*Service`.
2. **Hot-path grep** — for each candidate, grep the framework's source (NOT tests, NOT downstream consumers) for calls into the class's methods. Zero matches in the hot path = orphan.
3. **Tier 2 grep** — for each non-orphan, grep `tests/integration/` and `tests/e2e/` for the class name. Zero matches = unverified wiring.
4. **Collect-only sweep** — run `.venv/bin/python -m pytest --collect-only tests/ packages/*/tests/`. Every `ERROR <path>` / `ModuleNotFoundError` / `ImportError` at collection is a test-orphan. Disposition: delete the orphan test file (if the API is gone) or port its imports (if the API moved).
5. **Disposition** — every orphan and every unverified wiring MUST be either fixed (wire + test) or deleted (remove from public surface).

## Sub-Package Collection-Gate Patterns (Rule §5a)

Rule 5 mandates `pytest --collect-only` as a merge gate. Rule 5a clarifies: in monorepos with sub-package test-only deps (e.g. `hypothesis` in pact, `respx` in kaizen), the gate passes per-package, NOT combined.

### Why combined invocation fails

`python-environment.md` Rule 4 blocks sub-package test deps from root `[dev]` because plugins like `hypothesis` register as pytest plugins and trigger a `MemoryError` during AST rewrite on large monorepo suites. So the root venv cannot satisfy sub-package test deps; `pytest --collect-only tests/ packages/*/tests/` from the root venv fails with three classes of error:

- `ModuleNotFoundError: hypothesis` (pact tests)
- `ModuleNotFoundError: respx` (kaizen tests)
- `ImportPathMismatchError` (two `conftest.py` files both register as `tests.conftest`)

### Correct invocation — per-package iteration

```bash
# Install each sub-package's [dev] extras first
for pkg in packages/*/; do
  if [ -f "$pkg/pyproject.toml" ]; then
    uv pip install -e "$pkg[dev]" --python .venv/bin/python
  fi
done

# Then collect per-package
for pkg in packages/*/tests; do
  .venv/bin/python -m pytest --collect-only -q "$pkg" --continue-on-collection-errors
done
```

Each sub-package collects against its own declared test deps. No collision with `python-environment.md` Rule 4.

### Origin

Session 2026-04-20 `/redteam` collection-gate work. Combined root-venv invocation failed with 3 distinct root causes; per-package iteration after installing `packages/<pkg>[dev]` succeeded for all 9 sub-packages. See `workspaces/kailash-ml-gpu-stack/journal/0008-GAP-full-specs-redteam-2026-04-20-findings.md`.

## Extended Evidence By Rule

### §1 — Facade production call site (Phase 5.11 orphan)

kailash-py Phase 5.11 surfaced 2,407 LOC of trust integration code (`TrustAwareQueryExecutor`, `DataFlowAuditStore`, `TenantTrustManager`) instantiated and exposed as `db.trust_executor` / `db.audit_store` / `db.trust_manager`. Four downstream workspaces imported the classes. Zero production code paths invoked any method on them. Operators believed the trust plane was running for an unknown period; it was not.

The fix was a one-session wiring sweep that added `await self._db.trust_executor.check_read_access(...)` calls to `DataFlowExpress.read` / `.list` / `.create` / `.update` / `.delete`.

### §2a — Crypto-pair round-trip orphan pattern

Crypto wrappers that expose paired operations (`encrypt`/`decrypt`, `sign`/`verify`, `seal`/`unseal`, `wrap_key`/`unwrap_key`) have the same "framework never round-trips" failure mode as manager classes. If `encrypt()` is tested in isolation and `decrypt()` is tested in isolation, the pair can drift — `encrypt` uses AES-256-GCM while `decrypt` uses AES-256-CBC, or `sign` uses SHA-256 while `verify` uses SHA-1 — and both unit tests still pass because each test mocks the other half.

**Defense:** Tier 2 round-trip test through the facade: call `encrypt()`, feed output to `decrypt()`, assert plaintext equality. No amount of Tier 1 coverage catches "encrypt uses GCM, decrypt uses CBC".

### §4a — Stub-implementation deferral-test sweep (Session 2026-04-20)

kailash-ml 0.13.0 release (PR #552) landed real `km.track()` implementation for issue #548, replacing the `NotImplementedError` stub. The scaffold-era test at `packages/kailash-ml/tests/unit/test_mlengine_construction.py::TestMLEngineDeferredBodies::test_km_track_deferral_names_phase` continued to call `track()` inside `pytest.raises(NotImplementedError)` and blocked CI on every Python 3.10/3.11/3.12/3.13/3.14 base job simultaneously.

Fix: `release/kailash-ml-0.13.0` commit `ef8751c5` deleted the deferral test. Cost: one extra CI cycle + one follow-up commit at the worst possible moment (release gate).

**Implementation-author checklist:** before committing the stub→real-impl edit, run:

```bash
# Find paired deferral tests for the symbol being un-deferred
grep -rln 'NotImplementedError.*<symbol>\|<symbol>.*deferral' tests/
```

Catches the orphan in O(seconds) instead of O(minutes + CI cycle).

### §6 — `__all__` public-import contract (PR #523 / #529)

PR #523 (kailash-ml 0.11.0) eagerly imported `DeviceReport` / `device_report_from_backend_info` / `device` / `use_device` at module scope in `src/kailash_ml/__init__.py` but omitted all four from `__all__`. Caught by post-release reviewer; patched in PR #529 (kailash-ml 0.11.1).

**Why this matters:** `__all__` is the package's public-API contract. Documentation generators (Sphinx autodoc), linters, typing tools (`mypy --strict`), and `from pkg import *` consumers all read it as the canonical export list. A symbol that's eagerly imported but absent from `__all__` is both advertised (via the import) AND hidden (via `__all__`) — the exact inconsistency the orphan pattern produces on the consumer side.

## Related

- `rules/orphan-detection.md` — load-bearing MUST clauses
- `rules/facade-manager-detection.md` — narrower rule for the `*Manager` / `*Executor` / `*Store` / etc. naming pattern specifically
- `skills/30-claude-code-patterns/worktree-orchestration.md` — mechanical-sweep reviewer prompt template
- `workspaces/kailash-ml-gpu-stack/journal/0008-GAP-full-specs-redteam-2026-04-20-findings.md` — the /redteam sweep that surfaced §4a and §5a
