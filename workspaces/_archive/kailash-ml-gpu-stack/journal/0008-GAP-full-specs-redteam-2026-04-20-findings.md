---
type: GAP
date: 2026-04-20
created_at: 2026-04-20T06:00:00.000Z
author: co-authored
session_id: continue-session-2026-04-20-outstanding-items
project: kailash-ml-gpu-stack
topic: Full-specs /redteam sweep round 4 — 13 HIGH findings, 2 fixed inline, 11 need dedicated implementation sessions
phase: redteam
tags:
  [
    redteam,
    specs-authority,
    gap,
    onnx-bridge,
    km-doctor,
    km-track,
    orphan-detection,
    dialect-drift,
  ]
related_journal: [0007-DISCOVERY-full-specs-sweep-round.md]
---

# GAP — Full-specs sweep round 4 surfaces 13 HIGH findings across ML, Nexus, Governance

## Context

User requested `/redteam` scoped to "any active todos, gh issues, or gaps against full specs" following the outstanding-items cleanup pass (PR #543 merged — sibling floor bumps, worktree cleanup, loom Gate-2 verification). No open GH issues. Three analyst agents delegated in parallel covering (a) ML + DataFlow, (b) Core + Kaizen + Nexus + Security, (c) Governance + Trust + Infrastructure specs.

Prior round 3 (journal 0007) got ml-engines + ml-backends + ml-tracking to 14/14 green for the specific Phase 1 GPU-first contract. This round 4 audits the FULL surface of each spec (not just the Phase 1 additions) — and surfaces long-standing gaps that were never part of Phase 1 scope.

## Findings summary

- **63 / 76 assertions GREEN** across 34 audited spec files
- **13 HIGH** — 2 fixed inline, 11 deferred to dedicated implementation sessions
- **4 MEDIUM** — spec tightening / nice-to-haves

### Collection gate (blocker per orphan-detection §5)

Mechanical sweep of `pytest --collect-only` against every `packages/*/tests/` directory surfaced 4 non-specs blockers. All 4 resolved inline this session:

| Blocker                         | Root cause                                                                        | Fix                                                                                                                                          |
| ------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| kaizen — 4 collection errors    | `respx` missing; `benchmark` marker + fixture unregistered                        | Installed `respx` + declared `pytest-benchmark>=4.0.0` in kaizen [dev] extras + registered `benchmark` in pytest markers (commit `1313ae56`) |
| pact — 1 collection error       | `hypothesis` not in root venv (correctly blocked by python-environment.md Rule 4) | Installed `kailash-pact[dev]` which brings hypothesis via sub-package extras                                                                 |
| fsspec conflict                 | `datasets` caps `fsspec[http]<=2026.2.0`, installed 2026.3.0                      | `uv lock --upgrade-package fsspec --upgrade-package datasets`; `uv pip check` clean                                                          |
| Root venv sub-packages unlinked | `uv sync` dropped editable installs during lockfile sync                          | `uv pip install -e packages/kailash-*` bulk re-install                                                                                       |

Final state: 16027 root + ~26000 sub-package tests collect cleanly. Only exception: `packages/kailash-trust/tests/` which contains no test files (re-export shim — see finding #11).

### Fixed inline (2)

**#1 + #2. nexus — WebSocketTransport and WebhookTransport missing from package `__all__`.**

Both classes exist at `packages/kailash-nexus/src/nexus/transports/{websocket.py:47, webhook.py:117}` and are listed in `nexus.transports.__init__.__all__`. Documented in `specs/nexus-channels.md §4.4` and §4.5 as part of the channels contract. But the package root `nexus/__init__.py` imported only `HTTPTransport`, `MCPTransport`, `Transport` — so `from nexus import WebSocketTransport` raised `ImportError` despite the spec advertising it.

Per orphan-detection.md §6 MUST (module-scope public imports appear in `__all__`) — HIGH. Fixed in commit `842ebad4`.

### Deferred — ML domain (9)

All gated on Phase 6 work per `kailash_ml/__init__.py:187` comment + `specs/ml-tracking.md` elevation from draft to authoritative.

**#3. ONNX bridge matrix declares 6 frameworks, implements 3.**

`packages/kailash-ml/src/kailash_ml/bridge/onnx_bridge.py` has `_export_sklearn`, `_export_lightgbm`, `_export_xgboost`. Missing `_export_torch`, `_export_lightning`, `_export_catboost`. Spec `ml-engines.md §6.1 MUST 2` explicitly forbids advertising matrix keys without implemented branches (the rule was written to block this exact pattern — pre-Phase 1).

**#4. No `test_onnx_roundtrip_{framework}.py` regression tests** — `ml-engines.md §6.1 MUST 3` requires one per framework in the matrix.

**#5. `km.doctor()` / `km-doctor` console script entirely absent.** `grep "def doctor\|km.doctor" packages/kailash-ml/src/` returns zero matches. `specs/ml-backends.md §7` documents 30+ lines of contract (exit codes 0/1/2, `--json` output, `--require=<backend>`, CI lane requirement) backed by zero code.

**#6. `km.track()` is `raise NotImplementedError`** at `kailash_ml/__init__.py:187`. Code comment says "Phase 6 will implement per specs/ml-tracking.md"; spec says MUST. Per specs-authority §6 this is a spec-code contradiction that BLOCKS — either the spec needs a deviation note OR code ships.

**#7. Auto-capture of 16 mandatory fields cannot execute** (host, python_version, git_sha, device_family, device_fallback_reason, tenant_id, ...) — upstream of #6.

**#8. `COMPLETED/FAILED/KILLED` run-status auto-set on exit** — upstream of #6.

### Deferred — Governance, trust, infra (2)

**#9. `packages/kailash-trust` is a publication orphan.**

104-LOC re-export shim (`__init__.py` only) listing 39 symbols from `kailash.trust.*`. `packages/kailash-trust/tests/` contains only `__init__.py` — zero tests. `grep "from kailash_trust" --glob "*.py"` returns only the shim and two doc references — no production consumer. Per orphan-detection.md §6 this is an advertised-public-API-with-no-verification. A `pip install kailash-trust` wheel ships with a contract validated by nothing.

Mitigating: the underlying `kailash.trust.*` code IS properly tested (encrypt_record/decrypt_record round-trip at `tests/trust/plane/unit/test_encryption.py:78`, dual_sign/dual_verify at `tests/trust/unit/test_dual_signature.py`). The orphan is only at the packaging seam.

Disposition options: (a) add Tier 2 smoke test imported through `kailash_trust.*` that round-trips through one manager, (b) delete `packages/kailash-trust/` and direct users to `kailash` directly.

**#10. `dialect.quote_identifier()` absent from `src/kailash/db/`.**

`rules/dataflow-identifier-safety.md` MUST Rule 1 mandates `dialect.quote_identifier()` on every dynamic DDL path. `grep "quote_identifier" src/` returns zero matches. The canonical helper exists only in `packages/kailash-dataflow/src/dataflow/adapters/`. Core `src/kailash/db/dialect.py` has only `_validate_identifier` (validate-only, no quoting) — which the rule explicitly deems insufficient. `ConnectionManager.create_index()` interpolates identifiers via f-string after validation.

Disposition: mirror the DataFlow dialect contract into `src/kailash/db/dialect.py` OR amend `specs/infra-sql.md` to document the intentional split.

### MEDIUM findings (not expanded here)

- ml-tracking `_index.md` vs actual tracking surface drift
- dataflow-express carve-out documentation for scalar aggregates
- dataflow-cache keyspace v1→v2 entry format
- kaizen-llm-deployments §6.6 `test_errors.py` vs actual `test_errors_no_credential_leak.py` — spec-tightening

## What landed

- Commit `1313ae56` — kaizen pytest-benchmark dep + marker
- Commit `842ebad4` — nexus WebSocketTransport + WebhookTransport in **all**
- Full audit artifacts:
  - `workspaces/kailash-ml-gpu-stack/04-validate/05-specs-gap-audit-ml-dataflow.md`
  - `workspaces/kailash-ml-gpu-stack/04-validate/06-specs-gap-audit-core-kaizen-nexus.md`
  - `workspaces/kailash-ml-gpu-stack/04-validate/07-specs-gap-audit-governance-trust-infra.md`

## What did NOT land (flagged for dedicated sessions)

The 9 ML findings represent Phase 6 scope (ml-tracking production implementation + ONNX bridge matrix completion + km.doctor console script). The 2 governance/infra findings represent (a) a packaging decision about kailash-trust and (b) core-vs-dataflow dialect contract reconciliation. All 11 require dedicated `/analyze` → `/todos` → `/implement` cycles; none fit in this session's red-team-fixit scope.

## For Discussion

1. **Counterfactual**: If round 4 had not run, these 11 gaps would have remained invisible until either (a) a downstream user hit `km.track()`'s `NotImplementedError` in production or (b) a `from nexus import WebSocketTransport` lookup failed mid-deploy. The collection-gate blockers (hypothesis / respx / fsspec) would have kept blocking any attempt to run the full suite from root venv — which explains why nobody caught them. Should `/redteam` convergence include a MUST "collect-only across every package MUST pass from the root venv" gate, separate from the specs gate? The current orphan-detection.md §5 says "Collect-Only Is A Merge Gate" but the per-package separation hasn't been called out.

2. **Data-referenced**: Round 3 (journal 0007) claimed "14/14 spec-to-code parity green" after narrowing scope to specs touched by Phase 1. Round 4 against the FULL specs found 9 HIGH findings in the same ML domain because ml-tracking §2.2/§2.4 and ml-engines §6.1 were NEVER part of Phase 1 scope. The scope-narrowing caused a false-confidence APPROVE. Question: should `/redteam` mandate a FULL-specs sweep after every spec edit OR only on release gates? The cost differential is 1 round vs 3 rounds of analyst time.

3. **`specs-authority.md` extension candidate**: journal 0007 proposed extending `specs-authority.md` MUST 5 with "Every spec edit triggers a re-derivation against the full sibling-spec set in the same domain, not only the edited file." Round 4's data strengthens that proposal — the cross-spec drift between `ml-engines.md §6.1` and `onnx_bridge.py` was invisible to Phase 1 scope. If round 4's narrow-scope failure mode recurs in another session, the extension becomes codify-worthy.
