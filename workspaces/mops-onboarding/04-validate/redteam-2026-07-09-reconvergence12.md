# /redteam — mops-onboarding re-convergence #12 (fresh adversarial audit on merged main, post-#11) — 2026-07-09

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED, coordination OFF).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence, maximally parallelized (time-pressure framing →
parallelization, NOT procedure-drop, per `time-pressure-discipline.md`). Scope: fresh adversarial audit
of the re-convergence #11 state now MERGED on main (PRs #1632/#1633/#1634) — re-verify #11's `/claim`
predicate-token fix holds, AND audit the full onboarding/coordination/enrollment/genesis/certify suite
against the **NEW `command-skill-parity.md` rule (landed 2026-07-08, `882c68f92`)** whose Origin IS this
suite's `/certify` guard-lifecycle divergence (journal/0032) — a rule the prior 11 rounds never audited
against. Three distinct drift classes hunted in parallel.

## Outcome

**CONVERGED.** R1 mechanical (clean) → R2 (3 parallel adversarial agents; **0 CRITICAL, 0 HIGH**; the
recurring citation-vs-wired class + the new command↔skill-parity class both CLEAN; **3 LOW/MED
illustrative-enumeration gaps hardened**) → fix applied → R3 (verify fix + sibling re-hunt; clean) →
R4 mechanical (clean). **2 consecutive clean rounds post-fix (R3 + R4); 0 CRITICAL; 0 HIGH.** All edits
working-tree only (BUILD-repo owner commit gate), landed with this report + journal/0043 as the #12
codify PR.

## The new-rule audit — command↔skill parity (first audit of this suite against `command-skill-parity.md`)

The rule landed 2026-07-08 with its Origin IN THIS SUITE: the `/certify` `probe-phase-guard.js` lockfile
was torn down before the Phase-C gate retry loop in the skill while the command kept it through — a
security-guard-lifecycle divergence invisible to five prior review lenses, caught only by a command↔skill
parity sweep. That specific defect was already FIXED (commit `882c68f92` codified the rule + the fix).
Round #12 is the first adversarial re-audit of the WHOLE suite against the rule's MUST-2/MUST-3.

**Result: CLEAN across 5 pairs × 5 shared-step axes.**

- `/certify` guard lifecycle CONFIRMED HELD: `certify.md:60-66` (create at Phase-B entry, `rm` at
  "Probe exit (Phase C complete OR abandoned mid-gate)") byte-aligns with `42-certify/SKILL.md:103`
  ("the lockfile **PERSISTS through Phase C** — do NOT remove it at the Phase B→C transition") +
  `:126-132` (single teardown at gate exit, spanning the Phase-C retry loop). The prior divergence is
  closed and remains closed.
- The two Origin-cited sibling print-string drifts (enroll B3 hand-off, ecosystem C5 hand-off) are now
  BYTE-IDENTICAL: `enroll.md:65` ≡ `44-enroll:63`; `ecosystem-init.md:90-91` ≡ `43-ecosystem-init:97-98`.
- All other shared-step axes (ordering, STOP/gate predicates, cited field/branch/helper names) agree
  across `onboard↔41`, `certify↔42`, `enroll↔44`, `ecosystem-init↔43`, and the `45-genesis-bootstrap`
  ceremony-ownership invariant (`{45, /ecosystem-init C3}` — exactly one owns the run).

## The recurring class — citation vs wired mechanism (#9/#10/#11) — CLEAN, no phantoms

Re-derived every predicate/symbol/journal-type/token/helper/branch citation across the suite from the
WIRED source with a positive-allowlist mindset ("documented set == wired return set"). **Zero phantoms;
every completeness-claim enumeration re-derives EXACT.** The #9/#10/#11 fixes all hold:

| Completeness claim                                    | Wired source (line)                                                                                                                               | Verdict                                     |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------- |
| `claim.md:27` `/claim` SAME predicates (7)            | `adjacency.js::sameReason` `exact`(172)/`glob`(173)/`dir-contains`(183)/`workspace`(186)/`commit-cohort`(202)/`phase`(217)/`composed-axis-3`(235) | EXACT — **#11 fix holds**                   |
| journal `VALID_TYPES` (onboard/certify/41)            | `journal-reserve.js` Set = DECISION/DISCOVERY/TRADE-OFF/RISK/CONNECTION/GAP/AMENDMENT; DEFER absent                                               | EXACT — **#10 DEFER-phantom stays refuted** |
| `resolveIdentity()` shape (41-onboard)                | `operator-id.js` return triple + role/host_role/posture?/blocked_into?                                                                            | EXACT                                       |
| `probe-phase-guard` matcher (certify/42)              | `RETRIEVAL_TOOLS = Read/Grep/Glob/WebFetch` == `settings.json:76` == cited                                                                        | EXACT — **#9 guard-symbol class clean**     |
| `foldLog` / `MANDATORY_SCOPE` / `business_roles` enum | `coordination-log.js` 7-key / `codify-lease.js` 2-member / `operators.roster.schema.json:94-105`                                                  | EXACT                                       |

## The three LOW/MED illustrative-enumeration gaps — HARDENED (positive-allowlist per the #11 lesson)

No phantoms (accurate as far as they went), but three enumerations were partial-and-unhedged where the
wired set is larger — the exact drift-prone surface the #11 lesson warns of. All three source-verified
and hardened to anchor on the wired source (the #11 durable-fix pattern):

| #   | Artifact:line                 | Gap                                                                                                                                                                                        | Fix (source-verified)                                                                                                                                                 |
| --- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | `45-genesis-bootstrap:57-61`  | integrity-guard watched-paths list (8) omitted `coordination-mode.json`, `learning-codified.json`, `workspaces/<name>/journal/**` vs the wired `DIRECT` set (`integrity-guard.js:202-233`) | Completed to `documented == wired` (all 8 files + 3 subtrees) + inline "the wired `DIRECT` set + subtree predicates at `integrity-guard.js` are authoritative" anchor |
| 2   | `43-ecosystem-init:133-134`   | `STATE_PATH_RX` list (5) unhedged, while its sibling `45:143` correctly hedges "(among others)" — a genuine inconsistency                                                                  | Added "(among others; the wired `STATE_PATH_RX` at `validate-bash-command.js` is authoritative)" to match the sibling convention                                      |
| 3   | `45-genesis-bootstrap:99-101` | `runEnrollmentCeremony` return cited `{ok, error?, reason?, step?}` — omits the success-path `record` (`genesis-ceremony.js:199` = `{ok:true, record} \| {ok:false, error, reason, step}`) | Added `record?` → `{ ok, record?, error?, reason?, step? }` + "(`record` on the success path)"                                                                        |

`43`/`45` are NOT on the `self-referential-codify.md` Rule 2 allowlist (the Skills allowlist enumerates
`spec-compliance`/`command-authoring`/`skill-authoring`/`hook-authoring`/`sweep`/`32-trust-posture`/
`30-claude-code-patterns`/`12-testing-strategies/probe-driven-verification`; `enrollment-operations.md`
explicitly OMITS `45-genesis-bootstrap` as a runbook, not a codify-discipline skill) → no mandatory
multi-agent gate. The suite is loom-synced, so the fix is routed to loom via the BUILD→loom proposal
(`latest.yaml`, GLOBAL) — every downstream copy carries the same gaps.

## Findings + dispositions (by round)

| Round | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | Sev       | Disposition                                           |
| ----- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------- | ----------------------------------------------------- |
| R1    | MECHANICAL — parity rule on main (`882c68f92`); certify guard lifecycle holds; wired ground-truth sources present; 0 disclosure hits in suite; 0 stubs; `probe-phase-guard.js` registered on `Read\|Grep\|Glob\|WebFetch`                                                                                                                                                                                                                                                           | CLEAN     | —                                                     |
| R2    | ADVERSARIAL (3 parallel agents). **A (command↔skill parity):** 5 pairs × 5 axes, 0 contradictions; guard lifecycle + both Origin sibling drifts CLEAN. **B (citation-vs-wired):** 0 phantoms, all completeness enums EXACT; 3 LOW/MED illustrative-enumeration gaps. **C (dangling/disclosure/markers):** 0 genuine defects; absent targets all by-design BUILD-subset (loom-only `guides/`, `ecosystem.json` write-target, consumer-seeded cert bank); disclosure + markers CLEAN. | 3 LOW/MED | 3 gaps HARDENED (source-verified); dispositions below |
| R3    | VERIFY FIX + SIBLING RE-HUNT — 3 edits landed + match wired source; no OTHER unhedged wired-set enumeration in the suite (remaining `STATE_PATH_RX`/`integrity-guard`/`VALID_TYPES` refs are mechanism-explanation prose or accurate completeness claims); working tree scoped to the 2 skill files                                                                                                                                                                                 | CLEAN     | Fix confirmed vs ground truth                         |
| R4    | MECHANICAL — new anchors (`integrity-guard.js`, `validate-bash-command.js`) resolve; documented `DIRECT` set == wired (positive allowlist); 0 stubs/markers introduced; disclosure 0 hits; 45 skill 207 lines, 43 skill 235 lines                                                                                                                                                                                                                                                   | CLEAN     | Convergence confirmed (R3 + R4 = 2 consecutive clean) |

## R2 out-of-scope / informational dispositions (verified, non-blocking)

- **Agent C absent-target set — pre-existing loom→BUILD-subset artifacts, BY-DESIGN.** `guides/co-setup/*.md`
  (14 citations, all framed `use_excluded`/"loom-authored"/"NOT distributed" — skill 45 exists to
  reconstruct that depth in-repo); `.claude/bin/ecosystem.json` (the write-target `/ecosystem-init` C1
  creates; gitignored `loom_only`); `specs/_certification.yaml` (consumer-seeded; loom ships the
  `.claude/templates/` seed which exists). All resolve in loom-canonical / are created at runtime; not
  loom-side defects, not durably fixable BUILD-side.
- **Agent B minor return-shape omissions beyond #3 — NOT fixed (fail-closed-focused, accurate).**
  `runEnrollmentCeremony` `opts` (7 cited, all real; omits only optional `[now]`/`[sign]` test seams) —
  accurate; no fix.

## Convergence criteria

1. 0 CRITICAL ✓ · 2. 0 HIGH ✓ · 3. 2 consecutive clean rounds (R3 verify-and-re-hunt + R4 mechanical) ✓ ·
2. every predicate / symbol / cross-ref / journal-type / command↔skill shared-step claim
   ground-truth-verified against `adjacency.js` / `journal-reserve.js::VALID_TYPES` / `integrity-guard.js::DIRECT`
   / `validate-bash-command.js::STATE_PATH_RX` / `genesis-ceremony.js` / `settings.json` ✓ ·
   5–7. N/A (COC-artifact suite — no new code modules, frontend, or eval-harness).

## KEY institutional lessons

- **The new `command-skill-parity.md` rule found NOTHING new in this suite — because #5's codify already
  closed it.** The first adversarial re-audit of the whole suite against a rule whose Origin IS the suite
  confirms the fix generalized: the guard lifecycle holds AND both sibling print-strings are byte-aligned.
  The value of the round was the CONFIRMATION (an errored/empty parity sweep would have read as false
  convergence per `evidence-first-claims.md` MUST-3) — every pair was compared with both surfaces quoted.
- **The recurring "citation must match the wired mechanism" class produced NO phantom in #12** — the
  first round since #9 where the phantom-added subclass was absent. What remained was the OMISSION
  subclass in ILLUSTRATIVE (not completeness) enumerations. The distinction is load-bearing: an
  illustrative list is honest as "e.g. X, Y (among others)"; the defect is presenting a partial list
  UNHEDGED so a future editor reads it as authoritative. The durable fix is the #11 pattern — anchor
  inline to the wired source ("the wired `DIRECT` set at `integrity-guard.js` is authoritative") so the
  next editor re-derives instead of trusting the partial prose. One sibling (`45:143`) already used the
  "(among others)" convention; the fix propagated it to the two that had drifted from it.
- **Positive-allowlist symmetry across illustrative vs completeness lists.** A completeness claim MUST
  equal the wired set (claim.md:27, VALID_TYPES); an illustrative list MUST either equal it OR hedge +
  anchor. Both dispositions end at the same place: the wired source is cited inline as authoritative.
