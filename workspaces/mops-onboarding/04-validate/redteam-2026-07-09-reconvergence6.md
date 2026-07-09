# /redteam — mops-onboarding independent re-convergence #6 — 2026-07-09

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence. **10 rounds, ~30 parallel adversarial agents**
(waves of ~2–3, throttle-aware). Convergence at **0 CRIT / 0 HIGH / 0 MED across 2 consecutive
clean rounds (R9 + R10)**. This suite is COC-artifacts (no code/tests/frontend); ground-truth
verification against the actual hook/lib/schema source stands in for Criteria 4.

## Outcome

**CONVERGED. 9 working-tree files edited** (uncommitted — BUILD-repo commit gate; land via
`/codify` → `codify/esperie-2026-07-09` → PR → admin-merge, the self-referential-codify Rule-1
multi-agent gate already satisfied by these 10 rounds). Distributable invariant re-verified intact
on committed HEAD AND after every edit: roster `PLACEHOLDER-owner`/`0000000`/gen 0 · 0/6
coordination-enforcement hooks in committed `settings.json` · `probe-phase-guard` = 1 · 0 esperie
tokens in committed roster · disclosure scanner exit 0 (1559 files).

Files: `commands/{certify,claim,ecosystem-init,onboard,posture}.md` ·
`skills/{41-onboard,42-certify,43-ecosystem-init,45-genesis-bootstrap}/SKILL.md`.

## The headline find — a PRE-EXISTING certify coordination-ON write-surface conformance gap

Prior convergences (#1–#5) validated the suite under the lenses they applied and never exercised
`/certify`'s write surface against the **coordination-ON (enrolled) substrate** — because kailash-py
itself ships coordination-OFF, where `integrity-guard` / `journal-write-guard` passthrough. This
re-convergence walked that surface end-to-end and found `/certify` was never reconciled with the
multi-operator write discipline. Resolved across R5–R8 to a complete, source-verified coverage of all
8 certify writes:

- **Pass + deferral journal entries** are codify-class `journal/` writes → now acquire a covering
  `codify-lease` (`acquireCodifyLease({scopeFiles:["journal/"]})`) on a `codify/<display_id>-<date>`
  branch (Step 1.5) and release it (Step 5). `["journal/"]` DIRECTORY scope is load-bearing —
  `findCoveringLease` matches a trailing-slash-dir prefix; a bare filename does not, and
  `MANDATORY_SCOPE` doesn't cover `journal/`.
- **Deferral entry `type`** corrected `DEFER` → `DECISION` + `topic:"certify-defer-<id>"` — `DEFER`
  is NOT in `journal-reserve.js::VALID_TYPES`, so the old contract failed the reservation closed.
- **Brief `.pending/` receipts** moved OUT of the `journal/` subtree → `workspaces/_certify/.pending/`
  (integrity-guard watches `^workspaces/<name>/journal/`; Phase-A receipts under `journal/` would halt
  un-leased before any lease exists). They are ephemeral scratch, not codify-class entries.
- Entry-gate corrected to the code-accurate model: `resolveIdentity` reads the **working-tree** roster,
  so certify runs on the enrollment `codify/<id>-<date>` branch (roster row visible) OR after merge;
  registration precedes certification; certification gates `/claim`.

Verified against source: `integrity-guard.js` (watched subtrees + `findCoveringLease`), `codify-lease.js`
(`acquireCodifyLease`/`releaseCodifyLease`/`MANDATORY_SCOPE`), `journal-reserve.js::VALID_TYPES`,
`operator-id.js::resolveIdentity` (`_readJsonSafe` working-tree read), `validate-bash-command.js::STATE_PATH_RX`.

## Findings + dispositions (by round)

| Round | Finding(s)                                                                                                                                                        | Severity           | Disposition                                        |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------ | -------------------------------------------------- |
| R1    | certify skill drops `validate-cert-bank.mjs` security scan + consent STOP (Phase 0 absent)                                                                        | HIGH               | Added Phase 0 to skill mirroring command Step 1    |
| R1    | certify pass-receipt filename command↔skill drift; onboard PR-pending bounce; genesis double-run idempotency; 45 signing-order                                    | MED×3 + LOW        | Fixed all; command↔skill mirrored                  |
| R2    | claim.md SAME-conflict handoff → nonexistent `/lease-override` + wrong `/release-claim` invocation; F2-fix stale DEFER mirror; length-caps/posture/step-2 wording | MED×2 + LOW×4      | Fixed                                              |
| R3    | certify entry-gate just-enrolled sibling gap; certify exit next-steps contradiction; onboard ladder; claim.md phantom test citation                               | MED×2 + LOW×2      | Fixed                                              |
| R4    | certify **lifecycle-model contradiction** (register-first vs certify-first) — traced to an R3 over-constraint; corrected to code-accurate working-tree model      | HIGH               | Fixed (reversed own R3 error with source evidence) |
| R5    | certify pass-write **lease gap** (integrity-guard halts un-leased journal write under coordination-ON); certify.md:96 false "no coordination-log" claim           | HIGH + MED         | Added lease ceremony; corrected contract           |
| R6    | lease-fix bugs: scope shape (`r.reservation.filename` ≠ `journal/`-prefixed candidate), branch over-claim, contract-table omission                                | HIGH + MED×2 + LOW | Corrected to `["journal/"]` scope + branch-ensure  |
| R7    | abandon-path DEFER write lacked the lease ceremony (sibling gap); OFF fail-closed caveat; wrapper pointers                                                        | MED + LOW×2        | Fixed                                              |
| R8    | brief `.pending/` receipts hit `workspaces/<name>/journal/` watch; DEFER `type` invalid                                                                           | HIGH×2             | Fixed (move receipts; DECISION+certify-defer)      |
| R9    | **WRITE SURFACE FULLY COVERED — 0 gaps** (8-path table, source-verified); 2 non-blocking LOW                                                                      | CLEAN              | LOW-2 fixed; LOW-1 dispositioned                   |
| R10   | certify pair SETTLED; suite CLEAN                                                                                                                                 | CLEAN              | —                                                  |

### LOW dispositioned NOT-fixed (out of scope / rule-owner refinement)

- **enrollment-operations.md MUST-3 categorical wording vs certify Step-2 inline `node -e`.** Step 2
  (`reserveJournalSlotSigned`) is verified SAFE (the state path is internal to the helper, never on the
  command line, so `STATE_PATH_RX`/`detectStateFileMutationSegmentAware` don't fire), and the skill
  documents this. MUST-3's title reads categorically ("no `node -e` for watched-state mutation"); the
  precise fix is to tighten MUST-3's wording ("…on the command line…") — a rule-authoring refinement
  in a self-referential rule, out of this certify-focused convergence's scope. Noted for the
  enrollment-operations owner.
- **claim/release-claim/claims coordination-log writes** cite `coc-sign.js::sign` + filesystem-transport
  rather than `coc-append.js`/`coc-emit.js` (M1-era 2026-05-2x commands, pre-coc-emit-consolidation).
  Substantively satisfies `multi-operator-coordination.md` MUST-1 (stamped/chained/signed); helper-naming
  drift only, outside this suite's changed surface. Noted for a future coc-emit-alignment sweep.

## Convergence criteria

1. 0 CRITICAL ✓ · 2. 0 HIGH ✓ · 3. 2 consecutive clean rounds ✓ (R9 + R10 both 0 CRIT/HIGH/MED) ·
2. claim/citation compliance ground-truth-verified against actual hook/lib/schema source (8-path
   write-surface coverage table + ~18 citation spot-checks + command↔skill parity) · 5–7. N/A
   (COC-artifact suite — no new code modules / frontend; probe-phase-guard ships committed audit fixtures).

## KEY institutional lessons (candidates for /codify)

- **A command's write surface must be reconciled with the coordination-ON substrate, not only its
  coordination-OFF passthrough.** `/certify` was validated 5× in a coordination-OFF repo where every
  integrity-guard / journal-write-guard / codify-lease gate passes through; its journal writes were never
  exercised against the enrolled substrate they ship into. The full write-surface enumeration (every
  filesystem/state write × every guard, under coordination-ON) is the lens that closes this class — and
  it must be run to COMPLETION per-round (the "one sibling gap per round" pattern is the tell that the
  enumeration was partial).
- **A fix on one execution path implies the sibling paths.** Pass-path lease → abandon-path lease;
  pass-entry type → brief-receipt path + deferral type. `command-skill-parity` + multi-site-plumbing,
  generalized to "same-surface writes get the same treatment."
- **The code is the authority for a lifecycle claim.** The R3→R4 entry-gate error (over-constraining to
  "await merge") was corrected only by reading `resolveIdentity`'s working-tree roster read — an artifact
  claiming you can't do what the code permits is a spec-accuracy defect.
