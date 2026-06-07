---
type: DISCOVERY
date: 2026-06-07
project: kailash-py
topic: "Forest drained to #1183; pin-drift detector built + converged"
phase: analyze/implement/redteam
tags: [dependencies, pin-drift, issue-1183, tooling, redteam]
---

# 0001 — DISCOVERY: forest drained to #1183; pin-drift detector converged

## Forest reconciliation (the session's first finding)

Continuing from F32 (ml-docs, #1277/#1278 merged), I reconciled every outstanding
thread against live GH + git state. **The entire standing forest has shipped:**

- F32 ml-docs → #1277/#1278 (merged); nexus #1174 → 2.8.0; nexus parity
  #1216/#1217/#1218 → kailash 2.28.4 + nexus 2.9.0 (`c767aea21`/`9070ecf3f`);
  from_brief #1125 → 2.27.0; dataflow tenant #1249/#1252 → 2.11.0/2.11.1
  (`c823a0ab7`/`d03665aa2`); encoder #1258/#1269; #772. The tenant + parity
  workspaces were completed-but-uncleaned (stale journals), NOT in-flight.
- Of 4 open GH issues, 3 are genuinely blocked: #630 (Foundation mint ISS-37),
  #1086 (loom-side COC hooks), **#693 (M2-blocked — verified: kailash-ml 0.9.0
  exposes only internal `SchemaFeatureGroup`, no public `@feature`/`FeatureGroup`)**.
- **#1183 is the single unblocked, in-scope item** — the root cause of the
  recurring `uv.lock`/pin drift the sweeps repeatedly flag.

## #1183 — built the source-of-truth enforcer (not floor homogenization)

Reconciled with `rules/dependencies.md`: per-package floors legitimately differ
(feature usage), so the fix is to make drift LOUD, not identical. Built
`tools/check_pin_consistency.py` + `tests/unit/tools/test_check_pin_consistency.py`
(8 tests). ERROR = caps on first-party siblings / unsatisfiable floors /
intra-manifest drift; ADVISORY = cross-manifest divergence + staleness.

### Real findings on `main` (3 errors)

1. **Live resolution break:** `kailash-align` rl-bridge `kailash-ml[rl]>=1.1,<2.0`
   caps out the current ml 2.0.0. Cap origin `4fe9eea87` (defensive, pre-2.0).
   Live compat probe: all 9 `kailash_ml.rl.*` symbols align imports are present in
   ml 2.0.0 + `import kailash_align.rl_bridge` succeeds → the cap excludes a working
   version. (Behavioral major-version compat = align test-suite run; gated.)
2. `kailash-ml` intra-manifest: `kailash-kaizen` at `>=2.7` vs `>=2.7.5`.
3. `kailash-align` intra-manifest: `kailash-ml` at `>=0.11.0` (stale) vs `>=1.1`.

## Redteam → CONVERGED

- **Convergence receipt:** reviewer agent task `ade5cdbfa6c3e1607` — verdict
  **APPROVE**. Ran both mechanical sweeps (8 tests pass; tool reports 3 errors +
  advisories, exit 1), independently probed ~30 PEP 508 forms (env markers, extras,
  epoch/local versions, URL refs, `~=`, multi-constraint) + the `packaging`-absent
  fallback. 0 CRITICAL/HIGH/MEDIUM. 3 LOW (cosmetic).
- **3 LOW fixed in-shard** (autonomous-execution MUST Rule 4): staleness
  double-count (semantic floor grouping), `<=` branch in `_cap_excludes`, `===`
  confirmed already-correct. Re-ran: 8 tests pass, errors still 3, advisory 25→24.

## Disposition

- **DONE / converged:** detector + test suite (additive, untracked; no commits —
  BUILD repo).
- **GATED on user (published-contract + release):** the 3 pyproject ERROR fixes +
  wiring the detector into pre-commit/CI (per the no-auto-CI directive). Specific
  recommended values + evidence in `02-plans/findings-and-design.md`.

## Completion (2026-06-08, user-approved "please complete")

All 3 ERROR fixes applied in the working tree (BUILD repo — commit/release stays
with user) + verified:

- align `kailash-ml[rl]>=1.1,<2.0` → `>=1.1` (cap dropped); align core
  `kailash-ml>=0.11.0` → `>=1.1`; ml `kailash-kaizen>=2.7` → `>=2.7.5` (×2).
- Behavioral compat gate: **align rl-bridge suite 74 passed against ml 2.0.0**
  (not just import-surface) — cap removal verified safe.
- Detector now reports **0 errors** (21 advisories remain — legitimate per-package
  divergence/staleness, non-failing).
- Pre-commit hook `check-pin-consistency` added to `.pre-commit-config.yaml`
  (scoped to pyproject/tool changes); `pre-commit run --all-files` → Passed.
- Floor values (`>=1.1`, `>=2.7.5`) are PyPI-resolvable per `deployment.md`
  § "Optional Dependencies Pin to PyPI-Resolvable Versions".

**Release scope (per build-repo-release-discipline):** the align + ml pyproject
floor edits are consumer-visible → committing them requires version bumps +
`/release` of kailash-align + kailash-ml (user-authorized structural gate). The
tooling (`tools/`, `.pre-commit-config.yaml`) is not wheel-packaged → no release.

## Receipts

- `tools/check_pin_consistency.py`, `tests/unit/tools/test_check_pin_consistency.py`
- Reviewer convergence: agent task `ade5cdbfa6c3e1607` (APPROVE).
- Compat probe: 9/9 `kailash_ml.rl.*` symbols present in ml 2.0.0; rl_bridge imports OK.
