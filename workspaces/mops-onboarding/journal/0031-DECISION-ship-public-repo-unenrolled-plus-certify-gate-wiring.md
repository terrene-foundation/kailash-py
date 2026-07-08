---
type: DECISION
date: 2026-07-08
slug: ship-public-repo-unenrolled-plus-certify-gate-wiring
relates_to: 0030-AMENDMENT-independent-reconvergence-cert-helper-high
---

# DECISION — Ship kailash-py un-enrolled (public repo) + wire the /certify no-assist gate

Extends journal/0030. The exhaustive full-cohort onboarding redteam (user-approved after the
independent re-convergence) walked every EXECUTABLE surface — code blocks, function-call
signatures, cited hooks/bins, and hook REGISTRATIONS — across all 14 cohort files, since the
prior HIGH lived in a code block, not a prose citation. Two significant findings + one
user-directed architecture decision landed.

## Finding 1 (fixed) — /certify no-assist gate had no structural teeth

`probe-phase-guard.js` is the PR #355 R1 security HIGH-1 closure — a `severity:block`
PreToolUse hook that blocks orchestrator `Read/Grep/Glob/WebFetch` while a
`.claude/.certify-in-probe-<vid>.lock` exists, so a new operator cannot be COACHED through
the SOLO certification gate. The hook exists + ships audit fixtures, and BOTH `certify.md:64`
and `skills/42-certify:58` claim it is "registered in `.claude/settings.json` for matcher
`Read|Grep|Glob|WebFetch`" and "fires whether the LLM remembers or not" — but it was
registered in NO settings surface (repo/global settings.json + settings.local.json + no
hooks.json), so it never fired. The security HIGH PR #355 closed was inert.

Fix: registered the hook under matcher `Read|Grep|Glob|WebFetch` (exactly the docs' claim +
the hook header), timeout 5s. Verified live against its fixtures: no lockfile →
`{continue:true}`; lockfile + Read → `[BLOCK]`. Clone-safe: lockfile-gated, so silent unless
an active `/certify` runs. Commit `974305312`.

## Finding 2 → user decision — the public repo shipped coordination-ON to every clone

Six coordination-ENFORCEMENT PreToolUse hooks (`integrity-guard`, `signing-mutation-guard`,
`journal-write-guard`, `genesis-anchor-guard`, `adjacency-leasecheck`, `operator-gate`) are
registered in NO settings surface and composed by no registered hook (the many
`integrity-guard` mentions in `validate-bash-command.js` are comments). They therefore do
not fire — the codify-branch discipline this repo follows was convention-only.

Root cause (verified): the committed `operators.roster.json` carried a LIVE
`genesis.root_commit` (166c5eab), and `coordination-mode.js::isCoordinationEnabled` resolves
Tier-4 implicit-ON from the COMMITTED roster (the local `.claude/learning/` genesis-anchor is
gitignored). So every clone/fork of this PUBLIC repo inherited coordination = ON — this
working copy returned `true`. That is exactly why the enforcement hooks could NOT be wired
into committed settings.json: `signing-mutation-guard` would drop a fresh forker (no signing
key) into degraded read-only, bricking their fork. The co-owner asked the decisive question —
"if we do the enrolment here, will it mess up the clones?" — and the answer is yes.

**Decision (co-owner, verbatim: "approved your recommendation, we should ship this
un-enrolled"):**

- Do NOT wire the coordination-enforcement hooks into committed settings.json (would brick
  clones). Operator-local enforcement, if ever wanted, goes in the gitignored
  `settings.local.json`.
- Ship the public repo UN-ENROLLED: replace the committed roster with the canonical
  PLACEHOLDER shape `clean-instantiate.mjs` produces (`repo_owner "PLACEHOLDER-owner"`,
  `root_commit "0000000"`, one `PLACEHOLDER-owner` person + synthetic key). Verified:
  `isCoordinationEnabled(cwd)` now returns `false` (clones resolve OFF); roster-schema-validate
  `{valid:true}`; 0 residual esperie identity tokens in the committed public repo; disclosure
  scanner exit 0. A forker enrolls their own clone via `/ecosystem-init` / `/whoami --register`.
  Commit `862d28904`.
- Codify the lesson: `enrollment-operations.md` gains a "Distributable-Repo Caveat" section so
  no future session re-enrolls the public repo or wires enforcement hooks into committed
  settings (either bricks clones).

## Alternatives considered

- **Wire the 6 enforcement hooks into committed settings.json** (my initial Option A) —
  REJECTED once the committed-roster-forces-clones-ON mechanism was verified: it bricks every
  clone. The co-owner's question surfaced this before it shipped.
- **Leave the live genesis committed, add enforcement only in settings.local.json** — viable
  for esperie's local enforcement, but leaves clones inheriting coordination-ON with esperie's
  identity as genesis owner (a latent trap + an identity footprint). Shipping un-enrolled is
  cleaner for a public fork-template.
- **Full `clean-instantiate.mjs` run** — REJECTED: it also deletes `journal/`, resets
  ecosystem.json/tenant-denylist, and runs assert-zero — far beyond the one-file roster reset
  needed, and would nuke this workspace's journals.

## For Discussion

1. Counterfactual: if the co-owner had NOT asked "will it mess up the clones?", the initial
   Option-A (wire the enforcement hooks into committed settings.json) would have shipped and
   bricked every fresh fork on first edit. What structural check would have caught the
   committed-roster-forces-clones-ON coupling BEFORE the wiring PR? (Candidate: a
   distributable-repo lint asserting the committed roster is PLACEHOLDER + no
   coordination-enforcement hook in committed settings.json — the caveat's mechanical twin.)
2. esperie's OWN working copy now resolves coordination OFF (reads the placeholder committed
   roster). The local gitignored genesis-anchor is now orphaned. If real multi-operator
   coordination is ever needed in kailash-py, is a Tier-2 local override (gitignored
   `{enabled:true}`) + settings.local.json enforcement the intended path, or should genuine
   multi-operator work happen in a non-public repo?
