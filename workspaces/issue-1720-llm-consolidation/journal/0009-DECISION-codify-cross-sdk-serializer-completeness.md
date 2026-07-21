# DECISION — /codify: cross-SDK signed-model serializer-set completeness (cross-sdk-inspection.md Rule 4e)

Date: 2026-07-21. Repo class: BUILD (`name = "kailash"`). Author: agent (codify
receipt; the DECISION to codify was user-approved — "approved" — the clause content
is agent-derived from this session's #1841 arc + a 4-round adversarial redteam).
Coordination OFF (un-enrolled public repo). Codify lease HELD:
`codify/jack-hong-2026-07-21` (scope covers cross-sdk-inspection.md + its guide extract

- latest.yaml + learning-codified.json).

## What was codified

ONE new sub-rule capturing the single genuinely-new, un-covered institutional lesson
from the multi-wave EATP #1841 v2/v3 delegation-signing arc (kailash 2.59.0):

**`.claude/rules/cross-sdk-inspection.md` — new "### 4e. Existing Fold Fields On A
Cross-SDK Signed Model MUST Round-Trip Through EVERY Serializer Via One Shared Serde"**
(+ the matching `## Rule 4e` guide-extract section: full example, BLOCKED corpus, evidence).

Rule 4e is the OPPOSITE defect polarity to the existing Rule 4d (a coverage-assessment
sub-agent confirmed they are siblings, not duplicates):

- **4d** = a field ADDED to a signed model changes the not-configured pre-image → fix
  prune-when-unset (Origin #1510).
- **4e** = a field ALREADY folded is DROPPED by ONE serializer on round-trip → the
  reconstructed record can't recompute the pre-image → verify FALSE → signing
  non-functional end-to-end, invisible to every per-serializer unit test → fix ONE shared
  serde wired into EVERY serializing path + a DISCRIMINATING both-polarity e2e round-trip
  regression + a STRUCTURAL serializer-set-parity test (Origin #1841).

## Alternatives considered

- **Standalone new rule** — REJECTED. The coverage assessment found the detection
  mechanism (holistic redteam, `agents.md`), the test discipline (`testing.md` E2E
  regression), and the shared-helper fix pattern (`security.md` Multi-Site Plumbing /
  Pre-Encoder Consolidation) are ALREADY codified; only the serializer-set-completeness
  SURFACE was un-named. A sibling clause under 4d is the minimal, non-redundant home.
- **No new rule** — REJECTED. Learning #1 (serializer-set completeness) is genuinely
  un-covered and cascade-valuable (both SDKs carry the signed-delegation serializer
  surface). Learnings #2 (cyclic-import-via-Protocol — generic Python idiom) and #3
  (holistic-redteam + verify-first — already codified) correctly yielded NO new rule.

## Convergence receipt (redteam to convergence — user directive)

4-round adversarial redteam (parallel cc-architect + reviewer + security-reviewer):

- **R1:** cc-architect CLEAN (1 optional cross-ref); reviewer CLEAN (all Origin claims
  ground-truth-verified against `delegation_fold_serde.py` + the 4 serializers + the
  real regression test); security MERGE-WITH-FIXES (F1 non-discriminating regression,
  F2 manual-grep completeness, F3/F4 LOW, F5 out-of-scope pre-existing #1841 design).
- **R2:** applied F1-F4 (discriminating both-polarity pin + structural parity test +
  generalized enumeration + non-collidability invariant). cc-architect CLEAN; security
  MERGE-WITH-FIXES (R2-1 DO example re-showed single-polarity; R2-2 non-collidability
  over-claim; R2-3 circular discovery predicate — all BUG-class, fixed).
- **R3:** cc-architect CLEAN; security SECURITY-CLEAN (R2-1/2/3 closed; N1/N2 LOW
  INCREMENTAL, explicitly non-blocking, do-not-reset-convergence).
- **R4 (final):** applied N1 (n−1 cross-version pairs) + N2 (wiring enumeration); security
  confirmation — [receipt appended on completion].

## Dispositions carried forward (surfaced to user, NOT fixed here)

- **F5 (security R1, out of 4e scope):** pre-existing #1841 design — `constraint_subset`
  / `task_id` round-trip faithfully but are NOT in the v2/v3 signed pre-image; if v2/v3
  enforcement reads `get_effective_constraints`, a store-writer edit could alter
  authorization under a valid signature. Reviewer-labeled UNCONFIRMED INFERENCE (depends
  on whether v2/v3 enforcement consults that path). Routed to the #1841 signing-coverage
  owners as a SEPARATE pre-existing item — NOT a Rule-4e concern.

## Distribution / follow-ups

- BUILD-repo proposal appended to `.claude/.proposals/latest.yaml` (origin: build,
  classification_suggestion: global) → loom Gate-1.
- Eval-coverage (`coc-artifact-eval-coverage` MUST-1): NO eval-harness in this BUILD repo;
  probe-set obligation is loom-side Gate-1 (loom holds the eval ENGINE per that rule Origin).
- Cross-SDK mirror: the Rust SDK (private sibling, NOT in this repo's resolver) carries the
  same signed-delegation serializer surface → a human-gated mirror issue is DRAFTED and
  surfaced for the user's per-issue filing decision (upstream-issue-hygiene MUST-1 +
  handoff-completion MUST-3; not auto-filed — cross-repo write cannot be self-authorized).

## For Discussion

1. F5 is an unconfirmed inference: does v2/v3 enforcement actually read
   `get_effective_constraints` (making `constraint_subset` a live tamper surface), or is it
   inert for v2/v3? The #1841 owners should confirm before it is treated as a real gap.
2. Rule 4e mandates a STRUCTURAL serializer-set-parity test with a non-circular discovery
   predicate — but kailash-py does not yet SHIP that test. Should landing the test in
   `tests/regression/` be queued as a follow-up so the rule's own mechanical backstop exists
   in the origin repo, not only in future serializers?
