---
type: AMENDMENT
date: 2026-07-08
slug: independent-reconvergence-cert-helper-high
relates_to: 0029-AMENDMENT-independent-reconvergence-enrollment-ops-length-rationale
---

# AMENDMENT — Independent re-convergence surfaces a HIGH the prior 10 rounds + 3 appends missed

Extends journal/0029. This session (user directive: `/autonomize` + `/redteam to convergence`,
continuing from the prior session) ran a FRESH, fully-independent multi-agent redteam of the
Phase-1 onboarding COC suite on merged main (HEAD 7f0472c73, post PR #1621) — NOT trusting the
prior 10-round + THIRD-APPEND convergence self-reports. Doctrine: `/redteam` Step-1 "re-derive
every check from scratch; a prior round's self-report is an input to verify" +
`evidence-first-claims.md` MUST-3 (an errored/empty agent is zero evidence, never a clean round).

**Result: CONVERGED. 0 CRIT / 0 HIGH.** But the independent re-derivation surfaced a genuine
**HIGH** the prior rounds missed — which is exactly the value the re-convergence discipline exists
to capture.

## What the independent pass found (all verified against ground-truth source)

- **HIGH — `skills/42-certify` Step 2 wrong reservation helper.** The certify skill called the
  PURE `reserveJournalSlot("journal", {...})` — which computes off the filesystem only and emits
  NO signed `journal-slot-reservation` coordination-log record (`journal-reserve.js:260` docstring:
  "computes a slot from the filesystem only and emits [nothing]") — while the prose claimed
  fold-anchored semantics. `journal-write-guard.js` (docstring lines 32-34) READS existing
  reservations FROM THE FOLD and refuses a Write to an unreserved slot. So an operator following
  `/certify` would halt "slot unreserved" at Step 3. Fixed to
  `reserveJournalSlotSigned(process.cwd(), {dir:"journal", identity, type, topic})` + the real
  `{ok, reservation:{slot,filename,...}, record}` return shape + Step-3 reads `r.reservation.filename`.
  The sibling suite files (`45-genesis-bootstrap:176`, `coc-onboarding-specialist:83`) already
  cited the Signed variant — certify was the lone outlier. The prior rounds treated 42-certify as
  partly out-of-suite-scope (its `name:` was dispositioned no-change), so this functional bug in
  its Step-2 code block was never deeply audited until this pass.

- **MED — substrate §6 stale + bare citations.** Both "field presence by fold rules 5 + 9b"
  sentences cited `coordination-log.js:1125-1128` for the `archive_genN_tip_hash` presence check,
  but those lines are the rule-1 signature-verify code (`"rule 1: signature did not verify"`); the
  real check is the rule-5 guard at `coordination-log.js:1333` (`"rule 5: checkpoint missing
required field archive_genN_tip_hash"`). Bare+stale line cites replaced with grep-stable symbol
  anchors (`fold-rule-9b.js::foldGenerationRotation` R9-A-01) per `symbol-anchored-citations.md`.
  The F51/F53/F86-CLOSED historical forest receipts (bare `:295-343` cites) are commit-SHA-anchored
  frozen audit records — LEFT AS-IS, the same exempt class as the substrate:378 F86 receipt.

- **LOW cluster — `detectStateFileMutation` symbol-home (7 sites).** `validate-bash-command.js`
  INVOKES `detectStateFileMutationSegmentAware` (the segment-aware wrapper, defined in
  `violation-patterns.js`), not a same-file `detectStateFileMutation`. Corrected the `::` home
  claims across enrollment-operations.md, coc-onboarding-specialist, skill-45, skill-43.

- **LOW — self-introduced count.** The R1 SegmentAware rewording added a line to
  enrollment-operations.md (`wc -l` 268 -> 269); the length rationale still said "268 lines".
  Switched to the drift-robust approximate "~270 lines" (sibling convention).

- **LOW (same-class, R2) — residual "loom-internal <guide>" drift.** The prior appends fixed the
  use_excluded-guide framing in skill-45 + skill-43 but left the identical "loom-internal"
  mischaracterization in `commands/whoami.md` (x2) + `commands/ecosystem-init.md` (x1). Aligned all
  three per `zero-tolerance.md` Rule 1a (scanner-surface symmetry). The `(loom-internal reference)`
  redaction markers are a DIFFERENT class (genericized loom-only spec citations) — correctly untouched.

## Convergence

R1 (reviewer + cc-architect + security-reviewer, 3 independent agents, genuinely run) -> fixes
(commit 6fba35ba5) -> R2 (same-class + self-introduced-count) -> fixes (commit 669c5437b) -> R3
(mechanical battery: 23 `::`symbol citations resolve, all cited files exist, frontmatter parses,
0 residual drift, disclosure scanner exit 0) CLEAN -> R4 (cross-file consistency + semantic
validation of the HIGH fix against journal-write-guard's actual fold-read behavior) CLEAN = **2
consecutive clean rounds; 0 CRIT / 0 HIGH.**

**Evidence-gate note:** the R2 subagent wave died on an account usage limit ("resets 6:30pm"). Per
the `/redteam` reviewer-dispatch evidence gate + `evidence-first-claims.md` MUST-3, an errored agent
is ZERO evidence, NOT a clean round — so R2-R4 verification was re-run correctly by the orchestrator
directly (mechanical re-derivation with real command output), not counted as clean-by-omission. The
`self-referential-codify.md` Rule 1 multi-agent gate is satisfied by R1's 3 genuinely-run independent
specialists (surfaces touched: enrollment-operations.md, substrate + genesis-migration-n1 skills,
commands/ecosystem-init.md).

## Disposition

2 commits on codify branch `codify/esperie-2026-07-08` (6fba35ba5 R1 + 669c5437b R2). FOURTH APPEND
to `.claude/.proposals/latest.yaml` `onboarding-suite-accuracy-corrections` so loom Gate-1 distributes
the corrected mechanics — the HIGH cert-helper fix especially, an operator-breaking bug every
downstream consumer of the synced suite would otherwise inherit. `last_codified` NOT advanced (scoped
accuracy landing; the 66 telemetry observations remain F24). Program remains complete + release-clean.
