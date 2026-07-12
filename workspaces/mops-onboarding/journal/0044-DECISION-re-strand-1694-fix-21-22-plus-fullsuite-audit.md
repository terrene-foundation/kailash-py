---
type: DECISION
topic: re-strand #1694 — re-author #21/#22 + full-suite stranding re-verification
date: 2026-07-12
issue: 1694
---

# DECISION — Issue #1694 re-strand: #21/#22 re-authored + full-suite audit (7 more stranded)

## Context

Loom Gate-1 `/sync-from-build` (2026-07-12) forensically reviewed
`.claude/.proposals/latest.yaml` (onboarding-suite proposal) and filed **#1694**:
some entries' prose claims a fix was "Applied BUILD-side" but the committed source
contradicts it — the **prepared ≠ delivered / stranded** class. Root cause: a later
`/sync-to-build` restored loom-canonical-stale copies of loom-owned
commands/skills/rules, clobbering the BUILD-side re-convergence edits (NEW artifact
FILES survived via additive sync; EDITS to pre-existing loom-owned files reverted).

Two asks: (1) re-author #21 (45-genesis watched-paths + `runEnrollmentCeremony`
return) and #22 (43-ecosystem `STATE_PATH_RX` hedge) as real committed edits;
(2) re-verify the FULL suite (`loom == BUILD IDENTICAL` proves "no delta to place",
NOT "every fix landed" — 4 spot-checked were stranded, others may be too).

## Ask 1 — #21/#22 re-authored (DONE, redteam-converged)

Four edits, each verified byte-for-byte against the WIRED ground truth (evidence-first):

- **#21 CHANGE 1** — `skills/45-genesis-bootstrap/SKILL.md` codify-branch watched-paths
  list completed to the wired `integrity-guard.js::DIRECT` set: **8 files**
  (`operators.roster.json`, `operators.roster.schema.json`, `coordination-log.jsonl`,
  `posture.json`, `violations.jsonl`, `observations.jsonl`, `coordination-mode.json`,
  `learning-codified.json`) **+ 3 subtree predicates** (`team-memory/**`, `journal/**`,
  `workspaces/<name>/journal/**`) + authoritative anchor. Ground truth:
  `integrity-guard.js:194-232`.
- **#21 CHANGE 2** — same skill: `runEnrollmentCeremony` return citation
  `{ ok, error?, reason?, step? }` → `{ ok, record?, error?, reason?, step? }`
  (`record` on success). Ground truth: `genesis-ceremony.js` `_signAndAppend` (`:791`→`:349`
  `{ok:true, record}`; JSDoc `:369`).
- **#22** — `skills/43-ecosystem-init/SKILL.md` `STATE_PATH_RX` enumeration (5 paths, a
  genuine partial subset) gained the "(among others; wired STATE_PATH_RX authoritative)"
  hedge. Ground truth: `validate-bash-command.js:457` (10 wired paths).
- **#22 sibling hardening** — the 45-genesis `STATE_PATH_RX` sibling the proposal claimed
  "already hedges" was ITSELF stranded/unhedged (missing `observations.jsonl`,
  `presence-mechanism.json`, `operators.roster.schema.json`). Expanded to all wired members
  - hedge, so the convention #22 references is actually true. Ground truth:
    `validate-bash-command.js:457`.

Illustrative-vs-completeness discipline (the #12 subclass): EDIT 1 is a COMPLETENESS
claim (exact, anchored, not hedged); EDITs 3/4 are ILLUSTRATIVE (hedged). Correct
treatment per claim type.

**Redteam — 2 independent agents, both CLEAN, zero CRIT/HIGH/MED (convergence):**

- reviewer: all 4 edits accurate + complete vs wired source; no fabricated paths; no
  command↔skill parity obligation (`commands/ecosystem-init.md` carries no STATE_PATH_RX
  mirror — it defers to the skill); no dangling refs.
- cc-architect: faithful to proposal #21/#22 (source==prose restored); correct
  illustrative-vs-completeness treatment; frontmatter/progressive-disclosure intact.
- Two LOW advisories (both defensibly no-action): the now-complete 45-genesis STATE_PATH_RX
  "(among others)" hedge is the safe/future-proof direction; the `runEnrollmentCeremony`
  `opts` list omits `now`/`sign` (internal test seams, not caller-facing — complete for its
  caller-contract purpose).

## Ask 2 — full-suite re-verification (DONE): 7 additional stranded entries

Adversarial audit re-derived all 21 non-skipped `changes:` entries against committed HEAD.
**14 LANDED** (dependencies, security Enforcement-Surface-Parity, git CI-check/merge,
cross-sdk-inspection Rule 6/4d, tenant-isolation Rule 7, handoff-completion, cross-SDK
genericization + new rule/skill/agent FILES — additive sync preserved them). **2 N/A**
(`proposal_only` entries correctly unapplied BUILD-side). **7 STRANDED** — all in the
onboarding/certify suite, all the same root cause as #17/#18 (loom-canonical-stale copies
clobbered BUILD edits):

| #   | Artifact(s)                                                                                            | Re-authoring needed                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --- | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 10  | onboard.md, enroll.md, 44-enroll, enrollment-operations.md, 41-onboard, multi-operator-coordination.md | roster path `.claude/learning/operators.roster.json`→`.claude/operators.roster.json` (onboard.md:70); "four"→"three" business roles (enroll.md:47, 44-enroll:37; schema enum is 3); "loom-only and absent from BUILD/USE"→`use_excluded` framing (enrollment-operations.md:247); MUST-7→MUST-6 grace (onboard.md:43, 41-onboard:105); "seven"→"eight" section keys (41-onboard:124); remove FALSE "permissions.deny enforces this" for roster/coord-log (multi-operator-coordination.md:78) |
| 11  | self-referential-codify.md                                                                             | add `command-skill-parity` to the codify-discipline Rules allowlist (:79)                                                                                                                                                                                                                                                                                                                                                                                                                   |
| 12  | enroll.md, 44-enroll, onboard.md, 41-onboard, certify.md                                               | enroll B3 "Enrollment PR opened. Once it merges to main…"; MUST-7→MUST-6; certify.md:74 `::version`→`::bank_version`                                                                                                                                                                                                                                                                                                                                                                        |
| 13  | 42-certify, certify.md, claim.md                                                                       | pass/deferral codify-lease (scope `["journal/"]`); deferral `DEFER`→`DECISION` type; brief `.pending/`→`workspaces/_certify/.pending/`; Phase-0 `validate-cert-bank.mjs` in skill; claim.md:27 `lease-override`→sibling-self-release/reap                                                                                                                                                                                                                                                   |
| 14  | enrollment-operations.md, 45-genesis                                                                   | MUST-3 read/write-agnostic rewrite (STATE_PATH_RX is a path-presence detector; `reserveJournalSlotSigned`/`emitSignedRecord` permitted inline)                                                                                                                                                                                                                                                                                                                                              |
| 15  | enrollment-operations.md, 45-genesis                                                                   | MUST-3 4th-pass `detectHeredocWriteRunBundle` enumeration + DO-NOT heredoc-bundle example                                                                                                                                                                                                                                                                                                                                                                                                   |
| 16  | whoami.md, enrollment-operations.md, 42-certify                                                        | bare `detectStateFileMutation`→`detectStateFileMutationSegmentAware` (whoami.md:47, 42-certify:153); MUST-4 DO "both read the gitignored log"→"resolveIdentity reads the committed roster" (enrollment-operations.md:123)                                                                                                                                                                                                                                                                   |

## Disposition for the 7 (#10–#16): report to loom Gate-1, do NOT re-apply BUILD-side

Distinguished from #21/#22 (which #1694 explicitly classified "absent at BUILD **and loom**
→ Needs re-authoring here", so files-present BUILD re-authoring is the only path):

- **The mops `.session-notes` carry explicit prior-session guidance** for the onboarding-suite
  F-items: _"ride latest.yaml (Gate-1 pending). No BUILD-side action pending… Do NOT re-apply
  BUILD-side (churn loop — next sync reverts again); let loom Gate-1 handle it… NEVER re-apply
  after a sync reverts it."_
- **`repo-scope-discipline`** — a BUILD session cannot read loom, so I cannot classify each of
  the 7 as "loom canonical-applies" (like #17/#18) vs "absent at loom → needs BUILD
  re-authoring" (like #21/#22). That classification is loom Gate-1's, requiring loom-state
  comparison.
- Re-authoring the 7 BUILD-side would (a) violate the explicit anti-churn guidance and (b) risk
  the /sync-overwrite churn loop if loom canonical-applies them.

**Action:** surface the 7 to loom Gate-1 via a comment on **#1694** (its own tracking surface —
in-scope, not cross-repo) with the exact per-entry re-authoring above, so loom classifies +
canonicalizes each (`handoff-completion.md` MUST-1: explicit surfacing on the surface that owns
the action, not a local note). #21/#22 ship as a BUILD PR (files-present) so loom re-ingests
them correctly this time.

## Receipts

- Redteam: reviewer + cc-architect background agents, both CLEAN (this session's transcript).
- Full-suite audit: general-purpose background agent, 21 entries re-derived vs HEAD.
- PR: (linked on merge) — the #21/#22 BUILD re-authoring.
- #1694 comment: the 7-entry disposition to loom Gate-1.
