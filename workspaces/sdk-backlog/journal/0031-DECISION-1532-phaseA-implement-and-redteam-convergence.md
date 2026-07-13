---
type: DECISION
slug: 1532-phaseA-implement-and-redteam-convergence
date: 2026-07-13
issue: 1532
phase: 03-implement + 04-validate
branch: fix/delegate-connector-contract-hardening
depends-on: journal/0030 (ANALYZE)
---

# DECISION — #1532 Phase A implemented + redteam converged

Phase A of the #1532 root-cause plan (journal/0030): harden the kailash.delegate
connector contract in-repo (no cross-repo write) so consolidation — if pursued —
lands against a stable, shipped surface. Two root-cause fixes.

## RC1 — canonical conformance vectors ship as package data

**Root cause:** `load_canonical()` resolved `tests/fixtures/delegate-conformance/
canonical.json` (under `tests/`, never in the wheel) by walking up from
`__file__` → `FileNotFoundError` for every pip-installed consumer; downstream `dc`
connectors hand-rolled a `parents[4]`-ascent loader to work around it.

**Fix:** `git mv` the vectors (byte-identical, digest 770d539e… intact) to
`src/kailash/delegate/conformance/data/canonical.json`; `load_canonical()` now
resolves via `importlib.resources` (zip-safe TEXT read; shared `_load_from_text`
preserves the schema-version + digest-integrity + validation contract on both the
packaged and file paths). Packaging: `pyproject [tool.setuptools.package-data]` +
`MANIFEST.in`. `root=` override retained (back-compat). Cross-SDK: rs embeds its
vectors at compile time via `include_str!` → no equivalent bug (no rs issue filed).

## RC2 — connector-authoring surface consolidated onto kailash.delegate

Promoted 10 symbols from `dispatch.__all__` (already public) to the package
top-level `__all__` (56→66): Principal, SignedActionEnvelope, AttestedReadReceipt,
RevocationChannel, KnowledgeLedger, AuthVerifier, SignatureContract,
LegacyInvokeConnector, DispatchSignatureError, DispatchSignerError. Additive; a
connector depends on ONE surface. `test_package_shell` count guard updated 56→66.

## Gate evidence (all ran this session)

- Fence A/B: `lint-delegate-fences: clean (10 files scanned)` exit 0.
- Delegate unit + new regression: 452 passed, 1 skipped. Integration conformance:
  12 passed. E2E delegate: 9 passed, 1 xfailed. mypy on changed src: clean.
- **Wheel build (uv build --wheel):** ships `kailash/delegate/conformance/data/
canonical.json` (unzip -l confirmed).
- **Clean-venv consumer path:** `load_canonical()` returns 5 vectors + all 10 RC2
  symbols import from `kailash.delegate` (`__all__`==66) from the installed wheel.
- Collect-only: clean for the delegate/regression blast radius. 4 pre-existing
  collection errors (`test_issue_501/712_*`, `test_provider_registry_backcompat`,
  `test_issue_500_*`) are `No module named 'nexus'/'kaizen'` — the local venv has
  no editable sub-package installs + no pip/uv module to add them (stale-venv trap,
  session-notes); orthogonal to this delegate-only diff, green in CI. Documented,
  not a code failure.

## Redteam convergence (parallel, evidence-gated)

Two reviewers dispatched in parallel; both RAN with cited evidence (not
errored/empty — `evidence-first-claims.md` MUST-3 satisfied).

- **reviewer** (agent, ran all 6 mechanical sweeps + wheel build): 2 IMPORTANT + 2
  MINOR. F1 (README:469 stale path) → FIXED. F2 (regression test proxied source
  tree, not wheel — a dropped package-data line would keep source-tree tests green
  while the wheel breaks) → FIXED via `test_packaging_config_declares_conformance_data`
  (config-presence guard) + kept the manual wheel-build proof. F4 (zipimport-brittle
  str-path assert) → FIXED (guarded with `isinstance(resource, Path)` skip). F3
  (historical CHANGELOG:1116 entry) → NO CHANGE (historically accurate for when S7
  shipped; the move is documented in the new [Unreleased] entry).
- **security-reviewer** (read-only; rg/Bash unavailable in its sandbox, so
  code-read not executed): no CRITICAL/HIGH, ship-eligible. LOW (`_doc` names the
  rs crate in the now-public canonical.json) → NO CHANGE: not a strict
  `cross-sdk-inspection.md` Rule-6 violation (names a crate, not the repo slug; `rs`
  role-shorthand permitted), pre-existing pattern, and kailash-py is a PUBLIC repo
  whose source already carries the same refs — shipping the wheel discloses nothing
  new. INFO-A ("test_load_from_text_tamper_is_detected missing") → false alarm (it
  exists in tests/regression/test_issue_1532_…; the reviewer's broken rg searched
  the wrong file; green in the run). INFO-B (digest covers vectors only) →
  confirmatory.

Post-fix re-verification: 15 passed (9 regression incl. the 2 new guards + 6
package_shell). Production code (schema.py, **init**.py) unchanged since review —
only README + the regression test moved — so the reviewers' verdict on the fix
logic stands.

## Disposition + open items

- Phase A converged, merge-ready on `fix/delegate-connector-contract-hardening`.
  NOT committed — kailash-py is a BUILD repo; commit → PR → merge → /release stay
  with the co-owner (structural gate). Proposed version bump: kailash 2.48.1 →
  **2.49.0** (additive public API + packaging fix).
- Phase B/C (with-history `contrib/` migration + archive) remain gated on the
  cross-repo-WRITE authorization + the D1 structure ratification (journal/0030).
- Surfaced for the co-owner (NOT fixed here — different bug class, broader sweep):
  the delegate package source (`__init__.py:11` "kailash-rs", schema.py, audit.py)
  carries bare `kailash-rs` / rs-crate references that ship in the public wheel —
  a standing Directive-0 / Rule-6 disclosure-hygiene question spanning many files.
