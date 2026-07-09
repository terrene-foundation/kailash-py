# /redteam — mops-onboarding re-convergence #9 (fresh adversarial audit on merged main) — 2026-07-09

Repo: `terrene-foundation/kailash-py` (PUBLIC distributable BUILD, ships UN-ENROLLED).
Posture: **L5_DELEGATED** (fresh-repo default; `.claude/learning/` gitignored → reads fresh).
Method: `/autonomize` + `/redteam` to convergence. Scope: fresh adversarial audit of the
re-convergence #8 state now MERGED on main (PR #1628, `4689b7204`) — re-verify #8's edits hold
AND hunt across the FULL onboarding artifact + distributable/disclosure surface for anything the
prior 8 rounds missed. **3 rounds; Round 1 = 3 parallel adversarial agents** (guard-mechanics
ground-truth · cross-artifact consistency · distributable/disclosure security), Round 2 =
confirmation + fresh sweep (cc-architect), Round 3 = mechanical.

## Outcome

**Onboarding-artifact surface: CONVERGED** (1 MED + 3 LOW fixed; R2+R3 clean). **One HIGH
disclosure finding surfaced OUTSIDE the onboarding suite — FORWARD-FIXED in working tree, with
two user-gated/follow-up tails OPEN**, so re-convergence #9 is **NOT declared fully converged**
this session (honest disposition per `verify-resource-existence.md` MUST-4 — no self-attested
convergence over an open HIGH).

All edits are working-tree only (BUILD-repo commit gate — commits stay with the owner). 5 files
touched: `.claude/commands/whoami.md`, `.claude/rules/enrollment-operations.md`, `.gitignore`,
and a staged untrack of `.claude/rules/ci-runners.operator.local.md`.

## The HIGH finding — operator-local CI values committed to the PUBLIC repo (disclosure #260/#252)

`.claude/rules/ci-runners.operator.local.md` declares itself "gitignored, never committed" but is
TRACKED on `origin/main` since 2026-05-18 (`e6144ee98`, ~7 weeks), carrying 3 real CI infra
identifiers (`:17-19,:27,:33,:37` — referenced by location, not reproduced). BOTH safety nets
were absent: `.gitignore` lacked the pattern, AND the disclosure scanner unconditionally skips
`.operator.local.md` (`scan-synced-disclosure.mjs:276`) where the sibling `.local.json` skip was
made destination-conditional by issue #352. Full detail + evidence chain + open tails:
`journal/0038-RISK-committed-operator-local-ci-values-public-repo.md`.

**Forward-fix (this session, safe/reversible):** added `.gitignore` glob
`.claude/rules/*.operator.local.md` (verified to cover the real file, leave the `.example`
schema tracked); `git rm --cached` the leaked file (staged untrack, local copy preserved).
**OPEN tails:** (1) public git-history purge (filter-repo + force-push) — USER-GATED
(irreversible); (2) scanner line-276 parity fix — deferred to its own gated codify
(`self-referential-codify.md` allowlist + loom-distributed-tool semantics).

## Findings + dispositions (by round)

| Round | Finding                                                                                                                                                                                 | Sev      | Disposition                                                                                                                                                         |
| ----- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1    | `whoami.md:47` cites `detectStateFileMutation` (the internal primitive in `violation-patterns.js`) — every sibling artifact + the wired guard use `detectStateFileMutationSegmentAware` | MED      | FIXED — one-token symbol correction; now aligned with all 4 siblings + the `validate-bash-command.js:24/458/527` wiring                                             |
| R1    | `enrollment-operations.md` MUST-4 DO-example: fold + identity "both read the gitignored log" — `resolveIdentity` reads the COMMITTED roster                                             | LOW      | FIXED — split the parenthetical: foldLog folds the gitignored log's records, resolveIdentity reads the committed roster                                             |
| R1    | `enrollment-operations.md` MUST-1: genesis-guard BLOCK "only AFTER a real roster exists" omits the roster-absent/records-present (enrolled-then-deleted) block branch                   | LOW      | FIXED — sentence now names both `genesis-anchor-guard.js` block branches                                                                                            |
| R1    | **`ci-runners.operator.local.md` committed to public repo** (see above)                                                                                                                 | **HIGH** | FORWARD-FIXED (gitignore + untrack); history-purge + scanner-fix tails OPEN                                                                                         |
| R1    | `esperie-enterprise` org slug in `validate-bash-command.js:888` comment                                                                                                                 | LOW      | ACCEPTED non-blocking — already dispositioned (REFUTED by authoritative scan per `latest.yaml`); own-org allowlisted                                                |
| R1    | operator handle `pid-esperie-..` in shipped skill examples (`multi-operator-coordination-substrate.md`, `genesis-migration-n1-org-admin-anchor.md`)                                     | LOW      | ACCEPTED non-blocking — truncated illustrative examples, cosmetic; genericize to `alice` in a future canonical loom pass (self-ref-allowlisted skills → own codify) |
| R2    | CONFIRMATION — all 3 R1 accuracy fixes verified correct against ground-truth source, no new sibling drift; fresh sweep clean                                                            | CLEAN    | — (one informational shorthand B-1: "foldLog reads the log" → tightened to "folds … records" per own-the-line)                                                      |
| R3    | MECHANICAL — distributable invariant GREEN (roster PLACEHOLDER, 0 enforcement hooks); 0 bare-primitive citations in the onboarding suite; forward-fix state verified                    | CLEAN    | Convergence confirmed on the onboarding surface                                                                                                                     |

## Convergence criteria

1. 0 CRITICAL ✓ · 2. 0 HIGH on the ONBOARDING surface ✓ — **but 1 HIGH disclosure (ci-runners)
   forward-fixed with OPEN tails → #9 NOT fully converged** · 3. 2 consecutive clean rounds on
   the onboarding surface (R2 confirmation + R3 mechanical) ✓ · 4. every guard-mechanics /
   symbol / cross-ref claim ground-truth-verified against `validate-bash-command.js` /
   `violation-patterns.js` / `genesis-anchor-guard.js` / `operator-id.js` / `coordination-log.js`
   ✓ · 5–7. N/A (COC-artifact suite).

## KEY institutional lessons (candidates for /codify)

- **A file's self-description is not evidence of its git state.** `ci-runners.operator.local.md`
  says "gitignored, never committed" in its own header — and was committed for 7 weeks. Only a
  direct `git ls-files --error-unmatch` / `git check-ignore` (evidence-first MUST-3) surfaced the
  truth; 8 rounds trusted the assertion + the scanner's clean-but-blind exit.
- **A disclosure scanner that self-skips a class is blind to that class.** The
  `.operator.local.md` unconditional skip is the exact parity gap the #352 fix closed for
  `.local.json` — the belt (scanner) had a hole precisely where the suspenders (gitignore) also
  had one. Redundant defenses only help when they fail independently; here both failed on the
  same class.
- **The recurring "description must match the wired mechanism" class extends to symbol OWNERSHIP,
  not just symbol NAME.** whoami cited a real function (`detectStateFileMutation`) that was the
  wrong one (the internal primitive, not the wired `…SegmentAware` wrapper) AND in the wrong file
  — invisible to grep/dangling-ref sweeps because it resolves; only cross-artifact + source
  verification catches it.
