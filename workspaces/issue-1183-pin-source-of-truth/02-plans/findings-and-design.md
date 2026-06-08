# #1183 — Dependency version-pin source-of-truth: findings + design

**Date:** 2026-06-07
**Issue:** #1183 (design — "single source of truth for dependency version-pin sourcing")
**Phase:** analyze → implement (detector) ; recommend+gate (pyproject fixes)

## Context — why this is the session's pick

The standing forest from the prior session is fully shipped (F32 ml-docs #1277/#1278;
nexus #1174 → 2.8.0; nexus parity #1216/#1217/#1218 → 2.28.4/2.9.0; from_brief #1125 →
2.27.0; dataflow tenant #1249/#1252 → 2.11.x; encoder #1258/#1269; #772). Of the 4 open
GH issues, 3 are genuinely blocked: #630 (Foundation mint ISS-37), #1086 (loom-side COC
hooks), #693 (M2-blocked — verified kailash-ml 0.9.0 has no public `@feature`/`FeatureGroup`).
**#1183 is the single unblocked, in-scope item** — and the documented root cause of the
recurring `uv.lock`/pin drift the sweeps keep flagging.

## What #1183 actually asks (reconciled with `rules/dependencies.md`)

The naive reading — "one canonical floor for every dependency" — is WRONG and would
violate `dependencies.md`: floors (`>=X.Y`) are _expected_ to reflect each package's actual
feature usage, so the same dep legitimately CAN carry different floors across packages. The
real problems are (a) **silent** drift, (b) **defensive caps** on first-party siblings, and
(c) **intra-manifest** inconsistency. The fix is to make those _loud_, not to homogenize.

## Deliverable A — `tools/check_pin_consistency.py` (the source-of-truth enforcer)

A read-only, stdlib-first detector that scans all 9 first-party `pyproject.toml` manifests
and classifies pins, aligned with `dependencies.md`:

- **ERROR (exit 1):**
  1. Defensive upper cap (`<`/`<=`/`==`/`!=`) on a first-party `kailash*` sibling.
  2. Floor exceeding that sibling's current in-repo version (unsatisfiable in-workspace).
  3. Same dep at semantically-distinct floors **within one manifest**.
- **ADVISORY (exit 0):** cross-manifest floor divergence (legitimate per-package); floors
  far behind the sibling's current version (staleness — a feature-usage judgment).
- `--strict-advisory` escalates advisories to exit 1; `--json` for machine output.

Verified by `tests/unit/tools/test_check_pin_consistency.py` (8 tests, all pass) covering
every verdict class incl. `>=1.1`==`>=1.1.0` semantic equality and self-extra exclusion.

## Findings on current `main` (3 errors, 25 advisories)

### ERROR 1 (live resolution break) — `kailash-align` caps out the current ml

`packages/kailash-align/pyproject.toml [optional-dependencies.rl-bridge]`:
`kailash-ml[rl]>=1.1,<2.0` — the `<2.0` cap **excludes the current kailash-ml 2.0.0**.

- Origin: commit `4fe9eea87` ("wip(W30.2): bump kailash-align 0.5.0 + [rl-bridge] extra") —
  added defensively when ml was 1.x, speculatively excluding the then-unreleased 2.0 major.
- Compat probe (live, against installed ml 2.0.0): all 9 `kailash_ml.rl.*` symbols align's
  rl-bridge late-imports are present, and `import kailash_align.rl_bridge` succeeds. The cap
  excludes a working version.
- **Recommended fix:** drop the cap → `kailash-ml[rl]>=1.1` (per `dependencies.md` § "No
  Caps"). **Gate:** published-contract change to kailash-align → needs (a) align rl-bridge
  test suite run against ml 2.0.0 for behavioral (not just import) confidence, (b) align
  version bump + release (user's gate per BUILD-repo discipline).

### ERROR 2 — `kailash-ml` intra-manifest drift on `kailash-kaizen`

`packages/kailash-ml/pyproject.toml`: `kailash-kaizen>=2.7` (kaizen-judges, kaizen-observability)
vs `>=2.7.5` (agents). **Recommended fix:** align all three to `>=2.7.5`. Low risk.

### ERROR 3 — `kailash-align` intra-manifest drift on `kailash-ml`

`packages/kailash-align/pyproject.toml`: `kailash-ml>=0.11.0` (core deps — very stale; ml
is 2.0.0) vs `kailash-ml[rl]>=1.1` (rl-bridge, post-cap-removal). **Recommended fix:** raise
the core floor to match actual feature usage (≥1.1; confirm with align owner).

### Advisories (25) — not auto-fixed

Cross-manifest floor divergence (legitimate) + staleness. Notable: `kailash` core floored at
4 values (2.14.0/2.16.0/2.28.0/2.28.4) while core is 2.29.3; several siblings floored 1–2
minors behind. These are feature-usage judgments, surfaced for review, not errors.

## Deliverable B (recommended, GATED) — wire the detector into the drift gate

To make drift loud _going forward_, wire `check_pin_consistency.py` into either a local
pre-commit hook or CI. **Not auto-created** per the standing "never auto-create CI workflows
without asking" directive — recommend + cost-gate to the user.

## Disposition summary

- **DONE (converged):** detector + 8-test suite (this session's autonomous deliverable).
- **GATED on user (published-contract + release):** the 3 ERROR fixes + the CI/pre-commit
  wiring. Each carries a specific recommended value + evidence above.
