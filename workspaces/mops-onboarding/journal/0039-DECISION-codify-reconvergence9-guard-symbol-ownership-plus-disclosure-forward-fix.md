# DECISION — /codify re-convergence #9: guard-symbol ownership fixes + disclosure forward-fix

Date: 2026-07-09
Phase: 05-codify
Codify anchor advanced: 2026-07-09T08:00:00Z → 2026-07-09T09:00:19Z

## What was codified (landed on the codify branch → PR)

Re-convergence #9 ran a fresh 3-agent adversarial `/redteam` over the merged-main #8 state
(PR #1628) and landed 4 accuracy fixes + a disclosure forward-fix. All source-verified; the
self-referential-codify gate (reviewer + security-reviewer + cc-architect, parallel — required
because `enrollment-operations.md` is allowlisted) returned **3/3 APPROVE**.

- **`.claude/commands/whoami.md`** — guard-symbol fix: `detectStateFileMutation` (the internal
  per-segment primitive) → `detectStateFileMutationSegmentAware` (the wired wrapper in
  `validate-bash-command.js`). whoami was the lone outlier; now agrees with all 4 siblings.
- **`.claude/skills/42-certify/SKILL.md:206`** — the IDENTICAL bare-primitive imprecision,
  surfaced by the self-ref gate reviewer as a same-class gap; fixed IN-SHARD per
  `autonomous-execution.md` MUST-4 (filing a follow-up was BLOCKED). 0 bare-primitive citations
  now remain across the onboarding+certify suite.
- **`.claude/rules/enrollment-operations.md`** — MUST-1 now names BOTH genesis-guard `severity:block`
  branches (real-roster-no-anchor AND enrolled-then-deleted); MUST-4 DO-example corrected
  ("foldLog folds the gitignored coordination-log's records, resolveIdentity reads the committed
  roster" — resolveIdentity reads `operators.roster.json`, a committed file).

## The finding-class this codify extends

The recurring mops-onboarding class — **"a guard's DESCRIPTION must match its DETECTION
mechanism"** — extends here to guard-symbol **OWNERSHIP**, not just name: whoami cited a
real-but-wrong symbol (the primitive, not the wired wrapper), which resolves under grep and so is
invisible to dangling-ref/existence sweeps; only cross-artifact + source verification catches it.

## Disclosure forward-fix (separate from the synced artifacts)

`.gitignore` gained `.claude/rules/*.operator.local.md`; the committed operator-local CI file was
untracked (`git rm --cached`, local copy preserved). Full finding + the two owner-gated/loom tails
(public-history purge; `scan-synced-disclosure.mjs:276` parity fix — flagged to loom in the
proposal since the scanner is loom-distributed) in `journal/0038-RISK-…`.

## Convergence disposition (honest)

The onboarding-artifact surface CONVERGED (0 CRIT/HIGH, 2 consecutive clean rounds, self-ref gate
3/3 APPROVE). Re-convergence #9 is NOT declared fully converged: the HIGH disclosure is
forward-fixed with two tails held per owner approval — no self-attested convergence over an open
HIGH (`verify-resource-existence.md` MUST-4).

## Distribution

BUILD→loom proposal (`latest.yaml`, `pending_review`) appended with the onboarding+certify accuracy
fixes (suggested GLOBAL — the suite is synced cross-SDK) + a loom-tool follow-up flag for the
`scan-synced-disclosure.mjs` parity gap. Scrubbed: the disclosure is referenced by class/file:line,
never the hostnames.
