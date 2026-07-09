# /redteam — mops-onboarding re-convergence #8 (guard-mechanics precision on merged main) — 2026-07-09

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence. Scope: fresh adversarial audit of the
re-convergence #7 state now MERGED on main (PR #1627, `e32da19df`) — re-verify the #7 edits hold
on committed HEAD AND hunt for anything #7's 7 rounds missed across the onboarding artifact surface.
**4 rounds, 9 adversarial agent-passes** (waves of 2–3, throttle-aware). COC-artifact suite (no
code/tests/frontend) — the Criteria-4 stand-in is ground-truth verification against the actual
hook/lib source, including DIRECT guard execution (Round 3).

## Outcome

**CONVERGED. 2 working-tree files edited** (uncommitted — BUILD-repo commit gate; land via
`/codify` → `codify/esperie-2026-07-09` → PR → admin-merge + a BUILD→loom proposal for cross-SDK
distribution). Distributable invariant re-verified GREEN on committed HEAD after every edit: roster
`PLACEHOLDER-owner`/`0000000`/gen 0 · 0/6 coordination-enforcement hooks in committed
`settings.json` · `probe-phase-guard` present · disclosure scanner exit 0 (1559 files, 0 findings).

Files: `.claude/rules/enrollment-operations.md` (MUST-3 guard-mechanics enumeration) ·
`.claude/skills/45-genesis-bootstrap/SKILL.md` (§ script-by-path).

## The finding — MUST-3's guard-firing enumeration omitted a fourth pass (FIXED)

Re-convergence #7 established that the STATE_PATH guard (`detectStateFileMutationSegmentAware`) is
read/write-AGNOSTIC. #8 surfaced that MUST-3's **enumeration of firing surfaces** was INCOMPLETE:
it named the interpreter (`-c`/`-e`/`-m`), redirect, and file-utility bodies (the three
`detectStateFileMutation` layers) but OMITTED the **fourth whole-command pass** —
`detectHeredocWriteRunBundle` (`violation-patterns.js:1575`, wired into the segment-aware wrapper at
`:1721`). That pass fires when ONE command BOTH authors a heredoc script whose body carries a
`STATE_PATH_RX` literal AND executes that same script — the exact `cat >f <<EOF …literal… EOF && node f`
idiom. This is the same finding-class #7 chased: **a guard's DESCRIPTION must match its DETECTION
mechanism, not its layer count.** Surfaced via LIVE-FIRE (Round-1 Agent A's own probe command hit
the block), then confirmed by direct guard execution in Round 3.

Adjacent-flag resolution: the sibling runbooks do NOT self-block — `42-certify` Step 4/5 author +
run "as two separate Bash commands" (`SKILL.md:209,230,238`) and `45-genesis-bootstrap:160` already
warned against heredoc bundling. So there was NO live self-block bug; the gap was purely the rule's
enumeration precision. Fixes stayed minimal (the #7 report flagged MUST-3 over-density).

## Findings + dispositions (by round)

| Round | Finding(s)                                                                                                                                                                                          | Severity | Disposition                                                                                             |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------- |
| R1    | MUST-3 guard enumeration omits the 4th `detectHeredocWriteRunBundle` whole-command pass (live-fire evidence)                                                                                        | MED      | Added the 4th pass to the enumeration + a DO-NOT heredoc-bundle example (author + run as TWO commands)  |
| R1    | 45-genesis over-generalized "path-presence-based, not mutation-aware" to the WHOLE 3-layer detector (Layers 1–2 require a write construct)                                                          | LOW      | Scoped the read/write-AGNOSTIC property to the interpreter `-c`/`-e`/`-m` body layer only               |
| R1    | MUST-3 "watched state file" term overloads vs MUST-2's integrity-guard set                                                                                                                          | LOW      | Accepted non-blocking — MUST-3 already binds it as "`STATE_PATH_RX` (the watched state files)"; no edit |
| R2    | CLEAN — R1 fixes ground-truth-verified accurate (reviewer + security-reviewer)                                                                                                                      | CLEAN    | —                                                                                                       |
| R2    | (pre-existing) 45-genesis "bundling with `gh …` re-introduces a scanned token" — I had strengthened a conditional; loose unconditional claim                                                        | LOW      | Restored conditional: "can re-introduce … (if the bundled command itself names a watched path)"         |
| R2    | (pre-existing) MUST-3 Why-line invariant "no watched-state-path LITERAL on the command line (read OR write)" over-blankets — a bare `cat <state>` read is NOT caught                                | LOW      | Scoped to "in an interpreter / redirect / file-utility body … (interpreter bodies fire on a read too)"  |
| R3    | CLEAN — reviewer full source audit + independent verifier DIRECTLY EXECUTED the guard: (a) heredoc bundle → BLOCK, (b) bare read → PASS, (c) bare `node <file>` → PASS; all control positives fired | CLEAN    | —                                                                                                       |
| R4    | CLEAN — final exhaustive reviewer + security-reviewer; every claim/symbol/cross-ref ground-truth-resolves; distributable invariant + disclosure green                                               | CLEAN    | Convergence confirmed                                                                                   |

## Convergence criteria

1. 0 CRITICAL ✓ · 2. 0 HIGH ✓ · 3. **2 consecutive clean rounds** — R3 (2 agents, incl. direct
   guard execution) + R4 (2 agents, exhaustive) ✓ · 4. every guard-mechanics claim + every
   cross-reference ground-truth-verified against `violation-patterns.js` /
   `validate-bash-command.js` / `journal-reserve.js` / `coc-emit.js` / `coc-append.js` / `whoami.md`
   / `42-certify` — AND empirically confirmed by direct guard execution (R3) · 5–7. N/A
   (COC-artifact suite).

## Accepted non-blocking (documented; NOT convergence-blocking)

- **45-genesis:136 "three-layer detector" framing** — the sentence quotes the
  `detectStateFileMutation` docstring ("three-layer") for the per-segment core, then names the 4th
  `detectHeredocWriteRunBundle` pass separately at :164. Round-4 reviewer rated it explicitly NOT a
  finding: "framing-depth difference within tolerance, consistent across the artifact set" — both
  mechanisms are named in the same section and no behavior is misstated. A precise single-word
  tightening ("three-layer per-segment core + a fourth whole-command pass") is available for a
  future canonical loom pass but was NOT taken here — it would reset the converged 2-clean-round
  bracket for a not-a-finding nuance.
- **MUST-3 over-density** (carried from #7) — the SAFE-helper qualification paragraph remains dense;
  structural extraction to `skills/45-genesis-bootstrap` is best done in the canonical loom pass
  (F5, blocked-on-loom). Path-scoped rule → no baseline-emission cost.

## KEY institutional lessons (candidates for /codify)

- **A guard's firing-surface ENUMERATION must match its DETECTION mechanism completely — a "three
  layer" docstring can hide a fourth whole-command pass.** The #7 read/write-agnostic accuracy fix
  corrected the layers' SEMANTICS; #8 found the layer COUNT itself was incomplete (the
  `detectHeredocWriteRunBundle` bundle pass runs after the per-segment loop). Same class, one level
  deeper — confirming the #7 lesson that partial enumeration is the recurring trap; run it to
  completion across BOTH the rule and its depth-file.
- **Direct guard execution beats prose audit for guard-mechanics claims.** Round 3's verifier ran
  the actual detector (script-by-path) against every documented command form and quoted the real
  verdicts — turning "the prose looks accurate" into "the guard empirically blocks/passes exactly
  as documented," including the bare-read PASS that validates the Why-line scoping fix.
- **Own the line you edit.** The R2 gh-bundling LOW was pre-existing, but my R1 fix had strengthened
  its hedge ("can re-introduce" → "re-introduces"), making a loose claim less accurate. Fixing the
  line I touched (not deferring it as "pre-existing") is the zero-tolerance-correct disposition.
