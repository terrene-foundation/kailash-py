# /redteam — mops-onboarding re-convergence #11 (fresh adversarial audit on merged main, post-#10) — 2026-07-09

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED, coordination OFF).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence, maximally parallelized (time-pressure framing →
parallelization, NOT procedure-drop, per `time-pressure-discipline.md`). Scope: fresh adversarial audit
of the re-convergence #10 state now MERGED on main (PRs #1630 `1bb097e4e` / #1631 `e97808d20`) — re-verify
#10's DEFER fix holds, and hunt the full onboarding/coordination/enrollment/genesis artifact suite for
anything the prior 10 rounds missed, across three distinct drift classes in parallel.

## Outcome

**CONVERGED.** R1 mechanical (clean) → R2 (3 parallel adversarial agents; **1 in-scope MED found** +
dispositions) → fix applied → R3 (verify fix + sibling re-hunt; clean) → R4 mechanical (clean).
**2 consecutive clean rounds (R3 + R4); 0 CRITICAL; 0 HIGH.** All edits working-tree only (BUILD-repo
owner commit gate).

## The one new in-scope finding — `axis-3` phantom + `glob`/`phase` omissions in `/claim` (MED, FIXED)

Same class the #9 (guard-symbol) and #10 (canonical journal-type vocabulary) rounds surfaced — a
citation that resolves as text yet disagrees with the wired mechanism — this time a SAME-predicate
display-token set in the `/claim` command.

`.claude/commands/claim.md:27` (Step 6 SAME-dispatch) printed the matched predicate as
`(exact / dir-contains / workspace / commit-cohort / axis-3)`. Wired ground truth
`.claude/hooks/lib/adjacency.js::sameReason` returns `predicate: pred` (lines 271/371) where `pred` is a
`_matchX` helper literal:

| Wired literal     | `adjacency.js` line |
| ----------------- | ------------------- |
| `exact`           | 172                 |
| `glob`            | 173                 |
| `dir-contains`    | 183                 |
| `workspace`       | 186                 |
| `commit-cohort`   | 202                 |
| `phase`           | 217–218             |
| `composed-axis-3` | 235                 |

Three defects vs that set: **(a) `axis-3` is a PHANTOM** — the code emits `composed-axis-3`, never bare
`axis-3` (the exact #10 DEFER class — a token that resolves as text but is absent from the wired return
set); **(b) `glob` OMITTED**; **(c) `phase` OMITTED** (both genuine `sameReason` return literals a SAME
halt would print). MED — teaches false/incomplete vocabulary; resolution paths are predicate-agnostic so
no guard dropped / no operator misroute (not HIGH). Single-command drift: `claim.md` has NO backing skill,
so no command↔skill parity pair to mirror (unlike the #10 onboard command↔skill pair).

**Fix (this session, source-verified):** replaced the enumeration with the full wired set
`(exact / glob / dir-contains / workspace / commit-cohort / phase / composed-axis-3)` + an inline
"the full wired `adjacency.js::sameReason` `predicate` return set" anchor so future edits re-derive from
the wired source rather than re-enumerate. Each literal grep-verified against `adjacency.js` (lines above).
Routed to loom via the BUILD→loom proposal (`latest.yaml`, GLOBAL) — the coordination suite is loom-synced,
so every downstream copy carries the same phantom. `claim.md` is NOT on the `self-referential-codify.md`
Rule 2 allowlist → no mandatory multi-agent gate (a citation-vocabulary correction verified against wired
source).

## Findings + dispositions (by round)

| Round | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Sev   | Disposition                                           |
| ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | ----------------------------------------------------- |
| R1    | MECHANICAL — #10 DEFER phantom gone (0 both surfaces); 0 DEFER-typed journal files tree-wide; `VALID_TYPES` intact; 16 marker hits all legitimate detector-prose / SQL-`?`-placeholder / PLACEHOLDER-genesis / templates (0 real stubs); 0 real CI identifiers in tracked files; onboard.md 92 lines                                                                                                                                                                                                                                                                               | CLEAN | —                                                     |
| R2    | ADVERSARIAL (3 parallel agents). **A (parity/phantom-vocab):** full onboarding/coordination/enrollment suite — 1 MED (`claim.md` `axis-3` phantom + `glob`/`phase` omissions); all other pairs (onboard↔41, certify↔42, enroll↔44, ecosystem↔43, claims/release-claim/whoami/posture) verified against wired source, CLEAN. **B (guard-symbol):** 91/92 symbol citations verified accurate; 1 flagged (`multi-operator-coordination-substrate.md` matcher `Edit\|Write\|NotebookEdit`). **C (dangling/disclosure/markers):** disclosure CLEAN, markers CLEAN, 4 MED dangling refs. | 1 MED | MED FIXED; B-1 + D1–D4 dispositioned (below)          |
| R3    | VERIFY FIX + SIBLING RE-HUNT — fix holds (all 7 wired literals, ordered); no residual bare-`axis-3` token; no predicate/record enumeration to drift in claims/release-claim/whoami/posture; `latest.yaml` valid YAML (18 changes, pending_review); working tree scoped to claim.md + latest.yaml                                                                                                                                                                                                                                                                                   | CLEAN | Fix confirmed vs ground truth                         |
| R4    | MECHANICAL — #10 DEFER regression check clean (0); 0 disclosure leaks; my citation `adjacency.js::sameReason` resolves (no new dangling ref); claim.md 79 lines (≤150); 0 stubs introduced; ground truth reconfirmed (`predicate: pred` @ 271/371)                                                                                                                                                                                                                                                                                                                                 | CLEAN | Convergence confirmed (R3 + R4 = 2 consecutive clean) |

## R2 out-of-scope dispositions (verified, non-blocking)

- **B-1 (guard-symbol Agent) — `multi-operator-coordination-substrate.md` matcher `Edit|Write|NotebookEdit` — BY-DESIGN, NOT a defect.** The skill §7 describes the **loom-canonical** codex-mcp-guard wiring; `artifact-flow.md` (loom-canonical, synced in-repo) independently confirms the disclosure-guard hook is registered on `Edit|Write|NotebookEdit` in loom (F3 Level-1, journal/0335). This repo's `settings.json` is the deliberately-stripped un-enrolled subset (`Edit|Write`; `cross-ecosystem-disclosure-guard` = 0 occurrences here — `project_kailashpy_ships_unenrolled`). The loom corpus is internally consistent; editing the skill to `Edit|Write` would corrupt the canonical description. **Do not edit.**
- **D1–D4 (dangling Agent) — pre-existing loom→BUILD-subset artifacts, OUTSIDE the onboarding suite.** D1 (`test-harness-probe` skill → loom-only `test-harness/` + command), D2 (`reviewer.md:81` → loom-only `test-harness/README.md`), D4 (`ci-runners.operator.local.example.md:4` → `variants/py/rules/ci-runners.md`) all have targets that **resolve in loom-canonical** and are absent only in this composed public subset — not loom-side defects, not durably fixable BUILD-side. D3 (`todo-github-sync.md:484` self-ref → `guides/todo-github-sync-guide.md`) is a genuine loom-side stale self-ref but in a `deployment-git` skill, outside the coordination/onboarding suite. **Surfaced to user; recommended for a separate loom-forest item, not this convergence.**
- **LOW (disclosure Agent) — real operator display-name `jack-hong` in shipped `user-flow-validation-walk-discipline.md` + a tracked journal.** Display-name string (not a secret/credential/roster person_id); PUBLIC-shipped loom-authored skill. Worth a scrub-to-`<operator-display-id>` pass at loom; outside this suite. Surfaced to user.
- **KNOWN residual (disclosure Agent) — journal/0038 git-history window.** The real `ci-runners.operator.local.md` values sat on the public remote `e6144ee98`→`3875ec6e0` (~7 weeks); current tree CLEAN, fix landed, history-scrub is a standing user-gated decision (already documented). Not a new finding.

## Convergence criteria

1. 0 CRITICAL ✓ · 2. 0 HIGH ✓ · 3. 2 consecutive clean rounds (R3 verify-and-re-hunt + R4 mechanical) ✓ ·
2. every predicate / symbol / cross-ref / journal-type claim ground-truth-verified against
   `adjacency.js::sameReason` / `journal-reserve.js::VALID_TYPES` / `settings.json` / `artifact-flow.md`
   (Agent B: 91/92 verified; F1: fixed + grep-verified) ✓ · 5–7. N/A (COC-artifact suite — no new code
   modules, frontend, or eval-harness).

## KEY institutional lessons

- **The "citation must match the wired mechanism" class has now recurred across THREE artifact kinds:**
  a guard SYMBOL (#9, whoami `…SegmentAware`), a canonical journal-TYPE vocabulary (#10, onboard `DEFER`),
  and now a SAME-predicate DISPLAY-TOKEN set (#11, claim `axis-3`/`glob`/`phase`). All three resolve as
  text and pass grep/dangling-ref sweeps; only re-derivation from the WIRED source (`adjacency.js`)
  catches them. The durable fix pattern is the same each time: cite the wired source inline as the anchor
  so the next editor re-derives instead of re-enumerating.
- **An enumeration is drift-prone in BOTH directions.** claim.md was wrong three ways at once: one phantom
  ADDED (`axis-3`) and two real literals OMITTED (`glob`, `phase`). A positive-allowlist mindset — "the
  documented set MUST equal the wired return set" — catches both; spot-checking only the listed tokens
  catches neither omission.
- **Adversarial breadth vs BUILD-subset noise.** A repo-wide dangling-ref sweep surfaces many pre-existing
  loom→BUILD-subset artifacts (targets that resolve in loom-canonical, absent in the composed public
  subset). The discipline is to separate a genuine loom-side defect (resolve-nowhere, e.g. claim `axis-3`)
  from a subset-composition artifact (resolves in loom) — the former is owned + routed; the latter is
  documented, not "fixed" BUILD-side where the edit would be overwritten by `/sync`.
