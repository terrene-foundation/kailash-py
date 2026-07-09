# AMENDMENT — re-convergence #9 disclosure RISK closed (forward-fix sufficient)

Date: 2026-07-09
Phase: 05-codify
Amends: journal/0038-RISK-committed-operator-local-ci-values-public-repo.md
Author: co-authored (owner-directed closure)

## Disposition (owner decision)

The HIGH disclosure RISK in `journal/0038` is CLOSED as **remediated by the forward-fix** (untrack +
`.gitignore` glob, merged in PR #1629). The two originally-open tails are dispositioned:

- **T1 — public git-history purge: DECLINED as disproportionate.** Owner-reviewed the material facts:
  the exposed content is infra NAMES (3 CI hostnames/a runner label), NOT credentials/keys — nobody
  gains access from them; the repo has **3 public forks** + GitHub SHA caches a history rewrite cannot
  reach (best-effort only); the rewrite would re-SHA 1,276 commits and requires temporarily
  unprotecting public `main`. Real cost/risk for near-zero security gain on low-sensitivity names.
  Label ROTATION was also declined (renaming machines for names-in-a-log is disproportionate). The
  merged forward-fix stops recurrence, which is the part that matters.
- **T2 — `scan-synced-disclosure.mjs:276` parity fix: OPEN, routed to loom.** This is the one real
  follow-up (it's what let the leak slip past 8 rounds). Routed via the BUILD→loom PROPOSAL
  (`.claude/.proposals/latest.yaml`, the `LOOM-TOOL FOLLOW-UP FLAG` in the #9 change entry) — the
  canonical BUILD→loom lane; loom picks it up at Gate-1 on the next `/sync-from-build`. NOT filed as a
  standalone loom GH issue (a BUILD repo flows proposals, not direct cross-repo issues — `artifact-flow.md`).

## Net

Disclosure RISK closed. Forward-fix is the remediation of record. Only T2 (scanner parity) remains,
owned by loom via the proposal.
