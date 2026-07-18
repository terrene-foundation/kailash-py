# /redteam — mops-onboarding independent re-convergence #5 — 2026-07-08

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence. 7 rounds, ~18 parallel adversarial agents
(waves of ~3, throttle-aware). Convergence at **0 CRIT / 0 HIGH / 0 MED across 2 consecutive
clean rounds** (Criteria 1–3), with the field/citation + registration-parity ground-truth
verifications standing in for Criteria 4 (this is a COC-artifact suite, no code/tests/frontend).

## Ground-truth re-verification of the 6 load-bearing "ships un-enrolled" claims (Round 1)

| Claim                              | Command                                                        | Result                                              |
| ---------------------------------- | -------------------------------------------------------------- | --------------------------------------------------- |
| isCoordinationEnabled(cwd)         | `coordination-mode.js::isCoordinationEnabled` (script-by-path) | `false` (source `default-off`) ✓                    |
| roster genesis owner               | `git show HEAD:.claude/operators.roster.json`                  | `PLACEHOLDER-owner`, root_commit `0000000`, gen 0 ✓ |
| probe-phase-guard registered       | `grep -c` committed settings.json                              | 1 ✓                                                 |
| 6 enforcement hooks committed      | `grep -c` each in settings.json                                | 0 / 6 ✓                                             |
| esperie tokens in committed roster | `git show HEAD:…                                               | grep -ic esperie`                                   | 0 ✓ |
| disclosure scanner                 | `node .claude/bin/scan-synced-disclosure.mjs`                  | clean, 0 findings, 1558 files, exit 0 ✓             |

## Round-by-round

| Round | Lens(es)                                                                                     | Verdict                                                                               |
| ----- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| R1    | hook-registration parity · cited-symbol/bin existence · distributable-invariant completeness | CLEAN (0 CRIT/HIGH/MED; only informational LOWs)                                      |
| R2    | operator-lifecycle walk · cross-artifact consistency+structural · cross-reference accuracy   | 4 MED (3 lifecycle handoff + 1 xref) + LOWs                                           |
| R3    | fix-verification · fresh lifecycle re-walk                                                   | fixes CLEAN; re-walk found 2 command↔skill sibling divergences my R2 fixes introduced |
| R4    | full-cohort command↔skill parity sweep · holistic                                            | 1 MED (pre-existing certify no-assist lockfile divergence)                            |
| R5    | certify-fix verify + parity re-sweep · holistic                                              | parity CLEAN; holistic 2 LOW                                                          |
| R6    | fresh holistic · parity+coherence                                                            | parity CLEAN; holistic 1 LOW (pre-existing wrong-key citation)                        |
| R7    | final holistic · exhaustive field-citation hunt + invariant                                  | **CLEAN both agents** — 0 CRIT/HIGH/MED, 40+ field/helper citations verified          |

## Findings + dispositions (severity-ordered)

### MED (all fixed + verified)

1. **certify no-assist gate — command↔skill divergence on lockfile removal timing (SECURITY-relevant).**
   `commands/certify.md` keeps the `probe-phase-guard.js` lockfile through the Phase C gate
   ("Probe exit (Phase C complete OR abandoned mid-gate)"), but `skills/42-certify` removed it
   "end of Phase B before transition to Phase C" — and Phase C's gate loop RE-RUNS the probe on
   failed questions (`re-run probe on q`). An orchestrator following the skill tore down the
   no-assist guard exactly during the retry loop the gate exists to protect, leaving only prose
   refusal (belt, no suspenders). Fix: skill now states the lockfile PERSISTS through Phase C,
   single removal at Phase C exit (pass OR abandon), matching the command. (This is the PR #355
   security HIGH-1 mechanism — the guard was inert-during-retries on the skill path.)
2. **enroll B3 premature "Enrolled" before the roster PR merges.** `commands/enroll.md` B3 printed
   "Enrolled. Run /onboard" while the roster registration is still an unmerged PR → `/onboard` on
   `main` pre-merge resolves the operator as not-yet-rostered (a confusing bounce-back loop). Fix:
   B3 now prints "Enrollment PR opened. Once it merges to main, run /onboard" + the branch-vs-main
   roster-visibility explanation. Propagated to `skills/44-enroll` B3 (byte-aligned).
3. **cross-reference drift — MUST-7 cited for the grace/pending_verification mechanism.**
   `onboard.md` §4 + `skills/41-onboard` §6 cited `trust-posture.md MUST-7` for the grace
   mechanism, which is defined in **MUST-6 § Grace Period Semantics** (§7 is the wiring-requirement
   clause). Fix: both re-pointed to MUST-6.

### LOW (fixed)

- **F1 discoverability** — `skills/43-ecosystem-init` C3 precondition now cross-links
  `skills/45-genesis-bootstrap` (the first-owner roster-hand-author runbook that PRECEDES C3).
- **F2 owner-vs-teammate** — `ecosystem-init` C5 "Each operator now runs /enroll" → "Each TEAMMATE
  …" + note the genesis owner is already rostered and runs `/onboard` directly (propagated to
  skill 43 C5, byte-aligned).
- **`<id>` → `<display_id>`** consistency in `enroll.md` invariant-1.
- **certify footer stale line-count** ("Skill body ~140 lines"; actual 245 after the security fix)
  → dropped the number, kept the progressive-disclosure point.
- **command↔skill scrub asymmetry** — skills 43/44 raw `02-plans/02-ga-…` path → genericized to
  `(loom-internal reference)` matching their commands.
- **certify receipt wrong-key citation** — `commands/certify.md` receipt cited
  `_certification.yaml::version` (schema int `1`) for "the bank version"; the operator-visible
  field is `::bank_version` (the skill records this correctly). Fix: command → `::bank_version`.

### Verified NON-defects (dispositioned, not "fixed")

- **F4** (onboard `/whoami --register` nag) — `operator-id.js::resolveIdentity` returns a SOLO
  identity when `!isCoordinationEnabled` (no `blocked_into`), so the nag never fires on this OFF
  repo. Behavior correct; not a defect.
- **F5** (certify "if not already rostered" next-step) — a conditional no-op-when-rostered guard;
  defensively correct, not vestigial.

### Out-of-scope / accepted (NOT convergence blockers)

- `commands/whoami.md` 152 raw lines: body = 149 (≤150 per Rule 3, frontmatter excluded);
  delivered at 152 upstream via 2026-07-02 `/sync-to-build` (not this suite's edits); plausibly
  under Rule 3's procedural named-rationale exception. A loom-side concern — editing a synced
  command BUILD-side would create loom drift.
- No mechanical distributable-repo lint (journal/0031 "For Discussion" candidate); `ecosystem.json`
  not gitignored (the deliberate opt-in enable path); 42-certify skill `name:` strips number-prefix
  (historically tolerated, no dir collision); illustrative unbound pseudocode in 41-onboard.

## Convergence criteria

1. 0 CRITICAL ✓ (all rounds) · 2. 0 HIGH ✓ (all rounds) · 3. 2 consecutive clean rounds ✓ (R6
   substantive-clean, R7 fully clean) · 4. spec/claim compliance grep/AST-verified ✓ (6 claims + 40+
   field/helper citations + registration parity, all ground-truth) · 5–7. N/A (COC-artifact suite —
   no new code modules / frontend; probe-phase-guard ships committed audit fixtures).

## Diff: 13 edits across 8 files (working tree — UNCOMMITTED, BUILD-repo commit gate)

commands/{onboard,enroll,ecosystem-init,certify}.md · skills/{41-onboard,42-certify,
43-ecosystem-init,44-enroll}/SKILL.md. All self-referential-codify surface → the 7-round
multi-agent redteam-with-tests IS the required self-referential gate (self-referential-codify.md
Rule 1). Distributable invariant re-confirmed intact AFTER all edits (roster PLACEHOLDER, 0/6
enforcement hooks, probe-phase-guard=1, disclosure scanner exit 0).
