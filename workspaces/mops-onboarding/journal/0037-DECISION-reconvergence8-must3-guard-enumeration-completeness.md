---
type: DECISION
date: 2026-07-09
slug: reconvergence8-must3-guard-enumeration-completeness
relates_to: 0036-AMENDMENT-reconvergence7-must3-readwrite-accuracy-f2-refutation
---

# DECISION — re-convergence #8 completes the MUST-3 guard-firing enumeration (fourth pass)

Re-convergence #7 (journal/0036, PR #1627) rewrote enrollment-operations.md MUST-3 for
read/write-AGNOSTIC accuracy and merged to main. This session (`/autonomize` + `/redteam`, **4
rounds, 9 adversarial agent-passes**) ran a fresh adversarial audit of that MERGED-main state and
surfaced that the fix corrected the layers' SEMANTICS but left the layer COUNT itself incomplete.
Full report: `workspaces/mops-onboarding/04-validate/redteam-2026-07-09-reconvergence8.md`.

## The finding (one class, one level deeper than #7)

MUST-3 enumerated THREE guard-firing surfaces — interpreter (`-c`/`-e`/`-m`) body, redirect,
file-utility body (the `detectStateFileMutation` layers) — but OMITTED the FOURTH whole-command
pass, `detectHeredocWriteRunBundle` (`violation-patterns.js`, invoked at the tail of
`detectStateFileMutationSegmentAware`). That pass fires when ONE command BOTH authors a heredoc
script whose body carries a `STATE_PATH_RX` literal AND executes that same script — the natural
inline `cat >f <<EOF …STATE_PATH… EOF && node f` idiom. So an operator building the obvious
one-command form of MUST-3's "author the script, run it bare" DO example is blocked by a detector
the rule never named. Same finding-class as #7's read/write-agnostic fix — **a guard's DESCRIPTION
must match its DETECTION mechanism** — one level deeper: the "three-layer" docstring hid a fourth
pass. Surfaced via LIVE-FIRE (Round-1 Agent A's own probe command hit the block), then confirmed by
DIRECT guard execution in Round 3 (the detector was run script-by-path and its verdicts quoted).

## What changed (2 working-tree files → committed 0f8e15732 on codify/esperie-2026-07-09)

- `enrollment-operations.md` MUST-3: enumeration now names the 4th `detectHeredocWriteRunBundle`
  pass + a DO-NOT heredoc-bundle example (author + run as TWO separate commands); Why-line invariant
  scoped to "in an interpreter / redirect / file-utility body … (interpreter bodies fire on a read
  too)" — a bare `cat <state>` read is NOT caught by any layer.
- `45-genesis-bootstrap/SKILL.md` § script-by-path: read/write-AGNOSTIC property scoped to the
  interpreter `-c`/`-e`/`-m` body layer ONLY (Layers 1–2 require a write construct); gh-bundling
  claim restored to a conditional; heredoc-bundle warning names the fourth pass.

## Convergence + gate satisfaction

R1 (MED + 2 LOW → fixed) → R2 (fixes verified accurate + 2 pre-existing LOWs → fixed) → R3 (CLEAN,
direct guard execution) → R4 (CLEAN, exhaustive) = **2 consecutive fully-clean rounds (R3+R4); 0
CRIT / 0 HIGH every round.** `enrollment-operations.md` is on the `self-referential-codify.md` Rule 2
allowlist → the mandatory multi-agent redteam-with-tests round is SATISFIED by the 4-round
convergence (reviewer + security-reviewer + independent structural verifier, run in parallel each
round). `45-genesis-bootstrap/SKILL.md` is the deliberately-omitted depth-file (skill-only edit →
cc-architect doc-drift check, covered by the rounds).

Distributable invariant re-verified GREEN after every edit (roster PLACEHOLDER, 0/6
coordination-enforcement hooks committed, probe-phase-guard present, disclosure scanner exit 0 /
1559 files / 0 findings). Coordination OFF / SOLO throughout (`person_id=null`; codify-branch
convention). The two `rule_violation` observations at 06:47 are this session's own guard-probes
(`trust-posture/state-file-mutation` layer 3 + layer 1) — audit telemetry, not real violations.

## Accepted non-blocking (carried for the canonical loom pass)

- `45-genesis:136` "three-layer detector" framing — quotes the `detectStateFileMutation` docstring
  for the per-segment core then names the 4th pass separately; Round-4 reviewer rated it explicitly
  NOT a finding. A "three-layer per-segment core + a fourth whole-command pass" tightening is
  available but was not taken (would reset the converged clean-round bracket).
- MUST-3 SAFE-helper over-density (carried from #7) — extraction to 45-genesis is the loom F5 pass.

## Institutional lesson

A guard's firing-surface ENUMERATION must match its detection mechanism COMPLETELY — a "three-layer"
docstring can hide a fourth whole-command pass. #7 fixed the layers' semantics; #8 found the count.
Direct guard execution (Round 3) beats prose audit for guard-mechanics claims: it turned "the prose
looks accurate" into "the guard empirically blocks/passes exactly as documented." And: own the line
you edit — the R2 gh-bundling LOW was pre-existing, but my R1 fix had strengthened its hedge, so
fixing it (not deferring it as "pre-existing") was the zero-tolerance-correct disposition.

BUILD→loom proposal appended (`latest.yaml` changes[15], `pending_review`) for cross-SDK +
downstream distribution of the completed enumeration.
