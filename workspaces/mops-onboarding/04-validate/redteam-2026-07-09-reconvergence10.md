# /redteam — mops-onboarding re-convergence #10 (fresh adversarial audit on merged main + #9 close-out) — 2026-07-09

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence. Scope: fresh adversarial audit of the
re-convergence #9 state now MERGED on main (PR #1629) PLUS the #9 close-out (PR #1630 /
`925e37c07` — journal/0040 disclosure closure + sweep report). Re-verify #9's fixes hold on
merged main, re-verify the disclosure forward-fix + owner-decision closure, verify the close-out
receipts are accurate, AND hunt the full onboarding/enrollment artifact suite for anything the
prior 9 rounds missed.

## Outcome

**CONVERGED.** 4 rounds: R1 mechanical (clean) → R2 (2 parallel adversarial agents; **1 MED
found**) → fix applied → R3 (3-agent self-referential-codify gate: reviewer + security-reviewer +
cc-architect; clean) → R4 mechanical (clean). **2 consecutive clean rounds (R3 + R4); 0 CRITICAL;
0 HIGH.** All edits working-tree only on the codify branch (BUILD-repo owner commit gate).

## The one new finding — `DEFER` phantom journal-type in the /onboard read-path (MED, FIXED)

The `/onboard` read-path cited `DEFER` as a canonical journal type — a real-but-wrong citation
(a journal type that cannot exist) invisible to 9 prior rounds because it _resolves_ as a token
yet contradicts the wired ground truth AND the sibling `/certify` artifacts.

- `.claude/commands/onboard.md` (§ "Read the active workspace + recent decisions"): filtered
  `DECISION-` / `DISCOVERY-` / **`DEFER-`** entries.
- `.claude/skills/41-onboard/SKILL.md` (Step 3): `types=["DECISION","DISCOVERY",**"DEFER"**]`.

Ground truth that contradicts it: `journal-reserve.js::VALID_TYPES` =
`{DECISION, DISCOVERY, TRADE-OFF, RISK, CONNECTION, GAP, AMENDMENT}` (no `DEFER`; reservation
fails closed on a non-member); `.claude/rules/journal.md` canonical enum (no `DEFER`); and the
sibling `/certify` pair (`certify.md` + `42-certify/SKILL.md`) which explicitly state "`DEFER` is
NOT a canonical journal type." Real deferrals are `DECISION`-typed with "defer" in the _topic_
slot (e.g. `NNNN-DECISION-certify-defer-…`), so the `DEFER-` filter branch was **dead code**
(matched zero entries) — no operator-visible data loss, hence MED not HIGH.

**Fix (this session, mechanical 2-token removal across the command↔skill pair, same shard per
`command-skill-parity.md` MUST-1):** dropped `DEFER` from both filters; added a ground-truth-cited
note (`journal-reserve.js::VALID_TYPES` / `rules/journal.md`) that deferrals are `DECISION`-typed
and already surfaced by the `DECISION-` filter. Verified: no `DEFER`-_typed_ journal file exists
anywhere in the tree; `onboard.md` stays 92 lines (≤150). Routed to loom via the BUILD→loom
proposal (`latest.yaml`) for cross-SDK + downstream distribution — the onboard suite is
loom-synced, so every downstream copy carries the same phantom.

## Findings + dispositions (by round)

| Round | Finding                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | Sev   | Disposition                                           |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- | ----------------------------------------------------- |
| R1    | MECHANICAL — #9's 3 guard-symbol fixes (whoami `…SegmentAware`, enrollment-ops MUST-4 foldLog/resolveIdentity split, MUST-1 both genesis-guard block branches) all HOLD on merged main; disclosure forward-fix intact on branch + `origin/main`; `.example` schema still tracked; close-out `925e37c07` = pure receipts (66 insertions, 0 code/artifact change); journal/0040's "F6 routed via latest.yaml LOOM-TOOL FOLLOW-UP FLAG" claim VERIFIED (latest.yaml lines 1006–1052, appended by `a19372b4e`); no real CI identifier in any tracked file           | CLEAN | —                                                     |
| R2    | ADVERSARIAL (2 parallel agents). **Agent A (guard-mechanics/symbol-ownership):** 3/3 #9 fixes hold; **`DEFER` phantom journal-type in onboard.md + 41-onboard/SKILL.md** — MED. **Agent B (disclosure + receipt-accuracy):** disclosure remediation COMPLETE + verified on main (0 real CI identifiers tree-wide; lone remaining `*.operator.local.md` is the labeled-SYNTHETIC scanner fixture); all 4 mandated receipt claims + supporting figures (1,276 commits, ~7 weeks, 15 issues, 3 forks) ACCURATE; proposal correctly scrubbed (class/file:line only) | 1 MED | MED FIXED (2-token removal); Agent B CLEAN            |
| R3    | SELF-REFERENTIAL-CODIFY GATE (onboard.md is on the allowlist → multi-agent redteam-with-tests per `self-referential-codify.md` Rule 1). reviewer + security-reviewer + cc-architect, parallel. All three: fix CORRECT vs ground truth; command↔skill parity CONSISTENT; no regression (dropped branch was dead code); no dangling refs; onboard.md ≤150; each independently hunted the full onboard suite — no new drift                                                                                                                                        | CLEAN | Fix confirmed by 3 independent agents                 |
| R4    | MECHANICAL — working tree carries only the 2 fixed files + untracked `.session-notes`; leaked file still untracked, no new `*.operator.local.md` (closes the security-reviewer Bash caveat); DEFER phantom gone from both surfaces; DECISION/DISCOVERY retained                                                                                                                                                                                                                                                                                                 | CLEAN | Convergence confirmed (R3 + R4 = 2 consecutive clean) |

## Convergence criteria

1. 0 CRITICAL ✓ · 2. 0 HIGH ✓ · 3. 2 consecutive clean rounds (R3 self-ref gate + R4 mechanical)
   ✓ · 4. every guard-mechanics / symbol / cross-ref / journal-type claim ground-truth-verified
   against `validate-bash-command.js` / `violation-patterns.js` / `journal-reserve.js` /
   `genesis-anchor-guard.js` / `operator-id.js` / `coordination-log.js` / `journal.md` ✓ · 5–7. N/A
   (COC-artifact suite — no new code modules, frontend, or eval-harness).

## KEY institutional lessons

- **The "citation must match the wired mechanism" class extends to a canonical VOCABULARY, not
  just a symbol.** whoami (#9) cited a real-but-wrong _symbol_; onboard (#10) cited a _type token_
  that is not in the canonical set at all (`journal-reserve.js::VALID_TYPES`). Both resolve as
  tokens and pass grep/dangling-ref sweeps; only cross-artifact + wired-source verification (here:
  the sibling `/certify` pair already carried the correct ground truth) catches them.
- **A sibling artifact that already states the correct ground truth is the loudest signal of drift
  in its neighbour.** `/certify` explicitly said "DEFER is NOT a canonical journal type"; `/onboard`
  filtered on `DEFER-`. The two shipped side-by-side, contradicting each other, through 9 rounds —
  a command↔skill + cross-command parity sweep is what surfaces it (`command-skill-parity.md` MUST-2).
- **A dead filter branch is still a defect.** The `DEFER-` branch matched zero entries (no data
  loss) but taught every reader — and every downstream synced copy — a false canonical vocabulary.
