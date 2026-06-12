# DECISION — Wave 2 redteam CONVERGED (Shard B materialize + Shard F GDPR erase)

**Date:** 2026-06-12
**Phase:** /redteam → inter-wave gate G1 (CLOSED — converged)
**Type:** DECISION (coordination receipt — redteam convergence + dispositions)
**Relates to:** journal/0004 (Wave-2 self-verification, which left G1 INCOMPLETE)

## Convergence verdict

Wave 2 reached **2 consecutive clean redteam rounds** (R3 + R4), satisfying
`commands/redteam.md` § Convergence Criteria (per `wave-loop.md` G1). Four rounds ran;
findings decreased monotonically and were ALL one bug class (raw tenant scope id on an
observable surface) plus one spec drift + one LOW.

| Round | reviewer (code)                                                        | security-reviewer                                              | Outcome             |
| ----- | ---------------------------------------------------------------------- | -------------------------------------------------------------- | ------------------- |
| R1    | APPROVE-WITH-FIXES (task `a1d9a4599f6b03593`) — spec drift (MED) + LOW | APPROVE-WITH-FIXES (task `aaf161e50533632ac`) — HIGH-1 + MED-1 | fixes → `d37fdb266` |
| R2    | APPROVE-WITH-FIXES (task `a3fd887415030137d`) — NEW-1 (= HIGH-2)       | APPROVE-WITH-FIXES (task `a36915ddddb80db82`) — HIGH-2         | fix → `589bc67f4`   |
| R3    | CONVERGED (task `a8a5be9f92e4b361b`)                                   | CONVERGED (task `ace126e01c2da8212`)                           | clean #1            |
| R4    | CONVERGED (task `ab5ea8ff93824f3c3`)                                   | CONVERGED (task `a5a267cc27fad3395`)                           | clean #2            |

## Claimed-vs-found delta (wave-loop G2 learning capture)

The Wave-2 todos claimed Shard B/F were "implemented + self-verified." The redteam found
the implementation **correct** (zero CRIT, zero code-blockers; all 6 security invariants —
tenant-isolation id-derivation, fail-closed erase, unscoped-delete guard, redaction, no raw
SQL — verified intact against real SQLite across rounds), but surfaced one observability
bug class the self-verification missed:

- **Raw `tenant_id` on log + exception surfaces** (spec §11.4 mandates the erase audit be
  _fingerprinted_; raw scope id bleeds to log aggregators per `observability.md` Rule 4/8).
  R1 caught it on the erasure audit lines (HIGH-1) + exception messages (MED-1, via
  `MLError._format_message` echoing a raw `tenant_id=` kwarg). The R1 fix was **partial** on
  the materialiser — a `replace_all` matched only the 16-space `.start` log line and missed
  the 20-space `.ok`/`.error` lines nested inside the `try:`. R2 (both reviewers,
  independently) caught the two missed sites (HIGH-2) — the `security.md` § Multi-Site Kwarg
  Plumbing failure mode (primary fixed, siblings missed). Now: tenant fingerprinted on EVERY
  log/error surface in both files; mechanically guarded by caplog sweeps in BOTH test files
  (a regression cannot pass tests).
- **Spec drift** (code reviewer, MED): §11.2 listed the dropped `point_in_time` write-path
  kwarg after `adb0a6b70`. Fixed first-instance (`specs-authority.md` Rule 5); §11.1
  `FeatureGroup.materialize` 5-kwarg READ binding verified intact; signatures checked against
  ground truth before the durable write. R4 cosmetic line-citation drift (`erasure.py:239`→
  `241`) also corrected.
- **LOW**: reserved-key note added on the `classification["tenant_id"]` namespace-overload
  (fail-safe today via the `isinstance(value, str)` guard).

**Lesson (cross-shard, for codify consideration):** `replace_all` on a key-rename misses
sibling occurrences at a different indentation depth. The erasure log fix needed two passes
(12-space + 16-space); the materialiser fix needed two passes (16-space + 20-space) but R1
did only one — caught at R2. The structural defense is the caplog SWEEP test (assert the
property across ALL records), not per-line edits; both test files now carry it.

## journal/0004 fresh-reopen limitation — DISPOSITION

The fresh-DataFlow-instance `get_features` → `UserFeatListNode not found` finding (the
materialiser registers its dynamic `@db.model` only in its own DataFlow instance) is
**disposition: Wave 3** (both reviewers concur it is NOT a Wave-2 blocker — pre-existing 1.x
`SchemaFeatureGroup` "user registers the model" convention; reproduces WITHOUT erase; the
in-process happy path is fully tested + passing). The fix (option a — `get_features` / the
store re-registers the materialiser's model on demand when the backing table exists) composes
naturally with **Wave-3 Shard C** (the online-store serving path hits exactly the
separate-process read case). Carried into Wave 3 as a value-anchored shard, NOT silently
passed.

## Commit state (on `feat/fm2-wave1-authoring-registry`)

- `d37fdb266` — R1 fixes (HIGH-1 + MED-1 + spec drift + LOW)
- `589bc67f4` — R2 fix (HIGH-2 — two missed materialiser log sites + dual-path guard test)
- (this journal + the `:239`→`:241` spec citation fix land together)

Wave-2 Tier-2: 17/17 pass (real SQLite, dataflow 2.11.3); `npx pyright` clean.

## Next (inter-wave gate continues): G3 done (spec first-instance) → G4 re-rank → G5 Wave 3

Wave 3 = Shard C (online-store adapter + `OnlineStoreUnavailableError` + the journal/0004
on-demand re-registration fix) + Shard S6 (graduate `dataflow-ml-integration.md`, close #693).
Then holistic terminal `/redteam` across all merged shards (≥3-wave plan, `agents.md`).
