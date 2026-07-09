# /redteam — mops-onboarding re-convergence #7 (F1 + F2 outstanding-ledger closure) — 2026-07-09

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence. Scope: the F1/F2 items deferred as non-blocking
LOWs in re-convergence #6 (`redteam-2026-07-09-reconvergence6.md` § "LOW dispositioned NOT-fixed").
**7 rounds, 18 adversarial agent-passes** (waves of ~3, throttle-aware). This is a COC-artifact
suite (no code/tests/frontend) — Criteria-4 stand-in is ground-truth verification against the
actual hook/lib source.

## Outcome

**CONVERGED. 2 working-tree files edited** (uncommitted — BUILD-repo commit gate; land via
`/codify` → `codify/esperie-2026-07-09` → PR → admin-merge + a BUILD→loom proposal for cross-SDK
distribution). Distributable invariant re-verified GREEN on committed HEAD after every edit: roster
`PLACEHOLDER-owner`/`0000000`/gen 0 · 0/6 coordination-enforcement hooks in committed
`settings.json` · `probe-phase-guard` = 1 · disclosure scanner exit 0 (1559 files).

Files: `.claude/rules/enrollment-operations.md` (MUST-3) · `.claude/skills/45-genesis-bootstrap/SKILL.md`
(§ script-by-path).

## The two outstanding items — dispositions

### F1 — enrollment-operations.md MUST-3 categorical wording (FIXED)

The #6 LOW noted MUST-3's title/opening read categorically ("no inline `node -e` for watched-state
mutation"), which falsely flagged `/certify` Step 2's SAFE inline `reserveJournalSlotSigned(...)`
call. Ground-truth verification of the guard (`detectStateFileMutation` in `violation-patterns.js`

- `STATE_PATH_RX` in `validate-bash-command.js:456`) established the real enforced invariant:
  **the guard fires ONLY when a `STATE_PATH_RX` literal appears on the command line — and it is
  read/write-AGNOSTIC (a path-presence detector, not mutation-aware)**. MUST-3 was rewritten to state
  that invariant precisely:

* The satisfying pattern for an authored mutation is script-by-path (path off the command line).
* A delegated **signed-emit** helper (`reserveJournalSlotSigned` / `emitSignedRecord`) that routes
  its watched-path write through `coc-emit.js::emitSignedRecord` (enforcing
  `multi-operator-coordination.md` MUST-1) and keeps the path INTERNAL is PERMITTED inline — this is
  the `/certify` Step-2 case the categorical wording wrongly flagged.
* "Owns the write internally" is NECESSARY BUT NOT SUFFICIENT: a wrapper hiding a raw
  `fs.writeFileSync`, a concat-assembled path, and a helper taking the watched path as an ARGUMENT
  (`appendStamped(repoDir, filePath, …)`) are all BLOCKED / script-by-path — the last matching
  `skills/42-certify/SKILL.md` Step 4.

The same read/write-agnostic accuracy was propagated to the cross-referenced depth-file
`skills/45-genesis-bootstrap/SKILL.md` (four instances of the write-only framing corrected), and a
phantom cross-reference (an "illustrative `node -e` in whoami.md" that does not exist) was corrected
to describe whoami.md's actual script-by-path form.

### F2 — claim/release-claim/claims helper-naming "drift" (REFUTED — no edit)

The #6 LOW proposed aligning the `/claim`,`/release-claim`,`/claims` commands' coordination-log
write citations (`coc-sign.js::sign` + `transport-filesystem.js`) to the consolidated
`coc-emit.js::emitSignedRecord`. Ground-truth verification REFUTES the premise:

- `emitSignedRecord` serves NONE of the claim/release/reap record types (only journal-slot /
  codify-lease / capability-ledger / membership records).
- The actual claim-writer `adjacency-leasecheck.js::autoClaim` STILL builds the record inline, signs
  via `coc-sign.js::sign`, and appends via `transport-filesystem.js::appendRecord`; `reap-ceremony.js`
  signs via `coc-sign.js`. `coc-append.js::appendStamped` is the observations/violations helper, NOT
  the coordination-log write path.

The commands are **accurate to the runtime**. Editing them to cite `emitSignedRecord` would introduce
a NEW command↔code divergence (a `spec-accuracy` defect per journal/0035 §3 "the code is the
authority"). Disposition: **no edit**. (Independently confirmed by all three R1 agents + R3/R7.)

## Findings + dispositions (by round)

| Round | Finding(s)                                                                                                                    | Severity | Disposition                                                                                                 |
| ----- | ----------------------------------------------------------------------------------------------------------------------------- | -------- | ----------------------------------------------------------------------------------------------------------- |
| R1    | carve-out over-reach: `appendStamped` (arg-path) wrongly listed as inline-safe; "blessed" defined by porous "owns internally" | HIGH×2   | Narrowed to signed-emit pair; `appendStamped` → counter-example; "blessed"=routes-through-emitSignedRecord  |
| R2    | consolidated fix verified                                                                                                     | CLEAN    | —                                                                                                           |
| R3    | MUST-3 BLOCKED parenthetical "guard flags read-only node (it does not)" factually wrong — guard is read/write-agnostic        | MED      | Corrected to read/write-AGNOSTIC                                                                            |
| R4    | 2 same-class residuals: MUST-3 `**Why:**` invariant ("no…write") + depth-file "only state-file mutation is [blocked]"         | MED×2    | Both corrected; a 4th instance (skill guard-desc "MUTATES") found by orchestrator sweep + fixed             |
| R5    | read/write class verified fully closed across both files                                                                      | CLEAN    | —                                                                                                           |
| R6    | phantom citation: skill claims an "illustrative `node -e` in whoami.md" that does not exist                                   | LOW      | Reworded to whoami.md's actual script-by-path form; R5 partial-enumeration LOW closed with "(among others)" |
| R7    | definitive exhaustive audit — every claim + cross-ref grep-verified accurate                                                  | CLEAN    | Convergence confirmed                                                                                       |

## Convergence criteria

1. 0 CRITICAL ✓ · 2. 0 HIGH ✓ (since R2) · 3. clean R5 (full 3-agent) + clean R7 (reviewer + security)
   bracketing a single fixed LOW at R6 (per re-convergence #6 precedent, non-blocking LOWs do not break
   a clean round; the R6 LOW was additionally fixed and R7 confirms the fix introduced nothing new) ·
2. every guard-mechanics claim + every cross-reference ground-truth-verified against
   `violation-patterns.js` / `validate-bash-command.js` / `journal-reserve.js` / `coc-emit.js` /
   `coc-append.js` / `whoami.md` / `42-certify` · 5–7. N/A (COC-artifact suite).

## Accepted non-blocking (documented; NOT convergence-blocking)

- **MUST-3 over-density** — the SAFE-helper qualification paragraph is dense (~18 lines). Load-bearing
  (it closes a genuine over-block AND under-block); the structural extraction of the helper-qualification
  depth to `skills/45-genesis-bootstrap` is best done in the canonical loom pass, alongside any future
  `/codify` that touches this rule. Path-scoped rule → no baseline-emission cost.

## KEY institutional lessons (candidates for /codify)

- **A guard's DESCRIPTION must match its DETECTION mechanism, not its NAME or PURPOSE.** The detector is
  named `detectStateFileMutation` and exists to block state MUTATIONS, but it is a path-presence
  detector — read/write-agnostic. Four separate artifact sentences described it as mutation-only; the
  cascade closed only when the enumeration was run to completion across BOTH the rule and its depth-file
  (journal/0035 method note confirmed again: partial enumeration is why it took R3→R6).
- **"The code is the authority" refutes a queued finding, not just a lifecycle claim.** F2 was a queued
  "drift" item whose premise dissolved on reading the actual claim-writer — the correct action was NO
  edit, preventing a new divergence.
- **A carve-out fence must be a verifiable property, not a circular one.** "Owns the write internally"
  is satisfied by a malicious wrapper; "routes through `emitSignedRecord` (MUST-1)" is code-inspectable.
